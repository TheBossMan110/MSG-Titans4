"""
Customer response, the response guard, escalation, follow-up, review and SLA.

FR xxix  Professional Response Generation   SRS Step 32
FR xxx   Response Tone Management           SRS Step 33
FR xxxi  Unsupported Promise Detection      SRS Step 34
FR xxxii Hallucination Detection            SRS Step 35
FR xxxiii-xxxvi Escalation detect/level/notes/validation   SRS Steps 36-39
FR xxxvii-xxxviii Follow-up                 SRS Steps 40-41
FR lix-lx  SLA tracking and risk            SRS Steps 55-56
FR lxi-lxiii Review queue, decision, override  SRS Steps 57-59
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base, Code, Name, TimestampMixin, TZDateTime, UUIDPrimaryKey
from src.db.constraints import enum_check
from src.db.enums import (
    EscalationTrigger,
    GuardStatus,
    ResponseFlagType,
    ResponseTone,
    ReviewActionType,
    ReviewStatus,
    Severity,
)


class Response(UUIDPrimaryKey, TimestampMixin, Base):
    """
    A customer-facing reply draft.

    Generated from the **reconciled** verification result and constrained by
    the permitted/prohibited action lists that Pipeline 2 derived — then
    scanned again by the guard before any human sees it.
    """

    __tablename__ = "responses"
    __table_args__ = (
        UniqueConstraint("complaint_id", "version", name="uq_response_complaint_version"),
        Index("ix_responses_complaint", "complaint_id", "version"),
        enum_check("tone", ResponseTone),
        enum_check("guard_status", GuardStatus),
    )

    complaint_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("complaints.id", ondelete="CASCADE"), nullable=False
    )
    genai_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("genai_runs.id", ondelete="SET NULL")
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    tone: Mapped[str] = mapped_column(String(24), nullable=False, default=ResponseTone.PROFESSIONAL)

    draft_text: Mapped[str] = mapped_column(Text, nullable=False)
    final_text: Mapped[str | None] = mapped_column(Text)
    # [{"doc_ref":"DEL-POL-04","section_ref":"5.2","chunk_key":"...","version":"2.1"}]
    citations: Mapped[list[Any]] = mapped_column(nullable=False, default=list)

    guard_status: Mapped[str] = mapped_column(
        String(24), nullable=False, default=GuardStatus.PENDING
    )
    regeneration_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    edited_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    approved_at: Mapped[datetime | None] = mapped_column(TZDateTime)
    sent_at: Mapped[datetime | None] = mapped_column(TZDateTime)

    flags = relationship("ResponseFlag", back_populates="response", cascade="all, delete-orphan")


class ResponseFlag(UUIDPrimaryKey, TimestampMixin, Base):
    """
    One guard finding.  ``span_start``/``span_end`` drive the inline red
    highlight in the reply editor; ``explanation`` is the hover text
    ("not permitted under ESC-0042 / DEL-POL-04 s5.2").
    """

    __tablename__ = "response_flags"
    __table_args__ = (
        Index("ix_respflags_response", "response_id"),
        Index("ix_respflags_type", "flag_type"),
        enum_check("flag_type", ResponseFlagType),
        enum_check("severity", Severity),
    )

    response_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("responses.id", ondelete="CASCADE"), nullable=False
    )
    flag_type: Mapped[str] = mapped_column(String(32), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default=Severity.HIGH)
    matched_text: Mapped[str | None] = mapped_column(String(1024))
    span_start: Mapped[int | None] = mapped_column(Integer)
    span_end: Mapped[int | None] = mapped_column(Integer)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    blocking_rule_ref: Mapped[str | None] = mapped_column(Code)
    resolved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    response = relationship("Response", back_populates="flags")


class Escalation(UUIDPrimaryKey, TimestampMixin, Base):
    """
    SRS Step 38/39.

    ``triggered_by = PYTHON_RULE`` on a complaint the model rated low-urgency
    is precisely the Escalation Trap demonstration.
    """

    __tablename__ = "escalations"
    __table_args__ = (
        Index("ix_escalations_complaint", "complaint_id", "created_at"),
        enum_check("triggered_by", EscalationTrigger),
    )

    complaint_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("complaints.id", ondelete="CASCADE"), nullable=False
    )
    escalation_code: Mapped[str] = mapped_column(
        ForeignKey("escalation_levels.code"), nullable=False
    )
    triggered_by: Mapped[str] = mapped_column(String(16), nullable=False)
    rule_ref: Mapped[str | None] = mapped_column(Code)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)  # generated escalation notes
    to_department_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL")
    )
    acknowledged_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(TZDateTime)


class FollowUp(UUIDPrimaryKey, TimestampMixin, Base):
    """SRS Steps 40-41."""

    __tablename__ = "follow_ups"
    __table_args__ = (Index("ix_followups_due", "due_at", "completed_at"),)

    complaint_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("complaints.id", ondelete="CASCADE"), nullable=False, index=True
    )
    follow_up_type: Mapped[str] = mapped_column(Code, nullable=False)
    message: Mapped[str | None] = mapped_column(Text)
    due_at: Mapped[datetime | None] = mapped_column(TZDateTime)
    completed_at: Mapped[datetime | None] = mapped_column(TZDateTime)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )


class ReviewQueueItem(UUIDPrimaryKey, TimestampMixin, Base):
    """SRS Step 57 — entry conditions are recorded in ``reasons``."""

    __tablename__ = "review_queue"
    __table_args__ = (
        Index("ix_review_status_opened", "status", "created_at"),
        Index("ix_review_assigned", "assigned_to", "status"),
        enum_check("status", ReviewStatus),
    )

    complaint_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("complaints.id", ondelete="CASCADE"), nullable=False, index=True
    )
    reasons: Mapped[list[Any]] = mapped_column(nullable=False, default=list)
    priority_code: Mapped[str | None] = mapped_column(
        ForeignKey("priority_levels.code", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=ReviewStatus.OPEN)
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    closed_at: Mapped[datetime | None] = mapped_column(TZDateTime)

    actions = relationship(
        "ReviewAction", back_populates="queue_item", cascade="all, delete-orphan"
    )


class ReviewAction(UUIDPrimaryKey, TimestampMixin, Base):
    """
    SRS Step 59 — "The original recommendation and reviewer decision must both
    remain in the audit trail."

    ``original_value`` + ``is_override`` is the literal implementation of that
    sentence, and it is what we show when a judge asks about overrides.
    """

    __tablename__ = "review_actions"
    __table_args__ = (
        Index("ix_reviewactions_complaint", "complaint_id", "created_at"),
        enum_check("action", ReviewActionType),
    )

    review_queue_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("review_queue.id", ondelete="CASCADE")
    )
    complaint_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("complaints.id", ondelete="CASCADE"), nullable=False
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    action: Mapped[str] = mapped_column(String(24), nullable=False)
    is_override: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    original_value: Mapped[dict[str, Any] | None] = mapped_column()
    new_value: Mapped[dict[str, Any] | None] = mapped_column()
    comment: Mapped[str | None] = mapped_column(Text)

    queue_item = relationship("ReviewQueueItem", back_populates="actions")


class SLAEvent(UUIDPrimaryKey, TimestampMixin, Base):
    """SRS Steps 55-56."""

    __tablename__ = "sla_events"
    __table_args__ = (
        Index("ix_sla_open_due", "due_at", "met_at"),
        Index("ix_sla_complaint", "complaint_id"),
    )

    complaint_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("complaints.id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(Name, nullable=False)  # FIRST_RESPONSE | RESOLUTION
    due_at: Mapped[datetime] = mapped_column(TZDateTime, nullable=False)
    met_at: Mapped[datetime | None] = mapped_column(TZDateTime)
    breached: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    at_risk: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sla_policy_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sla_policies.id", ondelete="SET NULL")
    )
