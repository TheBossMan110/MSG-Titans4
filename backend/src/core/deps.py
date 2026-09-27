"""
FastAPI dependencies: database session, current user, role gates.

FR ii — Role-Based Access Control.  Every non-public route declares the roles
allowed to reach it; a refusal is written to ``audit_log`` as ACCESS_DENIED,
which is what the Unauthorised-Access section of the Security Testing Report
(Deliverable 10) is built from.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Generator
from typing import Annotated

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import event
from sqlalchemy.orm import Session

from src.core.config import settings
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


# Sessions signed out in this process, by id, until their access tokens would
# have expired anyway. Revoking the refresh token stops renewal; this stops the
# access token already issued, without a database read on every request.
_revoked: dict[str, float] = {}
_revoked_lock = threading.Lock()


def mark_session_revoked(sid: str) -> None:
    import time as _time

    with _revoked_lock:
        _revoked[str(sid)] = _time.time() + settings.access_token_minutes * 60
        now = _time.time()
        for key in [k for k, until in _revoked.items() if until < now]:
            _revoked.pop(key, None)


def session_revoked(sid: str) -> bool:
    import time as _time

    until = _revoked.get(str(sid))
    return until is not None and until > _time.time()


# Who a token belongs to, remembered briefly so that a page served from the
# response cache needs no database round trip at all. A copy is valid for a
# minute and only while nothing tracked has changed (response_cache
# generation: any change to users -- a role, a deactivation -- clears it), so
# a demotion or a disabled account takes effect on the very next request.
# Signed-out sessions are refused separately, before this, by session_revoked.
_USER_TTL_S = 60.0
_user_copies: dict = {}


# Any write to a user's row -- a password, two-step secret, lockout counter --
# drops that user's remembered copy once the write is committed, so the next
# request reads the row as it now is. (The response-cache generation, which
# also clears it, deliberately ignores sign-in bookkeeping; this does not.)
@event.listens_for(Session, "after_flush")
def _users_written(session: Session, _ctx) -> None:
    touched = {obj.id for obj in (*session.new, *session.dirty, *session.deleted) if isinstance(obj, User)}
    if touched:
        session.info.setdefault("sn_users_written", set()).update(touched)


@event.listens_for(Session, "after_commit")
def _forget_written_users(session: Session) -> None:
    for user_id in session.info.pop("sn_users_written", ()):
        _user_copies.pop(user_id, None)


@event.listens_for(Session, "after_rollback")
def _discard_written_users(session: Session) -> None:
    session.info.pop("sn_users_written", None)


def _known_user(db: Session, user_id):
    import time as _time

    from sqlalchemy.orm import make_transient_to_detached

    from src.core import response_cache

    now = _time.monotonic()
    known = _user_copies.get(user_id)
    if known is not None and known[1] == response_cache.generation() and now - known[2] < _USER_TTL_S:
        # Attach the remembered state to this request's session without a SELECT.
        return db.merge(known[0], load=False)
    user = db.get(User, user_id)
    if user is not None:
        copy = User(**{column.key: getattr(user, column.key) for column in User.__table__.columns})
        make_transient_to_detached(copy)
        _user_copies[user_id] = (copy, response_cache.generation(), now)
    return user


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

    sid = payload.get("sid")
    if sid and session_revoked(sid):
        raise AuthError("This session has been signed out.", code="SESSION_REVOKED")

    user_id = parse_uuid(payload.get("sub"))
    user = _known_user(db, user_id) if user_id else None
    if user is None or not user.is_active:
        raise AuthError("Account not found or deactivated.")

    request.state.user = user
    request.state.session_id = sid
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_optional_user(
    request: Request,
    db: DbSession,
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)] = None,
) -> User | None:
    """The signed-in user, or ``None`` for a visitor -- never an error."""
    if creds is None or not creds.credentials:
        return None
    try:
        return get_current_user(request, db, creds)
    except AuthError:
        return None


OptionalUser = Annotated[User | None, Depends(get_optional_user)]


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
