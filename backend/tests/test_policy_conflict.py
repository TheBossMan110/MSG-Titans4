"""
Contradictory policy detection (SRS 1.8 #10).

The test that matters most is
:meth:`TestDetection.test_a_contradiction_is_recorded_not_silently_resolved`.
Retrieval and precedence already made the system follow the higher policy. What
was missing was any record that it had *noticed* the lower one — and a system
that quietly follows the right policy looks identical to one that never saw the
wrong one.

The second most important is
:meth:`TestFalsePositives.test_two_policies_that_agree_are_not_a_conflict`.
A detector that fires on agreeing policies floods the trace view, and an agent
who dismisses findings stops reading them.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from hallucination_checks import policy_conflict
from hallucination_checks.claim_support import content_words
from hallucination_checks.policy_conflict import (
    FIGURE,
    NEGATION,
    Contradiction,
    _disagreement,
    _same_subject,
)

FLOOR = policy_conflict.DEFAULT_SUBJECT_FLOOR


def words(text: str) -> list[str]:
    return content_words(text)


# ══════════════════════════════════════════════════════════════
# what counts as the same subject
# ══════════════════════════════════════════════════════════════
class TestSubjectMatch:
    def test_two_sentences_about_the_same_rule_match(self):
        a = "Refunds for damaged goods are issued within 14 business days of return."
        b = "Refunds for damaged goods are issued within 30 business days of return."
        assert _same_subject(words(a), words(b), FLOOR) > 0

    def test_two_sentences_about_different_rules_do_not(self):
        a = "Refunds for damaged goods are issued within 14 business days."
        b = "Engineers attend safety incidents at the customer address within 4 hours."
        assert _same_subject(words(a), words(b), FLOOR) == 0

    def test_containment_is_checked_both_ways(self):
        """
        A one-way test matches a short sentence against a long one that merely
        happens to contain its words. Those are not about the same thing.
        """
        short = "Refunds are issued promptly."
        long = (
            "Refunds are issued promptly for damaged goods, for goods that fail "
            "within the warranty window, for duplicate charges arising from a "
            "payment gateway retry, and for cancelled orders where dispatch has "
            "not yet occurred under section 9 of the returns policy."
        )
        # Every word of the short sentence is in the long one, so a one-way
        # test would score 1.0.
        from hallucination_checks.claim_support import containment

        assert containment(words(short), set(words(long))) > FLOOR
        assert _same_subject(words(short), words(long), FLOOR) == 0

    def test_a_very_short_sentence_is_never_a_subject_match(self):
        """"This is not permitted." would otherwise match almost any negation."""
        assert _same_subject(words("This is not permitted."), words("This is permitted."), FLOOR) == 0


# ══════════════════════════════════════════════════════════════
# what counts as a disagreement
# ══════════════════════════════════════════════════════════════
class TestDisagreement:
    def test_opposite_polarity_is_a_negation_conflict(self):
        a = "Refunds for opened software licences are permitted under this policy."
        b = "Refunds for opened software licences are not permitted under this policy."
        found = _disagreement(a, b)
        assert found is not None
        assert found[0] == NEGATION

    def test_different_figures_in_the_same_unit_are_a_figure_conflict(self):
        a = "Returns are accepted within 14 days of delivery."
        b = "Returns are accepted within 30 days of delivery."
        found = _disagreement(a, b)
        assert found is not None
        assert found[0] == FIGURE
        assert "14" in found[1] and "30" in found[1]

    def test_the_same_figure_is_not_a_conflict(self):
        a = "Returns are accepted within 14 days of delivery."
        b = "Returns are accepted within 14 days of the delivery date."
        assert _disagreement(a, b) is None

    def test_figures_in_different_units_are_not_compared(self):
        """
        14 days against Rs. 14 is not a disagreement, and comparing raw numbers
        without their units would report one.
        """
        a = "Returns are accepted within 14 days of delivery."
        b = "A handling charge of Rs. 14 applies to returns of delivery."
        found = _disagreement(a, b)
        assert found is None or found[0] != FIGURE

    def test_two_sentences_that_simply_agree_are_not_a_conflict(self):
        a = "Refunds for damaged goods are issued within 14 business days."
        b = "Refunds for damaged goods are issued within 14 business days."
        assert _disagreement(a, b) is None


# ══════════════════════════════════════════════════════════════
# the recorded outcome
# ══════════════════════════════════════════════════════════════
class TestContradiction:
    def test_the_reason_names_both_policies_and_the_governing_tier(self):
        """
        An agent reading this has to be able to act on it without opening the
        detector's source.
        """
        contradiction = Contradiction(
            kind=FIGURE,
            winner_ref="REF-POL-02",
            overruled_ref="OPS-SOP-11",
            winning_tier="ACTIVE_POLICY",
            overruled_tier="DEPARTMENT_SOP",
            winner_sentence="Returns are accepted within 14 days.",
            overruled_sentence="Returns are accepted within 30 days.",
            overlap=0.88,
            detail="different days: 14 against 30",
        )
        reason = contradiction.reason

        assert "REF-POL-02" in reason
        assert "OPS-SOP-11" in reason
        assert "ACTIVE_POLICY" in reason
        assert "governs" in reason

    def test_an_empty_report_reports_no_rate_rather_than_zero(self):
        """
        Nothing compared is not the same as compared and clean. SRS 1.8 #17:
        a percentage with no denominator is null, never 0.
        """
        report = policy_conflict.ConflictReport()
        assert report.summary()["conflict_rate"] is None
        assert not report.detected


# ══════════════════════════════════════════════════════════════
# against the database
# ══════════════════════════════════════════════════════════════
class TestDetection:
    def test_one_document_is_never_a_conflict(self, db, ingested_kb):
        """A policy cannot contradict itself across two citations of itself."""
        import uuid

        report = policy_conflict.detect(db, uuid.uuid4())
        assert not report.detected
        assert report.pairs_compared == 0

    def test_a_contradiction_is_recorded_not_silently_resolved(
        self, db, contradicting_corpus
    ):
        """
        The point of the whole module. Precedence already decides which policy
        wins; without this the record shows only the winner, and a system that
        quietly follows the right policy is indistinguishable from one that
        never saw the wrong one.
        """
        complaint_id, high_ref, low_ref = contradicting_corpus

        report = policy_conflict.check(db, complaint_id)
        db.commit()

        assert report.detected, "the planted contradiction must be found"
        contradiction = report.contradictions[0]
        assert contradiction.winner_ref == high_ref
        assert contradiction.overruled_ref == low_ref

        recorded = policy_conflict.conflicts_for(db, complaint_id)
        assert recorded
        assert recorded[0]["overruled_ref"] == low_ref
        assert recorded[0]["governed_by_ref"] == high_ref

    def test_the_overruled_reference_is_kept(self, db, contradicting_corpus):
        """
        Deleting the loser would leave no evidence the conflict was ever
        detected, which is exactly what the challenge checks for.
        """
        from sqlalchemy import select

        from src.db.models import ComplaintPolicyRef

        complaint_id, _, low_ref = contradicting_corpus
        policy_conflict.check(db, complaint_id)
        db.commit()

        still_there = db.execute(
            select(ComplaintPolicyRef).where(
                ComplaintPolicyRef.complaint_id == complaint_id,
                ComplaintPolicyRef.doc_ref == low_ref,
            )
        ).scalars().first()

        assert still_there is not None
        assert still_there.conflict_with_ref is not None

    def test_running_twice_does_not_stack_the_reason(self, db, contradicting_corpus):
        """Re-analysis must not append the same explanation four times."""
        from sqlalchemy import select

        from src.db.models import ComplaintPolicyRef

        complaint_id, _, low_ref = contradicting_corpus

        policy_conflict.check(db, complaint_id)
        db.commit()
        first = db.execute(
            select(ComplaintPolicyRef).where(
                ComplaintPolicyRef.complaint_id == complaint_id,
                ComplaintPolicyRef.doc_ref == low_ref,
            )
        ).scalars().first().reason

        policy_conflict.check(db, complaint_id)
        db.commit()
        db.expire_all()
        second = db.execute(
            select(ComplaintPolicyRef).where(
                ComplaintPolicyRef.complaint_id == complaint_id,
                ComplaintPolicyRef.doc_ref == low_ref,
            )
        ).scalars().first().reason

        assert first == second, "the reason must not grow on every re-analysis"

    def test_the_threshold_is_configurable(self, db):
        """Retunable without a deploy, like every other threshold."""
        assert 0.0 < policy_conflict.subject_floor(db) <= 1.0


# ══════════════════════════════════════════════════════════════
# not crying wolf
# ══════════════════════════════════════════════════════════════
class TestFalsePositives:
    def test_two_policies_that_agree_are_not_a_conflict(self, db, agreeing_corpus):
        """
        A detector that fires on agreeing policies floods the trace view, and
        an agent who dismisses findings stops reading them.
        """
        complaint_id = agreeing_corpus
        report = policy_conflict.check(db, complaint_id)
        db.commit()

        assert not report.detected, [c.as_dict() for c in report.contradictions]
        assert report.pairs_compared > 0, "the pair must actually have been compared"

    def test_an_unresolved_citation_is_not_treated_as_a_policy(
        self, db, hallucinated_corpus
    ):
        """
        An unresolvable reference is a hallucination, already recorded as one.
        Treating it as a contradicting policy would blame a real document for
        disagreeing with one that does not exist.
        """
        complaint_id = hallucinated_corpus
        report = policy_conflict.detect(db, complaint_id)
        assert report.documents_compared <= 1
        assert not report.detected




# ══════════════════════════════════════════════════════════════
# fixtures
# ══════════════════════════════════════════════════════════════
#
# Each fixture plants its own documents with references unique to the test, and
# removes them afterwards. `documents.family_key` is unique, so two tests
# sharing a reference collide -- and a fixture that leaves rows behind makes
# the next test's failure look like a detector bug.
REFUND_14 = (
    "Refunds for damaged consumer electronics are issued within 14 business "
    "days of the returned item being received at the warehouse."
)
REFUND_30 = (
    "Refunds for damaged consumer electronics are issued within 30 business "
    "days of the returned item being received at the warehouse."
)


@pytest.fixture
def corpus(db):
    """
    Plants policy documents and the complaint that cites them.

    Yields ``plant(*(doc_type, text))`` which returns the generated doc_refs,
    plus the complaint id, so a test states only what its documents *say*.
    """
    import hashlib
    import uuid as _uuid

    from sqlalchemy import delete

    from complaint_processing.intake import next_public_ref
    from src.db.enums import (
        ComplaintStatus,
        DocStatus,
        PolicyApplicability,
        PolicyRefSource,
    )
    from src.db.models import (
        Chunk,
        Complaint,
        ComplaintPolicyRef,
        Document,
        DocumentVersion,
    )

    tag = _uuid.uuid4().hex[:8].upper()
    complaint = Complaint(
        public_ref=next_public_ref(db),
        title="Policy conflict fixture",
        description_raw="Fixture complaint for policy conflict detection.",
        description_clean="Fixture complaint for policy conflict detection.",
        status=ComplaintStatus.NEW,
        channel="WEB",
        dataset_tag=f"conflict-{tag}",
    )
    db.add(complaint)
    db.flush()

    planted: list[Document] = []

    def plant(*documents, resolved: bool = True) -> list[str]:
        refs: list[str] = []
        for index, (doc_type, text) in enumerate(documents):
            ref = f"{tag}-{doc_type[:3]}-{index:02d}"
            refs.append(ref)

            document = Document(
                family_key=ref.lower(), title=f"{ref} fixture", doc_type=doc_type
            )
            db.add(document)
            db.flush()
            planted.append(document)

            version = DocumentVersion(
                document_id=document.id,
                doc_ref=ref,
                version="1.0",
                title=f"{ref} fixture",
                status=DocStatus.ACTIVE,
                file_format="PDF",
                file_name=f"{ref}.pdf",
                file_path=f"fixture/{ref}.pdf",
                file_hash=hashlib.sha256(f"{ref}{text}".encode()).hexdigest(),
            )
            db.add(version)
            db.flush()

            db.add(
                Chunk(
                    document_version_id=version.id,
                    chunk_key=f"{ref}#1",
                    doc_ref=ref,
                    doc_version="1.0",
                    section_ref="1",
                    ordinal=0,
                    text=text,
                )
            )
            db.add(
                ComplaintPolicyRef(
                    complaint_id=complaint.id,
                    source=PolicyRefSource.GENAI,
                    doc_ref=ref,
                    doc_version="1.0",
                    chunk_key=f"{ref}#1",
                    document_version_id=version.id,
                    resolved=resolved,
                    was_active=resolved,
                    applicability=PolicyApplicability.APPLICABLE,
                )
            )
        db.flush()
        return refs

    def cite_nothing(ref: str) -> None:
        """A citation that resolves to no document at all."""
        db.add(
            ComplaintPolicyRef(
                complaint_id=complaint.id,
                source=PolicyRefSource.GENAI,
                doc_ref=ref,
                resolved=False,
                was_active=False,
                applicability=PolicyApplicability.NOT_APPLICABLE,
                reason="No such document.",
            )
        )
        db.flush()

    plant.complaint_id = complaint.id
    plant.cite_nothing = cite_nothing
    yield plant

    version_ids = [
        v.id
        for document in planted
        for v in db.execute(
            select(DocumentVersion).where(DocumentVersion.document_id == document.id)
        ).scalars()
    ]
    db.execute(delete(ComplaintPolicyRef).where(
        ComplaintPolicyRef.complaint_id == complaint.id
    ))
    if version_ids:
        db.execute(delete(Chunk).where(Chunk.document_version_id.in_(version_ids)))
        db.execute(delete(DocumentVersion).where(DocumentVersion.id.in_(version_ids)))
    for document in planted:
        db.execute(delete(Document).where(Document.id == document.id))
    db.execute(delete(Complaint).where(Complaint.id == complaint.id))
    db.commit()


@pytest.fixture
def contradicting_corpus(corpus):
    """An active policy and a department SOP that disagree on the same window."""
    high, low = corpus(("POLICY", REFUND_14), ("SOP", REFUND_30))
    return corpus.complaint_id, high, low


@pytest.fixture
def agreeing_corpus(corpus):
    """Two policies covering the same ground and saying the same thing."""
    corpus(("POLICY", REFUND_14), ("SOP", REFUND_14))
    return corpus.complaint_id


@pytest.fixture
def hallucinated_corpus(corpus):
    """One real policy and one citation that resolves to nothing."""
    corpus(("POLICY", REFUND_14))
    corpus.cite_nothing("INVENTED-POL-99")
    return corpus.complaint_id
