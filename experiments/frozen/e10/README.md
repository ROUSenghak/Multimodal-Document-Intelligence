# E10: an agentic document reader (development data)

This package is the immutable E10 execution: two smoke runs, the full run, the evaluation tables, the blind S-v2 queue and an independent audit.

**Population.** The 118 development questions of E6–E9 (102 answerable, 16 unanswerable) in 14 documents. The test pool was not read or run.

## Question and design

Can a reader that writes its own search queries and chooses which pages to read, under a fixed budget, beat B1? B1 reads ColQwen2's top 4 pages once.

- **Pre-registration.**
  - Specification: `experiments/specs/e10_agentic_reader_v1.json`, commit `25cd488`, before any paid call.
  - Design and reasoning: `docs/e10_agentic_reader_proposal.md`.
  - Notebook: `notebooks/10_agentic_reader.ipynb`.
- **Arms.** Run in one session, in 118 seeded blocks with the six arm orders balanced:
  - **B1s:** requests byte-identical to frozen E8 L-B1;
  - **AGa** and **AGb:** two agent replicates.
- **Agent.**
  - It starts with B1's exact top 4 pages.
  - Tools: `search_pages(query)` (ColQwen2 over all pages, numbers only), `read_pages(pages ≤ 4)` and `finish` (B1's strict schema).
  - Limits: ≤ 6 calls, ≤ 12 distinct pages, a pre-call cost check, `tool_choice: required`, finish forced on the last call.
  - Same reader and settings as B1.
- **New condition.** Agent queries are encoded on the Datalab CPU; E5 used Apple MPS. The parity gate passed before the spec was frozen: top-4 set equal for 113/118 questions, recall@4 0.723 vs 0.726 (`tables/stage0_parity.csv`). Page embeddings are E5's.

## Results

Frozen package `experiments/frozen/e10/`. Independent audit `AUDIT.json`: 31/31 checks.

**Run.** 354 items, 899 calls, all first-attempt successes on one served model (`gpt-6-luna`). Spend:
- full run: $0.455862;
- smoke: $0.017513, including the $0.0011 charged for a locally failed first attempt;
- total: **$0.473** of the $3.50 ceiling.

| S-v1, 118 questions | B1s | AGa | AGb |
|---|---:|---:|---:|
| correct / 102 answerable | 45 | **53** | **53** |
| correct abstentions / 16 | 8 | 9 | 12 |
| citation validity, schema validity | 1.000, 1.000 | 1.000, 1.000 | 1.000, 1.000 |
| evidence recall of pages seen (101) | 0.726 | **0.868** | **0.864** |
| evidence complete in pages seen (101) | 62 | 77 | 78 |
| calls / pages seen per question | 1 / 4 | 3.35 / 6.75 | 3.27 / 6.81 |
| cost per question, latency p50 / p90 | $0.0004, 2.3 / 3.9 s | $0.0018, 5.4 / 17.3 s | $0.0017, 5.7 / 14.9 s |

**Primary contrast:**
- AG − B1s = **+0.078** (+8 questions), 95 % interval [0.000, +0.181], bootstrap 5th percentile +0.010, exact sign-flip p = 0.053.
- Fixed / broken: AGa 13 / 5, AGb 17 / 9.
- AGa and AGb disagree on 12 questions.

**Frozen verdict: `regression`.** The pre-registered rule "broken > fixed / 2 in either replicate" fires on AGb (9 > 8.5). Without that rule the verdict would still not be `go`: p = 0.053 > 0.05 and 12 flips > 10. So the outcome would be `promising_but_uncertain`. The verdict is reported as frozen, and the name of the rule should not be read as "the agent is worse". The agent is **+8 questions net in both replicates**.

**Mechanism and location (H2, H3): both strongly supported.**
- **H2.** Evidence recall of the pages seen rose by +0.140 [+0.084, +0.198], sign-flip p = 0.0002.
- **H3, where the evidence was incomplete in B1's top 4** (39 questions): +0.256 [+0.136, +0.500], p = 0.001. 9 of AGa's 13 fixes and 11 of AGb's 17 are there.
- **H3, everywhere else:** −0.032 [−0.129, +0.085]. **Every broken question had its evidence complete in B1's top 4.**

**Why it breaks questions (all 5 questions broken in both replicates, read by hand):**
1. **Over-exploration** (mmlb-0048, mmlb-0599). The answer was already in view, but the agent searched and read 7–8 more pages, then miscounted or added colours from other pages.
2. **A different reading of the same 4 pages** (mmlb-0201, mmlb-1014). No new page was read, yet the answer changed. The agent's prompt and tool-call mode alter the reading itself, a confound the warm start cannot remove.
3. **Answer format** (mmlb-1025: "1,358,000 shares" instead of 1358000). S-v1 scores the text form wrong. This is a scoring artefact more than an error.

**Why it fixes questions** (5 sampled from the 11 fixed in both replicates). The agent wrote targeted queries and found pages ColQwen2 had ranked low for the original question. For example:
- "income tax provision … effective tax rate reconciliation" found pages 64 and 38 (mmlb-1055);
- "student cannot be found … whom to contact" found page 25 (mmlb-0990).

**Exploratory, not pre-registered:**
- **The agent's own stopping decision is a usable router.** 29 % of agent episodes finished at call 1 and were 76 % correct, against 41 % for the episodes that searched.
- **E9's U3 trigger is a worse router.** Using the agent only where U3 fires gives 46 (AGa) and 49 (AGb) of 102, below always running the agent (53).

**Session drift.** B1s scored 45, against 46 for frozen E8 L-B1 and 44 for frozen E9 B1s: 5 flips each, on byte-identical requests.

**S-v2 (secondary).** 17 new blind gray items await the owner's labels (`adjudication/blind_queue_unlabelled.csv`). Bounds while they are pending: AG − B1s from +0.045 (all counted wrong) to +0.104 (all counted correct).

**What this means.** Searching works: it finds the missing evidence and turns it into answers, concentrated where B1 fails. The cost is a smaller loss on questions B1 already answers, from over-exploration and from the change of reading mode. The next experiment should keep the search and remove that loss. Options:
- stop when the warm-start pages suffice: a stricter finish-first instruction, or the B1 answer as a fallback;
- read in B1's mode for the final answer.

It should be tested on a new benchmark, since these 118 questions are development data.

## Records found during execution (recorded, not hidden)

- **Two gate failures before any request reached the API.**
  - The first smoke attempt stopped on a wrong key path in the paid gate (fixed in `3e276e1`).
  - The second stopped on the Datalab's empty `OPENAI_BASE_URL` (fixed in `9cfc267`). Its single call failed locally and is charged at its $0.0011 upper bound (`smoke_20261127T102703Z_df4eb49e`).
- **Token accounting.** The agent's pre-call bound was never below a billed prompt, and the largest billed/bound ratio is 1.0. The exact-text estimate falls short by a median of 262 tokens (maximum 354): the tool definitions, which are not in the E8 token model. B1s prompt totals are exact.
- **Caching.** Provider prompt caching was active on agent calls (about 24 % of prompt tokens cached). Costs use billed usage.
- **The audit's first pass** reported 30/31: the audit script counted 2 unanswerable questions with annotated pages in the evidence population. It was corrected to the spec's 101 answerable questions. The notebook was right; now 31/31.

## Files

| Path | Content |
|---|---|
| `full_20261127T103158Z_3049dc6c/` | `settings.json` (plan, spec, contract, notebook-code and encoder hashes), `calls.jsonl` (899 calls), `items.jsonl` (354 items with trajectories), `summary.json` |
| `smoke_*` | the 6-episode smoke (`…9460aea6`) and the locally failed attempt (`…df4eb49e`) |
| `tables/` | `evaluation_per_question.csv`, `evaluation_summary.json`, `stage0_parity.csv`, `plan_identity.json` |
| `adjudication/` | `blind_queue_unlabelled.csv` (17 items for the owner) and `sealed_key.csv` |
| `audit/audit_e10.py`, `AUDIT.json` | the independent audit (no API, no torch, no notebook import) and its 31 checks |

Re-run the audit: `.venv/bin/python experiments/frozen/e10/audit/audit_e10.py . experiments/frozen/e10`.
