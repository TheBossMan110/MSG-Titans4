"""
The email channel's API: the mailbox's state, the messages it has received
and sent, and a way to put a message through without Gmail -- for testing and
for a demonstration where nobody should be emailed for real.

Staff see every message. A customer sees only messages to or from their own
address, which is how their "Emails" page is filled.
"""

from __future__ import annotations

import email.utils
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, or_, select

from schemas.common import Page
from src.core.deps import CurrentUser, DbSession, require_role
from src.core.errors import NotFoundError
from src.db.enums import UserRole
from src.db.models import EmailMessage
from src.services import email_channel
from src.services.email_template import EmailContent, render_html

router = APIRouter(prefix="/email", tags=["Email"])

STAFF = (UserRole.AGENT, UserRole.REVIEWER, UserRole.MANAGER, UserRole.ADMIN, UserRole.EVALUATOR)
OPERATORS = (UserRole.MANAGER, UserRole.ADMIN, UserRole.EVALUATOR)


class EmailOut(BaseModel):
    id: uuid.UUID
    direction: str
    from_address: str
    from_name: str | None = None
    to_address: str
    subject: str
    preview: str
    intent: str | None = None
    status: str
    complaint_ref: str | None = None
    error: str | None = None
    created_at: str | None = None


class EmailDetail(EmailOut):
    body_text: str
    body_html: str | None = None
    thread: list[EmailOut] = []


class SimulateIn(BaseModel):
    from_address: EmailStr
    from_name: str | None = Field(default=None, max_length=120)
    subject: str = Field(default="", max_length=300)
    body: str = Field(min_length=1, max_length=20000)
    send_reply: bool = Field(default=False, description="Also send the reply for real, if sending is configured.")


def _out(row: EmailMessage) -> EmailOut:
    return EmailOut(
        id=row.id, direction=row.direction, from_address=row.from_address, from_name=row.from_name,
        to_address=row.to_address, subject=row.subject, preview=(row.body_text or "")[:220],
        intent=row.intent, status=row.status,
        complaint_ref=row.complaint.public_ref if row.complaint is not None else None,
        error=row.error, created_at=row.created_at.isoformat() if row.created_at else None,
    )


def _visible(user: Any):
    """Staff: everything. Customer: their own address, either direction."""
    query = select(EmailMessage)
    if user.role == UserRole.CUSTOMER:
        address = user.email.lower()
        query = query.where(or_(func.lower(EmailMessage.from_address) == address, func.lower(EmailMessage.to_address) == address))
    return query


@router.get("/status", dependencies=[Depends(require_role(*STAFF))], summary="Is the mailbox connected, and how are replies sent")
def status() -> dict[str, Any]:
    return email_channel.status()


@router.get("/messages", response_model=Page[EmailOut], summary="Emails received and sent")
def messages(
    db: DbSession,
    user: CurrentUser,
    direction: str | None = Query(None, pattern="^(IN|OUT)$"),
    intent: str | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(25, ge=1, le=100),
) -> Page[EmailOut]:
    query = _visible(user)
    if direction:
        query = query.where(EmailMessage.direction == direction)
    if intent:
        query = query.where(EmailMessage.intent == intent.upper())
    total = db.execute(select(func.count()).select_from(query.subquery())).scalar_one()
    rows = db.execute(query.order_by(EmailMessage.created_at.desc()).offset((page - 1) * size).limit(size)).scalars().all()
    return Page[EmailOut](items=[_out(r) for r in rows], total=total, page=page, size=size)


@router.get("/messages/{message_id}", response_model=EmailDetail, summary="One email, with the rest of its thread")
def message(message_id: uuid.UUID, db: DbSession, user: CurrentUser) -> EmailDetail:
    row = db.execute(_visible(user).where(EmailMessage.id == message_id)).scalars().first()
    if row is None:
        raise NotFoundError("No such email.")
    links = []
    if row.message_id:
        links.append(EmailMessage.in_reply_to == row.message_id)
    if row.in_reply_to:
        links.append(EmailMessage.message_id == row.in_reply_to)
    if row.complaint_id:
        links.append(EmailMessage.complaint_id == row.complaint_id)
    thread = []
    if links:
        thread = db.execute(
            select(EmailMessage).where(EmailMessage.id != row.id, or_(*links)).order_by(EmailMessage.created_at)
        ).scalars().all()
    if user.role == UserRole.CUSTOMER:
        mine = user.email.lower()
        thread = [t for t in thread if mine in (t.from_address.lower(), t.to_address.lower())]
    base = _out(row)
    return EmailDetail(**base.model_dump(), body_text=row.body_text, body_html=row.body_html, thread=[_out(t) for t in thread])


@router.post("/poll", dependencies=[Depends(require_role(*OPERATORS))], summary="Check the inbox now")
def poll() -> dict[str, Any]:
    if not email_channel.receiving_configured():
        return {"fetched": 0, "handled": 0, "failed": 0, "note": "The mailbox is not connected: set EMAIL_APP_PASSWORD."}
    return email_channel.poll_once()


@router.post("/simulate", response_model=EmailDetail, dependencies=[Depends(require_role(*OPERATORS))], summary="Put a pretend email through the whole pipeline")
def simulate(payload: SimulateIn, db: DbSession, user: CurrentUser) -> EmailDetail:
    inbound = email_channel.Inbound(
        message_id=email.utils.make_msgid(domain="simulated.supportnova"), in_reply_to=None, references=None,
        from_address=str(payload.from_address).lower(), from_name=payload.from_name,
        to_address=(email_channel.settings.email_address or "support@supportnova.local").lower(),
        subject=payload.subject.strip(), text=payload.body.strip(), automatic=False,
    )
    row = email_channel.handle(db, inbound, dry_run=not payload.send_reply)
    db.commit()
    return message(row.id, db, user)


@router.get("/preview", dependencies=[Depends(require_role(*STAFF))], summary="The reply template, filled with sample content")
def preview() -> dict[str, str]:
    content = EmailContent(
        greeting="Dear Ayesha,",
        paragraphs=[
            "Thank you for telling us that your parcel CN-77451209 was marked out for delivery three days ago and still has not reached you in Gulshan, Karachi. We understand how frustrating that is.",
            "We have registered your complaint and passed it to the team that handles deliveries. They will check the tracking and the rider's records against our delivery policy.",
        ],
        reference="CMP-000123",
        facts=[("Category", "Delivery"), ("Handled by", "Delivery & Logistics Operations"), ("Target resolution", "28 Sep 2026, 17:00"), ("Status", "Checked against policy")],
        steps=["Our Delivery & Logistics Operations team reviews it against company policy.", "If we need anything else, we will ask; just reply to this email.", "Follow every step online: sign in with this email address."],
        cta_label="Track your complaint", cta_url=email_channel.settings.public_app_url.rstrip("/") + "/track/CMP-000123",
        preheader="We received your complaint: reference CMP-000123.",
    )
    return {"html": render_html(content, support_hours="09:00-21:00 PKT, Mon-Sat")}
