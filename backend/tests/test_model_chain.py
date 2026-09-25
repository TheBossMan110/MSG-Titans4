"""
Model chains, for every provider.

Twice during this project a provider stopped answering to a model name that
had worked the day before: Google retired ``gemini-2.5-flash`` and Groq
dropped its Llama models altogether. Each time a single pinned name turned
Pipeline 1 dark while the system quietly degraded to rules-only. These tests
pin down what the chain must survive — and, just as importantly, what it must
NOT paper over: a bad key or an exhausted quota belongs to the account, and
walking the chain would only burn more quota and blame the wrong model.
"""

from __future__ import annotations

import pytest

from genai_pipeline.providers import chain as chain_module
from genai_pipeline.providers.base import (
    LLMRequest,
    LLMResponse,
    ProviderRefused,
    ProviderServerError,
    ProviderTimeout,
    ProviderUnavailable,
    RateLimited,
)
from genai_pipeline.providers.gemini import GeminiProvider
from genai_pipeline.providers.openai_compatible import GroqProvider, OpenRouterProvider

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _cold_start():
    """The last-known-good model is module state; every test starts cold."""
    chain_module.forget()
    yield
    chain_module.forget()


def _request() -> LLMRequest:
    return LLMRequest(prompt="classify this", temperature=0.0, max_output_tokens=256)


def _answer(model: str, provider: str) -> LLMResponse:
    return LLMResponse(text='{"ok":true}', provider=provider, model=model, latency_ms=1)


PROVIDERS = [
    pytest.param(GeminiProvider, "gemini", id="gemini"),
    pytest.param(GroqProvider, "groq", id="groq"),
    pytest.param(OpenRouterProvider, "openrouter", id="openrouter"),
]


def _provider(cls, chain: list[str]):
    p = cls()
    p._chain = list(chain)
    p._model = chain[0]
    return p


# ── falling through ────────────────────────────────────────────────────────


@pytest.mark.parametrize("cls, name", PROVIDERS)
def test_a_retired_model_falls_through_to_the_next(monkeypatch, cls, name):
    tried: list[str] = []

    def fake(self, model, request):
        tried.append(model)
        if model == "retired":
            raise ProviderUnavailable("model not found", provider=name, status=404)
        return _answer(model, name)

    monkeypatch.setattr(cls, "_generate_with", fake, raising=True)
    provider = _provider(cls, ["retired", "working"])

    result = provider._generate(_request())

    assert tried == ["retired", "working"]
    assert result.model == "working"
    # The run record must name the model that actually answered.
    assert provider.model == "working"


@pytest.mark.parametrize("cls, name", PROVIDERS)
def test_an_overloaded_model_falls_through(monkeypatch, cls, name):
    tried: list[str] = []

    def fake(self, model, request):
        tried.append(model)
        if model != "quiet":
            raise ProviderServerError("high demand", provider=name, status=503)
        return _answer(model, name)

    monkeypatch.setattr(cls, "_generate_with", fake, raising=True)

    result = _provider(cls, ["busy-a", "busy-b", "quiet"])._generate(_request())

    assert tried == ["busy-a", "busy-b", "quiet"]
    assert result.model == "quiet"


def test_when_every_model_fails_the_last_error_is_raised(monkeypatch):
    def fake(self, model, request):
        raise ProviderServerError(f"{model} down", provider="groq", status=503)

    monkeypatch.setattr(GroqProvider, "_generate_with", fake, raising=True)

    with pytest.raises(ProviderServerError) as excinfo:
        _provider(GroqProvider, ["a", "b"])._generate(_request())

    assert "b down" in str(excinfo.value)


# ── refusing to fall through ───────────────────────────────────────────────


@pytest.mark.parametrize(
    "error",
    [
        ProviderRefused("blocked for safety", provider="x"),
        ProviderTimeout("took too long", provider="x"),
        ProviderUnavailable("api key invalid", provider="x", status=403),
        ProviderUnavailable("unauthenticated", provider="x", status=401),
    ],
    ids=["refused", "timeout", "forbidden", "unauthenticated"],
)
@pytest.mark.parametrize("cls, name", PROVIDERS)
def test_account_level_failures_do_not_try_other_models(monkeypatch, cls, name, error):
    tried: list[str] = []

    def fake(self, model, request):
        tried.append(model)
        raise error

    monkeypatch.setattr(cls, "_generate_with", fake, raising=True)

    with pytest.raises(type(error)):
        _provider(cls, ["first", "second", "third"])._generate(_request())

    assert tried == ["first"]


# ── remembering what worked ────────────────────────────────────────────────


@pytest.mark.parametrize("cls, name", PROVIDERS)
def test_a_rate_limited_model_hands_over_to_the_next(monkeypatch, cls, name):
    """
    Free-tier quotas are per model: the next model in the chain has a bucket of
    its own, so a 429 on one is a reason to try another, not to give up.
    """
    tried: list[str] = []

    def fake(self, model, request):
        tried.append(model)
        if model == "first":
            raise RateLimited("quota exhausted", provider="x")
        return _answer(model, name)

    monkeypatch.setattr(cls, "_generate_with", fake, raising=True)
    _provider(cls, ["first", "second", "third"])._generate(_request())
    assert tried == ["first", "second"]


@pytest.mark.parametrize("cls, name", PROVIDERS)
def test_every_model_rate_limited_surfaces_as_a_rate_limit(monkeypatch, cls, name):
    def fake(self, model, request):
        raise RateLimited("quota exhausted", provider="x")

    monkeypatch.setattr(cls, "_generate_with", fake, raising=True)
    with pytest.raises(RateLimited):
        _provider(cls, ["first", "second"])._generate(_request())


def test_the_model_that_answered_is_tried_first_next_time(monkeypatch):
    calls: list[list[str]] = []

    def fake(self, model, request):
        calls[-1].append(model)
        if model in ("busy-a", "busy-b"):
            raise ProviderServerError("high demand", provider="gemini", status=503)
        return _answer(model, "gemini")

    monkeypatch.setattr(GeminiProvider, "_generate_with", fake, raising=True)
    chain = ["busy-a", "busy-b", "quiet"]

    calls.append([])
    _provider(GeminiProvider, chain)._generate(_request())
    assert calls[0] == ["busy-a", "busy-b", "quiet"], "cold start walks the chain"

    calls.append([])
    _provider(GeminiProvider, chain)._generate(_request())
    assert calls[1] == ["quiet"], "the known-good model goes first, saving two calls"


def test_memory_is_per_provider():
    """Groq's last good model must not reorder Gemini's chain."""
    chain_module.remember("groq", "shared-name")

    assert chain_module.preferred_order("gemini", ["a", "shared-name"]) == ["a", "shared-name"]
    assert chain_module.preferred_order("groq", ["a", "shared-name"]) == ["shared-name", "a"]


def test_a_remembered_model_no_longer_configured_is_ignored():
    chain_module.remember("gemini", "retired-model")

    assert chain_module.preferred_order("gemini", ["a", "b"]) == ["a", "b"]


# ── configuration ──────────────────────────────────────────────────────────


def test_parse_chain_drops_blanks_and_never_returns_empty():
    assert chain_module.parse_chain(" a , b ,, c ", "z") == ["a", "b", "c"]
    assert chain_module.parse_chain("  ,  ", "z") == ["z"]
    assert chain_module.parse_chain(None, "z") == ["z"]


def test_settings_expose_the_chains(monkeypatch):
    from src.core.config import settings

    monkeypatch.setattr(settings, "gemini_model", "g1, g2", raising=False)
    monkeypatch.setattr(settings, "groq_model", "q1,q2 ,q3", raising=False)
    assert settings.gemini_model_chain == ["g1", "g2"]
    assert settings.groq_model_chain == ["q1", "q2", "q3"]


def test_groq_reads_its_chain_from_configuration(monkeypatch):
    from src.core.config import settings

    monkeypatch.setattr(settings, "groq_model", "first-model,second-model", raising=False)
    provider = GroqProvider()

    assert provider._chain == ["first-model", "second-model"]
    assert provider.model == "first-model"


def test_an_explicit_model_overrides_the_chain():
    assert GeminiProvider(model="pinned")._chain == ["pinned"]
    assert GroqProvider(model="pinned")._chain == ["pinned"]


def test_no_configured_groq_model_is_a_llama():
    """Groq retired every Llama model; a Llama default would be dead on arrival."""
    from src.core.config import Settings

    default = Settings.model_fields["groq_model"].default
    assert "llama" not in default.lower()
