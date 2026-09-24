"""
Business taxonomy and runtime configuration — all stored as DATA, not code.

This is the direct implementation of SRS 1.8 #5 (Hidden Complaint Category)
and #14 (Live Modification Challenge): an evaluator can add a category, a
department, an escalation level or change an SLA threshold through the API
with no deployment.

FR xi (rule matrix support), FR lix/lx (SLA), FR xxxvii (policy precedence).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import (
    Base,
    Code,
    JSONType,
    Name,
    TimestampMixin,
    TZDateTime,
    UpdatedAtMixin,
    UUIDPrimaryKey,
)


class Department(UUIDPrimaryKey, TimestampMixin, Base):
    """SRS Step 22 — responsible departments."""

    __tablename__ = "departments"

    code: Mapped[str] = mapped_column(Code, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(Name, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(String(320))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Category(UUIDPrimaryKey, TimestampMixin, Base):
    """SRS Step 14 — configurable complaint categories."""

    __tablename__ = "categories"

    code: Mapped[str] = mapped_column(Code, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(Name, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    default_department_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL")
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    default_department = relationship("Department", lazy="joined")
    subcategories = relationship(
        "Subcategory", back_populates="category", cascade="all, delete-orphan", lazy="selectin"
    )


class Subcategory(UUIDPrimaryKey, TimestampMixin, Base):
    """SRS Step 15."""

    __tablename__ = "subcategories"
    __table_args__ = (UniqueConstraint("category_id", "code", name="uq_subcat_category_code"),)

    category_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("categories.id", ondelete="CASCADE"), nullable=False
    )
    code: Mapped[str] = mapped_column(Code, nullable=False)
    name: Mapped[str] = mapped_column(Name, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    category = relationship("Category", back_populates="subcategories")


class PriorityLevel(TimestampMixin, Base):
    """
    SRS Step 20 — P0..P3 as an ORDERED ladder.

    ``rank`` is what makes "Python may raise but never lower the priority"
    expressible as a comparison instead of a hard-coded if-chain.
    """

    __tablename__ = "priority_levels"

    code: Mapped[str] = mapped_column(String(8), primary_key=True, sort_order=-100)
    name: Mapped[str] = mapped_column(Name, nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)  # 0 = most severe
    description: Mapped[str | None] = mapped_column(Text)


class EscalationLevel(TimestampMixin, Base):
    """SRS Step 37 — escalation ladder; ``rank`` enables the mandatory floor."""

    __tablename__ = "escalation_levels"

    code: Mapped[str] = mapped_column(Code, primary_key=True, sort_order=-100)
    name: Mapped[str] = mapped_column(Name, nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)  # 0 = no escalation
    description: Mapped[str | None] = mapped_column(Text)


class SLAPolicy(UUIDPrimaryKey, TimestampMixin, UpdatedAtMixin, Base):
    """SRS Step 55 — configurable response/resolution targets (FR lix)."""

    __tablename__ = "sla_policies"
    __table_args__ = (
        UniqueConstraint("category_id", "priority_code", name="uq_sla_category_priority"),
    )

    category_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("categories.id", ondelete="CASCADE")
    )
    priority_code: Mapped[str] = mapped_column(
        ForeignKey("priority_levels.code"), nullable=False
    )
    first_response_mins: Mapped[int] = mapped_column(Integer, nullable=False)
    resolution_mins: Mapped[int] = mapped_column(Integer, nullable=False)
    risk_threshold_pct: Mapped[int] = mapped_column(Integer, nullable=False, default=75)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class AppConfig(Base):
    """
    Arbitrary runtime configuration: policy precedence order, scoring weights,
    detection thresholds, the current ruleset version.

    Example rows
    ------------
    policy_precedence : ["ACTIVE_POLICY","DEPARTMENT_SOP","ROUTING_RULES","FAQ","INFORMAL"]
    ruleset_version   : "2026.09.23-4"
    comparison_weights: {"escalation_level":"CRITICAL","department":"CRITICAL", ...}
    """

    __tablename__ = "app_config"

    key: Mapped[str] = mapped_column(String(128), primary_key=True, sort_order=-100)
    # Union of object/array payloads -> explicit JSON column (no annotation map entry).
    value: Mapped[Any] = mapped_column(JSONType, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    updated_at: Mapped[datetime | None] = mapped_column(TZDateTime)
