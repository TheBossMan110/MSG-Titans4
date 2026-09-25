"""The organisation as the dataset defines it, for staff to browse."""

from __future__ import annotations

from typing import Any

from schemas.common import APIModel


class OrganisationProfileOut(APIModel):
    name: str | None = None
    legal_name: str | None = None
    industry: str | None = None
    founded_year: int | None = None
    regions: list[str] = []
    branches: list[str] = []
    services: list[str] = []
    customer_types: list[str] = []
    support_hours: str | None = None


class TeamOut(APIModel):
    code: str
    name: str
    description: str | None = None
    email: str | None = None
    escalation_contact: str | None = None
    handles: list[str] = []
    sla_response_hours: float | None = None
    sla_resolution_hours: float | None = None
    categories: list[str] = []
    open_complaints: int = 0
    total_complaints: int = 0


class SubcategoryBrief(APIModel):
    code: str
    name: str


class CategoryOut(APIModel):
    code: str
    name: str
    description: str | None = None
    default_department: str | None = None
    subcategories: list[SubcategoryBrief] = []
    complaints: int = 0


class SLARowOut(APIModel):
    category: str | None = None
    priority: str
    first_response_mins: int
    resolution_mins: int


class TemplateOut(APIModel):
    id: str
    scenario: str | None = None
    tone: str | None = None
    text: str


class CustomerMixOut(APIModel):
    customer_type: str
    complaints: int


class DatasetBrief(APIModel):
    dataset_tag: str
    total: int
    analysed: int
    labelled: int


class OrganisationOut(APIModel):
    profile: OrganisationProfileOut
    departments: list[TeamOut]
    categories: list[CategoryOut]
    sla: list[SLARowOut]
    templates: list[TemplateOut]
    customer_mix: list[CustomerMixOut]
    datasets: list[DatasetBrief]
    knowledge_base: dict[str, Any]
