"""Continuous operation, pieces 1-3 of 4 — scan, scheduler, case store.

Round 2 objective 1 ("detects and prioritises material KPI movements") and
§11's own "daily loop" narrative describe a system that looks at every
KPI x region slice on a cadence and opens the ones worth attention.
`orchestrator.run_case()` already does the "one case" half of that —
`_main()`'s own docstring admits the rest outright: *"which case to open is
not yet a solved problem in this codebase... this is the one case named on
stage."* This module is that missing half: which slices to check, and when.

**Piece 4 (live data ingestion) is explicitly out of scope here.** The corpus
stays the one frozen, seeded warehouse every other module already reads;
"continuous" means the scan loop is real, tested code, not that new data
arrives on its own. See `docs/continuous-operation-plan.md`.

`scan_slice()` is a thin wrapper over `run_case()`, not a separate `verify()`
call followed by `run_case()` — `run_case()` already calls `verify()` first
and returns immediately, with zero model calls, when it fails. Verifying
twice would double-pay `verify()`'s own cost (~80-100 SQL round-trips,
dominated by materiality's 36-period history scan) for nothing.

**A real gap this module found, not assumed.** Every existing test picks a
known-good contract/period/region by hand; `scan()` is the first thing in
this codebase that sweeps every contract against every region blindly, and
measured against the real committed warehouse, 7 of the 24 resulting slices
raise before `verify()` can even return a result — `_movement()`'s own
`VerifyError` ("no previous period to compare against") for a ratio KPI with
no renewal/opportunity due in one of the two periods for that region, and a
bare `ValueError` from `stats/stl.py` ("STL needs two full cycles") for a
region whose *own* series has fewer non-null observations than
`_history_is_sparse()`'s calendar-only check assumes. Both are pre-existing
Stage 1 gaps, out of scope for this module to fix (touching `verify.py`'s
sparse-history detection risks shifting the materiality calibration already
measured and committed in `docs/06-quality.md` §35.6) — logged in
`docs/DECISIONS.md` and deferred, the same "found, not fixed here" treatment
this session has given every out-of-scope gap. `scan()` treats either as "not
scannable this period," not a crash: it is counted in `ScanSummary.
slices_unverifiable` and the sweep continues, on the same principle
`run_case()` already applies one level up — closing early, or in this case
not opening at all, is a success path.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import date, datetime, timedelta

import duckdb

from casefile import casestore
from casefile.llm import LLMProvider
from casefile.metric import calendar_months, period_bounds
from casefile.models import Base, Case, KPIContract
from casefile.orchestrator import run_case


class ScanError(LookupError):
    """A contract names a source `meta.watermark` has no row for."""


class ScanSummary(Base):
    """One `scan()` call's own receipt — a `Telemetry`-style rollup one level
    up, folding every slice's own `Case` into the numbers a scheduler or a
    CLI actually wants to print. Lives here, not in `models.py` — nothing
    about it crosses the A/B/C treaty boundary `models.py`'s own docstring
    reserves for (same precedent `feedback.py`'s `FeedbackMark`/`LearningState`
    and `hypothesise.py`'s `HypothesiseResponse` already set)."""

    slices_checked: int
    cases_opened: int
    slices_unverifiable: int
    model_calls: int
    wall_ms: float


def latest_closed_period(con: duckdb.DuckDBPyConnection, contract: KPIContract) -> str:
    """The most recent calendar month `contract.refresh.source`'s own data has
    actually finished landing — read from `meta.watermark`, not assumed.

    Modelled on `verify.py`'s own private `_as_of()`/`_previous_period()` date
    math rather than inventing new date logic. A month is "closed" once the
    source's watermark reaches or passes that month's own last day; otherwise
    the previous month is the candidate. This is a starting guess for `scan()`
    to check, not a guarantee — `verify()` still runs its own freshness and
    completeness checks on whatever slice this resolves to.
    """
    row = con.execute(
        "SELECT watermark FROM meta.watermark WHERE source = ?", [contract.refresh.source]
    ).fetchone()
    if row is None or row[0] is None:
        raise ScanError(
            f"{contract.id} names source {contract.refresh.source!r}, which has no watermark"
        )
    watermark: datetime = row[0]
    candidate = f"{watermark.year:04d}-{watermark.month:02d}"
    _, end = period_bounds(con, contract, candidate)
    if watermark.date() >= end:
        return candidate
    return _previous_period(con, contract, candidate)


def _previous_period(con: duckdb.DuckDBPyConnection, contract: KPIContract, period: str) -> str:
    _, end = period_bounds(con, contract, period)
    labels = calendar_months(date(end.year - 1, end.month, 1), end)
    if len(labels) < 2:
        raise ScanError(f"{contract.id} {period}: no previous period")
    return labels[-2]


def regions(con: duckdb.DuckDBPyConnection) -> list[str]:
    """Every non-test region in the corpus.

    All six contracts declare `region` as `decomposition_dims[0]`
    (`grep -oh "decomposition_dims: \\[[a-z, ]*" contracts/*.yaml` confirms
    it), so this is the one dimension every scan needs. Reuses `verify.py`'s
    own `_peer_expectation` query shape, with the `is_test` exclusion
    `net_revenue.yaml`'s own formula filter already implies — a region that
    only test accounts live in is not a region worth scanning.
    """
    rows = con.execute(
        "SELECT DISTINCT region FROM crm.account WHERE region IS NOT NULL AND NOT is_test"
    ).fetchall()
    return sorted(str(row[0]) for row in rows)


def scan_slice(
    contract: KPIContract,
    period: str,
    dimensions: dict[str, str],
    con: duckdb.DuckDBPyConnection,
    provider: LLMProvider,
    as_of: datetime | None = None,
) -> Case:
    """One KPI x period x dimension slice, end to end — a place to hang
    scan-specific timing or logging without touching `run_case()` itself."""
    return run_case(contract, period, dimensions, con, provider, as_of)


def scan(
    contracts: dict[str, KPIContract],
    con: duckdb.DuckDBPyConnection,
    provider: LLMProvider,
    *,
    period: str | None = None,
    store: duckdb.DuckDBPyConnection | None = None,
) -> ScanSummary:
    """Every contract, every region.

    Persists every scanned slice when `store` is given — not only the ones
    that open a case. `run_case()` runs per candidate regardless, so this adds
    no cost, and it is what lets `casestore.list_cases()` answer "did we
    actually check East this month" for a slice that closed quietly.

    A slice `verify()` cannot even evaluate (see the module docstring's own
    real finding) is counted in `slices_unverifiable`, not raised — one
    unscannable region/contract combination does not abort the rest of the
    sweep.
    """
    t0 = time.perf_counter()
    slices_checked = 0
    cases_opened = 0
    slices_unverifiable = 0
    model_calls = 0

    for contract in contracts.values():
        resolved = period if period is not None else latest_closed_period(con, contract)
        for region in regions(con):
            slices_checked += 1
            try:
                case = scan_slice(contract, resolved, {"region": region}, con, provider)
            except ValueError:
                # VerifyError (no comparison period) and stats/stl.py's own
                # ValueError (a sparse series verify.py's calendar-only check
                # missed) both land here — see the module docstring.
                slices_unverifiable += 1
                continue
            if case.verification.passed:
                cases_opened += 1
            model_calls += case.telemetry.model_calls
            if store is not None:
                casestore.save(store, case)

    return ScanSummary(
        slices_checked=slices_checked,
        cases_opened=cases_opened,
        slices_unverifiable=slices_unverifiable,
        model_calls=model_calls,
        wall_ms=_ms(t0),
    )


def run_scheduled(
    contracts: dict[str, KPIContract],
    con: duckdb.DuckDBPyConnection,
    provider: LLMProvider,
    *,
    every: timedelta,
    iterations: int | None = None,
    sleep: Callable[[float], None] = time.sleep,
    store: duckdb.DuckDBPyConnection | None = None,
) -> None:
    """`scan()`, `every` apart — real, tested, in-process code: "a Python
    function on a timer," not Airflow/Kafka/a daemon framework. Scans
    immediately on the first iteration, then waits `every` between each
    subsequent one. `iterations=None` runs until interrupted; a test passes a
    small `iterations` and a fake `sleep` that just records calls, so this is
    unit-testable without a real wait. The OS-level production answer
    (crontab/systemd-timer calling `python -m casefile.scan` on each
    contract's own `refresh.cadence`) is documented, not built, here — see
    `docs/continuous-operation-plan.md`.
    """
    count = 0
    while iterations is None or count < iterations:
        scan(contracts, con, provider, store=store)
        count += 1
        if iterations is not None and count >= iterations:
            break
        sleep(every.total_seconds())


def _ms(t0: float) -> float:
    return (time.perf_counter() - t0) * 1000.0


def main() -> None:  # pragma: no cover — exercised by `make scan`, not pytest
    """Mirrors `orchestrator._main()`'s own template: repo-root paths, a
    read-only warehouse connection, `load_all`. Diverges on the provider
    default — `StubProvider()`, matching `test_cadence_upgrade.py` and
    `tools/build_real_case_fixtures.py`'s own precedent (deterministic,
    offline, zero cost, safe for a replay demo) — with `--live` as an
    explicit opt-in to `provider_from_env()`, mirroring how `orchestrator.
    _main()` already fails loudly, not silently, on a live-provider gap.
    """
    import sys
    from pathlib import Path

    from casefile.contract import load_all
    from casefile.llm import CacheMiss, StubProvider, provider_from_env

    root = Path(__file__).resolve().parents[2]
    con = duckdb.connect(str(root / "data" / "casefile.duckdb"), read_only=True)
    store = casestore.connect()
    try:
        contracts = load_all(root / "contracts")
        provider = provider_from_env() if "--live" in sys.argv else StubProvider()
        try:
            summary = scan(contracts, con, provider, store=store)
        except CacheMiss as exc:
            print(
                "No recorded LLM response for this exact prompt, and "
                "CASEFILE_LLM_REPLAY has no live provider to fall back to.\n"
                "Either record one (CASEFILE_LLM_REPLAY=false, a real "
                "ANTHROPIC_API_KEY, then re-run with --live) or drop --live.\n"
                f"{exc}",
                file=sys.stderr,
            )
            raise SystemExit(1) from exc
    finally:
        con.close()
        store.close()

    print(
        f"scanned {summary.slices_checked} slices, opened {summary.cases_opened} cases, "
        f"{summary.slices_unverifiable} unverifiable, {summary.model_calls} model calls, "
        f"{summary.wall_ms:,.0f}ms"
    )


if __name__ == "__main__":  # pragma: no cover
    main()
