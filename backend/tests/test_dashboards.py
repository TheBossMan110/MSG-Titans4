"""The three dashboards the SRS describes: administrator, agent and user."""

from __future__ import annotations

from genai_pipeline.providers.base import ProviderUnavailable
from genai_pipeline.providers.chain import is_model_fault


def test_the_admin_dashboard_has_every_listed_figure(client, auth_headers):
    d = client.get("/api/analytics/dashboard", headers=auth_headers("admin")).json()
    # total, categories, departments, priorities, escalations, resolution, SLA risks, mismatches, manual review
    for key in ("volume", "categories", "departments", "priorities", "escalation", "sla", "sla_risks", "pipelines", "mismatches", "review", "manual_review"):
        assert key in d, key
    assert "total" in d["volume"] and "by_status" in d["volume"]


def test_agents_cannot_open_the_admin_dashboard(client, auth_headers):
    assert client.get("/api/analytics/dashboard", headers=auth_headers("agent")).status_code == 403


def test_an_agent_sees_their_own_team_only(client, auth_headers):
    w = client.get("/api/analytics/agent-workspace", headers=auth_headers("agent")).json()
    assert w["scope"] == "mine"
    assert w["team"] in (None, "Billing & Accounts")
    for item in w["complaints"]:
        assert item["assigned_to_me"] or item["team"] == w["team"]
        for key in ("category", "priority", "sentiment", "recommendation", "validation", "suggested_response", "escalation_warnings"):
            assert key in item


def test_an_admin_can_view_any_team_as_an_agent_would(client, auth_headers):
    w = client.get("/api/analytics/agent-workspace?department=BILLING", headers=auth_headers("admin")).json()
    assert w["scope"] == "all"
    assert all(i["team"] in (None, w["team"]) for i in w["complaints"])


def test_customers_have_no_agent_dashboard(client, auth_headers):
    assert client.get("/api/analytics/agent-workspace", headers=auth_headers("customer")).status_code == 403


def test_a_reply_cannot_be_drafted_before_analysis(client, auth_headers):
    body = {"title": "Late parcel", "description": "My parcel has not arrived and the tracking page has not updated for days."}
    ref = client.post("/api/complaints?analyse=false", json=body, headers=auth_headers("reviewer")).json()["public_ref"]
    r = client.post(f"/api/complaints/{ref}/responses", headers=auth_headers("reviewer"))
    assert r.status_code == 422
    assert client.get(f"/api/complaints/{ref}/responses", headers=auth_headers("reviewer")).json() == []


def test_an_empty_prepaid_balance_is_not_retried():
    """DeepSeek answers 402 when the account has no credit: final, like a bad key."""
    assert is_model_fault(ProviderUnavailable("Insufficient Balance", provider="deepseek", status=402)) is False


class TestSearchAndFiltering:
    """SRS Step 66: ID, customer reference, category, department, priority, sentiment, status, date, escalation."""

    def _file(self, client, auth_headers, **extra):
        body = {"title": "Late parcel", "description": "My parcel has not arrived and the tracking has not updated for days.", **extra}
        return client.post("/api/complaints?analyse=false", json=body, headers=auth_headers("agent")).json()["public_ref"]

    def test_search_finds_an_order_reference(self, client, auth_headers):
        ref = self._file(client, auth_headers, order_ref="CN-9988776655")
        found = client.get("/api/complaints?search=cn-9988776655", headers=auth_headers("admin")).json()
        assert ref in [i["public_ref"] for i in found["items"]]

    def test_date_escalation_and_sentiment_filters_are_accepted(self, client, auth_headers):
        h = auth_headers("admin")
        for query in ("date_from=2020-01-01&date_to=2099-12-31", "escalation=ANY", "escalation=NONE", "sentiment=NEGATIVE"):
            assert client.get(f"/api/complaints?{query}", headers=h).status_code == 200, query

    def test_a_future_date_range_is_empty(self, client, auth_headers):
        out = client.get("/api/complaints?date_from=2099-01-01", headers=auth_headers("admin")).json()
        assert out["total"] == 0
