"""engine/hypothesise.py — Stage 3, S3.

B3's definition of done, made into assertions:

    "Hypothesis set is registry-enumerated and identical across runs; the
    model can only annotate and flag `unmodelled`, never add or remove a
    tested hypothesis; zero numbers in output"

Enumeration is exercised against the real `net_revenue` contract; the two
guardrails (fill a skipped driver, fold an invented one into `unmodelled`) are
exercised against a fake provider whose response is built by hand, because
that is the only way to construct the exact malformed shapes the guardrails
exist to catch.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from pydantic import BaseModel

from casefile.contract import load
from casefile.engine.hypothesise import HypothesiseResponse, _enumerate, hypothesise
from casefile.llm.base import Prompt
from casefile.llm.stub import StubProvider
from casefile.models import Footprint, Hypothesis, KPIContract, Signature, Trigger, Usage

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def contract() -> KPIContract:
    return load(ROOT / "contracts" / "net_revenue.yaml")


@pytest.fixture
def trigger() -> Trigger:
    return Trigger(
        kpi="net_revenue", period="2026-04", dimensions={"region": "East"},
        delta=-26_077_219.0, delta_relative=-0.0833,
    )


@pytest.fixture
def footprint() -> Footprint:
    return Footprint(
        entities={"account": ["ACC-0001", "ACC-0002"]},
        window_start=date(2026, 3, 1), window_end=date(2026, 4, 30), delta=-26_077_219.0,
    )


class FakeProvider:
    """Hands back a fixed `HypothesiseResponse` regardless of the prompt — the
    guardrail tests need to control exactly what the "model" said, including
    shapes a real one is instructed never to produce."""

    def __init__(self, hypotheses: list[Hypothesis]) -> None:
        self._response = HypothesiseResponse(hypotheses=hypotheses)

    def complete(self, prompt: Prompt, schema: type[BaseModel]) -> tuple[BaseModel, Usage]:
        assert schema is HypothesiseResponse
        return self._response, Usage(
            stage=prompt.stage, model="fake", input_tokens=1, output_tokens=1,
            latency_ms=0.0, cost_inr=0.0,
        )


def a_hypothesis(driver_id: str, rationale: str = "because") -> Hypothesis:
    return Hypothesis(
        driver_id=driver_id, rationale=rationale, priority=1, expected_signature=Signature()
    )


# ── Enumeration — deterministic and total ─────────────────────────────────────


def test_enumeration_is_every_driver_on_the_contract_in_order(contract: KPIContract) -> None:
    assert _enumerate(contract) == [driver.id for driver in contract.drivers]


def test_the_stub_still_covers_every_registry_driver(
    contract: KPIContract, trigger: Trigger, footprint: Footprint
) -> None:
    """The stub's default response is an empty list — the harshest case for
    the guardrail that fills in a skipped driver."""
    hypotheses, _ = hypothesise(contract, trigger, footprint, StubProvider())
    assert {h.driver_id for h in hypotheses} == {d.id for d in contract.drivers}


def test_the_hypothesis_set_is_identical_across_runs(
    contract: KPIContract, trigger: Trigger, footprint: Footprint
) -> None:
    """Two calls, two entirely different rationale texts from the "model" —
    the *set of driver ids* must not move."""
    driver_ids = _enumerate(contract)
    run_1 = FakeProvider([a_hypothesis(d, "run one says X") for d in driver_ids])
    run_2 = FakeProvider(
        [a_hypothesis(d, "run two says something else entirely") for d in driver_ids]
    )

    first, _ = hypothesise(contract, trigger, footprint, run_1)
    second, _ = hypothesise(contract, trigger, footprint, run_2)

    assert {h.driver_id for h in first} == {h.driver_id for h in second} == set(driver_ids)


# ── Guardrails, enforced in code ───────────────────────────────────────────────


def test_a_response_that_skips_a_driver_gets_it_filled_in(
    contract: KPIContract, trigger: Trigger, footprint: Footprint
) -> None:
    driver_ids = _enumerate(contract)
    missing = driver_ids[0]
    provider = FakeProvider([a_hypothesis(d) for d in driver_ids if d != missing])

    hypotheses, _ = hypothesise(contract, trigger, footprint, provider)

    filled = next(h for h in hypotheses if h.driver_id == missing)
    assert "no annotation returned" in filled.rationale


def test_an_off_registry_suggestion_lands_as_unmodelled(
    contract: KPIContract, trigger: Trigger, footprint: Footprint
) -> None:
    driver_ids = _enumerate(contract)
    provider = FakeProvider(
        [a_hypothesis(d) for d in driver_ids]
        + [a_hypothesis("mystery_cause", "a supply chain event nothing here models")]
    )

    hypotheses, _ = hypothesise(contract, trigger, footprint, provider)

    assert not any(h.driver_id == "mystery_cause" for h in hypotheses)
    unmodelled = [h for h in hypotheses if h.driver_id == "unmodelled"]
    assert len(unmodelled) == 1
    assert "supply chain event" in unmodelled[0].rationale


def test_a_legitimate_unmodelled_flag_is_kept_as_is(
    contract: KPIContract, trigger: Trigger, footprint: Footprint
) -> None:
    driver_ids = _enumerate(contract)
    provider = FakeProvider(
        [a_hypothesis(d) for d in driver_ids] + [a_hypothesis("unmodelled", "genuinely novel")]
    )
    hypotheses, _ = hypothesise(contract, trigger, footprint, provider)
    unmodelled = [h for h in hypotheses if h.driver_id == "unmodelled"]
    assert len(unmodelled) == 1
    assert unmodelled[0].rationale == "genuinely novel"


def test_a_second_off_registry_suggestion_is_dropped_not_appended(
    contract: KPIContract, trigger: Trigger, footprint: Footprint
) -> None:
    """"It may add exactly one thing" — a model that tries to add two gets one."""
    driver_ids = _enumerate(contract)
    provider = FakeProvider(
        [a_hypothesis(d) for d in driver_ids]
        + [a_hypothesis("first_guess", "kept"), a_hypothesis("second_guess", "dropped")]
    )
    hypotheses, _ = hypothesise(contract, trigger, footprint, provider)
    unmodelled = [h for h in hypotheses if h.driver_id == "unmodelled"]
    assert len(unmodelled) == 1
    assert unmodelled[0].rationale == "kept"


def test_a_duplicate_annotation_for_one_driver_keeps_the_first(
    contract: KPIContract, trigger: Trigger, footprint: Footprint
) -> None:
    driver_ids = _enumerate(contract)
    twice = driver_ids[0]
    provider = FakeProvider(
        [a_hypothesis(twice, "first annotation")]
        + [a_hypothesis(d) for d in driver_ids]  # includes `twice` again, second time
    )
    hypotheses, _ = hypothesise(contract, trigger, footprint, provider)
    kept = [h for h in hypotheses if h.driver_id == twice]
    assert len(kept) == 1
    assert kept[0].rationale == "first annotation"


def test_usage_from_the_provider_passes_through(
    contract: KPIContract, trigger: Trigger, footprint: Footprint
) -> None:
    provider = FakeProvider([a_hypothesis(d) for d in _enumerate(contract)])
    _, usage = hypothesise(contract, trigger, footprint, provider)
    assert usage.stage == "s3"


# ── §17: no numbers in the output ──────────────────────────────────────────────


def test_hypothesis_has_no_numeric_field_but_priority() -> None:
    """priority is display order only (§15 S3) — every other field the model
    can fill is text."""
    numeric = {
        name
        for name, field in Hypothesis.model_fields.items()
        if field.annotation in (int, float)
    }
    assert numeric == {"priority"}


def test_signature_has_no_numeric_field_at_all() -> None:
    numeric = {
        name
        for name, field in Signature.model_fields.items()
        if field.annotation in (int, float, int | None, float | None)
    }
    assert numeric == set()
