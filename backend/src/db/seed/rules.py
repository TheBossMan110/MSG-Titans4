"""
Load the Complaint Resolution Rule Matrix from YAML into the database.

SRS Step 8: "Teams must create a structured rule matrix representing approved
complaint-handling logic.  The matrix must not simply be generated at runtime
by the same GenAI model responsible for complaint resolution."

So the rules are hand-authored YAML under ``complaint_rules/``,
``routing_rules/`` and ``escalation_rules/`` — all three are required
deliverables — and this loader is the only path from those files into the
``rules`` table.

Everything is validated at load time rather than at evaluation time:

* the condition tree is structurally checked,
* every signal a rule references must exist in the lexicon,
* every category, subcategory, department, priority and escalation code must
  resolve to a real row,
* rule references must be unique across all files.

A rule that fails validation is **not loaded**, and the failure is reported.
The alternative — loading it anyway — produces a rule that silently never
fires, which is far worse: the matrix would claim coverage it does not have.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from python_validation.conditions import referenced_signals, validate_condition
from src.core.config import settings
from src.core.logging import get_logger
from src.db.enums import RuleType, Urgency
from src.db.models import (
    AppConfig,
    Category,
    Department,
    EscalationLevel,
    LexiconTerm,
    PriorityLevel,
    Rule,
    Subcategory,
)

log = get_logger("seed.rules")

RULE_DIRECTORIES = ("complaint_rules", "routing_rules", "escalation_rules")


@dataclass
class LoadReport:
    """What happened, in enough detail to fix an authoring mistake."""

    loaded: int = 0
    updated: int = 0
    skipped: int = 0
    files: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    mandatory_escalation: int = 0
    by_type: dict[str, int] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.errors

    def as_dict(self) -> dict[str, Any]:
        return {
            "loaded": self.loaded,
            "updated": self.updated,
            "skipped": self.skipped,
            "mandatory_escalation": self.mandatory_escalation,
            "by_type": dict(self.by_type),
            "files": self.files,
            "errors": self.errors,
        }


class _Lookups:
    """Code -> row resolution, loaded once per run."""

    def __init__(self, db: Session) -> None:
        self.categories = {c.code: c for c in db.execute(select(Category)).scalars()}
        self.departments = {d.code: d for d in db.execute(select(Department)).scalars()}
        self.priorities = {p.code for p in db.execute(select(PriorityLevel)).scalars()}
        self.escalations = {e.code for e in db.execute(select(EscalationLevel)).scalars()}
        self.signals = {
            row.signal_key
            for row in db.execute(select(LexiconTerm)).scalars()
        }
        self.subcategories: dict[tuple[str, str], Subcategory] = {}
        for sub in db.execute(select(Subcategory)).scalars():
            category = next(
                (c for c in self.categories.values() if c.id == sub.category_id), None
            )
            if category:
                self.subcategories[(category.code, sub.code)] = sub

    def subcategory(self, category_code: str | None, code: str | None) -> Subcategory | None:
        if not code:
            return None
        if category_code and (category_code, code) in self.subcategories:
            return self.subcategories[(category_code, code)]
        # Fall back to a unique match on the code alone.
        matches = [sub for (_, sub_code), sub in self.subcategories.items() if sub_code == code]
        return matches[0] if len(matches) == 1 else None


# ══════════════════════════════════════════════════════════════
# validation
# ══════════════════════════════════════════════════════════════
def _validate_rule(
    spec: dict[str, Any], lookups: _Lookups, source: str
) -> tuple[list[str], set[str]]:
    """Return ``(errors, referenced_signal_names)`` for one rule spec."""
    errors: list[str] = []
    ref = spec.get("rule_ref", "<missing rule_ref>")

    if not spec.get("rule_ref"):
        errors.append(f"{source}: a rule has no rule_ref")
    if not spec.get("name"):
        errors.append(f"{ref}: missing name")

    rule_type = str(spec.get("rule_type", "")).upper()
    if rule_type not in {member.value for member in RuleType}:
        errors.append(f"{ref}: rule_type '{rule_type}' is not a recognised RuleType")

    conditions = spec.get("when")
    if conditions is None:
        errors.append(f"{ref}: missing 'when' condition")
        signals: set[str] = set()
    else:
        errors.extend(f"{ref}: {problem}" for problem in validate_condition(conditions))
        signals = referenced_signals(conditions)

    unknown_signals = signals - lookups.signals
    errors.extend(
        f"{ref}: references unknown signal '{name}' (no lexicon term defines it)"
        for name in sorted(unknown_signals)
    )

    then = spec.get("then") or {}
    if not isinstance(then, dict):
        errors.append(f"{ref}: 'then' must be a mapping")
        then = {}

    category_code = then.get("category")
    if category_code and category_code not in lookups.categories:
        errors.append(f"{ref}: unknown category '{category_code}'")

    subcategory_code = then.get("subcategory")
    if subcategory_code and lookups.subcategory(category_code, subcategory_code) is None:
        errors.append(f"{ref}: unknown subcategory '{subcategory_code}'")

    for key in ("department", "support_department"):
        code = then.get(key)
        if code and code not in lookups.departments:
            errors.append(f"{ref}: unknown department '{code}' for {key}")

    urgency = then.get("urgency")
    if urgency and urgency not in {member.value for member in Urgency}:
        errors.append(f"{ref}: unknown urgency '{urgency}'")

    priority = then.get("priority")
    if priority and priority not in lookups.priorities:
        errors.append(f"{ref}: unknown priority '{priority}'")

    escalation = then.get("escalation")
    if escalation and escalation not in lookups.escalations:
        errors.append(f"{ref}: unknown escalation level '{escalation}'")

    if spec.get("mandatory_escalation") and not escalation:
        errors.append(
            f"{ref}: mandatory_escalation is set but no escalation level is given - "
            "a floor with no height cannot be enforced"
        )

    for policy_ref in then.get("policy_refs") or []:
        if not isinstance(policy_ref, dict) or not policy_ref.get("doc_ref"):
            errors.append(f"{ref}: policy_refs entries need a doc_ref")

    scope = spec.get("scope") or {}
    if scope and not isinstance(scope, dict):
        errors.append(f"{ref}: 'scope' must be a mapping")
    elif scope.get("category") and scope["category"] not in lookups.categories:
        errors.append(f"{ref}: scope references unknown category '{scope['category']}'")

    return errors, signals


# ══════════════════════════════════════════════════════════════
# loading
# ══════════════════════════════════════════════════════════════
def _rule_files() -> list[Path]:
    root = settings.config_dir.parent
    found: list[Path] = []
    for directory in RULE_DIRECTORIES:
        path = root / directory
        if path.exists():
            found.extend(sorted(path.glob("*.yaml")))
    return found


def _apply_spec(
    rule: Rule, spec: dict[str, Any], lookups: _Lookups, source: str, default_precedence: int
) -> None:
    then = spec.get("then") or {}
    scope = spec.get("scope") or {}
    eligibility = spec.get("eligibility") or {}

    category = lookups.categories.get(then.get("category", ""))
    subcategory = lookups.subcategory(then.get("category"), then.get("subcategory"))
    scope_category = lookups.categories.get(scope.get("category", ""))
    scope_subcategory = lookups.subcategory(scope.get("category"), scope.get("subcategory"))

    rule.name = spec["name"]
    rule.rule_type = str(spec.get("rule_type", RuleType.CLASSIFICATION)).upper()
    rule.conditions = spec.get("when") or {}
    rule.precedence = int(spec.get("precedence", default_precedence))
    rule.is_mandatory_escalation = bool(spec.get("mandatory_escalation", False))
    rule.rationale = " ".join(str(spec.get("rationale", "")).split())
    rule.source_ref = source
    rule.is_active = bool(spec.get("active", True))

    rule.category_id = scope_category.id if scope_category else None
    rule.subcategory_id = scope_subcategory.id if scope_subcategory else None

    rule.outcome_category_id = category.id if category else None
    rule.outcome_subcategory_id = subcategory.id if subcategory else None
    rule.outcome_department_id = (
        lookups.departments[then["department"]].id if then.get("department") else None
    )
    rule.outcome_support_department_id = (
        lookups.departments[then["support_department"]].id
        if then.get("support_department")
        else None
    )
    rule.outcome_urgency = then.get("urgency")
    rule.outcome_priority_code = then.get("priority")
    rule.outcome_escalation_code = then.get("escalation")

    rule.required_actions = list(then.get("required_actions") or [])
    rule.prohibited_actions = list(then.get("prohibited_actions") or [])
    rule.policy_refs = list(then.get("policy_refs") or [])
    rule.follow_up_required = bool(then.get("follow_up_required", then.get("follow_up", False)))

    rule.is_catch_all = bool(spec.get("catch_all", False))
    rule.eligibility = dict(eligibility) if eligibility else None


def load_rules(db: Session, *, deactivate_missing: bool = True) -> LoadReport:
    """
    Load every rule file into the ``rules`` table.

    Idempotent.  A rule present in the database but absent from the files is
    deactivated rather than deleted, so an edit made live through the admin API
    is never silently destroyed by a reseed.
    """
    report = LoadReport()
    lookups = _Lookups(db)
    seen_refs: set[str] = set()
    checksum = hashlib.sha256()

    for path in _rule_files():
        relative = path.relative_to(settings.config_dir.parent).as_posix()
        report.files.append(relative)

        try:
            raw = path.read_text(encoding="utf-8")
            document = yaml.safe_load(raw) or {}
        except yaml.YAMLError as exc:
            report.errors.append(f"{relative}: invalid YAML - {exc}")
            continue

        checksum.update(raw.encode("utf-8"))
        default_precedence = int(document.get("default_precedence", 50))

        for spec in document.get("rules", []):
            if not isinstance(spec, dict):
                report.errors.append(f"{relative}: a rule entry is not a mapping")
                report.skipped += 1
                continue

            ref = spec.get("rule_ref", "")
            errors, _ = _validate_rule(spec, lookups, relative)

            if ref in seen_refs:
                errors.append(f"{ref}: duplicate rule_ref (already defined in another file)")

            if errors:
                report.errors.extend(errors)
                report.skipped += 1
                log.warning("rule_rejected", rule_ref=ref, errors=errors)
                continue

            seen_refs.add(ref)

            existing = db.execute(
                select(Rule).where(Rule.rule_ref == ref)
            ).scalars().first()

            if existing is None:
                rule = Rule(rule_ref=ref)
                _apply_spec(rule, spec, lookups, relative, default_precedence)
                db.add(rule)
                report.loaded += 1
            else:
                _apply_spec(existing, spec, lookups, relative, default_precedence)
                existing.version = (existing.version or 1) + 1
                rule = existing
                report.updated += 1

            if rule.is_mandatory_escalation:
                report.mandatory_escalation += 1
            report.by_type[rule.rule_type] = report.by_type.get(rule.rule_type, 0) + 1

    db.flush()

    if deactivate_missing and seen_refs:
        stale = db.execute(
            select(Rule).where(Rule.rule_ref.notin_(seen_refs), Rule.is_active.is_(True))
        ).scalars().all()
        for rule in stale:
            rule.is_active = False
            log.info("rule_deactivated", rule_ref=rule.rule_ref, reason="absent from files")

    _bump_ruleset_version(db, checksum.hexdigest(), len(seen_refs))

    log.info("rules_loaded", **report.as_dict())
    return report


def _bump_ruleset_version(db: Session, checksum: str, rule_count: int) -> None:
    """
    Stamp a new ruleset version.

    Every ``validation_run`` records this, so a past ground-truth result can
    always be tied to the exact rules that produced it — which is what makes
    the comparison report reproducible after the matrix has moved on.
    """
    version = f"{datetime.now(UTC):%Y.%m.%d}-{checksum[:8]}"
    config = db.get(AppConfig, "ruleset_version")
    value = {
        "version": version,
        "rule_count": rule_count,
        "checksum": checksum,
        "loaded_at": datetime.now(UTC).isoformat(),
    }
    if config is None:
        db.add(
            AppConfig(
                key="ruleset_version",
                value=value,
                description="Bumped whenever any rule changes.",
            )
        )
    else:
        config.value = value
        config.version = (config.version or 1) + 1
        config.updated_at = datetime.now(UTC)
    db.flush()


def current_ruleset_version(db: Session) -> str:
    config = db.get(AppConfig, "ruleset_version")
    if config and isinstance(config.value, dict):
        return str(config.value.get("version", "unversioned"))
    return "unversioned"


def seed_rules(db: Session) -> dict[str, int]:
    """Seeder entry point, wired into ``python -m src.db.seed.run``."""
    report = load_rules(db)
    if report.errors:
        # Loud, but not fatal: the valid rules still load, and the operator
        # gets a precise list of what did not.
        log.error("rule_load_errors", count=len(report.errors), errors=report.errors[:20])
    return {
        "loaded": report.loaded,
        "updated": report.updated,
        "skipped": report.skipped,
        "mandatory_escalation": report.mandatory_escalation,
        "errors": len(report.errors),
    }
