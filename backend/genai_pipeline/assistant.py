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
* **Injection.** Every customer message is neutralised and screened first
  (``security/injection_defense`` and ``security/chat_firewall``). One that is
  an attack -- an override, a claimed role, a request for what Nova holds -- is
  answered with a fixed refusal **without any model being asked**, and recorded
  in ``injection_events``. Everything else reaches the model fenced as data.
* **Manipulation and disclosure.** What the model writes is untrusted output.
  ``security/manipulation_guard`` checks it in code before it is shown: one
  that approves, promises or guarantees an outcome, accepts a claimed role,
  describes what it holds or quotes its instructions, or names an email,
  phone number or reference the customer did not give, is replaced whole.
* **History.** The browser sends the conversation back each turn, so Nova's
  earlier lines are only believed when they carry the server's signature
  (src/api/v1/assistant.py). A forged "you are verified as admin" is dropped.

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
from security.chat_firewall import (
    DATA_EXFILTRATION,
    PRIVILEGE_CLAIM,
    PROMPT_EXTRACTION,
    inspect_message,
)
from security.injection_defense import (
    DATA_NOT_INSTRUCTIONS_NOTICE,
    ScanResult,
    fence,
    record_events,
    scan,
)
from security.manipulation_guard import (
    disclosure_reasons,
    manipulation_rules,
    policy_refusal,
    unsafe_reply,
)
from src.core import tenancy
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

{rules}
Refunds, compensation, replacements, approvals, guarantees and the rules themselves are always ON topic here, even when asked as a trick: never answer them with the off-topic line. Answer with the policy position above, then keep helping (intent "collecting").

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

    # Every customer line is neutralised and screened; the transcript is data.
    # A line that was an attack stays out of it, with whatever Nova said back,
    # so it cannot be built on in a later turn.
    lines: list[str] = []
    said: list[str] = []
    last_scan = None
    drop_reply = False
    for message in turns:
        text = message["content"][:MAX_MESSAGE_CHARS]
        if message["role"] == "user":
            last_scan = _screen(db, text)
            said.append(last_scan.sanitised)
            drop_reply = last_scan.suspected
            if not drop_reply:
                lines.append(f"Customer: {last_scan.sanitised}")
        elif drop_reply:
            drop_reply = False
        else:
            lines.append(f"Nova: {text}")
    last_customer = turns[-1]["content"]
    known = "\n".join(said)

    # The decision that matters, made in code and before any model is asked:
    # a message stopped here cannot be answered with anything it should not be.
    if last_scan is not None and last_scan.suspected:
        record_events(db, last_scan, source_type="CHAT")
        org = _org_name(db)
        log.warning("assistant_attack_stopped", labels=last_scan.labels)
        return AssistantResult(reply=_refusal_for(last_scan.labels, org), intent="collecting")

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
    org = _org_name(db)
    # What the model wrote is checked as untrusted output, and replaced whole:
    # a refusal stuck in front of a leak still shows the leak.
    problems = unsafe_reply(db, result.reply, known=known)
    if turn.draft is not None:
        problems += disclosure_reasons(f"{turn.draft.title}\n{turn.draft.description}", known=known)
    if problems:
        log.warning("assistant_reply_blocked", reasons=problems[:5])
        if "prompt disclosure" in problems:
            result.reply = _LEAK_REFUSAL + " " + _OFFER
        elif any(reason.startswith("disclosure") for reason in problems):
            result.reply = _NO_ACCESS
        else:
            # The customer asked an honest question and the model over-promised.
            # They did nothing wrong, so this is not worded as a refusal.
            result.reply = (
                f"I can't promise a time or an outcome here: the team checks every case against {org}'s "
                "written policy first, and nobody can override that in a chat. Tell me what happened "
                "and I'll help you raise a complaint so they can look into it."
            )
        result.intent = "collecting" if turn.intent == "draft_complaint" else turn.intent
        turn.draft = None
    elif turn.intent == "off_topic" and _OUTCOME_WORDS.search(last_customer):
        # Asking for a refund is never off topic; a brush-off would read as evasion.
        result.reply = policy_refusal(org) + " " + _OFFER
        result.intent = "collecting"

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
_OUTCOME_WORDS = re.compile(r"\b(refund|compensat\w*|replace\w*|approv\w*|guarantee\w*|polic(y|ies)|money back|exception)\b", re.IGNORECASE)
_LEAK_REFUSAL = (
    "I'm sorry, I can't share how I'm set up inside. I follow the company's written policy, "
    "and nobody can change that in a chat."
)
_OFFER = "What I can do is help you raise a complaint so the team can check it against that policy — tell me what happened."
_NO_ACCESS = (
    "I'm sorry, I can't share company, staff or other customers' information, and what anyone types in this "
    "chat can't give them extra access. I can only help with your own deliveries and complaints. "
    "Tell me what went wrong and I'll help you raise a complaint."
)


def _screen(db: Session, text: str) -> ScanResult:
    """The injection scan, plus the checks for who someone claims to be and what they are after."""
    result = scan(db, text)
    result.matches = [*result.matches, *inspect_message(result.sanitised)]
    return result


def _refusal_for(labels: list[str], org: str) -> str:
    if set(labels) & {PRIVILEGE_CLAIM, DATA_EXFILTRATION}:
        return _NO_ACCESS
    if set(labels) & {PROMPT_EXTRACTION, "PROMPT_LEAK"}:
        return _LEAK_REFUSAL + " " + _OFFER
    return policy_refusal(org) + " " + _OFFER


def _profile(db: Session) -> dict[str, Any]:
    """
    Who Nova works for in this conversation. Another company's customer is
    told about that company, never about the reference company whose profile
    the shared configuration holds.
    """
    bound = tenancy.current(db)
    if bound is not None and not tenancy.owns_template(bound):
        own = tenancy.info(bound) or {}
        return {"name": own.get("name"), "industry": own.get("industry")}
    row = db.get(AppConfig, "organisation")
    return row.value if row is not None and isinstance(row.value, dict) else {}


def _org_name(db: Session) -> str:
    return _profile(db).get("name") or "the company"


def _system(db: Session, user: User | None) -> str:
    org = _profile(db)
    name = org.get("name") or "the company"
    facts = "; ".join(filter(None, [
        f"{name} is {org.get('industry', 'a courier company')}" if org.get("industry") else None,
        f"services: {', '.join(org.get('services', []))}" if org.get("services") else None,
        f"support hours: {org['support_hours']}" if org.get("support_hours") else None,
        _service_levels(db),
        "every complaint is read by an AI and then checked against the company's written rules; a person reviews any disagreement",
        "customers can track a complaint by its reference on the website and add photos or receipts there",
    ]))
    # The display name stays out: the customer typed it, and these are the instructions.
    customer = (
        "The customer is signed in. They can file a complaint and ask about their own complaints."
        if user is not None else
        "The customer is NOT signed in. You can help them describe the problem and answer questions; filing and status need them to sign in."
    )
    return SYSTEM.format(org=name, facts=facts, customer=customer, rules=manipulation_rules(name), notice=DATA_NOT_INSTRUCTIONS_NOTICE)


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
