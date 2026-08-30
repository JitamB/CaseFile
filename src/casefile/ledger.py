"""The evidence ledger — §14.2, models.py's rule 4.

*"The evidence bag. Every fact goes into a labelled bag tagged with where it
came from. Nothing appears in the final report unless it came out of a bag."*

`EvidenceItem` is already frozen (models.py rule 4), so this module adds
exactly one thing a frozen model cannot enforce on its own: that the *ledger*
itself is append-only. `all()` returns a copy, so a caller cannot pop or
reorder their way around that. There is no `remove` and no `__setitem__`.

IDs are assigned by whoever builds the item (§4a's probes, §4c's extraction),
not by this module — they read as ledger citations in the narrative
(`ev-ticket_spike-001`), and only the writer knows a name worth citing.
"""

from __future__ import annotations

from casefile.models import EvidenceItem


class LedgerError(ValueError):
    pass


class Ledger:
    """Append-only store of `EvidenceItem`. One per case."""

    def __init__(self) -> None:
        self._items: list[EvidenceItem] = []
        self._by_id: dict[str, EvidenceItem] = {}

    def add(self, item: EvidenceItem) -> EvidenceItem:
        if item.id in self._by_id:
            raise LedgerError(
                f"duplicate evidence id {item.id!r} — every citation in the case must "
                "point at exactly one item"
            )
        self._items.append(item)
        self._by_id[item.id] = item
        return item

    def all(self) -> list[EvidenceItem]:
        """A copy. Mutating the result cannot mutate the ledger."""
        return list(self._items)

    def get(self, id: str) -> EvidenceItem:
        try:
            return self._by_id[id]
        except KeyError:
            raise LedgerError(f"no evidence item {id!r} in the ledger") from None

    def for_driver(self, driver_id: str) -> list[EvidenceItem]:
        """Every item that names this driver, supporting or contradicting it —
        what Stage 5 and Stage 6 read to test and rank a hypothesis."""
        return [
            item
            for item in self._items
            if driver_id in item.supports or driver_id in item.contradicts
        ]
