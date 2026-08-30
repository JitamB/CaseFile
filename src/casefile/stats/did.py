"""Difference-in-differences and placebo inference — the Control test, §15 S5.

    DiD = (Y_post^E - Y_pre^E) - (Y_post^C - Y_pre^C)

*"Did comparable segments without the cause behave differently?"* The subtraction
removes anything that moved both groups — seasonality, a market-wide shift, the
company's own trend — which is the whole reason a raw before/after cannot support
a causal claim.

**Inference is by placebo rank, not by a confidence interval.** §15 is explicit
about why: with two treated accounts an interval estimate would be indefensible,
and the same small-n honesty that makes Dose inconclusive applies here. So the
treatment is reassigned to each matched control in turn and the real effect is
ranked among the pretend ones. It reads in one sentence — *"the true effect is
larger than all six pretend ones"* — and a leader can follow it.

The rank is **two-sided**, on |effect|. A placebo that swung hugely the other way
is still a control group behaving dramatically, and treating it as harmless
because the sign was inconvenient would be the thumb on the scale this whole
package exists to avoid.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from casefile.models import TestOutcome

#: One unit's mean outcome before and after the onset.
Panel = Mapping[str, tuple[float, float]]

#: Fewer matched controls than this and the rank carries no information: being
#: the most extreme of three is one chance in three. §36 R6 names the honest
#: answer for a case with no usable control group, and it is `inconclusive`.
MIN_CONTROLS = 5


@dataclass(frozen=True)
class PlaceboResult:
    effect: float
    placebo_effects: tuple[float, ...]
    #: 1 = more extreme than every placebo.
    rank: int
    outcome: TestOutcome
    detail: str

    @property
    def pseudo_p(self) -> float:
        """`rank / (placebos + 1)` — the permutation p-value this rank implies."""
        return self.rank / (len(self.placebo_effects) + 1)


def _mean_change(panel: Panel) -> float:
    if not panel:
        raise ValueError("difference-in-differences over an empty group")
    return sum(post - pre for pre, post in panel.values()) / len(panel)


def did(treated: Panel, controls: Panel) -> float:
    """The point estimate. Each unit maps to `(pre_mean, post_mean)`."""
    return _mean_change(treated) - _mean_change(controls)


def placebo_rank(treated: Panel, controls: Panel) -> PlaceboResult:
    """Rank the real effect against one placebo per matched control.

    Each placebo reassigns the treatment to a single control unit and recomputes
    DiD against the remaining controls. That is the standard few-treated design:
    it asks *"how often does a control group produce a swing this large by
    itself?"* and answers with a count rather than an assumption about the error
    distribution.
    """
    if len(controls) < MIN_CONTROLS:
        return PlaceboResult(
            effect=did(treated, controls) if controls else 0.0,
            placebo_effects=(),
            rank=0,
            outcome="inconclusive",
            detail=(
                f"{len(controls)} matched controls, below the {MIN_CONTROLS} needed "
                "for a placebo rank to carry information — no valid control group"
            ),
        )

    effect = did(treated, controls)

    placebos: list[float] = []
    for name in sorted(controls):
        rest = {k: v for k, v in controls.items() if k != name}
        placebos.append(did({name: controls[name]}, rest))

    rank = 1 + sum(1 for p in placebos if abs(p) > abs(effect))
    total = len(placebos) + 1

    if rank == 1:
        outcome: TestOutcome = "pass"
        detail = (
            f"DiD {effect:,.0f}; the real effect is rank 1 of {total} against "
            f"{len(placebos)} placebo assignments"
        )
    elif rank > total / 2:
        outcome = "refute"
        detail = (
            f"DiD {effect:,.0f}; rank {rank} of {total} — most matched controls "
            "produced a larger swing on their own, so the exposed group did not "
            "behave differently"
        )
    else:
        outcome = "inconclusive"
        detail = (
            f"DiD {effect:,.0f}; rank {rank} of {total} — more extreme than most "
            "placebos but not all of them"
        )

    return PlaceboResult(
        effect=effect,
        placebo_effects=tuple(placebos),
        rank=rank,
        outcome=outcome,
        detail=detail,
    )
