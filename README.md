# VisualDoc AI — cited question answering over PDF documents

VisualDoc answers a question about one PDF. It returns the answer, the pages it cites and a short verbatim quote from each cited page, or `Not answerable`. It reads **page images** rather than extracted text, and it finds the pages to read with a **visual page retriever** (ColQwen2).

The repository is also a research record. Eleven pre-registered experiments (E0–E10) on the public benchmark [MMLongBench-Doc](https://huggingface.co/datasets/yubo2333/MMLongBench-Doc) decided each component on 20 development documents. A single pre-registered **final held-out evaluation** then measured the frozen system once on 110 documents never used in development. Every paid run is frozen with its requests, replies, an independent audit and checksums, so every reported number is re-derived without an API call.

> **Status (2026-11-26).**
> - **Validated baseline B1: frozen** (`docs/validated_baseline_b1.md`).
> - **Final held-out evaluation: done, audited and frozen** (commit `c6c450d`, `experiments/frozen/final/`). B1 answers 42.7 % of held-out answerable questions, and the project's central result, visual retrieval beating OCR + BM25, is **confirmed out of sample**. The test pool is now used: it may be reported, never used to tune a system.
> - **E9 (adaptive evidence acquisition): done** on development data, verdict `no_meaningful_gain`; B1 is unchanged.
> - **E10 (agentic reader): done** on development data (2026-11-27). The agent searches with its own queries: +8 questions net in both replicates (45 → 53 of 102), evidence recall of the pages seen 0.726 → 0.866. The frozen verdict is `regression` by the broken-ratio rule (AGb: 17 fixed, 9 broken). B1 is unchanged (`experiments/frozen/e10/`).
> - **Application** (CLI and local web page around B1): built, and revised after an independent review (`docs/application.md`).

---

## What B1 does

```
PDF ──► page images, 768 px short side
          │
          ▼
    ColQwen2 v1.0 ── MaxSim over every page ──► ranked pages
          │          (BM25 over native text + OCR is computed and logged beside it;
          │           it becomes the retriever only when the visual index cannot run)
          ▼
    top k = 4 pages ──► one gpt-6-luna call, temperature 0, reasoning_effort none
                        strict JSON schema: {answer, cited_pages, evidence[{page, quote}]}
          │
          ▼
    citation check + grounding check ──► answer, cited pages, quotes, or "Not answerable"
```

| Component | Choice | Decided by |
|---|---|---|
| Page rendering | 768 px short side, image only (no OCR text in the prompt) | E1, E3 |
| Retrieval | ColQwen2 v1.0, MaxSim late interaction over page images; BM25 as fallback | E5, E6, notebook 07; confirmed held out |
| Reading | one call over the retrieved pages | E7 |
| Reader | `gpt-6-luna`, temperature 0, strict JSON schema, 800 output tokens | E8 |
| Output contract | answer + cited pages + evidence quotes + explicit abstention | E8 |
| Pages read | k = 4, one read (no adaptive deepening) | E9 |

Source: `docs/validated_baseline_b1.md` §1, `experiments/frozen/e9/README.md`. The system design is in [`docs/architecture.md`](docs/architecture.md).

---

## Held-out result: the final evaluation (test pool, used once)

Protocol frozen in `experiments/specs/final_evaluation_v1.json` (commit `1c54a3e`) and approved by the owner before any pool document was downloaded. The ColQwen2 index of the pool was frozen before any question was read (`experiments/frozen/final_index/`, commit `ab8a9c8`). One reader session, one run per arm, the same reader and contract in every arm; only the pages differ.

**Population.** 110 MMLongBench-Doc documents outside the 20 development documents, minus 4 whose questions had been seen earlier and `mi_phone.pdf` (deviation D1: its served bytes differ from the pinned revision). All 872 of their questions: 674 answerable, 198 unanswerable, no question-level filter.

| Claim (S-v1, primary) | Result | Verdict |
|---|---|---|
| **C1** B1 accuracy, answerable | **288 / 674 = 0.427**, document-cluster 95 % CI [0.386, 0.470]; development estimate 0.451 (46/102) | estimate |
| C1, core scope (born-digital financial, research and administration documents, 32 documents) | 77 / 207 = 0.372 [0.305, 0.443] | estimate |
| **C2** B1 − T1: ColQwen2 top 4 vs OCR + BM25 top 4 (confirmatory) | **+0.119** [+0.088, +0.150]; sign-flip p = 1.0e-05; 103 fixed / 23 broken | **`visual_retrieval_confirmed`** |
| **C3** A1 − B1: E9's adaptive policy (secondary) | +0.021 [+0.007, +0.036]; p = 0.0046; 19 fixed / 5 broken | `a1_gain_supported`, reported only; the shipped system stays B1 |

| | B1 | T1 | A1 |
|---|---:|---:|---:|
| S-v1 correct / 674 answerable | 288 | 208 | 302 |
| Correct abstentions / 198 unanswerable | 120 | 140 | 121 |
| Citation validity | 1.000 | 0.995 | 0.999 |

- **Evidence retrieval at k = 4** (666 answerable questions with annotated evidence): ColQwen2 recall 0.711 vs BM25 0.543, +0.168 [+0.130, +0.207]; complete evidence 0.626 vs 0.459. Development (E5): 0.721 vs 0.526.
- **Robustness (independent audit).** It reproduced 70 quantities to within 3.7e-11. C2 is `visual_retrieval_confirmed` in all 110 leave-one-document-out folds (Δ from +0.1136 to +0.1239) and with documents weighted equally (+0.1246).
- **C3 is fragile.** It rests on 24 disagreements and one run per arm, stays below E9's +0.05 materiality, and its sign-flip p rises to 0.049 under the worst-case S-v2 labelling.
- **S-v2 (secondary).** 85 arm-blind gray items await the owner's labels. Over every consistent labelling, B1 − T1 stays within [+0.077, +0.150] and A1 − B1 within [+0.015, +0.028]; no labelling reverses either sign.
- **Cost.** 2,079 calls plus a 6-call smoke on development questions, all first-attempt successes on one served model: $0.993449 of a $2.50 ceiling.

Sources: `experiments/frozen/final/README.md`, `tables/evaluation_summary.json`, `AUDIT.json`. Full account: [`docs/research_report.md`](docs/research_report.md) §9.

---

## Development results (E0–E9)

All numbers are from frozen, audited packages in `experiments/frozen/`, on the 20 development documents. "Correct" uses the frozen scorer S-v1 (correct = score > 0), a local re-implementation of the benchmark's rule-based scorer: **these are not leaderboard numbers**.

| Exp. | Question | Population | Result | Verdict |
|---|---|---|---|---|
| E0 | Text vs page images, on retrieved vs annotated pages (GPT-4o-mini) | 6 docs, 57 q (40 answerable) | A text 7/40, B images 7/40, C text-oracle 9/40, D image-oracle 11/38; BM25 Recall@5 0.689, Hit@5 0.800 | exploratory: images not better on retrieved pages |
| E1 | 512 vs 768 px page images | 37 q | 10/37 → 16/37; 6 fixed, 0 broken | `adopt_768` |
| E2 | Qwen3-VL-8B vs GPT-4o-mini at 768 px | 37 q | 15/37 vs 16/37; 4 fixed, 5 broken | retain GPT-4o-mini |
| E3 | Text only vs images only vs both | 37 q | T 13, I 17, IT 16 of 37 | retain images only |
| E4 | The application end to end (BM25 → images → GPT-4o-mini) | 57 q | APP 11/40 answerable; ORACLE pages 17/37 | `page_selection_costs_accuracy` |
| E5 | ColQwen2 vs OCR + BM25: evidence reaching the reader | 14 new docs, 101 q | evidence recall 0.526 → 0.721, +0.195 [+0.110, +0.309] | `visual_improves_evidence` |
| E6 | Same, measured on answers | 118 q (102 answerable) | 25/102 → 38/102, +0.127 [0.074, 0.193], 13 fixed, 0 broken | `adopt_visual_retrieval` |
| E7 | Extract-then-answer vs one-shot reading | same 118 q | V0 38, X4 31, X8 29 of 102; X4 − V0 −0.069 [−0.135, −0.008] | `regression` |
| E8 | Reader migration to `gpt-6-luna` and the B1 contract | same 118 q | L-v1 42/102, L-B1 46/102, repeat 46/102; B1 − v1 +0.039 [−0.019, +0.098] | promote B1 (non-inferiority only) |
| E9 | Read pages 5–8 only when retrieval looks uncertain | same 118 q | B1s 44, F8 46/46, A1 47/46 of 102; A1 − B1s +0.025 [0.000, +0.051], sign-flip p = 0.125 (the smallest attainable here) | `no_meaningful_gain` |
| E10 | An agent that writes its own search queries and chooses pages (≤ 6 calls, ≤ 12 pages), warm-started with B1's top 4 | same 118 q | B1s 45, AGa 53, AGb 53 of 102; AG − B1s +0.078 [0.000, +0.181], sign-flip p = 0.053; 13/5 and 17/9 fixed/broken. Evidence recall of pages seen 0.726 → 0.866; on the 39 questions with evidence missing from the top 4, +0.256 [+0.136, +0.500]; all broken questions had complete evidence in the top 4. $0.0017 per question | `regression` (broken > fixed / 2 in AGb) |

Intervals are document-cluster bootstrap 95 % intervals. Sources: `AGENTS.md` (regression references), the `README.md` of each package in `experiments/frozen/`, and `experiments/frozen/e9/tables/evaluation_summary.json`.

### What the evidence supports, and how strongly

- **One strong result, now confirmed out of sample: visual retrieval beats OCR + BM25.** On development data it held for evidence (E5) and for answers (E6: 13 fixed, 0 broken, exact document sign-flip p = 2⁻¹⁰ ≈ 0.00098; S-v2 28/101 → 39/101). On 110 held-out documents the answer-level gain is +0.119 against +0.127 in development, and the evidence-level gain +0.168 against +0.195.
- **Negative results, reported as such.**
  - E2: a stronger open VLM did not beat GPT-4o-mini (a tie within noise).
  - E3: adding the extracted text to the images did not help.
  - E7: reading each page separately, then answering from the extracted facts, was **worse** (the interval excludes zero).
  - E10: the agent's search works (evidence recall +0.140, gain concentrated where B1 lacks evidence). But it also breaks questions B1 answers, by over-exploring or reading the same pages differently. The frozen broken-ratio rule therefore labels it `regression`, despite +8 questions net in both replicates.
  - E9: the adaptive policy was directionally positive on development data (5 fixed, 0 broken across two replicates) but missed the pre-registered +0.05 criterion. On held-out data it shows a small, statistically supported but fragile gain (+0.021); B1 stays the shipped system.
- **Non-inferiority only: the B1 contract.** 46 vs 42 of 102 (S-v1), 47 vs 44 of 101 (S-v2), with an interval that straddles zero. Two identical B1 replicates flip 4 questions (S-v1), 7 under S-v2. **B1 is not a demonstrated accuracy improvement over the previous contract.** What it does buy, measured: citation validity 1.000, 9/16 correct abstentions (8/16 before), 118/118 schema-valid replies (`docs/validated_baseline_b1.md` §2).
- **The ceiling.** More than half of held-out answerable questions remain wrong. Accuracy falls with the number of evidence pages: 54 % for single-page evidence, 13 % for 4+ pages (`experiments/frozen/final/README.md`). The strict grounding diagnostic passes 70 of 118 development replies, and E8's data show it is a poor signal of correctness (`docs/e9_proposal.md` §1).

---

## Try it (offline, no cost)

Use the project environment (`.venv`, Python 3.12). `PYTHONPATH=src` avoids a macOS import problem described in [`docs/reproducibility.md`](docs/reproducibility.md).

```bash
# Ask one question about a local PDF (BM25 fallback until the PDF has a visual index)
PYTHONPATH=src .venv/bin/python -m visualdoc.app ask data/documents/ch2.pdf "What does Cromwell's rule say about prior probability?"

# The same, as JSON
PYTHONPATH=src .venv/bin/python -m visualdoc.app ask data/documents/ch2.pdf "What does Cromwell's rule say about prior probability?" --json

# Build a visual index for a development document from notebook 04's cached E5 embeddings (no model needed)
PYTHONPATH=src .venv/bin/python -m visualdoc.app index data/external/mmlongbench_doc/documents/watch_d.pdf --from-e5-cache

# Start the local web page, then open http://127.0.0.1:8765
PYTHONPATH=src .venv/bin/python -m visualdoc.app serve
```

**What the offline answer means.** Offline, no model is called. `OfflineB1Reader` returns a **placeholder**: it cites the first supplied page and quotes that page's first words, so that the citation and grounding checks run on a reply of the right shape. The CLI, the JSON (`"offline_placeholder": true`) and the web page all label it **OFFLINE PLACEHOLDER**. It is never an answer. What runs as in B1 offline: retrieval and page selection, and the request that would be sent, with its fingerprint, token bound and cost bound. The citation and grounding checks also run, but on the placeholder reply, so their verdicts mean nothing; the web page greys them out.

**Visual retrieval offline** needs a page index for the PDF *and* a cached embedding of the exact question. The E5 cache holds both only for the 20 development documents and their 175 benchmark questions. For any other question the app falls back to BM25 and says why. The development PDFs are downloaded by notebooks 00 and 04 (they are not in git).

**Live mode is paid and opt-in.** `--live` sends page images to the OpenAI API and needs `OPENAI_API_KEY` exported in the shell (the app never reads `.env`). It is guarded by a per-request ceiling (default $0.01) and a session ceiling (default $0.10), both checked before any call. One 4-page B1 question has an upper bound of about $0.0008 at list price. `gpt-6-luna` is an alias without a dated snapshot, so the served model is recorded on every call. Run it only with the owner's approval.

Usage details, the visual index and the web page's safeguards: [`docs/application.md`](docs/application.md).

---

## Reproduce the research

Short version (full guide: [`docs/reproducibility.md`](docs/reproducibility.md)):

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt          # the package, notebook dependencies and pytest
python -m ipykernel install --user --name visualdoc-venv --display-name "VisualDoc (.venv, Python 3.12)"

# Verify a frozen package (repeat for each folder in experiments/frozen/)
cd experiments/frozen/final && shasum -a 256 -c SHA256SUMS && cd -

pytest                                   # application modules, frozen protocols, parity with frozen runs
```

Then run the notebooks in order, on the `visualdoc-venv` kernel. **No notebook makes a paid call by default**: `VISUALDOC_QA_MODE` defaults to `replay`, every `VISUALDOC_E*_MODE` to `offline` and `VISUALDOC_FINAL_MODE` to `offline`. In those modes each notebook rebuilds its requests, asserts that they equal the frozen ones, re-scores the frozen replies and asserts the regression references in `AGENTS.md`. Paid modes run only with the owner's explicit approval.

| Notebook | Stage | Main outputs (git-ignored, regenerable) |
|---|---|---|
| [`00_document_processing`](notebooks/00_document_processing.ipynb) | E0: pinned questions, seeded 6-document subset, native text + OCR fallback, page rendering (512 px and 768 px) | `data/processed/mmlongbench_doc/{questions,pages}.parquet`, page PNGs in `data/cache/` |
| [`01_retrieval`](notebooks/01_retrieval.ipynb) | E0: BM25 by hand and per document, Recall@k / Hit@k, OCR ablation | `rankings.parquet`, retrieval tables |
| [`02_question_answering`](notebooks/02_question_answering.ipynb) | E0 conditions A–D; E1–E4 requests and executors | predictions, request plans |
| [`03_evaluation`](notebooks/03_evaluation.ipynb) | E0–E4 scoring (S-v1, cell `f653d232`), paired comparisons, error analysis | evaluation summaries, figures |
| [`04_visual_retrieval`](notebooks/04_visual_retrieval.ipynb) | E5: ColQwen2 vs OCR + BM25 on 14 new documents (no API) | held-out pages, embeddings in `data/cache/e5/` |
| [`05_visual_retrieval_answering`](notebooks/05_visual_retrieval_answering.ipynb) | E6: ColQwen2 pages vs BM25 pages, end to end | E6 evaluation tables |
| [`06_extract_then_answer`](notebooks/06_extract_then_answer.ipynb) | E7: extract-then-answer vs one-shot | E7 evaluation tables |
| [`07_baseline_consolidation`](notebooks/07_baseline_consolidation.ipynb) | B1: retrieval complementarity, scoring protocol S-v2, E8 reader migration | `data/processed/mmlongbench_doc/b1/` |
| [`08_adaptive_evidence`](notebooks/08_adaptive_evidence.ipynb) | E9: trigger selection (Stage 0) and adaptive arms (Stage 2) | `data/processed/mmlongbench_doc/e9/` |
| [`09_final_evaluation`](notebooks/09_final_evaluation.ipynb) | Final held-out evaluation: pool indexing, questions and retrieval, reader run, frozen claims C1–C3 | `data/processed/mmlongbench_doc/final/`, embeddings in `data/cache/final/` |

Notebooks communicate only through saved files. Each states its inputs and outputs at the top and stops with a clear message when an input is missing. ColQwen2 *encoding* (notebook 04, and notebook 09's `index` and `queries` modes) requires the Apple M1 GPU, where E5 encoded, because the specs require bit-for-bit equality with it; everything else runs on any machine from the saved embeddings and frozen rankings (`docs/ssp_cloud.md`).

**What cannot be reproduced without paying:** whether the models would give the same replies today. At temperature 0 the same requests already differ between sessions (E9: 6 flips on byte-identical B1 requests sent on the same day). `gpt-6-luna` has no dated snapshot, and `gpt-4o-mini-2024-07-18` shuts down on 2027-01-14. The frozen replies, not the model names, define every result.

---

## How results are produced

- **Pre-registration.** From E1 on, each experiment has a JSON specification in `experiments/specs/`, committed before the first paid call. It fixes the population, arms, request construction, seeds, decision rule and budget ceiling. Paid modes refuse to run if the specification or the notebook code differs from the committed version. Deviations are written down and committed before any result they could affect (`experiments/specs/final_evaluation_v1_deviations.md`).
- **Controlled comparisons.** Arms differ in one factor; requests of a question are sent in a seeded order; repeat arms or a same-session control measure run-to-run change.
- **Scoring.** S-v1 (notebook 03 cell `f653d232`, correct = score > 0) is frozen and decides every verdict. S-v2 adds the owner's blind labels for ambiguous replies and is reported beside it; no model judgment replaces a human label.
- **Statistics.** The question is the unit, clustered by document: document-cluster bootstrap intervals (10,000 draws) and document sign-flip tests (exact for 14 documents, Monte Carlo for 110). McNemar and leave-one-document-out are descriptive. One primary contrast per experiment. Non-inferiority is not claimed on about 100 questions.
- **Freezing.** After a run, its directory is copied byte for byte into `experiments/frozen/<exp>/` with evaluation tables, an independent audit, provenance and `SHA256SUMS`. Frozen files are never edited.
- **One held-out test.** The test pool stayed untouched until the final evaluation, and everything seen about it is recorded in `experiments/test_pool_ledger.md`. It has now been used once.

Details: [`docs/research_report.md`](docs/research_report.md) §4.

## Open items

From `docs/PROGRESS.md` and the frozen packages:

1. **S-v2 labels (optional, owner).** 85 arm-blind items for the final evaluation (`experiments/frozen/final/adjudication/`) and 13 for E9. No labelling can reverse C2, C3 or E9's verdict.
2. **Environment.** The work is moving to an Onyxia datalab (ENSAE-ENSAI Datalab or SSP Cloud); the step-by-step guide is [`docs/ssp_cloud.md`](docs/ssp_cloud.md). Encoding stays on the M1.
3. **Future work** must use new data: the test pool may be reported but never used to tune a system, so A1's held-out gain is a reason for a new experiment, not for changing B1.

---

## Repository layout

```text
.
├── notebooks/                 # 00–09: the research record, one stage per notebook
├── src/visualdoc/             # the application
│   ├── documents.py           #   PDF validation, SHA-256, text (native + OCR), 768-px rendering      ┐
│   ├── retrieval.py           #   BM25, MaxSim, cached visual index                                     │ five modules,
│   ├── answering.py           #   reader profiles, contract b1, request builder, token/cost guard, parser │ SHA-256-pinned by
│   ├── citations.py           #   citation check, quote and numeric grounding                           │ the frozen E8 spec
│   ├── pipeline.py            #   answer_question_b1 (retrieve, read, verify), Budget, caches, run log  ┘
│   ├── visual_index.py        #   ColQwen2 embedding store, E5 importer, live encoder
│   ├── app.py                 #   B1App service and CLI (ask, index, serve)
│   ├── web.py                 #   local web page (stdlib http.server)
│   └── parsing.py             #   older page-routing baseline, kept for reference, unused
├── tests/                     # pytest: modules, parity with frozen runs, frozen-package integrity
├── experiments/
│   ├── specs/                 # pre-registered specifications: E1–E9 and the final evaluation (+ plan, deviations)
│   ├── frozen/                # committed runs, tables, audits, provenance and SHA256SUMS (e1…e9, final_index, final_retrieval, final)
│   ├── runs/                  # git-ignored outputs of new live runs
│   ├── README.md              # what each frozen folder holds
│   └── test_pool_ledger.md    # everything seen about the test pool, before and during the final evaluation
├── docs/                      # reports, specifications and the progress log (see below)
├── data/
│   ├── external/              # MMLongBench-Doc question table (tracked); PDFs downloaded on demand
│   ├── processed/, cache/     # git-ignored notebook and application outputs
│   ├── annotations/           # schema for the project's own question set (empty)
│   └── documents/             # three local sample PDFs, used by the tests and the demo
├── resources/                 # Tesseract English model; benchmark document list
├── requirements/              # course-lab requirements; dependency lock of 2026-11-26
├── archive/                   # superseded notebooks, course labs, old docs (read-only)
├── AGENTS.md                  # development policy: notebook-first, frozen files, paid-call gates
└── pyproject.toml, requirements.txt
```

## Documentation map

| Document | Content |
|---|---|
| [`docs/research_report.md`](docs/research_report.md) | Research report: E0–E9, the final held-out evaluation, negative results, statistics, threats to validity |
| [`docs/architecture.md`](docs/architecture.md) | System architecture: the B1 pipeline, the application layer, caches, budgets, the notebook workflow, how experiments map to code |
| [`docs/reproducibility.md`](docs/reproducibility.md) | Environment, data, notebook order and modes, verifying frozen packages, what needs paid calls, resources, test-pool rules |
| [`docs/application.md`](docs/application.md) | Application usage: CLI, web page, visual index, live mode, tests |
| [`docs/validated_baseline_b1.md`](docs/validated_baseline_b1.md) | What B1 is, what the evidence supports, its held-out confirmation, what it does not claim |
| [`docs/final_evaluation_specification.md`](docs/final_evaluation_specification.md) | The historical draft of the final evaluation; the executed protocol is `experiments/specs/final_evaluation_v1.json` |
| [`docs/ssp_cloud.md`](docs/ssp_cloud.md) | Moving the project to an Onyxia datalab: storage, secrets, what must stay on the M1 |
| [`docs/PROGRESS.md`](docs/PROGRESS.md) | Progress log: decisions, spend, resources, open items |
| `docs/baseline_b1_specification.md`, `docs/baseline_consolidation_assessment.md`, `docs/e9_proposal.md`, `docs/e2_proposal.md` | Design records written before the corresponding experiments |
| [`experiments/README.md`](experiments/README.md) | The frozen packages and how results are reproduced |

---

## API spend (list price)

| Experiment | Spend | Source |
|---|---:|---|
| E0–E7 | about $13 in all | `docs/baseline_consolidation_assessment.md` §1.1 |
| of which E1 (3 runs) / E2 (4 runs) / E3 (3 runs) | about $0.59 / $0.0436 / $0.91 | `experiments/frozen/e1/README.md`, `e2/README.md`, `e3/README.md` |
| of which E4 / E6 / E7 | $1.2006 / $3.7213 / $5.911057 | `AGENTS.md` |
| E5, E9 Stage 0 | $0 (no API call) | `experiments/frozen/e5/README.md`, `docs/PROGRESS.md` |
| E8 smoke + full | $0.0015431 + $0.144765 | `AGENTS.md` |
| E9 smoke + Stage 2 | $0.151647 | `experiments/frozen/e9/README.md` |
| Final evaluation, smoke + run | $0.003216 + $0.990233 = $0.993449 | `experiments/frozen/final/README.md` |

The reader change explains the drop: E6's GPT-4o-mini requests cost $1.827 per arm of 118 questions, while the final evaluation's 2,079 `gpt-6-luna` calls on 872 questions cost $0.990233.

---

## Data, licences and the test pool

- **MMLongBench-Doc** (revision `2ff6aa92…`) is licensed CC BY-NC 4.0, research use only. Its question table is tracked; its PDFs are downloaded on demand into a git-ignored folder (`data/external/README.md`).
- **The test pool** is every benchmark document outside the 20 used in development. It stayed untouched until the approved final evaluation, which used it once (110 documents). **It is now used: it may be reported, never used to tune a system** (`experiments/frozen/final/README.md`). `experiments/test_pool_ledger.md` records everything seen about it. The application still refuses all 115 pool document names; the check is mainly by name (`docs/application.md` §4).
- **ColQwen2** weights (`vidore/colqwen2-v1.0-hf`, revision `ddc07d23`, 4.4 GB) are downloaded from Hugging Face and are not in git.
- Third-party material and local sample PDFs: [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md). Do not commit private or rights-restricted documents.

## Limitations

- **One held-out evaluation, one run per arm.** E8 measured 4–7 flips between identical replicates on 102 questions; C2's 80 net questions are far above that, C3's 14 are closer to it.
- **Design data are small and reused.** E0–E9 used 20 documents (175 questions); E6–E9 reused the same 118 questions.
- **Single-annotator evidence.** A page that answers but is not annotated counts as missing.
- **Local scoring.** S-v1 re-implements the benchmark's rule-based scorer without its GPT-4o extraction step; S-v2 adds blind human labels for ambiguous replies (85 held-out items still unlabelled).
- **An unpinnable reader.** `gpt-6-luna` returns no system fingerprint; frozen replies define every result.
- **A thin core scope.** The product's core document types account for 32 of the 110 held-out documents.
- **Visual indexing is slow on the development laptop**: the 5,554 pool pages took about 14 h on the M1 GPU, about 9.5 s per page (`docs/PROGRESS.md`). Without an index the app falls back to BM25.
