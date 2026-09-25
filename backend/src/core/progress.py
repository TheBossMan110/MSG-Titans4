"""
Live progress for a complaint being analysed.

Intake takes a few seconds, most of it waiting on a language model. Telling
the person who submitted it what is actually happening -- which step, which
model, that a busy model was swapped for another -- turns an anonymous wait
into one they can follow.

The pipeline reports through :func:`emit`, which does nothing unless a caller
has opened :func:`reporting` around the work. That keeps the pipeline free of
any knowledge of HTTP: the streaming endpoint listens, the benchmark and the
tests do not, and the same code runs for all three.

Every step is a fixed id from :data:`STEPS`. What a step *says* is written for
a customer, because a customer is who watches it; nothing here may carry a
priority, an escalation level or a verification outcome.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

# (id, what the step is called while it runs). The order is the order a
# complaint moves through them; a step may be skipped but never reordered.
STEPS: list[tuple[str, str]] = [
    ("read", "Reading your complaint"),
    ("safety", "Checking it is safe to process"),
    ("details", "Checking the details you gave"),
    ("history", "Looking for earlier complaints"),
    ("saved", "Saving it with a reference"),
    ("rules", "Company rules are classifying it"),
    ("policy", "Finding the policies that apply"),
    ("ai", "AI is analysing your complaint"),
    ("verify", "Checking the AI against the rules"),
    ("route", "Sending it to the right team"),
]
STEP_IDS = [step for step, _ in STEPS]
LABELS = dict(STEPS)

Sink = Callable[[dict[str, Any]], None]
_sink: ContextVar[Sink | None] = ContextVar("progress_sink", default=None)
_started: ContextVar[float] = ContextVar("progress_started", default=0.0)


@contextmanager
def reporting(sink: Sink) -> Iterator[None]:
    """Send every step emitted inside this block to ``sink``."""
    token = _sink.set(sink)
    clock = _started.set(time.perf_counter())
    try:
        yield
    finally:
        _sink.reset(token)
        _started.reset(clock)


def emit(step: str, state: str = "active", detail: str | None = None) -> None:
    """
    Report that ``step`` is now ``active``, ``done`` or ``skipped``.

    Never raises: a listener that has gone away (a closed browser tab) must not
    fail the analysis it was only watching.
    """
    sink = _sink.get()
    if sink is None:
        return
    try:
        sink({
            "step": step,
            "state": state,
            "label": LABELS.get(step, step),
            "detail": detail,
            "elapsed_ms": int((time.perf_counter() - _started.get()) * 1000),
        })
    except Exception:  # noqa: BLE001, S110 - progress is advisory
        pass


def active() -> bool:
    """Whether anyone is listening -- to skip building a costly detail string."""
    return _sink.get() is not None
