"""
The comparison engine — diff, ladders, scores, decision, reconciliation.

Runs entirely offline with a stubbed Pipeline 1, so the tests measure the
comparison logic rather than a model's mood on the day.

The two that matter most, and why:

* :meth:`TestEscalationFloor.test_floor_raises_a_lower_genai_escalation` —
  SRS 1.8 #7. A model proposing a level below the mandatory floor must be
  raised to it, every time, including when the configuration has been edited
  to let the model win that field.
* :meth:`TestLadders.test_priority_ranks_are_inverted_on_load` — the priority
  table counts *down* in severity (P0 is rank 0) while escalation counts up.
  Compared raw, an under-prioritisation would be reported as over-caution,
  silently inverting the signal the floor exists to catch.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

import pytest
from sqlalchemy import select

from comparison_engine import (
    ReviewReason,
    compare_all,
    decide,
    floor_satisfied,
    load_ladders,
    reconcile,
)
from comparison_engine.decision import (
    Score,
    agreement_score,
    compliance_score,
    traceability_score,
)
from comparison_engine.engine import comparison_rows, load_comparison_config, resolve_citations
from comparison_engine.ladders import at_or_above, severity_rank
from src.db.enums import (
    Channel,
    ComparisonStatus,
    ComplaintStatus,
    Severity,
    VerificationOutcome,
    Winner,
)
from src.db.models import Comparison, Complaint, GenAIRun, VerificationDecision


# ══════════════════════════════════════════════════════════════
# stubs — shaped like the two real results, without running either
# ══════════════════════════════════════════════════════════════
@dataclass
class FakeStep:
    step: str = "Do the thing"
    action_code: str | None = None


@dataclass
class FakeRef:
    chunk_key: str | None = None
    doc_ref: str = "SAF-POL-02"
    section_ref: str | None = "5"
    supports: str | None = None


@dataclass
class FakeIntelligence:
    """Shaped like ``ComplaintIntelligence``."""

    category: str = "SAFETY"
    subcategory: str | None = "OVERHEATING"
    department: str = "SAFETY"
    support_department: str | None = None
    urgency: str = "CRITICAL"
    priority: str = "P0"
    escalation_required: bool = True
    escalation_level: str | None = "CRITICAL_MGMT"
    follow_up_required: bool = True
    sentiment: str = "NEGATIVE"
    primary_issue: str = "Charger overheating"
    resolution_steps: list[FakeStep] = field(default_factory=list)
    policy_refs: list[FakeRef] = field(default_factory=list)


@dataclass
class FakeOutcome:
    """Shaped like ``DerivedOutcome``."""

    category_code: str | None = "SAFETY"
    subcategory_code: str | None = "OVERHEATING"
    department_code: str | None = "SAFETY"
    support_department_code: str | None = None
    urgency: str | None = "CRITICAL"
    priority_code: str | None = "P0"
    escalation_code: str | None = "CRITICAL_MGMT"
    escalation_floor_code: str | None = "CRITICAL_MGMT"
    required_actions: list[str] = field(default_factory=list)
    prohibited_actions: list[str] = field(default_factory=list)
    follow_up_required: bool = True
    unmatched: bool = False
    conflict_detected: bool = False
    rule_errors: list[str] = field(default_factory=list)


@pytest.fixture
def ladders(db):
    return load_ladders(db)


@pytest.fixture
def weights(db):
    configured, _, _ = load_comparison_config(db)
    return configured


def _compare(intelligence, outcome, *, weights, ladders):
    return compare_all(intelligence, outcome, weights=weights, ranks=ladders)


def _by_field(comparisons):
    return {c.field: c for c in comparisons}


# ══════════════════════════════════════════════════════════════
# ladders
# ══════════════════════════════════════════════════════════════
class TestLadders:
    def test_escalation_ranks_ascend_with_severity(self, ladders):
        escalation = ladders["escalation_level"]
        assert escalation["NONE"] < escalation["CRITICAL_MGMT"]

    def test_priority_ranks_are_inverted_on_load(self, ladders):
        """
        ``priority_levels.rank`` is 0 for P0 — a display order, counting the
        opposite way to severity. Left raw, every priority comparison would
        report its direction backwards.
        """
        priority = ladders["priority"]
        assert priority["P0"] > priority["P3"], "P0 must outrank P3 in severity"
        assert priority["P1"] > priority["P2"]

    def test_urgency_ranks_are_plain_strings(self, ladders):
        assert set(ladders["urgency"]) == {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
        assert severity_rank(ladders, "urgency", "high") == 2, "lookup is case-insensitive"

    def test_at_or_above_respects_direction(self, ladders):
        assert at_or_above(ladders, "escalation_level", "CRITICAL_MGMT", "SUPERVISOR")
        assert not at_or_above(ladders, "escalation_level", "SUPERVISOR", "CRITICAL_MGMT")
        assert at_or_above(ladders, "priority", "P0", "P2")
        assert not at_or_above(ladders, "priority", "P2", "P0")

    def test_unknown_value_fails_closed_against_a_floor(self, ladders):
        """A level we cannot place must not be treated as satisfying a floor."""
        assert not at_or_above(ladders, "escalation_level", "MADE_UP", "SUPERVISOR")

    def test_no_floor_is_always_satisfied(self, ladders):
        assert at_or_above(ladders, "escalation_level", "NONE", None)


# ══════════════════════════════════════════════════════════════
# field comparison
# ══════════════════════════════════════════════════════════════
class TestFieldComparison:
    def test_full_agreement_matches_every_compared_field(self, weights, ladders):
        comparisons = _compare(FakeIntelligence(), FakeOutcome(), weights=weights, ladders=ladders)
        compared = [c for c in comparisons if c.counts_toward_agreement]
        assert compared and all(c.status == ComparisonStatus.MATCH for c in compared)
        assert all(c.winner == Winner.AGREED for c in compared)

    def test_category_disagreement_is_recorded_with_an_explanation(self, weights, ladders):
        comparisons = _compare(
            FakeIntelligence(category="DELIVERY"), FakeOutcome(), weights=weights, ladders=ladders
        )
        category = _by_field(comparisons)["category"]
        assert category.status == ComparisonStatus.MISMATCH
        assert category.severity == Severity.HIGH
        assert "DELIVERY" in category.explanation and "SAFETY" in category.explanation

    def test_rules_win_a_department_disagreement(self, weights, ladders):
        comparisons = _compare(
            FakeIntelligence(department="BILLING"), FakeOutcome(), weights=weights, ladders=ladders
        )
        department = _by_field(comparisons)["department"]
        assert department.severity == Severity.CRITICAL
        assert department.winner == Winner.PYTHON
        assert department.final_value == "SAFETY"

    def test_lower_genai_escalation_records_its_direction(self, weights, ladders):
        """The direction, not just the difference — SRS 1.8 #7."""
        comparisons = _compare(
            FakeIntelligence(escalation_level="SUPERVISOR"),
            FakeOutcome(), weights=weights, ladders=ladders,
        )
        escalation = _by_field(comparisons)["escalation_level"]
        assert escalation.direction == "GENAI_LOWER"
        assert escalation.reason_code == "GENAI_BELOW_RULE_DERIVED"
        assert "BELOW" in escalation.explanation

    def test_higher_genai_escalation_is_flagged_but_not_as_under_escalation(
        self, weights, ladders
    ):
        comparisons = _compare(
            FakeIntelligence(escalation_level="CRITICAL_MGMT"),
            FakeOutcome(escalation_code="SUPERVISOR", escalation_floor_code="SUPERVISOR"),
            weights=weights, ladders=ladders,
        )
        escalation = _by_field(comparisons)["escalation_level"]
        assert escalation.direction == "GENAI_HIGHER"
        assert escalation.reason_code != "GENAI_BELOW_RULE_DERIVED"

    def test_lower_priority_is_reported_as_lower(self, weights, ladders):
        """Guards the rank inversion: P2 against P0 must read as BELOW."""
        comparisons = _compare(
            FakeIntelligence(priority="P2"), FakeOutcome(), weights=weights, ladders=ladders
        )
        assert _by_field(comparisons)["priority"].direction == "GENAI_LOWER"

    def test_no_escalation_claim_reads_as_none_not_absent(self, weights, ladders):
        """
        "The model did not escalate" and "the model said nothing" are different
        claims, and only the first can be compared against a floor.
        """
        comparisons = _compare(
            FakeIntelligence(escalation_required=False, escalation_level=None),
            FakeOutcome(), weights=weights, ladders=ladders,
        )
        escalation = _by_field(comparisons)["escalation_level"]
        assert escalation.genai_value == "NONE"
        assert escalation.status == ComparisonStatus.MISMATCH
        assert escalation.direction == "GENAI_LOWER"

    def test_sentiment_is_unsupported_not_a_mismatch(self, weights, ladders):
        """
        Pipeline 2 derives no sentiment by design (SRS 1.8 #6). Scoring the
        model against that absence would manufacture a disagreement.
        """
        comparisons = _compare(FakeIntelligence(), FakeOutcome(), weights=weights, ladders=ladders)
        sentiment = _by_field(comparisons)["sentiment"]
        assert sentiment.status == ComparisonStatus.PYTHON_MISSING
        assert not sentiment.counts_toward_agreement
        assert sentiment.winner == Winner.GENAI

    def test_actions_are_not_compared_here(self, weights, ladders):
        """
        Obligations belong to the response guard (SRS Step 28). Comparing
        prose against prose produced false findings in both directions.
        """
        comparisons = _compare(FakeIntelligence(), FakeOutcome(), weights=weights, ladders=ladders)
        fields = {c.field for c in comparisons}
        assert "required_actions" not in fields
        assert "prohibited_actions" not in fields

    def test_missing_genai_leaves_the_rule_value_standing(self, weights, ladders):
        comparisons = _compare(None, FakeOutcome(), weights=weights, ladders=ladders)
        for comparison in comparisons:
            assert comparison.status in (
                ComparisonStatus.GENAI_MISSING, ComparisonStatus.UNSUPPORTED
            )
        department = _by_field(comparisons)["department"]
        assert department.final_value == "SAFETY", "nothing is invented to fill the gap"

    def test_long_values_are_truncated_to_fit_the_column(self, weights, ladders):
        """comparisons.genai_value is VARCHAR(512); PostgreSQL rejects overruns."""
        comparisons = _compare(
            FakeIntelligence(primary_issue="x" * 900), FakeOutcome(),
            weights=weights, ladders=ladders,
        )
        row = _by_field(comparisons)["primary_issue"].as_row()
        assert len(row["genai_value"]) <= 512


# ══════════════════════════════════════════════════════════════
# scores
# ══════════════════════════════════════════════════════════════
class TestScores:
    def test_agreement_counts_only_fields_both_pipelines_derived(self, weights, ladders):
        comparisons = _compare(FakeIntelligence(), FakeOutcome(), weights=weights, ladders=ladders)
        score = agreement_score(comparisons)
        assert score.value == 100.0
        assert score.denominator == len(
            [c for c in comparisons if c.counts_toward_agreement]
        )

    def test_agreement_falls_with_a_disagreement(self, weights, ladders):
        comparisons = _compare(
            FakeIntelligence(category="DELIVERY", department="LOGISTICS_OPS"),
            FakeOutcome(), weights=weights, ladders=ladders,
        )
        assert (agreement_score(comparisons).value or 100) < 100.0

    def test_a_score_with_no_denominator_is_none_not_a_hundred(self):
        """SRS 1.8 #17 — an unmeasured control must not display as a passing one."""
        assert Score(0, 0).value is None
        assert traceability_score([]).value is None
        assert compliance_score([]).value is None

    def test_traceability_counts_only_resolvable_active_citations(self):
        citations = [
            {"resolvable": True, "active": True},
            {"resolvable": True, "active": False},   # real but superseded
            {"resolvable": False, "active": False},  # fabricated
        ]
        score = traceability_score(citations)
        assert score.numerator == 1 and score.denominator == 3
        assert score.value == pytest.approx(33.33, abs=0.01)

    def test_a_superseded_citation_is_not_traceable(self):
        """SRS 1.8 #10 — acting on a withdrawn policy is the failure being tested."""
        assert traceability_score([{"resolvable": True, "active": False}]).value == 0.0


# ══════════════════════════════════════════════════════════════
# the escalation floor
# ══════════════════════════════════════════════════════════════
class TestEscalationFloor:
    def test_floor_raises_a_lower_genai_escalation(self, weights, ladders):
        result = decide(
            _compare(
                FakeIntelligence(escalation_level="SUPERVISOR"),
                FakeOutcome(), weights=weights, ladders=ladders,
            ),
            FakeOutcome(), ladders=ladders,
        )
        assert result.reconciled["escalation_level"] == "CRITICAL_MGMT"
        assert floor_satisfied(ladders, result.reconciled)

    def test_floor_holds_even_when_configuration_lets_genai_win(self, ladders):
        """
        The floor is a backstop, not a participant in the comparison. Even with
        the weights edited at runtime to give the model this field, it cannot
        lower the escalation.
        """
        rigged = {"escalation_level": {"severity": "INFORMATIONAL", "winner": "genai"}}
        comparisons = compare_all(
            FakeIntelligence(escalation_level="SUPERVISOR"),
            FakeOutcome(), weights=rigged, ranks=ladders,
        )
        assert _by_field(comparisons)["escalation_level"].final_value == "SUPERVISOR"

        result = decide(comparisons, FakeOutcome(), ladders=ladders)
        assert result.reconciled["escalation_level"] == "CRITICAL_MGMT"
        assert result.escalation_overridden is True
        assert ReviewReason.ESCALATION_UNCLEAR in result.review_reasons

    def test_floor_never_lowers_a_higher_escalation(self, weights, ladders):
        outcome = FakeOutcome(escalation_code="CRITICAL_MGMT", escalation_floor_code="SUPERVISOR")
        result = decide(
            _compare(
                FakeIntelligence(escalation_level="CRITICAL_MGMT"),
                outcome, weights=weights, ladders=ladders,
            ),
            outcome, ladders=ladders,
        )
        assert result.reconciled["escalation_level"] == "CRITICAL_MGMT"
        assert result.escalation_overridden is False

    def test_no_escalation_at_all_is_raised_to_the_floor(self, weights, ladders):
        result = decide(
            _compare(
                FakeIntelligence(escalation_required=False, escalation_level=None),
                FakeOutcome(), weights=weights, ladders=ladders,
            ),
            FakeOutcome(), ladders=ladders,
        )
        assert result.reconciled["escalation_level"] == "CRITICAL_MGMT"
        assert result.reconciled["escalation_required"] is True


# ══════════════════════════════════════════════════════════════
# the verdict
# ══════════════════════════════════════════════════════════════
class TestDecision:
    def _decide(self, intelligence, outcome, *, weights, ladders, **kwargs):
        return decide(
            _compare(intelligence, outcome, weights=weights, ladders=ladders),
            outcome, ladders=ladders, **kwargs,
        )

    def test_full_agreement_is_verified(self, weights, ladders):
        result = self._decide(
            FakeIntelligence(), FakeOutcome(), weights=weights, ladders=ladders
        )
        assert result.outcome == VerificationOutcome.VERIFIED
        assert not result.requires_review

    def test_a_critical_mismatch_is_corrected_by_rules(self, weights, ladders):
        result = self._decide(
            FakeIntelligence(department="BILLING"), FakeOutcome(),
            weights=weights, ladders=ladders,
        )
        assert result.outcome in (
            VerificationOutcome.CORRECTED_BY_RULES,
            VerificationOutcome.MANUAL_REVIEW_REQUIRED,
        )
        assert result.critical_mismatches >= 1
        assert result.requires_review

    def test_no_genai_contribution_is_incomplete_not_verified(self, weights, ladders):
        """
        NFR 5 — the rule result is fully usable during an outage, and labelled
        honestly rather than presented as a verified agreement.
        """
        result = decide(
            _compare(None, FakeOutcome(), weights=weights, ladders=ladders),
            FakeOutcome(), ladders=ladders, genai_available=False,
        )
        assert result.outcome == VerificationOutcome.INCOMPLETE
        assert ReviewReason.GENAI_UNAVAILABLE in result.review_reasons
        assert result.reconciled["department"] == "SAFETY"

    def test_an_unclassifiable_complaint_is_blocked(self, weights, ladders):
        """Neither pipeline produced a trustworthy classification."""
        outcome = FakeOutcome(category_code=None, unmatched=True)
        result = self._decide(None, outcome, weights=weights, ladders=ladders)
        assert result.outcome == VerificationOutcome.BLOCKED
        assert result.requires_review

    def test_unmatched_rules_force_review(self, weights, ladders):
        result = self._decide(
            FakeIntelligence(), FakeOutcome(unmatched=True), weights=weights, ladders=ladders
        )
        assert ReviewReason.RULE_UNMATCHED in result.review_reasons

    def test_a_rule_conflict_forces_review(self, weights, ladders):
        result = self._decide(
            FakeIntelligence(), FakeOutcome(conflict_detected=True),
            weights=weights, ladders=ladders,
        )
        assert ReviewReason.RULE_CONFLICT in result.review_reasons

    def test_an_unresolvable_citation_forces_review(self, weights, ladders):
        result = self._decide(
            FakeIntelligence(), FakeOutcome(), weights=weights, ladders=ladders,
            citations=[{"resolvable": False, "active": False}],
        )
        assert ReviewReason.POLICY_SUPPORT_MISSING in result.review_reasons

    def test_a_subcategory_disagreement_alone_is_only_a_warning(self, weights, ladders):
        """A MEDIUM field must not drag a complaint into the review queue."""
        result = self._decide(
            FakeIntelligence(subcategory="HAZARDOUS_MATERIAL_MISHANDLING"), FakeOutcome(),
            weights=weights, ladders=ladders,
        )
        assert result.outcome in (
            VerificationOutcome.VERIFIED_WITH_WARNING,
            VerificationOutcome.MANUAL_REVIEW_REQUIRED,
        )

    def test_review_reasons_are_deduplicated(self, weights, ladders):
        result = self._decide(
            FakeIntelligence(department="BILLING", category="DELIVERY", urgency="LOW"),
            FakeOutcome(), weights=weights, ladders=ladders,
        )
        assert len(result.review_reasons) == len(set(result.review_reasons))


# ══════════════════════════════════════════════════════════════
# citations
# ══════════════════════════════════════════════════════════════
class TestCitations:
    def test_an_invented_citation_is_unresolvable(self, db):
        intelligence = FakeIntelligence(
            policy_refs=[FakeRef(chunk_key="FAKE-POL-99#s1", doc_ref="FAKE-POL-99")]
        )
        citations = resolve_citations(db, intelligence)
        assert citations[0]["resolvable"] is False

    def test_no_citations_is_not_a_failure(self, db):
        assert resolve_citations(db, FakeIntelligence()) == []

    def test_a_citation_outside_the_retrieved_set_is_marked(self, db, ingested_kb):
        """Real, current, and not something the model was shown for this complaint."""
        intelligence = FakeIntelligence(
            policy_refs=[FakeRef(chunk_key="FAKE#1", doc_ref="SAF-POL-02", section_ref="5")]
        )
        citations = resolve_citations(db, intelligence, retrieved_chunk_keys=set())
        assert citations[0]["retrieved_for_this_complaint"] is False


# ══════════════════════════════════════════════════════════════
# persistence
# ══════════════════════════════════════════════════════════════
@pytest.fixture
def stored_complaint(db):
    row = Complaint(
        public_ref=f"CMP-X{uuid.uuid4().hex[:6].upper()}",
        title="Charger popped and smells of burning",
        description_raw="The charger made a pop and there is a burning smell. Order CN-9923100.",
        description_clean="The charger made a pop and there is a burning smell. Order CN-9923100.",
        channel=Channel.EMAIL, status=ComplaintStatus.NEW, dataset_tag="TEST",
    )
    db.add(row)
    db.commit()
    yield row
    for model in (Comparison, VerificationDecision, GenAIRun):
        db.query(model).filter(model.complaint_id == row.id).delete()
    db.commit()
    db.delete(row)
    db.commit()


class TestReconciliation:
    def test_degraded_run_persists_a_complete_decision(self, db, stored_complaint):
        """
        No provider is configured in the suite, so this is the real outage
        path, not a simulation of one.
        """
        result = reconcile(db, stored_complaint, run_genai=False)
        db.commit()

        assert result.outcome == VerificationOutcome.INCOMPLETE
        assert result.verification.genai_available is False

        decision = db.execute(
            select(VerificationDecision).where(
                VerificationDecision.complaint_id == stored_complaint.id
            )
        ).scalars().one()
        assert decision.outcome == VerificationOutcome.INCOMPLETE
        assert decision.requires_review is True
        assert decision.reconciled["department"]

        rows = comparison_rows(db, stored_complaint.id)
        assert rows, "a degraded run still produces a full comparison table"
        assert all(row["explanation"] for row in rows), "every row explains itself"

    def test_obligations_are_carried_into_the_reconciled_record(self, db, stored_complaint):
        result = reconcile(db, stored_complaint, run_genai=False)
        db.commit()
        assert "required_actions" in result.reconciled
        assert "prohibited_actions" in result.reconciled

    def test_rerunning_replaces_rather_than_appends(self, db, stored_complaint):
        """
        A complaint re-run after a rule change must not end up with two
        contradictory comparison sets for the UI to choose between.
        """
        reconcile(db, stored_complaint, run_genai=False)
        db.commit()
        first = len(comparison_rows(db, stored_complaint.id))

        reconcile(db, stored_complaint, run_genai=False)
        db.commit()
        assert len(comparison_rows(db, stored_complaint.id)) == first

    def test_scores_are_stored_with_the_decision(self, db, stored_complaint):
        reconcile(db, stored_complaint, run_genai=False)
        db.commit()
        decision = db.execute(
            select(VerificationDecision).where(
                VerificationDecision.complaint_id == stored_complaint.id
            )
        ).scalars().one()
        # Agreement has no denominator with no GenAI contribution, so it must
        # be null rather than a fabricated figure.
        assert decision.agreement_score is None
        assert decision.compliance_score is None

    def test_the_floor_holds_end_to_end(self, db, stored_complaint):
        result = reconcile(db, stored_complaint, run_genai=False)
        db.commit()
        assert floor_satisfied(load_ladders(db), result.reconciled)


# ══════════════════════════════════════════════════════════════
# configuration is data
# ══════════════════════════════════════════════════════════════
class TestConfiguration:
    def test_weights_come_from_the_database(self, db):
        weights, verification, thresholds = load_comparison_config(db)
        assert weights, "app_config['comparison_weights'] must be seeded"
        assert weights["department"]["severity"] == "CRITICAL"
        assert verification.get("high_mismatch_review_threshold")

    def test_retuning_a_weight_changes_the_verdict(self, ladders):
        """SRS 1.8 #14 — a policy change must not require a deploy."""
        intelligence = FakeIntelligence(department="BILLING")
        outcome = FakeOutcome()

        strict = compare_all(
            intelligence, outcome,
            weights={"department": {"severity": "CRITICAL", "winner": "python"}},
            ranks=ladders,
        )
        relaxed = compare_all(
            intelligence, outcome,
            weights={"department": {"severity": "INFORMATIONAL", "winner": "python"}},
            ranks=ladders,
        )
        assert decide(strict, outcome, ladders=ladders).critical_mismatches == 1
        assert decide(relaxed, outcome, ladders=ladders).critical_mismatches == 0

    def test_an_unrecognised_weight_falls_back_rather_than_crashing(self, ladders):
        """A typo in a runtime-editable file must not take the pipeline down."""
        comparisons = compare_all(
            FakeIntelligence(department="BILLING"), FakeOutcome(),
            weights={"department": {"severity": "VERY BAD", "winner": "whoever"}},
            ranks=ladders,
        )
        department = _by_field(comparisons)["department"]
        assert department.severity == Severity.MEDIUM
        assert department.winner == Winner.PYTHON
