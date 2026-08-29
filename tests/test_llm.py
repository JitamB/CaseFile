"""Ladder step 0.5 — the LLM layer.

The step's two verify commands from §44, made into assertions:

    "Stub round-trips a schema"
    "replay returns a recorded response with the network off"

Everything else here defends one of the two claims that rest on this layer —
§43's *CI never reaches the network*, and §19's published budget.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import BaseModel, create_model

from casefile.llm import (
    DEFAULT_CACHE_DIR,
    CacheMiss,
    Prompt,
    ReplayProvider,
    StubProvider,
    cache_key,
    cost_inr,
    provider_from_env,
)
from casefile.models import EvidenceItem, Hypothesis, Usage

PROMPT = Prompt(stage="s3", system="You annotate an enumerated hypothesis set.", user="ACME")


# ── The stub round-trips a schema — the ladder's first verify ─────────────────


def test_the_stub_round_trips_a_nested_schema() -> None:
    """`Hypothesis` carries a nested `Signature`, so this exercises recursion."""
    value, usage = StubProvider().complete(PROMPT, Hypothesis)

    assert isinstance(value, Hypothesis)
    assert value.expected_signature.timing is None  # optional fields keep their defaults
    assert usage.model == "stub"
    assert usage.stage == "s3"


def test_the_stub_round_trips_literals_constraints_and_datetimes() -> None:
    """`EvidenceItem` is the harder shape: two `Literal`s, a `ge/le` float, a
    nested frozen model with a `datetime`, and a model validator that rejects an
    incoherent combination."""
    value, _ = StubProvider().complete(PROMPT, EvidenceItem)

    assert value.kind == "fact"  # first member of the Literal
    assert value.outcome == "found"
    assert value.strength == 0.0  # satisfies ge=0.0
    assert value.source.timestamp.year == 2026
    assert value.denominator is None


def test_a_stub_call_costs_nothing() -> None:
    """A stub-driven run must report ₹0, not a number nobody was charged."""
    _, usage = StubProvider().complete(PROMPT, Hypothesis)
    assert (usage.input_tokens, usage.output_tokens, usage.cost_inr) == (0, 0, 0.0)


def test_overrides_win_over_the_synthesised_payload() -> None:
    stub = StubProvider({"driver_id": "integration_delay", "priority": 1})
    value, _ = stub.complete(PROMPT, Hypothesis)

    assert value.driver_id == "integration_delay"
    assert value.priority == 1


def test_an_unsupported_annotation_raises_rather_than_guesses() -> None:
    class Unsupported(BaseModel):
        blob: bytes

    with pytest.raises(TypeError, match="Unsupported.blob"):
        StubProvider().complete(PROMPT, Unsupported)


# ── Replay returns a recorded response — the ladder's second verify ───────────


class _Recorder:
    """Stands in for the live provider that arrives at 1.5. Returns a
    distinctive `Usage` so that "replay returns the *recorded* figures" is
    something a test can actually see."""

    def __init__(self) -> None:
        self.calls = 0

    def complete(self, prompt: Prompt, schema: type[BaseModel]) -> tuple[BaseModel, Usage]:
        self.calls += 1
        return schema.model_validate({"driver_id": "integration_delay", "rationale": "r",
                                      "priority": 1, "expected_signature": {}}), Usage(
            stage=prompt.stage,
            model="sonnet",
            input_tokens=14_500,
            output_tokens=3_700,
            latency_ms=2_500.0,
            cost_inr=cost_inr("sonnet", 14_500, 3_700),
            cache_hit=True,
        )


def test_record_then_replay_with_no_provider_to_fall_back_on(tmp_path: Path) -> None:
    recorder = _Recorder()
    recorded, recorded_usage = ReplayProvider(tmp_path, inner=recorder).complete(
        PROMPT, Hypothesis
    )
    assert recorder.calls == 1
    assert list(tmp_path.glob("s3-*.json")), "the entry is named for its stage"

    # inner=None is what CASEFILE_LLM_REPLAY=true builds, and what CI runs.
    replayed, replayed_usage = ReplayProvider(tmp_path).complete(PROMPT, Hypothesis)

    assert replayed == recorded
    assert recorder.calls == 1, "a hit must not reach the inner provider"
    assert replayed_usage == recorded_usage


def test_a_replayed_call_reports_the_original_calls_figures(tmp_path: Path) -> None:
    """Replayed telemetry is the real call's telemetry — otherwise the recorded
    demo would publish numbers that were never measured."""
    ReplayProvider(tmp_path, inner=_Recorder()).complete(PROMPT, Hypothesis)
    _, usage = ReplayProvider(tmp_path).complete(PROMPT, Hypothesis)

    assert usage.model == "sonnet"
    assert (usage.input_tokens, usage.output_tokens) == (14_500, 3_700)
    assert usage.latency_ms == 2_500.0
    # cache_hit is the provider's prompt cache (§19), not this cache. Replay
    # carries whatever the real call reported and never sets it itself.
    assert usage.cache_hit is True


def test_a_miss_with_no_inner_provider_raises_instead_of_reaching_out(tmp_path: Path) -> None:
    with pytest.raises(CacheMiss) as excinfo:
        ReplayProvider(tmp_path).complete(PROMPT, Hypothesis)

    assert "no recorded response" in str(excinfo.value)
    assert not list(tmp_path.iterdir()), "a miss writes nothing"


# ── The key ───────────────────────────────────────────────────────────────────


def test_the_key_is_deterministic() -> None:
    assert cache_key(PROMPT, Hypothesis) == cache_key(PROMPT, Hypothesis)


@pytest.mark.parametrize(
    "field,value",
    [("system", "different"), ("user", "NORTHWIND"), ("temperature", 0.7), ("stage", "s8b")],
)
def test_changing_the_prompt_changes_the_key(field: str, value: object) -> None:
    other = PROMPT.model_copy(update={field: value})
    assert cache_key(other, Hypothesis) != cache_key(PROMPT, Hypothesis)


def test_a_different_schema_changes_the_key() -> None:
    assert cache_key(PROMPT, Hypothesis) != cache_key(PROMPT, EvidenceItem)


def test_the_key_follows_the_shape_and_not_just_the_name() -> None:
    """The realistic drift is a field added to `Hypothesis` in place — same
    class, same name, wider shape. Keying on the name alone would replay a
    response that is missing the new field, so the key hashes the JSON schema.
    """
    widened = create_model("Hypothesis", __base__=Hypothesis, confidence_note=(str, ...))

    assert widened.__name__ == Hypothesis.__name__
    assert cache_key(PROMPT, widened) != cache_key(PROMPT, Hypothesis)


def test_a_schema_change_forces_a_re_record(tmp_path: Path) -> None:
    ReplayProvider(tmp_path, inner=_Recorder()).complete(PROMPT, Hypothesis)
    widened = create_model("Hypothesis", __base__=Hypothesis, confidence_note=(str, ...))

    with pytest.raises(CacheMiss):
        ReplayProvider(tmp_path).complete(PROMPT, widened)


# ── The budget ────────────────────────────────────────────────────────────────


def test_the_price_table_reproduces_the_published_per_case_figure() -> None:
    """§19 publishes ≈₹8 per case at the Sonnet tier for 14.5k in / 3.7k out.
    The claim is in the proposal, so it is a test."""
    assert cost_inr("sonnet", 14_500, 3_700) == pytest.approx(8.0, abs=1.0)


def test_every_tier_lands_inside_the_ten_rupee_budget() -> None:
    """§35 caps a case at ₹10; §19's own table says Opus does not fit."""
    assert cost_inr("haiku", 14_500, 3_700) < cost_inr("sonnet", 14_500, 3_700) < 10.0
    assert cost_inr("opus", 14_500, 3_700) > 10.0


def test_an_unpriced_model_raises_rather_than_costing_nothing() -> None:
    with pytest.raises(KeyError, match="no price for model class"):
        cost_inr("gpt-whatever", 1, 1)


# ── The env switch ────────────────────────────────────────────────────────────


def test_replay_is_the_default_when_the_variable_is_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fail safe, not fail open: a missing variable must not authorise a live
    call nobody intended to pay for."""
    monkeypatch.delenv("CASEFILE_LLM_REPLAY", raising=False)
    provider = provider_from_env()

    assert isinstance(provider, ReplayProvider)
    assert provider.inner is None, "there is no path from here to a network"
    assert provider.cache_dir == DEFAULT_CACHE_DIR


def test_turning_replay_off_fails_loudly_until_step_1_5(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CASEFILE_LLM_REPLAY", "false")
    with pytest.raises(NotImplementedError, match="ladder step 1.5"):
        provider_from_env()


def test_the_committed_cache_lives_at_the_repository_root() -> None:
    assert DEFAULT_CACHE_DIR.name == "llm_cache"
    assert (DEFAULT_CACHE_DIR / ".gitkeep").exists()
