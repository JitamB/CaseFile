# CaseFile — Concept & Process

**Accenture Innovation Challenge 2026 · Problem Track 3 — BusinessIntelligence.ai**
**Team Jerry — IIT Kharagpur**

This document carries forward the full Round 1 analysis and sets out the process we
decided to follow. It exists so that Round 2 work starts from a settled concept rather
than re-litigating it, and so every prototype decision can be traced back to a reason.

It is deliberately not an architecture document. Round 1 kept technology open on
purpose; that discipline is what produced the concept, and the concept should still
lead the build.

---

## 1. Where we are

Round 1 asked for a concept: what should a KPI storytelling engine actually be, for
whom, and why would it beat simply asking an AI to read a dashboard. We submitted
**CaseFile** — a 3-slide concept and a 3-minute video.

Round 2 asks for a **detailed business proposal**, a **working prototype** of the core
mechanism, and a **public GitHub repository** with a demo video and README. The brief
is materially more demanding, but it does not ask us to change direction. Read closely,
it validates the Round 1 bet — most explicitly in one line:

> *"The LLM should not be treated as the source of quantitative truth. Teams should
> explicitly demonstrate when they use deterministic logic, SQL, business rules,
> statistics, traditional ML, causal inference, retrieval or LLMs — and why."*

That is our Round 1 principle — *exhaust the arithmetic before invoking hypotheses* —
restated as a grading criterion. The job in Round 2 is to prove it, not to rethink it.

---

## 2. The problem, as we diagnosed it

The stated problem is that a dashboard shows revenue dropped 8% in a region but cannot
say why or what to do, and the translation takes an analyst days.

The common assumption is that those days are spent on analysis. **They are not.**
Decomposing an 8% drop by region, channel and SKU takes minutes in any modern BI tool.
The delay comes from three places:

1. **The cause is usually not in the warehouse.** Revenue fell because a competitor ran
   a promotion, a checkout flow broke, a good rep resigned, or a shipment was delayed.
   None of these is a column in a table. Structured data can localise a change with
   certainty; it is mute on why.

2. **The waiting is social.** The analyst's real work is assembling evidence — pulling
   release logs, reading support tickets, and messaging six people who reply when they
   can. The clock runs on other people's inboxes.

3. **Many alarming moves are not real.** Late-arriving data, a changed metric
   definition, a refund batch, one large invoice slipping across a month boundary.
   Effort spent explaining an artefact is effort spent twice.

By the time the answer arrives, the window to act has narrowed. Leaders are left
choosing between deciding without evidence and waiting for it.

**The gap we are closing is not description. It is evidence.**

---

## 3. The insight

> **Don't summarise the KPI. Open a case.**

An AI that writes a narrative will always produce one — confident, fluent, and
unfalsifiable. That is the failure mode of every "AI explains your dashboard" product:
it cannot return *"I don't know"*, because generating text is the only thing it does.

CaseFile behaves like an investigator instead. It establishes facts first, then tests
explanations against them, and it is willing to close a case as unresolved.

Every significant KPI movement becomes an investigation with a **verdict**, not a
paragraph. Four questions, in order:

| # | Question | What it does |
|---|----------|--------------|
| 01 | **Is it real?** | Is the data fresh and complete? Did the metric definition change? Is this one refund batch or a timing artefact? |
| 02 | **Where did it come from?** | Break the movement down until the actual contributors are visible. This part is arithmetic, so it cannot be wrong. |
| 03 | **Why did it happen?** | Generate competing explanations and test each against evidence — structured and unstructured — *for* and *against*. |
| 04 | **What should we do?** | Recommend an action with an owner — or identify exactly which missing information would settle it. |

Most systems never ask the first one.

---

## 4. The process — how CaseFile investigates

This is the core mechanism, and the thing Round 2's prototype must demonstrate.

```
Trigger  →  01 Verify  →  02 Decompose  →  03 Investigate  →  04 Challenge  →  05 Decide
KPI moves    Freshness      Region            Structured        Timing           Cause
             Definition     Product           CRM · Tickets     Locality         Confidence
             drift          Customer          Logs              Dose             Action
             Materiality    Channel           External          Control          Owner
                            Transaction       signals           Rule theories out
```

### Trigger
A KPI moves. Not every movement earns an investigation — the gate is stage 01.

### 01 · Verify — *is this change real?*
Before any explanation is attempted:
- **Data quality** — pipeline freshness, completeness, late-arriving records.
- **Definition drift** — did the metric's calculation, hierarchy, calendar or business
  rule change underneath us?
- **Artefacts** — a single refund batch, one invoice crossing a period boundary.
- **Materiality** — is this unusual *for this specific series*, given its own history and
  seasonality, and is it material to a number someone is accountable for?

Statistical significance is not business significance. Both gates must pass.

### 02 · Decompose — *where did it come from?*
Exhaust the arithmetic. Break the movement down across region, product, customer,
channel and, where needed, individual transactions, until the actual contributors are
visible.

This is the pivotal step and the reason the whole thing works:

> *"Revenue fell 8%. We don't ask a model why — we first ask **where**. If 88% of the
> decline sits in two enterprise renewals, an unanswerable question has become a
> focused one. Only then do we test why **those two** renewals stalled."*

Decomposition is fact, not correlation. It cannot hallucinate. It converts a question
no evidence base could answer into one a small evidence base can.

### 03 · Investigate — *gather evidence for the focused question*
Only now do we reach for context, and only for the narrow question decomposition left
us. Structured signals plus unstructured sources: support tickets, CRM notes and
lost-reason fields, release and deployment logs, sales-team commentary, competitor and
market news, internal announcements, campaign data.

Unstructured data is not "another source to feed the model." It is where the cause
actually lives. Structured data tells us *where*; unstructured tells us *why*.

### 04 · Challenge — *move from correlation to a defensible claim*
Several things always moved alongside the KPI. Correlation is not cause. Every
candidate explanation is put through four tests a business leader can follow without
statistics:

- **Timing** — did the proposed cause precede the effect, and by a plausible lag?
- **Locality** — does its footprint match the movement's footprint? *A bug that hit
  every region cannot explain a drop in one.*
- **Dose** — where the cause was stronger, was the effect stronger?
- **Control** — did comparable segments *without* the cause behave differently?

The system's job here is **elimination**. A theory that survives falsification is worth
far more than one that merely fits. Ruling explanations out is a first-class output.

### 05 · Decide — *verdict, confidence, action*
Every investigation closes as exactly one of:

| Verdict | Meaning |
|---------|---------|
| **Confirmed** | Evidence establishes the driver. |
| **Likely** | Survives elimination, causality not proven. |
| **Contested** | Multiple explanations survive; evidence conflicts. |
| **Undetermined** | Evidence is insufficient to decide. |

A verdict carries a recommended action with a named owner, an expected impact, and what
remains open. Every claim traces to the ticket, note or log it came from.

**Undetermined is a success state, not a failure.** When the evidence cannot decide,
CaseFile returns the single question that would settle it, who to ask, and what
resolving it is worth. A confidently wrong answer is more dangerous than no answer.

---

## 5. How this answers the three questions the problem statement raised

**A. Meaningful change vs normal noise** — handled at stage 01, as a two-part gate:
statistical unusualness *for that series* (its own history, seasonality, expected
variation, persistence), and business materiality (does it move a number someone owns).
Plus the step nobody else takes: is the change even real, or is it a data artefact?

**B. Correlation → actionable cause** — handled by stages 02 and 04 together.
Decomposition first, so hypotheses are only raised about a narrow, answerable question.
Then timing, locality, dose and control, applied to eliminate rather than confirm. The
output names the surviving explanation, the evidence behind it, what was ruled out and
why, and what remains uncertain.

**C. Genuine ambiguity** — handled by the four verdicts and, specifically, by
**Contested** and **Undetermined**. The system is architecturally permitted to abstain.
When it abstains it does not stop at "we don't know" — it returns what is missing, who
can provide it, and why it matters.

This is the differentiator, not a caveat. It is the reason a business leader can trust
the output at all.

---

## 6. Worked example — the one we lead with

**Alert:** Revenue, East region, down 8% month on month.

**Decompose:** 88% of the decline sits in two enterprise renewals.
*(Established before any hypothesis is raised.)*

| Hypothesis | Evidence | Verdict |
|---|---|---|
| Pricing increase | Identical pricing applied to unaffected accounts, which held steady. | **Ruled out** |
| Competitor offer | No competitor named in the affected accounts' notes or lost-reason fields. | **Weak** |
| Integration delay | Support ticket spike, matching renewal notes, timing that precedes both stalls. | **Likely** |

**Conclusion:** Integration delays likely drove both stalled renewals.
**Confidence:** Likely · **Recovery:** ₹X–₹Y · **Owner:** VP Sales, East
**Next action:** Prioritise integration resolution and contact both affected accounts
this week.
**Still open:** Causality is not confirmed. Ask the account owners directly whether the
integration delay influenced their renewal decision.

The point of this example is not the answer. It is that the answer shows its work,
shows what it eliminated, and states plainly what it has not proven.

---

## 7. What makes it different

| | |
|---|---|
| **Evidence over narrative** | Every claim traceable to the ticket, note or log it came from. Nothing asserted without a source you can open. |
| **Competing hypotheses** | The system actively tries to *rule explanations out*. Survival under elimination, not plausibility. |
| **Business materiality** | Not every statistical anomaly deserves an investigation. |
| **Uncertainty is actionable** | When evidence is insufficient it doesn't guess: what is missing → who can provide it → why it matters. |

Against the alternatives:

- **A BI dashboard** shows *what*. CaseFile establishes *why* and *what to do*.
- **An automated dashboard summary** describes the same numbers in sentences. CaseFile
  brings in evidence that is not in the warehouse at all.
- **A generic AI chatbot** answers whatever it is asked, with equal confidence
  regardless of evidence. CaseFile refuses to answer when it cannot.
- **An existing analytics copilot** accelerates the analyst's queries. CaseFile
  addresses the actual bottleneck, which was never the queries.

**The payoff:**

```
Traditional BI:   See → Search → Analyse → Explain → Decide     (human does the middle three)
CaseFile:         Detect → Investigate → Prove → Act
```

Days of analyst investigation → minutes. "We don't know" → "here's what would tell us."
A plausible narrative → a defensible position.

> Dashboards tell businesses what changed. CaseFile tells them what to believe, what to
> question, and what to do next.

---

## 8. Principles we hold to

These were decided in Round 1 and are not up for renegotiation while building:

1. **Exhaust the arithmetic before invoking hypotheses.** Anything that can be computed
   deterministically must be, and must never be delegated to a model.
2. **The LLM is not the source of quantitative truth.** It is used for language, intent,
   retrieval and synthesis — not for numbers, and not for verdicts.
3. **No claim without a source.** If it cannot be traced, it does not ship.
4. **Elimination beats confirmation.** Report what was ruled out, not only what survived.
5. **Abstention is a valid output.** Never manufacture confidence the evidence does not
   support.
6. **Materiality gates everything.** Statistically significant is not business
   significant.
7. **An action needs an owner.** A recommendation nobody is accountable for is a
   sentence, not a decision.

---

## 9. What Round 2 adds

The Round 2 brief keeps our concept intact and extends it along axes Round 1 didn't
require. Mapping its eight objectives against what we already have:

| Round 2 objective | Round 1 position | Status |
|---|---|---|
| 1. Detect and prioritise material KPI movements | Stage 01 — Verify + materiality gate | **Have it** |
| 2. Reconcile data and business context across heterogeneous sources | Stages 02–03; definition drift already central | **Have the principle; needs the semantic contract** |
| 3. Identify and rank explanatory drivers using appropriate methods | Stages 02 + 04 | **Have it; need to name the methods explicitly** |
| 4. Persona-specific narratives with traceable evidence | Traceability is core; personas are **new** | **Gap** |
| 5. Communicate uncertainty and abstain | Four verdicts — our headline differentiator | **Have it; strongest card** |
| 6. Actions grounded in business levers, constraints and decision rights | Action + owner in stage 05 | **Have it; needs levers/constraints depth** |
| 7. Learn from analyst and business-user feedback | **New** | **Gap** |
| 8. Realistic security, cost, latency, scalability constraints | **New** | **Gap** |

New in Round 2, to be designed rather than recalled:

- A **KPI / semantic contract** — definitions, calculations, drivers, thresholds,
  lineage, access restrictions. This is the formal home for the definition-drift check
  we already promised.
- **Personas** — at least two, receiving different narratives or recommended actions
  from the same investigation.
- **Role-based security and entitlements** — row, column and domain level.
- **Feedback and learning loops** — analyst correction and expert validation.
- **Sparse-history scenarios** — new products, categories or markets, where our
  "unusual for this series" test has little series to work with.
- **Runtime telemetry** — latency, model calls, token usage, estimated cost per insight.
- **An explicit LLM vs non-LLM breakdown** — which we are unusually well positioned to
  give, because the split was designed in from the start rather than reverse-engineered.

Deliverables: detailed business proposal (framing, solution design, target users,
business case, phased roadmap, risks and mitigations), working prototype of the core
mechanism on illustrative data, and a public GitHub repo with demo video and README.

---

## 10. Open questions to settle before building

Recorded here rather than resolved, so that the decisions are made deliberately:

1. **Which 3–5 connected KPIs, across which 2–3 sources?** They must have genuinely
   different grains or refresh cadences, and must be able to produce the multi-factor
   movement, the low-confidence case, and the sparse-history case we need to demo.
2. **Which two personas?** They should want visibly different things from the *same*
   case — not the same narrative at two reading levels. (A VP Sales who needs the action
   and the owner; an analyst who needs the decomposition and the eliminations, say.)
3. **How far into causal inference do we go?** The four challenge tests are deliberately
   leader-legible. Do they stay heuristics, or do they get formal statistical backing —
   and does formality cost us the explainability that made them good?
4. **What does "learning from feedback" actually change?** Hypothesis priors, materiality
   thresholds, evidence source weighting — or all three? Vague learning loops are
   hackathon filler; pick one and make it real.
5. **How is abstention demonstrated convincingly?** A demo where the system says "I don't
   know" needs to land as strength, not as a broken feature. It probably needs to be
   staged directly against a case it *does* resolve.
6. **Scope discipline.** Round 2 lists far more than any prototype can cover, and says
   so. We should build the spine end-to-end and go deep on the differentiator, rather
   than covering every bullet shallowly.

---

*Round 1 source material: `~/Downloads/AIC26_template/` — problem statements PDF,
`intructions.md`, `submission.md`, `script.md`, `casefile-deck.html`,
`Jerry_BusinessIntelligence.pdf`.*
