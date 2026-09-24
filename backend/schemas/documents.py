"""Knowledge-base API schemas (FR vi–x, FR xxii, FR l)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field

from schemas.common import APIModel


# ══════════════════════════════════════════════════════════════
# upload
# ══════════════════════════════════════════════════════════════
class ValidationIssueOut(APIModel):
    """One recorded finding from document validation (SRS Step 4)."""

    id: uuid.UUID
    issue_code: str
    severity: str
    outcome: str
    field: str | None = None
    message: str
    detail: str | None = None
    file_name: str
    document_version_id: uuid.UUID | None = None
    created_at: datetime


class IngestIssue(BaseModel):
    code: str
    message: str
    field: str | None = None
    detail: str | None = None
    fatal: bool = False


class UploadResult(BaseModel):
    """
    Outcome of one uploaded file.

    Rejections are returned as ``accepted=false`` with the reasons attached
    rather than as an HTTP error, so a batch upload reports per-file outcomes
    instead of failing wholesale on the first bad file.
    """

    file_name: str
    accepted: bool
    message: str
    document_version_id: uuid.UUID | None = None
    doc_ref: str | None = None
    version: str | None = None
    status: str | None = None
    section_count: int = 0
    chunk_count: int = 0
    embedded_count: int = 0
    superseded_version: str | None = None
    requires_review: bool = False
    issues: list[IngestIssue] = Field(default_factory=list)


class UploadResponse(BaseModel):
    uploaded: int
    accepted: int
    rejected: int
    requires_review: int
    results: list[UploadResult]


# ══════════════════════════════════════════════════════════════
# documents and versions
# ══════════════════════════════════════════════════════════════
class DocumentVersionSummary(APIModel):
    id: uuid.UUID
    doc_ref: str
    version: str
    title: str | None = None
    status: str
    file_format: str
    file_name: str
    file_size_bytes: int | None = None
    effective_date: date | None = None
    expiry_date: date | None = None
    page_count: int | None = None
    section_count: int | None = None
    chunk_count: int | None = None
    parse_status: str
    metadata_complete: bool
    activated_at: datetime | None = None
    superseded_at: datetime | None = None
    created_at: datetime


class DepartmentRef(APIModel):
    id: uuid.UUID
    code: str
    name: str


class DocumentSummary(APIModel):
    id: uuid.UUID
    family_key: str
    title: str
    doc_type: str
    department: DepartmentRef | None = None
    created_at: datetime
    active_version: DocumentVersionSummary | None = None
    version_count: int = 0


class DocumentDetail(DocumentSummary):
    versions: list[DocumentVersionSummary] = Field(default_factory=list)


class SectionOut(APIModel):
    id: uuid.UUID
    section_ref: str
    heading: str | None = None
    level: int
    page_no: int | None = None
    paragraph_index: int | None = None
    ordinal: int
    text: str


class DocumentVersionDetail(DocumentVersionSummary):
    metadata_json: dict[str, Any] | None = None
    parse_error: str | None = None
    sections: list[SectionOut] = Field(default_factory=list)
    validation_issues: list[ValidationIssueOut] = Field(default_factory=list)


# ══════════════════════════════════════════════════════════════
# retrieval
# ══════════════════════════════════════════════════════════════
class Citation(BaseModel):
    """
    The canonical citation shape.

    Reused verbatim on generated responses and on ``complaint_policy_refs`` so
    a reference means the same thing everywhere in the system.
    """

    chunk_key: str
    doc_ref: str
    version: str
    section_ref: str | None = None
    heading: str | None = None
    page_no: int | None = None
    paragraph_index: int | None = None


class RetrievedChunkOut(BaseModel):
    chunk_key: str
    text: str
    doc_ref: str
    doc_version: str
    section_ref: str | None = None
    heading: str | None = None
    page_no: int | None = None
    paragraph_index: int | None = None
    score: float
    matched_by: str
    lexical_rank: int | None = None
    semantic_rank: int | None = None
    exact_rank: int | None = None


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    top_k: int = Field(8, ge=1, le=50)
    include_superseded: bool = False
    doc_refs: list[str] | None = None
    semantic: bool = True


class SearchResponse(BaseModel):
    query: str
    results: list[RetrievedChunkOut]
    lexical_count: int
    semantic_count: int
    exact_count: int
    semantic_available: bool
    knowledge_base_empty: bool
    cited_documents: list[str]


class TraceabilityResponse(BaseModel):
    """
    Answer to "where did this statement come from?" — the Source-Traceability
    Challenge in a single call.
    """

    resolved: bool
    citation: Citation | None = None
    document_title: str | None = None
    document_status: str | None = None
    applicability: str | None = None
    effective_date: date | None = None
    expiry_date: date | None = None
    text: str | None = None
    section_text: str | None = None
    reason: str | None = None


class CoverageResponse(BaseModel):
    active_documents: int
    chunks: int
    embedded_chunks: int
    unembedded_chunks: int
    knowledge_base_version: str
    semantic_search_available: bool


class AffectedComplaintOut(BaseModel):
    """One complaint that rested on a version that no longer governs."""

    public_ref: str
    status: str
    doc_ref: str
    section_ref: str | None = None
    cited_version: str | None = None
    analyzed_at: str | None = None


class PolicyImpactOut(BaseModel):
    """
    What activating a new version invalidated (SRS 1.8 #4).

    The question an administrator asks the moment they press the button. Every
    complaint listed was decided from text that no longer governs; most will be
    unaffected and some will not, and nobody can tell which without looking.

    ``affected_open`` is split out because it is the half worth a person's
    time: a closed complaint decided under the old policy is history, an open
    one is a decision somebody is still about to act on.
    """

    doc_ref: str = ""
    superseded_version: str | None = None
    active_version: str | None = None
    affected_total: int = 0
    affected_open: int = 0
    complaints: list[AffectedComplaintOut] = Field(default_factory=list)


class ActivationResponse(BaseModel):
    document_version_id: uuid.UUID
    doc_ref: str
    version: str
    status: str
    superseded_version: str | None = None
    message: str
    # Nothing is re-analysed automatically: re-running hundreds of complaints
    # on a policy change would spend the free-tier quota in one click, and
    # silently rewriting a decision an agent has already acted on is worse
    # than leaving it visibly stale. This is a work queue for a person.
    impact: PolicyImpactOut | None = None
