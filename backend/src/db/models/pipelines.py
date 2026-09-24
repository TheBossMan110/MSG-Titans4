"""
The two pipelines, recorded separately and completely.

Pipeline 1 (GenAI)   -> ``genai_runs``
Pipeline 2 (Python)  -> ``validation_runs`` + ``rule_hits``

These are deliberately separate tables rather than JSON columns on
``complaints`` because four different SRS deliverables read from them:
  * GenAI Pipeline Evidence  (sample requests, sample responses,
    invalid responses, retry evidence)            - Deliverable 6
  * Python Validation Pipeline Evidence           - Deliverable 7
  * GenAI / Python Comparison Report              - Deliverable 8
  * Security & Adversarial Testing Report         - Deliverable 10

FR xliii Structured JSON Output   FR xliv JSON Schema Validation
FR xlv   Python Ground-Truth Validation
FR liii  Prompt Version Tracking  (SRS Step 49)
"""

from __future__ import annotations

import uuid
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
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base, Code, Name, TimestampMixin, UUIDPrimaryKey
from src.db.constraints import enum_check
from src.db.enums import GenAIPipeline, GenAIRunStatus, Urgency

ACTIVE_PROMPT_PREDICATE = text("is_active = true")


class PromptVersion(UUIDPrimaryKey, TimestampMixin, Base):
    """
    Registry of versioned prompt templates.

    Source of truth is the file on disk in ``prompt_templates/`` (a required
    deliverable).  This table records which version is active and its checksum,
    so every generation can be traced back to the exact prompt text that
    produced it — and so a tampered template is detectable.

    SRS Step 48: "Prompts must be centrally stored and versioned.  Teams must
    not scatter uncontrolled prompts across source-code files."
    """

    __tablename__ = "prompt_versions"
    __table_args__ = (
        UniqueConstraint("name", "version", name="uq_prompt_name_version"),
        Index(
            "ux_prompt_one_active",
            "name",
            unique=True,
            postgresql_where=ACTIVE_PROMPT_PREDICATE,
            sqlite_where=text("is_active = 1"),
        ),
    )

    name: Mapped[str] = mapped_column(Code, nullable=False)       # complaint_intelligence
    version: Mapped[str] = mapped_column(String(16), nullable=False)  # v1.2
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    changelog: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class LLMCache(TimestampMixin, Base):
    """
    Prompt-hash -> raw provider response.

    Two legitimate uses, both disclosed in the README and surfaced in the UI:
      1. development cost/latency control while iterating on prompts,
      2. a network-outage fallback on demo day ("Replay Mode").

    It stores **real** captured responses.  Fabricating responses is prohibited
    by SRS 1.8 #17 and this table must never be written by anything other than
    an actual provider call.
    """

    __tablename__ = "llm_cache"

    prompt_hash: Mapped[str] = mapped_column(String(64), primary_key=True, sort_order=-100)
    provider: Mapped[str] = mapped_column(Code, nullable=False)
    model: Mapped[str] = mapped_column(Name, nullable=False)
    response_raw: Mapped[str] = mapped_column(Text, nullable=False)
    tokens_in: Mapped[int | None] = mapped_column(Integer)
    tokens_out: Mapped[int | None] = mapped_column(Integer)
    hit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class GenAIRun(UUIDPrimaryKey, TimestampMixin, Base):
    """
    One attempt at one GenAI call.  Retries create additional rows (not
    overwrites) so the retry evidence deliverable is satisfied by simply
    querying this table.
    """

    __tablename__ = "genai_runs"
    __table_args__ = (
        Index("ix_genai_complaint_created", "complaint_id", "created_at"),
        Index("ix_genai_status_created", "status", "created_at"),
        enum_check("pipeline", GenAIPipeline),
        enum_check("status", GenAIRunStatus),
    )

    complaint_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("complaints.id", ondelete="CASCADE"), nullable=False
    )
    pipeline: Mapped[str] = mapped_column(String(32), nullable=False)

    prompt_name: Mapped[str] = mapped_column(Code, nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(16), nullable=False)
    provider: Mapped[str] = mapped_column(Code, nullable=False)
    model: Mapped[str] = mapped_column(Name, nullable=False)
    temperature: Mapped[float | None] = mapped_column(Numeric(3, 2))

    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default=GenAIRunStatus.PENDING)

    request_payload: Mapped[dict[str, Any] | None] = mapped_column()
    response_raw: Mapped[str | None] = mapped_column(Text)
    parsed_json: Mapped[dict[str, Any] | None] = mapped_column()
    schema_errors: Mapped[list[Any] | None] = mapped_column()
    retrieved_chunk_ids: Mapped[list[Any]] = mapped_column(nullable=False, default=list)

    # SRS Step 49: each analysis must store prompt version, provider, model,
    # timestamp AND policy version. These two columns are the policy half.
    knowledge_base_version: Mapped[str | None] = mapped_column(String(64))
    policy_snapshot: Mapped[list[Any] | None] = mapped_column()

    tokens_in: Mapped[int | None] = mapped_column(Integer)
    tokens_out: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    cache_hit: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    error_message: Mapped[str | None] = mapped_column(Text)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<GenAIRun {self.pipeline} {self.status} attempt={self.attempt}>"


class ValidationRun(UUIDPrimaryKey, TimestampMixin, Base):
    """
    The output of Pipeline 2.

    Critically: this record is produced from (complaint, rules, policies,
    config) ONLY.  The GenAI result is not an input.  ``python_validation/cli.py``
    proves it by running with no API key configured at all.
    """

    __tablename__ = "validation_runs"
    __table_args__ = (
        Index("ix_valrun_complaint_created", "complaint_id", "created_at"),
        enum_check("derived_urgency", Urgency, name="derived_urgency_valid"),
    )

    complaint_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("complaints.id", ondelete="CASCADE"), nullable=False
    )
    ruleset_version: Mapped[str] = mapped_column(String(64), nullable=False)
    # Which knowledge-base state this ground truth was derived against.
    knowledge_base_version: Mapped[str | None] = mapped_column(String(64))

    # Deterministic signals extracted from the text (no model involved).
    signals: Mapped[dict[str, Any]] = mapped_column(nullable=False, default=dict)

    derived_category_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL")
    )
    derived_subcategory_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("subcategories.id", ondelete="SET NULL")
    )
    derived_department_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL")
    )
    derived_support_department_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL")
    )
    derived_urgency: Mapped[str | None] = mapped_column(String(16))
    derived_priority_code: Mapped[str | None] = mapped_column(
        ForeignKey("priority_levels.code", ondelete="SET NULL")
    )
    derived_escalation_code: Mapped[str | None] = mapped_column(
        ForeignKey("escalation_levels.code", ondelete="SET NULL")
    )
    # The floor that nothing downstream may lower - SRS 1.8 #7 Escalation Trap.
    escalation_floor_code: Mapped[str | None] = mapped_column(
        ForeignKey("escalation_levels.code", ondelete="SET NULL")
    )

    required_actions: Mapped[list[Any]] = mapped_column(nullable=False, default=list)
    prohibited_actions: Mapped[list[Any]] = mapped_column(nullable=False, default=list)
    policy_refs: Mapped[list[Any]] = mapped_column(nullable=False, default=list)
    follow_up_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # e.g. ["ESC-0007:SAFETY_LEXICON", "RPT-0012:REPEAT_3X"]
    reason_codes: Mapped[list[Any]] = mapped_column(nullable=False, default=list)
    # True when no rule matched - routes to manual review, never a silent default.
    unmatched: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # True when two same-precedence rules disagreed.
    conflict_detected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    latency_ms: Mapped[int | None] = mapped_column(Integer)

    rule_hits = relationship(
        "RuleHit", back_populates="validation_run", cascade="all, delete-orphan"
    )


class RuleHit(UUIDPrimaryKey, TimestampMixin, Base):
    """
    Which rules fired, and exactly which text spans triggered them.

    ``matched_spans`` is what powers the explainability panel that highlights
    "burning smell" inside the complaint as the reason escalation was forced.
    """

    __tablename__ = "rule_hits"
    __table_args__ = (
        Index("ix_rulehits_run", "validation_run_id"),
        Index("ix_rulehits_rule", "rule_id"),
    )

    validation_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("validation_runs.id", ondelete="CASCADE"), nullable=False
    )
    rule_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("rules.id", ondelete="CASCADE"), nullable=False
    )
    rule_ref: Mapped[str] = mapped_column(Code, nullable=False)  # denormalised for reporting
    precedence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    matched_signals: Mapped[list[Any]] = mapped_column(nullable=False, default=list)
    # [{"start": 41, "end": 54, "text": "burning smell", "signal": "safety_lexicon_hit"}]
    matched_spans: Mapped[list[Any]] = mapped_column(nullable=False, default=list)
    # False when the rule matched but lost on precedence - still recorded.
    applied: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    validation_run = relationship("ValidationRun", back_populates="rule_hits")
    rule = relationship("Rule", lazy="joined")
