# Frozen S-v2 blind adjudication — E10 items

- **Frozen:** 2026-11-27.
- **Population:** the 17 distinct `(question, reply)` items that notebook 10's deterministic S-v2 layer left gray across the three E10 arms (B1s, AGa, AGb), for which no earlier owner label existed.
- **Judgment:** the project owner labelled the blind queue without arm identity: 9 correct, 8 wrong, 0 unsure. Only the question, reference and reply were shown; no page render.
- **Identity protection:** `adjudication_labels.csv` stores a SHA-256 over the exact blind fields `document`, `evidence_pages`, `question`, `answer_format`, `reference` and `reply`. Notebook 10 applies a label only to an item with the same identity.
- **Unblinding:** `adjudication_key.csv` is a byte-for-byte copy of the sealed key in `experiments/frozen/e10/adjudication/`, opened only after every label was recorded. All 17 identities match.
- **Unsure rule:** unchanged. No E10 item was labelled unsure, so the S-v2 denominator of 101 comes from the single inherited unsure item (`mmlb-1013`).

## Result (S-v2, secondary)

| 101 answerable questions | B1s | AGa | AGb | AG (avg) |
|---|---:|---:|---:|---:|
| correct | 47 | 55 | 57 | 56 |

- AG − B1s = **+0.089** (+9 questions), 95 % document-cluster bootstrap interval [+0.017, +0.177], 5th percentile +0.029, exact sign-flip p = 0.025.
- Fixed / broken versus B1s: AGa 13 / 5, AGb 16 / 6.
- The pending bounds were +0.045 to +0.104; the labelled value sits inside them.

**This does not change the E10 verdict.** The pre-registered primary metric is S-v1, and its frozen verdict stays `regression`. Under S-v2 the broken-ratio rule would not fire (6 ≤ 16 / 2) and the sign-flip p would pass 0.05, but the replicate flips rule (12 > 10) would still block `go`. This is a secondary reading and is reported as such.

This package contains development evidence only. It contains no test-pool question, and no model call was made to create it.
`experiments/frozen/e10` is unchanged by this freeze.
