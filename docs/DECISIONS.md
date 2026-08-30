# Decision log

Append-only, one line each — §46.4. Five weeks is long enough to forget why something was
chosen, and a re-litigated decision costs more than the original one did.

Newest last.

```
2026-08-29  initials/ stays local; the README describes it in prose rather than linking in.   — Jitam
2026-08-29  Rebase-only merges, branch deleted. main's log reads as a build log at task granularity. — Jitam
2026-08-29  Ladder order: 0.4 before 0.2. Without pyproject.toml, CI verifies nothing on models.py. — Jitam
2026-08-29  Default deps are pydantic only; statsmodels/sentence-transformers go behind extras CI does not install. — Jitam
2026-08-29  Gate command is `make gateN`, not `make gate N` — two-word make goals need a MAKECMDGOALS hack. — Jitam
2026-08-29  models.py and fixtures/ drafted solo while A and C await invites; both PRs stay open for their review before merge (§30 rule 1 deferred, not waived). — Jitam
2026-08-29  models.py carries three validators only: counted absence, coherent ranking, abstention-with-question. Everything else is a test. — Jitam
2026-08-29  D-3 settled: llm_cache/ is committed. §41.2 moved the row from Ignored to Committed. — Jitam
2026-08-29  No live provider at 0.5 — stub + replay only. AnthropicProvider lands at 1.5 with the first real prompt; shipping it earlier means unlinted, untyped code CI cannot install. — Jitam
2026-08-29  LLMProvider.complete is generic in T, not §18's literal `-> tuple[BaseModel, Usage]`. Same protocol, but call sites keep their types under disallow_untyped_defs. — Jitam
2026-08-29  CASEFILE_LLM_REPLAY defaults to on. Fail safe, not fail open: a missing var yields a CacheMiss, never a live call nobody intended to pay for. — Jitam
2026-08-29  Usage.cache_hit means the *provider's* prompt cache (§19), not the replay cache; replay never sets it. A cached_input_tokens field is the honest fix — treaty change, raise at the next sync. — Jitam
2026-08-30  §24's onset is 2026-03-12, not 2026-04-12, and the renewal lag U(18,30): §10's "21 and 23 days" and an April loss cannot both hold with an April onset. — Jitam
2026-08-30  The two treated accounts' renewal failure is injected, not sampled. §24 chooses the exogenous events; the model's job is to make them plausible (P(renew) = 0.041 / 0.082). — Jitam
2026-08-30  Per-entity RNG streams. One shared stream made every decision depend on draw order, so an unrelated change to ticket generation silently un-churned NORTHWIND. — Jitam
2026-08-30  `make check` runs the tools/ checks too. It did not, which is how a ground-truth violation reached CI at 0.7 with make check green — the divergence §41.3 says outranks everything. — Jitam
2026-08-30  P0 audit open item: fixtures/case_east_8pct.json attributes a share to driver_id "mix", which is not a registry driver. Needs the all-three sitting (§30 rule 1). — Jitam
```
