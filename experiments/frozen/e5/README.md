# Frozen E5 result: visual retrieval against OCR + BM25

**Question.** Does a pretrained visual page retriever put more annotated evidence in front of GPT-4o-mini than the application's OCR + BM25 retriever?

The comparison is made under the application's real constraint: the top 5 after the context guard, which keeps 3–4 pages at 768 px.

**Answer (held-out, 101 questions in 14 MMLongBench-Doc documents never used before).** Yes, by a wide and consistent margin.

- The pre-registered verdict is **`visual_improves_evidence`**.
- It leads to a controlled end-to-end answering experiment (E6), **not** to integration.

| after the context guard | A: OCR + BM25 (application) | V: ColQwen2 v1.0 | V − A (document-cluster 95 %) |
|---|---:|---:|---:|
| **Evidence recall (primary)** | **0.526** | **0.721** | **+0.195 [+0.110, +0.309]** |
| Any evidence supplied | 66/101 | 86/101 | +0.198 [+0.102, +0.325] |
| All evidence supplied | 42/101 | 61/101 | +0.188 [+0.099, +0.308] |

- **Tests.**
  - The exact document-level sign-flip test gives p = 0.0005, the smallest value possible here: all 12 documents with a difference favour V.
  - McNemar on "any evidence" counts 23 questions gained against 3 lost, p < 0.001.
  - Leave-one-document-out keeps the gain between +0.172 and +0.229.
- **Per document.** V is better on 12 of the 14 held-out documents and worse on none.
- **Ranking metrics** all agree: Recall@5 0.556 → 0.762, MRR 0.539 → 0.770, nDCG@5 0.482 → 0.709.
- **Development set** (exploratory; in-sample for E1–E4): evidence supplied for 29/40 → 38/40 questions, recall 0.608 → 0.826. Arm A reproduces notebook 01 and E4 exactly.
- **Fusion (exploratory).** Reciprocal-rank fusion of A and V (k = 60) is worse than V alone: −0.090 [−0.183, −0.026].
- **Where the gain sits** (descriptive only):
  - figures (0.40 → 0.85);
  - layout text (0.45 → 0.76);
  - OCR'd pages (0.49 → 0.85);
  - little on plain text (0.66 → 0.68) and tables (0.45 → 0.53).
- **Where both fail.** 9 of the 12 questions that both arms miss are on two 10-K filings, and 7 of those ask for a derived figure (EBITDA, return on assets) whose inputs sit in statement tables that never name it.

## How it was run

- **Specification.** `experiments/specs/e5_visual_retrieval_v1.json`, committed in `073d0a4` before any visual score existed. `spec_snapshot.json` is a byte-identical copy.
- **Arm A.** The application's retriever, unchanged:
  - native text, with Tesseract OCR below 30 words;
  - BM25 with k1 1.5 and b 0.75;
  - top 5 → guard.
- **Arm V.** `vidore/colqwen2-v1.0-hf` @ `ddc07d23`, with weights SHA-256 `2f6dbf32…`.
  - It is **ColQwen2**, not ColPali: the same method and training data on a Qwen2-VL-2B backbone.
  - transformers 5.23.0, Apple M1 GPU (MPS), bf16.
  - The input is the application's 768-px page image, with the processor's defaults (≤ 768 visual tokens).
  - Scoring is MaxSim over every page; the same guard follows.
- **Two passes.** On an 8 GB machine the model runs in two passes (vision tower, then language model). These give embeddings **bit for bit** equal to the single-pass forward, checked before the freeze and again in every execution.
- **Held-out selection.** Two documents per type, seeded, at most 100 pages each; 647 pages in all. The documents do not overlap the development set or any document previously named in the repository.
- **Annotation spot check.** 8 seeded questions were checked before any score: 6 supported, 2 partly.
- **Cost.** No API call and no spend.
  - On this fanless M1: 12.5 s per page to index (9.8 s vision + 2.7 s language), 0.16 s per query and about 4 ms to score a document.
  - Embeddings take 193 KB per page, and the weights 4.4 GB.
  - Details are in `PROVENANCE.json`, including two interruptions (a sleep and a session end), both resumed from checkpoints.

## Limitations

1. **Retrieval, not answers.** E4's reader answers 17/37 questions even with every evidence page, so more evidence is necessary for better accuracy, not sufficient.
2. **Small, clustered sample.** 101 questions in 14 documents. Documents over 100 pages were excluded, and per-group figures rest on 3–36 questions.
3. **Possible training overlap.** ColQwen2's training data (DocVQA, InfoVQA, TAT-DQA, arXivQA, web PDFs) may overlap held-out pages. This cannot be checked, and an overlap would favour V.
4. **One model and configuration.** ColPali v1.3 and ColQwen2.5 are untested; BM25 is untuned, as shipped.
5. **Single annotations.** An unannotated page that also answers the question counts as a miss for both arms.

## Contents

| Path | Content |
|---|---|
| `spec_snapshot.json` | Byte-identical copy of the frozen spec |
| `tables/summary.json` | All results: per-arm means, paired statistics, decision, categories, spot check, regression values |
| `tables/per_question.csv` | One row per evidence question (141): annotations (pages, sources, format; no question or answer text), every metric per arm, top 5 and supplied pages |
| `tables/rankings.parquet` | The full ranking and scores of every arm for all 175 questions |
| `tables/encoding_log.csv` | Per-page and per-query encoding times (two sessions) |
| `tables/render_manifest_heldout.csv` | Size and SHA-256 of every held-out page image |
| `tables/run_context.json` | Environment, encoder configuration, cost table, peaks, single-pass check |
| `figures/e5_evidence_after_guard.png` | Evidence supplied per arm (held-out) and per-document change |
| `AUDIT.json` | The independent audit: 34/34 checks and the recomputed results |
| `PROVENANCE.json` | Timeline, versions, interruptions, changes after the freeze, what cannot be verified |
| `SHA256SUMS` | Checksums of every file above |

No page image, question text, reference answer, embedding or credential is stored here. MMLongBench-Doc annotations are CC BY-NC 4.0, for research use.

## Verify and reproduce (no API call)

```bash
cd experiments/frozen/e5 && shasum -a 256 -c SHA256SUMS
```

Run notebooks 00 → 04. Notebook 04:
- re-executes the held-out selection rule;
- checks arm A against the frozen E0/E4 runs;
- re-ranks from cached embeddings, or re-encodes them: about 3 hours on an M1, minutes on a GPU, with a 4.4 GB download;
- requires `summary.json`, `per_question.csv` and all 525 rankings to regenerate **exactly**.

## Independent audit (2026-11-23)

A standalone script outside the notebooks recomputed the result from this copy, the processed inputs, the embedding cache and the application modules. It shares no code with notebook 04. All 34 checks passed:

- **Spec and timing.** The spec equals its freeze commit, which precedes the first encoding session.
- **Arm A is the application.** On all 647 held-out pages: the application's `extract_pages` gives the same text, `render_pages` the same image bytes, `BM25Index` the same rankings, and `select_pages_within_context` (on the real PNGs) the same supplied pages.
- **Arm V.** NumPy MaxSim reproduces every ranking, with scores within 8e-6. Arm H is the stated RRF.
- **Metrics and statistics.** Every per-question metric (0 mismatches) is recomputed. So are the means, the bootstrap interval (plus a second implementation agreeing within 0.003), the sign-flip and McNemar p-values, and the verdict.
- **Hygiene.** Ranking code reads no annotation column; notebook 04 does not import `src/visualdoc`; the frozen files contain no credentials, Base64 or question text.

The first audit run found one real defect: a 40-character question fragment in `run_context.json`. It was fixed, and the file regenerated. The audit also corrected a tolerance error in its own code. Both are recorded in `AUDIT.json`.
