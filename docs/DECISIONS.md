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
```
