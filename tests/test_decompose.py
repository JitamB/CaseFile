"""Ladder step 1.4 — Stage 2, Decompose.

The step's verify command from §44:

    "K(2) >= 0.85 on scenario A; cross-KPI residual <= 2%"

Both are here, measured against the sealed answer sheet. §15 calls Stage 2 *the
pivot* and rests it on one claim — *"this is just subtraction, so it cannot be
wrong"* — so most of this file is that claim being checked: shares sum to one,
PVM sums to the movement, the residual is what is left rather than what was
convenient, and nothing is quietly truncated.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import duckdb
import pytest

from casefile.contract import load_all
from casefile.engine.decompose import (
    MAX_DEPTH,
    NON_RECURRING,
    RESIDUAL_TOLERANCE,
    DecomposeError,
    decompose,
    residual,
)
from casefile.models import ContributionNode, ContributionTree, KPIContract

ROOT = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.gate1


@pytest.fixture(scope="module")
def contracts() -> dict[str, KPIContract]:
    return load_all(ROOT / "contracts")


@pytest.fixture(scope="module")
def con(warehouse: Path) -> duckdb.DuckDBPyConnection:
    connection = duckdb.connect(str(warehouse), read_only=True)
    yield connection
    connection.close()


@pytest.fixture(scope="module")
def sealed(generated: Path) -> dict[str, dict]:
    """`tests/` only — §30 rule 3."""
    return json.loads((generated / "ground_truth.json").read_text(encoding="utf-8"))["scenarios"]


@pytest.fixture(scope="module")
def east(
    con: duckdb.DuckDBPyConnection, contracts: dict[str, KPIContract]
) -> ContributionTree:
    return decompose(con, contracts["net_revenue"], "2026-04", {"region": "East"})


def depth(nodes: list[ContributionNode]) -> int:
    return 1 + max((depth(n.children) for n in nodes if n.children), default=0)


# ── The ladder's two verify commands ──────────────────────────────────────────


def test_two_accounts_carry_the_movement(east: ContributionTree) -> None:
    """§44 1.4, and §10's headline: *"88% of it is two accounts"*. §35.2 asserts
    ranges, so the gate is the 0.85 floor rather than the exact figure."""
    assert east.concentration(2) >= 0.85
    assert east.concentration(2) == pytest.approx(0.91, abs=0.03)


def test_the_cross_kpi_identity_reconciles(east: ContributionTree) -> None:
    """§23: *"residual tolerance <= 2% of |ΔNetRev|, else flagged as a
    reconciliation break"*. Measured at 0.00%, because the movement is
    **partitioned** rather than reassembled from CRM flows — every rupee is in
    exactly one bucket by construction."""
    assert residual(east) <= RESIDUAL_TOLERANCE
    assert residual(east) == pytest.approx(0.0, abs=1e-6)


def test_the_renewal_rate_carries_the_share_section_10_quotes(
    east: ContributionTree,
) -> None:
    """§10's decomposition line: *"renewal_rate −₹2.1 Cr (88%)"*."""
    renewals = next(n for n in east.by_dimension["kpi"] if n.key == "gross_renewal_rate")
    assert renewals.share == pytest.approx(0.88, abs=0.03)
    assert renewals.delta < 0


# ── The footprint everything downstream is scoped by ─────────────────────────


def test_the_footprint_is_the_two_accounts_the_answer_sheet_seals(
    east: ContributionTree, sealed: dict[str, dict]
) -> None:
    """§35.2: `set(case.decomposition.footprint.accounts) == set(truth.accounts)`.

    Nothing told Stage 2 which accounts were treated. It arrived at them by
    subtraction, which is the entire argument for doing arithmetic before asking
    a model anything.
    """
    assert east.footprint.entities["account_id"] == sorted(sealed["A"]["footprint_accounts"])


def test_the_footprint_window_spans_both_periods(east: ContributionTree) -> None:
    """§15 S5's Timing test compares a cause's onset against the effect, and the
    effect began somewhere inside the comparison rather than on the first of the
    month. A window covering only April would put the 2026-03-12 onset outside
    the footprint entirely."""
    assert east.footprint.window_start == date(2026, 3, 1)
    assert east.footprint.window_end == date(2026, 4, 30)
    assert east.footprint.window_start < date(2026, 3, 12) < east.footprint.window_end


def test_the_footprint_delta_is_the_footprint_accounts_movement(
    east: ContributionTree,
) -> None:
    accounts = set(east.footprint.entities["account_id"])
    by_hand = sum(n.delta for n in east.by_dimension["account"] if n.key in accounts)

    assert east.footprint.delta == pytest.approx(by_hand)
    assert abs(east.footprint.delta) > 0.80 * abs(east.total_delta)


# ── "Just subtraction, so it cannot be wrong" — checked ──────────────────────


@pytest.mark.parametrize("dimension", ["segment", "account", "kpi"])
def test_every_dimension_sums_to_the_whole_movement(
    east: ContributionTree, dimension: str
) -> None:
    nodes = east.by_dimension[dimension]
    assert sum(n.delta for n in nodes) == pytest.approx(east.total_delta, rel=1e-9)
    assert sum(n.share for n in nodes) == pytest.approx(1.0, rel=1e-9)


def test_price_volume_and_mix_sum_to_the_movement(east: ContributionTree) -> None:
    assert east.pvm is not None
    assert east.pvm.price + east.pvm.volume + east.pvm.mix == pytest.approx(
        east.total_delta, rel=1e-9
    )


def test_the_churn_lands_in_volume_rather_than_price(east: ContributionTree) -> None:
    """Two accounts stopped buying; they did not renegotiate to zero. Reading an
    absent side as `p = 0` smears the loss across all three terms — it sums
    correctly and means nothing."""
    assert east.pvm is not None
    assert east.pvm.volume < 0
    assert abs(east.pvm.volume) > abs(east.pvm.mix)


def test_no_contributor_is_collapsed_into_an_others_bucket(
    con: duckdb.DuckDBPyConnection, east: ContributionTree
) -> None:
    """The quiet one. `concentration` divides by `Σ|Δᵢ|` over whatever nodes it
    finds, so folding the tail into a single "others" node shrinks that
    denominator by cancellation and **inflates K(2)** — the project's headline
    number, in the flattering direction.

    Every account that moved is a node. Truncation is presentation, and belongs
    in the UI.
    """
    moved = con.execute(
        """
        WITH monthly AS (
          SELECT account_id, strftime(invoice_date, '%Y-%m') p, sum(amount_net) v
            FROM billing.invoice_line
           WHERE region = 'East' AND strftime(invoice_date, '%Y-%m') IN ('2026-03', '2026-04')
             AND account_id NOT IN (SELECT account_id FROM crm.account WHERE is_test)
           GROUP BY 1, 2)
        SELECT count(*) FROM (
          SELECT account_id,
                 sum(CASE WHEN p = '2026-04' THEN v ELSE 0 END)
               - sum(CASE WHEN p = '2026-03' THEN v ELSE 0 END) d
            FROM monthly GROUP BY 1) WHERE d <> 0
        """
    ).fetchone()
    assert moved is not None

    assert len(east.by_dimension["account"]) == moved[0]
    assert not any(n.key in ("others", "other", "rest") for n in east.by_dimension["account"])


def test_hhi_says_the_movement_is_concentrated(east: ContributionTree) -> None:
    """`HHI = Σ (Δᵢ/Δ_total)²` — §23. One contributor gives 1.0; a movement
    spread evenly over forty-eight gives about 0.02."""
    assert east.hhi is not None
    assert 0.3 < east.hhi < 1.0
    by_hand = sum((n.delta / east.total_delta) ** 2 for n in east.by_dimension["account"])
    assert east.hhi == pytest.approx(by_hand)


# ── The tree ──────────────────────────────────────────────────────────────────


def test_the_tree_nests_to_at_most_three_levels(east: ContributionTree) -> None:
    """§15: *"greedy top-down to 80% or depth 3"*."""
    for nodes in east.by_dimension.values():
        assert depth(nodes) <= MAX_DEPTH


def test_only_the_contributors_are_opened_up(east: ContributionTree) -> None:
    """Expanding the tail would multiply the tree by every account that did
    nothing, and each of those branches is a row somebody has to read past."""
    segments = east.by_dimension["segment"]
    with_children = [n for n in segments if n.children]

    assert with_children, "the tree never nested at all"
    assert all(abs(n.delta) > 0 for n in with_children)
    assert segments[0].children, "the largest contributor must be the one opened"
    assert not segments[-1].children


def test_a_dimension_no_term_can_carry_is_skipped_rather_than_half_computed(
    east: ContributionTree, contracts: dict[str, KPIContract]
) -> None:
    """`net_revenue` declares `[region, segment, product, account]`, but it
    subtracts credit notes and a credit note has no product. A per-product split
    would silently omit the credit side and the shares would not sum to the
    movement — so the dimension is dropped, loudly enough to be tested."""
    assert "product" in contracts["net_revenue"].decomposition_dims
    assert "product" not in east.by_dimension
    assert set(east.by_dimension) == {"segment", "account", "kpi"}


# ── Other KPIs, and the edges ────────────────────────────────────────────────


def test_a_kpi_with_no_quantity_has_no_price_volume_mix(
    con: duckdb.DuckDBPyConnection, contracts: dict[str, KPIContract]
) -> None:
    """A renewal rate has no volume and a median resolution time has no unit
    price. Inventing one would put a number on the case file that means
    nothing."""
    tree = decompose(con, contracts["gross_renewal_rate"], "2026-04", {"region": "East"})
    assert tree.pvm is None
    assert tree.by_dimension, "the rest of the decomposition must still work"


def test_a_kpi_with_no_composition_edges_has_no_cross_kpi_dimension(
    con: duckdb.DuckDBPyConnection, contracts: dict[str, KPIContract]
) -> None:
    tree = decompose(con, contracts["gross_renewal_rate"], "2026-04", {"region": "East"})
    assert not contracts["gross_renewal_rate"].composition
    assert "kpi" not in tree.by_dimension
    assert residual(tree) == 0.0


def test_the_non_recurring_term_is_named_rather_than_left_as_residual(
    east: ContributionTree,
) -> None:
    """§23's identity ends `+ ΔNonRecurring(t)`. It is a named part of the
    formula, so it is a node; folding it into the residual would report a 13%
    reconciliation break on a movement that reconciles exactly."""
    node = next(n for n in east.by_dimension["kpi"] if n.key == NON_RECURRING)
    assert node.delta != 0
    assert residual(east) == pytest.approx(0.0, abs=1e-6)


def test_a_period_that_did_not_move_cannot_be_decomposed(
    con: duckdb.DuckDBPyConnection, contracts: dict[str, KPIContract]
) -> None:
    """Dividing by a zero movement gives shares of infinity. Refusing is the only
    honest answer, and it is what Verify would already have closed the case on."""
    with pytest.raises(DecomposeError, match="nothing moved"):
        decompose(con, contracts["net_revenue"], "2022-01", {"region": "East"})


def test_decompose_needs_no_model_either(
    con: duckdb.DuckDBPyConnection, contracts: dict[str, KPIContract]
) -> None:
    """§17: *"contribution is arithmetic; a model can only add error."* The same
    import-graph argument as Verify — see `tests/test_verify.py`."""
    import ast

    src = ROOT / "src" / "casefile"
    reached: set[str] = set()
    frontier = ["engine.decompose"]
    while frontier:
        module = frontier.pop()
        if module in reached:
            continue
        reached.add(module)
        path = src / (module.replace(".", "/") + ".py")
        if not path.exists():
            path = src / module.replace(".", "/") / "__init__.py"
        if not path.exists():
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = []
            if isinstance(node, ast.ImportFrom) and node.module:
                names.append(node.module)
            elif isinstance(node, ast.Import):
                names += [a.name for a in node.names]
            frontier += [n[len("casefile."):] for n in names if n.startswith("casefile.")]

    assert reached
    assert not any(m.startswith("llm") for m in reached)
