# Project progress log

The single place that records what is done, what is running, what each decision rests on, what has been spent, and what is still open. Newest entries first within each section. Dates are UTC+1.

## Status at a glance

| Milestone | State | Evidence |
|---|---|---|
| E0–E8 and validated baseline B1 | **done, frozen** | `docs/validated_baseline_b1.md`, `experiments/frozen/*` |
| E9 pre-registration | **done** | `experiments/specs/e9_adaptive_evidence_v1.json`, commit `7f41eea` (before any analysis) |
| E9 Stage 0 (offline trigger selection, $0) | **passed** the frozen gate; independent audit running | notebook 08 §Stage 0, `data/processed/mmlongbench_doc/e9/stage0_summary.json` |
| E9 Stage 1 smoke (6 calls) | ready, gated on the audit and on committing the technical addendum | notebook 08 §Stages 1–2 |
| E9 Stage 2 (354 calls) | ready after the smoke | same |
| Application (B1 with live ColQwen2, cache, CLI, UI) | in progress (engineering agent) | new modules in `src/visualdoc/`, new tests |
| Final held-out evaluation | not started; needs a frozen spec, owner approval, a budget and indexing compute | `experiments/test_pool_ledger.md` |
| Documentation (README, architecture, report, reproducibility, demo) | not started | — |

## Decisions and their reasons

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

E9's cumulative ceiling is **$0.50** (authorised by the owner on 2026-11-25). Planned upper bound: smoke $0.006847 + full $0.368866.

## Resources and environment risks

- **Disk: 6.1 GB free of 228 GB (97 %).** The repository lives in iCloud-synced `~/Documents`. 391 cached page images, 85 processed files, 12 source PDFs, 495 `.venv` files and 82 `.git` objects are evicted (`dataless`). They download again on read, which needs network access.
- **ColQwen2 weights** (4.4 GB) are dataless. Materialising them would leave about 1.7 GB free. Nothing in E9 needs them: E9 uses E5's frozen rankings.
- **RAM 8 GB, fanless M1.** E5 measured 12.5 s per page to index with ColQwen2. Indexing the about 111-document test pool locally would take most of a day *and* more disk than is free.

## Open dependencies and blockers

1. **Final evaluation compute.** The ColQwen2 index of the test pool needs about 10 GB of free disk and many CPU hours, or the SSP Cloud GPU. This is an owner decision (see below).
2. **Final evaluation budget.** No budget is authorised beyond E9's $0.50. The final evaluation needs the owner's authorisation.
3. **S-v2 blind labels.** E9's new gray replies need the owner's blind labels, as in E8. S-v1 decides the verdict meanwhile.

## Known limitations (running list)

- All E1–E9 evidence is development data: 14–20 documents that have shaped every design decision.
- Evidence annotations come from a single annotator. A page that answers but is not annotated counts as missing.
- The reader alias `gpt-6-luna` cannot be pinned. Frozen replies, not the model name, define every result.
