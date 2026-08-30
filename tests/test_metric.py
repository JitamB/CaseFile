"""Ladder step 2.7 pulled forward — the six contracts, and executing them.

Two verify commands meet here. A1's definition of done is *"CI fails on missing
element, unknown `lever.owner_role`, or lineage referencing a non-existent
table"*, and §44 2.7's is *"all six validate"*. But a contract that validates and
cannot be **run** is documentation with a schema, and §14.1's whole claim is that
it is *"executable configuration, not documentation"* — so the harder half of
this file checks that every formula, filter and epoch in every contract actually
computes against the warehouse.

The independent check is deliberate: `test_the_east_series_matches_hand_written_sql`
recomputes net revenue with SQL written out by hand rather than with a second
call into `metric.py`, because a module grading its own output proves nothing.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import duckdb
import pytest

from casefile.contract import load, load_all
from casefile.metric import (
    FormulaError,
    calendar_months,
    formula_for,
    parse,
    period_bounds,
    previous_formula,
    value,
)
from casefile.models import KPIContract

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "contracts"

pytestmark = pytest.mark.gate0


@pytest.fixture(scope="module")
def contracts() -> dict[str, KPIContract]:
    return load_all(CONTRACTS)


@pytest.fixture(scope="module")
def con(warehouse: Path) -> duckdb.DuckDBPyConnection:
    connection = duckdb.connect(str(warehouse), read_only=True)
    yield connection
    connection.close()


# ── All six validate — §44 2.7, A1 ────────────────────────────────────────────


def test_all_six_kpis_have_a_contract_and_all_six_validate(
    contracts: dict[str, KPIContract],
) -> None:
    from casefile.data.schema import KPIS

    assert set(contracts) == set(KPIS)
    assert len(contracts) == 6


@pytest.mark.parametrize("kpi", sorted(load_all(CONTRACTS)))
def test_every_contract_carries_all_nine_elements(
    contracts: dict[str, KPIContract], kpi: str
) -> None:
    """R2 counts nine: the six required elements plus composition, definition
    epochs and history. `composition` may legitimately be empty — §23's K6 -> K2
    edge is causal, not arithmetic — but the other eight may not be."""
    contract = contracts[kpi]

    assert contract.definition.strip()
    assert contract.formula.strip()
    assert contract.materiality.relative > 0
    assert contract.drivers, "a KPI with no drivers can never be investigated"
    assert contract.lineage.upstream
    assert contract.access.row or contract.access.column
    assert contract.epochs, "definition epochs are element [+], not optional decoration"
    assert contract.history_start < date(2026, 1, 1)


def test_every_driver_that_can_be_acted_on_names_a_lever_and_an_owner(
    contracts: dict[str, KPIContract],
) -> None:
    """§15 S7: *"a finding nobody owns is a sentence, not a decision."* Only
    `external_uncontrollable` drivers are allowed a null lever."""
    for contract in contracts.values():
        for driver in contract.drivers:
            if driver.type == "external_uncontrollable":
                assert driver.lever is None
            else:
                assert driver.lever is not None, f"{contract.id}/{driver.id} has no lever"
                assert driver.lever.save_rate[0] < driver.lever.save_rate[1]


def test_scenario_g_can_be_contested_because_both_drivers_are_enumerable(
    contracts: dict[str, KPIContract],
) -> None:
    """§25 G injects `pricing_change` and `supply_delay` on the same five West
    accounts in the same fortnight, on Expansion ARR. Stage 3 enumerates from the
    contract, so if either is missing here the Contested path has nothing to
    contest and the scenario silently becomes a Likely."""
    drivers = {d.id for d in contracts["expansion_arr"].drivers}
    assert {"pricing_change", "supply_delay"} <= drivers


def test_the_sparse_kpi_is_genuinely_sparse(contracts: dict[str, KPIContract]) -> None:
    """Scenario C fires off these two fields and nothing else. If `history_start`
    ever moved back past two seasonal cycles the peer-borrowed baseline would
    stop being reachable and §25 C would quietly pass by not running."""
    contract = contracts["p1_resolution_time"]
    span = (date(2026, 4, 30) - contract.history_start).days

    assert span < 2 * contract.seasonal_period_days
    assert contracts["net_revenue"].history_start < contract.history_start


# ── The formula grammar ───────────────────────────────────────────────────────


def test_a_difference_of_two_tables_parses_into_two_signed_terms() -> None:
    formula = parse("SUM(invoice_line.amount_net) - SUM(credit_note.amount)")

    assert [t.sign for t in formula.numerator] == [1, -1]
    assert formula.tables == ("invoice_line", "credit_note")
    assert formula.denominator == ()


def test_a_ratio_parses_into_numerator_and_denominator() -> None:
    formula = parse("SUM(renewal.arr_renewed) / SUM(renewal.arr_up_for_renewal)")

    assert len(formula.numerator) == 1
    assert len(formula.denominator) == 1


def test_a_trailing_number_is_a_unit_conversion_not_a_denominator_term() -> None:
    formula = parse("MEDIAN(date_diff('minute', ticket.created_at, ticket.resolved_at)) / 60.0")

    assert formula.divisor == 60.0
    assert formula.denominator == ()
    assert formula.numerator[0].aggregate == "MEDIAN"


def test_a_compound_numerator_must_be_parenthesised() -> None:
    """The one genuine ambiguity in the grammar, and why the parens are
    mandatory: `a + b / c` reads as `a + (b/c)` to a finance team and would read
    as `(a+b)/c` to a parser that simply split on the first slash. A KPI that is
    silently the wrong one of those is the exact failure §14.1 exists to
    prevent, so the two forms must parse differently."""
    grouped = parse("(SUM(renewal.arr_renewed) + SUM(opportunity.arr_value)) "
                    "/ SUM(renewal.arr_up_for_renewal)")
    assert len(grouped.numerator) == 2 and len(grouped.denominator) == 1

    with pytest.raises(FormulaError, match="ambiguous"):
        parse("SUM(renewal.arr_renewed) + SUM(opportunity.arr_value) "
              "/ SUM(renewal.arr_up_for_renewal)")


def test_a_term_reading_two_tables_is_refused() -> None:
    """Terms compose by arithmetic, never by join. A term spanning two tables
    would need join semantics the grammar does not have, and guessing them is
    how a KPI quietly starts double-counting."""
    with pytest.raises(FormulaError, match="each term must read"):
        parse("SUM(invoice_line.amount_net + credit_note.amount)")


def test_an_unknown_table_is_refused_rather_than_queried() -> None:
    with pytest.raises(FormulaError, match="no period column"):
        parse("SUM(ledger.balance)")


def test_something_that_is_not_an_aggregate_is_refused() -> None:
    with pytest.raises(FormulaError, match="not an aggregate"):
        parse("invoice_line.amount_net")


@pytest.mark.parametrize("kpi", sorted(load_all(CONTRACTS)))
def test_every_contract_formula_and_every_epoch_formula_parses(
    contracts: dict[str, KPIContract], kpi: str
) -> None:
    contract = contracts[kpi]
    assert parse(contract.formula).numerator
    for epoch in contract.epochs:
        assert parse(epoch.formula).numerator


# ── Epochs — what Stage 1's drift check reads ────────────────────────────────


def test_the_formula_in_force_changes_at_the_epoch_boundary() -> None:
    contract = load(CONTRACTS / "net_revenue.yaml")

    assert formula_for(contract, date(2025, 10, 31)) == "SUM(invoice_line.amount_gross)"
    assert formula_for(contract, date(2026, 1, 31)) == (
        "SUM(invoice_line.amount_gross) - SUM(credit_note.amount)"
    )
    assert formula_for(contract, date(2026, 2, 1)) == contract.formula
    assert previous_formula(contract, date(2026, 2, 1)) == (
        "SUM(invoice_line.amount_gross) - SUM(credit_note.amount)"
    )


def test_the_first_epoch_has_nothing_before_it() -> None:
    """Verify cannot recompute a boundary period under an adjacent epoch that
    does not exist, and returning the same formula would make the drift check
    silently pass on every period in the opening era."""
    contract = load(CONTRACTS / "net_revenue.yaml")
    assert previous_formula(contract, date(2023, 6, 1)) is None


# ── Executing a contract against the warehouse ────────────────────────────────


@pytest.mark.parametrize("region", ["East", "North"])
def test_the_series_matches_hand_written_sql(
    con: duckdb.DuckDBPyConnection, contracts: dict[str, KPIContract], region: str
) -> None:
    """The independent check. `metric.py` walks the contract; this walks the
    warehouse directly, including the credit-note subtraction and both filters
    written out by hand. A module that graded its own output would prove only
    that it is self-consistent.

    **North is here because that is where the excluded accounts live.** East
    contains none, so an East-only comparison would agree whether the
    test-account filter were applied or quietly dropped.
    """
    contract = contracts["net_revenue"]

    for period, (start, end) in (
        ("2026-03", (date(2026, 3, 1), date(2026, 3, 31))),
        ("2026-04", (date(2026, 4, 1), date(2026, 4, 30))),
    ):
        row = con.execute(
            """
            SELECT
              (SELECT coalesce(sum(l.amount_net), 0) FROM billing.invoice_line l
                WHERE l.invoice_date BETWEEN ? AND ?
                  AND l.region = ? AND l.currency = 'INR'
                  AND l.account_id NOT IN (SELECT account_id FROM crm.account WHERE is_test))
            - (SELECT coalesce(sum(c.amount), 0) FROM billing.credit_note c
                JOIN crm.account a USING (account_id)
                WHERE c.credit_date BETWEEN ? AND ? AND a.region = ?)
            """,
            [start, end, region, start, end, region],
        ).fetchone()
        assert row is not None

        computed = value(con, contract, period, {"region": region})
        assert computed == pytest.approx(row[0], rel=1e-9)


def test_the_headline_movement_is_what_the_contract_computes(
    con: duckdb.DuckDBPyConnection, contracts: dict[str, KPIContract]
) -> None:
    """§10's alert, arrived at through the contract rather than through a query
    somebody wrote for the occasion."""
    contract = contracts["net_revenue"]
    march = value(con, contract, "2026-03", {"region": "East"})
    april = value(con, contract, "2026-04", {"region": "East"})
    assert march is not None and april is not None

    assert (april - march) / march == pytest.approx(-0.08, abs=0.01)
    assert abs(april - march) > contract.materiality.absolute


@pytest.mark.parametrize("kpi", sorted(load_all(CONTRACTS)))
def test_every_contract_computes_a_value_against_the_warehouse(
    con: duckdb.DuckDBPyConnection, contracts: dict[str, KPIContract], kpi: str
) -> None:
    """A contract that validates but cannot run is documentation with a schema.
    This is the test that stops the six drifting into that."""
    computed = value(con, contracts[kpi], "2026-04", {"region": "East"})
    assert computed is not None and computed != 0.0


def test_the_unit_conversion_is_applied_so_hours_are_hours(
    con: duckdb.DuckDBPyConnection, contracts: dict[str, KPIContract]
) -> None:
    """`p1_resolution_time` is declared in hours and computed with a `/ 60.0` on
    a median of minutes. Nothing else in the contract records the unit, so a
    dropped divisor would report 5,600 "hours" and the materiality threshold of
    2.0 would fire on every period forever."""
    contract = contracts["p1_resolution_time"]
    assert contract.unit == "hours"

    row = con.execute(
        "SELECT median(date_diff('minute', created_at, resolved_at)) "
        "FROM product_ops.ticket t JOIN crm.account a USING (account_id) "
        "WHERE a.region = 'East' AND t.priority = 'P1' AND t.resolved_at IS NOT NULL "
        "AND t.created_at::DATE BETWEEN '2026-04-01' AND '2026-04-30'"
    ).fetchone()
    assert row is not None

    computed = value(con, contract, "2026-04", {"region": "East"})
    assert computed == pytest.approx(row[0] / 60.0)
    assert 1.0 < computed < 24 * 14, "a P1 median outside this band is not hours"


def test_the_test_account_filter_actually_removes_something(
    con: duckdb.DuckDBPyConnection, contracts: dict[str, KPIContract]
) -> None:
    """§14.1's first filter excludes intercompany and test accounts. A filter
    that provably removes nothing is a comment, so the exclusion list is checked
    against the number it changes — North, because no scenario uses it."""
    contract = contracts["net_revenue"]

    filtered = value(con, contract, "2026-04", {"region": "North"})
    raw = con.execute(
        "SELECT sum(amount_net) FROM billing.invoice_line "
        "WHERE region = 'North' AND invoice_date BETWEEN '2026-04-01' AND '2026-04-30'"
    ).fetchone()
    assert raw is not None and filtered is not None

    assert filtered < raw[0]
    assert con.execute("SELECT count(*) FROM crm.account WHERE is_test").fetchone() == (2,)


def test_a_filter_that_binds_to_no_term_is_an_error_not_a_no_op(
    con: duckdb.DuckDBPyConnection, contracts: dict[str, KPIContract]
) -> None:
    """The failure mode that would be invisible otherwise: a filter naming a
    table the formula never reads applies nowhere, and the metric is wrong while
    the contract still looks right."""
    contract = contracts["net_revenue"].model_copy(
        update={"filters": ["ticket.priority = 'P1'"]}
    )
    with pytest.raises(FormulaError, match="would filter nothing"):
        value(con, contract, "2026-04")


def test_a_ratio_with_nothing_due_is_undefined_rather_than_zero(
    con: duckdb.DuckDBPyConnection, contracts: dict[str, KPIContract]
) -> None:
    """No renewals were due, so the renewal rate has no value. Reporting 0%
    would open a case on a month in which nothing happened."""
    assert value(con, contracts["gross_renewal_rate"], "2022-01") is None


# ── Scenario E — the definition change, which lives only in the contract ─────


def test_the_epoch_boundary_creates_a_step_that_the_adjacent_epoch_dissolves(
    con: duckdb.DuckDBPyConnection, contracts: dict[str, KPIContract]
) -> None:
    """§25 E, and the whole shape of it: the movement exists in the semantic
    layer, never in the data. No row of the corpus changed.

    Under the formula in force, North's February falls past the 3% materiality
    threshold. Recomputed under the *adjacent* epoch — consistently, both months
    on the pre-2026-02 definition — the step largely dissolves, which is exactly
    §15's test for drift: *"a step that vanishes under a consistent definition is
    drift"*.
    """
    contract = contracts["net_revenue"]
    dimensions = {"region": "North"}
    boundary = date(2026, 2, 1)

    prior = previous_formula(contract, boundary)
    assert prior is not None, "scenario E needs an epoch before the boundary"

    def step(formula: str | None) -> float:
        before = value(con, contract, "2026-01", dimensions, formula=formula)
        after = value(con, contract, "2026-02", dimensions, formula=formula)
        assert before is not None and after is not None
        return (after - before) / before

    in_force = step(None)
    consistent = step(prior)

    assert in_force < -contract.materiality.relative, "E must look material to open at all"
    assert abs(consistent) < contract.materiality.relative, "the step must dissolve"
    assert abs(consistent) < abs(in_force) / 2


def test_the_headline_case_is_nowhere_near_an_epoch_boundary(
    contracts: dict[str, KPIContract]
) -> None:
    """The guard on scenario E: the drift check only recomputes *boundary*
    periods, so scenario A must not sit on one. If a later epoch were ever added
    in March or April, A would close as drift and the project's headline case
    would disappear into a check that was meant for someone else."""
    boundaries = {epoch.effective_from for epoch in contracts["net_revenue"].epochs}
    assert not any(date(2026, 3, 1) <= b <= date(2026, 4, 30) for b in boundaries)


# ── Periods — calendar and 4-4-5 ─────────────────────────────────────────────


def test_a_calendar_month_resolves_to_its_own_days(
    con: duckdb.DuckDBPyConnection, contracts: dict[str, KPIContract]
) -> None:
    assert period_bounds(con, contracts["net_revenue"], "2026-04") == (
        date(2026, 4, 1),
        date(2026, 4, 30),
    )
    assert period_bounds(con, contracts["net_revenue"], "2026-12") == (
        date(2026, 12, 1),
        date(2026, 12, 31),
    )


def test_a_fiscal_period_resolves_through_the_calendar_stage_zero_built(
    con: duckdb.DuckDBPyConnection, contracts: dict[str, KPIContract]
) -> None:
    """`calendar: fiscal_445` is a contract field, and a 4-4-5 period is 28 or 35
    days rather than a month. The bounds come from `meta.fiscal_calendar` so that
    a period is a fact in the warehouse rather than a date calculation repeated
    in four modules."""
    start, end = period_bounds(con, contracts["net_revenue"], "FY2027-P02")

    assert (end - start).days + 1 in (28, 35)
    assert start <= date(2026, 4, 30) <= end


def test_fiscal_and_calendar_give_the_same_answer_on_the_headline_case(
    con: duckdb.DuckDBPyConnection, contracts: dict[str, KPIContract]
) -> None:
    """Load-bearing, and not obvious. `net_revenue` declares `fiscal_445` while
    the deck's -8% was measured on calendar months. They agree only because
    exactly one billing date falls in each fiscal period — 0.8 locked that in a
    test, and this is the same fact read through the contract."""
    contract = contracts["net_revenue"]
    assert value(con, contract, "FY2027-P02", {"region": "East"}) == pytest.approx(
        value(con, contract, "2026-04", {"region": "East"})
    )


def test_an_unparseable_period_is_refused(
    con: duckdb.DuckDBPyConnection, contracts: dict[str, KPIContract]
) -> None:
    with pytest.raises(FormulaError, match="neither a calendar month"):
        period_bounds(con, contracts["net_revenue"], "Q2 2026")


def test_calendar_months_walks_a_span_inclusively() -> None:
    assert calendar_months(date(2025, 11, 3), date(2026, 2, 1)) == [
        "2025-11", "2025-12", "2026-01", "2026-02",
    ]
    assert calendar_months(date(2026, 4, 1), date(2026, 4, 30)) == ["2026-04"]
