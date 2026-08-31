"""Builds `fixtures/case_real_scenario_{a,b,d}.json` — real `run_case()`
output, not hand-authored.

The UI shipped against exactly one fixture, `case_east_8pct.json`, and that
fixture was typed by hand at P0 before the engine existed — a demo viewer
has no way to tell it apart from something the pipeline actually computed.
This script closes that gap: it regenerates the corpus from the committed
seed (same discipline `tests/conftest.py`'s own `generated`/`warehouse`
fixtures use), then calls the real `orchestrator.run_case()` against it —
the same function `test_orchestrator.py` and `make demo` call — for three
scenarios named in `docs/03-data.md` §25:

  A  net_revenue   · East  · 2026-04  — the full chain, Likely
  B  new_business_arr · North · 2025-10 — Undetermined, sources can't see it
  D  net_revenue   · West  · 2026-03  — closed at Verify, 0 model calls

No live LLM key is available in this environment, so `StubProvider` stands
in for the three model calls scenario A and B make. That is honest, not a
shortcut: every quantitative field (decomposition, the four challenge tests,
the verdict, the recommendation) is computed by the real deterministic
pipeline regardless of which provider answers S3/S4c, because none of those
stages read model output for a number (§17). The one place a stub payload
shows up at all is S4c extraction — its guardrail requires a quote to be a
verbatim substring of a real retrieved document, so a stub's fabricated
quote is correctly rejected and the item lands as `checked_absent` rather
than a fabricated `found` — see `docs/DECISIONS.md` for the one place this
changes scenario A's attribution versus the golden fixture's hand-typed
version (pricing_change's minor share here comes from real SQL probe
evidence in the ledger, not extraction, so it is unaffected).

    python tools/build_real_case_fixtures.py
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import duckdb

from casefile.contract import load_all
from casefile.data.generator import generate
from casefile.data.loader import build
from casefile.llm import StubProvider
from casefile.orchestrator import run_case

ROOT = Path(__file__).resolve().parents[1]

SCENARIOS = {
    "a": ("net_revenue", "2026-04", {"region": "East"}),
    "b": ("new_business_arr", "2025-10", {"region": "North"}),
    "d": ("net_revenue", "2026-03", {"region": "West"}),
}


def main() -> None:
    contracts = load_all(ROOT / "contracts")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        generate(tmp_path / "corpus")
        db_path = build(
            raw_dir=tmp_path / "corpus" / "raw",
            db_path=tmp_path / "warehouse" / "casefile.duckdb",
            alias_path=ROOT / "data" / "account_alias.csv",
        )
        con = duckdb.connect(str(db_path), read_only=True)
        try:
            for letter, (kpi, period, dimensions) in SCENARIOS.items():
                case = run_case(contracts[kpi], period, dimensions, con, StubProvider())
                out = ROOT / "fixtures" / f"case_real_scenario_{letter}.json"
                out.write_text(
                    json.dumps(case.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
                print(f"wrote {out.relative_to(ROOT)} — {case.id}")
        finally:
            con.close()


if __name__ == "__main__":
    main()
