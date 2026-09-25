"""
What a customer can do to their own complaint after submitting it.

Three actions, all deterministic — none of them calls a model:

* ``answer_clarification`` — reply to a question the pipeline asked instead of
  guessing (SRS Step 43, the Missing-Information Challenge). Until this
  existed, the questions were stored and shown but could not be answered,
  which made "ask rather than invent" a dead end for the customer.
* ``attach_evidence`` — upload a photo, receipt or document (SRS Step 10).
* ``preview`` — what the system will read in the text, shown while the
  customer is still typing.

**Everything a customer writes here is untrusted input**, handled exactly as
the complaint body was: an answer is scanned for injection before it is
stored, and an upload is identified by its bytes, not by the name or content
type the browser claims. A customer who has discovered that the complaint
body is screened should not find an unscreened side door in the reply box.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from complaint_processing import followup
from complaint_processing.entities import extract_entities, load_entity_patterns
from complaint_processing.preprocess import preprocess
from security.injection_defense import record_events, scan
from src.core.config import settings
from src.core.errors import ConflictError, NotFoundError, ValidationError
from src.core.logging import get_logger
from src.db.enums import ComplaintStatus
from src.db.models import (
    ClarificationQuestion,
    Complaint,
    ComplaintAttachment,
    FollowUp,
    User,
)
from src.services import lifecycle
from src.services.audit import record_audit
from src.services.storage import get_storage

log = get_logger("complaint_processing.customer_actions")

MAX_ANSWER_CHARS = 2000
MAX_ATTACHMENTS = 10

# Which complaint field a missing-field answer can fill, and the entity types
# that are allowed to fill it. An answer to "what is your consignment number?"
# that contains one should make the rule engine's has_order_ref true; an
# answer that merely mentions an amount should not.
FILLABLE: dict[str, tuple[str, tuple[str, ...]]] = {
    "ORDER_ID": ("order_ref", ("ORDER_ID", "TRACKING_ID")),
    "ORDER_REF": ("order_ref", ("ORDER_ID", "TRACKING_ID")),
    "TRACKING_ID": ("order_ref", ("TRACKING_ID", "ORDER_ID")),
    "TRANSACTION_ID": ("transaction_ref", ("TRANSACTION_ID", "INVOICE_ID")),
    "INVOICE_ID": ("transaction_ref", ("INVOICE_ID", "TRANSACTION_ID")),
}


# ══════════════════════════════════════════════════════════════
# answering a clarifying question
# ══════════════════════════════════════════════════════════════
@dataclass
class AnswerResult:
    question: ClarificationQuestion
    filled: dict[str, str] = field(default_factory=dict)
    injection_suspected: bool = False
    all_answered: bool = False
    status_changed_to: str | None = None


def answer_clarification(
    db: Session,
    complaint: Complaint,
    question_id: Any,
    answer: str,
    *,
    actor: User | None,
    request: Request | None = None,
) -> AnswerResult:
    """
    Record the customer's reply to one clarifying question.

    Side effects, each of which is the point of answering at all:

    1. The answer is scanned for injection and the findings recorded, exactly
       as the complaint body was. Suspected text is still stored — refusing
       it would punish a customer for quoting an error message — but the
       complaint is flagged.
    2. If the question asked for a reference and the reply contains one, the
       complaint's empty ``order_ref``/``transaction_ref`` is filled, so the
       rule engine sees it on the next analysis. A filled field is never
       overwritten.
    3. When the last open question is answered, open CLARIFICATION follow-ups
       are closed and a complaint AWAITING_CUSTOMER moves back to IN_PROGRESS.
    """
    text = (answer or "").strip()
    if not text:
        raise ValidationError("Please write an answer before sending it.")
    if len(text) > MAX_ANSWER_CHARS:
        raise ValidationError(f"Answers are limited to {MAX_ANSWER_CHARS} characters.")

    question = db.execute(
        select(ClarificationQuestion).where(
            ClarificationQuestion.id == question_id,
            ClarificationQuestion.complaint_id == complaint.id,
        )
    ).scalars().first()
    if question is None:
        raise NotFoundError("That question does not belong to this complaint.")

    result = AnswerResult(question=question)

    # ── 1. untrusted text: scan before storing ──
    screened = scan(db, text)
    if screened.suspected:
        record_events(db, screened, source_type="CLARIFICATION", complaint_id=complaint.id)
        complaint.injection_suspected = True
        result.injection_suspected = True

    before = {"answer_len": len(question.answer or ""), "answered_at": _iso(question.answered_at)}
    question.answer = text
    question.answered_at = datetime.now(UTC)

    # ── 2. fill a missing reference the question was asking for ──
    target = FILLABLE.get((question.missing_field or "").upper())
    if target:
        column, entity_types = target
        if not getattr(complaint, column, None):
            found = extract_entities(text, load_entity_patterns(db))
            for entity_type in entity_types:
                hits = found.by_type.get(entity_type)
                if hits:
                    value = hits[0].value
                    setattr(complaint, column, value[:128])
                    result.filled[column] = value
                    break

    db.flush()

    # ── 3. last question answered: stop chasing, resume work ──
    remaining = db.execute(
        select(ClarificationQuestion.id).where(
            ClarificationQuestion.complaint_id == complaint.id,
            ClarificationQuestion.answered_at.is_(None),
        )
    ).first()
    result.all_answered = remaining is None

    if result.all_answered:
        open_chases = db.execute(
            select(FollowUp).where(
                FollowUp.complaint_id == complaint.id,
                FollowUp.follow_up_type == followup.CLARIFICATION,
                FollowUp.completed_at.is_(None),
            )
        ).scalars().all()
        for chase in open_chases:
            followup.complete(db, chase.id, user_id=actor.id if actor else None)

        if complaint.status == ComplaintStatus.AWAITING_CUSTOMER:
            lifecycle.transition(
                db, complaint, ComplaintStatus.IN_PROGRESS, actor=actor,
                reason="The customer answered every outstanding question.",
            )
            result.status_changed_to = ComplaintStatus.IN_PROGRESS

    record_audit(
        db, actor=actor, entity_type="complaint", entity_id=str(complaint.id),
        action="CLARIFICATION_ANSWERED",
        before=before,
        after={
            "question_ordinal": question.ordinal,
            "missing_field": question.missing_field,
            "answer_len": len(text),
            "filled": result.filled,
            "injection_suspected": result.injection_suspected,
            "all_answered": result.all_answered,
        },
        reason="Customer reply to a clarifying question.",
        request=request,
    )
    log.info(
        "clarification_answered", public_ref=complaint.public_ref,
        ordinal=question.ordinal, filled=list(result.filled), all_answered=result.all_answered,
    )
    return result


# ══════════════════════════════════════════════════════════════
# evidence upload
# ══════════════════════════════════════════════════════════════
@dataclass(frozen=True)
class SniffedType:
    mime: str
    extension: str
    label: str


ALLOWED_EVIDENCE = "PDF, DOCX, PNG, JPEG, WEBP or plain text"


def sniff(data: bytes, file_name: str) -> SniffedType | None:
    """
    Identify a file by its first bytes.

    The browser's content type and the file extension are both claims made by
    the uploader. The magic number is a property of the file. A ``.pdf`` that
    is really an executable is refused here rather than stored with a
    reassuring MIME type on it.
    """
    head = data[:16]
    name = file_name.lower()
    if head.startswith(b"%PDF-"):
        return SniffedType("application/pdf", "pdf", "PDF")
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return SniffedType("image/png", "png", "PNG image")
    if head.startswith(b"\xff\xd8\xff"):
        return SniffedType("image/jpeg", "jpg", "JPEG image")
    if head[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return SniffedType("image/webp", "webp", "WEBP image")
    if head.startswith(b"PK\x03\x04") and name.endswith(".docx") and b"word/" in data[:4096]:
        return SniffedType(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "docx", "Word document",
        )
    if name.endswith(".txt") and b"\x00" not in data:
        try:
            data.decode("utf-8")
        except UnicodeDecodeError:
            return None
        return SniffedType("text/plain", "txt", "text file")
    return None


def safe_file_name(file_name: str) -> str:
    """A display name with the path, control characters and odd spacing removed."""
    base = re.split(r"[\\/]", file_name or "")[-1]
    base = unicodedata.normalize("NFKC", base)
    base = "".join(ch for ch in base if ch.isprintable() and ch not in '<>:"|?*')
    base = re.sub(r"\s+", " ", base).strip(" .")
    return (base or "evidence")[:200]


def attach_evidence(
    db: Session,
    complaint: Complaint,
    *,
    data: bytes,
    file_name: str,
    actor: User | None,
    request: Request | None = None,
) -> tuple[ComplaintAttachment, bool]:
    """
    Store one evidence file against a complaint.

    Returns ``(attachment, created)``. Uploading the same bytes twice returns
    the existing row rather than storing a second copy: a customer who is not
    sure the first upload worked will press the button again, and the agent
    should not then read the same receipt twice.
    """
    if not data:
        raise ValidationError("That file is empty.")
    if len(data) > settings.max_upload_bytes:
        raise ValidationError(
            f"Files are limited to {settings.max_upload_mb} MB; this one is "
            f"{len(data) / (1024 * 1024):.1f} MB."
        )

    kind = sniff(data, file_name)
    if kind is None:
        raise ValidationError(
            f"That file type is not accepted. Please upload a {ALLOWED_EVIDENCE} file."
        )

    digest = hashlib.sha256(data).hexdigest()
    existing = db.execute(
        select(ComplaintAttachment).where(
            ComplaintAttachment.complaint_id == complaint.id,
            ComplaintAttachment.file_hash == digest,
        )
    ).scalars().first()
    if existing is not None:
        return existing, False

    count = len(db.execute(
        select(ComplaintAttachment.id).where(ComplaintAttachment.complaint_id == complaint.id)
    ).all())
    if count >= MAX_ATTACHMENTS:
        raise ConflictError(
            f"A complaint can hold at most {MAX_ATTACHMENTS} files. "
            "Please contact us if you need to send more."
        )

    key = f"evidence/{complaint.id}/{digest[:2]}/{digest}.{kind.extension}"
    path = get_storage().save(data, key=key, content_type=kind.mime)

    attachment = ComplaintAttachment(
        complaint_id=complaint.id,
        file_name=safe_file_name(file_name),
        file_path=path,
        mime_type=kind.mime,
        size_bytes=len(data),
        file_hash=digest,
    )
    db.add(attachment)
    db.flush()

    record_audit(
        db, actor=actor, entity_type="complaint", entity_id=str(complaint.id),
        action="EVIDENCE_ATTACHED",
        after={
            "attachment_id": str(attachment.id),
            "file_name": attachment.file_name,
            "mime_type": kind.mime,
            "size_bytes": len(data),
            "sha256": digest,
        },
        request=request,
    )
    log.info("evidence_attached", public_ref=complaint.public_ref, mime=kind.mime, bytes=len(data))
    return attachment, True


def load_evidence(complaint: Complaint, attachment_id: Any, db: Session) -> tuple[ComplaintAttachment, bytes]:
    attachment = db.execute(
        select(ComplaintAttachment).where(
            ComplaintAttachment.id == attachment_id,
            ComplaintAttachment.complaint_id == complaint.id,
        )
    ).scalars().first()
    if attachment is None:
        raise NotFoundError("No such file on this complaint.")
    return attachment, get_storage().load(attachment.file_path)


# ══════════════════════════════════════════════════════════════
# live pre-check while typing
# ══════════════════════════════════════════════════════════════
REFERENCE_TYPES = ("ORDER_ID", "TRACKING_ID", "TRANSACTION_ID", "INVOICE_ID")


def preview(db: Session, *, title: str, description: str, with_category: bool) -> dict[str, Any]:
    """
    What the pipelines will read in this text — without storing anything.

    Deterministic and free: pattern extraction, the injection screen and,
    optionally, the rule engine's category. No model is called, no complaint
    row is written, no injection event is recorded — a preview is not a
    submission, and counting keystrokes as attacks would poison the security
    figures.

    Deliberately customer-safe: it can say *what* was recognised and *what is
    missing*, and the likely category, but never the priority, urgency or
    escalation level. Those are internal routing decisions, and showing them
    while the customer types would invite writing the complaint to the score.
    """
    body = f"{title.strip()}\n\n{description.strip()}".strip()
    prepared = preprocess(body)
    text = prepared.clean

    found = extract_entities(text, load_entity_patterns(db))
    entities = [
        {"type": e.entity_type, "value": e.value, "start": e.span_start, "end": e.span_end}
        for e in found.entities
    ][:24]

    screened = scan(db, text)

    hints: list[dict[str, str]] = []
    words = len(re.findall(r"\w+", description))
    if not any(found.by_type.get(t) for t in REFERENCE_TYPES):
        hints.append({
            "field": "order_ref",
            "message": "Add your consignment or invoice number (for example CN-482913) "
                       "so we can find it straight away.",
        })
    if words < 12:
        hints.append({
            "field": "description",
            "message": "A sentence or two more about what happened helps us route it first time.",
        })
    if screened.suspected:
        hints.append({
            "field": "description",
            "message": "Part of this reads like instructions to our system. It will be treated "
                       "as part of your complaint, not followed.",
        })

    category: dict[str, str] | None = None
    if with_category and words >= 6:
        try:
            from python_validation.pipeline import run_validation
            from src.db.models import Category

            outcome = run_validation(db, text=text).outcome
            if outcome.category_code:
                row = db.execute(
                    select(Category).where(Category.code == outcome.category_code)
                ).scalars().first()
                category = {
                    "code": outcome.category_code,
                    "name": row.name if row else outcome.category_code,
                }
        except Exception as exc:  # noqa: BLE001 - a preview must never fail the form
            log.warning("preview_category_failed", error=str(exc)[:200])

    return {
        "entities": entities,
        "entity_counts": {k: len(v) for k, v in found.by_type.items()},
        "has_reference": any(found.by_type.get(t) for t in REFERENCE_TYPES),
        "words": words,
        "characters": len(description),
        "injection_suspected": screened.suspected,
        "likely_category": category,
        "hints": hints,
    }


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None
