"""YAML loading + idempotent upsert helpers used by every seeder."""

from __future__ import annotations

from pathlib import Path
from typing import Any, TypeVar

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.config import settings
from src.db.base import Base

T = TypeVar("T", bound=Base)


def load_yaml(name: str) -> dict[str, Any]:
    """Read ``config/<name>`` and return it as a dict."""
    path: Path = settings.config_dir / name
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a mapping at the top level")
    return data


def upsert(
    db: Session,
    model: type[T],
    *,
    match: dict[str, Any],
    values: dict[str, Any],
) -> tuple[T, bool]:
    """
    Find-or-create by ``match``, then update with ``values``.

    Returns ``(instance, created)``.  Seeders must be re-runnable: evaluators
    may reseed mid-competition and no row should be duplicated.
    """
    stmt = select(model)
    for key, val in match.items():
        stmt = stmt.where(getattr(model, key) == val)
    instance = db.execute(stmt).scalars().first()

    if instance is None:
        instance = model(**{**match, **values})
        db.add(instance)
        db.flush()
        return instance, True

    changed = False
    for key, val in values.items():
        if getattr(instance, key) != val:
            setattr(instance, key, val)
            changed = True
    if changed:
        db.flush()
    return instance, False
