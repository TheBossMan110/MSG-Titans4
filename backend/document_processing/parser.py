"""
Format dispatcher — the single entry point for turning bytes into a
``ParsedDocument``.

Callers never choose a parser.  They hand over bytes and a filename, and the
format is decided by magic bytes in :mod:`document_processing.validation`.
That is what lets the hidden evaluation pack arrive as "a mixture of PDF and
DOCX files" (SRS 1.2) and be processed with no code change.
"""

from __future__ import annotations

import csv
import io

from document_processing.contracts import ParsedDocument
from document_processing.docx_parser import parse_docx
from document_processing.metadata import extract_metadata
from document_processing.pdf_parser import parse_pdf
from document_processing.sections import build_sections_from_lines
from src.core.logging import get_logger
from src.db.enums import FileFormat, ValidationIssueCode

log = get_logger("document_processing.parser")


def parse_document(data: bytes, *, file_name: str, file_format: FileFormat) -> ParsedDocument:
    """Parse bytes using the parser for ``file_format``. Never raises."""
    if file_format == FileFormat.PDF:
        return parse_pdf(data, file_name=file_name)
    if file_format == FileFormat.DOCX:
        return parse_docx(data, file_name=file_name)
    if file_format in (FileFormat.TXT, FileFormat.MD):
        return _parse_text(data, file_name=file_name, file_format=file_format)
    if file_format == FileFormat.CSV:
        return _parse_csv(data, file_name=file_name)

    document = ParsedDocument(
        file_name=file_name,
        file_format=file_format,
        metadata=extract_metadata("", file_name=file_name),
        sections=[],
    )
    document.add_issue(
        ValidationIssueCode.UNSUPPORTED_FILE_TYPE,
        f"No parser is registered for {file_format}.",
        fatal=True,
    )
    return document


def _decode(data: bytes) -> str:
    """Decode text tolerantly — a stray byte must not lose a whole document."""
    for encoding in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _parse_text(data: bytes, *, file_name: str, file_format: FileFormat) -> ParsedDocument:
    """TXT / Markdown. Optional formats (SRS Step 3), handled for completeness."""
    text = _decode(data)
    document = ParsedDocument(
        file_name=file_name,
        file_format=file_format,
        metadata=extract_metadata("", file_name=file_name),
        sections=[],
        raw_text=text,
    )

    if not text.strip():
        document.add_issue(
            ValidationIssueCode.EMPTY_FILE, "The file contains no text.", fatal=True
        )
        return document

    lines: list[tuple[str, None, int]] = []
    for index, line in enumerate(text.splitlines(), start=1):
        stripped = line.rstrip()
        if file_format == FileFormat.MD and stripped.startswith("#"):
            # Re-shape a Markdown heading so the shared builder recognises it.
            level = len(stripped) - len(stripped.lstrip("#"))
            stripped = f"{'#' * level} {stripped.lstrip('#').strip()}"
        lines.append((stripped, None, index))

    document.paragraph_count = len(lines)
    document.sections = build_sections_from_lines(lines)
    for section in document.sections:
        if section.heading and section.heading.startswith("#"):
            section.level = len(section.heading) - len(section.heading.lstrip("#"))
            section.heading = section.heading.lstrip("#").strip()

    first_heading = next(
        (s.heading for s in document.sections if s.heading and s.heading != "Preamble"), None
    )
    document.metadata = extract_metadata(text, file_name=file_name, first_heading=first_heading)
    return document


def _parse_csv(data: bytes, *, file_name: str) -> ParsedDocument:
    """
    CSV. Each row becomes a pipe-delimited line under a single section, so a
    routing-rule or SLA sheet stays searchable and citable by row.
    """
    text = _decode(data)
    document = ParsedDocument(
        file_name=file_name,
        file_format=FileFormat.CSV,
        metadata=extract_metadata("", file_name=file_name),
        sections=[],
        raw_text=text,
    )

    try:
        reader = csv.reader(io.StringIO(text))
        rows = [row for row in reader if any(cell.strip() for cell in row)]
    except csv.Error as exc:
        document.add_issue(
            ValidationIssueCode.PARSE_FAILED,
            "The CSV file could not be read.",
            detail=str(exc),
            fatal=True,
        )
        return document

    if not rows:
        document.add_issue(
            ValidationIssueCode.EMPTY_FILE, "The CSV file contains no rows.", fatal=True
        )
        return document

    header, *body = rows
    lines: list[tuple[str, None, int]] = [(" | ".join(header), None, 1)]
    lines.extend(
        (" | ".join(cell.strip() for cell in row), None, index)
        for index, row in enumerate(body, start=2)
    )

    document.paragraph_count = len(lines)
    document.sections = build_sections_from_lines(lines)
    document.metadata = extract_metadata(text, file_name=file_name)
    return document
