# `experiments/` — evaluation runs

This folder holds the outputs of evaluation runs. The runs themselves are
executed in notebooks under `notebooks/project/` (notebook-first policy, see
`AGENTS.md`).

## Current evaluation: MMLongBench-Doc baseline (notebook 14)

`notebooks/project/14_mmlongbench_doc_benchmark.ipynb` runs a reproducible
development-subset benchmark:

```text
question → BM25 over the page texts of its PDF (native text + OCR fallback) → top-k pages
         → LLM (gated) → {answer, cited_pages} → rule-based score
```

| Measured | Metric | Status in the saved notebook |
| --- | --- | --- |
| Page retrieval | Recall@k and Hit@k for k ∈ {1, 3, 5, 10}, with the exact random-ranking expectation as a reference; native-only versus native + OCR | ✅ measured |
| Answer correctness | local re-implementation of the official rule-based `eval_score` (Int / Float / Str / List / None), accuracy and official F1 | ⏳ gated: needs `VISUALDOC_LLM_MODEL` and `OPENAI_API_KEY` |
| Citations | validity (cited ⊆ supplied pages); correctness (cites ≥ 1 evidence page) | ⏳ gated |
| Abstention | correct `"Not answerable"` on unanswerable questions; false-abstention rate | ⏳ gated |

**Saved retrieval result** (seed 42, 6 documents, 57 questions, 40 in the
retrieval population, dataset revision `2ff6aa92…`):

| k | BM25 native + OCR Recall@k | BM25 native-only Recall@k | random Recall@k |
| --- | --- | --- | --- |
| 1 | 0.346 | 0.200 | 0.035 |
| 5 | 0.689 | 0.358 | 0.176 |
| 10 | 0.809 | 0.474 | 0.352 |

These numbers describe a 6-document development subset. They are not an
estimate for the full benchmark.

### Local scores versus official scores

The official protocol has three stages: a free-form model response, GPT-4o
extraction of a short answer, then rule-based scoring. Notebook 14 keeps
stage 3 and replaces stages 1–2 with a structured JSON answer. Its answer
scores are therefore **local diagnostics** and must not be compared with the
MMLongBench-Doc leaderboard. Parity of the scoring rules was checked against
hand-traced cases from the official source, not by running the official file.

### Reproducing a run

1. `pip install -r requirements.txt` (adds `huggingface_hub`); for answer
   generation also run `pip install -e '.[llm]'`.
2. Optional, for answer generation: in `.env`, set `OPENAI_API_KEY` and
   `VISUALDOC_LLM_MODEL` (and `VISUALDOC_LLM_PROVIDER=openai`).
3. Run the notebook top to bottom with the project kernel. It downloads the
   sampled PDFs (about 22 MB) and OCRs about 120 pages (about 40 s).

Every setting that changes a result (dataset revision, seed, subset size, OCR
threshold, BM25 parameters, k, prompt and its hash, model, temperature) is
defined in one `SETTINGS` cell and saved with the run.

## Folder conventions

- `experiments/runs/<benchmark>/<UTC timestamp>_<config hash>/` holds the raw
  per-run outputs. It is **git-ignored**: raw model output can be large and
  should not be published by accident. Runs with identical configuration share
  the hash suffix. Each run folder contains:
  - `settings.json`: the full configuration, subset ids, prompt, generation status and library versions;
  - `retrieval_per_question.csv` and `retrieval_summary.csv`;
  - `predictions.jsonl`: raw model responses (empty when generation is gated);
  - `errors.jsonl`: API and parse errors;
  - `answer_summary.json`: answer metrics, or `null` with the reason;
  - `scored_predictions.csv`, written only when generation ran.
- `experiments/<name>/summary.*` is for small, reviewed result tables that
  are worth committing. None exist yet.

The controlled text-versus-image comparison on the project's own annotated
set (README §6) is still planned. It needs verified questions in
`data/annotations/questions.csv`.
