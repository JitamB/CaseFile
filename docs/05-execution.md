# Execution & Roadmap

**CaseFile** · Accenture Innovation Challenge 2026 · Problem Track 3 — BusinessIntelligence.ai · Team Jerry

`Part VI · §32–33`

[← Team & Ownership](04-team.md) · [Index](README.md) · [Testing & Risks →](06-quality.md)

---

# PART VI — EXECUTION

## 32. Roadmap

Deadline is open, so phases are ordered by **cut priority: cut from the tail, never the
middle.** Estimates are working days with three people in parallel.

| Phase | Days | Delivers | Gate — done when |
|---|---|---|---|
| **P0 · Foundation** | 3 | `models.py`, fixtures, repo skeleton, contract schema + validator, generator (structured), DuckDB loader | Contract validates; `make data` reproducible; fixtures validate |
| **P1 · Deterministic spine** *(zero LLM)* | 5 | S0, S1, S2, `stats/`, S6 rubric, S10 skeleton, entitlement, case-file UI on fixture | Scenarios D + E close at Verify with **0 LLM calls**; K(2) ≥ 0.85 on A; UI renders §10 |
| **P2 · Evidence & challenge** | 7 | LLM layer, frozen corpus, S3, S4a/b/c, S5, S6 full, S7, ledger | Both decoys refuted; A = **Likely** with ranked attribution; Dose `inconclusive`; B = **Undetermined** + correct question; G = **Contested** |
| **P3 · Surface** | 6 | S8a/8b, 4 personas, full UI (5 screens), telemetry panel, orchestrator wired | `make demo` end to end; security test passes; cost + latency on screen |
| **P4 · Learning** | 2 | S9 feedback | After 5 marks, gathering depth and presentation order shift; contract gap promoted |
| **P5 · Optional** | 3 | Conversational follow-up over closed cases; one platform-native seam (Unity Catalog masking) | Only if genuinely spare |
| **P6 · Deliverables** | 4 | README, business proposal, demo video, Squeeze benchmark, clean-machine test | `git clone && make demo` works on a fresh machine |

**Critical path:** P0 → P1 → P2 → P3 → P6. **≈25 working days full · ≈21 without P4/P5.**

> **P1 alone is demoable and already proves the thesis** (verification + decomposition +
> honest verdict, with zero model calls). **If we ship only P1–P3 + P6, the submission is
> complete and honest.** That is the point of this ordering.

### Parallelism by phase

*`models.py` and the fixtures are written jointly on day 1 ([§31](04-team.md)); everything
below is parallel from that afternoon on.*

| Phase | A · Goyal | B · Jitam | C · Sahil |
|---|---|---|---|
| P0 | contract, generator, loader | LLM layer + replay cache | repo skeleton, Makefile, CI |
| P1 | `stats/`, S1, S2 | corpus, retrieval | entitle, personas, case-file UI |
| P2 | scenarios B–G, benchmark | S3, S4, S5, S6, S7 | UI screens 1, 3, 4 |
| P3 | contract polish, tuning | telemetry aggregation | orchestrator, narrate, telemetry panel |
| P4 | — | — | feedback |
| P6 | benchmark writeup | LLM/non-LLM measurement writeup | README, proposal, video |

---

## 33. Phase Gates

A phase is not done until its gate passes. **Do not start the next phase early.** Each gate
is a pytest marker (`pytest -m gate1`) run live on a fresh clone by all three —
[§45](09-build-protocol.md). The step-by-step ladder that fills each phase is
[§44](09-build-protocol.md).

| Gate | Test | Owner |
|---|---|---|
| **G0** | `make data` byte-identical across two runs; all 6 contracts validate; both fixtures validate against `models.py` | A |
| **G1** | Scenarios D + E close at Verify with `telemetry.model_calls == 0`; scenario A gives `K(2) ≥ 0.85`; cross-KPI residual ≤ 2% | A |
| **G2** | Scenario A: `pricing_change` = eliminated-as-primary (minor share retained), `competitor_launch` = Weak, `integration_delay` = **Likely** with `dose == "inconclusive"`. Scenario B = **Undetermined** with the expected discriminating question. Scenario G = **Contested** with both hypotheses at Likely | B |
| **G3** | `make demo` runs alert→case; security test green for all 4 personas; each persona's *action* differs; telemetry shows cost < ₹10 and latency < 10 s | C |
| **G4** | 5 feedback marks measurably shift evidence-gathering depth and presentation order; one contract gap promoted into a registry | C |
| **G6** | Fresh clone on a clean machine: `make data && make demo && make test` all green | C |

---

[← Team & Ownership](04-team.md) · [Index](README.md) · [Testing & Risks →](06-quality.md)
