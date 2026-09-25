"""
Live progress: the streamed intake, and the speed settings behind it.

The stream is only worth having if every message is true -- emitted by the
pipeline at the moment the step happens -- and if it never tells a customer
more than their status page would. These tests hold it to both.
"""

from __future__ import annotations

import json
import uuid

import pytest

from complaint_processing import intake
from genai_pipeline.providers import gemini, openai_compatible
from src.core import progress
from src.core.config import settings

BODY = {
    "title": "Parcel never arrived",
    "description": (
        "My parcel has not arrived and the tracking page has not updated for "
        "several days. Please tell me where it is and what happens next."
    ),
}


def _events(text: str) -> list[tuple[str, dict]]:
    """Parse a server-sent-events body into (event, data) pairs."""
    out = []
    for block in text.split("\n\n"):
        kind, data = None, None
        for line in block.splitlines():
            if line.startswith("event: "):
                kind = line[7:]
            elif line.startswith("data: "):
                data = json.loads(line[6:])
        if kind:
            out.append((kind, data))
    return out


class TestProgressModule:
    def test_emit_without_a_listener_does_nothing(self):
        assert progress.active() is False
        progress.emit("read")  # must not raise

    def test_a_listener_receives_labelled_steps(self):
        seen = []
        with progress.reporting(seen.append):
            assert progress.active()
            progress.emit("ai", "done", "Answered")
        assert seen[0]["step"] == "ai"
        assert seen[0]["state"] == "done"
        assert seen[0]["label"] == progress.LABELS["ai"]
        assert seen[0]["detail"] == "Answered"
        assert seen[0]["elapsed_ms"] >= 0
        assert progress.active() is False

    def test_a_broken_listener_cannot_fail_the_analysis(self):
        def boom(_event):
            raise RuntimeError("tab closed")

        with progress.reporting(boom):
            progress.emit("read")  # swallowed


class TestStreamEndpoint:
    def test_the_stream_narrates_every_step_and_ends_with_the_result(self, client, auth_headers):
        response = client.post("/api/complaints/stream", json=BODY, headers=auth_headers("customer"))
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")

        events = _events(response.text)
        steps = [data for kind, data in events if kind == "step"]
        finished = {s["step"] for s in steps if s["state"] in ("done", "skipped")}
        for step in ("read", "safety", "details", "history", "saved", "rules", "ai", "verify", "route"):
            assert step in finished, f"{step} never finished"

        # Steps arrive in pipeline order.
        first_seen = []
        for s in steps:
            if s["step"] not in first_seen:
                first_seen.append(s["step"])
        order = [sid for sid in progress.STEP_IDS if sid in first_seen]
        assert first_seen == order

        kind, result = events[-1]
        assert kind == "result"
        assert result["public_ref"].startswith("CMP-")
        saved = next(s for s in steps if s["step"] == "saved" and s["state"] == "done")
        assert saved["detail"] == result["public_ref"]

    def test_a_customer_gets_the_customer_view_only(self, client, auth_headers):
        response = client.post("/api/complaints/stream", json=BODY, headers=auth_headers("customer"))
        kind, result = _events(response.text)[-1]
        assert kind == "result"
        assert result["complaint"] is None
        assert result["customer_view"]["public_ref"] == result["public_ref"]

    def test_no_step_leaks_what_the_status_page_withholds(self, client, auth_headers):
        response = client.post("/api/complaints/stream", json=BODY, headers=auth_headers("customer"))
        text = " ".join(
            f"{d['label']} {d.get('detail') or ''}"
            for kind, d in _events(response.text) if kind == "step"
        ).upper()
        for internal in ("P0", "P1", "P2", "P3", "ESCALATION", "CORRECTED_BY_RULES", "PRIORITY"):
            assert internal not in text

    def test_staff_get_the_full_record(self, client, auth_headers):
        response = client.post("/api/complaints/stream", json=BODY, headers=auth_headers("agent"))
        kind, result = _events(response.text)[-1]
        assert kind == "result"
        assert result["complaint"]["public_ref"] == result["public_ref"]

    def test_an_empty_complaint_ends_in_an_error_event(self, client, auth_headers):
        response = client.post(
            "/api/complaints/stream",
            json={"title": "x", "description": "   "},
            headers=auth_headers("customer"),
        )
        if response.status_code == 422:
            return  # refused by the request schema before streaming began
        kind, body = _events(response.text)[-1]
        assert kind == "error"
        assert body["error"]["code"] == "VALIDATION_ERROR"

    def test_the_stream_requires_sign_in(self, client):
        assert client.post("/api/complaints/stream", json=BODY).status_code == 401


class TestReasoningEffort:
    @pytest.fixture(autouse=True)
    def _restore(self):
        before = settings.llm_reasoning_effort
        yield
        settings.llm_reasoning_effort = before

    def test_gpt_oss_gets_low_effort(self):
        settings.llm_reasoning_effort = "low"
        assert openai_compatible._reasoning_effort("openai/gpt-oss-120b") == "low"
        settings.llm_reasoning_effort = "minimal"
        assert openai_compatible._reasoning_effort("openai/gpt-oss-20b") == "low"

    def test_qwen3_switches_thinking_off(self):
        settings.llm_reasoning_effort = "low"
        assert openai_compatible._reasoning_effort("qwen/qwen3.8-27b") == "none"
        settings.llm_reasoning_effort = "high"
        assert openai_compatible._reasoning_effort("qwen/qwen3.8-27b") == "default"

    def test_unknown_models_are_sent_nothing(self):
        settings.llm_reasoning_effort = "low"
        assert openai_compatible._reasoning_effort("meta-llama/llama-3.3-70b-instruct") is None

    def test_default_sends_nothing_anywhere(self):
        settings.llm_reasoning_effort = "default"
        assert openai_compatible._reasoning_effort("openai/gpt-oss-120b") is None
        assert gemini._thinking_config("gemini-3.5-flash-lite") is None

    def test_gemini_3_uses_a_thinking_level(self):
        settings.llm_reasoning_effort = "low"
        config = gemini._thinking_config("gemini-3.5-flash-lite")
        assert config is not None and config.thinking_level is not None
        assert config.thinking_budget is None

    def test_gemini_25_uses_a_budget(self):
        settings.llm_reasoning_effort = "minimal"
        assert gemini._thinking_config("gemini-2.5-flash-lite").thinking_budget == 0
        # 2.5 Pro cannot turn thinking off; asking for zero would be a 400.
        assert gemini._thinking_config("gemini-2.5-pro").thinking_budget == 128


class TestDeferredEscalationNote:
    def test_notes_are_collected_not_written_while_deferring(self):
        with intake.deferring_escalation_notes() as pending:
            assert intake._deferred_notes.get() is pending
        assert intake._deferred_notes.get() is None

    def test_writing_nothing_is_a_no_op(self):
        intake.write_deferred_notes([])

    def test_a_vanished_complaint_is_skipped_quietly(self):
        intake.write_deferred_notes([
            intake.PendingNote(
                complaint_id=uuid.uuid4(), reconciled={}, eligibility=[], escalation_rules=[],
            )
        ])


class TestFreshComplaintWrites:
    """Skipped DELETEs must never leave a second copy of a complaint's rows."""

    def test_only_the_first_write_of_a_fresh_complaint_skips_clearing(self, db):
        from src.db.fresh import forget_fresh, mark_fresh, needs_clearing

        cid = uuid.uuid4()
        assert needs_clearing(db, cid, "comparisons") is True  # not marked: always clear
        mark_fresh(db, cid)
        assert needs_clearing(db, cid, "comparisons") is False
        assert needs_clearing(db, cid, "comparisons") is True  # second write clears
        assert needs_clearing(db, cid, "resolution_steps") is False
        forget_fresh(db, cid)
        assert needs_clearing(db, cid, "agent_guidance") is True

    def test_reanalysis_replaces_rows_rather_than_duplicating_them(self, client, auth_headers, db):
        from sqlalchemy import func, select

        from src.db.models import Comparison, Complaint, ComplaintEntity, ResolutionStep

        headers = auth_headers("admin")
        ref = client.post("/api/complaints", json=BODY, headers=headers).json()["public_ref"]
        complaint = db.execute(select(Complaint).where(Complaint.public_ref == ref)).scalars().one()

        def counts():
            db.expire_all()
            return {
                model.__name__: db.execute(
                    select(func.count()).select_from(model).where(model.complaint_id == complaint.id)
                ).scalar_one()
                for model in (Comparison, ResolutionStep, ComplaintEntity)
            }

        before = counts()
        assert client.post(f"/api/complaints/{ref}/reanalyse", headers=headers).status_code == 200
        assert counts() == before
