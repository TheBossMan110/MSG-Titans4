"""
Pipeline 2 — the Python Ground-Truth Validation Pipeline.

    complaint text
      -> signals        deterministic lexicon + entity + fact extraction
      -> rules (pass 1) classification and routing, category not yet known
      -> rules (pass 2) scoped rules, now that the category has settled
      -> escalation floor
      -> eligibility findings
      -> validation_runs + rule_hits + eligibility_decisions

SRS 1.2 requires this pipeline to be "developed independently using Python"
and states that it "must not use a Generative AI API to approve the output of
Pipeline 1".  Two structural properties enforce that rather than promising it:

1. **Nothing in this package imports a provider client.**  ``grep -r`` over
   ``python_validation/`` finds no ``google``, ``groq``, ``openai`` or
   ``anthropic`` import, and a test asserts it stays that way.
2. **The GenAI result is not a parameter.**  ``run_validation`` takes a
   complaint and returns a conclusion.  There is nowhere to pass the model's
   answer in, so it cannot influence the ground truth even accidentally.

``python_validation/cli.py`` demonstrates both by running this with no API key
configured at all.

Why two passes
--------------
A routing rule scoped to ``category: BILLING`` cannot be evaluated until the
category is known, and the category is itself decided by rules.  Pass 1 runs
with no category and settles classification; pass 2 re-runs the whole matrix
with the category in context so scoped rules can refine the result.  Two
passes is a deliberate fixed bound — not a loop to convergence — because a
rule set that oscillates between two categories is an authoring bug that
should be visible, not smoothed over by iterating until it stops moving.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from python_validation.rule_engine import (
    DerivedOutcome,
    LoadedRule,
    evaluate_rules,
    rule_from_model,
)
from python_validation.signals import SignalSet, extract_signals
from src.core.logging import get_logger
from src.core.refcache import reference_data
from src.db.enums import EligibilityOutcome, EligibilityType
from src.db.models import (
    Category,
    Complaint,
    ComplaintLink,
    Department,
    EligibilityDecision,
    EscalationLevel,
    PriorityLevel,
    Rule,
    RuleHit,
    Subcategory,
    ValidationRun,
)

log = get_logger("python_validation.pipeline")

MAX_PASSES = 2


@dataclass
class ValidationResult:
    """
    Pipeline 2's complete conclusion about one complaint.

    Everything needed to explain the conclusion travels with it, so the
    reconciliation layer and the UI never have to re-derive anything.
    """

    outcome: DerivedOutcome
    signals: SignalSet
    eligibility: list[dict[str, Any]] = field(default_factory=list)
    latency_ms: int = 0
    passes: int = 0
    ruleset_version: str = "unversioned"
    knowledge_base_version: str | None = None
    validation_run_id: Any = None

    @property
    def requires_review(self) -> bool:
        """Conditions under which a human must see this before the customer does."""
        return (
            self.outcome.unmatched
            or self.outcome.conflict_detected
            or bool(self.outcome.rule_errors)
        )

    @property
    def review_reasons(self) -> list[str]:
        reasons: list[str] = []
        if self.outcome.unmatched:
            reasons.append("RULE_UNMATCHED")
        if self.outcome.conflict_detected:
            reasons.append("RULE_CONFLICT")
        if self.outcome.rule_errors:
            reasons.append("RULE_ERROR")
        return reasons

    def summary(self) -> dict[str, Any]:
        """Compact form for logs, the CLI and the comparison engine."""
        return {
            "category": self.outcome.category_code,
            "subcategory": self.outcome.subcategory_code,
            "department": self.outcome.department_code,
            "support_department": self.outcome.support_department_code,
            "urgency": self.outcome.urgency,
            "priority": self.outcome.priority_code,
            "escalation": self.outcome.escalation_code,
            "escalation_floor": self.outcome.escalation_floor_code,
            "required_actions": self.outcome.required_actions,
            "prohibited_actions": self.outcome.prohibited_actions,
            "policy_refs": self.outcome.policy_refs,
            "follow_up_required": self.outcome.follow_up_required,
            "reason_codes": self.outcome.reason_codes,
            "rules_fired": [h.rule_ref for h in self.outcome.applied_hits],
            "mandatory_escalation_rules": self.outcome.mandatory_escalation_refs,
            "unmatched": self.outcome.unmatched,
            "conflict_detected": self.outcome.conflict_detected,
            "signals": sorted(self.signals.for_rules()),
            "eligibility": self.eligibility,
            "latency_ms": self.latency_ms,
            "ruleset_version": self.ruleset_version,
        }


# ══════════════════════════════════════════════════════════════
# loading the matrix
# ══════════════════════════════════════════════════════════════
@reference_data("active_rules", copy_result=False)
def load_active_rules(db: Session) -> list[LoadedRule]:
    """Every active rule, flattened for the engine."""
    rows = db.execute(
        select(Rule)
        .where(Rule.is_active.is_(True))
        .order_by(Rule.precedence.desc(), Rule.rule_ref)
    ).scalars().all()
    return [rule_from_model(row) for row in rows]


@reference_data("ladder_ranks")
def _ladder_ranks(db: Session) -> tuple[dict[str, int], dict[str, int]]:
    escalation = {
        row.code: row.rank for row in db.execute(select(EscalationLevel)).scalars()
    }
    priority = {row.code: row.rank for row in db.execute(select(PriorityLevel)).scalars()}
    return escalation, priority


@reference_data("ruleset_version")
def _ruleset_version(db: Session) -> str:
    from src.db.seed.rules import current_ruleset_version

    return current_ruleset_version(db)


# ══════════════════════════════════════════════════════════════
# repeat history  (FR lviii / SRS Step 54)
# ══════════════════════════════════════════════════════════════
def count_repeats(db: Session, complaint: Complaint | None) -> tuple[int, int]:
    """
    Return ``(repeat_count, prior_complaints)`` for this customer.

    A repeat is measured from linked records and from the customer's unresolved
    history, not from the complaint claiming to be one — a customer saying "this
    is the third time" may be right or wrong, and the rule engine should see
    both the claim (as a signal) and the fact (as a count).
    """
    if complaint is None or complaint.id is None:
        return 0, 0

    linked = db.execute(
        select(func.count()).select_from(ComplaintLink).where(
            ComplaintLink.complaint_id == complaint.id,
            ComplaintLink.link_type.in_(["REPEAT", "NEAR_DUPLICATE", "EXACT_DUPLICATE"]),
        )
    ).scalar_one()

    prior = 0
    if complaint.customer_id:
        prior = db.execute(
            select(func.count()).select_from(Complaint).where(
                Complaint.customer_id == complaint.customer_id,
                Complaint.id != complaint.id,
                Complaint.created_at < (complaint.created_at or datetime.now(UTC)),
            )
        ).scalar_one()

    chain = 1 if complaint.previous_complaint_id else 0
    stored = complaint.repeat_count or 0

    return max(linked + chain, stored), prior


# ══════════════════════════════════════════════════════════════
# eligibility  (FR xxvi-xxviii / SRS Steps 29-31)
# ══════════════════════════════════════════════════════════════
def _collect_eligibility(
    rules: list[LoadedRule], outcome: DerivedOutcome
) -> list[dict[str, Any]]:
    """
    Turn eligibility-bearing rules that fired into findings.

    Where two rules assert different outcomes for the same eligibility type,
    the **more restrictive** one wins.  That direction is deliberate: wrongly
    withholding a refund is recoverable by a human, wrongly promising one is
    not (SRS 1.8 #9).
    """
    restrictiveness = {
        EligibilityOutcome.ELIGIBLE: 0,
        EligibilityOutcome.CONDITIONAL: 1,
        EligibilityOutcome.REQUIRES_VERIFICATION: 2,
        EligibilityOutcome.NOT_ELIGIBLE: 3,
        EligibilityOutcome.NOT_APPLICABLE: -1,
    }

    fired = {hit.rule_ref for hit in outcome.applied_hits}
    by_type: dict[str, dict[str, Any]] = {}

    for rule in rules:
        if rule.rule_ref not in fired or not rule.eligibility:
            continue

        spec = rule.eligibility
        raw_type = str(spec.get("type", "")).upper()
        if raw_type not in {member.value for member in EligibilityType}:
            log.warning("unknown_eligibility_type", rule=rule.rule_ref, type=raw_type)
            continue

        raw_outcome = str(spec.get("outcome", EligibilityOutcome.REQUIRES_VERIFICATION)).upper()
        if raw_outcome not in {member.value for member in EligibilityOutcome}:
            log.warning("unknown_eligibility_outcome", rule=rule.rule_ref, outcome=raw_outcome)
            continue

        finding = {
            "eligibility_type": raw_type,
            "python_outcome": raw_outcome,
            "rule_ref": rule.rule_ref,
            "conditions_evaluated": list(spec.get("conditions") or []),
            "requires_human_approval": bool(spec.get("requires_human_approval", False)),
            "max_amount": spec.get("max_amount"),
            "currency": spec.get("currency"),
            "policy_ref": spec.get("policy_ref"),
            "reason": rule.rationale,
        }

        existing = by_type.get(raw_type)
        if existing is None:
            by_type[raw_type] = finding
            continue

        if restrictiveness[raw_outcome] > restrictiveness[existing["python_outcome"]]:
            finding["superseded_rule_ref"] = existing["rule_ref"]
            by_type[raw_type] = finding

    return list(by_type.values())


# ══════════════════════════════════════════════════════════════
# the pipeline
# ══════════════════════════════════════════════════════════════
def run_validation(
    db: Session,
    *,
    text: str,
    complaint: Complaint | None = None,
    rules: list[LoadedRule] | None = None,
    knowledge_base_version: str | None = None,
) -> ValidationResult:
    """
    Derive the ground truth for one complaint.

    Note the signature: there is no parameter for the GenAI result.  This
    function cannot be influenced by it, which is what makes the comparison
    downstream a genuine second opinion rather than a rubber stamp.
    """
    started = time.perf_counter()

    rules = rules if rules is not None else load_active_rules(db)
    escalation_ranks, priority_ranks = _ladder_ranks(db)
    ruleset_version = _ruleset_version(db)

    repeat_count, prior_complaints = count_repeats(db, complaint)
    signals = extract_signals(
        db, text,
        complaint=complaint,
        repeat_count=repeat_count,
        prior_complaints=prior_complaints,
    )

    base_fields: dict[str, Any] = {
        "channel": getattr(complaint, "channel", None),
        "product": getattr(complaint, "product", None),
        "customer_tier": signals.fact("customer_tier"),
        "injection_suspected": bool(getattr(complaint, "injection_suspected", False)),
        "order_ref": signals.fact("order_ref"),
    }

    outcome: DerivedOutcome | None = None
    passes = 0

    for pass_number in range(1, MAX_PASSES + 1):
        fields = dict(base_fields)
        if outcome is not None:
            fields["category"] = outcome.category_code
            fields["subcategory"] = outcome.subcategory_code

        outcome = evaluate_rules(
            rules, signals,
            fields=fields,
            escalation_ranks=escalation_ranks,
            priority_ranks=priority_ranks,
            ruleset_version=ruleset_version,
        )
        passes = pass_number

        # Nothing matched on the first pass: a second pass has no new context
        # to offer, so stop rather than repeating the same evaluation.
        if outcome.unmatched and pass_number == 1 and not outcome.category_code:
            break

    assert outcome is not None  # loop always runs at least once

    result = ValidationResult(
        outcome=outcome,
        signals=signals,
        eligibility=_collect_eligibility(rules, outcome),
        latency_ms=int((time.perf_counter() - started) * 1000),
        passes=passes,
        ruleset_version=ruleset_version,
        knowledge_base_version=knowledge_base_version,
    )

    log.info(
        "validation_complete",
        complaint=getattr(complaint, "public_ref", None),
        department=outcome.department_code,
        urgency=outcome.urgency,
        escalation=outcome.escalation_code,
        floor=outcome.escalation_floor_code,
        rules=len(outcome.applied_hits),
        passes=passes,
        ms=result.latency_ms,
    )
    return result


# ══════════════════════════════════════════════════════════════
# persistence
# ══════════════════════════════════════════════════════════════
def _resolve_ids(db: Session, outcome: DerivedOutcome) -> dict[str, Any]:
    """Turn the outcome's codes into foreign keys for storage."""
    def category_id(code: str | None):
        if not code:
            return None
        row = db.execute(select(Category).where(Category.code == code)).scalars().first()
        return row.id if row else None

    def department_id(code: str | None):
        if not code:
            return None
        row = db.execute(select(Department).where(Department.code == code)).scalars().first()
        return row.id if row else None

    subcategory_id = None
    if outcome.subcategory_code:
        row = db.execute(
            select(Subcategory).where(Subcategory.code == outcome.subcategory_code)
        ).scalars().first()
        subcategory_id = row.id if row else None

    return {
        "derived_category_id": category_id(outcome.category_code),
        "derived_subcategory_id": subcategory_id,
        "derived_department_id": department_id(outcome.department_code),
        "derived_support_department_id": department_id(outcome.support_department_code),
    }


def persist_validation(
    db: Session, complaint: Complaint, result: ValidationResult
) -> ValidationRun:
    """
    Write the ground truth to the database.

    One ``validation_run`` per evaluation and one ``rule_hit`` per rule that
    fired — including rules that matched but lost on precedence, which are
    stored with ``applied=False``.  Keeping the losers is what lets the
    explainability panel show *why* a lower-precedence rule did not decide the
    outcome, instead of leaving the reviewer to guess.
    """
    ids = _resolve_ids(db, result.outcome)
    outcome = result.outcome

    run = ValidationRun(
        complaint_id=complaint.id,
        ruleset_version=result.ruleset_version,
        knowledge_base_version=result.knowledge_base_version,
        signals=result.signals.as_dict(),
        derived_urgency=outcome.urgency,
        derived_priority_code=outcome.priority_code,
        derived_escalation_code=outcome.escalation_code,
        escalation_floor_code=outcome.escalation_floor_code,
        required_actions=outcome.required_actions,
        prohibited_actions=outcome.prohibited_actions,
        policy_refs=outcome.policy_refs,
        follow_up_required=outcome.follow_up_required,
        reason_codes=outcome.reason_codes,
        unmatched=outcome.unmatched,
        conflict_detected=outcome.conflict_detected,
        latency_ms=result.latency_ms,
        **ids,
    )
    db.add(run)
    db.flush()

    for hit in outcome.hits:
        if hit.rule_id is None:
            continue
        db.add(
            RuleHit(
                validation_run_id=run.id,
                rule_id=hit.rule_id,
                rule_ref=hit.rule_ref,
                precedence=hit.precedence,
                matched_signals=hit.matched_signals,
                matched_spans=hit.matched_spans,
                applied=hit.applied,
            )
        )

    for finding in result.eligibility:
        existing = db.execute(
            select(EligibilityDecision).where(
                EligibilityDecision.complaint_id == complaint.id,
                EligibilityDecision.eligibility_type == finding["eligibility_type"],
            )
        ).scalars().first()

        policy_ref = finding.get("policy_ref") or {}
        values = {
            "python_outcome": finding["python_outcome"],
            # Until Pipeline 1 has run there is nothing to reconcile against,
            # so the deterministic finding stands as final.
            "final_outcome": finding["python_outcome"],
            "conditions_evaluated": finding["conditions_evaluated"],
            "rule_ref": finding["rule_ref"],
            "policy_ref": policy_ref.get("doc_ref"),
            "section_ref": policy_ref.get("section_ref"),
            "max_amount": finding.get("max_amount"),
            "currency": finding.get("currency"),
            "requires_human_approval": finding["requires_human_approval"],
            "reason": finding.get("reason") or "",
        }

        if existing is None:
            db.add(
                EligibilityDecision(
                    complaint_id=complaint.id,
                    eligibility_type=finding["eligibility_type"],
                    **values,
                )
            )
        else:
            for key, value in values.items():
                setattr(existing, key, value)

    db.flush()
    result.validation_run_id = run.id
    return run


def validate_complaint(
    db: Session, complaint: Complaint, *, persist: bool = True
) -> ValidationResult:
    """Run and optionally store the ground truth for a stored complaint."""
    from knowledge_base.versioning import knowledge_base_version

    result = run_validation(
        db,
        text=complaint.description_clean or complaint.description_raw or "",
        complaint=complaint,
        knowledge_base_version=knowledge_base_version(db),
    )
    if persist:
        persist_validation(db, complaint, result)
    return result
