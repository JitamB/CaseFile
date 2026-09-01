"""scan.py — continuous operation, pieces 1-3 of 4 (see
`docs/continuous-operation-plan.md`).

Cheapest first, since `verify()` dominates cost and a full `run_case()` is
heavier still: the period/region lookups are proven fast and standalone
first, then `scan()` itself across all six real contracts (24 slices, still
cheap relative to what follows), then the one test that pays the heaviest
real `run_case()` cost (marked `gate1`, same cost class as `test_verify.py`/
`test_materiality.py`'s own full-grid sweeps), then the cadence/casestore
integration, then the scheduler loop — proven with a fake `sleep` and no
real `run_case()` cost at all.
"""

from __future__ import annotations

import json
import shutil
from datetime import date, timedelta
from pathlib import Path

import duckdb
import pytest

from casefile import casestore
from casefile import scan as scan_module
from casefile.contract import load_all
from casefile.llm import StubProvider
from casefile.metric import calendar_months, value
from casefile.models import Case, KPIContract
from casefile.scan import ScanError, latest_closed_period, regions, run_scheduled, scan_slice
from casefile.stats.materiality import assess

ROOT = Path(__file__).resolve().parents[1]


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


# ── 1 · Period and region lookups — fast, no run_case() ──────────────────────


@pytest.fixture
def writable(warehouse: Path, tmp_path: Path) -> duckdb.DuckDBPyConnection:
    """A throwaway copy, so a test can mutate a watermark on purpose."""
    copy = tmp_path / "writable.duckdb"
    shutil.copy(warehouse, copy)
    connection = duckdb.connect(str(copy))
    yield connection
    connection.close()


def test_latest_closed_period_resolves_to_the_real_committed_watermarks_month(
    con: duckdb.DuckDBPyConnection, contracts: dict[str, KPIContract]
) -> None:
    """The committed corpus's own `AS_OF` (2026-05-01 06:00) sits just past
    April's close, so billing's real watermark already reaches April's own
    last day — the same reason §10's worked example (net_revenue, East,
    2026-04) is the slice a scan run today would actually pick up."""
    assert latest_closed_period(con, contracts["net_revenue"]) == "2026-04"


def test_latest_closed_period_steps_back_a_month_when_the_source_is_mid_month(
    writable: duckdb.DuckDBPyConnection, contracts: dict[str, KPIContract]
) -> None:
    """A watermark inside April means April is still landing — the candidate
    steps back to March, the last month that actually finished."""
    writable.execute(
        "UPDATE meta.watermark SET watermark = '2026-04-15 00:00:00' WHERE source = 'billing'"
    )
    assert latest_closed_period(writable, contracts["net_revenue"]) == "2026-03"


def test_latest_closed_period_treats_the_watermark_reaching_month_end_as_closed(
    writable: duckdb.DuckDBPyConnection, contracts: dict[str, KPIContract]
) -> None:
    """The real committed watermark always lands strictly past month-end, so
    this is the one test that actually exercises the `>=` boundary itself
    rather than a value that would pass under `>` too."""
    writable.execute(
        "UPDATE meta.watermark SET watermark = '2026-04-30 00:00:00' WHERE source = 'billing'"
    )
    assert latest_closed_period(writable, contracts["net_revenue"]) == "2026-04"


def test_latest_closed_period_raises_for_a_source_with_no_watermark(
    con: duckdb.DuckDBPyConnection, contracts: dict[str, KPIContract]
) -> None:
    contract = contracts["net_revenue"]
    broken = contract.model_copy(
        update={"refresh": contract.refresh.model_copy(update={"source": "no_such_source"})}
    )
    with pytest.raises(ScanError):
        latest_closed_period(con, broken)


def test_regions_lists_every_real_non_test_region_sorted(
    con: duckdb.DuckDBPyConnection,
) -> None:
    # The same four regions test_verify.py's own full-grid sweep iterates —
    # sorted() already puts them in that order.
    assert regions(con) == ["APAC", "East", "North", "West"]


# ── 2 · scan() over all six contracts — the validated default behaviour ──────


def test_scan_sweeps_every_contract_without_crashing_on_an_unverifiable_slice(
    con: duckdb.DuckDBPyConnection, contracts: dict[str, KPIContract], tmp_path: Path
) -> None:
    """The design decision put to the user directly and confirmed: all six
    contracts per scan, not narrowed to net_revenue first. Measured against
    the real committed warehouse, not assumed: 7 of the 24 resulting slices
    (gross_renewal_rate/new_business_arr/nrr, each missing a comparison
    period or dense-enough history for at least one region) raise before
    `verify()` can even return — a real, pre-existing Stage 1 gap `scan()`
    is the first thing in this codebase to hit, made resilient here rather
    than fixed at the source (see the module docstring). Every slice that
    *was* scannable, opened or not, still reaches the store.
    """
    store = casestore.connect(tmp_path / "scan_all.duckdb")
    try:
        summary = scan_module.scan(contracts, con, StubProvider(), store=store)
        assert summary.slices_checked == len(contracts) * len(regions(con))
        assert summary.slices_unverifiable == 7
        assert summary.cases_opened == 4
        assert summary.model_calls > 0

        stored = casestore.list_cases(store)
        assert len(stored) == summary.slices_checked - summary.slices_unverifiable
        assert sum(1 for c in stored if c.verification.passed) == summary.cases_opened
    finally:
        store.close()


# ── 3 · The slice-level backtest — real run_case() cost ──────────────────────


@pytest.mark.gate1
def test_the_slice_level_backtest_reproduces_verifys_own_survivors(
    con: duckdb.DuckDBPyConnection,
    contracts: dict[str, KPIContract],
    sealed: dict[str, dict],
) -> None:
    """The same statement `test_verify.py::
    test_exactly_one_movement_in_the_whole_corpus_survives_verify` already
    proves, reproduced through `scan_slice()` — the full `run_case()` cost
    every real scan pays, not `verify()` alone — which is the real proof this
    module does not change Stage 1's own established outcome (design
    decision 8, `docs/continuous-operation-plan.md`).

    Pre-filters by materiality first, the same optimisation `test_verify.py`'s
    own test already uses, so the heavier `run_case()` cost is only paid for
    the 4 slices that need it, not all 48.
    """
    contract = contracts["net_revenue"]
    periods = calendar_months(date(2023, 5, 1), date(2026, 4, 30))
    m = contract.materiality

    material: list[tuple[str, str]] = []
    for region in ("East", "West", "North", "APAC"):
        for period in periods[-12:]:
            series = [
                v
                for v in (
                    value(con, contract, p, {"region": region})
                    for p in periods[: periods.index(period) + 1]
                )
                if v is not None
            ]
            verdict = assess(
                series, period=12, relative=m.relative, absolute=m.absolute,
                z_threshold=m.z_threshold, min_persistence=m.min_persistence,
            )
            if verdict.passed:
                material.append((region, period))

    assert len(material) == 4

    cases: dict[tuple[str, str], Case] = {}
    for region, period in material:
        cases[(region, period)] = scan_slice(
            contract, period, {"region": region}, con, StubProvider()
        )

    opened = {
        key: (
            None
            if case.verification.passed
            else next(c.name for c in case.verification.checks if not c.passed)
        )
        for key, case in cases.items()
    }

    truth = sealed["A"]
    survivor = (truth["dimensions"]["region"], truth["period"])
    assert [key for key, failure in opened.items() if failure is None] == [survivor]
    assert opened[("West", "2026-03")] == "artefact"
    assert opened[("West", "2026-04")] == "artefact"
    assert opened[("North", "2026-02")] == "definition_drift"

    # The one open case went through the full chain, not just Verify —
    # scan_slice() is genuinely run_case(), not a cheaper look-alike.
    assert cases[survivor].decomposition is not None
    assert cases[survivor].verdict is not None


# ── 4 · The cadence upgrade path, through the case store ─────────────────────


def test_a_late_batch_scanned_into_the_store_upgrades_in_place(
    warehouse: Path, tmp_path: Path, contracts: dict[str, KPIContract]
) -> None:
    """Reuses `test_cadence_upgrade.py`'s exact watermark-mutation technique,
    proving the one piece that file does not: `casestore.save()`, called
    across two `scan_slice()` runs of the same real case, updates the same
    row in place rather than accumulating a duplicate once the ceiling lifts.
    """
    copy = tmp_path / "cadence.duckdb"
    shutil.copy(warehouse, copy)
    con = duckdb.connect(str(copy))
    store = casestore.connect(tmp_path / "casestore.duckdb")
    contract = contracts["net_revenue"]

    try:
        con.execute(
            "UPDATE meta.watermark SET watermark = watermark - INTERVAL 40 HOUR "
            "WHERE source = 'billing'"
        )
        late = scan_slice(contract, "2026-04", {"region": "East"}, con, StubProvider())
        casestore.save(store, late)

        con.execute(
            "UPDATE meta.watermark SET watermark = watermark + INTERVAL 40 HOUR "
            "WHERE source = 'billing'"
        )
        landed = scan_slice(contract, "2026-04", {"region": "East"}, con, StubProvider())
        casestore.save(store, landed)
    finally:
        con.close()

    assert late.id == landed.id
    assert late.verification.provisional is True
    assert late.verification.confidence_ceiling == "likely"
    assert landed.verification.provisional is False
    assert landed.verification.confidence_ceiling is None

    row_count = store.execute(
        "SELECT count(*) FROM meta.case WHERE case_id = ?", [landed.id]
    ).fetchone()
    assert row_count is not None and row_count[0] == 1

    stored = casestore.load(store, landed.id)
    assert stored is not None
    assert stored.verification.provisional is False
    assert stored.verification.confidence_ceiling is None
    store.close()


# ── 5 · The scheduler loop — no real wait ─────────────────────────────────────


def test_run_scheduled_calls_scan_the_given_number_of_times_with_no_real_wait(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`iterations=3` and a fake `sleep` that only records its calls — the
    scheduler is a real loop (`scan()`, `every` apart), proven without either
    a real wait or a real `run_case()` call, by replacing `scan()` itself."""
    scans: list[None] = []
    sleeps: list[float] = []
    monkeypatch.setattr(scan_module, "scan", lambda *args, **kwargs: scans.append(None))

    run_scheduled(
        {},  # unused — scan() is replaced above
        None,  # type: ignore[arg-type]
        None,  # type: ignore[arg-type]
        every=timedelta(seconds=5),
        iterations=3,
        sleep=sleeps.append,
    )

    assert len(scans) == 3
    assert sleeps == [5.0, 5.0]
