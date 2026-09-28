"""
The response guard (FR xxxiv; SRS Steps 34-35; SRS 1.8 #9).

    "Python must detect promises the policy does not support — refunds,
     compensation, timelines, exceptions — and prevent them from reaching the
     customer."                                            — SRS Step 34

The last thing between a generated reply and a customer. It runs **after** the
comparison engine and reads only the reconciled record, so what it enforces is
policy, not the model's opinion of policy.

**Every check here is deterministic.** No similarity thresholds, no embeddings,
no second model. That is not austerity, it is the requirement: a guard that
sometimes fails to notice a promised refund is not a guard, and one that
sometimes invents a violation trains agents to click past it.

The core rule is a single sentence:

    A promise of type T is UNSUPPORTED unless Pipeline 2 independently derived
    an eligibility decision of type T with outcome ELIGIBLE.

Which makes the SRS 1.8 #9 trap fall out for free. A complaint where refund
eligibility is ``REQUIRES_VERIFICATION`` is exactly the case where a model
writes "your full refund has been approved" — and the guard blocks it, because
``REQUIRES_VERIFICATION`` is not ``ELIGIBLE``.

Four further checks:

* **Citations** — every policy reference in the reply must resolve, and its
  document version must be ACTIVE. A real but superseded policy is flagged
  separately (SRS 1.8 #10); citing a withdrawn refund window is a different
  failure from inventing one.
* **Uncited policy claims** — a reply that asserts what "our policy" says
  without a citation, when ``require_citation_for_policy_claims`` is set.
* **Timelines** — a committed date is a promise no eligibility rule can
  authorise, so it requires a citation to an active policy that carries one.
* **Claim support** — every factual statement is scored against the text it
  cites, and every figure in it must appear in that text. The promise check
  asks whether a commitment was authorised; this asks whether a statement is
  grounded, and a reply free of promises can still tell a customer the refund
  window is 30 days when the policy says 14. See
  :mod:`hallucination_checks.claim_support`.

**What the guard deliberately does not do** is match the rule matrix's prose
obligations against the reply's prose. That approach was tried in the
comparison engine and produced false findings in both directions, because
token overlap cannot distinguish "advise the customer to stop using the
product" from "advise the customer to repair it". Required actions are
surfaced to the agent as a mandatory checklist instead, which is both honest
about what a machine can verify and how a real support desk works.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from complaint_processing.entities import load_entity_patterns, parse_amount
from hallucination_checks.citation_validator import source_texts
from hallucination_checks.claim_support import DEFAULT_SUPPORT_THRESHOLD, check_claims
from src.core.logging import get_logger
from src.db.enums import (
    DocStatus,
    EligibilityOutcome,
    GuardStatus,
    ResponseFlagType,
    Severity,
)
from src.db.models import Chunk, PromisePattern, ResponseFlag
from src.core.refcache import reference_data

log = get_logger("security.response_guard")

MAX_MATCH_SAMPLE = 200

# A citation as it appears in generated prose: DOC-012, REF-POL-02 s2,
# DEL-POL-04 section 5.2.
#
# Two segments or three, because a corpus may name its documents either way.
# Requiring three made every DOC-nnn citation invisible at once -- to the
# guard, to hallucination detection and to the Traceability Challenge.
#
# What stops it swallowing an order reference is the DIGIT COUNT, not the
# shape: a document is numbered in ones to thousands (DOC-012, REF-POL-02) and
# a consignment in millions (CN-9923190, FWD-1234567). The trailing lookahead
# rejects both a longer number and a further segment, so MER-1234-WH stays a
# merchant reference instead of becoming a citation to "MER-1234".
_CITATION_IN_TEXT = re.compile(
    r"\b(?P<doc>[A-Z]{2,6}(?:-[A-Z]{2,6})?-\d{1,4})(?![\d-])"
    r"(?:\s*(?:section|sec\.?|s)\s*(?P<section>\d+(?:\.\d+){0,3}))?",
    re.IGNORECASE,
)

# A promise inside a conditional frame is a different act from an outright
# one. "If our investigation confirms the duplicate, a refund will be
# processed" does not tell the customer the refund is approved; "your refund
# has been approved" does. The hedged form is still surfaced for a human, but
# blocking it would make the guard fire on correctly-written replies -- and a
# guard that fires on correct output is one agents learn to click past.
_CONDITIONAL_FRAME = re.compile(
    r"\b(?:if|once|when|after|should|subject\s+to|provided\s+that|pending"
    r"|upon)\b[^.]{0,120}$",
    re.IGNORECASE,
)


def _is_hedged(text: str, start: int) -> bool:
    """Whether a promise sits inside a conditional clause."""
    sentence_start = max(
        text.rfind(".", 0, start), text.rfind("!", 0, start), text.rfind("?", 0, start)
    )
    lead_in = text[sentence_start + 1 : start]
    return bool(_CONDITIONAL_FRAME.search(lead_in))


# A promise pattern matches a phrase, not a commitment. "Full refunds are not
# provided once delivery is complete" contains "full refund" and says the
# opposite of promising one; production step CMP-000292 was marked PROHIBITED
# for exactly that sentence. A negation only counts when it sits in the same
# clause as the phrase AND governs the act of granting it, which is why every
# test below asks for a granting word as well as a "not":
#
#   "we cannot offer a full refund"           -- negated, before the phrase
#   "full refunds are not provided"           -- negated, after the phrase
#   "your full refund won't be delayed"       -- still a promise
#   "don't worry, your full refund is issued" -- still a promise (new clause)
#
# Erring the other way would be the expensive mistake: a negation the check
# wrongly believes in lets a real commitment through, so anything it cannot
# read with confidence stays a promise.
_CLAUSE_BREAK = re.compile(
    r"[.;:!?,()\[\]\n]|\s[-–—]+\s|[–—]"
    r"|\b(?:and|but|or|however|although|though|whereas|while|unless|except|yet"
    r"|because|since|so|if|when|whenever|once|after|before|until|as|that|which"
    r"|who|where)\b",
    re.IGNORECASE,
)
_WORD = re.compile(r"[A-Za-z]+(?:['’][A-Za-z]+)?")

# Words that negate what follows them.
_NEGATORS = frozenset(
    {"not", "never", "cannot", "cant", "no", "nor", "neither", "unable", "none"}
)
# Words that negate and carry the granting sense in the same breath.
_SELF_NEGATING = frozenset({"ineligible", "unavailable"})
# What turns a negator into an idiom that negates nothing about the promise:
# "not only a full refund", "don't worry", "no later than", "at no cost".
_IDIOM_AFTER_NEGATOR = frozenset(
    {"only", "worry", "hesitate", "later", "doubt", "question", "questions",
     "problem", "cost", "charge", "extra"}
)
_AUXILIARIES = frozenset(
    {"is", "are", "was", "were", "will", "would", "shall", "should", "can",
     "could", "may", "might", "must", "has", "have", "had", "does", "do", "did"}
)
_FILLERS = frozenset({"be", "been", "being", "longer", "currently", "normally", "usually"})
# The act a promise is made of: offering, issuing, granting, being eligible.
_GRANTS = re.compile(
    r"^(?:offer|provid|issu|process|grant|giv|approv|arrang|guarant|promis|mak"
    r"|made|pay|paid|credit|authori[sz]|honou?r|accept|consider|refund|replac"
    r"|waiv|compensat|eligib|entitl|qualif|possib|availab|abl|permit|allow|appl)",
    re.IGNORECASE,
)

# How far either side of the phrase a governing negation may sit.
_NEGATION_WINDOW = 8


def _words(fragment: str) -> list[str]:
    return [w.lower().replace("’", "'") for w in _WORD.findall(fragment)]


def _is_negator(words: list[str], index: int) -> bool:
    word = words[index]
    if word not in _NEGATORS and not word.endswith("n't"):
        return False
    following = words[index + 1] if index + 1 < len(words) else ""
    if following in _IDIOM_AFTER_NEGATOR:
        return False
    # "not to worry" reassures; it negates nothing about the promise.
    return not (following == "to" and words[index + 2 : index + 3] == ["worry"])


def _negated_before(lead: list[str]) -> bool:
    """
    "cannot offer a", "not eligible for a", "no" -- a negation leading into it.

    Directly in front of the phrase ("we cannot guarantee a refund", "no full
    refund") the negator governs it outright. Further back it must reach the
    phrase through a granting word, so "don't worry about your full refund"
    is still read as the promise it is.
    """
    for index in range(len(lead)):
        if lead[index] in _SELF_NEGATING:
            return True
        if not _is_negator(lead, index):
            continue
        between = lead[index + 1 :]
        if len(between) <= 1 or any(_GRANTS.match(word) for word in between):
            return True
    return False


def _negated_after(trail: list[str]) -> bool:
    """
    "are not provided", "cannot be issued", "is no longer offered".

    Only a negated *granting* predicate counts. "Your full refund won't be
    delayed" negates the delay, not the refund, and remains a promise.
    """
    for index, word in enumerate(trail):
        previous = trail[index - 1] if index else ""
        if word in _SELF_NEGATING and previous in _AUXILIARIES:
            return True

        negates = word == "cannot" or word.endswith("n't") or (
            word in ("not", "never", "no") and previous in _AUXILIARIES
        )
        if not negates:
            continue
        predicate = [w for w in trail[index + 1 :] if w not in _FILLERS and not w.endswith("ly")]
        if any(_GRANTS.match(w) for w in predicate[:3]):
            return True
    return False


def is_negated(text: str, start: int, end: int) -> bool:
    """
    Whether the phrase at ``text[start:end]`` is negated within its clause.

    Public because the resolution validator asks it of a proposed step and the
    guard of a reply; one reading of "not" is what keeps the two agreeing on
    what counts as a promise.
    """
    if not text or start < 0 or end > len(text) or start >= end:
        return False

    clause_start = 0
    for match in _CLAUSE_BREAK.finditer(text, 0, start):
        clause_start = match.end()
    following = _CLAUSE_BREAK.search(text, end)
    clause_end = following.start() if following else len(text)

    lead = _words(text[clause_start:start])[-_NEGATION_WINDOW:]
    trail = _words(text[end:clause_end])[:_NEGATION_WINDOW]
    return _negated_before(lead) or _negated_after(trail)


# Claims about policy that a citation must back up.
_POLICY_CLAIM = re.compile(
    r"\b(?:"
    r"(?:our|the|company|store|current)\s+policy"
    r"|as\s+per\s+(?:our|the)\s+polic(?:y|ies)"
    r"|polic(?:y|ies)\s+(?:states?|says?|requires?|allows?|permits?)"
    r"|under\s+(?:our|the)\s+(?:terms|policy)"
    r"|terms\s+and\s+conditions"
    r")\b",
    re.IGNORECASE,
)


@dataclass(slots=True)
class GuardFinding:
    """One violation, with the span that produced it."""

    flag_type: str
    severity: str
    explanation: str
    matched_text: str | None = None
    span_start: int | None = None
    span_end: int | None = None
    blocking_rule_ref: str | None = None
    promise_type: str | None = None

    @property
    def blocking(self) -> bool:
        """Whether this finding must stop the reply reaching a customer."""
        return self.severity in (Severity.CRITICAL, Severity.HIGH)

    def as_dict(self) -> dict[str, Any]:
        return {
            "flag_type": self.flag_type,
            "severity": self.severity,
            "explanation": self.explanation,
            "matched_text": self.matched_text,
            "span": [self.span_start, self.span_end],
            "blocking_rule_ref": self.blocking_rule_ref,
            "promise_type": self.promise_type,
        }

    def to_row(self, response_id: Any) -> ResponseFlag:
        return ResponseFlag(
            response_id=response_id,
            flag_type=self.flag_type,
            severity=self.severity,
            matched_text=(self.matched_text or "")[:1024] or None,
            span_start=self.span_start,
            span_end=self.span_end,
            explanation=self.explanation,
            blocking_rule_ref=self.blocking_rule_ref,
            resolved=False,
        )


@dataclass(slots=True)
class GuardReport:
    """The verdict on one draft reply."""

    findings: list[GuardFinding] = field(default_factory=list)
    checks_run: int = 0
    checks_passed: int = 0
    citations_found: list[dict[str, Any]] = field(default_factory=list)
    promises_found: list[dict[str, Any]] = field(default_factory=list)
    required_action_checklist: list[dict[str, Any]] = field(default_factory=list)
    claims: list[dict[str, Any]] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return not self.findings

    @property
    def blocking_findings(self) -> list[GuardFinding]:
        return [finding for finding in self.findings if finding.blocking]

    @property
    def status(self) -> str:
        if not self.findings:
            return GuardStatus.CLEAN
        if self.blocking_findings:
            return GuardStatus.BLOCKED
        return GuardStatus.FLAGGED

    @property
    def compliance(self) -> tuple[int, int]:
        """
        ``(passed, run)`` — the evidence behind the compliance score.

        Counted as checks rather than as actions, because a check is something
        this module actually performed and can point at. Returning a ratio with
        no denominator when nothing was checkable is the honest outcome; see
        :func:`comparison_engine.decision.compliance_score`.
        """
        return self.checks_passed, self.checks_run

    def summary(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "findings": len(self.findings),
            "blocking": len(self.blocking_findings),
            "checks": {"passed": self.checks_passed, "run": self.checks_run},
            "promises": [p["promise_type"] for p in self.promises_found],
            "citations": len(self.citations_found),
            "claims_checked": len(self.claims),
            "flag_types": sorted({f.flag_type for f in self.findings}),
        }


# ══════════════════════════════════════════════════════════════
# patterns
# ══════════════════════════════════════════════════════════════
@lru_cache(maxsize=256)
def _compile(pattern: str) -> re.Pattern[str] | None:
    try:
        return re.compile(pattern, re.IGNORECASE)
    except re.error as exc:
        log.warning("invalid_promise_pattern", pattern=pattern[:70], error=str(exc))
        return None


@reference_data("promise_patterns")
def load_promise_patterns(db: Session) -> list[tuple[str, str, str | None]]:
    """Active promise patterns as ``(pattern, promise_type, requires_eligibility)``."""
    rows = db.execute(
        select(PromisePattern).where(PromisePattern.is_active.is_(True))
    ).scalars().all()
    return [(row.pattern, row.promise_type, row.requires_action) for row in rows]


def detect_promises(
    text: str,
    patterns: list[tuple[str, str, str | None]],
    *,
    exclude_negated: bool = False,
) -> list[dict[str, Any]]:
    """
    Every promise-shaped phrase in the reply, with its span.

    ``exclude_negated`` drops a phrase its own clause denies ("full refunds
    are not provided"), see :func:`is_negated`. The reply guard and the
    resolution validator ask for that; the chat manipulation guard does not,
    because it replaces any reply that so much as discusses an outcome.
    """
    found: list[dict[str, Any]] = []
    if not text:
        return found

    for pattern, promise_type, requires in patterns:
        compiled = _compile(pattern)
        if compiled is None:
            continue
        for match in compiled.finditer(text):
            if exclude_negated and is_negated(text, match.start(), match.end()):
                continue
            found.append(
                {
                    "promise_type": promise_type,
                    "requires_eligibility": requires,
                    "pattern": pattern,
                    "text": match.group(0)[:MAX_MATCH_SAMPLE],
                    "start": match.start(),
                    "end": match.end(),
                }
            )
    return found


# ══════════════════════════════════════════════════════════════
# eligibility
# ══════════════════════════════════════════════════════════════
def eligibility_index(eligibility: list[dict[str, Any]] | None) -> dict[str, dict[str, Any]]:
    """Pipeline 2's eligibility findings, keyed by type."""
    index: dict[str, dict[str, Any]] = {}
    for finding in eligibility or []:
        key = str(finding.get("eligibility_type", "")).upper()
        if key:
            index[key] = finding
    return index


def is_permitted(finding: dict[str, Any] | None) -> bool:
    """
    Only an explicit ELIGIBLE authorises a promise.

    Public because the resolution validator asks the same question of a
    proposed step that the guard asks of a generated sentence. Two copies of
    this rule would be two places for "what counts as approved" to drift.

    CONDITIONAL and REQUIRES_VERIFICATION deliberately do not. A condition the
    agent has not yet checked is not a basis for telling a customer the answer
    is yes, and that gap is the whole of SRS 1.8 #9.
    """
    if not finding:
        return False
    if finding.get("requires_human_approval"):
        return False
    return str(finding.get("python_outcome", "")).upper() == EligibilityOutcome.ELIGIBLE


def exceeds_ceiling(
    text: str,
    promise: dict[str, Any],
    finding: dict[str, Any] | None,
    *,
    amount_pattern: str,
) -> tuple[Decimal, Decimal] | None:
    """
    Whether the reply names an amount above what the eligibility rule allows.

    Returns ``(stated, ceiling)`` on a breach, else ``None``.

    This is the expensive failure the outcome check cannot catch: eligibility
    says yes, so the promise reads as authorised, and only the *number* is
    wrong. "Your compensation of Rs. 5,000 is approved" against a rule that
    caps compensation at 500 is a commitment the company is held to, made in a
    sentence that passes every other gate.

    Scoped to the sentence carrying the promise -- see :func:`_sentence_around`.
    """
    ceiling = finding.get("max_amount") if finding else None
    if ceiling is None:
        return None

    try:
        limit = Decimal(str(ceiling))
    except (InvalidOperation, ValueError):
        return None

    compiled = _compile(amount_pattern)
    if compiled is None:
        return None

    sentence = _sentence_around(text, promise.get("start", 0))
    stated = [
        parsed
        for match in compiled.finditer(sentence)
        if (parsed := parse_amount(match.group(0))) is not None
    ]
    if not stated:
        return None

    highest = max(stated)
    return (highest, limit) if highest > limit else None


# A sentence boundary is terminal punctuation followed by whitespace and the
# start of a new sentence. The lookahead is the whole point: a naive ". " split
# cuts "Rs. 5,000" in half, and the amount then disappears from the sentence
# being checked -- the ceiling silently passes every reply that quotes rupees.
# That is the same abbreviation trap that once turned "Rs. 42,500" into 0.42500.
_SENTENCE_BREAK = re.compile(r"""[.!?]\s+(?=["'(\[]?[A-Z])|\n""")


def _sentence_around(text: str, position: int) -> str:
    """
    The sentence containing ``position``.

    Deliberately narrow. A reply that quotes the customer's disputed amount in
    one paragraph and approves a smaller goodwill credit in another is correct,
    and comparing the largest number anywhere in the reply against the ceiling
    would flag it. An agent who gets flagged for correct replies stops reading
    the flags.
    """
    if not text:
        return ""

    start, end = 0, len(text)
    for match in _SENTENCE_BREAK.finditer(text):
        if match.end() <= position:
            start = match.end()
        else:
            end = match.start() + 1
            break
    return text[start:end]


def _why_not(promise_type: str, finding: dict[str, Any] | None) -> str:
    if finding is None:
        return (
            f"The reply promises a {promise_type.lower()}, but the rule engine "
            f"derived no {promise_type.lower()} eligibility for this complaint. "
            "Nothing authorises this commitment."
        )
    outcome = str(finding.get("python_outcome", "UNKNOWN")).upper()
    rule_ref = finding.get("rule_ref") or "a rule"
    if finding.get("requires_human_approval"):
        return (
            f"The reply promises a {promise_type.lower()}, but {rule_ref} requires "
            "human approval before it can be offered."
        )
    conditions = finding.get("conditions_evaluated") or []
    detail = f" Outstanding: {'; '.join(conditions)}." if conditions else ""
    return (
        f"The reply promises a {promise_type.lower()}, but {rule_ref} derived "
        f"{outcome}, not ELIGIBLE.{detail}"
    )


# ══════════════════════════════════════════════════════════════
# citations
# ══════════════════════════════════════════════════════════════
def extract_citations(text: str) -> list[dict[str, Any]]:
    """Policy references that appear in the reply text itself."""
    found: list[dict[str, Any]] = []
    for match in _CITATION_IN_TEXT.finditer(text or ""):
        found.append(
            {
                "doc_ref": match.group("doc").upper(),
                "section_ref": match.group("section"),
                "text": match.group(0),
                "start": match.start(),
                "end": match.end(),
            }
        )
    return found


def check_citations(
    db: Session, text: str, declared: list[dict[str, Any]] | None = None
) -> tuple[list[GuardFinding], list[dict[str, Any]], int, int]:
    """
    Resolve every citation the reply makes.

    Both the references written into the prose and the ones declared in the
    structured output are checked: a reply can name a policy in a sentence
    without listing it, and an unresolvable reference is a hallucination
    whichever field it arrived in.
    """
    findings: list[GuardFinding] = []
    run = passed = 0

    candidates = extract_citations(text)
    for reference in declared or []:
        candidates.append(
            {
                "doc_ref": str(reference.get("doc_ref", "")).upper(),
                "section_ref": reference.get("section_ref"),
                "chunk_key": reference.get("chunk_key"),
                "text": reference.get("doc_ref"),
                "start": None,
                "end": None,
            }
        )

    resolved: list[dict[str, Any]] = []
    seen: set[tuple[str, str | None]] = set()

    for candidate in candidates:
        key = (candidate["doc_ref"], candidate.get("section_ref"))
        if not candidate["doc_ref"] or key in seen:
            continue
        seen.add(key)
        run += 1

        chunk = _resolve(db, candidate)
        if chunk is None:
            findings.append(
                GuardFinding(
                    flag_type=ResponseFlagType.INVALID_CITATION,
                    severity=Severity.HIGH,
                    explanation=(
                        f"The reply cites {candidate['doc_ref']}, which does not exist "
                        "in the knowledge base. A customer cannot be given a policy "
                        "reference that cannot be produced."
                    ),
                    matched_text=str(candidate.get("text") or candidate["doc_ref"]),
                    span_start=candidate.get("start"),
                    span_end=candidate.get("end"),
                )
            )
            resolved.append({**candidate, "resolvable": False, "active": False})
            continue

        status = getattr(chunk.document_version, "status", None)
        active = status == DocStatus.ACTIVE
        resolved.append(
            {
                **candidate,
                "resolvable": True,
                "active": active,
                "version_status": status,
                "chunk_key": chunk.chunk_key,
                # Needed to widen claim scoring to the whole document when the
                # reply cited one without naming a section.
                "document_version_id": chunk.document_version_id,
                # `section_ref` stays as the reply WROTE it, not as it
                # resolved. Scope for claim scoring depends on how precisely
                # the reply cited, and overwriting it with the matched chunk's
                # section makes every document-level citation look
                # section-level -- which narrowed scoring to whichever chunk
                # happened to come first.
                "resolved_section_ref": chunk.section_ref,
            }
        )

        if active:
            passed += 1
            continue

        findings.append(
            GuardFinding(
                flag_type=ResponseFlagType.OUTDATED_POLICY,
                severity=Severity.HIGH,
                explanation=(
                    f"The reply cites {candidate['doc_ref']}, which resolves to a "
                    f"{status} version. Quoting a withdrawn policy to a customer "
                    "commits the company to terms it has replaced."
                ),
                matched_text=str(candidate.get("text") or candidate["doc_ref"]),
                span_start=candidate.get("start"),
                span_end=candidate.get("end"),
            )
        )

    return findings, resolved, run, passed


def _resolve(db: Session, candidate: dict[str, Any]) -> Chunk | None:
    from knowledge_base import retrieval

    return retrieval.resolve_citation(
        db,
        chunk_key=candidate.get("chunk_key"),
        doc_ref=candidate.get("doc_ref"),
        section_ref=candidate.get("section_ref"),
    )


# ══════════════════════════════════════════════════════════════
# the scan
# ══════════════════════════════════════════════════════════════
def scan_response(
    db: Session,
    text: str,
    *,
    reconciled: dict[str, Any] | None = None,
    eligibility: list[dict[str, Any]] | None = None,
    declared_citations: list[dict[str, Any]] | None = None,
    guard_config: dict[str, Any] | None = None,
    patterns: list[tuple[str, str, str | None]] | None = None,
) -> GuardReport:
    """
    Check one draft reply against everything policy says it may claim.

    ``patterns`` is injectable so a 500-complaint benchmark loads the pattern
    library once instead of per reply.
    """
    config = guard_config or {}
    reconciled = reconciled or {}
    patterns = patterns if patterns is not None else load_promise_patterns(db)
    index = eligibility_index(eligibility)

    # The configured money pattern, not a second copy of one. Two definitions
    # of what an amount looks like is how a five-digit dispute once slipped
    # under a threshold that a six-digit one would have caught.
    amount_pattern = load_entity_patterns(db).get("AMOUNT", "")

    report = GuardReport()

    # ── 1. promises ──
    # A phrase its own clause negates ("we cannot offer a full refund") is the
    # guard's desired outcome, not a violation of it; blocking it would fire on
    # exactly the replies the correction instruction asks the model to write.
    promises = detect_promises(text, patterns, exclude_negated=True)
    report.promises_found = promises

    for promise in promises:
        report.checks_run += 1
        promise_type = promise["promise_type"]
        required = promise.get("requires_eligibility")

        if required is None:
            # TIMELINE: no eligibility rule can authorise a committed date, so
            # it stands or falls on a citation to an active policy.
            if report.citations_found or _has_active_citation(db, text, declared_citations):
                report.checks_passed += 1
                continue
            report.findings.append(
                GuardFinding(
                    flag_type=ResponseFlagType.UNSUPPORTED_PROMISE,
                    severity=Severity.HIGH,
                    explanation=(
                        "The reply commits to a timeline with no policy citation to "
                        "support it. A date given to a customer becomes a commitment "
                        "the company is held to."
                    ),
                    matched_text=promise["text"],
                    span_start=promise["start"],
                    span_end=promise["end"],
                    promise_type=promise_type,
                )
            )
            continue

        finding = index.get(str(required).upper())
        if is_permitted(finding):
            # Eligible, but an eligibility can carry a ceiling. An approved
            # promise naming the wrong number is still an unauthorised
            # commitment, and it is the one that reads as authorised.
            breach = exceeds_ceiling(
                text, promise, finding, amount_pattern=amount_pattern
            )
            if breach is None:
                report.checks_passed += 1
                continue

            stated, limit = breach
            currency = (finding.get("currency") or "").strip()
            report.findings.append(
                GuardFinding(
                    flag_type=ResponseFlagType.UNSUPPORTED_PROMISE,
                    severity=Severity.CRITICAL,
                    explanation=(
                        f"The reply commits to {currency} {stated:,.2f} but "
                        f"{finding.get('rule_ref') or 'the eligibility rule'} caps a "
                        f"{promise_type.lower()} at {currency} {limit:,.2f}. The "
                        "eligibility is genuine, so only the amount is wrong -- which "
                        "is what makes it easy to miss."
                    ),
                    matched_text=promise["text"],
                    span_start=promise["start"],
                    span_end=promise["end"],
                    blocking_rule_ref=finding.get("rule_ref"),
                    promise_type=promise_type,
                )
            )
            continue

        hedged = _is_hedged(text, promise["start"])
        explanation = _why_not(promise_type, finding)
        if hedged:
            explanation += (
                " It is phrased conditionally, so it is flagged for a reviewer "
                "rather than blocked."
            )

        report.findings.append(
            GuardFinding(
                flag_type=ResponseFlagType.UNSUPPORTED_PROMISE,
                severity=Severity.MEDIUM if hedged else Severity.CRITICAL,
                explanation=explanation,
                matched_text=promise["text"],
                span_start=promise["start"],
                span_end=promise["end"],
                blocking_rule_ref=(finding or {}).get("rule_ref"),
                promise_type=promise_type,
            )
        )

    # ── 2. citations ──
    citation_findings, resolved, run, passed = check_citations(db, text, declared_citations)
    report.findings.extend(citation_findings)
    report.citations_found = resolved
    report.checks_run += run
    report.checks_passed += passed

    # ── 3. uncited policy claims ──
    if config.get("require_citation_for_policy_claims", True):
        for match in _POLICY_CLAIM.finditer(text or ""):
            report.checks_run += 1
            if any(c.get("resolvable") and c.get("active") for c in resolved):
                report.checks_passed += 1
                continue
            report.findings.append(
                GuardFinding(
                    flag_type=ResponseFlagType.HALLUCINATION,
                    severity=Severity.MEDIUM,
                    explanation=(
                        "The reply asserts what policy says without citing an active "
                        "policy document. The customer has no way to verify it and "
                        "neither has the agent."
                    ),
                    matched_text=match.group(0),
                    span_start=match.start(),
                    span_end=match.end(),
                )
            )

    # ── 4. claim support ──
    # Does the cited policy actually say what the reply says it says? The
    # promise check above asks whether a commitment was authorised; this asks
    # whether a statement of fact is grounded. A reply can be entirely free of
    # promises and still tell a customer the refund window is 30 days when the
    # policy says 14.
    sources = source_texts(db, resolved)
    if sources:
        claim_report = check_claims(
            text, sources,
            threshold=float(
                config.get("claim_support_threshold") or DEFAULT_SUPPORT_THRESHOLD
            ),
        )
        report.claims = [verdict.as_dict() for verdict in claim_report.verdicts]

        for verdict in claim_report.verdicts:
            report.checks_run += 1
            if not verdict.problematic:
                report.checks_passed += 1
                continue

            # A wrong figure is the serious one: a number given to a customer
            # becomes a commitment, and it is unambiguous. A low overlap score
            # is a prompt for a human to look, not a verdict.
            severity = (
                Severity.HIGH if verdict.unsupported_numbers else Severity.MEDIUM
            )
            report.findings.append(
                GuardFinding(
                    flag_type=ResponseFlagType.HALLUCINATION,
                    severity=severity,
                    explanation=verdict.reason or "This statement is not supported by the cited policy.",
                    matched_text=verdict.claim.text[:MAX_MATCH_SAMPLE],
                    span_start=verdict.claim.start,
                    span_end=verdict.claim.end,
                )
            )

    # ── 5. the agent checklist ──
    # Not a pass/fail check: whether "verify shipment status in the tracking
    # system" was done cannot be read off the reply text. It is surfaced for a
    # human to tick, and deliberately excluded from the compliance score
    # rather than guessed at.
    report.required_action_checklist = [
        {"action": action, "source": "RULE_MATRIX", "confirmed": False}
        for action in (reconciled.get("required_actions") or [])
    ]

    if report.findings:
        log.warning(
            "response_guard_findings",
            status=report.status,
            types=sorted({f.flag_type for f in report.findings}),
            blocking=len(report.blocking_findings),
        )
    return report


def _has_active_citation(
    db: Session, text: str, declared: list[dict[str, Any]] | None
) -> bool:
    """Whether the reply cites at least one resolvable, active policy."""
    _, resolved, _, _ = check_citations(db, text, declared)
    return any(c.get("resolvable") and c.get("active") for c in resolved)


# ══════════════════════════════════════════════════════════════
# persistence
# ══════════════════════════════════════════════════════════════
def persist_flags(db: Session, response_id: Any, report: GuardReport) -> list[ResponseFlag]:
    """
    Write the findings to ``response_flags``.

    Stored even when the reply is regenerated: "the first draft promised a
    refund the policy did not support, and here is the span" is the evidence
    SRS 1.8 #9 asks for, and it disappears if only the clean draft is kept.
    """
    rows = [finding.to_row(response_id) for finding in report.findings]
    for row in rows:
        db.add(row)
    if rows:
        db.flush()
    return rows


def correction_instruction(report: GuardReport) -> str:
    """
    What to tell the model when regenerating (``REGENERATE_ONCE_THEN_REVIEW``).

    Names the exact phrase and why it is not permitted. A model told only that
    its reply was rejected tends to return a differently non-compliant one.
    """
    lines: list[str] = []
    for finding in report.findings:
        quoted = f' "{finding.matched_text}"' if finding.matched_text else ""
        lines.append(f"- Remove or rephrase{quoted}: {finding.explanation}")

    return (
        "Your previous reply was rejected by an automated policy check. "
        "Rewrite it, correcting exactly these problems and changing nothing "
        "else:\n\n"
        + "\n".join(lines)
        + "\n\nDo not commit to any outcome, amount, exception or date that the "
        "approved policy extracts do not support. If the customer's request "
        "cannot be confirmed yet, say what will happen next instead."
    )
