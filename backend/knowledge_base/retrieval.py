"""
Hybrid retrieval over the knowledge base (SRS Step 25 — Policy Retrieval).

Two independent retrievers, fused:

**Lexical** — PostgreSQL full-text search over ``chunks.text``.  Catches the
things semantics is bad at: an exact policy identifier (``DEL-POL-04``), a
section number, a product name, a precise phrase like "fourteen calendar days".

**Semantic** — pgvector cosine over the stored embeddings.  Catches the things
lexical is bad at: a customer writing "money back" when the policy says
"refund", or "it smells like it's burning" when the policy says "overheating".

Neither is sufficient alone and the failure modes are complementary, so results
are combined with Reciprocal Rank Fusion — which needs only the *rank* from
each retriever, not comparable scores, and therefore does not require tuning a
weight between two incompatible scales.

Three invariants, all load-bearing:

1. **Only ACTIVE document versions are retrievable.**  SRS Step 7 says an
   outdated policy must not be the basis of a resolution; superseded text stays
   in the database for contradiction detection and version diffing, and is
   reachable only through the explicit ``include_superseded`` flag used by
   those features.
2. **Retrieval degrades, never fails.**  No embeddings, no API key, a provider
   outage, or a SQLite fallback database all reduce this to lexical-only rather
   than raising.
3. **Every result carries its full citation.**  doc_ref, version, section,
   page/paragraph — so the Source-Traceability Challenge is answerable from the
   retrieval result itself, with no second lookup.
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import and_, case, func, literal, or_, select
from sqlalchemy.orm import Session, undefer

from knowledge_base.embeddings import cosine_similarity, embed_query
from src.core.config import settings
from src.core.logging import get_logger
from src.db.enums import DocStatus
from src.db.models import Chunk, DocumentVersion

log = get_logger("knowledge_base.retrieval")

# Query embeddings in flight; a few, so concurrent submissions do not queue.
_EMBED_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="embed")

# RRF constant. 60 is the value from the original Cormack et al. paper and is
# deliberately left at the default: tuning it on three documents would be
# fitting noise.
RRF_K = 60

# How deep each retriever goes before fusion. Wider than top_k so a result
# ranked poorly by one retriever can still be rescued by the other.
CANDIDATE_DEPTH_MULTIPLIER = 4
MIN_CANDIDATE_DEPTH = 25

# Two fused fuzzy retrievers can contribute at most ~2/(RRF_K+1) = 0.033.
# An explicit identifier must dominate that, so the bonus is an order of
# magnitude larger rather than a tuned blend weight.
EXACT_REFERENCE_BONUS = 1.0


@dataclass(slots=True)
class RetrievedChunk:
    """One retrieval hit, carrying everything a citation needs."""

    chunk_id: Any
    chunk_key: str
    text: str
    doc_ref: str
    doc_version: str
    section_ref: str | None
    heading: str | None
    page_no: int | None
    paragraph_index: int | None
    document_version_id: Any
    score: float = 0.0
    lexical_rank: int | None = None
    semantic_rank: int | None = None
    exact_rank: int | None = None

    @property
    def matched_by(self) -> str:
        if self.exact_rank is not None:
            return "EXACT_REF"
        if self.lexical_rank is not None and self.semantic_rank is not None:
            return "HYBRID"
        if self.semantic_rank is not None:
            return "SEMANTIC"
        return "LEXICAL"

    def citation(self) -> dict[str, Any]:
        """The exact shape stored on responses and complaint_policy_refs."""
        return {
            "chunk_key": self.chunk_key,
            "doc_ref": self.doc_ref,
            "version": self.doc_version,
            "section_ref": self.section_ref,
            "heading": self.heading,
            "page_no": self.page_no,
            "paragraph_index": self.paragraph_index,
        }

    def as_prompt_context(self) -> str:
        """
        How this chunk appears inside a prompt.

        The identifier is stated up front so the model cites the token we can
        resolve, instead of inventing a plausible-looking reference.
        """
        location = ""
        if self.page_no:
            location = f", page {self.page_no}"
        elif self.paragraph_index:
            location = f", paragraph {self.paragraph_index}"
        header = (
            f"[{self.chunk_key}] {self.doc_ref} v{self.doc_version}"
            f" section {self.section_ref or 'n/a'}{location}"
        )
        # The header is ours; the text is the document's, and a document is
        # untrusted like a complaint (SRS Step 50). Fenced, an instruction
        # planted in a policy file reads as quoted policy, not as an order.
        from security.injection_defense import fence_document

        return f"{header}\n{fence_document(self.text)}"


@dataclass(slots=True)
class RetrievalResult:
    """Results plus the diagnostics the UI and the validator both need."""

    chunks: list[RetrievedChunk] = field(default_factory=list)
    query: str = ""
    lexical_count: int = 0
    semantic_count: int = 0
    exact_count: int = 0
    semantic_available: bool = False
    knowledge_base_empty: bool = False

    def __len__(self) -> int:
        return len(self.chunks)

    def __iter__(self):
        return iter(self.chunks)

    @property
    def chunk_keys(self) -> list[str]:
        return [c.chunk_key for c in self.chunks]

    @property
    def cited_documents(self) -> list[str]:
        seen: list[str] = []
        for chunk in self.chunks:
            ref = f"{chunk.doc_ref} v{chunk.doc_version}"
            if ref not in seen:
                seen.append(ref)
        return seen

    def as_prompt_context(self) -> str:
        return "\n\n---\n\n".join(c.as_prompt_context() for c in self.chunks)


# ══════════════════════════════════════════════════════════════
# base query
# ══════════════════════════════════════════════════════════════
def _active_chunk_query(
    *,
    include_superseded: bool,
    doc_refs: list[str] | None,
    department_id: Any | None,
):
    """
    Chunks joined to their version, restricted to what may be relied upon.

    The ACTIVE filter here is the enforcement point for "an outdated policy is
    never the basis of a resolution".
    """
    query = select(Chunk, DocumentVersion).join(
        DocumentVersion, Chunk.document_version_id == DocumentVersion.id
    )

    if include_superseded:
        query = query.where(
            DocumentVersion.status.in_([DocStatus.ACTIVE, DocStatus.SUPERSEDED])
        )
    else:
        query = query.where(DocumentVersion.status == DocStatus.ACTIVE)

    if doc_refs:
        query = query.where(Chunk.doc_ref.in_(doc_refs))
    if department_id is not None:
        from src.db.models import Document

        query = query.join(Document, DocumentVersion.document_id == Document.id).where(
            or_(Document.department_id == department_id, Document.department_id.is_(None))
        )
    return query


def _to_retrieved(chunk: Chunk) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk.id,
        chunk_key=chunk.chunk_key,
        text=chunk.text,
        doc_ref=chunk.doc_ref,
        doc_version=chunk.doc_version,
        section_ref=chunk.section_ref,
        heading=chunk.heading,
        page_no=chunk.page_no,
        paragraph_index=chunk.paragraph_index,
        document_version_id=chunk.document_version_id,
    )


# ══════════════════════════════════════════════════════════════
# lexical
# ══════════════════════════════════════════════════════════════
def _lexical_search(
    db: Session,
    query_text: str,
    *,
    depth: int,
    include_superseded: bool,
    doc_refs: list[str] | None,
    department_id: Any | None,
) -> list[Chunk]:
    base = _active_chunk_query(
        include_superseded=include_superseded, doc_refs=doc_refs, department_id=department_id
    )

    if settings.is_postgres:
        tsquery = func.websearch_to_tsquery("english", query_text)
        tsvector = func.to_tsvector("english", Chunk.text)
        ranked = (
            base.where(tsvector.op("@@")(tsquery))
            .order_by(func.ts_rank_cd(tsvector, tsquery).desc())
            .limit(depth)
        )
        rows = db.execute(ranked).all()
        if rows:
            return [row[0] for row in rows]
        # websearch_to_tsquery ANDs its terms, so a long natural-language
        # complaint often matches nothing. Fall through to term matching.

    return _term_match_search(
        db, query_text,
        depth=depth, include_superseded=include_superseded,
        doc_refs=doc_refs, department_id=department_id,
    )


_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "if", "then", "is", "are", "was", "were",
    "be", "been", "to", "of", "in", "on", "for", "with", "at", "by", "from", "as",
    "it", "its", "this", "that", "these", "those", "i", "my", "me", "we", "our",
    "you", "your", "they", "them", "their", "have", "has", "had", "do", "does",
    "did", "not", "no", "so", "very", "just", "about", "would", "will", "can",
}


def _keywords(text: str, *, limit: int = 12) -> list[str]:
    """Content words, longest first — the most distinctive terms lead."""
    words = [
        word.strip(".,;:!?\"'()[]").lower()
        for word in text.split()
    ]
    seen: set[str] = set()
    keywords: list[str] = []
    for word in sorted(words, key=len, reverse=True):
        if len(word) < 4 or word in _STOPWORDS or word in seen:
            continue
        seen.add(word)
        keywords.append(word)
        if len(keywords) >= limit:
            break
    return keywords


def _term_match_search(
    db: Session,
    query_text: str,
    *,
    depth: int,
    include_superseded: bool,
    doc_refs: list[str] | None,
    department_id: Any | None,
) -> list[Chunk]:
    """
    Portable keyword fallback, scored by how many distinct terms matched.

    Used on SQLite (no tsvector) and on PostgreSQL when the strict full-text
    query returns nothing.
    """
    terms = _keywords(query_text)
    if not terms:
        return []

    base = _active_chunk_query(
        include_superseded=include_superseded, doc_refs=doc_refs, department_id=department_id
    )
    conditions = [Chunk.text.ilike(f"%{term}%") for term in terms]

    # Score = number of matching terms, computed in SQL so the ranking survives
    # LIMIT rather than only ordering whatever rows happened to come back.
    #
    # CASE, not CAST: PostgreSQL refuses to cast boolean to a numeric type
    # ("cannot coerce type boolean to double precision"), while SQLite accepts
    # it silently - so a CAST here passes every test and fails in production.
    hit_score = sum(
        (case((condition, 1.0), else_=0.0) for condition in conditions),
        literal(0.0),
    )
    ranked = base.where(or_(*conditions)).order_by(hit_score.desc()).limit(depth)
    return [row[0] for row in db.execute(ranked).all()]


# ══════════════════════════════════════════════════════════════
# semantic
# ══════════════════════════════════════════════════════════════
def _semantic_search(
    db: Session,
    query_vector: list[float],
    *,
    depth: int,
    include_superseded: bool,
    doc_refs: list[str] | None,
    department_id: Any | None,
) -> list[Chunk]:
    base = _active_chunk_query(
        include_superseded=include_superseded, doc_refs=doc_refs, department_id=department_id
    ).where(Chunk.embedding.is_not(None))

    if settings.is_postgres:
        # pgvector's <=> is cosine distance; ascending = most similar first.
        ranked = base.order_by(Chunk.embedding.cosine_distance(query_vector)).limit(depth)
        return [row[0] for row in db.execute(ranked).all()]

    # SQLite stores vectors as JSON; rank in Python. Fine at corpus scale,
    # and it keeps the offline fallback semantically capable.
    rows = db.execute(base.options(undefer(Chunk.embedding))).all()
    scored = [
        (cosine_similarity(query_vector, row[0].embedding), row[0])
        for row in rows
    ]
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [chunk for _, chunk in scored[:depth]]


# ══════════════════════════════════════════════════════════════
# fusion
# ══════════════════════════════════════════════════════════════
def _reciprocal_rank_fusion(
    lexical: list[Chunk],
    semantic: list[Chunk],
    exact: list[Chunk],
    *,
    top_k: int,
) -> list[RetrievedChunk]:
    """
    Combine the ranked lists by rank alone.

    RRF is used rather than a weighted score blend because ts_rank_cd and
    cosine similarity are not on comparable scales, and any weight between them
    would be a number invented to look principled.

    The exception is the *exact reference* list.  When a query names a document
    by its identifier ("DEL-POL-04 section 5") that is not a fuzzy signal to be
    averaged with two fuzzy ones - it is the user telling us the answer.  Those
    hits get a flat bonus large enough to outrank any fused fuzzy pair, which
    is what makes a citation lookup return the cited document rather than a
    semantically similar one.
    """
    merged: dict[Any, RetrievedChunk] = {}

    for rank, chunk in enumerate(lexical, start=1):
        entry = merged.setdefault(chunk.id, _to_retrieved(chunk))
        entry.lexical_rank = rank
        entry.score += 1.0 / (RRF_K + rank)

    for rank, chunk in enumerate(semantic, start=1):
        entry = merged.setdefault(chunk.id, _to_retrieved(chunk))
        entry.semantic_rank = rank
        entry.score += 1.0 / (RRF_K + rank)

    for rank, chunk in enumerate(exact, start=1):
        entry = merged.setdefault(chunk.id, _to_retrieved(chunk))
        entry.exact_rank = rank
        entry.score += EXACT_REFERENCE_BONUS / rank

    ordered = sorted(merged.values(), key=lambda c: c.score, reverse=True)
    return ordered[:top_k]


# A document identifier in a query ("DEL-POL-04", "SAF-POL-02 5.2").
_DOC_REF_PATTERN = re.compile(r"\b([A-Z]{2,6}(?:-[A-Z0-9]{1,6}){1,3})\b")
_SECTION_PATTERN = re.compile(
    r"(?:section|clause|§|s\.)\s*(\d+(?:\.\d+){0,3})|\b(\d+\.\d+(?:\.\d+)?)\b",
    re.IGNORECASE,
)


def parse_references(query_text: str) -> tuple[list[str], list[str]]:
    """Pull explicit document and section references out of a query."""
    upper = query_text.upper()
    doc_refs = [match.group(1) for match in _DOC_REF_PATTERN.finditer(upper)]

    sections: list[str] = []
    for match in _SECTION_PATTERN.finditer(query_text):
        value = match.group(1) or match.group(2)
        if value and value not in sections:
            sections.append(value)
    return doc_refs, sections


def _exact_reference_search(
    db: Session,
    query_text: str,
    *,
    include_superseded: bool,
    depth: int,
) -> list[Chunk]:
    """
    Find chunks a query names outright.

    Returns nothing for ordinary natural-language complaints, which is the
    point: this retriever only fires when the user supplied an identifier.
    """
    doc_refs, sections = parse_references(query_text)
    if not doc_refs:
        return []

    base = _active_chunk_query(
        include_superseded=include_superseded, doc_refs=doc_refs, department_id=None
    )
    if sections:
        # Match the named section and its subsections ("5" also matches "5.2").
        section_filters = [Chunk.section_ref == value for value in sections]
        section_filters += [Chunk.section_ref.like(f"{value}.%") for value in sections]
        base = base.where(or_(*section_filters))

    rows = db.execute(base.order_by(Chunk.ordinal).limit(depth)).all()
    return [row[0] for row in rows]


# ══════════════════════════════════════════════════════════════
# public API
# ══════════════════════════════════════════════════════════════
def retrieve(
    db: Session,
    query_text: str,
    *,
    top_k: int | None = None,
    include_superseded: bool = False,
    doc_refs: list[str] | None = None,
    department_id: Any | None = None,
    semantic: bool = True,
) -> RetrievalResult:
    """
    Retrieve the policy passages most relevant to ``query_text``.

    Never raises on an empty knowledge base, an unavailable embedding provider
    or a query that matches nothing — the caller inspects the result instead.
    """
    top_k = top_k or settings.retrieval_top_k
    depth = max(MIN_CANDIDATE_DEPTH, top_k * CANDIDATE_DEPTH_MULTIPLIER)

    result = RetrievalResult(query=query_text)

    if not query_text or not query_text.strip():
        return result

    total_active = db.execute(
        select(func.count())
        .select_from(DocumentVersion)
        .where(DocumentVersion.status == DocStatus.ACTIVE)
    ).scalar_one()
    if not total_active:
        result.knowledge_base_empty = True
        log.warning("retrieval_on_empty_kb", query=query_text[:80])
        return result

    # The query embedding is a network round trip to the embedding provider
    # and touches no database state, so it runs while the lexical search does
    # rather than after it. A session is not thread-safe; an HTTP call is.
    pending_vector = _EMBED_POOL.submit(embed_query, query_text) if semantic else None

    lexical = _lexical_search(
        db, query_text,
        depth=depth, include_superseded=include_superseded,
        doc_refs=doc_refs, department_id=department_id,
    )
    result.lexical_count = len(lexical)

    semantic_hits: list[Chunk] = []
    if pending_vector is not None:
        try:
            query_vector = pending_vector.result()
        except Exception as exc:  # noqa: BLE001 - degrade to lexical, never fail
            log.warning("embedding_failed", error=type(exc).__name__)
            query_vector = None
        if query_vector:
            result.semantic_available = True
            semantic_hits = _semantic_search(
                db, query_vector,
                depth=depth, include_superseded=include_superseded,
                doc_refs=doc_refs, department_id=department_id,
            )
            result.semantic_count = len(semantic_hits)

    exact_hits = _exact_reference_search(
        db, query_text, include_superseded=include_superseded, depth=depth
    )
    result.exact_count = len(exact_hits)

    result.chunks = _reciprocal_rank_fusion(
        lexical, semantic_hits, exact_hits, top_k=top_k
    )

    log.info(
        "retrieved",
        query=query_text[:60],
        lexical=result.lexical_count,
        semantic=result.semantic_count,
        exact=result.exact_count,
        returned=len(result.chunks),
        mode="hybrid" if result.semantic_available else "lexical_only",
    )
    return result


def resolve_citation(
    db: Session,
    *,
    chunk_key: str | None = None,
    doc_ref: str | None = None,
    section_ref: str | None = None,
) -> Chunk | None:
    """
    Resolve a citation the model produced back to a real chunk.

    Returning ``None`` is the signal that a reference was hallucinated, so this
    is the primitive the citation validator is built on.  Superseded versions
    are searched too: a citation to an outdated policy is a *different* problem
    from an invented one, and the two must not be conflated.
    """
    if chunk_key:
        chunk = db.execute(
            select(Chunk).where(Chunk.chunk_key == chunk_key)
        ).scalars().first()
        if chunk:
            return chunk

    if not doc_ref:
        return None

    query = select(Chunk).where(Chunk.doc_ref == str(doc_ref).strip().upper())
    if section_ref:
        # Coerced, not assumed. A section ref of "1" round-trips through
        # YAML as an integer, and a resolver that trusts its caller's type
        # turns a configuration detail into a crash.
        query = query.where(Chunk.section_ref == str(section_ref).strip())

    # Prefer the active version when several versions carry the same section.
    query = query.join(
        DocumentVersion, Chunk.document_version_id == DocumentVersion.id
    ).order_by(
        (DocumentVersion.status == DocStatus.ACTIVE).desc(),
        Chunk.ordinal.asc(),
    )
    return db.execute(query).scalars().first()


def sections_for_document(
    db: Session, doc_ref: str, *, active_only: bool = True
) -> list[Chunk]:
    """Every chunk of one document, in reading order."""
    query = (
        select(Chunk)
        .join(DocumentVersion, Chunk.document_version_id == DocumentVersion.id)
        .where(Chunk.doc_ref == str(doc_ref).strip().upper())
    )
    if active_only:
        query = query.where(DocumentVersion.status == DocStatus.ACTIVE)
    return list(db.execute(query.order_by(Chunk.ordinal)).scalars())


def coverage_stats(db: Session) -> dict[str, int]:
    """Corpus health, surfaced on the admin dashboard and in /health."""
    active_versions = db.execute(
        select(func.count())
        .select_from(DocumentVersion)
        .where(DocumentVersion.status == DocStatus.ACTIVE)
    ).scalar_one()

    total_chunks = db.execute(
        select(func.count())
        .select_from(Chunk)
        .join(DocumentVersion, Chunk.document_version_id == DocumentVersion.id)
        .where(DocumentVersion.status == DocStatus.ACTIVE)
    ).scalar_one()

    embedded_chunks = db.execute(
        select(func.count())
        .select_from(Chunk)
        .join(DocumentVersion, Chunk.document_version_id == DocumentVersion.id)
        .where(and_(DocumentVersion.status == DocStatus.ACTIVE, Chunk.embedding.is_not(None)))
    ).scalar_one()

    return {
        "active_documents": active_versions,
        "chunks": total_chunks,
        "embedded_chunks": embedded_chunks,
        "unembedded_chunks": total_chunks - embedded_chunks,
    }
