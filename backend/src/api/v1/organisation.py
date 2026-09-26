"""
The organisation itself: who it is, its teams, taxonomy, service levels and
reply templates -- everything the dataset's ``configuration/`` folder defines,
read back from the database it was loaded into.

One call rather than six, because the page that shows it shows all of it.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request, status as http_status
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from schemas.organisation import (
    CategoryOut,
    CustomerMixOut,
    DatasetBrief,
    DepartmentCreate,
    OrganisationOut,
    OrganisationProfileOut,
    SLARowOut,
    SubcategoryBrief,
    TeamOut,
    TemplateOut,
)
from src.core.deps import CurrentUser, DbSession, require_role
from src.core.errors import ConflictError, ValidationError
from src.db.enums import ComplaintStatus, DocStatus, UserRole
from src.db.models import (
    AppConfig,
    Category,
    Complaint,
    Department,
    Document,
    DocumentVersion,
    SLAPolicy,
    User,
)

router = APIRouter(prefix="/organisation", tags=["Organisation"])

STAFF = (UserRole.AGENT, UserRole.REVIEWER, UserRole.MANAGER, UserRole.ADMIN, UserRole.EVALUATOR)
_CLOSED = (ComplaintStatus.RESOLVED, ComplaintStatus.CLOSED)


def _config(db: Any, key: str, default: Any) -> Any:
    row = db.get(AppConfig, key)
    return row.value if row is not None and row.value is not None else default


@router.get(
    "",
    response_model=OrganisationOut,
    dependencies=[Depends(require_role(*STAFF))],
    summary="The organisation, its teams, taxonomy, SLAs and templates",
)
def organisation(db: DbSession) -> OrganisationOut:
    profile = _config(db, "organisation", {})
    extras: dict[str, dict[str, Any]] = _config(db, "department_profiles", {})

    categories = db.execute(
        select(Category)
        .where(Category.is_active.is_(True))
        .order_by(Category.name)
        .options(selectinload(Category.subcategories))
    ).scalars().all()
    departments = db.execute(
        select(Department).where(Department.is_active.is_(True)).order_by(Department.name)
    ).scalars().all()
    dept_code = {d.id: d.code for d in departments}

    per_dept_total = dict(db.execute(
        select(Complaint.department_id, func.count()).group_by(Complaint.department_id)
    ).all())
    per_dept_open = dict(db.execute(
        select(Complaint.department_id, func.count())
        .where(Complaint.status.not_in(_CLOSED))
        .group_by(Complaint.department_id)
    ).all())
    per_category = dict(db.execute(
        select(Complaint.category_id, func.count()).group_by(Complaint.category_id)
    ).all())

    routed: dict[str, list[str]] = {}
    for c in categories:
        code = dept_code.get(c.default_department_id)
        if code:
            routed.setdefault(code, []).append(c.name)

    teams = [
        TeamOut(
            code=d.code, name=d.name, description=d.description, email=d.email,
            escalation_contact=extras.get(d.code, {}).get("escalation_contact"),
            handles=extras.get(d.code, {}).get("handles") or [],
            sla_response_hours=extras.get(d.code, {}).get("sla_response_hours"),
            sla_resolution_hours=extras.get(d.code, {}).get("sla_resolution_hours"),
            categories=routed.get(d.code, []),
            open_complaints=per_dept_open.get(d.id, 0),
            total_complaints=per_dept_total.get(d.id, 0),
        )
        for d in departments
    ]

    category_rows = [
        CategoryOut(
            code=c.code, name=c.name, description=c.description,
            default_department=dept_code.get(c.default_department_id),
            subcategories=[
                SubcategoryBrief(code=s.code, name=s.name)
                for s in sorted(c.subcategories, key=lambda s: s.name) if s.is_active
            ],
            complaints=per_category.get(c.id, 0),
        )
        for c in categories
    ]

    category_code = {c.id: c.code for c in categories}
    sla = [
        SLARowOut(
            category=category_code.get(p.category_id) if p.category_id else None,
            priority=p.priority_code,
            first_response_mins=p.first_response_mins,
            resolution_mins=p.resolution_mins,
        )
        for p in db.execute(
            select(SLAPolicy).where(SLAPolicy.is_active.is_(True))
        ).scalars()
    ]
    sla.sort(key=lambda r: (r.category is not None, r.category or "", r.priority))

    templates = [
        TemplateOut(id=t.get("id", ""), scenario=t.get("scenario"), tone=t.get("tone"), text=t.get("text", ""))
        for t in _config(db, "response_templates", [])
        if isinstance(t, dict)
    ]

    mix = [
        CustomerMixOut(customer_type=kind, complaints=count)
        for kind, count in db.execute(
            select(Complaint.customer_type, func.count())
            .where(Complaint.customer_type.is_not(None))
            .group_by(Complaint.customer_type)
            .order_by(func.count().desc())
        ).all()
    ]

    tagged = db.execute(
        select(
            Complaint.dataset_tag,
            func.count(),
            func.count(Complaint.analyzed_at),
            func.count(Complaint.expected_category_code),
        )
        .where(Complaint.dataset_tag.is_not(None))
        .group_by(Complaint.dataset_tag)
        .order_by(func.count().desc())
    ).all()
    datasets = [
        DatasetBrief(dataset_tag=tag, total=total, analysed=analysed, labelled=labelled)
        for tag, total, analysed, labelled in tagged
    ]

    knowledge_base = {
        "documents": db.execute(select(func.count()).select_from(Document)).scalar_one(),
        "active_versions": db.execute(
            select(func.count()).select_from(DocumentVersion)
            .where(DocumentVersion.status == DocStatus.ACTIVE)
        ).scalar_one(),
    }

    return OrganisationOut(
        profile=OrganisationProfileOut(**{
            k: profile.get(k) for k in OrganisationProfileOut.model_fields if profile.get(k) is not None
        }),
        departments=teams,
        categories=category_rows,
        sla=sla,
        templates=templates,
        customer_mix=mix,
        datasets=datasets,
        knowledge_base=knowledge_base,
    )


@router.post(
    "/departments",
    response_model=TeamOut,
    status_code=http_status.HTTP_201_CREATED,
    dependencies=[Depends(require_role(UserRole.ADMIN))],
    summary="Create a new department and optionally provision its manager",
)
def create_department(
    payload: DepartmentCreate,
    request: Request,
    db: DbSession,
    user: CurrentUser,
) -> TeamOut:
    """Admin provisions a new department, and optionally creates a manager account for it."""
    from src.core.security import hash_password
    from src.services.audit import record_audit

    code = payload.code.strip().upper()
    name = payload.name.strip()
    if not code:
        raise ValidationError("Department code is required.")
    if not name:
        raise ValidationError("Department name is required.")

    existing = db.execute(select(Department).where(Department.code == code)).scalars().first()
    if existing is not None:
        raise ConflictError(f"Department with code '{code}' already exists.")

    dept = Department(
        code=code,
        name=name,
        description=payload.description.strip() if payload.description else None,
        email=payload.email.strip().lower() if payload.email else None,
        is_active=True,
    )
    db.add(dept)
    db.flush()

    record_audit(
        db,
        entity_type="department",
        entity_id=dept.id,
        action="DEPARTMENT_CREATED",
        actor=user,
        after={"code": code, "name": name, "email": dept.email},
        request=request,
    )

    manager_created = None
    if payload.manager_email and payload.manager_email.strip():
        m_email = payload.manager_email.strip().lower()
        if db.execute(select(User.id).where(func.lower(User.email) == m_email)).first():
            raise ConflictError(f"An account with email '{m_email}' already exists.")
        m_pwd = payload.manager_password or "SupportNova#2026"
        m_name = (payload.manager_name or f"{name} Manager").strip()
        manager_user = User(
            email=m_email,
            full_name=m_name,
            role=UserRole.MANAGER,
            password_hash=hash_password(m_pwd),
            department_id=dept.id,
            is_active=True,
        )
        db.add(manager_user)
        db.flush()
        record_audit(
            db,
            entity_type="user",
            entity_id=manager_user.id,
            action="USER_CREATED",
            actor=user,
            after={"email": m_email, "role": UserRole.MANAGER, "department": code},
            request=request,
        )
        manager_created = manager_user

    db.commit()

    return TeamOut(
        code=dept.code,
        name=dept.name,
        description=dept.description,
        email=dept.email,
        escalation_contact=manager_created.full_name if manager_created else None,
        handles=[],
        sla_response_hours=4.0,
        sla_resolution_hours=24.0,
        categories=[],
        open_complaints=0,
        total_complaints=0,
    )
