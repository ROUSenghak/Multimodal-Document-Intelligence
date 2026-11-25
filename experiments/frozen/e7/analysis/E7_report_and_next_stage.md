# E7 extract-then-answer: results, error analysis and next-stage recommendation

- **Date:** 2026-11-24.
- **Run:** `experiments/runs/e7/20261124T160111456175Z_b3d0b5c0_full`.
- **Spec:** `e7_extract_then_answer_v1` (sha256 `7d124b81…`), notebook 06 at commit `469aff5`.
- **Status:** these are **development results**. E7 was designed on these 118 questions (14 documents), so nothing here is a generalisation claim.

Labels used throughout:
- **[observed]:** measured in this run.
- **[diagnostic]:** a descriptive breakdown with no controlled comparison.
- **[hypothesis]:** an interpretation that has not been tested.

## 1. Integrity audit

| Check | Result |
|---|---|
| Spec sha256 = run settings = byte-identical spec snapshot | ✅ |
| Notebook 06 and spec equal to git HEAD `469aff5`; working tree clean before and after | ✅ |
| Frozen E0–E6: 187 files equal to their SHA256SUMS (pre-flight run, offline mode) | ✅ |
| 1,309 / 1,309 planned calls logged, in plan order (qid, kind, arm, page) | ✅ |
| Retries: 0 attempts > 1; 0 rate limits | ✅ |
| Sent fingerprint = planned fingerprint on all 1,309 calls; request content verified; integrity valid | ✅ |
| Served model `gpt-4o-mini-2024-07-18` on all 1,309 calls | ✅ |
| V0 = frozen E6 V request (118/118 fingerprints) | ✅ |
| Each (question, page) extracted once; no extraction paid twice; X4 reads X8's cached extractions | ✅ (944 extraction calls serve 1,403 page readings) |
| Each reasoning memory = the arm's pages in rank order, built from this run's extractions | ✅ |
| Notebook 06 run validation (9 checks) | ✅ 9/9 |
| **Independent re-derivation** (separate script, no notebook code): accuracy, fixed/broken lists, cluster bootstrap (seed 20261203, 10,000 draws), exact 2^14 sign-flip, abstentions, citation validity, cost | ✅ all identical to notebook 06 |
| Spend | $5.848 this run; **$5.911 cumulative** of the $9.00 ceiling (planned upper bound $7.12) |

**Limitations recorded (not failures):**
1. **Backend split by call type.** Every image call (V0 and all extractions) was served by backend `fp_022a442bda`, and every text-only reasoning call by `fp_9400314673`.
   - The image stage is therefore comparable across arms.
   - X's text-only reasoning step necessarily ran on a different backend, and this run cannot separate that from the architecture.
2. **10 of 944 extraction replies were unusable** (1.1 %):
   - 7 hit the 800-token reply limit on dense pages;
   - 3 had no `facts` list (one question, mmlb-0199).

   As the frozen design specifies, each of these pages entered the memory as "unreadable".
3. **Session noise of the control arm.** V0 = 38/102, the same total as frozen E6 V (2 questions fixed, 2 broken between sessions).
4. **Scoring rule.** The frozen scorer counts *score > 0* as correct, so string similarity can give credit to a wrong answer (see §2.4).

**Leakage.** The notebook's structural, field, prompt, builder-signature and code-scan controls passed before the freeze. Reference answers, evidence pages and audit labels are read only by evaluation cells. In this analysis, reference answers were read offline; none entered any prompt.

## 2. Results

### 2.1 Primary and secondary comparisons (102 answerable questions, 14 document clusters)

| Comparison | Accuracy before → after | Δ | Fixed / broken | Bootstrap 5th pct | 95 % CI (cluster) | Sign-flip p (one-sided) | Verdict (frozen rule) |
|---|---|---|---|---|---|---|---|
| **X4 − V0 (primary)** | 38 → 31 /102 | **−0.069** | 3 / 10 | −0.124 | [−0.135, −0.008] | 0.990 | **regression** (Δ ≤ −0.05) |
| X8 − X4 (more pages) | 31 → 29 | −0.020 | 2 / 4 | −0.056 | [−0.064, +0.018] | 0.938 | no_meaningful_gain |
| X8 − V0 (total, descriptive) | 38 → 29 | −0.088 | 4 / 13 | −0.155 | [−0.167, −0.018] | 0.995 | regression (descriptive) |

How the primary comparison fails each part of the rule:
- **Engineering criteria:** E1 fails (gain < +0.05) and E2 fails (10 broken > 3 / 2). The guardrails pass: G1 abstention 9 ≥ 7 − 2; G2 citation validity +0.059.
- **Statistical criteria:** S1 and S2 both fail.
- **Descriptive tests:** McNemar p = 0.092. The document-weighted Δ is −0.078. Leave-one-document-out Δ ranges from −0.053 to −0.093, so **no single document drives the drop**.

**Frozen verdict: `regression`.** The prespecified next step is to keep E6's one-shot reader.

### 2.2 Breakdown [observed]

| Stratum | n | V0 | X4 | X8 |
|---|---|---|---|---|
| Single-page evidence | 55 | 30 | 25 | 23 |
| Multi-page evidence | 46 | 7 | 6 | 6 |
| No annotated evidence | 1 | 1 | 0 | 0 |
| E6 pages: complete evidence | 61 | 33 | 28 | 25 |
| E6 pages: partial evidence | 25 | 2 | 2 | 2 |
| E6 pages: no evidence | 15 | 2 | 1 | 2 |
| X8's own pages: complete evidence | 70 | — | — | 27 |

**The loss comes from questions whose evidence was already complete** (complete stratum: −5 for X4, −8 for X8). Multi-page accuracy did not improve: 7 → 6.

### 2.3 Reliability, cost and latency [observed]

| | V0 | X4 | X8 |
|---|---|---|---|
| Correct abstention (16 unanswerable) | 7 | 9 | 8 |
| False abstention (102 answerable) | 11 | 17 | 15 |
| Answered an unanswerable question | 9 | 7 | 8 |
| Answers without a valid citation (118) | 8 | **1** | 2 |
| Citation validity (118; valid and not missing) | 0.932 | **0.992** | 0.983 |
| Grounded answers (101) | 67 | 69 | 65 |
| Calls per question | 1 | 4.9 | 9 |
| Prompt tokens per question (mean) | 103 k | 106 k | 219 k |
| USD per question if run alone | $0.0155 | $0.0162 | $0.0334 |
| Median latency, sequential (p90) | 2.7 s (4.3) | 11.1 s (19.4) | 21.0 s (34.8) |
| Median latency, page calls in parallel | 2.7 s | 5.1 s | 5.6 s |

**Arithmetic tool:**
- X4 requested 19 calculations; only 5 could be evaluated. The other 14 were malformed: the model wrote shorthand such as `{"divide": [...]}` or `{"count": [...]}` that the frozen grammar does not accept.
- Net effect: correct with the tool 31, with the model's own answer 30. The tool helped **one** question (mmlb-1014: tool 11,749, the correct value; the model's own sum was 11,949).

### 2.4 Scoring sensitivity (descriptive; never changes the verdict)

In mmlb-0998, X4 answered "BBA", which is substantively correct: its memory shows BBA $6,026 as the highest salary. It scored 0. V0 answered "BAC (Hon) – Bachelor of Business Administration (Accountancy)", which is substantively wrong ($4,668), yet scored 0.951 by string similarity.

| Variant | X4 − V0 | Fixed / broken |
|---|---|---|
| Frozen rule (score > 0) | −0.069 | 3 / 10 |
| Strict rule (score = 1) | −0.049 | 4 / 9 |
| Frozen rule with mmlb-0998 corrected | −0.049 | 4 / 9 |

Under either variant the label would become `no_meaningful_gain`, just inside the boundary. **The practical conclusion is identical in every variant: extract-then-answer did not improve accuracy, and the point estimate is negative.**

## 3. Error analysis and remaining bottlenecks

### 3.1 Why X4 broke 10 questions V0 had right [diagnostic; my labels from reading memories and replies]

| Mechanism | Questions | Count |
|---|---|---|
| **Visual or layout property lost when the page was turned into "facts"**: presence of a signature, document colours, *number of charts*, flowchart order | 0579, 0599, 0688, 0044 | 4 |
| **Extraction perception or value error**: wrong animal on one cover; 4.9 instead of 8.8 (wrong row); a printed name counted as a signature | 0404, 1063, 0600 | 3 |
| Extraction failure on a dense table page (reply limit), then false abstention | 0988 | 1 |
| Reasoning over a correct memory: over-inclusive list ("which individual led" → all 16 lead authors) | 0137 | 1 |
| Scoring artefact (X4 substantively correct; §2.4) | 0998 | 1 |

The 3 fixes are all in categories the design targeted:
- **0081:** a list assembled across two pages.
- **1001:** counting from an enumerated list.
- **1014:** a sum computed by the arithmetic tool.

**[hypothesis]** The architecture works where the answer is a set of explicit text facts, but per-page textualisation discards what the one-shot visual reader uses on visual questions: layout, visual properties, object counts and relations. The extraction schema (label, value, unit, period, supporting text) has no slot for these. A further 13 % of annotated evidence pages (17/128) yielded no fact at all.

### 3.2 Frequency of each bottleneck

The denominator is V0's 64 errors on the 102 answerable questions, combined with the E6 manual audit, which labelled each error A (evidence), B (reader) or C (scoring).

| Bottleneck | Frequency | Source | Status |
|---|---|---|---|
| **Missing or incomplete evidence in the 4 supplied pages** | 36 / 64 errors (56 %): partial 23, none 13 | [observed] E6 stratum × V0 | Dominant |
| ↳ Multi-page questions | 39 / 64 errors; V0 7/46 correct. With complete multi-page evidence, 4/12 (E6 audit) | [observed] | Dominant |
| ↳ Retrieval rank, not just budget | Top-8 adds complete evidence for only 9 more questions (61 → 70); E6 audit: top-8/10/15 completes 6/9/16 of the 33 group-A questions | [observed] | |
| Reader errors with complete evidence | 28 / 64 (44 %); V0 33/61 correct with complete evidence | [observed] | Second |
| ↳ Counting / spatial | 6 | E6 audit (B) | |
| ↳ Visual perception | 5 | E6 audit (B) | |
| ↳ Semantic / distractor | 4 | E6 audit (B) | |
| ↳ List extraction | 3 | E6 audit (B) | |
| ↳ Calculation | 3 | E6 audit (B) | |
| ↳ Table-cell alignment | 2 | E6 audit (B) | |
| ↳ Multi-page aggregation | 2 | E6 audit (B) | |
| ↳ False abstention | 2 | E6 audit (B) | |
| Context guard drops (4-page cap) | 3 | E6 audit (A) | |
| False premise or unanswerable | V0 answers 9 of 16 unanswerable; 8 are false-premise variants | [observed] | Third |
| Incorrect or missing citations | V0: 8 of 118 answers lack a valid citation; X arms: 1–2 | [observed] | Fixed by structured output |
| Scoring or annotation issues | 4 (E6 audit) + 1 (0998) | [diagnostic] | |
| **Sensitivity to the number of pages** | Under extraction, 8 pages did *not* help (−0.020). 264/680 non-evidence pages were flagged "relevant", so the extra pages add distractor facts | [observed] for the extraction reader only; **untested for the one-shot visual reader** | Open |

**What E7 rules out [observed]:**
- Turning pages into structured text, then reasoning over text, is **not** a better reader than GPT-4o-mini's one-shot view of the same 4 images on these documents.
- Extracting more pages is not a cheap route to multi-page accuracy.

**What E7 suggests for the application:**
- **[observed]** The structured-output contract produced near-perfect citation validity: 99 % against 93 %.
- **[hypothesis]** A schema-constrained answer format with cited pages could be brought into the one-shot reader without the extraction stage. That is a product change, not a new architecture experiment.

**Ensemble ceiling [diagnostic].** Questions answered correctly by any arm: 42/102, against 38 for V0. Even a perfect per-question selector between the arms would add at most 4 questions. Combining arms is not worth pursuing.

## 4. Literature review

Full review: `literature_review.md` (same folder), about 25 sources, each marked by how far it was read (full, partial or abstract).

Key points for our failure profile:
- **Published gains come mostly from evidence localisation, not reasoning scaffolds.**
  - DocLens: removing the page-finding (Lens) module costs 3–4 points; removing the reasoning module costs about 0.5–1.
  - SimpleDoc: most of the gain comes from summary-based page selection; extra iterations add about +1.
  - This matches our profile, where 56 % of errors are evidence incompleteness, and E7's negative reasoning-side result.
- **The strongest systems use long-context frontier readers** (Gemini-2.5, Claude-4) or 32B open models that read many pages. Their designs assume image reading is cheap. **GPT-4o-mini bills 25,501 tokens per 768-px page in our measurements**, which is why our reader is capped at 4 pages. Their mechanisms do not transfer to our budget unchanged.
- **Per-page note-taking (Chain-of-Note style) baselines are weak on MMLongBench** in SimpleDoc's re-run: 40.45 against 59.55. That read is unverified (summary-level), but it is consistent with E7.
- **Training-free adaptive k (ViSAR) has a small published effect**: about +1 accuracy point with fewer pages. Its value for us would be cost.
- **DocLens's "+OCR text" gains did not transfer** to GPT-4o-mini in our E3 (image + text 16/37 against images alone 17/37). A concrete example of non-transfer.
- **The reader has a deadline.** OpenAI's deprecations table lists `gpt-4o-mini-2024-07-18` as deprecated, with **API shutdown on 2027-01-14**, about 7 weeks from now. I saw this through a search snippet; the official page should be checked.

## 5. Candidate improvements

Scores: + favourable, − unfavourable.

| Candidate | Fits E7 failures | Published evidence | Expected gain (our setup) | Complexity | Extra API cost | Local hardware | Reuses caches | Risk of new errors | Value for the application |
|---|---|---|---|---|---|---|---|---|---|
| More extraction or agentic scaffolds (SLEUTH, MDocAgent, adjudication) | − (E7 negative) | Mixed; reasoning modules about +0.5–1 | ≤ 0, uncertain | High | High (many calls) | None | Partial | High (E7 showed it) | Low |
| **Wider page budget in a one-shot visual reader** (needs a reader with cheaper image tokens) | + evidence incompleteness, multi-page | Mixed (VisRAG: more pages help; M3DocRAG: top-10 < top-6; SimpleDoc: selective pages beat many) | 0 to +5 points, **highly uncertain** | Low | Depends on the successor's pricing | None | ✅ rankings, renders | Distractors (E7 saw them under extraction) | **High**: the migration is forced anyway |
| **Listwise text-only page screening** (SimpleDoc-style) of ColQwen2 top-15 to 4 pages, using cached OCR text | + evidence incompleteness | SimpleDoc (EMNLP 2025): page selection is the main driver | Evidence completeness +0 to +9 questions; accuracy unknown | Medium | Very low (text only, ≈ $0.1–0.3 for 102 questions) | None | ✅ rankings, OCR | E7: per-page "relevant" flags were uninformative (39 % false positives); a listwise comparison is untested | Medium |
| ViSAR adaptive k | ± cost, distractors | arXiv 2026, not peer reviewed; about +1 point | ≈ 0 accuracy; fewer pages | Low–medium | **Zero** (embeddings only) | CPU | ✅ embeddings | Low | Medium (cost) |
| Patch-to-region crops / zoom | + perception, table cell (about 7–9 of 64 errors) | Preprint; localisation only, no QA gain shown | Small (bounded by about 8 % of errors) | Medium–high | Medium | CPU + OCR layout | ✅ patch embeddings | Medium | Medium |
| Sufficiency check / guided abstention | + false premise (9/16) | ICLR 2025, but trades coverage for precision | +1 to +3 on 16 unanswerable; risk of more false abstentions (E7: +6) | Low | Low | None | ✅ | **High** (E7 raised false abstentions) | Medium |
| Rerankers (jina-m0, MM-R5), RL agents (VRAG-RL, Doc-V\*), VDocRAG | ± | Trained models | Unknown | High | — | GPU or downloads | — | — | Licence (jina is non-commercial) or training: out of scope |

## 6. Recommendation

**Stop architecture experimentation on the current reader, and move to application development with the E6 configuration:**
- ColQwen2 top-4 pages, read by the one-shot visual reader, with citations;
- BM25 as the fallback.

The one evaluation that cannot be skipped is a **reader-migration evaluation** before 2027-01-14. It is a forced model substitution, not an architectural experiment.

Why this follows from E7:
1. The architecture designed to fix reader errors lowered accuracy, with a two-sided 95 % CI entirely below zero. The more-pages arm of it did not help either.
2. The dominant remaining bottleneck, evidence incompleteness (56 % of errors), is limited mainly by **GPT-4o-mini's image-token price**, which caps the reader at 4 pages, and by retrieval rank. Neither can be fixed cheaply on a reader that is retired in 7 weeks.
3. Every further optimisation on these 14 development documents adds selection bias. E4–E7 have already been designed on them.

**Ranked methods to keep in reserve:**
1. **Primary, folded into the migration evaluation: a wider page budget with the successor reader.**
   - The successor must be chosen anyway. If its image tokens are cheaper, an 8-page one-shot arm costs little extra and tests the evidence-incompleteness hypothesis directly.
   - Plausible gain: 0 to +5 points on 102 questions. It is uncertain whether more pages help a one-shot reader or only add distractors, and E7 showed distractors under extraction.
2. **Listwise text-only page screening.** Its cheapest test measures retrieval only (below); no answer calls are needed.
3. **ViSAR adaptive k.** An offline, zero-cost retrieval diagnostic; worth doing only for application cost.

**Not recommended:** further extraction or agentic scaffolds, ensembles (ceiling +4 questions), crops (small error share), trained rerankers or agents.

### Cheapest valid tests

**A. Offline (no API calls):**
- Freeze E7 into `experiments/frozen/e7` with its audit and SHA256SUMS, as was done for E6. This needs your approval.
- For the migration: read the successor's *official* pricing and image-token accounting; recompute the context guard (how many 768-px pages fit) and the cost of V at 4 pages and at 8 pages; rebuild the 118 requests deterministically; run mocked-reply interface tests.
- Optional zero-cost retrieval diagnostics:
  - ViSAR k\* against fixed top-4: evidence completeness on the 101 evidence questions, and mean pages;
  - the share of the 33 group-A questions whose evidence lies in the top 15.

**B. Technical smoke:**
- 2 calls on mmlb-0068 (the largest request), on the successor at 4 pages.
- Pass if: the reply parses; the served model equals the pinned snapshot; prompt tokens are within ±2 of the offline estimate; the cost is within the upper bound.
- Ceiling: $0.25.

**C. Diagnostic pilot: skip it.** With 102 questions in 14 clusters, a pilot cannot distinguish effects below ±0.13. Go directly to D, which costs only a few dollars.

**D. Migration evaluation (separate spec v1 and approval):**
- **Hypothesis:** the successor reader on the same ColQwen2 top-4 pages is *non-inferior* to GPT-4o-mini V. Margin −0.05, development only. Secondary: successor at 8 pages against successor at 4 pages.
- **Control:** the frozen E6 V and E7 V0 replies. Two sessions already exist (38/102 each), which also gives the session-noise estimate.
- **Treatment:** the successor reader with an identical prompt, pages, guard and scorer. The page budget changes only in the secondary arm.
- **Metrics:** as in E6/E7. Primary: accuracy on the 102 answerable questions. Guardrails: abstention (16) and citation validity (118). Also cost and latency per question.
- **Statistics:** the same cluster bootstrap and sign-flip test. Report the two-sided CI against the −0.05 margin.
  - On 102 questions, the CI half-width is about 0.065, so only gross regressions are detectable.
  - This is a deployment gate, not a generalisation claim.
- **Cost:** computed in step A from official pricing; I will not guess the successor's price. For scale, the GPT-4o-mini V arm cost $1.83 for 118 calls.
  - Propose a hard ceiling only after step A, likely ≤ $5 for both arms.
- **Stop or roll back:** any integrity failure; spend reaching the ceiling; the served model differing from the pin.
- **Reject the successor or the 8-page arm if:**
  - the lower 95 % bound is below −0.05 against V;
  - abstention or citation guardrails fail;
  - the 8-page arm's Δ against 4 pages is below +0.05, in which case keep 4 pages, since they are cheaper.

**E. Final generalisation claim, later and separately approved:** a single evaluation of the frozen application configuration on the untouched pool (115 documents, 916 questions). Do not inspect it before then.

### Approval gates (none started)

1. Freeze and commit E7 artefacts (local only; no push).
2. Choose the successor reader: confirm on OpenAI's official deprecations and pricing pages.
3. Spec v1 for the migration evaluation; offline stage (A).
4. Smoke (B).
5. Full migration evaluation (D).
6. Application-phase changes to `src/visualdoc/`: model, page budget, schema-constrained citations. This is a separate phase under AGENTS.md.
7. The final evaluation on the untouched pool (E).
