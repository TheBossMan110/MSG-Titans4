"""
Seed the organisation taxonomy, runtime configuration and deterministic signals.

Everything here comes from ``config/*.yaml`` — nothing is hard-coded in Python.
That is deliberate: it is the mechanism behind SRS 1.8 #5 (a new complaint
category must be processable through configuration) and #14 (live modification
without a deploy).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.logging import get_logger
from src.db.models import (
    AppConfig,
    Category,
    Department,
    EscalationLevel,
    InjectionPattern,
    LexiconTerm,
    PriorityLevel,
    PromisePattern,
    SLAPolicy,
    Subcategory,
)
from src.db.seed.loader import load_yaml, upsert

log = get_logger("seed")


# ══════════════════════════════════════════════════════════════════════
# taxonomy.yaml
# ══════════════════════════════════════════════════════════════════════
def seed_taxonomy(db: Session) -> dict[str, int]:
    data = load_yaml("taxonomy.yaml")
    counts = {"departments": 0, "categories": 0, "subcategories": 0,
              "priority_levels": 0, "escalation_levels": 0, "sla_policies": 0}

    # ── departments ──
    for row in data.get("departments", []):
        _, created = upsert(
            db, Department,
            match={"code": row["code"]},
            values={"name": row["name"], "description": row.get("description"),
                    "email": row.get("email"), "is_active": True},
        )
        counts["departments"] += 1
        log.debug("department", code=row["code"], created=created)

    dept_by_code = {d.code: d for d in db.execute(select(Department)).scalars()}

    # ── priority ladder ──
    for row in data.get("priority_levels", []):
        upsert(
            db, PriorityLevel,
            match={"code": row["code"]},
            values={"name": row["name"], "rank": row["rank"],
                    "description": row.get("description")},
        )
        counts["priority_levels"] += 1

    # ── escalation ladder ──
    for row in data.get("escalation_levels", []):
        upsert(
            db, EscalationLevel,
            match={"code": row["code"]},
            values={"name": row["name"], "rank": row["rank"],
                    "description": row.get("description")},
        )
        counts["escalation_levels"] += 1

    # ── categories ──
    for row in data.get("categories", []):
        default_dept = dept_by_code.get(row.get("default_department", ""))
        upsert(
            db, Category,
            match={"code": row["code"]},
            values={
                "name": row["name"],
                "description": row.get("description"),
                "default_department_id": default_dept.id if default_dept else None,
                "is_active": True,
            },
        )
        counts["categories"] += 1

    cat_by_code = {c.code: c for c in db.execute(select(Category)).scalars()}

    # ── subcategories ──
    for cat_code, subs in (data.get("subcategories") or {}).items():
        category = cat_by_code.get(cat_code)
        if category is None:
            log.warning("subcategory_orphan", category=cat_code)
            continue
        for sub in subs:
            upsert(
                db, Subcategory,
                match={"category_id": category.id, "code": sub["code"]},
                values={"name": sub["name"], "is_active": True},
            )
            counts["subcategories"] += 1

    # ── SLA policies ──
    sla = data.get("sla_policies") or {}
    risk_pct = int(sla.get("risk_threshold_pct", 75))

    for row in sla.get("default", []):
        upsert(
            db, SLAPolicy,
            match={"category_id": None, "priority_code": row["priority"]},
            values={
                "first_response_mins": row["first_response_mins"],
                "resolution_mins": row["resolution_mins"],
                "risk_threshold_pct": risk_pct,
                "is_active": True,
            },
        )
        counts["sla_policies"] += 1

    for row in sla.get("overrides", []):
        category = cat_by_code.get(row["category"])
        if category is None:
            log.warning("sla_override_orphan", category=row["category"])
            continue
        upsert(
            db, SLAPolicy,
            match={"category_id": category.id, "priority_code": row["priority"]},
            values={
                "first_response_mins": row["first_response_mins"],
                "resolution_mins": row["resolution_mins"],
                "risk_threshold_pct": risk_pct,
                "is_active": True,
            },
        )
        counts["sla_policies"] += 1

    # Organisation profile is config, not a table of its own.
    upsert(
        db, AppConfig,
        match={"key": "organisation"},
        values={"value": data.get("organisation", {}),
                "description": "Fictional organisation profile (SRS 1.8 #1)."},
    )

    # What the dataset says about each team beyond its name and mailbox: who
    # it escalates to, what it handles, the hours it commits to. Display-only,
    # so it lives beside the profile rather than as columns nothing queries.
    upsert(
        db, AppConfig,
        match={"key": "department_profiles"},
        values={
            "value": {
                row["code"]: {
                    "escalation_contact": row.get("escalation_contact"),
                    "handles": row.get("handles") or [],
                    "sla_response_hours": row.get("sla_response_hours"),
                    "sla_resolution_hours": row.get("sla_resolution_hours"),
                    "source_id": row.get("source_id"),
                }
                for row in data.get("departments", [])
            },
            "description": "Per-department escalation contact, remit and SLA hours, from the dataset.",
        },
    )
    upsert(
        db, AppConfig,
        match={"key": "response_templates"},
        values={
            "value": data.get("response_templates", []),
            "description": "The organisation's reply templates, as authored in the dataset.",
        },
    )

    log.info("seeded_taxonomy", **counts)
    return counts


# ══════════════════════════════════════════════════════════════════════
# policy.yaml  ->  app_config
# ══════════════════════════════════════════════════════════════════════
_CONFIG_DESCRIPTIONS: dict[str, str] = {
    "policy_precedence": "Documented policy precedence order (SRS 1.8 #10).",
    "comparison_weights": "Per-field severity and which pipeline wins (FR xlvi-li).",
    "verification": "Verification decision thresholds and review triggers (SRS Step 57).",
    "scoring": "Formulas and targets for the computed verification scores (FR li).",
    "thresholds": "Duplicate, repeat, hallucination and retrieval thresholds.",
    "response_guard": "Unsupported-promise guard behaviour (SRS Step 34).",
}


def seed_policy_config(db: Session) -> dict[str, int]:
    data = load_yaml("policy.yaml")
    count = 0
    for key, value in data.items():
        upsert(
            db, AppConfig,
            match={"key": key},
            values={"value": value, "description": _CONFIG_DESCRIPTIONS.get(key)},
        )
        count += 1

    # The ruleset version is stamped onto every validation run so a result can
    # always be traced back to the exact rules that produced it.
    existing = db.get(AppConfig, "ruleset_version")
    if existing is None:
        upsert(
            db, AppConfig,
            match={"key": "ruleset_version"},
            values={"value": {"version": "0.0.0", "rule_count": 0},
                    "description": "Bumped whenever any rule changes."},
        )
        count += 1

    log.info("seeded_policy_config", keys=count)
    return {"app_config": count}


# ══════════════════════════════════════════════════════════════════════
# signals.yaml
# ══════════════════════════════════════════════════════════════════════
def seed_signals(db: Session) -> dict[str, int]:
    """
    Load the deterministic signal configuration.

    Two files, one table:
      signals.yaml  RISK vocabulary  -> urgency, escalation
      topics.yaml   TOPIC vocabulary -> category, department

    They are separate documents because they answer different questions, and
    because Pipeline 2 must be able to decide what a complaint is *about*
    without consulting the model it is meant to check.
    """
    data = load_yaml("signals.yaml")
    topics = load_yaml("topics.yaml")

    # Merged for lexicon loading; a duplicate signal_key would be an authoring
    # error, so it is reported rather than silently overwritten.
    merged_lexicon: dict[str, Any] = dict(data.get("lexicon") or {})
    for signal_key, spec in (topics.get("lexicon") or {}).items():
        if signal_key in merged_lexicon:
            log.warning("duplicate_signal_key", signal_key=signal_key)
        merged_lexicon[signal_key] = spec

    counts = {"lexicon_terms": 0, "injection_patterns": 0,
              "promise_patterns": 0, "entity_patterns": 0}

    # ── risk + topic lexicons ──
    for signal_key, spec in merged_lexicon.items():
        weight = float(spec.get("weight", 1.0))
        description = spec.get("description")
        for term in spec.get("terms", []):
            upsert(
                db, LexiconTerm,
                match={"signal_key": signal_key, "term": term["t"]},
                values={
                    "match_type": term.get("m", "PHRASE"),
                    "weight": weight,
                    "description": description,
                    "is_active": True,
                },
            )
            counts["lexicon_terms"] += 1

    # Signals flagged analytics_only must never drive urgency/priority.
    analytics_only = [
        key for key, spec in merged_lexicon.items() if spec.get("analytics_only")
    ]
    upsert(
        db, AppConfig,
        match={"key": "analytics_only_signals"},
        values={
            "value": analytics_only,
            "description": (
                "Signals that MUST NOT influence urgency or priority. "
                "Enforced by tests/test_rule_engine.py (SRS 1.8 #6)."
            ),
        },
    )

    # ── injection patterns ──
    for group in data.get("injection_patterns", []):
        for pattern in group.get("patterns", []):
            upsert(
                db, InjectionPattern,
                match={"pattern": pattern},
                values={
                    "label": group["label"],
                    "severity": group.get("severity", "MEDIUM"),
                    "is_active": True,
                },
            )
            counts["injection_patterns"] += 1

    # ── promise patterns ──
    for group in data.get("promise_patterns", []):
        for pattern in group.get("patterns", []):
            upsert(
                db, PromisePattern,
                match={"pattern": pattern},
                values={
                    "promise_type": group["promise_type"],
                    # The column is named requires_action for historical
                    # reasons; it holds the EligibilityType that must be
                    # ELIGIBLE for this promise to be supported.
                    "requires_action": group.get("requires_eligibility"),
                    "is_active": True,
                },
            )
            counts["promise_patterns"] += 1

    # ── entity regexes -> config (used by the deterministic extractor) ──
    entity_patterns: dict[str, Any] = data.get("entity_patterns") or {}
    upsert(
        db, AppConfig,
        match={"key": "entity_patterns"},
        values={"value": entity_patterns,
                "description": "Deterministic entity regexes for Pipeline 2 (SRS Step 16)."},
    )
    counts["entity_patterns"] = len(entity_patterns)

    log.info("seeded_signals", **counts)
    return counts
