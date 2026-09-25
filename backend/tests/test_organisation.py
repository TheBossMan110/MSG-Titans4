"""The organisation page shows what the dataset's configuration folder defines."""

from __future__ import annotations


def test_staff_see_the_whole_organisation(client, auth_headers):
    response = client.get("/api/organisation", headers=auth_headers("agent"))
    assert response.status_code == 200, response.text
    org = response.json()

    assert org["profile"]["name"]
    assert org["profile"]["support_hours"]
    assert len(org["profile"]["customer_types"]) >= 4
    assert len(org["departments"]) >= 8
    assert len(org["categories"]) >= 10
    assert sum(len(c["subcategories"]) for c in org["categories"]) >= 20
    assert any(row["category"] is None for row in org["sla"]), "the default SLA ladder is missing"


def test_teams_carry_the_dataset_details(client, auth_headers):
    org = client.get("/api/organisation", headers=auth_headers("manager")).json()
    team = next(d for d in org["departments"] if d["code"] == "LOGISTICS_OPS")
    assert team["email"] == "logistics-ops@raftarxpress.com"
    assert team["escalation_contact"]
    assert team["handles"]
    assert team["sla_response_hours"] and team["sla_resolution_hours"]


def test_every_authored_template_is_there(client, auth_headers):
    org = client.get("/api/organisation", headers=auth_headers("admin")).json()
    ids = [t["id"] for t in org["templates"]]
    assert len(ids) == 14 and len(set(ids)) == 14
    assert all("{{" in t["text"] for t in org["templates"]), "placeholders were lost"


def test_customers_cannot_read_it(client, auth_headers):
    assert client.get("/api/organisation", headers=auth_headers("customer")).status_code == 403
