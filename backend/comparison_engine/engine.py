"""
Where the two pipelines meet (SRS 1.2; Deliverable 8).

Runs Pipeline 2, optionally runs Pipeline 1, compares them field by field,
decides, and persists — ``comparisons`` rows plus one ``verification_decisions``
row, so every figure the UI shows is a stored fact rather than a computation
nobody can audit (SRS 1.8 #17).

**Order is not arbitrary.** Pipeline 2 runs first and unconditionally. It needs
no network, no key and no model, so the complaint is always decided even if
everything after it fails. Pipeline 1 is then an *enhancement* to that decision,
which is what makes the degraded path a real path rather than an error branch.

**Citations are resolved here, not trusted.** Each cited ``chunk_key`` is looked
up and its document version checked, because a well-formed citation to a
superseded policy is a different failure from an invented one and the
traceability score must distinguish them.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from comparison_engine.decision import ReviewReason, VerificationResult, decide, decided_at
from comparison_engine.diff import FieldComparison, compare_all
from comparison_engine.ladders import load_ladders
from genai_pipeline.intelligence import IntelligenceResult, analyse_complaint
from hallucination_checks import citation_validator, policy_conflict
from knowledge_base import retrieval
from python_validation.pipeline import ValidationResult, validate_complaint
from src.core import progress
from src.core.logging import get_logger
from src.db.enums import DocStatus
from src.db.models import AppConfig, Comparison, Complaint, VerificationDecision
from src.core.refcache import reference_data
from src.db.fresh import needs_clearing

log = get_logger("comparison_engine")


@dataclass(slots=True)
class ReconciliationResult:
    """Everything the reconciliation produced for one complaint."""

    complaint_id: uuid.UUID
    verification: VerificationResult
    validation: ValidationResult
    intelligence: IntelligenceResult | None = None
    citations: list[dict[str, Any]] = field(default_factory=list)
    decision_id: uuid.UUID | None = None
    comparison_ids: list[uuid.UUID] = field(default_factory=list)
    citation_report: Any = None

    @property
    def outcome(self) -> str:
        return self.verification.outcome

    @property
    def reconciled(self) -> dict[str, Any]:
        return self.verification.reconciled

    def summary(self) -> dict[str, Any]:
        return {
            "complaint_id": str(self.complaint_id),
            **self.verification.summary(),
            "citations": {
                "total": len(self.citations),
                "resolvable": sum(1 for c in self.citations if c["resolvable"]),
                "active": sum(1 for c in self.citations if c["active"]),
            },
            "genai": self.intelligence.summary() if self.intelligence else None,
            "ruleset_version": self.validation.ruleset_version,
        }


# ══════════════════════════════════════════════════════════════
# configuration
# ══════════════════════════════════════════════════════════════
@reference_data("comparison_config")
def load_comparison_config(
    db: Session,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """
    Severity weights, verification settings and thresholds, from ``app_config``.

    Runtime-editable, which is the point: SRS 1.8 #14 asks for a threshold
    change to take effect without a deploy, and both of these are read on
    every reconciliation rather than cached at import.
    """
    def _read(key: str) -> dict[str, Any]:
        row = db.get(AppConfig, key)
        return row.value if row and isinstance(row.value, dict) else {}

    weights = _read("comparison_weights")
    verification = _read("verification")
    thresholds = _read("thresholds")

    if not weights:
        log.warning(
            "comparison_weights_missing",
            detail="app_config['comparison_weights'] is empty; defaults apply",
        )
    return weights, verification, thresholds


# ══════════════════════════════════════════════════════════════
# citations
# ══════════════════════════════════════════════════════════════
def resolve_citations(
    db: Session,
    intelligence: Any,
    *,
    retrieved_chunk_keys: set[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Resolve every citation the model made, recording *why* each one failed.

    Three distinct verdicts, which the traceability score and the
    hallucination report both depend on keeping apart:

    * **unresolvable** — no such chunk. Fabricated.
    * **resolvable but not active** — a real but superseded or expired policy.
      Formally correct, substantively wrong, and the case SRS 1.8 #10 tests.
    * **resolvable and active but not retrieved** — real, current, and not
      something the model was shown for this complaint, so the support is
      coincidental.
    """
    if intelligence is None:
        return []

    citations: list[dict[str, Any]] = []
    for reference in getattr(intelligence, "policy_refs", None) or []:
        chunk = retrieval.resolve_citation(
            db,
            chunk_key=reference.chunk_key,
            doc_ref=reference.doc_ref,
            section_ref=reference.section_ref,
        )

        active = False
        version_status = None
        if chunk is not None:
            version = chunk.document_version
            version_status = getattr(version, "status", None)
            active = version_status == DocStatus.ACTIVE

        key = reference.chunk_key or (chunk.chunk_key if chunk else None)
        citations.append(
            {
                "chunk_key": reference.chunk_key,
                "doc_ref": reference.doc_ref,
                "section_ref": reference.section_ref,
                "supports": reference.supports,
                "resolvable": chunk is not None,
                "active": active,
                "version_status": version_status,
                "retrieved_for_this_complaint": (
                    None if retrieved_chunk_keys is None else key in retrieved_chunk_keys
                ),
                "resolved_chunk_key": chunk.chunk_key if chunk else None,
            }
        )

    unresolvable = [c["chunk_key"] for c in citations if not c["resolvable"]]
    superseded = [c["chunk_key"] for c in citations if c["resolvable"] and not c["active"]]
    if unresolvable:
        log.warning("citations_unresolvable", keys=unresolvable)
    if superseded:
        log.warning("citations_not_active", keys=superseded)

    return citations


# ══════════════════════════════════════════════════════════════
# persistence
# ══════════════════════════════════════════════════════════════
def persist(
    db: Session,
    complaint: Complaint,
    result: VerificationResult,
    *,
    genai_run_id: uuid.UUID | None,
    validation_run_id: uuid.UUID | None,
) -> tuple[uuid.UUID | None, list[uuid.UUID]]:
    """
    Write the comparison rows and the decision.

    Prior rows for this complaint are cleared first: re-running a complaint
    after a rule change must replace its comparison, not append a second
    contradictory set that the UI would then have to choose between.
    """
    if needs_clearing(db, complaint.id, "comparisons"):
        db.query(Comparison).filter(Comparison.complaint_id == complaint.id).delete()

    rows = [
        Comparison(
            complaint_id=complaint.id,
            genai_run_id=genai_run_id,
            validation_run_id=validation_run_id,
            **comparison.as_row(),
        )
        for comparison in result.comparisons
    ]
    # One flush for the lot: the driver batches the inserts into a single
    # round trip, where a flush per row paid the network latency ten times.
    db.add_all(rows)
    db.flush()
    comparison_ids: list[uuid.UUID] = [row.id for row in rows]

    decision = VerificationDecision(
        complaint_id=complaint.id,
        genai_run_id=genai_run_id,
        validation_run_id=validation_run_id,
        outcome=result.outcome,
        critical_mismatches=result.critical_mismatches,
        high_mismatches=result.high_mismatches,
        total_fields=result.total_fields,
        matched_fields=result.matched_fields,
        agreement_score=result.agreement.value,
        traceability_score=result.traceability.value,
        compliance_score=result.compliance.value,
        requires_review=result.requires_review,
        review_reasons=result.review_reasons,
        reconciled=result.reconciled,
        genai_available=result.genai_available,
        decided_at=decided_at(),
    )
    db.add(decision)
    db.flush()

    return decision.id, comparison_ids


# ══════════════════════════════════════════════════════════════
# the reconciliation
# ══════════════════════════════════════════════════════════════
def reconcile(
    db: Session,
    complaint: Complaint,
    *,
    run_genai: bool = True,
    intelligence: IntelligenceResult | None = None,
    validation: ValidationResult | None = None,
    persist_rows: bool = True,
    **genai_kwargs: Any,
) -> ReconciliationResult:
    """
    Run both pipelines for one complaint and reconcile them.

    ``intelligence`` and ``validation`` can be supplied when a caller has
    already run them — the benchmark does exactly that, so a 500-complaint run
    does not pay for either pipeline twice.

    ``run_genai=False`` forces the degraded path. That is not only a test
    affordance: it is how the system behaves when no key is configured, and it
    still produces a complete, persisted, fully-explained decision.
    """
    # ── Pipeline 2, always, first ──
    if validation is None:
        progress.emit("rules")
        validation = validate_complaint(db, complaint, persist=persist_rows)
        progress.emit("rules", "done", _rules_detail(db, validation))
    outcome = validation.outcome

    # ── Pipeline 1, best effort ──
    if intelligence is None and run_genai:
        intelligence = analyse_complaint(db, complaint, **genai_kwargs)
    elif intelligence is None:
        progress.emit("policy", "skipped", "Not needed without AI analysis")
        progress.emit("ai", "skipped", "AI analysis is off; the company rules decide alone")
    progress.emit("verify")

    genai_result = intelligence.intelligence if intelligence else None
    genai_available = bool(intelligence and intelligence.ok and genai_result is not None)

    if intelligence is not None and not intelligence.ok:
        log.warning(
            "genai_unavailable_for_reconciliation",
            complaint=str(complaint.id),
            reason=intelligence.failure_reason,
        )

    # ── compare ──
    weights, verification_config, thresholds = load_comparison_config(db)
    ladders = load_ladders(db)

    retrieved = set(intelligence.retrieved_chunk_keys) if intelligence else None
    citations = resolve_citations(db, genai_result, retrieved_chunk_keys=retrieved)

    # Full traceability: every reference from all three sources, with the
    # verdict on each, written to complaint_policy_refs. This is the table the
    # Source-Traceability Challenge is answered from -- "pick any generated
    # statement and show us where it came from" is a row, not a search.
    citation_report = citation_validator.validate_all(
        db,
        genai_refs=getattr(genai_result, "policy_refs", None),
        rule_refs=getattr(outcome, "policy_refs", None),
        retrieved_chunk_keys=retrieved,
    )

    comparisons: list[FieldComparison] = compare_all(
        genai_result, outcome, weights=weights, ranks=ladders, thresholds=thresholds
    )

    extra_reasons: list[str] = []
    if validation.outcome and getattr(validation.outcome, "rule_errors", None):
        extra_reasons.append("RULE_CONFLICT")

    genai_run_id = (
        intelligence.run_ids[-1] if intelligence and intelligence.run_ids else None
    )
    if persist_rows:
        citation_validator.persist(
            db, complaint.id, citation_report,
            genai_run_id=genai_run_id,
            validation_run_id=validation.validation_run_id,
        )
        # Two policies this complaint rests on may disagree. Run after the
        # references are stored, because the check reads them back: it
        # compares what the complaint actually ended up citing, not what
        # retrieval happened to offer.
        #
        # And run before the decision, because a contradiction is a reason for
        # a person to look. Precedence already picked the governing policy, but
        # a complaint resting on two policies that disagree is exactly the case
        # SRS 1.8 #10 wants a human to see; recorded only on the references, it
        # never reached the review queue, which reads the decision's reasons.
        conflicts = policy_conflict.check(db, complaint.id)
        if conflicts.detected:
            extra_reasons.append(ReviewReason.POLICY_CONTRADICTION)

    result = decide(
        comparisons,
        outcome,
        ladders=ladders,
        citations=citations,
        genai_available=genai_available,
        verification_config=verification_config,
        extra_review_reasons=extra_reasons,
    )

    progress.emit(
        "verify", "done",
        f"{len(comparisons)} points compared against company policy"
        if genai_available else "Company rules applied on their own",
    )

    decision_id: uuid.UUID | None = None
    comparison_ids: list[uuid.UUID] = []
    if persist_rows:
        decision_id, comparison_ids = persist(
            db, complaint, result,
            genai_run_id=genai_run_id,
            validation_run_id=validation.validation_run_id,
        )

    return ReconciliationResult(
        complaint_id=complaint.id,
        verification=result,
        validation=validation,
        intelligence=intelligence,
        citations=citations,
        decision_id=decision_id,
        comparison_ids=comparison_ids,
        citation_report=citation_report,
    )


def _rules_detail(db: Session, validation: ValidationResult) -> str:
    """What the rules concluded, in words a customer may see: the category only."""
    from src.db.models import Category

    code = getattr(validation.outcome, "category_code", None)
    if not code:
        return "No exact rule matched; a person will classify it"
    name = db.execute(select(Category.name).where(Category.code == code)).scalar()
    return f"Identified as: {name or code.replace('_', ' ').title()}"


# ══════════════════════════════════════════════════════════════
# reporting
# ══════════════════════════════════════════════════════════════
def latest_decision(db: Session, complaint_id: uuid.UUID) -> VerificationDecision | None:
    return db.execute(
        select(VerificationDecision)
        .where(VerificationDecision.complaint_id == complaint_id)
        .order_by(VerificationDecision.created_at.desc())
    ).scalars().first()


def comparison_rows(db: Session, complaint_id: uuid.UUID) -> list[dict[str, Any]]:
    """
    The stored field-by-field comparison — Deliverable 8's table.

    Read back from the database rather than recomputed, so what a report shows
    is provably what the system decided at the time.
    """
    rows = db.execute(
        select(Comparison)
        .where(Comparison.complaint_id == complaint_id)
        .order_by(Comparison.field)
    ).scalars().all()

    return [
        {
            "field": row.field,
            "genai": row.genai_value,
            "python": row.python_value,
            "final": row.final_value,
            "status": row.status,
            "severity": row.severity,
            "winner": row.winner,
            "reason_code": row.reason_code,
            "explanation": row.explanation,
        }
        for row in rows
    ]
