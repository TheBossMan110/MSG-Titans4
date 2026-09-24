"""
Trend detection (FR lxx; SRS Step 65).

    "The system must detect rising complaint categories, escalation spikes and
     recurring product issues."                             — SRS Step 65

A trend is a *change over time*, not a count. "47 delivery complaints" says
nothing; "47 this week against 22 last week" says something. So every snapshot
stores its own previous value and the delta between them, and the comparison is
made once and kept rather than recomputed per page load — a trend the dashboard
recalculates from scratch cannot be compared against history or exported.

**A spike needs a floor.** Two complaints becoming four is a 100% rise and
almost always noise. ``MIN_BASELINE`` stops the dashboard crying wolf on small
numbers, which is the fastest way to make people stop reading it.

**Percentage change from zero is undefined, not infinite.** A category with no
complaints last week and six this week gets ``delta_pct: null`` and direction
UP, rather than a meaningless 600% or a divide-by-zero. The count is the real
signal there.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.core.logging import get_logger
from src.db.enums import TrendDirection
from src.db.models import Category, Complaint, Department, TrendSnapshot

log = get_logger("services.trends")

PERIOD_DAYS = {"DAY": 1, "WEEK": 7, "MONTH": 30}

# Below this many in the current period, a percentage change is noise.
MIN_BASELINE = 5

# How far a value must move before it counts as a trend rather than jitter.
MATERIAL_CHANGE_PCT = 20.0

# A far larger move, on a base big enough that it cannot be chance. This is
# what the dashboard raises as an alert rather than a line on a chart, so the
# bar is deliberately high: an anomaly that fires weekly is not an anomaly.
ANOMALY_CHANGE_PCT = 75.0
ANOMALY_MIN_BASELINE = 10

# Metrics, each measured the same way in both periods.
METRIC_VOLUME = "COMPLAINT_VOLUME"
METRIC_ESCALATIONS = "ESCALATIONS"
METRIC_SLA_BREACHES = "SLA_BREACHES"


@dataclass(slots=True)
class Trend:
    """One metric, one dimension value, across two consecutive periods."""

    metric: str
    dimension: str
    dimension_value: str
    value: float
    previous_value: float
    period_start: datetime
    period_end: datetime
    period_type: str

    @property
    def delta_pct(self) -> float | None:
        """
        Percentage change, or ``None`` when it cannot be stated.

        From a baseline of zero there is no percentage — only a count. Saying
        "600%" or "infinite" would put a number on the dashboard that means
        nothing.
        """
        if self.previous_value <= 0:
            return None
        return round(
            (self.value - self.previous_value) / self.previous_value * 100.0, 2
        )

    @property
    def direction(self) -> str:
        if self.value == self.previous_value:
            return TrendDirection.FLAT
        return TrendDirection.UP if self.value > self.previous_value else TrendDirection.DOWN

    @property
    def is_material(self) -> bool:
        """
        Whether this is worth showing.

        Small numbers move violently in percentage terms, and a dashboard that
        reports every one of them is a dashboard nobody reads.
        """
        if self.value < MIN_BASELINE and self.previous_value < MIN_BASELINE:
            return False
        delta = self.delta_pct
        if delta is None:
            return self.value >= MIN_BASELINE
        return abs(delta) >= MATERIAL_CHANGE_PCT

    @property
    def is_anomaly(self) -> bool:
        """
        A move large enough to be worth interrupting somebody over.

        Requires both a big percentage swing and a base large enough that the
        swing cannot be chance. A category going from 1 to 3 triples; that is
        not an anomaly, it is a Tuesday.
        """
        if max(self.value, self.previous_value) < ANOMALY_MIN_BASELINE:
            return False
        delta = self.delta_pct
        if delta is None:
            # No baseline at all: a standing start above the floor is itself
            # the anomaly.
            return self.value >= ANOMALY_MIN_BASELINE
        return abs(delta) >= ANOMALY_CHANGE_PCT

    def as_dict(self) -> dict[str, Any]:
        return {
            "metric": self.metric,
            "dimension": self.dimension,
            "dimension_value": self.dimension_value,
            "value": self.value,
            "previous_value": self.previous_value,
            "delta_pct": self.delta_pct,
            "direction": self.direction,
            "material": self.is_material,
            "anomaly": self.is_anomaly,
            "period_type": self.period_type,
            "period_start": self.period_start.isoformat(),
        }


# ══════════════════════════════════════════════════════════════
# measurement
# ══════════════════════════════════════════════════════════════
def _count_between(
    db: Session,
    start: datetime,
    end: datetime,
    *,
    escalated_only: bool = False,
) -> int:
    query = select(func.count()).select_from(Complaint).where(
        Complaint.created_at >= start, Complaint.created_at < end
    )
    if escalated_only:
        query = query.where(
            Complaint.escalation_code.isnot(None), Complaint.escalation_code != "NONE"
        )
    return db.execute(query).scalar_one()


def _grouped_between(
    db: Session, start: datetime, end: datetime, model: Any, join_column: Any
) -> dict[str, int]:
    rows = db.execute(
        select(model.code, func.count(Complaint.id))
        .select_from(Complaint)
        .outerjoin(model, join_column == model.id)
        .where(Complaint.created_at >= start, Complaint.created_at < end)
        .group_by(model.code)
    ).all()
    return {code or "UNCLASSIFIED": count for code, count in rows}


def period_bounds(
    period_type: str, now: datetime | None = None
) -> tuple[datetime, datetime, datetime]:
    """
    ``(previous_start, current_start, current_end)``, aligned to day boundaries.

    The alignment is what makes a snapshot idempotent. Taking the window as
    ``now() - 7 days`` gives a different ``period_start`` on every call, so the
    upsert never matches its own previous row: history then grows by one row
    per run and no stored trend can be compared with the one before it.

    A snapshot belongs to the *day* it was taken. The current window is the
    last N days up to and including today, so a complaint filed this morning
    is counted today rather than waiting for tomorrow.
    """
    moment = now or datetime.now(UTC)
    days = PERIOD_DAYS.get(period_type.upper(), 7)

    today = moment.replace(hour=0, minute=0, second=0, microsecond=0)
    current_end = today + timedelta(days=1)
    current_start = current_end - timedelta(days=days)
    previous_start = current_start - timedelta(days=days)
    return previous_start, current_start, current_end


def compute(
    db: Session,
    *,
    period_type: str = "WEEK",
    now: datetime | None = None,
) -> list[Trend]:
    """
    Compare the current period against the one immediately before it.

    ``now`` is injectable so a test can place itself in time exactly, and so a
    backfill can walk historical periods without the clock moving underneath
    it.
    """
    previous_start, current_start, current_end = period_bounds(period_type, now)
    moment = current_end

    trends: list[Trend] = []

    def add(metric: str, dimension: str, value_key: str, current: float, previous: float):
        trends.append(
            Trend(
                metric=metric,
                dimension=dimension,
                dimension_value=value_key,
                value=float(current),
                previous_value=float(previous),
                period_start=current_start,
                period_end=moment,
                period_type=period_type.upper(),
            )
        )

    # ── overall volume ──
    add(
        METRIC_VOLUME, "ALL", "ALL",
        _count_between(db, current_start, moment),
        _count_between(db, previous_start, current_start),
    )

    # ── escalations ──
    add(
        METRIC_ESCALATIONS, "ALL", "ALL",
        _count_between(db, current_start, moment, escalated_only=True),
        _count_between(db, previous_start, current_start, escalated_only=True),
    )

    # ── volume by category and department ──
    for dimension, model, column in (
        ("CATEGORY", Category, Complaint.category_id),
        ("DEPARTMENT", Department, Complaint.department_id),
    ):
        current = _grouped_between(db, current_start, moment, model, column)
        previous = _grouped_between(db, previous_start, current_start, model, column)
        # Union of both periods: a category that vanished is as interesting as
        # one that appeared, and iterating only the current period would hide
        # every drop to zero.
        for key in sorted(set(current) | set(previous)):
            add(
                METRIC_VOLUME, dimension, key,
                current.get(key, 0), previous.get(key, 0),
            )

    return trends


# ══════════════════════════════════════════════════════════════
# persistence
# ══════════════════════════════════════════════════════════════
def snapshot(
    db: Session, *, period_type: str = "WEEK", now: datetime | None = None
) -> dict[str, Any]:
    """
    Compute and store the current period's trends.

    Upserts on (period_type, period_start, metric, dimension, dimension_value)
    so re-running for the same period corrects the row rather than duplicating
    it — a scheduler that fires twice must not double the history.
    """
    trends = compute(db, period_type=period_type, now=now)

    _, current_start, _ = period_bounds(period_type, now)

    existing = {
        (row.metric, row.dimension, row.dimension_value): row
        for row in db.execute(
            select(TrendSnapshot).where(
                TrendSnapshot.period_type == period_type.upper(),
                TrendSnapshot.period_start == current_start,
            )
        ).scalars()
    }

    stored = 0
    for trend in trends:
        key = (trend.metric, trend.dimension, trend.dimension_value)
        row = existing.get(key)
        if row is None:
            row = TrendSnapshot(
                period_type=trend.period_type,
                period_start=trend.period_start,
                period_end=trend.period_end,
                metric=trend.metric,
                dimension=trend.dimension,
                dimension_value=trend.dimension_value,
            )
            db.add(row)
        row.period_end = trend.period_end
        row.value = trend.value
        row.previous_value = trend.previous_value
        row.delta_pct = trend.delta_pct
        row.direction = trend.direction
        row.is_anomaly = trend.is_anomaly
        stored += 1

    db.flush()

    material = [t for t in trends if t.is_material]
    anomalies = [t for t in trends if t.is_anomaly]
    log.info(
        "trends_snapshotted",
        period=period_type, computed=stored,
        material=len(material), anomalies=len(anomalies),
    )
    return {
        "period_type": period_type.upper(),
        "computed": stored,
        "material": [t.as_dict() for t in material],
        "anomalies": [t.as_dict() for t in anomalies],
    }


def rising(
    db: Session, *, period_type: str = "WEEK", now: datetime | None = None
) -> list[dict[str, Any]]:
    """
    What is going up and matters — the dashboard's alert strip.

    Sorted by absolute movement rather than percentage, because a jump from 40
    to 70 deserves attention ahead of one from 5 to 11 even though the
    percentage is smaller.
    """
    trends = [
        t
        for t in compute(db, period_type=period_type, now=now)
        if t.is_material and t.direction == TrendDirection.UP
    ]
    trends.sort(key=lambda t: t.value - t.previous_value, reverse=True)
    return [t.as_dict() for t in trends]


def history(
    db: Session, *, metric: str, dimension_value: str = "ALL", limit: int = 12
) -> list[dict[str, Any]]:
    """Stored snapshots for one metric, oldest first — the sparkline."""
    rows = db.execute(
        select(TrendSnapshot)
        .where(
            TrendSnapshot.metric == metric.upper(),
            TrendSnapshot.dimension_value == dimension_value.upper(),
        )
        .order_by(TrendSnapshot.period_start.desc())
        .limit(limit)
    ).scalars().all()

    return [
        {
            "period_start": row.period_start.isoformat() if row.period_start else None,
            "value": float(row.value),
            "previous_value": (
                float(row.previous_value) if row.previous_value is not None else None
            ),
            "delta_pct": float(row.delta_pct) if row.delta_pct is not None else None,
            "direction": row.direction,
            "anomaly": row.is_anomaly,
        }
        for row in reversed(rows)
    ]
