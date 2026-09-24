"""
Benchmark and dataset endpoints.

SRS 1.8 #2 Unique Complaint Dataset   SRS 1.8 #3 Hidden Complaint Dataset
NFR 1     Performance                 Deliverable 8 Comparison Report

Access model: evaluators and administrators. The hidden-dataset import is the
reason the evaluator role exists — a judge drops in their own complaints and
runs the benchmark without being handed an administrator token, and without
anyone touching the code.

The import and the benchmark are deliberately separate calls. Importing 500
complaints and analysing them in one request would time out, and a
half-finished import leaves a dataset nobody can reason about. Import lands
rows; the benchmark processes them, in batches, resumably.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Query, UploadFile, status

from schemas.benchmark import (
    BenchmarkDetailOut,
    BenchmarkRunOut,
    DatasetOut,
    ImportResultOut,
)
from src.core.deps import DbSession, require_role
from src.core.errors import NotFoundError, ValidationError
from src.core.logging import get_logger
from src.db.enums import UserRole
from src.services import benchmark, dataset

log = get_logger("api.benchmark")

router = APIRouter(prefix="/benchmark", tags=["Benchmark & Dataset"])

OPERATORS = (UserRole.EVALUATOR, UserRole.ADMIN)
VIEWERS = (*OPERATORS, UserRole.MANAGER)

MAX_UPLOAD_MB = 20


# ══════════════════════════════════════════════════════════════
# datasets
# ══════════════════════════════════════════════════════════════
@router.get(
    "/datasets",
    response_model=list[DatasetOut],
    dependencies=[Depends(require_role(*VIEWERS))],
    summary="Every dataset and how much of it can be scored",
)
def list_datasets(db: DbSession) -> list[DatasetOut]:
    return [DatasetOut(**row) for row in dataset.datasets(db)]


@router.get(
    "/datasets/{dataset_tag}",
    response_model=DatasetOut,
    dependencies=[Depends(require_role(*VIEWERS))],
    summary="One dataset's counts",
)
def describe_dataset(dataset_tag: str, db: DbSession) -> DatasetOut:
    info = dataset.describe(db, dataset_tag)
    if info["total"] == 0:
        raise NotFoundError(f"No complaints tagged '{dataset_tag.upper()}'.")
    return DatasetOut(**info)


@router.post(
    "/datasets/{dataset_tag}/import",
    response_model=ImportResultOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role(*OPERATORS))],
    summary="Import a labelled or unlabelled complaint file",
)
async def import_dataset(
    dataset_tag: str,
    db: DbSession,
    file: UploadFile = File(...),
    replace: bool = Query(
        False, description="Clear the tag first, so a corrected re-import does not double it."
    ),
) -> ImportResultOut:
    """
    Load complaints from CSV or XLSX (SRS 1.8 #2, #3).

    The same path serves the authored 500-complaint dataset and a hidden one an
    evaluator supplies at judging time. Writing a separate importer for the
    hidden case would mean the one that matters had never been run.

    Ground-truth ``expected_*`` columns are loaded when present and are read
    only by the benchmark. Nothing is analysed here.
    """
    payload = await file.read()
    if not payload:
        raise ValidationError("The uploaded file is empty.")
    if len(payload) > MAX_UPLOAD_MB * 1024 * 1024:
        raise ValidationError(f"File exceeds the {MAX_UPLOAD_MB} MB limit.")

    try:
        result = dataset.import_file(
            db, payload, file.filename or "upload.csv",
            dataset_tag=dataset_tag, replace=replace,
        )
    except Exception as exc:  # noqa: BLE001 - a bad file is a user error, not a 500
        db.rollback()
        raise ValidationError(f"Could not read the file: {exc}") from exc

    db.commit()
    return ImportResultOut(**result.summary())


@router.delete(
    "/datasets/{dataset_tag}",
    dependencies=[Depends(require_role(UserRole.ADMIN))],
    summary="Remove a dataset",
)
def delete_dataset(dataset_tag: str, db: DbSession) -> dict[str, int | str]:
    """
    Delete every complaint under a tag.

    Administrator only, and irreversible: the complaints and everything
    cascading from them go with it.
    """
    removed = dataset.clear(db, dataset_tag)
    db.commit()
    return {"dataset_tag": dataset_tag.upper(), "removed": removed}


# ══════════════════════════════════════════════════════════════
# running
# ══════════════════════════════════════════════════════════════
@router.post(
    "/run",
    response_model=BenchmarkRunOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role(*OPERATORS))],
    summary="Score a dataset against its ground-truth labels",
)
def run_benchmark(
    db: DbSession,
    dataset_tag: str = Query(..., description="Which dataset to score."),
    label: str | None = Query(None, description="A name for this run."),
    limit: int | None = Query(
        None, ge=1, le=2000, description="Cap the sample; useful for a smoke run."
    ),
    run_genai: bool = Query(
        True, description="False scores the rule engine alone — the outage configuration."
    ),
    workers: int = Query(benchmark.DEFAULT_WORKERS, ge=1, le=16),
    resume: bool = Query(
        True, description="Skip complaints already analysed, so an interrupted run continues."
    ),
) -> BenchmarkRunOut:
    """
    Run the benchmark (NFR 1; Deliverable 8).

    Accuracy here is measured against **labels**, not against the other
    pipeline: two matching errors count as two errors, where the dashboard's
    agreement figure would count them as a success.

    The headline number is mandatory escalation recall, whose target is 100%
    and is not negotiable. It is reported separately from per-field accuracy
    so that one un-escalated safety complaint cannot hide inside a 99.8%.
    """
    info = dataset.describe(db, dataset_tag)
    if info["total"] == 0:
        raise NotFoundError(f"No complaints tagged '{dataset_tag.upper()}'.")

    outcome = benchmark.run(
        db,
        dataset_tag=dataset_tag,
        label=label,
        limit=limit,
        run_genai=run_genai,
        workers=workers,
        resume=resume,
    )

    if outcome.run_id is None:
        raise ValidationError(
            f"Nothing to run: every complaint in '{dataset_tag.upper()}' has "
            "already been analysed. Pass resume=false to score them again."
        )

    detail = benchmark.run_detail(db, outcome.run_id)
    return BenchmarkRunOut(
        id=detail["id"],
        label=detail["label"],
        dataset_tag=detail["dataset_tag"],
        sample_size=outcome.sample_size,
        status=detail["status"],
        ruleset_version=detail["ruleset_version"],
        prompt_version=detail["prompt_version"],
        provider=detail["provider"],
        model=detail["model"],
        metrics=detail["metrics"],
    )


@router.get(
    "/runs",
    response_model=list[BenchmarkRunOut],
    dependencies=[Depends(require_role(*VIEWERS))],
    summary="Past benchmark runs",
)
def list_runs(db: DbSession, limit: int = Query(25, ge=1, le=100)) -> list[BenchmarkRunOut]:
    """
    Every run, newest first.

    Each carries its ruleset and prompt version, so two runs can be compared
    and a score can be attributed to the configuration that produced it.
    """
    return [BenchmarkRunOut(**row) for row in benchmark.runs(db, limit=limit)]


@router.get(
    "/runs/{run_id}",
    response_model=BenchmarkDetailOut,
    dependencies=[Depends(require_role(*VIEWERS))],
    summary="One run, with the cases the rules got wrong",
)
def run_detail(run_id: uuid.UUID, db: DbSession) -> BenchmarkDetailOut:
    """
    The most useful page in the console: every row under ``rule_failures`` is a
    rule worth revisiting, named with the complaint that exposed it.
    """
    detail = benchmark.run_detail(db, run_id)
    if detail is None:
        raise NotFoundError(f"No benchmark run {run_id}.")
    return BenchmarkDetailOut(**detail)
