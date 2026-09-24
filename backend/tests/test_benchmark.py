"""
Dataset import and the benchmark runner.

Two tests here are structural rather than behavioural, and they are the ones
that matter most:

* :func:`test_no_pipeline_can_read_a_ground_truth_label` — the ``expected_*``
  columns sit on the complaint row, so nothing but the compiler stops a
  pipeline consulting them. A model or a rule that could see the answer would
  be scoring its own homework, and every accuracy figure after that would be
  worthless. This greps the pipeline packages to prove none of them can.
* :meth:`TestEscalationRecall.test_an_under_escalation_is_caught` — the metric
  ``policy.yaml`` calls non-negotiable, tested by deliberately mislabelling a
  complaint so the run must report the miss.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from sqlalchemy import delete, select

from src.db.models import (
    AgentGuidance,
    BenchmarkResult,
    BenchmarkRun,
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
    GenAIRun,
    ResolutionStep,
    ReviewAction,
    ReviewQueueItem,
    SLAEvent,
    ValidationRun,
    VerificationDecision,
)
from src.services import benchmark, dataset

TAG = "TEST_BENCH"

LABELLED_CSV = """title,description,order_ref,expected_category,expected_department,expected_urgency,expected_priority,expected_escalation
Charger burning smell,"The parcel you delivered made a loud pop and there is a burning smell from the plug. I unplugged it immediately. Order CN-9923190.",CN-9923190,SAFETY,SAFETY,CRITICAL,P0,CRITICAL_MGMT
Parcel never arrived,"My parcel for order CN-4455660 has not arrived and the tracking page has not updated for nine days. Please tell me where it is.",CN-4455660,DELIVERY,LOGISTICS,MEDIUM,P2,NONE
"""

UNLABELLED_CSV = """title,description,order_ref
Parcel never arrived,"My parcel for order CN-4455660 has not arrived and the tracking page has not updated for nine days.",CN-4455660
"""


@pytest.fixture
def clean(db):
    def _purge():
        db.execute(delete(BenchmarkResult))
        db.execute(delete(BenchmarkRun))
        for model in (
            ReviewAction, ReviewQueueItem, SLAEvent, Escalation, Comparison,
            VerificationDecision, GenAIRun, ComplaintLink, ComplaintEntity,
            ComplaintValidationIssue, ComplaintPolicyRef, ResolutionStep,
            AgentGuidance, ClarificationQuestion, EligibilityDecision,
        ):
            db.execute(delete(model))
        db.execute(delete(ValidationRun))
        db.execute(delete(Complaint))
        db.execute(delete(Customer))
        db.commit()

    _purge()
    yield
    _purge()


def _import(db, csv_text=LABELLED_CSV, **kwargs):
    result = dataset.import_file(
        db, csv_text.encode("utf-8"), "seed.csv", dataset_tag=TAG, **kwargs
    )
    db.commit()
    return result


# ══════════════════════════════════════════════════════════════
# the structural guarantee
# ══════════════════════════════════════════════════════════════
def test_no_pipeline_can_read_a_ground_truth_label():
    """
    The ``expected_*`` columns live on the complaint row, so nothing but this
    test stops a pipeline consulting them. A rule or a model that could see the
    answer would be scoring its own homework, and every accuracy figure after
    that would be worthless.

    Enforced the same way as the GenAI restriction on Pipeline 2: by grepping
    the packages rather than by trusting a convention.
    """
    root = Path(__file__).resolve().parents[1]
    packages = (
        "python_validation", "genai_pipeline", "comparison_engine",
        "hallucination_checks", "security",
    )

    offenders: list[str] = []
    for package in packages:
        for path in (root / package).rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            for line in source.splitlines():
                if "expected_" in line and not line.strip().startswith("#"):
                    offenders.append(f"{package}/{path.name}: {line.strip()[:90]}")

    assert not offenders, (
        "a pipeline reaches a ground-truth label:\n" + "\n".join(offenders)
    )


def test_the_benchmark_is_the_only_reader():
    """The counterpart: the benchmark must actually use them."""
    root = Path(__file__).resolve().parents[1]
    source = (root / "src" / "services" / "benchmark.py").read_text(encoding="utf-8")
    assert "expected_category_code" in source
    assert "expected_escalation_code" in source


# ══════════════════════════════════════════════════════════════
# import
# ══════════════════════════════════════════════════════════════
class TestImport:
    def test_a_labelled_file_imports_with_its_labels(self, db, clean):
        result = _import(db)
        assert result.imported == 2
        assert result.labelled == 2
        assert not result.errors

        complaint = db.execute(
            select(Complaint).where(Complaint.dataset_tag == TAG)
        ).scalars().first()
        assert complaint.expected_category_code in ("SAFETY", "DELIVERY")

    def test_an_unlabelled_file_still_imports(self, db, clean):
        """
        The hidden-dataset case. An evaluator's complaints arrive with no
        labels and must process without a code change.
        """
        result = _import(db, UNLABELLED_CSV)
        assert result.imported == 1
        assert result.labelled == 0

    def test_a_row_with_no_description_is_skipped_with_a_reason(self, db, clean):
        csv_text = 'title,description\nEmpty one,""\nGood one,"A real complaint body that is long enough."\n'
        result = _import(db, csv_text)
        assert result.imported == 1
        assert result.skipped == 1
        assert result.errors[0]["row"] == 2

    def test_headers_are_matched_loosely(self, db, clean):
        """An evaluator should not have to match our capitalisation."""
        csv_text = (
            'Title,Description,Order Ref,Expected Category\n'
            'A title,"A complaint body long enough to pass validation.",CN-9923190,SAFETY\n'
        )
        result = _import(db, csv_text)
        assert result.imported == 1
        complaint = db.execute(
            select(Complaint).where(Complaint.dataset_tag == TAG)
        ).scalars().one()
        assert complaint.order_ref == "CN-9923190"
        assert complaint.expected_category_code == "SAFETY"

    def test_a_bom_does_not_corrupt_the_first_column(self, db, clean):
        """
        Excel writes a BOM. Without utf-8-sig the first header becomes
        "\\ufefftitle" and every row silently loses its title.
        """
        payload = ("﻿" + LABELLED_CSV).encode("utf-8")
        result = dataset.import_file(db, payload, "excel.csv", dataset_tag=TAG)
        db.commit()
        assert result.imported == 2

    def test_a_currency_symbol_in_an_amount_is_tolerated(self, db, clean):
        csv_text = (
            'title,description,amount,currency\n'
            'Charged,"I was charged too much for my order and want it corrected.","Rs. 42,500",INR\n'
        )
        _import(db, csv_text)
        complaint = db.execute(
            select(Complaint).where(Complaint.dataset_tag == TAG)
        ).scalars().one()
        assert float(complaint.amount) == 42500.0

    def test_replace_does_not_double_the_dataset(self, db, clean):
        _import(db)
        _import(db, replace=True)
        assert dataset.describe(db, TAG)["total"] == 2

    def test_importing_never_analyses(self, db, clean):
        """
        Analysing 500 complaints inside a request would time out, and a
        half-finished import is a dataset nobody can reason about.
        """
        _import(db)
        info = dataset.describe(db, TAG)
        assert info["analysed"] == 0
        assert info["pending_analysis"] == info["total"]

    def test_describe_separates_labelled_from_unlabelled(self, db, clean):
        _import(db)
        _import(db, UNLABELLED_CSV)
        info = dataset.describe(db, TAG)
        assert info["total"] == 3
        assert info["labelled"] == 2
        assert info["unlabelled"] == 1

    def test_an_xlsx_file_imports(self, db, clean):
        from openpyxl import Workbook

        book = Workbook()
        sheet = book.active
        sheet.append(["title", "description", "expected_category"])
        sheet.append(
            ["A title", "A complaint body long enough to pass validation.", "SAFETY"]
        )
        buffer = io.BytesIO()
        book.save(buffer)

        result = dataset.import_file(
            db, buffer.getvalue(), "data.xlsx", dataset_tag=TAG
        )
        db.commit()
        assert result.imported == 1
        assert result.labelled == 1


# ══════════════════════════════════════════════════════════════
# scoring
# ══════════════════════════════════════════════════════════════
class TestBenchmark:
    def test_a_run_scores_every_labelled_field(self, db, clean):
        _import(db)
        outcome = benchmark.run(db, dataset_tag=TAG, run_genai=False, workers=1)

        assert outcome.processed == 2
        assert outcome.failed == 0
        assert outcome.fields
        for score in outcome.fields.values():
            assert score.scored > 0

    def test_a_pipeline_that_did_not_run_scores_null_not_zero(self, db, clean):
        """
        A rules-only run must not report the model at 0% accurate. It was
        never asked, and "0%" reads as "got everything wrong".
        """
        _import(db)
        outcome = benchmark.run(db, dataset_tag=TAG, run_genai=False, workers=1)
        metrics = outcome.metrics()

        assert metrics["overall"]["genai_accuracy_pct"] is None
        assert metrics["overall"]["agreement_pct"] is None
        assert metrics["overall"]["python_accuracy_pct"] is not None
        for row in metrics["by_field"]:
            assert row["genai_scored"] == 0
            assert row["genai_accuracy_pct"] is None

    def test_unlabelled_complaints_are_processed_but_not_scored(self, db, clean):
        """
        An unlabelled field is unmeasured. Scoring it as wrong would punish
        the system for the dataset's gaps.
        """
        _import(db, UNLABELLED_CSV)
        outcome = benchmark.run(db, dataset_tag=TAG, run_genai=False, workers=1)
        assert outcome.processed == 1
        assert outcome.skipped_unlabelled == 1
        assert not outcome.fields

    def test_every_comparison_is_stored(self, db, clean):
        """
        The headline metrics are re-derivable from these rows, which is what
        makes them checkable rather than merely reported.
        """
        _import(db)
        outcome = benchmark.run(db, dataset_tag=TAG, run_genai=False, workers=1)

        rows = db.execute(
            select(BenchmarkResult).where(
                BenchmarkResult.benchmark_run_id == outcome.run_id
            )
        ).scalars().all()
        assert rows
        assert all(row.expected_value for row in rows)
        assert all(row.explanation for row in rows)

    def test_the_run_records_its_provenance(self, db, clean):
        """A score without the ruleset that produced it cannot be reproduced."""
        _import(db)
        outcome = benchmark.run(db, dataset_tag=TAG, run_genai=False, workers=1)

        run_row = db.get(BenchmarkRun, outcome.run_id)
        assert run_row.ruleset_version
        assert run_row.prompt_version
        assert run_row.metrics
        assert run_row.finished_at is not None

    def test_a_run_resumes_rather_than_restarting(self, db, clean):
        """
        On a rate-limited free tier this is the difference between finishing
        and not.
        """
        _import(db)
        benchmark.run(db, dataset_tag=TAG, run_genai=False, workers=1)

        second = benchmark.run(db, dataset_tag=TAG, run_genai=False, workers=1)
        assert second.sample_size == 0, "everything was already analysed"

        third = benchmark.run(
            db, dataset_tag=TAG, run_genai=False, workers=1, resume=False
        )
        assert third.sample_size == 2

    def test_an_empty_dataset_produces_no_run(self, db, clean):
        outcome = benchmark.run(db, dataset_tag="NOTHING_HERE", run_genai=False)
        assert outcome.sample_size == 0
        assert outcome.run_id is None

    def test_latency_reports_a_p95_not_only_a_mean(self, db, clean):
        """NFR 1 caps each complaint; a mean hides the tail that would breach it."""
        _import(db)
        outcome = benchmark.run(db, dataset_tag=TAG, run_genai=False, workers=1)
        latency = outcome.metrics()["latency"]
        assert latency["p95_ms"] is not None
        assert latency["max_ms"] >= latency["p50_ms"]

    def test_workers_are_clamped_to_what_the_database_can_serve(self):
        """
        Asking for more workers than the pool holds does not run faster — it
        runs until a worker waits past the timeout and the run dies part-way.
        """
        assert benchmark.safe_workers(999) <= 64
        assert benchmark.safe_workers(1) == 1
        assert benchmark.safe_workers(999) >= 1


# ══════════════════════════════════════════════════════════════
# the non-negotiable metric
# ══════════════════════════════════════════════════════════════
class TestEscalationRecall:
    def test_a_correctly_escalated_complaint_counts_as_recalled(self, db, clean):
        _import(db)
        outcome = benchmark.run(db, dataset_tag=TAG, run_genai=False, workers=1)

        assert outcome.escalation_expected == 1
        assert outcome.escalation_recalled == 1
        assert outcome.escalation_recall_pct == 100.0
        assert outcome.metrics()["mandatory_escalation"]["met"] is True

    def test_an_under_escalation_is_caught(self, db, clean):
        """
        The metric policy.yaml calls non-negotiable. A complaint labelled as
        needing CRITICAL_MGMT that the system leaves unescalated must show up
        as a miss, by reference, not be averaged away.
        """
        csv_text = (
            "title,description,expected_escalation\n"
            'Mild delivery query,"My parcel for order CN-4455660 is running a couple of '
            'days late and I would like an update when convenient.",CRITICAL_MGMT\n'
        )
        _import(db, csv_text)
        outcome = benchmark.run(db, dataset_tag=TAG, run_genai=False, workers=1)

        assert outcome.escalation_expected == 1
        assert outcome.escalation_recalled == 0
        assert outcome.escalation_recall_pct == 0.0
        assert outcome.escalation_missed, "the missed complaint must be named"
        assert outcome.metrics()["mandatory_escalation"]["met"] is False

    def test_over_escalating_is_recorded_but_not_a_failure(self, db, clean):
        """Over-escalating is cautious; under-escalating is a safety failure."""
        csv_text = (
            "title,description,expected_escalation\n"
            'Charger burning smell,"My RaftarXpress charger made a loud pop and there is a '
            'burning smell from the plug. Order CN-9923190.",NONE\n'
        )
        _import(db, csv_text)
        outcome = benchmark.run(db, dataset_tag=TAG, run_genai=False, workers=1)

        assert outcome.escalation_expected == 0
        assert outcome.escalation_over == 1
        assert outcome.escalation_recall_pct is None

    def test_a_dataset_that_never_tests_the_floor_reports_null(self, db, clean):
        """
        Null, not 100%. A dataset with nothing to escalate cannot evidence the
        floor, and claiming perfect recall from it would be the emptiest
        possible success.
        """
        _import(db, UNLABELLED_CSV)
        outcome = benchmark.run(db, dataset_tag=TAG, run_genai=False, workers=1)
        assert outcome.escalation_recall_pct is None
        assert outcome.metrics()["mandatory_escalation"]["met"] is None


# ══════════════════════════════════════════════════════════════
# endpoints
# ══════════════════════════════════════════════════════════════
class TestEndpoints:
    def _upload(self, client, auth_headers, role="evaluator", csv_text=LABELLED_CSV):
        return client.post(
            f"/api/benchmark/datasets/{TAG}/import",
            files={"file": ("seed.csv", csv_text.encode("utf-8"), "text/csv")},
            params={"replace": "true"},
            headers=auth_headers(role),
        )

    def test_an_evaluator_can_import_a_hidden_dataset(
        self, client, auth_headers, clean
    ):
        """
        The reason the evaluator role exists: a judge drops in their own
        complaints without an administrator token and without a code change.
        """
        response = self._upload(client, auth_headers)
        assert response.status_code == 201, response.text
        assert response.json()["imported"] == 2

    def test_an_agent_cannot_import(self, client, auth_headers, clean):
        assert self._upload(client, auth_headers, role="agent").status_code == 403

    def test_an_empty_file_is_refused(self, client, auth_headers, clean):
        response = client.post(
            f"/api/benchmark/datasets/{TAG}/import",
            files={"file": ("empty.csv", b"", "text/csv")},
            headers=auth_headers("evaluator"),
        )
        assert response.status_code == 422

    def test_datasets_are_listed_with_their_counts(self, client, auth_headers, clean):
        self._upload(client, auth_headers)
        body = client.get(
            "/api/benchmark/datasets", headers=auth_headers("evaluator")
        ).json()
        mine = [row for row in body if row["dataset_tag"] == TAG]
        assert mine and mine[0]["labelled"] == 2

    def test_running_an_unknown_dataset_is_a_404(self, client, auth_headers, clean):
        response = client.post(
            "/api/benchmark/run",
            params={"dataset_tag": "NO_SUCH_SET", "run_genai": "false"},
            headers=auth_headers("evaluator"),
        )
        assert response.status_code == 404

    def test_a_run_returns_its_metrics(self, client, auth_headers, clean):
        self._upload(client, auth_headers)
        response = client.post(
            "/api/benchmark/run",
            params={"dataset_tag": TAG, "run_genai": "false", "workers": 1},
            headers=auth_headers("evaluator"),
        )
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["metrics"]["mandatory_escalation"]["target_pct"] == 100.0
        assert body["ruleset_version"]

    def test_the_detail_view_lists_what_the_rules_got_wrong(
        self, client, auth_headers, clean
    ):
        """Every row here is a rule worth revisiting."""
        self._upload(client, auth_headers)
        run_id = client.post(
            "/api/benchmark/run",
            params={"dataset_tag": TAG, "run_genai": "false", "workers": 1},
            headers=auth_headers("evaluator"),
        ).json()["id"]

        body = client.get(
            f"/api/benchmark/runs/{run_id}", headers=auth_headers("evaluator")
        ).json()
        assert body["id"] == run_id
        assert "rule_failures" in body

    def test_only_an_administrator_can_delete_a_dataset(
        self, client, auth_headers, clean
    ):
        self._upload(client, auth_headers)
        assert (
            client.delete(
                f"/api/benchmark/datasets/{TAG}", headers=auth_headers("evaluator")
            ).status_code
            == 403
        )
        assert (
            client.delete(
                f"/api/benchmark/datasets/{TAG}", headers=auth_headers("admin")
            ).status_code
            == 200
        )
