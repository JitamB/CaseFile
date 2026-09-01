"""No raw warehouse value ever reaches an LLM prompt — ADA-3, docs/ada-integration-plan.md.

§17's own claim — three of twelve stages touch a model, "and none of them
produce a number" — is, until this file, asserted in docs and prose, never
verified by a test the way `evidence.py`'s own `_guardrail` verifies a
claim's *quote* is real. Automated Data Analyst's own `build_ai_payload`/
`build_planner_payload` (github.com/saineshnakra/automated-data-analyst) are
structurally incapable of this leak — they only ever serialize computed
dataclasses, never a dataframe. This file closes the same gap here,
empirically, for the three stages that build an LLM prompt (S3, S4c, S8b):
one real, distinctive raw warehouse figure — an `amount_net` invoice-line
value for a real account inside a real case's real footprint, queried from
the real generated warehouse, not invented — checked against the actual
`Prompt.system`/`.user` text each stage really constructs.

`case_real_scenario_a.json` (`tools/build_real_case_fixtures.py`, already
real `run_case()` output, not hand-typed — see `docs/DECISIONS.md`) supplies
the real trigger, footprint and hypotheses; only the sentinel value and the
funnel retrieval are fetched fresh here, against the same committed seed.
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pytest

from casefile.contract import load
from casefile.engine.evidence import _driver
from casefile.engine.evidence import _prompt as evidence_prompt
from casefile.engine.hypothesise import _enumerate
from casefile.engine.hypothesise import _prompt as hypothesise_prompt
from casefile.engine.narrate import _prompt as narrate_prompt
from casefile.engine.narrate import _tokens
from casefile.models import Case, KPIContract
from casefile.personas import load_all as load_personas
from casefile.retrieval import retrieve

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def contract() -> KPIContract:
    return load(ROOT / "contracts" / "net_revenue.yaml")


@pytest.fixture(scope="module")
def con(warehouse: Path) -> duckdb.DuckDBPyConnection:
    connection = duckdb.connect(str(warehouse), read_only=True)
    yield connection
    connection.close()


@pytest.fixture(scope="module")
def case() -> Case:
    """§25 A's real footprint (ACC-0001, ACC-0002) — real `run_case()`
    output, the same fixture the UI now renders (docs/DECISIONS.md)."""
    return Case.model_validate(
        json.loads(
            (ROOT / "fixtures" / "case_real_scenario_a.json").read_text(encoding="utf-8")
        )
    )


@pytest.fixture(scope="module")
def sentinel(con: duckdb.DuckDBPyConnection) -> str:
    """One real, raw invoice-line figure for a real footprint account —
    exactly the kind of number a careless prompt-builder could accidentally
    interpolate, and exactly what none of the three stages below are
    supposed to see. Formatted the way it would render if a bug ever
    interpolated it raw (`f"{amount:,.2f}"`), so the check is on the actual
    digit sequence, not merely the underlying float.
    """
    amount = con.execute(
        "SELECT amount_net FROM billing.invoice_line WHERE account_id = 'ACC-0001' "
        "ORDER BY invoice_id, line_no LIMIT 1"
    ).fetchone()[0]
    return f"{amount:,.2f}"


@pytest.mark.gate1
def test_the_sentinel_is_a_real_specific_warehouse_value(sentinel: str) -> None:
    """The three tests below only mean something if the sentinel is real and
    specific — not a value generic enough (e.g. "0.00") to pass by accident.
    Pinned to the committed seed, the same way `test_materiality.py`'s own
    headline assertions pin real generated numbers.
    """
    assert sentinel == "3,166,475.00"


# ── S3 — hypothesise, LLM #1 ─────────────────────────────────────────────────


@pytest.mark.gate2
def test_hypothesise_prompt_never_contains_the_sentinel(
    contract: KPIContract, case: Case, sentinel: str
) -> None:
    assert case.decomposition is not None  # scenario A always decomposes
    prompt = hypothesise_prompt(
        contract, case.trigger, case.decomposition.footprint, _enumerate(contract)
    )
    assert sentinel not in prompt.system
    assert sentinel not in prompt.user


# ── S4c — extraction, LLM #2 ──────────────────────────────────────────────────


@pytest.mark.gate2
def test_evidence_prompt_never_contains_the_sentinel(
    con: duckdb.DuckDBPyConnection, contract: KPIContract, case: Case, sentinel: str
) -> None:
    assert case.decomposition is not None
    hypothesis = next(h for h in case.hypotheses if h.driver_id == "integration_delay")
    driver = _driver(contract, hypothesis.driver_id)
    assert driver is not None

    funnel = retrieve(con, case.decomposition.footprint, hypothesis.rationale, driver=driver)
    assert funnel, "scenario A's integration_delay driver has real retrievable documents"

    prompt = evidence_prompt(driver, hypothesis, funnel)
    assert sentinel not in prompt.system
    assert sentinel not in prompt.user


# ── S8b — narrate, LLM #3 ─────────────────────────────────────────────────────


@pytest.mark.gate3
def test_narrate_prompt_never_contains_the_sentinel(
    contract: KPIContract, case: Case, sentinel: str
) -> None:
    personas = load_personas(ROOT / "personas")
    for persona in personas.values():
        tokens = _tokens(case, persona, contract)
        prompt = narrate_prompt(case, persona, tokens)
        assert sentinel not in prompt.system
        assert sentinel not in prompt.user
