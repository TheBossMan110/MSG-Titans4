"""
Compute the heaviest shared pages once, right after start-up.

Without this the first person to open the admin dashboard after a restart
waits for ~60 queries over the hosted database (13 s measured). Everything
here is the same for every viewer of a role, so one computation serves all of
them from the response cache; per-user pages warm themselves on first visit.
"""

from __future__ import annotations

import inspect
import threading
import time
from typing import Any

from src.core.logging import get_logger

log = get_logger("warmup")


def _defaults(endpoint: Any, **overrides: Any) -> dict[str, Any]:
    """The arguments FastAPI would pass for a request with no query string."""
    params = inspect.signature(getattr(endpoint, "__wrapped__", endpoint)).parameters
    values: dict[str, Any] = {}
    for name, param in params.items():
        if name in ("db", "user", "request", "response"):
            continue
        default = param.default
        values[name] = getattr(default, "default", default) if default is not inspect.Parameter.empty else None
    values.update({k: v for k, v in overrides.items() if k in params})
    return values


def warm() -> None:
    from src.api.v1 import admin, analytics, documents, organisation
    from src.db.base import SessionLocal

    started = time.monotonic()
    jobs = [
        (analytics.dashboard, {"days": 365}),      # the admin dashboard's default window
        # the analytics page opens on the last 30 days
        (analytics.dashboard, {"days": 30}),
        (analytics.volume, {"days": 30}),
        (analytics.categories, {"days": 30}),
        (analytics.departments, {"days": 30}),
        (analytics.pipelines, {"days": 30}),
        (analytics.rising_trends, {"period": "WEEK"}),
        (analytics.products, {"days": 30}),
        (analytics.urgency, {"days": 30}),
        (analytics.sentiment, {"days": 30}),
        (analytics.resolution_time, {"days": 30}),
        (analytics.repeat_complaints, {"days": 30}),
        (analytics.manager_overview, {}),
        (admin.list_rules, {}),
        (admin.get_taxonomy, {}),
        (organisation.organisation, {}),
        (documents.list_documents, {}),
        (documents.coverage, {}),
    ]
    done = 0
    for endpoint, overrides in jobs:
        db = SessionLocal()
        try:
            endpoint(db=db, **_defaults(endpoint, **overrides))
            db.commit()
            done += 1
        except Exception as exc:  # noqa: BLE001 - a page that fails to warm simply warms on first visit
            db.rollback()
            log.warning("warmup_failed", endpoint=endpoint.__name__, error=f"{type(exc).__name__}: {exc}"[:200])
        finally:
            db.close()
    log.info("warmup_done", pages=done, seconds=round(time.monotonic() - started, 1))


def start() -> threading.Thread:
    thread = threading.Thread(target=warm, name="page-warmup", daemon=True)
    thread.start()
    return thread
