"""GeminiProvider — behind the `providers` extra, not installed in CI.

The extra is genuinely absent here, the same as `sentence_transformers` for
`MiniLMRanker` (`test_retrieval.py`'s own
`test_the_minilm_backend_exists_and_refuses_to_load_itself_by_accident`) —
so this file can verify the data (every priced model class has a live id)
and the guard (constructing it without the package raises a clear
`ImportError`), but not `complete()`'s own wire-adjacent logic the way
`test_anthropic_provider.py` does for the one provider that *is* a default
dependency. That gap is real, not hidden — see `gemini_provider.py`'s own
docstring for what is and is not verified here.
"""

from __future__ import annotations

import pytest

from casefile.llm.gemini_provider import DEFAULT_MODEL_CLASS, MODEL_IDS, GeminiProvider
from casefile.llm.pricing import PRICES


def test_every_gemini_model_class_has_a_live_price() -> None:
    """`PRICES` is shared across all three providers (see `pricing.py`'s own
    docstring) — Gemini's own classes must all be priced."""
    assert set(MODEL_IDS) <= set(PRICES)


def test_the_default_model_class_is_a_real_one() -> None:
    assert DEFAULT_MODEL_CLASS in MODEL_IDS


def test_an_unknown_model_class_is_rejected_before_the_sdk_is_ever_touched() -> None:
    """The `providers` extra is not installed here — if construction reached
    the SDK import before validating `model_class`, this test would raise
    `ImportError` instead of `KeyError` and prove the ordering wrong."""
    with pytest.raises(KeyError, match="gemini-ultra"):
        GeminiProvider(model_class="gemini-ultra")


def test_it_refuses_to_load_itself_by_accident_without_the_extra() -> None:
    """Mirrors `test_retrieval.py`'s own MiniLM guard test exactly — same
    reasoning: never silently degrade, and never silently work only on
    whichever machine happens to have the package."""
    with pytest.raises(ImportError, match="providers"):
        GeminiProvider()
