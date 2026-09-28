"""
The rule engine — Pipeline 2's reasoning.

Given a complaint's signals and the Complaint Resolution Rule Matrix, this
module derives what the outcome *should* be: category, department, urgency,
priority, escalation, required and prohibited actions, policy references.

It reaches that conclusion from the complaint alone.  The GenAI result is not
an input and is not importable from here.  That independence is the whole
point of the dual-pipeline architecture (SRS 1.2), and it is what makes the
comparison downstream meaningful rather than circular.

Merge semantics
---------------
Rules do not simply overwrite one another.  Different fields merge differently
because they mean different things:

* **Scalar fields** (category, department, urgency, priority) — the
  highest-precedence rule that specifies the field wins.
* **Action lists** (required, prohibited) — *unioned* across every matching
  rule.  A safety rule forbidding a compensation promise must not be cancelled
  by a higher-precedence routing rule that happens to be silent on the subject.
* **Escalation** — the highest-precedence proposal is taken, then raised to the
  **mandatory floor** if any mandatory-escalation rule fired.  The floor can
  only ever raise (SRS 1.8 #7).
* **Conflicts** — two rules at the *same* precedence disagreeing on a scalar
  field is recorded as a conflict.  Severity fields resolve to the more severe
  value and the complaint is routed for review; it is never resolved silently.

Two outcomes are deliberately *not* defaults:

* nothing matched -> ``unmatched=True`` -> manual review. A complaint the rules
  do not cover must not be quietly assigned a plausible department.
* a rule with a malformed condition -> recorded with its errors, not skipped in
  silence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from python_validation.conditions import (
    ConditionResult,
    EvaluationContext,
    evaluate,
)
from python_validation.signals import SignalSet
from src.core.logging import get_logger

log = get_logger("python_validation.rule_engine")

# Scalar outcome fields, and whether a same-precedence disagreement should
# resolve to the more severe value rather than being left ambiguous.
SCALAR_FIELDS: dict[str, bool] = {
    "category_code": False,
    "subcategory_code": False,
    "department_code": False,
    "support_department_code": False,
    "urgency": True,
    "priority_code": True,
    "escalation_code": True,
}

URGENCY_RANK = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}

# The fields that say what a complaint is ABOUT, as opposed to how severe it is.
CLASSIFICATION_FIELDS = frozenset({"category_code", "subcategory_code", "department_code", "support_department_code"})

# RULE-005, RES-005, ESC-005 and ELG-005-REFU are one authored case. Cross-cutting
# rules (ESC-SAF-0001, LEG-0001, ...) belong to no case.
_CASE_REF = re.compile(r"^(?:RULE|RES|ESC|ELG)-(\d{3})(?:$|-)")


@dataclass(slots=True)
class LoadedRule:
    """
    A rule flattened into plain data.

    The engine never touches the ORM, so it can be exercised in a unit test
    with a handful of literals and no database at all.
    """

    rule_ref: str
    name: str
    rule_type: str
    conditions: dict[str, Any]
    precedence: int = 50
    is_mandatory_escalation: bool = False
    # A catch-all exists to give an unrecognised complaint somewhere to go.
    # It must NOT suppress the unmatched flag - see evaluate_rules().
    is_catch_all: bool = False
    rationale: str = ""
    rule_id: Any = None

    # scope: only evaluate when the complaint is already in this category
    scope_category_code: str | None = None
    scope_subcategory_code: str | None = None

    # outcomes
    category_code: str | None = None
    subcategory_code: str | None = None
    department_code: str | None = None
    support_department_code: str | None = None
    urgency: str | None = None
    priority_code: str | None = None
    escalation_code: str | None = None
    required_actions: list[str] = field(default_factory=list)
    prohibited_actions: list[str] = field(default_factory=list)
    policy_refs: list[dict[str, Any]] = field(default_factory=list)
    follow_up_required: bool = False
    # Eligibility finding this rule asserts (SRS Steps 29-31), if any.
    eligibility: dict[str, Any] | None = None

    def outcome_field(self, name: str) -> Any:
        return getattr(self, name, None)


@dataclass(slots=True)
class RuleHitRecord:
    """One rule that matched, and the evidence that made it match."""

    rule_ref: str
    rule_id: Any
    precedence: int
    is_mandatory_escalation: bool
    rationale: str
    matched_signals: list[str] = field(default_factory=list)
    matched_spans: list[dict[str, Any]] = field(default_factory=list)
    matched_facts: dict[str, Any] = field(default_factory=dict)
    applied: bool = True
    errors: list[str] = field(default_factory=list)

    @property
    def reason_code(self) -> str:
        """``ESC-0007:safety_lexicon_hit`` — rule plus why it fired."""
        if self.matched_signals:
            return f"{self.rule_ref}:{'+'.join(sorted(self.matched_signals))}"
        if self.matched_facts:
            return f"{self.rule_ref}:{'+'.join(sorted(self.matched_facts))}"
        return f"{self.rule_ref}:matched"


@dataclass(slots=True)
class FieldConflict:
    """Two equally-authoritative rules disagreeing on one field."""

    field_name: str
    values: list[str]
    rule_refs: list[str]
    precedence: int
    resolved_to: str | None = None


@dataclass(slots=True)
class DerivedOutcome:
    """What Pipeline 2 concluded, with everything needed to explain it."""

    category_code: str | None = None
    subcategory_code: str | None = None
    department_code: str | None = None
    support_department_code: str | None = None
    urgency: str | None = None
    priority_code: str | None = None
    escalation_code: str | None = None
    escalation_floor_code: str | None = None

    required_actions: list[str] = field(default_factory=list)
    prohibited_actions: list[str] = field(default_factory=list)
    policy_refs: list[dict[str, Any]] = field(default_factory=list)
    follow_up_required: bool = False

    hits: list[RuleHitRecord] = field(default_factory=list)
    conflicts: list[FieldConflict] = field(default_factory=list)
    reason_codes: list[str] = field(default_factory=list)
    unmatched: bool = False
    ruleset_version: str = "unversioned"

    @property
    def conflict_detected(self) -> bool:
        return bool(self.conflicts)

    @property
    def applied_hits(self) -> list[RuleHitRecord]:
        return [hit for hit in self.hits if hit.applied]

    @property
    def mandatory_escalation_refs(self) -> list[str]:
        return [h.rule_ref for h in self.hits if h.is_mandatory_escalation and h.applied]

    @property
    def rule_errors(self) -> list[str]:
        return [error for hit in self.hits for error in hit.errors]

    def explain(self) -> list[dict[str, Any]]:
        """Human-readable trace for the explainability panel."""
        return [
            {
                "rule_ref": hit.rule_ref,
                "precedence": hit.precedence,
                "mandatory_escalation": hit.is_mandatory_escalation,
                "rationale": hit.rationale,
                "signals": hit.matched_signals,
                "spans": hit.matched_spans,
                "applied": hit.applied,
            }
            for hit in self.hits
        ]


# ══════════════════════════════════════════════════════════════
# scope
# ══════════════════════════════════════════════════════════════
def _in_scope(rule: LoadedRule, fields: dict[str, Any]) -> bool:
    """
    A scoped rule only applies inside its category.

    Scope is checked before the condition so a Billing rule never fires on a
    Delivery complaint merely because a shared signal happened to be present.

    A scoped rule whose category is not yet known does NOT fire. That matters
    on the engine's first pass, where no category has been established: the
    permissive reading ("unknown category, so allow it") let every scoped rule
    run unscoped and contributed obligations from unrelated departments.
    """
    if rule.scope_category_code:
        current = fields.get("category")
        if not current or str(current).upper() != rule.scope_category_code.upper():
            return False
    if rule.scope_subcategory_code:
        current = fields.get("subcategory")
        if not current or str(current).upper() != rule.scope_subcategory_code.upper():
            return False
    return True


# ══════════════════════════════════════════════════════════════
# merging
# ══════════════════════════════════════════════════════════════
def _severity_rank(field_name: str, value: str, escalation_ranks: dict[str, int],
                   priority_ranks: dict[str, int]) -> int:
    """
    Higher = more severe, for every severity-bearing field.

    Priority ranks arrive with 0 as *most* severe (P0), so they are inverted
    here to keep one consistent direction across all three fields.
    """
    if field_name == "urgency":
        return URGENCY_RANK.get(str(value).upper(), -1)
    if field_name == "escalation_code":
        return escalation_ranks.get(str(value).upper(), -1)
    if field_name == "priority_code":
        rank = priority_ranks.get(str(value).upper())
        return -rank if rank is not None else -99
    return 0


def _resolve_scalar(
    field_name: str,
    candidates: list[tuple[LoadedRule, RuleHitRecord]],
    *,
    escalation_ranks: dict[str, int],
    priority_ranks: dict[str, int],
    conflicts: list[FieldConflict],
) -> str | None:
    """
    Pick one value for a scalar field from the rules that specified it.

    Candidates arrive sorted by precedence descending.  Only the top
    precedence band competes; anything below it is already overruled.
    """
    proposals = [
        (rule, hit, rule.outcome_field(field_name))
        for rule, hit in candidates
        if rule.outcome_field(field_name)
    ]
    if not proposals:
        return None

    top_precedence = proposals[0][0].precedence
    band = [p for p in proposals if p[0].precedence == top_precedence]
    distinct = {str(value).upper() for _, _, value in band}

    if len(distinct) == 1:
        return band[0][2]

    # Same authority, different answers.
    prefer_severe = SCALAR_FIELDS.get(field_name, False)
    if prefer_severe:
        chosen = max(
            band,
            key=lambda item: _severity_rank(
                field_name, item[2], escalation_ranks, priority_ranks
            ),
        )[2]
    else:
        # No principled tie-break exists for a non-severity field, so pick
        # deterministically and let the review queue decide.
        chosen = sorted(band, key=lambda item: item[0].rule_ref)[0][2]

    conflicts.append(
        FieldConflict(
            field_name=field_name,
            values=sorted(distinct),
            rule_refs=sorted(rule.rule_ref for rule, _, _ in band),
            precedence=top_precedence,
            resolved_to=chosen,
        )
    )
    log.warning(
        "rule_conflict",
        field=field_name,
        values=sorted(distinct),
        rules=sorted(rule.rule_ref for rule, _, _ in band),
        resolved_to=chosen,
    )
    return chosen


def _union_actions(candidates: list[tuple[LoadedRule, RuleHitRecord]], attribute: str) -> list[str]:
    """
    Union action lists across every matching rule, preserving first-seen order.

    Deliberately not "highest precedence wins": a prohibition issued by any
    matching rule must survive. A routing rule that outranks a safety rule on
    department must not thereby delete the safety rule's prohibitions.
    """
    seen: list[str] = []
    for rule, _ in candidates:
        for action in getattr(rule, attribute, []) or []:
            token = str(action).strip()
            if token and token not in seen:
                seen.append(token)
    return seen


def _union_policy_refs(candidates: list[tuple[LoadedRule, RuleHitRecord]]) -> list[dict[str, Any]]:
    seen: list[dict[str, Any]] = []
    keys: set[tuple[str, str]] = set()
    for rule, _ in candidates:
        for ref in rule.policy_refs or []:
            if not isinstance(ref, dict):
                continue
            key = (str(ref.get("doc_ref", "")), str(ref.get("section_ref", "")))
            if key in keys or not key[0]:
                continue
            keys.add(key)
            seen.append(dict(ref))
    return seen


# ══════════════════════════════════════════════════════════════
# the engine
# ══════════════════════════════════════════════════════════════
def _case_of(rule_ref: str) -> str | None:
    match = _CASE_REF.match(rule_ref or "")
    return match.group(1) if match else None


def _family(rule: LoadedRule) -> str:
    """The unit that wins or loses classification: an authored case, or a stand-alone rule."""
    case = _case_of(rule.rule_ref)
    return f"case:{case}" if case else f"rule:{rule.rule_ref}"


def _evidence(pairs: list[tuple[LoadedRule, RuleHitRecord]]) -> tuple[int, float]:
    """How much of the complaint speaks to these rules: distinct terms matched, then their weight."""
    terms: dict[tuple[str, str], float] = {}
    for _, hit in pairs:
        for span in hit.matched_spans:
            key = (str(span.get("signal")), str(span.get("term") or span.get("text") or "").lower())
            try:
                weight = float(span.get("weight") or 1.0)
            except (TypeError, ValueError):
                weight = 1.0
            terms[key] = max(terms.get(key, 0.0), weight)
    return len(terms), round(sum(terms.values()), 4)


def _secondary_cases(
    contributing: list[tuple[LoadedRule, RuleHitRecord]],
    conflicts: list[FieldConflict],
) -> set[str]:
    """
    The authored cases that lost the question "what is this complaint about?".

    Precedence is right for choosing between cases of ONE subcategory: the
    fake-attempt case outranks the routine missed-attempt case because it is
    the more specific finding. Across subcategories it only says which case
    would be more serious, not which one the customer is describing, so a
    passing mention of a severe topic used to take the classification away
    from the complaint's actual subject. Across subcategories the one with the
    most evidence in the text wins; precedence breaks a tie, and a genuine tie
    is recorded as a conflict so a person looks at it.

    Only the classification fields follow the winner. Urgency, priority and
    escalation are still resolved over every rule that fired, so a secondary
    issue can raise severity -- a mandatory floor is never lost this way.
    """
    groups: dict[str, list[tuple[LoadedRule, RuleHitRecord]]] = {}
    for pair in contributing:
        rule = pair[0]
        subcategory = rule.outcome_field("subcategory_code")
        if rule.rule_type == "CLASSIFICATION" and subcategory:
            groups.setdefault(str(subcategory).upper(), []).append(pair)
    if len(groups) < 2:
        return set()

    ranked = sorted(
        groups.items(),
        key=lambda item: (_evidence(item[1]), max(r.precedence for r, _ in item[1]), item[0]),
        reverse=True,
    )
    (winner, winning), (_, runner_up) = ranked[0], ranked[1]
    if _evidence(winning) == _evidence(runner_up):
        conflicts.append(
            FieldConflict(
                field_name="subcategory_code",
                values=sorted(groups),
                rule_refs=sorted(rule.rule_ref for pairs in groups.values() for rule, _ in pairs),
                precedence=max(r.precedence for r, _ in winning),
                resolved_to=winner,
            )
        )
    return {_family(rule) for _, pairs in ranked[1:] for rule, _ in pairs}


def evaluate_rules(
    rules: list[LoadedRule],
    signals: SignalSet,
    *,
    fields: dict[str, Any] | None = None,
    escalation_ranks: dict[str, int] | None = None,
    priority_ranks: dict[str, int] | None = None,
    ruleset_version: str = "unversioned",
) -> DerivedOutcome:
    """
    Run the rule matrix against one complaint's signals.

    ``fields`` carries complaint attributes a rule may test (channel, product,
    customer tier, and the working category when rules are run in a second
    pass after classification).
    """
    escalation_ranks = {k.upper(): v for k, v in (escalation_ranks or {}).items()}
    priority_ranks = {k.upper(): v for k, v in (priority_ranks or {}).items()}
    fields = fields or {}

    context = EvaluationContext.from_signal_set(signals, fields)
    outcome = DerivedOutcome(ruleset_version=ruleset_version)

    matched: list[tuple[LoadedRule, RuleHitRecord]] = []

    for rule in rules:
        if not _in_scope(rule, fields):
            continue

        result: ConditionResult = evaluate(rule.conditions, context)

        if not result.matched:
            # A rule that did not match is normally uninteresting, but one that
            # failed to *evaluate* is recorded so an authoring mistake is
            # visible rather than silently inert.
            if result.errors:
                outcome.hits.append(
                    RuleHitRecord(
                        rule_ref=rule.rule_ref,
                        rule_id=rule.rule_id,
                        precedence=rule.precedence,
                        is_mandatory_escalation=rule.is_mandatory_escalation,
                        rationale=rule.rationale,
                        applied=False,
                        errors=result.errors,
                    )
                )
            continue

        # Errors ride along on the applied hit; one rule never produces two
        # hit records.
        hit = RuleHitRecord(
            rule_ref=rule.rule_ref,
            rule_id=rule.rule_id,
            precedence=rule.precedence,
            is_mandatory_escalation=rule.is_mandatory_escalation,
            rationale=rule.rationale,
            matched_signals=result.matched_signals,
            matched_spans=result.matched_spans,
            matched_facts=result.matched_facts,
            applied=True,
            errors=result.errors,
        )
        matched.append((rule, hit))

    if not matched:
        outcome.unmatched = True
        log.info("no_rule_matched", signals=sorted(signals.for_rules()))
        return outcome

    # A catch-all gives an unrecognised complaint a queue to land in, but it
    # is not recognition. If nothing *substantive* matched, the complaint is
    # still unclassified and must reach a human - otherwise the catch-all
    # would quietly convert 'we do not know' into a confident-looking answer.
    if all(rule.is_catch_all for rule, _ in matched):
        outcome.unmatched = True
        log.info(
            "only_catch_all_matched",
            rules=[rule.rule_ref for rule, _ in matched],
            signals=sorted(signals.for_rules()),
        )

    # Highest precedence first; rule_ref breaks ties so the result is stable.
    matched.sort(key=lambda pair: (-pair[0].precedence, pair[0].rule_ref))
    outcome.hits.extend(hit for _, hit in matched)

    # A catch-all describes what to do with a complaint nobody recognised. Once
    # a substantive rule HAS recognised it, the catch-all's obligations are
    # noise - "manual classification required" has no business appearing on a
    # complaint eight rules just classified. The hit is still recorded, so the
    # trace stays complete; only its outcome is withdrawn.
    #
    # One exception: a substantive rule can fire without saying what the
    # complaint is about (a cross-cutting safety floor, a legal-threat rule).
    # Then a category-level fallback still names the category, and the
    # complaint is still marked unmatched below, so a person confirms it.
    substantive = [pair for pair in matched if not pair[0].is_catch_all]
    if substantive:
        classified = any(rule.outcome_field("category_code") for rule, _ in substantive)
        contributing = []
        for pair in matched:
            rule, hit = pair
            if not rule.is_catch_all or (not classified and rule.outcome_field("category_code")):
                contributing.append(pair)
            else:
                hit.applied = False
    else:
        contributing = matched

    secondary = _secondary_cases(contributing, outcome.conflicts)
    primary_only = [pair for pair in contributing if _family(pair[0]) not in secondary]

    for field_name in SCALAR_FIELDS:
        setattr(
            outcome,
            field_name,
            _resolve_scalar(
                field_name, primary_only if field_name in CLASSIFICATION_FIELDS else contributing,
                escalation_ranks=escalation_ranks,
                priority_ranks=priority_ranks,
                conflicts=outcome.conflicts,
            ),
        )

    outcome.required_actions = _union_actions(contributing, "required_actions")
    outcome.prohibited_actions = _union_actions(contributing, "prohibited_actions")
    outcome.policy_refs = _union_policy_refs(contributing)
    outcome.follow_up_required = any(rule.follow_up_required for rule, _ in contributing)
    outcome.reason_codes = [hit.reason_code for _, hit in contributing]

    # Recognition means knowing what the complaint is ABOUT. Universal
    # obligations ("acknowledge the complaint") and gap-fillers ("no order
    # reference supplied") match almost everything and identify nothing, so
    # counting them as recognition would mean `unmatched` never fires.
    #
    # No category derived -> we do not know what this is -> a human decides.
    if outcome.category_code is None:
        outcome.unmatched = True
        log.info(
            "unclassified_complaint",
            rules=[rule.rule_ref for rule, _ in contributing],
            signals=sorted(signals.for_rules()),
        )
    elif all(rule.is_catch_all for rule, _ in primary_only if rule.outcome_field("category_code")):
        # Recognised at category level only ("where is my parcel"): the
        # category's routine case is the best answer the rules can give, and
        # a person still confirms it.
        outcome.unmatched = True

    _apply_escalation_floor(outcome, contributing, escalation_ranks)

    log.info(
        "rules_evaluated",
        matched=len(matched),
        department=outcome.department_code,
        urgency=outcome.urgency,
        escalation=outcome.escalation_code,
        floor=outcome.escalation_floor_code,
        conflicts=len(outcome.conflicts),
    )
    return outcome


def _apply_escalation_floor(
    outcome: DerivedOutcome,
    matched: list[tuple[LoadedRule, RuleHitRecord]],
    escalation_ranks: dict[str, int],
) -> None:
    """
    Compute the mandatory escalation floor and raise the outcome to meet it.

    SRS 1.8 #7: "A complaint may contain an escalation condition that is easily
    overlooked by GenAI. The Python pipeline must independently enforce the
    escalation rule."

    The floor is the *highest* level demanded by any mandatory rule that fired.
    Everything downstream — reconciliation, the reviewer UI, the response
    guard — may raise the final escalation but never lower it below this.
    """
    mandatory = [
        rule for rule, _ in matched
        if rule.is_mandatory_escalation and rule.escalation_code
    ]
    if not mandatory:
        return

    floor_rule = max(
        mandatory,
        key=lambda rule: escalation_ranks.get(str(rule.escalation_code).upper(), 0),
    )
    floor_code = floor_rule.escalation_code
    outcome.escalation_floor_code = floor_code

    floor_rank = escalation_ranks.get(str(floor_code).upper(), 0)
    current_rank = escalation_ranks.get(str(outcome.escalation_code or "").upper(), -1)

    if current_rank < floor_rank:
        outcome.escalation_code = floor_code
        reason = f"{floor_rule.rule_ref}:MANDATORY_ESCALATION_FLOOR"
        if reason not in outcome.reason_codes:
            outcome.reason_codes.append(reason)
        log.info(
            "escalation_floor_applied",
            rule=floor_rule.rule_ref,
            raised_to=floor_code,
        )


def rule_from_model(rule) -> LoadedRule:
    """
    Flatten a ``Rule`` ORM row into the engine's plain-data shape.

    Codes are used throughout rather than foreign keys, so an outcome can be
    reasoned about, logged and compared without a database session.
    """
    def code_of(relationship) -> str | None:
        return getattr(relationship, "code", None) if relationship else None

    return LoadedRule(
        rule_id=rule.id,
        rule_ref=rule.rule_ref,
        name=rule.name,
        rule_type=rule.rule_type,
        conditions=rule.conditions or {},
        precedence=rule.precedence,
        is_mandatory_escalation=bool(rule.is_mandatory_escalation),
        is_catch_all=bool(rule.is_catch_all),
        rationale=rule.rationale or "",
        scope_category_code=code_of(getattr(rule, "category", None)),
        scope_subcategory_code=code_of(getattr(rule, "subcategory", None)),
        category_code=code_of(rule.outcome_category),
        subcategory_code=code_of(rule.outcome_subcategory),
        department_code=code_of(rule.outcome_department),
        support_department_code=code_of(rule.outcome_support_department),
        urgency=rule.outcome_urgency,
        priority_code=rule.outcome_priority_code,
        escalation_code=rule.outcome_escalation_code,
        required_actions=list(rule.required_actions or []),
        prohibited_actions=list(rule.prohibited_actions or []),
        policy_refs=list(rule.policy_refs or []),
        follow_up_required=bool(rule.follow_up_required),
        eligibility=dict(rule.eligibility) if rule.eligibility else None,
    )
