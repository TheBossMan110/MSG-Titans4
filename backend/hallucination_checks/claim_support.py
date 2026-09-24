"""
Claim support scoring (FR xxxii; SRS Step 35).

    "The system must detect statements that are not supported by the retrieved
     policy text."                                         — SRS Step 35

Splits generated text into claims and asks, of each one, whether the cited
policy actually says it.

**What lexical overlap can and cannot tell you.** Overlap measures *grounding*
— whether a claim's vocabulary appears in the source it rests on. It reliably
catches a sentence invented from nothing, because invented text does not share
vocabulary with a document it never read. It cannot tell you a claim is *true*:
a sentence that reuses the source's words while inverting their meaning scores
highly and is completely wrong.

That limitation is why there are three checks, not one:

1. **Support** — content-word containment against the cited chunks. Catches
   the fabricated sentence.
2. **Numeric grounding** — two questions about every figure. Does the line
   the claim rests on state a *different* figure in the same unit? And does
   the figure appear anywhere in the cited text at all? This is the check that
   earns its keep: "refunds are available within 30 days" against a policy
   that says 14 reuses every word of the source, scores near-perfectly on
   overlap, and is caught here exactly.
3. **Negation mismatch** — the claim negates where its best-matching source
   span does not, or the reverse. "Refunds are not available for opened items"
   against "refunds are available for opened items" is the failure overlap is
   blindest to.

**Only policy claims are scored.** Greetings, apologies and first-person
process narration ("we have escalated your complaint", "a specialist will
contact you") are skipped. No policy document describes what this company is
currently doing, so such sentences always score near zero against one, and
reporting them would fill the review queue with findings for politeness. A
reviewer who learns the findings are noise stops reading them, which costs
more than the check gains.

The one exception is a figure with a unit — "within 14 days", "a 20% fee".
Those are checked whatever frames them, because a wrong number given to a
customer is the most damaging thing a reply can contain.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from src.core.logging import get_logger

log = get_logger("hallucination_checks.claims")

DEFAULT_SUPPORT_THRESHOLD = 0.35
MIN_CLAIM_WORDS = 4

# How closely a source sentence must match a claim before its polarity is
# treated as saying anything about the claim's. Below this the two are simply
# about different things.
SENTENCE_MATCH_FLOOR = 0.5

# Sentence boundary that survives "Rs. 42,500", "REF-POL-02" and "14 days."
_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")

# Words carrying no evidential weight. Overlap computed over content words
# only, or every claim would score highly on "the", "of" and "your".
_STOPWORDS = frozenset((
    "a", "an", "and", "are", "as", "at", "be", "been",
    "being", "but", "by", "can", "could", "did", "do", "does",
    "for", "from", "had", "has", "have", "he", "her", "his",
    "how", "i", "if", "in", "into", "is", "it", "its",
    "may", "me", "might", "must", "my", "no", "nor", "not",
    "of", "on", "once", "one", "only", "or", "other", "our",
    "ours", "out", "over", "own", "said", "same", "she", "should",
    "so", "some", "such", "than", "that", "the", "their", "them",
    "then", "there", "these", "they", "this", "those", "to", "too",
    "under", "until", "up", "us", "was", "we", "were", "what",
    "when", "where", "which", "while", "who", "whom", "why", "will",
    "with", "would", "you", "your", "yours",
))

# What makes a sentence a POLICY claim rather than a process statement.
#
# The distinction is the difference between a useful finding and noise. "Our
# refund window is 14 days" is a claim the policy can support or contradict.
# "We have escalated your complaint" is a statement about what this company is
# doing, which no policy document describes and which will therefore always
# score near zero against one.
#
# An earlier version accepted any sentence containing a business noun, and
# duly reported "We take reports of duplicate charges very seriously" as an
# unsupported claim. A reviewer who learns the findings are noise stops
# reading them, which costs more than the check gains.
_ASSERTIVE = re.compile(
    r"\b(?:polic(?:y|ies)|entitled?|entitlement|eligible|eligibility|eligib\w+"
    r"|refundable|non-refundable|warrant(?:y|ies)|cover(?:ed|s|age)"
    r"|exclude[ds]?|excluded|exempt\w*|permitted|prohibited"
    r"|terms\s+and\s+conditions|deadline|window"
    r"|allow(?:s|ed)|permit(?:s|ted)|require[ds]|must\s+be"
    r"|(?:polic(?:y|ies)|terms)\s+(?:states?|says?|requires?|allows?|permits?)"
    r")\b",
    re.IGNORECASE,
)

# A figure with a unit is always a commitment, whatever frames it: "within 14
# days", "a 20% fee", "Rs. 500". These are checked even when no policy term
# appears, because a number given to a customer is the thing most worth being
# right.
_COMMITTING_FIGURE = re.compile(
    r"\d[\d,]*(?:\.\d+)?\s*"
    r"(?:%|percent|business\s+days?|working\s+days?|days?|weeks?|months?|years?|hours?"
    # Loyalty value is a commitment too: "credited with 500 points" tells
    # the customer something has moved to them, and inventing it is as
    # damaging as inventing a refund window.
    r"|points?|credits?|vouchers?)"
    r"|(?:rs\.?|inr|aed|gbp|usd|[\u20b9\u00a3$])\s?\d",
    re.IGNORECASE,
)

# First-person narration of what this company is doing. Describes process, not
# policy, so no policy document can support or contradict it.
_PROCESS_NARRATION = re.compile(
    r"^\s*(?:"
    r"(?:we|our\s+\w+|i|a\s+specialist|a\s+member|the\s+team|your\s+complaint"
    r"|this\s+(?:complaint|matter|issue|case))\b[^.]*?"
    r"\b(?:have|has|are|is|will|am|was|were|been)\b"
    r")",
    re.IGNORECASE,
)

# Courtesies and process statements that assert nothing about policy.
_NON_ASSERTIVE = re.compile(
    r"^\s*(?:"
    r"thank(?:s| you)\b"
    r"|(?:we|i)\s+(?:are\s+)?(?:sincerely\s+)?(?:sorry|apolog\w+)"
    r"|(?:we|i)\s+understand\b"
    r"|(?:we|i)\s+appreciate\b"
    r"|(?:kind|best)\s+regards\b"
    r"|please\s+(?:accept|note|let)\b"
    r")",
    re.IGNORECASE,
)

_NEGATION = re.compile(
    r"\b(?:not|no|never|cannot|can't|won't|will not|unable|neither|nor|without"
    r"|ineligible|unavailable|excluded|denied|decline[ds]?)\b",
    re.IGNORECASE,
)

# Numbers that a claim commits the company to: durations, amounts, percentages.
_NUMERIC = re.compile(
    r"(?:(?:rs\.?|inr|aed|gbp|usd|[₹£$])\s?)?"
    r"\d[\d,]*(?:\.\d+)?\s*"
    r"(?:%|percent|business\s+days?|working\s+days?|days?|weeks?|months?|years?|hours?)?",
    re.IGNORECASE,
)

# Numbers that are references, not commitments: "REF-POL-02", "ZN-77321".
_REFERENCE_NUMBER = re.compile(r"[A-Z]{2,}-?[A-Z]*-?\d+", re.IGNORECASE)


@dataclass(slots=True)
class Claim:
    """One sentence of generated text, with where it sits in the whole."""

    text: str
    start: int
    end: int

    @property
    def words(self) -> list[str]:
        return content_words(self.text)

    @property
    def checkable(self) -> bool:
        """
        Whether this sentence asserts something a policy could support.

        A greeting is not unsupported; it is simply not a claim.
        """
        if len(self.text.split()) < MIN_CLAIM_WORDS:
            return False
        if _NON_ASSERTIVE.match(self.text):
            return False

        # A figure with a unit is always checked -- a wrong number is the most
        # damaging thing a reply can contain, and it outranks framing.
        if _COMMITTING_FIGURE.search(self.text):
            return True

        # Otherwise it must actually be about policy, and must not be this
        # company narrating its own process.
        if _PROCESS_NARRATION.match(self.text):
            return False
        return bool(_ASSERTIVE.search(self.text))


@dataclass(slots=True)
class ClaimVerdict:
    """One claim, its score, and what was wrong with it."""

    claim: Claim
    support_score: float = 0.0
    best_chunk_key: str | None = None
    supported: bool = True
    unsupported_numbers: list[str] = field(default_factory=list)
    negation_mismatch: bool = False
    supporting_sentence: str | None = None
    reason: str | None = None

    @property
    def problematic(self) -> bool:
        return (
            not self.supported
            or bool(self.unsupported_numbers)
            or self.negation_mismatch
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "text": self.claim.text,
            "span": [self.claim.start, self.claim.end],
            "support_score": round(self.support_score, 4),
            "best_chunk_key": self.best_chunk_key,
            "supported": self.supported,
            "unsupported_numbers": self.unsupported_numbers,
            "negation_mismatch": self.negation_mismatch,
            "supporting_sentence": self.supporting_sentence,
            "reason": self.reason,
        }


@dataclass(slots=True)
class ClaimReport:
    """Every claim in one piece of generated text."""

    verdicts: list[ClaimVerdict] = field(default_factory=list)
    skipped: int = 0
    threshold: float = DEFAULT_SUPPORT_THRESHOLD
    had_sources: bool = True

    @property
    def problems(self) -> list[ClaimVerdict]:
        return [v for v in self.verdicts if v.problematic]

    @property
    def grounding(self) -> tuple[int, int]:
        """``(supported, checked)`` — the evidence, not just a percentage."""
        return sum(1 for v in self.verdicts if not v.problematic), len(self.verdicts)

    def summary(self) -> dict[str, Any]:
        supported, checked = self.grounding
        return {
            "checked": checked,
            "skipped": self.skipped,
            "supported": supported,
            "problems": len(self.problems),
            "threshold": self.threshold,
            "had_sources": self.had_sources,
            "unsupported_numbers": sorted(
                {n for v in self.verdicts for n in v.unsupported_numbers}
            ),
        }


# ══════════════════════════════════════════════════════════════
# text handling
# ══════════════════════════════════════════════════════════════
def is_negated(text: str) -> bool:
    """
    Whether a sentence states the negative of its subject.

    Public because the policy-conflict detector asks the same question of two
    policy sentences that this module asks of a claim against its source. Two
    definitions of what counts as a negation is how the two checks drift apart.
    """
    return bool(_NEGATION.search(text or ""))


def content_words(text: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9]+", (text or "").lower())
    return [t for t in tokens if t not in _STOPWORDS and len(t) > 1]


def split_claims(text: str) -> list[Claim]:
    """Split generated text into sentences, keeping each one's span."""
    claims: list[Claim] = []
    if not text or not text.strip():
        return claims

    cursor = 0
    for piece in _SENTENCE.split(text):
        stripped = piece.strip()
        if not stripped:
            cursor += len(piece)
            continue
        start = text.find(stripped, cursor)
        if start < 0:
            start = cursor
        claims.append(Claim(text=stripped, start=start, end=start + len(stripped)))
        cursor = start + len(stripped)
    return claims


def containment(claim_words: list[str], source_words: set[str]) -> float:
    """
    The fraction of a claim's content words that appear in the source.

    Containment rather than Jaccard: a two-sentence claim drawn from a
    2,000-word policy chunk should score high, and Jaccard would punish it for
    the chunk's length. The question is "is this claim's vocabulary present in
    the source", not "are these two texts similar".
    """
    if not claim_words:
        return 0.0
    hits = sum(1 for word in claim_words if word in source_words)
    return hits / len(claim_words)


def numbers_in(text: str) -> list[str]:
    """
    Durations, amounts and percentages a claim commits to.

    Reference numbers are excluded: "REF-POL-02" is a citation, not a promise
    of two of anything, and flagging it would make every cited reply look
    numerically ungrounded.
    """
    cleaned = _REFERENCE_NUMBER.sub(" ", text or "")
    found: list[str] = []
    for match in _NUMERIC.finditer(cleaned):
        token = match.group(0).strip().rstrip(".,")
        if token and any(character.isdigit() for character in token):
            found.append(_normalise_number(token))
    return found


def _normalise_number(token: str) -> str:
    """Compare "14 days", "14  Days" and "14days" as one thing."""
    return re.sub(r"\s+", " ", token.lower()).strip()


def numeric_values(tokens: list[str]) -> set[str]:
    """The bare numerals, for checking a value appears at all."""
    values: set[str] = set()
    for token in tokens:
        for number in re.findall(r"\d[\d,]*(?:\.\d+)?", token):
            values.add(number.replace(",", ""))
    return values


def unit_of(token: str) -> str | None:
    """
    The unit a figure commits to: days, weeks, percent, money.

    Business days and calendar days are folded together on purpose. A reply
    saying "3 days" against a policy stating "3 business days" is a wording
    difference for a reviewer to judge, not a contradiction worth a finding of
    its own.
    """
    lowered = token.lower()
    if "%" in lowered or "percent" in lowered:
        return "percent"
    for unit in ("day", "week", "month", "year", "hour"):
        if unit in lowered:
            return unit
    if re.search(r"rs\.?|inr|aed|gbp|usd|[\u20b9\u00a3$]", lowered):
        return "money"
    return None


def figures_by_unit(text: str) -> dict[str, set[str]]:
    """Every figure in a piece of text, grouped by what it measures."""
    grouped: dict[str, set[str]] = {}
    for token in numbers_in(text):
        unit = unit_of(token)
        if unit is None:
            continue
        grouped.setdefault(unit, set()).update(numeric_values([token]))
    return grouped


# ══════════════════════════════════════════════════════════════
# scoring
# ══════════════════════════════════════════════════════════════
def best_sentence(claim: Claim, source_text: str) -> str | None:
    """
    The single line of the source that best matches this claim.

    Negation must be compared against *this*, never against the whole chunk.
    A policy chunk of any length contains an exclusion somewhere, so a
    chunk-level comparison reports a mismatch for almost every claim and
    misses the inverted ones — it flagged "refunds are available within 14
    days" as contradicting a passage that says exactly that, and passed
    "refunds are NOT available" because the chunk happened to contain the word
    "excluded" further down.
    """
    if not source_text:
        return None

    claim_words = claim.words
    if not claim_words:
        return None

    best, best_score = None, 0.0
    for sentence in split_claims(source_text):
        score = containment(claim_words, set(content_words(sentence.text)))
        if score > best_score:
            best, best_score = sentence.text, score

    # Below the floor, the "closest" sentence is not about the same subject and
    # its polarity says nothing about the claim's.
    return best if best_score >= SENTENCE_MATCH_FLOOR else None


def score_claim(
    claim: Claim, sources: dict[str, str], *, threshold: float
) -> ClaimVerdict:
    """Score one claim against every cited chunk, keeping the best match."""
    verdict = ClaimVerdict(claim=claim)

    if not sources:
        verdict.supported = False
        verdict.reason = (
            "The reply makes a policy claim but cites no policy text, so nothing "
            "supports it."
        )
        return verdict

    claim_words = claim.words
    best_key, best_score, best_text = None, 0.0, ""
    for key, text in sources.items():
        score = containment(claim_words, set(content_words(text)))
        if score > best_score:
            best_key, best_score, best_text = key, score, text

    verdict.support_score = best_score
    verdict.best_chunk_key = best_key
    verdict.supported = best_score >= threshold

    if not verdict.supported:
        verdict.reason = (
            f"Only {best_score:.0%} of this statement's terms appear in the cited "
            f"policy (threshold {threshold:.0%}). It may not be supported by the "
            "source it rests on."
        )
        return verdict

    # Supported on vocabulary. Now the two checks vocabulary cannot make.
    supporting = best_sentence(claim, best_text)
    verdict.supporting_sentence = supporting

    claim_numbers = numbers_in(claim.text)
    if claim_numbers:
        # (a) Contradiction. When the line the claim rests on states a figure
        #     in the same unit, the claim must state the same figure. This is
        #     the check that catches "within 30 days" against a policy saying
        #     14: the wording is identical, the overlap score is near-perfect,
        #     and the number is simply wrong.
        contradicted: list[str] = []
        if supporting:
            source_by_unit = figures_by_unit(supporting)
            for token in claim_numbers:
                unit = unit_of(token)
                stated = source_by_unit.get(unit or "")
                if stated and not numeric_values([token]) <= stated:
                    contradicted.append(
                        f"{token} (the cited line states {'/'.join(sorted(stated))})"
                    )

        # (b) Absence. A figure appearing nowhere in anything the reply cited
        #     is ungrounded even if no single line contradicts it. Checked
        #     across EVERY cited source, not just the best-matching chunk: a
        #     reply citing a whole policy may take its figure from a table
        #     several sections from the sentence it paraphrases, and narrowing
        #     this to one chunk reported those as ungrounded.
        source_values: set[str] = set()
        for text in sources.values():
            source_values |= numeric_values(numbers_in(text))
        missing = [
            token for token in claim_numbers
            if not numeric_values([token]) <= source_values
        ]

        if contradicted:
            verdict.unsupported_numbers = contradicted
            verdict.reason = (
                f"The cited policy does not support {', '.join(contradicted)}. "
                "A figure given to a customer becomes a commitment."
            )
        elif missing:
            verdict.unsupported_numbers = missing
            verdict.reason = (
                f"The cited policy does not contain {', '.join(missing)}. A figure "
                "given to a customer becomes a commitment, so a number the source "
                "does not state must not appear in the reply."
            )

    if supporting:
        claim_negated = bool(_NEGATION.search(claim.text))
        source_negated = bool(_NEGATION.search(supporting))
        if claim_negated != source_negated:
            verdict.negation_mismatch = True
            verdict.reason = (
                "This statement "
                + ("negates" if claim_negated else "asserts")
                + " what the closest line of the cited policy "
                + ("does not" if claim_negated else "negates")
                + f': "{supporting[:160]}". Overlap alone cannot tell these apart, '
                "so a human should read both."
            )

    return verdict


def check_claims(
    text: str,
    sources: dict[str, str],
    *,
    threshold: float = DEFAULT_SUPPORT_THRESHOLD,
) -> ClaimReport:
    """
    Score every checkable claim in a piece of generated text.

    ``sources`` maps ``chunk_key`` to the chunk's text — the passages the reply
    actually cited, not everything retrieved. A claim is grounded in what it
    cited or it is not grounded.
    """
    report = ClaimReport(threshold=threshold, had_sources=bool(sources))

    for claim in split_claims(text):
        if not claim.checkable:
            report.skipped += 1
            continue
        report.verdicts.append(score_claim(claim, sources, threshold=threshold))

    if report.problems:
        log.warning(
            "unsupported_claims",
            count=len(report.problems),
            checked=len(report.verdicts),
            numbers=[n for v in report.problems for n in v.unsupported_numbers],
        )
    return report
