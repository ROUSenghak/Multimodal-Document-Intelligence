# Third-party material and provenance notes

This repository contains reference material and document samples whose terms
are separate from any future license chosen for the project code.

## Course labs

`archive/course_labs/` contains DeepLearning.AI course notebooks, helper
code, and lesson assets. Their inclusion here does not relicense them. Confirm
the applicable course terms before redistributing the repository.

Parts of `archive/course_labs/helper.py` cite LandingAI documentation and
the `landing-ai/ade-helper-scripts` repository as their source.

## Evaluation documents

Detailed provenance and current rights assessments are recorded in
`data/annotations/documents.csv`.

- `data/documents/ch2.pdf`: ENSAE course slides; redistribution rights remain
  unverified.
- `data/documents/scanned.pdf`: an EPA sample letter; likely a United States
  federal government work, but the original source URL is unknown.
- `data/documents/apple_10k.pdf`: Apple Form 10-K sourced from SEC filing
  material and also used by the course labs.

## External benchmarks

`data/external/` contains files from public Hugging Face datasets; see
`data/external/README.md`.

- MMLongBench-Doc (`yubo2333/MMLongBench-Doc`): data licensed CC BY-NC 4.0,
  research use only. The question table and one PDF are committed; further
  PDFs are downloaded on demand and git-ignored.
- ViDoRe (`vidore/vidore_v3_finance_fr`) and OmniDocBench
  (`opendatalab/OmniDocBench`): committed cache and annotation files whose
  licence terms have not yet been recorded here. Check each dataset card
  before redistributing them.

Do not add private, confidential, or rights-restricted documents to the
repository. A top-level project license should be added only after the owner
chooses one and confirms that it applies to project-authored code rather than
the third-party files listed here.

