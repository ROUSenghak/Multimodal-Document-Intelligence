# The B1 application: usage and architecture

**What it does.** You give it a PDF and a question. It returns an answer, the pages it cites, and a short verbatim quote from each cited page. It also shows whether each quote was found on its page.

This is the validated baseline B1 (`docs/validated_baseline_b1.md`) packaged as a command-line tool and a small local web page. It is built from the same functions E8 measured, so it ships what was evaluated.

```
PDF ──► page images, 768 px short side (documents.render_pages)
     ──► ColQwen2 v1.0 MaxSim over every page (visual_index + retrieval.CachedVisualIndex)
     ──► top k = 4 pages
     ──► one gpt-6-luna call, contract b1: {answer, cited_pages, evidence[{page, quote}]}
     ──► citation check + grounding check (citations.py)
```

BM25 (native text, OCR below 30 words) is computed for every question and logged beside the visual ranking. It becomes the retriever only when the visual path cannot run, and the result records why.

---

## 1. Running it offline (no cost)

Use the project environment: `.venv/bin/python` (Python 3.12). If `import visualdoc` fails, prefix the commands with `PYTHONPATH=src`.

```bash
# Ask one question (BM25 fallback until the PDF has a visual index)
PYTHONPATH=src .venv/bin/python -m visualdoc.app ask data/documents/ch2.pdf "What does Cromwell's rule say about prior probability?"

# The same, as JSON
PYTHONPATH=src .venv/bin/python -m visualdoc.app ask data/documents/ch2.pdf "..." --json

# Build a visual index for a development document from notebook 04's E5 embeddings (no model needed)
PYTHONPATH=src .venv/bin/python -m visualdoc.app index data/external/mmlongbench_doc/documents/watch_d.pdf --from-e5-cache

# Start the web UI, then open http://127.0.0.1:8765
PYTHONPATH=src .venv/bin/python -m visualdoc.app serve
```

**Offline answers are placeholders.** `OfflineB1Reader` calls no model. It cites the first supplied page and quotes that page's first words, so the citation and grounding checks run on a reply of the right shape. The CLI, the JSON (`"offline_placeholder": true`) and the web page all mark the answer as **OFFLINE PLACEHOLDER**.

What runs as in B1 offline:
- retrieval and page selection;
- the request that would be sent, with its fingerprint, token bound and cost bound.

The citation and grounding checks also run, but on the placeholder reply, so their verdicts mean nothing. The web page greys them out and labels them *"computed on a placeholder reply"*. Offline run-log records report `charged_usd: 0` and no spend in the trace.

**Visual retrieval offline** needs two things:
- a page index for the PDF;
- a cached embedding for the exact question.

The E5 cache holds both, but only for the 20 development documents and their 175 benchmark questions. For any other question, the app falls back to BM25 and shows the reason: *"no cached ColQwen2 embedding for this question and the live encoder is off"*.

---

## 2. Live mode (paid; only with the owner's approval)

```bash
export OPENAI_API_KEY=...        # the app never reads .env
PYTHONPATH=src .venv/bin/python -m visualdoc.app ask data/documents/ch2.pdf "..." --live
PYTHONPATH=src .venv/bin/python -m visualdoc.app serve --live
```

- One B1 question (4 pages) has an upper bound of about **$0.0008** at list price: about 4,000 prompt tokens plus 800 output tokens.
- **Per-request ceiling:** `--max-request-usd`, default $0.01.
- **Session ceiling:** `--session-ceiling-usd`, default $0.10. It is cumulative for one process.
- Both ceilings are enforced by the pinned `check_profiled_request` before any call. The request's limit is the smaller of the per-request ceiling and the remaining session budget.
- The session is charged a request's upper bound when the request is sent. A call that fails or times out may still be billed, so it is still counted (E8's rule). If the reported token usage ever costs more than the bound, the difference is charged too.
- The client is `OpenAI(max_retries=0, timeout=120)`, the notebooks' settings. The library's default would silently retry twice, and each retry could be billed while the session is charged once.
- Before sending, the run log gets an `attempt` record (fingerprint, upper bound, charge). A call that raises gets an `attempt_failed` record. Every answered question gets an `answer` record with `mode` and `charged_usd`.
- `gpt-6-luna` is an alias. The served model and system fingerprint are recorded per call. The app warns when either changes within a session, because AGENTS.md treats that as a new condition. Replies served from the cache are checked the same way, because the cache key does not include the served model (§5).

---

## 3. Visual index and the live encoder

**Store.** The index is stored at `data/cache/app/visual_index/vidore--colqwen2-v1.0-hf@ddc07d2317c8/short768-long1536/<pdf sha256>.safetensors`:
- one file per document, one bf16 matrix (tokens × 128) per page;
- the key is (PDF SHA-256, render profile, model id, model revision). It is written inside the file and checked on every load, so a file stored under another key raises `IndexKeyMismatch` instead of being reused;
- writes are atomic: temporary file, fsync, rename.

**Query embeddings** are stored in `.../queries/<sha256 of the exact question>.safetensors`.

**Building an index with the encoder:**

```bash
PYTHONPATH=src .venv/bin/python -m visualdoc.app index <pdf> --load-encoder
```

`--load-encoder` runs notebook 04's two-pass encoding:
- pass 1 runs the vision tower alone;
- pass 2 runs the language model with a stub that returns the pass-1 features.

E5 showed that these two passes are bitwise identical to a single pass, and that they fit in 8 GB of memory. About 13 s per page on the M1. The GPU cache is emptied after each pass, as in notebook 04.

**The encoder must be E5's encoder.** Before encoding anything, it checks:
- the SHA-256 of `preprocessor_config.json` and `tokenizer.json`;
- the preprocessing settings: min/max pixels 3,136 / 602,112, patch 14, merge 2;
- torch 2.15.0 and transformers 5.23.0;
- the processor's prompts and query rule: `"Query: "` + question + 10 × `<|endoftext|>` + newline, observed on a probe text;
- the SHA-256 of the 4.4 GB weights. This is hashed once per file version (size and modification time) and recorded in `encoder_work/weights_check.json` and in each index's metadata.

The expected values are E5's (`E5_ENCODER_IDENTITY`); a test compares them with the E5 cache's `config.json`. Any difference raises an error, and the app falls back to BM25 with that reason.

Pass-1 features are kept under a folder named after the model, revision and settings, so features from other settings are never reused.

**Not executed in tests.** The checkpoint (`data/cache/hf/colqwen2-v1.0-hf@ddc07d2317c8/model.safetensors`, 4.4 GB) is an iCloud placeholder on this machine. The app checks it with `os.stat` only and refuses to enable the encoder without opening it.
- The tests run the encoder's orchestration on a small fake model.
- They run the identity checks on the real small files and the real processor, with a guard that fails if anything opens the weights.

---

## 4. Architecture

| Module | Role | State |
|---|---|---|
| `documents.py` | PDF validation, SHA-256, text (native + OCR), 768-px rendering | pinned (E8 hashes) |
| `retrieval.py` | BM25, `maxsim_score`, `CachedVisualIndex` | pinned |
| `answering.py` | `LUNA_PROFILE`, contract `b1`, request builder, token/cost guard, parser | pinned |
| `citations.py` | citation check, quote and numeric grounding | pinned |
| `pipeline.py` | `answer_question_b1` (retrieve, read, verify), `Budget`, `JsonlReplyCache`, `append_run_log` | pinned |
| `visual_index.py` | bf16 safetensors codec (NumPy only), keyed store, E5 importer, `ColQwen2Encoder` (lazy torch) | **new** |
| `app.py` | `B1App` service: documents, index, guards, caches, run log; CLI | **new** |
| `web.py` | stdlib `http.server` UI: one HTML page, no JavaScript | **new** |

**The pinned modules are not edited.** `tests/test_b1.py` checks their SHA-256 against the frozen E8 specification. Each question goes through `pipeline.answer_question_b1` unchanged.

**Files written** (all git-ignored, under `data/cache/app/`):
- `visual_index/`: the page and query embeddings;
- `replies_offline.jsonl` and `replies_live_gpt-6-luna.jsonl`: separate reply caches, so a placeholder can never be replayed as a live answer. Failed replies are not cached;
- `run_log.jsonl`: JSON lines in `append_run_log`'s format, plus `record`, `mode`, `charged_usd` and `time`. Live mode writes an `attempt` record before each send, then `answer` or `attempt_failed`. An `answer` record holds the full B1 result. Its trace is retrieve, read, verify, plus `baseline_retrieve` (the BM25 pages logged beside). `append_run_log` itself cannot carry the mode or the charge, so the app writes these lines directly;
- `uploads/<sha256>.pdf`: uploaded PDFs. A refused upload (corrupt, encrypted, too long, pool) is deleted;
- `encoder_work/`: temporary pass-1 features, deleted after pass 2, and the weights hash record.

**Web UI safeguards:**
- it binds to 127.0.0.1 only and accepts only a `127.0.0.1` or `localhost` Host header, on GET and POST;
- every POST needs a random per-server token, compared as bytes. The upload form carries it in its URL, so it is checked before the body is read;
- request bodies are bounded before they are read (uploads 50 MB, forms 64 KB);
- each connection has a 15 s socket timeout, so an idle client cannot block the single-threaded server;
- `k` must be a whole number;
- every user or model string is HTML-escaped;
- a Content-Security-Policy forbids scripts, and page images carry `Cross-Origin-Resource-Policy: same-origin`.

**Untouched test pool.** `resources/mmlongbench_doc_documents.json` lists all 135 MMLongBench-Doc document names at revision `2ff6aa92…`. It was built from the `doc_id` column only; document names are level-0 frame metadata in `experiments/test_pool_ledger.md`. A test pins the file's SHA-256.
- The app refuses any of the 115 names outside the 20 development documents, whether or not the file is on disk, for a path, an `ask` or an upload. The UI lists only the 20 plus `data/documents/`.
- It also refuses by SHA-256 the one pool PDF whose bytes were on disk. The 3 other pool PDFs on disk are iCloud placeholders and were not read.
- **The check is mainly by name.** A renamed copy of any other pool PDF is not recognised. The final-evaluation protocol remains the safeguard.

---

## 5. Known limitations

- **Text is extracted twice per question.** The app extracts page text once per document, for BM25 logging and display. `answer_question_b1` extracts it again internally. That is negligible for born-digital PDFs but costs OCR time on scanned pages. Removing it would mean changing a pinned module.
- **Cached replies can be refused near the session ceiling.** The pinned pipeline checks the cost ceiling before it looks up the reply cache. Once the remaining session budget is below one request's upper bound, even a cached reply is refused.
- **The reply cache is keyed by request fingerprint only, with one file per mode and model.** The B1 specification asks for a key of (fingerprint, served model). The served model is only known after the call, so it is recorded with each reply instead. A replayed reply's served model and fingerprint are checked against the requested model and against the session's first reply, and a mismatch is shown as a warning.
- **Grounding is a trust signal for the reader, not a correctness signal.** E8 found it anti-predictive of correctness. Nothing in the app uses it to retry or repair an answer.
- **No adaptive retrieval.** E9 tests it. `k` (1–10, default 4) is the only retrieval parameter.

## 6. Tests

```bash
PYTHONPATH=src .venv/bin/python -m pytest -q
```

| File | What it checks |
|---|---|
| `tests/test_visual_index.py` | Codec: rewrites E5 files byte for byte. Keys and atomic writes. Key-mismatch refusal. Fake-model two-pass encoding equals one pass. Encoder identity: constants equal E5's `config.json`; the real small files and processor pass; a different encoder is refused; weights hashed once; the weights file is never opened. All 175 frozen E5 visual rankings reproduced from the cached embeddings, with scores within 1e-5 (skipped as a whole, never shrunk, if a manifest is missing). Store import from two PDFs reproduces their frozen rankings. |
| `tests/test_app.py` | Offline answers. BM25 fallback with its recorded reason. Visual retrieval with a fake encoder. Ceilings refuse before any call. Cache hits across sessions. Pool guard by name, on disk or not, and by hash. Live client settings (a fake `openai` module). Attempt records. CLI. The app rebuilds 14 frozen E8 L-B1 requests byte for byte, and parses their frozen replies identically. |
| `tests/test_web.py` | The server on an ephemeral port: JSON API, HTML escaping, token and Host checks on GET and POST, strict `k`, size limits, an idle connection, uploads, thumbnails, offline labels, cost refusal, API failure. |
