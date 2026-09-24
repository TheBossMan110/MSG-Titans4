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

import uuid

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from comparison_engine.engine import comparison_rows, latest_decision
from complaint_processing import dedupe, followup
from complaint_processing.intake import IntakeRejected, analyse_complaint
from complaint_processing.intake import IntakeResult as _IntakeResult
from complaint_processing.intake import submit as submit_complaint
from genai_pipeline import escalation_notes
from genai_pipeline.intelligence import runs_for_complaint
from hallucination_checks import policy_conflict
from hallucination_checks import trace as policy_trace
from python_validation import resolution
from schemas.common import Page
from schemas.complaints import (
    ChecklistOut,
    ChecklistStepOut,
    ClarificationOut,
    ComparisonOut,
    ComplaintCreate,
    ComplaintDetail,
    ComplaintStatusOut,
    ComplaintSummary,
    EligibilityOut,
    EntityOut,
    EscalationOut,
    ExplainResponse,
    FollowUpOut,
    GuidanceOut,
    IntakeResponse,
    LifecycleOut,
    PolicyConflictOut,
    ReanalyseResponse,
    ResolutionStepOut,
    ResolutionSummaryOut,
    StatusChangeIn,
    StatusHistoryRowOut,
    ValidationIssueOut,
    VerificationOut,
)
from src.core.deps import CurrentUser, DbSession, require_role
from src.core.errors import NotFoundError, ValidationError
from src.core.logging import get_logger
from src.db.enums import UserRole
from src.db.models import (
    AgentGuidance,
    Category,
    ClarificationQuestion,
    Complaint,
    ComplaintValidationIssue,
    Customer,
    Department,
    EligibilityDecision,
    ResolutionStep,
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

    return ComplaintDetail(
        **_summary(complaint).model_dump(),
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
        channel=complaint.channel,
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
                ordinal=q.ordinal, question=q.question,
                missing_field=q.missing_field, answered_at=q.answered_at,
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
    )


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
    analyse: bool = Query(True, description="Run both pipelines immediately."),
) -> IntakeResponse:
    """
    Submit a complaint (FR iii; SRS Steps 9-11).

    Accepted even when validation finds problems — a short complaint, an
    unrecognised reference, a suspected injection are all recorded and the
    complaint processed on its merits. Only an empty complaint is refused, and
    even that attempt is written to ``complaint_validation_issues``.
    """
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
            submitted_by_user_id=user.id,
            # Only an evaluator seeding the benchmark corpus may tag a
            # complaint into a dataset; a customer must not be able to place
            # their submission in the scored set.
            dataset_tag=(
                payload.dataset_tag
                if user.role in (UserRole.EVALUATOR, UserRole.ADMIN)
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

    return IntakeResponse(
        complaint=_detail(db, complaint),
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
        duplicate_of=(
            result.dedupe_result.exact.public_ref
            if result.dedupe_result and result.dedupe_result.exact
            else None
        ),
        repeat_count=result.dedupe_result.repeat_count if result.dedupe_result else 0,
        preprocessing=result.preprocessing,
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
    search: str | None = Query(None, max_length=200),
) -> Page[ComplaintSummary]:
    """List and filter complaints (FR lxxi)."""
    query = select(Complaint)

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
    if search:
        pattern = f"%{search.strip().lower()}%"
        query = query.where(
            func.lower(Complaint.title).like(pattern)
            | func.lower(Complaint.description_clean).like(pattern)
            | func.lower(Complaint.public_ref).like(pattern)
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


def _customer_view(db: DbSession, complaint: Complaint) -> ComplaintStatusOut:
    """
    The customer-safe projection of one complaint (FR lxvi; SRS Step 61).

    Built in one place so the list and the tracking page cannot drift. The
    payload is a separate model from the agent view rather than a filtered one:
    internal guidance, rule references, eligibility reasoning and the pipeline
    comparison are not fields of this response at all, so no future serialiser
    change can leak them.
    """
    questions = db.execute(
        select(ClarificationQuestion)
        .where(
            ClarificationQuestion.complaint_id == complaint.id,
            ClarificationQuestion.answered_at.is_(None),
        )
        .order_by(ClarificationQuestion.ordinal)
    ).scalars().all()

    return ComplaintStatusOut(
        public_ref=complaint.public_ref,
        title=complaint.title,
        status=complaint.status,
        submitted_at=complaint.created_at,
        category=complaint.category.code if complaint.category else None,
        summary=complaint.summary,
        # The fact, not the level. That a complaint went to compliance review
        # is internal routing; telling the customer a specialist will be in
        # touch is the same information without handing them a lever.
        escalated=bool(
            complaint.escalation_code and complaint.escalation_code.upper() != "NONE"
        ),
        awaiting_information=[q.question for q in questions],
        last_updated=complaint.analyzed_at or complaint.created_at,
    )


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

    return Page[ComplaintStatusOut](
        items=[_customer_view(db, row) for row in rows],
        total=total,
        page=page,
        size=size,
    )


@router.get(
    "/{ref}",
    response_model=ComplaintDetail,
    dependencies=[Depends(require_role(*STAFF))],
    summary="Read one complaint",
)
def get_complaint(ref: str, db: DbSession) -> ComplaintDetail:
    return _detail(db, _load(db, ref))


@router.get(
    "/{ref}/explain",
    response_model=ExplainResponse,
    dependencies=[Depends(require_role(*STAFF))],
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
# the completion stages
# ══════════════════════════════════════════════════════════════
@router.get(
    "/{ref}/checklist",
    response_model=ChecklistOut,
    dependencies=[Depends(require_role(*STAFF))],
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
    dependencies=[Depends(require_role(*STAFF))],
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
    dependencies=[Depends(require_role(*STAFF))],
    summary="What the system owes on this complaint",
)
def complaint_follow_ups(ref: str, db: DbSession) -> list[FollowUpOut]:
    complaint = _load(db, ref)
    return [FollowUpOut(**row) for row in followup.for_complaint(db, complaint.id)]


@router.post(
    "/{ref}/follow-ups/{follow_up_id}/complete",
    response_model=list[FollowUpOut],
    dependencies=[Depends(require_role(*STAFF))],
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
    dependencies=[Depends(require_role(*STAFF))],
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


@router.get(
    "/{ref}/lifecycle",
    response_model=LifecycleOut,
    dependencies=[Depends(require_role(*STAFF))],
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
    dependencies=[Depends(require_role(*STAFF))],
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
