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
    _stub_conforms: LLMProvider = StubProvider()
    _replay_conforms: LLMProvider = ReplayProvider()
    _anthropic_conforms: LLMProvider = AnthropicProvider()


_TRUE = {"1", "true", "yes", "on"}


def provider_from_env() -> LLMProvider:
    """Replay unless told otherwise.

    The default is on, not off. A missing env var on someone's laptop should
    produce a `CacheMiss` — loud, local, free — rather than a live call nobody
    intended to pay for.
    """
    if os.environ.get("CASEFILE_LLM_REPLAY", "true").strip().lower() in _TRUE:
        return ReplayProvider()

    return AnthropicProvider(model_class=model_class_from_env())
