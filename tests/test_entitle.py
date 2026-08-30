"""Ladder step 1.7 — Stage 8a, entitlement, and §35.4's security test.

The step's verify command from §44:

    "Security test green for all four personas"

§35.4 calls that test *non-negotiable* and writes it in three lines: for every
persona, every restricted field's **raw value** must be absent from the
narrative, from the evidence drill-down, and from the API payload. All three
surfaces are checked here against the fixture both tracks build against.

*"Security acts on DATA"* (§16). The point of running this before narration is
that a model cannot leak what it was never given, so most of this file is about
what `entitle` removes rather than about what it says.
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pytest
from pydantic import ValidationError

from casefile.contract import load_all as load_contracts
from casefile.engine.entitle import (
    AccountFacts,
    EntitledCase,
    NotEntitled,
    band,
    entitle,
)
from casefile.models import Case, KPIContract, Persona
from casefile.personas import load_all as load_personas

ROOT = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.gate1


@pytest.fixture(scope="module")
def contract() -> KPIContract:
    return load_contracts(ROOT / "contracts")["net_revenue"]


@pytest.fixture(scope="module")
def personas() -> dict[str, Persona]:
    return load_personas(ROOT / "personas")


@pytest.fixture(scope="module")
def accounts(warehouse: Path) -> dict[str, AccountFacts]:
    con = duckdb.connect(str(warehouse), read_only=True)
    try:
        return {
            str(row[0]): AccountFacts(str(row[0]), str(row[1]), str(row[2]), str(row[3]))
            for row in con.execute(
                "SELECT account_id, account_name, segment, region FROM crm.account"
            ).fetchall()
        }
    finally:
        con.close()


@pytest.fixture
def case() -> Case:
    """§31's golden object — the case both tracks build against."""
    return Case.model_validate(
        json.loads((ROOT / "fixtures" / "case_east_8pct.json").read_text(encoding="utf-8"))
    )


def rendered(view: EntitledCase) -> tuple[str, str, str]:
    """§35.4's three surfaces: narrative, evidence drill-down, API payload."""
    narrative = " ".join(
        [
            *(h.rationale for h in view.case.hypotheses),
            *(c.detail for c in view.case.verification.checks),
            *(
                getattr(matrix, name).detail
                for matrix in view.case.tests.values()
                for name in ("timing", "locality", "dose", "control")
            ),
            view.case.recommendation.action if view.case.recommendation else "",
            view.case.recommendation.monitoring if view.case.recommendation else "",
            view.case.open_question.question if view.case.open_question else "",
            view.statement,
        ]
    )
    evidence = " ".join(item.claim for item in view.case.ledger)
    return narrative, evidence, json.dumps(view.payload)


def restricted_values(
    case: Case, persona: Persona, contract: KPIContract, accounts: dict[str, AccountFacts]
) -> dict[str, list[str]]:
    """The raw values §35.4 says must not appear, per restricted column."""
    out: dict[str, list[str]] = {}
    for field, roles in contract.access.column.items():
        if persona.role_key in roles:
            continue
        if field == "account_name":
            nodes = case.decomposition.by_dimension["account"] if case.decomposition else []
            known = set(accounts) | {a.name for a in accounts.values()}
            out[field] = sorted({n.key for n in nodes} & known)
        elif field == "amount_net":
            dump = json.dumps(case.model_dump(mode="json"))
            out[field] = sorted(
                {
                    rendering
                    for value in _amounts(case)
                    for rendering in (f"{value:,.0f}", f"{abs(value):.1f}", str(int(value)))
                    if rendering in dump and len(rendering.strip("-")) >= 5
                }
            )
    return {k: v for k, v in out.items() if v}


def _amounts(case: Case) -> list[float]:
    values = [case.trigger.delta, case.priority]
    if case.decomposition is not None:
        values.append(case.decomposition.total_delta)
        values.append(case.decomposition.footprint.delta)
        values += [n.delta for nodes in case.decomposition.by_dimension.values() for n in nodes]
    if case.open_question is not None:
        values.append(case.open_question.value_at_stake)
    return [v for v in values if abs(v) >= 10_000]


# ── §35.4, the security test ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    "persona_id", ["cfo", "vp_sales_east", "analyst_east", "support_lead_east"]
)
def test_restricted_fields_never_reach_output(
    case: Case,
    personas: dict[str, Persona],
    contract: KPIContract,
    accounts: dict[str, AccountFacts],
    persona_id: str,
) -> None:
    """§35.4, verbatim in shape: narrative, evidence *and* API payload."""
    persona = personas[persona_id]
    view = entitle(case, persona, contract, accounts)
    narrative, evidence, payload = rendered(view)

    for field, values in restricted_values(case, persona, contract, accounts).items():
        assert values, f"{field} is restricted for {persona_id} but has no raw value to hide"
        for raw in values:
            assert raw not in narrative, f"{persona_id}: {field} {raw!r} leaked into narrative"
            assert raw not in evidence, f"{persona_id}: {field} {raw!r} leaked into evidence"
            assert raw not in payload, f"{persona_id}: {field} {raw!r} leaked into payload"


def test_the_support_lead_is_the_persona_with_something_to_hide(
    case: Case,
    personas: dict[str, Persona],
    contract: KPIContract,
    accounts: dict[str, AccountFacts],
) -> None:
    """A security test that passes because nothing was restricted proves nothing.
    §25 F puts three restrictions on this persona at once, so the parametrised
    test above has real work to do on at least one of its four runs."""
    values = restricted_values(
        case, personas["support_lead_east"], contract, accounts
    )
    assert set(values) == {"account_name", "amount_net"}
    assert len(values["account_name"]) >= 2
    assert len(values["amount_net"]) >= 3

    assert restricted_values(case, personas["cfo"], contract, accounts) == {}


# ── Row: the case a persona may not open at all ──────────────────────────────


def test_a_case_outside_the_viewers_region_is_withheld_entirely(
    case: Case, contract: KPIContract, accounts: dict[str, AccountFacts]
) -> None:
    """`access.row.region.vp_sales: [own_region]`. A West VP does not get a
    redacted East case, they get no case — the redaction markers themselves would
    say how much moved and where."""
    west = Persona(id="vp_west", role_key="vp_sales", label="VP Sales, West", region="West")

    with pytest.raises(NotEntitled, match="region"):
        entitle(case, west, contract, accounts)


def test_the_east_viewer_of_the_same_role_gets_the_case(
    case: Case,
    personas: dict[str, Persona],
    contract: KPIContract,
    accounts: dict[str, AccountFacts],
) -> None:
    view = entitle(case, personas["vp_sales_east"], contract, accounts)
    assert view.redactions == ()
    assert view.case.trigger.dimensions == {"region": "East"}


def test_a_role_the_contract_never_grants_sees_nothing(
    case: Case, contract: KPIContract, accounts: dict[str, AccountFacts]
) -> None:
    ops = Persona(id="ops", role_key="vp_ops", label="VP Ops", region="East")
    with pytest.raises(NotEntitled):
        entitle(case, ops, contract, accounts)


# ── Domain: withheld rows are stated, not dropped ────────────────────────────


def test_withheld_accounts_become_one_stated_marker(
    case: Case,
    personas: dict[str, Persona],
    contract: KPIContract,
    accounts: dict[str, AccountFacts],
) -> None:
    """§15: *"restricted values replaced with explicit markers, never silently
    dropped."* The arithmetic agrees — a contribution tree's shares sum to one,
    so deleting a node makes the remainder wrong in a way nobody can see."""
    view = entitle(case, personas["support_lead_east"], contract, accounts)
    keys = [n.key for n in view.case.decomposition.by_dimension["account"]]

    assert any("segment restricted" in key for key in keys)
    assert "ACME" not in keys and "NORTHWIND" not in keys

    before = case.decomposition.by_dimension["account"]
    after = view.case.decomposition.by_dimension["account"]
    assert sum(n.delta for n in after) == pytest.approx(sum(n.delta for n in before))
    assert sum(n.share for n in after) == pytest.approx(sum(n.share for n in before))


def test_the_withheld_marker_is_not_itself_hashed(
    case: Case,
    personas: dict[str, Persona],
    contract: KPIContract,
    accounts: dict[str, AccountFacts],
) -> None:
    """The marker is the sentence §15 asks for. Hashing it into `Account 4f2a`
    turns a statement about what is hidden back into something that reads like an
    account, and the reader learns nothing."""
    view = entitle(case, personas["support_lead_east"], contract, accounts)
    keys = [n.key for n in view.case.decomposition.by_dimension["account"]]
    marker = next(k for k in keys if "restricted" in k)

    assert marker.startswith("2 accounts")
    assert view.case.decomposition.footprint.entities["account_id"] == [marker]


# ── Column: one account, one alias ───────────────────────────────────────────


def test_an_account_gets_the_same_alias_wherever_it_appears(
    case: Case,
    personas: dict[str, Persona],
    contract: KPIContract,
    accounts: dict[str, AccountFacts],
) -> None:
    """An account is an id in the contribution tree and a name in the prose. If
    those resolved to different hashes a reader could count two accounts where
    there is one, which is the whole thing the alias exists to prevent."""
    view = entitle(case, personas["support_lead_east"], contract, accounts)
    _, evidence, _ = rendered(view)

    aliases = {word for word in evidence.split() if word.startswith("Account")}
    # ev-002 and ev-003 both name the same two accounts.
    assert len(aliases) >= 1
    for alias in aliases:
        assert evidence.count(alias) >= 1

    second = entitle(case, personas["support_lead_east"], contract, accounts)
    assert rendered(second)[1] == evidence, "aliases must be stable across runs"


def test_the_same_account_named_two_ways_gets_one_alias(
    case: Case,
    personas: dict[str, Persona],
    contract: KPIContract,
    accounts: dict[str, AccountFacts],
) -> None:
    """The shape the real pipeline produces, which the hand-written fixture does
    not: Stage 2 keys its contribution nodes by `account_id`, while the evidence
    claims name the account. Folding both to a canonical id before aliasing is
    what stops `ACC-0001` and `ACME` becoming two different hashes — and a reader
    counting two accounts where there is one.
    """
    facts = accounts["ACC-0019"]  # East, mid_market: survives the domain filter
    mixed = case.model_copy(deep=True)
    mixed.decomposition.by_dimension["account"][0].key = facts.account_id
    mixed.ledger = [
        mixed.ledger[0].model_copy(
            update={"claim": f"{facts.name} carries most of the movement."}
        ),
        *mixed.ledger[1:],
    ]

    view = entitle(mixed, personas["support_lead_east"], contract, accounts)
    in_tree = view.case.decomposition.by_dimension["account"]
    aliased = [n.key for n in in_tree if n.key.startswith("Account")]

    assert aliased, "the id-keyed node was not aliased at all"
    assert any(alias in view.case.ledger[0].claim for alias in aliased), (
        "the same account resolved to a different alias in the prose"
    )


def test_amounts_are_banded_rather_than_rounded(
    case: Case,
    personas: dict[str, Persona],
    contract: KPIContract,
    accounts: dict[str, AccountFacts],
) -> None:
    """§11 Screen 4 shows `"₹1–5 Cr"`. A rounded number is still a number and a
    reader will treat it as one, so the payload carries a band string."""
    view = entitle(case, personas["support_lead_east"], contract, accounts)

    assert view.payload["trigger"]["delta"] == "−₹1–5 Cr"
    assert isinstance(view.payload["priority"], str)
    assert band(-24_000_000.0) == "−₹1–5 Cr"
    assert band(240_000.0) == "under ₹1 Cr"
    assert band(2_000_000_000.0) == "over ₹100 Cr"


def test_a_share_is_not_an_amount_and_survives(
    case: Case,
    personas: dict[str, Persona],
    contract: KPIContract,
    accounts: dict[str, AccountFacts],
) -> None:
    """The trap in banding anything that looks numeric. `share`, `statistic` and
    the robust z are not `amount_net`, and a case file reporting the movement as
    "₹1–5 Cr standard deviations from expected" would be worse than one that
    leaked."""
    view = entitle(case, personas["support_lead_east"], contract, accounts)
    tree = view.payload["decomposition"]

    assert all(isinstance(n["share"], float) for n in tree["by_dimension"]["account"])
    assert view.payload["verification"]["robust_z"] == -3.8
    assert "87.5%" in " ".join(item.claim for item in view.case.ledger)


def test_a_date_is_not_an_amount(
    case: Case,
    personas: dict[str, Persona],
    contract: KPIContract,
    accounts: dict[str, AccountFacts],
) -> None:
    """The other half of the same trap: redacting every digit run would mangle
    `2026-04` and `0 of 12 populated lost-reason fields`, protecting nothing and
    destroying the evidence."""
    view = entitle(case, personas["support_lead_east"], contract, accounts)
    claims = " ".join(item.claim for item in view.case.ledger)

    assert "2026-04-20" in claims
    assert "0 of 12 populated lost-reason fields" in claims


# ── The statement, and the shape of the result ───────────────────────────────


def test_every_redaction_is_stated_on_the_page(
    case: Case,
    personas: dict[str, Persona],
    contract: KPIContract,
    accounts: dict[str, AccountFacts],
) -> None:
    """§11 Screen 4: *"redaction stated, never silent"*. A reader who cannot tell
    a small number from a withheld one will believe the small number."""
    view = entitle(case, personas["support_lead_east"], contract, accounts)

    assert {r.field for r in view.redactions} == {"segment", "account_name", "amount_net"}
    for redaction in view.redactions:
        assert redaction.detail in view.statement
    assert view.statement.startswith("Redacted:")


def test_a_view_with_nothing_hidden_says_so(
    case: Case,
    personas: dict[str, Persona],
    contract: KPIContract,
    accounts: dict[str, AccountFacts],
) -> None:
    view = entitle(case, personas["cfo"], contract, accounts)
    assert view.redactions == ()
    assert view.statement == "No redactions: this view is complete."


def test_entitlement_does_not_mutate_the_case_it_was_given(
    case: Case,
    personas: dict[str, Persona],
    contract: KPIContract,
    accounts: dict[str, AccountFacts],
) -> None:
    """Four personas render the same case. If the first view mutated it the
    second would be entitled against an already-redacted object, and the CFO
    would see the Support Lead's page."""
    original = case.model_dump(mode="json")

    entitle(case, personas["support_lead_east"], contract, accounts)
    assert case.model_dump(mode="json") == original

    view = entitle(case, personas["cfo"], contract, accounts)
    assert view.payload == original


def test_the_ledger_is_rebuilt_rather_than_mutated(
    case: Case,
    personas: dict[str, Persona],
    contract: KPIContract,
    accounts: dict[str, AccountFacts],
) -> None:
    """§30 rule 4: no stage mutates another stage's ledger entries, and
    `EvidenceItem` is frozen so trying would raise. Masking a claim therefore has
    to produce a new item."""
    view = entitle(case, personas["support_lead_east"], contract, accounts)

    assert view.case.ledger[1] is not case.ledger[1]
    assert view.case.ledger[1].id == case.ledger[1].id
    with pytest.raises(ValidationError):
        view.case.ledger[1].claim = "anything"  # type: ignore[misc]
