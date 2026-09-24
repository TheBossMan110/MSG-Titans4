"""
The verification decision (FR li; SRS Step 57; Deliverable 8).

Turns a list of field comparisons into one verdict: what the system finally
decided, how much the two pipelines agreed, whether a human is needed, and why.

**Every score is computed from stored rows.** SRS 1.8 #17 forbids a displayed
number that is not traceable to evidence, so each score here returns its own
numerator and denominator alongside the percentage, and a score with no
denominator is ``None`` rather than a flattering 100.

**The reconciled record is the only thing downstream may use.** Response
generation never reads raw model output; it reads this. That is what stops an
unverified classification reaching a customer.

**The escalation floor is enforced last, and it only ever raises.** Whatever
the comparison concluded, an escalation level below the rule-derived floor is
lifted back to it and the override is recorded. This is the structural answer
to SRS 1.8 #7: the floor is not advice that a later stage may weigh.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from comparison_engine.diff import FieldComparison
from comparison_engine.ladders import at_or_above, severity_rank
from src.core.logging import get_logger
from src.db.enums import ComparisonStatus, Severity, VerificationOutcome

log = get_logger("comparison_engine.decision")

DEFAULT_HIGH_MISMATCH_REVIEW_THRESHOLD = 2


class ReviewReason:
    """Why a human was put in the loop. Mirrors ``policy.yaml``."""

    GENAI_PYTHON_DISAGREEMENT = "GENAI_PYTHON_DISAGREEMENT"
    POLICY_SUPPORT_MISSING = "POLICY_SUPPORT_MISSING"
    AMBIGUOUS_COMPLAINT = "AMBIGUOUS_COMPLAINT"
    ESCALATION_UNCLEAR = "ESCALATION_UNCLEAR"
    POLICY_CONTRADICTION = "POLICY_CONTRADICTION"
    SENSITIVE_COMPLAINT = "SENSITIVE_COMPLAINT"
    GUARD_BLOCKED = "GUARD_BLOCKED"
    GENAI_UNAVAILABLE = "GENAI_UNAVAILABLE"
    RULE_UNMATCHED = "RULE_UNMATCHED"
    RULE_CONFLICT = "RULE_CONFLICT"


@dataclass(slots=True)
class Score:
    """A percentage with the evidence it was derived from."""

    numerator: int = 0
    denominator: int = 0

    @property
    def value(self) -> float | None:
        """``None`` when there is nothing to measure — never a default 100."""
        if self.denominator <= 0:
            return None
        return round(self.numerator / self.denominator * 100.0, 2)

    def as_dict(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "numerator": self.numerator,
            "denominator": self.denominator,
        }


@dataclass(slots=True)
class VerificationResult:
    """The reconciled verdict for one complaint."""

    outcome: str
    comparisons: list[FieldComparison] = field(default_factory=list)
    reconciled: dict[str, Any] = field(default_factory=dict)

    agreement: Score = field(default_factory=Score)
    traceability: Score = field(default_factory=Score)
    compliance: Score = field(default_factory=Score)

    critical_mismatches: int = 0
    high_mismatches: int = 0
    total_fields: int = 0
    matched_fields: int = 0

    requires_review: bool = False
    review_reasons: list[str] = field(default_factory=list)
    genai_available: bool = True
    escalation_overridden: bool = False
    notes: list[str] = field(default_factory=list)

    @property
    def blocked(self) -> bool:
        return self.outcome in (
            VerificationOutcome.BLOCKED,
            VerificationOutcome.MANUAL_REVIEW_REQUIRED,
            VerificationOutcome.INCOMPLETE,
        )

    def summary(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome,
            "agreement_score": self.agreement.as_dict(),
            "traceability_score": self.traceability.as_dict(),
            "compliance_score": self.compliance.as_dict(),
            "critical_mismatches": self.critical_mismatches,
            "high_mismatches": self.high_mismatches,
            "matched_fields": self.matched_fields,
            "total_fields": self.total_fields,
            "requires_review": self.requires_review,
            "review_reasons": self.review_reasons,
            "genai_available": self.genai_available,
            "escalation_overridden": self.escalation_overridden,
        }

    def mismatches(self) -> list[FieldComparison]:
        return [c for c in self.comparisons if c.is_mismatch]


# ══════════════════════════════════════════════════════════════
# scores
# ══════════════════════════════════════════════════════════════
def agreement_score(comparisons: list[FieldComparison]) -> Score:
    """
    ``matched_fields / total_compared_fields * 100`` (policy.yaml).

    Only fields both pipelines derived are counted. A field Pipeline 2 does
    not produce is not a disagreement, and including it would make the score
    measure the architecture instead of the model.
    """
    compared = [c for c in comparisons if c.counts_toward_agreement]
    matched = [c for c in compared if c.status == ComparisonStatus.MATCH]
    return Score(numerator=len(matched), denominator=len(compared))


def traceability_score(citations: list[dict[str, Any]]) -> Score:
    """
    ``resolvable_active_citations / total_citations * 100`` (policy.yaml).

    A citation counts only when the chunk resolves **and** its document version
    is ACTIVE. A correctly-formatted reference to a superseded policy is a
    traceability failure, not a success: acting on a withdrawn policy is the
    outcome SRS 1.8 #10 is testing for.
    """
    if not citations:
        # No citation attempted is not the same as every citation failing.
        # A complaint needing no policy support must not be scored as 0%.
        return Score(numerator=0, denominator=0)
    resolvable = [c for c in citations if c.get("resolvable") and c.get("active")]
    return Score(numerator=len(resolvable), denominator=len(citations))


def compliance_score(guard_checks: tuple[int, int] | None = None) -> Score:
    """
    ``guard_checks_passed / guard_checks_run * 100`` (policy.yaml).

    Measured by the response guard against the generated reply, because that
    is the only place the question can be answered deterministically. Each
    check is something the guard actually asked and can point at: is this
    promise authorised by an ELIGIBLE eligibility decision, does this citation
    resolve to an ACTIVE document, is this policy claim cited.

    At reconciliation time no reply exists yet, so ``guard_checks`` is None and
    the score is empty. It is filled in by
    :func:`comparison_engine.decision.record_guard_compliance` once the
    response stage has run.

    A ``Score`` with no denominator renders as ``None``, not as 0% or 100%: an
    unmeasured control must not display as a passing one (SRS 1.8 #17), and a
    reply that promised nothing and cited nothing gave the guard nothing to
    check.
    """
    if not guard_checks:
        return Score()
    passed, run = guard_checks
    return Score(numerator=passed, denominator=run)


def _count(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, (list, tuple, set, frozenset)):
        return len(value)
    return 1 if str(value).strip() else 0


# ══════════════════════════════════════════════════════════════
# reconciliation
# ══════════════════════════════════════════════════════════════
def build_reconciled(
    comparisons: list[FieldComparison],
    outcome: Any,
    *,
    ladders: dict[str, dict[str, int]],
) -> tuple[dict[str, Any], bool]:
    """
    The single agreed record downstream stages are constrained by.

    Returns ``(reconciled, escalation_was_overridden)``.

    The floor is applied after every field has been resolved, so it overrides
    the comparison rather than participating in it. A floor that could be
    weighed against other evidence would not be a floor.
    """
    reconciled: dict[str, Any] = {
        comparison.field: comparison.final_value for comparison in comparisons
    }

    # The rule matrix's obligations are carried through verbatim, from the
    # rule engine and never from the model. They are not compared here (see
    # comparison_engine.fields); they are the constraint list the response
    # guard enforces against the generated reply under SRS Step 28.
    reconciled["required_actions"] = list(getattr(outcome, "required_actions", []) or [])
    reconciled["prohibited_actions"] = list(
        getattr(outcome, "prohibited_actions", []) or []
    )

    floor = getattr(outcome, "escalation_floor_code", None) if outcome else None
    reconciled["escalation_floor"] = floor

    overridden = False
    if floor:
        current = reconciled.get("escalation_level")
        if not at_or_above(ladders, "escalation_level", current, floor):
            log.warning(
                "escalation_floor_enforced",
                proposed=current, floor=floor,
            )
            reconciled["escalation_level"] = floor
            reconciled["escalation_floor_applied"] = True
            overridden = True

    reconciled["escalation_required"] = bool(
        reconciled.get("escalation_level")
        and str(reconciled["escalation_level"]).upper() != "NONE"
    )
    return reconciled, overridden


# ══════════════════════════════════════════════════════════════
# the verdict
# ══════════════════════════════════════════════════════════════
def decide(
    comparisons: list[FieldComparison],
    outcome: Any,
    *,
    ladders: dict[str, dict[str, int]],
    citations: list[dict[str, Any]] | None = None,
    genai_available: bool = True,
    verification_config: dict[str, Any] | None = None,
    extra_review_reasons: list[str] | None = None,
) -> VerificationResult:
    """
    Reconcile both pipelines into one decision.

    The outcome ladder, worst first:

    * **BLOCKED** — nothing usable. Only when the rule engine itself failed to
      classify, so there is no trustworthy value to fall back to.
    * **MANUAL_REVIEW_REQUIRED** — a human must look before the customer does.
    * **CORRECTED_BY_RULES** — the rules overrode the model on a critical
      field. The system is still confident; the model was wrong.
    * **INCOMPLETE** — no GenAI contribution at all (outage). The rule result
      stands and is fully usable, but it is labelled honestly.
    * **VERIFIED_WITH_WARNING** — minor disagreements only.
    * **VERIFIED** — both pipelines agreed on everything compared.
    """
    config = verification_config or {}
    review_threshold = int(
        config.get("high_mismatch_review_threshold", DEFAULT_HIGH_MISMATCH_REVIEW_THRESHOLD)
    )

    critical = [c for c in comparisons if c.is_critical_mismatch]
    high = [c for c in comparisons if c.is_high_mismatch]
    compared = [c for c in comparisons if c.counts_toward_agreement]
    matched = [c for c in compared if c.status == ComparisonStatus.MATCH]

    reconciled, escalation_overridden = build_reconciled(
        comparisons, outcome, ladders=ladders
    )

    reasons: list[str] = list(extra_review_reasons or [])
    notes: list[str] = []

    if not genai_available:
        reasons.append(ReviewReason.GENAI_UNAVAILABLE)
        notes.append(
            "No GenAI contribution: the decision rests entirely on the rule engine."
        )

    if critical:
        reasons.append(ReviewReason.GENAI_PYTHON_DISAGREEMENT)
    if len(high) >= review_threshold:
        reasons.append(ReviewReason.GENAI_PYTHON_DISAGREEMENT)

    if any(c.needs_review for c in comparisons):
        reasons.append(ReviewReason.GENAI_PYTHON_DISAGREEMENT)

    if escalation_overridden:
        reasons.append(ReviewReason.ESCALATION_UNCLEAR)
        notes.append(
            "The GenAI escalation level was below the mandatory floor and was raised to it."
        )

    if outcome is not None:
        if getattr(outcome, "unmatched", False):
            reasons.append(ReviewReason.RULE_UNMATCHED)
            notes.append("No substantive rule matched; manual classification is required.")
        if getattr(outcome, "conflict_detected", False):
            reasons.append(ReviewReason.RULE_CONFLICT)

    scores = {
        "agreement": agreement_score(comparisons),
        "traceability": traceability_score(citations or []),
        # Empty here by construction: the reply does not exist yet.
        "compliance": compliance_score(),
    }

    if scores["traceability"].denominator and (scores["traceability"].value or 0) < 100.0:
        reasons.append(ReviewReason.POLICY_SUPPORT_MISSING)

    reasons = list(dict.fromkeys(reasons))  # de-duplicate, keep order
    requires_review = bool(reasons)

    # ── outcome ──
    rule_result_usable = outcome is not None and bool(
        getattr(outcome, "category_code", None)
    )

    if not rule_result_usable:
        # Neither pipeline produced a trustworthy classification.
        verdict = VerificationOutcome.BLOCKED
        requires_review = True
        if ReviewReason.AMBIGUOUS_COMPLAINT not in reasons:
            reasons.append(ReviewReason.AMBIGUOUS_COMPLAINT)
    elif not genai_available:
        verdict = VerificationOutcome.INCOMPLETE
    elif requires_review and (critical or len(high) >= review_threshold):
        verdict = (
            VerificationOutcome.CORRECTED_BY_RULES
            if critical and len(high) < review_threshold
            else VerificationOutcome.MANUAL_REVIEW_REQUIRED
        )
    elif critical:
        verdict = VerificationOutcome.CORRECTED_BY_RULES
    elif requires_review:
        verdict = VerificationOutcome.MANUAL_REVIEW_REQUIRED
    elif any(c.is_mismatch for c in comparisons):
        verdict = VerificationOutcome.VERIFIED_WITH_WARNING
    else:
        verdict = VerificationOutcome.VERIFIED

    result = VerificationResult(
        outcome=verdict,
        comparisons=comparisons,
        reconciled=reconciled,
        agreement=scores["agreement"],
        traceability=scores["traceability"],
        compliance=scores["compliance"],
        critical_mismatches=len(critical),
        high_mismatches=len(high),
        total_fields=len(compared),
        matched_fields=len(matched),
        requires_review=requires_review,
        review_reasons=reasons,
        genai_available=genai_available,
        escalation_overridden=escalation_overridden,
        notes=notes,
    )

    log.info(
        "verification_decided",
        outcome=verdict,
        agreement=result.agreement.value,
        critical=len(critical), high=len(high),
        review=requires_review, reasons=reasons,
    )
    return result


def decided_at() -> datetime:
    return datetime.now(UTC)


def record_guard_compliance(
    db: Any, complaint_id: Any, guard_checks: tuple[int, int]
) -> Score | None:
    """
    Fill in the compliance score once the response guard has run.

    Updates the complaint's most recent ``verification_decisions`` row rather
    than writing a second one: there is one verdict per complaint, and the
    compliance figure is a later-arriving part of it, not a new decision.

    Returns the score that was written, or ``None`` when there is no decision
    to attach it to or nothing was checked.
    """
    from comparison_engine.engine import latest_decision

    score = compliance_score(guard_checks)
    if score.value is None:
        return None

    decision = latest_decision(db, complaint_id)
    if decision is None:
        log.warning("compliance_without_decision", complaint=str(complaint_id))
        return None

    decision.compliance_score = score.value
    db.flush()
    log.info(
        "compliance_recorded",
        complaint=str(complaint_id),
        value=score.value, passed=score.numerator, run=score.denominator,
    )
    return score


def floor_satisfied(
    ladders: dict[str, dict[str, int]], reconciled: dict[str, Any]
) -> bool:
    """
    Assert the invariant the escalation trap turns on.

    Called by the tests and by the benchmark runner: the reconciled escalation
    level must never sit below the recorded floor.
    """
    return at_or_above(
        ladders,
        "escalation_level",
        reconciled.get("escalation_level"),
        reconciled.get("escalation_floor"),
    )


def rank_of(ladders: dict[str, dict[str, int]], field_name: str, value: str | None) -> int | None:
    """Re-exported for the reports, which rank outcomes without importing ladders."""
    return severity_rank(ladders, field_name, value)


SEVERITY_ORDER = {
    Severity.INFORMATIONAL: 0,
    Severity.MEDIUM: 1,
    Severity.HIGH: 2,
    Severity.CRITICAL: 3,
}
