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
from collections.abc import Mapping
from math import log

TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
BM25_K1 = 1.5
BM25_B = 0.75
TOP_K = 5


def tokenize(text: str) -> list[str]:
    return TOKEN_PATTERN.findall(str(text).lower())


class BM25Index:
    """BM25 statistics of one document, built from ``{page_number: text}``."""

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
