# E8 — reader migration and B1 stabilisation

This package is the immutable E8 execution and primary S-v1 evaluation. The run used the 118 development questions from E6; it did not read or run a system on the final test pool.

## Frozen result

- Run: `20261125T140433934010Z_4edb90e7_full`
- Execution: 354/354 successful first attempts; 118 replies in each of L-v1, L-B1 and L-B1r
- Served identity: `gpt-6-luna`; the service returned no system fingerprint
- Observed list-price cost: $0.144765 under the frozen $0.50 ceiling
- S-v1 answerable accuracy: L-v1 42/102; L-B1 46/102; L-B1r 46/102
- L-B1 − L-v1: +0.039; document-cluster 95% interval [-0.019, +0.098]; 8 fixed, 4 broken
- Stability: 4 correctness flips between L-B1 and L-B1r
- Correct abstentions: L-v1 8/16; L-B1 and L-B1r 9/16
- Citation-form validity: 1.000 in all three arms
- Frozen-rule S-v1 verdict: promote B1

The stricter grounding diagnostic is not the citation-form gate. L-B1 passed 70/118 replies: quotes were supported on 88/118 and numeric support passed on 25/53 applicable replies. No reply used an invalid evidence page or omitted evidence for a cited page. These failures are evidence for the next verification-triggered agent experiment, not a post-hoc change to E8's rule.

## S-v2 status

S-v2 is **not final**. Sixteen new distinct gray replies require blind owner labels. `adjudication/blind_queue_unlabelled.csv` is the frozen empty-label snapshot. The editable copy remains in the git-ignored live run. Do not open `adjudication/sealed_key.csv` before labeling; it contains the arm mapping. Final labels must be frozen separately with item-identity hashes, leaving this package unchanged.

## Contents

- `run_.../`: byte-identical append-only execution log, settings and execution summary.
- `tables/`: per-question metrics without reply text and the S-v1 evaluation summary.
- `adjudication/`: the arm-blind empty queue and its sealed key.
- `AUDIT.json`: fixed integrity and result checks.
- `PROVENANCE.json`: commits, protocol and copying provenance.
- `SHA256SUMS`: hashes for every file except itself.

Notebook 07 reproduces the evaluation in `VISUALDOC_QA_MODE=replay`. Never edit this directory.
