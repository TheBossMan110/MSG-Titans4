"""
Structured complaint-intelligence detail.

These tables exist because the SRS asks for each of these things to be
*generated, validated and shown* — and "free-form GenAI responses must not be
used as the only application output" (SRS 1.2, stated twice).  Keeping them as
JSON blobs inside ``genai_runs.parsed_json`` would technically store them, but
it would make them unqueryable, unvalidatable and unreportable.

Requirement coverage
--------------------
FR xxii   Policy Retrieval                -> ComplaintPolicyRef      (Step 25)
FR xxiii  Policy Applicability Validation -> ComplaintPolicyRef      (Step 26)
FR xxiv   Resolution Generation           -> ResolutionStep          (Step 27)
FR xxv    Resolution Validation           -> ResolutionStep          (Step 28)
FR xxvi   Refund Rule Validation          -> EligibilityDecision     (Step 29)
FR xxvii  Replacement Rule Validation     -> EligibilityDecision     (Step 30)
FR xxviii Compensation Validation         -> EligibilityDecision     (Step 31)
FR xl     Clarification Question Generation -> ClarificationQuestion (Step 43)
FR xlii   Agent Guidance                  -> AgentGuidance           (Step 45)
FR l      Policy Traceability             -> ComplaintPolicyRef
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
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base, Code, Name, Ref, TimestampMixin, TZDateTime, UUIDPrimaryKey
from src.db.constraints import enum_check
from src.db.enums import (
    EligibilityOutcome,
    EligibilityType,
    GuidanceKind,
    GuidanceSource,
    PolicyApplicability,
    PolicyRefSource,
    ResolutionStepSource,
    ResolutionStepStatus,
)


class ComplaintPolicyRef(UUIDPrimaryKey, TimestampMixin, Base):
    """
    Every policy reference attached to a complaint, and whether it actually
    holds up.

    This is the table the Source-Traceability Challenge is answered from: pick
    any generated statement, and this row gives the document, version, section,
    page, the exact chunk, who proposed it, whether the version was ACTIVE at
    the time, and the resulting applicability verdict.

    It is also what makes the "Policy usage" report (SRS Step 67) a simple
    aggregate rather than a text search.
    """

    __tablename__ = "complaint_policy_refs"
    __table_args__ = (
        Index("ix_cpr_complaint", "complaint_id"),
        Index("ix_cpr_docref", "doc_ref", "section_ref"),
        Index("ix_cpr_applicability", "applicability"),
        enum_check("source", PolicyRefSource),
        enum_check("applicability", PolicyApplicability),
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

    source: Mapped[str] = mapped_column(String(16), nullable=False)
    doc_ref: Mapped[str] = mapped_column(Ref, nullable=False)          # DEL-POL-04
    section_ref: Mapped[str | None] = mapped_column(String(64))        # 5.2
    doc_version: Mapped[str | None] = mapped_column(String(32))
    chunk_key: Mapped[str | None] = mapped_column(String(255))
    page_no: Mapped[int | None] = mapped_column(Integer)
    paragraph_index: Mapped[int | None] = mapped_column(Integer)

    # Resolution outcome - the heart of hallucinated-citation detection.
    document_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("document_versions.id", ondelete="SET NULL")
    )
    resolved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    was_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    applicability: Mapped[str] = mapped_column(
        String(32), nullable=False, default=PolicyApplicability.APPLICABLE
    )
    precedence_tier: Mapped[str | None] = mapped_column(Code)  # ACTIVE_POLICY, FAQ, ...
    conflict_with_ref: Mapped[str | None] = mapped_column(Ref)  # contradicting doc_ref
    reason: Mapped[str | None] = mapped_column(Text)
    relevance_score: Mapped[float | None] = mapped_column(Numeric(5, 4))

    document_version = relationship("DocumentVersion", lazy="joined")


class ResolutionStep(UUIDPrimaryKey, TimestampMixin, Base):
    """
    One recommended resolution step, from either pipeline, with its verdict.

    SRS Step 28: "Python must verify whether mandatory resolution steps are
    present.  It must also detect prohibited or unsupported actions."

    A rule-required step the model omitted is stored here with status MISSING —
    which is how a missing mandatory action becomes visible instead of silent.
    """

    __tablename__ = "resolution_steps"
    __table_args__ = (
        Index("ix_resstep_complaint_order", "complaint_id", "ordinal"),
        Index("ix_resstep_status", "status"),
        enum_check("source", ResolutionStepSource),
        enum_check("status", ResolutionStepStatus),
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

    ordinal: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    action_code: Mapped[str | None] = mapped_column(Code)  # VERIFY_SHIPMENT, ISSUE_REFUND…
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)

    rule_ref: Mapped[str | None] = mapped_column(Code)      # rule that required/forbade it
    policy_ref: Mapped[str | None] = mapped_column(Ref)     # supporting document
    section_ref: Mapped[str | None] = mapped_column(String(64))
    chunk_key: Mapped[str | None] = mapped_column(String(255))
    support_score: Mapped[float | None] = mapped_column(Numeric(5, 4))
    explanation: Mapped[str | None] = mapped_column(Text)


class EligibilityDecision(UUIDPrimaryKey, TimestampMixin, Base):
    """
    Refund / replacement / compensation / exception eligibility.

    SRS Step 29: "The final determination must be based on approved rules, not
    merely GenAI opinion."  So both opinions are recorded and the final value
    is the deterministic one.
    """

    __tablename__ = "eligibility_decisions"
    __table_args__ = (
        UniqueConstraint("complaint_id", "eligibility_type", name="uq_elig_complaint_type"),
        Index("ix_elig_type_outcome", "eligibility_type", "final_outcome"),
        enum_check("eligibility_type", EligibilityType),
        enum_check("genai_outcome", EligibilityOutcome, name="genai_outcome_valid"),
        enum_check("python_outcome", EligibilityOutcome, name="python_outcome_valid"),
        enum_check("final_outcome", EligibilityOutcome, name="final_outcome_valid"),
    )

    complaint_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("complaints.id", ondelete="CASCADE"), nullable=False
    )
    eligibility_type: Mapped[str] = mapped_column(String(24), nullable=False)

    genai_outcome: Mapped[str | None] = mapped_column(String(24))
    python_outcome: Mapped[str] = mapped_column(String(24), nullable=False)
    final_outcome: Mapped[str] = mapped_column(String(24), nullable=False)
    overridden: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Which conditions were checked and how each evaluated (Step 30).
    conditions_evaluated: Mapped[list[Any]] = mapped_column(nullable=False, default=list)
    rule_ref: Mapped[str | None] = mapped_column(Code)
    policy_ref: Mapped[str | None] = mapped_column(Ref)
    section_ref: Mapped[str | None] = mapped_column(String(64))
    max_amount: Mapped[float | None] = mapped_column(Numeric(12, 2))
    currency: Mapped[str | None] = mapped_column(String(8))
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    requires_human_approval: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )


class ClarificationQuestion(UUIDPrimaryKey, TimestampMixin, Base):
    """
    SRS Step 43: when information is insufficient the pipeline must ask a
    focused question "rather than inventing missing facts".

    Storing them individually lets the Missing-Information Challenge be
    demonstrated and measured (how often did we ask instead of invent?).
    """

    __tablename__ = "clarification_questions"
    __table_args__ = (Index("ix_clarq_complaint", "complaint_id", "ordinal"),)

    complaint_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("complaints.id", ondelete="CASCADE"), nullable=False
    )
    genai_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("genai_runs.id", ondelete="SET NULL")
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    # Which missing field prompted it: ORDER_ID, TRANSACTION_DATE, PRODUCT…
    missing_field: Mapped[str | None] = mapped_column(Code)
    required_for: Mapped[str | None] = mapped_column(Name)  # e.g. "refund eligibility"
    asked_at: Mapped[datetime | None] = mapped_column(TZDateTime)
    answered_at: Mapped[datetime | None] = mapped_column(TZDateTime)
    answer: Mapped[str | None] = mapped_column(Text)


class AgentGuidance(UUIDPrimaryKey, TimestampMixin, Base):
    """
    SRS Step 45 — internal, agent-facing guidance.

    Two sources are merged here: guidance the model generated, and the
    required/prohibited actions the rule engine derived.  Rule-sourced
    CAUTION items ("Do not promise refund before verification") are marked
    mandatory and cannot be dismissed by an agent.
    """

    __tablename__ = "agent_guidance"
    __table_args__ = (
        Index("ix_guidance_complaint", "complaint_id", "ordinal"),
        enum_check("source", GuidanceSource),
        enum_check("kind", GuidanceKind),
    )

    complaint_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("complaints.id", ondelete="CASCADE"), nullable=False
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default=GuidanceKind.ACTION)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    rule_ref: Mapped[str | None] = mapped_column(Code)
    is_mandatory: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    acknowledged_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(TZDateTime)
