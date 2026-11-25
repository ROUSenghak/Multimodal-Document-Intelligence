"""Check the pages a reply cites against the pages it was given.

Definitions follow notebook 03:

- a citation is *invalid* when it names a page that was not supplied;
- *off by one* when every invalid page equals a supplied page minus one, the
  signature of citing the page number printed on the page instead of the
  ``[Page N]`` tag (7 of 9 invalid image replies in the frozen E0 runs);
- a reply *cites evidence* when at least one cited page is an annotated
  evidence page (only when the evidence is known, e.g. in evaluation);
- an answer other than "Not answerable" with no citation is *missing* one.

"All cited pages were supplied" is vacuously true for an empty citation list,
so read it together with ``missing``. ``ok`` combines both.

``ok`` checks the form of a citation, not its support: it does not verify that
a cited page contains the answer (in the frozen text condition A, citation
validity was 1.000 while 7 of 40 answers were correct). ``cites_evidence`` is a
support check only against annotated evidence, so it exists only in evaluation.
"""

import re
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher

from .answering import EvidenceQuote, NOT_ANSWERABLE


@dataclass(frozen=True)
class CitationCheck:
    cited: tuple[int, ...]
    supplied: tuple[int, ...]
    invalid: tuple[int, ...]
    off_by_one: bool
    missing: bool
    cites_evidence: bool | None

    @property
    def all_supplied(self) -> bool:
        return not self.invalid

    @property
    def ok(self) -> bool:
        return self.all_supplied and not self.missing


def check_citations(answer, cited: Iterable[int], supplied: Iterable[int], evidence: Iterable[int] | None = None) -> CitationCheck:
    cited = tuple(dict.fromkeys(cited))  # drop repeats, keep order
    supplied = tuple(supplied)
    if not supplied:
        raise ValueError("no supplied pages to check against")
    supplied_set = set(supplied)
    invalid = tuple(page for page in cited if page not in supplied_set)
    off_by_one = bool(invalid) and all(page + 1 in supplied_set for page in invalid)
    abstained = answer == NOT_ANSWERABLE
    missing = not abstained and not cited
    cites_evidence = None if evidence is None else bool(set(cited) & set(evidence))
    return CitationCheck(cited, supplied, invalid, off_by_one, missing, cites_evidence)


NUMBER_PATTERN = re.compile(r"(?<![\w.])[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?%?")


def normalize_evidence_text(text: str) -> str:
    """Normalize Unicode and spacing while preserving words, digits and punctuation."""
    return " ".join(unicodedata.normalize("NFKC", str(text)).casefold().split())


def quote_match_score(quote: str, page_text: str) -> float:
    """Best normalized local similarity of a short quote to a cited page."""
    quote_norm, page_norm = normalize_evidence_text(quote), normalize_evidence_text(page_text)
    if not quote_norm or not page_norm:
        return 0.0
    if quote_norm in page_norm:
        return 1.0
    quote_words, page_words = quote_norm.split(), page_norm.split()
    target = len(quote_words)
    if target == 0:
        return 0.0
    lengths = range(max(1, target - 2), target + 3)
    return max(
        (
            SequenceMatcher(None, quote_norm, " ".join(page_words[start:start + length]), autojunk=False).ratio()
            for length in lengths
            for start in range(max(1, len(page_words) - length + 1))
        ),
        default=0.0,
    )


def _canonical_numbers(value) -> tuple[str, ...]:
    if isinstance(value, bool):
        return ()
    if isinstance(value, (int, float, Decimal)):
        raw = [str(value)]
    elif isinstance(value, list):
        return tuple(dict.fromkeys(number for item in value for number in _canonical_numbers(item)))
    else:
        raw = NUMBER_PATTERN.findall(str(value))
    canonical = []
    for number in raw:
        percent = str(number).endswith("%")
        cleaned = str(number).removesuffix("%").replace(",", "")
        try:
            normalized = format(Decimal(cleaned).normalize(), "f")
        except InvalidOperation:
            continue
        canonical.append(normalized + ("%" if percent else ""))
    return tuple(dict.fromkeys(canonical))


@dataclass(frozen=True)
class GroundingCheck:
    quote_scores: tuple[tuple[int, float], ...]
    invalid_evidence_pages: tuple[int, ...]
    missing_evidence_pages: tuple[int, ...]
    numeric_support: bool | None
    answer_numbers: tuple[str, ...]
    derived_numbers: bool
    answer_requires_evidence: bool
    threshold: float

    @property
    def quotes_supported(self) -> bool:
        return (
            not self.invalid_evidence_pages
            and not self.missing_evidence_pages
            and (not self.answer_requires_evidence or bool(self.quote_scores))
            and all(score >= self.threshold for _, score in self.quote_scores)
        )

    @property
    def ok(self) -> bool:
        return self.quotes_supported and self.numeric_support is not False


def check_grounding(
    answer,
    cited: Iterable[int],
    evidence: Iterable[EvidenceQuote],
    page_texts: Mapping[int, str],
    *,
    threshold: float = 0.9,
    derived_numbers: bool = False,
) -> GroundingCheck:
    """Verify B1 evidence passages and numeric answers against cited-page text.

    A calculation may set ``derived_numbers=True``: the source numbers must then
    be checked by a later derivation validator, so this form check does not
    incorrectly require the computed result to appear verbatim.
    """
    if not 0 <= threshold <= 1:
        raise ValueError("quote threshold must be between 0 and 1")
    cited = tuple(dict.fromkeys(cited))
    evidence = tuple(evidence)
    cited_set = set(cited)
    invalid = tuple(item.page for item in evidence if item.page not in cited_set or item.page not in page_texts)
    represented = {item.page for item in evidence if item.page in cited_set}
    missing = () if answer == NOT_ANSWERABLE else tuple(page for page in cited if page not in represented)
    scores = tuple(
        (item.page, quote_match_score(item.quote, page_texts.get(item.page, "")))
        for item in evidence
    )

    answer_numbers = _canonical_numbers(answer)
    if answer == NOT_ANSWERABLE or not answer_numbers or derived_numbers:
        numeric_support = None
    else:
        cited_numbers = set(_canonical_numbers(" ".join(page_texts.get(page, "") for page in cited)))
        numeric_support = all(number in cited_numbers for number in answer_numbers)
    return GroundingCheck(
        scores, invalid, missing, numeric_support, answer_numbers, derived_numbers,
        answer != NOT_ANSWERABLE, threshold,
    )
