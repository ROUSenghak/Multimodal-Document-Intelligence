# Notebook-first development policy

During the learning and experimentation phase, project features are implemented directly in the Jupyter notebooks under `notebooks/`.

## Structure

- `notebooks/00_document_processing.ipynb` → `01_retrieval.ipynb` → `02_question_answering.ipynb` → `03_evaluation.ipynb` form the base workflow (E0–E4). Later stages each have their own notebook: `04_visual_retrieval` (E5), `05_visual_retrieval_answering` (E6), `06_extract_then_answer` (E7), `07_baseline_consolidation` (baseline B1: retrieval complementarity, scoring protocol v2, reader migration E8). Each notebook has one responsibility.
- Notebooks communicate **only through saved files** (`data/processed/`, `data/cache/`, `experiments/`). Each notebook states its inputs and outputs at the top and fails with a clear message when an input is missing. Never depend on variables created by another notebook.
- `experiments/frozen/` holds the committed canonical predictions and the frozen E1–E7 results. Never edit those files; new live runs go to the git-ignored `experiments/runs/`.
- The untouched test pool is every MMLongBench-Doc document outside the 20 used in E0–E7. Do not read its questions, answers or evidence, and produce no system output for it, until a frozen final-evaluation specification is approved; then use it once, for frozen configurations in one session. `experiments/test_pool_ledger.md` records everything already seen about it; update it whenever more is read.
- `archive/` is read-only history. Do not import from it or extend it.

## Required workflow

- Do not create new Python modules or scripts for exploratory or experimental functionality that can reasonably live in a notebook.
- Do not develop a `.py` implementation and convert or generate a notebook from it.
- Do not use `src/visualdoc/` as a hidden implementation layer for the notebooks. Rebuild important operations visibly in notebook cells.
- Preserve `src/visualdoc/parsing.py`, `tests/` and `archive/` as historical, regression or reference material unless the user explicitly requests a change.
- `src/visualdoc/` also holds the application baseline approved on 2026-11-22 (`documents`, `retrieval`, `answering`, `citations`, `pipeline`). Notebooks import it only where the application itself is the object measured: `02_question_answering` section 13 (E4), `03_evaluation` sections 16–17, and the E8 sections of `07_baseline_consolidation`. Those sections import it explicitly, check its module hashes or outputs against the notebooks' own construction, and never use it to replace a step the notebooks rebuild visibly. No other section imports it. Its constants are pinned to the frozen runs by parity tests; a change that breaks one is a new condition, not a fix.
- Keep each notebook executable from top to bottom on a fresh kernel (`visualdoc-venv`), given the outputs of the notebooks before it.
- Prefer extending an existing stage over adding a notebook. A new stage gets the next number.

## Notebook structure

Each notebook follows: Objective (with inputs, outputs, next step) → Method (technique, why it fits, assumptions, essential mathematics) → Implementation in small, sequential cells → Validation checks, including at least one failure case or limitation → Results → Interpretation beside the evidence.

Show the underlying operation once before wrapping it in a helper when that improves understanding. Keep outputs bounded. Never present mock, illustrative or synthetic values as project results; mocked API responses are interface tests only.

## Experimental integrity

- Do not change the dataset revision, subset, seeds, OCR or BM25 parameters, prompts, model snapshot, page lists or scoring rules without recording it as a new condition.
- Answer scoring: S-v1 (notebook 03 cell `f653d232`; correct = score > 0) is frozen and decides every historical verdict, which is never re-labelled. New results also report S-v2 (notebook 07): S-v1 plus blind human adjudication of the replies it marks gray. Keep the adjudication labels with the result.
- A reader served through an alias without a dated snapshot (for example `gpt-6-luna`) is recorded per call (served model, system fingerprint). A change in either is a new condition; frozen replies, not the model name, define a baseline.
- Paid API calls are opt-in, one mode variable per notebook (`VISUALDOC_QA_MODE` default `replay`; `VISUALDOC_E*_MODE` default `offline`). Never run `smoke`, `pilot` or `full` without the user's explicit approval. Never print or commit credentials.
- Regression references (Recall@5 0.689, Hit@5 0.800, A 7/40, B 7/40, C 9/40, D 11/38; E1 10/37 → 16/37 with 6 fixed / 0 broken, repeat 11/37, verdict adopt_768; E2 Qwen 11/37 → 15/37 vs GPT-4o-mini 16/37 with 4 fixed / 5 broken, repeat 15/37, verdict retain_gpt4o_mini_768; E3 T 13/37, I 17/37, IT 16/37 with IT − I 1 fixed / 2 broken, repeat 16/37, verdict retain_image_only_768; E4 APP 11/40 answerable, ORACLE 17/37, ORACLE − APP 8 fixed / 2 broken, cross-session margin 5/37, verdict page_selection_costs_accuracy, spend $1.2006; E5 held-out evidence recall after the guard A 0.526 → V 0.721, verdict visual_improves_evidence; E6 A 25/102 → V 38/102 with 13 fixed / 0 broken, verdict adopt_visual_retrieval, spend $3.7213; E7 V0 38/102, X4 31/102, X8 29/102 with X4 − V0 3 fixed / 10 broken, verdict regression, spend $5.911057) are asserted in the notebooks; a change that breaks them must be explained, not silenced.

## Completion standard

Validate notebook JSON, execute the notebooks in order from a fresh kernel, save their outputs, inspect their rendered presentation, and run `pytest`. If credentials, annotations or an unresolved model choice block execution, keep an explicit readiness gate and state the missing input inside the notebook.

Extending the application baseline beyond its five modules, adding an application framework or user interface, or deleting the existing Python baseline is a separate phase that requires explicit user approval.
