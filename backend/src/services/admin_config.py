"""
Live configuration and rule editing (SRS 1.8 #14, the Live Modification Challenge).

    "The system's behaviour must be modifiable during evaluation without a
     redeployment."                                          — SRS 1.8 #14

Everything that decides anything in SupportNova is already a database row:
taxonomy, rules, lexicons, thresholds, comparison weights, SLA targets and
prompt versions. This module is the editing surface over those rows, and the
guards that keep the surface from becoming a back door.

**Refused at save time, never at evaluation time.** An administrator editing a
rule in front of judges is told immediately that a condition is malformed or
references a signal nothing emits. The alternative is a rule that saves
cleanly and then silently never fires, which looks exactly like the system
ignoring the evaluator.

**A mandatory escalation rule cannot be edited into harmlessness.** The
escalation floor is enforced against the model, against the comparison engine
and against a human reviewer. An admin API able to deactivate the rule that
*sets* the floor, or to weaken the level it sets, would be a fourth way
through — and the quietest of the four, because it leaves no override on the
complaint to notice. Raising is allowed, lowering is not, which is the same
rule everywhere else.

**Every change is audited and every rule change bumps the ruleset version.**
Each ``validation_run`` stamps that version, so a result recorded before the
edit stays traceable to the rules that actually produced it. Without the bump,
re-reading an old run would attribute it to the new matrix.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from python_validation.conditions import referenced_signals, validate_condition
from src.core.logging import get_logger
from src.db.models import (
    AppConfig,
    Category,
    Department,
    EscalationLevel,
    LexiconTerm,
    PriorityLevel,
    Rule,
    SLAPolicy,
    Subcategory,
    User,
)

log = get_logger("services.admin_config")


class ConfigRefused(Exception):
    """The change was rejected. Carries the specific problems, not a summary."""

    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("; ".join(problems))


# ══════════════════════════════════════════════════════════════
# app_config
# ══════════════════════════════════════════════════════════════
# Rows whose *shape* other code depends on structurally rather than by value.
# Editing the value is fine; replacing the object with a different shape would
# break the reader rather than change the behaviour, so these are read-only
# here and changed by redeploying the seed.
STRUCTURAL_KEYS: frozenset[str] = frozenset(
    {
        # Stamped onto every validation run. Hand-editing it would detach
        # stored results from the rules that produced them.
        "ruleset_version",
        # SRS 1.8 #6: signals that must never influence urgency or priority.
        # Editable only by changing which signals are analytics-only, and a
        # test enforces the list against the lexicon.
        "analytics_only_signals",
    }
)


def config_entries(db: Session) -> list[dict[str, Any]]:
    """Every configuration row, with who last changed it."""
    rows = db.execute(
        select(AppConfig, User.email)
        .outerjoin(User, AppConfig.updated_by == User.id)
        .order_by(AppConfig.key)
    ).all()

    return [
        {
            "key": row.key,
            "value": row.value,
            "description": row.description,
            "version": row.version or 1,
            "updated_by": email,
            "updated_at": row.updated_at,
            "editable": row.key not in STRUCTURAL_KEYS,
        }
        for row, email in rows
    ]


def set_config(
    db: Session, key: str, value: Any, *, actor: User
) -> tuple[dict[str, Any], Any]:
    """
    Replace one configuration value. Returns ``(entry, previous_value)``.

    The previous value comes back so the caller can write a truthful audit
    row: an audit entry whose before and after are identical records nothing,
    and that is what happens when the snapshot is taken after the write.
    """
    row = db.get(AppConfig, key)
    if row is None:
        raise ConfigRefused([f"No configuration key '{key}'."])

    if key in STRUCTURAL_KEYS:
        raise ConfigRefused(
            [
                f"'{key}' is derived, not configured. "
                "Editing it by hand would detach stored results from the "
                "configuration that produced them."
            ]
        )

    if value is None:
        raise ConfigRefused([f"'{key}' cannot be null."])

    previous = row.value
    if type(value) is not type(previous) and previous is not None:
        # A list where an object was expected does not fail here; it fails
        # deep inside the rule engine on the next complaint, which is a much
        # worse place to find out.
        raise ConfigRefused(
            [
                f"'{key}' holds a {type(previous).__name__}; "
                f"got a {type(value).__name__}. The readers of this key expect "
                "the existing shape."
            ]
        )

    row.value = value
    row.version = (row.version or 1) + 1
    row.updated_by = actor.id
    row.updated_at = datetime.now(UTC)
    db.flush()

    log.info("config_changed", key=key, by=actor.email, version=row.version)
    return (
        {
            "key": row.key,
            "value": row.value,
            "description": row.description,
            "version": row.version,
            "updated_by": actor.email,
            "updated_at": row.updated_at,
            "editable": True,
        },
        previous,
    )


# ══════════════════════════════════════════════════════════════
# taxonomy
# ══════════════════════════════════════════════════════════════
def taxonomy(db: Session) -> dict[str, list[dict[str, Any]]]:
    """
    Every vocabulary the rules are written against.

    Read-only. A category code appears in rule outcomes, in SLA policies, in
    stored complaints and in the ground-truth labels, so renaming one from a
    form would silently orphan all four.
    """

    def codes(model: Any, *, ranked: bool = False) -> list[dict[str, Any]]:
        order = model.rank if ranked else model.code
        return [
            {
                "code": row.code,
                "name": row.name,
                "description": getattr(row, "description", None),
                "rank": getattr(row, "rank", None),
            }
            for row in db.execute(select(model).order_by(order)).scalars()
        ]

    return {
        "categories": codes(Category),
        "subcategories": codes(Subcategory),
        "departments": codes(Department),
        "priority_levels": codes(PriorityLevel, ranked=True),
        "escalation_levels": codes(EscalationLevel, ranked=True),
    }


def _known_codes(db: Session) -> dict[str, set[str]]:
    return {
        "category": {r.code for r in db.execute(select(Category)).scalars()},
        "subcategory": {r.code for r in db.execute(select(Subcategory)).scalars()},
        "department": {r.code for r in db.execute(select(Department)).scalars()},
        "priority": {r.code for r in db.execute(select(PriorityLevel)).scalars()},
        "escalation": {r.code for r in db.execute(select(EscalationLevel)).scalars()},
    }


# ══════════════════════════════════════════════════════════════
# rules
# ══════════════════════════════════════════════════════════════
@dataclass(slots=True)
class RuleChange:
    """One applied edit."""

    rule: Rule
    changed_fields: list[str] = field(default_factory=list)
    before: dict[str, Any] = field(default_factory=dict)
    after: dict[str, Any] = field(default_factory=dict)


def _escalation_ranks(db: Session) -> dict[str, int]:
    return {row.code: row.rank for row in db.execute(select(EscalationLevel)).scalars()}


def rule_view(db: Session, rule: Rule, *, detail: bool = False) -> dict[str, Any]:
    """One rule as the admin API presents it."""
    payload: dict[str, Any] = {
        "rule_ref": rule.rule_ref,
        "name": rule.name,
        "rule_type": rule.rule_type,
        "precedence": rule.precedence,
        "is_active": rule.is_active,
        "is_mandatory_escalation": rule.is_mandatory_escalation,
        "is_catch_all": rule.is_catch_all,
        "outcome_escalation_code": rule.outcome_escalation_code,
        "outcome_urgency": rule.outcome_urgency,
        "outcome_priority_code": rule.outcome_priority_code,
        "version": rule.version or 1,
        # A mandatory escalation rule is the thing that sets the floor. It is
        # editable, but not into silence.
        "can_deactivate": not rule.is_mandatory_escalation,
    }
    if not detail:
        return payload

    def code_of(row: Any) -> str | None:
        return row.code if row is not None else None

    payload.update(
        {
            "conditions": rule.conditions,
            "rationale": rule.rationale,
            "policy_refs": rule.policy_refs,
            "required_actions": rule.required_actions,
            "prohibited_actions": rule.prohibited_actions,
            "eligibility": rule.eligibility,
            "follow_up_required": bool(rule.follow_up_required),
            "source_ref": rule.source_ref,
            "outcome_category": code_of(rule.outcome_category),
            "outcome_subcategory": code_of(rule.outcome_subcategory),
            "outcome_department": code_of(rule.outcome_department),
            "outcome_support_department": code_of(rule.outcome_support_department),
            "signals_referenced": sorted(referenced_signals(rule.conditions)),
        }
    )
    return payload


def load_rule(db: Session, rule_ref: str) -> Rule:
    rule = db.execute(
        select(Rule).where(Rule.rule_ref == rule_ref.strip().upper())
    ).scalars().first()
    if rule is None:
        raise ConfigRefused([f"No rule '{rule_ref}'."])
    return rule


def list_rules(
    db: Session,
    *,
    rule_type: str | None = None,
    active: bool | None = None,
    mandatory: bool | None = None,
    search: str | None = None,
) -> list[Rule]:
    query = select(Rule)
    if rule_type:
        query = query.where(Rule.rule_type == rule_type.strip().upper())
    if active is not None:
        query = query.where(Rule.is_active.is_(active))
    if mandatory is not None:
        query = query.where(Rule.is_mandatory_escalation.is_(mandatory))
    if search:
        needle = f"%{search.strip().lower()}%"
        query = query.where(
            func.lower(Rule.name).like(needle) | func.lower(Rule.rule_ref).like(needle)
        )
    return list(
        db.execute(query.order_by(Rule.precedence.desc(), Rule.rule_ref)).scalars()
    )


def _check_signals(db: Session, conditions: Any) -> list[str]:
    """
    Every signal the condition names must be one the lexicon can raise.

    A rule that tests a signal nothing emits never fires, and reads in the
    matrix as though the case is covered. That exact mistake made a whole
    promise check vacuous once already.
    """
    wanted = referenced_signals(conditions)
    if not wanted:
        return []

    known = {
        row.signal_key
        for row in db.execute(
            select(LexiconTerm).where(LexiconTerm.is_active.is_(True))
        ).scalars()
    }
    # Facts are not lexicon signals; they are derived values the engine
    # supplies, so only true signal nodes are checked here.
    unknown = sorted(wanted - known)
    return [
        f"condition references signal '{signal}' that no active lexicon term raises"
        for signal in unknown
    ]


def update_rule(
    db: Session, rule_ref: str, changes: dict[str, Any], *, actor: User
) -> RuleChange:
    """
    Apply an edit to one rule, or refuse it with the specific problems.

    Only the fields supplied are touched, so an evaluator can flip a single
    precedence without restating the whole rule and accidentally clearing its
    rationale.
    """
    rule = load_rule(db, rule_ref)
    problems: list[str] = []
    codes = _known_codes(db)

    # ── the floor guard ──
    if rule.is_mandatory_escalation:
        if changes.get("is_active") is False:
            problems.append(
                f"{rule.rule_ref} sets a mandatory escalation floor and cannot be "
                "deactivated. The floor is enforced against the model, the "
                "comparison engine and a human reviewer; switching off the rule "
                "that sets it would be a quieter way through than any of them."
            )
        proposed = changes.get("outcome_escalation_code")
        if proposed:
            ranks = _escalation_ranks(db)
            current_rank = ranks.get(rule.outcome_escalation_code or "")
            new_rank = ranks.get(proposed.strip().upper())
            if new_rank is None:
                problems.append(f"unknown escalation level '{proposed}'")
            elif current_rank is not None and new_rank < current_rank:
                problems.append(
                    f"{rule.rule_ref} is a mandatory escalation: its level may be "
                    f"raised but not lowered from {rule.outcome_escalation_code} "
                    f"to {proposed.strip().upper()}."
                )

    # ── conditions ──
    if "conditions" in changes and changes["conditions"] is not None:
        problems.extend(validate_condition(changes["conditions"]))
        problems.extend(_check_signals(db, changes["conditions"]))

    # ── outcome codes must exist ──
    for field_name, vocabulary in (
        ("outcome_category", "category"),
        ("outcome_subcategory", "subcategory"),
        ("outcome_department", "department"),
        ("outcome_priority_code", "priority"),
        ("outcome_escalation_code", "escalation"),
    ):
        proposed = changes.get(field_name)
        if proposed and proposed.strip().upper() not in codes[vocabulary]:
            problems.append(
                f"{field_name}: '{proposed}' is not a known {vocabulary} code"
            )

    if problems:
        raise ConfigRefused(problems)

    # ── apply ──
    before = rule_view(db, rule, detail=True)
    changed: list[str] = []

    simple = (
        "name", "conditions", "precedence", "is_active", "rationale",
        "outcome_urgency", "outcome_priority_code", "outcome_escalation_code",
        "follow_up_required",
    )
    for key in simple:
        if key not in changes or changes[key] is None:
            continue
        value = changes[key]
        if isinstance(value, str) and key.startswith("outcome_"):
            value = value.strip().upper()
        if getattr(rule, key) != value:
            setattr(rule, key, value)
            changed.append(key)

    # `is_active` may legitimately be set to False, which the None-skip above
    # would swallow for every other field but must not swallow for this one.
    if changes.get("is_active") is False and rule.is_active:
        rule.is_active = False
        changed.append("is_active")

    for key, model in (
        ("outcome_category", Category),
        ("outcome_subcategory", Subcategory),
        ("outcome_department", Department),
    ):
        proposed = changes.get(key)
        if not proposed:
            continue
        row = db.execute(
            select(model).where(model.code == proposed.strip().upper())
        ).scalars().first()
        if row is not None and getattr(rule, f"{key}_id") != row.id:
            setattr(rule, f"{key}_id", row.id)
            changed.append(key)

    if changed:
        rule.version = (rule.version or 1) + 1
        rule.updated_at = datetime.now(UTC)
        db.flush()
        # Stored results stay attributable to the rules that produced them.
        bump_ruleset_version(db)
        log.info(
            "rule_changed",
            rule=rule.rule_ref, fields=changed, by=actor.email, version=rule.version,
        )

    # Read the "after" from the flushed row rather than from the payload, so
    # the audit records what was stored and not what was asked for.
    return RuleChange(
        rule=rule,
        changed_fields=changed,
        before=before,
        after=rule_view(db, rule, detail=True),
    )


def bump_ruleset_version(db: Session) -> str:
    """
    Re-stamp the ruleset version after a live edit.

    Reuses the loader's own checksum so a version produced by an admin edit is
    indistinguishable in form from one produced by a redeploy -- two schemes
    for the same field is how a version string stops being comparable.
    """
    from src.db.seed.rules import _bump_ruleset_version, current_ruleset_version

    rows = db.execute(
        select(Rule).where(Rule.is_active.is_(True)).order_by(Rule.rule_ref)
    ).scalars().all()

    import hashlib
    import json

    digest = hashlib.sha256()
    for row in rows:
        digest.update(
            json.dumps(
                {
                    "ref": row.rule_ref,
                    "precedence": row.precedence,
                    "conditions": row.conditions,
                    "urgency": row.outcome_urgency,
                    "priority": row.outcome_priority_code,
                    "escalation": row.outcome_escalation_code,
                },
                sort_keys=True, default=str,
            ).encode()
        )

    _bump_ruleset_version(db, digest.hexdigest(), len(rows))
    return current_ruleset_version(db)


def active_rule_count(db: Session) -> int:
    return db.execute(
        select(func.count()).select_from(Rule).where(Rule.is_active.is_(True))
    ).scalar_one()


# ══════════════════════════════════════════════════════════════
# lexicon
# ══════════════════════════════════════════════════════════════
def _analytics_only(db: Session) -> set[str]:
    row = db.get(AppConfig, "analytics_only_signals")
    return set(row.value or []) if row and isinstance(row.value, list) else set()


def lexicon_view(db: Session, term: LexiconTerm, analytics: set[str]) -> dict[str, Any]:
    return {
        "id": str(term.id),
        "signal_key": term.signal_key,
        "term": term.term,
        "match_type": term.match_type,
        "weight": term.weight,
        "description": term.description,
        "is_active": bool(term.is_active),
        # SRS 1.8 #6: this signal must not influence urgency or priority,
        # whatever weight it carries. Surfaced so an evaluator editing the
        # weight can see the weight will not be used that way.
        "analytics_only": term.signal_key in analytics,
    }


def list_lexicon(db: Session, *, signal_key: str | None = None) -> list[dict[str, Any]]:
    query = select(LexiconTerm)
    if signal_key:
        query = query.where(LexiconTerm.signal_key == signal_key.strip())
    rows = db.execute(query.order_by(LexiconTerm.signal_key, LexiconTerm.term)).scalars()
    analytics = _analytics_only(db)
    return [lexicon_view(db, row, analytics) for row in rows]


# The database CHECK constraint's own vocabulary. Named here so an unknown
# value is refused with an explanation naming the alternatives, rather than
# reaching the insert and coming back as a 500 with nothing an evaluator can
# act on.
MATCH_TYPES: frozenset[str] = frozenset({"PHRASE", "REGEX", "WORD"})


def _check_term(term: str, match_type: str) -> list[str]:
    """A REGEX term that will not compile disables one signal, silently."""
    kind = match_type.strip().upper()
    if kind not in MATCH_TYPES:
        return [f"match_type must be one of {', '.join(sorted(MATCH_TYPES))}; got '{match_type}'"]

    if kind != "REGEX":
        return []
    import re

    try:
        re.compile(term)
    except re.error as exc:
        return [f"term is not a valid regular expression: {exc}"]
    return []


def create_term(db: Session, payload: dict[str, Any], *, actor: User) -> LexiconTerm:
    problems = _check_term(payload["term"], payload.get("match_type", "CONTAINS"))
    if problems:
        raise ConfigRefused(problems)

    existing = db.execute(
        select(LexiconTerm).where(
            LexiconTerm.signal_key == payload["signal_key"].strip(),
            func.lower(LexiconTerm.term) == payload["term"].strip().lower(),
        )
    ).scalars().first()
    if existing is not None:
        raise ConfigRefused(
            [f"'{payload['term']}' already raises {payload['signal_key']}."]
        )

    term = LexiconTerm(
        signal_key=payload["signal_key"].strip(),
        term=payload["term"].strip(),
        match_type=payload.get("match_type", "CONTAINS").strip().upper(),
        weight=payload.get("weight"),
        description=payload.get("description"),
        is_active=payload.get("is_active", True),
    )
    db.add(term)
    db.flush()
    log.info("lexicon_term_added", signal=term.signal_key, by=actor.email)
    return term


def update_term(
    db: Session, term_id: uuid.UUID, changes: dict[str, Any], *, actor: User
) -> tuple[LexiconTerm, dict[str, Any]]:
    term = db.get(LexiconTerm, term_id)
    if term is None:
        raise ConfigRefused([f"No lexicon term {term_id}."])

    analytics = _analytics_only(db)
    before = lexicon_view(db, term, analytics)

    proposed_term = changes.get("term") or term.term
    proposed_type = changes.get("match_type") or term.match_type
    problems = _check_term(proposed_term, proposed_type)
    if problems:
        raise ConfigRefused(problems)

    for key in ("term", "match_type", "weight", "description", "is_active"):
        if key in changes and changes[key] is not None:
            value = changes[key]
            if key == "match_type":
                value = str(value).strip().upper()
            setattr(term, key, value)
    # is_active False is a real edit, not an omission.
    if changes.get("is_active") is False:
        term.is_active = False

    db.flush()
    log.info("lexicon_term_changed", term=str(term_id), by=actor.email)
    return term, before


def delete_term(db: Session, term_id: uuid.UUID, *, actor: User) -> dict[str, Any]:
    """
    Deactivate rather than delete.

    A term that once raised a signal is part of the explanation for every
    complaint decided while it was active. Removing the row would make those
    stored decisions unexplainable.
    """
    term = db.get(LexiconTerm, term_id)
    if term is None:
        raise ConfigRefused([f"No lexicon term {term_id}."])

    before = lexicon_view(db, term, _analytics_only(db))
    term.is_active = False
    db.flush()
    log.info("lexicon_term_deactivated", term=str(term_id), by=actor.email)
    return before


# ══════════════════════════════════════════════════════════════
# SLA
# ══════════════════════════════════════════════════════════════
def sla_view(policy: SLAPolicy, categories: dict[Any, str] | None = None) -> dict[str, Any]:
    """
    One SLA target. ``categories`` maps category id to code.

    The model carries only ``category_id`` -- there is no relationship to walk,
    so the code is looked up rather than dotted through.
    """
    return {
        "id": str(policy.id),
        "category": (categories or {}).get(policy.category_id),
        "priority_code": policy.priority_code,
        "first_response_mins": policy.first_response_mins,
        "resolution_mins": policy.resolution_mins,
        "risk_threshold_pct": policy.risk_threshold_pct,
        "is_active": bool(policy.is_active),
    }


def category_codes(db: Session) -> dict[Any, str]:
    return {row.id: row.code for row in db.execute(select(Category)).scalars()}


def list_sla(db: Session) -> list[dict[str, Any]]:
    categories = category_codes(db)
    rows = db.execute(
        select(SLAPolicy).order_by(SLAPolicy.priority_code, SLAPolicy.id)
    ).scalars()
    return [sla_view(row, categories) for row in rows]


def update_sla(
    db: Session, policy_id: uuid.UUID, changes: dict[str, Any], *, actor: User
) -> tuple[SLAPolicy, dict[str, Any]]:
    policy = db.get(SLAPolicy, policy_id)
    if policy is None:
        raise ConfigRefused([f"No SLA policy {policy_id}."])

    categories = category_codes(db)
    before = sla_view(policy, categories)

    first = changes.get("first_response_mins") or policy.first_response_mins
    resolution = changes.get("resolution_mins") or policy.resolution_mins
    if resolution < first:
        raise ConfigRefused(
            [
                f"resolution_mins ({resolution}) is shorter than first_response_mins "
                f"({first}). Every complaint would breach resolution before its "
                "first reply was due."
            ]
        )

    for key in ("first_response_mins", "resolution_mins", "risk_threshold_pct", "is_active"):
        if key in changes and changes[key] is not None:
            setattr(policy, key, changes[key])
    if changes.get("is_active") is False:
        policy.is_active = False

    policy.updated_at = datetime.now(UTC)
    db.flush()
    log.info("sla_policy_changed", policy=str(policy_id), by=actor.email)
    return policy, before
