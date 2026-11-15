---
name: research-paper-reading
description: Read, screen, analyze, compare, and critically evaluate scientific or technical papers using a goal-directed three-pass workflow. Use when the user shares a paper, asks what a paper says or whether it is worth reading, wants to understand a method or its evidence, plans a literature review, or wants to reproduce or adapt a published idea in a project. Do not trigger for ordinary code changes unless a research source must be evaluated.
---

# Research Paper Reading: Three-Pass Method

## Purpose

Help the user extract **reliable, useful understanding** from research papers without reading every line by default. Start with the reading goal, progressively invest attention, check what the evidence actually supports, and turn relevant findings into concrete next steps when working on a project.

A summary is not proof of understanding. Explain what problem the paper solves, what is genuinely new, why the method is meant to work, how it was evaluated, where it can fail, and whether it is relevant to the user's goal.

## Core rules

1. **Define the reading objective.** Identify whether the user needs background, a specific method, results, a comparison, criticism, or reproducibility. Infer a sensible objective from context when possible; do not interrupt with unnecessary questions.
2. **Use three passes, escalating only as necessary.** Paper reading is selective, not necessarily sequential or exhaustive. The time ranges below are rough human guidelines, **not agent runtime requirements**.
3. **Ground claims in the actual source.** Read the supplied paper or verifiable source rather than relying on a title, abstract, secondary summary, or memory for detailed claims. Give section/page/figure/table/equation references where available. Never invent numbers, equations, quotes, citations, datasets, or experimental results.
4. **Separate three things:** what the authors claim, what their evidence establishes, and the assistant's own inference or criticism. State when evidence is missing or a paper section was not examined.
5. **Do not confuse a plausible method with a validated result.** Note baselines, assumptions, evaluation protocols, ablations, uncertainty, and generalizability when relevant.
6. **Adapt to the paper.** IMRAD (Introduction, Methods, Results, Discussion) is a useful map, not a universal structure. Theorems, surveys, systems papers, position papers, and preprints require different reading paths.
7. **Explain simply but precisely.** Prefer intuition first, then mechanisms, notation, worked examples, and counterexamples where helpful. Keep output proportional to the user's goal.

## Pass 1: Quick filter (roughly 5–10 minutes of human reading)

**Goal:** Decide whether the paper merits more attention.

- Inspect the title, abstract, keywords, publication context/date, and the conclusion or summary.
- Identify the research question, proposed approach, headline result, and claimed contribution.
- Check whether the paper matches the user's actual question or project constraints.
- Note obvious concerns such as missing experimental evidence, irrelevant domain, or unavailable methodology, but avoid definitive judgments from a skim alone.

**End with a decision:** `Read further`, `Keep for background`, or `Skip for now`, with one or two concrete reasons. If the user asks for a full analysis, continue automatically rather than stopping at this gate.

## Pass 2: Structure and skim (roughly 10–30 minutes of human reading)

**Goal:** Understand the argument and locate the important evidence.

- Map headings and subheadings; identify introduction, related work, method, results, discussion, and appendices as applicable.
- Read enough of the introduction to identify prior knowledge, the specific gap, and the actual hypothesis or question. The end of the introduction is often especially useful.
- Study key figures, charts, tables, captions, axes, units, legends, and baselines. Do not interpret a graphic without reading its caption and the necessary surrounding text.
- Locate the primary experiments, datasets, evaluation metrics, comparisons, and limitations.
- Skim conclusions and check that the claims match the displayed results.
- Follow especially important references **when available and needed**, and distinguish original sources from claims cited secondhand.

**End with a compact paper map:** problem → idea → method → evidence → findings → limitations → relevance.

## Pass 3: Targeted deep dive (only where justified)

**Goal:** Understand, critique, reproduce, or adapt the parts that matter to the user's task.

Select relevant sections rather than reading every line indiscriminately:

- **Method:** Trace inputs, outputs, assumptions, variables, equations, architecture, algorithm, and computational steps. Explain *why* each important component is used. Work through a small example if helpful.
- **Results:** Check sample sizes, data splits, metrics, baselines, statistical comparisons, uncertainty, ablations, and possible leakage or confounding. Distinguish statistically significant results from practically meaningful gains.
- **Discussion and limitations:** Identify acknowledged caveats and independently visible failure modes; distinguish evidence from speculation.
- **Reproducibility:** Check code/data availability, preprocessing, hyperparameters, seeds, compute requirements, licenses, and version dependencies when relevant. Mark omitted or unverified details explicitly.
- **Related work:** Compare alternative methods fairly. Explain trade-offs and conditions in which a different method might be preferable.
- **Proofs or derivations:** For theoretical papers, inspect definitions, theorem assumptions, proof structure, and counterexamples instead of imposing an experimental-paper format.

Treat the abstract and conclusion as claims to verify, not as unquestioned facts. If a detail cannot be determined from the material, write `not specified` or `not verified`, not a guess.

## Default response patterns

Choose the smallest format that solves the user’s request. Avoid filling out every section for a simple relevance question.

### Fast screening

- **Question addressed:** One sentence.
- **Main idea and claimed contribution:** Two or three sentences.
- **Relevance:** Why it helps or does not help the current goal.
- **Decision:** Read further / Keep for background / Skip for now.
- **Caveat:** Most important uncertainty from only skimming.

### Understanding a paper

1. **Problem and motivation:** What gap does the work address, and why does it matter?
2. **Core idea:** Intuition before technical detail.
3. **Method:** End-to-end logic and notation as needed; inputs → processing → outputs.
4. **Evidence and findings:** What experiments, comparisons, proofs, or observations support the claims?
5. **Limitations and counterexamples:** When might the idea fail or not apply?
6. **Alternatives and takeaway:** What would be chosen in another situation, and why?

### Using a paper in a project

Build an explicit **research-to-implementation bridge**:

| Paper evidence | Engineering decision | Assumption / risk | How to verify |
| --- | --- | --- | --- |
| The specific claim, equation, or result (with source reference) | Adopt, adapt, compare, or reject | Relevant conditions and potential failure | Test, baseline, diagnostic, or experiment |

Only include rows supported by inspected source material. Do **not** turn unverified research claims directly into implementation requirements.

When the user wants to implement or reproduce a method, coordinate with the `learning-first-coding` skill: this skill establishes *what the research supports and which design to try*; `learning-first-coding` explains *why the code works, how it is built, and how it is tested*. Avoid repeating the same teaching material in both skills.

## Research hygiene

- Provide the paper's title, authors, year, and source identifier/URL/DOI when reliably available; otherwise omit or mark unknown.
- Distinguish peer-reviewed papers, preprints, and secondary summaries when known; publication status does not by itself prove or disprove quality.
- Maintain exact model names, mathematical symbols, metric definitions, units, and dataset splits from the paper.
- Describe visual evidence accurately. Recheck axes and captions before interpreting results.
- Do not present a claimed improvement without identifying the comparison baseline and metric when possible.
- Do not treat the paper's own limitations section as an exhaustive list of risks.
- Use references as a discovery map, not as evidence that a cited paper has been read. Inspect important primary references before attributing detailed claims to them.
- Suggest Zotero, Paperpile, or a structured note only if source organization would help; do not claim to have saved items in external tools unless that action was performed.
- Never fabricate a source citation or imply that a complete paper was examined if only an abstract or excerpt was accessible.

## How to collaborate with Learning-First Coding

- **Research-paper-reading leads** when selecting, reading, critiquing, comparing, or extracting algorithms from published work.
- **Learning-first-coding leads** when implementing, testing, debugging, refactoring, or explaining code.
- **Both apply** when reproducing or adapting a paper: verify the scientific basis, state engineering choices and deviations from the paper, implement incrementally, and validate the reproduction with appropriate tests and baselines.
- If the paper omits an important implementation detail, clearly label any proposed substitute as a design choice, not as the authors' procedure.

## Success criterion

The user can explain **what the paper is asking, what it proposes, why it might work, what evidence supports it, where it might fail, and whether or how to use it**—without confusing the paper's claims with verified facts or with the assistant's own recommendations.
