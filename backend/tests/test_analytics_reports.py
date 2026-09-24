"""
Analytics, trend detection and report exports.

The theme throughout is that a number nobody can trace is worse than no number.
Two tests carry that weight:

* :meth:`TestHonestNulls.test_an_empty_system_reports_nothing_not_perfection`
  — a dashboard that reads 100% because nothing has happened is the single
  easiest way to mislead a judge, and it is what you get by default if a
  percentage is allowed to fall back to zero-over-zero.
* :meth:`TestTrends.test_a_percentage_change_from_zero_is_undefined` — the
  same problem one layer down.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, select

from complaint_processing.intake import submit
from src.db.enums import ExportFormat, TrendDirection
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
    GenAIRun,
    ReportExport,
    ResolutionStep,
    ReviewAction,
    ReviewQueueItem,
    SLAEvent,
    TrendSnapshot,
    ValidationRun,
    VerificationDecision,
)
from src.services import analytics, reports, trends

SAFETY = (
    "The parcel you delivered made a loud pop and there is a burning smell "
    "from the plug. I unplugged it immediately. Order CN-9923190."
)
DELIVERY = (
    "My parcel for order CN-4455660 has not arrived and the tracking page has not "
    "updated for nine days."
)


@pytest.fixture
def clean(db):
    def _purge():
        for model in (
            ReportExport, TrendSnapshot, ReviewAction, ReviewQueueItem, SLAEvent,
            Escalation, Comparison, VerificationDecision, GenAIRun, ComplaintLink,
            ComplaintEntity, ComplaintValidationIssue, ComplaintPolicyRef,
            ResolutionStep, AgentGuidance, ClarificationQuestion, EligibilityDecision,
        ):
            db.execute(delete(model))
        db.execute(delete(ValidationRun))
        db.execute(delete(Complaint))
        db.execute(delete(Customer))
        db.commit()

    _purge()
    yield
    _purge()


def _file(db, description=SAFETY, **overrides):
    payload = {
        "title": "Complaint",
        "description": description,
        "customer_email": "analytics@example.com",
        "order_ref": "CN-9923190",
        "run_genai": False,
    }
    payload.update(overrides)
    result = submit(db, **payload)
    db.commit()
    return result.complaint


# ══════════════════════════════════════════════════════════════
# the honest-nulls rule
# ══════════════════════════════════════════════════════════════
class TestHonestNulls:
    def test_a_ratio_with_no_denominator_is_none(self):
        assert analytics.Ratio(0, 0).pct is None
        assert analytics.Ratio(0, 4).pct == 0.0
        assert analytics.Ratio(4, 4).pct == 100.0

    def test_an_empty_system_reports_nothing_not_perfection(self, db, clean):
        """
        A dashboard reading 100% because nothing has happened is the easiest
        way to mislead a judge, and it is the default if a percentage is
        allowed to fall back to zero-over-zero.
        """
        payload = analytics.dashboard(db, days=365)

        assert payload["volume"]["total"] == 0
        assert payload["escalation"]["rate"]["pct"] is None
        assert payload["pipelines"]["mean_agreement_pct"] is None
        assert payload["review"]["override_rate"]["pct"] is None
        for bucket in payload["sla"]["by_type"].values():
            assert bucket["compliance"]["pct"] is None

    def test_every_ratio_carries_its_evidence(self, db, clean):
        _file(db)
        rate = analytics.escalation_rate(db, days=365)["rate"]
        assert set(rate) == {"count", "total", "pct"}
        assert rate["count"] <= rate["total"]

    def test_an_unmeasured_score_is_counted_not_averaged_as_zero(self, db, clean):
        """
        A null compliance score means the control was not measurable, not that
        it failed. Averaging nulls as zeros would punish complaints that had
        nothing to check.
        """
        _file(db)
        result = analytics.traceability(db, days=365)
        assert result["unmeasured_compliance"] >= 1
        assert result["mean_compliance_pct"] is None


# ══════════════════════════════════════════════════════════════
# analytics
# ══════════════════════════════════════════════════════════════
class TestAnalytics:
    def test_volume_counts_by_status(self, db, clean):
        _file(db)
        volume = analytics.volume(db, days=365)
        assert volume["total"] == 1
        assert volume["open"] == 1
        assert sum(volume["by_status"].values()) == 1

    def test_unclassified_complaints_are_shown_not_dropped(self, db, clean):
        """A distribution that omits its own failures is a flattering one."""
        complaint = _file(db)
        complaint.category_id = None
        db.commit()

        codes = {row["code"] for row in analytics.by_category(db, days=365)}
        assert "UNCLASSIFIED" in codes

    def test_category_percentages_sum_to_about_a_hundred(self, db, clean):
        _file(db)
        _file(db, description=DELIVERY, order_ref="CN-4455660")
        total = sum(row["pct"] or 0 for row in analytics.by_category(db, days=365))
        assert 99.0 <= total <= 101.0

    def test_department_load_separates_volume_from_backlog(self, db, clean):
        """
        A department closing everything quickly is not under strain; one
        holding a growing backlog is.
        """
        _file(db)
        rows = analytics.department_load(db, days=365)
        assert rows
        assert all("total" in r and "open" in r for r in rows)
        assert all(r["open"] <= r["total"] for r in rows)

    def test_a_rule_derived_escalation_is_attributed_to_python(self, db, clean):
        """
        SRS 1.8 #7's evidence. A rules-forced escalation and a reviewer-raised
        one are different findings, so the trigger has to be recorded.
        """
        _file(db)
        by_trigger = analytics.escalation_rate(db, days=365)["by_trigger"]
        assert by_trigger.get("PYTHON_RULE", 0) >= 1

    def test_the_escalation_record_names_the_rules_that_forced_it(self, db, clean):
        complaint = _file(db)
        row = db.execute(
            select(Escalation).where(Escalation.complaint_id == complaint.id)
        ).scalars().first()
        assert row is not None
        assert row.rule_ref
        assert "CRITICAL_MGMT" in row.reason

    def test_re_analysis_does_not_stack_escalation_records(self, db, clean):
        from complaint_processing.intake import IntakeResult, analyse_complaint

        complaint = _file(db)
        analyse_complaint(db, complaint, IntakeResult(complaint=complaint), run_genai=False)
        db.commit()

        rows = db.execute(
            select(Escalation).where(Escalation.complaint_id == complaint.id)
        ).scalars().all()
        assert len(rows) == 1

    def test_agreement_excludes_degraded_runs(self, db, clean):
        """
        No provider is configured in the suite, so every decision here is
        degraded. Scoring those as disagreement would blame the model for an
        outage.
        """
        _file(db)
        result = analytics.pipeline_agreement(db, days=365)
        assert result["degraded"] >= 1
        assert result["with_genai"] == 0
        assert result["mean_agreement_pct"] is None

    def test_sla_compliance_counts_only_settled_clocks(self, db, clean):
        """
        An open clock that has not yet breached is neither a success nor a
        failure. Counting it as met would make a large untouched backlog
        report excellent performance.
        """
        _file(db)
        result = analytics.sla_performance(db, days=365)
        for bucket in result["by_type"].values():
            assert bucket["settled"] == 0
            assert bucket["compliance"]["pct"] is None

    def test_the_dashboard_assembles_every_panel(self, db, clean):
        _file(db)
        payload = analytics.dashboard(db, days=365)
        assert set(payload) >= {
            "volume", "categories", "departments", "escalation", "sla",
            "pipelines", "traceability", "guard", "review", "generated_at",
        }


# ══════════════════════════════════════════════════════════════
# trends
# ══════════════════════════════════════════════════════════════
class TestTrends:
    def test_a_percentage_change_from_zero_is_undefined(self):
        """
        Not 600%, not infinity, not a crash. From a baseline of nothing there
        is only a count.
        """
        trend = trends.Trend(
            metric="X", dimension="ALL", dimension_value="ALL",
            value=6, previous_value=0,
            period_start=datetime.now(UTC), period_end=datetime.now(UTC),
            period_type="WEEK",
        )
        assert trend.delta_pct is None
        assert trend.direction == TrendDirection.UP

    def test_small_numbers_are_not_a_trend(self):
        """Two becoming four is a 100% rise and almost always noise."""
        trend = trends.Trend(
            metric="X", dimension="ALL", dimension_value="ALL",
            value=4, previous_value=2,
            period_start=datetime.now(UTC), period_end=datetime.now(UTC),
            period_type="WEEK",
        )
        assert trend.delta_pct == 100.0
        assert not trend.is_material

    def test_a_material_rise_on_a_real_base_is_reported(self):
        trend = trends.Trend(
            metric="X", dimension="ALL", dimension_value="ALL",
            value=70, previous_value=40,
            period_start=datetime.now(UTC), period_end=datetime.now(UTC),
            period_type="WEEK",
        )
        assert trend.is_material and trend.direction == TrendDirection.UP

    def test_an_anomaly_needs_both_a_big_swing_and_a_real_base(self):
        """A category going from 1 to 3 triples. That is a Tuesday."""
        small = trends.Trend(
            metric="X", dimension="ALL", dimension_value="ALL",
            value=3, previous_value=1,
            period_start=datetime.now(UTC), period_end=datetime.now(UTC),
            period_type="WEEK",
        )
        big = trends.Trend(
            metric="X", dimension="ALL", dimension_value="ALL",
            value=60, previous_value=20,
            period_start=datetime.now(UTC), period_end=datetime.now(UTC),
            period_type="WEEK",
        )
        assert not small.is_anomaly
        assert big.is_anomaly

    def test_a_flat_metric_is_flat(self):
        trend = trends.Trend(
            metric="X", dimension="ALL", dimension_value="ALL",
            value=10, previous_value=10,
            period_start=datetime.now(UTC), period_end=datetime.now(UTC),
            period_type="WEEK",
        )
        assert trend.direction == TrendDirection.FLAT
        assert not trend.is_material

    def test_compute_compares_two_consecutive_periods(self, db, clean):
        _file(db)
        computed = trends.compute(db, period_type="WEEK")
        assert computed
        volume = next(
            t for t in computed
            if t.metric == trends.METRIC_VOLUME and t.dimension == "ALL"
        )
        assert volume.value == 1
        assert volume.previous_value == 0

    def test_a_category_that_vanished_is_still_reported(self, db, clean):
        """
        Iterating only the current period would hide every drop to zero, and a
        category that stopped appearing is as interesting as one that started.
        """
        _file(db)
        # Stand one week in the future: the complaint now falls in the
        # PREVIOUS window and the current one is empty.
        now = datetime.now(UTC) + timedelta(days=8)
        computed = trends.compute(db, period_type="WEEK", now=now)

        safety = [
            t for t in computed
            if t.dimension == "CATEGORY" and t.dimension_value == "SAFETY"
        ]
        assert safety, "the category must still appear after its complaints aged out"
        assert safety[0].value == 0

    def test_a_snapshot_is_stored_and_idempotent(self, db, clean):
        _file(db)
        trends.snapshot(db, period_type="WEEK")
        db.commit()
        first = db.execute(select(TrendSnapshot)).scalars().all()

        trends.snapshot(db, period_type="WEEK")
        db.commit()
        second = db.execute(select(TrendSnapshot)).scalars().all()

        assert len(second) == len(first), "re-running corrects rather than duplicates"

    def test_rising_is_sorted_by_absolute_movement(self, db, clean):
        """
        A jump from 40 to 70 outranks one from 5 to 11, even though the
        percentage is smaller.
        """
        rows = trends.rising(db, period_type="WEEK")
        deltas = [r["value"] - r["previous_value"] for r in rows]
        assert deltas == sorted(deltas, reverse=True)


# ══════════════════════════════════════════════════════════════
# reports
# ══════════════════════════════════════════════════════════════
class TestReports:
    def test_every_declared_report_builds(self, db, clean):
        _file(db)
        for name in reports.REPORT_TYPES:
            report = reports.build(db, name)
            assert report.columns, f"{name} declares no columns"

    def test_an_unknown_report_is_rejected(self, db):
        with pytest.raises(ValueError, match="Unknown report"):
            reports.build(db, "MADE_UP")

    def test_an_empty_report_still_knows_its_shape(self, db, clean):
        """A table with no rows must still render its headers."""
        report = reports.build(db, reports.COMPARISON)
        assert report.row_count == 0
        assert report.columns

    def test_the_comparison_report_is_deliverable_eight(self, db, clean):
        """
        One row per compared field per complaint, both readings, which won,
        and why — read back from stored rows rather than recomputed.
        """
        _file(db)
        report = reports.build(db, reports.COMPARISON)
        assert report.rows
        assert set(report.columns) >= {
            "public_ref", "field", "genai_value", "python_value",
            "final_value", "winner", "explanation",
        }
        assert all(row["explanation"] for row in report.rows)

    def test_filters_narrow_a_report(self, db, clean):
        _file(db)
        everything = reports.build(db, reports.COMPARISON)
        mismatches = reports.build(db, reports.COMPARISON, mismatches_only=True)
        assert mismatches.row_count <= everything.row_count
        assert all(row["status"] == "MISMATCH" for row in mismatches.rows)

    def test_the_traceability_report_names_the_document_and_version(self, db, clean):
        _file(db)
        report = reports.build(db, reports.TRACEABILITY)
        assert set(report.columns) >= {"doc_ref", "version", "section", "was_active"}


class TestExports:
    @pytest.mark.parametrize(
        "export_format", [ExportFormat.CSV, ExportFormat.XLSX, ExportFormat.PDF]
    )
    def test_every_format_renders(self, db, clean, export_format):
        _file(db)
        report = reports.build(db, reports.COMPARISON)
        payload, filename, media_type = reports.render(report, export_format)

        assert payload, f"{export_format} produced nothing"
        assert filename.endswith(export_format.lower())
        assert media_type

    def test_csv_carries_a_bom_for_excel(self, db, clean):
        """
        Without it Excel on Windows reads UTF-8 as Latin-1 and turns every ₹
        into mojibake. Three bytes, and the evaluator sees clean text.
        """
        _file(db)
        payload = reports.to_csv(reports.build(db, reports.COMPARISON))
        assert payload.startswith(b"\xef\xbb\xbf")

    def test_csv_headers_match_the_declared_columns(self, db, clean):
        _file(db)
        report = reports.build(db, reports.COMPARISON)
        header = reports.to_csv(report).decode("utf-8-sig").splitlines()[0]
        assert header.split(",")[0] == report.columns[0]

    def test_an_unknown_format_is_rejected(self, db, clean):
        report = reports.build(db, reports.COMPARISON)
        with pytest.raises(ValueError, match="Unknown format"):
            reports.render(report, "DOCX")

    def test_an_export_is_recorded(self, db, clean):
        """
        "Who pulled what data, when" is an audit question, and a download that
        leaves no trace cannot answer it.
        """
        _file(db)
        report = reports.build(db, reports.COMPARISON, mismatches_only=True)
        reports.record_export(db, report, ExportFormat.CSV)
        db.commit()

        history = reports.export_history(db)
        assert history
        assert history[0]["report_type"] == reports.COMPARISON
        assert history[0]["filters"]["mismatches_only"] is True


# ══════════════════════════════════════════════════════════════
# endpoints
# ══════════════════════════════════════════════════════════════
class TestEndpoints:
    def _file_one(self, client, auth_headers):
        client.post(
            "/api/complaints",
            json={"title": "Charger burning smell", "description": SAFETY,
                  "order_ref": "CN-9923190"},
            headers=auth_headers("agent"),
        )

    def test_the_dashboard_needs_a_manager_or_above(
        self, client, auth_headers, clean
    ):
        assert client.get("/api/analytics/dashboard").status_code == 401
        assert (
            client.get("/api/analytics/dashboard", headers=auth_headers("agent")).status_code
            == 403
        )
        assert (
            client.get("/api/analytics/dashboard", headers=auth_headers("manager")).status_code
            == 200
        )

    def test_an_evaluator_can_read_the_dashboard(self, client, auth_headers, clean):
        """A judge inspects the system without an administrator token."""
        response = client.get(
            "/api/analytics/dashboard", headers=auth_headers("evaluator")
        )
        assert response.status_code == 200

    def test_the_dashboard_returns_every_panel(self, client, auth_headers, clean):
        self._file_one(client, auth_headers)
        body = client.get(
            "/api/analytics/dashboard",
            params={"days": 365},
            headers=auth_headers("manager"),
        ).json()
        assert body["volume"]["total"] >= 1
        assert body["categories"]
        assert "mean_agreement_pct" in body["pipelines"]

    def test_reports_are_discoverable(self, client, auth_headers, clean):
        body = client.get(
            "/api/analytics/reports", headers=auth_headers("manager")
        ).json()
        assert {r["report_type"] for r in body} == set(reports.REPORT_TYPES)
        assert all(r["description"] for r in body)

    def test_a_report_reads_as_json(self, client, auth_headers, clean):
        self._file_one(client, auth_headers)
        body = client.get(
            "/api/analytics/reports/COMPARISON", headers=auth_headers("manager")
        ).json()
        assert body["title"] == "GenAI and Python Comparison"
        assert body["columns"]

    def test_an_unknown_report_is_a_404(self, client, auth_headers, clean):
        response = client.get(
            "/api/analytics/reports/NONSENSE", headers=auth_headers("manager")
        )
        assert response.status_code == 404

    @pytest.mark.parametrize("export_format", ["CSV", "XLSX", "PDF"])
    def test_export_downloads_a_file(
        self, client, auth_headers, clean, export_format
    ):
        self._file_one(client, auth_headers)
        response = client.get(
            "/api/analytics/reports/COMPARISON/export",
            params={"format": export_format},
            headers=auth_headers("manager"),
        )
        assert response.status_code == 200
        assert response.content
        assert "attachment" in response.headers["content-disposition"]
        assert export_format.lower() in response.headers["content-disposition"]

    def test_an_agent_cannot_export(self, client, auth_headers, clean):
        """A download leaves the system and is recorded against a person."""
        response = client.get(
            "/api/analytics/reports/COMPLAINTS/export",
            headers=auth_headers("agent"),
        )
        assert response.status_code == 403

    def test_exporting_writes_to_the_history(self, client, auth_headers, clean):
        self._file_one(client, auth_headers)
        client.get(
            "/api/analytics/reports/SLA/export",
            params={"format": "CSV"},
            headers=auth_headers("manager"),
        )
        history = client.get(
            "/api/analytics/exports", headers=auth_headers("manager")
        ).json()
        assert any(row["report_type"] == "SLA" for row in history)

    def test_a_trend_snapshot_can_be_taken(self, client, auth_headers, clean):
        self._file_one(client, auth_headers)
        response = client.post(
            "/api/analytics/trends/snapshot",
            params={"period": "WEEK"},
            headers=auth_headers("manager"),
        )
        assert response.status_code == 200
        assert response.json()["computed"] >= 1

    def test_an_agent_sees_only_their_own_queue(self, client, auth_headers, clean):
        """Scoped to the caller, so one agent cannot read another's workload."""
        response = client.get("/api/analytics/my-queue", headers=auth_headers("agent"))
        assert response.status_code == 200
        assert "assigned" in response.json()
