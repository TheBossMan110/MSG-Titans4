"""Authentication endpoints (FR i, FR ii)."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response, status

from schemas.auth import (
    LoginRequest,
    PasswordChangeRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserOut,
)
from schemas.common import MessageResponse
from src.core.deps import CurrentUser, DbSession
from src.core.errors import AuthError
from src.core.ratelimit import LOGIN_LIMIT, limiter
from src.core.security import hash_password, verify_password
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
    response_model=TokenResponse,
    summary="Log in and receive an access + refresh token pair",
)
@limiter.limit(LOGIN_LIMIT)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,   # slowapi attaches X-RateLimit-* headers here
    db: DbSession,
) -> TokenResponse:
    """
    Rate-limited to `RATE_LIMIT_LOGIN` per IP.  Failures are audited but the
    error message never distinguishes an unknown account from a bad password.
    """
    user, access, refresh = auth_service.authenticate(
        db, email=payload.email, password=payload.password, request=request
    )
    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        expires_in=auth_service.access_token_ttl_seconds(),
        user=UserOut.model_validate(user),
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
    record_audit(
        db, actor=user, entity_type="auth", entity_id=str(user.id),
        action="PASSWORD_CHANGED", request=request,
    )
    return MessageResponse(message="Password updated.")
