# VisualDoc AI — cited question answering over PDF documents

VisualDoc answers a question about one PDF. It returns the answer, the pages it cites and a short verbatim quote from each cited page, or `Not answerable`. It reads **page images** rather than extracted text, and it finds the pages to read with a **visual page retriever** (ColQwen2).

The repository is also a research record. Ten pre-registered experiments (E0–E9) on the public benchmark [MMLongBench-Doc](https://huggingface.co/datasets/yubo2333/MMLongBench-Doc) decided each component. Every paid run is frozen with its requests, replies, an independent audit and checksums, so every reported number is re-derived without an API call.

> **Status (2026-11-25).**
> - **Validated baseline B1: frozen** (`docs/validated_baseline_b1.md`).
> - **E9 (adaptive evidence acquisition): done**, verdict `no_meaningful_gain`; B1 is unchanged (`experiments/frozen/e9/`).
> - **Application** (CLI and local web page around B1): built, and revised after an independent review (`docs/application.md`).
> - **Every result below is development data**: 20 documents that shaped the design. The **final held-out evaluation has not been run**. Its specification is a draft awaiting the owner's approval (`docs/final_evaluation_specification.md`).

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
| Retrieval | ColQwen2 v1.0, MaxSim late interaction over page images; BM25 as fallback | E5, E6, notebook 07 |
| Reading | one call over the retrieved pages | E7 |
| Reader | `gpt-6-luna`, temperature 0, strict JSON schema, 800 output tokens | E8 |
| Output contract | answer + cited pages + evidence quotes + explicit abstention | E8 |
| Pages read | k = 4, one read (no adaptive deepening) | E9 |

Source: `docs/validated_baseline_b1.md` §1, `experiments/frozen/e9/README.md`. The system design is in [`docs/architecture.md`](docs/architecture.md).

---

## Results at a glance (development data)

All numbers are from frozen, audited packages in `experiments/frozen/`. "Correct" uses the frozen scorer S-v1 (correct = score > 0), a local re-implementation of the benchmark's rule-based scorer: **these are not leaderboard numbers**.

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

Intervals are document-cluster bootstrap 95 % intervals. Sources: `AGENTS.md` (regression references), the `README.md` of each package in `experiments/frozen/`, and `experiments/frozen/e9/tables/evaluation_summary.json`. The full account, with hypotheses, designs and threats to validity, is in [`docs/research_report.md`](docs/research_report.md).

### What the evidence supports, and how strongly

- **One strong, replicated result: visual retrieval beats OCR + BM25.** It holds for evidence (E5) and for answers (E6). E6 fixed 13 questions and broke none, with an exact document sign-flip p = 2⁻¹⁰ ≈ 0.00098. Under the secondary scorer S-v2 it is 28/101 → 39/101 (`docs/validated_baseline_b1.md` §2).
- **Negative results, reported as such.**
  - E2: a stronger open VLM did not beat GPT-4o-mini (a tie within noise).
  - E3: adding the extracted text to the images did not help.
  - E7: reading each page separately, then answering from the extracted facts, was **worse** (the interval excludes zero).
  - E9: the adaptive policy was directionally positive (5 fixed, 0 broken across two replicates) but missed the pre-registered +0.05 criterion, and always reading 8 pages was not better than 4.
- **Non-inferiority only: the B1 contract.** 46 vs 42 of 102 (S-v1), 47 vs 44 of 101 (S-v2), with an interval that straddles zero. Two identical B1 replicates flip 4 questions (S-v1), 7 under S-v2. **B1 is not a demonstrated accuracy improvement over the previous contract.** What it does buy, measured: citation validity 1.000, 9/16 correct abstentions (8/16 before), 118/118 schema-valid replies (`docs/validated_baseline_b1.md` §2).
- **The ceiling.** B1 answers 46 of 102 answerable development questions. ColQwen2's top 4 pages miss part of the annotated evidence for 39 of 101 questions (`experiments/frozen/e9_stage0/README.md`). The strict grounding diagnostic passes 70 of 118 replies, and E8's data show it is a poor signal of correctness (`docs/e9_proposal.md` §1).

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
cd experiments/frozen/e6 && shasum -a 256 -c SHA256SUMS && cd -

pytest                                   # application modules, frozen protocols, parity with frozen runs
```

Then run the notebooks in order, on the `visualdoc-venv` kernel. **No notebook makes a paid call by default**: `VISUALDOC_QA_MODE` defaults to `replay` and every `VISUALDOC_E*_MODE` to `offline`. In those modes each notebook rebuilds its requests, asserts that they equal the frozen ones, re-scores the frozen replies and asserts the regression references in `AGENTS.md`. Paid modes (`smoke`, `pilot`, `full`) run only with the owner's explicit approval.

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

Notebooks communicate only through saved files. Each states its inputs and outputs at the top and stops with a clear message when an input is missing.

**What cannot be reproduced without paying:** whether the models would give the same replies today. At temperature 0 the same requests already differ between sessions (E9: 6 flips on byte-identical B1 requests sent on the same day). `gpt-6-luna` has no dated snapshot, and `gpt-4o-mini-2024-07-18` shuts down on 2027-01-14. The frozen replies, not the model names, define every result.

---

## How results are produced

- **Pre-registration.** From E1 on, each experiment has a JSON specification in `experiments/specs/`, committed before the first paid call. It fixes the population, arms, request construction, seeds, decision rule and budget ceiling. Paid modes refuse to run if the specification or the notebook code differs from the committed version.
- **Controlled comparisons.** Arms differ in one factor; requests of a question are sent adjacently in a seeded, counterbalanced order; repeat arms or a same-session control measure run-to-run change.
- **Scoring.** S-v1 (notebook 03 cell `f653d232`, correct = score > 0) is frozen and decides every verdict. S-v2 adds the owner's blind labels for ambiguous replies and is reported beside it; no model judgment replaces a human label.
- **Statistics.** The question is the unit, clustered by document: document-cluster bootstrap intervals (10,000 draws) and exact document sign-flip tests. McNemar and leave-one-document-out are descriptive. One primary contrast per experiment. Non-inferiority is not claimed on about 100 questions.
- **Freezing.** After a run, its directory is copied byte for byte into `experiments/frozen/<exp>/` with evaluation tables, an independent audit, provenance and `SHA256SUMS`. Frozen files are never edited.

Details: [`docs/research_report.md`](docs/research_report.md) §4.

## Open items

From `docs/PROGRESS.md` and `docs/final_evaluation_specification.md`:

1. **Final held-out evaluation.** The draft specification (B1 against OCR + BM25 with the same reader, on 111 untouched documents) needs the owner's approval, a budget (proposed ceiling $2.00) and a choice of indexing compute: about 5,300 pages to index with ColQwen2, about 18 h on the laptop or under an hour on an SSP Cloud GPU.
2. **S-v2 labels for E9.** 13 arm-blind items await the owner's labels; they cannot change the S-v1 verdict.
3. **Environment.** The repository sits in an iCloud-synced folder on a nearly full disk; evicted files must be downloaded again before some runs (`docs/reproducibility.md`).

---

## Repository layout

```text
.
├── notebooks/                 # 00–08: the research record, one stage per notebook
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
│   ├── specs/                 # pre-registered specifications E1–E9 (frozen before any call)
│   ├── frozen/                # committed runs, tables, audits, provenance and SHA256SUMS
│   ├── runs/                  # git-ignored outputs of new live runs
│   ├── README.md              # what each frozen folder holds
│   └── test_pool_ledger.md    # everything already seen about the untouched test pool
├── docs/                      # reports, specifications and the progress log (see below)
├── data/
│   ├── external/              # MMLongBench-Doc question table (tracked); PDFs downloaded on demand
│   ├── processed/, cache/     # git-ignored notebook and application outputs
│   ├── annotations/           # schema for the project's own question set (empty)
│   └── documents/             # three local sample PDFs, used by the tests and the demo
├── resources/                 # Tesseract English model; benchmark document list
├── archive/                   # superseded notebooks, course labs, old docs (read-only)
├── AGENTS.md                  # development policy: notebook-first, frozen files, paid-call gates
└── pyproject.toml, requirements.txt
```

## Documentation map

| Document | Content |
|---|---|
| [`docs/research_report.md`](docs/research_report.md) | Research report for E0–E9: questions, data, method, each experiment, negative results, statistics, threats to validity, the pending final evaluation |
| [`docs/architecture.md`](docs/architecture.md) | System architecture: the B1 pipeline, the application layer, caches, budgets, the notebook workflow, how experiments map to code |
| [`docs/reproducibility.md`](docs/reproducibility.md) | Environment, data, notebook order and modes, verifying frozen packages, what needs paid calls, resources, test-pool rules |
| [`docs/application.md`](docs/application.md) | Application usage: CLI, web page, visual index, live mode, tests |
| [`docs/validated_baseline_b1.md`](docs/validated_baseline_b1.md) | What B1 is, what the evidence supports and what it does not claim |
| [`docs/final_evaluation_specification.md`](docs/final_evaluation_specification.md) | **Draft, not approved**: the one-time held-out evaluation |
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

The reader change explains the drop: E6's GPT-4o-mini requests cost $1.827 per arm of 118 questions, while E8's 354 `gpt-6-luna` calls cost $0.144765 in all.

---

## Data, licences and the test pool

- **MMLongBench-Doc** (revision `2ff6aa92…`) is licensed CC BY-NC 4.0, research use only. Its question table is tracked; its PDFs are downloaded on demand into a git-ignored folder (`data/external/README.md`).
- **The untouched test pool** is every benchmark document outside the 20 used in development. Its questions, answers and evidence must not be read, and no system output may be produced for it, until a frozen final-evaluation specification is approved (`AGENTS.md`). `experiments/test_pool_ledger.md` records everything already seen about it. The application refuses all 115 pool document names; the check is mainly by name, so a renamed copy would not be recognised (`docs/application.md` §4).
- **ColQwen2** weights (`vidore/colqwen2-v1.0-hf`, revision `ddc07d23`, 4.4 GB) are downloaded once by notebook 04 and are not in git.
- Third-party material and local sample PDFs: [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md). Do not commit private or rights-restricted documents.

## Limitations

- **Development data only.** E0–E9 use 20 documents (175 questions) that shaped every decision; E6–E9 reuse the same 118 questions. No held-out result for B1 exists yet.
- **Small, clustered samples.** About 100 questions in 14 documents: one question is about 0.01 of accuracy, and replicate churn is 4–7 questions.
- **Single-annotator evidence.** A page that answers but is not annotated counts as missing.
- **Local scoring.** S-v1 re-implements the benchmark's rule-based scorer without its GPT-4o extraction step; S-v2 adds blind human labels for ambiguous replies.
- **An unpinnable reader.** `gpt-6-luna` returns no system fingerprint; frozen replies define the baseline.
- **Visual indexing is slow on the development laptop** (12.5 s per page on a fanless M1 with 8 GB of RAM) and the ColQwen2 weights are currently an iCloud placeholder there; without an index the app falls back to BM25.
