"""The KPI semantic contract — loader and validator, §14.1.

The *shape* lives in `models.py`, because every track reads it (§30). This file
is the half that shape cannot express: whether the names inside a contract refer
to things that actually exist.

That distinction is the whole point of A1's definition of done — *"CI fails on
missing element, unknown `lever.owner_role`, or lineage referencing a
non-existent table"*. Pydantic supplies the first for free. The other two are
cross-references, and a cross-reference is only checkable against a registry, so
they live here against `data/schema.py`.

Both kinds of failure raise `ContractError`, and it reports **every** problem it
found rather than the first. A validator that stops at one error turns a broken
contract into five rounds of CI.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml
from pydantic import ValidationError

from casefile.data.schema import KPIS, ROLES, known_tables
from casefile.models import KPIContract

# `billing.invoice_line`, `metric.nrr` — the qualified names inside a lineage
# entry, which §14.1 writes as prose ("billing.raw_invoice → billing.invoice
# (dedupe, currency norm)"). Anything without a dot is commentary.
_QUALIFIED = re.compile(r"\b[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*\b")


class ContractError(ValueError):
    def __init__(self, source: str, problems: list[str]) -> None:
        self.source = source
        self.problems = problems
        listed = "\n".join(f"  - {p}" for p in problems)
        super().__init__(f"{source} is not a valid KPI contract:\n{listed}")


def load(path: Path | str) -> KPIContract:
    """Parse, validate the shape, then validate the cross-references."""
    path = Path(path)
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ContractError(str(path), ["the file does not contain a YAML mapping"])

    try:
        contract = KPIContract.model_validate(raw)
    except ValidationError as exc:
        raise ContractError(str(path), _shape_problems(exc)) from None

    found = problems(contract)
    if found:
        raise ContractError(str(path), found)
    return contract


def load_all(directory: Path | str) -> dict[str, KPIContract]:
    """Every contract in a directory, keyed by id. §20 expects six of them."""
    contracts = {}
    for path in sorted(Path(directory).glob("*.yaml")):
        contract = load(path)
        contracts[contract.id] = contract
    return contracts


def problems(contract: KPIContract) -> list[str]:
    """Every cross-reference in the contract that does not resolve.

    Empty means valid. Each rule below is one line in §14.1 or A1 — nothing here
    is a house style preference.
    """
    return [
        *_unknown_roles(contract),
        *_unknown_lineage_tables(contract),
        *_driver_problems(contract),
        *_composition_problems(contract),
        *_epoch_problems(contract),
    ]


def _shape_problems(exc: ValidationError) -> list[str]:
    return [
        f"{'.'.join(str(p) for p in err['loc']) or '(root)'}: {err['msg']}"
        for err in exc.errors()
    ]


def _unknown_roles(contract: KPIContract) -> list[str]:
    """A role that does not exist reads as an empty entitlement at S8a — the
    page renders, the rows are simply gone, and nobody is told why."""
    named: list[tuple[str, str]] = [("owner_role", contract.owner_role)]

    for driver in contract.drivers:
        if driver.lever is not None:
            named.append((f"drivers.{driver.id}.lever.owner_role", driver.lever.owner_role))

    for dimension, by_role in contract.access.row.items():
        named += [(f"access.row.{dimension}", role) for role in by_role]
    for column, roles in contract.access.column.items():
        named += [(f"access.column.{column}", role) for role in roles]
    for dimension, by_role in contract.access.domain.items():
        named += [(f"access.domain.{dimension}", role) for role in by_role]

    return [
        f"{where} names an unknown role {role!r}; known roles: {sorted(ROLES)}"
        for where, role in named
        if role not in ROLES
    ]


def _unknown_lineage_tables(contract: KPIContract) -> list[str]:
    known = known_tables()
    found = []
    for field in ("upstream", "joins", "downstream"):
        for entry in getattr(contract.lineage, field):
            found += [
                f"lineage.{field} references {name!r}, which is not a table in §22"
                for name in _QUALIFIED.findall(entry)
                if name not in known
            ]
    return found


def _driver_problems(contract: KPIContract) -> list[str]:
    """Stage 3 enumerates over driver ids; two drivers sharing one id means a
    hypothesis that can never be told apart from its twin."""
    seen: set[str] = set()
    duplicates: list[str] = []
    for driver in contract.drivers:
        if driver.id in seen:
            duplicates.append(f"drivers: {driver.id!r} appears more than once")
        seen.add(driver.id)
    return duplicates


def _composition_problems(contract: KPIContract) -> list[str]:
    found = []
    for edge in contract.composition:
        if edge.kpi not in KPIS:
            found.append(f"composition names an unknown KPI {edge.kpi!r}; known: {sorted(KPIS)}")
        elif edge.kpi == contract.id:
            found.append(f"composition: {contract.id!r} cannot be composed of itself")
    return found


def _epoch_problems(contract: KPIContract) -> list[str]:
    """§15 S1 separates definition drift from business change by recomputing a
    boundary period under adjacent epochs. That check is only meaningful if the
    epoch list is ordered, starts where the history starts, and ends at the
    formula the contract actually claims to use.
    """
    if not contract.epochs:
        return []

    found = []
    dates = [epoch.effective_from for epoch in contract.epochs]
    if dates != sorted(dates):
        found.append(f"epochs are not in ascending order: {dates}")
    if dates[0] != contract.history_start:
        found.append(
            f"the first epoch starts {dates[0]} but history_start is "
            f"{contract.history_start}; the opening period has no definition"
        )
    if contract.epochs[-1].formula != contract.formula:
        found.append(
            "the last epoch's formula differs from `formula`, so the contract "
            "disagrees with itself about how the KPI is calculated today"
        )
    return found

