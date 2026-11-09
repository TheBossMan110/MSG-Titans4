"""
What each role may do inside its own organisation -- set by that
organisation's administrator on the Access Control page.

Two kinds of access, matching how a company actually delegates:

* **Work** -- named permissions such as ``documents.manage`` or
  ``reports.export``. A route guarded by :func:`require_permission` asks "has
  this organisation given this role this permission?" instead of "is this one
  of these roles?".
* **Data** -- how much of the complaint register a role sees:
  ``assigned`` (only what is assigned to them), ``team`` (their department's,
  plus what is assigned to them) or ``all``. src/core/scope.py applies it.

The defaults are exactly the role gates the platform had before organisations
existed, so an organisation that never opens the page behaves as it always
did. Two roles are not configurable: an administrator has every permission
(the platform must never be left without someone who can change access), and
the evaluator -- a judge's read-only account -- keeps its fixed read access.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from fastapi import Request

from src.core import tenancy
from src.core.deps import CurrentUser, OptionalUser
from src.core.errors import PermissionError_
from src.db.enums import UserRole

CONFIGURABLE_ROLES = ("manager", "reviewer", "agent")
SCOPES = ("assigned", "team", "all")


@dataclass(frozen=True, slots=True)
class Permission:
    key: str
    label: str
    description: str
    defaults: frozenset[str]
    evaluator: bool = False


CATALOGUE: tuple[Permission, ...] = (
    Permission("analytics.view", "View analytics and reports",
               "Analytics, trends and the ready-made reports on screen.",
               frozenset({"manager"}), evaluator=True),
    Permission("reports.export", "Download reports",
               "Export any report as CSV, Excel, PDF or JSON.",
               frozenset({"manager"})),
    Permission("review.queue", "See the review queue",
               "Open the queue of complaints a person must check, and its statistics.",
               frozenset({"reviewer", "manager"}), evaluator=True),
    Permission("review.decide", "Decide reviews",
               "Claim queued complaints; approve, reject, modify, reclassify, escalate or override.",
               frozenset({"reviewer", "manager"})),
    Permission("complaints.reanalyse", "Re-run the pipelines",
               "Send a complaint through both pipelines again.",
               frozenset({"manager"})),
    Permission("documents.manage", "Manage policy documents",
               "Upload, activate and withdraw the policies the AI may cite.",
               frozenset()),
    Permission("users.manage", "Add agents",
               "Create agent accounts in their own team.",
               frozenset({"manager"})),
    Permission("audit.view", "Read the audit log",
               "Every change in the organisation: who, what and when.",
               frozenset(), evaluator=True),
    Permission("benchmark.run", "Import and score datasets",
               "Import a labelled complaint file and measure accuracy against it.",
               frozenset(), evaluator=True),
)
BY_KEY = {p.key: p for p in CATALOGUE}
DEFAULT_SCOPE = {"manager": "all", "reviewer": "all", "agent": "team"}


def defaults() -> dict[str, Any]:
    """The policy an organisation has until its administrator changes it."""
    return {
        "permissions": {role: sorted(p.key for p in CATALOGUE if role in p.defaults) for role in CONFIGURABLE_ROLES},
        "complaint_scope": dict(DEFAULT_SCOPE),
    }


def policy_of(organisation_id: Any) -> dict[str, Any]:
    """The organisation's effective policy: what it saved, over the defaults, role by role."""
    return policy_from(tenancy.settings_of(organisation_id))


def policy_from(saved: dict[str, Any] | None) -> dict[str, Any]:
    """:func:`policy_of` for a settings value in hand (one not yet committed, say)."""
    saved = saved or {}
    effective = defaults()
    for role, keys in (saved.get("permissions") or {}).items():
        if role in CONFIGURABLE_ROLES and isinstance(keys, list):
            effective["permissions"][role] = sorted(k for k in keys if k in BY_KEY)
    for role, scope in (saved.get("complaint_scope") or {}).items():
        if role in CONFIGURABLE_ROLES and scope in SCOPES:
            effective["complaint_scope"][role] = scope
    return effective


def granted(user: Any) -> set[str]:
    role = str(getattr(user, "role", ""))
    if role == UserRole.SUPERADMIN:
        # The platform's own audit log (company suspensions, template edits);
        # the filter keeps every company's log out of reach.
        return {"audit.view"}
    if role == UserRole.ADMIN:
        return set(BY_KEY)
    if role == UserRole.EVALUATOR:
        return {p.key for p in CATALOGUE if p.evaluator}
    if role not in CONFIGURABLE_ROLES:
        return set()
    return set(policy_of(user.organisation_id)["permissions"][role])


def allows(user: Any, key: str) -> bool:
    return key in granted(user)


def complaint_scope(user: Any) -> str:
    """``assigned`` | ``team`` | ``all`` for staff; ``own`` for a customer; ``none`` for the platform."""
    role = str(getattr(user, "role", ""))
    if role == UserRole.SUPERADMIN:
        return "none"
    if role in (UserRole.ADMIN, UserRole.EVALUATOR):
        return "all"
    if role not in CONFIGURABLE_ROLES:
        return "own"
    return policy_of(user.organisation_id)["complaint_scope"][role]


def roles_with(organisation_id: Any, key: str) -> list[str]:
    """Who holds ``key`` in this organisation, for the refusal message."""
    policy = policy_of(organisation_id)
    holders = [UserRole.ADMIN.value] + [r for r in CONFIGURABLE_ROLES if key in policy["permissions"][r]]
    if BY_KEY[key].evaluator:
        holders.append(UserRole.EVALUATOR.value)
    return holders


def require_permission(key: str) -> Callable[..., Any]:
    """
    Route guard, used like ``require_role``::

        @router.post("", dependencies=[Depends(require_permission("documents.manage"))])

    A refusal is audited as ACCESS_DENIED, exactly as a role refusal is.
    """
    permission = BY_KEY[key]

    def _guard(request: Request, user: CurrentUser):
        if allows(user, key):
            return user
        from src.services.audit import record_security_event

        record_security_event(
            actor=user, entity_type="endpoint", entity_id=request.url.path, action="ACCESS_DENIED",
            reason=f"permission={key} role={user.role}", request=request,
            details={"method": request.method, "permission": key},
        )
        raise PermissionError_(
            f"Your organisation has not given the {user.role} role this permission: {permission.label.lower()}.",
            details={
                "required_permission": key,
                "required_roles": roles_with(user.organisation_id, key),
                "your_role": user.role,
            },
        )

    return _guard


def require_platform_admin(request: Request, user: CurrentUser):
    """
    Shared configuration -- taxonomy, the rule matrix, lexicon, prompts, SLA
    ladders -- is one template every organisation runs on. The super
    administrators maintain it, with the administrators of the reference
    company whose dataset defined it; another company's administrator changing
    a rule would change it for everybody.
    """
    if user.role == UserRole.SUPERADMIN or (
        user.role == UserRole.ADMIN and tenancy.owns_template(user.organisation_id)
    ):
        return user
    from src.services.audit import record_security_event

    record_security_event(
        actor=user, entity_type="endpoint", entity_id=request.url.path, action="ACCESS_DENIED",
        reason=f"shared_configuration role={user.role}", request=request, details={"method": request.method},
    )
    raise PermissionError_(
        "Shared configuration (taxonomy, rules, lexicon, prompts, SLA ladders) is maintained by the platform. "
        "Your organisation's people, policies, complaints and access are yours to change.",
        details={"required_roles": ["admin"], "your_role": user.role, "platform_only": True},
    )


def require_company_member(request: Request, user: OptionalUser):
    """
    Router-level guard on every router that serves a company's own data
    (complaints, review, analytics, documents, email, people, organisation,
    benchmark, assistant): a super administrator is refused there wholesale.

    The organisation filter would already leave them nothing to read, but
    "the platform sees no company's data" is a rule, not an accident of an
    empty organisation -- and refusing at the router covers an endpoint that
    forgets its own role gate. Visitors (no token) pass through to the
    endpoint's own rules.
    """
    if user is None or user.role != UserRole.SUPERADMIN:
        return user
    from src.services.audit import record_security_event

    record_security_event(
        actor=user, entity_type="endpoint", entity_id=request.url.path, action="ACCESS_DENIED",
        reason="superadmin_company_data", request=request, details={"method": request.method},
    )
    raise PermissionError_(
        "A super administrator sees the platform, not a company's complaints, people or emails.",
        details={"your_role": user.role, "platform_only": False},
    )


def require_platform_staff(*roles: str) -> Callable[..., Any]:
    """
    Route guard for the platform's own view of every company: only people in
    the platform organisation with one of ``roles`` (the super administrators).
    A company's administrator runs their company; they never see the others.
    """
    allowed = {str(r) for r in roles}

    def _guard(request: Request, user: CurrentUser):
        if user.role in allowed and tenancy.is_platform(user.organisation_id):
            return user
        from src.services.audit import record_security_event

        record_security_event(
            actor=user, entity_type="endpoint", entity_id=request.url.path, action="ACCESS_DENIED",
            reason=f"platform_only role={user.role}", request=request, details={"method": request.method},
        )
        raise PermissionError_(
            "Only the platform's own administrators see and manage every company.",
            details={"required_roles": sorted(allowed), "your_role": user.role, "platform_only": True},
        )

    return _guard


__all__ = [
    "BY_KEY", "CATALOGUE", "CONFIGURABLE_ROLES", "DEFAULT_SCOPE", "SCOPES", "allows", "complaint_scope",
    "defaults", "granted", "policy_from", "policy_of", "require_company_member", "require_permission",
    "require_platform_admin", "require_platform_staff", "roles_with",
]
