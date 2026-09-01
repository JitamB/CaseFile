"""Feedback — §15 S9, the learning stage.

*"Learning from being wrong — numbers you can watch move, not a model
retrained in the background."* Three marks, three narrow effects (§02
architecture's own Stage 9 table), each pure arithmetic or a registry lookup:

| Mark | Changes | Effect |
|---|---|---|
| `correct_driver` | `driver_prior` up | tried first, gathered on more deeply next time |
| `wrong_driver` | `driver_prior` down | tried later, gathered on less deeply next time |
| `not_material` | `not_material_count` up | relaxes S1's materiality gate — fewer alarms |
| `missed_cause` | the contract's `drivers` list | promotes an `unmodelled` gap into a real driver |

The verdict rubric itself never reads any of this — S6's adjudication stays exactly
as deterministic and auditable as before a single mark has ever been recorded. What
moves is presentation order (`reorder`) and how hard Stage 4 looks (`gathering_depth`),
both read *before* Stage 6 runs, never after — and the materiality threshold Stage 1
reads on the *next* case, never the one the mark was left on.

Every function here is pure: `apply()`, `adjusted_materiality()`, `promote()` and
`reorder()` all return a new object rather than mutating the one passed in, the same
discipline `models.py` rule 4 already holds evidence items to.
"""

from __future__ import annotations

from typing import Literal, Self

from pydantic import Field, model_validator

from casefile.models import Base, Driver, Hypothesis, KPIContract, Materiality

FeedbackKind = Literal["correct_driver", "wrong_driver", "not_material", "missed_cause"]
GatheringDepth = Literal["full", "probe_only"]


class FeedbackMark(Base):
    """One analyst or business-user mark against a closed case.

    `segment` is the dimension key the mark is *about* — learning is keyed
    "per driver per segment", not globally, so a driver right in the East does
    not make it right everywhere. Left empty for a mark with no segment scope:
    `not_material` is per-KPI, and `missed_cause` adds to the registry rather
    than judging a segment.
    """

    case_id: str
    kind: FeedbackKind
    kpi: str
    segment: dict[str, str] = Field(default_factory=dict)
    driver_id: str | None = None
    new_driver: Driver | None = None
    note: str = ""

    @model_validator(mode="after")
    def _kind_carries_what_it_needs(self) -> Self:
        if self.kind in ("correct_driver", "wrong_driver") and self.driver_id is None:
            raise ValueError(f"{self.kind} needs driver_id")
        if self.kind == "missed_cause" and self.new_driver is None:
            raise ValueError("missed_cause needs new_driver — the registry entry to add")
        return self


class LearningState(Base):
    """Everything Stage 9 has learned so far. One instance per KPI is typical;
    nothing here is scoped by case — it accumulates across every closed case
    for that KPI, which is the entire point of it being state.
    """

    driver_prior: dict[str, float] = Field(default_factory=dict)
    not_material_count: dict[str, int] = Field(default_factory=dict)


def _segment_key(segment: dict[str, str]) -> str:
    return ",".join(f"{k}={v}" for k, v in sorted(segment.items()))


def _prior_key(kpi: str, driver_id: str, segment: dict[str, str]) -> str:
    return f"{kpi}:{driver_id}:{_segment_key(segment)}"


CORRECT_STEP = 1.0
WRONG_STEP = -1.0
#: A driver nothing has been learned about yet gets full retrieval and
#: extraction — the depth choice is only ever a *cut* earned by being wrong
#: more than right, never the default.
PROBE_ONLY_THRESHOLD = -2.0


def apply(state: LearningState, mark: FeedbackMark) -> LearningState:
    """Fold one mark into the state. `missed_cause` touches the contract, not
    this state — see `promote()` — so it passes `state` through unchanged.
    """
    if mark.kind == "correct_driver":
        return _adjust_prior(state, mark, CORRECT_STEP)
    if mark.kind == "wrong_driver":
        return _adjust_prior(state, mark, WRONG_STEP)
    if mark.kind == "not_material":
        return _bump_not_material(state, mark)
    if mark.kind == "missed_cause":
        return state
    raise ValueError(f"unknown feedback kind {mark.kind!r}")  # pragma: no cover - unreachable


def _adjust_prior(state: LearningState, mark: FeedbackMark, step: float) -> LearningState:
    assert mark.driver_id is not None  # validated by FeedbackMark itself
    key = _prior_key(mark.kpi, mark.driver_id, mark.segment)
    updated = dict(state.driver_prior)
    updated[key] = updated.get(key, 0.0) + step
    return state.model_copy(update={"driver_prior": updated})


def _bump_not_material(state: LearningState, mark: FeedbackMark) -> LearningState:
    updated = dict(state.not_material_count)
    updated[mark.kpi] = updated.get(mark.kpi, 0) + 1
    return state.model_copy(update={"not_material_count": updated})


def driver_prior(state: LearningState, kpi: str, driver_id: str, segment: dict[str, str]) -> float:
    """0.0 for a driver nothing has been learned about yet."""
    return state.driver_prior.get(_prior_key(kpi, driver_id, segment), 0.0)


def gathering_depth(
    state: LearningState, kpi: str, driver_id: str, segment: dict[str, str]
) -> GatheringDepth:
    """Whether Stage 4 runs full retrieval + extraction (4b/4c) or stops at
    probes (4a) for this driver in this segment. Two uncontested
    `wrong_driver` marks are enough to stop paying for retrieval on a driver
    this segment has already ruled out; one `correct_driver` mark cancels one
    `wrong_driver`, so a driver that is right more often than not is never cut.
    """
    prior = driver_prior(state, kpi, driver_id, segment)
    return "probe_only" if prior <= PROBE_ONLY_THRESHOLD else "full"


def reorder(
    state: LearningState, kpi: str, hypotheses: list[Hypothesis], segment: dict[str, str]
) -> list[Hypothesis]:
    """Presentation order only — S3's own `priority` field is documented as
    "never gates what gets tested", and this respects that: nothing is added,
    removed, or excluded from testing, only the order a case lists them in,
    ranked by learned prior (highest first) with the enumerated `priority`
    breaking ties.
    """
    return sorted(
        hypotheses,
        key=lambda h: (-driver_prior(state, kpi, h.driver_id, segment), h.priority),
    )


NOT_MATERIAL_RELATIVE_STEP = 0.01
NOT_MATERIAL_ABSOLUTE_MULTIPLIER = 1.05
#: Bounds how far repeated "not material" marks can relax the gate — ten
#: marks is +10 percentage points of relative threshold and ×1.05¹⁰ ≈ ×1.63 of
#: absolute, after which further marks change nothing further.
NOT_MATERIAL_MAX_STEPS = 10


def adjusted_materiality(state: LearningState, kpi: str, base: Materiality) -> Materiality:
    """Relax the dual materiality gate for a KPI marked "not material"
    repeatedly — "fewer false alarms" (§02 architecture's Stage 9 table).
    Both halves of the gate move: `relative` by a fixed step per mark,
    `absolute` by a fixed multiplier per mark, each capped at
    `NOT_MATERIAL_MAX_STEPS` marks so no run of marks can silently turn the
    gate off. Unchanged (equal to `base`) when this KPI has no marks yet.
    """
    count = min(state.not_material_count.get(kpi, 0), NOT_MATERIAL_MAX_STEPS)
    relative = base.relative + NOT_MATERIAL_RELATIVE_STEP * count
    absolute = base.absolute * (NOT_MATERIAL_ABSOLUTE_MULTIPLIER**count)
    return base.model_copy(update={"relative": relative, "absolute": absolute})


def promote(contract: KPIContract, mark: FeedbackMark) -> KPIContract:
    """Add a `missed_cause` mark's driver to the registry — "the system can
    now investigate a cause it previously couldn't" (§02 architecture). Returns
    a new contract; `contract` itself is untouched.
    """
    if mark.kind != "missed_cause":
        raise ValueError(f"promote() only applies to a missed_cause mark, got {mark.kind!r}")
    assert mark.new_driver is not None  # validated by FeedbackMark itself
    if any(driver.id == mark.new_driver.id for driver in contract.drivers):
        raise ValueError(
            f"driver {mark.new_driver.id!r} is already in the registry — nothing to promote"
        )
    return contract.model_copy(update={"drivers": [*contract.drivers, mark.new_driver]})
