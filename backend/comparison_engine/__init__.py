"""
The comparison engine — where Pipeline 1 and Pipeline 2 meet.

    "The system must compare the GenAI result against the Python rule result
     field by field, and the comparison must be stored."   — SRS Steps 52-57

Four modules, each with one job:

* :mod:`~comparison_engine.fields`   — which fields are compared, and how each
  one is read out of two very differently-shaped results.
* :mod:`~comparison_engine.ladders`  — ordered vocabularies normalised so that
  higher always means more severe (priority counts the other way in its own
  table, which would otherwise invert every priority comparison).
* :mod:`~comparison_engine.diff`     — the field-by-field comparison, with the
  explanation Deliverable 8 asks for on every row.
* :mod:`~comparison_engine.decision` — scores, the review trigger, the
  reconciled record, and the escalation floor that only ever raises.
* :mod:`~comparison_engine.engine`   — runs both pipelines and persists.

The governing rule, and the reason the engine exists at all: **the rules win
any disagreement that matters.** The model contributes language, nuance and
speed. It does not contribute authority over routing, priority, escalation or
eligibility, and every place it tried to is recorded rather than smoothed over.
"""

from comparison_engine.decision import (
    ReviewReason,
    Score,
    VerificationResult,
    decide,
    floor_satisfied,
)
from comparison_engine.diff import FieldComparison, compare_all, compare_field
from comparison_engine.engine import (
    ReconciliationResult,
    comparison_rows,
    latest_decision,
    reconcile,
    resolve_citations,
)
from comparison_engine.fields import FIELD_SPECS, FIELDS_BY_NAME, FieldSpec
from comparison_engine.ladders import at_or_above, load_ladders, severity_rank

__all__ = [
    "FIELDS_BY_NAME",
    "FIELD_SPECS",
    "FieldComparison",
    "FieldSpec",
    "ReconciliationResult",
    "ReviewReason",
    "Score",
    "VerificationResult",
    "at_or_above",
    "comparison_rows",
    "compare_all",
    "compare_field",
    "decide",
    "floor_satisfied",
    "latest_decision",
    "load_ladders",
    "reconcile",
    "resolve_citations",
    "severity_rank",
]
