"""Stage 1 — Verify. §15 S1.

*"Checking the patient is actually sick before treating them. A surprising number
of business panics die right here — each saving three days."*

**In:** a KPI, a period, the conformed warehouse, the contract.
**Out:** a `VerificationResult`, and a case that either opens or closes.

Five checks, in §15's order. Four of them can close the case; the fifth cannot:

| Check | Closes the case when |
|---|---|
| freshness | **never** — it marks the case provisional and caps confidence, and the |
| | orchestrator re-runs it when the awaited batch lands |
| completeness | rows are still landing, so the number is not yet the number |
| definition drift | the step vanishes under a consistent definition — **scenario E** |
| artefact | one record *is* the movement — **scenario D** |
| materiality | noise, or real but not worth an afternoon |

**Zero model calls, by construction.** Nothing in this module or anything it
imports can reach `casefile.llm`; `tests/test_verify.py` asserts that over the
actual import graph rather than trusting the absence of an import line. That is
what makes §25 D and E close *for free*, and it is the cost gate §15 names.

**One deviation from §15, deliberately.** §15 describes completeness as *"count
vs 28-day median by weekday"*. Billing writes one date per month, so a weekday
median is vacuous here — but the deeper problem is that a row-count comparison
cannot tell a missing batch from a churned customer. Scenario A is exactly that:
two of East's 49 accounts leave, the row count drops 4%, and a count-based
completeness check would close the headline case as incomplete data. So
completeness is measured as **the share of the period's records that arrived
within their source's SLA** — which is what *"rows still landing"* actually
means, and it moves only when ingestion is late rather than when business
changes.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import duckdb

from casefile.metric import (
    PERIOD_COLUMN,
    calendar_months,
    parse,
    period_bounds,
    previous_formula,
    value,
)
from casefile.models import KPIContract, Trigger, VerificationCheck, VerificationResult
from casefile.stats.materiality import assess

#: How many periods of history the materiality gate reads. Three seasonal cycles
#: is what §22 gives billing, and STL needs two.
HISTORY_PERIODS = 36
#: How far back the peer-borrowed baseline and the artefact check look.
TRAILING_PERIODS = 3


class VerifyError(ValueError):
    """The period cannot be verified at all — missing history, no comparison."""


@dataclass(frozen=True)
class _Movement:
    latest: float
    previous: float

    @property
    def delta(self) -> float:
        return self.latest - self.previous

    @property
    def relative(self) -> float:
        return self.delta / self.previous if self.previous else 0.0


def verify(
    con: duckdb.DuckDBPyConnection,
    contract: KPIContract,
    period: str,
    dimensions: dict[str, str] | None = None,
    as_of: datetime | None = None,
) -> VerificationResult:
    """Run all five checks and return the result.

    All five always run, and the result carries all five. Reporting only the
    first failure sends somebody to fix the wrong thing — a case that is *both*
    a refund batch and immaterial should say so.
    """
    dimensions = dimensions or {}
    as_of = as_of or _as_of(con)
    start, end = period_bounds(con, contract, period)

    freshness_hours, freshness = _freshness(con, contract, as_of)
    checks = [
        freshness,
        _completeness(con, contract, period, dimensions),
        _definition_drift(con, contract, period, dimensions, end),
    ]

    movement = _movement(con, contract, period, dimensions)
    checks.append(_artefact(con, contract, period, dimensions, movement, start, end))

    borrowed = _history_is_sparse(contract, end)
    if borrowed:
        material, robust_z, persistence = _sparse_materiality(
            con, contract, period, dimensions, movement
        )
    else:
        material, robust_z, persistence = _materiality(con, contract, period, dimensions)
    checks.append(material)

    provisional = not freshness.passed
    ceiling = "likely" if provisional or borrowed else None

    return VerificationResult(
        passed=all(check.passed for check in checks if check.name != "freshness"),
        checks=checks,
        freshness_hours=freshness_hours,
        baseline="borrowed" if borrowed else "own",
        confidence_ceiling=ceiling,
        provisional=provisional,
        robust_z=robust_z,
        persistence=persistence,
    )


def trigger_for(
    con: duckdb.DuckDBPyConnection,
    contract: KPIContract,
    period: str,
    dimensions: dict[str, str] | None = None,
) -> Trigger:
    """The alert that opened the investigation, as §14.3's `Trigger`."""
    movement = _movement(con, contract, period, dimensions or {})
    return Trigger(
        kpi=contract.id,
        period=period,
        dimensions=dimensions or {},
        delta=movement.delta,
        delta_relative=movement.relative,
    )


# ── The movement under test ───────────────────────────────────────────────────


def _movement(
    con: duckdb.DuckDBPyConnection,
    contract: KPIContract,
    period: str,
    dimensions: dict[str, str],
) -> _Movement:
    series = _series(con, contract, period, dimensions, periods=2)
    if len(series) < 2:
        raise VerifyError(f"{contract.id} {period}: no previous period to compare against")
    if series[-2] == 0:
        # A relative movement against zero is undefined, not infinite. This is
        # what a period outside the KPI's history looks like from in here, and
        # reporting "no change" for a month nobody has a comparison for is worse
        # than refusing.
        raise VerifyError(
            f"{contract.id} {period}: no previous period to compare against — the "
            "preceding period is zero, so a relative movement has no meaning"
        )
    return _Movement(latest=series[-1], previous=series[-2])


def _series(
    con: duckdb.DuckDBPyConnection,
    contract: KPIContract,
    period: str,
    dimensions: dict[str, str],
    periods: int,
    formula: str | None = None,
) -> list[float]:
    """The KPI over the `periods` periods ending with `period`, dropping any
    leading periods the KPI is undefined for."""
    _, end = period_bounds(con, contract, period)
    start = date(end.year - (periods // 12) - 1, end.month, 1)
    labels = calendar_months(start, end)
    labels = labels[-periods:] if periods else labels

    values: list[float] = []
    for label in labels:
        computed = value(con, contract, label, dimensions, formula=formula)
        if computed is None:
            values.clear()  # a gap resets the run; STL cannot span one
            continue
        values.append(computed)
    return values


# ── 1 · Freshness ─────────────────────────────────────────────────────────────


def _as_of(con: duckdb.DuckDBPyConnection) -> datetime:
    """The simulated present, recorded by Stage 0 rather than read from a clock —
    §24's whole point is that a demo recorded today still says the same thing
    next month."""
    row = con.execute("SELECT max(as_of) FROM meta.watermark").fetchone()
    if row is None or row[0] is None:
        raise VerifyError("meta.watermark has no as_of; the warehouse was not built")
    return row[0]


def _freshness(
    con: duckdb.DuckDBPyConnection, contract: KPIContract, as_of: datetime
) -> tuple[float, VerificationCheck]:
    """`now − watermark` against `refresh.sla_hours`.

    A stale source does **not** close the case. §15: it marks the case
    provisional and caps confidence, and when the awaited watermark lands the
    orchestrator re-runs it and the ceiling lifts. Heterogeneous cadences are a
    visible behaviour, not metadata.
    """
    source = contract.refresh.source
    row = con.execute(
        "SELECT watermark FROM meta.watermark WHERE source = ?", [source]
    ).fetchone()
    if row is None or row[0] is None:
        raise VerifyError(f"{contract.id} names source {source!r}, which has no watermark")

    hours = (as_of - row[0]).total_seconds() / 3600.0
    sla = contract.refresh.sla_hours
    fresh = hours <= sla

    return hours, VerificationCheck(
        name="freshness",
        passed=fresh,
        detail=(
            f"{source} watermark {hours:.1f}h old against a {sla:g}h SLA"
            if fresh
            else f"{source} is {hours:.1f}h stale against a {sla:g}h SLA — the case is "
            "provisional and confidence is capped until the batch lands"
        ),
        statistic=round(hours, 2),
    )


# ── 2 · Completeness ──────────────────────────────────────────────────────────


def _completeness(
    con: duckdb.DuckDBPyConnection,
    contract: KPIContract,
    period: str,
    dimensions: dict[str, str],
) -> VerificationCheck:
    """*"Rows still landing"* — see the module docstring for why this is measured
    as ingest punctuality rather than as a row count."""
    start, end = period_bounds(con, contract, period)
    deadline = datetime.combine(end, datetime.min.time()) + timedelta(
        days=1, hours=contract.refresh.sla_hours
    )

    total = 0
    on_time = 0
    measurable = False
    for term in parse(contract.formula).numerator:
        ingest = _ingest_column(con, term.table)
        if ingest is None:
            continue
        measurable = True
        rows = con.execute(
            f"SELECT count(*), count(*) FILTER (WHERE {ingest}::TIMESTAMP <= ?) "
            f"FROM {term.qualified} "
            f"WHERE {PERIOD_COLUMN[term.table]}::DATE BETWEEN ? AND ?",
            [deadline, start, end],
        ).fetchone()
        assert rows is not None
        total += rows[0]
        on_time += rows[1]

    if not measurable:
        # §22 gives `product_ops` no ingest column, and for a <=15-minute stream
        # that is the honest schema: the event time *is* the arrival time, so
        # there is no lag to measure and nothing can be "still landing".
        return VerificationCheck(
            name="completeness",
            passed=True,
            detail=(
                f"{contract.refresh.source} records arrival time as event time "
                f"(§22), so no ingest lag exists to measure"
            ),
            statistic=None,
        )

    if total == 0:
        return VerificationCheck(
            name="completeness",
            passed=False,
            detail=f"no records at all in {period} — nothing has landed",
            statistic=0.0,
        )

    share = on_time / total
    minimum = contract.data_quality.min_completeness
    return VerificationCheck(
        name="completeness",
        passed=share >= minimum,
        detail=(
            f"{share:.1%} of {total:,} records arrived inside the "
            f"{contract.refresh.sla_hours:g}h SLA after period close"
            + ("" if share >= minimum else f"; under the {minimum:.0%} minimum, rows are "
               "still landing and the number is not yet the number")
        ),
        statistic=round(share, 4),
    )


def _ingest_column(con: duckdb.DuckDBPyConnection, table: str) -> str | None:
    for candidate in ("_ingested_at", "_synced_at"):
        found = con.execute(
            "SELECT 1 FROM duckdb_columns() WHERE table_name = ? AND column_name = ?",
            [table, candidate],
        ).fetchall()
        if found:
            return candidate
    return None


# ── 3 · Definition drift ──────────────────────────────────────────────────────


def _definition_drift(
    con: duckdb.DuckDBPyConnection,
    contract: KPIContract,
    period: str,
    dimensions: dict[str, str],
    end: date,
) -> VerificationCheck:
    """*"A step that vanishes under a consistent definition is drift."*

    Only boundary periods are recomputed. Running this everywhere would be both
    wasteful and wrong: away from a boundary the adjacent epoch *is* the current
    one, so the recomputation is the same query and the check would silently
    pass on evidence it never gathered.
    """
    start, _ = period_bounds(con, contract, period)
    boundaries = {epoch.effective_from for epoch in contract.epochs}
    at_boundary = any(start <= boundary <= end for boundary in boundaries)

    if not at_boundary:
        return VerificationCheck(
            name="definition_drift",
            passed=True,
            detail=f"{period} does not straddle a definition epoch; nothing to recompute",
            statistic=None,
        )

    prior = previous_formula(contract, end)
    if prior is None:
        return VerificationCheck(
            name="definition_drift",
            passed=True,
            detail=f"{period} opens the first epoch; there is no earlier definition to test",
            statistic=None,
        )

    in_force = _movement(con, contract, period, dimensions).relative
    consistent = _consistent_movement(con, contract, period, dimensions, prior)
    survives = abs(consistent) >= contract.materiality.relative

    return VerificationCheck(
        name="definition_drift",
        passed=survives,
        detail=(
            f"boundary period recomputed under the previous epoch: {in_force:+.2%} becomes "
            f"{consistent:+.2%}"
            + (
                "; the step survives, so it is business, not drift"
                if survives
                else f", inside the {contract.materiality.relative:.0%} threshold — the "
                "movement is the definition changing, not the business"
            )
        ),
        statistic=round(consistent, 4),
    )


def _consistent_movement(
    con: duckdb.DuckDBPyConnection,
    contract: KPIContract,
    period: str,
    dimensions: dict[str, str],
    formula: str,
) -> float:
    series = _series(con, contract, period, dimensions, periods=2, formula=formula)
    if len(series) < 2 or not series[-2]:
        raise VerifyError(f"{contract.id} {period}: cannot recompute under {formula!r}")
    return (series[-1] - series[-2]) / series[-2]


# ── 4 · Artefacts ─────────────────────────────────────────────────────────────


def _artefact(
    con: duckdb.DuckDBPyConnection,
    contract: KPIContract,
    period: str,
    dimensions: dict[str, str],
    movement: _Movement,
    start: date,
    end: date,
) -> VerificationCheck:
    """*"One invoice **is** the movement."*

    Two ways that happens, both measured as a share of |Δ| against
    `max_single_record_share`:

    * **single-record dominance** — the largest individual record in the period,
      on either side of the formula. §25 D is a credit note worth 71% of Δ.
    * **period-boundary slippage** — records whose business date lands in this
      period but which were recorded in another, so the movement is a timing
      artefact of the close rather than a change in trade.
    """
    scale = abs(movement.delta)
    if scale == 0:
        return VerificationCheck(
            name="artefact",
            passed=True,
            detail="no movement to attribute to any record",
            statistic=0.0,
        )

    if not _is_additive(contract):
        # A median cannot be dominated by one record — that is what a median is
        # for. Dividing the largest ticket's duration by a movement measured in
        # the median's units is not a smaller version of the same question, it
        # is a different question with no meaning.
        return VerificationCheck(
            name="artefact",
            passed=True,
            detail=(
                f"{contract.id} aggregates by "
                f"{'/'.join(sorted(_aggregates(contract)))}, which no single record can "
                "dominate; single-record share is not defined for it"
            ),
            statistic=None,
        )

    largest, record = _largest_record(con, contract, dimensions, start, end)
    slipped = _slippage(con, contract, dimensions, start, end)
    threshold = contract.data_quality.max_single_record_share

    single_share = largest / scale
    slip_share = slipped / scale
    worst = max(single_share, slip_share)

    if single_share > threshold:
        detail = (
            f"one record ({record}) is {single_share:.0%} of the movement, over the "
            f"{threshold:.0%} single-record threshold — this is a batch, not a trend"
        )
    elif slip_share > threshold:
        detail = (
            f"{slip_share:.0%} of the movement is records booked across the period "
            f"boundary, over the {threshold:.0%} threshold — a timing artefact of the close"
        )
    else:
        detail = (
            f"largest single record is {single_share:.0%} of the movement, under the "
            f"{threshold:.0%} threshold; no refund batch, no period-boundary slippage"
        )

    return VerificationCheck(
        name="artefact", passed=worst <= threshold, detail=detail, statistic=round(worst, 4)
    )


def _aggregates(contract: KPIContract) -> set[str]:
    formula = parse(contract.formula)
    return {term.aggregate for term in (*formula.numerator, *formula.denominator)}


def _is_additive(contract: KPIContract) -> bool:
    return _aggregates(contract) <= {"SUM", "COUNT"}


def _largest_record(
    con: duckdb.DuckDBPyConnection,
    contract: KPIContract,
    dimensions: dict[str, str],
    start: date,
    end: date,
) -> tuple[float, str]:
    """The biggest single row contributing to the period, across every term."""
    best, name = 0.0, "none"
    for term in (*parse(contract.formula).numerator, *parse(contract.formula).denominator):
        joins, where, params = _scope(con, term.table, dimensions, start, end)
        row = con.execute(
            f"SELECT max(abs({term.expression})) FROM {term.qualified} AS {term.table}"
            f"{joins} WHERE {where}",
            params,
        ).fetchone()
        if row is not None and row[0] is not None and float(row[0]) > best:
            best, name = float(row[0]), term.table
    return best, name


def _slippage(
    con: duckdb.DuckDBPyConnection,
    contract: KPIContract,
    dimensions: dict[str, str],
    start: date,
    end: date,
) -> float:
    """Value whose business date is in this period but whose ingest landed in a
    different one — the close moved, the trade did not."""
    total = 0.0
    for term in parse(contract.formula).numerator:
        ingest = _ingest_column(con, term.table)
        if ingest is None:
            continue
        joins, where, params = _scope(con, term.table, dimensions, start, end)
        row = con.execute(
            f"SELECT coalesce(sum(abs({term.expression})), 0) "
            f"FROM {term.qualified} AS {term.table}{joins} "
            f"WHERE {where} AND ({term.table}.{ingest}::DATE < ? "
            f"OR {term.table}.{ingest}::DATE > ?)",
            [*params, start, end + timedelta(days=2)],
        ).fetchone()
        if row is not None and row[0] is not None:
            total += float(row[0])
    return total


def _scope(
    con: duckdb.DuckDBPyConnection,
    table: str,
    dimensions: dict[str, str],
    start: date,
    end: date,
) -> tuple[str, str, list[object]]:
    """The period-and-dimension predicate a term's own query would use."""
    joins = ""
    where = [f"{table}.{PERIOD_COLUMN[table]}::DATE BETWEEN ? AND ?"]
    params: list[object] = [start, end]

    for dimension, wanted in dimensions.items():
        found = con.execute(
            "SELECT 1 FROM duckdb_columns() WHERE table_name = ? AND column_name = ?",
            [table, dimension],
        ).fetchall()
        if found:
            where.append(f"{table}.{dimension} = ?")
        else:
            joins = " JOIN crm.account AS account USING (account_id)"
            where.append(f"account.{dimension} = ?")
        params.append(wanted)
    return joins, " AND ".join(where), params


# ── 5 · Materiality, and the sparse-history path ─────────────────────────────


def _history_is_sparse(contract: KPIContract, end: date) -> bool:
    """§15: `history < 2 x seasonal period` -> borrow a peer baseline and cap at
    Likely. §25 C is `p1_resolution_time`, which §22 gives eight months."""
    return (end - contract.history_start).days < 2 * contract.seasonal_period_days


def _materiality(
    con: duckdb.DuckDBPyConnection,
    contract: KPIContract,
    period: str,
    dimensions: dict[str, str],
) -> tuple[VerificationCheck, float | None, int | None]:
    series = _series(con, contract, period, dimensions, periods=HISTORY_PERIODS)
    m = contract.materiality
    verdict = assess(
        series,
        period=12,
        relative=m.relative,
        absolute=m.absolute,
        z_threshold=m.z_threshold,
        min_persistence=m.min_persistence,
    )
    return (
        VerificationCheck(
            name="materiality",
            passed=verdict.passed,
            detail=verdict.detail,
            statistic=round(verdict.robust_z, 3),
        ),
        verdict.robust_z,
        verdict.persistence,
    )


def _sparse_materiality(
    con: duckdb.DuckDBPyConnection,
    contract: KPIContract,
    period: str,
    dimensions: dict[str, str],
    movement: _Movement,
) -> tuple[VerificationCheck, float | None, int | None]:
    """§23's sparse rule: `y_hat = y_{t-1} (1 + median_peers dy_p / y_p)`.

    There is no seasonal baseline to fit, so there is no robust z either, and
    reporting one anyway would be the single most misleading number this module
    could produce. The result carries `baseline: borrowed` and a Likely ceiling
    instead — §9's ceilings *"only ever lower"*.
    """
    expected = _peer_expectation(con, contract, period, dimensions, movement)
    m = contract.materiality

    if expected is None:
        return (
            VerificationCheck(
                name="materiality",
                passed=False,
                detail=(
                    "history is shorter than two seasonal cycles and no peer segment has "
                    "one either — there is no baseline to judge this against"
                ),
                statistic=None,
            ),
            None,
            None,
        )

    surprise = (movement.latest - expected) / expected if expected else 0.0
    passed = abs(surprise) >= m.relative and abs(movement.delta) >= m.absolute

    return (
        VerificationCheck(
            name="materiality",
            passed=passed,
            detail=(
                f"sparse history: baseline borrowed from peers, expected {expected:,.2f} "
                f"against {movement.latest:,.2f} ({surprise:+.2%}). Confidence is capped "
                "at Likely regardless of what the tests find"
            ),
            statistic=round(surprise, 4),
        ),
        None,
        None,
    )


def _peer_expectation(
    con: duckdb.DuckDBPyConnection,
    contract: KPIContract,
    period: str,
    dimensions: dict[str, str],
    movement: _Movement,
) -> float | None:
    """`y_{t-1}` moved by the median relative move across peer slices.

    Peers are the other values of the dimension being sliced on — the other
    regions when the case is regional. With no dimension there are no peers, and
    the honest answer is None rather than the KPI's own trend, which is the very
    thing that does not exist yet.
    """
    if len(dimensions) != 1:
        return None
    (dimension, own), = dimensions.items()

    rows = con.execute(
        f"SELECT DISTINCT {dimension} FROM crm.account WHERE {dimension} IS NOT NULL"
    ).fetchall()
    peers = sorted(str(r[0]) for r in rows if str(r[0]) != own)

    moves: list[float] = []
    for peer in peers:
        series = _series(con, contract, period, {dimension: peer}, periods=2)
        if len(series) == 2 and series[-2]:
            moves.append((series[-1] - series[-2]) / series[-2])

    if not moves:
        return None
    return movement.previous * (1 + statistics.median(moves))
