"""
Plans: what a company is on, what that allows, and what it has used.

The catalogue is ``config/plans.json``, with an identical copy at
``frontend/lib/plans.json`` so the public pricing page renders without waiting
for this server to wake; tests/test_billing.py fails if the two differ.

A company's subscription lives in ``organisations.settings["subscription"]``,
beside its access policy::

    {"plan": "growth", "status": "trialing", "billing_cycle": "monthly",
     "trial_ends_at": "2026-11-23T...", "current_period_end": null}

**A limit never turns a customer away.** Past its allowance, or after a trial
ends, a company's complaints are still accepted, stored, routed and escalated
by the deterministic rules; only the AI analysis stops, because that is the
part that costs money. A person with a safety complaint must not be refused
because of an invoice. Staff seats are the one hard limit, and that only stops
an administrator adding another account.

Payment is handled outside the application for now: Stripe does not onboard
Pakistani businesses, so a plan is requested on the pricing page, invoiced, and
then set here by the super administrator.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.core import tenancy
from src.core.errors import AppError
from src.db.enums import UserRole
from src.db.models import GenAIRun, User

CATALOGUE: dict[str, Any] = json.loads(
    (Path(__file__).resolve().parents[2] / "config" / "plans.json").read_text(encoding="utf-8")
)
PLANS: dict[str, dict[str, Any]] = {plan["code"]: plan for plan in CATALOGUE["plans"]}
TRIAL_DAYS: int = CATALOGUE["trial_days"]
STATUSES = ("trialing", "active", "past_due", "cancelled")
CYCLES = ("monthly", "annual")
STAFF_ROLES = (UserRole.AGENT, UserRole.REVIEWER, UserRole.MANAGER, UserRole.ADMIN)
DEFAULT_PLAN = "growth"


class PlanLimitError(AppError):
    status_code = status.HTTP_402_PAYMENT_REQUIRED
    code = "PLAN_LIMIT"


def new_subscription(plan: str = DEFAULT_PLAN, *, trial_days: int | None = None) -> dict[str, Any]:
    """A fresh subscription: a free trial of ``plan`` unless ``trial_days`` is 0."""
    days = TRIAL_DAYS if trial_days is None else trial_days
    return {
        "plan": plan,
        "status": "trialing" if days else "active",
        "billing_cycle": "monthly",
        "trial_ends_at": (datetime.now(UTC) + timedelta(days=days)).isoformat() if days else None,
        "current_period_end": None,
    }


def subscription_of(organisation_id: uuid.UUID | None) -> dict[str, Any] | None:
    return (tenancy.settings_of(organisation_id) or {}).get("subscription")


def _unmetered(organisation_id: uuid.UUID | None, subscription: dict[str, Any] | None) -> bool:
    """The reference company, and any company created before plans existed, have no limits."""
    return tenancy.owns_template(organisation_id) or not subscription or subscription.get("plan") not in PLANS


def _month_start() -> datetime:
    return datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _trial_over(subscription: dict[str, Any]) -> bool:
    if subscription.get("status") != "trialing" or not subscription.get("trial_ends_at"):
        return False
    ends = datetime.fromisoformat(subscription["trial_ends_at"])
    return (ends if ends.tzinfo else ends.replace(tzinfo=UTC)) <= datetime.now(UTC)


def ai_used(db: Session, organisation_id: uuid.UUID) -> int:
    """Complaints a model actually analysed this calendar month. Failed calls cost nothing and count for nothing."""
    return db.execute(
        select(func.count(func.distinct(GenAIRun.complaint_id)))
        .where(
            GenAIRun.organisation_id == organisation_id,
            GenAIRun.complaint_id.is_not(None),
            GenAIRun.status.in_(("SUCCESS", "CACHED")),
            GenAIRun.created_at >= _month_start(),
        )
        .execution_options(**tenancy.ALL_TENANTS)
    ).scalar_one()


def seats_used(db: Session, organisation_id: uuid.UUID) -> int:
    return db.execute(
        select(func.count(User.id))
        .where(User.organisation_id == organisation_id, User.role.in_(STAFF_ROLES), User.is_active.is_(True))
        .execution_options(**tenancy.ALL_TENANTS)
    ).scalar_one()


def ai_block_reason(db: Session, organisation_id: uuid.UUID | None) -> str | None:
    """Why this company's next complaint is analysed by the rules alone, or ``None`` if the AI may run."""
    subscription = subscription_of(organisation_id)
    if organisation_id is None or _unmetered(organisation_id, subscription):
        return None
    if subscription.get("status") == "cancelled":
        return "The subscription has been cancelled."
    if _trial_over(subscription):
        return "The free trial has ended."
    limit = PLANS[subscription["plan"]]["ai_complaints"]
    if limit is not None and ai_used(db, organisation_id) >= limit:
        return f"This month's allowance of {limit:,} AI-analysed complaints has been used."
    return None


def require_seat(db: Session, organisation_id: uuid.UUID | None) -> None:
    """Called before a staff account is created or reactivated."""
    subscription = subscription_of(organisation_id)
    if organisation_id is None or _unmetered(organisation_id, subscription):
        return
    plan = PLANS[subscription["plan"]]
    limit = plan["seats"]
    if limit is not None and seats_used(db, organisation_id) >= limit:
        raise PlanLimitError(
            f"Your {plan['name']} plan includes {limit} staff accounts and all of them are in use. "
            "Disable an account you no longer need, or move to a larger plan on the Subscription page.",
            details={"plan": plan["code"], "seats": limit},
        )


def view(db: Session, organisation_id: uuid.UUID) -> dict[str, Any]:
    """What the Subscription page shows."""
    subscription = subscription_of(organisation_id) or {}
    used_seats, used_ai = seats_used(db, organisation_id), ai_used(db, organisation_id)
    if _unmetered(organisation_id, subscription):
        return {
            "plan": None, "status": "unmetered", "billing_cycle": None, "trial_ends_at": None, "current_period_end": None,
            "seats_used": used_seats, "seats_limit": None, "ai_used": used_ai, "ai_limit": None,
            "ai_active": True, "notice": None, "period_start": _month_start(),
        }
    plan = PLANS[subscription["plan"]]
    return {
        "plan": plan, "status": "ended" if _trial_over(subscription) else subscription.get("status"),
        "billing_cycle": subscription.get("billing_cycle"), "trial_ends_at": subscription.get("trial_ends_at"),
        "current_period_end": subscription.get("current_period_end"),
        "seats_used": used_seats, "seats_limit": plan["seats"], "ai_used": used_ai, "ai_limit": plan["ai_complaints"],
        "ai_active": ai_block_reason(db, organisation_id) is None,
        "notice": ai_block_reason(db, organisation_id), "period_start": _month_start(),
    }


__all__ = [
    "CATALOGUE", "CYCLES", "DEFAULT_PLAN", "PLANS", "STATUSES", "TRIAL_DAYS", "PlanLimitError",
    "ai_block_reason", "ai_used", "new_subscription", "require_seat", "seats_used", "subscription_of", "view",
]
