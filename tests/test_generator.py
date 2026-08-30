"""Ladder step 0.7 — the generator, and scenario A on disk.

The step's verify command from §44:

    "make data twice → byte-identical; the East -8% is visible in the tables"

Both halves are here. Everything else defends a property some later gate needs:
if the ticket spike is not in the data, 2.4's Timing test has nothing to find;
if the pricing decoy touched two accounts instead of 41, Locality cannot refute
it; if the lost-reason fields are empty rather than populated-and-innocent,
§25's checked-absent / uncheckable distinction has nothing behind it.

These assert **shape**, never the fixture's hand-written rupees. The fixtures are
the §10 story; the generator is a causal model, and the two are allowed to
disagree on the last digit.
"""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import duckdb
import pytest

from casefile.contract import load, load_all
from casefile.data.generator import generate
from casefile.data.scm import (
    AS_OF,
    COMPETITOR_LOST_REASONS,
    COMPETITOR_ONSET,
    COMPETITOR_REGION,
    INTEGRATION_ONSET,
    N_ENTERPRISE,
    OPS_START,
    SCENARIO_B_COUNT,
    SCENARIO_B_REGION,
    SPAN_END,
    SPAN_START,
    TREATED,
)
from casefile.engine.decompose import decompose
from casefile.models import KPIContract

ROOT = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.gate0


@pytest.fixture(scope="module")
def data(generated: Path) -> Path:
    """The session-wide corpus from `conftest.py` — built once, not per module."""
    return generated


@pytest.fixture(scope="module")
def contracts() -> dict[str, KPIContract]:
    return load_all(ROOT / "contracts")


@pytest.fixture(scope="module")
def con(warehouse: Path) -> duckdb.DuckDBPyConnection:
    connection = duckdb.connect(str(warehouse), read_only=True)
    yield connection
    connection.close()


def rows(data: Path, name: str) -> list[dict[str, str]]:
    with (data / "raw" / name).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def truth(data: Path) -> dict[str, Any]:
    return json.loads((data / "ground_truth.json").read_text(encoding="utf-8"))


def east_by_month(data: Path) -> tuple[Counter[str], defaultdict[str, Counter[str]]]:
    total: Counter[str] = Counter()
    by_account: defaultdict[str, Counter[str]] = defaultdict(Counter)
    for line in rows(data, "billing/invoice_line.csv"):
        if line["region"] != "East":
            continue
        month = line["invoice_date"][:7]
        total[month] += float(line["amount_net"])
        by_account[month][line["account_id"]] += float(line["amount_net"])
    return total, by_account


# ── make data twice → byte-identical ──────────────────────────────────────────


def test_two_runs_produce_identical_bytes(tmp_path: Path) -> None:
    """The ladder's first verify. Every later gate runs against this data, so a
    generator that drifts between runs makes every one of them unfalsifiable."""
    first = generate(tmp_path / "one")
    second = generate(tmp_path / "two")

    assert first == second
    assert len(first) == 14, "thirteen tables and the sealed answer sheet"


def test_the_manifest_covers_every_file_that_was_written(data: Path) -> None:
    manifest = json.loads((data / "manifest.json").read_text(encoding="utf-8"))
    written = {
        str(p.relative_to(data))
        for p in data.rglob("*")
        if p.is_file() and p.name != "manifest.json"
    }
    assert set(manifest) == written


def test_nothing_in_the_corpus_was_stamped_with_the_wall_clock(data: Path) -> None:
    """`AS_OF` is the simulated present. If any timestamp came from the real
    clock, a recorded demo would start reporting stale data tomorrow."""
    latest = max(line["_ingested_at"] for line in rows(data, "billing/invoice.csv"))
    assert datetime.fromisoformat(latest) <= AS_OF


# ── The East −8% is visible in the tables ─────────────────────────────────────


def test_the_east_decline_is_visible_and_is_about_eight_percent(data: Path) -> None:
    """The ladder's second verify. Tolerance is half a point — the figure is a
    consequence of the model, not a constant someone typed in."""
    total, _ = east_by_month(data)
    march, april = total["2026-03"], total["2026-04"]
    relative = (april - march) / march

    # A point either side. Tighter than this makes an honest simulation brittle:
    # the figure is a consequence of the model, and a coefficient nudged
    # anywhere upstream moves it. A point still excludes the broken states —
    # the freshness bug briefly produced -5.12% and this would have caught it.
    assert relative == pytest.approx(-0.08, abs=0.01), f"East moved {relative:+.4f}"
    assert april < march


def test_the_movement_concentrates_in_the_two_treated_accounts(data: Path) -> None:
    """§35.2's gate: K(2) >= 0.85. Below that, Stage 2 has not actually narrowed
    anything and there is no footprint to scope retrieval to."""
    _, by_account = east_by_month(data)
    deltas = {
        account: by_account["2026-04"][account] - by_account["2026-03"][account]
        for account in set(by_account["2026-03"]) | set(by_account["2026-04"])
    }
    ranked = sorted(deltas.items(), key=lambda kv: abs(kv[1]), reverse=True)
    total = sum(abs(v) for v in deltas.values())

    assert sum(abs(v) for _, v in ranked[:2]) / total >= 0.85

    names = {a["account_id"]: a["account_name"] for a in rows(data, "crm/account.csv")}
    top_two = {names[f"ACC-{account[1:]}"] for account, _ in ranked[:2]}
    assert top_two == set(TREATED)


def test_the_tail_is_not_empty(data: Path) -> None:
    """Some ordinary variation has to survive, or Stage 2 is deciding between a
    signal and a vacuum and the demonstration proves nothing."""
    _, by_account = east_by_month(data)
    deltas = {
        account: by_account["2026-04"][account] - by_account["2026-03"][account]
        for account in set(by_account["2026-03"]) | set(by_account["2026-04"])
    }
    ranked = sorted(deltas.items(), key=lambda kv: abs(kv[1]), reverse=True)
    total = sum(abs(v) for v in deltas.values())

    assert sum(abs(v) for _, v in ranked[2:]) / total >= 0.02


# ── The causal chain is on disk, not merely asserted ──────────────────────────


def test_tickets_spike_on_the_treated_accounts_at_the_onset(data: Path) -> None:
    names = {a["account_id"]: a["account_name"] for a in rows(data, "crm/account.csv")}
    before: Counter[str] = Counter()
    after: Counter[str] = Counter()
    for ticket in rows(data, "product_ops/ticket.csv"):
        when = date.fromisoformat(ticket["created_at"][:10])
        bucket = after if when >= INTEGRATION_ONSET else before
        bucket[names[ticket["account_id"]]] += 1

    days_before = (INTEGRATION_ONSET - OPS_START).days
    days_after = (SPAN_END - INTEGRATION_ONSET).days + 1

    for name in TREATED:
        ratio = (after[name] / days_after) / (before[name] / days_before)
        assert ratio >= 3.0, f"{name} ticket rate rose only {ratio:.2f}x"


def test_untreated_accounts_show_no_ticket_spike(data: Path) -> None:
    """Without this the Locality test at 2.4 would have nothing to separate: a
    cause that shows up everywhere is not local to anything."""
    names = {a["account_id"]: a["account_name"] for a in rows(data, "crm/account.csv")}
    before: Counter[str] = Counter()
    after: Counter[str] = Counter()
    for ticket in rows(data, "product_ops/ticket.csv"):
        name = names[ticket["account_id"]]
        if name in TREATED:
            continue
        when = date.fromisoformat(ticket["created_at"][:10])
        (after if when >= INTEGRATION_ONSET else before)[name] += 1

    days_before = (INTEGRATION_ONSET - OPS_START).days
    days_after = (SPAN_END - INTEGRATION_ONSET).days + 1
    overall = (sum(after.values()) / days_after) / (sum(before.values()) / days_before)
    assert 0.85 <= overall <= 1.15, f"untreated ticket rate moved {overall:.2f}x"


def test_both_renewals_fall_inside_the_contract_maximum_lag(data: Path) -> None:
    """§10: the onset precedes each renewal decision by 21 and 23 days, inside
    `max_lag_days: 45`. Timing can only pass at 2.4 if that is true on disk."""
    contract = load(ROOT / "contracts" / "net_revenue.yaml")
    max_lag = next(d for d in contract.drivers if d.id == "integration_delay").max_lag_days
    names = {a["account_id"]: a["account_name"] for a in rows(data, "crm/account.csv")}

    lags = {
        names[r["account_id"]]: (date.fromisoformat(r["closed_date"]) - INTEGRATION_ONSET).days
        for r in rows(data, "crm/renewal.csv")
        if names[r["account_id"]] in TREATED and r["closed_date"].startswith("2026")
    }
    assert set(lags) == set(TREATED)
    for name, lag in lags.items():
        assert 0 < lag <= max_lag, f"{name} renewed {lag} days after onset"


def test_the_treated_accounts_failed_their_renewal(data: Path) -> None:
    names = {a["account_id"]: a["account_name"] for a in rows(data, "crm/account.csv")}
    outcomes = {
        names[r["account_id"]]: r["outcome"]
        for r in rows(data, "crm/renewal.csv")
        if names[r["account_id"]] in TREATED and r["closed_date"].startswith("2026")
    }
    assert set(outcomes.values()) <= {"churned", "downgraded"}


# ── The decoys are plausible, and each fails exactly one test ─────────────────


def test_the_price_rise_hit_every_enterprise_account(data: Path) -> None:
    """§24: it hit 41 accounts where the effect hit two. That ratio *is* the
    Locality refutation — a cause with a wider footprint than its effect."""
    book = rows(data, "billing/price_book.csv")
    stepped = {
        (r["product_id"], r["segment"])
        for r in book
        if r["effective_from"] == "2026-03-01" and r["segment"] == "enterprise"
    }
    assert len(stepped) == 6, "every product's enterprise price steps up"

    enterprise = [a for a in rows(data, "crm/account.csv") if a["segment"] == "enterprise"]
    assert len(enterprise) == N_ENTERPRISE


def test_the_competitor_promotion_is_apac_only_and_starts_after_the_decline(
    data: Path,
) -> None:
    """It fails Locality *and* Timing — §24's second decoy."""
    assert COMPETITOR_ONSET > INTEGRATION_ONSET

    regions = {a["account_id"]: a["region"] for a in rows(data, "crm/account.csv")}
    flagged = [
        opportunity
        for opportunity in rows(data, "crm/opportunity.csv")
        if opportunity["lost_reason_code"] in COMPETITOR_LOST_REASONS
    ]
    assert flagged, "the competitor decoy has to be findable somewhere"
    assert {regions[o["account_id"]] for o in flagged} == {COMPETITOR_REGION}
    for opportunity in flagged:
        assert date.fromisoformat(opportunity["close_date"]) >= COMPETITOR_ONSET


def test_the_east_lost_reasons_are_populated_and_name_no_competitor(data: Path) -> None:
    """ev-006, the counted absence: "0 of 12 populated lost-reason fields on the
    footprint accounts and their peers name a competitor".

    §25 rests on this. In scenario A the fields are *populated* and innocent —
    checked-absent, which refutes. In scenario B they are null and the sources
    have no coverage — uncheckable, which abstains. The difference has to exist
    in the data before any probe can report it.
    """
    east = {a["account_id"] for a in rows(data, "crm/account.csv") if a["region"] == "East"}
    window = [
        o
        for o in rows(data, "crm/opportunity.csv")
        if o["account_id"] in east
        and o["closed_won"] == "0"
        and "2026-03-01" <= o["close_date"] <= "2026-04-30"
    ]
    populated = [o for o in window if o["lost_reason_code"]]

    assert len(populated) >= 12, f"only {len(populated)} populated lost reasons in East"
    assert len(populated) == len(window), "a lost East opportunity always states why"
    assert not [o for o in populated if o["lost_reason_code"] in COMPETITOR_LOST_REASONS]


# ── §25 B: real, and unprovable from what the sources hold ───────────────────


def test_scenario_bs_lost_reasons_are_never_populated(data: Path) -> None:
    """The opposite of scenario A's ev-006: here the field is null on every
    lost deal, so evidence.py's probe finds nothing to check — uncheckable,
    not checked-absent."""
    lost = [
        o
        for o in rows(data, "crm/opportunity.csv")
        if o["opp_id"].startswith("OPPB-") and o["closed_won"] == "0"
    ]
    assert lost, "scenario B's injected deals produced no losses at all"
    assert not any(o["lost_reason_code"] for o in lost)


def test_scenario_b_accounts_keep_buying_something_after_the_loss(data: Path) -> None:
    """The lost deal isn't the account going silent — it still wins smaller,
    ordinary business. Only the one deal the competitor took disappears."""
    won = [
        o
        for o in rows(data, "crm/opportunity.csv")
        if o["opp_id"].startswith("OPPB-") and o["closed_won"] == "1"
    ]
    assert won


def test_scenario_b_never_moves_scenario_as_already_measured_figures(
    con: duckdb.DuckDBPyConnection, contracts: dict[str, KPIContract]
) -> None:
    """§25 B is on `new_business_arr`, keyed off `crm.opportunity` alone — it
    must not perturb East's net_revenue figures through the shared rendering
    RNG stream. This is the same failure class that once silently un-churned
    NORTHWIND: an unrelated addition reshuffling a later draw's outcome.

    Reads the metric's actual computed value, credit notes included — raw
    `invoice_line` alone would miss exactly the table this regression moves.
    """
    east = decompose(con, contracts["net_revenue"], "2026-04", {"region": "East"})
    assert east.total_delta == pytest.approx(-26_642_279, abs=100)
    assert east.concentration(2) == pytest.approx(0.9077, abs=0.001)


def test_the_answer_sheet_names_scenario_bs_true_driver_and_footprint(data: Path) -> None:
    sealed = truth(data)["scenarios"]["B"]
    assert sealed["scenario"] == "B"
    assert sealed["true_driver"] == "competitor_offer"
    assert sealed["dimensions"] == {"region": SCENARIO_B_REGION}
    assert len(sealed["footprint_accounts"]) == SCENARIO_B_COUNT
    assert sealed["expected_verdict"] == "undetermined"


# ── The sealed answer sheet ───────────────────────────────────────────────────


def test_the_answer_sheet_agrees_with_the_contract(data: Path) -> None:
    """The reason 0.6 comes before 0.7. A ground truth naming a driver the
    registry does not enumerate would make scenario A unrecoverable by
    construction, and the harness would be measuring nothing."""
    contract = load(ROOT / "contracts" / "net_revenue.yaml")
    known = {d.id for d in contract.drivers}
    sealed = truth(data)["scenarios"]["A"]

    assert sealed["true_driver"] in known
    assert {event["driver_id"] for event in sealed["events"]} <= known


def test_the_answer_sheet_records_the_verdict_the_scenario_forces(data: Path) -> None:
    sealed = truth(data)["scenarios"]["A"]
    assert sealed["scenario"] == "A"
    assert sealed["expected_verdict"] == "likely"
    assert len(sealed["footprint_accounts"]) == 2
    assert sealed["footprint_account_names"] == list(TREATED)


def test_the_two_not_real_scenarios_are_sealed_with_the_check_that_catches_them(
    data: Path,
) -> None:
    """§25 D and E close at Verify with zero model calls. Which *check* closes
    each is the part worth sealing: a case that closed for the right reason by
    accident would grade the same as one that reasoned, and the harness would
    never know."""
    sealed = truth(data)["scenarios"]

    assert sealed["D"]["failing_check"] == "artefact"
    assert sealed["E"]["failing_check"] == "definition_drift"
    for scenario in ("D", "E"):
        assert sealed[scenario]["closes_at"] == "verify"
        assert sealed[scenario]["expected_model_calls"] == 0
        assert sealed[scenario]["true_driver"] is None


def test_the_refund_batch_dominates_its_movement(data: Path) -> None:
    """§25 D: *"single credit note = 71% of delta"*. The share is what the
    artefact check reads against `max_single_record_share: 0.35`, so it is the
    number that has to land — not the headline percentage."""
    import csv

    sealed = truth(data)["scenarios"]["D"]
    with (data / "raw" / "billing" / "credit_note.csv").open(encoding="utf-8") as handle:
        notes = list(csv.DictReader(handle))

    batch = [n for n in notes if n["credit_id"] == sealed["credit_id"]]
    assert len(batch) == 1
    assert float(batch[0]["amount"]) == sealed["credit_amount"]
    assert batch[0]["reason_code"] == "refund_batch"
    # No other credit note in the corpus comes close; this one is the artefact.
    others = [float(n["amount"]) for n in notes if n["credit_id"] != sealed["credit_id"]]
    assert sealed["credit_amount"] > 2 * max(others)


# ── §22's volumes and cadences ────────────────────────────────────────────────


@pytest.mark.parametrize(
    "table,low,high",
    [
        ("billing/invoice_line.csv", 150_000, 220_000),
        ("crm/opportunity.csv", 1_800, 3_000),
        ("product_ops/ticket.csv", 38_000, 52_000),
        ("product_ops/deploy_event.csv", 600, 1_000),
        ("crm/account.csv", 120, 120),
    ],
)
def test_volumes_land_in_the_ranges_22_states(
    data: Path, table: str, low: int, high: int
) -> None:
    assert low <= len(rows(data, table)) <= high


def test_product_ops_carries_eight_months_where_billing_carries_thirty_six(
    data: Path,
) -> None:
    """§22's short product_ops history is what makes scenario C honest at 1.3 —
    a sparse baseline the system has to notice, not a flag someone sets."""
    tickets = [
        date.fromisoformat(t["created_at"][:10]) for t in rows(data, "product_ops/ticket.csv")
    ]
    invoices = [date.fromisoformat(i["invoice_date"]) for i in rows(data, "billing/invoice.csv")]

    assert min(tickets) >= OPS_START
    assert min(invoices) <= SPAN_START + timedelta(days=31)
    assert (max(invoices) - min(invoices)).days > 1000
    assert (max(tickets) - min(tickets)).days < 260


def test_billing_and_crm_disagree_about_account_identity(data: Path) -> None:
    """Conformance is Stage 0's job and 0.8's alias map is what does it. If the
    two sources already agreed, that test would pass on nothing."""
    crm = {a["account_id"] for a in rows(data, "crm/account.csv")}
    billing = {line["account_id"] for line in rows(data, "billing/invoice_line.csv")}

    assert billing.isdisjoint(crm)
    assert len(billing) == len(crm)


def test_every_ticket_carries_text_on_the_row_the_causal_model_made(data: Path) -> None:
    """Ladder step 1.5 fills text into the rows 0.7 created, never alongside
    them, so the ticket *count* the SCM produced and the ticket *documents*
    retrieval reads can never disagree."""
    import csv

    with (data / "raw" / "product_ops" / "ticket.csv").open(encoding="utf-8") as handle:
        tickets = list(csv.DictReader(handle))

    assert tickets
    assert all(t["body_text"].strip() for t in tickets)
    assert all(t["subject"].strip() for t in tickets)
    assert len({t["body_text"] for t in tickets}) > 50, "one template is not a corpus"


def test_the_price_rise_measurably_cooled_enterprise_upsell(data: Path) -> None:
    """The decoy has to have a *real* effect, or it is not a decoy.

    §35.2 requires `pricing_change` to survive adjudication as **minor**, with a
    share of 0.05-0.12 — which is impossible if the price rise moved nothing at
    all. What it moved is appetite: enterprise accounts kept renewing but
    stopped buying more. Measured here as a difference-in-differences against
    the segments the rise did not touch, so ordinary drift cannot account for it.
    """
    accounts = {a["account_id"]: a for a in rows(data, "crm/account.csv")}
    won: defaultdict[tuple[str, str], list[int]] = defaultdict(list)
    for opportunity in rows(data, "crm/opportunity.csv"):
        account = accounts[opportunity["account_id"]]
        if opportunity["type"] != "expansion" or account["region"] == COMPETITOR_REGION:
            continue  # APAC carries the other decoy; keep the two apart
        era = "after" if opportunity["close_date"] >= "2026-03-01" else "before"
        segment = "enterprise" if account["segment"] == "enterprise" else "other"
        won[(segment, era)].append(int(opportunity["closed_won"]))

    def rate(segment: str, era: str) -> float:
        outcomes = won[(segment, era)]
        assert len(outcomes) >= 20, f"too few {segment} expansions {era} to conclude anything"
        return sum(outcomes) / len(outcomes)

    exposed = rate("enterprise", "after") - rate("enterprise", "before")
    control = rate("other", "after") - rate("other", "before")
    assert exposed - control <= -0.15, "the price rise left no trace on upsell"


def test_thirty_nine_of_the_forty_one_held_steady(data: Path) -> None:
    """§24, verbatim: the price rise "hit all 41 enterprise accounts; 39 of them
    held steady". That ratio is the whole Locality refutation — and it only
    holds if the rise affected appetite rather than retention."""
    accounts = {a["account_id"]: a for a in rows(data, "crm/account.csv")}
    enterprise = {i for i, a in accounts.items() if a["segment"] == "enterprise"}

    exposed = [
        r
        for r in rows(data, "crm/renewal.csv")
        if r["account_id"] in enterprise and r["closed_date"] >= "2026-03-01"
    ]
    failed = {r["account_id"] for r in exposed if r["outcome"] != "renewed"}
    treated = {
        i for i, a in accounts.items() if a["account_name"] in TREATED
    }
    assert failed <= treated, "an unexposed enterprise account broke the decoy's story"


# ── Freshness — found by the P0 audit ─────────────────────────────────────────

#: Which column carries "when did this row land" for each source, per §22.
#: `product_ops` has no ingest column in §22's schema; for a ≤15-minute stream
#: the event time *is* the arrival time, which is the honest reading.
INGEST_COLUMNS = {
    "billing": [
        ("billing/invoice.csv", "_ingested_at"),
        ("billing/invoice_line.csv", "_ingested_at"),
        ("billing/credit_note.csv", "_ingested_at"),
    ],
    "crm": [
        ("crm/account.csv", "_synced_at"),
        ("crm/opportunity.csv", "_synced_at"),
    ],
    "product_ops": [
        ("product_ops/ticket.csv", "created_at"),
        ("product_ops/deploy_event.csv", "deployed_at"),
        ("product_ops/incident.csv", "started_at"),
    ],
}


def watermark(data: Path, source: str) -> datetime:
    """§22: watermark per source = max(_ingested_at | _synced_at)."""
    return max(
        datetime.fromisoformat(row[column])
        for table, column in INGEST_COLUMNS[source]
        for row in rows(data, table)
    )


def test_the_source_the_contract_names_is_fresh_at_as_of(data: Path) -> None:
    """The audit finding this test exists for.

    §15 S1 computes freshness as `now - watermark` against the contract's
    declared `refresh.sla_hours`. `net_revenue` names **billing**, 26 hours.
    Invoicing on the 28th put the last billing row 52.8h behind `AS_OF`, so
    scenario A would have gone *provisional with capped confidence* at ladder
    1.3 — contradicting §25, which requires it to reach Likely. Nothing caught
    it, because nothing measured it.
    """
    contract = load(ROOT / "contracts" / "net_revenue.yaml")
    age = (AS_OF - watermark(data, contract.refresh.source)).total_seconds() / 3600

    assert 0 < age <= contract.refresh.sla_hours, (
        f"{contract.refresh.source} is {age:.1f}h old against a "
        f"{contract.refresh.sla_hours}h SLA"
    )


#: Per §22's cadences — daily, 24h batch, ≤15 min. `product_ops` gets 2h rather
#: than 15 minutes because event gaps on a low-volume stream are real; a flat
#: 24h for everything is what let the six-hour overnight silence through.
QUIET_AFTER_HOURS = {"billing": 26.0, "crm": 24.0, "product_ops": 2.0}


@pytest.mark.parametrize("source", ["billing", "crm", "product_ops"])
def test_no_source_has_gone_quiet(data: Path, source: str) -> None:
    """One of the two defects the audit found: tickets confined to business
    hours left a ≤15-minute stream six hours silent every night."""
    age = (AS_OF - watermark(data, source)).total_seconds() / 3600
    assert 0 < age <= QUIET_AFTER_HOURS[source], f"{source} watermark is {age:.1f}h old"


def test_the_crm_account_table_is_resynced_wholesale(data: Path) -> None:
    """The other defect, and the reason a per-*source* watermark is not enough.

    CRM's nightly batch carries every account row whether or not it changed, so
    the whole table should share a recent stamp. Stamping rows from
    `first_contract_date` left them reading 3.5 years stale — and the source
    watermark hid it completely, because `max()` over the source also sees
    `opportunity`, which was fresh. A dead table inside a live source is exactly
    what §15 S1's completeness check exists to catch.
    """
    stamps = [datetime.fromisoformat(a["_synced_at"]) for a in rows(data, "crm/account.csv")]
    oldest = (AS_OF - min(stamps)).total_seconds() / 3600

    assert oldest <= 24, f"the oldest account row is {oldest:.1f}h old; the batch is nightly"
