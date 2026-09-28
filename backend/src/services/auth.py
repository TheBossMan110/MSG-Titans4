"""Authentication service: login, refresh, logout (FR i)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core import totp
from src.core.config import settings
from src.core.errors import AuthError, ConflictError, ValidationError
from src.core.security import (
    create_access_token,
    create_mfa_token,
    create_refresh_token,
    decode_token,
    hash_password,
    parse_uuid,
    sha256,
    verify_password,
)
from src.db.enums import UserRole
from src.db.models import RefreshToken, User
from src.services.audit import _client_ip, record_audit, record_security_event

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

    access, raw_refresh = _open_session(db, user, request=request)

    record_audit(
        db, actor=user, entity_type="user", entity_id=str(user.id),
        action="REGISTER", after={"email": address, "role": user.role},
        reason="self-service sign-up", request=request,
    )
    return user, access, raw_refresh


# Consecutive wrong passwords before the account is locked, and for how long.
# Counted per account rather than per address, because a password-guessing
# attack spread across many addresses is exactly the one a per-IP rate limit
# (which the login route also has) cannot see.
MAX_FAILED_LOGINS = 5
LOCKOUT_MINUTES = 15


@dataclass
class SignIn:
    """The outcome of a correct password: tokens, or a second step to complete."""

    user: User
    access_token: str | None = None
    refresh_token: str | None = None
    mfa_token: str | None = None

    @property
    def mfa_required(self) -> bool:
        return self.mfa_token is not None


def _open_session(
    db: Session,
    user: User,
    *,
    request: Request | None,
    started_at: datetime | None = None,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> tuple[str, str]:
    """Create a session row and the token pair bound to it."""
    raw_refresh, token_hash, expires_at = create_refresh_token(user_id=str(user.id))
    row = RefreshToken(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=expires_at,
        user_agent=user_agent if user_agent is not None else (
            (request.headers.get("User-Agent") or "")[:255] or None if request else None
        ),
        ip_address=ip_address if ip_address is not None else _client_ip(request),
        session_started_at=started_at or datetime.now(UTC),
    )
    db.add(row)
    db.flush()
    access = create_access_token(
        user_id=str(user.id), role=user.role, email=user.email, sid=str(row.id)
    )
    return access, raw_refresh


def authenticate(
    db: Session, *, email: str, password: str, request: Request | None = None
) -> SignIn:
    """
    Verify credentials. Returns tokens, or -- when two-step sign-in is on -- a
    short-lived token that only the second step accepts.

    The failure message is intentionally identical for "unknown email" and
    "wrong password" so the endpoint cannot be used to enumerate accounts.
    """
    user = db.execute(
        select(User).where(User.email == email.strip().lower())
    ).scalars().first()
    now = datetime.now(UTC)

    if user is not None and user.locked_until and user.locked_until > now:
        record_security_event(
            actor=user, entity_type="auth", entity_id=str(user.id),
            action="LOGIN_BLOCKED", reason="locked", request=request,
        )
        minutes = max(1, int((user.locked_until - now).total_seconds() // 60) + 1)
        raise AuthError(
            f"Too many wrong passwords. Try again in {minutes} minute{'s' if minutes != 1 else ''}.",
            code="ACCOUNT_LOCKED",
        )

    if user is None or not verify_password(password, user.password_hash):
        if user is not None:
            _count_failure(user.id, request=request)
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

    user.failed_login_count = 0
    user.locked_until = None

    if user.mfa_enabled:
        record_audit(
            db, actor=user, entity_type="auth", entity_id=str(user.id),
            action="LOGIN_PASSWORD_OK", reason="awaiting second step", request=request,
        )
        return SignIn(user=user, mfa_token=create_mfa_token(user_id=str(user.id)))

    return _complete_sign_in(db, user, request=request)


def _complete_sign_in(db: Session, user: User, *, request: Request | None, method: str = "password") -> SignIn:
    access, raw_refresh = _open_session(db, user, request=request)
    user.last_login_at = datetime.now(UTC)
    record_audit(
        db, actor=user, entity_type="auth", entity_id=str(user.id),
        action="LOGIN", reason=method, request=request,
    )
    return SignIn(user=user, access_token=access, refresh_token=raw_refresh)


def _count_failure(user_id: Any, *, request: Request | None) -> None:
    """
    Count a wrong password in a session of its own.

    The request's session is rolled back when the login fails, which would
    take the count with it; the count must survive precisely those requests.
    """
    from src.db.base import SessionLocal

    counter = SessionLocal()
    try:
        user = counter.get(User, user_id)
        if user is None:
            return
        user.failed_login_count = (user.failed_login_count or 0) + 1
        if user.failed_login_count >= MAX_FAILED_LOGINS:
            user.locked_until = datetime.now(UTC) + timedelta(minutes=LOCKOUT_MINUTES)
            user.failed_login_count = 0
            record_audit(
                counter, actor=user, entity_type="auth", entity_id=str(user.id),
                action="ACCOUNT_LOCKED",
                reason=f"{MAX_FAILED_LOGINS} wrong passwords; locked for {LOCKOUT_MINUTES} minutes",
                request=request,
            )
        counter.commit()
    except Exception:  # noqa: BLE001 - counting must never break the login response
        counter.rollback()
    finally:
        counter.close()


def verify_second_step(
    db: Session, *, mfa_token: str, code: str, request: Request | None = None
) -> SignIn:
    """Finish a two-step sign-in with an authenticator code or a recovery code."""
    try:
        payload = decode_token(mfa_token, expected_type="mfa")
    except jwt.ExpiredSignatureError as exc:
        raise AuthError("That sign-in took too long. Please enter your password again.", code="MFA_EXPIRED") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthError("Invalid sign-in step.") from exc

    user_id = parse_uuid(payload.get("sub"))
    user = db.get(User, user_id) if user_id else None
    if user is None or not user.is_active or not user.mfa_enabled:
        raise AuthError("Invalid sign-in step.")

    method = check_second_factor(db, user, code)
    if method is None:
        record_security_event(
            actor=user, entity_type="auth", entity_id=str(user.id),
            action="MFA_FAILED", request=request,
        )
        raise AuthError("That code is not right. Codes change every 30 seconds.", code="MFA_INVALID")
    return _complete_sign_in(db, user, request=request, method=method)


def check_second_factor(db: Session, user: User, code: str) -> str | None:
    """``"totp"`` or ``"recovery_code"`` if ``code`` is valid, else ``None``. A recovery code is spent."""
    secret = totp.decrypt(user.mfa_secret) if user.mfa_secret else None
    if secret and totp.verify(secret, code):
        return "totp"
    hashed = totp.hash_recovery(code or "")
    remaining = list(user.mfa_recovery_codes or [])
    if hashed in remaining:
        remaining.remove(hashed)
        user.mfa_recovery_codes = remaining
        return "recovery_code"
    return None


# ══════════════════════════════════════════════════════════════
# two-step setup
# ══════════════════════════════════════════════════════════════
def begin_mfa_setup(db: Session, user: User) -> tuple[str, str]:
    """A fresh secret, stored but not yet active. Returns (secret, otpauth URI)."""
    if user.mfa_enabled:
        raise ConflictError("Two-step sign-in is already on. Turn it off first to set it up again.")
    secret = totp.new_secret()
    user.mfa_secret = totp.encrypt(secret)
    return secret, totp.provisioning_uri(secret, user.email)


def enable_mfa(db: Session, user: User, code: str, *, request: Request | None = None) -> list[str]:
    """Switch two-step on once the app proves it holds the secret. Returns recovery codes, once."""
    if user.mfa_enabled:
        raise ConflictError("Two-step sign-in is already on.")
    secret = totp.decrypt(user.mfa_secret) if user.mfa_secret else None
    if not secret:
        raise ValidationError("Start the setup first, then enter the code your app shows.")
    if not totp.verify(secret, code):
        raise ValidationError("That code is not right. Check the time on your phone and try the newest code.")
    codes = totp.new_recovery_codes()
    user.mfa_recovery_codes = [totp.hash_recovery(c) for c in codes]
    user.mfa_enabled_at = datetime.now(UTC)
    record_audit(db, actor=user, entity_type="auth", entity_id=str(user.id), action="MFA_ENABLED", request=request)
    return codes


def disable_mfa(db: Session, user: User, *, password: str, code: str, request: Request | None = None) -> None:
    """Turning protection off needs both factors, so a stolen session alone cannot."""
    if not user.mfa_enabled:
        raise ConflictError("Two-step sign-in is not on.")
    if not verify_password(password, user.password_hash):
        raise AuthError("Your password is not right.")
    if check_second_factor(db, user, code) is None:
        raise AuthError("That code is not right.")
    user.mfa_secret = None
    user.mfa_enabled_at = None
    user.mfa_recovery_codes = None
    record_audit(db, actor=user, entity_type="auth", entity_id=str(user.id), action="MFA_DISABLED", request=request)


def regenerate_recovery_codes(db: Session, user: User, code: str, *, request: Request | None = None) -> list[str]:
    if not user.mfa_enabled:
        raise ConflictError("Two-step sign-in is not on.")
    if check_second_factor(db, user, code) is None:
        raise AuthError("That code is not right.")
    codes = totp.new_recovery_codes()
    user.mfa_recovery_codes = [totp.hash_recovery(c) for c in codes]
    record_audit(db, actor=user, entity_type="auth", entity_id=str(user.id), action="MFA_RECOVERY_REGENERATED", request=request)
    return codes


# ══════════════════════════════════════════════════════════════
# sessions
# ══════════════════════════════════════════════════════════════
def active_sessions(db: Session, user: User) -> list[RefreshToken]:
    return list(db.execute(
        select(RefreshToken)
        .where(
            RefreshToken.user_id == user.id,
            RefreshToken.revoked_at.is_(None),
            RefreshToken.expires_at > datetime.now(UTC),
        )
        .order_by(RefreshToken.created_at.desc())
    ).scalars())


def revoke_sessions(
    db: Session, user: User, *, keep: str | None = None, only: str | None = None,
    reason: str, request: Request | None = None,
) -> int:
    """Sign out sessions: one (``only``), or every one except ``keep``."""
    from src.core.deps import mark_session_revoked

    count = 0
    for row in active_sessions(db, user):
        if only is not None and str(row.id) != str(only):
            continue
        if keep is not None and str(row.id) == str(keep):
            continue
        row.revoked_at = datetime.now(UTC)
        mark_session_revoked(str(row.id))
        count += 1
    if count:
        record_audit(
            db, actor=user, entity_type="auth", entity_id=str(user.id),
            action="SESSIONS_REVOKED", reason=f"{reason} ({count})", request=request,
        )
    return count


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

    # The replacement belongs to the same session: same device, same start.
    access, new_raw = _open_session(
        db, user, request=request,
        started_at=stored.session_started_at or stored.created_at,
        user_agent=stored.user_agent, ip_address=stored.ip_address,
    )
    return user, access, new_raw


def revoke_refresh_token(
    db: Session, *, raw_refresh: str, session_id: str | None = None
) -> None:
    """
    Sign a session out: its refresh token, and its access token at once.

    Revoking the refresh token only stops renewal. The access token already
    issued would otherwise go on working until it expired -- up to
    ``ACCESS_TOKEN_MINUTES`` after the person pressed "Sign out", on a shared
    computer as much as anywhere. So the caller's session (the access token's
    ``sid``) is refused from now on, exactly as signing out another device is
    in :func:`revoke_sessions`.
    """
    from src.core.deps import mark_session_revoked

    stored = db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == sha256(raw_refresh))
    ).scalars().first()
    if stored and stored.revoked_at is None:
        stored.revoked_at = datetime.now(UTC)
    if stored is not None:
        mark_session_revoked(str(stored.id))
    if session_id:
        mark_session_revoked(session_id)


def access_token_ttl_seconds() -> int:
    return settings.access_token_minutes * 60
