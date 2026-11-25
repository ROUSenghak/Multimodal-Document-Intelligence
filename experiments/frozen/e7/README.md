# Frozen E7 result: extract-then-answer (development)

**Question.** On E6's 118 questions (14 MMLongBench-Doc documents), does reading each supplied page separately into a structured Evidence Memory and then answering from that memory in a text-only step answer more questions correctly than E6's one-shot reader? The comparison holds fixed the pages, the GPT-4o-mini snapshot, the 768-px images and the scorer.

**Status of the population.** E6's 118 questions were inspected answer by answer to design E7, so they are a **development set**. Every number below is a development result, not a held-out one.

**Answer.** No. The pre-registered verdict is **`regression`**: keep E6's one-shot reader.

| | V0: one-shot (E6's request, byte for byte) | X4: extract-then-answer, V0's pages | X8: extract-then-answer, ColQwen2 top 8 |
|---|---:|---:|---:|
| correct, 102 answerable (primary) | **38** | 31 | 29 |
| correct abstention, 16 unanswerable | 7 | 9 | 8 |
| false abstention, 102 answerable | 11 | 17 | 15 |
| citation validity, 118 replies | 0.932 | 0.992 | 0.983 |
| calls per question | 1 | 4.9 | 9 |
| USD per question if run alone | 0.0155 | 0.0162 | 0.0334 |
| median latency, sequential | 2.7 s | 11.1 s | 21.0 s |

- **Primary (X4 − V0, paired, one session).**
  - Δ = −0.069: 3 fixed, 10 broken.
  - Document-cluster bootstrap (14 documents, 10,000 resamples): 95 % interval [−0.135, −0.008].
  - Exact document sign-flip test: one-sided p = 0.990. McNemar p = 0.092, descriptive only.
- **Decision rule (frozen before any call).**
  - The guardrails hold: abstention 9 ≥ 7 − 2; citation validity +0.059.
  - The verdict is `regression` because Δ ≤ −0.05. E1 (gain ≥ +0.05) and E2 (broken ≤ fixed / 2) both fail.
- **Secondary.**
  - X8 − X4 = −0.020 (2 fixed / 4 broken): `no_meaningful_gain`.
  - X8 − V0 = −0.088 (4 / 13), descriptive.
- **Session noise.** Frozen E6 V and this session's V0 both score 38/102, with 2 fixed and 2 broken between sessions.
- **Scoring sensitivity (descriptive).** Strict scoring, or correcting `mmlb-0998` (V0 scored 0.951 for a wrong answer by string similarity), gives Δ = −0.049. That would read `no_meaningful_gain`; the conclusion is the same.
- **Mechanism (diagnostic).**
  - The loss sits on questions whose evidence was already complete.
  - Per-page "facts" lose visual and layout properties: signatures, colours, chart counts, flowchart order.
  - 14 of 19 requested calculations were malformed shorthand; the tool helped one question.
  - The structured contract raised citation validity from 0.93 to 0.99.

## How it was run

- **Model.** `gpt-4o-mini-2024-07-18` for every call: Chat Completions, temperature 0, JSON mode, image detail high.
- **Prompts.**
  - V0: `mmlb-image-v1` (35ff2e8b91f9).
  - Extraction: `e7-extract-v1` (b30616381e85).
  - Reasoning: `e7-reason-v1` (54cd7a60a931).
- **Specification.** `experiments/specs/e7_extract_then_answer_v1.json`, frozen at 2026-11-24 13:35:17 UTC and committed with notebook 06 in `f19ac27`. Outputs were recorded in `469aff5`, the commit at which both runs executed. Cumulative ceiling: USD 9.00.
- **Smoke run.** 11 calls on `mmlb-0068`, the largest V0 request: 12/12 technical checks passed.
- **Full run.**
  - The smoke block again, never scored, then 118 seeded blocks. Each block is 1 V0 call, 8 extractions, and the X4 and X8 reasoning calls.
  - Counterbalancing: V0 opens 59 blocks; X4's reasoning call precedes X8's in 59.
  - 1,309/1,309 calls answered on their first attempt, with no rate limit.
  - 10 extraction replies were unusable (1.1 %) and entered the memory as "unreadable", as designed.
- **Backends.** Every image call (V0 and extractions) ran on `fp_022a442bda`, and every text-only reasoning call on `fp_9400314673`. The architecture effect cannot be separated from this backend split.
- **Cost.** USD 5.911057 cumulative at list price: smoke $0.063019, full $5.848038.

## Limitations

1. **Development result.** The prompts and targeted categories were designed with these questions in view.
2. **Small, clustered sample.** 102 answerable questions in 14 documents; two 10-Ks hold 31 of them.
3. **One replicate per arm.**
4. **Bundled factors.** X4 − V0 bundles page-wise reading, structured evidence, text-only reasoning and the arithmetic tool; only the tool's share is separable.
5. **Retiring snapshot.** It shuts down on 2027-01-14, so the result is specific to it.
6. **Local scoring.** The rule-based scorer, with correct = score > 0. These are not leaderboard numbers.

## Contents

| Path | Content |
|---|---|
| `run_20261124T143927981959Z_9b46fcad_smoke/` | Byte-identical copy of the smoke run (12 files) |
| `run_20261124T160111456175Z_b3d0b5c0_full/` | Byte-identical copy of the full run (16 files): settings, spec snapshot, plan, session record, smoke gate, append-only log (with each reasoning call's Evidence Memory), run-scoped cache, extractions, predictions per arm, completion record |
| `tables/evaluation_summary.json`, `tables/per_question.csv` | Notebook 06's evaluation, byte for byte |
| `analysis/E7_report_and_next_stage.md` | Post-run report: results, error analysis, recommendation (written after the run) |
| `analysis/literature_review.md` | Literature review written during the run, independent of its results |
| `design/e6_error_audit.csv`, `design/e6_unanswerable_audit.csv` | The manual E6 error labels E7 was designed from (also written out in notebook 06 cell `e7-audit-labels`) |
| `AUDIT.json`, `audit_e7.py` | The independent audit (38/38) and the script that produced it |
| `PROVENANCE.json` | Timing, sessions, backends, tokens, cost, spec and code revision, approvals, environment, hashes of the launchers kept outside, what cannot be verified |
| `SHA256SUMS` | Checksums of every file above |

**What the files contain:**
- **The run files:** model replies, page numbers, image hashes, system prompts and extracted page facts. They contain no question text, page image, Base64 payload, annotation field or credential (checked by the audit).
- **`design/` and `tables/per_question.csv`:** short quotations of replies, and in `design/` of reference answers.

## Verify and reproduce (no API call)

```bash
cd experiments/frozen/e7 && shasum -a 256 -c SHA256SUMS
```

Then run notebook 06, given the outputs of notebooks 00 and 04. Its evaluation cell `e7-evaluate` evaluates this frozen run by default:
- it verifies `SHA256SUMS`;
- it validates the run;
- it re-derives `tables/` byte for byte;
- it asserts the regression references: V0 38, X4 31, X8 29 of 102; 3 fixed / 10 broken; `regression`; X8 − X4 `no_meaningful_gain`; USD 5.911057.

Re-running the audit: `python -I experiments/frozen/e7/audit_e7.py . AUDIT.json`. Its first check compares this copy with the original git-ignored runs in `experiments/runs/e7/`, so it needs them.

## Independent audit (2026-11-25)

The standalone script `audit_e7.py` neither imports nor executes notebook 06. It shares only notebook 03's frozen scorer cell `f653d232`, executed verbatim. It recomputed 38 checks from this copy, the tracked specs, the frozen E5 rankings and E6 run, and git objects at `f19ac27` and `469aff5`. All passed:

- **Package.** The run copies, tables, analysis and design files are byte-identical to their sources.
- **Specification and code.**
  - The spec snapshot equals the tracked spec and the spec at both commits, and its hash equals the settings.
  - Both session records name `469aff5` with a clean tree.
  - Notebook 06's code hash at that commit, recomputed, equals the recorded one.
  - Both commits precede the first request.
- **Population and plan.**
  - 14 documents; 118 questions = 102 answerable + 16 unanswerable; 101 evidence questions plus `mmlb-0599`.
  - 1,309 calls in 118 contiguous blocks, with 59/59 counterbalancing for V0 position and reasoning order.
  - Extraction pages = ColQwen2 top 8. X4 pages = V0 pages. V0 = the frozen E6 V request on 118/118 fingerprints.
- **Accounting.**
  - One final record per planned call, in order, on its first attempt.
  - Statuses: 1,299 ok and 10 extraction parse errors.
  - The pinned snapshot served every call, the sent fingerprint equals the planned one, and integrity is valid throughout.
  - Prompt tokens are +1 on 1,071 calls and +2 on the 238 reasoning calls.
  - Cache keys equal SHA-256(run_id:replicate:fingerprint) and are unique.
  - Prediction files equal the log, and every memory is built from this run's extractions for the arm's pages.
  - 944 extractions serve 1,403 page readings.
- **Cost.** Recomputed from billed tokens: $0.063019 + $5.848038 = $5.911057.
- **Results.** The audit rescored every reply and re-implemented the statistics and decision rule from the spec text. Everything below equals the frozen summary:
  - accuracies, fixed/broken lists, bootstrap interval, sign-flip p-values, McNemar, document-weighted Δ and leave-one-document-out;
  - X8 comparisons, abstentions and citation validity;
  - the verdicts, the session noise and the scoring sensitivity;
  - the 354 rows of `per_question.csv`.
- **Hygiene.** No question text, credential-like string or Base64 payload in any run file, and no annotation field in the logs.
