"""
Which organisation a request belongs to, enforced underneath every query.

    signed-in user  -> bind(db, user.organisation_id)              (src/core/deps.py)
    every ORM SELECT, UPDATE and DELETE on a TenantScoped table
                    -> ... AND organisation_id = <bound>            (_scope, below)
    every INSERT of a TenantScoped row
                    -> organisation_id = <bound>, else the parent row's
                       (a status-history row takes its complaint's), else
                       the default organisation                     (_stamp, below)

Filtering in one place, below the endpoints, is the point. Forty tables and a
few hundred queries reach complaint data; a WHERE that every endpoint had to
remember would be one forgotten clause away from showing one company another
company's complaints. Here an endpoint that forgets is filtered anyway, and
tests/test_tenancy.py walks the listing endpoints as two companies to prove
neither sees the other.

A session with nothing bound -- seeding, the email poller, SLA sweeps, sign-in
before the user is known -- sees every organisation, which is what those jobs
need. A count that must stay global (the CMP- and CUST- reference sequences,
which are unique across the platform) opts out explicitly with
``.execution_options(**ALL_TENANTS)``.
"""

from __future__ import annotations

import re
import threading
import time
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import event
from sqlalchemy.orm import Session, with_loader_criteria

from src.db.base import DEFAULT_ORGANISATION_ID, PLATFORM_ORGANISATION_ID, TenantScoped

TENANT_KEY = "sn_organisation_id"
ALL_TENANTS = {"all_tenants": True}


def bind(db: Session, organisation_id: uuid.UUID | None) -> None:
    """Scope everything this session reads and writes to one organisation."""
    if organisation_id is None:
        db.info.pop(TENANT_KEY, None)
    else:
        db.info[TENANT_KEY] = organisation_id


def current(db: Session) -> uuid.UUID | None:
    return db.info.get(TENANT_KEY)


def is_platform(organisation_id: Any) -> bool:
    """The platform's own organisation: super administrators, and no business data."""
    return organisation_id == PLATFORM_ORGANISATION_ID


def owns_template(organisation_id: Any) -> bool:
    """
    The reference company whose dataset defined the shared template (taxonomy,
    rule matrix, lexicon, prompts). Its administrators, like the super
    administrators, may edit it; every other company reads it.
    """
    return organisation_id == DEFAULT_ORGANISATION_ID


@contextmanager
def all_companies(db: Session) -> Generator[None, None, None]:
    """
    Read across every company for the platform's aggregate figures, then put
    the session back as it was. Only ever used to compute totals: nothing
    computed inside is returned row by row.
    """
    bound = db.info.pop(TENANT_KEY, None)
    try:
        yield
    finally:
        if bound is not None:
            db.info[TENANT_KEY] = bound


# ══════════════════════════════════════════════════════════════
# the filter
# ══════════════════════════════════════════════════════════════
@event.listens_for(Session, "do_orm_execute")
def _scope(state) -> None:
    tenant = state.session.info.get(TENANT_KEY)
    if tenant is None or state.execution_options.get("all_tenants"):
        return
    reading = state.is_select and not state.is_column_load and not state.is_relationship_load
    if reading or state.is_update or state.is_delete:
        state.statement = state.statement.options(
            with_loader_criteria(
                TenantScoped, lambda cls: cls.organisation_id == tenant, include_aliases=True,
            )
        )


_scoped_by_table: dict[str, type] = {}


def _model_for(table_name: str) -> type | None:
    if not _scoped_by_table:
        from src.db.base import Base

        for mapper in Base.registry.mappers:
            if issubclass(mapper.class_, TenantScoped):
                _scoped_by_table[mapper.local_table.name] = mapper.class_
    return _scoped_by_table.get(table_name)


def _inherited(session: Session, obj: Any) -> uuid.UUID | None:
    """The organisation of the row this one hangs off (its complaint, version, user)."""
    with session.no_autoflush:
        for fk in obj.__table__.foreign_keys:
            if fk.parent.name == "organisation_id":
                continue
            model = _model_for(fk.column.table.name)
            value = getattr(obj, fk.parent.name, None) if model is not None else None
            if value is None:
                continue
            parent = session.get(model, value)
            if parent is not None and parent.organisation_id is not None:
                return parent.organisation_id
    return None


@event.listens_for(Session, "before_flush")
def _stamp(session: Session, _ctx, _instances) -> None:
    tenant = session.info.get(TENANT_KEY)
    for obj in list(session.new):
        if isinstance(obj, TenantScoped) and obj.organisation_id is None:
            obj.organisation_id = tenant or _inherited(session, obj) or DEFAULT_ORGANISATION_ID


# ══════════════════════════════════════════════════════════════
# organisations, remembered briefly
# ══════════════════════════════════════════════════════════════
# The access policy is read on every permission check; reading it from a
# database a network hop away each time would cost more than the request.
# A copy lives for a short while and is dropped the moment an organisation
# row is committed in this process, so a changed policy applies at once.
_TTL_S = 30.0
_cache: dict[uuid.UUID, tuple[float, dict[str, Any]]] = {}
_lock = threading.Lock()


def info(organisation_id: uuid.UUID | None) -> dict[str, Any] | None:
    if organisation_id is None:
        return None
    now = time.monotonic()
    hit = _cache.get(organisation_id)
    if hit is not None and now - hit[0] < _TTL_S:
        return hit[1]
    from src.db.base import SessionLocal
    from src.db.models import Organisation

    db = SessionLocal()
    try:
        row = db.get(Organisation, organisation_id)
        value = None if row is None else {
            "id": row.id, "name": row.name, "slug": row.slug, "industry": row.industry,
            "is_active": row.is_active, "settings": dict(row.settings or {}),
            "created_at": row.created_at,
        }
    finally:
        db.close()
    if value is not None:
        with _lock:
            _cache[organisation_id] = (now, value)
    return value


def brief(organisation_id: uuid.UUID | None) -> dict[str, Any] | None:
    """What the signed-in user's own record says about their organisation."""
    found = info(organisation_id)
    if found is None:
        return None
    return {"id": found["id"], "name": found["name"], "slug": found["slug"],
            "is_platform": is_platform(found["id"]), "owns_template": owns_template(found["id"])}


def is_suspended(organisation_id: uuid.UUID | None) -> bool:
    """A company the platform has suspended: its people may not sign in or make requests."""
    found = info(organisation_id)
    return found is not None and not found["is_active"]


def settings_of(organisation_id: uuid.UUID | None) -> dict[str, Any]:
    found = info(organisation_id)
    return found["settings"] if found else {}


def forget(organisation_id: uuid.UUID | None = None) -> None:
    with _lock:
        if organisation_id is None:
            _cache.clear()
        else:
            _cache.pop(organisation_id, None)


@event.listens_for(Session, "after_flush")
def _organisations_written(session: Session, _ctx) -> None:
    from src.db.models import Organisation

    touched = {o.id for o in (*session.new, *session.dirty, *session.deleted) if isinstance(o, Organisation)}
    if touched:
        session.info.setdefault("sn_orgs_written", set()).update(touched)


@event.listens_for(Session, "after_commit")
def _forget_written(session: Session) -> None:
    for organisation_id in session.info.pop("sn_orgs_written", ()):
        forget(organisation_id)


@event.listens_for(Session, "after_rollback")
def _discard_written(session: Session) -> None:
    session.info.pop("sn_orgs_written", None)


# ══════════════════════════════════════════════════════════════
# creating organisations
# ══════════════════════════════════════════════════════════════
def slug_for(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return (slug or "company")[:48]


def unique_slug(db: Session, name: str) -> str:
    from sqlalchemy import select

    from src.db.models import Organisation

    base = slug_for(name)
    taken = set(db.execute(select(Organisation.slug).where(Organisation.slug.like(f"{base}%"))).scalars())
    if base not in taken:
        return base
    n = 2
    while f"{base}-{n}" in taken:
        n += 1
    return f"{base}-{n}"


def ensure_default(db: Session) -> None:
    """The organisation the seeded data belongs to. Idempotent."""
    from src.db.models import AppConfig, Organisation

    if db.get(Organisation, DEFAULT_ORGANISATION_ID) is not None:
        return
    profile = db.get(AppConfig, "organisation")
    name = (profile.value or {}).get("name") if profile is not None and isinstance(profile.value, dict) else None
    db.add(Organisation(
        id=DEFAULT_ORGANISATION_ID, name=name or "RaftarXpress Logistics (Pvt) Ltd",
        slug="raftarxpress", industry="Logistics & courier", is_active=True, settings={},
    ))
    db.flush()


def ensure_platform(db: Session) -> None:
    """The platform's own organisation, for the super administrators. Idempotent."""
    from src.db.models import Organisation

    if db.get(Organisation, PLATFORM_ORGANISATION_ID) is not None:
        return
    db.add(Organisation(
        id=PLATFORM_ORGANISATION_ID, name="SupportNova Platform", slug=unique_slug(db, "platform"),
        industry="Platform", is_active=True, settings={},
    ))
    db.flush()


__all__ = [
    "ALL_TENANTS", "TENANT_KEY", "all_companies", "bind", "brief", "current", "ensure_default",
    "ensure_platform", "forget", "info", "is_platform", "is_suspended", "owns_template", "settings_of",
    "slug_for", "unique_slug",
]
