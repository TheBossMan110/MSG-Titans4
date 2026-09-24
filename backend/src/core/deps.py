"""
FastAPI dependencies: database session, current user, role gates.

FR ii — Role-Based Access Control.  Every non-public route declares the roles
allowed to reach it; a refusal is written to ``audit_log`` as ACCESS_DENIED,
which is what the Unauthorised-Access section of the Security Testing Report
(Deliverable 10) is built from.
"""

from __future__ import annotations

from collections.abc import Callable, Generator
from typing import Annotated

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from src.core.errors import AuthError, PermissionError_
from src.core.security import decode_token, parse_uuid
from src.db.base import SessionLocal
from src.db.enums import UserRole
from src.db.models import User

bearer_scheme = HTTPBearer(auto_error=False, description="JWT access token")


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


DbSession = Annotated[Session, Depends(get_db)]


def get_current_user(
    request: Request,
    db: DbSession,
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)] = None,
) -> User:
    if creds is None or not creds.credentials:
        raise AuthError("Authentication required.")

    try:
        payload = decode_token(creds.credentials, expected_type="access")
    except jwt.ExpiredSignatureError as exc:
        raise AuthError("Access token has expired.", code="TOKEN_EXPIRED") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthError("Invalid access token.") from exc

    user_id = parse_uuid(payload.get("sub"))
    user = db.get(User, user_id) if user_id else None
    if user is None or not user.is_active:
        raise AuthError("Account not found or deactivated.")

    request.state.user = user
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_role(*allowed: UserRole | str) -> Callable[..., User]:
    """
    Route guard.

    Usage::

        @router.post("/rules", dependencies=[Depends(require_role(UserRole.ADMIN))])

    ``EVALUATOR`` is granted read-level access everywhere it is listed so that
    judges can inspect the system without holding an administrator token.
    """
    allowed_values = {str(role) for role in allowed}

    def _guard(request: Request, user: CurrentUser) -> User:
        if user.role not in allowed_values:
            # Imported here to avoid a circular import at module load time.
            from src.services.audit import record_security_event

            # Written on its own committed session: raising below rolls the
            # request session back, and this row is security evidence.
            record_security_event(
                actor=user,
                entity_type="endpoint",
                entity_id=request.url.path,
                action="ACCESS_DENIED",
                reason=f"role={user.role} required={sorted(allowed_values)}",
                request=request,
                details={"method": request.method},
            )
            raise PermissionError_(
                "Your role does not have access to this resource.",
                details={"required_roles": sorted(allowed_values), "your_role": user.role},
            )
        return user

    return _guard


# ── convenience gates used across the API ────────────────────────────
AdminOnly = Depends(require_role(UserRole.ADMIN))
AdminOrManager = Depends(require_role(UserRole.ADMIN, UserRole.MANAGER))
StaffOnly = Depends(
    require_role(
        UserRole.ADMIN, UserRole.MANAGER, UserRole.REVIEWER,
        UserRole.AGENT, UserRole.EVALUATOR,
    )
)
ReviewerOnly = Depends(require_role(UserRole.ADMIN, UserRole.MANAGER, UserRole.REVIEWER))
