"""Stage 7 · Recommend — §15 S7, the brief's own seven fields.

*"The to-do list, with a name on it. A finding nobody owns is a sentence,
not a decision."*

`driver → controllable lever → action → expected impact → owner → confidence
→ monitoring plan`. Every field is a contract lookup or arithmetic; none is
model-generated.

**Only a `primary` attribution earns a recommendation.** `Verdict`'s own
validator (`_ranking_is_coherent`, models.py) ties `primary` to confidence:
exactly one exists when confidence is Confirmed or Likely, and none exists
otherwise. So "no recommendation below Likely" is the whole rule — Contested
and Undetermined already have their own actionable next step, Stage 6's
discriminating question, and recommending a specific lever against a driver
the case itself says it cannot separate from its rivals would be exactly the
overclaiming §9 exists to prevent. `recommend()` returns `None` there, and
`Case.recommendation` stays `None`.

**A driver with no lever also returns `None`.** `Driver.lever` is `Lever |
None` "where nothing is controllable" (models.py) — a live possibility for
any driver, not only seasonality's canonical example.

**`expected_impact`** is `|tree.total_delta| × lever.save_rate` — the whole
movement at risk, not the footprint's own slice (that is what Stage 6's
`OpenQuestion.value_at_stake` uses instead) — times the lever's declared
recoverable band. A measured number times a stated assumption; the
`tuple[float, float]` shape carries that label structurally, so nothing here
reads as a point estimate. `docs/DECISIONS.md` has the arithmetic check
against the golden fixture that pins this to `total_delta`, not
`footprint.delta`.

**`monitoring`** reuses two fields nothing else in this stage touches:
`contract.refresh.cadence` (how often the data behind this KPI moves at all)
and `contract.materiality.min_persistence` — the same "how many periods"
number Stage 1 uses to call a movement real, reused here as "how many
periods to wait before escalating": the same question, asked at the other
end of the case.
"""

from __future__ import annotations

from casefile.models import ContributionTree, KPIContract, Recommendation, Verdict

#: One sentence per lever action — the full, closed set across every current
#: contract (verified: `grep -oh "action: [a-z_]*" contracts/*.yaml | sort -u`).
#: A lever action outside this set is a registry addition nobody has agreed
#: on yet (§30 rule 1 territory), not something to paper over with generic
#: text — `recommend()` raises rather than guessing at a sentence.
_ACTION_TEXT: dict[str, str] = {
    "prioritise_integration_fix": "Prioritise the integration fix for {accounts}.",
    "pricing_review": "Review pricing for {accounts}.",
    "competitive_desk_review": "Run a competitive desk review for {accounts}.",
    "fulfilment_escalation": "Escalate fulfilment for {accounts}.",
}


class RecommendError(ValueError):
    pass


def recommend(
    contract: KPIContract,
    verdict: Verdict,
    tree: ContributionTree,
    dimensions: dict[str, str],
) -> Recommendation | None:
    """`None` when there is nothing to recommend: no primary driver
    (Contested, Undetermined), or a primary driver nothing is controllable
    about."""
    primary = next((a for a in verdict.attribution if a.status == "primary"), None)
    if primary is None:
        return None
    drivers = {d.id: d for d in contract.drivers}
    driver = drivers.get(primary.driver_id)
    if driver is None or driver.lever is None:
        return None
    lever = driver.lever
    if lever.action not in _ACTION_TEXT:
        raise RecommendError(f"no action text for lever {lever.action!r} — add one")

    accounts = ", ".join(tree.footprint.entities.get("account_id", [])) or "the footprint"
    value_at_risk = abs(tree.total_delta)
    low, high = lever.save_rate
    return Recommendation(
        driver_id=primary.driver_id,
        lever=lever.action,
        action=_ACTION_TEXT[lever.action].format(accounts=accounts),
        expected_impact=(value_at_risk * low, value_at_risk * high),
        owner_role=lever.owner_role,
        confidence=verdict.confidence,
        monitoring=_monitoring(contract, dimensions),
    )


def _monitoring(contract: KPIContract, dimensions: dict[str, str]) -> str:
    scope = ", ".join(dimensions.values())
    scope_part = f"{contract.id}, {scope}" if scope else contract.id
    cycles = contract.materiality.min_persistence
    return (
        f"{scope_part}, {contract.refresh.cadence}; "
        f"escalate if not recovered within {cycles} cycles"
    )
