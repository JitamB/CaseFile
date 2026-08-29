# Data

**CaseFile** · Accenture Innovation Challenge 2026 · Problem Track 3 — BusinessIntelligence.ai · Team Jerry

`Part IV · §21–25`

[← Architecture](02-architecture.md) · [Index](README.md) · [Team & Ownership →](04-team.md)

---

# PART IV — DATA

## 21. Data Strategy

**Decision: simulate, seeded with real-world texture, validated against a public benchmark.**

### Why no real dataset works

We need revenue at invoice-line grain **plus** account-level renewals **plus** free text
about *those same named accounts* over time. That combination is simultaneously a company's
financials, customer list and support history. Nobody publishes it.

| Dataset | Gives | Fatal gap |
|---|---|---|
| Maven CRM Sales Opportunities (8.8k B2B opps) | Realistic pipeline shape, stages, values, agents | No free text, no billing, no tickets |
| Olist Brazilian E-Commerce (100k orders) | Structured + unstructured genuinely joined on `order_id`; 2 yrs real seasonality | B2C marketplace; no renewals, no accounts |
| UCI Online Retail II (1.07M rows) | True invoice-**line** grain; real returns as C-prefixed negative invoices | Zero text |
| HF / Kaggle support-ticket corpora (62k / 200k) | Real ticket phrasing, priorities, timestamps | Not linked to revenue or accounts |

And decisively: **a known true cause cannot exist in real data by definition.** If it were
labelled, there would have been no investigation.

### Why simulating is correct, not a fallback

1. The brief permits it twice: *"you are not expected to have access to a real company's
   proprietary data"* and *"a working proof-of-concept on illustrative or sample data is
   expected and encouraged."*
2. **Our architecture requires ground truth.** The evaluation harness measures whether
   CaseFile recovers the injected driver and refutes the decoys. On real data we could only
   *assert* accuracy; here we *measure* it.

### Three layers

**Layer 1 — Borrow the texture.** Invoice-value skew and return behaviour from Online Retail
II; pipeline structure and `lost_reason` distribution from Maven; ticket vocabulary and
length from the support corpora; seasonality shape from Olist. Result is *simulated*, not
*fabricated*.

**Layer 2 — Generate the spine from a causal model.** See §24.

**Layer 3 — Validate decomposition externally.** Stage 2 is load-bearing, so self-grading is
circular. We also run it against the **Squeeze / RiskLoc** semi-synthetic sets from
NetManAIOps, which carry labelled ground-truth root causes and published F1 scores for
Adtributor, HotSpot, Squeeze and RiskLoc. The adapter is real work — those sets are
predicted-vs-actual cuboids, so S2 needs a forecast baseline bolted on. **Timeboxed to two
days**; sets A and B0 run first, and the framing is decided in advance: competitive with
Adtributor/HotSpot at the depth this product needs; Squeeze and RiskLoc lead on
combinatorial root causes beyond our decomposition depth, which is outside the product's
scope.

---

## 22. Sources and Schemas

| # | Source | Grain | Refresh | History | Tables |
|---|---|---|---|---|---|
| S1 | `billing` | invoice line | daily, 26h SLA | 36 mo | `invoice`, `invoice_line`, `credit_note`, `price_book` |
| S2 | `crm` | opportunity / account | 24h batch | 36 mo | `account`, `opportunity`, `opportunity_note`*, `renewal` |
| S3 | `product_ops` | event / document | ≤15 min | **8 mo** | `ticket`*, `ticket_message`*, `deploy_event`, `incident`, `news_item`* |

`*` = unstructured. `product_ops`' short history creates the sparse-history scenario honestly.

```
billing.invoice_line
  invoice_id, line_no, invoice_date, account_id, product_id, region,
  qty, unit_price, amount_gross, discount, amount_net, currency,
  is_recurring, contract_start, contract_end, _ingested_at
billing.credit_note
  credit_id, credit_date, invoice_id, account_id, amount, reason_code, _ingested_at
billing.price_book
  product_id, segment, effective_from, effective_to, list_price

crm.account
  account_id, account_name, region, segment, industry, owner_user_id,
  first_contract_date, csm_user_id
crm.opportunity
  opp_id, account_id, type{new,renewal,expansion}, stage, arr_value,
  created_at, close_date, closed_won, lost_reason_code, owner_user_id, _synced_at
crm.opportunity_note          -- UNSTRUCTURED
  note_id, opp_id, account_id, author_user_id, created_at, body_text
crm.renewal
  renewal_id, account_id, arr_up_for_renewal, arr_renewed, due_date,
  closed_date, outcome{renewed,churned,downgraded,open}

product_ops.ticket            -- UNSTRUCTURED
  ticket_id, account_id, priority{P1..P4}, category, created_at,
  first_response_at, resolved_at, status, subject, body_text
product_ops.deploy_event
  deploy_id, service, deployed_at, version, change_summary, affected_regions[]
product_ops.incident
  incident_id, service, started_at, resolved_at, severity, affected_accounts[]
product_ops.news_item         -- UNSTRUCTURED
  news_id, published_at, source, competitor, region, headline, body_text
```

**Conformance keys:** `account_id` (via `account_alias` map) · `region` · `product_id` ·
`fiscal_calendar(date → period)` 4-4-5. Watermark per source =
`max(_ingested_at | _synced_at)`.

**Volume:** 120 accounts · 4 regions · 3 segments · 6 products · 30 months ≈ 180k invoice
lines · 2.4k opportunities · 9k notes · 45k tickets · 800 deploys · 200 news items.

---

## 23. The Six KPIs

| # | KPI | Source(s) | Grain | Cadence |
|---|---|---|---|---|
| K1 | Net Revenue | billing | invoice line | daily |
| K2 | Gross Renewal Rate | crm | opportunity | 24h |
| K3 | Expansion ARR | crm + billing | account | 24h |
| K4 | New Business ARR | crm | opportunity | 24h |
| K5 | Net Revenue Retention | billing + crm | account cohort | 24h |
| K6 | P1 Ticket Resolution Time | product_ops | ticket event | ≤15 min |

**Formulas**

```
K1   NetRev(t)  = Σ_{i∈L_t} (q_i · p_i − d_i) − Σ_{j∈C_t} c_j
K2   GRR(t)     = Σ_a ARR_renewed_a(t) / Σ_a ARR_due_a(t)
K3   ExpARR(t)  = Σ_{a∈existing} max(0, ARR_a(t) − ARR_a(t−1))
K4   NewARR(t)  = Σ_{a : first_contract_a ∈ t} ARR_a(t)
K5   NRR(t)     = (ARR₀ + Exp − Contr − Churn) / ARR₀      cohort = active at t−12m
K6   TTR_P1(t)  = median{ resolved_at_i − created_at_i | i ∈ T_t, priority = P1 }
```

**Connection graph — what makes them *connected*, not six separate dashboards**

```
        K6 (TTR_P1) ──drives──▶ K2 (GRR) ──┐
                                            ├──▶ K1 (Net Revenue)
        K3 (Expansion) ─────────────────────┤
        K4 (New ARR) ───────────────────────┘
        K1 + K2 + K3 ──────────────────────▶ K5 (NRR)
```

**Attribution identity used by Stage 2:**

```
ΔNetRev(t) = 1/12 · [ ΔARR_renewed + ΔARR_expansion + ΔARR_new − ΔARR_churned ]
             + ΔNonRecurring(t)
```
Residual tolerance ≤ 2% of |ΔNetRev|, else flagged as a reconciliation break.

**Decomposition**

```
Contribution     C_i = Δ_i / Δ_total ,  Σ C_i = 1
PVM              ΔRev = Σ(p₁−p₀)q₀        [PRICE]
                      + Σ p₀(q₁−q₀)        [VOLUME]
                      + Σ(p₁−p₀)(q₁−q₀)    [MIX]
Concentration    K(k) = Σ_{top-k}|Δ_i| / Σ_i|Δ_i| ;  HHI = Σ (Δ_i/Δ_total)²
```

**Materiality**

```
STL          y_t = T_t + S_t + R_t
Robust z     z_t = (R_t − median(R)) / (1.4826 · MAD(R))
Material iff |z_t| > 3  ∧  persistence ≥ 2  ∧  |Δ|/y_{t−1} ≥ θ_rel  ∧  |Δ| ≥ θ_abs
Sparse       ŷ_t = y_{t−1}(1 + median_{p∈peers} Δ_p/y_{p,t−1}) ,  ceiling = Likely
```

---

## 24. The Generator

A **structural causal model**, not a random-number loop. That distinction is the point.

```
WE CHOOSE THE EXOGENOUS EVENTS   (sealed in data/ground_truth.json)

  integration_delay   → accounts ACME, NORTHWIND    onset 2026-04-12   ← TRUE CAUSE
  pricing_change      → all 41 enterprise accounts  onset 2026-03-01   ← decoy
  competitor_launch   → region APAC                 onset 2026-04-20   ← decoy
  seasonality         → all                         continuous         ← background
  (+ the scenario B, C and G events — sealed in the same file)

PROPAGATION (lagged SCM)

  tickets_a(t)    = base_a · (1 + 3.2·1[integration_delay_a, t−ℓ]),  ℓ ~ U(0,3)
  csat_a(t)       = csat_a(t−1) − β₁ · tickets̃_a(t−7)
  P(renew_a)      = σ(α − β₂·csat_a − β₃·priceΔ_a − β₄·competitor_a),  ℓ ~ U(30,60)
  invoice_a(t)    = ARR_a · 1[renew_a]   at contract boundary

RENDER at three grains / three cadences → billing · crm · product_ops
CORRUPT realistically → late arrivals · one refund batch · one definition change · missing fields
```

### The decoys are the most important design decision

They are not noise — they are deliberately *plausible* alternatives, each engineered to fail
exactly one test:

| Decoy | Killed by | Why |
|---|---|---|
| `pricing_change` | **Locality** (J = 0.05) | Hit all 41 enterprise accounts; 39 held steady. A cause with a wider footprint than its effect is not the cause |
| `competitor_launch` | **Locality + Timing** | APAC-only, and starts *after* the East decline began |
| `integration_delay` | survives Timing, Locality, Control — **fails Dose (n=2)** | Which is why the honest verdict is **Likely, not Confirmed** |

### Text corpus honesty controls

1. **Generate once, freeze, commit.** No live generation at demo time — so the model writing
   tickets is never the model reading them in the same run.
2. **~85% irrelevant traffic** — password resets, billing queries, feature requests. Finding
   a needle in a stack of needles proves nothing.
3. **Deliberately misleading documents** — a ticket that mentions the integration and
   concludes it was fine; a CRM note blaming pricing with no evidence; genuinely ambiguous
   notes.
4. **The noise is templates; the signal is authored.** The ~85% irrelevant traffic is
   template-generated with vocabulary sampled from the real support corpora — ~38k
   documents need no model. Only the ~50 documents that carry signal or misdirection are
   LLM-authored, then frozen with the rest.

### What ships in the repo

Generator + fixed seed (reproduces structured tables byte-identically) · the frozen text
corpus as a committed artifact · `ground_truth.json` committed but **the pipeline is
forbidden from reading it — only `tests/` may.**

---

## 25. Seeded Scenarios

| # | Scenario | Requirement | Expected behaviour |
|---|---|---|---|
| **A** | Multi-factor movement — 3 injected events, PVM all non-zero | R4 | Decompose → 88% in 2 accounts; both decoys eliminated as primary (pricing keeps its −₹0.2 Cr minor share); `integration_delay` **Likely** (Dose inconclusive at n=2) |
| **B** | Low confidence — true cause is a competitor offer the sources **cannot see**: lost-reason fields left null, no notes on the footprint accounts in the window, news feed does not cover the segment | R5 | Probes return **uncheckable** (coverage ≈ 0 — nothing to check, as opposed to checked and empty) → **Undetermined** + discriminating question + contract gap raised |
| **C** | Sparse history — `p1_resolution_time`, product launched 2025-12-01, 8 months < 2×365d | R6 | Peer-borrowed baseline fires; `baseline: borrowed` in ledger; `confidence_ceiling = Likely` enforced regardless of test outcomes |
| **D** | Not-real #1 — refund batch, single credit note = 71% of Δ | bonus | Closed at Verify · artefact · **0 LLM calls** |
| **E** | Not-real #2 — `formula` changed to exclude discounts (contract epoch boundary) | bonus | Closed at Verify · definition drift · **0 LLM calls** |
| **F** | Entitlement — Support Lead opens case A | R7 | Region + segment filter, names hashed, ₹ banded, redaction stated on the page |
| **G** | Contested — `pricing_change` + `supply_delay` injected on the same 5 West accounts (Expansion ARR) in the same fortnight; footprints identical, both lags plausible | bonus (objective 5: contradictory evidence) | Both hypotheses reach **Likely**; Dose and Control cannot separate them → **Contested**, both presented with their evidence, + the discriminating question that would separate them |

**Scenario B vs the Scenario A decoys is the same signal read two ways, and the
distinction is the point:** in A the lost-reason fields are *populated* and none names a
competitor — checked-absent, which refutes. In B the fields are *null* and the sources
have no coverage of the footprint — uncheckable, which abstains. Evidence of absence
versus absence of evidence, as a code path.

---

[← Architecture](02-architecture.md) · [Index](README.md) · [Team & Ownership →](04-team.md)
