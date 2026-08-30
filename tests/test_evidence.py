"""engine/evidence.py — Stage 4a, probes and counted absence.

B5's definition of done: "`kind:\"absence\"` items carry an explicit
denominator." The headline case (§25 A) is the anchor throughout — its real
decomposition, from `decompose()`, is what the probes run against, so a
regression here shows up against the actual scenario the whole project is
built to explain, not a hand-typed stand-in.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import duckdb
import pytest

from casefile.contract import load_all
from casefile.engine.decompose import decompose
from casefile.engine.evidence import (
    EvidenceError,
    ExtractedClaim,
    ExtractionResponse,
    extract_claims,
    gather_probes,
)
from casefile.models import (
    AccessRules,
    DataQuality,
    Driver,
    Footprint,
    Hypothesis,
    KPIContract,
    Lineage,
    Materiality,
    RefreshSpec,
    Signature,
    Usage,
)

ROOT = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.gate2


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


@pytest.fixture(scope="module")
def east(con: duckdb.DuckDBPyConnection, contracts: dict[str, KPIContract]):
    return decompose(con, contracts["net_revenue"], "2026-04", {"region": "East"})


def a_hypothesis(driver_id: str) -> Hypothesis:
    return Hypothesis(
        driver_id=driver_id, rationale="test fixture", priority=1,
        expected_signature=Signature(),
    )


def integration_delay_hypothesis() -> Hypothesis:
    """A rationale that actually retrieves the on-topic authored notes and
    tickets — `a_hypothesis`'s generic "test fixture" text ranks nothing on
    the same topic, by design (§18's BM25 is a real ranker, not a stub)."""
    return Hypothesis(
        driver_id="integration_delay",
        rationale="integration issues delaying renewal",
        priority=1, expected_signature=Signature(),
    )


def by_driver(items, driver_id: str):
    return [i for i in items if driver_id in i.supports or driver_id in i.contradicts]


# ── Against the real headline case ──────────────────────────────────────────────


def test_every_probed_driver_produces_at_least_one_item(
    con: duckdb.DuckDBPyConnection, contracts: dict[str, KPIContract], east
) -> None:
    contract = contracts["net_revenue"]
    hypotheses = [a_hypothesis(d.id) for d in contract.drivers]
    items = gather_probes(contract, hypotheses, east.footprint, con)

    probed = [d.id for d in contract.drivers if d.probe_sql is not None]
    for driver_id in probed:
        assert by_driver(items, driver_id), f"no evidence produced for {driver_id!r}"


def test_the_competitor_probe_is_checked_absent_on_the_headline_footprint(
    con: duckdb.DuckDBPyConnection, contracts: dict[str, KPIContract], east
) -> None:
    """§25 A: lost-reason fields are populated, and none of them name a
    competitor — the decoy's evidence refutes it outright."""
    contract = contracts["net_revenue"]
    items = gather_probes(contract, [a_hypothesis("competitor_offer")], east.footprint, con)

    assert len(items) == 1
    item = items[0]
    assert item.outcome == "checked_absent"
    assert item.contradicts == ["competitor_offer"]
    assert item.denominator is not None and item.denominator > 0
    assert "0 of" in item.claim


def test_the_true_cause_matches_the_sealed_answer(
    con: duckdb.DuckDBPyConnection, contracts: dict[str, KPIContract], east, sealed: dict
) -> None:
    """The probe that supports `integration_delay` should fire on exactly the
    accounts the generator actually treated — read from the sealed answer
    sheet, not retyped by hand."""
    contract = contracts["net_revenue"]
    items = gather_probes(contract, [a_hypothesis("integration_delay")], east.footprint, con)
    spiked = {i.claim.split("'s")[0] for i in items if "integration_delay" in i.supports}
    assert spiked == set(sealed["A"]["footprint_accounts"])


def test_the_ticket_probe_finds_the_real_spike_on_the_treated_accounts(
    con: duckdb.DuckDBPyConnection, contracts: dict[str, KPIContract], east
) -> None:
    contract = contracts["net_revenue"]
    items = gather_probes(contract, [a_hypothesis("integration_delay")], east.footprint, con)

    found = [i for i in items if i.outcome == "found" and "integration_delay" in i.supports]
    assert len(found) == 2  # ACME and NORTHWIND both spiked
    assert all("rose" in i.claim for i in found)


def test_the_pricing_probe_finds_the_real_uplift(
    con: duckdb.DuckDBPyConnection, contracts: dict[str, KPIContract], east
) -> None:
    """The decoy's evidence is real — pricing genuinely moved. Locality is
    what eliminates it (§25), not the absence of a price change."""
    contract = contracts["net_revenue"]
    items = gather_probes(contract, [a_hypothesis("pricing_change")], east.footprint, con)

    assert items
    assert all(i.outcome == "found" and "pricing_change" in i.supports for i in items)


def test_a_driver_with_no_probe_sql_contributes_no_evidence(
    con: duckdb.DuckDBPyConnection, contracts: dict[str, KPIContract], east
) -> None:
    contract = contracts["net_revenue"]
    items = gather_probes(contract, [a_hypothesis("seasonality")], east.footprint, con)
    assert items == []


def test_an_unmodelled_hypothesis_contributes_no_evidence(
    con: duckdb.DuckDBPyConnection, contracts: dict[str, KPIContract], east
) -> None:
    contract = contracts["net_revenue"]
    items = gather_probes(contract, [a_hypothesis("unmodelled")], east.footprint, con)
    assert items == []


def test_evidence_ids_are_unique_across_a_full_gather(
    con: duckdb.DuckDBPyConnection, contracts: dict[str, KPIContract], east
) -> None:
    contract = contracts["net_revenue"]
    hypotheses = [a_hypothesis(d.id) for d in contract.drivers]
    items = gather_probes(contract, hypotheses, east.footprint, con)
    ids = [i.id for i in items]
    assert len(ids) == len(set(ids))


def test_as_of_defaults_from_the_warehouse_watermark(
    con: duckdb.DuckDBPyConnection, contracts: dict[str, KPIContract], east
) -> None:
    contract = contracts["net_revenue"]
    items = gather_probes(contract, [a_hypothesis("integration_delay")], east.footprint, con)
    assert all(i.freshness_hours > 0 for i in items)


# ── An empty footprint — the deterministic uncheckable path ───────────────────


@pytest.fixture
def empty_footprint(east) -> Footprint:
    """No accounts at all — every probe that keys off `account_ids` has
    nothing to find, deterministically, unlike the random incident table."""
    return Footprint(
        entities={"account_id": []},
        window_start=east.footprint.window_start,
        window_end=east.footprint.window_end,
        delta=0.0,
    )


def test_the_incident_probe_is_uncheckable_with_no_accounts_in_scope(
    con: duckdb.DuckDBPyConnection, contracts: dict[str, KPIContract], empty_footprint: Footprint
) -> None:
    contract = contracts["net_revenue"]
    items = gather_probes(contract, [a_hypothesis("supply_delay")], empty_footprint, con)
    assert len(items) == 1
    assert items[0].outcome == "uncheckable"
    assert items[0].coverage == 0.0
    assert items[0].supports == ["supply_delay"]  # findable via Ledger.for_driver


def test_the_competitor_probe_is_uncheckable_with_no_accounts_in_scope(
    con: duckdb.DuckDBPyConnection, contracts: dict[str, KPIContract], empty_footprint: Footprint
) -> None:
    contract = contracts["net_revenue"]
    items = gather_probes(contract, [a_hypothesis("competitor_offer")], empty_footprint, con)
    assert len(items) == 1
    assert items[0].outcome == "uncheckable"
    assert items[0].supports == ["competitor_offer"]


def test_the_ticket_probe_is_uncheckable_with_no_accounts_in_scope(
    con: duckdb.DuckDBPyConnection, contracts: dict[str, KPIContract], empty_footprint: Footprint
) -> None:
    contract = contracts["net_revenue"]
    items = gather_probes(contract, [a_hypothesis("integration_delay")], empty_footprint, con)
    assert items == []  # no account rows at all to full-outer-join against


# ── A probe naming an interpreter that does not exist ──────────────────────────


def _minimal_contract(probe_sql: str, driver_id: str = "bogus") -> KPIContract:
    driver = Driver(
        id=driver_id, type="internal_controllable", evidence_sources=["tickets"],
        max_lag_days=1, probe_sql=probe_sql,
    )
    return KPIContract(
        id="net_revenue", label="x", owner_role="cfo", definition="x", unit="INR",
        direction="down_is_good", grain=["date"], calendar="fiscal_445",
        formula="SUM(x)", refresh=RefreshSpec(source="billing", cadence="24h", sla_hours=24),
        decomposition_dims=["region"], materiality=Materiality(
            relative=0.03, absolute=1.0, min_persistence=2, z_threshold=3.0
        ),
        data_quality=DataQuality(max_single_record_share=0.35, min_completeness=0.95),
        drivers=[driver], lineage=Lineage(), access=AccessRules(),
        history_start=date(2023, 1, 1), seasonal_period_days=365,
    )


def test_a_probe_with_no_registered_interpreter_raises(
    con: duckdb.DuckDBPyConnection, east
) -> None:
    contract = _minimal_contract("probes/does_not_exist.sql")
    with pytest.raises(EvidenceError, match="does_not_exist"):
        gather_probes(contract, [a_hypothesis("bogus")], east.footprint, con)


# ── lost_reason_scan's denominator is `populated`, not `closed_lost` ──────────


# ── 4c · schema-forced extraction, against real retrieved documents ──────────


class FakeProvider:
    """Returns a fixed `ExtractionResponse` regardless of the prompt — the same
    pattern `test_hypothesise.py` uses to construct exact, malformed, or
    edge-case model output the guardrail has to handle."""

    def __init__(self, claims: list[ExtractedClaim]) -> None:
        self._response = ExtractionResponse(claims=claims)

    def complete(self, prompt, schema):  # noqa: ANN001, ANN201
        assert schema is ExtractionResponse
        return self._response, Usage(
            stage=prompt.stage, model="fake", input_tokens=1, output_tokens=1,
            latency_ms=0.0, cost_inr=0.0,
        )


class RaisingProvider:
    """Fails the test if the model is ever called — proves a skip really skips
    the call rather than making it and discarding the result."""

    def complete(self, prompt, schema):  # noqa: ANN001, ANN201
        raise AssertionError("no model call should have been made")


def test_a_real_quote_survives_and_carries_the_driver_it_supports(
    con: duckdb.DuckDBPyConnection, contracts: dict[str, KPIContract], east
) -> None:
    """`northwind-renewal-deferred` is a real, retrieved document on this
    footprint. The quote is copied verbatim from its actual text."""
    quote = "their operations team has been raising integration tickets steadily since mid-March"
    contract = contracts["net_revenue"]
    provider = FakeProvider(
        [
            ExtractedClaim(
                doc_id="northwind-renewal-deferred",
                quote=quote,
                claim="NORTHWIND's own notes tie the stalled renewal to open integration tickets.",
                supports=True,
            )
        ]
    )
    items, usages = extract_claims(
        contract, [integration_delay_hypothesis()], east.footprint, con, provider
    )

    assert len(items) == 1
    item = items[0]
    assert item.outcome == "found"
    assert item.method == "llm_extraction"
    assert item.supports == ["integration_delay"]
    assert item.contradicts == []
    assert item.quote == quote
    assert item.source.record_id == "northwind-renewal-deferred"
    assert len(usages) == 1
    assert usages[0].stage == "s4c"


def test_a_contradicting_claim_lands_in_contradicts_not_supports(
    con: duckdb.DuckDBPyConnection, contracts: dict[str, KPIContract], east
) -> None:
    contract = contracts["net_revenue"]
    provider = FakeProvider(
        [
            ExtractedClaim(
                doc_id="TKT-000517",
                quote="Twelfth day of partial exports.",
                claim="Doesn't actually contradict anything here, just exercising the flag.",
                supports=False,
            )
        ]
    )
    items, _usages = extract_claims(
        contract, [integration_delay_hypothesis()], east.footprint, con, provider
    )

    assert len(items) == 1
    assert items[0].supports == []
    assert items[0].contradicts == ["integration_delay"]


def test_a_hallucinated_doc_id_is_dropped(
    con: duckdb.DuckDBPyConnection, contracts: dict[str, KPIContract], east
) -> None:
    """Schema-forced guarantees the shape of the response, not its content —
    this is the guardrail that checks the content."""
    contract = contracts["net_revenue"]
    provider = FakeProvider(
        [
            ExtractedClaim(
                doc_id="does-not-exist-in-the-funnel",
                quote="anything at all",
                claim="a claim about a document that was never retrieved",
                supports=True,
            )
        ]
    )
    items, _usages = extract_claims(
        contract, [integration_delay_hypothesis()], east.footprint, con, provider
    )

    # the one claim was dropped, but documents genuinely were read — checked_absent
    assert len(items) == 1
    assert items[0].outcome == "checked_absent"
    assert items[0].denominator is not None and items[0].denominator > 0


def test_a_quote_that_is_not_actually_in_the_document_is_dropped(
    con: duckdb.DuckDBPyConnection, contracts: dict[str, KPIContract], east
) -> None:
    contract = contracts["net_revenue"]
    provider = FakeProvider(
        [
            ExtractedClaim(
                doc_id="northwind-renewal-deferred",
                quote="this exact sentence never appears in that document",
                claim="a fabricated quote",
                supports=True,
            )
        ]
    )
    items, _usages = extract_claims(
        contract, [integration_delay_hypothesis()], east.footprint, con, provider
    )
    assert len(items) == 1
    assert items[0].outcome == "checked_absent"


def test_whitespace_around_the_quote_does_not_break_verification(
    con: duckdb.DuckDBPyConnection, contracts: dict[str, KPIContract], east
) -> None:
    """The real text has none of this — a model reproducing it with different
    line breaks or doubled spaces should not read as a fabrication."""
    contract = contracts["net_revenue"]
    provider = FakeProvider(
        [
            ExtractedClaim(
                doc_id="TKT-000517",
                quote="Twelfth   day  of\npartial exports.",
                claim="whitespace-mangled but the same real sentence",
                supports=True,
            )
        ]
    )
    items, _usages = extract_claims(
        contract, [integration_delay_hypothesis()], east.footprint, con, provider
    )
    assert len(items) == 1
    assert items[0].outcome == "found"


def test_documents_were_read_and_nothing_extracted_is_checked_absent(
    con: duckdb.DuckDBPyConnection, contracts: dict[str, KPIContract], east
) -> None:
    contract = contracts["net_revenue"]
    provider = FakeProvider([])
    items, usages = extract_claims(
        contract, [integration_delay_hypothesis()], east.footprint, con, provider
    )
    assert len(items) == 1
    assert items[0].outcome == "checked_absent"
    assert items[0].contradicts == ["integration_delay"]
    assert len(usages) == 1  # the model was still called, just found nothing


def test_a_driver_with_no_document_bearing_sources_makes_no_call_at_all(
    con: duckdb.DuckDBPyConnection, contracts: dict[str, KPIContract], east
) -> None:
    """`seasonality`'s only `evidence_sources` entry is `historical_series`,
    which names no retrievable table — the same reason 4a skips a driver with
    no `probe_sql`."""
    contract = contracts["net_revenue"]
    items, usages = extract_claims(
        contract, [a_hypothesis("seasonality")], east.footprint, con, RaisingProvider()
    )
    assert items == []
    assert usages == []


def test_an_unmodelled_hypothesis_makes_no_call_either(
    con: duckdb.DuckDBPyConnection, contracts: dict[str, KPIContract], east
) -> None:
    contract = contracts["net_revenue"]
    items, usages = extract_claims(
        contract, [a_hypothesis("unmodelled")], east.footprint, con, RaisingProvider()
    )
    assert items == []
    assert usages == []


def test_no_documents_in_the_funnel_is_uncheckable_without_a_model_call(
    con: duckdb.DuckDBPyConnection, contracts: dict[str, KPIContract], east
) -> None:
    """`supply_delay` genuinely has no on-footprint documents worth ranking
    above BM25's floor here — real data, not a synthetic empty footprint."""
    contract = contracts["net_revenue"]
    items, usages = extract_claims(
        contract, [a_hypothesis("supply_delay")], east.footprint, con, RaisingProvider()
    )
    assert len(items) == 1
    assert items[0].outcome == "uncheckable"
    assert items[0].coverage == 0.0
    assert items[0].supports == ["supply_delay"]
    assert usages == []


def test_extraction_ids_are_unique_across_a_full_pass(
    con: duckdb.DuckDBPyConnection, contracts: dict[str, KPIContract], east
) -> None:
    contract = contracts["net_revenue"]
    provider = FakeProvider(
        [
            ExtractedClaim(
                doc_id="northwind-renewal-deferred",
                quote="Same pattern as ACME",
                claim="ties the two accounts together",
                supports=True,
            ),
            ExtractedClaim(
                doc_id="TKT-000517",
                quote="Twelfth day of partial exports.",
                claim="a second, independent claim",
                supports=True,
            ),
        ]
    )
    hypotheses = [a_hypothesis(d.id) for d in contract.drivers]
    items, _usages = extract_claims(contract, hypotheses, east.footprint, con, provider)
    ids = [i.id for i in items]
    assert len(ids) == len(set(ids))


def test_the_checked_absent_denominator_is_populated_fields_not_all_closed_lost() -> None:
    """A synthetic footprint where the two counts differ — the real warehouse
    happens not to exercise this distinction, so a mutant that swapped the
    denominator for `closed_lost` slipped past every other test here."""
    synthetic = duckdb.connect(":memory:")
    synthetic.execute("CREATE SCHEMA crm")
    synthetic.execute(
        "CREATE TABLE crm.opportunity (account_id VARCHAR, close_date DATE, "
        "closed_won BIGINT, lost_reason_code VARCHAR)"
    )
    synthetic.execute(
        "INSERT INTO crm.opportunity VALUES "
        "('ACC-1', '2026-04-05', 0, 'budget_freeze'), "  # closed lost, populated
        "('ACC-1', '2026-04-10', 0, ''), "  # closed lost, blank
        "('ACC-1', '2026-04-15', 0, ''), "  # closed lost, blank
        "('ACC-1', '2026-04-20', 1, '')"  # closed won — excluded entirely
    )
    contract = _minimal_contract("probes/lost_reason_scan.sql", driver_id="competitor_offer")
    footprint = Footprint(
        entities={"account_id": ["ACC-1"]},
        window_start=date(2026, 4, 1), window_end=date(2026, 4, 30), delta=0.0,
    )

    items = gather_probes(
        contract, [a_hypothesis("competitor_offer")], footprint, synthetic,
        as_of=datetime(2026, 5, 1),
    )

    assert len(items) == 1
    assert items[0].outcome == "checked_absent"
    assert items[0].denominator == 1  # populated, not closed_lost (3)
