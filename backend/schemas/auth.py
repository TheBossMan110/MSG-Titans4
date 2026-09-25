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
