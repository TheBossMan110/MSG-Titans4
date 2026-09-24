"""
The Deliberate Defect Challenge (SRS 1.8 #15).

A safety check nobody has ever seen fire is a safety check nobody has reason to
believe in. These tests are the evidence that each one does.

The test that matters most is
:meth:`TestIsolation.test_demonstrating_a_defect_changes_nothing`. The whole
design rests on the defect never being installed — if a demonstration could
leave the system degraded, the defect would stop being deliberate.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from security import deliberate_defect
from security.deliberate_defect import (
    COMPENSATION_OVER_CEILING,
    HALLUCINATED_CITATION,
    LOWERED_ESCALATION,
    UNSUPPORTED_PROMISE,
)


# ══════════════════════════════════════════════════════════════
# every defect is caught
# ══════════════════════════════════════════════════════════════
class TestDetection:
    @pytest.mark.parametrize(
        "code",
        [
            UNSUPPORTED_PROMISE,
            COMPENSATION_OVER_CEILING,
            HALLUCINATED_CITATION,
            LOWERED_ESCALATION,
        ],
    )
    def test_the_safeguard_fires(self, db, code):
        """
        Each defect is genuinely wrong and the production detector catches it.
        A failure here is not a broken test — it is a safeguard that does not
        work.
        """
        result = deliberate_defect.demonstrate(db, code)

        assert result.detected, (
            f"{code} was not caught by {result.detector}. "
            f"Artefact: {result.faulty_artefact}"
        )
        assert result.explanation
        assert "failure of the safeguard" not in result.explanation

    def test_an_unauthorised_promise_is_blocked_outright(self, db):
        result = deliberate_defect.demonstrate(db, UNSUPPORTED_PROMISE)

        assert result.findings
        finding = result.findings[0]
        assert finding["severity"] == "CRITICAL"
        assert finding["promise_type"] == "REFUND"

    def test_the_ceiling_defect_is_caught_despite_genuine_eligibility(self, db):
        """
        The expensive one. Eligibility really does say yes, so the promise
        reads as authorised and every other gate passes — only the number is
        wrong, which is exactly why an outcome check alone cannot catch it.
        """
        result = deliberate_defect.demonstrate(db, COMPENSATION_OVER_CEILING)

        assert result.detected
        explanation = result.findings[0]["explanation"]
        assert "5,000.00" in explanation
        assert "500.00" in explanation

    def test_the_escalation_floor_corrects_rather_than_refuses(self, db):
        """
        The floor does not reject the complaint; it raises it. A safety report
        that arrives under-escalated must still be handled, at the right level.
        """
        result = deliberate_defect.demonstrate(db, LOWERED_ESCALATION)

        assert result.detected
        assert result.corrected_to
        assert result.corrected_to.upper() != "NONE"
        assert "overridden" in result.explanation

    def test_every_catalogued_defect_can_be_demonstrated(self, db):
        """
        A catalogue entry with no runner would document a safeguard nobody
        ever checks.
        """
        results = deliberate_defect.demonstrate_all(db)
        assert len(results) == len(deliberate_defect.CATALOGUE)
        assert all(result.detected for result in results)


# ══════════════════════════════════════════════════════════════
# the defect is never installed
# ══════════════════════════════════════════════════════════════
class TestIsolation:
    def test_demonstrating_a_defect_changes_nothing(self, db):
        """
        The whole design rests on this. A switch that could leave the system
        degraded would stop the defect being deliberate — it could be left on.
        """
        from src.db.models import (
            AppConfig,
            Complaint,
            ResponseFlag,
            Rule,
            ValidationRun,
        )

        def snapshot():
            return {
                model.__name__: len(db.execute(select(model)).scalars().all())
                for model in (Complaint, ValidationRun, ResponseFlag, Rule, AppConfig)
            }

        before = snapshot()
        deliberate_defect.demonstrate_all(db)
        db.expire_all()

        assert snapshot() == before, "a demonstration must not persist anything"

    def test_no_pipeline_consults_this_module(self):
        """
        There must be no code path through which a demonstration can affect a
        real complaint. The import graph is the proof: nothing in the pipelines
        may reference it.
        """
        import pathlib

        root = pathlib.Path(__file__).resolve().parents[1]
        packages = (
            "genai_pipeline", "python_validation", "comparison_engine",
            "complaint_processing", "hallucination_checks", "knowledge_base",
        )

        offenders = []
        for package in packages:
            for path in (root / package).rglob("*.py"):
                if "deliberate_defect" in path.read_text(encoding="utf-8"):
                    offenders.append(str(path.relative_to(root)))

        assert not offenders, (
            "the deliberate defect module is reachable from a pipeline: "
            f"{offenders}"
        )

    def test_the_catalogue_needs_no_database(self):
        """Documentation a judge can read before anything is run."""
        catalogue = deliberate_defect.catalogue()
        assert catalogue
        for entry in catalogue:
            assert entry["detected_by"]
            assert entry["why_it_matters"]


# ══════════════════════════════════════════════════════════════
# endpoints
# ══════════════════════════════════════════════════════════════
class TestEndpoints:
    def test_the_catalogue_is_served(self, client, auth_headers):
        rows = client.get("/api/admin/defects", headers=auth_headers("evaluator")).json()
        assert len(rows) == len(deliberate_defect.CATALOGUE)
        assert all(row["detected_by"] for row in rows)

    def test_all_defects_run_in_one_call(self, client, auth_headers):
        """What a judge asks for: show me your safeguards working."""
        rows = client.post(
            "/api/admin/defects/demonstrate", headers=auth_headers("evaluator")
        ).json()

        assert rows
        undetected = [row["code"] for row in rows if not row["detected"]]
        assert not undetected, f"safeguards did not fire: {undetected}"

    def test_one_defect_runs_on_its_own(self, client, auth_headers):
        body = client.post(
            f"/api/admin/defects/{UNSUPPORTED_PROMISE}/demonstrate",
            headers=auth_headers("admin"),
        ).json()

        assert body["detected"]
        assert body["faulty_artefact"]
        assert body["findings"]

    def test_an_unknown_defect_is_404(self, client, auth_headers):
        response = client.post(
            "/api/admin/defects/NOT_A_DEFECT/demonstrate",
            headers=auth_headers("admin"),
        )
        assert response.status_code == 404

    @pytest.mark.parametrize("role", ["agent", "customer"])
    def test_it_is_not_open_to_everyone(self, client, auth_headers, role):
        assert (
            client.get("/api/admin/defects", headers=auth_headers(role)).status_code
            == 403
        )
