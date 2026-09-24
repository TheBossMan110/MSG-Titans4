"""
The rule condition DSL.

A rule's ``when`` clause is JSON stored in the database.  This module
interprets it.  It is **interpreted, never ``eval()``-ed** — rules are editable
at runtime by an administrator (SRS 1.8 #14), so a rule body is untrusted input
and must not be executable.

Grammar
-------
Leaves::

    {"signal": "safety_lexicon_hit"}          signal present
    {"signal": "legal_threat", "min_weight": 2.0}
    {"fact": "repeat_count", "gte": 3}        compare a derived fact
    {"field": "category", "eq": "DELIVERY"}   compare a complaint field
    {"always": true}                          unconditional (catch-alls)

Combinators::

    {"all_of": [...]}    every child must hold
    {"any_of": [...]}    at least one child must hold
    {"none_of": [...]}   no child may hold
    {"not": {...}}       negation

Comparison operators: ``eq ne in not_in gt gte lt lte contains not_contains
exists matches``.

Every evaluation returns a :class:`ConditionResult` carrying *why* it matched —
which signals fired and which text spans triggered them.  That trace is what
the explainability panel renders, so "escalated because of rule ESC-0007" can
show the words "burning smell" highlighted in the customer's own text.

Design choice: **an unknown operator or malformed node evaluates to False and
is reported**, never raises.  A typo in a rule saved during a live
demonstration must disable that one rule, not take down complaint processing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from src.core.logging import get_logger

log = get_logger("python_validation.conditions")

COMBINATORS = {"all_of", "any_of", "none_of", "not"}
COMPARATORS = {
    "eq", "ne", "in", "not_in", "gt", "gte", "lt", "lte",
    "contains", "not_contains", "exists", "matches",
}
MAX_DEPTH = 12  # a malformed self-referential rule must not recurse forever


@dataclass(slots=True)
class ConditionResult:
    """Outcome of evaluating a condition tree, with its evidence."""

    matched: bool
    matched_signals: list[str] = field(default_factory=list)
    matched_spans: list[dict[str, Any]] = field(default_factory=list)
    matched_facts: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.matched

    def merge(self, other: ConditionResult) -> None:
        """Absorb a child's evidence. Errors propagate even when it matched."""
        for signal in other.matched_signals:
            if signal not in self.matched_signals:
                self.matched_signals.append(signal)
        self.matched_spans.extend(other.matched_spans)
        self.matched_facts.update(other.matched_facts)
        self.errors.extend(other.errors)


class EvaluationContext:
    """
    Everything a condition may inspect.

    ``signals`` is deliberately the *rule-visible* set, so analytics-only
    signals are structurally unreachable from a rule (SRS 1.8 #6).
    """

    __slots__ = ("signals", "facts", "fields", "spans_by_signal", "weights")

    def __init__(
        self,
        *,
        signals: set[str],
        facts: dict[str, Any],
        fields: dict[str, Any],
        spans_by_signal: dict[str, list[dict[str, Any]]] | None = None,
        weights: dict[str, float] | None = None,
    ) -> None:
        self.signals = signals
        self.facts = facts
        self.fields = fields
        self.spans_by_signal = spans_by_signal or {}
        self.weights = weights or {}

    @classmethod
    def from_signal_set(cls, signal_set, fields: dict[str, Any] | None = None):
        """Build a context from a :class:`~python_validation.signals.SignalSet`."""
        visible = signal_set.for_rules()
        return cls(
            signals=visible,
            facts=dict(signal_set.facts),
            fields=dict(fields or {}),
            spans_by_signal={key: signal_set.spans(key) for key in visible},
            weights={key: signal_set.weight(key) for key in visible},
        )


# ══════════════════════════════════════════════════════════════
# comparison
# ══════════════════════════════════════════════════════════════
def _coerce_pair(left: Any, right: Any) -> tuple[Any, Any]:
    """
    Make two values comparable without lying about their meaning.

    Numeric strings are compared numerically; everything else falls back to
    case-insensitive string comparison.  A None on either side is left alone so
    ordering comparisons against it fail closed rather than raising.
    """
    if left is None or right is None:
        return left, right
    if isinstance(left, bool) or isinstance(right, bool):
        return bool(left), bool(right)
    if isinstance(left, Decimal):
        left = float(left)
    if isinstance(right, Decimal):
        right = float(right)
    if isinstance(left, int | float) and isinstance(right, int | float):
        return float(left), float(right)
    if isinstance(left, int | float) or isinstance(right, int | float):
        try:
            return float(left), float(right)
        except (TypeError, ValueError):
            return str(left).casefold(), str(right).casefold()
    return str(left).casefold(), str(right).casefold()


def _compare(operator: str, actual: Any, expected: Any) -> bool:
    """Apply one comparison operator. Returns False on anything nonsensical."""
    try:
        if operator == "exists":
            present = actual is not None and actual != "" and actual != []
            return present is bool(expected)

        if operator in {"in", "not_in"}:
            options = expected if isinstance(expected, list | tuple | set) else [expected]
            normalised = {_coerce_pair(actual, option)[1] for option in options}
            left = _coerce_pair(actual, next(iter(options), None))[0]
            found = left in normalised
            return found if operator == "in" else not found

        if operator in {"contains", "not_contains"}:
            haystack = actual if isinstance(actual, list | tuple | set) else str(actual or "")
            if isinstance(haystack, str):
                found = str(expected).casefold() in haystack.casefold()
            else:
                found = any(
                    str(item).casefold() == str(expected).casefold() for item in haystack
                )
            return found if operator == "contains" else not found

        if operator == "matches":
            try:
                return re.search(str(expected), str(actual or ""), re.IGNORECASE) is not None
            except re.error:
                return False

        left, right = _coerce_pair(actual, expected)

        if operator == "eq":
            return left == right
        if operator == "ne":
            return left != right

        # Ordering against a missing value is always False - fail closed.
        if left is None or right is None:
            return False
        if operator == "gt":
            return left > right
        if operator == "gte":
            return left >= right
        if operator == "lt":
            return left < right
        if operator == "lte":
            return left <= right
    except (TypeError, ValueError):
        return False

    return False


# ══════════════════════════════════════════════════════════════
# leaves
# ══════════════════════════════════════════════════════════════
def _eval_signal(node: dict[str, Any], ctx: EvaluationContext) -> ConditionResult:
    key = str(node["signal"])
    present = key in ctx.signals

    if present and "min_weight" in node:
        try:
            present = ctx.weights.get(key, 0.0) >= float(node["min_weight"])
        except (TypeError, ValueError):
            return ConditionResult(False, errors=[f"signal {key}: bad min_weight"])

    if not present:
        return ConditionResult(False)

    return ConditionResult(
        matched=True,
        matched_signals=[key],
        matched_spans=list(ctx.spans_by_signal.get(key, [])),
    )


def _eval_comparison(
    node: dict[str, Any], ctx: EvaluationContext, *, source: str, name: str
) -> ConditionResult:
    lookup = ctx.facts if source == "fact" else ctx.fields
    actual = lookup.get(name)

    operators = [key for key in node if key in COMPARATORS]

    # Computed before any early return: a typo'd operator such as {"gte_": 3}
    # would otherwise leave `operators` empty and be silently reinterpreted as
    # the bare truthy shorthand - quietly inverting what the rule author meant.
    unknown = [
        key for key in node
        if key not in COMPARATORS and key not in {"signal", "fact", "field", "always"}
    ]
    errors = [f"{source} '{name}': unknown operator '{key}'" for key in unknown]

    if not operators:
        if unknown:
            # Ambiguous intent. Fail closed and say why.
            return ConditionResult(False, errors=errors)
        # Bare {"fact": "x"} means "is truthy" - a useful shorthand.
        matched = bool(actual)
        return ConditionResult(matched, matched_facts={name: actual} if matched else {})

    matched = all(_compare(op, actual, node[op]) for op in operators)
    return ConditionResult(
        matched=matched,
        matched_facts={name: actual} if matched else {},
        errors=errors,
    )


# ══════════════════════════════════════════════════════════════
# tree walk
# ══════════════════════════════════════════════════════════════
def evaluate(
    node: Any, ctx: EvaluationContext, *, _depth: int = 0
) -> ConditionResult:
    """
    Evaluate a condition tree against a context.

    Never raises.  A malformed node yields ``matched=False`` plus an entry in
    ``errors``, which the engine records on the rule hit so a broken rule is
    visible rather than silently inert.
    """
    if _depth > MAX_DEPTH:
        return ConditionResult(False, errors=["condition nested too deeply"])

    if node is None:
        return ConditionResult(False, errors=["empty condition"])

    if isinstance(node, bool):
        return ConditionResult(node)

    if isinstance(node, list):
        # A bare list is treated as all_of - the common authoring shorthand.
        return _eval_all_of(node, ctx, _depth=_depth)

    if not isinstance(node, dict):
        return ConditionResult(False, errors=[f"unsupported condition node: {type(node).__name__}"])

    if "always" in node:
        return ConditionResult(bool(node["always"]))

    if "all_of" in node:
        return _eval_all_of(node["all_of"], ctx, _depth=_depth)

    if "any_of" in node:
        return _eval_any_of(node["any_of"], ctx, _depth=_depth)

    if "none_of" in node:
        inner = _eval_any_of(node["none_of"], ctx, _depth=_depth)
        # Evidence from a negated branch is not evidence FOR the rule.
        return ConditionResult(not inner.matched, errors=inner.errors)

    if "not" in node:
        inner = evaluate(node["not"], ctx, _depth=_depth + 1)
        return ConditionResult(not inner.matched, errors=inner.errors)

    if "signal" in node:
        return _eval_signal(node, ctx)

    if "fact" in node:
        return _eval_comparison(node, ctx, source="fact", name=str(node["fact"]))

    if "field" in node:
        return _eval_comparison(node, ctx, source="field", name=str(node["field"]))

    return ConditionResult(False, errors=[f"unrecognised condition keys: {sorted(node)}"])


def _eval_all_of(children: Any, ctx: EvaluationContext, *, _depth: int) -> ConditionResult:
    if not isinstance(children, list) or not children:
        return ConditionResult(False, errors=["all_of requires a non-empty list"])

    result = ConditionResult(matched=True)
    for child in children:
        child_result = evaluate(child, ctx, _depth=_depth + 1)
        if not child_result.matched:
            # Short-circuit, but keep the errors so a broken child is visible.
            return ConditionResult(False, errors=[*result.errors, *child_result.errors])
        result.merge(child_result)
    return result


def _eval_any_of(children: Any, ctx: EvaluationContext, *, _depth: int) -> ConditionResult:
    if not isinstance(children, list) or not children:
        return ConditionResult(False, errors=["any_of requires a non-empty list"])

    result = ConditionResult(matched=False)
    for child in children:
        child_result = evaluate(child, ctx, _depth=_depth + 1)
        result.errors.extend(child_result.errors)
        if child_result.matched:
            result.matched = True
            result.merge(child_result)
    return result


# ══════════════════════════════════════════════════════════════
# authoring-time validation
# ══════════════════════════════════════════════════════════════
def validate_condition(node: Any, *, _depth: int = 0) -> list[str]:
    """
    Static check of a condition tree, used when a rule is saved.

    Returning problems at save time rather than at evaluation time is what
    keeps the Live Modification Challenge safe: an administrator editing a rule
    on stage gets told immediately, instead of the rule quietly never firing.
    """
    problems: list[str] = []

    if _depth > MAX_DEPTH:
        return ["condition nested too deeply"]
    if isinstance(node, bool):
        return problems
    if isinstance(node, list):
        for child in node:
            problems.extend(validate_condition(child, _depth=_depth + 1))
        return problems
    if not isinstance(node, dict):
        return [f"unsupported node type: {type(node).__name__}"]
    if not node:
        return ["empty condition object"]

    for combinator in ("all_of", "any_of", "none_of"):
        if combinator in node:
            children = node[combinator]
            if not isinstance(children, list) or not children:
                problems.append(f"{combinator} requires a non-empty list")
            else:
                for child in children:
                    problems.extend(validate_condition(child, _depth=_depth + 1))
            return problems

    if "not" in node:
        return validate_condition(node["not"], _depth=_depth + 1)

    if "always" in node:
        return problems

    if "signal" in node:
        if not isinstance(node["signal"], str) or not node["signal"].strip():
            problems.append("signal must be a non-empty string")
        return problems

    if "fact" in node or "field" in node:
        source = "fact" if "fact" in node else "field"
        if not isinstance(node[source], str) or not node[source].strip():
            problems.append(f"{source} must be a non-empty string")
        unknown = [
            key for key in node
            if key not in COMPARATORS and key not in {"signal", "fact", "field"}
        ]
        problems.extend(f"unknown operator '{key}'" for key in unknown)
        return problems

    return [f"unrecognised condition keys: {sorted(node)}"]


def referenced_signals(node: Any, found: set[str] | None = None) -> set[str]:
    """
    Every signal name a condition tree mentions.

    Used by the rule loader to reject a rule that depends on a signal nobody
    defines, and by the test that proves no rule touches an analytics-only
    signal.
    """
    found = found if found is not None else set()

    if isinstance(node, dict):
        if "signal" in node and isinstance(node["signal"], str):
            found.add(node["signal"])
        for key, value in node.items():
            if key in COMBINATORS:
                referenced_signals(value, found)
    elif isinstance(node, list):
        for child in node:
            referenced_signals(child, found)

    return found
