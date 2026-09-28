"""
Ingestion, version control and retrieval tests.

FR vi–x (upload, validation, parsing, chunking, version control),
FR xxii (policy retrieval), SRS Steps 3–7 and 25.

Embeddings are disabled for the whole suite (see conftest), so every retrieval
test here runs lexical-only.  That is deliberate: it keeps the tests offline
and deterministic, and it means the degradation path required by NFR 5 — the
application staying useful during a GenAI provider outage — is exercised on
every single run rather than being a claim in a document.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from knowledge_base import versioning
from knowledge_base.ingest import ingest_document
from knowledge_base.retrieval import (
    coverage_stats,
    parse_references,
    resolve_citation,
    retrieve,
)
from src.db.enums import DocStatus, IssueOutcome, ValidationIssueCode
from src.db.models import Chunk, DocumentSection, DocumentValidationIssue, DocumentVersion

pytestmark = pytest.mark.integration


# ══════════════════════════════════════════════════════════════
# Ingestion
# ══════════════════════════════════════════════════════════════
def test_corpus_ingests_into_rows(ingested_kb, db):
    assert ingested_kb, "sample documents are missing; run make_sample_documents.py"
    for name, result in ingested_kb.items():
        assert result.accepted, f"{name}: {result.message}"
        assert result.status == DocStatus.ACTIVE
        assert result.section_count > 0
        assert result.chunk_count > 0

    sections = db.execute(select(DocumentSection)).scalars().all()
    chunks = db.execute(select(Chunk)).scalars().all()
    assert sections and chunks
    assert all(c.doc_ref and c.doc_version for c in chunks)


def test_every_chunk_is_fully_traceable(ingested_kb, db):
    """
    The Source-Traceability Challenge is answerable only if each chunk knows
    its document, version, section and physical location.
    """
    for chunk in db.execute(select(Chunk)).scalars():
        assert chunk.chunk_key
        assert chunk.doc_ref and chunk.doc_version
        assert chunk.section_ref is not None
        # PDFs carry a page; DOCX carries a paragraph index. One must exist.
        assert chunk.page_no is not None or chunk.paragraph_index is not None


def test_reuploading_the_same_file_is_rejected_and_recorded(ingested_kb, db, a_document):
    result = ingest_document(db, a_document.pdf.read_bytes(), a_document.name)
    db.flush()

    assert not result.accepted
    assert ValidationIssueCode.DUPLICATE_DOCUMENT.value in result.issue_codes

    # The refusal must leave evidence, not just an error response.
    issue = db.execute(
        select(DocumentValidationIssue)
        .where(DocumentValidationIssue.issue_code == ValidationIssueCode.DUPLICATE_DOCUMENT)
        .order_by(DocumentValidationIssue.created_at.desc())
    ).scalars().first()
    assert issue is not None
    assert issue.outcome == IssueOutcome.REJECTED


def test_unparseable_upload_is_rejected_and_recorded(db):
    result = ingest_document(db, b"%PDF-1.4\nnot really a pdf at all", "broken.pdf")
    db.flush()
    assert not result.accepted

    issue = db.execute(
        select(DocumentValidationIssue)
        .where(DocumentValidationIssue.file_name == "broken.pdf")
        .order_by(DocumentValidationIssue.created_at.desc())
    ).scalars().first()
    assert issue is not None


def test_document_without_metadata_lands_in_review_not_rejected(db):
    """
    SRS 1.8 #3 — a hidden-pack document that does not follow our metadata
    convention must still be processed, with reduced traceability.
    """
    body = (
        "Customer Escalation Guidance\n\n"
        "1 Overview\n"
        "Support staff should escalate unresolved matters to a supervisor.\n\n"
        "2 Timing\n"
        "Escalate within one business day of the second customer contact.\n"
    )
    result = ingest_document(db, body.encode(), "unknown_guidance.txt")
    db.flush()

    assert result.accepted, "an unfamiliar document must not be turned away"
    assert result.status == DocStatus.METADATA_REVIEW
    assert result.requires_review
    assert result.section_count > 0
    assert ValidationIssueCode.MISSING_EFFECTIVE_DATE.value in result.issue_codes


# ══════════════════════════════════════════════════════════════
# Version control  (SRS Step 7)
# ══════════════════════════════════════════════════════════════
def test_new_version_supersedes_the_previous_one(ingested_kb, db, a_document, tmp_path):
    """Uploading v2 of a policy demotes v1 rather than deleting it."""

    from scripts.make_sample_documents import render_pdf

    spec = a_document.spec()
    spec["metadata"]["version"] = "3.0"
    # Rewrite the first section so the new version genuinely differs from the
    # one on file; an identical body would be refused as a duplicate upload.
    spec["sections"][0]["body"][0] = (
        "Standard delivery is now committed at two to four business days from "
        "the date of despatch for all metropolitan service areas."
    )
    previous_version = a_document.spec()["metadata"]["version"]
    new_file = tmp_path / f"{a_document.doc_ref}_v3.0.pdf"
    render_pdf(spec, new_file)

    result = ingest_document(db, new_file.read_bytes(), new_file.name)
    db.flush()

    assert result.accepted
    assert result.superseded_version == previous_version

    versions = db.execute(
        select(DocumentVersion)
        .where(DocumentVersion.doc_ref == a_document.doc_ref)
        .order_by(DocumentVersion.version)
    ).scalars().all()
    by_version = {v.version: v for v in versions}

    assert by_version["3.0"].status == DocStatus.ACTIVE
    assert by_version[previous_version].status == DocStatus.SUPERSEDED
    # Superseded text is retained - contradiction detection needs it.
    assert by_version[previous_version].superseded_by_id == by_version["3.0"].id
    assert db.execute(
        select(Chunk).where(
            Chunk.document_version_id == by_version[previous_version].id
        )
    ).scalars().first() is not None


def test_only_one_version_can_be_active(ingested_kb, db):
    # Every document the corpus ingested, not three remembered names.
    for doc_ref in {r.document_version.doc_ref for r in ingested_kb.values() if r.accepted}:
        active = db.execute(
            select(DocumentVersion).where(
                DocumentVersion.doc_ref == doc_ref,
                DocumentVersion.status == DocStatus.ACTIVE,
            )
        ).scalars().all()
        assert len(active) <= 1, f"{doc_ref} has {len(active)} active versions"


@pytest.mark.unit
def test_initial_status_rules():
    from datetime import date

    today = date(2026, 6, 1)
    common = {"parse_failed": False, "on": today}

    assert versioning.initial_status(
        metadata_complete=True, effective_date=date(2026, 1, 1),
        expiry_date=date(2027, 1, 1), **common,
    ) == DocStatus.ACTIVE

    assert versioning.initial_status(
        metadata_complete=True, effective_date=date(2026, 1, 1),
        expiry_date=date(2026, 5, 1), **common,
    ) == DocStatus.EXPIRED, "a policy past its expiry date must not be active"

    assert versioning.initial_status(
        metadata_complete=True, effective_date=date(2026, 12, 1),
        expiry_date=None, **common,
    ) == DocStatus.DRAFT, "a policy not yet in force must not be active"

    assert versioning.initial_status(
        metadata_complete=False, effective_date=None, expiry_date=None, **common,
    ) == DocStatus.METADATA_REVIEW

    # A document's own "Status: DRAFT" outranks a passed effective date.
    assert versioning.initial_status(
        metadata_complete=True, effective_date=date(2026, 1, 1),
        expiry_date=None, declared_status="DRAFT", **common,
    ) == DocStatus.DRAFT, "a declared draft must not become active on its dates"
    assert versioning.initial_status(
        metadata_complete=True, effective_date=date(2026, 1, 1),
        expiry_date=None, declared_status="Draft - for consultation", **common,
    ) == DocStatus.DRAFT
    assert versioning.initial_status(
        metadata_complete=True, effective_date=date(2026, 1, 1),
        expiry_date=None, declared_status="ACTIVE", **common,
    ) == DocStatus.ACTIVE


def _declared_draft(ref: str, phrase: str) -> bytes:
    return (
        f"Document ID: {ref}\nTitle: {ref} dangerous goods handling\nVersion: 0.9\n"
        f"Effective Date: 2026-01-01\nStatus: DRAFT\nDocument Type: Policy\n\n"
        f"1. Scope\n\n{phrase} before any consignment leaves the hub.\n"
    ).encode()


def test_a_document_that_declares_itself_a_draft_is_stored_as_draft(db):
    """
    DOC-025 v0.9 says DRAFT and has an effective date that has passed. Its
    dates alone made it ACTIVE, and an unapproved policy was retrievable as
    policy. It must wait as a DRAFT until somebody activates it.
    """
    import uuid

    from knowledge_base import ingest

    ref = f"DRF-{uuid.uuid4().hex[:6].upper()}"
    phrase = "Quarantine every zirconium canister in the bonded cage"
    result = ingest_document(db, _declared_draft(ref, phrase), f"{ref}_v0.9.txt")
    db.flush()

    assert result.accepted, result.message
    assert result.status == DocStatus.DRAFT
    assert result.document_version.metadata_json["status"] == "DRAFT"
    assert not any(c.doc_ref == ref for c in retrieve(db, phrase, top_k=10).chunks), (
        "a draft must not be retrievable as policy"
    )

    ingest.activate(db, result.document_version.id)
    db.flush()
    assert result.document_version.status == DocStatus.ACTIVE
    assert any(c.doc_ref == ref for c in retrieve(db, phrase, top_k=10).chunks)


def test_the_corpus_draft_is_ingested_as_draft(db, sample_documents_dir):
    """The real DOC-025 v0.9 file, as rendered into the dataset."""
    try:
        path = sample_documents_dir("DOC-025_v0.9.pdf")
    except FileNotFoundError:
        pytest.skip("DOC-025 is not part of the configured corpus")

    existing = db.execute(
        select(DocumentVersion).where(DocumentVersion.doc_ref == "DOC-025")
    ).scalars().first()
    if existing is not None:
        pytest.skip("DOC-025 is already in this database")

    result = ingest_document(db, path.read_bytes(), path.name)
    db.flush()
    assert result.accepted, result.message
    assert result.status == DocStatus.DRAFT


@pytest.mark.unit
def test_precedence_order_is_configuration_not_code(db):
    order = versioning.precedence_order(db)
    assert order[0] == "ACTIVE_POLICY"
    assert "FAQ" in order
    # A policy must outrank an FAQ that contradicts it (SRS 1.8 #10).
    assert versioning.precedence_rank(db, "POLICY") < versioning.precedence_rank(db, "FAQ")
    # An unrecognised type sorts last, never first.
    assert versioning.precedence_rank(db, "SOMETHING_NEW") >= len(order) - 1


@pytest.mark.unit
def test_conflict_resolution_prefers_policy_then_recency(db):
    from datetime import date

    winner, overruled = versioning.resolve_conflict(
        db,
        [
            ("FAQ-01", "FAQ", date(2026, 8, 1)),
            ("DEL-POL-04", "POLICY", date(2026, 4, 1)),
        ],
    )
    assert winner == "DEL-POL-04", "a newer FAQ must not overrule an active policy"
    assert overruled == ["FAQ-01"]


# ══════════════════════════════════════════════════════════════
# Retrieval  (SRS Step 25)
# ══════════════════════════════════════════════════════════════
def test_retrieval_finds_the_relevant_policy(ingested_kb, db, an_indexed_phrase):
    doc_ref, _, phrase = an_indexed_phrase
    result = retrieve(db, phrase, top_k=5)
    assert len(result) > 0
    assert any(c.doc_ref == doc_ref for c in result.chunks), (
        f"a phrase taken from {doc_ref} did not retrieve it: {phrase!r}"
    )


def test_retrieval_returns_full_citations(ingested_kb, db):
    result = retrieve(db, "delivery compensation eligibility", top_k=3)
    assert result.chunks
    for chunk in result.chunks:
        citation = chunk.citation()
        assert citation["doc_ref"] and citation["version"] and citation["chunk_key"]
        assert citation["page_no"] is not None or citation["paragraph_index"] is not None


def test_retrieval_excludes_superseded_versions(
    ingested_kb, db, a_document, an_indexed_phrase, tmp_path
):
    """The invariant that makes 'an outdated policy is never used' true."""

    from scripts.make_sample_documents import render_pdf

    spec = a_document.spec()
    spec["metadata"]["version"] = "4.0"
    new_file = tmp_path / f"{a_document.doc_ref}_v4.0.pdf"
    render_pdf(spec, new_file)
    ingest_document(db, new_file.read_bytes(), new_file.name)
    db.flush()

    _, _, phrase = an_indexed_phrase
    superseded = a_document.spec()["metadata"]["version"]

    result = retrieve(db, phrase, top_k=20)
    versions = {c.doc_version for c in result.chunks if c.doc_ref == a_document.doc_ref}
    assert superseded not in versions, "a superseded version must never be retrieved"

    # ...but it is still reachable when explicitly requested, for diffing.
    with_old = retrieve(db, phrase, top_k=40, include_superseded=True)
    assert superseded in {
        c.doc_version for c in with_old.chunks if c.doc_ref == a_document.doc_ref
    }


def test_exact_reference_outranks_semantic_similarity(ingested_kb, db, an_indexed_phrase):
    """
    A judge asking for 'DEL-POL-04 section 5' during the Traceability
    Challenge must get that section, not a similar-sounding one.
    """
    doc_ref, section_ref, _ = an_indexed_phrase
    result = retrieve(db, f"{doc_ref} section {section_ref}", top_k=3)

    assert result.exact_count > 0
    top = result.chunks[0]
    assert top.doc_ref == doc_ref
    assert top.section_ref == section_ref
    assert top.matched_by == "EXACT_REF"


@pytest.mark.unit
@pytest.mark.parametrize(
    "query,expected_refs,expected_sections",
    [
        ("DEL-POL-04 section 5", ["DEL-POL-04"], ["5"]),
        ("what does SAF-POL-02 say", ["SAF-POL-02"], []),
        ("refer to REF-POL-02 clause 2.1", ["REF-POL-02"], ["2.1"]),
        ("my parcel never arrived", [], []),
    ],
)
def test_reference_parsing(query, expected_refs, expected_sections):
    refs, sections = parse_references(query)
    assert refs == expected_refs
    assert sections == expected_sections


def test_retrieval_on_empty_knowledge_base_is_reported_not_raised(db):
    from sqlalchemy import delete

    from src.db.models import Document

    for model in (Chunk, DocumentSection, DocumentValidationIssue, DocumentVersion, Document):
        db.execute(delete(model))
    db.flush()

    result = retrieve(db, "anything at all")
    assert result.knowledge_base_empty
    assert len(result) == 0


def test_retrieval_works_without_embeddings(ingested_kb, db, an_indexed_phrase):
    """
    The whole suite runs with EMBEDDING_ENABLED=false, so this asserts the
    outage path explicitly rather than by accident.
    """
    _, _, phrase = an_indexed_phrase
    result = retrieve(db, phrase, top_k=5)
    assert not result.semantic_available
    assert result.lexical_count > 0
    assert len(result) > 0


# ══════════════════════════════════════════════════════════════
# Citation resolution — the primitive hallucination detection needs
# ══════════════════════════════════════════════════════════════
def test_a_real_citation_resolves(ingested_kb, db, an_indexed_phrase):
    doc_ref, section_ref, _ = an_indexed_phrase
    assert resolve_citation(db, doc_ref=doc_ref, section_ref=section_ref) is not None


def test_an_invented_citation_does_not_resolve(ingested_kb, db):
    assert resolve_citation(db, doc_ref="FAKE-POL-99", section_ref="1") is None
    assert resolve_citation(db, chunk_key="MADE-UP::9.9::c1") is None


def test_citation_resolves_by_chunk_key(ingested_kb, db):
    chunk = db.execute(select(Chunk)).scalars().first()
    resolved = resolve_citation(db, chunk_key=chunk.chunk_key)
    assert resolved is not None and resolved.id == chunk.id


def test_coverage_stats_reflect_the_corpus(ingested_kb, db):
    stats = coverage_stats(db)
    accepted_active = sum(
        1 for result in ingested_kb.values()
        if result.accepted and result.status == DocStatus.ACTIVE
    )
    assert stats["active_documents"] == accepted_active
    assert stats["chunks"] > 0
    # Embeddings are off in tests, so everything is unembedded - and that is
    # reported honestly rather than hidden.
    assert stats["embedded_chunks"] + stats["unembedded_chunks"] == stats["chunks"]
