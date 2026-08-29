# CaseFile — Documentation

**Accenture Innovation Challenge 2026 · Round 2**
**Problem Track 3 — BusinessIntelligence.ai**
**Team Jerry — IIT Kharagpur** · Jitam Barman · Sahil Kumar Gupta · Aditya Goyal

> **These eight files are the canonical project plan — the single source of truth.**
> Earlier working documents live in [`initials/`](../initials/) as background; where they
> disagree with `docs/`, `docs/` wins.

---

## The project in one line

> A deterministic pipeline that establishes facts, and calls a language model only where
> language is the actual problem — three times, never for a number.

---

## Files

| # | Document | Covers | Read if you want to know… |
|---|---|---|---|
| 01 | **[Problem & Solution](01-problem-and-solution.md)** | §1–12 | What we're solving, and what CaseFile is |
| 02 | **[Architecture](02-architecture.md)** | §13–20 | How it's built — stages, artifacts, stack, cost |
| 03 | **[Data](03-data.md)** | §21–25 | Where the data comes from, the KPIs, the scenarios |
| 04 | **[Team & Ownership](04-team.md)** | §26–31 | Who builds what, and the day-one protocol |
| 05 | **[Execution & Roadmap](05-execution.md)** | §32–34 | Phases, first week, phase gates |
| 06 | **[Testing & Risks](06-quality.md)** | §35–36 | How we prove it works, what could go wrong |
| 07 | **[Outcome](07-outcome.md)** | §37–40 | Differentiators, evaluation, deliverables, demo script |
| 08 | **[Glossary](08-glossary.md)** | — | Term lookup |
| 09 | **[Build Protocol](09-build-protocol.md)** | §41–47 | Repo, GitHub rules, the step-by-step ladder, coordination |

---

## Reading paths

**New to the project (~20 min)** → 01 → §37 in 07 → §40 demo script in 07

**Building it** → 01 → 02 → 04 (your track) → **09 (how we work, and your ladder steps)** →
05 → 03 as needed

**Writing the business proposal** → 01 → §19 cost in 02 → §36 risks in 06 → §38–39 in 07

**Preparing the demo** → §10 worked example in 01 → §25 scenarios in 03 → §40 script in 07

**Reviewing / judging** → §38 requirement audit in 07 → §17 LLM boundary in 02 → §35 testing in 06

---

## Section → file lookup

Cross-references in the text use `§N`. Resolve them here.

| § | Section | File |
|---|---|---|
| 1 | The Problem Statement | [01](01-problem-and-solution.md) |
| 2 | The Real Problem Underneath | [01](01-problem-and-solution.md) |
| 3 | What Round 2 Requires | [01](01-problem-and-solution.md) |
| 4 | Key Challenges | [01](01-problem-and-solution.md) |
| 5 | Objective | [01](01-problem-and-solution.md) |
| 6 | The Central Insight | [01](01-problem-and-solution.md) |
| 7 | What CaseFile Is | [01](01-problem-and-solution.md) |
| 8 | The Investigation Process | [01](01-problem-and-solution.md) |
| 9 | The Four Verdicts | [01](01-problem-and-solution.md) |
| 10 | Worked Example | [01](01-problem-and-solution.md) |
| 11 | User Flow | [01](01-problem-and-solution.md) |
| 12 | How Each Component Answers the Problem | [01](01-problem-and-solution.md) |
| 13 | Architecture Decision | [02](02-architecture.md) |
| 14 | The Three Core Artifacts | [02](02-architecture.md) |
| 15 | The Twelve Stages | [02](02-architecture.md) |
| 16 | Data Flow | [02](02-architecture.md) |
| 17 | The LLM Boundary | [02](02-architecture.md) |
| 18 | Technology Stack | [02](02-architecture.md) |
| 19 | Cost and Latency Budget | [02](02-architecture.md) |
| 20 | Repository Structure | [02](02-architecture.md) |
| 21 | Data Strategy | [03](03-data.md) |
| 22 | Sources and Schemas | [03](03-data.md) |
| 23 | The Six KPIs | [03](03-data.md) |
| 24 | The Generator | [03](03-data.md) |
| 25 | Seeded Scenarios | [03](03-data.md) |
| 26 | Ownership Map | [04](04-team.md) |
| 27 | Track A — Data & Truth | [04](04-team.md) |
| 28 | Track B — Evidence & Reasoning | [04](04-team.md) |
| 29 | Track C — Surface & Delivery | [04](04-team.md) |
| 30 | Interface Contracts | [04](04-team.md) |
| 31 | Day One Protocol | [04](04-team.md) |
| 32 | Roadmap | [05](05-execution.md) |
| 33 | Phase Gates | [05](05-execution.md) |
| 35 | Testing Strategy | [06](06-quality.md) |
| 36 | Risks and Mitigations | [06](06-quality.md) |
| 37 | Key Differentiators | [07](07-outcome.md) |
| 38 | Evaluation Criteria | [07](07-outcome.md) |
| 39 | Final Deliverables | [07](07-outcome.md) |
| 40 | Demo Script | [07](07-outcome.md) |
| 41 | Repository | [09](09-build-protocol.md) |
| 42 | Branch and PR protocol | [09](09-build-protocol.md) |
| 43 | CI — the impartial verifier | [09](09-build-protocol.md) |
| 44 | The build ladder | [09](09-build-protocol.md) |
| 45 | Integration checkpoints | [09](09-build-protocol.md) |
| 46 | Coordination | [09](09-build-protocol.md) |
| 47 | Coordinator's runbook | [09](09-build-protocol.md) |

---

## Per-person entry points

| Owner | Track | Start here |
|---|---|---|
| **Aditya Goyal** | A · Data & Truth | [§27](04-team.md) → then [§14.1 contract](02-architecture.md), [§15 stages 0–2](02-architecture.md), [§23–24 KPIs & generator](03-data.md) → your ladder steps in [§44](09-build-protocol.md) |
| **Jitam Barman** | B · Evidence & Reasoning **+ coordination** | [§28](04-team.md) → then [§15 stages 3–7](02-architecture.md), [§17 LLM boundary](02-architecture.md), [§19 cost](02-architecture.md) → and [§47 coordinator's runbook](09-build-protocol.md) |
| **Sahil Kumar Gupta** | C · Surface & Delivery | [§29](04-team.md) → then [§11 user flow](01-problem-and-solution.md), [§15 stages 8–10](02-architecture.md), [§39–40 deliverables & demo](07-outcome.md) → your ladder steps in [§44](09-build-protocol.md) |

**Everyone, before anything else:** [§31 Day One Protocol](04-team.md) — harden the repo,
write `models.py` together, hand-write the two fixtures. It is what stops the final week
becoming integration hell.

---

## Background documents (`initials/`, superseded by this directory)

| Document | Purpose |
|---|---|
| [architecture-decision.md](../initials/architecture-decision.md) | Full evaluation of the four rejected architectures — the "why not an agent / a platform / a knowledge graph" reasoning |
| [data-strategy.md](../initials/data-strategy.md) | Dataset survey and why we simulate, with source links |
| [casefile-concept-and-process.md](../initials/casefile-concept-and-process.md) | Round 1 concept carried forward |
| [round2-requirements-spec.md](../initials/round2-requirements-spec.md) · [casefile-foundation.md](../initials/casefile-foundation.md) · [MASTER-PROJECT-PLAN.md](../initials/MASTER-PROJECT-PLAN.md) | Earlier working drafts of what is now §14–25 — kept for archaeology only |
