"""
Contradictory policy detection (SRS 1.8 #10).

    "Two policy documents that disagree must be detected, and the documented
     precedence order applied and stated."                    — SRS 1.8 #10

A complaint can end up resting on two policies that say different things: an
active refund policy allowing 14 days and a department SOP still saying 30, or
an FAQ that says a category is excluded when the policy says it is covered. The
system already picks one, because retrieval and precedence resolve it — what it
did not do was **say** that it picked one.

That silence is the whole problem. A system that quietly follows the higher
policy looks identical to a system that never noticed the lower one existed,
and the second is worth nothing to anybody auditing it.

**What counts as a disagreement is the claim checker's own definition.** Two
sentences, one from each document, that share most of their vocabulary — so
they are about the same thing — and then differ in exactly one of two ways:

* one negates what the other asserts, or
* they state different figures in the same unit.

Both tests come from :mod:`hallucination_checks.claim_support`, which asks the
same question of a generated claim against its source. Writing a second
definition here is how the two checks would drift apart, and a contradiction
detector that disagrees with the hallucination detector about what a
contradiction is helps nobody.

**Subject match is mutual and deliberately strict.** Containment is checked in
both directions, because a one-way test matches a short sentence against a long
one that merely contains its words. A false contradiction floods the trace view
with pairs an agent has to dismiss, and an agent who dismisses findings stops
reading them.

**Precedence decides, and the loser is marked, not deleted.** The overruled
reference stays on the complaint with ``conflict_with_ref`` naming what beat it
and why. Removing it would leave no evidence the conflict was ever resolved.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from hallucination_checks.claim_support import (
    containment,
    content_words,
    figures_by_unit,
    is_negated,
    split_claims,
)
from knowledge_base import versioning
from src.core.logging import get_logger
from src.db.models import AppConfig, Chunk, ComplaintPolicyRef, DocumentVersion

log = get_logger("hallucination_checks.policy_conflict")

# How much vocabulary two sentences must share, in *both* directions, before
# they count as being about the same subject. High on purpose: a false
# contradiction costs an agent a dismissal every time they open the complaint,
# and findings that are usually wrong stop being read.
DEFAULT_SUBJECT_FLOOR = 0.6

# A sentence shorter than this carries too few content words for containment to
# mean anything -- "This is not permitted." would match almost any negation.
MIN_SENTENCE_WORDS = 4

NEGATION = "NEGATION"
FIGURE = "FIGURE"

# The conflict explanation is appended to the citation's existing reason, which
# already says how the reference resolved and is still true. This separator is
# what makes the append idempotent: re-analysis rebuilds the tail rather than
# adding a second copy, so a complaint re-run four times does not end up with
# the same sentence four times.
# Split on the label itself, not on the separator around it. A row whose
# reason was empty the first time carries no separator, so splitting on the
# separator would fail to find the previous explanation and append a second
# copy beside it.
CONFLICT_MARKER = "Policy conflict: "


@dataclass(slots=True)
class Contradiction:
    """Two policy sentences that disagree, and which one governs."""

    kind: str
    winner_ref: str
    overruled_ref: str
    winning_tier: str | None
    overruled_tier: str | None
    winner_sentence: str
    overruled_sentence: str
    overlap: float
    detail: str = ""

    @property
    def reason(self) -> str:
        return (
            f"{self.overruled_ref} contradicts {self.winner_ref} on this point"
            + (f" ({self.detail})" if self.detail else "")
            + f". {self.winner_ref} governs: it sits in the "
            f"{self.winning_tier or 'higher'} precedence tier"
            + (
                f" and {self.overruled_ref} in {self.overruled_tier}"
                if self.overruled_tier and self.overruled_tier != self.winning_tier
                else ", by the documented precedence order"
            )
            + "."
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "winner_ref": self.winner_ref,
            "overruled_ref": self.overruled_ref,
            "winning_tier": self.winning_tier,
            "overruled_tier": self.overruled_tier,
            "winner_sentence": self.winner_sentence,
            "overruled_sentence": self.overruled_sentence,
            "overlap": round(self.overlap, 4),
            "detail": self.detail,
            "reason": self.reason,
        }


@dataclass(slots=True)
class ConflictReport:
    """Every contradiction found among one complaint's cited policies."""

    contradictions: list[Contradiction] = field(default_factory=list)
    documents_compared: int = 0
    pairs_compared: int = 0

    @property
    def detected(self) -> bool:
        return bool(self.contradictions)

    @property
    def overruled_refs(self) -> set[str]:
        return {c.overruled_ref for c in self.contradictions}

    def summary(self) -> dict[str, Any]:
        return {
            "detected": self.detected,
            "documents_compared": self.documents_compared,
            "pairs_compared": self.pairs_compared,
            "contradictions": [c.as_dict() for c in self.contradictions],
            # Honest null: with fewer than two documents there was nothing to
            # compare, which is not the same as comparing and finding nothing.
            "conflict_rate": (
                round(len(self.contradictions) / self.pairs_compared, 4)
                if self.pairs_compared
                else None
            ),
        }


def subject_floor(db: Session) -> float:
    """The configured overlap floor, so it can be retuned without a deploy."""
    row = db.get(AppConfig, "thresholds")
    if row and isinstance(row.value, dict):
        try:
            return float(row.value.get("policy_conflict_overlap", DEFAULT_SUBJECT_FLOOR))
        except (TypeError, ValueError):
            return DEFAULT_SUBJECT_FLOOR
    return DEFAULT_SUBJECT_FLOOR


def _same_subject(words_a: list[str], words_b: list[str], floor: float) -> float:
    """
    Mutual containment, or 0.

    Both directions must clear the floor. A one-way test matches a short
    sentence against a long one that merely happens to contain its words, and
    those are not about the same thing.
    """
    if len(words_a) < MIN_SENTENCE_WORDS or len(words_b) < MIN_SENTENCE_WORDS:
        return 0.0

    forward = containment(words_a, set(words_b))
    backward = containment(words_b, set(words_a))
    return min(forward, backward) if forward >= floor and backward >= floor else 0.0


def _disagreement(text_a: str, text_b: str) -> tuple[str, str] | None:
    """
    How these two sentences differ, if they do. Returns ``(kind, detail)``.

    Only the two differences that can be read off the text with confidence.
    Anything subtler is a judgement a person has to make, and asserting it
    here would produce findings nobody can check.
    """
    if is_negated(text_a) != is_negated(text_b):
        asserts, negates = (
            (text_b, text_a) if is_negated(text_a) else (text_a, text_b)
        )
        return (
            NEGATION,
            f'one asserts what the other negates: "{negates[:120]}"'
            f' against "{asserts[:120]}"',
        )

    figures_a = figures_by_unit(text_a)
    figures_b = figures_by_unit(text_b)
    for unit, values_a in figures_a.items():
        values_b = figures_b.get(unit)
        if values_b and not values_a & values_b:
            return (
                FIGURE,
                f"different {unit}: {'/'.join(sorted(values_a))} "
                f"against {'/'.join(sorted(values_b))}",
            )
    return None


def _document_texts(
    db: Session, by_ref: dict[str, ComplaintPolicyRef]
) -> dict[str, str]:
    """
    Everything each cited document says, keyed by doc_ref.

    The whole version rather than the cited chunk. A contradiction between two
    policies rarely sits in the two passages that happened to be retrieved:
    one document may state the rule in its body and the other in a schedule
    three sections away, and comparing only the retrieved chunks would miss
    exactly the plant this challenge is built around.
    """
    version_ids = {
        row.document_version_id
        for row in by_ref.values()
        if row.document_version_id is not None
    }
    if not version_ids:
        return {}

    by_version: dict[Any, list[tuple[int, str]]] = {}
    rows = db.execute(
        select(Chunk)
        .where(Chunk.document_version_id.in_(version_ids))
        .order_by(Chunk.ordinal)
    ).scalars()
    for chunk in rows:
        by_version.setdefault(chunk.document_version_id, []).append(
            (chunk.ordinal or 0, chunk.text or "")
        )

    texts: dict[str, str] = {}
    for ref, row in by_ref.items():
        pieces = by_version.get(row.document_version_id) or []
        texts[ref] = " ".join(text for _, text in sorted(pieces))
    return texts


def _document_facts(
    db: Session, version_ids: set[uuid.UUID]
) -> dict[str, tuple[str | None, Any, str | None]]:
    """``doc_ref -> (doc_type, effective_date, version_label)`` for precedence."""
    if not version_ids:
        return {}

    facts: dict[str, tuple[str | None, Any, str | None]] = {}
    rows = db.execute(
        select(DocumentVersion).where(DocumentVersion.id.in_(version_ids))
    ).scalars()
    for row in rows:
        doc = getattr(row, "document", None)
        facts[row.doc_ref] = (
            getattr(doc, "doc_type", None),
            row.effective_date,
            row.version,
        )
    return facts


def detect(db: Session, complaint_id: uuid.UUID) -> ConflictReport:
    """
    Compare every pair of policies this complaint rests on.

    Only citations that actually resolved are compared: an unresolvable
    reference is a hallucination, already recorded as one, and treating it as
    a contradicting policy would blame a real document for disagreeing with a
    document that does not exist.
    """
    report = ConflictReport()

    rows = db.execute(
        select(ComplaintPolicyRef).where(
            ComplaintPolicyRef.complaint_id == complaint_id,
            ComplaintPolicyRef.resolved.is_(True),
        )
    ).scalars().all()

    by_ref: dict[str, ComplaintPolicyRef] = {}
    for row in rows:
        by_ref.setdefault(row.doc_ref, row)

    report.documents_compared = len(by_ref)
    if len(by_ref) < 2:
        return report

    texts = _document_texts(db, by_ref)
    facts = _document_facts(
        db, {row.document_version_id for row in by_ref.values() if row.document_version_id}
    )
    floor = subject_floor(db)

    # Sentences once per document, not once per pair.
    sentences: dict[str, list[tuple[str, list[str]]]] = {}
    for ref in by_ref:
        text = texts.get(ref) or ""
        sentences[ref] = [
            (claim.text, content_words(claim.text)) for claim in split_claims(text)
        ]

    refs = sorted(by_ref)
    for index, ref_a in enumerate(refs):
        for ref_b in refs[index + 1:]:
            report.pairs_compared += 1
            found = _compare(
                db, ref_a, ref_b, sentences, facts, floor,
            )
            if found is not None:
                report.contradictions.append(found)

    if report.detected:
        log.info(
            "policy_conflict_detected",
            complaint=str(complaint_id),
            pairs=[(c.winner_ref, c.overruled_ref) for c in report.contradictions],
        )
    return report


def _compare(
    db: Session,
    ref_a: str,
    ref_b: str,
    sentences: dict[str, list[tuple[str, list[str]]]],
    facts: dict[str, tuple[str | None, Any, str | None]],
    floor: float,
) -> Contradiction | None:
    """The strongest disagreement between two documents, or None."""
    best: tuple[float, str, str, str, str] | None = None

    for text_a, words_a in sentences.get(ref_a, []):
        for text_b, words_b in sentences.get(ref_b, []):
            overlap = _same_subject(words_a, words_b, floor)
            if not overlap:
                continue
            difference = _disagreement(text_a, text_b)
            if difference is None:
                continue
            kind, detail = difference
            if best is None or overlap > best[0]:
                best = (overlap, kind, detail, text_a, text_b)

    if best is None:
        return None

    overlap, kind, detail, text_a, text_b = best

    type_a, date_a, _ = facts.get(ref_a, (None, None, None))
    type_b, date_b, _ = facts.get(ref_b, (None, None, None))
    winner, overruled = versioning.resolve_conflict(
        db, [(ref_a, type_a, date_a), (ref_b, type_b, date_b)]
    )
    if not overruled:
        return None

    loser = overruled[0]
    return Contradiction(
        kind=kind,
        winner_ref=winner,
        overruled_ref=loser,
        winning_tier=versioning.tier_for_document(type_a if winner == ref_a else type_b),
        overruled_tier=versioning.tier_for_document(type_a if loser == ref_a else type_b),
        winner_sentence=text_a if winner == ref_a else text_b,
        overruled_sentence=text_a if loser == ref_a else text_b,
        overlap=overlap,
        detail=detail,
    )


def persist(db: Session, complaint_id: uuid.UUID, report: ConflictReport) -> int:
    """
    Mark the overruled references, leaving them on the complaint.

    Deleting the loser would leave no evidence that a conflict was ever
    detected, which is exactly what the challenge is checking for. It stays,
    flagged, naming what beat it and why.
    """
    if not report.detected:
        return 0

    marked = 0
    for contradiction in report.contradictions:
        rows = db.execute(
            select(ComplaintPolicyRef).where(
                ComplaintPolicyRef.complaint_id == complaint_id,
                ComplaintPolicyRef.doc_ref == contradiction.overruled_ref,
            )
        ).scalars().all()
        for row in rows:
            row.conflict_with_ref = contradiction.winner_ref
            # The applicability reason already on the row explains how the
            # citation resolved and is still true, so the conflict is appended
            # to it -- but only ever once. Splitting on the marker first means
            # a re-run replaces the previous explanation instead of stacking
            # another copy beside it.
            base = (row.reason or "").split(CONFLICT_MARKER)[0].strip().rstrip("|").strip()
            row.reason = (
                f"{base} | {CONFLICT_MARKER}{contradiction.reason}"
                if base
                else f"{CONFLICT_MARKER}{contradiction.reason}"
            )
            marked += 1

    db.flush()
    log.info("policy_conflicts_recorded", complaint=str(complaint_id), rows=marked)
    return marked


def check(db: Session, complaint_id: uuid.UUID) -> ConflictReport:
    """Detect and record in one call -- what the pipeline uses."""
    report = detect(db, complaint_id)
    persist(db, complaint_id, report)
    return report


def conflicts_for(db: Session, complaint_id: uuid.UUID) -> list[dict[str, Any]]:
    """
    The recorded conflicts for one complaint, for the trace view.

    Read from the stored rows rather than recomputed, so what an agent sees is
    what was decided at the time and not what today's corpus would decide.
    """
    rows = db.execute(
        select(ComplaintPolicyRef).where(
            ComplaintPolicyRef.complaint_id == complaint_id,
            ComplaintPolicyRef.conflict_with_ref.is_not(None),
        )
    ).scalars().all()

    return [
        {
            "overruled_ref": row.doc_ref,
            "overruled_section": row.section_ref,
            "overruled_version": row.doc_version,
            "overruled_tier": row.precedence_tier,
            "governed_by_ref": row.conflict_with_ref,
            "reason": row.reason,
        }
        for row in rows
    ]
