"""
Gemini — the primary provider.

Chosen because its free tier covers both generation and embeddings on one key
(SRS deliverables require a working system without paid credit), and because
it supports native structured output: the schema is enforced by the decoding
loop rather than requested in prose.

Native schema enforcement removes one class of failure, not all of them.  The
model can still emit a *well-formed* object with an invented policy citation,
which is why :mod:`genai_pipeline.validator` and the hallucination checks run
regardless of which provider produced the text.
"""

from __future__ import annotations

import threading
import time
from functools import lru_cache
from typing import Any

from genai_pipeline.providers.base import (
    InvalidProviderResponse,
    LLMProvider,
    LLMRequest,
    LLMResponse,
    ProviderRefused,
    ProviderServerError,
    ProviderTimeout,
    ProviderUnavailable,
    RateLimited,
)
from genai_pipeline.providers.chain import run_chain
from src.core.config import settings
from src.core.logging import get_logger

log = get_logger("genai_pipeline.providers.gemini")

# Finish reasons that mean "the model stopped for its own reasons", each
# needing a different response from us.
_TRUNCATED = {"MAX_TOKENS", "LENGTH"}
_REFUSED = {"SAFETY", "RECITATION", "BLOCKLIST", "PROHIBITED_CONTENT", "SPII"}


_client_lock = threading.Lock()


@lru_cache(maxsize=1)
def _build_client() -> Any:
    try:
        from google import genai
    except ImportError as exc:  # pragma: no cover
        raise ProviderUnavailable("google-genai is not installed", provider="gemini") from exc
    from google.genai import types

    # The SDK has no deadline of its own and retries 5xx internally, which
    # together let one overloaded model hold a complaint for minutes. The
    # deadline here, and one attempt per call, leave retrying to the chain,
    # which knows to move to the next model instead.
    return genai.Client(
        api_key=settings.gemini_api_key,
        http_options=types.HttpOptions(
            timeout=settings.llm_timeout_seconds * 1000,
            retry_options=types.HttpRetryOptions(attempts=1),
        ),
    )


def _client() -> Any:
    """
    The one shared SDK client, built once under a lock.

    ``lru_cache`` alone is not enough: workers arriving together each build a
    client, one is cached, and the others are garbage-collected -- closing
    their connection under a request still in flight ("Cannot send a request,
    as the client has been closed"). The lock makes the first build the only
    one.
    """
    if not settings.gemini_api_key:
        raise ProviderUnavailable("GEMINI_API_KEY is not configured", provider="gemini")
    with _client_lock:
        return _build_client()


# Thinking-token budgets for the 2.5 family, which predates thinking levels.
_BUDGET_25 = {"minimal": 0, "low": 512, "medium": 2048, "high": -1}


def _thinking_config(model: str) -> Any | None:
    """The configured reasoning effort, in whichever form this model accepts."""
    from google.genai import types

    effort = (settings.llm_reasoning_effort or "default").lower()
    if effort == "default":
        return None
    if model.startswith("gemini-2.5"):
        budget = _BUDGET_25.get(effort)
        if budget == 0 and "pro" in model:
            budget = 128  # 2.5 Pro cannot switch thinking off entirely
        return None if budget is None else types.ThinkingConfig(thinking_budget=budget)
    if model.startswith("gemini-2.0") or model.startswith("gemini-1"):
        return None  # no thinking to configure
    level = getattr(types.ThinkingLevel, effort.upper(), None)
    return None if level is None else types.ThinkingConfig(thinking_level=level)


class GeminiProvider(LLMProvider):
    name = "gemini"
    supports_native_json_schema = True

    def __init__(self, model: str | None = None):
        # A chain, tried in order. Google retires model names ("no longer
        # available to new users") and 503s the most popular ones on the free
        # tier, and either of those turns a single pinned name into a dead
        # pipeline. Falling through to the next model keeps Pipeline 1 alive
        # without anyone editing configuration mid-evaluation.
        self._chain = [model] if model else settings.gemini_model_chain
        self._model = self._chain[0]

    @property
    def model(self) -> str:
        """The model that last answered — recorded on every run."""
        return self._model

    def is_configured(self) -> bool:
        return bool(settings.gemini_api_key)

    def _generate(self, request: LLMRequest) -> LLMResponse:
        """Try each model in the chain until one answers (see providers/chain.py)."""
        model, response = run_chain(
            self.name, self._chain, lambda m: self._generate_with(m, request), log=log
        )
        self._model = model  # what actually answered, for the run record
        return response

    def _generate_with(self, model: str, request: LLMRequest) -> LLMResponse:
        from google.genai import types

        config: dict[str, Any] = {
            "temperature": request.temperature,
            "max_output_tokens": request.max_output_tokens,
        }
        if request.system:
            config["system_instruction"] = request.system
        if request.stop:
            config["stop_sequences"] = request.stop
        if request.json_schema is not None:
            config["response_mime_type"] = "application/json"
            config["response_schema"] = request.json_schema
        thinking = _thinking_config(model)
        if thinking is not None:
            config["thinking_config"] = thinking

        started = time.perf_counter()
        try:
            response = _client().models.generate_content(
                model=model,
                contents=request.prompt,
                config=types.GenerateContentConfig(**config),
            )
        except Exception as exc:
            raise _translate(exc, model) from exc
        latency_ms = int((time.perf_counter() - started) * 1000)

        finish_reason = _finish_reason(response)
        if finish_reason in _REFUSED:
            raise ProviderRefused(
                f"Gemini declined to answer (finish_reason={finish_reason})",
                provider=self.name,
            )

        text = _extract_text(response)
        truncated = finish_reason in _TRUNCATED
        if not text and truncated:
            # Cut off before emitting anything usable. Distinct from a refusal:
            # a bigger token budget fixes this one.
            raise InvalidProviderResponse(
                "response truncated at max_output_tokens before any content",
                provider=self.name,
            )

        usage = getattr(response, "usage_metadata", None)
        return LLMResponse(
            text=text,
            provider=self.name,
            model=model,
            latency_ms=latency_ms,
            tokens_in=getattr(usage, "prompt_token_count", None),
            tokens_out=getattr(usage, "candidates_token_count", None),
            finish_reason=finish_reason,
            truncated=truncated,
        )


def _extract_text(response: Any) -> str:
    """
    Pull text out of the SDK response.

    ``response.text`` is the documented accessor but it raises on some
    multi-part candidates, so the parts are walked as a fallback rather than
    letting an SDK edge case look like a provider outage.
    """
    try:
        text = response.text
        if text:
            return str(text).strip()
    except Exception:  # noqa: BLE001 - accessor raises on some candidate shapes
        pass

    chunks: list[str] = []
    for candidate in getattr(response, "candidates", None) or []:
        content = getattr(candidate, "content", None)
        for part in getattr(content, "parts", None) or []:
            value = getattr(part, "text", None)
            if value:
                chunks.append(str(value))
    return "".join(chunks).strip()


def _finish_reason(response: Any) -> str | None:
    for candidate in getattr(response, "candidates", None) or []:
        reason = getattr(candidate, "finish_reason", None)
        if reason is not None:
            return getattr(reason, "name", None) or str(reason)

    # A prompt blocked before generation reports here instead.
    feedback = getattr(response, "prompt_feedback", None)
    blocked = getattr(feedback, "block_reason", None)
    if blocked is not None:
        return getattr(blocked, "name", None) or str(blocked)
    return None


def _translate(exc: Exception, model: str = "") -> Exception:
    """
    Map an SDK exception onto our taxonomy.

    Matched on status code first and message text second: google-genai raises
    several exception classes across versions and importing them by name makes
    failover break on an upgrade, which is the worst possible time for it.
    """
    status = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    message = str(exc)
    lowered = message.lower()

    if status == 429 or "resource_exhausted" in lowered or "rate limit" in lowered:
        return RateLimited(message, provider="gemini", retry_after=_retry_after(exc))
    if status in (500, 502, 503, 504) or "unavailable" in lowered or "internal error" in lowered:
        return ProviderServerError(message, provider="gemini", status=status)
    if "deadline" in lowered or "timeout" in lowered or "timed out" in lowered:
        return ProviderTimeout(message, provider="gemini")
    if status in (401, 403) or "api key" in lowered or "permission" in lowered:
        return ProviderUnavailable(message, provider="gemini", status=status)
    if status == 404 or "not found" in lowered:
        # A renamed or retired model. Terminal, and worth saying loudly —
        # 'gemini-2.0-flash' disappearing is exactly how this fails.
        return ProviderUnavailable(
            f"model '{model or settings.gemini_model}' unavailable: {message}",
            provider="gemini", status=404,
        )
    if "safety" in lowered or "blocked" in lowered:
        return ProviderRefused(message, provider="gemini")
    return InvalidProviderResponse(message, provider="gemini", status=status)


def _retry_after(exc: Exception) -> float | None:
    details = getattr(exc, "details", None) or getattr(exc, "response", None)
    if isinstance(details, dict):
        value = details.get("retryDelay") or details.get("retry_after")
        if value:
            try:
                return float(str(value).rstrip("s"))
            except ValueError:
                return None
    return None
