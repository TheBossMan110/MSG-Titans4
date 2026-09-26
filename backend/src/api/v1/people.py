"""
The people register and the live pulse.

``/people`` is the administrator's view of every account: who they are, when
they joined and last signed in, and -- for a customer -- every complaint they
raised with its full status history, their sign-in activity and their emails.
Staff rows carry how many complaints are assigned to them.

``/live/pulse`` is a handful of counters the dashboards poll. When one moves
(a complaint filed through the form, the chat or email; an account created; an
email received; a status changed) the open pages refresh themselves, so an
administrator watching the dashboard sees a new customer's complaint without
reloading.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query, Request
from fastapi import status as http_status
from sqlalchemy import func, or_, select

from schemas.common import Page
from schemas.people import (
    PeopleSummary,
    PersonActivity,
    PersonComplaint,
    PersonCreate,
    PersonDetail,
    PersonEmail,
    PersonRow,
    PersonUpdate,
    Pulse,
    SignInOut,
    StatusStep,
)
from src.core.deps import CurrentUser, DbSession, require_role
from src.core.errors import ConflictError, NotFoundError, ValidationError
from src.core.security import hash_password
from src.db.enums import UserRole
from src.db.models import AuditLog, Complaint, ComplaintStatusHistory, Customer, Department, User
from src.db.models.email import EmailMessage

OVERSIGHT = (UserRole.ADMIN, UserRole.MANAGER, UserRole.EVALUATOR)
STAFF = (UserRole.AGENT, UserRole.REVIEWER, UserRole.MANAGER, UserRole.ADMIN, UserRole.EVALUATOR)
CLOSED_STATUSES = ("RESOLVED", "CLOSED")

router = APIRouter(prefix="/people", tags=["People"])
# Managers see the people register to monitor their teams; only an
# administrator creates accounts, assigns roles or disables them (FR ii).
AdminOnly = Depends(require_role(UserRole.ADMIN))
CanCreatePerson = Depends(require_role(UserRole.ADMIN, UserRole.MANAGER))
ROLES = {role.value for role in UserRole}
live_router = APIRouter(prefix="/live", tags=["People"], dependencies=[Depends(require_role(*STAFF))])
# Who a complaint can be assigned to: names, roles and teams only, for every
# member of staff (a reviewer reassigns without reading the people register).
staff_router = APIRouter(prefix="/staff", tags=["People"], dependencies=[Depends(require_role(*STAFF))])

_CHANNEL = {"WEB": "the web form", "CHAT": "chat with Nova", "EMAIL": "email", "UPLOAD": "an uploaded file", "PHONE": "phone", "IMPORT": "the dataset import"}

# The same wording the account's own Security page uses.
_ACTIVITY = {
    "LOGIN": ("Signed in", True),
    "LOGIN_PASSWORD_OK": ("Password accepted, waiting for code", True),
    "LOGIN_FAILED": ("Wrong password", False),
    "LOGIN_BLOCKED": ("Sign-in blocked", False),
    "ACCOUNT_LOCKED": ("Account locked after wrong passwords", False),
    "MFA_FAILED": ("Wrong two-step code", False),
    "LOGOUT": ("Signed out", True),
    "PASSWORD_CHANGED": ("Password changed", True),
    "MFA_ENABLED": ("Two-step sign-in turned on", True),
    "MFA_DISABLED": ("Two-step sign-in turned off", False),
    "SESSIONS_REVOKED": ("Sessions signed out", True),
    "PROFILE_UPDATED": ("Name changed", True),
    "REGISTER": ("Account created", True),
}


def _owned(users: list[User]):
    """
    A person's complaints: the ones they submitted, and the ones whose customer
    record carries their email (raised by email before or without signing in).
    The same rule "My complaints" uses, so both views always agree.
    """
    ids = [u.id for u in users]
    emails = [u.email.lower() for u in users]
    return or_(
        Complaint.submitted_by_user_id.in_(ids),
        Complaint.customer_id.in_(select(Customer.id).where(func.lower(Customer.email).in_(emails))),
    )


def _rows(db: DbSession, users: list[User]) -> list[PersonRow]:
    """Rows for these accounts, with their complaint figures in a few queries, not a few per account."""
    if not users:
        return []
    ids = [u.id for u in users]
    by_email = {u.email.lower(): u.id for u in users}
    departments = dict(db.execute(select(Department.id, Department.name)).all())
    customers: dict[uuid.UUID, str] = {}
    for uid, email, ref in db.execute(
        select(Customer.user_id, Customer.email, Customer.external_ref)
        .where(or_(Customer.user_id.in_(ids), func.lower(Customer.email).in_(list(by_email))))
    ).all():
        owner = uid if uid in ids else by_email.get((email or "").lower())
        if owner is not None:
            customers.setdefault(owner, ref)

    raised: dict[uuid.UUID, list[int | datetime | None]] = {}
    for submitter, email, ref, status, created in db.execute(
        select(Complaint.submitted_by_user_id, Customer.email, Customer.external_ref, Complaint.status, Complaint.created_at)
        .outerjoin(Customer, Customer.id == Complaint.customer_id)
        .where(_owned(users))
    ).all():
        owners = {submitter} & set(ids) or {by_email.get((email or "").lower())}
        for owner in owners - {None}:
            if ref:
                customers.setdefault(owner, ref)
            figures = raised.setdefault(owner, [0, 0, None])
            figures[0] += 1
            figures[1] += status not in CLOSED_STATUSES
            figures[2] = max(filter(None, (figures[2], created)), default=None)
    assigned = dict(db.execute(
        select(Complaint.assigned_to, func.count(Complaint.id))
        .where(Complaint.assigned_to.in_(ids), Complaint.status.not_in(CLOSED_STATUSES))
        .group_by(Complaint.assigned_to)
    ).all())
    out = []
    for u in users:
        total, open_, last = raised.get(u.id, (0, 0, None))
        out.append(PersonRow(
            id=u.id, full_name=u.full_name, email=u.email, role=u.role,
            department=departments.get(u.department_id), is_active=u.is_active,
            created_at=u.created_at, last_login_at=u.last_login_at, mfa_on=u.mfa_enabled_at is not None,
            customer_ref=customers.get(u.id), complaints=int(total or 0), open_complaints=int(open_ or 0),
            last_complaint_at=last, assigned=int(assigned.get(u.id, 0)),
        ))
    return out


@router.get("", response_model=Page[PersonRow], dependencies=[Depends(require_role(*OVERSIGHT))], summary="Every account, newest first")
def list_people(
    db: DbSession,
    role: str | None = Query(None, max_length=32),
    search: str | None = Query(None, max_length=200, description="Name, email or customer reference."),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
) -> Page[PersonRow]:
    query = select(User)
    if role:
        query = query.where(User.role == role.strip().lower())
    if search:
        pattern = f"%{search.strip().lower()}%"
        by_ref = select(Customer.user_id).where(func.lower(Customer.external_ref).like(pattern), Customer.user_id.is_not(None))
        query = query.where(or_(
            func.lower(User.full_name).like(pattern), func.lower(User.email).like(pattern), User.id.in_(by_ref),
        ))
    total = db.execute(select(func.count()).select_from(query.subquery())).scalar_one()
    users = db.execute(
        query.order_by(User.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    ).scalars().all()
    return Page[PersonRow](items=_rows(db, list(users)), total=total, page=page, page_size=page_size)


@router.get("/summary", response_model=PeopleSummary, dependencies=[Depends(require_role(*OVERSIGHT))], summary="Accounts at a glance: new sign-ups and recent sign-ins")
def people_summary(db: DbSession) -> PeopleSummary:
    now = datetime.now(UTC)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    by_role = dict(db.execute(select(User.role, func.count()).group_by(User.role)).all())
    new_7d = db.execute(select(func.count()).where(User.created_at >= now - timedelta(days=7))).scalar_one()
    new_today = db.execute(select(func.count()).where(User.created_at >= today)).scalar_one()
    signed_in_today = db.execute(select(func.count()).where(User.last_login_at >= today)).scalar_one()
    recent = db.execute(select(User).order_by(User.created_at.desc()).limit(6)).scalars().all()

    logins = db.execute(
        select(AuditLog).where(or_(
            (AuditLog.entity_type == "auth") & (AuditLog.action == "LOGIN"),
            (AuditLog.entity_type == "user") & (AuditLog.action == "REGISTER"),
        ))
        .order_by(AuditLog.created_at.desc()).limit(8)
    ).scalars().all()
    def _who(row: AuditLog) -> uuid.UUID | None:
        if row.actor_id:
            return row.actor_id
        try:
            return uuid.UUID(row.entity_id)
        except ValueError:
            return None

    people = {u.id: u for u in db.execute(
        select(User).where(User.id.in_([uid for uid in map(_who, logins) if uid]))
    ).scalars()} if logins else {}
    signins = []
    for row in logins:
        who = people.get(_who(row))
        signins.append(SignInOut(
            user_id=who.id if who else None, full_name=who.full_name if who else None, email=who.email if who else None,
            role=who.role if who else row.actor_role, at=row.created_at, ip_address=row.ip_address,
            first_time=row.action == "REGISTER",
        ))
    return PeopleSummary(
        total=sum(by_role.values()), by_role=by_role, new_7d=new_7d, new_today=new_today,
        signed_in_today=signed_in_today, recent_signups=_rows(db, list(recent)), recent_signins=signins,
    )


@router.get("/{identifier}", response_model=PersonDetail, dependencies=[Depends(require_role(*STAFF))], summary="One account: details, complaints with history, sign-ins, emails")
def person(identifier: str, db: DbSession) -> PersonDetail:
    # 1. Try finding by Customer.external_ref (e.g. CUST-00184)
    customer = db.execute(
        select(Customer).where(func.upper(Customer.external_ref) == identifier.strip().upper())
    ).scalars().first()

    user: User | None = None
    if customer is not None:
        if customer.user_id:
            user = db.get(User, customer.user_id)
        elif customer.email:
            user = db.execute(
                select(User).where(func.lower(User.email) == customer.email.lower())
            ).scalars().first()

    # 2. If not found by customer ref, try as UUID
    if user is None and customer is None:
        try:
            parsed_id = uuid.UUID(identifier)
            user = db.get(User, parsed_id)
            if user is None:
                customer = db.get(Customer, parsed_id)
                if customer and customer.user_id:
                    user = db.get(User, customer.user_id)
        except ValueError:
            pass

    if user is not None:
        row = _rows(db, [user])[0]
        if customer is None:
            customer = db.execute(
                select(Customer).where(or_(Customer.user_id == user.id, func.lower(Customer.email) == user.email.lower()))
                .order_by(Customer.user_id.is_(None))
            ).scalars().first()

        complaints: list[PersonComplaint] = []
        found = db.execute(select(Complaint).where(_owned([user])).order_by(Complaint.created_at.desc())).scalars().all()
        if found:
            steps: dict[uuid.UUID, list[ComplaintStatusHistory]] = {}
            for step in db.execute(
                select(ComplaintStatusHistory)
                .where(ComplaintStatusHistory.complaint_id.in_([c.id for c in found]))
                .order_by(ComplaintStatusHistory.created_at)
            ).scalars():
                steps.setdefault(step.complaint_id, []).append(step)
            complaints = [
                PersonComplaint(
                    public_ref=c.public_ref, title=c.title, status=c.status, channel=c.channel,
                    category=c.category.name if c.category else None,
                    department=c.department.name if c.department else None,
                    priority=c.priority_code, urgency=c.urgency, sentiment=c.sentiment,
                    created_at=c.created_at, resolved_at=c.resolved_at,
                    updated_at=steps[c.id][-1].created_at if steps.get(c.id) else None,
                    history=[StatusStep(to_status="SUBMITTED", at=c.created_at, reason=f"via {_CHANNEL.get(c.channel, c.channel.lower())}")] + [
                        StatusStep(from_status=s.from_status, to_status=s.to_status, at=s.created_at, reason=s.reason)
                        for s in steps.get(c.id, [])
                    ],
                )
                for c in found
            ]

        # Failed sign-ins are logged against the email typed; both are this person's history.
        events = db.execute(
            select(AuditLog)
            .where(
                AuditLog.entity_type.in_(("auth", "user")),
                or_(AuditLog.entity_id == str(user.id), AuditLog.entity_id == user.email.lower()),
                AuditLog.action.in_(list(_ACTIVITY)),
            )
            .order_by(AuditLog.created_at.desc()).limit(25)
        ).scalars().all()
        activity = [
            PersonActivity(at=e.created_at, action=e.action, label=_ACTIVITY[e.action][0], ok=_ACTIVITY[e.action][1], ip_address=e.ip_address)
            for e in events
        ]

        refs = dict(db.execute(select(Complaint.id, Complaint.public_ref).where(
            Complaint.id.in_(select(EmailMessage.complaint_id).where(EmailMessage.complaint_id.is_not(None)))
        )).all())
        address = user.email.lower()
        mails = db.execute(
            select(EmailMessage)
            .where(or_(func.lower(EmailMessage.from_address) == address, func.lower(EmailMessage.to_address) == address))
            .order_by(EmailMessage.created_at.desc()).limit(25)
        ).scalars().all()
        emails = [
            PersonEmail(id=m.id, direction=m.direction, subject=m.subject or "(no subject)", status=m.status,
                        at=m.created_at, complaint_ref=refs.get(m.complaint_id))
            for m in mails
        ]
        return PersonDetail(
            person=row, phone=customer.phone if customer else None, tier=customer.tier if customer else None,
            region=customer.region if customer else None, complaints=complaints, activity=activity, emails=emails,
        )

    if customer is not None:
        found = db.execute(select(Complaint).where(Complaint.customer_id == customer.id).order_by(Complaint.created_at.desc())).scalars().all()
        steps: dict[uuid.UUID, list[ComplaintStatusHistory]] = {}
        if found:
            for step in db.execute(
                select(ComplaintStatusHistory)
                .where(ComplaintStatusHistory.complaint_id.in_([c.id for c in found]))
                .order_by(ComplaintStatusHistory.created_at)
            ).scalars():
                steps.setdefault(step.complaint_id, []).append(step)
        complaints_list = [
            PersonComplaint(
                public_ref=c.public_ref, title=c.title, status=c.status, channel=c.channel,
                category=c.category.name if c.category else None,
                department=c.department.name if c.department else None,
                priority=c.priority_code, urgency=c.urgency, sentiment=c.sentiment,
                created_at=c.created_at, resolved_at=c.resolved_at,
                updated_at=steps[c.id][-1].created_at if steps.get(c.id) else None,
                history=[StatusStep(to_status="SUBMITTED", at=c.created_at, reason=f"via {_CHANNEL.get(c.channel, c.channel.lower())}")] + [
                    StatusStep(from_status=s.from_status, to_status=s.to_status, at=s.created_at, reason=s.reason)
                    for s in steps.get(c.id, [])
                ],
            )
            for c in found
        ]
        synth_row = PersonRow(
            id=customer.id,
            full_name=customer.display_name,
            email=customer.email or f"{customer.external_ref.lower()}@customer.local",
            role=UserRole.CUSTOMER,
            department=None,
            is_active=True,
            created_at=customer.created_at,
            last_login_at=None,
            mfa_on=False,
            customer_ref=customer.external_ref,
            complaints=len(complaints_list),
            open_complaints=sum(1 for c in found if c.status not in CLOSED_STATUSES),
            last_complaint_at=found[0].created_at if found else None,
            assigned=0,
        )
        return PersonDetail(
            person=synth_row,
            phone=customer.phone,
            tier=customer.tier,
            region=customer.region,
            complaints=complaints_list,
            activity=[],
            emails=[],
        )

    raise NotFoundError(f"No account or customer found for '{identifier}'.")


@live_router.get("/pulse", response_model=Pulse, summary="Counters that move when anything new arrives")
def pulse(db: DbSession) -> Pulse:
    latest_complaint = db.execute(
        select(Complaint.public_ref, Complaint.created_at).order_by(Complaint.created_at.desc()).limit(1)
    ).first()
    latest_user = db.execute(select(User.full_name, User.created_at).order_by(User.created_at.desc()).limit(1)).first()
    latest_email = db.execute(
        select(EmailMessage.from_address, EmailMessage.created_at)
        .where(EmailMessage.direction == "IN").order_by(EmailMessage.created_at.desc()).limit(1)
    ).first()
    return Pulse(
        complaints=db.execute(select(func.count(Complaint.id))).scalar_one(),
        latest_complaint_ref=latest_complaint[0] if latest_complaint else None,
        latest_complaint_at=latest_complaint[1] if latest_complaint else None,
        users=db.execute(select(func.count(User.id))).scalar_one(),
        latest_user_name=latest_user[0] if latest_user else None,
        latest_user_at=latest_user[1] if latest_user else None,
        emails_in=db.execute(select(func.count(EmailMessage.id)).where(EmailMessage.direction == "IN")).scalar_one(),
        latest_email_from=latest_email[0] if latest_email else None,
        latest_email_at=latest_email[1] if latest_email else None,
        # The history table only grows, so its newest id changes whenever any status moves.
        status_changes=db.execute(select(func.coalesce(func.max(ComplaintStatusHistory.id), 0))).scalar_one(),
        checked_at=datetime.now(UTC),
    )


# ══════════════════════════════════════════════════════════════
# administration: accounts and roles
# ══════════════════════════════════════════════════════════════
def _department_id(db: DbSession, code: str | None):
    if not code:
        return None
    found = db.execute(select(Department.id).where(Department.code == code.strip().upper())).scalar()
    if found is None:
        raise ValidationError(f"No department with code '{code}'.")
    return found


@router.post("", response_model=PersonRow, status_code=http_status.HTTP_201_CREATED,
             dependencies=[CanCreatePerson], summary="Create an account with a role")
def create_person(payload: PersonCreate, request: Request, db: DbSession, user: CurrentUser) -> PersonRow:
    """Staff accounts are provisioned here; self-registration always creates a customer.
    Administrators can provision any role; managers can provision agents for their assigned department."""
    from src.services.audit import record_audit

    role = payload.role.strip().lower()
    if role not in ROLES:
        raise ValidationError(f"Role must be one of {', '.join(sorted(ROLES))}.")

    if user.role == UserRole.MANAGER:
        if role != UserRole.AGENT:
            raise ValidationError("Managers are only permitted to create Agent accounts.")
        if not user.department_id:
            raise ValidationError("Your account is not assigned to a department.")
        dept_id = user.department_id
    else:
        dept_id = _department_id(db, payload.department_code)

    email = payload.email.strip().lower()
    if db.execute(select(User.id).where(func.lower(User.email) == email)).first():
        raise ConflictError("An account with this email already exists.")
    person = User(
        email=email, full_name=payload.full_name.strip(), role=role,
        password_hash=hash_password(payload.password),
        department_id=dept_id, is_active=True,
    )
    db.add(person)
    db.flush()
    record_audit(
        db, entity_type="user", entity_id=person.id, action="USER_CREATED", actor=user,
        after={"email": email, "role": role, "department_id": str(dept_id) if dept_id else None}, request=request,
    )
    return _rows(db, [person])[0]


@router.patch("/{user_id}", response_model=PersonRow, dependencies=[AdminOnly],
              summary="Change an account's role, team, name, password or status")
def update_person(user_id: uuid.UUID, payload: PersonUpdate, request: Request, db: DbSession, user: CurrentUser) -> PersonRow:
    """
    A change of role or a disabled account signs the person out everywhere at
    once, so the old permissions do not outlive the change. An administrator
    cannot demote or disable themselves: the platform must never be left
    without one.
    """
    from src.services.audit import record_audit
    from src.services.auth import revoke_sessions

    person = db.get(User, user_id)
    if person is None:
        raise NotFoundError("No such account.")
    before = {"role": person.role, "department_id": str(person.department_id) if person.department_id else None,
              "is_active": person.is_active, "full_name": person.full_name}
    changes: dict = {}

    if payload.role is not None:
        role = payload.role.strip().lower()
        if role not in ROLES:
            raise ValidationError(f"Role must be one of {', '.join(sorted(ROLES))}.")
        if person.id == user.id and role != person.role:
            raise ValidationError("You cannot change your own role.")
        if role != person.role:
            person.role = role
            changes["role"] = role
    if payload.department_code is not None:
        department_id = _department_id(db, payload.department_code)
        if department_id != person.department_id:
            person.department_id = department_id
            changes["department"] = payload.department_code or None
    if payload.full_name is not None and payload.full_name.strip() != person.full_name:
        person.full_name = payload.full_name.strip()
        changes["full_name"] = person.full_name
    if payload.is_active is not None and payload.is_active != person.is_active:
        if person.id == user.id and not payload.is_active:
            raise ValidationError("You cannot disable your own account.")
        person.is_active = payload.is_active
        changes["is_active"] = payload.is_active
    if payload.password:
        person.password_hash = hash_password(payload.password)
        person.password_changed_at = datetime.now(UTC)
        person.failed_login_count = 0
        person.locked_until = None
        changes["password"] = "reset"

    if not changes:
        return _rows(db, [person])[0]
    db.flush()
    if {"role", "is_active", "password"} & set(changes):
        revoke_sessions(db, person, reason="Account changed by an administrator", request=request)
    record_audit(
        db, entity_type="user", entity_id=person.id, action="USER_UPDATED", actor=user,
        before=before, after=changes, request=request,
    )
    return _rows(db, [person])[0]


@staff_router.get("", summary="Active staff a complaint can be assigned to")
def staff_directory(db: DbSession) -> list[dict]:
    departments = dict(db.execute(select(Department.id, Department.name)).all())
    rows = db.execute(
        select(User).where(User.is_active.is_(True), User.role.in_(("agent", "reviewer", "manager", "admin")))
        .order_by(User.role, User.full_name)
    ).scalars().all()
    return [
        {"id": str(u.id), "full_name": u.full_name, "role": u.role, "team": departments.get(u.department_id)}
        for u in rows
    ]
