# `data/external/` — public benchmarks

Third-party datasets used to test the pipeline on documents and questions
that the project did not write. They are separate from the project's own
annotation set in `data/annotations/`.

| Folder | Source (Hugging Face) | Used by | What is local | Licence |
| --- | --- | --- | --- | --- |
| `mmlongbench_doc/` | `yubo2333/MMLongBench-Doc`, pinned revision `2ff6aa92…` | **notebooks 00–03** (archived 12–15) | question table (`data/*.parquet`, tracked); PDFs downloaded on demand (`documents/`, git-ignored) | data **CC BY-NC 4.0**, research use only (dataset README) |
| `vidore/` | `vidore/vidore_v3_finance_fr` | archived notebooks 12, 13 only | query and relevance tables in a `datasets` cache (git-ignored; untracked on 2026-11-22) | see the dataset card |
| `omnidocbench/` | `opendatalab/OmniDocBench` | archived notebooks 12, 13 only | `OmniDocBench.json` layout annotations (40 MB, git-ignored; untracked on 2026-11-22, see below) | no SPDX licence; dataset README: "for research purposes only and not for commercial use" |
| `doclaynet/` | — | — | empty placeholder created by archived notebook 12 | — |

## MMLongBench-Doc in brief

- 1,091 questions over 135 PDFs (7 domains, about 47 pages per document).
- Columns: `doc_id`, `doc_type`, `question`, `answer`, `evidence_pages`,
  `evidence_sources`, `answer_format`. List columns are stored as strings
  (`'[5]'`) and are parsed with `ast.literal_eval`.
- `evidence_pages` are **1-based physical PDF pages** (`pdf[p - 1]` in
  PyMuPDF). Notebook 00 checks this against answer strings, a synthetic PDF
  and OCR of real pages; notebook 01 checks it against retrieval rankings. Three rows cite page `0`; they are treated as annotation
  errors.
- 244 questions are unanswerable: `answer == "Not answerable"` and
  `answer_format == "None"`.
- Four `Int` questions have non-integer reference answers (`21%`,
  `14:04 CET`, `yes`, `GPT-4`), so they can never be scored correct under
  the official rules.
- Official scoring: `eval/eval_score.py` in
  `github.com/mayubo2333/MMLongBench-Doc` (notebook 03 re-implements it at
  commit `d73f0dc`).

## What Git tracks here

The ignore rules in the root `.gitignore` keep Hugging Face `.cache/`
folders, `*.lock` files, the ViDoRe `datasets` cache and downloaded
MMLongBench PDFs and `OmniDocBench.json` out of Git. Three of them had been
committed before those rules existed: the ViDoRe Arrow cache, one MMLongBench
PDF (not in the 6-document subset) and `OmniDocBench.json`. On 2026-11-22 they
were removed from tracking with `git rm --cached`: local copies are kept, Git
history still holds them (history was not rewritten), and fresh clones
re-download them only for the archived notebooks.

## OmniDocBench (archived notebooks only)

- **Source:** Hugging Face dataset `opendatalab/OmniDocBench`, file
  `OmniDocBench.json` (42,208,096 bytes), revision
  `aa1ee96d106dbe53d0ae59474d75c6e6d9b53fec`. The archived notebook 12
  downloaded it on 2026-11-18 without pinning a revision; the local file's
  SHA-256 equals the Hub's LFS hash of that file at this revision (checked
  2026-11-22).
- **SHA-256:** `a45cd84b04ad8b793e775089640e6b681209abea33ead54c1828ddca35fae496`
- **Licence:** the dataset card declares no licence. Its README "Copyright
  Statement" says the PDFs come from public online channels and community
  contributions and that "the dataset is for research purposes only and not
  for commercial use". It is therefore not redistributed here.
- **Download and verify:**

  ```bash
  python -c "from huggingface_hub import hf_hub_download; hf_hub_download('opendatalab/OmniDocBench', 'OmniDocBench.json', repo_type='dataset', revision='aa1ee96d106dbe53d0ae59474d75c6e6d9b53fec', local_dir='data/external/omnidocbench')"
  shasum -a 256 data/external/omnidocbench/OmniDocBench.json   # expect a45cd84b…fae496
  ```

Anything committed here is redistributed publicly. Check each dataset's
licence before committing more of its files.
