"""Orchestrator — §15 S0–S7, wired end to end. Ladder step 3.1.

*"Alert → closed case."* S0 (conform) already happened at `make data` time —
every stage below reads the conformed warehouse, never a raw source. S8a/S8b
(entitle, narrate) are deliberately not called here: they run per *persona*,
over an already-complete `Case`, which is a different question from "what is
the case" — `run_case` answers the second one.

A case that fails Verify returns here immediately, with an empty ledger and
no verdict — §15's own words, "closing early is a success path, not a
degraded one" (`Case`'s own docstring in `models.py`). Everything after Verify
is a straight line: decompose → hypothesise → probe + extract → challenge →
adjudicate → recommend, each stage's `Usage`/wall time folded into the one
`Telemetry` object every downstream consumer reads.
"""

from __future__ import annotations

import time
from datetime import date, datetime

import duckdb

from casefile.engine.adjudicate import adjudicate
from casefile.engine.challenge import challenge
from casefile.engine.decompose import decompose
from casefile.engine.evidence import extract_claims, gather_probes
from casefile.engine.hypothesise import hypothesise
from casefile.engine.recommend import recommend
from casefile.engine.verify import verify
from casefile.llm import LLMProvider
from casefile.metric import calendar_months, period_bounds, value
from casefile.models import Case, KPIContract, StageTiming, Telemetry, Trigger, Usage


def run_case(
    contract: KPIContract,
    period: str,
    dimensions: dict[str, str],
    con: duckdb.DuckDBPyConnection,
    provider: LLMProvider,
    as_of: datetime | None = None,
) -> Case:
    """S1 through S7 for one KPI, period and dimension slice. Never raises on
    a real business outcome — Verify failing, or every hypothesis eliminated —
    those are `Case` states, not exceptions. `AdjudicateError`'s "nothing was
    challenged" is the one thing this does not guard: every contract has at
    least one driver with a `probe_sql`, so it is unreachable today, the same
    reason nothing here special-cases an empty hypothesis list either."""
    stages: list[StageTiming] = []
    calls: list[Usage] = []
    case_id = _case_id(contract, period, dimensions)

    t0 = time.perf_counter()
    result = verify(con, contract, period, dimensions, as_of)
    stages.append(StageTiming(stage="s1_verify", wall_ms=_ms(t0)))

    delta, delta_relative = _trigger_delta(con, contract, period, dimensions)
    trigger = Trigger(
        kpi=contract.id, period=period, dimensions=dimensions,
        delta=delta, delta_relative=delta_relative,
    )

    if not result.passed:
        return Case(
            id=case_id, trigger=trigger, verification=result, priority=0.0,
            telemetry=Telemetry(calls=calls, stages=stages),
        )

    t0 = time.perf_counter()
    tree = decompose(con, contract, period, dimensions)
    stages.append(StageTiming(stage="s2_decompose", wall_ms=_ms(t0)))
    trigger = trigger.model_copy(
        update={"delta": tree.total_delta, "delta_relative": delta_relative}
    )

    t0 = time.perf_counter()
    hypotheses, s3_usage = hypothesise(contract, trigger, tree.footprint, provider)
    calls.append(s3_usage)
    stages.append(StageTiming(stage="s3_hypothesise", wall_ms=_ms(t0), used_model=True))

    t0 = time.perf_counter()
    probed = gather_probes(contract, hypotheses, tree.footprint, con, as_of)
    stages.append(StageTiming(stage="s4a_probes", wall_ms=_ms(t0)))

    t0 = time.perf_counter()
    extracted, s4c_usages = extract_claims(
        contract, hypotheses, tree.footprint, con, provider, as_of
    )
    calls.extend(s4c_usages)
    stages.append(
        StageTiming(stage="s4c_extract", wall_ms=_ms(t0), used_model=bool(s4c_usages))
    )
    ledger = probed + extracted

    t0 = time.perf_counter()
    matrices, challenge_items = challenge(contract, hypotheses, tree, con, as_of)
    ledger = ledger + challenge_items
    stages.append(StageTiming(stage="s5_challenge", wall_ms=_ms(t0)))

    t0 = time.perf_counter()
    verdict, question, priority = adjudicate(
        contract, hypotheses, tree, ledger, matrices, result
    )
    stages.append(StageTiming(stage="s6_adjudicate", wall_ms=_ms(t0)))

    t0 = time.perf_counter()
    recommendation = recommend(contract, verdict, tree, dimensions)
    stages.append(StageTiming(stage="s7_recommend", wall_ms=_ms(t0)))

    return Case(
        id=case_id, trigger=trigger, verification=result, decomposition=tree,
        hypotheses=hypotheses, ledger=ledger, tests=matrices, verdict=verdict,
        recommendation=recommendation, open_question=question, priority=priority,
        telemetry=Telemetry(calls=calls, stages=stages),
    )


def _ms(t0: float) -> float:
    return (time.perf_counter() - t0) * 1000.0


def _case_id(contract: KPIContract, period: str, dimensions: dict[str, str]) -> str:
    dims = "-".join(v.lower().replace(" ", "_") for v in dimensions.values())
    return f"case-{period}-{contract.id}" + (f"-{dims}" if dims else "")


def _trigger_delta(
    con: duckdb.DuckDBPyConnection, contract: KPIContract, period: str, dimensions: dict[str, str]
) -> tuple[float, float]:
    """The raw movement §10's alert states — computed independently of Verify,
    the same calendar-aware "previous period" lookup `decompose.py`'s own
    window uses, since `Trigger` has to exist even for a case that closes at
    Verify, before `decompose` ever runs."""
    start, end = period_bounds(con, contract, period)
    labels = calendar_months(date(start.year - 1, start.month, 1), end)
    if len(labels) < 2:
        return 0.0, 0.0
    previous = labels[-2]

    current_value = value(con, contract, period, dimensions)
    previous_value = value(con, contract, previous, dimensions)
    if current_value is None or previous_value is None:
        return 0.0, 0.0
    delta = current_value - previous_value
    return delta, (delta / previous_value if previous_value else 0.0)


def _main() -> None:  # pragma: no cover — exercised by `make demo`, not pytest
    """§10's own worked example: Net Revenue, East, 2026-04. `make demo`'s
    whole job is proving this runs end to end; which case to open is not yet
    a solved problem in this codebase (§25's daily-loop scan across every
    KPI×dimension is future scope), so this is the one case named on stage."""
    import sys
    from pathlib import Path

    from casefile.contract import load_all
    from casefile.llm import CacheMiss, provider_from_env

    root = Path(__file__).resolve().parents[2]
    con = duckdb.connect(str(root / "data" / "casefile.duckdb"), read_only=True)
    try:
        contract = load_all(root / "contracts")["net_revenue"]
        provider = provider_from_env()
        try:
            case = run_case(contract, "2026-04", {"region": "East"}, con, provider)
        except CacheMiss as exc:
            print(
                "No recorded LLM response for this prompt, and "
                "CASEFILE_LLM_REPLAY has no live provider to fall back to.\n"
                "Either record one (CASEFILE_LLM_REPLAY=false, a real "
                "ANTHROPIC_API_KEY, then re-run) or use an already-cached run.\n"
                f"{exc}",
                file=sys.stderr,
            )
            raise SystemExit(1) from exc
    finally:
        con.close()

    print(_report(case))


def _report(case: Case) -> str:
    lines = [f"CASE {case.id}", f"  verified: {case.verification.passed}"]
    if case.decomposition is not None:
        lines.append(
            f"  moved: {case.decomposition.total_delta:,.0f} "
            f"({case.trigger.delta_relative:+.1%})"
        )
    if case.verdict is not None:
        primary = next(
            (a for a in case.verdict.attribution if a.status == "primary"), None
        )
        lines.append(f"  confidence: {case.verdict.confidence}")
        if primary is not None:
            lines.append(f"  primary driver: {primary.driver_id}")
    if case.recommendation is not None:
        lines.append(f"  action: {case.recommendation.action}")
    if case.open_question is not None:
        lines.append(f"  still open: {case.open_question.question}")
    lines.append(f"  priority: {case.priority:,.0f}")
    return "\n".join(lines)


if __name__ == "__main__":  # pragma: no cover
    _main()
