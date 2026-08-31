"""orchestrator.py — ladder step 3.1, "make demo runs alert -> closed case."

`run_case` is exercised against real generated data for both outcomes: a case
that closes at Verify (no model calls, no decomposition) and a case that runs
the full S1-S7 chain. The full chain uses `StubProvider` rather than a live or
replayed model — this file's job is proving the *wiring* holds together
(every stage's output reaches the next stage, every `Usage`/wall-time reaches
`Telemetry`), not re-testing what S3/S4c already cover with their own
guardrail tests.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from casefile.contract import load_all
from casefile.llm import StubProvider
from casefile.metric import value
from casefile.models import KPIContract
from casefile.orchestrator import run_case

ROOT = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.gate3


@pytest.fixture(scope="module")
def contracts() -> dict[str, KPIContract]:
    return load_all(ROOT / "contracts")


@pytest.fixture(scope="module")
def con(warehouse: Path) -> duckdb.DuckDBPyConnection:
    connection = duckdb.connect(str(warehouse), read_only=True)
    yield connection
    connection.close()


# ── A case that closes at Verify ─────────────────────────────────────────────


def test_a_case_that_fails_verify_closes_with_no_model_calls(
    con: duckdb.DuckDBPyConnection, contracts: dict[str, KPIContract]
) -> None:
    """Scenario D's own month/region: a refund batch, closed as an artefact."""
    case = run_case(
        contracts["net_revenue"], "2026-03", {"region": "West"}, con, StubProvider()
    )
    assert case.verification.passed is False
    assert case.decomposition is None
    assert case.hypotheses == []
    assert case.ledger == []
    assert case.verdict is None
    assert case.recommendation is None
    assert case.priority == 0.0
    assert case.telemetry.calls == []
    assert [s.stage for s in case.telemetry.stages] == ["s1_verify"]
    assert case.trigger.kpi == "net_revenue"


# ── The full chain, real data through S1-S7 ──────────────────────────────────


@pytest.fixture(scope="module")
def scenario_a(con: duckdb.DuckDBPyConnection, contracts: dict[str, KPIContract]):
    return run_case(
        contracts["net_revenue"], "2026-04", {"region": "East"}, con, StubProvider()
    )


def test_the_full_chain_produces_a_complete_case(scenario_a) -> None:
    case = scenario_a
    assert case.verification.passed is True
    assert case.decomposition is not None
    assert case.hypotheses  # every registry driver, guardrailed
    assert case.ledger
    assert case.tests
    assert case.verdict is not None
    assert case.priority > 0.0


def test_every_stage_reports_its_wall_time_in_order(scenario_a) -> None:
    stages = [s.stage for s in scenario_a.telemetry.stages]
    assert stages == [
        "s1_verify", "s2_decompose", "s3_hypothesise", "s4a_probes",
        "s4c_extract", "s5_challenge", "s6_adjudicate", "s7_recommend",
    ]
    assert all(s.wall_ms >= 0.0 for s in scenario_a.telemetry.stages)


def test_only_the_model_stages_are_marked_as_using_a_model(scenario_a) -> None:
    used_model = {s.stage: s.used_model for s in scenario_a.telemetry.stages}
    assert used_model["s3_hypothesise"] is True
    assert used_model["s1_verify"] is False
    assert used_model["s2_decompose"] is False
    assert used_model["s5_challenge"] is False


def test_every_model_calls_usage_reaches_telemetry(scenario_a) -> None:
    # One S3 call plus one S4c call per driver with document-bearing sources.
    assert len(scenario_a.telemetry.calls) >= 1
    assert all(u.stage in ("s3", "s4c") for u in scenario_a.telemetry.calls)


def test_the_trigger_delta_matches_the_real_decomposed_total(scenario_a) -> None:
    case = scenario_a
    assert case.trigger.delta == pytest.approx(case.decomposition.total_delta)
    assert case.trigger.kpi == "net_revenue"
    assert case.trigger.period == "2026-04"
    assert case.trigger.dimensions == {"region": "East"}


def test_the_trigger_delta_relative_is_the_real_percent_against_march(
    con: duckdb.DuckDBPyConnection, contracts: dict[str, KPIContract], scenario_a
) -> None:
    """§10's own headline number: −8.0%. `delta` gets overwritten with the
    decomposed total after Verify passes, but `delta_relative` does not — it
    is only ever the one computed before Verify runs, against the real
    previous-period value, so this is the one place that number is checked."""
    previous = value(con, contracts["net_revenue"], "2026-03", {"region": "East"})
    expected = scenario_a.decomposition.total_delta / previous
    assert scenario_a.trigger.delta_relative == pytest.approx(expected)
    assert scenario_a.trigger.delta_relative == pytest.approx(-0.08, abs=0.005)


def test_the_case_id_names_the_kpi_period_and_dimensions(scenario_a) -> None:
    assert scenario_a.id == "case-2026-04-net_revenue-east"
