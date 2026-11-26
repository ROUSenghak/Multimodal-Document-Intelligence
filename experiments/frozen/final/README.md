# Final held-out evaluation (test pool, used once)

This package is the immutable final evaluation: the single reader session on the untouched MMLongBench-Doc test pool, its smoke run, and the evaluation under the frozen rules.

**Protocol.**
- Spec: `experiments/specs/final_evaluation_v1.json` (commit `1c54a3e`, approved by the owner before any pool access).
- Deviations D1–D2: `experiments/specs/final_evaluation_v1_deviations.md`, each committed before any result it could affect.
- Index: `../final_index/`, frozen before any question was read.
- Retrieval: `../final_retrieval/`.
- Plan: `experiments/specs/final_evaluation_v1_plan.json`.

## Population

- **Documents:** 110 MMLongBench-Doc documents. The pool is every document outside the 20 used in development (E0–E9), minus the 4 whose questions were seen earlier and `mi_phone.pdf` (D1: its served bytes differ from the pinned revision).
- **Questions:** all 872 of them, 674 answerable and 198 unanswerable, with no question-level filter.

## Arms

All arms use the same reader (`gpt-6-luna`, contract b1, temperature 0, reasoning effort none). Only the pages differ.

| Arm | Pages | Role |
|---|---|---|
| **B1** | ColQwen2 v1.0 top 4 | the selected system |
| **T1** | OCR + BM25 top 4 | text-retrieval baseline, confirmatory contrast |
| **A1** | ColQwen2 top 8 when the frozen E9 trigger U3 fires (335 questions), otherwise B1's reply | secondary contrast only |

## Results (S-v1, primary)

| Claim | Result | Verdict |
|---|---|---|
| **C1** B1 accuracy, answerable | **288 / 674 = 0.427**, document-cluster 95 % CI [0.386, 0.470] | development estimate 0.451 (46/102) |
| C1 on the core scope (born-digital financial, research and administration documents) | 77 / 207 = 0.372 [0.305, 0.443] | — |
| **C2** B1 − T1 (confirmatory) | **+0.119** [+0.088, +0.150]; sign-flip p = 1.0e-05; 103 fixed / 23 broken | **`visual_retrieval_confirmed`** |
| **C3** A1 − B1 (secondary) | +0.021 [+0.007, +0.036]; p = 0.0046; 19 fixed / 5 broken | `a1_gain_supported`. Reported only: the shipped system stays B1 |

**Secondary metrics.**

| | B1 | T1 | A1 |
|---|---:|---:|---:|
| Correct abstentions / 198 | 120 | 140 | 121 |
| Citation validity | 1.000 | 0.995 | 0.999 |
| Mean prompt tokens | 4,198 | 4,199 | 5,671 |
| Latency p50 / p90 (s) | 2.5 / 5.1 | 2.4 / 4.7 | 3.0 / 6.6 |

**Evidence retrieval at k = 4** (666 answerable questions with annotated evidence):

| | ColQwen2 | BM25 |
|---|---:|---:|
| Evidence recall | 0.711 | 0.543 |
| Complete evidence | 0.626 | 0.459 |

ColQwen2 − BM25 recall is +0.168 [+0.130, +0.207]. The development figures were 0.721 and 0.526 (E5).

**S-v2 (secondary).** 85 arm-blind gray items await the owner's labels (`adjudication/blind_queue_unlabelled.csv`).
- Over every consistent correct/wrong labelling of them, B1 − T1 stays within [+0.077, +0.150] and A1 − B1 within [+0.015, +0.028]. With "unsure" also allowed, the upper ends rise to +0.159 and +0.031.
- No labelling can reverse either sign. Under the worst case for C3, its sign-flip p is 0.049 (independent audit).

**Deviation D2.** The frozen S-v1 copy crashes on a non-numeric reply to a `$`-formatted Float reference. Such replies score 0, as in the official MMLongBench-Doc code.
- **Effect:** 2 replies, the B1 and T1 replies to one question (`mmlb-1087`).
- **Impact on the claims:** none on C2, where both arms score 0. That question is one of C3's 19 fixed pairs; without it, C3 is +0.019, p = 0.008, still supported.
- **Historical scores:** the wrapper reproduces all 708 frozen E8 and E9 S-v1 scores exactly.

## Interpretation

1. **The project's central result replicates out of sample.** Visual page retrieval beats OCR + BM25 by 11.9 points of answer accuracy, with the same reader, on 110 documents never used in development. The development estimate (E6) was +12.7. At the retrieval level, ColQwen2 supplies 16.8 points more annotated evidence than BM25. The gain is positive in every document type, from +0.026 on financial reports to +0.245 on tutorials. By evidence source it is larger on figures (+0.171) than on plain text (+0.112) or tables (+0.077), and it is larger on image-heavy documents (+0.180) than on born-digital ones (+0.091). These subgroup figures are descriptive; the 4 questions on documents over 200 pages are too few to read.
2. **B1's held-out accuracy is 42.7 %**, slightly below its development estimate of 45.1 % and inside its interval. More than half of answerable questions remain wrong. Accuracy falls with the number of evidence pages: 54 % for single-page evidence, 13 % for 4+ pages.
3. **E9's adaptive policy shows a small, statistically supported gain on held-out data:** +2.1 points, 19 fixed / 5 broken. Development data (102 questions) could not resolve it.
   - **It is fragile.** It rests on 24 disagreements, it is one run per arm, so reader noise is not part of the test, and its p is 0.049 under the worst-case S-v2 labelling.
   - It remains below E9's pre-registered +0.05 materiality, and by the frozen rule B1 stays the shipped system.
   - Any adoption would be a new decision for future work, not something tuned on this pool.
4. **T1 abstains correctly more often (140 vs 120 of 198).** Its pages more often lack the evidence, so it says "Not answerable" more often, which helps on unanswerable questions. Answerable accuracy, the primary metric, is what the claims rest on.

## Limitations

- **One run per arm.** E8 measured 4–7 flips between identical replicates on 102 questions. The C2 effect (80 net questions) is far larger, while C3 (14 net questions) is closer to that noise.
- **Single-annotator evidence; an aliased reader without a snapshot.** Frozen replies define the result.
- **The token model undercounts some prompts.** It computes `floor(1.2 × tiles)` in floating point, which for 24 × 35 tiles gives 1007.999… → 1007 instead of 1008. So 49 calls were billed 1–8 more prompt tokens than planned (146 tokens, about $0.000015). Costs are computed from billed usage, so no figure is affected. Future plans should compute `(12 × tiles) // 10` in integers; the frozen plan is unchanged.
- **The core-scope subgroup has only 32 documents.**
- **The test pool is now used.** It may be reported, but never used to tune a system again.

## Contents

| Path | Content |
|---|---|
| `run_…_full/` | byte-identical append-only execution log (loggable requests, raw replies, usage, served identity), settings with the full plan, summary |
| `smoke_…_smoke/` | the 6-call development smoke run and its gate |
| `tables/evaluation_per_question.csv` | per question and arm: S-v1 score and exception kind, S-v2 class and final label, citations, abstention, tokens, cost, latency. No reply text |
| `tables/evaluation_summary.json` | arms, C1–C3, S-v2 ranges, retrieval, subgroups, D2 counts, cost |
| `adjudication/blind_queue_unlabelled.csv` | the 85 arm-blind S-v2 items |
| `adjudication/sealed_key.csv` | the arm mapping; **do not open before labelling** |
| `AUDIT.json`, `audit/` | the independent audit |
| `PROVENANCE.json` | commits, runs, identity, cost |
| `SHA256SUMS` | checksums of every file except itself |

**Cost.** $0.990233 for the run plus $0.003216 for the smoke = **$0.993449** of the $2.50 ceiling. All 2,085 calls succeeded on the first attempt.

Notebook 09 reproduces the evaluation from this package in its default `offline` mode, with no API call. Never edit this directory.
