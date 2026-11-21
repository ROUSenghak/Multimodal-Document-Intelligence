# E2 proposal: does a stronger pretrained VLM beat GPT-4o-mini at 768 px?

**Status: design for review. Nothing is implemented or executed.** After approval,
the design is frozen as `experiments/specs/e2_stronger_vlm_v1.json` before any
model call, as E1 was.

## 1. Question and estimand

> On the same 37 E1 questions, the same annotated evidence pages and the same
> 768-px page images, does a stronger pretrained vision-language model answer
> more questions correctly than GPT-4o-mini did?

- **Primary outcome.** The paired accuracy difference
  mean(correct_M,768 − correct_4o-mini,768) over the 37 matched questions, with
  the frozen scorer ("correct" = score > 0).
- **Comparator.** The frozen E1 predictions `main_r1 / E1_768`: 16/37.

These predictions stay a valid comparator after the GPT-4o-mini API shuts
down (2027-01-14), because every request is fingerprint-verified. No new
GPT-4o-mini call is needed.

## 2. What must be separated

A raw "model A vs model B" comparison mixes four causes. The design isolates
each one or labels it as part of the treatment.

| Possible source of a difference | How E2 handles it |
|---|---|
| **Model capability** (the target) | M and GPT-4o-mini receive byte-identical PNGs (hash-checked), the same pages in the same order with the same `[Page N]` tags, the same system prompt text and the same JSON answer contract. Both use deterministic decoding with a 400-token cap. |
| **Input resolution** | The primary comparison holds pixels fixed at 768 px. A within-model 512-px condition completes a 2 × 2 design (model × resolution) with E1's two GPT-4o-mini conditions. It answers "does M's advantage depend on resolution?" (interaction), not only "is M better?". |
| **Internal visual resolution** | This cannot be equalised. GPT-4o-mini's internal processing is unknown, while M's is observable (its processor reports the visual-token grid). E2 records M's grid per image and verifies that the 768-px renders are **not resized**. "Same input pixels" is the control; what each model does with them is part of "capability". |
| **Prompt and output format** | Same wording; each model's own chat template is unavoidable and recorded. GPT-4o-mini ran in JSON mode (`response_format: json_object`), so M uses guided JSON decoding with the same contract. Parse failures are counted and reported separately. A prompt adapted to the model is allowed only as a labelled exploratory condition. |
| **Run-to-run variation** | M is repeated once at 768 px (greedy decoding, batch size 1, same GPU). Its correctness-change rate, together with E1's 1/37 for GPT-4o-mini, sets the variability margin. |
| **Training-data contamination** | MMLongBench-Doc (2024) predates any 2025 VLM. A gain could partly reflect exposure to these documents. This cannot be ruled out on this benchmark; it is the main reason to build the project's own question set later. |

## 3. Candidate models

The hardware decides most of this. The development machine is an **Apple M1
with 8 GB RAM and about 1 GB of free disk**. No model plausibly stronger than
GPT-4o-mini runs there reliably. An 8B model in 4-bit needs about 5–6 GB of
weights plus several thousand visual tokens of activations, and 4-bit
quantization would itself be a confound. Local inference therefore means a
**rented or institutional GPU**, not this laptop.

| Model | Open weights | Fits one GPU | Why consider it | Main concern |
|---|---|---|---|---|
| **Qwen3-VL-8B-Instruct** | yes (Apache-2.0, per model card) | 24–48 GB, bf16 | Strong reported document results (DocVQA 96.1 in the Qwen3-VL report); native dynamic resolution; long context; vLLM and transformers support; same family from 2B to 235B for a later scaling study | Released after MMLongBench-Doc (contamination); no official 8B MMLongBench-Doc number found yet |
| Qwen2.5-VL-7B-Instruct | yes | 24 GB | Mature tooling, widely reported baseline | Reported weak on MMLongBench-Doc (≈ 25, indicative); superseded by Qwen3-VL |
| Qwen3-VL-32B / 30B-A3B | yes | 80 GB | The report says they beat GPT-5-mini and Gemini-2.5-Flash on most benchmarks | Needs an A100/H100 80 GB; a natural second step |
| GLM-4.1V-9B-Thinking | yes | 24–48 GB | Best open model on the MMLongBench-Doc leaderboard snapshot found (42.4) | "Thinking" outputs conflict with the 400-token budget and JSON contract: a prompt and format confound |
| GPT-4.1-mini / GPT-4.1 (API) | no | — | Same provider and message format; GPT-4.1 leads the leaderboard snapshot found (49.7) | Same API shutdown date as GPT-4o-mini; different image tokenization (32-px patches); paid; not open-weight |
| Hosted Qwen3-VL-8B (e.g. OpenRouter) | weights yes, serving no | — | No GPU setup; about $0.25 per 1M input tokens listed | Provider controls resizing and quantization, which cannot be verified; only a fallback, with the provider pinned |

## 4. Recommendation: test Qwen3-VL-8B-Instruct first

Run it from a **pinned Hugging Face revision, in bf16, with greedy decoding, on
one rented 40–48 GB GPU** (for example an A100 40 GB or L40S). Use the same
notebook stage (02) cloned on that machine.

Why this model first:

1. **It answers the question with control.** With open weights we can verify
   what E1 could not: that the 768-px image is consumed unresized, and how many
   visual tokens each page becomes. The pages become roughly 750 visual tokens
   at 768 × 994, to be confirmed by the processor in the offline gate.
2. **It is reproducible after vendor deprecations.** A pinned revision gives the
   same weights in a year; the GPT-4o-mini snapshot will be gone in under two
   months.
3. **It is cheap enough to scale.** About 150 generations (37 × 768 px, 37 ×
   repeat, 37 × 512 px, plus smoke and pilot) take minutes on one GPU, likely
   **under $5** of rented compute. Once the pipeline is trusted, the same model
   can be run on many more MMLongBench-Doc documents. That is the only realistic
   fix for E1's main weakness, 37 questions in 6 documents.
4. **It is the right size.** It is not fine-tuned, fits one GPU without
   quantization, and the family offers a clean next step (32B) if 8B is
   inconclusive.

Not first: GPT-4.1-mini. It adds an image-tokenization change, is paid, shuts
down on the same date, and does not answer the open-weight part of the
question. It can be added as a separate closed-model arm before 2027-01-14 if
you want one.

## 5. Conditions

| ID | Model | Pages | Pixels | Role |
|---|---|---|---|---|
| `E1_768` (frozen) | GPT-4o-mini | annotated evidence | 768 px | comparator (no new call) |
| `E1_512` (frozen) | GPT-4o-mini | annotated evidence | 512 px | 2 × 2 cell (no new call) |
| `E2_M_768` | Qwen3-VL-8B | annotated evidence | 768 px (same PNGs) | **primary treatment** |
| `E2_M_768_r2` | Qwen3-VL-8B | same | same | repeat (determinism and variability) |
| `E2_M_512` | Qwen3-VL-8B | same | 512 px (same PNGs as E1) | resolution factor and interaction |
| `E2_M_native` *(exploratory)* | Qwen3-VL-8B | same | e.g. 1024–1536 px short side | Does M use pixels GPT-4o-mini could not? |
| `E2_M_768_excluded` *(exploratory)* | Qwen3-VL-8B | the 3 questions with 5–13 pages | 768 px | Feasible with M's longer context; reported separately, never pooled with the 37 |

**Evidence pages.** The oracle pages (annotated evidence, benchmark order, no
padding) are kept so that E2 measures *reading*, not retrieval. Retrieved pages
(BM25 top 5) at 768 px become feasible with a long-context model. That makes a
natural E3: re-testing B against D with a better reader.

## 6. Metrics

- **Primary.** Paired accuracy difference, M@768 − GPT-4o-mini@768, on 37 questions.
- **Secondary (pre-declared).**
  - mean benchmark-score difference;
  - strict accuracy (score = 1) as a sensitivity check;
  - fixed/broken counts;
  - the 2 × 2 interaction (M's 512→768 gain minus GPT-4o-mini's);
  - per-document effects and leave-one-document-out;
  - the visual-reading subgroup.
- **Citations.** Coverage, validity given a citation, evidence-page citation,
  and the **off-by-one citation rate** (the known printed-page failure).
- **Output.** Parse-failure rate, and whether guided decoding was needed.
- **Compute.**
  - per-image visual tokens from the processor, and resize verification;
  - latency per request at batch size 1, on a named GPU;
  - peak GPU memory;
  - cost = GPU price × wall time, beside the API list cost of the comparator.

Latency and cost are hardware-specific, so they are reported, not used to rank
the models.

## 7. Proposed decision rule (to freeze before any call)

1. **Adopt M as the image reader** for this pipeline only if all three hold:
   - the paired gain is ≥ 0.05 (2/37);
   - the gain is strictly greater than the larger of the two repeat
     correctness-change rates (GPT-4o-mini 1/37, M's own);
   - broken ≤ fixed / 2.
2. **Retain GPT-4o-mini@768** (while available) if the gain is ≤ 0.
3. **Otherwise inconclusive.**

The interaction and the exploratory conditions never change the verdict.

## 8. Statistical limits, stated in advance

- 37 paired questions in 6 documents. Only large effects are detectable: with
  no broken questions, at least 6 fixed ones are needed before an exact McNemar
  test even reaches p < 0.05, and that test ignores clustering anyway.
- The document-cluster bootstrap with 6 clusters is descriptive.
- A null result means "no large effect on these 37 questions", not
  "equivalent". If E2 is promising, the follow-up is an **expanded population**
  (more documents, frozen and sampled before any call), not more analyses of the
  same 37 questions.

## 9. Execution plan (after approval; same gates as E1)

1. **Freeze** the spec: model and HF revision SHA, processor settings
   (`min_pixels` / `max_pixels` chosen so 512- and 768-px renders are not
   resized), library versions, dtype, GPU type, prompt hash, decoding settings,
   conditions, decision rule.
2. **Offline gate on this Mac** (no weights, no GPU). Load only the processor
   and chat template. Verify per image that the visual-token grid implies no
   resizing, that the PNG hashes equal the E1 log, that the prompt text is
   identical, and that the context fits for all questions.
3. **Smoke** on the GPU: 2 requests, interface and parsing check.
   **Pilot**: the 8 E1 pilot questions, technical only. Then **full**.
4. **Record** the same audit format as E1: execution log with request
   fingerprints, replicate-scoped cache keys, image hashes, visual-token grids,
   timings and an environment snapshot.
5. **Evaluate** in 03 (new section), freeze to `experiments/frozen/e2/`, audit.

Implementation stays notebook-first. E2 becomes a new section of
`02_question_answering.ipynb` (generation) and `03_evaluation.ipynb`
(evaluation). The GPU machine runs 00 → 02 from a clone. No `src/` module is
added and no fine-tuning is involved.

## 10. Decisions needed from you

1. **Compute.** Rented GPU (which provider or budget), institutional GPU, or the
   hosted-API fallback (less control over preprocessing)?
2. **2 × 2.** Include `E2_M_512`? Recommended: it costs minutes and is the
   only way to separate model from resolution.
3. **Closed-model arm.** Add GPT-4.1-mini (paid, before 2027-01-14) as a
   second treatment, or keep E2 open-weight only?
4. **Thresholds.** Accept the decision rule in §7 as written, or adjust it
   before freezing?

## Sources checked 2026-11-21

- Qwen3-VL Technical Report, arXiv:2511.21631 (flagship MMLongBench-Doc 57.0;
  smaller models in Tables 3–4). The 8B MMLongBench-Doc value is still to be
  read from the report before freezing.
- MMLongBench-Doc leaderboard snapshot of 2025-07-04 (GPT-4.1 49.7, GPT-4o 46.3,
  GLM-4.1V-Thinking 42.4) and repository `mayubo2333/MMLongBench-Doc`.
- OpenAI deprecations page: GPT-4o, GPT-4o-mini and GPT-4.1-mini API shutdown on
  2027-01-14.
- OpenAI vision guide: patch-based image tokens for GPT-4.1-mini (32-px patches).
- OpenRouter listing for `qwen/qwen3-vl-8b-instruct` (input price; listings
  disagree, so verify before use).
