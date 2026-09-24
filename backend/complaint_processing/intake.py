"""
Complaint intake (FR iii; SRS Steps 9-11), and the write that closes the loop.

This is where a submission becomes a record and where everything the two
pipelines concluded stops being an in-memory result and becomes rows.

The order is fixed and each step earns its place:

1. **Pre-process** — normalise, keeping the original byte for byte.
2. **Scan** for injection. Detection never refuses the complaint.
3. **Validate** (SRS Step 10). Only an empty complaint is rejected; everything
   else is accepted with a recorded finding.
4. **Deduplicate** — link duplicates, count prior *unresolved* contacts. The
   repeat count comes from stored records, never from the complaint claiming
   to be a repeat.
5. **Persist** the complaint, so it exists even if analysis fails next.
6. **Analyse** — Pipeline 2 always, Pipeline 1 if a provider answers,
   reconciled by the comparison engine.
7. **Write back** the reconciled classification and its children.

Step 5 before step 6 is the important ordering. A complaint that is accepted
and then fails analysis must still be a complaint someone can find and work on
by hand. Persisting only on success would lose exactly the submissions that
most need a human.

**Nothing here decides anything.** Category, department, urgency, priority and
escalation are written from the *reconciled* record produced by the comparison
engine, which took them from the rule engine. Intake is plumbing, and keeping
it that way is what stops a convenience default from quietly becoming policy.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from comparison_engine import reconcile
from comparison_engine.engine import ReconciliationResult
from complaint_processing import dedupe, followup, validation
from complaint_processing.entities import extract_entities, load_entity_patterns
from complaint_processing.preprocess import preprocess
from python_validation import resolution
from security.injection_defense import record_events, scan
from src.core.logging import get_logger
from src.db.enums import (
    Channel,
    ComplaintStatus,
    EntityExtractor,
    EscalationTrigger,
    GuidanceKind,
    GuidanceSource,
    ResolutionStepSource,
    ResolutionStepStatus,
    VerificationOutcome,
)
from src.db.models import (
    AgentGuidance,
    Category,
    ClarificationQuestion,
    Complaint,
    ComplaintEntity,
    Customer,
    Department,
    EligibilityDecision,
    Escalation,
    ResolutionStep,
    Subcategory,
)
from src.services import lifecycle, review, sla

log = get_logger("complaint_processing.intake")

PUBLIC_REF_PREFIX = "CMP"


class IntakeRejected(Exception):
    """The submission could not be accepted. Carries the recorded findings."""

    def __init__(self, report: validation.ValidationReport):
        self.report = report
        codes = ", ".join(report.codes)
        super().__init__(f"complaint rejected: {codes}")


@dataclass(slots=True)
class IntakeResult:
    """Everything intake produced for one submission."""

    complaint: Complaint | None = None
    validation_report: validation.ValidationReport | None = None
    dedupe_result: dedupe.DedupeResult | None = None
    reconciliation: ReconciliationResult | None = None
    injection: dict[str, Any] = field(default_factory=dict)
    preprocessing: dict[str, Any] = field(default_factory=dict)
    entities_extracted: int = 0
    analysed: bool = False
    analysis_error: str | None = None

    @property
    def public_ref(self) -> str | None:
        return self.complaint.public_ref if self.complaint else None

    def summary(self) -> dict[str, Any]:
        return {
            "public_ref": self.public_ref,
            "status": self.complaint.status if self.complaint else None,
            "analysed": self.analysed,
            "analysis_error": self.analysis_error,
            "preprocessing": self.preprocessing,
            "injection_suspected": bool(self.injection.get("suspected")),
            "validation": (
                self.validation_report.summary() if self.validation_report else None
            ),
            "duplicates": (
                self.dedupe_result.summary() if self.dedupe_result else None
            ),
            "entities": self.entities_extracted,
            "verification": (
                self.reconciliation.verification.summary()
                if self.reconciliation
                else None
            ),
        }


# ══════════════════════════════════════════════════════════════
# references
# ══════════════════════════════════════════════════════════════
def next_public_ref(db: Session) -> str:
    """
    The next customer-facing reference, ``CMP-000123``.

    Derived from the row count rather than a sequence so it behaves the same
    on SQLite and PostgreSQL — the offline demo fallback has to produce
    references that look identical to the hosted one.
    """
    count = db.execute(select(func.count()).select_from(Complaint)).scalar_one()
    return f"{PUBLIC_REF_PREFIX}-{count + 1:06d}"


def next_customer_ref(db: Session) -> str:
    """The next customer reference, ``CUST-000042``."""
    count = db.execute(select(func.count()).select_from(Customer)).scalar_one()
    return f"CUST-{count + 1:06d}"


def find_or_create_customer(
    db: Session,
    *,
    email: str | None,
    name: str | None = None,
    phone: str | None = None,
) -> Customer | None:
    """
    Match a customer by email, or create one.

    Returns ``None`` for an anonymous submission rather than inventing a
    customer record — an anonymous complaint is still a complaint, and a
    fabricated identity would corrupt the repeat count for whoever that
    identity happened to collide with.
    """
    if not email:
        return None

    normalised = email.strip().lower()
    existing = db.execute(
        select(Customer).where(func.lower(Customer.email) == normalised)
    ).scalars().first()
    if existing is not None:
        return existing

    customer = Customer(
        external_ref=next_customer_ref(db),
        # The local part is a placeholder until a real name is supplied; the
        # column is not nullable and the address itself must not be shown to
        # an agent as a name.
        display_name=(name or "").strip() or normalised.split("@")[0],
        email=normalised,
        phone=phone,
    )
    db.add(customer)
    db.flush()
    log.info("customer_created", ref=customer.external_ref)
    return customer


# ══════════════════════════════════════════════════════════════
# intake
# ══════════════════════════════════════════════════════════════
def submit(
    db: Session,
    *,
    title: str,
    description: str,
    customer_email: str | None = None,
    customer_name: str | None = None,
    product: str | None = None,
    order_ref: str | None = None,
    transaction_ref: str | None = None,
    amount: float | None = None,
    currency: str | None = None,
    channel: str = Channel.WEB,
    requested_resolution: str | None = None,
    attachments: list[dict[str, Any]] | None = None,
    submitted_by_user_id: uuid.UUID | None = None,
    dataset_tag: str | None = None,
    analyse: bool = True,
    run_genai: bool = True,
) -> IntakeResult:
    """
    Accept a complaint, record it, and analyse it.

    Raises :class:`IntakeRejected` only for an empty complaint. Every other
    finding is recorded and the complaint accepted, because a customer with a
    badly-formed complaint still has a complaint.
    """
    result = IntakeResult()

    # ── 1. pre-process ──
    prepared = preprocess(description)
    result.preprocessing = prepared.summary()

    # ── 2. injection scan ──
    scan_result = scan(db, prepared.clean)
    result.injection = scan_result.summary()

    # ── 3. validate ──
    report = validation.validate_submission(
        title=title,
        description=description,
        clean_description=prepared.clean,
        order_ref=order_ref,
        transaction_ref=transaction_ref,
        attachments=attachments,
        injection_suspected=scan_result.suspected,
        truncated=prepared.truncated,
        # The same configured regexes the entity extractor uses, so a
        # reference cannot pass intake and then be invisible to the rules.
        entity_patterns=load_entity_patterns(db),
    )
    result.validation_report = report

    if report.rejected:
        # No complaints row is created, but the attempt is recorded so a
        # refused intake is visible in the audit rather than vanishing.
        validation.persist(
            db, report,
            submitted_ref=(title or "")[:120] or "untitled",
            submitted_by_user_id=submitted_by_user_id,
        )
        log.warning("complaint_rejected", codes=report.codes)
        raise IntakeRejected(report)

    # ── 4. duplicates and repeats ──
    customer = find_or_create_customer(
        db, email=customer_email, name=customer_name
    )
    duplicates = dedupe.detect(
        db,
        text=prepared.clean,
        customer_id=customer.id if customer else None,
        order_ref=order_ref,
    )
    result.dedupe_result = duplicates

    if duplicates.exact is not None:
        validation.add_duplicate_issue(
            report,
            public_ref=duplicates.exact.public_ref,
            similarity=duplicates.exact.similarity,
        )

    # ── 5. persist the complaint ──
    complaint = Complaint(
        public_ref=next_public_ref(db),
        customer_id=customer.id if customer else None,
        submitted_by_user_id=submitted_by_user_id,
        title=(title or "").strip()[:255] or "Untitled complaint",
        description_raw=prepared.raw,
        description_clean=scan_result.sanitised or prepared.clean,
        product=product,
        order_ref=order_ref,
        transaction_ref=transaction_ref,
        amount=amount,
        currency=currency,
        channel=channel,
        requested_resolution=requested_resolution,
        status=ComplaintStatus.NEW,
        injection_suspected=scan_result.suspected,
        is_duplicate=duplicates.is_duplicate,
        repeat_count=duplicates.repeat_count,
        previous_complaint_id=(
            duplicates.repeats[0].complaint_id if duplicates.repeats else None
        ),
        dataset_tag=dataset_tag,
    )
    db.add(complaint)
    db.flush()
    result.complaint = complaint

    validation.persist(
        db, report,
        complaint_id=complaint.id,
        submitted_ref=complaint.public_ref,
        submitted_by_user_id=submitted_by_user_id,
    )
    dedupe.persist_links(db, complaint.id, duplicates)

    if scan_result.suspected:
        record_events(
            db, scan_result, source_type="COMPLAINT", complaint_id=complaint.id
        )

    # ── 6. deterministic entity extraction ──
    result.entities_extracted = _persist_entities(db, complaint)

    log.info(
        "complaint_accepted",
        public_ref=complaint.public_ref,
        duplicate=duplicates.is_duplicate,
        repeats=duplicates.repeat_count,
        issues=report.codes,
    )

    if not analyse:
        return result

    # ── 7. analyse and write back ──
    try:
        analyse_complaint(db, complaint, result, run_genai=run_genai)
    except Exception as exc:  # noqa: BLE001 - the complaint must survive this
        # The complaint is already persisted and findable. Analysis failing is
        # a reason for a human to pick it up, not a reason to lose it.
        # force: the complaint must land in FAILED from wherever it happened
        # to be when analysis raised. A refusal here would lose the complaint
        # rather than record the problem.
        lifecycle.transition(
            db, complaint, ComplaintStatus.FAILED,
            reason=f"Analysis failed: {type(exc).__name__}", force=True,
        )
        result.analysis_error = f"{type(exc).__name__}: {exc}"
        log.error(
            "complaint_analysis_failed",
            public_ref=complaint.public_ref, error=result.analysis_error,
            exc_info=True,
        )

    return result


def analyse_complaint(
    db: Session,
    complaint: Complaint,
    result: IntakeResult,
    *,
    run_genai: bool = True,
) -> ReconciliationResult:
    """Run both pipelines, reconcile, and write the outcome onto the complaint."""
    lifecycle.transition(
        db, complaint, ComplaintStatus.ANALYZING, reason="Both pipelines running."
    )
    db.flush()

    reconciliation = reconcile(db, complaint, run_genai=run_genai)
    result.reconciliation = reconciliation
    result.analysed = True

    apply_reconciled(db, complaint, reconciliation, intake_result=result)
    return reconciliation


# ══════════════════════════════════════════════════════════════
# write-back
# ══════════════════════════════════════════════════════════════
def apply_reconciled(
    db: Session,
    complaint: Complaint,
    reconciliation: ReconciliationResult,
    *,
    intake_result: IntakeResult | None = None,
) -> None:
    """
    Write the reconciled decision onto the complaint and its children.

    Reads only ``reconciliation.reconciled`` — the record the comparison engine
    produced after the rules had their say. Reading Pipeline 1's raw output
    here would let a classification the rules overrode reach the agent view by
    the back door.
    """
    reconciled = reconciliation.reconciled
    outcome = reconciliation.validation.outcome
    intelligence = (
        reconciliation.intelligence.intelligence
        if reconciliation.intelligence
        else None
    )

    # ── classification ──
    complaint.category_id = _code_to_id(db, Category, reconciled.get("category"))
    complaint.subcategory_id = _code_to_id(
        db, Subcategory, reconciled.get("subcategory")
    )
    complaint.department_id = _code_to_id(db, Department, reconciled.get("department"))
    complaint.support_department_id = _code_to_id(
        db, Department, reconciled.get("support_department")
    )
    complaint.urgency = reconciled.get("urgency")
    complaint.priority_code = reconciled.get("priority")
    complaint.escalation_code = reconciled.get("escalation_level")
    complaint.verification_outcome = reconciliation.verification.outcome

    # ── language-surface fields, which only the model produces ──
    if intelligence is not None:
        complaint.sentiment = intelligence.sentiment
        complaint.primary_issue = (intelligence.primary_issue or "")[:255] or None
        complaint.secondary_issue = (intelligence.secondary_issue or "")[:255] or None
        complaint.summary = intelligence.summary
        # Analytics only. SRS 1.8 #6: these must never reach the rule engine,
        # and the rule engine has no parameter through which they could.
        complaint.emotion_indicators = list(intelligence.emotion_indicators or [])
        complaint.missing_information = list(intelligence.missing_information or [])

    # ── status ──
    #
    # Through the same door a human uses, and subject to the same graph. The
    # history is then the whole account of how a complaint reached its current
    # state, rather than only the part somebody touched by hand.
    lifecycle.transition(
        db, complaint, _status_for(reconciliation.verification.outcome),
        reason=f"Verification outcome: {reconciliation.verification.outcome}.",
    )
    complaint.analyzed_at = datetime.now(UTC)
    complaint.validated_at = datetime.now(UTC)

    # ── children ──
    _record_escalation(db, complaint, reconciliation)
    _persist_resolution_steps(db, complaint, reconciliation, intelligence, outcome)
    _persist_guidance(db, complaint, intelligence, outcome)
    _persist_clarifications(db, complaint, intelligence)
    _persist_eligibility(db, complaint, reconciliation)

    if intelligence is not None:
        _persist_entities(db, complaint, intelligence=intelligence)

    db.flush()

    # ── the two downstream consequences of a decision ──
    #
    # The queue is derived from the stored decision rather than from a second
    # rule of its own: deciding twice is how the queue and the verdict drift
    # apart, and then the queue stops meaning what the decision says.
    #
    # Intake findings marked ROUTED_TO_REVIEW are passed in alongside the
    # decision's own reasons: a suspected injection or an unresolvable order
    # reference needs a human even when both pipelines agreed about the
    # classification.
    intake_reasons = (
        validation.review_reasons(intake_result.validation_report)
        if intake_result and intake_result.validation_report
        else []
    )
    review.enqueue(db, complaint, reasons=intake_reasons)

    # ── the completion stages ──
    #
    # Each reads the reconciled record, so none of them can be influenced by a
    # classification the rules already overrode.
    eligibility = reconciliation.validation.eligibility or []

    # Classify every stored step: which obligations are outstanding, which
    # generated suggestions are traceable, and which are forbidden outright.
    resolution.classify(db, complaint.id, eligibility=eligibility)

    # Work out what the system now owes the customer, and when.
    followup.apply(db, complaint, reconciled=reconciled, eligibility=eligibility)

    # The handover note, for an escalated complaint only. It calls a provider,
    # so it is best-effort: an outage costs the note, never the escalation.
    #
    # ``intelligence is None`` means Pipeline 1 was deliberately skipped -- the
    # offline demo path, or a caller that asked for rules only. Reaching for a
    # provider here would make ``run_genai=False`` a lie and spend the free-tier
    # quota a caller just declined to spend.
    if reconciled.get("escalation_required") and reconciliation.intelligence is not None:
        _write_escalation_note(db, complaint, reconciliation, reconciled, eligibility)

    # The SLA clock is recomputed rather than set once, because the due date
    # derives from the complaint's *current* priority. A re-analysis that
    # raises P2 to P0 must tighten the deadline with it.
    sla.apply(db, complaint)

    db.flush()
    log.info(
        "complaint_analysed",
        public_ref=complaint.public_ref,
        outcome=reconciliation.verification.outcome,
        status=complaint.status,
    )


def _record_escalation(
    db: Session, complaint: Complaint, reconciliation: ReconciliationResult
) -> None:
    """
    Record a rule-derived escalation (SRS Step 38; SRS 1.8 #7).

    ``triggered_by = PYTHON_RULE`` on a complaint the model rated low-urgency
    is precisely the Escalation Trap demonstration, and it has to be a row
    rather than a column: the analytics break escalations down by trigger, and
    a reviewer-raised escalation and a rules-forced one are different evidence.

    One row per (complaint, level). Re-analysis that reaches the same level
    does not stack a second record.
    """
    level = complaint.escalation_code
    if not level or str(level).upper() == "NONE":
        return

    already = db.execute(
        select(Escalation).where(
            Escalation.complaint_id == complaint.id,
            Escalation.escalation_code == level,
        )
    ).scalars().first()
    if already is not None:
        return

    outcome = reconciliation.validation.outcome
    floor = getattr(outcome, "escalation_floor_code", None)
    refs = getattr(outcome, "mandatory_escalation_refs", None) or []

    reason = (
        f"Mandatory escalation floor {floor} derived by "
        f"{', '.join(refs)}." if refs and floor
        else f"Escalated to {level} by the rule engine."
    )

    db.add(
        Escalation(
            complaint_id=complaint.id,
            escalation_code=level,
            triggered_by=EscalationTrigger.PYTHON_RULE,
            rule_ref=refs[0] if refs else None,
            reason=reason,
            to_department_id=complaint.department_id,
        )
    )
    db.flush()
    log.info(
        "escalation_recorded",
        public_ref=complaint.public_ref, level=level, rules=refs[:3],
    )


def _write_escalation_note(
    db: Session,
    complaint: Complaint,
    reconciliation: ReconciliationResult,
    reconciled: dict[str, Any],
    eligibility: list[dict[str, Any]],
) -> None:
    """
    Generate the handover note, tolerating a provider outage.

    Deliberately swallowed: the escalation is a rule-derived fact that has
    already been recorded, the complaint is routed and the floor holds. Losing
    the note is a degraded handover, not a failed analysis, and raising here
    would mark a correctly-escalated complaint as FAILED.
    """
    from genai_pipeline import escalation_notes

    outcome = reconciliation.validation.outcome
    rules = list(getattr(outcome, "mandatory_escalation_refs", None) or [])

    try:
        result = escalation_notes.generate(
            db,
            complaint,
            reconciled=reconciled,
            eligibility=eligibility,
            escalation_rules=rules,
        )
    except Exception as exc:  # noqa: BLE001 - a missing note must not fail intake
        log.warning(
            "escalation_note_failed",
            public_ref=complaint.public_ref, error=f"{type(exc).__name__}: {exc}",
        )
        return

    if not result.ok:
        log.info(
            "escalation_note_skipped",
            public_ref=complaint.public_ref, reason=result.failure_reason,
        )


def _status_for(outcome: str) -> str:
    """
    Map a verification outcome to a complaint status.

    Anything a human must look at lands in MANUAL_REVIEW rather than being
    marked analysed, so the queue is populated by the decision rather than by
    a separate rule that could drift from it.
    """
    if outcome in (
        VerificationOutcome.MANUAL_REVIEW_REQUIRED,
        VerificationOutcome.BLOCKED,
    ):
        return ComplaintStatus.MANUAL_REVIEW
    return ComplaintStatus.ANALYZED


def _code_to_id(db: Session, model: Any, code: str | None) -> uuid.UUID | None:
    """Resolve a taxonomy code to its row id, tolerating an unknown one."""
    if not code:
        return None
    row = db.execute(
        select(model).where(model.code == str(code).strip().upper())
    ).scalars().first()
    if row is None:
        log.warning("unknown_code_on_writeback", model=model.__name__, code=code)
        return None
    return row.id


# ══════════════════════════════════════════════════════════════
# children
# ══════════════════════════════════════════════════════════════
def _persist_entities(
    db: Session, complaint: Complaint, *, intelligence: Any = None
) -> int:
    """
    Store extracted entities.

    Python's regex pass and the model's pass are stored **separately**, tagged
    with ``extracted_by``, and never merged. Merging them would destroy the
    comparison SRS Step 16 asks for, and would let a model-invented order
    number sit indistinguishably beside one actually found in the text.
    """
    source = EntityExtractor.GENAI if intelligence is not None else EntityExtractor.PYTHON

    db.query(ComplaintEntity).filter(
        ComplaintEntity.complaint_id == complaint.id,
        ComplaintEntity.extracted_by == source,
    ).delete()

    rows = 0
    if intelligence is None:
        text = complaint.description_clean or complaint.description_raw or ""
        found = extract_entities(text, load_entity_patterns(db))
        for entity in found.entities:
            db.add(
                ComplaintEntity(
                    complaint_id=complaint.id,
                    entity_type=entity.entity_type,
                    value=entity.value[:512],
                    normalized=(entity.normalized or "")[:512] or None,
                    span_start=entity.span_start,
                    span_end=entity.span_end,
                    extracted_by=EntityExtractor.PYTHON,
                )
            )
            rows += 1
    else:
        for entity in intelligence.entities or []:
            db.add(
                ComplaintEntity(
                    complaint_id=complaint.id,
                    entity_type=entity.entity_type[:64].upper(),
                    value=entity.value[:512],
                    extracted_by=EntityExtractor.GENAI,
                )
            )
            rows += 1

    db.flush()
    return rows


def _persist_resolution_steps(
    db: Session,
    complaint: Complaint,
    reconciliation: ReconciliationResult,
    intelligence: Any,
    outcome: Any,
) -> None:
    """
    Store the resolution steps from both sources (SRS Steps 27-28).

    Rule-required obligations are written as ``RULE_REQUIRED`` and the model's
    suggestions as ``GENAI``. A rule obligation is never marked satisfied here:
    whether "verify the shipment in the tracking system" was actually done is
    not readable from generated text, so it stays MISSING until an agent ticks
    it off. Guessing would turn a checklist into a rubber stamp.
    """
    db.query(ResolutionStep).filter(
        ResolutionStep.complaint_id == complaint.id
    ).delete()

    validation_run_id = reconciliation.validation.validation_run_id
    genai_run_id = (
        reconciliation.intelligence.run_ids[-1]
        if reconciliation.intelligence and reconciliation.intelligence.run_ids
        else None
    )

    ordinal = 0
    for action in getattr(outcome, "required_actions", None) or []:
        db.add(
            ResolutionStep(
                complaint_id=complaint.id,
                validation_run_id=validation_run_id,
                ordinal=ordinal,
                text=str(action),
                source=ResolutionStepSource.RULE_REQUIRED,
                status=ResolutionStepStatus.MISSING,
                explanation="Required by the rule matrix; an agent must confirm it.",
            )
        )
        ordinal += 1

    if intelligence is not None:
        for step in intelligence.resolution_steps or []:
            db.add(
                ResolutionStep(
                    complaint_id=complaint.id,
                    genai_run_id=genai_run_id,
                    ordinal=ordinal,
                    text=step.step,
                    action_code=step.action_code,
                    source=ResolutionStepSource.GENAI,
                    status=ResolutionStepStatus.SUPPORTED,
                    policy_ref=step.policy_ref,
                )
            )
            ordinal += 1

    db.flush()


def _persist_guidance(
    db: Session, complaint: Complaint, intelligence: Any, outcome: Any
) -> None:
    """
    Store agent guidance (SRS Step 45).

    Prohibitions derived by the rule engine are written as **mandatory**
    CAUTION items that an agent cannot dismiss. Model-generated guidance is
    advisory. The difference is the point: "do not confirm a refund before
    eligibility is verified" is policy, not a suggestion.
    """
    db.query(AgentGuidance).filter(AgentGuidance.complaint_id == complaint.id).delete()

    ordinal = 0
    for action in getattr(outcome, "prohibited_actions", None) or []:
        db.add(
            AgentGuidance(
                complaint_id=complaint.id,
                ordinal=ordinal,
                text=f"Do not: {action}",
                kind=GuidanceKind.CAUTION,
                source=GuidanceSource.RULE,
                is_mandatory=True,
            )
        )
        ordinal += 1

    if intelligence is not None:
        for item in intelligence.agent_guidance or []:
            db.add(
                AgentGuidance(
                    complaint_id=complaint.id,
                    ordinal=ordinal,
                    text=item.guidance,
                    kind=item.kind,
                    source=GuidanceSource.GENAI,
                    is_mandatory=False,
                )
            )
            ordinal += 1

    db.flush()


def _persist_clarifications(db: Session, complaint: Complaint, intelligence: Any) -> None:
    """Store clarification questions (SRS Step 43) — ask, never invent."""
    db.query(ClarificationQuestion).filter(
        ClarificationQuestion.complaint_id == complaint.id
    ).delete()

    if intelligence is None:
        db.flush()
        return

    for ordinal, question in enumerate(intelligence.clarification_questions or []):
        db.add(
            ClarificationQuestion(
                complaint_id=complaint.id,
                ordinal=ordinal,
                question=question.question,
                missing_field=question.missing_field,
            )
        )
    db.flush()


def _persist_eligibility(
    db: Session, complaint: Complaint, reconciliation: ReconciliationResult
) -> None:
    """
    Store eligibility decisions (SRS Steps 29-31).

    ``final_outcome`` is the Python one. The model has no vote here: an
    eligibility decision is the single most consequential thing in the system,
    and it is the one the response guard checks every promise against.
    """
    db.query(EligibilityDecision).filter(
        EligibilityDecision.complaint_id == complaint.id
    ).delete()

    for finding in reconciliation.validation.eligibility or []:
        policy_ref = finding.get("policy_ref") or {}
        db.add(
            EligibilityDecision(
                complaint_id=complaint.id,
                eligibility_type=finding["eligibility_type"],
                python_outcome=finding["python_outcome"],
                final_outcome=finding["python_outcome"],
                overridden=False,
                conditions_evaluated=list(finding.get("conditions_evaluated") or []),
                rule_ref=finding.get("rule_ref"),
                policy_ref=policy_ref.get("doc_ref") if isinstance(policy_ref, dict) else None,
                section_ref=(
                    policy_ref.get("section_ref") if isinstance(policy_ref, dict) else None
                ),
                max_amount=finding.get("max_amount"),
                currency=finding.get("currency"),
                reason=finding.get("reason") or "",
                requires_human_approval=bool(finding.get("requires_human_approval")),
            )
        )
    db.flush()
