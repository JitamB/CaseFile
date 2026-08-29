# Problem & Solution

**CaseFile** · Accenture Innovation Challenge 2026 · Problem Track 3 — BusinessIntelligence.ai · Team Jerry

`Parts I–II · §1–12`

[Index](README.md) · [Architecture →](02-architecture.md)

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
| R2 | Lightweight KPI/semantic contract: definitions, calculations, drivers, thresholds, lineage, access restrictions | **9 elements (6 required + composition + definition epochs + history)** |
| R3 | ≥2 personas receiving different narratives or actions | **4 personas, different actions** |
| R4 | One multi-factor KPI movement with known/simulated drivers | **2 multi-factor movements (A, G), 5 injected drivers** |
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
| Evidence assembly | ~3 days of chasing → seconds, plus at most one targeted question with a named owner |

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
| **Undetermined** | Evidence insufficient to decide | No hypothesis reaches Likely; key evidence stale or missing; or evidence-source coverage of the footprint ≈ 0 — the sources *could not be checked*, as opposed to checked and empty |

**The verdict ranks; it does not crown.** The attribution lists every driver with its
deterministically computed share where one exists (contribution tree, PVM). A hypothesis
eliminated as the primary explanation keeps its measured minor contribution — *"pricing
cannot explain the concentrated movement"* and *"pricing cost ₹0.2 Cr"* are both true,
and the case says both.

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
| Pricing increase | pass | **refute** (hit 41 accounts, 39 held steady) | n/a | refute | **Eliminated as primary** · minor share −₹0.2 Cr kept (PVM) |
| Competitor offer | **refute** (APAC onset, after decline began) | **refute** (APAC only) | n/a | inconclusive | **Weak** |
| Integration delay | pass (21d, 23d lag) | pass (J = 1.0) | **inconclusive (n=2)** | pass (DiD −₹0.9 Cr, exceeds all 6 placebos) | **Survives** |

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

Ordered by case priority: ₹ at stake × confidence.

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
07:00  crm 24h batch lands → the one provisional case re-runs; its ceiling lifts, verdict upgrades
09:00  CFO opens digest: 2 cases. VP Sales East gets a push: "ACME + NORTHWIND, act this week."
09:15  Analyst opens the same case, sees the full decomposition tree and every eliminated theory
09:20  Analyst marks the verdict → feedback adjusts driver priors for next time
```

---

## 12. How Each Component Answers the Problem

| PS demand | Component | How |
|---|---|---|
| *"explains what changed"* | Stage 2 Decompose | Exact contribution arithmetic, not description |
| *"identifies likely root causes"* | Stages 3–5 | Registry-enumerated hypotheses tested by falsification; the verdict ranks drivers with shares |
| *"recommends next steps"* | Stage 7 | driver → lever → action → impact → owner → confidence → monitoring |
| *"natural language"* | Stage 8b | Per persona, over already-filtered facts |
| *"structured and unstructured"* | Stage 4 | Tables locate; text explains. Joined at footprint scope |
| *"meaningful change vs noise"* | Stage 1 | Five checks + dual materiality gate + peer baseline for sparse series |
| *"correlation → actionable"* | Stages 2 + 5 | Narrow first, then four elimination tests |
| *"genuinely ambiguous"* | Stage 6 | Four verdicts; Undetermined + discriminating question + owner + value |

---

[Index](README.md) · [Architecture →](02-architecture.md)
