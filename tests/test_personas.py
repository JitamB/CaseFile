"""Ladder step 1.8 — the four persona specs.

The step's verify command from §44:

    "All four load and validate"

*Validate* is the interesting half. A persona is three strings, and both ways it
can be wrong are silent: a `role_key` the contract never mentions renders a page
with no rows and no error, and a region-scoped role with no region has an
`own_region` that resolves to nothing. Neither raises anywhere else, so both are
checked here.

Taken before 1.7 rather than after it. §44 orders steps by dependency and
entitlement's security test needs personas that exist.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from casefile.contract import load_all as load_contracts
from casefile.data.schema import ROLES
from casefile.models import KPIContract, Persona
from casefile.personas import PersonaError, load, load_all, problems

ROOT = Path(__file__).resolve().parents[1]
PERSONAS = ROOT / "personas"

pytestmark = pytest.mark.gate1


@pytest.fixture(scope="module")
def personas() -> dict[str, Persona]:
    return load_all(PERSONAS)


@pytest.fixture(scope="module")
def contracts() -> dict[str, KPIContract]:
    return load_contracts(ROOT / "contracts")


# ── "All four load and validate" ──────────────────────────────────────────────


def test_the_four_personas_of_section_11_are_all_there(
    personas: dict[str, Persona]
) -> None:
    """§11 Screen 4: *"the same case rendered for CFO / VP Sales / Analyst /
    Support Lead"*. R3 counts four, and each must reach a different verdict on
    what it may see."""
    assert len(personas) == 4
    assert {p.role_key for p in personas.values()} == {
        "cfo", "vp_sales", "analyst", "support_lead",
    }


def test_every_persona_names_a_role_the_system_knows(
    personas: dict[str, Persona]
) -> None:
    """Silent failure #1. A role that does not exist is not an error anywhere —
    §14.1's access tables are dictionaries keyed by role, so an unknown key
    simply matches nothing and the page renders empty."""
    assert {p.role_key for p in personas.values()} <= ROLES


def test_every_persona_can_be_entitled_against_every_contract(
    personas: dict[str, Persona], contracts: dict[str, KPIContract]
) -> None:
    """The whole point of `problems()`. Six contracts x four personas is
    twenty-four pages that have to be renderable, and the failure mode of any one
    of them is blankness rather than an exception."""
    found = [
        f"{persona.id}/{contract.id}: {problem}"
        for persona in personas.values()
        for contract in contracts.values()
        for problem in problems(persona, contract)
    ]
    assert not found, found


def test_a_region_scoped_persona_carries_the_region_own_region_means(
    personas: dict[str, Persona], contracts: dict[str, KPIContract]
) -> None:
    """Silent failure #2, and the reason `Persona` gained a field. §14.1 writes
    `access.row.region.vp_sales: [own_region]`, and *own* is a fact about the
    viewer that lives nowhere else."""
    rules = contracts["net_revenue"].access.row["region"]

    for persona in personas.values():
        scoped = "own_region" in rules.get(persona.role_key, [])
        assert scoped == (persona.region is not None), (
            f"{persona.id} is scoped={scoped} but region={persona.region!r}"
        )

    assert personas["cfo"].region is None
    assert rules["cfo"] == ["*"]


def test_the_support_lead_is_the_one_the_security_test_is_about(
    personas: dict[str, Persona], contracts: dict[str, KPIContract]
) -> None:
    """§25 F. Three restrictions land on this persona at once, and **none of them
    is written in the persona file** — every one is a consequence of `role_key`
    meeting §14.1's access rules. A persona that carried its own restrictions
    would be a second place for them to disagree with the contract."""
    contract = contracts["net_revenue"]
    lead = personas["support_lead_east"]

    assert contract.access.row["region"][lead.role_key] == ["own_region"]
    assert lead.role_key not in contract.access.column["account_name"]
    assert lead.role_key not in contract.access.column["amount_net"]
    assert contract.access.domain["segment"][lead.role_key] == ["smb", "mid_market"]

    stored = (PERSONAS / "support_lead.yaml").read_text(encoding="utf-8")
    body = "\n".join(line for line in stored.splitlines() if not line.startswith("#"))
    assert "account_name" not in body and "hash_alias" not in body


def test_the_analyst_sees_more_than_the_support_lead_and_less_than_the_cfo(
    contracts: dict[str, KPIContract]
) -> None:
    """R3 asks for personas that receive *different* narratives. If two of them
    resolved to the same permissions the difference would be wording, which is
    what §11 Screen 4 exists to disprove."""
    columns = contracts["net_revenue"].access.column

    def granted(role: str) -> set[str]:
        return {field for field, roles in columns.items() if role in roles}

    assert granted("support_lead") < granted("analyst") < granted("cfo")


# ── What the loader refuses ───────────────────────────────────────────────────


def test_an_unknown_role_is_refused(tmp_path: Path) -> None:
    (tmp_path / "ghost.yaml").write_text(
        "id: ghost\nrole_key: chief_vibes_officer\nlabel: Ghost\n", encoding="utf-8"
    )
    with pytest.raises(PersonaError, match="not a known role"):
        load(tmp_path / "ghost.yaml")


def test_a_field_the_treaty_does_not_have_is_refused(tmp_path: Path) -> None:
    """`Persona` forbids unknown keys, and that is deliberate: a rendering
    preference invented in a YAML file before narration needs it is a field all
    three of us have to agree to remove later."""
    (tmp_path / "extra.yaml").write_text(
        "id: x\nrole_key: cfo\nlabel: X\ntone: breezy\n", encoding="utf-8"
    )
    with pytest.raises(PersonaError, match="Extra inputs"):
        load(tmp_path / "extra.yaml")


def test_a_missing_field_is_refused(tmp_path: Path) -> None:
    (tmp_path / "half.yaml").write_text("id: x\nrole_key: cfo\n", encoding="utf-8")
    with pytest.raises(PersonaError, match="label"):
        load(tmp_path / "half.yaml")


def test_a_file_that_is_not_a_mapping_is_refused(tmp_path: Path) -> None:
    (tmp_path / "list.yaml").write_text("- cfo\n- analyst\n", encoding="utf-8")
    with pytest.raises(PersonaError, match="YAML mapping"):
        load(tmp_path / "list.yaml")


def test_two_personas_cannot_share_an_id(tmp_path: Path) -> None:
    for name in ("a.yaml", "b.yaml"):
        (tmp_path / name).write_text("id: same\nrole_key: cfo\nlabel: Same\n", encoding="utf-8")
    with pytest.raises(PersonaError, match="duplicate persona id"):
        load_all(tmp_path)


# ── What `problems()` catches that the loader cannot ─────────────────────────


def test_a_region_scoped_role_with_no_region_is_reported(
    contracts: dict[str, KPIContract]
) -> None:
    """This is why `problems()` takes a contract. The persona is valid on its
    own; it is only unentitleable *against a contract that scopes its role*, and
    nothing about the file could have told you that."""
    homeless = Persona(id="vp", role_key="vp_sales", label="VP Sales", region=None)
    found = problems(homeless, contracts["net_revenue"])

    assert found and "own_region" in found[0]


def test_a_role_the_contract_never_grants_is_reported(
    contracts: dict[str, KPIContract]
) -> None:
    """`vp_ops` owns a lever in the registry but appears in no `access.row`
    table, so a page for it renders with every row withheld and nothing said."""
    ops = Persona(id="ops", role_key="vp_ops", label="VP Ops", region="West")
    found = problems(ops, contracts["net_revenue"])

    assert found and "renders empty" in found[0]


def test_a_role_the_contract_grants_everything_is_fine_without_a_region(
    contracts: dict[str, KPIContract]
) -> None:
    assert problems(Persona(id="c", role_key="cfo", label="CFO"), contracts["net_revenue"]) == []
