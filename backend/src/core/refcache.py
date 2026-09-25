"""
In-process cache for reference data: rules, lexicon, taxonomy, configuration.

Every complaint used to re-read all of it -- 619 rules, the signal lexicon, the
category tree, a dozen configuration rows -- from a database that is a network
hop away. Measured against the hosted database, the rules alone took up to
13 s and the lexicon 5 s of a single intake, for rows that change a few times
a week.

Correctness rests on three things:

* **Commit invalidates.** A session that writes to any reference table clears
  the cache when it commits. An administrator's change to a rule, a threshold
  or a category therefore applies to the very next complaint in this process,
  which is what SRS 1.8 #14 ("takes effect without a deploy") asks for.
* **Uncommitted writes bypass.** While a session holds unflushed or uncommitted
  reference changes, its reads skip the cache entirely -- it sees its own
  writes, and nothing it read is stored for anyone else.
* **A TTL** bounds staleness for a change made by *another* process (a
  seeding script, a second worker). Set ``REFERENCE_CACHE_SECONDS=0`` to turn
  caching off.

The server also warms the cache at startup and refreshes it in the background
before it expires (:func:`start_refresher`), so no customer's complaint is the
one that pays for reloading 619 rules over a slow link.

Only plain data is cached -- dataclasses, dicts, tuples -- never ORM instances,
which belong to the session that loaded them.
"""

from __future__ import annotations

import copy
import threading
import time
from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar

from sqlalchemy import event
from sqlalchemy.orm import Session

from src.core.config import settings

T = TypeVar("T")

# Tables whose rows the cached loaders read. A write to any of them from any
# session invalidates everything: the loaders overlap (the taxonomy feeds the
# prompt, the validator and the rule engine) and reference writes are rare.
REFERENCE_TABLES = frozenset({
    "rules", "lexicon_terms", "injection_patterns", "promise_patterns",
    "app_config", "categories", "subcategories", "departments",
    "priority_levels", "escalation_levels", "sla_policies", "prompt_versions",
})

_DIRTY = "reference_dirty"
_lock = threading.Lock()
_store: dict[tuple[Any, ...], tuple[float, int, Any]] = {}
_generation = 0
# Every cached loader that takes no argument besides the session, by name;
# these are what warming reloads.
_loaders: dict[str, Callable[..., Any]] = {}
# Set on invalidation so the refresher reloads at once instead of at its next
# scheduled pass; the next complaint after an admin edit then finds it warm.
_wake = threading.Event()


def invalidate() -> None:
    """Forget everything. Loaders read from the database again on next use."""
    global _generation
    with _lock:
        _generation += 1
        _store.clear()
    _wake.set()


def reference_data(name: str, *, copy_result: bool = True) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Cache a ``loader(db, *args)`` that returns plain data.

    ``copy_result`` hands each caller its own deep copy, so a caller that
    mutates what it got cannot corrupt the next caller's. Loaders whose result
    is large and only ever read (the rule list) pass ``False``.
    """
    def decorate(loader: Callable[..., T]) -> Callable[..., T]:
        @wraps(loader)
        def cached(db: Session, *args: Any) -> T:
            ttl = settings.reference_cache_seconds
            if ttl <= 0 or db.info.get(_DIRTY) or _pending_reference_writes(db):
                return loader(db, *args)

            key = (name, *args)
            now = time.monotonic()
            hit = _store.get(key)
            if hit is not None and hit[1] == _generation and now - hit[0] < ttl:
                return copy.deepcopy(hit[2]) if copy_result else hit[2]

            generation = _generation
            value = loader(db, *args)
            with _lock:
                # Invalidated while we were reading: what we read may predate
                # the change, so it is used once and not kept.
                if generation == _generation:
                    _store[key] = (now, generation, value)
            return copy.deepcopy(value) if copy_result else value

        cached.uncached = loader  # type: ignore[attr-defined]
        _loaders[name] = loader
        return cached

    return decorate


def warm() -> dict[str, Any]:
    """
    Load every registered loader into the cache now, replacing what is there.

    Returns what happened per loader. Never raises: a failed warm leaves that
    entry to load on demand, which is where it would have been anyway.
    """
    from src.db.base import SessionLocal

    report: dict[str, Any] = {}
    if settings.reference_cache_seconds <= 0:
        return report
    db = SessionLocal()
    try:
        for name, loader in list(_loaders.items()):
            started = time.perf_counter()
            generation = _generation
            try:
                value = loader(db)
            except TypeError:
                continue  # needs an argument; loads on first use instead
            except Exception as exc:  # noqa: BLE001 - warming is best effort
                db.rollback()
                report[name] = f"failed: {type(exc).__name__}"
                continue
            with _lock:
                if generation == _generation:
                    _store[(name,)] = (time.monotonic(), generation, value)
            report[name] = round(time.perf_counter() - started, 2)
    finally:
        db.close()
    return report


def start_refresher() -> threading.Thread | None:
    """
    Warm now, then refresh at a third of the TTL, in a daemon thread.

    Refreshing ahead of expiry means an entry is always replaced by a newer
    one rather than lapsing; a request never finds the cache cold.
    """
    ttl = settings.reference_cache_seconds
    if ttl <= 0:
        return None
    # Registration happens at import; make sure every loader module is loaded.
    import comparison_engine.engine  # noqa: F401
    import complaint_processing.entities  # noqa: F401
    import genai_pipeline.prompts  # noqa: F401
    import genai_pipeline.response  # noqa: F401
    import genai_pipeline.validator  # noqa: F401
    import python_validation.pipeline  # noqa: F401
    import security.injection_defense  # noqa: F401
    import security.response_guard  # noqa: F401
    from src.core.logging import get_logger

    log = get_logger("refcache")

    def loop() -> None:
        while True:
            started = time.perf_counter()
            report = warm()
            log.info(
                "reference_cache_warmed",
                seconds=round(time.perf_counter() - started, 1), loaders=report,
            )
            _wake.wait(timeout=max(30, ttl // 3))
            _wake.clear()

    thread = threading.Thread(target=loop, name="reference-cache-refresher", daemon=True)
    thread.start()
    return thread


# ══════════════════════════════════════════════════════════════
# invalidation, from the session's own bookkeeping
# ══════════════════════════════════════════════════════════════
def _is_reference(obj: Any) -> bool:
    return getattr(obj, "__tablename__", None) in REFERENCE_TABLES


def _pending_reference_writes(db: Session) -> bool:
    """Reference rows added or changed in this session but not yet flushed."""
    return any(_is_reference(o) for o in (*db.new, *db.dirty, *db.deleted))


@event.listens_for(Session, "before_flush")
def _mark_on_flush(session: Session, _context: Any, _instances: Any) -> None:
    if _pending_reference_writes(session):
        session.info[_DIRTY] = True


@event.listens_for(Session, "do_orm_execute")
def _mark_on_bulk(state: Any) -> None:
    """``update(Rule)...`` and friends bypass the unit of work; catch them here."""
    if not (state.is_update or state.is_delete or state.is_insert):
        return
    table = getattr(state.statement, "table", None)
    if getattr(table, "name", None) in REFERENCE_TABLES:
        state.session.info[_DIRTY] = True


@event.listens_for(Session, "after_commit")
def _invalidate_on_commit(session: Session) -> None:
    if session.info.pop(_DIRTY, False):
        invalidate()


@event.listens_for(Session, "after_soft_rollback")
def _forget_on_rollback(session: Session, _previous: Any) -> None:
    # Nothing was cached from inside the dirty transaction, so a rollback has
    # nothing to undo -- only the flag to clear.
    if not session.in_transaction():
        session.info.pop(_DIRTY, None)
