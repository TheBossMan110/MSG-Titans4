"""
A company asking to join or change plan, from the public pricing page.

Belongs to the platform, not to a tenant: it usually arrives before any
company exists, and only the super administrators read it.
"""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base, TimestampMixin, UUIDPrimaryKey


class PlanRequest(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "plan_requests"
    __table_args__ = (
        Index("ix_plan_requests_status_created", "status", "created_at"),
    )

    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    contact_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(40))
    plan_code: Mapped[str] = mapped_column(String(32), nullable=False)
    billing_cycle: Mapped[str] = mapped_column(String(16), nullable=False, default="monthly")
    team_size: Mapped[int | None] = mapped_column(Integer)
    monthly_complaints: Mapped[int | None] = mapped_column(Integer)
    message: Mapped[str | None] = mapped_column(Text)
    # NEW -> CONTACTED -> WON | LOST
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="NEW")
    # Set when an administrator already on the platform asks to change plan.
    organisation_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organisations.id", ondelete="SET NULL"))
