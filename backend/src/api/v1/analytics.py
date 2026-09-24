"""
Analytics, trends and report endpoints.

FR lxviii Administrator Dashboard   FR lxix  Complaint Analytics
FR lxx    Trend Detection           FR lxxii Reports
FR lxxiii Export

Access model: managers, administrators and evaluators see the analytics;
agents see the operational panels through the review endpoints instead. Export
is restricted to manager and administrator because a download leaves the system
and is recorded against the person who took it.

Every figure returned here is an aggregate over stored rows. A percentage with
no denominator comes back as ``null``, never as 0 or 100 — an empty system
reports "nothing to measure", not "perfect compliance".
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select

from schemas.analytics import (
    DashboardOut,
    ExportHistoryOut,
    ReportOut,
    ReportTypeOut,
    TrendOut,
    TrendSnapshotOut,
)
from src.core.deps import CurrentUser, DbSession, require_role
from src.core.errors import NotFoundError, ValidationError
from src.core.logging import get_logger
from src.db.enums import UserRole
from src.db.models import Complaint
from src.services import analytics, reports, trends

log = get_logger("api.analytics")

router = APIRouter(prefix="/analytics", tags=["Analytics & Reports"])

VIEWERS = (UserRole.MANAGER, UserRole.ADMIN, UserRole.EVALUATOR)
EXPORTERS = (UserRole.MANAGER, UserRole.ADMIN)


# ══════════════════════════════════════════════════════════════
# dashboard
# ══════════════════════════════════════════════════════════════
@router.get(
    "/dashboard",
    response_model=DashboardOut,
    dependencies=[Depends(require_role(*VIEWERS))],
    summary="The administrator dashboard, in one call",
)
def dashboard(
    db: DbSession,
    days: int | None = Query(30, ge=1, le=365, description="Null for all time."),
) -> DashboardOut:
    """
    Every panel, assembled server-side (FR lxviii).

    One call rather than eight, because panels fetched at different instants
    can show figures that do not add up — and "why does the total not match"
    is an expensive question during a demo.
    """
    return DashboardOut(**analytics.dashboard(db, days=days))


@router.get(
    "/volume",
    dependencies=[Depends(require_role(*VIEWERS))],
    summary="Complaint volume by status",
)
def volume(db: DbSession, days: int | None = Query(30, ge=1, le=365)) -> dict[str, Any]:
    return analytics.volume(db, days=days)


@router.get(
    "/categories",
    dependencies=[Depends(require_role(*VIEWERS))],
    summary="Category distribution",
)
def categories(
    db: DbSession, days: int | None = Query(30, ge=1, le=365)
) -> list[dict[str, Any]]:
    """
    Distribution across categories (FR lxix).

    Complaints the system could not classify appear as ``UNCLASSIFIED`` rather
    than being dropped — a distribution that omits its own failures is a
    flattering one.
    """
    return analytics.by_category(db, days=days)


@router.get(
    "/departments",
    dependencies=[Depends(require_role(*VIEWERS))],
    summary="Department load and open backlog",
)
def departments(
    db: DbSession, days: int | None = Query(30, ge=1, le=365)
) -> list[dict[str, Any]]:
    return analytics.department_load(db, days=days)


@router.get(
    "/pipelines",
    dependencies=[Depends(require_role(*VIEWERS))],
    summary="How often the model matched the rule engine",
)
def pipelines(
    db: DbSession, days: int | None = Query(30, ge=1, le=365)
) -> dict[str, Any]:
    """
    Pipeline agreement — deliberately **not** called accuracy.

    This measures Pipeline 1 against Pipeline 2, not against truth: a
    complaint where both were wrong in the same way counts as agreement. Real
    accuracy needs the labelled dataset and comes from the benchmark runner.
    """
    return analytics.pipeline_agreement(db, days=days)


# ══════════════════════════════════════════════════════════════
# trends
# ══════════════════════════════════════════════════════════════
@router.get(
    "/trends",
    response_model=list[TrendOut],
    dependencies=[Depends(require_role(*VIEWERS))],
    summary="What is rising and matters",
)
def rising_trends(
    db: DbSession,
    period: str = Query("WEEK", pattern="^(DAY|WEEK|MONTH)$"),
) -> list[TrendOut]:
    """
    Rising metrics above the noise floor (FR lxx; SRS Step 65).

    Sorted by absolute movement, not percentage: a jump from 40 to 70 deserves
    attention ahead of one from 5 to 11, even though the percentage is smaller.
    """
    return [TrendOut(**row) for row in trends.rising(db, period_type=period)]


@router.post(
    "/trends/snapshot",
    dependencies=[Depends(require_role(UserRole.MANAGER, UserRole.ADMIN))],
    summary="Compute and store the current period's trends",
)
def snapshot_trends(
    db: DbSession,
    period: str = Query("WEEK", pattern="^(DAY|WEEK|MONTH)$"),
) -> dict[str, Any]:
    """
    Take a trend snapshot.

    Idempotent per period: re-running corrects the stored row rather than
    duplicating it, so a scheduler firing twice cannot double the history.
    """
    result = trends.snapshot(db, period_type=period)
    db.commit()
    return result


@router.get(
    "/trends/history",
    response_model=list[TrendSnapshotOut],
    dependencies=[Depends(require_role(*VIEWERS))],
    summary="Stored history for one metric",
)
def trend_history(
    db: DbSession,
    metric: str = Query("COMPLAINT_VOLUME"),
    dimension_value: str = Query("ALL"),
    limit: int = Query(12, ge=1, le=104),
) -> list[TrendSnapshotOut]:
    return [
        TrendSnapshotOut(**row)
        for row in trends.history(
            db, metric=metric, dimension_value=dimension_value, limit=limit
        )
    ]


# ══════════════════════════════════════════════════════════════
# reports
# ══════════════════════════════════════════════════════════════
@router.get(
    "/reports",
    response_model=list[ReportTypeOut],
    dependencies=[Depends(require_role(*VIEWERS))],
    summary="What can be reported on",
)
def list_reports() -> list[ReportTypeOut]:
    return [ReportTypeOut(**row) for row in reports.available()]


@router.get(
    "/reports/{report_type}",
    response_model=ReportOut,
    dependencies=[Depends(require_role(*VIEWERS))],
    summary="Read a report as JSON",
)
def read_report(
    report_type: str,
    db: DbSession,
    limit: int = Query(1000, ge=1, le=10000),
    mismatches_only: bool = False,
    breached_only: bool = False,
    overrides_only: bool = False,
    unresolved_only: bool = False,
    status_filter: str | None = Query(None, alias="status"),
    dataset_tag: str | None = None,
    field_name: str | None = Query(None, alias="field"),
) -> ReportOut:
    """
    One report, rendered as JSON for the dashboard to display.

    ``COMPARISON`` is Deliverable 8: one row per compared field per complaint,
    both pipelines' readings, which prevailed, and the explanation — read back
    from stored rows rather than recomputed.
    """
    try:
        report = reports.build(
            db,
            report_type,
            limit=limit,
            mismatches_only=mismatches_only,
            breached_only=breached_only,
            overrides_only=overrides_only,
            unresolved_only=unresolved_only,
            status=status_filter,
            dataset_tag=dataset_tag,
            field=field_name,
        )
    except ValueError as exc:
        raise NotFoundError(str(exc)) from exc

    return ReportOut(**report.as_dict())


@router.get(
    "/reports/{report_type}/export",
    dependencies=[Depends(require_role(*EXPORTERS))],
    summary="Download a report as CSV, XLSX or PDF",
    response_class=Response,
)
def export_report(
    report_type: str,
    db: DbSession,
    user: CurrentUser,
    export_format: str = Query("CSV", alias="format", pattern="^(?i)(CSV|XLSX|PDF)$"),
    limit: int = Query(5000, ge=1, le=10000),
    mismatches_only: bool = False,
    breached_only: bool = False,
    overrides_only: bool = False,
    unresolved_only: bool = False,
) -> Response:
    """
    Export a report (FR lxxiii; SRS Step 68).

    The export is recorded in ``report_exports`` before the bytes are returned:
    "who pulled what data, when" is an audit question, and a download that
    leaves no trace cannot answer it.
    """
    try:
        report = reports.build(
            db,
            report_type,
            limit=limit,
            mismatches_only=mismatches_only,
            breached_only=breached_only,
            overrides_only=overrides_only,
            unresolved_only=unresolved_only,
        )
    except ValueError as exc:
        raise NotFoundError(str(exc)) from exc

    try:
        payload, filename, media_type = reports.render(report, export_format)
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc

    reports.record_export(db, report, export_format, created_by=user.id)
    db.commit()

    return Response(
        content=payload,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(
    "/exports",
    response_model=list[ExportHistoryOut],
    dependencies=[Depends(require_role(*VIEWERS))],
    summary="Recent exports",
)
def export_history(db: DbSession, limit: int = Query(50, ge=1, le=200)):
    return [ExportHistoryOut(**row) for row in reports.export_history(db, limit=limit)]


# ══════════════════════════════════════════════════════════════
# agent-facing
# ══════════════════════════════════════════════════════════════
@router.get(
    "/my-queue",
    dependencies=[
        Depends(
            require_role(
                UserRole.AGENT, UserRole.REVIEWER, UserRole.MANAGER, UserRole.ADMIN
            )
        )
    ],
    summary="An agent's own workload",
)
def my_queue(db: DbSession, user: CurrentUser) -> dict[str, Any]:
    """
    What is assigned to the caller (FR lxvii).

    Scoped to the caller rather than taking a user id, so one agent cannot read
    another's workload by guessing an identifier.
    """
    rows = db.execute(
        select(Complaint)
        .where(Complaint.assigned_to == user.id)
        .order_by(Complaint.priority_code.asc(), Complaint.created_at.asc())
        .limit(100)
    ).scalars().all()

    return {
        "assigned": len(rows),
        "by_priority": {
            code: sum(1 for r in rows if r.priority_code == code)
            for code in sorted({r.priority_code for r in rows if r.priority_code})
        },
        "complaints": [
            {
                "public_ref": row.public_ref,
                "title": row.title,
                "status": row.status,
                "priority": row.priority_code,
                "urgency": row.urgency,
                "escalation": row.escalation_code,
            }
            for row in rows
        ],
    }
