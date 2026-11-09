"""The super administrator's overview: totals across every company, never one company's rows."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class PlatformCompanies(BaseModel):
    total: int
    active: int
    suspended: int
    new_in_window: int


class PlatformPeople(BaseModel):
    staff: int
    customers: int


class CompanyVolume(BaseModel):
    name: str
    is_active: bool
    is_reference: bool
    complaints: int
    open_complaints: int


class BenchmarkSummary(BaseModel):
    """The latest accuracy measurement against a labelled dataset."""

    label: str | None = None
    dataset_tag: str | None = None
    finished_at: datetime | None = None
    sample_size: int | None = None
    genai_accuracy_pct: float | None = None
    python_accuracy_pct: float | None = None
    agreement_pct: float | None = None
    escalation_recall_pct: float | None = None
    by_field: list[dict[str, Any]] = Field(default_factory=list)


class PlatformOverview(BaseModel):
    """
    The aggregate blocks are the same dictionaries each company's own analytics
    return, computed across every company, so a company's figures and the
    platform's are always measured the same way.
    """

    window_days: int | None = None
    generated_at: datetime
    companies: PlatformCompanies
    people: PlatformPeople
    by_company: list[CompanyVolume]
    complaints: dict[str, Any]
    priorities: dict[str, int]
    escalation: dict[str, Any]
    sla: dict[str, Any]
    resolution_time: dict[str, Any]
    agreement: dict[str, Any]
    traceability: dict[str, Any]
    safety: dict[str, Any]
    ai: dict[str, Any]
    benchmark: BenchmarkSummary | None = None
