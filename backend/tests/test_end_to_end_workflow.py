"""
The whole journey, in order, as one company lives it.

    super administrator creates a company and its administrator
    -> the administrator creates a manager, a reviewer and an agent
    -> a customer signs up on the company's link and files a complaint
    -> it reaches the agent, the reviewer and the manager
    -> the agent works it, and everyone sees the change
    -> another company sees none of it

The defect behind this file: a new complaint appeared only on the
administrator's dashboard, because every other view listed the oldest or most
urgent cases first and stopped at a page's worth.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from src.core import tenancy
from src.db.base import Base, SessionLocal
from src.db.models import Complaint, Department, Organisation

PASSWORD = "Correct-Horse-Battery-9"
COMPLAINT = {
    "title": "Charged twice for one delivery",
    "description": "My invoice shows the delivery charge twice for consignment CN-55120045 and I need the billing corrected.",
}


@pytest.fixture(scope="module")
def world():
    from src.main import app

    with TestClient(app) as client:
        tag = uuid.uuid4().hex[:6]

        def sign_in(email: str, password: str = PASSWORD) -> dict[str, str]:
            out = client.post("/api/auth/login", json={"email": email, "password": password})
            assert out.status_code == 200, out.text
            return {"Authorization": f"Bearer {out.json()['access_token']}"}

        def make_company(name: str, admin_email: str) -> dict:
            out = client.post("/api/company/create", headers=superadmin, json={
                "company_name": name, "industry": "Courier", "admin_full_name": "First Admin",
                "admin_email": admin_email, "admin_password": PASSWORD,
            })
            assert out.status_code == 201, out.text
            return out.json()

        superadmin = sign_in("superadmin@supportnova.com", "SupportNova#2026")
        made = make_company(f"Delta Couriers {tag}", f"admin.{tag}@delta-example.com")
        rival = make_company(f"Rival Couriers {tag}", f"admin.{tag}@rival-example.com")
        people = {
            "client": client, "tag": tag, "sign_in": sign_in, "superadmin": superadmin, "company": made["company"],
            "admin": sign_in(f"admin.{tag}@delta-example.com"),
            "rival_admin": sign_in(f"admin.{tag}@rival-example.com"),
            "slug": made["company"]["slug"], "emails": {},
        }
        yield people

    db = SessionLocal()
    try:
        for org_id in (uuid.UUID(made["company"]["id"]), uuid.UUID(rival["company"]["id"])):
            for table in reversed(Base.metadata.sorted_tables):
                if "organisation_id" in table.c and table.name != "organisations":
                    db.execute(delete(table).where(table.c.organisation_id == org_id))
            db.execute(delete(Organisation).where(Organisation.id == org_id))
            tenancy.forget(org_id)
        db.commit()
    finally:
        db.close()


def _create(world, role: str, department: str | None, headers=None) -> str:
    email = f"{role}.{world['tag']}@delta-example.com"
    out = world["client"].post("/api/people", headers=headers or world["admin"], json={
        "email": email, "full_name": f"{role.title()} Person", "password": PASSWORD,
        "role": role, "department_code": department,
    })
    assert out.status_code == 201, out.text
    assert out.json()["role"] == role
    world["emails"][role] = email
    return email


@pytest.fixture(scope="module")
def staffed(world):
    """The administrator creates each role, then a customer joins on the company's link."""
    _create(world, "manager", "CUSTOMER_RELATIONS")
    _create(world, "reviewer", "COMPLIANCE")
    _create(world, "agent", "BILLING")
    customer = f"customer.{world['tag']}@delta-example.com"
    joined = world["client"].post("/api/auth/register", json={
        "email": customer, "full_name": "Real Customer", "password": PASSWORD, "company": world["slug"],
    })
    assert joined.status_code in (200, 201), joined.text
    for role in ("manager", "reviewer", "agent"):
        world[role] = world["sign_in"](world["emails"][role])
    world["customer"] = world["sign_in"](customer)
    return world


@pytest.fixture(scope="module")
def filed(staffed):
    out = staffed["client"].post("/api/complaints", headers=staffed["customer"], json=COMPLAINT)
    assert out.status_code == 201, out.text
    staffed["ref"] = out.json()["public_ref"]
    return staffed


class TestSettingUpACompany:
    def test_the_company_admin_runs_only_their_company(self, staffed):
        me = staffed["client"].get("/api/auth/me", headers=staffed["admin"]).json()
        assert me["role"] == "admin" and me["organisation"]["slug"] == staffed["slug"]

    def test_the_admin_can_create_every_staff_role(self, staffed):
        people = staffed["client"].get("/api/people?page_size=100", headers=staffed["admin"]).json()
        assert {"manager", "reviewer", "agent"} <= {p["role"] for p in people["items"]}

    def test_a_manager_may_add_agents_but_nothing_higher(self, staffed):
        client = staffed["client"]
        manager = staffed["manager"]
        out = client.post("/api/people", headers=manager, json={
            "email": f"boss.{staffed['tag']}@delta-example.com", "full_name": "Would Be Admin",
            "password": PASSWORD, "role": "admin",
        })
        assert out.status_code == 422, out.text

    def test_nobody_else_can_create_a_company(self, staffed):
        out = staffed["client"].post("/api/company/create", headers=staffed["admin"], json={
            "company_name": "Sneaky Ltd", "admin_full_name": "Mr Sneaky",
            "admin_email": "sneaky@example.com", "admin_password": PASSWORD,
        })
        assert out.status_code == 403

    def test_a_short_staff_password_is_refused(self, staffed):
        out = staffed["client"].post("/api/people", headers=staffed["admin"], json={
            "email": f"weak.{staffed['tag']}@delta-example.com", "full_name": "Weak Password",
            "password": "short123", "role": "agent",
        })
        assert out.status_code == 422


class TestANewComplaintReachesEveryone:
    def test_it_is_handed_to_an_agent(self, filed, db):
        row = db.execute(select(Complaint).where(Complaint.public_ref == filed["ref"])).scalars().one()
        assert row.assigned_to is not None

    def test_it_is_on_the_agents_dashboard(self, filed):
        body = filed["client"].get("/api/analytics/agent-workspace", headers=filed["agent"]).json()
        found = next(c for c in body["complaints"] if c["public_ref"] == filed["ref"])
        assert found["assigned_to_me"] is True and found["is_new"] is True

    def test_it_is_on_the_managers_dashboard(self, filed):
        body = filed["client"].get("/api/analytics/manager", headers=filed["manager"]).json()
        assert filed["ref"] in [c["public_ref"] for c in body["latest"]]

    def test_it_is_on_the_reviewers_dashboard(self, filed):
        body = filed["client"].get("/api/review/overview", headers=filed["reviewer"]).json()
        assert filed["ref"] in [c["public_ref"] for c in body["latest"]]

    def test_it_is_on_the_admins_dashboard(self, filed):
        body = filed["client"].get("/api/complaints?size=6", headers=filed["admin"]).json()
        assert filed["ref"] in [c["public_ref"] for c in body["items"]]

    def test_the_agent_sees_a_real_percentage(self, filed, db):
        from src.db.models import VerificationDecision

        row = db.execute(select(Complaint).where(Complaint.public_ref == filed["ref"])).scalars().one()
        decision = db.execute(select(VerificationDecision).where(VerificationDecision.complaint_id == row.id)).scalars().first()
        decision.agreement_score = 57.14
        db.commit()
        from src.core import response_cache

        response_cache.clear()
        body = filed["client"].get("/api/analytics/agent-workspace", headers=filed["agent"]).json()
        found = next(c for c in body["complaints"] if c["public_ref"] == filed["ref"])
        assert found["validation"]["agreement_pct"] == pytest.approx(57.14), "it was once shown as 5714%"

    def test_it_says_who_has_it(self, filed):
        body = filed["client"].get("/api/analytics/manager", headers=filed["manager"]).json()
        row = next(c for c in body["latest"] if c["public_ref"] == filed["ref"])
        assert row["assignee"] == "Agent Person"


class TestABusyTeamStillSeesNewWork:
    """Sixty old urgent cases: the situation on the live site, where the new one fell off the end."""

    @pytest.fixture(scope="class")
    def crowded(self, filed):
        db = SessionLocal()
        try:
            organisation = uuid.UUID(filed["company"]["id"])
            billing = db.execute(select(Department).where(Department.code == "BILLING")).scalars().one()
            old = datetime.now(UTC) - timedelta(days=30)
            for i in range(60):
                db.add(Complaint(
                    public_ref=f"CMP-8{filed['tag'][:2]}{i:03d}".upper(), title=f"Older case {i}",
                    description_raw="An older complaint still open.", description_clean="An older complaint still open.",
                    status="VALIDATED", priority_code="P0", department_id=billing.id, analyzed_at=old, created_at=old,
                    channel="WEB", organisation_id=organisation,
                ))
            db.commit()
        finally:
            db.close()
        out = filed["client"].post("/api/complaints", headers=filed["customer"], json={
            "title": "A newer billing problem",
            "description": "Another wrong COD amount was deducted from my account for consignment CN-99120045 this morning.",
        })
        assert out.status_code == 201, out.text
        filed["newer"] = out.json()["public_ref"]
        return filed

    def test_the_agent_queue(self, crowded):
        body = crowded["client"].get("/api/analytics/agent-workspace", headers=crowded["agent"]).json()
        assert crowded["newer"] in [c["public_ref"] for c in body["complaints"]]

    def test_urgent_older_work_is_not_pushed_out(self, crowded):
        body = crowded["client"].get("/api/analytics/agent-workspace", headers=crowded["agent"]).json()
        assert any(c["title"].startswith("Older case") for c in body["complaints"])

    def test_the_manager_list(self, crowded):
        body = crowded["client"].get("/api/analytics/manager", headers=crowded["manager"]).json()
        assert body["latest"][0]["public_ref"] == crowded["newer"]

    def test_the_reviewer_list(self, crowded):
        body = crowded["client"].get("/api/review/overview", headers=crowded["reviewer"]).json()
        assert body["latest"][0]["public_ref"] == crowded["newer"]

    def test_the_review_queue_can_show_newest_first(self, crowded):
        body = crowded["client"].get("/api/review/queue?size=50&sort=newest", headers=crowded["reviewer"]).json()
        if body["items"]:
            assert body["items"][0]["created_at"] >= body["items"][-1]["created_at"]


class TestWorkOnItIsSeenByEveryone:
    def test_taking_it_moves_the_pulse(self, filed):
        client = filed["client"]
        before = client.get("/api/live/pulse", headers=filed["manager"]).json()
        me = client.get("/api/auth/me", headers=filed["agent"]).json()["id"]
        out = client.post(f"/api/complaints/{filed['ref']}/assign", headers=filed["agent"], json={"user_id": me})
        assert out.status_code == 200, out.text
        after = client.get("/api/live/pulse", headers=filed["manager"]).json()
        assert after["work_changes"] > before["work_changes"], "other dashboards must learn something changed"

    def test_a_status_change_reaches_the_manager_and_the_customer(self, filed):
        client = filed["client"]
        current = client.get(f"/api/complaints/{filed['ref']}/lifecycle", headers=filed["agent"]).json()
        target = "ASSIGNED" if "ASSIGNED" in current["available_actions"] else current["available_actions"][0]
        moved = client.post(f"/api/complaints/{filed['ref']}/status", headers=filed["agent"], json={"to_status": target, "reason": "Working on it."})
        assert moved.status_code == 200, moved.text

        body = client.get("/api/analytics/manager", headers=filed["manager"]).json()
        row = next(c for c in body["latest"] if c["public_ref"] == filed["ref"])
        assert row["status"] == target

        seen = client.get(f"/api/complaints/{filed['ref']}/status", headers=filed["customer"])
        assert seen.status_code == 200, seen.text

    def test_a_review_decision_moves_the_pulse(self, filed):
        client = filed["client"]
        before = client.get("/api/live/pulse", headers=filed["manager"]).json()
        out = client.post(f"/api/review/{filed['ref']}/actions", headers=filed["reviewer"], json={"action": "COMMENT", "comment": "Looks right."})
        assert out.status_code == 201, out.text
        after = client.get("/api/live/pulse", headers=filed["manager"]).json()
        assert after["work_changes"] > before["work_changes"]


class TestCompaniesAreSeparate:
    def test_another_company_cannot_open_it(self, filed):
        out = filed["client"].get(f"/api/complaints/{filed['ref']}", headers=filed["rival_admin"])
        assert out.status_code == 404

    def test_another_company_does_not_list_it(self, filed):
        body = filed["client"].get("/api/complaints?size=100", headers=filed["rival_admin"]).json()
        assert filed["ref"] not in [c["public_ref"] for c in body["items"]]

    def test_an_agent_is_never_taken_from_another_company(self, filed, db):
        from src.db.models import User

        row = db.execute(select(Complaint).where(Complaint.public_ref == filed["ref"])).scalars().one()
        owner = db.get(User, row.assigned_to)
        assert owner.organisation_id == row.organisation_id


class TestStaffPrivacy:
    def test_an_agent_cannot_open_a_colleagues_account(self, filed):
        client = filed["client"]
        people = client.get("/api/people?role=manager", headers=filed["admin"]).json()
        target = people["items"][0]["id"]
        assert client.get(f"/api/people/{target}", headers=filed["agent"]).status_code == 404

    def test_an_agent_sees_a_customer_but_not_their_sign_ins(self, filed):
        client = filed["client"]
        people = client.get("/api/people?role=customer", headers=filed["admin"]).json()
        out = client.get(f"/api/people/{people['items'][0]['id']}", headers=filed["agent"])
        assert out.status_code == 200 and out.json()["activity"] == []

    def test_the_manager_can_still_see_staff(self, filed):
        client = filed["client"]
        people = client.get("/api/people?role=agent", headers=filed["admin"]).json()
        assert client.get(f"/api/people/{people['items'][0]['id']}", headers=filed["manager"]).status_code == 200


def test_a_new_department_manager_needs_a_real_password(client, auth_headers):
    out = client.post("/api/organisation/departments", headers=auth_headers("admin"), json={
        "code": f"T{uuid.uuid4().hex[:5].upper()}", "name": "Temporary Team", "manager_email": f"m.{uuid.uuid4().hex[:6]}@example.com",
    })
    assert out.status_code == 422, out.text
