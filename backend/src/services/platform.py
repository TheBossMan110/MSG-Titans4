"""
The super administrator's view of the platform: every company's totals and how
well the system is doing overall -- never one company's complaints, customers,
people or emails.

Everything here crosses company boundaries on purpose, and does so in exactly
two ways: grouped counts that opt out of the organisation filter explicitly
(``ALL_TENANTS``), and the existing aggregate analytics run inside
:func:`src.core.tenancy.all_companies`. Both return numbers only; no row of any
company leaves this module.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from schemas.company import CompanyRow
from src.core import tenancy
from src.db.base import PLATFORM_ORGANISATION_ID
from src.db.enums import ComplaintStatus, GenAIRunStatus, JobStatus, UserRole
from src.db.models import BenchmarkRun, Complaint, Document, GenAIRun, Organisation, User
from src.services import analytics

_STAFF_ROLES = ("agent", "reviewer", "manager", "admin")
_CLOSED = (ComplaintStatus.RESOLVED, ComplaintStatus.CLOSED)


def company_rows(db: Session, only: uuid.UUID | None = None) -> list[CompanyRow]:
    """Every company with its figures, in a few grouped queries."""

    def per_company(statement) -> dict:
        return dict(db.execute(statement.execution_options(**tenancy.ALL_TENANTS)).all())

    def counted(model, *where) -> dict:
        return per_company(
            select(model.organisation_id, func.count(model.id)).where(*where).group_by(model.organisation_id)
        )

    staff = counted(User, User.role.in_(_STAFF_ROLES))
    admins = counted(User, User.role == UserRole.ADMIN)
    customers = counted(User, User.role == UserRole.CUSTOMER)
    complaints = counted(Complaint)
    open_ = counted(Complaint, Complaint.status.not_in(_CLOSED))
    documents = counted(Document)
    last_complaint = per_company(
        select(Complaint.organisation_id, func.max(Complaint.created_at)).group_by(Complaint.organisation_id)
    )
    contact: dict = {}
    for organisation_id, email in db.execute(
        select(User.organisation_id, User.email)
        .where(User.role == UserRole.ADMIN, User.is_active.is_(True))
        .order_by(User.created_at)
        .execution_options(**tenancy.ALL_TENANTS)
    ).all():
        contact.setdefault(organisation_id, email)

    # The platform's own organisation is not a company: it holds the super administrators only.
    query = select(Organisation).where(Organisation.id != PLATFORM_ORGANISATION_ID).order_by(Organisation.created_at)
    if only is not None:
        query = query.where(Organisation.id == only)

    def row(o: Organisation) -> CompanyRow:
        subscription = (o.settings or {}).get("subscription") or {}
        return CompanyRow(
            id=o.id, name=o.name, slug=o.slug, industry=o.industry, is_active=o.is_active,
            is_reference=tenancy.owns_template(o.id), created_at=o.created_at,
            administrator=contact.get(o.id), administrators=admins.get(o.id, 0),
            staff=staff.get(o.id, 0), customers=customers.get(o.id, 0),
            complaints=complaints.get(o.id, 0), open_complaints=open_.get(o.id, 0),
            documents=documents.get(o.id, 0), last_complaint_at=last_complaint.get(o.id),
            plan=subscription.get("plan"), subscription_status=subscription.get("status"),
            billing_cycle=subscription.get("billing_cycle"), trial_ends_at=subscription.get("trial_ends_at"),
            current_period_end=subscription.get("current_period_end"),
        )

    return [row(o) for o in db.execute(query).scalars()]


def _ai_availability(db: Session, since: datetime | None) -> dict[str, Any]:
    """How often a model answered at all: the free-tier providers do go down."""
    query = select(GenAIRun.status, func.count()).group_by(GenAIRun.status)
    if since is not None:
        query = query.where(GenAIRun.created_at >= since)
    by_status = dict(db.execute(query).all())
    answered = by_status.get(GenAIRunStatus.SUCCESS, 0) + by_status.get(GenAIRunStatus.CACHED, 0)
    return {"calls": sum(by_status.values()), "by_status": by_status,
            "answered": analytics.Ratio(answered, sum(by_status.values())).as_dict()}


def _latest_benchmark(db: Session) -> dict[str, Any] | None:
    """The most recent finished accuracy measurement against a labelled dataset."""
    run = db.execute(
        select(BenchmarkRun)
        .where(BenchmarkRun.finished_at.is_not(None), BenchmarkRun.status != JobStatus.CANCELLED)
        .order_by(BenchmarkRun.finished_at.desc())
        .limit(1)
    ).scalars().first()
    if run is None:
        return None
    metrics = run.metrics or {}
    overall = metrics.get("overall") or {}
    escalation = metrics.get("mandatory_escalation") or {}
    return {
        "label": run.label, "dataset_tag": run.dataset_tag, "finished_at": run.finished_at,
        "sample_size": metrics.get("sample_size") or run.sample_size,
        "genai_accuracy_pct": overall.get("genai_accuracy_pct"),
        "python_accuracy_pct": overall.get("python_accuracy_pct"),
        "agreement_pct": overall.get("agreement_pct"),
        "escalation_recall_pct": escalation.get("recall_pct"),
        "by_field": metrics.get("by_field") or [],
    }


def overview(db: Session, *, days: int | None) -> dict[str, Any]:
    rows = company_rows(db)
    since = datetime.now(UTC) - timedelta(days=days) if days else None
    with tenancy.all_companies(db):
        figures = {
            "complaints": analytics.volume(db, days=days),
            "priorities": analytics.priority_levels(db, days=days),
            "escalation": analytics.escalation_rate(db, days=days),
            "sla": analytics.sla_performance(db, days=days),
            "resolution_time": analytics.resolution_time(db, days=days),
            "agreement": analytics.pipeline_agreement(db, days=days),
            "traceability": analytics.traceability(db, days=days),
            "safety": analytics.guard_activity(db, days=days),
            "ai": _ai_availability(db, since),
            "benchmark": _latest_benchmark(db),
        }
    active = sum(1 for r in rows if r.is_active)
    return {
        "window_days": days,
        "generated_at": datetime.now(UTC),
        "companies": {
            "total": len(rows), "active": active, "suspended": len(rows) - active,
            "new_in_window": sum(1 for r in rows if since is None or (r.created_at and r.created_at >= since)),
        },
        "people": {"staff": sum(r.staff for r in rows), "customers": sum(r.customers for r in rows)},
        "by_company": sorted(
            ({"name": r.name, "is_active": r.is_active, "is_reference": r.is_reference,
              "complaints": r.complaints, "open_complaints": r.open_complaints} for r in rows),
            key=lambda c: c["complaints"], reverse=True,
        ),
        **figures,
    }


__all__ = ["company_rows", "overview"]
