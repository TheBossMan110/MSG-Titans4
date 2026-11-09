"""A company on the platform: sign-up, its profile, and who may do what inside it."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from schemas.common import APIModel


class OrganisationBrief(APIModel):
    """What a signed-in user's own record says about their company."""

    id: uuid.UUID
    name: str
    slug: str
    is_platform: bool = False      # the platform itself: super administrators only
    owns_template: bool = False    # the reference company that defined the shared template


class CompanyCreate(BaseModel):
    """
    A company the super administrator adds to the platform, with its first
    administrator, whose sign-in details the super administrator then shares.

    The administrator role is granted only inside the new company: nothing in
    this body reaches another organisation's data, and taxonomy, rules and
    prompts stay the shared platform template.
    """

    company_name: str = Field(min_length=2, max_length=255)
    industry: str | None = Field(None, max_length=120)
    admin_full_name: str = Field(min_length=2, max_length=255)
    admin_email: EmailStr
    admin_password: str = Field(min_length=12, max_length=256)
    plan: str = Field("growth", max_length=32)
    trial_days: int = Field(14, ge=0, le=90, description="0 starts the plan as paid.")


class CompanyPublicOut(BaseModel):
    """What a customer sees on the company's sign-up link before they have an account."""

    name: str
    industry: str | None = None
    slug: str


class CompanyUpdate(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=255)
    industry: str | None = Field(None, max_length=120)


class PermissionOut(BaseModel):
    key: str
    label: str
    description: str
    defaults: list[str]
    evaluator: bool


class AccessPolicy(BaseModel):
    """
    Per configurable role (manager, reviewer, agent): the permissions it holds,
    and how much of the complaint register it sees (assigned, team or all).
    A role left out keeps its current setting.
    """

    permissions: dict[str, list[str]] = Field(default_factory=dict)
    complaint_scope: dict[str, str] = Field(default_factory=dict)


class CompanyCounts(BaseModel):
    staff: int
    customers: int
    complaints: int
    open_complaints: int
    documents: int


class CompanyRow(BaseModel):
    """One company as the super administrators see it in the list of every company."""

    id: uuid.UUID
    name: str
    slug: str
    industry: str | None = None
    is_active: bool
    # The reference company whose dataset defined the shared template (RaftarXpress).
    is_reference: bool
    created_at: datetime | None = None
    administrator: str | None = None   # the first administrator's email: who to contact
    administrators: int
    staff: int
    customers: int
    complaints: int
    open_complaints: int
    documents: int
    last_complaint_at: datetime | None = None
    plan: str | None = None
    subscription_status: str | None = None
    billing_cycle: str | None = None
    trial_ends_at: str | None = None
    current_period_end: str | None = None


class CompanyCreated(BaseModel):
    """
    What the super administrator shares with the new company. The password is
    not echoed back: the super administrator typed or generated it, and it
    lives in one place only, their screen, until it is handed over.
    """

    company: CompanyRow
    admin_email: str
    admin_full_name: str
    sign_in_path: str
    customer_signup_path: str


class CompanyList(BaseModel):
    total: int
    active: int
    suspended: int
    items: list[CompanyRow]


class CompanyStatusIn(BaseModel):
    """Suspend a company (its people are signed out and refused) or reactivate it."""

    is_active: bool
    reason: str | None = Field(None, max_length=500)


class CompanyOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    industry: str | None = None
    created_at: datetime | None = None
    # True for the reference company, whose administrators may edit the shared template.
    owns_template: bool
    counts: CompanyCounts
    access: AccessPolicy
    defaults: AccessPolicy
    catalogue: list[PermissionOut]
    roles: list[str]
    scopes: list[str]
    customer_signup_path: str
