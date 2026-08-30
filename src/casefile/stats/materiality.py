"""§23's materiality rule, in one place.

    Material iff  |z_t| > 3  AND  persistence >= 2
                  AND  |delta| / y_{t-1} >= theta_rel  AND  |delta| >= theta_abs

Four conditions, all required. §15 S1 calls this the *dual materiality gate*, and
each half is answering a different question: the statistical half asks *"is this
outside what this series normally does?"*, the business half asks *"is it big
enough to be worth a person's afternoon?"*. A movement can easily be one without
the other — a quiet KPI wobbling 40% on ₹3 L, or a ₹5 Cr swing that this series
produces every quarter — and opening a case on either is how a system teaches
people to ignore it.

It lives in `stats/` rather than in `engine/verify.py` because it is arithmetic
over a series with no knowledge of contracts, cases or the warehouse: Verify
supplies the thresholds it read from the contract, and gets a verdict back.

**Measured over the whole corpus** — four regions, the trailing twelve periods,
48 region-periods — this rule opens exactly three cases, and they are exactly
scenarios A, D and E. `tests/test_materiality.py` is that measurement.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from casefile.stats.robust_z import persistence as run_length
from casefile.stats.robust_z import robust_z
from casefile.stats.stl import decompose


@dataclass(frozen=True)
class Assessment:
    delta: float
    delta_relative: float
    robust_z: float
    persistence: int
    passed: bool
    detail: str


def assess(
    series: Sequence[float],
    period: int,
    relative: float,
    absolute: float,
    z_threshold: float,
    min_persistence: int,
) -> Assessment:
    """Judge the **last** observation of `series` against the four conditions.

    `series` must end with the period under test and carry at least two seasonal
    cycles before it; the sparse-history path in §15 is Verify's business, not
    this function's, and `decompose` raises rather than guessing.
    """
    if len(series) < 2:
        raise ValueError("materiality needs a previous period to compare against")

    latest, previous = series[-1], series[-2]
    delta = latest - previous
    relative_delta = delta / previous if previous else 0.0

    zscores = robust_z(decompose(series, period).residual)
    z = zscores[-1]
    run = run_length(zscores, z_threshold)

    reasons = []
    if abs(z) <= z_threshold:
        reasons.append(f"robust z {z:.2f} is inside the {z_threshold:g} threshold")
    if run < min_persistence:
        reasons.append(f"the movement has run {run} period(s), under the {min_persistence} needed")
    if abs(relative_delta) < relative:
        reasons.append(f"{relative_delta:+.2%} is under the {relative:.0%} relative threshold")
    if abs(delta) < absolute:
        reasons.append(f"{abs(delta):,.0f} is under the {absolute:,.0f} absolute threshold")

    if reasons:
        return Assessment(delta, relative_delta, z, run, False, "; ".join(reasons))
    return Assessment(
        delta,
        relative_delta,
        z,
        run,
        True,
        f"robust z {z:.2f} over {run} periods; {relative_delta:+.2%} and {abs(delta):,.0f} "
        f"clear the {relative:.0%} and {absolute:,.0f} thresholds",
    )
