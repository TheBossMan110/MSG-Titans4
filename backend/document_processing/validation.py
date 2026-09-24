"""
Document validation — FR vii, SRS Step 4.

The SRS lists exactly what must be checked:

    file type · file size · empty files · duplicate documents ·
    document ID · version · effective date · expiry date · document category

Every check returns a finding rather than raising, and the caller persists all
of them to ``document_validation_issues``.  A rejected upload that leaves no
trace is indistinguishable from a check nobody wrote, so the evidence is the
point as much as the enforcement.

File type is decided by **magic bytes, not the file extension**.  A `.pdf`
extension on a ZIP payload is the oldest upload trick there is, and trusting
the extension would let it through to the parser.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

import filetype

from document_processing.contracts import ParseIssue
from src.core.config import settings
from src.db.enums import FileFormat, IssueOutcome, Severity, ValidationIssueCode

# Mandatory formats (SRS Step 3). TXT/MD/CSV are accepted as an optional extra.
SUPPORTED_FORMATS: dict[str, FileFormat] = {
    ".pdf": FileFormat.PDF,
    ".docx": FileFormat.DOCX,
    ".txt": FileFormat.TXT,
    ".md": FileFormat.MD,
    ".csv": FileFormat.CSV,
}
MANDATORY_FORMATS = {FileFormat.PDF, FileFormat.DOCX}

# Magic-byte signatures we accept for each declared format.
_MAGIC_MIME: dict[FileFormat, set[str]] = {
    FileFormat.PDF: {"application/pdf"},
    FileFormat.DOCX: {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/zip",  # DOCX is a ZIP container; refined by the OOXML check
    },
}

_DOCX_OOXML_MARKER = b"word/"
_PDF_MARKER = b"%PDF-"
MIN_FILE_BYTES = 32


@dataclass(slots=True)
class FileValidationResult:
    """Outcome of validating raw bytes before any parsing is attempted."""

    file_name: str
    file_hash: str
    size_bytes: int
    file_format: FileFormat | None = None
    issues: list[ParseIssue] = field(default_factory=list)

    @property
    def is_rejected(self) -> bool:
        return any(issue.fatal for issue in self.issues)

    @property
    def outcome(self) -> IssueOutcome:
        """
        How the upload was handled overall.

        Only meaningful when ``issues`` is non-empty — a clean file produces no
        ``document_validation_issues`` row at all.
        """
        return IssueOutcome.REJECTED if self.is_rejected else IssueOutcome.ACCEPTED_WITH_WARNING

    def add(
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


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_filename(file_name: str) -> str:
    """
    Strip any path component and dangerous characters.

    Defends against '../../etc/passwd' and against a filename that would escape
    the storage directory once joined to a path.
    """
    name = re.split(r"[\\/]", file_name or "")[-1]
    name = re.sub(r"[^A-Za-z0-9._\- ]+", "_", name).strip(" .")
    return name[:255] or "unnamed"


def detect_format(data: bytes, file_name: str) -> tuple[FileFormat | None, str | None]:
    """
    Decide the real format from content, cross-checked against the extension.

    Returns ``(format, mismatch_detail)``.  ``mismatch_detail`` is set when the
    extension claims something the bytes do not support.
    """
    suffix = ""
    if "." in file_name:
        suffix = "." + file_name.rsplit(".", 1)[-1].lower()
    claimed = SUPPORTED_FORMATS.get(suffix)

    # Content sniffing first.
    if data.startswith(_PDF_MARKER):
        actual = FileFormat.PDF
    elif data[:4] == b"PK\x03\x04" and _DOCX_OOXML_MARKER in data[:8192]:
        actual = FileFormat.DOCX
    else:
        kind = filetype.guess(data)
        mime = kind.mime if kind else None
        actual = None
        if mime:
            for fmt, mimes in _MAGIC_MIME.items():
                if mime in mimes:
                    actual = fmt
                    break
        if actual is None and claimed in {FileFormat.TXT, FileFormat.MD, FileFormat.CSV}:
            # Plain-text formats have no magic bytes; accept if it decodes.
            try:
                data[:4096].decode("utf-8")
                actual = claimed
            except UnicodeDecodeError:
                actual = None

    if actual is None:
        return None, f"extension={suffix or 'none'} content=unrecognised"
    if claimed and claimed != actual:
        return actual, f"extension claims {claimed.value}, content is {actual.value}"
    return actual, None


def validate_file(
    data: bytes,
    file_name: str,
    *,
    existing_hashes: set[str] | None = None,
) -> FileValidationResult:
    """
    Run every Step 4 check that can be answered from the bytes alone.

    Metadata checks (document ID, version, effective/expiry date, category)
    run after parsing, in :func:`validate_metadata`.
    """
    clean_name = safe_filename(file_name)
    result = FileValidationResult(
        file_name=clean_name,
        file_hash=sha256_bytes(data),
        size_bytes=len(data),
    )

    # ── empty file ──
    if len(data) < MIN_FILE_BYTES:
        result.add(
            ValidationIssueCode.EMPTY_FILE,
            "The uploaded file is empty or too small to contain a document.",
            field_name="file",
            detail=f"{len(data)} bytes",
            fatal=True,
        )
        return result

    # ── file size ──
    if len(data) > settings.max_upload_bytes:
        result.add(
            ValidationIssueCode.FILE_TOO_LARGE,
            f"The file exceeds the {settings.max_upload_mb} MB upload limit.",
            field_name="file",
            detail=f"{len(data) / 1_048_576:.1f} MB",
            fatal=True,
        )
        return result

    # ── file type (magic bytes, not the extension) ──
    file_format, mismatch = detect_format(data, clean_name)
    if file_format is None:
        result.add(
            ValidationIssueCode.UNSUPPORTED_FILE_TYPE,
            "Unsupported file type. PDF and DOCX are required; "
            "TXT, Markdown and CSV are accepted as optional extras.",
            field_name="file",
            detail=mismatch,
            fatal=True,
        )
        return result

    result.file_format = file_format
    if mismatch:
        result.add(
            ValidationIssueCode.UNSUPPORTED_FILE_TYPE,
            "The file extension does not match the actual file content. "
            "The content was trusted and the extension ignored.",
            field_name="file",
            detail=mismatch,
        )

    # ── duplicate document ──
    if existing_hashes and result.file_hash in existing_hashes:
        result.add(
            ValidationIssueCode.DUPLICATE_DOCUMENT,
            "This exact file has already been uploaded.",
            field_name="file_hash",
            detail=result.file_hash[:16],
            fatal=True,
        )

    return result


def validate_metadata(metadata, *, file_name: str) -> list[ParseIssue]:
    """
    Post-parse metadata checks (Step 4, second half).

    None of these are fatal.  A hidden-pack document with no metadata block
    must still be ingested — it lands in METADATA_REVIEW with reduced
    traceability instead of being turned away.
    """
    issues: list[ParseIssue] = []

    if not metadata.doc_ref:
        issues.append(
            ParseIssue(
                code=ValidationIssueCode.MISSING_DOCUMENT_ID,
                message="No document ID found in the file or inferable from its name. "
                "A provisional reference has been assigned for review.",
                field="doc_ref",
            )
        )
    if not metadata.version:
        issues.append(
            ParseIssue(
                code=ValidationIssueCode.MISSING_VERSION,
                message="No version found. Defaulted to 1.0 pending review.",
                field="version",
            )
        )
    if not metadata.effective_date:
        issues.append(
            ParseIssue(
                code=ValidationIssueCode.MISSING_EFFECTIVE_DATE,
                message="No effective date found. Policy precedence by date "
                "cannot be applied to this version until one is supplied.",
                field="effective_date",
            )
        )
    if not metadata.category and not metadata.doc_type:
        issues.append(
            ParseIssue(
                code=ValidationIssueCode.MISSING_CATEGORY,
                message="No document category or type found; it will be treated as OTHER.",
                field="category",
            )
        )

    if (
        metadata.expiry_date
        and metadata.effective_date
        and metadata.expiry_date < metadata.effective_date
    ):
        issues.append(
            ParseIssue(
                code=ValidationIssueCode.EXPIRED_DOCUMENT,
                message="The expiry date precedes the effective date.",
                field="expiry_date",
                detail=f"{metadata.effective_date} -> {metadata.expiry_date}",
            )
        )

    if issues:
        issues.append(
            ParseIssue(
                code=ValidationIssueCode.METADATA_INCOMPLETE,
                message="Metadata is incomplete; this version requires review "
                "before it can be activated.",
                field="metadata",
                detail=f"missing: {', '.join(metadata.missing_fields) or 'none'}",
            )
        )
    return issues


def severity_for(code: ValidationIssueCode) -> Severity:
    """Map an issue code to the severity stored on the row."""
    critical = {
        ValidationIssueCode.UNSUPPORTED_FILE_TYPE,
        ValidationIssueCode.FILE_TOO_LARGE,
        ValidationIssueCode.EMPTY_FILE,
        ValidationIssueCode.PARSE_FAILED,
    }
    high = {
        ValidationIssueCode.DUPLICATE_DOCUMENT,
        ValidationIssueCode.NO_TEXT_LAYER,
        ValidationIssueCode.EXPIRED_DOCUMENT,
        ValidationIssueCode.MISSING_DOCUMENT_ID,
    }
    if code in critical:
        return Severity.CRITICAL
    if code in high:
        return Severity.HIGH
    return Severity.MEDIUM
