"""
Complaint API contracts.

Every field a complaint endpoint returns is declared here. SRS 1.6 states twice
that free-form GenAI output must not be the only application output, so the
API's shape is a typed contract rather than whatever the model produced — and
the frontend generates its TypeScript from it.

Two things are deliberately absent from :class:`ComplaintDetail`:

* the ``expected_*`` benchmark labels, which are ground truth for scoring and
  must never be visible to anything that could be trained or tuned on them;
* raw Pipeline 1 output, which is reachable only through the explainability
  endpoint. The agent view shows what the system *decided*, and mixing an
  overridden model opinion into it would undo the comparison engine's work.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from schemas.common import APIModel
from src.core.config import settings
from src.db.enums import Channel


# ══════════════════════════════════════════════════════════════
# submission
# ══════════════════════════════════════════════════════════════
class ComplaintCreate(APIModel):
    """
    A new complaint (FR iii; SRS Step 9).

    Bounds here are generous on purpose. A complaint that is too short or
    carries an unrecognised reference is **accepted** and flagged, because a
    customer with a badly-formed complaint still has a complaint. The only
    thing rejected outright is an empty one, and that is enforced by the
    minimum length below.
    """

    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=settings.max_complaint_length * 2)

    customer_email: str | None = Field(default=None, max_length=320)
    customer_name: str | None = Field(default=None, max_length=255)

    product: str | None = Field(default=None, max_length=255)
    order_ref: str | None = Field(default=None, max_length=64)
    transaction_ref: str | None = Field(default=None, max_length=64)
    amount: float | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, max_length=8)
    channel: str = Field(default="WEB", max_length=16)
    requested_resolution: str | None = Field(default=None, max_length=2000)
    attachments: list[dict[str, Any]] = Field(default_factory=list, max_length=10)

    # Only an evaluator seeding the benchmark corpus sets this.
    dataset_tag: str | None = Field(default=None, max_length=32)

    @field_validator("channel")
    @classmethod
    def _upper(cls, value: str) -> str:
        # The table's CHECK constraint accepts only these; anything else must be
        # a clear 422 here, not a database error after the pipelines have run.
        value = value.strip().upper()
        allowed = {c.value for c in Channel}
        if value not in allowed:
            raise ValueError(f"channel must be one of {', '.join(sorted(allowed))}")
        return value


# ══════════════════════════════════════════════════════════════
# components
# ══════════════════════════════════════════════════════════════
class ValidationIssueOut(APIModel):
    code: str
    message: str
    severity: str
    outcome: str
    field: str | None = None


class LinkOut(APIModel):
    link_type: str
    related_ref: str
    related_status: str | None = None
    similarity: float | None = None
    detected_by: str


class EntityOut(APIModel):
    entity_type: str
    value: str
    normalized: str | None = None
    extracted_by: str
    span_start: int | None = None
    span_end: int | None = None


class ResolutionStepOut(APIModel):
    ordinal: int
    text: str
    action_code: str | None = None
    source: str
    status: str
    rule_ref: str | None = None
    policy_ref: str | None = None


class GuidanceOut(APIModel):
    ordinal: int
    text: str
    kind: str
    source: str
    # Rule-derived guidance an agent cannot dismiss. The flag is the whole
    # point: "do not confirm a refund before eligibility is verified" is
    # policy, not a suggestion.
    is_mandatory: bool
    rule_ref: str | None = None


class ClarificationOut(APIModel):
    id: uuid.UUID | None = None
    ordinal: int
    question: str
    missing_field: str | None = None
    answered_at: datetime | None = None
    # The customer's reply. Screened for injection before it was stored.
    answer: str | None = None


class EvidenceOut(APIModel):
    """One file a customer (or an agent on their behalf) attached."""

    id: uuid.UUID
    file_name: str
    mime_type: str
    size_bytes: int
    uploaded_at: datetime | None = None


class EligibilityOut(APIModel):
    eligibility_type: str
    final_outcome: str
    python_outcome: str
    requires_human_approval: bool
    conditions_evaluated: list[Any] = Field(default_factory=list)
    rule_ref: str | None = None
    reason: str = ""


class ScoreOut(APIModel):
    """A percentage with the evidence behind it (SRS 1.8 #17)."""

    value: float | None = None
    numerator: int = 0
    denominator: int = 0


class VerificationOut(APIModel):
    outcome: str
    agreement_score: float | None = None
    traceability_score: float | None = None
    compliance_score: float | None = None
    critical_mismatches: int = 0
    high_mismatches: int = 0
    matched_fields: int = 0
    total_fields: int = 0
    requires_review: bool = False
    review_reasons: list[str] = Field(default_factory=list)
    genai_available: bool = True


class ComparisonOut(APIModel):
    """One field, both pipelines' readings, and why they differ."""

    field: str
    genai_value: str | None = None
    python_value: str | None = None
    final_value: str | None = None
    status: str
    severity: str
    winner: str | None = None
    reason_code: str | None = None
    explanation: str | None = None


# ══════════════════════════════════════════════════════════════
# complaint views
# ══════════════════════════════════════════════════════════════
class AssignIn(BaseModel):
    """Who should handle the complaint. ``null`` releases it back to the team."""

    user_id: uuid.UUID | None = None


class AssigneeOut(APIModel):
    id: uuid.UUID
    full_name: str
    role: str


class AssignOut(APIModel):
    public_ref: str
    assigned_to: AssigneeOut | None = None


class FileDraftOut(APIModel):
    """A complaint read out of an uploaded file, for the customer to check before filing."""

    file_name: str
    file_format: str
    title: str
    description: str
    order_ref: str | None = None
    pages: int | None = None
    notes: list[str] = []


class ComplaintSummary(APIModel):
    """One row in a queue or list."""

    id: uuid.UUID
    public_ref: str
    title: str
    status: str
    category: str | None = None
    subcategory: str | None = None
    department: str | None = None
    urgency: str | None = None
    priority_code: str | None = None
    escalation_code: str | None = None
    verification_outcome: str | None = None
    injection_suspected: bool = False
    is_duplicate: bool = False
    repeat_count: int = 0
    created_at: datetime | None = None
    # Who raised it ("Business/Merchant Account") and which dataset it came in
    # with, if any. Staff views only: the customer-facing status never has them.
    customer_type: str | None = None
    dataset_tag: str | None = None
    # WEB, CHAT, EMAIL, UPLOAD...: how it reached us, so a new one is recognisable.
    channel: str | None = None
    agreement_score: float | None = None


class ComplaintDetail(ComplaintSummary):
    """Everything an agent needs to work one complaint."""

    description_raw: str
    description_clean: str
    support_department: str | None = None
    sentiment: str | None = None
    primary_issue: str | None = None
    secondary_issue: str | None = None
    summary: str | None = None

    # Analytics only. Recorded, shown, and structurally unable to reach the
    # rule engine — which is the whole of SRS 1.8 #6.
    emotion_indicators: list[Any] = Field(default_factory=list)
    missing_information: list[Any] = Field(default_factory=list)

    product: str | None = None
    order_ref: str | None = None
    transaction_ref: str | None = None
    amount: float | None = None
    currency: str | None = None
    customer_ref: str | None = None
    # Who is handling it; null while it waits for someone to take it.
    assigned_to: AssigneeOut | None = None

    analyzed_at: datetime | None = None
    validated_at: datetime | None = None

    verification: VerificationOut | None = None
    validation_issues: list[ValidationIssueOut] = Field(default_factory=list)
    links: list[LinkOut] = Field(default_factory=list)
    entities: list[EntityOut] = Field(default_factory=list)
    resolution_steps: list[ResolutionStepOut] = Field(default_factory=list)
    guidance: list[GuidanceOut] = Field(default_factory=list)
    clarifications: list[ClarificationOut] = Field(default_factory=list)
    eligibility: list[EligibilityOut] = Field(default_factory=list)
    evidence: list[EvidenceOut] = Field(default_factory=list)


class IntakeResponse(APIModel):
    """
    What the submitter gets back.

    **Who submitted decides the shape.** Staff get the full agent view in
    ``complaint``. A customer gets ``customer_view`` and ``complaint`` is
    null: the agent view carries priority, escalation level, the verification
    decision and internal guidance, which the tracking page deliberately
    withholds — and returning them from the submit call would have leaked
    exactly that through the side door. ``public_ref`` is present for both.
    """

    public_ref: str
    complaint: ComplaintDetail | None = None
    customer_view: ComplaintStatusOut | None = None
    accepted: bool = True
    analysed: bool = False
    analysis_error: str | None = None
    validation_issues: list[ValidationIssueOut] = Field(default_factory=list)
    duplicate_of: str | None = None
    repeat_count: int = 0
    preprocessing: dict[str, Any] = Field(default_factory=dict)


# ══════════════════════════════════════════════════════════════
# explainability
# ══════════════════════════════════════════════════════════════
class RuleHitOut(APIModel):
    """One rule that fired, and the text that made it fire."""

    rule_ref: str
    precedence: int | None = None
    mandatory_escalation: bool = False
    applied: bool = True
    rationale: str | None = None
    signals: list[Any] = Field(default_factory=list)
    spans: list[Any] = Field(default_factory=list)


class GenAIRunOut(APIModel):
    """One attempt, including the failures — the retry evidence."""

    attempt: int
    pipeline: str
    provider: str
    model: str
    status: str
    prompt: str
    knowledge_base_version: str | None = None
    cited_chunks: int = 0
    tokens: dict[str, Any] = Field(default_factory=dict)
    latency_ms: int | None = None
    cache_hit: bool = False
    schema_errors: Any = None
    error: str | None = None
    created_at: str | None = None
    raw_json: Any = None
    response_raw: str | None = None


class TraceRowOut(APIModel):
    """One policy reference and whether it holds up."""

    source: str
    doc_ref: str
    version: str | None = None
    section: str | None = None
    page: int | None = None
    chunk_key: str | None = None
    resolved: bool
    was_active: bool
    applicability: str
    reason: str | None = None


class PolicyConflictOut(APIModel):
    """
    One policy that was overruled by another (SRS 1.8 #10).

    Recorded rather than resolved silently. A system that quietly follows the
    higher policy looks identical to one that never noticed the lower one
    existed, and the second is worth nothing to anybody auditing it.
    """

    overruled_ref: str
    overruled_section: str | None = None
    overruled_version: str | None = None
    overruled_tier: str | None = None
    governed_by_ref: str
    reason: str | None = None


class ExplainResponse(APIModel):
    """
    Why the system decided what it decided (FR lxiv).

    The whole chain in one payload: which rules fired and on what text, what
    each pipeline said, where they disagreed, every policy reference with its
    verdict, and every model attempt including the failed ones. Nothing here
    is recomputed for display — it is read back from stored rows, so what a
    judge sees is provably what the system did.
    """

    public_ref: str
    verification: VerificationOut | None = None
    reconciled: dict[str, Any] = Field(default_factory=dict)
    comparisons: list[ComparisonOut] = Field(default_factory=list)
    rule_hits: list[RuleHitOut] = Field(default_factory=list)
    reason_codes: list[str] = Field(default_factory=list)
    escalation_floor: str | None = None
    genai_runs: list[GenAIRunOut] = Field(default_factory=list)
    policy_trace: list[TraceRowOut] = Field(default_factory=list)
    policy_conflicts: list[PolicyConflictOut] = Field(default_factory=list)
    ruleset_version: str | None = None
    knowledge_base_version: str | None = None


class ReanalyseResponse(APIModel):
    public_ref: str
    verification: VerificationOut | None = None
    changed: dict[str, Any] = Field(default_factory=dict)


# ══════════════════════════════════════════════════════════════
# the customer's own view
# ══════════════════════════════════════════════════════════════
class CustomerQuestionOut(APIModel):
    """A clarifying question as the customer sees it: answerable, not annotated."""

    id: uuid.UUID
    ordinal: int
    question: str
    answered: bool = False
    answer: str | None = None
    answered_at: datetime | None = None


class MilestoneOut(APIModel):
    """
    One step of the customer-facing timeline.

    Derived from the status history, but in the customer's vocabulary. The
    internal states (ANALYZED, MANUAL_REVIEW, ESCALATED) are collapsed on
    purpose: "a specialist is looking at it" is the truth a customer needs,
    and "your case is in manual review because the model and the rules
    disagreed" is not.
    """

    key: str
    label: str
    detail: str | None = None
    reached: bool = False
    current: bool = False
    at: datetime | None = None


class DepartmentContactOut(APIModel):
    """The team handling a customer's complaint, and how to reach it."""

    name: str
    summary: str | None = None
    email: str | None = None
    support_hours: str | None = None


class FollowUpOut(APIModel):
    id: str
    type: str
    message: str | None = None
    due_at: str | None = None
    completed_at: str | None = None
    open: bool = True


class ComplaintStatusOut(APIModel):
    """
    What a customer may see about their own complaint (FR lxvi).

    Deliberately a separate model rather than a filtered ``ComplaintDetail``.
    The agent view carries internal guidance, rule references, eligibility
    reasoning and the pipeline comparison — none of which a customer should
    read, and a shared model with optional fields is one careless serialiser
    change away from leaking all of it.

    Notably absent: ``escalation_code``. That a complaint was escalated to
    compliance review is an internal routing fact; telling the customer a
    specialist will contact them is the same information without handing them
    a lever to argue about.

    ``department`` IS shown — the team handling it and how to reach them. This
    was a product decision (2026-09-25): a customer who knows which team has
    their case, and has that team's address, has a direct line instead of a
    general queue. It does reveal how a complaint was routed ("Account Security
    & Fraud Prevention" says something), which is why the escalation *level*
    and the priority still stay out.
    """

    public_ref: str
    title: str
    status: str
    submitted_at: datetime | None = None
    category: str | None = None
    category_name: str | None = None
    summary: str | None = None
    # True when the system has escalated internally — the fact, not the level.
    escalated: bool = False
    awaiting_information: list[str] = Field(default_factory=list)
    last_updated: datetime | None = None
    # When the organisation aims to have it resolved, if an SLA applies.
    target_resolution_at: datetime | None = None
    # The team handling it. A name and a mailbox — never the escalation level.
    department: DepartmentContactOut | None = None
    questions: list[CustomerQuestionOut] = Field(default_factory=list)
    milestones: list[MilestoneOut] = Field(default_factory=list)
    evidence: list[EvidenceOut] = Field(default_factory=list)
    # True when the next move is the customer's: an open question to answer.
    action_needed: bool = False
    follow_ups: list[FollowUpOut] = Field(default_factory=list)


# ══════════════════════════════════════════════════════════════
# the completion stages
# ══════════════════════════════════════════════════════════════
class ChecklistStepOut(APIModel):
    """
    One resolution step as an agent sees it (FR xxv; SRS Step 28).

    ``confirmable`` is the field the UI hangs a tick-box off. Only a
    rule-required step is confirmable — a generated suggestion is advice, and
    letting someone "complete" advice would blur the line the checklist exists
    to draw.
    """

    id: str
    ordinal: int
    text: str
    source: str
    status: str
    confirmable: bool
    policy_ref: str | None = None
    explanation: str | None = None


class ResolutionSummaryOut(APIModel):
    steps: int = 0
    required: int = 0
    confirmed: int = 0
    # Null when the rules impose no obligations — there was nothing to do,
    # which is not the same as nothing having been done.
    coverage_pct: float | None = None
    prohibited: int = 0
    unsupported: int = 0
    complete: bool = False
    by_status: dict[str, int] = Field(default_factory=dict)


class ChecklistOut(APIModel):
    summary: ResolutionSummaryOut
    steps: list[ChecklistStepOut] = Field(default_factory=list)


class DueFollowUpOut(APIModel):
    id: str
    public_ref: str
    priority: str | None = None
    type: str
    message: str | None = None
    due_at: str | None = None
    overdue_minutes: float | None = None


class EscalationOut(APIModel):
    """
    The escalation and its handover note (FR xxxv; SRS Step 38).

    ``note_available`` distinguishes "not escalated" from "escalated while no
    provider was reachable". The second is a degraded handover an agent should
    know about; conflating them would hide it.
    """

    escalation_code: str
    triggered_by: str
    rule_ref: str | None = None
    reason: str | None = None
    notes: str | None = None
    note_available: bool = False
    acknowledged_at: str | None = None


# ══════════════════════════════════════════════════════════════
# lifecycle
# ══════════════════════════════════════════════════════════════
class StatusChangeIn(APIModel):
    """A requested status change (FR lxv; SRS Step 60)."""

    to_status: str
    reason: str | None = Field(default=None, max_length=500)


class StatusHistoryRowOut(APIModel):
    """One transition.

    ``changed_by`` reads ``pipeline`` rather than null for a machine
    transition: a move nobody made is not a move by an unknown person, and the
    distinction is what a trail is read for.
    """

    from_status: str | None = None
    to_status: str
    changed_by: str
    reason: str | None = None
    at: str | None = None


class LifecycleOut(APIModel):
    """Where a complaint is, how it got here, and where it may go next."""

    public_ref: str
    status: str
    available_actions: list[str] = Field(default_factory=list)
    history: list[StatusHistoryRowOut] = Field(default_factory=list)


# ══════════════════════════════════════════════════════════════
# customer actions
# ══════════════════════════════════════════════════════════════
class ClarificationAnswerIn(BaseModel):
    answer: str = Field(min_length=1, max_length=2000)


class ClarificationAnswerOut(APIModel):
    status: ComplaintStatusOut
    # Complaint fields the answer filled, e.g. {"order_ref": "CN-482913"}.
    filled: dict[str, str] = Field(default_factory=dict)
    all_answered: bool = False
    status_changed_to: str | None = None


class PreviewIn(BaseModel):
    title: str = Field(default="", max_length=300)
    description: str = Field(default="", max_length=10_000)


class PreviewEntityOut(APIModel):
    type: str
    value: str
    start: int
    end: int


class PreviewHintOut(APIModel):
    field: str
    message: str


class PreviewCategoryOut(APIModel):
    code: str
    name: str


class PreviewOut(APIModel):
    """What the pipelines will read in a draft complaint. Nothing is stored."""

    entities: list[PreviewEntityOut] = Field(default_factory=list)
    entity_counts: dict[str, int] = Field(default_factory=dict)
    has_reference: bool = False
    words: int = 0
    characters: int = 0
    injection_suspected: bool = False
    likely_category: PreviewCategoryOut | None = None
    hints: list[PreviewHintOut] = Field(default_factory=list)


IntakeResponse.model_rebuild()
