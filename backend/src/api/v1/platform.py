"""
The platform's own view, for the super administrators.

    GET /platform/overview   totals across every company and how the system is doing

A super administrator sees the platform, not its tenants: every company's
counts and the system's accuracy, safety and health, but no company's
complaints, customers, people or emails. Every other business endpoint refuses
the role, because no role list there includes it.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from schemas.platform import PlatformOverview
from src.core.deps import DbSession
from src.core.permissions import require_platform_staff
from src.db.enums import UserRole
from src.services import platform as platform_service

router = APIRouter(prefix="/platform", tags=["Platform"])


@router.get(
    "/overview",
    response_model=PlatformOverview,
    dependencies=[Depends(require_platform_staff(UserRole.SUPERADMIN))],
    summary="Totals across every company, and how the system is doing (super administrators only)",
)
def overview(
    db: DbSession,
    days: int | None = Query(None, ge=1, le=3650, description="Window in days; omit for all time."),
) -> PlatformOverview:
    return PlatformOverview(**platform_service.overview(db, days=days))
