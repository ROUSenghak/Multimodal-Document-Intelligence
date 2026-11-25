# E9 proposal — adaptive evidence acquisition

**Status:** proposal only. No specification is frozen, no notebook 08 exists, no paid call is authorised.
**Population:** the same 118 development questions in 14 documents. The test pool stays untouched.

---

## 1. The finding that reshapes this experiment

E9 was planned as *verification-triggered* adaptive retrieval: when B1's grounding check fails, fetch more evidence and read again. **The E8 data does not support that trigger.** Measured on both independent B1 replicates:

| | S-v1 wrong | S-v1 correct | P(wrong \| signal) |
|---|---:|---:|---|
| Grounding **fails** (L-B1) | 17 | 27 | **0.39** |
| Grounding **passes** (L-B1) | 39 | 19 | **0.67** |
| Grounding **fails** (L-B1r) | 18 | 24 | 0.43 |
| Grounding **passes** (L-B1r) | 38 | 22 | 0.63 |

Base rate of wrong answers: 0.55. **A grounding failure makes an answer *more* likely to be correct, not less** — replicated across two independent runs, and true of the quote and numeric components separately.

So a verification-triggered policy would spend its budget on the subpopulation that is already better than average, re-reading 27 correct answers to attempt 17 repairs — against a measured replicate churn of 7 questions. The expected value is negative.

**Likely mechanism (hypothesis, not established):** the grounding check requires verbatim quotes that match the page's text layer. E5 showed ColQwen2's advantage concentrates on figures (0.40 → 0.85), layout text (0.45 → 0.76) and OCR'd pages (0.49 → 0.85) — exactly the pages whose text layer is poor. A model that correctly reads a chart produces a quote that cannot string-match, and fails the check. A model that is wrong while copying clean body text passes it.

This does not make the grounding checker useless — it remains a *user-facing trust signal* and a genuine measure of citation quality. It makes it a bad *repair trigger*.

## 2. Motivation — where the errors actually are

Three frozen results point at the same bottleneck:

- **E4:** oracle pages 17/37 vs application pages 11/40 → `page_selection_costs_accuracy`.
- **E5:** after the context guard, ColQwen2 supplies *all* annotated evidence for only **61/101** questions, and some for 86/101.
- **E8:** P(wrong | grounding passes) = 0.67 — most errors occur when the reply looks well-grounded, consistent with the right page never being supplied and the model answering confidently from a plausible wrong one.

The remaining headroom is **evidence supply**, not reading. E9 should therefore trigger on *retrieval uncertainty*, not on output verification.

## 3. Architecture — no new components

The baseline is already `retrieve → read → verify`, and `Budget(max_calls, max_pages, max_usd)` already exists for this purpose. E9 adds one conditional edge and nothing else:

```
retrieve (ColQwen2, top 4) ──► read ──► verify ──► answer
      │
      └─ if trigger fires: retrieve pages 5–8 ──► read once more ──► keep better answer
```

- **No new dependency, no agent framework, no new module.** The policy lives in `notebooks/08_adaptive_evidence.ipynb` per the notebook-first rule, reusing the frozen `visualdoc` primitives read-only. `src/visualdoc` is **not** modified — its module hashes are pinned by the E8 specification, and changing them would be a new condition.
- Hard bound: **at most one extra read per question**, at most 8 pages total.

## 4. Hypothesis

> **H:** A retrieval-uncertainty trigger identifies questions whose annotated evidence is missing from the top 4 pages, and supplying pages 5–8 to a second read recovers answers that B1 gets wrong, without breaking answers B1 gets right.

Falsifiable sub-claims, tested in order:
- **H0 (free):** some retrieval signal predicts "evidence not fully supplied at k=4" materially better than chance.
- **H1 (paid):** the triggered arm beats frozen B1 on answerable accuracy.
- **H2 (paid):** the triggered arm beats a fixed-8-page arm — i.e. the *trigger* adds value, not merely more pages.

## 5. Method

### Stage 0 — trigger selection, offline, **$0**

Using the frozen E5 rankings and per-question evidence labels, evaluate candidate triggers against the known target "annotated evidence not fully supplied at k = 4":

- MaxSim margin between page 4 and page 5;
- absolute MaxSim of the top page;
- score mass concentration across the top 8;
- answer-side signals (abstention, numeric claim with no supported quote).

**Gate:** Stage 0 must show a trigger whose precision on "evidence missing" clearly exceeds the base rate, on a document-clustered split. **If none does, E9 stops here having cost $0**, and the conclusion — that current signals cannot tell when retrieval failed — is itself a reportable result.

### Stage 1 — technical smoke, ~6 calls, ≤ $0.02

Validate the 8-page request path only: schema accepted, one served model, token model reproduces observed prompt totals, cost within bound. Not scored.

### Stage 2 — full run

| Arm | Calls | Source |
|---|---|---|
| **B1** (control) | 0 | reuse the frozen E8 `L-B1` replies, verified by request-fingerprint parity |
| **A1** (triggered) | 1 per triggered question | second read with pages 5–8 added |
| **F8** (confound control) | 118 | fixed 8 pages, one shot |

Both paid arms run **twice**. E8 measured 7 correctness flips between identical replicates, so any single-run margin below ~7 questions is uninterpretable.

Scoring: S-v1 primary, S-v2 reported beside it, new gray items adjudicated blind as in E8. Documents are the unit of inference; 10,000 bootstrap draws.

## 6. Acceptance criteria (pre-registered, in verdict order)

| | Criterion |
|---|---|
| **Guardrails** | correct abstentions ≥ B1 − 2; citation validity ≥ B1 − 0.05; schema validity ≥ 0.99 |
| **Engineering** | answerable accuracy gain ≥ **+0.05** over frozen B1; broken ≤ fixed / 2 |
| **Statistical** | one-sided document-cluster bootstrap 5th percentile > 0; sign-flip p ≤ 0.05 |
| **Attribution** | A1 − F8 > 0; otherwise the verdict is `more_pages_not_triggering` |
| **Stability** | ≤ 10 correctness flips between replicates; the churn is reported either way |

Verdict order: guardrail fails → `regression`; Δ ≤ −0.05 → `regression`; Δ < +0.05 → `no_meaningful_gain`; broken > fixed/2 → `regression`; A1 ≤ F8 → `more_pages_not_triggering`; statistics hold → `adopt_adaptive_acquisition`; else `promising_but_uncertain`.

**Honest power note.** Full evidence is missing for ~40 of 101 questions, so the ceiling on repairs is real but modest, and +0.05 on 102 questions is ~5 questions — close to the 7-question replicate churn. A null result is a likely and acceptable outcome.

## 7. Estimated cost

From E8's measured profile: a 4-page B1 call averaged **3,977** prompt tokens and 47 completion tokens; prices $0.10/1M input, $0.50/1M output. An 8-page call is ≈ **7,900** prompt tokens.

| Item | Calls | Estimate |
|---|---:|---:|
| Stage 0 | 0 | **$0.00** |
| Stage 1 smoke | 6 | $0.01 |
| A1, 2 replicates (assuming a 40% trigger rate) | ~94 | $0.08 |
| F8, 2 replicates | 236 | $0.19 |
| **Total** | **~336** | **≈ $0.28** |

Proposed hard ceiling **$0.50**, cumulative, fail-closed, as in E8. For scale, E8's 354-call full run cost $0.144765 and E7's 1,309-call run cost $5.911057; per-experiment spend is recorded in `AGENTS.md` and in each frozen package.

Dropping F8 halves the cost to ~$0.09 but makes H2 untestable, so any gain could not be attributed to the trigger. I recommend keeping it.

## 8. How this serves the application

E9 is deliberately the smallest step that is also a product feature: a bounded retrieve-read-verify loop with an explicit call budget, which is what a practical document-intelligence app needs anyway. If Stage 0 fails, the application keeps B1 unchanged and gains a validated negative result instead of a speculative agent loop.

## 9. Prerequisite

Re-materialize the 11 macOS `dataless` PDFs in `data/external/mmlongbench_doc/documents/`, or re-download via notebook 00. The cached 768 px renders cover pages 1–N already rendered, but an 8-page arm may need pages never rendered before.
