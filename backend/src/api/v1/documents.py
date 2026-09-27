"""
Knowledge-base endpoints.

FR vi   Knowledge-Base Upload      FR vii  Document Validation
FR viii Document Parsing           FR ix   Document Chunking
FR x    Document Version Control   FR xxii Policy Retrieval
FR l    Policy Traceability

Access model: administrators manage the corpus; every other staff role may read
it.  The evaluator role has read access throughout so a judge can inspect the
knowledge base without being handed an administrator token.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile, status
from sqlalchemy import func, select

from knowledge_base import versioning
from knowledge_base.embeddings import is_available as embeddings_available
from knowledge_base.ingest import activate as activate_version
from knowledge_base.ingest import deactivate as deactivate_version
from knowledge_base.ingest import ingest_document
from knowledge_base.retrieval import coverage_stats, resolve_citation, retrieve
from schemas.common import Page
from schemas.documents import (
    ActivationResponse,
    Citation,
    CoverageResponse,
    DocumentDetail,
    DocumentSummary,
    DocumentVersionDetail,
    DocumentVersionSummary,
    IngestIssue,
    PolicyImpactOut,
    RetrievedChunkOut,
    SearchRequest,
    SearchResponse,
    SectionOut,
    TraceabilityResponse,
    UploadResponse,
    UploadResult,
    ValidationIssueOut,
)
from src.core.deps import CurrentUser, DbSession, require_role
from src.core.errors import NotFoundError, ValidationError
from src.core.logging import get_logger
from src.core.response_cache import cached_endpoint
from src.db.enums import DocStatus, UserRole
from src.db.models import (
    Chunk,
    Document,
    DocumentSection,
    DocumentValidationIssue,
    DocumentVersion,
)
from src.services import policy_update

log = get_logger("api.documents")

router = APIRouter(prefix="/documents", tags=["Knowledge Base"])

AdminOnly = Depends(require_role(UserRole.ADMIN))
StaffRead = Depends(
    require_role(
        UserRole.ADMIN, UserRole.MANAGER, UserRole.REVIEWER,
        UserRole.AGENT, UserRole.EVALUATOR,
    )
)

MAX_FILES_PER_UPLOAD = 25


# ══════════════════════════════════════════════════════════════
# upload
# ══════════════════════════════════════════════════════════════
@router.post(
    "",
    response_model=UploadResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[AdminOnly],
    summary="Upload one or more knowledge-base documents",
)
def upload_documents(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    files: list[UploadFile] = File(..., description="PDF or DOCX files"),
    department_code: str | None = Query(None, description="Override the owning department"),
    activate: bool = Query(
        True,
        description=(
            "Activate immediately. Pass false to stage a new version for "
            "impact review before it supersedes the current one."
        ),
    ),
) -> UploadResponse:
    """
    Ingest documents: validate, parse, chunk, embed and version.

    A rejected file returns ``accepted=false`` with its reasons rather than an
    HTTP error, so one bad file in a batch does not discard the good ones.
    Every rejection is recorded in ``document_validation_issues``.
    """
    if not files:
        raise ValidationError("No files were uploaded.")
    if len(files) > MAX_FILES_PER_UPLOAD:
        raise ValidationError(
            f"At most {MAX_FILES_PER_UPLOAD} files may be uploaded at once.",
            details={"received": len(files)},
        )

    results: list[UploadResult] = []
    for upload in files:
        data = upload.file.read()
        outcome = ingest_document(
            db, data, upload.filename or "unnamed",
            uploaded_by=user.id,
            activate=activate,
            department_code=department_code,
            request=request,
        )
        version = outcome.document_version
        results.append(
            UploadResult(
                file_name=outcome.file_name,
                accepted=outcome.accepted,
                message=outcome.message,
                document_version_id=version.id if version else None,
                doc_ref=version.doc_ref if version else None,
                version=version.version if version else None,
                status=version.status if version else None,
                section_count=outcome.section_count,
                chunk_count=outcome.chunk_count,
                embedded_count=outcome.embedded_count,
                superseded_version=outcome.superseded_version,
                requires_review=outcome.requires_review,
                issues=[
                    IngestIssue(
                        code=i.code.value, message=i.message,
                        field=i.field, detail=i.detail, fatal=i.fatal,
                    )
                    for i in outcome.issues
                ],
            )
        )

    accepted = sum(1 for r in results if r.accepted)
    return UploadResponse(
        uploaded=len(results),
        accepted=accepted,
        rejected=len(results) - accepted,
        requires_review=sum(1 for r in results if r.requires_review),
        results=results,
    )


# ══════════════════════════════════════════════════════════════
# browse
# ══════════════════════════════════════════════════════════════
@router.get(
    "",
    response_model=Page[DocumentSummary],
    dependencies=[StaffRead],
    summary="List knowledge-base documents",
)
@cached_endpoint(ttl=60)
def list_documents(
    db: DbSession,
    q: str | None = Query(None, description="Match on title or document reference"),
    doc_type: str | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
) -> Page[DocumentSummary]:
    query = select(Document)
    if q:
        needle = f"%{q.strip()}%"
        query = query.where(
            Document.title.ilike(needle) | Document.family_key.ilike(needle)
        )
    if doc_type:
        query = query.where(Document.doc_type == doc_type.upper())

    total = db.execute(
        select(func.count()).select_from(query.subquery())
    ).scalar_one()

    documents = db.execute(
        query.order_by(Document.title).offset((page - 1) * page_size).limit(page_size)
    ).scalars().all()

    wanted_status = status_filter.upper() if status_filter else None

    items: list[DocumentSummary] = []
    for document in documents:
        versions = document.versions
        active = next((v for v in versions if v.status == DocStatus.ACTIVE), None)

        # `status` filters on the document's *current* state. A document whose
        # only versions are superseded or under review has no active version,
        # so it is excluded unless that is what was asked for.
        if wanted_status and wanted_status != "ANY":
            current = active.status if active else DocStatus.METADATA_REVIEW
            if current != wanted_status:
                continue

        summary = DocumentSummary.model_validate(document)
        summary.version_count = len(versions)
        summary.active_version = (
            DocumentVersionSummary.model_validate(active) if active else None
        )
        items.append(summary)

    return Page[DocumentSummary](
        items=items, total=total, page=page, page_size=page_size
    )


@router.get(
    "/coverage",
    response_model=CoverageResponse,
    dependencies=[StaffRead],
    summary="Knowledge-base corpus health",
)
@cached_endpoint(ttl=60)
def coverage(db: DbSession) -> CoverageResponse:
    stats = coverage_stats(db)
    return CoverageResponse(
        **stats,
        knowledge_base_version=versioning.knowledge_base_version(db),
        semantic_search_available=embeddings_available(),
    )


@router.get(
    "/validation-issues",
    response_model=Page[ValidationIssueOut],
    dependencies=[StaffRead],
    summary="Recorded document validation findings (SRS Step 4 evidence)",
)
def list_validation_issues(
    db: DbSession,
    issue_code: str | None = Query(None),
    outcome: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> Page[ValidationIssueOut]:
    """
    Every check that fired, including on files that were refused.

    This is the endpoint that answers "prove your invalid-file handling runs"
    without needing to re-upload anything.
    """
    query = select(DocumentValidationIssue)
    if issue_code:
        query = query.where(DocumentValidationIssue.issue_code == issue_code.upper())
    if outcome:
        query = query.where(DocumentValidationIssue.outcome == outcome.upper())

    total = db.execute(select(func.count()).select_from(query.subquery())).scalar_one()
    rows = db.execute(
        query.order_by(DocumentValidationIssue.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).scalars().all()

    return Page[ValidationIssueOut](
        items=[ValidationIssueOut.model_validate(r) for r in rows],
        total=total, page=page, page_size=page_size,
    )


@router.get(
    "/versions/{version_id}",
    response_model=DocumentVersionDetail,
    dependencies=[StaffRead],
    summary="One document version with its sections and validation findings",
)
def get_version(version_id: uuid.UUID, db: DbSession) -> DocumentVersionDetail:
    version = db.get(DocumentVersion, version_id)
    if version is None:
        raise NotFoundError("Document version not found.")

    sections = db.execute(
        select(DocumentSection)
        .where(DocumentSection.document_version_id == version.id)
        .order_by(DocumentSection.ordinal)
    ).scalars().all()

    issues = db.execute(
        select(DocumentValidationIssue)
        .where(DocumentValidationIssue.document_version_id == version.id)
        .order_by(DocumentValidationIssue.created_at)
    ).scalars().all()

    detail = DocumentVersionDetail.model_validate(version)
    detail.sections = [SectionOut.model_validate(s) for s in sections]
    detail.validation_issues = [ValidationIssueOut.model_validate(i) for i in issues]
    return detail


# ══════════════════════════════════════════════════════════════
# version control
# ══════════════════════════════════════════════════════════════
@router.post(
    "/versions/{version_id}/activate",
    response_model=ActivationResponse,
    dependencies=[AdminOnly],
    summary="Activate a version, superseding the current one",
)
def activate(
    version_id: uuid.UUID, request: Request, db: DbSession, user: CurrentUser
) -> ActivationResponse:
    existing = db.get(DocumentVersion, version_id)
    if existing is None:
        raise NotFoundError("Document version not found.")

    previous = versioning.current_active(db, existing.document_id)
    previous_label = previous.version if previous and previous.id != existing.id else None
    previous_id = previous.id if previous and previous.id != existing.id else None

    version = activate_version(db, version_id, actor=user, request=request)

    # Read after the switch, so `active_version` names the version that now
    # governs rather than the one that did a moment ago.
    report = (
        policy_update.impact(db, previous_id) if previous_id is not None else None
    )

    return ActivationResponse(
        document_version_id=version.id,
        doc_ref=version.doc_ref,
        version=version.version,
        status=version.status,
        superseded_version=previous_label,
        message=(
            f"{version.doc_ref} v{version.version} is now active."
            + (f" v{previous_label} was superseded." if previous_label else "")
            + (
                f" {report.open_count} open complaint(s) were decided under it."
                if report and report.open_count
                else ""
            )
        ),
        impact=PolicyImpactOut(**report.summary()) if report else None,
    )


@router.get(
    "/versions/{version_id}/impact",
    response_model=PolicyImpactOut,
    dependencies=[StaffRead],
    summary="Which complaints were decided under this version",
)
def version_impact(version_id: uuid.UUID, db: DbSession) -> PolicyImpactOut:
    """
    The blast radius of a policy change (SRS 1.8 #4).

    Read from stored citations rather than recomputed: ``complaint_policy_refs``
    records which version each reference actually resolved to at the time, so
    this stays correct even after the corpus moves on again.
    """
    if db.get(DocumentVersion, version_id) is None:
        raise NotFoundError("Document version not found.")
    return PolicyImpactOut(**policy_update.impact(db, version_id).summary())


@router.post(
    "/versions/{version_id}/deactivate",
    response_model=ActivationResponse,
    dependencies=[AdminOnly],
    summary="Withdraw an active version without deleting it",
)
def deactivate(
    version_id: uuid.UUID, request: Request, db: DbSession, user: CurrentUser
) -> ActivationResponse:
    version = deactivate_version(db, version_id, actor=user, request=request)
    return ActivationResponse(
        document_version_id=version.id,
        doc_ref=version.doc_ref,
        version=version.version,
        status=version.status,
        message=(
            f"{version.doc_ref} v{version.version} withdrawn. "
            "Its text is retained for contradiction detection."
        ),
    )


# ══════════════════════════════════════════════════════════════
# retrieval and traceability
# ══════════════════════════════════════════════════════════════
@router.post(
    "/search",
    response_model=SearchResponse,
    dependencies=[StaffRead],
    summary="Search the knowledge base (hybrid lexical + semantic)",
)
def search(payload: SearchRequest, db: DbSession) -> SearchResponse:
    """
    The same retrieval the GenAI pipeline uses, exposed directly.

    Running it standalone is how an evaluator confirms which passages the model
    was given, separately from what the model did with them.
    """
    result = retrieve(
        db,
        payload.query,
        top_k=payload.top_k,
        include_superseded=payload.include_superseded,
        doc_refs=payload.doc_refs,
        semantic=payload.semantic,
    )
    return SearchResponse(
        query=result.query,
        results=[
            RetrievedChunkOut(
                chunk_key=c.chunk_key, text=c.text,
                doc_ref=c.doc_ref, doc_version=c.doc_version,
                section_ref=c.section_ref, heading=c.heading,
                page_no=c.page_no, paragraph_index=c.paragraph_index,
                score=round(c.score, 6), matched_by=c.matched_by,
                lexical_rank=c.lexical_rank, semantic_rank=c.semantic_rank,
                exact_rank=c.exact_rank,
            )
            for c in result.chunks
        ],
        lexical_count=result.lexical_count,
        semantic_count=result.semantic_count,
        exact_count=result.exact_count,
        semantic_available=result.semantic_available,
        knowledge_base_empty=result.knowledge_base_empty,
        cited_documents=result.cited_documents,
    )


@router.get(
    "/trace/{chunk_key:path}",
    response_model=TraceabilityResponse,
    dependencies=[StaffRead],
    summary="Resolve a citation back to its source (Traceability Challenge)",
)
def trace(chunk_key: str, db: DbSession) -> TraceabilityResponse:
    """
    Given a citation, return the exact source passage and whether it may be
    relied upon.

    An unresolvable citation returns ``resolved=false`` rather than a 404: a
    reference that does not exist is a *finding*, and it is the signal
    hallucination detection is built on.
    """
    chunk = resolve_citation(db, chunk_key=chunk_key)
    if chunk is None:
        return TraceabilityResponse(
            resolved=False,
            reason=(
                "No chunk with this key exists in the knowledge base. "
                "A generated statement citing it is unsupported."
            ),
        )

    version = db.get(DocumentVersion, chunk.document_version_id)
    section = None
    if chunk.section_id:
        section = db.get(DocumentSection, chunk.section_id)

    return TraceabilityResponse(
        resolved=True,
        citation=Citation(**chunk.as_citation()),
        document_title=version.title if version else None,
        document_status=version.status if version else None,
        applicability=versioning.applicability_for(version),
        effective_date=version.effective_date if version else None,
        expiry_date=version.expiry_date if version else None,
        text=chunk.text,
        section_text=section.text if section else None,
    )


@router.get(
    "/chunks/by-reference",
    response_model=TraceabilityResponse,
    dependencies=[StaffRead],
    summary="Resolve a citation by document reference and section",
)
def trace_by_reference(
    db: DbSession,
    doc_ref: str = Query(..., description="e.g. DEL-POL-04"),
    section_ref: str | None = Query(None, description="e.g. 5.2"),
) -> TraceabilityResponse:
    chunk = resolve_citation(db, doc_ref=doc_ref, section_ref=section_ref)
    if chunk is None:
        return TraceabilityResponse(
            resolved=False,
            reason=(
                f"No active or superseded content matches {doc_ref}"
                f"{' section ' + section_ref if section_ref else ''}."
            ),
        )
    return trace(chunk.chunk_key, db)


@router.get(
    "/versions/{version_id}/chunks",
    response_model=list[RetrievedChunkOut],
    dependencies=[StaffRead],
    summary="Every chunk of a version, in reading order",
)
def version_chunks(version_id: uuid.UUID, db: DbSession) -> list[RetrievedChunkOut]:
    chunks = db.execute(
        select(Chunk)
        .where(Chunk.document_version_id == version_id)
        .order_by(Chunk.ordinal)
    ).scalars().all()
    if not chunks and db.get(DocumentVersion, version_id) is None:
        raise NotFoundError("Document version not found.")

    return [
        RetrievedChunkOut(
            chunk_key=c.chunk_key, text=c.text,
            doc_ref=c.doc_ref, doc_version=c.doc_version,
            section_ref=c.section_ref, heading=c.heading,
            page_no=c.page_no, paragraph_index=c.paragraph_index,
            score=0.0, matched_by="DIRECT",
        )
        for c in chunks
    ]


# Declared last on purpose: this UUID catch-all would otherwise shadow the
# literal /versions/... , /search, /trace/... and /chunks/... routes above,
# because FastAPI matches paths in declaration order.
@router.get(
    "/{document_id}",
    response_model=DocumentDetail,
    dependencies=[StaffRead],
    summary="One document with its full version history",
)
def get_document(document_id: uuid.UUID, db: DbSession) -> DocumentDetail:
    document = db.get(Document, document_id)
    if document is None:
        raise NotFoundError("Document not found.")

    detail = DocumentDetail.model_validate(document)
    versions = sorted(document.versions, key=lambda v: v.created_at, reverse=True)
    detail.versions = [DocumentVersionSummary.model_validate(v) for v in versions]
    detail.version_count = len(versions)
    active = next((v for v in versions if v.status == DocStatus.ACTIVE), None)
    detail.active_version = DocumentVersionSummary.model_validate(active) if active else None
    return detail
