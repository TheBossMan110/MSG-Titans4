"""
Identity, sessions and the audit trail.

FR i   — User Authentication
FR ii  — Role-Based Access Control
FR lxiv— Audit Trail (original AND final decisions are logged)
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import (
    Base,
    BigIntPK,
    Code,
    JSONType,
    Name,
    TenantScoped,
    TimestampMixin,
    TZDateTime,
    UUIDPrimaryKey,
)
from src.db.constraints import enum_check
from src.db.enums import UserRole


class Organisation(UUIDPrimaryKey, TimestampMixin, Base):
    """
    A company using the platform (migration 0006): its people, complaints and
    policies are its own, and what each of its roles may do is set here.

    ``settings`` holds the access policy an administrator edits on the Access
    Control page::

        {"permissions":     {"manager": ["analytics.view", ...], "reviewer": [...], "agent": [...]},
         "complaint_scope": {"manager": "all", "reviewer": "all", "agent": "team"}}

    A role missing from either map gets the defaults in src/core/permissions.py,
    which are exactly what the platform did before organisations existed.
    """

    __tablename__ = "organisations"

    name: Mapped[str] = mapped_column(Name, nullable=False)
    slug: Mapped[str] = mapped_column(Code, nullable=False, unique=True)
    industry: Mapped[str | None] = mapped_column(String(120))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    settings: Mapped[dict[str, Any] | None] = mapped_column(JSONType)


class User(UUIDPrimaryKey, TimestampMixin, TenantScoped, Base):
    __tablename__ = "users"
    __table_args__ = (
        enum_check("role", UserRole),
        Index("ux_users_email_lower", text("lower(email)"), unique=True),
    )

    email: Mapped[str] = mapped_column(String(320), nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    full_name: Mapped[str] = mapped_column(Name, nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL")
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(TZDateTime)

    # ── account security (migration 0003) ──
    # The TOTP secret, Fernet-encrypted; see src/core/totp.py. Set during
    # setup, but two-step sign-in is only on once ``mfa_enabled_at`` is.
    mfa_secret: Mapped[str | None] = mapped_column(Text)
    mfa_enabled_at: Mapped[datetime | None] = mapped_column(TZDateTime)
    # SHA-256 hashes of the unused recovery codes; each is removed when used.
    mfa_recovery_codes: Mapped[list[str] | None] = mapped_column(JSONType)
    failed_login_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(TZDateTime)
    password_changed_at: Mapped[datetime | None] = mapped_column(TZDateTime)

    department = relationship("Department", lazy="joined")

    @property
    def mfa_enabled(self) -> bool:
        return self.mfa_enabled_at is not None

    # ── what the signed-in user may do, for UserOut (src/core/permissions.py) ──
    @property
    def organisation(self) -> dict[str, Any] | None:
        from src.core import tenancy

        return tenancy.brief(self.organisation_id)

    @property
    def permissions(self) -> list[str]:
        from src.core import permissions

        return sorted(permissions.granted(self))

    @property
    def complaint_scope(self) -> str:
        from src.core import permissions

        return permissions.complaint_scope(self)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<User {self.email} ({self.role})>"


class RefreshToken(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "refresh_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(TZDateTime, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(TZDateTime)
    user_agent: Mapped[str | None] = mapped_column(String(255))
    ip_address: Mapped[str | None] = mapped_column(String(64))
    # Carried across rotation: the token is replaced on every refresh, the
    # session it belongs to is not.
    session_started_at: Mapped[datetime | None] = mapped_column(TZDateTime)


class AuditLog(TimestampMixin, TenantScoped, Base):
    """
    Append-only.  The application role must not be granted UPDATE/DELETE here —
    see database/grants.sql.
    """

    __tablename__ = "audit_log"
    __table_args__ = (
        Index("ix_audit_entity", "entity_type", "entity_id", "created_at"),
        Index("ix_audit_actor", "actor_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(
        BigIntPK, primary_key=True, autoincrement=True, sort_order=-100
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    actor_role: Mapped[str | None] = mapped_column(String(32))
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(48), nullable=False)
    before: Mapped[dict[str, Any] | None] = mapped_column()
    after: Mapped[dict[str, Any] | None] = mapped_column()
    reason: Mapped[str | None] = mapped_column(Text)
    request_id: Mapped[str | None] = mapped_column(String(64))
    ip_address: Mapped[str | None] = mapped_column(String(64))
