"""
Alembic environment.

The database URL always comes from ``DATABASE_URL`` (via pydantic-settings), so
the same migrations run against Supabase Postgres in production and against a
local SQLite file in the offline demo fallback.
"""

from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config, pool

from alembic import context

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.core.config import settings  # noqa: E402
from src.db.models import Base  # noqa: E402  (registers every table)

config = context.config

# configparser treats '%' as interpolation syntax, so a percent-encoded
# password (e.g. '%40' for '@') raises
# ValueError: invalid interpolation syntax - and prints the whole URL,
# password included, into the traceback. Escaping it here avoids both.
config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


# Tables owned by Postgres extensions must never appear in an autogenerate diff.
EXTENSION_OWNED_TABLES = {"spatial_ref_sys"}


def _include_object(obj, name, type_, reflected, compare_to):
    return not (type_ == "table" and name in EXTENSION_OWNED_TABLES)


# Our portable column types (src/db/base.py) must be rendered by NAME with a
# matching import, not as a fully-qualified path.  Without this, autogenerate
# emits `src.db.base.TZDateTime(...)` with no import (NameError at upgrade),
# and renders JSONType as plain `sa.JSON()` when the dev connection is SQLite -
# which would silently create un-indexable `json` columns on PostgreSQL.
CUSTOM_TYPE_NAMES = {"TZDateTime", "JSONType", "Vector"}


def _render_item(type_, obj, autogen_context):
    if type_ != "type":
        return False  # fall back to alembic's default rendering

    name = type(obj).__name__
    if name == "Vector":
        autogen_context.imports.add("from src.db.base import Vector")
        return f"Vector({getattr(obj, 'dim', 768)})"
    if name in CUSTOM_TYPE_NAMES:
        autogen_context.imports.add(f"from src.db.base import {name}")
        return f"{name}()"
    # JSONType is a variant instance, not a class - match it by identity.
    from src.db.base import JSONType

    if obj is JSONType:
        autogen_context.imports.add("from src.db.base import JSONType")
        return "JSONType"
    return False


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
        include_object=_include_object,
        render_item=_render_item,
        render_as_batch=not settings.is_postgres,  # SQLite needs batch ALTER
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
            include_object=_include_object,
            render_item=_render_item,
            render_as_batch=connection.dialect.name == "sqlite",
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
