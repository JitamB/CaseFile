<div align="center">

# CaseFile

### An AI that *investigates* business numbers instead of narrating them.

**Accenture Innovation Challenge 2026 · Round 2**</br>
**Problem Track 3 — BusinessIntelligence.ai**</br>
**Team Jerry · IIT Kharagpur**</br>

*A deterministic pipeline that establishes facts, and calls a language model only where
language is the actual problem — three times, never for a number.*

</div>

---

## The problem

> A dashboard can show revenue dropped 8% in a region; it rarely explains why or what to do
> next — that translation still falls to an analyst, often taking days.

The common assumption is that those days are spent on analysis. **They are not.**
Decomposing an 8% drop by region, channel and SKU takes minutes in any modern BI tool. The
delay comes from somewhere else:

| | |
|---|---|
| **The cause is usually not in the warehouse** | Revenue fell because a competitor ran a promotion, a checkout flow broke, a good rep resigned, or a shipment was delayed. None of these is a column in a table. Structured data can localise a change with certainty; it is mute on *why*. |
| **The waiting is social** | The analyst's real work is assembling evidence — pulling release logs, reading support tickets, messaging six people who reply when they can. The clock runs on other people's inboxes, not on query time. |
| **Many alarming moves are not real** | Late-arriving data, a changed metric definition, a refund batch, one large invoice slipping across a month boundary. Effort spent explaining an artefact is spent twice — and it destroys trust when discovered. |

> ### The gap we close is not description. It is evidence.

---

## The insight

> ## Don't summarise the KPI. Open a case.

An AI that writes a narrative will always produce one — confident, fluent, and
unfalsifiable. That is the failure mode of every *"AI explains your dashboard"* product: it
cannot return **"I don't know"**, because generating text is the only thing it does.

CaseFile behaves like an investigator instead. It establishes facts first, tests
explanations against them, and is willing to close a case unresolved. The operating
principle from which everything else follows:

> ### Exhaust the arithmetic before invoking hypotheses.

Revenue fell 8%. We do not ask a model *why*. We first ask *where*. If 88% of the decline
sits in two enterprise renewals, an unanswerable question has become a focused one. Only
then do we test why **those two** renewals stalled.

**The analogy:** a dashboard is a smoke alarm — it goes off loudly and is then done.
CaseFile is the fire investigator who arrives afterwards, establishes what happened, rules
out the theories that don't hold, and writes the report.

---

## How an investigation runs

Every material KPI movement becomes a case with four questions:

| | Question | What it does |
|---|---|---|
| **01** | **Is it real?** | Is the data fresh and complete? Did the definition change? Is this one refund batch or a timing artefact? **Most systems never ask this.** Many "crises" die here — for zero model calls. |
| **02** | **Where did it come from?** | Break the movement down until contributors are visible. This is arithmetic, so it *cannot be wrong* — and everything downstream is scoped by it. |
| **03** | **Why did it happen?** | Enumerate competing explanations from the KPI's driver registry; gather evidence for and against each, structured and unstructured; then try to knock every one of them down. |
| **04** | **What should we do?** | An action with an owner, a rupee figure and a monitoring plan — or the single missing fact that would settle it, and who to ask. |

```
Trigger → VERIFY → DECOMPOSE → INVESTIGATE → CHALLENGE → DECIDE
```

---

## A case, end to end

```
ALERT   Net Revenue · East region · down 8.0% month on month · ₹2.4 Cr
```

**Verify** — billing 4h fresh · complete · no definition change · largest single invoice is
9% of delta (no artefact) · robust z = −3.8, persisted 2 periods · ₹2.4 Cr over the ₹25 L
materiality threshold → **case opens**.

**Decompose** — pure subtraction, no model has been called yet:

```
Net Revenue · East · Δ = −₹2.4 Cr
├── by KPI:      renewal_rate −₹2.1 Cr (88%) · expansion −₹0.2 Cr · new −₹0.1 Cr
└── by account:  ACME −₹1.3 Cr (54%) · NORTHWIND −₹0.8 Cr (34%) · 47 others −₹0.3 Cr
                 concentration K(2) = 0.88
FOOTPRINT → accounts {ACME, NORTHWIND}, window 2026-03-01 … 2026-04-30
```

**Investigate & challenge** — every hypothesis faces four questions a business leader can
follow without statistics:

| Hypothesis | Timing | Locality | Dose | Control | Result |
|---|---|---|---|---|---|
| Pricing increase | pass | **refute** — hit 41 accounts, 39 held steady | n/a | refute | **Eliminated as primary** · minor share −₹0.2 Cr kept |
| Competitor offer | **refute** — APAC onset, after the decline began | **refute** — APAC only | n/a | inconclusive | **Weak** |
| Integration delay | pass (21d, 23d lag) | pass (J = 1.0) | **inconclusive (n=2)** | pass (DiD −₹0.9 Cr, beats all 6 placebos) | **Survives** |

**Decide:**

```
VERDICT       Integration delays likely drove both stalled renewals
ATTRIBUTION   integration_delay −₹2.1 Cr (88%, primary) · pricing −₹0.2 Cr (8%, minor)
              · mix −₹0.1 Cr (4%)
CONFIDENCE    Likely — not Confirmed, because Dose is inconclusive at n=2
ACTION        Prioritise integration fix; contact both accounts this week
OWNER         VP Sales, East  (+ VP Engineering for the fix)
RECOVERY      ₹1.8 – 2.4 Cr  =  ₹2.4 Cr at risk (decomposition) × save-rate
              75–100% (lever assumption, stated on the case)
MONITORING    renewal_rate · East · weekly; escalate if not recovered in 2 cycles
STILL OPEN    "Did the integration delay influence the renewal decision?
               Ask the ACME and NORTHWIND account owners."  Worth ₹2.1 Cr
```

> **The most important line in the whole project is `Likely — not Confirmed`.**
> With two accounts, the Dose test *cannot* pass. A system that claimed otherwise would be
> lying, and ours is built so that it structurally cannot.

---

## The rules of evidence

### Four falsification tests

The system's job is **elimination**. A theory that survives falsification is worth far more
than one that merely fits.

| Test | Question | Kills a hypothesis when | Method |
|---|---|---|---|
| **Timing** | Did the cause precede the effect, by a plausible lag? | The cause starts after the effect | Event dates · PELT change-point |
| **Locality** | Does the cause's footprint match the effect's? | *A bug that hit every region cannot explain a drop in one* | Jaccard overlap |
| **Dose** | Where the cause was stronger, was the effect stronger? | No monotonic relationship | Spearman ρ, **n ≥ 5** |
| **Control** | Did comparable segments *without* the cause behave differently? | Unexposed peers moved identically | DiD, decided by **placebo rank** |

### Three probe outcomes — evidence of absence vs absence of evidence

Every probe lands as exactly one of three things, and the distinction is load-bearing:

| Outcome | Meaning | Effect |
|---|---|---|
| **found** | The evidence is there, cited to a record | Supports or contradicts |
| **checked_absent** | *"0 of 12 populated lost-reason fields name a competitor"* — the denominator is stated | **Refutes.** This is what makes "Eliminated" defensible |
| **uncheckable** | The source has no coverage of this footprint in this window | **Abstains.** Caps confidence; at coverage ≈ 0 across a hypothesis's sources, forces Undetermined |

### Four verdicts

| Verdict | Rule |
|---|---|
| **Confirmed** | Control passes **and** ≥2 other tests pass **and** nothing contradicts |
| **Likely** | Survives elimination; ≥2 tests pass including Timing or Locality; Control inconclusive |
| **Contested** | ≥2 hypotheses reach Likely with conflicting evidence — both are presented |
| **Undetermined** | Nothing reaches Likely, key evidence is stale or missing, or the sources simply could not see the footprint |

**The verdict ranks; it does not crown.** A hypothesis eliminated as the *primary*
explanation keeps its measured minor contribution — *"pricing cannot explain the
concentrated movement"* and *"pricing cost ₹0.2 Cr"* are both true, and the case says both.

**Confidence ceilings** only ever lower: a stale source or a peer-borrowed baseline caps
the verdict at Likely; an unmodelled driver forces Undetermined and raises a contract gap
an analyst can promote into the registry.

> **Undetermined is a success state.** When the evidence cannot decide, CaseFile returns
> the single question that would settle it, who to ask, and what resolving it is worth.
> A confidently wrong answer is more dangerous than no answer.

---

## The pipeline

Twelve stages. `DET` = deterministic code · `LLM` = schema-enforced model call · `HYB` = both.

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

### The LLM boundary

The brief is explicit: *"the LLM should not be treated as the source of quantitative truth
— demonstrate when you use deterministic logic, SQL, business rules, statistics, causal
inference, retrieval or LLMs, and why."* Three of twelve stages touch a model:

| Stage | Method | Why this method |
|---|---|---|
| **3 · Hypothesise** | Registry enumeration + **LLM** annotation | The tested set is a deterministic function of the contract and the footprint. The model adds rationale and may flag one `unmodelled` driver — it can never remove a suspect from the list |
| **4c · Extract** | **LLM**, schema-forced | Language → structure, with a `doc_id` and a quoted span on every claim |
| **8b · Narrate** | **LLM** | Language, per persona — over facts already filtered, with numbers interpolated from the case object |

Everything else — conformance, verification, decomposition, probes, retrieval ranking, the
four tests, adjudication, recommendation, entitlement, feedback, telemetry — is SQL,
arithmetic, statistics or set operations.

> **None of the three model calls produces a number, and none decides what gets tested.**
> Stage 10 measures this per case rather than asserting it.

---

## What the system is made of

### 1 · The KPI Semantic Contract — *executable configuration, not documentation*

One YAML per KPI, read by the pipeline at every stage: definition · calculation ·
definition epochs · composition edges to other KPIs · materiality and data-quality
thresholds · a **driver registry** where each driver names its evidence sources, its
maximum plausible lag, its probe SQL, and the controllable lever it maps to (with an owner
role and a declared save-rate band) · lineage · row/column/domain access rules with masking.

The registry is what makes hypothesis generation deterministic: **the contract decides who
gets investigated, not the model.**

### 2 · The Evidence Ledger — *append-only, and nothing reaches the page without it*

```python
class EvidenceItem(BaseModel):
    claim: str
    kind: Literal["fact", "statistic", "document", "absence"]
    outcome: Literal["found", "checked_absent", "uncheckable"]
    source: Source                       # system, record_id, timestamp, url
    method: Literal["sql", "contribution", "stat_test", "did",
                    "retrieval", "llm_extraction"]
    supports: list[str]                  # hypothesis ids
    contradicts: list[str]
    strength: float
    freshness_hours: float
    denominator: int | None              # absence: how many records were checked
    coverage: float | None               # share of the footprint the source can see
```

Because `method` travels with every claim, the LLM/non-LLM breakdown is a **property of the
data**, not a slide. Because `denominator` and `coverage` travel with absences, "we found
nothing" is a computed finding rather than an assertion.

### 3 · The Case — *one investigation, start to finish*

Trigger · verification result · contribution tree and footprint · hypotheses · ledger ·
test matrix · a **ranked attribution** with deterministic shares · verdict and confidence ·
recommendation · open question · priority (`|Δ at stake| × confidence weight`, which orders
the case list) · telemetry.

---

## What a person actually sees

| Screen | Contents |
|---|---|
| **Case list** | The inbox, ordered by ₹ at stake × confidence. Cases closed as *not real* or *not material* stay visible — the ones that died at Verify are part of the argument |
| **Case file** | What moved · where it came from · what we tested · verdict & confidence · do this (action, owner, ₹, by when) · still open |
| **Evidence drill-down** | Click any claim → the actual ticket, CRM note, deploy log, or the SQL that produced the number, with its method label and freshness |
| **Persona switcher** | The same case for CFO / VP Sales / Analyst / Support Lead — *different actions*, not one paragraph at two lengths. Restricted fields appear as `"2 accounts (names restricted)"`, `"₹1–5 Cr"`: redaction stated, never silent |
| **Telemetry panel** | Latency by stage, model calls, tokens, cost, and the share of stages that ran without a model |

Entitlement is applied to the **`Case` object, before narration**. The other order — write
first, then ask the model to redact — leaks every time.

---

## The data, and why it is simulated

We need revenue at invoice-line grain **plus** account-level renewals **plus** free text
about *those same named accounts* over time. That combination is simultaneously a company's
financials, customer list and support history. Nobody publishes it. And decisively:

> **A known true cause cannot exist in real data by definition.** If it were labelled, there
> would have been no investigation.

So the data is generated from a **structural causal model** — lagged propagation from
injected events through tickets, CSAT, renewal probability and invoices, rendered at three
grains and three cadences, then corrupted realistically with late arrivals, a refund batch,
a definition change and missing fields. Texture (invoice-value skew, `lost_reason`
distributions, ticket vocabulary, seasonality shape) is borrowed from public datasets, so
the result is *simulated*, not *fabricated*.

**Three honesty controls:**

1. The injected events are sealed in `ground_truth.json`, which **the pipeline is forbidden
   from reading** — only the test suite may. It is a lint rule in CI, because *"we'll
   remember"* is not a control.
2. The text corpus is generated once and **frozen into the repo**, so the model writing
   tickets is never the model reading them in the same run. ~85% is irrelevant traffic, and
   some documents are deliberately misleading.
3. Decomposition — the load-bearing stage — is also scored against the public
   **Squeeze / RiskLoc** semi-synthetic benchmarks with published F1 for Adtributor and
   HotSpot. **That is the one number we do not self-grade.**

**Seeded scenarios**, each proving one behaviour:

| | Scenario | Proves |
|---|---|---|
| **A** | Multi-factor movement, 3 injected events, 2 plausible decoys | Both decoys eliminated as primary; the true driver reaches **Likely, not Confirmed** |
| **B** | The true cause is a competitor offer the sources genuinely *cannot see* | Probes return **uncheckable** → **Undetermined** + the discriminating question |
| **C** | An 8-month-old KPI with no seasonal baseline | Peer-borrowed baseline; confidence ceiling enforced regardless of test outcomes |
| **D** | A refund batch — one credit note is 71% of the movement | Closed at Verify · **0 LLM calls** |
| **E** | The metric definition changed at an epoch boundary | Closed at Verify · **0 LLM calls** |
| **F** | A Support Lead opens the headline case | Row + column + domain filter, names hashed, ₹ banded, redaction stated |
| **G** | Two causes on the same accounts in the same fortnight, identical footprints | Neither Dose nor Control can separate them → **Contested**, both presented |

> **A and B are the same signal read two ways.** In A the lost-reason fields are *populated*
> and none names a competitor — checked-absent, which refutes. In B they are *null* and the
> sources have no coverage — uncheckable, which abstains. Evidence of absence versus absence
> of evidence, as a code path.

---

## Budget

Per case, close path: **3 model calls, ≈14.5k input / 3.7k output tokens.** Small *because*
of decomposition-scoped retrieval — measured at ladder step 1.6 on the East fixture:
64.6k documents filtered to ~1.0–1.3k by footprint (exact, not semantic), then BM25 ranks
the top 15. Recall@15 over the authored evidence documents measured 1.000 for every driver,
so `sentence-transformers` stays behind an opt-in extra rather than running by default.

| | Target |
|---|---|
| Alert → closed case | **< 10 s** |
| Cost per case | **< ₹10** (~₹8 at Sonnet-class pricing; ~₹3 at Haiku-class) |
| Stages producing numbers without a model | **100%** |
| Claims without a traceable source | **0** |
| Evidence assembly | ~3 days of chasing → seconds, plus at most one targeted question with a named owner |

Whole-corpus RAG at ~200k input tokens per case would be **10–15× these figures**. The
scoping is an architectural consequence of the core insight, not a bolted-on optimisation.

---

## "Tableau Pulse and Databricks Genie already do this"

| Platform-native narrators (Pulse, Genie, Cortex Analyst, Spotter) | CaseFile |
|---|---|
| Detect and describe the movement | **Verifies the movement is real** before explaining anything |
| One generated narrative | Four falsification tests; decoys eliminated with stated, cited evidence |
| Always produce an answer | **Abstains** — with the discriminating question, its owner and its value |
| Redaction at the prompt layer, if at all | Entitlement applied to the case object *before* narration |
| Insight | Action with an owner, a ₹ figure and a monitoring plan |

They are detection-and-description layers. **CaseFile begins where they stop: after the
alert, before the decision.**

---

## Stack

| Layer | Choice | Why |
|---|---|---|
| Language | **Python 3.11** | Statistical ecosystem |
| Store | **DuckDB** | Real SQL, file-based, no service to run. One engine for warehouse, ledger and case store — and because every quantitative op is already SQL, Snowflake/Databricks is a connector swap |
| Types | **Pydantic v2** | Contract, evidence, verdict — *and* LLM output-schema enforcement, for free |
| Statistics | **statsmodels + scipy** | STL, PELT change-point, Spearman, DiD |
| Retrieval | **rank_bm25 (default), sentence-transformers behind an `embed` extra** | Local, free, offline. Measured recall@15 = 1.000 for BM25 alone, so the embedding stays opt-in |
| API / UI | **FastAPI · React + Vite** | One process, five screens |
| LLM | **Provider-agnostic protocol** | Every call schema-enforced; every call returns `Usage`, which is what makes telemetry a measurement |

**Deliberately not used** — a design statement, not an omission:

| Rejected | Used instead | Why |
|---|---|---|
| Knowledge graph / Neo4j | YAML driver registry + composition edges | Same expressive power at our depth; no service |
| Vector DB | numpy cosine over ~200 scoped docs | A vector service would be *slower* than the array |
| Airflow / Kafka | A Python function on a timer; watermark-based cadences | Twelve stages, one process |
| LangChain / LangGraph / CrewAI | Plain functions + Pydantic | A linear DAG; a framework adds indirection and version churn |
| Agent loop | A fixed twelve-stage pipeline | Non-determinism is the failure mode we are engineering against |
| DoWhy / do-calculus | Four tests + DiD | DiD *is* causal inference, and a leader can follow it |
| Whole-corpus RAG | Decomposition-scoped retrieval | Better *and* 10–15× cheaper |

---

## Repository

```
casefile/
├── contracts/          6 KPI semantic contracts (YAML)
├── personas/           4 persona definitions
├── probes/             SQL templates, one per driver
├── src/casefile/
│   ├── models.py       ★ the interface contract every track builds against
│   ├── contract.py     contract model + validator
│   ├── metric.py       executes a contract's formula/filters/epochs
│   ├── stats/          stl · changepoint · did (+ placebo rank) · jaccard · spearman · pvm
│   ├── data/           generator (SCM + sealed ground truth) · DuckDB loader
│   ├── engine/         S1 verify … S9 feedback, one module per stage
│   ├── retrieval/      footprint scoping → BM25 (embeddings behind an extra)
│   ├── llm/            provider protocol, schema enforcement, usage telemetry
│   ├── orchestrator.py runs S0→S8, writes the Case
│   └── api/            FastAPI
├── ui/                 React + Vite — 5 screens
├── data/
│   ├── ground_truth.json   ★ pipeline forbidden from reading it; tests only
│   └── corpus/authored/    hand-authored signal/misdirection text, committed
│                            (the noise floor regenerates from the seed)
├── fixtures/           golden Case objects
├── tests/              unit · ground-truth harness · benchmark · security
└── docs/               the canonical project plan
```

---

## Documentation

The full plan lives in [`docs/`](docs/README.md). Cross-references in the text use `§N`;
[the index](docs/README.md) resolves every one of them.

| | Document | Covers |
|---|---|---|
| 01 | [**Problem & Solution**](docs/01-problem-and-solution.md) | The problem underneath, the four verdicts, the worked example, user flow |
| 02 | [**Architecture**](docs/02-architecture.md) | The three artifacts, twelve stages, the LLM boundary, stack, cost |
| 03 | [**Data**](docs/03-data.md) | Data strategy, six KPIs, the generator, seeded scenarios |
| 04 | [**Team & Ownership**](docs/04-team.md) | Three tracks, interface contracts, day-one protocol |
| 05 | [**Execution & Roadmap**](docs/05-execution.md) | Phases and phase gates |
| 06 | [**Testing & Risks**](docs/06-quality.md) | Five test layers, the ground-truth harness, risk register |
| 07 | [**Outcome**](docs/07-outcome.md) | Differentiators, evaluation criteria, deliverables, demo script |
| 08 | [**Glossary**](docs/08-glossary.md) | Term lookup |
| 09 | [**Build Protocol**](docs/09-build-protocol.md) | Repo rules, CI, the build ladder, coordination |

---

## Team

**Team Jerry — IIT Kharagpur**

| Member | Track | Owns |
|---|---|---|
| **Aditya Goyal** | **A · Data & Truth** | Everything that produces a number — contract, generator, loader, statistics, Verify, Decompose |
| **Jitam Barman** | **B · Evidence & Reasoning** | Everything between a footprint and a verdict — hypotheses, retrieval, extraction, challenge, adjudication, recommendation, the LLM layer |
| **Sahil Kumar Gupta** | **C · Surface & Delivery** | Everything a human touches — orchestrator, API, entitlement, narration, personas, UI, feedback |

---

<div align="center">

**Dashboards tell businesses what changed.**
**CaseFile tells them what to believe, what to question, and what to do next.**

</div>
