"""
Analytics and reporting API contracts.

Percentages are ``float | None`` throughout, and that nullability is load-
bearing rather than defensive typing. A percentage with no denominator is
unmeasured, not zero and not a hundred — an empty system must report "nothing
to measure" rather than "perfect compliance", and a non-nullable field would
force a lie into the contract (SRS 1.8 #17).
"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from schemas.common import APIModel


class RatioOut(APIModel):
    """A count over a total, with the percentage derived from both."""

    count: int = 0
    total: int = 0
    pct: float | None = None


class VolumeOut(APIModel):
    window_days: int | None = None
    total: int = 0
    by_status: dict[str, int] = Field(default_factory=dict)
    open: int = 0
    resolved: int = 0
    failed: int = 0


class CategorySliceOut(APIModel):
    code: str
    name: str
    count: int
    pct: float | None = None


class DepartmentLoadOut(APIModel):
    code: str
    name: str
    total: int
    open: int


class EscalationOut(APIModel):
    rate: RatioOut
    by_level: dict[str, int] = Field(default_factory=dict)
    # PYTHON_RULE escalations on complaints the model rated low-urgency are the
    # Escalation Trap working, and this is where that count surfaces.
    by_trigger: dict[str, int] = Field(default_factory=dict)


class SLATypeOut(APIModel):
    settled: int = 0
    met: int = 0
    breached: int = 0
    at_risk: int = 0
    compliance: RatioOut


class SLAOut(APIModel):
    by_type: dict[str, SLATypeOut] = Field(default_factory=dict)
    open_at_risk: int = 0


class PipelineOut(APIModel):
    decisions: int = 0
    with_genai: int = 0
    # Decisions taken with no provider reachable. Excluded from agreement,
    # because scoring a degraded run as a disagreement blames the model for an
    # outage.
    degraded: int = 0
    mean_agreement_pct: float | None = None
    rules_corrected_the_model: RatioOut
    critical_mismatches: int = 0
    by_outcome: dict[str, int] = Field(default_factory=dict)


class TraceabilityOut(APIModel):
    mean_traceability_pct: float | None = None
    mean_compliance_pct: float | None = None
    # A null score is not a zero: the control was not measurable for that
    # complaint. Counting them separately keeps the mean honest.
    unmeasured_traceability: int = 0
    unmeasured_compliance: int = 0


class GuardOut(APIModel):
    injection_events: dict[str, int] = Field(default_factory=dict)
    injection_flagged_complaints: int = 0
    response_flags: dict[str, int] = Field(default_factory=dict)


class ReviewOut(APIModel):
    queue_depth: dict[str, int] = Field(default_factory=dict)
    open: int = 0
    override_rate: RatioOut
    by_action: dict[str, int] = Field(default_factory=dict)


class DashboardOut(APIModel):
    """Every panel in one payload, assembled from one query pass."""

    generated_at: str
    window_days: int | None = None
    volume: VolumeOut
    categories: list[CategorySliceOut] = Field(default_factory=list)
    departments: list[DepartmentLoadOut] = Field(default_factory=list)
    escalation: EscalationOut
    sla: SLAOut
    pipelines: PipelineOut
    traceability: TraceabilityOut
    guard: GuardOut
    review: ReviewOut
    # Named in the SRS list for administrators and not covered by the panels above.
    priorities: dict[str, int] = Field(default_factory=dict)
    products: list[dict[str, Any]] = Field(default_factory=list)
    urgency: dict[str, int] = Field(default_factory=dict)
    sentiment: dict[str, int] = Field(default_factory=dict)
    resolution_time: dict[str, Any] = Field(default_factory=dict)
    repeat_complaints: dict[str, Any] = Field(default_factory=dict)
    sla_risks: list[dict[str, Any]] = Field(default_factory=list)
    mismatches: list[dict[str, Any]] = Field(default_factory=list)
    manual_review: list[dict[str, Any]] = Field(default_factory=list)


# ══════════════════════════════════════════════════════════════
# trends
# ══════════════════════════════════════════════════════════════
class TrendOut(APIModel):
    metric: str
    dimension: str
    dimension_value: str
    value: float
    previous_value: float
    # Null when the previous period was zero: there is no percentage change
    # from nothing, only a count.
    delta_pct: float | None = None
    direction: str
    material: bool = False
    anomaly: bool = False
    period_type: str
    period_start: str


class TrendSnapshotOut(APIModel):
    period_start: str | None = None
    value: float
    previous_value: float | None = None
    delta_pct: float | None = None
    direction: str
    anomaly: bool = False


# ══════════════════════════════════════════════════════════════
# reports
# ══════════════════════════════════════════════════════════════
class ReportTypeOut(APIModel):
    report_type: str
    description: str


class ReportOut(APIModel):
    """
    A report is its rows plus the column order they read in.

    ``columns`` is returned explicitly rather than left to the key order of the
    first row, so a table renders in a stable, meaningful order and a report
    with no rows still knows its own shape.
    """

    report_type: str
    title: str
    columns: list[str] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    row_count: int = 0
    filters: dict[str, Any] = Field(default_factory=dict)
    generated_at: str


class ExportHistoryOut(APIModel):
    report_type: str
    format: str
    rows: int | None = None
    filters: dict[str, Any] | None = None
    at: str | None = None
