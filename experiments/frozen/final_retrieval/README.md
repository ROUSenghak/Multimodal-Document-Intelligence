# Frozen final-evaluation retrieval

These are the rankings the final evaluation reads from. They were computed once, on the Apple M1 machine that encoded the pages (notebook 09, `queries` mode), after the index was frozen in `../final_index/` (commit `ab8a9c8`). No reader call has been made.

## Contents

| File | Content |
|---|---|
| `rankings.parquet` | per pool question: document, page count; the full ColQwen2 ranking and MaxSim scores (`V_*`) and the full BM25 ranking and scores (`A_*`); U3 and whether the frozen trigger fires. No question text |
| `query_manifest.csv` | per question: the SHA-256 of the question text and of its ColQwen2 query-embedding file |
| `SHA256SUMS` | checksums of every file above |

## Checks that passed before freezing

- **Parity gate.** Bitwise E5 reproduction, re-run in `queries` mode.
- **Development retrieval.** All 118 development questions' ColQwen2 and BM25 rankings equal E5's frozen rankings at every position. The maximum score difference is 5.0e-07.
- **Requests.** All 118 development B1 requests built from the raw question text equal the frozen E8 L-B1 requests.

## Numbers

| | |
|---|---|
| Questions | 872 in 110 documents (674 answerable, 198 unanswerable) |
| U3 trigger | fires on 335 questions (38.4 %; development 39.8 %) |
| Plan | 2,079 calls: B1 872, T1 872, triggered 8-page 335 |
| Plan upper bound | $1.831161, frozen in `experiments/specs/final_evaluation_v1_plan.json` |

On another machine, notebook 09 uses these rankings and only checks that its recomputed scores are consistent with them within 1e-4. Never edit this directory.
