"""Rank correlation — the Dose test, §15 S5.

    Spearman rho over (cause intensity, effect magnitude);  pass iff rho > 0.5 AND n >= 5

**The `n >= 5` rule is the most load-bearing line in this package.** §15 says so
outright: the headline case has two treated accounts, so Dose *cannot* pass, so
the verdict *cannot* be Confirmed. A system that reported rho over two points
would be producing a number that looks like evidence and is not one — Spearman
on n = 2 is +/-1 by construction, whatever the data says.

Spearman rather than Pearson because dose-response is asked as *"where the cause
was stronger, was the effect stronger?"* — a monotonic question, not a linear
one, and rank correlation is robust to the account-size skew in §21 Layer 1.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from scipy import stats

from casefile.models import TestOutcome

#: §15. Below this many paired observations the test abstains rather than
#: reporting a coefficient. Not a tuning parameter — see the module docstring.
MIN_PAIRS = 5
#: §15's pass band.
PASS_RHO = 0.5


@dataclass(frozen=True)
class RankCorrelation:
    """`rho` is None exactly when the test could not be run."""

    rho: float | None
    n: int
    outcome: TestOutcome
    detail: str


def spearman(cause: Sequence[float], effect: Sequence[float]) -> RankCorrelation:
    """Dose-response over paired intensities.

    Three outcomes, and the middle one is the interesting one:

    * **pass** — rho > 0.5 on at least five pairs. More cause, more effect.
    * **refute** — rho < 0. The relationship runs *backwards*: the accounts hit
      hardest moved least, which is evidence against the hypothesis rather than
      merely absent evidence for it.
    * **inconclusive** — too few pairs, no variation to rank, or a weak positive
      relationship that neither establishes nor contradicts anything.
    """
    if len(cause) != len(effect):
        raise ValueError(f"unpaired series: {len(cause)} causes, {len(effect)} effects")

    n = len(cause)
    if n < MIN_PAIRS:
        return RankCorrelation(
            rho=None,
            n=n,
            outcome="inconclusive",
            detail=(
                f"n = {n} paired observations, below the n >= {MIN_PAIRS} minimum for "
                "Spearman — the test cannot pass here, which is why the verdict "
                "cannot be Confirmed"
            ),
        )

    if len(set(cause)) < 2 or len(set(effect)) < 2:
        return RankCorrelation(
            rho=None,
            n=n,
            outcome="inconclusive",
            detail=(
                "no exposure gradient: one of the two series is constant, so there "
                "is nothing to rank against"
            ),
        )

    rho = float(stats.spearmanr(list(cause), list(effect)).statistic)

    if rho > PASS_RHO:
        outcome: TestOutcome = "pass"
        detail = f"rho = {rho:.2f} over n = {n}: more cause, more effect"
    elif rho < 0.0:
        outcome = "refute"
        detail = (
            f"rho = {rho:.2f} over n = {n}: the relationship runs backwards — the "
            "accounts most exposed moved least"
        )
    else:
        outcome = "inconclusive"
        detail = f"rho = {rho:.2f} over n = {n}: too weak to establish or contradict"

    return RankCorrelation(rho=rho, n=n, outcome=outcome, detail=detail)
