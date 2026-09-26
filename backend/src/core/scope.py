"""
Which complaints a member of staff may see (FR ii, Role-Based Access Control).

    Customer  -> their own complaints only (enforced where customers read, in
                 src/api/v1/complaints.py -- they never reach these endpoints)
    Agent     -> their team's complaints, and any complaint assigned to them
    Reviewer, manager, administrator, evaluator -> every complaint

An agent handles cases; they do not browse the whole register. "Their team"
is the complaint's owning or supporting department. An agent with no
department sees only what is assigned to them.

Out-of-scope references answer 404, not 403, so an agent cannot use the API
to discover which references exist in other teams.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import or_, select

from src.core.deps import CurrentUser, DbSession
from src.core.errors import NotFoundError
from src.db.enums import UserRole
from src.db.models import Complaint


def is_scoped(user: Any) -> bool:
    """True when this caller sees only part of the register."""
    return str(getattr(user, "role", "")) == UserRole.AGENT


def agent_clause(user: Any):
    """The SQL condition for "complaints this agent may see"."""
    conditions = [Complaint.assigned_to == user.id]
    if user.department_id is not None:
        conditions += [
            Complaint.department_id == user.department_id,
            Complaint.support_department_id == user.department_id,
        ]
    return or_(*conditions)


def restrict(query, user: Any):
    """Narrow a complaint query to what the caller may see."""
    return query.where(agent_clause(user)) if is_scoped(user) else query


def can_see(complaint: Any, user: Any) -> bool:
    if not is_scoped(user):
        return True
    if complaint.assigned_to == user.id:
        return True
    return user.department_id is not None and user.department_id in (
        complaint.department_id, complaint.support_department_id,
    )


def complaint_in_scope(ref: str, db: DbSession, user: CurrentUser) -> None:
    """
    Route guard for ``/{ref}`` endpoints. Unknown references are left to the
    endpoint's own 404; a known one outside the agent's scope gets the same 404.
    """
    if not is_scoped(user):
        return
    query = select(Complaint.assigned_to, Complaint.department_id, Complaint.support_department_id)
    try:
        row = db.execute(query.where(Complaint.id == uuid.UUID(str(ref)))).first()
    except (ValueError, AttributeError):
        row = db.execute(query.where(Complaint.public_ref == ref.strip().upper())).first()
    if row is None:
        return
    assigned_to, department_id, support_department_id = row
    if assigned_to == user.id:
        return
    if user.department_id is not None and user.department_id in (department_id, support_department_id):
        return
    raise NotFoundError(f"No complaint with reference '{ref}'.")


__all__ = ["agent_clause", "can_see", "complaint_in_scope", "is_scoped", "restrict"]
