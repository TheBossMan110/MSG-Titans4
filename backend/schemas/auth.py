"""Authentication and user schemas (FR i, FR ii)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from schemas.common import APIModel


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds
    user: UserOut


class RefreshRequest(BaseModel):
    refresh_token: str


class DepartmentRef(APIModel):
    id: uuid.UUID
    code: str
    name: str


class UserOut(APIModel):
    id: uuid.UUID
    email: str
    full_name: str
    role: str
    is_active: bool
    department: DepartmentRef | None = None
    last_login_at: datetime | None = None
    created_at: datetime
    mfa_enabled: bool = False


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=255)
    password: str = Field(min_length=8, max_length=256)
    role: str
    department_code: str | None = None


class RegisterRequest(BaseModel):
    """
    Self-service sign-up.

    There is deliberately no ``role`` field. A role decides what a person may
    change in a complaint register, so it is not something the person applying
    for the account gets to choose — the server always assigns CUSTOMER, and
    staff roles are provisioned by an administrator.
    """

    email: EmailStr
    full_name: str = Field(min_length=2, max_length=255)
    password: str = Field(min_length=12, max_length=256)


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=256)


TokenResponse.model_rebuild()


# ══════════════════════════════════════════════════════════════
# account security
# ══════════════════════════════════════════════════════════════
class LoginResponse(BaseModel):
    """
    Either a signed-in session, or -- with two-step sign-in on -- a request for
    the second step. ``mfa_token`` is accepted only by ``/auth/login/mfa`` and
    only for five minutes.
    """

    access_token: str | None = None
    refresh_token: str | None = None
    token_type: str = "bearer"
    expires_in: int | None = None
    user: UserOut | None = None
    mfa_required: bool = False
    mfa_token: str | None = None


class MfaVerifyRequest(BaseModel):
    mfa_token: str
    code: str = Field(min_length=6, max_length=16)


class MfaCodeRequest(BaseModel):
    code: str = Field(min_length=6, max_length=16)


class MfaDisableRequest(BaseModel):
    password: str = Field(min_length=1, max_length=256)
    code: str = Field(min_length=6, max_length=16)


class MfaSetupOut(BaseModel):
    secret: str
    otpauth_uri: str


class RecoveryCodesOut(BaseModel):
    codes: list[str]


class ProfileUpdate(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)


class SessionOut(BaseModel):
    id: uuid.UUID
    device: str
    user_agent: str | None = None
    ip_address: str | None = None
    started_at: datetime | None = None
    last_active_at: datetime | None = None
    expires_at: datetime
    current: bool = False


class ActivityOut(BaseModel):
    at: datetime
    action: str
    label: str
    ip_address: str | None = None
    detail: str | None = None
    ok: bool = True


class SecurityOverview(BaseModel):
    mfa_enabled: bool
    mfa_enabled_at: datetime | None = None
    recovery_codes_left: int = 0
    password_changed_at: datetime | None = None
    last_login_at: datetime | None = None
    active_sessions: int = 0
    locked_until: datetime | None = None
