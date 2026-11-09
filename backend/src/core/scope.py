"""
Which complaints a member of staff may see (FR ii, Role-Based Access Control).

Each organisation's administrator sets this per role on the Access Control
page (src/core/permissions.py, ``complaint_scope``):

    assigned -> only the complaints assigned to them
    team     -> their team's complaints, and any complaint assigned to them
    all      -> every complaint in their organisation

The defaults are what the platform always did: agents ``team``; reviewers and
managers ``all``. Administrators and evaluators always see everything in their
organisation, and customers only their own (enforced where customers read, in
src/api/v1/complaints.py -- they never reach these endpoints). Other
organisations are never in reach at all: src/core/tenancy.py filters below
this.

"Their team" is the complaint's owning or supporting department. Someone with
``team`` scope but no department sees only what is assigned to them.

Out-of-scope references answer 404, not 403, so nobody can use the API to
discover which references exist in other teams.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import or_, select

from src.core.deps import CurrentUser, DbSession
from src.core.errors import NotFoundError
from src.db.enums import UserRole
from src.db.models import Complaint


def _scope(user: Any) -> str:
    from src.core.permissions import complaint_scope

    return complaint_scope(user)


def is_scoped(user: Any) -> bool:
    """True when this caller sees only part of the register."""
    return str(getattr(user, "role", "")) != UserRole.CUSTOMER and _scope(user) in ("assigned", "team")


def _sees_team(user: Any) -> bool:
    return _scope(user) == "team" and user.department_id is not None


def agent_clause(user: Any):
    """The SQL condition for "complaints this person may see"."""
    conditions = [Complaint.assigned_to == user.id]
    if _sees_team(user):
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
    return _sees_team(user) and user.department_id in (
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
    if _sees_team(user) and user.department_id in (department_id, support_department_id):
        return
    raise NotFoundError(f"No complaint with reference '{ref}'.")


__all__ = ["agent_clause", "can_see", "complaint_in_scope", "is_scoped", "restrict"]
