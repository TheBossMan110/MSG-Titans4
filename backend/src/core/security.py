"""
Password hashing and JWT issuing / verification.

Deliberately self-contained (not Supabase Auth) so that:
  * roles have a single source of truth in our own ``users`` table (FR ii),
  * every login is auditable in ``audit_log`` (FR lxiv),
  * the whole stack still works offline against SQLite on demo day.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, VerifyMismatchError

from src.core.config import settings

_hasher = PasswordHasher()

ALGORITHM = settings.jwt_algorithm


# ── passwords ────────────────────────────────────────────────
def hash_password(plain: str) -> str:
    return _hasher.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _hasher.verify(hashed, plain)
    except (VerifyMismatchError, VerificationError, Exception):
        return False


# ── tokens ───────────────────────────────────────────────────
def _encode(payload: dict[str, Any], expires: timedelta, token_type: str) -> str:
    now = datetime.now(UTC)
    body = {
        **payload,
        "iat": int(now.timestamp()),
        "exp": int((now + expires).timestamp()),
        "jti": str(uuid.uuid4()),
        "typ": token_type,
    }
    return jwt.encode(body, settings.jwt_secret, algorithm=ALGORITHM)


def create_access_token(*, user_id: str, role: str, email: str) -> str:
    return _encode(
        {"sub": str(user_id), "role": role, "email": email},
        timedelta(minutes=settings.access_token_minutes),
        "access",
    )


def create_refresh_token(*, user_id: str) -> tuple[str, str, datetime]:
    """Returns (raw_token, sha256_hash, expires_at). Only the hash is stored."""
    expires_at = datetime.now(UTC) + timedelta(days=settings.refresh_token_days)
    raw = _encode({"sub": str(user_id)}, timedelta(days=settings.refresh_token_days), "refresh")
    return raw, sha256(raw), expires_at


def decode_token(token: str, expected_type: str | None = None) -> dict[str, Any]:
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
    if expected_type and payload.get("typ") != expected_type:
        raise jwt.InvalidTokenError(f"expected {expected_type} token")
    return payload


# ── helpers ──────────────────────────────────────────────────
def sha256(value: str | bytes) -> str:
    data = value.encode() if isinstance(value, str) else value
    return hashlib.sha256(data).hexdigest()


def random_token(n: int = 32) -> str:
    return secrets.token_urlsafe(n)


def parse_uuid(value: str | uuid.UUID | None) -> uuid.UUID | None:
    """
    JWT claims are always strings.  SQLAlchemy's Uuid column type wants a
    real UUID for primary-key lookups (Postgres coerces silently, SQLite
    does not) - so every token subject goes through here.
    """
    if value is None:
        return None
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return None
