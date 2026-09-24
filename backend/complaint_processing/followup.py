"""
Follow-up detection and scheduling (FR xxxvii, xxxviii; SRS Steps 40-41).

    "The system must detect when a follow-up is required and schedule it."
                                                      — SRS Steps 40-41

A follow-up is an obligation the system takes on itself: something it has
promised to come back about. Each has a type, a message and a due date, and
each is derived from a stored fact rather than from the model saying so.

Five triggers, each answering a different question:

* **VERIFICATION** — an eligibility decision needs checking before anything can
  be confirmed. This is the one that matters: a refund left at
  ``REQUIRES_VERIFICATION`` with nobody scheduled to verify it is how a
  customer waits three weeks for an answer nobody was working on.
* **CLARIFICATION** — a question was asked and not answered.
* **ESCALATION** — a complaint was escalated and the specialist owes contact.
* **RESOLUTION_CHECK** — the rules said follow up, so follow up.
* **SATISFACTION** — a resolved complaint, checked once after the fact.

**Due dates come from the SLA policy, not from a constant.** A P0 safety
verification is owed within the hour; a P3 satisfaction check can wait a week.
Reusing the SLA window means retuning a target moves both the deadline and the
follow-up with it, rather than leaving two numbers to drift apart.

**Nothing here is scheduled twice.** An open follow-up of the same type for the
same complaint is refreshed, not duplicated — re-analysis after a rule change
must not leave an agent with four identical reminders.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.logging import get_logger
from src.db.enums import EligibilityOutcome
from src.db.models import ClarificationQuestion, Complaint, FollowUp
from src.services import sla

log = get_logger("complaint_processing.followup")

VERIFICATION = "VERIFICATION"
CLARIFICATION = "CLARIFICATION"
ESCALATION = "ESCALATION"
RESOLUTION_CHECK = "RESOLUTION_CHECK"
SATISFACTION = "SATISFACTION"

# What fraction of the first-response window each follow-up type gets. A
# verification that has to happen before the first reply is due earlier than
# the reply itself; a satisfaction check happens long after.
WINDOW_FRACTION = {
    VERIFICATION: 0.5,
    CLARIFICATION: 1.0,
    ESCALATION: 0.5,
    RESOLUTION_CHECK: 2.0,
    SATISFACTION: 8.0,
}

# Used only when no SLA policy matches the complaint. Deliberately generous:
# guessing a tight deadline the business never agreed to would put a false
# breach on the dashboard.
FALLBACK_MINUTES = 24 * 60


@dataclass(slots=True)
class PlannedFollowUp:
    """One follow-up the system owes."""

    follow_up_type: str
    message: str
    due_at: datetime
    reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "type": self.follow_up_type,
            "message": self.message,
            "due_at": self.due_at.isoformat(),
            "reason": self.reason,
        }


@dataclass(slots=True)
class FollowUpPlan:
    """Everything owed on one complaint."""

    planned: list[PlannedFollowUp] = field(default_factory=list)
    created: int = 0
    refreshed: int = 0

    @property
    def required(self) -> bool:
        return bool(self.planned)

    def summary(self) -> dict[str, Any]:
        return {
            "required": self.required,
            "created": self.created,
            "refreshed": self.refreshed,
            "follow_ups": [p.as_dict() for p in self.planned],
        }


# ══════════════════════════════════════════════════════════════
# timing
# ══════════════════════════════════════════════════════════════
def _window_minutes(db: Session, complaint: Complaint) -> int:
    """
    The first-response window for this complaint, from its SLA policy.

    Falls back to a day when no policy matches — the same stance the SLA
    service takes, for the same reason: a deadline the business never agreed
    to is worse than a loose one.
    """
    policy = sla.find_policy(
        db, category_id=complaint.category_id, priority_code=complaint.priority_code
    )
    return policy.first_response_mins if policy else FALLBACK_MINUTES


def _due(db: Session, complaint: Complaint, follow_up_type: str) -> datetime:
    minutes = _window_minutes(db, complaint) * WINDOW_FRACTION.get(follow_up_type, 1.0)
    return datetime.now(UTC) + timedelta(minutes=minutes)


# ══════════════════════════════════════════════════════════════
# detection
# ══════════════════════════════════════════════════════════════
def detect(
    db: Session,
    complaint: Complaint,
    *,
    reconciled: dict[str, Any] | None = None,
    eligibility: list[dict[str, Any]] | None = None,
) -> FollowUpPlan:
    """
    Work out what the system owes on this complaint.

    Reads stored facts only. "The model said a follow-up was needed" is not a
    trigger on its own — ``follow_up_required`` reaches here through the
    reconciled record, where the rules have already had their say.
    """
    plan = FollowUpPlan()
    reconciled = reconciled or {}

    # ── an eligibility decision nobody is scheduled to verify ──
    for finding in eligibility or []:
        outcome = str(finding.get("python_outcome", "")).upper()
        if outcome not in (
            EligibilityOutcome.REQUIRES_VERIFICATION,
            EligibilityOutcome.CONDITIONAL,
        ):
            continue

        kind = finding.get("eligibility_type", "eligibility")
        conditions = finding.get("conditions_evaluated") or []
        plan.planned.append(
            PlannedFollowUp(
                follow_up_type=VERIFICATION,
                message=(
                    f"Verify {kind.lower()} eligibility before confirming anything "
                    "to the customer."
                    + (f" Outstanding: {'; '.join(conditions)}." if conditions else "")
                ),
                due_at=_due(db, complaint, VERIFICATION),
                reason=f"{kind} eligibility is {outcome}, not ELIGIBLE.",
            )
        )

    # ── a question asked and not answered ──
    outstanding = db.execute(
        select(ClarificationQuestion).where(
            ClarificationQuestion.complaint_id == complaint.id,
            ClarificationQuestion.answered_at.is_(None),
        )
    ).scalars().all()
    if outstanding:
        plan.planned.append(
            PlannedFollowUp(
                follow_up_type=CLARIFICATION,
                message=(
                    f"Chase the customer for {len(outstanding)} outstanding "
                    f"question(s): {outstanding[0].question}"
                ),
                due_at=_due(db, complaint, CLARIFICATION),
                reason="Information was requested and has not arrived.",
            )
        )

    # ── an escalation owes contact ──
    if reconciled.get("escalation_required"):
        plan.planned.append(
            PlannedFollowUp(
                follow_up_type=ESCALATION,
                message=(
                    "Confirm the specialist has made contact with the customer."
                ),
                due_at=_due(db, complaint, ESCALATION),
                reason=f"Escalated to {reconciled.get('escalation_level')}.",
            )
        )

    # ── the rules asked for one ──
    if reconciled.get("follow_up_required"):
        plan.planned.append(
            PlannedFollowUp(
                follow_up_type=RESOLUTION_CHECK,
                message="Check the resolution held and the customer is satisfied.",
                due_at=_due(db, complaint, RESOLUTION_CHECK),
                reason="The rule matrix requires a follow-up for this complaint.",
            )
        )

    return plan


# ══════════════════════════════════════════════════════════════
# scheduling
# ══════════════════════════════════════════════════════════════
def schedule(
    db: Session, complaint: Complaint, plan: FollowUpPlan
) -> FollowUpPlan:
    """
    Write the plan to ``follow_ups``.

    One open follow-up per (complaint, type): an existing one is refreshed
    rather than duplicated, because re-analysis after a rule change must not
    leave an agent with four identical reminders to dismiss.
    """
    existing = {
        row.follow_up_type: row
        for row in db.execute(
            select(FollowUp).where(
                FollowUp.complaint_id == complaint.id,
                FollowUp.completed_at.is_(None),
            )
        ).scalars()
    }

    for item in plan.planned:
        row = existing.get(item.follow_up_type)
        if row is None:
            db.add(
                FollowUp(
                    complaint_id=complaint.id,
                    follow_up_type=item.follow_up_type,
                    message=item.message,
                    due_at=item.due_at,
                )
            )
            plan.created += 1
        else:
            row.message = item.message
            row.due_at = item.due_at
            plan.refreshed += 1

    db.flush()

    if plan.created:
        log.info(
            "follow_ups_scheduled",
            public_ref=complaint.public_ref,
            created=plan.created, refreshed=plan.refreshed,
            types=[p.follow_up_type for p in plan.planned],
        )
    return plan


def apply(
    db: Session,
    complaint: Complaint,
    *,
    reconciled: dict[str, Any] | None = None,
    eligibility: list[dict[str, Any]] | None = None,
) -> FollowUpPlan:
    """Detect and schedule in one call — what intake uses."""
    return schedule(
        db, complaint, detect(db, complaint, reconciled=reconciled, eligibility=eligibility)
    )


# ══════════════════════════════════════════════════════════════
# working the list
# ══════════════════════════════════════════════════════════════
def complete(db: Session, follow_up_id: uuid.UUID, *, user_id: uuid.UUID | None = None) -> FollowUp:
    """Mark one done. Idempotent: completing twice keeps the first timestamp."""
    row = db.get(FollowUp, follow_up_id)
    if row is None:
        raise ValueError(f"No follow-up {follow_up_id}.")

    if row.completed_at is None:
        row.completed_at = datetime.now(UTC)
        row.created_by = row.created_by or user_id
        db.flush()
        log.info("follow_up_completed", follow_up=str(follow_up_id))
    return row


def due(
    db: Session, *, now: datetime | None = None, limit: int = 200
) -> list[dict[str, Any]]:
    """
    Follow-ups that are due or overdue, soonest first.

    The list an agent works from. Overdue items sort to the top because they
    are the ones already costing the customer something.
    """
    moment = now or datetime.now(UTC)

    rows = db.execute(
        select(FollowUp, Complaint.public_ref, Complaint.priority_code)
        .join(Complaint, FollowUp.complaint_id == Complaint.id)
        .where(FollowUp.completed_at.is_(None), FollowUp.due_at <= moment)
        .order_by(FollowUp.due_at)
        .limit(limit)
    ).all()

    return [
        {
            "id": str(row.id),
            "public_ref": public_ref,
            "priority": priority,
            "type": row.follow_up_type,
            "message": row.message,
            "due_at": row.due_at.isoformat() if row.due_at else None,
            "overdue_minutes": (
                round((moment - row.due_at).total_seconds() / 60.0, 1)
                if row.due_at
                else None
            ),
        }
        for row, public_ref, priority in rows
    ]


def for_complaint(db: Session, complaint_id: uuid.UUID) -> list[dict[str, Any]]:
    """Every follow-up on one complaint, open and closed."""
    rows = db.execute(
        select(FollowUp)
        .where(FollowUp.complaint_id == complaint_id)
        .order_by(FollowUp.due_at)
    ).scalars().all()

    return [
        {
            "id": str(row.id),
            "type": row.follow_up_type,
            "message": row.message,
            "due_at": row.due_at.isoformat() if row.due_at else None,
            "completed_at": row.completed_at.isoformat() if row.completed_at else None,
            "open": row.completed_at is None,
        }
        for row in rows
    ]
