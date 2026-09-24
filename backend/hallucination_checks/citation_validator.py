"""
Citation validation (FR xxxii; SRS Step 35; Source-Traceability Challenge).

Every policy reference that touches a complaint — cited by the model, required
by a matched rule, or surfaced by retrieval — is written to
``complaint_policy_refs`` with the verdict on whether it holds up.

That table is the answer to *"pick any generated statement and show us where it
came from"*: one row gives the document, version, section, page, the exact
chunk, who proposed it, whether the version was ACTIVE at the time, and the
resulting applicability.

Four verdicts, deliberately kept apart because they mean different things and
three of them are easy to conflate:

* **unresolvable** — no such chunk. The reference was invented.
* **OUTDATED** — real, but superseded or expired. Formally correct and
  substantively wrong, which is the case SRS 1.8 #10 tests: quoting a
  withdrawn refund window commits the company to terms it has replaced.
* **NOT_APPLICABLE** — real and current, but not yet in force, or a draft.
* **APPLICABLE** — safe to rely on.

Recording the source matters as much as the verdict. A reference the *rules*
required and a reference the *model* chose are different kinds of evidence, and
an aggregate that mixed them would make the model look as well-grounded as the
rule matrix.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from knowledge_base import retrieval, versioning
from src.core.logging import get_logger
from src.db.enums import DocStatus, PolicyApplicability, PolicyRefSource
from src.db.models import Chunk, ComplaintPolicyRef

log = get_logger("hallucination_checks.citations")


@dataclass(slots=True)
class CitationVerdict:
    """One reference and whether it holds up."""

    doc_ref: str
    section_ref: str | None = None
    chunk_key: str | None = None
    source: str = PolicyRefSource.GENAI

    resolved: bool = False
    was_active: bool = False
    applicability: str = PolicyApplicability.NOT_APPLICABLE
    doc_version: str | None = None
    precedence_tier: str | None = None
    page_no: int | None = None
    paragraph_index: int | None = None
    document_version_id: uuid.UUID | None = None
    reason: str | None = None
    retrieved_for_this_complaint: bool | None = None

    @property
    def hallucinated(self) -> bool:
        """Invented outright — no such chunk exists."""
        return not self.resolved

    @property
    def trustworthy(self) -> bool:
        """Safe for a generated statement to rest on."""
        return self.resolved and self.applicability == PolicyApplicability.APPLICABLE

    def as_dict(self) -> dict[str, Any]:
        return {
            "doc_ref": self.doc_ref,
            "section_ref": self.section_ref,
            "chunk_key": self.chunk_key,
            "source": self.source,
            "resolved": self.resolved,
            "was_active": self.was_active,
            "applicability": self.applicability,
            "doc_version": self.doc_version,
            "trustworthy": self.trustworthy,
            "reason": self.reason,
        }


@dataclass(slots=True)
class CitationReport:
    """Every reference attached to one complaint."""

    verdicts: list[CitationVerdict] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.verdicts)

    @property
    def hallucinated(self) -> list[CitationVerdict]:
        return [v for v in self.verdicts if v.hallucinated]

    @property
    def outdated(self) -> list[CitationVerdict]:
        return [
            v for v in self.verdicts
            if v.resolved and v.applicability == PolicyApplicability.OUTDATED
        ]

    @property
    def trustworthy(self) -> list[CitationVerdict]:
        return [v for v in self.verdicts if v.trustworthy]

    def by_source(self, source: str) -> list[CitationVerdict]:
        return [v for v in self.verdicts if v.source == source]

    def traceability(self) -> tuple[int, int]:
        """
        ``(trustworthy, total)`` over the references the **model** proposed.

        Rule-required and retrieval-surfaced references are excluded: they are
        correct by construction, and counting them would dilute the score into
        flattery. The number is supposed to measure the model's grounding.
        """
        genai = self.by_source(PolicyRefSource.GENAI)
        return sum(1 for v in genai if v.trustworthy), len(genai)

    def summary(self) -> dict[str, Any]:
        trustworthy, total = self.traceability()
        return {
            "total": self.total,
            "hallucinated": len(self.hallucinated),
            "outdated": len(self.outdated),
            "trustworthy": len(self.trustworthy),
            "genai_traceability": {"trustworthy": trustworthy, "total": total},
            "by_source": {
                source: len(self.by_source(source))
                for source in (
                    PolicyRefSource.GENAI,
                    PolicyRefSource.PYTHON,
                    PolicyRefSource.RETRIEVAL,
                )
            },
        }


# ══════════════════════════════════════════════════════════════
# resolution
# ══════════════════════════════════════════════════════════════
def validate_citation(
    db: Session,
    *,
    doc_ref: str | None,
    section_ref: str | None = None,
    chunk_key: str | None = None,
    source: str = PolicyRefSource.GENAI,
    retrieved_chunk_keys: set[str] | None = None,
) -> CitationVerdict:
    """Resolve one reference and classify what it resolved to."""
    verdict = CitationVerdict(
        doc_ref=(doc_ref or "").upper(),
        section_ref=section_ref,
        chunk_key=chunk_key,
        source=source,
    )

    if not verdict.doc_ref and not chunk_key:
        verdict.reason = "No document reference was given."
        return verdict

    chunk = retrieval.resolve_citation(
        db, chunk_key=chunk_key, doc_ref=doc_ref, section_ref=section_ref
    )
    if chunk is None:
        verdict.reason = (
            f"{verdict.doc_ref or chunk_key} does not exist in the knowledge base."
        )
        log.warning("citation_unresolvable", doc_ref=verdict.doc_ref, chunk_key=chunk_key)
        return verdict

    version = chunk.document_version
    verdict.resolved = True
    verdict.chunk_key = chunk.chunk_key
    verdict.doc_ref = chunk.doc_ref or verdict.doc_ref
    verdict.section_ref = chunk.section_ref or section_ref
    verdict.page_no = chunk.page_no
    verdict.paragraph_index = chunk.paragraph_index
    verdict.document_version_id = getattr(version, "id", None)
    verdict.doc_version = getattr(version, "version", None)
    verdict.was_active = getattr(version, "status", None) == DocStatus.ACTIVE
    verdict.applicability = versioning.applicability_for(version)
    verdict.precedence_tier = versioning.tier_for_document(
        getattr(getattr(version, "document", None), "doc_type", None)
    )

    if retrieved_chunk_keys is not None:
        verdict.retrieved_for_this_complaint = chunk.chunk_key in retrieved_chunk_keys

    if verdict.applicability == PolicyApplicability.OUTDATED:
        verdict.reason = (
            f"{verdict.doc_ref} resolves to a version that is no longer in force "
            f"({getattr(version, 'status', 'unknown')}). It may be used to detect a "
            "contradiction, but not as the basis of an answer."
        )
    elif verdict.applicability == PolicyApplicability.NOT_APPLICABLE:
        verdict.reason = (
            f"{verdict.doc_ref} resolves to a version that is not yet in force."
        )

    return verdict


def validate_all(
    db: Session,
    *,
    genai_refs: list[Any] | None = None,
    rule_refs: list[dict[str, Any]] | None = None,
    retrieved: list[Any] | None = None,
    retrieved_chunk_keys: set[str] | None = None,
) -> CitationReport:
    """
    Validate every reference attached to a complaint, from all three sources.

    De-duplicated on (doc_ref, section_ref, source): the same document cited
    twice by the model is one reference, but the same document cited by the
    model *and* required by a rule is two, because they are different claims
    about where the answer came from.
    """
    report = CitationReport()
    seen: set[tuple[str, str | None, str]] = set()

    def add(doc_ref, section_ref, chunk_key, source):
        key = ((doc_ref or "").upper(), section_ref, source)
        if not doc_ref and not chunk_key:
            return
        if key in seen:
            return
        seen.add(key)
        report.verdicts.append(
            validate_citation(
                db,
                doc_ref=doc_ref, section_ref=section_ref, chunk_key=chunk_key,
                source=source, retrieved_chunk_keys=retrieved_chunk_keys,
            )
        )

    for reference in genai_refs or []:
        add(
            _get(reference, "doc_ref"),
            _get(reference, "section_ref"),
            _get(reference, "chunk_key"),
            PolicyRefSource.GENAI,
        )

    for reference in rule_refs or []:
        add(
            _get(reference, "doc_ref"),
            _get(reference, "section_ref"),
            _get(reference, "chunk_key"),
            PolicyRefSource.PYTHON,
        )

    for chunk in retrieved or []:
        add(
            _get(chunk, "doc_ref"),
            _get(chunk, "section_ref"),
            _get(chunk, "chunk_key"),
            PolicyRefSource.RETRIEVAL,
        )

    return report


def _get(item: Any, name: str) -> Any:
    if isinstance(item, dict):
        return item.get(name)
    return getattr(item, name, None)


# ══════════════════════════════════════════════════════════════
# persistence
# ══════════════════════════════════════════════════════════════
def persist(
    db: Session,
    complaint_id: uuid.UUID,
    report: CitationReport,
    *,
    genai_run_id: uuid.UUID | None = None,
    validation_run_id: uuid.UUID | None = None,
    replace: bool = True,
) -> list[ComplaintPolicyRef]:
    """
    Write the verdicts to ``complaint_policy_refs``.

    ``replace`` clears prior rows for the complaint first: re-running after a
    policy update must not leave two contradictory traceability records that a
    report would then have to choose between.
    """
    if replace:
        db.query(ComplaintPolicyRef).filter(
            ComplaintPolicyRef.complaint_id == complaint_id
        ).delete()

    rows: list[ComplaintPolicyRef] = []
    for verdict in report.verdicts:
        row = ComplaintPolicyRef(
            complaint_id=complaint_id,
            genai_run_id=genai_run_id if verdict.source == PolicyRefSource.GENAI else None,
            validation_run_id=(
                validation_run_id if verdict.source == PolicyRefSource.PYTHON else None
            ),
            source=verdict.source,
            doc_ref=verdict.doc_ref or "UNKNOWN",
            section_ref=verdict.section_ref,
            doc_version=verdict.doc_version,
            chunk_key=verdict.chunk_key,
            page_no=verdict.page_no,
            paragraph_index=verdict.paragraph_index,
            document_version_id=verdict.document_version_id,
            resolved=verdict.resolved,
            was_active=verdict.was_active,
            applicability=verdict.applicability,
            precedence_tier=verdict.precedence_tier,
            reason=verdict.reason,
        )
        db.add(row)
        rows.append(row)

    if rows:
        db.flush()
    return rows


def trace(db: Session, complaint_id: uuid.UUID) -> list[dict[str, Any]]:
    """
    The stored traceability record for one complaint.

    This is what the Source-Traceability Challenge is answered with: read back
    from the database rather than recomputed, so what is shown is provably what
    the system concluded at the time.
    """
    rows = db.execute(
        select(ComplaintPolicyRef)
        .where(ComplaintPolicyRef.complaint_id == complaint_id)
        .order_by(ComplaintPolicyRef.source, ComplaintPolicyRef.doc_ref)
    ).scalars().all()

    return [
        {
            "source": row.source,
            "doc_ref": row.doc_ref,
            "version": row.doc_version,
            "section": row.section_ref,
            "page": row.page_no,
            "paragraph": row.paragraph_index,
            "chunk_key": row.chunk_key,
            "resolved": row.resolved,
            "was_active": row.was_active,
            "applicability": row.applicability,
            "precedence_tier": row.precedence_tier,
            "reason": row.reason,
        }
        for row in rows
    ]


def chunk_texts(db: Session, chunk_keys: list[str]) -> dict[str, str]:
    """The source text behind a set of chunks, for claim-support scoring."""
    if not chunk_keys:
        return {}
    rows = db.execute(select(Chunk).where(Chunk.chunk_key.in_(chunk_keys))).scalars().all()
    return {row.chunk_key: row.text or "" for row in rows}


def source_texts(db: Session, citations: list[dict[str, Any]]) -> dict[str, str]:
    """
    The text a set of citations actually points at.

    Scope depends on how precisely the reply cited:

    * **with a section** — that chunk alone. The reply named a specific
      passage, so that passage is what its claims must rest on.
    * **document only** — every chunk of that document version.

    The distinction matters more than it looks. ``resolve_citation`` given a
    bare ``REF-POL-02`` returns the document's first chunk, so scoring a claim
    about the refund window against it would compare the claim to the policy's
    preamble and report a perfectly grounded sentence as unsupported. A reply
    that cites a whole document is claiming support from that whole document,
    and must be scored against it.
    """
    sources: dict[str, str] = {}
    version_ids: set[uuid.UUID] = set()
    exact_keys: list[str] = []

    for citation in citations:
        if not (citation.get("resolvable") and citation.get("active")):
            continue
        if citation.get("section_ref") and citation.get("chunk_key"):
            exact_keys.append(citation["chunk_key"])
            continue
        version_id = citation.get("document_version_id")
        if version_id is None and citation.get("chunk_key"):
            chunk = db.execute(
                select(Chunk).where(Chunk.chunk_key == citation["chunk_key"])
            ).scalars().first()
            version_id = getattr(chunk, "document_version_id", None)
        if version_id is not None:
            version_ids.add(version_id)

    sources.update(chunk_texts(db, exact_keys))

    if version_ids:
        rows = db.execute(
            select(Chunk).where(Chunk.document_version_id.in_(version_ids))
        ).scalars().all()
        for row in rows:
            sources[row.chunk_key] = row.text or ""

    return sources
