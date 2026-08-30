"""Render the causal model to three sources at three grains — §22, §24.

`scm.py` decides what happened. This file decides what each department wrote
down about it, which is a different question and the reason the pipeline has
work to do: finance keeps invoices, sales keeps opportunities, support keeps
tickets, and none of them agrees with the others about customer identity.

**Determinism is the deliverable here**, not a nicety — ladder step 0.7 is
verified by `make data` twice producing identical bytes, and every later gate
runs against this data. So: one seeded `random.Random`, iteration over lists
only, money formatted to two places, ISO dates, `\\n` line endings, and no call
to the wall clock anywhere. `scm.AS_OF` is the present.

Writes the sealed answer sheet alongside the data. Nothing outside `tests/` may
read it back — `tools/check_ground_truth_isolation.py` enforces that, and this
module is its one allowed exception because it is the module that *authors* the
file. Writing is not reading.
"""

from __future__ import annotations

import csv
import hashlib
import json
import random
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from casefile.data import corpus
from casefile.data.scm import (
    AS_OF,
    INTEGRATION_ONSET,
    LOST_REASONS,
    OPS_END,
    OPS_START,
    PRICING_ONSET,
    PRICING_UPLIFT,
    PRODUCTS,
    REFUND_AMOUNT,
    REFUND_MONTH,
    REFUND_REASON,
    SCENARIO_B_DEAL_VALUE,
    SCENARIO_B_ONSET,
    SCENARIO_C_END,
    SCENARIO_C_MULTIPLIER,
    SCENARIO_C_START,
    SPAN_END,
    SPAN_START,
    Account,
    World,
    day_range,
    month_range,
    read_seed,
    seasonal_factor,
)

SERVICES = ("sync-gateway", "billing-core", "insight-api", "edge-router")
SEVERITIES = ("sev1", "sev2", "sev3")
#: §25 B's injected rows, distinguishable from an organic "OPP-" id so
#: `_opportunity_notes` can skip drawing notes for them.
SCENARIO_B_ID_PREFIX = "OPPB-"

#: Usage lines on top of the recurring subscription. §23's PVM needs price *and*
#: volume to move, which a pure subscription line cannot supply on its own.
USAGE_LINES = (5, 12)


@dataclass(frozen=True)
class _UsageTerms:
    """What an account agreed to, once. Everything monthly varies around it."""

    lines: int
    qty: int
    price: float
    recurring_discount: float
    usage_discount: float


def generate(out_dir: Path | str, seed: int | None = None) -> dict[str, str]:
    """Write every structured table under `out_dir/raw/`, the sealed answer
    sheet and a manifest of sha256 digests beside it. Returns the manifest.

    The manifest is what ladder step 0.7 is verified against: a DuckDB file's
    byte-identity is DuckDB's business, but a digest over the CSVs the loader
    reads is ours, and it is the artefact `make data` twice must reproduce.
    """
    out = Path(out_dir)
    world = World(seed)
    # A separate stream from the SCM's, so retuning a coefficient does not
    # reshuffle every invoice id in the corpus.
    rng = random.Random((seed if seed is not None else read_seed()) ^ 0x5F5F)

    written: list[Path] = []
    for relative, header, rows in _tables(world, rng):
        written.append(_write_csv(out / relative, header, rows))

    answer_sheet = out / "ground_truth.json"
    answer_sheet.parent.mkdir(parents=True, exist_ok=True)
    answer_sheet.write_text(
        json.dumps(world.answer_sheet(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    written.append(answer_sheet)

    manifest = {
        str(path.relative_to(out)): _digest(path) for path in sorted(written, key=str)
    }
    (out / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


# ── The tables ────────────────────────────────────────────────────────────────


def _tables(
    world: World, rng: random.Random
) -> Iterator[tuple[str, Sequence[str], list[list[Any]]]]:
    subscriptions = {
        a.account_id: rng.sample(PRODUCTS, rng.randint(3, 6)) for a in world.accounts
    }
    # Usage is metered against a standing baseline per account and product, not
    # redrawn every month. Real consumption drifts; it does not triple and halve
    # at random, and a corpus where it does buries a real movement in noise.
    # The line count and the discount are contractual, drawn once per account
    # and product: a customer's negotiated discount does not change every month,
    # and neither does the shape of their bill.
    usage = {
        (a.account_id, product): _UsageTerms(
            lines=rng.randint(*USAGE_LINES),
            qty=rng.randint(6, 34),
            price=round(rng.uniform(900, 3_200), 2),
            recurring_discount=round(rng.uniform(0.0, 0.06), 4),
            usage_discount=round(rng.uniform(0.0, 0.10), 4),
        )
        for a in world.accounts
        for product in subscriptions[a.account_id]
    }
    invoices, lines = _billing(world, rng, subscriptions, usage)
    opportunities = _opportunities(world, rng)
    authored = corpus.load_authored()
    tickets = _tickets(world, rng, authored)

    yield "raw/crm/account.csv", (
        "account_id", "account_name", "region", "segment", "industry",
        "owner_user_id", "first_contract_date", "csm_user_id", "_synced_at",
    ), _accounts(world, rng)

    yield "raw/crm/opportunity.csv", (
        "opp_id", "account_id", "type", "stage", "arr_value", "created_at",
        "close_date", "closed_won", "lost_reason_code", "owner_user_id", "_synced_at",
    ), opportunities

    yield "raw/crm/opportunity_note.csv", (
        "note_id", "opp_id", "account_id", "author_user_id", "created_at", "body_text",
    ), _opportunity_notes(world, rng, opportunities, authored)

    yield "raw/crm/renewal.csv", (
        "renewal_id", "account_id", "arr_up_for_renewal", "arr_renewed",
        "due_date", "closed_date", "outcome",
    ), _renewals(world)

    yield "raw/billing/price_book.csv", (
        "product_id", "segment", "effective_from", "effective_to", "list_price",
    ), _price_book(rng)

    yield "raw/billing/invoice.csv", (
        "invoice_id", "account_id", "invoice_date", "currency",
        "amount_gross", "amount_net", "_ingested_at",
    ), invoices

    yield "raw/billing/invoice_line.csv", (
        "invoice_id", "line_no", "invoice_date", "account_id", "product_id", "region",
        "qty", "unit_price", "amount_gross", "discount", "amount_net", "currency",
        "is_recurring", "contract_start", "contract_end", "_ingested_at",
    ), lines

    yield "raw/billing/credit_note.csv", (
        "credit_id", "credit_date", "invoice_id", "account_id", "amount",
        "reason_code", "_ingested_at",
    ), _credit_notes(world, rng, invoices)

    yield "raw/product_ops/ticket.csv", (
        "ticket_id", "account_id", "priority", "category", "created_at",
        "first_response_at", "resolved_at", "status", "subject", "body_text",
    ), tickets

    yield "raw/product_ops/ticket_message.csv", (
        "message_id", "ticket_id", "author_user_id", "created_at", "body_text",
    ), _ticket_messages(rng, tickets)

    yield "raw/product_ops/news_item.csv", (
        "news_id", "published_at", "source", "competitor", "region",
        "headline", "body_text",
    ), _news_items(rng, authored)

    yield "raw/product_ops/deploy_event.csv", (
        "deploy_id", "service", "deployed_at", "version",
        "change_summary", "affected_regions",
    ), _deploys(rng)

    yield "raw/product_ops/incident.csv", (
        "incident_id", "service", "started_at", "resolved_at", "severity",
        "affected_accounts",
    ), _incidents(world, rng)


def _accounts(world: World, rng: random.Random) -> list[list[Any]]:
    """`_synced_at` is the **batch** that last carried the row, not the day the
    customer signed. Stamping it from `first_contract_date` made every account
    look 3.5 years stale, which would have failed §15 S1's freshness check on a
    source that is in fact refreshed nightly."""
    return [
        [
            a.account_id, a.account_name, a.region, a.segment, a.industry,
            f"U-{rng.randint(100, 199)}", a.first_contract_date.isoformat(),
            f"U-{rng.randint(200, 299)}", _batch_synced(rng),
        ]
        for a in world.accounts
    ]


def _price_book(rng: random.Random) -> list[list[Any]]:
    """§24's pricing decoy lives here: on 2026-03-01 every enterprise list price
    steps up. It is a real, visible, plausible cause — and it hit 41 accounts
    where the effect hit two, which is what Locality will refute it on."""
    rows: list[list[Any]] = []
    for product in PRODUCTS:
        for segment in ("enterprise", "mid_market", "smb"):
            base = round(rng.uniform(180_000, 640_000), -3)
            rows.append([product, segment, SPAN_START.isoformat(),
                         (PRICING_ONSET - timedelta(days=1)).isoformat(), f"{base:.2f}"])
            uplift = base * (1 + PRICING_UPLIFT) if segment == "enterprise" else base
            rows.append([product, segment, PRICING_ONSET.isoformat(), "", f"{uplift:.2f}"])
    return rows


def _billing(
    world: World,
    rng: random.Random,
    subscriptions: dict[str, list[str]],
    usage: dict[tuple[str, str], _UsageTerms],
) -> tuple[list[list[Any]], list[list[Any]]]:
    """One invoice per account per month; recurring lines carry the subscription,
    usage lines carry the volume. Note the account id: billing writes `A0001`
    where CRM writes `ACC-0001`, and nothing here reconciles them — that is
    Stage 0's job, and 0.8's alias map is what does it."""
    invoices: list[list[Any]] = []
    lines: list[list[Any]] = []
    counter = 0

    for month in month_range(SPAN_START, SPAN_END):
        for account in world.accounts:
            invoice_date = min(_month_end(month), SPAN_END)
            share = world.recurring_share(account, invoice_date)
            if share == 0.0:
                continue

            counter += 1
            invoice_id = f"INV-{counter:07d}"
            ingested = _ingested(invoice_date, rng, low=4, high=26)
            products = subscriptions[account.account_id]
            monthly = account.arr / 12.0
            volume = (
                seasonal_factor(invoice_date)
                * world.demand_shock(account.region_at(invoice_date), month)
                * rng.uniform(0.94, 1.06)
            )
            gross = net = 0.0
            line_no = 0

            for product in products:
                terms = usage[(account.account_id, product)]
                unit = round(monthly * share / len(products), 2)
                if unit > 0:
                    line_no += 1
                    discount = round(unit * terms.recurring_discount, 2)
                    lines.append(_line(
                        invoice_id, line_no, invoice_date, account, product, 1, unit,
                        discount, True, ingested,
                    ))
                    gross += unit
                    net += unit - discount

                for _ in range(terms.lines):
                    line_no += 1
                    qty = max(1, round(terms.qty * volume * rng.uniform(0.96, 1.04)))
                    price = round(terms.price * rng.uniform(0.98, 1.02), 2)
                    amount = round(qty * price, 2)
                    discount = round(amount * terms.usage_discount, 2)
                    lines.append(_line(
                        invoice_id, line_no, invoice_date, account, product, qty, price,
                        discount, False, ingested,
                    ))
                    gross += amount
                    net += amount - discount

            invoices.append([
                invoice_id, account.billing_id, invoice_date.isoformat(), "INR",
                f"{gross:.2f}", f"{net:.2f}", ingested,
            ])
    return invoices, lines


def _line(
    invoice_id: str, line_no: int, when: date, account: Account, product: str,
    qty: int, unit: float, discount: float, recurring: bool, ingested: str,
) -> list[Any]:
    amount = round(qty * unit, 2)
    return [
        invoice_id, line_no, when.isoformat(), account.billing_id, product,
        account.region_at(when),
        qty, f"{unit:.2f}", f"{amount:.2f}", f"{discount:.2f}", f"{amount - discount:.2f}",
        "INR", int(recurring), account.first_contract_date.isoformat(),
        _safe_month_day(date(when.year + 1, when.month, 1), 28).isoformat(), ingested,
    ]


def _credit_notes(
    world: World, rng: random.Random, invoices: list[list[Any]]
) -> list[list[Any]]:
    """A thin, ordinary trickle, plus scenario D.

    §25 D is a single credit note worth ~71% of a movement — an alarming drop
    that is not real, closed at Verify on the artefact check with zero model
    calls. It is written last so that its credit id is stable no matter how the
    ordinary trickle lands.
    """
    rows: list[list[Any]] = []
    for index, invoice in enumerate(invoices):
        if rng.random() > 0.012:
            continue
        when = date.fromisoformat(str(invoice[2])) + timedelta(days=rng.randint(3, 25))
        if when > SPAN_END:
            continue
        rows.append([
            f"CN-{index + 1:06d}", when.isoformat(), invoice[0], invoice[1],
            f"{float(invoice[5]) * rng.uniform(0.02, 0.18):.2f}",
            rng.choice(("service_credit", "billing_error", "goodwill")),
            _ingested(when, rng, low=4, high=26),
        ])

    rows.append(_refund_batch(world, rng, invoices))
    return rows


def _refund_batch(
    world: World, rng: random.Random, invoices: list[list[Any]]
) -> list[Any]:
    """Scenario D. One credit note against the refund month's invoice for the
    largest account in the refund region."""
    account = world.refund_batch_account()
    month_end = _month_end(REFUND_MONTH).isoformat()
    invoice = next(
        row for row in invoices if row[1] == account.billing_id and row[2] == month_end
    )
    when = _safe_month_day(REFUND_MONTH, 22)
    return [
        "CN-REFUND-01", when.isoformat(), invoice[0], account.billing_id,
        f"{REFUND_AMOUNT:.2f}", REFUND_REASON, _ingested(when, rng, low=4, high=26),
    ]


def _opportunities(world: World, rng: random.Random) -> list[list[Any]]:
    """Renewals, expansions and new business, as sales recorded them.

    Expansions and renewals are *rendered* here, not decided here — `scm.py`
    owns both, because both are consequences of the injected events. What this
    function adds is the shape of the CRM record around them.

    The lost-reason codes carry scenario A's other half. On the East footprint
    the fields are **populated and none names a competitor** — evidence against
    the competitor hypothesis. Competitor codes exist and are used, but only in
    APAC once the promotion starts. §25 turns on that distinction: checked
    absent refutes, uncheckable abstains.
    """
    rows: list[list[Any]] = []
    counter = 0

    for expansion in world.expansions:
        counter += 1
        rows.append([
            f"OPP-{counter:06d}", expansion.account_id, "expansion",
            "closed_won" if expansion.won else "closed_lost",
            f"{expansion.arr_delta:.2f}" if expansion.won else
            f"{world.by_id[expansion.account_id].arr * 0.03:.2f}",
            expansion.created.isoformat(), expansion.close_date.isoformat(),
            int(expansion.won), expansion.lost_reason,
            f"U-{rng.randint(100, 199)}", _synced(expansion.close_date, rng),
        ])

    for renewal in world.renewals:
        counter += 1
        won = renewal.outcome == "renewed"
        rows.append([
            f"OPP-{counter:06d}", renewal.account_id, "renewal",
            "closed_won" if won else "closed_lost", f"{renewal.arr_up_for_renewal:.2f}",
            (renewal.due_date - timedelta(days=60)).isoformat(),
            renewal.closed_date.isoformat(), int(won),
            "" if won else rng.choice(LOST_REASONS),
            f"U-{rng.randint(100, 199)}", _synced(renewal.closed_date, rng),
        ])

    for account in world.accounts:
        for month in month_range(max(SPAN_START, account.first_contract_date), SPAN_END):
            if rng.random() > 0.06:
                continue
            counter += 1
            created = _safe_month_day(month, rng.randint(1, 26))
            close = created + timedelta(days=rng.randint(20, 70))
            if close > SPAN_END:
                continue
            won = rng.random() < 0.32
            rows.append([
                f"OPP-{counter:06d}", account.account_id, "new",
                "closed_won" if won else "closed_lost",
                f"{account.arr * rng.uniform(0.02, 0.08):.2f}", created.isoformat(),
                close.isoformat(), int(won), "" if won else rng.choice(LOST_REASONS),
                f"U-{rng.randint(100, 199)}", _synced(close, rng),
            ])

    # §25 B: one explicit deal a month, per footprint account — won until the
    # competitor arrives, lost with no reason recorded after. Injected
    # outright rather than nudging the trickle above, the same way scenario
    # D's refund batch is its own row rather than a thumb on an ordinary one.
    #
    # Its own stream, not the shared `rng` above. Drawing from the shared
    # stream here shifts every rng call after it in generation order —
    # `_credit_notes`' ordinary trickle among them, which moved East's
    # already-measured April figures with no causal link between the two at
    # all. This is the exact failure `World.stream()` exists to prevent for
    # `scm.py`'s draws; `generator.py`'s rendering stream needed the same
    # discipline once a second consumer was added to it.
    b_rng = random.Random(f"{world.seed}:scenario_b")
    for index, account in enumerate(world.scenario_b_accounts()):
        # Half the accounts lose their deal at the onset, half a month later
        # — two consecutive periods each down by roughly half, rather than
        # one cliff STL's trend catches up with by the second period.
        account_onset = (
            SCENARIO_B_ONSET if index % 2 == 0 else _add_month(SCENARIO_B_ONSET)
        )
        for month in month_range(max(SPAN_START, account.first_contract_date), SPAN_END):
            counter += 1
            created = _safe_month_day(month, 3)
            close = _safe_month_day(month, 24)  # same month as `created` — never spills over
            if close > SPAN_END:
                continue
            # `new_business_arr` groups by close_date, so won/lost has to key
            # off it too — keying off `month` let one deal's actual close
            # date drift a month past its onset side, contaminating the
            # first post-onset period with a win that should have counted
            # against the last pre-onset one.
            won = close < account_onset
            rows.append([
                f"{SCENARIO_B_ID_PREFIX}{counter:06d}", account.account_id, "new",
                "closed_won" if won else "closed_lost",
                f"{SCENARIO_B_DEAL_VALUE:.2f}", created.isoformat(), close.isoformat(),
                int(won), "", f"U-{b_rng.randint(100, 199)}", _synced(close, b_rng),
            ])
            if not won:
                # The account keeps buying something — just not the deal the
                # competitor took. A smaller, ordinary, *won* line alongside
                # the lost one, so a post-onset month is still several
                # distinct records rather than one record standing for the
                # whole movement (§15 S1's artefact check, correctly, would
                # otherwise refuse this the same way it refuses scenario D).
                counter += 1
                rows.append([
                    f"{SCENARIO_B_ID_PREFIX}{counter:06d}", account.account_id, "new",
                    "closed_won", f"{SCENARIO_B_DEAL_VALUE * 0.18:.2f}",
                    created.isoformat(), close.isoformat(), 1, "",
                    f"U-{b_rng.randint(100, 199)}", _synced(close, b_rng),
                ])

    rows.sort(key=lambda r: (str(r[6]), str(r[0])))
    return rows


def _renewals(world: World) -> list[list[Any]]:
    return [
        [
            f"REN-{index + 1:05d}", r.account_id, f"{r.arr_up_for_renewal:.2f}",
            f"{r.arr_renewed:.2f}", r.due_date.isoformat(), r.closed_date.isoformat(),
            r.outcome,
        ]
        for index, r in enumerate(world.renewals)
    ]


def _tickets(
    world: World, rng: random.Random, authored: list[corpus.Authored]
) -> list[list[Any]]:
    """Text is written onto the rows the SCM already decided existed, never
    alongside them — so the ticket *count* the causal model produced and the
    ticket *documents* retrieval reads can never disagree.

    Authored tickets **replace** a generated body rather than adding a row, for
    the same reason. A hand-written ticket that could not be attached to a real
    one raises: a signal document nobody can retrieve is worse than none, because
    it looks like coverage.
    """
    rows: list[list[Any]] = []
    counter = 0
    # §25 C: which P1 tickets take a supply delay's hit. Modifies an existing
    # draw's result rather than adding one, so it cannot shift any later rng
    # call's outcome — the same class of bug scenario B's first attempt hit.
    scenario_c_accounts = {a.account_id for a in world.scenario_c_accounts()}
    for account in world.accounts:
        for day in day_range(OPS_START, OPS_END):
            count = world.daily_tickets.get((account.account_id, day), 0)
            for _ in range(count):
                counter += 1
                category = (
                    "integration"
                    if world.is_treated(account) and day >= INTEGRATION_ONSET
                    and rng.random() < 0.7
                    else corpus.category(rng)
                )
                priority = rng.choices(("P1", "P2", "P3", "P4"), (0.08, 0.22, 0.45, 0.25))[0]
                # Round the clock, weighted to business hours. Confining tickets
                # to 08:00-20:00 left a ≤15-minute source looking ten hours
                # stale every night, which §15 S1 would read as a broken feed.
                minute = (
                    rng.randint(8 * 60, 20 * 60)
                    if rng.random() < 0.82
                    else rng.randint(0, 24 * 60 - 1)
                )
                created = datetime.combine(day, datetime.min.time()) + timedelta(
                    minutes=min(minute, 24 * 60 - 1)
                )
                if created > AS_OF:
                    continue  # the stream reaches the present, not past it
                responded = created + timedelta(minutes=rng.randint(5, 240))
                hours = rng.uniform(2, 96) * (2.1 if priority == "P1" else 1.0)
                if (
                    priority == "P1"
                    and account.account_id in scenario_c_accounts
                    and SCENARIO_C_START <= day < SCENARIO_C_END
                ):
                    hours *= SCENARIO_C_MULTIPLIER
                resolved = responded + timedelta(hours=hours)
                rows.append([
                    f"TKT-{counter:06d}", account.account_id, priority, category,
                    created.isoformat(timespec="seconds"),
                    responded.isoformat(timespec="seconds"),
                    resolved.isoformat(timespec="seconds") if resolved <= AS_OF else "",
                    "resolved" if resolved <= AS_OF else "open",
                    corpus.subject(rng, category),
                    corpus.ticket_body(rng, category, account.account_name),
                ])

    _apply_authored_tickets(rows, authored)
    return rows


def _apply_authored_tickets(rows: list[list[Any]], authored: list[corpus.Authored]) -> None:
    by_account: dict[str, list[int]] = {}
    for index, row in enumerate(rows):
        by_account.setdefault(str(row[1]), []).append(index)

    for document in authored:
        if document.table != "product_ops.ticket":
            continue
        account = document.account
        wanted = date.fromisoformat(document.date)
        candidates = [
            index
            for index in by_account.get(account or "", [])
            if abs((datetime.fromisoformat(str(rows[index][4])).date() - wanted).days) <= 3
            and str(rows[index][9]) != ""
        ]
        if not candidates:
            raise ValueError(
                f"authored ticket {document.doc_id!r} names {account} on {wanted}, and no "
                "generated ticket sits within three days of it — the document would be "
                "committed but unretrievable"
            )
        index = candidates[len(candidates) // 2]
        rows[index][3] = document.get("category", str(rows[index][3]))
        rows[index][8] = document.doc_id.replace("-", " ").capitalize()
        rows[index][9] = document.body


def _ticket_messages(rng: random.Random, tickets: list[list[Any]]) -> list[list[Any]]:
    """§22's `ticket_message`. Only P1 tickets carry a thread: those are the ones
    somebody escalated, and generating a conversation for forty thousand
    password resets would triple the corpus to say nothing."""
    rows: list[list[Any]] = []
    for ticket in tickets:
        if ticket[2] != "P1":
            continue
        created = datetime.fromisoformat(str(ticket[5]))
        for turn in range(rng.randint(1, 3)):
            when = created + timedelta(hours=rng.uniform(1, 30) * (turn + 1))
            if when > AS_OF:
                break
            rows.append([
                f"MSG-{len(rows) + 1:06d}", ticket[0], f"U-{rng.randint(300, 349)}",
                when.isoformat(timespec="seconds"), corpus.ticket_message(rng),
            ])
    return rows


def _opportunity_notes(
    world: World,
    rng: random.Random,
    opportunities: list[list[Any]],
    authored: list[corpus.Authored],
) -> list[list[Any]]:
    """§22's `opportunity_note`, ~9k of them. The ordinary ones say nothing;
    §24's point is that a needle in a stack of needles proves nothing."""
    rows: list[list[Any]] = []
    by_account: dict[str, list[list[Any]]] = {}
    for opportunity in opportunities:
        by_account.setdefault(str(opportunity[1]), []).append(opportunity)
        # §25 B's injected rows carry a distinct id and draw no notes here —
        # they have their own stream (generator.py) precisely so a change to
        # how many of them exist cannot shift this loop's draw count for
        # every *organic* row that follows, which is what moved scenario A's
        # already-measured figures before this guard existed.
        if str(opportunity[0]).startswith(SCENARIO_B_ID_PREFIX):
            continue
        for _ in range(rng.randint(2, 6)):
            closed = date.fromisoformat(str(opportunity[6]))
            when = closed - timedelta(days=rng.randint(0, 55))
            if when < SPAN_START:
                continue
            rows.append([
                f"NOTE-{len(rows) + 1:06d}", opportunity[0], opportunity[1],
                f"U-{rng.randint(100, 199)}",
                _ingested(when, rng, low=8, high=20), corpus.note_body(rng),
            ])

    for document in authored:
        if document.table != "crm.opportunity_note":
            continue
        account = document.account or ""
        if account not in world.by_id:
            raise ValueError(
                f"authored note {document.doc_id!r} names account {account!r}, which is "
                "not in the corpus"
            )
        when = date.fromisoformat(document.date)
        nearest = min(
            by_account.get(account, []),
            key=lambda o: abs((date.fromisoformat(str(o[6])) - when).days),
            default=None,
        )
        rows.append([
            document.doc_id, nearest[0] if nearest else "", account, "U-101",
            datetime.combine(when, datetime.min.time()).isoformat(timespec="seconds"),
            document.body,
        ])
    return rows


def _news_items(rng: random.Random, authored: list[corpus.Authored]) -> list[list[Any]]:
    """§22's 200 news items. Industry noise, plus the authored competitor
    coverage that scenario A's Timing test refutes the decoy on."""
    rows: list[list[Any]] = []
    for index, month in enumerate(month_range(OPS_START, OPS_END)):
        for _ in range(rng.randint(20, 28)):
            when = _safe_month_day(month, rng.randint(1, 28))
            if when > OPS_END:
                continue
            source, headline, body = corpus.news(rng)
            rows.append([
                f"NEWS-{len(rows) + 1:05d}",
                datetime.combine(when, datetime.min.time()).isoformat(timespec="seconds"),
                source, "", "", headline, body,
            ])
        del index

    for document in authored:
        if document.table != "product_ops.news_item":
            continue
        when = date.fromisoformat(document.date)
        rows.append([
            document.doc_id,
            datetime.combine(when, datetime.min.time()).isoformat(timespec="seconds"),
            "Sector Weekly", document.get("competitor"), document.get("region"),
            document.get("headline"), document.body,
        ])
    return rows


def _deploys(rng: random.Random) -> list[list[Any]]:
    rows: list[list[Any]] = []
    for index, day in enumerate(day_range(OPS_START, OPS_END)):
        for _ in range(rng.randint(2, 5)):
            when = datetime.combine(day, datetime.min.time()) + timedelta(
                minutes=rng.randint(0, 1439)
            )
            if when > AS_OF:
                continue
            rows.append([
                f"DEP-{len(rows) + 1:05d}", rng.choice(SERVICES),
                when.isoformat(timespec="seconds"),
                f"{2 + index // 120}.{index % 120}.{rng.randint(0, 9)}",
                rng.choice(("schema migration", "hotfix", "feature flag", "dependency bump")),
                "|".join(rng.sample(("East", "West", "North", "APAC"), rng.randint(1, 4))),
            ])
    return rows


def _incidents(world: World, rng: random.Random) -> list[list[Any]]:
    rows: list[list[Any]] = []
    for month in month_range(OPS_START, OPS_END):
        for _ in range(rng.randint(3, 8)):
            started = datetime.combine(
                _safe_month_day(month, rng.randint(1, 28)), datetime.min.time()
            ) + timedelta(minutes=rng.randint(0, 1439))
            if started > AS_OF:
                continue
            affected = rng.sample([a.account_id for a in world.accounts], rng.randint(1, 9))
            rows.append([
                f"INC-{len(rows) + 1:05d}", rng.choice(SERVICES),
                started.isoformat(timespec="seconds"),
                (started + timedelta(hours=rng.uniform(0.5, 30))).isoformat(timespec="seconds"),
                rng.choice(SEVERITIES), "|".join(affected),
            ])
    return rows


# ── Writing ───────────────────────────────────────────────────────────────────


def _write_csv(path: Path, header: Sequence[str], rows: list[list[Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)
    return path


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _ingested(when: date, rng: random.Random, low: int, high: int) -> str:
    """Late arrival, bounded by the source's SLA. Derived from the record's own
    date — never from the wall clock, or the demo would rot overnight."""
    return (
        datetime.combine(when, datetime.min.time())
        + timedelta(hours=rng.uniform(low, high))
    ).isoformat(timespec="seconds")


def _synced(when: date, rng: random.Random) -> str:
    return _ingested(when, rng, low=12, high=24)


def _batch_synced(rng: random.Random) -> str:
    """CRM's nightly batch: the run that last carried the whole account table.
    Rows that never change still arrive in it, which is exactly why the account
    table's watermark is recent even though nobody edited a row."""
    return (AS_OF - timedelta(hours=rng.uniform(5.0, 9.0))).isoformat(timespec="seconds")


def _month_end(month: date) -> date:
    """The last day of `month` — where a billing close actually lands. Invoicing
    on the 28th put the final batch 52h behind `AS_OF` against a 26h SLA."""
    following = date(month.year + month.month // 12, month.month % 12 + 1, 1)
    return following - timedelta(days=1)


def _safe_month_day(month: date, day: int) -> date:
    return date(month.year, month.month, min(day, 28))


def _add_month(day: date) -> date:
    return date(day.year + day.month // 12, day.month % 12 + 1, day.day)


def main() -> None:
    root = Path(__file__).resolve().parents[3]
    manifest = generate(root / "data")
    print(f"wrote {len(manifest)} files under data/")


if __name__ == "__main__":
    main()
