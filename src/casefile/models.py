"""The treaty — §30.

Nothing crosses a track boundary except the objects in this file:

    A ──────────────────▶ B ──────────────────▶ C
    VerificationResult    Case (complete)       Rendered narrative
    ContributionTree      + Verdict             + entitlement applied
    Footprint             + Recommendation      + UI

Four rules govern it (§30). Two are enforced here rather than remembered:

* **Rule 1 — a schema change needs all three of us in the same sitting.** If you
  need a field that is not here, do not add it on your branch: subclass locally
  and raise it at the next sync (§46.3).
* **Rule 4 — no stage mutates another stage's ledger entries.** `Source` and
  `EvidenceItem` are frozen. (Pydantic blocks reassignment, not in-place list
  mutation; treat `supports` and `contradicts` as read-once anyway.)

Every model forbids unknown keys. The two fixtures in `fixtures/` are written by
hand, and a silently-dropped typo there would poison every track at once.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FrozenBase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# ── Vocabulary ────────────────────────────────────────────────────────────────
# Import these rather than retyping the literals; a stage that invents its own
# spelling of "checked_absent" is a bug nobody notices until adjudication.

ProbeOutcome = Literal["found", "checked_absent", "uncheckable"]
EvidenceKind = Literal["fact", "statistic", "document", "absence"]
Method = Literal["sql", "contribution", "stat_test", "did", "retrieval", "llm_extraction"]
TestOutcome = Literal["pass", "refute", "inconclusive"]
AttributionStatus = Literal["primary", "minor", "eliminated", "unresolved"]
Confidence = Literal["confirmed", "likely", "contested", "undetermined"]
DriverType = Literal["internal_controllable", "external", "external_uncontrollable"]
Direction = Literal["up_is_good", "down_is_good"]
CheckName = Literal["freshness", "completeness", "definition_drift", "artefact", "materiality"]


# ── The KPI semantic contract — §14.1 ─────────────────────────────────────────
# The shape only. Track A owns the YAML loader and the validator (contract.py,
# ladder step 0.6); this is what B reads `drivers` from and C reads `access` from.


class RefreshSpec(Base):
    source: str
    cadence: str
    sla_hours: float


class Epoch(Base):
    """One era of the metric's definition. Verify recomputes boundary periods
    under adjacent epochs to separate definition drift from business change."""

    effective_from: date
    formula: str


class CompositionEdge(Base):
    """A cross-KPI edge. Enables the cross-KPI attribution in Stage 2."""

    kpi: str
    weight: str
    transform: str


class Materiality(Base):
    relative: float
    absolute: float
    min_persistence: int
    z_threshold: float


class DataQuality(Base):
    max_single_record_share: float
    min_completeness: float


class Lever(Base):
    """The controllable action a driver maps to.

    `save_rate` is the declared recoverable band. Stage 7 multiplies it by the
    value at risk and labels the result an assumption — it is not a measurement,
    and the case says so.
    """

    action: str
    owner_role: str
    lag_days: int
    save_rate: tuple[float, float]


class Driver(Base):
    id: str
    type: DriverType
    evidence_sources: list[str]
    max_lag_days: int
    probe_sql: str | None = None
    lever: Lever | None = None  # null where nothing is controllable, e.g. seasonality


class Lineage(Base):
    upstream: list[str] = Field(default_factory=list)
    joins: list[str] = Field(default_factory=list)
    downstream: list[str] = Field(default_factory=list)


class AccessRules(Base):
    """Row / column / domain entitlement, applied to the `Case` object at S8a —
    before narration, never after."""

    row: dict[str, dict[str, list[str]]] = Field(default_factory=dict)
    column: dict[str, list[str]] = Field(default_factory=dict)
    domain: dict[str, dict[str, list[str]]] = Field(default_factory=dict)
    masking: dict[str, str] = Field(default_factory=dict)


class KPIContract(Base):
    id: str
    label: str
    owner_role: str

    definition: str
    unit: str
    direction: Direction
    grain: list[str]
    calendar: str

    formula: str
    filters: list[str] = Field(default_factory=list)
    refresh: RefreshSpec

    epochs: list[Epoch] = Field(default_factory=list)
    composition: list[CompositionEdge] = Field(default_factory=list)
    decomposition_dims: list[str]

    materiality: Materiality
    data_quality: DataQuality
    drivers: list[Driver]
    lineage: Lineage
    access: AccessRules

    history_start: date
    seasonal_period_days: int


# ── Stage 1 · Verify ──────────────────────────────────────────────────────────


class Trigger(Base):
    kpi: str
    period: str
    dimensions: dict[str, str] = Field(default_factory=dict)
    delta: float
    delta_relative: float


class VerificationCheck(Base):
    name: CheckName
    passed: bool
    detail: str
    statistic: float | None = None


class VerificationResult(Base):
    """`passed is False` closes the case here, with zero model calls — scenarios
    D and E. `baseline == "borrowed"` and a stale source both cap confidence."""

    passed: bool
    checks: list[VerificationCheck]
    freshness_hours: float
    baseline: Literal["own", "borrowed"] = "own"
    confidence_ceiling: Confidence | None = None
    provisional: bool = False
    robust_z: float | None = None
    persistence: int | None = None


# ── Stage 2 · Decompose ───────────────────────────────────────────────────────


class Footprint(Base):
    """The entity set and window that scope everything downstream: which
    hypotheses are enumerated, what retrieval may see, what the four tests
    compare against."""

    entities: dict[str, list[str]]
    window_start: date
    window_end: date
    delta: float


class PVM(Base):
    price: float
    volume: float
    mix: float


class ContributionNode(Base):
    dimension: str
    key: str
    delta: float
    share: float
    children: list[ContributionNode] = Field(default_factory=list)


class ContributionTree(Base):
    kpi: str
    period: str
    total_delta: float
    by_dimension: dict[str, list[ContributionNode]]
    footprint: Footprint
    pvm: PVM | None = None
    hhi: float | None = None

    def concentration(self, k: int, dimension: str = "account") -> float:
        """K(k) = Σ_top-k |Δ_i| / Σ_i |Δ_i| — §23.

        The "88% sits in two accounts" number. Computed, never stored, so it
        cannot drift away from the deltas it summarises.
        """
        magnitudes = sorted((abs(n.delta) for n in self.by_dimension[dimension]), reverse=True)
        total = sum(magnitudes)
        if total == 0:
            return 0.0
        return sum(magnitudes[:k]) / total


# ── Stage 3 · Hypothesise ─────────────────────────────────────────────────────


class Signature(Base):
    """What this hypothesis predicts each challenge test should find. Written by
    the model; it constrains nothing — Stage 5 runs the tests regardless."""

    timing: str | None = None
    locality: str | None = None
    dose: str | None = None
    control: str | None = None


class Hypothesis(Base):
    driver_id: str  # a registry driver id, or "unmodelled"
    rationale: str
    priority: int  # presentation order only — never gates what gets tested
    expected_signature: Signature


# ── Stage 4 · Evidence ────────────────────────────────────────────────────────


class Source(FrozenBase):
    system: str
    record_id: str
    timestamp: datetime
    url: str | None = None


class EvidenceItem(FrozenBase):
    """One item in the append-only ledger. Nothing reaches a narrative unless it
    came out of here.

    `outcome` is the load-bearing field. **checked_absent** means we looked and
    counted — "0 of 12 populated lost-reason fields name a competitor" — and it
    *refutes*. **uncheckable** means the source has no coverage of this footprint
    and it *abstains*, capping confidence. Evidence of absence is not absence of
    evidence, and the validator below is what stops the two collapsing into each
    other the first time someone is in a hurry.
    """

    id: str
    claim: str
    kind: EvidenceKind
    outcome: ProbeOutcome
    source: Source
    method: Method
    supports: list[str] = Field(default_factory=list)
    contradicts: list[str] = Field(default_factory=list)
    strength: float = Field(ge=0.0, le=1.0)
    freshness_hours: float
    denominator: int | None = None
    coverage: float | None = None

    @model_validator(mode="after")
    def _absence_is_counted(self) -> Self:
        if self.outcome == "checked_absent" and self.denominator is None:
            raise ValueError(
                f"evidence {self.id}: checked_absent needs a denominator — "
                "an absence without a count is an assertion, not evidence"
            )
        if self.outcome == "uncheckable" and self.coverage is None:
            raise ValueError(
                f"evidence {self.id}: uncheckable needs a coverage figure — "
                "it is the number that distinguishes it from checked_absent"
            )
        return self


# ── Stage 5 · Challenge ───────────────────────────────────────────────────────


class TestResult(Base):
    outcome: TestOutcome
    detail: str
    statistic: float | None = None
    evidence_ids: list[str] = Field(default_factory=list)


class TestMatrix(Base):
    timing: TestResult
    locality: TestResult
    dose: TestResult
    control: TestResult


# ── Stage 6 · Adjudicate ──────────────────────────────────────────────────────


class Attribution(Base):
    """One driver's place in the ranking.

    A hypothesis eliminated as the *primary* explanation keeps its measured
    share: "pricing cannot explain the concentrated movement" and "pricing cost
    ₹0.2 Cr" are both true, and the case says both.
    """

    driver_id: str
    share: float | None
    status: AttributionStatus
    eliminated_by: str | None = None  # the test that killed it


class Verdict(Base):
    attribution: list[Attribution]
    confidence: Confidence

    @model_validator(mode="after")
    def _ranking_is_coherent(self) -> Self:
        for item in self.attribution:
            if item.status == "eliminated" and item.eliminated_by is None:
                raise ValueError(
                    f"{item.driver_id} is eliminated but names no test — "
                    "an elimination nobody can trace is an opinion"
                )
        primaries = [a.driver_id for a in self.attribution if a.status == "primary"]
        if len(primaries) > 1:
            raise ValueError(f"the verdict ranks, it does not crown: {primaries}")
        if not primaries and self.confidence in ("confirmed", "likely"):
            raise ValueError(f"confidence {self.confidence!r} needs a primary driver")
        return self


class OpenQuestion(Base):
    """The single missing fact that would most change the verdict, its owner, and
    what resolving it is worth."""

    question: str
    owner_role: str
    value_at_stake: float
    hypotheses_separated: list[str] = Field(default_factory=list)


# ── Stage 7 · Recommend ───────────────────────────────────────────────────────


class Recommendation(Base):
    """Exactly the shape the brief asks for: driver → lever → action → expected
    impact → owner → confidence → monitoring. Every field is a contract lookup or
    arithmetic; none is model-generated.

    `expected_impact` is value at risk × the lever's `save_rate` band, which is a
    measured number times a stated assumption.
    """

    driver_id: str
    lever: str
    action: str
    expected_impact: tuple[float, float]
    owner_role: str
    confidence: Confidence
    monitoring: str


# ── Stage 10 · Telemetry ──────────────────────────────────────────────────────


class Usage(Base):
    stage: str
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: float
    cost_inr: float
    cache_hit: bool = False


class StageTiming(Base):
    stage: str
    wall_ms: float
    used_model: bool = False


class Telemetry(Base):
    """The receipt. Every figure below is derived from the records, not stored
    alongside them — which is what makes "the model never produced a number" a
    measurement rather than a claim.
    """

    calls: list[Usage] = Field(default_factory=list)
    stages: list[StageTiming] = Field(default_factory=list)

    @property
    def model_calls(self) -> int:
        return len(self.calls)

    @property
    def total_cost_inr(self) -> float:
        return sum(call.cost_inr for call in self.calls)

    @property
    def total_latency_s(self) -> float:
        return sum(stage.wall_ms for stage in self.stages) / 1000.0

    @property
    def share_of_stages_without_model(self) -> float:
        if not self.stages:
            return 0.0
        return sum(1 for stage in self.stages if not stage.used_model) / len(self.stages)


# ── The case ──────────────────────────────────────────────────────────────────


class Case(Base):
    """One investigation, start to finish.

    Most fields are optional because a case that fails Verify closes there, with
    no decomposition, no hypotheses and no verdict — and closing early is a
    success path, not a degraded one.
    """

    id: str
    trigger: Trigger
    verification: VerificationResult
    decomposition: ContributionTree | None = None
    hypotheses: list[Hypothesis] = Field(default_factory=list)
    ledger: list[EvidenceItem] = Field(default_factory=list)
    tests: dict[str, TestMatrix] = Field(default_factory=dict)  # keyed by driver_id
    verdict: Verdict | None = None
    recommendation: Recommendation | None = None
    open_question: OpenQuestion | None = None
    priority: float  # |Δ at stake| × confidence weight — orders the case list
    telemetry: Telemetry

    @model_validator(mode="after")
    def _abstention_carries_its_question(self) -> Self:
        if (
            self.verdict is not None
            and self.verdict.confidence == "undetermined"
            and self.open_question is None
        ):
            raise ValueError(
                f"case {self.id}: Undetermined without a discriminating question — "
                "abstention ships with the question that would settle it, or it is "
                "just a shrug"
            )
        return self


# ── Personas ──────────────────────────────────────────────────────────────────


class Persona(Base):
    """Track C populates these from `personas/*.yaml`. Deliberately minimal here:
    the treaty needs the shape, not C's rendering preferences.

    `region` is the one addition P1 forced, and it is not a preference. §14.1
    writes `access.row.region.vp_sales: [own_region]`, and *own* is a fact about
    the viewer that lives nowhere else — without it S8a cannot resolve the rule
    at all, and a region-scoped persona either sees everything or nothing.
    Optional and defaulted, so no fixture moves. §30 rule 1 wants all three of us
    in one sitting for this; nobody else is reachable, so it lands with a
    `DECISIONS.md` entry and goes on the G1 agenda.
    """

    id: str
    role_key: str
    label: str
    region: str | None = None


ContributionNode.model_rebuild()
