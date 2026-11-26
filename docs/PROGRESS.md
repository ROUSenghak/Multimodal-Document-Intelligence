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
| Application (B1 with live ColQwen2, cache, CLI, UI) | **built, reviewed, verified live.** 200 tests pass. Three live calls reproduced frozen E8 L-B1 requests, tokens and answers exactly. The live *encoder* is checked by notebook 09's parity gate | `src/visualdoc/{visual_index,app,web}.py`, commit `041827f` |
| Final held-out evaluation | **done, audited, frozen** (`c6c450d`). C1 B1 0.427; C2 `visual_retrieval_confirmed` (+0.119); C3 `a1_gain_supported` (+0.021, secondary). $0.993 | `experiments/frozen/final/` |
| Documentation (README, architecture, report, reproducibility, demo) | written; final-evaluation results are still to be added | `README.md`, `docs/{research_report,architecture,reproducibility}.md` |

## Decisions and their reasons

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
  - Next:
    - **Owner:** choose an archive for those files.
    - Then free the rest of the Mac: PDFs, embeddings (on MinIO), `.venv`, the ColQwen2 weights.
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

E9's cumulative ceiling is **$0.50** (authorised by the owner on 2026-11-25). Planned upper bound: smoke $0.006847 + full $0.368866.

## Resources and environment risks

- **Disk: 6.1 GB free of 228 GB (97 %).** The repository lives in iCloud-synced `~/Documents`. 391 cached page images, 85 processed files, 12 source PDFs, 495 `.venv` files and 82 `.git` objects are evicted (`dataless`). They download again on read, which needs network access.
- **ColQwen2 weights** (4.4 GB) are dataless. Materialising them would leave about 1.7 GB free. Nothing in E9 needs them: E9 uses E5's frozen rankings.
- **RAM 8 GB, fanless M1.** E5 measured 12.5 s per page to index with ColQwen2. Indexing the about 111-document test pool locally would take most of a day *and* more disk than is free.

## Open dependencies and blockers

1. **Final-evaluation indexing time.** About 5,000 pages at about 12.5 s per page on the fanless M1, so the job runs for many hours under `caffeinate`. It is resumable: re-running `index` mode skips every page already encoded.
2. **No off-machine backup of today's work.** iCloud sync is blocked by the account's storage quota, and commits since `7da078f` are local only, because pushing needs the owner's authorisation.
3. **S-v2 blind labels.** 13 E9 items in `data/processed/mmlongbench_doc/e9/adjudication_queue.csv` (frozen empty copy in `experiments/frozen/e9/adjudication/`). They do not affect the S-v1 verdict, and the S-v2 interval cannot change it.

## Known limitations (running list)

- All E1–E9 evidence is development data: 14–20 documents that have shaped every design decision.
- Evidence annotations come from a single annotator. A page that answers but is not annotated counts as missing.
- The reader alias `gpt-6-luna` cannot be pinned. Frozen replies, not the model name, define every result.
