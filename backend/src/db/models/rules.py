"""
The Complaint Resolution Rule Matrix — the ground truth of the whole system.

SRS Step 8:  "Teams must create a structured rule matrix representing approved
complaint-handling logic.  The matrix must NOT simply be generated at runtime
by the same GenAI model responsible for complaint resolution."

So: rules are authored by humans as YAML in ``complaint_rules/`` (a required
deliverable), loaded into this table by a seeder, and edited at runtime through
the admin API — which is how the Live Modification Challenge (SRS 1.8 #14) is
answered without a deploy.

``conditions`` holds a small declarative DSL that the engine interprets.  It is
*data*, never ``eval()``-ed:

    {"any_of": [
        {"signal": "safety_lexicon_hit"},
        {"all_of": [{"field": "category", "eq": "PRODUCT_DEFECT"},
                    {"signal": "injury_mention"}]}
    ]}
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base, Code, Name, TimestampMixin, UpdatedAtMixin, UUIDPrimaryKey
from src.db.constraints import enum_check
from src.db.enums import RuleType, Urgency


class Rule(UUIDPrimaryKey, TimestampMixin, UpdatedAtMixin, Base):
    __tablename__ = "rules"
    __table_args__ = (
        Index("ix_rules_active_precedence", "is_active", "precedence"),
        Index("ix_rules_mandatory", "is_mandatory_escalation", "is_active"),
        enum_check("rule_type", RuleType),
        enum_check("outcome_urgency", Urgency, name="outcome_urgency_valid"),
    )

    rule_ref: Mapped[str] = mapped_column(Code, nullable=False, unique=True)  # e.g. ESC-0007
    name: Mapped[str] = mapped_column(Name, nullable=False)
    rule_type: Mapped[str] = mapped_column(String(32), nullable=False)

    # Optional scoping: only evaluate this rule for a given category/subcategory.
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("categories.id", ondelete="CASCADE")
    )
    subcategory_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("subcategories.id", ondelete="CASCADE")
    )

    # ── WHEN ────────────────────────────────────────────────
    conditions: Mapped[dict[str, Any]] = mapped_column(nullable=False, default=dict)

    # ── THEN ────────────────────────────────────────────────
    outcome_category_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL")
    )
    outcome_subcategory_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("subcategories.id", ondelete="SET NULL")
    )
    outcome_department_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL")
    )
    outcome_support_department_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL")
    )
    outcome_urgency: Mapped[str | None] = mapped_column(String(16))
    outcome_priority_code: Mapped[str | None] = mapped_column(
        ForeignKey("priority_levels.code", ondelete="SET NULL")
    )
    outcome_escalation_code: Mapped[str | None] = mapped_column(
        ForeignKey("escalation_levels.code", ondelete="SET NULL")
    )

    required_actions: Mapped[list[Any]] = mapped_column(nullable=False, default=list)
    prohibited_actions: Mapped[list[Any]] = mapped_column(nullable=False, default=list)
    # [{"doc_ref": "DEL-POL-04", "section_ref": "5.2", "min_version": "2.0"}]
    policy_refs: Mapped[list[Any]] = mapped_column(nullable=False, default=list)
    follow_up_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # ── CONTROL ─────────────────────────────────────────────
    precedence: Mapped[int] = mapped_column(Integer, nullable=False, default=50)  # higher wins
    # When true this rule sets an escalation FLOOR that nothing downstream
    # (including the GenAI result) is allowed to lower.  SRS 1.8 #7.
    is_mandatory_escalation: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # A catch-all gives an unrecognised complaint a queue to land in without
    # claiming to have recognised it. The engine still reports `unmatched` when
    # only catch-alls fired, so "we do not know" never becomes a confident
    # answer.
    is_catch_all: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Refund / replacement / compensation eligibility finding (SRS Steps 29-31).
    # A dedicated column, not metadata smuggled into `conditions`: the condition
    # evaluator must only ever see a condition tree.
    eligibility: Mapped[dict[str, Any] | None] = mapped_column()
    # Human-readable justification shown in the explainability panel.
    rationale: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source_ref: Mapped[str | None] = mapped_column(String(255))  # YAML file it came from

    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

    # Scope relationships. Without these, `rule.category` resolves to None and
    # `_in_scope()` silently passes every rule - a Billing rule would fire on a
    # Safety complaint. The scope columns existed; the mappings did not.
    category = relationship("Category", foreign_keys=[category_id], lazy="joined")
    subcategory = relationship("Subcategory", foreign_keys=[subcategory_id], lazy="joined")

    outcome_category = relationship("Category", foreign_keys=[outcome_category_id], lazy="joined")
    outcome_subcategory = relationship(
        "Subcategory", foreign_keys=[outcome_subcategory_id], lazy="joined"
    )
    outcome_department = relationship(
        "Department", foreign_keys=[outcome_department_id], lazy="joined"
    )
    outcome_support_department = relationship(
        "Department", foreign_keys=[outcome_support_department_id], lazy="joined"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Rule {self.rule_ref} p={self.precedence}>"
