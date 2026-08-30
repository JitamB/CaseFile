"""Price · volume · mix — §23.

    ΔRev = Σ(p₁−p₀)q₀        [PRICE]
         + Σ p₀(q₁−q₀)       [VOLUME]
         + Σ(p₁−p₀)(q₁−q₀)   [MIX]

An algebraic identity, not an approximation: expanding the three terms gives
`Σ p₁q₁ − Σ p₀q₀` exactly. That matters more than it looks. Stage 2's whole
claim is *"this is just subtraction, so it cannot be wrong"* (§15), and a
decomposition whose parts do not sum to the whole would quietly forfeit it —
so `split` returns the residual it did not explain and the caller can assert it
is zero.

**An item present in only one period keeps its price on the side it is missing
from.** Without that, a customer who left reads as a price cut to zero: the
absent side contributes `p = 0`, and the loss smears across all three terms as
`price −pq`, `volume −pq`, `mix +pq`. Those sum correctly and mean nothing. A
churned account did not renegotiate, it stopped buying — that is volume, and §10
agrees, putting the two stalled renewals there and leaving mix at −₹0.1 Cr.

Carrying the price across also leaves **mix** with its textbook meaning: the
interaction term over items whose price *and* quantity both moved.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from casefile.models import PVM

#: One item's quantity and unit price in a period.
Basket = Mapping[str, tuple[float, float]]


@dataclass(frozen=True)
class PVMSplit:
    pvm: PVM
    total_delta: float
    #: `total_delta − (price + volume + mix)`. Zero up to floating point, and
    #: asserted as such — see the module docstring.
    residual: float


def split(before: Basket, after: Basket) -> PVMSplit:
    """Decompose the revenue movement between two baskets.

    Each basket maps an item key — a product, an account, whatever grain the
    caller is working at — to `(quantity, unit_price)`.
    """
    price = volume = mix = 0.0
    total_before = total_after = 0.0

    for key in sorted(set(before) | set(after)):
        q0, p0 = before.get(key, (0.0, 0.0))
        q1, p1 = after.get(key, (0.0, 0.0))
        # An absent side has no price of its own; borrow the one it had, or will
        # have, so that appearing and vanishing are quantity changes.
        if key not in before:
            p0 = p1
        if key not in after:
            p1 = p0
        price += (p1 - p0) * q0
        volume += p0 * (q1 - q0)
        mix += (p1 - p0) * (q1 - q0)
        total_before += p0 * q0
        total_after += p1 * q1

    total = total_after - total_before
    return PVMSplit(
        pvm=PVM(price=price, volume=volume, mix=mix),
        total_delta=total,
        residual=total - (price + volume + mix),
    )
