"""
Hallucination detection (FR xxxii; SRS Step 35).

Two questions, deliberately separate because they fail in different ways and a
single "hallucination score" would blur them:

* :mod:`~hallucination_checks.citation_validator` — **does the source exist?**
  Every policy reference is resolved to a chunk and its version classified, so
  an invented reference, a superseded one and a not-yet-in-force one are three
  distinct verdicts rather than one vague doubt. This is also the table the
  Source-Traceability Challenge is answered from.

* :mod:`~hallucination_checks.claim_support` — **does the source say it?**
  Generated sentences are scored against the text they cite, with two further
  checks that lexical overlap alone cannot make: every figure in a claim must
  appear in the cited text, and the claim's polarity must match the source
  line it rests on.

Neither uses a model. A hallucination check that asked a model whether a model
hallucinated would inherit the failure it is supposed to catch, and could not
run during the outage where it matters most.
"""

from hallucination_checks.citation_validator import (
    CitationReport,
    CitationVerdict,
    chunk_texts,
    persist,
    trace,
    validate_all,
    validate_citation,
)
from hallucination_checks.claim_support import (
    DEFAULT_SUPPORT_THRESHOLD,
    Claim,
    ClaimReport,
    ClaimVerdict,
    best_sentence,
    check_claims,
    containment,
    numbers_in,
    split_claims,
)

__all__ = [
    "DEFAULT_SUPPORT_THRESHOLD",
    "CitationReport",
    "CitationVerdict",
    "Claim",
    "ClaimReport",
    "ClaimVerdict",
    "best_sentence",
    "check_claims",
    "chunk_texts",
    "containment",
    "numbers_in",
    "persist",
    "split_claims",
    "trace",
    "validate_all",
    "validate_citation",
]
