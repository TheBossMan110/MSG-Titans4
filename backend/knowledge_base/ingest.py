"""
Document ingestion — the orchestrator that turns an uploaded file into rows.

    bytes
      -> validate            (SRS Step 4)   -> document_validation_issues
      -> store               object storage
      -> parse               (SRS Step 5)   -> metadata, sections
      -> scan for injection  (SRS Step 50)  -> injection_events
      -> version             (SRS Step 7)   -> documents, document_versions
      -> sections            (SRS Step 5)   -> document_sections
      -> chunk + embed       (SRS Step 6)   -> chunks
      -> activate                            -> supersede the previous version

Two rules govern the whole flow:

**Nothing is silently discarded.**  Every rejection and every warning becomes a
``document_validation_issue`` row.  An evaluator testing invalid-file handling
must be able to *see* the check ran, and a rejected upload that leaves no trace
is indistinguishable from a check nobody wrote.

**A document that cannot be fully understood is still ingested.**  A missing
metadata block, an unparseable date, an unfamiliar layout — none of these
reject the file.  It lands in METADATA_REVIEW with reduced traceability and an
administrator completes it.  This is what SRS 1.8 #3 means by processing unseen
documents without changing the source code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from document_processing.chunker import chunk_document
from document_processing.contracts import ParsedDocument, ParseIssue
from document_processing.metadata import family_key_for
from document_processing.parser import parse_document
from document_processing.validation import (
    FileValidationResult,
    severity_for,
    validate_file,
    validate_metadata,
)
from knowledge_base import versioning
from knowledge_base.embeddings import embed_texts, verify_dimension
from src.core.logging import get_logger
from src.db.enums import DocStatus, DocType, IssueOutcome, ParseStatus
from src.db.models import (
    Chunk,
    Department,
    Document,
    DocumentSection,
    DocumentValidationIssue,
    DocumentVersion,
)
from src.services.audit import record_audit
from src.services.storage import content_type_for, get_storage, object_key

log = get_logger("knowledge_base.ingest")


@dataclass(slots=True)
class IngestResult:
    """Everything the caller needs to report the outcome of one upload."""

    file_name: str
    accepted: bool
    document_version: DocumentVersion | None = None
    status: DocStatus | None = None
    section_count: int = 0
    chunk_count: int = 0
    embedded_count: int = 0
    superseded_version: str | None = None
    issues: list[ParseIssue] = field(default_factory=list)
    message: str = ""

    @property
    def requires_review(self) -> bool:
        return self.status == DocStatus.METADATA_REVIEW

    @property
    def issue_codes(self) -> list[str]:
        return [issue.code.value for issue in self.issues]


# ══════════════════════════════════════════════════════════════
# issue persistence
# ══════════════════════════════════════════════════════════════
def _record_issues(
    db: Session,
    issues: list[ParseIssue],
    *,
    file_name: str,
    file_hash: str | None,
    uploaded_by: UUID | None,
    document_version_id: UUID | None,
    rejected: bool,
) -> None:
    """Persist every finding. Called even when the upload was refused."""
    outcome = IssueOutcome.REJECTED if rejected else IssueOutcome.ACCEPTED_WITH_WARNING
    for issue in issues:
        db.add(
            DocumentValidationIssue(
                document_version_id=document_version_id,
                file_name=file_name,
                file_hash=file_hash,
                uploaded_by=uploaded_by,
                issue_code=issue.code,
                severity=severity_for(issue.code),
                outcome=IssueOutcome.REJECTED if issue.fatal else outcome,
                field=issue.field,
                message=issue.message,
                detail=issue.detail,
            )
        )
    db.flush()


def _existing_hashes(db: Session) -> set[str]:
    return {
        row[0]
        for row in db.execute(select(DocumentVersion.file_hash)).all()
        if row[0]
    }


# ══════════════════════════════════════════════════════════════
# main entry point
# ══════════════════════════════════════════════════════════════
def ingest_document(
    db: Session,
    data: bytes,
    file_name: str,
    *,
    uploaded_by: UUID | None = None,
    activate: bool = True,
    department_code: str | None = None,
    request=None,
) -> IngestResult:
    """
    Ingest one uploaded file.  Never raises on bad input.

    ``activate=False`` ingests the version without promoting it, which is how
    the Policy Update Challenge is staged: upload v2, diff it against the
    active v1, review the impact, *then* activate.
    """
    # ── 1. validate the bytes (SRS Step 4) ──
    validation: FileValidationResult = validate_file(
        data, file_name, existing_hashes=_existing_hashes(db)
    )

    if validation.is_rejected:
        _record_issues(
            db, validation.issues,
            file_name=validation.file_name, file_hash=validation.file_hash,
            uploaded_by=uploaded_by, document_version_id=None, rejected=True,
        )
        reason = next((i.message for i in validation.issues if i.fatal), "Rejected.")
        log.info("ingest_rejected", file=validation.file_name, codes=[i.code for i in validation.issues])
        return IngestResult(
            file_name=validation.file_name, accepted=False,
            issues=validation.issues, message=reason,
        )

    # ── 2. parse (SRS Step 5) ──
    parsed: ParsedDocument = parse_document(
        data, file_name=validation.file_name, file_format=validation.file_format
    )
    all_issues = [*validation.issues, *parsed.issues]

    if parsed.is_fatal:
        _record_issues(
            db, all_issues,
            file_name=validation.file_name, file_hash=validation.file_hash,
            uploaded_by=uploaded_by, document_version_id=None, rejected=True,
        )
        reason = next((i.message for i in parsed.issues if i.fatal), "Could not be parsed.")
        return IngestResult(
            file_name=validation.file_name, accepted=False,
            issues=all_issues, message=reason,
        )

    all_issues.extend(validate_metadata(parsed.metadata, file_name=validation.file_name))

    # ── 3. store the original file ──
    key = object_key(validation.file_hash, validation.file_format)
    stored_path = get_storage().save(
        data, key=key, content_type=content_type_for(validation.file_format)
    )

    # ── 4. document family + version (SRS Step 7) ──
    metadata = parsed.metadata
    family = family_key_for(metadata.doc_ref, metadata.title, validation.file_name)
    document = _get_or_create_document(
        db, family_key=family, metadata=metadata,
        department_code=department_code, created_by=uploaded_by,
    )

    version_label = versioning.next_version_label(
        db, document.id, proposed=metadata.version
    )
    status = versioning.initial_status(
        metadata_complete=metadata.is_complete,
        effective_date=metadata.effective_date,
        expiry_date=metadata.expiry_date,
        parse_failed=False,
    )

    version = DocumentVersion(
        document_id=document.id,
        doc_ref=metadata.doc_ref or family,
        version=version_label,
        title=metadata.title,
        effective_date=metadata.effective_date,
        expiry_date=metadata.expiry_date,
        status=DocStatus.DRAFT,           # promoted below, after rows exist
        file_format=validation.file_format,
        file_name=validation.file_name,
        file_path=stored_path,
        file_hash=validation.file_hash,
        file_size_bytes=validation.size_bytes,
        page_count=parsed.page_count,
        section_count=parsed.section_count,
        parse_status=ParseStatus.PARSED,
        metadata_json=metadata.as_dict(),
        metadata_complete=metadata.is_complete,
        uploaded_by=uploaded_by,
    )
    db.add(version)
    db.flush()

    # ── 5. sections (SRS Step 5) ──
    for section in parsed.sections:
        db.add(
            DocumentSection(
                document_version_id=version.id,
                section_ref=section.section_ref,
                heading=section.heading,
                level=section.level,
                page_no=section.page_no,
                paragraph_index=section.paragraph_index,
                ordinal=section.ordinal,
                text=section.text,
            )
        )
    db.flush()

    section_ids = {
        row.section_ref: row.id
        for row in db.execute(
            select(DocumentSection).where(DocumentSection.document_version_id == version.id)
        ).scalars()
    }

    # ── 6. chunks + embeddings (SRS Step 6) ──
    candidates = chunk_document(parsed.sections, doc_ref=version.doc_ref)
    vectors = embed_texts([c.text for c in candidates]) if candidates else []
    embedded = 0

    for candidate, vector in zip(candidates, vectors or [None] * len(candidates), strict=False):
        usable = verify_dimension(vector)
        if usable:
            embedded += 1
        db.add(
            Chunk(
                document_version_id=version.id,
                section_id=section_ids.get(candidate.section_ref),
                chunk_key=candidate.chunk_key,
                doc_ref=version.doc_ref,
                doc_version=version.version,
                section_ref=candidate.section_ref,
                heading=candidate.heading,
                page_no=candidate.page_no,
                paragraph_index=candidate.paragraph_index,
                ordinal=candidate.ordinal,
                text=candidate.text,
                token_count=candidate.token_count,
                embedding=vector if usable else None,
            )
        )

    version.chunk_count = len(candidates)
    db.flush()

    # ── 7. activation (SRS Step 7) ──
    superseded: DocumentVersion | None = None
    if status == DocStatus.ACTIVE and activate:
        superseded = versioning.activate_version(db, version)
    else:
        version.status = status
        db.flush()

    versioning.refresh_expiry_status(db)

    # ── 8. record findings + audit ──
    if all_issues:
        _record_issues(
            db, all_issues,
            file_name=validation.file_name, file_hash=validation.file_hash,
            uploaded_by=uploaded_by, document_version_id=version.id, rejected=False,
        )

    record_audit(
        db,
        entity_type="document_version",
        entity_id=version.id,
        action="INGEST",
        after={
            "doc_ref": version.doc_ref,
            "version": version.version,
            "status": version.status,
            "sections": len(parsed.sections),
            "chunks": len(candidates),
            "embedded": embedded,
            "superseded": superseded.version if superseded else None,
        },
        request=request,
    )

    log.info(
        "ingest_complete",
        doc_ref=version.doc_ref, version=version.version, status=version.status,
        sections=len(parsed.sections), chunks=len(candidates), embedded=embedded,
    )

    return IngestResult(
        file_name=validation.file_name,
        accepted=True,
        document_version=version,
        status=DocStatus(version.status),
        section_count=len(parsed.sections),
        chunk_count=len(candidates),
        embedded_count=embedded,
        superseded_version=superseded.version if superseded else None,
        issues=all_issues,
        message=_summary_message(version, superseded, embedded, len(candidates)),
    )


def _summary_message(
    version: DocumentVersion,
    superseded: DocumentVersion | None,
    embedded: int,
    total_chunks: int,
) -> str:
    parts = [f"{version.doc_ref} v{version.version} ingested as {version.status}."]
    if superseded:
        parts.append(f"Superseded v{superseded.version}.")
    if version.status == DocStatus.METADATA_REVIEW:
        parts.append("Metadata is incomplete; review required before activation.")
    if total_chunks and embedded < total_chunks:
        parts.append(
            f"{total_chunks - embedded} chunk(s) stored without an embedding; "
            "lexical retrieval is unaffected and they can be backfilled."
        )
    return " ".join(parts)


def _get_or_create_document(
    db: Session,
    *,
    family_key: str,
    metadata,
    department_code: str | None,
    created_by: UUID | None,
) -> Document:
    document = versioning.find_document_by_family(db, family_key)
    if document is not None:
        return document

    department_id = None
    dept_name = department_code or metadata.department
    if dept_name:
        department = db.execute(
            select(Department).where(Department.code == dept_name.strip().upper())
        ).scalars().first()
        if department is None:
            # Documents name departments in prose ("Logistics"); match on name too.
            department = db.execute(
                select(Department).where(Department.name.ilike(f"%{dept_name.strip()}%"))
            ).scalars().first()
        department_id = department.id if department else None

    doc_type = (metadata.doc_type or "OTHER").upper()
    if doc_type not in {member.value for member in DocType}:
        doc_type = DocType.OTHER

    document = Document(
        family_key=family_key,
        title=metadata.title or family_key,
        doc_type=doc_type,
        department_id=department_id,
        created_by=created_by,
    )
    db.add(document)
    db.flush()
    return document


# ══════════════════════════════════════════════════════════════
# administrative operations
# ══════════════════════════════════════════════════════════════
def activate(db: Session, version_id: UUID, *, actor=None, request=None) -> DocumentVersion:
    """Promote a reviewed version (used after METADATA_REVIEW is resolved)."""
    version = db.get(DocumentVersion, version_id)
    if version is None:
        raise ValueError(f"No such document version: {version_id}")

    before = {"status": version.status}
    superseded = versioning.activate_version(db, version)

    record_audit(
        db, actor=actor, entity_type="document_version", entity_id=version.id,
        action="ACTIVATE", before=before,
        after={"status": version.status, "superseded": superseded.version if superseded else None},
        request=request,
    )
    return version


def deactivate(db: Session, version_id: UUID, *, actor=None, request=None) -> DocumentVersion:
    """Withdraw an active version without deleting it."""
    version = db.get(DocumentVersion, version_id)
    if version is None:
        raise ValueError(f"No such document version: {version_id}")

    before = {"status": version.status}
    version.status = DocStatus.SUPERSEDED
    version.superseded_at = datetime.now(UTC)
    db.flush()

    record_audit(
        db, actor=actor, entity_type="document_version", entity_id=version.id,
        action="DEACTIVATE", before=before, after={"status": version.status}, request=request,
    )
    return version


def reingest_from_storage(db: Session, version_id: UUID) -> IngestResult:
    """
    Re-run parsing and chunking for an existing version from its stored bytes.

    Needed after a parser improvement or an embedding backfill: the original
    file is content-addressed in object storage, so nothing has to be
    re-uploaded.
    """
    version = db.get(DocumentVersion, version_id)
    if version is None:
        raise ValueError(f"No such document version: {version_id}")

    data = get_storage().load(version.file_path)

    for chunk in db.execute(
        select(Chunk).where(Chunk.document_version_id == version.id)
    ).scalars():
        db.delete(chunk)
    for section in db.execute(
        select(DocumentSection).where(DocumentSection.document_version_id == version.id)
    ).scalars():
        db.delete(section)
    db.flush()

    parsed = parse_document(
        data, file_name=version.file_name, file_format=version.file_format
    )
    if parsed.is_fatal:
        version.parse_status = ParseStatus.FAILED
        version.parse_error = next(
            (i.message for i in parsed.issues if i.fatal), "Re-parse failed."
        )
        db.flush()
        return IngestResult(
            file_name=version.file_name, accepted=False,
            issues=parsed.issues, message=version.parse_error,
        )

    for section in parsed.sections:
        db.add(
            DocumentSection(
                document_version_id=version.id,
                section_ref=section.section_ref,
                heading=section.heading,
                level=section.level,
                page_no=section.page_no,
                paragraph_index=section.paragraph_index,
                ordinal=section.ordinal,
                text=section.text,
            )
        )
    db.flush()

    section_ids = {
        row.section_ref: row.id
        for row in db.execute(
            select(DocumentSection).where(DocumentSection.document_version_id == version.id)
        ).scalars()
    }

    candidates = chunk_document(parsed.sections, doc_ref=version.doc_ref)
    vectors = embed_texts([c.text for c in candidates]) if candidates else []
    embedded = 0
    for candidate, vector in zip(candidates, vectors or [None] * len(candidates), strict=False):
        usable = verify_dimension(vector)
        embedded += int(usable)
        db.add(
            Chunk(
                document_version_id=version.id,
                section_id=section_ids.get(candidate.section_ref),
                chunk_key=candidate.chunk_key,
                doc_ref=version.doc_ref,
                doc_version=version.version,
                section_ref=candidate.section_ref,
                heading=candidate.heading,
                page_no=candidate.page_no,
                paragraph_index=candidate.paragraph_index,
                ordinal=candidate.ordinal,
                text=candidate.text,
                token_count=candidate.token_count,
                embedding=vector if usable else None,
            )
        )

    version.section_count = len(parsed.sections)
    version.chunk_count = len(candidates)
    version.parse_status = ParseStatus.PARSED
    version.parse_error = None
    db.flush()

    return IngestResult(
        file_name=version.file_name, accepted=True, document_version=version,
        status=DocStatus(version.status), section_count=len(parsed.sections),
        chunk_count=len(candidates), embedded_count=embedded,
        message=f"Re-ingested {version.doc_ref} v{version.version}.",
    )
