# E10 proposal — an agentic document reader

**Status:** proposal only, for the owner's review. No specification is frozen, no notebook 10 exists, no paid call is authorised.
**Population (development):** the same 118 questions in 14 documents used by E6–E9. The MMLongBench-Doc test pool is used up and is not touched (`AGENTS.md`).
**Written:** 2026-11-27.

This proposal is also a learning document. Every design choice has three parts:
- **Decision**: what we do.
- **Why**: the evidence or reasoning behind it, preferably from this project's own frozen results.
- **Concept**: the general AI-engineering idea behind it, so you can recognise it in other systems and explain it in an interview.

---

## 1. The problem, measured

B1 reads ColQwen2's top 4 pages once. Its accuracy depends almost entirely on whether those 4 pages hold the evidence. Measured on E9's same-session B1 control (B1s, S-v1, 101 answerable questions with annotated evidence; computed from `experiments/frozen/e9/tables/evaluation_per_question.csv` and `experiments/frozen/e9_stage0/tables/stage0_per_question.csv`):

| Annotated evidence in B1's top 4 pages | Questions | B1 correct |
|---|---:|---:|
| all of it | 62 | **40 (65 %)** |
| only part or none | 39 | **4 (10 %)** |

| Evidence spans | Questions | B1 correct |
|---|---:|---:|
| 1 page | 55 | 35 (64 %) |
| 2–3 pages | 40 | 8 (20 %) |
| 4+ pages | 6 | 1 (17 %) |

The held-out evaluation shows the same pattern: 54 % → 31 % → 13 % (`experiments/frozen/final/README.md`).

**Why E9 did not solve this.** E9 read pages 5–8 *of the same ranking*. That ranking was built from one query, the user's question. But:
- 11 of the 101 questions have **no** evidence in the top 8 at all (E9 Stage 0). Reading deeper down the same list cannot find these.
- A question like "compare the 2019 revenue with the 2021 headcount" needs two different pages, each about a different thing. One query scores both halves together, and one half wins.

Of the 39 questions whose evidence is incomplete in the top 4, reading the top 8 completes only **8**. The other **31 stay incomplete** however far down the list E9 reads (`stage0_per_question.csv`, `complete_at_8`). E9 could therefore help at most 8 questions, and it gained about 2–3. Its held-out re-test (C3) gained +0.021. E10 targets the 31.

What can fix this is a different **query**, not a longer list. That is the one thing a fixed pipeline cannot do and an agent can.

> **Concept — "let the evidence choose the architecture".** Agents cost more, are slower and are harder to test than pipelines. A common industry mistake is to build an agent first. Here the decision follows a measured failure: the pipeline fails when evidence is spread out or hard to find with the original wording. That is exactly the case agents are good at. In an interview, this is the sentence that matters: *"I built the agent because my evaluation showed where the pipeline failed."*

---

## 2. Hypothesis

> **H:** A reader that can write its own search queries and choose which pages to look at, within a fixed budget, answers more answerable questions correctly than B1. The gain comes mostly from questions whose evidence is not in B1's top 4.

Falsifiable sub-claims:
- **H1 (outcome):** the agent (AG) beats a same-session B1 control (B1s) on S-v1 answerable accuracy.
- **H2 (mechanism):** the pages the agent *looked at* contain more annotated evidence than B1's top 4. This is evidence recall of the viewed set.
- **H3 (where):** the gain is concentrated in the 39 "evidence incomplete at 4" questions and the multi-page questions. It is not a general shift.

If H1 holds but H2 does not, the gain has another cause (for example, the agent's different prompt), and we must say so. Checking the mechanism, not just the score, is what separates an experiment from a demo.

> **Concept — outcome metrics vs process metrics.** For agents, the final answer is not enough. You also measure *what the agent did* (its trajectory): which tools it called, which pages it found, where it wasted steps. This project has page-level evidence annotations, so it can measure the process directly. Most agent demos cannot.

---

## 3. Design decisions

### 3.1 Tools: three, no more

| Tool | Arguments | Returns |
|---|---|---|
| `search_pages` | `query: str`, `k: int (1–8)` | page numbers and their MaxSim scores, from ColQwen2 over the whole document; no images |
| `read_pages` | `pages: list[int]` (≤ 4 per call) | the 768-px page images, each tagged `[Page N]`, exactly as B1 presents them |
| `finish` | B1's schema: `answer`, `cited_pages`, `evidence[{page, quote}]` | ends the episode |

**Why separate "search" from "read".** Search is cheap: a list of numbers, almost no tokens. Reading is expensive: about 920–1,237 prompt tokens per page for `gpt-6-luna` (E8 smoke). Splitting them lets the agent look at the result list, run a second search and then pay to read only the pages it chose. This is the agentic version of E9's lesson that more pages are not automatically better.

**Why no `zoom` and no `calculate` in v1.** Both are plausible:
- `zoom` would target the visual-reading errors seen in E0 and E4.
- `calculate` would target aggregation errors.

But E7 is the warning. It bundled four changes (page-wise reading, structured memory, text-only reasoning and an arithmetic tool), regressed, and could not say which change caused it. One factor per experiment. `zoom` and `calculate` are the obvious E11 candidates once we know what the search tool alone does.

**Why `finish` is a tool with B1's exact schema.**
- The agent's answer goes through the **same** parser, citation check, grounding check and S-v1/S-v2 scorers as B1. AG and B1s are then compared on identical terms.
- A structured "final answer" tool is the standard way to end an agent loop cleanly. The model cannot "half finish" in free text.

> **Concept — tool design is interface design.** A tool's name, description, argument schema and return format are a prompt the model reads at every step. Good tools are few, do one thing each and return just what the model needs to decide its next step. Search returning numbers, not images, is an example. Most agent failures in practice are bad tool interfaces, not bad models.

### 3.2 Warm start: the agent begins where B1 ends

**Decision.** The first message already contains B1's top 4 pages, exactly the pages B1 reads. The agent may answer at once with `finish`, or search for more.

**Why.**
1. **No loss of information by construction.** The agent always sees at least what B1 sees. If it does worse, the cause is its behaviour (a bad search, being distracted by extra pages, a wrong stop), not missing pages. That keeps the result interpretable.
2. **Cheap on easy questions.** On the 62 questions where the top 4 were complete, a good agent finishes in one call, at about B1's cost.
3. **The step count becomes a signal.** How often the agent stops at step 1, and whether those answers are right, tells us whether it knows when it already has enough evidence.

The alternative, a **cold start** (the agent starts with only the question and must search first), is a fair design too. It mixes two questions, though: "can it search?" and "can it match B1's first retrieval?". It is a possible later ablation.

> **Concept — baselines inside the treatment.** A good design makes the new system a *superset* of the old one wherever possible. Then a regression can only come from the new part. The same idea appears in production as "fallback to the old path" and in research as a nested comparison.

### 3.3 Budget and stopping rules

| Limit | Value | Enforced by |
|---|---|---|
| model calls per question | ≤ 6 | the loop |
| distinct pages read per question | ≤ 12 (B1 reads 4) | `read_pages` refuses beyond it, and says so |
| pages per `read_pages` call | ≤ 4 | the tool schema |
| cost per question | ≤ $0.02, checked **before** each call | the existing `check_profiled_request` |
| last call | forced `finish` (`tool_choice` set to `finish`) | the loop |

**Why hard limits.** An agent's cost is not fixed: it depends on what the model decides. Without limits, one confused episode can loop, rereading pages and repeating searches, and cost more than a hundred normal ones. This project already refuses a call before it is sent if its worst-case cost would exceed a ceiling. The agent keeps that rule at every step.

**Why tell the model its remaining budget.** Each tool result ends with `"Budget left: N calls, M pages."`. A model that knows its budget can plan: search first, then read the best pages. A model that does not know it may spend everything on the first idea.

**Why force `finish` at the last step instead of abstaining.** If the budget runs out, the agent must give its best answer from what it has read (or "Not answerable"). Silently returning nothing would count as a wrong answer for a reason that is not about reading, and it would make AG look worse than it is.

**Guards against loops.**
- A repeated identical query returns `"Already searched; results above."` and still costs a step.
- Reading a page already read returns `"Page N is already in view."`.
- A malformed tool call returns its validation error to the model, and costs a step.

These are common failure modes, and logging them is part of the result.

> **Concept — bounded autonomy.** Production agents almost always run inside explicit limits on steps, tokens, money and time, with a defined fallback when a limit is hit. "How do you stop your agent from running forever or spending too much?" is a standard interview question. The answer is these limits plus the pre-call cost check.

### 3.4 Context grows at every step

Each call re-sends the whole conversation: the instructions, the question, every tool result and every page image read so far. With 12 pages at up to 1,237 tokens each, the last call can carry about 15,000 image tokens, and the episode pays for them again at every call.

**Decisions.**
- Keep the 12-page cap. At most about 18,000 prompt tokens per call, well inside the 128k context.
- Do **not** summarise or drop earlier pages in v1. Summarising pages into text is what E7 did, and it lost visual information (signatures, colours, chart counts). Dropping pages would make citations unverifiable.
- Record cached prompt tokens separately. E9 found that provider prompt caching was active on repeated prefixes. A multi-turn agent repeats its prefix at every call, so caching will lower the observed cost. We report both the cached and the list-price figures.

> **Concept — context management and prompt caching.** In multi-turn agents, cost grows faster than the number of steps, because each step re-sends everything before it. The standard tools are caps, summarisation, retrieval over memory and provider caching. Each has a cost. Here the project's own E7 result tells us summarisation is the risky one.

### 3.5 Same reader, same pages, same scorer

**Decision.** AG uses `gpt-6-luna` with B1's settings (temperature 0, `reasoning_effort: none`, 768-px images, strict schema on `finish`). The **only** differences from B1 are the tools, the loop and an agent system prompt.

**Why.** If the agent also used a stronger model or a reasoning mode, any gain could come from the model, not the agent. One factor per experiment, as in every experiment since E1.

`reasoning_effort` above `none` is a natural follow-up. It is a separate factor and is tested separately.

### 3.6 No agent framework, a visible loop

**Decision.** Write the loop by hand, about 150 lines, in notebook 10:
1. call the model;
2. if it called a tool, run the tool and append the result;
3. repeat until `finish` or the budget runs out.

No LangGraph, no OpenAI Agents SDK.

**Why.**
1. **Learning.** Frameworks hide the exact things you need to understand: how tool calls are encoded in messages, how results go back, where the cost comes from. Once you have written the loop yourself, any framework is easy to pick up, and you can debug it when it misbehaves.
2. **Reproducibility.** Every request in this project is fingerprinted and checked against frozen bytes. A framework adds its own hidden prompts, retries and message rewriting, which would break that.
3. **Project rules.** `AGENTS.md` puts experimental code in notebooks, visibly, and requires the owner's approval for a new application framework.

If E10 succeeds, moving the loop into the application (`src/visualdoc/agent.py`) is a separate step that needs your approval. That is the moment to reconsider a framework, for example for streaming or tracing.

> **Concept — the agent loop.** Under every agent framework is the same loop: *model → tool call → tool result → model …*. It is often called ReAct-style (Yao et al., 2022, "ReAct: Synergizing Reasoning and Acting in Language Models"). Anthropic's essay "Building effective agents" (December 2024) makes the same point as this section: start with simple, composable code and add frameworks only when needed.

### 3.7 Searching with new queries means encoding queries live

B1's offline mode works only because E5 cached a ColQwen2 embedding for every benchmark question. The agent writes **new** queries, so they must be encoded at run time.

**What this needs.**
1. Download the pinned ColQwen2 weights (4.4 GB, revision `ddc07d23`). They are not on the Datalab yet: only the 14 MB of small files are.
2. Encode on the CPU, in `.venv` (torch 2.15.0+cpu, the pinned version).
   - A query is short (≈ 20–40 tokens), so CPU encoding takes about a second.
   - Page embeddings are **not** recomputed. The 14 documents' pages come from E5's frozen cache.
3. **A parity gate before any paid call.** Re-encode the 118 original questions on the CPU and check that the resulting rankings match E5's frozen rankings. That is the same test the final evaluation ran (118/118 equal). If they differ, CPU encoding is a new condition: it is recorded and fixed before going further.

> **Concept — parity gates.** Whenever you change *where* or *how* something runs (CPU vs GPU, a new library version, a new machine), first prove it reproduces the old results on known inputs. This project has already met this problem: x86 OCR differs from the M1's. A parity gate is the cheap test that stops a silent change from corrupting an expensive experiment.

### 3.8 Testing the agent without paying

Before any paid call, the loop is tested offline with a **scripted fake model**: a function that returns pre-written tool calls (search, read, then finish; or loop forever; or send a malformed argument). The tests check that budgets stop the loop, that guards fire, that the forced `finish` happens, that costs add up and that the trajectory log is complete.

These are interface tests only. Following `AGENTS.md`, nothing a fake model returns is ever reported as a result.

> **Concept — deterministic tests for non-deterministic systems.** You cannot unit-test what an LLM will say. You *can* test everything around it (the loop, limits, parsing, logging) by replacing the model with a script. This is how production agent code is tested, and it is a skill interviewers look for.

---

## 4. Evaluation

### 4.1 Arms (one session, adjacent and counterbalanced, as in E8 and E9)

| Arm | What | Calls |
|---|---|---|
| **B1s** | B1, requests byte-identical to frozen E8 L-B1 (same-session control) | 118 |
| **AGa** | the agent, replicate a | ≤ 6 × 118 |
| **AGb** | the agent, replicate b | ≤ 6 × 118 |

**Why a same-session control and two replicates.** `gpt-6-luna` is an alias with no fixed snapshot, and E8/E9 measured how much it varies:
- 4–7 questions flip between identical runs;
- B1 scored 44 in one session and 46 in another on byte-identical requests.

A gain smaller than that variation means nothing. Two agent replicates let us compare the gain with the agent's own variation.

### 4.2 Metrics

**Primary:** AG − B1s, S-v1 answerable accuracy, averaged over both replicates. Statistics as in every experiment since E6: a document-cluster bootstrap 95 % interval and an exact document sign-flip test.

**Secondary (H2, H3 and costs):**
- evidence recall of the pages viewed (AG) vs the 4 pages read (B1s);
- accuracy split by "evidence complete at 4: yes/no" and by the number of evidence pages;
- correct abstentions (16 unanswerable questions), citation validity, schema validity;
- per question: calls, pages read, searches, prompt tokens (cached and uncached), cost, latency;
- trajectory statistics: how often it stops at step 1, repeated queries, budget exhaustions, forced finishes.

**Qualitative:** read 20 trajectories by hand, sampled with a fixed seed from fixed, broken and still-wrong questions, and classify the failures. Typical classes: bad query, found the page but misread it, stopped too early, distracted by extra pages.

> **Concept — error analysis.** The numbers tell you *whether* the agent helps. Reading trajectories tells you *why*, and gives you the next experiment. Teams that ship good agents spend a lot of time reading traces.

### 4.3 Decision rule (to freeze in the specification)

E10 is a **development** experiment. Its verdict decides whether to build and confirm the agent, not whether the agent "works" in general.

- `go`, all of:
  - Δ ≥ +0.05 on average and in each replicate;
  - broken ≤ fixed / 2;
  - H2 holds (higher evidence recall of the viewed pages);
  - correct abstentions ≥ B1s − 2;
  - citation validity ≥ 0.99;
  - mean cost ≤ $0.01 per question.
- `no_gain` otherwise. It is reported like E7 and E9, with the trajectory analysis that says why.

**What this sample can detect.** The 39 "incomplete" questions are where the gain must come from, and B1 gets 4 of them right.
- **Ceiling:** if the agent made every one of them complete and then answered at the "complete" rate (65 %), it would gain about +21 questions (≈ +0.20).
- **Detection floor:** an honest gain of 3–5 questions (+0.03 to +0.05) is within replicate noise and **cannot** be told apart from it on 102 questions.

That is why a `go` here leads to a confirmatory test on new data, not a claim.

### 4.4 Confirmation on new data (Stage 5, only after a `go`)

The development questions have shaped every design since E5, so they cannot confirm anything. Confirmation needs a new benchmark with:
- long PDF documents;
- questions whose evidence spans several pages;
- page-level evidence annotations.

LongDocURL and SlideVQA are candidates to check. Their licence, size, annotation quality and overlap with ColQwen2's training data must be verified first. The benchmark is chosen and the protocol frozen **before** any of its documents is read, exactly as for the final evaluation.

---

## 5. Cost

Upper bound per agent question: 6 calls × (≤ 12 images × 1,237 tokens + ≤ 3,000 text tokens) ≈ 107,000 prompt tokens, plus 6 × 800 output tokens. At `LUNA_PROFILE` list prices ($0.10 / $0.50 per million) that is about **$0.013 per question**.

| | Upper bound | Rough expectation |
|---|---:|---:|
| smoke (6 questions, AG only) | $0.08 | < $0.02 |
| full: B1s (118) + AGa + AGb (236) | ≈ $3.15 | $0.4–$1.0 (most episodes should stop after 1–3 calls; prompt caching lowers it further) |

For comparison, B1 costs about $0.0004 per question observed (E9 B1s). An agent that is about 3–10× more expensive per question for a clear accuracy gain is a normal trade-off; the evaluation reports it explicitly. The ceiling to request at specification time is **$3.50**.

---

## 6. Plan of work

Each stage ends with something you can check, and with the "why" written down before moving on.

| Stage | What | Paid? | What you learn |
|---|---|---|---|
| 0 | Download the ColQwen2 weights; encode queries live on the CPU; parity gate vs E5 rankings (118/118) | no | running a retrieval model yourself; parity gates |
| 1 | Tools (`search_pages`, `read_pages`, `finish`) over the 14 documents, offline; inspect searches by hand: does a reworded query find a missing evidence page? | no | dense multi-vector retrieval (MaxSim), query reformulation |
| 2 | The agent loop with a scripted fake model; tests for budgets, guards, forced finish, logging | no | the agent loop, tool-call message format, deterministic testing |
| 3 | Freeze the specification (`experiments/specs/e10_agentic_reader_v1.json`), then a 6-question smoke: tool calls with images accepted? token model still exact over several turns? caching reported? | ≈ $0.02 | pre-registration; measuring an API instead of trusting documentation |
| 4 | Full development run, evaluation, independent audit, frozen package; trajectory review | ≤ $3.50 | agent evaluation, outcome vs process, error analysis |
| 5 | Only after a `go`: new benchmark, frozen protocol, confirmatory run | later | out-of-sample confirmation |
| 6 | Only after a `go` and with your approval: `src/visualdoc/agent.py`, CLI/web option, then service, tracing and MCP | later | production engineering |

**An open question to answer at Stage 3, not to assume.** The Chat Completions API traditionally accepts only text in a `tool` message. The plan is therefore:
1. return `read_pages` results as a short `tool` message ("Pages 7 and 12 attached");
2. follow it with a `user` message that holds the images.

The smoke checks that `gpt-6-luna` accepts this, and that its token counts still follow the E8 model. If not, the design changes *before* the full run, and the change is recorded.

---

## 7. What this experiment does not change

- B1 stays the shipped system unless and until a confirmed result says otherwise.
- `src/visualdoc/` is not modified: the five baseline modules are hash-pinned by the E8 specification. The agent lives in notebook 10 until Stage 6.
- No frozen file is edited. New runs go to `experiments/runs/`, and the frozen package to `experiments/frozen/e10/`.
- No paid call without the owner's explicit approval of each paid stage.
