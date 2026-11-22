# Frozen E2 result: a stronger VLM (Qwen3-VL-8B) vs GPT-4o-mini

**Question.** Given exactly the page images, prompt and parameters GPT-4o-mini
received in E1, does Qwen3-VL-8B-Instruct answer the 37 matched questions more
accurately at 768 px?

**Answer (for this pipeline and question set).** No. The pre-registered rule says
**retain GPT-4o-mini at 768 px**. The difference is one question, a tie within
noise, not evidence that Qwen reads worse.

| | GPT-4o-mini 512 px | GPT-4o-mini 768 px | GPT-4o-mini 512 px repeat | Qwen 512 px | Qwen 768 px | Qwen 768 px repeat |
|---|---:|---:|---:|---:|---:|---:|
| correct answers (score > 0) | 10/37 | **16/37** | 11/37 | 11/37 | **15/37** | 15/37 |
| mean benchmark score | 0.270 | 0.425 | 0.297 | 0.297 | 0.405 | 0.405 |
| cites an evidence page | 0.95 | 0.95 | 0.95 | 0.89 | 0.86 | 0.84 |
| mean input tokens (own tokenizer) | 21,630 | 45,830 | 21,630 | 763 | 1,474 | 1,474 |
| cost, 37 questions | $0.121 | $0.255 | $0.121 | $0.007 | $0.014 | $0.013 |
| median latency | 1.30 s | 1.68 s | 1.21 s | 0.97 s | 1.29 s | 1.34 s |

The GPT-4o-mini columns are the frozen E1 run (`../e1/`). GPT-4o-mini costs are
OpenAI list prices; Qwen costs are OpenRouter's actual charge.

- **Primary (Qwen 768 vs GPT-4o-mini 768, paired):**
  - 4 fixed, 5 broken, 11 both correct, 17 both wrong;
  - the difference is −1/37 = −0.027;
  - the document-cluster bootstrap gives [−0.29, +0.22], and leave-one-document-out gives −0.13 to +0.03;
  - exact McNemar p = 1.0, which ignores clustering.
- **Decision rule (frozen in the spec before any call).**
  - gain ≥ 0.05: fails;
  - gain > the larger repeat change rate (0.027): fails;
  - broken ≤ fixed / 2: fails.

  Because the gain is ≤ 0, the verdict is `retain_gpt4o_mini_768_reference`.
- **Resolution × model (descriptive).**
  - Qwen 512 → 768: +4 fixed, 0 broken (+0.108);
  - GPT-4o-mini 512 → 768: +0.162;
  - interaction −0.054, [−0.24, +0.14].

  E1's 768-px choice holds for both readers.
- **Repeat.** Qwen's identical 768-px repeat changed correctness for 0/37
  questions, the parsed answer for 1/37 and the reply text for 1/37. GPT-4o-mini's
  512-px repeat changed 1, 5 and 9.

## What differed between the readers

- **Qwen gains:** the arXiv paper (3/6 against 0/6), where GPT-4o-mini fails at
  both resolutions (`0762`, `0766`, `0767`); a count in `bdf54dxa.pdf` (`0315`).
- **Qwen losses:**
  - small-print values on a slide (`0033`) and in a watch guidebook (`0094`), which GPT-4o-mini reads at 768 px;
  - a chart percentage (`0359`);
  - two answer-format cases rather than misreadings:
    - `0037`: a single string "The Economist and TIME" where the reference is a list;
    - `0095`: `2.5` where the reference is "2.5-3cm".
- Under strict accuracy (score = 1) the readers tie exactly. The scorer is
  frozen; formatting is a lead for a future condition, not a correction.

## How it was run

- **Model.** `qwen/qwen3-vl-8b-instruct` through OpenRouter's OpenAI-compatible
  API, pinned to Parasail bf16 with fallbacks disabled; every reply was served by
  Parasail.
- **Request.** Each request reused the frozen E1 messages object for object: the
  same image bytes, prompt and `[Page N]` tags, temperature 0, 400 output tokens
  and JSON mode. Only the slug, the cap's name (`max_tokens`) and the provider
  block differ.
- **Specification.** `experiments/specs/e2_stronger_vlm_v2.json` was frozen and
  committed in `f0f4584` 22 s before the first request. It supersedes v1, from
  which it differs only in execution rules: a 2-s pause between calls, and HTTP
  429 responses waited out without consuming an attempt. v1's full run was
  stopped twice by "rate-limited upstream"; that run is kept, git-ignored, as an
  abandoned record and was never evaluated.
- **The run.** 113 replies (2 smoke, 37 × 512, 37 × 768, 37 × 768 repeat), all
  sent within 9 min 12 s. Three 429s were each waited out once (30 s) and
  retried successfully. Every reply parsed as plain JSON, with no truncation and
  no fence stripping.
- **Cost.** $0.0343 for this run; $0.0436 for all four E2 runs (smoke, pilot,
  abandoned v1 full, this run). OpenRouter's account total matches.

## Limitations

1. **Small, clustered sample.** 37 questions in 6 documents: one question is
   0.027. Intervals and the p-value are descriptive.
2. **Hosted inference cannot be fully verified.** OpenRouter returns a provider
   name and a generation id, never a weight hash. The weight revision,
   quantization kernels, image preprocessing and serving stack behind the slug
   are unknown, and the slug may point elsewhere later.
   - **Indirect check:** every reply's prompt-token count equals, exactly, what
     the reference Qwen3-VL processor (revision `0c351dd0`) implies for the
     intended resolution. This is evidence, not proof.
   - **Determinism:** bitwise determinism at temperature 0 is not guaranteed.
3. **Provider caching.** 13 % of prompt tokens were cache reads, mostly the shared
   system prompt; 5 of 111 main and repeat calls were at least 90 % cached. The
   repeat's stability is therefore unlikely to be a cache artefact, but caching
   could not be disabled.
4. **Comparator margin.** The GPT-4o-mini repeat was measured only at 512 px.
5. **Pretraining exposure.** Qwen3-VL was released after MMLongBench-Doc, so the
   documents may have been seen in training.
6. **Local scoring.** The rule-based scorer re-implements MMLongBench-Doc without
   its GPT-4o extraction step; "correct" means score > 0. These are not
   leaderboard numbers.

## Contents

| Path | Content |
|---|---|
| `run_20261122T120924635816Z_4f2e1369_full/` | Byte-identical copy of the 15 run files: settings, spec snapshot, plan, request plan, session record (environment, endpoint listing), smoke gate, execution log (116 records: 113 replies and 3 rate-limit events), response cache, completion record, five prediction files, and `evaluation_summary.json` written by notebook 03. |
| `tables/per_question.csv` | One row per question: reference, the six replies, scores, citations, transitions. |
| `figures/fig1`–`fig4` (`.png`, `.pdf`) | Accuracy 2 × 2 and primary effect; per-question outcomes; interaction by document; citations, repeat stability and input tokens. Produced by `notebooks/03_evaluation.ipynb` section 14. |
| `AUDIT.json` | The independent audit: 44 checks and the recomputed results. |
| `PROVENANCE.json` | Run timing, tokens and cost, spec and code revision, environment, what cannot be verified, supporting runs and their checksums. |
| `SHA256SUMS` | Checksums of every file above. |

The run files contain model replies, image hashes and the system prompt, but no
question text, page images, Base64 payloads or credentials. `per_question.csv`
contains MMLongBench-Doc reference answers (CC BY-NC 4.0, research use).

## Verify and reproduce (no API call)

```bash
cd experiments/frozen/e2 && shasum -a 256 -c SHA256SUMS
```

Then run notebooks 00 → 03. Notebook 02's default offline mode rebuilds the E2
requests and checks them against the frozen E1 requests. Notebook 03 evaluates
this frozen run by default:

- it verifies `SHA256SUMS`;
- it re-derives `evaluation_summary.json` exactly and `tables/per_question.csv` byte for byte;
- it asserts the regression references: 11/15/15 against 10/16/11; 4 fixed, 5 broken; 0 Qwen repeat flips; retain;
- it redraws the figures into `data/processed/mmlongbench_doc/e2/figures/`.

PNG and PDF bytes can differ across matplotlib versions, so figures are checked
by eye. The smoke, pilot and abandoned v1 runs stay in git-ignored
`experiments/runs/e2/`; their checksums are in `PROVENANCE.json`.

## Independent audit (2026-11-22)

A standalone script outside the notebooks recomputed every check from the raw
files. It shared only the frozen scoring-rule cell, which has been unchanged
since before E2. All 44 checks passed:

- **Specification.** The snapshot equals the tracked v2 spec and the copy in
  `f0f4584`. It was committed before the first request, and v1 is unchanged.
- **Plan.** It was re-derived from the spec seeds, with 113 items in order.
- **Accounting.**
  - 113 replies in plan order, all live;
  - 3 rate-limit records, each with no reply and followed by a successful retry;
  - no attempt consumed;
  - prediction files equal the log, and the cache equals the log.
- **Responses.**
  - every raw reply re-parses to the logged answer and citations;
  - every reply came from Parasail with stop as the finish reason;
  - prompt tokens equal the offline expectation on 113/113 replies;
  - generation ids are unique.
- **Requests.** Image hashes, dimensions and E1 fingerprints equal the frozen
  E1 request of the same question and resolution. The repeat shares the main
  fingerprint but not its cache key, and it started after the last main reply.
- **Costs.**
  - each reply's cost equals its token counts times the spec prices;
  - the total equals `completion.json` and stays within budget;
  - OpenRouter's account usage equals the recorded total of all four E2 runs.
- **Results.** Counts, fixed and broken, repeat rates, leave-one-out,
  interaction, verdict and the per-question table all match notebook 03.
- **Code.** The executed notebook 02 equals its source at `f0f4584`.
- **Hygiene.** The run files contain no credentials.
