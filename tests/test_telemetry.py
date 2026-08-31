"""Ladder step 3.4 — telemetry aggregation, against a real run.

`Telemetry`'s own arithmetic (`total_cost_inr`, `total_latency_s`,
`share_of_stages_without_model`) is already exercised in `test_models.py`
against hand-built figures, and the budget itself (§19: cost < ₹10, latency
< 10 s) is already checked in `test_fixtures.py` against the golden,
hand-typed fixture. What neither covers is whether `orchestrator.py`'s own
assembly — real wall time, real call count — produces the same shape for a
real, generated case, not a typed-in one. That is this file's job.

The two real LLM calls' own cost and latency cannot be measured live here —
same environment gap already logged for `make demo` and `AnthropicProvider`
(no key, no network). What is real and checked: the deterministic six of
eight stages' wall time, measured for real against generated data, and that
it alone already sits far under the ₹10/10 s budget with real headroom to
spare for the two calls the golden fixture's own recorded figures (₹2.1 +
₹4.6, 1.4 s + 3.1 s) already show comfortably fit the rest.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from casefile.contract import load_all
from casefile.llm import StubProvider
from casefile.models import KPIContract
from casefile.orchestrator import run_case

ROOT = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.gate2

#: The golden fixture's own recorded s3+s4c figures (fixtures/case_east_8pct.json,
#: §10) — the best available evidence for the two calls this environment cannot
#: place a live one for. Real recordings replace this once an API key does.
_RECORDED_LLM_COST_INR = 2.1 + 4.6
_RECORDED_LLM_LATENCY_S = (1400.0 + 3100.0) / 1000.0

_BUDGET_COST_INR = 10.0
_BUDGET_LATENCY_S = 10.0


@pytest.fixture(scope="module")
def contract() -> KPIContract:
    return load_all(ROOT / "contracts")["net_revenue"]


@pytest.fixture(scope="module")
def con(warehouse: Path) -> duckdb.DuckDBPyConnection:
    connection = duckdb.connect(str(warehouse), read_only=True)
    yield connection
    connection.close()


@pytest.fixture(scope="module")
def case(con: duckdb.DuckDBPyConnection, contract: KPIContract):
    return run_case(contract, "2026-04", {"region": "East"}, con, StubProvider())


def test_exactly_the_model_stages_are_marked_as_using_a_model(case) -> None:
    used_model = {s.stage: s.used_model for s in case.telemetry.stages}
    assert {name for name, used in used_model.items() if used} == {
        "s3_hypothesise", "s4c_extract",
    }


def test_the_llm_non_llm_split_matches_six_of_eight_stages(case) -> None:
    assert len(case.telemetry.stages) == 8
    assert case.telemetry.share_of_stages_without_model == pytest.approx(6 / 8)


def test_scenario_a_makes_exactly_two_real_model_calls(case) -> None:
    """Measured, not assumed: only integration_delay's funnel yields a
    document worth extracting from in this footprint and window — the other
    three drivers with a probe are either skipped (no funnel) or make no
    call 4c would keep. Two calls, not four, not per-hypothesis."""
    assert len(case.telemetry.calls) == 2
    assert {c.stage for c in case.telemetry.calls} == {"s3", "s4c"}


def test_the_deterministic_stages_alone_fit_well_inside_the_full_budget(case) -> None:
    """Real, measured wall time for verify through recommend — StubProvider
    reports its own two calls near-instantly, so this is close to the floor
    the six deterministic stages actually cost. Generous bound (2s, real
    measurement is under 1s) rather than a tight one, so this does not flake
    on a slower CI runner; it exists to prove there is real headroom left for
    the two calls this environment cannot place a live one for."""
    deterministic = sum(
        s.wall_ms for s in case.telemetry.stages if not s.used_model
    ) / 1000.0
    assert deterministic < 2.0


def test_the_recorded_llm_figures_leave_the_full_run_under_budget(case) -> None:
    deterministic_s = sum(
        s.wall_ms for s in case.telemetry.stages if not s.used_model
    ) / 1000.0
    estimated_total_latency = deterministic_s + _RECORDED_LLM_LATENCY_S
    assert estimated_total_latency < _BUDGET_LATENCY_S
    assert _RECORDED_LLM_COST_INR < _BUDGET_COST_INR
