"""
Plans and subscriptions.

    GET   /billing/subscription     your company's plan and this month's usage (administrators)
    POST  /billing/requests         ask for a plan, from the pricing page (anyone)
    GET   /billing/requests         every request (super administrators)
    PATCH /billing/requests/{id}    mark a request contacted, won or lost (super administrators)

Setting a company's plan is on /company/{id}/subscription, beside its status.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy import func, select

from schemas.billing import (
    PlanRequestAccepted,
    PlanRequestIn,
    PlanRequestList,
    PlanRequestOut,
    PlanRequestStatusIn,
    SubscriptionOut,
)
from src.core import billing
from src.core.deps import CurrentUser, DbSession, OptionalUser, require_role
from src.core.errors import NotFoundError, ValidationError
from src.core.permissions import require_platform_staff
from src.core.ratelimit import limiter
from src.db.enums import UserRole
from src.db.models import PlanRequest

router = APIRouter(prefix="/billing", tags=["Billing"])
PlatformOnly = Depends(require_platform_staff(UserRole.SUPERADMIN))


@router.get(
    "/subscription",
    response_model=SubscriptionOut,
    dependencies=[Depends(require_role(UserRole.ADMIN))],
    summary="Your company's plan and what it has used this month",
)
def my_subscription(db: DbSession, user: CurrentUser) -> SubscriptionOut:
    return SubscriptionOut(**billing.view(db, user.organisation_id))


@router.post(
    "/requests",
    response_model=PlanRequestAccepted,
    status_code=status.HTTP_201_CREATED,
    summary="Ask to join a plan or change plan",
)
@limiter.limit("5/hour")
def request_plan(
    payload: PlanRequestIn, request: Request, response: Response, db: DbSession, user: OptionalUser,
) -> PlanRequestAccepted:
    """
    Open to anyone, so it is rate-limited and stores plain text only. A filled
    honeypot gets the same answer as a real request and is not kept, so a bot
    learns nothing from the response.
    """
    if payload.website:
        return PlanRequestAccepted()
    if payload.plan_code not in billing.PLANS:
        raise ValidationError("That is not one of our plans.")
    db.add(PlanRequest(
        company_name=payload.company_name.strip(), contact_name=payload.contact_name.strip(),
        email=str(payload.email).strip().lower(), phone=(payload.phone or "").strip() or None,
        plan_code=payload.plan_code, billing_cycle=payload.billing_cycle, team_size=payload.team_size,
        monthly_complaints=payload.monthly_complaints, message=(payload.message or "").strip() or None,
        organisation_id=user.organisation_id if user is not None and user.role == UserRole.ADMIN else None,
    ))
    db.flush()
    return PlanRequestAccepted()


def _out(row: PlanRequest) -> PlanRequestOut:
    return PlanRequestOut(
        id=row.id, company_name=row.company_name, contact_name=row.contact_name, email=row.email, phone=row.phone,
        plan_code=row.plan_code, billing_cycle=row.billing_cycle, team_size=row.team_size,
        monthly_complaints=row.monthly_complaints, message=row.message, status=row.status,
        existing_customer=row.organisation_id is not None, created_at=row.created_at,
    )


@router.get("/requests", response_model=PlanRequestList, dependencies=[PlatformOnly], summary="Requests from the pricing page")
def list_requests(db: DbSession, limit: int = Query(100, ge=1, le=500)) -> PlanRequestList:
    rows = db.execute(select(PlanRequest).order_by(PlanRequest.created_at.desc()).limit(limit)).scalars().all()
    waiting = db.execute(select(func.count(PlanRequest.id)).where(PlanRequest.status == "NEW")).scalar_one()
    return PlanRequestList(new=waiting, items=[_out(row) for row in rows])


@router.patch("/requests/{request_id}", response_model=PlanRequestOut, dependencies=[PlatformOnly], summary="Update a request's status")
def update_request(request_id: uuid.UUID, payload: PlanRequestStatusIn, db: DbSession) -> PlanRequestOut:
    row = db.get(PlanRequest, request_id)
    if row is None:
        raise NotFoundError("No such request.")
    row.status = payload.status
    db.flush()
    return _out(row)
