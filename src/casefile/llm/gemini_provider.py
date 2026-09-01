"""A second live provider — Google Gemini, behind the `providers` extra.

*"Provider is a one-file swap"* (§18) — this file is that swap for Gemini,
the same way `anthropic_provider.py` is it for Claude. Selected via
`LLM_PROVIDER=google` (see `provider_from_env()` in `__init__.py`).
`google-genai` is behind the `providers` extra, not a default dependency —
the same reasoning `casefile.retrieval.rank.MiniLMRanker` already gives for
`sentence_transformers` behind `embed`, and the same mechanics: the import
lives inside `GeminiProvider.__init__`, not this module's top level, so
`import casefile.llm.gemini_provider` (and `mypy src`, via
`[[tool.mypy.overrides]]`'s `ignore_missing_imports` for `google.genai.*`)
both work with the package absent — only *constructing* the class needs it,
with a clear `ImportError` naming the extra when it is missing.

**Schema enforcement** uses `response_mime_type="application/json"` +
`response_json_schema=schema.model_json_schema()` (the current,
non-deprecated `google-genai` SDK shape — verified against
`googleapis/python-genai`'s own README, not assumed) and parses the
returned text back into `schema` with `model_validate_json`, the same
"schema comes back validated, never free text to parse downstream" contract
`LLMProvider.complete` promises. A response with no text raises
`GeminiResponseError` rather than handing a caller `None` to guess about,
mirroring `AnthropicResponseError`.

**Verified live, same session this shipped.** Against a real key:
`gemini-3.5-flash` correctly round-trips `HypothesiseResponse` — the nested
schema (`Hypothesis` nesting `Signature`) this project's own S3 call actually
sends — with zero schema transformation, unlike Groq (see
`groq_provider.py`'s own docstring for the real bug that needed). Two of the
three original model ids were wrong, caught the same way: `gemini-2.5-pro`
and `gemini-2.5-flash-lite` both 404 — Google's own error names the
replacement (`gemini-3.1-pro-preview`, `gemini-3.5-flash-lite`), confirmed
live in turn. `gemini-3.7-flash` (the "flash" default) returned repeated
503s under real load during this same session — a real, current model
(503, not 404), and §DECISIONS.md logs the live evidence rather than
guessing whether that was a one-off. `tests/test_gemini_provider.py` still
only covers what can run without a key (data invariants, the "no extra
installed" guard) — it does not replay this session's live calls.
"""

from __future__ import annotations

import time

from casefile.llm.base import Prompt, T
from casefile.llm.pricing import cost_inr
from casefile.models import Usage

#: §19-style tiers, mapped to Gemini's own model ids. "flash" and "lite" are
#: confirmed live and working this session; "pro" is confirmed live and
#: *reachable* (a 429 quota error, not 404 — this key is simply on the free
#: tier, which has zero quota for this model; a paid key would not hit this).
#: "flash" note: 3.7 Flash is discount-priced through 2026-12-31 and doubles
#: to $1.50/$7.50 on 2027-01-01 — `pricing.PRICES`'s entry is today's rate,
#: update both together when that date arrives.
MODEL_IDS: dict[str, str] = {
    "gemini-pro": "gemini-3.1-pro-preview",
    "gemini-flash": "gemini-3.7-flash",
    "gemini-lite": "gemini-3.5-flash-lite",
}

DEFAULT_MODEL_CLASS = "gemini-flash"


class GeminiResponseError(RuntimeError):
    """The API returned no text this provider could turn into `schema` —
    blocked, empty, or otherwise unparsed. Surfacing `finish_reason` is the
    difference between a caller debugging this in a minute or an hour."""

    def __init__(self, stage: str, finish_reason: object) -> None:
        self.stage = stage
        self.finish_reason = finish_reason
        super().__init__(
            f"stage {stage!r}: Gemini did not return a schema-conformant response "
            f"(finish_reason={finish_reason!r})"
        )


class GeminiProvider:
    """`LLMProvider` over the Gemini API. One class, mirroring
    `AnthropicProvider`'s own shape exactly."""

    def __init__(self, model_class: str = DEFAULT_MODEL_CLASS, api_key: str | None = None) -> None:
        if model_class not in MODEL_IDS:
            raise KeyError(f"no model id for class {model_class!r}; known: {sorted(MODEL_IDS)}")
        self.model_class = model_class
        try:
            from google import genai
        except ImportError as exc:  # pragma: no cover - the extra is not installed in CI
            raise ImportError(
                "GeminiProvider needs the `providers` extra: pip install -e '.[providers]'. "
                "It is deliberately not a default dependency — see casefile.llm.gemini_provider"
            ) from exc
        # `api_key=None` lets the SDK read GEMINI_API_KEY / GOOGLE_API_KEY
        # itself — this class does not duplicate that lookup or its error.
        self._client = genai.Client(api_key=api_key)

    def complete(self, prompt: Prompt, schema: type[T]) -> tuple[T, Usage]:
        from google.genai import types

        started = time.perf_counter()
        response = self._client.models.generate_content(
            model=MODEL_IDS[self.model_class],
            contents=prompt.user,
            config=types.GenerateContentConfig(
                system_instruction=prompt.system,
                response_mime_type="application/json",
                response_json_schema=schema.model_json_schema(),
                temperature=prompt.temperature,
                max_output_tokens=prompt.max_tokens,
            ),
        )
        latency_ms = (time.perf_counter() - started) * 1000.0

        text = response.text
        if not text:
            finish_reason = None
            if response.candidates:
                finish_reason = response.candidates[0].finish_reason
            raise GeminiResponseError(prompt.stage, finish_reason)
        parsed = schema.model_validate_json(text)

        api_usage = response.usage_metadata
        input_tokens = (api_usage.prompt_token_count or 0) if api_usage else 0
        output_tokens = (api_usage.candidates_token_count or 0) if api_usage else 0
        usage = Usage(
            stage=prompt.stage,
            model=self.model_class,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            cost_inr=cost_inr(self.model_class, input_tokens, output_tokens),
        )
        return parsed, usage
