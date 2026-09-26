"""
Reports and exports (FR lxxii, lxxiii; SRS Steps 66-68).

    "Reports must be exportable in CSV, PDF and Excel-compatible formats, and
     every export must be recorded."                    — SRS Steps 66-68

Six report types, each a list of dictionaries assembled from stored rows, and
three writers that turn any of them into a file. Keeping the two apart means a
new report needs no new export code and a new format needs no new reports.

**Deliverable 8 lives here.** ``comparison_report`` is the GenAI-versus-Python
table the brief asks for: one row per compared field per complaint, carrying
both readings, which won, and why. It is read back from ``comparisons`` rather
than recomputed, so what the report shows is provably what the system decided
at the time rather than what it would decide today.

**Every export is recorded.** ``report_exports`` gets a row with the type, the
format, the filters applied and the row count, because "who pulled what data,
when" is an audit question and a report that leaves no trace cannot answer it.
"""

from __future__ import annotations

import csv
import io
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.config import settings
from src.core.logging import get_logger
from src.db.enums import ExportFormat
from src.db.models import (
    Comparison,
    Complaint,
    ComplaintPolicyRef,
    Department,
    Escalation,
    InjectionEvent,
    ReportExport,
    ResponseFlag,
    ReviewAction,
    ReviewQueueItem,
    SLAEvent,
    User,
    VerificationDecision,
)
from src.services import analytics

log = get_logger("services.reports")

COMPLAINTS = "COMPLAINTS"
COMPARISON = "COMPARISON"
SLA = "SLA"
OVERRIDES = "OVERRIDES"
SECURITY = "SECURITY"
TRACEABILITY = "TRACEABILITY"
DEPARTMENT_PERFORMANCE = "DEPARTMENT_PERFORMANCE"
ESCALATIONS = "ESCALATIONS"
RESOLUTION_COMPLIANCE = "RESOLUTION_COMPLIANCE"
MANUAL_REVIEW = "MANUAL_REVIEW"

REPORT_TYPES = (
    COMPLAINTS,
    COMPARISON,
    SLA,
    OVERRIDES,
    SECURITY,
    TRACEABILITY,
    DEPARTMENT_PERFORMANCE,
    ESCALATIONS,
    RESOLUTION_COMPLIANCE,
    MANUAL_REVIEW,
)

# An export is a file someone downloads; an unbounded one is a way to fall over
# during a demo. Callers wanting everything page through instead.
MAX_ROWS = 10_000


@dataclass(slots=True)
class Report:
    """A report is its rows plus the column order they should be read in."""

    report_type: str
    columns: list[str]
    rows: list[dict[str, Any]] = field(default_factory=list)
    filters: dict[str, Any] = field(default_factory=dict)
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def row_count(self) -> int:
        return len(self.rows)

    @property
    def title(self) -> str:
        return {
            COMPLAINTS: "Complaint Register",
            COMPARISON: "GenAI and Python Comparison",
            SLA: "SLA Performance",
            OVERRIDES: "Reviewer Overrides",
            SECURITY: "Security Events",
            TRACEABILITY: "Policy Traceability",
            DEPARTMENT_PERFORMANCE: "Department Performance",
            ESCALATIONS: "Escalation Analysis",
            RESOLUTION_COMPLIANCE: "Resolution Compliance",
            MANUAL_REVIEW: "Manual Review Queue",
        }.get(self.report_type, self.report_type.title())

    def as_dict(self) -> dict[str, Any]:
        return {
            "report_type": self.report_type,
            "title": self.title,
            "columns": self.columns,
            "rows": self.rows,
            "row_count": self.row_count,
            "filters": self.filters,
            "generated_at": self.generated_at.isoformat(),
        }


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, datetime):
        return value.isoformat(sep=" ", timespec="seconds")
    if isinstance(value, (list, tuple)):
        return "; ".join(str(v) for v in value)
    return str(value)


# ══════════════════════════════════════════════════════════════
# the reports
# ══════════════════════════════════════════════════════════════
def complaint_register(
    db: Session, *, limit: int = MAX_ROWS, **filters: Any
) -> Report:
    """Every complaint with its reconciled decision (SRS Step 66)."""
    query = select(Complaint).order_by(Complaint.created_at.desc()).limit(limit)

    if filters.get("status"):
        query = query.where(Complaint.status == str(filters["status"]).upper())
    if filters.get("dataset_tag"):
        query = query.where(Complaint.dataset_tag == str(filters["dataset_tag"]).upper())

    rows = [
        {
            "public_ref": c.public_ref,
            "created_at": c.created_at,
            "title": c.title,
            "status": c.status,
            "category": c.category.code if c.category else None,
            "subcategory": c.subcategory.code if c.subcategory else None,
            "department": c.department.code if c.department else None,
            "urgency": c.urgency,
            "priority": c.priority_code,
            "escalation": c.escalation_code,
            "verification_outcome": c.verification_outcome,
            "injection_suspected": c.injection_suspected,
            "is_duplicate": c.is_duplicate,
            "repeat_count": c.repeat_count,
        }
        for c in db.execute(query).scalars()
    ]

    return Report(
        report_type=COMPLAINTS,
        columns=list(rows[0]) if rows else [
            "public_ref", "created_at", "title", "status", "category",
            "subcategory", "department", "urgency", "priority", "escalation",
            "verification_outcome", "injection_suspected", "is_duplicate",
            "repeat_count",
        ],
        rows=rows,
        filters=filters,
    )


def comparison_report(db: Session, *, limit: int = MAX_ROWS, **filters: Any) -> Report:
    """
    Deliverable 8 — the GenAI versus Python comparison.

    One row per compared field per complaint: what each pipeline said, which
    prevailed, and the explanation of the disagreement. Read back from stored
    ``comparisons`` rows rather than recomputed, so the report shows what the
    system decided at the time and not what it would decide today.
    """
    query = (
        select(Comparison, Complaint.public_ref)
        .join(Complaint, Comparison.complaint_id == Complaint.id)
        .order_by(Complaint.created_at.desc(), Comparison.field)
        .limit(limit)
    )

    if filters.get("mismatches_only"):
        query = query.where(Comparison.status == "MISMATCH")
    if filters.get("field"):
        query = query.where(Comparison.field == str(filters["field"]))

    rows = [
        {
            "public_ref": public_ref,
            "field": row.field,
            "genai_value": row.genai_value,
            "python_value": row.python_value,
            "final_value": row.final_value,
            "status": row.status,
            "severity": row.severity,
            "winner": row.winner,
            "reason_code": row.reason_code,
            "explanation": row.explanation,
        }
        for row, public_ref in db.execute(query).all()
    ]

    return Report(
        report_type=COMPARISON,
        columns=[
            "public_ref", "field", "genai_value", "python_value", "final_value",
            "status", "severity", "winner", "reason_code", "explanation",
        ],
        rows=rows,
        filters=filters,
    )


def sla_report(db: Session, *, limit: int = MAX_ROWS, **filters: Any) -> Report:
    """Every SLA clock with its outcome (SRS Step 67)."""
    query = (
        select(SLAEvent, Complaint.public_ref, Complaint.priority_code)
        .join(Complaint, SLAEvent.complaint_id == Complaint.id)
        .order_by(SLAEvent.due_at.desc())
        .limit(limit)
    )
    if filters.get("breached_only"):
        query = query.where(SLAEvent.breached.is_(True))

    rows = [
        {
            "public_ref": public_ref,
            "priority": priority,
            "event_type": event.event_type,
            "due_at": event.due_at,
            "met_at": event.met_at,
            "breached": event.breached,
            "at_risk": event.at_risk,
        }
        for event, public_ref, priority in db.execute(query).all()
    ]

    return Report(
        report_type=SLA,
        columns=[
            "public_ref", "priority", "event_type", "due_at", "met_at",
            "breached", "at_risk",
        ],
        rows=rows,
        filters=filters,
    )


def override_report(db: Session, *, limit: int = MAX_ROWS, **filters: Any) -> Report:
    """
    Every reviewer action, with what changed.

    The human-in-the-loop evidence: what the system decided, what a person
    changed it to, and why.
    """
    query = (
        select(ReviewAction, Complaint.public_ref)
        .join(Complaint, ReviewAction.complaint_id == Complaint.id)
        .order_by(ReviewAction.created_at.desc())
        .limit(limit)
    )
    if filters.get("overrides_only"):
        query = query.where(ReviewAction.is_override.is_(True))

    rows = []
    for action, public_ref in db.execute(query).all():
        before = action.original_value or {}
        after = action.new_value or {}
        changed = [k for k in after if before.get(k) != after.get(k)]
        rows.append(
            {
                "public_ref": public_ref,
                "at": action.created_at,
                "action": action.action,
                "is_override": action.is_override,
                "changed_fields": changed,
                "before": "; ".join(f"{k}={before.get(k)}" for k in changed),
                "after": "; ".join(f"{k}={after.get(k)}" for k in changed),
                "comment": action.comment,
            }
        )

    return Report(
        report_type=OVERRIDES,
        columns=[
            "public_ref", "at", "action", "is_override", "changed_fields",
            "before", "after", "comment",
        ],
        rows=rows,
        filters=filters,
    )


def security_report(db: Session, *, limit: int = MAX_ROWS, **filters: Any) -> Report:
    """
    Injection detections and guard interventions.

    The Security Testing Report's data: what was attempted, what was caught,
    and what was stopped before a customer saw it.
    """
    rows: list[dict[str, Any]] = []

    for event, public_ref in db.execute(
        select(InjectionEvent, Complaint.public_ref)
        .outerjoin(Complaint, InjectionEvent.complaint_id == Complaint.id)
        .order_by(InjectionEvent.created_at.desc())
        .limit(limit)
    ).all():
        rows.append(
            {
                "at": event.created_at,
                "public_ref": public_ref,
                "kind": "INJECTION",
                "detail": event.pattern_label,
                "severity": event.severity,
                "action_taken": event.action_taken,
                "matched": _text(
                    [span.get("text") for span in (event.matched_spans or [])]
                )[:300],
            }
        )

    for flag, public_ref in db.execute(
        select(ResponseFlag, Complaint.public_ref)
        .join(ResponseFlag.response)
        .join(Complaint)
        .order_by(ResponseFlag.created_at.desc())
        .limit(limit)
    ).all():
        rows.append(
            {
                "at": flag.created_at,
                "public_ref": public_ref,
                "kind": "RESPONSE_GUARD",
                "detail": flag.flag_type,
                "severity": flag.severity,
                "action_taken": "BLOCKED" if flag.severity in ("CRITICAL", "HIGH") else "FLAGGED",
                "matched": (flag.matched_text or "")[:300],
            }
        )

    rows.sort(key=lambda r: r["at"] or datetime.min.replace(tzinfo=UTC), reverse=True)

    return Report(
        report_type=SECURITY,
        columns=["at", "public_ref", "kind", "detail", "severity", "action_taken", "matched"],
        rows=rows[:limit],
        filters=filters,
    )


def traceability_report(db: Session, *, limit: int = MAX_ROWS, **filters: Any) -> Report:
    """
    Every policy reference and whether it held up.

    The Source-Traceability answer in bulk: pick any row and it names the
    document, version, section and whether that version was active.
    """
    query = (
        select(ComplaintPolicyRef, Complaint.public_ref)
        .join(Complaint, ComplaintPolicyRef.complaint_id == Complaint.id)
        .order_by(ComplaintPolicyRef.created_at.desc())
        .limit(limit)
    )
    if filters.get("unresolved_only"):
        query = query.where(ComplaintPolicyRef.resolved.is_(False))

    rows = [
        {
            "public_ref": public_ref,
            "source": ref.source,
            "doc_ref": ref.doc_ref,
            "version": ref.doc_version,
            "section": ref.section_ref,
            "page": ref.page_no,
            "resolved": ref.resolved,
            "was_active": ref.was_active,
            "applicability": ref.applicability,
            "reason": ref.reason,
        }
        for ref, public_ref in db.execute(query).all()
    ]

    return Report(
        report_type=TRACEABILITY,
        columns=[
            "public_ref", "source", "doc_ref", "version", "section", "page",
            "resolved", "was_active", "applicability", "reason",
        ],
        rows=rows,
        filters=filters,
    )


def department_performance_report(
    db: Session, *, limit: int = MAX_ROWS, **filters: Any
) -> Report:
    """Department performance: volume, open backlog, resolution times, SLA compliance."""
    dept_query = select(Department).order_by(Department.code)
    if filters.get("department"):
        dept_query = dept_query.where(Department.code == str(filters["department"]).upper())
    departments = db.execute(dept_query).scalars().all()

    rows = []
    for d in departments:
        comp_query = select(Complaint).where(Complaint.department_id == d.id)
        if filters.get("status"):
            comp_query = comp_query.where(Complaint.status == str(filters["status"]).upper())
        comps = db.execute(comp_query).scalars().all()

        total = len(comps)
        open_cnt = sum(1 for c in comps if c.status not in ("RESOLVED", "CLOSED"))
        resolved_cnt = sum(1 for c in comps if c.status in ("RESOLVED", "CLOSED"))
        escalated_cnt = sum(1 for c in comps if c.escalation_code and c.escalation_code != "NONE")

        resolution_hours = [
            (c.resolved_at - c.created_at).total_seconds() / 3600.0
            for c in comps
            if c.resolved_at and c.created_at
        ]
        avg_res_hours = (
            round(sum(resolution_hours) / len(resolution_hours), 1)
            if resolution_hours
            else None
        )

        comp_ids = [c.id for c in comps]
        breaches_cnt = 0
        total_sla_events = 0
        if comp_ids:
            sla_events = db.execute(
                select(SLAEvent).where(SLAEvent.complaint_id.in_(comp_ids))
            ).scalars().all()
            total_sla_events = len(sla_events)
            breaches_cnt = sum(1 for s in sla_events if s.breached)

        breach_rate = (
            round((breaches_cnt / total_sla_events) * 100, 1)
            if total_sla_events > 0
            else 0.0
        )
        compliance_rate = round(100.0 - breach_rate, 1) if total_sla_events > 0 else 100.0

        rows.append(
            {
                "department_code": d.code,
                "department_name": d.name,
                "is_active": d.is_active,
                "total_complaints": total,
                "open_complaints": open_cnt,
                "resolved_complaints": resolved_cnt,
                "escalated_complaints": escalated_cnt,
                "sla_events": total_sla_events,
                "sla_breaches": breaches_cnt,
                "sla_compliance_pct": compliance_rate,
                "avg_resolution_hours": avg_res_hours,
            }
        )

    return Report(
        report_type=DEPARTMENT_PERFORMANCE,
        columns=[
            "department_code",
            "department_name",
            "is_active",
            "total_complaints",
            "open_complaints",
            "resolved_complaints",
            "escalated_complaints",
            "sla_events",
            "sla_breaches",
            "sla_compliance_pct",
            "avg_resolution_hours",
        ],
        rows=rows[:limit],
        filters=filters,
    )


def escalations_report(
    db: Session, *, limit: int = MAX_ROWS, **filters: Any
) -> Report:
    """Every escalation event with reasons, triggers, and complaint context."""
    query = (
        select(Escalation, Complaint)
        .join(Complaint, Escalation.complaint_id == Complaint.id)
        .order_by(Escalation.created_at.desc())
        .limit(limit)
    )
    if filters.get("escalation_code"):
        query = query.where(Escalation.escalation_code == str(filters["escalation_code"]).upper())
    if filters.get("triggered_by"):
        query = query.where(Escalation.triggered_by == str(filters["triggered_by"]).upper())

    rows = []
    for esc, comp in db.execute(query).all():
        rows.append(
            {
                "public_ref": comp.public_ref,
                "escalation_code": esc.escalation_code,
                "triggered_by": esc.triggered_by,
                "rule_ref": esc.rule_ref,
                "reason": esc.reason,
                "notes": esc.notes,
                "department": comp.department.code if comp.department else None,
                "priority": comp.priority_code,
                "urgency": comp.urgency,
                "status": comp.status,
                "created_at": esc.created_at,
                "acknowledged": esc.acknowledged_at is not None,
            }
        )

    return Report(
        report_type=ESCALATIONS,
        columns=[
            "public_ref",
            "escalation_code",
            "triggered_by",
            "rule_ref",
            "reason",
            "notes",
            "department",
            "priority",
            "urgency",
            "status",
            "created_at",
            "acknowledged",
        ],
        rows=rows,
        filters=filters,
    )


def resolution_compliance_report(
    db: Session, *, limit: int = MAX_ROWS, **filters: Any
) -> Report:
    """Resolution compliance: verification outcomes, compliance scores, and review requirements."""
    query = (
        select(VerificationDecision, Complaint)
        .join(Complaint, VerificationDecision.complaint_id == Complaint.id)
        .order_by(VerificationDecision.created_at.desc())
        .limit(limit)
    )
    if filters.get("outcome"):
        query = query.where(VerificationDecision.outcome == str(filters["outcome"]).upper())
    if filters.get("requires_review_only"):
        query = query.where(VerificationDecision.requires_review.is_(True))

    rows = []
    for vd, comp in db.execute(query).all():
        rows.append(
            {
                "public_ref": comp.public_ref,
                "outcome": vd.outcome,
                "compliance_score": float(vd.compliance_score) if vd.compliance_score is not None else None,
                "agreement_score": float(vd.agreement_score) if vd.agreement_score is not None else None,
                "traceability_score": float(vd.traceability_score) if vd.traceability_score is not None else None,
                "matched_fields": vd.matched_fields,
                "total_fields": vd.total_fields,
                "critical_mismatches": vd.critical_mismatches,
                "high_mismatches": vd.high_mismatches,
                "requires_review": vd.requires_review,
                "review_reasons": "; ".join(str(r) for r in (vd.review_reasons or [])),
                "department": comp.department.code if comp.department else None,
                "decided_at": vd.decided_at or vd.created_at,
            }
        )

    return Report(
        report_type=RESOLUTION_COMPLIANCE,
        columns=[
            "public_ref",
            "outcome",
            "compliance_score",
            "agreement_score",
            "traceability_score",
            "matched_fields",
            "total_fields",
            "critical_mismatches",
            "high_mismatches",
            "requires_review",
            "review_reasons",
            "department",
            "decided_at",
        ],
        rows=rows,
        filters=filters,
    )


def manual_review_report(
    db: Session, *, limit: int = MAX_ROWS, **filters: Any
) -> Report:
    """Manual review queue report: cases routed to human review, entry triggers, and status."""
    query = (
        select(ReviewQueueItem, Complaint, User.email)
        .join(Complaint, ReviewQueueItem.complaint_id == Complaint.id)
        .outerjoin(User, ReviewQueueItem.assigned_to == User.id)
        .order_by(ReviewQueueItem.created_at.desc())
        .limit(limit)
    )
    if filters.get("status"):
        query = query.where(ReviewQueueItem.status == str(filters["status"]).upper())
    if filters.get("open_only"):
        query = query.where(ReviewQueueItem.status == "OPEN")

    rows = []
    for item, comp, user_email in db.execute(query).all():
        rows.append(
            {
                "public_ref": comp.public_ref,
                "queue_status": item.status,
                "priority": item.priority_code or comp.priority_code,
                "reasons": "; ".join(str(r) for r in (item.reasons or [])),
                "assigned_to": user_email or (str(item.assigned_to) if item.assigned_to else None),
                "department": comp.department.code if comp.department else None,
                "escalation": comp.escalation_code,
                "verification_outcome": comp.verification_outcome,
                "complaint_status": comp.status,
                "created_at": item.created_at,
                "closed_at": item.closed_at,
            }
        )

    return Report(
        report_type=MANUAL_REVIEW,
        columns=[
            "public_ref",
            "queue_status",
            "priority",
            "reasons",
            "assigned_to",
            "department",
            "escalation",
            "verification_outcome",
            "complaint_status",
            "created_at",
            "closed_at",
        ],
        rows=rows,
        filters=filters,
    )


BUILDERS = {
    COMPLAINTS: complaint_register,
    COMPARISON: comparison_report,
    SLA: sla_report,
    OVERRIDES: override_report,
    SECURITY: security_report,
    TRACEABILITY: traceability_report,
    DEPARTMENT_PERFORMANCE: department_performance_report,
    ESCALATIONS: escalations_report,
    RESOLUTION_COMPLIANCE: resolution_compliance_report,
    MANUAL_REVIEW: manual_review_report,
}


def build(db: Session, report_type: str, **filters: Any) -> Report:
    """Build one report by name."""
    key = str(report_type).strip().upper()
    builder = BUILDERS.get(key)
    if builder is None:
        raise ValueError(
            f"Unknown report '{report_type}'. Available: {', '.join(REPORT_TYPES)}"
        )
    return builder(db, **filters)


# ══════════════════════════════════════════════════════════════
# writers
# ══════════════════════════════════════════════════════════════
def to_csv(report: Report) -> bytes:
    """
    CSV, UTF-8 with a BOM.

    The BOM is there because Excel on Windows reads a plain UTF-8 CSV as
    Latin-1 and turns every ₹ and é into mojibake. It costs three bytes and
    saves the evaluator opening the file and seeing corruption.
    """
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=report.columns, extrasaction="ignore")
    writer.writeheader()
    for row in report.rows:
        writer.writerow({key: _text(row.get(key)) for key in report.columns})
    return buffer.getvalue().encode("utf-8-sig")


def to_xlsx(report: Report) -> bytes:
    """Excel workbook with a frozen, styled header row."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    book = Workbook()
    sheet = book.active
    sheet.title = report.report_type[:31]

    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="2C3E50")

    sheet.append([col.replace("_", " ").title() for col in report.columns])
    for cell in sheet[1]:
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(vertical="center")

    for row in report.rows:
        sheet.append([_text(row.get(col)) for col in report.columns])

    for index, column in enumerate(report.columns, start=1):
        longest = max(
            [len(column)] + [len(_text(r.get(column))) for r in report.rows[:200]]
        )
        sheet.column_dimensions[get_column_letter(index)].width = min(max(longest + 2, 10), 60)

    sheet.freeze_panes = "A2"

    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def to_pdf(report: Report) -> bytes:
    """
    PDF, landscape, with the table repeating its header on every page.

    Wide reports are truncated to the columns that fit rather than overflowing
    the page: a PDF whose right-hand columns run off the paper is worse than
    one that says which columns it dropped.
    """
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buffer = io.BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=12 * mm, rightMargin=12 * mm,
        topMargin=12 * mm, bottomMargin=12 * mm,
        title=f"SupportNova — {report.title}",
    )

    styles = getSampleStyleSheet()
    cell = styles["BodyText"].clone("cell")
    cell.fontSize = 7
    cell.leading = 9

    story: list[Any] = [
        Paragraph(f"<b>{report.title}</b>", styles["Title"]),
        Paragraph(
            f"Generated {report.generated_at.isoformat(sep=' ', timespec='seconds')} · "
            f"{report.row_count} rows"
            + (f" · filters: {report.filters}" if report.filters else ""),
            styles["Normal"],
        ),
        Spacer(1, 6 * mm),
    ]

    # 10 columns is about what landscape A4 holds legibly.
    columns = report.columns[:10]
    dropped = report.columns[10:]

    data = [[Paragraph(f"<b>{c.replace('_', ' ').title()}</b>", cell) for c in columns]]
    for row in report.rows:
        data.append([Paragraph(_text(row.get(c))[:220], cell) for c in columns])

    if len(data) == 1:
        story.append(Paragraph("No rows matched.", styles["Normal"]))
    else:
        table = Table(data, repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2C3E50")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#BDC3C7")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F4F6F7")]),
                ]
            )
        )
        story.append(table)

    if dropped:
        story.append(Spacer(1, 4 * mm))
        story.append(
            Paragraph(
                f"<i>Columns omitted to fit the page: {', '.join(dropped)}. "
                "The CSV and Excel exports carry every column.</i>",
                styles["Normal"],
            )
        )

    document.build(story)
    return buffer.getvalue()


def to_json(report: Report) -> bytes:
    import json
    return json.dumps(report.as_dict(), indent=2, default=str).encode("utf-8")


WRITERS = {
    ExportFormat.CSV: (to_csv, "csv", "text/csv"),
    ExportFormat.XLSX: (
        to_xlsx,
        "xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ),
    ExportFormat.PDF: (to_pdf, "pdf", "application/pdf"),
    ExportFormat.JSON: (to_json, "json", "application/json"),
}


def render(report: Report, export_format: str) -> tuple[bytes, str, str]:
    """Render a report. Returns ``(payload, filename, media_type)``."""
    key = str(export_format).strip().upper()
    writer = WRITERS.get(key)
    if writer is None:
        raise ValueError(
            f"Unknown format '{export_format}'. Available: "
            f"{', '.join(WRITERS)}"
        )

    write, extension, media_type = writer
    stamp = report.generated_at.strftime("%Y%m%d-%H%M%S")
    filename = f"supportnova-{report.report_type.lower()}-{stamp}.{extension}"
    return write(report), filename, media_type


# ══════════════════════════════════════════════════════════════
# recording
# ══════════════════════════════════════════════════════════════
def record_export(
    db: Session,
    report: Report,
    export_format: str,
    *,
    created_by: uuid.UUID | None = None,
    file_path: str | None = None,
) -> ReportExport:
    """
    Write the export to ``report_exports``.

    "Who pulled what data, when" is an audit question, and an export that
    leaves no trace cannot answer it. The filters are stored too, because the
    same report name over a different slice is a different export.
    """
    row = ReportExport(
        report_type=report.report_type,
        format=str(export_format).upper(),
        filters=report.filters or {},
        file_path=file_path,
        row_count=report.row_count,
        created_by=created_by,
    )
    db.add(row)
    db.flush()
    log.info(
        "report_exported",
        report=report.report_type, format=export_format, rows=report.row_count,
    )
    return row


def save_to_disk(payload: bytes, filename: str) -> Path:
    """Write an export under ``reports/generated/`` and return the path."""
    target = settings.reports_dir
    target.mkdir(parents=True, exist_ok=True)
    path = target / filename
    path.write_bytes(payload)
    return path


def export_history(db: Session, *, limit: int = 50) -> list[dict[str, Any]]:
    """Recent exports, newest first."""
    rows = db.execute(
        select(ReportExport).order_by(ReportExport.created_at.desc()).limit(limit)
    ).scalars().all()

    return [
        {
            "report_type": row.report_type,
            "format": row.format,
            "rows": row.row_count,
            "filters": row.filters,
            "at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]


def summary_pack(db: Session, *, days: int | None = 30) -> dict[str, Any]:
    """
    The figures a report cover page quotes, from the analytics service.

    Deliberately delegated rather than recomputed here: two modules counting
    the same thing separately is how a report and a dashboard end up
    disagreeing in front of a judge.
    """
    return analytics.dashboard(db, days=days)


def available() -> list[dict[str, str]]:
    """What can be exported, for the API's discovery endpoint."""
    titles = {
        COMPLAINTS: "Every complaint with its reconciled decision.",
        COMPARISON: "GenAI against Python, field by field, with explanations.",
        SLA: "Every SLA clock and whether it was met.",
        OVERRIDES: "Every reviewer action and what it changed.",
        SECURITY: "Injection detections and response-guard interventions.",
        TRACEABILITY: "Every policy citation and whether it held up.",
        DEPARTMENT_PERFORMANCE: "Department performance, workload, and SLA compliance.",
        ESCALATIONS: "Complaints escalated to higher tiers, reasons, and triggers.",
        RESOLUTION_COMPLIANCE: "Mandatory steps compliance, prohibited action checks, and verification scores.",
        MANUAL_REVIEW: "Cases routed to human review, entry triggers, and reviewer decisions.",
    }
    return [
        {"report_type": name, "description": titles[name]} for name in REPORT_TYPES
    ]
