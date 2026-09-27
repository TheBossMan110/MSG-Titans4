"""
What each role's dashboard is built from (FR ii, FR lxvii, FR lxviii).

The SRS names five kinds of user. The customer, agent and administrator
dashboards are specified item by item (Steps 61-63); the reviewer and the
support manager are named as users the interface must serve. These are the
figures their dashboards need:

* **Manager** -- the support operation: today's load, each team's
  performance, each agent's workload, SLA risk, critical cases, escalations
  and the state of the review queue. Watches and intervenes; does not
  configure the platform.
* **Reviewer** -- the quality-control desk between the pipelines and the
  agent: the queue grouped by why a person is needed (AI against the rules,
  policy conflicts, escalation questions, adversarial complaints, validation
  failures), and their own review history.
* **Agent** -- their own performance, next to the assigned work the agent
  workspace already lists.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session, joinedload, lazyload, load_only

from src.db.models import Complaint, Department, ReviewQueueItem, SLAEvent, User
from src.db.models.workflow import ReviewAction
from src.services import analytics

CLOSED = ("RESOLVED", "CLOSED")

# The dashboards read a handful of small columns. Loading whole rows -- the
# complaint text, and the category/department joins every Complaint query
# carries by default -- made one query 7-9 s over the hosted database.
_SLIM = (
    lazyload("*"),
    joinedload(Complaint.department).load_only(Department.name),
    load_only(
        Complaint.id, Complaint.public_ref, Complaint.title, Complaint.status, Complaint.priority_code,
        Complaint.escalation_code, Complaint.department_id, Complaint.assigned_to, Complaint.injection_suspected,
        Complaint.created_at, Complaint.resolved_at, Complaint.closed_at,
    ),
)
IN_PROGRESS = ("ASSIGNED", "IN_PROGRESS", "AWAITING_CUSTOMER", "REOPENED")

# The reviewer's desk, grouped the way the work is done.
REVIEW_GROUPS: list[tuple[str, str, tuple[str, ...]]] = [
    ("disagreement", "AI and rules disagree", ("GENAI_PYTHON_DISAGREEMENT",)),
    ("policy", "Policy conflicts", ("POLICY_CONTRADICTION", "RULE_CONFLICT", "POLICY_SUPPORT_MISSING")),
    ("escalation", "Escalation questions", ("ESCALATION_UNCLEAR",)),
    ("adversarial", "Adversarial and sensitive", ("SENSITIVE_COMPLAINT",)),
    ("validation", "Validation failures", ("GENAI_UNAVAILABLE", "RULE_UNMATCHED", "GUARD_BLOCKED")),
    ("ambiguous", "Ambiguous complaints", ("AMBIGUOUS_COMPLAINT",)),
]


def _hours(start: datetime | None, end: datetime | None) -> float | None:
    if not start or not end:
        return None
    return max(0.0, (_aware(end) - _aware(start)).total_seconds() / 3600)


def _aware(at: datetime) -> datetime:
    """SQLite hands back naive datetimes; Postgres aware ones. Compare like with like."""
    return at if at.tzinfo else at.replace(tzinfo=UTC)


def _brief(c: Complaint, **extra: Any) -> dict[str, Any]:
    return {
        "public_ref": c.public_ref, "title": c.title, "priority": c.priority_code, "status": c.status,
        "team": c.department.name if c.department else None,
        "created_at": c.created_at.isoformat() if c.created_at else None, **extra,
    }


# ══════════════════════════════════════════════════════════════
# manager
# ══════════════════════════════════════════════════════════════
def manager_overview(db: Session, *, department_code: str | None = None) -> dict[str, Any]:
    now = datetime.now(UTC)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    departments = db.execute(select(Department).order_by(Department.name)).scalars().all()
    team = next((d for d in departments if d.code == (department_code or "").upper()), None)

    def scoped(query):
        return query.where(Complaint.department_id == team.id) if team else query

    complaints = db.execute(scoped(select(Complaint).options(*_SLIM))).scalars().all()
    open_ = [c for c in complaints if c.status not in CLOSED]

    at_risk_ids = {cid for (cid,) in db.execute(
        select(SLAEvent.complaint_id).where(
            SLAEvent.event_type == "RESOLUTION", SLAEvent.met_at.is_(None),
            or_(SLAEvent.at_risk.is_(True), SLAEvent.breached.is_(True)),
        )
    ).all()}
    in_review = {cid for (cid,) in db.execute(
        select(ReviewQueueItem.complaint_id).where(ReviewQueueItem.status.in_(("OPEN", "IN_REVIEW")))
    ).all()}

    def escalated(c: Complaint) -> bool:
        return c.status == "ESCALATED" or (c.escalation_code not in (None, "NONE") and c.status not in CLOSED)

    today_view = {
        "total": len(complaints),
        "new_today": sum(1 for c in complaints if c.created_at and _aware(c.created_at) >= today),
        "open": len(open_),
        "in_progress": sum(1 for c in complaints if c.status in IN_PROGRESS),
        "escalated": sum(1 for c in open_ if escalated(c)),
        "sla_at_risk": sum(1 for c in open_ if c.id in at_risk_ids),
        "critical": sum(1 for c in open_ if c.priority_code == "P0"),
        "manual_review": sum(1 for c in open_ if c.id in in_review),
        "resolved": sum(1 for c in complaints if c.status in CLOSED),
    }

    # Each team's performance.
    by_team: dict[Any, list[Complaint]] = defaultdict(list)
    for c in complaints:
        by_team[c.department_id].append(c)
    team_rows = []
    for d in departments:
        rows = by_team.get(d.id, [])
        if not rows:
            continue
        resolved = [c for c in rows if c.status in CLOSED]
        hours = [h for h in (_hours(c.created_at, c.resolved_at or c.closed_at) for c in resolved) if h is not None]
        team_rows.append({
            "code": d.code, "name": d.name, "total": len(rows),
            "open": sum(1 for c in rows if c.status not in CLOSED),
            "resolved": len(resolved),
            "resolved_pct": round(100 * len(resolved) / len(rows), 1) if rows else 0.0,
            "escalated": sum(1 for c in rows if escalated(c)),
            "sla_at_risk": sum(1 for c in rows if c.status not in CLOSED and c.id in at_risk_ids),
            "in_review": sum(1 for c in rows if c.status not in CLOSED and c.id in in_review),
            "avg_resolution_hours": round(sum(hours) / len(hours), 1) if hours else None,
        })

    # Each agent's workload.
    agents = db.execute(
        select(User).where(User.role == "agent", User.is_active.is_(True)).order_by(User.full_name)
    ).scalars().all()
    if team:
        agents = [a for a in agents if a.department_id == team.id]
    assigned: dict[Any, list[Complaint]] = defaultdict(list)
    for c in db.execute(select(Complaint).options(*_SLIM).where(Complaint.assigned_to.in_([a.id for a in agents]))).scalars() if agents else []:
        assigned[c.assigned_to].append(c)
    names = {d.id: d.name for d in departments}
    agent_rows = []
    for a in agents:
        rows = assigned.get(a.id, [])
        resolved = [c for c in rows if c.status in CLOSED]
        hours = [h for h in (_hours(c.created_at, c.resolved_at or c.closed_at) for c in resolved) if h is not None]
        agent_rows.append({
            "id": str(a.id), "name": a.full_name, "team": names.get(a.department_id),
            "open": sum(1 for c in rows if c.status not in CLOSED),
            "resolved": len(resolved),
            "sla_at_risk": sum(1 for c in rows if c.status not in CLOSED and c.id in at_risk_ids),
            "avg_resolution_hours": round(sum(hours) / len(hours), 1) if hours else None,
            "last_login_at": a.last_login_at.isoformat() if a.last_login_at else None,
        })

    critical = sorted((c for c in open_ if c.priority_code == "P0"), key=lambda c: c.created_at or now)[:8]
    escalations = sorted((c for c in open_ if escalated(c)), key=lambda c: c.created_at or now, reverse=True)[:8]
    risks = analytics.sla_risks(db, limit=8)
    if team:
        risks = [r for r in risks if r.get("team") == team.name]

    return {
        "department": team.code if team else None,
        "department_name": team.name if team else None,
        "departments": [{"code": d.code, "name": d.name} for d in departments],
        "today": today_view,
        "teams": team_rows,
        "agents": agent_rows,
        "critical": [_brief(c, escalation=c.escalation_code) for c in critical],
        "escalations": [_brief(c, escalation=c.escalation_code) for c in escalations],
        "sla_risks": risks,
        "unassigned_open": sum(1 for c in open_ if c.assigned_to is None),
        "generated_at": now.isoformat(),
    }


# ══════════════════════════════════════════════════════════════
# reviewer
# ══════════════════════════════════════════════════════════════
def reviewer_overview(db: Session, user: User) -> dict[str, Any]:
    items = db.execute(
        select(ReviewQueueItem, Complaint)
        .join(Complaint, Complaint.id == ReviewQueueItem.complaint_id)
        .options(*_SLIM)
        .where(ReviewQueueItem.status.in_(("OPEN", "IN_REVIEW")))
        .order_by(ReviewQueueItem.priority_code.asc().nulls_last(), ReviewQueueItem.created_at.asc())
    ).all()

    groups = []
    for key, label, reasons in REVIEW_GROUPS:
        matched = [
            (item, c) for item, c in items
            if set(item.reasons or []) & set(reasons) or (key == "adversarial" and c.injection_suspected)
        ]
        groups.append({
            "key": key, "label": label, "reasons": list(reasons), "count": len(matched),
            "items": [
                _brief(c, reasons=item.reasons or [], queue_status=item.status,
                       claimed_by_me=item.assigned_to == user.id,
                       waiting_since=item.created_at.isoformat() if item.created_at else None)
                for item, c in matched[:6]
            ],
        })

    reason_counts = Counter(r for item, _ in items for r in (item.reasons or []))
    mine = [(item, c) for item, c in items if item.assigned_to == user.id]

    today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    actions = db.execute(
        select(ReviewAction, Complaint.public_ref, Complaint.title)
        .join(Complaint, Complaint.id == ReviewAction.complaint_id)
        .where(ReviewAction.actor_id == user.id)
        .order_by(ReviewAction.created_at.desc())
        .limit(15)
    ).all()
    totals = db.execute(
        select(func.count(), func.sum(case((ReviewAction.is_override.is_(True), 1), else_=0)))
        .where(ReviewAction.actor_id == user.id)
    ).first()
    today_count = db.execute(
        select(func.count()).where(ReviewAction.actor_id == user.id, ReviewAction.created_at >= today)
    ).scalar_one()

    return {
        "open": len(items),
        "claimed_by_me": len(mine),
        "unclaimed": sum(1 for item, _ in items if item.assigned_to is None),
        "reasons": dict(reason_counts),
        "groups": groups,
        "my_queue": [_brief(c, reasons=item.reasons or []) for item, c in mine[:8]],
        "history": [
            {
                "public_ref": ref, "title": title, "action": a.action, "is_override": bool(a.is_override),
                "at": a.created_at.isoformat() if a.created_at else None,
                "note": a.comment,
            }
            for a, ref, title in actions
        ],
        "totals": {
            "actions": int(totals[0] or 0) if totals else 0,
            "overrides": int(totals[1] or 0) if totals else 0,
            "today": int(today_count or 0),
        },
    }


# ══════════════════════════════════════════════════════════════
# agent
# ══════════════════════════════════════════════════════════════
def agent_performance(db: Session, user: User) -> dict[str, Any]:
    rows = db.execute(select(Complaint).options(*_SLIM).where(Complaint.assigned_to == user.id)).scalars().all()
    resolved = [c for c in rows if c.status in CLOSED]
    week = datetime.now(UTC) - timedelta(days=7)
    hours = [h for h in (_hours(c.created_at, c.resolved_at or c.closed_at) for c in resolved) if h is not None]

    def recent(c: Complaint) -> bool:
        at = c.resolved_at or c.closed_at
        return at is not None and _aware(at) >= week

    return {
        "assigned_open": sum(1 for c in rows if c.status not in CLOSED),
        "resolved_total": len(resolved),
        "resolved_this_week": sum(1 for c in resolved if recent(c)),
        "avg_resolution_hours": round(sum(hours) / len(hours), 1) if hours else None,
        "escalated_open": sum(1 for c in rows if c.status == "ESCALATED"),
    }


__all__ = ["REVIEW_GROUPS", "agent_performance", "manager_overview", "reviewer_overview"]
