"""
The fourth way in: a complaint that arrives as a file (SRS workflow step 1,
"Uploaded Complaint").

A customer who already wrote a letter -- a PDF, a Word document, a text file --
uploads it instead of retyping it. The file is read with the same parsers the
knowledge base uses (format decided by the bytes, not the name), and turned
into a *draft*: a title, the text, and an order reference if one is written in
it. Nothing is filed here. The customer checks the draft in the ordinary form
and submits it with channel UPLOAD, so it goes through exactly the intake,
validation and both pipelines every other complaint does. The text is
untrusted like any complaint body; the pipelines scan it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from document_processing.parser import parse_document
from document_processing.validation import detect_format
from src.core.config import settings
from src.core.errors import ValidationError
from src.db.enums import FileFormat

ACCEPTED = {FileFormat.PDF, FileFormat.DOCX, FileFormat.TXT, FileFormat.MD}
TITLE_MAX = 120

_SUBJECT = re.compile(r"^\s*(?:subject|re|regarding|complaint)\s*[:\-]\s*(.+)$", re.IGNORECASE | re.MULTILINE)
_NOT_A_TITLE = re.compile(
    r"^\s*(?:dear\b|to\b|to:|from\b|from:|date\b|date:|sir\b|madam\b|hello\b|hi\b|respected\b|\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4})",
    re.IGNORECASE,
)
# Consignment and order numbers as the dataset and customers write them.
_ORDER_REF = re.compile(r"\b(?:CN|ORD|RX|TRK|AWB|ORDER)[-\s#]?\d{4,}\b", re.IGNORECASE)


@dataclass
class FileDraft:
    file_name: str
    file_format: str
    title: str
    description: str
    order_ref: str | None
    pages: int | None
    notes: list[str] = field(default_factory=list)


def read_complaint_file(data: bytes, file_name: str) -> FileDraft:
    """Bytes of an uploaded complaint -> a draft for the form. Raises ValidationError with a plain message."""
    if not data:
        raise ValidationError("The file is empty.")
    if len(data) > settings.max_upload_bytes:
        raise ValidationError(f"The file is larger than {settings.max_upload_mb} MB.")

    file_format, _ = detect_format(data, file_name)
    if file_format not in ACCEPTED:
        raise ValidationError("Upload the complaint as a PDF, a Word document (DOCX) or a text file.")

    document = parse_document(data, file_name=file_name, file_format=file_format)
    text = document.raw_text.strip() or "\n\n".join(
        "\n".join(part for part in (section.heading, section.text) if part) for section in document.sections
    ).strip()
    text = _tidy(text)
    if len(text.split()) < 5:
        raise ValidationError(
            "We couldn't read any text in this file. If it is a scanned photo, please type the complaint instead."
        )

    notes: list[str] = []
    limit = settings.max_complaint_length
    if len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0]
        notes.append(f"The file was long, so only the first {limit:,} characters were kept.")

    order = _ORDER_REF.search(text)
    return FileDraft(
        file_name=file_name,
        file_format=file_format.value,
        title=_title(text, file_name),
        description=text,
        order_ref=order.group(0).upper().replace(" ", "-") if order else None,
        pages=document.page_count,
        notes=notes,
    )


def _tidy(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _title(text: str, file_name: str) -> str:
    """A 'Subject:' line if the letter has one; else its first real sentence; else the file name."""
    subject = _SUBJECT.search(text)
    if subject and subject.group(1).strip():
        return _clip(subject.group(1))
    for line in text.split("\n"):
        line = line.strip()
        if len(line.split()) >= 3 and not _NOT_A_TITLE.match(line):
            return _clip(re.split(r"(?<=[.!?])\s", line, maxsplit=1)[0])
    stem = file_name.rsplit(".", 1)[0].replace("_", " ").replace("-", " ").strip()
    return _clip(stem or "Uploaded complaint")


def _clip(value: str) -> str:
    value = value.strip().rstrip(".")
    return value if len(value) <= TITLE_MAX else value[:TITLE_MAX].rsplit(" ", 1)[0] + "…"
