# Project progress log

The single place that records what is done, what is running, what each decision rests on, what has been spent, and what is still open. Newest entries first within each section. Dates are UTC+1.

## Status at a glance

| Milestone | State | Evidence |
|---|---|---|
| E0–E8 and validated baseline B1 | **done, frozen** | `docs/validated_baseline_b1.md`, `experiments/frozen/*` |
| E9 pre-registration | **done** | `experiments/specs/e9_adaptive_evidence_v1.json`, commit `7f41eea` (before any analysis) |
| E9 Stage 0 (offline trigger selection, $0) | **passed**; independently audited (reproduced ≤ 5e-7) | `experiments/frozen/e9_stage0/` (commit `a30bb29`) |
| E9 Stage 1 smoke (6 calls) | **passed** all 7 gates, $0.004592 | `experiments/frozen/e9/smoke_*` |
| E9 Stage 2 (354 calls) | **done: `no_meaningful_gain`** (S-v1). B1 unchanged. Independent audit 47/47. 13 S-v2 items await owner labels; no labelling can change the verdict | `experiments/frozen/e9/`, notebook 08 |
| E10 agentic reader (spec `25cd488`, smoke, 354-item run) | **done: `regression`** by the frozen broken-ratio rule (AGb 17 fixed / 9 broken), with +8 questions net in both replicates (45 → 53 of 102) and evidence recall of pages seen 0.726 → 0.866. B1 unchanged. Audit 31/31 (32/32 with the package sums). S-v2 labelled by the owner (`e10_scoring_v2`): +0.089 [+0.017, +0.177], p 0.025, verdict unchanged. $0.473 | `experiments/frozen/e10/`, notebook 10 |
| Application (B1 with live ColQwen2, cache, CLI, UI) | **built, reviewed, verified live.** 200 tests pass. Three live calls reproduced frozen E8 L-B1 requests, tokens and answers exactly. The live *encoder* is checked by notebook 09's parity gate | `src/visualdoc/{visual_index,app,web}.py`, commit `041827f` |
| Final held-out evaluation | **done, audited, frozen** (`c6c450d`). C1 B1 0.427; C2 `visual_retrieval_confirmed` (+0.119); C3 `a1_gain_supported` (+0.021, secondary). $0.993 | `experiments/frozen/final/` |
| Documentation (README, architecture, report, reproducibility, demo) | written; final-evaluation results are still to be added | `README.md`, `docs/{research_report,architecture,reproducibility}.md` |

## Decisions and their reasons

### 2026-11-27 — E10: an agentic reader (search, read, finish), development data

- **Why.** B1 answers 40/62 questions when its top 4 pages hold all the evidence, and 4/39 when they do not. Deeper reading of the same ranking (E9) can complete only 8 of the 39. A reader that writes new queries targets the other 31. Design and reasoning: `docs/e10_agentic_reader_proposal.md`.
- **Encoder on the Datalab CPU** (new condition). The weights were downloaded at the pinned revision (sha `2f6dbf32…` equals E5's). CPU query embeddings are not bitwise equal to E5's MPS ones (0/175, max |Δ| 0.12 in bf16). The pre-registered parity gate passed: top-4 set equal for 113/118 questions, recall@4 0.723 vs 0.726.
- **Two Datalab facts found.**
  - The container's CPU quota is 8 cores, although `nproc` says 256. 32–64 torch threads throttle: 12–19 s per query instead of 1.6 s.
  - `OPENAI_BASE_URL` is exported empty, which breaks the OpenAI SDK. Notebook 10 falls back to the official endpoint.
  - Both gate failures happened before any request reached the API.
- **Result.** B1s 45, AGa 53, AGb 53 of 102.
  - AG − B1s +0.078 [0.000, +0.181], p = 0.053.
  - The frozen verdict is `regression`, because AGb broke 9 > 17/2. Without that rule it would be `promising_but_uncertain` (p > 0.05, 12 flips).
  - Mechanism confirmed: evidence recall of the pages seen +0.140 [+0.084, +0.198].
  - Gain on the 39 incomplete-evidence questions: +0.256. Every broken question had its evidence complete in the top 4.
  - Causes of breaks: over-exploration; a different reading of the same pages in tool mode; answer format.
- **Exploratory.** The agent's own decision to stop at call 1 is a better router than E9's U3 trigger: always-agent 53 vs U3-routed 46/49.
- **Next.** Keep the search and remove the loss on easy questions (finish-first, B1 fallback, or a final read in B1's mode). Confirm on a new benchmark.


### 2026-11-26 — Datalab environment ready: pinned `.venv` built, notebook 09 audit reproduces the final evaluation

- **No CUDA 12 build of torch 2.15.0 exists.** It ships only for CUDA 13.2 and 13.4 (plus CPU, ROCm and XPU), which need NVIDIA driver 580 or later. The `vscode-python-gpu` A100 has driver 565.77 (CUDA ≤ 12.7). So `.venv-cu126` (torch 2.14.0+cu126) was left unchanged; any result from it is a new condition. The setup guide's GPU line, which would have installed the unusable CUDA 13 wheel, is corrected in `docs/ssp_cloud.md` §2.5.
- **`.venv` built as the pinned environment** (owner-approved): torch 2.15.0+cpu, `requirements/lock-2026-11-26.txt`, the project in editable mode, then `pip check` with no broken requirements. transformers is 5.23.0 and PyMuPDF 2.1. The `visualdoc-venv` kernel is registered. `pip freeze` snapshots from before the install are in `~/work/venv-freeze-before-setup.txt` and `~/work/venv-cu126-freeze-before-torch215.txt`.
- **`pytest` in `.venv`: 211 passed, 1 failed.** The ColQwen2 identity check now passes against the real tokenizer and processor. The one failure is the x86 OCR text of `bdf54dxa.pdf` page 11 (see the entry below). It is permanent on this processor and the pin is kept.
- **Notebooks.** All 10 are valid nbformat and use the `visualdoc-venv` kernel.
- **Notebook 09 offline audit**, executed in `.venv` with `VISUALDOC_FINAL_MODE=offline` and no API key in the environment; no error output:
  - "Index frozen and committed: True";
  - pool question embeddings complete;
  - 118/118 development rankings identical to E5 (max score difference 3.7e-6), and all 872 frozen rankings consistent;
  - 118/118 requests equal frozen E8 L-B1;
  - plan frozen;
  - "Paid gate closed";
  - C1 0.427, C2 `visual_retrieval_confirmed` (+0.119), C3 `a1_gain_supported` (+0.021).
  The combined digests of `data/cache/{mmlongbench_doc,final,e5}` and `git status` were unchanged by the run.
- **Caution: re-rendering notebooks overwrite the Mac page images.** Notebook 00 writes `page_*.png` unconditionally. Notebook 04 rewrites any whose bytes differ. Run here, either would silently replace some Mac images with x86 renders. Do not re-run them on the Datalab without first protecting `data/cache/mmlongbench_doc/page_images/` (restore source: `~/work/visualdoc-archive`, or `srou/visualdoc-mac-archive`). Notebook 09 writes images only in `index` mode, which refuses non-M1 machines.

### 2026-11-26 — Datalab test suite: two failures from one page rendered differently on x86-64; fixed by a provenance-checked archive import

**Symptom.** On the Datalab (`.venv-cu126`), `pytest` gave 2 failed, 198 passed, 6 skipped. Both failures were raised by `import_e5_document`: "the E5 cache has no embedding for 1 of 20 pages of e639029d16094ea71d964e2fb953952b.pdf (first: [15])".
- `test_visual_index.py::test_store_imported_from_the_pdf_reproduces_frozen_rankings[e639…]`
- `test_app.py::test_application_rebuilds_the_frozen_e8_b1_requests_and_replays_their_replies`

**1. The archived image and embedding exist and match their records.**
- Page 15's archived M1 image has SHA-256 `31c14c7d…27ebb70f7a`. It equals:
  - the git-frozen `experiments/frozen/e5/tables/render_manifest_heldout.csv`, itself checked against `experiments/frozen/e5/SHA256SUMS`;
  - the archive manifest entry. The manifest's own SHA-256 is `d3b11c16…`, as recorded. Both copies are byte-identical, and `sha256sum -c` passes on all files in the archive folder and in the project.
- The E5 embedding `pages/31c14c7d….safetensors` exists and holds 755 × 128 tokens. That equals the 755 tokens that `experiments/frozen/e5/tables/encoding_log.csv` records for this key.
- The combined digests are unchanged: `data/cache/e5` `dff4abffcfab9345` (1,013 files) and `data/cache/mmlongbench_doc` `36abcd316b292d57` (6,592 files). Every `experiments/frozen/*/SHA256SUMS` passes.

**2. The mismatch is confirmed and is the processor.**
- The renders were made with the same PDF (SHA-256 `773e1fc4…`, "pdf ok" in the rebuild test) and the same PyMuPDF 2.1 (MuPDF 1.28.6).
- The Linux x86-64 render of page 15 has SHA-256 `0860457a…`. It has the same 768 × 994 size and the same PNG length (137,391 bytes) as the M1 image.
- 38 of 763,392 pixels differ, all in row y = 211 (x 365–402), each by 18 levels at most: an anti-aliasing difference.
- The other 19 pages of this PDF, and all 20 of `efd88e41…`, render to their frozen hashes. This is one more instance of the §2.6 finding in `docs/ssp_cloud.md`.

**3. Fix: archived images may replace renders only through a reviewed list.**
- `import_e5_document` still renders every page and still uses the fresh render where E5 has an embedding for it. Only a page whose render has no E5 embedding may use E5's archived M1 image, and only if all of these hold:
  - the page is listed in the committed `resources/archived_page_images.json` (one entry: e639… page 15);
  - `visual_index.verified_archived_pages` checks:
    - the PDF's SHA-256;
    - the frozen render manifest, against its package's `SHA256SUMS`;
    - the manifest row's hash and path;
    - the archived PNG's bytes;
    - its pixel size, against the fresh render's.
- Any failed check raises `IndexKeyMismatch`. Unlisted pages fail as before.
- The store records each substituted page (archived hash, path, and the hash of the differing render) in its `encoder` metadata.
- Nothing is re-rendered into the store, nothing is re-encoded, and no embedding is regenerated. The five SHA-pinned B1 modules are untouched (`test_b1` passes), and no frozen file changed.
- **Why the E8 requests still match.** Page 15 of e639… is never in the top 4 that B1 reads for that document's 7 questions. So the reader request fingerprints are unaffected, and the app test reproduces all 14 frozen E8 requests and replies exactly.
- **Limit.** The index now holds the M1 embedding of page 15. A live encoding on the Datalab would encode the x86 render, and its embedding would almost surely differ slightly. Any new Datalab run is a new rendering condition, as already noted above.
- **New tests** (no existing test changed):
  - acceptance with full provenance;
  - refusal for a wrong PDF, a tampered image, a tampered manifest and a wrong size;
  - an unlisted page is not substituted;
  - the e639 import records its substitution.

**4. The six skips: missing inputs, not failures.**

| Skipped test | Missing input |
|---|---|
| `test_documents.py::test_page_text_equals_the_text_pinned_by_the_e3_spec[PG_2020…]` | `PG_2020.05.21_International-Cooperation-COVID_FINAL.pdf` |
| `test_documents.py::test_page_text_equals_the_text_pinned_by_the_e3_spec[germanwings…]` | `germanwingsdigitalcrisisanalysis-150403064828-conversion-gate01_95.pdf` |
| `test_documents.py::test_page_text_equals_the_text_pinned_by_the_e3_spec[bdf54dxa…]` | `bdf54dxa.pdf` |
| `test_documents.py::test_render_equals_the_frozen_e1_768_px_image` | germanwings PDF (mmlb-0729) |
| `test_answering.py::test_request_fingerprint_equals_the_frozen_e1_768_request` | germanwings PDF (mmlb-0729) |
| `test_visual_index.py::test_identity_checks_pass_on_the_real_small_files_and_processor` | ColQwen2 small files in `data/cache/hf/colqwen2-v1.0-hf@ddc07d2317c8/` (`preprocessor_config.json`, `tokenizer.json`, `tokenizer_config.json`) |

- **PDFs.** All 6 development PDFs are absent on the Datalab: `2210.02442v1`, `PG_2020…`, `bdf54dxa`, `earlybird…`, `germanwings…` and `watch_d`. The rebuild test downloaded only 124 PDFs. They are git-ignored, and notebook 00 downloads them at the pinned revision.
- **Expected after download.** These tests may then *fail* on x86-64 rather than pass:
  - germanwings and bdf54dxa are OCR pages, and OCR text differed for 24/330 pages in the rebuild test;
  - the two E1 tests check render hashes.
  Such a failure would be the same processor effect. It must be recorded, not silenced.
- **ColQwen2 small files.** Once they are present, the test will still fail: `.venv-cu126` has torch **2.14.0**+cu126, while E5 and `requirements/lock-2026-11-26.txt` pin **2.15.0**. `check_library_versions` would report "a new condition", correctly. `.venv` has neither torch nor pytest.
- Nothing was downloaded here.

**5. Result.**
- `pytest` in `.venv-cu126`: **206 passed, 6 skipped, 0 failed** (89 s). That is the 198 earlier passes, the 2 fixed tests and 6 new tests.
- No paid call, no regenerated embedding, no push.
- Committed locally as `4912a69`, not pushed.

**6. Missing inputs supplied (owner-approved, the same day).**
- **The 6 development PDFs** were downloaded at revision `2ff6aa92` into `data/external/mmlongbench_doc/documents/`. Each was checked against the Hub's record before being copied in: LFS SHA-256 and size, or git blob SHA-1 for `watch_d.pdf`. 6/6 match.
- **The ColQwen2 small files** (`vidore/colqwen2-v1.0-hf@ddc07d23`, everything except `model.safetensors`, 14 MB) are now in `data/cache/hf/colqwen2-v1.0-hf@ddc07d2317c8/`, which is git-ignored. The preprocessor and tokenizer hashes equal E5's (`be69973e…`, `091aa759…`).
- **Result: 210 passed, 0 skipped, 2 failed** (91 s). 4 of the 6 formerly skipped tests pass:
  - the PG_2020 native-text pin;
  - the germanwings OCR pin;
  - the E1 768-px render hashes;
  - the E1 request fingerprint.
- The two failures, as predicted:
  - `test_page_text_equals_the_text_pinned_by_the_e3_spec[bdf54dxa.pdf-11-True]`: **OCR differs by processor.**
    - The Mac's archived `pages.parquet` text equals the pin (`7fe28233…`). The Linux text is `ae5b334c…`.
    - Both runs used OCR and found 235 words, with 98.7 % character similarity. The only difference is one four-token span of OCR noise on a graphic: `gS &€ Ss ww` became `a S&S S&S ~—`.
    - The OCR engine is PyMuPDF's built-in Tesseract with `resources/tessdata`; there is no system binary.
    - This is the same effect as the 24/330 texts in the rebuild test. The pin stays as it is: on x86-64 this page is a new text condition.
  - `test_identity_checks_pass_on_the_real_small_files_and_processor`: "torch 2.14.0+cu126 / transformers 5.23.0 differ from E5's 2.15.0 / 5.23.0: a new condition". The check is correct, and the environment is what is wrong.

### 2026-11-26 — Final held-out evaluation: results (test pool used once)

| Claim (S-v1) | Result | Verdict |
|---|---|---|
| C1 B1 accuracy | 288/674 = **0.427** [0.386, 0.470] (development 0.451); core scope 0.372 | — |
| C2 B1 − T1 (confirmatory) | **+0.119** [+0.088, +0.150], p 1e-5, 103/23 | **`visual_retrieval_confirmed`** |
| C3 A1 − B1 (secondary) | +0.021 [+0.007, +0.036], p 0.0046, 19/5 | `a1_gain_supported` (report only) |

- **Retrieval.** Evidence recall@4 is 0.711 for ColQwen2 against 0.543 for BM25, replicating E5 out of sample.
- **Cost.** 2,079 calls plus a 6-call smoke on development questions, all first-attempt successes: $0.993449 of $2.50.
- **Deviation D2.** It was fixed after the run but before any number was computed. The frozen S-v1 copy crashed on non-numeric replies to `$`-formatted Float references; they now score 0, as in the official code. Two replies, both on one question, were affected.
- **Independent audit.**
  - It reproduced all 70 quantities.
  - C2 holds in every leave-one-document-out fold.
  - C3 is fragile: p = 0.049 under the worst-case S-v2 labelling.
  - Two low-severity findings are recorded: token-model rounding, and a pool reference quoted in D2's text, now in the ledger.
- **Decision.** B1 remains the shipped system. A1's gain is reported, not adopted. The pool is now used: it may be reported, never tuned on.
- **Open (owner, optional).** 85 blind S-v2 items, `experiments/frozen/final/adjudication/`. No labelling can reverse C2 or C3.
- **Move to the ENSAE-ENSAI Datalab.**
  - Done:
    - GitHub is complete.
    - The OpenAI key and a GitHub token are set up.
    - The embeddings are on MinIO, byte-verified.
  - Blocked: page images, PDFs and some tables. The storage gateway's content filter rejects them; see `docs/ssp_cloud.md`.
  - The owner chose not to contact the Datalab admins about the filter. The route is to rebuild the blocked files on the Datalab.
  - First service (`vscode-python-gpu`, started 2026-11-26): the Vault key is present and both VS Code extensions installed. Claude Code did not install, because the image has no npm. `tools/datalab_init.sh` now uses the official installer and `CLAUDE_CONFIG_DIR`.
  - Rebuild test on the Datalab (2026-11-26): **NOT IDENTICAL**.
    - PDFs: 124/124 identical (the 7 other Mac PDFs: 7/7 from the Mac).
    - Page images: 354/372. Page texts: 306/330.
    - The Mac reproduces the same pages: 36/36 images, 57/57 texts. So the cause is the processor (M1 ARM vs x86-64), not the files.
    - **Consequence:** the Mac's page images (1.69 GB) and 30 files in `data/processed` (4.0 MB) are irreplaceable bit for bit. Notebook 09's offline audit needs them. Details: `docs/ssp_cloud.md` §2.6.
  - Embeddings copied from MinIO to the Datalab disk and verified (2026-11-26). The combined SHA-256 over all files matches the Mac: `data/cache/final` 6,223 files `b12dec4646a211a4`; `data/cache/e5` 1,013 files `dff4abffcfab9345`. The Datalab also holds the 213 `data/processed` and 452 `experiments/runs` files from MinIO.
  - Uploads to MinIO work from inside a Datalab service; the filter blocks only uploads from outside.
  - Freed on the Mac, with the owner's approval (2026-11-26):
    - the ColQwen2 weights, re-downloadable at the pinned revision;
    - the 131 PDFs, each re-downloadable identically;
    - the embeddings, checked on MinIO and the Datalab;
    - `experiments/runs`, 460 files checked on MinIO or in git.
    Free space went from 3.0 GB to 9.2 GB.
  - Archive: the private Hugging Face dataset `srou/visualdoc-mac-archive` (`docs/ssp_cloud.md` §2.9).
    - It holds the page images (6,592 files) and `data/processed` (254 files), with a SHA-256 manifest.
    - 6,847/6,847 files are identical to the Mac.
    - 6,092/6,092 page images referenced by the frozen packages are archived with identical bytes.
  - Next:
    - Restored on the Datalab and backed up to MinIO from there (2026-11-26):
      - all 6,846 files pass `sha256sum -c`;
      - the combined digests match the Mac (`36abcd316b292d57`, `94b7096c3ad2a24b`);
      - MinIO has 6,846/6,846 files identical by MD5.
  - Deleted on the Mac with the owner's approval (2026-11-26): the page images, `data/processed`, the checksum list and `.venv`. The project folder is now 153 MB (code and git).
    - Before deleting, all 6,846 files matched the archive manifest: 6,413 read from disk; 433 had become iCloud placeholders and were not read.
    - iCloud resumed syncing `~/Documents` once space was freed, and evicted files to online-only placeholders. A git checkout there is fragile: keep code elsewhere or rely on GitHub.
  - Next: push the local commits; test a real pause/resume on the Datalab; set up the full environment there.
    - New Datalab experiments are a new rendering and OCR condition: run all arms there.

### 2026-11-26 — Final evaluation is ready to run; the move to SSP Cloud is prepared

- **Indexing.**
  - 5,554 pages of 110 documents embedded on the M1 GPU in about 14 h, at 9.5 s per page.
  - The parity gate reproduced E5 bit for bit, before and after.
  - Index frozen and committed before any question was read.
- **Deviation D1.** Pool PDFs must match the revision's recorded hash.
  - `mi_phone.pdf` is excluded: Hugging Face serves different bytes.
  - The first check wrongly flagged 20 git-stored PDFs, which have a blob SHA-1 rather than an LFS SHA-256. This was fixed before any question was read.
  - One LFS pointer has a wrong size but the right content hash. It is included after a verified direct fetch.
- **Questions.**
  - 872 encoded on the M1 GPU.
  - Development rankings 118/118 identical to E5's.
  - Development requests 118/118 identical to frozen E8.
  - U3 triggers on 38.4 % of questions.
  - The 2,079-call plan is frozen.
- **Ready to move to SSP Cloud.**
  - Notebook 09 is portable. On non-M1 machines it uses the frozen rankings and checks them within 1e-4; its encoding modes refuse non-M1 machines.
  - Dependencies are locked in `requirements/lock-2026-11-26.txt`.
  - Step-by-step guide: `docs/ssp_cloud.md`.
  - Remaining owner actions: authorise the GitHub push and configure `mc` for the MinIO upload.

### 2026-11-25 — Final evaluation: approval, environment and two engineering decisions

- **Owner decisions.**
  - Run B1, T1 and the secondary A1, under a $2.50 ceiling.
  - Index on the laptop. The re-downloadable caches `~/.cache/uv` (2.6 GB) and `~/.cache/puppeteer` (0.5 GB) were cleared with authorisation.
  - Amend AGENTS.md with the wording shown.
  - Authorise ≤ $0.01 for a live application check.
- **Weights from Hugging Face, outside iCloud.** The repository's copy of the ColQwen2 weights is an evicted iCloud placeholder. iCloud sync for this account is blocked ("Quota exceeded"), so it cannot be restored. The pinned revision `ddc07d23…` was downloaded into `~/.cache/huggingface` instead. Weights, preprocessor and tokenizer hashes equal E5's (`2f6dbf32…`, `be69973e…`, `091aa759…`).
- **Chunked two-pass encoding.** Pass-1 features take about 1.8 MB per page. Running pass 1 over all pool pages first would need about 9.5 GB of transient disk, so the passes alternate over 200-page chunks. The operations per page are unchanged, and the spec's parity gate requires bitwise equality with E5 before any pool page is encoded.
- **Evicted placeholders are re-downloaded.** Three pool PDFs fetched during E5's selection had become unreadable placeholders, and the first indexing launch stopped on one of them. The download cell now forces a fresh copy for such files; nothing else had run.
- **Live application check.** 3 calls, observed about $0.0013. They match frozen E8 L-B1 in fingerprints, billed tokens and answers.

### 2026-11-25 — E9 Stage 2 result: `no_meaningful_gain` (development data)

| | B1s | F8a | F8b | A1a | A1b |
|---|---:|---:|---:|---:|---:|
| S-v1 / 102 | 44 | 46 | 46 | 47 | 46 |

- **Primary contrast.**
  - A1 − B1s = +0.025, 95 % CI [0.000, +0.051], sign-flip p = 0.125.
  - Fixed / broken: 3 / 0 in replicate a, 2 / 0 in replicate b.
  - The +0.05 engineering criterion fails, which gives `no_meaningful_gain`.
- **Fixed-depth and attribution contrasts.**
  - F8 − B1s = +0.020 [−0.048, +0.079].
  - A1 − F8 = +0.005.
  - On triggered questions, 8 pages help (+0.061). On untriggered ones they slightly hurt (−0.008).
- **Session drift.** B1s scores 44 on byte-identical requests, against the frozen E8 L-B1's 46 (6 flips). The same-session control prevented a cross-day comparison that would have hidden most of the effect.
- **Decision.** B1 keeps k = 4 and a single read. Adaptive acquisition is not adopted, and the application does not implement it. A1 may be reported in the final evaluation only as a pre-registered *secondary* comparison (owner's choice), never to change the shipped system after seeing test results.

### 2026-11-25 — E9 Stage 0 result (pre-registered gate, development data)

- **Population.** 101 held-out questions with annotated evidence (14 documents). Base rate of "evidence not fully in ColQwen2's top 4": 39/101 = 0.386.
- **Selected trigger.** U3 flatness = −(s₁ − s₈)/s₁ of the ColQwen2 MaxSim scores:
  - AUROC 0.783, document-cluster 95 % CI [0.661, 0.861];
  - Holm-adjusted p < 0.001;
  - lift +0.239 [+0.095, +0.362] at a 40 % trigger rate (threshold −0.153079);
  - minimum leave-one-document-out AUROC 0.752;
  - 8 recoverable questions triggered.
- **The other four signals fail at least one gate condition.**
  - The 4–5 margin: AUROC 0.62.
  - The top-page stand-out: AUROC 0.62.
  - Reader abstention: AUROC 0.645, failing the leave-one-document-out condition.
  - Numeric support of the answer: AUROC 0.47. It is at chance, consistent with E8's finding that grounding is a poor repair trigger.
- **Not only a "hard document" effect.** Under a within-document permutation null (which keeps each document's base rate), U3's null mean is 0.604. The observed 0.783 still exceeds it (p = 0.001).
- **Correction recorded in the notebook.** On first execution, a validation cell wrongly asserted that the within-document null centres on 0.5. The cell now uses a global permutation as the null calibration and keeps the within-document one as a decomposition. The gate itself was never changed.
- **k = 8 headroom.**
  - 15/101 questions have missing evidence at ranks 5–8.
  - 8 become complete at k = 8.
  - 11 have no evidence in the top 8 at all.
  - The ceiling on any 8-page gain is therefore small. The pre-registration says a null result is likely and acceptable.

### 2026-11-25 — E9 design choices (frozen in the spec before Stage 0)

- **Same-session B1 control (B1s).** The reader is an alias without a snapshot, and E8 measured 7 flips between identical replicates. A same-session control separates "more pages" from "a different day". The B1s requests are byte-identical to frozen E8 L-B1; the notebook asserts this.
- **A1 derived from F8, with no extra call.** U3 is a pre-read trigger, so the adaptive policy's reply on a triggered question *is* the 8-page reply. A1 − F8 then measures exactly what the trigger saves.
- **The F8 arm is run twice.** Any gain must exceed the measured replicate churn.

### 2026-11-25 — Application constraints

- The five B1 modules (`documents`, `retrieval`, `answering`, `citations`, `pipeline`) are SHA-256-pinned by the frozen E8 spec. The application therefore grows by **new** modules only, which keeps E8 replayable.
- The owner's 2026-11-25 instruction ("build a functional, usable application") is taken as the explicit approval that AGENTS.md requires to extend beyond the five modules and to add a minimal UI.
- Notebook 08 imports nothing from `src/visualdoc`. It rebuilds the requests visibly and proves parity with the frozen E8 requests instead. This is AGENTS.md's import rule, applied.

## API spend

| Date | Experiment | Calls | Observed list-price USD | Ceiling |
|---|---|---:|---:|---:|
| ≤ 2026-11-25 | E3 | — | 0.91 (smoke + pilot + full, `experiments/README.md`) | 1.25 |
| ≤ 2026-11-25 | E4 | — | 1.2006 | 1.50 |
| ≤ 2026-11-25 | E6 | — | 3.7213 | 5.60 |
| ≤ 2026-11-25 | E7 | 1,320 | 5.911057 | 9.00 |
| ≤ 2026-11-25 | E8 smoke + full | 6 + 354 | 0.0015431 + 0.144765 | 0.10 + 0.50 |
| ≤ 2026-11-25 | E0–E2 | — | recorded in their frozen packages (not re-added here) | — |
| 2026-11-25 | E9 Stage 0 | 0 | 0.00 | — |
| 2026-11-25 | E9 smoke + Stage 2 | 6 + 354 | 0.004592 + 0.147055 = **0.151647** | 0.50 |
| 2026-11-25 | Application live check | 3 | ≈ 0.0013 observed (≤ 0.0024 charged at the upper bound) | 0.01 |
| 2026-11-26 | Final evaluation smoke + full | 6 + 2,079 | 0.003216 + 0.990233 = **0.993449** | 2.50 |
| 2026-11-27 | E10 smoke (26 calls + 1 failed locally) + full (899 calls) | 27 + 899 | 0.017513 (charged) + 0.455862 = **0.473375** | 3.50 |

E9's cumulative ceiling is **$0.50** (authorised by the owner on 2026-11-25). Planned upper bound: smoke $0.006847 + full $0.368866.

## Resources and environment risks

- **Disk: 6.1 GB free of 228 GB (97 %).** The repository lives in iCloud-synced `~/Documents`. 391 cached page images, 85 processed files, 12 source PDFs, 495 `.venv` files and 82 `.git` objects are evicted (`dataless`). They download again on read, which needs network access.
- **ColQwen2 weights** (4.4 GB) are dataless. Materialising them would leave about 1.7 GB free. Nothing in E9 needs them: E9 uses E5's frozen rankings.
- **RAM 8 GB, fanless M1.** E5 measured 12.5 s per page to index with ColQwen2. Indexing the about 111-document test pool locally would take most of a day *and* more disk than is free.

## Open dependencies and blockers

1. **Final-evaluation indexing time.** About 5,000 pages at about 12.5 s per page on the fanless M1, so the job runs for many hours under `caffeinate`. It is resumable: re-running `index` mode skips every page already encoded.
2. **No off-machine backup of today's work.** iCloud sync is blocked by the account's storage quota, and commits since `7da078f` are local only, because pushing needs the owner's authorisation.
3. **Datalab conditions (2026-11-26).**
   - `bdf54dxa.pdf` page 11 OCR text differs on x86-64. This is a processor condition, and the test stays as it is (the one `pytest` failure in `.venv`).
   - GPU encoding is possible only with torch 2.14.0+cu126, a new condition. The pinned torch 2.15.0 needs driver ≥ 580 for CUDA, and the service has 565.
   - The local commits are not pushed yet.
4. **S-v2 blind labels.** E10's 17 items were labelled on 2026-11-27 (`experiments/frozen/e10_scoring_v2/`). 13 E9 items in `data/processed/mmlongbench_doc/e9/adjudication_queue.csv` (frozen empty copy in `experiments/frozen/e9/adjudication/`). They do not affect the S-v1 verdict, and the S-v2 interval cannot change it.

## Known limitations (running list)

- All E1–E9 evidence is development data: 14–20 documents that have shaped every design decision.
- Evidence annotations come from a single annotator. A page that answers but is not annotated counts as missing.
- The reader alias `gpt-6-luna` cannot be pinned. Frozen replies, not the model name, define every result.
