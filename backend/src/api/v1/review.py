"""
Review queue, reviewer overrides and SLA endpoints.

FR lxi   Manual Review Queue    FR lxii  Reviewer Actions
FR lxiii Reviewer Override      FR lix   SLA Tracking
FR lx    SLA Risk Detection     FR lxvii Override Rate

Access model: reviewers, managers and administrators work the queue;
evaluators read it. An agent cannot override a decision — that is the point of
having a reviewer role at all.

The one thing no role can do is lower an escalation below the mandatory floor.
The endpoint refuses it with an explanation naming the floor, because a
reviewer who believes they lowered an escalation and did not is in a worse
position than one who was told no (SRS 1.8 #7).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select

from complaint_processing import followup
from schemas.common import Page
from schemas.complaints import DueFollowUpOut
from schemas.review import (
    QueueStatsOut,
    ReviewActionOut,
    ReviewActionRequest,
    ReviewHistoryOut,
    ReviewItemOut,
    SLAStatusOut,
    SLASweepOut,
)
from src.core.deps import CurrentUser, DbSession, require_role
from src.core.errors import NotFoundError, ValidationError
from src.core.logging import get_logger
from src.db.enums import ReviewStatus, UserRole
from src.db.models import Complaint, ReviewQueueItem, SLAEvent
from src.services import review, sla

log = get_logger("api.review")

router = APIRouter(prefix="/review", tags=["Review & SLA"])

REVIEWERS = (UserRole.REVIEWER, UserRole.MANAGER, UserRole.ADMIN)
READERS = (*REVIEWERS, UserRole.EVALUATOR, UserRole.AGENT)


def _item_out(db: DbSession, item: ReviewQueueItem, complaint: Complaint) -> ReviewItemOut:
    events = db.execute(
        select(SLAEvent).where(SLAEvent.complaint_id == complaint.id)
    ).scalars().all()

    return ReviewItemOut(
        id=item.id,
        complaint_id=complaint.id,
        public_ref=complaint.public_ref,
        title=complaint.title,
        status=item.status,
        reasons=list(item.reasons or []),
        priority_code=item.priority_code,
        category=complaint.category.code if complaint.category else None,
        department=complaint.department.code if complaint.department else None,
        urgency=complaint.urgency,
        escalation_code=complaint.escalation_code,
        verification_outcome=complaint.verification_outcome,
        assigned_to=item.assigned_to,
        sla_breached=any(e.breached for e in events),
        sla_at_risk=any(e.at_risk and not e.breached for e in events),
        created_at=item.created_at,
        closed_at=item.closed_at,
    )


def _load_complaint(db: DbSession, ref: str) -> Complaint:
    query = select(Complaint)
    try:
        complaint = db.execute(
            query.where(Complaint.id == uuid.UUID(str(ref)))
        ).scalars().first()
    except (ValueError, AttributeError):
        complaint = db.execute(
            query.where(Complaint.public_ref == ref.strip().upper())
        ).scalars().first()

    if complaint is None:
        raise NotFoundError(f"No complaint with reference '{ref}'.")
    return complaint


# ══════════════════════════════════════════════════════════════
# the queue
# ══════════════════════════════════════════════════════════════
@router.get(
    "/queue",
    response_model=Page[ReviewItemOut],
    dependencies=[Depends(require_role(*READERS))],
    summary="The manual review queue",
)
def list_queue(
    db: DbSession,
    page: int = Query(1, ge=1),
    size: int = Query(25, ge=1, le=100),
    status_filter: str | None = Query(None, alias="status"),
    assigned_to_me: bool = False,
    breached_only: bool = False,
    user: CurrentUser = None,
) -> Page[ReviewItemOut]:
    """
    What is waiting for a human (FR lxi; SRS Step 57).

    Ordered by priority then age, so the most severe waiting longest is at the
    top. A P0 filed an hour ago outranks a P3 filed yesterday.
    """
    query = select(ReviewQueueItem, Complaint).join(
        Complaint, ReviewQueueItem.complaint_id == Complaint.id
    )

    if status_filter:
        query = query.where(ReviewQueueItem.status == status_filter.strip().upper())
    else:
        query = query.where(
            ReviewQueueItem.status.in_((ReviewStatus.OPEN, ReviewStatus.IN_REVIEW))
        )

    if assigned_to_me and user is not None:
        query = query.where(ReviewQueueItem.assigned_to == user.id)

    if breached_only:
        breached = select(SLAEvent.complaint_id).where(SLAEvent.breached.is_(True))
        query = query.where(ReviewQueueItem.complaint_id.in_(breached))

    rows = db.execute(
        query.order_by(
            # priority_code sorts lexically and that happens to be correct:
            # P0 < P1 < P2 < P3, most severe first.
            ReviewQueueItem.priority_code.asc(),
            ReviewQueueItem.created_at.asc(),
        )
    ).all()

    window = rows[(page - 1) * size : page * size]
    return Page[ReviewItemOut](
        items=[_item_out(db, item, complaint) for item, complaint in window],
        total=len(rows),
        page=page,
        size=size,
    )


@router.get(
    "/stats",
    response_model=QueueStatsOut,
    dependencies=[Depends(require_role(*READERS))],
    summary="Queue depth and override rate",
)
def queue_stats(db: DbSession) -> QueueStatsOut:
    """
    How much is waiting, and how often humans overrule the system (FR lxvii).

    A rising override rate on one field is the system telling you a rule is
    wrong, which is why it is reported per action rather than as one number.
    """
    return QueueStatsOut(
        depth=review.queue_depth(db),
        override_rate=review.override_rate(db),
    )


@router.post(
    "/queue/{ref}/claim",
    response_model=ReviewItemOut,
    dependencies=[Depends(require_role(*REVIEWERS))],
    summary="Claim a queue item",
)
def claim_item(ref: str, db: DbSession, user: CurrentUser) -> ReviewItemOut:
    """Take an item, so two reviewers do not work the same complaint."""
    complaint = _load_complaint(db, ref)
    item = review.open_item(db, complaint.id)
    if item is None:
        raise NotFoundError(f"Complaint {complaint.public_ref} is not in the queue.")

    review.claim(db, item, user)
    db.commit()
    return _item_out(db, item, complaint)


# ══════════════════════════════════════════════════════════════
# actions
# ══════════════════════════════════════════════════════════════
@router.post(
    "/{ref}/actions",
    response_model=ReviewActionOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role(*REVIEWERS))],
    summary="Record a reviewer action",
)
def record_action(
    ref: str,
    payload: ReviewActionRequest,
    db: DbSession,
    user: CurrentUser,
) -> ReviewActionOut:
    """
    Apply and record one reviewer action (FR lxii, lxiii; SRS Steps 58-59).

    Every action writes a ``review_actions`` row carrying the before and after
    values, so the audit shows what the system decided, what the human changed
    it to and why. A complaint a reviewer reclassified must never look like one
    the system classified correctly in the first place.
    """
    complaint = _load_complaint(db, ref)

    try:
        result = review.apply_action(
            db,
            complaint,
            action=payload.action,
            reviewer=user,
            comment=payload.comment,
            category=payload.category,
            subcategory=payload.subcategory,
            department=payload.department,
            urgency=payload.urgency,
            priority=payload.priority,
            escalation=payload.escalation,
            assign_to=payload.assign_to,
        )
    except review.OverrideRefused as exc:
        db.rollback()
        raise ValidationError(str(exc)) from exc

    # A priority change moves the deadline with it.
    sla.apply(db, complaint)
    db.commit()

    return ReviewActionOut(**result.summary())


@router.get(
    "/{ref}/history",
    response_model=list[ReviewHistoryOut],
    dependencies=[Depends(require_role(*READERS))],
    summary="Every reviewer action on a complaint",
)
def action_history(ref: str, db: DbSession) -> list[ReviewHistoryOut]:
    """
    The override trail.

    This is what shows a judge that a human overruled the system and exactly
    what they changed — before and after are stored, not reconstructed.
    """
    complaint = _load_complaint(db, ref)
    return [ReviewHistoryOut(**row) for row in review.history(db, complaint.id)]


# ══════════════════════════════════════════════════════════════
# SLA
# ══════════════════════════════════════════════════════════════
@router.get(
    "/{ref}/sla",
    response_model=list[SLAStatusOut],
    dependencies=[Depends(require_role(*READERS))],
    summary="SLA clocks for a complaint",
)
def complaint_sla(ref: str, db: DbSession) -> list[SLAStatusOut]:
    complaint = _load_complaint(db, ref)
    return [SLAStatusOut(**row) for row in sla.status_for(db, complaint.id)]


@router.post(
    "/sla/sweep",
    response_model=SLASweepOut,
    dependencies=[Depends(require_role(UserRole.MANAGER, UserRole.ADMIN))],
    summary="Re-evaluate every open complaint's SLA clocks",
)
def sweep_sla(db: DbSession, limit: int = Query(500, ge=1, le=5000)) -> SLASweepOut:
    """
    Run the breach sweep (FR lx; SRS Step 56).

    Nothing notices a breach on its own — a due date passes silently unless
    something looks. This is what turns a stored deadline into a warning
    somebody sees, and it is idempotent, so a scheduler may call it as often
    as it likes.
    """
    result = sla.sweep(db, limit=limit)
    db.commit()
    return SLASweepOut(**result)


@router.get(
    "/follow-ups/due",
    response_model=list[DueFollowUpOut],
    dependencies=[Depends(require_role(*READERS))],
    summary="Follow-ups that are due or overdue",
)
def due_follow_ups(
    db: DbSession, limit: int = Query(100, ge=1, le=500)
) -> list[DueFollowUpOut]:
    """
    The work list (FR xxxviii; SRS Step 41).

    Soonest first, so overdue items sort to the top — they are the ones
    already costing the customer something. Nothing notices a follow-up coming
    due on its own; this endpoint is what turns a stored date into work.
    """
    return [DueFollowUpOut(**row) for row in followup.due(db, limit=limit)]
