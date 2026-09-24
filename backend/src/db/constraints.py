"""Helpers for turning code enums into database CHECK constraints."""

from __future__ import annotations

from enum import StrEnum

from sqlalchemy import CheckConstraint


def enum_check(column: str, enum_cls: type[StrEnum], name: str | None = None) -> CheckConstraint:
    allowed = ", ".join(f"'{m.value}'" for m in enum_cls)
    return CheckConstraint(f"{column} IN ({allowed})", name=name or f"{column}_valid")
