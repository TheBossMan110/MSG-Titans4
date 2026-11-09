"""Content relevance: a finding for uploads that are not about complaint handling.

Revision ID: 0005_off_topic_content
Revises: 0004_email_messages

``complaint_validation_issues.issue_code`` / ``document_validation_issues.issue_code``
    The CHECK constraint learns ``OFF_TOPIC_CONTENT``: a valid PDF or DOCX
    about something else (a song and a picture, a recipe) refused by
    document_processing/relevance.py.

``app_config.content_relevance``
    The gate's thresholds, inserted when absent, so an administrator can tune
    them at runtime on a database that is never reseeded. A seeded value is
    left as it is.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005_off_topic_content"
down_revision: str | None = "0004_email_messages"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_BEFORE = [
    "EMPTY_COMPLAINT", "TOO_SHORT", "TOO_LONG", "DUPLICATE_COMPLAINT", "INVALID_REFERENCE_ID",
    "MISSING_MANDATORY_FIELD", "UNSUPPORTED_ATTACHMENT", "SUSPECTED_INJECTION",
    "UNSUPPORTED_FILE_TYPE", "FILE_TOO_LARGE", "EMPTY_FILE", "DUPLICATE_DOCUMENT",
    "MISSING_DOCUMENT_ID", "MISSING_VERSION", "MISSING_EFFECTIVE_DATE", "EXPIRED_DOCUMENT",
    "MISSING_CATEGORY", "NO_TEXT_LAYER", "PARSE_FAILED", "METADATA_INCOMPLETE",
]
_AFTER = [*_BEFORE, "OFF_TOPIC_CONTENT"]
_TABLES = ("complaint_validation_issues", "document_validation_issues")

_DEFAULTS = {
    "enabled": True,
    "policy_min_density": 6.0,
    "policy_min_distinct": 6,
    "complaint_min_density_without_anchor": 4.5,
    "complaint_min_distinct_without_anchor": 4,
    "song_max_density": 10.0,
    "song_repeat_share": 0.25,
    "song_min_lines": 8,
    "cv_min_sections": 4,
    "cv_min_sections_with_marker": 2,
}


def _recreate_checks(codes: list[str]) -> None:
    allowed = ", ".join(f"'{code}'" for code in codes)
    for table in _TABLES:
        name = op.f(f"ck_{table}_issue_code_valid")
        with op.batch_alter_table(table) as batch:
            batch.drop_constraint(name, type_="check")
            batch.create_check_constraint(name, f"issue_code IN ({allowed})")


def upgrade() -> None:
    _recreate_checks(_AFTER)

    config = sa.table(
        "app_config",
        sa.column("key", sa.String), sa.column("value", sa.JSON),
        sa.column("description", sa.Text), sa.column("version", sa.Integer),
    )
    bind = op.get_bind()
    present = bind.execute(sa.text("SELECT 1 FROM app_config WHERE key = 'content_relevance'")).first()
    if present is None:
        op.bulk_insert(config, [{
            "key": "content_relevance",
            "value": _DEFAULTS,
            "description": "Thresholds for refusing uploads that are not about complaint handling (song lyrics, recipes).",
            "version": 1,
        }])


def downgrade() -> None:
    op.execute("DELETE FROM app_config WHERE key = 'content_relevance'")
    for table in _TABLES:
        op.execute(f"DELETE FROM {table} WHERE issue_code = 'OFF_TOPIC_CONTENT'")
    _recreate_checks(_BEFORE)
