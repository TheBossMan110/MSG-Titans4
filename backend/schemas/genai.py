"""
The structured contract Pipeline 1 must satisfy.

SRS Step 37/43-44: "The GenAI model must return results in a predefined
structured JSON format. Free-form responses must not be used as the only
application output." and "Python must validate: required fields, data types,
valid category values, valid urgency values, valid department IDs, valid
policy IDs, valid escalation status."

Two levels of validation, because they catch different failures:

* **Shape** — Pydantic enforces required fields, types and enum membership.
  A model returning ``"urgency": "quite high"`` fails here.
* **Reference** — a separate pass resolves every cited ``chunk_key`` against
  the knowledge base. A model returning a *well-formed* citation to a document
  that does not exist passes the shape check and fails this one. That second
  failure is the interesting one: it is a hallucination, not a formatting bug.

Enum values are injected into the prompt from the database at render time, so
adding a complaint category never requires editing this file — but the check
here still runs against the live values, so a model inventing a category is
caught even if the prompt was somehow stale.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# Bounded collections: an unbounded list from a model is a denial-of-service
# vector against our own database as much as a quality problem.
MAX_RESOLUTION_STEPS = 12
MAX_ENTITIES = 30
MAX_POLICY_REFS = 12
MAX_QUESTIONS = 6
MAX_GUIDANCE = 10

Sentiment = Literal["POSITIVE", "NEUTRAL", "NEGATIVE", "STRONGLY_NEGATIVE"]
Urgency = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
Priority = Literal["P0", "P1", "P2", "P3"]


class StrictModel(BaseModel):
    """
    Reject unknown fields.

    A model that invents ``"confidence": 0.93`` is telling us the prompt and
    the schema have drifted apart. Silently dropping it would hide that.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


# ══════════════════════════════════════════════════════════════
# components
# ══════════════════════════════════════════════════════════════
class ExtractedEntityOut(StrictModel):
    """SRS Step 16. Compared against Python's regex pass, never trusted alone."""

    entity_type: str = Field(max_length=64)
    value: str = Field(max_length=512)


class PolicyReferenceOut(StrictModel):
    """
    A citation the model claims supports its answer.

    ``chunk_key`` is the token we can resolve exactly; ``doc_ref`` and
    ``section_ref`` are the human-readable form. The prompt asks for the chunk
    key precisely so that an invented citation is *detectable* rather than
    merely plausible.
    """

    chunk_key: str | None = Field(default=None, max_length=255)
    doc_ref: str = Field(max_length=64)
    section_ref: str | None = Field(default=None, max_length=64)
    supports: str | None = Field(
        default=None, max_length=400,
        description="What this reference is being cited for.",
    )


class ResolutionStepOut(StrictModel):
    """SRS Step 27. Validated against the rule matrix's permitted actions."""

    step: str = Field(min_length=3, max_length=400)
    action_code: str | None = Field(default=None, max_length=64)
    policy_ref: str | None = Field(default=None, max_length=64)


class ClarificationQuestionOut(StrictModel):
    """SRS Step 43 — ask rather than invent."""

    question: str = Field(min_length=5, max_length=300)
    missing_field: str | None = Field(default=None, max_length=64)


class AgentGuidanceOut(StrictModel):
    """SRS Step 45 — internal, never shown to the customer."""

    guidance: str = Field(min_length=3, max_length=300)
    kind: Literal["ACTION", "CAUTION", "VERIFICATION", "ESCALATION", "INFORMATION"] = "ACTION"


# ══════════════════════════════════════════════════════════════
# the intelligence result
# ══════════════════════════════════════════════════════════════
class ComplaintIntelligence(StrictModel):
    """
    Everything Pipeline 1 returns for one complaint.

    Mirrors the sample structure in SRS 1.2 and extends it to cover the fields
    the later steps require.
    """

    # ── classification ──
    primary_issue: str = Field(min_length=3, max_length=200)
    secondary_issue: str | None = Field(default=None, max_length=200)
    category: str = Field(max_length=64)
    subcategory: str | None = Field(default=None, max_length=64)

    # ── assessment ──
    sentiment: Sentiment
    emotion_indicators: Annotated[list[str], Field(max_length=8)] = Field(default_factory=list)
    urgency: Urgency
    priority: Priority

    # ── routing ──
    department: str = Field(max_length=64)
    support_department: str | None = Field(default=None, max_length=64)

    # ── extraction ──
    entities: Annotated[list[ExtractedEntityOut], Field(max_length=MAX_ENTITIES)] = Field(
        default_factory=list
    )
    missing_information: Annotated[list[str], Field(max_length=8)] = Field(default_factory=list)

    # ── grounding ──
    policy_refs: Annotated[list[PolicyReferenceOut], Field(max_length=MAX_POLICY_REFS)] = Field(
        default_factory=list
    )

    # ── recommendation ──
    resolution_steps: Annotated[
        list[ResolutionStepOut], Field(max_length=MAX_RESOLUTION_STEPS)
    ] = Field(default_factory=list)
    escalation_required: bool = False
    escalation_level: str | None = Field(default=None, max_length=64)
    escalation_reason: str | None = Field(default=None, max_length=500)
    follow_up_required: bool = False

    # ── agent-facing ──
    summary: str = Field(min_length=10, max_length=1000)
    agent_guidance: Annotated[list[AgentGuidanceOut], Field(max_length=MAX_GUIDANCE)] = Field(
        default_factory=list
    )
    clarification_questions: Annotated[
        list[ClarificationQuestionOut], Field(max_length=MAX_QUESTIONS)
    ] = Field(default_factory=list)

    # ── self-report ──
    insufficient_information: bool = Field(
        default=False,
        description=(
            "Set when the complaint does not contain enough to classify "
            "confidently. Saying so is the correct answer; guessing is not."
        ),
    )

    @field_validator("category", "subcategory", "department", "support_department",
                     "escalation_level", mode="before")
    @classmethod
    def _upper(cls, value: Any) -> Any:
        """Codes are compared case-insensitively; normalise once, here."""
        return value.strip().upper() if isinstance(value, str) and value.strip() else None

    @model_validator(mode="after")
    def _escalation_consistency(self) -> ComplaintIntelligence:
        """
        An escalation claim must carry a level.

        Caught here rather than downstream because "escalation_required: true"
        with no level is ambiguous, and an ambiguous escalation is the failure
        mode SRS 1.8 #7 is testing for.
        """
        if self.escalation_required and not self.escalation_level:
            raise ValueError(
                "escalation_required is true but escalation_level is missing"
            )
        if self.escalation_level in {"NONE", ""} and self.escalation_required:
            raise ValueError(
                "escalation_required is true but escalation_level is NONE"
            )
        return self

    @model_validator(mode="after")
    def _insufficient_information_implies_questions(self) -> ComplaintIntelligence:
        """
        SRS Step 43: when information is insufficient the pipeline must ask a
        focused question "rather than inventing missing facts". Declaring the
        gap without asking anything is half an answer.
        """
        if self.insufficient_information and not self.clarification_questions:
            raise ValueError(
                "insufficient_information is true but no clarification question was asked"
            )
        return self


# ══════════════════════════════════════════════════════════════
# the customer response
# ══════════════════════════════════════════════════════════════
class CustomerResponse(StrictModel):
    """
    The customer-facing reply (SRS Steps 32-33).

    Generated only from the *reconciled* result, never from raw model output,
    and scanned by the response guard before any human sees it.
    """

    response_text: str = Field(min_length=20, max_length=4000)
    tone: Literal["PROFESSIONAL", "EMPATHETIC", "CONCISE", "FORMAL"] = "PROFESSIONAL"
    acknowledges_issue: bool = True
    citations: Annotated[list[PolicyReferenceOut], Field(max_length=MAX_POLICY_REFS)] = Field(
        default_factory=list
    )
    follow_up_message: str | None = Field(default=None, max_length=1000)


class EscalationNote(StrictModel):
    """Internal escalation note (SRS Step 38)."""

    complaint_summary: str = Field(min_length=10, max_length=1000)
    key_facts: Annotated[list[str], Field(max_length=10)] = Field(default_factory=list)
    reason_for_escalation: str = Field(min_length=5, max_length=500)
    actions_already_taken: Annotated[list[str], Field(max_length=10)] = Field(
        default_factory=list
    )
    relevant_policy: str | None = Field(default=None, max_length=200)
    required_next_action: str = Field(min_length=5, max_length=500)


# ══════════════════════════════════════════════════════════════
# provider-facing JSON Schema
# ══════════════════════════════════════════════════════════════
def json_schema_for(model: type[BaseModel]) -> dict[str, Any]:
    """
    A JSON Schema a provider's structured-output mode will accept.

    Gemini's schema support is a subset of JSON Schema: ``$ref``/``$defs``,
    ``additionalProperties`` and format annotations are rejected or ignored.
    Pydantic emits all of them, so the schema is inlined and pruned here rather
    than handed over raw.
    """
    schema = model.model_json_schema()
    definitions = schema.pop("$defs", {})
    return _simplify(_inline_refs(schema, definitions))


def _inline_refs(node: Any, definitions: dict[str, Any], depth: int = 0) -> Any:
    """Replace every ``$ref`` with the definition it points at."""
    if depth > 12:
        return {"type": "object"}
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/$defs/"):
            target = definitions.get(ref.split("/")[-1], {})
            merged = {**_inline_refs(target, definitions, depth + 1)}
            for key, value in node.items():
                if key != "$ref":
                    merged[key] = _inline_refs(value, definitions, depth + 1)
            return merged
        return {key: _inline_refs(value, definitions, depth + 1) for key, value in node.items()}
    if isinstance(node, list):
        return [_inline_refs(item, definitions, depth + 1) for item in node]
    return node


# Keys a provider either rejects or silently ignores.
#
# The length and bound constraints are the interesting ones. Gemini compiles a
# response schema into a constrained-decoding state machine and rejects the
# whole request with "too many states for serving" when that machine grows too
# large -- string min/max lengths and array item limits across ~25 fields are
# enough to trip it. Measured, not guessed: with them the API returns 400
# INVALID_ARGUMENT before generating a token.
#
# Dropping them here costs nothing, because the schema sent to a provider is a
# *shape hint* and was never the enforcement point. Every response is parsed by
# ComplaintIntelligence above, which applies the same bounds and rejects an
# over-long field regardless of what the provider was told.
_STRIPPED_KEYS = {
    "additionalProperties", "$schema", "$defs", "definitions",
    "discriminator", "examples", "const", "default", "format",
    "patternProperties", "title",
    # value matchers that inflate the decoder state machine
    "minLength", "maxLength", "minItems", "maxItems",
    "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum",
    "multipleOf", "pattern",
}


def _simplify(node: Any) -> Any:
    if isinstance(node, dict):
        cleaned: dict[str, Any] = {}
        for key, value in node.items():
            if key in _STRIPPED_KEYS:
                continue
            # anyOf[X, null] is how Pydantic spells Optional; providers handle
            # a plain nullable type far more reliably.
            if key == "anyOf" and isinstance(value, list):
                non_null = [
                    option for option in value
                    if not (isinstance(option, dict) and option.get("type") == "null")
                ]
                if len(non_null) == 1:
                    cleaned.update(_simplify(non_null[0]))
                    cleaned["nullable"] = len(non_null) != len(value)
                    continue
            cleaned[key] = _simplify(value)
        return cleaned
    if isinstance(node, list):
        return [_simplify(item) for item in node]
    return node


INTELLIGENCE_SCHEMA = json_schema_for(ComplaintIntelligence)
RESPONSE_SCHEMA = json_schema_for(CustomerResponse)
ESCALATION_NOTE_SCHEMA = json_schema_for(EscalationNote)
