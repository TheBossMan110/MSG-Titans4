"""
Deterministic signal configuration used by **Pipeline 2 only**.

These tables are what allow the Python ground-truth pipeline to reach its own
conclusion about a complaint without ever calling a language model
(SRS 1.8 #18 — "The GenAI API must not replace Python business rules").

Storing them as rows rather than Python constants is also what makes the
Prompt-Injection and Live-Modification challenges answerable on stage.
"""

from __future__ import annotations

from sqlalchemy import Boolean, CheckConstraint, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base, Code, TimestampMixin, UUIDPrimaryKey
from src.db.constraints import enum_check
from src.db.enums import Severity


class LexiconTerm(UUIDPrimaryKey, TimestampMixin, Base):
    """
    Maps a phrase/regex to a named *signal* that rule conditions can test.

    Example
    -------
    signal_key='safety_lexicon_hit', term='burning smell'
    signal_key='legal_threat',       term='(lawyer|solicitor|legal action)', match_type='REGEX'

    This is the mechanism behind SRS 1.8 #6 (Sentiment–Urgency Trap): urgency
    is derived from *risk signals in the text*, never from tone.
    """

    __tablename__ = "lexicon_terms"
    __table_args__ = (
        UniqueConstraint("signal_key", "term", name="uq_lexicon_signal_term"),
        CheckConstraint("match_type IN ('PHRASE','REGEX','WORD')", name="match_type_valid"),
    )

    signal_key: Mapped[str] = mapped_column(Code, nullable=False, index=True)
    term: Mapped[str] = mapped_column(String(255), nullable=False)
    match_type: Mapped[str] = mapped_column(String(16), nullable=False, default="PHRASE")
    weight: Mapped[float] = mapped_column(Numeric(4, 2), nullable=False, default=1.0)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class InjectionPattern(UUIDPrimaryKey, TimestampMixin, Base):
    """
    SRS Step 50/51 — prompt-injection detection patterns.

    Layer 2 of the four-layer defence.  Layer 4 is structural: Pipeline 2 has
    no instruction-following surface at all, so even a fully compromised model
    cannot change routing, escalation or eligibility.
    """

    __tablename__ = "injection_patterns"
    __table_args__ = (enum_check("severity", Severity),)

    pattern: Mapped[str] = mapped_column(String(512), nullable=False)
    label: Mapped[str] = mapped_column(Code, nullable=False)   # INSTRUCTION_OVERRIDE, ROLE_HIJACK…
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default=Severity.MEDIUM)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class PromisePattern(UUIDPrimaryKey, TimestampMixin, Base):
    """
    SRS Step 34 — unsupported-promise detection for the response guard.

    Each match is cross-checked against the permitted_actions derived by
    Pipeline 2; anything not permitted is flagged, redacted or regenerated.
    """

    __tablename__ = "promise_patterns"

    pattern: Mapped[str] = mapped_column(String(512), nullable=False)
    promise_type: Mapped[str] = mapped_column(Code, nullable=False)  # REFUND, COMPENSATION…
    requires_action: Mapped[str | None] = mapped_column(Code)        # permitted action it needs
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
