"""AnthropicProvider — the live provider's own logic, not the wire.

Nothing in this build environment can reach the Anthropic API (no key, and
`anthropic_provider.py` says so in its own docstring), so these tests
monkeypatch `messages.parse` with a fabricated response and verify what this
module does with it: usage accounting, cache-hit detection, the request it
builds, and the error path when the API hands back nothing schema-shaped.
That is the boundary of what can be verified without live credentials — it
does not claim the wire behaviour matches.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import BaseModel

from casefile.llm.anthropic_provider import (
    MODEL_IDS,
    AnthropicProvider,
    AnthropicResponseError,
    model_class_from_env,
)
from casefile.llm.base import Prompt
from casefile.llm.pricing import PRICES, cost_inr

PROMPT = Prompt(stage="s3", system="annotate", user="ACME", max_tokens=500, temperature=0.0)


class Foo(BaseModel):
    x: int


def fake_response(
    parsed: Foo | None,
    input_tokens: int = 100,
    output_tokens: int = 20,
    cache_creation: int = 0,
    cache_read: int = 0,
    stop_reason: str = "end_turn",
) -> SimpleNamespace:
    usage = SimpleNamespace(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_creation_input_tokens=cache_creation,
        cache_read_input_tokens=cache_read,
    )
    return SimpleNamespace(parsed_output=parsed, usage=usage, stop_reason=stop_reason)


def patched(monkeypatch: pytest.MonkeyPatch, response: SimpleNamespace) -> tuple[
    AnthropicProvider, dict[str, Any]
]:
    provider = AnthropicProvider()
    captured: dict[str, Any] = {}

    def fake_parse(**kwargs: Any) -> SimpleNamespace:
        captured.update(kwargs)
        return response

    monkeypatch.setattr(provider._client.messages, "parse", fake_parse)
    return provider, captured


def test_the_parsed_value_and_usage_come_back(monkeypatch: pytest.MonkeyPatch) -> None:
    provider, _ = patched(monkeypatch, fake_response(Foo(x=5)))
    value, usage = provider.complete(PROMPT, Foo)

    assert value == Foo(x=5)
    assert usage.stage == "s3"
    assert usage.model == "sonnet"
    assert usage.input_tokens == 100
    assert usage.output_tokens == 20
    assert usage.cache_hit is False
    assert usage.cost_inr == cost_inr("sonnet", 100, 20)


def test_cache_creation_and_read_tokens_are_added_to_input_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Anthropic reports three separate counts; `pricing.cost_inr` has one flat
    rate. Missing either the creation or the read count would silently
    undercount the true prompt size the caller was billed for."""
    provider, _ = patched(
        monkeypatch,
        fake_response(Foo(x=1), input_tokens=100, cache_creation=30, cache_read=50),
    )
    _, usage = provider.complete(PROMPT, Foo)
    assert usage.input_tokens == 180


def test_a_nonzero_cache_read_marks_the_call_a_cache_hit(monkeypatch: pytest.MonkeyPatch) -> None:
    provider, _ = patched(monkeypatch, fake_response(Foo(x=1), cache_read=1))
    _, usage = provider.complete(PROMPT, Foo)
    assert usage.cache_hit is True


def test_zero_cache_read_is_not_a_cache_hit(monkeypatch: pytest.MonkeyPatch) -> None:
    provider, _ = patched(monkeypatch, fake_response(Foo(x=1), cache_read=0))
    _, usage = provider.complete(PROMPT, Foo)
    assert usage.cache_hit is False


def test_an_unparsed_response_raises_rather_than_returning_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider, _ = patched(monkeypatch, fake_response(None, stop_reason="max_tokens"))
    with pytest.raises(AnthropicResponseError, match="max_tokens") as excinfo:
        provider.complete(PROMPT, Foo)
    assert excinfo.value.stage == "s3"


def test_the_request_carries_the_prompt_the_schema_and_the_configured_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider, captured = patched(monkeypatch, fake_response(Foo(x=1)))
    provider.complete(PROMPT, Foo)

    assert captured["model"] == MODEL_IDS["sonnet"]
    assert captured["max_tokens"] == 500
    assert captured["system"] == "annotate"
    assert captured["messages"] == [{"role": "user", "content": "ACME"}]
    assert captured["output_format"] is Foo
    assert captured["extra_body"] == {"temperature": 0.0}


def test_latency_is_measured_in_milliseconds(monkeypatch: pytest.MonkeyPatch) -> None:
    provider, _ = patched(monkeypatch, fake_response(Foo(x=1)))
    ticks = iter([1.000, 1.250])  # 250 ms apart
    monkeypatch.setattr("casefile.llm.anthropic_provider.time.perf_counter", lambda: next(ticks))

    _, usage = provider.complete(PROMPT, Foo)
    assert usage.latency_ms == pytest.approx(250.0)


def test_an_unknown_model_class_is_rejected_at_construction() -> None:
    with pytest.raises(KeyError, match="haiku3"):
        AnthropicProvider(model_class="haiku3")


def test_every_anthropic_model_class_has_a_live_price() -> None:
    """A model nothing prices is a budget figure §19 cannot actually stand
    behind. `PRICES` is shared across all three providers now — Gemini's and
    Groq's own test files assert this same thing for their own MODEL_IDS."""
    assert set(MODEL_IDS) <= set(PRICES)


def test_model_class_from_env_defaults_to_sonnet(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CASEFILE_MODEL", raising=False)
    assert model_class_from_env() == "sonnet"


def test_model_class_from_env_reads_the_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CASEFILE_MODEL", "Haiku")
    assert model_class_from_env() == "haiku"
