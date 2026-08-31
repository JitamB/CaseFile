"""Builds `fixtures/case_real_scenario_a_entitled.json` — `entitle()` run
over the real `case_real_scenario_a.json` (see `build_real_case_fixtures.py`),
not the hand-written golden fixture.

Sibling of `tools/build_entitled_fixtures.py`, which stays untouched — several
tests already key off its exact output. This script exists only so the UI's
persona switcher can be pointed at real pipeline output too, the same reason
`build_real_case_fixtures.py` exists. Same accounts, for the same reason
`build_entitled_fixtures.py` already gives: ACC-0001/ACME and ACC-0002/
NORTHWIND are enterprise, East, confirmed against the real warehouse
(docs/DECISIONS.md).

Run `build_real_case_fixtures.py` first.

    python tools/build_real_entitled_fixture.py
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
        json.loads(
            (ROOT / "fixtures" / "case_real_scenario_a.json").read_text(encoding="utf-8")
        )
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

    out = ROOT / "fixtures" / "case_real_scenario_a_entitled.json"
    out.write_text(json.dumps(views, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {out.relative_to(ROOT)} ({len(views)} personas)")


if __name__ == "__main__":
    main()
