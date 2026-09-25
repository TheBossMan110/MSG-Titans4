"""
Document processing tests — FR vi–ix, SRS Steps 3–6.

These cover the Parsing, Chunking and Document-upload test categories the SRS
requires (Deliverable 11), and they pin two regressions that were found while
building the pipeline:

* a bare capital letter at the start of wrapped prose being read as a lettered
  section, which invented a section that generated text could then cite;
* merged-cell deduplication in DOCX tables collapsing legitimately repeated
  adjacent values, silently dropping a column of an SLA/routing matrix.
"""

from __future__ import annotations

import pathlib

import pytest

from document_processing.chunker import chunk_document, estimate_tokens
from document_processing.metadata import (
    derive_from_filename,
    extract_metadata,
    family_key_for,
    parse_date,
)
from document_processing.parser import parse_document
from document_processing.sections import looks_like_heading
from document_processing.validation import (
    detect_format,
    safe_filename,
    validate_file,
    validate_metadata,
)

# The corpus moved out of the backend when the project split into
# backend / frontend / dataset. Resolved through settings so a
# relocation is a one-line change rather than a grep.
from src.core.config import settings  # noqa: E402
from src.db.enums import FileFormat, ValidationIssueCode


def corpus(name: str) -> pathlib.Path:
    """
    A corpus file, wherever its domain happens to be.

    Which domain a policy belongs to is a business fact that can change, and a
    test that hardcoded it would break on a filing decision with nothing to do
    with what it tests. Returns a non-existent path rather than raising, so the
    module-level skip guard below can report "corpus missing" rather than
    erroring at import.
    """
    # Parser fixtures are not organisation data: look in every domain folder
    # under dataset/, not only the ones DATASET_DOMAINS makes active, so the
    # parsing tests keep running whichever organisation is configured.
    folders = [*settings.document_dirs, *sorted(settings.dataset_dir.glob("*/documents"))]
    for folder in folders:
        candidate = folder / name
        if candidate.exists():
            return candidate
    return settings.dataset_dir / "missing" / name

PDF_SAMPLE = corpus("DEL-POL-04_v2.1.pdf")
DOCX_SAMPLE = corpus("DEL-POL-04_v2.1.docx")
DOCX_TABLE_SAMPLE = corpus("REF-POL-02_v3.0.docx")

pytestmark = pytest.mark.skipif(
    not PDF_SAMPLE.exists(),
    reason="run `python scripts/make_sample_documents.py` to render the corpus",
)


def _parse(path: pathlib.Path):
    data = path.read_bytes()
    result = validate_file(data, path.name)
    assert not result.is_rejected, [i.code for i in result.issues]
    return parse_document(data, file_name=path.name, file_format=result.file_format)


# ══════════════════════════════════════════════════════════════
# File validation — SRS Step 4
# ══════════════════════════════════════════════════════════════
@pytest.mark.unit
def test_format_is_detected_from_magic_bytes_not_extension():
    """A .pdf extension on DOCX bytes must not fool the dispatcher."""
    docx_bytes = DOCX_SAMPLE.read_bytes()
    detected, mismatch = detect_format(docx_bytes, "totally_a_policy.pdf")
    assert detected == FileFormat.DOCX
    assert mismatch, "an extension/content mismatch must be reported"


@pytest.mark.unit
def test_extension_spoofing_is_recorded_but_content_is_trusted():
    result = validate_file(DOCX_SAMPLE.read_bytes(), "spoofed.pdf")
    assert result.file_format == FileFormat.DOCX
    assert not result.is_rejected
    assert ValidationIssueCode.UNSUPPORTED_FILE_TYPE in {i.code for i in result.issues}


@pytest.mark.unit
def test_empty_file_is_rejected():
    result = validate_file(b"", "empty.pdf")
    assert result.is_rejected
    assert {i.code for i in result.issues} == {ValidationIssueCode.EMPTY_FILE}


@pytest.mark.unit
def test_unsupported_file_type_is_rejected():
    result = validate_file(b"\x00\x01\x02" * 100, "payload.exe")
    assert result.is_rejected
    assert ValidationIssueCode.UNSUPPORTED_FILE_TYPE in {i.code for i in result.issues}


@pytest.mark.unit
def test_oversized_file_is_rejected(monkeypatch):
    from src.core import config

    monkeypatch.setattr(config.settings, "max_upload_mb", 0.00001, raising=False)
    result = validate_file(PDF_SAMPLE.read_bytes(), PDF_SAMPLE.name)
    assert result.is_rejected
    assert ValidationIssueCode.FILE_TOO_LARGE in {i.code for i in result.issues}


@pytest.mark.unit
def test_duplicate_document_is_detected_by_hash():
    data = PDF_SAMPLE.read_bytes()
    first = validate_file(data, PDF_SAMPLE.name)
    second = validate_file(data, "renamed_copy.pdf", existing_hashes={first.file_hash})
    assert second.is_rejected
    assert ValidationIssueCode.DUPLICATE_DOCUMENT in {i.code for i in second.issues}


@pytest.mark.unit
@pytest.mark.parametrize(
    "raw,expected",
    [
        # Path components are discarded entirely, so traversal cannot survive.
        ("../../etc/passwd", "passwd"),
        ("C:\\Windows\\system32\\cmd.exe", "cmd.exe"),
        ("normal-policy_v2.pdf", "normal-policy_v2.pdf"),
        ("policy<>:\"|?*.pdf", "policy_.pdf"),
        ("", "unnamed"),
    ],
)
def test_filenames_are_sanitised(raw, expected):
    cleaned = safe_filename(raw)
    assert cleaned == expected
    assert "/" not in cleaned and "\\" not in cleaned and ".." not in cleaned


# ══════════════════════════════════════════════════════════════
# Metadata — SRS Step 4/5, and hidden-pack degradation
# ══════════════════════════════════════════════════════════════
@pytest.mark.unit
def test_metadata_is_read_from_the_front_matter_block():
    document = _parse(PDF_SAMPLE)
    meta = document.metadata
    assert meta.doc_ref == "DEL-POL-04"
    assert meta.version == "2.1"
    assert meta.title == "Delivery and Shipment Policy"
    assert meta.effective_date and meta.effective_date.isoformat() == "2026-04-01"
    assert meta.department == "Logistics"
    assert meta.is_complete


@pytest.mark.unit
def test_metadata_falls_back_to_the_filename():
    """A hidden-pack document with no metadata block must still be identifiable."""
    meta = extract_metadata(
        "Some policy text with no labelled fields at all.",
        file_name="ESC-SOP-09_v1.4.docx",
    )
    assert meta.doc_ref == "ESC-SOP-09"
    assert meta.version == "1.4"
    assert not meta.is_complete           # no effective date -> METADATA_REVIEW
    assert "effective_date" in meta.missing_fields


@pytest.mark.unit
def test_missing_metadata_produces_issues_but_is_never_fatal():
    meta = extract_metadata("Unlabelled body text.", file_name="mystery.pdf")
    issues = validate_metadata(meta, file_name="mystery.pdf")
    codes = {i.code for i in issues}
    assert ValidationIssueCode.MISSING_DOCUMENT_ID in codes
    assert ValidationIssueCode.MISSING_EFFECTIVE_DATE in codes
    assert not any(i.fatal for i in issues), "metadata gaps must never reject a document"


@pytest.mark.unit
@pytest.mark.parametrize(
    "raw,iso",
    [
        ("2026-04-01", "2026-04-01"),
        ("01/04/2026", "2026-04-01"),
        ("1 April 2026", "2026-04-01"),
        ("April 1, 2026", "2026-04-01"),
        ("1st April 2026", "2026-04-01"),
        ("not a date", None),
        (None, None),
    ],
)
def test_dates_are_parsed_tolerantly(raw, iso):
    parsed = parse_date(raw)
    assert (parsed.isoformat() if parsed else None) == iso


@pytest.mark.unit
def test_family_key_groups_versions_of_one_document():
    assert family_key_for("DEL-POL-04", None, "x.pdf") == "DEL-POL-04"
    # Same family regardless of which version file produced it.
    assert derive_from_filename("DEL-POL-04_v2.1.pdf")[0] == "DEL-POL-04"
    assert derive_from_filename("DEL-POL-04_v1.4.pdf")[0] == "DEL-POL-04"


# ══════════════════════════════════════════════════════════════
# Section detection
# ══════════════════════════════════════════════════════════════
@pytest.mark.unit
@pytest.mark.parametrize(
    "line,is_heading",
    [
        ("5.2 Delivery Windows", True),
        ("3 Delayed Delivery", True),
        ("Section 4 - Lost Shipments", True),
        ("A.3 Appendix Items", True),
        ("A. Appendix", True),
        ("ESCALATION TRIGGERS", True),
        # Regression: wrapped prose beginning with a bare capital letter.
        ("A delivery complaint must be escalated to Compliance Review", False),
        ("A refund may be requested within fourteen days of delivery", False),
        ("I have contacted you three times about this order already", False),
        ("Agents must not offer compensation for a delayed delivery.", False),
        ("Page 3 of 12", False),
        ("", False),
    ],
)
def test_heading_detection(line, is_heading):
    assert looks_like_heading(line)[0] is is_heading


@pytest.mark.unit
def test_bare_capital_letter_does_not_invent_a_section():
    """
    Regression guard.  'A delivery complaint must be...' was being read as
    lettered section 'A', creating a section that never existed in the source.
    A citation to it could never be resolved.
    """
    document = _parse(PDF_SAMPLE)
    assert "A" not in {s.section_ref for s in document.sections}


# ══════════════════════════════════════════════════════════════
# Parsing — both mandatory formats
# ══════════════════════════════════════════════════════════════
@pytest.mark.unit
def test_pdf_sections_carry_page_numbers():
    document = _parse(PDF_SAMPLE)
    assert document.page_count and document.page_count >= 1
    assert document.sections
    assert all(s.page_no is not None for s in document.sections), (
        "a PDF citation must be able to name the page"
    )


@pytest.mark.unit
def test_docx_sections_carry_paragraph_indices():
    document = _parse(DOCX_SAMPLE)
    assert document.paragraph_count and document.paragraph_count > 0
    assert document.sections
    assert all(s.paragraph_index is not None for s in document.sections), (
        "a DOCX citation must be able to name the paragraph"
    )


@pytest.mark.unit
def test_pdf_and_docx_of_the_same_document_agree():
    """
    The two renderings hold byte-identical content, so the two parsers must
    reach the same section structure.  If they diverge, one of them is wrong.
    """
    pdf, docx = _parse(PDF_SAMPLE), _parse(DOCX_SAMPLE)
    assert [s.section_ref for s in pdf.sections] == [s.section_ref for s in docx.sections]
    assert [s.heading for s in pdf.sections] == [s.heading for s in docx.sections]
    assert pdf.metadata.doc_ref == docx.metadata.doc_ref
    assert pdf.metadata.version == docx.metadata.version


@pytest.mark.unit
def test_expected_sections_are_present():
    document = _parse(PDF_SAMPLE)
    headings = {s.heading for s in document.sections}
    assert "Delivery Compensation Eligibility" in headings
    assert "Escalation Triggers" in headings


@pytest.mark.unit
def test_docx_tables_are_captured_without_losing_columns():
    """
    Regression guard.  Merged-cell dedupe was collapsing adjacent cells with
    the same text, so '14 days | 14 days' became one column and the refund
    matrix silently lost a field.
    """
    document = _parse(DOCX_TABLE_SAMPLE)
    table_text = "\n".join(s.text for s in document.sections if "|" in s.text)
    assert "Product Category | Refund Window | Replacement Window" in table_text
    assert "General merchandise | 14 days | 14 days | Unused and repackaged" in table_text


@pytest.mark.unit
def test_a_corrupt_pdf_is_reported_not_raised():
    result = parse_document(
        b"%PDF-1.4\nthis is not actually a valid pdf body",
        file_name="broken.pdf",
        file_format=FileFormat.PDF,
    )
    assert result.is_fatal
    assert not result.sections


# ══════════════════════════════════════════════════════════════
# Chunking — SRS Step 6
# ══════════════════════════════════════════════════════════════
@pytest.mark.unit
def test_chunks_never_cross_a_section_boundary():
    """
    The load-bearing invariant.  A chunk spanning two sections cannot be cited
    honestly, and citation integrity is what the whole project is judged on.
    """
    document = _parse(PDF_SAMPLE)
    section_text = {s.section_ref: s.text for s in document.sections}
    chunks = chunk_document(document.sections, doc_ref="DEL-POL-04")

    assert chunks
    for chunk in chunks:
        assert chunk.section_ref in section_text
        # Every non-heading line of the chunk must come from its own section.
        body = chunk.text.split("\n", 1)[-1]
        source = section_text[chunk.section_ref]
        sample = body[:60].strip()
        if sample:
            assert sample in source or sample in " ".join(source.split()), (
                f"chunk {chunk.chunk_key} contains text absent from its section"
            )


@pytest.mark.unit
def test_chunk_keys_are_unique_and_traceable():
    document = _parse(PDF_SAMPLE)
    chunks = chunk_document(document.sections, doc_ref="DEL-POL-04")
    keys = [c.chunk_key for c in chunks]
    assert len(keys) == len(set(keys)), "duplicate chunk keys break citation resolution"
    for chunk in chunks:
        assert chunk.chunk_key.startswith("DEL-POL-04::")
        assert f"::{chunk.section_ref}::" in chunk.chunk_key


@pytest.mark.unit
def test_chunks_carry_location_metadata_forward():
    document = _parse(PDF_SAMPLE)
    chunks = chunk_document(document.sections, doc_ref="DEL-POL-04")
    assert all(c.page_no is not None for c in chunks)
    assert all(c.token_count > 0 for c in chunks)


@pytest.mark.unit
def test_chunks_include_their_section_heading():
    """
    'within 48 hours of delivery' is ambiguous alone and meaningful under
    '2 Refund Eligibility Window'. Retrieval quality depends on the prefix.
    """
    document = _parse(DOCX_TABLE_SAMPLE)
    chunks = chunk_document(document.sections, doc_ref="REF-POL-02")
    headed = [c for c in chunks if c.heading and c.heading != "Preamble"]
    assert headed
    for chunk in headed:
        assert chunk.heading in chunk.text


@pytest.mark.unit
def test_long_sections_are_split_and_short_ones_are_not():
    document = _parse(PDF_SAMPLE)
    small = chunk_document(document.sections, doc_ref="D", max_tokens=64, overlap_tokens=8)
    large = chunk_document(document.sections, doc_ref="D", max_tokens=4000, overlap_tokens=0)
    assert len(small) > len(large)
    assert len(large) == len([s for s in document.sections if s.text.strip() or s.heading])


@pytest.mark.unit
def test_token_estimate_is_monotonic():
    assert estimate_tokens("short") < estimate_tokens("short " * 200)
