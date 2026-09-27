"""
System endpoints: health and provenance.

``/health``  — read by the uptime pinger that keeps the free-tier instance warm
               (NFR 5: 99% uptime during evaluation).
``/version`` — provenance.  SRS Step 49 requires every analysis to record the
               prompt version, provider, model and policy version; this shows
               the evaluator what the running system is configured with, right
               now, without digging through logs.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter
from sqlalchemy import func, select

from schemas.common import HealthResponse, VersionResponse
from src.core.config import settings
from src.core.deps import DbSession
from src.db.enums import DocStatus
from src.db.models import AppConfig, DocumentVersion, PromptVersion, Rule

router = APIRouter(tags=["System"])


@router.get("/health", response_model=HealthResponse, summary="Liveness and readiness")
def health(db: DbSession) -> HealthResponse:
    # During a database outage this still answers, "degraded", rather than
    # failing with a 500 that monitors and browsers cannot tell apart.
    active_docs = active_rules = 0
    try:
        db.execute(select(1))
        database = "ok"
        active_docs = db.execute(
            select(func.count())
            .select_from(DocumentVersion)
            .where(DocumentVersion.status == DocStatus.ACTIVE)
        ).scalar_one()
        active_rules = db.execute(
            select(func.count()).select_from(Rule).where(Rule.is_active.is_(True))
        ).scalar_one()
    except Exception:  # pragma: no cover - only on a real outage
        db.rollback()
        database = "unavailable"

    llm_configured = bool(
        settings.gemini_api_key or settings.groq_api_key or settings.openrouter_api_key
    )

    return HealthResponse(
        status="ok" if database == "ok" else "degraded",
        app=settings.app_name,
        version=settings.app_version,
        environment=settings.app_env,
        database=database,
        knowledge_base_documents=active_docs,
        active_rules=active_rules,
        llm_primary=settings.llm_primary_provider,
        llm_configured=llm_configured,
        timestamp=datetime.now(UTC),
    )


@router.get("/version", response_model=VersionResponse, summary="Active configuration provenance")
def version(db: DbSession) -> VersionResponse:
    ruleset = db.get(AppConfig, "ruleset_version")
    precedence = db.get(AppConfig, "policy_precedence")

    active_prompts = {
        row.name: row.version
        for row in db.execute(
            select(PromptVersion).where(PromptVersion.is_active.is_(True))
        ).scalars()
    }

    newest_kb = db.execute(
        select(DocumentVersion.activated_at)
        .where(DocumentVersion.status == DocStatus.ACTIVE)
        .order_by(DocumentVersion.activated_at.desc())
        .limit(1)
    ).scalar_one_or_none()

    return VersionResponse(
        app_version=settings.app_version,
        environment=settings.app_env,
        ruleset_version=(ruleset.value or {}).get("version", "unversioned") if ruleset else "none",
        active_prompts=active_prompts,
        llm_primary_provider=settings.llm_primary_provider,
        llm_primary_model=settings.gemini_model
        if settings.llm_primary_provider == "gemini"
        else settings.groq_model,
        llm_fallback_provider=settings.llm_fallback_provider or None,
        embedding_model=settings.gemini_embed_model if settings.embedding_enabled else None,
        knowledge_base_version=newest_kb.isoformat() if newest_kb else None,
        policy_precedence=(precedence.value or {}).get("order", []) if precedence else [],
    )
