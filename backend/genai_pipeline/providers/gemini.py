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
from src.core.config import settings
from src.core.logging import get_logger

log = get_logger("genai_pipeline.providers.gemini")

# Finish reasons that mean "the model stopped for its own reasons", each
# needing a different response from us.
_TRUNCATED = {"MAX_TOKENS", "LENGTH"}
_REFUSED = {"SAFETY", "RECITATION", "BLOCKLIST", "PROHIBITED_CONTENT", "SPII"}


@lru_cache(maxsize=1)
def _client() -> Any:
    if not settings.gemini_api_key:
        raise ProviderUnavailable("GEMINI_API_KEY is not configured", provider="gemini")
    try:
        from google import genai
    except ImportError as exc:  # pragma: no cover
        raise ProviderUnavailable("google-genai is not installed", provider="gemini") from exc
    return genai.Client(api_key=settings.gemini_api_key)


class GeminiProvider(LLMProvider):
    name = "gemini"
    supports_native_json_schema = True

    def __init__(self, model: str | None = None):
        self._model = model or settings.gemini_model

    @property
    def model(self) -> str:
        return self._model

    def is_configured(self) -> bool:
        return bool(settings.gemini_api_key)

    def _generate(self, request: LLMRequest) -> LLMResponse:
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

        started = time.perf_counter()
        try:
            response = _client().models.generate_content(
                model=self._model,
                contents=request.prompt,
                config=types.GenerateContentConfig(**config),
            )
        except Exception as exc:
            raise _translate(exc) from exc
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
            model=self._model,
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


def _translate(exc: Exception) -> Exception:
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
            f"model '{settings.gemini_model}' unavailable: {message}",
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
