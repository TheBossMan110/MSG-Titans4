"""Organisations: more than one company on the platform.

Revision ID: 0006_organisations
Revises: 0005_off_topic_content

``organisations``
    A company: name, slug (its customer sign-up link), industry, and the
    access policy its administrator sets (``settings``). One row is created
    for the data that already exists: RaftarXpress, with the fixed id
    ``00000000-0000-0000-0000-000000000001``.

``<business table>.organisation_id``
    Added to the 40 tables that hold a company's own data -- users,
    customers, complaints and everything derived from them, the knowledge
    base, the review queue, email, audit, benchmarks. Every existing row is
    backfilled to RaftarXpress, so nothing anybody sees today changes.
    Reference data (taxonomy, rules, lexicon, prompts, configuration) is not
    touched: it is the shared template every company runs on.

Unique keys that were global become per organisation, so two companies can
each have a "DOC-001" and upload the same file:
    documents        (family_key)                -> (organisation_id, family_key)
    document_versions (file_hash)                -> (organisation_id, file_hash)
    trend_snapshots  (period_type, ... )         -> (organisation_id, period_type, ...)

Additive and backfilled in place: no row is deleted or rewritten except to
gain its organisation.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from src.db.base import JSONType, TZDateTime

revision: str = "0006_organisations"
down_revision: str | None = "0005_off_topic_content"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEFAULT_ID = "00000000-0000-0000-0000-000000000001"

TABLES = (
    "users", "audit_log", "customers", "complaints", "complaint_entities", "complaint_links",
    "complaint_status_history", "complaint_attachments", "email_messages",
    "complaint_policy_refs", "resolution_steps", "eligibility_decisions", "clarification_questions",
    "agent_guidance", "documents", "document_versions", "document_sections", "chunks",
    "injection_events", "jobs", "benchmark_runs", "benchmark_results", "impact_analyses",
    "impact_items", "report_exports", "trend_snapshots", "genai_runs", "validation_runs",
    "rule_hits", "complaint_validation_issues", "document_validation_issues", "comparisons",
    "verification_decisions", "responses", "response_flags", "escalations", "follow_ups",
    "review_queue", "review_actions", "sla_events",
)

# (table, old name, old columns, new name, new columns)
UNIQUES = (
    ("documents", "uq_documents_family_key", ["family_key"],
     "uq_documents_org_family_key", ["organisation_id", "family_key"]),
    ("document_versions", "uq_docver_file_hash", ["file_hash"],
     "uq_docver_org_file_hash", ["organisation_id", "file_hash"]),
    ("trend_snapshots", "uq_trend_period_metric_dim",
     ["period_type", "period_start", "metric", "dimension", "dimension_value"],
     "uq_trend_org_period_metric_dim",
     ["organisation_id", "period_type", "period_start", "metric", "dimension", "dimension_value"]),
)


def _default_literal() -> sa.TextClause:
    # A Uuid column is native uuid on PostgreSQL and 32 hex characters on SQLite.
    if op.get_bind().dialect.name == "postgresql":
        return sa.text(f"'{DEFAULT_ID}'")
    return sa.text(f"'{DEFAULT_ID.replace('-', '')}'")


def upgrade() -> None:
    op.create_table(
        "organisations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(64), nullable=False),
        sa.Column("industry", sa.String(120), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("settings", JSONType, nullable=True),
        sa.Column("created_at", TZDateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_organisations")),
        sa.UniqueConstraint("slug", name=op.f("uq_organisations_slug")),
    )

    bind = op.get_bind()
    profile = bind.execute(sa.text("SELECT value FROM app_config WHERE key = 'organisation'")).scalar()
    name = profile.get("name") if isinstance(profile, dict) else None
    organisations = sa.table(
        "organisations",
        sa.column("id", sa.Uuid()), sa.column("name", sa.String), sa.column("slug", sa.String),
        sa.column("industry", sa.String), sa.column("is_active", sa.Boolean), sa.column("settings", sa.JSON),
    )
    op.bulk_insert(organisations, [{
        "id": uuid.UUID(DEFAULT_ID), "name": name or "RaftarXpress Logistics (Pvt) Ltd",
        "slug": "raftarxpress", "industry": "Logistics & courier", "is_active": True, "settings": {},
    }])

    default = _default_literal()
    for table in TABLES:
        with op.batch_alter_table(table) as batch:
            # The server default fills every existing row in the same statement,
            # and is kept: the previous release, still serving while a deploy
            # starts, inserts without the column, and its rows must land in the
            # platform organisation rather than fail. The application itself
            # always supplies the value.
            batch.add_column(sa.Column("organisation_id", sa.Uuid(), nullable=False, server_default=default))
        with op.batch_alter_table(table) as batch:
            batch.create_foreign_key(
                op.f(f"fk_{table}_organisation_id_organisations"), "organisations",
                ["organisation_id"], ["id"], ondelete="CASCADE",
            )
            batch.create_index(op.f(f"ix_{table}_organisation_id"), ["organisation_id"])

    for table, old, _old_cols, new, new_cols in UNIQUES:
        with op.batch_alter_table(table) as batch:
            batch.drop_constraint(old, type_="unique")
            batch.create_unique_constraint(new, new_cols)


def downgrade() -> None:
    for table, old, old_cols, new, _new_cols in UNIQUES:
        with op.batch_alter_table(table) as batch:
            batch.drop_constraint(new, type_="unique")
            batch.create_unique_constraint(old, old_cols)
    for table in reversed(TABLES):
        with op.batch_alter_table(table) as batch:
            batch.drop_index(op.f(f"ix_{table}_organisation_id"))
            batch.drop_constraint(op.f(f"fk_{table}_organisation_id_organisations"), type_="foreignkey")
            batch.drop_column("organisation_id")
    op.drop_table("organisations")
