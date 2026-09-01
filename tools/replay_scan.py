"""The demo-facing proof that continuous operation's pieces 1-3 (scan, the
case store, the scheduler) work end to end — without piece 4 (live data
ingestion, explicitly out of scope; see `docs/continuous-operation-plan.md`).

Mirrors `tools/build_real_case_fixtures.py`'s own `generate()` +
`build()`-into-a-tempdir pattern, then walks the corpus's own already-existing
trailing periods one at a time, calling `scan()` per period against a tempdir
case store, printing a transcript in the shape of §11's "daily loop" narrative
(`docs/01-problem-and-solution.md`). The frozen corpus cannot demonstrate time
actually advancing — `AS_OF`/`SPAN_END` are fixed constants baked into the
seed — so this walks the corpus's own real trailing months instead, the same
substitute `docs/continuous-operation-plan.md`'s design decision 7 names.

    python tools/replay_scan.py
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import duckdb

from casefile import casestore
from casefile.contract import load_all
from casefile.data.generator import generate
from casefile.data.loader import build
from casefile.llm import StubProvider
from casefile.models import KPIContract
from casefile.scan import scan

ROOT = Path(__file__).resolve().parents[1]

#: Three of the corpus's own real trailing months — enough to show the
#: mechanism (a scan that opens nothing, one that opens several, sweeping all
#: six contracts each time) without paying a full 12-month replay's cost.
PERIODS = ["2026-02", "2026-03", "2026-04"]


def main() -> None:
    contracts = load_all(ROOT / "contracts")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        generate(tmp_path / "corpus")
        db_path = build(
            raw_dir=tmp_path / "corpus" / "raw",
            db_path=tmp_path / "warehouse" / "casefile.duckdb",
            alias_path=ROOT / "data" / "account_alias.csv",
        )
        con = duckdb.connect(str(db_path), read_only=True)
        store = casestore.connect(tmp_path / "casestore.duckdb")
        try:
            for period in PERIODS:
                _replay_one_period(contracts, con, store, period)
        finally:
            con.close()
            store.close()


def _replay_one_period(
    contracts: dict[str, KPIContract],
    con: duckdb.DuckDBPyConnection,
    store: duckdb.DuckDBPyConnection,
    period: str,
) -> None:
    summary = scan(contracts, con, StubProvider(), period=period, store=store)
    print(
        f"{period}  scanned {summary.slices_checked} slices "
        f"({len(contracts)} KPIs x 4 regions) — {summary.cases_opened} opened, "
        f"{summary.slices_unverifiable} unverifiable, {summary.model_calls} model calls, "
        f"{summary.wall_ms:,.0f}ms"
    )
    opened = [
        case
        for case in casestore.list_cases(store, open_only=True)
        if case.trigger.period == period
    ]
    for case in opened:
        verdict = case.verdict
        primary = next((a for a in verdict.attribution if a.status == "primary"), None) \
            if verdict is not None else None
        detail = f"{verdict.confidence}" if verdict is not None else "?"
        if primary is not None:
            detail += f", primary driver {primary.driver_id}"
        print(f"    -> {case.id}: {detail}")


if __name__ == "__main__":
    main()
