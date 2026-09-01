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

## High-value

| # | Step | Files touched | Why | Verify |
|---|---|---|---|---|
| ADA-4 | Plain-language "why not Confirmed" sentence on every Contested/Undetermined verdict | `src/casefile/engine/narrate.py` (`_prompt`, `_tokens`, and whichever `_fallback_*` covers the explanation section) | ADA's evidence cards never bury a caveat — *"this cannot be told apart from no relationship at all," "carried by a few extreme records rather than the bulk of the data."* Our own Stage 5/6 already compute the ingredients (which of the 4 tests failed, and the discriminating question that would resolve it) but that reasoning currently lives inside `adjudicate.py`'s internals rather than being guaranteed to surface as a sentence in every narrated case | A test over a Contested and an Undetermined fixture case asserts the narrated output for **every persona** contains a plain-language clause naming the specific failed test(s) — not just a confidence label |
| ADA-5 | Surface concentration as "N segments carry the risk of M equal ones" | `src/casefile/engine/decompose.py` (`_hhi`, near `decompose.py:383`), whichever narration/UI template currently renders `ContributionTree.concentration` | `_hhi()` already computes the Herfindahl index (`decompose.py:383`) — ADA's `_effective_segments()` in `business_insights.py` is the same index inverted into a legible sentence (*"the N of them carry as much risk as M equally sized ones"*), which reads better to a CFO/VP-Sales persona than a bare HHI float | Add `1/hhi` as a `float | None` alongside the existing `hhi` field (mirroring the `None`-when-undefined guard ADA uses for negative shares); one test asserts the identity `effective_segments == 1/hhi` on a real decomposition, and that the field is exposed wherever `hhi` already is |
| ADA-6 | Re-verify (or fix) the DuckDB-specific-SQL-in-probes finding before repeating "Snowflake is a connector swap" in submission material | `src/casefile/engine/evidence.py` (`_sql`, `_ticket_spike`, `_price_delta`, `_lost_reason_scan`, `_incident_scan` — `evidence.py:142` onward), `probes/*.sql` | Flagged in an earlier critical review and not yet re-checked this session. It's exactly the kind of overclaim a "highly critical external reviewer" (ADA's own docs never overclaim past what the code does) would catch, and it directly undercuts the "production scalability" answer in [§18](02-architecture.md) | Either (a) audit the five probe SQL strings for DuckDB-only syntax and replace with ANSI-portable equivalents where cheap, or (b) if a genuine DuckDB-ism is load-bearing, soften the specific claim in §18 to name the actual cost ("a connector change plus a probe-dialect pass") instead of "a connector swap." Pick (a) unless it's non-trivial; either way, the doc and the code must agree — that's the pass condition, not a specific SQL rewrite |

## Optional

| # | Step | Files touched | Why | Verify |
|---|---|---|---|---|
| ADA-7 | Read-only NLQ over the already-filtered `Case` object (not the raw warehouse) | `ui/src/` (new panel), a thin new query layer scoped to one `Case`'s own evidence/ledger fields | The narrow, in-scope version of ADA's `nlq.py`: demo polish, zero new causal claims, reuses data a persona is already entitled to see post-Stage-8a. **Not** a Round 2 requirement — only pick this up after P3/P4 are both done | A handful of canned questions against a fixture `Case` return answers sourced only from that case's own fields, never a fresh warehouse query |
| ADA-8 | Live deployment of the FastAPI + React stack | deployment config only, no source changes | Strengthens the "practical value" optics the way ADA's live Streamlit demo does — zero bearing on the Round 2 grading rubric as written | A reachable URL that renders a real case end to end |

---

## Suggested sequencing

1. **ADA-1** first, unconditionally — it's a Round 2-mandatory objective with no code yet,
   independent of everything else in this file.
2. **ADA-2** and **ADA-3** next, in either order — both are small, additive, test-only-plus-one-tool
   changes with no risk to existing behavior, and both close trust gaps raised directly in this
   session (materiality asserted-not-measured; "how did you make this without an LLM" for narration
   generally).
3. **ADA-4**–**ADA-6** after P4 closes, same branch → PR → CI → merge discipline as every other
   ladder step this session ([§42](09-build-protocol.md)), each its own PR.
4. **ADA-7**/**ADA-8** only if genuinely spare, same rule §47.3 already applies to the existing
   P5 optional items — first on the cut list, not before P4 and the high-value items are done.

Log each step's outcome in [`docs/DECISIONS.md`](DECISIONS.md) on merge, same convention as
every other real finding this session (the Gemini/Groq bugs, the ratio-attribution bug) — a
measured calibration number or a "no DuckDB-ism found" result is exactly the kind of thing
that belongs there, not just in a PR description.
