"""Persona specs — §11 Screen 4, §25 F.

One YAML per persona, loaded into the treaty's `Persona` and nothing else. The
file *is* the spec: §30 keeps `Persona` minimal on purpose, so a field invented
here before narration needs it is a field all three of us have to agree to remove
later.

Two of the three fields are load-bearing at S8a:

* **`role_key`** is what §14.1's `access` rules are written against. A typo is
  not an error — it is an empty page nobody is told about — so it is validated
  against the same `ROLES` registry `contract.py` uses.
* **`region`** is what resolves `own_region` in those rules. A region-scoped role
  with no region cannot be entitled at all, and saying so at load time is better
  than discovering it when a case renders blank.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from casefile.data.schema import ROLES
from casefile.models import KPIContract, Persona

#: Roles §14.1 scopes to a single region. A persona holding one needs a `region`.
_SCOPED = "own_region"


class PersonaError(ValueError):
    def __init__(self, source: str, problems: list[str]) -> None:
        self.source = source
        self.problems = problems
        listed = "\n".join(f"  - {p}" for p in problems)
        super().__init__(f"{source} is not a valid persona:\n{listed}")


def load(path: Path | str) -> Persona:
    path = Path(path)
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise PersonaError(str(path), ["the file does not contain a YAML mapping"])

    try:
        persona = Persona.model_validate(raw)
    except ValidationError as exc:
        raise PersonaError(
            str(path),
            [
                f"{'.'.join(str(p) for p in err['loc']) or '(root)'}: {err['msg']}"
                for err in exc.errors()
            ],
        ) from None

    if persona.role_key not in ROLES:
        raise PersonaError(
            str(path),
            [f"role_key {persona.role_key!r} is not a known role; known: {sorted(ROLES)}"],
        )
    return persona


def load_all(directory: Path | str) -> dict[str, Persona]:
    """Every persona in a directory, keyed by id. §20 expects four."""
    personas: dict[str, Persona] = {}
    for path in sorted(Path(directory).glob("*.yaml")):
        persona = load(path)
        if persona.id in personas:
            raise PersonaError(str(path), [f"duplicate persona id {persona.id!r}"])
        personas[persona.id] = persona
    return personas


def problems(persona: Persona, contract: KPIContract) -> list[str]:
    """Whether this persona can actually be entitled against this contract.

    Checked rather than assumed, because both failure modes are silent: a role
    the contract never mentions sees a page with no rows and no explanation, and
    a region-scoped role with no region has an `own_region` that resolves to
    nothing at all.
    """
    found: list[str] = []
    for dimension, by_role in contract.access.row.items():
        allowed = by_role.get(persona.role_key)
        if allowed is None:
            found.append(
                f"{contract.id} grants no {dimension} access to {persona.role_key!r}, "
                "so every row is withheld and the page renders empty"
            )
        elif _SCOPED in allowed and dimension == "region" and persona.region is None:
            found.append(
                f"{contract.id} scopes {persona.role_key!r} to own_region, but this "
                "persona has no region for own_region to mean"
            )
    return found
