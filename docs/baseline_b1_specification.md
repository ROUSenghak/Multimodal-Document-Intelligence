# Baseline B1: specification, repository changes, feasibility and the E8 smoke plan

- **Date:** 2026-11-25.
- **Builds on:** `docs/baseline_consolidation_assessment.md` and the owner's decisions of 2026-11-25.
- **Status:** proposal. Nothing in sections 4–8 is implemented. The approval gates are listed in section 9.

**Done today (local, not pushed):**
- **E7 frozen** in `experiments/frozen/e7/`, with an independent audit (38/38) and checksums. Commits `cbb7ac8` (freeze) and `b05bb78` (notebook 06 outputs). Notebook 06 now evaluates the frozen copy by default, re-derives its tables byte for byte and asserts the regression references.
- **Test-pool ledger:** `experiments/test_pool_ledger.md`.
- **Notebook `07_baseline_consolidation.ipynb`** (offline, development data): retrieval complementarity and the scoring protocol v2. It was executed top to bottom on a fresh kernel. It and this document are uncommitted, for your review.

---

## 1. The owner's decisions, and where I push back

| Decision | Assessment |
|---|---|
| 1. Freeze E7 | **Done.** |
| 2. Scope = product contract; whole benchmark for evaluation, with prespecified subgroups | **Agree.** Notebook 07 shows why the scope cannot be the evaluation filter: only 6 of the 20 used documents are born-digital report-type, and the two 10-Ks hold 31 of their 57 evidence questions. |
| 3. Preserve the untouched pool; no split | **Agree, with a condition.** See §1.1. |
| 4. ColQwen2 and BM25/OCR first-class; no hybrid without evidence | **Agree. The evidence says no fusion.** See §2. |
| 5. A minimal E8 | **Agree.** Three live arms, each justified in §5. I removed the 8-page, oracle and effort arms. |
| 6. Scoring v2, preserving history | **Done offline** (notebook 07). It needs ~30 minutes of human adjudication before E8 is interpreted; see §1.2. |
| 7. Extensible application, no LangGraph | **Agree.** Interfaces in §4.3. |
| 8. Exact `AGENTS.md` wording first | **Provided in §8, not applied.** |

### 1.1 Preserving the pool: the condition

Without a split, any later improvement (adaptive retrieval, a bounded agent) is designed on the same 20 development documents. Only 6 of them are in the core scope, and since E4 they have been reused for every design decision. This is acceptable only if:
- the pool is used **once**, at the end, for frozen configurations run in the same session;
- no per-question error analysis is ever done on it.

**When a split would become compelling:** if an improvement phase starts and its design needs more in-scope development documents than the 6 available. At that point the ledger shows exactly what has been touched, and a seeded document-level split can be argued for on its merits.

**One correction from the ledger.** Four pool documents were touched at the question level, mostly in archived notebooks:
- `PH_2016.06.08_Economy-Final.pdf`;
- `05-03-18-political-release.pdf`;
- `2312.04350v3.pdf`;
- `RAR.pdf`.

I also displayed three `PH_2016` questions today, inadvertently, during a schema check. **The final evaluation should exclude these four documents, as E5 did,** which leaves 111 of 115. No system output has ever been produced for a pool question.

### 1.2 Scoring is the larger source of uncertainty

On E6's ColQwen2 arm, S-v1 counts 38/102 correct.
- S-v2 leaves 12 replies per arm to a human, so the interval is 35–47.
- The same request run in two sessions flips only 2 + 2 questions.

**Absolute accuracies are therefore uncertain by about ±6 questions until the 29 queued replies are adjudicated.** Paired differences are stable: E6's V − A is +0.098 at both S-v2 bounds, and E7's X4 − V0 is −0.059 to −0.069. Neither frozen verdict changes direction.

**Adjudicate before E8's results are read** (`data/processed/mmlongbench_doc/b1/adjudication_queue.csv`, rubric in notebook 07 §Method B). The labels must be a human's, given blind to the arm, so I did not pre-label them.

### 1.3 Two risks to accept explicitly

1. **The successor reader cannot be pinned.**
   - `gpt-6-luna` exists only as an alias; OpenAI lists no dated snapshot.
   - In B1, *frozen replies* define the baseline, not the model name. Every call records the served model and system fingerprint, and a change in either is a new condition.
   - If the thesis needs a reader that can be pinned and re-run, the only true option is self-hosted open weights, for example Qwen3-VL-8B at a fixed revision on SSP Cloud. E2 found it within noise of GPT-4o-mini. **This is postponed, not rejected.**
2. **The visual retriever is not runnable on the laptop today.**
   - The ColQwen2 weights (4.4 GB) are no longer cached, and only 5.9 GB of disk is free.
   - E8 is unaffected: it uses E5's frozen rankings.
   - The live application can use ColQwen2 only on SSP Cloud, or on the laptop after freeing about 10 GB. Otherwise it falls back to BM25, by design (§4.2).

---

## 2. Retrieval decision (notebook 07 §A, development data)

At B1's budget of 4 pages, on 141 evidence questions:

| Complete evidence | ColQwen2 only | BM25 only | both | neither |
|---|---:|---:|---:|---:|
| all 141 | 32 | 4 | 60 | 45 |
| core scope (57) | 6 | 2 | 25 | 24 |

- **No combination beats ColQwen2 alone.** On the 101 held-out evidence questions, Complete@4 against ColQwen2:
  - RRF −0.079 [−0.167, −0.016];
  - interleaving −0.059 [−0.133, −0.009];
  - RRF in the core scope 0.000 [−0.064, +0.039].
- **The rule stated before computing** (gain ≥ 0.05 with interval above 0, and no loss in the core scope) **is not met.**
- **Ceiling.** A perfect per-question choice between the two retrievers would add only +0.04 complete evidence.
- **Answer level.** In E6, no question (0/102) was answered correctly *only* with BM25's pages.
- **Where BM25 is competitive.** Plain-text pages and the 10-Ks, where recall@4 is 0.57 for RRF against 0.55 for ColQwen2. ColQwen2 dominates on figures, layout and OCR'd pages.

**B1 therefore retrieves with ColQwen2.** BM25 is first-class in four roles:
- the fallback when no visual index is available;
- a ranking computed and logged beside ColQwen2's for every question, at no cost;
- the text layer used to verify citations;
- a candidate tool for a later *adaptive* step, tested only then.

The real retrieval gap is evidence that *neither* retriever ranks in the top 4: 45 of 141 questions, concentrated in multi-page questions. Fusion does not address it.

---

## 3. Scope (product contract) and evaluation population

**Product contract.**
- **Input:**
  - one English PDF, not encrypted, of up to about 200 pages (a configuration value);
  - *born-digital*: at least 80 % of pages carry ≥ 30 native words. On the development documents, the core-scope set is the same for every threshold from 0.5 to 0.84;
  - image-only pages are processed best effort (OCR plus visual retrieval) and flagged in the output, not claimed.
- **Questions:** answerable from this document alone. Factual lookup, numeric extraction, comparison, simple aggregation; evidence on at most a few pages. No handwriting, cross-document questions, outside knowledge or document-wide synthesis.
- **Output:** a typed answer or `Not answerable`, cited pages, and a verbatim supporting passage per cited page (if E8 accepts contract v2).

**Evaluation population.** All questions of the evaluation documents, with no question-level filter. A user cannot know in advance how many pages a question needs. Prespecified subgroups:
- **core scope:** born-digital report-type documents (financial, research report, administration/industry);
- evidence span: 1 / 2–3 / 4+ pages;
- evidence source;
- numeric vs other answers;
- born-digital vs image-only.

**Development population:** the 20 used documents (175 questions). For E8: E6's 118 questions, the only ones with frozen GPT-4o-mini anchors on ColQwen2 pages.

---

## 4. B1 specification

### 4.1 Pipeline and parameters

| Stage | B1 setting | Evidence | In `src/visualdoc` today |
|---|---|---|---|
| Ingest | Open and validate the PDF; SHA-256 of its bytes (the document key); per page: native word count and size; document born-digital flag | E0; notebook 07 | `documents.py` (validation); key and flag **new** |
| Text | Native layer `get_text("text", sort=True)`; full-page Tesseract OCR (PyMuPDF, `eng`, 150 dpi) below 30 native words | E0 (BM25 Recall@5 0.689 with OCR vs 0.358 without) | exists, parity-tested |
| Render | Whole page fitted in a 768 × 1536 box, RGB PNG | E1 (GPT-4o-mini); kept for comparability, re-examined only as a later improvement | exists, parity-tested |
| Index | BM25 per document (k1 1.5, b 0.75). ColQwen2 v1.0 at revision `ddc07d23`, bf16, page multi-vectors stored as safetensors under (PDF SHA-256, render profile, model revision) | E5 (+0.195 recall), E6 (+0.127 accuracy) | BM25 exists; visual index **new** |
| Retrieve | Primary: ColQwen2 MaxSim over the cached page vectors. BM25 always computed and logged; used alone when no visual index exists (recorded in the result) | E5, E6, notebook 07 | MaxSim **new** (NumPy, as notebook 05) |
| Select | The first **k = 4** pages of the primary ranking, then the reader profile's checks (context, per-request cost ceiling) | E6 read 4 pages for 105/118 questions; 8 pages add complete evidence for at most 9/101 | guard exists for GPT-4o-mini only; **becomes profile-driven** |
| Read | One call: `gpt-6-luna` (pending E8), `reasoning_effort` fixed (proposed `none`), image detail `high`; contract v2 if E8 accepts it, otherwise v1 | E2, E3, E7 (one-shot, images only); E8 | **modify** |
| Validate | Strict parse; citation validity, off-by-one, missing citation; **quote verification** (each support passage found in its cited page's text, normalised fuzzy match ≥ 0.9); **numeric support** (the answer's number appears on a cited page, or is flagged as derived) | E7 (structured output raised citation validity from 0.93 to 0.99) | form checks exist; grounding **new** |
| Log and cache | One JSONL record per call: request fingerprint, served model, system fingerprint, tokens, cost, latency. Reply cache keyed by (fingerprint, served model). Cumulative budget with a hard stop | E1–E7 executors (notebooks) | **new** (README limitation 5) |

### 4.2 Output contract v2 (to be tested in E8)

**Prompt `b1-image-v2`.** The frozen `mmlb-image-v1` prompt, plus one sentence:

> "evidence": for each cited page, one short passage copied verbatim from that page (at most 30 words) that supports the answer ([] if "Not answerable").

**Response schema** (Structured Outputs, `strict: true`):

```json
{"type": "object", "additionalProperties": false, "required": ["answer", "cited_pages", "evidence"],
 "properties": {
   "answer": {"anyOf": [{"type": "string"}, {"type": "number"},
                        {"type": "array", "items": {"anyOf": [{"type": "string"}, {"type": "number"}]}}]},
   "cited_pages": {"type": "array", "items": {"type": "integer"}},
   "evidence": {"type": "array", "items": {"type": "object", "additionalProperties": false, "required": ["page", "quote"],
                "properties": {"page": {"type": "integer"}, "quote": {"type": "string"}}}}}}
```

Abstention stays the exact string `Not answerable`, as every frozen result defines it. An abstention *reason* is left out of B1 to keep the contract minimal.

### 4.3 Interfaces prepared for adaptive and agentic retrieval (no framework)

```python
@dataclass(frozen=True)
class ReaderProfile:            # everything model-specific, nothing architectural
    model: str; context_tokens: int; image_tokens: Callable[[int, int], int]
    usd_per_1m_input: float; usd_per_1m_output: float; request_params: dict; max_output_tokens: int

class Retriever(Protocol):      # "visual" (ColQwen2 MaxSim) and "bm25" implement it
    name: str
    def rank(self, question: str) -> list[tuple[int, float]]: ...

@dataclass
class Budget:                   # bounds any run, one question or a loop
    max_calls: int; max_pages: int; max_usd: float

@dataclass(frozen=True)
class Step:                     # one recorded action: retrieve / read / verify
    action: str; inputs: dict; output: dict; usd: float; latency_s: float

def answer_question(doc, question, *, reader, contract, retriever="visual", k=4, budget) -> QAResult:
    """B1 = the one-step policy: retrieve once, read once, verify. Returns the answer and its Trace (list[Step])."""
```

**A later bounded agent** is a different *policy* over the same three actions, under the same `Budget` and `Trace`. Its actions would be to:
- re-retrieve with a refined query or the other tool;
- read more pages;
- verify;
- answer or abstain.

B1 against an agent is then a controlled comparison: same tools, logs and cost accounting.

**Orchestration.** A plain Python loop over a state dataclass is enough. LangGraph would add value only for checkpointing, human-in-the-loop or branching visualisation, none of which is needed.

### 4.4 Evaluation protocol for B1

- **Primary:** answer accuracy on answerable questions under S-v1 (continuity with every frozen result), reported with S-v2 (S-v1 plus blind adjudication of gray replies).
- **Secondary:**
  - correct abstention (unanswerable), false abstention, answered false premises;
  - coverage and selective accuracy;
  - citation validity, page-level citation precision and recall against annotated evidence, correct-and-grounded answers;
  - quote verification and numeric support;
  - tokens, USD, latency p50/p90; indexing seconds per page and bytes per page.
- **Statistics:**
  - the unit is the question, clustered by document;
  - document-cluster percentile bootstrap (10,000 draws);
  - exact or Monte Carlo sign-flip test for paired contrasts, McNemar descriptive;
  - one primary contrast per experiment.
- **Not used:** non-inferiority claims on about 100 questions. A planning simulation showed an equally good reader passes "95 % lower bound > −0.05" only 26–33 % of the time.

---

## 5. E8: reader migration and B1 stabilisation (minimal design)

**Question.** Can `gpt-6-luna` replace `gpt-4o-mini-2024-07-18` as B1's reader on the same pages, with a structured output contract, reliably and at a feasible cost?

**Population.** E6's 118 questions (102 answerable, 16 unanswerable; development).

**Anchors (no new call).** The two frozen GPT-4o-mini sessions on ColQwen2 pages, E6 V and E7 V0: 38/102 each, with 2 fixed and 2 broken between them.

| Arm | Reader | Pages | Contract | Calls | Why it is needed |
|---|---|---|---|---:|---|
| **L-v1** | `gpt-6-luna` | E6 V's exact pages (4 for 105 questions, 3 for 13) | `mmlb-image-v1`, `json_object`, 400 output tokens | 118 | **Matched comparison.** The model changes, and nothing else the API allows to stay fixed. |
| **L-B1** | `gpt-6-luna` | ColQwen2 top 4 (= E6 V's pages for 105; one more page for 13) | `b1-image-v2`, strict JSON schema, 800 output tokens | 118 | **B1 as it will ship:** structured-output reliability and grounding. L-B1 − L-v1 is the contract change, plus one page on 13 questions, reported separately. |
| **L-B1r** | identical to L-B1, later in the session | same | same | 118 | **Stability.** An alias with no snapshot, and possibly no temperature control. Its flip rate is the noise floor every later improvement must exceed. |

**Removed and deferred:**
- **8 pages.** At most 9/101 more questions get complete evidence; this is a retrieval improvement for later.
- **Oracle pages.** A diagnostic ceiling for improvement planning, not for the baseline.
- **Reasoning-effort levels.** Fixed by a technical rule in the smoke test; a later improvement candidate.
- **A live GPT-4o-mini control.** Two frozen sessions already give its noise; it would cost about $1.83.

**Fixed settings.**
- `reasoning_effort = "none"`: the closest to the non-reasoning anchor, the fastest, and no hidden reasoning in the baseline. Smoke check S3 verifies the API accepts it.
- `temperature = 0` only if the API accepts it with that effort; otherwise omitted, and recorded.
- Image detail `high`.
- Seeded, counterbalanced order: L-v1 and L-B1 adjacent per question, 59/59; the L-B1r block after all pairs.

**Decision rules (fixed in the spec before any reply).**
1. **Technical gate.**
   - 354/354 replies received.
   - One served model string across the run.
   - `finish_reason = stop` on all replies.
   - L-B1 schema-valid on ≥ 117/118 per replicate.
2. **Migration (L-v1 against each anchor).**
   - Report Δ with the cluster 95 % interval, under S-v1 and S-v2.
   - **Material harm** = Δ ≤ −0.05 *and* the upper bound < 0, against both anchors. If flagged, B1 is not frozen on `gpt-6-luna`; a fallback (effort `low`, or another reader) becomes a new condition needing approval.
3. **Contract (L-B1 against L-v1).** Adopt contract v2 if all hold:
   - schema validity ≥ 99 %;
   - citation validity ≥ L-v1's − 0.03;
   - accuracy Δ ≥ −0.05.

   Otherwise B1 ships contract v1. Quote verification is reported, never gating.
4. **Stability.** The L-B1 vs L-B1r correctness flip count is reported. More than 10 flips on 102 marks B1 "unstable": any later comparison must then use repeated runs.
5. **Guardrail.** Correct abstentions of L-B1 on the 16 unanswerable questions must be ≥ 5 (anchors: 7). Below that, the contract is reviewed before freezing.

**Cost.** Depends on `gpt-6-luna`'s image-token rule, which the documentation does not give.
- If it follows the documented ×1.2 patch rule of `gpt-5.6-luna`: about 1,000 tokens per page, about $0.0005 per call, **about $0.20 for the full run**.
- If it billed like `gpt-4o-mini` (25,501 tokens per page): about $0.011 per call, **about $3.7**.

Proposed **hard ceiling: $5 cumulative**, smoke included.

---

## 6. Minimal E8 smoke plan (≤ 8 calls, ceiling $0.10)

**Purpose:** measure what the documentation does not say, before the full spec is frozen. Nothing in the smoke test is scored.

| Call | Request | Measures |
|---|---|---|
| S1 | Text only: B1 system prompt + `Question: …` (question of `mmlb-0068`), no image | Text-token baseline and framing for `gpt-6-luna`'s tokenizer; served model string; `reasoning_effort: "none"` accepted |
| S2 | S1 + one 768 × 994 portrait page | Image tokens per portrait page = S2 − S1 − page-tag tokens |
| S3 | S1 + one 16:9 page (1366 × 768) | Image tokens per landscape page; with S2, tells which rule applies (×1.2 patches, other patches, tiles) |
| S4 | L-v1 request for `mmlb-0068` (E6 V's 3 pages, the largest E6 request), with `temperature: 0` | `temperature` accepted or refused (a 400 refusal is not a reply); `json_object` parse; latency |
| S4′ | Only if S4 is refused for temperature: the same request without it | — |
| S5 | L-B1 request for `mmlb-0068` (unanswerable): strict schema | Strict `json_schema` accepted; `Not answerable` with empty evidence |
| S6 | L-B1 request for one answerable single-page core-scope question, chosen by a seeded rule from the 10-K questions | Evidence quotes returned; quote verification path; output tokens |

**Gates, all required before the full stage is proposed:**
- every reply parses;
- S5 and S6 validate against the schema;
- the served model is recorded and identical across calls;
- image tokens per page are measured, and the reader profile's rule reproduces S2 and S3 exactly (or within one token);
- effort `none` is accepted;
- billed cost ≤ $0.10.

**Then:**
1. Freeze the E8 spec with the measured reader profile.
2. Rebuild all 354 requests offline (fingerprints, token bounds, cost upper bound).
3. Run mocked interface tests.
4. Ask for the full-stage approval.

**Note for S1.** The `mmlb-0068` question text is development data, already sent to OpenAI in E6 and E7; nothing from the pool is sent.

---

## 7. Feasibility

| Item | Assessment |
|---|---|
| E8 cost | $0.2–3.7 (see §5); ceiling $5. Total project spend so far ≈ $13 |
| E8 duration | 354 + ≤ 8 calls; at an estimated 3–5 s each, sequential, about 25 minutes |
| Laptop (M1, 8 GB RAM, **5.9 GB free disk**, repository in iCloud) | Fine for notebooks 00–07, BM25, NumPy MaxSim over cached embeddings, E8 and the app's BM25 path. **Not** fine for ColQwen2 (4.4 GB of weights not cached) or for indexing the final pool. Move the repository out of iCloud: the `.pth` hidden flag recurs, and held-out PDFs became dataless. |
| SSP Cloud | The intended place for ColQwen2 indexing (pool for E9) and for running the visual path live. **The GPU type and quota are not verified;** please check your datalab account. Indexing about 5,000 pages at E5's 12 s per page would take about 17 h on the laptop; on a GPU it should be far less. Embeddings take about 193 KB per page (about 1 GB for the pool). |
| Final evaluation (E9, later) | 111 pool documents, no page cap (GPU indexing), B1 frozen, one session. Somewhat fewer than the pool's 705 answerable questions: the four excluded documents' counts are computed only when that spec is frozen. Accuracy interval about ±0.03–0.04 (cluster); paired differences of about 0.05 detectable (planning simulation) |
| Engineering size of B1 | About 300–400 new lines in `src/visualdoc` plus tests: reader profiles, contract v2, MaxSim, run log, cache and budget, grounding checks, and one new module `indexing.py` for ColQwen2 encoding (heavy optional dependencies isolated). No framework. |

---

## 8. Repository changes

### 8.1 Done today

| Change | State |
|---|---|
| `experiments/frozen/e7/` (runs, tables, analysis, design labels, AUDIT 38/38, script, PROVENANCE, SHA256SUMS) | committed `cbb7ac8` |
| `notebooks/06`: evaluates the frozen E7 by default, asserts references, paid gate explicitly closed; executed | committed `cbb7ac8`, outputs `b05bb78` |
| `experiments/README.md`: rows and entries for E4–E7 | committed `cbb7ac8` |
| `experiments/test_pool_ledger.md` | uncommitted |
| `notebooks/07_baseline_consolidation.ipynb` (sections A, B; executed) | uncommitted |
| `docs/baseline_consolidation_assessment.md`, this file | uncommitted |

### 8.2 Proposed, each needing approval

1. Commit the uncommitted files above.
2. **`AGENTS.md`** (wording in §8.3).
3. **`src/visualdoc` B1 extension.** This is the application phase under `AGENTS.md`.
   - **Modules:**
     - `answering.py`: `ReaderProfile` for GPT-4o-mini, frozen and parity-tested, and for `gpt-6-luna`, built from smoke measurements; contracts v1 and v2.
     - `retrieval.py`: the retriever protocol and MaxSim.
     - `citations.py`: grounding checks.
     - `pipeline.py`: stages, `Budget`, `Trace`, run log and cache, BM25 fallback.
     - New `indexing.py`.
   - **Tests:** parity to every frozen E6 V request with the GPT-4o-mini profile and contract v1 (fingerprints, 118/118), and mocked `gpt-6-luna` replies.
4. **Notebook 07 sections C–E:** the E8 smoke stage, the E8 full run *through the B1 application* (the app is the object measured, the `AGENTS.md` exception), and the evaluation. Each paid stage needs its own approval.
5. **README:** rewritten around B1. Stale items: status block, "Implemented versus planned" (visual retrieval "Planned"), layout and workflow tables stopping at E3/03.

**Ordering reason.** Implementing B1 in `src` *before* the E8 full run means E8 measures the application that ships. It also avoids writing a fourth notebook executor that the app would then have to duplicate. The smoke test can run before the app changes: it needs only hand-built requests.

### 8.3 Proposed `AGENTS.md` amendments (exact wording; not applied)

**(a) Structure: replace the first bullet**

> - `notebooks/00_document_processing.ipynb` → `01_retrieval.ipynb` → `02_question_answering.ipynb` → `03_evaluation.ipynb`. Each notebook has one responsibility.

with

> - `notebooks/00_document_processing.ipynb` → `01_retrieval.ipynb` → `02_question_answering.ipynb` → `03_evaluation.ipynb` form the base workflow (E0–E4). Later stages each have their own notebook: `04_visual_retrieval` (E5), `05_visual_retrieval_answering` (E6), `06_extract_then_answer` (E7), `07_baseline_consolidation` (baseline B1: retrieval complementarity, scoring protocol v2, reader migration E8). Each notebook has one responsibility.

**(b) Frozen results: replace**

> - `experiments/frozen/` holds the committed canonical predictions and the frozen E1–E4 runs. Never edit those files; new live runs go to the git-ignored `experiments/runs/`.

with

> - `experiments/frozen/` holds the committed canonical predictions and the frozen E1–E7 results. Never edit those files; new live runs go to the git-ignored `experiments/runs/`.
> - The untouched test pool is every MMLongBench-Doc document outside the 20 used in E0–E7. Do not read its questions, answers or evidence, and produce no system output for it, until a frozen final-evaluation specification is approved; then use it once, for frozen configurations in one session. `experiments/test_pool_ledger.md` records everything already seen about it; update it whenever more is read.

**(c) Application baseline: replace the sentence**

> Notebooks import it only where the application itself is the object measured: `02_question_answering` section 13 (E4) and `03_evaluation` sections 16–17.

with

> Notebooks import it only where the application itself is the object measured: `02_question_answering` section 13 (E4), `03_evaluation` sections 16–17, and the E8 sections of `07_baseline_consolidation`.

**(d) Experimental integrity: add two bullets after the first**

> - Answer scoring: S-v1 (notebook 03 cell `f653d232`; correct = score > 0) is frozen and decides every historical verdict, which is never re-labelled. New results also report S-v2 (notebook 07): S-v1 plus blind human adjudication of the replies it marks gray. Keep the adjudication labels with the result.
> - A reader served through an alias without a dated snapshot (for example `gpt-6-luna`) is recorded per call (served model, system fingerprint). A change in either is a new condition; frozen replies, not the model name, define a baseline.

**(e) Paid calls: replace**

> - Paid API calls are opt-in (`VISUALDOC_QA_MODE`, default `replay`).

with

> - Paid API calls are opt-in, one mode variable per notebook (`VISUALDOC_QA_MODE` default `replay`; `VISUALDOC_E*_MODE` default `offline`).

**(f) Regression references: append, before the closing "are asserted in the notebooks"**

> ; E5 held-out evidence recall after the guard A 0.526 → V 0.721, verdict visual_improves_evidence; E6 A 25/102 → V 38/102 with 13 fixed / 0 broken, verdict adopt_visual_retrieval, spend $3.7213; E7 V0 38/102, X4 31/102, X8 29/102 with X4 − V0 3 fixed / 10 broken, verdict regression, spend $5.911057

---

## 9. Approval gates, in order

| Gate | Action | Cost |
|---|---|---|
| G1 | Commit the ledger, notebook 07 and these documents (local) | $0 |
| G2 | Apply the `AGENTS.md` amendments (§8.3, possibly edited) | $0 |
| G3 | **Human adjudication** of the 29 queued replies (you) | $0, ~30 min |
| G4 | E8 smoke (§6): at most 8 calls | ≤ $0.10 |
| G5 | Freeze the E8 spec with the measured reader profile; begin the `src` B1 extension (application phase) | $0 |
| G6 | E8 full: 354 calls through the B1 application | ≤ $5 (likely ≈ $0.20) |
| G7 | Freeze B1 (E8 result, frozen replies, tests) | $0 |
| later | Pool indexing on SSP Cloud and the final evaluation E9; improvement phase | separate specs |

`gpt-4o-mini-2024-07-18` shuts down on 2027-01-14. Nothing above depends on it, except that the current application's `--live` mode stops working then.
