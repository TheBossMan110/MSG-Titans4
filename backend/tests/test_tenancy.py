"""
Multi-company: a company signs up, runs its own complaint desk, and neither it
nor RaftarXpress can see, count or change the other's data -- and its
administrator decides what each of its roles may do.

The isolation tests deliberately go through ordinary endpoints written before
organisations existed, none of which filter by organisation themselves: the
point of src/core/tenancy.py is that they do not have to.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import delete, select

from src.core import tenancy
from src.db.base import DEFAULT_ORGANISATION_ID, Base, TenantScoped
from src.db.models import AuditLog, Complaint, Department, Organisation, User

PASSWORD = "Correct-Horse-Battery-9"
COMPLAINT = {
    "title": "Parcel CN-77120045 never arrived",
    "description": "My parcel CN-77120045 was due on Monday and has not arrived. Tracking has not moved for four days.",
}


def _login(client, email: str, password: str = PASSWORD) -> dict[str, str]:
    out = client.post("/api/auth/login", json={"email": email, "password": password})
    assert out.status_code == 200, out.text
    return {"Authorization": f"Bearer {out.json()['access_token']}"}


@pytest.fixture(scope="module")
def company(client_module):
    """A second company, created by the super administrator, removed afterwards."""
    tag = uuid.uuid4().hex[:6]
    body = {
        "company_name": f"Acme Couriers {tag}", "industry": "Logistics",
        "admin_full_name": "Ayesha Khan", "admin_email": f"ayesha.{tag}@acme-example.com",
        "admin_password": PASSWORD,
    }
    super_admin = _login(client_module, "superadmin@supportnova.com", "SupportNova#2026")
    out = client_module.post("/api/company/create", headers=super_admin, json=body)
    assert out.status_code == 201, out.text
    created = out.json()
    organisation_id = uuid.UUID(created["company"]["id"])
    yield {
        "id": organisation_id, "tag": tag, "name": body["company_name"],
        "admin_email": body["admin_email"],
        # The administrator signs in with the details the super administrator handed over.
        "admin": _login(client_module, body["admin_email"]),
        "created": created, "super_admin": super_admin,
    }
    _purge(organisation_id)


@pytest.fixture(scope="module")
def client_module():
    from fastapi.testclient import TestClient

    from src.main import app

    with TestClient(app) as c:
        yield c


def _purge(organisation_id: uuid.UUID) -> None:
    """Every row the company wrote, children first, then the company."""
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


def _staff(client, company, role: str, department_code: str | None = None) -> dict[str, str]:
    email = f"{role}.{company['tag']}.{uuid.uuid4().hex[:4]}@acme-example.com"
    out = client.post("/api/people", headers=company["admin"], json={
        "email": email, "full_name": f"Acme {role.title()}", "password": PASSWORD,
        "role": role, "department_code": department_code,
    })
    assert out.status_code == 201, out.text
    return _login(client, email)


def _access(client, company, **policy):
    out = client.put("/api/company/access", headers=company["admin"], json=policy)
    assert out.status_code == 200, out.text
    return out.json()


# ══════════════════════════════════════════════════════════════
# creating a company
# ══════════════════════════════════════════════════════════════
def test_the_super_admin_creates_a_company_and_its_administrator(client_module, company, db):
    created = company["created"]
    assert created["company"]["name"] == company["name"] and created["company"]["is_active"]
    assert created["admin_email"] == company["admin_email"] and created["sign_in_path"] == "/login"
    assert "password" not in str(created).lower(), "the password is never echoed back"
    me = client_module.get("/api/auth/me", headers=company["admin"]).json()
    assert me["role"] == "admin" and me["organisation"]["name"] == company["name"]
    assert me["organisation"]["is_platform"] is False
    assert "documents.manage" in me["permissions"], "an administrator holds every permission"

    row = db.execute(select(User).where(User.email == company["admin_email"])).scalar_one()
    assert row.organisation_id == company["id"]
    assert db.execute(select(AuditLog).where(
        AuditLog.action == "COMPANY_CREATED", AuditLog.organisation_id == company["id"],
    )).scalars().first() is not None, "the company's own log says the platform created it"


def test_a_company_name_and_an_admin_email_are_taken_once(client_module, company):
    body = {"company_name": company["name"].upper(), "admin_full_name": "Someone Else",
            "admin_email": f"other.{company['tag']}@acme-example.com", "admin_password": PASSWORD}
    assert client_module.post("/api/company/create", headers=company["super_admin"], json=body).status_code == 409
    body.update(company_name=f"Another {company['tag']}", admin_email="admin@raftarxpress.com")
    assert client_module.post("/api/company/create", headers=company["super_admin"], json=body).status_code == 409


def test_companies_cannot_sign_themselves_up(client_module, company, auth_headers):
    body = {"company_name": f"Rogue {company['tag']}", "admin_full_name": "Rogue",
            "admin_email": f"rogue.{company['tag']}@rogue-example.com", "admin_password": PASSWORD}
    # The open sign-up is gone...
    assert client_module.post("/api/company/signup", json=body).status_code in (404, 405)
    # ...and only the super administrator creates companies.
    assert client_module.post("/api/company/create", json=body).status_code == 401
    for headers in (company["admin"], auth_headers("admin"), auth_headers("evaluator")):
        assert client_module.post("/api/company/create", headers=headers, json=body).status_code == 403


def test_me_names_the_company(client_module, company):
    me = client_module.get("/api/auth/me", headers=company["admin"]).json()
    assert me["organisation"]["slug"].startswith("acme-couriers")
    assert me["complaint_scope"] == "all"


# ══════════════════════════════════════════════════════════════
# isolation
# ══════════════════════════════════════════════════════════════
def test_a_new_company_starts_empty(client_module, company):
    headers = company["admin"]
    assert client_module.get("/api/complaints", headers=headers).json()["total"] == 0
    assert client_module.get("/api/documents", headers=headers).json()["total"] == 0
    people = client_module.get("/api/people", headers=headers).json()
    assert [p["email"] for p in people["items"]] == [company["admin_email"]]
    dashboard = client_module.get("/api/analytics/dashboard", headers=headers)
    assert dashboard.status_code == 200, dashboard.text
    org = client_module.get("/api/organisation", headers=headers).json()
    assert org["profile"]["name"] == company["name"]


def test_neither_company_sees_the_others_complaints(client_module, company, auth_headers):
    raftar_admin = auth_headers("admin")
    raftar_total = client_module.get("/api/complaints", headers=raftar_admin).json()["total"]

    created = client_module.post("/api/complaints?analyse=false", headers=company["admin"], json=COMPLAINT)
    assert created.status_code == 201, created.text
    ref = created.json()["public_ref"]

    mine = client_module.get("/api/complaints", headers=company["admin"]).json()
    assert [c["public_ref"] for c in mine["items"]] == [ref]
    assert client_module.get(f"/api/complaints/{ref}", headers=company["admin"]).status_code == 200

    # RaftarXpress: not in the register, not countable, not openable by reference.
    assert client_module.get("/api/complaints", headers=raftar_admin).json()["total"] == raftar_total
    assert client_module.get(f"/api/complaints/{ref}", headers=raftar_admin).status_code == 404
    # ...and the other way round.
    theirs = client_module.get("/api/complaints?size=1", headers=raftar_admin).json()["items"]
    if theirs:
        assert client_module.get(f"/api/complaints/{theirs[0]['public_ref']}", headers=company["admin"]).status_code == 404


def test_references_stay_unique_across_companies(client_module, company, auth_headers, db):
    a = client_module.post("/api/complaints?analyse=false", headers=company["admin"], json=COMPLAINT).json()["public_ref"]
    b = client_module.post("/api/complaints?analyse=false", headers=auth_headers("customer"), json=COMPLAINT).json()["public_ref"]
    assert a != b
    owners = dict(db.execute(select(Complaint.public_ref, Complaint.organisation_id).where(Complaint.public_ref.in_((a, b)))).all())
    assert owners[a] == company["id"] and owners[b] == DEFAULT_ORGANISATION_ID


def test_a_gap_in_the_sequence_never_reissues_a_reference(client_module, company, db):
    """
    Once the highest reference is above the row count -- complaints deleted
    from the middle, as a dataset ``replace`` does -- count + 1 would hand out
    a number already taken and the submission would fail.
    """
    ref = client_module.post("/api/complaints?analyse=false", headers=company["admin"], json=COMPLAINT).json()["public_ref"]
    row = db.execute(select(Complaint).where(Complaint.public_ref == ref)).scalar_one()
    high = 900000 + uuid.uuid4().int % 9999
    row.public_ref = f"CMP-{high:06d}"
    db.commit()
    nxt = client_module.post("/api/complaints?analyse=false", headers=company["admin"], json=COMPLAINT)
    assert nxt.status_code == 201, nxt.text
    assert int(nxt.json()["public_ref"].split("-")[1]) > high


def test_cached_dashboards_are_never_shared(client_module, company, auth_headers):
    """The response cache keyed by endpoint alone would hand one company the other's numbers."""
    raftar = client_module.get("/api/analytics/volume", headers=auth_headers("admin")).json()
    acme = client_module.get("/api/analytics/volume", headers=company["admin"]).json()
    assert raftar != acme


def test_the_same_policy_file_can_belong_to_both_companies(client_module, company, auth_headers, sample_documents_dir, db):
    """Duplicate detection, and the unique keys behind it, are per company (migration 0006)."""
    from src.db.models import (
        Chunk,
        Document,
        DocumentSection,
        DocumentValidationIssue,
        DocumentVersion,
    )

    path = sample_documents_dir("DOC-001_v2.0.pdf")
    upload = lambda headers: client_module.post(  # noqa: E731
        "/api/documents", headers=headers, files={"files": (path.name, path.read_bytes(), "application/pdf")},
    ).json()
    raftar = auth_headers("admin")
    raftar_before = client_module.get("/api/documents", headers=raftar).json()["total"]
    try:
        assert upload(raftar)["rejected"] in (0, 1)   # it may already be there from another test
        first = upload(company["admin"])
        assert first["accepted"] == 1, first
        assert upload(company["admin"])["accepted"] == 0, "within one company it is a duplicate"
        assert client_module.get("/api/documents", headers=company["admin"]).json()["total"] == 1
    finally:
        # Leave RaftarXpress's library as the test found it.
        if raftar_before == 0:
            for model in (Chunk, DocumentSection, DocumentValidationIssue, DocumentVersion, Document):
                db.execute(delete(model).where(model.organisation_id == DEFAULT_ORGANISATION_ID))
            db.commit()


def test_people_of_another_company_cannot_be_opened_or_changed(client_module, company, db):
    raftar_admin_id = db.execute(select(User.id).where(User.email == "admin@raftarxpress.com")).scalar_one()
    assert client_module.get(f"/api/people/{raftar_admin_id}", headers=company["admin"]).status_code == 404
    out = client_module.patch(f"/api/people/{raftar_admin_id}", headers=company["admin"], json={"is_active": False})
    assert out.status_code == 404


def test_customers_join_a_company_through_its_link(client_module, company, db):
    slug = client_module.get("/api/company", headers=company["admin"]).json()["slug"]
    public = client_module.get(f"/api/company/public/{slug}")
    assert public.status_code == 200 and public.json() == {"name": company["name"], "industry": "Logistics", "slug": slug}
    assert client_module.get("/api/company/public/no-such-company").status_code == 404
    email = f"customer.{company['tag']}@acme-example.com"
    out = client_module.post("/api/auth/register", json={
        "email": email, "full_name": "Acme Customer", "password": PASSWORD, "company": slug,
    })
    assert out.status_code == 201, out.text
    assert out.json()["user"]["role"] == "customer"
    assert db.execute(select(User.organisation_id).where(User.email == email)).scalar_one() == company["id"]

    bad = client_module.post("/api/auth/register", json={
        "email": f"x.{company['tag']}@acme-example.com", "full_name": "Nobody", "password": PASSWORD, "company": "no-such-company",
    })
    assert bad.status_code == 404


# ══════════════════════════════════════════════════════════════
# the shared template
# ══════════════════════════════════════════════════════════════
@pytest.mark.parametrize("method,path,body", [
    ("PUT", "/api/admin/config/thresholds", {"value": {}, "reason": "x"}),
    ("POST", "/api/admin/rules/reload", None),
    ("POST", "/api/organisation/departments", {"code": "ACME_OPS", "name": "Acme Ops"}),
])
def test_another_company_cannot_change_shared_configuration(client_module, company, method, path, body):
    out = client_module.request(method, path, headers=company["admin"], json=body)
    assert out.status_code == 403, out.text
    assert out.json()["error"]["details"]["platform_only"] is True


def test_another_company_cannot_mint_evaluators(client_module, company):
    out = client_module.post("/api/people", headers=company["admin"], json={
        "email": f"judge.{company['tag']}@acme-example.com", "full_name": "Judge", "password": PASSWORD, "role": "evaluator",
    })
    assert out.status_code == 422


# ══════════════════════════════════════════════════════════════
# the access matrix
# ══════════════════════════════════════════════════════════════
def test_the_defaults_are_the_old_role_gates(client_module, company):
    body = client_module.get("/api/company", headers=company["admin"]).json()
    assert body["access"] == body["defaults"]
    assert "analytics.view" in body["access"]["permissions"]["manager"]
    assert body["access"]["complaint_scope"]["agent"] == "team"
    assert body["customer_signup_path"].startswith("/register?company=")


def test_granting_a_permission_opens_the_route(client_module, company, sample_documents_dir):
    manager = _staff(client_module, company, "manager", "BILLING")
    path = sample_documents_dir("DOC-002_v1.0.docx")
    upload = lambda: client_module.post(  # noqa: E731
        "/api/documents", headers=manager,
        files={"files": (path.name, path.read_bytes(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )
    refused = upload()
    assert refused.status_code == 403
    assert refused.json()["error"]["details"]["required_permission"] == "documents.manage"

    defaults = client_module.get("/api/company", headers=company["admin"]).json()["defaults"]
    _access(client_module, company, permissions={"manager": [*defaults["permissions"]["manager"], "documents.manage"]})
    assert upload().status_code == 201
    assert "documents.manage" in client_module.get("/api/auth/me", headers=manager).json()["permissions"]


def test_revoking_a_permission_closes_the_route(client_module, company):
    manager = _staff(client_module, company, "manager", "BILLING")
    assert client_module.get("/api/analytics/volume", headers=manager).status_code == 200
    _access(client_module, company, permissions={"manager": ["review.queue"]})
    assert client_module.get("/api/analytics/volume", headers=manager).status_code == 403
    # An administrator can never lose a permission.
    assert client_module.get("/api/analytics/volume", headers=company["admin"]).status_code == 200
    _access(client_module, company, permissions={"manager": client_module.get(
        "/api/company", headers=company["admin"]).json()["defaults"]["permissions"]["manager"]})


def test_the_data_scope_decides_what_an_agent_sees(client_module, company, db):
    agent = _staff(client_module, company, "agent", "BILLING")
    agent_id = client_module.get("/api/auth/me", headers=agent).json()["id"]
    ref = client_module.post("/api/complaints?analyse=false", headers=company["admin"], json=COMPLAINT).json()["public_ref"]
    row = db.execute(select(Complaint).where(Complaint.public_ref == ref)).scalar_one()
    row.department_id = db.execute(select(Department.id).where(Department.code == "BILLING")).scalar_one()
    row.assigned_to = None
    db.commit()

    visible = lambda: {c["public_ref"] for c in client_module.get("/api/complaints?size=100", headers=agent).json()["items"]}  # noqa: E731
    assert ref in visible(), "team scope: the team's complaints"

    _access(client_module, company, complaint_scope={"agent": "assigned"})
    assert ref not in visible(), "assigned scope: only what is assigned to them"
    assert client_module.get(f"/api/complaints/{ref}", headers=agent).status_code == 404

    row = db.execute(select(Complaint).where(Complaint.public_ref == ref)).scalar_one()
    row.assigned_to = uuid.UUID(agent_id)
    db.commit()
    assert ref in visible()
    _access(client_module, company, complaint_scope={"agent": "team"})


def test_a_policy_change_is_validated_and_audited(client_module, company, db):
    bad = client_module.put("/api/company/access", headers=company["admin"],
                            json={"permissions": {"manager": ["rules.rewrite"]}, "complaint_scope": {"agent": "everything"}})
    assert bad.status_code == 422
    assert len(bad.json()["error"]["details"]["problems"]) == 2
    assert client_module.put("/api/company/access", headers=company["admin"],
                             json={"permissions": {"admin": []}}).status_code == 422

    _access(client_module, company, complaint_scope={"reviewer": "team"})
    entry = db.execute(select(AuditLog).where(
        AuditLog.action == "ACCESS_POLICY_UPDATED", AuditLog.organisation_id == company["id"],
    ).order_by(AuditLog.id.desc())).scalars().first()
    assert entry.before["complaint_scope"]["reviewer"] == "all"
    assert entry.after["complaint_scope"]["reviewer"] == "team"
    _access(client_module, company, complaint_scope={"reviewer": "all"})


def test_only_an_administrator_sets_access(client_module, company):
    manager = _staff(client_module, company, "manager", "BILLING")
    assert client_module.put("/api/company/access", headers=manager, json={}).status_code == 403


# ══════════════════════════════════════════════════════════════
# the filter itself
# ══════════════════════════════════════════════════════════════
def test_every_business_table_is_scoped():
    """A new business table that forgot the mixin would be readable by every company."""
    shared = {
        "organisations", "refresh_tokens", "rules", "lexicon_terms", "injection_patterns", "promise_patterns",
        "departments", "categories", "subcategories", "priority_levels", "escalation_levels", "sla_policies",
        "app_config", "prompt_versions", "llm_cache",
    }
    unscoped = {t.name for t in Base.metadata.sorted_tables if "organisation_id" not in t.c} - shared
    assert not unscoped, f"tables without organisation_id: {sorted(unscoped)}"


def test_an_unbound_session_writes_to_the_parent_rows_company(db, company):
    """A background job with no user behind it still files a complaint's rows under the complaint's company."""
    from src.db.models import ComplaintStatusHistory

    complaint = db.execute(select(Complaint).where(Complaint.organisation_id == company["id"])).scalars().first()
    assert complaint is not None
    entry = ComplaintStatusHistory(complaint_id=complaint.id, from_status=None, to_status=complaint.status, reason="test")
    db.add(entry)
    db.flush()
    assert entry.organisation_id == company["id"]
    db.rollback()


def test_a_bound_session_cannot_read_another_company(db, company):
    tenancy.bind(db, company["id"])
    try:
        assert db.execute(select(User).where(User.email == "admin@raftarxpress.com")).scalar_one_or_none() is None
        assert all(isinstance(u, TenantScoped) and u.organisation_id == company["id"]
                   for u in db.execute(select(User)).scalars())
    finally:
        tenancy.bind(db, None)


# ══════════════════════════════════════════════════════════════
# the super administrator's view of every company
# ══════════════════════════════════════════════════════════════
def test_the_super_admin_lists_every_company(client_module, company, auth_headers):
    body = client_module.get("/api/company/all", headers=auth_headers("superadmin"))
    assert body.status_code == 200, body.text
    body = body.json()
    assert body["total"] == len(body["items"]) == body["active"] + body["suspended"]
    acme = next(r for r in body["items"] if r["id"] == str(company["id"]))
    assert acme["name"] == company["name"] and acme["is_active"] and not acme["is_reference"]
    assert acme["administrator"] == company["admin_email"] and acme["staff"] >= 1
    reference = next(r for r in body["items"] if r["is_reference"])
    assert reference["staff"] >= 5, "counts cross companies: RaftarXpress's staff are counted, not the caller's"
    assert all(r["name"] != "SupportNova Platform" for r in body["items"]), "the platform is not a company"


@pytest.mark.parametrize("who", ["company admin", "raftarxpress admin", "evaluator", "manager"])
def test_only_the_super_admin_sees_every_company(client_module, company, auth_headers, who):
    headers = company["admin"] if who == "company admin" else auth_headers(
        {"raftarxpress admin": "admin", "evaluator": "evaluator", "manager": "manager"}[who])
    out = client_module.get("/api/company/all", headers=headers)
    assert out.status_code == 403
    assert out.json()["error"]["details"]["platform_only"] is True


def test_a_suspended_company_is_locked_out_until_reactivated(client_module, company, auth_headers):
    path = f"/api/company/{company['id']}/status"
    for who in ("evaluator", "admin"):
        assert client_module.patch(path, headers=auth_headers(who), json={"is_active": False}).status_code == 403
    assert client_module.patch(path, headers=company["admin"], json={"is_active": False}).status_code == 403

    super_admin = auth_headers("superadmin")
    out = client_module.patch(path, headers=super_admin, json={"is_active": False, "reason": "test"})
    assert out.status_code == 200, out.text
    assert out.json()["is_active"] is False
    try:
        me = client_module.get("/api/auth/me", headers=company["admin"])
        assert me.status_code == 401 and me.json()["error"]["code"] == "ORGANISATION_SUSPENDED"
        login = client_module.post("/api/auth/login", json={"email": company["admin_email"], "password": PASSWORD})
        assert login.status_code == 401 and login.json()["error"]["code"] == "ORGANISATION_SUSPENDED"
    finally:
        back = client_module.patch(path, headers=super_admin, json={"is_active": True})
        assert back.status_code == 200 and back.json()["is_active"] is True
    assert client_module.get("/api/auth/me", headers=company["admin"]).status_code == 200


def test_the_reference_company_and_the_platform_cannot_be_suspended(client_module, auth_headers):
    from src.db.base import PLATFORM_ORGANISATION_ID

    super_admin = auth_headers("superadmin")
    out = client_module.patch(f"/api/company/{DEFAULT_ORGANISATION_ID}/status", headers=super_admin,
                              json={"is_active": False})
    assert out.status_code == 422, "RaftarXpress holds the template and the evaluation accounts"
    out = client_module.patch(f"/api/company/{PLATFORM_ORGANISATION_ID}/status", headers=super_admin,
                              json={"is_active": False})
    assert out.status_code == 404, "the platform is not a company"
