"""
Field-level comparison of the two pipelines (SRS Steps 52-56; FR xlvi-l).

One :class:`FieldComparison` per field, each carrying the explanation
Deliverable 8 requires — *"an explanation of the disagreement"*, not merely the
fact of one.

Three things here are deliberate and worth reading before changing:

**Ladder fields compare by rank, not equality.** ``MANAGER`` against
``CRITICAL_MGMT`` is not simply "different": one is *below* the other, and the
direction decides whether this is a safe disagreement or the exact failure
SRS 1.8 #7 tests for. ``direction`` records it.

**Set fields report which values are missing, not that a set differs.**
"GenAI omitted REPLACE_UNIT" is actionable; "the sets differ" is not.

**A field Pipeline 2 does not derive is UNSUPPORTED, never a mismatch.**
Sentiment is the case that matters: Python has no sentiment opinion by design,
and scoring the model's reading against an absence would manufacture a
disagreement out of an architectural choice — and would quietly let emotional
tone back into a decision path that SRS 1.8 #6 requires it to stay out of.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from comparison_engine.fields import (
    FIELD_SPECS,
    REVIEW_WINNER,
    SEVERITY_ALIASES,
    WINNER_ALIASES,
    FieldSpec,
    _as_set,
    _norm,
)
from src.core.logging import get_logger
from src.db.enums import ComparisonStatus, Severity, Winner

log = get_logger("comparison_engine.diff")

# Used when a field has no configured weight. Deliberately non-silent: an
# unweighted field is a configuration gap, and defaulting it to INFORMATIONAL
# would hide a newly added field from every review trigger.
# Every key resolve_weight() can return must be present here: the early-return
# path hands this dict straight to the caller, and a missing key there crashes
# the whole reconciliation for any field absent from the config file.
DEFAULT_WEIGHT = {
    "severity": Severity.MEDIUM,
    "winner": Winner.PYTHON,
    "review": False,
    "configured": False,
}

@dataclass(slots=True)
class FieldComparison:
    """One field, both readings, and why the difference matters."""

    field: str
    genai_value: Any
    python_value: Any
    status: str
    severity: str
    winner: str | None
    final_value: Any
    reason_code: str | None = None
    explanation: str = ""
    direction: str | None = None          # ladder only: GENAI_LOWER / GENAI_HIGHER
    missing_from_genai: list[str] = field(default_factory=list)
    missing_from_python: list[str] = field(default_factory=list)
    needs_review: bool = False

    @property
    def is_mismatch(self) -> bool:
        return self.status == ComparisonStatus.MISMATCH

    @property
    def is_critical_mismatch(self) -> bool:
        return self.is_mismatch and self.severity == Severity.CRITICAL

    @property
    def is_high_mismatch(self) -> bool:
        return self.is_mismatch and self.severity == Severity.HIGH

    @property
    def counts_toward_agreement(self) -> bool:
        """
        Whether this field belongs in the agreement score.

        A field only one pipeline produces is excluded. Including it would
        drag the score down for an architectural decision rather than a
        disagreement, and the resulting number would not mean what FR li says
        it means.
        """
        return self.status in (ComparisonStatus.MATCH, ComparisonStatus.MISMATCH)

    def as_row(self) -> dict[str, Any]:
        """The shape written to ``comparisons``."""
        return {
            "field": self.field,
            "genai_value": _stringify(self.genai_value),
            "python_value": _stringify(self.python_value),
            "final_value": _stringify(self.final_value),
            "status": self.status,
            "severity": self.severity,
            "winner": self.winner,
            "reason_code": self.reason_code,
            "explanation": self.explanation,
        }


# comparisons.genai_value / python_value / final_value are VARCHAR(512).
# A joined action list overruns that easily, and PostgreSQL rejects the insert
# rather than truncating -- so the cap is applied here, once, for every type.
MAX_VALUE_CHARS = 512


def _stringify(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (set, frozenset)):
        text = "; ".join(sorted(str(v) for v in value))
    elif isinstance(value, (list, tuple)):
        text = "; ".join(str(v) for v in value)
    else:
        text = str(value)
    if not text:
        return None
    if len(text) > MAX_VALUE_CHARS:
        # The full list stays available in the decision's reconciled record;
        # this column is the human-readable summary.
        text = text[: MAX_VALUE_CHARS - 3].rstrip() + "..."
    return text


# ══════════════════════════════════════════════════════════════
# weights
# ══════════════════════════════════════════════════════════════
def resolve_weight(name: str, weights: dict[str, Any]) -> dict[str, Any]:
    """
    Look up a field's severity and winner from configuration.

    Unknown severities and winners fall back rather than raising: a typo in a
    runtime-editable config file must not take the pipeline down mid-demo. It
    is logged, and ``configured`` records that the value was not honoured.
    """
    raw = weights.get(name)
    if not isinstance(raw, dict):
        return dict(DEFAULT_WEIGHT)

    severity = SEVERITY_ALIASES.get(str(raw.get("severity", "")).upper())
    winner_key = str(raw.get("winner", "")).strip().lower()
    winner = WINNER_ALIASES.get(winner_key)

    if severity is None or winner is None:
        log.warning(
            "comparison_weight_unrecognised",
            field=name, severity=raw.get("severity"), winner=raw.get("winner"),
        )

    return {
        "severity": severity or DEFAULT_WEIGHT["severity"],
        "winner": winner or DEFAULT_WEIGHT["winner"],
        "review": winner_key == REVIEW_WINNER,
        "configured": severity is not None and winner is not None,
    }


# ══════════════════════════════════════════════════════════════
# comparators
# ══════════════════════════════════════════════════════════════
def _compare_scalar(genai: Any, python: Any) -> tuple[bool, str]:
    left, right = _norm(genai), _norm(python)
    if left == right:
        return True, f"Both pipelines derived {left or 'no value'}."
    return False, f"GenAI derived {left or 'no value'}; rules derived {right or 'no value'}."


def _compare_ladder(
    genai: Any, python: Any, ranks: dict[str, int]
) -> tuple[bool, str, str | None]:
    """
    Compare two rungs of an ordered ladder.

    Returns ``(matched, explanation, direction)``. Direction is the part that
    matters downstream: a GenAI level *below* the rule-derived one is an
    under-escalation, which is the failure mode SRS 1.8 #7 is built around,
    while a level above it is merely over-cautious.
    """
    left, right = _norm(genai), _norm(python)
    if left == right:
        return True, f"Both pipelines derived {left or 'no value'}.", None

    if left is None or right is None:
        return (
            False,
            f"GenAI derived {left or 'no value'}; rules derived {right or 'no value'}.",
            None,
        )

    left_rank, right_rank = ranks.get(left), ranks.get(right)
    if left_rank is None or right_rank is None:
        # An unknown rung: compare as strings rather than guessing an order.
        return False, f"GenAI derived {left}; rules derived {right}.", None

    if left_rank < right_rank:
        return (
            False,
            f"GenAI proposed {left}, which is BELOW the rule-derived {right}. "
            "The rule-derived value stands.",
            "GENAI_LOWER",
        )
    return (
        False,
        f"GenAI proposed {left}, which is ABOVE the rule-derived {right}.",
        "GENAI_HIGHER",
    )


def _compare_set(genai: Any, python: Any) -> tuple[bool, str, list[str], list[str]]:
    """Plain set comparison, kept for any field that really is a code set."""
    left, right = _as_set(genai), _as_set(python)
    if left == right:
        return True, f"Both pipelines listed {len(left)} value(s).", [], []

    missing_from_genai = sorted(right - left)
    missing_from_python = sorted(left - right)

    parts: list[str] = []
    if missing_from_genai:
        parts.append(f"GenAI omitted {', '.join(missing_from_genai)}")
    if missing_from_python:
        parts.append(f"GenAI added {', '.join(missing_from_python)} which no rule requires")
    return False, ". ".join(parts) + ".", missing_from_genai, missing_from_python


# ══════════════════════════════════════════════════════════════
# one field
# ══════════════════════════════════════════════════════════════
def compare_field(
    spec: FieldSpec,
    intelligence: Any,
    outcome: Any,
    *,
    weights: dict[str, Any],
    ranks: dict[str, dict[str, int]],
    thresholds: dict[str, Any] | None = None,
) -> FieldComparison:
    """Compare one field across both pipelines."""
    thresholds = thresholds or {}
    weight = resolve_weight(spec.name, weights)
    severity: str = weight["severity"]
    winner: str = weight["winner"]
    review = bool(weight["review"])

    genai_value = spec.genai_value(intelligence)
    python_value = spec.python_value(outcome)

    genai_present = _has_value(genai_value)
    python_present = _has_value(python_value)

    # ── only one side produced anything ──
    if not genai_present and not python_present:
        return FieldComparison(
            field=spec.name, genai_value=None, python_value=None,
            status=ComparisonStatus.UNSUPPORTED, severity=Severity.INFORMATIONAL,
            winner=None, final_value=None, reason_code="NEITHER_PIPELINE_DERIVED",
            explanation="Neither pipeline produced a value for this field.",
        )

    if not python_present:
        # Expected for sentiment and free-text fields: Pipeline 2 has no
        # opinion by design, so this is not a disagreement.
        return FieldComparison(
            field=spec.name, genai_value=genai_value, python_value=None,
            status=ComparisonStatus.PYTHON_MISSING,
            severity=Severity.INFORMATIONAL, winner=Winner.GENAI,
            final_value=genai_value, reason_code="PYTHON_DOES_NOT_DERIVE",
            explanation=(
                "The rule engine does not derive this field, so the GenAI value "
                "is kept without a comparison."
            ),
        )

    if not genai_present:
        # The rule-derived value stands. Nothing is invented to fill the gap.
        return FieldComparison(
            field=spec.name, genai_value=None, python_value=python_value,
            status=ComparisonStatus.GENAI_MISSING, severity=severity,
            winner=Winner.PYTHON, final_value=python_value,
            reason_code="GENAI_DID_NOT_DERIVE",
            explanation=(
                f"GenAI produced no value; the rule-derived {_stringify(python_value)} "
                "is used."
            ),
            needs_review=severity == Severity.CRITICAL,
        )

    # ── both sides produced something ──
    direction: str | None = None
    missing_from_genai: list[str] = []
    missing_from_python: list[str] = []

    if spec.kind == "ladder":
        matched, explanation, direction = _compare_ladder(
            genai_value, python_value, ranks.get(spec.name, {})
        )
    elif spec.kind == "set":
        matched, explanation, missing_from_genai, missing_from_python = _compare_set(
            genai_value, python_value
        )
    else:
        matched, explanation = _compare_scalar(genai_value, python_value)

    if matched:
        return FieldComparison(
            field=spec.name, genai_value=genai_value, python_value=python_value,
            status=ComparisonStatus.MATCH, severity=Severity.INFORMATIONAL,
            winner=Winner.AGREED, final_value=python_value,
            reason_code="AGREED", explanation=explanation,
        )

    final_value = genai_value if winner == Winner.GENAI else python_value
    reason_code = "GENAI_PYTHON_DISAGREEMENT"
    if direction == "GENAI_LOWER":
        # Named separately because an under-escalation is the interesting one,
        # and the review queue and the report both filter on it.
        reason_code = "GENAI_BELOW_RULE_DERIVED"

    return FieldComparison(
        field=spec.name, genai_value=genai_value, python_value=python_value,
        status=ComparisonStatus.MISMATCH, severity=severity,
        winner=winner, final_value=final_value,
        reason_code=reason_code, explanation=explanation, direction=direction,
        missing_from_genai=missing_from_genai,
        missing_from_python=missing_from_python,
        # A "review" winner means neither side prevails automatically. The
        # rule-derived value is used in the interim because it is the one
        # traceable to approved policy.
        needs_review=review or severity == Severity.CRITICAL,
    )


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return True          # False is a real answer, not an absence
    if isinstance(value, (list, tuple, set, frozenset, dict)):
        return len(value) > 0
    return bool(str(value).strip())


# ══════════════════════════════════════════════════════════════
# every field
# ══════════════════════════════════════════════════════════════
def compare_all(
    intelligence: Any,
    outcome: Any,
    *,
    weights: dict[str, Any],
    ranks: dict[str, dict[str, int]],
    thresholds: dict[str, Any] | None = None,
    specs: tuple[FieldSpec, ...] = FIELD_SPECS,
) -> list[FieldComparison]:
    """
    Compare every field.

    When Pipeline 1 is unavailable, ``intelligence`` is ``None`` and every
    field resolves to GENAI_MISSING with the rule-derived value standing. The
    complaint is still fully decided — that is the NFR 5 degraded path, and it
    produces a complete set of comparison rows rather than none.
    """
    return [
        compare_field(
            spec, intelligence, outcome,
            weights=weights, ranks=ranks, thresholds=thresholds,
        )
        for spec in specs
    ]
