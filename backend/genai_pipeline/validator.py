"""
Output validation for Pipeline 1 (SRS Steps 43-44, 47; FR xlix-li).

    "Python must validate: required fields, data types, valid category values,
     valid urgency values, valid department IDs, valid policy IDs, valid
     escalation status."                                   — SRS Step 43

    "If validation fails, the system must retry with a corrected instruction,
     apply a fallback, or reject the output. Retries must be bounded."
                                                           — SRS Step 47

Four gates, in order of how cheaply they fail:

1. **Extraction** — find the JSON object in the text. Models wrap output in
   markdown fences and prose even when told not to, which is a formatting
   problem, not a reasoning one, and is fixed locally rather than by spending
   another API call.
2. **Shape** — Pydantic. Required fields, types, enum membership, and the two
   cross-field invariants.
3. **Reference** — every code checked against the live database. A model can
   return a perfectly-formed ``"category": "URGENT"`` that no taxonomy row
   matches; the shape gate cannot see that, because the permitted values are
   configuration, not constants.
4. **Citation** — every ``chunk_key`` resolved against the knowledge base and
   against *what was actually retrieved for this complaint*. A citation to a
   real document the retriever never returned is still ungrounded.

Gates 3 and 4 are why this module reads from the database. Gate 2 alone would
pass output that is well-formed and wrong, and "well-formed and wrong" is the
failure mode the SRS 1.8 traps are built around.

Failures are sorted into **repairable** and **terminal**. A repairable failure
produces a correction instruction naming the exact field and the permitted
values, appended to the original prompt for one bounded retry. A terminal
failure does not — retrying a refusal with the same input wastes free-tier
quota to arrive at the same refusal.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from schemas.genai import ComplaintIntelligence
from src.core.logging import get_logger
from src.db.models import Category, Chunk, Department, EscalationLevel, PriorityLevel, Subcategory
from src.core.refcache import reference_data

log = get_logger("genai_pipeline.validator")

# A fenced block, with or without a language tag.
_FENCED = re.compile(r"```(?:json|JSON)?\s*(.+?)\s*```", re.DOTALL)
# Trailing commas: the single most common thing between a model and valid JSON.
_TRAILING_COMMA = re.compile(r",(\s*[}\]])")

MAX_REPAIR_ATTEMPTS = 1


class ValidationStage:
    EXTRACTION = "extraction"
    SCHEMA = "schema"
    REFERENCE = "reference"
    CITATION = "citation"


@dataclass(slots=True)
class ValidationIssue:
    """One problem, specific enough to write a correction instruction from."""

    stage: str
    field_path: str
    message: str
    received: Any = None
    permitted: list[str] = field(default_factory=list)
    repairable: bool = True

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "stage": self.stage,
            "field": self.field_path,
            "message": self.message,
            "repairable": self.repairable,
        }
        if self.received is not None:
            payload["received"] = self.received
        if self.permitted:
            # Truncated: a correction instruction listing 37 subcategories is
            # longer than the answer we are asking for.
            payload["permitted"] = self.permitted[:25]
        return payload

    def instruction(self) -> str:
        line = f"- `{self.field_path}`: {self.message}"
        if self.received is not None:
            line += f" You returned {self.received!r}."
        if self.permitted:
            shown = ", ".join(self.permitted[:25])
            more = "" if len(self.permitted) <= 25 else f", … ({len(self.permitted)} total)"
            line += f" Permitted values: {shown}{more}."
        return line


@dataclass(slots=True)
class ValidationOutcome:
    """The result of validating one raw provider response."""

    ok: bool
    parsed: dict[str, Any] | None = None
    intelligence: ComplaintIntelligence | None = None
    issues: list[ValidationIssue] = field(default_factory=list)
    unresolved_citations: list[str] = field(default_factory=list)
    ungrounded_citations: list[str] = field(default_factory=list)

    @property
    def repairable(self) -> bool:
        """Worth one more call only if every issue is something a model can fix."""
        return bool(self.issues) and all(issue.repairable for issue in self.issues)

    @property
    def failed_stage(self) -> str | None:
        return self.issues[0].stage if self.issues else None

    def errors_for_storage(self) -> list[dict[str, Any]]:
        """Written to ``genai_runs.schema_errors`` — the retry evidence."""
        return [issue.as_dict() for issue in self.issues]

    def correction_instruction(self) -> str:
        """
        The corrective instruction for the bounded retry (SRS Step 47).

        Names each field and its permitted values rather than saying "your
        output was invalid": a model given the specific constraint corrects it,
        a model told only that something was wrong usually returns a differently
        invalid answer.
        """
        lines = [issue.instruction() for issue in self.issues if issue.repairable]
        return (
            "Your previous response was rejected by automated validation. "
            "Correct exactly these problems and return the complete JSON object "
            "again. Change nothing else.\n\n"
            + "\n".join(lines)
            + "\n\nReturn only the JSON object, with no markdown fence and no commentary."
        )


# ══════════════════════════════════════════════════════════════
# gate 1 — extraction
# ══════════════════════════════════════════════════════════════
def extract_json(text: str) -> tuple[dict[str, Any] | None, str | None]:
    """
    Recover a JSON object from a model response.

    Tolerant on purpose. A fenced block or a trailing comma is a formatting
    slip; spending a second API call on it would be both slower and, on a free
    tier, more expensive than handling it here.
    """
    if not text or not text.strip():
        return None, "response was empty"

    candidate = text.strip()

    fenced = _FENCED.search(candidate)
    if fenced:
        candidate = fenced.group(1).strip()

    try:
        return _as_object(json.loads(candidate))
    except json.JSONDecodeError:
        pass

    # Narrow to the outermost braces: strips "Here is the JSON:" preambles and
    # any trailing commentary.
    start, end = candidate.find("{"), candidate.rfind("}")
    if start == -1 or end <= start:
        return None, "no JSON object found in response"
    candidate = candidate[start : end + 1]

    try:
        return _as_object(json.loads(candidate))
    except json.JSONDecodeError:
        pass

    try:
        return _as_object(json.loads(_TRAILING_COMMA.sub(r"\1", candidate)))
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON: {exc.msg} at position {exc.pos}"


def _as_object(value: Any) -> tuple[dict[str, Any] | None, str | None]:
    if isinstance(value, dict):
        return value, None
    if isinstance(value, list) and len(value) == 1 and isinstance(value[0], dict):
        # Some models wrap a single result in an array.
        return value[0], None
    return None, f"expected a JSON object, received {type(value).__name__}"


# ══════════════════════════════════════════════════════════════
# gate 3 — reference data
# ══════════════════════════════════════════════════════════════
@dataclass(slots=True)
class ReferenceData:
    """The live vocabulary, loaded once per batch rather than per complaint."""

    categories: set[str]
    subcategories: dict[str, set[str]]
    departments: set[str]
    priorities: set[str]
    escalations: set[str]

    @property
    def all_subcategories(self) -> set[str]:
        return {code for group in self.subcategories.values() for code in group}


@reference_data("reference_data")
def load_reference_data(db: Session) -> ReferenceData:
    categories = {c.code for c in db.execute(select(Category)).scalars()}
    subcategories: dict[str, set[str]] = {}
    # One join, not ``sub.category`` per row: that lazy load was a round trip
    # per subcategory, a dozen of them on every complaint.
    for category_code, sub_code in db.execute(
        select(Category.code, Subcategory.code).join(
            Category, Subcategory.category_id == Category.id
        )
    ).all():
        subcategories.setdefault(category_code, set()).add(sub_code)
    return ReferenceData(
        categories=categories,
        subcategories=subcategories,
        departments={d.code for d in db.execute(select(Department)).scalars()},
        priorities={p.code for p in db.execute(select(PriorityLevel)).scalars()},
        escalations={e.code for e in db.execute(select(EscalationLevel)).scalars()},
    )


def _check_references(
    result: ComplaintIntelligence, reference: ReferenceData
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    if result.category not in reference.categories:
        issues.append(
            ValidationIssue(
                stage=ValidationStage.REFERENCE, field_path="category",
                message="not a category defined in the taxonomy.",
                received=result.category, permitted=sorted(reference.categories),
            )
        )
    elif result.subcategory and result.subcategory not in reference.subcategories.get(
        result.category, set()
    ):
        # A subcategory that exists but belongs to a different category is the
        # more interesting failure: it means the two fields disagree.
        permitted = sorted(reference.subcategories.get(result.category, set()))
        elsewhere = result.subcategory in reference.all_subcategories
        issues.append(
            ValidationIssue(
                stage=ValidationStage.REFERENCE, field_path="subcategory",
                message=(
                    f"belongs to a different category, not {result.category}."
                    if elsewhere
                    else "not a subcategory defined in the taxonomy."
                ),
                received=result.subcategory, permitted=permitted,
            )
        )

    for attribute, vocabulary, label in (
        ("department", reference.departments, "department"),
        ("support_department", reference.departments, "department"),
        ("priority", reference.priorities, "priority level"),
    ):
        value = getattr(result, attribute)
        if value and value not in vocabulary:
            issues.append(
                ValidationIssue(
                    stage=ValidationStage.REFERENCE, field_path=attribute,
                    message=f"not a {label} defined in the system.",
                    received=value, permitted=sorted(vocabulary),
                )
            )

    if result.escalation_level and result.escalation_level not in reference.escalations:
        issues.append(
            ValidationIssue(
                stage=ValidationStage.REFERENCE, field_path="escalation_level",
                message="not an escalation level defined in the system.",
                received=result.escalation_level, permitted=sorted(reference.escalations),
            )
        )

    return issues


# ══════════════════════════════════════════════════════════════
# gate 4 — citations
# ══════════════════════════════════════════════════════════════
def _check_citations(
    db: Session,
    result: ComplaintIntelligence,
    retrieved_chunk_keys: set[str] | None,
) -> tuple[list[ValidationIssue], list[str], list[str]]:
    """
    Resolve every cited chunk key.

    Two distinct failures, and conflating them would hide the worse one:

    * **unresolved** — the key matches no chunk anywhere. A fabricated citation.
    * **ungrounded** — the chunk exists but was not retrieved for this
      complaint. The model is citing something it was never shown, which means
      the support is coincidental even when the document is real.

    Neither blocks the pipeline here. Both are recorded, reported by the
    hallucination checks, and surfaced to the reviewer — a citation problem is
    evidence about output quality, which is what the comparison report measures.
    """
    issues: list[ValidationIssue] = []
    unresolved: list[str] = []
    ungrounded: list[str] = []

    keys = [ref.chunk_key for ref in result.policy_refs if ref.chunk_key]
    if not keys:
        return issues, unresolved, ungrounded

    existing = {
        row.chunk_key
        for row in db.execute(select(Chunk).where(Chunk.chunk_key.in_(keys))).scalars()
    }

    for key in keys:
        if key not in existing:
            unresolved.append(key)
        elif retrieved_chunk_keys is not None and key not in retrieved_chunk_keys:
            ungrounded.append(key)

    if unresolved:
        issues.append(
            ValidationIssue(
                stage=ValidationStage.CITATION, field_path="policy_refs[].chunk_key",
                message=(
                    "cites a policy identifier that does not exist. Cite only the "
                    "identifiers shown in the approved policy extracts, or return "
                    "no citation at all."
                ),
                received=unresolved,
                # Repairable: naming the invented key usually gets a corrected
                # citation or an honest empty list on the retry.
                repairable=True,
            )
        )

    if ungrounded:
        log.warning("citation_not_in_retrieved_set", keys=ungrounded)

    return issues, unresolved, ungrounded


# ══════════════════════════════════════════════════════════════
# the validator
# ══════════════════════════════════════════════════════════════
def validate_response(
    db: Session,
    raw_text: str,
    *,
    reference: ReferenceData | None = None,
    retrieved_chunk_keys: set[str] | None = None,
) -> ValidationOutcome:
    """Run all four gates over one raw provider response."""
    parsed, error = extract_json(raw_text)
    if parsed is None:
        return ValidationOutcome(
            ok=False,
            issues=[
                ValidationIssue(
                    stage=ValidationStage.EXTRACTION, field_path="$",
                    message=f"response could not be parsed as JSON ({error}).",
                )
            ],
        )

    try:
        intelligence = ComplaintIntelligence.model_validate(parsed)
    except PydanticValidationError as exc:
        return ValidationOutcome(
            ok=False, parsed=parsed, issues=_from_pydantic(exc)
        )

    reference = reference or load_reference_data(db)
    issues = _check_references(intelligence, reference)

    citation_issues, unresolved, ungrounded = _check_citations(
        db, intelligence, retrieved_chunk_keys
    )
    issues.extend(citation_issues)

    if issues:
        log.warning(
            "genai_output_invalid",
            stages=sorted({i.stage for i in issues}),
            fields=[i.field_path for i in issues],
        )

    return ValidationOutcome(
        ok=not issues,
        parsed=parsed,
        # The object is returned even when reference checks failed: a caller
        # that has exhausted its retries can still salvage the valid fields,
        # and the comparison engine records what the model actually said.
        intelligence=intelligence,
        issues=issues,
        unresolved_citations=unresolved,
        ungrounded_citations=ungrounded,
    )


def _from_pydantic(exc: PydanticValidationError) -> list[ValidationIssue]:
    """Turn Pydantic errors into instructions a model can act on."""
    issues: list[ValidationIssue] = []
    for error in exc.errors():
        path = ".".join(str(part) for part in error["loc"]) or "$"
        kind = error["type"]
        permitted: list[str] = []

        if kind == "literal_error":
            # Pydantic phrases this as "Input should be 'A' or 'B'"; the
            # permitted list is extracted so the instruction is explicit.
            permitted = re.findall(r"'([^']+)'", error.get("msg", ""))
            message = "is not one of the permitted values."
        elif kind == "missing":
            message = "is required and was missing from your response."
        elif kind == "extra_forbidden":
            message = "is not a field in the schema. Remove it."
        elif kind.startswith("string_too"):
            message = f"has an invalid length ({error.get('msg', '')})."
        elif kind.startswith("too_"):
            message = f"has an invalid number of items ({error.get('msg', '')})."
        elif kind == "value_error":
            message = str(error.get("msg", "failed validation")).removeprefix("Value error, ")
        else:
            message = error.get("msg", "failed validation")

        issues.append(
            ValidationIssue(
                stage=ValidationStage.SCHEMA, field_path=path,
                message=message, received=_sample(error.get("input")),
                permitted=permitted,
            )
        )
    return issues


def _sample(value: Any) -> Any:
    """Keep the echo short — a whole rejected object in an error field is noise."""
    if isinstance(value, str):
        return value[:120]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    if isinstance(value, list):
        return f"<list of {len(value)}>"
    if isinstance(value, dict):
        return f"<object with keys {sorted(value)[:6]}>"
    return str(value)[:120]
