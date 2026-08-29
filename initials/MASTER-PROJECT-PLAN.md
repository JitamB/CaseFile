# CaseFile — Master Project Plan

**Accenture Innovation Challenge 2026 · Round 2**
**Problem Track 3 — BusinessIntelligence.ai**
**Team Jerry — IIT Kharagpur**
**Members:** Jitam Barman · Sahil Kumar Gupta · Aditya Goyal

> **This is the single source of truth.** It is self-contained. No other document or prior
> conversation is required to understand, build, or present this project.

---

## Contents

**Part I — The Problem** · [1](#1-the-problem-statement) [2](#2-the-real-problem-underneath) [3](#3-what-round-2-requires) [4](#4-key-challenges) [5](#5-objective)
**Part II — The Solution** · [6](#6-the-central-insight) [7](#7-what-casefile-is) [8](#8-the-investigation-process) [9](#9-the-four-verdicts) [10](#10-worked-example) [11](#11-user-flow) [12](#12-how-each-component-answers-the-problem)
**Part III — Architecture** · [13](#13-architecture-decision) [14](#14-the-three-core-artifacts) [15](#15-the-twelve-stages) [16](#16-data-flow) [17](#17-the-llm-boundary) [18](#18-technology-stack) [19](#19-cost-and-latency-budget) [20](#20-repository-structure)
**Part IV — Data** · [21](#21-data-strategy) [22](#22-sources-and-schemas) [23](#23-the-six-kpis) [24](#24-the-generator) [25](#25-seeded-scenarios)
**Part V — Team** · [26](#26-ownership-map) [27](#27-track-a) [28](#28-track-b) [29](#29-track-c) [30](#30-interface-contracts) [31](#31-day-one-protocol)
**Part VI — Execution** · [32](#32-roadmap) [33](#33-first-week-day-by-day) [34](#34-phase-gates)
**Part VII — Quality** · [35](#35-testing-strategy) [36](#36-risks-and-mitigations)
**Part VIII — Outcome** · [37](#37-key-differentiators) [38](#38-evaluation-criteria) [39](#39-final-deliverables) [40](#40-demo-script)

---
---

# PART I — THE PROBLEM

## 1. The Problem Statement

**As given (Round 1):**

> **BusinessIntelligence.ai** — A dashboard can show revenue dropped 8% in a region; it
> rarely explains why or what to do next — that translation still falls to an analyst,
> often taking days. Design a KPI storytelling engine: an AI system that explains in
> natural language what changed in a business metric, identifies likely root causes, and
> recommends next steps. It should use both structured and unstructured data.
>
> Think about:
> - How would the engine separate meaningful change from normal noise?
> - How does it move from correlation to something a business leader can act on?
> - What does it do when the data is genuinely ambiguous?

**As elaborated (Round 2):**

> In practice, most businesses track KPIs across fragmented systems with different refresh
> cadences and granularities, and the "right" explanation for a movement often depends on
> who's asking and what they plan to do about it.

Round 2 sets eight objectives. Design and demonstrate a working prototype that:

1. Detects and prioritises material KPI movements
2. Reconciles data and business context across heterogeneous sources
3. Identifies and ranks explanatory drivers using appropriate analytical methods
4. Generates persona-specific narratives supported by traceable evidence
5. Communicates uncertainty and abstains when evidence is insufficient or contradictory
6. Recommends practical actions grounded in business levers, constraints and decision rights
7. Has a mechanism to learn from analyst and business-user feedback
8. Operates within realistic security, cost, latency and scalability constraints

And it sets one hard constraint that shapes the entire architecture:

> **"The LLM should not be treated as the source of quantitative truth. Teams should
> explicitly demonstrate when they use deterministic logic, SQL, business rules,
> statistics, traditional ML, causal inference, retrieval or LLMs — and why."**

---

## 2. The Real Problem Underneath

The stated problem is that translating a KPI movement into an explanation takes days.

**The common assumption is that those days are spent on analysis. They are not.**
Decomposing an 8% drop by region, channel and SKU takes minutes in any modern BI tool.
The delay comes from three places:

**2.1 The cause is usually not in the warehouse.**
Revenue fell because a competitor ran a promotion, a checkout flow broke, a good rep
resigned, or a shipment was delayed. None of these is a column in a table. Structured data
can localise a change with certainty; it is mute on *why*.

**2.2 The waiting is social.**
The analyst's real work is assembling evidence — pulling release logs, reading support
tickets, and messaging six people who reply when they can. The clock runs on other
people's inboxes, not on query time.

**2.3 Many alarming moves are not real.**
Late-arriving data, a changed metric definition, a refund batch, one large invoice slipping
across a month boundary. Effort spent explaining an artefact is effort spent twice — and
it destroys trust when discovered.

By the time the answer arrives, the window to act has narrowed. Leaders choose between
deciding without evidence and waiting for it.

> **The gap we are closing is not description. It is evidence.**

---

## 3. What Round 2 Requires

### 3.1 Deliverables

| # | Deliverable | Detail |
|---|---|---|
| D1 | **Detailed Business Proposal** | Problem framing, solution design, target users, business case and impact, phased roadmap, key risks with mitigations |
| D2 | **Working Prototype** | Functional demonstration of the core mechanism. Need not be production-grade; proof-of-concept on illustrative data is expected and encouraged |
| D3 | **Public GitHub repository** | Including a prototype demo video and a README |

### 3.2 Minimum prototype expectations (all ten)

| # | Requirement | Our delivery |
|---|---|---|
| R1 | 3–5 connected KPIs across 2–3 sources, different grains/cadences | **6 KPIs, 3 sources, 3 grains, 3 cadences** |
| R2 | Lightweight KPI/semantic contract: definitions, calculations, drivers, thresholds, lineage, access restrictions | **8 elements (6 required + composition + history)** |
| R3 | ≥2 personas receiving different narratives or actions | **4 personas, different actions** |
| R4 | One multi-factor KPI movement with known/simulated drivers | **3 scenarios, 3 injected drivers** |
| R5 | One low-confidence scenario: clarification or abstention | **Scenario B — Undetermined + discriminating question** |
| R6 | One sparse-history or newly-launched KPI scenario | **Scenario C — 8-month history, peer-borrowed baseline** |
| R7 | One role-based security/entitlement scenario | **Persona P4 — row + column + domain filter, masked, banded** |
| R8 | Evidence showing source freshness, analytical method, contribution, confidence, lineage | **Evidence Ledger — every item carries all five** |
| R9 | Clear LLM vs non-LLM processing breakdown | **§17 table + measured, not asserted** |
| R10 | Runtime telemetry: latency, model calls, token usage, estimated cost | **§19, per-stage and per-case** |

---

## 4. Key Challenges

The genuinely hard parts, and where each is solved.

| # | Challenge | Why it's hard | Solved at |
|---|---|---|---|
| C1 | **Meaningful change vs noise** | An 8% move may be seasonal, may be a data artefact, may be real but immaterial | Stage 1 — five-check verification + dual materiality gate |
| C2 | **Correlation → actionable cause** | Many things move together; almost none are causes | Stage 2 (narrow the question) + Stage 5 (four falsification tests) |
| C3 | **Genuine ambiguity** | Systems that always answer will confidently answer wrongly | Stage 6 — four verdicts, abstention is a code path, plus the discriminating question |
| C4 | **Structured + unstructured** | The cause lives in text; the location lives in tables. Joining them at the right scope is the trick | Stage 2 → Stage 4: decomposition-scoped retrieval |
| C5 | **Heterogeneous sources** | Three grains, three cadences, inconsistent definitions | Stage 0 conformance + contract `formula`/`calendar`/`refresh` |
| C6 | **Sparse history** | New products have no seasonal baseline | Stage 1 — peer-borrowed baseline + confidence ceiling |
| C7 | **Trust** | A confidently wrong answer is worse than no answer | Evidence Ledger + deterministic rubric + traceability on every claim |
| C8 | **Role-dependent truth** | The right explanation depends on who's asking | Stage 8a entitlement on the case object, then Stage 8b narration |
| C9 | **LLM economics** | Whole-corpus RAG is expensive and imprecise | Scoped retrieval → ~14k input tokens/case instead of ~200k |

---

## 5. Objective

> Build a system that converts a KPI movement into a **defensible position** — what
> happened, what caused it, how confident we are, what to do, and who owns it — in under
> ten seconds and for under ten rupees, with every claim traceable to a source, and with
> the structural ability to say *"I cannot tell you, and here is exactly what would."*

**Measurable targets:**

| Target | Value |
|---|---|
| Alert → closed case | < 10 seconds |
| Cost per case | < ₹10 (~$0.12) |
| Stages producing numbers without a model | 100% |
| Claims without a traceable source | 0 |
| Analyst time replaced | ~3 days → ~0 |

---
---

# PART II — THE SOLUTION

## 6. The Central Insight

> ### Don't summarise the KPI. Open a case.

An AI that writes a narrative will always produce one — confident, fluent, and
unfalsifiable. That is the failure mode of every "AI explains your dashboard" product: it
cannot return *"I don't know"*, because generating text is the only thing it does.

**CaseFile behaves like an investigator instead.** It establishes facts first, then tests
explanations against them, and is willing to close a case unresolved.

The operating principle, from which everything else follows:

> ### Exhaust the arithmetic before invoking hypotheses.

Revenue fell 8%. We do not ask a model *why*. We first ask *where*. If 88% of the decline
sits in two enterprise renewals, an unanswerable question has become a focused one. Only
then do we test why **those two** renewals stalled.

---

## 7. What CaseFile Is

**In one sentence:** an automatic investigator for business numbers.

**The analogy:** a dashboard is a smoke alarm — it goes off loudly and is then done.
CaseFile is the fire investigator who arrives afterwards, establishes what happened, rules
out the theories that don't hold, and writes the report.

**What it does, in four steps:**

1. **Watches** — connects to systems the company already has: billing, CRM, support
   tickets, release logs.
2. **Checks the change is real** — before anything else: genuine business event, or a data
   glitch, refund batch, or metric-definition change? Many "crises" die here.
3. **Investigates** — narrows down *where* the movement came from using pure arithmetic,
   then gathers evidence around only that narrow slice, lists possible explanations, and
   tries to knock each one down.
4. **Delivers a verdict** — one page: what happened, how confident, what to do, who owns
   it, what's still unresolved.

**What it is not:**
- Not a chatbot. You don't ask it questions; it brings you the case.
- Not a dashboard replacement. Dashboards stay; this is the missing layer after them.
- Not an AI that writes summaries. Those always produce an answer whether one exists or not.

> **The product in one line: an AI analyst that knows when not to pretend it knows.**

---

## 8. The Investigation Process

Every significant KPI movement becomes an investigation with four questions:

| # | Question | What it does |
|---|---|---|
| 01 | **Is it real?** | Is the data fresh and complete? Did the definition change? Is this one refund batch or a timing artefact? |
| 02 | **Where did it come from?** | Break the movement down until contributors are visible. This is arithmetic, so it cannot be wrong. |
| 03 | **Why did it happen?** | Generate competing explanations; test each against evidence — structured and unstructured — *for* and *against*. |
| 04 | **What should we do?** | Recommend an action with an owner — or identify exactly which missing information would settle it. |

**Most systems never ask the first one.**

Operationally this becomes six phases:

```
Trigger → VERIFY → DECOMPOSE → INVESTIGATE → CHALLENGE → DECIDE
```

### The four challenge tests

Correlation is not cause. Every candidate explanation faces four questions a business
leader can follow without statistics:

| Test | Question | Kills a hypothesis when |
|---|---|---|
| **Timing** | Did the cause precede the effect, by a plausible lag? | Cause starts after the effect |
| **Locality** | Does the cause's footprint match the effect's? | *A bug that hit every region cannot explain a drop in one* |
| **Dose** | Where the cause was stronger, was the effect stronger? | No monotonic relationship |
| **Control** | Did comparable segments *without* the cause behave differently? | Unexposed peers moved identically |

The system's job here is **elimination**. A theory that survives falsification is worth far
more than one that merely fits.

---

## 9. The Four Verdicts

Every investigation closes as exactly one of:

| Verdict | Meaning | Rule |
|---|---|---|
| **Confirmed** | Evidence establishes the driver | Control passes **and** ≥2 other tests pass **and** no contradicting evidence |
| **Likely** | Survives elimination; causality not proven | ≥2 tests pass including Timing or Locality; Control inconclusive |
| **Contested** | Multiple explanations survive; evidence conflicts | ≥2 hypotheses at Likely with conflicting evidence |
| **Undetermined** | Evidence insufficient to decide | No hypothesis reaches Likely, or key evidence stale/missing/untestable |

**Confidence ceilings** (applied after scoring; they only ever lower):
- stale source → cap at **Likely**
- borrowed (peer) baseline → cap at **Likely**
- unmodelled driver in play → force **Undetermined** + raise a contract gap

**Undetermined is a success state.** When evidence cannot decide, CaseFile returns the
single question that would settle it, who to ask, and what resolving it is worth.

> A confidently wrong answer is more dangerous than no answer.

---

## 10. Worked Example

This case threads through the whole document.

```
ALERT   Net Revenue · East region · down 8.0% month on month · ₹2.4 Cr
```

**Verify:** billing 4h fresh · complete · no definition change · largest single invoice is
9% of delta (no artefact) · robust z = −3.8, persisted 2 periods · ₹2.4 Cr > ₹25 L
threshold → **case opens**.

**Decompose:**
```
Net Revenue · East · Δ = −₹2.4 Cr
├── by KPI:      renewal_rate −₹2.1 Cr (88%) · expansion −₹0.2 Cr · new −₹0.1 Cr
└── by account:  ACME −₹1.3 Cr (54%) · NORTHWIND −₹0.8 Cr (34%) · 47 others −₹0.3 Cr
                 concentration K(2) = 0.88
FOOTPRINT → accounts {ACME, NORTHWIND}, window 2026-03-01 … 2026-04-30
```

**Investigate & Challenge:**

| Hypothesis | Timing | Locality | Dose | Control | Result |
|---|---|---|---|---|---|
| Pricing increase | pass | **refute** (hit 41 accounts, 39 held steady) | n/a | refute | **Ruled out** |
| Competitor offer | **refute** (APAC onset, after decline began) | **refute** (APAC only) | n/a | inconclusive | **Weak** |
| Integration delay | pass (21d, 23d lag) | pass (J = 1.0) | **inconclusive (n=2)** | pass (DiD −₹0.9 Cr, 6 matched) | **Survives** |

**Decide:**

```
VERDICT       Integration delays likely drove both stalled renewals
CONFIDENCE    Likely — not Confirmed, because Dose is inconclusive at n=2
ACTION        Prioritise integration fix; contact both accounts this week
OWNER         VP Sales, East  (+ VP Engineering for the fix)
RECOVERY      ₹1.8 – 2.4 Cr
MONITORING    renewal_rate · East · weekly; escalate if not recovered in 2 cycles
STILL OPEN    "Did the integration delay influence the renewal decision?
               Ask the ACME and NORTHWIND account owners."  Worth ₹2.1 Cr
```

**The most important line in the whole project is "Likely — not Confirmed."** With two
accounts, the Dose test *cannot* pass. A system that claimed otherwise would be lying, and
ours is built so it structurally cannot.

---

## 11. User Flow

**What a person actually sees.**

### Screen 1 — Case list (the inbox)

```
● Revenue · East          ↓ 8.0%    LIKELY         VP Sales, East      ₹2.4 Cr
● Renewal Rate · Mid-Mkt  ↓ 4.1%    UNDETERMINED   —                   ₹0.9 Cr
● TTR P1 · NewProduct     ↑ 31%     LIKELY ⚠sparse  VP Engineering     —
○ Expansion ARR · APAC    ↑ 6.2%    NOT MATERIAL   (closed, no action)
○ Revenue · West          ↓11.0%    NOT REAL       (refund batch — closed at Verify)
```

### Screen 2 — Case file (the core artifact)

Six blocks: **What moved** · **Where it came from** · **What we tested** · **Verdict &
confidence** · **Do this (action, owner, ₹, by when)** · **Still open**.

### Screen 3 — Evidence drill-down

Click any claim → the actual ticket, CRM note, deploy log, or the SQL that produced the
number, with its method label and freshness.

### Screen 4 — Persona switcher

The same case rendered for CFO / VP Sales / Analyst / Support Lead. Restricted fields shown
as `"2 accounts (names restricted)"`, `"₹1–5 Cr"` — redaction stated, never silent.

### Screen 5 — Telemetry panel

Per case: latency by stage, model calls, tokens, cost, and the share of stages that ran
without a model.

### The daily loop

```
06:00  Refresh cadences fire → movements detected → non-material and not-real cases closed
06:04  Material cases investigated → verdicts written → entitlement-filtered per persona
09:00  CFO opens digest: 2 cases. VP Sales East gets a push: "ACME + NORTHWIND, act this week."
09:15  Analyst opens the same case, sees the full decomposition tree and every eliminated theory
09:20  Analyst marks the verdict → feedback adjusts driver priors for next time
```

---

## 12. How Each Component Answers the Problem

| PS demand | Component | How |
|---|---|---|
| *"explains what changed"* | Stage 2 Decompose | Exact contribution arithmetic, not description |
| *"identifies likely root causes"* | Stages 3–5 | Registry-bounded hypotheses, tested by falsification |
| *"recommends next steps"* | Stage 7 | driver → lever → action → impact → owner → confidence → monitoring |
| *"natural language"* | Stage 8b | Per persona, over already-filtered facts |
| *"structured and unstructured"* | Stage 4 | Tables locate; text explains. Joined at footprint scope |
| *"meaningful change vs noise"* | Stage 1 | Five checks + dual materiality gate + peer baseline for sparse series |
| *"correlation → actionable"* | Stages 2 + 5 | Narrow first, then four elimination tests |
| *"genuinely ambiguous"* | Stage 6 | Four verdicts; Undetermined + discriminating question + owner + value |

---
---

# PART III — ARCHITECTURE

## 13. Architecture Decision

Four approaches were evaluated. **Approach B is chosen.**

| Approach | Verdict | Reason |
|---|---|---|
| **A · LLM agent with tools (ReAct)** | **Rejected as core** | Makes the LLM the source of quantitative truth — the exact thing the brief forbids. Makes the LLM/non-LLM breakdown unanswerable, confidence uncalibratable, telemetry a range not a number, and the demo non-reproducible. *Retained only for optional Phase 5 conversational follow-up over already-closed cases, where facts are fixed.* |
| **B · Deterministic pipeline, typed LLM boundary** | **✅ CHOSEN** | See below |
| **C · Platform-native (Databricks / Snowflake)** | **Deferred, seam preserved** | Unity Catalog row/column masking is genuinely better than anything we'd build — but Round 2 requires a public repo a judge can run, and a cloud dependency mid-demo is risk with no upside. We design the entitlement layer to map 1:1 onto Unity Catalog and say so in the proposal. |
| **D · Knowledge graph / ontology-first** | **Rejected, absorbed** | The hard part is populating the graph, and once populated the causal edges *are* the driver registry — with a graph DB's operational cost attached. We take the typed driver→lever structure as YAML. |
| **E · Semantic-layer-first (dbt/Cube)** | **Absorbed** | Not an architecture — a component. Approach B already contains it as the KPI contract. Referenced as the production path in the proposal; no dependency taken now. |

### Why B wins — five reasons in order of weight

1. **It answers the brief's sharpest instruction structurally, not rhetorically.** Three of
   twelve stages touch a model; none produce a number — and Stage 10 *measures* that rather
   than asserting it.
2. **It is the Round 1 concept compiled.** *Exhaust the arithmetic before invoking
   hypotheses* is the pipeline's execution order, enforced by construction.
3. **Abstention becomes mechanical rather than aspirational.** Undetermined is a rubric over
   a test matrix with confidence ceilings — a code path with tests, not a hoped-for
   behaviour.
4. **It is practical and it deploys.** One process, one file-based engine, no services.
   `git clone && make demo`. Scaling is honest: DuckDB → Snowflake is a connector swap,
   because every quantitative operation is already SQL.
5. **Its weaknesses are recoverable; A's are not.** B's real limitation is a bounded
   hypothesis space — and the `unmodelled` path converts that into the feedback loop's best
   signal.

---

## 14. The Three Core Artifacts

### 14.1 The KPI Semantic Contract

> **Plain terms:** a recipe card for each number the company cares about. What "Net Revenue"
> actually means, who owns it, how fresh the data should be, how big a change has to be
> before anyone should care, and what usually makes it move.

One YAML per KPI. **Executable configuration, not documentation** — the pipeline reads it
at every stage. Full specimen:

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

# [+] COMPOSITION — cross-KPI edges, enables cross-KPI attribution
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
    - billing.raw_invoice  → billing.invoice       (dedupe, currency norm)
    - billing.invoice      → billing.invoice_line  (explode)
    - billing.raw_credit   → billing.credit_note
    - billing.invoice_line → metric.net_revenue    (aggregate)
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
    account_name: hash_alias        # → "2 accounts (names restricted)"
    amount_net:   band_1_5_cr       # → "₹1–5 Cr"

# [+] HISTORY
history_start: 2023-04-01
seasonal_period_days: 365
```

Every Round 2 requirement traces to a field here.

### 14.2 The Evidence Ledger

> **Plain terms:** the evidence bag. Every fact goes into a labelled bag tagged with where
> it came from. **Nothing appears in the final report unless it came out of a bag.**

```python
class EvidenceItem(BaseModel):
    id: str
    claim: str
    kind: Literal["fact", "statistic", "document", "absence"]
    source: Source                # system, record_id, timestamp, url
    method: Literal["sql", "contribution", "stat_test", "did",
                    "retrieval", "llm_extraction"]
    supports:    list[str] = []   # hypothesis ids
    contradicts: list[str] = []
    strength: float               # 0..1
    freshness_hours: float
```

Two fields carry unusual weight:
- **`kind: "absence"`** — *"0 of 12 lost-reason fields name a competitor."* Absence is
  computed and recorded as evidence. This is what makes "Ruled out" defensible.
- **`method`** — every claim carries how it was established. This makes the LLM/non-LLM
  breakdown a property of the data, not a slide.

### 14.3 The Case

> **Plain terms:** the case folder. One investigation, start to finish.

```python
class Case(BaseModel):
    id: str
    trigger: Trigger                     # kpi, period, delta
    verification: VerificationResult     # stage 1
    decomposition: ContributionTree      # stage 2  (contains Footprint)
    hypotheses: list[Hypothesis]         # stage 3
    ledger: list[EvidenceItem]           # stages 1–4
    tests: dict[str, TestMatrix]         # stage 5   keyed by hypothesis id
    verdict: Verdict                     # stage 6
    recommendation: Recommendation|None  # stage 7
    open_question: OpenQuestion|None     # stage 6
    telemetry: Telemetry                 # stage 10
```

---

## 15. The Twelve Stages

`DET` = deterministic code · `LLM` = model call with enforced schemas · `HYB` = both

### Stage 0 · Ingest & Conform — `DET`
> **Plain terms:** getting three departments to speak the same language. Finance keeps
> records by invoice, Sales by deal, Support by ticket — and they disagree on customer names
> and month boundaries.

**In:** three raw sources. **Out:** conformed DuckDB tables sharing `account_id`, `region`,
`product_id`, fiscal calendar; a **watermark** per source.
**How:** entity-alias map + calendar table. Small, committed, not clever.
**Necessary because:** every cross-source claim later depends on a shared key; the watermark
is what Stage 1 checks.

### Stage 1 · Verify — `DET`
> **Plain terms:** checking the patient is actually sick before treating them. Revenue
> "dropping 8%" might just mean yesterday's data hasn't loaded. A surprising number of
> business panics die right here — each saving three days.

**In:** KPI, period, conformed tables, contract. **Out:** `VerificationResult` + open/close.

| Check | Method | Fails when |
|---|---|---|
| Freshness | `now − watermark` vs `sla_hours` | Stale → provisional, cap confidence |
| Completeness | count vs 28-day median by weekday; vintage comparison | Rows still landing |
| Definition drift | hash(formula + grain + calendar + filters) per period; restatement check | Metric changed, not the business |
| Artefacts | single-record dominance > 0.35; refund-batch; period-boundary slippage | One invoice *is* the movement |
| Materiality | STL → robust z (MAD), persistence ≥ 2 **and** relative **and** absolute thresholds | Noise, or real but immaterial |

**Sparse history** (`history < 2 × seasonal period`): borrow baseline from peer segments;
set `confidence_ceiling = Likely`.

**Necessary because:** this is the Round 1 differentiator *and* the cost gate — a failed
case closes with zero model calls.

### Stage 2 · Decompose — `DET` ← **the pivot**
> **Plain terms:** finding which tap is running before asking why the bill is high. "Revenue
> in the East fell 8%" is unanswerable. "88% of it is two accounts" is answerable. This is
> just subtraction, so **it cannot be wrong** — and everything downstream is scoped by it.

**In:** verified movement, `decomposition_dims`, `composition`.
**Out:** `ContributionTree` + **`Footprint`** (entity set + time window).

Three decompositions: **additive contribution** (greedy top-down to 80% or depth 3),
**price·volume·mix**, **cross-KPI attribution** via `composition` edges. Plus
**concentration** `K(k)` and HHI.

**Necessary because:** hypotheses are generated *for this footprint*; retrieval searches
*only these entities in this window*; the four tests compare *this footprint* against each
cause's. Skip it and input tokens grow 10–15×.

### Stage 3 · Hypothesise — `LLM #1`
> **Plain terms:** drawing up the suspect list. One strict rule: every suspect must be
> checkable. No unfalsifiable theories.

**In:** decomposition summary, footprint, registry filtered to drivers with available
evidence sources. **Out:** schema-enforced —

```python
class Hypothesis(BaseModel):
    driver_id: str                  # MUST be in registry, or "unmodelled"
    rationale: str
    testable_with: list[str]        # MUST be non-empty
    expected_signature: Signature
```

**Guardrails:** registry-bounded or flagged `unmodelled` (→ Undetermined + contract gap);
empty `testable_with` cannot win; **no numbers in the output**.

### Stage 4 · Gather Evidence — `HYB`
> **Plain terms:** going door to door. Run the precise numbers; read the tickets and notes —
> but only those about these two accounts in this window. And write down what you *didn't*
> find: "we checked 12 lost-reason fields, none mention a competitor" is a real finding.

**4a Probes — `DET`:** SQL template per driver from the contract. Absence **counted**, with
an explicit denominator.

**4b Scoped retrieval — `DET`:**
```
45,000 docs → filter by footprint (exact, not semantic) → ~200 → BM25 + embedding → top 15
```
Precision up, input tokens down ~10–15×, hallucination surface shrinks.

**4c Extraction — `LLM #2`:** documents → typed evidence claims, schema-forced, each with
`doc_id` and quoted span.

### Stage 5 · Challenge — `DET`
> **Plain terms:** cross-examination. Ice cream sales and drownings both rise in summer.
> Four questions any detective asks — and the point is to knock theories *down*.

| Test | Formula | Pass |
|---|---|---|
| Timing | `τ_effect − τ_cause`, τ = PELT change-point | `0 ≤ Δτ ≤ max_lag_days` |
| Locality | `J(A,B) = |A∩B| / |A∪B|` | `J > 0.5` (refute < 0.2) |
| Dose | Spearman `ρ` (cause intensity, effect magnitude) | `ρ > 0.5` **and n ≥ 5** |
| Control | DiD: `(Ȳᴱ_post − Ȳᴱ_pre) − (Ȳᶜ_post − Ȳᶜ_pre)` | 95% CI excludes 0 |

**The `n ≥ 5` rule on Dose is load-bearing.** Our headline case has two accounts; Dose
*cannot* pass, so the verdict *cannot* be Confirmed.

### Stage 6 · Adjudicate — `DET`
> **Plain terms:** the verdict, scored against a fixed rulebook — not a model's opinion, so
> the same evidence always gives the same answer. And when the answer is "we can't tell," it
> works out the single question that would settle it.

Rubric of §9. Confidence ceilings applied. **Discriminating question:** for each
inconclusive test compute what would resolve it; rank by *(hypotheses separated)* ×
*(value at stake)*; return the top one with the owner from the contract.

### Stage 7 · Recommend — `DET`
> **Plain terms:** the to-do list, with a name on it. A finding nobody owns is a sentence,
> not a decision.

Output shape exactly as the brief specifies:
`driver → controllable lever → action → expected impact → owner → confidence → monitoring plan`
Every field is a contract lookup or arithmetic. **Impact comes from Stage 2, never a model.**

### Stage 8a · Entitle — `DET`
> **Plain terms:** strip out what this person isn't allowed to see — **then** write. The
> wrong order (write, then ask the model to redact) leaks every time.

Row / column / domain filters from `contract.access`, applied **to the `Case` object**.
Restricted values replaced with explicit markers, never silently dropped.

### Stage 8b · Narrate — `LLM #3`
> **Plain terms:** the same facts, written for different readers — genuinely different
> pages, not one paragraph at two lengths.

Per persona, over the already-filtered case. Every sentence cites ledger IDs. Numbers are
**interpolated from the case object**, never generated.

### Stage 9 · Feedback — `DET`
> **Plain terms:** learning from being wrong — numbers you can watch move, not a model
> retrained in the background.

| Signal | Changes | Effect |
|---|---|---|
| correct / wrong driver | driver prior weights per driver per segment | Stage 3 ranking shifts |
| "not material" ×N | `materiality` thresholds for that KPI/owner | Fewer false alarms |
| "missed the real cause" | promotes the `unmodelled` contract gap into the registry | System can now investigate a cause it previously couldn't |

### Stage 10 · Telemetry — `DET`
> **Plain terms:** the receipt. Turns "the model never touches a number" from a claim into
> a measurement.

Per call: model, in/out tokens, latency, cost from a price table, cache hits. Per stage:
wall time. Per case: cost per insight, total latency, share of stages with no model.

---

## 16. Data Flow

```
  billing (daily, invoice-line) ─┐
  crm (24h, opportunity)         ├─▶ S0 CONFORM ─▶ S1 VERIFY ──▶ [CLOSE: not real / not material]
  product_ops (≤15min, event)  ──┘      DET           DET               ↑ zero LLM calls, zero cost
                                                       │
                                                       ▼
                                            S2 DECOMPOSE  DET  ◀── the pivot
                                                       │
                                                       ▼  FOOTPRINT {entities, window, Δ}
                                            S3 HYPOTHESISE  LLM #1
                                                       │
                                     ┌─────────────────┴─────────────────┐
                                     ▼                                   ▼
                            S4a PROBES  DET                    S4b RETRIEVAL  DET
                            (SQL + absence)                    (footprint filter → BM25+emb)
                                     └─────────────────┬─────────────────┘
                                                       ▼
                                            S4c EXTRACT  LLM #2
                                                       │
                                                       ▼
                                            S5 CHALLENGE  DET   (timing·locality·dose·control)
                                                       │
                                                       ▼
                                            S6 ADJUDICATE  DET  (4 verdicts + ceilings + open question)
                                                       │
                                                       ▼
                                            S7 RECOMMEND  DET
                                                       │
                                                       ▼
                                            S8a ENTITLE  DET    ◀── security acts on DATA
                                                       │
                                                       ▼
                                            S8b NARRATE  LLM #3 (per persona)
                                                       │
                          ┌────────────────────────────┴────────────────────────────┐
                          ▼                                                         ▼
                  S9 FEEDBACK  DET                                        S10 TELEMETRY  DET
             (priors · thresholds · registry)                    (tokens · latency · cost · split)
```

---

## 17. The LLM Boundary

**The headline deliverable — R9.**

| Stage | Method | Why this method |
|---|---|---|
| 0 Conform | SQL + alias map | Keys must be exact |
| 1 Verify | SQL + rules + STL/robust-z | Truth about data must be deterministic |
| 2 Decompose | SQL + arithmetic | Contribution is arithmetic; a model can only add error |
| **3 Hypothesise** | **LLM** (registry-constrained) | Generative breadth over a typed space |
| 4a Probe | SQL | Exactness; absence must be counted |
| 4b Retrieve | BM25 + embeddings | Ranking, not judgement |
| **4c Extract** | **LLM** (schema-forced) | Language → structure |
| 5 Challenge | change-point · set overlap · rank corr · DiD | Falsification must be reproducible |
| 6 Adjudicate | rules | Confidence must be auditable |
| 7 Recommend | contract lookup + arithmetic | Impact and owner are facts |
| 8a Entitle | set operations on the case object | Security is not a prompt |
| **8b Narrate** | **LLM** | Language, per persona |
| 9 Feedback | table + multipliers | Learning must be legible |
| 10 Telemetry | instrumentation | Measurement, not assertion |

> **Three of twelve stages touch a model. None of them produce a number.**
> Stage 10 measures this per case rather than asserting it.

---

## 18. Technology Stack

| Layer | Choice | Justification |
|---|---|---|
| Language | **Python 3.11** | Statistical ecosystem; team familiarity |
| Warehouse / store | **DuckDB** | Real SQL, file-based, no service to run, fast at this scale. One engine for warehouse, ledger and case store. Swap to Snowflake/Databricks is a connector change because every quantitative op is already SQL |
| Types & validation | **Pydantic v2** | Contract, hypothesis, evidence, verdict — *and* LLM output-schema enforcement, for free |
| Statistics | **statsmodels + scipy** | STL, change-point, rank correlation, DiD |
| Retrieval | **rank_bm25 + sentence-transformers (`all-MiniLM-L6-v2`)** | Local, free, offline — no API dependency during the demo. Corpus is ~200 docs post-scoping, so numpy cosine beats any vector service |
| API | **FastAPI** | One process |
| UI | **React + Vite** | Reuses the Round 1 deck's design language. *Fallback: Streamlit if P3 arrives under time pressure* |
| Tests | **pytest** | Also hosts the ground-truth evaluation harness |
| LLM | **Provider-agnostic interface** | Provider undecided; see below |

**LLM abstraction** (provider is a one-file swap):

```python
class LLMProvider(Protocol):
    def complete(self, prompt: Prompt, schema: type[BaseModel]) -> tuple[BaseModel, Usage]: ...
```

Every call is schema-enforced. Every call returns `Usage`, which makes Stage 10 a
measurement. Reference implementation targets Claude (`output_config.format`, or tools with
`strict: true`); equivalents exist on other providers.

**Deliberately NOT used** — and this is a design statement, not an omission:

| Rejected | Used instead | Why |
|---|---|---|
| Neo4j / knowledge graph | YAML driver registry + composition edges | Same expressive power at our depth; no service |
| Vector DB (Pinecone/Chroma) | numpy cosine over ~200 scoped docs | A vector service would be *slower* than the array |
| Airflow / Dagster | A Python function on a timer | Twelve stages, one process |
| Kafka / streaming | Watermark-based cadence simulator | We need different *cadences*, which is a watermark |
| LangChain / LangGraph / CrewAI | Plain functions + Pydantic | Linear DAG; a framework adds indirection and version churn |
| Fine-tuning | Prompting + schema enforcement | Nothing here is a style-transfer problem |
| DoWhy / do-calculus | Four tests + DiD | DiD *is* causal inference, and a leader can follow it |
| Kubernetes / microservices | One FastAPI process | Prototype |
| Whole-corpus RAG | Decomposition-scoped retrieval | Better *and* 10–15× cheaper |

---

## 19. Cost and Latency Budget

**Per case: 3 LLM calls, ≈14.5k input / 3.7k output tokens** — small *because* of
decomposition-scoped retrieval.

| Model class | In $/1M | Out $/1M | ≈ per case | ≈ 200 cases/mo |
|---|---|---|---|---|
| Opus-5 class | $5 | $25 | ~$0.17 (₹14) | ~$34 |
| Sonnet-5 class | $2 | $10 | ~$0.066 (₹6) | ~$13 |
| Haiku-4.5 class | $1 | $5 | ~$0.033 (₹3) | ~$7 |

Prompt caching on the stable prefix (system prompt + contract, comfortably over the ~1024
token minimum) reduces the input side further on repeat cases. **Whole-corpus RAG at ~200k
input tokens/case would be 10–15× these figures** — a number worth stating in the proposal.

**Latency budget:**

| Stage | Target |
|---|---|
| Verify + Decompose (DuckDB) | < 1 s |
| Retrieval | < 200 ms |
| 3 LLM calls (2 narratives in parallel) | 3–8 s |
| Challenge tests | < 500 ms |
| **Total alert → case** | **< 10 s** |

*Prices are current first-party API rates; the telemetry module reads a price table, so they
are configuration.*

---

## 20. Repository Structure

```
casefile/
├── README.md                      ← C
├── Makefile                       ← C     (make data | make demo | make test)
├── pyproject.toml                 ← C
│
├── contracts/                     ← A
│   ├── net_revenue.yaml
│   ├── gross_renewal_rate.yaml
│   ├── expansion_arr.yaml
│   ├── new_business_arr.yaml
│   ├── nrr.yaml
│   └── p1_resolution_time.yaml
├── personas/                      ← C
│   ├── cfo.yaml
│   ├── vp_sales.yaml
│   ├── analyst.yaml
│   └── support_lead.yaml
├── probes/                        ← B     (SQL templates per driver)
│
├── src/casefile/
│   ├── models.py                  ← ALL THREE, day 1   ★ the interface contract
│   ├── contract.py                ← A     KPIContract + validator
│   ├── stats/                     ← A     stl, changepoint, did, jaccard, spearman, pvm
│   ├── data/
│   │   ├── generator.py           ← A     SCM + ground truth + corruption
│   │   └── loader.py              ← A     DuckDB, conformance, watermarks
│   ├── engine/
│   │   ├── verify.py              ← A     S1
│   │   ├── decompose.py           ← A     S2
│   │   ├── hypothesise.py         ← B     S3
│   │   ├── evidence.py            ← B     S4a/4c
│   │   ├── challenge.py           ← B     S5  (calls stats/)
│   │   ├── adjudicate.py          ← B     S6
│   │   ├── recommend.py           ← B     S7
│   │   ├── entitle.py             ← C     S8a
│   │   ├── narrate.py             ← C     S8b
│   │   └── feedback.py            ← C     S9
│   ├── retrieval/                 ← B     bm25 + embeddings + footprint scoping
│   ├── llm/                       ← B     provider protocol, schema enforcement, telemetry
│   ├── ledger.py                  ← B
│   ├── orchestrator.py            ← C     runs S0→S8, writes the Case
│   └── api/                       ← C     FastAPI
│
├── ui/                            ← C     React + Vite
├── data/
│   ├── seed.txt                   ← A
│   ├── ground_truth.json          ← A     ★ pipeline forbidden from reading; tests only
│   └── corpus/                    ← B     frozen text, committed
├── fixtures/                      ← ALL   golden Case objects for parallel work
└── tests/                         ← ALL   unit + harness + benchmark + security
```

---
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
circular. We also run it against the **Squeeze / RiskLoc** semi-synthetic sets (A, B0–B4, D)
from NetManAIOps, which carry labelled ground-truth root causes and published F1 scores for
Adtributor, HotSpot, Squeeze and RiskLoc. Costs ~1 day; buys an external, citable number.

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

### What ships in the repo

Generator + fixed seed (reproduces structured tables byte-identically) · the frozen text
corpus as a committed artifact · `ground_truth.json` committed but **the pipeline is
forbidden from reading it — only `tests/` may.**

---

## 25. Seeded Scenarios

| # | Scenario | Requirement | Expected behaviour |
|---|---|---|---|
| **A** | Multi-factor movement — 3 injected events, PVM all non-zero | R4 | Decompose → 88% in 2 accounts; both decoys refuted; `integration_delay` **Likely** (Dose inconclusive at n=2) |
| **B** | Low confidence — true cause is a competitor offer with **zero evidence-source coverage** (absent from news, unmentioned in notes, no lost-reason code) | R5 | All four tests inconclusive → **Undetermined** + discriminating question + contract gap raised |
| **C** | Sparse history — `p1_resolution_time`, product launched 2025-12-01, 8 months < 2×365d | R6 | Peer-borrowed baseline fires; `baseline: borrowed` in ledger; `confidence_ceiling = Likely` enforced regardless of test outcomes |
| **D** | Not-real #1 — refund batch, single credit note = 71% of Δ | bonus | Closed at Verify · artefact · **0 LLM calls** |
| **E** | Not-real #2 — `formula` changed to exclude discounts | bonus | Closed at Verify · definition drift · **0 LLM calls** |
| **F** | Entitlement — Support Lead opens case A | R7 | Region + segment filter, names hashed, ₹ banded, redaction stated on the page |

---
---

# PART V — TEAM

## 26. Ownership Map

Three tracks, split along the architecture's natural seams so the handoff is **linear**
(A → B → C) rather than a ping-pong.

| Track | Name | Owner | Scope |
|---|---|---|---|
| **A** | **Data & Truth** | **Sahil Kumar Gupta** | Everything that produces a number. Contract, generator, loader, statistics library, Verify, Decompose |
| **B** | **Evidence & Reasoning** | **Aditya Goyal** | Everything between a footprint and a verdict. Hypotheses, retrieval, extraction, challenge, adjudication, recommendation, LLM layer |
| **C** | **Surface & Delivery** | **Jitam Barman** | Everything a human touches. Orchestrator, API, entitlement, narration, personas, UI, feedback — plus all three graded deliverables |

> **Swap owners freely if skills point elsewhere — the *tracks* are what matters.** Track A
> is the most statistics-heavy; Track B the most LLM- and retrieval-heavy; Track C the most
> product-, design- and deliverable-heavy. Assign to strengths.

**Shared by all three:** `src/casefile/models.py` (day 1, together), tests for own modules,
the demo script, and the business proposal's technical sections.

---

## 27. Track A — Data & Truth  *(Sahil Kumar Gupta)*

### Primary responsibility
Produce every number in the system, and produce the data the system runs on. **If a figure
appears anywhere in a case, Track A computed it.**

### Modules owned

| Module | Stage | Contents |
|---|---|---|
| `contract.py` + `contracts/*.yaml` | — | `KPIContract` Pydantic model, YAML loader, validator. 6 contracts |
| `data/generator.py` | — | SCM, injected events, propagation, three-grain rendering, corruption, `ground_truth.json` |
| `data/loader.py` | S0 | DuckDB ingest, entity-alias conformance, fiscal calendar, watermarks |
| `stats/` | — | `stl.py`, `changepoint.py` (PELT), `did.py`, `overlap.py` (Jaccard), `correlation.py` (Spearman), `pvm.py`, `robust_z.py` |
| `engine/verify.py` | S1 | Five checks + dual materiality gate + peer-borrowed baseline |
| `engine/decompose.py` | S2 | Additive contribution, PVM, cross-KPI attribution, concentration, **Footprint** |

### Dependencies
- **On C:** `models.py` schemas (day 1, joint). Nothing after that.
- **On B:** none. Track A is the head of the chain and never blocks on anyone.
- **Provides to B:** `VerificationResult`, `ContributionTree`, `Footprint`, and the `stats/`
  library that B's Challenge stage calls.
- **Provides to C:** the loaded DuckDB database and all six contracts.

### Deliverables

| # | Deliverable | Definition of done |
|---|---|---|
| A1 | 6 validated KPI contracts | CI fails on missing element, unknown `lever.owner_role`, or lineage referencing a non-existent table |
| A2 | Generator + sealed ground truth | `make data` reproduces byte-identically from the seed |
| A3 | DuckDB loader + watermarks | All three sources conformed on `account_id`/`region`/`product_id`/calendar |
| A4 | `stats/` library | Every function unit-tested against a hand-computed example |
| A5 | Verify (S1) | Catches scenarios D and E with **zero LLM calls** |
| A6 | Decompose (S2) | Recovers ≥85% concentration on scenario A; cross-KPI residual ≤2% |
| A7 | Squeeze/RiskLoc benchmark run | S2 scored against published Adtributor/HotSpot/Squeeze/RiskLoc F1 on B0-level data |

### Implementation order
```
1. models.py (joint, day 1)
2. contract.py + net_revenue.yaml           → verify: validator rejects a broken contract
3. generator.py — structured only            → verify: 8% East drop is visible in the data
4. loader.py + watermarks                    → verify: three sources join on account_id
5. stats/ library                            → verify: each fn matches a hand-computed value
6. verify.py (S1)                            → verify: scenarios D and E close, 0 LLM calls
7. decompose.py (S2)                         → verify: K(2) = 0.88 on scenario A
8. remaining 5 contracts                     → verify: all 6 validate
9. generator — scenarios B, C, D, E, F       → verify: each triggers its expected path
10. Squeeze benchmark                        → verify: external F1 recorded in README
```

---

## 28. Track B — Evidence & Reasoning  *(Aditya Goyal)*

### Primary responsibility
Take a footprint and turn it into a defended verdict with a recommendation. **Owns the
entire LLM boundary** — and owns proving that the boundary holds.

### Modules owned

| Module | Stage | Contents |
|---|---|---|
| `llm/` | — | `LLMProvider` protocol, schema enforcement, `Usage`, telemetry wrapper, price table, prompt caching |
| `engine/hypothesise.py` | S3 | Registry-constrained generation, `unmodelled` path, guardrails |
| `retrieval/` | S4b | Footprint filter → BM25 + `all-MiniLM-L6-v2` hybrid rank |
| `engine/evidence.py` | S4a/4c | SQL probes, **counted absence**, schema-forced extraction with quote spans |
| `probes/*.sql` | S4a | One template per driver |
| `engine/challenge.py` | S5 | Four tests, calling `stats/`. Returns `TestMatrix` |
| `engine/adjudicate.py` | S6 | Verdict rubric, confidence ceilings, **discriminating question** |
| `engine/recommend.py` | S7 | Contract lever lookup → the seven-field recommendation |
| `ledger.py` | — | Append-only `EvidenceItem` store |
| `data/corpus/` | — | Frozen text generation: tickets, notes, news — with the 85% noise floor and the misleading documents |

### Dependencies
- **On C:** `models.py` (day 1, joint).
- **On A:** `ContributionTree` + `Footprint` (needed to run for real) and `stats/` (for S5).
  **Unblocked from day 1 by `fixtures/decomposition_east.json`** — a hand-written
  `ContributionTree` matching §10. Do not wait for A.
- **Provides to C:** a complete `Case` with verdict, recommendation, ledger, open question,
  telemetry.

### Deliverables

| # | Deliverable | Definition of done |
|---|---|---|
| B1 | LLM provider layer | Provider swap touches one file; every call returns `Usage` |
| B2 | Frozen text corpus | 45k tickets / 9k notes / 200 news items committed; 85% irrelevant; misleading docs present |
| B3 | Hypothesise (S3) | Rejects any driver not in the registry; empty `testable_with` cannot win; **zero numbers in output** |
| B4 | Scoped retrieval | 45k → ~200 → top 15; measured input tokens ≈14.5k, not ≈200k |
| B5 | Evidence + absence | `kind:"absence"` items carry an explicit denominator |
| B6 | Challenge (S5) | Refutes both decoys on scenario A; Dose returns `inconclusive` at n=2 |
| B7 | Adjudicate (S6) | Scenario A → **Likely**. Scenario B → **Undetermined** + correct discriminating question |
| B8 | Recommend (S7) | All seven fields populated from contract + arithmetic; no model-generated number |
| B9 | Telemetry instrumentation | Per-call and per-stage records feeding C's panel |

### Implementation order
```
1. models.py (joint, day 1)
2. llm/ provider + schema enforcement + Usage → verify: a stub provider round-trips a schema
3. corpus generation, frozen                  → verify: 85% noise measured, misleading docs present
4. retrieval/ + footprint scoping             → verify: 45k → ~200 on the East fixture
5. hypothesise.py (S3)                        → verify: an off-registry driver is rejected
6. evidence.py probes + absence               → verify: "0 of 12 lost-reason" is produced
7. evidence.py extraction (4c)                → verify: every claim carries doc_id + span
8. challenge.py (S5) on A's stats/            → verify: both decoys refuted; Dose inconclusive
9. adjudicate.py (S6) + discriminating question → verify: A = Likely, B = Undetermined
10. recommend.py (S7)                         → verify: 7 fields, all traceable
11. telemetry aggregation                     → verify: cost/case < ₹10, LLM/non-LLM split correct
```

---

## 29. Track C — Surface & Delivery  *(Jitam Barman)*

### Primary responsibility
Everything a human touches, and **everything that gets graded**. Also the integration lead:
C owns the orchestrator, so C is where A and B meet.

### Modules owned

| Module | Stage | Contents |
|---|---|---|
| `orchestrator.py` | S0–S8 | Runs the pipeline, writes the `Case`, handles cadence simulation |
| `api/` | — | FastAPI: case list, case detail, persona switch, feedback, telemetry |
| `engine/entitle.py` | S8a | Row / column / domain filters on the `Case` object; masking and banding |
| `engine/narrate.py` + `personas/*.yaml` | S8b | Four persona specs; narration over filtered cases with ledger citations |
| `engine/feedback.py` | S9 | Driver priors, threshold tuning, contract-gap promotion |
| `ui/` | — | Case list · case file · evidence drill-down · persona switcher · telemetry panel |
| Repo & deliverables | — | README, Makefile, business proposal, demo video |

### Dependencies
- **On A and B:** a complete `Case`. **Unblocked from day 1 by
  `fixtures/case_east_8pct.json`** — a hand-written full `Case` matching §10. Build the
  entire UI against it. Do not wait.
- **Provides to A and B:** `models.py` shepherding on day 1, plus the fixtures both tracks
  build against.

### Deliverables

| # | Deliverable | Definition of done |
|---|---|---|
| C1 | `models.py` agreed and frozen | All three tracks import it; changes require all three to agree |
| C2 | Fixtures | `case_east_8pct.json` + `decomposition_east.json` hand-written by end of day 1 |
| C3 | Orchestrator | `make demo` runs alert → case end to end |
| C4 | Entitlement (S8a) | **Security test passes:** restricted fields never appear in any persona's rendered output |
| C5 | 4 personas + narration (S8b) | Each persona's *recommended action* differs, not only the wording |
| C6 | UI, 5 screens | Case list, case file, evidence drill-down, persona switcher, telemetry panel |
| C7 | Feedback (S9) | After 5 marks, driver ranking shifts measurably; a promoted contract gap appears in the registry |
| C8 | README + Makefile | `git clone && make demo` works on a clean machine |
| C9 | Business proposal | Problem framing, solution design, users, business case, roadmap, risks + mitigations |
| C10 | Demo video | ≤ the stated limit; ends with the ground-truth reveal |

### Implementation order
```
1. models.py (joint, day 1) + fixtures      → verify: fixtures validate against the models
2. Repo skeleton, Makefile, pyproject       → verify: `make test` runs on an empty suite
3. entitle.py (S8a) against fixture         → verify: security test passes for all 4 personas
4. personas/*.yaml + narrate.py             → verify: 4 outputs, 4 different actions
5. UI: case file screen (fixture-driven)    → verify: renders §10 exactly
6. UI: case list + evidence drill-down      → verify: every claim links to its source
7. UI: persona switcher                     → verify: P4 shows masked names, banded ₹
8. orchestrator.py — wire A + B             → verify: `make demo` runs end to end
9. UI: telemetry panel                      → verify: cost, latency, LLM/non-LLM split on screen
10. feedback.py (S9)                        → verify: before/after ranking shift
11. README, business proposal, demo video   → verify: clean-machine clone works
```

---

## 30. Interface Contracts

**`models.py` is the treaty.** Nothing crosses a track boundary except these objects.

```
        A ──────────────────▶ B ──────────────────▶ C
   VerificationResult      Case (complete)      Rendered narrative
   ContributionTree         + Verdict            + entitlement applied
   Footprint                + Recommendation     + UI
   stats/ (library)         + EvidenceLedger
   DuckDB + contracts       + OpenQuestion
                            + Telemetry
```

| Boundary | Object | Owner of the schema | Consumer |
|---|---|---|---|
| A → B | `VerificationResult` | A | B (for confidence ceilings) |
| A → B | `ContributionTree`, `Footprint` | A | B (scopes S3, S4, S5) |
| A → B | `stats/*` function signatures | A | B (S5 calls them) |
| B → C | `Case` (fully populated) | joint | C (entitle, narrate, render) |
| B → C | `Telemetry` | B | C (panel) |
| C → A | `KPIContract` shape | A | C reads `access` for S8a |
| C → B | Persona role keys | C | B never sees them (entitlement is C's) |

**Rules:**
1. A schema change requires all three to agree, in the same sitting.
2. No track reaches into another's internals. Only `models.py` types cross.
3. `ground_truth.json` may be read **only** by `tests/`. A lint rule enforces this.
4. Every stage writes to the ledger. No stage mutates another stage's ledger entries.

---

## 31. Day One Protocol

**The single most important half-day of the project.** Do this before anyone writes a
feature.

**Morning — all three in one room:**

1. **Write `src/casefile/models.py` together.** Every Pydantic model in §14 and §30:
   `KPIContract`, `Trigger`, `VerificationResult`, `ContributionTree`, `Footprint`,
   `Hypothesis`, `EvidenceItem`, `Source`, `TestResult`, `TestMatrix`, `Verdict`,
   `Recommendation`, `OpenQuestion`, `Telemetry`, `Case`, `Persona`.
2. **Hand-write two fixtures** from §10:
   - `fixtures/decomposition_east.json` — a `ContributionTree` + `Footprint` (unblocks B)
   - `fixtures/case_east_8pct.json` — a complete `Case` (unblocks C)
3. **Agree the four rules in §30.**

**Afternoon — split.** Everyone now has something to build against and **nobody blocks on
anybody for the rest of the project.**

> Skipping this creates two weeks of integration pain in the last three days. It is
> non-negotiable.

---
---

# PART VI — EXECUTION

## 32. Roadmap

Deadline is open, so phases are ordered by **cut priority: cut from the tail, never the
middle.** Estimates are working days with three people in parallel.

| Phase | Days | Delivers | Gate — done when |
|---|---|---|---|
| **P0 · Foundation** | 3 | `models.py`, fixtures, repo skeleton, contract schema + validator, generator (structured), DuckDB loader | Contract validates; `make data` reproducible; fixtures validate |
| **P1 · Deterministic spine** *(zero LLM)* | 5 | S0, S1, S2, `stats/`, S6 rubric, S10 skeleton, entitlement, case-file UI on fixture | Scenarios D + E close at Verify with **0 LLM calls**; K(2)=0.88 on A; UI renders §10 |
| **P2 · Evidence & challenge** | 7 | LLM layer, frozen corpus, S3, S4a/b/c, S5, S6 full, S7, ledger | Both decoys refuted; A = **Likely**; Dose `inconclusive`; B = **Undetermined** + correct question |
| **P3 · Surface** | 6 | S8a/8b, 4 personas, full UI (5 screens), telemetry panel, orchestrator wired | `make demo` end to end; security test passes; cost + latency on screen |
| **P4 · Learning** | 2 | S9 feedback | After 5 marks, ranking shifts; contract gap promoted |
| **P5 · Optional** | 3 | Conversational follow-up over closed cases; one platform-native seam (Unity Catalog masking) | Only if genuinely spare |
| **P6 · Deliverables** | 4 | README, business proposal, demo video, Squeeze benchmark, clean-machine test | `git clone && make demo` works on a fresh machine |

**Critical path:** P0 → P1 → P2 → P3 → P6. **≈25 working days full · ≈21 without P4/P5.**

> **P1 alone is demoable and already proves the thesis** (verification + decomposition +
> honest verdict, with zero model calls). **If we ship only P1–P3 + P6, the submission is
> complete and honest.** That is the point of this ordering.

### Parallelism by phase

| Phase | A | B | C |
|---|---|---|---|
| P0 | contract, generator, loader | LLM layer, corpus | models.py, fixtures, repo |
| P1 | `stats/`, S1, S2 | retrieval, probes | entitle, case-file UI, personas |
| P2 | scenarios B–F, benchmark | S3, S4, S5, S6, S7 | UI screens 1, 3, 4 |
| P3 | contract polish, tuning | telemetry aggregation | orchestrator, narrate, telemetry panel |
| P4 | — | — | feedback |
| P6 | benchmark writeup | LLM/non-LLM measurement writeup | README, proposal, video |

---

## 33. First Week, Day by Day

| Day | A · Sahil | B · Aditya | C · Jitam |
|---|---|---|---|
| **1 am** | **ALL THREE:** write `models.py`; hand-write both fixtures; agree §30 rules | ← | ← |
| **1 pm** | `contract.py` + `net_revenue.yaml` | `llm/` protocol + stub provider | repo skeleton, Makefile, pyproject |
| **2** | validator; CI check on contracts | schema enforcement + `Usage` | `entitle.py` against `case_east_8pct.json` |
| **3** | `generator.py` — structured, scenario A | corpus generator — tickets | security test: 4 personas, restricted fields never leak |
| **4** | `loader.py` + conformance + watermarks | corpus — notes, news, 85% noise floor | `personas/*.yaml` + `narrate.py` |
| **5** | `stats/`: STL, robust-z, PVM | `retrieval/` — footprint filter + BM25 | UI: case-file screen from fixture |
| **6** | `stats/`: changepoint, Jaccard, Spearman, DiD | embeddings + hybrid rank; measure 45k→200 | UI: case list |
| **7** | `verify.py` (S1) — five checks | `hypothesise.py` (S3) + guardrails | UI: evidence drill-down |

**End of week 1:** A has Verify running, B has scoped retrieval measured, C has three UI
screens rendering a real-looking case. Nobody has waited on anybody.

---

## 34. Phase Gates

A phase is not done until its gate passes. **Do not start the next phase early.**

| Gate | Test | Owner |
|---|---|---|
| **G0** | `make data` byte-identical across two runs; all 6 contracts validate; both fixtures validate against `models.py` | A |
| **G1** | Scenarios D + E close at Verify with `telemetry.model_calls == 0`; scenario A gives `K(2) ≥ 0.85`; cross-KPI residual ≤ 2% | A |
| **G2** | Scenario A: `pricing_change` = Ruled out, `competitor_launch` = Weak, `integration_delay` = **Likely** with `dose == "inconclusive"`. Scenario B = **Undetermined** with the expected discriminating question | B |
| **G3** | `make demo` runs alert→case; security test green for all 4 personas; each persona's *action* differs; telemetry shows cost < ₹10 and latency < 10 s | C |
| **G4** | 5 feedback marks measurably shift driver ranking; one contract gap promoted into a registry | C |
| **G6** | Fresh clone on a clean machine: `make data && make demo && make test` all green | C |

---
---

# PART VII — QUALITY

## 35. Testing Strategy

Five layers. Every one is runnable via `make test`.

### 35.1 Unit tests — *per module, owned by its track*
Every `stats/` function checked against a hand-computed value. Every contract element
validated. Every LLM call schema-round-tripped against a stub provider.

### 35.2 The ground-truth harness — *the headline*
Because we author the data-generating process, we assert recovery:

```python
def test_scenario_a_recovers_injected_driver():
    case = run_pipeline("net_revenue", "East", "2026-04")
    truth = load_sealed_ground_truth()          # tests/ only

    assert case.verification.passed
    assert case.decomposition.concentration(k=2) >= 0.85
    assert set(case.decomposition.footprint.accounts) == set(truth.accounts)

    assert case.tests["pricing_change"].locality   == "refute"
    assert case.tests["competitor_launch"].timing  == "refute"
    assert case.tests["integration_delay"].dose    == "inconclusive"   # n = 2

    assert case.verdict.driver_id  == truth.driver      # integration_delay
    assert case.verdict.confidence == "Likely"          # NOT Confirmed
    assert case.open_question is not None
```

Plus: scenario B → `Undetermined` with the expected question; C → `baseline == "borrowed"`
and ceiling enforced; D and E → closed at Verify with `model_calls == 0`.

### 35.3 External benchmark — *anti-circularity*
Stage 2 run against Squeeze / RiskLoc semi-synthetic sets (A, B0–B4, D). Report F1 alongside
published Adtributor / HotSpot / Squeeze / RiskLoc figures. **This is the one number we do
not self-grade.**

### 35.4 Security test — *non-negotiable*
```python
@pytest.mark.parametrize("persona", ["cfo","vp_sales","analyst","support_lead"])
def test_restricted_fields_never_reach_output(persona):
    rendered = render_case(case_east, persona)
    for field in restricted_fields_for(persona):
        assert field.raw_value not in rendered.text        # narrative
        assert field.raw_value not in rendered.evidence    # drill-down
        assert field.raw_value not in rendered.json        # API payload
```
Entitlement runs on the `Case` object *before* narration. This test is what proves it.

### 35.5 Determinism, budget and regression
- **Determinism:** run the pipeline twice; assert every numeric field is bit-identical. Only
  narrative prose may vary.
- **Budget:** assert `cost_per_case < ₹10` and `latency < 10 s`.
- **Boundary:** assert `model_calls == 3` and no `EvidenceItem` with `method == "llm_*"`
  carries a numeric claim.
- **Golden regression:** `fixtures/case_east_8pct.json` is the expected output. Any diff in a
  numeric field fails CI.

---

## 36. Risks and Mitigations

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| **R1** | *"You made up the data, so of course it works."* | **High** | **High** | Raise it ourselves before a judge does. Answer: the two decoys, the 85% noise floor, the honest `Likely` where a weaker system would claim `Confirmed`, and the external Squeeze benchmark on the stage that matters most |
| **R2** | Integration hell in the final week | High | High | §31 Day One Protocol: `models.py` + fixtures on day 1. Nobody blocks on anybody |
| **R3** | LLM nondeterminism breaks the recorded demo | Medium | High | Frozen corpus, cached responses for the demo path, and a deterministic core — the numbers never move even if the prose does |
| **R4** | Scope creep; nothing finished | Medium | High | Hard phase gates (§34). Cut from the tail. P1–P3 + P6 is already a complete submission |
| **R5** | DiD has no valid control group on a real case | Medium | Low | Test returns `inconclusive`, which caps confidence and generates the discriminating question. **The honest failure is the designed behaviour** |
| **R6** | Bounded hypothesis space misses the true cause | Medium | Medium | `unmodelled` path → Undetermined + contract gap → analyst promotes it. The limitation becomes the feedback loop's best signal |
| **R7** | Judges equate "agentic" with innovation and read us as conservative | Medium | Medium | Lead with the brief's own instruction on quantitative truth; show the measured LLM/non-LLM split; optionally add P5's conversational layer for the wow |
| **R8** | LLM provider/budget unresolved | Medium | Low | Provider sits behind a one-file interface; telemetry reads a price table. Choose before P2 |
| **R9** | UI eats the schedule | Medium | Medium | Streamlit fallback pre-agreed. Decide at end of P2, not before |
| **R10** | Contract authoring feels like manual labour | Low | Low | True of every semantic layer in industry (dbt, LookML, Cube). Frame as realism. ~40 lines per KPI |
| **R11** | Demo machine / network fails on the day | Low | High | Everything runs locally: DuckDB file, local embeddings, cached LLM responses. No cloud dependency on the demo path |

---
---

# PART VIII — OUTCOME

## 37. Key Differentiators

Six, ordered by how memorable they are to a judge.

**1 · It asks "is this real?" first.**
Freshness, completeness, definition drift, single-record artefacts. Most systems begin by
explaining; we begin by checking there is something to explain. This is also the cost gate —
a failed case closes for zero.

**2 · Uncertainty is a first-class output, not a caveat.**
Four verdicts, one of which is *Undetermined* — produced by a rubric, with confidence
ceilings, and always paired with the discriminating question, its owner, and its value. *"I
don't know"* is a code path with tests, not a hoped-for behaviour.

**3 · Decomposition-scoped retrieval.**
Because arithmetic tells us the movement lives in two named accounts in a six-week window,
retrieval filters by entity and date *before* semantic search. Precision up, hallucination
surface down, input tokens down 10–15× (≈14k vs ≈200k). **An architectural consequence of
the core insight, not a bolted-on optimisation.**

**4 · The system rules explanations out.**
Timing, locality, dose, control — four falsification tests a business leader can follow
without statistics. A theory that survives elimination is worth far more than one that
merely fits. And absence of evidence is *computed and recorded*, which is what makes "Ruled
out" defensible.

**5 · The LLM never produces a number — and we measure it.**
Three of twelve stages touch a model. Stage 10 reports the split per case. The brief asks
teams to demonstrate this; we instrument it.

**6 · Security acts on data, not on prose.**
Entitlement filters the `Case` object *before* narration. The same investigation yields four
legitimately different truths, with redaction stated rather than silently applied.

> **The one-line version:** a deterministic pipeline that establishes facts, and calls a
> language model only where language is the actual problem — three times, never for a number.

---

## 38. Evaluation Criteria

### 38.1 Requirement checklist — self-audit before submission

| Req | Evidence | Where |
|---|---|---|
| R1 · 3–5 connected KPIs, 2–3 sources, different grains/cadences | 6 KPIs, 3 sources, 3 grains, 3 cadences; composition identity | §22, §23 |
| R2 · Semantic contract, 6 elements | 8 elements, annotated `[1]`–`[6]` | §14.1 |
| R3 · ≥2 personas, different narratives/actions | 4 personas, **different actions** | §29, C5 |
| R4 · Multi-factor movement, known drivers | Scenario A, 3 injected events | §25 |
| R5 · Low-confidence abstention | Scenario B → Undetermined + question | §25 |
| R6 · Sparse-history KPI | Scenario C → peer baseline + ceiling | §25 |
| R7 · Role-based entitlement | Scenario F → P4 masked + banded | §25 |
| R8 · Evidence: freshness, method, contribution, confidence, lineage | Every `EvidenceItem` carries all five | §14.2 |
| R9 · LLM vs non-LLM breakdown | §17 table + measured per case | §17, §19 |
| R10 · Runtime telemetry | Latency, calls, tokens, cost — per stage and per case | §19 |

### 38.2 What judges will likely weigh

| Criterion | Our answer |
|---|---|
| Innovation / technical novelty | Decomposition-scoped retrieval; falsification-based causal reasoning; abstention as a code path |
| Directness to the PS | Every one of the three PS questions maps to named stages (§12) |
| Trustworthiness | Ledger traceability, deterministic rubric, external benchmark, security test |
| Realism as a product | Runs on a laptop; DuckDB→Snowflake is a connector swap; contract mirrors dbt/LookML practice |
| Business value | 3 days → 10 seconds; ₹6/case; action with an owner and a rupee figure |
| Communicability | Detective analogy; the "88% in two accounts" line; the ground-truth reveal |
| Honesty | The verdict is **Likely, not Confirmed** — and we explain why on stage |

---

## 39. Final Deliverables

| # | Deliverable | Owner | Contents |
|---|---|---|---|
| **D1** | **Business Proposal** | C (with A, B on technical sections) | Problem framing (§1–2) · solution design (§6–17) · target users (§29 personas) · business case: 3 days→10s, ₹6/case, ₹2.4 Cr recovered per case · phased roadmap (§32) · risks + mitigations (§36) · native/configured/custom-built table for the platform question |
| **D2** | **Working Prototype** | all | 6 KPIs, 3 sources, 6 scenarios, 4 personas, 5 UI screens, full telemetry. `git clone && make demo` |
| **D3** | **Public GitHub repo** | C | README with architecture diagram, LLM/non-LLM table, benchmark result, run instructions, screenshots |
| **D4** | **Demo video** | C | §40 |
| **D5** | *(supporting)* Benchmark writeup | A | Squeeze/RiskLoc F1 vs published baselines, in the README |
| **D6** | *(supporting)* LLM/non-LLM measurement | B | Measured split + cost-per-case table, in the README |

---

## 40. Demo Script

Structured so the strongest moment lands last.

| Beat | Content |
|---|---|
| **1 · The problem** | A dashboard says revenue is down 8% in the East. It cannot say why. That translation takes an analyst days — and the days are evidence-gathering, not analysis |
| **2 · The alert** | Case list. Five movements. Two already closed: one *not material*, one **not real** — a refund batch, caught before a single model call. *Most systems would have explained it.* |
| **3 · Is it real?** | Open the East case. Show the five checks passing. Freshness, completeness, no definition drift, no artefact, z = −3.8 |
| **4 · Exhaust the arithmetic** | Decomposition. **88% of the drop sits in two enterprise renewals.** An unanswerable question just became a focused one. No model has been called yet |
| **5 · The suspects** | Three hypotheses, each with a named evidence source |
| **6 · Cross-examination** | Pricing → **Ruled out** (hit 41 accounts, 39 held steady). Competitor → **Weak** (APAC only, and too late). Integration → survives |
| **7 · The honest verdict** | **Likely, not Confirmed** — because with two accounts the Dose test cannot pass. *Pause here.* A system that claimed Confirmed would be lying |
| **8 · The action** | Owner, ₹1.8–2.4 Cr, by Friday, monitoring plan. And the open question: ask the two account owners |
| **9 · Abstention** | Open the mid-market case. **Undetermined** — and here is the single question that would settle it, who owns it, and what it's worth |
| **10 · Four truths** | Persona switcher. CFO, VP Sales, Analyst, Support Lead — same case, different actions, and the Support Lead sees *"2 accounts (names restricted), ₹1–5 Cr"* with the redaction stated |
| **11 · The receipt** | Telemetry: 8.2 s, 3 model calls, 14.5k tokens, ₹6. Three of twelve stages used a model. **None produced a number** |
| **12 · The reveal** | Unseal `ground_truth.json` on screen. *This is what we injected. This is what CaseFile recovered — including correctly refusing to be certain.* |
| **13 · Close** | Dashboards tell businesses what changed. CaseFile tells them what to believe, what to question, and what to do next |

---

## Glossary

| Term | Meaning |
|---|---|
| **Case** | One investigation of one KPI movement, start to finish |
| **Contract** | The YAML per KPI: definition, calculation, drivers, thresholds, lineage, access |
| **Footprint** | The entity set + time window produced by decomposition; scopes everything downstream |
| **Ledger** | Append-only evidence store; every claim in a narrative cites it |
| **Driver** | A typed cause in the contract registry, with a lever and an owner |
| **Lever** | The controllable action a driver maps to |
| **Verdict** | Confirmed / Likely / Contested / Undetermined |
| **Discriminating question** | The single missing fact that would most change the verdict |
| **Contract gap** | An `unmodelled` driver an analyst can promote into the registry |
| **Confidence ceiling** | A cap on verdict strength from stale data or a borrowed baseline |
| **Concentration K(k)** | Share of \|Δ\| in the top-k contributors — the "88%" number |
| **PVM** | Price · Volume · Mix decomposition |
| **DiD** | Difference-in-differences; the Control test |

---

*End of Master Project Plan.*
