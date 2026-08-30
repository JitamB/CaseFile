"""Decomposition-scoped retrieval — §15 S4b, and C9's answer.

    45,000 docs -> filter by footprint (exact, not semantic) -> ~200 -> BM25 -> top 15

Two narrowings and one ranking. The narrowings are where the cost goes: they are
exact, so every token they remove is removed with certainty. §18 rejects
whole-corpus RAG for this reason and not on taste — *"better **and** 10-15x
cheaper"*.
"""

from __future__ import annotations

from collections.abc import Sequence

import duckdb

from casefile.models import Driver, Footprint
from casefile.retrieval.rank import DEFAULT_K, BM25Ranker, Ranker, recall_at, top
from casefile.retrieval.scope import Document, corpus_size, scope

__all__ = [
    "DEFAULT_K",
    "BM25Ranker",
    "Document",
    "Funnel",
    "Ranker",
    "corpus_size",
    "recall_at",
    "retrieve",
    "scope",
    "top",
]


class Funnel(list[Document]):
    """The top-`k` documents, carrying the two counts they were narrowed from.

    Stage 10 reports the funnel per case, so the 10-15x claim in §19 is a
    measurement on every run rather than a sentence in a document.
    """

    def __init__(
        self, documents: Sequence[Document], corpus: int, scoped: int
    ) -> None:
        super().__init__(documents)
        self.corpus = corpus
        self.scoped = scoped

    @property
    def reduction(self) -> float:
        """How many times smaller the ranked slice is than the whole corpus."""
        return self.corpus / len(self) if self else float("inf")


def retrieve(
    con: duckdb.DuckDBPyConnection,
    footprint: Footprint,
    query: str,
    driver: Driver | None = None,
    k: int = DEFAULT_K,
    ranker: Ranker | None = None,
) -> Funnel:
    """Scope by footprint, then rank. The whole of Stage 4b."""
    scoped = scope(con, footprint, driver)
    return Funnel(top(scoped, query, k, ranker), corpus_size(con), len(scoped))
