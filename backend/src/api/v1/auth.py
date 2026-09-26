"""Authentication endpoints (FR i, FR ii)."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Request, Response, status
from sqlalchemy import or_, select

from schemas.auth import (
    ActivityOut,
    LoginRequest,
    LoginResponse,
    MfaCodeRequest,
    MfaDisableRequest,
    MfaSetupOut,
    MfaVerifyRequest,
    PasswordChangeRequest,
    ProfileUpdate,
    RecoveryCodesOut,
    RefreshRequest,
    RegisterRequest,
    SecurityOverview,
    SessionOut,
    TokenResponse,
    UserOut,
)
from schemas.common import MessageResponse
from src.core.deps import CurrentUser, DbSession
from src.core.errors import AuthError, NotFoundError
from src.core.ratelimit import LOGIN_LIMIT, limiter
from src.core.security import hash_password, verify_password
from src.db.models import AuditLog
from src.services import auth as auth_service
from src.services.audit import record_audit

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a customer account and sign in",
)
@limiter.limit(LOGIN_LIMIT)
def register(
    payload: RegisterRequest,
    request: Request,
    response: Response,   # slowapi attaches X-RateLimit-* headers here
    db: DbSession,
) -> TokenResponse:
    """
    Open sign-up, rate-limited per IP like login.

    The account created is always a **customer**: the request cannot ask for
    a role, and the service ignores anything that tries. Staff accounts come
    from an administrator, so no one can promote themselves by posting JSON.
    """
    user, access, refresh = auth_service.register(
        db,
        email=payload.email,
        full_name=payload.full_name,
        password=payload.password,
        request=request,
    )
    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        expires_in=auth_service.access_token_ttl_seconds(),
        user=UserOut.model_validate(user),
    )


@router.post(
    "/login",
    response_model=LoginResponse,
    summary="Log in: a token pair, or a request for the second step",
)
@limiter.limit(LOGIN_LIMIT)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,   # slowapi attaches X-RateLimit-* headers here
    db: DbSession,
) -> LoginResponse:
    """
    Rate-limited to `RATE_LIMIT_LOGIN` per IP, and an account locks for 15
    minutes after 5 wrong passwords in a row. Failures are audited but the
    error message never distinguishes an unknown account from a bad password.

    With two-step sign-in on, a correct password returns ``mfa_required`` and
    a five-minute ``mfa_token`` instead of tokens; ``/auth/login/mfa`` finishes.
    """
    signed = auth_service.authenticate(
        db, email=payload.email, password=payload.password, request=request
    )
    if signed.mfa_required:
        return LoginResponse(mfa_required=True, mfa_token=signed.mfa_token)
    return LoginResponse(
        access_token=signed.access_token,
        refresh_token=signed.refresh_token,
        expires_in=auth_service.access_token_ttl_seconds(),
        user=UserOut.model_validate(signed.user),
    )


@router.post(
    "/login/mfa",
    response_model=TokenResponse,
    summary="Finish a two-step sign-in with an authenticator or recovery code",
)
@limiter.limit(LOGIN_LIMIT)
def login_mfa(
    payload: MfaVerifyRequest,
    request: Request,
    response: Response,
    db: DbSession,
) -> TokenResponse:
    signed = auth_service.verify_second_step(
        db, mfa_token=payload.mfa_token, code=payload.code, request=request
    )
    return TokenResponse(
        access_token=signed.access_token,
        refresh_token=signed.refresh_token,
        expires_in=auth_service.access_token_ttl_seconds(),
        user=UserOut.model_validate(signed.user),
    )


@router.post("/refresh", response_model=TokenResponse, summary="Rotate an expiring session")
def refresh(payload: RefreshRequest, request: Request, db: DbSession) -> TokenResponse:
    user, access, new_refresh = auth_service.refresh_tokens(
        db, raw_refresh=payload.refresh_token, request=request
    )
    return TokenResponse(
        access_token=access,
        refresh_token=new_refresh,
        expires_in=auth_service.access_token_ttl_seconds(),
        user=UserOut.model_validate(user),
    )


@router.post("/logout", response_model=MessageResponse, summary="Revoke a refresh token")
def logout(payload: RefreshRequest, request: Request, db: DbSession, user: CurrentUser):
    auth_service.revoke_refresh_token(db, raw_refresh=payload.refresh_token)
    record_audit(
        db, actor=user, entity_type="auth", entity_id=str(user.id),
        action="LOGOUT", request=request,
    )
    return MessageResponse(message="Signed out.")


@router.get("/me", response_model=UserOut, summary="The signed-in user")
def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)


@router.post(
    "/change-password",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Change your own password",
)
def change_password(
    payload: PasswordChangeRequest, request: Request, db: DbSession, user: CurrentUser
):
    if not verify_password(payload.current_password, user.password_hash):
        record_audit(
            db, actor=user, entity_type="auth", entity_id=str(user.id),
            action="PASSWORD_CHANGE_FAILED", request=request,
        )
        raise AuthError("Current password is incorrect.")

    user.password_hash = hash_password(payload.new_password)
    user.password_changed_at = datetime.now(UTC)
    record_audit(
        db, actor=user, entity_type="auth", entity_id=str(user.id),
        action="PASSWORD_CHANGED", request=request,
    )
    # Whoever knew the old password may hold a session made with it.
    others = auth_service.revoke_sessions(
        db, user, keep=getattr(request.state, "session_id", None),
        reason="password changed", request=request,
    )
    suffix = f" {others} other session{'s were' if others != 1 else ' was'} signed out." if others else ""
    return MessageResponse(message=f"Password updated.{suffix}")


# ══════════════════════════════════════════════════════════════
# profile and account security
# ══════════════════════════════════════════════════════════════
@router.patch("/me", response_model=UserOut, summary="Update your own name")
def update_me(payload: ProfileUpdate, request: Request, db: DbSession, user: CurrentUser) -> UserOut:
    before = user.full_name
    user.full_name = payload.full_name.strip()
    record_audit(
        db, actor=user, entity_type="auth", entity_id=str(user.id), action="PROFILE_UPDATED",
        before={"full_name": before}, after={"full_name": user.full_name}, request=request,
    )
    return UserOut.model_validate(user)


@router.get("/security", response_model=SecurityOverview, summary="Your account's security at a glance")
def security_overview(db: DbSession, user: CurrentUser) -> SecurityOverview:
    return SecurityOverview(
        mfa_enabled=user.mfa_enabled,
        mfa_enabled_at=user.mfa_enabled_at,
        recovery_codes_left=len(user.mfa_recovery_codes or []),
        password_changed_at=user.password_changed_at,
        last_login_at=user.last_login_at,
        active_sessions=len(auth_service.active_sessions(db, user)),
        locked_until=user.locked_until,
    )


@router.post("/mfa/setup", response_model=MfaSetupOut, summary="Start setting up two-step sign-in")
def mfa_setup(db: DbSession, user: CurrentUser) -> MfaSetupOut:
    secret, uri = auth_service.begin_mfa_setup(db, user)
    return MfaSetupOut(secret=secret, otpauth_uri=uri)


@router.post("/mfa/enable", response_model=RecoveryCodesOut, summary="Confirm the code and switch two-step on")
def mfa_enable(payload: MfaCodeRequest, request: Request, db: DbSession, user: CurrentUser) -> RecoveryCodesOut:
    return RecoveryCodesOut(codes=auth_service.enable_mfa(db, user, payload.code, request=request))


@router.post("/mfa/disable", response_model=MessageResponse, summary="Switch two-step sign-in off")
def mfa_disable(payload: MfaDisableRequest, request: Request, db: DbSession, user: CurrentUser) -> MessageResponse:
    auth_service.disable_mfa(db, user, password=payload.password, code=payload.code, request=request)
    return MessageResponse(message="Two-step sign-in is off.")


@router.post("/mfa/recovery-codes", response_model=RecoveryCodesOut, summary="Replace your recovery codes")
def mfa_recovery_codes(payload: MfaCodeRequest, request: Request, db: DbSession, user: CurrentUser) -> RecoveryCodesOut:
    return RecoveryCodesOut(codes=auth_service.regenerate_recovery_codes(db, user, payload.code, request=request))


@router.get("/sessions", response_model=list[SessionOut], summary="Where you are signed in")
def list_sessions(request: Request, db: DbSession, user: CurrentUser) -> list[SessionOut]:
    current = getattr(request.state, "session_id", None)
    return [
        SessionOut(
            id=row.id,
            device=_device(row.user_agent),
            user_agent=row.user_agent,
            ip_address=row.ip_address,
            started_at=row.session_started_at or row.created_at,
            last_active_at=row.created_at,
            expires_at=row.expires_at,
            current=current is not None and str(row.id) == str(current),
        )
        for row in auth_service.active_sessions(db, user)
    ]


@router.delete("/sessions/{session_id}", response_model=MessageResponse, summary="Sign out one session")
def revoke_session(session_id: str, request: Request, db: DbSession, user: CurrentUser) -> MessageResponse:
    count = auth_service.revoke_sessions(db, user, only=session_id, reason="signed out from profile", request=request)
    if not count:
        raise NotFoundError("That session is not active.")
    return MessageResponse(message="That session has been signed out.")


@router.post("/sessions/revoke-others", response_model=MessageResponse, summary="Sign out everywhere else")
def revoke_other_sessions(request: Request, db: DbSession, user: CurrentUser) -> MessageResponse:
    count = auth_service.revoke_sessions(
        db, user, keep=getattr(request.state, "session_id", None),
        reason="signed out everywhere else", request=request,
    )
    return MessageResponse(message=f"Signed out of {count} other session{'s' if count != 1 else ''}." if count else "There were no other sessions.")


# What each audited action reads as on the activity list, and whether it is good news.
_ACTIVITY = {
    "LOGIN": ("Signed in", True),
    "LOGIN_PASSWORD_OK": ("Password accepted, waiting for code", True),
    "LOGIN_FAILED": ("Wrong password", False),
    "LOGIN_BLOCKED": ("Sign-in blocked", False),
    "ACCOUNT_LOCKED": ("Account locked after wrong passwords", False),
    "MFA_FAILED": ("Wrong two-step code", False),
    "LOGOUT": ("Signed out", True),
    "PASSWORD_CHANGED": ("Password changed", True),
    "PASSWORD_CHANGE_FAILED": ("Password change refused", False),
    "MFA_ENABLED": ("Two-step sign-in turned on", True),
    "MFA_DISABLED": ("Two-step sign-in turned off", False),
    "MFA_RECOVERY_REGENERATED": ("New recovery codes made", True),
    "SESSIONS_REVOKED": ("Sessions signed out", True),
    "PROFILE_UPDATED": ("Name changed", True),
    "REGISTER": ("Account created", True),
}


@router.get("/activity", response_model=list[ActivityOut], summary="Recent sign-ins and security changes")
def activity(db: DbSession, user: CurrentUser, limit: int = 30) -> list[ActivityOut]:
    # Failed sign-ins are recorded against the email typed, not the account id,
    # because an unknown email has no account; both are the user's history.
    rows = db.execute(
        select(AuditLog)
        .where(
            # Registration is logged as a "user" event; everything else here is "auth".
            AuditLog.entity_type.in_(("auth", "user")),
            or_(AuditLog.entity_id == str(user.id), AuditLog.entity_id == user.email.lower()),
            AuditLog.action.in_(list(_ACTIVITY)),
        )
        .order_by(AuditLog.created_at.desc())
        .limit(max(1, min(limit, 100)))
    ).scalars().all()
    return [
        ActivityOut(
            at=row.created_at, action=row.action,
            label=_ACTIVITY[row.action][0], ok=_ACTIVITY[row.action][1],
            ip_address=row.ip_address,
            detail=row.reason if row.action in ("SESSIONS_REVOKED", "ACCOUNT_LOCKED") else None,
        )
        for row in rows
    ]


def _device(user_agent: str | None) -> str:
    """'Chrome on Windows' from a user-agent string; enough to recognise a session."""
    ua = user_agent or ""
    if not ua:
        return "Unknown device"
    browser = next((name for key, name in (
        ("Edg/", "Edge"), ("OPR/", "Opera"), ("Firefox/", "Firefox"), ("Chrome/", "Chrome"),
        ("Safari/", "Safari"), ("python-httpx", "API client"), ("curl/", "curl"),
    ) if key in ua), "Browser")
    system = next((name for key, name in (
        ("Windows", "Windows"), ("Android", "Android"), ("iPhone", "iPhone"), ("iPad", "iPad"),
        ("Mac OS X", "macOS"), ("Linux", "Linux"),
    ) if key in ua), "")
    return f"{browser} on {system}" if system else browser
