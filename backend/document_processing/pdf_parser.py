"""
PDF parsing (SRS Step 3 and 5 — PDF is a mandatory format).

Page numbers are the whole point.  A policy citation that cannot say *which
page* fails the Source-Traceability Challenge, so every line carries the page
it came from and that page number follows the text all the way into the chunk
row and out into the citation shown next to a generated sentence.

pdfplumber is the primary extractor because it preserves layout well enough for
heading detection.  pypdf is the fallback for files pdfplumber chokes on.  A
scanned PDF with no text layer is *not* an error: it is reported as
NO_TEXT_LAYER so the upload is recorded and routed for review rather than
silently producing an empty knowledge base.
"""

from __future__ import annotations

import io
import re

from document_processing.contracts import ParsedDocument, ParsedSection
from document_processing.metadata import extract_metadata
from document_processing.sections import build_sections_from_lines
from src.core.logging import get_logger
from src.db.enums import FileFormat, ValidationIssueCode

log = get_logger("document_processing.pdf")

# Running headers/footers repeat on most pages; they pollute section text and
# would otherwise be indexed as if they were policy content.
_PAGE_NOISE = re.compile(
    r"^\s*(page\s+\d+(\s+of\s+\d+)?|\d+\s*\|\s*page|-\s*\d+\s*-)\s*$",
    re.IGNORECASE,
)
# Hyphen-split words across a line break: "deliv-\nery" -> "delivery"
_HYPHEN_BREAK = re.compile(r"(\w)-\s*\n\s*(\w)")


def _clean_line(line: str) -> str:
    return re.sub(r"[ \t]{2,}", " ", line.rstrip())


def _extract_with_pdfplumber(data: bytes) -> tuple[list[tuple[str, int, None]], int, str]:
    import pdfplumber

    lines: list[tuple[str, int, None]] = []
    raw_parts: list[str] = []

    with pdfplumber.open(io.BytesIO(data)) as pdf:
        page_count = len(pdf.pages)
        for page_number, page in enumerate(pdf.pages, start=1):
            text = page.extract_text(x_tolerance=1.5, y_tolerance=2.5) or ""
            if not text.strip():
                continue
            text = _HYPHEN_BREAK.sub(r"\1\2", text)
            raw_parts.append(text)
            for line in text.splitlines():
                cleaned = _clean_line(line)
                if cleaned and not _PAGE_NOISE.match(cleaned):
                    lines.append((cleaned, page_number, None))

    return lines, page_count, "\n".join(raw_parts)


def _extract_with_pypdf(data: bytes) -> tuple[list[tuple[str, int, None]], int, str]:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    lines: list[tuple[str, int, None]] = []
    raw_parts: list[str] = []

    for page_number, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        if not text.strip():
            continue
        text = _HYPHEN_BREAK.sub(r"\1\2", text)
        raw_parts.append(text)
        for line in text.splitlines():
            cleaned = _clean_line(line)
            if cleaned and not _PAGE_NOISE.match(cleaned):
                lines.append((cleaned, page_number, None))

    return lines, len(reader.pages), "\n".join(raw_parts)


def parse_pdf(data: bytes, *, file_name: str) -> ParsedDocument:
    """
    Parse a PDF into sections.  Never raises: problems come back as issues.
    """
    document = ParsedDocument(
        file_name=file_name,
        file_format=FileFormat.PDF,
        metadata=extract_metadata("", file_name=file_name),
        sections=[],
    )

    lines: list[tuple[str, int, None]] = []
    page_count = 0
    raw_text = ""

    try:
        lines, page_count, raw_text = _extract_with_pdfplumber(data)
    except Exception as exc:
        log.warning("pdfplumber_failed", file=file_name, error=str(exc))
        document.add_issue(
            ValidationIssueCode.PARSE_FAILED,
            "Primary PDF extractor failed; retrying with the fallback reader.",
            detail=f"{type(exc).__name__}: {exc}",
        )
        try:
            lines, page_count, raw_text = _extract_with_pypdf(data)
        except Exception as fallback_exc:
            log.error("pdf_parse_failed", file=file_name, error=str(fallback_exc))
            document.add_issue(
                ValidationIssueCode.PARSE_FAILED,
                "The PDF could not be read by either extractor.",
                detail=f"{type(fallback_exc).__name__}: {fallback_exc}",
                fatal=True,
            )
            return document

    document.page_count = page_count
    document.raw_text = raw_text

    if not raw_text.strip():
        # Almost always a scanned document. Recorded, not rejected: an
        # administrator can supply a text version or accept reduced coverage.
        document.add_issue(
            ValidationIssueCode.NO_TEXT_LAYER,
            "No extractable text found. The PDF is most likely a scan; "
            "OCR is out of scope, so this version cannot be indexed.",
            fatal=True,
        )
        return document

    document.sections = build_sections_from_lines(lines)
    first_heading = _first_real_heading(document.sections)
    document.metadata = extract_metadata(
        raw_text, file_name=file_name, first_heading=first_heading
    )

    if not document.sections:
        document.add_issue(
            ValidationIssueCode.PARSE_FAILED,
            "Text was extracted but no sections could be identified.",
        )

    log.info(
        "pdf_parsed",
        file=file_name,
        pages=page_count,
        sections=len(document.sections),
        chars=len(raw_text),
    )
    return document


def _first_real_heading(sections: list[ParsedSection]) -> str | None:
    for section in sections:
        if section.heading and section.heading != "Preamble":
            return section.heading
    return None
