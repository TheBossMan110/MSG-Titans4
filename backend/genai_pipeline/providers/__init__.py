"""
Provider factory and failover chain (SRS Step 46, NFR 5).

    "Fallback behaviour must be defined."                  — SRS Step 46
    "System uptime ... excluding external GenAI API outages" — NFR 5

Two independent mechanisms, often confused:

**Retry** — the same provider, again, after a backoff.  For a failure that is
plausibly transient (timeout, 429, 5xx, an unusable body).  Bounded by
``LLM_MAX_RETRIES``; SRS Step 47 forbids an unbounded loop, and on a free tier
an unbounded loop does not merely hang, it exhausts the daily quota.

**Failover** — the next provider in the chain.  For a provider that is
finished: unconfigured, wrong key, retired model, or out of retries.

Order is Gemini → Groq → OpenRouter, worst case roughly 3 providers × (1 + 2
retries).  Every attempt returns its own ``genai_runs`` row rather than
overwriting the last, so "show us your retry handling" is answered with a
query, not a claim.

What the chain deliberately does *not* do: fabricate a result.  If every
provider fails, ``AllProvidersFailed`` is raised, the complaint is marked
``GENAI_UNAVAILABLE`` and Pipeline 2 still produces a routing and escalation
decision on its own.  A support system that stops working when a model is
unreachable would fail NFR 5, and SRS 1.8 #17 prohibits presenting a
fabricated response as a real one.
"""

from __future__ import annotations

import time
from typing import Any

from genai_pipeline.providers.base import (
    LLMProvider,
    LLMRequest,
    LLMResponse,
    ProviderError,
    ProviderUnavailable,
    RateLimited,
)
from genai_pipeline.providers.gemini import GeminiProvider
from genai_pipeline.providers.openai_compatible import (
    DeepSeekProvider,
    GroqProvider,
    OpenAICompatibleProvider,
    OpenRouterProvider,
)
from src.core import progress
from src.core.config import settings
from src.core.logging import get_logger

log = get_logger("genai_pipeline.providers")

__all__ = [
    "AllProvidersFailed",
    "AttemptRecord",
    "GeminiProvider",
    "GroqProvider",
    "LLMProvider",
    "LLMRequest",
    "LLMResponse",
    "OpenAICompatibleProvider",
    "OpenRouterProvider",
    "ProviderChain",
    "ProviderError",
    "build_chain",
    "describe_providers",
    "get_provider",
]

_REGISTRY: dict[str, type[LLMProvider]] = {
    "gemini": GeminiProvider,
    "groq": GroqProvider,
    "deepseek": DeepSeekProvider,
    "openrouter": OpenRouterProvider,
}

BACKOFF_BASE_SECONDS = 1.5
BACKOFF_CAP_SECONDS = 20.0


class AllProvidersFailed(ProviderError):
    """Every provider in the chain failed. Carries each attempt for the audit."""

    def __init__(self, attempts: list[AttemptRecord]):
        self.attempts = attempts
        tried = ", ".join(f"{a.provider}({a.error_type})" for a in attempts) or "none"
        super().__init__(f"all providers failed: {tried}")

    def as_dict(self) -> dict[str, Any]:
        return {
            "error": "AllProvidersFailed",
            "message": str(self),
            "attempts": [a.as_dict() for a in self.attempts],
        }


class AttemptRecord:
    """One call attempt — the raw material for a ``genai_runs`` row."""

    __slots__ = ("attempt", "provider", "model", "ok", "error_type", "error_message",
                 "retryable", "latency_ms")

    def __init__(
        self, *, attempt: int, provider: str, model: str, ok: bool,
        error: ProviderError | None = None, latency_ms: int = 0,
    ):
        self.attempt = attempt
        self.provider = provider
        self.model = model
        self.ok = ok
        self.error_type = type(error).__name__ if error else None
        self.error_message = str(error) if error else None
        self.retryable = bool(error.retryable) if error else False
        self.latency_ms = latency_ms

    def as_dict(self) -> dict[str, Any]:
        return {
            "attempt": self.attempt,
            "provider": self.provider,
            "model": self.model,
            "ok": self.ok,
            "error_type": self.error_type,
            "error_message": self.error_message,
            "retryable": self.retryable,
            "latency_ms": self.latency_ms,
        }


def get_provider(name: str, *, model: str | None = None) -> LLMProvider:
    key = (name or "").strip().lower()
    factory = _REGISTRY.get(key)
    if factory is None:
        raise ProviderUnavailable(f"unknown provider '{name}'", provider=key)
    return factory(model=model) if model else factory()


def build_chain(names: list[str] | None = None) -> list[LLMProvider]:
    """
    The failover order: configured primary, configured fallback, then the rest.

    Unconfigured providers are dropped here rather than at call time, so the
    chain length reported in the health endpoint is the number that could
    actually answer.
    """
    if names is None:
        names = [settings.llm_primary_provider, settings.llm_fallback_provider]
        names += [n for n in _REGISTRY if n not in names]

    chain: list[LLMProvider] = []
    seen: set[str] = set()
    for name in names:
        key = (name or "").strip().lower()
        if not key or key in seen or key not in _REGISTRY:
            continue
        seen.add(key)
        provider = _REGISTRY[key]()
        if provider.is_configured():
            chain.append(provider)
        else:
            log.debug("provider_skipped_unconfigured", provider=key)
    return chain


def describe_providers() -> list[dict[str, Any]]:
    """Status of every known provider, for ``/api/system/health``."""
    return [_REGISTRY[name]().describe() for name in _REGISTRY]


def _backoff(attempt: int, error: ProviderError) -> float:
    """
    Exponential backoff, honouring a server-supplied ``Retry-After``.

    A 429 that tells us when to come back is worth obeying: retrying earlier on
    a free tier usually extends the block rather than shortening it.
    """
    if isinstance(error, RateLimited) and error.retry_after:
        return min(float(error.retry_after), BACKOFF_CAP_SECONDS)
    return min(BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)), BACKOFF_CAP_SECONDS)


class ProviderChain:
    """
    Calls providers in order, retrying the retryable and failing over the rest.

    ``on_attempt`` fires for every attempt including the failures, which is how
    the orchestrator writes one ``genai_runs`` row per attempt without this
    class needing a database session.
    """

    def __init__(
        self,
        providers: list[LLMProvider] | None = None,
        *,
        max_retries: int | None = None,
        sleep: Any = time.sleep,
    ):
        self.providers = providers if providers is not None else build_chain()
        self.max_retries = settings.llm_max_retries if max_retries is None else max_retries
        self._sleep = sleep
        self.attempts: list[AttemptRecord] = []

    @property
    def available(self) -> bool:
        return bool(self.providers)

    def generate(
        self,
        request: LLMRequest,
        *,
        on_attempt: Any = None,
    ) -> LLMResponse:
        """Return the first successful response, or raise ``AllProvidersFailed``."""
        self.attempts = []
        if not self.providers:
            raise AllProvidersFailed([])

        attempt_number = 0
        for index, provider in enumerate(self.providers):
            has_backup = index < len(self.providers) - 1
            for retry in range(self.max_retries + 1):
                attempt_number += 1
                started = time.perf_counter()
                try:
                    response = provider.generate(request)
                except ProviderError as exc:
                    latency_ms = int((time.perf_counter() - started) * 1000)
                    record = AttemptRecord(
                        attempt=attempt_number, provider=provider.name,
                        model=provider.model, ok=False, error=exc, latency_ms=latency_ms,
                    )
                    self.attempts.append(record)
                    if on_attempt:
                        on_attempt(record)

                    log.warning(
                        "llm_attempt_failed",
                        provider=provider.name, attempt=attempt_number,
                        error=type(exc).__name__, retryable=exc.retryable,
                    )

                    if not exc.retryable or retry >= self.max_retries:
                        if has_backup:
                            progress.emit(
                                "ai",
                                detail=f"{provider.name.title()} is unavailable; switching to {self.providers[index + 1].name.title()}",
                            )
                        break  # terminal, or out of retries -> next provider
                    if isinstance(exc, RateLimited) and has_backup:
                        # A free-tier quota does not refill in a few seconds,
                        # and someone is waiting on this answer. A provider
                        # with quota left beats sleeping on one without.
                        progress.emit(
                            "ai",
                            detail=f"{provider.name.title()} hit its free limit; switching to {self.providers[index + 1].name.title()}",
                        )
                        break
                    progress.emit("ai", detail=f"{provider.name.title()} did not answer; trying again")
                    self._sleep(_backoff(retry + 1, exc))
                    continue

                record = AttemptRecord(
                    attempt=attempt_number, provider=provider.name,
                    model=response.model, ok=True, latency_ms=response.latency_ms,
                )
                self.attempts.append(record)
                if on_attempt:
                    on_attempt(record)

                if attempt_number > 1:
                    log.info(
                        "llm_recovered",
                        provider=provider.name, after_attempts=attempt_number,
                    )
                return response

        raise AllProvidersFailed(self.attempts)
