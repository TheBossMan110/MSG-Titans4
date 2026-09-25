"""
Self-service registration (FR i).

The interesting tests here are the ones that try to get more authority than
the form offers: a role in the body, a role in a nested object, an address
that already belongs to a seeded administrator. Registration is the only
unauthenticated write in the system, so it is the only place where a stranger
gets to put rows in the database at all.
"""

from __future__ import annotations

import itertools

import pytest
from sqlalchemy import select

from src.db.models import AuditLog, User

pytestmark = pytest.mark.integration


_seq = itertools.count()


def fresh_email() -> str:
    """A unique address per call: these tests share one database."""
    return f"nina.raza+{next(_seq)}@example.com"


def _body(**over):
    body = {
        "email": fresh_email(),
        "full_name": "Nina Raza",
        "password": "a-long-enough-passphrase",
    }
    body.update(over)
    return body


def test_registration_creates_a_customer_and_signs_them_in(client, db):
    body = _body()
    response = client.post("/api/auth/register", json=body)

    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["access_token"]
    assert payload["refresh_token"]
    assert payload["user"]["email"] == body["email"]
    assert payload["user"]["role"] == "customer"

    user = db.execute(
        select(User).where(User.email == body["email"])
    ).scalars().first()
    assert user is not None
    assert user.is_active is True
    # The password is never stored as given.
    assert user.password_hash != "a-long-enough-passphrase"
    assert "a-long-enough-passphrase" not in user.password_hash


def test_the_issued_token_works_immediately(client):
    token = client.post("/api/auth/register", json=_body()).json()["access_token"]

    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert me.status_code == 200
    assert me.json()["role"] == "customer"


@pytest.mark.parametrize(
    "attempt",
    [
        {"role": "admin"},
        {"role": "manager"},
        {"user": {"role": "admin"}},
        {"is_active": False},
        {"department_code": "COMPLIANCE"},
    ],
)
def test_the_body_cannot_ask_for_authority(client, attempt):
    """
    Anything beyond email, name and password is ignored.

    A sign-up form that let the applicant choose their own role would make
    every `require_role` check downstream decorative, so the service assigns
    CUSTOMER and never reads a role from the request.
    """
    response = client.post("/api/auth/register", json=_body(**attempt))

    assert response.status_code == 201, response.text
    assert response.json()["user"]["role"] == "customer"


def test_a_taken_address_is_refused(client):
    taken = fresh_email()
    client.post("/api/auth/register", json=_body(email=taken))

    again = client.post("/api/auth/register", json=_body(email=taken, full_name="Someone Else"))

    assert again.status_code == 409
    assert "already exists" in again.json()["error"]["message"].lower()


def test_a_seeded_staff_address_cannot_be_claimed(client):
    """Registering over an administrator would be account takeover."""
    response = client.post(
        "/api/auth/register", json=_body(email="admin@raftarxpress.com")
    )

    assert response.status_code == 409


def test_the_address_is_normalised(client, db):
    client.post("/api/auth/register", json=_body(email="  Mixed.CASE@Example.com  "))

    stored = db.execute(
        select(User).where(User.email == "mixed.case@example.com")
    ).scalars().first()
    assert stored is not None

    # ...and the normalised form is what collides on a second attempt.
    again = client.post("/api/auth/register", json=_body(email="MIXED.case@example.com"))
    assert again.status_code == 409


@pytest.mark.parametrize("password", ["short", "eleven-chrs", ""])
def test_a_weak_password_is_refused(client, password):
    response = client.post("/api/auth/register", json=_body(password=password))

    assert response.status_code == 422


@pytest.mark.parametrize("email", ["not-an-email", "@example.com", "nina@", ""])
def test_a_malformed_address_is_refused(client, email):
    response = client.post("/api/auth/register", json=_body(email=email))

    assert response.status_code == 422


def test_registration_is_audited(client, db):
    body = _body()
    response = client.post("/api/auth/register", json=body)
    assert response.status_code == 201

    entry = db.execute(
        select(AuditLog)
        .where(AuditLog.action == "REGISTER")
        .order_by(AuditLog.id.desc())
    ).scalars().first()

    assert entry is not None
    assert entry.actor_role == "customer"
    assert entry.after["email"] == body["email"].strip().lower()
    # The password must not travel into the audit trail.
    assert body["password"] not in str(entry.after)


def test_a_new_customer_sees_only_their_own_register(client):
    """
    The point of restricting sign-up to CUSTOMER: the account it creates
    cannot read the organisation's complaints.
    """
    token = client.post("/api/auth/register", json=_body()).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    assert client.get("/api/complaints", headers=headers).status_code == 403
    assert client.get("/api/admin/rules", headers=headers).status_code == 403
    assert client.get("/api/audit", headers=headers).status_code == 403

    mine = client.get("/api/complaints/mine", headers=headers)
    assert mine.status_code == 200
    assert mine.json()["items"] == []
