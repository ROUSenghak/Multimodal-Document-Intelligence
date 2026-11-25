# Final evaluation v1: recorded deviations

Each deviation is written and committed **before** any pool question, answer or evidence is read, and before any reader call. None depends on a result.

## D1 — Documents whose bytes cannot be verified are excluded (2026-11-25)

**What happened.** During download, Hugging Face served `mi_phone.pdf` with different bytes from the pinned revision `2ff6aa92…`:

| | Size | SHA-256 |
|---|---:|---|
| LFS pointer at the revision | 24,877,442 bytes | `c5feec13…` |
| Object served by the CDN | 31,841,340 bytes | `16ee1cfb…` |

The failure reproduces with `huggingface_hub` and with a plain `curl` of the resolve URL. The exact document the benchmark annotated therefore cannot be obtained.

**Rule (added to notebook 09's download cell).**
- A pool document is evaluated only if its downloaded bytes equal the pinned revision's LFS SHA-256.
- Documents that cannot be verified are excluded, with all of their questions, and listed below with the reason.
- The rule is technical, applies to every document alike, and was fixed before any question was read.

**Why not use the served bytes.** If the content differs, the annotated evidence pages and answers may not correspond to it. Scoring against them would mix annotation error into the result.

**Effect.** The population becomes the 111 documents minus the excluded ones. Every claim and rule in `final_evaluation_v1.json` is otherwise unchanged.

**Excluded documents** (filled in from the download log before the index manifest is frozen):

- `mi_phone.pdf`: the CDN bytes differ from the LFS SHA-256.
