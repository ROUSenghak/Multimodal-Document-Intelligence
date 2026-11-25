# Frozen S-v2 blind adjudication — E8 items

- **Frozen:** 2026-11-25.
- **Population:** the 16 distinct `(question, reply)` items that notebook 07's deterministic S-v2 layer left gray across the three E8 arms, and for which no historical label existed.
- **Judgment:** the project owner labelled the blind queue without arm identity: 9 correct, 7 wrong, 0 unsure.
- **Identity protection:** `adjudication_labels.csv` stores a SHA-256 over the exact blind fields `document`, `evidence_pages`, `question`, `answer_format`, `reference` and `reply`. Notebook 07 refuses to apply a label if that identity changes.
- **Unblinding:** `adjudication_key.csv` is a byte-for-byte copy of the sealed key in `experiments/frozen/e8/adjudication/`, opened only after every label was recorded.
- **Evidence:** four items (1, 3, 6, 11) were adjudicated with the cached 768 px page render in view — the same image the reader received. The source PDFs were not used; they are macOS dataless placeholders on this machine.
- **Unsure rule:** unchanged from the E6/E7 adjudication. No E8 item was labelled unsure, so the S-v2 denominator of 101 comes entirely from the single inherited unsure item (`mmlb-1013`).

This package contains development evidence only. It contains no test-pool question, and no model call was made to create it.
`experiments/frozen/e8` is unchanged by this freeze.
