"""
Audit trail writer (FR lxiv).

Every consequential action goes through here: logins, access denials, rule
changes, reviewer overrides, document activations, config edits.

SRS Step 59: "The original recommendation and reviewer decision must both
remain in the audit trail."  That is why ``before`` and ``after`` are stored
as separate JSON snapshots rather than a diff string.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session

from src.db.models import AuditLog, User


def _jsonable(value: Any) -> Any:
    """Make UUIDs/datetimes safe for a JSON column without pulling in FastAPI."""
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, list | tuple | set):
        return [_jsonable(v) for v in value]
    return str(value)


def record_audit(
    db: Session,
    *,
    entity_type: str,
    entity_id: str | uuid.UUID,
    action: str,
    actor: User | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    reason: str | None = None,
    request: Request | None = None,
) -> AuditLog:
    entry = AuditLog(
        actor_id=actor.id if actor else None,
        actor_role=actor.role if actor else None,
        entity_type=entity_type,
        entity_id=str(entity_id),
        action=action,
        before=_jsonable(before),
        after=_jsonable(after),
        reason=reason,
        request_id=getattr(getattr(request, "state", None), "request_id", None),
        ip_address=_client_ip(request),
    )
    db.add(entry)
    db.flush()
    return entry


def record_security_event(
    *,
    entity_type: str,
    entity_id: str | uuid.UUID,
    action: str,
    actor: User | None = None,
    reason: str | None = None,
    request: Request | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """
    Audit a *denied* action on its own committed session.

    Failed logins and role refusals end the request with an exception, which
    rolls the request-scoped session back — taking the audit row with it.  The
    Unauthorised-Access section of the Security Testing Report (Deliverable 10)
    depends on those rows existing, so they are written independently and
    committed before the exception propagates.

    Deliberately best-effort: an audit failure must never mask the original
    security refusal.
    """
    from src.db.base import SessionLocal

    session = SessionLocal()
    try:
        session.add(
            AuditLog(
                actor_id=actor.id if actor else None,
                actor_role=actor.role if actor else None,
                entity_type=entity_type,
                entity_id=str(entity_id),
                action=action,
                after=_jsonable(details) if details else None,
                reason=reason,
                request_id=getattr(getattr(request, "state", None), "request_id", None),
                ip_address=_client_ip(request),
            )
        )
        session.commit()
    except Exception:  # pragma: no cover - never mask the security refusal
        session.rollback()
    finally:
        session.close()


def _client_ip(request: Request | None) -> str | None:
    if request is None:
        return None
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None
