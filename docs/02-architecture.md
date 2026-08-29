# Architecture

**CaseFile** · Accenture Innovation Challenge 2026 · Problem Track 3 — BusinessIntelligence.ai · Team Jerry

`Part III · §13–20`

[← Problem & Solution](01-problem-and-solution.md) · [Index](README.md) · [Data →](03-data.md)

---

# PART III — ARCHITECTURE

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

# [+] DEFINITION EPOCHS — the formula's history; Verify recomputes boundary
#     periods under adjacent epochs to separate drift from business
epochs:
  - { effective_from: 2023-04-01, formula: "SUM(invoice_line.amount_net)" }
  - { effective_from: 2025-11-01, formula: "SUM(invoice_line.amount_net) - SUM(credit_note.amount)" }

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
    lever: { action: prioritise_integration_fix, owner_role: vp_engineering,
             lag_days: 14, save_rate: [0.75, 1.00] }
  - id: pricing_change
    type: internal_controllable
    evidence_sources: [price_book, crm_notes]
    max_lag_days: 60
    probe_sql: probes/price_delta.sql
    lever: { action: pricing_review, owner_role: cro, lag_days: 30, save_rate: [0.30, 0.60] }
  - id: competitor_offer
    type: external
    evidence_sources: [crm_lost_reason, news]
    max_lag_days: 90
    probe_sql: probes/lost_reason_scan.sql
    lever: { action: competitive_desk_review, owner_role: vp_sales,
             lag_days: 7, save_rate: [0.20, 0.50] }
  - id: seasonality
    type: external_uncontrollable
    evidence_sources: [historical_series]
    max_lag_days: 0
    lever: null
  - id: supply_delay
    type: internal_controllable
    evidence_sources: [incident, deploy_log]
    max_lag_days: 30
    lever: { action: fulfilment_escalation, owner_role: vp_ops, lag_days: 10, save_rate: [0.50, 0.80] }

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
    outcome: Literal["found", "checked_absent", "uncheckable"]
    source: Source                # system, record_id, timestamp, url
    method: Literal["sql", "contribution", "stat_test", "did",
                    "retrieval", "llm_extraction"]
    supports:    list[str] = []   # hypothesis ids
    contradicts: list[str] = []
    strength: float               # 0..1
    freshness_hours: float
    denominator: int | None = None    # absence: how many records were checked
    coverage: float | None = None     # share of the footprint the source covers
```

Three fields carry unusual weight:
- **`outcome`** — every probe lands as one of three things. **found**;
  **checked_absent** (*"0 of 12 populated lost-reason fields name a competitor"* — the
  denominator is stated, and this is evidence *against*); or **uncheckable** (the source
  has no coverage of this footprint in this window — no evidence either way). The
  distinction is load-bearing: checked-absent refutes, uncheckable caps confidence.
  Evidence of absence is not absence of evidence, and the ledger records which one it has.
- **`kind: "absence"`** with its `denominator` and `coverage` is what makes "Eliminated"
  defensible — absence is computed, never asserted.
- **`method`** — every claim carries how it was established. This makes the LLM/non-LLM
  breakdown a property of the data, not a slide.

### 14.3 The Case

> **Plain terms:** the case folder. One investigation, start to finish. The verdict inside
> it **ranks drivers rather than crowning one** — a decoy that measurably contributed
> keeps its arithmetic share even when eliminated as the primary explanation.

```python
class Attribution(BaseModel):
    driver_id: str
    share: float | None                  # deterministic share of Δ (S2 / PVM), when computable
    status: Literal["primary", "minor", "eliminated", "unresolved"]
    eliminated_by: str | None            # test id, when status == "eliminated"

class Verdict(BaseModel):
    attribution: list[Attribution]       # ranked; one primary unless Contested/Undetermined
    confidence: Literal["confirmed", "likely", "contested", "undetermined"]

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
    priority: float                      # |Δ at stake| × confidence weight — orders the case list
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
| Definition drift | recompute the boundary period under adjacent contract `epochs`; a step that vanishes under a consistent definition is drift | Metric changed, not the business |
| Artefacts | single-record dominance > 0.35; refund-batch; period-boundary slippage | One invoice *is* the movement |
| Materiality | STL → robust z (MAD), persistence ≥ 2 **and** relative **and** absolute thresholds | Noise, or real but immaterial |

**Sparse history** (`history < 2 × seasonal period`): borrow baseline from peer segments;
set `confidence_ceiling = Likely`.

**Provisional cases:** a stale source marks the case provisional and caps confidence. When
the awaited watermark lands, the orchestrator re-runs the case — the ceiling lifts and the
verdict re-adjudicates. Heterogeneous cadences are a visible behaviour, not just metadata.

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

### Stage 3 · Hypothesise — `HYB` (LLM #1)
> **Plain terms:** drawing up the suspect list. The registry names the suspects; the model
> writes the brief on each and may flag one the registry doesn't know. It can add a note
> to the file — it can never decide who gets investigated.

**Enumeration — `DET`:** every registry driver whose `evidence_sources` cover the
footprint becomes a hypothesis, always. The tested set is a function of the contract and
the footprint — identical across runs, never at the mercy of a model omission.

**Annotation — `LLM #1`:** over the enumerated set, schema-enforced —

```python
class Hypothesis(BaseModel):
    driver_id: str                  # from the registry enumeration, or "unmodelled"
    rationale: str
    priority: int                   # presentation order only — never gates testing
    expected_signature: Signature
```

**Guardrails:** the model may *add* exactly one thing — an `unmodelled` flag ("this
movement fits no registry driver" → Undetermined + contract gap). It cannot remove or
skip an enumerated hypothesis, and **no numbers in the output**.

### Stage 4 · Gather Evidence — `HYB`
> **Plain terms:** going door to door. Run the precise numbers; read the tickets and notes —
> but only those about these two accounts in this window. And write down what you *didn't*
> find: "we checked 12 lost-reason fields, none mention a competitor" is a real finding.

**4a Probes — `DET`:** SQL template per driver from the contract. Every probe returns one
of three outcomes: **found** · **checked-absent** (fields populated, denominator stated,
nothing matched — evidence *against*) · **uncheckable** (the source has no coverage of
this footprint in this window — no evidence either way). Checked-absent refutes;
uncheckable caps confidence and, at coverage ≈ 0 across a hypothesis's sources, drives
Undetermined.

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
| Timing | `τ_effect − τ_cause` · τ = event date for a discrete-event footprint (a renewal's onset *is* its date); PELT change-point for continuous series (tickets) | `0 ≤ Δτ ≤ max_lag_days` |
| Locality | `J(A,B) = |A∩B| / |A∪B|` | `J > 0.5` (refute < 0.2) |
| Dose | Spearman `ρ` (cause intensity, effect magnitude) | `ρ > 0.5` **and n ≥ 5** |
| Control | DiD: `(Ȳᴱ_post − Ȳᴱ_pre) − (Ȳᶜ_post − Ȳᶜ_pre)` | **placebo rank** — real effect more extreme than every placebo (treatment reassigned to each matched control in turn) |

**The `n ≥ 5` rule on Dose is load-bearing.** Our headline case has two accounts; Dose
*cannot* pass, so the verdict *cannot* be Confirmed.

**Control uses placebo inference, not a classical CI** — with two treated accounts an
interval estimate would be indefensible, and that is the same small-`n` honesty that makes
Dose inconclusive. Reassigning the treatment to each matched control and ranking the real
effect against the placebos is the standard few-treated approach, and it reads in one
sentence: *"the true effect is larger than all six pretend ones."*

### Stage 6 · Adjudicate — `DET`
> **Plain terms:** the verdict, scored against a fixed rulebook — not a model's opinion, so
> the same evidence always gives the same answer. And when the answer is "we can't tell," it
> works out the single question that would settle it.

Rubric of §9, over the ranked attribution — the primary driver is named, minor
contributors keep their deterministic shares, eliminated hypotheses carry the test that
killed them. Confidence ceilings applied. **Case priority** = |Δ at stake| × confidence
weight — it orders the case list. **Discriminating question:** for each inconclusive test
compute what would resolve it; rank by *(hypotheses separated)* × *(value at stake)*;
return the top one with the owner from the contract.

### Stage 7 · Recommend — `DET`
> **Plain terms:** the to-do list, with a name on it. A finding nobody owns is a sentence,
> not a decision.

Output shape exactly as the brief specifies:
`driver → controllable lever → action → expected impact → owner → confidence → monitoring plan`
Every field is a contract lookup or arithmetic. **Impact = value at risk (Stage 2) × the
lever's declared `save_rate` band** — a measured number times a stated assumption, and the
case labels it as exactly that. Never a model.

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
| correct / wrong driver | driver prior weights per driver per segment | Evidence-gathering depth (full retrieval + extraction vs probe-only) and presentation order shift. The verdict rubric itself never moves — learning is legible, adjudication stays deterministic |
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
                                            S3 HYPOTHESISE  HYB
                                            (registry enumerates · LLM #1 annotates)
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
| **3 Hypothesise** | Registry enumeration + **LLM** annotation | The tested set is deterministic; the model adds rationale, signatures and the `unmodelled` flag — never the list |
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

> **Three of twelve stages touch a model. None of them produce a number — and none
> decides what gets tested.** Stage 10 measures this per case rather than asserting it.

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

**Per case, close path: 3 LLM calls, ≈14.5k input / 3.7k output tokens** — small
*because* of decomposition-scoped retrieval. The three calls are hypothesis annotation,
extraction, and one narration for the case owner's persona; additional persona views
narrate on demand and are cached, and telemetry reports both figures separately.

| Model class | In $/1M | Out $/1M | ≈ per case | ≈ 200 cases/mo |
|---|---|---|---|---|
| Opus class | $5 | $25 | ~$0.17 (₹14) | ~$34 |
| Sonnet class | $3 | $15 | ~$0.10 (₹8) | ~$20 |
| Haiku class | $1 | $5 | ~$0.033 (₹3) | ~$7 |

Prompt caching on the stable prefix (system prompt + contract, comfortably over the ~1024
token minimum) reduces the input side further on repeat cases. **Whole-corpus RAG at ~200k
input tokens/case would be 10–15× these figures** — a number worth stating in the proposal.

**Latency budget:**

| Stage | Target |
|---|---|
| Verify + Decompose (DuckDB) | < 1 s |
| Retrieval | < 200 ms |
| 3 LLM calls (close path) | 3–8 s |
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
│   ├── stats/                     ← A     stl, changepoint, did (+ placebo rank), jaccard, spearman, pvm
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

[← Problem & Solution](01-problem-and-solution.md) · [Index](README.md) · [Data →](03-data.md)
