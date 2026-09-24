"""
SQLAlchemy 2.0 declarative base, engine and session factory.

Design notes
------------
* **Sync** SQLAlchemy on purpose.  FastAPI runs ``def`` endpoints in a
  threadpool; concurrency for LLM calls comes from a ThreadPoolExecutor in the
  batch runner.  This avoids the async/greenlet failure modes that cost
  hackathon teams entire afternoons, at no practical throughput cost here.
* All column types are **dialect-portable** so ``DATABASE_URL`` can be swapped
  from Supabase Postgres to a local SQLite file for the offline demo fallback.
"""

from __future__ import annotations

import uuid
from collections.abc import Generator
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    Float,
    Integer,
    MetaData,
    String,
    TypeDecorator,
    create_engine,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from src.core.config import settings

# Predictable constraint names -> clean Alembic autogenerate diffs.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


# ── portable column types ────────────────────────────────────
JSONType = JSONB().with_variant(JSON(), "sqlite")


class Vector(TypeDecorator):
    """
    pgvector column on Postgres, JSON list of floats everywhere else.

    Wrapping pgvector in a ``TypeDecorator`` is what makes the SQLite fallback
    possible, but it hides pgvector's comparator, so ``column.cosine_distance``
    would not exist.  ``comparator_factory`` re-exposes the three distance
    operators, which is how ORDER BY on similarity stays expressible without
    dropping to raw SQL.
    """

    impl = JSON
    cache_ok = True

    class comparator_factory(TypeDecorator.Comparator):  # noqa: N801 - SQLAlchemy API
        """pgvector distance operators. PostgreSQL only."""

        def cosine_distance(self, other):
            return self.op("<=>", return_type=Float)(other)

        def l2_distance(self, other):
            return self.op("<->", return_type=Float)(other)

        def max_inner_product(self, other):
            return self.op("<#>", return_type=Float)(other)

    def __init__(self, dim: int = 768):
        self.dim = dim
        super().__init__()

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            from pgvector.sqlalchemy import Vector as PGVector

            return dialect.type_descriptor(PGVector(self.dim))
        return dialect.type_descriptor(JSON())

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if dialect.name == "postgresql":
            return value
        return list(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return list(value)


class TZDateTime(TypeDecorator):
    """Always store & return timezone-aware UTC datetimes (SQLite drops tzinfo)."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_result_value(self, value, dialect):
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value


def utcnow() -> datetime:
    return datetime.now(UTC)


# ── declarative base ─────────────────────────────────────────
class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map = {dict[str, Any]: JSONType, list[Any]: JSONType}


class UUIDPrimaryKey:
    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, sort_order=-100
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        TZDateTime, server_default=func.now(), default=utcnow, nullable=False, sort_order=100
    )


class UpdatedAtMixin:
    updated_at: Mapped[datetime] = mapped_column(
        TZDateTime,
        server_default=func.now(),
        default=utcnow,
        onupdate=utcnow,
        nullable=False,
        sort_order=101,
    )


# SQLite only auto-increments an INTEGER PRIMARY KEY - a BIGINT PK silently
# loses autoincrement and every insert fails on a NOT NULL id.  This variant
# keeps BIGINT on Postgres and degrades to INTEGER on SQLite.
BigIntPK = BigInteger().with_variant(Integer(), "sqlite")

# Short reusable string columns
Code = String(64)
Name = String(255)
Ref = String(64)


# ── engine / session ─────────────────────────────────────────
def _engine_kwargs() -> dict[str, Any]:
    if settings.is_postgres:
        return {
            "pool_size": settings.db_pool_size,
            "max_overflow": settings.db_max_overflow,
            "pool_pre_ping": True,
            "pool_recycle": 1800,
            "echo": settings.db_echo,
        }
    # SQLite offline fallback
    return {"connect_args": {"check_same_thread": False}, "echo": settings.db_echo}


engine = create_engine(settings.database_url, future=True, **_engine_kwargs())
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: one transactional session per request."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def session_scope() -> Session:
    """For background jobs and CLI scripts (caller manages commit/close)."""
    return SessionLocal()
