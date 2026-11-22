# Frozen E3 result: text–image fusion with GPT-4o-mini at 768 px

**Question.** On the 37 matched questions and their annotated evidence pages, does
adding the extracted page text (native text layer, or OCR when a page has fewer
than 30 native words) to the 768-px page images improve GPT-4o-mini's answer
accuracy over the images alone?

**Answer (for this pipeline and question set).** No. The pre-registered rule says
**retain images only at 768 px** (`retain_image_only_768`). Adding the text
changed two questions for the worse and one for the better; that is a tie
within noise, not evidence that text hurts.

| | text only (T) | images only (I) | images + text (IT) | IT repeat | frozen E1 768 px |
|---|---:|---:|---:|---:|---:|
| correct answers (score > 0) | 13/37 | **17/37** | **16/37** | 16/37 | 16/37 |
| strict accuracy (score = 1) | 0.324 | 0.432 | 0.405 | 0.405 | 0.405 |
| false abstention | 0.162 | 0.000 | 0.027 | 0.027 | 0.000 |
| citation validity (given a citation) | 1.000 | 0.946 | 1.000 | 0.972 | 0.892 |
| off-by-one citations | 0 | 2 | 0 | 1 | 4 |
| mean input tokens | 788 | 45,849 | 46,430 | 46,430 | 45,830 |
| list-price cost, 37 questions | $0.005 | $0.255 | $0.258 | $0.258 | $0.255 |

The last column is the frozen E1 run (`../e1/`): the same images under the old
image-only prompt. It is a descriptive anchor, never part of the verdict.

- **Primary (IT vs I, paired, same session):**
  - 1 fixed (`mmlb-0362`), 2 broken (`mmlb-0094`, `mmlb-0729`), 15 both correct, 19 both wrong;
  - the difference is −1/37 = −0.027;
  - the document-cluster bootstrap gives [−0.11, +0.06];
  - exact McNemar p = 1.0, which ignores clustering.
- **Decision rule (frozen in the spec before any call).**
  - gain ≥ 0.05: fails;
  - gain > max(1/37, IT repeat change rate 0/37) = 0.027: fails;
  - broken ≤ fixed / 2: fails.

  Because the gain is ≤ 0, the verdict is `retain_image_only_768`.
- **Sensitivity (never changes the verdict).** S1 (without the 2 unscorable
  references), S2 (without the 4 annotation or scoring issues) and S3 (strict
  accuracy) each give 1 fixed and 2 broken.
- **Secondary.** Images beat text (I − T: 6 fixed, 2 broken, +0.108); fusion
  also beats text (IT − T: 4 fixed, 1 broken, +0.081). The image is the
  stronger single source on these questions.
- **Repeat.** The IT repeat, 65 min after the last main reply, was fully cold
  (0/37 calls with cached tokens). Correctness changed for 0/37 questions, the
  parsed answer for 2/37 and the reply text for 3/37.

## What happened where the sources disagree

- **Complementarity is real but not exploited.** T or I is right on 19
  questions; IT reaches 16 of them and adds no question that both got wrong
  (synergy 0, interference 3).
- **When T and I give different answers and IT is wrong, IT gave T's answer in
  8 cases.** Where IT gave T's answer on a disagreement, it was right 1 time in
  9. The extracted text pulls the fused reader toward its errors:
  - `mmlb-0729`: OCR reads Lufthansa's 12 tweets as "42", so the text sums to
    71; T and IT answer 71, I answers 41 (reference 41);
  - `mmlb-0094`: a count in the watch guide; I counts 8 (correct), T says 1,
    IT says 6.
- **The one fix** (`mmlb-0362`, a percentage difference) is a question where the
  text is right and the image reader is not.
- **Citations.** With labelled text, invalid "printed page number" citations
  disappear (I: 2 off-by-one, IT: 0).

## How it was run

- **Model.** `gpt-4o-mini-2024-07-18` (Chat Completions, temperature 0,
  400 output tokens, JSON mode, image detail high). Every reply was served by
  the pinned snapshot.
- **Requests.** One neutral prompt (`mmlb-evidence-v1`) for all three
  conditions. Per page: `[Page N]` tag, then the image (I, IT), then the text
  (T, IT). I equals IT minus the text parts and T equals IT minus the image
  parts, object for object. The images are byte-identical to the frozen E1
  768-px request; every page text is sent in full (no truncation) and pinned by
  SHA-256 in the spec.
- **Order.** The three conditions of a question were sent as an adjacent,
  counterbalanced triplet; the 37 triplets in seeded random order.
- **Specification.** `experiments/specs/e3_text_image_fusion_v1.json` was frozen
  and committed with the implementation in `a433f13`, before the smoke run.
- **The run.** 151 replies (3 smoke, 111 main, 37 repeat), no failure, no rate
  limit, every reply parsed, none truncated.
- **Cost.** $0.784 at list price for this run (cached input counted at the full
  price, as in the spec's budget guard); $0.910 for all three E3 runs (smoke,
  pilot, full), within the approved $1.25.

## Limitations

1. **Small, clustered sample.** 37 questions in 6 documents: one question is
   0.027. Intervals and the p-value are descriptive. A tie means no large
   effect, not equivalence.
2. **Oracle pages only.** The result says nothing about fusion when retrieval
   is imperfect, and abstention on unanswerable questions is not measured.
3. **One fusion layout and one prompt.** Ordering and conflict-resolution
   instructions were not varied.
4. **OCR quality is part of the pipeline.** On OCR documents the text can be
   wrong (`mmlb-0729`) and mislead the fused reader.
5. **One snapshot**, deprecated and shut down on 2027-01-14.
6. **Margins, not variances.** One cold IT repeat and the frozen 512-px
   GPT-4o-mini repeat; I is not repeated.
7. **Prompt change.** E3's neutral prompt differs from E1's image prompt, so
   I vs frozen E1 768 (17 vs 16) mixes prompt wording and session; it is
   descriptive only.
8. **Local scoring.** The rule-based scorer re-implements MMLongBench-Doc
   without its GPT-4o extraction step; these are not leaderboard numbers.
9. **No manual review.** Notebook 03 queues 14 questions for manual review;
   none was labelled before freezing. The mechanical taxonomy in
   `evaluation_summary.json` is not a substitute.

## Contents

| Path | Content |
|---|---|
| `run_20261122T143134629529Z_4c62bfc2_full/` | Byte-identical copy of the 18 run files: settings, spec snapshot, plan, request plan, session record (environment, code commit), smoke gate, repeat-wait record, execution log (151 replies), response cache, completion record, seven prediction files, and `evaluation_summary.json` written by notebook 03. |
| `tables/per_question.csv` | One row per question: reference, the five replies, scores, citations, transitions, subgroups. |
| `figures/fig1`–`fig4` (`.png`, `.pdf`) | Accuracy and paired effects; per-question outcomes; complementarity and citations; documents and subgroups. Produced by `notebooks/03_evaluation.ipynb` section 15. |
| `AUDIT.json` | The independent audit: 55 checks and the recomputed results. |
| `PROVENANCE.json` | Run timing, tokens and cost, spec and code revision, environment, what cannot be verified, supporting runs and their checksums. |
| `SHA256SUMS` | Checksums of every file above. |

The run files contain model replies, image and text hashes and the system
prompt, but no question text, page images, Base64 payloads or credentials.
`per_question.csv` contains MMLongBench-Doc reference answers (CC BY-NC 4.0,
research use).

## Verify and reproduce (no API call)

```bash
cd experiments/frozen/e3 && shasum -a 256 -c SHA256SUMS
```

Then run notebooks 00 → 03. Notebook 03 evaluates this frozen run by default:
it verifies `SHA256SUMS`, re-derives `evaluation_summary.json` exactly and
`tables/per_question.csv` byte for byte, asserts the regression references
(T 13, I 17, IT 16, repeat 16; 1 fixed, 2 broken; retain), and redraws the
figures into `data/processed/mmlongbench_doc/e3/figures/`. PNG and PDF bytes
can differ across matplotlib versions, so figures are checked by eye.

## Independent audit (2026-11-22)

A standalone script outside the notebooks recomputed every check from the raw
files of this frozen copy. It shared only the frozen scoring-rule cell
(`f653d232`), unchanged since before E2. All 55 checks passed:

- **Specification and code.** The snapshot equals the tracked spec and the copy
  in `a433f13`; that commit precedes the first request; the run records it; the
  notebook-02 code cells at HEAD equal those at `a433f13`.
- **Plan.** 151 items: 3 smoke, 37 adjacent (T, I, IT) triplets with each of
  the 6 orders used 6 or 7 times, then 37 repeats.
- **Accounting.** One live, first-attempt, `ok` record per planned item in plan
  order; prediction files and cache equal the log; cache keys are
  SHA-256(run:replicate:fingerprint) and the repeat never reuses a main key.
- **Responses.** Every raw reply re-parses to the logged answer and citations;
  the pinned snapshot served every reply, all with finish reason stop; the sent
  fingerprint equals the planned one.
- **Requests.** Pages and images equal the frozen E1 768-px request; texts
  equal SHA-256 of the page text in `pages.parquet` and the spec hashes; T has
  no image and I no text; the repeat shares main IT's fingerprint.
- **Timing and caching.** The repeat started 65.0 min after the last main reply
  and no repeat call reported cached tokens.
- **Costs.** Recomputed list-price costs equal `completion.json` for this run
  and the cumulative total of all E3 runs; both within budget.
- **Results.** Counts, fixed and broken questions, secondary pairs, repeat
  changes, margin, verdict, leave-one-document-out, the bootstrap interval,
  S1–S3 and the per-question table all match notebook 03.
- **Hygiene.** The run files contain no credential-like strings.
