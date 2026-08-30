"""Stage 2 — Decompose. §15 S2, **the pivot**.

*"Finding which tap is running before asking why the bill is high. 'Revenue in
the East fell 8%' is unanswerable. '88% of it is two accounts' is answerable.
This is just subtraction, so it cannot be wrong."*

**In:** a verified movement, the contract's `decomposition_dims` and
`composition`. **Out:** a `ContributionTree` carrying the `Footprint` that scopes
everything downstream — which hypotheses get enumerated, what retrieval may see,
what the four challenge tests compare against.

Three decompositions, and the claim that they *cannot be wrong* is only worth
making if it is checked:

* **Additive contribution** — Δ per key, per dimension. Every key is kept, never
  truncated to a "top N plus others". `ContributionTree.concentration` divides by
  `Σ|Δᵢ|` over whatever nodes it finds, so collapsing the tail into one node
  shrinks that denominator by cancellation and **inflates K(k)** — the headline
  number of the entire project, quietly, in the flattering direction. Truncation
  is a presentation choice and belongs in the UI.
* **Price · volume · mix** — §23's identity, over `stats/pvm.py`. Only for KPIs
  billed at a quantity and a unit price; `None` otherwise, because a median
  resolution time has no price.
* **Cross-KPI attribution** — §23's `ΔNetRev = 1/12·[ΔARR…] + ΔNonRecurring`,
  computed by partitioning the actual billing movement rather than by summing
  CRM flows. Those are different quantities: an ARR flow recorded this month may
  bill from next, and adding them would produce a reconciliation break that is an
  artefact of the arithmetic rather than of the business. Partitioning gives a
  **residual of 0.00%** against §23's 2% tolerance, because every rupee is in
  exactly one bucket by construction.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import duckdb

from casefile.metric import (
    PERIOD_COLUMN,
    calendar_months,
    parse,
    period_bounds,
    sliceable,
    value,
)
from casefile.models import (
    PVM,
    ContributionNode,
    ContributionTree,
    Footprint,
    KPIContract,
)
from casefile.stats.pvm import split

#: §15: greedy top-down "to 80% or depth 3". The share of the movement the
#: footprint must cover, and how deep the tree nests.
FOOTPRINT_COVERAGE = 0.80
MAX_DEPTH = 3
#: §23's reconciliation tolerance on the cross-KPI identity.
RESIDUAL_TOLERANCE = 0.02
#: The node that carries §23's `+ ΔNonRecurring(t)` term. It is a named part of
#: the identity, not a leftover, so it is a node rather than the residual.
NON_RECURRING = "non_recurring"

#: `decomposition_dims` names concepts; the warehouse names columns. §14.1 says
#: `[region, segment, product, account]`, and two of those are keys.
DIMENSION_COLUMN = {"account": "account_id", "product": "product_id"}


def _column(dimension: str) -> str:
    return DIMENSION_COLUMN.get(dimension, dimension)


class DecomposeError(ValueError):
    """The movement cannot be decomposed — no dimensions, or nothing moved."""


@dataclass(frozen=True)
class _Window:
    previous: str
    current: str
    start: date
    end: date


def decompose(
    con: duckdb.DuckDBPyConnection,
    contract: KPIContract,
    period: str,
    dimensions: dict[str, str] | None = None,
) -> ContributionTree:
    """Split the movement every way the contract declares."""
    dimensions = dimensions or {}
    window = _window(con, contract, period)
    total = _delta(con, contract, window, dimensions)
    if total == 0:
        raise DecomposeError(f"{contract.id} {period}: nothing moved, nothing to decompose")

    free = [
        d
        for d in contract.decomposition_dims
        if d not in dimensions and sliceable(con, contract, _column(d))
    ]
    if not free:
        raise DecomposeError(
            f"{contract.id}: none of {contract.decomposition_dims} can slice every term "
            "of the formula, so there is no decomposition that adds up"
        )
    by_dimension = {
        dimension: _nodes(con, contract, window, dimensions, dimension, total)
        for dimension in free
    }
    if contract.composition:
        by_dimension["kpi"] = _cross_kpi(con, contract, window, dimensions, total)

    _nest(con, contract, window, dimensions, by_dimension, free, total)

    accounts = _footprint_keys(by_dimension.get("account", []))
    return ContributionTree(
        kpi=contract.id,
        period=period,
        total_delta=total,
        by_dimension=by_dimension,
        footprint=Footprint(
            entities={"account_id": accounts},
            window_start=window.start,
            window_end=window.end,
            delta=sum(
                node.delta for node in by_dimension.get("account", []) if node.key in accounts
            ),
        ),
        pvm=_pvm(con, contract, window, dimensions),
        hhi=_hhi(by_dimension.get("account", []), total),
    )


def residual(tree: ContributionTree) -> float:
    """How much of the movement the cross-KPI identity failed to place, as a
    share of |Δ|. §23 flags anything over 2% as a reconciliation break."""
    nodes = tree.by_dimension.get("kpi")
    if not nodes or tree.total_delta == 0:
        return 0.0
    return abs(tree.total_delta - sum(node.delta for node in nodes)) / abs(tree.total_delta)


# ── The window ────────────────────────────────────────────────────────────────


def _window(
    con: duckdb.DuckDBPyConnection, contract: KPIContract, period: str
) -> _Window:
    """This period and the one before it.

    The footprint's window spans **both**, because §15 S5's Timing test compares
    a cause's onset against an effect that began somewhere inside the comparison,
    not on the first of the month.
    """
    start, end = period_bounds(con, contract, period)
    labels = calendar_months(date(start.year - 1, start.month, 1), end)
    if len(labels) < 2:
        raise DecomposeError(f"{contract.id} {period}: no previous period")
    previous = labels[-2]
    earlier, _ = period_bounds(con, contract, previous)
    return _Window(previous=previous, current=period, start=earlier, end=end)


# ── Additive contribution ─────────────────────────────────────────────────────


def _delta(
    con: duckdb.DuckDBPyConnection,
    contract: KPIContract,
    window: _Window,
    dimensions: dict[str, str],
) -> float:
    latest = value(con, contract, window.current, dimensions)
    earlier = value(con, contract, window.previous, dimensions)
    return (latest or 0.0) - (earlier or 0.0)


def _keys(
    con: duckdb.DuckDBPyConnection,
    contract: KPIContract,
    window: _Window,
    dimensions: dict[str, str],
    dimension: str,
) -> list[str]:
    """Every value of `dimension` that appears in either period.

    Read from the data rather than from a registry: an account that churned this
    month still has to appear, carrying the negative that explains the movement.
    """
    term = parse(contract.formula).numerator[0]
    column = _column(dimension)
    on_table = con.execute(
        "SELECT 1 FROM duckdb_columns() WHERE table_name = ? AND column_name = ?",
        [term.table, column],
    ).fetchall()

    source = f"{term.qualified} AS {term.table}"
    select = f"{term.table}.{column}"
    if not on_table:
        source += " JOIN crm.account AS account USING (account_id)"
        select = f"account.{column}"

    where = [f"{term.table}.{PERIOD_COLUMN[term.table]}::DATE BETWEEN ? AND ?"]
    params: list[object] = [window.start, window.end]
    for name, wanted in dimensions.items():
        fixed = _column(name)
        held = con.execute(
            "SELECT 1 FROM duckdb_columns() WHERE table_name = ? AND column_name = ?",
            [term.table, fixed],
        ).fetchall()
        if held:
            where.append(f"{term.table}.{fixed} = ?")
        else:
            if "crm.account" not in source:
                source += " JOIN crm.account AS account USING (account_id)"
            where.append(f"account.{fixed} = ?")
        params.append(wanted)

    rows = con.execute(
        f"SELECT DISTINCT {select} FROM {source} WHERE {' AND '.join(where)}", params
    ).fetchall()
    return sorted(str(r[0]) for r in rows if r[0] is not None)


def _nodes(
    con: duckdb.DuckDBPyConnection,
    contract: KPIContract,
    window: _Window,
    dimensions: dict[str, str],
    dimension: str,
    total: float,
) -> list[ContributionNode]:
    column = _column(dimension)
    nodes = []
    for key in _keys(con, contract, window, dimensions, dimension):
        delta = _delta(con, contract, window, {**dimensions, column: key})
        if delta == 0:
            continue
        nodes.append(
            ContributionNode(
                dimension=dimension, key=key, delta=delta, share=delta / total
            )
        )
    return sorted(nodes, key=lambda n: (-abs(n.delta), n.key))


def _nest(
    con: duckdb.DuckDBPyConnection,
    contract: KPIContract,
    window: _Window,
    dimensions: dict[str, str],
    by_dimension: dict[str, list[ContributionNode]],
    free: list[str],
    total: float,
) -> None:
    """§15's *"greedy top-down to 80% or depth 3"*.

    Only the contributors that make up the movement are opened up. Expanding the
    tail would multiply the tree by the number of accounts that did nothing, and
    every one of those branches is a row a person has to read past.
    """
    if len(free) < 2:
        return

    ranked = sorted(free, key=lambda d: -_concentration(by_dimension[d]))
    order = ranked[:MAX_DEPTH]

    def expand(nodes: list[ContributionNode], held: dict[str, str], depth: int) -> None:
        if depth >= len(order):
            return
        child_dim = order[depth]
        for node in _explaining(nodes):
            inner = {**held, _column(node.dimension): node.key}
            children = _nodes(con, contract, window, inner, child_dim, node.delta or total)
            node.children.extend(_explaining(children))
            expand(node.children, inner, depth + 1)

    expand(by_dimension[order[0]], dimensions, 1)


def _explaining(nodes: list[ContributionNode]) -> list[ContributionNode]:
    """The leading nodes that together cover `FOOTPRINT_COVERAGE` of `Σ|Δ|`."""
    magnitudes = sum(abs(node.delta) for node in nodes)
    if magnitudes == 0:
        return []

    covered = 0.0
    chosen: list[ContributionNode] = []
    for node in nodes:
        chosen.append(node)
        covered += abs(node.delta)
        if covered / magnitudes >= FOOTPRINT_COVERAGE:
            break
    return chosen


def _concentration(nodes: list[ContributionNode]) -> float:
    magnitudes = sorted((abs(n.delta) for n in nodes), reverse=True)
    total = sum(magnitudes)
    return sum(magnitudes[:2]) / total if total else 0.0


def _footprint_keys(nodes: list[ContributionNode]) -> list[str]:
    return sorted(node.key for node in _explaining(nodes))


def _hhi(nodes: list[ContributionNode], total: float) -> float | None:
    """`HHI = Σ (Δᵢ/Δ_total)²` — §23. One contributor gives 1.0; a movement
    spread evenly over fifty gives 0.02."""
    if not nodes or total == 0:
        return None
    return sum((node.delta / total) ** 2 for node in nodes)


# ── Price · volume · mix ──────────────────────────────────────────────────────


def _pvm(
    con: duckdb.DuckDBPyConnection,
    contract: KPIContract,
    window: _Window,
    dimensions: dict[str, str],
) -> PVM | None:
    """§23's three-way split, at (account × product) grain.

    `None` where the KPI is not billed at a quantity and a price. A renewal rate
    has no volume and a median resolution time has no unit price, and inventing
    one would put a number on the case file that means nothing.
    """
    term = parse(contract.formula).numerator[0]
    columns = con.execute(
        "SELECT column_name FROM duckdb_columns() WHERE table_name = ?", [term.table]
    ).fetchall()
    held = {str(r[0]) for r in columns}
    if not {"qty", "unit_price", "amount_net"} <= held:
        return None

    baskets: dict[str, dict[str, tuple[float, float]]] = {}
    for label in (window.previous, window.current):
        start, end = period_bounds(con, contract, label)
        where = [f"{PERIOD_COLUMN[term.table]}::DATE BETWEEN ? AND ?"]
        params: list[object] = [start, end]
        for name, wanted in dimensions.items():
            where.append(f"{name} = ?")
            params.append(wanted)

        rows = con.execute(
            f"SELECT account_id || '/' || product_id AS item, sum(qty), sum(amount_net) "
            f"FROM {term.qualified} WHERE {' AND '.join(where)} GROUP BY 1",
            params,
        ).fetchall()
        baskets[label] = {
            str(item): (float(qty), float(net) / float(qty))
            for item, qty, net in rows
            if qty
        }

    return split(baskets[window.previous], baskets[window.current]).pvm


# ── Cross-KPI attribution ─────────────────────────────────────────────────────


def _cross_kpi(
    con: duckdb.DuckDBPyConnection,
    contract: KPIContract,
    window: _Window,
    dimensions: dict[str, str],
    total: float,
) -> list[ContributionNode]:
    """§23's identity, by **partitioning** the movement rather than summing flows.

    Each account's recurring change lands in exactly one bucket, decided by what
    the CRM says happened to that account in the window: a renewal that did not
    renew, a first contract, an upsell that closed. Non-recurring revenue is
    §23's own `+ ΔNonRecurring(t)` term and gets its own node. What is left over
    is genuinely unexplained, and `residual()` reports it.
    """
    term = parse(contract.formula).numerator[0]
    columns = con.execute(
        "SELECT column_name FROM duckdb_columns() WHERE table_name = ?", [term.table]
    ).fetchall()
    if "is_recurring" not in {str(r[0]) for r in columns}:
        return []

    edges = {edge.kpi for edge in contract.composition}
    changes = _recurring_change(con, term.qualified, window, dimensions)
    classified = _classify(con, window, set(changes))

    buckets = dict.fromkeys(sorted(edges), 0.0)
    unplaced = 0.0
    for account, delta in changes.items():
        bucket = classified.get(account)
        if bucket in buckets:
            buckets[bucket] += delta
        else:
            unplaced += delta

    nodes = [
        ContributionNode(dimension="kpi", key=kpi, delta=delta, share=delta / total)
        for kpi, delta in buckets.items()
    ]
    non_recurring = _non_recurring_change(con, term.qualified, window, dimensions)
    nodes.append(
        ContributionNode(
            dimension="kpi",
            key=NON_RECURRING,
            delta=non_recurring + unplaced,
            share=(non_recurring + unplaced) / total,
        )
    )
    return sorted(nodes, key=lambda n: (-abs(n.delta), n.key))


def _recurring_change(
    con: duckdb.DuckDBPyConnection,
    table: str,
    window: _Window,
    dimensions: dict[str, str],
) -> dict[str, float]:
    return dict(_side(con, table, window, dimensions, recurring=1))


def _non_recurring_change(
    con: duckdb.DuckDBPyConnection,
    table: str,
    window: _Window,
    dimensions: dict[str, str],
) -> float:
    return sum(delta for _, delta in _side(con, table, window, dimensions, recurring=0))


def _side(
    con: duckdb.DuckDBPyConnection,
    table: str,
    window: _Window,
    dimensions: dict[str, str],
    recurring: int,
) -> list[tuple[str, float]]:
    where = ["is_recurring = ?", "strftime(invoice_date, '%Y-%m') IN (?, ?)"]
    params: list[object] = [recurring, window.previous, window.current]
    for name, wanted in dimensions.items():
        where.append(f"{name} = ?")
        params.append(wanted)

    return [
        (str(account), float(delta))
        for account, delta in con.execute(
            f"""
            WITH monthly AS (
              SELECT account_id, strftime(invoice_date, '%Y-%m') AS p, sum(amount_net) AS v
                FROM {table} WHERE {' AND '.join(where)} GROUP BY 1, 2)
            SELECT account_id,
                   sum(CASE WHEN p = ? THEN v ELSE 0 END)
                 - sum(CASE WHEN p = ? THEN v ELSE 0 END)
              FROM monthly GROUP BY 1
            """,
            [*params, window.current, window.previous],
        ).fetchall()
    ]


def _classify(
    con: duckdb.DuckDBPyConnection, window: _Window, accounts: set[str]
) -> dict[str, str]:
    """Which composed KPI owns each account's recurring change.

    Order matters and is not arbitrary: an account that churned *and* had an
    upsell close in the same fortnight belongs to the renewal, because the upsell
    left with it.
    """
    if not accounts:
        return {}

    churned = {
        str(r[0])
        for r in con.execute(
            "SELECT DISTINCT account_id FROM crm.renewal "
            "WHERE outcome <> 'renewed' AND closed_date BETWEEN ? AND ?",
            [window.start, window.end],
        ).fetchall()
    }
    launched = {
        str(r[0])
        for r in con.execute(
            "SELECT DISTINCT account_id FROM crm.account "
            "WHERE first_contract_date BETWEEN ? AND ?",
            [window.start, window.end],
        ).fetchall()
    }
    expanded = {
        str(r[0])
        for r in con.execute(
            "SELECT DISTINCT account_id FROM crm.opportunity "
            "WHERE type = 'expansion' AND closed_won = 1 AND close_date BETWEEN ? AND ?",
            [window.start, window.end],
        ).fetchall()
    }

    owner: dict[str, str] = {}
    for account in accounts:
        if account in churned:
            owner[account] = "gross_renewal_rate"
        elif account in launched:
            owner[account] = "new_business_arr"
        elif account in expanded:
            owner[account] = "expansion_arr"
    return owner
