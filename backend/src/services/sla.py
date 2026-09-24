"""
SLA tracking (FR lix, lx; SRS Steps 55-56).

    "The system must track service-level targets per category and priority,
     and detect complaints at risk of breaching them."     — SRS Steps 55-56

Two clocks per complaint, started at intake:

* **first response** — how long until the customer hears something;
* **resolution** — how long until the matter is closed.

Both are due dates computed from ``sla_policies``, which is a table rather than
a constant so an evaluator can retighten a target at runtime and re-run a
complaint to watch the due date move (SRS 1.8 #14).

**At-risk is not the same as breached, and the difference is the point.** A
breach is a fact recorded after the fact; at-risk is a warning while there is
still time to act. ``risk_threshold_pct`` decides how much of the window must
elapse before a complaint starts shouting — 75% by default, so a four-hour
target warns at three hours.

**The clock is never invented.** Every due date is derived from a stored policy
row, and a complaint whose category and priority match no policy gets no SLA
event rather than a guessed one. A fabricated deadline would be worse than
none: it would make the analytics look complete while measuring nothing.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from src.core.logging import get_logger
from src.db.models import Complaint, SLAEvent, SLAPolicy

log = get_logger("services.sla")

FIRST_RESPONSE = "FIRST_RESPONSE"
RESOLUTION = "RESOLUTION"

DEFAULT_RISK_THRESHOLD_PCT = 75


@dataclass(slots=True)
class SLAStatus:
    """Where one clock stands right now."""

    event_type: str
    due_at: datetime
    met_at: datetime | None = None
    breached: bool = False
    at_risk: bool = False
    policy_id: uuid.UUID | None = None
    minutes_remaining: float | None = None
    elapsed_pct: float | None = None

    @property
    def open(self) -> bool:
        return self.met_at is None

    def as_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type,
            "due_at": self.due_at.isoformat(),
            "met_at": self.met_at.isoformat() if self.met_at else None,
            "breached": self.breached,
            "at_risk": self.at_risk,
            "minutes_remaining": (
                round(self.minutes_remaining, 1)
                if self.minutes_remaining is not None
                else None
            ),
            "elapsed_pct": (
                round(self.elapsed_pct, 1) if self.elapsed_pct is not None else None
            ),
        }


@dataclass(slots=True)
class SLAResult:
    """Both clocks for one complaint."""

    events: list[SLAStatus] = field(default_factory=list)
    policy_found: bool = True

    @property
    def breached(self) -> bool:
        return any(e.breached for e in self.events)

    @property
    def at_risk(self) -> bool:
        return any(e.at_risk and not e.breached for e in self.events)

    def by_type(self, event_type: str) -> SLAStatus | None:
        return next((e for e in self.events if e.event_type == event_type), None)

    def summary(self) -> dict[str, Any]:
        return {
            "policy_found": self.policy_found,
            "breached": self.breached,
            "at_risk": self.at_risk,
            "events": [e.as_dict() for e in self.events],
        }


# ══════════════════════════════════════════════════════════════
# policy lookup
# ══════════════════════════════════════════════════════════════
def find_policy(
    db: Session,
    *,
    category_id: uuid.UUID | None,
    priority_code: str | None,
) -> SLAPolicy | None:
    """
    The SLA policy governing this complaint.

    A category-specific policy beats a general one for the same priority: a
    four-hour target for safety complaints must not be overridden by a generic
    P0 rule that happens to be looser.

    Returns ``None`` when nothing matches, and the caller then creates no SLA
    event. Guessing a deadline would make the analytics look complete while
    measuring nothing.
    """
    if not priority_code:
        return None

    rows = db.execute(
        select(SLAPolicy).where(
            SLAPolicy.priority_code == priority_code,
            SLAPolicy.is_active.is_(True),
            or_(SLAPolicy.category_id == category_id, SLAPolicy.category_id.is_(None)),
        )
    ).scalars().all()
    if not rows:
        return None

    # Specific before general.
    rows.sort(key=lambda p: (p.category_id is None, p.first_response_mins))
    return rows[0]


# ══════════════════════════════════════════════════════════════
# computation
# ══════════════════════════════════════════════════════════════
def _status(
    event_type: str,
    *,
    started: datetime,
    due: datetime,
    met: datetime | None,
    threshold_pct: int,
    now: datetime,
) -> SLAStatus:
    """
    Where one clock stands.

    A target that was met late is still a breach — the recorded fact is
    whether the response arrived before the deadline, not whether it arrived
    at all.
    """
    window = (due - started).total_seconds() / 60.0
    reference = met or now
    elapsed = (reference - started).total_seconds() / 60.0
    elapsed_pct = (elapsed / window * 100.0) if window > 0 else 100.0

    breached = reference > due
    at_risk = not breached and met is None and elapsed_pct >= threshold_pct

    return SLAStatus(
        event_type=event_type,
        due_at=due,
        met_at=met,
        breached=breached,
        at_risk=at_risk,
        minutes_remaining=(due - now).total_seconds() / 60.0 if met is None else None,
        elapsed_pct=elapsed_pct,
    )


def evaluate(
    db: Session, complaint: Complaint, *, now: datetime | None = None
) -> SLAResult:
    """
    Compute both clocks for one complaint without writing anything.

    ``now`` is injectable so the tests can move time rather than sleep, and so
    the breach sweep can evaluate a whole batch against one consistent instant.
    """
    moment = now or datetime.now(UTC)
    result = SLAResult()

    policy = find_policy(
        db, category_id=complaint.category_id, priority_code=complaint.priority_code
    )
    if policy is None:
        result.policy_found = False
        log.debug(
            "sla_policy_not_found",
            public_ref=complaint.public_ref, priority=complaint.priority_code,
        )
        return result

    started = complaint.created_at or moment
    if started.tzinfo is None:
        # SQLite hands back naive datetimes; comparing them to an aware `now`
        # raises, and the offline fallback has to behave like PostgreSQL.
        started = started.replace(tzinfo=UTC)

    threshold = policy.risk_threshold_pct or DEFAULT_RISK_THRESHOLD_PCT

    result.events.append(
        _status(
            FIRST_RESPONSE,
            started=started,
            due=started + timedelta(minutes=policy.first_response_mins),
            met=_aware(complaint.first_response_at),
            threshold_pct=threshold,
            now=moment,
        )
    )
    result.events.append(
        _status(
            RESOLUTION,
            started=started,
            due=started + timedelta(minutes=policy.resolution_mins),
            met=_aware(complaint.resolved_at),
            threshold_pct=threshold,
            now=moment,
        )
    )

    for event in result.events:
        event.policy_id = policy.id

    return result


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


# ══════════════════════════════════════════════════════════════
# persistence
# ══════════════════════════════════════════════════════════════
def apply(
    db: Session, complaint: Complaint, *, now: datetime | None = None
) -> SLAResult:
    """
    Compute and store both clocks.

    One row per (complaint, event_type), updated in place. The due date is
    recomputed on every call because it derives from the complaint's *current*
    priority — a reviewer raising P2 to P0 must tighten the deadline, and a
    row frozen at intake would leave the queue sorting by a target nobody is
    held to any more.
    """
    result = evaluate(db, complaint, now=now)
    if not result.policy_found:
        return result

    existing = {
        row.event_type: row
        for row in db.execute(
            select(SLAEvent).where(SLAEvent.complaint_id == complaint.id)
        ).scalars()
    }

    for status in result.events:
        row = existing.get(status.event_type)
        if row is None:
            row = SLAEvent(
                complaint_id=complaint.id, event_type=status.event_type
            )
            db.add(row)
        row.due_at = status.due_at
        row.met_at = status.met_at
        row.breached = status.breached
        row.at_risk = status.at_risk
        row.sla_policy_id = status.policy_id

    db.flush()

    if result.breached:
        log.warning(
            "sla_breached",
            public_ref=complaint.public_ref,
            events=[e.event_type for e in result.events if e.breached],
        )
    return result


def mark_first_response(
    db: Session, complaint: Complaint, *, at: datetime | None = None
) -> SLAResult:
    """
    Record that the customer has been answered, and stop that clock.

    Idempotent: the first response is the first one, and a second reply must
    not quietly reset the measurement.
    """
    if complaint.first_response_at is None:
        complaint.first_response_at = at or datetime.now(UTC)
        db.flush()
    return apply(db, complaint)


def mark_resolved(
    db: Session, complaint: Complaint, *, at: datetime | None = None
) -> SLAResult:
    if complaint.resolved_at is None:
        complaint.resolved_at = at or datetime.now(UTC)
        db.flush()
    return apply(db, complaint)


# ══════════════════════════════════════════════════════════════
# the sweep
# ══════════════════════════════════════════════════════════════
def sweep(
    db: Session, *, now: datetime | None = None, limit: int = 500
) -> dict[str, Any]:
    """
    Re-evaluate every open complaint's clocks.

    Run on a schedule. Nothing here notices a breach on its own — a due date
    passes silently unless something looks — so this is what turns a stored
    deadline into a warning somebody sees.
    """
    moment = now or datetime.now(UTC)

    open_complaints = db.execute(
        select(Complaint)
        .where(Complaint.resolved_at.is_(None), Complaint.closed_at.is_(None))
        .order_by(Complaint.created_at)
        .limit(limit)
    ).scalars().all()

    breached: list[str] = []
    at_risk: list[str] = []
    skipped = 0

    for complaint in open_complaints:
        result = apply(db, complaint, now=moment)
        if not result.policy_found:
            skipped += 1
            continue
        if result.breached:
            breached.append(complaint.public_ref)
        elif result.at_risk:
            at_risk.append(complaint.public_ref)

    log.info(
        "sla_sweep",
        checked=len(open_complaints),
        breached=len(breached), at_risk=len(at_risk), no_policy=skipped,
    )
    return {
        "checked": len(open_complaints),
        "breached": breached,
        "at_risk": at_risk,
        "no_policy": skipped,
        "evaluated_at": moment.isoformat(),
    }


def status_for(db: Session, complaint_id: uuid.UUID) -> list[dict[str, Any]]:
    """The stored clocks for one complaint, for the agent view."""
    rows = db.execute(
        select(SLAEvent)
        .where(SLAEvent.complaint_id == complaint_id)
        .order_by(SLAEvent.event_type)
    ).scalars().all()

    return [
        {
            "event_type": row.event_type,
            "due_at": row.due_at.isoformat() if row.due_at else None,
            "met_at": row.met_at.isoformat() if row.met_at else None,
            "breached": row.breached,
            "at_risk": row.at_risk,
        }
        for row in rows
    ]
