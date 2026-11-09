"""Plan requests from the public pricing page. A new table only; nothing existing changes.

Revision ID: 0008_plan_requests
Revises: 0007_platform_superadmin
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from src.db.base import TZDateTime

revision: str = "0008_plan_requests"
down_revision: str | None = "0007_platform_superadmin"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "plan_requests",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("company_name", sa.String(255), nullable=False),
        sa.Column("contact_name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("phone", sa.String(40)),
        sa.Column("plan_code", sa.String(32), nullable=False),
        sa.Column("billing_cycle", sa.String(16), nullable=False, server_default="monthly"),
        sa.Column("team_size", sa.Integer()),
        sa.Column("monthly_complaints", sa.Integer()),
        sa.Column("message", sa.Text()),
        sa.Column("status", sa.String(16), nullable=False, server_default="NEW"),
        sa.Column("organisation_id", sa.Uuid(), sa.ForeignKey("organisations.id", ondelete="SET NULL")),
        sa.Column("created_at", TZDateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_plan_requests_status_created", "plan_requests", ["status", "created_at"])


def downgrade() -> None:
    op.drop_table("plan_requests")
