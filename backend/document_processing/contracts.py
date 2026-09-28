"""
The contract every parser produces.

PDF and DOCX are both mandatory formats (SRS Step 3) and they expose *different*
location information: a PDF knows page numbers, a DOCX knows paragraph indices.
Rather than flatten that away, both are carried through the whole pipeline so a
citation can answer the Source-Traceability Challenge precisely:

    DEL-POL-04 v2.1, section 5.2, page 7            (PDF)
    ESC-SOP-02 v1.3, section 3.1, paragraph 41      (DOCX)

Parsers do exactly one job: turn bytes into ``ParsedDocument``.  They never
touch the database, never call a model, and never raise on malformed input —
they return the problems they found so the caller can record them
(``document_validation_issues``) and degrade instead of crashing.  That is what
makes an unrecognised hidden-pack document survivable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from src.db.enums import FileFormat, ValidationIssueCode


@dataclass(slots=True)
class ParseIssue:
    """A problem found while reading a file. Never raised, always returned."""

    code: ValidationIssueCode
    message: str
    field: str | None = None
    detail: str | None = None
    fatal: bool = False


@dataclass(slots=True)
class DocumentMetadata:
    """
    Metadata declared inside the document itself.

    Our own corpus carries a front-matter block.  The hidden evaluation pack
    will not, so every field is optional and ``is_complete`` drives whether the
    version lands ACTIVE or in METADATA_REVIEW.
    """

    doc_ref: str | None = None
    title: str | None = None
    version: str | None = None
    doc_type: str | None = None
    department: str | None = None
    category: str | None = None
    effective_date: date | None = None
    expiry_date: date | None = None
    owner: str | None = None
    # The lifecycle the document declares for itself ("Status: DRAFT"), as
    # written. Optional like everything else; see versioning.initial_status.
    status: str | None = None
    raw: dict[str, str] = field(default_factory=dict)

    # Fields that must be present for a version to be publishable as-is.
    REQUIRED = ("doc_ref", "version", "effective_date")

    @property
    def is_complete(self) -> bool:
        return all(getattr(self, name) for name in self.REQUIRED)

    @property
    def missing_fields(self) -> list[str]:
        return [name for name in self.REQUIRED if not getattr(self, name)]

    def as_dict(self) -> dict[str, Any]:
        return {
            "doc_ref": self.doc_ref,
            "title": self.title,
            "version": self.version,
            "doc_type": self.doc_type,
            "department": self.department,
            "category": self.category,
            "effective_date": self.effective_date.isoformat() if self.effective_date else None,
            "expiry_date": self.expiry_date.isoformat() if self.expiry_date else None,
            "owner": self.owner,
            "status": self.status,
            "raw": self.raw,
        }


@dataclass(slots=True)
class ParsedSection:
    """
    One addressable section of a document.

    ``section_ref`` is the human-facing address a policy citation uses ("5.2").
    When the source document numbers its own headings we keep that numbering;
    otherwise we synthesise a stable one so every section is still citable.
    """

    section_ref: str
    heading: str | None
    level: int
    text: str
    ordinal: int
    page_no: int | None = None
    paragraph_index: int | None = None
    numbered_in_source: bool = True

    @property
    def is_empty(self) -> bool:
        return not self.text.strip()

    def __len__(self) -> int:
        return len(self.text)


@dataclass(slots=True)
class ParsedDocument:
    """Everything a parser could learn about one file."""

    file_name: str
    file_format: FileFormat
    metadata: DocumentMetadata
    sections: list[ParsedSection]
    page_count: int | None = None
    paragraph_count: int | None = None
    raw_text: str = ""
    issues: list[ParseIssue] = field(default_factory=list)

    @property
    def has_text(self) -> bool:
        return bool(self.raw_text.strip())

    @property
    def is_fatal(self) -> bool:
        return any(issue.fatal for issue in self.issues)

    @property
    def section_count(self) -> int:
        return len(self.sections)

    @property
    def char_count(self) -> int:
        return len(self.raw_text)

    def add_issue(
        self,
        code: ValidationIssueCode,
        message: str,
        *,
        field_name: str | None = None,
        detail: str | None = None,
        fatal: bool = False,
    ) -> None:
        self.issues.append(
            ParseIssue(code=code, message=message, field=field_name, detail=detail, fatal=fatal)
        )


@dataclass(slots=True)
class ChunkCandidate:
    """
    A retrieval unit, before it becomes a database row.

    Chunks never cross a section boundary.  A chunk that straddled two sections
    could not be cited honestly, and citation integrity is the whole point.
    """

    chunk_key: str
    text: str
    ordinal: int
    section_ref: str | None
    heading: str | None
    page_no: int | None
    paragraph_index: int | None
    token_count: int

    @property
    def is_empty(self) -> bool:
        return not self.text.strip()
