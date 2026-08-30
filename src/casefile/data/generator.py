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

from casefile.data.scm import (
    AS_OF,
    INTEGRATION_ONSET,
    LOST_REASONS,
    OPS_START,
    PRICING_ONSET,
    PRICING_UPLIFT,
    PRODUCTS,
    SPAN_END,
    SPAN_START,
    Account,
    World,
    day_range,
    month_range,
    read_seed,
    seasonal_factor,
)

TICKET_CATEGORIES = ("integration", "billing_query", "access", "performance", "how_to")
SERVICES = ("sync-gateway", "billing-core", "insight-api", "edge-router")
SEVERITIES = ("sev1", "sev2", "sev3")

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

    yield "raw/crm/account.csv", (
        "account_id", "account_name", "region", "segment", "industry",
        "owner_user_id", "first_contract_date", "csm_user_id", "_synced_at",
    ), _accounts(world, rng)

    yield "raw/crm/opportunity.csv", (
        "opp_id", "account_id", "type", "stage", "arr_value", "created_at",
        "close_date", "closed_won", "lost_reason_code", "owner_user_id", "_synced_at",
    ), _opportunities(world, rng)

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
    ), _tickets(world, rng)

    yield "raw/product_ops/deploy_event.csv", (
        "deploy_id", "service", "deployed_at", "version",
        "change_summary", "affected_regions",
    ), _deploys(rng)

    yield "raw/product_ops/incident.csv", (
        "incident_id", "service", "started_at", "resolved_at", "severity",
        "affected_accounts",
    ), _incidents(world, rng)


def _accounts(world: World, rng: random.Random) -> list[list[Any]]:
    return [
        [
            a.account_id, a.account_name, a.region, a.segment, a.industry,
            f"U-{rng.randint(100, 199)}", a.first_contract_date.isoformat(),
            f"U-{rng.randint(200, 299)}", _synced(a.first_contract_date, rng),
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
            invoice_date = min(_safe_month_day(month, 28), SPAN_END)
            share = world.recurring_share(account, invoice_date)
            if share == 0.0:
                continue

            counter += 1
            invoice_id = f"INV-{counter:07d}"
            ingested = _ingested(invoice_date, rng, low=4, high=26)
            products = subscriptions[account.account_id]
            monthly = account.arr / 12.0
            volume = seasonal_factor(invoice_date) * rng.uniform(0.94, 1.06)
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
        invoice_id, line_no, when.isoformat(), account.billing_id, product, account.region,
        qty, f"{unit:.2f}", f"{amount:.2f}", f"{discount:.2f}", f"{amount - discount:.2f}",
        "INR", int(recurring), account.first_contract_date.isoformat(),
        _safe_month_day(date(when.year + 1, when.month, 1), 28).isoformat(), ingested,
    ]


def _credit_notes(
    world: World, rng: random.Random, invoices: list[list[Any]]
) -> list[list[Any]]:
    """A thin, ordinary trickle. Scenario D's refund batch — one credit note
    worth 71% of a movement — is a separate scenario and arrives with it."""
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
    return rows


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


def _tickets(world: World, rng: random.Random) -> list[list[Any]]:
    """`body_text` is left empty on purpose. Ladder step 1.5 fills text into
    these rows, so the ticket *count* the SCM produced and the ticket
    *documents* retrieval reads can never disagree."""
    rows: list[list[Any]] = []
    counter = 0
    for account in world.accounts:
        for day in day_range(OPS_START, SPAN_END):
            count = world.daily_tickets.get((account.account_id, day), 0)
            for _ in range(count):
                counter += 1
                category = (
                    "integration"
                    if world.is_treated(account) and day >= INTEGRATION_ONSET
                    and rng.random() < 0.7
                    else rng.choice(TICKET_CATEGORIES)
                )
                priority = rng.choices(("P1", "P2", "P3", "P4"), (0.08, 0.22, 0.45, 0.25))[0]
                created = datetime.combine(day, datetime.min.time()) + timedelta(
                    minutes=rng.randint(8 * 60, 20 * 60)
                )
                responded = created + timedelta(minutes=rng.randint(5, 240))
                hours = rng.uniform(2, 96) * (2.1 if priority == "P1" else 1.0)
                resolved = responded + timedelta(hours=hours)
                rows.append([
                    f"TKT-{counter:06d}", account.account_id, priority, category,
                    created.isoformat(timespec="seconds"),
                    responded.isoformat(timespec="seconds"),
                    resolved.isoformat(timespec="seconds") if resolved <= AS_OF else "",
                    "resolved" if resolved <= AS_OF else "open",
                    f"{category.replace('_', ' ').title()} issue on {account.account_name}",
                    "",
                ])
    return rows


def _deploys(rng: random.Random) -> list[list[Any]]:
    rows: list[list[Any]] = []
    for index, day in enumerate(day_range(OPS_START, SPAN_END)):
        for _ in range(rng.randint(2, 5)):
            when = datetime.combine(day, datetime.min.time()) + timedelta(
                minutes=rng.randint(0, 1439)
            )
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
    for month in month_range(OPS_START, SPAN_END):
        for _ in range(rng.randint(3, 8)):
            started = datetime.combine(
                _safe_month_day(month, rng.randint(1, 28)), datetime.min.time()
            ) + timedelta(minutes=rng.randint(0, 1439))
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


def _safe_month_day(month: date, day: int) -> date:
    return date(month.year, month.month, min(day, 28))


def main() -> None:
    root = Path(__file__).resolve().parents[3]
    manifest = generate(root / "data")
    print(f"wrote {len(manifest)} files under data/")


if __name__ == "__main__":
    main()
