# VisualDoc AI: research report, E0–E9

- **Date:** 2026-11-25.
- **Scope:** every experiment from E0 to E9, the consolidation into the validated baseline B1, and the pending final held-out evaluation.
- **Status of the evidence:** **all results in this report are development results.** They come from 20 MMLongBench-Doc documents that shaped the design. No result exists on the untouched test pool; the final evaluation that would produce one is specified only as a draft and is not approved (`docs/final_evaluation_specification.md`).
- **Sources:** every number is taken from a frozen package in `experiments/frozen/`, from `AGENTS.md` (regression references), or from the documents in `docs/`. The source is named beside each table. Where two sources disagree, both are given (section 10).

---

## 1. Summary

The project asks how to answer questions about long PDF documents with **cited, checkable answers**, and which design choices actually matter. It started from one controlled comparison (extracted text vs rendered page images) and moved, one pre-registered experiment at a time, to a frozen pipeline called **B1**: ColQwen2 visual retrieval over page images, the top 4 pages, one `gpt-6-luna` call with a strict JSON contract, then deterministic citation and grounding checks.

What the record supports:

1. **Visual retrieval beats OCR + BM25** for evidence (E5: recall after the context guard 0.526 → 0.721) and for answers (E6: 25/102 → 38/102, 13 fixed, 0 broken, document-cluster 95 % interval [0.074, 0.193]). This is the project's one strong result.
2. **Per-page extract-then-answer is worse than one-shot reading** (E7: −0.069, interval [−0.135, −0.008]). A supported negative result.
3. **Several plausible changes did not help:** a stronger open VLM (E2), adding OCR text to images (E3), adaptive reading of more pages (E9). These are reported as negative or null results.
4. **The B1 output contract is non-inferior, not better**, than the previous contract (E8: 46 vs 42 of 102, interval [−0.019, +0.098]); it adds valid citations and verbatim quotes.
5. **The ceiling is evidence supply.** B1 answers 46 of 102 answerable development questions; ColQwen2's top 4 pages miss part of the annotated evidence for 39 of 101 questions (E9 Stage 0).

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

---

## 3. Data

**Benchmark.** MMLongBench-Doc (`yubo2333/MMLongBench-Doc`), pinned at revision `2ff6aa9237fc777b6627dc57a486e9225ac5fb86`. 1,091 questions over 135 PDFs; 847 answerable and 244 unanswerable (22.4 %). Evidence is annotated as 1-based physical page numbers, which notebook 00 verifies rather than assumes. Licence CC BY-NC 4.0, research use only. (Notebook 00 §1; `data/external/README.md`.)

| Population | Documents | Questions | Used by | Notes |
|---|---:|---:|---|---|
| dev6 | 6 | 57 (40 answerable, 17 unanswerable) | E0–E4 | seeded draw (seed 42) of documents ≤ 15 MB; 195 pages, 120 needed OCR; E1–E3 use the 37 answerable questions whose evidence fits the context at both resolutions |
| held-out-14 | 14 | 118 (102 answerable, 16 unanswerable; 101 with annotated evidence) | E5, E6; then E7–E9 as development data | two documents per benchmark type, seeded, ≤ 100 pages each, 647 pages; never used before E5 |
| **Development total** | **20** | **175** | — | every design decision rests on these |
| Untouched test pool | 115 | 916 (705 answerable) | nothing yet | the final evaluation would use 111 of them (section 9) |

Sources: notebook 00 (§1–4), `experiments/frozen/e5/README.md`, `experiments/test_pool_ledger.md`, `docs/baseline_consolidation_assessment.md` §4.2.

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
| Paired test | exact document sign-flip test on per-document summed differences (2¹⁴ patterns for 14 documents); Monte Carlo when exact enumeration is impossible | same; notebook 08 |
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

  **S-v2 (secondary).** 13 new arm-blind gray items await the owner's labels. With every pending item counted wrong, A1 − B1s is +0.025; with every pending item counted correct, +0.020 (`tables/evaluation_summary.json`). These two values are *not* bounds: over every consistent labelling of the 13 items, the independent Stage 2 audit puts A1 − B1s in **[+0.005, +0.040]** ([+0.005, +0.042] if "unsure" is allowed). No labelling reaches +0.05 or −0.05, so S-v2 cannot change the verdict (`experiments/frozen/e9/AUDIT.json`, README).

  **Caveats from the independent Stage 2 audit** (`experiments/frozen/e9/AUDIT.json`: 47/47 checks passed, verdict confirmed; script in `audit/audit_e9_stage2.py`). The counts below were also re-checked against the frozen execution log and per-question table:
  - **Provider prompt caching was active.** 104 of 118 F8b calls and 54 of 118 F8a calls reused a cached prompt prefix; B1s calls did not. Replies were still generated afresh: 37 of 118 F8a and F8b replies differ. Without caching, the full run would have cost $0.236 instead of the observed $0.147055.
  - **The fingerprint guard could never fire.** `system_fingerprint` was `None` on every E8 and E9 call, so only the served-model string guarded against a silent model change.
  - **The smallest attainable sign-flip p was 0.125.** Only 3 of the 14 documents had a non-zero A1 − B1s, so 2³ sign patterns carry all the information; p = 0.125 is the floor, not a near miss.
  - **The single invalid citation in F8a and F8b** (citation validity 0.992) is a *missing* citation: a non-abstaining answer with empty `cited_pages` on `mmlb-0579`, not a page outside those supplied.
  - **Counterbalance.** B1s went first in 59 of 118 pairs, but in 55 of the 102 answerable pairs (47 F8a-first).
- **Decision.** `no_meaningful_gain`. B1 keeps k = 4 and one read; the application does not implement adaptive acquisition. Always reading 8 pages is not better than 4 for this reader, so the GPT-4o-mini-era 4-page cap costs no measurable accuracy and halves prompt tokens. Spend $0.151647 of a $0.50 ceiling (smoke $0.004592, full run $0.147055, lowered by the prompt caching noted above).

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
| E9 | an uncertainty trigger plus 8 pages recovers answers | +0.025, p = 0.125; F8 not better than 4 pages | adaptive deepening as a material gain at this sample size |

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
- **One benchmark, a thin core scope.** Only 6 of the 20 development documents are born-digital report-type, and two 10-Ks hold 31 of their 57 evidence questions (notebook 07).
- **Possible training overlap.** ColQwen2's training data may overlap benchmark pages; that would favour visual retrieval and cannot be checked (`experiments/frozen/e5/README.md`).
- **Model-specific settings.** 768 px and the 4-page cap were chosen for GPT-4o-mini; E9 showed the cap costs no measurable accuracy for `gpt-6-luna`, but resolution was not re-tested for it.
- **Laptop constraints shaped selection.** E5 capped held-out documents at 100 pages for compute reasons, which excluded long filings.

---

## 8. Development versus confirmatory evidence

| Evidence | Status | Why |
|---|---|---|
| E0 | exploratory | no pre-registered rule; 6 documents |
| E1–E4 | pre-registered, development | specs frozen before calls, but on dev6, where the settings were chosen (in-sample) |
| E5, E6 | pre-registered, **first use** of 14 new documents | the closest the record has to a confirmatory test; still only 14 documents, and the documents were then reused |
| E7, B1 consolidation, E8, E9 | pre-registered, development | the 118 questions were inspected to design these experiments |
| Final held-out evaluation | **confirmatory, not run** | specified only as a draft; no pool document has been downloaded, indexed or run |

No result on the untouched pool exists. A headline accuracy for B1 should not be quoted from development data as if it were a held-out estimate.

---

## 9. The pending final held-out evaluation

Source: `docs/final_evaluation_specification.md` (**DRAFT, not approved, not frozen**) and `experiments/test_pool_ledger.md`.

- **Population.** All MMLongBench-Doc documents minus the 20 development documents and minus 4 pool documents whose questions were already seen (`PH_2016.06.08_Economy-Final.pdf`, `05-03-18-political-release.pdf`, `2312.04350v3.pdf`, `RAR.pdf`): **111 documents**, about 880 questions expected, every question kept, no page cap. About 5,300 pages (± 1,000).
- **Arms.** **B1** as frozen, and **T1**: the same reader and contract on OCR + BM25 top 4. An optional third arm, **A1** (E9's adaptive policy), only as a pre-registered secondary contrast if the owner chooses it; the shipped system stays B1 whatever A1 scores.
- **Claims.** C1: B1's held-out accuracy with its interval (the headline). C2: **confirmatory test** that visual retrieval beats OCR + BM25 end to end (`visual_retrieval_confirmed` if Δ > 0, one-sided lower bound > 0 and sign-flip p ≤ 0.05). C3: abstention, citation validity and evidence recall. C4: prespecified descriptive subgroups. No per-question error analysis on the pool.
- **Scoring.** S-v1 primary; S-v2 beside it, reported as an interval until blind owner labels exist.
- **Budget and compute.** Expected about $0.75 for B1 + T1; proposed ceiling $2.00 without A1, $2.50 with it. ColQwen2 indexing of about 5,300 pages would take about 18 h on the laptop and needs more free disk than is available, or under an hour on an SSP Cloud GPU.
- **Owner decisions still needed.** Approve the specification (a one-time, irreversible use of the pool), authorise the budget, choose the indexing compute, and optionally label the S-v2 queue afterwards.

Until these decisions are made, the pool stays untouched: no question, answer or evidence is read and no system output is produced for it (`AGENTS.md`). The ledger records what has been seen: frame-level counts, the page counts of three documents, question-level content from three of the four excluded documents (the fourth, `RAR.pdf`, was only named in archived work). No system output exists for any pool question.

---

## 10. Where the sources disagree

| Item | Source 1 | Source 2 | Note |
|---|---|---|---|
| E6 leave-one-document-out range | `docs/validated_baseline_b1.md` §2: "+0.113 and +0.154" | `experiments/frozen/e6/README.md` and `tables/evaluation_summary.json`: 0.113 to 0.149 | 0.154 is E6's document-weighted Δ; the frozen summary gives a maximum leave-one-out of 0.149 |
| Reading of E4 | `docs/validated_baseline_b1.md` §2: E4 "confirms retrieval, not reading, is the bottleneck" | `experiments/frozen/e4/README.md`: "Reading still loses about three times more than page selection" (20/37 vs 6/37) | the frozen verdict is `page_selection_costs_accuracy` by one question; the package itself says reading loses more |
| Test pool size | `docs/validated_baseline_b1.md` §4: "111-document / ~916-question test pool" | ledger: 115 documents and 916 questions; final-evaluation draft: 111 documents, about 880 questions | 916 belongs to the 115-document pool; 111 documents leave about 880 |
| Replicate churn in E8 | `docs/e9_proposal.md` and notebook 08: "7 flips between identical replicates" | `experiments/frozen/e8/README.md`: 4 correctness flips | 4 is under S-v1, 7 under S-v2 (`docs/validated_baseline_b1.md` §2) |
| E7 cost per call count | `docs/e9_proposal.md` §7: "E7's 1,309-call run cost $5.911057" | `experiments/frozen/e7/README.md`: $5.911057 is smoke + full ($0.063019 + $5.848038) | the 1,309-call full run alone cost $5.848038 |
| Evicted source PDFs | `docs/validated_baseline_b1.md` §5: 11 of 24 | `docs/PROGRESS.md`: 12 | iCloud eviction changes over time |
| E0 text run-to-run changes | `experiments/README.md`: 3–6 of 57 | `experiments/frozen/mmlongbench_doc/README.md`: 4–6 of 57 | both describe the 2026-11-19 text runs |

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

---

## 12. Provenance

| Artifact | Location |
|---|---|
| E0 canonical runs | `experiments/frozen/mmlongbench_doc/` |
| E1–E7 runs, tables, audits | `experiments/frozen/e1/` … `e7/` |
| S-v2 owner labels | `experiments/frozen/scoring_v2/` (E6/E7), `experiments/frozen/e8_scoring_v2/` (E8) |
| E8 smoke and execution | `experiments/frozen/e8_smoke/`, `experiments/frozen/e8/` (commit `0d68a93`) |
| E9 Stage 0 | `experiments/frozen/e9_stage0/` (commit `a30bb29`) |
| E9 Stage 1–2 | `experiments/frozen/e9/` (commit `7f6c744`; independent audit 47/47; 13 S-v2 items await the owner's labels) |
| Specifications | `experiments/specs/` (E1–E9, E2 v1 superseded by v2, E9 addendum) |
| Baseline description | `docs/validated_baseline_b1.md` |
| Reproduction | notebooks 00–08 in their default modes; see `docs/reproducibility.md` |
