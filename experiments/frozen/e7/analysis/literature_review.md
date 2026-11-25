# Literature review for the post-E7 stage (written 2026-11-24, independent of E7 results)

Scope: multi-page document QA, visual RAG / late interaction, structured extraction, evidence sufficiency,
adaptive page selection, region-level reading, training-free agentic systems, inference cost.

**Verification levels**
- **[full]:** a full-text read of the paper's HTML, with tables quoted.
- **[partial]:** a full-text read of only part of the paper; items marked "summary" came from a model-extracted summary.
- **[abstract]:** only the abstract, listing or search snippets were checked.

Numbers are the authors' own claims unless noted. No result here has been reproduced on our setup.

**Our setup, for compatibility notes**
- **Retrieval:** ColQwen2 page embeddings, cached as bf16 safetensors in `data/cache/e5`.
- **Reader:** GPT-4o-mini-2024-07-18, reading 768-px page images.
  - Each page costs 25,501 prompt tokens.
  - The context guard therefore allows only 3–4 pages per call.
  - The snapshot is scheduled to shut down on 2027-01-14.
- **Development data:** 14 documents and 118 questions, of which 102 are answerable.
- **No local GPU is assumed.**

## A. Reference point

| Work | Key facts |
|---|---|
| **MMLongBench-Doc**: Ma et al., NeurIPS 2024 Datasets and Benchmarks (spotlight). [arXiv 2407.01523](https://arxiv.org/abs/2407.01523), [code](https://github.com/mayubo2333/MMLongBench-Doc) [abstract] | 1,082 questions over 135 PDFs averaging 47.5 pages. Best model in the paper: GPT-4o, F1 44.9 in the NeurIPS version (42.7 in arXiv v1). |

Later papers re-run the benchmark with different judges: SimpleDoc uses a GPT-4.1 judge, DocLens its own protocol, and ViSAR a Qwen2.5-14B judge. So their absolute numbers are **not comparable** with each other or with our rule-based scorer (the notebook 03 scorer).

## B. Visual retrieval (late interaction)

| Method | Mechanism | Training | Evidence | Fit with our pipeline | Failure mode it addresses |
|---|---|---|---|---|---|
| **ColPali**: Faysse et al., ICLR 2025. [arXiv 2407.01449](https://arxiv.org/abs/2407.01449) [abstract] | Page screenshot to patch multi-vectors, then MaxSim late interaction. | Trained retriever (we use the released ColQwen2). | ViDoRe benchmark; large gains over OCR + BM25 pipelines. | Already adopted in E5/E6, where it raised recall by 0.195 and accuracy from 25 to 38 of 102. | Retrieval |
| **VisRAG**: Yu et al., ICLR 2025. [arXiv 2410.10594](https://arxiv.org/abs/2410.10594) [abstract] | VLM retriever plus VLM generator over page images. | Trained retriever. | 20–40 % end-to-end gain over text RAG on their benchmarks. | Same paradigm as E6; no new mechanism for us. | — |
| **M3DocRAG**: Cho et al., 2024 (ICCVW 2025). [arXiv 2411.04952](https://arxiv.org/abs/2411.04952) [abstract] | ColPali plus Qwen2-VL, single- or multi-document. | None beyond the released models. | Reports on MMLongBench-Doc and MP-DocVQA. | **This is essentially our E6 V arm.** | — |
| **VDocRAG**: Tanaka et al., CVPR 2025. [arXiv 2504.09795](https://arxiv.org/abs/2504.09795) [abstract] | Unified image-based retriever and generator, self-supervised pre-training. | Yes | OpenDocVQA | Needs training; **not compatible** with a training-free scope. | — |
| **Light-ColPali / ColQwen2**: Ma et al., Findings of ACL 2025. [arXiv 2506.04997](https://arxiv.org/abs/2506.04997) [abstract] | Merges patch embeddings after the projector, by semantic clustering. | Light fine-tuning. | Keeps 98.2 % of retrieval quality at 11.8 % of the memory. | Application-phase storage optimisation only; does not address accuracy. | Index cost |

## C. Training-free or light agentic multi-page systems

**SimpleDoc**: Jain, Wu, Zeng, Liu, Dai, Shao, Wu, Wang. EMNLP 2025. [arXiv 2506.14035](https://arxiv.org/abs/2506.14035), [code](https://github.com/ag2ai/SimpleDoc) [partial]
- **Mechanism:**
  - Offline, each page gets a 3–5-sentence summary written by a VLM, without knowing any question.
  - At query time, ColQwen2.5 retrieves the top-k pages. A *text-only* LLM then reads the k summaries, keeps and orders a subset (about 3.2–3.5 pages), and writes a document-level note.
  - A VLM reasoner reads those pages and returns either an answer, "not answerable", or an updated query. The loop runs for at most L iterations.
- **Training:** none.
- **Models:** Qwen2.5-VL-32B (summaries and reasoner) and Qwen3-30B-A3B (page selection).
- **MMLongBench results (GPT-4.1 judge, ColQwen-2.5 retrieval):**

| System | Accuracy | Pages read |
|---|---|---|
| M3DocRAG top-2 | 41.8 | 2 |
| MDocAgent top-6 | 55.3 | 12 |
| SimpleDoc | 59.55–60.58 | 3.2–3.5 |
| Ground-truth pages | 67.94 | — |

- **Ablation on top-k for the candidate pool:** k = 2 → 56.66, k = 6 → 58.25, k = 10 → 59.55, k = 30 → 60.58.
- **Page selection quality:** whether *all* evidence pages are kept rises from 64.1 % (ColQwen top-2) to 67.4 % (SimpleDoc, 3.46 pages). Page-level F1 rises from 38.8 to 62.2.
- **Iterations** [summary]: 1 → 58.62, 2 → 59.27, 3 → 59.55. Most of the gain comes from summary-based page selection, not from iterating.
- **Chain-of-Notes baseline** [summary, Table 3]: 40.45 at the same backbone. That is a per-page note-taking design close to E7's extraction, and it scored well below SimpleDoc.
- **Costs:** model calls, tokens and latency are *not reported*.
- **Limitations:**
  - Single-document setting only.
  - An open-weight 32B model, not an API model.
  - The summarisation pass reads every page of every document once.
- **Fit with our pipeline:**
  - Reuses the cached ColQwen2 rankings.
  - The summaries need one VLM call per page, for all pages of the 14 documents. If GPT-4o-mini wrote them from images (25.5k tokens per page), that pass would be the dominant cost.
  - Page selection can run text-only, which is cheap.
- **Targets:** missing or partial evidence (E6 group A) and the 4-page cap.
- **Falsifier:** recall of complete evidence among the pages selected does not exceed ColQwen2 top-4 on the 101 evidence questions.

**DocLens**: Zhu, Meng, Chen, Li, Pfister, Yoon. arXiv Nov 2025; ACL 2026 long. [arXiv 2511.11552](https://arxiv.org/abs/2511.11552) [partial]
- **Mechanism:**
  - **Page Navigator:** OCR on every page. The model reads all page screenshots with their OCR text interleaved, 8 times at temperature 0.7, and the predicted page sets are combined.
  - **Element Localizer:** a layout detector crops figures, charts and tables on the predicted pages and adds the crops to the input.
  - **Reasoning:** 8 sampled answers, then an adjudicator call picks the most consistent one.
- **Training:** none.
- **Backbones:** Gemini-2.5-Pro, Gemini-2.5-Flash and Claude-4-Sonnet. All of them take the *whole document* at once. Our GPT-4o-mini context cannot.
- **MMLongBench-Doc ALL scores:**

| Backbone | Vanilla | + OCR text | + DocLens |
|---|---|---|---|
| Claude-4-Sonnet | 53.4 | 56.0 | 63.3 |
| Gemini-2.5-Flash | 49.6 | 58.5 | 64.7 |
| Gemini-2.5-Pro | 58.1 | 63.3 | 67.6 |

  The human expert reference is 65.8. On unanswerable questions, the gain is about 8–14 points.
- **Ablations:**
  - Page Navigator recall is 97.3 % with 3.5 pages, against 71.1 % for MDocAgent's retriever (13.6 pages) and 89.0 % for SimpleDoc (4.9 pages). Removing OCR drops recall to 87.3 % and the score to 58.1.
  - Removing the Lens module: −3 to −4 points. Removing the reasoning module: about −0.5 to −1.
- **Costs:** about 17 calls per question, each over about 49 pages. Tokens and latency are not reported.
- **Limitations:** it depends on long-context frontier models, and the authors say many visual-element cases are not solved by zooming in.
- **Fit with our pipeline:** **low with GPT-4o-mini.** Reading all pages costs 49 × 25.5k image tokens, and that does not fit.
  - The transferable parts are an OCR-text page navigator, which is cheap and text-only, and element crops.
  - Our E3 found that adding OCR text did *not* help GPT-4o-mini (image + text 16/37 vs images alone 17/37). DocLens's "+OCR" gains do not transfer automatically.
- **Targets:** evidence localisation (retrieval), visual elements, unanswerable questions.

**SLEUTH**: Liu et al. arXiv Nov 2025; CVPR 2026. [arXiv 2511.22850](https://arxiv.org/abs/2511.22850) [abstract]
- **Mechanism:** a retriever plus four agents, coarse to fine: clue discovery, page screening, then building a compact, evidence-dense context ("evidence first, decision later").
- **Training:** none.
- **Results:** 52.77 % average on MMLongBench-Doc, against 48.75 for MoLoRAG and 46.76 for the base model (Qwen3-VL-8B family). No independent replication.
- **Fit with our pipeline:** conceptually close to E7's Evidence Memory. Multi-agent, so more calls.

**MDocAgent**: Han et al., 2025. [arXiv 2503.13964](https://arxiv.org/abs/2503.13964), [code](https://github.com/aiming-lab/MDocAgent) [abstract]
- **Mechanism:** five agents (general, critical, text, image, summarizing) over ColBERTv2 text retrieval plus ColPali image retrieval.
- **Results:** +12.1 % average over prior state of the art on five benchmarks. Re-run by SimpleDoc at 55.3 (top-6, 12 pages).
- **Fit with our pipeline:** text + image fusion was already tested in E3 without gain, and the design needs many pages per question.

**ViDoRAG**: Wang et al., EMNLP 2025. [arXiv 2502.18017](https://arxiv.org/abs/2502.18017) [abstract]
- **Mechanism:** hybrid text/visual retrieval fused with a Gaussian mixture model, then a seeker, inspector and answer agent loop.
- **Results:** more than 10 % gain on ViDoSeek, the benchmark the authors introduced.

**MoLoRAG**: Wu et al., EMNLP 2025. [arXiv 2509.07666](https://arxiv.org/abs/2509.07666) [abstract]
- **Mechanism:** a page graph, traversed by a light VLM, to find logically linked pages that semantic similarity misses.
- **Training:** a training-free variant exists, plus a fine-tuned one.
- **Results:** +9.68 accuracy over direct inference and +7.44 retrieval precision on 4 benchmarks.
- **Targets:** multi-page evidence where the second page is not similar to the question.

**D2-ScaleAgent**: arXiv 2608.16417 (2026) [abstract only; numbers not verified]
- **Mechanism:** a Verifier agent decides when the evidence is insufficient. It then either widens retrieval or reads more finely, around an Evidence Bank that acts as working memory.
- **Results:** reports MDocAgent at 58.3 and itself at 63.7 on GPT-4o (from a snippet; unverified).
- **Fit with our pipeline:** the closest published design to "E7 plus a sufficiency check".

**Agentic methods that require training** (out of scope here; listed for completeness):
- **VRAG-RL**: Wang et al., NeurIPS 2025. [arXiv 2505.22019](https://arxiv.org/abs/2505.22019). Trained with GRPO RL; actions include search, crop and zoom.
- **Doc-V\***: Zheng et al., ACL 2026. [arXiv 2604.13731](https://arxiv.org/abs/2604.13731). Imitation learning plus GRPO; thumbnail overview, then fetching selected pages.

## D. Adaptive page count (dynamic k)

**ViSAR**: Mialland, Plantevit, Gallois, Robardet. arXiv Sep 2026 (v3 Nov 2026), not peer reviewed. [arXiv 2609.02486](https://arxiv.org/abs/2609.02486), [code](https://github.com/adrienmialland/ViSAR) [partial]
- **Mechanism:** uses only the late-interaction embeddings.
  - Query-token weights resemble IDF.
  - Patch relevance and page-to-page similarity are computed from the patch vectors.
  - k\* minimises a coherence-minus-leakage cost J(k).
- **Training and tuning:** none; T = 50 and γ = 1e5 are fixed across datasets.
- **MMLongBench results** (ColQwen2.5, Qwen2.5-VL-7B reader, Qwen2.5-14B judge):

| Budget | Fixed top-k | ViSAR |
|---|---|---|
| Max-5 | 35.04 (5.0 pages) | 36.53 (2.9 pages) |
| Max-10 | 35.69 (10 pages) | 36.63 (3.7 pages) |

- **Significance:** significant in 4 of 12 configurations, never significantly worse [summary].
- **Latency:** −34 % to −59 %.
- **Fit with our pipeline:** **high.** It needs only the cached ColQwen2 embeddings, runs on CPU, and needs no API call to select pages.
- **Effect size:** the published accuracy effect is small (about +1 point). The main benefit is fewer pages, which for us means fewer 25.5k-token images and lower cost.
- **Targets:** cost, and distractor pages; it does *not* add missing evidence.

**AVIR**: Li et al., MMAsia 2025. [arXiv 2601.11976](https://arxiv.org/abs/2601.11976) [abstract]
- **Mechanism:** a light relevance scorer, then grouping pages by score distribution.
- **Results:** 70 % fewer pages; ANLS 84.58 on MP-DocVQA (short documents).

## E. Evidence sufficiency, verification and abstention

**Sufficient Context**: Joren et al., ICLR 2025. [arXiv 2411.06037](https://arxiv.org/abs/2411.06037), [code](https://github.com/hljoren/sufficientcontext) [abstract]
- **Finding:** an LLM autorater can label whether the retrieved context is sufficient.
  - Proprietary models answer well when it is, but often answer *wrongly instead of abstaining* when it is not.
  - Guided abstention raises the correct fraction among answered questions by 2–10 % (Gemini, GPT, Gemma).
- **Fit with our pipeline:** a cheap text-only check over E7's Evidence Memory.
- **Targets:** false-premise and unanswerable questions (E6 V failed 9 of 16), and the trigger for retrieving more pages.
- **Caveat:** it is a selective-accuracy method, so it trades coverage for precision. Our scorer counts an abstention on an answerable question as wrong.

**CRAG** (Corrective RAG): Yan, Gu, Zhu, Ling, arXiv 2024. [arXiv 2401.15884](https://arxiv.org/abs/2401.15884), [code](https://github.com/HuskyInSalt/CRAG) [abstract]
- **Mechanism:** a light evaluator labels the retrieval Correct, Incorrect or Ambiguous, which triggers a corrective action. A decompose-then-recompose step filters the retrieved text.
- **Fit with our pipeline:** a foundational pattern for "expand retrieval if insufficient". The web-search fallback does not apply to us.

**Chain-of-Note**: Yu et al., EMNLP 2024. [arXiv 2311.09210](https://arxiv.org/abs/2311.09210) [abstract]
- **Mechanism:** sequential reading notes per retrieved document, then the answer; designed for robustness to noise and to "unknown".
- **Relation to E7:** the closest text-RAG ancestor of E7's per-page extraction. SimpleDoc's re-run of a Chain-of-Notes baseline on MMLongBench (40.45) was weak relative to its own method; that comes from the summary-level read and is unverified.

## F. Region-level reading: crop, zoom and OCR

**ViCrop** ("MLLMs Know Where to Look"): Zhang, Khayatkhoei, Chhikara, Ilievski. ICLR 2025. [arXiv 2502.17422](https://arxiv.org/abs/2502.17422) [abstract]
- **Finding:** MLLM accuracy depends causally on the size of the visual subject, yet the model's attention often points to the right region even when its answer is wrong.
- **Mechanism:** crops guided by the model's own attention or gradients. Training-free.
- **Fit with our pipeline:** **not applicable with an API model**, because attention maps cannot be read. Only the principle transfers: small text and cells at 768 px are a perception risk.

**ZoomEye**: Shen et al., EMNLP 2025. [arXiv 2411.16044](https://arxiv.org/abs/2411.16044), [code](https://github.com/om-ai-lab/ZoomEye) [abstract]
- **Mechanism:** tree search over image sub-patches, using the model's confidence to decide when to stop. Training-free.
- **Results:** +15.7 / +17.7 on HR-Bench for InternVL2.5-8B. These are natural high-resolution images, not documents.
- **Fit with our pipeline:** it needs many confidence-scored calls, which is expensive at 25.5k tokens per image unless crops are small.

**Patch-to-region relevance propagation**: A. Georgiou, arXiv 2512.02660 (v3 Jan 2026), preprint. [abstract]
- **Mechanism:** maps ColPali/ColQwen query-token × patch similarity heatmaps onto OCR bounding boxes (weighted by overlap) to rank page *regions*. No training.
- **Results:** on BBox-DocVQA, region hit-rate at IoU 0.5 is 59.7 % against 6.7 % at random. Context tokens fall by 52.3 % against full-page images.
- **Fit with our pipeline:** **high in principle.** It uses our cached ColQwen2 patch embeddings plus an OCR layout pass; the patch-grid geometry of our renders must be verified first. A crop could be sent at higher resolution for fewer tokens than a whole page.
- **Targets:** perception, table-cell and small-text errors (E6 group B), and token cost.

**RegionRAG**: Li et al., AAAI 2026. [arXiv 2510.27261](https://arxiv.org/abs/2510.27261) [abstract]
- **Mechanism:** region-level retrieval with a *trained* hybrid-supervised retriever; neighbouring salient patches are grouped at inference.
- **Results:** +3.56 % average accuracy on five benchmarks.
- **Fit with our pipeline:** training is required, so it is out of scope. It does show that region granularity is worth testing.

**DocLens Element Localizer** (section C): layout-detector crops of tables, charts and figures added beside the page image.
- **Results:** block-level F1 +6.7 % on FinRAGBench-V (202 cases).
- **Limitation:** the authors note that zooming does not solve many visual-element cases.

## G. Page reranking

| Method | Mechanism | Evidence | Fit with our pipeline |
|---|---|---|---|
| **jina-reranker-m0** (2025). [model card](https://huggingface.co/jinaai/jina-reranker-m0) [abstract] | 2.4B decoder-only VLM reranker based on Qwen2-VL-2B. | Vendor-reported 91.02 NDCG@5 on ViDoRe. | **CC-BY-NC licence:** non-commercial only, so a problem for the application. Local inference of a 2.4B VLM over the top-20 pages needs a download (approval needed); on Apple-silicon CPU/MPS it is feasible but slow. |
| **MM-R5**: arXiv 2506.12364 [abstract] | RL-trained Qwen2.5-VL-7B reasoning reranker. | +4 % recall@1 over the best retriever. | Training, and a 7B model locally. |

## H. Inference cost (documented facts)

- **OpenAI Batch API:** a 50 % discount on every model, with results within 24 h. Source: [OpenAI FAQ](https://help.openai.com/en/articles/9197833-batch-api-faq).
  - Using it in an experiment is an execution change, not a model change, but it alters timing and the serving backend. Record it as a condition.
  - Forum reports question whether the discount applies to image tokens; verify with a 1–2 request batch before relying on it.
- **GPT-4o-mini image tokens:** forum reports put its image-token multiplier at about 33× GPT-4o's (OpenAI did not document it; staff reportedly confirmed it was intentional).
  - Our own measurement is consistent with this: 25,501 prompt tokens per 768-px page.
  - **Any method that sends fewer or smaller images, such as crops, adaptive k or text-only steps, cuts cost almost proportionally.** Reasoning over text is about 100× cheaper per call than reading an image.
- **The snapshot gpt-4o-mini-2024-07-18 is scheduled to shut down on 2027-01-14** (recorded in the E6 notes).
  - Any method tuned to this model has a short shelf life.
  - The application phase will need a model-migration condition, and that is itself a new experiment.

## I. Cross-cutting reading

1. **Gains in the strongest papers come mainly from evidence localisation, not from reasoning scaffolds.**
   - DocLens: Lens −3 to −4 points when removed, reasoning about −0.5 to −1.
   - SimpleDoc: page selection carries most of the gain; iterations add about +1.
   - With ground-truth pages, SimpleDoc's reader reaches 67.9 against 41.8–60.6 with retrieval.
2. **Most strong results use long-context or larger readers**: Gemini-2.5, Claude-4, Qwen2.5-VL-32B. With GPT-4o-mini at 25.5k tokens per page, "read many pages" designs are cost-prohibitive. The transferable ingredients are text-only or embedding-only selection, and crops.
3. **Training-free adaptive k (ViSAR) has small but consistent published effects (about +1 point).** Its value for us would be cost, not accuracy.
4. **Evidence that per-page note-taking (Chain-of-Note style) helps on MMLongBench is weak** (SimpleDoc's re-run, unverified). E7 is the direct test on our setup.
5. **Benchmark judges differ** (GPT-4.1, Qwen-14B, rule-based). Never compare absolute numbers across papers or with ours.
