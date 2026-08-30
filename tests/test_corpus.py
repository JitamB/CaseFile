"""Ladder step 1.5 — the frozen text corpus.

The step's verify command from §44:

    "85% noise measured; the misleading documents are present and findable"

Both halves, and the second one is the harder claim. *Present* is a row in a
table; *findable* means the document sits on a footprint account inside the
footprint window, so Stage 4b's exact filter will hand it to the extractor. A
misdirection document the pipeline can never retrieve is not a test of anything —
it is a file that makes the corpus look honest.
"""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

import duckdb
import pytest

from casefile.data.corpus import (
    AUTHORED_DIR,
    CATEGORY_WEIGHTS,
    NOISE_CATEGORIES,
    CorpusError,
    is_noise,
    load_authored,
    noise_share,
)
from casefile.data.scm import INTEGRATION_ONSET, TREATED

ROOT = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.gate1

#: The two accounts §25 A's footprint resolves to, and the window around them.
FOOTPRINT = ("ACC-0001", "ACC-0002")
WINDOW = (date(2026, 3, 1), date(2026, 4, 30))


@pytest.fixture(scope="module")
def con(warehouse: Path) -> duckdb.DuckDBPyConnection:
    connection = duckdb.connect(str(warehouse), read_only=True)
    yield connection
    connection.close()


@pytest.fixture(scope="module")
def authored() -> list:
    return load_authored()


# ── "85% noise measured" ──────────────────────────────────────────────────────


def test_the_noise_floor_is_where_section_24_says_it_is(
    con: duckdb.DuckDBPyConnection, authored: list
) -> None:
    """§24: *"~85% irrelevant traffic — password resets, billing queries, feature
    requests. Finding a needle in a stack of needles proves nothing."*

    Measured over every ticket in the corpus, which is where the volume is. The
    authored documents are excluded from the noise count whatever their role:
    signal, misdirection and the deliberately ambiguous alike are all things an
    investigator would want to read.
    """
    ids = {d.doc_id for d in authored}
    rows = con.execute("SELECT ticket_id, category FROM product_ops.ticket").fetchall()
    measured = noise_share(
        [(str(category), "authored" if str(ticket) in ids else None) for ticket, category in rows]
    )

    assert 0.83 <= measured <= 0.90, f"noise floor measured at {measured:.1%}"


def test_the_category_weights_are_what_make_the_claim_measurable() -> None:
    """A floor asserted on the corpus and a floor asserted on the weights that
    built it are two different statements, and the second is what stops somebody
    reweighting the templates and finding out at G2."""
    assert sum(CATEGORY_WEIGHTS.values()) == pytest.approx(1.0)
    assert sum(CATEGORY_WEIGHTS[c] for c in NOISE_CATEGORIES) == pytest.approx(0.85)


def test_the_treated_accounts_are_the_exception_to_the_floor(
    con: duckdb.DuckDBPyConnection,
) -> None:
    """The signal has to be somewhere. On the two footprint accounts after the
    onset, integration is the *majority* category — which is the spike §24
    injects, showing up as documents rather than as a count."""
    row = con.execute(
        "SELECT avg(CASE WHEN category = 'integration' THEN 1.0 ELSE 0.0 END) "
        "FROM product_ops.ticket WHERE account_id IN ? AND created_at >= ?",
        [list(FOOTPRINT), INTEGRATION_ONSET],
    ).fetchone()
    assert row is not None
    assert row[0] > 0.5

    elsewhere = con.execute(
        "SELECT avg(CASE WHEN category = 'integration' THEN 1.0 ELSE 0.0 END) "
        "FROM product_ops.ticket WHERE account_id NOT IN ?",
        [list(FOOTPRINT)],
    ).fetchone()
    assert elsewhere is not None
    assert elsewhere[0] < 0.15


# ── "The misleading documents are present and findable" ──────────────────────


def test_every_authored_document_reached_the_warehouse(
    con: duckdb.DuckDBPyConnection, authored: list
) -> None:
    """A committed document that never became a row is a file that makes the
    corpus look honest without making it so."""
    present = set()
    for table, column in (
        ("crm.opportunity_note", "note_id"),
        ("product_ops.news_item", "news_id"),
    ):
        present |= {
            str(r[0]) for r in con.execute(f"SELECT {column} FROM {table}").fetchall()
        }

    bodies = {
        str(r[0]) for r in con.execute("SELECT body_text FROM product_ops.ticket").fetchall()
    }

    for document in authored:
        if document.table == "product_ops.ticket":
            assert document.body in bodies, f"{document.doc_id} never reached a ticket row"
        else:
            assert document.doc_id in present, f"{document.doc_id} never reached a row"


def test_all_three_kinds_of_misleading_document_exist(authored: list) -> None:
    """§24's third honesty control names three: *"a ticket that mentions the
    integration and concludes it was fine; a CRM note blaming pricing with no
    evidence; genuinely ambiguous notes."*"""
    roles = {d.role for d in authored}
    assert {"signal", "misdirection", "ambiguous"} <= roles

    misdirection = [d for d in authored if d.role == "misdirection"]
    assert len(misdirection) >= 3

    integration_but_fine = [
        d for d in misdirection
        if d.table == "product_ops.ticket" and "no fault found" in d.body
    ]
    pricing_without_evidence = [
        d for d in misdirection if d.get("driver") == "pricing_change"
    ]
    assert integration_but_fine, "no ticket that mentions the integration and clears it"
    assert len(pricing_without_evidence) >= 2, "no note blaming pricing without evidence"
    assert [d for d in authored if d.role == "ambiguous"]


def test_the_misleading_documents_sit_where_retrieval_will_find_them(
    authored: list,
) -> None:
    """*Findable*, not merely present. Stage 4b filters by footprint — exact, not
    semantic — so a misdirection document outside the footprint accounts or
    outside the window is one the pipeline can never be misled by, and testing
    against it would prove nothing."""
    reachable = [
        d
        for d in authored
        if d.role in ("misdirection", "ambiguous")
        and d.account in FOOTPRINT
        and WINDOW[0] <= date.fromisoformat(d.date) <= WINDOW[1]
    ]
    assert len(reachable) >= 4, "the decoy documents are outside the footprint"


def test_the_true_cause_is_written_down_where_a_reader_could_find_it(
    authored: list,
) -> None:
    """The other side of the same coin. §35.2's ev-004 is *"the ACME renewal call
    notes record the integration backlog as the reason for deferring
    signature"* — that document has to exist for extraction to have anything to
    extract."""
    signal = [d for d in authored if d.role == "signal" and d.get("driver") == "integration_delay"]
    on_footprint = [d for d in signal if d.account in FOOTPRINT]

    assert len(on_footprint) >= 4
    assert any("integration" in d.body.lower() and "renew" in d.body.lower() for d in signal)


def test_the_competitor_coverage_is_apac_only_and_dated_after_the_decline(
    con: duckdb.DuckDBPyConnection,
) -> None:
    """§25's competitor decoy dies on Timing *and* Locality, and both facts live
    in the news feed rather than in a constant."""
    rows = con.execute(
        "SELECT published_at, region FROM product_ops.news_item WHERE competitor <> ''"
    ).fetchall()

    assert rows, "the competitor decoy has no coverage at all"
    assert {str(region) for _, region in rows} == {"APAC"}
    assert all(published.date() >= date(2026, 4, 20) for published, _ in rows)


# ── The corpus is templates plus authorship, and stays that way ──────────────


def test_text_was_written_onto_the_rows_the_causal_model_made(
    con: duckdb.DuckDBPyConnection, authored: list
) -> None:
    """Authored tickets **replace** a body rather than adding a row. Adding one
    would put a document in the corpus that the SCM never decided existed, and
    the ticket count and the ticket documents would drift apart — which is the
    one thing ladder step 0.7 left `body_text` empty to prevent."""
    tickets = [d for d in authored if d.table == "product_ops.ticket"]
    assert tickets

    row = con.execute(
        "SELECT count(*), count(DISTINCT ticket_id) FROM product_ops.ticket"
    ).fetchone()
    assert row is not None
    assert row[0] == row[1], "a ticket id appears twice"

    matched = con.execute(
        "SELECT count(*) FROM product_ops.ticket WHERE body_text IN ?",
        [[d.body for d in tickets]],
    ).fetchone()
    assert matched is not None
    assert matched[0] == len(tickets)


def test_the_unstructured_tables_section_22_names_are_all_populated(
    con: duckdb.DuckDBPyConnection,
) -> None:
    """§22 marks four tables unstructured. Three of them did not exist before
    this step, and a schema that lists a table nobody writes is documentation."""
    for table, low, high in (
        ("crm.opportunity_note", 7_000, 12_000),
        ("product_ops.ticket", 38_000, 52_000),
        ("product_ops.ticket_message", 3_000, 20_000),
        ("product_ops.news_item", 150, 260),
    ):
        row = con.execute(f"SELECT count(*) FROM {table}").fetchone()
        assert row is not None
        assert low <= row[0] <= high, f"{table} holds {row[0]} rows"


def test_ticket_messages_hang_off_tickets_that_were_escalated(
    con: duckdb.DuckDBPyConnection,
) -> None:
    """Only P1 tickets carry a thread. Generating a conversation for forty
    thousand password resets would triple the corpus to say nothing."""
    row = con.execute(
        "SELECT count(*) FROM product_ops.ticket_message m "
        "JOIN product_ops.ticket t ON t.ticket_id = m.ticket_id WHERE t.priority <> 'P1'"
    ).fetchone()
    assert row is not None and row[0] == 0

    orphans = con.execute(
        "SELECT count(*) FROM product_ops.ticket_message m WHERE NOT EXISTS "
        "(SELECT 1 FROM product_ops.ticket t WHERE t.ticket_id = m.ticket_id)"
    ).fetchone()
    assert orphans is not None and orphans[0] == 0


def test_notes_and_news_carry_real_text_rather_than_placeholders(
    con: duckdb.DuckDBPyConnection,
) -> None:
    for table, column in (
        ("crm.opportunity_note", "body_text"),
        ("product_ops.news_item", "body_text"),
    ):
        row = con.execute(
            f"SELECT count(*) FILTER (WHERE trim({column}) = ''), "
            f"count(DISTINCT {column}) FROM {table}"
        ).fetchone()
        assert row is not None
        assert row[0] == 0, f"{table} has empty bodies"
        assert row[1] > 5, f"{table} has one template and no variation"


# ── The authored loader refuses what it cannot attach ────────────────────────


def test_a_document_with_no_front_matter_is_refused(tmp_path: Path) -> None:
    (tmp_path / "stray.md").write_text("just some prose\n", encoding="utf-8")
    with pytest.raises(CorpusError, match="front-matter fence"):
        load_authored(tmp_path)


def test_a_document_missing_a_required_field_is_refused(tmp_path: Path) -> None:
    (tmp_path / "half.md").write_text(
        "---\ndoc_id: half\ntable: crm.opportunity_note\n---\nbody\n", encoding="utf-8"
    )
    with pytest.raises(CorpusError, match="'date'"):
        load_authored(tmp_path)


def test_two_documents_cannot_share_an_id(tmp_path: Path) -> None:
    header = "---\ndoc_id: same\ntable: crm.opportunity_note\ndate: 2026-01-01\nrole: signal\n---\n"
    (tmp_path / "a.md").write_text(header + "one\n", encoding="utf-8")
    (tmp_path / "b.md").write_text(header + "two\n", encoding="utf-8")
    with pytest.raises(CorpusError, match="duplicate doc_id"):
        load_authored(tmp_path)


def test_an_authored_ticket_that_attaches_to_nothing_raises(authored: list) -> None:
    """The failure that would otherwise be silent: a hand-written document is
    committed, reviewed, and then quietly never becomes a row because the date
    it names has no ticket on it. The corpus would look richer than it is and
    every test over it would still pass."""
    from casefile.data.corpus import Authored
    from casefile.data.generator import _apply_authored_tickets

    rows = [
        ["TKT-000001", "ACC-0001", "P3", "how_to", "2026-03-16T09:00:00",
         "2026-03-16T09:20:00", "", "open", "subject", "body"],
    ]
    stray = Authored(
        doc_id="nowhere",
        table="product_ops.ticket",
        role="signal",
        front={"account": "ACC-0001", "date": "2025-01-01"},
        body="a document about a day with no tickets on it",
    )

    with pytest.raises(ValueError, match="unretrievable"):
        _apply_authored_tickets(rows, [stray])

    _apply_authored_tickets(rows, [stray.__class__(**{**stray.__dict__, "front": {
        "account": "ACC-0001", "date": "2026-03-16"}})])
    assert rows[0][9] == stray.body


def test_an_authored_document_is_never_counted_as_noise() -> None:
    """Signal, misdirection and the deliberately ambiguous are all things an
    investigator would want to read, whatever category the row carries. Counting
    a hand-written misdirection ticket as noise because it is filed under
    `access` would let the floor drift while the arithmetic still agreed."""
    assert is_noise("access", authored_role=None) is True
    assert is_noise("access", authored_role="misdirection") is False
    assert is_noise("integration", authored_role="noise") is True

    mixed = [("access", None), ("access", "misdirection"), ("how_to", None), ("integration", None)]
    assert noise_share(mixed) == pytest.approx(0.5)
    assert noise_share([]) == 0.0


def test_the_authored_directory_is_committed_and_not_empty() -> None:
    """§41.2 with the correction this step earns: the authored documents are
    committed because they are the part a reviewer has to read in a diff; the
    ~46k template documents regenerate from the seed instead of living in git."""
    assert AUTHORED_DIR.is_dir()
    assert len(list(AUTHORED_DIR.glob("*.md"))) >= 20


def test_the_treated_accounts_are_named_in_the_authored_signal(authored: list) -> None:
    """A sanity check on the hand-written half: if the names in `scm.TREATED`
    ever change, the authored documents point at accounts that no longer carry
    the injected event and the whole corpus quietly stops being about anything."""
    ids = {d.account for d in authored if d.account}
    assert set(FOOTPRINT) <= ids
    assert TREATED == ("ACME", "NORTHWIND")


def test_every_committed_document_is_readable_as_a_document() -> None:
    """The files are Markdown a person can read, not a serialisation format."""
    for path in sorted(AUTHORED_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        assert text.startswith("---\n")
        body = text.split("---\n", 2)[2].strip()
        assert len(body.split()) >= 25, f"{path.name} is too short to carry anything"


def test_the_generated_corpus_is_not_committed() -> None:
    """The other half of the §41.2 correction. If `data/raw/` ever entered git,
    `make data` would stop being the thing that produces it and a stale corpus
    could outlive the generator that made it."""
    import subprocess

    tracked = subprocess.run(
        ["git", "ls-files", "data/raw", "data/corpus"],
        capture_output=True, text=True, cwd=ROOT, check=True,
    ).stdout.split()

    assert not [p for p in tracked if p.startswith("data/raw")]
    assert all(p.startswith("data/corpus/authored/") or p.endswith(".gitkeep") for p in tracked)


def test_the_authored_documents_are_plain_utf8_with_no_stray_csv_hazards() -> None:
    """Every body ends up inside a CSV cell. A stray carriage return or a NUL
    would survive the writer and surface as a mangled row three stages later."""
    for document in load_authored():
        assert "\r" not in document.body and "\x00" not in document.body
        assert csv.writer.__module__  # the writer these will pass through
