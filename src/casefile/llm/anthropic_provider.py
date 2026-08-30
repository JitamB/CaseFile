"""The live provider — §18, D-2, ladder step 2.x.

*"AnthropicProvider lands with the first real prompt"* — `provider_from_env()`
said so since 0.5, and `engine/hypothesise.py`'s S3 call is that prompt. This
module is the one-file swap §18 promises: everything else asks
`provider_from_env()` for an `LLMProvider` and never names this class.

**Schema enforcement** uses the SDK's `messages.parse(output_format=schema)`
— §18's `output_config.format` — so a `Hypothesis` or `EvidenceItem` comes
back as an already-validated instance, never free text this module has to
parse itself. A response the API could not fit to the schema raises
`AnthropicResponseError` rather than handing a caller `None` to guess about.

**D-2:** Sonnet tier for the demo path, Haiku for bulk work if cost bites —
"the tier stays configurable" because `Telemetry` reads a price table, not a
model id. `CASEFILE_MODEL` (default `sonnet`) is that configuration
point; `AnthropicProvider(model_class=...)` overrides it per instance for a
caller (S4c's extraction) that wants a different tier than the shared default.

**Untested against a live endpoint.** Nothing in this build environment can
reach the Anthropic API — no key, no network policy that promises one — so
`tests/test_anthropic_provider.py` verifies this module's own logic (usage
accounting, cache-hit detection, the error path) against a fabricated SDK
response, not the wire behaviour. That gap is real and stated here rather
than papered over; it closes the first time someone runs this with a key and
CASEFILE_LLM_REPLAY=false to record `llm_cache/` entries for S3.

**Total input tokens, not just the fresh ones.** Anthropic reports
`input_tokens`, `cache_creation_input_tokens` and `cache_read_input_tokens`
as three separate counts; `pricing.cost_inr` has one flat rate per token
class, no cache discount. Summing all three overstates cost on a cache hit
rather than understating it — the safe direction to be wrong in a number this
project publishes. `Usage.cache_hit` records the fact of a hit; the missing
`cached_input_tokens` split is D-1's `cache_hit` decision again — a treaty
change, raised at the next sync rather than added solo.
"""

from __future__ import annotations

import os
import time

import anthropic

from casefile.llm.base import Prompt, T
from casefile.llm.pricing import cost_inr
from casefile.models import Usage

#: §19's tiers, mapped to the model ids named in this build's own environment.
#: Keys match `pricing.PRICES` exactly, minus "stub" — a live provider never
#: calls that one, and a test asserts the two sets agree.
MODEL_IDS: dict[str, str] = {
    "opus": "claude-opus-5",
    "sonnet": "claude-sonnet-5",
    "haiku": "claude-haiku-4-5-20251001",
}

DEFAULT_MODEL_CLASS = "sonnet"  # D-2: the demo path


class AnthropicResponseError(RuntimeError):
    """The API returned a message this provider could not turn into `schema`
    — refused, truncated, or otherwise unparsed. Surfacing `stop_reason` is
    the difference between a caller debugging this in a minute or an hour."""

    def __init__(self, stage: str, stop_reason: str | None) -> None:
        self.stage = stage
        self.stop_reason = stop_reason
        super().__init__(
            f"stage {stage!r}: Claude did not return a schema-conformant response "
            f"(stop_reason={stop_reason!r})"
        )


class AnthropicProvider:
    """`LLMProvider` over the real API. One class, so §18's "provider is a
    one-file swap" is this file."""

    def __init__(self, model_class: str = DEFAULT_MODEL_CLASS, api_key: str | None = None) -> None:
        if model_class not in MODEL_IDS:
            raise KeyError(f"no model id for class {model_class!r}; known: {sorted(MODEL_IDS)}")
        self.model_class = model_class
        # `api_key=None` lets the SDK read ANTHROPIC_API_KEY itself — this
        # class does not duplicate that lookup or its error message.
        self._client = anthropic.Anthropic(api_key=api_key)

    def complete(self, prompt: Prompt, schema: type[T]) -> tuple[T, Usage]:
        started = time.perf_counter()
        response = self._client.messages.parse(
            model=MODEL_IDS[self.model_class],
            max_tokens=prompt.max_tokens,
            system=prompt.system,
            messages=[{"role": "user", "content": prompt.user}],
            output_format=schema,
            # `temperature` has no named parameter on this SDK version's
            # `.parse` (checked against the installed 1.2.0, not assumed);
            # `extra_body` still sends it as a literal request field so the
            # three close-path calls' determinism intent reaches the API if
            # it is honoured, and is silently unused if not.
            extra_body={"temperature": prompt.temperature},
        )
        latency_ms = (time.perf_counter() - started) * 1000.0

        parsed = response.parsed_output
        if parsed is None:
            raise AnthropicResponseError(prompt.stage, response.stop_reason)

        api_usage = response.usage
        input_tokens = (
            api_usage.input_tokens
            + (api_usage.cache_creation_input_tokens or 0)
            + (api_usage.cache_read_input_tokens or 0)
        )
        usage = Usage(
            stage=prompt.stage,
            model=self.model_class,
            input_tokens=input_tokens,
            output_tokens=api_usage.output_tokens,
            latency_ms=latency_ms,
            cost_inr=cost_inr(self.model_class, input_tokens, api_usage.output_tokens),
            cache_hit=bool(api_usage.cache_read_input_tokens),
        )
        return parsed, usage


def model_class_from_env() -> str:
    """§19's "the tier stays configurable" — Sonnet unless told otherwise."""
    return os.environ.get("CASEFILE_MODEL", DEFAULT_MODEL_CLASS).strip().lower()
