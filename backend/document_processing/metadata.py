"""
Metadata extraction from document text, with graceful degradation.

Our own corpus writes a front-matter block:

    Document ID: DEL-POL-04
    Title: Delivery and Shipment Policy
    Version: 2.1
    Effective Date: 2026-04-01
    Department: Logistics
    Category: POLICY

The hidden evaluation pack will not follow that convention.  SRS 1.8 #3 says
the application must process unseen documents "without modifying the core
source code", so this module never assumes the block exists:

  1. read whatever labelled fields are present,
  2. fall back to the filename for the document reference and version,
  3. fall back to the first heading for the title,
  4. report what is still missing so the caller can park the version in
     METADATA_REVIEW rather than reject the file.

A document that arrives with no metadata at all is still parsed, chunked and
retrievable — only its traceability score is reduced, and an administrator can
complete the fields in the UI.
"""

from __future__ import annotations

import re
from datetime import date, datetime

from document_processing.contracts import DocumentMetadata

# ── labelled field patterns ──────────────────────────────────────────
# Tolerant of ':' or '-' separators, extra spacing, and British/US spellings.
_LABEL_PATTERNS: dict[str, list[str]] = {
    "doc_ref": [
        r"document\s*(?:id|ref(?:erence)?|no\.?|number)",
        r"doc\s*(?:id|ref)",
        r"policy\s*(?:id|ref(?:erence)?|number)",
        r"sop\s*(?:id|ref(?:erence)?|number)",
        r"reference\s*(?:id|code)",
    ],
    "title": [r"title", r"document\s*(?:title|name)", r"policy\s*(?:title|name)"],
    "version": [r"version", r"revision", r"ver\.?", r"rev\.?"],
    "doc_type": [r"document\s*type", r"type", r"classification"],
    "department": [r"department", r"owning\s*department", r"business\s*unit", r"function"],
    "category": [r"category", r"document\s*category"],
    "effective_date": [
        r"effective\s*(?:date|from)", r"date\s*effective",
        r"issue\s*date", r"published\s*(?:date|on)", r"approved\s*on",
    ],
    "expiry_date": [
        r"expiry\s*date", r"expires?\s*(?:on|date)?", r"valid\s*until",
        r"review\s*(?:date|by)", r"next\s*review",
    ],
    "owner": [r"owner", r"document\s*owner", r"approved\s*by", r"author"],
    # A document's own word on where it stands: "Status: DRAFT". Its dates
    # cannot say this -- a draft whose effective date has passed is still a
    # draft until somebody approves it.
    "status": [
        r"(?:document|policy|lifecycle|approval)\s*status", r"status",
    ],
}

_SEPARATOR = r"\s*[:\-–]\s*"
_VALUE = r"(?P<value>[^\n\r]{1,200})"

_COMPILED: dict[str, list[re.Pattern[str]]] = {
    field: [
        re.compile(rf"^\s*{label}{_SEPARATOR}{_VALUE}$", re.IGNORECASE | re.MULTILINE)
        for label in labels
    ]
    for field, labels in _LABEL_PATTERNS.items()
}

# ── date parsing ─────────────────────────────────────────────────────
_DATE_FORMATS = (
    "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d",
    "%d %B %Y", "%d %b %Y", "%B %d, %Y", "%b %d, %Y",
    "%d.%m.%Y", "%Y.%m.%d",
)
_ORDINAL_SUFFIX = re.compile(r"(\d{1,2})(st|nd|rd|th)\b", re.IGNORECASE)

# ── filename fallbacks ───────────────────────────────────────────────
# DEL-POL-04_v2.1.pdf / ESC-SOP-02-v1.3.docx / REFUND_POLICY_v3.pdf
_FILENAME_REF = re.compile(r"^([A-Z][A-Z0-9]{1,8}(?:-[A-Z0-9]{1,8}){1,3})", re.IGNORECASE)
_FILENAME_VERSION = re.compile(r"[_\-\s]v(?:er)?[._\-]?(\d+(?:\.\d+)*)", re.IGNORECASE)

# ── document-type inference ──────────────────────────────────────────
_TYPE_HINTS: tuple[tuple[str, str], ...] = (
    ("ESCALATION", "ESCALATION"),
    ("ROUTING", "ROUTING_RULES"),
    ("SLA", "SLA"),
    ("SERVICE LEVEL", "SLA"),
    ("FAQ", "FAQ"),
    ("FREQUENTLY ASKED", "FAQ"),
    ("SOP", "SOP"),
    ("STANDARD OPERATING", "SOP"),
    ("COMPLIANCE", "COMPLIANCE"),
    ("HANDBOOK", "HANDBOOK"),
    ("PROCESS", "PROCESS"),
    ("PROCEDURE", "PROCESS"),
    ("POLICY", "POLICY"),
)


def parse_date(value: str | None) -> date | None:
    """Parse a human-written date. Returns None rather than raising."""
    if not value:
        return None
    cleaned = _ORDINAL_SUFFIX.sub(r"\1", value.strip().strip(".,;"))
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    # Last resort: a bare ISO-like date anywhere in the string.
    match = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", cleaned)
    if match:
        try:
            return date(int(match[1]), int(match[2]), int(match[3]))
        except ValueError:
            return None
    return None


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip().strip("|").strip()
    # Strip a trailing table pipe or repeated whitespace from PDF extraction.
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return cleaned or None


def _first_match(text: str, field: str) -> str | None:
    for pattern in _COMPILED[field]:
        match = pattern.search(text)
        if match:
            value = _clean(match.group("value"))
            if value:
                return value
    return None


def infer_doc_type(*candidates: str | None) -> str | None:
    """Guess POLICY / SOP / FAQ / ... from a title or filename."""
    haystack = " ".join(c for c in candidates if c).upper()
    for needle, doc_type in _TYPE_HINTS:
        if needle in haystack:
            return doc_type
    return None


def derive_from_filename(file_name: str) -> tuple[str | None, str | None]:
    """Return ``(doc_ref, version)`` inferred from the filename."""
    stem = re.sub(r"\.(pdf|docx|txt|md|csv)$", "", file_name, flags=re.IGNORECASE)
    ref_match = _FILENAME_REF.match(stem)
    doc_ref = ref_match.group(1).upper() if ref_match else None
    version_match = _FILENAME_VERSION.search(stem)
    version = version_match.group(1) if version_match else None
    return doc_ref, version


def extract_metadata(
    text: str,
    *,
    file_name: str,
    first_heading: str | None = None,
    scan_chars: int = 4000,
) -> DocumentMetadata:
    """
    Pull metadata out of document text.

    Only the first ``scan_chars`` are scanned for labelled fields: a front
    matter block lives at the top, and scanning the whole body would match
    phrases like "effective date" inside ordinary prose.
    """
    head = text[:scan_chars]

    meta = DocumentMetadata()
    for field_name in _LABEL_PATTERNS:
        value = _first_match(head, field_name)
        if value:
            meta.raw[field_name] = value

    meta.doc_ref = meta.raw.get("doc_ref")
    meta.title = meta.raw.get("title")
    meta.version = meta.raw.get("version")
    meta.doc_type = meta.raw.get("doc_type")
    meta.department = meta.raw.get("department")
    meta.category = meta.raw.get("category")
    meta.owner = meta.raw.get("owner")
    meta.status = meta.raw.get("status")
    meta.effective_date = parse_date(meta.raw.get("effective_date"))
    meta.expiry_date = parse_date(meta.raw.get("expiry_date"))

    # ── fallbacks, in descending order of trustworthiness ──
    file_ref, file_version = derive_from_filename(file_name)
    if not meta.doc_ref:
        meta.doc_ref = file_ref
    if not meta.version:
        meta.version = file_version
    if not meta.title:
        meta.title = first_heading or _pretty_filename(file_name)
    if not meta.doc_type:
        meta.doc_type = infer_doc_type(meta.title, meta.category, file_name)

    # Normalise a version written as "v2.1" or "Rev 3".
    if meta.version:
        version_match = re.search(r"(\d+(?:\.\d+)*)", meta.version)
        meta.version = version_match.group(1) if version_match else meta.version.strip()

    if meta.doc_ref:
        meta.doc_ref = meta.doc_ref.strip().upper()

    return meta


def _pretty_filename(file_name: str) -> str:
    stem = re.sub(r"\.(pdf|docx|txt|md|csv)$", "", file_name, flags=re.IGNORECASE)
    return re.sub(r"[_\-]+", " ", stem).strip().title()


def family_key_for(doc_ref: str | None, title: str | None, file_name: str) -> str:
    """
    Group every version of the same document under one family.

    ``DEL-POL-04`` and ``DEL-POL-04`` v2 must land in the same family, so the
    trailing instance number is kept but the version is not part of the key.
    Without a reference we fall back to a slug of the title, which is stable
    across re-uploads of the same policy.
    """
    if doc_ref:
        return doc_ref.strip().upper()
    basis = title or _pretty_filename(file_name)
    slug = re.sub(r"[^A-Z0-9]+", "-", basis.upper()).strip("-")
    return slug[:64] or "UNIDENTIFIED-DOCUMENT"
