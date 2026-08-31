"""Stage 8b · Narrate — §15 S8b, LLM #3, the last model touchpoint.

*"The same facts, written for different readers — genuinely different pages,
not one paragraph at two lengths."*

Runs **after** `entitle.py`, over the already-filtered `Case` (§17: "before
narration, never after") — a restricted account name is already hashed and a
restricted amount is already scrubbed to `"[amount restricted]"` in every
prose field the case carries by the time this module ever sees it. What this
module still has to guard against is the number entitlement's own field-level
banding cannot reach: `Case`'s numeric fields (`trigger.delta`, `priority`,
`recommendation.expected_impact`, ...) stay exact floats in the typed object
— entitle.py's own docstring says why: *"trigger.delta is a float and cannot
hold '₹1-5 Cr'"* — so a persona whose `amount_net` is restricted still needs
those figures **banded**, and this module is what actually renders them into
text a viewer reads.

**How "the model never produces a number" stays a fact and not a hope.**
§17 says "nothing downstream ever parses free text" — extracting numbers back
out of prose to check them would be exactly that. Instead the model is handed
a fixed menu of named tokens (`{delta}`, `{confidence}`, `{action}`, ...) —
each one a string this module computed and formatted, banded already if this
persona's `amount_net` is restricted — and told to write around them, never
inside them. The guardrail is then a single check per section: strip every
recognised `{token}` and `[ev-XXX]` citation out of the model's text; if a
digit survives, the model wrote one itself, and that section is discarded for
a plain, fully-templated sentence built from the same tokens instead. A model
that stays inside the menu produces the genuinely differentiated page §11
asks for; a model that does not still produces a safe one.

**Citations are checked, not merely requested.** Every `[ev-XXX]` token the
model writes is verified against `case.ledger`'s real ids — an invented one
fails the same way a stray digit does. "Every sentence cites a ledger id" is
asked for in the prompt but not mechanically enforced per sentence, which
would need real sentence segmentation to do without false positives; this is
a stated simplification, not a hidden one.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict

from casefile.engine.entitle import band
from casefile.llm.base import LLMProvider, Prompt
from casefile.models import Case, KPIContract, Persona, Usage

_CRORE = 10_000_000.0

_SECTIONS = ("headline", "explanation", "action", "outstanding")

_TOKEN = re.compile(r"\{([a-z_]+)\}")
_CITATION = re.compile(r"\[(ev-[\w-]+)\]")


class NarrationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    headline: str
    explanation: str
    action: str
    outstanding: str


class Narration(BaseModel):
    """The rendered page for one persona. Not a treaty type (§30) — nothing
    outside Track C's own rendering reads this; the treaty stops at `Case`."""

    model_config = ConfigDict(extra="forbid")

    persona_id: str
    headline: str
    explanation: str
    action: str
    outstanding: str


def narrate(
    case: Case, persona: Persona, contract: KPIContract, provider: LLMProvider
) -> tuple[Narration, Usage]:
    """Renders one persona's page over an already-entitled `case`. Calling
    this on a case `entitle()` has not yet filtered would narrate the
    unfiltered facts — the caller's job, per §17, is to entitle first."""
    tokens = _tokens(case, persona, contract)
    prompt = _prompt(case, persona, tokens)
    response, usage = provider.complete(prompt, NarrationResponse)

    sections = {
        name: _guardrail(name, getattr(response, name), tokens, case)
        for name in _SECTIONS
    }
    return Narration(persona_id=persona.id, **sections), usage


# ── Tokens — every fact the model is allowed to reference ──────────────────


def _tokens(case: Case, persona: Persona, contract: KPIContract) -> dict[str, str]:
    restricted = persona.role_key not in contract.access.column.get("amount_net", [])

    def money(v: float | None) -> str | None:
        if v is None:
            return None
        return band(v) if restricted else _crore(v)

    tokens: dict[str, str] = {
        "kpi": _label(case.trigger.kpi),
        "period": case.trigger.period,
        "dimensions": ", ".join(case.trigger.dimensions.values()) or "the whole business",
        "delta_pct": _percent(case.trigger.delta_relative),
        "priority": money(case.priority) or "",
    }
    delta = money(case.trigger.delta)
    if delta is not None:
        tokens["delta"] = delta

    if case.verdict is not None:
        tokens["confidence"] = case.verdict.confidence.capitalize()
        primary = next((a for a in case.verdict.attribution if a.status == "primary"), None)
        if primary is not None:
            tokens["primary_driver"] = primary.driver_id.replace("_", " ")
            if primary.share is not None:
                tokens["primary_share"] = _share(primary.share)

    if case.recommendation is not None:
        tokens["action"] = case.recommendation.action
        tokens["owner"] = _label(case.recommendation.owner_role)
        tokens["monitoring"] = case.recommendation.monitoring
        low, high = case.recommendation.expected_impact
        impact = money((low + high) / 2) if restricted else None
        if impact is not None:
            tokens["impact"] = impact
        else:
            low_s, high_s = money(low), money(high)
            if low_s is not None and high_s is not None:
                tokens["impact"] = f"{low_s} to {high_s}"

    if case.open_question is not None:
        tokens["open_question"] = case.open_question.question
        tokens["question_owner"] = _label(case.open_question.owner_role)
        value_at_stake = money(case.open_question.value_at_stake)
        if value_at_stake is not None:
            tokens["value_at_stake"] = value_at_stake

    return tokens


def _crore(v: float) -> str:
    sign = "−" if v < 0 else ""
    return f"{sign}₹{abs(v) / _CRORE:.1f} Cr"


def _percent(v: float, digits: int = 1) -> str:
    sign = "−" if v < 0 else ""
    return f"{sign}{abs(v) * 100:.{digits}f}%"


def _share(v: float) -> str:
    """A share of the movement, rounded to a whole percent — matching the
    UI's own `share()` in format.ts, deliberately not `_percent`'s one
    decimal place, which is reserved for the KPI's own delta_relative."""
    return f"{round(v * 100)}%"


def _label(value: str) -> str:
    return " ".join(w[:1].upper() + w[1:] for w in value.split("_"))


# ── The prompt ───────────────────────────────────────────────────────────────


def _prompt(case: Case, persona: Persona, tokens: dict[str, str]) -> Prompt:
    system = (
        "You write one page of a case file for a specific reader's role. You "
        "have four fields: headline, explanation, action, outstanding. Use "
        "the reader's role to decide what to emphasise and what to recommend "
        "they personally do next — two different readers of the same case "
        "should get two genuinely different pages, not the same page at two "
        "lengths.\n\n"
        "You may use only the named tokens below for any number, amount, "
        "percentage, name, date or fact — write them exactly as {token_name}, "
        "verbatim, and never write a digit yourself anywhere in any field. "
        "Every factual claim beyond a token must cite a ledger id from the "
        "list below, written as [ev-xxx]. Never invent a ledger id, a token, "
        "or a number. Leave a field empty only if it truly has nothing to say."
    )
    available = "\n".join(f"  {{{name}}} = {value}" for name, value in tokens.items())
    ledger = "\n".join(
        f"  [{item.id}] {item.claim}" for item in case.ledger[:30]
    ) or "  (none)"
    user = (
        f"Reader: {persona.label} (role: {persona.role_key})\n\n"
        f"Available tokens:\n{available}\n\n"
        f"Ledger, citable as [id]:\n{ledger}\n\n"
        "Write the four fields now."
    )
    return Prompt(stage="s8b", system=system, user=user)


# ── The guardrail ────────────────────────────────────────────────────────────


def _guardrail(section: str, text: str, tokens: dict[str, str], case: Case) -> str:
    """A section survives only if every `{token}` it uses is real, every
    `[ev-xxx]` it cites is real, and nothing else in it is a digit — else it
    is replaced by this section's own fully-templated fallback sentence."""
    ledger_ids = {item.id for item in case.ledger}
    used_tokens = set(_TOKEN.findall(text))
    used_citations = set(_CITATION.findall(text))

    if text.strip() and used_tokens <= tokens.keys() and used_citations <= ledger_ids:
        stripped = _CITATION.sub("", _TOKEN.sub("", text))
        if not any(ch.isdigit() for ch in stripped):
            return _TOKEN.sub(lambda m: tokens.get(m.group(1), m.group(0)), text)

    return _FALLBACKS[section](tokens)


def _fallback_headline(tokens: dict[str, str]) -> str:
    delta = tokens.get("delta", "")
    return f"{tokens['kpi']} moved {tokens['delta_pct']} ({delta}) in {tokens['period']}.".strip()


def _fallback_explanation(tokens: dict[str, str]) -> str:
    if "confidence" not in tokens:
        return "This case closed before a cause could be tested."
    driver = tokens.get("primary_driver")
    if driver is None:
        return f"Confidence: {tokens['confidence']}."
    share = tokens.get("primary_share")
    return f"Confidence: {tokens['confidence']}. Primary driver: {driver}" + (
        f" ({share})." if share else "."
    )


def _fallback_action(tokens: dict[str, str]) -> str:
    if "action" not in tokens:
        return "No recommendation — no controllable driver reached a verdict."
    return f"{tokens['action']} Owner: {tokens.get('owner', 'unassigned')}."


def _fallback_outstanding(tokens: dict[str, str]) -> str:
    if "open_question" not in tokens:
        return "Nothing outstanding."
    return f"{tokens['open_question']} Ask: {tokens.get('question_owner', 'the case owner')}."


_FALLBACKS = {
    "headline": _fallback_headline,
    "explanation": _fallback_explanation,
    "action": _fallback_action,
    "outstanding": _fallback_outstanding,
}
