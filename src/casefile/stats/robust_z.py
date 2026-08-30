"""Robust z on the STL residual — §23.

    z_t = (R_t − median(R)) / (1.4826 · MAD(R))

Median and MAD rather than mean and standard deviation, because the series this
runs on contains the very outliers it is trying to detect. One ₹2.4 Cr movement
inflates a standard deviation enough to hide itself; it moves a median by
nothing. 1.4826 is the constant that makes MAD estimate σ for normal data, so a
threshold of 3.0 keeps its usual reading.
"""

from __future__ import annotations

import statistics
from collections.abc import Sequence

#: MAD → σ under normality. `1 / Φ⁻¹(0.75)`.
MAD_TO_SIGMA = 1.4826
#: Mean-absolute-deviation → σ under normality, `sqrt(π/2)`. Only used when MAD
#: collapses to zero; see `_scale`.
MEAN_AD_TO_SIGMA = 1.2533


def _scale(deviations: Sequence[float]) -> float:
    """The spread estimate, with the one degenerate case handled honestly.

    MAD is zero whenever more than half the observations are identical — a flat
    series with a couple of spikes, which is exactly what a low-traffic KPI looks
    like. Dividing by it would report every spike as `inf`, so the estimator
    falls back to the mean absolute deviation, which is non-zero unless the
    series is genuinely constant.
    """
    mad = statistics.median(deviations)
    if mad > 0:
        return MAD_TO_SIGMA * mad
    mean_ad = sum(deviations) / len(deviations)
    if mean_ad > 0:
        return MEAN_AD_TO_SIGMA * mean_ad
    return 0.0


def robust_z(residuals: Sequence[float]) -> tuple[float, ...]:
    """One z per observation, index-aligned with `residuals`.

    A constant series yields all zeros rather than `nan`: nothing has deviated,
    so nothing is anomalous, and that is the true answer rather than a missing
    one.
    """
    if not residuals:
        raise ValueError("robust z over an empty series")

    centre = statistics.median(residuals)
    deviations = [abs(r - centre) for r in residuals]
    scale = _scale(deviations)
    if scale == 0.0:
        return tuple(0.0 for _ in residuals)
    return tuple((r - centre) / scale for r in residuals)


#: The bar a *preceding* period must clear for the run to continue: one robust
#: deviation on the same side of expected. See `persistence`.
CONTINUATION = 1.0


def persistence(
    zscores: Sequence[float], threshold: float, continuation: float = CONTINUATION
) -> int:
    """How many periods the movement has been running, counting back from the
    last observation.

    §23's materiality rule is `|z| > 3 ∧ persistence ≥ 2`: a single period past
    the threshold is a spike, and two is a movement. Sign matters — a fall
    followed by a rebound has not persisted, it has reverted, and counting the
    absolute value alone would call that two periods of trouble.

    **Two thresholds, not one.** The latest period must clear `threshold`; the
    ones before it need only stay on the same side of expected by `continuation`.
    Requiring 3σ in both would make the rule unsatisfiable for the case it exists
    to catch: a step change has, by construction, exactly one period at 3σ — the
    one it happened in — and everything before it is the old normal. §25 A is
    exactly that shape (Feb -1.9, Mar -1.5, **Apr -13.6**), and a single-threshold
    rule would refuse to open the headline case of the entire project.

    Hysteresis like this is the standard construction in statistical process
    control, and it says what a business person means by *"has this been going
    the wrong way?"* rather than *"has it been catastrophic twice?"*
    """
    if not zscores:
        return 0
    last = zscores[-1]
    if abs(last) <= threshold:
        return 0
    rising = last > 0

    count = 0
    for index, z in enumerate(reversed(zscores)):
        bar = threshold if index == 0 else continuation
        if abs(z) > bar and (z > 0) == rising:
            count += 1
        else:
            break
    return count
