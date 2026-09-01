"""casestore.py — round-trip save/load/upsert on synthetic `Case` objects.

No `run_case()` call anywhere here: casestore.py's own job is persistence,
not computation, so these are proven against hand-built `Case` objects, the
same "cheapest first" convention `test_scan.py` uses for its own fast checks.
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pytest

from casefile import casestore
from casefile.models import (
    Attribution,
    Case,
    Confidence,
    Telemetry,
    Trigger,
    Verdict,
    VerificationCheck,
    VerificationResult,
)


def _case(
    case_id: str,
    *,
    priority: float = 1.0,
    passed: bool = True,
    confidence: Confidence | None = None,
) -> Case:
    verdict = None
    if confidence is not None:
        verdict = Verdict(
            attribution=[
                Attribution(driver_id="driver_x", share=None, status="primary", eliminated_by=None)
            ],
            confidence=confidence,
        )
    return Case(
        id=case_id,
        trigger=Trigger(
            kpi="net_revenue", period="2026-04", dimensions={"region": "East"},
            delta=-1.0, delta_relative=-0.01,
        ),
        verification=VerificationResult(
            passed=passed,
            checks=[VerificationCheck(name="materiality", passed=passed, detail="synthetic")],
            freshness_hours=1.0,
        ),
        priority=priority,
        telemetry=Telemetry(),
        verdict=verdict,
    )


@pytest.fixture
def store(tmp_path: Path) -> duckdb.DuckDBPyConnection:
    connection = casestore.connect(tmp_path / "casestore.duckdb")
    yield connection
    connection.close()


def test_a_fresh_save_can_be_loaded_back(store: duckdb.DuckDBPyConnection) -> None:
    case = _case("case-1", confidence="likely")
    casestore.save(store, case)
    loaded = casestore.load(store, "case-1")
    assert loaded == case


def test_load_returns_none_for_an_unknown_id(store: duckdb.DuckDBPyConnection) -> None:
    assert casestore.load(store, "nope") is None


def test_saving_again_upserts_rather_than_duplicating(store: duckdb.DuckDBPyConnection) -> None:
    casestore.save(store, _case("case-1", priority=1.0, passed=False))
    casestore.save(store, _case("case-1", priority=9.0, passed=True))

    rows = store.execute("SELECT count(*) FROM meta.case WHERE case_id = 'case-1'").fetchone()
    assert rows is not None and rows[0] == 1

    loaded = casestore.load(store, "case-1")
    assert loaded is not None
    assert loaded.priority == 9.0
    assert loaded.verification.passed is True


def test_list_cases_open_only_filters_by_verification_passed(
    store: duckdb.DuckDBPyConnection,
) -> None:
    casestore.save(store, _case("case-open", passed=True))
    casestore.save(store, _case("case-closed", passed=False))

    every = casestore.list_cases(store)
    assert {c.id for c in every} == {"case-open", "case-closed"}

    open_only = casestore.list_cases(store, open_only=True)
    assert {c.id for c in open_only} == {"case-open"}


def test_the_flat_columns_match_the_cases_own_fields(store: duckdb.DuckDBPyConnection) -> None:
    """The flat columns (kpi, period, dimensions, priority, confidence,
    provisional, verification_passed) exist so a lightweight query can read
    case metadata without deserialising `payload` — design decision 9's own
    reasoning for `verification_passed` applies to the rest of the row too.
    `load()`/`list_cases()` only ever read `payload` back (plus
    `verification_passed` for `open_only`), so this is the one place a
    mistake in `save()`'s column mapping for the other flat columns would be
    caught at all.
    """
    case = _case("case-1", priority=3.5, passed=False, confidence="contested")
    casestore.save(store, case)

    row = store.execute(
        "SELECT kpi, period, dimensions, priority, confidence, provisional, "
        "verification_passed FROM meta.case WHERE case_id = 'case-1'"
    ).fetchone()
    assert row is not None
    kpi, period, dimensions, priority, confidence, provisional, verification_passed = row
    assert kpi == case.trigger.kpi
    assert period == case.trigger.period
    assert json.loads(dimensions) == case.trigger.dimensions
    assert priority == case.priority
    assert confidence == case.verdict.confidence
    assert provisional == case.verification.provisional
    assert verification_passed == case.verification.passed


def test_list_cases_orders_by_priority_descending(store: duckdb.DuckDBPyConnection) -> None:
    casestore.save(store, _case("case-low", priority=1.0))
    casestore.save(store, _case("case-high", priority=9.0))
    casestore.save(store, _case("case-mid", priority=5.0))

    ordered = [c.id for c in casestore.list_cases(store)]
    assert ordered == ["case-high", "case-mid", "case-low"]
