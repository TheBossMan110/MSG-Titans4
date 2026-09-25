"""Account security: two-step sign-in, lockout, session metadata.

Revision ID: 0003_account_security
Revises: 0002_rule_flags

``users``
    ``mfa_secret``           the TOTP secret, encrypted at rest (never plain).
    ``mfa_enabled_at``       when two-step sign-in was switched on; NULL = off.
    ``mfa_recovery_codes``   SHA-256 hashes of the unused one-time codes.
    ``failed_login_count``   consecutive wrong passwords since the last success.
    ``locked_until``         sign-in refused until then, after too many failures.
    ``password_changed_at``  so a user can see when it last changed.

``refresh_tokens``
    ``ip_address``           where the session was started.
    ``session_started_at``   carried across token rotation, so a session keeps
                             its age even though its token is replaced each
                             time it is refreshed.

Additive only; every column is nullable or defaulted.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from src.db.base import JSONType, TZDateTime

revision: str = "0003_account_security"
down_revision: str | None = "0002_rule_flags"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("mfa_secret", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("mfa_enabled_at", TZDateTime(), nullable=True))
    op.add_column("users", sa.Column("mfa_recovery_codes", JSONType, nullable=True))
    op.add_column(
        "users",
        sa.Column("failed_login_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("users", sa.Column("locked_until", TZDateTime(), nullable=True))
    op.add_column("users", sa.Column("password_changed_at", TZDateTime(), nullable=True))
    op.alter_column("users", "failed_login_count", server_default=None)

    op.add_column("refresh_tokens", sa.Column("ip_address", sa.String(64), nullable=True))
    op.add_column("refresh_tokens", sa.Column("session_started_at", TZDateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("refresh_tokens", "session_started_at")
    op.drop_column("refresh_tokens", "ip_address")
    for column in (
        "password_changed_at", "locked_until", "failed_login_count",
        "mfa_recovery_codes", "mfa_enabled_at", "mfa_secret",
    ):
        op.drop_column("users", column)
