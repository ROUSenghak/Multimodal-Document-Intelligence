# Frozen final-evaluation index (no question read)

This package is the index of the final held-out evaluation, frozen **before any test-pool question, answer or evidence was read**. It follows the order fixed in `experiments/specs/final_evaluation_v1.json`: index → commit → only then questions.

## Contents

| File | Content |
|---|---|
| `pool_documents.csv` | the 111 pool documents: bytes, the hash recorded at revision `2ff6aa92…` (LFS SHA-256 or git blob SHA-1), the local hash, SHA-256, page count, and whether the document was verified (deviation D1) |
| `index_manifest.csv` | one row per page of the 110 verified documents: native word count, whether OCR was used, render size, the PNG's SHA-256, the ColQwen2 embedding file's SHA-256, and the SHA-256 of the page text. No text is stored |
| `parity_gate.json` | the bitwise reproduction of E5 required by the spec before any pool page was encoded |
| `index_summary.json` | the counts and encoding statistics |
| `SHA256SUMS` | checksums of every file above |

## Result

- **Documents.** 110 of the 111 are verified. `mi_phone.pdf` is excluded because its served bytes differ from the recorded hash (deviation D1, `experiments/specs/final_evaluation_v1_deviations.md`).
- **Pages.** 5,554 pages (5,348 distinct images), all embedded by ColQwen2 v1.0 at revision `ddc07d23…` on the Apple M1 GPU, with the encoder configuration identical to E5's.
- **Parity gate.** Passed: two development pages and one development question re-encoded from scratch equal the frozen E5 cache bit for bit.

The embeddings themselves (about 1 GB) are git-ignored under `data/cache/final/`. Their SHA-256s are in the manifest, so any copy can be verified against this package. Never edit this directory.
