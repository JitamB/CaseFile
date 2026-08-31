"""Stage 6 · Adjudicate — §15 S6, §9's four verdicts.

*"The verdict, scored against a fixed rulebook — not a model's opinion, so the
same evidence always gives the same answer. And when the answer is 'we can't
tell,' it works out the single question that would settle it."*

Rules, not judgement:

* **Confirmed** — a hypothesis with ≥2 tests passing (Timing or Locality among
  them), Control passing, and nothing inconclusive. This is what makes
  Confirmed structurally unreachable at n<5 accounts without a special case
  anywhere: Dose cannot *pass* below `stats/correlation.py`'s own `MIN_PAIRS`,
  so it is always `inconclusive` there, and `inconclusive` anywhere disqualifies
  Confirmed by this same rule.
* **Likely** — the same ≥2-tests-including-Timing-or-Locality bar, met, but
  short of Confirmed's stricter one (something inconclusive, or Control not
  passing). A hypothesis refuted by *any* test never reaches either tier.
* **Contested** — more than one hypothesis reaches Likely or better in the
  same case. Nothing separates them.
* **Undetermined** — no hypothesis reaches Likely. This can happen two ways,
  and the attribution says which: a hypothesis **eliminated** by a refuting
  test, or a hypothesis **unresolved** because nothing refuted it either —
  the evidence had no coverage to check it with at all (§25 B's "the sources
  cannot see it"). An `unmodelled` hypothesis in play also forces this,
  regardless of what the four tests found on the registry drivers — the
  model flagged a cause outside the contract, and the rubric will not paper
  over that with a confident answer about a *different* cause.

**Ceilings apply after scoring and only ever lower** (§9): today `verify.py`
only ever hands back `"likely"` or `None`, so the one thing a ceiling ever
does is stop a Confirmed verdict from standing on a stale or borrowed
baseline. It never raises a case, and it never touches Contested or
Undetermined — those are not overconfidence, so there is nothing to cap.

**Attribution.share** is left `None` for every status except the survivor(s)
— `primary` (a clean single winner) or `unresolved` (Contested's ties, whose
footprints coincide with the movement by hypothesis, same as the primary's).
A refuted hypothesis's cause footprint does not slice into the same movement
a second time; the one exception is a hypothesis whose *entire* mechanism is
a price change (§23's PVM already isolates that component on its own, for
free, on any KPI billed at a quantity and a price) — there, `share` is
`PVM.price / total_delta`, a real, separately-measured number, not a
re-slice of the account-level movement the survivor already explains.
`docs/DECISIONS.md` has the reasoning for not attempting this generally.

**The discriminating question** targets the hypothesis at the front of the
ranking — the primary if there is one, the earliest unresolved otherwise —
and names its first inconclusive test in `timing, locality, dose, control`
order, or the evidence gap itself when nothing about it is even inconclusive,
just uncovered. `None` only when confidence is Confirmed: nothing is left
worth asking.
"""

from __future__ import annotations

from pathlib import Path

from casefile.models import (
    Attribution,
    AttributionStatus,
    Confidence,
    ContributionTree,
    Driver,
    EvidenceItem,
    Hypothesis,
    KPIContract,
    OpenQuestion,
    TestMatrix,
    Verdict,
    VerificationResult,
)

#: §9's per-tier weight on `|Δ at stake|` for `Case.priority`. Only "likely"
#: is stated anywhere (the golden fixture: 16.8M / 21M footprint delta =
#: 0.8, exactly); the rest are this module's own, logged in DECISIONS.md —
#: monotone with confidence, and Undetermined stays well above zero so an
#: unexplained movement never falls off the bottom of a priority-ordered list.
CONFIDENCE_WEIGHT: dict[Confidence, float] = {
    "confirmed": 1.0,
    "likely": 0.8,
    "contested": 0.6,
    "undetermined": 0.4,
}

#: Order tests are checked in, throughout this module — which one gets named
#: as `eliminated_by`, and which one the discriminating question is about.
_TEST_ORDER = ("timing", "locality", "dose", "control")

_STATUS_RANK: dict[AttributionStatus, int] = {
    "primary": 0, "unresolved": 1, "minor": 2, "eliminated": 3,
}


class AdjudicateError(ValueError):
    pass


def adjudicate(
    contract: KPIContract,
    hypotheses: list[Hypothesis],
    tree: ContributionTree,
    ledger: list[EvidenceItem],
    matrices: dict[str, TestMatrix],
    verification: VerificationResult,
) -> tuple[Verdict, OpenQuestion | None, float]:
    """The rubric, over Stage 5's test matrices and Stage 4's ledger. Returns
    the verdict, the discriminating question (`None` only when Confirmed),
    and `Case.priority`."""
    if not matrices:
        raise AdjudicateError("nothing was challenged; adjudicate has nothing to rank")

    drivers = {d.id: d for d in contract.drivers}
    tiers = {driver_id: _tier(matrix) for driver_id, matrix in matrices.items()}
    refuted_by = {driver_id: _first_refuting_test(matrix) for driver_id, matrix in matrices.items()}

    confidence = _case_confidence(tiers)
    if any(h.driver_id == "unmodelled" for h in hypotheses):
        confidence = "undetermined"
    confidence = _apply_ceiling(confidence, verification.confidence_ceiling)

    attribution = [
        _attribution(
            driver_id, tiers[driver_id], refuted_by[driver_id], confidence,
            ledger, drivers.get(driver_id), tree,
        )
        for driver_id in matrices
    ]
    attribution.sort(key=lambda a: (_STATUS_RANK[a.status], -(a.share or 0.0)))

    verdict = Verdict(attribution=attribution, confidence=confidence)
    open_question = None if confidence == "confirmed" else _open_question(
        attribution, matrices, drivers, contract, tree
    )
    priority = abs(tree.total_delta) * CONFIDENCE_WEIGHT[confidence]
    return verdict, open_question, priority


# ── Per-hypothesis tier ──────────────────────────────────────────────────────


def _tier(matrix: TestMatrix) -> Confidence | None:
    """`None` means "does not survive" — refuted outright, or never reached
    the bar to begin with. Never `"undetermined"`/`"contested"`: those are
    case-level conclusions, not something one hypothesis can be."""
    outcomes = {name: getattr(matrix, name).outcome for name in _TEST_ORDER}
    if "refute" in outcomes.values():
        return None
    passes = {name for name, outcome in outcomes.items() if outcome == "pass"}
    if len(passes) < 2 or not ({"timing", "locality"} & passes):
        return None
    if outcomes["control"] == "pass" and "inconclusive" not in outcomes.values():
        return "confirmed"
    return "likely"


def _first_refuting_test(matrix: TestMatrix) -> str | None:
    return next((name for name in _TEST_ORDER if getattr(matrix, name).outcome == "refute"), None)


def _case_confidence(tiers: dict[str, Confidence | None]) -> Confidence:
    survivors = [tier for tier in tiers.values() if tier is not None]
    if not survivors:
        return "undetermined"
    if len(survivors) == 1:
        return survivors[0]
    return "contested"


def _apply_ceiling(confidence: Confidence, ceiling: Confidence | None) -> Confidence:
    """Only ever lowers, and today only one ceiling value is ever produced
    (`verify.py`'s stale-source/borrowed-baseline path hands back "likely" or
    nothing) — so the only thing this can do is stop Confirmed from standing
    on data that should not carry that much weight. Contested and
    Undetermined are not overconfidence; nothing here touches them."""
    if ceiling == "likely" and confidence == "confirmed":
        return "likely"
    return confidence


# ── Attribution ──────────────────────────────────────────────────────────────


def _has_found_support(ledger: list[EvidenceItem], driver_id: str) -> bool:
    """Real, independent evidence for this specific driver — not Control's.
    Control (`method="did"`) is computed once and shared across every
    hypothesis in the same `challenge()` call; its "found" item would
    otherwise support every driver equally and make minor-vs-eliminated
    undiscriminating for all of them at once."""
    return any(
        driver_id in item.supports and item.outcome == "found" and item.method != "did"
        for item in ledger
    )


def _status(
    tier: Confidence | None, refuted_by: str | None, has_support: bool, confidence: Confidence,
) -> AttributionStatus:
    if tier is not None:
        return "unresolved" if confidence == "contested" else "primary"
    if has_support:
        # A real, independently-found effect somewhere — "pricing cannot
        # explain the concentrated movement" and "pricing cost ₹0.2 Cr" are
        # both true, and this is what keeps both true even when a test also
        # refuted it as the *primary* explanation.
        return "minor"
    if refuted_by is not None:
        return "eliminated"
    return "unresolved"


def _share(
    status: AttributionStatus, driver: Driver | None, tree: ContributionTree
) -> float | None:
    if status in ("primary", "unresolved") and tree.total_delta:
        return tree.footprint.delta / tree.total_delta
    pvm = tree.pvm
    has_probe = driver is not None and driver.probe_sql is not None
    if status == "minor" and pvm is not None and driver is not None and has_probe:
        assert driver.probe_sql is not None
        if Path(driver.probe_sql).stem == "price_delta" and tree.total_delta:
            return pvm.price / tree.total_delta
    return None


def _attribution(
    driver_id: str,
    tier: Confidence | None,
    refuted_by: str | None,
    confidence: Confidence,
    ledger: list[EvidenceItem],
    driver: Driver | None,
    tree: ContributionTree,
) -> Attribution:
    has_support = _has_found_support(ledger, driver_id)
    status = _status(tier, refuted_by, has_support, confidence)
    return Attribution(
        driver_id=driver_id,
        share=_share(status, driver, tree),
        status=status,
        eliminated_by=refuted_by if status == "eliminated" else None,
    )


# ── The discriminating question ──────────────────────────────────────────────


def _open_question(
    attribution: list[Attribution],
    matrices: dict[str, TestMatrix],
    drivers: dict[str, Driver],
    contract: KPIContract,
    tree: ContributionTree,
) -> OpenQuestion:
    target = attribution[0]  # already ranked: primary, else the earliest unresolved
    driver = drivers.get(target.driver_id)
    owner = (
        driver.lever.owner_role
        if driver is not None and driver.lever is not None
        else contract.owner_role
    )
    accounts = ", ".join(tree.footprint.entities.get("account_id", [])) or "the footprint"
    label = target.driver_id.replace("_", " ")

    matrix = matrices.get(target.driver_id)
    inconclusive_test = None
    if matrix is not None:
        inconclusive_test = next(
            (name for name in _TEST_ORDER if getattr(matrix, name).outcome == "inconclusive"), None
        )

    if inconclusive_test is not None:
        question = (
            f"Did {label} actually influence the outcome for {accounts}? "
            "Ask the account owner(s)."
        )
    else:
        question = (
            f"What actually happened to {accounts}? The available sources "
            f"have no coverage of {label}."
        )

    return OpenQuestion(
        question=question,
        owner_role=owner,
        value_at_stake=abs(tree.footprint.delta),
        hypotheses_separated=[target.driver_id],
    )
