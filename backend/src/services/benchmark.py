"""
Benchmark runner (NFR 1; SRS 1.8 #2, #3; Deliverable 8).

Scores both pipelines against the labelled dataset, field by field, and stores
every comparison so the headline numbers can be re-derived from rows rather
than believed.

**This is the only module that may read a ground-truth label.** The
``expected_*`` columns sit on the complaint because that is the natural place
for them, and a pipeline that could consult them would be scoring its own
homework. :mod:`tests.test_benchmark` greps the pipeline packages to prove
none of them can.

**Accuracy here is real accuracy** — against labels, not against the other
pipeline. The dashboard's "agreement" figure measures Pipeline 1 against
Pipeline 2 and counts two matching errors as a success; this does not.

**Mandatory escalation recall is the number that cannot slip.**
``policy.yaml`` sets its target at 100% and calls it non-negotiable. It asks
one question: of the complaints whose ground truth says escalate, how many did
the system escalate at least that far? Under-escalating one safety complaint
in five hundred is a failure of the whole system, and no other metric
compensates for it. It is computed separately from per-field accuracy because
"escalation accuracy 99.8%" reads like success and hides exactly that case.

**Runs resume.** A run interrupted at complaint 300 of 500 picks up at 301.
On a free-tier API that is the difference between finishing and not.
"""

from __future__ import annotations

import statistics
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from comparison_engine import reconcile
from comparison_engine.ladders import at_or_above, load_ladders
from src.core.config import settings
from src.core.logging import get_logger
from src.db.base import SessionLocal
from src.db.enums import JobStatus
from src.db.models import BenchmarkResult, BenchmarkRun, Complaint
from src.services import dataset

log = get_logger("services.benchmark")

# Field name -> (ground-truth column, reconciled key, comparison kind)
SCORED_FIELDS: dict[str, tuple[str, str, str]] = {
    "category": ("expected_category_code", "category", "exact"),
    "subcategory": ("expected_subcategory_code", "subcategory", "exact"),
    "department": ("expected_department_code", "department", "exact"),
    "urgency": ("expected_urgency", "urgency", "exact"),
    "priority": ("expected_priority_code", "priority", "exact"),
    # Escalation is scored two ways: exactly, and as a floor. The floor is the
    # one that matters -- over-escalating is cautious, under-escalating is a
    # safety failure.
    "escalation_level": ("expected_escalation_code", "escalation_level", "ladder"),
}

NO_ESCALATION = "NONE"

# Concurrency. Modest on purpose: the free-tier providers rate-limit hard, and
# a run that trips a 429 storm takes longer than a slower one that does not.
DEFAULT_WORKERS = 4


def safe_workers(requested: int) -> int:
    """
    How many workers the database can actually serve.

    Each worker opens a session of its own, so concurrency is bounded by the
    connection pool rather than by the CPU. Asking for more than the pool holds
    does not run faster -- it runs until a worker waits past the timeout and
    the run dies part-way through, which on a 500-complaint benchmark is an
    expensive way to learn the limit.

    SQLite is pinned to one worker regardless: it takes a database-level write
    lock, so concurrent writers serialise at best and raise "database is
    locked" at worst. The offline fallback trades throughput for finishing.
    """
    if not settings.is_postgres:
        return 1

    # Leave one connection for the caller's own session, which stays open for
    # the length of the run.
    capacity = max(1, settings.db_pool_size + settings.db_max_overflow - 1)
    allowed = max(1, min(requested, capacity))

    if allowed < requested:
        log.warning(
            "benchmark_workers_clamped",
            requested=requested, allowed=allowed, pool_capacity=capacity,
        )
    return allowed


@dataclass(slots=True)
class FieldScore:
    """
    One field's accuracy across the run.

    The two pipelines have separate denominators. ``scored`` counts every
    labelled occurrence, which is what the rule engine always answers;
    ``genai_scored`` counts only those where the model produced a value.

    Without that split a rules-only run reports the model at 0% accurate,
    which reads as "it got everything wrong" when the truth is "it was never
    asked" -- and the same applies to any complaint analysed during a provider
    outage.
    """

    field: str
    scored: int = 0
    genai_scored: int = 0
    genai_correct: int = 0
    python_correct: int = 0
    agreed: int = 0

    def _pct(self, correct: int, total: int) -> float | None:
        return round(correct / total * 100.0, 2) if total else None

    @property
    def python_accuracy_pct(self) -> float | None:
        return self._pct(self.python_correct, self.scored)

    @property
    def genai_accuracy_pct(self) -> float | None:
        """``None`` when the model contributed nothing to this field."""
        return self._pct(self.genai_correct, self.genai_scored)

    @property
    def agreement_pct(self) -> float | None:
        """``None`` when there was nothing to agree with."""
        return self._pct(self.agreed, self.genai_scored)

    def as_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "scored": self.scored,
            "genai_scored": self.genai_scored,
            "genai_accuracy_pct": self.genai_accuracy_pct,
            "python_accuracy_pct": self.python_accuracy_pct,
            "agreement_pct": self.agreement_pct,
            "genai_correct": self.genai_correct,
            "python_correct": self.python_correct,
        }


@dataclass(slots=True)
class BenchmarkOutcome:
    """Everything one run measured."""

    run_id: uuid.UUID | None = None
    label: str = ""
    dataset_tag: str = ""
    sample_size: int = 0
    processed: int = 0
    failed: int = 0
    skipped_unlabelled: int = 0

    fields: dict[str, FieldScore] = field(default_factory=dict)
    latencies_ms: list[float] = field(default_factory=list)

    escalation_expected: int = 0
    escalation_recalled: int = 0
    escalation_missed: list[str] = field(default_factory=list)
    escalation_over: int = 0

    genai_available_count: int = 0
    errors: list[dict[str, Any]] = field(default_factory=list)

    @property
    def escalation_recall_pct(self) -> float | None:
        """
        The non-negotiable metric.

        ``None`` when the dataset contains no complaint that should escalate —
        which is itself a finding, because a dataset that never tests the floor
        cannot evidence it.
        """
        if self.escalation_expected == 0:
            return None
        return round(self.escalation_recalled / self.escalation_expected * 100.0, 2)

    @property
    def latency(self) -> dict[str, float | None]:
        """
        Per-complaint wall time, including both pipelines and reconciliation.

        p95 rather than a mean: NFR 1 sets a ceiling per complaint, and a mean
        hides the tail that would breach it.
        """
        if not self.latencies_ms:
            return {"mean_ms": None, "p50_ms": None, "p95_ms": None, "max_ms": None}
        ordered = sorted(self.latencies_ms)
        return {
            "mean_ms": round(statistics.fmean(ordered), 1),
            "p50_ms": round(statistics.median(ordered), 1),
            "p95_ms": round(ordered[max(0, int(len(ordered) * 0.95) - 1)], 1),
            "max_ms": round(ordered[-1], 1),
        }

    def metrics(self) -> dict[str, Any]:
        """The stored headline numbers."""
        scored = [f for f in self.fields.values() if f.scored]
        return {
            "sample_size": self.sample_size,
            "processed": self.processed,
            "failed": self.failed,
            "skipped_unlabelled": self.skipped_unlabelled,
            "genai_available_count": self.genai_available_count,
            "by_field": [f.as_dict() for f in self.fields.values()],
            "overall": {
                "genai_accuracy_pct": _mean_pct(
                    [f.genai_accuracy_pct for f in scored]
                ),
                "python_accuracy_pct": _mean_pct(
                    [f.python_accuracy_pct for f in scored]
                ),
                "agreement_pct": _mean_pct([f.agreement_pct for f in scored]),
            },
            "mandatory_escalation": {
                "expected": self.escalation_expected,
                "recalled": self.escalation_recalled,
                "recall_pct": self.escalation_recall_pct,
                "missed": self.escalation_missed[:25],
                "over_escalated": self.escalation_over,
                "target_pct": 100.0,
                "met": self.escalation_recall_pct == 100.0
                if self.escalation_recall_pct is not None
                else None,
            },
            "latency": self.latency,
            "errors": self.errors[:25],
        }


def _mean_pct(values: list[float | None]) -> float | None:
    present = [v for v in values if v is not None]
    return round(statistics.fmean(present), 2) if present else None


# ══════════════════════════════════════════════════════════════
# scoring one complaint
# ══════════════════════════════════════════════════════════════
def _norm(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().upper()
    return text or None


def score_complaint(
    complaint: Complaint,
    reconciliation: Any,
    *,
    ladders: dict[str, dict[str, int]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """
    Score one complaint against its labels.

    Returns ``(field_rows, escalation)``. A field with no label is skipped
    rather than counted as wrong — an unlabelled field is unmeasured, and
    scoring it as a failure would punish the system for the dataset's gaps.
    """
    reconciled = reconciliation.reconciled
    genai = (
        reconciliation.intelligence.intelligence
        if reconciliation.intelligence
        else None
    )

    rows: list[dict[str, Any]] = []

    for name, (label_column, reconciled_key, kind) in SCORED_FIELDS.items():
        expected = _norm(getattr(complaint, label_column, None))
        if expected is None:
            continue

        python_value = _norm(reconciled.get(reconciled_key))
        genai_value = _norm(_genai_field(genai, name))

        if kind == "ladder":
            # At or above the expected level counts as correct. Over-escalating
            # is cautious; under-escalating is the failure.
            python_correct = at_or_above(
                ladders, "escalation_level", python_value, expected
            )
            genai_correct = (
                at_or_above(ladders, "escalation_level", genai_value, expected)
                if genai_value is not None
                else None
            )
        else:
            python_correct = python_value == expected
            genai_correct = genai_value == expected if genai_value is not None else None

        rows.append(
            {
                "field": name,
                "expected_value": expected,
                "genai_value": genai_value,
                "python_value": python_value,
                "genai_correct": genai_correct,
                "python_correct": python_correct,
                "agreed": (
                    genai_value == python_value if genai_value is not None else None
                ),
                "explanation": _explain(
                    name, expected, python_value, genai_value, python_correct
                ),
            }
        )

    return rows, _escalation_check(complaint, reconciled, ladders)


def _genai_field(genai: Any, name: str) -> Any:
    if genai is None:
        return None
    if name == "escalation_level":
        return genai.escalation_level or (
            NO_ESCALATION if not genai.escalation_required else None
        )
    return getattr(genai, name, None)


def _explain(
    name: str,
    expected: str,
    python_value: str | None,
    genai_value: str | None,
    python_correct: bool,
) -> str:
    if python_correct:
        return f"Expected {expected}; the rules derived {python_value or 'nothing'}."
    return (
        f"Expected {expected}; the rules derived {python_value or 'nothing'} "
        f"and the model proposed {genai_value or 'nothing'}."
    )


def _escalation_check(
    complaint: Complaint, reconciled: dict[str, Any], ladders: dict[str, dict[str, int]]
) -> dict[str, Any]:
    """
    Whether the mandatory escalation floor was honoured for this complaint.

    Separate from per-field accuracy because "escalation accuracy 99.8%" reads
    like success while hiding the one safety complaint that was not escalated.
    """
    expected = _norm(complaint.expected_escalation_code)
    actual = _norm(reconciled.get("escalation_level"))

    if expected is None or expected == NO_ESCALATION:
        return {
            "required": False,
            "recalled": None,
            "over_escalated": bool(actual and actual != NO_ESCALATION),
        }

    return {
        "required": True,
        "recalled": at_or_above(ladders, "escalation_level", actual, expected),
        "over_escalated": False,
        "expected": expected,
        "actual": actual,
    }


# ══════════════════════════════════════════════════════════════
# the run
# ══════════════════════════════════════════════════════════════
def _process_one(
    complaint_id: uuid.UUID, *, run_genai: bool
) -> dict[str, Any]:
    """
    Analyse one complaint on its own session.

    Each worker gets a session of its own: SQLAlchemy sessions are not
    thread-safe, and sharing one across a pool produces corruption that looks
    like a logic bug and is anything but.
    """
    started = time.perf_counter()
    db = SessionLocal()
    try:
        complaint = db.get(Complaint, complaint_id)
        if complaint is None:
            return {"complaint_id": complaint_id, "error": "complaint not found"}

        reconciliation = reconcile(db, complaint, run_genai=run_genai)
        ladders = load_ladders(db)
        rows, escalation = score_complaint(
            complaint, reconciliation, ladders=ladders
        )

        complaint.analyzed_at = complaint.analyzed_at or datetime.now(UTC)
        db.commit()

        return {
            "complaint_id": complaint_id,
            "public_ref": complaint.public_ref,
            "rows": rows,
            "escalation": escalation,
            "genai_available": reconciliation.verification.genai_available,
            "latency_ms": (time.perf_counter() - started) * 1000.0,
        }
    except Exception as exc:  # noqa: BLE001 - one bad complaint must not end the run
        db.rollback()
        log.error(
            "benchmark_complaint_failed",
            complaint_id=str(complaint_id), error=str(exc), exc_info=True,
        )
        return {"complaint_id": complaint_id, "error": f"{type(exc).__name__}: {exc}"}
    finally:
        db.close()


def run(
    db: Session,
    *,
    dataset_tag: str,
    label: str | None = None,
    limit: int | None = None,
    run_genai: bool = True,
    workers: int = DEFAULT_WORKERS,
    resume: bool = True,
) -> BenchmarkOutcome:
    """
    Score a dataset.

    ``resume`` skips complaints already analysed, so an interrupted run
    continues rather than restarting — on a rate-limited free tier that is
    often the difference between finishing and not.

    ``run_genai=False`` scores the rule engine alone. That is not a lesser
    mode: it is the configuration the system falls back to during a provider
    outage, and knowing how it scores on its own is worth measuring.
    """
    tag = dataset_tag.strip().upper()
    outcome = BenchmarkOutcome(
        label=label or f"{tag} {datetime.now(UTC):%Y-%m-%d %H:%M}",
        dataset_tag=tag,
    )

    query = select(Complaint.id).where(Complaint.dataset_tag == tag)
    if resume:
        query = query.where(Complaint.analyzed_at.is_(None))
    query = query.order_by(Complaint.created_at)
    if limit:
        query = query.limit(limit)

    ids = list(db.execute(query).scalars())
    outcome.sample_size = len(ids)

    if not ids:
        log.warning("benchmark_nothing_to_run", dataset_tag=tag, resume=resume)
        return outcome

    info = dataset.describe(db, tag)
    if info["labelled"] == 0:
        # Processing is still useful; scoring is not. Saying so up front beats
        # reporting an accuracy figure drawn from nothing.
        log.warning("benchmark_dataset_unlabelled", dataset_tag=tag)

    run_row = BenchmarkRun(
        label=outcome.label,
        dataset_tag=tag,
        sample_size=len(ids),
        ruleset_version=_ruleset_version(db),
        prompt_version=_prompt_version(db),
        provider=_provider_name(run_genai),
        model=_model_name(run_genai),
        metrics={},
        status=JobStatus.RUNNING,
    )
    db.add(run_row)
    db.commit()
    outcome.run_id = run_row.id

    log.info(
        "benchmark_started",
        run=str(run_row.id), dataset_tag=tag, sample=len(ids),
        genai=run_genai, workers=safe_workers(workers),
    )

    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=safe_workers(workers)) as pool:
        futures = {
            pool.submit(_process_one, cid, run_genai=run_genai): cid for cid in ids
        }
        for future in as_completed(futures):
            results.append(future.result())

    _accumulate(outcome, results)
    _persist_results(db, run_row.id, results)

    run_row.metrics = outcome.metrics()
    run_row.status = JobStatus.SUCCESS if outcome.failed == 0 else JobStatus.FAILED
    run_row.finished_at = datetime.now(UTC)
    db.commit()

    recall = outcome.escalation_recall_pct
    log.info(
        "benchmark_finished",
        run=str(run_row.id), processed=outcome.processed, failed=outcome.failed,
        escalation_recall=recall,
    )
    if recall is not None and recall < 100.0:
        log.error(
            "mandatory_escalation_recall_below_target",
            recall=recall, missed=outcome.escalation_missed[:10],
        )

    return outcome


def _accumulate(outcome: BenchmarkOutcome, results: list[dict[str, Any]]) -> None:
    for result in results:
        if result.get("error"):
            outcome.failed += 1
            outcome.errors.append(
                {"complaint_id": str(result["complaint_id"]), "error": result["error"]}
            )
            continue

        outcome.processed += 1
        outcome.genai_available_count += int(bool(result.get("genai_available")))
        if result.get("latency_ms"):
            outcome.latencies_ms.append(result["latency_ms"])

        rows = result.get("rows") or []
        if not rows:
            outcome.skipped_unlabelled += 1

        for row in rows:
            score = outcome.fields.setdefault(row["field"], FieldScore(row["field"]))
            score.scored += 1
            score.python_correct += int(bool(row["python_correct"]))

            # Only count the model where it actually answered, so its
            # denominator reflects what it was asked rather than what the rule
            # engine was asked.
            if row["genai_correct"] is not None:
                score.genai_scored += 1
                score.genai_correct += int(bool(row["genai_correct"]))
                if row["agreed"]:
                    score.agreed += 1

        escalation = result.get("escalation") or {}
        if escalation.get("required"):
            outcome.escalation_expected += 1
            if escalation.get("recalled"):
                outcome.escalation_recalled += 1
            else:
                outcome.escalation_missed.append(
                    f"{result.get('public_ref')}: expected "
                    f"{escalation.get('expected')}, got {escalation.get('actual')}"
                )
        elif escalation.get("over_escalated"):
            outcome.escalation_over += 1


def _persist_results(
    db: Session, run_id: uuid.UUID, results: list[dict[str, Any]]
) -> None:
    """
    Store every field comparison.

    The headline metrics are re-derivable from these rows, which is what makes
    them checkable rather than merely reported.
    """
    for result in results:
        for row in result.get("rows") or []:
            db.add(
                BenchmarkResult(
                    benchmark_run_id=run_id,
                    complaint_id=result["complaint_id"],
                    field=row["field"],
                    expected_value=row["expected_value"],
                    genai_value=row["genai_value"],
                    python_value=row["python_value"],
                    genai_correct=row["genai_correct"],
                    python_correct=row["python_correct"],
                    agreed=row["agreed"],
                    explanation=row["explanation"],
                )
            )
    db.flush()


# ══════════════════════════════════════════════════════════════
# provenance
# ══════════════════════════════════════════════════════════════
def _ruleset_version(db: Session) -> str:
    from src.db.seed.rules import current_ruleset_version

    return current_ruleset_version(db)


def _prompt_version(db: Session) -> str:
    from genai_pipeline import prompts

    try:
        return prompts.active_version(db, "complaint_intelligence")
    except Exception:  # noqa: BLE001 - provenance must not fail a run
        return "unknown"


def _provider_name(run_genai: bool) -> str:
    if not run_genai:
        return "none"
    from genai_pipeline.providers import build_chain

    chain = build_chain()
    return chain[0].name if chain else "none"


def _model_name(run_genai: bool) -> str:
    if not run_genai:
        return "rules-only"
    from genai_pipeline.providers import build_chain

    chain = build_chain()
    return chain[0].model if chain else "rules-only"


# ══════════════════════════════════════════════════════════════
# reading back
# ══════════════════════════════════════════════════════════════
def runs(db: Session, *, limit: int = 25) -> list[dict[str, Any]]:
    rows = db.execute(
        select(BenchmarkRun).order_by(BenchmarkRun.created_at.desc()).limit(limit)
    ).scalars().all()

    return [
        {
            "id": str(row.id),
            "label": row.label,
            "dataset_tag": row.dataset_tag,
            "sample_size": row.sample_size,
            "status": row.status,
            "ruleset_version": row.ruleset_version,
            "prompt_version": row.prompt_version,
            "provider": row.provider,
            "model": row.model,
            "metrics": row.metrics,
            "started_at": row.created_at.isoformat() if row.created_at else None,
            "finished_at": row.finished_at.isoformat() if row.finished_at else None,
        }
        for row in rows
    ]


def run_detail(db: Session, run_id: uuid.UUID) -> dict[str, Any] | None:
    row = db.get(BenchmarkRun, run_id)
    if row is None:
        return None

    failures = db.execute(
        select(BenchmarkResult, Complaint.public_ref)
        .join(Complaint, BenchmarkResult.complaint_id == Complaint.id)
        .where(
            BenchmarkResult.benchmark_run_id == run_id,
            BenchmarkResult.python_correct.is_(False),
        )
        .limit(200)
    ).all()

    return {
        "id": str(row.id),
        "label": row.label,
        "dataset_tag": row.dataset_tag,
        "status": row.status,
        "metrics": row.metrics,
        "ruleset_version": row.ruleset_version,
        "prompt_version": row.prompt_version,
        "provider": row.provider,
        "model": row.model,
        # Where the rules were wrong. The most useful page in the whole
        # console: every row here is a rule worth revisiting.
        "rule_failures": [
            {
                "public_ref": public_ref,
                "field": result.field,
                "expected": result.expected_value,
                "python": result.python_value,
                "genai": result.genai_value,
                "explanation": result.explanation,
            }
            for result, public_ref in failures
        ],
    }
