# `data/external/` — public benchmarks

Third-party datasets used to test the pipeline on documents and questions
that the project did not write. They are separate from the project's own
annotation set in `data/annotations/`.

| Folder | Source (Hugging Face) | Used by | What is local | Licence |
| --- | --- | --- | --- | --- |
| `mmlongbench_doc/` | `yubo2333/MMLongBench-Doc`, pinned revision `2ff6aa92…` | **notebooks 00–03** (archived 12–15) | question table (`data/*.parquet`, tracked); PDFs downloaded on demand (`documents/`, git-ignored) | data **CC BY-NC 4.0**, research use only (dataset README) |
| `vidore/` | `vidore/vidore_v3_finance_fr` | archived notebooks 12, 13 only | query and relevance tables in a `datasets` cache (tracked before the ignore rules existed) | see the dataset card |
| `omnidocbench/` | `opendatalab/OmniDocBench` | archived notebooks 12, 13 only | `OmniDocBench.json` layout annotations (40 MB, tracked) | see the dataset card |
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
MMLongBench PDFs out of Git. Files committed before those rules existed (the
ViDoRe Arrow cache, `OmniDocBench.json`, one MMLongBench PDF) remain tracked
until the owner decides otherwise. Removing them from tracking would keep the
local copies but make fresh clones re-download them.

Anything committed here is redistributed publicly. Check each dataset's
licence before committing more of its files.
