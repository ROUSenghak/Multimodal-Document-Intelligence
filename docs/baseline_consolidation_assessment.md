# VisualDoc AI: post-E7 assessment and proposal for one consolidated baseline

- **Date:** 2026-11-25. Branch `refactor/simplify-structure` at `469aff5`, working tree clean before this file.
- **Method:** read-only investigation of the repository, the frozen E0–E6 packages, the E7 run and its report, the E6 error audit, and the literature review. Offline diagnostics on development data (scripts in the session scratchpad, not in the repository). Official OpenAI documentation re-read on 2026-11-25. No API call, no notebook or `src/` change, no commit.
- **Status:** proposal. Every action in section 10 waits for your approval.

Evidence labels:
- **[established]:** published, widely replicated, or official documentation.
- **[our result]:** a frozen, audited E0–E7 measurement.
- **[diagnostic]:** a descriptive offline breakdown done for this assessment.
- **[hypothesis]:** untested.
- **[planning]:** a simulation used only to size a design; never a result.

**Test-pool boundary.** For the untouched pool (115 documents, 916 questions), I computed only document-level frame counts by benchmark document type. No question text, answer, evidence annotation or outcome of a pool question was printed or used. Every question-level analysis below uses the 20 documents already used in E0–E7.

---

## 0. Summary

1. **The experimental record is strong; the application lags it.**
   - E0–E7 are pre-registered, byte-reproducible and independently audited. All 125 tests pass.
   - The shipped application (`src/visualdoc`) still runs OCR + BM25 → GPT-4o-mini, refuses any other model, and has no visual retrieval, cache or budget.
   - The adopted configuration (ColQwen2 + one-shot reader, E6) exists only in notebooks 04–05.
2. **The reader must change, and several historical "decisions" are GPT-4o-mini artefacts.**
   - `gpt-4o-mini-2024-07-18` shuts down on **2027-01-14**. OpenAI names **`gpt-6-luna`** as its replacement.
   - `gpt-4.1-mini` retires on the same day and `gpt-5-mini` on 2026-12-11, so neither is a safe interim choice.
   - The **4-page cap** comes from GPT-4o-mini billing 25,501 tokens per 768-px page; it is not an architectural requirement.
   - The **768-px** choice is likewise tied to GPT-4o-mini's preprocessing.
3. **Your proposed scope is useful as a product definition, but too thin as an evaluation population.**
   - In the 20 used documents, only **6** are born-digital report-type documents, and two 10-Ks hold more than half of their questions.
   - The untouched pool holds only **9 financial reports** (86 questions).
   - Restricting by genre also **raises** the reported accuracy: E6 V scores 0.42 on report-type documents against 0.31 on the others, which is the effect you asked me to avoid.
   - **Recommendation:** keep the scope as the product contract and as a pre-registered key subgroup. Make configuration comparisons on all questions of the evaluation documents.
4. **Under the new scope, the error profile changes.**
   - On born-digital report-type documents, ColQwen2's retrieval advantage over BM25 nearly vanishes: recall after the guard is 0.54 → 0.63, against 0.51 → 0.81 elsewhere. RRF hybrid ties ColQwen2 (0.62).
   - Errors there are mostly **evidence** errors (18 of 29), including all 9 retrieval misses, which sit in the two 10-Ks. Only one is a perception error.
   - BM25 and OCR text are therefore not just fallbacks; they are candidate retrieval partners and the basis of a cheap grounding check. [diagnostic, 50 questions in 5 documents: a hypothesis to confirm, not a finding]
5. **Recommended baseline (B1).**
   - Pipeline, mostly unchanged: born-digital-aware ingestion with OCR fallback → ColQwen2 MaxSim (BM25 fallback, hybrid as a measured alternative) → a fixed top-k sized by a **reader profile** → one-shot `gpt-6-luna` → JSON-schema answer with cited pages and verbatim support → deterministic citation and grounding checks → content-addressed caches and a run log.
   - The architecture changes little; the reader, page budget and output contract are decided in one inexpensive experiment (E8).
6. **The proposed migration test would not work as written.**
   - The E7 report's non-inferiority rule (95 % lower bound > −0.05 on 102 questions) passes an *equally good* successor only **26–33 %** of the time [planning].
   - The migration is forced, so frame it as estimation plus harm detection, and choose among *successor configurations*.
7. **Agentic work comes later, and its value is bounded first.**
   - E8's oracle-page and wider-budget arms measure how much any retrieval-side agent could gain. Design the interfaces now so that the static pipeline is the one-step case of the agent.
   - LangGraph is not needed.

---

## 1. Current project state

### 1.1 What has been measured [our result]

| Exp. | Question | Population | Result | Retained |
|---|---|---|---|---|
| E0 | Text vs images × retrieved vs oracle | dev6: 6 docs, 57 q (40 answerable) | A 7/40, B 7/40, C 9/40, D 11/38; BM25 Recall@5 0.689 | Images not better on retrieved pages |
| E1 | 512 vs 768 px (oracle pages) | 37 q | 10/37 → 16/37, 6 fixed / 0 broken | 768 px *for GPT-4o-mini* |
| E2 | Qwen3-VL-8B vs GPT-4o-mini | 37 q | 15/37 vs 16/37 (4 / 5) | GPT-4o-mini (tie within noise) |
| E3 | Text vs image vs both | 37 q | T 13, I 17, IT 16 | Images only |
| E4 | Application end to end | 57 q | APP 11/40; ORACLE 17/37 | Page selection costs accuracy |
| E5 | ColQwen2 vs BM25 (evidence) | held-out 14 docs, 101 q | Recall after guard 0.526 → 0.721 | `visual_improves_evidence` |
| E6 | ColQwen2 vs BM25 (answers) | 118 q (102 answerable) | 25/102 → **38/102**, 13 / 0, CI [0.074, 0.193] | `adopt_visual_retrieval` |
| E7 | Extract-then-answer | same 118 (now development) | V0 38, X4 31, X8 29 | Regression; keep one-shot |

Total API spend across E0–E7: about $13 at list price.

### 1.2 What is implemented

| Component | Notebooks | `src/visualdoc` (application) | Gap |
|---|---|---|---|
| PDF text + OCR fallback, rendering | 00 | `documents.py` (parity-tested) | none |
| BM25 | 01 | `retrieval.py` (parity-tested) | none |
| ColQwen2 indexing + MaxSim | 04 (MPS), 05 (NumPy MaxSim from cached bf16 embeddings) | **absent** | adopted retriever not in the app |
| Context guard, request, parser | 02, 05, 06 | `answering.py` (GPT-4o-mini only; `check_request` refuses other models) | reader hard-wired to a retiring snapshot |
| Citations | 03 | `citations.py` (form only) | no semantic grounding |
| Run log, cache, budget, resume | 02/05/06 (thorough) | **absent** ("no retry, rate limiting, response cache or cumulative budget") | the notebooks' engineering never reached the app |
| Evaluation and statistics | 03, 05, 06 | — | appropriate |

### 1.3 Unfinished items

- **E7 is not frozen.** There is no `experiments/frozen/e7`. Its run, evaluation, report, literature review and the E6 error-audit labels live only in git-ignored folders (`experiments/runs/e7`, `data/processed/mmlongbench_doc/e7`), inside an iCloud-synced `~/Documents`. This is the most urgent risk of loss.
- **Stale documentation:**
  - the README status block, "Implemented versus planned" (visual retrieval still "Planned; no model chosen") and the repository layout stop at E3–E4;
  - `experiments/README.md` has no E5 or E7 entry;
  - `AGENTS.md` lists regression references only to E4 and the structure only to notebook 03, which you chose to leave unchanged.
- The project's own question set (`data/annotations/questions.csv`) is still empty.
- The 14-question E3 manual-review queue is unlabelled.

---

## 2. Strengths, weaknesses, technical debt

### 2.1 Strengths (retain)
- **Experimental integrity of a high standard for a master's project:**
  - specs frozen and committed before any call;
  - request fingerprints, append-only logs, run-scoped caches and budget ceilings;
  - same-session counterbalanced pairs;
  - document-cluster bootstrap plus exact sign-flip tests;
  - independent audits and SHA256SUMS;
  - honest negative results (E2, E3, E7).
- **A causal decomposition, not only leaderboard numbers:** oracle vs retrieved pages (E0, E4), evidence vs answers (E5 → E6), and a manual error audit.
- **A small application layer** whose constants are pinned to the frozen runs by parity tests.
- **Cost discipline:** about $13 for seven experiments.

### 2.2 Weaknesses
1. **Small, reused development data.**
   - E1–E4 were tuned in-sample on 6 documents. The 14 held-out documents of E5/E6 became development data in E7, and E8 would use them again.
   - Selection bias accumulates; the only remedy is fresh documents (section 6.4).
2. **Model-specific constraints were treated as architecture:** the 4-page cap, 768 px and the cost guard all encode GPT-4o-mini's billing.
3. **Abstention is weak.** V answers 9 of 16 unanswerable questions, 8 of them false-premise variants. The scorer counts every abstention on an answerable question as wrong, so abstention never pays off.
4. **Scoring noise is the same size as the effects being tested.**
   - In frozen E6 V, 3 of 38 "correct" answers receive only partial ANLS credit.
   - The audit adds 2 correct-but-verbose answers scored 0 and 2 debatable references.
   - That is about 7 of 102 questions against a 0.05 (5-question) decision threshold.
5. **Single-annotator labels** (E6 error audit) with no agreement measure.

### 2.3 Technical debt

| Item | Severity | Proposed action |
|---|---|---|
| E7 artefacts unfrozen, git-ignored, in iCloud | High | Freeze into `experiments/frozen/e7` (approval) |
| Repository inside iCloud-synced `~/Documents`: the `.pth` hidden flag recurs, 9 held-out PDFs were dataless | High (operational) | Move the clone out of the synced folder, or exclude it from sync (your action) |
| Laptop disk 97 % full (7.6 GB free); ColQwen2 weights are 4.4 GB | High (operational) | Index on SSP Cloud; keep only embeddings locally |
| Application hard-wired to `gpt-4o-mini-2024-07-18` | High (dies 2027-01-14) | Reader profiles (section 9) |
| Reader, guard, scorer and statistics re-implemented in notebooks 02, 03, 05 and 06 (≈ 14k code lines; 02 and 03 hold E0–E4) | Medium | Leave frozen notebooks alone; the new stage imports only what it measures (needs an `AGENTS.md` amendment) |
| Specs of 28–35k characters | Medium (defensibility) | A shorter spec template for E8+ with the same required fields |
| `openai>=1.0` unpinned | Low | Pin the SDK version used in a run |
| README, experiments README and `AGENTS.md` stale | Low | Update after approval |
| `parsing.py` unused | None | Keep (policy) |

---

## 3. Methodology: literature, our evidence, open questions

| Pipeline choice | External evidence | Our evidence | Status |
|---|---|---|---|
| Visual late-interaction retrieval (ColPali/ColQwen2, MaxSim) | ColPali (ICLR 2025), VisRAG (ICLR 2025), M3DocRAG: large gains over OCR + BM25 on visually rich pages [established] | E5 recall +0.195; E6 accuracy +0.127, 0 broken [our result] | **Retain as primary.** |
| Lexical retrieval stays competitive on text-dense pages | General IR experience; RRF (Cormack et al., SIGIR 2009) is the standard simple fusion [established] | Born-digital report-type documents: recall after guard A 0.542 / V 0.628 / H 0.620; on the 10-Ks H 0.573 ≥ V 0.548 [diagnostic, 50 q, 5 docs] | **Hypothesis:** hybrid ≥ visual in scope. Test offline (free) before any decision. |
| One-shot reading of page images | MMLongBench-Doc itself; SimpleDoc's per-page-notes baseline is weak (40.45 vs 59.55, summary-level read) | E7: extract-then-answer regresses (−0.069; CI below 0) [our result] | **Retain; do not retest.** The mechanism (textualisation loses layout and visual properties) is not reader-specific. |
| Images only (no OCR text) to the reader | DocLens gains from + OCR on Gemini/Claude | E3: no gain on GPT-4o-mini [our result] | **Retain for the reader.** Use text where it is verifiable: retrieval and grounding checks. |
| Fixed top-k evidence | Gains come mostly from evidence localisation (DocLens, SimpleDoc ablations); distractor sensitivity ("lost in the middle", Liu et al., TACL 2024) [established for text LLMs] | Top-8 completes evidence for only 6 of 33 evidence-failure questions (E6 audit); E7 X8 did not help *under extraction* | **Open for the new reader:** k is a factor in E8, with a small expected ceiling (≤ +6/102). |
| Abstention via sufficiency | Sufficient Context (Joren et al., ICLR 2025): models answer instead of abstaining when context is insufficient; guided abstention trades coverage for precision; selective prediction (Geifman & El-Yaniv, NeurIPS 2017) [established] | V answers 9/16 unanswerable; E7 raised false abstentions [our result] | Measure with selective-risk metrics in the baseline; intervene only in the agentic phase. |
| Cluster-aware inference | Clustered standard errors for question clusters (Miller, "Adding Error Bars to Evals", arXiv 2411.00640); cluster bootstrap (Field & Welsh, JRSS-B 2007); paired testing in NLP (Dror et al., ACL 2018) [established] | Implemented since E5 [our result] | **Retain.** |
| Citation and attribution evaluation | ALCE (Gao et al., EMNLP 2023): citation precision and recall; AIS (Rashkin et al., 2023) [established] | Only form validity exists [gap] | Add page-level precision and recall plus deterministic quote verification. |

The literature table in `data/processed/mmlongbench_doc/e7/post_run_analysis/literature_review.md` remains the detailed reference. I did not re-read those papers for this assessment.

---

## 4. Scope and dataset feasibility

### 4.1 Is the scope precise?

Your scope is a good product statement. To be testable, it should be written as three contracts:

| Contract | Proposed definition | How it is checked |
|---|---|---|
| **Input** | One English PDF, not encrypted, ≤ 200 pages (configurable). *Born-digital*: a text layer with ≥ 30 native words on ≥ 80 % of pages. Image-only pages are handled best effort (OCR + visual retrieval) and flagged in the output, not claimed. | Mechanical, from PyMuPDF, at ingestion |
| **Question** | Answerable from this document alone: factual lookup, numeric extraction, comparison, simple aggregation (sum, difference, ratio, % change over a few values). Evidence on ≤ 3 pages. | In evaluation: the benchmark's evidence-page count. Not checkable at runtime. |
| **Output** | A typed answer (number + unit, string, or list), or `Not answerable` with a reason; cited pages; a verbatim support span per cited page | Schema validation, citation validity, quote verification |

Out of scope, as you proposed: handwriting, cross-document questions, external knowledge, document-wide synthesis (≥ 4 evidence pages), and complex diagram reasoning.

### 4.2 Is it statistically viable on MMLongBench-Doc? [diagnostic]

**The documents already used (20 documents, 175 questions):**

| | Documents | Answerable questions | Comment |
|---|---:|---:|---|
| Report-type genres (Financial report; Research report / Introduction; Administration/Industry file) | 9 | 75 | 3 of the 9 are image-only or scanned: earlybird and germanwings are SlideShare decks with 100 % OCR pages; `3276a5b9…` has 16/16 OCR pages |
| **Of those, born-digital** | **6** | **57** | PG_2020 (dev6), plus AMAZON and COSTCO 10-Ks, `e639029d…`, `11-21-16…` and `efd88e41…` (held-out). **The two 10-Ks hold 31 of the 50 held-out questions.** |
| Unanswerable, born-digital report-type | — | 3 (held-out) | Abstention cannot be estimated in scope |

**E6 V on the held-out 14 documents, by subgroup (102 answerable):**

| Subgroup | n | V correct | BM25 (A) correct |
|---|---:|---:|---:|
| Born-digital report-type (in scope) | 50 | 21 (0.42) | 16 |
| All other documents | 52 | 17 (0.33) | 9 |
| By genre: report-type vs other | 57 / 45 | 0.42 / 0.31 | — |
| Single-page evidence | 55 | 30 (0.55) | 20 |
| 2–3 evidence pages | 40 | 7 (0.18) | 4 |
| 4+ evidence pages | 6 | 0 | 0 |
| Table evidence (in scope) | 27 | 8 (0.30) | 7 |
| Float answers (in scope) | 27 | 10 (0.37) | 8 |

**Errors in scope (29 E6 V errors on born-digital report-type documents):**
- Evidence errors: 18. Retrieval miss 9 (all in the 10-Ks), partial evidence 8, context guard 1.
- Reader errors: 8. Calculation 3, semantic or distractor 2, list 1, multi-page aggregation 1, perception 1.
- Scoring or annotation: 3.

**Outside the scope,** perception and counting/spatial errors dominate the reader errors (10 of 17). **The scope moves the bottleneck from visual reading to retrieval in long, text-dense financial documents, and to numerical aggregation.**

**Untouched pool, document-level frame only:**

| Benchmark type | Documents | Questions |
|---|---:|---:|
| Research report / Introduction | 29 | 242 |
| Financial report | **9** | 86 |
| Administration/Industry file | 8 | 66 |
| *Report-type subtotal* | *46* | *394* |
| Other types (academic paper, guidebook, tutorial, brochure) | 69 | 522 |
| **All** | **115** | **916** (705 answerable) |

The born-digital share of the 46 is unknown; the dev data show that "Research report / Introduction" includes image-only slide decks. A plausible in-scope frame is 30–35 documents and about 220–280 questions [hypothesis].

**Power [planning]**, paired comparison, 20 % discordant pairs, cluster bootstrap:

| Evaluation population | ≈ Answerable q | 95 % CI half-width of Δ | Power to show Δ = +0.05 (lower bound > 0) | Power for Δ = +0.10 |
|---|---:|---:|---:|---:|
| E6 development set (14 docs) | 102 | ±0.07–0.09 | 19–27 % | 55–77 % |
| In-scope pool, if split 1/3 dev, 2/3 test (~22 docs) | 160 | ±0.07 | 33 % | 82 % |
| In-scope pool, all (~33 docs) | 220 | ±0.06 | 40 % | 91 % |
| Whole pool (~100 docs) | 680 | ±0.03 | 81 % | ≈100 % |

### 4.3 Recommendation on scope
- **Keep your scope as the product contract** (4.1). Do not narrow it further; widen the input contract only to say what is handled best effort.
- **Do not use it as the filter for configuration comparisons.** It leaves too few documents (financial: 9), and genre filtering raises the reported accuracy by about 0.1.
  - Primary population for comparisons: all questions of the evaluation documents, with no question-level filter. A user cannot know a question's evidence count in advance.
  - The pre-registered **key subgroup** is *born-digital report-type documents*. It carries the product claim and is reported with its own interval and a "no harm" requirement.
  - Other strata: evidence span (0, 1, 2–3, 4+), evidence source, answer format (numeric vs other), born-digital vs image-only.
- **Keep academic papers in the evaluation.** E6 V scores 1/12 on them; excluding them would be exactly the accuracy-driven narrowing you want to avoid.
- **Optional:** if a credible *financial* claim matters, add the FinanceBench open sample (150 questions on public-company filings, evidence included, non-commercial licence) as an external secondary benchmark after B1 is frozen. Published context: GPT-4-Turbo with retrieval answered incorrectly or refused 81 % of FinanceBench questions. Its documents are long (often > 100 pages), so indexing needs a GPU.
- **Keep MMLongBench-Doc as the primary benchmark**: there is no compelling reason to change, and the revision and document-level separation are preserved.

---

## 5. Recommended baseline architecture (B1)

### 5.1 Which historical choices are architectural and which are model-specific

| Choice | Source | Nature | In B1 |
|---|---|---|---|
| 4-page cap | GPT-4o-mini: 25,501 tokens per 768-px page, 128k context | **Model-specific** | Becomes `k`, set by a reader profile; 4 vs 8 tested in E8 |
| 768-px short side | E1 on GPT-4o-mini, whose preprocessing reduces the short side to 768 | **Model-specific** | Kept as the default for comparability; resolution is an optional E8 diagnostic |
| Images only to the reader | E3 (GPT-4o-mini, oracle pages, 37 q) | Partly model-specific | Kept; text goes to retrieval and grounding instead |
| One-shot vs extract-then-answer | E7 | **Architectural** | Kept |
| ColQwen2 primary | E5/E6 | Retriever-level (reader-independent for recall) | Kept, with hybrid measured offline in scope |
| Prompt `mmlb-image-v1`, `json_object` | E0 | API contract | Kept for the migration comparison; contract v2 tested as a factor |
| OCR below 30 words at 150 dpi; BM25 k1 1.5, b 0.75 | E0 | Method | Kept |

### 5.2 Pipeline

```text
PDF ─► 1 inspect/validate (sha256, page size, native words, born-digital flag)
    ─► 2 text: native layer, OCR fallback (<30 words, 150 dpi)          [cache: pdf_sha → pages]
    ─► 3 render: profile 768×1536 PNG                                    [cache: pdf_sha+profile → PNG]
    ─► 4 index: BM25 (ms) + ColQwen2 v1.0 @ddc07d23 multi-vectors      [cache: pdf_sha+profile+model_rev → safetensors]
            (once per document; SSP Cloud GPU or local MPS ≈ 12.5 s/page)
question ─► 5 retrieve: MaxSim (primary) | BM25 (fallback if no visual index) | RRF (measured alternative)
         ─► 6 select: top-k under ReaderProfile budget (context, image-token rule, $ ceiling)
         ─► 7 read: one-shot VLM, JSON schema {answer, answer_type, unit, cited_pages, support[], abstain_reason}
         ─► 8 validate: parse; citation validity / off-by-one; quote verification against page text;
                        numeric lexical support; abstention normalisation
         ─► 9 log: request fingerprint, served model + fingerprint, tokens, $, latency     [cache: fingerprint+model → reply]
```

### 5.3 Interfaces prepared for a later bounded agent (designed now, used later)

| Interface | Baseline use | Later agentic use |
|---|---|---|
| `retrieve(query, k, tool) → RankedPages` with `tool ∈ {visual, bm25, hybrid}` | one call, `tool=visual` | choose a tool; re-query |
| `read(question, pages, contract) → Answer` | one call | read more pages |
| `verify(answer, pages) → Verification` (deterministic: quotes found, numbers supported) | reported as a metric | sufficiency signal that triggers more evidence or abstention |
| `Budget(max_calls, max_pages, max_usd, max_seconds)` | 1 call, k pages | bounds every loop |
| `Trace` (list of step records) | one fixed step | an auditable multi-step trace |

The static baseline is then **the agent with a one-step policy**. A later agent differs only in its policy, so B1 vs agent is a controlled comparison under the same tools, logs and budget accounting.

**Orchestration framework:**
- A plain Python loop over a state dataclass is enough, and easier to explain and test.
- LangGraph earns its place only if checkpointing or resume, human-in-the-loop steps, or branching visualisation become requirements. Do not adopt it now.

---

## 6. Reader recommendation

### 6.1 Verified facts (official OpenAI pages, read 2026-11-25)

| Model | Status | Price per 1M (input / cached / output) | Context | Image accounting | Pinning |
|---|---|---|---|---|---|
| `gpt-4o-mini-2024-07-18` | Deprecated; **shutdown 2027-01-14**; replacement `gpt-6-luna` (notice 2026-10-14) | 0.15 / 0.075 / 0.60 | 128k | Tile-based, 2,833 + 5,667 per tile | Dated snapshot |
| `gpt-4.1-mini-2025-04-14` | Deprecated; shutdown **2027-01-14** | — | — | Patch, ×1.62 | Dated |
| `gpt-5-mini(-2025-08-07)` | Deprecated; shutdown **2026-12-11** | 0.25 / 0.025 / 2.00 | 400k | Patch, ×1.2 | Dated |
| **`gpt-6-luna`** | Current; the official replacement | **0.10 / 0.01 / 0.50**; Batch and Flex 50 % | 1.05M (922k input) | **Not documented** (absent from the vision guide's tables) | **Alias only; no dated snapshot** |
| `gpt-5.6-luna` | Current | 0.20 / 0.02 / 1.20 | 1.05M | Patch, ×1.2, high ≤ 2,500 patches and 2048 px | Alias only |

Also from the `gpt-6-luna` page:
- It is a reasoning model with `reasoning_effort` ∈ {none, low, medium (default), high, xhigh, max}.
- It lists Structured Outputs and Chat Completions support. The smoke test still validates the exact strict `json_schema` request shape used by B1.
- Temperature, seed and logprobs support are **not stated**. The GPT-6.2 guidance for other models says to omit temperature.

### 6.2 Recommendation
1. **Primary reader: `gpt-6-luna`, with `reasoning_effort` fixed explicitly. Never rely on the default.** Reasons:
   - It is the official successor and works on the same Chat Completions endpoint, so the code change is minimal.
   - It is the cheapest current option.
   - Its 1M-token context removes the context guard as a binding constraint.
   - It supports Batch (−50 %).

   Projection [hypothesis until the smoke test]: if it follows the documented ×1.2 patch rule of its siblings, a 768 × 994 page costs ≈ 922 tokens instead of 25,501. That is ≈ $0.0006 per question at 4 pages instead of $0.0155, about 25× cheaper, so 8 pages become affordable.
2. **Conditions to verify with a 2–3-call smoke test before any design commitment** (each is a gate):
   - billed image tokens per page;
   - which parameters are accepted (temperature, effort);
   - `json_schema` strict mode;
   - the `model` and fingerprint the API returns;
   - latency at the chosen effort.

   Choose the effort level on technical grounds only (acceptance, latency), never on accuracy. My default proposal is `low`.
3. **Reproducibility risk:** with an alias and no snapshot, the model can change under you. Mitigations:
   - record the served model and fingerprint on every call;
   - freeze the E8 replies;
   - re-run a fixed 20-question canary before any later comparison;
   - treat a changed model or fingerprint as a new condition.
4. **Optional open-weights reference:** Qwen3-VL-8B with pinned weights, served on an SSP Cloud GPU.
   - It addresses the pinning problem (E2: 15/37 vs GPT-4o-mini's 16/37 on oracle pages).
   - Add it only if reproducibility becomes a thesis requirement; it brings GPU serving work.
5. **Not recommended now:**
   - `gpt-4.1-mini` and `gpt-5-mini`, which retire within weeks;
   - Gemini and Claude readers, which I did not verify in detail today, and which add a second SDK and data-sharing review without evidence of need.
6. **GPT-4o-mini's remaining role:** a historical anchor. Two sessions already exist on the E6 pages (38/102 each).
   - An optional *live* in-session control (≈ $1.83 for 118 questions) is possible only before 2027-01-14.

---

## 7. Evaluation methodology (protocol v2)

### 7.1 Scoring: preserve history, fix the known defects
- **S-v1 (frozen):** the official rule-based scorer as re-implemented in notebook 03 (cell `f653d232`), with correct = score > 0.
  - It stays the reference for every historical number and verdict.
  - It is reported for every new run, for continuity.
- **Official convention:** the mean score and the benchmark's F1, reported beside S-v1. Our structured answers replace the official GPT-4o extraction step, so these remain local diagnostics.
- **S-v2, the new primary binary correctness: "automatic plus blind adjudication".**
  - **Automatic:** score = 1 is correct. Score = 0 on Int/Float after unit and scale normalisation (%, thousands, millions, currency) with relative tolerance 1 % is wrong.
  - **Gray zone, adjudicated:**
    1. 0 < score < 1 (E6 V: 3 of 38 correct answers);
    2. score = 0 but the normalised reference is contained in the prediction, or vice versa (the verbose-answer cases 0684 and 0593);
    3. references flagged as debatable.
  - **Rubric:** written before any adjudication. The adjudicator sees the question, reference, prediction and the cited page, never the arm or system.
  - **Reliability:** about 20 % re-labelled after at least a week, or by a second person; report Cohen's κ.
  - **History:** S-v2 is applied to E6 and E7 as a sensitivity analysis only; frozen verdicts never change.
- **LLM-as-judge:** optional secondary, never primary.
  - It would itself be an alias model that drifts, and it may favour its own family's answers (Zheng et al., 2023).
  - Use it only after its agreement with the human labels is measured.
- **Numerical accuracy:** reported separately for Int/Float references, using the same normalisation and tolerance.

### 7.2 Metrics

| Family | Metric | Population |
|---|---|---|
| Retrieval | Recall@k, Hit@k, **Complete@k** (all evidence pages), after the selection step; MRR | evidence questions |
| Answers | S-v2 accuracy (primary), S-v1, mean score, F1, numerical accuracy | answerable / all |
| Citations | validity (cited ⊆ supplied, none missing); page-level **precision and recall vs annotated evidence**; **correct-and-grounded** = correct ∧ cites an evidence page | all / evidence questions |
| Semantic grounding | **quote verified**: each support span is found in its cited page's text layer (normalised fuzzy match ≥ 0.9); **numeric support**: the answer number appears on a cited page, or is flagged "derived" | contract-v2 replies; born-digital pages |
| Abstention | correct abstention (unanswerable); false abstention (answerable); answered-a-false-premise; **coverage**; **selective accuracy and risk** at the operating point | all |
| Selective (exploratory) | risk–coverage curve and AURC with a free confidence proxy (normalised top MaxSim score or margin), or token logprobs if the reader exposes them | all |
| Efficiency | input, image, output and reasoning tokens; USD at list price; calls; p50/p90 latency; indexing s/page; embedding bytes/page; peak memory; cache hit rate | per question / page |

### 7.3 Statistics
- **Unit and estimand:**
  - The unit is the question, paired across arms, clustered by document.
  - The primary estimand is the question-weighted Δ; the document-weighted Δ is secondary.
- **Intervals and tests:**
  - Document-cluster percentile bootstrap (10,000 draws, seeded).
  - Sign-flip permutation on document sums: exact up to about 20 documents, Monte Carlo (10⁵) beyond.
  - McNemar and leave-one-document-out, both descriptive.
- **Multiplicity:** one primary contrast per experiment. Factorial main effects are pre-specified; everything else is descriptive.
- **Session noise:** a repeat arm, together with the existing E6 V and E7 V0 sessions.
- **No non-inferiority claims on about 100 questions** [planning]: an equally good successor passes "95 % LB > −0.05" only 26–33 % of the time.
  - For a forced migration, report Δ with its interval.
  - Flag *material harm* when the two-sided 95 % upper bound is below 0 **and** Δ ≤ −0.05; that triggers a review of the alternative reader before freezing.
- **Planning simulation:** keep it in every spec (as in E6/E7), and state the minimum detectable effect honestly.

### 7.4 Data partitions
- **Development:** dev6 (57 q) + the E6 set (118 q), for every B1 decision. All results on these are labelled "development".
- **Untouched pool:** before any further use, freeze a seeded, document-level split stratified by benchmark type, with approval:
  - **D2** (≈ 25 documents) for in-scope error analysis and later agent design;
  - **T** (≈ 90 documents) for confirmation only.
  - On T: no per-question error analysis, beyond blind adjudication of gray-zone scores.
- **Why split at all:** the 20 development documents contain only 6 in-scope ones and have been reused since E4. Any later agentic work needs fresh in-scope development data, or it will be tuned on T.

---

## 8. Computational and engineering feasibility

| Resource | Fact | Consequence |
|---|---|---|
| Laptop | Fanless M1, 8 GB RAM, **7.6 GB disk free (97 % full)**, repository in iCloud | Fine for BM25, NumPy MaxSim from cached embeddings, query encoding and notebooks. Not for indexing ~5,000 pool pages (≈ 17 h at 12.5 s/page) |
| SSP Cloud (Onyxia) | Self-service containers with a GPU option and S3 storage (Onyxia project). **I could not verify the current GPU model or quota.** | Use it to index D2/T once: ≈ 193 KB per page in bf16, so about 1 GB for the pool. Store embeddings in S3, then copy them for offline analysis. Pin the ColQwen2 revision and transformers/torch versions as in E5. |
| API | `gpt-6-luna` [hypothesis: ≈ $0.0006–0.001 per question] | E8 ≈ $1–3 including an optional live GPT-4o-mini control; final test ≈ $1–2 |
| Caching | content-addressed by pdf sha256, render profile, model revision and request fingerprint | Indexing once per document; replay without calls |

---

## 9. Changes to the repository

### 9.1 Retain, simplify, modify, postpone, remove

| Decision | Items | Why |
|---|---|---|
| **Retain** | Frozen E0–E6 (+ E7 once frozen); notebooks 00–06 as the record; OCR policy; BM25; ColQwen2 v1.0; one-shot reading; images-only reader input; cluster statistics; spec-before-call discipline; parity tests | All validated |
| **Modify** | `answering.py`: a `ReaderProfile` (frozen GPT-4o-mini profile kept for parity; `gpt-6-luna` profile from measured accounting) and output contract v2. `retrieval.py`: a retriever protocol, MaxSim from cached embeddings, RRF. `citations.py`: quote and number verification. `pipeline.py`: stage functions, `Budget`, `Trace`, retriever choice with BM25 fallback, run log and cache | Carry the adopted configuration into the application; remove model constants from the architecture |
| **Add (needs approval: beyond the five modules)** | `indexing.py` (ColQwen2 encoding + embedding cache; optional heavy dependencies); possibly `runlog.py` (cache and JSONL log), or fold it into `pipeline.py` | Separates the GPU or one-off indexing step from the query path |
| **Add (notebook)** | `07_baseline_consolidation.ipynb` (E8). It imports `src/visualdoc` only where the application is the object measured. **That needs an `AGENTS.md` amendment.** | Notebook-first policy; the next number |
| **Simplify** | E8+ spec template (≈ 1/3 of the E7 length, same required fields); README rewritten around B1; one results table across E0–E8 | Defensibility and readability |
| **Postpone** | Agentic loop; UI (Streamlit); FinanceBench; resolution study; Qwen3-VL self-hosting; own annotation set; ViSAR, crops, rerankers | Not needed for B1; each waits for an observed need |
| **Remove** | Nothing deleted. Drop "own annotated question set" from the active roadmap (it stays in `data/annotations` as history) | MMLongBench covers the need; manual annotation is the costliest item |

### 9.2 Essential vs optional

| Essential for B1 | Optional |
|---|---|
| Freeze E7; move the repository out of iCloud | Live GPT-4o-mini control arm (before 2027-01-14) |
| `gpt-6-luna` smoke test and measured reader profile | 1024-px resolution diagnostic on oracle pages |
| E8 (reader × budget × contract, plus oracle) | Effort factor (`low` vs `medium`) |
| Scoring protocol v2 with adjudication | LLM judge as a secondary scorer |
| Application update (section 9.1) with parity and mocked tests | Qwen3-VL-8B pinned reference reader |
| Pool split pre-registration; T indexing; final test | FinanceBench external benchmark; UI demo |

---

## 10. Roadmap with validation criteria and approval gates

| Phase | Work | Cost | Validation | Gate (your approval) |
|---|---|---|---|---|
| **0. Secure the record** | Freeze E7 into `experiments/frozen/e7` (run, evaluation, report, literature review, E6 audit labels, AUDIT, PROVENANCE, SHA256SUMS). Update the README and experiments README. Propose `AGENTS.md` amendments (E5–E7 references, notebooks 04–07, the new notebook's `src` import). Move the clone out of iCloud. | $0 | SHA256SUMS verify; notebooks 03, 05 and 06 reproduce their frozen numbers offline; pytest green | **G0:** commit the freeze; `AGENTS.md` wording |
| **1. Protocol** | Write the scope contracts (4.1), scoring protocol v2 and adjudication rubric, the metric list, the pool split (seed, strata, D2/T sizes), and a short E8 spec with planning simulation and ceiling | $0 | Spec reviewed; split recorded before any pool PDF is read beyond the frame counts | **G1:** scope, split, E8 design, ceiling |
| **2. Reader smoke** | 2–3 `gpt-6-luna` calls on mmlb-0068 (the largest request) at 4 and 8 pages | < $0.05 | Billed image tokens measured; parameters accepted; strict schema works; served model recorded; reader profile built from the measurement | **G2:** run the smoke |
| **3. Offline retrieval diagnostics** | RRF vs ColQwen2 vs BM25 on in-scope development documents; Complete@k for k = 4, 8, 12; optional ViSAR k\* | $0 | Reproduces frozen E5 numbers first | — |
| **4. E8: baseline consolidation** | On the 118 E6 questions (development), `gpt-6-luna` at fixed effort: **2 × 2 of k ∈ {4, 8} × contract ∈ {v1 prompt, v2 schema + support}**, plus **ORACLE** pages (reading ceiling) and a **repeat** of one arm. Anchor: frozen E6 V and E7 V0 (GPT-4o-mini). About 700 calls. | ≈ $1–3 | Decision rules fixed in the spec: report migration Δ with CI and flag material harm (7.3); adopt k = 8 if its main effect is ≥ +0.03 with broken ≤ fixed/2 and guardrails hold; adopt v2 if its main effect is ≥ −0.02 and citation validity or grounding improve. ORACLE − selected arm bounds any retrieval-side agent. | **G3:** full run |
| **5. Application B1** | Implement 9.1 in `src/visualdoc`; `07` runs the app offline on E8's frozen replies | $0 | Request fingerprints equal E8's 118/118; GPT-4o-mini parity tests unchanged; mocked tests for every failure path; pytest green | **G4:** application phase (`AGENTS.md`) |
| **6. Index D2 and T** | Download pool PDFs at the pinned revision; compute the born-digital flag; index with ColQwen2 on SSP Cloud | $0 (compute) | Rankings deterministic; embedding hashes recorded | **G5:** touch the pool (mechanical steps only) |
| **7. Final test (E9)** | Frozen B1 on T, one session; primary = all T questions; key subgroup = born-digital report-type; one pre-registered secondary (V vs H pages, if phase 3 supports it) | ≈ $1–2 | Pre-registered; blind adjudication; cluster CIs | **G6:** run the final test |
| *8. Later* | Bounded agent (tools and budget from 5.3), designed on D2 against frozen B1 and confirmed on T, aimed at the observed failures: 10-K retrieval misses, partial multi-page evidence, false premises | — | Same metrics and budget accounting | separate spec and approval |
| *9. Later* | UI demo | — | — | separate phase approval |

**Deadline note.** Only two items depend on 2027-01-14:
- any live GPT-4o-mini control;
- the current application's `--live` demo, which stops working on that date.

`gpt-6-luna` is available now, so nothing in phases 2–7 is blocked by the shutdown. Running phases 0–2 soon is still prudent.

---

## Sources (read 2026-11-25)

- OpenAI deprecations: <https://developers.openai.com/api/docs/deprecations>
- OpenAI `gpt-6-luna`: <https://developers.openai.com/api/docs/models/gpt-6-luna>; `gpt-5.6-luna`: <https://developers.openai.com/api/docs/models/gpt-5.6-luna>; `gpt-5-mini`: <https://developers.openai.com/api/docs/models/gpt-5-mini>
- OpenAI pricing: <https://developers.openai.com/api/docs/pricing>
- OpenAI images and vision (token accounting): <https://developers.openai.com/api/docs/guides/images-vision>
- OpenAI Structured Outputs: <https://developers.openai.com/api/docs/guides/structured-outputs>
- FinanceBench: Islam et al., 2023, <https://arxiv.org/abs/2311.11944>; Patronus documentation, <https://docs.patronus.ai/docs/research_and_differentiators/financebench>
- Onyxia (the platform behind SSP Cloud): <https://github.com/inseefrlab/onyxia-web>
- Statistics and evaluation (not re-read today):
  - Miller 2024, arXiv 2411.00640;
  - Field & Welsh 2007, JRSS-B;
  - Dror et al. 2018, ACL;
  - Geifman & El-Yaniv 2017, NeurIPS;
  - Gao et al. 2023 (ALCE), EMNLP;
  - Cormack et al. 2009, SIGIR;
  - Liu et al. 2024, TACL.
- Visual RAG and agentic literature: `data/processed/mmlongbench_doc/e7/post_run_analysis/literature_review.md`.
