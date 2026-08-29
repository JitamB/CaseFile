# CaseFile — Architecture Evaluation & Decision

**Round 2 · Problem Track 3 — BusinessIntelligence.ai · Team Jerry**

Companion to [`casefile-concept-and-process.md`](casefile-concept-and-process.md). That
document settles *what* we are building. This one settles *how*, by evaluating four
genuinely different architectures against the Round 2 brief and recommending one.

---

## 0. Assumptions

Stated up front because several are load-bearing. If one is wrong, the recommendation
moves.

| # | Assumption | Basis | If wrong |
|---|---|---|---|
| A1 | Fully custom, portable core — no platform dependency | Decided | Sections 5C and 9 cover the platform-native fork |
| A2 | Domain is B2B SaaS revenue (enterprise renewals) | Decided; continues the Round 1 narrative | Contract and generator change; pipeline does not |
| A3 | Deadline not fixed — design must degrade gracefully | Decided | Phasing in §10 exists precisely for this |
| A4 | LLM provider undecided — must sit behind an interface | Decided | Cost model in §8 is parameterised, not hard-coded |
| A5 | No real enterprise data; we generate it | Brief explicitly permits and encourages this | — |
| A6 | Judges will run, or at least read, the GitHub repo | Round 2 requires a public repo | Reinforces A1 |
| A7 | The demo video carries more weight than raw feature count | Every hackathon | Reinforces "spine deep, not surface wide" |

**A5 is an opportunity, not a concession.** Because we author the data-generating
process, we know the true cause. That gives us a measurable accuracy claim and an
evaluation harness — see §7.

---

## 1. What the architecture actually has to satisfy

Eight objectives and ten prototype requirements from the brief, collapsed into
architectural forces:

| Force | Where it bites |
|---|---|
| **Determinism where numbers are concerned** | *"The LLM should not be treated as the source of quantitative truth… demonstrate when you use deterministic logic, SQL, business rules, statistics, traditional ML, causal inference, retrieval or LLMs — and why."* |
| **Heterogeneous reconciliation** | 3–5 connected KPIs, 2–3 sources, different grains and refresh cadences |
| **A governed semantic layer** | Definitions, calculations, drivers, thresholds, lineage, access restrictions |
| **Ranked, method-attributed drivers** | Contribution + confidence + method label on every claim |
| **Persona divergence** | ≥2 personas, different narratives *and* different recommended actions |
| **Calibrated abstention** | Must refuse to answer, and say what would resolve it |
| **Sparse history** | A newly launched KPI with no seasonal baseline |
| **Row/column/domain entitlements** | Enforced, not described |
| **Feedback that changes behaviour** | Not a thumbs-up button wired to nothing |
| **Measured runtime economics** | Latency, model calls, tokens, cost per insight |

The single sharpest constraint is the first. It rules out an entire architectural
family before we start — see §5A.

---

## 2. Approach A — LLM agent with tools (ReAct / agentic orchestration)

### Architecture
A single agent loop. Claude (or equivalent) is given tools — `run_sql`,
`search_documents`, `get_schema`, `compute_stats` — a system prompt describing the
investigation method, and the KPI alert. It decides what to call, in what order, and
when it has enough to conclude. Optionally a supervisor/critic agent reviews the case.

### Flow
```
Alert → Agent(system prompt = investigation method)
          ↓ tool_use: get_schema
          ↓ tool_use: run_sql (decomposition, agent-authored)
          ↓ tool_use: search_documents
          ↓ tool_use: run_sql (probe)
          ↓ ... N iterations, agent-decided ...
        → final narrative + verdict
```

### Why anyone would choose it
- Least code to write. The loop is a library call.
- Handles questions we did not anticipate; no driver registry to author.
- Reads as "innovative" to an audience that equates agents with sophistication.
- Genuinely the right answer for open-ended exploratory analysis.

### Why it fails *this* brief
1. **It makes the LLM the source of quantitative truth** — the one thing the brief
   names. The agent authors the SQL, reads the result, and reports the number. Every
   figure in the output passes through a token stream.
2. **The "clear LLM vs non-LLM breakdown" becomes unanswerable.** The honest answer is
   "the LLM decided everything and called some tools," which is precisely the answer the
   brief is testing for.
3. **Confidence cannot be calibrated.** A verdict produced by a model's judgement has no
   reproducible basis. Ours must be defensible to a skeptical CFO.
4. **Ordering is not guaranteed.** Our entire Round 1 thesis is *arithmetic before
   hypotheses*. An agent may reason its way to a cause before decomposing, and nothing
   stops it.
5. **Telemetry is noise.** Token spend varies 5× run to run. "Cost per insight" becomes
   a range, not a number.
6. **The demo is not reproducible.** Same input, different path, occasionally a
   different answer, on video, in front of judges.

### Verdict
**Rejected as the core.** Retained in one narrow place: the *conversational follow-up*
layer in Phase 5, where the user interrogates an already-closed case. There, the facts
are fixed and the agent only navigates them — which is the safe half of the pattern.

---

## 3. Approach B — Deterministic investigation pipeline with a typed LLM boundary

### Architecture
A fixed nine-stage pipeline. Every stage is ordinary code — SQL, arithmetic, statistics,
rules — except three narrow points where an LLM is the only reasonable tool. Those three
points have enforced input and output schemas and are structurally forbidden from
producing numbers.

Two artifacts hold the system together:

**The KPI Semantic Contract** (YAML, one per KPI) — not documentation, but the thing the
code reads:

```yaml
id: net_revenue
label: Net Revenue
owner_role: cfo
formula: SUM(invoice_line.amount_net)
grain: [date, account_id, product_id, region]
calendar: fiscal_445
unit: INR
direction: up_is_good
refresh: { source: billing, cadence: daily, sla_hours: 26 }
composition: [renewal_rate, expansion_arr]        # cross-KPI edges
decomposition_dims: [region, segment, product, account]
materiality: { relative: 0.03, absolute: 2_500_000, min_persistence: 2 }
drivers:
  - id: integration_delay
    type: internal_controllable
    evidence_sources: [tickets, crm_notes, deploy_log]
    max_lag_days: 45
    lever: { action: prioritise_integration_fix, owner_role: vp_engineering, lag_days: 14 }
  - id: competitor_offer
    type: external
    evidence_sources: [crm_lost_reason, news]
    max_lag_days: 90
    lever: { action: competitive_desk_review, owner_role: vp_sales, lag_days: 7 }
lineage: [billing.raw_invoice → billing.invoice_line → metric.net_revenue]
access:
  row:    { region: role_scoped }
  column: { account_name: [cfo, vp_sales], amount_net: [cfo, vp_sales, analyst] }
history_start: 2023-04-01
```

Every Round 2 requirement traces to a field here. Definitions and calculations →
`formula`/`grain`/`calendar`. Thresholds → `materiality`. Drivers and levers → `drivers`.
Lineage → `lineage`. Access restrictions → `access`. Sparse-history detection →
`history_start`. Freshness verification → `refresh.sla_hours`.

**The Evidence Ledger** — an append-only typed record, written by every stage:

```python
EvidenceItem(
  id, claim, kind: fact|statistic|document|absence,
  source: {system, record_id, timestamp, url},
  method: sql|contribution|stat_test|did|retrieval|llm_extraction,
  supports: [hypothesis_id], contradicts: [hypothesis_id],
  strength: float, freshness_hours: float,
)
```

Nothing reaches the narrative without a ledger ID behind it. `kind: absence` is what
makes "Ruled out" and "Weak" defensible — *"0 of 12 lost-reason fields name a
competitor"* is evidence, and it is computed, not asserted.

### End-to-end flow

```
                                   ┌──────────────────────────────────┐
   billing (daily, invoice-line)   │                                  │
   crm     (24h,  opportunity)  ───┤   S0  Ingest + conform + watermark│
   product_ops (stream, event)     │                                  │
                                   └───────────────┬──────────────────┘
                                                   ▼
  ╔═══════════════════════════════ DETERMINISTIC ═══════════════════════════════╗
  ║  S1 VERIFY      freshness · completeness · definition drift · artefacts     ║
  ║                 · anomaly (STL + robust z, persistence) · materiality       ║
  ║                        └─ fails → close case, no LLM call, no cost          ║
  ║                                                                             ║
  ║  S2 DECOMPOSE   additive contribution over dim hierarchy (greedy → 80%)     ║
  ║                 price·volume·mix · cross-KPI attribution · concentration    ║
  ╚═════════════════════════════════════┬═══════════════════════════════════════╝
                                        ▼   footprint = {entities, window, Δ}
  ┌────────────────────────────────── LLM #1 ───────────────────────────────────┐
  │  S3 HYPOTHESISE   registry-constrained; each must name a testable source;   │
  │                   schema-forced output; no numbers; unmodelled → contract gap│
  └────────────────────────────────────┬────────────────────────────────────────┘
                                       ▼
  ┌───────────────── HYBRID ─────────────────┐   ┌────────── LLM #2 ───────────┐
  │  S4a  structured probes (SQL per driver) │   │  S4b  doc → typed evidence  │
  │       negative evidence (counted)        │   │       claim + quote + cite  │
  │       retrieval scoped BY the footprint  │──▶│       schema-forced         │
  └──────────────────────────────────────────┘   └──────────────┬──────────────┘
                                                                ▼
  ╔═══════════════════════════════ DETERMINISTIC ═══════════════════════════════╗
  ║  S5 CHALLENGE   timing (change-point lag) · locality (footprint overlap)    ║
  ║                 dose (rank corr) · control (difference-in-differences)      ║
  ║                 → each returns pass | refute | inconclusive + the statistic ║
  ║                                                                             ║
  ║  S6 ADJUDICATE  rubric over the test matrix → Confirmed/Likely/Contested/   ║
  ║                 Undetermined · confidence ceilings · discriminating question ║
  ║                                                                             ║
  ║  S7 RECOMMEND   driver → lever → action → impact(₹ from S2) → owner →       ║
  ║                 confidence → monitoring plan     (contract lookup + arith.) ║
  ║                                                                             ║
  ║  S8a ENTITLE    row/column/domain filter applied to the CASE OBJECT         ║
  ╚═════════════════════════════════════┬═══════════════════════════════════════╝
                                        ▼
  ┌────────────────────────────────── LLM #3 ───────────────────────────────────┐
  │  S8b NARRATE    per persona, over the already-filtered case; every sentence │
  │                 cites ledger IDs; numbers are interpolated, never generated │
  └────────────────────────────────────┬────────────────────────────────────────┘
                                       ▼
        S9 FEEDBACK  ──▶ driver priors · materiality thresholds · registry growth
        S10 TELEMETRY   model · tokens · latency · cost, per stage, per case
```

### Why each component is necessary

| Stage | Necessary because | What breaks without it |
|---|---|---|
| S0 conform | Three grains and three cadences must share entity keys and a calendar before anything compares | Cross-source claims are meaningless |
| S1 verify | Round 1's core differentiator; also the cost gate — a failed verify closes the case for ₹0 | We explain artefacts; we burn tokens on noise |
| S2 decompose | Converts an unanswerable question into an answerable one; scopes everything downstream | Retrieval has no scope, hypotheses have no footprint, and the four tests have nothing to test |
| S3 hypothesise | Breadth of plausible causes is a genuine language task | Either a hard-coded list (brittle) or an agent (unbounded) |
| S4a probes | Structured tests must be exact and repeatable | Numbers become model output |
| S4b extraction | Text → structure is the one thing only an LLM does well | Unstructured data stays unusable, and the PS requires it |
| S5 challenge | The correlation→cause step, and it must be reproducible | Confidence is vibes |
| S6 adjudicate | Calibration and abstention must be auditable rules | We cannot defend a verdict to a CFO |
| S7 recommend | The brief's exact required shape: driver → lever → action → impact → owner → confidence → monitoring | An insight, not a decision |
| S8a entitle | Security must operate on data, not prose | Redaction by prompt = redaction that leaks |
| S8b narrate | Persona divergence is a language task over fixed facts | Two personas get the same paragraph at different lengths |
| S9 feedback | Explicitly required, and the registry-gap path makes it real | A thumbs-up button wired to nothing |
| S10 telemetry | Explicitly required; also produces our LLM/non-LLM evidence | We would be *claiming* the split instead of *measuring* it |

### The resulting LLM boundary — the headline artifact

| Stage | Method | Why this method |
|---|---|---|
| Verify | SQL + rules + STL/robust-z | Truth about data must be deterministic |
| Decompose | SQL + arithmetic | Contribution is arithmetic; a model can only add error |
| Hypothesise | **LLM** (registry-constrained) | Generative breadth over a typed space |
| Probe / negative evidence | SQL | Exactness; absence must be counted |
| Retrieve | BM25 + embeddings | Ranking, not judgement |
| Extract | **LLM** (schema-forced) | Language → structure |
| Challenge | Change-point, set overlap, rank corr, DiD | Falsification must be reproducible |
| Adjudicate | Rules | Confidence must be auditable |
| Recommend | Contract lookup + arithmetic | Impact and owner are facts |
| Entitle | Set operations on the case object | Security is not a prompt |
| Narrate | **LLM** | Language, per persona |

**Three of eleven stages touch a model. None of them produce a number.** That table is a
slide.

### Trade-offs and limitations — honestly

| Limitation | Severity | Mitigation |
|---|---|---|
| Hypothesis space bounded by the registry | Real | `unmodelled` path routes to Undetermined *and* raises a contract gap the analyst can promote — turning the limitation into the feedback loop's most valuable signal |
| Contract must be hand-authored per KPI | Moderate | True of every semantic layer in the industry (dbt, LookML, Cube). Frame as realism, not debt. ~40 lines per KPI |
| DiD needs a valid control group, often absent | Real | Test returns `inconclusive`, which caps confidence and generates the discriminating question. The honest failure is the designed behaviour |
| Less immediately "agentic" | Perception only | The brief penalises the alternative. And Phase 5 adds a conversational layer over closed cases |
| Rigid pipeline can't answer novel ad-hoc questions | By design | We are not building a copilot. Round 1 established that the bottleneck was never the queries |

---

## 4. Approach C — Platform-native (Databricks / Snowflake / Fabric)

### Architecture
Delta or Snowflake tables; Unity Catalog or Snowflake RBAC for entitlements *and*
lineage; DBSQL/Snowpark for verification and decomposition; MLflow for the statistical
components; platform AI functions or Cortex for narrative; a notebook or app for the UI.

### Genuine strengths
- **Entitlements and lineage stop being a demo and become real.** Unity Catalog row
  filters and column masks are the correct answer to the brief's security requirement,
  and they are configuration rather than code.
- Enterprise credibility with judges from a consulting firm is not a small thing.
- The brief invites exactly this and asks teams to distinguish native / configured /
  custom-built — an invitation to score points.

### Why we are not building on it
- **The repo stops being runnable.** Round 2 requires a public GitHub repository. A
  judge who clones a platform-bound project sees notebooks they cannot execute.
- **Demo fragility.** A cloud dependency in the middle of a recorded demo is a risk with
  no upside.
- **Time goes to plumbing, not to the differentiator.** Workspace setup, catalog
  configuration and credential management consume days that belong to the investigation
  engine.
- **It can read as configuration rather than invention** — the opposite of what a
  hackathon rewards.

### What we take from it anyway
Design the entitlement layer as a **declarative policy on the contract** (`access.row`,
`access.column`) that maps 1:1 onto Unity Catalog row filters and column masks, and say
so explicitly in the business proposal with the native / configured / custom table the
brief asks for. We get the architectural credit without the operational cost.

### Verdict
**Deferred, with the seam preserved.** Revisit only if the timeline turns out generous
(Phase 5, §10).

---

## 5. Approach D — Knowledge-graph / ontology-first

### Architecture
Model the business as a typed graph — metrics, entities, events, and causal edges — in
Neo4j or similar. Investigation becomes traversal: find paths from the moved metric to
candidate causes, score paths by evidence.

### Strengths
- Lineage and cross-KPI composition are native.
- Multi-hop causal chains (integration delay → ticket spike → NPS drop → renewal stall)
  are expressible in a way a flat registry struggles with.
- Sounds impressive.

### Why it loses
- **The hard part is populating the graph, and the honest answer is "by hand."** After
  that work, the causal edges are exactly the driver registry from Approach B — with a
  graph database's operational cost attached.
- Hackathon failure mode: you finish the ontology and run out of time for the product.
- It does not demo. A graph visualisation is pretty and explains nothing in 3 minutes.

### What we take from it
The **typed driver→lever graph inside the YAML contract**, plus the `composition` edges
that let S2 attribute a revenue movement across connected KPIs. That is the 90% of the
value at 5% of the cost. If cross-KPI chains grow past two hops, we revisit.

### Verdict
**Rejected as an architecture, absorbed as a data structure.**

---

## 6. Approach E — Semantic-layer-first (dbt / Cube metrics store)

Build on a metrics layer; everything derives from governed metric definitions.

**This is not an architecture — it is a component**, and Approach B already contains it
as the KPI contract. Adopting dbt wholesale would buy us mature metric definitions and
cost us a build dependency, a compile step, and a modelling paradigm the rest of the
pipeline does not need.

**Verdict: absorbed into B.** We reference dbt/Cube compatibility in the proposal as the
production path for the contract; we do not take the dependency now.

---

## 7. Overengineering audit

Asked at every stage: *can this be simpler without losing meaningful value?* The
deliberate cut list:

| Tempting | We use instead | Reasoning |
|---|---|---|
| Neo4j knowledge graph | YAML driver registry + composition edges | Same expressive power at our depth; no service to run |
| Vector DB (Pinecone/Chroma/Weaviate) | numpy cosine over ~50k docs in memory | Post-decomposition the candidate set is ~200 docs. A vector service would be slower than the array |
| Airflow / Dagster | A Python function on a timer | Ten stages, one process. An orchestrator orchestrates nothing |
| Kafka / streaming ingest | A cadence simulator that reveals rows by watermark | We need *different refresh cadences*, which is a watermark, not a broker |
| LangChain / LangGraph / CrewAI | Plain Python functions + Pydantic | The DAG is linear with one branch. A framework adds indirection and a version-churn dependency |
| Fine-tuning | Prompting + schema enforcement | Nothing here is a style-transfer problem |
| DoWhy / full causal DAG + do-calculus | The four tests + difference-in-differences | DiD *is* causal inference, it is defensible, and a leader can follow it. Formal identification would cost explainability — the thing that made the four tests good |
| Microservices / Kubernetes | One FastAPI process | Prototype |
| RAG over the whole corpus | Retrieval scoped by the decomposition footprint | See below — this is not just simpler, it is *better* |
| A separate critic/supervisor agent | The deterministic rubric in S6 | A rubric is cheaper, faster and auditable |
| Postgres + a warehouse + a cache | DuckDB for all of it | Real SQL, file-based, no service, genuinely fast at this scale |

### The one that is worth a slide: decomposition-scoped retrieval

Conventional RAG-for-BI retrieves against the whole document corpus using a vague query
("why did revenue drop in the East?"). We retrieve only *after* S2 has told us the
movement lives in two named accounts within a 6-week window — so the corpus is filtered
by entity ID and date range **before** semantic search runs.

- **Precision goes up**, because the filter is exact rather than semantic.
- **Input tokens fall roughly 10–15×** (~14k vs ~200k per case).
- **Hallucination surface shrinks**, because the model sees only documents that provably
  concern the entities in question.

This is not a clever optimisation bolted on. It is a direct consequence of the Round 1
insight — *exhaust the arithmetic first* — showing up as an architectural property. That
is the kind of thing judges remember.

---

## 8. The recommended architecture, concretely

**Approach B**, built as follows.

### Data — 3 sources, 3 grains, 3 cadences

| Source | Grain | Cadence | History | Role |
|---|---|---|---|---|
| `billing` | invoice line | daily, 26h SLA | 3 years | Revenue truth; refunds, credits, contract terms |
| `crm` | opportunity / account | 24h batch | 3 years | Renewals, stage, ARR, `lost_reason`, owner, **free-text notes** |
| `product_ops` | event / document | near-real-time | 8 months | Support tickets, deploy & incident logs, competitor news feed |

`product_ops`' short history is deliberate: it is what creates the **sparse-history
scenario** honestly rather than by contrivance.

### KPIs — 5, genuinely connected

```
        Net Revenue
        ├── Renewal Rate        (crm)            ← composition edge
        ├── Expansion ARR       (crm + billing)  ← composition edge
        └── New Business ARR    (crm + billing)
    NRR (billing + crm)                          ← cross-source
    P1 Ticket Resolution Time (product_ops)      ← driver-side, sparse history
```

"Connected" means S2 can attribute a Net Revenue movement *across KPIs* — how much of
the drop is renewal-rate versus expansion — not merely slice one metric by dimensions.

### Personas — 2, plus an entitlement case

- **CFO** — sees every region and column. Wants: verdict, ₹ at stake, action, owner, what
  is still open. One screen.
- **VP Sales, East** — row-scoped to East; sees account names in their book. Wants: which
  accounts, what to do this week, which of it is theirs to act on.
- **Support Lead** (entitlement scenario) — opens the same case, receives account names
  masked and ₹ banded, with the redaction stated rather than silently applied.

Same investigation, three legitimately different truths. The filter runs on the **case
object**, before rendering — which is both the correct security architecture and the
clearest way to demonstrate it.

### Statistical methods, named

| Where | Method | Notes |
|---|---|---|
| Anomaly | STL residual + robust z (MAD), persistence ≥ 2 periods | Not a bare z-score; seasonality is decomposed out first |
| Sparse history | Peer-borrowed baseline from sibling segments | Fires when `history < 2 × seasonal period`; **caps confidence at Likely** and says so |
| Decomposition | Additive contribution; price·volume·mix; cross-KPI attribution | Greedy top-down to 80% cumulative or depth 3 |
| Timing | Change-point on both series; lag within `driver.max_lag_days` | |
| Locality | Jaccard overlap of cause and effect footprints | pass > 0.5, refute < 0.2 |
| Dose | Spearman ρ across exposed segments | **inconclusive when n < 5** — with two accounts it must say so |
| Control | Difference-in-differences vs matched unexposed segments | Our causal-inference component; matched on size, segment, prior trend |

The `dose` rule matters more than it looks. In our own headline example there are two
accounts, so dose *cannot* pass — and a system that claimed it did would be lying. The
demo shows the test returning `inconclusive`, and the verdict landing at Likely rather
than Confirmed as a result. That is the product's thesis, executing.

### Stack

```
Python 3.11
DuckDB                    warehouse, ledger, case store — one engine, no service
Pydantic v2               contract, hypothesis, evidence, verdict — and LLM schema enforcement
statsmodels + scipy       STL, change-point, rank correlation, DiD
rank_bm25 + sentence-transformers (all-MiniLM-L6-v2)   hybrid retrieval, local, free, offline
FastAPI                   one process
React + Vite              reusing the Round 1 deck's design tokens
pytest                    the evaluation harness (§9)
```

**LLM behind a provider interface**, since the provider is undecided:

```python
class LLMProvider(Protocol):
    def complete(self, prompt: Prompt, schema: type[BaseModel]) -> tuple[BaseModel, Usage]: ...
```

Every call is schema-enforced (Claude: `output_config.format`, or tool definitions with
`strict: true`; equivalents exist on other providers). Every call returns `Usage`, which
is what makes S10 a measurement rather than an estimate. Swapping providers touches one
file.

### Cost and latency — estimated, to be replaced by measurement

Per case: 3 LLM calls, ≈14.5k input / 3.7k output tokens (small *because* of
decomposition-scoped retrieval).

| Model | Input $/1M | Output $/1M | ≈ Cost / case | ≈ 200 cases / month |
|---|---|---|---|---|
| Claude Opus 5 | $5 | $25 | ~$0.17 | ~$34 |
| Claude Sonnet 5 | $2 | $10 | ~$0.066 | ~$13 |
| Claude Haiku 4.5 | $1 | $5 | ~$0.033 | ~$7 |

Prompt caching on the stable prefix (system prompt + contract, comfortably over the ~1024
token minimum) cuts the input side further on repeat cases. Whole-corpus RAG at ~200k
input tokens per case would be roughly 10–15× these figures — a number worth stating
plainly in the proposal.

Latency budget per case: verify + decompose < 1s (DuckDB), retrieval < 200ms, three LLM
calls ~3–8s with the two persona narratives issued in parallel, challenge tests < 500ms.
**Target: under 10 seconds, alert to case.** Reported per stage by S10.

*(Model IDs and prices above are Anthropic first-party rates as of this writing; the
telemetry module reads a price table, so they are configuration.)*

---

## 9. The evaluation harness — why A5 is an advantage

Because we author the data generator, we inject the true causal process and then hide it:

```
generator.py  →  emits billing/crm/product_ops  +  ground_truth.json (sealed)
                 ground_truth: {driver: integration_delay,
                                accounts: [ACME, NORTHWIND],
                                onset: 2026-04-12,
                                decoys: [pricing_change, competitor_offer]}
```

Then we measure, in `pytest`:

- Does S1 catch the injected refund-batch artefact and the injected definition change?
- Does S2 recover ≥ 85% concentration in the injected accounts?
- Does S5 refute both decoys?
- Does S6 land on the true driver at Likely — and *not* at Confirmed, given dose is
  inconclusive?
- Does the low-evidence scenario return Undetermined with the correct discriminating
  question?

This gives us three things the brief asks for and most teams will only assert:
**continuous evaluation**, a **defensible accuracy claim**, and a regression suite.

It also gives the demo its strongest moment: run the investigation, show the verdict,
then reveal the sealed ground truth on screen. The system becomes falsifiable in front
of the judges — which is, precisely, the product's argument about itself.

---

## 10. Phasing — spine first, cut from the tail

Since the deadline is open, every phase ends at something demonstrable. Cut from the
bottom, never the middle.

| Phase | Delivers | Verify by |
|---|---|---|
| **P0 · Foundation** | Contract schema + validator; DuckDB loader; generator with sealed ground truth | Contract validates; generator's injected driver is recoverable by hand |
| **P1 · Deterministic spine** *(zero LLM)* | S0–S2 + S6 rubric + S10 | On the seeded 8% drop: artefact and definition-drift caught; ≥85% concentration recovered. **Demoable on its own, and already proves the thesis** |
| **P2 · Evidence & challenge** | S3, S4, S5; ledger; verdicts | Both decoys refuted; true driver at Likely; dose correctly `inconclusive` |
| **P3 · Surface** | S7, S8a/b; 2 personas + redacted third; telemetry view; UI | Same case renders three ways; restricted role sees masked output; per-case cost and latency displayed |
| **P4 · Learning** | S9 — driver priors, threshold tuning, registry growth from contract gaps | After 5 feedback marks, ranking shifts measurably; a promoted unmodelled driver appears in the registry |
| **P5 · Optional** | Conversational follow-up over closed cases; one platform-native seam (Unity Catalog masking) | Only if time is genuinely spare |

Required scenarios are designed into the generator from P0, so they arrive with the data
rather than being retrofitted: multi-factor movement, low-confidence abstention,
sparse-history KPI, role-based entitlement.

If we finish only P1–P3, we have a complete, honest submission. That is the point of
ordering it this way.

---

## 11. Recommendation

**Build Approach B: a deterministic investigation pipeline with a typed, three-point LLM
boundary, driven by a YAML KPI semantic contract and recorded in an evidence ledger.**

Five reasons, in order of weight:

1. **It answers the brief's sharpest instruction structurally, not rhetorically.** The
   brief demands we show which processing is deterministic and which is LLM, and why.
   Approach A cannot answer it. B answers it with a table where three of eleven stages
   touch a model and none of them produce a number — and S10 *measures* that claim
   rather than asserting it.

2. **It is the Round 1 concept compiled.** *Exhaust the arithmetic before invoking
   hypotheses* is not a slogan we bolt onto an agent; it is the pipeline's execution
   order, enforced by construction. Judges who saw Round 1 will see the same idea, now
   running.

3. **Abstention becomes mechanical rather than aspirational.** Undetermined is produced
   by a rubric over a test matrix, with confidence ceilings from stale sources and
   borrowed baselines. In an agent architecture, "I don't know" is a behaviour you hope
   for; here it is a code path with tests.

4. **It is practical and it deploys.** One process, one file-based engine, no services,
   `git clone && make demo`. Judges can run it. It survives a hotel wifi demo. And the
   scaling story is honest: DuckDB → Snowflake/Databricks is a connector swap, because
   every quantitative operation is already SQL.

5. **Its weaknesses are recoverable; A's are not.** B's real limitation is a bounded
   hypothesis space — and the `unmodelled` path converts that into the feedback loop's
   best signal. A's limitation is that the model is the source of truth, which is the
   thing the brief is explicitly testing for, and no amount of prompting fixes it.

**What we keep from the alternatives:** the driver→lever graph from D (as YAML, not
Neo4j); the declarative entitlement policy from C (mapping onto Unity Catalog, not built
on it); metric-contract discipline from E (as our own contract, not dbt); and A's agent
loop confined to Phase 5, over cases that are already closed.

### The one-line version

> A deterministic pipeline that establishes facts, and calls a language model only where
> language is the actual problem — three times, never for a number.

---

## 12. Open items

1. **Frontend depth.** React + Vite reusing the deck's design language is the
   recommendation; Streamlit is the de-risking fallback if P3 arrives under time
   pressure. Decide at the end of P2, not before.
2. **Provider selection.** Design proceeds behind the interface. Choose before P2, since
   schema-enforcement mechanics differ slightly across providers.
3. **Whether P5's conversational layer ships.** It is the highest-wow, lowest-necessity
   item on the list. Decide only once P4 is done.
