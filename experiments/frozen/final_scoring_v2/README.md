# Frozen S-v2 blind adjudication — final held-out evaluation

- **Frozen:** 2026-11-27.
- **Population:** the 85 distinct `(question, reply)` items that notebook 09's deterministic S-v2 layer left gray across the paid final arms (B1, T1, F8) on the held-out pool. A1 inherits its labels from the F8 or B1 reply it reuses.
- **Judgment:** the project owner labelled the blind queue without arm identity, in four batches: 53 correct, 32 wrong, 0 unsure. Only the question, reference and reply were shown; no page render.
- **Use of held-out data:** scoring only. The frozen replies were labelled; no design, prompt or threshold changed.
- **Identity protection:** `adjudication_labels.csv` stores a SHA-256 over the exact blind fields. Notebook 09 applies a label only to an item with the same identity.
- **Unblinding:** `adjudication_key.csv` is a byte-for-byte copy of the sealed key in `experiments/frozen/final/adjudication/`, opened only after every label was recorded. All 85 identities match.

## Result (S-v2, secondary; statistics as notebook 09: document-cluster bootstrap over 110 documents, Monte Carlo sign-flip)

| 674 answerable questions | B1 | T1 | A1 |
|---|---:|---:|---:|
| S-v2 correct | 296 | 217 | 311 |

| Claim | S-v1 (frozen, decides) | S-v2 (owner-labelled) |
|---|---|---|
| **C2** B1 − T1 (visual vs OCR retrieval) | +0.119 [+0.088, +0.150], 103 / 23 | **+0.117** [+0.087, +0.148], p05 +0.092, sign-flip p < 0.0001, 104 / 25 |
| **C3** A1 − B1 (adaptive evidence) | +0.021 [+0.007, +0.036], p 0.005, 19 / 5 | **+0.022** [+0.009, +0.037], p05 +0.011, sign-flip p 0.002, 20 / 5 |

- Both values lie inside the ranges frozen before labelling (C2 [+0.077, +0.150], C3 [+0.015, +0.028]).
- **Both claims hold under S-v2.** C3's worst-case sign-flip p of 0.049 does not occur: with the owner's labels it is 0.002.
- C3 remains below E9's +0.05 materiality; B1 stays the shipped system, as frozen.

`experiments/frozen/final` is unchanged by this freeze. No model call was made to create this package.
