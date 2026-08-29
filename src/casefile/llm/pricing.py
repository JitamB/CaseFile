"""The price table — §19.

Prices are configuration, not code. §19 says so explicitly ("the telemetry
module reads a price table, so they are configuration"), and it is the reason
D-2 could name a tier without the tier becoming a commitment: switching the
demo path from Sonnet to Haiku is an env var, not an edit.

Keys are model *classes*, not API model ids. A caller passes the class it is
billed at; mapping an id like `claude-sonnet-4-5` onto `sonnet` belongs to the
provider that knows its own catalogue, not here.
"""

from __future__ import annotations

from typing import NamedTuple

USD_INR = 83.0


class TokenPrice(NamedTuple):
    input_usd_per_mtok: float
    output_usd_per_mtok: float


# First-party API rates, §19.
PRICES: dict[str, TokenPrice] = {
    "opus": TokenPrice(5.0, 25.0),
    "sonnet": TokenPrice(3.0, 15.0),
    "haiku": TokenPrice(1.0, 5.0),
    # A stub call costs nothing, so a stub-driven run reports ₹0 honestly rather
    # than reporting a number nobody was charged.
    "stub": TokenPrice(0.0, 0.0),
}


def cost_inr(model: str, input_tokens: int, output_tokens: int) -> float:
    """Rupee cost of one call. Unknown model classes raise rather than default to
    zero — a silently free call would understate the budget we publish."""
    try:
        price = PRICES[model]
    except KeyError:
        raise KeyError(
            f"no price for model class {model!r}; known classes: {sorted(PRICES)}"
        ) from None

    usd = (
        input_tokens * price.input_usd_per_mtok + output_tokens * price.output_usd_per_mtok
    ) / 1_000_000
    return round(usd * USD_INR, 4)
