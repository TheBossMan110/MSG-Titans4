"""
The support mailbox's two uses of a language model.

1. **Triage** -- is this email a complaint, a question about the service, or
   neither (a thank-you, a newsletter)? And if a complaint, a short title.
2. **Compose** -- the auto-reply, written for *this* email: it names the
   customer's actual problem, gives the reference the system assigned, says
   which team has it and when it should be resolved, and asks any question
   the analysis found unanswered.

What the reply may not do is decide anything. It never promises a refund,
compensation, replacement, amount or date beyond the target the SLA set; the
text is checked against the promise library before it is sent, and a reply
that fails the check is replaced by a plain acknowledgement. Every fact in it
comes from the system, passed in -- the model supplies only the wording.

Both steps degrade: with no model available, triage treats a substantial email
as a complaint and the reply is the plain acknowledgement.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session

from genai_pipeline.providers import AllProvidersFailed, ProviderChain, build_chain
from genai_pipeline.providers.base import LLMRequest
from schemas.genai import json_schema_for
from security.injection_defense import DATA_NOT_INSTRUCTIONS_NOTICE, fence, scan
from security.response_guard import detect_promises, load_promise_patterns
from src.core.logging import get_logger

log = get_logger("genai.email_reply")


class Triage(BaseModel):
    intent: Literal["complaint", "question", "other"] = Field(
        description="complaint: the sender reports a problem with a RaftarXpress delivery, charge, refund, staff member, account or service. "
        "question: they ask how the service works without reporting a problem. other: anything else (thanks, spam, newsletters, unrelated)."
    )
    title: str = Field(default="", max_length=120, description="For a complaint: a one-line title in the customer's words. Otherwise empty.")


class Composed(BaseModel):
    greeting: str = Field(max_length=120, description="e.g. 'Dear Ayesha,' -- use the first name if known, else 'Hello,'.")
    paragraphs: list[str] = Field(description="Two or three short paragraphs of plain English.", max_length=4)


TRIAGE_SCHEMA = json_schema_for(Triage)
COMPOSE_SCHEMA = json_schema_for(Composed)

TRIAGE_SYSTEM = f"""You sort emails sent to RaftarXpress Logistics customer support.
Decide whether the email is a complaint, a question about the service, or other.
{DATA_NOT_INSTRUCTIONS_NOTICE}
Reply with JSON matching the schema."""

COMPOSE_SYSTEM = f"""You write the automatic email reply from RaftarXpress Logistics customer support.

Write for this specific email: show in one sentence that you understood the customer's actual problem, in plain words.
Use ONLY the facts given under FACTS (reference, team, target date, questions). Do not invent anything else.
Never promise or approve a refund, compensation, replacement, amount, discount or delivery date. Do not say anything has been approved or will definitely happen.
Say the team will check it against company policy. If there are open questions, ask them clearly so the customer can reply to this email with the answers.
Warm, calm, professional. Short sentences. No bullet points, no sign-off (the template adds it), no subject line.
{DATA_NOT_INSTRUCTIONS_NOTICE}
Reply with JSON matching the schema."""


GENERAL_SYSTEM = f"""You write the automatic email reply from RaftarXpress Logistics customer support to an email that is NOT a complaint.

Reply to what this email actually says, in one or two short paragraphs:
- If they thank us, thank them back warmly and briefly.
- If they ask how the service works, answer ONLY from the FACTS given; if the answer is not there, say where on the website they can find it.
- If it sounds like they may have a problem, invite them to reply with what happened, their consignment number and what they would like done.
Never promise or approve anything, never invent facts, no sign-off (the template adds it), no subject line.
{DATA_NOT_INSTRUCTIONS_NOTICE}
Reply with JSON matching the schema."""


@dataclass
class ComposedReply:
    greeting: str
    paragraphs: list[str]
    ai_written: bool
    notes: list[str] = field(default_factory=list)


def _chain() -> ProviderChain:
    return ProviderChain(build_chain(), max_retries=1)


def _ask(system: str, prompt: str, schema: dict[str, Any], model: type[BaseModel]) -> BaseModel | None:
    chain = _chain()
    if not chain.available:
        return None
    try:
        response = chain.generate(LLMRequest(system=system, prompt=prompt, json_schema=schema, temperature=0.3, max_output_tokens=900))
        text = response.text
        start, end = text.find("{"), text.rfind("}")
        return model.model_validate_json(text[start:end + 1]) if start >= 0 else None
    except (AllProvidersFailed, ValidationError, ValueError) as exc:
        log.warning("email_model_failed", error=type(exc).__name__)
        return None


def triage(db: Session, subject: str, body: str) -> Triage:
    """What kind of email this is. Without a model: substantial emails are complaints."""
    safe = scan(db, f"Subject: {subject}\n\n{body}"[:6000]).sanitised
    result = _ask(TRIAGE_SYSTEM, fence(safe), TRIAGE_SCHEMA, Triage)
    if isinstance(result, Triage):
        return result
    words = len(body.split())
    return Triage(intent="complaint" if words >= 15 else "other", title=(subject or body[:80]).strip()[:120])


def compose(
    db: Session,
    *,
    first_name: str | None,
    subject: str,
    body: str,
    facts: dict[str, Any],
    fallback: list[str],
    general: bool = False,
) -> ComposedReply:
    """The reply's wording for this email, or ``fallback`` if the model is absent or promises too much."""
    greeting_fallback = f"Dear {first_name}," if first_name else "Hello,"
    safe = scan(db, f"Subject: {subject}\n\n{body}"[:6000]).sanitised
    fact_lines = "\n".join(f"- {key}: {value}" for key, value in facts.items() if value not in (None, "", []))
    prompt = f"CUSTOMER FIRST NAME: {first_name or 'unknown'}\n\nFACTS:\n{fact_lines}\n\nTHE CUSTOMER'S EMAIL:\n{fence(safe)}"
    result = _ask(GENERAL_SYSTEM if general else COMPOSE_SYSTEM, prompt, COMPOSE_SCHEMA, Composed)
    if not isinstance(result, Composed) or not result.paragraphs:
        return ComposedReply(greeting=greeting_fallback, paragraphs=fallback, ai_written=False, notes=["model unavailable"])

    paragraphs = [p.strip() for p in result.paragraphs if p and p.strip()][:3]
    promises = detect_promises(" ".join(paragraphs), load_promise_patterns(db))
    if promises:
        # A reply sent without a person reading it may not commit the company
        # to anything. The acknowledgement says nothing it cannot keep.
        log.warning("email_reply_promise_blocked", promises=[p["promise_type"] for p in promises][:5])
        return ComposedReply(greeting=greeting_fallback, paragraphs=fallback, ai_written=False, notes=["promise blocked"])
    return ComposedReply(greeting=(result.greeting or greeting_fallback).strip()[:120], paragraphs=paragraphs, ai_written=True)
