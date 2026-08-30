"""Ladder step 0.6 — the contract loader and validator.

The step's verify command from §44:

    "Validator rejects a contract missing an element or naming an unknown owner_role"

Each rejection test mutates the real `net_revenue.yaml` rather than building a
toy contract, so a rule cannot pass against a fixture that has drifted away from
the file the pipeline actually reads.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
import yaml

from casefile.contract import ContractError, load, load_all, problems
from casefile.data.schema import ROLES
from casefile.models import KPIContract

CONTRACTS = Path(__file__).resolve().parents[1] / "contracts"
SPECIMEN = CONTRACTS / "net_revenue.yaml"

pytestmark = pytest.mark.gate0


@pytest.fixture(scope="module")
def contract() -> KPIContract:
    return load(SPECIMEN)


@pytest.fixture()
def raw() -> dict[str, Any]:
    return yaml.safe_load(SPECIMEN.read_text(encoding="utf-8"))


def write(tmp_path: Path, data: dict[str, Any]) -> Path:
    path = tmp_path / "broken.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


# ── The specimen is real ──────────────────────────────────────────────────────


def test_the_specimen_loads_and_validates(contract: KPIContract) -> None:
    assert contract.id == "net_revenue"
    assert contract.owner_role == "cfo"
    assert problems(contract) == []


def test_every_element_of_14_1_survived_the_round_trip(contract: KPIContract) -> None:
    """All six numbered blocks, plus the three marked `[+]`. A contract that
    loses a block on the way through is how §14.1 quietly becomes documentation."""
    assert contract.definition.startswith("Invoiced revenue net of discounts")
    assert contract.formula.startswith("SUM(invoice_line.amount_net)")
    assert contract.refresh.sla_hours == 26
    assert contract.materiality.absolute == 2_500_000
    assert contract.data_quality.max_single_record_share == 0.35
    assert contract.lineage.downstream == ["metric.nrr", "dashboard.exec_revenue"]
    assert contract.access.masking["amount_net"] == "band_1_5_cr"
    assert len(contract.epochs) == 3
    assert len(contract.composition) == 3
    assert contract.seasonal_period_days == 365


def test_the_five_drivers_land_with_four_levers(contract: KPIContract) -> None:
    """`seasonality` carries no lever — §14.1 sets it null, because nothing about
    the weather is controllable, and Stage 7 must not offer an action for it."""
    by_id = {d.id: d for d in contract.drivers}
    assert set(by_id) == {
        "integration_delay",
        "pricing_change",
        "competitor_offer",
        "seasonality",
        "supply_delay",
    }
    assert by_id["seasonality"].lever is None
    assert by_id["seasonality"].type == "external_uncontrollable"
    assert sum(1 for d in contract.drivers if d.lever is not None) == 4

    lever = by_id["integration_delay"].lever
    assert lever is not None
    assert lever.save_rate == (0.75, 1.00)
    assert lever.owner_role == "vp_engineering"


def test_load_all_reads_the_directory(contract: KPIContract) -> None:
    assert load_all(CONTRACTS)["net_revenue"] == contract


# ── Missing an element — the ladder's first verify ────────────────────────────


@pytest.mark.parametrize(
    "element", ["definition", "formula", "materiality", "drivers", "lineage", "access"]
)
def test_a_contract_missing_an_element_is_rejected(
    tmp_path: Path, raw: dict[str, Any], element: str
) -> None:
    """The six numbered blocks of §14.1. None of them has a default, so the
    shape check is what enforces A1's first clause."""
    del raw[element]
    with pytest.raises(ContractError) as excinfo:
        load(write(tmp_path, raw))

    assert element in str(excinfo.value)


def test_a_misspelled_key_is_rejected_rather_than_ignored(
    tmp_path: Path, raw: dict[str, Any]
) -> None:
    """`extra="forbid"` on the treaty models. A silently-dropped `materialty`
    would mean the pipeline running on defaults nobody chose."""
    raw["materialty"] = raw.pop("materiality")
    with pytest.raises(ContractError, match="materialty"):
        load(write(tmp_path, raw))


# ── Unknown owner_role — the ladder's second verify ───────────────────────────


def test_an_unknown_lever_owner_role_is_rejected(tmp_path: Path, raw: dict[str, Any]) -> None:
    raw["drivers"][0]["lever"]["owner_role"] = "vp_martian"
    with pytest.raises(ContractError) as excinfo:
        load(write(tmp_path, raw))

    assert "vp_martian" in str(excinfo.value)
    assert "integration_delay" in str(excinfo.value)


def test_an_unknown_role_is_caught_in_every_place_a_role_can_appear(
    tmp_path: Path, raw: dict[str, Any]
) -> None:
    """A role reaches the contract from four directions. Catching it in one and
    missing the rest is worse than not checking — it reads as covered."""
    raw["owner_role"] = "ghost_a"
    raw["access"]["row"]["region"]["ghost_b"] = ["own_region"]
    raw["access"]["column"]["account_name"].append("ghost_c")
    raw["access"]["domain"]["segment"]["ghost_d"] = ["smb"]

    with pytest.raises(ContractError) as excinfo:
        load(write(tmp_path, raw))

    message = str(excinfo.value)
    for ghost in ("ghost_a", "ghost_b", "ghost_c", "ghost_d"):
        assert ghost in message, f"{ghost} slipped through"


def test_every_role_the_specimen_uses_is_a_known_role(contract: KPIContract) -> None:
    used = {contract.owner_role} | {
        d.lever.owner_role for d in contract.drivers if d.lever is not None
    }
    assert used <= ROLES


# ── Lineage referencing a non-existent table — A1's third clause ──────────────


def test_lineage_naming_a_table_that_does_not_exist_is_rejected(
    tmp_path: Path, raw: dict[str, Any]
) -> None:
    raw["lineage"]["upstream"].append("billing.raw_invoice → billing.imaginary_table")
    with pytest.raises(ContractError, match="billing.imaginary_table"):
        load(write(tmp_path, raw))


def test_lineage_prose_is_parsed_rather_than_skipped(tmp_path: Path, raw: dict[str, Any]) -> None:
    """§14.1 writes lineage as prose with arrows and parenthetical notes. If the
    commentary defeated the parser the rule would pass on anything."""
    raw["lineage"]["joins"] = ["crm.nowhere ON account_id  (region enrichment)"]
    with pytest.raises(ContractError, match="crm.nowhere"):
        load(write(tmp_path, raw))


def test_downstream_tables_are_checked_too(tmp_path: Path, raw: dict[str, Any]) -> None:
    raw["lineage"]["downstream"] = ["metric.nrr", "dashboard.does_not_exist"]
    with pytest.raises(ContractError, match="dashboard.does_not_exist"):
        load(write(tmp_path, raw))


# ── The remaining cross-references ────────────────────────────────────────────


def test_two_drivers_sharing_an_id_are_rejected(tmp_path: Path, raw: dict[str, Any]) -> None:
    """Stage 3 enumerates over driver ids; a duplicate is a hypothesis that can
    never be told apart from its twin."""
    raw["drivers"].append(copy.deepcopy(raw["drivers"][0]))
    with pytest.raises(ContractError, match="integration_delay"):
        load(write(tmp_path, raw))


def test_composition_naming_an_unknown_kpi_is_rejected(
    tmp_path: Path, raw: dict[str, Any]
) -> None:
    raw["composition"][0]["kpi"] = "vibes"
    with pytest.raises(ContractError, match="vibes"):
        load(write(tmp_path, raw))


def test_a_kpi_cannot_be_composed_of_itself(tmp_path: Path, raw: dict[str, Any]) -> None:
    raw["composition"][0]["kpi"] = "net_revenue"
    with pytest.raises(ContractError, match="cannot be composed of itself"):
        load(write(tmp_path, raw))


def test_epochs_out_of_order_are_rejected(tmp_path: Path, raw: dict[str, Any]) -> None:
    raw["epochs"].reverse()
    with pytest.raises(ContractError, match="ascending"):
        load(write(tmp_path, raw))


def test_the_last_epoch_must_agree_with_the_formula(tmp_path: Path, raw: dict[str, Any]) -> None:
    """§15 S1 recomputes boundary periods under adjacent epochs to separate
    definition drift from business change. A contract that disagrees with itself
    about today's formula makes that check meaningless."""
    raw["epochs"][-1]["formula"] = "SUM(invoice_line.amount_gross)"
    with pytest.raises(ContractError, match="disagrees with itself"):
        load(write(tmp_path, raw))


def test_the_first_epoch_must_cover_the_start_of_history(
    tmp_path: Path, raw: dict[str, Any]
) -> None:
    raw["history_start"] = "2022-04-01"
    with pytest.raises(ContractError, match="no definition"):
        load(write(tmp_path, raw))


def test_a_file_that_is_not_a_mapping_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "broken.yaml"
    path.write_text("- just\n- a list\n", encoding="utf-8")
    with pytest.raises(ContractError, match="YAML mapping"):
        load(path)


# ── Not checked yet, on purpose ───────────────────────────────────────────────


def test_probe_sql_paths_are_not_yet_required_to_exist(contract: KPIContract) -> None:
    """`probes/` stays empty until Track B's ladder step 2.2, so a
    file-existence rule would fail on the only contract we have. This test is
    the reminder that the gap is deliberate, and where it closes."""
    declared = [d.probe_sql for d in contract.drivers if d.probe_sql]
    assert declared, "the specimen declares probes"
    assert not any((CONTRACTS.parent / p).exists() for p in declared)
