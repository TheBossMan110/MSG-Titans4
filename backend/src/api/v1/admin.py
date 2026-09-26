"""
Admin configuration and rule editing (SRS 1.8 #14).

The Live Modification Challenge: an evaluator changes the system's behaviour
on stage and the next complaint is decided differently, with no redeployment
and with the change on the record.

``POST /api/admin/rules/{rule_ref}/test`` is the endpoint that makes the
demonstration land. It runs Pipeline 2 alone over a piece of text and returns
what the rules conclude *right now* — deterministic, no provider call, nothing
written. Edit a rule, run it again, and the difference is the whole challenge
in two requests.

Reading is open to managers and evaluators; writing is admin only. Every write
is audited with the value as it was stored rather than as it was requested.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Request

from python_validation.pipeline import run_validation
from schemas.config import (
    ConfigEntryOut,
    ConfigUpdateIn,
    DefectResultOut,
    DefectSpecOut,
    LexiconTermIn,
    LexiconTermOut,
    LexiconTermUpdateIn,
    PromptActivateIn,
    PromptVersionOut,
    ReloadOut,
    RuleChangeOut,
    RuleDetailOut,
    RuleSummaryOut,
    RuleTestIn,
    RuleTestOut,
    RuleUpdateIn,
    SLAPolicyOut,
    SLAPolicyUpdateIn,
    TaxonomyOut,
)
from security import deliberate_defect
from src.core.deps import CurrentUser, DbSession, require_role
from src.core.errors import NotFoundError, ValidationError
from src.core.logging import get_logger
from src.db.enums import UserRole
from src.services import admin_config
from src.services.admin_config import ConfigRefused
from src.services.audit import record_audit

log = get_logger("api.admin")

router = APIRouter(prefix="/admin", tags=["Administration"])

# Reading the configuration is how an evaluator verifies the system is
# configuration-driven rather than hard-coded, so they can see all of it.
READERS = (UserRole.ADMIN, UserRole.MANAGER, UserRole.EVALUATOR)
WRITERS = (UserRole.ADMIN,)

ReadAccess = Depends(require_role(*READERS))
WriteAccess = Depends(require_role(*WRITERS))
# The reference every member of staff works from -- the rule matrix, the
# taxonomy and the SLA targets -- is readable by agents and reviewers too;
# only an administrator changes it (FR ii).
StaffReadAccess = Depends(require_role(*READERS, UserRole.REVIEWER, UserRole.AGENT))
# Platform configuration -- runtime settings, prompts, deliberate defects -- is
# the administrator's; evaluators read it to verify the system is config-driven.
PlatformAccess = Depends(require_role(UserRole.ADMIN, UserRole.EVALUATOR))


def _refuse(exc: ConfigRefused) -> ValidationError:
    """
    Turn a refusal into a 422 that names every problem.

    All of them, not the first: an evaluator fixing a rule one error per
    round-trip is the demonstration going badly in public.
    """
    return ValidationError("; ".join(exc.problems))


# ══════════════════════════════════════════════════════════════
# configuration values
# ══════════════════════════════════════════════════════════════
@router.get(
    "/config",
    response_model=list[ConfigEntryOut],
    dependencies=[PlatformAccess],
    summary="Every runtime configuration value",
)
def list_config(db: DbSession) -> list[ConfigEntryOut]:
    """
    Thresholds, comparison weights, policy precedence, guard behaviour.

    ``editable: false`` marks the rows that are derived rather than
    configured — the ruleset version is stamped onto stored results, so
    hand-editing it would detach them from what produced them.
    """
    return [ConfigEntryOut(**entry) for entry in admin_config.config_entries(db)]


@router.put(
    "/config/{key}",
    response_model=ConfigEntryOut,
    dependencies=[WriteAccess],
    summary="Replace one configuration value",
)
def update_config(
    key: str,
    payload: ConfigUpdateIn,
    db: DbSession,
    user: CurrentUser,
    request: Request,
) -> ConfigEntryOut:
    """
    Change a threshold or a weight, live.

    The new value must keep the existing shape. A list where an object was
    expected does not fail here — it fails deep inside the rule engine on the
    next complaint, which is a far worse place to discover it.
    """
    try:
        entry, previous = admin_config.set_config(db, key, payload.value, actor=user)
    except ConfigRefused as exc:
        raise _refuse(exc) from exc

    record_audit(
        db,
        entity_type="app_config",
        entity_id=key,
        action="CONFIG_CHANGE",
        actor=user,
        before={"value": previous},
        after={"value": entry["value"]},
        reason=payload.reason,
        request=request,
    )
    db.commit()
    return ConfigEntryOut(**entry)


@router.get(
    "/taxonomy",
    response_model=TaxonomyOut,
    dependencies=[StaffReadAccess],
    summary="Every vocabulary the rules are written against",
)
def get_taxonomy(db: DbSession) -> TaxonomyOut:
    """
    Read-only on purpose.

    A category code appears in rule outcomes, in SLA policies, in stored
    complaints and in the ground-truth labels. Renaming one from a form would
    silently orphan all four.
    """
    return TaxonomyOut(**admin_config.taxonomy(db))


# ══════════════════════════════════════════════════════════════
# rules
# ══════════════════════════════════════════════════════════════
@router.get(
    "/rules",
    response_model=list[RuleSummaryOut],
    dependencies=[StaffReadAccess],
    summary="The rule matrix",
)
def list_rules(
    db: DbSession,
    rule_type: str | None = None,
    active: bool | None = None,
    mandatory: bool | None = Query(None, description="Mandatory escalation rules only."),
    search: str | None = Query(None, max_length=200),
) -> list[RuleSummaryOut]:
    rows = admin_config.list_rules(
        db, rule_type=rule_type, active=active, mandatory=mandatory, search=search
    )
    return [RuleSummaryOut(**admin_config.rule_view(db, row)) for row in rows]


@router.get(
    "/rules/{rule_ref}",
    response_model=RuleDetailOut,
    dependencies=[StaffReadAccess],
    summary="One rule, with its conditions",
)
def get_rule(rule_ref: str, db: DbSession) -> RuleDetailOut:
    try:
        rule = admin_config.load_rule(db, rule_ref)
    except ConfigRefused as exc:
        raise NotFoundError(exc.problems[0]) from exc
    return RuleDetailOut(**admin_config.rule_view(db, rule, detail=True))


@router.patch(
    "/rules/{rule_ref}",
    response_model=RuleChangeOut,
    dependencies=[WriteAccess],
    summary="Edit one rule",
)
def update_rule(
    rule_ref: str,
    payload: RuleUpdateIn,
    db: DbSession,
    user: CurrentUser,
    request: Request,
) -> RuleChangeOut:
    """
    Change a rule and have it take effect on the next complaint.

    Refused with 422 and every specific problem when a condition is malformed,
    when it references a signal no active lexicon term raises, or when an
    outcome names a code that does not exist. Saving such a rule would let it
    sit in the matrix looking like coverage while never firing.

    A rule that sets a mandatory escalation may have its level **raised** but
    not lowered, and cannot be deactivated at all.
    """
    changes = payload.model_dump(exclude_unset=True)
    changes.pop("reason", None)

    try:
        change = admin_config.update_rule(db, rule_ref, changes, actor=user)
    except ConfigRefused as exc:
        if exc.problems and exc.problems[0].startswith("No rule"):
            raise NotFoundError(exc.problems[0]) from exc
        raise _refuse(exc) from exc

    if change.changed_fields:
        record_audit(
            db,
            entity_type="rule",
            entity_id=change.rule.rule_ref,
            action="RULE_CHANGE",
            actor=user,
            before={k: change.before.get(k) for k in change.changed_fields},
            after={k: change.after.get(k) for k in change.changed_fields},
            reason=payload.reason,
            request=request,
        )
    db.commit()

    from src.db.seed.rules import current_ruleset_version

    return RuleChangeOut(
        rule=RuleDetailOut(**change.after),
        changed_fields=change.changed_fields,
        ruleset_version=current_ruleset_version(db),
        active_rule_count=admin_config.active_rule_count(db),
    )


@router.post(
    "/rules/test",
    response_model=RuleTestOut,
    dependencies=[ReadAccess],
    summary="Run the rule engine over a piece of text without storing anything",
)
def test_rules(payload: RuleTestIn, db: DbSession) -> RuleTestOut:
    """
    What Pipeline 2 alone concludes about this text, right now.

    The endpoint that makes the Live Modification Challenge legible: edit a
    rule, post the same text again, and the difference is visible in one
    response. Deterministic and free — no provider is called and no complaint
    row is created, so it can be run as often as an evaluator likes without
    spending the free-tier quota or filling the register with test rows.
    """
    result = run_validation(db, text=payload.description)
    outcome = result.outcome

    return RuleTestOut(
        category=outcome.category_code,
        subcategory=outcome.subcategory_code,
        department=outcome.department_code,
        support_department=outcome.support_department_code,
        urgency=outcome.urgency,
        priority=outcome.priority_code,
        escalation_code=outcome.escalation_code,
        escalation_floor_code=outcome.escalation_floor_code,
        escalation_required=bool(
            outcome.escalation_code and outcome.escalation_code.upper() != "NONE"
        ),
        follow_up_required=bool(outcome.follow_up_required),
        matched_rules=[hit.rule_ref for hit in outcome.applied_hits],
        mandatory_escalation_refs=list(outcome.mandatory_escalation_refs),
        signals_fired=sorted(result.signals.hits),
        required_actions=list(outcome.required_actions),
        prohibited_actions=list(outcome.prohibited_actions),
        unmatched=outcome.unmatched,
        conflict_detected=outcome.conflict_detected,
        ruleset_version=result.ruleset_version,
        latency_ms=result.latency_ms,
    )


@router.post(
    "/rules/reload",
    response_model=ReloadOut,
    dependencies=[WriteAccess],
    summary="Restore the rule matrix from its committed source",
)
def reload_rules(db: DbSession, user: CurrentUser, request: Request) -> ReloadOut:
    """
    The undo for a live demonstration.

    Whatever was changed on stage goes back to the committed YAML in one call,
    so the next demonstration starts from a known state rather than from
    whatever the last one left behind.
    """
    from src.db.seed.rules import current_ruleset_version, seed_rules

    report = seed_rules(db)
    record_audit(
        db,
        entity_type="rule",
        entity_id="*",
        action="RULES_RELOADED",
        actor=user,
        after=report,
        reason="Restored from the committed rule source.",
        request=request,
    )
    db.commit()

    return ReloadOut(
        reloaded=report,
        ruleset_version=current_ruleset_version(db),
        active_rule_count=admin_config.active_rule_count(db),
    )


# ══════════════════════════════════════════════════════════════
# lexicon
# ══════════════════════════════════════════════════════════════
@router.get(
    "/lexicon",
    response_model=list[LexiconTermOut],
    dependencies=[ReadAccess],
    summary="Terms that raise signals",
)
def list_lexicon(
    db: DbSession, signal_key: str | None = None
) -> list[LexiconTermOut]:
    return [
        LexiconTermOut(**row) for row in admin_config.list_lexicon(db, signal_key=signal_key)
    ]


@router.post(
    "/lexicon",
    response_model=LexiconTermOut,
    status_code=201,
    dependencies=[WriteAccess],
    summary="Add a term",
)
def add_term(
    payload: LexiconTermIn, db: DbSession, user: CurrentUser, request: Request
) -> LexiconTermOut:
    """
    Teach the rule engine a new word, live.

    A REGEX term that will not compile is refused here rather than accepted:
    an uncompilable term disables one signal silently, and a signal that stops
    firing looks exactly like a complaint that did not mention the thing.
    """
    try:
        term = admin_config.create_term(db, payload.model_dump(), actor=user)
    except ConfigRefused as exc:
        raise _refuse(exc) from exc

    record_audit(
        db,
        entity_type="lexicon_term",
        entity_id=term.id,
        action="LEXICON_ADD",
        actor=user,
        after={"signal_key": term.signal_key, "term": term.term},
        request=request,
    )
    db.commit()
    view = admin_config.list_lexicon(db, signal_key=term.signal_key)
    return LexiconTermOut(**next(row for row in view if row["id"] == str(term.id)))


@router.patch(
    "/lexicon/{term_id}",
    response_model=LexiconTermOut,
    dependencies=[WriteAccess],
    summary="Edit a term",
)
def edit_term(
    term_id: uuid.UUID,
    payload: LexiconTermUpdateIn,
    db: DbSession,
    user: CurrentUser,
    request: Request,
) -> LexiconTermOut:
    try:
        term, before = admin_config.update_term(
            db, term_id, payload.model_dump(exclude_unset=True), actor=user
        )
    except ConfigRefused as exc:
        if exc.problems[0].startswith("No lexicon"):
            raise NotFoundError(exc.problems[0]) from exc
        raise _refuse(exc) from exc

    view = admin_config.list_lexicon(db, signal_key=term.signal_key)
    after = next(row for row in view if row["id"] == str(term.id))

    record_audit(
        db,
        entity_type="lexicon_term",
        entity_id=term_id,
        action="LEXICON_CHANGE",
        actor=user,
        before=before,
        after=after,
        request=request,
    )
    db.commit()
    return LexiconTermOut(**after)


@router.delete(
    "/lexicon/{term_id}",
    response_model=LexiconTermOut,
    dependencies=[WriteAccess],
    summary="Withdraw a term",
)
def remove_term(
    term_id: uuid.UUID, db: DbSession, user: CurrentUser, request: Request
) -> LexiconTermOut:
    """
    Deactivated, not deleted.

    A term that once raised a signal is part of the explanation for every
    complaint decided while it was active. Removing the row would make those
    stored decisions unexplainable.
    """
    try:
        before = admin_config.delete_term(db, term_id, actor=user)
    except ConfigRefused as exc:
        raise NotFoundError(exc.problems[0]) from exc

    record_audit(
        db,
        entity_type="lexicon_term",
        entity_id=term_id,
        action="LEXICON_WITHDRAW",
        actor=user,
        before=before,
        after={**before, "is_active": False},
        request=request,
    )
    db.commit()
    return LexiconTermOut(**{**before, "is_active": False})


# ══════════════════════════════════════════════════════════════
# SLA
# ══════════════════════════════════════════════════════════════
@router.get(
    "/sla",
    response_model=list[SLAPolicyOut],
    dependencies=[StaffReadAccess],
    summary="SLA targets",
)
def list_sla(db: DbSession) -> list[SLAPolicyOut]:
    return [SLAPolicyOut(**row) for row in admin_config.list_sla(db)]


@router.patch(
    "/sla/{policy_id}",
    response_model=SLAPolicyOut,
    dependencies=[WriteAccess],
    summary="Retune an SLA target",
)
def update_sla(
    policy_id: uuid.UUID,
    payload: SLAPolicyUpdateIn,
    db: DbSession,
    user: CurrentUser,
    request: Request,
) -> SLAPolicyOut:
    """
    Move a deadline, live.

    Follow-up due dates are a fraction of the first-response window rather
    than a separate constant, so retuning a target moves the follow-up
    schedule with it instead of leaving two numbers to drift apart.
    """
    changes = payload.model_dump(exclude_unset=True)
    changes.pop("reason", None)

    try:
        policy, before = admin_config.update_sla(db, policy_id, changes, actor=user)
    except ConfigRefused as exc:
        if exc.problems[0].startswith("No SLA"):
            raise NotFoundError(exc.problems[0]) from exc
        raise _refuse(exc) from exc

    after = admin_config.sla_view(policy, admin_config.category_codes(db))
    record_audit(
        db,
        entity_type="sla_policy",
        entity_id=policy_id,
        action="SLA_CHANGE",
        actor=user,
        before=before,
        after=after,
        reason=payload.reason,
        request=request,
    )
    db.commit()
    return SLAPolicyOut(**after)


# ══════════════════════════════════════════════════════════════
# prompts
# ══════════════════════════════════════════════════════════════
@router.get(
    "/prompts",
    response_model=list[PromptVersionOut],
    dependencies=[PlatformAccess],
    summary="Registered prompt templates",
)
def list_prompts(db: DbSession) -> list[PromptVersionOut]:
    """
    Every template version with a live on-disk integrity check.

    ``checksum_matches: false`` means the file changed without a version bump,
    which is the one thing a version registry exists to detect.
    """
    from genai_pipeline import prompts

    return [
        PromptVersionOut(
            name=row["name"],
            version=row["version"],
            is_active=row["is_active"],
            checksum=row["checksum"],
            variables=[] if row["checksum_matches"] else ["CHECKSUM_MISMATCH"],
        )
        for row in prompts.registry_status(db)
    ]


@router.patch(
    "/prompts/{name}",
    response_model=PromptVersionOut,
    dependencies=[WriteAccess],
    summary="Switch which version of a prompt is used",
)
def activate_prompt(
    name: str,
    payload: PromptActivateIn,
    db: DbSession,
    user: CurrentUser,
    request: Request,
) -> PromptVersionOut:
    """
    Promote a prompt version without a deploy.

    Deliberately explicit: dropping a new template into the repository must
    not silently redirect traffic away from a version an administrator pinned.
    """
    from genai_pipeline import prompts

    before = prompts.active_version(db, name)
    try:
        row = prompts.activate(db, name, payload.version.strip())
    except Exception as exc:  # noqa: BLE001 - surfaced as a 422 with the reason
        raise ValidationError(str(exc)) from exc

    record_audit(
        db,
        entity_type="prompt_version",
        entity_id=name,
        action="PROMPT_ACTIVATED",
        actor=user,
        before={"version": before},
        after={"version": row.version},
        reason=payload.reason,
        request=request,
    )
    db.commit()

    return PromptVersionOut(
        name=row.name, version=row.version, is_active=row.is_active,
        checksum=row.checksum, variables=[],
    )


# ══════════════════════════════════════════════════════════════
# the deliberate defect
# ══════════════════════════════════════════════════════════════
@router.get(
    "/defects",
    response_model=list[DefectSpecOut],
    dependencies=[PlatformAccess],
    summary="The deliberate defects and what should catch each one",
)
def list_defects() -> list[DefectSpecOut]:
    """
    Documented before they are demonstrated (SRS 1.8 #15).

    Each entry states what it breaks, which detector should catch it, and why
    that detector exists — so a judge reading a result can tell a genuine
    safeguard from a coincidence.
    """
    return [DefectSpecOut(**spec) for spec in deliberate_defect.catalogue()]


@router.post(
    "/defects/demonstrate",
    response_model=list[DefectResultOut],
    dependencies=[PlatformAccess],
    summary="Run every deliberate defect through its real detector",
)
def demonstrate_defects(db: DbSession) -> list[DefectResultOut]:
    """
    Produce each documented defect and report what the production detector
    said about it.

    A safety check nobody has ever seen fire is a safety check nobody has
    reason to believe in. Nothing is persisted and nothing outside this request
    is affected: each faulty artefact exists for the duration of the call and
    is then discarded.
    """
    return [
        DefectResultOut(**result.as_dict())
        for result in deliberate_defect.demonstrate_all(db)
    ]


@router.post(
    "/defects/{code}/demonstrate",
    response_model=DefectResultOut,
    dependencies=[PlatformAccess],
    summary="Run one deliberate defect through its real detector",
)
def demonstrate_defect(code: str, db: DbSession) -> DefectResultOut:
    try:
        result = deliberate_defect.demonstrate(db, code)
    except KeyError as exc:
        raise NotFoundError(f"No deliberate defect '{code}'.") from exc
    return DefectResultOut(**result.as_dict())
