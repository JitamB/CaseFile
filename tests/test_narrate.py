"""engine/narrate.py — Stage 8b, §15 S8b, LLM #3.

Ladder step 3.2's own verify text: "4 outputs, 4 different actions." The
guardrail is tested against a fake provider so every case — a well-formed
response, an invented token, an invented citation, a stray digit — is exact
and reproducible; the money-banding split (exact for an unrestricted persona,
banded for one whose `amount_net` is not granted) and the "no restricted name
ever leaks into prose" check run against the real, generated scenario A case,
the same discipline `test_entitle.py`'s own §35.4 security test already
holds narration to.

ADA-4 (docs/ada-integration-plan.md), below the money tests: a Contested or
Undetermined verdict must always name the specific test that kept it there —
checked both when the fallback fires and when the model's own text already
passes the guardrail, since the guarantee is code's, not a request the model
can decline.
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pytest

from casefile.contract import load_all as load_contracts
from casefile.engine.entitle import AccountFacts, entitle
from casefile.engine.narrate import NarrationResponse, narrate
from casefile.models import (
    Attribution,
    Case,
    KPIContract,
    Persona,
    Telemetry,
    TestMatrix,
    TestResult,
    Trigger,
    Usage,
    Verdict,
    VerificationResult,
)
from casefile.personas import load_all as load_personas

ROOT = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.gate3


class FakeProvider:
    """Returns a fixed `NarrationResponse` regardless of the prompt — the
    same pattern `test_evidence.py`'s own `FakeProvider` uses."""

    def __init__(self, **sections: str) -> None:
        self._response = NarrationResponse(**sections)

    def complete(self, prompt, schema):  # noqa: ANN001, ANN201
        assert schema is NarrationResponse
        return self._response, Usage(
            stage=prompt.stage, model="fake", input_tokens=1, output_tokens=1,
            latency_ms=0.0, cost_inr=0.0,
        )


def a_response(**overrides: str) -> dict[str, str]:
    base = {"headline": "", "explanation": "", "action": "", "outstanding": ""}
    base.update(overrides)
    return base


@pytest.fixture(scope="module")
def contract() -> KPIContract:
    return load_contracts(ROOT / "contracts")["net_revenue"]


@pytest.fixture(scope="module")
def personas() -> dict[str, Persona]:
    return load_personas(ROOT / "personas")


@pytest.fixture
def case() -> Case:
    """§31's golden object, same fixture `test_entitle.py`'s fast unit tests
    build against."""
    return Case.model_validate(
        json.loads((ROOT / "fixtures" / "case_east_8pct.json").read_text(encoding="utf-8"))
    )


# ── The guardrail, against a fake provider ──────────────────────────────────


def test_a_well_formed_section_interpolates_its_tokens_and_citations(
    case: Case, personas: dict[str, Persona], contract: KPIContract
) -> None:
    provider = FakeProvider(**a_response(
        headline="{kpi} moved {delta_pct} ({delta}) in {period}. [ev-001]",
    ))
    narration, usage = narrate(case, personas["cfo"], contract, provider)
    assert "{" not in narration.headline
    assert "[ev-001]" in narration.headline  # the citation stays, visibly, for a reader to trace
    assert "Net Revenue" in narration.headline
    assert usage.stage == "s8b"


def test_an_unknown_token_falls_back_to_the_templated_sentence(
    case: Case, personas: dict[str, Persona], contract: KPIContract
) -> None:
    provider = FakeProvider(**a_response(headline="{made_up_token} happened."))
    narration, _ = narrate(case, personas["cfo"], contract, provider)
    assert "{made_up_token}" not in narration.headline
    assert "Net Revenue" in narration.headline  # the fallback sentence


def test_an_invented_citation_falls_back(
    case: Case, personas: dict[str, Persona], contract: KPIContract
) -> None:
    provider = FakeProvider(**a_response(explanation="Something happened. [ev-999]"))
    narration, _ = narrate(case, personas["cfo"], contract, provider)
    assert narration.explanation == _fallback_explanation_text(case)


def test_a_stray_digit_falls_back_even_with_valid_tokens_and_citations(
    case: Case, personas: dict[str, Persona], contract: KPIContract
) -> None:
    provider = FakeProvider(**a_response(
        explanation="Confidence is {confidence}, roughly 24000000 INR. [ev-001]",
    ))
    narration, _ = narrate(case, personas["cfo"], contract, provider)
    assert "24000000" not in narration.explanation
    assert narration.explanation == _fallback_explanation_text(case)


def test_an_empty_response_falls_back_on_every_section(
    case: Case, personas: dict[str, Persona], contract: KPIContract
) -> None:
    provider = FakeProvider(**a_response())
    narration, _ = narrate(case, personas["cfo"], contract, provider)
    assert narration.headline
    assert narration.explanation
    assert narration.action
    assert narration.outstanding


def _fallback_explanation_text(case: Case) -> str:
    assert case.verdict is not None
    primary = next(a for a in case.verdict.attribution if a.status == "primary")
    driver = primary.driver_id.replace("_", " ")
    share = round(primary.share * 100)
    confidence = case.verdict.confidence.capitalize()
    return f"Confidence: {confidence}. Primary driver: {driver} ({share}%)."


# ── Money: exact for an unrestricted persona, banded for a restricted one ───


def test_money_is_exact_for_cfo_and_banded_for_support_lead(
    case: Case, personas: dict[str, Persona], contract: KPIContract
) -> None:
    provider = FakeProvider(**a_response(headline="Impact stands at {impact}."))

    cfo_narration, _ = narrate(case, personas["cfo"], contract, provider)
    support_narration, _ = narrate(case, personas["support_lead_east"], contract, provider)

    assert "₹1.8 Cr" in cfo_narration.headline or "₹2.4 Cr" in cfo_narration.headline
    assert "₹1–5 Cr" in support_narration.headline or "₹5–25 Cr" in support_narration.headline
    assert cfo_narration.headline != support_narration.headline


# ── Real data: no restricted name ever leaks into prose ────────────────────


@pytest.fixture(scope="module")
def con(warehouse: Path) -> duckdb.DuckDBPyConnection:
    connection = duckdb.connect(str(warehouse), read_only=True)
    yield connection
    connection.close()


@pytest.fixture(scope="module")
def accounts(warehouse: Path) -> dict[str, AccountFacts]:
    connection = duckdb.connect(str(warehouse), read_only=True)
    try:
        return {
            str(row[0]): AccountFacts(str(row[0]), str(row[1]), str(row[2]), str(row[3]))
            for row in connection.execute(
                "SELECT account_id, account_name, segment, region FROM crm.account"
            ).fetchall()
        }
    finally:
        connection.close()


@pytest.fixture(scope="module")
def real_entitled_case(
    con: duckdb.DuckDBPyConnection,
    contract: KPIContract,
    personas: dict[str, Persona],
    accounts: dict[str, AccountFacts],
):
    from casefile.engine.adjudicate import adjudicate
    from casefile.engine.challenge import challenge
    from casefile.engine.decompose import decompose
    from casefile.engine.evidence import gather_probes
    from casefile.engine.recommend import recommend
    from casefile.engine.verify import verify
    from casefile.models import Hypothesis, Signature, Telemetry, Trigger

    period, dimensions = "2026-04", {"region": "East"}
    result = verify(con, contract, period, dimensions)
    assert result.passed
    tree = decompose(con, contract, period, dimensions)
    hypotheses = [
        Hypothesis(driver_id=d.id, rationale="test", priority=1, expected_signature=Signature())
        for d in contract.drivers
    ]
    ledger = gather_probes(contract, hypotheses, tree.footprint, con)
    matrices, challenge_items = challenge(contract, hypotheses, tree, con)
    ledger += challenge_items
    verdict, question, priority = adjudicate(
        contract, hypotheses, tree, ledger, matrices, result
    )
    recommendation = recommend(contract, verdict, tree, dimensions)
    trigger = Trigger(
        kpi=contract.id, period=period, dimensions=dimensions,
        delta=tree.total_delta, delta_relative=-0.08,
    )
    case = Case(
        id="case-2026-04-net_revenue-east", trigger=trigger, verification=result,
        decomposition=tree, hypotheses=hypotheses, ledger=ledger, tests=matrices,
        verdict=verdict, recommendation=recommendation, open_question=question,
        priority=priority, telemetry=Telemetry(),
    )
    return {
        role: entitle(case, personas[role], contract, accounts)
        for role in ("cfo", "support_lead_east")
    }


def test_no_restricted_account_name_leaks_into_narration_for_support_lead(
    real_entitled_case, contract: KPIContract, personas: dict[str, Persona]
) -> None:
    view = real_entitled_case["support_lead_east"]
    provider = FakeProvider(**a_response(
        explanation="Movement traced to {primary_driver} on {dimensions}. [ev-001]",
        action="{action}" if view.case.recommendation else "",
    ))
    narration, _ = narrate(view.case, personas["support_lead_east"], contract, provider)
    for name in ("ACME", "NORTHWIND"):
        assert name not in narration.headline
        assert name not in narration.explanation
        assert name not in narration.action
        assert name not in narration.outstanding


# ── ADA-4 — Contested/Undetermined always names the limiting test ──────────


@pytest.fixture(scope="module")
def undetermined_case() -> Case:
    """Real `run_case()` output, scenario B — §25, docs/DECISIONS.md."""
    return Case.model_validate(
        json.loads((ROOT / "fixtures" / "case_real_scenario_b.json").read_text(encoding="utf-8"))
    )


def test_an_undetermined_verdict_names_the_limiting_test_on_the_fallback_path(
    undetermined_case: Case, personas: dict[str, Persona], contract: KPIContract
) -> None:
    provider = FakeProvider(**a_response())
    narration, _ = narrate(undetermined_case, personas["cfo"], contract, provider)
    assert "competitor offer — no determinable onset for competitor_offer" in narration.explanation


def test_the_limiting_test_clause_is_appended_even_when_the_models_own_text_passes(
    undetermined_case: Case, personas: dict[str, Persona], contract: KPIContract
) -> None:
    """The guarantee is code's, not the model's — proven by giving the model
    valid, guardrail-passing text and confirming the clause still lands."""
    provider = FakeProvider(**a_response(
        explanation="Confidence is {confidence}. [ev-competitor_offer-timing-001]",
    ))
    narration, _ = narrate(undetermined_case, personas["cfo"], contract, provider)
    assert narration.explanation.startswith("Confidence is Undetermined.")
    assert "no determinable onset for competitor_offer" in narration.explanation


def test_a_contested_verdict_names_the_limiting_test_for_every_contender() -> None:
    """Two survivors, both unresolved (adjudicate.py's own Contested status,
    per its docstring) — the clause must name what kept *each* short of
    Confirmed, not just the higher-ranked one."""
    passing = TestResult(outcome="pass", detail="clears easily")
    matrices = {
        "pricing_change": TestMatrix(
            timing=passing,
            locality=passing,
            dose=TestResult(outcome="inconclusive", detail="only 2 accounts, dose needs n>=5"),
            control=passing,
        ),
        "competitor_offer": TestMatrix(
            timing=passing,
            locality=TestResult(
                outcome="inconclusive", detail="no determinable footprint for competitor_offer"
            ),
            dose=passing,
            control=passing,
        ),
    }
    verdict = Verdict(
        attribution=[
            Attribution(
                driver_id="pricing_change", share=0.5, status="unresolved", eliminated_by=None
            ),
            Attribution(
                driver_id="competitor_offer", share=0.5, status="unresolved", eliminated_by=None
            ),
        ],
        confidence="contested",
    )
    case = Case(
        id="synthetic-contested",
        trigger=Trigger(
            kpi="net_revenue", period="2026-04", delta=-1_000_000.0, delta_relative=-0.05
        ),
        verification=VerificationResult(passed=True, checks=[], freshness_hours=1.0),
        tests=matrices,
        verdict=verdict,
        priority=1.0,
        telemetry=Telemetry(),
    )
    contract = load_contracts(ROOT / "contracts")["net_revenue"]
    personas = load_personas(ROOT / "personas")
    provider = FakeProvider(**a_response())

    narration, _ = narrate(case, personas["cfo"], contract, provider)

    assert "pricing change — only 2 accounts, dose needs n>=5" in narration.explanation
    assert (
        "competitor offer — no determinable footprint for competitor_offer"
        in narration.explanation
    )


def test_a_likely_verdict_gets_no_limiting_test_clause(
    case: Case, personas: dict[str, Persona], contract: KPIContract
) -> None:
    """Scoped to Contested/Undetermined only — a Likely verdict already has a
    primary driver and a share; this clause would be redundant noise there."""
    assert case.verdict is not None and case.verdict.confidence == "likely"
    provider = FakeProvider(**a_response())
    narration, _ = narrate(case, personas["cfo"], contract, provider)
    assert " — " not in narration.explanation
