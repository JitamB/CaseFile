"""Seasonal-trend decomposition — §23's `y_t = T_t + S_t + R_t`.

Stage 1's materiality gate runs STL first and robust-z on what is left, so that
"revenue fell 8%" is judged against the residual rather than against the raw
series: a December fall against a December peak is not news, and a system that
cannot tell the difference cries wolf every January.

statsmodels' STL is used rather than a hand-rolled LOESS — §18 names it, and the
smoother is the one part of this package where a bespoke implementation would be
harder to defend than a citation.

**On the seasonal smoother, which is not a detail.** §22 gives us 36 months
against a 12-month cycle: three observations per seasonal phase. With the
library defaults — a degree-one local fit over that window — STL interpolates
those three points almost exactly, the residual collapses to numerical dust, and
a real -₹2.6 Cr movement comes back with a robust z of **+0.66**, because the
drop was absorbed into "April is a weak month" on the strength of one April.

So the fit is pinned to a **flat seasonal profile over the whole series**
(`seasonal_deg=0`, window spanning every observation): the seasonal shape is
assumed constant rather than drifting. With three cycles that is the only
honest assumption available — a drifting seasonal profile is not estimable from
three points — and it is what puts the movement back in the residual where the
materiality gate can see it (z = -13.6, against a historical maximum of 2.5).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from statsmodels.tsa.seasonal import STL


@dataclass(frozen=True)
class Decomposition:
    """`y_t = trend_t + seasonal_t + residual_t`, index-aligned with the input."""

    trend: tuple[float, ...]
    seasonal: tuple[float, ...]
    residual: tuple[float, ...]

    def __len__(self) -> int:
        return len(self.residual)


def decompose(series: Sequence[float], period: int) -> Decomposition:
    """Split `series` into trend, seasonal and residual.

    `period` is the number of observations in one seasonal cycle — 12 for the
    monthly series every KPI in §23 is aggregated to.

    Raises `ValueError` below two full cycles. That is not a defensive check for
    an impossible case: it is scenario C. `product_ops` has eight months of
    history against a 365-day seasonal period, and §15's answer there is a
    peer-borrowed baseline with a confidence ceiling — not an STL fitted to half
    a cycle and quietly believed.
    """
    if period < 2:
        raise ValueError(f"a seasonal period of {period} is not a cycle")
    if len(series) < 2 * period:
        raise ValueError(
            f"STL needs two full cycles: {len(series)} observations against a "
            f"period of {period}. This is the sparse-history path (§15) — borrow "
            "a peer baseline and cap confidence rather than fitting this."
        )

    values = list(series)
    # An odd window spanning the series: see the module docstring.
    window = len(values) | 1
    fitted = STL(
        values, period=period, robust=True, seasonal=max(7, window), seasonal_deg=0
    ).fit()
    return Decomposition(
        trend=tuple(float(v) for v in fitted.trend),
        seasonal=tuple(float(v) for v in fitted.seasonal),
        residual=tuple(float(v) for v in fitted.resid),
    )
