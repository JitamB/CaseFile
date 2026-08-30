"""Ladder step 1.6 — Stage 4b, decomposition-scoped retrieval.

The step's verify command from §44:

    "45k -> ~200 -> top 15 on the East fixture"

The funnel is here, measured rather than quoted, and so is the number that
settles §18's open question about the ranker: **recall@15 over the authored
signal documents**. Those documents are ground truth we wrote ourselves, so
*"did the ranker surface the evidence?"* is a measurement and not an opinion.
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from pathlib import Path

import duckdb
import pytest

from casefile.contract import load_all
from casefile.data.corpus import load_authored
from casefile.engine.decompose import decompose
from casefile.models import Driver, Footprint, KPIContract
from casefile.retrieval import Document, corpus_size, retrieve, scope, top
from casefile.retrieval.rank import BM25Ranker, recall_at, tokenise
from casefile.retrieval.scope import ENTITY_SCOPED, SOURCE_TABLES

ROOT = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.gate1

#: The queries Stage 3 will hand retrieval: `Hypothesis.rationale`, taken from
#: the fixture both tracks build against rather than invented for the test.
RATIONALES = {
    "integration_delay": (
        "Both footprint accounts opened integration tickets in the weeks before "
        "their renewal dates."
    ),
    "pricing_change": (
        "A list-price increase took effect on 2026-03-01 across the enterprise segment."
    ),
    "competitor_offer": "A competitor launched a promotion during the quarter.",
}


@pytest.fixture(scope="module")
def contracts() -> dict[str, KPIContract]:
    return load_all(ROOT / "contracts")


@pytest.fixture(scope="module")
def con(warehouse: Path) -> duckdb.DuckDBPyConnection:
    connection = duckdb.connect(str(warehouse), read_only=True)
    yield connection
    connection.close()


@pytest.fixture(scope="module")
def footprint(con: duckdb.DuckDBPyConnection, contracts: dict[str, KPIContract]) -> Footprint:
    """Scenario A's, arrived at by Stage 2 rather than written down here."""
    return decompose(con, contracts["net_revenue"], "2026-04", {"region": "East"}).footprint


def driver(contracts: dict[str, KPIContract], name: str) -> Driver:
    return next(d for d in contracts["net_revenue"].drivers if d.id == name)


def wanted(con: duckdb.DuckDBPyConnection, footprint: Footprint, name: str) -> list[str]:
    """The authored documents a driver's retrieval ought to surface.

    Authored *tickets* replace a generated body rather than adding a row, so they
    live in the corpus under their ticket id. Resolving by body text is what
    makes the measurement about retrieval rather than about ids.
    """
    bodies = {
        str(row[1]): str(row[0])
        for row in con.execute("SELECT ticket_id, body_text FROM product_ops.ticket").fetchall()
    }
    accounts = set(footprint.entities["account_id"])
    return [
        bodies.get(document.body, document.doc_id)
        for document in load_authored()
        if document.get("driver") == name
        and document.role in ("signal", "misdirection")
        and document.account in accounts
        and footprint.window_start <= date.fromisoformat(document.date) <= footprint.window_end
    ]


# ── The funnel — §44's verify command ─────────────────────────────────────────


def test_the_funnel_narrows_by_three_orders_of_magnitude(
    con: duckdb.DuckDBPyConnection, footprint: Footprint
) -> None:
    """§15 S4b, measured. The doc estimates "45,000 -> ~200 -> top 15"; the
    generated corpus is larger and the scoped set wider, so the reduction is
    *bigger* than claimed rather than smaller — but it is quoted here as what it
    is rather than as what was guessed."""
    funnel = retrieve(con, footprint, RATIONALES["integration_delay"])

    assert 55_000 <= funnel.corpus <= 75_000
    assert 700 <= funnel.scoped <= 1_600
    assert len(funnel) <= 15
    assert funnel.reduction > 1_000


def test_the_first_narrowing_is_exact_and_not_semantic(
    con: duckdb.DuckDBPyConnection, footprint: Footprint
) -> None:
    """§15 says so in those words, and it is the reason the token saving is a
    guarantee: a ticket belonging to an account outside the footprint cannot be
    evidence about the footprint, whatever it says."""
    accounts = set(footprint.entities["account_id"])
    scoped = scope(con, footprint)

    assert scoped
    assert {d.account for d in scoped} <= accounts
    assert all(footprint.window_start <= d.when <= footprint.window_end for d in scoped)


def test_a_market_level_source_is_out_of_scope_unless_a_driver_asks_for_it(
    con: duckdb.DuckDBPyConnection, footprint: Footprint, contracts: dict[str, KPIContract]
) -> None:
    """A news item is about a market, not a customer, so the footprint cannot
    narrow it by entity. Searching it unscoped returned the whole news feed and
    generic short documents crowded out the account's own tickets — six of the
    first fifteen. It is reachable only through a driver that names it."""
    assert "product_ops.news_item" not in ENTITY_SCOPED
    assert {d.table for d in scope(con, footprint)} <= set(ENTITY_SCOPED)

    competitor = scope(con, footprint, driver(contracts, "competitor_offer"))
    assert any(d.table == "product_ops.news_item" for d in competitor)


def test_each_driver_searches_only_the_sources_its_contract_names(
    con: duckdb.DuckDBPyConnection, footprint: Footprint, contracts: dict[str, KPIContract]
) -> None:
    """*"Which documents could bear on this driver?"* is a contract lookup, not a
    judgement — §14.1 gives every driver its `evidence_sources`."""
    for name in ("integration_delay", "pricing_change", "competitor_offer"):
        spec = driver(contracts, name)
        allowed = {t for source in spec.evidence_sources for t in SOURCE_TABLES.get(source, ())}
        assert {d.table for d in scope(con, footprint, spec)} <= allowed


def test_a_structured_source_is_not_retrieved_as_a_document(
    contracts: dict[str, KPIContract]
) -> None:
    """`crm_lost_reason` and `price_book` are columns, and §15 S4a probes them in
    SQL. Putting a lost-reason code through the extractor would ask a model to
    read a value arithmetic already knows exactly."""
    assert "crm_lost_reason" not in SOURCE_TABLES
    assert "price_book" not in SOURCE_TABLES
    assert "historical_series" not in SOURCE_TABLES


def test_a_drivers_lag_widens_the_window_it_can_look_back_through(
    con: duckdb.DuckDBPyConnection, footprint: Footprint, contracts: dict[str, KPIContract]
) -> None:
    """A cause that acts within 45 days cannot be evidenced by a note from the
    year before — and equally, a 90-day driver must be able to see further back
    than the movement's own window."""
    short = driver(contracts, "supply_delay")  # max_lag_days 30
    long = driver(contracts, "competitor_offer")  # max_lag_days 90

    earliest = min(d.when for d in scope(con, footprint, long))
    assert earliest < footprint.window_start
    assert earliest >= footprint.window_end - timedelta(days=long.max_lag_days)
    assert min(d.when for d in scope(con, footprint, short)) >= earliest


# ── The measurement that settles the ranker — §18 ────────────────────────────


@pytest.mark.parametrize("name", sorted(RATIONALES))
def test_bm25_surfaces_every_authored_document_for_every_driver(
    con: duckdb.DuckDBPyConnection,
    footprint: Footprint,
    contracts: dict[str, KPIContract],
    name: str,
) -> None:
    """**The number that decides §18's open question.**

    Queried the way Stage 3 will query it — with the hypothesis rationale, taken
    from the fixture rather than invented here — BM25 puts *every* authored
    signal and misdirection document for every driver inside the top 15. There
    is nothing left for an embedding to recover, so §18's
    `sentence-transformers` is implemented behind the `embed` extra and is not
    the default: 2 GB of torch on every CI run to improve on 1.000 is not a
    trade, and a ranker that changed with what happened to be installed would
    break §35.5's determinism promise.
    """
    spec = driver(contracts, name)
    documents = scope(con, footprint, spec)
    expected = wanted(con, footprint, name)

    assert expected, f"{name} has no authored evidence on the footprint to measure against"
    assert recall_at(documents, RATIONALES[name], expected, k=15) == 1.0


def test_a_bare_driver_id_is_a_worse_query_and_the_misses_are_paraphrase(
    con: duckdb.DuckDBPyConnection, footprint: Footprint, contracts: dict[str, KPIContract]
) -> None:
    """Where a lexical ranker does lose, and why it does not matter here.

    Queried with the registry's own words — "integration delay" — BM25 misses the
    documents that describe the cause in the customer's words: *"the outstanding
    sync-gateway work"*, *"partial exports"*. That is exactly the paraphrase gap
    §18's embeddings exist to close, and it is why the real query is the
    hypothesis rationale rather than the driver id.
    """
    spec = driver(contracts, "integration_delay")
    documents = scope(con, footprint, spec)
    expected = wanted(con, footprint, "integration_delay")

    bare = recall_at(documents, "integration delay", expected, k=15)
    written = recall_at(documents, RATIONALES["integration_delay"], expected, k=15)

    assert bare < written == 1.0
    assert bare >= 0.5


def test_a_document_with_no_overlap_is_not_the_eighth_best_match(
    con: duckdb.DuckDBPyConnection, footprint: Footprint, contracts: dict[str, KPIContract]
) -> None:
    """Returning `k` regardless pads the extractor's input with whatever the
    tie-break surfaced. §19 budgets ~9k input tokens for extraction; fifteen
    documents of which eight score zero spends that on nothing, and gives the
    model eight chances to extract a claim about an irrelevant record."""
    documents = scope(con, footprint, driver(contracts, "pricing_change"))
    results = top(documents, "pricing change", k=15)

    assert 0 < len(results) < 15

    scored = dict(
        zip(
            (d.doc_id for d in documents),
            BM25Ranker().rank(documents, "pricing change"),
            strict=True,
        )
    )
    assert all(scored[d.doc_id] > -math.inf for d in results)
    assert any(score == -math.inf for score in scored.values()), "nothing was excluded"


def test_a_negatively_scored_match_is_still_a_match() -> None:
    """The trap in excluding on the *sign* of the score.

    Okapi's IDF goes negative for a term that appears in more than half the
    corpus, so a set of documents that all discuss the same thing scores every
    one of them below zero. Excluding on the sign would return **nothing** for a
    query about the very topic the set is about — which is what an earlier
    version of `top` did, and what this test was written from.

    Exclusion is on token overlap instead: a fact about the document rather than
    about the scorer, and one an embedding ranker is free not to use.
    """
    identical = [
        Document(f"D{n}", "product_ops.ticket", "ACC-0001", date(2026, 3, 4),
                 "Export failing", "the integration export is failing every night")
        for n in range(4)
    ]

    scores = BM25Ranker().rank(identical, "integration export")
    assert all(score < 0 for score in scores), "this corpus has no negative-IDF case"
    assert all(score > -math.inf for score in scores)
    assert len(top(identical, "integration export", k=4)) == 4

    stray = Document(
        "D9", "product_ops.ticket", "ACC-0001", date(2026, 3, 4),
        "Password reset", "the reset link never arrived",
    )
    unrelated = [*identical, stray]
    assert "D9" not in {d.doc_id for d in top(unrelated, "integration export", k=5)}


def test_ranking_is_the_same_on_two_runs(
    con: duckdb.DuckDBPyConnection, footprint: Footprint
) -> None:
    """§35.5: every numeric field bit-identical across runs. Ties break on
    `(when, table, doc_id)` rather than on whatever order the rows arrived in."""
    query = RATIONALES["integration_delay"]
    first = [d.doc_id for d in retrieve(con, footprint, query)]
    second = [d.doc_id for d in retrieve(con, footprint, query)]

    assert first == second and first


def test_documents_that_score_identically_come_back_in_a_fixed_order() -> None:
    """§24's noise is template-generated, so hundreds of documents share a body
    word for word and therefore share a BM25 score exactly. Which of them reaches
    the top 15 would otherwise be decided by the order DuckDB happened to return
    rows in — and DuckDB promises no order at all."""
    same = [
        Document(f"TKT-{n:04d}", "product_ops.ticket", "ACC-0001", date(2026, 3, 4),
                 "Export queue backed up", "an export that normally takes minutes is queued")
        for n in (9, 3, 7, 1)
    ]

    ordered = [d.doc_id for d in top(same, "export queue", k=3)]
    assert ordered == ["TKT-0001", "TKT-0003", "TKT-0007"]
    assert [d.doc_id for d in top(list(reversed(same)), "export queue", k=3)] == ordered


def test_ranking_does_not_depend_on_the_order_the_rows_arrived_in(
    con: duckdb.DuckDBPyConnection, footprint: Footprint
) -> None:
    """Python's sort is stable, so the same input order gives the same output
    whatever the key — which means the determinism test above would pass with no
    tie-break at all. The claim that actually needs defending is that a *change*
    in the order the warehouse hands back rows cannot move the top 15, because
    §35.5 promises the numbers do not move and DuckDB promises no row order."""
    import random

    documents = scope(con, footprint)
    query = RATIONALES["integration_delay"]
    expected = [d.doc_id for d in top(documents, query)]

    shuffled = list(documents)
    random.Random(4).shuffle(shuffled)
    assert [d.doc_id for d in top(shuffled, query)] == expected


def test_the_stemmer_lets_a_singular_query_reach_a_plural_document() -> None:
    """`competitor-speculation` says "competitors" and the query says
    "competitor". Without normalisation BM25 misses it outright — and a baseline
    without stemming would be artificially weak, which would make the comparison
    against §18's embeddings meaningless rather than favourable."""
    assert tokenise("competitors promotions") == tokenise("competitor promotion")
    assert tokenise("The renewals were deferred") == ["renewal", "defer"]


def test_the_minilm_backend_exists_and_refuses_to_load_itself_by_accident() -> None:
    """§18's named model is implemented rather than dismissed, and it is never
    selected by availability: a ranker that switched on because a library
    happened to be installed would make the top 15 depend on the machine."""
    from casefile.retrieval.rank import MiniLMRanker

    assert MiniLMRanker.name == "minilm"
    with pytest.raises(ImportError, match="embed"):
        MiniLMRanker()


# ── Edges ─────────────────────────────────────────────────────────────────────


def test_a_footprint_with_no_documents_returns_nothing_rather_than_everything(
    con: duckdb.DuckDBPyConnection
) -> None:
    empty = Footprint(
        entities={"account_id": ["ACC-9999"]},
        window_start=date(2026, 3, 1),
        window_end=date(2026, 4, 30),
        delta=-1.0,
    )
    assert scope(con, empty) == []
    assert retrieve(con, empty, "anything") == []


def test_recall_over_nothing_is_refused() -> None:
    with pytest.raises(ValueError, match="empty set"):
        recall_at([], "query", [])


def test_the_corpus_count_is_every_readable_table(con: duckdb.DuckDBPyConnection) -> None:
    by_hand = sum(
        int(con.execute(f"SELECT count(*) FROM {table}").fetchone()[0])  # type: ignore[index]
        for table in (
            "product_ops.ticket", "product_ops.ticket_message", "crm.opportunity_note",
            "product_ops.deploy_event", "product_ops.incident", "product_ops.news_item",
        )
    )
    assert corpus_size(con) == by_hand
