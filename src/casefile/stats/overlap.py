"""Footprint overlap — the Locality test's arithmetic, §15 S5.

    J(A, B) = |A n B| / |A u B|

*"A bug that hit every region cannot explain a drop in one."* Locality is the
test that kills the pricing decoy in §25: the price rise hit 41 enterprise
accounts and the movement sits in two, so J = 0.05 and a cause with a footprint
twenty times wider than its effect is not the cause.

§15's bands: `J > 0.5` passes, `J < 0.2` refutes, between them is inconclusive.
"""

from __future__ import annotations

from collections.abc import Iterable


def jaccard(cause: Iterable[str], effect: Iterable[str]) -> float:
    """Overlap of two entity sets.

    Raises on an empty union rather than returning a number. An empty union
    means neither footprint has any entities, so nothing about overlap has been
    established — and 0.0 would read as `refute` under §15's bands, which is a
    silently wrong answer rather than a missing one. The caller's honest verdict
    for a cause with no footprint is `uncheckable` (§14.2), and making it handle
    this explicitly is the point.
    """
    a, b = set(cause), set(effect)
    union = a | b
    if not union:
        raise ValueError(
            "Jaccard over two empty footprints: nothing has been established "
            "about overlap. This is an `uncheckable` probe outcome, not J = 0."
        )
    return len(a & b) / len(union)
