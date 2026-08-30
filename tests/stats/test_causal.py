"""Ladder step 1.2 — change-point, Jaccard, Spearman, DiD + placebo rank.

The step's verify command from §44:

    "Same [each function matches a hand-computed value]. Placebo rank returns
     the real effect's position among 6 placebos"

Every expected number below is arithmetic written out. Three of the four tests
are the ones that kill §25's decoys, so the constants here are the ones §10 and
§35.2 quote — J = 0.05 for pricing, n = 2 for dose, rank 1 of 7 for control.
"""

from __future__ import annotations

import random
from datetime import timedelta
from pathlib import Path

import duckdb
import pytest

from casefile.data.scm import INTEGRATION_ONSET
from casefile.stats.changepoint import changepoints, onset
from casefile.stats.correlation import MIN_PAIRS, spearman
from casefile.stats.did import MIN_CONTROLS, did, placebo_rank
from casefile.stats.overlap import jaccard

pytestmark = pytest.mark.gate1


# ── Locality: Jaccard — §15 S5, and how the pricing decoy dies ────────────────


def test_jaccard_matches_the_hand_computed_value() -> None:
    """|{a,b} n {b,c}| / |{a,b,c}| = 1/3"""
    assert jaccard(["a", "b"], ["b", "c"]) == pytest.approx(1 / 3)


def test_the_pricing_decoy_scores_the_value_section_25_quotes() -> None:
    """§25: the price rise hit all 41 enterprise accounts; the movement sits in
    two of them. 2/41 = 0.0488, which §10 rounds to 0.05 and §15's bands refute
    at anything under 0.2. *A cause with a footprint twenty times wider than its
    effect is not the cause.*"""
    exposed = [f"ACC-{i:04d}" for i in range(1, 42)]
    movement = ["ACC-0001", "ACC-0002"]

    j = jaccard(exposed, movement)
    assert j == pytest.approx(2 / 41)
    assert j == pytest.approx(0.05, abs=0.005)
    assert j < 0.2, "§15 refutes below 0.2"


def test_the_competitor_decoy_scores_zero_against_a_disjoint_region() -> None:
    assert jaccard(["APAC-1", "APAC-2"], ["ACC-0001", "ACC-0002"]) == 0.0


def test_the_true_cause_scores_one_because_the_footprints_are_the_same() -> None:
    """§10's Locality row for `integration_delay`: "pass (J = 1.0)"."""
    footprint = ["ACC-0001", "ACC-0002"]
    assert jaccard(footprint, list(reversed(footprint))) == 1.0


def test_two_empty_footprints_raise_rather_than_reading_as_refuted() -> None:
    """0.0 would land under §15's 0.2 band and refute the hypothesis on the
    strength of having checked nothing. §14.2's word for that is `uncheckable`,
    and it abstains."""
    with pytest.raises(ValueError, match="uncheckable"):
        jaccard([], [])


# ── Dose: Spearman — §15 S5, and the n >= 5 rule that caps the verdict ────────


def test_the_headline_case_cannot_pass_dose_at_two_accounts() -> None:
    """The most important behaviour in the package. §15: *"Our headline case has
    two accounts; Dose cannot pass, so the verdict cannot be Confirmed."*"""
    result = spearman([9.5, 8.0], [-15_000_016.0, -10_588_526.0])

    assert result.outcome == "inconclusive"
    assert result.rho is None, "a coefficient over two points is +/-1 by construction"
    assert result.n == 2
    assert "cannot be Confirmed" in result.detail


def test_spearman_matches_the_hand_computed_rho() -> None:
    """cause  [1, 2, 3, 4, 5]   ranks 1..5
    effect    [1, 3, 2, 4, 5]   ranks 1, 3, 2, 4, 5
    d         [0, -1, 1, 0, 0]  sum d^2 = 2
    rho       1 - 6x2 / (5 x 24) = 1 - 0.1 = 0.9
    """
    result = spearman([1, 2, 3, 4, 5], [1, 3, 2, 4, 5])

    assert result.rho == pytest.approx(0.9)
    assert result.outcome == "pass"


def test_a_rho_of_exactly_one_half_does_not_pass() -> None:
    """§15's band is `rho > 0.5`, not `>=`. The boundary is asserted because a
    hypothesis that squeaks through on a coin-flip correlation is exactly the
    kind of thing this project promises not to do.

    cause  [1, 2, 3, 4, 5]  effect [3, 1, 4, 2, 5]
    d      [-2, 1, -1, 2, 0]  sum d^2 = 10   rho = 1 - 60/120 = 0.5
    """
    result = spearman([1, 2, 3, 4, 5], [3, 1, 4, 2, 5])

    assert result.rho == pytest.approx(0.5)
    assert result.outcome == "inconclusive"


def test_a_backwards_relationship_refutes_rather_than_abstains() -> None:
    """The accounts hit hardest moved least. That is evidence *against* the
    hypothesis, not merely absent evidence for it — §14.2's distinction, applied
    to a statistic rather than to a probe."""
    result = spearman([1, 2, 3, 4, 5], [10, 8, 6, 4, 2])

    assert result.rho == pytest.approx(-1.0)
    assert result.outcome == "refute"
    assert "backwards" in result.detail


def test_a_moderate_inversion_refutes_too_not_only_a_perfect_one() -> None:
    """cause  [1, 2, 3, 4, 5]  effect [4, 5, 1, 2, 3]
    d        [-3, -3, 2, 2, 2]   sum d^2 = 30   rho = 1 - 180/120 = -0.5

    §15's band for Dose is `rho > 0.5` to pass; anything running backwards is
    evidence against. Pinning only the perfect -1.0 case would let the boundary
    drift until nothing but a textbook inversion could refute anything.
    """
    result = spearman([1, 2, 3, 4, 5], [4, 5, 1, 2, 3])

    assert result.rho == pytest.approx(-0.5)
    assert result.outcome == "refute"


def test_a_flat_cause_has_no_gradient_to_correlate() -> None:
    """§10's pricing row: *"price delta was uniform across the exposed accounts,
    so there is no gradient to correlate."* Inconclusive, not zero."""
    result = spearman([0.06] * 6, [1, 2, 3, 4, 5, 6])

    assert result.outcome == "inconclusive"
    assert result.rho is None
    assert "gradient" in result.detail


def test_the_minimum_is_five_pairs_and_five_pairs_is_enough() -> None:
    assert MIN_PAIRS == 5
    assert spearman([1, 2, 3, 4], [1, 2, 3, 4]).outcome == "inconclusive"
    assert spearman([1, 2, 3, 4, 5], [1, 2, 3, 4, 5]).outcome == "pass"


def test_spearman_refuses_unpaired_series() -> None:
    with pytest.raises(ValueError, match="unpaired"):
        spearman([1, 2, 3], [1, 2])


# ── Control: DiD and placebo rank — §15 S5 ───────────────────────────────────

#: §10's shape: two treated accounts against six matched enterprise controls.
TREATED = {"ACME": (100.0, 60.0), "NORTHWIND": (80.0, 50.0)}
CONTROLS = {
    "c1": (100.0, 98.0), "c2": (90.0, 89.0), "c3": (120.0, 117.0),
    "c4": (110.0, 109.0), "c5": (95.0, 93.0), "c6": (105.0, 104.0),
}


def test_did_matches_the_hand_computed_value() -> None:
    """treated changes  -40, -30            mean -35
    control changes     -2, -1, -3, -1, -2, -1   sum -10, mean -10/6 = -1.6667
    DiD                 -35 - (-1.6667) = -33.3333
    """
    assert did(TREATED, CONTROLS) == pytest.approx(-35.0 - (-10.0 / 6.0))
    assert did(TREATED, CONTROLS) == pytest.approx(-33.333333, abs=1e-5)


def test_did_subtracts_a_shift_that_moved_both_groups() -> None:
    """The whole reason a raw before/after cannot support a causal claim. Add a
    market-wide -20 to every unit and the estimate must not move."""
    shifted_t = {k: (pre, post - 20.0) for k, (pre, post) in TREATED.items()}
    shifted_c = {k: (pre, post - 20.0) for k, (pre, post) in CONTROLS.items()}

    assert did(shifted_t, shifted_c) == pytest.approx(did(TREATED, CONTROLS))


def test_placebo_rank_returns_the_position_among_six_placebos() -> None:
    """§44's verify command for this step, and §10's Control row verbatim: the
    real effect is rank 1 of 7 against 6 placebo assignments.

    Each placebo reassigns the treatment to one control and recomputes against
    the remaining five. For c1: its own change is -2; the other five change
    -1, -3, -1, -2, -1, mean -1.6. Placebo DiD = -2 - (-1.6) = -0.4.
    """
    result = placebo_rank(TREATED, CONTROLS)

    assert len(result.placebo_effects) == 6
    assert result.placebo_effects[0] == pytest.approx(-2.0 - (-8.0 / 5.0))
    assert result.placebo_effects[0] == pytest.approx(-0.4)

    assert result.rank == 1
    assert result.outcome == "pass"
    assert result.pseudo_p == pytest.approx(1 / 7)
    assert "rank 1 of 7" in result.detail


def test_the_rank_is_two_sided_so_a_large_opposite_swing_still_counts() -> None:
    """A control that swung hugely the *other* way is still a control group
    behaving dramatically. Ranking on the signed effect would discard it because
    the sign was inconvenient, which is the thumb on the scale this package
    exists to avoid."""
    noisy = dict(CONTROLS)
    noisy["c1"] = (100.0, 300.0)  # +200, far more extreme than the real -33

    result = placebo_rank(TREATED, noisy)
    assert result.rank > 1
    assert result.outcome != "pass"


def test_an_unexposed_group_that_moved_identically_refutes() -> None:
    """§10's pricing row: *"exposed accounts outside the footprint moved with the
    unexposed control group."* The effect is unremarkable among its own
    placebos, so Control refutes rather than abstaining."""
    flat_treated = {"x": (100.0, 99.0)}
    jittery = {
        "c1": (100.0, 90.0), "c2": (100.0, 112.0), "c3": (100.0, 88.0),
        "c4": (100.0, 115.0), "c5": (100.0, 85.0), "c6": (100.0, 110.0),
    }

    result = placebo_rank(flat_treated, jittery)
    assert result.outcome == "refute"
    assert "larger swing on their own" in result.detail


def test_too_few_controls_abstains_rather_than_reporting_rank_one() -> None:
    """§36 R6: *"DiD has no valid control group on a real case -> the test returns
    inconclusive."* Being the most extreme of three is one chance in three, and
    reporting that as a pass would be the failure the risk register names."""
    assert MIN_CONTROLS == 5

    few = {"c1": (100.0, 98.0), "c2": (90.0, 89.0), "c3": (120.0, 117.0)}
    result = placebo_rank(TREATED, few)

    assert result.outcome == "inconclusive"
    assert result.placebo_effects == ()
    assert "no valid control group" in result.detail


def test_did_refuses_an_empty_group() -> None:
    with pytest.raises(ValueError, match="empty group"):
        did(TREATED, {})


# ── Timing: PELT change-point — §15 S5 ───────────────────────────────────────


def test_a_clean_step_is_found_at_the_first_observation_of_the_new_segment() -> None:
    assert changepoints([1.0] * 20 + [10.0] * 20) == (20,)


def test_a_series_that_never_shifts_has_no_onset() -> None:
    """Returning an index anyway — the argmax, the first day over a threshold —
    would manufacture a date the data does not support, and Timing would then
    compare a real renewal against a fictional cause."""
    assert changepoints([5.0] * 40) == ()
    assert onset([5.0] * 40) is None


def test_the_integration_ticket_spike_is_found_at_its_true_onset() -> None:
    """The actual use. §24's treated accounts run at ~2.5 tickets/day and rise to
    ~9.5 after the onset; the generator measures 2.55 -> 9.50 for ACME. Getting
    this date wrong by a fortnight moves the lag across `max_lag_days: 45` and
    flips the Timing test."""
    rng = random.Random(24)
    series = [rng.gauss(2.5, 1.2) for _ in range(60)] + [rng.gauss(9.5, 2.5) for _ in range(50)]

    found = onset(series)
    assert found is not None
    assert abs(found - 60) <= 2


def test_two_shifts_are_both_found() -> None:
    assert changepoints([1.0] * 15 + [9.0] * 20 + [3.0] * 15) == (15, 35)


def test_a_series_shorter_than_two_segments_has_no_change_point() -> None:
    assert changepoints([1.0, 2.0, 3.0]) == ()


def test_a_one_day_spike_is_not_an_onset() -> None:
    """Timing asks when a cause *started*, not when something once happened. A
    minimum segment length is what separates the two: without it, a single
    outlying day becomes a segment of its own and the Timing test compares the
    renewal against a lag measured from an incident that lasted an afternoon."""
    spike = [1.0] * 20 + [50.0] + [1.0] * 20

    assert changepoints(spike) == ()
    assert changepoints(spike, min_size=1) == (20, 21)


def test_pelt_finds_the_injected_onset_to_the_day_on_the_real_corpus(
    warehouse: Path,
) -> None:
    """The verification that actually matters, and the one that corrected this
    module: on both treated accounts' daily ticket counts, PELT returns exactly
    `2026-03-12` — `scm.INTEGRATION_ONSET`, which nothing here was told.

    A robust MAD-based penalty was tried first and returned seven change-points
    on this same series. The module docstring records why.
    """
    con = duckdb.connect(str(warehouse), read_only=True)
    try:
        for account in ("ACC-0001", "ACC-0002"):
            rows = con.execute(
                "SELECT created_at::DATE, count(*) FROM product_ops.ticket "
                "WHERE account_id = ? GROUP BY 1 ORDER BY 1",
                [account],
            ).fetchall()
            by_day = dict(rows)
            first, last = rows[0][0], rows[-1][0]
            series = [
                float(by_day.get(first + timedelta(days=i), 0))
                for i in range((last - first).days + 1)
            ]

            found = onset(series)
            assert found is not None, f"{account} shows no onset at all"
            assert first + timedelta(days=found) == INTEGRATION_ONSET
    finally:
        con.close()


def test_a_higher_penalty_finds_fewer_change_points() -> None:
    series = [1.0] * 15 + [9.0] * 20 + [3.0] * 15
    assert len(changepoints(series, penalty=1e9)) == 0
    assert len(changepoints(series, penalty=1.0)) >= 2


def test_min_size_must_be_a_segment() -> None:
    with pytest.raises(ValueError, match="not a segment"):
        changepoints([1.0] * 20, min_size=0)
