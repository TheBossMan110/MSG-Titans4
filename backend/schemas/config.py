"""
Admin configuration and rule-editing payloads (SRS 1.8 #14).

The Live Modification Challenge asks an evaluator to change the system's
behaviour on stage and see the next complaint decided differently. Everything
that decides anything is already a database row rather than a constant; these
models are the surface that exposes those rows for editing.

Two things run through every model here.

**A change is refused at save time, not at evaluation time.** An administrator
editing a rule in front of judges gets told immediately that a condition is
malformed or references a signal nothing emits. The alternative is a rule that
saves cleanly and then quietly never fires, which looks like the system
ignoring the evaluator.

**A mandatory escalation rule is not editable into harmlessness.** The
escalation floor is enforced against the model, against the comparison engine
and against a human reviewer. An admin API able to deactivate the rule that
sets the floor would be a fourth way through, and the quietest of the four.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from schemas.common import APIModel


# ══════════════════════════════════════════════════════════════
# app_config
# ══════════════════════════════════════════════════════════════
class ConfigEntryOut(APIModel):
    """One configuration row."""

    key: str
    value: Any
    description: str | None = None
    version: int
    updated_by: str | None = None
    updated_at: datetime | None = None
    # False for rows whose shape other code depends on structurally.
    editable: bool = True


class ConfigUpdateIn(BaseModel):
    """A replacement value for one configuration key."""

    model_config = ConfigDict(extra="forbid")

    value: Any
    reason: str | None = Field(default=None, max_length=500)


# ══════════════════════════════════════════════════════════════
# taxonomy
# ══════════════════════════════════════════════════════════════
class CodeOut(APIModel):
    """One taxonomy code, as everything else refers to it."""

    code: str
    name: str
    description: str | None = None
    rank: int | None = None


class TaxonomyOut(APIModel):
    """
    Every vocabulary the rules are written against.

    Read-only through this API. A category code appears in rule outcomes, in
    SLA policies, in stored complaints and in the ground-truth labels, so
    renaming one from a form would silently orphan all four.
    """

    categories: list[CodeOut] = Field(default_factory=list)
    subcategories: list[CodeOut] = Field(default_factory=list)
    departments: list[CodeOut] = Field(default_factory=list)
    priority_levels: list[CodeOut] = Field(default_factory=list)
    escalation_levels: list[CodeOut] = Field(default_factory=list)


# ══════════════════════════════════════════════════════════════
# rules
# ══════════════════════════════════════════════════════════════
class RuleSummaryOut(APIModel):
    """One rule in a list."""

    rule_ref: str
    name: str
    rule_type: str
    precedence: int
    is_active: bool
    is_mandatory_escalation: bool
    is_catch_all: bool
    outcome_escalation_code: str | None = None
    outcome_urgency: str | None = None
    outcome_priority_code: str | None = None
    version: int
    # False when this rule sets a mandatory escalation: see the module note.
    can_deactivate: bool = True


class RuleDetailOut(RuleSummaryOut):
    """One rule, in full."""

    conditions: Any = None
    rationale: str | None = None
    policy_refs: Any = None
    required_actions: Any = None
    prohibited_actions: Any = None
    eligibility: Any = None
    follow_up_required: bool = False
    source_ref: str | None = None
    outcome_category: str | None = None
    outcome_subcategory: str | None = None
    outcome_department: str | None = None
    outcome_support_department: str | None = None
    signals_referenced: list[str] = Field(default_factory=list)


class RuleUpdateIn(BaseModel):
    """
    An edit to one rule.

    Every field is optional and only the ones supplied are changed, so an
    evaluator can flip a single precedence without restating the whole rule
    and accidentally clearing its rationale.
    """

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=200)
    conditions: Any = None
    precedence: int | None = Field(default=None, ge=0, le=10_000)
    is_active: bool | None = None
    rationale: str | None = Field(default=None, max_length=2000)
    outcome_urgency: str | None = Field(default=None, max_length=32)
    outcome_priority_code: str | None = Field(default=None, max_length=32)
    outcome_escalation_code: str | None = Field(default=None, max_length=64)
    outcome_category: str | None = Field(default=None, max_length=64)
    outcome_subcategory: str | None = Field(default=None, max_length=64)
    outcome_department: str | None = Field(default=None, max_length=64)
    follow_up_required: bool | None = None
    reason: str | None = Field(default=None, max_length=500)


class RuleChangeOut(APIModel):
    """What an edit changed, and what it cost."""

    rule: RuleDetailOut
    changed_fields: list[str] = Field(default_factory=list)
    ruleset_version: str
    # Stated so an evaluator can see the edit is already live rather than
    # being told it is.
    active_rule_count: int


class RuleTestIn(BaseModel):
    """A complaint to try the rules against, without storing anything."""

    model_config = ConfigDict(extra="forbid")

    description: str = Field(min_length=1, max_length=20_000)
    title: str = Field(default="Rule test", max_length=300)
    product: str | None = Field(default=None, max_length=200)
    order_ref: str | None = Field(default=None, max_length=64)
    amount: float | None = None


class RuleTestOut(APIModel):
    """
    What Pipeline 2 alone concludes about that text, right now.

    Deterministic and free: no provider is called and nothing is written, so
    an evaluator can change a rule and re-run this as many times as they like
    without spending the free-tier quota or filling the complaint register
    with test rows.
    """

    category: str | None = None
    subcategory: str | None = None
    department: str | None = None
    support_department: str | None = None
    urgency: str | None = None
    priority: str | None = None
    escalation_code: str | None = None
    escalation_floor_code: str | None = None
    escalation_required: bool = False
    follow_up_required: bool = False
    matched_rules: list[str] = Field(default_factory=list)
    mandatory_escalation_refs: list[str] = Field(default_factory=list)
    signals_fired: list[str] = Field(default_factory=list)
    required_actions: list[str] = Field(default_factory=list)
    prohibited_actions: list[str] = Field(default_factory=list)
    unmatched: bool = False
    conflict_detected: bool = False
    ruleset_version: str
    latency_ms: int | None = None


# ══════════════════════════════════════════════════════════════
# lexicon
# ══════════════════════════════════════════════════════════════
class LexiconTermOut(APIModel):
    """One term that raises a signal."""

    id: str
    signal_key: str
    term: str
    match_type: str
    weight: float | None = None
    description: str | None = None
    is_active: bool = True
    # True when this signal is analytics-only: SRS 1.8 #6 forbids it from
    # influencing urgency or priority, whatever weight it carries.
    analytics_only: bool = False


class LexiconTermIn(BaseModel):
    """A new or edited lexicon term."""

    model_config = ConfigDict(extra="forbid")

    signal_key: str = Field(min_length=1, max_length=64)
    term: str = Field(min_length=1, max_length=200)
    # PHRASE, REGEX or WORD -- the database's own vocabulary.
    match_type: str = Field(default="PHRASE", max_length=32)
    weight: float | None = Field(default=None, ge=0, le=10)
    description: str | None = Field(default=None, max_length=500)
    is_active: bool = True


class LexiconTermUpdateIn(BaseModel):
    """An edit to one term."""

    model_config = ConfigDict(extra="forbid")

    term: str | None = Field(default=None, min_length=1, max_length=200)
    match_type: str | None = Field(default=None, max_length=32)
    weight: float | None = Field(default=None, ge=0, le=10)
    description: str | None = Field(default=None, max_length=500)
    is_active: bool | None = None


# ══════════════════════════════════════════════════════════════
# SLA
# ══════════════════════════════════════════════════════════════
class SLAPolicyOut(APIModel):
    """One SLA target."""

    id: str
    category: str | None = None
    priority_code: str | None = None
    first_response_mins: int
    resolution_mins: int
    risk_threshold_pct: int | None = None
    is_active: bool = True


class SLAPolicyUpdateIn(BaseModel):
    """
    An edit to one SLA target.

    Retuning these moves the follow-up schedule with them: due dates are a
    fraction of the first-response window rather than a separate constant, so
    the two cannot drift apart.
    """

    model_config = ConfigDict(extra="forbid")

    first_response_mins: int | None = Field(default=None, ge=1, le=100_000)
    resolution_mins: int | None = Field(default=None, ge=1, le=1_000_000)
    risk_threshold_pct: int | None = Field(default=None, ge=1, le=100)
    is_active: bool | None = None
    reason: str | None = Field(default=None, max_length=500)


# ══════════════════════════════════════════════════════════════
# prompts
# ══════════════════════════════════════════════════════════════
class PromptVersionOut(APIModel):
    """One prompt template version."""

    name: str
    version: str
    is_active: bool
    checksum: str | None = None
    variables: list[str] = Field(default_factory=list)
    template_text: str | None = None


class PromptActivateIn(BaseModel):
    """Switch which version of a prompt is used."""

    model_config = ConfigDict(extra="forbid")

    version: str = Field(min_length=1, max_length=32)
    reason: str | None = Field(default=None, max_length=500)


# ══════════════════════════════════════════════════════════════
# revert
# ══════════════════════════════════════════════════════════════
class ReloadOut(APIModel):
    """
    What a reload from the YAML source restored.

    The undo for the Live Modification Challenge: whatever was changed on
    stage goes back to the committed configuration in one call.
    """

    reloaded: dict[str, int] = Field(default_factory=dict)
    ruleset_version: str
    active_rule_count: int


# ══════════════════════════════════════════════════════════════
# the deliberate defect
# ══════════════════════════════════════════════════════════════
class DefectSpecOut(APIModel):
    """One deliberate defect, documented before it is demonstrated."""

    code: str
    name: str
    breaks: str
    detected_by: str
    why_it_matters: str
    severity: str


class DefectFindingOut(APIModel):
    """What the detector said."""

    flag_type: str
    severity: str
    explanation: str
    matched_text: str | None = None
    promise_type: str | None = None


class DefectResultOut(DefectSpecOut):
    """
    A deliberately broken artefact and the real detector's verdict on it
    (SRS 1.8 #15).

    Nothing here is installed. The faulty artefact is built inside the request,
    checked by the production detector, and discarded — there is no flag that
    makes the system behave badly, because a switch that can be left on stops
    the defect being deliberate.
    """

    faulty_artefact: str
    detected: bool
    detector: str
    findings: list[DefectFindingOut] = Field(default_factory=list)
    # Set when the safeguard corrected rather than refused, as the escalation
    # floor does: the value it was raised to.
    corrected_to: str | None = None
    explanation: str
