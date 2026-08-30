"""§23's materiality rule, measured over the whole corpus.

This file exists because of what three surviving mutations showed at ladder step
1.2.9: the generator's demand shock, STL's flat seasonal profile and
`persistence`'s hysteresis are each **individually necessary** for §25 A to open
at all, and nothing tested any of them. Each is now pinned by a measurement
rather than by a comment.

The headline measurement is `test_exactly_three_cases_open_across_the_whole_corpus`:
four regions x the trailing twelve periods is 48 chances to cry wolf, and the
gate takes exactly three of them — scenarios A, D and E.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import duckdb
import pytest

from casefile.contract import load
from casefile.metric import calendar_months, value
from casefile.models import KPIContract
from casefile.stats.materiality import assess
from casefile.stats.robust_z import robust_z
from casefile.stats.stl import decompose

ROOT = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.gate1

#: The corpus spans 2023-05 to 2026-04 (§22's 36 months).
FIRST, LAST = date(2023, 5, 1), date(2026, 4, 30)
REGIONS = ("East", "West", "North", "APAC")


@pytest.fixture(scope="module")
def contract() -> KPIContract:
    return load(ROOT / "contracts" / "net_revenue.yaml")


@pytest.fixture(scope="module")
def con(warehouse: Path) -> duckdb.DuckDBPyConnection:
    connection = duckdb.connect(str(warehouse), read_only=True)
    yield connection
    connection.close()


@pytest.fixture(scope="module")
def sealed(generated: Path) -> dict[str, dict]:
    """`tests/` only — §30 rule 3."""
    return json.loads((generated / "ground_truth.json").read_text(encoding="utf-8"))["scenarios"]


def judge(
    con: duckdb.DuckDBPyConnection, contract: KPIContract, region: str, upto: str
) -> object:
    periods = calendar_months(FIRST, LAST)
    series = [
        value(con, contract, p, {"region": region}) for p in periods[: periods.index(upto) + 1]
    ]
    assert all(v is not None for v in series)
    m = contract.materiality
    return assess(
        [v for v in series if v is not None],
        period=12,
        relative=m.relative,
        absolute=m.absolute,
        z_threshold=m.z_threshold,
        min_persistence=m.min_persistence,
    )


# ── The headline measurement ──────────────────────────────────────────────────


def test_only_four_movements_in_the_whole_corpus_are_material(
    con: duckdb.DuckDBPyConnection, contract: KPIContract, sealed: dict[str, dict]
) -> None:
    """Four regions x twelve periods = 48 chances to cry wolf.

    A gate that opens nothing is useless and a gate that opens everything is
    worse, so the interesting number is not "does A fire" but "what else does".
    Four movements clear it. Three are the sealed scenarios; the fourth is West's
    April, which looks like a recovery of exactly the size of March's refund
    batch — a real movement in the arithmetic that Verify then closes as the
    artefact it is (`tests/test_verify.py`).
    """
    periods = calendar_months(FIRST, LAST)
    opened = {
        (region, period)
        for region in REGIONS
        for period in periods[-12:]
        if judge(con, contract, region, period).passed  # type: ignore[attr-defined]
    }

    sealed_movements = {
        (scenario["dimensions"]["region"], scenario["period"])
        for scenario in sealed.values()
        if scenario["kpi"] == "net_revenue"
    }
    assert sealed_movements <= opened
    assert opened == sealed_movements | {("West", "2026-04")}


# ── Scenario A — the one the whole project rests on ──────────────────────────


def test_the_headline_movement_is_material(
    con: duckdb.DuckDBPyConnection, contract: KPIContract
) -> None:
    verdict = judge(con, contract, "East", "2026-04")

    assert verdict.passed  # type: ignore[attr-defined]
    assert verdict.delta_relative == pytest.approx(-0.08, abs=0.01)  # type: ignore[attr-defined]
    assert verdict.robust_z < -contract.materiality.z_threshold  # type: ignore[attr-defined]
    assert verdict.persistence >= contract.materiality.min_persistence  # type: ignore[attr-defined]


def test_the_z_scale_stays_a_number_a_person_could_read(
    con: duckdb.DuckDBPyConnection, contract: KPIContract
) -> None:
    """Kills the "drop the demand shock" mutation.

    46 accounts x ~1,800 usage lines averages every per-line wobble away, so
    without a shared regional shock the aggregate series is nearly deterministic:
    STL fits it exactly, MAD collapses towards zero, and the case file reports a
    robust z with six digits in it. The movement is still found — but "z =
    −26,789,781" on a page a judge reads is a broken instrument, not a finding.
    """
    periods = calendar_months(FIRST, LAST)
    scores = [judge(con, contract, "East", p).robust_z for p in periods[-13:]]  # type: ignore[attr-defined]

    assert abs(scores[-1]) > 10.0, "the real movement must be unmistakable"
    assert max(abs(z) for z in scores) < 100.0, "the residual scale has collapsed"


def test_the_movement_had_already_begun_before_the_period_it_broke_in(
    con: duckdb.DuckDBPyConnection, contract: KPIContract
) -> None:
    """Kills the "drop the hysteresis" mutation, and explains why it is there.

    A step change has exactly one period at 3 sigma — the one it happened in.
    Requiring two would make §23's own rule unsatisfiable for the case it exists
    to catch. Read from April, February and March sit below expectation but well
    inside 3 sigma, which is exactly what `persistence`'s lower continuation bar
    is for.
    """
    periods = calendar_months(FIRST, LAST)
    series = [
        value(con, contract, p, {"region": "East"})
        for p in periods[: periods.index("2026-04") + 1]
    ]
    scores = robust_z(decompose([v for v in series if v is not None], 12).residual)

    assert scores[-1] < -3.0, "April broke"
    assert all(z < 0 for z in scores[-3:]), "Feb and Mar were already below expectation"
    assert abs(scores[-1]) > 3 * max(abs(z) for z in scores[-3:-1]), "April is the break"

    assert judge(con, contract, "East", "2026-04").persistence >= 2  # type: ignore[attr-defined]


def test_each_of_the_four_conditions_rejects_something_in_the_real_corpus(
    con: duckdb.DuckDBPyConnection, contract: KPIContract
) -> None:
    """Why §23's gate has four parts, measured rather than argued.

    The 2026-02 epoch boundary steps *every* region's series down by the discount
    rate, so the same event meets the gate three times and is turned away twice —
    each time by a different condition:

    ``East 2026-02``  z −12.8, −5.30%  loud and large, but **no run behind it**
    ``East 2026-03``  z −12.7, −0.97%  loud with a run, but **commercially tiny**
    ``North 2026-02`` z  −6.4, −4.94%  loud, a run, and large → scenario E opens

    A detector with one threshold would have raised all three. Two of them are
    the same definition change seen from a different angle, and sending somebody
    to explain either would be sending them to explain arithmetic.
    """
    february = judge(con, contract, "East", "2026-02")
    assert abs(february.robust_z) > contract.materiality.z_threshold  # type: ignore[attr-defined]
    assert abs(february.delta_relative) > contract.materiality.relative  # type: ignore[attr-defined]
    assert february.persistence < contract.materiality.min_persistence  # type: ignore[attr-defined]
    assert not february.passed  # type: ignore[attr-defined]

    march = judge(con, contract, "East", "2026-03")
    assert abs(march.robust_z) > contract.materiality.z_threshold  # type: ignore[attr-defined]
    assert march.persistence >= contract.materiality.min_persistence  # type: ignore[attr-defined]
    assert abs(march.delta_relative) < contract.materiality.relative  # type: ignore[attr-defined]
    assert not march.passed  # type: ignore[attr-defined]

    assert judge(con, contract, "North", "2026-02").passed  # type: ignore[attr-defined]
