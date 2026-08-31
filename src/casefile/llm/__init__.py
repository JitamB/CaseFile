"""The LLM layer — ladder step 0.5.

Everything downstream asks for a provider here and never constructs one itself,
so "is this run allowed to reach the network?" is answered in exactly one place.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from casefile.llm.anthropic_provider import AnthropicProvider, model_class_from_env
from casefile.llm.base import CacheMiss, LLMProvider, Prompt
from casefile.llm.pricing import PRICES, USD_INR, cost_inr
from casefile.llm.replay import DEFAULT_CACHE_DIR, CacheEntry, ReplayProvider, cache_key
from casefile.llm.stub import StubProvider

__all__ = [
    "DEFAULT_CACHE_DIR",
    "PRICES",
    "USD_INR",
    "AnthropicProvider",
    "CacheEntry",
    "CacheMiss",
    "LLMProvider",
    "Prompt",
    "ReplayProvider",
    "StubProvider",
    "cache_key",
    "cost_inr",
    "model_class_from_env",
    "provider_from_env",
]

if TYPE_CHECKING:
    # §18 promises the provider is a one-file swap. These never run; they exist
    # so mypy fails here, on the line that made the promise, if an implementation
    # drifts from the protocol — rather than at some call site weeks later.
    # Gemini's and Groq's own packages sit behind the `providers` extra
    # (pyproject.toml), which this TYPE_CHECKING-only import does not require
    # installed — `[[tool.mypy.overrides]]` treats their absence the same way
    # it already treats sentence_transformers's for the `embed` extra.
    from casefile.llm.gemini_provider import GeminiProvider
    from casefile.llm.groq_provider import GroqProvider

    _stub_conforms: LLMProvider = StubProvider()
    _replay_conforms: LLMProvider = ReplayProvider()
    _anthropic_conforms: LLMProvider = AnthropicProvider()
    _gemini_conforms: LLMProvider = GeminiProvider()
    _groq_conforms: LLMProvider = GroqProvider()


_TRUE = {"1", "true", "yes", "on"}

#: LLM_PROVIDER's known values — the vendor names §17's own "provider is a
#: one-file swap" promise now spans. "anthropic" is the default: unset, this
#: behaves exactly as it did before LLM_PROVIDER existed.
_PROVIDERS = {"anthropic", "google", "groq"}


def provider_from_env() -> LLMProvider:
    """Replay unless told otherwise.

    The default is on, not off. A missing env var on someone's laptop should
    produce a `CacheMiss` — loud, local, free — rather than a live call nobody
    intended to pay for.

    Past that gate, `LLM_PROVIDER` picks the vendor (default: anthropic, so
    every call site written before this existed keeps its old behaviour
    unchanged) and `LLM_MODEL` — new, generic, and provider-agnostic — is an
    optional override for which class within that vendor to call, read by
    each provider's own constructor. Anthropic's own `CASEFILE_MODEL` still
    works standalone (`model_class_from_env()`, unchanged) for anyone using
    only that one provider; `LLM_MODEL` takes precedence when both are set,
    since it is the newer, general knob. Gemini's and Groq's own provider
    classes are imported here, lazily, inside their branch only — never at
    this module's top level — so a default install never needs their
    packages (the `providers` extra) just to import `casefile.llm`.
    """
    if os.environ.get("CASEFILE_LLM_REPLAY", "true").strip().lower() in _TRUE:
        return ReplayProvider()

    provider = os.environ.get("LLM_PROVIDER", "anthropic").strip().lower() or "anthropic"
    if provider not in _PROVIDERS:
        raise KeyError(f"unknown LLM_PROVIDER {provider!r}; known: {sorted(_PROVIDERS)}")

    model_class = os.environ.get("LLM_MODEL", "").strip().lower() or None

    if provider == "anthropic":
        return AnthropicProvider(model_class=model_class or model_class_from_env())

    if provider == "google":
        from casefile.llm.gemini_provider import DEFAULT_MODEL_CLASS, GeminiProvider

        return GeminiProvider(model_class=model_class or DEFAULT_MODEL_CLASS)

    from casefile.llm.groq_provider import DEFAULT_MODEL_CLASS, GroqProvider

    return GroqProvider(model_class=model_class or DEFAULT_MODEL_CLASS)
