"""
Ordered ladders, normalised so that a higher number always means more severe.

This module exists because of one inversion that would otherwise be invisible.

``priority_levels.rank`` is 0 for **P0**, the most severe priority — the rank
is a display order, counting down in urgency terms. ``escalation_levels.rank``
runs the other way: 0 is **NONE** and 5 is **CRITICAL_MGMT**, counting *up*.

Compared raw, those two ladders disagree about what "below" means. A GenAI
proposal of **P3** against a rule-derived **P0** would be reported as *above*
the rule-derived value, and an under-prioritisation would be filed as a safe
over-cautious disagreement — inverting the exact signal SRS 1.8 #7 asks us to
detect.

So every ladder is converted here to a single convention:

    higher severity rank == more severe

Priority is inverted on load. Urgency has no table of its own and is ranked
from its enum order. Nothing downstream needs to know which way any source
table happened to count.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.logging import get_logger
from src.db.enums import Urgency
from src.db.models import EscalationLevel, PriorityLevel

log = get_logger("comparison_engine.ladders")

# LOW < MEDIUM < HIGH < CRITICAL. Urgency is an enum rather than a table
# because it is a fixed vocabulary the rule engine reasons over directly.
# Keys are plain strings, not enum members. A StrEnum happens to hash equal to
# its value so either works today, but these ranks are also serialised into
# diagnostics, and enum keys would surface there as "Urgency.LOW".
URGENCY_RANKS: dict[str, int] = {
    str(Urgency.LOW): 0,
    str(Urgency.MEDIUM): 1,
    str(Urgency.HIGH): 2,
    str(Urgency.CRITICAL): 3,
}


def load_ladders(db: Session) -> dict[str, dict[str, int]]:
    """
    Severity ranks for every ordered field, keyed by comparison field name.

    Loaded from the database rather than hard-coded so that an administrator
    adding an escalation level gets a correctly ordered comparison without a
    code change (SRS 1.8 #5).
    """
    escalation = {
        row.code: int(row.rank)
        for row in db.execute(select(EscalationLevel).order_by(EscalationLevel.rank)).scalars()
    }

    # Invert priority: rank 0 (P0) is the most severe, so it must carry the
    # highest severity rank. Using max-rank minus rank keeps the spacing and
    # survives an administrator adding a P4.
    priority_rows = {
        row.code: int(row.rank)
        for row in db.execute(select(PriorityLevel).order_by(PriorityLevel.rank)).scalars()
    }
    highest = max(priority_rows.values(), default=0)
    priority = {code: highest - rank for code, rank in priority_rows.items()}

    ladders = {
        "escalation_level": escalation,
        "priority": priority,
        "urgency": dict(URGENCY_RANKS),
    }

    log.debug(
        "ladders_loaded",
        escalation=len(escalation), priority=len(priority), urgency=len(URGENCY_RANKS),
    )
    return ladders


def severity_rank(ladders: dict[str, dict[str, int]], field: str, value: str | None) -> int | None:
    """Rank one value on one ladder, or ``None`` if it is not a known rung."""
    if not value:
        return None
    return ladders.get(field, {}).get(str(value).strip().upper())


def at_or_above(
    ladders: dict[str, dict[str, int]], field: str, value: str | None, floor: str | None
) -> bool:
    """
    Whether ``value`` satisfies ``floor`` on this ladder.

    Used to enforce the mandatory escalation floor. An unknown rung fails
    closed — returning True for a level we cannot place would let an
    unrecognised value silently satisfy a safety floor.
    """
    if not floor:
        return True
    value_rank = severity_rank(ladders, field, value)
    floor_rank = severity_rank(ladders, field, floor)
    if floor_rank is None:
        return True          # nothing to enforce
    if value_rank is None:
        return False         # unplaceable value cannot be shown to satisfy it
    return value_rank >= floor_rank
