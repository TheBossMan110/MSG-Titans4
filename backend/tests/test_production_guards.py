"""
A production server refuses to start on settings that would make it unsafe or
silently empty, instead of running and failing at the first sign-in.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.core.config import settings
from src.main import app


@pytest.fixture()
def production(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "production")


def test_the_public_default_jwt_secret_is_refused(production, monkeypatch):
    monkeypatch.setattr(settings, "jwt_secret", "insecure-dev-secret-change-me")
    with pytest.raises(RuntimeError, match="JWT_SECRET"), TestClient(app):
        pass


def test_a_short_jwt_secret_is_refused(production, monkeypatch):
    monkeypatch.setattr(settings, "jwt_secret", "too-short")
    with pytest.raises(RuntimeError, match="JWT_SECRET"), TestClient(app):
        pass


def test_a_missing_database_url_is_refused_rather_than_run_on_empty_sqlite(production, monkeypatch):
    # The test suite itself runs on SQLite, which is exactly the fallback a
    # missing backend/.env would produce on a server.
    monkeypatch.setattr(settings, "jwt_secret", "x" * 64)
    assert not settings.is_postgres
    with pytest.raises(RuntimeError, match="DATABASE_URL"), TestClient(app):
        pass
