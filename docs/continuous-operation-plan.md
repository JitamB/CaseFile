# Continuous operation — scan, scheduler, case store (pieces 1–3 of 4)

**Not one of the nine canonical docs** ([docs/README.md](README.md)) — an addendum, same
convention as [`docs/ada-integration-plan.md`](ada-integration-plan.md). Own step-ID prefix
(`CO-1`…) so it never collides with the canonical `0.x`–`6.x` ladder or `ADA-1`…`ADA-8`.

## Context

`orchestrator.run_case()`'s own `_main()` docstring admits the gap outright: *"which case to
open is not yet a solved problem in this codebase... this is the one case named on stage."*
Round 2 objective 1 ("detects and prioritises material KPI movements") and §11's own "daily
loop" narrative ([01-problem-and-solution.md](01-problem-and-solution.md)) describe exactly
this — a system that looks at every KPI x region slice on a cadence and opens the ones worth
attention. D2 explicitly allows "illustrative data, need not be production-grade," so this was
never a missing requirement, but the architecture already had the seams for it
(`contract.refresh.cadence`, per-source `meta.watermark`, a proven provisional/re-run
mechanism) without the wiring.

Pieces 1–3 (scan, scheduler, case store) are built and verified here. **Piece 4 — live data
ingestion — stays explicitly out of scope.** The corpus remains the one frozen, seeded
warehouse every other module already reads; "continuous" means the scan loop is real, tested
code, not that new data arrives on its own.

## Design decisions, validated against real code

1. **Region is the uniform scan dimension.** All six contracts declare `region` as
   `decomposition_dims[0]`, and exactly four regions exist corpus-wide.
   `scan.regions()` queries them directly (`SELECT DISTINCT region FROM crm.account WHERE
   region IS NOT NULL AND NOT is_test`) rather than hardcoding — the same shape
   `verify.py`'s own `_peer_expectation` already uses, plus the `is_test` exclusion
   `net_revenue.yaml`'s own formula filter already implies.

2. **`scan_slice()` is a thin wrapper over `run_case()`, not a separate `verify()` +
   `run_case()` pair.** `run_case()` already calls `verify()` first and returns immediately
   with zero LLM calls on failure. Verifying twice would double-pay `verify()`'s real cost
   (~80–100 SQL round-trips per call, dominated by materiality's 36-period history scan) for
   nothing.

3. **The case store is a separate DuckDB file — `data/casestore.duckdb` — never
   `data/casefile.duckdb`.** `loader.build()` unconditionally deletes and rebuilds the
   warehouse file on every `make data`; any table added there would be wiped on the next run.
   A separate, loader-untouched file also avoids read-only/read-write connection contention
   with everything that already opens the warehouse read-only. Already covered by the
   existing `*.duckdb` gitignore rule.

4. **Every scanned slice is persisted, not just the ones that open a case.** `run_case()` runs
   per candidate regardless, so persisting adds no cost, and it gives the audit trail the
   project's own tests already treat as a first-class property ("48 chances to cry wolf... the
   gate takes exactly three of them") — without it, nothing can answer "did we actually check
   East this month."

5. **Provider defaults to `StubProvider()`**, matching `test_cadence_upgrade.py` and
   `tools/build_real_case_fixtures.py`'s own precedent — deterministic, offline, zero cost,
   safe for CI and the replay demo. `provider_from_env()` stays available as an explicit
   `--live` opt-in on the CLI, mirroring how `orchestrator._main()` already fails loudly, not
   silently, on a live-provider gap.

6. **The scheduler is real, tested, in-process code — `run_scheduled()`** — "a Python function
   on a timer," explicitly not Airflow/Kafka/a daemon framework. Injectable `sleep` and an
   iteration cap make it unit-testable without a real wait. An OS-level crontab/systemd-timer
   example is the documented *production* answer (below), not built or tested here —
   environment-specific, out of scope for this repo.

7. **The frozen corpus can't demonstrate "time advancing" by itself.** `AS_OF`/`SPAN_END` are
   fixed constants baked into the seed, so `latest_closed_period()` resolves to the same
   period every tick against the stock warehouse. The demonstration instead comes from
   `tools/replay_scan.py` walking the corpus's own already-existing trailing periods, and from
   reusing `test_cadence_upgrade.py`'s exact watermark-mutation technique for the
   provisional-upgrade proof. Nobody should expect the scheduler to show something new against
   the static seed alone.

8. **Ground truth for `scan.py`'s own end-to-end test is `test_verify.py`, not
   `test_materiality.py`.** `test_materiality.py`'s own full-corpus test proves 4 slices pass
   *materiality alone* (pre-`verify()`, net_revenue only). The number that matches what
   `scan()` actually does (full `run_case()` → full `verify()` per slice) is
   `tests/test_verify.py::test_exactly_one_movement_in_the_whole_corpus_survives_verify`:
   across the 4-region × trailing-12-period grid, **exactly one survives** (East/2026-04), and
   three of the four materiality-passing candidates close with named reasons. Reproducing this
   through `scan_slice()` (real `run_case()` cost, not `verify()` alone) is
   `tests/test_scan.py::test_the_slice_level_backtest_reproduces_verifys_own_survivors` — the
   real proof this module does not change Stage 1's own established outcome. It pre-filters by
   materiality first, the same optimisation `test_verify.py`'s own test already uses, so the
   heavier `run_case()` cost is paid only for the 4 slices that need it, not all 48.

9. **`casestore.list_cases(open_only=...)`** reads `verification.passed` — `Case` has no
   separate status field, and this is the one existing boolean the rest of the test suite
   already treats as "worth attention" versus "closed for a documented reason." The flat
   `provisional`/`confidence`/`kpi`/`period`/`dimensions`/`priority` columns exist for the
   same reason (a lightweight query without deserialising `payload`) and are checked directly
   in `tests/test_casestore.py::test_the_flat_columns_match_the_cases_own_fields` — the one
   place a mistake in `save()`'s column mapping for them would be caught at all.

10. **A real gap `scan()` found, not assumed — 7 of 24 real slices cannot even be verified.**
    Every existing test in this repository picks a known-good contract/period/region by hand;
    `scan()` is the first thing here that sweeps every contract against every region blindly.
    Measured against the real committed warehouse (all six contracts, each at its own
    `latest_closed_period()`, all four regions): `verify()` itself raises before returning a
    result for 7 of the 24 resulting slices —

    - `_movement()`'s own `VerifyError` ("no previous period to compare against") for a ratio
      or ARR-flow KPI with nothing due in one of the two compared periods for that region
      (`gross_renewal_rate`/APAC, `new_business_arr`/APAC, `nrr`/APAC), and
    - a bare `ValueError` from `stats/stl.py` ("STL needs two full cycles") for a region whose
      *own* value series has fewer non-null observations than `verify.py`'s
      `_history_is_sparse()` assumes — that check reads the calendar span between
      `contract.history_start` and the period end, not the count of actually-defined values,
      and a region with gaps (no renewals due some months) can have a long enough calendar
      span but still too few real observations for STL's own two-cycle requirement
      (`gross_renewal_rate`/North and West, `nrr`/North and West).

    Both are pre-existing Stage 1 gaps, not introduced by this module — out of scope to fix
    here: touching `verify.py`'s sparse-history detection risks shifting the materiality
    false-alarm calibration already measured and committed in
    [06-quality.md §35.6](06-quality.md) (`docs/ada-integration-plan.md`'s ADA-2). `scan()`
    treats either as "not scannable this period," not a crash — counted in
    `ScanSummary.slices_unverifiable`, the sweep continues — the same "closing early is a
    success path" principle `run_case()` already applies one level up, extended one step
    further to "not opening at all is also not a crash." Logged here rather than fixed,
    matching the treatment `docs/ada-integration-plan.md`'s own out-of-scope findings and
    `docs/DECISIONS.md`'s "Scenario G attempted and deferred" entry already got.

Both open questions from the validation pass were put to the user directly and confirmed:
**all six contracts per scan** (not narrowed to `net_revenue` first — decision 10 above is a
direct, measured consequence of that choice), and **real `run_scheduled()` code**, not
documentation-only.

## Files — done, verified

571 backend tests pass (`pytest -q`, up from 552 before this work), `ruff check src tests` and
`mypy src` both clean, `tools/check_ground_truth_isolation.py` and `tools/check_links.py` both
clean. Every load-bearing piece of logic was mutation-tested by hand before being counted done
(a real bug introduced on purpose, confirmed caught by a failing test, then reverted) — see
`docs/DECISIONS.md` for specifics, including one real test-coverage gap the mutation pass
itself found and closed (the case store's flat columns had no test reading them back at all).

| # | Piece | Files | Verify | Status |
|---|---|---|---|---|
| CO-1 | Scan — `latest_closed_period`, `regions`, `scan_slice`, `scan` | `src/casefile/scan.py` (new) | `tests/test_scan.py`: period/region lookups (incl. the `>=` month-end boundary), the all-six-contracts sweep (decision 10), the `gate1`-marked slice-level backtest against `test_verify.py`'s own survivors | ✅ |
| CO-2 | Scheduler — `run_scheduled` | `src/casefile/scan.py` | `tests/test_scan.py`: `iterations=3` with a fake `sleep`, `scan()` itself replaced via `monkeypatch` — zero real wait, zero real `run_case()` cost | ✅ |
| CO-3 | Case store | `src/casefile/casestore.py` (new) | `tests/test_casestore.py`: round-trip save/load, upsert-not-duplicate, `open_only` filter, priority ordering, flat-column integrity; `tests/test_scan.py`'s cadence-upgrade test proves the store upserts the same `case_id` in place when a provisional case's ceiling lifts (reusing `test_cadence_upgrade.py`'s own watermark-mutation technique) | ✅ |
| CO-4 | Demo-facing proof | `tools/replay_scan.py` (new), `Makefile` (`scan`/`replay` targets) | `python tools/replay_scan.py` / `make replay` walks 2026-02 → 2026-04 against a fresh generated corpus, printing a §11-shaped transcript; `make scan` runs against the committed warehouse and populates `data/casestore.duckdb` | ✅ |
| CO-5 | Piece 4 — live data ingestion | — | out of scope, deliberately deferred | not started |

## The OS-level production answer (documented, not built)

`run_scheduled()` proves the loop's own logic; the actual production deployment is an
OS-level timer calling the module's CLI entrypoint on each contract's own `refresh.cadence`,
e.g.:

```cron
# billing/crm refresh daily — run the sweep once after each day's batch lands
0 7 * * *  cd /opt/casefile && python -m casefile.scan --live >> /var/log/casefile-scan.log 2>&1
```

or the equivalent `systemd` timer unit calling the same command. This is genuinely
environment-specific (which host, which secrets manager for the live API key, log rotation)
and not something this repository's own test suite can prove — stated here as the documented
answer rather than asserted as done.

## Verification

1. `pytest -q`, `ruff check src tests`, `mypy src` — same bar as every change this session. ✅
2. `tools/check_ground_truth_isolation.py`, `tools/check_links.py` — same bar `make check`
   holds every change to. ✅
3. `python tools/replay_scan.py` runs end to end against a fresh `generate()`+`build()` corpus
   and produces a real, inspectable transcript. ✅
4. `python -m casefile.scan` (`make scan`) runs against the committed `data/casefile.duckdb`,
   populates `data/casestore.duckdb`, and prints a `ScanSummary`. ✅

Not committed or pushed — per standing instruction, the exact diff is shown for review first.
