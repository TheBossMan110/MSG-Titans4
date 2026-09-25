"""
The audit trail, readable (FR lxiv; SRS Step 59).

Every consequential act already writes a row here: logins and refusals, rule
and configuration edits, reviewer overrides, status changes, document
activations, exports. What was missing was any way to *read* the trail except
one complaint at a time -- so the Live Modification Challenge wrote a
RULE_CHANGE row for every edit an evaluator made, and nothing on screen could
show it to them.

Read-only, on purpose. The table is append-only at the database level and
this router adds no way to change that.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

from schemas.audit import AuditActionCountOut, AuditEntryOut
from schemas.common import Page
from src.core.deps import DbSession, require_role
from src.db.enums import UserRole
from src.db.models import AuditLog, User

router = APIRouter(prefix="/audit", tags=["Audit"])

# Who may read the whole trail. An agent sees their own complaints' history on
# the complaint; the organisation-wide log is oversight, and oversight is a
# manager's, an administrator's and an evaluator's job.
READERS = (UserRole.MANAGER, UserRole.ADMIN, UserRole.EVALUATOR)
ReadAccess = Depends(require_role(*READERS))

MAX_TRAIL = 500


def _entry(row: AuditLog, email: str | None) -> AuditEntryOut:
    return AuditEntryOut(
        id=row.id,
        at=row.created_at,
        actor=email,
        actor_role=row.actor_role,
        entity_type=row.entity_type,
        entity_id=row.entity_id,
        action=row.action,
        before=row.before,
        after=row.after,
        reason=row.reason,
        request_id=row.request_id,
    )


@router.get(
    "",
    response_model=Page[AuditEntryOut],
    dependencies=[ReadAccess],
    summary="The organisation-wide audit trail, newest first",
)
def list_audit(
    db: DbSession,
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    entity_type: str | None = Query(None, max_length=64),
    action: str | None = Query(None, max_length=48),
    actor: str | None = Query(None, max_length=320, description="Actor email."),
    entity_id: str | None = Query(None, max_length=64),
) -> Page[AuditEntryOut]:
    """
    Every recorded act, filterable by what was touched, what was done and who
    did it.

    ``before`` and ``after`` are returned as stored: two snapshots, not a diff.
    SRS Step 59 wants the original recommendation and the reviewer's decision
    both on the record, and a diff would keep only what changed.
    """
    query = select(AuditLog, User.email).outerjoin(User, AuditLog.actor_id == User.id)

    if entity_type:
        query = query.where(AuditLog.entity_type == entity_type.strip().lower())
    if action:
        query = query.where(AuditLog.action == action.strip().upper())
    if entity_id:
        query = query.where(AuditLog.entity_id == entity_id.strip())
    if actor:
        query = query.where(func.lower(User.email) == actor.strip().lower())

    total = db.execute(
        select(func.count()).select_from(query.subquery())
    ).scalar_one()

    rows = db.execute(
        query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .offset((page - 1) * size)
        .limit(size)
    ).all()

    return Page[AuditEntryOut](
        items=[_entry(row, email) for row, email in rows],
        total=total,
        page=page,
        size=size,
    )


@router.get(
    "/actions",
    response_model=list[AuditActionCountOut],
    dependencies=[ReadAccess],
    summary="Every action that has been recorded, with a count",
)
def audit_actions(db: DbSession) -> list[AuditActionCountOut]:
    """
    What the trail contains, for a filter control and for the dashboard's
    "what changed" figure. Read from the rows, so an action that has never
    happened is absent rather than listed at zero.
    """
    rows = db.execute(
        select(AuditLog.action, func.count())
        .group_by(AuditLog.action)
        .order_by(func.count().desc())
    ).all()
    return [AuditActionCountOut(action=action, count=count) for action, count in rows]


@router.get(
    "/{entity_type}/{entity_id}",
    response_model=list[AuditEntryOut],
    dependencies=[ReadAccess],
    summary="One entity's full trail, oldest first",
)
def entity_trail(entity_type: str, entity_id: str, db: DbSession) -> list[AuditEntryOut]:
    """
    How one thing got to its current state.

    Oldest first, because a trail is read forwards. Capped, because an entity
    with more than five hundred recorded acts is a bug report rather than a
    page.
    """
    rows = db.execute(
        select(AuditLog, User.email)
        .outerjoin(User, AuditLog.actor_id == User.id)
        .where(
            AuditLog.entity_type == entity_type.strip().lower(),
            AuditLog.entity_id == entity_id.strip(),
        )
        .order_by(AuditLog.created_at.asc(), AuditLog.id.asc())
        .limit(MAX_TRAIL)
    ).all()
    return [_entry(row, email) for row, email in rows]
