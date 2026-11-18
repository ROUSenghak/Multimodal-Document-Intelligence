# `experiments/` — evaluation runs (planned)

This folder will hold the controlled comparisons described in the root
`README.md` (text-only vs multimodal question answering).

Nothing has been run yet.

Convention for when it is used:

- `experiments/<name>/` — code or notebook plus a short `README.md` stating
  the configuration (models, prompts, retrieval settings, question split).
- `experiments/<name>/summary.*` — small result tables (metrics per question
  type / evidence modality). **Committed**, so results are reviewable.
- `experiments/runs/` — raw per-run outputs (model responses, caches,
  embeddings). **Git-ignored**: large, regenerable, and may contain API output
  you do not want to publish.

The earlier exploratory notebooks live under `notebooks/`. They resolve
inputs from the repository root and remain separate from controlled runs so
saved demonstrations are not mistaken for evaluation results.
