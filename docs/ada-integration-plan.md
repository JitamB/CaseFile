# Integration Plan — lessons from Automated Data Analyst (ADA)

**Not one of the nine canonical docs** ([docs/README.md](README.md)) — this is a derived,
addendum plan produced from a direct source read of
[github.com/saineshnakra/automated-data-analyst](https://github.com/saineshnakra/automated-data-analyst),
compared against our own [§02 Architecture](02-architecture.md) and [§01 Problem & Solution](01-problem-and-solution.md).
The comparison itself isn't repeated here — this file is only the actionable output of it:
what to build, in which file, why, and how to know it worked. Where this disagrees with the
nine canonical docs, the canonical docs still win; this file proposes changes to them.

**Verdict the plan rests on:** ADA solves an adjacent, shallower problem (explain any
uploaded spreadsheet, no causal claim) and explicitly disclaims doing what CaseFile's
core mechanism does (falsification-tested root cause, verdict rubric, entitlement,
persona narration). The overlap doesn't threaten differentiation. But ADA is more
rigorous than us in a few specific, narrow places, and reading it surfaced one gap
(P4/Feedback) that has nothing to do with ADA at all — it's just conspicuous by contrast.

---

## Non-goals (explicitly not adopting)

Recorded here so this file is a complete answer, not just the half that adds work:

- Generic "any CSV" schema inference — dilutes the governed-contract differentiator, not
  asked for by Round 2.
- ADA's `nlq.py` as a general free-text query planner over arbitrary columns — see the
  Optional section below for the narrow, in-scope version of this idea.
- Streamlit — already committed to React for persona/entitlement-filtered views.
- ADA's forecasting module wholesale — Round 2's 8 objectives don't ask for a forecast;
  see High-value #3 for the honesty *pattern* worth borrowing without the feature.
- Cohort/retention analysis, cross-sheet joins, multi-file comparison — ADA's own
  roadmap items, irrelevant to a fixed KPI/contract model.

---

## Where this sits relative to the existing ladder

Per [§44 The build ladder](09-build-protocol.md): P1–P3 are merged (main is past 3.6).
**P4 (`feedback.py`, ladder step 4.1) has not been started** — no `feedback.py`,
no `tests/test_feedback.py` exist in the repo today. The steps below are new work,
labelled `ADA-1`…`ADA-8` so they're never confused with the canonical `0.x`–`6.x`
step IDs. `ADA-1` *is* ladder step 4.1 — it's listed here only to fix its priority
in one place; it is not a new design.

---

## Critical — done, verified

All three shipped: 552 tests pass (`pytest -q`), `ruff check src tests` and `mypy src`
both clean, `pytest -m gate1`/`gate2`/`gate3`/`gate4` all pass, `tools/check_ground_truth_isolation.py`
clean. Each was mutation-tested by hand before being counted done (a real bug or
regression introduced on purpose, confirmed caught by a failing test, then reverted) —
see each entry's own `docs/DECISIONS.md` entry for specifics. Not committed or pushed —
per standing instruction, the exact diff is shown for review first; see the handoff
commands at the bottom of the conversation this was implemented in.

| # | Step | Files touched | Why | Verify | Status |
|---|---|---|---|---|---|
| ADA-1 | Finish `feedback.py` S9 (ladder step 4.1) | `src/casefile/engine/feedback.py` (new), `tests/test_feedback.py` (new) | Round 2 objective 7 is mandatory and currently has **zero code** — the sharpest gap this whole exercise surfaced, independent of ADA | Per [§44 P4](09-build-protocol.md#44-the-build-ladder): after 5 marks, gathering depth and presentation order shift; a contract gap promotes into the registry | ✅ 21 tests, `pytest -m gate4` |
| ADA-2 | Calibrate the S1 materiality gate | `tools/calibrate_materiality.py` (new), `tests/test_materiality.py` (extended), `docs/06-quality.md` §35.6 (new) | `stats/materiality.py::assess()`'s own docstring already states a measurement — *"four regions, the trailing twelve periods, 48 region-periods... exactly three cases"* — but that's **one seed's one narrative**. ADA's `tools/calibrate_anomalies.py` earns its "≈1 in 20" claim by simulating stable synthetic series directly against its own detector function; the equivalent here simulates directly against `assess()` the same way, not against the domain generator (whose scenarios turned out to be seed-invariant by construction, not random — see the DECISIONS.md entry) | Measured, 3,000 trials/contract: 0.00%–0.43% false-alarm rate across all six contracts, comfortably under ADA's own 5% reference target. `test_the_gate_rarely_fires_on_genuinely_stable_data` is the fast (500-trial) regression guard on that property | ✅ table in §35.6 |
| ADA-3 | Regression test: no raw warehouse value ever reaches an LLM prompt | `tests/test_no_raw_data_in_prompts.py` (new) | ADA's `ai_insights.py::build_ai_payload`/`build_planner_payload` are *structurally* incapable of serializing a raw row — they only ever call `asdict()` on computed dataclasses. Our own equivalent guarantee ("the LLM never sees raw rows") was a doc claim (§17), not a test — exactly the kind of gap the user's own "how did you make this without an LLM" question flagged as a trust concern this session | A real `amount_net` invoice-line figure (₹31,66,475.00) for scenario A's own ACC-0001, queried from the real generated warehouse, checked against the real `Prompt.system`/`.user` text each of S3/S4c/S8b actually constructs from the real `case_real_scenario_a.json` fixture | ✅ 4 tests across gate1/2/3 |

## High-value — done, verified

All three shipped: 556 backend tests pass, `ruff`/`mypy` clean; UI: 42 tests pass
(`npm test`), `npm run build` (tsc + vite) clean. Mutation-tested by hand — see each
entry's own `docs/DECISIONS.md` line.

| # | Step | Files touched | Why | Verify | Status |
|---|---|---|---|---|---|
| ADA-4 | Plain-language "why not Confirmed" sentence on every Contested/Undetermined verdict | `src/casefile/engine/narrate.py` (new `_why_not_confirmed`/`_limiting_test`, appended post-guardrail in `narrate()`) | ADA's evidence cards never bury a caveat. Our own Stage 5 already computes the ingredients (`TestResult.detail`) but nothing guaranteed it reached a narrated page | Real scenario B (Undetermined) + a synthetic Contested case: the clause names the limiting test for every contender, appended even when the model's own text already passes the guardrail (not just on the fallback path) | ✅ 5 new tests in `tests/test_narrate.py` |
| ADA-5 | Surface concentration as "N accounts carry the risk of M equal ones" | `ui/src/blocks/WhereItCameFrom.tsx` | `tree.hhi` was already flowing through every case's JSON and `types.ts` — just never rendered. ADA's `_effective_segments()` is the same 1/HHI inversion into a legible sentence | New `ui/src/__tests__/WhereItCameFrom.test.tsx` (5 tests) — the block's first dedicated test file | ✅ pure frontend change, no backend/schema touch needed |
| ADA-6 | Re-verify the DuckDB-specific-SQL-in-probes finding before repeating "Snowflake is a connector swap" | `docs/02-architecture.md` §18 (corrected claim) | Real audit found it: 3 of 4 `probes/*.sql` files use DuckDB's own `UNNEST($array_param)` idiom (not a one-line Snowflake port), plus a `FILTER (WHERE ...)` clause Snowflake doesn't support | The doc now names the actual cost — a probe-dialect rewrite alongside the connector swap — instead of asserting a swap alone. No SQL rewrite attempted; untestable against a real Snowflake instance from here, so the honest move was correcting the claim, not a speculative fix | ✅ §18 corrected |

## Optional

| # | Step | Files touched | Why | Verify |
|---|---|---|---|---|
| ADA-7 | Read-only NLQ over the already-filtered `Case` object (not the raw warehouse) | `ui/src/` (new panel), a thin new query layer scoped to one `Case`'s own evidence/ledger fields | The narrow, in-scope version of ADA's `nlq.py`: demo polish, zero new causal claims, reuses data a persona is already entitled to see post-Stage-8a. **Not** a Round 2 requirement — only pick this up after P3/P4 are both done | A handful of canned questions against a fixture `Case` return answers sourced only from that case's own fields, never a fresh warehouse query |
| ADA-8 | Live deployment of the FastAPI + React stack | deployment config only, no source changes | Strengthens the "practical value" optics the way ADA's live Streamlit demo does — zero bearing on the Round 2 grading rubric as written | A reachable URL that renders a real case end to end |

---

## Suggested sequencing

1. ~~**ADA-1** first, unconditionally~~ — ✅ done.
2. ~~**ADA-2** and **ADA-3**~~ — ✅ done.
3. ~~**ADA-4**–**ADA-6**~~ — ✅ done.
4. **ADA-7**/**ADA-8** — still open, Optional tier, only if genuinely spare, same rule §47.3
   already applies to the existing P5 optional items — first on the cut list.

Critical and High-value are both fully shipped. Only the two Optional items remain.

Log each step's outcome in [`docs/DECISIONS.md`](DECISIONS.md) on merge, same convention as
every other real finding this session (the Gemini/Groq bugs, the ratio-attribution bug) — a
measured calibration number or a "no DuckDB-ism found" result is exactly the kind of thing
that belongs there, not just in a PR description.
