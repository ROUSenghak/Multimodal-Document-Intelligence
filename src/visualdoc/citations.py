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

from collections.abc import Iterable
from dataclasses import dataclass

from .answering import NOT_ANSWERABLE


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
