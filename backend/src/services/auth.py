"""Authentication service: login, refresh, logout (FR i)."""

from __future__ import annotations

from datetime import UTC, datetime

import jwt
from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.config import settings
from src.core.errors import AuthError, ConflictError, ValidationError
from src.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    parse_uuid,
    sha256,
    verify_password,
)
from src.db.enums import UserRole
from src.db.models import RefreshToken, User
from src.services.audit import record_audit, record_security_event

MIN_PASSWORD_LENGTH = 12


def register(
    db: Session,
    *,
    email: str,
    full_name: str,
    password: str,
    request: Request | None = None,
) -> tuple[User, str, str]:
    """
    Create a customer account and sign it in (FR i).

    **The role is not a parameter.** Self-registration always produces a
    CUSTOMER, whatever the request body says; agent, reviewer, manager, admin
    and evaluator accounts are created by an administrator. A sign-up form
    that let the applicant pick their own authority would make every
    role check downstream decorative.

    A customer can read only their own complaints, so the account is harmless
    on its own — which is precisely why it is the only role worth opening.

    Unlike ``authenticate``, this does distinguish "already registered" from
    success. Registration cannot hide that fact without an email round-trip to
    confirm ownership, and a form that silently refuses is worse for the
    honest majority than the enumeration is for us. The seeded demonstration
    addresses are published in the README in any case.
    """
    address = email.strip().lower()
    name = full_name.strip()

    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValidationError(
            f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
        )
    if not name:
        raise ValidationError("Please give a name for the account.")

    existing = db.execute(
        select(User).where(User.email == address)
    ).scalars().first()
    if existing is not None:
        record_security_event(
            entity_type="auth",
            entity_id=address,
            action="REGISTER_REJECTED",
            reason="email_taken",
            request=request,
        )
        raise ConflictError("An account already exists for that email address.")

    user = User(
        email=address,
        full_name=name,
        password_hash=hash_password(password),
        role=UserRole.CUSTOMER,
        is_active=True,
        last_login_at=datetime.now(UTC),
    )
    db.add(user)
    db.flush()  # assign the primary key before the token references it

    access = create_access_token(user_id=str(user.id), role=user.role, email=user.email)
    raw_refresh, token_hash, expires_at = create_refresh_token(user_id=str(user.id))
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=expires_at,
            user_agent=(request.headers.get("User-Agent")[:255] if request else None),
        )
    )

    record_audit(
        db, actor=user, entity_type="user", entity_id=str(user.id),
        action="REGISTER", after={"email": address, "role": user.role},
        reason="self-service sign-up", request=request,
    )
    return user, access, raw_refresh


def authenticate(
    db: Session, *, email: str, password: str, request: Request | None = None
) -> tuple[User, str, str]:
    """
    Verify credentials and issue a token pair.

    The failure message is intentionally identical for "unknown email" and
    "wrong password" so the endpoint cannot be used to enumerate accounts.
    """
    user = db.execute(
        select(User).where(User.email == email.strip().lower())
    ).scalars().first()

    if user is None or not verify_password(password, user.password_hash):
        # Independent session: this request is about to be rolled back.
        record_security_event(
            entity_type="auth",
            entity_id=email.strip().lower(),
            action="LOGIN_FAILED",
            reason="unknown_account" if user is None else "bad_password",
            request=request,
        )
        raise AuthError("Invalid email or password.")

    if not user.is_active:
        record_security_event(
            actor=user, entity_type="auth", entity_id=str(user.id),
            action="LOGIN_BLOCKED", reason="inactive_account", request=request,
        )
        raise AuthError("This account has been deactivated.")

    access = create_access_token(user_id=str(user.id), role=user.role, email=user.email)
    raw_refresh, token_hash, expires_at = create_refresh_token(user_id=str(user.id))

    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=expires_at,
            user_agent=(request.headers.get("User-Agent")[:255] if request else None),
        )
    )
    user.last_login_at = datetime.now(UTC)

    record_audit(
        db, actor=user, entity_type="auth", entity_id=str(user.id),
        action="LOGIN", request=request,
    )
    return user, access, raw_refresh


def refresh_tokens(
    db: Session, *, raw_refresh: str, request: Request | None = None
) -> tuple[User, str, str]:
    """Rotate a refresh token: the presented token is revoked and replaced."""
    try:
        payload = decode_token(raw_refresh, expected_type="refresh")
    except jwt.ExpiredSignatureError as exc:
        raise AuthError("Refresh token has expired.", code="TOKEN_EXPIRED") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthError("Invalid refresh token.") from exc

    token_hash = sha256(raw_refresh)
    stored = db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    ).scalars().first()

    if stored is None or stored.revoked_at is not None:
        raise AuthError("Refresh token is no longer valid.")
    if stored.expires_at <= datetime.now(UTC):
        raise AuthError("Refresh token has expired.", code="TOKEN_EXPIRED")

    user_id = parse_uuid(payload.get("sub"))
    user = db.get(User, user_id) if user_id else None
    if user is None or not user.is_active:
        raise AuthError("Account not found or deactivated.")

    stored.revoked_at = datetime.now(UTC)

    access = create_access_token(user_id=str(user.id), role=user.role, email=user.email)
    new_raw, new_hash, expires_at = create_refresh_token(user_id=str(user.id))
    db.add(RefreshToken(user_id=user.id, token_hash=new_hash, expires_at=expires_at))

    return user, access, new_raw


def revoke_refresh_token(db: Session, *, raw_refresh: str) -> None:
    stored = db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == sha256(raw_refresh))
    ).scalars().first()
    if stored and stored.revoked_at is None:
        stored.revoked_at = datetime.now(UTC)


def access_token_ttl_seconds() -> int:
    return settings.access_token_minutes * 60
