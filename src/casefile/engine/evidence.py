"""Stage 4 · Gather evidence — §15 S4a and S4c.

*"Going door to door. Run the precise numbers... And write down what you
didn't find: 'we checked 12 lost-reason fields, none mention a competitor'
is a real finding."*

## 4a — probes, counted absence

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

## 4c — schema-forced extraction, LLM #2

`retrieval.retrieve` hands back a `Funnel` of documents already scoped to one
driver's `evidence_sources` and `max_lag_days`. The model reads them and
proposes claims; **the same three-outcome discipline as 4a applies**, and the
same rule that outcome is a property of the text, never of which corpus role
(signal, misdirection, noise) a human author assigned it — the pipeline
cannot see that tag, and would not be allowed to use it if it could.

Every claim the model proposes is checked in code before it becomes an
`EvidenceItem`, not merely requested in the prompt: its `doc_id` must name a
document actually in the funnel, and its `quote` must be an exact, verbatim
substring of that document's text (whitespace-normalised only). A model that
invents either is not trusted — the claim is dropped, the same way
`hypothesise.py`'s guardrail never trusts an invented driver id. `claim`
itself, the one-sentence gloss on *why* the quote matters, is left as prose —
unverifiable by construction, like `Hypothesis.rationale`, and never the
field anything downstream keys off of.

A driver whose `evidence_sources` are entirely structured (§24's
`seasonality`, whose only source is `historical_series`) is skipped here too,
for the same reason 4a skips a driver with no `probe_sql`: there is nothing
document-shaped to retrieve, so there is no call to make.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import date, datetime
from pathlib import Path

import duckdb
from pydantic import BaseModel

from casefile.llm.base import LLMProvider, Prompt
from casefile.models import Driver, EvidenceItem, Footprint, Hypothesis, KPIContract, Source, Usage
from casefile.retrieval import Funnel, retrieve
from casefile.retrieval.scope import SOURCE_TABLES

ROOT = Path(__file__).resolve().parents[3]

#: Ticket volume at or above this multiple of its own prior-period baseline
#: counts as a spike — comfortably below §24's injected 4.2x, comfortably
#: above the noise a quiet account's week-to-week count carries on its own.
SPIKE_RATIO = 1.5
COMPETITOR_CODES = ("competitor_price", "competitor_features")

#: A single document's assertion, verified only as a real quote — weaker than
#: a directly measured fact (4a's price-book fact is 0.8) but not negligible.
DOCUMENT_STRENGTH = 0.6
#: Documents were retrieved and read; nothing in them bore on the driver. A
#: softer absence than a complete structured-field scan (4a's 0.6-0.8 range),
#: since a handful of documents is not the same as a counted, exhaustive field.
ABSENCE_STRENGTH = 0.5


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


# ── 4c · Schema-forced extraction ───────────────────────────────────────────


class ExtractedClaim(BaseModel):
    """The model's proposal. `doc_id` and `quote` are verified against the
    funnel before either is trusted — see `_guardrail`."""

    doc_id: str
    quote: str
    claim: str
    supports: bool


class ExtractionResponse(BaseModel):
    claims: list[ExtractedClaim]


def extract_claims(
    contract: KPIContract,
    hypotheses: list[Hypothesis],
    footprint: Footprint,
    con: duckdb.DuckDBPyConnection,
    provider: LLMProvider,
    as_of: datetime | None = None,
) -> tuple[list[EvidenceItem], list[Usage]]:
    """Retrieves and extracts for every hypothesis with a document-bearing
    driver, in hypothesis order. One model call per driver — the funnel each
    retrieves is scoped to that driver's own `evidence_sources` and
    `max_lag_days`, so there is no single combined document set to extract
    from in one call the way 4a has a single registry to annotate in one."""
    as_of = as_of or _default_as_of(con)
    items: list[EvidenceItem] = []
    usages: list[Usage] = []
    for hypothesis in hypotheses:
        driver = _driver(contract, hypothesis.driver_id)
        if driver is None or not _has_documents(driver):
            continue

        funnel = retrieve(con, footprint, hypothesis.rationale, driver=driver)
        if not funnel:
            items.append(_uncheckable(driver, as_of, footprint))
            continue

        prompt = _prompt(driver, hypothesis, funnel)
        response, usage = provider.complete(prompt, ExtractionResponse)
        usages.append(usage)

        claims = _guardrail(response.claims, funnel)
        if not claims:
            items.append(_checked_absent(driver, as_of, footprint, len(funnel)))
            continue
        items.extend(_items(driver, claims, funnel, as_of, footprint))
    return items, usages


def _has_documents(driver: Driver) -> bool:
    return any(source in SOURCE_TABLES for source in driver.evidence_sources)


def _prompt(driver: Driver, hypothesis: Hypothesis, funnel: Funnel) -> Prompt:
    system = (
        "You are reading retrieved documents for evidence about one candidate "
        "cause of a business KPI movement. For each document that contains a "
        "passage bearing on this cause — supporting it or contradicting it — "
        "return one claim: the document's id, a one-sentence paraphrase of why "
        "the passage matters, whether the passage supports or contradicts the "
        "cause, and the passage itself, copied character-for-character from "
        "the document — never summarised, shortened or reworded. A document "
        "that says nothing about this cause contributes no claim; do not force "
        "one. Never invent a document id, and never quote text that is not "
        "actually present in the document below."
    )
    listed = "\n\n".join(f"[{doc.doc_id}] {doc.text}" for doc in funnel)
    user = (
        f"Candidate cause: {driver.id} — {hypothesis.rationale}\n\n"
        f"Documents:\n{listed}\n\n"
        "Return one claim per document that bears on this cause, referencing "
        "its id, or no claims at all if none do."
    )
    return Prompt(stage="s4c", system=system, user=user)


def _guardrail(raw: list[ExtractedClaim], funnel: Funnel) -> list[ExtractedClaim]:
    """'Schema-forced' guarantees the *shape* of the response; it guarantees
    nothing about its content. This is where the content is checked: a
    `doc_id` naming no retrieved document, or a `quote` that is not an actual
    substring of that document's text, is dropped rather than trusted."""
    by_id = {doc.doc_id: doc for doc in funnel}
    kept = []
    for claim in raw:
        doc = by_id.get(claim.doc_id)
        if doc is None:
            continue
        if _normalise(claim.quote) not in _normalise(doc.text):
            continue
        kept.append(claim)
    return kept


def _normalise(text: str) -> str:
    return " ".join(text.split())


def _items(
    driver: Driver,
    claims: list[ExtractedClaim],
    funnel: Funnel,
    as_of: datetime,
    footprint: Footprint,
) -> list[EvidenceItem]:
    by_id = {doc.doc_id: doc for doc in funnel}
    freshness = _freshness_hours(as_of, footprint)
    items: list[EvidenceItem] = []
    for i, claim in enumerate(claims, start=1):
        doc = by_id[claim.doc_id]
        items.append(
            EvidenceItem(
                id=f"ev-{driver.id}-doc-{i:03d}",
                claim=claim.claim,
                kind="document", outcome="found",
                source=Source(
                    system=doc.table.split(".")[0], record_id=doc.doc_id,
                    timestamp=_ts(doc.when),
                ),
                method="llm_extraction",
                supports=[driver.id] if claim.supports else [],
                contradicts=[] if claim.supports else [driver.id],
                strength=DOCUMENT_STRENGTH, freshness_hours=freshness,
                quote=claim.quote,
            )
        )
    return items


def _uncheckable(driver: Driver, as_of: datetime, footprint: Footprint) -> EvidenceItem:
    sources = ", ".join(driver.evidence_sources)
    return EvidenceItem(
        id=f"ev-{driver.id}-doc-000",
        claim=f"no documents on this footprint's {sources} sources fall inside the lag window",
        kind="absence", outcome="uncheckable",
        source=Source(
            system="corpus", record_id=f"{driver.id}:no_documents",
            timestamp=_ts(footprint.window_end),
        ),
        method="retrieval", supports=[driver.id], strength=0.0,
        freshness_hours=_freshness_hours(as_of, footprint), coverage=0.0,
    )


def _checked_absent(
    driver: Driver, as_of: datetime, footprint: Footprint, read: int
) -> EvidenceItem:
    return EvidenceItem(
        id=f"ev-{driver.id}-doc-000",
        claim=f"{read} retrieved document(s) were read; none bear on {driver.id}",
        kind="absence", outcome="checked_absent",
        source=Source(
            system="corpus", record_id=f"{driver.id}:no_claims_extracted",
            timestamp=_ts(footprint.window_end),
        ),
        method="llm_extraction", contradicts=[driver.id], strength=ABSENCE_STRENGTH,
        freshness_hours=_freshness_hours(as_of, footprint), denominator=read,
    )
