"""A third live provider — Groq, behind the `providers` extra.

Same role as `gemini_provider.py`, same mechanics: §18's "provider is a
one-file swap", selected via `LLM_PROVIDER=groq`, `groq` behind the
`providers` extra with the import inside `GroqProvider.__init__` rather than
this module's top level — see `gemini_provider.py`'s own docstring for why
(mirrors `casefile.retrieval.rank.MiniLMRanker`). `mypy src` still
type-checks this file via `[[tool.mypy.overrides]]`'s `ignore_missing_imports`
for `groq.*`.

**Schema enforcement** uses Groq's strict structured-output mode —
`response_format={"type": "json_schema", "json_schema": {"strict": True,
"schema": ...}}` — verified against console.groq.com/docs/structured-outputs
and /docs/api-reference (fetched 2026-08-31), not assumed. Strict mode
requires `additionalProperties: false` on every object in the schema, which
Pydantic's own `model_json_schema()` does not set by default; `_strict()`
below walks the schema and adds it, the same guardrail-not-guesswork
discipline `evidence.py`'s own quote-verification uses for the model's
*content* — this is verifying the model's *shape* instead.

**Untested against a live endpoint** — the same honest gap
`anthropic_provider.py` and `gemini_provider.py` both state: no key or
network reaches Groq's API here. `tests/test_groq_provider.py` verifies this
module's own logic against a fabricated SDK response. Also untested for
real, same open question as Gemini's: strict mode's `$ref` support against
this project's *nested* schemas (`HypothesiseResponse`, `ExtractionResponse`)
— Groq's docs demonstrate strict mode on a flat schema only.
"""

from __future__ import annotations

import time
from typing import Any

from casefile.llm.base import Prompt, T
from casefile.llm.pricing import cost_inr
from casefile.models import Usage

#: §19-style tiers, mapped to Groq's own model ids — verified against
#: console.groq.com/docs/models (fetched 2026-08-31): the only two Groq
#: model prices confirmed there, not guessed. Groq also serves several Llama
#: and Kimi models this project does not price — add a class here and to
#: `pricing.PRICES` together once a real, sourced number exists for one; an
#: unpriced call should fail loudly (`pricing.cost_inr` already does this),
#: not silently report ₹0.
MODEL_IDS: dict[str, str] = {
    "groq-120b": "openai/gpt-oss-120b",
    "groq-20b": "openai/gpt-oss-20b",
}

DEFAULT_MODEL_CLASS = "groq-120b"


class GroqResponseError(RuntimeError):
    """The API returned no content this provider could turn into `schema` —
    refused, truncated, or otherwise unparsed. Mirrors
    `AnthropicResponseError`/`GeminiResponseError`."""

    def __init__(self, stage: str, finish_reason: str | None) -> None:
        self.stage = stage
        self.finish_reason = finish_reason
        super().__init__(
            f"stage {stage!r}: Groq did not return a schema-conformant response "
            f"(finish_reason={finish_reason!r})"
        )


def _strict(schema: dict[str, Any]) -> dict[str, Any]:
    """Every object in the schema needs `additionalProperties: false` for
    Groq's strict mode — walks `$defs` too, since a nested Pydantic model
    (§ this module's own docstring) lands there, not inline."""
    if schema.get("type") == "object":
        schema.setdefault("additionalProperties", False)
    for value in schema.values():
        if isinstance(value, dict):
            _strict(value)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    _strict(item)
    return schema


class GroqProvider:
    """`LLMProvider` over the Groq API. One class, mirroring
    `AnthropicProvider`'s own shape exactly."""

    def __init__(self, model_class: str = DEFAULT_MODEL_CLASS, api_key: str | None = None) -> None:
        if model_class not in MODEL_IDS:
            raise KeyError(f"no model id for class {model_class!r}; known: {sorted(MODEL_IDS)}")
        self.model_class = model_class
        try:
            from groq import Groq
        except ImportError as exc:  # pragma: no cover - the extra is not installed in CI
            raise ImportError(
                "GroqProvider needs the `providers` extra: pip install -e '.[providers]'. "
                "It is deliberately not a default dependency — see casefile.llm.groq_provider"
            ) from exc
        # `api_key=None` lets the SDK read GROQ_API_KEY itself — this class
        # does not duplicate that lookup or its error message.
        self._client = Groq(api_key=api_key)

    def complete(self, prompt: Prompt, schema: type[T]) -> tuple[T, Usage]:
        started = time.perf_counter()
        response = self._client.chat.completions.create(
            model=MODEL_IDS[self.model_class],
            messages=[
                {"role": "system", "content": prompt.system},
                {"role": "user", "content": prompt.user},
            ],
            temperature=prompt.temperature,
            max_completion_tokens=prompt.max_tokens,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": schema.__name__,
                    "strict": True,
                    "schema": _strict(schema.model_json_schema()),
                },
            },
        )
        latency_ms = (time.perf_counter() - started) * 1000.0

        choice = response.choices[0]
        content = choice.message.content
        if not content:
            raise GroqResponseError(prompt.stage, choice.finish_reason)
        parsed = schema.model_validate_json(content)

        api_usage = response.usage
        input_tokens = api_usage.prompt_tokens if api_usage else 0
        output_tokens = api_usage.completion_tokens if api_usage else 0
        usage = Usage(
            stage=prompt.stage,
            model=self.model_class,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            cost_inr=cost_inr(self.model_class, input_tokens, output_tokens),
        )
        return parsed, usage
