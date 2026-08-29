"""Ladder step 0.3 — the two golden objects, and the fixture half of G0.

`fixtures/decomposition_east.json` unblocks Track B before Decompose exists;
`fixtures/case_east_8pct.json` unblocks Track C before anything exists, and
becomes the golden regression target in §35.5.

Both are hand-written from the §10 worked example, which is the single source of
truth for every number below. The point of these assertions is that the fixtures
cannot quietly drift away from the case we present on stage.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from casefile.models import Case, ContributionTree

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"

pytestmark = pytest.mark.gate0


@pytest.fixture(scope="module")
def tree() -> ContributionTree:
    return ContributionTree.model_validate_json(
        (FIXTURES / "decomposition_east.json").read_text(encoding="utf-8")
    )


@pytest.fixture(scope="module")
def case() -> Case:
    return Case.model_validate_json(
        (FIXTURES / "case_east_8pct.json").read_text(encoding="utf-8")
    )


# ── Both files parse ──────────────────────────────────────────────────────────
# `extra="forbid"` means a mistyped key fails here rather than silently becoming
# a default three weeks from now.


def test_the_two_fixtures_validate(tree: ContributionTree, case: Case) -> None:
    assert tree.kpi == "net_revenue"
    assert case.id == "case-2026-04-net_revenue-east"


def test_the_case_carries_the_same_decomposition(tree: ContributionTree, case: Case) -> None:
    assert case.decomposition == tree


# ── The arithmetic reconciles ─────────────────────────────────────────────────


@pytest.mark.parametrize("dimension", ["kpi", "account"])
def test_every_decomposition_sums_to_the_movement(tree: ContributionTree, dimension: str) -> None:
    assert sum(n.delta for n in tree.by_dimension[dimension]) == pytest.approx(tree.total_delta)


@pytest.mark.parametrize("dimension", ["kpi", "account"])
def test_stored_shares_agree_with_stored_deltas(tree: ContributionTree, dimension: str) -> None:
    for node in tree.by_dimension[dimension]:
        assert node.share == pytest.approx(abs(node.delta) / abs(tree.total_delta))


def test_pvm_reconciles_to_the_movement(tree: ContributionTree) -> None:
    assert tree.pvm is not None
    assert tree.pvm.price + tree.pvm.volume + tree.pvm.mix == pytest.approx(tree.total_delta)


def test_concentration_is_the_88_percent_line(tree: ContributionTree) -> None:
    """§10 prints 0.88; the fixture holds 21/24 so it reconciles with the deltas."""
    assert tree.concentration(2) == pytest.approx(0.875)
    assert round(tree.concentration(2), 2) == 0.88
    assert tree.concentration(2) >= 0.85  # the §35.2 gate


def test_the_footprint_is_the_two_accounts(tree: ContributionTree) -> None:
    assert tree.footprint.entities["account_id"] == ["ACME", "NORTHWIND"]
    assert tree.footprint.window_start == date(2026, 3, 1)
    assert tree.footprint.window_end == date(2026, 4, 30)
    assert tree.footprint.delta == pytest.approx(-21_000_000.0)


# ── The verdict is Likely, not Confirmed ──────────────────────────────────────


def test_the_verdict_is_likely_not_confirmed(case: Case) -> None:
    """The most important line in the whole project. With two accounts the Dose
    test cannot pass, so Confirmed is unreachable — by construction, not by
    tuning."""
    assert case.verdict is not None
    assert case.verdict.confidence == "likely"
    assert case.tests["integration_delay"].dose.outcome == "inconclusive"


def test_the_attribution_ranks_rather_than_crowns(case: Case) -> None:
    assert case.verdict is not None
    attribution = {a.driver_id: a for a in case.verdict.attribution}

    primary = case.verdict.attribution[0]
    assert primary.driver_id == "integration_delay"
    assert primary.status == "primary"

    # A decoy eliminated as the primary explanation keeps its arithmetic share.
    pricing = attribution["pricing_change"]
    assert pricing.status == "minor"
    assert pricing.share is not None
    assert 0.05 <= pricing.share <= 0.12  # §35.2

    competitor = attribution["competitor_offer"]
    assert competitor.status == "eliminated"
    assert competitor.eliminated_by == "locality"


def test_the_shares_that_exist_sum_to_the_whole_movement(case: Case) -> None:
    assert case.verdict is not None
    shares = [a.share for a in case.verdict.attribution if a.share is not None]
    assert sum(shares) == pytest.approx(1.0)


def test_both_decoys_are_refuted_on_locality(case: Case) -> None:
    assert case.tests["pricing_change"].locality.outcome == "refute"
    assert case.tests["competitor_offer"].locality.outcome == "refute"
    assert case.tests["competitor_offer"].timing.outcome == "refute"


def test_control_passes_on_placebo_rank(case: Case) -> None:
    control = case.tests["integration_delay"].control
    assert control.outcome == "pass"
    assert "placebo" in control.detail


# ── Evidence, absence and traceability ────────────────────────────────────────


def test_absence_is_counted_not_asserted(case: Case) -> None:
    """The 'we checked 12 lost-reason fields' item — evidence *against*."""
    absences = [e for e in case.ledger if e.outcome == "checked_absent"]
    assert absences, "the case must carry at least one counted absence"
    for item in absences:
        assert item.denominator is not None and item.denominator > 0


def test_every_test_result_cites_the_ledger_or_says_why_not(case: Case) -> None:
    ledger_ids = {e.id for e in case.ledger}
    for driver_id, matrix in case.tests.items():
        for name in ("timing", "locality", "dose", "control"):
            result = getattr(matrix, name)
            assert set(result.evidence_ids) <= ledger_ids, f"{driver_id}.{name} cites a ghost"
            if result.outcome in ("pass", "refute"):
                assert result.evidence_ids, f"{driver_id}.{name} decided without citing anything"


def test_every_hypothesis_was_tested(case: Case) -> None:
    """The registry enumerates; nothing quietly drops out before Challenge."""
    assert {h.driver_id for h in case.hypotheses} == set(case.tests)


def test_no_model_produced_a_number(case: Case) -> None:
    """§17 — llm_extraction may carry a claim, never a statistic."""
    for item in case.ledger:
        if item.method == "llm_extraction":
            assert item.kind != "statistic"


# ── Action and abstention ─────────────────────────────────────────────────────


def test_the_recommendation_has_all_seven_fields(case: Case) -> None:
    rec = case.recommendation
    assert rec is not None
    assert all(
        [rec.driver_id, rec.lever, rec.action, rec.expected_impact, rec.owner_role,
         rec.confidence, rec.monitoring]
    )
    assert rec.driver_id == "integration_delay"


def test_expected_impact_is_value_at_risk_times_the_save_rate_band(case: Case) -> None:
    """1.8-2.4 Cr = 2.4 Cr at risk x a declared 75-100% save rate — a measured
    number times a stated assumption."""
    assert case.recommendation is not None
    at_risk = abs(case.trigger.delta)
    low, high = case.recommendation.expected_impact
    assert low == pytest.approx(at_risk * 0.75)
    assert high == pytest.approx(at_risk * 1.00)


def test_the_open_question_is_worth_the_footprint(case: Case) -> None:
    assert case.open_question is not None
    assert case.open_question.owner_role == "vp_sales"
    assert case.open_question.value_at_stake == pytest.approx(21_000_000.0)


# ── The receipt ───────────────────────────────────────────────────────────────


def test_the_close_path_used_exactly_three_model_calls(case: Case) -> None:
    assert case.telemetry.model_calls == 3
    assert {c.stage for c in case.telemetry.calls} == {"s3", "s4c", "s8b"}


def test_three_of_twelve_stages_touched_a_model(case: Case) -> None:
    stages = case.telemetry.stages
    assert len(stages) == 12
    assert sum(1 for s in stages if s.used_model) == 3
    assert case.telemetry.share_of_stages_without_model == pytest.approx(0.75)


def test_the_case_lands_inside_the_budget(case: Case) -> None:
    assert case.telemetry.total_cost_inr < 10.0
    assert case.telemetry.total_latency_s < 10.0


def test_the_token_count_matches_the_scoped_retrieval_claim(case: Case) -> None:
    """~14.5k input, not the ~200k a whole-corpus RAG would need — §19."""
    assert sum(c.input_tokens for c in case.telemetry.calls) == 14_500
    assert sum(c.output_tokens for c in case.telemetry.calls) == 3_700
