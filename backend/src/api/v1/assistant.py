"""
The chat receptionist (FR iii, the chat channel). See genai_pipeline/assistant.py.

Only talks: the draft it produces is filed by the customer pressing a button,
which posts to ``/api/complaints/stream`` with channel ``CHAT`` -- the same
intake as the form.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select

from genai_pipeline import assistant
from src.core.deps import DbSession, OptionalUser
from src.core.ratelimit import limiter
from src.db.models import Complaint, Customer, SLAEvent, User

router = APIRouter(prefix="/assistant", tags=["Assistant"])


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=4000)


class ChatIn(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=40)


class DraftOut(BaseModel):
    title: str
    description: str
    order_ref: str | None = None
    product: str | None = None
    requested_resolution: str | None = None


class StatusBrief(BaseModel):
    public_ref: str
    title: str
    status_label: str
    team: str | None = None
    action_needed: bool = False
    submitted_at: str | None = None
    target_resolution_at: str | None = None


class ChatOut(BaseModel):
    reply: str
    intent: str
    draft: DraftOut | None = None
    statuses: list[StatusBrief] = []
    needs_sign_in: bool = False
    degraded: bool = False


# How a stored status reads to a customer. Internal states such as
# MANUAL_REVIEW or ESCALATED are deliberately phrased as "with the team".
_LABEL = {
    "NEW": "Received", "ANALYZING": "Being read", "ANALYZED": "Checked against policy",
    "VALIDATED": "Checked against policy", "ASSIGNED": "With the team", "IN_PROGRESS": "With the team",
    "AWAITING_CUSTOMER": "Waiting for you", "ESCALATED": "With a specialist", "MANUAL_REVIEW": "With the team",
    "REOPENED": "With the team", "RESOLVED": "Resolved", "CLOSED": "Closed", "FAILED": "With the team",
}


def _own(db: DbSession, user: User, reference: str | None) -> list[StatusBrief]:
    """The customer's own complaints: the same ownership rule as My complaints."""
    query = select(Complaint).where(
        or_(
            Complaint.submitted_by_user_id == user.id,
            Complaint.customer_id.in_(
                select(Customer.id).where(func.lower(Customer.email) == user.email.lower())
            ),
        )
    )
    if reference:
        query = query.where(Complaint.public_ref == reference.strip().upper())
    rows = db.execute(query.order_by(Complaint.created_at.desc()).limit(1 if reference else 3)).scalars().all()
    due = dict(db.execute(
        select(SLAEvent.complaint_id, func.max(SLAEvent.due_at))
        .where(SLAEvent.complaint_id.in_([c.id for c in rows]), SLAEvent.event_type == "RESOLUTION")
        .group_by(SLAEvent.complaint_id)
    ).all()) if rows else {}
    return [
        StatusBrief(
            public_ref=c.public_ref,
            title=c.title,
            status_label=_LABEL.get(c.status, "With the team"),
            team=c.department.name if c.department else None,
            action_needed=c.status == "AWAITING_CUSTOMER",
            submitted_at=c.created_at.isoformat() if c.created_at else None,
            target_resolution_at=due[c.id].isoformat() if due.get(c.id) else None,
        )
        for c in rows
    ]


@router.post("/chat", response_model=ChatOut, summary="One turn with Nova, the chat receptionist")
@limiter.limit("30/minute")
def chat(payload: ChatIn, request: Request, response: Response, db: DbSession, user: OptionalUser) -> ChatOut:
    # Staff use the register, not the receptionist; they chat as a visitor would.
    customer = user if user is not None and user.role == "customer" else None
    result = assistant.converse(
        db,
        [m.model_dump() for m in payload.messages],
        user=customer,
        status_lookup=(lambda ref: [s.model_dump() for s in _own(db, customer, ref)]) if customer else None,
    )
    return ChatOut(
        reply=result.reply,
        intent=result.intent,
        draft=DraftOut(**result.draft) if result.draft else None,
        statuses=[StatusBrief(**s) for s in result.statuses],
        needs_sign_in=result.needs_sign_in,
        degraded=result.degraded,
    )
