"""
The people register and the live pulse.

An administrator must see a new account and what it did -- its complaints,
their history, its sign-ins -- straight from the database, and the pulse must
move when anything new arrives so an open dashboard refreshes itself.
"""

from __future__ import annotations

import uuid

import pytest

COMPLAINT = {
    "title": "Parcel not arrived",
    "description": (
        "My parcel for order CN-7755001 has not arrived and the tracking page "
        "has not updated for several days. Please tell me where it is."
    ),
    "order_ref": "CN-7755001",
}


def _register(client) -> tuple[dict, dict[str, str]]:
    body = {"email": f"people-{uuid.uuid4().hex[:8]}@example.com", "full_name": "Sana Tariq", "password": "a-long-enough-passphrase"}
    response = client.post("/api/auth/register", json=body)
    assert response.status_code == 201, response.text
    return body, {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.mark.parametrize("role", ["customer", "agent", "reviewer"])
def test_only_oversight_roles_see_people(client, auth_headers, role):
    assert client.get("/api/people", headers=auth_headers(role)).status_code == 403


def test_the_pulse_is_for_staff_only(client, auth_headers):
    assert client.get("/api/live/pulse", headers=auth_headers("customer")).status_code == 403
    assert client.get("/api/live/pulse", headers=auth_headers("agent")).status_code == 200


def test_a_new_account_shows_up_at_once(client, auth_headers):
    admin = auth_headers("admin")
    before = client.get("/api/live/pulse", headers=admin).json()

    body, _ = _register(client)

    pulse = client.get("/api/live/pulse", headers=admin).json()
    assert pulse["users"] == before["users"] + 1
    assert pulse["latest_user_name"] == "Sana Tariq"

    summary = client.get("/api/people/summary", headers=admin).json()
    assert body["email"] in [p["email"] for p in summary["recent_signups"]]
    assert summary["new_today"] >= 1
    # Registering signs the customer in, and that sign-in is on the dashboard too.
    assert body["email"] in [s["email"] for s in summary["recent_signins"]]

    found = client.get("/api/people", params={"search": body["email"]}, headers=admin).json()
    assert found["total"] == 1 and found["items"][0]["role"] == "customer"


def test_a_customers_complaint_and_its_history_reach_the_admin(client, auth_headers):
    admin = auth_headers("admin")
    before = client.get("/api/live/pulse", headers=admin).json()
    body, customer = _register(client)

    created = client.post("/api/complaints", json=COMPLAINT, headers=customer)
    assert created.status_code == 201, created.text
    ref = created.json()["public_ref"]

    pulse = client.get("/api/live/pulse", headers=admin).json()
    assert pulse["complaints"] == before["complaints"] + 1
    assert pulse["latest_complaint_ref"] == ref
    assert pulse["status_changes"] > before["status_changes"]

    row = client.get("/api/people", params={"search": body["email"]}, headers=admin).json()["items"][0]
    assert row["complaints"] == 1 and row["open_complaints"] == 1

    detail = client.get(f"/api/people/{row['id']}", headers=admin).json()
    assert detail["person"]["email"] == body["email"]
    complaint = next(c for c in detail["complaints"] if c["public_ref"] == ref)
    assert complaint["history"], "the status history travels with the complaint"
    assert complaint["history"][0]["to_status"]
    assert any(a["action"] in ("REGISTER", "LOGIN") for a in detail["activity"])


def test_staff_rows_carry_their_assigned_work(client, auth_headers):
    rows = client.get("/api/people", params={"role": "agent"}, headers=auth_headers("admin")).json()["items"]
    assert rows and all(r["role"] == "agent" for r in rows)
    assert all("assigned" in r for r in rows)


def test_an_unknown_account_is_a_404(client, auth_headers):
    assert client.get(f"/api/people/{uuid.uuid4()}", headers=auth_headers("admin")).status_code == 404
