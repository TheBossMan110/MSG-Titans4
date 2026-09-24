"""
What gets compared, and how (FR xlvi-l; SRS Steps 52-56).

    "The system must compare GenAI classification against Python rule
     classification ... routing ... urgency ... escalation status."
                                                      — SRS Steps 52-55

The comparison is field-by-field, and each field declares three things:

* **how to read it** from each pipeline's very different result object;
* **how to compare** two values — ``escalation_level`` is a ladder, not a
  string, and ``required_actions`` is a set, so ``==`` would be wrong for both;
* **its severity and winner**, loaded from ``app_config['comparison_weights']``
  rather than written here, so an evaluator can retune the policy at runtime
  (SRS 1.8 #14).

The comparators matter more than they look. A naive ``genai == python`` would
report ``MANAGER`` vs ``CRITICAL_MGMT`` as a plain mismatch and lose the fact
that one is *below* the other — which is the entire point of SRS 1.8 #7.

**Required and prohibited actions are deliberately NOT compared here.**

An earlier version did compare them, by fuzzy-matching the rule matrix's prose
obligations against the model's prose steps. It produced two false findings on
the very first real complaint, in opposite directions:

* a CRITICAL violation for proposing *"advise the customer to cease using the
  product"* against a prohibition on *"advise the customer to repair or test
  the product"* — near-identical token sets, opposite meanings;
* a compliance score of 18% on a result that had in fact carried out the
  safety procedure, because correct paraphrases scored below the threshold.

No similarity threshold fixes that: the distinguishing feature is negation,
which token overlap cannot see. Fabricated findings are worse than absent ones,
especially CRITICAL ones.

These checks are not lost, and they were never this module's remit. The
comparison engine owns FR xlvi-li — classification, routing, urgency,
escalation, traceability and the verification score. Obligations belong to
FR xxv / SRS Step 28, where Python checks the *generated reply* against the
rule matrix using the configured phrase patterns in
``policy.yaml -> response_guard``. Both action lists are carried into the
reconciled record for exactly that purpose.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from src.db.enums import Severity, Winner

# Severity strings that may appear in configuration, mapped to the enum.
SEVERITY_ALIASES = {
    "CRITICAL": Severity.CRITICAL,
    "HIGH": Severity.HIGH,
    "MEDIUM": Severity.MEDIUM,
    "INFO": Severity.INFORMATIONAL,
    "INFORMATIONAL": Severity.INFORMATIONAL,
}

# Who prevails on a disagreement.
WINNER_ALIASES = {
    "python": Winner.PYTHON,
    "genai": Winner.GENAI,
    # "review" means neither side wins automatically: a human decides. The
    # safe interim value is Python's, because it is the one derived from
    # approved policy.
    "review": Winner.PYTHON,
}

# Fields whose configured winner is "review" also force a human into the loop.
REVIEW_WINNER = "review"


@dataclass(frozen=True, slots=True)
class FieldSpec:
    """One comparable field."""

    name: str
    read_genai: Callable[[Any], Any]
    read_python: Callable[[Any], Any]
    kind: str = "scalar"          # scalar | ladder | set | bool
    describe: str = ""

    def genai_value(self, intelligence: Any) -> Any:
        return None if intelligence is None else self.read_genai(intelligence)

    def python_value(self, outcome: Any) -> Any:
        return None if outcome is None else self.read_python(outcome)


def _norm(value: Any) -> str | None:
    """Codes compare case-insensitively; empty is indistinguishable from absent."""
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    text = str(value).strip()
    return text.upper() if text else None


def _as_set(value: Any) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, str):
        return {value.strip().upper()} if value.strip() else set()
    out: set[str] = set()
    for item in value:
        if isinstance(item, dict):
            item = item.get("action_code") or item.get("code") or item.get("step")
        text = _norm(item)
        if text:
            out.add(text)
    return out


# ══════════════════════════════════════════════════════════════
# the field map
# ══════════════════════════════════════════════════════════════
def genai_steps(intelligence: Any) -> list[str]:
    """
    Everything the model proposed doing, as text.

    Not a comparison field -- see the module docstring. It is carried into the
    reconciled record so the response guard can check the final reply against
    the rule matrix's obligations, which is where SRS Step 28 puts that check.
    """
    steps: list[str] = []
    for step in getattr(intelligence, "resolution_steps", None) or []:
        text = (getattr(step, "step", "") or "").strip()
        if text:
            steps.append(text)
        code = (getattr(step, "action_code", None) or "").strip()
        if code:
            steps.append(code)
    return steps


FIELD_SPECS: tuple[FieldSpec, ...] = (
    FieldSpec(
        "category",
        lambda g: g.category,
        lambda p: p.category_code,
        describe="Complaint category (SRS Step 52).",
    ),
    FieldSpec(
        "subcategory",
        lambda g: g.subcategory,
        lambda p: p.subcategory_code,
        describe="Complaint subcategory.",
    ),
    FieldSpec(
        "department",
        lambda g: g.department,
        lambda p: p.department_code,
        describe="Routing destination (SRS Step 53).",
    ),
    FieldSpec(
        "support_department",
        lambda g: g.support_department,
        lambda p: p.support_department_code,
        describe="Secondary department.",
    ),
    FieldSpec(
        "urgency",
        lambda g: g.urgency,
        lambda p: p.urgency,
        kind="ladder",
        describe="Urgency level (SRS Step 54).",
    ),
    FieldSpec(
        "priority",
        lambda g: g.priority,
        lambda p: p.priority_code,
        kind="ladder",
        describe="Priority level.",
    ),
    FieldSpec(
        "escalation_level",
        # An escalation that was not requested is NONE, not null: "the model
        # did not escalate" and "the model said nothing" are different claims,
        # and only the first can be compared against the floor.
        lambda g: g.escalation_level or ("NONE" if not g.escalation_required else None),
        lambda p: p.escalation_code,
        kind="ladder",
        describe="Escalation level against the mandatory floor (SRS Step 55).",
    ),
    FieldSpec(
        "follow_up_required",
        lambda g: g.follow_up_required,
        lambda p: p.follow_up_required,
        kind="bool",
        describe="Whether a follow-up is owed.",
    ),
    FieldSpec(
        "sentiment",
        lambda g: g.sentiment,
        # Pipeline 2 does not derive sentiment, and must not: emotional
        # intensity is an analytics-only signal, structurally unreachable from
        # rule evaluation (SRS 1.8 #6). The comparison therefore records the
        # model's reading as UNSUPPORTED rather than as a disagreement.
        lambda p: None,
        describe="Customer sentiment — GenAI only, by design.",
    ),
    FieldSpec(
        "primary_issue",
        lambda g: g.primary_issue,
        lambda p: None,
        describe="Free-text issue summary — GenAI only.",
    ),
)

FIELDS_BY_NAME = {spec.name: spec for spec in FIELD_SPECS}
