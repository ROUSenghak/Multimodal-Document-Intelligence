# Notebook-first development policy

During the learning and experimentation phase, implement project features directly in Jupyter notebooks under `notebooks/project/`.

## Required workflow

- Do not create new Python modules or scripts for exploratory or experimental functionality that can reasonably live in a notebook.
- Do not develop a `.py` implementation and convert or generate a notebook from it.
- Do not use `src/visualdoc/` as a hidden implementation layer for new learning notebooks. Rebuild important operations visibly in notebook cells.
- Preserve the existing `src/`, `tests/`, `notebooks/prototypes/`, and `notebooks/course_labs/` content as historical, regression, or reference material unless the user explicitly requests a change.
- Keep project notebooks independently executable from top to bottom. Do not depend on variables created by another notebook.
- Use numbered filenames in `notebooks/project/` to preserve the learning sequence.

## Notebook teaching structure

Each substantive notebook must include:

1. Objective
2. Concept and relevant assumptions or mathematics
3. Small, focused implementation cells
4. Executed outputs
5. Inspection of intermediate values, tables, or figures
6. Interpretation beside the evidence
7. Validation checks and at least one relevant failure case or limitation
8. A clear next step

Show the underlying operation before wrapping it in a helper function when that improves understanding. Keep outputs bounded and never present mock, illustrative, or synthetic values as project results.

## Completion standard

Validate notebook JSON, execute runnable notebooks from a fresh kernel, save their outputs, and inspect their rendered presentation. If credentials, annotations, or an unresolved model choice block execution, retain an explicit readiness gate and state the missing input inside the notebook.

Moving notebook code into production modules, adding an application framework, or deleting the existing Python baseline is a separate phase that requires explicit user approval.
