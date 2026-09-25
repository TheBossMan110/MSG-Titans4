"""
Knowledge base: documents -> versions -> sections -> chunks.

FR vi   Knowledge-Base Upload        SRS Step 3  (PDF + DOCX mandatory)
FR vii  Document Validation          SRS Step 4
FR viii Document Parsing             SRS Step 5
FR ix   Document Chunking            SRS Step 6
FR x    Document Version Control     SRS Step 7
FR l    Policy Traceability          SRS Step 25

Every chunk carries the exact coordinates a judge can ask for during the
Source-Traceability Challenge: doc_ref, version, section_ref, page number
(PDF) and paragraph index (DOCX).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.config import settings
from src.db.base import Base, Code, Name, Ref, TimestampMixin, TZDateTime, UUIDPrimaryKey, Vector
from src.db.constraints import enum_check
from src.db.enums import DocStatus, DocType, FileFormat, ParseStatus

ACTIVE_PREDICATE = text("status = 'ACTIVE'")


class Document(UUIDPrimaryKey, TimestampMixin, Base):
    """A policy *family* — the logical document across all of its versions."""

    __tablename__ = "documents"
    __table_args__ = (enum_check("doc_type", DocType),)

    family_key: Mapped[str] = mapped_column(Code, nullable=False, unique=True)  # e.g. DEL-POL
    title: Mapped[str] = mapped_column(Name, nullable=False)
    doc_type: Mapped[str] = mapped_column(String(32), nullable=False, default=DocType.POLICY)
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL")
    )
    description: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

    versions = relationship(
        "DocumentVersion",
        back_populates="document",
        cascade="all, delete-orphan",
        foreign_keys="DocumentVersion.document_id",
        order_by="DocumentVersion.created_at.desc()",
    )


class DocumentVersion(UUIDPrimaryKey, TimestampMixin, Base):
    """
    One uploaded file = one version.

    The partial unique index ``ux_docver_one_active`` makes "at most one ACTIVE
    version per document" a *database guarantee*, not a code convention — which
    is how we can promise that an outdated policy is never used as the primary
    basis for a resolution (SRS Step 7).
    """

    __tablename__ = "document_versions"
    __table_args__ = (
        UniqueConstraint("document_id", "version", name="uq_docver_document_version"),
        UniqueConstraint("file_hash", name="uq_docver_file_hash"),
        Index(
            "ux_docver_one_active",
            "document_id",
            unique=True,
            postgresql_where=ACTIVE_PREDICATE,
            sqlite_where=ACTIVE_PREDICATE,
        ),
        Index("ix_docver_ref_version", "doc_ref", "version"),
        enum_check("status", DocStatus),
        enum_check("file_format", FileFormat),
        enum_check("parse_status", ParseStatus),
    )

    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    doc_ref: Mapped[str] = mapped_column(Ref, nullable=False, index=True)  # e.g. DEL-POL-04
    version: Mapped[str] = mapped_column(String(32), nullable=False)       # e.g. 2.1
    title: Mapped[str | None] = mapped_column(Name)

    effective_date: Mapped[date | None] = mapped_column(Date)
    expiry_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=DocStatus.DRAFT)

    file_format: Mapped[str] = mapped_column(String(8), nullable=False)
    file_name: Mapped[str] = mapped_column(String(512), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger)

    page_count: Mapped[int | None] = mapped_column(Integer)
    section_count: Mapped[int | None] = mapped_column(Integer)
    chunk_count: Mapped[int | None] = mapped_column(Integer)

    parse_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=ParseStatus.PENDING
    )
    parse_error: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column()
    # False when a hidden/unknown document did not carry our metadata block.
    metadata_complete: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    activated_at: Mapped[datetime | None] = mapped_column(TZDateTime)
    superseded_at: Mapped[datetime | None] = mapped_column(TZDateTime)
    superseded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("document_versions.id", ondelete="SET NULL")
    )

    document = relationship("Document", back_populates="versions", foreign_keys=[document_id])
    sections = relationship(
        "DocumentSection", back_populates="document_version", cascade="all, delete-orphan"
    )
    chunks = relationship("Chunk", back_populates="document_version", cascade="all, delete-orphan")

    @property
    def citation(self) -> str:
        return f"{self.doc_ref} v{self.version}"


class DocumentSection(UUIDPrimaryKey, TimestampMixin, Base):
    """A numbered/headed section — the unit a policy reference points at."""

    __tablename__ = "document_sections"
    __table_args__ = (
        UniqueConstraint("document_version_id", "section_ref", name="uq_section_docver_ref"),
    )

    document_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    section_ref: Mapped[str] = mapped_column(String(64), nullable=False)  # e.g. 5.2
    heading: Mapped[str | None] = mapped_column(Name)
    level: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    page_no: Mapped[int | None] = mapped_column(Integer)          # PDF location
    paragraph_index: Mapped[int | None] = mapped_column(Integer)  # DOCX location
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    text: Mapped[str] = mapped_column(Text, nullable=False)

    document_version = relationship("DocumentVersion", back_populates="sections")


class Chunk(UUIDPrimaryKey, TimestampMixin, Base):
    """
    Retrieval unit.  ``chunk_key`` (e.g. ``DEL-POL-04::5.2::c1``) is the token
    the GenAI pipeline must cite and the validation pipeline resolves back to
    an ACTIVE document version.
    """

    __tablename__ = "chunks"
    __table_args__ = (
        UniqueConstraint("document_version_id", "chunk_key", name="uq_chunk_docver_key"),
        Index("ix_chunks_docver_ordinal", "document_version_id", "ordinal"),
    )

    document_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_versions.id", ondelete="CASCADE"), nullable=False
    )
    section_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("document_sections.id", ondelete="CASCADE")
    )
    chunk_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    # Denormalised traceability - avoids three joins on every retrieval result.
    doc_ref: Mapped[str] = mapped_column(Ref, nullable=False, index=True)
    doc_version: Mapped[str] = mapped_column(String(32), nullable=False)
    section_ref: Mapped[str | None] = mapped_column(String(64))
    heading: Mapped[str | None] = mapped_column(Name)
    page_no: Mapped[int | None] = mapped_column(Integer)
    paragraph_index: Mapped[int | None] = mapped_column(Integer)

    ordinal: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int | None] = mapped_column(Integer)
    # Deferred: ~3 KB per row that only the database's own similarity ranking
    # reads. Loading it with every retrieved passage made each policy search
    # ship megabytes over the wire to throw them away -- measured at 10-24 s of
    # a 30 s intake against the hosted database. Code that does need the
    # vector (SQLite ranking, re-embedding) asks for it with ``undefer``.
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(settings.embedding_dim), deferred=True
    )

    document_version = relationship("DocumentVersion", back_populates="chunks")

    def as_citation(self) -> dict[str, Any]:
        return {
            "chunk_key": self.chunk_key,
            "doc_ref": self.doc_ref,
            "version": self.doc_version,
            "section_ref": self.section_ref,
            "heading": self.heading,
            "page_no": self.page_no,
            "paragraph_index": self.paragraph_index,
        }
