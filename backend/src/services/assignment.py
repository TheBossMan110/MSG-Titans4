"""
Who a new complaint goes to.

The rules decide the team; this decides the person. Without it a complaint sat
"unassigned" until someone happened to claim it, and one routed to a team with
no agent reached nobody at all -- only a screen an administrator was watching.

    1. the least-loaded active agent on the owning team
    2. else on the supporting team
    3. else any active agent in the company

The third step matters most for small companies. The department list is a
shared template of nine teams; a company with two agents cannot staff them all,
and a complaint routed to an empty team must still reach a person. The team on
the complaint does not change, so the manager still sees where it belongs.

A person can always reassign it afterwards. Nothing here touches a complaint
that already has an owner.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.core.logging import get_logger
from src.db.enums import ComplaintStatus, UserRole
from src.db.models import Complaint, User
from src.services import lifecycle
from src.services.audit import record_audit

log = get_logger("services.assignment")

_CLOSED = (ComplaintStatus.RESOLVED, ComplaintStatus.CLOSED)
# Only these move to ASSIGNED. A complaint waiting for a reviewer or escalated
# keeps that status: gaining an owner does not end the review.
_READY = (ComplaintStatus.ANALYZED, ComplaintStatus.VALIDATED)


def assign_new_complaint(db: Session, complaint: Complaint) -> User | None:
    """Give a newly analysed complaint an owner. Returns who, or ``None`` if the company has no agent."""
    if complaint.assigned_to is not None:
        return None

    # Filtered by the complaint's company explicitly, not left to the session:
    # the mailbox poller has no signed-in user, so its session is not bound to one.
    company = complaint.organisation_id
    agents = db.execute(
        select(User).where(
            User.organisation_id == company,
            User.role == UserRole.AGENT,
            User.is_active.is_(True),
        )
    ).scalars().all()
    if not agents:
        log.info("complaint_unassigned_no_agents", public_ref=complaint.public_ref)
        return None

    load = dict(db.execute(
        select(Complaint.assigned_to, func.count(Complaint.id))
        .where(
            Complaint.organisation_id == company,
            Complaint.assigned_to.in_([a.id for a in agents]),
            Complaint.status.not_in(_CLOSED),
        )
        .group_by(Complaint.assigned_to)
    ).all())

    owning = [a for a in agents if a.department_id and a.department_id == complaint.department_id]
    supporting = [a for a in agents if a.department_id and a.department_id == complaint.support_department_id]
    chosen = min(owning or supporting or agents, key=lambda a: (load.get(a.id, 0), a.full_name))

    complaint.assigned_to = chosen.id
    if complaint.status in _READY:
        lifecycle.transition(
            db, complaint, ComplaintStatus.ASSIGNED,
            reason=f"Assigned automatically to {chosen.full_name}.",
        )
    record_audit(
        db, entity_type="complaint", entity_id=complaint.id, action="AUTO_ASSIGN",
        after={"assigned_to": str(chosen.id), "assignee": chosen.full_name},
        reason="owning team" if owning else ("supporting team" if supporting else "no agent on the routed team"),
    )
    db.flush()
    log.info("complaint_auto_assigned", public_ref=complaint.public_ref, assignee=str(chosen.id))
    return chosen


__all__ = ["assign_new_complaint"]
