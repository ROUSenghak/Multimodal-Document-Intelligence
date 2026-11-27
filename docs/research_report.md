# VisualDoc AI: research report, E0–E9 and the final held-out evaluation

- **Date:** 2026-11-26.
- **Scope:** every experiment from E0 to E9, the consolidation into the validated baseline B1, and the final held-out evaluation.
- **Status of the evidence:** E0–E9 are **development results**, from 20 MMLongBench-Doc documents that shaped the design. The **final held-out evaluation** (section 9) is the one confirmatory result: it ran once, on 2026-11-26, on 110 documents never used in development, under a protocol frozen before any of them was downloaded (`experiments/frozen/final/`). The test pool is now used and may not be used to tune a system again.
- **Sources:** every number is taken from a frozen package in `experiments/frozen/`, from `AGENTS.md` (regression references), or from the documents in `docs/`. The source is named beside each table. Where two sources disagree, both are given (section 10).

---

## 1. Summary

The project asks how to answer questions about long PDF documents with **cited, checkable answers**, and which design choices actually matter. It started from one controlled comparison (extracted text vs rendered page images) and moved, one pre-registered experiment at a time, to a frozen pipeline called **B1**: ColQwen2 visual retrieval over page images, the top 4 pages, one `gpt-6-luna` call with a strict JSON contract, then deterministic citation and grounding checks.

What the record supports:

1. **Visual retrieval beats OCR + BM25, in development and held out.** In development it held for evidence (E5: recall after the context guard 0.526 → 0.721) and for answers (E6: 25/102 → 38/102, 13 fixed, 0 broken, document-cluster 95 % interval [0.074, 0.193]). The final evaluation **confirmed it out of sample**: with the same reader, ColQwen2's top 4 pages beat OCR + BM25's by +0.119 [+0.088, +0.150] on 674 held-out answerable questions (103 fixed, 23 broken, sign-flip p = 1.0e-05), verdict `visual_retrieval_confirmed`.
2. **Per-page extract-then-answer is worse than one-shot reading** (E7: −0.069, interval [−0.135, −0.008]). A supported negative result.
3. **Several plausible changes did not help in development:** a stronger open VLM (E2), adding OCR text to images (E3), adaptive reading of more pages (E9). These are reported as negative or null results. On held-out data, E9's adaptive policy showed a small, fragile gain (+0.021, secondary claim C3); it is reported, not adopted.
4. **The B1 output contract is non-inferior, not better**, than the previous contract (E8: 46 vs 42 of 102, interval [−0.019, +0.098]); it adds valid citations and verbatim quotes.
5. **B1's held-out accuracy is 0.427** (288 of 674 answerable questions, [0.386, 0.470]), slightly below its development estimate of 0.451 and inside its interval. **The ceiling is evidence supply:** accuracy falls from 54 % for single-page evidence to 13 % for 4+ pages (`experiments/frozen/final/README.md`), and in development ColQwen2's top 4 pages missed part of the annotated evidence for 39 of 101 questions (E9 Stage 0).

---

## 2. Research questions

The question changed as the evidence came in. Each stage is recorded in its notebook.

| Stage | Question | Notebook |
|---|---|---|
| E0 | With the same model, questions and pages, does sending rendered page images instead of extracted text improve answers and citations? | 00–03 |
| E1–E3 | For the image reader: which resolution, which model, and does adding the page text help? | 02, 03 |
| E4 | How accurate is the application end to end, and how much of its error is page selection rather than reading? | 02 §13, 03 §17 |
| E5–E6 | Does a visual page retriever put more evidence in front of the reader, and does that turn into more correct answers? | 04, 05 |
| E7 | Does separating per-page extraction from reasoning help the reader? | 06 |
| B1, E8 | Which retriever does the baseline use, how are answers scored, and can a successor reader with a structured contract replace the retiring one? | 07 |
| E9 | Can a retrieval-uncertainty signal decide when to read more pages? | 08 |
| Final | How accurate is the frozen system on documents never used in development, and does the visual-retrieval result hold out of sample? | 09 |

---

## 3. Data

**Benchmark.** MMLongBench-Doc (`yubo2333/MMLongBench-Doc`), pinned at revision `2ff6aa9237fc777b6627dc57a486e9225ac5fb86`. 1,091 questions over 135 PDFs; 847 answerable and 244 unanswerable (22.4 %). Evidence is annotated as 1-based physical page numbers, which notebook 00 verifies rather than assumes. Licence CC BY-NC 4.0, research use only. (Notebook 00 §1; `data/external/README.md`.)

| Population | Documents | Questions | Used by | Notes |
|---|---:|---:|---|---|
| dev6 | 6 | 57 (40 answerable, 17 unanswerable) | E0–E4 | seeded draw (seed 42) of documents ≤ 15 MB; 195 pages, 120 needed OCR; E1–E3 use the 37 answerable questions whose evidence fits the context at both resolutions |
| held-out-14 | 14 | 118 (102 answerable, 16 unanswerable; 101 with annotated evidence) | E5, E6; then E7–E9 as development data | two documents per benchmark type, seeded, ≤ 100 pages each, 647 pages; never used before E5 |
| **Development total** | **20** | **175** | — | every design decision rests on these |
| Test pool (untouched until the final evaluation) | 115 | 916 (705 answerable) | nothing before 2026-11-26 | defined in `experiments/test_pool_ledger.md` |
| **Final evaluation population** (pool, used once) | **110** | **872 (674 answerable, 198 unanswerable)** | the final held-out evaluation | the pool minus 4 documents whose questions had been seen and `mi_phone.pdf` (deviation D1); 5,554 pages; no page cap, no question filter |

Sources: notebook 00 (§1–4), `experiments/frozen/e5/README.md`, `experiments/test_pool_ledger.md`, `docs/baseline_consolidation_assessment.md` §4.2, `experiments/frozen/final/README.md`, `experiments/frozen/final_index/README.md`.

**Known data properties.**
- Half of dev6 has no usable text layer: two slide decks exported as images and one guidebook whose text is vector outlines. Without OCR, a text system sees empty pages and raises no error (notebook 00, Interpretation).
- The `answer_format` column reveals unanswerability, so it is never shown to a model (notebook 00 §1).
- Evidence annotations come from a single annotator; an unannotated page that also answers counts as a miss.
- In the held-out-14 set, two 10-K filings hold 31 of the 102 answerable questions (`experiments/frozen/e6/README.md`, Limitations).

---

## 4. Method common to all experiments

### 4.1 Pre-registration and execution discipline

- **A specification before any call.** From E1 on, each experiment has a JSON specification in `experiments/specs/`, frozen and committed before the first paid request. It fixes the population, arms, request construction, seeds, decision rule and budget ceiling. Paid modes refuse to run if the specification (and, from E3, the notebook code) differs from the committed version.
- **Same-session, counterbalanced pairs.** Arms of a question are sent adjacently, in a seeded order that balances which arm goes first.
- **Append-only logs and run-scoped caches.** Every call records its request fingerprint, served model, system fingerprint, tokens, cost and latency. A reply cache is keyed by run, replicate and fingerprint, so a replicate can never reuse another replicate's reply.
- **Budget ceilings, fail-closed.** A cumulative ceiling per experiment; a call whose upper-bound cost would exceed it is refused before it is sent.
- **Frozen packages.** After a run, the run directory is copied byte for byte into `experiments/frozen/<exp>/` with evaluation tables, `PROVENANCE.json`, an independent audit (recorded in an `AUDIT.json` in most packages from E2 on) and `SHA256SUMS`.
- **Replay.** Each notebook, in its default mode, rebuilds every request offline, asserts that it equals the frozen one, re-scores the frozen replies and asserts the regression references listed in `AGENTS.md`.

### 4.2 Scoring

- **S-v1 (frozen, primary).** The MMLongBench-Doc rule-based scorer, re-implemented in notebook 03 cell `f653d232` without the official GPT-4o extraction step; a reply is correct when its score is > 0. S-v1 decides every verdict and is never re-labelled. Because the extraction step is replaced by structured JSON answers, these are **local diagnostics, not leaderboard numbers**.
- **S-v2 (secondary, from notebook 07).** A deterministic layer marks each reply correct, wrong or gray (numeric normalisation with units and scale, list matching, containment, partial string credit, debatable references). Gray replies are labelled by the owner, **blind to the arm**, and frozen with item-identity hashes. Owner judgments: 29 items on E6/E7 (7 correct, 21 wrong, 1 unsure; `experiments/frozen/scoring_v2/`) and 16 items on E8 (9 correct, 7 wrong, 0 unsure; `experiments/frozen/e8_scoring_v2/`). The unsure item (`mmlb-1013`) is excluded, which gives a denominator of 101. No model judgment replaces a human label.
- **Why both.** Scoring noise is as large as the effects tested: before adjudication, E6 V's S-v2 interval was 35–47 of 102, while the same request in two sessions flipped only 2 + 2 questions (notebook 07, Results B).

### 4.3 Statistics conventions

| Convention | Rule | Source |
|---|---|---|
| Unit | the question, paired across arms, clustered by document | `docs/baseline_b1_specification.md` §4.4 |
| Interval | document-cluster percentile bootstrap, 10,000 draws, seeded | same |
| Paired test | exact document sign-flip test on per-document summed differences (2¹⁴ patterns for 14 documents); Monte Carlo with 100,000 draws for the 110 documents of the final evaluation | same; notebook 08; `experiments/specs/final_evaluation_v1.json` |
| Descriptive only | McNemar (ignores clustering), leave-one-document-out, document-weighted Δ | each frozen README |
| Multiplicity | one primary contrast per experiment; Holm adjustment where several signals are screened (E9 Stage 0) | `docs/baseline_consolidation_assessment.md` §7.3; notebook 08 |
| Decision rules | typically: gain ≥ +0.05, gain larger than the measured repeat change rate, broken ≤ fixed / 2; from E6 on also a one-sided lower bound > 0 and sign-flip p ≤ 0.05; guardrails on abstention and citation validity | each spec and frozen README |
| Non-inferiority | **not claimed on about 100 questions**: a planning simulation showed an equally good reader passes "95 % lower bound > −0.05" only 26–33 % of the time | `docs/baseline_b1_specification.md` §4.4 |
| Session noise | from E8 on, a repeat arm or a same-session control; any gain smaller than about 7 questions on 102 needs replicates | `docs/validated_baseline_b1.md` §5; `experiments/frozen/e9/README.md` |

With 6 documents (E0–E4) the cluster bootstrap is descriptive and unstable; with 14 (E5–E9) it is usable but still coarse. One question moves accuracy by 0.027 on 37 questions and by about 0.01 on 102.

---

## 5. The experiments

Each entry gives the hypothesis, the design, the result and the decision. Costs are list prices.

### E0 — text vs page images, retrieved vs annotated pages (exploratory)

- **Hypotheses.** H1: images beat text on retrieved pages. H2: the image gain is larger on chart and figure questions. H3: images beat text on annotated (oracle) pages.
- **Design.** A 2 × 2 on dev6 with `gpt-4o-mini-2024-07-18`, temperature 0, one run per condition. Retrieval: BM25 top 5 (k1 1.5, b 0.75) over native text with Tesseract OCR below 30 native words (150 dpi). Text pages truncated at 3,500 characters; images in a 512 × 1024 box (about 60 dpi). Oracle = annotated evidence pages padded to 5. Only the evidence representation changes between conditions.
- **Result** (notebook 03, Results and interpretation; `experiments/frozen/mmlongbench_doc/`):

| | A text, retrieved | B images, retrieved | C text, oracle | D images, oracle |
|---|---|---|---|---|
| correct, answerable | 7/40 (0.175) | 7/40 (0.175) | 9/40 (0.225); 9/38 (0.237) | 11/38 (0.289) |
| correct abstention, 17 unanswerable | 8/17 | 6/17 | — | — |
| citation validity | 1.000 | 0.895 | 1.000 | 0.921 |

  Retrieval (notebook 01): BM25 Recall@5 **0.689** and Hit@5 **0.800** with OCR, against 0.358 on native text only and 0.176 for a random ranking.
- **Findings.** H1 not supported (0.175 = 0.175); images trade errors on retrieved pages (3 fixed, 3 broken). H2 not supported; the pattern follows the document, not the evidence type. H3: direction consistent, not established (6 fixed, 4 broken, McNemar p = 0.75). Text *reading*, not retrieval, limits the text pipeline. Visual reading fails on small detail at about 60 dpi. Image replies sometimes cite the page number printed on the page instead of the supplied `[Page N]` tag.
- **Decision.** No pre-registered rule (exploratory). It motivated E1: test resolution on oracle pages.

### E1 — page-image resolution, 512 px vs 768 px

- **Hypothesis.** On the same annotated evidence pages, a 768-px short side improves accuracy enough to justify the extra input tokens.
- **Design.** 37 matched questions, GPT-4o-mini, prompt `mmlb-image-v1`, 400 output tokens; 512 px, 768 px, and an identical 512-px repeat to measure run-to-run change. Rule: gain ≥ 0.05, gain > repeat change rate, ≤ $0.10 per extra correct answer. Spec `experiments/specs/e1_image_resolution_v1.json`.
- **Result** (`experiments/frozen/e1/README.md`): 512 px 10/37, 512-px repeat 11/37, **768 px 16/37**. Paired: 6 fixed, 0 broken; Δ = 0.162, cluster bootstrap [0.081, 0.296]; repeat changed 1/37. Cost $0.022 per extra correct answer. 21/37 questions are wrong at both resolutions (mostly counting, aggregation and chart reasoning).
- **Decision.** `adopt_768` for this model and population. 768 px is tied to GPT-4o-mini's preprocessing, which reduces a short side above 768 px to 768. The full run executed notebook code committed 16 minutes afterwards (`4d202d5`); all 113 requests are rebuilt byte for byte, but the executed source is not bound by a hash (Limitation 6).

### E2 — a stronger VLM: Qwen3-VL-8B vs GPT-4o-mini

- **Hypothesis.** Qwen3-VL-8B-Instruct, given exactly E1's requests, answers more of the 37 questions correctly at 768 px.
- **Design.** Served through OpenRouter, pinned to one provider in bf16 with fallbacks disabled; same messages, image bytes and parameters as E1. Primary: Qwen 768 vs frozen GPT-4o-mini 768, plus a Qwen 768 repeat. Spec v2 (v1's full run was stopped twice by rate limits; v2 changed only execution rules).
- **Result** (`experiments/frozen/e2/README.md`): Qwen 768 **15/37** vs GPT-4o-mini **16/37**; 4 fixed, 5 broken; Δ = −0.027, bootstrap [−0.29, +0.22]. 768 px helps Qwen too (+4 fixed, 0 broken). Qwen's repeat changed 0/37. Qwen's 768-px cell cost $0.014 against $0.255.
- **Decision.** `retain_gpt4o_mini_768`: a tie within noise, not evidence that Qwen reads worse. The hosted weight revision and image preprocessing cannot be verified.

### E3 — text–image fusion

- **Hypothesis.** Adding the extracted page text to the 768-px images improves accuracy over images alone.
- **Design.** 37 questions, GPT-4o-mini, one neutral prompt `mmlb-evidence-v1`; T, I and IT built so that I = IT minus its text parts and T = IT minus its image parts; adjacent counterbalanced triplets; an IT repeat.
- **Result** (`experiments/frozen/e3/README.md`): T **13/37**, I **17/37**, IT **16/37**, IT repeat 16/37. IT − I: 1 fixed, 2 broken, −0.027, bootstrap [−0.11, +0.06]. Images beat text (I − T: 6 fixed, 2 broken). Where IT gave the text-only answer on a question where T and I disagreed, it was right 1 time in 9; an OCR misread ("42" for "12") pulls the fused reader to a wrong sum.
- **Decision.** `retain_image_only_768`. Cost $0.91 for all three E3 runs.

### E4 — the application end to end

- **Question.** How accurate is the application in `src/visualdoc/` as shipped (BM25 top 5, context guard keeping 3–4 pages, 768-px images, GPT-4o-mini), and how much of its error is page selection rather than reading?
- **Design.** APP: the application's own request on all 57 questions. ORACLE: the annotated evidence pages, byte-identical to frozen E1 768-px requests, on the 37 matched questions. Primary: ORACLE − APP on the 37. Margin: the ORACLE vs frozen E1_768 cross-day change rate.
- **Result** (`experiments/frozen/e4/README.md`): APP **11/40** answerable (0.275, cluster 95 % 0.13–0.43); ORACLE **17/37**. ORACLE − APP = +6/37 = 0.162, 8 fixed, 2 broken, bootstrap [0.09, 0.26]; margin 5/37, cleared by one question. The 29 APP errors split into 14 page-selection errors (7 retrieval, 3 context guard, 4 incomplete evidence) and 15 reader errors (8 reasoning or aggregation, 3 visual reading, 4 annotation or scoring issues). Reading still loses more (20/37) than page selection (6/37). The application never abstained when no evidence page was sent (0/11).
- **Decision.** `page_selection_costs_accuracy`, by one question. Spend $1.2006. In-sample: E1–E3 chose the settings on these questions.

### E5 — visual retrieval: evidence (no API call)

- **Hypothesis.** A pretrained visual page retriever puts more annotated evidence in front of the reader than OCR + BM25, counting only the pages that survive the context guard.
- **Design.** 14 documents never used before (held-out-14), 101 evidence questions. Arm A: the application's OCR + BM25. Arm V: ColQwen2 v1.0 (`vidore/colqwen2-v1.0-hf` at `ddc07d23`, a ColPali-family model on a Qwen2-VL-2B backbone), MaxSim over every page, same guard. Spec `experiments/specs/e5_visual_retrieval_v1.json`, committed before any visual score existed.
- **Result** (`experiments/frozen/e5/README.md`):

| After the context guard | A: OCR + BM25 | V: ColQwen2 | V − A (cluster 95 %) |
|---|---:|---:|---|
| Evidence recall (primary) | 0.526 | 0.721 | +0.195 [+0.110, +0.309] |
| Any evidence supplied | 66/101 | 86/101 | +0.198 [+0.102, +0.325] |
| All evidence supplied | 42/101 | 61/101 | +0.188 [+0.099, +0.308] |

  Exact sign-flip p = 0.0005 (all 12 documents with a difference favour V); V better on 12 of 14 documents and worse on none. The gain sits on figures (0.40 → 0.85), layout text (0.45 → 0.76) and OCR'd pages (0.49 → 0.85), little on plain text (0.66 → 0.68). Reciprocal-rank fusion of A and V was worse than V alone (−0.090 [−0.183, −0.026]).
- **Decision.** `visual_improves_evidence`, leading to E6, not to integration. Indexing on the fanless M1: 12.5 s per page, 193 KB of embeddings per page, 4.4 GB of weights.

### E6 — visual retrieval: answers

- **Hypothesis.** ColQwen2's pages lead the same reader to more correct answers than OCR + BM25's pages.
- **Design.** 118 held-out questions; GPT-4o-mini, `mmlb-image-v1`, 768-px images, the same guard and parser; only the page list differs (4 pages for 105 questions, 3 for 13). 118 adjacent counterbalanced pairs. Rule: Δ ≥ 0.05, one-sided lower bound > 0, sign-flip p ≤ 0.05, broken ≤ fixed / 2; guardrails G1 (correct abstentions ≥ A − 2) and G2 (citations).
- **Result** (`experiments/frozen/e6/README.md`): A **25/102** (0.245), V **38/102** (0.373). Δ = +0.127, 13 fixed, 0 broken; cluster 95 % [0.074, 0.193], one-sided lower bound 0.082; exact sign-flip p = 2⁻¹⁰ ≈ 0.00098. V ≥ A on all 14 documents. G1 held at its limit (7 vs 9 of 16). Under S-v2: 28/101 → 39/101.
- **Decision.** `adopt_visual_retrieval`. Spend $3.7213 (the run paused once when the API credit ran out and resumed in place; every pair stayed adjacent). The 14 documents become development data from here on.

### E7 — extract-then-answer

- **Hypothesis.** Reading each page separately into a structured Evidence Memory, then answering in a text-only step with optional deterministic arithmetic (X4), beats E6's one-shot reader on the same pages (V0), especially on multi-page questions.
- **Motivation.** E6's one-shot reader answered 7 of 46 multi-page questions; 27 of its 64 errors happened with sufficient evidence in front of it (notebook 06, Method).
- **Design.** Same 118 questions, now explicitly a development set (inspected answer by answer to design E7). V0 = E6 V's request byte for byte; X4 on V0's pages; X8 on ColQwen2's top 8. 1,309 calls in 118 seeded blocks.
- **Result** (`experiments/frozen/e7/README.md`): V0 **38**, X4 **31**, X8 **29** of 102. X4 − V0 = −0.069, 3 fixed, 10 broken, cluster 95 % [−0.135, −0.008]. The structured contract raised citation validity from 0.93 to 0.99. Per-page facts lose visual and layout properties (signatures, colours, chart counts, flowchart order). Under S-v2: V0 39/101, X4 33/101, X8 31/101.
- **Decision.** `regression`: keep one-shot reading. Spend $5.911057. Image calls and text-only reasoning calls ran on different backends, so the architecture effect cannot be separated from that split.

### Consolidation into B1 (notebook 07, offline)

- **Retrieval complementarity.** At 4 pages on 141 evidence questions: complete evidence from ColQwen2 only 32, BM25 only 4, both 60, neither 45. Against ColQwen2 on the 101 held-out evidence questions, Complete@4 of RRF is −0.079 [−0.167, −0.016] and of interleaving −0.059 [−0.133, −0.009]. A perfect per-question choice between the two would add only +0.04. In E6, no question was answered correctly only with BM25's pages. Rule fixed before computing: not met. **ColQwen2 stays primary; BM25 is the fallback, a logged second ranking and the text layer for grounding checks.**
- **Scoring protocol S-v2** defined and applied (section 4.2).
- **Product contract.** One English PDF up to about 200 pages, born-digital or best effort; questions answerable from that document alone (`docs/baseline_b1_specification.md` §3).
- **Model-specific limits identified.** The 4-page cap and 768 px came from GPT-4o-mini's image billing (25,501 tokens per 768-px page), not from the architecture (`docs/baseline_consolidation_assessment.md` §5.1). `gpt-4o-mini-2024-07-18` shuts down on 2027-01-14; OpenAI names `gpt-6-luna` as its replacement.

### E8 — reader migration and the B1 contract

- **Question.** Can `gpt-6-luna` replace GPT-4o-mini as the reader on the same pages, with a strict structured contract, reliably and at a feasible cost?
- **Smoke (6 calls, $0.0015431).** Measured what the documentation does not state: `reasoning_effort: none` and `temperature: 0` accepted; strict `json_schema` accepted; no system fingerprint returned; a prompt-token model (o200k_base text + 10 or 9 framing tokens + `floor(1.2 × ceil(w/32) × ceil(h/32))` per image + 100 for the strict schema) that reproduces all six observed totals (`docs/baseline_b1_specification.md` §6.1). A portrait page contributes 920 tokens and a landscape page 1,237, against 25,501 per 768-px page for GPT-4o-mini.
- **Design.** 118 questions, three arms: L-v1 (new reader, E6 V's exact pages and old contract), L-B1 (ColQwen2 top 4, contract b1: strict schema with verbatim evidence quotes, 800 output tokens) and L-B1r (an independent repeat of L-B1). Anchors: frozen E6 V and E7 V0, 38/102 each. Rules: technical gate; material harm = Δ ≤ −0.05 and upper bound < 0 against both anchors; contract adopted if schema validity ≥ 99 %, citation validity ≥ L-v1 − 0.03 and Δ ≥ −0.05; > 10 flips marks instability; ≥ 5 correct abstentions.
- **Result** (`experiments/frozen/e8/README.md`, `tables/evaluation_summary.json`):

| | L-v1 | L-B1 | L-B1r |
|---|---:|---:|---:|
| S-v1 correct / 102 | 42 | 46 | 46 |
| correct abstentions / 16 | 8 | 9 | 9 |
| citation validity | 1.000 | 1.000 | 1.000 |

  L-v1 − E6 V: +0.039 [−0.045, +0.138]. L-B1 − L-v1: +0.039 [−0.019, +0.098], 8 fixed, 4 broken. 4 correctness flips between L-B1 and L-B1r (S-v1); 7 under S-v2. S-v2: L-B1 47/101 vs L-v1 44/101 (`docs/validated_baseline_b1.md` §2). 354/354 first-attempt successes, one served model string, $0.144765.
- **Grounding diagnostic (outside the decision rule).** L-B1 passes 70/118 replies: quotes supported on 88/118, numeric support on 25/53 applicable. A grounding *failure* made an answer *more* likely to be correct (P(wrong | fails) 0.39 vs P(wrong | passes) 0.67 on L-B1; replicated on L-B1r), so grounding is a trust signal for the user, not a repair trigger (`docs/e9_proposal.md` §1).
- **Decision.** Under S-v1 the frozen rules **promote B1**. This is **non-inferiority, not a demonstrated gain**: the +4-question margin sits inside the 4–7-question replicate churn. B1 is frozen (`docs/validated_baseline_b1.md`).

### E9 — adaptive evidence acquisition

- **Motivation.** B1's ColQwen2 top 4 miss part of the annotated evidence for 39 of 101 questions. The grounding check cannot serve as a trigger (E8), so E9 tests a *retrieval-uncertainty* trigger instead (`docs/e9_proposal.md`).
- **Pre-registration.** Spec `experiments/specs/e9_adaptive_evidence_v1.json` (commit `7f41eea`, before any analysis) and a technical addendum (commit `a30bb29`, before any paid call). The design in the proposal changed before the freeze: the control became a same-session re-run of B1 (B1s) instead of the frozen E8 replies.
- **Stage 0 (offline, $0)** (`experiments/frozen/e9_stage0/README.md`). Five signals screened against "evidence not fully in the top 4" with a five-condition gate (AUROC ≥ 0.65, Holm p ≤ 0.05, lift ≥ +0.15 with lower bound > 0, every leave-one-document-out AUROC ≥ 0.60, ≥ 6 recoverable questions triggered). Only **U3, the flatness of the top-8 MaxSim scores, −(s₁ − s₈)/s₁**, passed: AUROC 0.783 [0.661, 0.861], Holm p 0.0005, lift +0.239 [+0.095, +0.362], minimum leave-one-document-out AUROC 0.752, 8 recoverable questions triggered. Threshold −0.153079 fires on 47 of 118 questions. Numeric support of the answer (U5) was at chance (AUROC 0.47). **The audit's main finding, recorded before any paid call:** U3 predicts *incomplete* evidence but not evidence that 8 pages would *complete* (AUROC 0.480), so A1 − B1s could not exceed about +0.069.
- **Stage 2 design.** One session, 354 calls: B1s (top 4, requests byte-identical to frozen E8 L-B1), F8a and F8b (top 8, two replicates). A1a and A1b are derived without a call: the F8 reply where U3 fires, the B1s reply elsewhere. Primary: A1 − B1s, replicate-averaged.
- **Result** (`experiments/frozen/e9/README.md`, `tables/evaluation_summary.json`):

| | B1s | F8a | F8b | A1a | A1b |
|---|---:|---:|---:|---:|---:|
| S-v1 correct / 102 | 44 | 46 | 46 | 47 | 46 |
| correct abstentions / 16 | 9 | 9 | 8 | 9 | 9 |
| mean prompt tokens | 3,977 | 7,641 | 7,641 | 5,421 | 5,421 |

| Contrast (S-v1) | Δ | 95 % CI | sign-flip p |
|---|---:|---|---:|
| **A1 − B1s (primary)** | **+0.025** | [0.000, +0.051] | 0.125 |
| F8 − B1s | +0.020 | [−0.048, +0.079] | 0.33 |
| A1 − F8 | +0.005 | [−0.050, +0.065] | 0.50 |
| F8 − B1s, triggered questions | +0.061 | [0.000, +0.125] | 0.125 |
| F8 − B1s, untriggered questions | −0.008 | [−0.103, +0.079] | 0.63 |

  A1 fixed 3 and broke 0 (replicate a), fixed 2 and broke 0 (replicate b). Guardrails pass; the engineering criterion (+0.05 on average and in each replicate: +0.025, +0.029, +0.020) fails. **Session drift:** on byte-identical requests sent the same day, B1s scored 44 against frozen E8 L-B1's 46 (6 flips).

  **S-v2 (secondary).** 13 new arm-blind gray items await the owner's labels. With every pending item counted wrong, A1 − B1s is +0.025; with every pending item counted correct, +0.020 (`tables/evaluation_summary.json`). These two values are *not* bounds: over every consistent labelling of the 13 items, the independent Stage 2 audit puts A1 − B1s in **[+0.005, +0.040]** ([+0.005, +0.042] if "unsure" is allowed). No labelling reaches +0.05 or −0.05, so S-v2 cannot change the verdict (`experiments/frozen/e9/AUDIT.json`, README). **Labelled 2026-11-27** (`experiments/frozen/e9_scoring_v2/`, 7 correct, 6 wrong): B1s 47, A1a 49, A1b 49 of 101; A1 − B1s **+0.020** [−0.005, +0.050], sign-flip p 0.19. The verdict stands.

  **Caveats from the independent Stage 2 audit** (`experiments/frozen/e9/AUDIT.json`: 47/47 checks passed, verdict confirmed; script in `audit/audit_e9_stage2.py`). The counts below were also re-checked against the frozen execution log and per-question table:
  - **Provider prompt caching was active.** 104 of 118 F8b calls and 54 of 118 F8a calls reused a cached prompt prefix; B1s calls did not. Replies were still generated afresh: 37 of 118 F8a and F8b replies differ. Without caching, the full run would have cost $0.236 instead of the observed $0.147055.
  - **The fingerprint guard could never fire.** `system_fingerprint` was `None` on every E8 and E9 call, so only the served-model string guarded against a silent model change.
  - **The smallest attainable sign-flip p was 0.125.** Only 3 of the 14 documents had a non-zero A1 − B1s, so 2³ sign patterns carry all the information; p = 0.125 is the floor, not a near miss.
  - **The single invalid citation in F8a and F8b** (citation validity 0.992) is a *missing* citation: a non-abstaining answer with empty `cited_pages` on `mmlb-0579`, not a page outside those supplied.
  - **Counterbalance.** B1s went first in 59 of 118 pairs, but in 55 of the 102 answerable pairs (47 F8a-first).
- **Decision.** `no_meaningful_gain`. B1 keeps k = 4 and one read; the application does not implement adaptive acquisition. (On held-out data, the same policy was re-tested as the final evaluation's secondary claim C3: +0.021, `a1_gain_supported` but fragile, reported only; section 9.) Always reading 8 pages is not better than 4 for this reader, so the GPT-4o-mini-era 4-page cap costs no measurable accuracy and halves prompt tokens. Spend $0.151647 of a $0.50 ceiling (smoke $0.004592, full run $0.147055, lowered by the prompt caching noted above).

### E10 — an agentic reader: search, read, finish

- **Motivation.** B1 answers 4 of the 39 questions whose evidence is incomplete in its top 4. Reading deeper down the same ranking completes only 8 of them (E9 Stage 0). E10 lets the reader write **new queries**. Design and reasoning: `docs/e10_agentic_reader_proposal.md`.
- **Pre-registration.** Spec `experiments/specs/e10_agentic_reader_v1.json` (commit `25cd488`, before any paid call).
- **Design.**
  - **Warm start:** the first message holds B1's exact top 4 pages.
  - **Tools:** `search_pages` (ColQwen2 MaxSim over all pages, numbers only), `read_pages` (≤ 4 images) and `finish` (B1's strict schema).
  - **Limits:** ≤ 6 calls, ≤ 12 pages, a pre-call cost check, finish forced on the last call.
  - **Reader:** the same as B1.
  - **Arms:** B1s (byte-identical to frozen E8 L-B1), AGa and AGb, in 118 counterbalanced blocks.
  - **Search encoder:** queries encoded on the Datalab CPU, a new condition. The parity gate passed: top-4 set 113/118, recall@4 0.723 vs 0.726.
- **Result** (`experiments/frozen/e10/README.md`, `tables/evaluation_summary.json`; audit 31/31):

| | B1s | AGa | AGb |
|---|---:|---:|---:|
| S-v1 correct / 102 | 45 | 53 | 53 |
| correct abstentions / 16 | 8 | 9 | 12 |
| evidence recall of pages seen (101) | 0.726 | 0.868 | 0.864 |
| calls / pages seen per question | 1 / 4 | 3.35 / 6.75 | 3.27 / 6.81 |
| cost per question | $0.0004 | $0.0018 | $0.0017 |

| Contrast (S-v1) | Δ | 95 % CI | sign-flip p |
|---|---:|---|---:|
| **AG − B1s (primary)** | **+0.078** | [0.000, +0.181] | 0.053 |
| evidence recall of pages seen | +0.140 | [+0.084, +0.198] | 0.0002 |
| AG − B1s, evidence incomplete in top 4 (39) | +0.256 | [+0.136, +0.500] | 0.001 |
| AG − B1s, elsewhere (63) | −0.032 | [−0.129, +0.085] | 0.75 |

  - Fixed / broken: AGa 13 / 5, AGb 17 / 9. All broken questions had complete evidence in B1's top 4.
  - The 5 questions broken in both replicates fail for three reasons:
    - over-exploration (2);
    - a different reading of the same 4 pages in tool mode (2);
    - an answer-format artefact (1).
  - **Exploratory.** The agent's own stopping decision is a better router than E9's U3 trigger (U3-routed 46/49 vs always-agent 53).
  - **S-v2** (secondary, owner's 17 blind labels, `experiments/frozen/e10_scoring_v2/`): B1s 47, AGa 55, AGb 57 of 101; AG − B1s **+0.089** [+0.017, +0.177], sign-flip p = 0.025; fixed / broken 13 / 5 and 16 / 6. The broken-ratio rule would not fire under S-v2, but the replicates still disagree on 12 questions (> 10), so even S-v2 would not give `go`. The verdict stays the frozen S-v1 one.
- **Decision.** `regression` under the frozen rule "broken > fixed / 2 in either replicate" (AGb 9 > 8.5). Without it the verdict would be `promising_but_uncertain` (p 0.053, 12 flips > 10). B1 is unchanged. The record supports the mechanism, more evidence found and turned into answers where B1 lacks it, but not a clean improvement. Spend $0.473375 of a $3.50 ceiling.

---

## 6. Negative and null results

| Experiment | What was expected | What happened | What it rules out (on this data) |
|---|---|---|---|
| E0 H1, H2 | images beat text on retrieved pages, more so on charts | 7/40 = 7/40; errors traded | page images as a free accuracy gain at about 60 dpi |
| E2 | a stronger open VLM reads better | 15/37 vs 16/37, 4 fixed / 5 broken | a reader swap as the bottleneck fix |
| E3 | text + images beat images | 16/37 vs 17/37; text pulls the reader to OCR errors | fusing OCR text into the reader's prompt |
| E5 (exploratory) and notebook 07 | fusing BM25 and ColQwen2 rankings helps | RRF −0.090 (E5), −0.079 (notebook 07) vs ColQwen2 alone | static retrieval fusion |
| E7 | extract-then-answer fixes multi-page and reading errors | −0.069 [−0.135, −0.008], 3 fixed / 10 broken | per-page textualisation of evidence |
| E8 (diagnostic) | grounding failures flag wrong answers | they flag *correct* answers more often | grounding as a repair trigger |
| E9 | an uncertainty trigger plus 8 pages recovers answers | +0.025, p = 0.125; F8 not better than 4 pages | adaptive deepening as a material gain at this sample size (held out, a small gain of +0.021 appeared: section 9) |
| E10 | an agent that searches with its own queries is better than B1 | +0.078 net, p = 0.053, but AGb broke 9 vs 17 fixed (rule: ≤ fixed/2) | an agent as a clean improvement; it does show the search mechanism works (evidence recall +0.140) |

These are reported with the same weight as the positive results. Several are "ties within noise" rather than evidence of harm (E2, E3); E7 is the only negative result whose interval excludes zero.

---

## 7. Threats to validity

**Internal validity**
- **Reused development data.** E1–E4 were tuned in-sample on dev6; held-out-14 became development data after E6 and was reused by E7, E8 and E9. Selection bias accumulates with each reuse.
- **Session drift and an unpinnable reader.** `gpt-6-luna` is an alias with no dated snapshot and returned no system fingerprint on any E8 or E9 call, so a silent change of backend would show only through the served-model string. In E9, provider prompt caching was active on most F8 calls (replies were still generated afresh). Identical requests at temperature 0 flip 4–8 questions between sessions (E8: 4 under S-v1; E9: 6 against L-B1, 8 against L-B1r). Earlier experiments saw a backend fingerprint change between sessions (E4 against E1), within a resumed run (E6), and a backend split by request type (E7).
- **Bundled factors.** E4's gap mixes missing evidence, extra pages, order and length; E6's difference mixes evidence availability with distractors and page order; E7's X4 bundles page-wise reading, structured evidence, text-only reasoning and an arithmetic tool.
- **Provenance gaps.** E1's executed code was committed 16 minutes after the run (rebuilt byte for byte, not hash-bound). E2's hosted weights and preprocessing cannot be verified.
- **Corrections recorded, not hidden.** A Stage 0 validation cell of notebook 08 first asserted a wrong expectation about a within-document null; it was corrected without changing the frozen gate (`experiments/frozen/e9/PROVENANCE.json`).

**Measurement validity**
- **Local scoring.** S-v1 is a re-implementation without the benchmark's GPT-4o extraction; it gives partial ANLS credit and scored a wrong reply 0.951 and correct verbose replies 0 (notebook 07, Method B). S-v2 depends on one adjudicator's blind labels; across the two adjudication rounds, human judgment disagreed with the automatic scorer on 13 of 58 gray arm-cells (`docs/validated_baseline_b1.md` §4).
- **Single-annotator evidence.** A page that answers but is not annotated counts as missing for every retriever and every recall figure.
- **Citation validity is form, not support.** It checks that cited pages were supplied, not that they contain the answer; the grounding check is stricter but anti-predictive of correctness on this data.

**Statistical conclusion validity**
- **Small, clustered samples.** 37 questions in 6 documents (E1–E4) and 102 in 14 (E6–E9). Planned power to show a +0.05 gain on 102 questions was 19–27 % (`docs/baseline_consolidation_assessment.md` §4.2, planning simulation).
- **Coarse bootstrap.** Percentile intervals over 14 clusters may be slightly narrow (`notebooks/08`, recorded deviation 2).

**External validity**
- **One benchmark, a thin core scope.** Only 6 of the 20 development documents are born-digital report-type, and two 10-Ks hold 31 of their 57 evidence questions (notebook 07). In the final evaluation the core scope is 32 of 110 documents (207 answerable questions).
- **Possible training overlap.** ColQwen2's training data may overlap benchmark pages; that would favour visual retrieval and cannot be checked (`experiments/frozen/e5/README.md`).
- **Model-specific settings.** 768 px and the 4-page cap were chosen for GPT-4o-mini; E9 showed the cap costs no measurable accuracy for `gpt-6-luna`, but resolution was not re-tested for it.
- **Laptop constraints shaped selection.** E5 capped held-out documents at 100 pages for compute reasons, which excluded long filings. The final evaluation had no page cap, but only 4 of its answerable questions are on documents over 200 pages.

**Specific to the final evaluation**
- **One run per arm.** Reader noise is not part of the test. E8 measured 4–7 flips between identical replicates on 102 questions; C2's 80 net questions are far above that, C3's 14 are closer to it (`experiments/frozen/final/README.md`).
- **Deviations.** D1 excluded one document whose served bytes did not match the pinned revision, before any question was read; D2 fixed an S-v1 crash after the run but before any number was computed (2 replies affected). Both are recorded in `experiments/specs/final_evaluation_v1_deviations.md`.
- **Two audit findings.** The independent audit passed 36 of its 38 integrity checks. The two failures are low-severity and recorded: the token model undercounted 49 calls by 1–8 prompt tokens through floating-point rounding (146 tokens in all; costs come from billed usage and are unaffected), and D2's committed text quotes one pool reference answer, now entered in the ledger (`experiments/frozen/final/AUDIT.json`, checks 1.15 and 5.03; `experiments/test_pool_ledger.md`).

---

## 8. Development versus confirmatory evidence

| Evidence | Status | Why |
|---|---|---|
| E0 | exploratory | no pre-registered rule; 6 documents |
| E1–E4 | pre-registered, development | specs frozen before calls, but on dev6, where the settings were chosen (in-sample) |
| E5, E6 | pre-registered, **first use** of 14 new documents | the closest the development record has to a confirmatory test; only 14 documents, which were then reused |
| E7, B1 consolidation, E8, E9 | pre-registered, development | the 118 questions were inspected to design these experiments |
| Final held-out evaluation | **confirmatory, run once (2026-11-26)** | 110 documents never used in development; spec approved and frozen before any pool document was downloaded; index frozen before any question was read; one reader session |

Only C2 of the final evaluation is a confirmatory test. C1 is an estimate, and C3 is a pre-registered secondary contrast that cannot change the shipped system. Development figures should be quoted as development figures; the held-out accuracy of B1 is 0.427.

---

## 9. The final held-out evaluation

Sources: `experiments/frozen/final/README.md`, `tables/evaluation_summary.json`, `AUDIT.json`, `PROVENANCE.json`; `experiments/frozen/final_index/README.md`; `experiments/frozen/final_retrieval/README.md`; `experiments/specs/final_evaluation_v1.json`, `final_evaluation_v1_plan.json`, `final_evaluation_v1_deviations.md`; notebook 09, cell `fe-results`.

### 9.1 Protocol and order of operations

| Step | Commit | What it fixed |
|---|---|---|
| Specification approved by the owner and frozen (2026-11-25) | `1c54a3e` | population, indexing order, parity gate, arms, scoring, decision rules, a $2.50 ceiling, laptop indexing |
| Deviation D1 | `dfeaad0`, `476b156` | documents whose bytes do not match the hash recorded at the pinned revision are excluded; `mi_phone.pdf` is the only one (committed before any question was read) |
| Index frozen | `ab8a9c8` | 110 documents, 5,554 pages (5,348 distinct images), ColQwen2 page embeddings on the M1 GPU after a parity gate that reproduced E5 bit for bit; **no question read** |
| Questions encoded, retrieval and plan frozen | `8d5768a` | ColQwen2 and BM25 rankings for 872 questions; development rankings 118/118 equal to E5's (maximum score difference 5.0e-07) and development requests 118/118 equal to frozen E8; U3 fires on 335 questions (38.4 %; development 39.8 %); a 2,079-call plan with an upper bound of $1.831161 |
| Reader session (2026-11-26) | run launched at `61f769f` | 6-call smoke on development questions, then 2,079 calls; all first-attempt successes; one served model, `gpt-6-luna`; no system fingerprint |
| Deviation D2 | `bcf0345` | after the run, before any number: the frozen S-v1 copy crashed on a non-numeric reply to a `$`-formatted Float reference; such replies now score 0, as in the official code (2 replies, both on `mmlb-1087`); the wrapper reproduces all 708 frozen E8 and E9 S-v1 scores |
| Evaluation, audit and freeze | `c6c450d` | `experiments/frozen/final/` |

**Arms.** All use the same reader as B1 (`gpt-6-luna`, contract b1, temperature 0, reasoning effort none); only the pages differ.

| Arm | Pages | Role |
|---|---|---|
| **B1** | ColQwen2 v1.0 top 4 | the selected system |
| **T1** | OCR + BM25 top 4 | text-retrieval baseline for the confirmatory contrast |
| **A1** | ColQwen2 top 8 when E9's frozen trigger U3 fires (335 questions), otherwise B1's reply | secondary contrast only; B1 stays the shipped system whatever A1 scores |

**Decision rules** (`experiments/specs/final_evaluation_v1.json`). C2 is `visual_retrieval_confirmed` if Δ > 0, the one-sided bootstrap 5th percentile > 0 and the sign-flip p ≤ 0.05; `reversed` if the 97.5th percentile < 0; otherwise `visual_retrieval_not_confirmed`. C3 is `a1_gain_supported` if the one-sided 5th percentile > 0 and p ≤ 0.05. Unit: the question, clustered by document; percentile bootstrap with 10,000 draws; Monte Carlo sign-flip test with 100,000 draws.

### 9.2 Results (S-v1, primary)

| Claim | Result | Verdict |
|---|---|---|
| **C1** B1 accuracy, answerable | **288 / 674 = 0.427** [0.386, 0.470]; development estimate 0.451 (46/102) | estimate |
| C1, core scope (32 documents) | 77 / 207 = 0.372 [0.305, 0.443] | estimate |
| **C2** B1 − T1 (confirmatory) | **+0.119** [+0.088, +0.150]; sign-flip p = 1.0e-05; 103 fixed / 23 broken | **`visual_retrieval_confirmed`** |
| **C3** A1 − B1 (secondary) | +0.021 [+0.007, +0.036]; p = 0.0046; 19 fixed / 5 broken | `a1_gain_supported`, reported only |

| | B1 | T1 | A1 |
|---|---:|---:|---:|
| S-v1 correct / 674 answerable | 288 | 208 | 302 |
| Correct abstentions / 198 unanswerable | 120 | 140 | 121 |
| Citation validity | 1.000 | 0.995 | 0.999 |
| Mean prompt tokens | 4,198 | 4,199 | 5,671 |
| Latency p50 / p90 (s) | 2.5 / 5.1 | 2.4 / 4.7 | 3.0 / 6.6 |

**Evidence retrieval at k = 4** (666 answerable questions with annotated evidence): ColQwen2 recall 0.711 against BM25 0.543, +0.168 [+0.130, +0.207]; complete evidence 0.626 against 0.459. The development figures (E5, after the context guard) were 0.721 and 0.526.

**S-v2 (secondary).** 85 arm-blind gray items await the owner's labels (`experiments/frozen/final/adjudication/`). Over every consistent correct/wrong labelling, B1 − T1 stays within [+0.077, +0.150] and A1 − B1 within [+0.015, +0.028]; with "unsure" also allowed, the upper ends rise to +0.159 and +0.031. No labelling can reverse either sign. **Labelled 2026-11-27:** S-v2 with the owner's 85 blind labels (`experiments/frozen/final_scoring_v2/`): B1 − T1 **+0.117** [+0.087, +0.148] and A1 − B1 **+0.022** [+0.009, +0.037], sign-flip p 0.002. Both claims hold, inside the ranges frozen before labelling ([+0.077, +0.150] and [+0.015, +0.028]).

**Independent audit** (`experiments/frozen/final/AUDIT.json`). It reproduced 70 quantities to within 3.7e-11 and passed 36 of 38 integrity checks (the two failures are described in section 7). Robustness variations:
- leave-one-document-out: C2 between +0.1136 and +0.1239, `visual_retrieval_confirmed` in 110 of 110 folds;
- documents weighted equally: C2 +0.1246;
- without the D2 question: C2 unchanged in its verdict; C3 +0.019, p = 0.008, still supported (`experiments/frozen/final/README.md`);
- worst-case S-v2 labelling: C2 still confirmed (+0.077); **C3's sign-flip p rises to 0.049**. With the owner's actual labels C3's p is 0.002.

**Cost.** $0.990233 for the run plus $0.003216 for the smoke = $0.993449 of the $2.50 ceiling; 2,085 calls, all first-attempt successes.

### 9.3 Interpretation

Drawn from `experiments/frozen/final/README.md` (Interpretation) and notebook 09 (`fe-results`).

1. **The central result replicates out of sample, at both layers.** Answers: +11.9 points against +12.7 in development (E6). Evidence: +16.8 points against +19.5 (E5). The answer-level gain is positive in every document type, from +0.026 on financial reports to +0.245 on tutorials; it is larger on figures (+0.171) than on plain text (+0.112) or tables (+0.077), and larger on image-heavy documents (+0.180) than on born-digital ones (+0.091). These subgroup figures are descriptive.
2. **B1's held-out accuracy is 42.7 %,** slightly below the development estimate and inside its interval. More than half of answerable questions remain wrong. Accuracy falls with the number of evidence pages: 54 % for one page, 31 % for 2–3 pages, 13 % for 4+ pages. Gathering evidence across pages remains the main weakness.
3. **E9's adaptive policy shows a small, statistically supported gain on held-out data** that 102 development questions could not resolve. It is fragile: 24 disagreements, one run per arm, p = 0.049 under the worst-case S-v2 labelling (0.002 with the owner's labels), and below E9's pre-registered +0.05 materiality. By the frozen rule B1 stays the shipped system; any adoption would be a new decision tested on new data.
4. **T1 abstains correctly more often (140 vs 120 of 198)** because its pages more often lack the evidence. Answerable accuracy, the primary metric, is what the claims rest on.

### 9.4 Limitations

- One run per arm; single-annotator evidence; a reader alias without a snapshot (frozen replies define the result).
- The core-scope subgroup has only 32 documents, and only 4 answerable questions are on documents over 200 pages.
- The token model undercounts some prompts (`floor(1.2 × tiles)` in floating point): 49 calls were billed 1–8 more prompt tokens than planned. No cost figure is affected; future plans should compute `(12 × tiles) // 10` in integers.
- **The test pool is now used.** It may be reported, but never used to tune a system again. Its use is recorded in `experiments/test_pool_ledger.md`.

---

## 10. Where the sources disagree

Three disagreements found in an earlier version of this report were corrected in `docs/validated_baseline_b1.md` (commit `1c54a3e`): E6's leave-one-document-out range (now +0.113 to +0.149, as in `experiments/frozen/e6/tables/evaluation_summary.json`), the reading of E4 (reading still loses more than page selection), and the size of the test pool. The remaining ones:

| Item | Source 1 | Source 2 | Note |
|---|---|---|---|
| Replicate churn in E8 | `docs/e9_proposal.md` and notebook 08: "7 flips between identical replicates" | `experiments/frozen/e8/README.md`: 4 correctness flips | 4 is under S-v1, 7 under S-v2 (`docs/validated_baseline_b1.md` §2) |
| E7 cost per call count | `docs/e9_proposal.md` §7: "E7's 1,309-call run cost $5.911057" | `experiments/frozen/e7/README.md`: $5.911057 is smoke + full ($0.063019 + $5.848038) | the 1,309-call full run alone cost $5.848038 |
| Evicted source PDFs | `docs/validated_baseline_b1.md` §5: 11 of 24 | `docs/PROGRESS.md`: 12 | iCloud eviction changes over time |
| E0 text run-to-run changes | `experiments/README.md`: 3–6 of 57 | `experiments/frozen/mmlongbench_doc/README.md`: 4–6 of 57 | both describe the 2026-11-19 text runs |
| Final-evaluation claim numbering | `docs/final_evaluation_specification.md` (draft): C3 = secondary estimates, C4 = subgroups, A1 optional | `experiments/specs/final_evaluation_v1.json` (frozen): C3 = the A1 contrast; abstention, citations and recall are secondary metrics; subgroups descriptive | the frozen JSON takes precedence, as the draft itself states |
| Final-evaluation audit status | `experiments/frozen/final/README.md` and notebook 09: the audit "reproduced all 70 quantities" | `experiments/frozen/final/AUDIT.json`: `all_checks_passed: false` (36 of 38 integrity checks) | both are true; the two failed checks are the low-severity findings in section 7, also recorded in `docs/PROGRESS.md` |

---

## 11. Spend

| Experiment | Calls | List-price USD | Source |
|---|---:|---:|---|
| E0–E7 | — | about 13 in all | `docs/baseline_consolidation_assessment.md` §1.1 |
| E1 (smoke, pilot, full) | 113 in the full run | about 0.59 | `experiments/frozen/e1/README.md` |
| E2 (four runs) | 113 in the frozen run | 0.0436 (OpenRouter actual charge) | `experiments/frozen/e2/README.md` |
| E3 (three runs) | 151 in the full run | 0.91 | `experiments/frozen/e3/README.md` |
| E4 | 2 + 96 | 1.2006 | `AGENTS.md` |
| E5 | 0 | 0 | `experiments/frozen/e5/README.md` |
| E6 | 2 + 238 | 3.7213 | `AGENTS.md` |
| E7 | 11 + 1,309 | 5.911057 | `AGENTS.md` |
| E8 | 6 + 354 | 0.0015431 + 0.144765 | `AGENTS.md` |
| E9 | 6 + 354 | 0.151647 | `experiments/frozen/e9/README.md` |
| Final evaluation | 6 + 2,079 | 0.003216 + 0.990233 = 0.993449 | `experiments/frozen/final/README.md` |
| E10 | 27 + 899 | 0.017513 + 0.455862 = 0.473375 | `experiments/frozen/e10/README.md` |

---

## 12. Provenance

| Artifact | Location |
|---|---|
| E0 canonical runs | `experiments/frozen/mmlongbench_doc/` |
| E1–E7 runs, tables, audits | `experiments/frozen/e1/` … `e7/` |
| S-v2 owner labels | `experiments/frozen/scoring_v2/` (E6/E7), `experiments/frozen/e8_scoring_v2/` (E8), `experiments/frozen/e9_scoring_v2/` (E9), `experiments/frozen/final_scoring_v2/` (final), `experiments/frozen/e10_scoring_v2/` (E10) |
| E8 smoke and execution | `experiments/frozen/e8_smoke/`, `experiments/frozen/e8/` (commit `0d68a93`) |
| E9 Stage 0 | `experiments/frozen/e9_stage0/` (commit `a30bb29`) |
| E9 Stage 1–2 | `experiments/frozen/e9/` (commit `7f6c744`; independent audit 47/47); S-v2 labels in `experiments/frozen/e9_scoring_v2/` |
| Final evaluation: index | `experiments/frozen/final_index/` (commit `ab8a9c8`, before any question was read) |
| Final evaluation: retrieval | `experiments/frozen/final_retrieval/` (commit `8d5768a`) |
| Final evaluation: run, evaluation, audit | `experiments/frozen/final/` (commit `c6c450d`); S-v2 labels in `experiments/frozen/final_scoring_v2/` |
| E10 agentic reader | `experiments/frozen/e10/` (spec commit `25cd488`; audit 31/31); S-v2 labels in `experiments/frozen/e10_scoring_v2/` |
| Specifications | `experiments/specs/` (E1–E9, E2 v1 superseded by v2, E9 addendum; `final_evaluation_v1.json` with its plan and deviations) |
| Baseline description | `docs/validated_baseline_b1.md` |
| Test-pool record | `experiments/test_pool_ledger.md` |
| Reproduction | notebooks 00–09 in their default modes; see `docs/reproducibility.md` |
