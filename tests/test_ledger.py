"""ledger.py — the evidence bag is append-only, and a citation always resolves."""

from __future__ import annotations

from datetime import datetime

import pytest

from casefile.ledger import Ledger, LedgerError
from casefile.models import EvidenceItem, Source

SOURCE = Source(system="crm", record_id="opp-1", timestamp=datetime(2026, 4, 12, 9, 0))


def an_evidence_item(**overrides: object) -> EvidenceItem:
    payload: dict[str, object] = {
        "id": "ev-1",
        "claim": "Integration ticket volume rose 3.2x on ACME",
        "kind": "fact",
        "outcome": "found",
        "source": SOURCE,
        "method": "sql",
        "strength": 0.8,
        "freshness_hours": 4.0,
    }
    payload.update(overrides)
    return EvidenceItem.model_validate(payload)


def test_an_added_item_is_returned_and_stored() -> None:
    ledger = Ledger()
    item = an_evidence_item()
    assert ledger.add(item) is item
    assert ledger.all() == [item]


def test_two_items_with_the_same_id_collide() -> None:
    """An id is a citation target — two items answering to it is worse than
    rejecting the second outright."""
    ledger = Ledger()
    ledger.add(an_evidence_item(id="ev-1"))
    with pytest.raises(LedgerError, match="duplicate"):
        ledger.add(an_evidence_item(id="ev-1", claim="a different claim entirely"))


def test_all_returns_a_copy_the_caller_cannot_mutate_the_ledger_through() -> None:
    ledger = Ledger()
    ledger.add(an_evidence_item(id="ev-1"))
    snapshot = ledger.all()
    snapshot.append(an_evidence_item(id="ev-2"))
    snapshot.clear()
    assert len(ledger.all()) == 1


def test_get_resolves_a_citation() -> None:
    ledger = Ledger()
    item = an_evidence_item(id="ev-7")
    ledger.add(item)
    assert ledger.get("ev-7") is item


def test_get_on_an_unknown_id_raises_rather_than_returning_none() -> None:
    """A narration citing a dangling id should fail loudly, not render a blank."""
    ledger = Ledger()
    with pytest.raises(LedgerError, match="ev-404"):
        ledger.get("ev-404")


def test_for_driver_finds_items_that_support_it() -> None:
    ledger = Ledger()
    item = an_evidence_item(id="ev-1", supports=["integration_delay"])
    ledger.add(item)
    ledger.add(an_evidence_item(id="ev-2", supports=["pricing_change"]))
    assert ledger.for_driver("integration_delay") == [item]


def test_for_driver_finds_items_that_contradict_it_too() -> None:
    """Elimination evidence lives in `contradicts`, and Stage 6 needs both
    directions to rank a hypothesis — missing one would make an eliminated
    driver's own refuting evidence invisible to the case that eliminated it."""
    ledger = Ledger()
    item = an_evidence_item(
        id="ev-1",
        outcome="checked_absent",
        denominator=12,
        contradicts=["competitor_offer"],
    )
    ledger.add(item)
    assert ledger.for_driver("competitor_offer") == [item]


def test_for_driver_is_empty_for_a_driver_nothing_names() -> None:
    ledger = Ledger()
    ledger.add(an_evidence_item(id="ev-1", supports=["integration_delay"]))
    assert ledger.for_driver("supply_delay") == []


def test_an_item_can_support_one_driver_and_contradict_another() -> None:
    ledger = Ledger()
    item = an_evidence_item(
        id="ev-1", supports=["integration_delay"], contradicts=["pricing_change"]
    )
    ledger.add(item)
    assert ledger.for_driver("integration_delay") == [item]
    assert ledger.for_driver("pricing_change") == [item]
