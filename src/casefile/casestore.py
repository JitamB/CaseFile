"""Case persistence — cross-cutting, not a pipeline stage.

Keeps every scanned `Case`, not just the ones that open, so the audit trail
`scan.py` exists to build can answer "did we actually check East this month"
for a slice that closed quietly as much as one that opened (§25's own "48
chances to cry wolf... the gate takes exactly three of them" is the same
property this makes queryable after the fact).

Always a separate DuckDB file from the warehouse. `loader.build()`
unconditionally deletes and rebuilds `data/casefile.duckdb` on every
`make data` (loader.py's own docstring: *"Rebuilds from scratch"*); a table
added there would be wiped on the next run. A loader-untouched file also
avoids read/write contention with everything that already opens the
warehouse read-only. Already covered by the repo's `*.duckdb` gitignore rule.
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb

from casefile.models import Case

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STORE_DB = ROOT / "data" / "casestore.duckdb"


def connect(db_path: Path | str = DEFAULT_STORE_DB) -> duckdb.DuckDBPyConnection:
    """Read-write connection to the case store, creating the table if new."""
    con = duckdb.connect(str(db_path))
    ensure_table(con)
    return con


def ensure_table(con: duckdb.DuckDBPyConnection) -> None:
    """`CREATE ... IF NOT EXISTS` throughout — idempotent, safe on every
    `connect()` rather than a one-time migration step nobody remembers to run."""
    con.execute("CREATE SCHEMA IF NOT EXISTS meta")
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS meta.case (
            case_id VARCHAR PRIMARY KEY,
            kpi VARCHAR,
            period VARCHAR,
            dimensions VARCHAR,
            priority DOUBLE,
            confidence VARCHAR,
            provisional BOOLEAN,
            verification_passed BOOLEAN,
            payload VARCHAR,
            updated_at TIMESTAMP
        )
        """
    )


def save(con: duckdb.DuckDBPyConnection, case: Case) -> None:
    """Insert, or update in place when `case.id` already has a row.

    The upsert is what makes the cadence-upgrade path (§15) land correctly: a
    provisional case re-scanned once its watermark lands replaces its own row
    rather than accumulating a duplicate. `payload` is
    `json.dumps(case.model_dump(mode="json"), sort_keys=True)` — the same
    convention `tools/build_real_case_fixtures.py` already established, not
    `model_dump_json()`.
    """
    con.execute(
        """
        INSERT INTO meta.case
            (case_id, kpi, period, dimensions, priority, confidence,
             provisional, verification_passed, payload, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, now())
        ON CONFLICT (case_id) DO UPDATE SET
            kpi = excluded.kpi,
            period = excluded.period,
            dimensions = excluded.dimensions,
            priority = excluded.priority,
            confidence = excluded.confidence,
            provisional = excluded.provisional,
            verification_passed = excluded.verification_passed,
            payload = excluded.payload,
            updated_at = excluded.updated_at
        """,
        [
            case.id,
            case.trigger.kpi,
            case.trigger.period,
            json.dumps(case.trigger.dimensions, sort_keys=True),
            case.priority,
            case.verdict.confidence if case.verdict is not None else None,
            case.verification.provisional,
            case.verification.passed,
            json.dumps(case.model_dump(mode="json"), sort_keys=True),
        ],
    )


def load(con: duckdb.DuckDBPyConnection, case_id: str) -> Case | None:
    """`None` for an unknown id — the caller's "was this ever scanned" check."""
    row = con.execute("SELECT payload FROM meta.case WHERE case_id = ?", [case_id]).fetchone()
    if row is None or row[0] is None:
        return None
    return Case.model_validate_json(row[0])


def list_cases(con: duckdb.DuckDBPyConnection, *, open_only: bool = False) -> list[Case]:
    """Ordered by `priority DESC` — the case-list ordering the UI already uses.

    `open_only` reads the stored `verification_passed` column directly rather
    than deserialising every row's JSON payload just to filter — `Case` has no
    separate status field, and `verification.passed` is the one existing
    boolean the rest of the test suite already treats as "worth attention"
    versus "closed for a documented reason".
    """
    where = " WHERE verification_passed" if open_only else ""
    rows = con.execute(f"SELECT payload FROM meta.case{where} ORDER BY priority DESC").fetchall()
    return [Case.model_validate_json(row[0]) for row in rows]
