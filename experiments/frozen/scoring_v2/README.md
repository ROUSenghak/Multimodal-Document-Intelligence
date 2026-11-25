# Frozen S-v2 blind adjudication

- **Frozen:** 2026-11-25.
- **Population:** the 29 distinct `(question, reply)` items classified as gray by notebook 07's deterministic S-v2 layer across frozen E6 and E7.
- **Judgment:** the project owner labelled the blind queue without arm identity: 7 correct, 21 wrong and 1 unsure.
- **Identity protection:** `adjudication_labels.csv` stores a SHA-256 for the exact blind fields `document`, `evidence_pages`, `question`, `answer_format`, `reference`, and `reply`. Notebook 07 refuses to apply a label if this identity changes.
- **Unblinding:** `adjudication_key.csv` maps item IDs to question IDs and arms only after judgment.
- **Unsure rule:** an unsure observation is excluded from the S-v2 point estimate and paired contrast; the result also reports the sensitivity interval obtained by counting it wrong and correct. S-v1 remains the historical primary score and is never relabelled.

This package contains development evidence only. It contains no test-pool question and no model call was made to create it.
