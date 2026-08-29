"""Ladder step 0.2 — the treaty holds.

Three things are checked here: every type constructs, the three validators fire
on exactly the cases they exist for, and `extra="forbid"` catches a typo. The
fixtures are checked separately in test_fixtures.py.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest
from pydantic import ValidationError

from casefile.models import (
    PVM,
    AccessRules,
    Attribution,
    Case,
    CompositionEdge,
    ContributionNode,
    ContributionTree,
    DataQuality,
    Driver,
    Epoch,
    EvidenceItem,
    Footprint,
    Hypothesis,
    KPIContract,
    Lever,
    Lineage,
    Materiality,
    OpenQuestion,
    Persona,
    Recommendation,
    RefreshSpec,
    Signature,
    Source,
    StageTiming,
    Telemetry,
    TestMatrix,
    TestResult,
    Trigger,
    Usage,
    Verdict,
    VerificationCheck,
    VerificationResult,
)

SOURCE = Source(system="crm", record_id="opp-1", timestamp=datetime(2026, 4, 12, 9, 0))


def an_evidence_item(**overrides: object) -> EvidenceItem:
    payload: dict[str, object] = {
        "id": "ev-1",
        "claim": "Integration ticket volume rose 3.2x on ACME",
        "kind": "fact",
        "outcome": "found",
        "source": SOURCE,
        "method": "sql",
        "strength": 0.8,
        "freshness_hours": 4.0,
    }
    payload.update(overrides)
    return EvidenceItem.model_validate(payload)


def a_test_result(outcome: str = "pass") -> TestResult:
    return TestResult(outcome=outcome, detail="—")  # type: ignore[arg-type]


def a_verification(passed: bool = True) -> VerificationResult:
    return VerificationResult(
        passed=passed,
        checks=[VerificationCheck(name="freshness", passed=True, detail="4h old")],
        freshness_hours=4.0,
    )


def a_case(**overrides: object) -> Case:
    payload: dict[str, object] = {
        "id": "case-1",
        "trigger": Trigger(
            kpi="net_revenue", period="2026-04", delta=-24_000_000, delta_relative=-0.08
        ),
        "verification": a_verification(),
        "priority": 1.0,
        "telemetry": Telemetry(),
    }
    payload.update(overrides)
    return Case.model_validate(payload)


# ── The contract shape ────────────────────────────────────────────────────────


def test_contract_round_trips() -> None:
    contract = KPIContract(
        id="net_revenue",
        label="Net Revenue",
        owner_role="cfo",
        definition="Invoiced revenue net of discounts and credit notes.",
        unit="INR",
        direction="up_is_good",
        grain=["date", "account_id"],
        calendar="fiscal_445",
        formula="SUM(invoice_line.amount_net) - SUM(credit_note.amount)",
        refresh=RefreshSpec(source="billing", cadence="daily", sla_hours=26),
        epochs=[Epoch(effective_from=date(2023, 4, 1), formula="SUM(invoice_line.amount_net)")],
        composition=[
            CompositionEdge(kpi="gross_renewal_rate", weight="recurring", transform="arr_over_12")
        ],
        decomposition_dims=["region", "account"],
        materiality=Materiality(
            relative=0.03, absolute=2_500_000, min_persistence=2, z_threshold=3.0
        ),
        data_quality=DataQuality(max_single_record_share=0.35, min_completeness=0.98),
        drivers=[
            Driver(
                id="integration_delay",
                type="internal_controllable",
                evidence_sources=["tickets"],
                max_lag_days=45,
                lever=Lever(
                    action="prioritise_integration_fix",
                    owner_role="vp_engineering",
                    lag_days=14,
                    save_rate=(0.75, 1.0),
                ),
            )
        ],
        lineage=Lineage(),
        access=AccessRules(masking={"account_name": "hash_alias"}),
        history_start=date(2023, 4, 1),
        seasonal_period_days=365,
    )
    assert KPIContract.model_validate_json(contract.model_dump_json()) == contract


def test_an_uncontrollable_driver_may_have_no_lever() -> None:
    driver = Driver(
        id="seasonality",
        type="external_uncontrollable",
        evidence_sources=["historical_series"],
        max_lag_days=0,
    )
    assert driver.lever is None


# ── Validator 1: absence is counted ───────────────────────────────────────────


def test_checked_absent_without_a_denominator_is_rejected() -> None:
    with pytest.raises(ValidationError, match="denominator"):
        an_evidence_item(kind="absence", outcome="checked_absent")


def test_checked_absent_with_a_denominator_is_accepted() -> None:
    item = an_evidence_item(kind="absence", outcome="checked_absent", denominator=12)
    assert item.denominator == 12


def test_uncheckable_without_coverage_is_rejected() -> None:
    with pytest.raises(ValidationError, match="coverage"):
        an_evidence_item(kind="absence", outcome="uncheckable")


def test_uncheckable_with_coverage_is_accepted() -> None:
    """Scenario B: the sources could not see the footprint at all."""
    item = an_evidence_item(kind="absence", outcome="uncheckable", coverage=0.0)
    assert item.coverage == 0.0


def test_ledger_entries_cannot_be_reassigned() -> None:
    """§30 rule 4 — no stage mutates another stage's ledger entries."""
    with pytest.raises(ValidationError):
        an_evidence_item().strength = 0.1  # type: ignore[misc]


# ── Validator 2: the verdict ranks, it does not crown ─────────────────────────


def test_elimination_must_name_the_test_that_killed_it() -> None:
    with pytest.raises(ValidationError, match="names no test"):
        Verdict(
            attribution=[
                Attribution(driver_id="integration_delay", share=0.875, status="primary"),
                Attribution(driver_id="pricing_change", share=0.08, status="eliminated"),
            ],
            confidence="likely",
        )


def test_two_primaries_are_rejected() -> None:
    with pytest.raises(ValidationError, match="does not crown"):
        Verdict(
            attribution=[
                Attribution(driver_id="integration_delay", share=0.5, status="primary"),
                Attribution(driver_id="supply_delay", share=0.5, status="primary"),
            ],
            confidence="contested",
        )


def test_likely_needs_a_primary_driver() -> None:
    with pytest.raises(ValidationError, match="needs a primary driver"):
        Verdict(
            attribution=[Attribution(driver_id="pricing_change", share=0.08, status="minor")],
            confidence="likely",
        )


def test_contested_may_have_no_primary() -> None:
    """Scenario G: two hypotheses reach Likely and nothing separates them."""
    verdict = Verdict(
        attribution=[
            Attribution(driver_id="pricing_change", share=0.5, status="unresolved"),
            Attribution(driver_id="supply_delay", share=0.5, status="unresolved"),
        ],
        confidence="contested",
    )
    assert verdict.confidence == "contested"


# ── Validator 3: abstention carries its question ──────────────────────────────


def test_undetermined_without_a_question_is_rejected() -> None:
    with pytest.raises(ValidationError, match="discriminating question"):
        a_case(
            verdict=Verdict(
                attribution=[Attribution(driver_id="unmodelled", share=None, status="unresolved")],
                confidence="undetermined",
            )
        )


def test_undetermined_with_a_question_is_accepted() -> None:
    case = a_case(
        verdict=Verdict(
            attribution=[Attribution(driver_id="unmodelled", share=None, status="unresolved")],
            confidence="undetermined",
        ),
        open_question=OpenQuestion(
            question="Did either account cite a competitor?",
            owner_role="vp_sales",
            value_at_stake=9_000_000,
        ),
    )
    assert case.open_question is not None


def test_a_case_closed_at_verify_needs_no_verdict() -> None:
    """Scenarios D and E: a refund batch and a definition change, closed with
    zero model calls."""
    case = a_case(verification=a_verification(passed=False))
    assert case.verdict is None
    assert case.telemetry.model_calls == 0


# ── Concentration ─────────────────────────────────────────────────────────────


def test_concentration_matches_the_hand_computed_value() -> None:
    tree = ContributionTree(
        kpi="net_revenue",
        period="2026-04",
        total_delta=-24_000_000,
        by_dimension={
            "account": [
                ContributionNode(
                    dimension="account", key="ACME", delta=-13_000_000, share=13 / 24
                ),
                ContributionNode(
                    dimension="account", key="NORTHWIND", delta=-8_000_000, share=8 / 24
                ),
                ContributionNode(
                    dimension="account", key="others", delta=-3_000_000, share=3 / 24
                ),
            ]
        },
        footprint=Footprint(
            entities={"account_id": ["ACME", "NORTHWIND"]},
            window_start=date(2026, 3, 1),
            window_end=date(2026, 4, 30),
            delta=-21_000_000,
        ),
    )
    # 21 / 24 — the "88% sits in two accounts" line, before rounding.
    assert tree.concentration(2) == pytest.approx(0.875)
    assert tree.concentration(3) == pytest.approx(1.0)


def test_concentration_of_an_empty_dimension_is_zero() -> None:
    tree = ContributionTree(
        kpi="net_revenue",
        period="2026-04",
        total_delta=0.0,
        by_dimension={"account": []},
        footprint=Footprint(
            entities={},
            window_start=date(2026, 3, 1),
            window_end=date(2026, 4, 30),
            delta=0.0,
        ),
    )
    assert tree.concentration(2) == 0.0


# ── Telemetry is derived, never asserted ──────────────────────────────────────


def test_telemetry_derives_its_figures_from_the_records() -> None:
    telemetry = Telemetry(
        calls=[
            Usage(
                stage="s3",
                model="claude-sonnet",
                input_tokens=4000,
                output_tokens=800,
                latency_ms=1200,
                cost_inr=2.5,
            ),
            Usage(
                stage="s4c",
                model="claude-sonnet",
                input_tokens=9000,
                output_tokens=2000,
                latency_ms=2400,
                cost_inr=5.0,
            ),
        ],
        stages=[
            StageTiming(stage="s1", wall_ms=300),
            StageTiming(stage="s3", wall_ms=1200, used_model=True),
        ],
    )
    assert telemetry.model_calls == 2
    assert telemetry.total_cost_inr == pytest.approx(7.5)
    assert telemetry.total_latency_s == pytest.approx(1.5)
    assert telemetry.share_of_stages_without_model == pytest.approx(0.5)


def test_telemetry_figures_cannot_be_hand_written() -> None:
    """They are properties, so `extra="forbid"` rejects an asserted value."""
    with pytest.raises(ValidationError):
        Telemetry.model_validate({"calls": [], "stages": [], "model_calls": 3})


# ── extra="forbid" everywhere ─────────────────────────────────────────────────


def test_an_unknown_key_is_rejected() -> None:
    with pytest.raises(ValidationError, match="Extra inputs"):
        Footprint.model_validate(
            {
                "entities": {},
                "window_start": "2026-03-01",
                "window_end": "2026-04-30",
                "delta": -1.0,
                "acounts": ["ACME"],  # codespell:ignore
            }
        )


# ── The remaining types construct ─────────────────────────────────────────────


def test_the_rest_of_the_treaty_constructs() -> None:
    assert Hypothesis(
        driver_id="integration_delay",
        rationale="Ticket volume rose sharply on both accounts.",
        priority=1,
        expected_signature=Signature(timing="cause precedes effect by 14-45d"),
    ).priority == 1

    assert TestMatrix(
        timing=a_test_result(),
        locality=a_test_result(),
        dose=a_test_result("inconclusive"),
        control=a_test_result(),
    ).dose.outcome == "inconclusive"

    assert Recommendation(
        driver_id="integration_delay",
        lever="prioritise_integration_fix",
        action="Prioritise the integration fix; contact both accounts this week.",
        expected_impact=(18_000_000, 24_000_000),
        owner_role="vp_sales",
        confidence="likely",
        monitoring="renewal_rate · East · weekly",
    ).owner_role == "vp_sales"

    assert PVM(price=-2_000_000, volume=-21_000_000, mix=-1_000_000).mix == -1_000_000
    persona = Persona(id="p4", role_key="support_lead", label="Support Lead")
    assert persona.role_key == "support_lead"
