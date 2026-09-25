"""
API v1 aggregate router.

Routers are added here as each module lands.  Keeping the registration in one
place means the OpenAPI schema at /api/docs is always the single source of
truth the frontend generates its TypeScript types from.
"""

from __future__ import annotations

from fastapi import APIRouter

from src.api.v1 import (
    admin,
    assistant,
    analytics,
    audit,
    auth,
    benchmark,
    complaints,
    documents,
    email,
    organisation,
    review,
    system,
)

api_router = APIRouter()

api_router.include_router(system.router)
api_router.include_router(auth.router)
api_router.include_router(documents.router)
api_router.include_router(complaints.router)
api_router.include_router(review.router)
api_router.include_router(analytics.router)
api_router.include_router(benchmark.router)
api_router.include_router(admin.router)
api_router.include_router(audit.router)
api_router.include_router(organisation.router)
api_router.include_router(assistant.router)
api_router.include_router(email.router)
