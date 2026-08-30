"""Ladder step 1.3 — Stage 1, Verify.

The step's verify command from §44:

    "Scenarios D and E close with `telemetry.model_calls == 0`"

Both halves are here, and the second half is asserted twice: once as a property
of the `Case` object, and once — the one that would actually catch a regression —
over the **import graph**, because `model_calls == 0` on a `Telemetry` nobody
wrote to proves nothing at all.

The rest defend the five checks individually. Three of them cannot fail on the
committed corpus (nothing in it is stale, late, or booked across a boundary), so
those tests build the condition into a copy of the warehouse. A check that has
never been seen to fail is a check nobody has tested.
"""

from __future__ import annotations

import ast
import json
import shutil
from datetime import date, timedelta
from pathlib import Path

import duckdb
import pytest

from casefile.contract import load_all
from casefile.engine.verify import VerifyError, trigger_for, verify
from casefile.models import Case, KPIContract, Telemetry

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "casefile"

pytestmark = pytest.mark.gate1


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


@pytest.fixture
def writable(warehouse: Path, tmp_path: Path) -> duckdb.DuckDBPyConnection:
    """A throwaway copy, so a test can break the data on purpose."""
    copy = tmp_path / "broken.duckdb"
    shutil.copy(warehouse, copy)
    connection = duckdb.connect(str(copy))
    yield connection
    connection.close()


def first_failure(result: object) -> str | None:
    """The check that closed the case, in §15's order."""
    return next((c.name for c in result.checks if not c.passed), None)  # type: ignore[attr-defined]


def closed_case(result: object, identifier: str) -> Case:
    """The `Case` a closing Verify produces: no decomposition, no hypotheses, no
    verdict, and — the point of the exercise — an empty `Telemetry`."""
    return Case(
        id=identifier,
        trigger=__import__("casefile.models", fromlist=["Trigger"]).Trigger(
            kpi="net_revenue", period="2026-03", delta=-1.0, delta_relative=-0.01
        ),
        verification=result,  # type: ignore[arg-type]
        priority=0.0,
        telemetry=Telemetry(),
    )


# ── The ladder's verify command ───────────────────────────────────────────────


@pytest.mark.parametrize("scenario,expected", [("D", "artefact"), ("E", "definition_drift")])
def test_the_not_real_scenarios_close_at_verify_with_no_model_calls(
    con: duckdb.DuckDBPyConnection,
    contracts: dict[str, KPIContract],
    sealed: dict[str, dict],
    scenario: str,
    expected: str,
) -> None:
    """§25 D and E. Both close here, for the reason the answer sheet seals — and
    *which* reason matters: a case that closed for the right answer by accident
    would grade identically to one that reasoned."""
    truth = sealed[scenario]
    result = verify(con, contracts[truth["kpi"]], truth["period"], truth["dimensions"])

    assert result.passed is False
    assert first_failure(result) == expected == truth["failing_check"]

    case = closed_case(result, f"case-{scenario}")
    assert case.telemetry.model_calls == 0 == truth["expected_model_calls"]
    assert case.decomposition is None and case.verdict is None


def test_verify_cannot_reach_the_llm_layer_at_all(
    con: duckdb.DuckDBPyConnection, contracts: dict[str, KPIContract]
) -> None:
    """The assertion that would actually catch a regression.

    `telemetry.model_calls == 0` on a `Telemetry` the test constructed empty is
    true whatever Verify does. This walks the real import graph from
    `casefile.engine.verify` and asserts `casefile.llm` is not reachable from it
    — so *"a failed case closes with zero model calls"* (§15) is a property of
    the code rather than of the fixture.
    """
    reached: set[str] = set()
    frontier = ["engine.verify"]

    while frontier:
        module = frontier.pop()
        if module in reached:
            continue
        reached.add(module)

        path = SRC / (module.replace(".", "/") + ".py")
        if not path.exists():
            path = SRC / module.replace(".", "/") / "__init__.py"
        if not path.exists():
            continue

        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.ImportFrom) and node.module:
                names.append(node.module)
            elif isinstance(node, ast.Import):
                names += [alias.name for alias in node.names]
            for name in names:
                if name.startswith("casefile."):
                    frontier.append(name[len("casefile."):])

    assert reached, "the import walk found nothing, so it is asserting nothing"
    assert not any(module.startswith("llm") for module in reached), (
        f"Verify can reach the LLM layer through {sorted(reached)}"
    )


def test_the_headline_case_opens_with_every_check_green(
    con: duckdb.DuckDBPyConnection,
    contracts: dict[str, KPIContract],
    sealed: dict[str, dict],
) -> None:
    """§25 A. The converse of the two above — a Verify that closed everything
    would pass both of those and be useless."""
    truth = sealed["A"]
    result = verify(con, contracts[truth["kpi"]], truth["period"], truth["dimensions"])

    assert result.passed is True
    assert [c.name for c in result.checks] == [
        "freshness", "completeness", "definition_drift", "artefact", "materiality",
    ]
    assert all(check.passed for check in result.checks)
    assert result.provisional is False
    assert result.baseline == "own"
    assert result.confidence_ceiling is None


def test_all_five_checks_are_reported_even_after_one_fails(
    con: duckdb.DuckDBPyConnection, contracts: dict[str, KPIContract]
) -> None:
    """A case that closes saying only the first of three reasons sends somebody
    to fix the wrong one. §25 E fails drift *and* single-record dominance, and
    the result carries both."""
    result = verify(con, contracts["net_revenue"], "2026-02", {"region": "North"})

    assert len(result.checks) == 5
    failed = [c.name for c in result.checks if not c.passed]
    assert "definition_drift" in failed and len(failed) >= 2


# ── 1 · Freshness — the check that does not close the case ───────────────────


def test_a_stale_source_makes_the_case_provisional_rather_than_closing_it(
    writable: duckdb.DuckDBPyConnection, contracts: dict[str, KPIContract]
) -> None:
    """§15: *"a stale source marks the case provisional and caps confidence"* —
    and when the awaited watermark lands the orchestrator re-runs it. Closing
    the case instead would throw away a real movement because a batch was late,
    which is the opposite of the product."""
    writable.execute(
        "UPDATE meta.watermark SET watermark = watermark - INTERVAL 40 HOUR "
        "WHERE source = 'billing'"
    )
    result = verify(writable, contracts["net_revenue"], "2026-04", {"region": "East"})

    assert result.passed is True, "a late batch is not a reason to drop a real case"
    assert result.provisional is True
    assert result.confidence_ceiling == "likely"
    assert result.freshness_hours > 26
    assert first_failure(result) == "freshness"


def test_a_fresh_source_leaves_the_ceiling_alone(
    con: duckdb.DuckDBPyConnection, contracts: dict[str, KPIContract]
) -> None:
    result = verify(con, contracts["net_revenue"], "2026-04", {"region": "East"})
    assert 0 < result.freshness_hours <= contracts["net_revenue"].refresh.sla_hours


# ── 2 · Completeness ─────────────────────────────────────────────────────────


def test_rows_still_landing_close_the_case(
    writable: duckdb.DuckDBPyConnection, contracts: dict[str, KPIContract]
) -> None:
    """Nothing in the committed corpus is late, so the condition is built here.
    A check nobody has seen fail is a check nobody has tested."""
    writable.execute(
        "UPDATE billing.invoice_line SET _ingested_at = _ingested_at + INTERVAL 20 DAY "
        "WHERE invoice_date BETWEEN '2026-04-01' AND '2026-04-30' AND line_no % 5 = 0"
    )
    result = verify(writable, contracts["net_revenue"], "2026-04", {"region": "East"})

    assert result.passed is False
    assert first_failure(result) == "completeness"


def test_a_source_whose_event_time_is_its_arrival_time_has_no_lag_to_measure(
    con: duckdb.DuckDBPyConnection, contracts: dict[str, KPIContract]
) -> None:
    """§22 gives `product_ops` no ingest column, and for a ≤15-minute stream that
    is the honest schema rather than an omission. Treating the missing column as
    zero records would close every ticket case as incomplete."""
    result = verify(con, contracts["p1_resolution_time"], "2026-04", {"region": "East"})
    completeness = next(c for c in result.checks if c.name == "completeness")

    assert completeness.passed is True
    assert "event time" in completeness.detail


# ── 3 · Definition drift ─────────────────────────────────────────────────────


def test_the_drift_check_only_recomputes_boundary_periods(
    con: duckdb.DuckDBPyConnection, contracts: dict[str, KPIContract]
) -> None:
    """Away from a boundary the adjacent epoch *is* the current one, so the
    recomputation is the same query and the check would pass on evidence it
    never gathered. Saying so is the difference between a check and a stub."""
    away = verify(con, contracts["net_revenue"], "2026-04", {"region": "East"})
    check = next(c for c in away.checks if c.name == "definition_drift")

    assert check.passed is True
    assert check.statistic is None
    assert "nothing to recompute" in check.detail


def test_a_step_that_survives_a_consistent_definition_is_business_not_drift(
    con: duckdb.DuckDBPyConnection, contracts: dict[str, KPIContract]
) -> None:
    """The other half of §25 E, and the one that stops the check refuting
    everything: East's February also straddles the boundary, and its movement is
    small either way — so drift must *not* be the story of every boundary
    period."""
    north = verify(con, contracts["net_revenue"], "2026-02", {"region": "North"})
    drift = next(c for c in north.checks if c.name == "definition_drift")

    assert drift.passed is False
    assert drift.statistic is not None
    assert abs(drift.statistic) < contracts["net_revenue"].materiality.relative


# ── 4 · Artefacts ────────────────────────────────────────────────────────────


def test_one_credit_note_being_most_of_the_movement_closes_the_case(
    con: duckdb.DuckDBPyConnection,
    contracts: dict[str, KPIContract],
    sealed: dict[str, dict],
) -> None:
    """§25 D, read through the check that catches it: *"one invoice **is** the
    movement."*"""
    truth = sealed["D"]
    result = verify(con, contracts["net_revenue"], truth["period"], truth["dimensions"])
    artefact = next(c for c in result.checks if c.name == "artefact")

    assert artefact.passed is False
    assert artefact.statistic is not None
    assert artefact.statistic == pytest.approx(0.71, abs=0.03)
    assert artefact.statistic > contracts["net_revenue"].data_quality.max_single_record_share


def test_the_headline_movement_is_not_one_big_invoice(
    con: duckdb.DuckDBPyConnection, contracts: dict[str, KPIContract]
) -> None:
    """§10: *"largest single invoice is 9% of the movement"*. The measured figure
    on the generated corpus is 14%; §35.2 asserts ranges, and what has to hold is
    that it stays well under the 35% threshold."""
    result = verify(con, contracts["net_revenue"], "2026-04", {"region": "East"})
    artefact = next(c for c in result.checks if c.name == "artefact")

    assert artefact.passed is True
    assert artefact.statistic is not None
    assert 0.05 <= artefact.statistic <= 0.25


def test_records_booked_across_the_period_boundary_are_an_artefact(
    writable: duckdb.DuckDBPyConnection, contracts: dict[str, KPIContract]
) -> None:
    """*"One large invoice slipping across a month boundary"* — §2.3's third way
    an alarming move turns out not to be real."""
    writable.execute(
        "UPDATE billing.invoice_line SET _ingested_at = _ingested_at - INTERVAL 45 DAY "
        "WHERE invoice_date BETWEEN '2026-04-01' AND '2026-04-30' AND is_recurring = 1"
    )
    result = verify(writable, contracts["net_revenue"], "2026-04", {"region": "East"})
    artefact = next(c for c in result.checks if c.name == "artefact")

    assert artefact.passed is False
    assert "boundary" in artefact.detail


def test_a_median_kpi_has_no_single_record_share(
    con: duckdb.DuckDBPyConnection, contracts: dict[str, KPIContract]
) -> None:
    """Dividing the longest ticket's duration by a movement measured in the
    median's own units is not a smaller version of the same question — it is a
    different question with no meaning, and it produced 371,908% before this
    branch existed."""
    result = verify(con, contracts["p1_resolution_time"], "2026-04", {"region": "East"})
    artefact = next(c for c in result.checks if c.name == "artefact")

    assert artefact.passed is True
    assert artefact.statistic is None
    assert "MEDIAN" in artefact.detail


# ── 5 · Materiality and the sparse-history path ──────────────────────────────


def test_a_kpi_with_less_than_two_seasonal_cycles_borrows_a_peer_baseline(
    con: duckdb.DuckDBPyConnection, contracts: dict[str, KPIContract]
) -> None:
    """§25 C. `product_ops` has eight months against a 365-day seasonal period,
    so there is no own baseline to fit — §15 borrows one from peer segments and
    caps confidence at Likely *regardless of what the tests later find*."""
    result = verify(con, contracts["p1_resolution_time"], "2026-04", {"region": "East"})

    assert result.baseline == "borrowed"
    assert result.confidence_ceiling == "likely"
    assert result.robust_z is None, "there is no seasonal fit, so there is no z to report"
    assert result.persistence is None


def test_a_sparse_kpi_with_no_peers_abstains_instead_of_inventing_a_baseline(
    con: duckdb.DuckDBPyConnection, contracts: dict[str, KPIContract]
) -> None:
    """The whole-company view of a sparse KPI has no peer segment to borrow
    from — there is nothing beside it to compare against.

    The tempting fallback is the KPI's own trend, which is precisely the thing
    that does not exist yet: eight months against a 365-day cycle. Fitting one
    anyway would produce a confident number out of no history at all, so the
    check fails and says why.
    """
    result = verify(con, contracts["p1_resolution_time"], "2026-04")
    materiality = next(c for c in result.checks if c.name == "materiality")

    assert result.passed is False
    assert materiality.passed is False
    assert materiality.statistic is None
    assert "no baseline" in materiality.detail


def test_a_kpi_with_full_history_uses_its_own_baseline(
    con: duckdb.DuckDBPyConnection, contracts: dict[str, KPIContract]
) -> None:
    result = verify(con, contracts["net_revenue"], "2026-04", {"region": "East"})

    assert result.baseline == "own"
    assert result.robust_z is not None and result.robust_z < -3.0
    assert result.persistence is not None and result.persistence >= 2


def test_the_ceiling_only_ever_lowers(
    writable: duckdb.DuckDBPyConnection, contracts: dict[str, KPIContract]
) -> None:
    """§9: *"confidence ceilings (applied after scoring; they only ever lower)"*.
    A sparse baseline and a stale source together must not cancel out."""
    writable.execute(
        "UPDATE meta.watermark SET watermark = watermark - INTERVAL 5 HOUR "
        "WHERE source = 'product_ops'"
    )
    result = verify(writable, contracts["p1_resolution_time"], "2026-04", {"region": "East"})

    assert result.provisional is True
    assert result.baseline == "borrowed"
    assert result.confidence_ceiling == "likely"


# ── The trigger, and the edges ───────────────────────────────────────────────


def test_the_trigger_carries_the_movement_that_raised_the_alert(
    con: duckdb.DuckDBPyConnection, contracts: dict[str, KPIContract]
) -> None:
    """§10's alert line: *"Net Revenue · East region · down 8.0% month on month ·
    ₹2.4 Cr"*."""
    trigger = trigger_for(con, contracts["net_revenue"], "2026-04", {"region": "East"})

    assert trigger.kpi == "net_revenue"
    assert trigger.period == "2026-04"
    assert trigger.dimensions == {"region": "East"}
    assert trigger.delta_relative == pytest.approx(-0.08, abs=0.01)
    assert trigger.delta < -20_000_000


def test_a_period_with_nothing_before_it_cannot_be_verified(
    con: duckdb.DuckDBPyConnection, contracts: dict[str, KPIContract]
) -> None:
    """The first period of history has no previous period, so there is no
    movement. Returning zero would report "no change" for a month nobody has a
    comparison for."""
    with pytest.raises(VerifyError, match="no previous period"):
        verify(con, contracts["net_revenue"], "2022-01", {"region": "East"})


def test_verify_reads_the_simulated_present_not_the_wall_clock(
    con: duckdb.DuckDBPyConnection, contracts: dict[str, KPIContract]
) -> None:
    """§24's whole point: a demo recorded today still says the same thing next
    month. `as_of` comes from `meta.watermark`, which Stage 0 stamped."""
    stored = con.execute("SELECT max(as_of) FROM meta.watermark").fetchone()
    assert stored is not None

    result = verify(con, contracts["net_revenue"], "2026-04", {"region": "East"})
    row = con.execute(
        "SELECT watermark FROM meta.watermark WHERE source = 'billing'"
    ).fetchone()
    assert row is not None

    expected = (stored[0] - row[0]).total_seconds() / 3600
    assert result.freshness_hours == pytest.approx(expected, abs=0.01)
    assert stored[0].date() == date(2026, 5, 1)
    assert stored[0] - row[0] < timedelta(hours=26)
