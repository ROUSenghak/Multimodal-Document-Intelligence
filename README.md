# VisualDoc AI — Multimodal Document Intelligence

**Objective.** Answer questions about digital and scanned PDF documents from
text and visual evidence, cite the pages used, and measure when page images
help compared with extracted text.

The project has three parts, one notebook stage each (plus evaluation):

1. **Document processing**: inspect each PDF page, extract native text, use OCR
   when there is no text layer, render page images, and store page records.
2. **Retrieval and question answering**: rank the pages of a document for a
   question (BM25), then answer from the top pages with an LLM (text) or a
   VLM (page images), returning a structured answer with cited pages.
3. **Evaluation**: retrieval quality, answer correctness, citation validity,
   abstention, paired comparisons between conditions, error analysis and cost.

> **Status.** A complete, reproducible baseline on a 6-document subset of the
> public benchmark [MMLongBench-Doc](https://huggingface.co/datasets/yubo2333/MMLongBench-Doc)
> (57 questions). All four conditions have been run with gpt-4o-mini; their
> predictions are frozen in the repository and are re-evaluated without API
> calls. The project's own annotated question set
> (`data/annotations/questions.csv`) is still empty.

## Research question and design

With the same model, questions and pages, does sending **rendered page
images** instead of **extracted text** improve answers and citations? Only the
evidence representation changes between conditions:

| | Retrieved pages (BM25 top 5) | Oracle pages (annotated evidence, padded to 5) |
| --- | --- | --- |
| **Extracted text** (native + OCR) | **A** | **C** |
| **Rendered page images** (≈ 60 dpi) | **B** | **D** |

The oracle column separates "the retriever missed the page" from "the model
misread the page".

## Results (development subset, local scoring)

6 documents, 57 questions (40 answerable), `gpt-4o-mini-2024-07-18`,
temperature 0, one run per condition.

| | A text, retrieved | B images, retrieved | C text, oracle | D images, oracle |
| --- | --- | --- | --- | --- |
| correct, answerable | 7/40 (0.175) | 7/40 (0.175) | 9/40 (0.225); 9/38 on D's questions | 11/38 (0.289) |
| accuracy, all 57 / F1 | 0.263 / 0.165 | 0.228 / 0.156 | — | — |
| correct abstention (17 unanswerable) | 8/17 | 6/17 | — | — |
| citation validity | 1.000 | 0.895 | 1.000 | 0.921 |
| mean prompt tokens per question | ≈ 1.9k | ≈ 71k | ≈ 1.8k | ≈ 71k |

Retrieval: BM25 Recall@5 **0.689** and Hit@5 **0.800** with the OCR fallback,
against 0.358 Recall@5 on native text only and 0.176 for a random ranking.

What the evidence supports (all exploratory: 38–57 questions in 6 documents):

- **Text reading, not retrieval, limits the text pipeline.** Supplying the
  evidence pages fixes 2 text answers out of 33 errors.
- **Images trade errors rather than reduce them** on the retrieved pages
  (3 fixed, 3 broken). They recover values that OCR destroyed on slide decks,
  and they lose small detail at the resolution gpt-4o-mini's token cost allows.
- **The image reader benefits more from correct pages** (4 fixed, 0 broken,
  from retrieved to oracle pages).
- **Images abstain less, in both directions**, and sometimes cite the page
  number printed on the page instead of the supplied `[Page N]` tag.
- Hypotheses: images better than text on retrieved pages (H1) and a larger
  gain on charts and figures (H2) are **not supported**. Images better on
  oracle pages (H3) shows a consistent direction but is **not established**
  (6 fixed, 4 broken, McNemar p = 0.75).

Answer scores re-implement the benchmark's rule-based scorer with structured
JSON answers instead of its GPT-4o extraction stage, so they are **local
diagnostics, not leaderboard numbers**. Details, limitations and the manual
error review are in `notebooks/03_evaluation.ipynb`.

## Workflow

Run the notebooks in order. Each one reads only the saved files of the
previous ones (never their variables) and states its inputs and outputs at the
top.

| Notebook | Purpose | Reads | Writes (git-ignored, regenerable) |
| --- | --- | --- | --- |
| [`00_document_processing`](notebooks/00_document_processing.ipynb) | Pinned questions, seeded subset, page anatomy, native text + OCR fallback, page-number checks, page rendering | MMLongBench-Doc question table (tracked) and PDFs (downloaded at a pinned revision) | `data/processed/mmlongbench_doc/{questions,pages}.parquet`, `render_manifest.csv`; PNGs in `data/cache/` |
| [`01_retrieval`](notebooks/01_retrieval.ipynb) | BM25 by hand and per document, Recall@k / Hit@k against a random reference, OCR ablation, failure cases | 00 outputs | `rankings.parquet`, `retrieval_*.csv` |
| [`02_question_answering`](notebooks/02_question_answering.ipynb) | Page lists for A–D, text and image prompts, token/cost budget, API error handling, response cache, mocked tests, generation | 00–01 outputs, `experiments/frozen/` | `predictions/{A,B,C,D}.jsonl`, `predictions/manifest.json` |
| [`03_evaluation`](notebooks/03_evaluation.ipynb) | Scoring rules, four-condition metrics, paired comparisons, citations, abstention, legibility, error categories, manual review, cost | 00–02 outputs | `evaluation_summary.json` |

**No paid call by default.** `02_question_answering` runs in `replay` mode
unless `VISUALDOC_QA_MODE` is set to `smoke`, `pilot` or `full`. Replay
rebuilds every request (page lists, prompts, parameters, image fingerprints,
token estimates), asserts that it equals what was sent in the frozen runs, and
reuses those replies. `03_evaluation` then reproduces the table above and
checks it against the frozen files.

## Setup

Tested with Python 3.12.6 on macOS (Apple Silicon).

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt          # project, notebooks (incl. offline API tests) and pytest
python -m ipykernel install --user --name visualdoc-venv --display-name "VisualDoc (.venv, Python 3.12)"
cp .env.example .env                     # only for live API runs
```

OCR uses the Tesseract engine built into PyMuPDF with the model in
`resources/tessdata/`; no system Tesseract is needed. Notebook 00 downloads
6 PDFs (≈ 22 MB) from Hugging Face and OCRs 120 pages (≈ 1 minute).

```bash
pytest                                   # 18 tests: parsing module and annotation schema
jupyter lab notebooks/                   # then run 00 → 01 → 02 → 03 with the visualdoc-venv kernel
```

For a live run, set `OPENAI_API_KEY` and `VISUALDOC_QA_MODE` in `.env`, and
always go `smoke` → `pilot` → `full`. A full run costs about $1.10 at list
prices if no image reply is cached.

**Troubleshooting.** `ModuleNotFoundError: No module named 'visualdoc'` while
`pip show visualdoc-ai` works: the editable-install `.pth` file has the macOS
`hidden` flag. Run `chflags nohidden .venv/lib/python3.12/site-packages/*.pth`.

## Repository layout

```text
.
├── notebooks/                 # the four-stage workflow (00 → 03)
├── experiments/
│   ├── frozen/mmlongbench_doc/  # committed canonical predictions and results, with SHA256SUMS
│   └── runs/                  # git-ignored outputs of new live runs
├── data/
│   ├── external/              # MMLongBench-Doc question table (tracked) and PDFs (git-ignored); other benchmarks
│   ├── processed/, cache/     # git-ignored outputs of the notebooks
│   ├── annotations/           # schema and guide for the project's own question set (empty)
│   └── documents/             # three local candidate PDFs, used by the tests
├── src/visualdoc/parsing.py   # tested page-routing baseline (native / OCR / hybrid / review)
├── tests/                     # parsing and annotation-schema tests
├── resources/tessdata/        # Tesseract English model
├── archive/                   # superseded notebooks, course labs, old docs (see archive/README.md)
├── AGENTS.md                  # development policy for coding agents
└── pyproject.toml, requirements*.txt
```

## Implemented versus planned

| Component | Status |
| --- | --- |
| Native text + OCR fallback, page records, rendering | Implemented (00); routing module and tests in `src/` |
| BM25 page retrieval and metrics | Implemented (01) |
| Text and image QA with page citations, four conditions | Implemented and run (02) |
| Evaluation, paired comparisons, error analysis | Implemented (03); manual review partly done (10 questions) |
| Dense or visual retrieval (embeddings, ColPali) | Planned; no model chosen |
| Project's own verified question set | Not started (needs annotation) |
| User interface (e.g. Streamlit) | Deferred until after the experimental phase |

## Data and licensing

MMLongBench-Doc is licensed CC BY-NC 4.0 (research use). Its PDFs are
downloaded on demand into a git-ignored folder. See
[`data/external/README.md`](data/external/README.md),
[`data/annotations/README.md`](data/annotations/README.md) and
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md). Do not commit private or
rights-restricted documents.
