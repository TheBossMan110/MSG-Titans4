"""Audit trail contracts (FR lxiv)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from schemas.common import APIModel


class AuditEntryOut(APIModel):
    """
    One recorded act.

    ``before`` and ``after`` are the stored snapshots, not a diff: SRS Step 59
    wants the original recommendation and the reviewer's decision both on the
    record, and a diff would keep only what changed between them.
    """

    id: int
    at: datetime | None = None
    # An email, or null for the pipeline. Null is not an unknown person; it is
    # the system acting on its own, and the distinction is what a trail is for.
    actor: str | None = None
    actor_role: str | None = None
    entity_type: str
    entity_id: str
    action: str
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    reason: str | None = None
    request_id: str | None = None


class AuditActionCountOut(APIModel):
    """An action name and how often it has been recorded."""

    action: str
    count: int
