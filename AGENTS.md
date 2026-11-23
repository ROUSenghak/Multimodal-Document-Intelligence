# Notebook-first development policy

During the learning and experimentation phase, project features are implemented directly in the Jupyter notebooks under `notebooks/`.

## Structure

- `notebooks/00_document_processing.ipynb` → `01_retrieval.ipynb` → `02_question_answering.ipynb` → `03_evaluation.ipynb`. Each notebook has one responsibility.
- Notebooks communicate **only through saved files** (`data/processed/`, `data/cache/`, `experiments/`). Each notebook states its inputs and outputs at the top and fails with a clear message when an input is missing. Never depend on variables created by another notebook.
- `experiments/frozen/` holds the committed canonical predictions and the frozen E1–E4 runs. Never edit those files; new live runs go to the git-ignored `experiments/runs/`.
- `archive/` is read-only history. Do not import from it or extend it.

## Required workflow

- Do not create new Python modules or scripts for exploratory or experimental functionality that can reasonably live in a notebook.
- Do not develop a `.py` implementation and convert or generate a notebook from it.
- Do not use `src/visualdoc/` as a hidden implementation layer for the notebooks. Rebuild important operations visibly in notebook cells.
- Preserve `src/visualdoc/parsing.py`, `tests/` and `archive/` as historical, regression or reference material unless the user explicitly requests a change.
- `src/visualdoc/` also holds the application baseline approved on 2026-11-22 (`documents`, `retrieval`, `answering`, `citations`, `pipeline`). Notebooks import it only where the application itself is the object measured: `02_question_answering` section 13 (E4) and `03_evaluation` sections 16–17. Those sections import it explicitly, check its module hashes or outputs against the notebooks' own construction, and never use it to replace a step the notebooks rebuild visibly. No other section imports it. Its constants are pinned to the frozen runs by parity tests; a change that breaks one is a new condition, not a fix.
- Keep each notebook executable from top to bottom on a fresh kernel (`visualdoc-venv`), given the outputs of the notebooks before it.
- Prefer extending an existing stage over adding a notebook. A new stage gets the next number.

## Notebook structure

Each notebook follows: Objective (with inputs, outputs, next step) → Method (technique, why it fits, assumptions, essential mathematics) → Implementation in small, sequential cells → Validation checks, including at least one failure case or limitation → Results → Interpretation beside the evidence.

Show the underlying operation once before wrapping it in a helper when that improves understanding. Keep outputs bounded. Never present mock, illustrative or synthetic values as project results; mocked API responses are interface tests only.

## Experimental integrity

- Do not change the dataset revision, subset, seeds, OCR or BM25 parameters, prompts, model snapshot, page lists or scoring rules without recording it as a new condition.
- Paid API calls are opt-in (`VISUALDOC_QA_MODE`, default `replay`). Never run `smoke`, `pilot` or `full` without the user's explicit approval. Never print or commit credentials.
- Regression references (Recall@5 0.689, Hit@5 0.800, A 7/40, B 7/40, C 9/40, D 11/38; E1 10/37 → 16/37 with 6 fixed / 0 broken, repeat 11/37, verdict adopt_768; E2 Qwen 11/37 → 15/37 vs GPT-4o-mini 16/37 with 4 fixed / 5 broken, repeat 15/37, verdict retain_gpt4o_mini_768; E3 T 13/37, I 17/37, IT 16/37 with IT − I 1 fixed / 2 broken, repeat 16/37, verdict retain_image_only_768; E4 APP 11/40 answerable, ORACLE 17/37, ORACLE − APP 8 fixed / 2 broken, cross-session margin 5/37, verdict page_selection_costs_accuracy, spend $1.2006) are asserted in the notebooks; a change that breaks them must be explained, not silenced.

## Completion standard

Validate notebook JSON, execute the notebooks in order from a fresh kernel, save their outputs, inspect their rendered presentation, and run `pytest`. If credentials, annotations or an unresolved model choice block execution, keep an explicit readiness gate and state the missing input inside the notebook.

Extending the application baseline beyond its five modules, adding an application framework or user interface, or deleting the existing Python baseline is a separate phase that requires explicit user approval.
