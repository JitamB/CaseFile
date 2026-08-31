"""engine/recommend.py — Stage 7, the brief's own seven fields.

Ladder step 2.6's own verify text: "Seven fields; impact = at-risk ×
save_rate, labelled as an assumption." Scenario A (Likely, a real primary)
and scenario B (Undetermined, no primary) are asserted against the real,
generated cases — no hand-typed stand-in for either. The branches those two
scenarios cannot reach — Contested, a driver with no lever, an unregistered
lever action — are exercised against `adjudicate()`'s own synthetic-matrix
fixtures, the same approach `test_adjudicate.py` already takes for Confirmed
and Contested.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import duckdb
import pytest

from casefile.contract import load_all
from casefile.engine.adjudicate import adjudicate
from casefile.engine.challenge import challenge
from casefile.engine.decompose import decompose
from casefile.engine.evidence import gather_probes
from casefile.engine.recommend import RecommendError, recommend
from casefile.engine.verify import verify
from casefile.models import (
    AccessRules,
    ContributionTree,
    DataQuality,
    Driver,
    Footprint,
    Hypothesis,
    KPIContract,
    Lever,
    Lineage,
    Materiality,
    RefreshSpec,
    Signature,
    TestMatrix,
    TestResult,
    VerificationResult,
)

ROOT = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.gate2


@pytest.fixture(scope="module")
def contracts() -> dict[str, KPIContract]:
    return load_all(ROOT / "contracts")


@pytest.fixture(scope="module")
def con(warehouse: Path) -> duckdb.DuckDBPyConnection:
    connection = duckdb.connect(str(warehouse), read_only=True)
    yield connection
    connection.close()


def a_hypothesis(driver_id: str) -> Hypothesis:
    return Hypothesis(
        driver_id=driver_id, rationale="test fixture", priority=1,
        expected_signature=Signature(),
    )


def all_hypotheses(contract: KPIContract) -> list[Hypothesis]:
    return [a_hypothesis(d.id) for d in contract.drivers]


def run_case(
    con: duckdb.DuckDBPyConnection, contract: KPIContract, period: str, dimensions: dict[str, str]
):
    """The real pipeline, S1 through S7, against generated data."""
    result = verify(con, contract, period, dimensions)
    assert result.passed
    tree = decompose(con, contract, period, dimensions)
    hypotheses = all_hypotheses(contract)
    ledger = gather_probes(contract, hypotheses, tree.footprint, con)
    matrices, challenge_items = challenge(contract, hypotheses, tree, con)
    ledger += challenge_items
    verdict, _question, _priority = adjudicate(contract, hypotheses, tree, ledger, matrices, result)
    recommendation = recommend(contract, verdict, tree, dimensions)
    return recommendation, verdict, tree


# ── Scenario A, real: Likely, a recommendation for the primary ─────────────


@pytest.fixture(scope="module")
def scenario_a(con: duckdb.DuckDBPyConnection, contracts: dict[str, KPIContract]):
    return run_case(con, contracts["net_revenue"], "2026-04", {"region": "East"})


def test_scenario_a_recommends_the_primary_driver(scenario_a) -> None:
    recommendation, verdict, _tree = scenario_a
    primary = next(a for a in verdict.attribution if a.status == "primary")
    assert recommendation is not None
    assert recommendation.driver_id == primary.driver_id == "integration_delay"


def test_scenario_a_lever_and_owner_come_from_the_contract(scenario_a) -> None:
    recommendation, _verdict, _tree = scenario_a
    assert recommendation.lever == "prioritise_integration_fix"
    assert recommendation.owner_role == "vp_engineering"


def test_scenario_a_expected_impact_is_total_delta_times_save_rate(scenario_a) -> None:
    recommendation, _verdict, tree = scenario_a
    value_at_risk = abs(tree.total_delta)
    assert recommendation.expected_impact == pytest.approx(
        (value_at_risk * 0.75, value_at_risk * 1.00)
    )


def test_scenario_a_confidence_matches_the_verdict(scenario_a) -> None:
    recommendation, verdict, _tree = scenario_a
    assert recommendation.confidence == verdict.confidence == "likely"


def test_scenario_a_action_names_the_footprint_accounts(scenario_a) -> None:
    recommendation, _verdict, tree = scenario_a
    for account in tree.footprint.entities["account_id"]:
        assert account in recommendation.action


def test_scenario_a_monitoring_names_the_kpi_region_and_persistence(scenario_a) -> None:
    recommendation, _verdict, _tree = scenario_a
    assert "net_revenue" in recommendation.monitoring
    assert "East" in recommendation.monitoring
    assert "2 cycles" in recommendation.monitoring  # materiality.min_persistence


# ── Scenario B, real: Undetermined, nothing to recommend ───────────────────


def test_scenario_b_has_no_recommendation(con: duckdb.DuckDBPyConnection, contracts) -> None:
    recommendation, verdict, _tree = run_case(
        con, contracts["new_business_arr"], "2025-10", {"region": "North"}
    )
    assert verdict.confidence == "undetermined"
    assert recommendation is None


# ── Synthetic matrices — Confirmed, Contested, no lever, no action text ────


def a_result(outcome: str) -> TestResult:
    return TestResult(outcome=outcome, detail="synthetic")


def a_matrix(timing: str, locality: str, dose: str, control: str) -> TestMatrix:
    return TestMatrix(
        timing=a_result(timing), locality=a_result(locality),
        dose=a_result(dose), control=a_result(control),
    )


@pytest.fixture
def synthetic_tree() -> ContributionTree:
    footprint = Footprint(
        entities={"account_id": ["ACC-1", "ACC-2"]},
        window_start=date(2026, 1, 1), window_end=date(2026, 2, 28), delta=-1_000_000.0,
    )
    return ContributionTree(
        kpi="net_revenue", period="2026-02", total_delta=-1_000_000.0,
        by_dimension={}, footprint=footprint,
    )


@pytest.fixture
def clean_verification() -> VerificationResult:
    return VerificationResult(passed=True, checks=[], freshness_hours=1.0)


def test_a_confirmed_primary_gets_the_exact_impact_band(
    contracts: dict[str, KPIContract], synthetic_tree: ContributionTree, clean_verification
) -> None:
    contract = contracts["net_revenue"]
    matrices = {"integration_delay": a_matrix("pass", "pass", "pass", "pass")}
    verdict, _question, _priority = adjudicate(
        contract, [a_hypothesis("integration_delay")], synthetic_tree, [],
        matrices, clean_verification,
    )
    recommendation = recommend(contract, verdict, synthetic_tree, {"region": "East"})
    assert recommendation is not None
    assert recommendation.expected_impact == (750_000.0, 1_000_000.0)
    assert recommendation.monitoring == (
        "net_revenue, East, daily; escalate if not recovered within 2 cycles"
    )


def test_a_contested_verdict_recommends_nothing(
    contracts: dict[str, KPIContract], synthetic_tree: ContributionTree, clean_verification
) -> None:
    """§9: recommending one lever over an untied rival is exactly the
    overclaiming Stage 6's ranked-not-crowned rule exists to prevent —
    Contested's actionable next step is the discriminating question, not
    this stage."""
    contract = contracts["expansion_arr"]
    matrices = {
        "pricing_change": a_matrix("pass", "pass", "inconclusive", "inconclusive"),
        "supply_delay": a_matrix("pass", "pass", "inconclusive", "inconclusive"),
    }
    hypotheses = [a_hypothesis("pricing_change"), a_hypothesis("supply_delay")]
    verdict, _question, _priority = adjudicate(
        contract, hypotheses, synthetic_tree, [], matrices, clean_verification
    )
    assert verdict.confidence == "contested"
    assert recommend(contract, verdict, synthetic_tree, {}) is None


def test_a_primary_driver_with_no_lever_recommends_nothing(
    contracts: dict[str, KPIContract], synthetic_tree: ContributionTree, clean_verification
) -> None:
    """Seasonality: `external_uncontrollable`, `lever: null` in every
    contract. There is nothing here to put a name on."""
    contract = contracts["net_revenue"]
    matrices = {"seasonality": a_matrix("pass", "pass", "pass", "pass")}
    verdict, _question, _priority = adjudicate(
        contract, [a_hypothesis("seasonality")], synthetic_tree, [], matrices, clean_verification
    )
    assert verdict.attribution[0].status == "primary"
    assert recommend(contract, verdict, synthetic_tree, {}) is None


def _minimal_contract(lever: Lever) -> KPIContract:
    driver = Driver(
        id="bogus", type="internal_controllable", evidence_sources=["tickets"],
        max_lag_days=1, probe_sql="probes/ticket_spike.sql", lever=lever,
    )
    return KPIContract(
        id="net_revenue", label="x", owner_role="cfo", definition="x", unit="INR",
        direction="down_is_good", grain=["date"], calendar="fiscal_445",
        formula="SUM(x)", refresh=RefreshSpec(source="billing", cadence="24h", sla_hours=24),
        decomposition_dims=["region"], materiality=Materiality(
            relative=0.03, absolute=1.0, min_persistence=2, z_threshold=3.0
        ),
        data_quality=DataQuality(max_single_record_share=0.35, min_completeness=0.95),
        drivers=[driver], lineage=Lineage(), access=AccessRules(),
        history_start=date(2023, 1, 1), seasonal_period_days=365,
    )


def test_a_lever_action_with_no_registered_text_raises(
    synthetic_tree: ContributionTree, clean_verification
) -> None:
    lever = Lever(action="mystery_lever", owner_role="cfo", lag_days=1, save_rate=(0.1, 0.2))
    contract = _minimal_contract(lever)
    matrices = {"bogus": a_matrix("pass", "pass", "pass", "pass")}
    verdict, _question, _priority = adjudicate(
        contract, [a_hypothesis("bogus")], synthetic_tree, [], matrices, clean_verification
    )
    with pytest.raises(RecommendError, match="mystery_lever"):
        recommend(contract, verdict, synthetic_tree, {})
