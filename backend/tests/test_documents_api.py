"""
Knowledge-base API tests.

Covers the Document-upload and Security (unauthorised-access) test categories
the SRS requires as deliverables, and proves the Source-Traceability Challenge
is answerable through a single endpoint.
"""

from __future__ import annotations

import pathlib

import pytest

# The corpus moved out of the backend when the project split into
# backend / frontend / dataset. Resolved through settings so a
# relocation is a one-line change rather than a grep.
from src.core.config import settings  # noqa: E402


def corpus(name: str) -> pathlib.Path:
    """
    A corpus file, wherever its domain happens to be.

    Which domain a policy belongs to is a business fact that can change, and a
    test that hardcoded it would break on a filing decision with nothing to do
    with what it tests. Returns a non-existent path rather than raising, so the
    module-level skip guard below can report "corpus missing" rather than
    erroring at import.
    """
    for folder in settings.document_dirs:
        candidate = folder / name
        if candidate.exists():
            return candidate
    return settings.dataset_dir / "missing" / name

PDF = corpus("DOC-001_v2.0.pdf")
DOCX = corpus("DOC-010_v2.0.docx")

pytestmark = pytest.mark.skipif(
    not PDF.exists(), reason="run `python scripts/make_sample_documents.py` first"
)


def _upload(client, headers, path: pathlib.Path, mime: str, **params):
    with path.open("rb") as handle:
        return client.post(
            "/api/documents",
            headers=headers,
            files={"files": (path.name, handle, mime)},
            params=params or None,
        )


PDF_MIME = "application/pdf"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@pytest.fixture(autouse=True)
def _clean_knowledge_base(db):
    """
    Start every test from an empty corpus.

    Duplicate detection is content-hash based and works across the whole
    database, so without this the second test to upload the same file would
    (correctly) have it refused - and then fail for the wrong reason.
    """
    from sqlalchemy import delete

    from src.db.models import (
        Chunk,
        Document,
        DocumentSection,
        DocumentValidationIssue,
        DocumentVersion,
    )

    def _purge():
        for model in (
            Chunk, DocumentSection, DocumentValidationIssue, DocumentVersion, Document,
        ):
            db.execute(delete(model))
        db.commit()

    _purge()
    yield
    _purge()


# ══════════════════════════════════════════════════════════════
# access control  (FR ii — unauthorised-access evidence)
# ══════════════════════════════════════════════════════════════
@pytest.mark.integration
def test_upload_requires_authentication(client):
    with PDF.open("rb") as handle:
        response = client.post(
            "/api/documents", files={"files": (PDF.name, handle, PDF_MIME)}
        )
    assert response.status_code == 401


@pytest.mark.integration
def test_agent_cannot_upload_documents(client, auth_headers):
    response = _upload(client, auth_headers("agent"), PDF, PDF_MIME)
    assert response.status_code == 403
    body = response.json()["error"]
    assert body["code"] == "FORBIDDEN"
    assert "admin" in body["details"]["required_roles"]


@pytest.mark.integration
def test_refused_access_is_written_to_the_audit_trail(client, auth_headers, db):
    """
    The refusal must survive the request rollback, because the Security
    Testing Report is built by querying these rows.
    """
    from sqlalchemy import select

    from src.db.models import AuditLog

    _upload(client, auth_headers("agent"), PDF, PDF_MIME)

    entry = db.execute(
        select(AuditLog)
        .where(AuditLog.action == "ACCESS_DENIED")
        .order_by(AuditLog.created_at.desc())
        .limit(1)
    ).scalars().first()
    assert entry is not None
    assert entry.entity_id == "/api/documents"


@pytest.mark.integration
def test_evaluator_can_read_but_not_upload(client, auth_headers):
    headers = auth_headers("evaluator")
    assert client.get("/api/documents", headers=headers).status_code == 200
    assert client.get("/api/documents/coverage", headers=headers).status_code == 200
    assert _upload(client, headers, PDF, PDF_MIME).status_code == 403


# ══════════════════════════════════════════════════════════════
# upload  (FR vi–ix)
# ══════════════════════════════════════════════════════════════
@pytest.mark.integration
def test_admin_can_upload_a_pdf(client, auth_headers):
    response = _upload(client, auth_headers("admin"), PDF, PDF_MIME)
    assert response.status_code == 201, response.text

    body = response.json()
    assert body["uploaded"] == 1
    result = body["results"][0]
    assert result["accepted"] is True
    assert result["doc_ref"] == "DOC-001"
    assert result["version"] == "2.0"
    assert result["status"] == "ACTIVE"
    assert result["section_count"] > 0
    assert result["chunk_count"] > 0


@pytest.mark.integration
def test_admin_can_upload_a_docx(client, auth_headers):
    response = _upload(client, auth_headers("admin"), DOCX, DOCX_MIME)
    assert response.status_code == 201
    result = response.json()["results"][0]
    assert result["accepted"] is True
    assert result["doc_ref"] == "DOC-010"


@pytest.mark.integration
def test_duplicate_upload_is_reported_per_file_not_as_an_error(client, auth_headers):
    headers = auth_headers("admin")
    _upload(client, headers, PDF, PDF_MIME)
    response = _upload(client, headers, PDF, PDF_MIME)

    # Still 201: the request succeeded, the file was refused.
    assert response.status_code == 201
    result = response.json()["results"][0]
    assert result["accepted"] is False
    assert any(i["code"] == "DUPLICATE_DOCUMENT" for i in result["issues"])


@pytest.mark.integration
def test_unsupported_file_type_is_refused_with_a_reason(client, auth_headers):
    response = client.post(
        "/api/documents",
        headers=auth_headers("admin"),
        files={"files": ("payload.exe", b"MZ\x90\x00" + b"\x00" * 200, "application/octet-stream")},
    )
    assert response.status_code == 201
    result = response.json()["results"][0]
    assert result["accepted"] is False
    assert any(i["code"] == "UNSUPPORTED_FILE_TYPE" for i in result["issues"])


@pytest.mark.integration
def test_validation_findings_are_queryable(client, auth_headers):
    headers = auth_headers("admin")
    _upload(client, headers, PDF, PDF_MIME)
    _upload(client, headers, PDF, PDF_MIME)  # duplicate -> recorded

    response = client.get(
        "/api/documents/validation-issues",
        headers=headers,
        params={"issue_code": "DUPLICATE_DOCUMENT"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] >= 1
    assert body["items"][0]["outcome"] == "REJECTED"


# ══════════════════════════════════════════════════════════════
# browse and version control  (FR x)
# ══════════════════════════════════════════════════════════════
@pytest.mark.integration
def test_documents_list_shows_the_active_version(client, auth_headers):
    headers = auth_headers("admin")
    _upload(client, headers, PDF, PDF_MIME)

    body = client.get("/api/documents", headers=headers).json()
    assert body["total"] >= 1
    document = next(d for d in body["items"] if d["family_key"] == "DOC-001")
    assert document["active_version"]["status"] == "ACTIVE"
    assert document["version_count"] >= 1


@pytest.mark.integration
def test_version_detail_exposes_sections_for_inspection(client, auth_headers):
    headers = auth_headers("admin")
    version_id = _upload(client, headers, PDF, PDF_MIME).json()["results"][0][
        "document_version_id"
    ]

    detail = client.get(f"/api/documents/versions/{version_id}", headers=headers).json()
    assert detail["doc_ref"] == "DOC-001"
    assert detail["sections"]
    headings = {s["heading"] for s in detail["sections"]}
    assert "Eligible Refund Timelines" in headings
    assert all(s["page_no"] is not None for s in detail["sections"])


@pytest.mark.integration
def test_deactivate_withdraws_without_deleting(client, auth_headers):
    headers = auth_headers("admin")
    version_id = _upload(client, headers, PDF, PDF_MIME).json()["results"][0][
        "document_version_id"
    ]

    response = client.post(
        f"/api/documents/versions/{version_id}/deactivate", headers=headers
    )
    assert response.status_code == 200
    assert response.json()["status"] == "SUPERSEDED"

    # The content survives - contradiction detection needs it.
    chunks = client.get(
        f"/api/documents/versions/{version_id}/chunks", headers=headers
    ).json()
    assert chunks


@pytest.mark.integration
def test_reactivating_restores_retrievability(client, auth_headers):
    headers = auth_headers("admin")
    version_id = _upload(client, headers, PDF, PDF_MIME).json()["results"][0][
        "document_version_id"
    ]

    client.post(f"/api/documents/versions/{version_id}/deactivate", headers=headers)
    response = client.post(
        f"/api/documents/versions/{version_id}/activate", headers=headers
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ACTIVE"


# ══════════════════════════════════════════════════════════════
# retrieval and traceability  (FR xxii, FR l)
# ══════════════════════════════════════════════════════════════
@pytest.mark.integration
def test_search_returns_scored_results_with_citations(client, auth_headers):
    headers = auth_headers("admin")
    _upload(client, headers, DOCX, DOCX_MIME)

    response = client.post(
        "/api/documents/search",
        headers=headers,
        json={"query": "ticket intake initial triage", "top_k": 5},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["results"]
    top = body["results"][0]
    assert top["doc_ref"] and top["doc_version"] and top["chunk_key"]
    assert top["score"] > 0
    assert top["matched_by"] in {"LEXICAL", "SEMANTIC", "HYBRID", "EXACT_REF"}
    # Embeddings are off in tests; the response says so rather than pretending.
    assert body["semantic_available"] is False


@pytest.mark.integration
def test_search_on_empty_knowledge_base_is_not_an_error(client, auth_headers):
    response = client.post(
        "/api/documents/search",
        headers=auth_headers("admin"),
        json={"query": "anything"},
    )
    assert response.status_code == 200
    assert response.json()["results"] == []


@pytest.mark.integration
def test_traceability_resolves_a_real_citation(client, auth_headers):
    """The Source-Traceability Challenge, answered in one call."""
    headers = auth_headers("admin")
    _upload(client, headers, PDF, PDF_MIME)

    search = client.post(
        "/api/documents/search",
        headers=headers,
        json={"query": "delivery compensation eligibility", "top_k": 1},
    ).json()
    chunk_key = search["results"][0]["chunk_key"]

    response = client.get(f"/api/documents/trace/{chunk_key}", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["resolved"] is True
    assert body["citation"]["doc_ref"] == "DOC-001"
    assert body["document_status"] == "ACTIVE"
    assert body["applicability"] == "APPLICABLE"
    assert body["text"]


@pytest.mark.integration
def test_traceability_reports_an_invented_citation_as_unresolved(client, auth_headers):
    """
    An unresolvable citation is a finding, not a 404 - this is the primitive
    hallucination detection is built on.
    """
    response = client.get(
        "/api/documents/trace/FAKE-POL-99::9.9::c1", headers=auth_headers("admin")
    )
    assert response.status_code == 200
    body = response.json()
    assert body["resolved"] is False
    assert body["citation"] is None
    assert "unsupported" in body["reason"].lower()


@pytest.mark.integration
def test_traceability_by_document_reference(client, auth_headers):
    headers = auth_headers("admin")
    _upload(client, headers, PDF, PDF_MIME)

    response = client.get(
        "/api/documents/chunks/by-reference",
        headers=headers,
        params={"doc_ref": "DOC-001", "section_ref": "4"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["resolved"] is True
    assert body["citation"]["section_ref"].startswith("4")


@pytest.mark.integration
def test_coverage_reports_corpus_health(client, auth_headers):
    headers = auth_headers("admin")
    _upload(client, headers, PDF, PDF_MIME)

    body = client.get("/api/documents/coverage", headers=headers).json()
    assert body["active_documents"] >= 1
    assert body["chunks"] > 0
    assert body["knowledge_base_version"].startswith("kb:")
    assert body["semantic_search_available"] is False
