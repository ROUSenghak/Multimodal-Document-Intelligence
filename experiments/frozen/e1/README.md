# Frozen E1 result: page-image resolution (512 px vs 768 px)

**Question.** On the same annotated evidence pages, with the same model, prompt and
scorer, does rendering pages with a 768-px instead of a 512-px short side improve
answer accuracy enough to justify the extra input-token cost?

**Answer (for this model and question set).** Yes. The pre-registered rule says
**adopt 768 px**.

| | 512 px, run 1 | 512 px, run 2 (identical repeat) | 768 px, run 1 |
|---|---:|---:|---:|
| correct answers (score > 0) | 10/37 (27.0%) | 11/37 (29.7%) | 16/37 (43.2%) |
| mean benchmark score | 0.270 | 0.297 | 0.425 |
| cites at least one page | 36/37 | 36/37 | 37/37 |
| all cited pages supplied, given a citation | 34/36 (94.4%) | 34/36 | 33/37 (89.2%) |
| cites an evidence page | 35/37 | 35/37 | 35/37 |
| mean input tokens | 21,630 | 21,630 | 45,830 |
| list-price cost, 37 questions | $0.121 | $0.121 | $0.255 |
| median live latency | 1.30 s | 1.21 s | 1.68 s |

- **Paired 512 → 768 (run 1):** 6 fixed, 0 broken, 10 both correct, 21 both wrong.
  The difference is 6/37 = 0.162. Leave-one-document-out gives 0.121–0.194. The
  document-cluster bootstrap gives [0.081, 0.296]. Exact McNemar p = 0.031,
  which ignores clustering.
- **Repeat (512 px run 1 vs run 2):** correctness changed for 1/37 questions
  (`mmlb-0313`). The parsed answer changed for 5/37 and the reply text for 9/37.
- **Decision rule (frozen in the spec before any call).** Each criterion and its outcome:
  - gain ≥ 0.05: passes (0.162);
  - gain > the repeat's correctness-change rate: passes (0.027);
  - incremental cost ≤ $0.10 per extra correct answer: passes ($0.134 / 6 = $0.022).

  Verdict: `adopt_768_for_this_model_and_population`.

Model `gpt-4o-mini-2024-07-18` (served as requested, one system fingerprint
`fp_9483e83037`), `detail: high`, temperature 0, 400 output tokens, prompt
`mmlb-image-v1` (hash `35ff2e8b91f9`). The questions are the 37 of the 40
answerable questions in the fixed 6-document MMLongBench-Doc subset whose
evidence pages fit the 128k context at both resolutions. Three questions, with
5, 10 and 13 evidence pages, were excluded before any call.

## What higher resolution changed

- **Improved:** small printed values that are illegible at 512 px:
  - a valuation difference on a slide chart (`0033`) and a blog count on a slide (`0737`);
  - a count of illustrated postures (`0094`) and a measurement (`0095`, partial
    ANLS credit) in a watch guidebook;
  - a step number in a manual's figure (`0313`);
  - a percentage difference from a report chart (`0359`).

  Four of these fixes (`0033`, `0094`, `0095`, `0737`) had the *same* wrong
  512-px answer in both runs; they are the strongest evidence. `0313` is also
  fixed by the identical 512-px repeat, so it is within run-to-run variation.
  Under a stricter rule counting only score = 1, which is not the frozen rule,
  the gain is 5/37.
- **Unsolved:** 21/37 questions are wrong at both resolutions. They are mostly
  counting, aggregation and chart-reasoning failures (the arXiv paper stays at
  0/6).
- **Trade-offs:** input tokens rise 2.12× on average: 1.79× for most pages,
  2.59× for wide 16:9 slides (2 → 6 high-detail tiles). Cost and context use rise
  in proportion; median latency rises from about 1.3 s to 1.7 s. There are two
  more off-by-one page citations. Every invalid citation, at either resolution,
  is exactly one page below a supplied page: the printed page number is cited
  instead of the `[Page N]` tag.

## Limitations

1. **Small, clustered sample.** 37 questions in 6 documents, so one question is
   0.027. The intervals and the p-value are descriptive, not confirmatory.
2. **Narrow scope.** One deprecated model snapshot (API shutdown 2027-01-14),
   oracle evidence pages only, answerable questions only, two resolutions. Above
   768 px this model downscales high-detail input, so 1024 px is not a distinct
   condition for it.
3. **Repeat variability is probably understated.** OpenAI's prompt cache served
   20 of the 37 repeated requests. Those reproduced the first reply more often
   (18/20) than uncached ones (10/17); cache use is confounded with time since
   the first request. Two runs give an observed margin, not a variance estimate.
4. **Local scoring.** The rule-based scorer re-implements MMLongBench-Doc
   without its GPT-4o extraction step. "Correct" means score > 0, so it includes
   one partial ANLS match. These are not leaderboard numbers.
5. **Costs are list-price upper bounds.** If cached input tokens are billed at
   half price, the full run cost about $0.47 rather than $0.50. All three E1 runs
   (smoke, pilot, full) cost about $0.59 at list price.
6. **Code revision.** The full run executed notebook code that was committed
   only afterwards, in `4d202d5`, 16 minutes after the run ended. That commit
   contains the executed notebook, with outputs naming this run. The run's
   records use fields that exist only in that code, and all 113 requests are
   rebuilt byte for byte today. The executed source is therefore identified
   with high confidence but not bound to it by a hash. Library versions were not
   recorded at run time. Details are in `PROVENANCE.json`.

## Contents

| Path | Content |
|---|---|
| `run_20261121T131525011829Z_29c92c8a_full/` | Byte-identical copy of the run directory. It holds the settings, spec snapshot, execution plan, request estimates, execution log (113 records in call order: timestamps, image hashes, token usage, fingerprints, cache provenance), response cache, smoke gate and records, completion record, the three prediction files, and the run's own `evaluation_summary.json` and summary figure. |
| `tables/per_question.csv` | One row per question: reference, the three replies, scores, citations, tokens, latency, transitions. |
| `figures/fig1`–`fig6` (`.png` at 300 dpi, `.pdf`) | Accuracy, paired outcomes, by document, repeat variability, citations, accuracy versus cost. They are produced by `notebooks/03_evaluation.ipynb` section 13. |
| `PROVENANCE.json` | Run timing and usage, spec and code revision, environment, supporting runs, external artifacts, audit. |
| `SHA256SUMS` | Checksums of every file above. |

The run files contain model replies, image hashes and the system prompt, but no
question text, page images, Base64 payloads or credentials. `per_question.csv`
contains MMLongBench-Doc reference answers (CC BY-NC 4.0, research use).

## Verify and reproduce (no API call)

```bash
cd experiments/frozen/e1 && shasum -a 256 -c SHA256SUMS
```

Then run notebooks 00 → 03 (README at the repository root). Notebook 02 in its
default offline mode rebuilds the 113 requests and asserts that their
fingerprints and cache keys equal the logged ones. Notebook 03 evaluates this
frozen run by default:
- it re-derives the run's `evaluation_summary.json` exactly;
- it runs the integrity audit (section 12);
- it asserts the regression references (10/37, 11/37, 16/37; 6 fixed, 0 broken;
  1 repeat flip; adopt);
- it redraws the figures into `data/processed/mmlongbench_doc/e1/figures/`.

The regenerated PNG and PDF bytes can differ across matplotlib versions, so the
figures are checked by eye, not by checksum; the per-question table is checked
byte for byte.

**Not in git**, because it is regenerable or rights-restricted: the 94 page
images actually sent (17.2 MB) and the 6 PDFs (about 23 MB). Their integrity is
anchored by the image SHA-256 hashes in the execution log and by the pinned
dataset revision. The smoke and pilot runs stay in git-ignored
`experiments/runs/e1/`; their checksums are in `PROVENANCE.json`.

## Independent audit (2026-11-21)

Recomputed from the raw files, separately from the evaluation code (only the
frozen scoring rule was shared). 55/55 checks passed:

- **Accounting.** All 113 planned calls are present once, in plan order, live,
  with one attempt each. Prediction files equal their log records, and the
  cache holds one entry per call.
- **Requests.** Cache keys equal SHA-256(run:replicate:fingerprint). The
  repeated 512-px requests share fingerprints with run 1 but have distinct cache
  keys, so no reply was reused. All 113 fingerprints recomputed from the current
  images and prompt match.
- **Responses.** Observed prompt tokens are expected + 1 for every call.
- **Results.** Scores, transitions, bootstrap, leave-one-out, citations, tokens,
  cost, latency and verdict all match `evaluation_summary.json`.
- **Baseline.** The frozen baseline (`../mmlongbench_doc/`, 29 files) is
  unchanged.
