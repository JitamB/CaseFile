# Build Protocol

**CaseFile** · Accenture Innovation Challenge 2026 · Problem Track 3 — BusinessIntelligence.ai · Team Jerry

`Part IX · §41–47`

[← Glossary](08-glossary.md) · [Index](README.md)

---

# PART IX — HOW WE BUILD IT

The roadmap in [§32](05-execution.md) says *what ships when*. This says *how three people
ship it without colliding*, and how every change is proved before it lands.

**One rule underneath all of it:** nothing is "done" because someone says so. It is done
when a named command exits zero, on a machine that is not theirs.

---

## 41. Repository

**`github.com/JitamB/CaseFile`** — one repo, everything in it. The prototype, the docs, the
data generator, the frozen corpus. A judge clones once and has the whole project.

### 41.1 The settings in force

These are configuration, not convention — the protocol below is enforceable because of
them, not because anyone remembers it.

| Setting | State | Why |
|---|---|---|
| **Visibility** | Public | Round 2 requires it, and CI minutes are free on public repos |
| **Collaborators** | All three, write access | CODEOWNERS silently ignores anyone without write access |
| **Branches** | `main` only, plus short-lived work branches | Branches are per *work item*, never per *person*. A personal branch drifts for weeks and merges as one unreviewable lump |
| **`main` protection** | PR required · 1 approval · both CI jobs green · branch deleted on merge | No direct pushes, including the owner's |
| **`.github/`** | `CODEOWNERS`, `pull_request_template.md`, `workflows/ci.yml` | §42–43 — what makes review automatic instead of remembered |
| **`initials/`** | Committed | `docs/README.md` links into it, and `architecture-decision.md` shows four rejected architectures with reasoning — the depth a judge rewards. CI fails on a link into an uncommitted path, so this cannot silently regress |

The source tree from [§20](02-architecture.md) is scaffolded at ladder step 0.4, so
everyone's first feature PR adds files rather than directories.

### 41.2 What is committed, and what is not

| Committed | Why |
|---|---|
| `contracts/`, `personas/`, `probes/` | The system's configuration *is* the design |
| `data/generator.py`, `data/seed.txt` | `make data` must reproduce byte-identically |
| `data/corpus/` (frozen text) | Must not vary between runs — [§24](03-data.md) |
| `data/ground_truth.json` | Committed, but a lint rule forbids anything outside `tests/` from importing it |
| `fixtures/` | The golden objects both tracks build against |
| `docs/` | The design record |

| Ignored | Why |
|---|---|
| `.venv/`, `__pycache__/`, `.pytest_cache/` | Machine-local |
| `.env` | **API keys never enter the repo.** Commit `.env.example` with the key names and no values |
| `*.duckdb` | Regenerable by `make data`; a binary in git history is dead weight |
| `ui/node_modules/`, `ui/dist/` | Regenerable |
| `llm_cache/` *(decide at P0)* | Recorded LLM responses. **Recommendation: commit them** — they are what makes CI offline and the demo bulletproof |

### 41.3 The commands everything else refers to

One `Makefile`, owned by C, written on day one. Every verification in §44 is one of these.

```
make setup     venv + dependencies + pre-commit hook
make data      regenerate structured tables + ground_truth.json from the seed
make corpus    regenerate the frozen text corpus   (rare; needs an API key)
make demo      alert → closed case, end to end
make test      the full pytest suite
make check     ruff + mypy + pytest          ← exactly what CI runs
make gate N    run phase gate N's assertions  (pytest -m gateN)
```

**`make check` is the contract with CI.** If it passes locally it passes on GitHub. If those
two ever diverge, fixing the divergence is the highest-priority task in the project.

---

## 42. Branch and PR protocol

### 42.1 One ladder step, one branch, one PR

Branches are named `<track>/<step-slug>` — the prefix makes ownership visible in the branch
list without opening anything:

```
a/stats-did-placebo        b/s3-hypothesise        c/entitle-s8a
```

**Keep PRs small enough to review in ten minutes.** A ladder step from §44 is the right
size. If a PR grows past ~400 changed lines, it is two steps wearing one coat.

**Push daily, even unfinished.** Open it as a *draft* PR. A draft PR is how the other two
see what you are doing without asking, and it is where CI catches your mistake at hour four
instead of day three.

### 42.2 What a PR must contain

The template enforces it, so it cannot be forgotten:

```markdown
### Ladder step
<!-- e.g. 2.4 — challenge.py S5 -->

### Verification
<!-- the exact command, and its output pasted below -->
```
$ pytest tests/engine/test_challenge.py -q
....... 7 passed in 1.2s
```

### Crosses a track boundary?
<!-- no · or: which models.py type / which other track's module -->

### Gate advanced
<!-- G0–G6, or none -->
```

A PR with an empty Verification section does not get reviewed. That is not pedantry — it is
the entire reason the tracks can move in parallel without trusting each other.

### 42.3 Review rules

`.github/CODEOWNERS` requests the right reviewer automatically:

```
# Every PR gets its track owner. Shared surfaces get everybody.
/src/casefile/stats/          @its-adityagoyal
/src/casefile/data/           @its-adityagoyal
/contracts/                   @its-adityagoyal
/src/casefile/engine/verify.py     @its-adityagoyal
/src/casefile/engine/decompose.py  @its-adityagoyal

/src/casefile/llm/            @JitamB
/src/casefile/retrieval/      @JitamB
/probes/                      @JitamB
/src/casefile/engine/hypothesise.py @JitamB
/src/casefile/engine/evidence.py    @JitamB
/src/casefile/engine/challenge.py   @JitamB
/src/casefile/engine/adjudicate.py  @JitamB
/src/casefile/engine/recommend.py   @JitamB

/src/casefile/orchestrator.py @sahilgupta630
/src/casefile/api/            @sahilgupta630
/ui/                          @sahilgupta630
/personas/                    @sahilgupta630
/src/casefile/engine/entitle.py  @sahilgupta630
/src/casefile/engine/narrate.py  @sahilgupta630
/src/casefile/engine/feedback.py @sahilgupta630

# The treaty — all three, always
/src/casefile/models.py       @JitamB @its-adityagoyal @sahilgupta630
/fixtures/                    @JitamB @its-adityagoyal @sahilgupta630
/Makefile                     @JitamB @its-adityagoyal @sahilgupta630
/.github/                     @JitamB @its-adityagoyal @sahilgupta630
```

| Change | Approvals needed |
|---|---|
| Inside your own track | 1, from either other member — a sanity read, not an audit |
| Touches another track's module | 1, from **that track's owner** |
| `models.py`, `fixtures/`, `Makefile`, `.github/` | **All three**, and for `models.py` in the same sitting ([§30 rule 1](04-team.md)) |

**What is machine-enforced, and what is convention.** Branch protection hard-requires *one*
approval and green CI on every PR. The rest of the table is convention, carried by
CODEOWNERS auto-requesting the right reviewer. GitHub's stricter `require_code_owner_reviews`
is deliberately **off**: most paths have a single owner, and GitHub will not accept an
author's approval of their own PR — so turning it on deadlocks every solo-owned change.
Routing is automatic; judgement stays human.

**Squash-merge, delete the branch.** History stays one commit per ladder step, which makes
`git log` a build log.

### 42.4 Conflicts are a signal, not an accident

The tracks own disjoint directories. A merge conflict outside `models.py` means someone
edited across a boundary — resolve the *ownership* question in the sync, not the diff in the
editor.

---

## 43. CI — the impartial verifier

[`.github/workflows/ci.yml`](../.github/workflows/ci.yml) runs on every PR and every push to
`main`, as two jobs:

| Job | Runs | Catches |
|---|---|---|
| **docs** | [`tools/check_links.py`](../tools/check_links.py) | A relative link pointing at a path the repo does not track. Checked against `git ls-files`, not the filesystem — a link into an ignored directory resolves on your laptop and 404s on GitHub |
| **check** | [`tools/check_ground_truth_isolation.py`](../tools/check_ground_truth_isolation.py), then `ruff` · `mypy` · `pytest` | Anything outside `tests/` reaching for `ground_truth.json` ([§30 rule 3](04-team.md)), then lint, types and the suite |

The lint/type/test steps sit behind a `pyproject.toml` guard and are skipped with a notice
until ladder step 0.4 creates it. **Delete the guard as part of 0.4** — it is scaffolding,
not a feature.

**CI never reaches the network.** No API keys in Actions, no live model calls. This is
possible because of one Track B decision on day one: the LLM layer ships with a **replay
provider** that records real responses to `llm_cache/` and replays them by prompt hash.
Same mechanism makes the recorded demo immune to a bad model day ([§36 R4](06-quality.md)).

**Phase gates are pytest markers, not meetings.** `pytest -m gate1` is a real command that
either passes or does not:

```python
@pytest.mark.gate1
def test_scenario_d_closes_at_verify_with_no_model_calls():
    case = run_pipeline("net_revenue", "West", "2026-01")
    assert case.verification.passed is False
    assert case.telemetry.model_calls == 0
```

Once a gate passes, add its marker to the required checks on `main`. **A gate that has been
met can never silently regress.** That is the single highest-value line in this document.

---

## 44. The build ladder

Every step: who owns it, and the command that proves it. Steps within a phase are ordered by
dependency, not by importance — anything without a dependency on the row above can run in
parallel.

### P0 · Foundation — 3 days

| # | Step | Owner | Verify |
|---|---|---|---|
| 0.1 | Repo hardening (§41.1), `.github/` files, CI skeleton | Jitam | A throwaway PR is blocked without review; CI runs and is green |
| 0.2 | **`models.py` written together** — every type in [§14](02-architecture.md), [§30](04-team.md), incl. `Attribution`, `EvidenceItem.outcome/coverage`, `Case.priority` | **all three** | `pytest tests/test_models.py` |
| 0.3 | **Two fixtures hand-written** — `decomposition_east.json`, `case_east_8pct.json` | **all three** | Both validate against `models.py` |
| 0.4 | Repo skeleton, `pyproject.toml`, `Makefile` | Sahil | `make check` green on an empty suite |
| 0.5 | `llm/` — provider protocol, schema enforcement, `Usage`, **stub + replay cache** | Jitam | Stub round-trips a schema; replay returns a recorded response with the network off |
| 0.6 | `contract.py` + `net_revenue.yaml` + validator | Goyal | Validator rejects a contract missing an element or naming an unknown `owner_role` |
| 0.7 | `generator.py` — structured only, scenario A | Goyal | `make data` twice → byte-identical; the East −8% is visible in the tables |
| 0.8 | `loader.py` — DuckDB, conformance, watermarks | Goyal | Three sources join on `account_id`; one watermark per source |

**→ G0:** `make gate 0` — `make data` reproducible, contracts validate, fixtures validate.

### P1 · Deterministic spine — 5 days · zero LLM calls

| # | Step | Owner | Verify |
|---|---|---|---|
| 1.1 | `stats/` — STL, robust-z, PVM | Goyal | Each function matches a hand-computed value in the test |
| 1.2 | `stats/` — changepoint, Jaccard, Spearman, **DiD + placebo rank** | Goyal | Same. Placebo rank returns the real effect's position among 6 placebos |
| 1.3 | `verify.py` S1 — five checks, **definition epochs**, peer baseline, provisional path | Goyal | Scenarios D and E close with `telemetry.model_calls == 0` |
| 1.4 | `decompose.py` S2 — contribution, PVM, cross-KPI, concentration, `Footprint` | Goyal | `K(2) ≥ 0.85` on scenario A; cross-KPI residual ≤ 2% |
| 1.5 | Text corpus — generate, freeze, commit (templates for noise, authored for signal) | Jitam | 85% noise measured; the misleading documents are present and findable |
| 1.6 | `retrieval/` — footprint filter → BM25 + embeddings | Jitam | 45k → ~200 → top 15 on the East fixture |
| 1.7 | `entitle.py` S8a against the fixture | Sahil | **Security test green for all four personas** |
| 1.8 | `personas/*.yaml` — four specs | Sahil | All four load and validate |
| 1.9 | UI: case-file screen, fixture-driven | Sahil | Renders [§10](01-problem-and-solution.md) exactly |

**→ G1:** `make gate 1`. **This is the first demoable state, and it already proves the
thesis** — verification, decomposition and an honest verdict, with no model in the loop.

### P2 · Evidence and challenge — 7 days

| # | Step | Owner | Verify |
|---|---|---|---|
| 2.1 | `hypothesise.py` S3 — registry enumeration + LLM annotation | Jitam | **Hypothesis set identical across two runs**; an off-registry suggestion lands as `unmodelled` |
| 2.2 | `evidence.py` 4a — probes, three-way outcome, counted absence | Jitam | `checked_absent` carries a denominator; scenario B's probes return `uncheckable` with coverage ≈ 0 |
| 2.3 | `evidence.py` 4c — schema-forced extraction | Jitam | Every claim carries `doc_id` and a quoted span |
| 2.4 | `challenge.py` S5 — four tests | Jitam | Both decoys refuted on A; Dose `inconclusive` at n=2; Control reports placebo rank |
| 2.5 | `adjudicate.py` S6 — rubric, ceilings, ranked attribution, question, priority | Jitam | A → **Likely**, B → **Undetermined**, G → **Contested** |
| 2.6 | `recommend.py` S7 | Jitam | Seven fields; impact = at-risk × `save_rate`, labelled as an assumption |
| 2.7 | Remaining five contracts | Goyal | All six validate |
| 2.8 | Generator — scenarios B, C, D, E, F, G | Goyal | Each triggers its expected path |
| 2.9 | UI: case list (priority-ordered) + evidence drill-down | Sahil | Every claim links to its source; list order matches `case.priority` |

**→ G2:** `make gate 2`. The reasoning engine is now falsifiable against sealed ground truth.

### P3 · Surface — 6 days

| # | Step | Owner | Verify |
|---|---|---|---|
| 3.1 | `orchestrator.py` — wire A + B | Sahil | `make demo` runs alert → closed case |
| 3.2 | `narrate.py` S8b — per persona over the filtered case | Sahil | Four outputs, four **different recommended actions** |
| 3.3 | UI: persona switcher | Sahil | P4 sees masked names and banded ₹, with the redaction stated |
| 3.4 | Telemetry aggregation | Jitam | Cost < ₹10, latency < 10 s, LLM/non-LLM split correct |
| 3.5 | UI: telemetry panel | Sahil | Cost, latency and split on screen |
| 3.6 | Cadence upgrade path — provisional case re-runs on a late watermark | Sahil | Ceiling lifts and the verdict re-adjudicates when the 24h batch lands |

**→ G3:** `make gate 3`. **This is a complete submission.** Everything after is upside.

### P4 · Learning — 2 days

| # | Step | Owner | Verify |
|---|---|---|---|
| 4.1 | `feedback.py` S9 — priors, threshold tuning, gap promotion | Sahil | After 5 marks: gathering depth and presentation order shift; a contract gap appears in the registry |

**→ G4:** `make gate 4`.

### P5 · Optional — 3 days
Conversational follow-up over closed cases; the Unity Catalog masking seam. **Only if
genuinely spare** — first on the cut list (§47.3).

### P6 · Deliverables — 4 days

| # | Step | Owner | Verify |
|---|---|---|---|
| 6.1 | Squeeze/RiskLoc benchmark, **timeboxed to 2 days**, sets A and B0 first | Goyal | F1 recorded in the repo README beside published baselines |
| 6.2 | LLM/non-LLM measurement writeup | Jitam | Measured split and cost-per-case table in the README |
| 6.3 | Repo README + architecture diagram + screenshots | Sahil | A stranger can run it from the README alone |
| 6.4 | Business proposal (D1) | Sahil | Every element in [§39](07-outcome.md), incl. the competitive table from [§37](07-outcome.md) |
| 6.5 | Demo video ([§40](07-outcome.md) script) | Sahil | Ends on the ground-truth reveal |
| 6.6 | **Clean-machine test** | all three | Fresh clone on a machine that never built this: `make setup && make data && make demo && make test` |

**→ G6:** `make gate 6`.

---

## 45. Integration checkpoints

A phase gate is **a thirty-minute call with all three present**, not a status update.

```
1.  git clone into a fresh directory        ← not anyone's working copy
2.  make setup && make data
3.  make gate N                             ← run it live, together
4.  Green  → tick the gate, add its marker to the required checks on main
    Red    → the failure is the top of the next day's board, for whoever owns it
5.  Record the result and any decision in the log (§46.4)
```

**Do not start the next phase early.** The gates exist because the failure mode of a
three-person parallel build is three tracks that are each 90% done and have never met.

Two checkpoints matter more than the rest:

- **G0** — the treaty. `models.py` and the fixtures are frozen here. Every later schema change
  costs three people a context switch, so spend the time getting it right on day one.
- **G3** — the last point at which cutting is cheap. If G3 is late, cut in the order in §47.3
  rather than compressing P6. **A finished prototype with no video scores worse than a
  smaller prototype with one.**

---

## 46. Coordination

Three people, disjoint ownership, one treaty. The coordination load is deliberately low —
these are the only standing commitments.

### 46.1 Daily, async — three lines each

In one channel, before you stop for the day:

```
done:    1.3 verify.py — D and E close, model_calls 0   (PR #24, merged)
next:    1.4 decompose — contribution + footprint
blocked: no
```

Thirty seconds to write. Its purpose is not reporting — it is that the other two can see a
dependency arriving before they need it.

### 46.2 Twice weekly, live — 20 minutes, fixed agenda

Monday and Thursday. Same four items, in this order, every time:

1. **Gate status** — which gate are we on, what is left in it
2. **Open PRs** — anything waiting on a review, cleared on the call
3. **Open decisions** (§47.2) — any past its deadline
4. **Slippage** — is the critical path moving; if not, what gets cut

If it runs past twenty minutes, the overflow is a separate call with only the people
involved.

### 46.3 Blocked protocol

> **Nobody waits silently. Ever.**

| Situation | Do this |
|---|---|
| Stuck > 2 hours on your own module | Post it in the channel with what you have tried |
| Blocked on another track's output | **Switch to the fixture and keep moving** — that is what fixtures are for — then post it |
| Blocked > 1 day | It goes to the top of the next sync, and the coordinator re-plans around it |
| You need a `models.py` change | Stop. It needs all three in one sitting. Post it and use a local subclass until then |

### 46.4 Decision log

`docs/DECISIONS.md`, append-only, one line each:

```
2026-09-02  LLM provider: Claude, strict schema enforcement. Sonnet tier on the demo path.  — Jitam
2026-09-02  initials/ committed; README links now resolve on GitHub.                        — Jitam
```

Five weeks is long enough to forget why something was chosen, and a re-litigated decision
costs more than the original one did.

### 46.5 Who verifies whom

Verification is structural — each track's output is checked by the track that consumes it,
plus CI, which trusts nobody.

| Artifact | Built by | Consumed by | Verified how |
|---|---|---|---|
| `contracts/*.yaml` | Goyal | Sahil (reads `access`), Jitam (reads `drivers`) | Contract validator in CI |
| `stats/*` | Goyal | Jitam (S5 calls them) | Unit tests against hand-computed values |
| `ContributionTree`, `Footprint` | Goyal | Jitam | Must match `decomposition_east.json`; K(2) in range |
| `Case` (complete) | Jitam | Sahil | Schema validation + golden regression on `case_east_8pct.json` |
| `Telemetry` | Jitam | Sahil | Budget assertions: cost < ₹10, latency < 10 s |
| Entitlement | Sahil | everyone | **The security test** — restricted values absent from narrative, evidence *and* API payload |
| The whole pipeline | all three | the judges | The ground-truth harness ([§35.2](06-quality.md)) |

---

## 47. Coordinator's runbook

*Jitam — Track B plus coordination. Track B is the heaviest single track; the coordination
overhead below is deliberately kept to about two hours a week so it does not eat it.*

### 47.1 The weekly rhythm

| When | Do |
|---|---|
| **Monday sync** | Confirm each track's next three ladder steps. Anything not in §44 gets questioned |
| **Daily, 5 min** | Clear the review queue. A PR sitting overnight is a track blocked tomorrow |
| **Thursday sync** | Gate status and slippage. This is where a cut decision gets made, not the week after |
| **Gate days** | Run the gate live on a fresh clone (§45). Record it |
| **Continuously** | Watch the critical path: **A's generator is the long pole through P0–P2.** If it slips, B works on corpus and retrieval against fixtures, C works on UI against fixtures — neither should ever idle |

### 47.2 Open decisions — drive each to its deadline

| # | Decision | Owner | Due | Recommendation |
|---|---|---|---|---|
| D-1 | `initials/` committed or ignored | Jitam | Day 1 | **Commit.** It is a judge-facing asset and it fixes the dead README links |
| D-2 | LLM provider and tier | Jitam | End of P0 | **Claude, strict schema enforcement.** Sonnet tier for the demo path, Haiku for bulk extraction if cost bites. Telemetry reads a price table, so the tier stays configurable |
| D-3 | Commit `llm_cache/`? | Jitam | End of P0 | **Yes.** It is what makes CI offline and the recorded demo reproducible |
| D-4 | React or Streamlit for the UI | Sahil | End of P2 | Decide on measured progress, not nerves. If UI screens 1 and 2 are not rendering by G2, take Streamlit |
| D-5 | Repo and project name | Jitam | Before P6 | The repo is `CaseFile` today; renaming late breaks every link in the proposal and video |
| D-6 | Does P5 ship | all | After G4 | Default no |

### 47.3 The cut order, agreed in advance

When something has to go, it goes in this order — **decided now, so it is not an argument
in week four**:

```
1.  P5 entirely                          (conversational layer, platform seam)
2.  P4 feedback → keep threshold tuning only, document the rest as design
3.  React UI → Streamlit                 (same screens, less time)
4.  Squeeze benchmark run → keep the framing in the proposal, drop the run
5.  Scenario G (Contested)               (cheap; cut last)
```

**Never cut:** the P1 spine · the abstention path · the security test · telemetry · the
ground-truth reveal. Those five *are* the submission.

### 47.4 The three things that would sink this, and their early warnings

| Risk | Early warning | Response |
|---|---|---|
| **Generator calibration slips** (R3) — it is the largest artifact and everything depends on it | End of P0 and scenario A's −8% is not visible in the tables | Relax gates to ranges, not point values; ship scenario A alone and defer B–G to P2 |
| **Integration deferred to the end** (R2) | `make demo` has not run end to end by the middle of P3 | Stop feature work. Wire the orchestrator against whatever exists, including fixtures, and get one path green |
| **Deliverables crunch** (R5) | P6 opens with the business proposal unwritten | Draft the proposal incrementally from P1 — §1–2 and §37 are already written in these docs and need editing, not authoring |

---

[← Glossary](08-glossary.md) · [Index](README.md)
