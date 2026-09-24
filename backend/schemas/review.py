"""
Review queue and SLA API contracts.

The override payload is deliberately explicit rather than a free-form patch.
A reviewer changing a category is a different, separately-audited act from one
reassigning a department, and a generic "update these fields" endpoint would
collapse both into a single indistinguishable edit.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import Field, model_validator

from schemas.common import APIModel


class ReviewItemOut(APIModel):
    """One complaint waiting for a human."""

    id: uuid.UUID
    complaint_id: uuid.UUID
    public_ref: str
    title: str
    status: str
    reasons: list[str] = Field(default_factory=list)
    priority_code: str | None = None
    category: str | None = None
    department: str | None = None
    urgency: str | None = None
    escalation_code: str | None = None
    verification_outcome: str | None = None
    assigned_to: uuid.UUID | None = None
    sla_breached: bool = False
    sla_at_risk: bool = False
    created_at: datetime | None = None
    closed_at: datetime | None = None


class ReviewActionRequest(APIModel):
    """
    One reviewer action.

    ``action`` says what kind of act this is; the optional fields say what it
    changed. An escalation may be raised but never lowered below the mandatory
    floor — the endpoint refuses explicitly rather than silently ignoring it,
    because a reviewer who believes they lowered an escalation and did not is
    worse off than one who was told no.
    """

    action: str = Field(max_length=24)
    comment: str | None = Field(default=None, max_length=2000)

    category: str | None = Field(default=None, max_length=64)
    subcategory: str | None = Field(default=None, max_length=64)
    department: str | None = Field(default=None, max_length=64)
    urgency: str | None = Field(default=None, max_length=16)
    priority: str | None = Field(default=None, max_length=8)
    escalation: str | None = Field(default=None, max_length=64)
    assign_to: uuid.UUID | None = None

    @model_validator(mode="after")
    def _modifications_need_a_change(self) -> ReviewActionRequest:
        """
        A modifying action must actually modify something.

        Recording a RECLASSIFY that changed nothing would put a misleading
        override in the audit trail and inflate the override rate, which is a
        number the analytics treat as a signal that a rule is wrong.
        """
        modifying = self.action.strip().upper() in {
            "MODIFY", "RECLASSIFY", "REASSIGN", "ESCALATE", "OVERRIDE",
        }
        if modifying and not any(
            (
                self.category, self.subcategory, self.department, self.urgency,
                self.priority, self.escalation, self.assign_to,
            )
        ):
            raise ValueError(
                f"{self.action} requires at least one field to change."
            )
        return self


class ReviewActionOut(APIModel):
    action: str
    is_override: bool
    changed: dict[str, Any] = Field(default_factory=dict)
    queue_closed: bool = False
    escalation_raised: bool = False


class ReviewHistoryOut(APIModel):
    action: str
    is_override: bool
    actor_id: str | None = None
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    comment: str | None = None
    at: str | None = None


class SLAStatusOut(APIModel):
    event_type: str
    due_at: str | None = None
    met_at: str | None = None
    breached: bool = False
    at_risk: bool = False


class SLASweepOut(APIModel):
    """What the breach sweep found."""

    checked: int
    breached: list[str] = Field(default_factory=list)
    at_risk: list[str] = Field(default_factory=list)
    # Complaints whose category and priority match no policy get no clock
    # rather than a guessed one, and are counted here so the gap is visible.
    no_policy: int = 0
    evaluated_at: str


class QueueStatsOut(APIModel):
    depth: dict[str, int] = Field(default_factory=dict)
    override_rate: dict[str, Any] = Field(default_factory=dict)
