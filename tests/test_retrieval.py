"""BM25 retrieval: formula, tie-breaking, failure cases, and parity with the frozen E0 rankings."""

import ast
import csv
from math import isclose, log

import pytest

from conftest import FROZEN_E0_IMAGE_SETTINGS, FROZEN_E0_TEXT_RUN, PAGES_PARQUET, read_json
from visualdoc import retrieval
from visualdoc.retrieval import BM25Index, tokenize


def test_parameters_equal_the_frozen_settings():
    frozen = read_json(FROZEN_E0_IMAGE_SETTINGS)
    assert (retrieval.BM25_K1, retrieval.BM25_B, retrieval.TOP_K) == (frozen["bm25_k1"], frozen["bm25_b"], frozen["generation_top_k"])


def test_tokenize_lowercases_and_splits_on_non_alphanumerics():
    assert tokenize("Lufthansa's 12 Tweets, (2015)!") == ["lufthansa", "s", "12", "tweets", "2015"]
    assert tokenize("Café") == ["caf"]  # ASCII only, as in notebook 01: accented letters split words
    assert tokenize("") == []


def test_score_matches_the_formula_by_hand():
    index = BM25Index({1: "apple apple banana", 2: "banana cherry", 3: "cherry cherry cherry date"})
    n, avgdl, k1, b = 3, 3.0, 1.5, 0.75
    idf_apple = log(1 + (n - 1 + 0.5) / (1 + 0.5))
    idf_banana = log(1 + (n - 2 + 0.5) / (2 + 0.5))
    expected_page1 = sum(idf * f * (k1 + 1) / (f + k1 * (1 - b + b * 3 / avgdl)) for idf, f in ((idf_apple, 2), (idf_banana, 1)))
    scores = dict(index.rank("apple banana"))
    assert isclose(scores[1], expected_page1, rel_tol=1e-12)
    assert scores[3] == 0.0
    assert index.top_pages("apple banana", k=2) == [1, 2]


def test_repeated_query_terms_count_once():
    index = BM25Index({1: "alpha beta", 2: "beta gamma"})
    assert index.rank("alpha") == index.rank("alpha alpha ALPHA")


def test_ties_and_unmatched_queries_are_ordered_by_page_number():
    index = BM25Index({3: "same words", 1: "same words", 2: "other text"})
    assert [page for page, _ in index.rank("same")][:2] == [1, 3]
    assert index.top_pages("nothing matches", k=3) == [1, 2, 3]  # all scores 0


def test_empty_pages_do_not_break_the_index():
    index = BM25Index({1: "", 2: "", 3: "answer here"})
    assert index.top_pages("answer", k=1) == [3]
    assert BM25Index({1: "", 2: ""}).rank("anything") == [(1, 0.0), (2, 0.0)]


def test_failure_cases():
    with pytest.raises(ValueError, match="no pages"):
        BM25Index({})
    with pytest.raises(ValueError, match="at least 1"):
        BM25Index({1: "text"}).top_pages("text", k=0)
    assert BM25Index({1: "a", 2: "b"}).top_pages("a", k=10) == [1, 2]  # k larger than the document


def test_rankings_equal_the_frozen_e0_text_run():
    """Every page position of every question's ranking equals the frozen run (needs notebook 00's pages.parquet)."""
    pd = pytest.importorskip("pandas")
    if not PAGES_PARQUET.is_file():
        pytest.skip("pages.parquet is git-ignored: run notebook 00")
    pages = pd.read_parquet(PAGES_PARQUET)
    indexes = {doc: BM25Index(dict(zip(group["page"], group["text"]))) for doc, group in pages.groupby("doc_id")}
    with open(FROZEN_E0_TEXT_RUN / "scored_predictions.csv", newline="") as handle:
        frozen = list(csv.DictReader(handle))
    assert len(frozen) == 57
    for row in frozen:
        assert [page for page, _ in indexes[row["doc_id"]].rank(row["question"])] == ast.literal_eval(row["ranking"]), row["qid"]
