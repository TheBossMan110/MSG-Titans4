"""
Complaint lifecycle: the transition graph, its history and its refusals.

The test that matters most is
:meth:`TestGraph.test_a_complaint_cannot_be_closed_without_being_worked`.
A status column with no graph behind it lets a complaint reach CLOSED without
anyone resolving it, and every dashboard then counts it as handled.
"""

from __future__ import annotations

import pytest
from sqlalchemy import delete, select

from complaint_processing.intake import submit
from src.db.enums import ComplaintStatus as S
from src.db.models import (
    AgentGuidance,
    ClarificationQuestion,
    Comparison,
    Complaint,
    ComplaintEntity,
    ComplaintLink,
    ComplaintPolicyRef,
    ComplaintStatusHistory,
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
from src.services import lifecycle

LATE_PARCEL = (
    "My parcel for order CN-4455660 has still not arrived and the tracking page "
    "has not updated in four days. I would like to know where it is."
)


@pytest.fixture
def clean(db):
    def _purge():
        for model in (
            FollowUp, ReviewAction, ReviewQueueItem, SLAEvent, Escalation,
            Comparison, VerificationDecision, GenAIRun, ComplaintLink,
            ComplaintEntity, ComplaintValidationIssue, ComplaintPolicyRef,
            ResolutionStep, AgentGuidance, ClarificationQuestion,
            EligibilityDecision, ComplaintStatusHistory,
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


def _file(db):
    result = submit(
        db,
        title="Parcel not arrived",
        description=LATE_PARCEL,
        customer_email="lifecycle@example.com",
        order_ref="CN-4455660",
        run_genai=False,
    )
    db.commit()
    return result.complaint


# ══════════════════════════════════════════════════════════════
# the graph
# ══════════════════════════════════════════════════════════════
class TestGraph:
    def test_every_status_appears_in_the_graph(self):
        """
        A status missing from the graph is a dead end nothing can leave, and
        it would be discovered by a complaint getting stuck in it.
        """
        missing = [s for s in S if s not in lifecycle.TRANSITIONS]
        assert not missing, f"statuses with no declared transitions: {missing}"

    def test_every_destination_is_a_real_status(self):
        vocabulary = set(S)
        for origin, allowed in lifecycle.TRANSITIONS.items():
            unknown = allowed - vocabulary
            assert not unknown, f"{origin} -> {unknown}"

    def test_a_complaint_cannot_be_closed_without_being_worked(self, db, clean):
        """
        The reason the graph exists. NEW -> CLOSED would let a complaint be
        marked handled before anybody looked at it, and every count of
        "resolved this week" would include it.
        """
        assert not lifecycle.is_permitted(S.ANALYZING, S.CLOSED)
        assert not lifecycle.is_permitted(S.ASSIGNED, S.CLOSED)
        assert not lifecycle.is_permitted(S.IN_PROGRESS, S.CLOSED)
        # Closure is reachable only through a resolution or a review decision.
        assert lifecycle.is_permitted(S.RESOLVED, S.CLOSED)

    def test_a_closed_complaint_can_only_be_reopened(self):
        assert lifecycle.permitted_from(S.CLOSED) == frozenset({S.REOPENED})

    def test_re_analysis_is_permitted_from_any_open_status(self):
        """
        A rule change or a provider coming back justifies running the pipelines
        again. Closed ones are excluded: that means reopening first, on the
        record.
        """
        for origin in S:
            if origin in (S.RESOLVED, S.CLOSED, S.ANALYZING):
                continue
            assert lifecycle.is_permitted(origin, S.ANALYZING), origin

    def test_a_no_op_is_permitted(self):
        """Retries must be safe to repeat; refusing a no-op makes them errors."""
        assert lifecycle.is_permitted(S.ASSIGNED, S.ASSIGNED)

    def test_machine_statuses_are_not_offered_to_a_human(self, db, clean):
        complaint = _file(db)
        offered = set(lifecycle.available_actions(complaint))
        assert not offered & lifecycle.MACHINE_ONLY


# ══════════════════════════════════════════════════════════════
# transitions
# ══════════════════════════════════════════════════════════════
class TestTransition:
    def test_the_pipeline_writes_its_own_history(self, db, clean):
        """
        Intake moves a complaint too, and through the same door. A trail that
        recorded only what a human touched would not explain how anything got
        to its first status.
        """
        complaint = _file(db)
        trail = lifecycle.history(db, complaint.id)

        assert trail[0]["from_status"] == S.NEW
        assert trail[0]["to_status"] == S.ANALYZING
        assert trail[-1]["to_status"] == complaint.status
        assert all(row["changed_by"] == "pipeline" for row in trail)
        # Each row starts where the previous one ended -- an unbroken chain, so
        # no status was reached by a write that went round the service.
        for earlier, later in zip(trail, trail[1:], strict=False):
            assert later["from_status"] == earlier["to_status"]

    def test_a_human_move_records_who_and_why(self, db, clean, agent):
        complaint = _file(db)
        lifecycle.transition(
            db, complaint, S.ASSIGNED, actor=agent, reason="Taking this one."
        )
        db.commit()

        last = lifecycle.history(db, complaint.id)[-1]
        assert last["to_status"] == S.ASSIGNED
        assert last["changed_by"] == agent.email
        assert last["reason"] == "Taking this one."

    def test_a_refused_move_raises_rather_than_doing_nothing(self, db, clean, agent):
        """
        Swallowing it would leave the caller believing the complaint moved.

        RESOLVED straight out of review is the refusal being exercised: a
        complaint is not resolved by somebody deciding it needed looking at.
        """
        complaint = _file(db)
        before = complaint.status
        assert before == S.MANUAL_REVIEW

        with pytest.raises(lifecycle.TransitionRefused) as exc:
            lifecycle.transition(db, complaint, S.RESOLVED, actor=agent)

        assert complaint.status == before
        assert before in str(exc.value)
        assert "Permitted from" in str(exc.value)

    def test_a_refusal_writes_no_history(self, db, clean, agent):
        complaint = _file(db)
        before = len(lifecycle.history(db, complaint.id))

        with pytest.raises(lifecycle.TransitionRefused):
            lifecycle.transition(db, complaint, S.RESOLVED, actor=agent)
        db.rollback()

        assert len(lifecycle.history(db, complaint.id)) == before

    def test_a_no_op_changes_nothing_and_logs_nothing(self, db, clean, agent):
        complaint = _file(db)
        before = len(lifecycle.history(db, complaint.id))

        result = lifecycle.transition(db, complaint, complaint.status, actor=agent)
        db.commit()

        assert not result.changed
        assert len(lifecycle.history(db, complaint.id)) == before

    def test_resolving_stamps_the_time(self, db, clean, agent):
        complaint = _file(db)
        for step in (S.ASSIGNED, S.IN_PROGRESS, S.RESOLVED):
            lifecycle.transition(db, complaint, step, actor=agent)
        db.commit()

        assert complaint.resolved_at is not None

    def test_reopening_clears_the_closure_stamps(self, db, clean, agent):
        """
        Leaving them would make a complaint that is open again look resolved
        to every report that reads the dates rather than the status.
        """
        complaint = _file(db)
        for step in (S.ASSIGNED, S.IN_PROGRESS, S.RESOLVED, S.CLOSED):
            lifecycle.transition(db, complaint, step, actor=agent)
        db.commit()
        assert complaint.closed_at is not None

        lifecycle.transition(db, complaint, S.REOPENED, actor=agent,
                             reason="Customer says it is still broken.")
        db.commit()

        assert complaint.resolved_at is None
        assert complaint.closed_at is None
        assert complaint.status == S.REOPENED

    def test_an_unknown_status_is_refused(self, db, clean, agent):
        complaint = _file(db)
        with pytest.raises(lifecycle.TransitionRefused, match="not a status"):
            lifecycle.transition(db, complaint, "DONE_I_GUESS", actor=agent)

    def test_force_is_for_the_failure_path(self, db, clean):
        """
        A complaint whose analysis raised must land in FAILED from wherever it
        was. Refusing would lose the complaint rather than record the problem.
        """
        complaint = _file(db)
        assert not lifecycle.is_permitted(complaint.status, S.FAILED)

        lifecycle.transition(db, complaint, S.FAILED, reason="Analysis raised.",
                             force=True)
        db.commit()
        assert complaint.status == S.FAILED
        assert lifecycle.history(db, complaint.id)[-1]["to_status"] == S.FAILED


# ══════════════════════════════════════════════════════════════
# endpoints
# ══════════════════════════════════════════════════════════════
class TestEndpoints:
    def _file_one(self, client, auth_headers):
        response = client.post(
            "/api/complaints",
            json={"title": "Parcel not arrived", "description": LATE_PARCEL,
                  "order_ref": "CN-4455660"},
            headers=auth_headers("agent"),
        )
        assert response.status_code == 201, response.text
        return response.json()["complaint"]["public_ref"]

    def test_the_lifecycle_is_served(self, client, auth_headers, clean):
        ref = self._file_one(client, auth_headers)
        body = client.get(
            f"/api/complaints/{ref}/lifecycle", headers=auth_headers("reviewer")
        ).json()

        assert body["status"]
        assert body["history"]
        assert body["available_actions"]
        assert body["history"][0]["from_status"] == S.NEW

    def test_every_offered_action_is_one_the_api_accepts(
        self, client, auth_headers, clean, db
    ):
        """
        An interface that offers a move the API refuses teaches people to
        distrust it. Checked against the graph for all of them, and end to end
        for one -- the endpoint changes the complaint, so exercising every
        option over the same complaint would only test the second from
        wherever the first left it.
        """
        ref = self._file_one(client, auth_headers)
        headers = auth_headers("reviewer")
        body = client.get(f"/api/complaints/{ref}/lifecycle", headers=headers).json()
        offered = body["available_actions"]
        assert offered

        for action in offered:
            assert lifecycle.is_permitted(body["status"], action), action
            assert action not in lifecycle.MACHINE_ONLY

        response = client.post(
            f"/api/complaints/{ref}/status",
            json={"to_status": offered[0], "reason": "Checking the offer holds."},
            headers=headers,
        )
        assert response.status_code == 200, f"{offered[0]}: {response.text}"
        assert response.json()["status"] == offered[0]

    def test_a_move_outside_the_graph_is_refused_with_an_explanation(
        self, client, auth_headers, clean
    ):
        ref = self._file_one(client, auth_headers)
        response = client.post(
            f"/api/complaints/{ref}/status",
            json={"to_status": "RESOLVED", "reason": "Tidying up."},
            headers=auth_headers("reviewer"),
        )

        assert response.status_code == 422, response.text
        assert "Permitted from" in response.text

    def test_a_machine_status_cannot_be_set_by_hand(self, client, auth_headers, clean):
        """
        These are consequences of the pipeline. A human setting one would put
        the complaint in a state nothing downstream produced.
        """
        ref = self._file_one(client, auth_headers)
        response = client.post(
            f"/api/complaints/{ref}/status",
            json={"to_status": "ANALYZED"},
            headers=auth_headers("reviewer"),
        )
        assert response.status_code == 422
        assert "pipeline" in response.text

    def test_a_customer_cannot_move_their_own_complaint(
        self, client, auth_headers, clean
    ):
        ref = self._file_one(client, auth_headers)
        response = client.post(
            f"/api/complaints/{ref}/status",
            json={"to_status": "RESOLVED"},
            headers=auth_headers("customer"),
        )
        assert response.status_code == 403

    def test_the_change_is_audited(self, client, auth_headers, clean, db):
        from src.db.models import AuditLog

        ref = self._file_one(client, auth_headers)
        client.post(
            f"/api/complaints/{ref}/status",
            json={"to_status": "ASSIGNED", "reason": "Picking it up."},
            headers=auth_headers("reviewer"),
        )

        entry = db.execute(
            select(AuditLog)
            .where(AuditLog.action == "STATUS_CHANGE")
            .order_by(AuditLog.created_at.desc())
        ).scalars().first()

        assert entry is not None
        assert entry.before != entry.after, "an audit row with no delta records nothing"
        assert entry.after["status"] == "ASSIGNED"
