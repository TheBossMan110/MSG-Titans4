"""
Dialect portability guards.

The suite runs against SQLite so it stays fast and offline, but production is
Supabase PostgreSQL.  Two bugs slipped through that gap during development and
only surfaced on the real database:

* ``CAST(boolean AS FLOAT)`` in the lexical fallback ranking — accepted
  silently by SQLite, rejected by PostgreSQL with "cannot coerce type boolean
  to double precision";
* ``Chunk.embedding.cosine_distance(...)`` — our ``Vector`` TypeDecorator wraps
  pgvector and hid its comparator, so the attribute did not exist at all.

These tests compile the real queries against the PostgreSQL dialect without
needing a connection.  That catches anything resolved at query-build or
render time.

**Limit, stated plainly:** compilation does not execute, so a *runtime* type
coercion error can still get past this.  The genuine guarantee comes from
running the suite with ``DATABASE_URL`` pointed at Postgres, which is what CI
should do before submission.  These tests are a fast first line, not a
substitute for that.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from src.db.models import Chunk, Complaint, DocumentVersion

PG = postgresql.dialect()


def _compiles(statement) -> str:
    """Render a statement as PostgreSQL SQL, or fail loudly."""
    return str(statement.compile(dialect=PG, compile_kwargs={"literal_binds": False}))


@pytest.mark.unit
def test_pgvector_distance_operators_are_available():
    """
    Regression guard: wrapping pgvector in a TypeDecorator removed its
    comparator, so ordering by similarity raised AttributeError on Postgres
    while every SQLite test passed.
    """
    vector = [0.1] * 768
    for operator, symbol in (
        ("cosine_distance", "<=>"),
        ("l2_distance", "<->"),
        ("max_inner_product", "<#>"),
    ):
        expression = getattr(Chunk.embedding, operator)(vector)
        sql = _compiles(select(Chunk).order_by(expression))
        assert symbol in sql, f"{operator} did not render the {symbol} operator"


@pytest.mark.unit
def test_lexical_fallback_ranking_compiles_for_postgres():
    """
    Regression guard: the term-match ranking used CAST(bool AS FLOAT), which
    PostgreSQL refuses.  It must render as CASE instead.
    """
    from sqlalchemy import case, literal, or_

    from knowledge_base.retrieval import _active_chunk_query

    terms = ["refund", "delivery", "escalation"]
    conditions = [Chunk.text.ilike(f"%{t}%") for t in terms]
    hit_score = sum((case((c, 1.0), else_=0.0) for c in conditions), literal(0.0))

    query = (
        _active_chunk_query(include_superseded=False, doc_refs=None, department_id=None)
        .where(or_(*conditions))
        .order_by(hit_score.desc())
    )
    sql = _compiles(query).upper()
    assert "CASE" in sql
    assert "CAST(CHUNKS.TEXT ILIKE" not in sql, "boolean must never be CAST to a number"


@pytest.mark.unit
def test_retrieval_queries_compile_for_postgres():
    """Every query shape the retrieval module builds must render on Postgres."""
    from knowledge_base.retrieval import _active_chunk_query

    for include_superseded in (False, True):
        query = _active_chunk_query(
            include_superseded=include_superseded,
            doc_refs=["DEL-POL-04"],
            department_id=None,
        )
        assert "document_versions" in _compiles(query)


@pytest.mark.unit
def test_jsonb_columns_render_as_jsonb_on_postgres():
    """
    JSONType must become JSONB on PostgreSQL. Plain `json` cannot be indexed
    with GIN the way the query paths assume.
    """
    from src.db.models import Rule, ValidationRun

    for column in (Rule.conditions, ValidationRun.signals, Complaint.missing_information):
        rendered = column.type.compile(dialect=PG).upper()
        assert rendered == "JSONB", f"{column} rendered as {rendered}, expected JSONB"


@pytest.mark.unit
def test_vector_column_renders_as_vector_on_postgres():
    rendered = Chunk.embedding.type.compile(dialect=PG).upper()
    assert rendered.startswith("VECTOR"), f"embedding rendered as {rendered}"


@pytest.mark.unit
def test_bigint_primary_keys_render_correctly_per_dialect():
    """
    SQLite only auto-increments an INTEGER PRIMARY KEY; PostgreSQL wants
    BIGINT. The variant must resolve differently per dialect.
    """
    from sqlalchemy.dialects import sqlite

    from src.db.models import AuditLog

    assert AuditLog.id.type.compile(dialect=PG).upper() == "BIGINT"
    assert AuditLog.id.type.compile(dialect=sqlite.dialect()).upper() == "INTEGER"


@pytest.mark.unit
def test_timestamps_are_timezone_aware_on_postgres():
    rendered = DocumentVersion.created_at.type.compile(dialect=PG).upper()
    assert "TIME ZONE" in rendered, f"created_at rendered as {rendered}"
