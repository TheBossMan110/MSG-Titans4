"""
Customers and complaints.

Key modelling decision
----------------------
A **customer** is *a record about the person who complained*.
A **user** is *someone who logs into the system*.
They are separate tables, and ``Customer.user_id`` is NULLABLE, because most
complaints are filed on a customer's behalf (phone, email, import) by someone
who has an account when the customer does not.

FR iii  Complaint Submission     SRS Step 9
FR iv   Complaint Validation     SRS Step 10
FR v    Complaint Pre-processing SRS Step 11
FR lvi  Duplicate Detection      SRS Step 52
FR lvii Complaint History        SRS Step 53
FR lviii Repeat Detection        SRS Step 54
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import (
    Base,
    BigIntPK,
    Code,
    Name,
    Ref,
    TimestampMixin,
    TZDateTime,
    UUIDPrimaryKey,
)
from src.db.constraints import enum_check
from src.db.enums import (
    Channel,
    ComplaintStatus,
    CustomerTier,
    EntityExtractor,
    LinkType,
    Sentiment,
    Urgency,
    VerificationOutcome,
)


class Customer(UUIDPrimaryKey, TimestampMixin, Base):
    """Synthetic only — SRS Step 1 forbids real customer confidential data."""

    __tablename__ = "customers"
    __table_args__ = (enum_check("tier", CustomerTier),)

    external_ref: Mapped[str] = mapped_column(Ref, nullable=False, unique=True)  # CUST-00184
    display_name: Mapped[str] = mapped_column(Name, nullable=False)
    email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(64))
    tier: Mapped[str] = mapped_column(String(16), nullable=False, default=CustomerTier.STANDARD)
    region: Mapped[str | None] = mapped_column(String(128))
    # Nullable on purpose - see module docstring.
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    complaints = relationship("Complaint", back_populates="customer")


class Complaint(UUIDPrimaryKey, TimestampMixin, Base):
    """
    The central record.

    The classification columns hold the **reconciled** result (what the system
    finally decided), not the raw GenAI output.  The raw model output lives in
    ``genai_runs``, the independent Python result lives in ``validation_runs``,
    and the field-by-field difference lives in ``comparisons`` — so no number
    displayed in the UI is ever unsourced (SRS 1.8 #17, No Hard-Coded Outputs).
    """

    __tablename__ = "complaints"
    __table_args__ = (
        Index("ix_comp_status_created", "status", "created_at"),
        Index("ix_comp_queue", "department_id", "priority_code", "created_at"),
        Index("ix_comp_assigned", "assigned_to", "status"),
        Index("ix_comp_customer", "customer_id", "created_at"),
        Index("ix_comp_dataset", "dataset_tag"),
        CheckConstraint("id <> previous_complaint_id", name="no_self_reference"),
        enum_check("status", ComplaintStatus),
        enum_check("channel", Channel),
        enum_check("sentiment", Sentiment),
        enum_check("urgency", Urgency),
        enum_check("verification_outcome", VerificationOutcome),
    )

    public_ref: Mapped[str] = mapped_column(Ref, nullable=False, unique=True)  # CMP-00421
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("customers.id", ondelete="SET NULL")
    )
    submitted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

    # ── raw input ───────────────────────────────────────────
    title: Mapped[str] = mapped_column(Name, nullable=False)
    description_raw: Mapped[str] = mapped_column(Text, nullable=False)   # exactly as received
    description_clean: Mapped[str] = mapped_column(Text, nullable=False)  # normalised/sanitised
    product: Mapped[str | None] = mapped_column(Name)
    order_ref: Mapped[str | None] = mapped_column(String(64), index=True)
    transaction_ref: Mapped[str | None] = mapped_column(String(64))
    amount: Mapped[float | None] = mapped_column(Numeric(12, 2))
    currency: Mapped[str | None] = mapped_column(String(8))
    channel: Mapped[str] = mapped_column(String(16), nullable=False, default=Channel.WEB)
    customer_type: Mapped[str | None] = mapped_column(String(32))
    preferred_contact: Mapped[str | None] = mapped_column(String(32))
    requested_resolution: Mapped[str | None] = mapped_column(Text)
    previous_complaint_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("complaints.id", ondelete="SET NULL")
    )

    # ── reconciled classification ───────────────────────────
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=ComplaintStatus.NEW, index=True
    )
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL")
    )
    subcategory_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("subcategories.id", ondelete="SET NULL")
    )
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL")
    )
    support_department_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL")
    )
    urgency: Mapped[str | None] = mapped_column(String(16))
    priority_code: Mapped[str | None] = mapped_column(
        ForeignKey("priority_levels.code", ondelete="SET NULL")
    )
    escalation_code: Mapped[str | None] = mapped_column(
        ForeignKey("escalation_levels.code", ondelete="SET NULL")
    )
    sentiment: Mapped[str | None] = mapped_column(String(24))
    verification_outcome: Mapped[str | None] = mapped_column(String(32), index=True)

    primary_issue: Mapped[str | None] = mapped_column(Name)
    secondary_issue: Mapped[str | None] = mapped_column(Name)  # SRS Step 13
    # FR xli / SRS Step 44 - concise structured summary for the agent.
    summary: Mapped[str | None] = mapped_column(Text)
    # SRS Step 18 - emotion/tone indicators. ANALYTICS ONLY: these must never
    # influence urgency or priority (that is the trap in SRS 1.8 #6).
    emotion_indicators: Mapped[list[Any]] = mapped_column(nullable=False, default=list)

    # ── flags ───────────────────────────────────────────────
    injection_suspected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_duplicate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    repeat_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    missing_information: Mapped[list[Any]] = mapped_column(nullable=False, default=list)
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

    # ── benchmark ground-truth labels ───────────────────────
    # Authored as part of the 500-complaint dataset.  NEVER read by either
    # pipeline - only by the benchmark comparator (tests assert this).
    expected_category_code: Mapped[str | None] = mapped_column(Code)
    expected_subcategory_code: Mapped[str | None] = mapped_column(Code)
    expected_department_code: Mapped[str | None] = mapped_column(Code)
    expected_urgency: Mapped[str | None] = mapped_column(String(16))
    expected_priority_code: Mapped[str | None] = mapped_column(String(8))
    expected_escalation_code: Mapped[str | None] = mapped_column(Code)
    dataset_tag: Mapped[str | None] = mapped_column(Code)  # SEED_500 / ADVERSARIAL / HIDDEN

    # ── lifecycle timestamps ────────────────────────────────
    analyzed_at: Mapped[datetime | None] = mapped_column(TZDateTime)
    validated_at: Mapped[datetime | None] = mapped_column(TZDateTime)
    first_response_at: Mapped[datetime | None] = mapped_column(TZDateTime)
    resolved_at: Mapped[datetime | None] = mapped_column(TZDateTime)
    closed_at: Mapped[datetime | None] = mapped_column(TZDateTime)

    customer = relationship("Customer", back_populates="complaints")
    category = relationship("Category", lazy="joined")
    subcategory = relationship("Subcategory", lazy="joined")
    department = relationship("Department", foreign_keys=[department_id], lazy="joined")
    support_department = relationship("Department", foreign_keys=[support_department_id])
    entities = relationship(
        "ComplaintEntity", back_populates="complaint", cascade="all, delete-orphan"
    )
    attachments = relationship(
        "ComplaintAttachment", back_populates="complaint", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Complaint {self.public_ref} {self.status}>"


class ComplaintEntity(UUIDPrimaryKey, TimestampMixin, Base):
    """
    SRS Step 16 — entity extraction.

    ``extracted_by`` records whether Python's deterministic regex pass or the
    GenAI pass found it, so the two can be compared.
    """

    __tablename__ = "complaint_entities"
    __table_args__ = (
        Index("ix_entities_complaint_type", "complaint_id", "entity_type"),
        enum_check("extracted_by", EntityExtractor),
    )

    complaint_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("complaints.id", ondelete="CASCADE"), nullable=False
    )
    entity_type: Mapped[str] = mapped_column(Code, nullable=False)  # ORDER_ID, AMOUNT, DATE…
    value: Mapped[str] = mapped_column(String(512), nullable=False)
    normalized: Mapped[str | None] = mapped_column(String(512))
    span_start: Mapped[int | None] = mapped_column(Integer)
    span_end: Mapped[int | None] = mapped_column(Integer)
    extracted_by: Mapped[str] = mapped_column(String(16), nullable=False)
    confidence: Mapped[float | None] = mapped_column(Numeric(4, 3))

    complaint = relationship("Complaint", back_populates="entities")


class ComplaintLink(UUIDPrimaryKey, TimestampMixin, Base):
    """SRS Steps 52/54 — duplicate, near-duplicate and repeat relationships."""

    __tablename__ = "complaint_links"
    __table_args__ = (
        UniqueConstraint("complaint_id", "related_id", "link_type", name="uq_link_pair_type"),
        CheckConstraint("complaint_id <> related_id", name="no_self_link"),
        Index("ix_links_complaint", "complaint_id"),
        enum_check("link_type", LinkType),
    )

    complaint_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("complaints.id", ondelete="CASCADE"), nullable=False
    )
    related_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("complaints.id", ondelete="CASCADE"), nullable=False
    )
    link_type: Mapped[str] = mapped_column(String(24), nullable=False)
    similarity: Mapped[float | None] = mapped_column(Numeric(5, 4))
    detected_by: Mapped[str] = mapped_column(Code, nullable=False)  # TRIGRAM/EMBEDDING/REFERENCE


class ComplaintStatusHistory(TimestampMixin, Base):
    """FR lxv — complaint lifecycle tracking."""

    __tablename__ = "complaint_status_history"
    __table_args__ = (Index("ix_statushist_complaint", "complaint_id", "created_at"),)

    id: Mapped[int] = mapped_column(
        BigIntPK, primary_key=True, autoincrement=True, sort_order=-100
    )
    complaint_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("complaints.id", ondelete="CASCADE"), nullable=False
    )
    from_status: Mapped[str | None] = mapped_column(String(32))
    to_status: Mapped[str] = mapped_column(String(32), nullable=False)
    changed_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    reason: Mapped[str | None] = mapped_column(Text)


class ComplaintAttachment(UUIDPrimaryKey, TimestampMixin, Base):
    """SRS Step 10 — unsupported attachments must be detected, not crash."""

    __tablename__ = "complaint_attachments"

    complaint_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("complaints.id", ondelete="CASCADE"), nullable=False, index=True
    )
    file_name: Mapped[str] = mapped_column(String(512), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    complaint = relationship("Complaint", back_populates="attachments")
