"""Stage 8a — Entitle. §15 S8a, §25 F.

*"Strip out what this person isn't allowed to see — **then** write. The wrong
order (write, then ask the model to redact) leaks every time."*

**In:** a complete `Case` and a `Persona`. **Out:** a case with the rows that
persona may not see removed, the values it may not see replaced by markers, and
a list of exactly what was withheld — because §15 says *"restricted values
replaced with explicit markers, never silently dropped"*, and §11 Screen 4 puts
the redaction on the page rather than behind it.

Three filters, all read from `contract.access` and none of them from the persona
file. §17 calls this "set operations on the case object" and gives the reason in
four words: **security is not a prompt.**

| Filter | Reads | Does |
|---|---|---|
| row | `access.row` | withholds the case entirely if the viewer's scope excludes it |
| domain | `access.domain` | collapses rows outside the viewer's slice into one stated marker |
| column | `access.column` + `access.masking` | replaces values with `hash_alias` / `band_1_5_cr` |

**Why there is a `payload` as well as a `case`.** §35.4 checks three surfaces —
narrative, evidence and the API payload — and two of them are strings while the
`Case` is typed. `trigger.delta` is a `float` and cannot hold "₹1-5 Cr", so
banding an amount inside the model is impossible without either lying about the
number or widening the treaty. The `Case` therefore carries the *filtered* facts
that narration reads, and `payload` is the JSON a persona may actually be shown,
with restricted amounts replaced by their bands. Anything narration is allowed
to interpolate is in the case; anything a viewer sees is in the payload.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Literal

from casefile.models import Case, ContributionNode, KPIContract, Persona

#: §14.1's placeholder for "the viewer's own", resolved from `Persona.region`.
OWN = "own_region"
#: §14.1's `access.row` wildcard.
ALL = "*"

#: Money in the free text of a claim: a grouped figure (24,000,000) or a bare run
#: of five or more digits. Deliberately not "any number" — `2026-04`, `0 of 12`
#: and `87.5%` are not amounts, and redacting them would mangle the evidence
#: while protecting nothing.
_MONEY = re.compile(r"\b\d{1,3}(?:,\d{3})+(?:\.\d+)?\b|\b\d{5,}(?:\.\d+)?\b")

#: The money-bearing fields of a `Case`, named rather than guessed. A heuristic
#: over "fields that look numeric" would sooner or later band a z-score or a
#: share, and the first anyone would know is a case file saying the movement was
#: "₹1-5 Cr standard deviations" from expected.
_MONEY_PATHS = (
    ("trigger", "delta"),
    ("decomposition", "total_delta"),
    ("decomposition", "footprint", "delta"),
    ("decomposition", "pvm", "price"),
    ("decomposition", "pvm", "volume"),
    ("decomposition", "pvm", "mix"),
    ("open_question", "value_at_stake"),
    ("recommendation", "expected_impact"),
    ("priority",),
)


class NotEntitled(PermissionError):
    """The viewer's row scope excludes this case entirely."""


@dataclass(frozen=True)
class AccountFacts:
    """What entitlement needs to know about an account. Supplied by the caller
    rather than looked up, so this module never touches the warehouse and a
    security test can construct exactly the situation it wants to test."""

    account_id: str
    name: str
    segment: str
    region: str


@dataclass(frozen=True)
class Redaction:
    surface: Literal["row", "column", "domain"]
    field: str
    marker: str
    count: int
    detail: str


@dataclass(frozen=True)
class EntitledCase:
    case: Case
    payload: dict[str, Any]
    redactions: tuple[Redaction, ...]

    @property
    def statement(self) -> str:
        """The sentence §11 Screen 4 puts on the page. *"Redaction stated, never
        silent"* is not a nicety: a reader who cannot tell a small number from a
        withheld one will believe the small number."""
        if not self.redactions:
            return "No redactions: this view is complete."
        return "Redacted: " + "; ".join(r.detail for r in self.redactions) + "."


def entitle(
    case: Case,
    persona: Persona,
    contract: KPIContract,
    accounts: Mapping[str, AccountFacts] | None = None,
) -> EntitledCase:
    """Apply row, domain and column entitlement, in that order.

    The order is not cosmetic. Rows the viewer may not see are removed before any
    value on them is masked, so a masked marker never stands in for a row that
    should not have been counted at all.
    """
    accounts = _indexed(accounts or {})
    _check_rows(case, persona, contract)

    redactions: list[Redaction] = []
    filtered = case.model_copy(deep=True)

    withheld, markers = _apply_domain(filtered, persona, contract, accounts, redactions)
    secrets = _apply_columns(
        filtered, persona, contract, accounts, withheld, markers, redactions
    )

    payload = filtered.model_dump(mode="json")
    if "amount_net" in secrets:
        _band_payload(payload)

    return EntitledCase(filtered, payload, tuple(redactions))


def _indexed(accounts: Mapping[str, AccountFacts]) -> dict[str, AccountFacts]:
    """Reachable by id **and** by name.

    Stage 2 keys its contribution nodes by `account_id`; the hand-written
    fixtures both tracks build against key theirs by name (§31). Entitlement has
    to work on either, and quietly failing to find an account is the worst
    possible outcome here — it means the row was not withheld.
    """
    indexed: dict[str, AccountFacts] = {}
    for key, facts in accounts.items():
        indexed[key] = facts
        indexed.setdefault(facts.account_id, facts)
        indexed.setdefault(facts.name, facts)
    return indexed


# ── Row ───────────────────────────────────────────────────────────────────────


def allowed_values(
    contract: KPIContract, persona: Persona, dimension: str
) -> list[str] | None:
    """What this viewer may see along `dimension`. None means "everything"."""
    rules = contract.access.row.get(dimension, {})
    granted = rules.get(persona.role_key)
    if granted is None:
        return []
    if ALL in granted:
        return None
    return [persona.region if v == OWN and persona.region else v for v in granted]


def _check_rows(case: Case, persona: Persona, contract: KPIContract) -> None:
    for dimension, value in case.trigger.dimensions.items():
        permitted = allowed_values(contract, persona, dimension)
        if permitted is not None and value not in permitted:
            raise NotEntitled(
                f"{persona.label} may see {dimension} {permitted or 'nothing'}; "
                f"case {case.id} is {dimension} {value!r}"
            )


# ── Domain ────────────────────────────────────────────────────────────────────


def _apply_domain(
    case: Case,
    persona: Persona,
    contract: KPIContract,
    accounts: Mapping[str, AccountFacts],
    redactions: list[Redaction],
) -> tuple[set[str], set[str]]:
    """Collapse rows outside the viewer's slice into one stated marker.

    Not deleted. §15 is explicit, and the arithmetic agrees: the shares in a
    contribution tree sum to one, so dropping a node makes the remainder wrong in
    a way nobody can see. The marker keeps the total and says what it is hiding.
    """
    withheld: set[str] = set()
    markers: set[str] = set()
    if case.decomposition is None:
        return withheld, markers

    for dimension, by_role in contract.access.domain.items():
        permitted = by_role.get(persona.role_key)
        if permitted is None:
            continue

        nodes = case.decomposition.by_dimension.get("account", [])
        keep: list[ContributionNode] = []
        hide: list[ContributionNode] = []
        for node in nodes:
            facts = accounts.get(node.key)
            value = getattr(facts, dimension, None) if facts else None
            (hide if value is not None and value not in permitted else keep).append(node)

        if not hide:
            continue
        withheld |= {n.key for n in hide}
        marker = f"{len(hide)} accounts ({dimension} restricted)"
        markers.add(marker)
        keep.append(
            ContributionNode(
                dimension="account",
                key=marker,
                delta=sum(n.delta for n in hide),
                share=sum(n.share for n in hide),
            )
        )
        case.decomposition.by_dimension["account"] = sorted(
            keep, key=lambda n: (-abs(n.delta), n.key)
        )
        case.decomposition.footprint.entities["account_id"] = [
            key
            for key in case.decomposition.footprint.entities.get("account_id", [])
            if key not in withheld
        ] or [marker]
        redactions.append(
            Redaction(
                surface="domain",
                field=dimension,
                marker=marker,
                count=len(hide),
                detail=f"{len(hide)} accounts withheld ({dimension} outside this view)",
            )
        )
    return withheld, markers


# ── Column ────────────────────────────────────────────────────────────────────


def _apply_columns(
    case: Case,
    persona: Persona,
    contract: KPIContract,
    accounts: Mapping[str, AccountFacts],
    withheld: set[str],
    markers: set[str],
    redactions: list[Redaction],
) -> set[str]:
    """Replace restricted values everywhere they appear, including inside prose.

    The prose pass is the one that matters. §35.4 checks the narrative, the
    evidence drill-down *and* the API payload, and a claim reading *"ACME and
    NORTHWIND account for 87.5% of the movement"* leaks two restricted names
    however carefully the structured fields were masked.
    """
    restricted = {
        field
        for field, roles in contract.access.column.items()
        if persona.role_key not in roles
    }
    if not restricted:
        return restricted

    if "account_name" in restricted:
        style = contract.access.masking.get("account_name", "hash_alias")
        canonical, aliases = _aliases(case, accounts, markers, style)
        _rename_accounts(case, canonical, aliases, withheld)
        redactions.append(
            Redaction(
                surface="column",
                field="account_name",
                marker=style,
                count=len(aliases),
                detail=f"account names hashed ({style})",
            )
        )
    else:
        canonical, aliases = {}, {}

    replacements: list[tuple[re.Pattern[str], str]] = [
        (re.compile(re.escape(identifier), re.IGNORECASE), aliases[key])
        for identifier, key in sorted(canonical.items(), key=lambda kv: -len(kv[0]))
        if identifier not in markers
    ]

    if "amount_net" in restricted:
        style = contract.access.masking.get("amount_net", "band_1_5_cr")
        replacements.append((_MONEY, "[amount restricted]"))
        redactions.append(
            Redaction(
                surface="column",
                field="amount_net",
                marker=style,
                count=len(case.ledger),
                detail=f"amounts banded ({style})",
            )
        )

    _mask_prose(case, replacements)
    return restricted


def _aliases(
    case: Case,
    accounts: Mapping[str, AccountFacts],
    markers: set[str],
    style: str,
) -> tuple[dict[str, str], dict[str, str]]:
    """Every way of naming an account, mapped to **one** alias for it.

    An account appears as an id in the contribution tree and as a name in the
    prose, and if those two resolved to different hashes a reader could tell them
    apart — which is the whole thing the alias exists to prevent. So identifiers
    are folded to a canonical id first, and the alias is a function of that.
    """
    canonical: dict[str, str] = {}
    for key in {n.key for n in _account_nodes(case)} | set(accounts):
        if key in markers:
            continue
        facts = accounts.get(key)
        canonical[key] = facts.account_id if facts else key
    aliases = {cid: _mask_name(cid, style) for cid in set(canonical.values())}
    return canonical, aliases


def _account_nodes(case: Case) -> list[ContributionNode]:
    if case.decomposition is None:
        return []
    return case.decomposition.by_dimension.get("account", [])


def _mask_name(account_id: str, style: str) -> str:
    if style != "hash_alias":
        return f"account ({style})"
    digest = hashlib.sha256(account_id.encode("utf-8")).hexdigest()[:4]
    return f"Account {digest}"


def _rename_accounts(
    case: Case,
    canonical: Mapping[str, str],
    aliases: Mapping[str, str],
    withheld: set[str],
) -> None:
    """Markers are left alone. *"2 accounts (segment restricted)"* is the thing
    §15 asks for; hashing it into `Account 4f2a` would turn a statement about
    what is hidden back into something that looks like an account."""

    def alias(key: str) -> str:
        # Markers never reach `canonical` — `_aliases` excludes them — so this is
        # the single place that decides what gets a hash. A second guard here
        # would look like belt and braces and would in fact mean neither could
        # ever be observed to fail.
        return aliases[canonical[key]] if key in canonical else key

    for node in _account_nodes(case):
        if node.key not in withheld:
            node.key = alias(node.key)
    if case.decomposition is not None:
        entities = case.decomposition.footprint.entities.get("account_id", [])
        case.decomposition.footprint.entities["account_id"] = [alias(k) for k in entities]


def _mask_prose(case: Case, replacements: Iterable[tuple[re.Pattern[str], str]]) -> None:
    """Rewrite every string a viewer could read. `EvidenceItem` is frozen (§30
    rule 4), so the ledger is rebuilt rather than mutated."""
    patterns = list(replacements)
    if not patterns:
        return

    def scrub(text: str) -> str:
        for pattern, marker in patterns:
            text = pattern.sub(marker, text)
        return text

    case.ledger = [
        item.model_copy(update={"claim": scrub(item.claim)}) for item in case.ledger
    ]
    for hypothesis in case.hypotheses:
        hypothesis.rationale = scrub(hypothesis.rationale)
    for matrix in case.tests.values():
        for name in ("timing", "locality", "dose", "control"):
            result = getattr(matrix, name)
            result.detail = scrub(result.detail)
    for check in case.verification.checks:
        check.detail = scrub(check.detail)
    if case.recommendation is not None:
        case.recommendation.action = scrub(case.recommendation.action)
        case.recommendation.monitoring = scrub(case.recommendation.monitoring)
    if case.open_question is not None:
        case.open_question.question = scrub(case.open_question.question)


# ── Banding the payload ───────────────────────────────────────────────────────

#: §11 Screen 4: `"Rs 1-5 Cr"`. One crore is 10^7.
_CRORE = 10_000_000.0
_BANDS = ((1.0, "under ₹1 Cr"), (5.0, "₹1–5 Cr"), (25.0, "₹5–25 Cr"), (100.0, "₹25–100 Cr"))


def band(value: float) -> str:
    """A magnitude band, never a rounded number. A rounded number is still a
    number and a reader will treat it as one."""
    crores = abs(value) / _CRORE
    label = next((name for edge, name in _BANDS if crores < edge), "over ₹100 Cr")
    return f"−{label}" if value < 0 else label


def _band_payload(payload: dict[str, Any]) -> None:
    for path in _MONEY_PATHS:
        _band_at(payload, path)
    tree = payload.get("decomposition")
    if isinstance(tree, dict):
        for nodes in tree.get("by_dimension", {}).values():
            _band_nodes(nodes)


def _band_nodes(nodes: Any) -> None:
    if not isinstance(nodes, list):
        return
    for node in nodes:
        if isinstance(node, dict):
            _band_at(node, ("delta",))
            _band_nodes(node.get("children"))


def _band_at(payload: Any, path: tuple[str, ...]) -> None:
    for key in path[:-1]:
        if not isinstance(payload, dict):
            return
        payload = payload.get(key)
    if not isinstance(payload, dict):
        return

    value = payload.get(path[-1])
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        payload[path[-1]] = band(float(value))
    elif isinstance(value, list) and all(isinstance(v, (int, float)) for v in value):
        payload[path[-1]] = [band(float(v)) for v in value]
