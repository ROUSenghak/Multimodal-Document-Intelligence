"""BM25 ranking of the pages of one PDF for a question (notebook 01's retriever).

For a query q and page d with term counts f(t, d), length |d| and mean page
length avgdl over the N pages of the document:

    score(d, q) = sum over distinct t in q of
                  idf(t) * f(t, d) * (k1 + 1) / (f(t, d) + k1 * (1 - b + b * |d| / avgdl))
    idf(t)      = log(1 + (N - n_t + 0.5) / (n_t + 0.5)),   n_t = pages containing t

Tokens are lower-cased runs of ASCII letters and digits; k1 = 1.5, b = 0.75.
Ties are broken by page number, so rankings are deterministic. Statistics are
per document: a page competes only with the other pages of its own PDF.
"""

import re
from collections import Counter
from collections.abc import Callable, Mapping
from math import log
from typing import Any, Protocol

TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
BM25_K1 = 1.5
BM25_B = 0.75
TOP_K = 5


class Retriever(Protocol):
    """One ranking tool; the pipeline depends on this interface, not a model library."""

    name: str

    def rank(self, question: str) -> list[tuple[int, float]]: ...


def tokenize(text: str) -> list[str]:
    return TOKEN_PATTERN.findall(str(text).lower())


class BM25Index:
    """BM25 statistics of one document, built from ``{page_number: text}``."""

    name = "bm25"

    def __init__(self, page_texts: Mapping[int, str], k1: float = BM25_K1, b: float = BM25_B):
        if not page_texts:
            raise ValueError("cannot index a document with no pages")
        self.k1, self.b = k1, b
        tokens = {page: tokenize(text) for page, text in page_texts.items()}
        self.term_counts = {page: Counter(page_tokens) for page, page_tokens in tokens.items()}
        self.lengths = {page: len(page_tokens) for page, page_tokens in tokens.items()}
        self.avgdl = sum(self.lengths.values()) / len(self.lengths)
        n_pages = len(tokens)
        frequency = Counter(token for page_tokens in tokens.values() for token in set(page_tokens))
        self.idf = {token: log(1 + (n_pages - n_t + 0.5) / (n_t + 0.5)) for token, n_t in frequency.items()}

    def rank(self, query: str) -> list[tuple[int, float]]:
        """Every page with its score, best first; ties broken by page number."""
        terms = set(tokenize(query))
        scored = []
        for page, counts in self.term_counts.items():
            length_factor = self.k1 * (1 - self.b + self.b * self.lengths[page] / max(self.avgdl, 1.0))
            score = sum(self.idf[t] * counts[t] * (self.k1 + 1) / (counts[t] + length_factor) for t in terms if counts[t])
            scored.append((page, score))
        return sorted(scored, key=lambda item: (-item[1], item[0]))

    def top_pages(self, query: str, k: int = TOP_K) -> list[int]:
        """The k best pages. Pages scoring 0 are kept: with no matching term the order is by page number."""
        if k < 1:
            raise ValueError("k must be at least 1")
        return [page for page, _ in self.rank(query)[:k]]


def maxsim_score(query_embeddings: Any, page_embeddings: Any) -> float:
    """Late interaction: sum, over query tokens, of the best page-token dot product."""
    try:
        import numpy as np
    except ImportError as error:
        raise RuntimeError("cached visual retrieval needs NumPy; install visualdoc-ai[visual]") from error
    query, page = np.asarray(query_embeddings), np.asarray(page_embeddings)
    if query.ndim != 2 or page.ndim != 2 or query.shape[1:] != page.shape[1:]:
        raise ValueError(f"need query/page matrices with one shared embedding width, got {query.shape} and {page.shape}")
    if query.shape[0] == 0 or page.shape[0] == 0:
        raise ValueError("query and page embeddings must contain at least one token")
    return float((query @ page.T).max(axis=1).sum())


class CachedVisualIndex:
    """ColQwen-style MaxSim over cached page embeddings; it never loads model weights."""

    name = "visual"

    def __init__(self, page_embeddings: Mapping[int, Any], query_encoder: Callable[[str], Any]):
        if not page_embeddings:
            raise ValueError("cannot index a document with no page embeddings")
        self.page_embeddings = dict(page_embeddings)
        self.query_encoder = query_encoder

    def rank(self, question: str) -> list[tuple[int, float]]:
        if not str(question).strip():
            raise ValueError("the question is empty")
        query = self.query_encoder(question)
        scored = [(page, maxsim_score(query, embeddings)) for page, embeddings in self.page_embeddings.items()]
        return sorted(scored, key=lambda item: (-item[1], item[0]))


class FrozenRankingRetriever:
    """A named immutable ranking, used when an experiment freezes retrieval before reader evaluation."""

    def __init__(self, ranking: list[tuple[int, float]], name: str = "frozen_visual"):
        if not ranking:
            raise ValueError("a frozen ranking cannot be empty")
        pages = [page for page, _ in ranking]
        if len(set(pages)) != len(pages):
            raise ValueError("a page occurs twice in the frozen ranking")
        self._ranking, self.name = list(ranking), name

    def rank(self, question: str) -> list[tuple[int, float]]:
        if not str(question).strip():
            raise ValueError("the question is empty")
        return list(self._ranking)
