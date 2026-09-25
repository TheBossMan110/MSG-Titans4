"""
The organisation itself: who it is, its teams, taxonomy, service levels and
reply templates -- everything the dataset's ``configuration/`` folder defines,
read back from the database it was loaded into.

One call rather than six, because the page that shows it shows all of it.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from schemas.organisation import (
    CategoryOut,
    CustomerMixOut,
    DatasetBrief,
    OrganisationOut,
    OrganisationProfileOut,
    SLARowOut,
    SubcategoryBrief,
    TeamOut,
    TemplateOut,
)
from src.core.deps import DbSession, require_role
from src.db.enums import ComplaintStatus, DocStatus, UserRole
from src.db.models import (
    AppConfig,
    Category,
    Complaint,
    Department,
    Document,
    DocumentVersion,
    SLAPolicy,
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
