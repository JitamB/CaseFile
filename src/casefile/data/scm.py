"""The structural causal model — §24.

*"A structural causal model, not a random-number loop. That distinction is the
point."* We choose the exogenous events; everything else is consequence. That is
what lets `tests/` assert **recovery** rather than agreement: the pipeline is
graded against a cause it was never shown.

The chain, §24, with the lag settled against §10:

    tickets_a(t)  = base_a · (1 + 3.2·1[treated_a, t ≥ onset])
    csat_a(t)     = csat_a(t−1) − β₁ · tickets̃_a(t−7)
    P(renew_a)    = σ(α − β₂·csat_deficit_a − β₃·priceΔ_a − β₄·competitor_a)
    invoice_a(t)  = ARR_a/12 · 1[renew_a]   from the contract boundary

**On the dates.** §24 prints `integration_delay onset 2026-04-12` with a renewal
lag of U(30,60). §10, both fixtures and the deck say the onset precedes the two
renewal decisions by 21 and 23 days and that the loss lands in 2026-04. Those
cannot both hold — an April-12 onset puts the renewals in May, and April would
show nothing. This module follows §10; §24's two figures need a doc correction.

Nothing here reads the wall clock. `AS_OF` is the simulated present, so a demo
recorded today still says the same thing next month.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

SEED_FILE = Path(__file__).resolve().parents[3] / "data" / "seed.txt"

#: The simulated present. §15 S1 measures freshness as `now − watermark`; if
#: "now" were the wall clock, every recorded demo would rot overnight.
AS_OF = datetime(2026, 5, 1, 6, 0, 0)

# ── The world ─────────────────────────────────────────────────────────────────

# §22: 36 months of billing and crm, 8 months of product_ops. The short
# product_ops history is what makes scenario C's sparse baseline honest rather
# than a flag someone sets.
SPAN_START = date(2023, 5, 1)
SPAN_END = date(2026, 4, 30)
OPS_START = date(2025, 9, 1)
#: product_ops runs to the present, not to the period end. Billing and CRM close
#: with the fiscal month; a ≤15-minute event stream does not stop because the
#: books did, and stopping it there left the source looking six hours stale
#: against a fifteen-minute SLA.
OPS_END = AS_OF.date()

#: §22 volume line. East carries 49 of them — ev-002 counts "across 49 accounts".
ACCOUNTS_PER_REGION = {"East": 49, "West": 30, "North": 25, "APAC": 16}
N_ENTERPRISE = 41  # §24's pricing decoy is defined as hitting all of them
SEGMENTS = ("enterprise", "mid_market", "smb")
PRODUCTS = ("PRD-CORE", "PRD-SYNC", "PRD-INSIGHT", "PRD-GUARD", "PRD-FLOW", "PRD-EDGE")
INDUSTRIES = ("manufacturing", "retail", "bfsi", "healthcare", "logistics", "media")

# ── The exogenous events, sealed into the answer sheet ───────────────────────

TREATED = ("ACME", "NORTHWIND")
INTEGRATION_ONSET = date(2026, 3, 12)
#: §10: "ticket onset precedes each renewal decision by 21 and 23 days". The
#: dates are derived rather than written down, so the lag cannot drift from the
#: onset the way §24's did.
RENEWAL_LAG_DAYS = {"ACME": 21, "NORTHWIND": 23}
TREATED_RENEWAL = {
    name: INTEGRATION_ONSET + timedelta(days=lag) for name, lag in RENEWAL_LAG_DAYS.items()
}
TICKET_MULTIPLIER = 4.2  # §24's 1 + 3.2

PRICING_ONSET = date(2026, 3, 1)
PRICING_UPLIFT = 0.06  # list-price increase applied to every enterprise account

COMPETITOR_ONSET = date(2026, 4, 20)
COMPETITOR_REGION = "APAC"

CASE_PERIOD = (date(2026, 4, 1), date(2026, 4, 30))

# ── Propagation coefficients ──────────────────────────────────────────────────
# Chosen so the treated accounts fail their renewal and nobody else does. They
# are parameters of a stated model, not a nudge applied to the output.

#: β₁ — csat lost per month per unit of *relative* ticket excess. Relative, not
#: absolute: ev-003 reads "rose 3.2x against their own 12-month baseline", and a
#: big account with more tickets is not thereby less satisfied.
BETA_CSAT = 0.70
BETA_RENEW_CSAT = 3.5  # β₂
BETA_RENEW_PRICE = 3.0  # β₃ — × a 6% uplift is 0.18, so 39 of 41 hold steady
BETA_RENEW_COMPETITOR = 2.2  # β₄
#: α puts a healthy account at P(renew) ≈ 0.996. Higher than it looks: at 0.96,
#: fourteen accounts churn for no reason across the span and scenario A's
#: concentration drowns in them.
ALPHA_RENEW = 5.5

#: §24's fourth injected event: seasonality, "all accounts, continuous". It is
#: background rather than a cause anyone investigates, but a corpus with no
#: ordinary variation makes Stage 2 look staged — and gives Verify's materiality
#: gate nothing to distinguish a real movement from.
SEASONAL_AMPLITUDE = 0.16
SEASONAL_PEAK_MONTH = 10

#: Upsell attempts per account per month, and the base rate at which they land.
EXPANSION_RATE = 0.42
EXPANSION_WIN = 0.55
#: What the 2026-03 price rise does to enterprise appetite. Not churn — chill.
PRICING_UPSELL_CHILL = 0.4

#: Lost-reason codes the CRM offers. None of them names a competitor — which is
#: exactly what makes scenario A's probe *checked-absent* rather than empty
#: (§25). The two competitor codes exist and are used, but only in APAC.
LOST_REASONS = ("budget_freeze", "no_decision", "product_gap", "timing", "internal_project")
COMPETITOR_LOST_REASONS = ("competitor_price", "competitor_features")


@dataclass(frozen=True)
class Account:
    account_id: str  # crm form, "ACC-0001"
    billing_id: str  # billing form, "A0001" — the two disagree on purpose
    account_name: str
    region: str
    segment: str
    industry: str
    first_contract_date: date
    arr: float
    renewal_month: int
    renewal_day: int
    base_tickets: float
    csat0: float
    #: A handful of accounts were reassigned between regions mid-history. CRM
    #: overwrites the account's region; billing keeps whatever it stamped on the
    #: invoice line at the time. The two therefore disagree about the past, which
    #: is what Stage 0's conformance exists to reconcile — and without it,
    #: "conform region" would be a step that provably never changes anything.
    prior_region: str | None = None
    region_changed_on: date | None = None

    def region_at(self, when: date) -> str:
        """Billing's view: the region as it stood when the line was written."""
        if self.prior_region and self.region_changed_on and when < self.region_changed_on:
            return self.prior_region
        return self.region


@dataclass(frozen=True)
class Expansion:
    """An upsell attempt. Won ones raise the account's recurring base; lost ones
    carry a reason code, and the reason codes are scenario A's other half."""

    account_id: str
    created: date
    close_date: date
    arr_delta: float
    won: bool
    lost_reason: str


@dataclass(frozen=True)
class Renewal:
    account_id: str
    due_date: date
    closed_date: date
    arr_up_for_renewal: float
    arr_renewed: float
    outcome: str  # renewed | churned | downgraded


def read_seed() -> int:
    """The seed is a committed file, not a literal — §41.2 commits `data/seed.txt`
    so that reproducing the dataset does not require reading the source."""
    return int.from_bytes(SEED_FILE.read_text(encoding="utf-8").strip().encode(), "big")


class World:
    """One deterministic run of the causal model.

    Every draw comes from `random.Random(seed)` in a fixed order — stdlib
    Mersenne Twister is stable across Python versions and platforms, which is
    what `make data` reproducing byte-identically actually rests on.
    """

    def __init__(self, seed: int | None = None) -> None:
        self.seed = seed if seed is not None else read_seed()
        self.rng = random.Random(self.seed)
        self.accounts = self._build_accounts()
        self.by_id = {a.account_id: a for a in self.accounts}
        self.enterprise = [a for a in self.accounts if a.segment == "enterprise"]
        self.daily_tickets = self._propagate_tickets()
        self.csat = self._propagate_csat()
        self.renewals = self._decide_renewals()
        self.expansions = self._decide_expansions()
        self._expansion_by_account: dict[str, list[tuple[date, float]]] = {}
        for e in self.expansions:
            if e.won:
                self._expansion_by_account.setdefault(e.account_id, []).append(
                    (e.close_date, e.arr_delta)
                )
        self._steps: dict[str, list[tuple[date, float]]] = {}
        for renewal in self.renewals:
            if renewal.outcome == "renewed" or renewal.arr_up_for_renewal == 0:
                continue
            kept = renewal.arr_renewed / renewal.arr_up_for_renewal
            self._steps.setdefault(renewal.account_id, []).append((renewal.closed_date, kept))

    # ── Population ────────────────────────────────────────────────────────────

    def _build_accounts(self) -> list[Account]:
        rng = self.rng
        names = _account_names()
        accounts: list[Account] = []
        index = 0

        # Enterprise slots are dealt out per region first, so the 41 are spread
        # rather than piled into whichever region happens to be built first.
        enterprise_left = N_ENTERPRISE
        for region, count in ACCOUNTS_PER_REGION.items():
            share = round(N_ENTERPRISE * count / sum(ACCOUNTS_PER_REGION.values()))
            region_enterprise = min(share, enterprise_left)
            enterprise_left -= region_enterprise

            for position in range(count):
                treated = region == "East" and position < len(TREATED)
                name = TREATED[position] if treated else names[index]
                segment = (
                    "enterprise"
                    if position < region_enterprise
                    else rng.choice(("mid_market", "smb"))
                )
                arr = self._arr_for(rng, name, segment)
                first = SPAN_START - timedelta(days=rng.randint(200, 1400))
                # Reassigned well before the case window, so scenario A's
                # March-to-April comparison is untouched by it.
                reassigned = not treated and rng.random() < 0.035
                prior_region = (
                    rng.choice([r for r in ACCOUNTS_PER_REGION if r != region])
                    if reassigned
                    else None
                )
                changed_on = (
                    date(2024, rng.randint(1, 12), rng.randint(1, 28)) if reassigned else None
                )

                boundary = TREATED_RENEWAL.get(name)
                renewal_month = boundary.month if boundary else first.month
                renewal_day = boundary.day if boundary else min(first.day, 28)

                accounts.append(
                    Account(
                        account_id=f"ACC-{index + 1:04d}",
                        billing_id=f"A{index + 1:04d}",
                        account_name=name,
                        region=region,
                        segment=segment,
                        industry=rng.choice(INDUSTRIES),
                        first_contract_date=first,
                        arr=arr,
                        renewal_month=renewal_month,
                        renewal_day=renewal_day,
                        base_tickets=self._base_tickets(rng, segment),
                        csat0=round(rng.uniform(7.4, 9.1), 2),
                        prior_region=prior_region,
                        region_changed_on=changed_on,
                    )
                )
                index += 1
        return accounts

    def _arr_for(self, rng: random.Random, name: str, segment: str) -> float:
        """ACME and NORTHWIND are sized so their loss dominates the East
        movement — which is the scenario, not a thumb on the scale afterwards."""
        if name == "ACME":
            return 156_000_000.0
        if name == "NORTHWIND":
            return 96_000_000.0
        bands = {
            "enterprise": (70_000_000, 120_000_000),
            "mid_market": (28_000_000, 60_000_000),
            "smb": (6_000_000, 22_000_000),
        }
        low, high = bands[segment]
        return float(round(rng.uniform(low, high), -4))

    def _base_tickets(self, rng: random.Random, segment: str) -> float:
        rate = {"enterprise": 3.10, "mid_market": 1.70, "smb": 0.85}[segment]
        return rate * rng.uniform(0.7, 1.3)

    # ── Propagation ───────────────────────────────────────────────────────────

    def is_treated(self, account: Account) -> bool:
        return account.account_name in TREATED

    def _propagate_tickets(self) -> dict[tuple[str, date], int]:
        """`tickets_a(t) = base_a · (1 + 3.2·1[treated])`, Poisson-ish via a
        seeded draw. Only over the product_ops window — §22 gives that source
        eight months of history and no more."""
        counts: dict[tuple[str, date], int] = {}
        for account in self.accounts:
            treated = self.is_treated(account)
            day = OPS_START
            while day <= OPS_END:
                rate = account.base_tickets
                if treated and day >= INTEGRATION_ONSET:
                    rate *= TICKET_MULTIPLIER
                # Weekday seasonality: support queues are quiet at weekends.
                if day.weekday() >= 5:
                    rate *= 0.35
                counts[(account.account_id, day)] = _poisson(self.rng, rate)
                day += timedelta(days=1)
        return counts

    def _propagate_csat(self) -> dict[tuple[str, date], float]:
        """`csat_a(t) = csat_a(t−1) − β₁ · tickets̃_a(t−7)`, evaluated monthly —
        the renewal decision is the only consumer and it is monthly."""
        series: dict[tuple[str, date], float] = {}
        for account in self.accounts:
            level = account.csat0
            for month_start in month_range(OPS_START, OPS_END):
                # The 7-day lag of §24, read as a window that opens a week
                # before the month and closes with it.
                span = day_range(
                    month_start - timedelta(days=7), month_start + timedelta(days=23)
                )
                window = [self.daily_tickets.get((account.account_id, d), 0) for d in span]
                pressure = sum(window) / max(len(window), 1)
                excess = max(0.0, pressure / account.base_tickets - 1.0)
                level = max(1.0, level - BETA_CSAT * excess)
                level = min(account.csat0, level + 0.08)  # recovers slowly
                series[(account.account_id, month_start)] = round(level, 3)
        return series

    def stream(self, purpose: str, key: str) -> random.Random:
        """An independent RNG per entity per purpose.

        One shared stream means every draw depends on how many draws happened
        before it, so an unrelated change — more days of ticket generation, say —
        silently reshuffles who churns three functions later. That is how the
        freshness fix broke scenario A. Keying the stream on the entity makes a
        decision depend on the entity, which is the only thing it should.
        """
        return random.Random(f"{self.seed}:{purpose}:{key}")

    def csat_deficit(self, account: Account, when: date) -> float:
        month_key = date(when.year, when.month, 1)
        level = self.csat.get((account.account_id, month_key), account.csat0)
        return max(0.0, account.csat0 - level)

    def renew_probability(self, account: Account, when: date) -> float:
        """σ(α − β₂·csat_deficit − β₃·priceΔ − β₄·competitor), §24."""
        score = (
            ALPHA_RENEW
            - BETA_RENEW_CSAT * self.csat_deficit(account, when)
            - BETA_RENEW_PRICE * self._price_delta(account, when)
            - BETA_RENEW_COMPETITOR * self._competitor_pressure(account, when)
        )
        return 1.0 / (1.0 + math.exp(-score))

    def is_injected_failure(self, account: Account, when: date) -> bool:
        """The renewal the injected event is defined to have caused."""
        return (
            self.is_treated(account)
            and TREATED_RENEWAL.get(account.account_name) == when
        )

    def _price_delta(self, account: Account, when: date) -> float:
        return PRICING_UPLIFT if account.segment == "enterprise" and when >= PRICING_ONSET else 0.0

    def _competitor_pressure(self, account: Account, when: date) -> float:
        return 1.0 if account.region == COMPETITOR_REGION and when >= COMPETITOR_ONSET else 0.0

    def _decide_renewals(self) -> list[Renewal]:
        """`P(renew) = σ(α − β₂·csat_deficit − β₃·priceΔ − β₄·competitor)`.

        Once an account churns it stops renewing — an account cannot renew a
        contract it walked away from, and a ledger that says otherwise would
        make every downstream ARR figure wrong.
        """
        renewals: list[Renewal] = []
        for account in self.accounts:
            share = 1.0
            rng = self.stream("renewal", account.account_id)
            for year in range(SPAN_START.year, SPAN_END.year + 1):
                due = _safe_date(year, account.renewal_month, account.renewal_day)
                if not (SPAN_START <= due <= SPAN_END):
                    continue
                if due < account.first_contract_date:
                    continue

                at_risk = account.arr * share
                probability = self.renew_probability(account, due)
                deficit = self.csat_deficit(account, due)

                if self.is_injected_failure(account, due):
                    # §24: "WE CHOOSE THE EXOGENOUS EVENTS." The two treated
                    # accounts failing is the injection, not a sample from it —
                    # the model's job is to make that failure *plausible*, and
                    # `renew_probability` above says 0.004 and 0.04, which it is.
                    # Sampling it instead made the entire scenario hinge on one
                    # draw: a change to ticket generation elsewhere reshuffled
                    # the stream and NORTHWIND quietly renewed.
                    outcome, kept = "churned", 0.0
                elif rng.random() < probability:
                    outcome, kept = "renewed", 1.0
                else:
                    # How a failed renewal fails depends on how bad it got. A
                    # marginal account trims its contract; an account whose
                    # support experience collapsed walks away. Leaving this to a
                    # flat coin flip made the scenario hinge on a draw rather
                    # than on the cause.
                    severity = min(1.0, deficit / 3.0)
                    if rng.random() < 0.45 + 0.5 * severity:
                        outcome, kept = "churned", 0.0
                    else:
                        outcome, kept = "downgraded", round(rng.uniform(0.25, 0.5), 3)

                renewals.append(
                    Renewal(
                        account_id=account.account_id,
                        due_date=due,
                        closed_date=due,
                        arr_up_for_renewal=round(at_risk, 2),
                        arr_renewed=round(at_risk * kept, 2),
                        outcome=outcome,
                    )
                )
                share *= kept
                if share == 0.0:
                    break
        return renewals

    def _decide_expansions(self) -> list[Expansion]:
        """Upsell, and what suppresses it.

        This is where the pricing decoy earns its keep. A 6% list increase does
        not make 41 accounts churn — §24 is explicit that 39 of them held
        steady — but it does cool their appetite for buying more. That gives
        `pricing_change` a real, small, measurable share of the movement, which
        is what §35.2 means when it requires the decoy to survive as *minor*
        rather than vanish. A decoy with no effect at all is not a decoy; it is
        a distraction nobody would have proposed.
        """
        out: list[Expansion] = []
        for account in self.accounts:
            rng = self.stream("expansion", account.account_id)
            start = max(SPAN_START, account.first_contract_date)
            for month in month_range(start, SPAN_END):
                if rng.random() > EXPANSION_RATE:
                    continue
                created = _safe_date(month.year, month.month, rng.randint(1, 26))
                close = created + timedelta(days=rng.randint(12, 55))
                if close > SPAN_END:
                    continue

                win = EXPANSION_WIN
                if account.segment == "enterprise" and close >= PRICING_ONSET:
                    win *= PRICING_UPSELL_CHILL
                if self.is_treated(account) and close >= INTEGRATION_ONSET:
                    win *= 0.2
                if account.region == COMPETITOR_REGION and close >= COMPETITOR_ONSET:
                    win *= 0.5

                won = rng.random() < win
                delta = account.arr * rng.uniform(0.012, 0.045) if won else 0.0
                if won:
                    reason = ""
                elif account.region == COMPETITOR_REGION and close >= COMPETITOR_ONSET:
                    reason = rng.choice(COMPETITOR_LOST_REASONS)
                else:
                    # Never a competitor code outside APAC. This is what makes
                    # the East probe *checked-absent* rather than empty (§25).
                    reason = rng.choice(LOST_REASONS)

                out.append(
                    Expansion(account.account_id, created, close, round(delta, 2), won, reason)
                )
        return out

    def expansion_arr(self, account: Account, day: date) -> float:
        return sum(
            delta
            for when, delta in self._expansion_by_account.get(account.account_id, ())
            if when <= day
        )

    # ── What the renderer asks for ────────────────────────────────────────────

    def recurring_share(self, account: Account, day: date) -> float:
        """The multiple of base ARR billing on this day: what survived renewal,
        plus whatever upsell has landed since."""
        if day < account.first_contract_date:
            return 0.0
        share = 1.0
        for when, kept in self._steps.get(account.account_id, ()):
            if day >= when:
                share *= kept
        if share == 0.0:
            return 0.0
        return share + self.expansion_arr(account, day) / account.arr

    def answer_sheet(self) -> dict[str, object]:
        """What we injected, for `tests/` to grade recovery against.

        Named for the concept rather than the filename on purpose: only the
        module that *writes* the file should have to name it, and this one does
        not write anything. Keeping the isolation rule's exemption list at a
        single entry is worth a rename.
        """
        treated_ids = [a.account_id for a in self.accounts if self.is_treated(a)]
        return {
            "scenario": "A",
            "description": "Multi-factor movement — one true cause and two plausible decoys.",
            "kpi": "net_revenue",
            "period": "2026-04",
            "dimensions": {"region": "East"},
            "true_driver": "integration_delay",
            "footprint_accounts": treated_ids,
            "footprint_account_names": list(TREATED),
            "events": [
                {
                    "driver_id": "integration_delay",
                    "role": "true_cause",
                    "onset": INTEGRATION_ONSET.isoformat(),
                    "accounts": treated_ids,
                    "ticket_multiplier": TICKET_MULTIPLIER,
                },
                {
                    "driver_id": "pricing_change",
                    "role": "decoy",
                    "onset": PRICING_ONSET.isoformat(),
                    "accounts": [a.account_id for a in self.enterprise],
                    "uplift": PRICING_UPLIFT,
                    "killed_by": "locality",
                },
                {
                    "driver_id": "competitor_offer",
                    "role": "decoy",
                    "onset": COMPETITOR_ONSET.isoformat(),
                    "region": COMPETITOR_REGION,
                    "killed_by": "locality_and_timing",
                },
            ],
            "expected_verdict": "likely",
            "expected_verdict_reason": (
                "n = 2 treated accounts, below the n >= 5 minimum for the dose test, "
                "so Confirmed is unreachable by construction"
            ),
            "as_of": AS_OF.isoformat(),
        }


# ── Small deterministic helpers ───────────────────────────────────────────────


def _poisson(rng: random.Random, mean: float) -> int:
    """Knuth's method. `random.Random` has no Poisson, and numpy is not a
    dependency at this ladder step."""
    if mean <= 0:
        return 0
    limit, count, product = math.exp(-mean), 0, rng.random()
    while product > limit:
        count += 1
        product *= rng.random()
    return count


def month_range(start: date, end: date) -> list[date]:
    out, current = [], date(start.year, start.month, 1)
    while current <= end:
        out.append(current)
        current = date(current.year + current.month // 12, current.month % 12 + 1, 1)
    return out


def day_range(start: date, end: date) -> list[date]:
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def _safe_date(year: int, month: int, day: int) -> date:
    return date(year, month, min(day, 28))


def _account_names() -> list[str]:
    """A fixed roster, built without the RNG so that adding an account later
    does not reshuffle every name before it."""
    stems = (
        "Alder", "Basalt", "Cobalt", "Dunmore", "Everest", "Fairlight", "Granite",
        "Harbour", "Ironwood", "Juniper", "Kestrel", "Lantern", "Meridian", "Nimbus",
        "Orchard", "Pinnacle", "Quarry", "Redwood", "Sable", "Tamarind", "Umber",
        "Vantage", "Westfield", "Yardley",
    )
    suffixes = ("Industries", "Systems", "Logistics", "Retail", "Health")
    return [f"{stem} {suffix}" for suffix in suffixes for stem in stems]


def seasonal_factor(when: date) -> float:
    """Annual demand cycle on usage volume, peaking in the festive quarter."""
    phase = 2 * math.pi * (when.month - SEASONAL_PEAK_MONTH) / 12.0
    return 1.0 + SEASONAL_AMPLITUDE * math.cos(phase)
