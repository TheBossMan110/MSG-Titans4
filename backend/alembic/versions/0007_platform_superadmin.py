"""The platform and its super administrator.

Revision ID: 0007_platform_superadmin
Revises: 0006_organisations

``users.role``
    The CHECK constraint learns ``superadmin``: the platform owner, who sees
    every company and the system's health and accuracy but no company's
    complaints, customers, people or emails.

``organisations``
    The platform's own organisation (id ``00000000-0000-0000-0000-000000000000``)
    holds the super administrators and no business data, so the organisation
    filter leaves a super administrator with no company's rows in reach.
    RaftarXpress stays the reference company that owns the shared template.

``users``
    ``superadmin@supportnova.com`` is created when absent, with the seeded
    demonstration password (``SEED_PASSWORD``, default ``SupportNova#2026``),
    like every other published demo account. An existing account is left alone.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa

from alembic import op

revision: str = "0007_platform_superadmin"
down_revision: str | None = "0006_organisations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PLATFORM_ID = uuid.UUID("00000000-0000-0000-0000-000000000000")
EMAIL = "superadmin@supportnova.com"
_BEFORE = ["customer", "agent", "reviewer", "manager", "admin", "evaluator"]
_AFTER = [*_BEFORE, "superadmin"]


def _role_check(roles: list[str]) -> None:
    allowed = ", ".join(f"'{r}'" for r in roles)
    with op.batch_alter_table("users") as batch:
        batch.drop_constraint(op.f("ck_users_role_valid"), type_="check")
        batch.create_check_constraint(op.f("ck_users_role_valid"), f"role IN ({allowed})")


def upgrade() -> None:
    _role_check(_AFTER)
    bind = op.get_bind()

    organisations = sa.table(
        "organisations",
        sa.column("id", sa.Uuid()), sa.column("name", sa.String), sa.column("slug", sa.String),
        sa.column("industry", sa.String), sa.column("is_active", sa.Boolean), sa.column("settings", sa.JSON),
    )
    exists = bind.execute(sa.select(organisations.c.id).where(organisations.c.id == PLATFORM_ID)).first()
    if exists is None:
        taken = bind.execute(sa.select(organisations.c.id).where(organisations.c.slug == "platform")).first()
        op.bulk_insert(organisations, [{
            "id": PLATFORM_ID, "name": "SupportNova Platform",
            "slug": "supportnova-platform" if taken else "platform",
            "industry": "Platform", "is_active": True, "settings": {},
        }])

    users = sa.table(
        "users",
        sa.column("id", sa.Uuid()), sa.column("email", sa.String), sa.column("password_hash", sa.Text),
        sa.column("full_name", sa.String), sa.column("role", sa.String), sa.column("is_active", sa.Boolean),
        sa.column("failed_login_count", sa.Integer), sa.column("organisation_id", sa.Uuid()),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    present = bind.execute(sa.select(users.c.id).where(sa.func.lower(users.c.email) == EMAIL)).first()
    if present is None:
        from src.core.security import hash_password

        op.bulk_insert(users, [{
            "id": uuid.uuid4(), "email": EMAIL,
            "password_hash": hash_password(os.getenv("SEED_PASSWORD", "SupportNova#2026")),
            "full_name": "Platform Super Admin", "role": "superadmin", "is_active": True,
            "failed_login_count": 0, "organisation_id": PLATFORM_ID, "created_at": datetime.now(UTC),
        }])


def downgrade() -> None:
    op.execute("DELETE FROM users WHERE role = 'superadmin'")
    platform = sa.table("organisations", sa.column("id", sa.Uuid()))
    op.execute(platform.delete().where(platform.c.id == PLATFORM_ID))
    _role_check(_BEFORE)
