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
> calls. Experiments E1–E3 (image resolution, a stronger VLM, text–image
> fusion) are frozen with independent audits, and their retained
> configuration is packaged as a small tested application baseline
> (`src/visualdoc/`). The project's own annotated question set
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

## Experiment E1 — image resolution (completed, frozen)

E1 tests the same annotated oracle evidence pages at a 512-px short side and
a 768-px short side. It needs a new matched 512-px control: the frozen D
condition pads oracle evidence to five pages, while five high-detail 768-px
pages plus the unchanged 400-token output allowance exceed GPT-4o-mini's
128k context. The matched preflight retains 37/40 answerable questions and
excludes the three questions with 5, 10 and 13 evidence pages.

**Result** (full run of 2026-11-21, 113 calls, $0.50 at list price; frozen in
[`experiments/frozen/e1/`](experiments/frozen/e1/README.md)):

| | 512 px | 512 px repeat | 768 px |
| --- | --- | --- | --- |
| correct (37 questions, 6 documents) | 10/37 (0.270) | 11/37 (0.297) | 16/37 (0.432) |
| citation validity, given a citation | 0.944 | 0.944 | 0.892 |
| mean input tokens | ≈ 21.6k | ≈ 21.6k | ≈ 45.8k |

Paired: 6 fixed, 0 broken. The identical 512-px repeat changed correctness on 1/37
questions. The pre-registered rule says **adopt 768 px for this model and
question set**, at $0.022 per additional correct answer. Higher resolution fixes
small printed digits, counts and labels. It does not fix the counting and
reasoning failures that make up most remaining errors (21/37 wrong at both
resolutions). The sample is small and clustered, so intervals are descriptive.
An independent audit of the saved run passed. Notebook 02 rebuilds its 113
requests byte for byte, and notebook 03 re-evaluates it with figures; see the
package README for limitations, including how the executing code revision was
established.

The frozen specification is
[`experiments/specs/e1_image_resolution_v1.json`](experiments/specs/e1_image_resolution_v1.json).
Offline rendering, request invariants, decoded image dimensions and hashes,
replicate-isolated cache tests, reproducible randomized ordering, mocked
responses, context feasibility and cost estimation pass.

The primary outcome is the paired answer-accuracy difference. Mean benchmark
score is secondary. A full run adds an independent repeated 512-px control to
estimate run-to-run variability. Requests are adjacent pairs by question with
seeded within-pair order; the run log records timestamps, model/system
fingerprints, token usage and cache provenance. The 8-question pilot validates
technical feasibility only and is not an accuracy estimate.

Upper-bound list cost (including the full 400-token allowance) is about
**$0.0065** for the two-call technical smoke, **$0.0881** for smoke plus the
8-question pilot pair, and **$0.5276** for smoke plus the 37-question main pair
and 37-question repeated control. Actual cost should be lower when replies use
fewer than 400 output tokens.

The 768-px choice is deliberate: GPT-4o-mini high-detail billing
preprocessing does not enlarge the 512-px control and reduces a shortest side
above 768 px to 768. A 1024-px render is therefore not a distinct documented
input treatment for this model. Observed token counts validate the expected
billing accounting; they do not prove the model's internal visual resolution. The pinned
snapshot is deprecated and scheduled for shutdown on 2027-01-14; retain it
for E1 comparability, then treat a newer-model resolution study as a separate
experiment.

## Experiment E2 — a stronger VLM through OpenRouter (done: retain GPT-4o-mini)

**Result (frozen in [`experiments/frozen/e2/`](experiments/frozen/e2/README.md)).**

| | 512 px | 768 px | 768 px repeat |
|---|---:|---:|---:|
| GPT-4o-mini (frozen E1) | 10/37 | **16/37** | |
| Qwen3-VL-8B (E2) | 11/37 | **15/37** | 15/37 |

- **Primary 768-px comparison:** 4 fixed, 5 broken, −0.027, bootstrap [−0.29, +0.22]. That is a tie within noise, and the pre-registered rule **retains GPT-4o-mini at 768 px**.
- **Resolution:** 768 px helps Qwen too (+4 fixed, 0 broken).
- **Repeat:** Qwen's repeat changed no answer's correctness.
- **Cost:** Qwen's 768-px cell cost $0.014 for 37 questions, against $0.255 for GPT-4o-mini.
- **Validation:** the frozen run passed an independent 44-check audit, and notebook 03 reproduces it by default without any API call.
- **Not verifiable:** the hosted weight revision and image preprocessing.


E2 asks whether **Qwen3-VL-8B-Instruct** answers the same 37 questions better
than GPT-4o-mini. Qwen is served through OpenRouter as `qwen/qwen3-vl-8b-instruct`,
pinned to the provider Parasail in BF16, the only endpoint listed on 2026-11-22.
Image resolution is controlled with a 2 × 2 design:

| | 512 px | 768 px |
|---|---|---|
| GPT-4o-mini | frozen E1, 10/37 | frozen E1, 16/37 (comparator) |
| Qwen3-VL-8B | new | new (primary), plus an independent repeat |

- **Same request.** Each E2 request body reuses the E1 request messages that
  GPT-4o-mini answered: the same prompt, page tags, page order and PNG bytes.
  It also keeps temperature 0, the 400-token cap and JSON mode. Only the model
  slug, the cap's parameter name (`max_tokens`) and a provider-pinning block
  (no fallbacks) change.
- **What the hosted API cannot verify.** OpenRouter exposes a slug, a provider
  name and a generation id, not a weight hash. The served weight revision, the
  provider's image resizing, its chat-template rendering and its serving stack
  cannot be checked, and the slug can change later. The only indirect check:
  each reply's prompt-token count must lie within 2 % of the count the shipped
  Qwen processor implies (336–448 visual tokens per page at 512 px, 744–1,032 at
  768 px). This is **less reproducible than self-hosting** the pinned weights,
  which was set aside for simplicity.
- **Decision rule, fixed in advance.** Adopt only if all three hold:
  - the paired gain is ≥ 0.05;
  - it exceeds the larger repeat change rate of the two models;
  - broken ≤ fixed / 2.

  Retain GPT-4o-mini if the gain is ≤ 0; otherwise the result is inconclusive.
- **Cost.** At the 2026-11-22 price ($0.25 / $0.75 per million input / output
  tokens), smoke + pilot + full (133 calls) was estimated at about **$0.04**, with a
  list-price upper bound of about **$0.08**. Actual spend for all four E2 runs
  was **$0.0436**. Paid modes re-check the public price
  listing, and every call is checked against the approved budget.
- **Spec.** [`experiments/specs/e2_stronger_vlm_v2.json`](experiments/specs/e2_stronger_vlm_v2.json),
  frozen on 2026-11-22 with a $1.00 budget. Paid modes refuse to run unless the
  spec is frozen with a budget. It supersedes
  [`v1`](experiments/specs/e2_stronger_vlm_v1.json). v1's smoke and pilot passed,
  but its full run was stopped twice by HTTP 429 "rate-limited upstream". v2
  changes only the execution rules: a 2-s pause between calls, and 429s waited
  out (30–480 s) without using one of a request's two attempts.

```bash
# Offline (default): nothing is sent to OpenRouter
jupyter nbconvert --execute --to notebook --inplace notebooks/02_question_answering.ipynb
# Paid, after approval, one stage at a time (OPENROUTER_API_KEY in .env);
# add VISUALDOC_E2_RESUME_DIR=experiments/runs/e2/<run-id> to resume an interrupted run
VISUALDOC_E2_MODE=smoke jupyter nbconvert --execute --to notebook --inplace notebooks/02_question_answering.ipynb
# Evaluate without any API call: the frozen run by default, or another saved run
VISUALDOC_E2_RUN_DIR=experiments/runs/e2/<run-id> jupyter nbconvert --execute --to notebook --inplace notebooks/03_evaluation.ipynb
```

Answer scores re-implement the benchmark's rule-based scorer with structured
JSON answers instead of its GPT-4o extraction stage, so they are **local
diagnostics, not leaderboard numbers**. Details, limitations and the manual
error review are in `notebooks/03_evaluation.ipynb`.

## Experiment E3 — text–image fusion (done: retain images only)

**Result (frozen in [`experiments/frozen/e3/`](experiments/frozen/e3/README.md)).**
GPT-4o-mini, 768-px page images, the 37 matched questions and their annotated
evidence pages, one shared prompt (`mmlb-evidence-v1`):

| | text only (T) | images only (I) | images + text (IT) | IT repeat |
|---|---:|---:|---:|---:|
| correct (37 questions) | 13/37 | **17/37** | **16/37** | 16/37 |

- **Primary, IT − I:** 1 fixed, 2 broken, −0.027, cluster bootstrap [−0.11, +0.06]. All three criteria of the pre-registered rule fail and the gain is ≤ 0, so the verdict is **retain images only at 768 px**. S1–S3 (known scoring defects, strict scoring) each give 1 fixed, 2 broken.
- **Images are the stronger single source** here (I − T: 6 fixed, 2 broken). Fusion reaches 16 of the 19 questions that T or I answers, with no synergy: where T and I disagree, IT follows the text 9 times and is right once. On OCR documents a misread digit pulls the fused reader to a wrong answer (`mmlb-0729`: OCR reads 12 as "42").
- **Repeat:** 65 min later, fully cold (no cached tokens), 0/37 correctness changes.
- **Cost:** $0.78 for the full run, $0.91 for all three E3 runs (list price; ceiling $1.25).
- **Validation:** an independent 55-check audit; notebook 03 reproduces the result by default without any API call. The 14-question manual-review queue is not labelled yet.

Design in brief: per page, `[Page N]` then the image (I, IT) then the extracted
text (T, IT); I is IT minus its text parts and T is IT minus its image parts,
asserted for every question. Images are E1's exact PNGs; texts are untruncated
and pinned by SHA-256. The T/I/IT requests of a question were sent as an
adjacent, counterbalanced triplet. Spec:
[`experiments/specs/e3_text_image_fusion_v1.json`](experiments/specs/e3_text_image_fusion_v1.json),
frozen and committed with the implementation before the first call.

```bash
# Evaluate without any API call: the frozen run by default, or another saved run
VISUALDOC_E3_RUN_DIR=experiments/runs/e3/<run-id> jupyter nbconvert --execute --to notebook --inplace notebooks/03_evaluation.ipynb
```

## Application baseline (`src/visualdoc/`)

Small reusable modules that answer a question about **any** PDF with the
configuration the frozen experiments retained. The notebooks do not import
them; they stay the record of how each choice was measured.

| Module | Does | Pinned to |
| --- | --- | --- |
| `documents.py` | page text (native layer; full-page OCR at 150 dpi below 30 native words), 768 × 1536-px page PNGs, 1-based page access | notebook 00; tests reproduce E3's pinned page texts and E1's 768-px PNG byte for byte |
| `retrieval.py` | BM25 per document (k1 1.5, b 0.75), ties by page number | notebook 01; tests reproduce the frozen rankings of all 57 questions |
| `answering.py` | image request (`mmlb-image-v1` prompt, GPT-4o-mini, temperature 0, 400 tokens, JSON), context guard, reply parser, one model call through an injected `create` | notebook 02; tests rebuild a frozen E1 request with an identical fingerprint and re-parse all 264 frozen GPT-4o-mini replies |
| `citations.py` | cited pages vs supplied pages: invalid, off-by-one (printed page number), missing citation | notebook 03's definitions |
| `pipeline.py` | PDF → text → BM25 top 5 → images → context guard → answer → citation check; command-line demo | — |

```bash
# Offline demonstration (default): no model is called, the answer is a placeholder
PYTHONPATH=src python -m visualdoc.pipeline data/documents/ch2.pdf "What does Cromwell's rule say about prior probability?"
# Live (paid, sends page images to OpenAI): add --live with OPENAI_API_KEY set
```

- **OCR policy.** The application uses notebook 00's policy, the one behind
  every frozen result. The older routing in `src/visualdoc/parsing.py`
  (NATIVE / OCR / HYBRID / REVIEW by image coverage, OCR at 200 dpi) is kept
  unchanged with its tests but not used: on the vector-outlined benchmark PDF
  `bdf54dxa.pdf` it routes 53 of 54 pages to REVIEW and returns no text, where
  notebook 00's policy recovers a median of 158 words per page.
**Limitations of the application baseline.**

1. **Its default configuration is untested.** The experiments measured BM25
   top-5 pages at 512 px (condition B: 7/40) and 768-px images on annotated
   evidence pages only (E1–E3: 16–17/37). They never measured BM25-retrieved
   pages at 768 px, which is what the pipeline sends. It follows each
   decision, but its accuracy is unknown until that condition is run.
2. **Retrieved pages are truncated to fit the context.** At 768 px a 4:3 or
   US-letter page costs about 25.5k prompt tokens and a 16:9 slide 36.8k, so
   only 4 (or 3) of the 5 retrieved pages fit GPT-4o-mini's 128k context. The
   guard keeps the best-ranked prefix that fits and lists the rest in
   `dropped_pages`; nothing is dropped silently. The cost in retrieval is
   measurable on the benchmark: BM25 Recall@5 0.689 and Hit@5 0.800 fall to
   Recall@3 0.608 and Hit@3 0.725.
3. **A valid citation is not evidence support.** `citations.ok` only checks
   form: every cited page was supplied, and an answer other than "Not
   answerable" cites at least one page. It does not check that the cited page
   contains the answer, and the answer itself is not verified at all. In the
   frozen E0 text condition A, citation validity was 1.000 while 7 of 40
   answers were correct. `cites_evidence` (a cited page is an annotated
   evidence page) is available only when evidence annotations exist, i.e. in
   evaluation, never for a new user PDF.
4. **Engineering gaps.** No retry, rate limiting, response cache or spending
   limit; API errors propagate to the caller. The token estimate uses a fixed
   1,000-token text allowance, which covered all 113 frozen E1 requests but
   is not exact for very long questions.

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
pytest                                   # 82 tests: application modules, parsing module, annotation schema
jupyter lab notebooks/                   # then run 00 → 01 → 02 → 03 with the visualdoc-venv kernel
```

For a live run, set `OPENAI_API_KEY` and `VISUALDOC_QA_MODE` in `.env`, and
always go `smoke` → `pilot` → `full`. A full run costs about $1.10 at list
prices if no image reply is cached.

E1 is gated separately so the frozen baseline can remain in replay mode:

```bash
# Offline validation only (default; no API call)
VISUALDOC_QA_MODE=replay VISUALDOC_E1_MODE=offline jupyter nbconvert \
  --execute --to notebook --inplace notebooks/02_question_answering.ipynb

# Paid modes: run only after explicit approval, in this order
VISUALDOC_QA_MODE=replay VISUALDOC_E1_MODE=smoke jupyter nbconvert --execute --to notebook --inplace notebooks/02_question_answering.ipynb
VISUALDOC_QA_MODE=replay VISUALDOC_E1_MODE=pilot jupyter nbconvert --execute --to notebook --inplace notebooks/02_question_answering.ipynb
VISUALDOC_QA_MODE=replay VISUALDOC_E1_MODE=full jupyter nbconvert --execute --to notebook --inplace notebooks/02_question_answering.ipynb

# Evaluate one immutable saved run without calling the API
VISUALDOC_E1_RUN_DIR=experiments/runs/e1/<run-id> jupyter nbconvert \
  --execute --to notebook --inplace notebooks/03_evaluation.ipynb
```

Each paid E1 invocation creates a unique run directory and refuses to
overwrite an earlier run. `smoke` writes technical verification only;
`pilot` saves selected responses but 03 suppresses performance claims;
`full` is the only mode that writes the repeated-control comparison and the
predefined accuracy–cost decision readout.

**Troubleshooting.** `ModuleNotFoundError: No module named 'visualdoc'` while
`pip show visualdoc-ai` works: the editable-install `.pth` file has the macOS
`hidden` flag. Run `chflags nohidden .venv/lib/python3.12/site-packages/*.pth`
(the flag can come back; `pytest` does not depend on it, and `PYTHONPATH=src`
works for the demo).

## Repository layout

```text
.
├── notebooks/                 # the four-stage workflow (00 → 03)
├── experiments/
│   ├── frozen/mmlongbench_doc/  # committed canonical predictions and results, with SHA256SUMS
│   ├── frozen/e1/             # frozen E1 full run, figures, per-question table, provenance, SHA256SUMS
│   ├── frozen/e2/             # frozen E2 full run, figures, audit, provenance, SHA256SUMS
│   ├── frozen/e3/             # frozen E3 full run, figures, audit, provenance, SHA256SUMS
│   ├── specs/                 # experiment specifications (E1, E2, E3, all frozen)
│   └── runs/                  # git-ignored outputs of new live runs (e1/, e2/, e3/, ...)
├── data/
│   ├── external/              # MMLongBench-Doc question table (tracked) and PDFs (git-ignored); other benchmarks
│   ├── processed/, cache/     # git-ignored outputs of the notebooks
│   ├── annotations/           # schema and guide for the project's own question set (empty)
│   └── documents/             # three local candidate PDFs, used by the tests
├── src/visualdoc/             # application modules (documents, retrieval, answering, citations, pipeline);
│                              #   parsing.py = older page-routing baseline, kept for reference
├── tests/                     # application, parsing and annotation-schema tests
├── resources/tessdata/        # Tesseract English model
├── archive/                   # superseded notebooks, course labs, old docs (see archive/README.md)
├── AGENTS.md                  # development policy for coding agents
└── pyproject.toml, requirements*.txt
```

## Implemented versus planned

| Component | Status |
| --- | --- |
| Native text + OCR fallback, page records, rendering | Implemented (00); application module `documents.py` |
| BM25 page retrieval and metrics | Implemented (01); application module `retrieval.py` |
| Text and image QA with page citations, four conditions | Implemented and run (02) |
| Experiments E1–E3 (resolution, stronger VLM, text–image fusion) | Run, audited and frozen (`experiments/frozen/`) |
| End-to-end application baseline (image answering, citation check) | Implemented with offline tests (`src/visualdoc/`); accuracy on retrieved pages at 768 px not measured |
| Evaluation, paired comparisons, error analysis | Implemented (03); manual review of the E0 queue done (29 cases); E3's 14-question queue not labelled |
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
