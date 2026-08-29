# CaseFile — Round 2 Minimum Requirements Spec

Scope: the four prototype requirements below, with formulas and data inputs.
Stated minimums vs. what we deliver:

| Requirement | Minimum | Delivered |
|---|---|---|
| Connected KPIs | 3–5 | **6** |
| Data sources | 2–3 | **3** |
| Distinct grains | — | **3** (invoice-line · opportunity · event) |
| Distinct refresh cadences | — | **3** (daily 26h SLA · 24h batch · near-real-time) |
| Semantic contract elements | 6 | **8** (+ composition edges, + history_start) |
| Personas | 2 | **4** (3 narratives + 1 entitlement-restricted) |
| Multi-factor movements | 1 | **3** (1 multi-factor, 1 abstention, 1 sparse-history) |
| Injected drivers | ≥1 known | **3** (1 true + 2 decoys) |

---

# 1 · Data Inputs

## 1.1 Sources

| # | Source | Grain | Refresh | History | Tables |
|---|---|---|---|---|---|
| S1 | `billing` | invoice line | daily, 26h SLA | 36 mo | `invoice`, `invoice_line`, `credit_note`, `price_book` |
| S2 | `crm` | opportunity / account | 24h batch | 36 mo | `account`, `opportunity`, `opportunity_note`, `renewal` |
| S3 | `product_ops` | event / document | near-real-time (≤15 min) | 8 mo | `ticket`, `ticket_message`, `deploy_event`, `incident`, `news_item` |

## 1.2 Schemas

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

crm.opportunity_note              -- UNSTRUCTURED
  note_id, opp_id, account_id, author_user_id, created_at, body_text

crm.renewal
  renewal_id, account_id, arr_up_for_renewal, arr_renewed, due_date,
  closed_date, outcome{renewed,churned,downgraded,open}

product_ops.ticket                -- UNSTRUCTURED
  ticket_id, account_id, priority{P1..P4}, category, created_at,
  first_response_at, resolved_at, status, subject, body_text

product_ops.deploy_event
  deploy_id, service, deployed_at, version, change_summary, affected_regions[]

product_ops.incident
  incident_id, service, started_at, resolved_at, severity, affected_accounts[]

product_ops.news_item             -- UNSTRUCTURED
  news_id, published_at, source, competitor, region, headline, body_text
```

## 1.3 Conformance keys

`account_id` (via `account_alias` map) · `region` · `product_id` · `fiscal_calendar(date → period)` (4-4-5)
Per-source watermark: `max(_ingested_at | _synced_at)`.

## 1.4 Volume

120 accounts · 4 regions · 3 segments · 6 products · 30 months
≈180k invoice lines · 2.4k opportunities · 9k notes · 45k tickets · 800 deploys · 200 news items

---

# 2 · Connected KPIs (6)

## 2.1 Definitions and formulas

| # | KPI | Source(s) | Grain | Cadence |
|---|---|---|---|---|
| K1 | Net Revenue | S1 | invoice line | daily |
| K2 | Gross Renewal Rate | S2 | opportunity | 24h |
| K3 | Expansion ARR | S2 + S1 | account | 24h |
| K4 | New Business ARR | S2 | opportunity | 24h |
| K5 | Net Revenue Retention | S1 + S2 | account cohort | 24h |
| K6 | P1 Ticket Resolution Time | S3 | ticket event | ≤15 min |

**K1 · Net Revenue**

$$\mathrm{NetRev}(t)=\sum_{i \in L_t}\big(q_i \cdot p_i - d_i\big) \;-\; \sum_{j \in C_t} c_j$$

$L_t$ = invoice lines in period $t$; $q$ qty, $p$ unit price, $d$ discount, $c$ credit note.

**K2 · Gross Renewal Rate**

$$\mathrm{GRR}(t)=\frac{\sum_a \mathrm{ARR}^{\text{renewed}}_a(t)}{\sum_a \mathrm{ARR}^{\text{due}}_a(t)}$$

**K3 · Expansion ARR**

$$\mathrm{ExpARR}(t)=\sum_{a \in A^{\text{existing}}}\max\!\big(0,\ \mathrm{ARR}_a(t)-\mathrm{ARR}_a(t-1)\big)$$

**K4 · New Business ARR**

$$\mathrm{NewARR}(t)=\sum_{a\,:\,\text{first\_contract}_a \in t}\mathrm{ARR}_a(t)$$

**K5 · Net Revenue Retention** (cohort = accounts active at $t-12$)

$$\mathrm{NRR}(t)=\frac{\mathrm{ARR}_0+\mathrm{Exp}-\mathrm{Contr}-\mathrm{Churn}}{\mathrm{ARR}_0}$$

**K6 · P1 Ticket Resolution Time**

$$\mathrm{TTR}_{P1}(t)=\operatorname{median}\{\,\tau^{\text{resolved}}_i-\tau^{\text{created}}_i \;\big|\; i \in T_t,\ \text{priority}=P1\,\}$$

## 2.2 Connection graph — the composition identity

```
                       K6 ──drives──▶ K2 ──┐
                    (TTR_P1)      (GRR)    │
                                           ├──▶ K1 (Net Revenue)
                       K3 (Expansion) ─────┤
                       K4 (New ARR) ───────┘
                                           
                       K1 + K2 + K3 ──────▶ K5 (NRR)
```

Attribution identity used by decomposition:

$$\Delta \mathrm{NetRev}(t)=\underbrace{\tfrac{1}{12}\Big[\Delta\mathrm{ARR}^{\text{renewed}}+\Delta\mathrm{ARR}^{\text{exp}}+\Delta\mathrm{ARR}^{\text{new}}-\Delta\mathrm{ARR}^{\text{churn}}\Big]}_{\text{recurring}} + \Delta \mathrm{NonRecurring}(t)$$

Residual tolerance ≤ 2% of $|\Delta\mathrm{NetRev}|$, else flagged as a reconciliation break.

## 2.3 Decomposition formulas

Additive contribution over dimension $D$:

$$C_i=\frac{\Delta_i}{\Delta_{\text{total}}},\qquad \sum_i C_i = 1$$

Price–Volume–Mix (three-term):

$$\Delta \mathrm{Rev}=\underbrace{\sum_i (p_{i,1}-p_{i,0})q_{i,0}}_{\text{PRICE}}+\underbrace{\sum_i p_{i,0}(q_{i,1}-q_{i,0})}_{\text{VOLUME}}+\underbrace{\sum_i (p_{i,1}-p_{i,0})(q_{i,1}-q_{i,0})}_{\text{MIX}}$$

Concentration:

$$K(k)=\frac{\sum_{i \in \text{top-}k}|\Delta_i|}{\sum_i |\Delta_i|},\qquad \mathrm{HHI}=\sum_i \Big(\tfrac{\Delta_i}{\Delta_{\text{total}}}\Big)^2$$

## 2.4 Materiality formulas

STL decomposition: $y_t = T_t + S_t + R_t$

Robust z on residuals:

$$z_t=\frac{R_t-\operatorname{median}(R)}{1.4826\cdot \mathrm{MAD}(R)}$$

Material iff:

$$|z_t|>3 \;\wedge\; \text{persistence}\ge 2 \;\wedge\; \frac{|\Delta|}{y_{t-1}}\ge\theta_{\text{rel}} \;\wedge\; |\Delta|\ge\theta_{\text{abs}}$$

Sparse history ($\text{history} < 2\times$ seasonal period) → peer-borrowed baseline:

$$\hat{y}_t=y_{t-1}\Big(1+\operatorname*{median}_{p \in \text{peers}}\tfrac{\Delta_p}{y_{p,t-1}}\Big),\qquad \text{confidence\_ceiling}=\text{Likely}$$

## 2.5 Challenge test formulas

| Test | Formula | Pass |
|---|---|---|
| Timing | $\tau_{\text{effect}}-\tau_{\text{cause}}$, $\tau$ = PELT change-point | $0 \le \Delta\tau \le \text{max\_lag\_days}$ |
| Locality | $J(A,B)=\dfrac{\lvert A\cap B\rvert}{\lvert A\cup B\rvert}$ | $J>0.5$ (refute $<0.2$) |
| Dose | Spearman $\rho_s$(cause intensity, effect magnitude) | $\rho_s>0.5 \wedge n\ge5$ |
| Control | $\delta=(\bar Y^{E}_{post}-\bar Y^{E}_{pre})-(\bar Y^{C}_{post}-\bar Y^{C}_{pre})$ | 95% CI excludes 0 |

---

# 3 · Semantic Contract

One YAML per KPI. Eight elements — the six required plus `composition` and `history_start`.

```yaml
# ── contracts/net_revenue.yaml ─────────────────────────────────────────
id: net_revenue
label: Net Revenue
owner_role: cfo

# [1] DEFINITION
definition: >
  Invoiced revenue net of discounts and credit notes, recognised in the
  fiscal period of the invoice date. Excludes intercompany and test accounts.
unit: INR
direction: up_is_good
grain: [date, account_id, product_id, region]
calendar: fiscal_445

# [2] CALCULATION
formula: SUM(invoice_line.amount_net) - SUM(credit_note.amount)
filters:
  - invoice_line.account_id NOT IN (SELECT account_id FROM account WHERE is_test)
  - invoice_line.currency = 'INR'
refresh: { source: billing, cadence: daily, sla_hours: 26 }

# [+] COMPOSITION  (cross-KPI edges → enables §2.2 attribution)
composition:
  - { kpi: gross_renewal_rate, weight: recurring, transform: arr_over_12 }
  - { kpi: expansion_arr,      weight: recurring, transform: arr_over_12 }
  - { kpi: new_business_arr,   weight: recurring, transform: arr_over_12 }
decomposition_dims: [region, segment, product, account]

# [3] THRESHOLDS
materiality:
  relative: 0.03
  absolute: 2_500_000
  min_persistence: 2
  z_threshold: 3.0
data_quality:
  max_single_record_share: 0.35
  min_completeness: 0.98

# [4] DRIVERS
drivers:
  - id: integration_delay
    type: internal_controllable
    evidence_sources: [tickets, crm_notes, deploy_log]
    max_lag_days: 45
    probe_sql: probes/ticket_spike.sql
    lever: { action: prioritise_integration_fix, owner_role: vp_engineering, lag_days: 14 }
  - id: pricing_change
    type: internal_controllable
    evidence_sources: [price_book, crm_notes]
    max_lag_days: 60
    probe_sql: probes/price_delta.sql
    lever: { action: pricing_review, owner_role: cro, lag_days: 30 }
  - id: competitor_offer
    type: external
    evidence_sources: [crm_lost_reason, news]
    max_lag_days: 90
    probe_sql: probes/lost_reason_scan.sql
    lever: { action: competitive_desk_review, owner_role: vp_sales, lag_days: 7 }
  - id: seasonality
    type: external_uncontrollable
    evidence_sources: [historical_series]
    max_lag_days: 0
    lever: null
  - id: supply_delay
    type: internal_controllable
    evidence_sources: [incident, deploy_log]
    max_lag_days: 30
    lever: { action: fulfilment_escalation, owner_role: vp_ops, lag_days: 10 }

# [5] LINEAGE
lineage:
  upstream:
    - billing.raw_invoice        → billing.invoice          (dedupe, currency norm)
    - billing.invoice            → billing.invoice_line      (explode)
    - billing.raw_credit         → billing.credit_note
    - billing.invoice_line       → metric.net_revenue        (aggregate, §2.1 K1)
  joins:
    - crm.account ON account_id  (region, segment enrichment)
  downstream: [metric.nrr, dashboard.exec_revenue]

# [6] ACCESS RESTRICTIONS
access:
  row:
    region:
      cfo: ["*"]
      cro: ["*"]
      vp_sales: [own_region]
      analyst: [own_region]
      support_lead: [own_region]
  column:
    account_name: [cfo, cro, vp_sales, analyst]
    amount_net:   [cfo, cro, vp_sales, analyst]
    contract_end: [cfo, cro, vp_sales]
  domain:
    segment: { support_lead: [smb, mid_market] }     # enterprise withheld
  masking:
    account_name: hash_alias        # "2 accounts (names restricted)"
    amount_net:   band_1_5_cr       # "₹1–5 Cr"

# [+] HISTORY
history_start: 2023-04-01
seasonal_period_days: 365
```

Remaining five contracts (`gross_renewal_rate`, `expansion_arr`, `new_business_arr`,
`nrr`, `p1_resolution_time`) use the identical schema.
`p1_resolution_time.history_start: 2025-12-01` → triggers the sparse-history path.

**Validation:** Pydantic model `KPIContract`; CI fails on missing element, unknown
`driver.lever.owner_role`, or `lineage` referencing a non-existent table.

---

# 4 · Personas (4)

## 4.1 Definitions

| # | Persona | Role key | Row scope | Column scope | Channel |
|---|---|---|---|---|---|
| P1 | CFO | `cfo` | all regions | all | Morning digest + case view |
| P2 | VP Sales, East | `vp_sales` | `region = East` | all in-scope | Push alert + case view |
| P3 | Revenue Analyst | `analyst` | `region = East` | all except `contract_end` | Case view + full evidence tree |
| P4 | Support Lead | `support_lead` | `region = East`, `segment ∈ {smb, mid_market}` | masked `account_name`, banded `amount_net` | Ticket-queue banner |

## 4.2 Divergent outputs on the same case

| | P1 · CFO | P2 · VP Sales East | P3 · Analyst | P4 · Support Lead |
|---|---|---|---|---|
| **Narrative depth** | Verdict + ₹ + 1 action | Verdict + accounts + weekly plan | Full decomposition tree, all 4 test statistics, every elimination | Signal only |
| **Headline** | "₹2.4 Cr revenue risk, East — integration-driven, Likely" | "ACME + NORTHWIND stalled — integration delays. Act this week." | "88% concentration, n=2, Dose inconclusive → Likely not Confirmed" | "P1 integration backlog is affecting renewals — priority raised" |
| **Recommended action** | Approve engineering reprioritisation; ₹1.8–2.4 Cr recoverable | Contact both account owners by Friday; confirm renewal intent | Validate DiD control matching; log discriminating question | Escalate the 3 open integration tickets to P1 |
| **Owner shown** | VP Sales East + VP Engineering | Self | — | Self |
| **Evidence shown** | 3 top ledger items | 6 ledger items, account-scoped | All 41 ledger items + method labels | 3 ticket IDs only |
| **Entitlement applied** | none | region filter | region filter + column filter | region + segment + mask + band |
| **What P4 literally sees** | — | — | — | "2 accounts (names restricted), ₹1–5 Cr at risk. Redacted: enterprise segment." |

**Rule:** entitlement filters apply to the `Case` object (Step 8a) **before** narration
(Step 8b). Redaction is stated on the page, never silent.

---

# 5 · Multi-Factor KPI Movement (3 seeded scenarios)

## 5.1 Scenario A — multi-factor, known drivers  *(the required one)*

**Injected causal model** (sealed in `ground_truth.json`, readable only by the test suite):

| Event | Scope | Onset | Role |
|---|---|---|---|
| `integration_delay` | accounts `ACME`, `NORTHWIND` | 2026-04-12 | **TRUE CAUSE** |
| `pricing_change` | all 41 enterprise accounts | 2026-03-01 | decoy |
| `competitor_launch` | region `APAC` | 2026-04-20 | decoy |
| `seasonality` | all | continuous | background |

**Propagation** (lagged SCM):

$$
\begin{aligned}
\text{tickets}_a(t) &= \text{base}_a \cdot \big(1 + 3.2\cdot \mathbb{1}[\text{integration\_delay}_a,\, t-\ell],\ \ell\sim U(0,3)\big) \\
\text{csat}_a(t) &= \text{csat}_a(t-1) - \beta_1 \cdot \widetilde{\text{tickets}}_a(t-7) \\
\Pr(\text{renew}_a) &= \sigma\!\big(\alpha - \beta_2 \text{csat}_a - \beta_3 \text{price}\Delta_a - \beta_4 \text{competitor}_a\big),\ \ \ell\sim U(30,60) \\
\text{invoice}_a(t) &= \mathrm{ARR}_a \cdot \mathbb{1}[\text{renew}_a] \quad \text{at contract boundary}
\end{aligned}
$$

**Observed movement:** K1 Net Revenue · East · **−8.0% MoM · −₹2.4 Cr**
Multi-factor: price effect, volume effect and mix effect all non-zero (§2.3 PVM).

**Expected recovery — the test assertion:**

| Stage | Expected |
|---|---|
| Verify | pass (fresh, complete, no drift, no artefact, z = −3.8, persistence 2) |
| Decompose | K2 renewal_rate 88% of Δ; accounts ACME 54% + NORTHWIND 34%; $K(2)=0.88$ |
| PVM | volume-dominant (−₹2.1 Cr), price −₹0.2 Cr, mix −₹0.1 Cr |
| Challenge | `pricing_change` → **Ruled out** (Locality $J=0.05$: hit 41, 39 held) |
| | `competitor_launch` → **Weak** (Locality $J=0$; Timing $\Delta\tau<0$) |
| | `integration_delay` → Timing pass ($\Delta\tau$ = 21 d, 23 d), Locality pass ($J=1.0$), **Dose inconclusive ($n=2$)**, Control pass (DiD $\delta=-₹0.9$ Cr, 6 matched) |
| Adjudicate | **Likely** — not Confirmed, because Dose is inconclusive |
| Open question | "Did the integration delay influence the renewal decision? Ask ACME + NORTHWIND account owners." Value ₹2.1 Cr |

## 5.2 Scenario B — low confidence / abstention

Injected cause: `competitor_offer` on 2 mid-market accounts, with **zero evidence-source
coverage** (absent from `news_item`, unmentioned in `opportunity_note`, no
`lost_reason_code`).
Expected: all four tests `inconclusive` → **Undetermined** + discriminating question
("Request lost-reason detail from the two account owners") + contract gap raised.

## 5.3 Scenario C — sparse history

KPI `p1_resolution_time`, product launched 2025-12-01 → 8 months history < $2\times365$ d.
Expected: peer-borrowed baseline fires, `baseline: borrowed` recorded in the ledger,
`confidence_ceiling = Likely` enforced regardless of test outcomes.

## 5.4 Bonus — not-real changes (Verify gate)

| Injection | Period | Expected |
|---|---|---|
| Refund batch, single credit note = 71% of Δ | 2026-01 | Case closed at Verify · artefact · **0 LLM calls** |
| `formula` changed to exclude discounts | 2025-11 | Case closed at Verify · definition drift · **0 LLM calls** |

## 5.5 Corpus honesty controls

- ~85% of the 45k tickets are irrelevant traffic (password resets, billing queries, feature requests).
- Misleading documents included deliberately: a ticket mentioning the integration that concludes it was fine; a CRM note blaming pricing with no supporting evidence.
- Text corpus generated once, frozen, committed. No generation at demo time.

---

# 6 · Requirement → Artifact Trace

| Requirement | Satisfied by | Location |
|---|---|---|
| 3–5 connected KPIs | 6 KPIs, composition identity §2.2 | `contracts/*.yaml` |
| 2–3 sources, different grains/cadences | 3 sources, 3 grains, 3 cadences §1.1 | `data/generator.py` |
| Contract: definitions | `definition`, `unit`, `grain`, `calendar` | `contracts/net_revenue.yaml` [1] |
| Contract: calculations | `formula`, `filters`, `refresh` | [2] |
| Contract: drivers | `drivers[]` (5 typed, with levers) | [4] |
| Contract: thresholds | `materiality`, `data_quality` | [3] |
| Contract: lineage | `lineage.upstream / joins / downstream` | [5] |
| Contract: access restrictions | `access.row / column / domain / masking` | [6] |
| ≥2 personas, different narratives **and** actions | 4 personas, divergent action column §4.2 | `personas/*.yaml` |
| 1 multi-factor movement, known drivers | Scenario A, 3 injected events §5.1 | `data/ground_truth.json` |
