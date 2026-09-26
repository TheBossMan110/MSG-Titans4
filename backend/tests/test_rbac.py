"""
Role-based access control, enforced by the API (FR ii).

Five roles, five different sets of permissions -- held by the server, not only
hidden in the menus. Each test sends the real request with the real role's
token and checks the answer.

    Customer  own complaints only; nothing internal
    Agent     their team's and their assigned complaints; reads the rules
    Reviewer  the review queue and decisions; reads the rules
    Manager   the operation: every team, analytics, reports, assignment
    Admin     everything, including users, roles, policies, rules and prompts
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from src.db.models import Complaint, Department, User

COMPLAINT = {
    "title": "Parcel not arrived",
    "description": "My parcel CN-5566778 has not arrived and the tracking page has not updated for several days now.",
    "order_ref": "CN-5566778",
}


def _complaint(client, auth_headers, db, department_code: str) -> str:
    created = client.post("/api/complaints", json=COMPLAINT, headers=auth_headers("customer"))
    assert created.status_code == 201, created.text
    ref = created.json()["public_ref"]
    row = db.execute(select(Complaint).where(Complaint.public_ref == ref)).scalar_one()
    row.department_id = db.execute(select(Department.id).where(Department.code == department_code)).scalar_one()
    row.support_department_id = None
    row.assigned_to = None
    db.commit()
    return ref


# ── what each role may open ──────────────────────────────────────
MATRIX = [
    # (method, path, {role: expected status})
    ("GET", "/api/admin/rules", {"agent": 200, "reviewer": 200, "manager": 200, "admin": 200, "customer": 403}),
    ("GET", "/api/admin/taxonomy", {"agent": 200, "reviewer": 200, "manager": 200, "admin": 200, "customer": 403}),
    ("GET", "/api/admin/sla", {"agent": 200, "reviewer": 200, "manager": 200, "admin": 200, "customer": 403}),
    ("GET", "/api/admin/prompts", {"agent": 403, "reviewer": 403, "manager": 403, "admin": 200, "customer": 403}),
    ("GET", "/api/admin/config", {"agent": 403, "reviewer": 403, "manager": 403, "admin": 200, "customer": 403}),
    ("GET", "/api/review/queue", {"agent": 403, "reviewer": 200, "manager": 200, "admin": 200, "customer": 403}),
    ("GET", "/api/review/overview", {"agent": 403, "reviewer": 200, "manager": 200, "admin": 200, "customer": 403}),
    ("GET", "/api/analytics/manager", {"agent": 403, "reviewer": 403, "manager": 200, "admin": 200, "customer": 403}),
    ("GET", "/api/analytics/dashboard", {"agent": 403, "reviewer": 403, "manager": 200, "admin": 200, "customer": 403}),
    ("GET", "/api/analytics/agent-workspace", {"agent": 200, "reviewer": 200, "manager": 200, "admin": 200, "customer": 403}),
    ("GET", "/api/people", {"agent": 403, "reviewer": 403, "manager": 200, "admin": 200, "customer": 403}),
    ("GET", "/api/audit", {"agent": 403, "reviewer": 403, "manager": 403, "admin": 200, "customer": 403}),
    ("GET", "/api/complaints", {"agent": 200, "reviewer": 200, "manager": 200, "admin": 200, "customer": 403}),
    ("GET", "/api/complaints/mine", {"customer": 200}),
]


@pytest.mark.parametrize("method,path,expected", MATRIX, ids=[f"{m} {p}" for m, p, _ in MATRIX])
def test_each_role_gets_what_the_matrix_says(client, auth_headers, method, path, expected):
    for role, code in expected.items():
        got = client.request(method, path, headers=auth_headers(role)).status_code
        assert got == code, f"{role} {method} {path}: {got}, expected {code}"


# ── changing the platform is the administrator's ─────────────────
@pytest.mark.parametrize("role", ["agent", "reviewer", "manager"])
def test_only_an_admin_changes_rules_policies_prompts_and_users(client, auth_headers, role):
    headers = auth_headers(role)
    assert client.patch("/api/admin/rules/RULE-001", json={"reason": "x"}, headers=headers).status_code == 403
    assert client.post("/api/documents", files={"files": ("p.txt", b"Document ID: X\n", "text/plain")}, headers=headers).status_code == 403
    assert client.patch("/api/admin/prompts/complaint_intelligence", json={"version": "v1.0"}, headers=headers).status_code == 403
    assert client.post("/api/people", json={"email": "x@example.com", "full_name": "X Y", "password": "long-enough", "role": "agent"},
                       headers=headers).status_code == 403


# ── agents see their team's work, not the register ───────────────
def test_an_agent_sees_their_team_and_their_assignments_only(client, auth_headers, db):
    agent = auth_headers("agent")  # Billing team
    mine = _complaint(client, auth_headers, db, "BILLING")
    other = _complaint(client, auth_headers, db, "SAFETY")

    assert client.get(f"/api/complaints/{mine}", headers=agent).status_code == 200
    # Another team's complaint answers 404, exactly like one that does not exist.
    assert client.get(f"/api/complaints/{other}", headers=agent).status_code == 404
    assert client.get(f"/api/complaints/{other}/lifecycle", headers=agent).status_code == 404
    listed = {r["public_ref"] for r in client.get("/api/complaints", params={"search": "CN-5566778", "size": 100}, headers=agent).json()["items"]}
    assert mine in listed and other not in listed

    # Once it is assigned to them, it is theirs to see.
    agent_id = db.execute(select(User.id).where(User.email == "agent.billing@raftarxpress.com")).scalar_one()
    assigned = client.post(f"/api/complaints/{other}/assign", json={"user_id": str(agent_id)}, headers=auth_headers("manager"))
    assert assigned.status_code == 200, assigned.text
    assert client.get(f"/api/complaints/{other}", headers=agent).status_code == 200


def test_reviewers_managers_and_admins_see_every_team(client, auth_headers, db):
    ref = _complaint(client, auth_headers, db, "SAFETY")
    for role in ("reviewer", "manager", "admin"):
        assert client.get(f"/api/complaints/{ref}", headers=auth_headers(role)).status_code == 200, role


def test_a_customer_never_reaches_the_internal_view(client, auth_headers, db):
    ref = _complaint(client, auth_headers, db, "BILLING")
    customer = auth_headers("customer")
    assert client.get(f"/api/complaints/{ref}", headers=customer).status_code == 403
    assert client.get(f"/api/complaints/{ref}/explain", headers=customer).status_code == 403
    # Their own complaint, through the customer-facing view.
    assert client.get(f"/api/complaints/{ref}/status", headers=customer).status_code == 200


# ── assignment ───────────────────────────────────────────────────
def test_who_may_assign_whom(client, auth_headers, db):
    ref = _complaint(client, auth_headers, db, "BILLING")
    agent_id = str(db.execute(select(User.id).where(User.email == "agent.billing@raftarxpress.com")).scalar_one())
    reviewer_id = str(db.execute(select(User.id).where(User.email == "reviewer@raftarxpress.com")).scalar_one())

    # An agent takes a complaint in their scope for themselves...
    assert client.post(f"/api/complaints/{ref}/assign", json={"user_id": agent_id}, headers=auth_headers("agent")).status_code == 200
    # ...but does not hand work to someone else.
    assert client.post(f"/api/complaints/{ref}/assign", json={"user_id": reviewer_id}, headers=auth_headers("agent")).status_code == 403
    # Managers and reviewers reassign.
    assert client.post(f"/api/complaints/{ref}/assign", json={"user_id": reviewer_id}, headers=auth_headers("manager")).status_code == 200
    assert client.post(f"/api/complaints/{ref}/assign", json={"user_id": agent_id}, headers=auth_headers("reviewer")).status_code == 200
    # Evaluators read; they do not assign. Customers cannot at all.
    assert client.post(f"/api/complaints/{ref}/assign", json={"user_id": agent_id}, headers=auth_headers("evaluator")).status_code == 403
    assert client.post(f"/api/complaints/{ref}/assign", json={"user_id": agent_id}, headers=auth_headers("customer")).status_code == 403


# ── users and roles ──────────────────────────────────────────────
def test_an_admin_creates_changes_and_disables_accounts(client, auth_headers):
    admin = auth_headers("admin")
    email = f"rbac-{uuid.uuid4().hex[:8]}@example.com"
    created = client.post("/api/people", json={
        "email": email, "full_name": "Rida Agent", "password": "a-long-password", "role": "agent", "department_code": "BILLING",
    }, headers=admin)
    assert created.status_code == 201, created.text
    person = created.json()
    assert person["role"] == "agent" and person["department"]

    token = client.post("/api/auth/login", json={"email": email, "password": "a-long-password"}).json()["access_token"]
    as_them = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/review/queue", headers=as_them).status_code == 403

    # Promoted to reviewer: the old token stops working at once; a new sign-in carries the new role.
    changed = client.patch(f"/api/people/{person['id']}", json={"role": "reviewer"}, headers=admin)
    assert changed.status_code == 200 and changed.json()["role"] == "reviewer"
    assert client.get("/api/auth/me", headers=as_them).status_code == 401
    token = client.post("/api/auth/login", json={"email": email, "password": "a-long-password"}).json()["access_token"]
    assert client.get("/api/review/queue", headers={"Authorization": f"Bearer {token}"}).status_code == 200

    # Disabled: cannot sign in.
    assert client.patch(f"/api/people/{person['id']}", json={"is_active": False}, headers=admin).status_code == 200
    assert client.post("/api/auth/login", json={"email": email, "password": "a-long-password"}).status_code in (401, 403)

    assert client.post("/api/people", json={
        "email": email, "full_name": "Again", "password": "a-long-password", "role": "agent",
    }, headers=admin).status_code == 409


def test_an_admin_cannot_lock_themselves_out(client, auth_headers, db):
    admin_id = str(db.execute(select(User.id).where(User.email == "admin@raftarxpress.com")).scalar_one())
    headers = auth_headers("admin")
    assert client.patch(f"/api/people/{admin_id}", json={"role": "agent"}, headers=headers).status_code == 422
    assert client.patch(f"/api/people/{admin_id}", json={"is_active": False}, headers=headers).status_code == 422


def test_an_unknown_role_is_refused(client, auth_headers):
    out = client.post("/api/people", json={
        "email": f"x-{uuid.uuid4().hex[:6]}@example.com", "full_name": "X Y", "password": "a-long-password", "role": "superuser",
    }, headers=auth_headers("admin"))
    assert out.status_code == 422


# ── each role's dashboard data ───────────────────────────────────
def test_the_manager_dashboard_has_the_operation(client, auth_headers):
    body = client.get("/api/analytics/manager", headers=auth_headers("manager")).json()
    assert {"today", "teams", "agents", "critical", "escalations", "sla_risks"} <= set(body)
    assert {"total", "open", "in_progress", "escalated", "sla_at_risk", "critical", "manual_review"} <= set(body["today"])
    one_team = client.get("/api/analytics/manager", params={"department": "BILLING"}, headers=auth_headers("manager")).json()
    assert one_team["department"] == "BILLING"


def test_the_reviewer_dashboard_groups_the_queue(client, auth_headers):
    body = client.get("/api/review/overview", headers=auth_headers("reviewer")).json()
    assert [g["key"] for g in body["groups"]] == ["disagreement", "policy", "escalation", "adversarial", "validation", "ambiguous"]
    assert {"open", "claimed_by_me", "history", "totals"} <= set(body)


def test_an_agent_sees_their_own_performance(client, auth_headers):
    body = client.get("/api/analytics/agent-workspace", headers=auth_headers("agent")).json()
    assert {"assigned_open", "resolved_total", "avg_resolution_hours"} <= set(body["performance"])
