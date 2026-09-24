"""
The provider interface (FR xii; SRS Step 46).

    "The system must handle API failures gracefully: timeouts, rate limits,
     invalid responses, and service outages. Fallback behaviour must be
     defined."                                            — SRS Step 46

One interface, several implementations, and a factory that fails over between
them.  The rest of the pipeline never imports a provider directly, so swapping
Gemini for Groq is a configuration change.

**Error taxonomy matters more than it looks.** Failures are sorted into
retryable (timeout, rate limit, 5xx, malformed body) and terminal (bad key,
model not found, content refused).  Retrying a terminal failure burns the free
tier's quota to arrive at the same answer; not retrying a retryable one throws
away a request that would have succeeded on the second attempt.

Providers here do exactly one thing: send a prompt, return text and usage.
They do not parse JSON, validate schemas, retry, or touch the database — that
belongs to :mod:`genai_pipeline.validator` and the orchestrator, and keeping it
out of here is what makes a provider ten lines to add.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from src.core.config import settings
from src.core.logging import get_logger

log = get_logger("genai_pipeline.providers")

# Read from configuration so it can be raised for a verbose provider
# without a redeploy. See settings.llm_max_output_tokens.
DEFAULT_MAX_OUTPUT_TOKENS = settings.llm_max_output_tokens


# ══════════════════════════════════════════════════════════════
# errors
# ══════════════════════════════════════════════════════════════
class ProviderError(Exception):
    """Base class. ``retryable`` decides whether another attempt is worth it."""

    retryable = False

    def __init__(self, message: str, *, provider: str = "", status: int | None = None):
        super().__init__(message)
        self.provider = provider
        self.status = status

    def as_dict(self) -> dict[str, Any]:
        return {
            "error": type(self).__name__,
            "provider": self.provider,
            "status": self.status,
            "message": str(self),
            "retryable": self.retryable,
        }


class ProviderUnavailable(ProviderError):
    """Not configured, or the SDK is missing. Never retried — nothing changes."""


class ProviderTimeout(ProviderError):
    retryable = True


class RateLimited(ProviderError):
    """429. Retryable, but with a longer backoff than a plain timeout."""

    retryable = True

    def __init__(self, message: str, *, provider: str = "", retry_after: float | None = None):
        super().__init__(message, provider=provider, status=429)
        self.retry_after = retry_after


class ProviderServerError(ProviderError):
    """5xx. The provider's problem, and usually transient."""

    retryable = True


class ProviderRefused(ProviderError):
    """
    The provider declined to answer (safety filter, blocked content).

    Terminal: sending the same complaint again produces the same refusal.  It
    is recorded rather than hidden, because a safety complaint being refused by
    a safety filter is exactly the case a reviewer needs to see.
    """


class InvalidProviderResponse(ProviderError):
    """
    A 200 with a body we cannot use — empty text, truncated JSON, wrong shape.

    Retryable: at a non-zero temperature the next sample often is usable, and
    this is the most common real failure with structured output.
    """

    retryable = True


# ══════════════════════════════════════════════════════════════
# value objects
# ══════════════════════════════════════════════════════════════
@dataclass(slots=True)
class LLMRequest:
    """What to send. Provider-agnostic; each adapter maps it to its own API."""

    prompt: str
    system: str | None = None
    temperature: float = 0.1
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS
    json_schema: dict[str, Any] | None = None
    stop: list[str] = field(default_factory=list)

    @property
    def wants_json(self) -> bool:
        return self.json_schema is not None


@dataclass(slots=True)
class LLMResponse:
    """
    What came back, plus everything ``genai_runs`` needs to record the call.

    ``truncated`` is separate from an error on purpose: a response cut off at
    the token limit arrives as a successful 200 with unparseable JSON, and
    without this flag that looks identical to a model that cannot follow a
    schema.  One is fixed by raising a limit, the other by fixing a prompt.
    """

    text: str
    provider: str
    model: str
    latency_ms: int
    tokens_in: int | None = None
    tokens_out: int | None = None
    finish_reason: str | None = None
    truncated: bool = False
    raw: dict[str, Any] = field(default_factory=dict)

    def usage(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "latency_ms": self.latency_ms,
            "finish_reason": self.finish_reason,
            "truncated": self.truncated,
        }


# ══════════════════════════════════════════════════════════════
# the interface
# ══════════════════════════════════════════════════════════════
class LLMProvider(ABC):
    """A text-in, text-out generation provider."""

    name: str = "abstract"
    supports_native_json_schema: bool = False

    @property
    @abstractmethod
    def model(self) -> str:
        """The model identifier recorded against every run."""

    @abstractmethod
    def is_configured(self) -> bool:
        """Whether a call could be made right now. Never raises."""

    @abstractmethod
    def _generate(self, request: LLMRequest) -> LLMResponse:
        """Perform the call. Raise a :class:`ProviderError` subclass on failure."""

    def generate(self, request: LLMRequest) -> LLMResponse:
        """
        Call the provider, timing it and normalising failures.

        Every exception leaves here as a ``ProviderError``: an adapter raising
        something the factory does not recognise would bypass failover and
        surface as a 500 instead of a fallback.
        """
        if not self.is_configured():
            raise ProviderUnavailable(
                f"{self.name} is not configured", provider=self.name
            )

        started = time.perf_counter()
        try:
            response = self._generate(request)
        except ProviderError:
            raise
        except Exception as exc:  # unmapped SDK failure
            raise InvalidProviderResponse(
                f"{type(exc).__name__}: {exc}", provider=self.name
            ) from exc

        if not response.latency_ms:
            response.latency_ms = int((time.perf_counter() - started) * 1000)

        if not response.text.strip():
            raise InvalidProviderResponse(
                "provider returned an empty body", provider=self.name
            )

        log.debug(
            "llm_call",
            provider=self.name, model=response.model,
            latency_ms=response.latency_ms,
            tokens_in=response.tokens_in, tokens_out=response.tokens_out,
            truncated=response.truncated,
        )
        return response

    def describe(self) -> dict[str, Any]:
        """For ``/api/system/providers`` — status without exposing a key."""
        return {
            "name": self.name,
            "model": self.model,
            "configured": self.is_configured(),
            "native_json_schema": self.supports_native_json_schema,
        }
