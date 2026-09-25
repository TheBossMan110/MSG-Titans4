"""
Groq and OpenRouter — the fallback providers.

Both speak the OpenAI ``/chat/completions`` dialect, so they share one adapter
and differ only in base URL, key, model and headers.  Written against httpx
directly rather than the ``openai`` package: one shape of HTTP call does not
justify a dependency, and the error mapping we need is finer-grained than the
SDK's.

**Schema support is the real difference from Gemini.** Neither backend enforces
an arbitrary JSON Schema during decoding the way Gemini does.  They are asked
for ``response_format: json_object``, which guarantees syntactically valid JSON
and nothing about its fields, and the schema is additionally restated in the
prompt.  Pydantic validation downstream is therefore not belt-and-braces here —
it is the only thing standing between a fallback response and the database.

Free-tier reality, since it shapes the failover order: Groq is fast with a low
daily cap, OpenRouter's free models are slower with tighter rate limits.  Groq
is tried first.
"""

from __future__ import annotations

import json
import time
from typing import Any

import httpx

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
from genai_pipeline.providers.chain import parse_chain, run_chain
from src.core.config import settings
from src.core.logging import get_logger

log = get_logger("genai_pipeline.providers.openai_compatible")

_TRUNCATED = {"length", "max_tokens"}
_REFUSED = {"content_filter"}


class OpenAICompatibleProvider(LLMProvider):
    """Shared implementation for any OpenAI-compatible chat endpoint."""

    supports_native_json_schema = False

    def __init__(
        self,
        *,
        name: str,
        api_key: str,
        base_url: str,
        model: str,
        extra_headers: dict[str, str] | None = None,
    ):
        self.name = name
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        # A comma-separated chain, tried in order. Groq retired every Llama
        # model it served; a single pinned name is how that becomes a dead
        # fallback. See providers/chain.py for what may fall through.
        self._chain = parse_chain(model, model or "")
        self._model = self._chain[0]
        self._extra_headers = extra_headers or {}

    @property
    def model(self) -> str:
        """The model that last answered — recorded on every run."""
        return self._model

    def is_configured(self) -> bool:
        return bool(self._api_key and self._base_url and self._model)

    def _generate(self, request: LLMRequest) -> LLMResponse:
        model, response = run_chain(
            self.name, self._chain, lambda m: self._generate_with(m, request), log=log
        )
        self._model = model
        return response

    def _generate_with(self, model: str, request: LLMRequest) -> LLMResponse:
        messages: list[dict[str, str]] = []
        if request.system:
            messages.append({"role": "system", "content": request.system})
        messages.append({"role": "user", "content": self._user_content(request)})

        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": request.temperature,
            "max_tokens": request.max_output_tokens,
        }
        if request.stop:
            payload["stop"] = request.stop
        if request.wants_json:
            # Valid JSON is guaranteed; the right *fields* are not. The schema
            # is also restated in the user content above.
            payload["response_format"] = {"type": "json_object"}

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            **self._extra_headers,
        }

        started = time.perf_counter()
        try:
            with httpx.Client(timeout=settings.llm_timeout_seconds) as client:
                response = client.post(
                    f"{self._base_url}/chat/completions", json=payload, headers=headers
                )
        except httpx.TimeoutException as exc:
            raise ProviderTimeout(str(exc), provider=self.name) from exc
        except httpx.HTTPError as exc:
            raise ProviderServerError(str(exc), provider=self.name) from exc
        latency_ms = int((time.perf_counter() - started) * 1000)

        self._raise_for_status(response)

        try:
            body = response.json()
        except ValueError as exc:
            raise InvalidProviderResponse(
                "response body was not JSON", provider=self.name
            ) from exc

        # OpenRouter reports upstream failures as a 200 with an error object.
        error = body.get("error")
        if error:
            message = error.get("message", str(error)) if isinstance(error, dict) else str(error)
            code = error.get("code") if isinstance(error, dict) else None
            raise _from_status(int(code) if str(code).isdigit() else 502, message, self.name)

        choices = body.get("choices") or []
        if not choices:
            raise InvalidProviderResponse("no choices returned", provider=self.name)

        choice = choices[0]
        finish_reason = choice.get("finish_reason") or choice.get("native_finish_reason")
        if finish_reason in _REFUSED:
            raise ProviderRefused(
                f"{self.name} content filter rejected the request", provider=self.name
            )

        text = (choice.get("message") or {}).get("content") or ""
        usage = body.get("usage") or {}

        return LLMResponse(
            text=str(text).strip(),
            provider=self.name,
            model=body.get("model") or model,
            latency_ms=latency_ms,
            tokens_in=usage.get("prompt_tokens"),
            tokens_out=usage.get("completion_tokens"),
            finish_reason=finish_reason,
            truncated=finish_reason in _TRUNCATED,
        )

    def _user_content(self, request: LLMRequest) -> str:
        """
        Append the schema for providers that cannot enforce it natively.

        Restating it costs a few hundred tokens and measurably raises the rate
        of first-attempt valid output — cheaper than the repair round trip it
        avoids.
        """
        if not request.wants_json:
            return request.prompt
        schema = json.dumps(request.json_schema, indent=None, separators=(",", ":"))
        return (
            f"{request.prompt}\n\n"
            "Return ONLY a JSON object conforming to this JSON Schema. "
            "No markdown fence, no commentary.\n"
            f"{schema}"
        )

    def _raise_for_status(self, response: httpx.Response) -> None:
        if response.status_code < 400:
            return
        detail = response.text[:500]
        retry_after = response.headers.get("retry-after")
        if response.status_code == 429:
            raise RateLimited(
                detail, provider=self.name,
                retry_after=float(retry_after) if retry_after and retry_after.isdigit() else None,
            )
        raise _from_status(response.status_code, detail, self.name)


def _from_status(status: int, message: str, provider: str) -> Exception:
    if status == 429:
        return RateLimited(message, provider=provider)
    if status in (401, 403):
        return ProviderUnavailable(message, provider=provider, status=status)
    if status == 404:
        return ProviderUnavailable(
            f"model or endpoint not found: {message}", provider=provider, status=404
        )
    if status == 408 or status == 504:
        return ProviderTimeout(message, provider=provider, status=status)
    if status >= 500:
        return ProviderServerError(message, provider=provider, status=status)
    return InvalidProviderResponse(message, provider=provider, status=status)


class GroqProvider(OpenAICompatibleProvider):
    def __init__(self, model: str | None = None):
        super().__init__(
            name="groq",
            api_key=settings.groq_api_key,
            base_url=settings.groq_base_url,
            model=model or settings.groq_model,
        )


class OpenRouterProvider(OpenAICompatibleProvider):
    def __init__(self, model: str | None = None):
        super().__init__(
            name="openrouter",
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
            model=model or settings.openrouter_model,
            # OpenRouter attributes requests to an app; these are public
            # identifiers, not credentials.
            extra_headers={
                "HTTP-Referer": "https://github.com/supportnova",
                "X-Title": settings.app_name,
            },
        )
