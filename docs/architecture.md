# VisualDoc AI: architecture

- **Date:** 2026-11-26.
- **What this covers:** the B1 question-answering pipeline, the application layer built around it, caches and their keys, budgets and guards, the notebook-first research workflow, the frozen packages and specifications, and how each experiment maps to code.
- **What it does not repeat:** command-line usage and the web page's details are in [`docs/application.md`](application.md); results are in [`docs/research_report.md`](research_report.md).

The application layer (`src/visualdoc/app.py`, `visual_index.py`, `web.py`) was revised after an independent review. This document describes its structure; for exact constants and behaviour, `docs/application.md` and the code are authoritative.

---

## 1. Two layers with different jobs

| Layer | Where | Job | Rule |
|---|---|---|---|
| **Research record** | `notebooks/00`–`08`, `experiments/` | Measure each design choice under a frozen specification and keep the evidence | Notebook-first: each operation is rebuilt visibly in cells; notebooks share only saved files (`AGENTS.md`) |
| **Application** | `src/visualdoc/` | Answer a question about any PDF with the configuration the experiments retained | Five modules are SHA-256-pinned to the frozen E8 run; the application grows only by new modules |

The two meet in a few places only. Notebooks import `src/visualdoc` where the application itself is the object measured: notebook 02 §13 (E4), notebook 03 §16–17, and the E8 sections of notebook 07. Those sections check module hashes or outputs against the notebooks' own construction. Notebook 08 (E9) imports nothing from `src/` and instead proves that its requests equal the frozen E8 requests (`AGENTS.md`; `docs/PROGRESS.md`, Application constraints). Notebook 09 (the final held-out evaluation) also imports nothing from `src/`: it rebuilds rendering, MaxSim, BM25, requests and the executor in its own cells, and proves on development data that its rankings equal E5's (118/118) and its B1 requests equal frozen E8 L-B1 (118/118) before building any pool request (`experiments/frozen/final_retrieval/README.md`).

---

## 2. The B1 pipeline

B1 is the configuration frozen after E8 (`docs/validated_baseline_b1.md`). Its policy is: **retrieve once, read once, verify once**, inside a budget.

```
 question, PDF
      │
      ▼
 ┌─ RETRIEVE ─────────────────────────────────────────────────────────────────────┐
 │ documents.extract_pages   native text layer; Tesseract OCR (eng, 150 dpi)       │
 │                           on pages with < 30 native words                       │
 │ retrieval.BM25Index       k1 1.5, b 0.75, ties by page number  ── always computed│
 │ primary retriever         retrieval.CachedVisualIndex: ColQwen2 v1.0 MaxSim     │
 │                           over cached page embeddings                            │
 │   └─ if the visual retriever cannot run (OSError, RuntimeError): BM25, with the  │
 │      reason recorded in the result                                               │
 │ select                    the first k = 4 pages of the primary ranking           │
 └──────────────────────────────────────┬──────────────────────────────────────────┘
                                        ▼
 ┌─ READ ──────────────────────────────────────────────────────────────────────────┐
 │ documents.render_pages    whole page fitted in a 768 × 1536 box, RGB PNG        │
 │ answering                 select_profiled_pages_within_context (context check)  │
 │                           build_profiled_request (LUNA_PROFILE, contract b1)    │
 │                           check_profiled_request: token and cost bound, refused │
 │                           before any call if over the ceiling                    │
 │ reply cache               keyed by request fingerprint; on a miss, one call:    │
 │                           gpt-6-luna, temperature 0, reasoning_effort none,     │
 │                           image detail high, strict JSON schema, 800 tokens     │
 └──────────────────────────────────────┬──────────────────────────────────────────┘
                                        ▼
 ┌─ VERIFY ────────────────────────────────────────────────────────────────────────┐
 │ citations.check_citations  cited pages ⊆ supplied pages; off-by-one; missing    │
 │ citations.check_grounding  each quote found on its cited page (normalised,      │
 │                            score ≥ 0.9); numbers in the answer present on a     │
 │                            cited page                                            │
 └──────────────────────────────────────┬──────────────────────────────────────────┘
                                        ▼
 B1Result: answer or "Not answerable", cited pages, quotes, checks, three-step trace
```

**The contract (b1).** The reply must match a strict JSON schema with three required fields: `answer` (string, number or list), `cited_pages` (integers) and `evidence` (a list of `{page, quote}`). The prompt `b1-image-v2` is the frozen `mmlb-image-v1` prompt plus one sentence asking for a verbatim passage of at most 30 words per cited page. Abstention is the exact string `Not answerable` (`docs/baseline_b1_specification.md` §4.2).

**Why each step is there.**

| Step | Choice | Evidence |
|---|---|---|
| Text extraction with OCR fallback | needed for BM25 and for grounding checks, not sent to the reader | E0 (OCR raises BM25 Recall@5 from 0.358 to 0.689); E3 (adding text to the prompt did not help) |
| 768-px images | the reader sees page images only | E1 (10/37 → 16/37 with GPT-4o-mini); E3 |
| ColQwen2 primary, BM25 fallback | no fusion | E5, E6; notebook 07 (RRF and interleaving worse than ColQwen2 alone); **confirmed held out**: the final evaluation's B1 − T1 is +0.119, `visual_retrieval_confirmed` |
| k = 4, one read | no adaptive deepening | E6 read 4 pages for 105 of 118 questions; E9 `no_meaningful_gain`; held out, the adaptive policy's +0.021 is a secondary result that by rule does not change the shipped system |
| One-shot read | not extract-then-answer | E7 `regression` |
| `gpt-6-luna`, contract b1 | the successor reader with structured, quotable evidence | E8 (non-inferior; citation validity 1.000) |
| Grounding check | shown to the user as a trust signal, never used to retry or repair | E8: grounding failure is *anti*-predictive of a wrong answer |

### 2.1 The reader profile

Everything model-specific sits in a `ReaderProfile` (`answering.py`), so the pipeline itself is model-neutral.

| Field | `LUNA_PROFILE` (B1) | `GPT4O_MINI_PROFILE` (frozen, for parity) |
|---|---|---|
| model | `gpt-6-luna` (alias, no dated snapshot) | `gpt-4o-mini-2024-07-18` |
| request parameters | `reasoning_effort: none`, `temperature: 0` | `temperature: 0` |
| maximum output tokens | 800 | 400 |
| context checked against | 128,000 tokens | 128,000 tokens |
| image tokens | `floor(1.2 × ceil(w/32) × ceil(h/32))`, measured by the E8 smoke | tile rule: 2,833 + 5,667 per 512-px tile |
| text tokens | `o200k_base` + 10 (text-only) or 9 (multimodal) framing tokens + 100 for the strict schema | byte-length upper bound + 100 framing |
| list price per 1M tokens (input / output) | $0.10 / $0.50 | from the 2026-11-22 price list |

The 128,000-token context check in `LUNA_PROFILE` is a code setting; the consolidation assessment lists a much larger documented context for `gpt-6-luna` (`docs/baseline_consolidation_assessment.md` §6.1). At 4 pages, B1 requests average 3,977 prompt tokens (E9 B1s arm), so the check never binds in practice.

### 2.2 The five pinned modules

| Module | Role in B1 | Pinned by |
|---|---|---|
| `documents.py` | PDF validation, SHA-256, native text + OCR, 768-px rendering, 1-based page access | `application_module_sha256` in `experiments/specs/e8_reader_migration_v1.json` |
| `retrieval.py` | `Retriever` protocol, `BM25Index`, `maxsim_score`, `CachedVisualIndex`, `FrozenRankingRetriever` | same |
| `answering.py` | `ReaderProfile`, `LUNA_PROFILE`, contracts `v1` and `b1`, request builder, token and cost guard, reply parser, request fingerprint | same |
| `citations.py` | citation form check, quote and numeric grounding | same |
| `pipeline.py` | `answer_question_b1`, `Budget`, `Step`, `B1Result`, reply caches, `append_run_log`; also the legacy GPT-4o-mini path measured in E4 (`answer_question`, `python -m visualdoc.pipeline`) | same |

`tests/test_b1.py` recomputes these hashes against the frozen E8 specification. A change to any of the five modules is therefore a new experimental condition, not a fix (`AGENTS.md`). `parsing.py` is an older page-routing baseline, kept with its tests and not used.

The legacy `python -m visualdoc.pipeline` command (BM25 → images → GPT-4o-mini) is the application E4 measured. Its `--live` mode stops working when `gpt-4o-mini-2024-07-18` shuts down on 2027-01-14 (`docs/validated_baseline_b1.md` §5).

---

## 3. The application layer

Three new modules wrap the pinned ones. Each question still goes through `pipeline.answer_question_b1` unchanged, so the application ships what E8 measured (`docs/application.md` §4).

```
 ┌──────────── web.py ────────────┐   ┌──────────── CLI ────────────┐
 │ stdlib http.server, 127.0.0.1  │   │ python -m visualdoc.app     │
 │ one HTML page, no JavaScript   │   │   ask | index | serve       │
 └───────────────┬────────────────┘   └──────────────┬──────────────┘
                 └──────────────┬────────────────────┘
                                ▼
 ┌──────────────────────── app.py: B1App ───────────────────────────────────────────┐
 │ documents: content-addressed registration (SHA-256), page cap, test-pool guard   │
 │ retriever choice: visual index + query embedding → CachedVisualIndex;            │
 │                   otherwise BM25, with the reason recorded                        │
 │ spending: per-request ceiling ∧ remaining session budget                          │
 │ reader: OfflineB1Reader (placeholder, default) or the paid OpenAI client (--live) │
 │ reply caches (one per mode and model) · run log · served-model change warning     │
 └───────────────┬───────────────────────────────────────┬──────────────────────────┘
                 ▼                                       ▼
 ┌──── visual_index.py ─────────────────────┐   ┌── pinned modules ───────────────┐
 │ VisualIndexStore: bf16 safetensors,      │   │ pipeline.answer_question_b1     │
 │   key checked on every load              │   │ documents · retrieval ·         │
 │ E5 importer (no model needed)            │   │ answering · citations           │
 │ StoreQueryEncoder (cached query vectors) │   └─────────────────────────────────┘
 │ ColQwen2Encoder (lazy torch, two passes) │
 └──────────────────────────────────────────┘
```

| Module | Responsibilities |
|---|---|
| `visual_index.py` | A NumPy-only safetensors codec for bfloat16 (NumPy has no bf16 type, so values are stored as their upper 16 bits and widened exactly to float32); a keyed, atomic embedding store; an importer for notebook 04's E5 embeddings; a cache of query embeddings; `ColQwen2Encoder`, ported from notebook 04's two-pass encoding. torch and transformers are imported only inside the encoder. |
| `app.py` | `B1App`: document registration, retriever selection, spending guards, reply caches, run log; `OfflineB1Reader`; the `ask`, `index` and `serve` commands. |
| `web.py` | A local page to upload or pick a PDF, ask a question and see the answer, cited-page thumbnails, quotes and checks. |

**Offline by default.** `OfflineB1Reader` calls no model and returns a placeholder that cites the first supplied page and quotes its first words. Every output marks it **OFFLINE PLACEHOLDER**. Retrieval, page selection and the request (fingerprint, token bound, cost bound) run as in B1. The citation and grounding checks also run, but on the placeholder, so their verdicts mean nothing; the web page greys them out. Offline run-log records report `charged_usd: 0`.

**Visual retrieval needs two cached things:** the PDF's page embeddings and the exact question's embedding. The E5 cache supplies both for the 20 development documents and their 175 questions. Encoding anything new needs the ColQwen2 checkpoint (4.4 GB) and `--load-encoder`. Before encoding, the encoder checks that it is E5's encoder: hashes of the processor and tokenizer files, the preprocessing settings, torch 2.15.0 and transformers 5.23.0, the query prompt rule, and the SHA-256 of the weights; any difference raises an error and the app falls back to BM25 with that reason. The encoder's orchestration is tested on a small fake model only, because the checkpoint is an iCloud placeholder on the development machine (`docs/application.md` §3).

**Not in the application, by evidence:** no fusion of retrievers (notebook 07), no extract-then-answer (E7), no adaptive deepening (E9), no repair loop driven by grounding (E8).

---

## 4. Caches and their keys

| Cache | Location (git-ignored unless stated) | Key | Written by |
|---|---|---|---|
| Benchmark page images | `data/cache/mmlongbench_doc/page_images/<render box>/` | render box in the folder name; per-page SHA-256 in the render manifests | notebooks 00, 04 |
| Page records | `data/processed/mmlongbench_doc/{questions,pages}.parquet`, `e5/heldout_pages.parquet` | dataset revision and settings recorded beside them | notebooks 00, 04 |
| E5 page and query embeddings | `data/cache/e5/colqwen2-v1.0-hf@ddc07d2317c8/<config hash>/` | a hash over model revision, weight hash, library versions, device, dtype, preprocessing, prompts and embedding rule | notebook 04 |
| ColQwen2 checkpoint | `data/cache/hf/colqwen2-v1.0-hf@ddc07d2317c8/` (E5; now an evicted iCloud placeholder); for the final evaluation, the same revision in the Hugging Face cache outside the repository | revision in the folder name; weight, preprocessor and tokenizer hashes equal E5's | notebooks 04, 09 |
| Final-evaluation page and query embeddings | `data/cache/final/` (about 1 GB) | SHA-256 of every page embedding in `experiments/frozen/final_index/index_manifest.csv`, of every query embedding in `experiments/frozen/final_retrieval/query_manifest.csv` | notebook 09 (`index`, `queries`) |
| Final-evaluation tables | `data/processed/mmlongbench_doc/final/` | document and page tables, encoding log, plan design, evaluation; frozen copies in `experiments/frozen/final*/` | notebook 09 |
| Application visual index | `data/cache/app/visual_index/vidore--colqwen2-v1.0-hf@ddc07d2317c8/short768-long1536/<pdf sha256>.safetensors` | (PDF SHA-256, render profile, model id, model revision), written inside the file and checked on every load; a mismatch raises `IndexKeyMismatch` | `visual_index.py` |
| Application query embeddings | `…/queries/<sha256 of the exact question>.safetensors` | (model id, revision, SHA-256 of the question) | `visual_index.py` |
| Application reply caches | `data/cache/app/replies_offline.jsonl`, `replies_live_gpt-6-luna.jsonl` | request fingerprint; one file per mode and model, so a placeholder is never replayed as a live answer; failed replies are not cached | `app.py` via `pipeline.JsonlReplyCache` |
| Application run log | `data/cache/app/run_log.jsonl` | append-only JSON lines in `append_run_log`'s format plus `record`, `mode`, `charged_usd` and `time`; live mode writes an `attempt` record before each send, then `answer` or `attempt_failed`; an `answer` holds the full B1 result with its retrieve / read / verify trace and the BM25 pages logged beside | `app.py` |
| Uploaded PDFs | `data/cache/app/uploads/<sha256>.pdf` | PDF SHA-256 | `app.py`, `web.py` |
| Experiment response caches | `experiments/runs/<exp>/<run-id>/response_cache.jsonl` | SHA-256(run id : replicate : request fingerprint): scoped to one run and one replicate | notebooks 02, 05–08 |
| Experiment run logs | `experiments/runs/<exp>/<run-id>/execution_log.jsonl` | append-only, one record per call with fingerprint, usage and served identity | notebooks 02, 05–09 |
| Frozen runs (tracked) | `experiments/frozen/<exp>/` | byte-identical copies, protected by `SHA256SUMS` | copied after each run |

Two design points recur. **Content addressing:** a document is identified by the SHA-256 of its bytes, a request by the fingerprint of its loggable form, a question embedding by the SHA-256 of its text. **Key inside the artefact:** the visual index stores its own key, so a file moved or renamed cannot be silently reused for another PDF, rendering or checkpoint. Writes are atomic (temporary file, fsync, rename).

The B1 specification asks for a reply-cache key of (fingerprint, served model). The served model is known only after a call, so the application records and checks it instead of keying on it (`docs/application.md` §5).

---

## 5. Budgets and guards

### 5.1 In the application

| Guard | Default | Where | Source |
|---|---|---|---|
| Pages read, `k` | 4 (allowed 1–10) | `app.py`, `pipeline.Budget` | `docs/application.md` §5 |
| `Budget` | one call, 4 pages, $0.01 | `pipeline.Budget` | `src/visualdoc/pipeline.py` |
| Per-request ceiling | $0.01 (`--max-request-usd`) | `app.py`, enforced by `answering.check_profiled_request` before any call | `docs/application.md` §2 |
| Session ceiling | $0.10 (`--session-ceiling-usd`), cumulative for one process | `app.py` | same |
| Charging rule | a request is charged its upper bound when sent; a failed or timed-out call still counts; reported usage above the bound is charged too | `app.py` | same (E8's rule) |
| Live client | `OpenAI(max_retries=0, timeout=120)`, the notebooks' settings: the library's default would silently retry, and each retry could be billed | `app.py` | same |
| Upper bound of one B1 question | about $0.0008 at list price (about 4,000 prompt tokens + 800 output tokens) | — | same |
| Served identity | served model and system fingerprint recorded per call, including for replies served from the cache; a warning when either changes in a session | `app.py` | same |
| PDF size | up to 200 pages (the product contract's configurable limit) | `app.py` | `docs/baseline_b1_specification.md` §3 |
| Test pool (used once by the final evaluation) | all 115 pool document names (from `resources/mmlongbench_doc_documents.json`) are refused, on disk or not, for a path, a question or an upload; one pool PDF whose bytes were on disk is also refused by SHA-256; the check is mainly by name, so a renamed copy is not recognised | `app.py` | `docs/application.md` §4 |
| Web page | binds to 127.0.0.1; Host header must be `127.0.0.1` or `localhost`; a random per-server token on every POST; bounded request bodies (uploads 50 MB, forms 64 KB); a 15 s socket timeout per connection; HTML-escaped output; a Content-Security-Policy that forbids scripts | `web.py` | `docs/application.md` §4 |
| Live mode | opt-in `--live`; needs `OPENAI_API_KEY` exported; `.env` is never read | `app.py` | `docs/application.md` §2 |

**A known interaction.** The pinned pipeline checks the cost ceiling before it looks up the reply cache. Near the session ceiling, even a cached reply is therefore refused (`docs/application.md` §5).

### 5.2 In the experiments

| Guard | Rule | Source |
|---|---|---|
| Opt-in paid modes | one mode variable per notebook: `VISUALDOC_QA_MODE` (default `replay`), `VISUALDOC_E*_MODE` and `VISUALDOC_FINAL_MODE` (default `offline`); `smoke`, `pilot`, `full` need the owner's explicit approval | `AGENTS.md`; notebook 09 |
| Frozen specification | paid modes refuse to run unless the spec (and the notebook's code) equal the committed version | `experiments/README.md`; frozen READMEs |
| Cumulative ceiling | fail-closed across smoke and full; unknown usage charged at its upper bound ($0.50 for E9, $2.50 for the final evaluation) | notebook 08, Stages 1–2; `experiments/specs/final_evaluation_v1.json` |
| No silent retries | no SDK retries; at most two attempts per planned request; stop on any API error, contract failure, or change of served model or system fingerprint. `gpt-6-luna` returned no system fingerprint on any E8 or E9 call, so in practice only the served-model check could fire | notebook 08 (E9, "as E8"); E9 independent audit |
| Exclusive run directories | each paid invocation creates a new `experiments/runs/<exp>/<run-id>/` and never overwrites one | `experiments/README.md` |
| Smoke gate | a few technical calls must pass every check before a full run is proposed; the final evaluation's smoke used development questions only | E8, E9 and final smoke runs |
| Encoding only on the M1 GPU | notebook 04 and notebook 09's `index` and `queries` modes assert Apple MPS: the specs require bit-for-bit equality with E5's embeddings, and another GPU type gives slightly different numbers. A parity gate re-encodes development pages and a question and requires bitwise equality with the E5 cache before any pool page is encoded | notebook 09 (`fe-encoder`, `fe-parity`); `docs/ssp_cloud.md` |
| Frozen rankings elsewhere | on any other machine, notebook 09 reads the frozen rankings in `experiments/frozen/final_retrieval/` and only checks that recomputed scores agree within 1e-4 | `experiments/frozen/final_retrieval/README.md` |
| Index before questions | the pool index was committed before any pool question was read; the `queries` mode refuses to run until the index manifest is committed | `experiments/frozen/final_index/README.md`; notebook 09 |

---

## 6. The notebook-first research workflow

Notebooks are the record of how each choice was measured. They communicate **only through saved files**; each states its inputs and outputs at the top and stops with a clear message if an input is missing (`AGENTS.md`).

```
 MMLongBench-Doc, revision 2ff6aa92…                 experiments/specs/*.json
 (question table tracked; PDFs downloaded)           (frozen and committed before any call)
          │                                                        │
          ▼                                                        │
 00 document processing ──► data/processed/mmlongbench_doc/{questions,pages}.parquet
          │                 data/cache/mmlongbench_doc/page_images/ (512 px, 768 px)
          ▼
 01 retrieval ──► rankings.parquet
          │
          ▼
 02 question answering ──► E0 conditions A–D, E1–E4 requests and executors
          │
          ▼
 03 evaluation ──► S-v1 scorer (cell f653d232), E0–E4 results and figures
          │
          ▼
 04 visual retrieval (E5) ──► held-out page records, data/cache/e5/ embeddings
          │
          ├──► 05 E6: ColQwen2 pages vs BM25 pages, end to end
          ├──► 06 E7: extract-then-answer
          ├──► 07 B1: retrieval complementarity, S-v2, E8 reader migration
          ├──► 08 E9: trigger selection (Stage 0), adaptive arms (Stage 2)
          └──► 09 final held-out evaluation (test pool, used once):
                 index (M1 only) ──► frozen/final_index ──► queries (M1 only) ──► frozen/final_retrieval
                 ──► smoke, full reader run ──► frozen/final

 every paid run ──► experiments/runs/<exp>/<run-id>/   (git-ignored, append-only)
                        │ copied byte for byte after the run
                        ▼
                    experiments/frozen/<exp>/   (tables, AUDIT.json, PROVENANCE.json, SHA256SUMS)
                        │
                        └──► read back by the notebook's default mode and asserted
```

| Notebook | Stage | Reads | Writes (git-ignored) | Mode variables |
|---|---|---|---|---|
| 00 | E0 data | question table, 6 PDFs | page records, renders | — |
| 01 | E0 retrieval | 00 outputs | rankings, retrieval tables | — |
| 02 | E0 conditions, E1–E4 execution | 00–01 outputs, `experiments/frozen/` | predictions, request plans | `VISUALDOC_QA_MODE`, `VISUALDOC_E1_MODE` … `VISUALDOC_E4_MODE` |
| 03 | E0–E4 evaluation | 00–02 outputs, frozen runs | evaluation summaries, figures | `VISUALDOC_E1_RUN_DIR` … `VISUALDOC_E4_RUN_DIR` |
| 04 | E5 (no API) | 00–01 outputs, 14 held-out PDFs, ColQwen2 checkpoint | held-out pages, embeddings | — |
| 05 | E6 | 00 and 04 outputs, frozen E5, E4 | E6 tables | `VISUALDOC_E6_MODE` |
| 06 | E7 | 00 and 04 outputs, frozen E5, E6 | E7 tables | `VISUALDOC_E7_MODE` |
| 07 | B1 consolidation, E8 | 00 and 04 outputs, frozen E5–E8, S-v2 labels | `data/processed/mmlongbench_doc/b1/` | `VISUALDOC_QA_MODE`, `VISUALDOC_E8_RUN_DIR` |
| 08 | E9 | frozen E5 and E8 tables, frozen E9 | `data/processed/mmlongbench_doc/e9/` | `VISUALDOC_E9_MODE` |
| 09 | final held-out evaluation | frozen spec and plan, document list, pool PDFs at the pinned revision, ColQwen2 snapshot and E5 cache (parity gate), frozen `final_index`, `final_retrieval` and `final` | `data/processed/mmlongbench_doc/final/`, `data/cache/final/` | `VISUALDOC_FINAL_MODE` (`offline`, `index`, `queries`, `smoke`, `full`) |

Each notebook follows Objective → Method → small sequential implementation cells → Validation (including a failure case) → Results → Interpretation. Important operations are shown once by hand before being wrapped in a helper (for example BM25 on one question in notebook 01).

---

## 7. Frozen packages and specifications

**Specifications** (`experiments/specs/`): one JSON file per experiment from E1 to E9, frozen and committed before the first paid call. E2 has a superseded v1 and a v2 that changed only execution rules; E9 has a technical addendum committed before its paid stages. The final evaluation has `final_evaluation_v1.json` (approved and frozen before any pool access, commit `1c54a3e`), `final_evaluation_v1_plan.json` (the frozen 2,079-call plan) and `final_evaluation_v1_deviations.md` (D1, D2, each committed before any result it could affect). `docs/final_evaluation_specification.md` is the historical draft.

**Frozen packages** (`experiments/frozen/`, never edited):

| Package | Content |
|---|---|
| `mmlongbench_doc/` | the E0 text and image runs |
| `e1/` … `e7/` | run copies, per-question tables, evaluation summaries, figures where produced, audit, provenance, checksums |
| `e8_smoke/` | the six-call technical diagnostic and measured reader profile |
| `e8/` | the 354-call E8 execution, S-v1 evaluation, blind S-v2 queue and sealed key |
| `scoring_v2/`, `e8_scoring_v2/` | the owner's blind S-v2 labels, with item-identity hashes |
| `e9_stage0/` | E9 trigger selection and its independent audit script and output |
| `e9/` | E9 smoke and Stage 2 run, evaluation tables, blind queue (13 items) and sealed key, the independent Stage 2 audit (`AUDIT.json`, 47/47, with its script in `audit/`), provenance, checksums |
| `final_index/` | the pool index, frozen before any question was read: the 111 pool documents and their hashes, a per-page manifest (render and embedding SHA-256, no text) for 5,554 pages of 110 documents, the parity gate, a summary |
| `final_retrieval/` | ColQwen2 and BM25 rankings and scores for the 872 questions, U3 and its trigger, the per-question query-embedding hashes (no question text) |
| `final/` | the final evaluation's smoke and full run, per-question evaluation (no reply text), summary, blind S-v2 queue (85 items) and sealed key, independent audit (`AUDIT.json` and script), provenance, checksums |

Run files contain request fingerprints, image hashes, prompts and replies; they never contain page images, Base64 payloads or credentials, and most contain no question text. Checksums are verified with `shasum -a 256 -c SHA256SUMS` in each folder (see `docs/reproducibility.md`).

---

## 8. How experiments map to code

| Exp. | Notebook (sections) | Spec | Frozen package | Imports `src/visualdoc`? | Effect on the application |
|---|---|---|---|---|---|
| E0 | 00, 01, 02 §1–9, 03 §1–10 | — | `mmlongbench_doc/` | no | OCR policy (`documents.py`), BM25 parameters (`retrieval.py`) |
| E1 | 02 §10, 03 §11–13 | `e1_image_resolution_v1` | `e1/` | no | 768 × 1536 render box (`documents.py`) |
| E2 | 02 §11, 03 §14 | `e2_stronger_vlm_v2` | `e2/` | no | none (GPT-4o-mini kept at the time) |
| E3 | 02 §12, 03 §15 | `e3_text_image_fusion_v1` | `e3/` | no | image-only reader requests |
| — | 03 §16 | — | — | yes (measures the application offline) | documented evidence lost to the context guard |
| E4 | 02 §13, 03 §17 | `e4_application_end_to_end_v1` | `e4/` | yes (the application as shipped is the object) | none; it measured `pipeline.answer_question` |
| E5 | 04 | `e5_visual_retrieval_v1` | `e5/` | no (the independent audit checked arm A against the application's functions) | ColQwen2 chosen; later `retrieval.CachedVisualIndex`, `visual_index.py` |
| E6 | 05 | `e6_visual_retrieval_answering_v1` | `e6/` | no (the audit rebuilt every request through the application) | ColQwen2 default, BM25 fallback |
| E7 | 06 | `e7_extract_then_answer_v1` | `e7/` | no | one-shot reading kept |
| B1 consolidation | 07 §A–B | — | `scoring_v2/` | no | no fusion; BM25's four roles; S-v2 |
| E8 | 07 §C–D | `e8_reader_migration_v1` | `e8_smoke/`, `e8/`, `e8_scoring_v2/` | yes (imports and hashes the five modules; 236/236 unique requests equal the notebook's construction) | `LUNA_PROFILE`, contract b1, grounding, `Budget`, caches, run log; module hashes pinned |
| E9 | 08 | `e9_adaptive_evidence_v1` + addendum | `e9_stage0/`, `e9/` | no (proves B1s requests equal frozen E8 L-B1) | none: k stays 4, one read |
| Application | — | — | — | — | `visual_index.py`, `app.py`, `web.py` (new modules; the owner's instruction of 2026-11-25 is the approval `AGENTS.md` requires) |
| Final evaluation | 09 | `final_evaluation_v1` + plan + deviations | `final_index/`, `final_retrieval/`, `final/` | no (rebuilds every step in cells; development parity with E5 rankings and E8 requests) | none: B1 evaluated as frozen and kept as shipped; C2 confirms ColQwen2 as the retriever |

Tests tie the two layers together: `tests/test_b1.py` pins the module hashes and checks frozen-package integrity; `tests/test_visual_index.py` reproduces all 175 frozen E5 visual rankings from the cached embeddings; `tests/test_app.py` rebuilds frozen E8 L-B1 requests byte for byte through the application and parses their frozen replies identically (`docs/application.md` §6).
