"""
A company on the platform: its profile, and who may do what inside it.

    GET  /company           the caller's company, its counts and access policy
    PATCH /company          rename it (administrator)
    PUT  /company/access    which work each role may do, and how much it sees

    POST  /company/create             a company and its first administrator (super administrators)
    GET   /company/all                every company (super administrators)
    PATCH /company/{id}/status        suspend or reactivate one (super administrators)

Everything here is scoped to the caller's own organisation by construction:
the session is bound to it (src/core/tenancy.py), so the counts are that
company's and the policy saved is that company's. An administrator of one
company cannot name another company here at all.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import func, select

from schemas.billing import SubscriptionUpdate
from schemas.company import (
    AccessPolicy,
    CompanyCounts,
    CompanyCreate,
    CompanyCreated,
    CompanyList,
    CompanyOut,
    CompanyPublicOut,
    CompanyRow,
    CompanyStatusIn,
    CompanyUpdate,
    PermissionOut,
)
from src.core import billing, permissions, tenancy
from src.core.deps import CurrentUser, DbSession, require_role
from src.core.errors import ConflictError, NotFoundError, ValidationError
from src.core.permissions import require_platform_staff
from src.core.security import hash_password
from src.db.enums import ComplaintStatus, UserRole
from src.db.models import AuditLog, Complaint, Document, Organisation, User
from src.services import platform as platform_service
from src.services.audit import record_audit

router = APIRouter(prefix="/company", tags=["Company"])

STAFF = (UserRole.AGENT, UserRole.REVIEWER, UserRole.MANAGER, UserRole.ADMIN, UserRole.EVALUATOR)
_CLOSED = (ComplaintStatus.RESOLVED, ComplaintStatus.CLOSED)


@router.post(
    "/create",
    response_model=CompanyCreated,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_platform_staff(UserRole.SUPERADMIN))],
    summary="Create a company and its first administrator (super administrators only)",
)
def create_company(payload: CompanyCreate, request: Request, db: DbSession, user: CurrentUser) -> CompanyCreated:
    """
    Companies do not sign themselves up: the platform decides who joins it, so
    a stranger cannot open a workspace and fill it with whatever they like.
    The super administrator creates the company here and hands its first
    administrator their sign-in details; nobody is signed in by this call.

    The administrator administers only the new, empty company: no complaints,
    no policies, no other people, and the shared taxonomy, rule matrix and
    prompts read-only. Staff are added from Users & Roles; customers join with
    the company's sign-up link.
    """
    name = payload.company_name.strip()
    email = str(payload.admin_email).strip().lower()
    if payload.plan not in billing.PLANS:
        raise ValidationError("That is not one of our plans.")
    if db.execute(select(Organisation.id).where(func.lower(Organisation.name) == name.lower())).first():
        raise ConflictError("A company with this name already exists.")
    taken = db.execute(
        select(User.id).where(func.lower(User.email) == email).execution_options(**tenancy.ALL_TENANTS)
    ).first()
    if taken:
        raise ConflictError("An account already exists for that email address. Use another for this company's administrator.")

    organisation = Organisation(
        name=name, slug=tenancy.unique_slug(db, name),
        industry=(payload.industry or "").strip() or None, is_active=True,
        settings={"subscription": billing.new_subscription(payload.plan, trial_days=payload.trial_days)},
    )
    db.add(organisation)
    db.flush()
    admin = User(
        email=email, full_name=payload.admin_full_name.strip(), role=UserRole.ADMIN, is_active=True,
        password_hash=hash_password(payload.admin_password), organisation_id=organisation.id,
    )
    db.add(admin)
    created = {"name": organisation.name, "slug": organisation.slug, "industry": organisation.industry,
               "administrator": email}
    # In the platform's log (this session is the platform's) and in the new company's own.
    record_audit(db, actor=user, entity_type="organisation", entity_id=organisation.id, action="COMPANY_CREATED",
                 after=created, request=request)
    db.add(AuditLog(
        actor_id=user.id, actor_role=user.role, entity_type="organisation", entity_id=str(organisation.id),
        action="COMPANY_CREATED", after=created, reason="Created by the platform", organisation_id=organisation.id,
    ))
    db.flush()
    return CompanyCreated(
        company=platform_service.company_rows(db, only=organisation.id)[0],
        admin_email=email, admin_full_name=admin.full_name, sign_in_path="/login",
        customer_signup_path=f"/register?company={organisation.slug}",
    )


@router.get(
    "/public/{slug}",
    response_model=CompanyPublicOut,
    summary="The name behind a company's customer sign-up link",
)
def public_profile(slug: str, db: DbSession) -> CompanyPublicOut:
    """Only what the sign-up page shows -- the name and industry -- and only for an active company."""
    found = db.execute(
        select(Organisation).where(Organisation.slug == slug.strip().lower(), Organisation.is_active.is_(True))
    ).scalars().first()
    if found is None:
        raise NotFoundError("That company sign-up link is not valid.")
    return CompanyPublicOut(name=found.name, industry=found.industry, slug=found.slug)


def _company(db: DbSession, user: User) -> CompanyOut:
    organisation = db.get(Organisation, user.organisation_id)
    staff = db.execute(
        select(func.count(User.id)).where(User.role.in_(("agent", "reviewer", "manager", "admin")))
    ).scalar_one()
    customers = db.execute(select(func.count(User.id)).where(User.role == UserRole.CUSTOMER)).scalar_one()
    complaints = db.execute(select(func.count(Complaint.id))).scalar_one()
    open_ = db.execute(select(func.count(Complaint.id)).where(Complaint.status.not_in(_CLOSED))).scalar_one()
    documents = db.execute(select(func.count(Document.id))).scalar_one()
    return CompanyOut(
        id=organisation.id, name=organisation.name, slug=organisation.slug, industry=organisation.industry,
        created_at=organisation.created_at, owns_template=tenancy.owns_template(organisation.id),
        counts=CompanyCounts(staff=staff, customers=customers, complaints=complaints,
                             open_complaints=open_, documents=documents),
        # From the row in this session: a change just made here is not committed yet.
        access=AccessPolicy(**permissions.policy_from(organisation.settings)),
        defaults=AccessPolicy(**permissions.defaults()),
        catalogue=[
            PermissionOut(key=p.key, label=p.label, description=p.description,
                          defaults=sorted(p.defaults), evaluator=p.evaluator)
            for p in permissions.CATALOGUE
        ],
        roles=list(permissions.CONFIGURABLE_ROLES),
        scopes=list(permissions.SCOPES),
        customer_signup_path=f"/register?company={organisation.slug}",
    )


@router.get(
    "",
    response_model=CompanyOut,
    dependencies=[Depends(require_role(*STAFF))],
    summary="Your company: profile, counts and who may do what",
)
def get_company(db: DbSession, user: CurrentUser) -> CompanyOut:
    return _company(db, user)


@router.patch(
    "",
    response_model=CompanyOut,
    dependencies=[Depends(require_role(UserRole.ADMIN))],
    summary="Rename your company or change its industry",
)
def update_company(payload: CompanyUpdate, request: Request, db: DbSession, user: CurrentUser) -> CompanyOut:
    organisation = db.get(Organisation, user.organisation_id)
    before = {"name": organisation.name, "industry": organisation.industry}
    if payload.name is not None:
        organisation.name = payload.name.strip()
    if payload.industry is not None:
        organisation.industry = payload.industry.strip() or None
    db.flush()
    record_audit(db, actor=user, entity_type="organisation", entity_id=organisation.id, action="COMPANY_UPDATED",
                 before=before, after={"name": organisation.name, "industry": organisation.industry}, request=request)
    tenancy.forget(organisation.id)
    return _company(db, user)


# ══════════════════════════════════════════════════════════════
# the platform's view of every company
# ══════════════════════════════════════════════════════════════
@router.get(
    "/all",
    response_model=CompanyList,
    dependencies=[Depends(require_platform_staff(UserRole.SUPERADMIN))],
    summary="Every company on the platform (super administrators only)",
)
def all_companies(db: DbSession) -> CompanyList:
    rows = platform_service.company_rows(db)
    active = sum(1 for r in rows if r.is_active)
    return CompanyList(total=len(rows), active=active, suspended=len(rows) - active, items=rows)


@router.patch(
    "/{organisation_id}/status",
    response_model=CompanyRow,
    dependencies=[Depends(require_platform_staff(UserRole.SUPERADMIN))],
    summary="Suspend or reactivate a company (super administrators only)",
)
def set_company_status(
    organisation_id: uuid.UUID, payload: CompanyStatusIn, request: Request, db: DbSession, user: CurrentUser,
) -> CompanyRow:
    """
    A suspended company's people are refused from their very next request, and
    cannot sign in or refresh a session, until it is reactivated. Nothing is
    deleted: reactivating restores everything as it was. Audited with the reason.
    """
    organisation = db.get(Organisation, organisation_id)
    if organisation is None or tenancy.is_platform(organisation.id):
        raise NotFoundError("No such company.")
    if tenancy.owns_template(organisation.id) and not payload.is_active:
        raise ValidationError(
            "The reference company cannot be suspended: its dataset defines the shared template, "
            "and the evaluation accounts belong to it."
        )
    before = organisation.is_active
    organisation.is_active = payload.is_active
    db.flush()
    if before != payload.is_active:
        record_audit(
            db, actor=user, entity_type="organisation", entity_id=organisation.id,
            action="COMPANY_REACTIVATED" if payload.is_active else "COMPANY_SUSPENDED",
            before={"is_active": before}, after={"is_active": payload.is_active, "name": organisation.name},
            reason=payload.reason, request=request,
        )
    tenancy.forget(organisation.id)
    return platform_service.company_rows(db, only=organisation.id)[0]


@router.put(
    "/{organisation_id}/subscription",
    response_model=CompanyRow,
    dependencies=[Depends(require_platform_staff(UserRole.SUPERADMIN))],
    summary="Set a company's plan after payment is arranged (super administrators only)",
)
def set_subscription(
    organisation_id: uuid.UUID, payload: SubscriptionUpdate, request: Request, db: DbSession, user: CurrentUser,
) -> CompanyRow:
    """Payment happens outside the application for now; this records the result. Audited with the reason."""
    organisation = db.get(Organisation, organisation_id)
    if organisation is None or tenancy.is_platform(organisation.id):
        raise NotFoundError("No such company.")
    if tenancy.owns_template(organisation.id):
        raise ValidationError("The reference company is not on a plan.")
    if payload.plan not in billing.PLANS:
        raise ValidationError("That is not one of our plans.")
    saved = dict(organisation.settings or {})
    before = saved.get("subscription")
    saved["subscription"] = {
        "plan": payload.plan, "status": payload.status, "billing_cycle": payload.billing_cycle,
        "trial_ends_at": payload.trial_ends_at.isoformat() if payload.trial_ends_at else None,
        "current_period_end": payload.current_period_end.isoformat() if payload.current_period_end else None,
    }
    organisation.settings = saved   # reassigned, so the JSON column registers the change
    db.flush()
    record_audit(
        db, actor=user, entity_type="organisation", entity_id=organisation.id, action="SUBSCRIPTION_UPDATED",
        before=before, after=saved["subscription"], reason=payload.reason, request=request,
    )
    tenancy.forget(organisation.id)
    return platform_service.company_rows(db, only=organisation.id)[0]


@router.put(
    "/access",
    response_model=CompanyOut,
    dependencies=[Depends(require_role(UserRole.ADMIN))],
    summary="Set which work each role may do, and how much of the register it sees",
)
def set_access(payload: AccessPolicy, request: Request, db: DbSession, user: CurrentUser) -> CompanyOut:
    """
    Takes effect on the next request of everyone in the company: permissions
    are read from this policy on every check, not baked into tokens. Every
    change is audited with the policy before and after. Administrators always
    keep every permission, so a company can never lock itself out.
    """
    problems: list[str] = []
    for role, keys in payload.permissions.items():
        if role not in permissions.CONFIGURABLE_ROLES:
            problems.append(f"'{role}' is not a configurable role ({', '.join(permissions.CONFIGURABLE_ROLES)}).")
            continue
        unknown = sorted(set(keys) - set(permissions.BY_KEY))
        if unknown:
            problems.append(f"Unknown permission(s) for {role}: {', '.join(unknown)}.")
    for role, scope in payload.complaint_scope.items():
        if role not in permissions.CONFIGURABLE_ROLES:
            problems.append(f"'{role}' is not a configurable role.")
        elif scope not in permissions.SCOPES:
            problems.append(f"Scope for {role} must be one of {', '.join(permissions.SCOPES)}.")
    if problems:
        raise ValidationError(" ".join(problems), details={"problems": problems})

    organisation = db.get(Organisation, user.organisation_id)
    before = permissions.policy_from(organisation.settings)
    saved = dict(organisation.settings or {})
    stored_permissions = dict(saved.get("permissions") or {})
    stored_scope = dict(saved.get("complaint_scope") or {})
    for role, keys in payload.permissions.items():
        stored_permissions[role] = sorted(set(keys))
    stored_scope.update(payload.complaint_scope)
    saved["permissions"], saved["complaint_scope"] = stored_permissions, stored_scope
    organisation.settings = saved   # reassigned, so the JSON column registers the change
    db.flush()
    record_audit(
        db, actor=user, entity_type="organisation", entity_id=organisation.id, action="ACCESS_POLICY_UPDATED",
        before=before, after=permissions.policy_from(saved), request=request,
    )
    # The cached copy is dropped again when this commits (tenancy._forget_written).
    tenancy.forget(organisation.id)
    return _company(db, user)
