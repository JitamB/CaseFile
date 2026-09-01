"""GroqProvider — behind the `providers` extra, not installed in CI.

Same reasoning as `test_gemini_provider.py`: verifies the data and the
guard, not `complete()`'s own wire-adjacent logic, because the package this
provider needs to construct a real client genuinely is not installed here.

`_strict()`'s own tests are the exception — pure schema-dict logic, no SDK
needed — and `test_strict_lists_every_property_in_required_including_a_
nested_one` is a regression test for a real bug: the first version of
`_strict()` set `additionalProperties` only, and a live call against
`HypothesiseResponse` (which nests `Signature`, four nullable fields) was
rejected by Groq's own strict-mode validator with `400 ... required:
missing properties: timing, locality, dose, control` — caught the same
session this shipped, not assumed correct from reading the docs.
"""

from __future__ import annotations

import pytest

from casefile.llm.groq_provider import DEFAULT_MODEL_CLASS, MODEL_IDS, GroqProvider, _strict


def test_every_groq_model_class_has_a_live_price() -> None:
    from casefile.llm.pricing import PRICES

    assert set(MODEL_IDS) <= set(PRICES)


def test_the_default_model_class_is_a_real_one() -> None:
    assert DEFAULT_MODEL_CLASS in MODEL_IDS


def test_an_unknown_model_class_is_rejected_before_the_sdk_is_ever_touched() -> None:
    with pytest.raises(KeyError, match="groq-1b"):
        GroqProvider(model_class="groq-1b")


def test_it_refuses_to_load_itself_by_accident_without_the_extra() -> None:
    with pytest.raises(ImportError, match="providers"):
        GroqProvider()


# ── _strict — schema shape, no SDK involved ──────────────────────────────────


def test_strict_adds_additional_properties_false_to_a_flat_object() -> None:
    schema = {"type": "object", "properties": {"x": {"type": "string"}}}
    assert _strict(schema)["additionalProperties"] is False


def test_strict_lists_every_property_in_required_including_a_nested_one() -> None:
    """Regression test for a real bug (module docstring): a nullable field
    with a default — every field of `Signature`, in the real schema — is
    left out of Pydantic's own `required` list, and strict mode has no
    "optional but present" concept to fall back on."""
    schema = {
        "type": "object",
        "properties": {"x": {"anyOf": [{"type": "string"}, {"type": "null"}], "default": None}},
    }
    assert _strict(schema)["required"] == ["x"]


def test_strict_reaches_into_defs_for_a_nested_pydantic_model() -> None:
    """`HypothesiseResponse`/`ExtractionResponse` nest a nested `BaseModel`
    into `$defs`, not inline — the walk has to follow dict values generally,
    not just a fixed `properties`/`items` path, to reach it."""
    schema = {
        "type": "object",
        "properties": {"items": {"type": "array", "items": {"$ref": "#/$defs/Item"}}},
        "$defs": {"Item": {"type": "object", "properties": {"y": {"type": "integer"}}}},
    }
    result = _strict(schema)
    assert result["additionalProperties"] is False
    assert result["required"] == ["items"]
    assert result["$defs"]["Item"]["additionalProperties"] is False
    assert result["$defs"]["Item"]["required"] == ["y"]


def test_strict_does_not_touch_a_non_object_schema() -> None:
    schema = {"type": "string"}
    assert "additionalProperties" not in _strict(schema)
    assert "required" not in _strict(schema)
