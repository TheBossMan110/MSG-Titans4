"""The people register: every account, and what each one has done (admin view)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class PersonRow(BaseModel):
    id: uuid.UUID
    full_name: str
    email: str
    role: str
    department: str | None = None
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None = None
    mfa_on: bool = False
    customer_ref: str | None = None
    complaints: int = 0
    open_complaints: int = 0
    last_complaint_at: datetime | None = None
    assigned: int = 0


class PersonCreate(BaseModel):
    """An administrator provisions an account: staff roles are never self-assigned."""

    email: EmailStr
    full_name: str = Field(min_length=2, max_length=255)
    password: str = Field(min_length=8, max_length=256)
    role: str
    department_code: str | None = None


class PersonUpdate(BaseModel):
    """Only the fields sent are changed. ``department_code: ""`` clears the team."""

    full_name: str | None = Field(default=None, min_length=2, max_length=255)
    role: str | None = None
    department_code: str | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=8, max_length=256)


class SignInOut(BaseModel):
    user_id: uuid.UUID | None = None
    full_name: str | None = None
    email: str | None = None
    role: str | None = None
    at: datetime
    ip_address: str | None = None
    first_time: bool = False  # the sign-in that came with creating the account


class PeopleSummary(BaseModel):
    total: int
    by_role: dict[str, int]
    new_7d: int
    new_today: int
    signed_in_today: int
    recent_signups: list[PersonRow]
    recent_signins: list[SignInOut]


class StatusStep(BaseModel):
    from_status: str | None = None
    to_status: str
    at: datetime
    reason: str | None = None


class PersonComplaint(BaseModel):
    public_ref: str
    title: str
    status: str
    channel: str
    category: str | None = None
    department: str | None = None
    priority: str | None = None
    urgency: str | None = None
    sentiment: str | None = None
    created_at: datetime
    updated_at: datetime | None = None
    resolved_at: datetime | None = None
    history: list[StatusStep]


class PersonActivity(BaseModel):
    at: datetime
    action: str
    label: str
    ok: bool
    ip_address: str | None = None


class PersonEmail(BaseModel):
    id: uuid.UUID
    direction: str
    subject: str
    status: str
    at: datetime
    complaint_ref: str | None = None


class PersonDetail(BaseModel):
    person: PersonRow
    phone: str | None = None
    tier: str | None = None
    region: str | None = None
    complaints: list[PersonComplaint]
    activity: list[PersonActivity]
    emails: list[PersonEmail]


class Pulse(BaseModel):
    """Cheap counters the dashboards poll to know when to refresh."""

    complaints: int
    latest_complaint_ref: str | None = None
    latest_complaint_at: datetime | None = None
    users: int
    latest_user_name: str | None = None
    latest_user_at: datetime | None = None
    emails_in: int
    latest_email_from: str | None = None
    latest_email_at: datetime | None = None
    status_changes: int
    checked_at: datetime
