"""System endpoint and taxonomy-minimum tests."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from src.db.models import (
    Category,
    Department,
    EscalationLevel,
    InjectionPattern,
    LexiconTerm,
    PriorityLevel,
    PromisePattern,
    Subcategory,
)


@pytest.mark.unit
def test_health_is_public_and_reports_ok(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["app"] == "SupportNova"


@pytest.mark.unit
def test_version_exposes_provenance(client):
    resp = client.get("/api/version")
    assert resp.status_code == 200
    body = resp.json()
    # SRS Step 49: provider, model and policy precedence must be traceable.
    assert body["llm_primary_provider"]
    assert isinstance(body["policy_precedence"], list)
    assert "ACTIVE_POLICY" in body["policy_precedence"]


@pytest.mark.unit
def test_root_advertises_the_docs(client):
    body = client.get("/").json()
    assert body["docs"] == "/api/docs"


@pytest.mark.unit
def test_openapi_schema_builds(client):
    spec = client.get("/api/openapi.json").json()
    assert spec["info"]["title"] == "SupportNova"
    assert "/api/auth/login" in spec["paths"]


# ── SRS dataset minimums (section 1.2 Hint) ──────────────────────────
@pytest.mark.unit
def test_taxonomy_meets_srs_minimums(db):
    """
    SRS requires at least 10 complaint categories, 20 subcategories and
    8 responsible departments.
    """
    categories = db.execute(select(func.count()).select_from(Category)).scalar_one()
    subcategories = db.execute(select(func.count()).select_from(Subcategory)).scalar_one()
    departments = db.execute(select(func.count()).select_from(Department)).scalar_one()

    assert categories >= 10, f"SRS requires >=10 categories, found {categories}"
    assert subcategories >= 20, f"SRS requires >=20 subcategories, found {subcategories}"
    assert departments >= 8, f"SRS requires >=8 departments, found {departments}"


@pytest.mark.unit
def test_priority_and_escalation_ladders_are_ordered(db):
    """
    Ranks must be a contiguous ordered ladder — the mandatory escalation floor
    is expressed as a rank comparison, so gaps or duplicates would break it.
    """
    priorities = sorted(
        db.execute(select(PriorityLevel)).scalars(), key=lambda p: p.rank
    )
    escalations = sorted(
        db.execute(select(EscalationLevel)).scalars(), key=lambda e: e.rank
    )

    assert [p.rank for p in priorities] == list(range(len(priorities)))
    assert [e.rank for e in escalations] == list(range(len(escalations)))
    assert escalations[0].code == "NONE", "rank 0 must mean 'no escalation'"


@pytest.mark.unit
def test_signal_configuration_is_loaded(db):
    lexicon = db.execute(select(func.count()).select_from(LexiconTerm)).scalar_one()
    injection = db.execute(select(func.count()).select_from(InjectionPattern)).scalar_one()
    promises = db.execute(select(func.count()).select_from(PromisePattern)).scalar_one()

    assert lexicon > 50, "risk lexicons drive Pipeline 2's independent judgement"
    assert injection >= 20, "SRS asks for >=20 prompt-injection cases to defend against"
    assert promises >= 10, "response guard needs a meaningful promise-pattern library"


@pytest.mark.unit
def test_safety_lexicon_exists_for_the_sentiment_urgency_trap(db):
    """
    SRS 1.8 #6: a calmly written safety complaint must still be critical.
    That is only possible if safety risk is detectable from the words alone.
    """
    terms = db.execute(
        select(LexiconTerm).where(LexiconTerm.signal_key == "safety_lexicon_hit")
    ).scalars().all()
    assert len(terms) >= 10
    assert any("burning smell" in t.term for t in terms)


@pytest.mark.unit
def test_emotional_signals_are_marked_analytics_only(db):
    """
    Emotional intensity must never be allowed to drive urgency or priority.
    The seeder records which signals are analytics-only; the rule engine test
    suite enforces that no rule uses them.
    """
    from src.db.models import AppConfig

    cfg = db.get(AppConfig, "analytics_only_signals")
    assert cfg is not None
    assert "emotional_intensity" in cfg.value
