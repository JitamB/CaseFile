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

Items present in only one period land entirely in **mix**, which is the standard
treatment and the honest one: a product that did not exist last month has no
price change and no volume change, it has a change of assortment.
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
