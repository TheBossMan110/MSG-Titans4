"""
SupportNova — application entry point.

    uvicorn src.main:app --reload

The interactive OpenAPI docs at ``/api/docs`` are not just a developer
convenience here: they are the contract the Next.js frontend generates its
TypeScript types from, and they are a judge-facing artefact showing a real,
typed API rather than a handful of ad-hoc endpoints.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from src.api.router import api_router
from src.core.config import settings
from src.core.errors import register_exception_handlers
from src.core.logging import configure_logging, get_logger
from src.core.middleware import RequestContextMiddleware
from src.core.ratelimit import limiter

configure_logging(settings.log_level, json_output=settings.is_production)
log = get_logger("app")

DESCRIPTION = """
**SupportNova** turns a customer complaint into a routed, escalated,
policy-grounded resolution — where a deterministic Python rule engine
independently verifies and, where required, overrides the AI before anything
reaches the customer.

Two pipelines run over the same inputs:

* **Pipeline 1 — GenAI Complaint Intelligence** (`genai_pipeline/`)
  classifies, extracts and drafts, returning strictly-schemaed JSON.
* **Pipeline 2 — Python Ground-Truth Validation** (`python_validation/`)
  reaches its *own* conclusion from the Complaint Resolution Rule Matrix,
  using no language model at all.  It can be run from the command line with
  no API key configured.

Their outputs are reconciled field by field; Python holds veto on department,
urgency, priority, escalation, policy validity and prohibited actions.
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info(
        "startup",
        environment=settings.app_env,
        database="postgresql" if settings.is_postgres else "sqlite",
        llm_primary=settings.llm_primary_provider,
    )
    settings.storage_local_dir.mkdir(parents=True, exist_ok=True)
    settings.reports_dir.mkdir(parents=True, exist_ok=True)
    yield
    log.info("shutdown")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=DESCRIPTION,
    lifespan=lifespan,
    docs_url=f"{settings.api_prefix}/docs",
    redoc_url=f"{settings.api_prefix}/redoc",
    openapi_url=f"{settings.api_prefix}/openapi.json",
    contact={"name": "SupportNova Team"},
    license_info={"name": "MIT"},
)

# ── middleware (outermost first) ─────────────────────────────
app.state.limiter = limiter
app.add_middleware(RequestContextMiddleware)
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "X-Response-Time-ms"],
)

# ── errors ───────────────────────────────────────────────────
register_exception_handlers(app)


@app.exception_handler(RateLimitExceeded)
async def _rate_limited(request, exc):  # noqa: ANN001
    from fastapi.responses import JSONResponse

    from src.core.logging import request_id_ctx

    return JSONResponse(
        status_code=429,
        content={
            "error": {
                "code": "RATE_LIMITED",
                "message": "Too many requests. Please slow down.",
                "details": {"limit": str(exc.detail)},
                "request_id": request_id_ctx.get(),
            }
        },
    )


# ── routes ───────────────────────────────────────────────────
app.include_router(api_router, prefix=settings.api_prefix)


@app.get("/", include_in_schema=False)
def root():
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "docs": f"{settings.api_prefix}/docs",
        "health": f"{settings.api_prefix}/health",
    }
