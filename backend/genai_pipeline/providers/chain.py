"""
Model chains: an ordered list of model names per provider, tried in turn.

Why this exists. Twice during this project a provider stopped answering to a
model name that had been working the day before — Google retired
``gemini-2.5-flash`` ("no longer available to new users") and Groq dropped
its Llama models altogether. Each time a single pinned name turned the whole
GenAI pipeline dark without a line of code changing, and the system quietly
degraded to rules-only. On top of that, the free tiers 503 their busiest
models for minutes at a time.

So every provider takes a comma-separated chain in configuration and falls
through it. The rules for falling through are deliberately narrow:

* **Fall through** on failures that belong to the *model*: a retired or
  unknown name (404) and a model-level overload or server error (5xx).
* **Do not fall through** on failures that belong to the *account*: a bad key
  (401/403), a rate limit, a timeout, a refusal. Retrying those against three
  more names burns quota, multiplies the wait, and reports the last model as
  the culprit instead of the key.

Each provider also remembers the model that last answered and tries it first
next time. The free tier 503s different models at different moments, so the
head of the configured chain is not reliably the fastest route; paying two
failed calls before every success is a real slice of the per-complaint
latency budget (NFR 1).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

from genai_pipeline.providers.base import ProviderServerError, ProviderUnavailable, RateLimited
from src.core import progress

T = TypeVar("T")

# provider name -> the model that most recently answered for it
_last_good: dict[str, str] = {}


def parse_chain(value: str | None, fallback: str) -> list[str]:
    """Split a comma-separated chain, dropping blanks. Never returns empty."""
    chain = [m.strip() for m in (value or "").split(",") if m.strip()]
    return chain or [fallback]


def preferred_order(provider: str, chain: list[str]) -> list[str]:
    """The configured chain with the last model that answered moved to the front."""
    good = _last_good.get(provider)
    if good and good in chain and chain[0] != good:
        return [good] + [m for m in chain if m != good]
    return list(chain)


def remember(provider: str, model: str) -> None:
    _last_good[provider] = model


def forget(provider: str | None = None) -> None:
    """Clear the memory — for tests, or after a configuration change."""
    if provider is None:
        _last_good.clear()
    else:
        _last_good.pop(provider, None)


def is_model_fault(exc: BaseException) -> bool:
    """
    True when another model name on the same account might succeed.

    A rate limit counts: free-tier quotas are per model, so the next model in
    the chain has a bucket of its own. A bad key does not -- every model on
    the account would refuse it the same way.
    """
    if isinstance(exc, RateLimited):
        return True
    if not isinstance(exc, (ProviderUnavailable, ProviderServerError)):
        return False
    return getattr(exc, "status", None) not in (401, 402, 403)


def run_chain(
    provider: str,
    chain: list[str],
    call: Callable[[str], T],
    *,
    log: Any,
) -> tuple[str, T]:
    """
    Call ``call(model)`` for each model in order until one succeeds.

    Returns ``(model_that_answered, result)``. Re-raises the last model-fault
    error if every model fails, and raises account-level errors immediately.
    """
    order = preferred_order(provider, chain)
    for index, model in enumerate(order):
        try:
            result = call(model)
        except (ProviderUnavailable, ProviderServerError, RateLimited) as exc:
            if not is_model_fault(exc):
                raise  # the key, not the model
            remaining = len(order) - index - 1
            log.warning(
                "model_fallback",
                provider=provider,
                model=model,
                remaining=remaining,
                error=str(exc)[:200],
            )
            if not remaining:
                raise
            progress.emit("ai", detail=f"{model} is busy; switching to {order[index + 1]}")
        else:
            remember(provider, model)
            return model, result
    raise ProviderUnavailable(f"no {provider} model configured", provider=provider)
