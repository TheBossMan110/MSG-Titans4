"""
Duplicate and repeat detection (FR lvi, lviii; SRS Steps 52, 54).

    "The system must detect duplicate complaints and repeat complaints from
     the same customer."                                  — SRS Steps 52, 54

Three different relationships, deliberately not merged into one "similar"
score, because they mean different things to an agent:

* **EXACT_DUPLICATE** — the same complaint submitted twice, usually because
  the customer thought the first attempt failed. One answer is owed, not two.
* **NEAR_DUPLICATE** — the same underlying problem described again. Worth
  linking; still its own complaint.
* **REPEAT** — the customer has contacted us before about an *unresolved*
  matter. This is the one that changes the outcome: the rule matrix escalates
  on the third unresolved contact, and that count must come from stored
  records rather than from the customer asserting it.

The distinction between near-duplicate and repeat matters. A customer
complaining twice in an hour is duplicating; a customer complaining for the
third time in six weeks is being failed, and only the second deserves
escalation.

**Similarity is lexical, never semantic here.** ``rapidfuzz`` over normalised
text, with no embedding call. Duplicate detection has to work during a provider
outage and has to give the same answer twice — a link that appears only when
the embedding service is up would make the repeat count, and therefore the
escalation, non-deterministic.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from rapidfuzz import fuzz
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from src.core.config import settings
from src.core.logging import get_logger
from src.db.enums import ComplaintStatus, LinkType
from src.db.models import Complaint, ComplaintLink
from src.db.fresh import needs_clearing

log = get_logger("complaint_processing.dedupe")

DETECTED_BY_TRIGRAM = "TRIGRAM"
DETECTED_BY_REFERENCE = "REFERENCE"

# How far back to look for a duplicate. A complaint about the same thing a
# year later is a new complaint, not a duplicate of a closed one.
DUPLICATE_LOOKBACK_DAYS = 30

# Statuses that mean the customer's problem is still open. Only these count
# toward a repeat: a customer coming back about something we actually resolved
# is not being failed.
UNRESOLVED = frozenset(
    {
        ComplaintStatus.NEW,
        ComplaintStatus.ANALYZING,
        ComplaintStatus.ANALYZED,
        ComplaintStatus.VALIDATED,
        ComplaintStatus.ASSIGNED,
        ComplaintStatus.IN_PROGRESS,
        ComplaintStatus.AWAITING_CUSTOMER,
        ComplaintStatus.ESCALATED,
        ComplaintStatus.MANUAL_REVIEW,
        ComplaintStatus.REOPENED,
        # A complaint the system failed to process is the most unresolved of
        # all: the customer is waiting and nothing is working on it.
        ComplaintStatus.FAILED,
    }
)

# Candidates to compare against. Scoring every complaint ever filed would make
# intake O(n); this bounds it while keeping recall high, because a duplicate
# is almost always recent.
MAX_CANDIDATES = 200


@dataclass(slots=True)
class DuplicateMatch:
    """One related complaint and why it was linked."""

    complaint_id: uuid.UUID
    public_ref: str
    similarity: float
    link_type: str
    detected_by: str = DETECTED_BY_TRIGRAM
    status: str | None = None
    created_at: datetime | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "complaint_id": str(self.complaint_id),
            "public_ref": self.public_ref,
            "similarity": round(self.similarity, 4),
            "link_type": self.link_type,
            "detected_by": self.detected_by,
            "status": self.status,
        }


@dataclass(slots=True)
class DedupeResult:
    """Everything found about one complaint's relatives."""

    exact: DuplicateMatch | None = None
    near: list[DuplicateMatch] = field(default_factory=list)
    repeats: list[DuplicateMatch] = field(default_factory=list)

    @property
    def is_duplicate(self) -> bool:
        return self.exact is not None

    @property
    def repeat_count(self) -> int:
        """
        Prior *unresolved* contacts from this customer.

        Counted from stored records, never from the complaint claiming to be a
        repeat: "I have called five times" is a sentiment, not a fact, and
        letting it drive escalation would put the customer in charge of their
        own priority.
        """
        return len(self.repeats)

    @property
    def all_matches(self) -> list[DuplicateMatch]:
        matches = list(self.near)
        if self.exact:
            matches.insert(0, self.exact)
        return matches + self.repeats

    def summary(self) -> dict[str, Any]:
        return {
            "is_duplicate": self.is_duplicate,
            "exact": self.exact.as_dict() if self.exact else None,
            "near": [m.as_dict() for m in self.near],
            "repeat_count": self.repeat_count,
            "repeats": [m.as_dict() for m in self.repeats],
        }


# ══════════════════════════════════════════════════════════════
# similarity
# ══════════════════════════════════════════════════════════════
def similarity(left: str, right: str) -> float:
    """
    How alike two complaints are, from 0.0 to 1.0.

    ``token_sort_ratio`` rather than a plain ratio: the same complaint retyped
    rarely preserves word order, and a positional comparison would score an
    obvious resubmission as unrelated. The negation problem that made this
    metric unsuitable for comparing *obligations* does not arise here — two
    complaints are not each other's opposite.
    """
    return fuzz.token_sort_ratio((left or "").lower(), (right or "").lower()) / 100.0


def _candidates(
    db: Session,
    *,
    customer_id: uuid.UUID | None,
    exclude_id: uuid.UUID | None,
    order_ref: str | None,
    since: datetime,
) -> list[Complaint]:
    """
    Complaints worth comparing against.

    Scoped to the same customer, plus anything sharing the order reference —
    a duplicate filed from a different account is still a duplicate of the
    same order.
    """
    conditions = []
    if customer_id is not None:
        conditions.append(Complaint.customer_id == customer_id)
    if order_ref:
        conditions.append(Complaint.order_ref == order_ref)
    if not conditions:
        return []

    query = (
        select(Complaint)
        .where(or_(*conditions), Complaint.created_at >= since)
        .order_by(Complaint.created_at.desc())
        .limit(MAX_CANDIDATES)
    )
    if exclude_id is not None:
        query = query.where(Complaint.id != exclude_id)

    return list(db.execute(query).scalars())


# ══════════════════════════════════════════════════════════════
# detection
# ══════════════════════════════════════════════════════════════
def detect(
    db: Session,
    *,
    text: str,
    customer_id: uuid.UUID | None = None,
    order_ref: str | None = None,
    exclude_id: uuid.UUID | None = None,
    exact_threshold: float | None = None,
    near_threshold: float | None = None,
    repeat_lookback_days: int | None = None,
) -> DedupeResult:
    """
    Find duplicates and prior unresolved contacts for one complaint.

    Thresholds come from ``app_config['thresholds']`` via settings, so an
    evaluator can retune them at runtime (SRS 1.8 #14).
    """
    result = DedupeResult()
    exact_floor = exact_threshold or settings.duplicate_similarity_threshold
    near_floor = near_threshold or settings.near_duplicate_threshold
    lookback = repeat_lookback_days or 90

    now = datetime.now(UTC)
    duplicate_since = now - timedelta(days=DUPLICATE_LOOKBACK_DAYS)
    repeat_since = now - timedelta(days=lookback)

    candidates = _candidates(
        db,
        customer_id=customer_id,
        exclude_id=exclude_id,
        order_ref=order_ref,
        since=min(duplicate_since, repeat_since),
    )
    if not candidates:
        return result

    for candidate in candidates:
        other = candidate.description_clean or candidate.description_raw or ""
        created = candidate.created_at
        score = similarity(text, other)

        detected_by = (
            DETECTED_BY_REFERENCE
            if order_ref and candidate.order_ref == order_ref
            else DETECTED_BY_TRIGRAM
        )

        match = DuplicateMatch(
            complaint_id=candidate.id,
            public_ref=candidate.public_ref,
            similarity=score,
            link_type=LinkType.NEAR_DUPLICATE,
            detected_by=detected_by,
            status=candidate.status,
            created_at=created,
        )

        within_duplicate_window = created is None or created >= duplicate_since

        if score >= exact_floor and within_duplicate_window:
            match.link_type = LinkType.EXACT_DUPLICATE
            # Keep the closest match, not merely the first.
            if result.exact is None or score > result.exact.similarity:
                if result.exact is not None:
                    result.exact.link_type = LinkType.NEAR_DUPLICATE
                    result.near.append(result.exact)
                result.exact = match
            else:
                match.link_type = LinkType.NEAR_DUPLICATE
                result.near.append(match)
        elif score >= near_floor and within_duplicate_window:
            result.near.append(match)

        # A repeat is about status and recency, not similarity: the customer
        # coming back about a different unresolved problem is still a repeat
        # contact, and the rule matrix escalates on the count.
        if (
            customer_id is not None
            and candidate.customer_id == customer_id
            and candidate.status in UNRESOLVED
            and (created is None or created >= repeat_since)
        ):
            result.repeats.append(
                DuplicateMatch(
                    complaint_id=candidate.id,
                    public_ref=candidate.public_ref,
                    similarity=score,
                    link_type=LinkType.REPEAT,
                    detected_by=DETECTED_BY_TRIGRAM,
                    status=candidate.status,
                    created_at=created,
                )
            )

    if result.is_duplicate:
        log.info(
            "duplicate_detected",
            public_ref=result.exact.public_ref,
            similarity=round(result.exact.similarity, 3),
        )
    return result


# ══════════════════════════════════════════════════════════════
# persistence
# ══════════════════════════════════════════════════════════════
def persist_links(
    db: Session, complaint_id: uuid.UUID, result: DedupeResult, *, replace: bool = True
) -> list[ComplaintLink]:
    """
    Write the relationships to ``complaint_links``.

    Links are directional from the new complaint to the earlier one, so the
    graph reads chronologically and an agent opening the original does not see
    it pointing forward at something that did not exist when it was filed.
    """
    if replace and needs_clearing(db, complaint_id, "complaint_links"):
        db.query(ComplaintLink).filter(
            ComplaintLink.complaint_id == complaint_id
        ).delete()

    rows: list[ComplaintLink] = []
    seen: set[tuple[uuid.UUID, str]] = set()

    for match in result.all_matches:
        key = (match.complaint_id, match.link_type)
        if key in seen or match.complaint_id == complaint_id:
            continue
        seen.add(key)
        row = ComplaintLink(
            complaint_id=complaint_id,
            related_id=match.complaint_id,
            link_type=match.link_type,
            similarity=match.similarity,
            detected_by=match.detected_by,
        )
        db.add(row)
        rows.append(row)

    if rows:
        db.flush()
    return rows


def links_for(db: Session, complaint_id: uuid.UUID) -> list[dict[str, Any]]:
    """Stored relationships for one complaint, for the agent view."""
    rows = db.execute(
        select(ComplaintLink, Complaint.public_ref, Complaint.status)
        .join(Complaint, ComplaintLink.related_id == Complaint.id)
        .where(ComplaintLink.complaint_id == complaint_id)
        .order_by(ComplaintLink.link_type)
    ).all()

    return [
        {
            "link_type": link.link_type,
            "related_ref": public_ref,
            "related_status": status,
            "similarity": float(link.similarity) if link.similarity is not None else None,
            "detected_by": link.detected_by,
        }
        for link, public_ref, status in rows
    ]
