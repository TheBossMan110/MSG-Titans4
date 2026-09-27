"""
Fast reads for the dashboards: computed once, served from memory, recomputed
the moment the data behind them changes.

Why it exists. The database is a hosted Postgres far from this server; one
round trip costs 0.1-1.5 s. An admin dashboard needs ~60 queries, a manager
overview reads every complaint, and a page that fires five such requests at
once also waits for free connections. Measured on 2026-09-27: 20-72 s for the
heaviest pages, although nothing had changed between visits.

How it stays correct -- never stale after a change:

* **Generation.** Every commit that writes a tracked table (complaints, their
  status history, reviews, SLA clocks, users...) bumps a generation number. A
  cached answer from an older generation is never served; the next request
  recomputes it.
* **Re-warm.** Right after a change, a background thread recomputes the
  answers people were recently looking at, so the page that refreshes itself
  on the live pulse finds them ready rather than waiting.
* **Age.** Even with no writes, an answer older than its ``ttl`` is refreshed
  (SLA clocks move with time): the stale copy is served once while a
  background thread replaces it, so nobody waits for the refresh.
* **Single flight.** Ten browsers asking for the same cold answer cause one
  computation, not ten.

Answers are keyed by endpoint, parameters and -- where the endpoint takes the
signed-in user -- that user's id, so one person's view is never served to
another. Writes made by another process (a one-off script) are caught by the
``ttl`` rather than the generation.
"""

from __future__ import annotations

import functools
import inspect
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import event
from sqlalchemy.orm import Session

from src.core.logging import get_logger

log = get_logger("response_cache")

# Tables whose changes can alter a dashboard or a report. Sign-in bookkeeping
# (refresh tokens, the audit log) is deliberately absent: it changes nothing
# a dashboard shows, and a login should not empty the cache.
TRACKED = frozenset({
    "complaints", "complaint_status_history", "review_queue", "review_actions",
    "verification_decisions", "comparisons", "sla_events", "escalations", "follow_ups",
    "responses", "response_flags", "email_messages", "users", "customers",
    "complaint_policy_refs", "injection_events", "rules", "categories", "subcategories",
    "departments", "sla_policies", "documents", "document_versions", "app_config",
    "genai_runs", "complaint_attachments", "clarification_questions", "resolution_steps",
    "eligibility_decisions", "agent_guidance", "trend_snapshots",
})

WARM_WINDOW_S = 15 * 60      # re-warm what someone looked at in the last quarter hour
DEBOUNCE_S = 1.5             # let a burst of writes settle before re-warming
MAX_DEBOUNCE_S = 20.0        # ...but never postpone longer than this

_generation = 0
_gen_lock = threading.Lock()


@dataclass
class _Entry:
    value: Any
    generation: int
    computed_at: float
    ttl: float
    compute: Callable[[Session], Any]
    last_used: float = field(default_factory=time.monotonic)
    refreshing: bool = False


_store: dict[str, _Entry] = {}
_key_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def generation() -> int:
    return _generation


def _lock_for(key: str) -> threading.Lock:
    with _locks_guard:
        lock = _key_locks.get(key)
        if lock is None:
            lock = _key_locks[key] = threading.Lock()
        return lock


# ══════════════════════════════════════════════════════════════
# invalidation
# ══════════════════════════════════════════════════════════════
def _touches_tracked(objects) -> bool:
    return any(getattr(obj, "__tablename__", None) in TRACKED for obj in objects)


# A sign-in rewrites last_login_at and resets the failed-login count. Nothing a
# dashboard shows depends on either, and treating every login as a data change
# emptied the cache the moment someone signed in. Only these user fields count.
_VISIBLE_USER_FIELDS = ("role", "is_active", "department_id", "full_name", "email")


def _changed_visibly(obj: Any) -> bool:
    if getattr(obj, "__tablename__", None) != "users":
        return getattr(obj, "__tablename__", None) in TRACKED
    from sqlalchemy import inspect as sa_inspect

    attrs = sa_inspect(obj).attrs
    return any(attrs[name].history.has_changes() for name in _VISIBLE_USER_FIELDS)


@event.listens_for(Session, "before_flush")
def _before_flush(session: Session, _ctx, _instances) -> None:
    # Checked before the flush, while the attribute history still says what changed.
    changed = {getattr(o, "__tablename__", "?") for o in (*session.new, *session.deleted) if getattr(o, "__tablename__", None) in TRACKED}
    changed |= {getattr(o, "__tablename__", "?") for o in session.dirty if _changed_visibly(o)}
    if changed:
        session.info["sn_cache_dirty"] = True
        session.info.setdefault("sn_cache_tables", set()).update(changed)


@event.listens_for(Session, "do_orm_execute")
def _bulk_write(state) -> None:
    # UPDATE/DELETE statements bypass the flush; catch them by their table.
    mapper = state.bind_mapper
    if (state.is_update or state.is_delete) and mapper is not None and mapper.local_table.name in TRACKED:
        state.session.info["sn_cache_dirty"] = True
        state.session.info.setdefault("sn_cache_tables", set()).add(mapper.local_table.name)


@event.listens_for(Session, "after_commit")
def _after_commit(session: Session) -> None:
    tables = session.info.pop("sn_cache_tables", set())
    if session.info.pop("sn_cache_dirty", False):
        bump(tables)


@event.listens_for(Session, "after_rollback")
def _after_rollback(session: Session) -> None:
    session.info.pop("sn_cache_dirty", None)
    session.info.pop("sn_cache_tables", None)


def bump(tables: set[str] | None = None) -> None:
    """Something tracked changed: older answers are no longer servable."""
    global _generation
    with _gen_lock:
        _generation += 1
    log.info("cache_invalidated", tables=sorted(tables or []), generation=_generation)
    _schedule_rewarm()


def clear() -> None:
    """Forget everything (tests; a manual reset)."""
    global _generation
    with _gen_lock:
        _generation += 1
        _store.clear()


# ══════════════════════════════════════════════════════════════
# reading
# ══════════════════════════════════════════════════════════════
def _compute(key: str, compute: Callable[[Session], Any], db: Session, ttl: float) -> Any:
    lock = _lock_for(key)
    with lock:
        entry = _store.get(key)
        if entry is not None and entry.generation == _generation and time.monotonic() - entry.computed_at < entry.ttl:
            entry.last_used = time.monotonic()
            return entry.value          # someone else computed it while we waited
        gen = _generation               # read before computing: a write during it makes the result stale
        started = time.monotonic()
        value = compute(db)
        _store[key] = _Entry(value=value, generation=gen, computed_at=time.monotonic(), ttl=ttl, compute=compute)
        log.debug("cache_computed", key=key, seconds=round(time.monotonic() - started, 2))
        return value


def get_or_compute(key: str, compute: Callable[[Session], Any], db: Session, *, ttl: float = 60.0) -> Any:
    entry = _store.get(key)
    now = time.monotonic()
    if entry is not None and entry.generation == _generation:
        entry.last_used = now
        if now - entry.computed_at < entry.ttl:
            return entry.value
        # Old but not invalidated: serve it and refresh behind the scenes.
        _refresh_in_background(key, entry)
        return entry.value
    return _compute(key, compute, db, ttl)


def _refresh_in_background(key: str, entry: _Entry) -> None:
    if entry.refreshing:
        return
    entry.refreshing = True

    def run() -> None:
        from src.db.base import SessionLocal

        db = SessionLocal()
        try:
            _compute(key, entry.compute, db, entry.ttl)
            db.commit()
        except Exception as exc:  # noqa: BLE001 - a failed refresh keeps the old answer
            db.rollback()
            log.warning("cache_refresh_failed", key=key, error=f"{type(exc).__name__}: {exc}"[:200])
        finally:
            entry.refreshing = False
            db.close()

    threading.Thread(target=run, name="cache-refresh", daemon=True).start()


# ══════════════════════════════════════════════════════════════
# re-warming after a change
# ══════════════════════════════════════════════════════════════
_rewarm: dict[str, Any] = {"timer": None, "first": 0.0}
_rewarm_lock = threading.Lock()


def _schedule_rewarm() -> None:
    with _rewarm_lock:
        now = time.monotonic()
        timer = _rewarm["timer"]
        if timer is not None:
            if now - _rewarm["first"] >= MAX_DEBOUNCE_S:
                return              # already due soon; do not postpone further
            timer.cancel()
        else:
            _rewarm["first"] = now
        timer = threading.Timer(DEBOUNCE_S, _rewarm_now)
        timer.daemon = True
        _rewarm["timer"] = timer
        timer.start()


def _rewarm_now() -> None:
    with _rewarm_lock:
        _rewarm["timer"] = None
    from src.db.base import SessionLocal

    now = time.monotonic()
    hot = [(k, e) for k, e in list(_store.items()) if now - e.last_used < WARM_WINDOW_S and e.generation != _generation]
    hot.sort(key=lambda kv: kv[1].last_used, reverse=True)
    if not hot:
        return
    db = SessionLocal()
    try:
        for key, entry in hot:
            try:
                _compute(key, entry.compute, db, entry.ttl)
                db.commit()
            except Exception as exc:  # noqa: BLE001
                db.rollback()
                log.warning("cache_rewarm_failed", key=key, error=f"{type(exc).__name__}: {exc}"[:200])
        log.info("cache_rewarmed", entries=len(hot))
    finally:
        db.close()


# ══════════════════════════════════════════════════════════════
# the decorator
# ══════════════════════════════════════════════════════════════
def cached_endpoint(ttl: float = 60.0) -> Callable:
    """
    Cache a FastAPI endpoint's answer. Put it *under* the ``@router.get``.

    The endpoint must take ``db``; if it takes ``user``, the answer is kept
    per user and a background recompute reloads that user in its own session.
    Every other argument is part of the key.
    """
    def decorate(fn: Callable) -> Callable:
        params = inspect.signature(fn).parameters
        takes_user = "user" in params

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            db: Session = kwargs["db"]
            bound = {k: v for k, v in kwargs.items() if k not in ("db", "user", "request", "response")}
            user = kwargs.get("user")
            user_id = getattr(user, "id", None) if takes_user else None
            key = f"{fn.__module__}.{fn.__qualname__}|{user_id}|" + "&".join(f"{k}={bound[k]!r}" for k in sorted(bound))

            def compute(session: Session) -> Any:
                call = dict(kwargs)
                call["db"] = session
                if takes_user and user_id is not None and session is not db:
                    from src.db.models import User

                    call["user"] = session.get(User, user_id)
                return fn(*args, **call)

            return get_or_compute(key, compute, db, ttl=ttl)

        return wrapper

    return decorate


__all__ = ["bump", "cached_endpoint", "clear", "generation", "get_or_compute"]
