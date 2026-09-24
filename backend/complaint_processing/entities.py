"""
Deterministic entity extraction (FR xvi, SRS Step 16).

Pure regex over the complaint text.  No model is involved, which is the point:
the GenAI pipeline *also* extracts entities, and storing both with
``extracted_by`` set lets the comparison engine show where they disagree.

Patterns live in ``app_config['entity_patterns']`` (seeded from
``config/signals.yaml``) rather than in this file, so an evaluator can add an
identifier format at runtime — a new order-reference shape, a new transaction
prefix — without a deploy.

Every match carries its character span.  Spans are what let the UI highlight
the exact text that produced a finding, and the same mechanism powers the
rule-hit explainability panel.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from typing import Any

from sqlalchemy.orm import Session

from src.core.logging import get_logger
from src.db.models import AppConfig

log = get_logger("complaint_processing.entities")

# Fallback used only when app_config has not been seeded. The seeded copy in
# config/signals.yaml is the source of truth.
DEFAULT_ENTITY_PATTERNS: dict[str, str] = {
    "ORDER_ID": r"\bZ[NK]-?\d{6,8}\b|\bORD-?\d{6,10}\b",
    "TRANSACTION_ID": r"\bTXN[-_ ]?[A-Z0-9]{8,14}\b",
    "INVOICE_ID": r"\bINV-?\d{6,10}\b",
    "COMPLAINT_REF": r"\bCMP-?\d{4,8}\b",
    "AMOUNT": r"(?:rs\.?|inr|aed|gbp|usd|[₹£$])\s?\d[\d,]*(?:\.\d{1,2})?",
    "DATE_ISO": r"\b\d{4}-\d{2}-\d{2}\b",
    "EMAIL": r"[\w.+-]+@[\w-]+\.[\w.]{2,}",
    "PHONE": r"\+?\d[\d\s-]{8,14}\d",
}

# Currency token -> ISO code, for normalising an extracted amount.
_CURRENCY_TOKENS: dict[str, str] = {
    "rs": "INR", "rs.": "INR", "inr": "INR", "₹": "INR",
    "aed": "AED",
    "gbp": "GBP", "£": "GBP",
    "usd": "USD", "$": "USD",
}


@dataclass(slots=True)
class ExtractedEntity:
    """One entity found in the complaint text, with its exact location."""

    entity_type: str
    value: str
    normalized: str | None
    span_start: int
    span_end: int

    def as_span(self) -> dict[str, Any]:
        return {
            "start": self.span_start,
            "end": self.span_end,
            "text": self.value,
            "type": self.entity_type,
        }


@dataclass(slots=True)
class EntitySet:
    """All entities found, grouped for cheap lookup by the rule engine."""

    entities: list[ExtractedEntity] = field(default_factory=list)
    by_type: dict[str, list[ExtractedEntity]] = field(default_factory=dict)

    def add(self, entity: ExtractedEntity) -> None:
        self.entities.append(entity)
        self.by_type.setdefault(entity.entity_type, []).append(entity)

    def has(self, entity_type: str) -> bool:
        return bool(self.by_type.get(entity_type))

    def first(self, entity_type: str) -> ExtractedEntity | None:
        found = self.by_type.get(entity_type)
        return found[0] if found else None

    def values(self, entity_type: str) -> list[str]:
        return [e.value for e in self.by_type.get(entity_type, [])]

    @property
    def types(self) -> list[str]:
        return sorted(self.by_type)

    def max_amount(self) -> Decimal | None:
        """
        Largest monetary amount mentioned.

        Used by value-threshold rules.  The *largest* is taken deliberately: a
        complaint quoting both an item price and a total dispute value should
        be assessed on the larger exposure.
        """
        amounts: list[Decimal] = []
        for entity in self.by_type.get("AMOUNT", []):
            parsed = parse_amount(entity.normalized or entity.value)
            if parsed is not None:
                amounts.append(parsed)
        return max(amounts) if amounts else None


# The numeric part of a money string: must START with a digit, may carry
# thousands separators, may end with at most two decimal places.
_AMOUNT_NUMBER = re.compile(r"\d[\d,]*(?:\.\d{1,2})?")


def parse_amount(raw: str) -> Decimal | None:
    """
    Turn 'Rs. 12,499.00' into Decimal('12499.00'). None if unparseable.

    Stripping everything except digits and dots is NOT safe here: the full stop
    in a currency abbreviation survives that filter, so 'Rs. 42,500' became
    '.42500' and parsed as 0.42500. A forty-two-thousand-rupee dispute would
    then sail under every value threshold in the matrix without any error being
    raised.

    Matching the number itself, anchored on a leading digit, avoids the whole
    class of problem.
    """
    match = _AMOUNT_NUMBER.search(raw or "")
    if not match:
        return None
    try:
        return Decimal(match.group(0).replace(",", ""))
    except InvalidOperation:
        return None


def currency_of(raw: str) -> str | None:
    lowered = (raw or "").strip().lower()
    for token, code in _CURRENCY_TOKENS.items():
        if lowered.startswith(token):
            return code
    return None


@lru_cache(maxsize=256)
def _compile(pattern: str) -> re.Pattern[str] | None:
    """
    Compile a configured pattern, tolerating a bad one.

    Patterns are editable at runtime, so an administrator can save an invalid
    regex.  That must degrade to "this one entity type stops matching", never
    to a crashed validation pipeline.
    """
    try:
        return re.compile(pattern, re.IGNORECASE)
    except re.error as exc:
        log.warning("invalid_entity_pattern", pattern=pattern[:80], error=str(exc))
        return None


def load_entity_patterns(db: Session) -> dict[str, str]:
    config = db.get(AppConfig, "entity_patterns")
    if config and isinstance(config.value, dict) and config.value:
        return {str(k): str(v) for k, v in config.value.items()}
    return dict(DEFAULT_ENTITY_PATTERNS)


def extract_entities(text: str, patterns: dict[str, str]) -> EntitySet:
    """
    Find every configured entity in ``text``.

    Overlapping matches of the *same* type are collapsed; different types are
    allowed to overlap, because one substring can legitimately be both an
    amount and part of a reference.
    """
    result = EntitySet()
    if not text:
        return result

    for entity_type, pattern in patterns.items():
        compiled = _compile(pattern)
        if compiled is None:
            continue

        claimed: list[tuple[int, int]] = []
        for match in compiled.finditer(text):
            start, end = match.span()
            if any(start < prev_end and end > prev_start for prev_start, prev_end in claimed):
                continue
            claimed.append((start, end))

            value = match.group(0).strip()
            result.add(
                ExtractedEntity(
                    entity_type=entity_type,
                    value=value,
                    normalized=_normalise(entity_type, value),
                    span_start=start,
                    span_end=end,
                )
            )

    return result


def _normalise(entity_type: str, value: str) -> str | None:
    """Canonical form, so two spellings of one reference compare equal."""
    if entity_type in {"ORDER_ID", "TRANSACTION_ID", "INVOICE_ID", "COMPLAINT_REF", "TRACKING_ID"}:
        return re.sub(r"[\s_-]", "", value).upper()
    if entity_type == "AMOUNT":
        amount = parse_amount(value)
        currency = currency_of(value)
        if amount is None:
            return None
        return f"{currency} {amount}" if currency else str(amount)
    if entity_type == "EMAIL":
        return value.lower()
    if entity_type == "PHONE":
        return re.sub(r"[\s-]", "", value)
    return None


def extract_for_complaint(db: Session, text: str) -> EntitySet:
    """Convenience wrapper that loads the configured patterns first."""
    return extract_entities(text, load_entity_patterns(db))
