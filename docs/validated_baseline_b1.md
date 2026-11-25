# The validated baseline (B1)

**Status:** frozen 2026-11-25. Evidence: E1–E8, all development data.
**Population for every number below:** 118 questions (102 answerable, 16 unanswerable) across 14 MMLongBench-Doc documents. The final test pool has never been run.

---

## 1. What B1 is

```
PDF ──► page images (768 px short side)
          │
          ▼
    ColQwen2 v1.0 ── MaxSim over every page ──► ranked pages
          │
          ▼
    context guard ──► top 4 pages (3 when the budget is tight)
          │
          ▼
    one reader call (gpt-6-luna, temperature 0, reasoning_effort none)
    strict JSON schema: {answer, cited_pages, evidence[{page, quote}]}
          │
          ▼
    answer + page citations + verbatim quotes, or "Not answerable"
```

Five decisions, each the survivor of a pre-registered experiment:

| Component | Choice | Decided by |
|---|---|---|
| Page rendering | 768 px short side, image only (no OCR text in the prompt) | E1, E3 |
| Retrieval | ColQwen2 v1.0, MaxSim late interaction over page images | E5, E6 |
| Reading | **one** call over the retrieved pages | E7 |
| Reader | `gpt-6-luna`, temperature 0, strict JSON schema, 800 output tokens | E8 |
| Output contract | B1 v2: answer + cited pages + evidence quotes + explicit abstention | E8 |

---

## 2. What the evidence supports, and how strongly

### Statistically supported

**Visual retrieval beats OCR + BM25.** This is the project's one strong, replicated result, and it holds at both the retrieval and the answering layer.

| | OCR + BM25 | ColQwen2 | Difference (document-cluster 95%) |
|---|---:|---:|---|
| Evidence recall after the guard (E5, 101 held-out q) | 0.526 | 0.721 | **+0.195 [+0.110, +0.309]** |
| Answer accuracy end to end (E6, 102 q) | 25/102 | 38/102 | **+0.127 [+0.074, +0.193]** |
| Same, under S-v2 | 28/101 | 39/101 | +0.109 |

Supporting checks: E6 fixed 13 questions and broke **0**; the document sign-flip test gives one-sided p = 0.00098; leave-one-document-out keeps the gain between +0.113 and +0.149. E5's gain holds on 12 of 14 documents and on none is it negative. The gain concentrates where OCR is weakest — figures 0.40 → 0.85, layout text 0.45 → 0.76, OCR'd pages 0.49 → 0.85 — and is near zero on plain text (0.66 → 0.68).

**Per-page extract-then-answer is worse than one-shot.** A supported *negative* result, which is why B1 reads in a single call.

| E7 arm | Accuracy | vs one-shot |
|---|---:|---|
| V0 (one-shot) | 38/102 | — |
| X4 (extract per page, then answer) | 31/102 | **−0.069, CI95 [−0.135, −0.008]**, 3 fixed / 10 broken |
| X8 (same, 8 pages) | 29/102 | −0.079, 4 fixed / 12 broken |

The interval excludes zero on the negative side. Mechanism: per-page extraction discards visual and layout information (signatures, colours, chart counts, flowchart order).

### Not statistically supported — report as non-inferiority only

**The reader migration and the B1 contract.** Both deltas have intervals that straddle zero.

| Contrast | S-v1 | S-v2 | Interval (S-v1) |
|---|---|---|---|
| New reader vs frozen GPT-4o-mini, same contract | 42 vs 38 /102 | — | [−0.045, +0.138] |
| B1 contract vs old contract, same reader | 46 vs 42 /102 | 47 vs 44 /101 | **[−0.019, +0.098]** |

And the decisive caution: **two identical B1 replicates (same pages, same contract, temperature 0) differ by 1 question but flip 7 individual questions between them** under S-v2 (4 under S-v1). The +2 to +3 question margin sits inside that churn.

> **State B1 as: non-inferior to the previous contract, with 100% structurally valid citations and one additional correct abstention, at no measured accuracy cost.** It is *not* a demonstrated accuracy improvement. Any write-up that reports "46 vs 42" as better answering overstates the evidence.

What B1 *does* buy, and these are measured, not inferred:

- **Citation validity 1.000** in all three arms — every cited page was one of the pages actually supplied, and no reply cited a page without giving evidence for it.
- **Correct abstentions 9/16**, against 8/16 for the old contract.
- **Schema validity 118/118** per replicate; 354/354 calls returned `finish_reason: stop` with no parse error.

### Supporting decisions, smaller evidence

| Experiment | Verdict | Caveat |
|---|---|---|
| E1 image resolution | `adopt_768` — 10/37 → 16/37, 6 fixed / 0 broken | 37 questions, development |
| E3 text–image fusion | `retain_image_only_768` — text 13, image 17, both 16 /37 | image vs both is within noise; both clearly beat text alone |
| E4 application end to end | `page_selection_costs_accuracy` — app 11/40, oracle pages 17/37 | page selection costs accuracy, but reading still loses about three times more: even on oracle pages only 17/37 are correct (`experiments/frozen/e4/README.md`) |

---

## 3. The honest ceiling

B1 answers **46 of 102** answerable development questions (S-v1), **47 of 101** (S-v2). Roughly **55%** of answerable questions are still wrong. Two measured reasons:

1. **Evidence is still missing.** ColQwen2 supplies all annotated evidence for 61/101 questions and some for 86/101. The remaining gap is an upper bound on what any reader can do.
2. **Grounding is weak even when the answer is right.** The strict grounding diagnostic — quotes actually supported by the cited page, and numeric claims traceable — passes only **70/118** replies (59.3%): quotes supported on 88/118, numeric support on 25/53 applicable.

Point 2 is the single most actionable finding in E8, and it is the motivation for E9. Note it is a *diagnostic*, deliberately kept outside E8's decision rule — it was not a post-hoc gate.

---

## 4. What this baseline does not claim

- **It is a development result.** 14 documents, 118 questions. The test pool (115 documents and 916 questions; 111 documents and about 880 questions once the four touched documents are excluded) is untouched and must be used once, against frozen configurations, under its own approved specification.
- **The reader is an alias, not a snapshot.** `gpt-6-luna` returns no system fingerprint. The **frozen replies**, not the model name, define this baseline. A change in served model or fingerprint is a new condition.
- **S-v1 is primary and is never re-labelled.** S-v2 is reported beside it. One item (`mmlb-1013`) carries an inherited `unsure` and is excluded from S-v2, giving a denominator of 101.
- **Scoring is itself approximate.** Across the two adjudication rounds, human judgment disagreed with the automatic scorer on 13 of 58 gray arm-cells. That is why every result carries both scorers.

## 5. Known operational risks

| Risk | State |
|---|---|
| `gpt-4o-mini-2024-07-18` shuts down 2027-01-14 | Migration already done and measured (E8). Only the legacy `--live` path depends on it. |
| 11 of 24 source PDFs are macOS `dataless` placeholders | Cached 768 px renders are intact and were sufficient for E8 and adjudication. Re-materialize before any run needing the originals. |
| Replicate churn of 7 questions at temperature 0 | Any future experiment claiming a gain under ~7 questions needs replicates, not a single run. |

---

## 6. Provenance

| Artifact | Location |
|---|---|
| E8 execution and S-v1 verdict | `experiments/frozen/e8/` (commit `0d68a93`) |
| E8 S-v2 blind labels | `experiments/frozen/e8_scoring_v2/` (commit `bedb8f3`) |
| E5 / E6 / E7 frozen results | `experiments/frozen/e5/`, `e6/`, `e7/` |
| S-v2 labels for E6/E7 | `experiments/frozen/scoring_v2/` |
| Reproduction | `notebooks/07_baseline_consolidation.ipynb`, `VISUALDOC_QA_MODE=replay` (no API call) |
| Regression guards | `tests/test_b1.py` (137 tests pass) |
