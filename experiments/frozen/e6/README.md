# Frozen E6 result: visual retrieval, end to end

**Question.** On E5's 118 held-out MMLongBench-Doc questions (14 documents), do the pages ColQwen2 retrieves lead
GPT-4o-mini to more correct answers than the pages the application's OCR + BM25 retrieves? Everything else is held fixed:
reader, prompt, 768-px images, context guard and parser.

**Answer (this population of questions and documents).** Yes. The pre-registered verdict is **`adopt_visual_retrieval`**.

| | A: OCR + BM25 pages | V: ColQwen2 pages |
|---|---:|---:|
| correct, 102 answerable (primary) | 25 (0.245) | **38 (0.373)** |
| correct abstention, 16 unanswerable (G1) | 9 | 7 |
| citation valid and present, 118 replies (G2) | 108 | 107 |
| answer citing an annotated evidence page, 101 | 49 | 67 |
| benchmark accuracy / F1, all 118 | 0.288 / 0.265 | 0.379 / 0.372 |
| list-price cost, 118 requests | $1.827 | $1.827 |

- **Primary (V − A, paired, one session).**
  - Δ = +0.127: 13 fixed, 0 broken, 25 both correct, 64 both wrong.
  - Document-cluster bootstrap (14 documents, 10,000 resamples): 95 % interval [0.074, 0.193], one-sided lower bound 0.082.
  - Exact document sign-flip test: one-sided p = 2⁻¹⁰ ≈ 0.00098. McNemar p = 0.00024, descriptive only because it ignores clustering.
- **Decision rule (frozen before any call).**
  - Accuracy criteria: C1 Δ ≥ 0.05, C2 lower bound > 0, C3 p ≤ 0.05 and C4 broken ≤ fixed / 2 all hold.
  - Guardrail G1 holds **at its limit**: V abstains correctly on 7 of 16 unanswerable questions, against A's 9, and the rule allows V ≥ A − 2.
  - Guardrail G2 holds: valid citations differ by −1/118.
- **Robustness (descriptive).**
  - V ≥ A in all 14 documents, and V > A in 10.
  - Leave-one-document-out Δ ranges from 0.113 to 0.149.
  - Document-weighted Δ is 0.154; without the two 10-K filings, 0.155.
  - Strict scoring gives 0.098 (10 fixed, 0 broken).
- **Mechanism.**
  - 6 of the 13 fixed questions are among the 28 where V supplies more annotated evidence.
  - 7 are among the 68 where both arms supply the same amount.
  - None of the 5 questions where V supplies less evidence was lost.

**Statistical reading versus deployment action (pre-registered).**
- **What E6 shows.** At one-sided α = 0.05, with documents as the unit of inference, V answers more held-out questions correctly than A, by an estimated margin of at least 0.05. This is a claim about this population, not about every document type.
- **What the application does.** ColQwen2 becomes the default retriever in the application phase, with OCR + BM25 as the fallback where the model cannot run. That change to `src/visualdoc/` needs the owner's separate approval (AGENTS.md).

**Efficiency beside quality (E5's measurements, one fanless M1).**
- **API cost:** the same in both arms (same page count and tokens).
- **Indexing:** about 12 s per page image (2.19 h for these 14 documents, 3.0–19.4 min per document), against milliseconds for BM25.
- **Storage:** 124 MB of embeddings (193 KB per page).
- **Model:** 4.42 GB of weights and about 3.3 GB of peak GPU memory.
- **Per question:** 0.16 s query encoding.

The application must therefore index at upload and cache the embeddings.

## How it was run

- **Model.** `gpt-4o-mini-2024-07-18`: Chat Completions, temperature 0, 400 output tokens, JSON mode, image detail high, prompt `mmlb-image-v1`.
- **Pages.**
  - A: BM25 top 5 (k1 1.5, b 0.75).
  - V: ColQwen2 v1.0 top 5 (MaxSim) from E5's frozen rankings, re-derived offline from E5's cached embeddings.
  - Both arms pass through the application's context guard, which keeps 4 pages for 105 questions and 3 for 13. No A request equals its V request.
- **Specification.** `experiments/specs/e6_visual_retrieval_answering_v1.json` was frozen on 2026-11-23 at 19:54 UTC and committed with notebook 05 in `c2ac6e6`. Outputs were recorded in `9b24381`, and both runs executed at that commit. Paid modes refused to run unless the spec and notebook 05's code equalled HEAD. The cumulative ceiling was USD 5.60, retries included.
- **Smoke run.** 2 calls on `mmlb-0068`, the largest request (110,706 prompt tokens per arm).
- **Full run.** The smoke pair again, never scored, then 118 adjacent A/V pairs in one seeded order (59 open with A).
- **Interruption.**
  - After 108 replies the OpenAI credit ran out. The API refused call 109 (`mmlb-1057`, arm A, the first of pair 54) with HTTP 429 `insufficient_quota`. It was not billed.
  - The executor stopped by design and wrote a stop record.
  - After the owner added credit and authorised it, the same run resumed in place 44 minutes later, from the same commit, under the same budget guard. Only the 130 missing items were sent; `mmlb-1057` A was sent as its second attempt.
  - The pause fell between pairs 53 and 54, so every pair stayed adjacent.
- **Backends.** `fp_8b385e4fac` served 221 replies. `fp_b4fe8e4fe2` served the first 17 after the resume (8 complete pairs plus one call; 8 in A, 9 in V).
- **Result of both runs.**
  - 240 of 240 replies `ok`, finish `stop`, from the pinned snapshot.
  - No 429 rate limit, and no retry other than the quota stop.
  - Billed prompt tokens = expected + 1 on every call.
- **Cost.** USD 3.721277 at list price (smoke $0.033278, full $3.687999), against a planned upper bound of $3.8003.

## Limitations

1. **One replicate.** Run-to-run variation at temperature 0 was not measured in E6. Between sessions in earlier experiments, it changed 3–6 of 57 text predictions and the correctness of 5 of 37 image replies.
2. **Small, clustered sample.** 102 questions in 14 documents; the two 10-K filings hold 31. The interval admits a gain as small as +0.07.
3. **The difference mixes** evidence availability with distractor pages and page order. The strata separate the first only.
4. **Training overlap.** ColQwen2 may have seen held-out documents during training, which would favour V. This cannot be checked.
5. **Abstention.** G1 passed at its limit: with ColQwen2's pages the reader answers 2 more unanswerable questions with content.
6. **Efficiency figures** come from E5 on one fanless M1, not from an application.
7. **One snapshot,** shut down on 2027-01-14.
8. **Local scoring.** The rule-based MMLongBench-Doc scorer, re-implemented: these are not leaderboard numbers.

## Contents

| Path | Content |
|---|---|
| `run_20261123T200131832026Z_cbe3025f_smoke/` | Byte-identical copy of the smoke run (11 files): settings, spec snapshot, plans, session record, smoke gate, log, cache, predictions, completion record. |
| `run_20261123T200722253880Z_d94e85f1_full/` | Byte-identical copy of the full run (15 files): the same layout, two session records (start and resume), the stop record of the credit interruption, and the `main_r1` A and V predictions (118 each). |
| `tables/evaluation_summary.json` | Every result of notebook 05 section 7: primary, decision, statistical reading, deployment action, efficiency, per-document, secondary, sensitivity, mechanism. |
| `tables/per_question.csv` | One row per question and arm: group, status, score, correctness, abstention, citation checks, evidence supplied, grounded, supplied pages, tokens, cost, latency. It holds no question, reference-answer or reply text. |
| `AUDIT.json` | The independent audit: 43 checks and the recomputed results. |
| `PROVENANCE.json` | Timing, sessions, the interruption and resume, backends, tokens, cost, spec and code revision, approvals, environment, what was added after the runs, what cannot be verified. |
| `SHA256SUMS` | Checksums of every file above. |

The run files contain model replies, page numbers, image hashes and the system prompt. They contain no question text, page images, Base64 payloads, annotations or credentials.

## Verify and reproduce (no API call)

```bash
cd experiments/frozen/e6 && shasum -a 256 -c SHA256SUMS
```

Then run notebook 05, given the outputs of notebooks 00 and 04. Section 7 evaluates this frozen run by default:

- it verifies `SHA256SUMS`;
- it validates the run (16 checks);
- it re-derives `tables/evaluation_summary.json` and `tables/per_question.csv` byte for byte;
- it asserts the regression references: A 25/102, V 38/102, 13 fixed / 0 broken, one-sided p 2⁻¹⁰, `adopt_visual_retrieval`, USD 3.721277.

## Independent audit (2026-11-24)

A standalone script outside the repository recomputed every check from this frozen copy. It does not import or execute notebook 05. It shared only the frozen scoring-rule cell `f653d232` of notebook 03, and it rebuilt every request through the application (`src/visualdoc`). All 43 checks passed:

- **Specification and code.**
  - The spec snapshot equals the tracked spec and the spec in `c2ac6e6` and `9b24381`.
  - The freeze and run commits precede the first request.
  - All three session records name one clean commit, whose notebook-05 code hash is recomputed.
  - Since the runs, only the evaluation cell `e6-evaluate` has changed; `src/visualdoc/` is unchanged.
- **Population and plan.**
  - 14 documents, 118 questions, 102 answerable, 16 unanswerable, and 101 evidence questions plus `mmlb-0599`.
  - Both plans re-derive from the spec seeds, with 59/59 counterbalanced pairs.
- **Requests.**
  - Page images were taken from the frozen E5 render manifest (SHA-256). The application re-rendered 169 of the 393 pages byte for byte. The other 9 documents' PDFs were offloaded to iCloud and unreadable at audit time.
  - The application's guard on the frozen E5 top 5, `build_request` and `request_fingerprint` reproduce the supplied pages, fingerprints, image hashes, dimensions and prompt-token bounds of all 240 logged replies. The sent fingerprint equals the planned one on every call.
- **Accounting.**
  - One live `ok` record per planned item, in plan order.
  - The single refused attempt is the unbilled quota 429, and the only second attempt is its resend.
  - The stop and completion records are consistent. Cache and prediction files equal the log, and cache keys are run-scoped and unique.
- **Responses and costs.**
  - Every raw reply re-parses with the application's parser.
  - The pinned snapshot served all replies, and billed prompt tokens = expected + 1.
  - Recomputed list prices equal the completion records, for a cumulative $3.721277, within $5.60.
- **Results.** The audit rescored every reply, re-implemented the statistics from the spec text, and re-applied the decision rule. All of the following match notebook 05:
  - the counts, Δ, bootstrap interval, sign-flip p-values, McNemar, document-weighted Δ and leave-one-document-out;
  - G1 and G2, and the verdict;
  - the secondary citation and abstention counts (application citation checker) and the sensitivity analyses;
  - the evidence strata (which also equal the spec's pre-registered transitions), the mechanism table, the per-document table and the per-question table.
- **Hygiene.** No credential-like string, Base64 image payload, annotation field, or question text in any frozen file.
