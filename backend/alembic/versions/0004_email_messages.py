"""Email channel: messages received and sent.

Revision ID: 0004_email_messages
Revises: 0003_account_security
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from src.db.base import TZDateTime

revision: str = "0004_email_messages"
down_revision: str | None = "0003_account_security"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "email_messages",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("direction", sa.String(3), nullable=False),
        sa.Column("message_id", sa.String(512)),
        sa.Column("in_reply_to", sa.String(512)),
        sa.Column("from_address", sa.String(320), nullable=False),
        sa.Column("from_name", sa.String(255)),
        sa.Column("to_address", sa.String(320), nullable=False),
        sa.Column("subject", sa.String(998), nullable=False, server_default=""),
        sa.Column("body_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("body_html", sa.Text()),
        sa.Column("intent", sa.String(16)),
        sa.Column("status", sa.String(16), nullable=False, server_default="RECEIVED"),
        sa.Column("complaint_id", sa.Uuid(), sa.ForeignKey("complaints.id", ondelete="SET NULL")),
        sa.Column("error", sa.Text()),
        sa.Column("handled_at", TZDateTime()),
        sa.Column("created_at", TZDateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_email_from", "email_messages", ["from_address"])
    op.create_index("ix_email_to", "email_messages", ["to_address"])
    op.create_index("ix_email_complaint", "email_messages", ["complaint_id"])
    op.create_index("ix_email_message_id", "email_messages", ["message_id"])


def downgrade() -> None:
    op.drop_table("email_messages")
