"""
Resolution validation (FR xxv; SRS Step 28).

    "Python must verify whether mandatory resolution steps are present. It must
     also detect prohibited or unsupported actions."      — SRS Step 28

Runs over the stored ``resolution_steps`` rows once both pipelines have spoken,
and gives each one a status a human can act on:

* ``MISSING`` — the rules require it and nobody has confirmed it was done.
* ``REQUIRED_MET`` — an agent ticked it off. Only a person can put a step here.
* ``SUPPORTED`` — the model proposed it and it cites a policy that resolves.
* ``UNSUPPORTED`` — the model proposed it and nothing backs it.
* ``PROHIBITED`` — the model proposed something the rules forbid.

**A rule obligation is never satisfied automatically.** Whether "verify the
shipment status in the tracking system" actually happened is not readable from
generated text, and a system that inferred it would turn a safety checklist
into a rubber stamp. ``REQUIRED_MET`` is reachable only through
:func:`confirm`, which records who confirmed it.

**PROHIBITED is decided the same way the response guard decides it** — by
promise pattern against eligibility, not by matching the step's prose against
the prohibition's prose. That comparison was tried in the comparison engine and
produced false findings in both directions, because token overlap cannot tell
"advise the customer to stop using the product" from "advise them to repair
it". Sharing the guard's rule keeps one definition of what is forbidden.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.logging import get_logger
from src.db.enums import ResolutionStepSource, ResolutionStepStatus
from src.db.models import Chunk, ResolutionStep, User

log = get_logger("python_validation.resolution")


@dataclass(slots=True)
class StepVerdict:
    """One step and what became of it."""

    step_id: uuid.UUID
    ordinal: int
    text: str
    source: str
    status: str
    reason: str = ""
    promise_type: str | None = None

    @property
    def is_problem(self) -> bool:
        return self.status in (
            ResolutionStepStatus.PROHIBITED,
            ResolutionStepStatus.UNSUPPORTED,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "ordinal": self.ordinal,
            "text": self.text,
            "source": self.source,
            "status": self.status,
            "reason": self.reason,
            "promise_type": self.promise_type,
        }


@dataclass(slots=True)
class ResolutionReport:
    """Every step for one complaint, classified."""

    verdicts: list[StepVerdict] = field(default_factory=list)

    @property
    def required(self) -> list[StepVerdict]:
        return [v for v in self.verdicts if v.source == ResolutionStepSource.RULE_REQUIRED]

    @property
    def confirmed(self) -> list[StepVerdict]:
        return [v for v in self.required if v.status == ResolutionStepStatus.REQUIRED_MET]

    @property
    def prohibited(self) -> list[StepVerdict]:
        return [v for v in self.verdicts if v.status == ResolutionStepStatus.PROHIBITED]

    @property
    def unsupported(self) -> list[StepVerdict]:
        return [v for v in self.verdicts if v.status == ResolutionStepStatus.UNSUPPORTED]

    @property
    def complete(self) -> bool:
        """
        Whether every obligation has been confirmed and nothing is forbidden.

        A complaint with no obligations is complete by default — there was
        nothing to do.
        """
        return not self.prohibited and len(self.confirmed) == len(self.required)

    def coverage(self) -> tuple[int, int]:
        """``(confirmed, required)`` — the evidence, not a bare percentage."""
        return len(self.confirmed), len(self.required)

    def summary(self) -> dict[str, Any]:
        confirmed, required = self.coverage()
        return {
            "steps": len(self.verdicts),
            "required": required,
            "confirmed": confirmed,
            "coverage_pct": (
                round(confirmed / required * 100.0, 2) if required else None
            ),
            "prohibited": len(self.prohibited),
            "unsupported": len(self.unsupported),
            "complete": self.complete,
            "by_status": {
                status: sum(1 for v in self.verdicts if v.status == status)
                for status in sorted({v.status for v in self.verdicts})
            },
        }


# ══════════════════════════════════════════════════════════════
# classification
# ══════════════════════════════════════════════════════════════
# How the chunker joins a chunk key: ``DOC-003::2::c1`` is document, section,
# chunk (see document_processing/chunker.py).
_CHUNK_KEY_SEPARATOR = "::"

# What a model wraps a reference in when it copies one out of the prompt. The
# policy extracts are headed ``[DOC-003::2::c1] DOC-003 v2.1 ...``, so the
# brackets come back with the key more often than not.
_REFERENCE_WRAPPING = "[](){}<>\"'` "


def _chunk_exists(db: Session, chunk_key: str) -> bool:
    return db.execute(
        select(Chunk.id).where(Chunk.chunk_key == chunk_key).limit(1)
    ).first() is not None


def _cites_a_real_policy(db: Session, step: ResolutionStep) -> str | None:
    """
    The reference this step's citation resolves to, or ``None``.

    A policy reference that resolves is the difference between a step an agent
    can defend and one they cannot.

    The GenAI schema gives a step only ``policy_ref``, and the model fills it
    the way the prompt showed it references: with a chunk key
    (``DOC-003::2::c1``), often still in its brackets. Comparing that with
    ``chunks.doc_ref`` alone left every such step UNSUPPORTED -- 392 of them in
    the production data -- although the chunk it names exists. So a reference
    is tried, in order, as

    1. a chunk key that exists, exactly as written;
    2. the document named before the first ``::`` of a chunk-key-shaped
       reference, which is as traceable as naming that document outright;
    3. a document reference, with the step's section when it gives one.

    A reference that names no real chunk and no real document still resolves to
    nothing: an invented citation is never made to look supported.
    """
    if step.chunk_key:
        key = step.chunk_key.strip(_REFERENCE_WRAPPING)
        if key and _chunk_exists(db, key):
            return key

    reference = (step.policy_ref or "").strip(_REFERENCE_WRAPPING)
    if not reference:
        return None

    if _CHUNK_KEY_SEPARATOR in reference:
        if _chunk_exists(db, reference):
            return reference
        reference = reference.split(_CHUNK_KEY_SEPARATOR, 1)[0].strip(_REFERENCE_WRAPPING)
        if not reference:
            return None

    doc_ref = reference.upper()
    query = select(Chunk.id).where(Chunk.doc_ref == doc_ref)
    if step.section_ref:
        query = query.where(Chunk.section_ref == str(step.section_ref).strip())
    return doc_ref if db.execute(query.limit(1)).first() is not None else None


def classify(
    db: Session,
    complaint_id: uuid.UUID,
    *,
    eligibility: list[dict[str, Any]] | None = None,
    patterns: list[tuple[str, str, str | None]] | None = None,
) -> ResolutionReport:
    """
    Give every stored step a status.

    Rule-required steps keep whatever status they already have: only
    :func:`confirm` may move one to REQUIRED_MET, and re-running the classifier
    must not quietly undo an agent's confirmation.
    """
    from security.response_guard import (
        detect_promises,
        eligibility_index,
        is_permitted,
        load_promise_patterns,
    )

    patterns = patterns if patterns is not None else load_promise_patterns(db)
    index = eligibility_index(eligibility)

    steps = db.execute(
        select(ResolutionStep)
        .where(ResolutionStep.complaint_id == complaint_id)
        .order_by(ResolutionStep.ordinal)
    ).scalars().all()

    report = ResolutionReport()

    for step in steps:
        if step.source == ResolutionStepSource.RULE_REQUIRED:
            # Untouched. An agent's confirmation is the only thing that moves
            # this, and a re-run must not undo one.
            report.verdicts.append(
                StepVerdict(
                    step_id=step.id, ordinal=step.ordinal, text=step.text,
                    source=step.source, status=step.status,
                    # The explanation written by :func:`confirm` names who
                    # confirmed it and when. Overwriting it with a generic
                    # phrase would drop the only audit trail the checklist has.
                    reason=(
                        (step.explanation or "Confirmed by an agent.")
                        if step.status == ResolutionStepStatus.REQUIRED_MET
                        else "Required by the rule matrix; awaiting confirmation."
                    ),
                )
            )
            continue

        # ── a generated step ──
        # Negated phrases are not promises: "full refunds are not provided
        # once delivery is complete" states the policy rather than offering
        # the refund, and calling it PROHIBITED tells an agent not to say the
        # one thing they should.
        promises = detect_promises(step.text, patterns, exclude_negated=True)
        offending = next(
            (
                promise
                for promise in promises
                if not is_permitted(
                    index.get(str(promise.get("requires_eligibility") or "").upper())
                )
            ),
            None,
        )

        if offending is not None:
            status = ResolutionStepStatus.PROHIBITED
            reason = (
                f"Proposes a {offending['promise_type'].lower()} that no eligibility "
                "decision authorises. An agent must not carry this out."
            )
            promise_type = offending["promise_type"]
        elif (traced := _cites_a_real_policy(db, step)) is not None:
            status = ResolutionStepStatus.SUPPORTED
            reason = f"Traceable to {traced}."
            promise_type = None
        else:
            status = ResolutionStepStatus.UNSUPPORTED
            reason = (
                "Generated without a policy reference that resolves. It may still "
                "be sensible; it is simply not traceable, so an agent owns it."
            )
            promise_type = None

        step.status = status
        step.explanation = reason
        report.verdicts.append(
            StepVerdict(
                step_id=step.id, ordinal=step.ordinal, text=step.text,
                source=step.source, status=status, reason=reason,
                promise_type=promise_type,
            )
        )

    db.flush()

    if report.prohibited:
        log.warning(
            "prohibited_resolution_steps",
            complaint=str(complaint_id),
            steps=[v.ordinal for v in report.prohibited],
        )
    return report


# ══════════════════════════════════════════════════════════════
# confirmation
# ══════════════════════════════════════════════════════════════
def confirm(
    db: Session, step_id: uuid.UUID, user: User
) -> ResolutionStep:
    """
    Record that an agent carried out a required step.

    The only path to ``REQUIRED_MET``. Inferring it from generated text would
    make the checklist decorative, and the checklist is what stops a safety
    obligation being skipped.
    """
    step = db.get(ResolutionStep, step_id)
    if step is None:
        raise ValueError(f"No resolution step {step_id}.")

    if step.source != ResolutionStepSource.RULE_REQUIRED:
        raise ValueError(
            "Only a rule-required step can be confirmed. A generated "
            "suggestion is advice, not an obligation."
        )

    step.status = ResolutionStepStatus.REQUIRED_MET
    step.explanation = (
        f"Confirmed by {user.email} at {datetime.now(UTC).isoformat(timespec='seconds')}."
    )
    db.flush()

    log.info(
        "resolution_step_confirmed",
        step=str(step_id), complaint=str(step.complaint_id), by=user.email,
    )
    return step


def steps_for(db: Session, complaint_id: uuid.UUID) -> list[dict[str, Any]]:
    """The checklist as an agent sees it."""
    steps = db.execute(
        select(ResolutionStep)
        .where(ResolutionStep.complaint_id == complaint_id)
        .order_by(ResolutionStep.ordinal)
    ).scalars().all()

    return [
        {
            "id": str(step.id),
            "ordinal": step.ordinal,
            "text": step.text,
            "source": step.source,
            "status": step.status,
            # Only these can be ticked off; the rest are advice.
            "confirmable": step.source == ResolutionStepSource.RULE_REQUIRED
            and step.status != ResolutionStepStatus.REQUIRED_MET,
            "policy_ref": step.policy_ref,
            "explanation": step.explanation,
        }
        for step in steps
    ]
