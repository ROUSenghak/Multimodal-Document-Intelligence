# Final held-out evaluation: specification (approved 2026-11-25; frozen JSON in `experiments/specs/final_evaluation_v1.json`)

**Status.** Approved by the owner on 2026-11-25: arms B1, T1 and secondary A1; ceiling USD 2.50; laptop indexing. Frozen as `experiments/specs/final_evaluation_v1.json`, which takes precedence over this draft wherever they differ.

**Sources of pool information used here:** only `experiments/test_pool_ledger.md` (frame-level counts) and the published benchmark statistics.

---

## 1. What the final evaluation must answer

| | Claim | Type |
|---|---|---|
| **C1** | B1's answer accuracy on documents never used in development, with its uncertainty: the headline number | estimate |
| **C2** | Visual retrieval (ColQwen2) beats OCR + BM25 retrieval end to end on held-out documents, with the same reader and contract | **confirmatory test**: the project's one strong development result (E5, E6), re-tested once |
| C3 | Abstention, citation validity and evidence-retrieval recall of B1 on held-out documents | secondary estimates |
| C4 | Where B1 fails: prespecified subgroups only | descriptive |

No per-question error analysis is ever done on the pool (ledger rule 3). Subgroup results are descriptive and never used to change the system.

## 2. Population

- **Documents.**
  - Start from every MMLongBench-Doc document (revision `2ff6aa92…`).
  - Drop the 20 documents used in E0–E9.
  - Drop the 4 pool documents whose questions were seen (`PH_2016.06.08_Economy-Final.pdf`, `05-03-18-political-release.pdf`, `2312.04350v3.pdf`, `RAR.pdf`).
  - That leaves **111 documents**, with **no page cap and no file-size filter**. This applies the owner's decision of 2026-11-25: whole benchmark, with prespecified subgroups.
- **Questions.** Every question of those documents, answerable and unanswerable, with no question-level filter. Expected: about 880 of the pool's 916 (exact count computed by code at freeze, without displaying any row).
- **Size estimate.** At the published average of about 47–49 pages per document, roughly 5,300 pages (uncertain by ±1,000). The longest known pool document has 468 pages.

## 3. Frozen configurations (run in one session)

| Arm | Retrieval | Pages | Reader and contract | Role |
|---|---|---|---|---|
| **B1** | ColQwen2 v1.0 (`ddc07d23`), MaxSim over every page | top 4 | `gpt-6-luna`, `reasoning_effort` none, temperature 0, contract `b1` (strict schema), 800 output tokens, 768-px renders | the selected architecture |
| **T1** | Native text + Tesseract OCR below 30 words (150 dpi), BM25 k1 1.5, b 0.75 | top 4 | identical to B1 | text-retrieval baseline |

- **Same reader in both arms.** T1 differs from B1 only by the retriever, which is exactly the E6 contrast, re-tested out of sample.
- **E9 did not adopt a policy** (`no_meaningful_gain`, 2026-11-25), so B1 is the selected architecture, unchanged.
- **Optional third arm, A1 (owner's choice, secondary only).** E9's adaptive policy was directionally positive on development data: +0.025 with 5 fixed and 0 broken, but underpowered. With about 880 questions the final evaluation could settle the question. If it is included:
  - A1 reads ColQwen2's top 8 pages when U3 ≥ −0.153079 (frozen), and otherwise reuses B1's reply. That is about 40 % extra calls.
  - It is reported as a pre-registered secondary contrast, A1 − B1.
  - **The shipped system stays B1 whatever A1 scores.** Choosing a configuration after seeing test results would bias the held-out estimate.
- **One replicate per arm.** With about 880 questions, E8's replicate churn (4 S-v1 flips per 102) is small relative to the expected effect.
- **Order.** The order of questions and arms is seeded and counterbalanced.

## 4. Scoring

- **S-v1** (notebook 03 cell `f653d232`, correct = score > 0) is **primary** and decides every claim.
- **S-v2** is reported beside it.
  - Gray replies go to an arm-blind queue for the owner.
  - Until labelled, S-v2 is reported as an interval (pending counted wrong / counted correct).
  - **No model judgment replaces a human label.**
  - Expected queue: about 10 % of answerable replies, or roughly 150 distinct items. That is about 2–3 hours of the owner's time; optional for the verdict.
- **Answer accuracy** is reported on answerable questions. **Correct abstention** is reported on unanswerable ones.

## 5. Statistics and decision rules (fixed before any pool access)

- **Unit and clustering.** The unit is the question, clustered by document (about 111 clusters).
- **Intervals.** Document-cluster percentile bootstrap, 10,000 draws, seed fixed at freeze.
- **Paired test.** Document sign-flip test, Monte Carlo with 100,000 draws (2¹¹¹ patterns cannot be enumerated). McNemar is reported as descriptive.
- **C2 decision.**
  - `visual_retrieval_confirmed` if Δ = acc(B1) − acc(T1) > 0, the one-sided 95 % bootstrap lower bound is > 0, and the sign-flip p ≤ 0.05.
  - `visual_retrieval_not_confirmed` if the interval includes 0.
  - `reversed` if the upper bound is < 0.
- **C1.** Accuracy with its 95 % cluster interval, overall and on the core scope (born-digital financial, research and administration documents). It is compared descriptively with the development estimate (46/102 = 0.451).
- **Guardrails** (reported, not a gate): schema validity ≥ 0.99; citation validity ≥ 0.95; one served model and system fingerprint for the whole run (otherwise stop).

**Prespecified subgroups (descriptive).**
- Document type (7 types).
- Core scope vs other.
- Document length: ≤ 50, 51–200 and > 200 pages. "> 200" lies outside the product contract.
- Evidence span: 1, 2–3 and 4+ pages.
- Evidence source: text, layout, table, chart, figure.
- Answer format.
- Born-digital vs image-only.

## 6. Budget and compute

| Item | Estimate | Notes |
|---|---|---|
| Reader calls (B1 + T1) | about 880 × 2 = about 1,760 calls | about 3,980 prompt tokens per call (E8/E9 measured) |
| Expected cost (B1 + T1) | **about $0.75** | at $0.10 / 1M input and $0.50 / 1M output, about 50 output tokens per call |
| Optional A1 | about 350 extra 8-page calls, **about $0.28** expected | about 7,640 prompt tokens per call (E9 measured) |
| Upper bound | about $1.45 without A1, about $1.85 with it | full 800-token output allowance on every call |
| **Proposed ceiling** | **$2.00 without A1, $2.50 with it; cumulative, fail-closed** | smoke included |
| ColQwen2 indexing | about 5,300 pages | **laptop:** about 12.5 s per page, so about 18 h, plus 4.4 GB of weights, about 1 GB of embeddings and the PDFs. That does not fit in the 6.1 GB free today. **SSP Cloud GPU:** under 1 h |
| OCR + BM25 indexing | CPU only | OCR only on pages with fewer than 30 native words |

**Execution order after approval:**
1. Commit the frozen spec.
2. Download the pool PDFs at the pinned revision and record their checksums.
3. Index with ColQwen2 and BM25. Indexing is question-independent and reads no question.
4. Freeze the index checksums.
5. Load the questions.
6. Build and fingerprint every request offline.
7. Run the smoke, then the full run.
8. Score blind with S-v1, and queue S-v2.
9. Run an independent audit.
10. Freeze the package.

## 7. What the owner must decide

1. **Approve this specification**, including its use of the pool once and irreversibly.
2. **Authorise the budget:** a ceiling of $2.00.
3. **Choose the indexing compute:**
   - free about 10 GB on the laptop, so that the local run takes about 18 h unattended; or
   - run notebook 09's indexing section on SSP Cloud and copy back the embeddings, about 1 GB.
4. **Optionally, label the S-v2 queue blind** afterwards (about 150 items).
