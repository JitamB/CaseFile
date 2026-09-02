# Running the project

**Accenture Innovation Challenge 2026 · Team Jerry — IIT Kharagpur**

The full command sequence to take a fresh clone to a running system — setup, data, the
pipeline, continuous operation, and the UI. Everything below is a real command against this
repo, not a description of one; where a step needs something a prior step produces, that
dependency is stated. `docs/09-build-protocol.md` §41.3 is the canonical command reference
this file walks through in order; §45's own clean-machine sequence is step 1–3 below.

---

## 0. Prerequisites

| | Needed for |
|---|---|
| **Python 3.11+** | Everything under `src/`, `tests/`, `tools/` |
| **Node 18+** | The UI only (`ui/`) — skip it if you only want the pipeline |
| An **Anthropic/Gemini/Groq API key** | *Not* needed for anything below. `CASEFILE_LLM_REPLAY` defaults to `true`, and the three demoed calls already have recorded responses in `llm_cache/`. A key is only needed if you deliberately want a live model call — §9 below |

No database server, no Docker, no cloud account. DuckDB is a file; there is nothing to
stand up.

---

## 1. One-time setup

```bash
git clone <repo-url> && cd Accenture_Innovation-2026
python3 -m venv .venv && source .venv/bin/activate
make setup
```

`make setup` is `pip install -e ".[dev]"` — the package itself plus pytest/ruff/mypy. It
does not install the `embed` or `providers` extras (§18/`pyproject.toml`); add them only if
you need `sentence-transformers` or the Gemini/Groq SDKs specifically:

```bash
pip install -e ".[dev,embed,providers]"   # optional, not needed for anything below
```

Copy `.env.example` to `.env` if you want to override a default (provider, model tier). It
is a template, not auto-loaded — export the variables you need, or `set -a; source .env;
set +a` before running a command.

---

## 2. Generate the data

```bash
make data
```

Regenerates `data/raw/` (three sources: billing, crm, product_ops) from the committed seed
(`data/seed.txt`), then loads it into `data/casefile.duckdb` with one watermark per source.
Deterministic — running it twice produces byte-identical output (`§24`,
`test_two_runs_produce_identical_bytes`). Every other command below that touches real data
depends on this having run at least once; re-run it whenever you want a clean slate.

`data/ground_truth.json` (the injected events behind each seeded scenario) is written at the
same time. It is committed but lint-forbidden outside `tests/` — see `tools/check_ground_truth_isolation.py` in step 3.

The text corpus (`data/corpus/`) is committed frozen and does **not** regenerate with `make
data`. Only run this if you've changed the generator's document logic — it's slow and rarely
needed:

```bash
make corpus   # python -m casefile.data.generator && python -m casefile.data.corpus
```

---

## 3. Prove it works

```bash
make check
```

Exactly what CI runs, in order: `tools/check_ground_truth_isolation.py` →
`tools/check_links.py` → `ruff check src tests` → `mypy src` → `pytest -q` → `cd ui && npm ci
&& npm test && npm run build`. If this is green locally, it's green on GitHub.

For just the Python suite, or one phase gate's assertions:

```bash
make test          # pytest -q
make gate1          # pytest -m gate1 -q   (gate0..gate6 — §44)
```

---

## 4. Run one case, end to end

```bash
make demo
```

Depends on `data`, then runs `python -m casefile.orchestrator` — §10's worked example
(Net Revenue · East · 2026-04) through all nine stages, printing the verdict, primary
driver, recommended action, and the still-open question. Uses the recorded `llm_cache/`
responses for its three model calls (`CASEFILE_LLM_REPLAY=true` by default), so it needs no
API key and reaches no network.

---

## 5. Continuous operation — scan, replay, ingest

The scheduler-facing layer on top of a single case (`docs/continuous-operation-plan.md`):
sweeping every contract × region instead of one named case, persisting every scan to its
own store, and — piece 4 — simulating new data arriving over time so the watermark actually
advances run over run.

```bash
make scan
```
Depends on `data`. Sweeps all 6 contracts × 4 regions over the warehouse's own latest closed
period, writing `data/casestore.duckdb`. `StubProvider` by default (deterministic, zero
cost); pass `--live` (`python -m casefile.scan --live`) to use a real provider via
`provider_from_env()`.

```bash
make replay
```
Depends on `data`. The demo-facing proof of all four pieces together, in a tempdir case
store: walks the corpus's own last three real trailing months, then simulates two more
periods arriving and scans those too — `tools/replay_scan.py`.

```bash
make ingest
```
Deliberately does **not** depend on `data` — unlike the two above, this is meant to be
re-run repeatedly, each call chaining one further calendar month onto whatever's already in
`data/raw/`. Appends one new period of billing activity (and re-syncs crm's `account.csv`),
then rebuilds `data/casefile.duckdb` with the new watermark. Run `make data` once first on a
fresh clone — `src/casefile/data/ingest.py`. Running it N times in a row advances N periods:

```bash
make data && make ingest && make ingest   # lands on two periods past the frozen corpus
```

---

## 6. The UI

```bash
cd ui
npm install       # or: npm ci
npm run dev       # dev server, http://localhost:5173
npm test          # vitest
npm run build     # tsc --noEmit && vite build
```

No backend to run alongside it: the UI is fixture-driven, importing the golden `Case`
objects from `fixtures/` at the repo root directly (`@fixtures` alias in `vite.config`), not
fetching them from a server. `src/casefile/api/` is scaffolded but not yet implemented — the
pipeline and the UI both run standalone.

---

## 7. Rebuilding fixtures (only after a pipeline or contract change)

Not part of `make check` — run by hand, and only when something they depend on changes:

```bash
python tools/build_real_case_fixtures.py     # fixtures/case_real_scenario_{a,b,d}.json
python tools/build_entitled_fixtures.py      # fixtures/case_east_8pct_entitled.json
python tools/build_real_entitled_fixture.py
python tools/calibrate_materiality.py        # measures the anomaly-band false-positive rate
```

Each script's own docstring says exactly what changed upstream should trigger a re-run.

---

## 8. Using a live LLM instead of replay

Every command above defaults to `CASEFILE_LLM_REPLAY=true` — recorded responses, no network,
no key. To make a real call:

```bash
export LLM_PROVIDER=anthropic        # or google, groq
export ANTHROPIC_API_KEY=...         # the credential matching whichever provider you set
export CASEFILE_LLM_REPLAY=false
python -m casefile.orchestrator      # or: python -m casefile.scan --live
```

A prompt with no recorded response and `CASEFILE_LLM_REPLAY=true` fails loudly
(`CacheMiss`), not silently — the error message names the exact fix.

---

## Quick reference

| Command | Depends on | Does |
|---|---|---|
| `make setup` | — | Install the package + dev tools |
| `make data` | — | Regenerate the corpus, load the warehouse |
| `make corpus` | — | Regenerate the frozen text corpus (rare) |
| `make check` | `data` (transitively, via `pytest`) | Exactly what CI runs |
| `make test` | `data` (transitively) | `pytest -q` |
| `make gateN` | `data` (transitively) | One phase gate's assertions |
| `make demo` | `data` | One case, end to end, §10's worked example |
| `make scan` | `data` | Sweep every contract × region, write the case store |
| `make replay` | `data` | 3 frozen + 2 simulated periods, one transcript |
| `make ingest` | `data` (once, not per-call) | Append one new period, chainable |
| `cd ui && npm run dev` | — | The UI, against committed fixtures |
