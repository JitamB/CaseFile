"""Stage 4b, second half — ranking. §15 S4b.

*"Ranking, not judgement"* (§17). Nothing here decides what is true; it decides
what order a fixed set of documents is read in, and the extractor at 2.3 reads
the top slice. That distinction is why this stage sits on the non-LLM side of
§17's table.

**On the backend, and why the default is lexical.** §18 names
`sentence-transformers` with `all-MiniLM-L6-v2`. Its stated justification is
*"local, free, offline — no API dependency during the demo"*, and BM25 satisfies
all three at 0.1% of the install size. The case for embeddings is paraphrase:
they earn their keep when different words mean the same thing. Two facts about
this corpus cut against that —

* the 46k -> ~1k narrowing is an **exact** footprint filter, so all the token
  reduction §19 claims happens before any ranker runs; embeddings would only
  reorder the last mile;
* §24's noise is **template-generated**, so paraphrase diversity is precisely
  what it does not have, and the authored signal is authored by us.

So the backend is a decision to be measured, not argued, and `recall_at` is the
measurement: the authored documents are known ground truth, so *"did the ranker
put the signal in the top 15?"* is a number. `MiniLMBackend` is implemented for
real behind the `embed` extra; CI does not install it and the demo path does not
select it, so the pipeline ranks identically everywhere — §35.5 requires that
every numeric field be reproducible, and a ranker that changed with what happens
to be installed would quietly break it.
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from typing import Protocol

from rank_bm25 import BM25Okapi

from casefile.retrieval.scope import Document

#: §15's funnel ends here: "-> top 15".
DEFAULT_K = 15

_TOKEN = re.compile(r"[a-z0-9']+")
#: Suffixes stripped before matching. Not a linguistic claim — a query for
#: "competitor" must reach a note that says "competitors", and without this BM25
#: misses it entirely. Any lexical retriever worth comparing against normalises;
#: leaving it out would make the baseline artificially weak and the comparison
#: with §18's embeddings meaningless.
_SUFFIXES = ("iness", "ingly", "edly", "ings", "ies", "ing", "ers", "est", "ed", "es", "er", "s")
#: Words too common in this corpus to separate anything. Deliberately short: an
#: aggressive stop list is a place to hide a ranking decision.
_STOPWORDS = frozenset(
    "the a an and or of to in on for with is are was were be been it its this that "
    "they them their we our you your i at by from as has have had not no but if".split()
)


def _stem(token: str) -> str:
    for suffix in _SUFFIXES:
        if len(token) > len(suffix) + 2 and token.endswith(suffix):
            stem = token[: -len(suffix)]
            if suffix == "ies":
                return stem + "y"
            # "deferred" -> "deferr" -> "defer": English doubles the final
            # consonant before -ed and -ing, and leaving it doubled means the
            # inflected and uninflected forms never match.
            if len(stem) > 2 and stem[-1] == stem[-2] and stem[-1] not in "lsz":
                stem = stem[:-1]
            return stem
    return token


def tokenise(text: str) -> list[str]:
    return [_stem(t) for t in _TOKEN.findall(text.lower()) if t not in _STOPWORDS]


class Ranker(Protocol):
    def rank(self, documents: Sequence[Document], query: str) -> list[float]:
        """One score per document, index-aligned. Higher is more relevant.

        `-inf` means **not a match at all**, which is different from scoring
        badly: `top` drops those rather than ranking them. A lexical ranker can
        say it (no shared term is no shared term); an embedding ranker cannot,
        because a paraphrase match has no token in common with its query, so it
        scores every document and drops none.
        """
        ...


class BM25Ranker:
    """Okapi BM25 over the scoped set — §18's `rank_bm25`.

    Documents sharing no term with the query score `-inf`. Note that this is
    **not** the same as "scored zero or below": Okapi's IDF goes *negative* for a
    term that appears in more than half the corpus, and after the footprint
    filter that describes words like "integration" exactly. Excluding on the sign
    of the score would therefore drop the most on-topic documents in the set,
    which is the opposite of the intent.
    """

    name = "bm25"

    def rank(self, documents: Sequence[Document], query: str) -> list[float]:
        if not documents:
            return []
        terms = set(tokenise(query))
        corpus = [tokenise(d.text) or ["\x00"] for d in documents]
        scores = BM25Okapi(corpus).get_scores(sorted(terms))
        return [
            float(score) if terms & set(tokens) else -math.inf
            for score, tokens in zip(scores, corpus, strict=True)
        ]


class MiniLMRanker:
    """`all-MiniLM-L6-v2` cosine similarity — §18's named model.

    Behind the `embed` extra, and **never selected by availability**: a ranker
    that switched on because a library happened to be installed would make the
    top-15 depend on the machine, and §35.5 requires the numbers not to move.
    Construct it explicitly, or not at all.
    """

    name = "minilm"

    def __init__(self, model: str = "sentence-transformers/all-MiniLM-L6-v2") -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # pragma: no cover - the extra is not installed in CI
            raise ImportError(
                "MiniLMRanker needs the `embed` extra: pip install -e '.[embed]'. "
                "It is deliberately not a default dependency — see casefile.retrieval.rank"
            ) from exc
        self._model = SentenceTransformer(model)

    def rank(self, documents: Sequence[Document], query: str) -> list[float]:  # pragma: no cover
        import numpy as np

        if not documents:
            return []
        vectors = self._model.encode(
            [d.text for d in documents], normalize_embeddings=True, show_progress_bar=False
        )
        wanted = self._model.encode([query], normalize_embeddings=True, show_progress_bar=False)
        return [float(s) for s in np.asarray(vectors) @ np.asarray(wanted)[0]]


def top(
    documents: Sequence[Document],
    query: str,
    k: int = DEFAULT_K,
    ranker: Ranker | None = None,
) -> list[Document]:
    """The `k` best documents for `query`, most relevant first.

    **Fewer than `k` is a correct answer.** A document the ranker scores `-inf`
    is not the eighth-best match, it is not a match — and on this corpus a
    thousand of them share no word with the query, so returning `k` regardless
    would pad the extractor's input with whatever the tie-break happened to
    surface. §19 budgets ~9k input tokens for extraction; fifteen documents of
    which eight are noise spends that budget on nothing and gives the model eight
    chances to extract a claim about an irrelevant record.

    Ties among genuine matches break on `(when, table, doc_id)` — the same order
    `scope` returns — so two runs over the same corpus produce the same list.
    Left to the sort's own stability it would still be deterministic, but only by
    accident of the input order, and §35.5 is a promise rather than an accident.
    """
    scored = (ranker or BM25Ranker()).rank(documents, query)
    ordered = sorted(
        (pair for pair in zip(documents, scored, strict=True) if pair[1] > -math.inf),
        key=lambda pair: (-pair[1], pair[0].when, pair[0].table, pair[0].doc_id),
    )
    return [document for document, _ in ordered[:k]]


def recall_at(
    documents: Sequence[Document],
    query: str,
    wanted: Sequence[str],
    k: int = DEFAULT_K,
    ranker: Ranker | None = None,
) -> float:
    """Share of `wanted` document ids that reach the top `k`.

    This is what decides the backend. The authored documents are ground truth we
    wrote ourselves, so *"did the ranker surface the signal?"* is a measurement
    rather than an opinion — and a spec deviation backed by a number is worth
    more than one backed by a rationale.
    """
    if not wanted:
        raise ValueError("recall over an empty set of wanted documents")
    found = {d.doc_id for d in top(documents, query, k, ranker)}
    return len(found & set(wanted)) / len(set(wanted))
