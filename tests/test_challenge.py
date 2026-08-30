"""engine/challenge.py — Stage 5, the four tests.

Ladder step 2.4's own verify text: "Both decoys refuted on A; Dose
inconclusive at n=2; Control reports placebo rank." All three are asserted
here against the real, generated headline case — no hand-typed stand-in, the
same discipline `test_evidence.py` and `test_decompose.py` already keep.
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pytest

from casefile.contract import load_all
from casefile.engine.challenge import ChallengeError, challenge
from casefile.engine.decompose import decompose
from casefile.models import ContributionTree, Hypothesis, KPIContract, Signature

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


@pytest.fixture(scope="module")
def sealed(generated: Path) -> dict[str, dict]:
    """`tests/` only — §30 rule 3."""
    return json.loads((generated / "ground_truth.json").read_text(encoding="utf-8"))["scenarios"]


@pytest.fixture(scope="module")
def east(con: duckdb.DuckDBPyConnection, contracts: dict[str, KPIContract]) -> ContributionTree:
    return decompose(con, contracts["net_revenue"], "2026-04", {"region": "East"})


def a_hypothesis(driver_id: str) -> Hypothesis:
    return Hypothesis(
        driver_id=driver_id, rationale="test fixture", priority=1,
        expected_signature=Signature(),
    )


def all_hypotheses(contract: KPIContract) -> list[Hypothesis]:
    return [a_hypothesis(d.id) for d in contract.drivers]


# ── The ladder's own verify text, against the real headline case ────────────


def test_both_decoys_are_refuted(
    con: duckdb.DuckDBPyConnection, contracts: dict[str, KPIContract], east: ContributionTree
) -> None:
    contract = contracts["net_revenue"]
    matrices, _items = challenge(contract, all_hypotheses(contract), east, con)

    for decoy in ("pricing_change", "competitor_offer"):
        matrix = matrices[decoy]
        outcomes = [
            matrix.timing.outcome, matrix.locality.outcome,
            matrix.dose.outcome, matrix.control.outcome,
        ]
        assert "refute" in outcomes, f"{decoy} was not refuted by any test: {outcomes}"


def test_the_decoys_are_refuted_by_the_tests_the_answer_sheet_names(
    con: duckdb.DuckDBPyConnection, contracts: dict[str, KPIContract], east: ContributionTree,
    sealed: dict,
) -> None:
    """The sealed answer sheet records exactly which test killed each decoy —
    `locality` for pricing, `locality_and_timing` for competitor. Not just
    'refuted by something', refuted by the right thing."""
    contract = contracts["net_revenue"]
    matrices, _items = challenge(contract, all_hypotheses(contract), east, con)
    events = {e["driver_id"]: e for e in sealed["A"]["events"]}

    assert matrices["pricing_change"].locality.outcome == "refute"
    assert "locality" in events["pricing_change"]["killed_by"]

    assert matrices["competitor_offer"].locality.outcome == "refute"
    assert matrices["competitor_offer"].timing.outcome == "refute"
    assert events["competitor_offer"]["killed_by"] == "locality_and_timing"


def test_dose_is_inconclusive_at_two_accounts(
    con: duckdb.DuckDBPyConnection, contracts: dict[str, KPIContract], east: ContributionTree
) -> None:
    contract = contracts["net_revenue"]
    matrices, _items = challenge(
        contract, [a_hypothesis("integration_delay")], east, con
    )
    dose = matrices["integration_delay"].dose
    assert dose.outcome == "inconclusive"
    assert dose.statistic is None
    assert "n = 2" in dose.detail or "n=2" in dose.detail


def test_control_reports_a_placebo_rank(
    con: duckdb.DuckDBPyConnection, contracts: dict[str, KPIContract], east: ContributionTree
) -> None:
    contract = contracts["net_revenue"]
    matrices, _items = challenge(
        contract, [a_hypothesis("integration_delay")], east, con
    )
    control = matrices["integration_delay"].control
    assert "rank" in control.detail
    assert control.statistic is not None


def test_the_true_cause_survives_timing_and_locality(
    con: duckdb.DuckDBPyConnection, contracts: dict[str, KPIContract], east: ContributionTree
) -> None:
    contract = contracts["net_revenue"]
    matrices, _items = challenge(
        contract, [a_hypothesis("integration_delay")], east, con
    )
    matrix = matrices["integration_delay"]
    assert matrix.timing.outcome == "pass"
    assert matrix.locality.outcome == "pass"
    assert matrix.locality.statistic == pytest.approx(1.0)


def test_timing_lags_match_the_real_renewal_dates(
    con: duckdb.DuckDBPyConnection, contracts: dict[str, KPIContract], east: ContributionTree
) -> None:
    """21 and 23 days: the two renewals' real `closed_date` (April 2, April 4)
    against the real PELT onset (March 12) — §10's own worked numbers,
    reproduced from the warehouse rather than typed in."""
    contract = contracts["net_revenue"]
    matrices, _items = challenge(
        contract, [a_hypothesis("integration_delay")], east, con
    )
    detail = matrices["integration_delay"].timing.detail
    assert "[21, 23]" in detail
    assert "2026-03-12" in detail


# ── Skips, matching 4a/4c's own convention ───────────────────────────────────


def test_a_driver_with_no_probe_sql_is_not_challenged(
    con: duckdb.DuckDBPyConnection, contracts: dict[str, KPIContract], east: ContributionTree
) -> None:
    contract = contracts["net_revenue"]
    matrices, items = challenge(contract, [a_hypothesis("seasonality")], east, con)
    assert matrices == {}
    assert items == []


def test_an_unmodelled_hypothesis_is_not_challenged(
    con: duckdb.DuckDBPyConnection, contracts: dict[str, KPIContract], east: ContributionTree
) -> None:
    contract = contracts["net_revenue"]
    matrices, items = challenge(contract, [a_hypothesis("unmodelled")], east, con)
    assert matrices == {}
    assert items == []


# ── The ledger contract every stage 4/5 item keeps ───────────────────────────


def test_every_result_cites_the_evidence_it_produced(
    con: duckdb.DuckDBPyConnection, contracts: dict[str, KPIContract], east: ContributionTree
) -> None:
    contract = contracts["net_revenue"]
    matrices, items = challenge(
        contract, [a_hypothesis("integration_delay")], east, con
    )
    by_id = {item.id: item for item in items}
    matrix = matrices["integration_delay"]
    for test_name in ("timing", "locality", "dose", "control"):
        result = getattr(matrix, test_name)
        assert len(result.evidence_ids) == 1
        assert result.evidence_ids[0] in by_id


def test_evidence_ids_are_unique_across_a_full_challenge(
    con: duckdb.DuckDBPyConnection, contracts: dict[str, KPIContract], east: ContributionTree
) -> None:
    contract = contracts["net_revenue"]
    _matrices, items = challenge(contract, all_hypotheses(contract), east, con)
    ids = [item.id for item in items]
    assert len(ids) == len(set(ids))
    assert len(items) == 16  # 4 drivers with probes * 4 tests


def test_an_inconclusive_result_is_an_uncheckable_evidence_item_with_coverage(
    con: duckdb.DuckDBPyConnection, contracts: dict[str, KPIContract], east: ContributionTree
) -> None:
    """The exact bug this guards: `TestResult.outcome` ('inconclusive') and
    `EvidenceItem.outcome` ('uncheckable') are different vocabularies — a
    literal `"uncheckable"` comparison against `TestResult.outcome` would
    never match, silently leaving `coverage` unset on every inconclusive
    item and raising `EvidenceItem`'s own validator every time."""
    contract = contracts["net_revenue"]
    _matrices, items = challenge(
        contract, [a_hypothesis("integration_delay")], east, con
    )
    dose_item = next(i for i in items if "-dose-" in i.id)
    assert dose_item.outcome == "uncheckable"
    assert dose_item.coverage is not None


def test_a_passing_result_is_a_found_evidence_item_with_no_coverage(
    con: duckdb.DuckDBPyConnection, contracts: dict[str, KPIContract], east: ContributionTree
) -> None:
    contract = contracts["net_revenue"]
    _matrices, items = challenge(
        contract, [a_hypothesis("integration_delay")], east, con
    )
    timing_item = next(i for i in items if "-timing-" in i.id)
    assert timing_item.outcome == "found"
    assert timing_item.coverage is None


def test_a_refuting_result_lands_in_contradicts_not_supports(
    con: duckdb.DuckDBPyConnection, contracts: dict[str, KPIContract], east: ContributionTree
) -> None:
    contract = contracts["net_revenue"]
    _matrices, items = challenge(contract, [a_hypothesis("competitor_offer")], east, con)
    locality_item = next(i for i in items if "-locality-" in i.id)
    assert locality_item.contradicts == ["competitor_offer"]
    assert locality_item.supports == []


def test_control_is_computed_once_and_shared_across_hypotheses(
    con: duckdb.DuckDBPyConnection, contracts: dict[str, KPIContract], east: ContributionTree
) -> None:
    """§15's formula and every worked example describe Control as a check on
    the effect's own significance, not a per-hypothesis construction — see
    the module docstring and docs/DECISIONS.md. Every hypothesis in the same
    challenge() call should see the identical Control statistic."""
    contract = contracts["net_revenue"]
    matrices, _items = challenge(contract, all_hypotheses(contract), east, con)
    statistics = {m.control.statistic for m in matrices.values()}
    assert len(statistics) == 1


# ── The strength/statistic split ─────────────────────────────────────────────


def test_locality_strength_is_the_jaccard_index_itself(
    con: duckdb.DuckDBPyConnection, contracts: dict[str, KPIContract], east: ContributionTree
) -> None:
    contract = contracts["net_revenue"]
    _matrices, items = challenge(contract, [a_hypothesis("pricing_change")], east, con)
    locality_item = next(i for i in items if "-locality-" in i.id)
    assert locality_item.strength == pytest.approx(0.04878048780487805)


def test_every_strength_is_bounded_zero_to_one(
    con: duckdb.DuckDBPyConnection, contracts: dict[str, KPIContract], east: ContributionTree
) -> None:
    """Timing's own statistic is a day-count, not a 0..1 figure — the item's
    `strength` must never be that raw number verbatim."""
    contract = contracts["net_revenue"]
    _matrices, items = challenge(contract, all_hypotheses(contract), east, con)
    for item in items:
        assert 0.0 <= item.strength <= 1.0, item


# ── The watermark, matching 4a's own convention ──────────────────────────────


def test_as_of_defaults_from_the_warehouse_watermark(
    con: duckdb.DuckDBPyConnection, contracts: dict[str, KPIContract], east: ContributionTree
) -> None:
    contract = contracts["net_revenue"]
    _matrices, items = challenge(
        contract, [a_hypothesis("integration_delay")], east, con
    )
    assert all(i.freshness_hours > 0 for i in items)


def test_a_warehouse_with_no_watermark_raises(east: ContributionTree, contracts) -> None:
    synthetic = duckdb.connect(":memory:")
    synthetic.execute("CREATE SCHEMA meta")
    synthetic.execute("CREATE TABLE meta.watermark (as_of TIMESTAMP)")
    contract = contracts["net_revenue"]
    with pytest.raises(ChallengeError, match="watermark"):
        challenge(contract, [a_hypothesis("integration_delay")], east, synthetic)


# ── An empty footprint — the deterministic path, no data at all ─────────────


@pytest.fixture
def empty_tree(east: ContributionTree) -> ContributionTree:
    return east.model_copy(
        update={
            "footprint": east.footprint.model_copy(update={"entities": {"account_id": []}}),
        }
    )


def test_every_test_is_inconclusive_with_no_accounts_in_scope(
    con: duckdb.DuckDBPyConnection, contracts: dict[str, KPIContract], empty_tree: ContributionTree
) -> None:
    contract = contracts["net_revenue"]
    matrices, items = challenge(
        contract, [a_hypothesis("integration_delay")], empty_tree, con
    )
    matrix = matrices["integration_delay"]
    assert matrix.timing.outcome == "inconclusive"
    assert matrix.locality.outcome == "inconclusive"
    assert matrix.dose.outcome == "inconclusive"
    assert matrix.control.outcome == "inconclusive"
    assert all(i.outcome == "uncheckable" for i in items)
