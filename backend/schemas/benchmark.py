"""
Benchmark and dataset API contracts.

Accuracy fields are ``float | None`` throughout. A pipeline that did not run
scores ``null``, never 0 — a rules-only run or one taken during a provider
outage must not report the model as having got everything wrong when it was
never asked (SRS 1.8 #17).
"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from schemas.common import APIModel


class DatasetOut(APIModel):
    """
    One dataset and how much of it can be scored.

    ``unlabelled`` is load-bearing: an unlabelled complaint can be processed
    but not scored, and a benchmark run over a mostly-unlabelled set would
    report accuracy drawn from a handful of rows.
    """

    dataset_tag: str
    total: int = 0
    labelled: int = 0
    unlabelled: int = 0
    analysed: int = 0
    pending_analysis: int = 0


class ImportResultOut(APIModel):
    dataset_tag: str
    imported: int = 0
    skipped: int = 0
    labelled: int = 0
    unlabelled: int = 0
    errors: list[dict[str, Any]] = Field(default_factory=list)
    error_count: int = 0


class FieldScoreOut(APIModel):
    field: str
    scored: int = 0
    # Counted separately: the model's denominator is what it was asked, not
    # what the rule engine was asked.
    genai_scored: int = 0
    genai_accuracy_pct: float | None = None
    python_accuracy_pct: float | None = None
    agreement_pct: float | None = None
    genai_correct: int = 0
    python_correct: int = 0


class EscalationRecallOut(APIModel):
    """
    The non-negotiable metric (policy.yaml targets).

    Reported on its own rather than folded into per-field accuracy, because
    "escalation accuracy 99.8%" reads like success while hiding the one safety
    complaint that was not escalated.
    """

    expected: int = 0
    recalled: int = 0
    recall_pct: float | None = None
    missed: list[str] = Field(default_factory=list)
    over_escalated: int = 0
    target_pct: float = 100.0
    met: bool | None = None


class LatencyOut(APIModel):
    """p95 rather than a mean: NFR 1 caps each complaint, and a mean hides the tail."""

    mean_ms: float | None = None
    p50_ms: float | None = None
    p95_ms: float | None = None
    max_ms: float | None = None


class OverallOut(APIModel):
    genai_accuracy_pct: float | None = None
    python_accuracy_pct: float | None = None
    agreement_pct: float | None = None


class BenchmarkMetricsOut(APIModel):
    sample_size: int = 0
    processed: int = 0
    failed: int = 0
    skipped_unlabelled: int = 0
    genai_available_count: int = 0
    by_field: list[FieldScoreOut] = Field(default_factory=list)
    overall: OverallOut
    mandatory_escalation: EscalationRecallOut
    latency: LatencyOut
    errors: list[dict[str, Any]] = Field(default_factory=list)


class BenchmarkRunOut(APIModel):
    id: str
    label: str
    dataset_tag: str
    sample_size: int = 0
    status: str
    # Provenance: which rules and which prompt produced these numbers. A score
    # without them cannot be reproduced or compared against a later run.
    ruleset_version: str
    prompt_version: str
    provider: str
    model: str
    metrics: dict[str, Any] = Field(default_factory=dict)
    started_at: str | None = None
    finished_at: str | None = None


class RuleFailureOut(APIModel):
    """One case the rules got wrong — each is a rule worth revisiting."""

    public_ref: str
    field: str
    expected: str | None = None
    python: str | None = None
    genai: str | None = None
    explanation: str | None = None


class BenchmarkDetailOut(APIModel):
    id: str
    label: str
    dataset_tag: str
    status: str
    metrics: dict[str, Any] = Field(default_factory=dict)
    ruleset_version: str
    prompt_version: str
    provider: str
    model: str
    rule_failures: list[RuleFailureOut] = Field(default_factory=list)
