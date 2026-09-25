"""
Resolution validation, follow-up scheduling and escalation notes.

The test that matters most is
:meth:`TestResolutionValidation.test_a_rule_obligation_is_never_satisfied_automatically`.
Whether "verify the shipment status in the tracking system" actually happened
is not readable from any text the system holds. A checklist that inferred it
would be decorative, and the checklist is the thing standing between a safety
obligation and being skipped.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, select

from complaint_processing import followup
from complaint_processing.intake import submit
from python_validation import resolution
from src.db.enums import ResolutionStepSource, ResolutionStepStatus
from src.db.models import (
    AgentGuidance,
    ClarificationQuestion,
    Comparison,
    Complaint,
    ComplaintEntity,
    ComplaintLink,
    ComplaintPolicyRef,
    ComplaintValidationIssue,
    Customer,
    EligibilityDecision,
    Escalation,
    FollowUp,
    GenAIRun,
    ResolutionStep,
    ReviewAction,
    ReviewQueueItem,
    SLAEvent,
    User,
    ValidationRun,
    VerificationDecision,
)

SAFETY = (
    "The parcel you delivered made a loud pop and there is a burning smell "
    "from the plug. I unplugged it immediately. Order CN-9923190."
)
BILLING = (
    "I was charged twice for order CN-7788990. Rs. 42,500 left my account on two "
    "separate occasions and I would like the duplicate refunded."
)


@pytest.fixture
def clean(db):
    def _purge():
        for model in (
            FollowUp, ReviewAction, ReviewQueueItem, SLAEvent, Escalation,
            Comparison, VerificationDecision, GenAIRun, ComplaintLink,
            ComplaintEntity, ComplaintValidationIssue, ComplaintPolicyRef,
            ResolutionStep, AgentGuidance, ClarificationQuestion,
            EligibilityDecision,
        ):
            db.execute(delete(model))
        db.execute(delete(ValidationRun))
        db.execute(delete(Complaint))
        db.execute(delete(Customer))
        db.commit()

    _purge()
    yield
    _purge()


@pytest.fixture
def agent(db):
    return db.execute(
        select(User).where(User.email == "agent.billing@raftarxpress.com")
    ).scalars().one()


def _file(db, description=SAFETY, **overrides):
    payload = {
        "title": "Complaint",
        "description": description,
        "customer_email": "completion@example.com",
        "order_ref": "CN-9923190",
        "run_genai": False,
    }
    payload.update(overrides)
    result = submit(db, **payload)
    db.commit()
    return result


# ══════════════════════════════════════════════════════════════
# resolution validation
# ══════════════════════════════════════════════════════════════
class TestResolutionValidation:
    def test_rule_obligations_become_a_checklist(self, db, clean):
        complaint = _file(db).complaint
        report = resolution.classify(db, complaint.id)
        db.commit()

        assert report.required, "a safety complaint carries obligations"
        assert all(
            v.status == ResolutionStepStatus.MISSING for v in report.required
        )
        assert not report.complete

    def test_a_rule_obligation_is_never_satisfied_automatically(self, db, clean):
        """
        Whether the obligation was actually carried out is not readable from
        anything the system holds. A checklist that ticked itself would be
        decorative, and it is what stops a safety step being skipped.
        """
        complaint = _file(db).complaint

        for _ in range(3):
            report = resolution.classify(db, complaint.id)
            db.commit()

        confirmed, required = report.coverage()
        assert required > 0
        assert confirmed == 0, "re-running must never confirm anything"

    def test_an_agent_can_confirm_one(self, db, clean, agent):
        complaint = _file(db).complaint
        report = resolution.classify(db, complaint.id)
        db.commit()

        step = report.required[0]
        resolution.confirm(db, step.step_id, agent)
        db.commit()

        after = resolution.classify(db, complaint.id)
        db.commit()
        assert len(after.confirmed) == 1
        assert agent.email in after.confirmed[0].reason

    def test_confirming_survives_a_re_run(self, db, clean, agent):
        """A re-analysis after a rule change must not undo an agent's work."""
        complaint = _file(db).complaint
        report = resolution.classify(db, complaint.id)
        db.commit()

        resolution.confirm(db, report.required[0].step_id, agent)
        db.commit()

        again = resolution.classify(db, complaint.id)
        db.commit()
        assert len(again.confirmed) == 1

    def test_a_generated_suggestion_cannot_be_confirmed(self, db, clean, agent):
        """
        Advice is not an obligation, and letting someone complete advice would
        blur the line the checklist exists to draw.
        """
        complaint = _file(db).complaint
        step = ResolutionStep(
            complaint_id=complaint.id,
            ordinal=99,
            text="Consider offering a goodwill gesture.",
            source=ResolutionStepSource.GENAI,
            status=ResolutionStepStatus.SUPPORTED,
        )
        db.add(step)
        db.commit()

        with pytest.raises(ValueError, match="rule-required"):
            resolution.confirm(db, step.id, agent)

    def test_an_unauthorised_promise_in_a_step_is_prohibited(self, db, clean):
        """
        Decided by promise pattern against eligibility — the same rule the
        response guard uses, so there is one definition of what is forbidden.
        """
        complaint = _file(db, description=BILLING, order_ref="CN-7788990").complaint
        db.add(
            ResolutionStep(
                complaint_id=complaint.id,
                ordinal=50,
                text="Tell the customer their full refund has been approved.",
                source=ResolutionStepSource.GENAI,
                status=ResolutionStepStatus.SUPPORTED,
            )
        )
        db.commit()

        report = resolution.classify(
            db,
            complaint.id,
            eligibility=[
                {
                    "eligibility_type": "REFUND",
                    "python_outcome": "REQUIRES_VERIFICATION",
                    "rule_ref": "ELG-0001",
                }
            ],
        )
        db.commit()

        assert report.prohibited
        assert report.prohibited[0].promise_type == "REFUND"
        assert not report.complete

    def test_a_permitted_promise_is_not_prohibited(self, db, clean):
        complaint = _file(db, description=BILLING, order_ref="CN-7788990").complaint
        db.add(
            ResolutionStep(
                complaint_id=complaint.id,
                ordinal=50,
                text="Confirm the full refund will be processed.",
                source=ResolutionStepSource.GENAI,
                status=ResolutionStepStatus.SUPPORTED,
            )
        )
        db.commit()

        report = resolution.classify(
            db,
            complaint.id,
            eligibility=[
                {
                    "eligibility_type": "REFUND",
                    "python_outcome": "ELIGIBLE",
                    "rule_ref": "ELG-0002",
                }
            ],
        )
        db.commit()
        assert not report.prohibited

    def test_an_uncited_suggestion_is_unsupported_not_wrong(self, db, clean):
        """
        It may still be sensible. It is simply not traceable, so an agent owns
        it rather than the policy.
        """
        complaint = _file(db).complaint
        db.add(
            ResolutionStep(
                complaint_id=complaint.id,
                ordinal=50,
                text="Ask the customer to take a photograph of the plug.",
                source=ResolutionStepSource.GENAI,
                status=ResolutionStepStatus.SUPPORTED,
            )
        )
        db.commit()

        report = resolution.classify(db, complaint.id)
        db.commit()
        assert report.unsupported
        assert "not traceable" in report.unsupported[0].reason

    def test_coverage_is_null_when_there_is_nothing_to_do(self, db, clean):
        """A complaint with no obligations is not 0% complete — it is not measured."""
        report = resolution.ResolutionReport()
        assert report.summary()["coverage_pct"] is None
        assert report.complete


# ══════════════════════════════════════════════════════════════
# follow-ups
# ══════════════════════════════════════════════════════════════
class TestFollowUps:
    def test_an_escalation_schedules_contact(self, db, clean):
        complaint = _file(db).complaint
        rows = followup.for_complaint(db, complaint.id)
        assert any(r["type"] == followup.ESCALATION for r in rows)

    def test_an_unverified_eligibility_schedules_verification(self, db, clean):
        """
        The trigger that matters. A refund left at REQUIRES_VERIFICATION with
        nobody scheduled to verify it is how a customer waits three weeks for
        an answer nobody was working on.
        """
        complaint = _file(db, description=BILLING, order_ref="CN-7788990").complaint
        plan = followup.detect(
            db,
            complaint,
            reconciled={},
            eligibility=[
                {
                    "eligibility_type": "REFUND",
                    "python_outcome": "REQUIRES_VERIFICATION",
                    "conditions_evaluated": ["Purchase date within the window"],
                }
            ],
        )
        assert any(p.follow_up_type == followup.VERIFICATION for p in plan.planned)
        verification = next(
            p for p in plan.planned if p.follow_up_type == followup.VERIFICATION
        )
        assert "Purchase date" in verification.message

    def test_an_eligible_decision_schedules_nothing(self, db, clean):
        complaint = _file(db).complaint
        plan = followup.detect(
            db,
            complaint,
            reconciled={},
            eligibility=[{"eligibility_type": "REFUND", "python_outcome": "ELIGIBLE"}],
        )
        assert not [
            p for p in plan.planned if p.follow_up_type == followup.VERIFICATION
        ]

    def test_due_dates_come_from_the_sla_policy(self, db, clean):
        """
        Retuning an SLA target must move the follow-up with it, rather than
        leaving two numbers to drift apart.
        """
        complaint = _file(db).complaint
        assert complaint.priority_code == "P0"

        plan = followup.detect(db, complaint, reconciled={"escalation_required": True})
        escalation = next(
            p for p in plan.planned if p.follow_up_type == followup.ESCALATION
        )

        # The window is configuration. Read it, then assert the FRACTION --
        # that an escalation follow-up is due at half the first-response
        # window -- which is the behaviour, and survives a retune.
        from src.services import sla as sla_service

        policy = sla_service.find_policy(
            db, category_id=complaint.category_id,
            priority_code=complaint.priority_code,
        )
        expected = policy.first_response_mins * followup.WINDOW_FRACTION[
            followup.ESCALATION
        ]
        minutes = (escalation.due_at - datetime.now(UTC)).total_seconds() / 60
        assert 0 < minutes <= expected

    def test_rescheduling_refreshes_rather_than_duplicates(self, db, clean):
        """Re-analysis must not leave four identical reminders to dismiss."""
        complaint = _file(db).complaint
        before = len(followup.for_complaint(db, complaint.id))

        followup.apply(db, complaint, reconciled={"escalation_required": True})
        db.commit()

        assert len(followup.for_complaint(db, complaint.id)) == before

    def test_completing_is_idempotent(self, db, clean, agent):
        complaint = _file(db).complaint
        rows = followup.for_complaint(db, complaint.id)
        assert rows

        from uuid import UUID

        followup.complete(db, UUID(rows[0]["id"]), user_id=agent.id)
        db.commit()
        first = followup.for_complaint(db, complaint.id)[0]["completed_at"]

        followup.complete(db, UUID(rows[0]["id"]), user_id=agent.id)
        db.commit()
        assert followup.for_complaint(db, complaint.id)[0]["completed_at"] == first

    def test_the_due_list_is_soonest_first(self, db, clean):
        complaint = _file(db).complaint
        for row in db.execute(
            select(FollowUp).where(FollowUp.complaint_id == complaint.id)
        ).scalars():
            row.due_at = datetime.now(UTC) - timedelta(hours=2)
        db.commit()

        due = followup.due(db)
        assert due
        dates = [row["due_at"] for row in due]
        assert dates == sorted(dates)
        assert all(row["overdue_minutes"] > 0 for row in due)


# ══════════════════════════════════════════════════════════════
# escalation notes
# ══════════════════════════════════════════════════════════════
class TestEscalationNotes:
    def test_an_unescalated_complaint_gets_no_note(self, db, clean):
        """Generating a handover for something nobody is handing over wastes a call."""
        from genai_pipeline import escalation_notes

        complaint = _file(db).complaint
        result = escalation_notes.generate(
            db, complaint, reconciled={"escalation_level": "NONE"}
        )
        assert not result.ok
        assert result.failure_reason == "NOT_ESCALATED"

    def test_an_outage_costs_the_note_not_the_escalation(self, db, clean):
        """
        The escalation is a rule-derived fact already on record. Losing the
        note is a degraded handover, not a failed analysis.
        """
        from genai_pipeline import escalation_notes
        from genai_pipeline.providers import ProviderChain

        complaint = _file(db).complaint
        result = escalation_notes.generate(
            db,
            complaint,
            reconciled={"escalation_level": "CRITICAL_MGMT", "escalation_required": True},
            chain=ProviderChain([]),
        )

        assert not result.ok
        assert result.failure_reason == "NO_PROVIDER_CONFIGURED"
        assert complaint.escalation_code == "CRITICAL_MGMT", "the escalation stands"

    def test_the_escalation_record_survives_without_a_note(self, db, clean):
        from genai_pipeline import escalation_notes

        complaint = _file(db).complaint
        record = escalation_notes.note_for(db, complaint.id)

        assert record is not None
        assert record["escalation_code"] == "CRITICAL_MGMT"
        assert record["triggered_by"] == "PYTHON_RULE"
        # No provider in the suite, so the note is absent and says so.
        assert record["note_available"] is False

    def test_rendering_flattens_the_structured_note(self):
        from genai_pipeline.escalation_notes import render_note
        from schemas.genai import EscalationNote

        note = EscalationNote(
            complaint_summary="A charger overheated and the customer unplugged it.",
            key_facts=["Order CN-9923190", "Purchased 3 weeks ago"],
            reason_for_escalation="Product safety incident.",
            actions_already_taken=["Logged as a safety incident."],
            required_next_action="Notify Product Safety within one hour.",
            relevant_policy="SAF-POL-02",
        )
        text = render_note(note)

        assert "Key facts:" in text
        assert "Order CN-9923190" in text
        assert text.rstrip().endswith("SAF-POL-02")


# ══════════════════════════════════════════════════════════════
# endpoints
# ══════════════════════════════════════════════════════════════
class TestEndpoints:
    def _file_one(self, client, auth_headers):
        response = client.post(
            "/api/complaints",
            json={"title": "Charger burning smell", "description": SAFETY,
                  "order_ref": "CN-9923190"},
            headers=auth_headers("agent"),
        )
        assert response.status_code == 201, response.text
        return response.json()["complaint"]["public_ref"]

    def test_the_checklist_is_served(self, client, auth_headers, clean):
        ref = self._file_one(client, auth_headers)
        body = client.get(
            f"/api/complaints/{ref}/checklist", headers=auth_headers("agent")
        ).json()

        assert body["summary"]["required"] > 0
        assert body["summary"]["confirmed"] == 0
        assert all(step["confirmable"] for step in body["steps"])

    def test_confirming_a_step_moves_the_coverage(self, client, auth_headers, clean):
        ref = self._file_one(client, auth_headers)
        headers = auth_headers("agent")
        steps = client.get(f"/api/complaints/{ref}/checklist", headers=headers).json()

        step_id = steps["steps"][0]["id"]
        response = client.post(
            f"/api/complaints/{ref}/checklist/{step_id}/confirm", headers=headers
        )
        assert response.status_code == 200, response.text
        assert response.json()["summary"]["confirmed"] == 1

    def test_follow_ups_are_listed(self, client, auth_headers, clean):
        ref = self._file_one(client, auth_headers)
        body = client.get(
            f"/api/complaints/{ref}/follow-ups", headers=auth_headers("agent")
        ).json()
        assert body
        assert all(row["open"] for row in body)

    def test_completing_a_follow_up(self, client, auth_headers, clean):
        ref = self._file_one(client, auth_headers)
        headers = auth_headers("agent")
        rows = client.get(f"/api/complaints/{ref}/follow-ups", headers=headers).json()

        response = client.post(
            f"/api/complaints/{ref}/follow-ups/{rows[0]['id']}/complete",
            headers=headers,
        )
        assert response.status_code == 200
        assert any(not row["open"] for row in response.json())

    def test_the_escalation_note_is_served(self, client, auth_headers, clean):
        ref = self._file_one(client, auth_headers)
        body = client.get(
            f"/api/complaints/{ref}/escalation", headers=auth_headers("agent")
        ).json()

        assert body["escalation_code"] == "CRITICAL_MGMT"
        assert body["triggered_by"] == "PYTHON_RULE"
        assert "note_available" in body

    def test_an_unescalated_complaint_returns_404(self, client, auth_headers, clean):
        response = client.post(
            "/api/complaints",
            json={
                "title": "Where is my parcel",
                "description": (
                    "My parcel for order CN-4455660 has not arrived and the tracking "
                    "page has not updated for a couple of days."
                ),
                "order_ref": "CN-4455660",
            },
            headers=auth_headers("agent"),
        ).json()
        ref = response["complaint"]["public_ref"]

        if response["complaint"]["escalation_code"] in (None, "NONE"):
            assert (
                client.get(
                    f"/api/complaints/{ref}/escalation", headers=auth_headers("agent")
                ).status_code
                == 404
            )

    def test_the_due_list_is_available_to_staff(self, client, auth_headers, clean):
        self._file_one(client, auth_headers)
        response = client.get(
            "/api/review/follow-ups/due", headers=auth_headers("agent")
        )
        assert response.status_code == 200
        assert isinstance(response.json(), list)
