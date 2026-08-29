# Team & Ownership

**CaseFile** · Accenture Innovation Challenge 2026 · Problem Track 3 — BusinessIntelligence.ai · Team Jerry

`Part V · §26–31`

[← Data](03-data.md) · [Index](README.md) · [Execution & Roadmap →](05-execution.md)

---

# PART V — TEAM

## 26. Ownership Map

Three tracks, split along the architecture's natural seams so the handoff is **linear**
(A → B → C) rather than a ping-pong.

| Track | Name | Owner | Scope |
|---|---|---|---|
| **A** | **Data & Truth** | **Aditya Goyal** | Everything that produces a number. Contract, generator, loader, statistics library, Verify, Decompose |
| **B** | **Evidence & Reasoning** | **Jitam Barman** | Everything between a footprint and a verdict. Hypotheses, retrieval, extraction, challenge, adjudication, recommendation, LLM layer |
| **C** | **Surface & Delivery** | **Sahil Kumar Gupta** | Everything a human touches. Orchestrator, API, entitlement, narration, personas, UI, feedback — plus all three graded deliverables |

>Track A is the most statistics-heavy; Track B the most LLM- and retrieval-heavy; Track C the most
> product-, design- and deliverable-heavy. Assign to strengths.

**Coordination sits with B.** Jitam owns the repo protocol, the review queue, the gate
sessions and the open-decision list — [§47](09-build-protocol.md). It is a process role, not
extra modules: the orchestrator stays with C, where the tracks naturally meet.

**Shared by all three:** `src/casefile/models.py` and `fixtures/` (day 1, together — and
never changed by one person afterwards), tests for own modules, the demo script, and the
business proposal's technical sections.

---

## 27. Track A — Data & Truth

### Primary responsibility
Produce every number in the system, and produce the data the system runs on. **If a figure
appears anywhere in a case, Track A computed it.**

### Modules owned

| Module | Stage | Contents |
|---|---|---|
| `contract.py` + `contracts/*.yaml` | — | `KPIContract` Pydantic model, YAML loader, validator. 6 contracts |
| `data/generator.py` | — | SCM, injected events, propagation, three-grain rendering, corruption, `ground_truth.json` |
| `data/loader.py` | S0 | DuckDB ingest, entity-alias conformance, fiscal calendar, watermarks |
| `stats/` | — | `stl.py`, `changepoint.py` (PELT), `did.py` (DiD + placebo rank), `overlap.py` (Jaccard), `correlation.py` (Spearman), `pvm.py`, `robust_z.py` |
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
9. generator — scenarios B, C, D, E, F, G    → verify: each triggers its expected path
10. Squeeze benchmark                        → verify: external F1 recorded in README
```

---

## 28. Track B — Evidence & Reasoning

### Primary responsibility
Take a footprint and turn it into a defended verdict with a recommendation. **Owns the
entire LLM boundary** — and owns proving that the boundary holds.

### Modules owned

| Module | Stage | Contents |
|---|---|---|
| `llm/` | — | `LLMProvider` protocol, schema enforcement, `Usage`, telemetry wrapper, price table, prompt caching |
| `engine/hypothesise.py` | S3 | Deterministic registry enumeration, LLM annotation, `unmodelled` path, guardrails |
| `retrieval/` | S4b | Footprint filter → BM25 + `all-MiniLM-L6-v2` hybrid rank |
| `engine/evidence.py` | S4a/4c | SQL probes, **counted absence**, schema-forced extraction with quote spans |
| `probes/*.sql` | S4a | One template per driver |
| `engine/challenge.py` | S5 | Four tests, calling `stats/`. Returns `TestMatrix` |
| `engine/adjudicate.py` | S6 | Verdict rubric, confidence ceilings, **discriminating question** |
| `engine/recommend.py` | S7 | Contract lever lookup → the seven-field recommendation |
| `ledger.py` | — | Append-only `EvidenceItem` store |
| `data/corpus/` | — | Frozen text generation: tickets, notes, news — with the 85% noise floor and the misleading documents |

### Dependencies
- **On nobody after day 1.** `models.py` and the fixtures are written jointly that morning.
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
| B3 | Hypothesise (S3) | Hypothesis set is registry-enumerated and identical across runs; the model can only annotate and flag `unmodelled`, never add or remove a tested hypothesis; **zero numbers in output** |
| B4 | Scoped retrieval | 45k → ~200 → top 15; measured input tokens ≈14.5k, not ≈200k |
| B5 | Evidence + absence | `kind:"absence"` items carry an explicit denominator |
| B6 | Challenge (S5) | Refutes both decoys on scenario A; Dose returns `inconclusive` at n=2; Control reports the real effect's placebo rank |
| B7 | Adjudicate (S6) | Scenario A → **Likely** with ranked attribution. Scenario B → **Undetermined** + correct discriminating question. Scenario G → **Contested** |
| B8 | Recommend (S7) | All seven fields populated from contract + arithmetic; no model-generated number |
| B9 | Telemetry instrumentation | Per-call and per-stage records feeding C's panel |

### Implementation order
```
1. models.py (joint, day 1)
2. llm/ provider + schema enforcement + Usage → verify: a stub provider round-trips a schema
3. corpus generation, frozen                  → verify: 85% noise measured, misleading docs present
4. retrieval/ + footprint scoping             → verify: 45k → ~200 on the East fixture
5. hypothesise.py (S3)                        → verify: hypothesis set identical across two runs; an off-registry suggestion lands as `unmodelled`
6. evidence.py probes + absence               → verify: "0 of 12 lost-reason" is produced
7. evidence.py extraction (4c)                → verify: every claim carries doc_id + span
8. challenge.py (S5) on A's stats/            → verify: both decoys refuted; Dose inconclusive
9. adjudicate.py (S6) + discriminating question → verify: A = Likely, B = Undetermined, G = Contested
10. recommend.py (S7)                         → verify: 7 fields, all traceable
11. telemetry aggregation                     → verify: cost/case < ₹10, LLM/non-LLM split correct
```

---

## 29. Track C — Surface & Delivery

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
- **Provides to A and B:** the repo skeleton, `Makefile` and CI on day 1 — the commands
  every other track's verification runs through ([§41.3](09-build-protocol.md)).

### Deliverables

| # | Deliverable | Definition of done |
|---|---|---|
| C1 | Repo skeleton, `Makefile`, CI | `make check` green; CI blocks a PR that has not run it |
| C2 | Orchestrator | `make demo` runs alert → case end to end |
| C3 | Entitlement (S8a) | **Security test passes:** restricted fields never appear in any persona's rendered output |
| C4 | 4 personas + narration (S8b) | Each persona's *recommended action* differs, not only the wording |
| C5 | UI, 5 screens | Case list, case file, evidence drill-down, persona switcher, telemetry panel |
| C6 | Feedback (S9) | After 5 marks, evidence-gathering depth and presentation order shift measurably; a promoted contract gap appears in the registry |
| C7 | Repo README | `git clone && make demo` works on a clean machine |
| C8 | Business proposal | Problem framing, solution design, users, business case, roadmap, risks + mitigations |
| C9 | Demo video | ≤ the stated limit; ends with the ground-truth reveal |

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

1. **Harden the repo** — [§41.1](09-build-protocol.md). Thirty minutes, and it is what makes
   every rule below enforceable instead of remembered.
2. **Write `src/casefile/models.py` together.** Every Pydantic model in §14 and §30:
   `KPIContract`, `Trigger`, `VerificationResult`, `ContributionTree`, `Footprint`,
   `Hypothesis`, `EvidenceItem`, `Source`, `TestResult`, `TestMatrix`, `Attribution`,
   `Verdict`, `Recommendation`, `OpenQuestion`, `Telemetry`, `Case`, `Persona`.
3. **Hand-write two fixtures** from §10:
   - `fixtures/decomposition_east.json` — a `ContributionTree` + `Footprint` (unblocks B)
   - `fixtures/case_east_8pct.json` — a complete `Case` (unblocks C)
4. **Agree the four rules in §30**, and settle decision D-1 in
   [§47.2](09-build-protocol.md).

**Afternoon — split.** Everyone now has something to build against and **nobody blocks on
anybody for the rest of the project.**

> Skipping this creates two weeks of integration pain in the last three days. It is
> non-negotiable.

---

[← Data](03-data.md) · [Index](README.md) · [Execution & Roadmap →](05-execution.md)
