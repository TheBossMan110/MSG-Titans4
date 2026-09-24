"""
Security events, background jobs, benchmarking, impact analysis and exports.

FR liv/lv  Prompt Injection Protection / Adversarial Detection  SRS Steps 50-51
FR lxxii   Reports                                              SRS Step 67
FR lxxiii  Export                                               SRS Step 68
SRS 1.8 #4 Hidden Policy Update -> impact_analyses / impact_items
Deliverable 8  GenAI + Python Comparison Report -> benchmark_*
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base, Code, Name, TimestampMixin, TZDateTime, UUIDPrimaryKey
from src.db.constraints import enum_check
from src.db.enums import (
    ExportFormat,
    InjectionAction,
    JobStatus,
    Severity,
    TrendDirection,
)


class InjectionEvent(UUIDPrimaryKey, TimestampMixin, Base):
    """
    Every prompt-injection detection, on complaints *and* uploaded documents.

    Layer 2 of the four-layer defence produces these rows; the Security Console
    reads them; the Security Testing Report aggregates them.
    """

    __tablename__ = "injection_events"
    __table_args__ = (
        Index("ix_injection_created", "created_at"),
        Index("ix_injection_complaint", "complaint_id"),
        enum_check("action_taken", InjectionAction),
        enum_check("severity", Severity),
    )

    source_type: Mapped[str] = mapped_column(String(16), nullable=False)  # COMPLAINT | DOCUMENT
    complaint_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("complaints.id", ondelete="CASCADE")
    )
    document_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("document_versions.id", ondelete="CASCADE")
    )
    pattern_label: Mapped[str] = mapped_column(Code, nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default=Severity.MEDIUM)
    # [{"start": 0, "end": 31, "text": "Ignore all previous instructions"}]
    matched_spans: Mapped[list[Any]] = mapped_column(nullable=False, default=list)
    action_taken: Mapped[str] = mapped_column(String(24), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)


class Job(UUIDPrimaryKey, TimestampMixin, Base):
    """
    Durable background-job record.

    Deliberately a table rather than Redis/Celery: one less service to fail on
    demo day, and the progress bar in the UI reads straight from here.
    """

    __tablename__ = "jobs"
    __table_args__ = (
        Index("ix_jobs_status_created", "status", "created_at"),
        Index("ix_jobs_type", "job_type"),
        enum_check("status", JobStatus),
    )

    job_type: Mapped[str] = mapped_column(Code, nullable=False)  # ANALYZE, PARSE_DOCUMENT…
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=JobStatus.QUEUED)
    payload: Mapped[dict[str, Any]] = mapped_column(nullable=False, default=dict)
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total: Mapped[int | None] = mapped_column(Integer)
    result: Mapped[dict[str, Any] | None] = mapped_column()
    error: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    started_at: Mapped[datetime | None] = mapped_column(TZDateTime)
    finished_at: Mapped[datetime | None] = mapped_column(TZDateTime)


class BenchmarkRun(UUIDPrimaryKey, TimestampMixin, Base):
    """
    A batch evaluation over the labelled dataset.

    ``metrics`` holds the headline numbers, including the one that matters
    most: mandatory escalation recall, which must be 100%.
    """

    __tablename__ = "benchmark_runs"

    label: Mapped[str] = mapped_column(Name, nullable=False)
    dataset_tag: Mapped[str] = mapped_column(Code, nullable=False)
    sample_size: Mapped[int] = mapped_column(Integer, nullable=False)
    ruleset_version: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(16), nullable=False)
    provider: Mapped[str] = mapped_column(Code, nullable=False)
    model: Mapped[str] = mapped_column(Name, nullable=False)
    metrics: Mapped[dict[str, Any]] = mapped_column(nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=JobStatus.RUNNING)
    job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"))
    finished_at: Mapped[datetime | None] = mapped_column(TZDateTime)

    results = relationship(
        "BenchmarkResult", back_populates="run", cascade="all, delete-orphan"
    )


class BenchmarkResult(UUIDPrimaryKey, TimestampMixin, Base):
    """One field, one complaint, in one benchmark run."""

    __tablename__ = "benchmark_results"
    __table_args__ = (
        Index("ix_benchresults_run_field", "benchmark_run_id", "field"),
        Index("ix_benchresults_complaint", "complaint_id"),
    )

    benchmark_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("benchmark_runs.id", ondelete="CASCADE"), nullable=False
    )
    complaint_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("complaints.id", ondelete="CASCADE"), nullable=False
    )
    field: Mapped[str] = mapped_column(Code, nullable=False)
    expected_value: Mapped[str | None] = mapped_column(String(255))
    genai_value: Mapped[str | None] = mapped_column(String(255))
    python_value: Mapped[str | None] = mapped_column(String(255))
    genai_correct: Mapped[bool | None] = mapped_column(Boolean)
    python_correct: Mapped[bool | None] = mapped_column(Boolean)
    agreed: Mapped[bool | None] = mapped_column(Boolean)
    explanation: Mapped[str | None] = mapped_column(Text)

    run = relationship("BenchmarkRun", back_populates="results")


class ImpactAnalysis(UUIDPrimaryKey, TimestampMixin, Base):
    """
    SRS 1.8 #4 — when a policy is replaced, what breaks?

    Answerable only because every resolution stores the policy refs it relied
    on, so the query is a join rather than a guess.
    """

    __tablename__ = "impact_analyses"

    new_document_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_versions.id", ondelete="CASCADE"), nullable=False
    )
    old_document_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("document_versions.id", ondelete="SET NULL")
    )
    # [{"section_ref":"5.2","change":"MODIFIED","summary":"..."}]
    changed_sections: Mapped[list[Any]] = mapped_column(nullable=False, default=list)
    affected_rule_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    affected_complaint_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

    items = relationship(
        "ImpactItem", back_populates="analysis", cascade="all, delete-orphan"
    )


class ImpactItem(UUIDPrimaryKey, TimestampMixin, Base):
    """One affected complaint / rule / response, and whether it was regenerated."""

    __tablename__ = "impact_items"
    __table_args__ = (Index("ix_impactitems_analysis", "impact_analysis_id", "item_type"),)

    impact_analysis_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("impact_analyses.id", ondelete="CASCADE"), nullable=False
    )
    item_type: Mapped[str] = mapped_column(String(16), nullable=False)  # COMPLAINT|RULE|RESPONSE
    item_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    item_ref: Mapped[str | None] = mapped_column(Code)  # human-readable, e.g. CMP-00421
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    regenerated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    regenerated_at: Mapped[datetime | None] = mapped_column(TZDateTime)

    analysis = relationship("ImpactAnalysis", back_populates="items")


class ReportExport(UUIDPrimaryKey, TimestampMixin, Base):
    """FR lxxiii — every export is recorded (who exported what, when)."""

    __tablename__ = "report_exports"
    __table_args__ = (enum_check("format", ExportFormat),)

    report_type: Mapped[str] = mapped_column(Code, nullable=False)
    format: Mapped[str] = mapped_column(String(8), nullable=False)
    filters: Mapped[dict[str, Any] | None] = mapped_column()
    file_path: Mapped[str | None] = mapped_column(String(1024))
    row_count: Mapped[int | None] = mapped_column(Integer)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )


class TrendSnapshot(UUIDPrimaryKey, TimestampMixin, Base):
    """
    FR lxx / SRS Step 65 — Trend Detection.

    Rolling period aggregates so "rising delivery complaints", "escalation
    spikes" and "recurring product issues" are detectable as a *change over
    time* rather than a single-point count.  Computed by a scheduled job and
    stored, because a trend the dashboard recomputes from scratch on every page
    load cannot be compared against history or exported.
    """

    __tablename__ = "trend_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "period_type", "period_start", "metric", "dimension", "dimension_value",
            name="uq_trend_period_metric_dim",
        ),
        Index("ix_trend_metric_period", "metric", "period_start"),
        enum_check("direction", TrendDirection),
    )

    period_type: Mapped[str] = mapped_column(String(16), nullable=False)  # DAY | WEEK | MONTH
    period_start: Mapped[datetime] = mapped_column(TZDateTime, nullable=False)
    period_end: Mapped[datetime] = mapped_column(TZDateTime, nullable=False)

    metric: Mapped[str] = mapped_column(Code, nullable=False)  # COMPLAINT_VOLUME, ESCALATIONS…
    dimension: Mapped[str] = mapped_column(Code, nullable=False, default="ALL")  # CATEGORY…
    dimension_value: Mapped[str] = mapped_column(Name, nullable=False, default="ALL")

    value: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False, default=0)
    previous_value: Mapped[float | None] = mapped_column(Numeric(14, 4))
    delta_pct: Mapped[float | None] = mapped_column(Numeric(8, 2))
    direction: Mapped[str] = mapped_column(String(8), nullable=False, default=TrendDirection.FLAT)
    is_anomaly: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
