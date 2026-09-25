"""
Skip clearing rows that cannot exist yet.

Every writer of a complaint's derived rows -- comparisons, resolution steps,
guidance, entities -- first deletes the complaint's previous rows, so that a
re-analysis replaces its output instead of piling a second copy beside it.
For a complaint created moments ago in this same intake there is nothing to
delete, and each of those DELETEs still cost a round trip to the database:
eight or nine of them per complaint.

Intake marks the complaint it has just created; a writer asks
:func:`needs_clearing` before deleting. The answer is "no" exactly once per
kind of row for a fresh complaint -- the first write -- and "yes" for every
later write and for every complaint intake did not create in this session.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

_FRESH = "fresh_complaints"


def mark_fresh(db: Session, complaint_id: uuid.UUID) -> None:
    """Record that ``complaint_id`` was created in this session and has no derived rows."""
    db.info.setdefault(_FRESH, {})[complaint_id] = set()


def forget_fresh(db: Session, complaint_id: Any) -> None:
    """End the fresh window; later writes clear as usual."""
    db.info.get(_FRESH, {}).pop(complaint_id, None)


def needs_clearing(db: Session, complaint_id: Any, kind: str) -> bool:
    """Whether a writer of ``kind`` rows must delete this complaint's old ones first."""
    written = db.info.get(_FRESH, {}).get(complaint_id)
    if written is None or kind in written:
        return True
    written.add(kind)
    return False
