# E9: adaptive evidence acquisition (development data)

This package is the immutable E9 Stage 2 execution, its Stage 1 smoke and the primary S-v1 evaluation. Stage 0 (offline trigger selection) is frozen separately in `../e9_stage0/`.

**Population.** The 118 development questions of E6/E8 (102 answerable, 16 unanswerable) in 14 documents. The test pool was not read or run.

## Question and design

Does reading ColQwen2 pages 5–8 *only when retrieval looks uncertain* answer more questions than B1's fixed top 4, and is any gain due to the trigger rather than to more pages?

- **Pre-registration.**
  - Spec: `experiments/specs/e9_adaptive_evidence_v1.json`, commit `7f41eea`, written before any analysis.
  - Technical addendum: `…_addendum.json`, commit `a30bb29`, written before any paid call.
- **Trigger** (selected by Stage 0). U3 = −(s₁ − s₈)/s₁ of the ColQwen2 MaxSim scores. It fires at ≥ −0.153079, on 47/118 questions.
- **Arms** (one session, `gpt-6-luna`, contract b1, temperature 0, reasoning effort none):

| Arm | What it reads | Calls |
|---|---|---:|
| **B1s** | top 4 pages; same session, requests byte-identical to frozen E8 L-B1 | 118 |
| **F8a**, **F8b** | top 8 pages, two replicates | 236 |
| **A1a**, **A1b** | derived without a call: the F8 reply where the trigger fires, the B1s reply elsewhere | 0 |

## Result: `no_meaningful_gain` (S-v1, frozen rules)

| Arm | S-v1 correct / 102 | Correct abstentions / 16 | Citation validity | Mean prompt tokens |
|---|---:|---:|---:|---:|
| B1s | 44 | 9 | 1.000 | 3,977 |
| F8a | 46 | 9 | 0.992 | 7,641 |
| F8b | 46 | 8 | 0.992 | 7,641 |
| A1a | 47 | 9 | 0.992 | 5,421 |
| A1b | 46 | 9 | 0.992 | 5,421 |

**Contrasts.** Document-cluster bootstrap (10,000 draws) and the exact sign-flip test over 14 documents:

| Contrast | Δ | 95 % CI | Sign-flip p | Fixed / broken |
|---|---:|---|---:|---|
| **A1 − B1s (primary, replicate-averaged)** | **+0.025** | [0.000, +0.051] | 0.125 | a: 3 / 0; b: 2 / 0 |
| F8 − B1s | +0.020 | [−0.048, +0.079] | 0.33 | — |
| A1 − F8 | +0.005 | [−0.050, +0.065] | 0.50 | — |
| F8 − B1s, triggered questions only | +0.061 | [0.000, +0.125] | 0.125 | — |
| F8 − B1s, untriggered questions only | −0.008 | [−0.103, +0.079] | 0.63 | — |

**How the frozen rules decide.**
- The guardrails pass.
- The engineering criterion (Δ ≥ +0.05 on average and in each replicate) fails: +0.025, +0.029 and +0.020.
- The verdict is therefore **`no_meaningful_gain`**.
- The statistics would not have supported adoption either: the sign-flip p is 0.125.

**Stability.** F8a and F8b differ on 2 questions. B1s against the frozen E8 L-B1 replies, on byte-identical requests sent on the same day: 44 vs 46, with 6 flips.

**S-v2 (secondary).** 13 new arm-blind gray items await the owner's labels (`adjudication/blind_queue_unlabelled.csv`).
- Over every consistent labelling of those items, A1 − B1s ranges from **+0.005 to +0.040**, or +0.042 if "unsure" is allowed.
- No labelling reaches +0.05 or −0.05, so S-v2 cannot change the verdict.
- Counting every pending item as wrong gives +0.025; counting every one as correct gives +0.020. These are not bounds.

**Cost.** $0.147055 for the full run plus $0.004592 for the smoke = **$0.151647** of the $0.50 ceiling. All 360 calls succeeded on the first attempt, with one served model (`gpt-6-luna`) and no system fingerprint.

## Interpretation

1. **The adaptive policy is directionally positive and never broke an answer.** It fixed 3 and 2 questions in the two replicates and broke none. The effect is about 2.5 points, below the pre-registered +0.05 materiality and not statistically established. The independent Stage 0 audit predicted this before any paid call:
   - U3 detects *incomplete* evidence well (AUROC 0.78), but it is at chance for the questions that 8 pages can *complete* (AUROC 0.48);
   - the ceiling on A1 − B1s was therefore about +0.069.
2. **Reading 8 pages for every question is not better than 4.** It helps on triggered questions (+0.061) and slightly hurts the others (−0.008). This is the pattern a useful trigger would show, but at this sample size it is suggestive only.
3. **The same-session control mattered.** Identical requests on the same day differ from the frozen E8 replies by 2 questions (6 flips). Against the frozen replies, A1's apparent gain would almost vanish (+0.005). Any future claim of a gain under about 7 questions on this set needs a same-session control and replicates.

**Consequence.** B1 is unchanged: ColQwen2 top 4, one read. The application does not adopt adaptive acquisition. Under the spec, a non-adopted policy is not carried into the final evaluation as a candidate.

## Caveats found by the independent audit (none changes the verdict)

- **The provider's prompt cache was active.** 104/118 F8b calls and 54 F8a calls reused a cached prompt prefix, while E8 had none.
  - Replies were generated fresh, not replayed: 37/118 F8a and F8b replies differ, and latency is equal.
  - Replicate agreement was no higher than E8's uncached pair: 81/118 identical replies, against 80/118.
  - Without the cache, the run would have cost $0.236.
  - This is the only visible sign that serving changed between the E8 and E9 sessions.
- **The system-fingerprint guard could never fire.** The service returned no system fingerprint in any of the 708 E8 and E9 calls. In a completed run, the schema guardrail cannot fail either, because the executor stops on any contract error.
- **The sign-flip test had little power.** Only 3 of the 14 documents have a non-zero A1 − B1s, so the smallest attainable p was 2⁻³ = 0.125, which is the value observed. The CI's lower bound is exactly 0 because no document lost an answer.
- **Guardrail margins.** F8b's correct abstentions (8) sit one question above their floor (7). The only invalid citation in F8a and F8b is a *missing* citation: a correct, non-abstention answer with an empty `cited_pages` (mmlb-0579). No reply cited a page outside the 8 supplied.
- **Counterbalance.** B1s went first for 59 of 118 questions, which is 55 B1s-first against 47 F8a-first on the 102 answerable ones. No order effect is detectable (permutation p = 0.22), but order is confounded with the prompt cache.
- **The drift is ordinary churn.** B1s differs from L-B1 on 6 questions and from L-B1r on 8. Across the three B1 replicates, B1s is the odd one out in 5 of 9 split questions (binomial p = 0.145). Its 4 net losses fall on untriggered questions, where A1 uses the B1s reply, so they cancel out of the primary contrast.

## Contents

| Path | Content |
|---|---|
| `run_20261125T171152006205Z_57d16dea_full/` | byte-identical append-only execution log (loggable requests without Base64, raw replies, usage, served identity), settings with the full plan, and the run summary |
| `smoke_20261125T171115088784Z_8a4e2bb5/` | the 6-call smoke run and its gate (all 7 checks passed) |
| `tables/evaluation_per_question.csv` | per arm and question: S-v1 score, S-v2 class and final label, schema, citation, abstention, pages, tokens, cost. No reply text |
| `tables/evaluation_summary.json` | arm table, decision, secondary contrasts, drift, S-v2 interval |
| `adjudication/blind_queue_unlabelled.csv` | the 13 arm-blind S-v2 items, with empty labels |
| `adjudication/sealed_key.csv` | the arm mapping. **Do not open before labelling** |
| `AUDIT.json`, `audit/` | the independent Stage 2 audit and its script |
| `PROVENANCE.json` | commits, protocol, copying provenance |
| `SHA256SUMS` | checksums of every file except itself |

Notebook 08 reproduces the evaluation from this package in its default `offline` mode, with no API call. Never edit this directory. Final S-v2 labels are frozen separately (`../e9_scoring_v2/`), as in E8.
