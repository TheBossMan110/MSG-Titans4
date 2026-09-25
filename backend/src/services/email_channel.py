"""
The email channel (FR iii): complaints received at the support mailbox,
answered automatically, and visible to staff and to the customer.

For each new email:

1. It is stored, whatever it is -- the record of what arrived is kept even
   when nothing else happens.
2. Automatic mail (out-of-office replies, bounces, newsletters) and our own
   messages are ignored, so two auto-responders can never answer each other
   forever.
3. A reply that names a reference (CMP-000123), or answers one of our own
   emails, is a **follow-up**: added to that complaint -- as the answer to an
   open question if one is waiting -- and answered with its status. Only when
   the complaint belongs to the address writing; anything else is told the
   reference was not found, which says nothing about whether it exists.
4. Anything else is triaged. A **complaint** goes through exactly the intake
   the web form uses, and the reply names the problem, the reference, the
   team and the target date. A **question** or anything **other** gets a short
   answer inviting details.

The reply is written by a model for that email (genai_pipeline/email_reply)
and checked for promises before sending; see that module for the limits.
"""

from __future__ import annotations

import email
import email.utils
import imaplib
import re
import smtplib
import threading
import time
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime
from email.message import EmailMessage as MimeMessage
from email.policy import default as default_policy
from html import unescape
from typing import Any

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from genai_pipeline import email_reply
from src.core.config import settings
from src.core.logging import get_logger
from src.db.models import AppConfig, ClarificationQuestion, Complaint, Customer, EmailMessage, User
from src.services.email_template import EmailContent, render_html, render_text

log = get_logger("services.email")

REF = re.compile(r"\bCMP-\d{3,}\b", re.IGNORECASE)
MAX_PER_POLL = 20

# What the status page shows about the mailbox.
state: dict[str, Any] = {"last_poll_at": None, "last_error": None, "last_count": 0}

# Set by a simulated email: everything happens except the reply leaving.
_dry_run: ContextVar[bool] = ContextVar("email_dry_run", default=False)


# ══════════════════════════════════════════════════════════════
# configuration
# ══════════════════════════════════════════════════════════════
def receiving_configured() -> bool:
    return bool(settings.email_address and settings.email_app_password)


def sending_method() -> str | None:
    """How replies go out: through Resend from a verified domain, or Gmail SMTP."""
    if settings.resend_api_key and settings.resend_from:
        return "resend"
    if settings.email_address and settings.email_app_password:
        return "smtp"
    return None


def status() -> dict[str, Any]:
    return {
        "address": settings.email_address or None,
        "receiving": receiving_configured(),
        "sending": sending_method(),
        "resend_key_present": bool(settings.resend_api_key),
        "resend_from": settings.resend_from or None,
        "poll_seconds": settings.email_poll_seconds,
        **state,
    }


# ══════════════════════════════════════════════════════════════
# parsing
# ══════════════════════════════════════════════════════════════
@dataclass
class Inbound:
    message_id: str | None
    in_reply_to: str | None
    references: str | None
    from_address: str
    from_name: str | None
    to_address: str
    subject: str
    text: str
    automatic: bool


def _strip_html(html: str) -> str:
    html = re.sub(r"(?is)<(script|style).*?</\1>", " ", html)
    html = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>", "\n", html)
    return unescape(re.sub(r"<[^>]+>", " ", html))


def _strip_quoted(text: str) -> str:
    """Drop the quoted earlier message a mail client appends to a reply."""
    lines = []
    for line in text.splitlines():
        if re.match(r"^\s*On .+wrote:\s*$", line) or line.strip().startswith("-----Original Message"):
            break
        if line.startswith(">"):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def parse(raw: bytes) -> Inbound:
    msg = email.message_from_bytes(raw, policy=default_policy)
    name, address = email.utils.parseaddr(str(msg.get("From", "")))
    _, to = email.utils.parseaddr(str(msg.get("To", "")))
    body = msg.get_body(preferencelist=("plain", "html"))
    text = ""
    if body is not None:
        text = body.get_content()
        if body.get_content_type() == "text/html":
            text = _strip_html(text)
    auto_submitted = str(msg.get("Auto-Submitted", "no")).lower()
    precedence = str(msg.get("Precedence", "")).lower()
    automatic = (
        auto_submitted not in ("", "no")
        or precedence in ("bulk", "junk", "list", "auto_reply")
        or bool(msg.get("List-Id") or msg.get("X-Autoreply") or msg.get("X-Autorespond"))
        or re.search(r"mailer-daemon|no-?reply|postmaster", address or "", re.I) is not None
    )
    return Inbound(
        message_id=(str(msg.get("Message-ID")) or None) if msg.get("Message-ID") else None,
        in_reply_to=str(msg.get("In-Reply-To")) if msg.get("In-Reply-To") else None,
        references=str(msg.get("References")) if msg.get("References") else None,
        from_address=(address or "").strip().lower(),
        from_name=(name or None),
        to_address=(to or settings.email_address or "").strip().lower(),
        subject=str(msg.get("Subject", "") or "").strip(),
        text=_strip_quoted(re.sub(r"\r\n?", "\n", text or "")).strip(),
        automatic=automatic,
    )


# ══════════════════════════════════════════════════════════════
# receiving
# ══════════════════════════════════════════════════════════════
def fetch_unseen() -> list[bytes]:
    """New messages from the inbox. Fetching marks them read, so each is handled once."""
    box = imaplib.IMAP4_SSL(settings.email_imap_host, settings.email_imap_port, timeout=30)
    try:
        box.login(settings.email_address, settings.email_app_password)
        box.select("INBOX")
        _, data = box.search(None, "UNSEEN")
        ids = (data[0] or b"").split()[:MAX_PER_POLL]
        messages = []
        for mid in ids:
            _, parts = box.fetch(mid, "(RFC822)")
            for part in parts:
                if isinstance(part, tuple):
                    messages.append(part[1])
        return messages
    finally:
        try:
            box.logout()
        except Exception:  # noqa: BLE001, S110 - closing is best effort
            pass


def poll_once() -> dict[str, int]:
    """Read the inbox and handle every new message, each in its own transaction."""
    from src.db.base import SessionLocal

    counts = {"fetched": 0, "handled": 0, "failed": 0}
    try:
        raws = fetch_unseen()
    except Exception as exc:  # noqa: BLE001
        state.update(last_poll_at=datetime.now(UTC).isoformat(), last_error=f"{type(exc).__name__}: {exc}"[:300])
        log.warning("email_poll_failed", error=state["last_error"])
        return counts
    counts["fetched"] = len(raws)
    for raw in raws:
        db = SessionLocal()
        try:
            handle(db, parse(raw))
            db.commit()
            counts["handled"] += 1
        except Exception as exc:  # noqa: BLE001 - one bad email must not stop the rest
            db.rollback()
            counts["failed"] += 1
            log.error("email_handle_failed", error=f"{type(exc).__name__}: {exc}", exc_info=True)
        finally:
            db.close()
    state.update(last_poll_at=datetime.now(UTC).isoformat(), last_error=None, last_count=counts["fetched"])
    return counts


def start_poller() -> threading.Thread | None:
    if not receiving_configured():
        log.info("email_poller_off", reason="EMAIL_ADDRESS / EMAIL_APP_PASSWORD not set")
        return None

    def loop() -> None:
        while True:
            poll_once()
            time.sleep(max(20, settings.email_poll_seconds))

    thread = threading.Thread(target=loop, name="email-poller", daemon=True)
    thread.start()
    return thread


# ══════════════════════════════════════════════════════════════
# handling one email
# ══════════════════════════════════════════════════════════════
def handle(db: Session, inbound: Inbound, *, dry_run: bool = False) -> EmailMessage:
    """Store, classify, act on and answer one inbound email."""
    token = _dry_run.set(dry_run)
    try:
        return _handle(db, inbound)
    finally:
        _dry_run.reset(token)


def _handle(db: Session, inbound: Inbound) -> EmailMessage:
    if inbound.message_id:
        existing = db.execute(
            select(EmailMessage).where(EmailMessage.message_id == inbound.message_id, EmailMessage.direction == "IN")
        ).scalars().first()
        if existing is not None:
            return existing

    row = EmailMessage(
        direction="IN", message_id=inbound.message_id, in_reply_to=inbound.in_reply_to,
        from_address=inbound.from_address, from_name=inbound.from_name, to_address=inbound.to_address,
        subject=inbound.subject[:998], body_text=inbound.text[:20000], status="RECEIVED",
    )
    db.add(row)
    # Committed before any model call: whatever fails later, the email itself
    # is on record and visible on the Email page.
    db.commit()

    own = {a.lower() for a in (settings.email_address, _address_of(settings.resend_from)) if a}
    if inbound.automatic or not inbound.from_address or inbound.from_address in own:
        row.status, row.intent, row.handled_at = "IGNORED", "OTHER", datetime.now(UTC)
        return row

    complaint = _referenced_complaint(db, inbound)
    if complaint is not None:
        return _follow_up(db, row, inbound, complaint)
    if REF.search(f"{inbound.subject} {inbound.text}"):
        # A reference that is not this sender's: the same answer as an unknown one.
        row.intent = "STATUS"
        content = EmailContent(
            greeting=_greeting(db, inbound),
            paragraphs=[
                "Thank you for your email. We could not find that complaint reference for this email address.",
                "If you raised it from another address, please write to us from that one. If this is a new problem, reply with what happened, your consignment number and what you would like us to do.",
            ],
        )
        return _finish(db, row, inbound, content, complaint=None)

    verdict = email_reply.triage(db, inbound.subject, inbound.text)
    if verdict.intent == "complaint":
        return _new_complaint(db, row, inbound, verdict.title)
    return _general(db, row, inbound, verdict.intent)


def _referenced_complaint(db: Session, inbound: Inbound) -> Complaint | None:
    """The complaint this email continues -- only if it belongs to the sender."""
    candidate: Complaint | None = None
    for ref in inbound.in_reply_to, inbound.references:
        if not ref:
            continue
        for mid in re.findall(r"<[^>]+>", ref) or [ref]:
            ours = db.execute(select(EmailMessage).where(EmailMessage.message_id == mid.strip(), EmailMessage.complaint_id.is_not(None))).scalars().first()
            if ours is not None:
                candidate = ours.complaint
                break
        if candidate is not None:
            break
    if candidate is None:
        match = REF.search(f"{inbound.subject} {inbound.text}")
        if match:
            candidate = db.execute(select(Complaint).where(Complaint.public_ref == match.group(0).upper())).scalars().first()
    if candidate is None:
        return None
    owner = candidate.customer.email.lower() if candidate.customer and candidate.customer.email else None
    submitter = db.get(User, candidate.submitted_by_user_id) if candidate.submitted_by_user_id else None
    if inbound.from_address in {owner, submitter.email.lower() if submitter else None}:
        return candidate
    return None


def _new_complaint(db: Session, row: EmailMessage, inbound: Inbound, title: str) -> EmailMessage:
    from complaint_processing.intake import IntakeRejected, deferring_escalation_notes, submit, write_deferred_notes

    row.intent = "COMPLAINT"
    user = _user_for(db, inbound.from_address)
    try:
        with deferring_escalation_notes() as pending:
            result = submit(
                db,
                title=(title or inbound.subject or inbound.text[:80]).strip()[:200],
                description=inbound.text,
                customer_email=inbound.from_address,
                customer_name=inbound.from_name or (user.full_name if user else None),
                channel="EMAIL",
                submitted_by_user_id=user.id if user else None,
            )
    except IntakeRejected:
        content = EmailContent(
            greeting=_greeting(db, inbound),
            paragraphs=["Thank you for writing to us. Your email did not include enough detail for us to open a complaint.",
                        "Please reply with what happened, when, your consignment or order number, and what you would like us to do."],
        )
        return _finish(db, row, inbound, content, complaint=None)
    db.flush()
    complaint = result.complaint
    row.complaint_id = complaint.id
    write_after = pending

    facts = _facts(db, complaint)
    fallback = [
        f"Thank you for contacting RaftarXpress. We have received your complaint and registered it as {complaint.public_ref}.",
        "It has been read and checked against our company policy" + (f", and it is now with our {facts['team']} team." if facts.get("team") else "."),
    ]
    if facts.get("questions"):
        fallback.append("To help us resolve it quickly, please reply to this email with: " + " ".join(facts["questions"]))
    composed = email_reply.compose(db, first_name=_first_name(db, inbound), subject=inbound.subject, body=inbound.text, facts=facts, fallback=fallback)

    content = EmailContent(
        greeting=composed.greeting,
        paragraphs=composed.paragraphs,
        reference=complaint.public_ref,
        facts=[(label, value) for label, value in (
            ("Category", facts.get("category")), ("Handled by", facts.get("team")),
            ("Target resolution", facts.get("target")), ("Status", facts.get("status")),
        ) if value],
        steps=[
            f"Our {facts['team']} team reviews it against company policy." if facts.get("team") else "A specialist reviews it against company policy.",
            "If we need anything else, we will ask — just reply to this email.",
            f"Follow every step online: sign in or create an account with {inbound.from_address}.",
        ],
        cta_label="Track your complaint",
        cta_url=f"{settings.public_app_url.rstrip('/')}/track/{complaint.public_ref}",
        preheader=f"We received your complaint — reference {complaint.public_ref}.",
    )
    out = _finish(db, row, inbound, content, complaint=complaint, subject=f"[{complaint.public_ref}] We received your complaint: {inbound.subject or 'your email'}", ai_written=composed.ai_written)
    db.commit()
    write_deferred_notes(write_after)
    return out


def _follow_up(db: Session, row: EmailMessage, inbound: Inbound, complaint: Complaint) -> EmailMessage:
    from complaint_processing.customer_actions import answer_clarification

    row.intent, row.complaint_id = "FOLLOW_UP", complaint.id
    open_questions = db.execute(
        select(ClarificationQuestion)
        .where(ClarificationQuestion.complaint_id == complaint.id, ClarificationQuestion.answered_at.is_(None))
        .order_by(ClarificationQuestion.ordinal)
    ).scalars().all()
    answered = False
    if open_questions and len(inbound.text.split()) >= 2:
        answer_clarification(db, complaint, open_questions[0].id, inbound.text[:2000], actor=_user_for(db, inbound.from_address))
        answered = True

    facts = _facts(db, complaint)
    lead = (
        f"Thank you — we have added your answer to complaint {complaint.public_ref} and passed it back to the team."
        if answered else f"Thank you for your email about complaint {complaint.public_ref}. We have added it to the complaint so the team sees it."
    )
    content = EmailContent(
        greeting=_greeting(db, inbound),
        paragraphs=[lead, f"Its current status is: {facts.get('status', 'with our team').lower()}." + (f" It is with our {facts['team']} team." if facts.get("team") else "")],
        reference=complaint.public_ref,
        facts=[(label, value) for label, value in (("Handled by", facts.get("team")), ("Target resolution", facts.get("target")), ("Status", facts.get("status"))) if value],
        cta_label="See every step",
        cta_url=f"{settings.public_app_url.rstrip('/')}/track/{complaint.public_ref}",
        preheader=f"Update on {complaint.public_ref}",
    )
    return _finish(db, row, inbound, content, complaint=complaint, subject=_re(inbound.subject, complaint.public_ref))


def _general(db: Session, row: EmailMessage, inbound: Inbound, intent: str) -> EmailMessage:
    row.intent = "OTHER" if intent == "other" else "QUESTION"
    hours = _support_hours(db)
    facts = {
        "how to raise a complaint": "reply to this email describing what happened, with the consignment number, or use the website form or the chat assistant",
        "how complaints are handled": "an AI reads each complaint, the company's written rules check every decision, and a person reviews any disagreement",
        "tracking": "every complaint gets a reference and can be followed on the website",
        "support hours": hours,
    }
    fallback = [
        "Thank you for writing to RaftarXpress customer support.",
        "If you would like us to look into a problem, reply to this email with what happened, your consignment or order number, and what you would like us to do. We will register it straight away and send you a reference.",
    ]
    composed = email_reply.compose(db, first_name=_first_name(db, inbound), subject=inbound.subject, body=inbound.text, facts=facts, fallback=fallback, general=True)
    content = EmailContent(
        greeting=composed.greeting, paragraphs=composed.paragraphs,
        cta_label="Visit SupportNova", cta_url=settings.public_app_url.rstrip("/"),
        preheader="Thanks for writing to RaftarXpress support.",
    )
    return _finish(db, row, inbound, content, complaint=None, ai_written=composed.ai_written)


# ══════════════════════════════════════════════════════════════
# sending
# ══════════════════════════════════════════════════════════════
def _finish(db: Session, row: EmailMessage, inbound: Inbound, content: EmailContent, *, complaint: Complaint | None, subject: str | None = None, ai_written: bool = False) -> EmailMessage:
    out = send(db, to=inbound.from_address, name=inbound.from_name, subject=subject or _re(inbound.subject), content=content, in_reply_to=inbound.message_id, complaint=complaint)
    row.status = "REPLIED" if out.status == "SENT" else ("PROCESSED" if out.status == "NOT_SENT" else "FAILED")
    row.error = out.error
    row.handled_at = datetime.now(UTC)
    log.info("email_handled", intent=row.intent, complaint=complaint.public_ref if complaint else None, reply=out.status, ai_written=ai_written)
    return row


def send(db: Session, *, to: str, name: str | None, subject: str, content: EmailContent, in_reply_to: str | None = None, complaint: Complaint | None = None) -> EmailMessage:
    """Render and send one reply, recording it whatever happens."""
    hours = _support_hours(db)
    html_body = render_html(content, support_hours=hours)
    text_body = render_text(content, support_hours=hours)
    sender = settings.resend_from if sending_method() == "resend" else settings.email_address
    domain = (_address_of(sender) or "supportnova.local").split("@")[-1]
    message_id = email.utils.make_msgid(domain=domain)
    row = EmailMessage(
        direction="OUT", message_id=message_id, in_reply_to=in_reply_to,
        from_address=_address_of(sender) or "", from_name=settings.email_sender_name, to_address=to,
        subject=subject[:998], body_text=text_body, body_html=html_body, intent="REPLY",
        complaint_id=complaint.id if complaint else None, status="NOT_SENT",
    )
    db.add(row)
    method = sending_method()
    if _dry_run.get():
        row.error = "Simulated email: the reply was written but not sent."
        db.flush()
        return row
    if method is None:
        row.error = "No way to send is configured (set EMAIL_APP_PASSWORD, or RESEND_FROM with RESEND_API_KEY)."
        db.flush()
        return row
    try:
        if method == "resend":
            _send_resend(to, subject, html_body, text_body, message_id, in_reply_to)
        else:
            _send_smtp(to, name, subject, html_body, text_body, message_id, in_reply_to)
        row.status = "SENT"
        row.handled_at = datetime.now(UTC)
    except Exception as exc:  # noqa: BLE001 - a failed send is recorded, not raised
        row.status, row.error = "FAILED", f"{type(exc).__name__}: {exc}"[:500]
        log.warning("email_send_failed", error=row.error)
    db.flush()
    return row


def _send_smtp(to: str, name: str | None, subject: str, html_body: str, text_body: str, message_id: str, in_reply_to: str | None) -> None:
    msg = MimeMessage()
    msg["From"] = email.utils.formataddr((settings.email_sender_name, settings.email_address))
    msg["To"] = email.utils.formataddr((name or "", to))
    msg["Subject"] = subject
    msg["Message-ID"] = message_id
    msg["Auto-Submitted"] = "auto-replied"   # tells other auto-responders not to answer
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = in_reply_to
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")
    with smtplib.SMTP(settings.email_smtp_host, settings.email_smtp_port, timeout=30) as smtp:
        smtp.starttls()
        smtp.login(settings.email_address, settings.email_app_password)
        smtp.send_message(msg)


def _send_resend(to: str, subject: str, html_body: str, text_body: str, message_id: str, in_reply_to: str | None) -> None:
    headers = {"Message-ID": message_id, "Auto-Submitted": "auto-replied"}
    if in_reply_to:
        headers.update({"In-Reply-To": in_reply_to, "References": in_reply_to})
    payload = {"from": settings.resend_from, "to": [to], "subject": subject, "html": html_body, "text": text_body, "headers": headers}
    if settings.email_address:
        payload["reply_to"] = settings.email_address
    response = httpx.post("https://api.resend.com/emails", json=payload, headers={"Authorization": f"Bearer {settings.resend_api_key}"}, timeout=30)
    if response.status_code >= 300:
        raise RuntimeError(f"Resend {response.status_code}: {response.text[:200]}")


# ══════════════════════════════════════════════════════════════
# small helpers
# ══════════════════════════════════════════════════════════════
def _address_of(value: str | None) -> str | None:
    if not value:
        return None
    return email.utils.parseaddr(value)[1].lower() or None


def _re(subject: str, ref: str | None = None) -> str:
    subject = subject or "your email"
    base = subject if subject.lower().startswith("re:") else f"Re: {subject}"
    return f"{base} [{ref}]" if ref and ref not in base else base


def _user_for(db: Session, address: str) -> User | None:
    return db.execute(select(User).where(func.lower(User.email) == address.lower(), User.role == "customer")).scalars().first()


def _first_name(db: Session, inbound: Inbound) -> str | None:
    user = _user_for(db, inbound.from_address)
    name = (user.full_name if user else None) or inbound.from_name
    if not name:
        customer = db.execute(select(Customer).where(func.lower(Customer.email) == inbound.from_address)).scalars().first()
        name = customer.display_name if customer else None
    first = (name or "").strip().split(" ")[0]
    return first if first and "@" not in first else None


def _greeting(db: Session, inbound: Inbound) -> str:
    first = _first_name(db, inbound)
    return f"Dear {first}," if first else "Hello,"


def _support_hours(db: Session) -> str | None:
    row = db.get(AppConfig, "organisation")
    return row.value.get("support_hours") if row is not None and isinstance(row.value, dict) else None


_STATUS_WORDS = {
    "NEW": "Received", "ANALYZING": "Being checked", "ANALYZED": "Checked against policy", "VALIDATED": "Checked against policy",
    "ASSIGNED": "With the team", "IN_PROGRESS": "With the team", "AWAITING_CUSTOMER": "Waiting for your reply",
    "ESCALATED": "With a specialist", "MANUAL_REVIEW": "With the team", "REOPENED": "With the team",
    "RESOLVED": "Resolved", "CLOSED": "Closed", "FAILED": "With the team",
}


def _facts(db: Session, complaint: Complaint) -> dict[str, Any]:
    """Only what the customer may see: no priority, escalation level or verification."""
    from src.db.models import SLAEvent

    due = db.execute(
        select(SLAEvent.due_at).where(SLAEvent.complaint_id == complaint.id, SLAEvent.event_type == "RESOLUTION").order_by(SLAEvent.due_at.desc())
    ).scalars().first()
    questions = [
        q.question for q in db.execute(
            select(ClarificationQuestion).where(ClarificationQuestion.complaint_id == complaint.id, ClarificationQuestion.answered_at.is_(None)).order_by(ClarificationQuestion.ordinal)
        ).scalars()
    ][:3]
    return {
        "reference": complaint.public_ref,
        "category": complaint.category.name if complaint.category else None,
        "team": complaint.department.name if complaint.department else None,
        "target": due.strftime("%d %b %Y, %H:%M") if due else None,
        "status": _STATUS_WORDS.get(complaint.status, "With the team"),
        "questions": questions,
        "specialist involved": "yes" if complaint.escalation_code and complaint.escalation_code != "NONE" else None,
    }
