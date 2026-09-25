"""
Nova, the chat receptionist: the third way to raise a complaint (FR iii).

The customer talks; Nova listens, asks for what is missing, and writes the
complaint up as a draft. **Nova never files anything.** The customer confirms
the draft with a button, and the draft then goes through exactly the intake a
web form uses -- both pipelines, the rules, the verification. The model's job
here is to take notes politely, not to make decisions.

Three limits are enforced in code, not only asked for in the prompt:

* **Scope.** Nova answers about RaftarXpress, its deliveries and complaints,
  and this service. The prompt asks the model to decline anything else, and
  the response schema forces it to label such turns ``off_topic``.
* **Other people's data.** Status comes from the database, looked up by the
  server among the signed-in customer's own complaints. The model is never
  given a complaint it did not hear about in this conversation, and anything
  it writes about status is replaced by what the server found.
* **Injection.** Every customer message is neutralised and scanned first, and
  the transcript is fenced as data, exactly as a complaint body is.

When no model answers, Nova still works in a reduced way: a reference like
CMP-000123 still returns its status, and everything else points to the form.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session

from genai_pipeline.providers import AllProvidersFailed, ProviderChain, build_chain
from genai_pipeline.providers.base import LLMRequest
from schemas.genai import json_schema_for
from security.injection_defense import DATA_NOT_INSTRUCTIONS_NOTICE, fence, scan
from src.core.logging import get_logger
from src.db.models import AppConfig, User

log = get_logger("genai.assistant")

MAX_TURNS = 14          # transcript turns sent to the model
MAX_MESSAGE_CHARS = 2000
REF_PATTERN = re.compile(r"\bCMP-\d{3,}\b", re.IGNORECASE)


class ComplaintDraft(BaseModel):
    title: str = Field(description="One line, in the customer's own words.", max_length=200)
    description: str = Field(description="Everything the customer said about the problem, in the first person, as they would write it.", max_length=4000)
    order_ref: str | None = Field(default=None, description="Consignment or order number, exactly as given.")
    product: str | None = Field(default=None, description="The service or item, if mentioned.")
    requested_resolution: str | None = Field(default=None, description="What the customer wants done, if they said.")


class AssistantTurn(BaseModel):
    reply: str = Field(description="What Nova says next. Warm, short, plain English.", max_length=1500)
    intent: Literal["chat", "collecting", "draft_complaint", "check_status", "off_topic"] = Field(
        description=(
            "chat: answering about the service. collecting: gathering complaint details. "
            "draft_complaint: the complaint is complete and summarised for the customer to confirm. "
            "check_status: the customer asked about an existing complaint. "
            "off_topic: the message is not about RaftarXpress, deliveries, complaints or this service."
        )
    )
    draft: ComplaintDraft | None = Field(default=None, description="Only with intent draft_complaint.")
    reference: str | None = Field(default=None, description="A complaint reference the customer gave, e.g. CMP-000123.")


ASSISTANT_SCHEMA = json_schema_for(AssistantTurn)

SYSTEM = """You are Nova, the friendly receptionist for {org} customer support, on the SupportNova website.

What you do, and only this:
1. Help customers raise a complaint about {org}: a late, lost or damaged parcel, a billing or COD issue, a refund, rider behaviour, their account, and similar.
2. Tell customers how the service works: how complaints are checked, how long they take, how to track one, how to add evidence, who handles it.
3. Help customers ask about the status of a complaint they already raised.

How to take a complaint:
- Be warm and brief. Ask ONE question at a time for what is missing.
- You need: what happened, and when; the consignment/order number if they have one; what they would like done. Do not insist on details they do not have.
- When you have enough, set intent to "draft_complaint", fill "draft" in the customer's own words (first person), and in "reply" summarise it and ask them to press "File this complaint" if it is right, or tell you what to change.
- Never say a complaint has been filed or give a reference number yourself. Filing happens only when the customer presses the button.
- Never promise a refund, compensation, date or outcome. Say the team will check it against company policy.

Status questions: set intent "check_status" and copy any reference (like CMP-000123) into "reference". Do not guess a status; the website fills it in.

Anything else -- general knowledge, maths, coding, other companies, opinions, jokes, personal advice -- is off topic. Set intent "off_topic" and reply kindly in one sentence that you can only help with {org} deliveries and complaints, and offer what you can do.

Company facts you may use: {facts}
If a customer asks for a fact that is not listed here, say where on the website they can see it. Never invent a number, time, price or policy.
{customer}

{notice}
Reply with JSON matching the schema. The conversation follows."""


@dataclass
class AssistantResult:
    reply: str
    intent: str
    draft: dict[str, Any] | None = None
    statuses: list[dict[str, Any]] = field(default_factory=list)
    needs_sign_in: bool = False
    degraded: bool = False


def converse(
    db: Session,
    messages: list[dict[str, str]],
    *,
    user: User | None,
    chain: ProviderChain | None = None,
    status_lookup: Any = None,
) -> AssistantResult:
    """One assistant turn for the transcript ``messages`` (oldest first)."""
    turns = [m for m in messages if m.get("role") in ("user", "assistant") and (m.get("content") or "").strip()][-MAX_TURNS:]
    if not turns or turns[-1]["role"] != "user":
        return AssistantResult(reply="Hello! I'm Nova. Tell me what went wrong and I'll help you raise a complaint.", intent="chat")

    # Every customer line is neutralised and scanned; the transcript is data.
    lines: list[str] = []
    for message in turns:
        text = message["content"][:MAX_MESSAGE_CHARS]
        if message["role"] == "user":
            text = scan(db, text).sanitised
            lines.append(f"Customer: {text}")
        else:
            lines.append(f"Nova: {text}")
    last_customer = turns[-1]["content"]

    chain = chain or ProviderChain(build_chain(), max_retries=1)
    turn: AssistantTurn | None = None
    if chain.available:
        request = LLMRequest(
            system=_system(db, user),
            prompt=fence("\n".join(lines)),
            temperature=0.3,
            max_output_tokens=900,
            json_schema=ASSISTANT_SCHEMA,
        )
        try:
            response = chain.generate(request)
            turn = AssistantTurn.model_validate_json(_json_only(response.text))
        except (AllProvidersFailed, ValidationError, ValueError) as exc:
            log.warning("assistant_turn_failed", error=type(exc).__name__)

    if turn is None:
        return _degraded(db, last_customer, user=user, status_lookup=status_lookup)

    result = AssistantResult(reply=turn.reply.strip(), intent=turn.intent)

    if turn.intent == "draft_complaint" and turn.draft is not None:
        draft = turn.draft.model_dump()
        if len((draft.get("description") or "").strip()) < 20:
            result.intent = "collecting"
        elif user is None:
            result.needs_sign_in = True
            result.draft = draft
            result.reply += "\n\nTo file it, please sign in or create a free account — it takes a minute, and I'll keep this draft."
        else:
            result.draft = draft

    if turn.intent == "check_status" or REF_PATTERN.search(last_customer):
        reference = turn.reference or _first_ref(last_customer)
        if user is None:
            result.needs_sign_in = True
            result.reply = "I can look that up once you sign in — status is only shown to the person who raised the complaint."
        elif status_lookup is not None:
            result.statuses = status_lookup(reference)
            result.intent = "check_status"
            # The model does not know the status; the server does. Say what was found.
            result.reply = _status_reply(result.statuses, reference)
    return result


# ── helpers ────────────────────────────────────────────────────
def _system(db: Session, user: User | None) -> str:
    row = db.get(AppConfig, "organisation")
    org = row.value if row is not None and isinstance(row.value, dict) else {}
    name = org.get("name") or "the company"
    facts = "; ".join(filter(None, [
        f"{name} is {org.get('industry', 'a courier company')}" if org.get("industry") else None,
        f"services: {', '.join(org.get('services', []))}" if org.get("services") else None,
        f"support hours: {org['support_hours']}" if org.get("support_hours") else None,
        _service_levels(db),
        "every complaint is read by an AI and then checked against the company's written rules; a person reviews any disagreement",
        "customers can track a complaint by its reference on the website and add photos or receipts there",
    ]))
    customer = (
        f"The customer is signed in as {user.full_name}. They can file a complaint and ask about their own complaints."
        if user is not None else
        "The customer is NOT signed in. You can help them describe the problem and answer questions; filing and status need them to sign in."
    )
    return SYSTEM.format(org=name, facts=facts, customer=customer, notice=DATA_NOT_INSTRUCTIONS_NOTICE)


def _service_levels(db: Session) -> str | None:
    """The default resolution targets by priority, read from the SLA table, so Nova never guesses."""
    from sqlalchemy import select

    from src.db.models import SLAPolicy

    rows = db.execute(
        select(SLAPolicy.priority_code, SLAPolicy.resolution_mins)
        .where(SLAPolicy.category_id.is_(None), SLAPolicy.is_active.is_(True))
        .order_by(SLAPolicy.priority_code)
    ).all()
    if not rows:
        return None
    words = {"P0": "urgent", "P1": "high priority", "P2": "normal", "P3": "low priority"}

    def span(mins: int) -> str:
        return f"{mins // 60} hours" if mins < 1440 else f"{mins // 1440} day{'s' if mins >= 2880 else ''}"

    return "target time to resolve, set by how urgent it is: " + ", ".join(
        f"{words.get(code, code)} within {span(mins)}" for code, mins in rows
    ) + " (some teams commit to faster)"


def _json_only(text: str) -> str:
    """Some models wrap JSON in prose or a code fence; keep the object."""
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no JSON object in the response")
    return text[start:end + 1]


def _first_ref(text: str) -> str | None:
    match = REF_PATTERN.search(text or "")
    return match.group(0).upper() if match else None


def _status_reply(statuses: list[dict[str, Any]], reference: str | None) -> str:
    if not statuses:
        if reference:
            return f"I couldn't find {reference.upper()} among your complaints. Check the number, or look under My complaints."
        return "You haven't raised a complaint yet. Tell me what went wrong and I'll help you raise one."
    if reference and len(statuses) == 1:
        s = statuses[0]
        return f"Here's the latest on {s['public_ref']}: {s['status_label'].lower()}." + (f" It's with the {s['team']} team." if s.get("team") else "")
    return "Here are your most recent complaints. Tap one to see every step."


def _degraded(db: Session, text: str, *, user: User | None, status_lookup: Any) -> AssistantResult:
    """No model answered. References still work; everything else goes to the form."""
    reference = _first_ref(text)
    if reference and user is not None and status_lookup is not None:
        statuses = status_lookup(reference)
        return AssistantResult(reply=_status_reply(statuses, reference), intent="check_status", statuses=statuses, degraded=True)
    return AssistantResult(
        reply=(
            "Sorry — I can't think clearly right now. You can still raise your complaint with the form "
            "(it takes two minutes), or give me a reference like CMP-000123 and I'll look it up."
        ),
        intent="chat",
        degraded=True,
    )


__all__ = ["ASSISTANT_SCHEMA", "AssistantResult", "AssistantTurn", "converse"]
