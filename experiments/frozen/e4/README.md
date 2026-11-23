# Frozen E4 result: the application, end to end

**Question.** On the 57 questions of the 6-document MMLongBench-Doc subset, how accurate is the
application in `src/visualdoc/` as shipped? It uses BM25 top 5, the context guard (3–4 pages kept),
768-px page images and GPT-4o-mini. And on the 37 matched questions, how much of its error comes
from **page selection** rather than from **reading** the pages it is given?

**Answer (for this application and question set, in-sample).**

- The application answers **11/40** answerable questions correctly.
- The same reader on the annotated evidence pages answers **17/37**.
- The pre-registered rule says **`page_selection_costs_accuracy`**, by one question.
- Reading still loses about three times more than page selection.

| | APP (application) | ORACLE (evidence pages) | frozen E1_768 (same requests as ORACLE, 2026-11-21) | frozen B (512 px, 5 pages) |
|---|---:|---:|---:|---:|
| answerable, 40 | **11/40** (0.275; cluster 95 % 0.13–0.43) | — | — | 7/40 |
| matched, 37 | 11/37 | **17/37** | 16/37 | — |
| all 57: accuracy / F1 | 0.293 / 0.235 | — | — | — |
| correct abstention, 17 unanswerable | 6/17 | — | — | 6/17 |
| citations valid | 47/57 (8 of 10 invalid are off by one) | — | — | — |
| mean prompt tokens / list price per question | 105,333 / $0.0158 | 45,830 / $0.0069 | — | — |

- **Primary (ORACLE − APP, paired, same session).**
  - 8 fixed, 2 broken, 9 both correct, 18 both wrong.
  - Δ = +6/37 = 0.162; the document-cluster bootstrap gives [0.09, 0.26]; exact McNemar p = 0.11 (ignores clustering).
  - Reading loss: 1 − ORACLE = 20/37.
- **Decision rule (frozen before any call).**
  - Δ ≥ 0.05: passes.
  - Δ > max(1/37, ORACLE vs E1_768 change rate 5/37) = 0.135: passes, by 1/37.
  - broken ≤ fixed / 2: passes.
- **Where the gap is.**
  - All 8 fixed questions lack some or all of their evidence: 3 not retrieved, 1 dropped by the guard, 4 incomplete.
  - With all evidence supplied, APP scored 10/20 and ORACLE 8/20, so distractor pages showed no measurable cost.
- **Robustness (post hoc, not part of the verdict).**
  - The frozen E1_768 replies answered the identical ORACLE requests on another day and another backend (`fp_9483e83037`; E4 ran on `fp_e7d4fdcd1d`).
  - With E1_768 in ORACLE's place, the gap is 5/37 with 0 broken.
  - Five questions are fixed against both sessions: `0037`, `0727`, `0740` (retrieval) and `0096`, `0359` (incomplete evidence).
  - The other 3 fixed and both broken questions are ORACLE's cross-session flips.
- **Sensitivity.** S1 0.171, S2 0.182, S3 0.162; never changes the verdict.

## Failure analysis (diagnostic hypotheses, not demonstrated causes)

The 29 answerable APP errors split as follows:

- **Page selection** (mechanical, from the evidence group):
  - 7 retrieval: no evidence page in the BM25 top 5;
  - 3 context guard;
  - 4 incomplete evidence.
- **Reader** (ORACLE also wrong), by manual label:
  - 8 reasoning or aggregation;
  - 3 visual reading;
  - 4 annotation or scoring issues (`0733` and `0034` are right in substance).

None of the errors points to the text layer.

**Behaviour.**

- The application never said "Not answerable" when no evidence page was sent (0/11).
- It answered 11 of the 17 unanswerable questions, usually with the answer to their answerable twin.

## How it was run

- **Model.** `gpt-4o-mini-2024-07-18`: Chat Completions, temperature 0, 400 output tokens, JSON mode, image detail high, prompt `mmlb-image-v1`.
- **APP requests.** Captured from `visualdoc.pipeline.answer_question` with `OfflineReader`, then sent through the application's own `ask`.
- **ORACLE requests.** Byte-identical to the frozen E1_768 requests.
- **Specification.** `experiments/specs/e4_application_end_to_end_v1.json` was frozen and committed with the implementation in `72791e9` before the smoke run (ceiling $1.50). Paid modes refused to run unless the spec, notebook 02's code and `src/visualdoc/` equalled that commit.
- **Smoke run.** 2 calls on `mmlb-0095`, the largest request: 110,733 prompt tokens.
- **Full run.** The smoke pair again, then 37 adjacent counterbalanced APP/ORACLE pairs (19 open with APP) and 20 APP-only questions, in one seeded order.
- **Result of both runs.** 98/98 replies `ok`, finish `stop`, from the pinned snapshot. No retry, no 429. Billed prompt = expected + 1 on every call.
- **Cost.** $1.2006 at list price for both runs (≈ $1.167 with cached input at half price).

## Limitations

1. **In-sample.** E1–E3 chose the application's resolution, model and representation on these 37 questions.
2. **Small, clustered sample.** 37 paired questions in 6 documents; one question is 0.027, and the margin decision turned on one question.
3. **Variability.** APP was not repeated. The margin comes from one cross-day ORACLE comparison that also spans a backend change.
4. **The primary gap mixes** missing evidence, extra pages, page order and request length. The evidence groups separate only the first.
5. **Manual labels.** 14 of the 15 reader labels were carried over from the frozen evidence-page review after checking each reply against its description. Page images were not re-inspected.
6. **Annotations.** The evidence-page annotations are single annotations, and some references are unscorable or questionable (S1, S2).
7. **One snapshot,** shut down on 2027-01-14.
8. **Local scoring.** The rule-based MMLongBench-Doc scorer, re-implemented: these are not leaderboard numbers.

## Contents

| Path | Content |
|---|---|
| `run_20261123T000439244313Z_ea059977_smoke/` | Byte-identical copy of the smoke run (11 files): settings, spec snapshot, plans, session record, smoke gate, log, cache, predictions, completion record. |
| `run_20261123T000625940289Z_15119ec0_full/` | Byte-identical copy of the full run (13 files), same layout, with the `main_r1` APP (57) and ORACLE (37) predictions. |
| `tables/evaluation_summary.json` | All results of notebook 03 §17: accuracy, primary, cross-session check, decision, evidence groups, behaviour, hypotheses, sensitivity, cost, manual review, robustness, backends, spend. |
| `tables/per_question.csv` | One row per question: evidence group, both replies, scores, citations, abstention, frozen anchors, diagnostic hypothesis. |
| `AUDIT.json` | The independent audit: 35 checks and the recomputed results. |
| `PROVENANCE.json` | Timing, tokens, backends, cost, spec and code revision, environment, what was added after the freeze, what cannot be verified. |
| `SHA256SUMS` | Checksums of every file above. |

The run files contain model replies, page numbers, image hashes and the system prompt. They contain no question text, page images, Base64 payloads or credentials. `per_question.csv` contains MMLongBench-Doc reference answers (CC BY-NC 4.0, research use).

## Verify and reproduce (no API call)

```bash
cd experiments/frozen/e4 && shasum -a 256 -c SHA256SUMS
```

Then run notebooks 00 → 03. Notebook 03 §17 evaluates this frozen run by default:

- it verifies `SHA256SUMS`;
- it re-derives `evaluation_summary.json` exactly and `per_question.csv` byte for byte;
- it asserts the regression references: APP 11/40, ORACLE 17/37, 8 fixed / 2 broken, margin 5/37, `page_selection_costs_accuracy`, $1.2006.

## Independent audit (2026-11-23)

A standalone script outside the notebooks recomputed every check from this frozen copy. It shared only the frozen scoring-rule cell (`f653d232`). All 35 checks passed:

- **Specification and code.** The snapshot equals the tracked spec and the copy in `72791e9`. That commit precedes the first request. Notebook 02's code cells and the application modules on disk still equal it.
- **Plan.** Re-derived from the spec seeds and equal to both run plans: 2 smoke, 37 adjacent pairs (19 APP-first), 20 singles.
- **Requests.** All 57 APP requests were rebuilt through `answer_question` (no network). Fingerprints, pages and image SHA-256 equal every logged APP record. The ORACLE records carry the frozen E1_768 fingerprints and pages. The top 5 equals frozen condition B. The sent fingerprint equals the planned one on all 98 calls.
- **Accounting.** One live, first-attempt `ok` record per item in plan order. The cache and prediction files equal the log, and cache keys are run-scoped.
- **Responses.** Every raw reply re-parses with the application's parser. The pinned snapshot served all replies. Billed prompt = expected + 1 on all calls and below the application bound.
- **Costs.** Recomputed list prices equal `completion.json`; the cumulative $1.2006 is within $1.50.
- **Results.** Rescored counts, fixed and broken questions, gap, margin, verdict, McNemar p, both cluster bootstraps, leave-one-document-out, accuracy and F1 on 57, S1–S3, behaviour counts, diagnostic hypotheses, the per-question table and the manual-review queue all match notebook 03.
- **Hygiene.** No credential-like strings or Base64 payloads.
