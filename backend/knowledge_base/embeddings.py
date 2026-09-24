"""
Embeddings for the semantic half of hybrid retrieval.

Design stance: **embeddings are an enhancement, never a dependency.**

Retrieval is lexical (PostgreSQL full-text + trigram) *plus* semantic.  If the
embedding provider is unconfigured, rate-limited or unreachable, this module
returns ``None`` for every vector, the chunks are stored without one, and
retrieval silently falls back to lexical-only.  Nothing raises, nothing blocks,
and a document ingested during an outage can be re-embedded later with
``backfill_embeddings``.

That matters for two reasons the SRS cares about:

* NFR 5 — the application must stay available "excluding external GenAI API
  outages", and an ingestion path that hard-fails on an embedding call would
  make the knowledge base unusable during one;
* SRS 1.8 #18 — the GenAI API must not replace core logic.  Retrieval that
  cannot work without a hosted model would put a provider in the critical path
  of policy lookup.

Gemini's embedding endpoint is used because it is on the same free tier as the
generation model, so there is no second account to provision, and because
running a local sentence-transformer would add roughly 800 MB of PyTorch to a
512 MB instance.
"""

from __future__ import annotations

import hashlib
import math
from functools import lru_cache

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.config import settings
from src.core.logging import get_logger

log = get_logger("knowledge_base.embeddings")

# Gemini accepts batched contents; keep batches modest to stay inside
# free-tier request-size limits.
BATCH_SIZE = 32
MAX_CHARS_PER_TEXT = 8000

# Embedding a query and embedding a document are different tasks and the API
# scores them better when told which is which.
TASK_DOCUMENT = "RETRIEVAL_DOCUMENT"
TASK_QUERY = "RETRIEVAL_QUERY"


class EmbeddingUnavailable(Exception):
    """Raised internally only; callers receive ``None`` vectors instead."""


@lru_cache(maxsize=1)
def _client():
    """Create the Gemini client once, or signal that embeddings are off."""
    if not settings.embedding_enabled:
        raise EmbeddingUnavailable("embeddings disabled by configuration")
    if not settings.gemini_api_key:
        raise EmbeddingUnavailable("GEMINI_API_KEY is not configured")
    try:
        from google import genai
    except ImportError as exc:  # pragma: no cover
        raise EmbeddingUnavailable("google-genai is not installed") from exc
    return genai.Client(api_key=settings.gemini_api_key)


def is_available() -> bool:
    """Whether semantic retrieval can currently contribute."""
    try:
        _client()
        return True
    except EmbeddingUnavailable:
        return False


def _truncate(text: str) -> str:
    cleaned = " ".join(text.split())
    return cleaned[:MAX_CHARS_PER_TEXT]


def _normalise(vector: list[float] | None) -> list[float] | None:
    """
    Scale a vector to unit length.

    ``gemini-embedding-001`` only returns normalised vectors at its native 3072
    dimensions.  Reduced-dimension output (we request 768 to match the pgvector
    column) comes back unnormalised — measured L2 of ~0.59 — and Google's
    documentation requires the caller to normalise it.

    Cosine distance is scale-invariant so retrieval ranking would survive
    without this, but unit vectors make cosine equal to the dot product, keep
    similarity scores comparable across batches, and leave the door open to an
    inner-product index later.
    """
    if not vector:
        return None
    magnitude = math.sqrt(sum(value * value for value in vector))
    if magnitude == 0.0:
        return None
    return [value / magnitude for value in vector]


def _extract_vectors(response, expected: int) -> list[list[float] | None]:
    """
    Pull vectors out of the SDK response shape.

    Written defensively: the google-genai response object has changed shape
    across releases, and an ingestion run must not die because an attribute was
    renamed upstream.
    """
    raw = getattr(response, "embeddings", None)
    if raw is None:
        raw = getattr(response, "embedding", None)
        if raw is not None:
            raw = [raw]
    if not raw:
        return [None] * expected

    vectors: list[list[float] | None] = []
    for item in raw:
        values = getattr(item, "values", None)
        if values is None and isinstance(item, dict):
            values = item.get("values")
        if values is None and isinstance(item, list):
            values = item
        vectors.append([float(v) for v in values] if values else None)

    while len(vectors) < expected:
        vectors.append(None)
    return vectors[:expected]


def embed_texts(
    texts: list[str], *, task_type: str = TASK_DOCUMENT
) -> list[list[float] | None]:
    """
    Embed a list of texts.  Always returns one entry per input; a failed batch
    yields ``None`` entries rather than an exception.
    """
    if not texts:
        return []

    try:
        client = _client()
    except EmbeddingUnavailable as exc:
        log.info("embeddings_unavailable", reason=str(exc), count=len(texts))
        return [None] * len(texts)

    prepared = [_truncate(t) for t in texts]
    vectors: list[list[float] | None] = []

    for start in range(0, len(prepared), BATCH_SIZE):
        batch = prepared[start : start + BATCH_SIZE]
        try:
            response = client.models.embed_content(
                model=settings.gemini_embed_model,
                contents=batch,
                config={
                    "task_type": task_type,
                    # gemini-embedding-001 returns 3072 dimensions by default.
                    # The pgvector column is fixed-width, so the reduction is
                    # requested explicitly rather than truncated afterwards.
                    "output_dimensionality": settings.embedding_dim,
                },
            )
            batch_vectors = [_normalise(v) for v in _extract_vectors(response, len(batch))]
        except Exception as exc:
            # Includes quota exhaustion, which is expected on a free tier.
            log.warning(
                "embedding_batch_failed",
                error=f"{type(exc).__name__}: {exc}"[:200],
                batch_size=len(batch),
            )
            batch_vectors = [None] * len(batch)
        vectors.extend(batch_vectors)

    produced = sum(1 for v in vectors if v)
    if produced:
        log.info("embedded", requested=len(texts), produced=produced, dim=len(vectors[0] or []))
    return vectors


def embed_query(text: str) -> list[float] | None:
    """Embed a single search query. ``None`` means 'fall back to lexical'."""
    if not text.strip():
        return None
    return embed_texts([text], task_type=TASK_QUERY)[0]


def verify_dimension(vector: list[float] | None) -> bool:
    """
    Guard against a model change silently producing the wrong width.

    A vector whose length does not match ``EMBEDDING_DIM`` cannot be stored in
    the pgvector column, and a mismatch would otherwise surface as an opaque
    database error halfway through an ingestion run.
    """
    return vector is not None and len(vector) == settings.embedding_dim


def cosine_similarity(a: list[float] | None, b: list[float] | None) -> float:
    """Pure-Python cosine, used on SQLite where pgvector is unavailable."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def text_fingerprint(text: str) -> str:
    return hashlib.sha256(_truncate(text).encode("utf-8")).hexdigest()


def backfill_embeddings(db: Session, *, limit: int = 500) -> dict[str, int]:
    """
    Embed chunks that have no vector yet.

    Run after an ingestion that happened while the provider was unavailable, or
    after changing the embedding model.  Idempotent and resumable.
    """
    from src.db.models import Chunk

    pending = db.execute(
        select(Chunk).where(Chunk.embedding.is_(None)).limit(limit)
    ).scalars().all()

    if not pending:
        return {"pending": 0, "embedded": 0, "skipped": 0}

    vectors = embed_texts([chunk.text for chunk in pending])
    embedded = skipped = 0
    for chunk, vector in zip(pending, vectors, strict=False):
        if verify_dimension(vector):
            chunk.embedding = vector
            embedded += 1
        else:
            skipped += 1

    db.flush()
    log.info("backfill_complete", pending=len(pending), embedded=embedded, skipped=skipped)
    return {"pending": len(pending), "embedded": embedded, "skipped": skipped}
