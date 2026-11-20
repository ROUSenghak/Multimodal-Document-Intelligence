# `experiments/` — results and runs

| Folder | Tracked | Content |
| --- | --- | --- |
| `frozen/mmlongbench_doc/` | yes | The canonical text run (conditions A, C) and image run (B, D), copied byte for byte, with `SHA256SUMS` and a provenance [README](frozen/mmlongbench_doc/README.md). Never edited. |
| `runs/` | no (git-ignored) | Raw outputs of live runs. New runs from `notebooks/02_question_answering.ipynb` go to `runs/qa/<UTC timestamp>_<mode>/`; the historical runs of the archived notebooks 14 and 15 stay in `runs/mmlongbench_doc/` and `runs/mmlongbench_doc_multimodal/` where they exist. |

## How results are reproduced

```text
00 → pages and images ─┐
01 → rankings ─────────┼─► 02 (replay: rebuild every request, assert it equals the frozen one, reuse the reply)
frozen predictions ────┘        └─► predictions/{A,B,C,D}.jsonl ─► 03 (score, compare, analyse; asserts the frozen numbers)
```

What is verified on every execution, without API calls:

- the document subset, question ids, full BM25 rankings (57/57) and the retrieval table (Recall@5 0.689, Hit@5 0.800) equal the frozen run;
- the 124 page images sent to the model are reproduced byte for byte;
- page lists, both system prompts (hashes `f60729bf0b66`, `35ff2e8b91f9`), generation parameters, token estimates and all 95 image-request fingerprints equal what was sent;
- every per-question score, the four-condition counts (A 7/40, B 7/40, C 9/40, D 11/38) and the five paired summaries equal the frozen files.

What cannot be verified without paying for new calls: whether the model would
give the same replies today. At temperature 0, 3–6 of 57 text predictions
changed between identical runs on 2026-11-19, with no score change; image
run-to-run variation has not been measured.

## Settings that define a run

Defined in one `SETTINGS` cell per notebook and recorded with each live run:
dataset revision `2ff6aa92…`, seed 42, 6 documents ≤ 15 MB, OCR below 30
native words at 150 dpi, BM25 k1 = 1.5 and b = 0.75, top-k = 5, 3,500
characters per text page, render box 512 × 1024 px, `detail: high`, model
`gpt-4o-mini-2024-07-18`, temperature 0, 400 output tokens, prompt versions
`mmlb-structured-v1` (text) and `mmlb-image-v1` (images).
