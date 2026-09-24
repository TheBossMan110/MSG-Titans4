"""
Manual review queue and reviewer overrides (FR lxi-lxiii; SRS Steps 57-59).

    "Complaints must be routed to a manual review queue when the system cannot
     decide safely. Reviewers must be able to approve, modify, reclassify,
     reassign or escalate, and every action must be recorded."
                                                      — SRS Steps 57-59

**The queue is derived, never hand-populated.** An item exists because a stored
``verification_decisions`` row says ``requires_review``, or because the guard
blocked a reply. Deciding twice — once in the comparison engine and again in a
separate queueing rule — is how the two drift apart, and then the queue stops
meaning what the decision says.

**An override is a recorded act, not an edit.** Every reviewer action writes a
``review_actions`` row carrying the before and after values, so the audit shows
what the system decided, what the human changed it to, and why. A complaint
whose category was changed by a reviewer must never look like one the system
classified correctly in the first place.

**The escalation floor survives a reviewer.** A reviewer may raise an
escalation; they cannot lower it below the level the mandatory rules derived.
That is not distrust of the reviewer — it is SRS 1.8 #7, which says the floor
holds regardless of what any later stage concludes. A reviewer who genuinely
needs it lowered is asking for a rule change, and that is a different, audited
act.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from comparison_engine.engine import latest_decision
from comparison_engine.ladders import at_or_above, load_ladders
from src.core.logging import get_logger
from src.db.enums import (
    ComplaintStatus,
    EscalationTrigger,
    ReviewActionType,
    ReviewStatus,
)
from src.db.models import (
    Category,
    Complaint,
    Department,
    Escalation,
    ReviewAction,
    ReviewQueueItem,
    Subcategory,
    User,
    ValidationRun,
)
from src.services import lifecycle

log = get_logger("services.review")

# Actions that change a stored decision, as opposed to commenting on it.
OVERRIDING_ACTIONS = frozenset(
    {
        ReviewActionType.MODIFY,
        ReviewActionType.RECLASSIFY,
        ReviewActionType.REASSIGN,
        ReviewActionType.ESCALATE,
        ReviewActionType.OVERRIDE,
    }
)

# Actions that close the queue item.
CLOSING_ACTIONS = frozenset({ReviewActionType.APPROVE, ReviewActionType.REJECT})


class OverrideRefused(Exception):
    """A reviewer asked for something policy does not permit."""


@dataclass(slots=True)
class OverrideResult:
    """What one reviewer action changed."""

    action: str
    is_override: bool
    before: dict[str, Any] = field(default_factory=dict)
    after: dict[str, Any] = field(default_factory=dict)
    queue_closed: bool = False
    escalation_raised: bool = False

    @property
    def changed(self) -> dict[str, Any]:
        return {
            key: {"before": self.before.get(key), "after": self.after.get(key)}
            for key in self.after
            if self.before.get(key) != self.after.get(key)
        }

    def summary(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "is_override": self.is_override,
            "changed": self.changed,
            "queue_closed": self.queue_closed,
            "escalation_raised": self.escalation_raised,
        }


# ══════════════════════════════════════════════════════════════
# the queue
# ══════════════════════════════════════════════════════════════
def enqueue(
    db: Session,
    complaint: Complaint,
    *,
    reasons: list[str] | None = None,
) -> ReviewQueueItem | None:
    """
    Put a complaint in the queue, or leave it there.

    Idempotent: one open item per complaint. Re-analysing a complaint that is
    already queued refreshes its reasons and priority rather than stacking a
    second item a reviewer would have to close twice.

    Returns ``None`` when the complaint needs no review.
    """
    decision = latest_decision(db, complaint.id)
    derived = list(decision.review_reasons or []) if decision else []
    combined = list(dict.fromkeys([*(reasons or []), *derived]))

    needs_review = bool(combined) or (
        decision.requires_review if decision else False
    )
    if not needs_review:
        return None

    existing = db.execute(
        select(ReviewQueueItem).where(
            ReviewQueueItem.complaint_id == complaint.id,
            ReviewQueueItem.status.in_((ReviewStatus.OPEN, ReviewStatus.IN_REVIEW)),
        )
    ).scalars().first()

    if existing is not None:
        existing.reasons = combined
        existing.priority_code = complaint.priority_code
        db.flush()
        return existing

    item = ReviewQueueItem(
        complaint_id=complaint.id,
        reasons=combined,
        priority_code=complaint.priority_code,
        status=ReviewStatus.OPEN,
    )
    db.add(item)

    # A resolved or closed complaint is not dragged back into the queue by a
    # late finding; it would have to be reopened first, deliberately.
    if complaint.status not in (ComplaintStatus.RESOLVED, ComplaintStatus.CLOSED):
        lifecycle.transition(
            db, complaint, ComplaintStatus.MANUAL_REVIEW,
            reason="Queued for review: " + ", ".join(combined),
        )

    db.flush()
    log.info("review_enqueued", public_ref=complaint.public_ref, reasons=combined)
    return item


def open_item(db: Session, complaint_id: uuid.UUID) -> ReviewQueueItem | None:
    return db.execute(
        select(ReviewQueueItem).where(
            ReviewQueueItem.complaint_id == complaint_id,
            ReviewQueueItem.status.in_((ReviewStatus.OPEN, ReviewStatus.IN_REVIEW)),
        )
    ).scalars().first()


def claim(db: Session, item: ReviewQueueItem, reviewer: User) -> ReviewQueueItem:
    """Take an item, so two reviewers do not work the same complaint."""
    item.assigned_to = reviewer.id
    item.status = ReviewStatus.IN_REVIEW
    db.flush()
    return item


def queue_depth(db: Session) -> dict[str, int]:
    """How much is waiting, by status."""
    rows = db.execute(
        select(ReviewQueueItem.status, func.count()).group_by(ReviewQueueItem.status)
    ).all()
    return dict(rows)


# ══════════════════════════════════════════════════════════════
# overrides
# ══════════════════════════════════════════════════════════════
def _snapshot(complaint: Complaint) -> dict[str, Any]:
    return {
        "category": complaint.category.code if complaint.category else None,
        "subcategory": complaint.subcategory.code if complaint.subcategory else None,
        "department": complaint.department.code if complaint.department else None,
        "urgency": complaint.urgency,
        "priority": complaint.priority_code,
        "escalation": complaint.escalation_code,
        "status": complaint.status,
        "assigned_to": str(complaint.assigned_to) if complaint.assigned_to else None,
    }


def _resolve(db: Session, model: Any, code: str | None) -> Any:
    if not code:
        return None
    row = db.execute(
        select(model).where(model.code == str(code).strip().upper())
    ).scalars().first()
    if row is None:
        raise OverrideRefused(f"'{code}' is not a known {model.__name__.lower()}.")
    return row


def escalation_floor(db: Session, complaint_id: uuid.UUID) -> str | None:
    """The level the mandatory rules derived, which nothing may go below."""
    run = db.execute(
        select(ValidationRun)
        .where(ValidationRun.complaint_id == complaint_id)
        .order_by(ValidationRun.created_at.desc())
    ).scalars().first()
    return run.escalation_floor_code if run else None


def apply_action(
    db: Session,
    complaint: Complaint,
    *,
    action: str,
    reviewer: User,
    comment: str | None = None,
    category: str | None = None,
    subcategory: str | None = None,
    department: str | None = None,
    urgency: str | None = None,
    priority: str | None = None,
    escalation: str | None = None,
    assign_to: uuid.UUID | None = None,
) -> OverrideResult:
    """
    Apply one reviewer action and record it.

    Raises :class:`OverrideRefused` when a reviewer asks for something policy
    does not permit — currently only one thing: lowering an escalation below
    the mandatory floor. The refusal is explicit rather than a silent no-op,
    because a reviewer who believes they lowered an escalation and did not is
    worse off than one who was told no.
    """
    action = str(action).strip().upper()
    if action not in {member.value for member in ReviewActionType}:
        raise OverrideRefused(f"'{action}' is not a reviewer action.")

    before = _snapshot(complaint)
    result = OverrideResult(action=action, is_override=action in OVERRIDING_ACTIONS)

    # ── classification ──
    if category:
        complaint.category_id = _resolve(db, Category, category).id
    if subcategory:
        complaint.subcategory_id = _resolve(db, Subcategory, subcategory).id
    if department:
        complaint.department_id = _resolve(db, Department, department).id
    if urgency:
        complaint.urgency = urgency.strip().upper()
    if priority:
        complaint.priority_code = priority.strip().upper()
    if assign_to is not None:
        complaint.assigned_to = assign_to
        lifecycle.transition(
            db, complaint, ComplaintStatus.ASSIGNED, actor=reviewer,
            reason="Assigned from the review queue.",
        )

    # ── escalation, floor-guarded ──
    if escalation:
        proposed = escalation.strip().upper()
        floor = escalation_floor(db, complaint.id)
        ladders = load_ladders(db)

        if not at_or_above(ladders, "escalation_level", proposed, floor):
            raise OverrideRefused(
                f"Escalation cannot be lowered to {proposed}: the mandatory "
                f"rules derived a floor of {floor} for this complaint. Change "
                "the rule if the floor is wrong."
            )

        raised = not at_or_above(
            ladders, "escalation_level", complaint.escalation_code, proposed
        )
        complaint.escalation_code = proposed
        if raised:
            result.escalation_raised = True
            db.add(
                Escalation(
                    complaint_id=complaint.id,
                    escalation_code=proposed,
                    triggered_by=EscalationTrigger.REVIEWER,
                    reason=comment or f"Raised to {proposed} by reviewer.",
                )
            )
            # force: an escalation may always be raised. A lifecycle graph
            # that could veto one would be a second, quieter way to lower it.
            lifecycle.transition(
                db, complaint, ComplaintStatus.ESCALATED, actor=reviewer,
                reason=comment or f"Raised to {proposed} by reviewer.", force=True,
            )

    # ── close the queue item ──
    item = open_item(db, complaint.id)
    if action in CLOSING_ACTIONS and item is not None:
        item.status = (
            ReviewStatus.RESOLVED
            if action == ReviewActionType.APPROVE
            else ReviewStatus.DISMISSED
        )
        item.closed_at = datetime.now(UTC)
        item.assigned_to = item.assigned_to or reviewer.id
        result.queue_closed = True
        if complaint.status == ComplaintStatus.MANUAL_REVIEW:
            lifecycle.transition(
                db, complaint, ComplaintStatus.ANALYZED, actor=reviewer,
                reason="Review closed.",
            )

    db.flush()

    # Expire the loaded relationships before snapshotting. `category`,
    # `subcategory` and `department` are lazy="joined" and were populated when
    # the complaint was read, so changing the foreign key alone leaves the
    # object graph showing the OLD code -- and the audit row would then record
    # a before and after that were identical.
    db.expire(complaint, ["category", "subcategory", "department"])
    after = _snapshot(complaint)
    result.before, result.after = before, after

    # ── the record ──
    db.add(
        ReviewAction(
            review_queue_id=item.id if item else None,
            complaint_id=complaint.id,
            actor_id=reviewer.id,
            action=action,
            is_override=result.is_override and bool(result.changed),
            original_value=before,
            new_value=after,
            comment=comment,
        )
    )
    db.flush()

    log.info(
        "review_action",
        public_ref=complaint.public_ref,
        action=action, reviewer=str(reviewer.id), changed=list(result.changed),
    )
    return result


# ══════════════════════════════════════════════════════════════
# reporting
# ══════════════════════════════════════════════════════════════
def history(db: Session, complaint_id: uuid.UUID) -> list[dict[str, Any]]:
    """
    Every reviewer action on one complaint, oldest first.

    This is what shows a judge that a human overrode the system and exactly
    what they changed — the before and after are stored, not reconstructed.
    """
    rows = db.execute(
        select(ReviewAction)
        .where(ReviewAction.complaint_id == complaint_id)
        .order_by(ReviewAction.created_at)
    ).scalars().all()

    return [
        {
            "action": row.action,
            "is_override": row.is_override,
            "actor_id": str(row.actor_id) if row.actor_id else None,
            "before": row.original_value,
            "after": row.new_value,
            "comment": row.comment,
            "at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]


def override_rate(db: Session) -> dict[str, Any]:
    """
    How often humans overrule the system (FR lxvii).

    A headline number for the analytics dashboard, and a genuinely useful one:
    a rising override rate on a particular field is the system telling you a
    rule is wrong.
    """
    total = db.execute(select(func.count()).select_from(ReviewAction)).scalar_one()
    overrides = db.execute(
        select(func.count())
        .select_from(ReviewAction)
        .where(ReviewAction.is_override.is_(True))
    ).scalar_one()

    by_action = dict(
        db.execute(
            select(ReviewAction.action, func.count()).group_by(ReviewAction.action)
        ).all()
    )

    return {
        "actions": total,
        "overrides": overrides,
        "override_rate_pct": round(overrides / total * 100.0, 2) if total else None,
        "by_action": by_action,
    }
