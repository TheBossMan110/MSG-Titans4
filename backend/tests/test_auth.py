"""
Authentication and RBAC tests.

These double as evidence for the Security Testing Report (Deliverable 10):
"Unauthorised-access tests".
"""

from __future__ import annotations

import pytest


@pytest.mark.unit
def test_login_succeeds_for_seeded_evaluator(client, seed_password):
    resp = client.post(
        "/api/auth/login",
        json={"email": "evaluator@raftarxpress.com", "password": seed_password},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["user"]["role"] == "evaluator"
    # The password hash must never travel over the wire.
    assert "password" not in resp.text.lower() or "password_hash" not in resp.text


@pytest.mark.unit
def test_login_rejects_wrong_password(client):
    resp = client.post(
        "/api/auth/login",
        json={"email": "admin@raftarxpress.com", "password": "definitely-wrong"},
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHENTICATED"


@pytest.mark.unit
def test_login_does_not_enumerate_accounts(client, seed_password):
    """Unknown email and wrong password must be indistinguishable."""
    unknown = client.post(
        "/api/auth/login",
        json={"email": "nobody@raftarxpress.com", "password": seed_password},
    )
    wrong = client.post(
        "/api/auth/login",
        json={"email": "admin@raftarxpress.com", "password": "definitely-wrong"},
    )
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json()["error"]["message"] == wrong.json()["error"]["message"]


@pytest.mark.unit
def test_me_requires_a_token(client):
    assert client.get("/api/auth/me").status_code == 401


@pytest.mark.unit
def test_me_rejects_a_garbage_token(client):
    resp = client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert resp.status_code == 401


@pytest.mark.unit
def test_me_returns_the_signed_in_user(client, auth_headers):
    resp = client.get("/api/auth/me", headers=auth_headers("agent"))
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == "agent.billing@raftarxpress.com"
    assert body["role"] == "agent"
    assert body["department"]["code"] == "BILLING"


@pytest.mark.unit
def test_refresh_rotates_the_token(client, seed_password):
    login = client.post(
        "/api/auth/login",
        json={"email": "admin@raftarxpress.com", "password": seed_password},
    ).json()

    refreshed = client.post(
        "/api/auth/refresh", json={"refresh_token": login["refresh_token"]}
    )
    assert refreshed.status_code == 200
    assert refreshed.json()["refresh_token"] != login["refresh_token"]

    # The old refresh token is now revoked and must not work twice.
    replay = client.post(
        "/api/auth/refresh", json={"refresh_token": login["refresh_token"]}
    )
    assert replay.status_code == 401


@pytest.mark.unit
def test_login_records_an_audit_entry(client, db, seed_password):
    from sqlalchemy import select

    from src.db.models import AuditLog

    client.post(
        "/api/auth/login",
        json={"email": "manager@raftarxpress.com", "password": seed_password},
    )
    entry = db.execute(
        select(AuditLog)
        .where(AuditLog.action == "LOGIN")
        .order_by(AuditLog.created_at.desc())
        .limit(1)
    ).scalars().first()
    assert entry is not None
    assert entry.entity_type == "auth"


@pytest.mark.unit
def test_failed_login_is_audited(client, db):
    from sqlalchemy import select

    from src.db.models import AuditLog

    client.post(
        "/api/auth/login",
        json={"email": "reviewer@raftarxpress.com", "password": "nope"},
    )
    entry = db.execute(
        select(AuditLog)
        .where(AuditLog.action == "LOGIN_FAILED")
        .order_by(AuditLog.created_at.desc())
        .limit(1)
    ).scalars().first()
    assert entry is not None
