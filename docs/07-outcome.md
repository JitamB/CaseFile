# Differentiators, Evaluation & Deliverables

**CaseFile** · Accenture Innovation Challenge 2026 · Problem Track 3 — BusinessIntelligence.ai · Team Jerry

`Part VIII · §37–40`

[← Testing & Risks](06-quality.md) · [Index](README.md) · [Glossary →](08-glossary.md)

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
merely fits. Absence is *computed and recorded* with its denominator — and the ledger
separates **checked-and-absent** from **uncheckable**: evidence of absence refutes;
absence of coverage abstains. That one distinction is why "Eliminated" is defensible and
"Undetermined" is honest.

**5 · The LLM never produces a number — and we measure it.**
Three of twelve stages touch a model. Stage 10 reports the split per case. The brief asks
teams to demonstrate this; we instrument it.

**6 · Security acts on data, not on prose.**
Entitlement filters the `Case` object *before* narration. The same investigation yields four
legitimately different truths, with redaction stated rather than silently applied.

> **The one-line version:** a deterministic pipeline that establishes facts, and calls a
> language model only where language is the actual problem — three times, never for a number.

### The positioning question a judge will ask

*"Tableau Pulse and Databricks Genie already summarise metric changes — why isn't this
that?"*

| Platform-native narrators (Pulse, Genie, Cortex Analyst, Spotter) | CaseFile |
|---|---|
| Detect and describe the movement | **Verifies the movement is real** before explaining anything |
| One generated narrative | Four falsification tests; decoys eliminated with stated, cited evidence |
| Always produce an answer | **Abstains**, with the discriminating question, its owner and its value |
| Redaction at the prompt layer, if at all | Entitlement applied to the case object *before* narration |
| Insight | Action with an owner, a ₹ figure and a monitoring plan |

They are detection-and-description layers. CaseFile begins where they stop: after the
alert, before the decision. The business proposal carries this table alongside the
native / configured / custom-built breakdown the brief asks for.

---

## 38. Evaluation Criteria

### 38.1 Requirement checklist — self-audit before submission

| Req | Evidence | Where |
|---|---|---|
| R1 · 3–5 connected KPIs, 2–3 sources, different grains/cadences | 6 KPIs, 3 sources, 3 grains, 3 cadences; composition identity | §22, §23 |
| R2 · Semantic contract, 6 elements | 9 elements (6 required + composition + epochs + history) | §14.1 |
| R3 · ≥2 personas, different narratives/actions | 4 personas, **different actions** | §29, C5 |
| R4 · Multi-factor movement, known drivers | Scenarios A + G, 5 injected drivers | §25 |
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
| Business value | 3 days → 10 seconds; ~₹8/case; action with an owner and a rupee figure |
| Communicability | Detective analogy; the "88% in two accounts" line; the ground-truth reveal |
| Honesty | The verdict is **Likely, not Confirmed** — and we explain why on stage |

---

## 39. Final Deliverables

| # | Deliverable | Owner | Contents |
|---|---|---|---|
| **D1** | **Business Proposal** | C (with A, B on technical sections) | Problem framing (§1–2) · solution design (§6–17) · target users (§29 personas) · business case: 3 days→10s, ~₹8/case, ₹1.8–2.4 Cr recoverable per headline case · competitive positioning vs platform-native narrators (§37) · phased roadmap (§32) · risks + mitigations (§36) · native/configured/custom-built table for the platform question |
| **D2** | **Working Prototype** | all | 6 KPIs, 3 sources, 7 scenarios, 4 personas, 5 UI screens, full telemetry. `git clone && make demo` |
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
| **6 · Cross-examination** | Pricing → **Eliminated as primary** (hit 41 accounts, 39 held steady) — its measured ₹0.2 Cr share stays on the page, because eliminating a theory doesn't erase its arithmetic. Competitor → **Weak** (APAC only, and too late). Integration → survives |
| **7 · The honest verdict** | **Likely, not Confirmed** — because with two accounts the Dose test cannot pass. *Pause here.* A system that claimed Confirmed would be lying |
| **8 · The action** | Owner, ₹1.8–2.4 Cr, by Friday, monitoring plan. And the open question: ask the two account owners |
| **9 · Abstention** | Open the mid-market case. **Undetermined** — and here is the single question that would settle it, who owns it, and what it's worth |
| **10 · Four truths** | Persona switcher. CFO, VP Sales, Analyst, Support Lead — same case, different actions, and the Support Lead sees *"2 accounts (names restricted), ₹1–5 Cr"* with the redaction stated |
| **11 · The receipt** | Telemetry: 8.2 s, 3 model calls, 14.5k tokens, ~₹8. Three of twelve stages used a model. **None produced a number — and none decided what got tested** |
| **12 · The reveal** | Unseal `ground_truth.json` on screen. *This is what we injected. This is what CaseFile recovered — including correctly refusing to be certain.* |
| **13 · Close** | Dashboards tell businesses what changed. CaseFile tells them what to believe, what to question, and what to do next |

---

[← Testing & Risks](06-quality.md) · [Index](README.md) · [Glossary →](08-glossary.md)
