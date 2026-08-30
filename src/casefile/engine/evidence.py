"""Stage 4a · Gather evidence — probes, counted absence — §15 S4a.

*"Going door to door. Run the precise numbers... And write down what you
didn't find: 'we checked 12 lost-reason fields, none mention a competitor'
is a real finding."*

One probe per driver, from `contract.drivers[i].probe_sql` — a SQL template
under `probes/`. Each probe lands as exactly one of three outcomes, and which
one is a property of what the data actually holds, never of the driver's
narrative role:

* **found** — the probe turned up something.
* **checked_absent** — a populated, countable field was checked and did not
  match; the count is the `denominator`. §25's "0 of 12 populated lost-reason
  fields name a competitor" is this outcome.
* **uncheckable** — the source has no coverage of this footprint in this
  window: nothing was there to check, as opposed to checked and empty.

A driver with no `probe_sql` (§24's `seasonality`) is skipped here — its
evidence is the materiality figures Stage 1 already computed, not a fresh
probe. `hypothesise.py`'s `unmodelled` flag is skipped too: it names no
registry driver, so there is no probe to run.

**Every item, uncheckable ones included, carries its driver in `supports`.**
`models.py` gives evidence exactly two linkage fields — `supports` and
`contradicts` — and an uncheckable finding argues for neither direction. It
still has to be findable by `Ledger.for_driver`, or Stage 6 could never tell
"this driver's sources have no coverage of this footprint" from "no probe
ever ran" — which is the difference between Undetermined and a driver that
was silently never tested. `outcome` carries the epistemic weight; `supports`
here means only "this item is about this driver."
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import date, datetime
from pathlib import Path

import duckdb

from casefile.models import Driver, EvidenceItem, Footprint, Hypothesis, KPIContract, Source

ROOT = Path(__file__).resolve().parents[3]

#: Ticket volume at or above this multiple of its own prior-period baseline
#: counts as a spike — comfortably below §24's injected 4.2x, comfortably
#: above the noise a quiet account's week-to-week count carries on its own.
SPIKE_RATIO = 1.5
COMPETITOR_CODES = ("competitor_price", "competitor_features")


class EvidenceError(ValueError):
    pass


def gather_probes(
    contract: KPIContract,
    hypotheses: list[Hypothesis],
    footprint: Footprint,
    con: duckdb.DuckDBPyConnection,
    as_of: datetime | None = None,
) -> list[EvidenceItem]:
    """Runs every enumerated hypothesis's probe, in hypothesis order."""
    as_of = as_of or _default_as_of(con)
    account_ids = footprint.entities.get("account_id", [])

    items: list[EvidenceItem] = []
    for hypothesis in hypotheses:
        driver = _driver(contract, hypothesis.driver_id)
        if driver is None or driver.probe_sql is None:
            continue
        interpreter = _INTERPRETERS.get(Path(driver.probe_sql).stem)
        if interpreter is None:
            raise EvidenceError(
                f"driver {driver.id!r} names probe {driver.probe_sql!r}, which has no "
                "registered interpreter — add one to evidence.py's _INTERPRETERS"
            )
        items.extend(interpreter(con, driver, account_ids, footprint, as_of))
    return items


def _driver(contract: KPIContract, driver_id: str) -> Driver | None:
    return next((d for d in contract.drivers if d.id == driver_id), None)


def _default_as_of(con: duckdb.DuckDBPyConnection) -> datetime:
    row = con.execute("SELECT max(as_of) FROM meta.watermark").fetchone()
    if row is None or row[0] is None:
        raise EvidenceError("meta.watermark has no as_of; the warehouse was not built")
    return row[0]


def _ts(value: date | datetime) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.combine(value, datetime.min.time())


def _freshness_hours(as_of: datetime, footprint: Footprint) -> float:
    return (as_of - _ts(footprint.window_end)).total_seconds() / 3600.0


def _sql(driver: Driver) -> str:
    assert driver.probe_sql is not None
    return (ROOT / driver.probe_sql).read_text(encoding="utf-8")


Interpreter = Callable[
    [duckdb.DuckDBPyConnection, Driver, Sequence[str], Footprint, datetime], list[EvidenceItem]
]


# ── integration_delay · tickets ────────────────────────────────────────────────


def _ticket_spike(
    con: duckdb.DuckDBPyConnection,
    driver: Driver,
    account_ids: Sequence[str],
    footprint: Footprint,
    as_of: datetime,
) -> list[EvidenceItem]:
    window_start, window_end = footprint.window_start, footprint.window_end
    length = window_end - window_start
    baseline_start, baseline_end = window_start - length, window_start
    rows = con.execute(
        _sql(driver),
        {
            "account_ids": list(account_ids),
            "window_start": window_start,
            "window_end": window_end,
            "baseline_start": baseline_start,
            "baseline_end": baseline_end,
        },
    ).fetchall()

    freshness = _freshness_hours(as_of, footprint)
    items: list[EvidenceItem] = []
    for i, (account_id, _window_count, _baseline_count, ratio) in enumerate(rows, start=1):
        source = Source(
            system="product_ops",
            record_id=f"tickets:{account_id}:{window_start}:{window_end}",
            timestamp=_ts(window_end),
        )
        if ratio is None:
            items.append(
                EvidenceItem(
                    id=f"ev-{driver.id}-{i:03d}",
                    claim=(
                        f"{account_id} has no ticket history in the prior period to "
                        "compare against"
                    ),
                    kind="statistic", outcome="uncheckable", source=source, method="sql",
                    supports=[driver.id], strength=0.0, freshness_hours=freshness,
                    coverage=0.0,
                )
            )
        elif ratio >= SPIKE_RATIO:
            items.append(
                EvidenceItem(
                    id=f"ev-{driver.id}-{i:03d}",
                    claim=(
                        f"{account_id}'s ticket volume rose {ratio:.1f}x against its "
                        "prior-period baseline"
                    ),
                    kind="statistic", outcome="found", source=source, method="sql",
                    supports=[driver.id], strength=min(1.0, (ratio - 1.0) / 3.0),
                    freshness_hours=freshness,
                )
            )
        else:
            items.append(
                EvidenceItem(
                    id=f"ev-{driver.id}-{i:03d}",
                    claim=(
                        f"{account_id}'s ticket volume held at {ratio:.1f}x its "
                        "prior-period baseline"
                    ),
                    kind="statistic", outcome="found", source=source, method="sql",
                    contradicts=[driver.id], strength=min(1.0, max(0.0, 1.0 - ratio)),
                    freshness_hours=freshness,
                )
            )
    return items


# ── pricing_change · price_book ────────────────────────────────────────────────


def _price_delta(
    con: duckdb.DuckDBPyConnection,
    driver: Driver,
    account_ids: Sequence[str],
    footprint: Footprint,
    as_of: datetime,
) -> list[EvidenceItem]:
    segments = [
        row[0]
        for row in con.execute(
            "SELECT DISTINCT segment FROM crm.account WHERE account_id IN (SELECT UNNEST($ids))",
            {"ids": list(account_ids)},
        ).fetchall()
    ]
    freshness = _freshness_hours(as_of, footprint)
    sql = _sql(driver)
    items: list[EvidenceItem] = []
    counter = 0

    for segment in segments:
        rows = con.execute(
            sql,
            {
                "segment": segment,
                "window_start": footprint.window_start,
                "window_end": footprint.window_end,
            },
        ).fetchall()
        if rows:
            for product_id, _segment, effective_from, list_price in rows:
                counter += 1
                items.append(
                    EvidenceItem(
                        id=f"ev-{driver.id}-{counter:03d}",
                        claim=(
                            f"{product_id}'s list price for {segment} changed to "
                            f"{list_price:g} on {effective_from}"
                        ),
                        kind="fact", outcome="found",
                        source=Source(
                            system="billing",
                            record_id=f"price_book:{product_id}:{effective_from}",
                            timestamp=_ts(effective_from),
                        ),
                        method="sql", supports=[driver.id], strength=0.8,
                        freshness_hours=freshness,
                    )
                )
        else:
            # price_book has full history for every segment, always — a
            # window with nothing in it is a real, countable absence, not a
            # coverage gap.
            total_row = con.execute(
                "SELECT count(*) FROM billing.price_book WHERE segment = $segment",
                {"segment": segment},
            ).fetchone()
            assert total_row is not None  # count(*) always returns exactly one row
            total = total_row[0]
            counter += 1
            items.append(
                EvidenceItem(
                    id=f"ev-{driver.id}-{counter:03d}",
                    claim=(
                        f"none of {total} recorded price changes for {segment} fall "
                        "inside this window"
                    ),
                    kind="absence", outcome="checked_absent",
                    source=Source(
                        system="billing", record_id=f"price_book:{segment}",
                        timestamp=_ts(footprint.window_end),
                    ),
                    method="sql", contradicts=[driver.id], strength=0.6,
                    freshness_hours=freshness, denominator=total,
                )
            )
    return items


# ── competitor_offer · crm.opportunity.lost_reason_code ────────────────────────


def _lost_reason_scan(
    con: duckdb.DuckDBPyConnection,
    driver: Driver,
    account_ids: Sequence[str],
    footprint: Footprint,
    as_of: datetime,
) -> list[EvidenceItem]:
    row = con.execute(
        _sql(driver),
        {
            "account_ids": list(account_ids),
            "window_start": footprint.window_start,
            "window_end": footprint.window_end,
        },
    ).fetchone()
    assert row is not None  # the probe's three count(*) FILTERs always return one row
    closed_lost, populated, names_competitor = row

    freshness = _freshness_hours(as_of, footprint)
    source = Source(
        system="crm", record_id="opportunity:lost_reason_code",
        timestamp=_ts(footprint.window_end),
    )

    if closed_lost == 0:
        return [
            EvidenceItem(
                id=f"ev-{driver.id}-001",
                claim="no closed-lost opportunities exist on this footprint in this window",
                kind="absence", outcome="uncheckable", source=source, method="sql",
                supports=[driver.id], strength=0.0, freshness_hours=freshness, coverage=0.0,
            )
        ]
    if populated == 0:
        return [
            EvidenceItem(
                id=f"ev-{driver.id}-001",
                claim=(
                    f"{closed_lost} closed-lost opportunities on this footprint carry "
                    "no lost-reason code"
                ),
                kind="absence", outcome="uncheckable", source=source, method="sql",
                supports=[driver.id], strength=0.0, freshness_hours=freshness, coverage=0.0,
            )
        ]
    if names_competitor > 0:
        return [
            EvidenceItem(
                id=f"ev-{driver.id}-001",
                claim=(
                    f"{names_competitor} of {populated} populated lost-reason fields "
                    "name a competitor"
                ),
                kind="fact", outcome="found", source=source, method="sql",
                supports=[driver.id], strength=min(1.0, names_competitor / populated),
                freshness_hours=freshness,
            )
        ]
    return [
        EvidenceItem(
            id=f"ev-{driver.id}-001",
            claim=f"0 of {populated} populated lost-reason fields name a competitor",
            kind="absence", outcome="checked_absent", source=source, method="sql",
            contradicts=[driver.id], strength=0.8, freshness_hours=freshness,
            denominator=populated,
        )
    ]


# ── supply_delay · incident ─────────────────────────────────────────────────────


def _incident_scan(
    con: duckdb.DuckDBPyConnection,
    driver: Driver,
    account_ids: Sequence[str],
    footprint: Footprint,
    as_of: datetime,
) -> list[EvidenceItem]:
    rows = con.execute(
        _sql(driver),
        {
            "account_ids": list(account_ids),
            "window_start": footprint.window_start,
            "window_end": footprint.window_end,
        },
    ).fetchall()

    freshness = _freshness_hours(as_of, footprint)
    if not rows:
        return [
            EvidenceItem(
                id=f"ev-{driver.id}-001",
                claim="no incident on record overlaps this footprint's accounts and window",
                kind="absence", outcome="uncheckable",
                source=Source(
                    system="product_ops", record_id="incident:none",
                    timestamp=_ts(footprint.window_end),
                ),
                method="sql", supports=[driver.id], strength=0.0, freshness_hours=freshness,
                coverage=0.0,
            )
        ]

    items: list[EvidenceItem] = []
    for i, (incident_id, service, started_at, resolved_at, severity) in enumerate(rows, start=1):
        items.append(
            EvidenceItem(
                id=f"ev-{driver.id}-{i:03d}",
                claim=(
                    f"incident {incident_id} ({service}, {severity}) ran {started_at} to "
                    f"{resolved_at}, overlapping the footprint"
                ),
                kind="fact", outcome="found",
                source=Source(system="product_ops", record_id=incident_id, timestamp=started_at),
                method="sql", supports=[driver.id], strength=0.7, freshness_hours=freshness,
            )
        )
    return items


_INTERPRETERS: dict[str, Interpreter] = {
    "ticket_spike": _ticket_spike,
    "price_delta": _price_delta,
    "lost_reason_scan": _lost_reason_scan,
    "incident_scan": _incident_scan,
}
