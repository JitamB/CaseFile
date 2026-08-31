"""Builds `fixtures/case_east_8pct_entitled.json` — ladder step 3.3's own
input. §31: "fixtures are golden objects for parallel work," and the persona
switcher is UI, not engine — it is meant to be built against a fixture, the
same way screens 1 through 3 already are, not against a live pipeline run.

Runs `entitle()` once per persona over the golden `case_east_8pct.json`
fixture and writes the four results out as one JSON file the UI imports
directly. Deterministic, no model call: `entitle()` is Stage 8a, DET.
Re-run this whenever `case_east_8pct.json`, `personas/*.yaml`, or
`entitle.py`'s own logic changes.

    python tools/build_entitled_fixtures.py

ACME/NORTHWIND's facts (segment, region) are hand-entered here rather than
looked up from the warehouse: `case_east_8pct.json` is itself hand-written,
not warehouse-derived (§31), and this script's whole point is to stay a
static, reproducible transform of one fixture into another — not to grow a
new dependency on a live database for two facts already established and
unchanging (docs/DECISIONS.md, 2026-08-31: ACC-0001/ACME and ACC-0002/
NORTHWIND are enterprise, East).
"""

from __future__ import annotations

import json
from pathlib import Path

from casefile.contract import load_all as load_contracts
from casefile.engine.entitle import AccountFacts, entitle
from casefile.models import Case
from casefile.personas import load_all as load_personas

ROOT = Path(__file__).resolve().parents[1]

ACCOUNTS = {
    "ACC-0001": AccountFacts("ACC-0001", "ACME", "enterprise", "East"),
    "ACC-0002": AccountFacts("ACC-0002", "NORTHWIND", "enterprise", "East"),
}


def main() -> None:
    case = Case.model_validate(
        json.loads((ROOT / "fixtures" / "case_east_8pct.json").read_text(encoding="utf-8"))
    )
    contract = load_contracts(ROOT / "contracts")["net_revenue"]
    personas = load_personas(ROOT / "personas")

    views = {}
    for persona_id, persona in personas.items():
        view = entitle(case, persona, contract, ACCOUNTS)
        views[persona_id] = {
            "persona": persona.model_dump(mode="json"),
            "payload": view.payload,
            "statement": view.statement,
            "redactions": [
                {
                    "surface": r.surface, "field": r.field, "marker": r.marker,
                    "count": r.count, "detail": r.detail,
                }
                for r in view.redactions
            ],
        }

    out = ROOT / "fixtures" / "case_east_8pct_entitled.json"
    out.write_text(json.dumps(views, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {out.relative_to(ROOT)} ({len(views)} personas)")


if __name__ == "__main__":
    main()
