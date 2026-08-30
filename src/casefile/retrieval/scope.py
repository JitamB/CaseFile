"""Stage 4b, first half — the footprint filter. §15 S4b.

    45,000 docs -> filter by footprint (exact, not semantic) -> ~200 -> BM25 -> top 15

**Exact, not semantic**, and that word is doing all the work. Every token saved
here is saved with certainty: a ticket belonging to an account outside the
footprint cannot be evidence about the footprint, whatever it says. Semantic
narrowing at this stage would trade a guarantee for a similarity score and put
the 10-15x cost reduction in §19 at the mercy of an embedding.

The second narrowing is per hypothesis. §14.1 gives every driver its
`evidence_sources` and its `max_lag_days`, so *"which documents could bear on
this driver?"* is a contract lookup, not a judgement: a cause cannot have acted
outside its own plausible lag, and a source the driver does not name is not
evidence about it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import duckdb

from casefile.models import Driver, Footprint

#: §14.1's `evidence_sources` vocabulary -> the §22 tables that hold that text.
#: `crm_lost_reason`, `price_book` and `historical_series` are deliberately
#: absent: they are structured, and §15 S4a probes them in SQL. Retrieval is for
#: documents, and pretending a lost-reason code is a document would put a claim
#: through the extractor that arithmetic already knows exactly.
SOURCE_TABLES: dict[str, tuple[str, ...]] = {
    "tickets": ("product_ops.ticket", "product_ops.ticket_message"),
    "crm_notes": ("crm.opportunity_note",),
    "deploy_log": ("product_ops.deploy_event",),
    "incident": ("product_ops.incident",),
    "news": ("product_ops.news_item",),
}

#: Every table retrieval can read, and how to read it as a document.
#: `account` is None where the table has no account of its own — news is about a
#: market, not a customer, so the footprint cannot filter it by entity.
_READERS: dict[str, tuple[str, str | None, str, str]] = {
    # table: (id column, account column, timestamp column, title column)
    "product_ops.ticket": ("ticket_id", "account_id", "created_at", "subject"),
    "product_ops.ticket_message": ("message_id", "account_id", "created_at", "author_user_id"),
    "crm.opportunity_note": ("note_id", "account_id", "created_at", "author_user_id"),
    "product_ops.deploy_event": ("deploy_id", None, "deployed_at", "service"),
    "product_ops.incident": ("incident_id", None, "started_at", "service"),
    "product_ops.news_item": ("news_id", None, "published_at", "headline"),
}

_BODY = {
    "product_ops.deploy_event": "change_summary",
    "product_ops.incident": "severity",
}


@dataclass(frozen=True)
class Document:
    """One retrievable thing. `account` is None for market-level sources."""

    doc_id: str
    table: str
    account: str | None
    when: date
    title: str
    body: str

    @property
    def text(self) -> str:
        return f"{self.title}. {self.body}".strip()


def scope(
    con: duckdb.DuckDBPyConnection,
    footprint: Footprint,
    driver: Driver | None = None,
) -> list[Document]:
    """Every document the footprint admits, in a stable order.

    With no `driver`, every readable table is searched. With one, only the tables
    its `evidence_sources` name, and only back as far as its `max_lag_days`
    allows — a cause that acts within 45 days cannot be evidenced by a note from
    the year before.
    """
    accounts = footprint.entities.get("account_id", [])
    start = footprint.window_start
    if driver is not None and driver.max_lag_days:
        start = min(start, footprint.window_end - timedelta(days=driver.max_lag_days))

    tables = _tables_for(driver)
    documents: list[Document] = []
    for table in tables:
        documents.extend(
            _read(con, table, accounts, start, footprint.window_end)
        )
    return sorted(documents, key=lambda d: (d.when, d.table, d.doc_id))


#: Tables whose rows belong to an account. The footprint scopes by entity, so a
#: source with no entity cannot be narrowed by it — a news item is about a market,
#: not a customer. Those are reachable **only** through a driver that names them
#: in `evidence_sources`: without that rule an unscoped search returns the whole
#: news feed, and generic short documents crowd out the account's own tickets.
ENTITY_SCOPED = ("product_ops.ticket", "product_ops.ticket_message", "crm.opportunity_note")


def _tables_for(driver: Driver | None) -> list[str]:
    if driver is None:
        return list(ENTITY_SCOPED)
    wanted: list[str] = []
    for source in driver.evidence_sources:
        wanted += [t for t in SOURCE_TABLES.get(source, ()) if t not in wanted]
    return wanted


def _read(
    con: duckdb.DuckDBPyConnection,
    table: str,
    accounts: list[str],
    start: date,
    end: date,
) -> list[Document]:
    identifier, account_column, stamp, title = _READERS[table]
    body = _BODY.get(table, "body_text")

    source = table
    select_account = f"{table}.{account_column}" if account_column else "NULL"
    if table == "product_ops.ticket_message":
        # A message has no account column of its own; it inherits its ticket's,
        # and carries it forward so every retrieved document can say whose it is.
        source = f"{table} JOIN product_ops.ticket USING (ticket_id)"
        select_account = "product_ops.ticket.account_id"

    where = [f"{table}.{stamp}::DATE BETWEEN ? AND ?"]
    params: list[object] = [start, end]
    if account_column is not None and accounts:
        where.append(f"{select_account} IN ?")
        params.append(accounts)

    rows = con.execute(
        f"SELECT {table}.{identifier}, {select_account}, {table}.{stamp}::DATE, "
        f"{table}.{title}, {table}.{body} FROM {source} WHERE {' AND '.join(where)}",
        params,
    ).fetchall()

    return [
        Document(
            doc_id=str(row[0]),
            table=table,
            account=None if row[1] is None else str(row[1]),
            when=row[2],
            title="" if row[3] is None else str(row[3]),
            body="" if row[4] is None else str(row[4]),
        )
        for row in rows
    ]


def corpus_size(con: duckdb.DuckDBPyConnection) -> int:
    """Every document in the warehouse — the left-hand side of §15's funnel."""
    total = 0
    for table in _READERS:
        row = con.execute(f"SELECT count(*) FROM {table}").fetchone()
        assert row is not None
        total += int(row[0])
    return total
