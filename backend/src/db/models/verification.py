"""
Comparison engine + verification decision — where the two pipelines meet.

SRS Step 57 (Manual Review Queue triggers), FR xlvi-li (Classification /
Routing / Urgency / Escalation comparison, Policy Traceability, Verification
Score), Deliverable 8 (GenAI and Python Comparison Report).

The severity model is what makes the override policy defensible:

    CRITICAL  escalation_level, department, priority, policy validity,
              prohibited_actions   -> Python wins, outcome CORRECTED_BY_RULES
    HIGH      category, urgency    -> Python wins, routed to review
    MEDIUM    subcategory          -> warning only
    INFO      sentiment, tone      -> logged only

Weights live in ``app_config['comparison_weights']`` so they are tunable at
runtime rather than compiled into the engine.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base, Code, TimestampMixin, TZDateTime, UUIDPrimaryKey
from src.db.constraints import enum_check
from src.db.enums import ComparisonStatus, Severity, VerificationOutcome, Winner


class Comparison(UUIDPrimaryKey, TimestampMixin, Base):
    """One row per compared field per complaint."""

    __tablename__ = "comparisons"
    __table_args__ = (
        Index("ix_comparisons_complaint", "complaint_id"),
        Index("ix_comparisons_status_severity", "status", "severity"),
        Index("ix_comparisons_field", "field"),
        enum_check("status", ComparisonStatus),
        enum_check("severity", Severity),
        enum_check("winner", Winner),
    )

    complaint_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("complaints.id", ondelete="CASCADE"), nullable=False
    )
    genai_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("genai_runs.id", ondelete="SET NULL")
    )
    validation_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("validation_runs.id", ondelete="SET NULL")
    )

    field: Mapped[str] = mapped_column(Code, nullable=False)  # category, department, urgency…
    genai_value: Mapped[str | None] = mapped_column(String(512))
    python_value: Mapped[str | None] = mapped_column(String(512))
    final_value: Mapped[str | None] = mapped_column(String(512))

    status: Mapped[str] = mapped_column(String(24), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    winner: Mapped[str | None] = mapped_column(String(16))
    reason_code: Mapped[str | None] = mapped_column(Code)
    # Deliverable 8 requires an "explanation of disagreement" per row.
    explanation: Mapped[str | None] = mapped_column(Text)


class VerificationDecision(UUIDPrimaryKey, TimestampMixin, Base):
    """
    The single reconciled verdict for a complaint.

    ``reconciled`` holds the final agreed record that downstream response
    generation is constrained by — the customer never sees prose generated
    from an unverified classification.
    """

    __tablename__ = "verification_decisions"
    __table_args__ = (
        Index("ix_verdict_complaint", "complaint_id", "created_at"),
        Index("ix_verdict_outcome", "outcome"),
        enum_check("outcome", VerificationOutcome),
    )

    complaint_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("complaints.id", ondelete="CASCADE"), nullable=False
    )
    genai_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("genai_runs.id", ondelete="SET NULL")
    )
    validation_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("validation_runs.id", ondelete="SET NULL")
    )

    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    critical_mismatches: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    high_mismatches: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_fields: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    matched_fields: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # FR li - Verification Score.  Computed, never hand-entered.
    agreement_score: Mapped[float | None] = mapped_column(Numeric(5, 2))
    traceability_score: Mapped[float | None] = mapped_column(Numeric(5, 2))
    compliance_score: Mapped[float | None] = mapped_column(Numeric(5, 2))

    requires_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    review_reasons: Mapped[list[Any]] = mapped_column(nullable=False, default=list)
    reconciled: Mapped[dict[str, Any]] = mapped_column(nullable=False, default=dict)

    genai_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    decided_at: Mapped[datetime | None] = mapped_column(TZDateTime)

    comparisons = relationship(
        "Comparison",
        primaryjoin="VerificationDecision.complaint_id == foreign(Comparison.complaint_id)",
        viewonly=True,
    )
