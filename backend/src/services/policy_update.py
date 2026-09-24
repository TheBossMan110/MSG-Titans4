"""
Policy update impact (SRS 1.8 #4, the Hidden Policy Update Challenge).

    "An updated policy introduced during evaluation must be picked up without
     a redeployment, and the system's answers must change accordingly."
                                                            — SRS 1.8 #4

Activating a new version already works: the old one is demoted to SUPERSEDED,
retrieval stops returning it, and a citation to it is scored OUTDATED. What was
missing is the question an administrator actually asks the moment they press
the button — **what did I just invalidate?**

Every complaint decided while the old version was active was decided from text
that no longer governs. Most will be unaffected; some will not. Nobody can tell
which without looking, and nothing was telling anyone to look.

**The answer is read from stored citations, not recomputed.** ``complaint_policy_refs``
records, per complaint, exactly which document version each reference resolved
to at the time. That makes the blast radius a lookup rather than a guess, and
it stays correct even after the corpus moves on again.

**Nothing is re-analysed automatically.** Re-running hundreds of complaints on
a policy change would spend the free-tier quota in one click, and silently
rewriting a decision an agent has already acted on is worse than leaving it
stale. The impact list is a work queue for a person, and re-analysis stays the
explicit act it already is.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.core.logging import get_logger
from src.db.enums import DocStatus
from src.db.models import Complaint, ComplaintPolicyRef, DocumentVersion

log = get_logger("services.policy_update")


@dataclass(slots=True)
class AffectedComplaint:
    """One complaint that rested on the version just superseded."""

    public_ref: str
    status: str
    doc_ref: str
    section_ref: str | None
    cited_version: str | None
    analyzed_at: Any = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "public_ref": self.public_ref,
            "status": self.status,
            "doc_ref": self.doc_ref,
            "section_ref": self.section_ref,
            "cited_version": self.cited_version,
            "analyzed_at": self.analyzed_at.isoformat() if self.analyzed_at else None,
        }


@dataclass(slots=True)
class ImpactReport:
    """What a version change invalidated."""

    doc_ref: str = ""
    superseded_version: str | None = None
    active_version: str | None = None
    affected: list[AffectedComplaint] = field(default_factory=list)
    open_count: int = 0

    @property
    def total(self) -> int:
        return len(self.affected)

    def summary(self) -> dict[str, Any]:
        return {
            "doc_ref": self.doc_ref,
            "superseded_version": self.superseded_version,
            "active_version": self.active_version,
            "affected_total": self.total,
            # Split out because they are the ones worth a person's time: a
            # closed complaint decided under the old policy is history, an
            # open one is a decision somebody is still about to act on.
            "affected_open": self.open_count,
            "complaints": [row.as_dict() for row in self.affected],
        }


# Statuses where the decision has already been delivered and acted on. A policy
# change does not reopen them; it only matters for work still in flight.
_SETTLED = frozenset({"RESOLVED", "CLOSED"})


def impact(
    db: Session, version_id: uuid.UUID, *, limit: int = 500
) -> ImpactReport:
    """
    Which complaints cited this document version.

    Called with the version that was *superseded*, which is what the activate
    endpoint has to hand. Every complaint listed was decided from text that no
    longer governs.
    """
    version = db.get(DocumentVersion, version_id)
    if version is None:
        return ImpactReport()

    report = ImpactReport(doc_ref=version.doc_ref, superseded_version=version.version)

    active = db.execute(
        select(DocumentVersion).where(
            DocumentVersion.document_id == version.document_id,
            DocumentVersion.status == DocStatus.ACTIVE,
        )
    ).scalars().first()
    report.active_version = active.version if active else None

    rows = db.execute(
        select(ComplaintPolicyRef, Complaint)
        .join(Complaint, ComplaintPolicyRef.complaint_id == Complaint.id)
        .where(ComplaintPolicyRef.document_version_id == version_id)
        .order_by(Complaint.created_at.desc())
        .limit(limit)
    ).all()

    seen: set[str] = set()
    for ref, complaint in rows:
        if complaint.public_ref in seen:
            continue
        seen.add(complaint.public_ref)
        report.affected.append(
            AffectedComplaint(
                public_ref=complaint.public_ref,
                status=complaint.status,
                doc_ref=ref.doc_ref,
                section_ref=ref.section_ref,
                cited_version=ref.doc_version,
                analyzed_at=complaint.analyzed_at,
            )
        )
        if complaint.status not in _SETTLED:
            report.open_count += 1

    if report.total:
        log.info(
            "policy_update_impact",
            doc_ref=report.doc_ref,
            superseded=report.superseded_version,
            affected=report.total,
            open=report.open_count,
        )
    return report


def stale_citation_count(db: Session) -> int | None:
    """
    How many stored citations point at a version that no longer governs.

    A standing health figure for the administrator dashboard. Returns ``None``
    rather than 0 when nothing has been cited yet: no citations is not the
    same as no stale ones, and a dashboard reading "0 stale" on an empty
    corpus is the kind of unsourced reassurance SRS 1.8 #17 forbids.
    """
    total = db.execute(
        select(func.count()).select_from(ComplaintPolicyRef).where(
            ComplaintPolicyRef.resolved.is_(True)
        )
    ).scalar_one()
    if not total:
        return None

    return db.execute(
        select(func.count())
        .select_from(ComplaintPolicyRef)
        .join(
            DocumentVersion,
            ComplaintPolicyRef.document_version_id == DocumentVersion.id,
        )
        .where(
            ComplaintPolicyRef.resolved.is_(True),
            DocumentVersion.status.in_([DocStatus.SUPERSEDED, DocStatus.EXPIRED]),
        )
    ).scalar_one()
