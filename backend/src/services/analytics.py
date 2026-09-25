"""
Complaint analytics (FR lxviii, lxix; SRS Steps 61-64).

    "The system must report complaint volume, category distribution,
     department load, escalation rate, SLA performance and AI accuracy."
                                                      — SRS Steps 61-64

**Every figure is an aggregate over stored rows.** Nothing here is a constant,
an estimate or a remembered number. SRS 1.8 #17 forbids a displayed figure that
is not traceable to evidence, so each metric returns its own numerator and
denominator and a percentage is ``None`` when the denominator is zero.

That last rule matters more than it sounds. An empty system should report "no
complaints yet", not "100% SLA compliance" — and the second is what you get if
you let a percentage default. A dashboard that looks perfect because nothing
has happened is worse than one that admits it has nothing to show.

**The AI-accuracy panel measures the model against the rule engine, not
against truth.** Agreement is how often Pipeline 1 matched Pipeline 2; override
rate is how often a human overruled the reconciled result. Neither is
"accuracy" in the benchmark sense — that needs the labelled dataset and lives
in the benchmark runner. Labelling these honestly is the difference between a
dashboard and a sales pitch.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from src.core.logging import get_logger
from src.db.enums import ComplaintStatus, ReviewStatus, VerificationOutcome
from src.db.models import (
    Category,
    Complaint,
    Department,
    Escalation,
    InjectionEvent,
    ResponseFlag,
    ReviewAction,
    ReviewQueueItem,
    SLAEvent,
    VerificationDecision,
)

log = get_logger("services.analytics")

DEFAULT_WINDOW_DAYS = 30


@dataclass(slots=True)
class Ratio:
    """A count over a total, with the percentage derived rather than stored."""

    numerator: int = 0
    denominator: int = 0

    @property
    def pct(self) -> float | None:
        """``None`` when there is nothing to measure — never a flattering 100."""
        if self.denominator <= 0:
            return None
        return round(self.numerator / self.denominator * 100.0, 2)

    def as_dict(self) -> dict[str, Any]:
        return {
            "count": self.numerator,
            "total": self.denominator,
            "pct": self.pct,
        }


def _window(days: int | None) -> datetime | None:
    if not days:
        return None
    return datetime.now(UTC) - timedelta(days=days)


def _scoped(query, since: datetime | None):
    return query.where(Complaint.created_at >= since) if since else query


# ══════════════════════════════════════════════════════════════
# volume and distribution
# ══════════════════════════════════════════════════════════════
def volume(db: Session, *, days: int | None = DEFAULT_WINDOW_DAYS) -> dict[str, Any]:
    """Complaint counts by status (SRS Step 61)."""
    since = _window(days)

    total = db.execute(
        _scoped(select(func.count()).select_from(Complaint), since)
    ).scalar_one()

    by_status = dict(
        db.execute(
            _scoped(
                select(Complaint.status, func.count()).group_by(Complaint.status), since
            )
        ).all()
    )

    open_statuses = (
        ComplaintStatus.NEW,
        ComplaintStatus.ANALYZING,
        ComplaintStatus.ANALYZED,
        ComplaintStatus.VALIDATED,
        ComplaintStatus.ASSIGNED,
        ComplaintStatus.IN_PROGRESS,
        ComplaintStatus.AWAITING_CUSTOMER,
        ComplaintStatus.ESCALATED,
        ComplaintStatus.MANUAL_REVIEW,
        ComplaintStatus.REOPENED,
    )

    return {
        "window_days": days,
        "total": total,
        "by_status": by_status,
        "open": sum(by_status.get(s, 0) for s in open_statuses),
        "resolved": by_status.get(ComplaintStatus.RESOLVED, 0)
        + by_status.get(ComplaintStatus.CLOSED, 0),
        "failed": by_status.get(ComplaintStatus.FAILED, 0),
    }


def by_category(db: Session, *, days: int | None = DEFAULT_WINDOW_DAYS) -> list[dict[str, Any]]:
    """
    Category distribution (SRS Step 62).

    Complaints with no category are reported under ``UNCLASSIFIED`` rather than
    dropped. A distribution that silently omits what the system could not
    classify hides its own failures.
    """
    since = _window(days)

    rows = db.execute(
        _scoped(
            select(Category.code, Category.name, func.count(Complaint.id))
            .select_from(Complaint)
            .outerjoin(Category, Complaint.category_id == Category.id)
            .group_by(Category.code, Category.name),
            since,
        )
    ).all()

    total = sum(count for _, _, count in rows) or 0
    out = [
        {
            "code": code or "UNCLASSIFIED",
            "name": name or "Not classified",
            "count": count,
            "pct": round(count / total * 100.0, 2) if total else None,
        }
        for code, name, count in rows
    ]
    out.sort(key=lambda r: r["count"], reverse=True)
    return out


def department_load(
    db: Session, *, days: int | None = DEFAULT_WINDOW_DAYS
) -> list[dict[str, Any]]:
    """
    Routing distribution with each department's open backlog (SRS Step 63).

    Volume alone is a poor load signal: a department handling many complaints
    that all close quickly is not under strain, and one holding a small but
    growing backlog is.
    """
    since = _window(days)
    closed = (ComplaintStatus.RESOLVED, ComplaintStatus.CLOSED)

    rows = db.execute(
        _scoped(
            select(
                Department.code,
                Department.name,
                func.count(Complaint.id),
                # CASE rather than CAST(boolean AS INTEGER): SQLite accepts the
                # cast silently and PostgreSQL rejects it, and this query has
                # to give the same answer on the offline fallback.
                func.sum(case((Complaint.status.notin_(closed), 1), else_=0)),
            )
            .select_from(Complaint)
            .outerjoin(Department, Complaint.department_id == Department.id)
            .group_by(Department.code, Department.name),
            since,
        )
    ).all()

    out = [
        {
            "code": code or "UNROUTED",
            "name": name or "Not routed",
            "total": total,
            "open": int(open_count or 0),
        }
        for code, name, total, open_count in rows
    ]
    out.sort(key=lambda r: r["total"], reverse=True)
    return out


# ══════════════════════════════════════════════════════════════
# escalation and SLA
# ══════════════════════════════════════════════════════════════
def escalation_rate(db: Session, *, days: int | None = DEFAULT_WINDOW_DAYS) -> dict[str, Any]:
    """
    How much is escalating, and who triggered it (SRS Step 64).

    ``by_trigger`` is the interesting column: escalations raised by
    ``PYTHON_RULE`` on complaints the model rated low-urgency are the
    Escalation Trap working, and the count is the evidence.
    """
    since = _window(days)

    total = db.execute(
        _scoped(select(func.count()).select_from(Complaint), since)
    ).scalar_one()

    escalated = db.execute(
        _scoped(
            select(func.count())
            .select_from(Complaint)
            .where(
                Complaint.escalation_code.isnot(None),
                Complaint.escalation_code != "NONE",
            ),
            since,
        )
    ).scalar_one()

    by_level = dict(
        db.execute(
            _scoped(
                select(Complaint.escalation_code, func.count())
                .where(
                    Complaint.escalation_code.isnot(None),
                    Complaint.escalation_code != "NONE",
                )
                .group_by(Complaint.escalation_code),
                since,
            )
        ).all()
    )

    by_trigger = dict(
        db.execute(
            select(Escalation.triggered_by, func.count()).group_by(
                Escalation.triggered_by
            )
        ).all()
    )

    return {
        "rate": Ratio(escalated, total).as_dict(),
        "by_level": by_level,
        "by_trigger": by_trigger,
    }


def sla_performance(db: Session, *, days: int | None = DEFAULT_WINDOW_DAYS) -> dict[str, Any]:
    """
    SLA compliance per clock (SRS Step 56).

    Compliance counts only clocks that have actually *stopped*. An open clock
    that has not yet breached is neither a success nor a failure, and counting
    it as met would make a system with a large untouched backlog report
    excellent performance.
    """
    since = _window(days)

    query = select(SLAEvent).join(Complaint, SLAEvent.complaint_id == Complaint.id)
    if since is not None:
        query = query.where(Complaint.created_at >= since)

    events = db.execute(query).scalars().all()

    per_type: dict[str, dict[str, int]] = {}
    for event in events:
        bucket = per_type.setdefault(
            event.event_type, {"settled": 0, "met": 0, "breached": 0, "at_risk": 0}
        )
        if event.breached:
            bucket["settled"] += 1
            bucket["breached"] += 1
        elif event.met_at is not None:
            bucket["settled"] += 1
            bucket["met"] += 1
        elif event.at_risk:
            bucket["at_risk"] += 1

    return {
        "by_type": {
            name: {
                **counts,
                "compliance": Ratio(counts["met"], counts["settled"]).as_dict(),
            }
            for name, counts in per_type.items()
        },
        "open_at_risk": sum(c["at_risk"] for c in per_type.values()),
    }


# ══════════════════════════════════════════════════════════════
# the two pipelines
# ══════════════════════════════════════════════════════════════
def pipeline_agreement(db: Session, *, days: int | None = DEFAULT_WINDOW_DAYS) -> dict[str, Any]:
    """
    How often the model matched the rule engine.

    Deliberately **not** called accuracy. This measures Pipeline 1 against
    Pipeline 2, not against truth: a complaint where both were wrong in the
    same way counts as agreement. Real accuracy needs the labelled dataset and
    is reported by the benchmark runner.

    Decisions taken while no provider was reachable are excluded — scoring a
    degraded run as a disagreement would blame the model for an outage.
    """
    since = _window(days)

    query = select(VerificationDecision).join(
        Complaint, VerificationDecision.complaint_id == Complaint.id
    )
    if since is not None:
        query = query.where(Complaint.created_at >= since)

    decisions = db.execute(query).scalars().all()
    contested = [d for d in decisions if d.genai_available]

    scores = [
        float(d.agreement_score)
        for d in contested
        if d.agreement_score is not None
    ]

    by_outcome = dict(
        db.execute(
            select(VerificationDecision.outcome, func.count()).group_by(
                VerificationDecision.outcome
            )
        ).all()
    )

    corrected = sum(
        1
        for d in contested
        if d.outcome
        in (VerificationOutcome.CORRECTED_BY_RULES, VerificationOutcome.MANUAL_REVIEW_REQUIRED)
    )

    return {
        "decisions": len(decisions),
        "with_genai": len(contested),
        "degraded": len(decisions) - len(contested),
        "mean_agreement_pct": (
            round(sum(scores) / len(scores), 2) if scores else None
        ),
        "rules_corrected_the_model": Ratio(corrected, len(contested)).as_dict(),
        "critical_mismatches": sum(d.critical_mismatches for d in contested),
        "by_outcome": by_outcome,
    }


def traceability(db: Session, *, days: int | None = DEFAULT_WINDOW_DAYS) -> dict[str, Any]:
    """Mean citation traceability and compliance across stored decisions."""
    since = _window(days)

    query = select(VerificationDecision).join(
        Complaint, VerificationDecision.complaint_id == Complaint.id
    )
    if since is not None:
        query = query.where(Complaint.created_at >= since)

    decisions = db.execute(query).scalars().all()

    def _mean(values: list[float]) -> float | None:
        return round(sum(values) / len(values), 2) if values else None

    return {
        "mean_traceability_pct": _mean(
            [float(d.traceability_score) for d in decisions if d.traceability_score is not None]
        ),
        "mean_compliance_pct": _mean(
            [float(d.compliance_score) for d in decisions if d.compliance_score is not None]
        ),
        # A null score is not a zero. It means the control was not measurable
        # for that complaint -- no citation was made, or no reply exists yet.
        "unmeasured_traceability": sum(
            1 for d in decisions if d.traceability_score is None
        ),
        "unmeasured_compliance": sum(
            1 for d in decisions if d.compliance_score is None
        ),
    }


# ══════════════════════════════════════════════════════════════
# safety and security
# ══════════════════════════════════════════════════════════════
def guard_activity(db: Session, *, days: int | None = DEFAULT_WINDOW_DAYS) -> dict[str, Any]:
    """
    What the response guard and the injection scanner caught.

    The headline for the Security Testing Report: how many replies were
    stopped before a customer saw them, and what stopped them.
    """
    since = _window(days)

    injections = db.execute(
        select(InjectionEvent.pattern_label, func.count()).group_by(
            InjectionEvent.pattern_label
        )
    ).all()

    flags = db.execute(
        select(ResponseFlag.flag_type, func.count()).group_by(ResponseFlag.flag_type)
    ).all()

    flagged_complaints = db.execute(
        _scoped(
            select(func.count())
            .select_from(Complaint)
            .where(Complaint.injection_suspected.is_(True)),
            since,
        )
    ).scalar_one()

    return {
        "injection_events": dict(injections),
        "injection_flagged_complaints": flagged_complaints,
        "response_flags": dict(flags),
    }


def review_activity(db: Session, *, days: int | None = DEFAULT_WINDOW_DAYS) -> dict[str, Any]:
    """Queue depth and how often humans overrule the system."""
    depth = dict(
        db.execute(
            select(ReviewQueueItem.status, func.count()).group_by(
                ReviewQueueItem.status
            )
        ).all()
    )

    actions = db.execute(select(func.count()).select_from(ReviewAction)).scalar_one()
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
        "queue_depth": depth,
        "open": depth.get(ReviewStatus.OPEN, 0) + depth.get(ReviewStatus.IN_REVIEW, 0),
        "override_rate": Ratio(overrides, actions).as_dict(),
        "by_action": by_action,
    }


# ══════════════════════════════════════════════════════════════
# the dashboard
# ══════════════════════════════════════════════════════════════
def priority_levels(db: Session, *, days: int | None = DEFAULT_WINDOW_DAYS) -> dict[str, int]:
    """How many complaints sit at each priority (SRS: administrators see priority levels)."""
    since = _window(days)
    query = select(Complaint.priority_code, func.count()).group_by(Complaint.priority_code)
    if since is not None:
        query = query.where(Complaint.created_at >= since)
    return {(code or "UNSET"): count for code, count in db.execute(query).all()}


_CLOSED = ("RESOLVED", "CLOSED")


def sla_risks(db: Session, *, limit: int = 8) -> list[dict[str, Any]]:
    """Open complaints whose resolution clock is at risk or already breached, soonest first."""
    rows = db.execute(
        select(SLAEvent, Complaint)
        .join(Complaint, SLAEvent.complaint_id == Complaint.id)
        .where(
            SLAEvent.event_type == "RESOLUTION",
            SLAEvent.met_at.is_(None),
            or_(SLAEvent.at_risk.is_(True), SLAEvent.breached.is_(True)),
            Complaint.status.not_in(_CLOSED),
        )
        .order_by(SLAEvent.due_at.asc())
        .limit(limit)
    ).all()
    return [
        {
            "public_ref": c.public_ref, "title": c.title, "priority": c.priority_code,
            "team": c.department.name if c.department else None,
            "due_at": e.due_at.isoformat() if e.due_at else None, "breached": bool(e.breached),
        }
        for e, c in rows
    ]


def recent_mismatches(db: Session, *, limit: int = 8) -> list[dict[str, Any]]:
    """The latest complaints where the rules overruled the model, with how many fields differed."""
    rows = db.execute(
        select(VerificationDecision, Complaint)
        .join(Complaint, VerificationDecision.complaint_id == Complaint.id)
        .where(VerificationDecision.genai_available.is_(True))
        .where((VerificationDecision.total_fields - VerificationDecision.matched_fields) > 0)
        .order_by(VerificationDecision.created_at.desc())
        .limit(limit)
    ).all()
    return [
        {
            "public_ref": c.public_ref, "title": c.title, "outcome": d.outcome,
            "mismatched_fields": int((d.total_fields or 0) - (d.matched_fields or 0)),
            "critical": int(d.critical_mismatches or 0),
        }
        for d, c in rows
    ]


def manual_review_cases(db: Session, *, limit: int = 8) -> list[dict[str, Any]]:
    """Complaints waiting on a person, most urgent first."""
    rows = db.execute(
        select(Complaint)
        .where(Complaint.status == "MANUAL_REVIEW")
        .order_by(Complaint.priority_code.asc().nulls_last(), Complaint.created_at.asc())
        .limit(limit)
    ).scalars().all()
    return [
        {
            "public_ref": c.public_ref, "title": c.title, "priority": c.priority_code,
            "team": c.department.name if c.department else None,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        }
        for c in rows
    ]


def dashboard(db: Session, *, days: int | None = DEFAULT_WINDOW_DAYS) -> dict[str, Any]:
    """
    Everything the administrator dashboard shows, in one query pass.

    Assembled server-side rather than by the frontend making eight calls: a
    dashboard whose panels were fetched at different instants can show figures
    that do not add up, and "why does the total not match" is an expensive
    question to answer during a demo.
    """
    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "window_days": days,
        "volume": volume(db, days=days),
        "categories": by_category(db, days=days),
        "departments": department_load(db, days=days),
        "escalation": escalation_rate(db, days=days),
        "sla": sla_performance(db, days=days),
        "pipelines": pipeline_agreement(db, days=days),
        "traceability": traceability(db, days=days),
        "guard": guard_activity(db, days=days),
        "review": review_activity(db, days=days),
        "priorities": priority_levels(db, days=days),
        "sla_risks": sla_risks(db),
        "mismatches": recent_mismatches(db),
        "manual_review": manual_review_cases(db),
    }
    log.info(
        "dashboard_generated",
        window_days=days, complaints=payload["volume"]["total"],
    )
    return payload
