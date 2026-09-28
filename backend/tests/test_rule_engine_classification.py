"""
How Pipeline 2 decides what a complaint is ABOUT.

Precedence orders the cases inside one subcategory by severity. Across
subcategories it only says which case would be more serious, so the
subcategory with the most evidence in the text decides the classification,
while urgency, priority and escalation are still resolved over every rule
that fired (a mandatory floor is never lost). A complaint that names only its
general topic ("where is my parcel") gets its category's routine case from a
fallback, and is still sent to a person to confirm.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from python_validation.pipeline import complaint_text
from python_validation.rule_engine import LoadedRule, evaluate_rules
from python_validation.signals import SignalHit, SignalSet, match_lexicon
from src.db.models import Complaint, Rule

ESCALATION = {"NONE": 0, "SUPERVISOR": 1, "DEPT_MANAGER": 2, "SPECIALIST": 3, "COMPLIANCE_REVIEW": 4, "CRITICAL_MGMT": 5}
PRIORITY = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}


def _signals(**terms: list[str]) -> SignalSet:
    signals = SignalSet()
    for key, words in terms.items():
        for i, word in enumerate(words):
            signals.add(SignalHit(signal_key=key, term=word, start=i, end=i + 1, text=word))
    return signals


def _evaluate(rules: list[LoadedRule], signals: SignalSet):
    return evaluate_rules(rules, signals, escalation_ranks=ESCALATION, priority_ranks=PRIORITY)


def _case(ref: str, signal: str, subcategory: str, *, precedence: int, department: str, urgency: str, **extra) -> LoadedRule:
    return LoadedRule(
        rule_ref=ref, name=ref, rule_type="CLASSIFICATION", precedence=precedence,
        conditions={"signal": signal}, category_code=extra.pop("category", "CAT"),
        subcategory_code=subcategory, department_code=department, urgency=urgency, **extra,
    )


@pytest.mark.unit
def test_the_subcategory_with_more_evidence_wins_over_a_more_severe_passing_mention():
    damaged = _case("RULE-019", "damaged_terms", "DAMAGED_PARCEL", precedence=60, department="WARRANTY_CLAIMS", urgency="LOW")
    partial = _case("RULE-018", "partial_terms", "PARTIAL_SHIPMENT_MISSING", precedence=69, department="LOGISTICS_OPS", urgency="HIGH")
    signals = _signals(damaged_terms=["shattered", "broken", "cracked"], partial_terms=["pieces"])

    outcome = _evaluate([damaged, partial], signals)

    assert outcome.subcategory_code == "DAMAGED_PARCEL"
    assert outcome.department_code == "WARRANTY_CLAIMS", "the department follows what the complaint is about"
    assert outcome.urgency == "HIGH", "severity is still resolved over every rule that fired"
    assert not outcome.conflict_detected, "a clear evidence margin is not a conflict"


@pytest.mark.unit
def test_within_one_subcategory_the_more_specific_case_still_wins_by_precedence():
    routine = _case("RULE-004", "missed_terms", "MISSED_DELIVERY_ATTEMPT", precedence=60, department="LOGISTICS_OPS", urgency="LOW")
    fake = LoadedRule(
        rule_ref="RULE-005", name="fake attempt", rule_type="CLASSIFICATION", precedence=66,
        conditions={"all_of": [{"signal": "missed_terms"}, {"signal": "rule_005_evidence"}]},
        category_code="DELIVERY", subcategory_code="MISSED_DELIVERY_ATTEMPT",
        department_code="LOGISTICS_OPS", support_department_code="ACCOUNT_SECURITY", urgency="HIGH",
    )
    outcome = _evaluate([routine, fake], _signals(missed_terms=["no one came"], rule_005_evidence=["fake"]))
    assert outcome.urgency == "HIGH"
    assert outcome.support_department_code == "ACCOUNT_SECURITY"


@pytest.mark.unit
def test_an_even_split_is_recorded_as_a_conflict_for_a_person():
    a = _case("RULE-031", "dup_terms", "DUPLICATE_CHARGE", precedence=60, department="BILLING", urgency="MEDIUM")
    b = _case("RULE-001", "delay_terms", "DELAYED_DELIVERY", precedence=60, department="LOGISTICS_OPS", urgency="MEDIUM")
    outcome = _evaluate([a, b], _signals(dup_terms=["charged twice"], delay_terms=["late"]))
    assert outcome.conflict_detected
    assert any(c.field_name == "subcategory_code" for c in outcome.conflicts)


@pytest.mark.unit
def test_a_losing_case_cannot_take_the_department_but_its_floor_still_applies():
    delay = _case("RULE-001", "delay_terms", "DELAYED_DELIVERY", precedence=60, department="LOGISTICS_OPS", urgency="MEDIUM")
    fraud = _case("RULE-022", "wrong_item_terms", "WRONG_ITEM_DELIVERED", precedence=66, department="ACCOUNT_SECURITY", urgency="HIGH")
    fraud_floor = LoadedRule(
        rule_ref="ESC-022", name="floor", rule_type="ESCALATION", precedence=103,
        conditions={"signal": "wrong_item_terms"}, is_mandatory_escalation=True,
        escalation_code="SUPERVISOR", department_code="ACCOUNT_SECURITY", urgency="HIGH",
    )
    signals = _signals(delay_terms=["late", "overdue", "still not received"], wrong_item_terms=["swapped"])

    outcome = _evaluate([delay, fraud, fraud_floor], signals)

    assert outcome.subcategory_code == "DELAYED_DELIVERY"
    assert outcome.department_code == "LOGISTICS_OPS"
    assert outcome.escalation_floor_code == "SUPERVISOR", "a mandatory floor is never lost to classification"


def _fallback(ref: str, signal: str, category: str, subcategory: str) -> LoadedRule:
    return LoadedRule(
        rule_ref=ref, name=ref, rule_type="CLASSIFICATION", precedence=8, is_catch_all=True,
        conditions={"signal": signal}, category_code=category, subcategory_code=subcategory,
        department_code="LOGISTICS_OPS", urgency="MEDIUM", priority_code="P2",
    )


@pytest.mark.unit
def test_a_vague_complaint_gets_its_categorys_routine_case_and_still_goes_to_a_person():
    fallback = _fallback("CFB-DELIVERY", "delivery_inquiry_terms", "DELIVERY", "DELAYED_DELIVERY")
    outcome = _evaluate([fallback], _signals(delivery_inquiry_terms=["where is my parcel"]))
    assert outcome.category_code == "DELIVERY"
    assert outcome.subcategory_code == "DELAYED_DELIVERY"
    assert outcome.unmatched, "a category-level guess is confirmed by a person"


@pytest.mark.unit
def test_a_fallback_names_the_category_when_only_a_cross_cutting_rule_fired():
    safety_floor = LoadedRule(
        rule_ref="ESC-SAF-0001", name="safety", rule_type="ESCALATION", precedence=120,
        conditions={"signal": "injury_mention"}, is_mandatory_escalation=True, escalation_code="CRITICAL_MGMT",
    )
    fallback = _fallback("CFB-SAFETY", "injury_mention", "SAFETY", "RECKLESS_DRIVING_SAFETY_RISK")
    outcome = _evaluate([safety_floor, fallback], _signals(injury_mention=["injured"]))
    assert outcome.category_code == "SAFETY"
    assert outcome.escalation_code == "CRITICAL_MGMT"
    assert outcome.unmatched


@pytest.mark.unit
def test_a_fallback_never_overrides_a_real_classification():
    real = _case("RULE-019", "damaged_terms", "DAMAGED_PARCEL", precedence=60, department="WARRANTY_CLAIMS", urgency="LOW", category="PRODUCT_DEFECT")
    fallback = _fallback("CFB-DELIVERY", "delivery_inquiry_terms", "DELIVERY", "DELAYED_DELIVERY")
    signals = _signals(damaged_terms=["broken"], delivery_inquiry_terms=["where is my parcel", "not received my parcel"])
    outcome = _evaluate([real, fallback], signals)
    assert outcome.category_code == "PRODUCT_DEFECT"
    assert not outcome.unmatched


@pytest.mark.unit
def test_a_phrase_matches_whole_words_only():
    lexicon = [("safety_lexicon_hit", "on fire", "PHRASE", 3.0)]
    assert not match_lexicon("Our application firewalls blocked the tracking page.", lexicon)
    assert match_lexicon("The van was on fire outside the hub.", lexicon)
    assert match_lexicon("The van was on\nfire outside the hub.", lexicon), "line breaks inside a phrase still match"


@pytest.mark.unit
def test_the_rules_read_the_title_as_well_as_the_body():
    complaint = Complaint(title="Package stolen after courier left it at the gate", description_raw="Please call me back.")
    text = complaint_text(complaint)
    assert "stolen" in text and "call me back" in text
    repeated = Complaint(title="Late parcel", description_raw="Late parcel - it is three days overdue.")
    assert complaint_text(repeated).count("Late parcel") == 1, "a body that starts with the title is not doubled"


@pytest.mark.integration
def test_the_loader_keeps_what_the_matrix_says_about_follow_ups_and_escalation(db):
    follow_ups = db.execute(select(Rule).where(Rule.follow_up_required.is_(True))).scalars().all()
    assert follow_ups, "the matrix marks cases follow_up_required; the loader used to drop every one"

    # Not mandatory, so no floor -- but the case's own escalation is its outcome.
    rude_rider = db.execute(select(Rule).where(Rule.rule_ref == "RULE-067")).scalars().one()
    assert rude_rider.outcome_escalation_code == "SUPERVISOR"
    assert not rude_rider.is_mandatory_escalation

    fallbacks = db.execute(select(Rule).where(Rule.rule_ref.like("CFB-%"))).scalars().all()
    assert fallbacks and all(rule.is_catch_all for rule in fallbacks)
