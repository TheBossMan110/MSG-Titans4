"""
Complaint endpoints.

FR iii   Complaint Submission     FR iv    Complaint Validation
FR v     Pre-processing           FR lvi   Duplicate Detection
FR lviii Repeat Detection         FR lxiv  Explainability
FR lxxi  Search and Filtering

Access model: a customer may submit and read back their own complaint by
reference; staff roles may list and inspect any complaint; re-analysis is
restricted to manager and administrator because it rewrites a stored decision.
The evaluator role reads everything, so a judge can inspect the system without
being handed an administrator token.

The explainability endpoint is the one that matters for judging. It returns
the whole chain — rules fired and the spans that fired them, both pipelines'
readings, every disagreement with its explanation, every policy reference with
its verdict, and every model attempt including the failures — all read back
from stored rows rather than recomputed for display.
"""

from __future__ import annotations

import json
import queue
import threading
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from comparison_engine.engine import comparison_rows, latest_decision
from complaint_processing import customer_actions, dedupe, file_intake, followup
from complaint_processing.intake import (
    IntakeRejected,
    analyse_complaint,
    deferring_escalation_notes,
    write_deferred_notes,
)
from complaint_processing.intake import IntakeResult as _IntakeResult
from complaint_processing.intake import submit as submit_complaint
from genai_pipeline import escalation_notes
from genai_pipeline.intelligence import runs_for_complaint
from hallucination_checks import policy_conflict
from hallucination_checks import trace as policy_trace
from python_validation import resolution
from schemas.common import Page
from schemas.complaints import (
    AssigneeOut,
    AssignIn,
    AssignOut,
    ChecklistOut,
    ChecklistStepOut,
    ClarificationAnswerIn,
    ClarificationAnswerOut,
    ClarificationOut,
    ComparisonOut,
    ComplaintCreate,
    ComplaintDetail,
    ComplaintStatusOut,
    ComplaintSummary,
    CustomerQuestionOut,
    DepartmentContactOut,
    EligibilityOut,
    EntityOut,
    EscalationOut,
    EvidenceOut,
    ExplainResponse,
    FileDraftOut,
    FollowUpOut,
    GuidanceOut,
    IntakeResponse,
    LifecycleOut,
    MilestoneOut,
    PolicyConflictOut,
    PreviewIn,
    PreviewOut,
    ReanalyseResponse,
    ResolutionStepOut,
    ResolutionSummaryOut,
    StatusChangeIn,
    StatusHistoryRowOut,
    ValidationIssueOut,
    VerificationOut,
)
from src.core import progress
from src.core.config import settings
from src.core.deps import CurrentUser, DbSession, require_role
from src.core.errors import AppError, NotFoundError, PermissionError_, ValidationError
from src.core.logging import get_logger
from src.core.ratelimit import limiter
from src.core.scope import can_see, complaint_in_scope, restrict
from src.db.enums import UserRole
from src.db.models import (
    AgentGuidance,
    AppConfig,
    Category,
    ClarificationQuestion,
    Complaint,
    ComplaintAttachment,
    ComplaintStatusHistory,
    ComplaintValidationIssue,
    Customer,
    Department,
    EligibilityDecision,
    ResolutionStep,
    SLAEvent,
    User,
    ValidationRun,
    VerificationDecision,
)
from src.services import lifecycle
from src.services.audit import record_audit

log = get_logger("api.complaints")

router = APIRouter(prefix="/complaints", tags=["Complaints"])

STAFF = (
    UserRole.AGENT,
    UserRole.REVIEWER,
    UserRole.MANAGER,
    UserRole.ADMIN,
    UserRole.EVALUATOR,
)


# ══════════════════════════════════════════════════════════════
# serialisation
# ══════════════════════════════════════════════════════════════
def _summary(complaint: Complaint) -> ComplaintSummary:
    return ComplaintSummary(
        id=complaint.id,
        public_ref=complaint.public_ref,
        title=complaint.title,
        status=complaint.status,
        category=complaint.category.code if complaint.category else None,
        department=complaint.department.code if complaint.department else None,
        urgency=complaint.urgency,
        priority_code=complaint.priority_code,
        escalation_code=complaint.escalation_code,
        verification_outcome=complaint.verification_outcome,
        injection_suspected=complaint.injection_suspected,
        is_duplicate=complaint.is_duplicate,
        repeat_count=complaint.repeat_count,
        created_at=complaint.created_at,
        customer_type=complaint.customer_type,
        dataset_tag=complaint.dataset_tag,
        channel=complaint.channel,
    )


def _verification(db: DbSession, complaint_id: uuid.UUID) -> VerificationOut | None:
    decision = latest_decision(db, complaint_id)
    if decision is None:
        return None
    return VerificationOut(
        outcome=decision.outcome,
        agreement_score=(
            float(decision.agreement_score) if decision.agreement_score is not None else None
        ),
        traceability_score=(
            float(decision.traceability_score)
            if decision.traceability_score is not None
            else None
        ),
        compliance_score=(
            float(decision.compliance_score)
            if decision.compliance_score is not None
            else None
        ),
        critical_mismatches=decision.critical_mismatches,
        high_mismatches=decision.high_mismatches,
        matched_fields=decision.matched_fields,
        total_fields=decision.total_fields,
        requires_review=decision.requires_review,
        review_reasons=list(decision.review_reasons or []),
        genai_available=decision.genai_available,
    )


def _detail(db: DbSession, complaint: Complaint) -> ComplaintDetail:
    """
    The full agent view.

    Built from stored rows only. Raw Pipeline 1 output is deliberately absent —
    it is reachable through ``/explain``, and mixing an overridden model
    opinion into the working view would undo the comparison engine's work.
    """
    issues = db.execute(
        select(ComplaintValidationIssue)
        .where(ComplaintValidationIssue.complaint_id == complaint.id)
        .order_by(ComplaintValidationIssue.created_at)
    ).scalars().all()

    steps = db.execute(
        select(ResolutionStep)
        .where(ResolutionStep.complaint_id == complaint.id)
        .order_by(ResolutionStep.ordinal)
    ).scalars().all()

    guidance = db.execute(
        select(AgentGuidance)
        .where(AgentGuidance.complaint_id == complaint.id)
        .order_by(AgentGuidance.ordinal)
    ).scalars().all()

    questions = db.execute(
        select(ClarificationQuestion)
        .where(ClarificationQuestion.complaint_id == complaint.id)
        .order_by(ClarificationQuestion.ordinal)
    ).scalars().all()

    eligibility = db.execute(
        select(EligibilityDecision).where(
            EligibilityDecision.complaint_id == complaint.id
        )
    ).scalars().all()

    holder = db.get(User, complaint.assigned_to) if complaint.assigned_to else None
    return ComplaintDetail(
        **_summary(complaint).model_dump(),
        assigned_to=AssigneeOut(id=holder.id, full_name=holder.full_name, role=holder.role) if holder else None,
        description_raw=complaint.description_raw,
        description_clean=complaint.description_clean,
        subcategory=complaint.subcategory.code if complaint.subcategory else None,
        support_department=(
            complaint.support_department.code if complaint.support_department else None
        ),
        sentiment=complaint.sentiment,
        primary_issue=complaint.primary_issue,
        secondary_issue=complaint.secondary_issue,
        summary=complaint.summary,
        emotion_indicators=list(complaint.emotion_indicators or []),
        missing_information=list(complaint.missing_information or []),
        product=complaint.product,
        order_ref=complaint.order_ref,
        transaction_ref=complaint.transaction_ref,
        amount=float(complaint.amount) if complaint.amount is not None else None,
        currency=complaint.currency,
        customer_ref=complaint.customer.external_ref if complaint.customer else None,
        analyzed_at=complaint.analyzed_at,
        validated_at=complaint.validated_at,
        verification=_verification(db, complaint.id),
        validation_issues=[
            ValidationIssueOut(
                code=i.issue_code, message=i.message, severity=i.severity,
                outcome=i.outcome, field=i.field,
            )
            for i in issues
        ],
        links=dedupe.links_for(db, complaint.id),
        entities=[
            EntityOut(
                entity_type=e.entity_type, value=e.value, normalized=e.normalized,
                extracted_by=e.extracted_by, span_start=e.span_start, span_end=e.span_end,
            )
            for e in complaint.entities
        ],
        resolution_steps=[
            ResolutionStepOut(
                ordinal=s.ordinal, text=s.text, action_code=s.action_code,
                source=s.source, status=s.status, rule_ref=s.rule_ref,
                policy_ref=s.policy_ref,
            )
            for s in steps
        ],
        guidance=[
            GuidanceOut(
                ordinal=g.ordinal, text=g.text, kind=g.kind, source=g.source,
                is_mandatory=g.is_mandatory, rule_ref=g.rule_ref,
            )
            for g in guidance
        ],
        clarifications=[
            ClarificationOut(
                id=q.id, ordinal=q.ordinal, question=q.question,
                missing_field=q.missing_field, answered_at=q.answered_at,
                answer=q.answer,
            )
            for q in questions
        ],
        eligibility=[
            EligibilityOut(
                eligibility_type=e.eligibility_type,
                final_outcome=e.final_outcome,
                python_outcome=e.python_outcome,
                requires_human_approval=e.requires_human_approval,
                conditions_evaluated=list(e.conditions_evaluated or []),
                rule_ref=e.rule_ref,
                reason=e.reason or "",
            )
            for e in eligibility
        ],
        evidence=_evidence(db, complaint),
    )


def _evidence(db: DbSession, complaint: Complaint, *, rows: list[Any] | None = None) -> list[EvidenceOut]:
    if rows is None:
        rows = db.execute(
            select(ComplaintAttachment)
            .where(ComplaintAttachment.complaint_id == complaint.id)
            .order_by(ComplaintAttachment.created_at)
        ).scalars().all()
    return [
        EvidenceOut(
            id=a.id, file_name=a.file_name, mime_type=a.mime_type,
            size_bytes=a.size_bytes, uploaded_at=a.created_at,
        )
        for a in rows
    ]


def _load(db: DbSession, ref: str) -> Complaint:
    """Find a complaint by public reference or id."""
    query = select(Complaint).options(
        selectinload(Complaint.entities), selectinload(Complaint.customer)
    )
    try:
        complaint = db.execute(
            query.where(Complaint.id == uuid.UUID(str(ref)))
        ).scalars().first()
    except (ValueError, AttributeError):
        complaint = db.execute(
            query.where(Complaint.public_ref == ref.strip().upper())
        ).scalars().first()

    if complaint is None:
        raise NotFoundError(f"No complaint with reference '{ref}'.")
    return complaint


# ══════════════════════════════════════════════════════════════
# submission
# ══════════════════════════════════════════════════════════════
@router.post(
    "",
    response_model=IntakeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a complaint",
)
def create_complaint(
    request: Request,
    payload: ComplaintCreate,
    db: DbSession,
    user: CurrentUser,
    background: BackgroundTasks,
    analyse: bool = Query(True, description="Run both pipelines immediately."),
) -> IntakeResponse:
    """
    Submit a complaint (FR iii; SRS Steps 9-11).

    Accepted even when validation finds problems — a short complaint, an
    unrecognised reference, a suspected injection are all recorded and the
    complaint processed on its merits. Only an empty complaint is refused, and
    even that attempt is written to ``complaint_validation_issues``.

    ``POST /api/complaints/stream`` does the same work and reports each step
    as it happens.
    """
    with deferring_escalation_notes() as pending:
        response = _intake(db, payload, user_id=user.id, role=user.role, analyse=analyse)
    # The handover note is for the agent, not the customer; it is written once
    # the response has gone rather than making the customer wait for it.
    background.add_task(write_deferred_notes, pending)
    return response


@router.post(
    "/stream",
    summary="Submit a complaint and follow its analysis live",
    response_class=StreamingResponse,
    responses={200: {
        "content": {"text/event-stream": {}},
        "description": (
            "Server-sent events. `step` events report each stage as it starts and "
            "finishes; exactly one `result` (the IntakeResponse) or `error` "
            "(the usual error body) ends the stream."
        ),
    }},
)
def create_complaint_stream(
    payload: ComplaintCreate,
    user: CurrentUser,
    analyse: bool = Query(True, description="Run both pipelines immediately."),
) -> StreamingResponse:
    """
    The same intake as ``POST /api/complaints``, narrated.

    Analysis takes seconds, most of them waiting on a language model. Rather
    than a spinner, the submitter sees which step is running, which model was
    asked and whether a busy one was swapped for another -- every message
    comes from the pipeline at the moment it happens, none are timed.
    """
    user_id, role = user.id, user.role  # plain values: the worker has its own session
    events: queue.Queue[tuple[str, Any] | None] = queue.Queue()

    def work() -> None:
        from src.db.base import SessionLocal

        db = SessionLocal()
        pending: list[Any] = []
        try:
            with progress.reporting(lambda event: events.put(("step", event))), \
                    deferring_escalation_notes() as pending:
                response = _intake(db, payload, user_id=user_id, role=role, analyse=analyse)
            events.put(("result", response.model_dump(mode="json")))
        except AppError as exc:
            db.rollback()
            events.put(("error", {"error": {
                "code": exc.code, "message": exc.message, "details": exc.details,
            }}))
        except Exception:  # noqa: BLE001 - the stream must end with an answer
            db.rollback()
            log.error("complaint_stream_failed", exc_info=True)
            events.put(("error", {"error": {
                "code": "INTERNAL_ERROR",
                "message": "Something went wrong while saving your complaint. Please try again.",
                "details": {},
            }}))
        finally:
            db.close()
            events.put(None)
        write_deferred_notes(pending)

    def stream() -> Any:
        # A comment line first, so proxies commit to streaming straight away.
        yield ": analysing\n\n"
        while True:
            try:
                item = events.get(timeout=15)
            except queue.Empty:
                yield ": still working\n\n"  # keep idle connections open
                continue
            if item is None:
                return
            kind, data = item
            yield f"event: {kind}\ndata: {json.dumps(data, default=str)}\n\n"

    threading.Thread(target=work, name="complaint-intake-stream", daemon=True).start()
    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )


def _intake(
    db: Any,
    payload: ComplaintCreate,
    *,
    user_id: uuid.UUID,
    role: str,
    analyse: bool,
) -> IntakeResponse:
    """Accept, analyse and commit one complaint; shape the answer for ``role``."""
    try:
        result: _IntakeResult = submit_complaint(
            db,
            title=payload.title,
            description=payload.description,
            customer_email=payload.customer_email,
            customer_name=payload.customer_name,
            product=payload.product,
            order_ref=payload.order_ref,
            transaction_ref=payload.transaction_ref,
            amount=payload.amount,
            currency=payload.currency,
            channel=payload.channel,
            requested_resolution=payload.requested_resolution,
            attachments=payload.attachments,
            submitted_by_user_id=user_id,
            # Only an evaluator seeding the benchmark corpus may tag a
            # complaint into a dataset; a customer must not be able to place
            # their submission in the scored set.
            dataset_tag=(
                payload.dataset_tag
                if role in (UserRole.EVALUATOR, UserRole.ADMIN)
                else None
            ),
            analyse=analyse,
        )
    except IntakeRejected as exc:
        db.commit()  # keep the recorded findings
        raise ValidationError(
            "The complaint could not be accepted.",
            details={"issues": [i.as_dict() for i in exc.report.issues]},
        ) from exc

    db.commit()
    complaint = result.complaint
    assert complaint is not None  # noqa: S101 - guaranteed when not rejected

    staff = role in STAFF
    return IntakeResponse(
        public_ref=complaint.public_ref,
        complaint=_detail(db, complaint) if staff else None,
        customer_view=None if staff else _customer_view(db, complaint),
        accepted=True,
        analysed=result.analysed,
        analysis_error=result.analysis_error,
        validation_issues=[
            ValidationIssueOut(
                code=i.code, message=i.message, severity=i.severity,
                outcome=i.outcome, field=i.field_name,
            )
            for i in (result.validation_report.issues if result.validation_report else [])
        ],
        # Internal bookkeeping stays with staff: the duplicate a complaint was
        # matched to may not be the submitter's own, and the preprocessing
        # summary describes how untrusted text was neutralised.
        duplicate_of=(
            result.dedupe_result.exact.public_ref
            if staff and result.dedupe_result and result.dedupe_result.exact
            else None
        ),
        repeat_count=result.dedupe_result.repeat_count if result.dedupe_result else 0,
        preprocessing=result.preprocessing if staff else {},
    )


# ══════════════════════════════════════════════════════════════
# reading
# ══════════════════════════════════════════════════════════════
@router.get(
    "",
    response_model=Page[ComplaintSummary],
    dependencies=[Depends(require_role(*STAFF))],
    summary="List complaints",
)
def list_complaints(
    db: DbSession,
    user: CurrentUser,
    page: int = Query(1, ge=1),
    size: int = Query(25, ge=1, le=100),
    status_filter: str | None = Query(None, alias="status"),
    category: str | None = None,
    department: str | None = None,
    urgency: str | None = None,
    priority: str | None = None,
    verification_outcome: str | None = None,
    requires_review: bool | None = None,
    dataset_tag: str | None = None,
    customer_type: str | None = Query(None, max_length=64),
    sentiment: str | None = Query(None, max_length=32),
    escalation: str | None = Query(None, max_length=32, description="ANY (escalated), NONE, or a level code."),
    date_from: date | None = Query(None, description="Received on or after this date."),
    date_to: date | None = Query(None, description="Received on or before this date."),
    search: str | None = Query(None, max_length=200),
) -> Page[ComplaintSummary]:
    """List and filter complaints (FR lxxi). Agents see their team's and their own (FR ii)."""
    query = restrict(select(Complaint), user)

    if status_filter:
        query = query.where(Complaint.status == status_filter.strip().upper())
    if urgency:
        query = query.where(Complaint.urgency == urgency.strip().upper())
    if priority:
        query = query.where(Complaint.priority_code == priority.strip().upper())
    if verification_outcome:
        query = query.where(
            Complaint.verification_outcome == verification_outcome.strip().upper()
        )
    if dataset_tag:
        query = query.where(Complaint.dataset_tag == dataset_tag.strip().upper())
    if customer_type:
        query = query.where(Complaint.customer_type == customer_type.strip())
    if category:
        query = query.where(
            Complaint.category_id.in_(
                select(Category.id).where(Category.code == category.strip().upper())
            )
        )
    if department:
        query = query.where(
            Complaint.department_id.in_(
                select(Department.id).where(Department.code == department.strip().upper())
            )
        )
    if requires_review is not None:
        # Driven by the stored decision rather than by a status guess, so the
        # queue cannot drift from what the comparison engine concluded.
        review_ids = select(VerificationDecision.complaint_id).where(
            VerificationDecision.requires_review.is_(True)
        )
        query = (
            query.where(Complaint.id.in_(review_ids))
            if requires_review
            else query.where(Complaint.id.not_in(review_ids))
        )
    if sentiment:
        query = query.where(Complaint.sentiment == sentiment.strip().upper())
    if escalation:
        level = escalation.strip().upper()
        if level == "ANY":
            query = query.where(Complaint.escalation_code.is_not(None), Complaint.escalation_code != "NONE")
        elif level == "NONE":
            query = query.where(or_(Complaint.escalation_code.is_(None), Complaint.escalation_code == "NONE"))
        else:
            query = query.where(Complaint.escalation_code == level)
    if date_from:
        query = query.where(Complaint.created_at >= datetime.combine(date_from, time.min, tzinfo=UTC))
    if date_to:
        query = query.where(Complaint.created_at < datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=UTC))
    if search:
        # SRS Step 66: complaint ID, customer reference, and the text itself.
        pattern = f"%{search.strip().lower()}%"
        customers = select(Customer.id).where(
            func.lower(Customer.external_ref).like(pattern) | func.lower(Customer.email).like(pattern)
        )
        query = query.where(
            func.lower(Complaint.title).like(pattern)
            | func.lower(Complaint.description_clean).like(pattern)
            | func.lower(Complaint.public_ref).like(pattern)
            | func.lower(Complaint.order_ref).like(pattern)
            | func.lower(Complaint.transaction_ref).like(pattern)
            | Complaint.customer_id.in_(customers)
        )

    total = db.execute(
        select(func.count()).select_from(query.subquery())
    ).scalar_one()

    rows = db.execute(
        query.order_by(Complaint.created_at.desc())
        .offset((page - 1) * size)
        .limit(size)
    ).scalars().all()

    return Page[ComplaintSummary](
        items=[_summary(row) for row in rows],
        total=total,
        page=page,
        size=size,
    )


def _belongs_to(db: DbSession, complaint: Complaint, user: User) -> bool:
    """
    Whether this complaint is the signed-in person's own.

    Two ways in, because there are two ways a complaint gets filed. Usually
    the customer submits it themselves and ``submitted_by_user_id`` is theirs.
    But an agent taking a complaint by phone files it *for* them, and the only
    link back is the customer record. Checking the submitter alone would hide a
    customer's own complaint from them because somebody else typed it in.
    """
    if complaint.submitted_by_user_id == user.id:
        return True
    customer = complaint.customer
    return bool(
        customer
        and customer.email
        and user.email
        and customer.email.lower() == user.email.lower()
    )


@dataclass
class _ViewData:
    """Everything the customer view reads beyond the complaint row, for many complaints at once."""

    questions: dict[Any, list[Any]]
    targets: dict[Any, Any]
    history: dict[Any, list[tuple[str, Any]]]
    evidence: dict[Any, list[Any]]
    support_hours: str | None


def _prefetch(db: DbSession, ids: list[Any]) -> _ViewData:
    """
    Five queries for a whole page instead of six per complaint.

    Against a hosted database each query is a network round trip, and a
    customer with 19 complaints waited over six seconds for their list.
    """
    data = _ViewData(questions={}, targets={}, history={}, evidence={}, support_hours=None)
    if ids:
        for q in db.execute(
            select(ClarificationQuestion).where(ClarificationQuestion.complaint_id.in_(ids)).order_by(ClarificationQuestion.ordinal)
        ).scalars():
            data.questions.setdefault(q.complaint_id, []).append(q)
        for cid, due in db.execute(
            select(SLAEvent.complaint_id, func.max(SLAEvent.due_at))
            .where(SLAEvent.complaint_id.in_(ids), SLAEvent.event_type == "RESOLUTION")
            .group_by(SLAEvent.complaint_id)
        ).all():
            data.targets[cid] = due
        for cid, to_status, at in db.execute(
            select(ComplaintStatusHistory.complaint_id, ComplaintStatusHistory.to_status, ComplaintStatusHistory.created_at)
            .where(ComplaintStatusHistory.complaint_id.in_(ids)).order_by(ComplaintStatusHistory.created_at)
        ).all():
            data.history.setdefault(cid, []).append((to_status, at))
        for a in db.execute(
            select(ComplaintAttachment).where(ComplaintAttachment.complaint_id.in_(ids)).order_by(ComplaintAttachment.created_at)
        ).scalars():
            data.evidence.setdefault(a.complaint_id, []).append(a)
    organisation = db.get(AppConfig, "organisation")
    if organisation is not None and isinstance(organisation.value, dict):
        data.support_hours = organisation.value.get("support_hours")
    return data


def _customer_view(db: DbSession, complaint: Complaint, pre: _ViewData | None = None) -> ComplaintStatusOut:
    """
    The customer-safe projection of one complaint (FR lxvi; SRS Step 61).

    Built in one place so the list and the tracking page cannot drift. The
    payload is a separate model from the agent view rather than a filtered one:
    internal guidance, rule references, eligibility reasoning and the pipeline
    comparison are not fields of this response at all, so no future serialiser
    change can leak them.
    """
    pre = pre or _prefetch(db, [complaint.id])
    questions = pre.questions.get(complaint.id, [])
    open_questions = [q for q in questions if q.answered_at is None]
    target = pre.targets.get(complaint.id)
    history = pre.history.get(complaint.id, [])

    # "Last updated" means the last time anything happened to it, which the
    # status history knows and the analysis timestamp does not.
    last_moved = max((at for _, at in history), default=None)

    return ComplaintStatusOut(
        public_ref=complaint.public_ref,
        title=complaint.title,
        status=complaint.status,
        submitted_at=complaint.created_at,
        category=complaint.category.code if complaint.category else None,
        category_name=complaint.category.name if complaint.category else None,
        summary=complaint.summary,
        # The fact, not the level. That a complaint went to compliance review
        # is internal routing; telling the customer a specialist will be in
        # touch is the same information without handing them a lever.
        escalated=bool(
            complaint.escalation_code and complaint.escalation_code.upper() != "NONE"
        ),
        awaiting_information=[q.question for q in open_questions],
        last_updated=last_moved or complaint.analyzed_at or complaint.created_at,
        target_resolution_at=target,
        department=_department_contact(db, complaint, hours=pre.support_hours),
        questions=[
            CustomerQuestionOut(
                id=q.id, ordinal=q.ordinal, question=q.question,
                answered=q.answered_at is not None, answer=q.answer,
                answered_at=q.answered_at,
            )
            for q in questions
        ],
        milestones=_milestones(db, complaint, history=history),
        evidence=_evidence(db, complaint, rows=pre.evidence.get(complaint.id, [])),
        action_needed=bool(open_questions),
    )


def _department_contact(db: DbSession, complaint: Complaint, *, hours: str | None = None) -> DepartmentContactOut | None:
    """The owning team as the customer sees it: name, remit, mailbox, hours."""
    dept = complaint.department
    if dept is None:
        return None
    return DepartmentContactOut(
        name=dept.name, summary=dept.description, email=dept.email, support_hours=hours,
    )


# Customer vocabulary for the internal lifecycle. Several internal states map
# to one milestone on purpose — see MilestoneOut.
_TEAM_STATES = {
    "ASSIGNED", "IN_PROGRESS", "AWAITING_CUSTOMER", "ESCALATED", "MANUAL_REVIEW", "REOPENED",
}
_DONE_STATES = {"RESOLVED", "CLOSED"}
_CHECKED_STATES = {"ANALYZED", "VALIDATED"} | _TEAM_STATES | _DONE_STATES


def _milestones(db: DbSession, complaint: Complaint, *, history: list[tuple[str, Any]] | None = None) -> list[MilestoneOut]:
    if history is None:
        history = db.execute(
            select(ComplaintStatusHistory.to_status, ComplaintStatusHistory.created_at)
            .where(ComplaintStatusHistory.complaint_id == complaint.id)
            .order_by(ComplaintStatusHistory.created_at)
        ).all()
    first_at: dict[str, Any] = {}
    for to_status, at in history:
        first_at.setdefault(to_status, at)

    def first_of(states: set[str]):
        times = [first_at[state] for state in states if state in first_at]
        return min(times) if times else None

    now = complaint.status
    team = f"the {complaint.department.name} team" if complaint.department else "a specialist"
    steps = [
        MilestoneOut(
            key="RECEIVED", label="Received",
            detail="Your complaint is in the register with a reference number.",
            reached=True, at=complaint.created_at,
        ),
        MilestoneOut(
            key="UNDERSTOOD", label="Read and understood",
            detail="What happened, what you are asking for, and what is missing.",
            reached=bool(first_at.get("ANALYZING") or complaint.analyzed_at),
            at=first_at.get("ANALYZING") or complaint.analyzed_at,
        ),
        MilestoneOut(
            key="CHECKED", label="Checked against policy",
            detail="Every decision is confirmed against the company's own rules.",
            reached=now in _CHECKED_STATES or bool(first_of(_CHECKED_STATES)),
            at=complaint.validated_at or complaint.analyzed_at or first_of(_CHECKED_STATES),
        ),
        MilestoneOut(
            key="WITH_TEAM", label=f"With {team}",
            detail=(
                "Waiting for your answer to the questions below."
                if now == "AWAITING_CUSTOMER"
                else "A person is working on it."
            ),
            reached=now in (_TEAM_STATES | _DONE_STATES) or bool(first_of(_TEAM_STATES)),
            at=first_of(_TEAM_STATES),
        ),
        MilestoneOut(
            key="RESOLVED", label="Resolved",
            detail="The outcome has been confirmed and sent to you.",
            reached=now in _DONE_STATES,
            at=first_of(_DONE_STATES),
        ),
    ]
    for step in steps:
        if not step.reached:
            step.current = True
            break
    return steps


@router.get(
    "/mine",
    response_model=Page[ComplaintStatusOut],
    summary="Your own complaints",
)
def my_complaints(
    db: DbSession,
    user: CurrentUser,
    page: int = Query(1, ge=1),
    size: int = Query(25, ge=1, le=100),
) -> Page[ComplaintStatusOut]:
    """
    Every complaint the signed-in person filed (FR lxvi; SRS Step 61).

    Declared before ``/{ref}`` deliberately: FastAPI matches in declaration
    order, and a ``/mine`` behind the wildcard would be read as a complaint
    reference called "mine".

    Without this a customer dashboard means remembering CMP-000014, and a
    reference typed from memory is the one thing standing between a person and
    their own complaint. Staff get the same customer-safe projection here --
    the agent view lives at ``GET /api/complaints`` and carries far more.
    """
    owned = select(Complaint).where(
        or_(
            Complaint.submitted_by_user_id == user.id,
            Complaint.customer_id.in_(
                select(Customer.id).where(func.lower(Customer.email) == user.email.lower())
            ),
        )
    )

    total = db.execute(
        select(func.count()).select_from(owned.subquery())
    ).scalar_one()

    rows = db.execute(
        owned.options(selectinload(Complaint.category))
        .order_by(Complaint.created_at.desc())
        .offset((page - 1) * size)
        .limit(size)
    ).scalars().all()
    pre = _prefetch(db, [row.id for row in rows])

    return Page[ComplaintStatusOut](
        items=[_customer_view(db, row, pre) for row in rows],
        total=total,
        page=page,
        size=size,
    )


@router.get(
    "/{ref}",
    response_model=ComplaintDetail,
    dependencies=[Depends(require_role(*STAFF)), Depends(complaint_in_scope)],
    summary="Read one complaint",
)
def get_complaint(ref: str, db: DbSession) -> ComplaintDetail:
    return _detail(db, _load(db, ref))


@router.get(
    "/{ref}/explain",
    response_model=ExplainResponse,
    dependencies=[Depends(require_role(*STAFF)), Depends(complaint_in_scope)],
    summary="Why this complaint was decided as it was",
)
def explain_complaint(ref: str, db: DbSession) -> ExplainResponse:
    """
    The full decision chain (FR lxiv).

    Everything here is read back from stored rows. Nothing is recomputed for
    display, so what a judge sees is provably what the system did at the time
    — including the model attempts that failed.
    """
    complaint = _load(db, ref)
    decision = latest_decision(db, complaint.id)

    validation_run = db.execute(
        select(ValidationRun)
        .where(ValidationRun.complaint_id == complaint.id)
        .order_by(ValidationRun.created_at.desc())
    ).scalars().first()

    rule_hits = []
    reason_codes: list[str] = []
    if validation_run is not None:
        reason_codes = list(validation_run.reason_codes or [])
        for hit in validation_run.rule_hits:
            # The mandatory-escalation flag and the rationale live on the rule,
            # not on the hit: a hit records that a rule fired and on what text,
            # while what the rule *is* stays in one place and can be edited at
            # runtime without rewriting history.
            rule = hit.rule
            rule_hits.append(
                {
                    "rule_ref": hit.rule_ref,
                    "precedence": hit.precedence,
                    "mandatory_escalation": bool(
                        getattr(rule, "is_mandatory_escalation", False)
                    ),
                    "applied": hit.applied,
                    "rationale": getattr(rule, "rationale", None) or None,
                    "signals": list(hit.matched_signals or []),
                    "spans": list(hit.matched_spans or []),
                }
            )

    return ExplainResponse(
        public_ref=complaint.public_ref,
        verification=_verification(db, complaint.id),
        reconciled=dict(decision.reconciled) if decision else {},
        comparisons=[ComparisonOut(**_rename(row)) for row in comparison_rows(db, complaint.id)],
        rule_hits=rule_hits,
        reason_codes=reason_codes,
        escalation_floor=(
            validation_run.escalation_floor_code if validation_run else None
        ),
        genai_runs=runs_for_complaint(db, complaint.id),
        policy_trace=policy_trace(db, complaint.id),
        policy_conflicts=[
            PolicyConflictOut(**row)
            for row in policy_conflict.conflicts_for(db, complaint.id)
        ],
        ruleset_version=validation_run.ruleset_version if validation_run else None,
        knowledge_base_version=(
            validation_run.knowledge_base_version if validation_run else None
        ),
    )


def _rename(row: dict) -> dict:
    """``comparison_rows`` uses short keys; the API contract uses explicit ones."""
    return {
        "field": row["field"],
        "genai_value": row["genai"],
        "python_value": row["python"],
        "final_value": row["final"],
        "status": row["status"],
        "severity": row["severity"],
        "winner": row["winner"],
        "reason_code": row["reason_code"],
        "explanation": row["explanation"],
    }


# ══════════════════════════════════════════════════════════════
# re-analysis
# ══════════════════════════════════════════════════════════════
@router.post(
    "/{ref}/reanalyse",
    response_model=ReanalyseResponse,
    dependencies=[Depends(require_role(UserRole.MANAGER, UserRole.ADMIN))],
    summary="Re-run both pipelines for a complaint",
)
def reanalyse(
    ref: str,
    db: DbSession,
    run_genai: bool = Query(True),
) -> ReanalyseResponse:
    """
    Re-run analysis after a rule, policy or threshold change.

    This is how SRS 1.8 #14 is demonstrated: change an escalation rule, re-run
    one complaint, and watch the outcome move — without a deploy. The previous
    comparison rows are replaced rather than appended, so the complaint has one
    current decision rather than two contradictory ones.

    Restricted to manager and administrator because it rewrites a stored
    decision an agent may already have acted on.
    """
    complaint = _load(db, ref)
    before = {
        "category": complaint.category.code if complaint.category else None,
        "department": complaint.department.code if complaint.department else None,
        "urgency": complaint.urgency,
        "priority": complaint.priority_code,
        "escalation": complaint.escalation_code,
        "verification_outcome": complaint.verification_outcome,
    }

    result = _IntakeResult(complaint=complaint)
    analyse_complaint(db, complaint, result, run_genai=run_genai)
    db.commit()

    after = {
        "category": complaint.category.code if complaint.category else None,
        "department": complaint.department.code if complaint.department else None,
        "urgency": complaint.urgency,
        "priority": complaint.priority_code,
        "escalation": complaint.escalation_code,
        "verification_outcome": complaint.verification_outcome,
    }
    changed = {
        key: {"before": before[key], "after": after[key]}
        for key in before
        if before[key] != after[key]
    }

    log.info("complaint_reanalysed", public_ref=complaint.public_ref, changed=list(changed))
    return ReanalyseResponse(
        public_ref=complaint.public_ref,
        verification=_verification(db, complaint.id),
        changed=changed,
    )


# ══════════════════════════════════════════════════════════════
# the customer's own view
# ══════════════════════════════════════════════════════════════
@router.get(
    "/{ref}/status",
    response_model=ComplaintStatusOut,
    summary="Track your own complaint",
)
def complaint_status(
    ref: str, db: DbSession, user: CurrentUser
) -> ComplaintStatusOut:
    """
    What a customer may see about their own complaint (FR lxvi; SRS Step 61).

    **Ownership is checked, not assumed.** A customer may read only a complaint
    they submitted; staff may read any. Without that check a public reference
    like ``CMP-000014`` is guessable, and the whole register would be readable
    by incrementing a number.

    The payload is a separate model from the agent view rather than a filtered
    one. Internal guidance, rule references, eligibility reasoning and the
    pipeline comparison are not merely hidden here — they are not fields of
    this response at all, so no future serialiser change can leak them.
    """
    complaint = _load(db, ref)

    if user.role not in STAFF and not _belongs_to(db, complaint, user):
        # Deliberately the same 404 an unknown reference returns. A distinct
        # 403 would confirm that the reference exists, which is exactly what
        # someone walking the numbers is trying to learn.
        raise NotFoundError(f"No complaint with reference '{ref}'.")

    return _customer_view(db, complaint)


# ══════════════════════════════════════════════════════════════
# customer actions: answer, attach, preview
# ══════════════════════════════════════════════════════════════
def _own_or_staff(db: DbSession, ref: str, user: User) -> Complaint:
    """
    Load a complaint the caller may act on: their own, or any if staff.

    An unowned reference answers with the same 404 as an unknown one, so the
    endpoints below cannot be used to discover which references exist.
    """
    complaint = _load(db, ref)
    if user.role not in STAFF and not _belongs_to(db, complaint, user):
        raise NotFoundError(f"No complaint with reference '{ref}'.")
    if user.role in STAFF and not can_see(complaint, user):
        raise NotFoundError(f"No complaint with reference '{ref}'.")
    return complaint


@router.post(
    "/preview",
    response_model=PreviewOut,
    summary="What the system will read in a draft complaint (nothing is stored)",
)
@limiter.limit("40/minute")
def preview_complaint(
    request: Request,
    response: Response,
    payload: PreviewIn,
    db: DbSession,
    user: CurrentUser,
) -> PreviewOut:
    """
    The live pre-check behind the intake form.

    Pattern extraction and the injection screen, plus the rule engine's
    likely category once there is enough text to classify. **No model is
    called and nothing is written** — not a complaint row, not an injection
    event — so it can run on every pause in typing without spending quota or
    counting keystrokes as attacks. Rate-limited all the same.
    """
    return PreviewOut(**customer_actions.preview(
        db, title=payload.title, description=payload.description,
        with_category=len(payload.description.split()) >= 6,
    ))


@router.post(
    "/{ref}/clarifications/{question_id}/answer",
    response_model=ClarificationAnswerOut,
    summary="Answer one clarifying question",
)
def answer_question(
    ref: str,
    question_id: uuid.UUID,
    payload: ClarificationAnswerIn,
    db: DbSession,
    user: CurrentUser,
    request: Request,
) -> ClarificationAnswerOut:
    """
    The customer's side of the Missing-Information Challenge.

    The pipeline asks rather than invents; this is how the answer gets back.
    The reply is screened for injection like the complaint body, may fill an
    empty order or transaction reference, and — once every question is
    answered — closes the chase follow-up and returns the complaint to work.
    Staff may record an answer given by phone on the customer's behalf.
    """
    complaint = _own_or_staff(db, ref, user)
    result = customer_actions.answer_clarification(
        db, complaint, question_id, payload.answer, actor=user, request=request,
    )
    db.flush()
    return ClarificationAnswerOut(
        status=_customer_view(db, complaint),
        filled=result.filled,
        all_answered=result.all_answered,
        status_changed_to=result.status_changed_to,
    )


@router.post(
    "/{ref}/evidence",
    response_model=EvidenceOut,
    status_code=status.HTTP_201_CREATED,
    summary="Attach a photo, receipt or document",
)
async def attach_evidence(
    ref: str,
    db: DbSession,
    user: CurrentUser,
    request: Request,
    response: Response,
    file: UploadFile = File(...),
) -> EvidenceOut:
    """
    Upload one evidence file: PDF, DOCX, PNG, JPEG, WEBP or plain text.

    The type is decided by the file's bytes, not its name or the browser's
    content type, so a renamed executable is refused rather than stored with a
    reassuring MIME type. The same file uploaded twice returns the first copy
    with 200 instead of 201.
    """
    complaint = _own_or_staff(db, ref, user)
    data = await file.read(settings.max_upload_bytes + 1)
    attachment, created = customer_actions.attach_evidence(
        db, complaint, data=data, file_name=file.filename or "evidence",
        actor=user, request=request,
    )
    if not created:
        response.status_code = status.HTTP_200_OK
    return EvidenceOut(
        id=attachment.id, file_name=attachment.file_name, mime_type=attachment.mime_type,
        size_bytes=attachment.size_bytes, uploaded_at=attachment.created_at,
    )


@router.post(
    "/from-file",
    response_model=FileDraftOut,
    summary="Read a complaint letter (PDF, DOCX or text) into a draft to check and file",
)
@limiter.limit("20/minute")
async def complaint_from_file(
    request: Request, response: Response, user: CurrentUser, file: UploadFile = File(...),
) -> FileDraftOut:
    """
    The "uploaded complaint" channel. Nothing is filed: the draft goes back to
    the form, the customer checks it, and it is submitted with channel UPLOAD
    through the same intake and pipelines as any other complaint.
    """
    data = await file.read(settings.max_upload_bytes + 1)
    draft = file_intake.read_complaint_file(data, file.filename or "complaint")
    log.info("complaint_file_read", format=draft.file_format, chars=len(draft.description), by=user.role)
    return FileDraftOut(**draft.__dict__)


@router.get(
    "/{ref}/evidence/{attachment_id}",
    summary="Download one evidence file",
    response_class=Response,
)
def download_evidence(
    ref: str, attachment_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> Response:
    """
    Always served as a download, never inline: an uploaded file is untrusted
    content, and rendering it in our origin would let a crafted file run as us.
    """
    complaint = _own_or_staff(db, ref, user)
    attachment, data = customer_actions.load_evidence(complaint, attachment_id, db)
    safe = attachment.file_name.replace('"', "")
    return Response(
        content=data,
        media_type=attachment.mime_type,
        headers={
            "Content-Disposition": f'attachment; filename="{safe}"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


# ══════════════════════════════════════════════════════════════
# the completion stages
# ══════════════════════════════════════════════════════════════
@router.get(
    "/{ref}/checklist",
    response_model=ChecklistOut,
    dependencies=[Depends(require_role(*STAFF)), Depends(complaint_in_scope)],
    summary="Resolution steps and what is outstanding",
)
def complaint_checklist(ref: str, db: DbSession) -> ChecklistOut:
    """
    The agent's checklist (FR xxv; SRS Step 28).

    Rule obligations sit at ``MISSING`` until a person confirms them. Nothing
    infers that "verify the shipment in the tracking system" was done, because
    that is not readable from any text the system holds — and a checklist that
    ticked itself would be decorative.
    """
    complaint = _load(db, ref)
    report = resolution.classify(db, complaint.id)
    db.commit()

    return ChecklistOut(
        summary=ResolutionSummaryOut(**report.summary()),
        steps=[ChecklistStepOut(**row) for row in resolution.steps_for(db, complaint.id)],
    )


@router.post(
    "/{ref}/checklist/{step_id}/confirm",
    response_model=ChecklistOut,
    dependencies=[Depends(require_role(*STAFF)), Depends(complaint_in_scope)],
    summary="Confirm a required step was carried out",
)
def confirm_step(
    ref: str, step_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> ChecklistOut:
    """
    Record that an agent did one of the things the rules require.

    The only route to ``REQUIRED_MET``, and it records who confirmed it. A
    generated suggestion cannot be confirmed — it is advice, not an obligation,
    and the refusal says so rather than silently succeeding.
    """
    complaint = _load(db, ref)
    try:
        resolution.confirm(db, step_id, user)
    except ValueError as exc:
        db.rollback()
        raise ValidationError(str(exc)) from exc

    report = resolution.classify(db, complaint.id)
    db.commit()

    return ChecklistOut(
        summary=ResolutionSummaryOut(**report.summary()),
        steps=[ChecklistStepOut(**row) for row in resolution.steps_for(db, complaint.id)],
    )


@router.get(
    "/{ref}/follow-ups",
    response_model=list[FollowUpOut],
    dependencies=[Depends(require_role(*STAFF)), Depends(complaint_in_scope)],
    summary="What the system owes on this complaint",
)
def complaint_follow_ups(ref: str, db: DbSession) -> list[FollowUpOut]:
    complaint = _load(db, ref)
    return [FollowUpOut(**row) for row in followup.for_complaint(db, complaint.id)]


@router.post(
    "/{ref}/follow-ups/{follow_up_id}/complete",
    response_model=list[FollowUpOut],
    dependencies=[Depends(require_role(*STAFF)), Depends(complaint_in_scope)],
    summary="Mark a follow-up done",
)
def complete_follow_up(
    ref: str, follow_up_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> list[FollowUpOut]:
    """Idempotent: completing twice keeps the first timestamp."""
    complaint = _load(db, ref)
    try:
        followup.complete(db, follow_up_id, user_id=user.id)
    except ValueError as exc:
        db.rollback()
        raise NotFoundError(str(exc)) from exc

    db.commit()
    return [FollowUpOut(**row) for row in followup.for_complaint(db, complaint.id)]


@router.get(
    "/{ref}/escalation",
    response_model=EscalationOut,
    dependencies=[Depends(require_role(*STAFF)), Depends(complaint_in_scope)],
    summary="The escalation and its handover note",
)
def complaint_escalation(ref: str, db: DbSession) -> EscalationOut:
    """
    The note a specialist reads cold (FR xxxv; SRS Step 38).

    A 404 here means the complaint was never escalated. An escalation with
    ``note_available: false`` means it was escalated while no provider was
    reachable — the handover is degraded, and an agent should know that rather
    than see an empty box.
    """
    complaint = _load(db, ref)
    record = escalation_notes.note_for(db, complaint.id)
    if record is None:
        raise NotFoundError(f"Complaint {complaint.public_ref} is not escalated.")
    return EscalationOut(**record)


@router.post(
    "/{ref}/assign",
    response_model=AssignOut,
    dependencies=[Depends(require_role(*STAFF)), Depends(complaint_in_scope)],
    summary="Assign or reassign who handles a complaint",
)
def assign_complaint(ref: str, payload: AssignIn, request: Request, db: DbSession, user: CurrentUser) -> AssignOut:
    """
    Managers, reviewers and administrators assign any complaint to any active
    member of staff. An agent may only take a complaint in their own scope for
    themselves, or hand back one they hold (FR ii). Evaluators read; they do
    not assign. Every change is audited with the before and after.
    """
    if user.role == UserRole.EVALUATOR:
        raise PermissionError_("Evaluators have read-only access.")
    complaint = _load(db, ref)
    if user.role == UserRole.AGENT:
        taking = payload.user_id is not None and payload.user_id == user.id
        releasing = payload.user_id is None and complaint.assigned_to == user.id
        if not (taking or releasing):
            raise PermissionError_("An agent can take a complaint for themselves or hand back their own, not assign others.")
    assignee = None
    if payload.user_id is not None:
        assignee = db.get(User, payload.user_id)
        if assignee is None or not assignee.is_active or assignee.role not in (
            UserRole.AGENT, UserRole.REVIEWER, UserRole.MANAGER, UserRole.ADMIN,
        ):
            raise ValidationError("Assign to an active agent, reviewer, manager or administrator.")
    before = str(complaint.assigned_to) if complaint.assigned_to else None
    complaint.assigned_to = assignee.id if assignee else None
    record_audit(
        db, entity_type="complaint", entity_id=complaint.id, action="ASSIGN", actor=user,
        before={"assigned_to": before},
        after={"assigned_to": str(assignee.id) if assignee else None, "assignee": assignee.full_name if assignee else None},
        request=request,
    )
    db.flush()
    return AssignOut(
        public_ref=complaint.public_ref,
        assigned_to=AssigneeOut(id=assignee.id, full_name=assignee.full_name, role=assignee.role) if assignee else None,
    )


@router.get(
    "/{ref}/lifecycle",
    response_model=LifecycleOut,
    dependencies=[Depends(require_role(*STAFF)), Depends(complaint_in_scope)],
    summary="Status, history and the moves available next",
)
def complaint_lifecycle(ref: str, db: DbSession) -> LifecycleOut:
    """
    How this complaint reached its current status (FR lxv; SRS Step 60).

    ``available_actions`` is what a human may move it to next, so the options
    offered are the options that will be accepted. An interface that offers a
    move the API refuses teaches people to distrust it.
    """
    complaint = _load(db, ref)
    return LifecycleOut(
        public_ref=complaint.public_ref,
        status=complaint.status,
        available_actions=lifecycle.available_actions(complaint),
        history=[StatusHistoryRowOut(**row) for row in lifecycle.history(db, complaint.id)],
    )


@router.post(
    "/{ref}/status",
    response_model=LifecycleOut,
    dependencies=[Depends(require_role(*STAFF)), Depends(complaint_in_scope)],
    summary="Move a complaint to another status",
)
def change_complaint_status(
    ref: str,
    payload: StatusChangeIn,
    db: DbSession,
    user: CurrentUser,
    request: Request,
) -> LifecycleOut:
    """
    Move one complaint, recording who moved it and why.

    A move outside the declared graph is refused with 422 naming what *is*
    permitted, rather than accepted and quietly recorded. The alternative is a
    complaint that reaches CLOSED without anyone resolving it and a dashboard
    that counts it as handled.

    ``ANALYZING``, ``ANALYZED`` and ``FAILED`` are refused here whatever the
    graph says: they are consequences of the pipeline, and a human setting one
    by hand would put the complaint in a state nothing downstream produced.
    """
    complaint = _load(db, ref)
    requested = payload.to_status.strip().upper()

    if requested in lifecycle.MACHINE_ONLY:
        raise ValidationError(
            f"{requested} is set by the pipeline, not by hand. "
            "Re-analyse the complaint instead."
        )

    before = complaint.status
    try:
        lifecycle.transition(
            db, complaint, requested, actor=user, reason=payload.reason
        )
    except lifecycle.TransitionRefused as exc:
        raise ValidationError(exc.detail) from exc

    record_audit(
        db,
        entity_type="complaint",
        entity_id=complaint.id,
        action="STATUS_CHANGE",
        actor=user,
        before={"status": before},
        after={"status": complaint.status},
        reason=payload.reason,
        request=request,
    )
    db.commit()

    return LifecycleOut(
        public_ref=complaint.public_ref,
        status=complaint.status,
        available_actions=lifecycle.available_actions(complaint),
        history=[StatusHistoryRowOut(**row) for row in lifecycle.history(db, complaint.id)],
    )



# ══════════════════════════════════════════════════════════════
# suggested response (SRS: agents see a suggested response)
# ══════════════════════════════════════════════════════════════
@router.get(
    "/{ref}/responses",
    dependencies=[Depends(require_role(*STAFF)), Depends(complaint_in_scope)],
    summary="Drafted replies for a complaint, newest last",
)
def list_responses(ref: str, db: DbSession) -> list[dict[str, Any]]:
    from genai_pipeline.response import drafts_for_complaint

    return drafts_for_complaint(db, _load(db, ref).id)


@router.post(
    "/{ref}/responses",
    dependencies=[Depends(require_role(*STAFF)), Depends(complaint_in_scope)],
    summary="Draft a suggested reply from the verified decision",
)
@limiter.limit("20/minute")
def draft_response(ref: str, request: Request, response: Response, db: DbSession, user: CurrentUser) -> dict[str, Any]:
    """
    Write a reply from the *reconciled* record -- what the rules confirmed --
    and run it through the response guard, which blocks any promise the
    eligibility rules do not authorise. Nothing is sent: an agent reads it.
    """
    from genai_pipeline.response import drafts_for_complaint, generate_response
    from src.db.models import EligibilityDecision

    complaint = _load(db, ref)
    decision = latest_decision(db, complaint.id)
    if decision is None or not decision.reconciled:
        raise ValidationError("This complaint has not been analysed yet, so there is nothing verified to reply from.")
    eligibility = [
        {
            "eligibility_type": row.eligibility_type, "python_outcome": row.final_outcome,
            "rule_ref": row.rule_ref, "policy_ref": {"doc_ref": row.policy_ref, "section_ref": row.section_ref},
            "max_amount": float(row.max_amount) if row.max_amount is not None else None,
            "currency": row.currency, "reason": row.reason,
            "requires_human_approval": row.requires_human_approval,
        }
        for row in db.execute(select(EligibilityDecision).where(EligibilityDecision.complaint_id == complaint.id)).scalars()
    ]
    result = generate_response(db, complaint, reconciled=decision.reconciled, eligibility=eligibility)
    if not result.ok and not getattr(result, "response_id", None):
        raise ValidationError(f"A reply could not be drafted: {result.failure_detail or result.failure_reason}.")
    record_audit(db, actor=user, entity_type="complaint", entity_id=str(complaint.id), action="RESPONSE_DRAFTED", request=request)
    drafts = drafts_for_complaint(db, complaint.id)
    return drafts[-1] if drafts else {}
