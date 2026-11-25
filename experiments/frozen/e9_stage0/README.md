# Frozen E9 Stage 0: retrieval-uncertainty trigger selection (offline, $0)

**Question.** Does any of five pre-registered signals predict that ColQwen2's top 4 pages miss annotated evidence?

**Spec.** `experiments/specs/e9_adaptive_evidence_v1.json`, committed in `7f41eea` before any association was computed.

**Population.** 101 held-out development questions with annotated evidence, in 14 documents. Thresholds are set over all 118 questions without labels. No test-pool document is involved.

## Result: Stage 0 passed

Only U3, the flatness of the top-8 scores −(s₁ − s₈)/s₁, satisfies all five gates G1–G5:

| | U3 |
|---|---|
| AUROC | 0.783, document-cluster 95 % CI [0.661, 0.861] |
| Holm-adjusted p | 0.0005 (the bootstrap floor) |
| Lift at a 40 % trigger rate | +0.239 [+0.095, +0.362] |
| Leave-one-document-out minimum | 0.752 |
| Recoverable questions triggered | 8 |

- **Frozen threshold:** −0.153079, which triggers on 47 of the 118 questions.
- **Base rate:** evidence is incomplete at k = 4 for 39 of the 101 questions.
- **Headroom:** for 15 questions the missing evidence sits at ranks 5–8, and 8 questions become complete at k = 8.

## The limitation that matters downstream

U3 predicts *incomplete* evidence. It does not predict evidence that 8 pages would recover:

- AUROC is 0.634 against "evidence at ranks 5–8".
- AUROC is 0.480 against "complete at 8 but not at 4".
- Of the 40 triggered labelled questions, only 8 are recoverable.

The ceiling for the adaptive policy A1 against B1 is therefore about +0.069, and the expected gain is below the +0.05 engineering criterion. This was recorded before any paid call (notebook 08, cell `e9-stage0-results`).

## Contents

| Path | Content |
|---|---|
| `tables/stage0_summary.json` | The gate, all signals, thresholds, headroom and strata |
| `tables/stage0_per_question.csv` | Identifiers, targets, signals and triggers. No question, answer or page text |
| `audit/audit_e9_stage0.py` | The independent auditor's script. It shares no code with notebook 08 |
| `audit/audit_output.txt` | Its output: reproduction differences ≤ 5e-7, and foundation checks on page numbering, pages read, leakage, population, threshold, 10-K sensitivity and proxies |
| `SHA256SUMS` | Checksums of every file above |

Reproduce with notebook 08 (`VISUALDOC_E9_MODE=offline`, the default), or run `.venv/bin/python experiments/frozen/e9_stage0/audit/audit_e9_stage0.py` from the repository root. Never edit this directory.
