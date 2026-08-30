"""Stage 5 · Challenge — §15 S5, the four tests.

*"Trying to prove it's wrong. A cause that cannot be falsified was never
tested — it was just believed."*

Four tests, each already built and unit-tested against hand-computed values
in `stats/` (ladder 1.1/1.2). This module is the caller: it pulls the raw
series each test needs straight from the warehouse and the contract, never
from anything the generator alone knows — a test that read the answer would
not be testing anything.

* **Timing** — τ_effect − τ_cause. τ_cause is a PELT change-point for a
  continuous series (tickets) or the earliest matching record for a discrete
  one (a price change, a competitor's news item, an incident); no detection
  needed for a discrete date, it *is* the event. τ_effect, per footprint
  account, is that account's own renewal outcome inside the window. Passes
  at `0 ≤ Δτ ≤ max_lag_days`; a negative lag means the effect happened before
  the cause, which is not a lag, it's a refutation.
* **Locality** — Jaccard between the driver's own footprint (every account
  its mechanism plausibly touched, deliberately computed *wider* than the
  KPI's own footprint — a driver that hits 41 accounts and a movement that
  touched 2 is exactly what this test exists to catch) and the movement's
  footprint. `J > 0.5` passes, `J < 0.2` refutes (§15).
* **Dose** — Spearman rank correlation between each footprint account's
  exposure intensity and its own contribution to the movement, only where a
  driver's evidence carries a natural per-account gradient (today: the
  ticket-spike ratio). `stats/correlation.py`'s own `n ≥ 5` rule is what
  makes Dose `inconclusive` at two accounts — nothing here special-cases it.
* **Control** — DiD and placebo rank, treated (footprint accounts) against
  matched peers (same region and segment, excluding the footprint itself).
  Computed **once per case, not once per hypothesis** — it asks whether the
  movement is real against a comparable baseline, which is a property of the
  effect, not of any one candidate cause. §15's formula and every worked
  example describe it exactly this way, with no per-hypothesis treated/
  control construction; the only field the sealed answer sheet records for
  why a decoy was eliminated is `locality` or `locality_and_timing`, never
  `control` — see `docs/DECISIONS.md` for the reasoning kept there.

A hypothesis with no `probe_sql` (§24's `seasonality`) is skipped, same as
4a and 4c: there is nothing here to run either. `unmodelled` is skipped for
the same reason — it names no registry driver.

Every result becomes an `EvidenceItem` (`method="stat_test"`, or `"did"` for
Control) in the ledger, the same discipline as 4a/4c: an inconclusive test
is `uncheckable`, findable, never silently absent.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

import duckdb

from casefile.engine.evidence import SPIKE_RATIO
from casefile.metric import calendar_months, value
from casefile.models import (
    ContributionTree,
    Driver,
    EvidenceItem,
    Footprint,
    Hypothesis,
    KPIContract,
    Source,
    TestMatrix,
    TestResult,
)
from casefile.stats.changepoint import onset
from casefile.stats.correlation import spearman
from casefile.stats.did import MIN_CONTROLS, placebo_rank
from casefile.stats.overlap import jaccard

ROOT = Path(__file__).resolve().parents[3]

#: §15's Locality bands.
LOCALITY_PASS = 0.5
LOCALITY_REFUTE = 0.2
#: Timing is a clean date-arithmetic finding, not a continuous statistic —
#: a flat strength, the same way 4a scores several of its own SQL facts.
TIMING_STRENGTH = 0.7


class ChallengeError(ValueError):
    pass


@dataclass(frozen=True)
class _Finding:
    """A `TestResult` plus the two figures only this module needs to turn it
    into an `EvidenceItem`: `coverage` (how much of the footprint the test
    could actually examine — always known, not just when inconclusive) and
    `strength` (the item's own 0..1 evidentiary weight, distinct from
    `TestResult.statistic`, which stays in the test's native units)."""

    result: TestResult
    coverage: float
    strength: float


def challenge(
    contract: KPIContract,
    hypotheses: list[Hypothesis],
    tree: ContributionTree,
    con: duckdb.DuckDBPyConnection,
    as_of: datetime | None = None,
) -> tuple[dict[str, TestMatrix], list[EvidenceItem]]:
    """Runs all four tests for every hypothesis with a probe, in hypothesis
    order. Returns `Case.tests`'s own shape plus every `EvidenceItem` minted
    along the way, for the caller to add to the ledger."""
    as_of = as_of or _default_as_of(con)
    footprint = tree.footprint
    control = _control(con, contract, tree)

    matrices: dict[str, TestMatrix] = {}
    items: list[EvidenceItem] = []
    for hypothesis in hypotheses:
        driver = _driver(contract, hypothesis.driver_id)
        if driver is None or driver.probe_sql is None:
            continue

        findings = {
            "timing": _timing(con, driver, footprint),
            "locality": _locality(con, driver, footprint),
            "dose": _dose(con, driver, footprint, tree),
            "control": control,
        }
        fields: dict[str, TestResult] = {}
        for name, finding in findings.items():
            item = _evidence(driver, name, finding, as_of, footprint)
            items.append(item)
            fields[name] = finding.result.model_copy(update={"evidence_ids": [item.id]})
        matrices[driver.id] = TestMatrix(**fields)

    return matrices, items


def _driver(contract: KPIContract, driver_id: str) -> Driver | None:
    return next((d for d in contract.drivers if d.id == driver_id), None)


def _default_as_of(con: duckdb.DuckDBPyConnection) -> datetime:
    row = con.execute("SELECT max(as_of) FROM meta.watermark").fetchone()
    if row is None or row[0] is None:
        raise ChallengeError("meta.watermark has no as_of; the warehouse was not built")
    return row[0]


def _ts(value: date | datetime) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.combine(value, datetime.min.time())


def _freshness_hours(as_of: datetime, footprint: Footprint) -> float:
    return (as_of - _ts(footprint.window_end)).total_seconds() / 3600.0


def _evidence(
    driver: Driver, test_name: str, finding: _Finding, as_of: datetime, footprint: Footprint
) -> EvidenceItem:
    result = finding.result
    if result.outcome == "pass":
        supports, contradicts = [driver.id], []
    elif result.outcome == "refute":
        supports, contradicts = [], [driver.id]
    else:
        supports, contradicts = [driver.id], []  # uncheckable: findable, not endorsed
    evidence_outcome = "uncheckable" if result.outcome == "inconclusive" else "found"
    return EvidenceItem(
        id=f"ev-{driver.id}-{test_name}-001",
        claim=result.detail,
        kind="statistic",
        outcome=evidence_outcome,
        source=Source(
            system="stats", record_id=f"{test_name}:{driver.id}",
            timestamp=_ts(footprint.window_end),
        ),
        method="did" if test_name == "control" else "stat_test",
        supports=supports, contradicts=contradicts,
        strength=finding.strength, freshness_hours=_freshness_hours(as_of, footprint),
        coverage=finding.coverage if evidence_outcome == "uncheckable" else None,
    )


def _region_peers(con: duckdb.DuckDBPyConnection, accounts: list[str]) -> list[str]:
    """Every account sharing a region with `accounts` — Locality's candidate
    pool for a driver's own footprint. Deliberately wider than the KPI's own
    footprint: that width is what lets a broadly-acting decoy's low overlap
    actually show up rather than being invisible by construction."""
    if not accounts:
        return []
    regions = [
        r[0]
        for r in con.execute(
            "SELECT DISTINCT region FROM crm.account WHERE account_id IN (SELECT UNNEST($ids))",
            {"ids": accounts},
        ).fetchall()
    ]
    if not regions:
        return []
    rows = con.execute(
        "SELECT account_id FROM crm.account WHERE region IN (SELECT UNNEST($regions))",
        {"regions": regions},
    ).fetchall()
    return [r[0] for r in rows]


def _segments_of(con: duckdb.DuckDBPyConnection, accounts: list[str]) -> list[str]:
    if not accounts:
        return []
    return [
        r[0]
        for r in con.execute(
            "SELECT DISTINCT segment FROM crm.account WHERE account_id IN (SELECT UNNEST($ids))",
            {"ids": accounts},
        ).fetchall()
    ]


# ── Timing ───────────────────────────────────────────────────────────────────

OnsetDetector = Callable[[duckdb.DuckDBPyConnection, Driver, Footprint], "date | None"]


def _ticket_spike_onset(
    con: duckdb.DuckDBPyConnection, driver: Driver, footprint: Footprint
) -> date | None:
    accounts = footprint.entities.get("account_id", [])
    if not accounts:
        return None
    length = footprint.window_end - footprint.window_start
    start = footprint.window_start - length
    rows = con.execute(
        "SELECT created_at::DATE, count(*) FROM product_ops.ticket "
        "WHERE account_id IN (SELECT UNNEST($ids)) AND created_at::DATE BETWEEN $start AND $end "
        "GROUP BY 1",
        {"ids": accounts, "start": start, "end": footprint.window_end},
    ).fetchall()
    by_day = dict(rows)
    days: list[date] = []
    day = start
    while day <= footprint.window_end:
        days.append(day)
        day += timedelta(days=1)
    series = [by_day.get(d, 0) for d in days]
    idx = onset(series)
    return days[idx] if idx is not None else None


def _price_delta_onset(
    con: duckdb.DuckDBPyConnection, driver: Driver, footprint: Footprint
) -> date | None:
    segments = _segments_of(con, footprint.entities.get("account_id", []))
    if not segments:
        return None
    start = footprint.window_start - timedelta(days=driver.max_lag_days)
    row = con.execute(
        "SELECT min(effective_from) FROM billing.price_book "
        "WHERE segment IN (SELECT UNNEST($segments)) AND effective_from BETWEEN $start AND $end",
        {"segments": segments, "start": start, "end": footprint.window_end},
    ).fetchone()
    return row[0] if row and row[0] is not None else None


def _lost_reason_onset(
    con: duckdb.DuckDBPyConnection, driver: Driver, footprint: Footprint
) -> date | None:
    start = footprint.window_start - timedelta(days=driver.max_lag_days)
    row = con.execute(
        "SELECT min(published_at::DATE) FROM product_ops.news_item "
        "WHERE competitor IS NOT NULL AND published_at::DATE BETWEEN $start AND $end",
        {"start": start, "end": footprint.window_end},
    ).fetchone()
    return row[0] if row and row[0] is not None else None


def _incident_onset(
    con: duckdb.DuckDBPyConnection, driver: Driver, footprint: Footprint
) -> date | None:
    start = footprint.window_start - timedelta(days=driver.max_lag_days)
    row = con.execute(
        "SELECT min(started_at::DATE) FROM product_ops.incident "
        "WHERE started_at::DATE BETWEEN $start AND $end",
        {"start": start, "end": footprint.window_end},
    ).fetchone()
    return row[0] if row and row[0] is not None else None


_ONSET: dict[str, OnsetDetector] = {
    "ticket_spike": _ticket_spike_onset,
    "price_delta": _price_delta_onset,
    "lost_reason_scan": _lost_reason_onset,
    "incident_scan": _incident_onset,
}


def _effect_dates(
    con: duckdb.DuckDBPyConnection, accounts: list[str], footprint: Footprint
) -> dict[str, date]:
    """Each footprint account's own realised outcome inside the window — a
    renewal's decision date, the one discrete event a revenue movement in
    this project is ever traced back to. An account with no renewal in the
    window contributes no pair; it is not evidence either way."""
    if not accounts:
        return {}
    rows = con.execute(
        "SELECT account_id, max(closed_date) FROM crm.renewal "
        "WHERE account_id IN (SELECT UNNEST($ids)) AND closed_date BETWEEN $start AND $end "
        "GROUP BY 1",
        {"ids": accounts, "start": footprint.window_start, "end": footprint.window_end},
    ).fetchall()
    return {account_id: closed for account_id, closed in rows if closed is not None}


def _worst_lag(lags: dict[str, int], max_lag_days: int) -> int:
    def badness(lag: int) -> int:
        return -lag if lag < 0 else max(0, lag - max_lag_days)

    return max(lags.values(), key=badness)


def _timing(con: duckdb.DuckDBPyConnection, driver: Driver, footprint: Footprint) -> _Finding:
    assert driver.probe_sql is not None
    detector = _ONSET.get(Path(driver.probe_sql).stem)
    cause = detector(con, driver, footprint) if detector else None
    if cause is None:
        result = TestResult(outcome="inconclusive", detail=f"no determinable onset for {driver.id}")
        return _Finding(result, coverage=0.0, strength=0.0)

    accounts = footprint.entities.get("account_id", [])
    effects = _effect_dates(con, accounts, footprint)
    coverage = len(effects) / len(accounts) if accounts else 0.0
    if not effects:
        result = TestResult(
            outcome="inconclusive",
            detail="no footprint account has a discrete effect event inside the window",
            statistic=None,
        )
        return _Finding(result, coverage=0.0, strength=0.0)

    lags = {account: (closed - cause).days for account, closed in effects.items()}
    worst = _worst_lag(lags, driver.max_lag_days)
    if any(lag < 0 or lag > driver.max_lag_days for lag in lags.values()):
        detail = (
            f"onset {cause}; lag(s) {sorted(lags.values())} days against a "
            f"{driver.max_lag_days}-day window — at least one effect falls outside it"
        )
        result = TestResult(outcome="refute", detail=detail, statistic=float(worst))
    else:
        detail = f"onset {cause}; lag(s) {sorted(lags.values())} days, within {driver.max_lag_days}"
        result = TestResult(outcome="pass", detail=detail, statistic=float(worst))
    return _Finding(result, coverage=coverage, strength=TIMING_STRENGTH)


# ── Locality ─────────────────────────────────────────────────────────────────

FootprintDetector = Callable[[duckdb.DuckDBPyConnection, Driver, Footprint], "set[str] | None"]


def _ticket_spike_footprint(
    con: duckdb.DuckDBPyConnection, driver: Driver, footprint: Footprint
) -> set[str] | None:
    accounts = footprint.entities.get("account_id", [])
    peers = _region_peers(con, accounts)
    if not peers:
        return None
    length = footprint.window_end - footprint.window_start
    baseline_start, baseline_end = footprint.window_start - length, footprint.window_start
    sql = (ROOT / "probes/ticket_spike.sql").read_text(encoding="utf-8")
    rows = con.execute(
        sql,
        {
            "account_ids": peers,
            "window_start": footprint.window_start, "window_end": footprint.window_end,
            "baseline_start": baseline_start, "baseline_end": baseline_end,
        },
    ).fetchall()
    return {
        account_id for account_id, _w, _b, ratio in rows
        if ratio is not None and ratio >= SPIKE_RATIO
    }


def _price_delta_footprint(
    con: duckdb.DuckDBPyConnection, driver: Driver, footprint: Footprint
) -> set[str] | None:
    accounts = footprint.entities.get("account_id", [])
    segments = _segments_of(con, accounts)
    if not segments:
        return None
    start = footprint.window_start - timedelta(days=driver.max_lag_days)
    changed = [
        r[0]
        for r in con.execute(
            "SELECT DISTINCT segment FROM billing.price_book "
            "WHERE segment IN (SELECT UNNEST($segments)) "
            "AND effective_from BETWEEN $start AND $end",
            {"segments": segments, "start": start, "end": footprint.window_end},
        ).fetchall()
    ]
    if not changed:
        return set()
    rows = con.execute(
        "SELECT account_id FROM crm.account WHERE segment IN (SELECT UNNEST($segments))",
        {"segments": changed},
    ).fetchall()
    return {r[0] for r in rows}


def _lost_reason_footprint(
    con: duckdb.DuckDBPyConnection, driver: Driver, footprint: Footprint
) -> set[str] | None:
    start = footprint.window_start - timedelta(days=driver.max_lag_days)
    regions = [
        r[0]
        for r in con.execute(
            "SELECT DISTINCT region FROM product_ops.news_item "
            "WHERE competitor IS NOT NULL AND published_at::DATE BETWEEN $start AND $end "
            "AND region IS NOT NULL",
            {"start": start, "end": footprint.window_end},
        ).fetchall()
    ]
    if not regions:
        return set()
    rows = con.execute(
        "SELECT account_id FROM crm.account WHERE region IN (SELECT UNNEST($regions))",
        {"regions": regions},
    ).fetchall()
    return {r[0] for r in rows}


_LOCALITY: dict[str, FootprintDetector] = {
    "ticket_spike": _ticket_spike_footprint,
    "price_delta": _price_delta_footprint,
    "lost_reason_scan": _lost_reason_footprint,
}


def _locality(con: duckdb.DuckDBPyConnection, driver: Driver, footprint: Footprint) -> _Finding:
    assert driver.probe_sql is not None
    detector = _LOCALITY.get(Path(driver.probe_sql).stem)
    cause = detector(con, driver, footprint) if detector else None
    if cause is None:
        detail = f"no determinable footprint for {driver.id}"
        result = TestResult(outcome="inconclusive", detail=detail)
        return _Finding(result, coverage=0.0, strength=0.0)

    effect = set(footprint.entities.get("account_id", []))
    try:
        j = jaccard(cause, effect)
    except ValueError:
        result = TestResult(
            outcome="inconclusive",
            detail="cause and effect footprints are both empty",
            statistic=0.0,
        )
        return _Finding(result, coverage=1.0, strength=0.0)

    if j > LOCALITY_PASS:
        outcome = "pass"
    elif j < LOCALITY_REFUTE:
        outcome = "refute"
    else:
        outcome = "inconclusive"
    detail = f"J={j:.3f} over {len(cause)} cause and {len(effect)} effect account(s)"
    result = TestResult(outcome=outcome, detail=detail, statistic=j)
    return _Finding(result, coverage=1.0, strength=j)


# ── Dose ─────────────────────────────────────────────────────────────────────

IntensityDetector = Callable[[duckdb.DuckDBPyConnection, Footprint], "dict[str, float]"]


def _ticket_spike_intensity(
    con: duckdb.DuckDBPyConnection, footprint: Footprint
) -> dict[str, float]:
    accounts = footprint.entities.get("account_id", [])
    if not accounts:
        return {}
    length = footprint.window_end - footprint.window_start
    baseline_start, baseline_end = footprint.window_start - length, footprint.window_start
    sql = (ROOT / "probes/ticket_spike.sql").read_text(encoding="utf-8")
    rows = con.execute(
        sql,
        {
            "account_ids": accounts,
            "window_start": footprint.window_start, "window_end": footprint.window_end,
            "baseline_start": baseline_start, "baseline_end": baseline_end,
        },
    ).fetchall()
    return {account_id: ratio for account_id, _w, _b, ratio in rows if ratio is not None}


_DOSE: dict[str, IntensityDetector] = {
    "ticket_spike": _ticket_spike_intensity,
}


def _dose(
    con: duckdb.DuckDBPyConnection, driver: Driver, footprint: Footprint, tree: ContributionTree
) -> _Finding:
    assert driver.probe_sql is not None
    detector = _DOSE.get(Path(driver.probe_sql).stem)
    accounts = footprint.entities.get("account_id", [])
    if detector is None:
        detail = f"{driver.id} has no per-account intensity signal — dose does not apply"
        result = TestResult(outcome="inconclusive", detail=detail)
        return _Finding(result, coverage=0.0, strength=0.0)

    intensity = detector(con, footprint)
    magnitude = {n.key: n.delta for n in tree.by_dimension.get("account", [])}
    paired = sorted(set(intensity) & set(magnitude))
    coverage = len(paired) / len(accounts) if accounts else 0.0
    if not paired:
        detail = "no account carries both a dose and an effect figure"
        result = TestResult(outcome="inconclusive", detail=detail)
        return _Finding(result, coverage=0.0, strength=0.0)

    corr = spearman([intensity[a] for a in paired], [magnitude[a] for a in paired])
    result = TestResult(outcome=corr.outcome, detail=corr.detail, statistic=corr.rho)
    strength = abs(corr.rho) if corr.rho is not None else 0.0
    return _Finding(result, coverage=coverage, strength=strength)


# ── Control ──────────────────────────────────────────────────────────────────


def _peer_accounts(con: duckdb.DuckDBPyConnection, accounts: list[str]) -> list[str]:
    """Every account matching a footprint account's own region and segment,
    excluding the footprint itself — Control's matched-peer pool."""
    if not accounts:
        return []
    pairs = con.execute(
        "SELECT DISTINCT region, segment FROM crm.account "
        "WHERE account_id IN (SELECT UNNEST($ids))",
        {"ids": accounts},
    ).fetchall()
    peers: set[str] = set()
    for region, segment in pairs:
        rows = con.execute(
            "SELECT account_id FROM crm.account WHERE region = $region AND segment = $segment "
            "AND account_id NOT IN (SELECT UNNEST($excl))",
            {"region": region, "segment": segment, "excl": accounts},
        ).fetchall()
        peers.update(r[0] for r in rows)
    return sorted(peers)


def _panel(
    con: duckdb.DuckDBPyConnection, contract: KPIContract, accounts: list[str],
    previous: str, current: str,
) -> dict[str, tuple[float, float]]:
    panel: dict[str, tuple[float, float]] = {}
    for account in accounts:
        pre = value(con, contract, previous, {"account_id": account})
        post = value(con, contract, current, {"account_id": account})
        if pre is not None and post is not None:
            panel[account] = (pre, post)
    return panel


def _control(
    con: duckdb.DuckDBPyConnection, contract: KPIContract, tree: ContributionTree
) -> _Finding:
    footprint = tree.footprint
    accounts = footprint.entities.get("account_id", [])
    if not accounts:
        result = TestResult(outcome="inconclusive", detail="no footprint accounts to test")
        return _Finding(result, coverage=0.0, strength=0.0)

    periods = calendar_months(footprint.window_start, footprint.window_end)[-2:]
    if len(periods) < 2:
        detail = "fewer than two periods span the footprint window"
        result = TestResult(outcome="inconclusive", detail=detail)
        return _Finding(result, coverage=0.0, strength=0.0)
    previous, current = periods

    peers = _peer_accounts(con, accounts)
    treated = _panel(con, contract, accounts, previous, current)
    controls = _panel(con, contract, peers, previous, current)
    coverage = min(1.0, len(controls) / MIN_CONTROLS)

    if not treated:
        detail = "no footprint account has both periods' figures"
        result = TestResult(outcome="inconclusive", detail=detail)
        return _Finding(result, coverage=0.0, strength=0.0)

    placebo = placebo_rank(treated, controls)
    result = TestResult(outcome=placebo.outcome, detail=placebo.detail, statistic=placebo.effect)
    return _Finding(result, coverage=coverage, strength=1.0 - placebo.pseudo_p)
