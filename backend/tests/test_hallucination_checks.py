"""
Hallucination detection — citation validation and claim support.

Two different questions, tested separately: *does the source exist*, and *does
the source say it*.

The one that earns its keep is
:meth:`TestNumericGrounding.test_an_invented_figure_is_caught` — a reply
telling a customer the refund window is 30 days when the policy says 14 scores
almost perfectly on lexical overlap, because it reuses every word of the
source. Only the numeric check sees it, and a number given to a customer
becomes a commitment.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from hallucination_checks import (
    check_claims,
    containment,
    numbers_in,
    split_claims,
    trace,
    validate_all,
    validate_citation,
)
from hallucination_checks.citation_validator import persist, source_texts
from hallucination_checks.claim_support import best_sentence, score_claim
from src.db.enums import (
    Channel,
    ComplaintStatus,
    PolicyApplicability,
    PolicyRefSource,
)
from src.db.models import Complaint, ComplaintPolicyRef

POLICY = {
    "REF-POL-02::2::c1": (
        "Refunds are available for eligible purchases within 14 days of delivery. "
        "Items must be unused and in their original packaging. Opened consumable "
        "items are excluded from the refund policy."
    ),
    "REF-POL-02::5::c1": (
        "General merchandise 14 days. Large appliances 30 days. "
        "Opened consumables 7 days."
    ),
}


@pytest.fixture
def complaint(db):
    row = Complaint(
        public_ref=f"CMP-H{uuid.uuid4().hex[:6].upper()}",
        title="Refund query",
        description_raw="I would like a refund for order CN-5551200.",
        description_clean="I would like a refund for order CN-5551200.",
        channel=Channel.WEB, status=ComplaintStatus.NEW, dataset_tag="TEST",
    )
    db.add(row)
    db.commit()
    yield row
    db.query(ComplaintPolicyRef).filter(
        ComplaintPolicyRef.complaint_id == row.id
    ).delete()
    db.commit()
    db.delete(row)
    db.commit()


# ══════════════════════════════════════════════════════════════
# citation validation
# ══════════════════════════════════════════════════════════════
class TestCitationValidation:
    def test_an_invented_reference_is_unresolvable(self, db):
        verdict = validate_citation(db, doc_ref="FAKE-POL-99", section_ref="1")
        assert verdict.hallucinated
        assert not verdict.trustworthy
        assert "does not exist" in verdict.reason

    def test_a_real_active_policy_is_trustworthy(self, db, a_cited_document):
        doc_ref, _ = a_cited_document
        verdict = validate_citation(db, doc_ref=doc_ref)
        assert verdict.resolved and verdict.was_active
        assert verdict.applicability == PolicyApplicability.APPLICABLE
        assert verdict.trustworthy

    def test_an_empty_reference_is_rejected(self, db):
        verdict = validate_citation(db, doc_ref=None)
        assert verdict.hallucinated
        assert "No document reference" in verdict.reason

    def test_the_resolved_chunk_carries_its_location(self, db, a_cited_document):
        """The Source-Traceability answer needs more than "it exists"."""
        doc_ref, _ = a_cited_document
        verdict = validate_citation(db, doc_ref=doc_ref)
        assert verdict.chunk_key
        assert verdict.doc_version
        assert verdict.document_version_id is not None

    def test_sources_are_kept_apart(self, db, ingested_kb):
        report = validate_all(
            db,
            genai_refs=[{"doc_ref": "REF-POL-02"}],
            rule_refs=[{"doc_ref": "SAF-POL-02", "section_ref": "5"}],
        )
        assert len(report.by_source(PolicyRefSource.GENAI)) == 1
        assert len(report.by_source(PolicyRefSource.PYTHON)) == 1

    def test_traceability_measures_only_what_the_model_cited(self, db, ingested_kb):
        """
        Rule-required references are correct by construction. Counting them
        would dilute the score into flattery.
        """
        report = validate_all(
            db,
            genai_refs=[{"doc_ref": "FAKE-POL-99"}],
            rule_refs=[{"doc_ref": "REF-POL-02"}],
        )
        trustworthy, total = report.traceability()
        assert (trustworthy, total) == (0, 1)

    def test_the_same_document_from_two_sources_is_two_references(self, db, ingested_kb):
        """They are different claims about where the answer came from."""
        report = validate_all(
            db,
            genai_refs=[{"doc_ref": "REF-POL-02"}],
            rule_refs=[{"doc_ref": "REF-POL-02"}],
        )
        assert report.total == 2

    def test_the_same_reference_twice_from_one_source_is_one(self, db, ingested_kb):
        report = validate_all(
            db, genai_refs=[{"doc_ref": "REF-POL-02"}, {"doc_ref": "REF-POL-02"}]
        )
        assert report.total == 1


class TestCitationPersistence:
    def test_verdicts_are_written_and_readable_back(
        self, db, complaint, a_cited_document
    ):
        real_ref, _ = a_cited_document
        report = validate_all(
            db,
            genai_refs=[{"doc_ref": real_ref}, {"doc_ref": "FAKE-POL-99"}],
        )
        persist(db, complaint.id, report)
        db.commit()

        rows = trace(db, complaint.id)
        assert len(rows) == 2
        by_ref = {row["doc_ref"]: row for row in rows}
        assert by_ref[real_ref]["resolved"] is True
        assert by_ref["FAKE-POL-99"]["resolved"] is False
        assert by_ref["FAKE-POL-99"]["reason"]

    def test_rerunning_replaces_rather_than_appends(
        self, db, complaint, a_cited_document
    ):
        real_ref, _ = a_cited_document
        report = validate_all(db, genai_refs=[{"doc_ref": real_ref}])
        persist(db, complaint.id, report)
        db.commit()
        persist(db, complaint.id, report)
        db.commit()

        rows = db.execute(
            select(ComplaintPolicyRef).where(
                ComplaintPolicyRef.complaint_id == complaint.id
            )
        ).scalars().all()
        assert len(rows) == 1


# ══════════════════════════════════════════════════════════════
# claim splitting and scoping
# ══════════════════════════════════════════════════════════════
class TestClaims:
    def test_sentences_are_split_with_their_spans(self):
        text = "Refunds are available within 14 days. Items must be unused."
        claims = split_claims(text)
        assert len(claims) == 2
        for claim in claims:
            assert text[claim.start : claim.end] == claim.text

    def test_abbreviations_do_not_split_a_sentence(self):
        claims = split_claims("You were charged Rs. 42,500 twice for this order.")
        assert len(claims) == 1

    @pytest.mark.parametrize(
        "text",
        [
            "Thank you for contacting us.",
            "We are sincerely sorry for the inconvenience.",
            "We understand your frustration.",
            "Kind regards.",
        ],
    )
    def test_courtesies_are_not_claims(self, text):
        """A greeting is not unsupported; it is simply not a claim."""
        report = check_claims(text, POLICY)
        assert report.verdicts == []
        assert report.skipped >= 1

    def test_a_policy_statement_is_a_claim(self):
        assert split_claims("Refunds are available within 14 days.")[0].checkable

    def test_a_claim_about_money_moving_is_checkable(self):
        """A fabricated credit asserts as much as a claim about policy."""
        claim = split_claims("Your account has been credited with 500 points.")[0]
        assert claim.checkable

    def test_containment_measures_vocabulary_presence(self):
        assert containment(["refund", "days"], {"refund", "days", "policy"}) == 1.0
        assert containment(["refund", "days"], {"refund"}) == 0.5
        assert containment([], {"anything"}) == 0.0


class TestSupportScoring:
    def test_a_grounded_claim_passes(self):
        report = check_claims("Refunds are available within 14 days of delivery.", POLICY)
        assert not report.problems

    def test_a_fabricated_claim_is_flagged(self):
        report = check_claims(
            "Your account has been credited with a loyalty bonus of 500 points.", POLICY
        )
        assert report.problems
        assert not report.verdicts[0].supported

    def test_a_claim_with_no_source_at_all_is_unsupported(self):
        report = check_claims("Refunds are available within 14 days.", {})
        assert report.problems
        assert report.had_sources is False

    def test_the_verdict_names_the_chunk_it_scored_against(self):
        verdict = check_claims(
            "Refunds are available within 14 days of delivery.", POLICY
        ).verdicts[0]
        assert verdict.best_chunk_key in POLICY

    def test_grounding_reports_its_evidence(self):
        supported, checked = check_claims(
            "Refunds are available within 14 days of delivery.", POLICY
        ).grounding
        assert (supported, checked) == (1, 1)


# ══════════════════════════════════════════════════════════════
# what overlap cannot see
# ══════════════════════════════════════════════════════════════
class TestNumericGrounding:
    def test_an_invented_figure_is_caught(self):
        """
        "within 30 days" against a policy that says 14 reuses every word of
        the source and scores almost perfectly on overlap. Only this check
        sees it.
        """
        verdict = check_claims(
            "Refunds are available within 30 days of delivery.", POLICY
        ).verdicts[0]
        assert verdict.support_score > 0.7, "overlap alone would have passed it"
        assert verdict.unsupported_numbers
        assert verdict.problematic

    def test_a_figure_from_another_chunk_of_the_cited_document_is_fine(self):
        """
        A reply citing a whole policy may take its figure from a table several
        sections from the sentence it paraphrases.
        """
        report = check_claims("Large appliances allow 30 days.", POLICY)
        assert not report.problems

    def test_reference_numbers_are_not_treated_as_figures(self):
        """"REF-POL-02" is a citation, not a promise of two of anything."""
        assert numbers_in("REF-POL-02 applies") == []
        assert numbers_in("order CN-7732100") == []

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("within 14 days", ["14 days"]),
            ("30 business days", ["30 business days"]),
            ("a 5% fee", ["5%"]),
        ],
    )
    def test_commitments_are_extracted(self, text, expected):
        assert numbers_in(text) == expected


class TestNegationMismatch:
    def test_an_inverted_claim_is_caught(self):
        """
        "Refunds are NOT available within 14 days" against a policy that says
        they are. Identical vocabulary, opposite meaning — the failure overlap
        is blindest to.
        """
        verdict = check_claims(
            "Refunds are not available within 14 days of delivery.", POLICY
        ).verdicts[0]
        assert verdict.support_score > 0.7
        assert verdict.negation_mismatch
        assert verdict.supporting_sentence

    def test_a_correctly_negated_claim_is_not_flagged(self):
        """The policy does exclude opened consumables, so saying so is right."""
        report = check_claims(
            "Opened consumable items are excluded from the refund policy.", POLICY
        )
        assert not [v for v in report.verdicts if v.negation_mismatch]

    def test_polarity_is_compared_against_a_sentence_not_the_whole_chunk(self):
        """
        Any policy chunk contains an exclusion somewhere. Comparing against the
        whole chunk flagged correct claims and passed inverted ones — exactly
        backwards.
        """
        chunk = POLICY["REF-POL-02::2::c1"]
        claim = split_claims("Refunds are available within 14 days of delivery.")[0]
        sentence = best_sentence(claim, chunk)
        assert sentence is not None
        assert "excluded" not in sentence, "must match the affirmative line"

    def test_an_unrelated_sentence_is_not_used_for_polarity(self):
        claim = split_claims("Deliveries are dispatched on the next working day.")[0]
        assert best_sentence(claim, POLICY["REF-POL-02::2::c1"]) is None


# ══════════════════════════════════════════════════════════════
# source scoping
# ══════════════════════════════════════════════════════════════
class TestSourceScope:
    def test_a_document_citation_scores_against_the_whole_document(
        self, db, a_cited_document
    ):
        """
        Resolving a bare document reference returns its first chunk. Scoring a
        claim only against that would compare it to the policy's preamble.
        """
        doc_ref, chunk = a_cited_document
        citations = [
            {
                "doc_ref": doc_ref,
                "section_ref": None,
                "chunk_key": chunk.chunk_key,
                "resolvable": True,
                "active": True,
            }
        ]
        sources = source_texts(db, citations)
        assert len(sources) > 1, (
            "a bare document citation must widen to the whole document"
        )

    def test_a_section_citation_scores_against_that_section(self, db, a_cited_document):
        doc_ref, chunk = a_cited_document
        citations = [
            {
                "doc_ref": doc_ref,
                "section_ref": chunk.section_ref,
                "chunk_key": chunk.chunk_key,
                "resolvable": True,
                "active": True,
            }
        ]
        assert list(source_texts(db, citations)) == [chunk.chunk_key]

    def test_an_unresolvable_citation_contributes_no_source(self, db):
        citations = [{"doc_ref": "FAKE-POL-99", "resolvable": False, "active": False}]
        assert source_texts(db, citations) == {}


# ══════════════════════════════════════════════════════════════
# no model involved
# ══════════════════════════════════════════════════════════════
def test_hallucination_checks_never_call_a_provider():
    """
    A check that asked a model whether a model hallucinated would inherit the
    failure it exists to catch, and could not run during the outage where it
    matters most. Enforced structurally, like the Pipeline 2 restriction.
    """
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "hallucination_checks"
    forbidden = ("genai_pipeline.providers", "google.genai", "from google import genai",
                 "openai", "groq", "httpx")
    for path in root.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in source, f"{path.name} reaches a provider via {token}"


def test_score_claim_is_pure():
    """No database, no network — it takes text and returns a verdict."""
    claim = split_claims("Refunds are available within 14 days of delivery.")[0]
    verdict = score_claim(claim, POLICY, threshold=0.35)
    assert verdict.supported


# ══════════════════════════════════════════════════════════════
# policy claims vs process statements
# ══════════════════════════════════════════════════════════════
class TestClaimScoping:
    """
    The line between a useful finding and noise.

    No policy document describes what this company is currently doing, so a
    process statement always scores near zero against one. An earlier version
    accepted any sentence containing a business noun and duly reported "We
    take reports of duplicate charges very seriously" as an unsupported claim.
    """

    @pytest.mark.parametrize(
        "text",
        [
            "Refunds are available within 14 days of delivery.",
            "Our policy excludes opened consumable items.",
            "A 20% restocking fee applies.",
            "Your account has been credited with a bonus of 500 points.",
        ],
    )
    def test_policy_claims_and_figures_are_checked(self, text):
        assert split_claims(text)[0].checkable

    @pytest.mark.parametrize(
        "text",
        [
            "We have escalated your complaint internally.",
            "We take reports of duplicate charges very seriously.",
            "A specialist from our team will be in contact with you.",
            "We are currently verifying the transaction in our payment ledger.",
            "Your complaint has been escalated to our billing team for review.",
        ],
    )
    def test_process_statements_are_skipped(self, text):
        assert not split_claims(text)[0].checkable

    def test_a_figure_is_checked_even_inside_process_narration(self):
        """A wrong number outranks how the sentence is framed."""
        claim = split_claims("We will refund you within 30 days.")[0]
        assert claim.checkable

    def test_a_realistic_reply_produces_no_noise(self):
        """
        A well-written reply that cites nothing contentious must not fill the
        review queue with findings for politeness.
        """
        reply = (
            "Thank you for reporting this. I understand how concerning it must be "
            "to see two charges for your order. We take duplicate charges very "
            "seriously. Your complaint has been escalated internally to our "
            "specialist team. They are currently investigating the transaction "
            "in our payment ledger. A specialist will contact you with the outcome."
        )
        report = check_claims(reply, POLICY)
        assert report.verdicts == [], "no sentence here is a policy claim"
        assert report.skipped >= 5
