"""
Complaint lifecycle (FR lxv; SRS Step 60).

    "The system must track complaint status through its lifecycle."
                                                        — SRS Step 60

Every status a complaint has ever held, who moved it and why. The vocabulary
and its CHECK constraint already existed; what did not was any record of the
*transitions*, and a status column with no history answers "where is it now"
but never "how did it get here" — which is the question asked when something
went wrong.

**Permitted transitions are declared, not implied.** ``TRANSITIONS`` is the
whole graph. A move that is not in it is refused, because the alternative is a
complaint that reaches CLOSED without anyone resolving it and a dashboard that
counts it as handled.

**The pipeline moves a complaint too, and it goes through the same door.**
Intake and review both call :func:`transition`, so the history is the complete
account rather than only the part a human touched. A machine transition simply
has no actor, and that is itself worth recording.

**A refused transition is an error, not a silent no-op.** Swallowing it would
leave the caller believing the complaint moved.

**REOPENED exists so that closure is not a lie.** A complaint that comes back
is not a new complaint — the repeat count depends on that, and so does every
question about whether the first resolution worked.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.logging import get_logger
from src.db.enums import ComplaintStatus
from src.db.models import Complaint, ComplaintStatusHistory, User

log = get_logger("services.lifecycle")

S = ComplaintStatus

# The lifecycle graph. Read as "from -> everything it may become".
#
# MANUAL_REVIEW is reachable from almost anywhere on purpose: a complaint can
# turn out to need a human at any point, and a graph that made that awkward
# would be a graph people route around.
TRANSITIONS: dict[str, frozenset[str]] = {
    S.NEW: frozenset({S.ANALYZING, S.MANUAL_REVIEW, S.FAILED, S.CLOSED}),
    S.ANALYZING: frozenset({S.ANALYZED, S.MANUAL_REVIEW, S.ESCALATED, S.FAILED}),
    S.ANALYZED: frozenset(
        {S.VALIDATED, S.ASSIGNED, S.MANUAL_REVIEW, S.ESCALATED, S.CLOSED}
    ),
    S.VALIDATED: frozenset({S.ASSIGNED, S.MANUAL_REVIEW, S.ESCALATED, S.CLOSED}),
    S.ASSIGNED: frozenset(
        {S.IN_PROGRESS, S.AWAITING_CUSTOMER, S.MANUAL_REVIEW, S.ESCALATED, S.RESOLVED}
    ),
    S.IN_PROGRESS: frozenset(
        {S.AWAITING_CUSTOMER, S.RESOLVED, S.MANUAL_REVIEW, S.ESCALATED, S.ASSIGNED}
    ),
    S.AWAITING_CUSTOMER: frozenset(
        {S.IN_PROGRESS, S.ASSIGNED, S.RESOLVED, S.ESCALATED, S.MANUAL_REVIEW, S.CLOSED}
    ),
    S.ESCALATED: frozenset(
        {S.IN_PROGRESS, S.ASSIGNED, S.RESOLVED, S.MANUAL_REVIEW, S.AWAITING_CUSTOMER}
    ),
    S.MANUAL_REVIEW: frozenset(
        {S.ANALYZED, S.VALIDATED, S.ASSIGNED, S.ESCALATED, S.IN_PROGRESS, S.CLOSED}
    ),
    # RESOLVED is not the end. Closure is, and a customer who disagrees sends
    # it back through REOPENED rather than filing a complaint about a complaint.
    S.RESOLVED: frozenset({S.CLOSED, S.REOPENED, S.AWAITING_CUSTOMER}),
    S.CLOSED: frozenset({S.REOPENED}),
    S.REOPENED: frozenset(
        {S.ANALYZING, S.ASSIGNED, S.IN_PROGRESS, S.ESCALATED, S.MANUAL_REVIEW}
    ),
    # A complaint whose analysis failed is still a complaint somebody has to
    # work on by hand. FAILED is a dead end only for the machine.
    S.FAILED: frozenset({S.ANALYZING, S.MANUAL_REVIEW, S.CLOSED}),
}

# Re-analysis is legitimate from any status that is still open: a rule change,
# a policy update or a provider coming back all justify running the pipelines
# again, and the complaint passes back through ANALYZING when they do. Adding
# it here rather than forcing past the graph keeps one definition of what is
# permitted. RESOLVED and CLOSED are excluded deliberately -- re-analysing a
# closed complaint means reopening it first, on purpose and on the record.
for _status, _allowed in list(TRANSITIONS.items()):
    if _status not in (S.RESOLVED, S.CLOSED, S.ANALYZING):
        TRANSITIONS[_status] = _allowed | {S.ANALYZING}

# Statuses that stop the SLA clock, and the column each one stamps.
TERMINAL: frozenset[str] = frozenset({S.RESOLVED, S.CLOSED})

_STAMPS: dict[str, str] = {
    S.RESOLVED: "resolved_at",
    S.CLOSED: "closed_at",
}

# Moves a human may not make directly. These are consequences of the pipeline
# or the review workflow, and letting an agent set them by hand would put the
# complaint in a state nothing downstream produced.
MACHINE_ONLY: frozenset[str] = frozenset({S.ANALYZING, S.ANALYZED, S.FAILED})


class TransitionRefused(Exception):
    """The requested move is not permitted from the current status."""

    def __init__(self, current: str, requested: str, detail: str = ""):
        self.current, self.requested = current, requested
        self.detail = detail or (
            f"A complaint in {current} cannot move to {requested}. "
            f"Permitted from {current}: {', '.join(sorted(permitted_from(current))) or 'nothing'}."
        )
        super().__init__(self.detail)


@dataclass(slots=True)
class TransitionResult:
    """What one move changed."""

    complaint_id: uuid.UUID
    from_status: str | None
    to_status: str
    changed: bool
    reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "complaint_id": str(self.complaint_id),
            "from_status": self.from_status,
            "to_status": self.to_status,
            "changed": self.changed,
            "reason": self.reason,
        }


def permitted_from(status: str | None) -> frozenset[str]:
    """Everything a complaint in ``status`` may become."""
    return TRANSITIONS.get(str(status or ""), frozenset())


def is_permitted(current: str | None, requested: str) -> bool:
    """
    Whether the move is in the graph.

    A move to the status the complaint already holds is permitted and does
    nothing: re-analysis and retries must be safe to repeat, and refusing a
    no-op would turn an idempotent call into an error.
    """
    if current == requested:
        return True
    return requested in permitted_from(current)


def transition(
    db: Session,
    complaint: Complaint,
    to_status: str,
    *,
    actor: User | None = None,
    reason: str | None = None,
    force: bool = False,
) -> TransitionResult:
    """
    Move one complaint, recording the move.

    ``force`` exists for the pipeline's own failure path: a complaint whose
    analysis raised must land in FAILED from wherever it happened to be, and a
    refusal there would lose the complaint rather than record the problem. It
    is not reachable from the API.
    """
    current = complaint.status
    to_status = str(to_status)

    if to_status not in TRANSITIONS:
        raise TransitionRefused(current, to_status, f"{to_status} is not a status.")

    if current == to_status:
        return TransitionResult(complaint.id, current, to_status, changed=False,
                                reason=reason)

    if not force and not is_permitted(current, to_status):
        raise TransitionRefused(current, to_status)

    complaint.status = to_status

    stamp = _STAMPS.get(to_status)
    if stamp and getattr(complaint, stamp, None) is None:
        setattr(complaint, stamp, datetime.now(UTC))

    # Reopening clears the closure stamps. Leaving them would make a complaint
    # that is open again look resolved to every report that reads the dates
    # rather than the status.
    if to_status == S.REOPENED:
        complaint.resolved_at = None
        complaint.closed_at = None

    db.add(
        ComplaintStatusHistory(
            complaint_id=complaint.id,
            from_status=current,
            to_status=to_status,
            changed_by=actor.id if actor else None,
            reason=reason,
        )
    )
    db.flush()

    log.info(
        "complaint_status_changed",
        public_ref=complaint.public_ref,
        from_status=current, to_status=to_status,
        by=actor.email if actor else "pipeline",
    )
    return TransitionResult(complaint.id, current, to_status, changed=True, reason=reason)


def history(db: Session, complaint_id: uuid.UUID) -> list[dict[str, Any]]:
    """Every transition, oldest first — the account of how it got here."""
    rows = db.execute(
        select(ComplaintStatusHistory, User.email)
        .outerjoin(User, ComplaintStatusHistory.changed_by == User.id)
        .where(ComplaintStatusHistory.complaint_id == complaint_id)
        .order_by(ComplaintStatusHistory.created_at, ComplaintStatusHistory.id)
    ).all()

    return [
        {
            "from_status": row.from_status,
            "to_status": row.to_status,
            # "pipeline" rather than null: a machine transition is not an
            # unknown actor, and the distinction matters when reading a trail.
            "changed_by": email or "pipeline",
            "reason": row.reason,
            "at": row.created_at.isoformat() if row.created_at else None,
        }
        for row, email in rows
    ]


def available_actions(complaint: Complaint) -> list[str]:
    """
    What a human may move this complaint to next.

    Drives the agent view's status control, so the options offered are the
    options that will be accepted — an interface that offers a move the API
    refuses teaches people to distrust it.
    """
    return sorted(permitted_from(complaint.status) - MACHINE_ONLY)
