# Final evaluation v1: recorded deviations

Each deviation is written and committed **before any result it could affect was computed**:
- D1 was committed before any question was read;
- D2 was committed after the reader run but before any final number existed.

None was chosen by looking at a result.

## D1 — Documents whose bytes cannot be verified are excluded (2026-11-25)

**Rule (notebook 09, download cell).**
- A pool document is evaluated only if its bytes equal the hash recorded at the pinned revision `2ff6aa92…`: the LFS SHA-256 for files stored in LFS, the git blob SHA-1 for files stored directly in git.
- If the Hugging Face client refuses a file, the revision's resolve URL is fetched directly. The bytes are kept only if their hash equals the recorded one.
- Documents that still cannot be verified are excluded, with all of their questions.
- The rule is technical, applies to every document alike, and was fixed before any question was read.

**Why not use unverified bytes.** If the content differs from what was annotated, the evidence pages and answers may not correspond to it. Scoring against them would mix annotation error into the result.

**How the rule was reached** (recorded in full, including a mistake):

1. **`mi_phone.pdf` triggered the rule.** The client refused it on size. The served object has 31,841,340 bytes and SHA-256 `16ee1cfb…`. The revision records 24,877,442 bytes and `c5feec13…`.
2. **A mistake in the first implementation.** It compared every file with an LFS SHA-256. 20 small PDFs are stored directly in git and have none, so they were wrongly flagged.
   - It was caught before any question was read or any page was encoded.
   - It was fixed by verifying git-stored files against their git blob SHA-1. All 20 verify.
3. **`dr-vorapptchapter1emissionsources-121120210508-phpapp02_95.pdf` has a wrong LFS size field.** The pointer records 11,191,551 bytes, yet the served object has 15,398,470 bytes and **exactly the recorded SHA-256** (`13562992…`).
   - The content hash identifies the file, so it is verified through the direct-fetch fallback and **included**.
   - The local copy downloaded during E5's selection (11,191,551 bytes, `8250d7a3…`) was a different file. It is replaced.

**Excluded documents:**

- `mi_phone.pdf`: the served bytes differ from the recorded LFS SHA-256.

**Effect.** 110 of the 111 documents are evaluated. Every claim and rule in `final_evaluation_v1.json` is otherwise unchanged.

## D2 — S-v1 scorer crash on numeric questions (2026-11-26)

**When.** Decided after the full run completed but **before any final number was computed**. The evaluation stopped on the first affected reply; no claim, count or contrast had been produced.

**What happened.** The frozen S-v1 cell (notebook 03 `f653d232`, copied in notebooks 07–09) converts a Float question's reference and reply in a single tuple assignment: `gt, pred = float(clean(gt)), float(clean(pred))`. When the reply is not numeric, the assignment fails as a whole. The reference stays an unconverted string, and the next line, `float("$1577.00")`, raises. The official MMLongBench-Doc code converts the two separately, so for the same reply it returns score 0. The case never occurs in the development data.

**Rule.**
- When, and only when, the frozen function raises on a Float question:
  - if the cleaned reference is numeric and the reply is not → score **0**, the official result;
  - if the cleaned reference is not numeric → S-v1 cannot score the question (the official code fails as well). Every arm scores **0**, and the count of such questions is reported.
- Any other exception still stops the evaluation.
- The frozen cell's source is unchanged and still pinned. The wrapper is a separate, visible cell in notebook 09.

**Check.** The wrapped scorer reproduces all 708 frozen E8 and E9 S-v1 scores exactly. No historical verdict changes.
