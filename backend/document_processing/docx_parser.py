"""
DOCX parsing (SRS Step 3 and 5 — DOCX is a mandatory format).

Where a PDF gives us page numbers, a DOCX gives us something better: real
structure.  Paragraph styles declare headings explicitly, so section detection
here is reading the document's own outline rather than guessing from layout.
The SRS asks for a "paragraph or section reference for DOCX documents", so the
paragraph index is carried through to the chunk row exactly as the page number
is for PDFs.

Tables matter in this corpus — routing rules, SLA targets and escalation
matrices are almost always tables — so table cells are flattened into pipe-
delimited rows and attached to the section they sit under, instead of being
dropped the way a naive paragraph-only reader would.

Two adversarial details are handled deliberately, because SRS 1.8 #8 says a
hidden document may carry an injection attempt:

* text in the document's headers and footers is read too, since that is a
  classic place to hide instructions a paragraph-only parser never sees;
* white-on-white / hidden-formatted runs are extracted like any other text and
  flagged, rather than silently skipped.  The injection scanner can only defend
  against text the parser actually surfaced.
"""

from __future__ import annotations

import io
import re

from document_processing.contracts import ParsedDocument, ParsedSection
from document_processing.metadata import extract_metadata
from document_processing.sections import build_sections_from_lines
from src.core.logging import get_logger
from src.db.enums import FileFormat, ValidationIssueCode

log = get_logger("document_processing.docx")

_HEADING_STYLE = re.compile(r"^heading\s*(\d)", re.IGNORECASE)
_TITLE_STYLE = re.compile(r"^(title|subtitle)$", re.IGNORECASE)


def _style_level(paragraph) -> int | None:
    """Return the outline level a paragraph's style declares, if any."""
    style_name = getattr(getattr(paragraph, "style", None), "name", "") or ""
    match = _HEADING_STYLE.match(style_name.strip())
    if match:
        return int(match.group(1))
    if _TITLE_STYLE.match(style_name.strip()):
        return 1
    return None


def _is_hidden(paragraph) -> bool:
    """True when every run in the paragraph is formatted as hidden text."""
    runs = getattr(paragraph, "runs", None) or []
    if not runs:
        return False
    for run in runs:
        vanish = getattr(getattr(run, "font", None), "hidden", None)
        if not vanish:
            return False
    return True


def _flatten_table(table) -> list[str]:
    """Render a table as pipe-delimited rows so its content stays searchable."""
    rows: list[str] = []
    for row in table.rows:
        # python-docx yields the SAME cell object once per grid column it spans,
        # so a horizontally merged cell appears repeatedly. Deduplicate by the
        # underlying XML element, never by cell text: two adjacent cells that
        # legitimately hold the same value ("14 days | 14 days") are distinct
        # data, and collapsing them silently drops a column.
        seen: set[int] = set()
        cells: list[str] = []
        for cell in row.cells:
            element_id = id(cell._tc)
            if element_id in seen:
                continue
            seen.add(element_id)
            cells.append(" ".join(cell.text.split()))
        line = " | ".join(c for c in cells if c)
        if line:
            rows.append(line)
    return rows


def _iter_block_items(document):
    """
    Yield paragraphs and tables in true document order.

    python-docx exposes ``.paragraphs`` and ``.tables`` as separate lists, which
    loses their interleaving - a table would end up attached to the wrong
    section.  Walking the body XML preserves the real order.
    """
    from docx.document import Document as DocxDocument
    from docx.oxml.ns import qn
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    parent = document.element.body if isinstance(document, DocxDocument) else document
    for child in parent.iterchildren():
        if child.tag == qn("w:p"):
            yield Paragraph(child, document)
        elif child.tag == qn("w:tbl"):
            yield Table(child, document)


def parse_docx(data: bytes, *, file_name: str) -> ParsedDocument:
    """Parse a DOCX into sections. Never raises: problems come back as issues."""
    document = ParsedDocument(
        file_name=file_name,
        file_format=FileFormat.DOCX,
        metadata=extract_metadata("", file_name=file_name),
        sections=[],
    )

    try:
        import docx
        from docx.table import Table
        from docx.text.paragraph import Paragraph

        docx_file = docx.Document(io.BytesIO(data))
    except Exception as exc:
        log.error("docx_parse_failed", file=file_name, error=str(exc))
        document.add_issue(
            ValidationIssueCode.PARSE_FAILED,
            "The DOCX file could not be opened.",
            detail=f"{type(exc).__name__}: {exc}",
            fatal=True,
        )
        return document

    lines: list[tuple[str, None, int]] = []
    raw_parts: list[str] = []
    paragraph_index = 0
    hidden_count = 0

    for block in _iter_block_items(docx_file):
        if isinstance(block, Paragraph):
            paragraph_index += 1
            text = " ".join(block.text.split())
            if not text:
                continue
            if _is_hidden(block):
                hidden_count += 1
            level = _style_level(block)
            if level is not None and not _looks_numbered(text):
                # Re-emit style-declared headings in a numbered shape so the
                # shared section builder treats them as headings.
                text = f"{'#' * level} {text}"
            lines.append((text, None, paragraph_index))
            raw_parts.append(text)

        elif isinstance(block, Table):
            for row_text in _flatten_table(block):
                paragraph_index += 1
                lines.append((row_text, None, paragraph_index))
                raw_parts.append(row_text)

    # Headers and footers - a favourite hiding place for injected instructions.
    header_footer_lines = _extract_headers_footers(docx_file)
    for text in header_footer_lines:
        paragraph_index += 1
        lines.append((text, None, paragraph_index))
        raw_parts.append(text)

    document.paragraph_count = paragraph_index
    document.raw_text = "\n".join(raw_parts)

    if not document.raw_text.strip():
        document.add_issue(
            ValidationIssueCode.EMPTY_FILE,
            "The DOCX file contains no readable text.",
            fatal=True,
        )
        return document

    if hidden_count:
        document.add_issue(
            ValidationIssueCode.METADATA_INCOMPLETE,
            f"{hidden_count} paragraph(s) use hidden text formatting. "
            "The content was extracted and will be scanned for injected "
            "instructions rather than ignored.",
            field_name="hidden_text",
        )

    document.sections = _rebuild_style_headings(build_sections_from_lines(lines))
    first_heading = next(
        (s.heading for s in document.sections if s.heading and s.heading != "Preamble"),
        None,
    )
    document.metadata = extract_metadata(
        document.raw_text, file_name=file_name, first_heading=first_heading
    )

    if not document.sections:
        document.add_issue(
            ValidationIssueCode.PARSE_FAILED,
            "Text was extracted but no sections could be identified.",
        )

    log.info(
        "docx_parsed",
        file=file_name,
        paragraphs=paragraph_index,
        sections=len(document.sections),
        chars=len(document.raw_text),
    )
    return document


_NUMBERED = re.compile(r"^\s*(?:\d+|[A-Z])(?:\.\d+){0,4}\.?\s+\S")


def _looks_numbered(text: str) -> bool:
    return bool(_NUMBERED.match(text))


def _rebuild_style_headings(sections: list[ParsedSection]) -> list[ParsedSection]:
    """Strip the temporary '#' markers used to signal style-declared headings."""
    for section in sections:
        if section.heading and section.heading.startswith("#"):
            stripped = section.heading.lstrip("#").strip()
            section.level = len(section.heading) - len(section.heading.lstrip("#"))
            section.heading = stripped
        if section.text.startswith("#"):
            section.text = re.sub(r"^#+\s*", "", section.text)
    return sections


def _extract_headers_footers(docx_file) -> list[str]:
    """Collect header and footer text from every section of the document."""
    collected: list[str] = []
    try:
        for section in docx_file.sections:
            for part in (section.header, section.footer):
                if part is None:
                    continue
                for paragraph in part.paragraphs:
                    text = " ".join(paragraph.text.split())
                    if text:
                        collected.append(text)
    except Exception as exc:  # pragma: no cover - malformed header parts
        log.debug("header_footer_read_failed", error=str(exc))
    return collected
