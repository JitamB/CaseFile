"""engine/feedback.py — Stage 9, S9.

§44's own ladder step 4.1, made into assertions: *"After 5 marks: gathering
depth and presentation order shift; a contract gap appears in the registry."*
Enumeration is exercised against the real `net_revenue` contract (five real
drivers), the same convention `test_hypothesise.py` uses, so the composite
gate4 test at the bottom is a real scenario, not a synthetic one.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from casefile.contract import load
from casefile.engine.feedback import (
    NOT_MATERIAL_MAX_STEPS,
    FeedbackMark,
    LearningState,
    adjusted_materiality,
    apply,
    driver_prior,
    gathering_depth,
    promote,
    reorder,
)
from casefile.engine.hypothesise import _enumerate
from casefile.models import Driver, Hypothesis, KPIContract, Signature

pytestmark = pytest.mark.gate4

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def contract() -> KPIContract:
    return load(ROOT / "contracts" / "net_revenue.yaml")


def a_hypothesis(driver_id: str, priority: int = 1) -> Hypothesis:
    return Hypothesis(
        driver_id=driver_id, rationale="because", priority=priority, expected_signature=Signature()
    )


def a_mark(**overrides: object) -> FeedbackMark:
    base = {
        "case_id": "c1", "kind": "correct_driver", "kpi": "net_revenue",
        "driver_id": "pricing_change",
    }
    return FeedbackMark(**{**base, **overrides})  # type: ignore[arg-type]


# ── FeedbackMark — a kind carries what it needs ────────────────────────────────


def test_correct_driver_without_driver_id_is_rejected() -> None:
    with pytest.raises(ValidationError, match="driver_id"):
        FeedbackMark(case_id="c1", kind="correct_driver", kpi="net_revenue")


def test_wrong_driver_without_driver_id_is_rejected() -> None:
    with pytest.raises(ValidationError, match="driver_id"):
        FeedbackMark(case_id="c1", kind="wrong_driver", kpi="net_revenue")


def test_missed_cause_without_new_driver_is_rejected() -> None:
    with pytest.raises(ValidationError, match="new_driver"):
        FeedbackMark(case_id="c1", kind="missed_cause", kpi="net_revenue")


def test_not_material_needs_neither_driver_id_nor_new_driver() -> None:
    FeedbackMark(case_id="c1", kind="not_material", kpi="net_revenue")


# ── apply — pure, per driver per segment ────────────────────────────────────────


def test_apply_does_not_mutate_the_state_passed_in() -> None:
    state = LearningState()
    updated = apply(state, a_mark(kind="correct_driver"))
    assert state.driver_prior == {}
    assert updated.driver_prior != {}


def test_correct_driver_raises_the_prior_and_wrong_driver_lowers_it() -> None:
    state = LearningState()
    state = apply(state, a_mark(kind="correct_driver"))
    assert driver_prior(state, "net_revenue", "pricing_change", {}) == 1.0
    state = apply(state, a_mark(kind="wrong_driver"))
    assert driver_prior(state, "net_revenue", "pricing_change", {}) == 0.0


def test_a_driver_nothing_has_been_learned_about_has_a_zero_prior() -> None:
    state = LearningState()
    assert driver_prior(state, "net_revenue", "seasonality", {}) == 0.0


def test_the_same_driver_in_two_segments_learns_independently() -> None:
    state = LearningState()
    state = apply(state, a_mark(kind="wrong_driver", segment={"account": "ACC-0001"}))
    assert driver_prior(state, "net_revenue", "pricing_change", {"account": "ACC-0001"}) == -1.0
    assert driver_prior(state, "net_revenue", "pricing_change", {"account": "ACC-0002"}) == 0.0


# ── gathering_depth — a cut earned by being wrong, never the default ────────────


def test_gathering_depth_starts_full() -> None:
    state = LearningState()
    assert gathering_depth(state, "net_revenue", "pricing_change", {}) == "full"


def test_two_wrong_marks_cut_gathering_depth_to_probe_only() -> None:
    state = LearningState()
    for _ in range(2):
        state = apply(state, a_mark(kind="wrong_driver"))
    assert gathering_depth(state, "net_revenue", "pricing_change", {}) == "probe_only"


def test_one_correct_mark_cancels_one_wrong_mark() -> None:
    state = LearningState()
    for _ in range(2):
        state = apply(state, a_mark(kind="wrong_driver"))
    state = apply(state, a_mark(kind="correct_driver"))
    assert gathering_depth(state, "net_revenue", "pricing_change", {}) == "full"


# ── reorder — presentation only, never adds, removes, or re-tests ──────────────


def test_reorder_ranks_the_learned_driver_first(contract: KPIContract) -> None:
    driver_ids = _enumerate(contract)
    hypotheses = [a_hypothesis(d, priority=i) for i, d in enumerate(driver_ids, start=1)]
    state = LearningState()
    state = apply(state, a_mark(kind="correct_driver", driver_id="competitor_offer"))

    ordered = reorder(state, "net_revenue", hypotheses, {})

    assert ordered[0].driver_id == "competitor_offer"
    assert {h.driver_id for h in ordered} == set(driver_ids)
    assert len(ordered) == len(hypotheses)


def test_reorder_with_nothing_learned_keeps_the_enumerated_order(contract: KPIContract) -> None:
    driver_ids = _enumerate(contract)
    hypotheses = [a_hypothesis(d, priority=i) for i, d in enumerate(driver_ids, start=1)]
    ordered = reorder(LearningState(), "net_revenue", hypotheses, {})
    assert [h.driver_id for h in ordered] == driver_ids


# ── adjusted_materiality — relaxes, capped, per KPI ─────────────────────────────


def test_no_marks_leaves_materiality_unchanged(contract: KPIContract) -> None:
    unchanged = adjusted_materiality(LearningState(), "net_revenue", contract.materiality)
    assert unchanged == contract.materiality


def test_not_material_marks_raise_both_thresholds(contract: KPIContract) -> None:
    state = LearningState()
    state = apply(state, a_mark(kind="not_material"))
    relaxed = adjusted_materiality(state, "net_revenue", contract.materiality)
    assert relaxed.relative > contract.materiality.relative
    assert relaxed.absolute > contract.materiality.absolute


def test_not_material_adjustment_is_capped(contract: KPIContract) -> None:
    at_cap = LearningState()
    for _ in range(NOT_MATERIAL_MAX_STEPS):
        at_cap = apply(at_cap, a_mark(kind="not_material"))
    past_cap = at_cap
    for _ in range(40):
        past_cap = apply(past_cap, a_mark(kind="not_material"))

    a = adjusted_materiality(at_cap, "net_revenue", contract.materiality)
    b = adjusted_materiality(past_cap, "net_revenue", contract.materiality)
    assert a.relative == b.relative
    assert a.absolute == b.absolute


def test_a_different_kpis_marks_do_not_relax_this_one(contract: KPIContract) -> None:
    state = LearningState()
    state = apply(state, a_mark(kind="not_material", kpi="nrr"))
    unchanged = adjusted_materiality(state, "net_revenue", contract.materiality)
    assert unchanged == contract.materiality


# ── promote — the registry gap, filled ──────────────────────────────────────────


def new_driver(driver_id: str = "regulatory_change") -> Driver:
    return Driver(
        id=driver_id, type="external", evidence_sources=["support_corpus"], max_lag_days=30
    )


def test_promote_adds_the_driver_and_leaves_the_original_contract_untouched(
    contract: KPIContract,
) -> None:
    mark = a_mark(kind="missed_cause", new_driver=new_driver())
    promoted = promote(contract, mark)
    assert "regulatory_change" in {d.id for d in promoted.drivers}
    assert "regulatory_change" not in {d.id for d in contract.drivers}


def test_promote_rejects_a_driver_id_already_in_the_registry(contract: KPIContract) -> None:
    mark = a_mark(kind="missed_cause", new_driver=new_driver("pricing_change"))
    with pytest.raises(ValueError, match="already in the registry"):
        promote(contract, mark)


def test_promote_rejects_a_mark_that_is_not_missed_cause(contract: KPIContract) -> None:
    mark = a_mark(kind="not_material")
    with pytest.raises(ValueError, match="missed_cause"):
        promote(contract, mark)


# ── The ladder's own verify text, as one scenario ───────────────────────────────


def test_after_five_marks_depth_and_order_shift_and_a_gap_is_promoted(
    contract: KPIContract,
) -> None:
    """§44 ladder step 4.1: "After 5 marks: gathering depth and presentation
    order shift; a contract gap appears in the registry." Five marks, three
    kinds, against the real net_revenue contract's five real drivers.
    """
    segment = {"account": "ACC-0001"}
    marks = [
        a_mark(case_id="c1", kind="wrong_driver", driver_id="pricing_change", segment=segment),
        a_mark(case_id="c2", kind="wrong_driver", driver_id="pricing_change", segment=segment),
        a_mark(case_id="c3", kind="correct_driver", driver_id="competitor_offer", segment=segment),
        a_mark(case_id="c4", kind="not_material"),
        a_mark(case_id="c5", kind="missed_cause", new_driver=new_driver()),
    ]

    state = LearningState()
    for mark in marks:
        state = apply(state, mark)

    # gathering depth shifts: two uncontested wrong marks cut it, an untouched
    # driver in the same segment does not move
    assert gathering_depth(state, "net_revenue", "pricing_change", segment) == "probe_only"
    assert gathering_depth(state, "net_revenue", "seasonality", segment) == "full"

    # presentation order shifts: the one correct mark ranks its driver first
    driver_ids = _enumerate(contract)
    hypotheses = [a_hypothesis(d, priority=i) for i, d in enumerate(driver_ids, start=1)]
    ordered = reorder(state, "net_revenue", hypotheses, segment)
    assert ordered[0].driver_id == "competitor_offer"
    assert {h.driver_id for h in ordered} == set(driver_ids)

    # the materiality gate relaxes for this KPI
    relaxed = adjusted_materiality(state, "net_revenue", contract.materiality)
    assert relaxed.relative > contract.materiality.relative

    # a contract gap is promoted into a real, testable driver
    promoted = promote(contract, marks[-1])
    assert "regulatory_change" in {d.id for d in promoted.drivers}

    # and the rubric itself never moved: the same five original drivers are
    # still exactly what gets enumerated from the untouched contract
    assert _enumerate(contract) == driver_ids
