# Archive

Superseded or reference material, kept for history. Nothing here is imported
or read by the current notebooks in `notebooks/`. Files were moved with
`git mv`, so `git log --follow <file>` shows their full history.

| Path | What it is | Where its content went |
| --- | --- | --- |
| `notebooks/project_v1/00–05` | Learning path on the local PDFs: environment, PDF anatomy, page features, routing rule, OCR modes, annotation schema | Page features, native/OCR extraction and page records → `notebooks/00_document_processing.ipynb`. The NATIVE/HYBRID/OCR/REVIEW routing rule lives on in `src/visualdoc/parsing.py` (tested). Annotation checks → `tests/test_annotations.py`. |
| `notebooks/project_v1/06–07` | Term-frequency cosine retrieval and Hit@k mechanics on 4 slide pages | BM25, Recall@k and Hit@k on the benchmark → `notebooks/01_retrieval.ipynb` |
| `notebooks/project_v1/08–11` | Designs for text QA, image QA, the four-condition evaluation and error analysis, executed on gated or synthetic inputs | Implemented for real → `02_question_answering.ipynb` and `03_evaluation.ipynb` |
| `notebooks/project_v1/12–13` | Download log and exploration of MMLongBench-Doc, ViDoRe and OmniDocBench | Only MMLongBench-Doc is used; its loading and checks → `00_document_processing.ipynb` |
| `notebooks/project_v1/14_mmlongbench_doc_benchmark.ipynb` | Text benchmark: subset, OCR, BM25, scoring, text answers (A), oracle text (C); executed in `full` mode | Split into 00 (§1–5), 01 (§6–7), 02 (§9, §13 generation), 03 (§8, §10, §12–13 analysis). Its predictions are in `experiments/frozen/`. |
| `notebooks/project_v1/15_multimodal_mmlongbench_doc.ipynb` | Image conditions (B, D), paired analysis, error taxonomy. **Last saved execution is `off` mode**: its code cells show no image results; its markdown "Results" section describes the full run `20261119T232847Z_65ccf1ef` | Rendering → 00; prompts, cost model, API plumbing, generation → 02; scoring, paired comparisons, legibility, error analysis, manual review → 03. Its predictions are in `experiments/frozen/`. |
| `notebooks/experiments/pdf_anatomy.ipynb` | Early study of text, spans, images, tables and OCR in a PDF | Background for 00 |
| `notebooks/prototypes/page_extraction.ipynb` | Original page-routing prototype | `src/visualdoc/parsing.py` |
| `course_labs/` | DeepLearning.AI course notebooks (OCR, layout, ADE, RAG); run from this folder, dependencies in `requirements/labs.txt` | Reference only |
| `docs/technical-knowledge-map.md` | 1,500-line study guide written on 2026-11-18, before the benchmark | Reference only; parts describe planned components that were never built (embeddings, Streamlit) |

The archived notebooks still resolve paths from the repository root, but they
were written for the old layout (`notebooks/project/`) and are not maintained;
re-executing them is not part of the current workflow.
