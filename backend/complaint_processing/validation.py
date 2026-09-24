"""
Complaint validation (FR iv; SRS Step 10).

    "The system must detect empty complaints, extremely short complaints,
     duplicate submissions, invalid reference IDs, missing mandatory fields
     and unsupported attachments."                         — SRS Step 10

Every finding is persisted to ``complaint_validation_issues``, including for a
complaint that is rejected outright and therefore never gets a ``complaints``
row. That is what ``submitted_ref`` is for: the attempt is recorded even when
the record is not, so "we validate submissions" is demonstrable by query rather
than by assertion.

**Rejection is rare and deliberate.** Only an empty complaint is refused. A
short complaint, an unrecognised order reference, a missing field, a suspected
injection — all are accepted with a warning and routed for review. The reason
is the same one throughout this system: a customer with a badly-formed
complaint still has a complaint, and refusing to accept it is a worse failure
than accepting it with a flag. The SRS asks us to *detect* these things, not to
turn them away.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from sqlalchemy.orm import Session

from src.core.config import settings
from src.core.logging import get_logger
from src.db.enums import IssueOutcome, Severity, ValidationIssueCode
from src.db.models import ComplaintValidationIssue

log = get_logger("complaint_processing.validation")

# Attachment types a complaint may carry. Anything else is recorded and the
# attachment dropped, while the complaint itself is still accepted.
ALLOWED_ATTACHMENT_TYPES = frozenset(
    {"application/pdf", "image/jpeg", "image/png", "image/webp", "text/plain"}
)

# Which configured entity pattern governs each submitted reference field.
#
# The patterns themselves live in config/signals.yaml and are loaded from
# app_config, so there is exactly one definition of what an order reference
# looks like. An earlier version hardcoded a second set here, and the two had
# already drifted: validation accepted five digits where extraction required
# six, so a reference could pass intake and then be invisible to every rule
# that needs an order number.
#
# A reference that does not match is a warning, never a rejection. Customers
# mistype, and the complaint is still about something real.
REFERENCE_FIELD_PATTERNS = {
    "order_ref": "ORDER_ID",
    "transaction_ref": "TRANSACTION_ID",
}

# Used only when the configured patterns are unavailable.
FALLBACK_PATTERNS = {
    "ORDER_ID": r"\bZ[NK]-?\d{6,8}\b|\bORD-?\d{6,10}\b",
    "TRANSACTION_ID": r"\bTXN[-_ ]?[A-Z0-9]{8,14}\b",
}


@lru_cache(maxsize=64)
def _anchored(pattern: str) -> re.Pattern[str] | None:
    """
    Turn a search pattern into a whole-value matcher.

    The configured patterns are written to find a reference inside free text,
    so they carry word boundaries. Validating a submitted field is a different
    question -- is this value, in its entirety, a valid reference -- so the
    boundaries are stripped and the whole thing anchored.
    """
    try:
        return re.compile(f"^(?:{pattern.replace(chr(92) + 'b', '')})$", re.IGNORECASE)
    except re.error:
        return None

MANDATORY_FIELDS = ("title", "description")


@dataclass(slots=True)
class ValidationIssue:
    """One problem found with a submission."""

    code: str
    message: str
    severity: str = Severity.MEDIUM
    outcome: str = IssueOutcome.ACCEPTED_WITH_WARNING
    field_name: str | None = None
    detail: str | None = None

    @property
    def rejects(self) -> bool:
        return self.outcome == IssueOutcome.REJECTED

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "severity": self.severity,
            "outcome": self.outcome,
            "field": self.field_name,
            "detail": self.detail,
        }


@dataclass(slots=True)
class ValidationReport:
    """Everything found with one submission."""

    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def rejected(self) -> bool:
        return any(issue.rejects for issue in self.issues)

    @property
    def needs_review(self) -> bool:
        return any(
            issue.outcome == IssueOutcome.ROUTED_TO_REVIEW for issue in self.issues
        )

    @property
    def codes(self) -> list[str]:
        return [issue.code for issue in self.issues]

    def add(self, issue: ValidationIssue) -> None:
        self.issues.append(issue)

    def summary(self) -> dict[str, Any]:
        return {
            "rejected": self.rejected,
            "needs_review": self.needs_review,
            "issues": [issue.as_dict() for issue in self.issues],
        }


# ══════════════════════════════════════════════════════════════
# checks
# ══════════════════════════════════════════════════════════════
def validate_submission(
    *,
    title: str | None,
    description: str | None,
    clean_description: str | None = None,
    order_ref: str | None = None,
    transaction_ref: str | None = None,
    attachments: list[dict[str, Any]] | None = None,
    injection_suspected: bool = False,
    truncated: bool = False,
    min_length: int | None = None,
    max_length: int | None = None,
    entity_patterns: dict[str, str] | None = None,
) -> ValidationReport:
    """
    Check one submission against every rule in SRS Step 10.

    ``clean_description`` is the pre-processed text; length is judged on it
    rather than the raw form, because 4,000 zero-width characters are not a
    long complaint.

    ``entity_patterns`` are the configured reference regexes from
    ``app_config['entity_patterns']``. Passing them in keeps this function
    free of a database session while still using the one definition of what a
    reference looks like.
    """
    patterns = {**FALLBACK_PATTERNS, **(entity_patterns or {})}
    report = ValidationReport()
    body = (clean_description if clean_description is not None else description) or ""
    floor = min_length or settings.min_complaint_length
    ceiling = max_length or settings.max_complaint_length

    # ── empty: the only outright rejection ──
    if not body.strip():
        report.add(
            ValidationIssue(
                code=ValidationIssueCode.EMPTY_COMPLAINT,
                message="The complaint has no description. There is nothing to act on.",
                severity=Severity.HIGH,
                outcome=IssueOutcome.REJECTED,
                field_name="description",
            )
        )
        return report  # nothing else is meaningful

    # ── too short ──
    if len(body.strip()) < floor:
        report.add(
            ValidationIssue(
                code=ValidationIssueCode.TOO_SHORT,
                message=(
                    f"The complaint is {len(body.strip())} characters, below the "
                    f"{floor}-character minimum. It is accepted, and a clarification "
                    "question will be asked rather than details being invented."
                ),
                severity=Severity.MEDIUM,
                outcome=IssueOutcome.ROUTED_TO_REVIEW,
                field_name="description",
            )
        )

    # ── too long ──
    if truncated or len(body) > ceiling:
        report.add(
            ValidationIssue(
                code=ValidationIssueCode.TOO_LONG,
                message=(
                    f"The complaint exceeded the {ceiling}-character limit and was "
                    "truncated for analysis. The full text is retained."
                ),
                # Informational, not a defect: the complaint is intact in
                # description_raw and only the analysed copy was shortened.
                severity=Severity.INFORMATIONAL,
                outcome=IssueOutcome.ACCEPTED_WITH_WARNING,
                field_name="description",
            )
        )

    # ── mandatory fields ──
    values = {"title": title, "description": description}
    for name in MANDATORY_FIELDS:
        if not (values.get(name) or "").strip():
            report.add(
                ValidationIssue(
                    code=ValidationIssueCode.MISSING_MANDATORY_FIELD,
                    message=f"'{name}' was not supplied.",
                    severity=Severity.MEDIUM,
                    outcome=IssueOutcome.ACCEPTED_WITH_WARNING,
                    field_name=name,
                )
            )

    # ── reference shapes ──
    for name, value in (("order_ref", order_ref), ("transaction_ref", transaction_ref)):
        if not value:
            continue
        compiled = _anchored(patterns.get(REFERENCE_FIELD_PATTERNS[name], ""))
        if compiled is None:
            continue
        if not compiled.match(value.strip()):
            report.add(
                ValidationIssue(
                    code=ValidationIssueCode.INVALID_REFERENCE_ID,
                    message=(
                        f"'{value}' is not a recognised {name.replace('_', ' ')}. "
                        "The complaint is accepted; the reference will be confirmed "
                        "with the customer rather than guessed."
                    ),
                    severity=Severity.MEDIUM,
                    outcome=IssueOutcome.ROUTED_TO_REVIEW,
                    field_name=name,
                    detail=value[:200],
                )
            )

    # ── attachments ──
    for attachment in attachments or []:
        content_type = str(attachment.get("content_type", "")).lower()
        if content_type and content_type not in ALLOWED_ATTACHMENT_TYPES:
            report.add(
                ValidationIssue(
                    code=ValidationIssueCode.UNSUPPORTED_ATTACHMENT,
                    message=(
                        f"Attachment '{attachment.get('filename', 'unnamed')}' is of "
                        f"unsupported type {content_type} and was not stored. The "
                        "complaint itself is accepted."
                    ),
                    severity=Severity.MEDIUM,
                    outcome=IssueOutcome.ACCEPTED_WITH_WARNING,
                    field_name="attachments",
                    detail=content_type,
                )
            )

    # ── injection ──
    if injection_suspected:
        report.add(
            ValidationIssue(
                code=ValidationIssueCode.SUSPECTED_INJECTION,
                message=(
                    "The complaint contains text shaped like an instruction to the "
                    "system. It is processed as complaint content and routed for "
                    "review; no instruction within it is followed."
                ),
                severity=Severity.HIGH,
                outcome=IssueOutcome.ROUTED_TO_REVIEW,
                field_name="description",
            )
        )

    if report.issues:
        log.info(
            "complaint_validation_issues",
            codes=report.codes, rejected=report.rejected,
        )
    return report


# Which review reason each intake finding raises. Only findings whose
# outcome is ROUTED_TO_REVIEW appear here: an accepted-with-warning finding is
# recorded for the audit but does not need a human to look.
REVIEW_REASON_FOR_ISSUE = {
    ValidationIssueCode.TOO_SHORT: "AMBIGUOUS_COMPLAINT",
    ValidationIssueCode.INVALID_REFERENCE_ID: "AMBIGUOUS_COMPLAINT",
    ValidationIssueCode.SUSPECTED_INJECTION: "SENSITIVE_COMPLAINT",
    ValidationIssueCode.DUPLICATE_COMPLAINT: "AMBIGUOUS_COMPLAINT",
}


def review_reasons(report: ValidationReport) -> list[str]:
    """
    The review reasons an intake report raises.

    This is what makes ROUTED_TO_REVIEW mean something. Without it the outcome
    is decorative: a suspected injection on a complaint both pipelines agreed
    about would be recorded and then reach nobody.
    """
    reasons: list[str] = []
    for issue in report.issues:
        if issue.outcome != IssueOutcome.ROUTED_TO_REVIEW:
            continue
        reason = REVIEW_REASON_FOR_ISSUE.get(issue.code)
        if reason and reason not in reasons:
            reasons.append(reason)
    return reasons


def add_duplicate_issue(report: ValidationReport, *, public_ref: str, similarity: float) -> None:
    """
    Record a duplicate finding.

    Accepted, never rejected. A customer who submits twice because the first
    attempt appeared to fail still needs an answer, and the link to the
    original is more useful than a refusal.
    """
    report.add(
        ValidationIssue(
            code=ValidationIssueCode.DUPLICATE_COMPLAINT,
            message=(
                f"This appears to duplicate complaint {public_ref} "
                f"({similarity:.0%} similar). It is accepted and linked to the "
                "original rather than refused."
            ),
            severity=Severity.MEDIUM,
            outcome=IssueOutcome.ROUTED_TO_REVIEW,
            field_name="description",
            detail=public_ref,
        )
    )


# ══════════════════════════════════════════════════════════════
# persistence
# ══════════════════════════════════════════════════════════════
def persist(
    db: Session,
    report: ValidationReport,
    *,
    complaint_id: uuid.UUID | None = None,
    submitted_ref: str | None = None,
    submitted_by_user_id: uuid.UUID | None = None,
) -> list[ComplaintValidationIssue]:
    """
    Write every finding to ``complaint_validation_issues``.

    ``complaint_id`` is null for a rejected submission, which never becomes a
    complaint. ``submitted_ref`` carries the trail in that case, so a refused
    intake is still visible in the audit rather than vanishing.
    """
    rows: list[ComplaintValidationIssue] = []
    for issue in report.issues:
        row = ComplaintValidationIssue(
            complaint_id=complaint_id,
            submitted_ref=submitted_ref,
            submitted_by_user_id=submitted_by_user_id,
            issue_code=issue.code,
            severity=issue.severity,
            outcome=issue.outcome,
            field=issue.field_name,
            message=issue.message,
            detail=issue.detail,
        )
        db.add(row)
        rows.append(row)

    if rows:
        db.flush()
    return rows
