"""
The response guard and customer response generation.

Offline throughout: the guard is deterministic by design, and the response
pipeline is driven by scripted providers so the regeneration loop is measured
rather than hoped for.

The centrepiece is :class:`TestUnsupportedPromise` — SRS 1.8 #9. A model that
writes "your full refund has been approved" on a complaint where refund
eligibility is only ``REQUIRES_VERIFICATION`` must be stopped, and the rejected
draft must survive as evidence that it was.
"""

from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import select

from genai_pipeline.providers import ProviderChain
from genai_pipeline.providers.base import LLMProvider, LLMRequest, LLMResponse, RateLimited
from genai_pipeline.response import (
    choose_tone,
    drafts_for_complaint,
    generate_response,
    next_version,
    tidy,
)
from security.response_guard import (
    correction_instruction,
    detect_promises,
    eligibility_index,
    extract_citations,
    load_promise_patterns,
    scan_response,
)
from src.db.enums import (
    Channel,
    ComplaintStatus,
    GuardStatus,
    ResponseFlagType,
    ResponseTone,
    Severity,
)
from src.db.models import Complaint, GenAIRun, Response, ResponseFlag

RECONCILED = {
    "category": "BILLING",
    "department": "BILLING",
    "urgency": "MEDIUM",
    "escalation_required": False,
    "required_actions": ["Confirm the duplicate against the payment ledger"],
    "prohibited_actions": ["Confirm a refund before eligibility is verified"],
}


def eligibility(
    outcome: str,
    *,
    kind: str = "REFUND",
    approval: bool = False,
    ceiling: float | None = None,
    currency: str = "INR",
):
    return [
        {
            "eligibility_type": kind,
            "python_outcome": outcome,
            "rule_ref": "ELG-0001",
            "conditions_evaluated": ["Purchase date within the applicable refund window"],
            "requires_human_approval": approval,
            "max_amount": ceiling,
            "currency": currency,
        }
    ]


@pytest.fixture
def patterns(db):
    return load_promise_patterns(db)


# ══════════════════════════════════════════════════════════════
# detection primitives
# ══════════════════════════════════════════════════════════════
class TestDetection:
    def test_promise_patterns_are_seeded(self, patterns):
        assert patterns, "promise_patterns must be seeded"
        types = {promise_type for _, promise_type, _ in patterns}
        assert {"REFUND", "COMPENSATION", "REPLACEMENT", "TIMELINE", "EXCEPTION"} <= types

    def test_every_promise_type_names_a_real_eligibility_type(self, patterns):
        """
        An earlier draft named invented action codes that nothing emitted,
        which would have made every promise check vacuous.
        """
        from src.db.enums import EligibilityType

        valid = {member.value for member in EligibilityType}
        for _, promise_type, requires in patterns:
            if requires is None:
                assert promise_type == "TIMELINE"
            else:
                assert requires in valid, f"{promise_type} -> {requires}"

    @pytest.mark.parametrize(
        "text",
        [
            "Your full refund will be processed.",
            "We will definitely refund you.",
            "We guarantee a refund.",
            "Your refund is credited.",
        ],
    )
    def test_refund_promises_are_detected(self, text, patterns):
        found = detect_promises(text, patterns)
        assert any(p["promise_type"] == "REFUND" for p in found)

    def test_a_neutral_reply_promises_nothing(self, patterns):
        text = (
            "Thank you for reporting this. A specialist will review the transaction "
            "and contact you with the outcome."
        )
        assert detect_promises(text, patterns) == []

    def test_spans_point_at_the_matched_phrase(self, patterns):
        text = "Hello. Your full refund will be processed. Thanks."
        promise = detect_promises(text, patterns)[0]
        assert text[promise["start"] : promise["end"]] == promise["text"]

    def test_citations_are_extracted_from_prose(self):
        found = extract_citations("Under REF-POL-02 section 7 and DEL-POL-04, we can help.")
        refs = {c["doc_ref"] for c in found}
        assert refs == {"REF-POL-02", "DEL-POL-04"}
        assert found[0]["section_ref"] == "7"

    def test_an_order_reference_is_not_mistaken_for_a_citation(self):
        assert extract_citations("Your order CN-7732100 was charged twice.") == []


# ══════════════════════════════════════════════════════════════
# SRS 1.8 #9
# ══════════════════════════════════════════════════════════════
class TestUnsupportedPromise:
    PROMISE = "Good news — your full refund will be processed today."

    def test_eligible_permits_the_promise(self, db, patterns):
        report = scan_response(
            db, self.PROMISE, eligibility=eligibility("ELIGIBLE"), patterns=patterns
        )
        assert not [
            f for f in report.findings if f.flag_type == ResponseFlagType.UNSUPPORTED_PROMISE
        ]

    @pytest.mark.parametrize(
        "outcome", ["REQUIRES_VERIFICATION", "CONDITIONAL", "NOT_ELIGIBLE", "NOT_APPLICABLE"]
    )
    def test_anything_short_of_eligible_blocks_it(self, db, patterns, outcome):
        """
        CONDITIONAL and REQUIRES_VERIFICATION deliberately do not authorise a
        promise. A condition the agent has not yet checked is not a basis for
        telling a customer the answer is yes.
        """
        report = scan_response(
            db, self.PROMISE, eligibility=eligibility(outcome), patterns=patterns
        )
        assert report.status == GuardStatus.BLOCKED
        finding = next(
            f for f in report.findings if f.flag_type == ResponseFlagType.UNSUPPORTED_PROMISE
        )
        assert finding.severity == Severity.CRITICAL
        assert outcome in finding.explanation

    def test_an_amount_above_the_ceiling_blocks_a_genuinely_eligible_promise(
        self, db, patterns
    ):
        """
        The expensive one. Eligibility says yes, so the promise reads as
        authorised and every other gate passes -- only the number is wrong, and
        a number given to a customer is a commitment the company is held to.
        """
        report = scan_response(
            db,
            "Your compensation of Rs. 5,000 has been approved and will be credited.",
            eligibility=eligibility("ELIGIBLE", kind="COMPENSATION", ceiling=500),
            patterns=patterns,
        )

        finding = next(
            f for f in report.findings
            if f.flag_type == ResponseFlagType.UNSUPPORTED_PROMISE
        )
        assert finding.severity == Severity.CRITICAL
        assert "5,000.00" in finding.explanation
        assert "500.00" in finding.explanation
        assert finding.blocking_rule_ref == "ELG-0001"

    def test_an_amount_within_the_ceiling_passes(self, db, patterns):
        report = scan_response(
            db,
            "Your compensation of Rs. 450 has been approved and will be credited.",
            eligibility=eligibility("ELIGIBLE", kind="COMPENSATION", ceiling=500),
            patterns=patterns,
        )
        assert not [
            f for f in report.findings
            if f.flag_type == ResponseFlagType.UNSUPPORTED_PROMISE
        ]

    def test_the_ceiling_is_read_from_the_promise_sentence_only(self, db, patterns):
        """
        A reply that quotes the customer's disputed amount and then approves a
        smaller credit is correct. Comparing the largest number anywhere in the
        reply against the ceiling would flag it, and an agent who is flagged for
        correct replies stops reading the flags.
        """
        report = scan_response(
            db,
            "We understand Rs. 42,500 is in dispute and are still reviewing it. "
            "Separately, your compensation of Rs. 400 has been approved.",
            eligibility=eligibility("ELIGIBLE", kind="COMPENSATION", ceiling=500),
            patterns=patterns,
        )
        assert not [
            f for f in report.findings
            if f.flag_type == ResponseFlagType.UNSUPPORTED_PROMISE
        ]

    def test_an_eligibility_with_no_ceiling_is_not_second_guessed(self, db, patterns):
        """A rule that sets no cap has not set a cap of zero."""
        report = scan_response(
            db,
            "Your full refund of Rs. 42,500 will be processed today.",
            eligibility=eligibility("ELIGIBLE", ceiling=None),
            patterns=patterns,
        )
        assert not [
            f for f in report.findings
            if f.flag_type == ResponseFlagType.UNSUPPORTED_PROMISE
        ]

    def test_no_eligibility_at_all_blocks_it(self, db, patterns):
        report = scan_response(db, self.PROMISE, eligibility=[], patterns=patterns)
        assert report.status == GuardStatus.BLOCKED
        assert "no refund eligibility" in report.findings[0].explanation

    def test_eligible_but_needing_human_approval_blocks_it(self, db, patterns):
        report = scan_response(
            db, self.PROMISE,
            eligibility=eligibility("ELIGIBLE", approval=True), patterns=patterns,
        )
        assert report.status == GuardStatus.BLOCKED
        assert "human approval" in report.findings[0].explanation

    def test_the_wrong_eligibility_type_does_not_authorise(self, db, patterns):
        """A replacement approval is not a refund approval."""
        report = scan_response(
            db, self.PROMISE,
            eligibility=eligibility("ELIGIBLE", kind="REPLACEMENT"), patterns=patterns,
        )
        assert report.status == GuardStatus.BLOCKED

    def test_an_outright_promise_blocks(self, db, patterns):
        report = scan_response(
            db, "Your full refund has been approved.",
            eligibility=eligibility("REQUIRES_VERIFICATION"), patterns=patterns,
        )
        assert report.status == GuardStatus.BLOCKED
        assert report.findings[0].severity == Severity.CRITICAL

    @pytest.mark.parametrize(
        "sentence",
        [
            "If our investigation confirms the duplicate, a full refund will be processed.",
            "Once confirmed, your full refund will be processed.",
            "Subject to verification, a full refund will be processed.",
        ],
    )
    def test_a_hedged_promise_is_flagged_not_blocked(self, db, patterns, sentence):
        """
        "If we confirm it, a refund will be processed" does not tell the
        customer the refund is approved. It still reaches a reviewer, but
        blocking it would make the guard fire on correctly-written replies —
        and a guard that fires on correct output is one agents click past.
        """
        report = scan_response(
            db, sentence, eligibility=eligibility("REQUIRES_VERIFICATION"),
            patterns=patterns,
        )
        assert report.status == GuardStatus.FLAGGED
        promise = next(
            f for f in report.findings
            if f.flag_type == ResponseFlagType.UNSUPPORTED_PROMISE
        )
        assert promise.severity == Severity.MEDIUM
        assert "conditionally" in promise.explanation

    def test_a_hedge_in_an_earlier_sentence_does_not_excuse_a_later_promise(
        self, db, patterns
    ):
        """The hedge must govern the clause the promise sits in."""
        report = scan_response(
            db,
            "If you contact us we will help. Your full refund has been approved.",
            eligibility=eligibility("REQUIRES_VERIFICATION"), patterns=patterns,
        )
        assert report.status == GuardStatus.BLOCKED

    def test_the_finding_names_the_blocking_rule(self, db, patterns):
        report = scan_response(
            db, self.PROMISE,
            eligibility=eligibility("REQUIRES_VERIFICATION"), patterns=patterns,
        )
        assert report.findings[0].blocking_rule_ref == "ELG-0001"

    def test_the_span_lets_the_reviewer_see_the_phrase(self, db, patterns):
        report = scan_response(
            db, self.PROMISE, eligibility=eligibility("CONDITIONAL"), patterns=patterns
        )
        finding = report.findings[0]
        assert self.PROMISE[finding.span_start : finding.span_end] == finding.matched_text

    def test_a_timeline_without_a_citation_is_flagged(self, db, patterns):
        report = scan_response(
            db, "We will resolve this within 3 business days.",
            eligibility=eligibility("ELIGIBLE"), patterns=patterns,
        )
        assert any(
            f.promise_type == "TIMELINE" for f in report.findings
        ), "a committed date needs policy support"

    def test_an_exception_promise_needs_policy_exception_eligibility(self, db, patterns):
        report = scan_response(
            db, "We will make an exception for you on this occasion.",
            eligibility=eligibility("ELIGIBLE", kind="POLICY_EXCEPTION"), patterns=patterns,
        )
        assert not [
            f for f in report.findings if f.flag_type == ResponseFlagType.UNSUPPORTED_PROMISE
        ]


# ══════════════════════════════════════════════════════════════
# citations
# ══════════════════════════════════════════════════════════════
class TestCitationChecks:
    def test_an_invented_policy_reference_is_flagged(self, db, patterns):
        report = scan_response(
            db, "As set out in FAKE-POL-99, we cannot proceed.", patterns=patterns
        )
        assert any(
            f.flag_type == ResponseFlagType.INVALID_CITATION for f in report.findings
        )

    def test_a_real_active_policy_passes(self, db, patterns, a_cited_document):
        doc_ref, _ = a_cited_document
        report = scan_response(
            db, f"Our returns policy ({doc_ref}) sets out the window.",
            patterns=patterns,
        )
        assert not [
            f for f in report.findings
            if f.flag_type in (ResponseFlagType.INVALID_CITATION, ResponseFlagType.OUTDATED_POLICY)
        ]

    def test_an_uncited_policy_claim_is_flagged(self, db, patterns):
        report = scan_response(db, "Our policy does not allow this.", patterns=patterns)
        finding = next(
            f for f in report.findings if f.flag_type == ResponseFlagType.HALLUCINATION
        )
        assert finding.severity == Severity.MEDIUM

    def test_a_policy_claim_with_a_valid_citation_passes(
        self, db, patterns, a_cited_document
    ):
        doc_ref, _ = a_cited_document
        report = scan_response(
            db, f"Our policy ({doc_ref}) sets out the window.", patterns=patterns
        )
        assert not [
            f for f in report.findings if f.flag_type == ResponseFlagType.HALLUCINATION
        ]

    def test_declared_citations_are_checked_too(self, db, patterns):
        """A reference can arrive in the structured field without appearing in prose."""
        report = scan_response(
            db, "We have reviewed your complaint and will be in touch.",
            declared_citations=[{"doc_ref": "FAKE-POL-77", "section_ref": "1"}],
            patterns=patterns,
        )
        assert any(
            f.flag_type == ResponseFlagType.INVALID_CITATION for f in report.findings
        )


# ══════════════════════════════════════════════════════════════
# report mechanics
# ══════════════════════════════════════════════════════════════
class TestGuardReport:
    def test_a_clean_reply_is_clean(self, db, patterns):
        report = scan_response(
            db, "Thank you for letting us know. A specialist will contact you shortly.",
            reconciled=RECONCILED, patterns=patterns,
        )
        assert report.status == GuardStatus.CLEAN and report.clean

    def test_a_medium_finding_flags_without_blocking(self, db, patterns):
        report = scan_response(db, "Our policy does not allow this.", patterns=patterns)
        assert report.status == GuardStatus.FLAGGED
        assert not report.blocking_findings

    def test_nothing_checkable_yields_no_denominator(self, db, patterns):
        """A reply that promises and cites nothing gave the guard nothing to do."""
        report = scan_response(db, "Thank you for your message.", patterns=patterns)
        assert report.compliance == (0, 0)

    def test_required_actions_are_a_checklist_not_a_score(self, db, patterns):
        """
        Whether "verify the duplicate against the ledger" was done cannot be
        read off the reply, so it is surfaced for a human rather than guessed.
        """
        report = scan_response(
            db, "Thank you for your message.", reconciled=RECONCILED, patterns=patterns
        )
        assert len(report.required_action_checklist) == 1
        assert report.required_action_checklist[0]["confirmed"] is False
        assert report.compliance == (0, 0), "the checklist must not inflate the score"

    def test_eligibility_index_keys_by_type(self):
        index = eligibility_index(eligibility("ELIGIBLE"))
        assert index["REFUND"]["python_outcome"] == "ELIGIBLE"

    def test_correction_instruction_quotes_the_offending_phrase(self, db, patterns):
        report = scan_response(
            db, "Your full refund will be processed today.",
            eligibility=eligibility("REQUIRES_VERIFICATION"), patterns=patterns,
        )
        instruction = correction_instruction(report)
        assert "full refund" in instruction
        assert "REQUIRES_VERIFICATION" in instruction


# ══════════════════════════════════════════════════════════════
# text tidying
# ══════════════════════════════════════════════════════════════
class TestTidy:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("caused you.Your complaint", "caused you. Your complaint"),
            ("Thanks (really).Next step", "Thanks (really). Next step"),
            ("word   spaced", "word spaced"),
            ("a\n\n\n\nb", "a\n\nb"),
        ],
    )
    def test_artefacts_are_repaired(self, raw, expected):
        assert tidy(raw) == expected

    @pytest.mark.parametrize(
        "text",
        [
            "Rs. 42,500 was charged",
            "policy REF-POL-02.Section 5 applies",
            "A total of 3.5 days",
        ],
    )
    def test_references_and_numbers_are_left_alone(self, text):
        assert tidy(text) == text

    def test_no_character_is_ever_removed(self):
        """Tidying must not change meaning — the guard scans this exact text."""
        raw = "We refunded you.Then we did not."
        assert tidy(raw).replace(" ", "") == raw.replace(" ", "")


# ══════════════════════════════════════════════════════════════
# the response pipeline
# ══════════════════════════════════════════════════════════════
class ScriptedProvider(LLMProvider):
    """Returns each scripted reply in turn, recording the prompts it saw."""

    name = "scripted"

    def __init__(self, replies: list[str]):
        self._replies = list(replies)
        self.calls = 0
        self.prompts_seen: list[str] = []

    @property
    def model(self) -> str:
        return "scripted-1"

    def is_configured(self) -> bool:
        return True

    def _generate(self, request: LLMRequest) -> LLMResponse:
        self.prompts_seen.append(request.prompt)
        body = self._replies[min(self.calls, len(self._replies) - 1)]
        self.calls += 1
        return LLMResponse(
            text=body, provider=self.name, model=self.model,
            latency_ms=1, tokens_in=10, tokens_out=20,
        )


def reply(text: str, citations=None) -> str:
    return json.dumps(
        {
            "response_text": text,
            "tone": "PROFESSIONAL",
            "acknowledges_issue": True,
            "citations": citations or [],
        }
    )


CLEAN_REPLY = reply(
    "Thank you for reporting this. A specialist is reviewing the transaction and "
    "will contact you with the outcome."
)
PROMISING_REPLY = reply(
    "Thank you for reporting this. Your full refund will be processed and the "
    "money returned to your account."
)


@pytest.fixture
def complaint(db):
    row = Complaint(
        public_ref=f"CMP-R{uuid.uuid4().hex[:6].upper()}",
        title="Charged twice",
        description_raw="I was charged twice for order CN-7732100. I want a refund.",
        description_clean="I was charged twice for order CN-7732100. I want a refund.",
        order_ref="CN-7732100", channel=Channel.WEB,
        status=ComplaintStatus.NEW, dataset_tag="TEST",
    )
    db.add(row)
    db.commit()
    yield row
    for model in (ResponseFlag,):
        db.query(model).filter(
            model.response_id.in_(
                select(Response.id).where(Response.complaint_id == row.id)
            )
        ).delete(synchronize_session=False)
    db.query(Response).filter(Response.complaint_id == row.id).delete()
    db.query(GenAIRun).filter(GenAIRun.complaint_id == row.id).delete()
    db.commit()
    db.delete(row)
    db.commit()


def _run(db, complaint, replies, **kwargs):
    provider = ScriptedProvider(replies)
    result = generate_response(
        db, complaint,
        reconciled=kwargs.pop("reconciled", RECONCILED),
        chain=ProviderChain([provider], sleep=lambda _: None),
        **kwargs,
    )
    return result, provider


class TestResponseGeneration:
    def test_a_clean_draft_is_generated_and_stored(self, db, complaint):
        result, provider = _run(db, complaint, [CLEAN_REPLY])
        db.commit()

        assert result.ok and result.guard_status == GuardStatus.CLEAN
        assert result.sendable
        assert provider.calls == 1

        row = db.execute(
            select(Response).where(Response.complaint_id == complaint.id)
        ).scalars().one()
        assert row.version == 1
        assert row.draft_text == result.draft_text
        assert row.final_text is None, "a draft is not a sent reply"

    def test_a_blocked_draft_triggers_exactly_one_regeneration(self, db, complaint):
        """``REGENERATE_ONCE_THEN_REVIEW`` from policy.yaml."""
        result, provider = _run(
            db, complaint, [PROMISING_REPLY, CLEAN_REPLY],
            eligibility=eligibility("REQUIRES_VERIFICATION"),
        )
        db.commit()

        assert provider.calls == 2
        assert result.regenerations == 1
        assert result.guard_status == GuardStatus.CLEAN
        assert "full refund" in provider.prompts_seen[1], "the correction must be sent"

    def test_the_rejected_draft_survives_the_regeneration(self, db, complaint):
        """
        The SRS 1.8 #9 artefact. Once the clean replacement exists it is easy
        to keep only that, and then nothing shows the guard did anything —
        which is the one thing this whole mechanism exists to demonstrate.
        """
        result, _ = _run(
            db, complaint, [PROMISING_REPLY, CLEAN_REPLY],
            eligibility=eligibility("REQUIRES_VERIFICATION"),
        )
        db.commit()

        drafts = drafts_for_complaint(db, complaint.id)
        assert len(drafts) == 2, "the rejected draft must be stored, not overwritten"

        rejected, accepted = drafts
        assert rejected["guard_status"] == GuardStatus.BLOCKED
        assert "full refund" in rejected["draft_text"]
        assert rejected["flags"], "the flagged spans are kept with the rejected draft"
        assert accepted["guard_status"] == GuardStatus.CLEAN
        assert result.response_id is not None
        assert result.version == accepted["version"], "the result points at the final draft"

    def test_a_still_blocked_draft_is_kept_not_discarded(self, db, complaint):
        """
        The rejected draft is the SRS 1.8 #9 evidence. Dropping it would leave
        no record that the model tried to promise an unapproved refund.
        """
        result, provider = _run(
            db, complaint, [PROMISING_REPLY, PROMISING_REPLY],
            eligibility=eligibility("REQUIRES_VERIFICATION"),
        )
        db.commit()

        assert provider.calls == 2, "regeneration is bounded"
        assert result.ok, "the pipeline succeeded; the draft is what failed"
        assert result.guard_status == GuardStatus.BLOCKED
        assert not result.sendable and result.requires_review

        drafts = drafts_for_complaint(db, complaint.id)
        assert drafts and drafts[-1]["guard_status"] == GuardStatus.BLOCKED
        assert drafts[-1]["flags"], "the flagged spans are stored"

    def test_guard_flags_are_persisted_with_spans(self, db, complaint):
        result, _ = _run(
            db, complaint, [PROMISING_REPLY, PROMISING_REPLY],
            eligibility=eligibility("NOT_ELIGIBLE"),
        )
        db.commit()

        flags = db.execute(
            select(ResponseFlag).where(ResponseFlag.response_id == result.response_id)
        ).scalars().all()
        assert flags
        flag = flags[0]
        assert flag.flag_type == ResponseFlagType.UNSUPPORTED_PROMISE
        assert flag.span_start is not None and flag.span_end > flag.span_start
        assert flag.explanation

    def test_an_eligible_promise_is_not_regenerated(self, db, complaint):
        result, provider = _run(
            db, complaint, [PROMISING_REPLY], eligibility=eligibility("ELIGIBLE")
        )
        db.commit()
        assert provider.calls == 1
        assert result.guard_status == GuardStatus.CLEAN

    def test_drafts_are_versioned_not_overwritten(self, db, complaint):
        _run(db, complaint, [CLEAN_REPLY])
        db.commit()
        _run(db, complaint, [CLEAN_REPLY])
        db.commit()

        versions = [d["version"] for d in drafts_for_complaint(db, complaint.id)]
        assert versions == [1, 2]
        assert next_version(db, complaint.id) == 3

    def test_every_attempt_writes_a_response_pipeline_run(self, db, complaint):
        _run(db, complaint, [CLEAN_REPLY])
        db.commit()
        runs = db.execute(
            select(GenAIRun).where(GenAIRun.complaint_id == complaint.id)
        ).scalars().all()
        assert runs and all(r.pipeline == "RESPONSE" for r in runs)
        assert runs[0].prompt_name == "customer_response"

    def test_an_unverified_complaint_produces_no_reply(self, db, complaint):
        """Nothing was verified, so there is nothing safe to write from."""
        result, provider = _run(db, complaint, [CLEAN_REPLY], reconciled={})
        assert not result.ok
        assert result.failure_reason == "NOT_VERIFIED"
        assert provider.calls == 0, "no model call is made without a verified record"

    def test_invalid_json_is_retried_then_reported(self, db, complaint):
        result, provider = _run(db, complaint, ["not json at all", "still not json"])
        assert not result.ok
        assert result.failure_reason == "INVALID_OUTPUT"
        assert provider.calls == 2

    def test_a_total_outage_fails_without_inventing_a_reply(self, db, complaint):
        dead = ScriptedProvider([CLEAN_REPLY])
        dead._generate = lambda request: (_ for _ in ()).throw(  # noqa: SLF001
            RateLimited("429", provider="scripted")
        )
        result = generate_response(
            db, complaint, reconciled=RECONCILED,
            chain=ProviderChain([dead], max_retries=0, sleep=lambda _: None),
        )
        assert not result.ok
        assert result.failure_reason == "PROVIDERS_EXHAUSTED"
        assert result.draft_text == ""

    def test_no_provider_configured_is_reported_not_raised(self, db, complaint):
        result = generate_response(
            db, complaint, reconciled=RECONCILED, chain=ProviderChain([])
        )
        assert not result.ok
        assert result.failure_reason == "NO_PROVIDER_CONFIGURED"

    def test_the_prompt_fences_the_complaint(self, db, complaint):
        _, provider = _run(db, complaint, [CLEAN_REPLY])
        assert "<untrusted_complaint>" in provider.prompts_seen[0]

    def test_the_prompt_states_what_may_not_be_promised(self, db, complaint):
        _, provider = _run(
            db, complaint, [CLEAN_REPLY], eligibility=eligibility("REQUIRES_VERIFICATION")
        )
        sent = provider.prompts_seen[0]
        assert "REQUIRES_VERIFICATION" in sent
        assert "NOT yet approved" in sent


class TestTone:
    @pytest.mark.parametrize(
        ("urgency", "expected"),
        [
            ("CRITICAL", ResponseTone.EMPATHETIC),
            ("HIGH", ResponseTone.EMPATHETIC),
            ("MEDIUM", ResponseTone.PROFESSIONAL),
            ("LOW", ResponseTone.PROFESSIONAL),
        ],
    )
    def test_tone_follows_urgency_not_the_model(self, urgency, expected):
        """A safety incident answered breezily is a complaint of its own."""
        assert choose_tone({"urgency": urgency}) == expected

    def test_an_unknown_urgency_falls_back_to_professional(self):
        assert choose_tone({"urgency": "WHATEVER"}) == ResponseTone.PROFESSIONAL
        assert choose_tone({}) == ResponseTone.PROFESSIONAL
