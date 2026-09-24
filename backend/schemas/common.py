"""
Shared API schema primitives.

Everything the API returns is a declared Pydantic model.  That is not just
hygiene: SRS 1.6 states twice that "free-form GenAI responses must not be used
as the only application output", so every endpoint has a typed contract that
the frontend generates TypeScript types from.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class APIModel(BaseModel):
    """Base for every response model."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    request_id: str | None = None


class ErrorResponse(BaseModel):
    error: ErrorDetail


class Page(BaseModel, Generic[T]):
    """Uniform pagination envelope (FR lxxi — search and filtering)."""

    items: list[T]
    total: int
    page: int = 1
    page_size: int = 25

    @property
    def pages(self) -> int:
        return max(1, -(-self.total // self.page_size))


class PaginationParams(BaseModel):
    page: int = Field(1, ge=1)
    page_size: int = Field(25, ge=1, le=200)

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


class RefBase(APIModel):
    """A lookup-table reference as returned inside larger payloads."""

    id: uuid.UUID
    code: str
    name: str


class MessageResponse(BaseModel):
    message: str


class HealthResponse(BaseModel):
    """Read by the uptime pinger and by judges checking the deployment."""

    status: str
    app: str
    version: str
    environment: str
    database: str
    knowledge_base_documents: int
    active_rules: int
    llm_primary: str
    llm_configured: bool
    timestamp: datetime


class VersionResponse(BaseModel):
    """
    Provenance endpoint.

    SRS Step 49 requires each analysis to store the prompt version, provider,
    model and policy version.  Exposing the *currently active* set here lets an
    evaluator confirm at a glance what the running system is using.
    """

    app_version: str
    environment: str
    ruleset_version: str
    active_prompts: dict[str, str]
    llm_primary_provider: str
    llm_primary_model: str
    llm_fallback_provider: str | None
    embedding_model: str | None
    knowledge_base_version: str | None
    policy_precedence: list[str]
