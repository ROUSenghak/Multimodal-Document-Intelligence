# Frozen S-v2 blind adjudication — E9 items

- **Frozen:** 2026-11-27.
- **Population:** the 13 distinct `(question, reply)` items that notebook 08's deterministic S-v2 layer left gray across the paid E9 arms (B1s, F8a, F8b), with no earlier owner label at the time of E9.
- **Judgment:** the project owner labelled the blind queue without arm identity: 7 correct, 6 wrong, 0 unsure. Only the question, reference and reply were shown; no page render.
- **Reused labels:** items 8, 9 and 12 are byte-identical to E10 items the owner had just labelled (`../e10_scoring_v2/`), so those labels were reused and the owner was told.
- **Identity protection:** `adjudication_labels.csv` stores a SHA-256 over the exact blind fields. Notebook 08 applies a label only to an item with the same identity.
- **Unblinding:** `adjudication_key.csv` is a byte-for-byte copy of the sealed key in `experiments/frozen/e9/adjudication/`, opened only after every label was recorded. All 13 identities match.

## Result (S-v2, secondary)

| 101 answerable questions | B1s | F8a | F8b | A1a | A1b |
|---|---:|---:|---:|---:|---:|
| correct | 47 | 48 | 49 | 49 | 49 |

- A1 − B1s = **+0.020**, 95 % document-cluster bootstrap interval [−0.005, +0.050], exact sign-flip p = 0.19; fixed / broken A1a 3 / 1, A1b 2 / 0.
- F8 − B1s = +0.015 [−0.052, +0.078], p = 0.39.
- The value lies inside the audit's range over every possible labelling (+0.005 to +0.040), as expected.

**The E9 verdict is unchanged:** `no_meaningful_gain` (S-v1, frozen). S-v2 agrees.

This package contains development evidence only and no model call was made to create it. `experiments/frozen/e9` is unchanged by this freeze.
