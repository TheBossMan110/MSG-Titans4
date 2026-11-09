"""Plans, a company's subscription, and requests from the pricing page."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, EmailStr, Field


class SubscriptionOut(BaseModel):
    """A company's plan and what it has used this month. ``plan`` is empty for an unmetered company."""

    plan: dict[str, Any] | None = None
    status: str
    billing_cycle: str | None = None
    trial_ends_at: str | None = None
    current_period_end: str | None = None
    seats_used: int
    seats_limit: int | None = None
    ai_used: int
    ai_limit: int | None = None
    ai_active: bool
    notice: str | None = None
    period_start: datetime


class SubscriptionUpdate(BaseModel):
    plan: str = Field(max_length=32)
    status: Literal["trialing", "active", "past_due", "cancelled"]
    billing_cycle: Literal["monthly", "annual"] = "monthly"
    trial_ends_at: datetime | None = None
    current_period_end: datetime | None = None
    reason: str | None = Field(None, max_length=500)


class PlanRequestIn(BaseModel):
    company_name: str = Field(min_length=2, max_length=255)
    contact_name: str = Field(min_length=2, max_length=255)
    email: EmailStr
    phone: str | None = Field(None, max_length=40)
    plan_code: str = Field(max_length=32)
    billing_cycle: Literal["monthly", "annual"] = "monthly"
    team_size: int | None = Field(None, ge=1, le=100000)
    monthly_complaints: int | None = Field(None, ge=0, le=100000000)
    message: str | None = Field(None, max_length=1000)
    # Left empty by people; bots fill in every field they find.
    website: str | None = Field(None, max_length=255)


class PlanRequestAccepted(BaseModel):
    received: bool = True


class PlanRequestOut(BaseModel):
    id: uuid.UUID
    company_name: str
    contact_name: str
    email: str
    phone: str | None = None
    plan_code: str
    billing_cycle: str
    team_size: int | None = None
    monthly_complaints: int | None = None
    message: str | None = None
    status: str
    existing_customer: bool
    created_at: datetime


class PlanRequestList(BaseModel):
    new: int
    items: list[PlanRequestOut]


class PlanRequestStatusIn(BaseModel):
    status: Literal["NEW", "CONTACTED", "WON", "LOST"]
