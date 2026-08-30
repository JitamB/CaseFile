"""PELT change-point detection — the Timing test's continuous half, §15 S5.

Timing asks whether the cause preceded the effect by a plausible lag. For a
discrete event — a renewal, a price change — the onset *is* its date and no
detection is needed. For a continuous series it is not given: §24's integration
delay shows up as ticket volume rising from ~2.5/day to ~9.5/day, and *when* it
started is a thing to be measured, not assumed. Getting that date wrong by a
fortnight moves the lag across `max_lag_days` and flips the test.

**Pruned Exact Linear Time** (Killick, Fearnhead & Eckley 2012) over an L2 cost:
optimal partitioning, which finds the exact best segmentation for a given
penalty, plus a pruning rule that discards candidate starts which can never
again be optimal. Implemented here rather than pulled in, because it is forty
lines over prefix sums and `ruptures` would be a dependency for one function.

**On the penalty.** `2 log(n) sigma^2` over the *sample* variance — a BIC. A
robust MAD-based scale was tried first, on the reasoning that borrowed from
`robust_z`: an outlier should not inflate the threshold that is meant to catch
it. Measured against the generated ticket series it was simply wrong. MAD on a
series whose bulk is one quiet level estimates the within-segment noise and
nothing else, so the penalty came out seven times too small and PELT returned
seven change-points where there is one. The sample variance returns exactly
`2026-03-12` on both treated accounts, which is the injected onset to the day.

The failure direction matters and is the safe one: an outlier-heavy series
inflates the penalty, a real shift goes undetected, `onset` returns None and the
Timing test reports inconclusive. That is §36 R6's designed behaviour, not a
wrong answer wearing a number.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Sequence

#: Multiplier on `log(n) x sigma^2`. 2.0 is the BIC-flavoured default; higher
#: means fewer, more confident change-points.
DEFAULT_PENALTY_SCALE = 2.0
#: No segment shorter than this. A change-point that isolates two observations
#: is describing noise, and for a daily ticket series it would fire on weekends.
DEFAULT_MIN_SIZE = 4


def _scale(series: Sequence[float]) -> float:
    """The variance the penalty is expressed in. See the module docstring for
    why this is the sample variance and not a robust estimate."""
    return statistics.pvariance(series) or 1.0


def changepoints(
    series: Sequence[float],
    penalty: float | None = None,
    min_size: int = DEFAULT_MIN_SIZE,
) -> tuple[int, ...]:
    """Indices where the mean of `series` changes.

    Each returned index is the **first observation of the new segment**, so a
    series that steps up at index 20 returns `(20,)`. Endpoints are not
    change-points and are never returned.
    """
    n = len(series)
    if min_size < 1:
        raise ValueError(f"a minimum segment of {min_size} is not a segment")
    if n < 2 * min_size:
        return ()

    if penalty is None:
        penalty = DEFAULT_PENALTY_SCALE * math.log(n) * _scale(series)

    # Prefix sums make the cost of any segment O(1).
    sum1 = [0.0] * (n + 1)
    sum2 = [0.0] * (n + 1)
    for i, value in enumerate(series):
        sum1[i + 1] = sum1[i] + value
        sum2[i + 1] = sum2[i] + value * value

    def cost(start: int, end: int) -> float:
        """Within-segment sum of squares about the segment mean."""
        span = end - start
        total = sum1[end] - sum1[start]
        return (sum2[end] - sum2[start]) - total * total / span

    best = [0.0] * (n + 1)
    best[0] = -penalty
    previous = [0] * (n + 1)
    candidates = [0]

    for end in range(min_size, n + 1):
        viable = [s for s in candidates if end - s >= min_size]
        if not viable:
            best[end] = best[end - 1]
            previous[end] = previous[end - 1]
            continue

        scored = [(best[s] + cost(s, end) + penalty, s) for s in viable]
        best[end], previous[end] = min(scored)

        # Killick's pruning: a start that already costs more than the best
        # total can never be optimal for any later end.
        candidates = [s for s, (total, _) in zip(viable, scored, strict=True)
                      if total <= best[end] + penalty]
        candidates.append(end - min_size + 1)

    found: list[int] = []
    at = n
    while at > 0:
        start = previous[at]
        if start > 0:
            found.append(start)
        at = start
    return tuple(reversed(found))


def onset(series: Sequence[float], **kwargs: float | int | None) -> int | None:
    """The first change-point, or None if the series never shifts.

    This is what the Timing test asks for: *when did the cause start?* A series
    with no change-point has no onset, and returning an index anyway — the
    argmax, the first day above some threshold — would manufacture a date the
    data does not support.
    """
    points = changepoints(series, **kwargs)  # type: ignore[arg-type]
    return points[0] if points else None
