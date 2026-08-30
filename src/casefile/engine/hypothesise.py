"""Stage 3 · Hypothesise — §15 S3, LLM #1.

*"Drawing up the suspect list. The registry names the suspects; the model
writes the brief on each and may flag one the registry doesn't know. It can
add a note to the file — it can never decide who gets investigated."*

**Enumeration is deterministic.** Every driver on the contract becomes a
hypothesis, always (`_enumerate`) — the tested set is a function of the
contract, never at the mercy of a model omission.

**Annotation is the one LLM call.** It writes a rationale, a priority (display
order only) and an expected signature per hypothesis, and may add exactly one
further hypothesis flagged `unmodelled`.

Both guardrails are enforced here, in code, never merely requested in the
prompt: a response that skips a driver gets it filled in with a placeholder
annotation; a response that names anything other than a known driver id gets
folded into a single `unmodelled` entry. The model's *content* can vary call
to call — its *set of driver ids* cannot, which is what makes B3's "identical
across runs" a property of this function rather than of the model's mood.
"""

from __future__ import annotations

from pydantic import BaseModel

from casefile.llm.base import LLMProvider, Prompt
from casefile.models import Footprint, Hypothesis, KPIContract, Signature, Trigger, Usage

UNMODELLED = "unmodelled"


class HypothesiseResponse(BaseModel):
    """The shape of LLM #1's one call. No numeric field but `Hypothesis.priority`
    — and that one is display order only (§15 S3), never an input to Stage 5's
    tests or Stage 6's rubric."""

    hypotheses: list[Hypothesis]


def hypothesise(
    contract: KPIContract, trigger: Trigger, footprint: Footprint, provider: LLMProvider
) -> tuple[list[Hypothesis], Usage]:
    """The registry enumeration, annotated by the model, guardrailed by code."""
    driver_ids = _enumerate(contract)
    prompt = _prompt(contract, trigger, footprint, driver_ids)
    response, usage = provider.complete(prompt, HypothesiseResponse)
    hypotheses = _guardrail(response.hypotheses, driver_ids)
    return hypotheses, usage


def _enumerate(contract: KPIContract) -> list[str]:
    """Every registry driver, in the contract's own order — deterministic and
    total. §15: 'always', not 'when the evidence looks promising'."""
    return [driver.id for driver in contract.drivers]


def _prompt(
    contract: KPIContract, trigger: Trigger, footprint: Footprint, driver_ids: list[str]
) -> Prompt:
    system = (
        "You are annotating a fixed list of candidate causes for a business KPI "
        "movement. You do not choose which causes are tested — the list below is "
        "final. For each candidate, write a one-sentence rationale and a "
        "qualitative prediction of what four tests (timing, locality, dose, "
        "control) would find if it is the true cause: describe direction and "
        "shape only. Never write a number, a rupee amount, a percentage or a "
        "date in any field — those are computed later, not written by you. You "
        "may add exactly one further hypothesis with driver_id 'unmodelled' if "
        "the movement plausibly has no cause on this list. Invent no other "
        "driver_id."
    )
    entities = ", ".join(f"{dim}={ids}" for dim, ids in footprint.entities.items())
    listed = "\n".join(f"- {driver_id}" for driver_id in driver_ids)
    user = (
        f"KPI: {contract.id} ({contract.label})\n"
        f"Period: {trigger.period}\n"
        f"Footprint: {entities}, {footprint.window_start} to {footprint.window_end}\n\n"
        f"Candidate causes:\n{listed}\n\n"
        "Return one Hypothesis per candidate cause above, in the same order, "
        "plus optionally one more with driver_id='unmodelled'."
    )
    return Prompt(stage="s3", system=system, user=user)


def _guardrail(raw: list[Hypothesis], driver_ids: list[str]) -> list[Hypothesis]:
    """Two rules, enforced regardless of what the model returned:

    * every enumerated driver id appears exactly once, in enumeration order
    * anything the model invented besides a known driver id is folded into a
      single 'unmodelled' hypothesis — never silently dropped, and never
      trusted as a phantom driver the rest of the pipeline would have to
      recognise
    """
    known = set(driver_ids)
    by_driver: dict[str, Hypothesis] = {}
    unmodelled: Hypothesis | None = None

    for item in raw:
        if item.driver_id in known:
            by_driver.setdefault(item.driver_id, item)  # first annotation wins
        elif unmodelled is None:
            unmodelled = (
                item
                if item.driver_id == UNMODELLED
                else item.model_copy(update={"driver_id": UNMODELLED})
            )
        # a second off-registry suggestion is dropped — "exactly one"

    out = [
        by_driver.get(driver_id) or _default(driver_id, priority)
        for priority, driver_id in enumerate(driver_ids, start=1)
    ]
    if unmodelled is not None:
        out.append(unmodelled)
    return out


def _default(driver_id: str, priority: int) -> Hypothesis:
    """A driver the model's response skipped. §15: 'it cannot remove or skip
    an enumerated hypothesis' — enforced here, not requested in the prompt."""
    return Hypothesis(
        driver_id=driver_id,
        rationale="no annotation returned for this registry driver",
        priority=priority,
        expected_signature=Signature(),
    )
