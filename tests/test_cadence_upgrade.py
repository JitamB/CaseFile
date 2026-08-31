"""Ladder step 3.6 — the cadence upgrade path.

§15 S1: *"a stale source marks the case provisional and caps confidence, and
when the awaited watermark lands the orchestrator re-runs it — the ceiling
lifts and the verdict re-adjudicates."* The two halves of that sentence are
already proven separately: `test_verify.py`'s own
`test_a_stale_source_makes_the_case_provisional_rather_than_closing_it`
proves the first (staleness sets the flag and the ceiling), and
`test_adjudicate.py`'s `test_a_borrowed_baseline_caps_confirmed_at_likely`
proves the second (the ceiling actually caps a verdict, on a synthetic case
built to reach Confirmed — no real generated scenario does, by design: Dose
cannot pass below n = 5). What neither proves is the thing this ladder step
is actually about: that `run_case` itself, called again with the watermark
moved, is the re-run — not a special code path, the same function, on the
same real case, producing a genuinely different `VerificationResult`.

`as_of` is not touched here — the watermark itself is, the same technique
`test_verify.py`'s own staleness test already uses, and the more faithful
one: it is the batch that is late or has landed, not the clock.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import duckdb
import pytest

from casefile.contract import load_all
from casefile.llm import StubProvider
from casefile.models import KPIContract
from casefile.orchestrator import run_case

ROOT = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.gate3


@pytest.fixture(scope="module")
def contract() -> KPIContract:
    return load_all(ROOT / "contracts")["net_revenue"]


@pytest.fixture(scope="module")
def con(warehouse: Path) -> duckdb.DuckDBPyConnection:
    connection = duckdb.connect(str(warehouse), read_only=True)
    yield connection
    connection.close()


@pytest.fixture
def late_batch(warehouse: Path, tmp_path: Path) -> duckdb.DuckDBPyConnection:
    """A throwaway copy with billing's watermark pushed back — the batch has
    not landed yet, from this connection's point of view."""
    copy = tmp_path / "late.duckdb"
    shutil.copy(warehouse, copy)
    connection = duckdb.connect(str(copy))
    connection.execute(
        "UPDATE meta.watermark SET watermark = watermark - INTERVAL 40 HOUR "
        "WHERE source = 'billing'"
    )
    yield connection
    connection.close()


def test_a_late_batch_runs_the_case_provisional_rather_than_dropping_it(
    late_batch: duckdb.DuckDBPyConnection, contract: KPIContract
) -> None:
    case = run_case(contract, "2026-04", {"region": "East"}, late_batch, StubProvider())
    assert case.verification.passed is True, "a late batch is not a reason to drop a real case"
    assert case.verification.provisional is True
    assert case.verification.confidence_ceiling == "likely"
    # provisional does not mean degraded — the whole chain still ran
    assert case.decomposition is not None
    assert case.verdict is not None
    assert case.recommendation is not None


def test_the_same_case_re_run_once_the_batch_lands_is_no_longer_provisional(
    con: duckdb.DuckDBPyConnection, contract: KPIContract
) -> None:
    """The real warehouse, unmutated — the batch this same case was waiting
    for, landed. Same contract, same period, same dimensions, same function:
    `run_case` is the re-run, not a special path for one."""
    case = run_case(contract, "2026-04", {"region": "East"}, con, StubProvider())
    assert case.verification.provisional is False
    assert case.verification.confidence_ceiling is None


def test_the_ceiling_is_the_only_thing_that_moves(
    late_batch: duckdb.DuckDBPyConnection, con: duckdb.DuckDBPyConnection, contract: KPIContract
) -> None:
    """The movement itself does not depend on which batch is late — §15's
    own point about a stale source ("does not close the case") holds because
    nothing about the business fact changes, only how much confidence the
    case is allowed to state about it."""
    late = run_case(contract, "2026-04", {"region": "East"}, late_batch, StubProvider())
    landed = run_case(contract, "2026-04", {"region": "East"}, con, StubProvider())

    assert late.decomposition is not None
    assert landed.decomposition is not None
    assert late.decomposition.total_delta == pytest.approx(landed.decomposition.total_delta)
    assert late.verdict is not None and landed.verdict is not None
    assert {a.driver_id for a in late.verdict.attribution} == {
        a.driver_id for a in landed.verdict.attribution
    }
