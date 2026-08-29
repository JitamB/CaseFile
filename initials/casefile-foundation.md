# CaseFile — The Foundation Model

**Round 2 · Problem Track 3 · Team Jerry**
**Status: FINAL. This is the base we build on.**

Companions: [`casefile-concept-and-process.md`](casefile-concept-and-process.md) (why),
[`architecture-decision.md`](architecture-decision.md) (which architecture and why not the
others), [`data-strategy.md`](data-strategy.md) (what data).

This document is the *what we are building*, step by step.

---

## How to read this

Every step has two layers:

> **📖 In plain terms**
> A naive, non-technical explanation. If you only read these boxes, you still understand
> the whole product.

Followed by the technical detail — inputs, outputs, method, and how the step behaves on
our running example. Each step is also tagged:

`DETERMINISTIC` — ordinary code. Same input, same output, every time. No model involved.
`LLM` — a language model is called, with an enforced input and output schema.
`HYBRID` — both, with a hard line between them.

---

## The running example

One case threads through every step, so you can watch it develop.

```
ALERT   Net Revenue · East region · down 8.0% month on month · ₹2.4 Cr
```

At the end of Step 8 this becomes a one-page verdict with an owner. Follow it down.

---

# Part I — The three things everything else uses

Before the steps, three artifacts. Every stage reads or writes at least one of them.

---

## Artifact 1 — The KPI Semantic Contract

> **📖 In plain terms**
> A recipe card for each number the company cares about.
>
> It says what "Net Revenue" actually means, who owns it, how fresh the data should be,
> how big a change has to be before anyone should care, and a list of the things that
> usually make it move.
>
> Without this, the system doesn't know what revenue is — and honestly, neither do most
> companies, which is why two teams often report different numbers for the same thing.

**Technically:** one YAML file per KPI. It is *executable configuration*, not
documentation — the pipeline reads it at every stage.

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

composition: [renewal_rate, expansion_arr, new_business_arr]   # cross-KPI edges
decomposition_dims: [region, segment, product, account]

materiality:
  relative: 0.03
  absolute: 2_500_000
  min_persistence: 2

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
  - id: pricing_change
    type: internal_controllable
    evidence_sources: [price_book, crm_notes]
    max_lag_days: 60
    lever: { action: pricing_review, owner_role: cro, lag_days: 30 }

lineage: [billing.raw_invoice → billing.invoice_line → metric.net_revenue]

access:
  row:    { region: role_scoped }
  column: { account_name: [cfo, vp_sales], amount_net: [cfo, vp_sales, analyst] }

history_start: 2023-04-01
```

**Every Round 2 requirement traces to a field here.** Definitions and calculations →
`formula`, `grain`, `calendar`. Thresholds → `materiality`. Drivers and levers →
`drivers`. Lineage → `lineage`. Access restrictions → `access`. Sparse-history detection
→ `history_start`. Freshness → `refresh.sla_hours`.

---

## Artifact 2 — The Evidence Ledger

> **📖 In plain terms**
> The evidence bag.
>
> Every single fact the investigation picks up goes into a labelled bag with a tag saying
> exactly where it came from — which ticket, which note, which query.
>
> The rule: **nothing appears in the final report unless it came out of a bag.** That is
> the whole reason you can trust the output. Click any sentence, see the receipt.

**Technically:** an append-only typed record. Every stage writes to it; the narrative
stage may only reference it.

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

- **`kind: "absence"`** — *"0 of 12 lost-reason fields name a competitor."* Absence of
  evidence is computed and recorded as evidence. This is what makes a "Ruled out" verdict
  defensible rather than a shrug.
- **`method`** — every claim carries the label of *how* it was established. This is what
  makes the LLM-vs-non-LLM breakdown a property of the data rather than a slide.

---

## Artifact 3 — The Case

> **📖 In plain terms**
> The case folder. One investigation, start to finish, in one place.
>
> It starts nearly empty when the alert fires and gets thicker as each step adds to it.
> At the end it is the thing you read.

```python
class Case(BaseModel):
    id: str
    trigger: Trigger                    # kpi, period, delta
    verification: VerificationResult    # step 1
    decomposition: ContributionTree     # step 2
    hypotheses: list[Hypothesis]        # step 3
    ledger: list[EvidenceItem]          # steps 1–4
    tests: dict[str, TestMatrix]        # step 5
    verdict: Verdict                    # step 6
    recommendation: Recommendation|None # step 7
    open_question: OpenQuestion|None    # step 6
    telemetry: Telemetry                # step 10
```

---

# Part II — The eleven steps

---

## Step 0 · Ingest & Conform  `DETERMINISTIC`

> **📖 In plain terms**
> Getting three departments to speak the same language.
>
> Finance keeps records by invoice. Sales keeps them by deal. Support keeps them by
> ticket. They use different names for the same customer and different ideas of when a
> month ends.
>
> Before you can compare anything, you have to agree that "ACME Corp" in one system is the
> same company as "Acme Corporation" in another, and that "April" means the same 30 days
> everywhere. That's all this step does. It's boring and nothing works without it.

**In** — three sources at three grains and three cadences:

| Source | Grain | Cadence | History |
|---|---|---|---|
| `billing` | invoice line | daily, 26h SLA | 3 years |
| `crm` | opportunity / account | 24h batch | 3 years |
| `product_ops` | event / document | near-real-time | 8 months |

**Out** — conformed tables in DuckDB sharing `account_id`, `region`, `product_id` and a
fiscal calendar; plus a **watermark** per source recording how fresh it is.

**How** — an entity resolution map (`account_alias → account_id`) and a calendar table.
Both are small, both are committed, neither is clever.

**Why we can't skip it** — every cross-source claim we make later ("this ticket concerns
the account in this invoice") is meaningless without a shared key. The watermark written
here is what Step 1 checks.

---

## Step 1 · Verify — *is this change real?*  `DETERMINISTIC`

> **📖 In plain terms**
> Checking the patient is actually sick before treating them.
>
> A doctor taps the thermometer before diagnosing a fever. Revenue "dropping 8%" might
> just mean yesterday's data hasn't finished loading. Or someone quietly changed how
> revenue is counted. Or one big refund landed on the last day of the month.
>
> A surprising number of business panics die right here — and each one that dies saves
> somebody three days.
>
> This step also asks a second question: even if it's real, is it *big enough to care
> about?* Statistics can find a "significant" change in something worth ₹40,000. Nobody
> should be woken up for that.

**In** — the KPI, the period, the conformed tables, the contract.

**Out** — a `VerificationResult`, and either a closed case or a green light.

**The five checks, in order:**

| Check | Method | Fails when |
|---|---|---|
| **Freshness** | `now − watermark` vs `refresh.sla_hours` | Source is stale → report the movement as provisional, cap confidence |
| **Completeness** | row count vs 28-day median by weekday; vintage comparison for late arrivals | Rows are still landing → not a real drop |
| **Definition drift** | hash of (`formula` + `grain` + `calendar` + filters) per period; restatement check against the prior snapshot | The metric changed, not the business |
| **Artefacts** | single-record dominance (`max |Δ_record| / |Δ_total| > 0.35`), refund-batch detection, period-boundary slippage | One invoice or one refund *is* the movement |
| **Materiality** | statistical: STL decomposition → robust z on residuals (MAD), persistence ≥ 2 periods · business: `materiality.relative` **and** `materiality.absolute` | Normal variation, or real but too small to act on |

**Sparse history:** if `history < 2 × seasonal period`, the seasonal baseline is
unavailable. Instead of failing, we **borrow a baseline from peer segments** — compare
against sibling segments' movement in the same period — and set a hard rule:
`confidence_ceiling = Likely`. A KPI with no history can never reach Confirmed on
statistical grounds. This is how the newly-launched product line is handled honestly.

**On our example:** freshness OK (billing 4h old). Completeness OK. No definition change.
Largest single invoice is 9% of the delta — no artefact. Robust z = −3.8, persisted 2
periods, ₹2.4 Cr > ₹25 L threshold. **Case opens.**

**Why we can't skip it** — this is the Round 1 differentiator, and it is also the **cost
gate**: a case that fails verification closes without a single model call. Explaining an
artefact convincingly is worse than not explaining it at all.

---

## Step 2 · Decompose — *where did it come from?*  `DETERMINISTIC`

> **📖 In plain terms**
> Finding which tap is running before asking why the water bill is high.
>
> "Revenue in the East fell 8%" is a question nobody can answer — it could be anything,
> anywhere, involving hundreds of customers.
>
> "88% of that fall is two specific accounts" is a question somebody *can* answer.
>
> This step is just subtraction. It adds up where the money went missing until the
> contributors are visible. Because it's arithmetic, **it cannot be wrong** — and that
> matters enormously, because everything downstream is scoped by its answer.
>
> This is the single most important step in the system.

**In** — the verified movement, `decomposition_dims`, `composition` edges.

**Out** — a `ContributionTree` with exact numbers, plus a **footprint**: the set of
entities and the time window that everything downstream will be restricted to.

**Three kinds of decomposition:**

1. **Additive contribution** — `contribution_i = Δ_i / Δ_total` across the dimension
   hierarchy. Greedy top-down; keep expanding a branch until cumulative contribution
   reaches 80% or depth 3.
2. **Price · Volume · Mix** — `Δrevenue = Σ(Δprice × vol₀) + Σ(price₀ × Δvol) + mix`.
   This is what makes the multi-factor scenario rigorous rather than hand-waved.
3. **Cross-KPI attribution** — using `composition`, split the Net Revenue movement across
   Renewal Rate, Expansion and New Business. This is what makes the five KPIs genuinely
   *connected* rather than five separate dashboards.

Also computed: **concentration** — what fraction of `|Δ|` sits in the top-k leaves. This
is the "88%" number, and it is the headline of the whole case.

**On our example:**

```
Net Revenue · East · Δ = −₹2.4 Cr
├── by KPI:      renewal_rate −₹2.1 Cr (88%) · expansion −₹0.2 Cr · new −₹0.1 Cr
└── by account:  ACME −₹1.3 Cr (54%) · NORTHWIND −₹0.8 Cr (34%) · 47 others −₹0.3 Cr
                 └── concentration: 88% in 2 of 49 accounts
FOOTPRINT → accounts {ACME, NORTHWIND}, window 2026-03-01 … 2026-04-30
```

**Why we can't skip it** — three downstream steps depend on the footprint. Hypotheses are
generated *for these two accounts*. Retrieval searches *only documents about these two
accounts in this window*. The four challenge tests compare *this footprint* against a
cause's footprint. Skip this and retrieval has no scope, the model has no anchor, and
input tokens grow by 10–15×.

---

## Step 3 · Hypothesise — *what could have caused it?*  `LLM #1`

> **📖 In plain terms**
> Drawing up the suspect list.
>
> We now know two specific accounts stalled. What could make *those two* stall?
>
> The system has a known list of things that usually cause renewals to fail — from the
> contract. It picks the ones that could plausibly apply here, given what actually
> happened.
>
> One strict rule: **every suspect must be checkable.** If we can't name a place to look
> for evidence, it doesn't go on the suspect list — it goes on a separate "we can't test
> this" list, which pushes the whole case toward "we don't know". No unfalsifiable
> theories.

**In** — the decomposition summary, the footprint, the contract's `drivers` registry
filtered to drivers whose `evidence_sources` are actually available.

**Out** — schema-enforced:

```python
class Hypothesis(BaseModel):
    driver_id: str                  # MUST exist in the registry, or be "unmodelled"
    rationale: str                  # why plausible for THIS footprint
    testable_with: list[str]        # MUST be non-empty
    expected_signature: Signature   # what timing/locality/dose should look like if true
```

**Three guardrails:**

- The model may only propose drivers that exist in the registry — **or** flag `unmodelled`,
  which routes the case toward Undetermined *and* raises a **contract gap** an analyst can
  later promote into the registry. The limitation becomes the feedback loop's best signal.
- A hypothesis with empty `testable_with` is recorded as untestable and cannot win.
- **The model produces no numbers.** Its entire output is IDs, prose rationale, and
  expected signatures.

**On our example:** three hypotheses — `integration_delay`, `pricing_change`,
`competitor_offer`. Each names its evidence sources.

**Why an LLM here** — generating a plausible, contextual suspect list from a typed
registry is a genuine language task. The alternative is a hard-coded lookup (brittle) or a
free-roaming agent (unbounded). This is the constrained middle.

---

## Step 4 · Gather Evidence  `HYBRID`

> **📖 In plain terms**
> Going door to door.
>
> For each suspect, collect what the company already knows. Two kinds of legwork:
>
> **The numbers** — run precise queries. Did prices actually change for these two
> accounts? How many support tickets did they file, and when?
>
> **The words** — read the support tickets, CRM notes and deploy logs. But *only* those
> about these two accounts, in this window. That's maybe 200 documents out of 45,000 —
> because Step 2 already told us where to look.
>
> And one thing most systems never do: **write down what you didn't find.** "We checked 12
> lost-reason fields and none mentioned a competitor" is a real finding. It's how you rule
> something out instead of just failing to confirm it.

### 4a · Structured probes and negative evidence — `DETERMINISTIC`

Per hypothesis, a SQL probe template from the contract. Returns `EvidenceItem`s with
`method: "sql"`. Absence is **counted, not inferred**: `kind: "absence"` with an explicit
denominator.

### 4b · Scoped retrieval — `DETERMINISTIC`

**This is the architecture's best idea, and it comes free from Step 2.**

Conventional RAG-for-BI searches the whole corpus with a vague query. We filter by
`entity_id ∈ footprint` and `date ∈ window` **before** semantic search runs:

```
45,000 documents
   └─ filter by footprint (exact, not semantic)   →  ~200 documents
        └─ hybrid rank: BM25 + embedding cosine   →  top 15
```

Precision rises (the filter is exact). Input tokens fall ~10–15× (≈14k vs ≈200k). The
hallucination surface shrinks, because the model only ever sees documents that provably
concern these accounts.

### 4c · Extraction — `LLM #2`

Retrieved documents → typed evidence claims, schema-forced, each carrying `doc_id` and the
quoted span it came from. Marked `method: "llm_extraction"`.

This is the one thing only a language model does well: turning "customer is frustrated,
the sync has been failing since the 12th and they've escalated twice" into a structured
claim linked to a hypothesis.

**On our example:** ticket volume for ACME and NORTHWIND spikes 4.2× from 12 April.
Renewal notes on both mention integration problems. Price book shows no change for either.
12 of 12 lost-reason fields are silent on competitors.

---

## Step 5 · Challenge — *does the explanation survive?*  `DETERMINISTIC`

> **📖 In plain terms**
> Cross-examination.
>
> Lots of things moved at the same time as revenue. That proves nothing — ice cream sales
> and drowning deaths both rise in summer.
>
> So every suspect faces four questions any detective would ask:
>
> **Timing** — did it happen *before* the effect? A cause can't come after its effect.
> **Locality** — does the footprint match? A power cut across the whole city can't explain
> why one house is dark.
> **Dose** — more cause, more effect? If it hit some accounts harder, did they fall harder?
> **Control** — did similar accounts *without* this problem behave differently?
>
> The point isn't to prove a theory. It's to **knock theories down.** A suspect who
> survives four attempts to eliminate them is worth far more than one who merely fits.

**Per hypothesis, four tests. Each returns `pass | refute | inconclusive` plus the statistic:**

| Test | Method | Passes when |
|---|---|---|
| **Timing** | change-point detection on cause and effect series; measure lag | `0 ≤ lag ≤ driver.max_lag_days` |
| **Locality** | Jaccard overlap of cause footprint vs effect footprint | `> 0.5` (refutes below 0.2) |
| **Dose** | Spearman ρ between per-segment cause intensity and effect magnitude | `ρ > 0.5` **and n ≥ 5** |
| **Control** | difference-in-differences vs matched unexposed segments (matched on size, segment, prior trend) | effect estimate significant, CI excludes 0 |

**The `n ≥ 5` rule on Dose matters more than it looks.** In our own headline example there
are two accounts. Dose *cannot* pass. A system that claimed otherwise would be lying, and
ours is built so it structurally cannot.

**On our example:**

| Hypothesis | Timing | Locality | Dose | Control | Result |
|---|---|---|---|---|---|
| `pricing_change` | pass | **refute** — hit all 41 enterprise accounts, 39 held steady | n/a | refute | **Ruled out** |
| `competitor_offer` | **refute** — APAC onset, and after the decline began | **refute** — APAC only | n/a | inconclusive | **Weak** |
| `integration_delay` | pass — tickets 12 Apr, stalls 3 & 5 May | pass — exactly these 2 accounts | **inconclusive (n=2)** | pass — 6 matched accounts, DiD −₹0.9 Cr | **Survives** |

**Why we can't skip it** — this is the correlation→cause step, and it has to be
reproducible. An LLM judging plausibility gives an answer no CFO can audit. A rank
correlation and a difference-in-differences give an answer anyone can recompute.

---

## Step 6 · Adjudicate — *what do we actually believe?*  `DETERMINISTIC`

> **📖 In plain terms**
> The verdict.
>
> Score the cross-examination against a fixed rulebook — not a model's opinion, so the
> same evidence always produces the same verdict. Four possible outcomes: **Confirmed,
> Likely, Contested, Undetermined.**
>
> And here's the part that makes this product different from every "AI explains your
> dashboard" tool: when the answer is *"we can't tell"*, the system says so — and then does
> something useful with it. It works out **the single question that would settle the
> matter**, who to ask, and what getting the answer is worth in rupees.
>
> "I don't know" is a valid answer. "I don't know, and here's exactly what would tell us"
> is a useful one.

**The rubric:**

| Verdict | Rule |
|---|---|
| **Confirmed** | Control passes **and** ≥ 2 other tests pass **and** no contradicting evidence |
| **Likely** | ≥ 2 tests pass including Timing or Locality; Control inconclusive |
| **Contested** | ≥ 2 hypotheses reach Likely with conflicting evidence |
| **Undetermined** | No hypothesis reaches Likely, or a key evidence source was stale/missing/untestable |

**Confidence ceilings** (applied after scoring, they only ever lower):

- stale source → cap at **Likely**
- borrowed (peer) baseline → cap at **Likely**
- `unmodelled` driver in play → force **Undetermined** + contract gap

**The discriminating question** (fires on Contested or Undetermined):

For each inconclusive test, compute what evidence would resolve it. Rank by
*(how many hypotheses it would separate)* × *(value at stake from Step 2)*. Return the top
one, with the owner looked up from the contract.

**On our example:** `integration_delay` — Timing pass, Locality pass, Control pass, Dose
inconclusive. Control passed but Dose is inconclusive, so **Likely**, not Confirmed.

Still open: *"Did the integration delay influence the renewal decision? Ask the ACME and
NORTHWIND account owners."* Worth ₹2.1 Cr.

---

## Step 7 · Recommend — *what should we do?*  `DETERMINISTIC`

> **📖 In plain terms**
> The to-do list, with a name on it.
>
> Knowing the cause isn't the point. Doing something is. So the cause gets mapped to a
> lever someone can actually pull, an action, a rupee figure, an owner, and a date.
>
> A finding nobody owns is a sentence, not a decision.

**In** — the surviving driver, the contract's `lever` mapping, the decomposition's rupee
figures.

**Out** — exactly the shape the brief asks for:

```
driver → controllable lever → action → expected impact → owner → confidence → monitoring
```

Every field is a lookup or arithmetic. **The expected impact comes from Step 2's
decomposition, never from a model.**

**On our example:**

| Field | Value |
|---|---|
| Driver | `integration_delay` (internal, controllable) |
| Lever | Engineering prioritisation + CS outreach |
| Action | Prioritise integration fix; contact both accounts this week |
| Expected impact | ₹1.8–2.4 Cr recoverable |
| Owner | VP Sales, East (+ VP Engineering for the fix) |
| Confidence | Likely |
| Monitoring | Watch renewal_rate · East · weekly; escalate if not recovered in 2 cycles |

---

## Step 8 · Entitle, then Narrate  `8a DETERMINISTIC` `8b LLM #3`

> **📖 In plain terms**
> Who's allowed to see what — and then how it's written for them.
>
> The order matters enormously. We **first** strip out everything this person isn't
> allowed to see, and **then** write the report from what's left.
>
> The wrong way — write the full report and ask the model to redact it — leaks, every
> time. You can't un-say something to a language model.
>
> Then the same case gets written differently for different people. The CFO wants the
> verdict, the rupees and the decision. The regional VP wants which accounts and what to
> do on Monday. Same investigation, same facts, genuinely different pages — not one
> paragraph at two lengths.

### 8a · Entitlement — `DETERMINISTIC`

Row, column and domain filters from `contract.access`, applied **to the Case object**.
Restricted values are replaced with explicit markers (`"2 accounts (names restricted)"`,
`"₹1–5 Cr"`), never silently dropped — the reader is told something was withheld.

### 8b · Narration — `LLM #3`

Per persona, over the already-filtered case. Every sentence must cite ledger IDs. Numbers
are **interpolated from the case object**, never generated.

**Three views of the same case:**

| Persona | Sees | Wants |
|---|---|---|
| **CFO** | all regions, all columns | Verdict, ₹ at stake, action, owner, what's still open. One screen |
| **VP Sales, East** | East rows only; account names in their book | Which accounts, what to do this week, which part is theirs |
| **Support Lead** | East rows; **names masked, ₹ banded** | The integration signal and its priority — with the redaction stated on the page |

---

## Step 9 · Feedback  `DETERMINISTIC`

> **📖 In plain terms**
> Learning from being wrong.
>
> An analyst marks a case: right, wrong cause, missed the real cause, or not worth
> investigating. Three concrete things change — not a model retrained in the background,
> but numbers you can watch move.

| Signal | What changes | Effect |
|---|---|---|
| "wrong driver" / "correct" | driver prior weights, per driver per segment | Ranking in Step 3 shifts |
| "not material" (repeatedly) | `materiality` thresholds for that KPI and owner | Fewer false alarms |
| "missed the real cause" | promotes the `unmodelled` contract gap into the registry | The system can investigate a cause it previously couldn't |

Stored in a small table, applied as multipliers on the next run. Demonstrable as a
before/after. **No retraining theatre** — the whole point is that the learning is legible.

---

## Step 10 · Telemetry  `DETERMINISTIC`

> **📖 In plain terms**
> The receipt.
>
> Every case records what it cost, how long each part took, and which parts used AI versus
> plain calculation.
>
> This turns our biggest claim — *"the model never touches a number"* — from something we
> say into something we measured.

Recorded per LLM call: model, input/output tokens, latency, cost from a price table, cache
hits. Recorded per stage: wall time. Aggregated per case: cost per insight, latency, and
the share of stages that ran without a model.

**Budget:** under 10 seconds alert-to-case; ~₹6 per case (≈$0.07 on Sonnet-5-class
pricing, with the two persona narratives issued in parallel).

---

# Part III — The whole thing on one page

```
  billing (daily) ─┐
  crm (24h)        ├─▶ S0 CONFORM ─▶ S1 VERIFY ─▶ [close if not real / not material]
  product_ops (rt)─┘    det.           det.              ↓ no LLM call, no cost
                                                    S2 DECOMPOSE  det.  ← the pivot
                                                         ↓ footprint
                                                    S3 HYPOTHESISE  LLM #1
                                                         ↓
                                        S4a probes det. ─┴─ S4b retrieval det.
                                                         ↓
                                                    S4c EXTRACT  LLM #2
                                                         ↓
                                                    S5 CHALLENGE  det.  ← 4 tests
                                                         ↓
                                                    S6 ADJUDICATE  det. ← 4 verdicts
                                                         ↓
                                                    S7 RECOMMEND  det.
                                                         ↓
                                                    S8a ENTITLE  det.
                                                         ↓
                                                    S8b NARRATE  LLM #3
                                                         ↓
                                              S9 FEEDBACK ──┘  S10 TELEMETRY
```

## The method table — our headline deliverable

| Step | Method | Why this method |
|---|---|---|
| 0 Conform | SQL + mapping | Keys must be exact |
| 1 Verify | SQL + rules + STL/robust-z | Truth about data must be deterministic |
| 2 Decompose | SQL + arithmetic | Contribution is arithmetic; a model can only add error |
| 3 Hypothesise | **LLM** (registry-constrained) | Generative breadth over a typed space |
| 4a Probe | SQL | Exactness; absence must be counted |
| 4b Retrieve | BM25 + embeddings | Ranking, not judgement |
| 4c Extract | **LLM** (schema-forced) | Language → structure |
| 5 Challenge | change-point, set overlap, rank corr, DiD | Falsification must be reproducible |
| 6 Adjudicate | rules | Confidence must be auditable |
| 7 Recommend | contract lookup + arithmetic | Impact and owner are facts |
| 8a Entitle | set operations on the case object | Security is not a prompt |
| 8b Narrate | **LLM** | Language, per persona |

**Three of twelve stages touch a model. None of them produce a number.**

---

# Part IV — Build order

Each phase ends demoable. Cut from the bottom, never the middle.

| Phase | Steps | Done when |
|---|---|---|
| **P0 Foundation** | Contract schema + validator · DuckDB loader · causal generator with sealed `ground_truth.json` | Contract validates; injected driver recoverable by hand |
| **P1 Spine** *(zero LLM)* | S0, S1, S2, S6 rubric, S10 | Refund artefact and definition change both caught; ≥85% concentration recovered on the seeded case |
| **P2 Evidence** | S3, S4, S5 · ledger | Both decoys refuted; `integration_delay` at **Likely**; Dose correctly `inconclusive` |
| **P3 Surface** | S7, S8a, S8b · UI · telemetry view | Three persona views; restricted role masked; cost and latency on screen |
| **P4 Learning** | S9 | After 5 marks, ranking shifts; a promoted contract gap appears in the registry |
| **P5 Optional** | Conversational follow-up over closed cases · one platform-native seam | Only if time is genuinely spare |

**P1 is demoable on its own and already proves the thesis.** If we ship only P1–P3, the
submission is complete and honest.

---

# The one-line version

> **A deterministic pipeline that establishes facts, and calls a language model only where
> language is the actual problem — three times, never for a number.**
