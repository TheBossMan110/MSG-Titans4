"""
The super administrator sees the platform, never a company.

Allowed: every company's totals (/platform/overview, /company/all), the shared
template (rules, taxonomy, configuration, prompts), the platform's own audit
log. Refused: every router that serves one company's data, wholesale, so an
endpoint that forgets its own role gate is still closed to them.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import delete

from src.core import tenancy
from src.db.base import Base
from src.db.models import Organisation

PASSWORD = "Correct-Horse-Battery-9"
COMPLAINT = {"title": "Parcel never arrived", "description": "My parcel CN-55120045 was due on Monday and has not arrived."}


@pytest.fixture(scope="module")
def client_module():
    from fastapi.testclient import TestClient

    from src.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def other_company(client_module):
    """A second company with two complaints, so totals have something to cross."""
    tag = uuid.uuid4().hex[:6]
    login = client_module.post("/api/auth/login", json={"email": "superadmin@supportnova.com", "password": "SupportNova#2026"})
    super_admin = {"Authorization": f"Bearer {login.json()['access_token']}"}
    out = client_module.post("/api/company/create", headers=super_admin, json={
        "company_name": f"Beta Freight {tag}", "admin_full_name": "Bilal Ahmed",
        "admin_email": f"bilal.{tag}@beta-example.com", "admin_password": PASSWORD,
    })
    assert out.status_code == 201, out.text
    signed = client_module.post("/api/auth/login", json={"email": f"bilal.{tag}@beta-example.com", "password": PASSWORD})
    headers = {"Authorization": f"Bearer {signed.json()['access_token']}"}
    for _ in range(2):
        created = client_module.post("/api/complaints?analyse=false", headers=headers, json=COMPLAINT)
        assert created.status_code == 201, created.text
    organisation_id = uuid.UUID(out.json()["company"]["id"])
    yield {"id": organisation_id, "name": f"Beta Freight {tag}", "admin": headers}

    from src.db.base import SessionLocal

    db = SessionLocal()
    try:
        for table in reversed(Base.metadata.sorted_tables):
            if "organisation_id" in table.c and table.name != "organisations":
                db.execute(delete(table).where(table.c.organisation_id == organisation_id))
        db.execute(delete(Organisation).where(Organisation.id == organisation_id))
        db.commit()
    finally:
        db.close()
    tenancy.forget(organisation_id)


def test_the_super_admin_belongs_to_the_platform(client_module, auth_headers):
    me = client_module.get("/api/auth/me", headers=auth_headers("superadmin")).json()
    assert me["role"] == "superadmin"
    assert me["organisation"]["is_platform"] is True and me["organisation"]["owns_template"] is False
    assert me["permissions"] == ["audit.view"] and me["complaint_scope"] == "none"


@pytest.mark.parametrize("method,path,body", [
    ("GET", "/api/complaints", None),
    ("POST", "/api/complaints?analyse=false", COMPLAINT),
    ("GET", "/api/email/messages", None),
    ("GET", "/api/people", None),
    ("GET", "/api/staff", None),
    ("GET", "/api/live/pulse", None),
    ("GET", "/api/analytics/dashboard", None),
    ("GET", "/api/documents", None),
    ("GET", "/api/review/queue", None),
    ("GET", "/api/organisation", None),
    ("GET", "/api/benchmark/runs", None),
    ("POST", "/api/assistant/chat", {"messages": [{"role": "user", "content": "hello"}]}),
    ("GET", "/api/company", None),
])
def test_the_super_admin_sees_no_company_data(client_module, auth_headers, method, path, body):
    out = client_module.request(method, path, headers=auth_headers("superadmin"), json=body)
    assert out.status_code == 403, f"{method} {path} -> {out.status_code} {out.text[:200]}"


@pytest.mark.parametrize("path", [
    "/api/platform/overview", "/api/company/all", "/api/admin/rules", "/api/admin/taxonomy",
    "/api/admin/config", "/api/admin/prompts", "/api/audit", "/api/version",
])
def test_the_super_admin_sees_the_platform(client_module, auth_headers, path):
    out = client_module.get(path, headers=auth_headers("superadmin"))
    assert out.status_code == 200, out.text[:300]


def test_the_overview_adds_up_across_companies(client_module, auth_headers, other_company):
    body = client_module.get("/api/platform/overview", headers=auth_headers("superadmin")).json()
    assert body["companies"]["total"] >= 2
    assert body["complaints"]["total"] == sum(c["complaints"] for c in body["by_company"]), \
        "all-time totals are the sum of every company's"
    beta = next(c for c in body["by_company"] if c["name"] == other_company["name"])
    assert beta["complaints"] == 2 and beta["open_complaints"] == 2
    assert {"agreement", "safety", "ai", "sla", "escalation"} <= set(body)
    windowed = client_module.get("/api/platform/overview?days=30", headers=auth_headers("superadmin"))
    assert windowed.status_code == 200 and windowed.json()["window_days"] == 30


@pytest.mark.parametrize("who", ["company admin", "raftarxpress admin", "evaluator"])
def test_only_the_super_admin_sees_the_overview(client_module, auth_headers, other_company, who):
    headers = other_company["admin"] if who == "company admin" else auth_headers(
        "admin" if who == "raftarxpress admin" else "evaluator")
    assert client_module.get("/api/platform/overview", headers=headers).status_code == 403


def test_the_super_admin_maintains_the_shared_template(client_module, auth_headers, other_company):
    current = client_module.get("/api/admin/config", headers=auth_headers("superadmin")).json()
    entry = next(e for e in current if e["key"] == "content_relevance")
    body = {"value": entry["value"], "reason": "unchanged, a test"}
    assert client_module.put("/api/admin/config/content_relevance", headers=auth_headers("superadmin"),
                             json=body).status_code == 200
    # The reference company's administrators keep their edit, as the README documents...
    assert client_module.put("/api/admin/config/content_relevance", headers=auth_headers("admin"),
                             json=body).status_code == 200
    # ...and any other company only reads it.
    assert client_module.put("/api/admin/config/content_relevance", headers=other_company["admin"],
                             json=body).status_code == 403


def test_no_company_can_make_a_super_admin(client_module, auth_headers, other_company):
    out = client_module.post("/api/people", headers=other_company["admin"], json={
        "email": f"sneaky.{uuid.uuid4().hex[:6]}@beta-example.com", "full_name": "Sneaky",
        "password": PASSWORD, "role": "superadmin",
    })
    assert out.status_code == 422
    people = client_module.get("/api/people", headers=auth_headers("admin")).json()["items"]
    someone = next(p for p in people if p["role"] == "agent")
    out = client_module.patch(f"/api/people/{someone['id']}", headers=auth_headers("admin"), json={"role": "superadmin"})
    assert out.status_code == 422


def test_the_super_admins_audit_log_is_the_platforms_own(client_module, auth_headers):
    entries = client_module.get("/api/audit?size=100", headers=auth_headers("superadmin")).json()["items"]
    assert all(e["entity_type"] not in ("complaint", "document_version") for e in entries)
