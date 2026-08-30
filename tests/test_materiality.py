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
import math
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


def test_exactly_three_cases_open_across_the_whole_corpus(
    con: duckdb.DuckDBPyConnection, contract: KPIContract, sealed: dict[str, dict]
) -> None:
    """Four regions x twelve periods = 48 chances to cry wolf.

    A gate that opens nothing is useless and a gate that opens everything is
    worse, so the interesting number is not "does A fire" but "what else does".
    Nothing else does: the three cases the gate opens are the three the answer
    sheet seals, at the region and period it names for each.
    """
    periods = calendar_months(FIRST, LAST)
    opened = {
        (region, period)
        for region in REGIONS
        for period in periods[-12:]
        if judge(con, contract, region, period).passed  # type: ignore[attr-defined]
    }

    expected = {
        (scenario["dimensions"]["region"], scenario["period"])
        for scenario in sealed.values()
        if scenario["kpi"] == "net_revenue"
    }
    assert opened == expected
    assert len(opened) == 3


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
    for earlier in scores[-3:-1]:
        assert -3.0 < earlier < -1.0, "Feb and Mar were drifting, not breaking"

    assert judge(con, contract, "East", "2026-04").persistence >= 2  # type: ignore[attr-defined]


def test_the_seasonal_fit_does_not_swallow_the_movement(
    con: duckdb.DuckDBPyConnection, contract: KPIContract
) -> None:
    """Kills the "let STL use its default seasonal smoother" mutation.

    Three observations per seasonal phase is enough for a degree-one local fit
    to interpolate them, so one bad April teaches the model that April is a weak
    month and the residual comes back near zero — a -₹2.6 Cr movement scoring
    **+0.66**. The sign alone is the tell: whatever else is true, a large fall
    cannot produce a positive z.
    """
    verdict = judge(con, contract, "East", "2026-04")

    assert verdict.delta < 0  # type: ignore[attr-defined]
    assert verdict.robust_z < 0, "a fall that scores positive means the fit absorbed it"  # type: ignore[attr-defined]


# ── The four conditions are all required ─────────────────────────────────────


def test_a_movement_that_is_large_but_ordinary_is_not_material() -> None:
    """The business half without the statistical half. This series swings around
    by 7% most months; doing it once more is not news, however much a relative
    threshold on its own would like it to be."""
    series = [100.0 + 10.0 * math.sin(i * 1.7) for i in range(36)]
    verdict = assess(series, 12, relative=0.03, absolute=1.0, z_threshold=3.0, min_persistence=2)

    assert abs(series[-1] - series[-2]) / series[-2] > 0.03, "large enough to tempt the gate"
    assert not verdict.passed
    assert "robust z" in verdict.detail


def test_a_movement_that_is_unusual_but_tiny_is_not_material() -> None:
    """The statistical half without the business half — the false-alarm engine
    of every anomaly detector that ships with one threshold."""
    series = [100.0] * 35 + [96.0]
    verdict = assess(
        series, 12, relative=0.03, absolute=1_000_000.0, z_threshold=3.0, min_persistence=1
    )

    assert not verdict.passed
    assert "absolute threshold" in verdict.detail


def test_the_detail_names_every_condition_that_failed_not_just_the_first() -> None:
    """Verify writes this into `VerificationCheck.detail`, and a case that closes
    saying only the first of three reasons sends someone to fix the wrong one."""
    series = [100.0] * 35 + [100.5]
    verdict = assess(
        series, 12, relative=0.03, absolute=1_000_000.0, z_threshold=3.0, min_persistence=2
    )

    assert not verdict.passed
    assert verdict.detail.count(";") >= 1


def test_materiality_needs_something_to_compare_against() -> None:
    with pytest.raises(ValueError, match="previous period"):
        assess([1.0], 12, relative=0.03, absolute=1.0, z_threshold=3.0, min_persistence=1)
