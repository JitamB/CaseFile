"""Ladder step 1.1 — STL, robust z, PVM.

The step's verify command from §44:

    "Each function matches a hand-computed value in the test"

So every expected number below is arithmetic written out in the test body. A
test that recomputes the function's own logic to check the function proves only
that the code is self-consistent, which it always is.
"""

from __future__ import annotations

import math
import statistics

import pytest

from casefile.stats.pvm import split
from casefile.stats.robust_z import MAD_TO_SIGMA, persistence, robust_z
from casefile.stats.stl import decompose

pytestmark = pytest.mark.gate1


# ── Robust z — §23 ────────────────────────────────────────────────────────────


def test_robust_z_matches_the_hand_computed_value() -> None:
    """series   [2, 4, 4, 4, 5, 5, 7, 9]
    median      4.5
    deviations  [2.5, 0.5, 0.5, 0.5, 0, 0, 2.5, 4.5] → sorted median 0.5
    scale       1.4826 x 0.5 = 0.7413
    z(9)        (9 - 4.5) / 0.7413 = 6.0704...
    """
    zs = robust_z([2, 4, 4, 4, 5, 5, 7, 9])

    assert zs[-1] == pytest.approx(4.5 / (1.4826 * 0.5), rel=1e-12)
    assert zs[-1] == pytest.approx(6.070417, abs=1e-6)
    # The two observations sitting on the median are exactly unremarkable.
    assert zs[4] == pytest.approx(0.5 / 0.7413, rel=1e-12)


def test_the_scale_constant_is_the_one_that_makes_three_mean_three() -> None:
    """1.4826 is not decoration: it is what makes MAD estimate sigma, and
    therefore what lets §23's `|z| > 3` keep its ordinary reading. Against a
    large normal sample the robust z and the plain z agree."""
    assert MAD_TO_SIGMA == pytest.approx(1.4826)

    rng = __import__("random").Random(11)
    sample = [rng.gauss(0.0, 1.0) for _ in range(4000)]
    scaled = robust_z(sample)
    plain = statistics.stdev(sample)

    assert max(abs(z) for z in scaled) == pytest.approx(
        max(abs(v - statistics.median(sample)) for v in sample) / plain, rel=0.05
    )


def test_an_outlier_does_not_hide_behind_its_own_influence() -> None:
    """The point of a robust estimator. One huge value inflates a standard
    deviation enough to look ordinary against it; it moves a median by nothing.
    §35.2's headline movement is exactly this shape."""
    series = [100.0] * 20 + [300.0]

    plain = (300.0 - statistics.mean(series)) / statistics.stdev(series)
    robust = robust_z(series)[-1]

    assert plain < 5.0, "a classical z calls a tripling barely remarkable"
    assert robust > 15.0
    assert robust > 3 * plain


def test_a_constant_series_has_no_anomalies_rather_than_nan() -> None:
    assert robust_z([7.0] * 6) == (0.0,) * 6


def test_mad_of_zero_falls_back_rather_than_dividing_by_it() -> None:
    """More than half the observations identical drives MAD to zero — a quiet
    KPI with two spikes. `inf` for every spike would be useless, and dropping
    the check would be worse.

    series      [1, 1, 1, 1, 5]     median 1, MAD 0
    mean |dev|  4/5 = 0.8           scale 1.2533 x 0.8 = 1.00264
    z(5)        4 / 1.00264 = 3.98946...
    """
    assert robust_z([1, 1, 1, 1, 5])[-1] == pytest.approx(4 / (1.2533 * 0.8), rel=1e-12)


def test_robust_z_refuses_an_empty_series() -> None:
    with pytest.raises(ValueError, match="empty"):
        robust_z([])


# ── Persistence — the second half of §23's materiality rule ───────────────────


def test_persistence_counts_back_from_the_last_period() -> None:
    assert persistence([0.0, -1.0, -4.0, -5.0], 3.0) == 2
    assert persistence([-9.0, -8.0, -7.0], 3.0) == 3


def test_a_single_period_past_the_threshold_is_a_spike_not_a_movement() -> None:
    """§23 requires persistence >= 2 precisely so this case does not open a
    case. Materiality is `|z| > 3 AND persistence >= 2`, not either."""
    assert persistence([0.0, 0.0, -4.0], 3.0) == 1


def test_a_rebound_has_not_persisted() -> None:
    """A fall then a rise is a reversion, not two periods of trouble. Counting
    |z| alone would score this 2 and open a case on a metric that recovered."""
    assert persistence([-4.0, 5.0], 3.0) == 1


def test_a_quiet_last_period_ends_the_run_regardless_of_history() -> None:
    assert persistence([-9.0, -9.0, -0.2], 3.0) == 0


# ── PVM — §23 ─────────────────────────────────────────────────────────────────


def test_pvm_matches_the_hand_computed_value() -> None:
    """one item, q 10 -> 12 at a price of 5.00 -> 6.00

    price   (6 - 5) x 10        =  10
    volume   5 x (12 - 10)      =  10
    mix     (6 - 5) x (12 - 10) =   2
    total    12x6 - 10x5 = 72 - 50 = 22 = 10 + 10 + 2
    """
    result = split({"PRD-CORE": (10.0, 5.0)}, {"PRD-CORE": (12.0, 6.0)})

    assert result.pvm.price == pytest.approx(10.0)
    assert result.pvm.volume == pytest.approx(10.0)
    assert result.pvm.mix == pytest.approx(2.0)
    assert result.total_delta == pytest.approx(22.0)
    assert result.residual == pytest.approx(0.0, abs=1e-9)


def test_the_three_parts_sum_to_the_whole_on_a_mixed_basket() -> None:
    """The identity is what Stage 2's "it cannot be wrong" rests on, so it is
    asserted on a basket with a rise, a fall, a new item and a dropped one."""
    before = {"a": (10.0, 5.0), "b": (4.0, 100.0), "gone": (3.0, 20.0)}
    after = {"a": (8.0, 5.5), "b": (9.0, 90.0), "new": (2.0, 45.0)}

    result = split(before, after)
    by_hand = (8 * 5.5 + 9 * 90 + 2 * 45) - (10 * 5 + 4 * 100 + 3 * 20)

    assert result.total_delta == pytest.approx(by_hand)
    assert result.pvm.price + result.pvm.volume + result.pvm.mix == pytest.approx(by_hand)
    assert result.residual == pytest.approx(0.0, abs=1e-9)


def test_a_new_item_is_assortment_not_price_or_volume() -> None:
    """It has no previous price to have changed and no previous quantity to have
    grown. Putting it in volume would report a price-flat launch as organic
    growth of an item that did not exist."""
    result = split({}, {"new": (4.0, 25.0)})

    assert result.pvm.price == 0.0
    assert result.pvm.volume == 0.0
    assert result.pvm.mix == pytest.approx(100.0)


def test_a_pure_price_rise_lands_entirely_in_price() -> None:
    result = split({"a": (10.0, 5.0)}, {"a": (10.0, 5.5)})
    assert result.pvm.price == pytest.approx(5.0)
    assert (result.pvm.volume, result.pvm.mix) == (0.0, 0.0)


def test_an_unchanged_basket_moves_nothing() -> None:
    basket = {"a": (10.0, 5.0), "b": (2.0, 3.0)}
    result = split(basket, dict(basket))
    assert (result.pvm.price, result.pvm.volume, result.pvm.mix) == (0.0, 0.0, 0.0)
    assert result.total_delta == 0.0


# ── STL — §23 ─────────────────────────────────────────────────────────────────


def _seasonal_series(n: int = 48) -> list[float]:
    """Trend 100 + 2t, a 12-period seasonal swing of amplitude 20, no noise."""
    return [100.0 + 2.0 * t + 20.0 * math.sin(2 * math.pi * t / 12) for t in range(n)]


def test_the_decomposition_reconstructs_the_series_exactly() -> None:
    """`y_t = T_t + S_t + R_t` is §23's definition, not an approximation of it.
    Everything downstream reads the residual, so a decomposition that lost a
    little of the series each period would bias every z quietly."""
    series = _seasonal_series()
    parts = decompose(series, period=12)

    for t, y in enumerate(series):
        assert parts.trend[t] + parts.seasonal[t] + parts.residual[t] == pytest.approx(y)


def test_a_clean_seasonal_series_leaves_almost_no_residual() -> None:
    """The whole reason Stage 1 runs STL first: a December fall against a
    December peak must not read as an anomaly.

    Note what is *not* asserted here — that robust z on the residual stays under
    3. Robust z is scale-free, so on a residual that is pure numerical noise it
    reports large multiples of nothing at all. The meaningful claim is that STL
    absorbed the swing: a 40-unit seasonal cycle leaves under a unit behind.
    Whether a *real* movement survives that is the next test, and it is the one
    that would catch an over-eager smoother.
    """
    parts = decompose(_seasonal_series(), period=12)
    interior = parts.residual[6:-6]  # the endpoints carry the smoother's edge effect
    swing = max(parts.seasonal) - min(parts.seasonal)

    assert max(abs(r) for r in interior) < 1.0
    assert max(abs(r) for r in interior) < 0.05 * swing


def test_the_seasonal_component_recovers_the_swing_that_was_put_in() -> None:
    parts = decompose(_seasonal_series(), period=12)
    swing = max(parts.seasonal) - min(parts.seasonal)
    assert swing == pytest.approx(40.0, rel=0.1)  # 2 x amplitude 20


def test_the_trend_component_recovers_the_slope_that_was_put_in() -> None:
    parts = decompose(_seasonal_series(), period=12)
    per_period = (parts.trend[-7] - parts.trend[6]) / (len(parts) - 13)
    assert per_period == pytest.approx(2.0, rel=0.1)


def test_a_real_step_survives_the_decomposition_as_a_residual() -> None:
    """The converse of the seasonality test, and the one that matters: a genuine
    8% fall in the last period must reach robust z as an outlier rather than be
    absorbed into the trend."""
    series = _seasonal_series()
    series[-1] *= 0.92

    parts = decompose(series, period=12)
    assert abs(robust_z(parts.residual)[-1]) > 3.0


def test_a_one_off_shock_is_not_learnt_as_seasonality() -> None:
    """Why the fit is `robust=True`, and the only test that can tell.

    A non-robust LOESS lets a single shock contaminate the seasonal component at
    every observation sharing its phase — so the anomaly teaches the model to
    expect itself, and next year's identical fall reads as normal. Worse for us
    now: part of the shock is absorbed, so the residual understates it and the
    materiality gate sees a smaller movement than actually happened.

    The shock here is -60 at t = 24, a position shared with t = 12 and t = 36.
    """
    series = _seasonal_series()
    series[24] -= 60.0

    parts = decompose(series, period=12)
    same_phase = [parts.seasonal[i] for i in (12, 24, 36)]

    assert parts.residual[24] == pytest.approx(-60.0, abs=1.0), (
        "the shock must survive into the residual whole, not be part-absorbed"
    )
    assert max(abs(v) for v in same_phase) < 1.0, (
        "one bad month has been learnt as a seasonal expectation"
    )


def test_stl_refuses_a_series_shorter_than_two_cycles() -> None:
    """Scenario C. `product_ops` has eight months against a 365-day seasonal
    period, and §15's answer is a peer-borrowed baseline with a ceiling — not an
    STL fitted to half a cycle and quietly believed."""
    with pytest.raises(ValueError, match="two full cycles"):
        decompose(_seasonal_series(n=18), period=12)


def test_stl_refuses_a_period_that_is_not_a_cycle() -> None:
    with pytest.raises(ValueError, match="not a cycle"):
        decompose(_seasonal_series(), period=1)
