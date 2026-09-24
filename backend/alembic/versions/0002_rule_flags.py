"""Rule catch-all flag and eligibility finding.

Revision ID: 0002_rule_flags
Revises: 0001_initial

Adds two columns to ``rules``:

``is_catch_all``
    A catch-all rule gives an unrecognised complaint a queue to land in
    without claiming to have recognised it.  The engine still reports
    ``unmatched`` when only catch-alls fired, so "we do not know" never
    silently becomes a confident answer.

``eligibility``
    The refund / replacement / compensation finding a rule asserts
    (SRS Steps 29-31).  A dedicated column rather than metadata smuggled into
    ``conditions``, because the condition evaluator must only ever be handed a
    condition tree.

Note on what this migration deliberately does NOT do
----------------------------------------------------
Autogenerate proposed dropping ``ix_comp_fts``, ``ix_comp_desc_trgm``,
``ix_chunks_fts`` and ``ix_chunks_embedding``, and creating
``ux_users_email_lower``.  All five are expression or operator-class indexes
created by raw SQL in 0001; SQLAlchemy cannot reflect them faithfully, so
every autogenerate run will keep proposing to churn them.  Applying that churn
would silently delete the search and ANN indexes the retrieval layer depends
on, so those operations are removed here.

If a future migration genuinely needs to change one of those indexes, do it
with explicit ``op.execute`` as 0001 does.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from src.db.base import JSONType

revision: str = "0002_rule_flags"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "rules",
        sa.Column("is_catch_all", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("rules", sa.Column("eligibility", JSONType, nullable=True))
    # The server default exists only to backfill existing rows; the application
    # always supplies the value explicitly.
    op.alter_column("rules", "is_catch_all", server_default=None)


def downgrade() -> None:
    op.drop_column("rules", "eligibility")
    op.drop_column("rules", "is_catch_all")
