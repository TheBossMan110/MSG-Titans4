"""
The email channel: every message received at, and sent from, the support
mailbox. One row per message, both directions, so a thread can be read back
exactly as it happened -- including what the auto-reply said.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base, TimestampMixin, TZDateTime, UUIDPrimaryKey


class EmailMessage(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "email_messages"
    __table_args__ = (
        Index("ix_email_from", "from_address"),
        Index("ix_email_to", "to_address"),
        Index("ix_email_complaint", "complaint_id"),
        Index("ix_email_message_id", "message_id"),
    )

    direction: Mapped[str] = mapped_column(String(3), nullable=False)          # IN | OUT
    message_id: Mapped[str | None] = mapped_column(String(512))                 # RFC 5322 Message-ID
    in_reply_to: Mapped[str | None] = mapped_column(String(512))
    from_address: Mapped[str] = mapped_column(String(320), nullable=False)
    from_name: Mapped[str | None] = mapped_column(String(255))
    to_address: Mapped[str] = mapped_column(String(320), nullable=False)
    subject: Mapped[str] = mapped_column(String(998), nullable=False, default="")
    body_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    body_html: Mapped[str | None] = mapped_column(Text)
    # COMPLAINT | STATUS | FOLLOW_UP | OTHER (inbound); REPLY (outbound)
    intent: Mapped[str | None] = mapped_column(String(16))
    # RECEIVED -> PROCESSED -> REPLIED | IGNORED | FAILED (inbound); SENT | FAILED | NOT_SENT (outbound)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="RECEIVED")
    complaint_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("complaints.id", ondelete="SET NULL"))
    error: Mapped[str | None] = mapped_column(Text)
    handled_at: Mapped[datetime | None] = mapped_column(TZDateTime)

    complaint = relationship("Complaint", lazy="joined")
