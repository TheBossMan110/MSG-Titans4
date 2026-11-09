"""
API v1 aggregate router.

Routers are added here as each module lands.  Keeping the registration in one
place means the OpenAPI schema at /api/docs is always the single source of
truth the frontend generates its TypeScript types from.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from src.api.v1 import (
    admin,
    analytics,
    assistant,
    audit,
    auth,
    benchmark,
    billing,
    company,
    complaints,
    documents,
    email,
    organisation,
    people,
    platform,
    review,
    system,
)
from src.core.permissions import require_company_member

api_router = APIRouter()

# Routers that serve one company's own data refuse a super administrator
# wholesale (src/core/permissions.py): the platform sees totals, never a
# company's complaints, people or emails.
CompanyData = [Depends(require_company_member)]

api_router.include_router(system.router)
api_router.include_router(auth.router)
api_router.include_router(company.router)
api_router.include_router(billing.router)     # each route carries its own gate
api_router.include_router(platform.router)
api_router.include_router(admin.router)       # the shared template: super administrators maintain it
api_router.include_router(audit.router)       # filtered to the caller's organisation
api_router.include_router(documents.router, dependencies=CompanyData)
api_router.include_router(complaints.router, dependencies=CompanyData)
api_router.include_router(review.router, dependencies=CompanyData)
api_router.include_router(analytics.router, dependencies=CompanyData)
api_router.include_router(benchmark.router, dependencies=CompanyData)
api_router.include_router(organisation.router, dependencies=CompanyData)
api_router.include_router(assistant.router, dependencies=CompanyData)
api_router.include_router(email.router, dependencies=CompanyData)
api_router.include_router(people.router, dependencies=CompanyData)
api_router.include_router(people.live_router, dependencies=CompanyData)
api_router.include_router(people.staff_router, dependencies=CompanyData)
