"""
Plans: what is enforced, and the one thing that never is.

A plan can limit staff accounts and AI analysis. It can never make the system
refuse a customer's complaint.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select

from src.core import billing, tenancy
from src.db.models import AuditLog, PlanRequest

PASSWORD = "Correct-Horse-Battery-9"
COMPLAINT = {"title": "Parcel never arrived", "description": "My parcel CN-55120045 was due on Monday and has not arrived."}


@pytest.fixture
def superadmin(client):
    token = client.post("/api/auth/login", json={"email": "superadmin@supportnova.com", "password": "SupportNova#2026"}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def company(client, superadmin):
    """Make a company on a plan and return its id, slug and administrator's header."""
    def make(plan: str = "starter", trial_days: int = 14) -> dict:
        tag = uuid.uuid4().hex[:8]
        email = f"admin.{tag}@bill-example.com"
        out = client.post("/api/company/create", headers=superadmin, json={
            "company_name": f"Billing Co {tag}", "admin_full_name": "First Admin", "admin_email": email,
            "admin_password": PASSWORD, "plan": plan, "trial_days": trial_days,
        })
        assert out.status_code == 201, out.text
        token = client.post("/api/auth/login", json={"email": email, "password": PASSWORD}).json()["access_token"]
        row = out.json()["company"]
        return {"id": row["id"], "slug": row["slug"], "row": row, "admin": {"Authorization": f"Bearer {token}"}}
    return make


def _add_staff(client, admin, role="agent"):
    return client.post("/api/people", headers=admin, json={
        "email": f"{role}.{uuid.uuid4().hex[:8]}@bill-example.com", "full_name": "Staff Person", "password": PASSWORD, "role": role,
    })


def _customer(client, slug: str) -> dict:
    email = f"cust.{uuid.uuid4().hex[:8]}@bill-example.com"
    out = client.post("/api/auth/register", json={"email": email, "full_name": "A Customer", "password": PASSWORD, "company": slug})
    assert out.status_code in (200, 201), out.text
    token = client.post("/api/auth/login", json={"email": email, "password": PASSWORD}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_the_pricing_page_and_the_server_agree():
    frontend = Path(__file__).resolve().parents[2] / "frontend" / "lib" / "plans.json"
    if not frontend.exists():
        pytest.skip("frontend not present")
    assert json.loads(frontend.read_text(encoding="utf-8")) == billing.CATALOGUE


class TestAStartingCompany:
    def test_it_starts_on_a_free_trial_of_its_plan(self, company):
        row = company("growth")["row"]
        assert row["plan"] == "growth" and row["subscription_status"] == "trialing" and row["trial_ends_at"]

    def test_no_trial_means_active(self, company):
        assert company("starter", trial_days=0)["row"]["subscription_status"] == "active"

    def test_an_unknown_plan_is_refused(self, client, superadmin):
        out = client.post("/api/company/create", headers=superadmin, json={
            "company_name": f"Bad {uuid.uuid4().hex[:6]}", "admin_full_name": "Bad Plan", "admin_email": f"b.{uuid.uuid4().hex[:6]}@bill-example.com",
            "admin_password": PASSWORD, "plan": "free-forever",
        })
        assert out.status_code == 422


class TestSeats:
    def test_staff_stop_at_the_plan_limit(self, client, company):
        c = company("starter")
        for _ in range(4):     # the first administrator is seat one of five
            assert _add_staff(client, c["admin"]).status_code == 201
        refused = _add_staff(client, c["admin"])
        assert refused.status_code == 402
        assert refused.json()["error"]["code"] == "PLAN_LIMIT"

    def test_customers_take_no_seat(self, client, company):
        c = company("starter")
        for _ in range(4):
            _add_staff(client, c["admin"])
        assert client.post("/api/people", headers=c["admin"], json={
            "email": f"c.{uuid.uuid4().hex[:8]}@bill-example.com", "full_name": "A Customer", "password": PASSWORD, "role": "customer",
        }).status_code == 201

    def test_a_seat_comes_back_when_an_account_is_disabled(self, client, company):
        c = company("starter")
        rows = [_add_staff(client, c["admin"]).json() for _ in range(4)]
        assert client.patch(f"/api/people/{rows[0]['id']}", headers=c["admin"], json={"is_active": False}).status_code == 200
        assert _add_staff(client, c["admin"]).status_code == 201

    def test_reactivating_past_the_limit_is_refused(self, client, company):
        c = company("starter")
        rows = [_add_staff(client, c["admin"]).json() for _ in range(4)]
        client.patch(f"/api/people/{rows[0]['id']}", headers=c["admin"], json={"is_active": False})
        _add_staff(client, c["admin"])
        assert client.patch(f"/api/people/{rows[0]['id']}", headers=c["admin"], json={"is_active": True}).status_code == 402

    def test_the_reference_company_has_no_limit(self, client, auth_headers):
        assert billing.subscription_of(None) is None
        assert _add_staff(client, auth_headers("admin")).status_code == 201


class TestTheAIAllowance:
    @pytest.fixture
    def asked(self, monkeypatch):
        """Records whether the pipelines were told to use the AI."""
        from complaint_processing import intake

        calls: list[bool] = []
        real = intake.reconcile

        def spy(db, complaint, *, run_genai=True, **kwargs):
            calls.append(run_genai)
            return real(db, complaint, run_genai=run_genai, **kwargs)

        monkeypatch.setattr(intake, "reconcile", spy)
        return calls

    def test_within_the_allowance_the_ai_runs(self, client, company, asked):
        c = company("starter")
        assert client.post("/api/complaints", headers=_customer(client, c["slug"]), json=COMPLAINT).status_code == 201
        assert asked == [True]

    def test_over_the_allowance_the_complaint_is_still_taken_by_the_rules(self, client, company, asked, monkeypatch):
        c = company("starter")
        monkeypatch.setattr(billing, "ai_used", lambda db, org: 1000)
        out = client.post("/api/complaints", headers=_customer(client, c["slug"]), json=COMPLAINT)
        assert out.status_code == 201, "a limit must never turn a customer away"
        assert out.json()["public_ref"].startswith("CMP-")
        assert asked == [False]

    def test_after_the_trial_the_complaint_is_still_taken_by_the_rules(self, client, company, asked, db):
        from src.db.models import Organisation

        c = company("starter")
        org = db.get(Organisation, uuid.UUID(c["id"]))
        settings = dict(org.settings)
        settings["subscription"] = {**settings["subscription"], "trial_ends_at": (datetime.now(UTC) - timedelta(days=1)).isoformat()}
        org.settings = settings
        db.commit()
        tenancy.forget(org.id)

        out = client.post("/api/complaints", headers=_customer(client, c["slug"]), json=COMPLAINT)
        assert out.status_code == 201 and asked == [False]
        seen = client.get("/api/billing/subscription", headers=c["admin"]).json()
        assert seen["status"] == "ended" and seen["ai_active"] is False and "trial" in seen["notice"]

    def test_the_reference_company_is_unmetered(self, client, auth_headers, asked, monkeypatch):
        monkeypatch.setattr(billing, "ai_used", lambda db, org: 10**9)
        assert client.post("/api/complaints", headers=auth_headers("customer"), json=COMPLAINT).status_code == 201
        assert asked == [True]


class TestWhatAnAdministratorSees:
    def test_their_plan_and_usage(self, client, company):
        c = company("growth")
        _add_staff(client, c["admin"])
        body = client.get("/api/billing/subscription", headers=c["admin"]).json()
        assert body["plan"]["code"] == "growth"
        assert body["seats_used"] == 2 and body["seats_limit"] == 15
        assert body["ai_used"] == 0 and body["ai_limit"] == 5000 and body["ai_active"] is True

    def test_a_customer_or_agent_cannot_see_it(self, client, auth_headers):
        assert client.get("/api/billing/subscription", headers=auth_headers("customer")).status_code == 403
        assert client.get("/api/billing/subscription", headers=auth_headers("agent")).status_code == 403


class TestChangingAPlan:
    def test_the_super_admin_sets_it_and_it_is_audited(self, client, superadmin, company, db):
        c = company("starter")
        out = client.put(f"/api/company/{c['id']}/subscription", headers=superadmin, json={
            "plan": "scale", "status": "active", "billing_cycle": "annual", "reason": "Invoice 42 paid",
        })
        assert out.status_code == 200, out.text
        assert out.json()["plan"] == "scale" and out.json()["subscription_status"] == "active"
        assert client.get("/api/billing/subscription", headers=c["admin"]).json()["seats_limit"] == 50
        audited = db.execute(select(AuditLog).where(AuditLog.entity_id == c["id"], AuditLog.action == "SUBSCRIPTION_UPDATED")).scalars().first()
        assert audited is not None and audited.reason == "Invoice 42 paid"

    def test_nobody_else_can(self, client, company):
        c = company("starter")
        out = client.put(f"/api/company/{c['id']}/subscription", headers=c["admin"], json={"plan": "enterprise", "status": "active"})
        assert out.status_code == 403


class TestThePricingForm:
    BODY = {"company_name": "Fast Couriers", "contact_name": "Ali Raza", "email": "ali@fastcouriers.example", "plan_code": "growth", "team_size": 12}

    def test_anyone_can_ask(self, client, db):
        email = f"ali.{uuid.uuid4().hex[:6]}@fastcouriers.example"
        out = client.post("/api/billing/requests", json={**self.BODY, "email": email})
        assert out.status_code == 201 and out.json() == {"received": True}
        assert db.execute(select(PlanRequest).where(PlanRequest.email == email)).scalars().first() is not None

    def test_a_bot_is_told_yes_and_nothing_is_kept(self, client, db):
        email = f"bot.{uuid.uuid4().hex[:6]}@spam.example"
        out = client.post("/api/billing/requests", json={**self.BODY, "email": email, "website": "http://spam.example"})
        assert out.status_code == 201
        assert db.execute(select(PlanRequest).where(PlanRequest.email == email)).scalars().first() is None

    def test_a_made_up_plan_is_refused(self, client):
        assert client.post("/api/billing/requests", json={**self.BODY, "plan_code": "free"}).status_code == 422

    def test_it_is_rate_limited(self, client):
        for _ in range(5):
            client.post("/api/billing/requests", json=self.BODY)
        assert client.post("/api/billing/requests", json=self.BODY).status_code == 429

    def test_only_the_platform_reads_them(self, client, superadmin, auth_headers):
        client.post("/api/billing/requests", json=self.BODY)
        assert client.get("/api/billing/requests", headers=superadmin).json()["items"]
        assert client.get("/api/billing/requests", headers=auth_headers("admin")).status_code == 403

    def test_a_request_can_be_followed_up(self, client, superadmin):
        client.post("/api/billing/requests", json=self.BODY)
        first = client.get("/api/billing/requests", headers=superadmin).json()["items"][0]
        out = client.patch(f"/api/billing/requests/{first['id']}", headers=superadmin, json={"status": "CONTACTED"})
        assert out.status_code == 200 and out.json()["status"] == "CONTACTED"
