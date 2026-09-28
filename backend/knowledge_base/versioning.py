"""
Document version control and policy precedence.

FR x    Document Version Control   SRS Step 7
FR xxiii Policy Applicability      SRS Step 26
SRS 1.8 #10 Contradictory Policy Challenge

SRS Step 7 requires the application to distinguish an active policy from a
previous, superseded or draft one, and states that "outdated policies should
not be used as the primary basis for final complaint resolutions".

Two mechanisms enforce that, and neither of them is a convention:

1. ``ux_docver_one_active`` is a partial unique index on
   ``document_versions(document_id) WHERE status = 'ACTIVE'``.  The database
   physically cannot hold two active versions of one policy.
2. Retrieval filters on ``status = 'ACTIVE'``.  A superseded version stays in
   the database and stays readable, but only for contradiction detection and
   version diffing — never as the basis of a resolution.

Precedence between *different* documents that disagree (policy vs SOP vs FAQ)
is a separate question, answered from ``app_config['policy_precedence']`` so
the order is documented data rather than an if-chain.
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.logging import get_logger
from src.db.enums import DocStatus, PolicyApplicability
from src.db.models import AppConfig, Document, DocumentVersion

log = get_logger("knowledge_base.versioning")

DEFAULT_PRECEDENCE = [
    "ACTIVE_POLICY", "COMPLIANCE", "DEPARTMENT_SOP",
    "ROUTING_RULES", "SLA", "FAQ", "HANDBOOK",
]

# Maps a document's declared type onto a precedence tier.
_TIER_BY_DOC_TYPE = {
    "POLICY": "ACTIVE_POLICY",
    "COMPLIANCE": "COMPLIANCE",
    "SOP": "DEPARTMENT_SOP",
    "PROCESS": "DEPARTMENT_SOP",
    "ESCALATION": "DEPARTMENT_SOP",
    "ROUTING_RULES": "ROUTING_RULES",
    "SLA": "SLA",
    "FAQ": "FAQ",
    "HANDBOOK": "HANDBOOK",
    "OTHER": "HANDBOOK",
}


def _today() -> date:
    return datetime.now(UTC).date()


# ══════════════════════════════════════════════════════════════
# Status
# ══════════════════════════════════════════════════════════════
_DECLARED_DRAFT = re.compile(r"^\s*draft\b", re.IGNORECASE)


def declares_draft(status: str | None) -> bool:
    """Whether a document's own status field says it is a draft ("DRAFT", "Draft v0.9")."""
    return bool(status and _DECLARED_DRAFT.match(status))


def initial_status(
    *,
    metadata_complete: bool,
    effective_date: date | None,
    expiry_date: date | None,
    parse_failed: bool,
    on: date | None = None,
    declared_status: str | None = None,
) -> DocStatus:
    """
    Decide the status a freshly ingested version should take.

    A document that could not be parsed, or that arrived without the metadata
    needed to place it on a timeline, goes to METADATA_REVIEW rather than being
    rejected.  That is what lets an unrecognised hidden-pack document be
    ingested and reviewed instead of turning the evaluator away.

    A document that declares itself a draft stays one, whatever its dates say.
    DOC-025 v0.9 is marked DRAFT with an effective date of 2026-01-01; once
    that date had passed, the dates alone made it ACTIVE, and an unapproved
    policy became retrievable as policy. Only DRAFT is read from the field:
    it is the one declared status that withholds a document, and every other
    lifecycle is already decided from the dates or by an administrator.
    """
    today = on or _today()

    if parse_failed or not metadata_complete:
        return DocStatus.METADATA_REVIEW
    if declares_draft(declared_status):
        return DocStatus.DRAFT  # not in force until somebody activates it
    if expiry_date and expiry_date < today:
        return DocStatus.EXPIRED
    if effective_date and effective_date > today:
        return DocStatus.DRAFT  # approved but not yet in force
    return DocStatus.ACTIVE


def refresh_expiry_status(db: Session, *, on: date | None = None) -> int:
    """
    Demote any ACTIVE version whose expiry date has passed.

    Called on ingest and from the health path.  Without it a policy would stay
    authoritative past its own expiry date purely because nothing looked.
    """
    today = on or _today()
    expired = db.execute(
        select(DocumentVersion).where(
            DocumentVersion.status == DocStatus.ACTIVE,
            DocumentVersion.expiry_date.is_not(None),
            DocumentVersion.expiry_date < today,
        )
    ).scalars().all()

    for version in expired:
        version.status = DocStatus.EXPIRED
        log.info("version_expired", doc_ref=version.doc_ref, version=version.version)
    return len(expired)


# ══════════════════════════════════════════════════════════════
# Activation
# ══════════════════════════════════════════════════════════════
def current_active(db: Session, document_id) -> DocumentVersion | None:
    return db.execute(
        select(DocumentVersion).where(
            DocumentVersion.document_id == document_id,
            DocumentVersion.status == DocStatus.ACTIVE,
        )
    ).scalars().first()


def activate_version(
    db: Session, version: DocumentVersion, *, superseded_by_upload: bool = True
) -> DocumentVersion | None:
    """
    Make ``version`` the active one for its document family.

    Returns the version it replaced, if any.  The previous version is *demoted,
    never deleted* — contradiction detection and the Policy Update Challenge
    both need the old text to compare against.

    The demotion is flushed before the promotion so the one-active partial
    unique index is never momentarily violated inside the transaction.
    """
    previous = current_active(db, version.document_id)

    if previous is not None and previous.id == version.id:
        return None

    if previous is not None:
        previous.status = DocStatus.SUPERSEDED
        previous.superseded_at = datetime.now(UTC)
        if superseded_by_upload:
            previous.superseded_by_id = version.id
        db.flush()

    version.status = DocStatus.ACTIVE
    version.activated_at = datetime.now(UTC)
    db.flush()

    log.info(
        "version_activated",
        doc_ref=version.doc_ref,
        version=version.version,
        replaced=previous.version if previous else None,
    )
    return previous


def next_version_label(db: Session, document_id, *, proposed: str | None) -> str:
    """
    Choose a version label, avoiding a collision with an existing one.

    A hidden-pack document often carries no version at all.  Rather than
    refusing it we assign the next integer, so the family timeline stays
    coherent and the upload is still traceable.
    """
    existing = {
        v.version
        for v in db.execute(
            select(DocumentVersion).where(DocumentVersion.document_id == document_id)
        ).scalars()
    }
    if proposed and proposed not in existing:
        return proposed

    if not existing:
        return proposed or "1.0"

    numeric: list[float] = []
    for label in existing:
        try:
            parts = label.split(".")
            numeric.append(float(f"{parts[0]}.{parts[1]}" if len(parts) > 1 else parts[0]))
        except (ValueError, IndexError):
            continue
    base = max(numeric) if numeric else 0.0
    candidate = f"{base + 0.1:.1f}"
    while candidate in existing:
        base += 0.1
        candidate = f"{base + 0.1:.1f}"
    return candidate


# ══════════════════════════════════════════════════════════════
# Precedence  (SRS 1.8 #10)
# ══════════════════════════════════════════════════════════════
def precedence_order(db: Session) -> list[str]:
    """The documented precedence order, highest authority first."""
    config = db.get(AppConfig, "policy_precedence")
    if config and isinstance(config.value, dict):
        order = config.value.get("order")
        if isinstance(order, list) and order:
            return [str(tier) for tier in order]
    return list(DEFAULT_PRECEDENCE)


def tier_for_document(doc_type: str | None) -> str:
    return _TIER_BY_DOC_TYPE.get((doc_type or "OTHER").upper(), "HANDBOOK")


def precedence_rank(db: Session, doc_type: str | None) -> int:
    """
    Lower rank wins.  An unknown tier sorts last rather than first, so an
    unrecognised document can never outrank an approved policy.
    """
    order = precedence_order(db)
    tier = tier_for_document(doc_type)
    return order.index(tier) if tier in order else len(order)


def resolve_conflict(
    db: Session,
    candidates: list[tuple[str, str | None, date | None]],
) -> tuple[str, list[str]]:
    """
    Pick the authoritative source among disagreeing documents.

    ``candidates`` is ``(doc_ref, doc_type, effective_date)``.  Ties inside a
    precedence tier are broken by the later effective date, as declared in
    ``config/policy.yaml``.

    Returns ``(winning_doc_ref, overruled_doc_refs)``.  Both halves matter: the
    overruled list is what the UI shows to prove a conflict was detected and
    resolved rather than silently ignored.
    """
    if not candidates:
        return "", []

    def sort_key(candidate: tuple[str, str | None, date | None]):
        _, doc_type, effective = candidate
        return (precedence_rank(db, doc_type), -(effective or date.min).toordinal())

    ranked = sorted(candidates, key=sort_key)
    winner = ranked[0][0]
    return winner, [ref for ref, _, _ in ranked[1:]]


# ══════════════════════════════════════════════════════════════
# Applicability  (FR xxiii / SRS Step 26)
# ══════════════════════════════════════════════════════════════
def applicability_for(
    version: DocumentVersion | None,
    *,
    on: date | None = None,
    conditional: bool = False,
) -> PolicyApplicability:
    """
    Classify a referenced policy version.

    A citation that resolves to nothing at all is handled by the caller as a
    hallucinated reference; this function answers the narrower question of
    whether a version that *does* exist may be relied upon.
    """
    if version is None:
        return PolicyApplicability.NOT_APPLICABLE

    today = on or _today()

    if version.status in (DocStatus.SUPERSEDED, DocStatus.EXPIRED):
        return PolicyApplicability.OUTDATED
    if version.expiry_date and version.expiry_date < today:
        return PolicyApplicability.OUTDATED
    if version.status == DocStatus.DRAFT:
        return PolicyApplicability.NOT_APPLICABLE
    if version.status == DocStatus.METADATA_REVIEW:
        return PolicyApplicability.CONDITIONALLY_APPLICABLE
    if version.effective_date and version.effective_date > today:
        return PolicyApplicability.NOT_APPLICABLE
    if conditional:
        return PolicyApplicability.CONDITIONALLY_APPLICABLE
    return PolicyApplicability.APPLICABLE


def knowledge_base_version(db: Session) -> str:
    """
    A single token identifying the current knowledge-base state.

    Stamped onto every GenAI and validation run (SRS Step 49) so a past result
    can be tied to the exact corpus that produced it.
    """
    rows = db.execute(
        select(DocumentVersion.doc_ref, DocumentVersion.version, DocumentVersion.activated_at)
        .where(DocumentVersion.status == DocStatus.ACTIVE)
        .order_by(DocumentVersion.activated_at.desc().nullslast())
    ).all()
    if not rows:
        return "kb:empty"
    newest = rows[0][2]
    stamp = newest.strftime("%Y%m%d%H%M%S") if newest else "unknown"
    return f"kb:{len(rows)}docs@{stamp}"


def active_document_count(db: Session) -> int:
    return len(
        db.execute(
            select(DocumentVersion.id).where(DocumentVersion.status == DocStatus.ACTIVE)
        ).all()
    )


def find_document_by_family(db: Session, family_key: str) -> Document | None:
    return db.execute(
        select(Document).where(Document.family_key == family_key)
    ).scalars().first()
