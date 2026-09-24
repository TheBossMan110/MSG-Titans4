"""
Complaint pre-processing (FR v; SRS Step 11).

    "Text must be normalised before analysis: whitespace, casing artefacts,
     control characters and length."                       — SRS Step 11

Runs before anything else looks at a complaint, and produces **two** texts that
are both kept:

* ``description_raw`` — exactly as received, byte for byte. This is the
  evidence. A complaint that arrived with a zero-width character hiding an
  instruction must still show that character to a security reviewer, and a
  normalised-only record would have destroyed it.
* ``description_clean`` — what the pipelines read.

Keeping both is not redundancy. The injection console highlights what was
stripped, and it can only do that by diffing one against the other.

Normalisation deliberately overlaps with
:func:`security.injection_defense.neutralise` — both strip invisible
characters. That is not duplication to be factored out: the security layer
must keep working even if someone changes intake, and intake must keep working
even if the security layer is reconfigured. Each is correct on its own.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from src.core.config import settings
from src.core.logging import get_logger

log = get_logger("complaint_processing.preprocess")

# Control characters that carry no meaning in a complaint but break parsing,
# storage and display. Tab, newline and carriage return are kept.
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

# Zero-width and bidirectional marks: invisible to a reader, fully visible to
# a tokeniser. See security.injection_defense for why this matters.
_INVISIBLE = re.compile("[​-‏‪-‮⁠-⁤﻿­]")

_TRAILING_SPACE = re.compile(r"[ \t]+$", re.MULTILINE)
_RUN_OF_SPACES = re.compile(r"[ \t]{2,}")
_RUN_OF_NEWLINES = re.compile(r"\n{3,}")

# A complaint typed with caps lock on. Shouting is a tone signal, not a
# content one -- it is recorded, never removed, because SRS 1.8 #6 turns on
# tone being visible to analytics and invisible to the rule engine.
_SHOUTING_MIN_LENGTH = 20
_SHOUTING_RATIO = 0.7


@dataclass(slots=True)
class PreprocessResult:
    """The cleaned text and everything that was done to it."""

    raw: str
    clean: str
    transformations: list[str] = field(default_factory=list)
    truncated: bool = False
    original_length: int = 0
    shouting: bool = False

    @property
    def changed(self) -> bool:
        return self.raw != self.clean

    def summary(self) -> dict[str, Any]:
        return {
            "original_length": self.original_length,
            "clean_length": len(self.clean),
            "transformations": self.transformations,
            "truncated": self.truncated,
            "shouting": self.shouting,
        }


def looks_like_shouting(text: str) -> bool:
    """
    Whether the complaint is mostly upper case.

    Recorded as an analytics signal and never acted on. A furious customer is
    still describing whatever they are describing, and letting caps drive
    urgency is exactly the trap in SRS 1.8 #6.
    """
    letters = [c for c in text if c.isalpha()]
    if len(letters) < _SHOUTING_MIN_LENGTH:
        return False
    return sum(1 for c in letters if c.isupper()) / len(letters) >= _SHOUTING_RATIO


def preprocess(text: str, *, max_length: int | None = None) -> PreprocessResult:
    """
    Normalise a complaint for analysis, keeping the original intact.

    Never raises and never rejects: an empty or over-long complaint is a
    *validation* finding, recorded by :mod:`complaint_processing.validation`
    with its own row. Silently dropping it here would leave no evidence that
    anything was submitted.
    """
    raw = text if isinstance(text, str) else ""
    limit = max_length or settings.max_complaint_length

    result = PreprocessResult(raw=raw, clean=raw, original_length=len(raw))
    if not raw:
        return result

    working = raw

    # NFKC folds look-alike forms so a fullwidth "REFUND" matches a lexicon
    # entry written in ASCII.
    normalised = unicodedata.normalize("NFKC", working)
    if normalised != working:
        result.transformations.append("unicode_nfkc")
        working = normalised

    working, removed = _INVISIBLE.subn("", working)
    if removed:
        result.transformations.append(f"stripped_{removed}_invisible_chars")

    working, removed = _CONTROL.subn("", working)
    if removed:
        result.transformations.append(f"stripped_{removed}_control_chars")

    working = working.replace("\r\n", "\n").replace("\r", "\n")

    collapsed = _TRAILING_SPACE.sub("", working)
    collapsed = _RUN_OF_SPACES.sub(" ", collapsed)
    collapsed = _RUN_OF_NEWLINES.sub("\n\n", collapsed)
    if collapsed != working:
        result.transformations.append("collapsed_whitespace")
        working = collapsed

    working = working.strip()

    result.shouting = looks_like_shouting(working)
    if result.shouting:
        # Recorded, not corrected. The text a customer wrote is the text the
        # agent should see.
        result.transformations.append("shouting_detected")

    if len(working) > limit:
        working = working[:limit].rstrip()
        result.truncated = True
        result.transformations.append(f"truncated_to_{limit}_chars")
        log.warning(
            "complaint_truncated", original=result.original_length, limit=limit
        )

    result.clean = working
    return result
