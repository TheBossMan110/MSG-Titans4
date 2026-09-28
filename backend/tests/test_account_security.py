"""
Account security: two-step sign-in, lockout, sessions, profile, activity.

Each test registers its own customer, so locking or signing out an account
here can never disturb the seeded users the rest of the suite logs in as.
"""

from __future__ import annotations

import uuid

import pytest

from src.core import totp
from src.core.deps import _revoked
from src.db.models import User
from src.services import auth as auth_service

PASSWORD = "a-long-enough-passphrase"


def _register(client) -> tuple[str, dict]:
    email = f"sec-{uuid.uuid4().hex[:10]}@example.com"
    response = client.post(
        "/api/auth/register",
        json={"email": email, "full_name": "Sana Security", "password": PASSWORD},
    )
    assert response.status_code in (200, 201), response.text
    return email, response.json()


def _login(client, email: str, password: str = PASSWORD, ua: str = "pytest-browser"):
    return client.post(
        "/api/auth/login", json={"email": email, "password": password},
        headers={"User-Agent": ua},
    )


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def _clear_revocations():
    _revoked.clear()
    yield
    _revoked.clear()


class TestLockout:
    def test_five_wrong_passwords_lock_the_account(self, client):
        email, _ = _register(client)
        for _ in range(auth_service.MAX_FAILED_LOGINS):
            assert _login(client, email, "wrong-password-here").status_code == 401

        locked = _login(client, email)  # even the right password is refused now
        assert locked.status_code == 401
        assert locked.json()["error"]["code"] == "ACCOUNT_LOCKED"

    def test_a_success_resets_the_count(self, client, db):
        email, _ = _register(client)
        for _ in range(auth_service.MAX_FAILED_LOGINS - 1):
            _login(client, email, "wrong-password-here")
        assert _login(client, email).status_code == 200
        db.expire_all()
        user = db.query(User).filter(User.email == email).one()
        assert user.failed_login_count == 0


class TestTwoStep:
    def _enable(self, client, token: str) -> tuple[str, list[str]]:
        setup = client.post("/api/auth/mfa/setup", headers=_bearer(token))
        assert setup.status_code == 200, setup.text
        secret = setup.json()["secret"]
        assert setup.json()["otpauth_uri"].startswith("otpauth://totp/SupportNova")
        enabled = client.post("/api/auth/mfa/enable", json={"code": totp.now_code(secret)}, headers=_bearer(token))
        assert enabled.status_code == 200, enabled.text
        return secret, enabled.json()["codes"]

    def test_the_secret_is_never_stored_in_plain_text(self, client, db):
        email, reg = _register(client)
        secret, _ = self._enable(client, reg["access_token"])
        db.expire_all()
        stored = db.query(User).filter(User.email == email).one().mfa_secret
        assert secret not in stored
        assert totp.decrypt(stored) == secret

    def test_a_wrong_setup_code_does_not_switch_it_on(self, client):
        _, reg = _register(client)
        token = reg["access_token"]
        client.post("/api/auth/mfa/setup", headers=_bearer(token))
        bad = client.post("/api/auth/mfa/enable", json={"code": "000000"}, headers=_bearer(token))
        assert bad.status_code == 422
        assert client.get("/api/auth/security", headers=_bearer(token)).json()["mfa_enabled"] is False

    def test_sign_in_then_needs_the_code(self, client):
        email, reg = _register(client)
        secret, _ = self._enable(client, reg["access_token"])

        first = _login(client, email).json()
        assert first["mfa_required"] is True
        assert first["access_token"] is None and first["refresh_token"] is None

        wrong = client.post("/api/auth/login/mfa", json={"mfa_token": first["mfa_token"], "code": "000000"})
        assert wrong.status_code == 401

        right = client.post("/api/auth/login/mfa", json={"mfa_token": first["mfa_token"], "code": totp.now_code(secret)})
        assert right.status_code == 200, right.text
        assert right.json()["access_token"]

    def test_the_mfa_token_is_not_an_access_token(self, client):
        email, reg = _register(client)
        self._enable(client, reg["access_token"])
        mfa_token = _login(client, email).json()["mfa_token"]
        assert client.get("/api/auth/me", headers=_bearer(mfa_token)).status_code == 401

    def test_a_recovery_code_works_exactly_once(self, client):
        email, reg = _register(client)
        _, codes = self._enable(client, reg["access_token"])
        assert len(codes) == 8

        step = _login(client, email).json()["mfa_token"]
        assert client.post("/api/auth/login/mfa", json={"mfa_token": step, "code": codes[0]}).status_code == 200
        step = _login(client, email).json()["mfa_token"]
        assert client.post("/api/auth/login/mfa", json={"mfa_token": step, "code": codes[0]}).status_code == 401

    def test_turning_it_off_needs_password_and_code(self, client):
        email, reg = _register(client)
        secret, _ = self._enable(client, reg["access_token"])
        token = reg["access_token"]

        no_pw = client.post("/api/auth/mfa/disable", json={"password": "not-it-at-all", "code": totp.now_code(secret)}, headers=_bearer(token))
        assert no_pw.status_code == 401
        ok = client.post("/api/auth/mfa/disable", json={"password": PASSWORD, "code": totp.now_code(secret)}, headers=_bearer(token))
        assert ok.status_code == 200
        assert _login(client, email).json()["mfa_required"] is False


class TestSessions:
    def test_each_sign_in_is_a_session_and_the_current_one_is_marked(self, client):
        email, _ = _register(client)
        a = _login(client, email, ua="Mozilla/5.0 (Windows NT 10.0) Chrome/130.0").json()
        _login(client, email, ua="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0) Safari/604.1")

        sessions = client.get("/api/auth/sessions", headers=_bearer(a["access_token"])).json()
        assert len(sessions) >= 3  # the sign-up session and two sign-ins
        current = [s for s in sessions if s["current"]]
        assert len(current) == 1 and current[0]["device"] == "Chrome on Windows"
        assert any(s["device"] == "Safari on iPhone" for s in sessions)

    def test_signing_out_everywhere_else_stops_the_other_devices_at_once(self, client):
        email, _ = _register(client)
        mine = _login(client, email).json()
        theirs = _login(client, email).json()

        done = client.post("/api/auth/sessions/revoke-others", headers=_bearer(mine["access_token"]))
        assert done.status_code == 200

        # The other device's access token stops working now, not in two hours...
        refused = client.get("/api/auth/me", headers=_bearer(theirs["access_token"]))
        assert refused.status_code == 401 and refused.json()["error"]["code"] == "SESSION_REVOKED"
        # ...and it cannot renew itself.
        assert client.post("/api/auth/refresh", json={"refresh_token": theirs["refresh_token"]}).status_code == 401
        # This device carries on.
        assert client.get("/api/auth/me", headers=_bearer(mine["access_token"])).status_code == 200

    def test_signing_out_stops_this_access_token_at_once(self, client):
        """
        Revoking only the refresh token left the access token working until it
        expired -- "Sign out" on a shared computer did not sign anyone out.
        """
        email, _ = _register(client)
        mine = _login(client, email).json()
        other = _login(client, email).json()
        assert client.get("/api/auth/me", headers=_bearer(mine["access_token"])).status_code == 200

        done = client.post(
            "/api/auth/logout",
            json={"refresh_token": mine["refresh_token"]},
            headers=_bearer(mine["access_token"]),
        )
        assert done.status_code == 200, done.text

        refused = client.get("/api/auth/me", headers=_bearer(mine["access_token"]))
        assert refused.status_code == 401
        assert refused.json()["error"]["code"] == "SESSION_REVOKED"
        assert client.post("/api/auth/refresh", json={"refresh_token": mine["refresh_token"]}).status_code == 401
        # Only this session: the same account elsewhere carries on.
        assert client.get("/api/auth/me", headers=_bearer(other["access_token"])).status_code == 200

    def test_a_refreshed_session_keeps_its_device_and_start(self, client):
        email, _ = _register(client)
        first = _login(client, email, ua="Mozilla/5.0 (X11; Linux x86_64) Firefox/131.0").json()
        renewed = client.post("/api/auth/refresh", json={"refresh_token": first["refresh_token"]}).json()
        sessions = client.get("/api/auth/sessions", headers=_bearer(renewed["access_token"])).json()
        current = next(s for s in sessions if s["current"])
        assert current["device"] == "Firefox on Linux"

    def test_changing_the_password_signs_out_other_sessions(self, client):
        email, _ = _register(client)
        mine = _login(client, email).json()
        theirs = _login(client, email).json()
        changed = client.post(
            "/api/auth/change-password",
            json={"current_password": PASSWORD, "new_password": "another-long-passphrase"},
            headers=_bearer(mine["access_token"]),
        )
        assert changed.status_code == 200, changed.text
        assert "signed out" in changed.json()["message"]
        assert client.get("/api/auth/me", headers=_bearer(theirs["access_token"])).status_code == 401
        assert client.get("/api/auth/me", headers=_bearer(mine["access_token"])).status_code == 200


class TestProfileAndActivity:
    def test_a_user_can_change_their_name(self, client):
        _, reg = _register(client)
        response = client.patch("/api/auth/me", json={"full_name": "Sana Qureshi"}, headers=_bearer(reg["access_token"]))
        assert response.status_code == 200
        assert response.json()["full_name"] == "Sana Qureshi"

    def test_activity_shows_sign_ins_and_failures(self, client):
        email, _ = _register(client)
        _login(client, email, "wrong-password-here")
        token = _login(client, email).json()["access_token"]
        labels = [a["label"] for a in client.get("/api/auth/activity", headers=_bearer(token)).json()]
        assert "Signed in" in labels
        assert "Wrong password" in labels

    def test_the_overview_counts_sessions_and_reports_two_step(self, client):
        email, reg = _register(client)
        overview = client.get("/api/auth/security", headers=_bearer(reg["access_token"])).json()
        assert overview["mfa_enabled"] is False
        assert overview["active_sessions"] >= 1


class TestTotp:
    def test_rfc_6238_vectors(self):
        import base64

        secret = base64.b32encode(b"12345678901234567890").decode().rstrip("=")
        assert totp.now_code(secret, at=59) == "287082"
        assert totp.now_code(secret, at=1111111109) == "081804"
        assert totp.now_code(secret, at=2000000000) == "279037"

    def test_one_step_of_clock_drift_is_tolerated(self):
        secret = totp.new_secret()
        assert totp.verify(secret, totp.now_code(secret, at=1_000_000_000), at=1_000_000_030)
        assert not totp.verify(secret, totp.now_code(secret, at=1_000_000_000), at=1_000_000_120)
