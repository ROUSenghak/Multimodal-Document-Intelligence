"""Citation validation: supplied pages, printed-page (off-by-one) citations, missing citations, evidence."""

import pytest

from visualdoc.citations import check_citations


def test_valid_citation():
    check = check_citations(41, [16], supplied=[16, 3])
    assert check.ok and check.all_supplied and not check.off_by_one and not check.missing and check.cites_evidence is None


def test_unsupplied_page_is_invalid():
    check = check_citations(41, [16, 30], supplied=[16, 3])
    assert check.invalid == (30,) and not check.all_supplied and not check.ok and not check.off_by_one


def test_printed_page_number_is_detected_as_off_by_one():
    check = check_citations("x", [14], supplied=[15, 20])  # printed "14" on PDF page 15
    assert check.invalid == (14,) and check.off_by_one and not check.ok
    mixed = check_citations("x", [14, 30], supplied=[15, 20])
    assert not mixed.off_by_one  # only when every invalid page is one below a supplied page


def test_abstention_needs_no_citation_but_an_answer_does():
    assert check_citations("Not answerable", [], supplied=[1, 2]).ok
    uncited = check_citations(12, [], supplied=[1, 2])
    assert uncited.missing and uncited.all_supplied and not uncited.ok  # validity alone is vacuous here


def test_repeats_are_ignored_and_order_kept():
    assert check_citations(1, [3, 1, 3], supplied=[1, 3]).cited == (3, 1)


def test_evidence_is_checked_when_known():
    assert check_citations(1, [3], supplied=[1, 3], evidence=[3]).cites_evidence is True
    assert check_citations(1, [1], supplied=[1, 3], evidence=[3]).cites_evidence is False


def test_no_supplied_pages_is_an_error():
    with pytest.raises(ValueError, match="no supplied pages"):
        check_citations(1, [1], supplied=[])
