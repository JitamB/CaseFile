"""engine/adjudicate.py — Stage 6, §9's four verdicts.

Ladder step 2.5's own verify text: "A → Likely, B → Undetermined, G →
Contested." A and B are asserted against the real, generated cases — no
hand-typed stand-in. G has no generator support yet (§44's own ladder order
puts scenario G's injection at 2.8, after this step), so the Contested path
is exercised against a hand-built `TestMatrix` pair instead — the same
approach `test_evidence.py` already takes for `_lost_reason_scan`'s
denominator distinction, where the real warehouse happens not to exercise it.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import duckdb
import pytest

from casefile.contract import load_all
from casefile.engine.adjudicate import AdjudicateError, adjudicate
from casefile.engine.challenge import challenge
from casefile.engine.decompose import decompose
from casefile.engine.evidence import gather_probes
from casefile.engine.verify import verify
from casefile.models import (
    ContributionTree,
    Footprint,
    Hypothesis,
    KPIContract,
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
    """The real pipeline, S1 through S6, against generated data — no
    hand-typed stand-in for any of the numbers adjudicate() reads."""
    result = verify(con, contract, period, dimensions)
    assert result.passed
    tree = decompose(con, contract, period, dimensions)
    hypotheses = all_hypotheses(contract)
    ledger = gather_probes(contract, hypotheses, tree.footprint, con)
    matrices, challenge_items = challenge(contract, hypotheses, tree, con)
    ledger += challenge_items
    verdict, question, priority = adjudicate(contract, hypotheses, tree, ledger, matrices, result)
    return verdict, question, priority, tree.total_delta


# ── Scenario A, real: Likely, ranked, not crowned ────────────────────────────


@pytest.fixture(scope="module")
def scenario_a(con: duckdb.DuckDBPyConnection, contracts: dict[str, KPIContract]):
    return run_case(con, contracts["net_revenue"], "2026-04", {"region": "East"})


def test_scenario_a_is_likely_not_confirmed(scenario_a) -> None:
    verdict, _question, _priority, _delta = scenario_a
    assert verdict.confidence == "likely"


def test_scenario_a_ranks_rather_than_crowns(scenario_a) -> None:
    verdict, _question, _priority, _delta = scenario_a
    by_id = {a.driver_id: a for a in verdict.attribution}

    assert by_id["integration_delay"].status == "primary"
    assert by_id["integration_delay"].share is not None
    assert by_id["integration_delay"].share > 0.9  # the footprint is nearly the whole movement

    assert by_id["pricing_change"].status == "minor"
    assert by_id["pricing_change"].eliminated_by is None  # minor keeps its finding, not a kill

    assert by_id["competitor_offer"].status == "eliminated"
    assert by_id["competitor_offer"].eliminated_by is not None


def test_scenario_a_has_exactly_one_primary(scenario_a) -> None:
    verdict, _question, _priority, _delta = scenario_a
    primaries = [a for a in verdict.attribution if a.status == "primary"]
    assert len(primaries) == 1


def test_scenario_a_carries_a_discriminating_question_about_the_primary(scenario_a) -> None:
    verdict, question, _priority, _delta = scenario_a
    assert question is not None
    assert question.hypotheses_separated == ["integration_delay"]
    assert question.value_at_stake > 0
    assert question.owner_role


def test_scenario_a_priority_is_delta_times_the_likely_weight(scenario_a) -> None:
    _verdict, _question, priority, total_delta = scenario_a
    assert priority == pytest.approx(abs(total_delta) * 0.8, rel=1e-6)


# ── Scenario B, real: Undetermined, the sources cannot see it ───────────────


@pytest.fixture(scope="module")
def scenario_b(con: duckdb.DuckDBPyConnection, contracts: dict[str, KPIContract]):
    return run_case(con, contracts["new_business_arr"], "2025-10", {"region": "North"})


def test_scenario_b_is_undetermined(scenario_b) -> None:
    verdict, _question, _priority, _delta = scenario_b
    assert verdict.confidence == "undetermined"


def test_scenario_b_carries_the_expected_discriminating_question(scenario_b) -> None:
    verdict, question, _priority, _delta = scenario_b
    assert question is not None
    assert question.value_at_stake > 0
    assert question.hypotheses_separated


def test_scenario_b_has_no_primary(scenario_b) -> None:
    """§9: confirmed/likely need a primary; undetermined must not have one —
    `Verdict`'s own validator would already refuse this, but the rubric
    should never even try."""
    verdict, _question, _priority, _delta = scenario_b
    assert not any(a.status == "primary" for a in verdict.attribution)


def test_scenario_b_distinguishes_no_coverage_from_checked_absent(scenario_b) -> None:
    """The true cause (competitor_offer) has no refuting test anywhere — the
    lost-reason field was never populated, not checked and found silent — so
    it is `unresolved`, never `eliminated`. Only a driver a test actually
    refuted (pricing_change, on locality) is eliminated."""
    verdict, _question, _priority, _delta = scenario_b
    by_id = {a.driver_id: a for a in verdict.attribution}
    assert by_id["competitor_offer"].status == "unresolved"
    assert by_id["competitor_offer"].eliminated_by is None
    assert by_id["pricing_change"].status == "eliminated"
    assert by_id["pricing_change"].eliminated_by is not None


# ── Synthetic matrices — Confirmed, Contested, and the ceiling ──────────────


def a_result(outcome: str, statistic: float | None = None) -> TestResult:
    return TestResult(outcome=outcome, detail="synthetic", statistic=statistic)


def a_matrix(timing: str, locality: str, dose: str, control: str) -> TestMatrix:
    return TestMatrix(
        timing=a_result(timing), locality=a_result(locality),
        dose=a_result(dose), control=a_result(control),
    )


@pytest.fixture
def synthetic_tree() -> ContributionTree:
    footprint = Footprint(
        entities={"account_id": ["ACC-1", "ACC-2", "ACC-3", "ACC-4", "ACC-5"]},
        window_start=date(2026, 1, 1), window_end=date(2026, 2, 28), delta=-1_000_000.0,
    )
    return ContributionTree(
        kpi="net_revenue", period="2026-02", total_delta=-1_000_000.0,
        by_dimension={}, footprint=footprint,
    )


@pytest.fixture
def clean_verification() -> VerificationResult:
    return VerificationResult(passed=True, checks=[], freshness_hours=1.0)


def test_a_hypothesis_that_passes_everything_including_dose_is_confirmed(
    contracts: dict[str, KPIContract], synthetic_tree: ContributionTree, clean_verification
) -> None:
    """The only way Confirmed is reachable at all — every test passes, Dose
    included, which needs n >= 5 pairs by construction."""
    contract = contracts["net_revenue"]
    matrices = {"integration_delay": a_matrix("pass", "pass", "pass", "pass")}
    verdict, question, _priority = adjudicate(
        contract, [a_hypothesis("integration_delay")], synthetic_tree, [],
        matrices, clean_verification,
    )
    assert verdict.confidence == "confirmed"
    assert verdict.attribution[0].status == "primary"
    assert question is None  # nothing left worth asking


def test_two_hypotheses_both_surviving_is_contested(
    contracts: dict[str, KPIContract], synthetic_tree: ContributionTree, clean_verification
) -> None:
    """Scenario G's own shape: two mechanisms, identical footprints, neither
    Dose nor Control can separate them."""
    contract = contracts["expansion_arr"]
    matrices = {
        "pricing_change": a_matrix("pass", "pass", "inconclusive", "inconclusive"),
        "supply_delay": a_matrix("pass", "pass", "inconclusive", "inconclusive"),
    }
    hypotheses = [a_hypothesis("pricing_change"), a_hypothesis("supply_delay")]
    verdict, question, _priority = adjudicate(
        contract, hypotheses, synthetic_tree, [], matrices, clean_verification
    )
    assert verdict.confidence == "contested"
    assert not any(a.status == "primary" for a in verdict.attribution)
    assert {a.status for a in verdict.attribution} == {"unresolved"}
    assert question is not None


def test_a_hypothesis_refuted_by_any_test_never_survives(
    contracts: dict[str, KPIContract], synthetic_tree: ContributionTree, clean_verification
) -> None:
    contract = contracts["net_revenue"]
    matrices = {"integration_delay": a_matrix("pass", "pass", "pass", "refute")}
    verdict, _question, _priority = adjudicate(
        contract, [a_hypothesis("integration_delay")], synthetic_tree, [],
        matrices, clean_verification,
    )
    assert verdict.confidence == "undetermined"
    assert verdict.attribution[0].status == "eliminated"


def test_a_borrowed_baseline_caps_confirmed_at_likely(
    contracts: dict[str, KPIContract], synthetic_tree: ContributionTree
) -> None:
    contract = contracts["net_revenue"]
    matrices = {"integration_delay": a_matrix("pass", "pass", "pass", "pass")}
    capped = VerificationResult(
        passed=True, checks=[], freshness_hours=1.0,
        baseline="borrowed", confidence_ceiling="likely",
    )
    verdict, question, _priority = adjudicate(
        contract, [a_hypothesis("integration_delay")], synthetic_tree, [], matrices, capped
    )
    assert verdict.confidence == "likely"  # would have been confirmed
    assert question is not None  # capped means something is still worth asking


def test_a_ceiling_never_raises_undetermined_or_contested(
    contracts: dict[str, KPIContract], synthetic_tree: ContributionTree
) -> None:
    """§9: ceilings only ever lower. A "likely" ceiling on an already-worse
    verdict must not do anything at all."""
    contract = contracts["net_revenue"]
    matrices = {"integration_delay": a_matrix("refute", "pass", "pass", "pass")}
    capped = VerificationResult(
        passed=True, checks=[], freshness_hours=1.0, confidence_ceiling="likely",
    )
    verdict, _question, _priority = adjudicate(
        contract, [a_hypothesis("integration_delay")], synthetic_tree, [], matrices, capped
    )
    assert verdict.confidence == "undetermined"  # not lifted to "likely"


def test_an_unmodelled_hypothesis_forces_undetermined(
    contracts: dict[str, KPIContract], synthetic_tree: ContributionTree, clean_verification
) -> None:
    """Even a driver that passed everything cannot carry a confident verdict
    when the model flagged a cause the registry doesn't know about — the
    rubric refuses to paper over that with a confident answer about a
    *different* cause."""
    contract = contracts["net_revenue"]
    matrices = {"integration_delay": a_matrix("pass", "pass", "pass", "pass")}
    hypotheses = [a_hypothesis("integration_delay"), a_hypothesis("unmodelled")]
    verdict, _question, _priority = adjudicate(
        contract, hypotheses, synthetic_tree, [], matrices, clean_verification
    )
    assert verdict.confidence == "undetermined"


def test_priority_weight_is_monotone_with_confidence(
    contracts: dict[str, KPIContract], synthetic_tree: ContributionTree, clean_verification
) -> None:
    contract = contracts["net_revenue"]
    confirmed = a_matrix("pass", "pass", "pass", "pass")
    refuted = a_matrix("refute", "pass", "pass", "pass")

    _v, _q, p_confirmed = adjudicate(
        contract, [a_hypothesis("integration_delay")], synthetic_tree, [],
        {"integration_delay": confirmed}, clean_verification,
    )
    _v, _q, p_undetermined = adjudicate(
        contract, [a_hypothesis("integration_delay")], synthetic_tree, [],
        {"integration_delay": refuted}, clean_verification,
    )
    assert p_confirmed > p_undetermined
    assert p_undetermined > 0  # never falls off a priority-ordered list entirely


def test_nothing_to_adjudicate_raises(
    contracts: dict[str, KPIContract], synthetic_tree: ContributionTree, clean_verification
) -> None:
    contract = contracts["net_revenue"]
    with pytest.raises(AdjudicateError, match="nothing was challenged"):
        adjudicate(contract, [], synthetic_tree, [], {}, clean_verification)
