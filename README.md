# VisualDoc AI — Multimodal Document Intelligence

VisualDoc AI is a project to answer questions about PDF documents (digital
and scanned) with **verifiable citations to the source page**, and to
measure, through a controlled evaluation, **when looking at the page image
helps compared with reading only the extracted text**.

> **Project status: learning notebooks plus a first public-benchmark baseline.**
> The repository has a tested native/OCR page parser, a numbered notebook path,
> and a reproducible **MMLongBench-Doc** benchmark notebook
> (`notebooks/project/14_mmlongbench_doc_benchmark.ipynb`) that measures page
> retrieval for real and scores answers with the benchmark's rules. LLM answer
> generation is implemented but **gated**: it runs only when a model and API key
> are configured, so no answer accuracy has been measured yet. The project's own
> verified question set is still empty. The [status table](#9-implemented-vs-planned)
> separates what works from what is planned.

---

## 1. Motivation and problem statement

Most "chat with your PDF" systems convert each page to text, split it into
chunks, retrieve the chunks most similar to the question, and give them to a
language model. This works for prose, but a PDF page is a set of drawing
instructions, not a structured document. The experiments in this repository
show concrete failures of the text route:

- **Figures stored as images carry no extractable text.** On `data/documents/ch2.pdf`
  page 65, the plotted curves and their labels exist only as pixels; native
  extraction returns only the caption.
- **Tables lose their structure.** On `data/documents/ch2.pdf` page 49, PyMuPDF's
  `find_tables()` detects a table but returns it as a single column.
- **Equations are mangled.** The integral sign in the TeX font CMEX comes out
  as the letter `R`; a fraction comes out as `m(x)1`.
- **Scanned pages contain no text at all** until OCR is run, and simple
  heuristics can be fooled: `data/documents/scanned.pdf` page 1 has one native heading
  drawn over a full-page scan.

Vision-language models (VLMs) can read a rendered page image directly, which
should help on exactly these cases — but they are slower, more expensive,
and their claims are harder to verify. The project asks where the trade-off
is worth it, and builds a system that cites the pages it used so answers can
be checked.

## 2. Objectives and expected outcomes

1. A parsing stage that handles both born-digital and scanned PDFs, choosing
   native extraction or OCR per page.
2. Page-level semantic retrieval that returns the evidence pages for a
   question.
3. Two answer generators over the same retrieved pages: **text-only** (LLM
   over extracted text) and **multimodal** (VLM over page images).
4. Answers with **page citations** that link back to the source.
5. A small, human-verified evaluation set and a report comparing the two
   generators by question type and evidence type.
6. A minimal Streamlit interface to upload a PDF, ask a question, and see the
   answer next to the cited pages.

## 3. MVP scope and limitations

**In scope:** English PDFs (born-digital and scanned); questions about a
single document; text, tables, figures, equations and scanned text as
evidence; page-level citations; local single-user app.

**Out of scope for the MVP:** cross-document questions; handwriting;
image-only inputs (JPG/PNG — explored in `notebooks/course_labs/`, not in the MVP); open-ended
summaries; region-level (bounding-box) citations; fine-tuning; multi-user
deployment.

**Known limitations to expect:**

- The evaluation set will be small (target 60–100 questions), so only
  large differences between methods will be distinguishable from noise.
- Both generators will likely depend on paid APIs; costs and model versions
  must be recorded with each run for results to be reproducible.
- A single annotator (with a delayed second pass) is weaker than two
  independent annotators. This will be stated in the results.

## 4. Proposed architecture (planned)

```mermaid
flowchart LR
    PDF[PDF] --> I[Inspect page<br/>native words, image coverage]
    I --> R{Route}
    R -->|native| N[PyMuPDF text]
    R -->|scanned| O[Tesseract OCR]
    I --> IMG[Render page image]
    N & O --> P[(Page records<br/>text + image + page no.)]
    IMG --> P
    P --> E[Embed page text] --> V[(Vector index)]
    Q[Question] --> S[Retrieve top-k pages]
    V --> S
    S --> T[Text-only: LLM over page text]
    S --> M[Multimodal: VLM over page images]
    T & M --> A[Answer + cited pages]
    A --> UI[Streamlit UI]
    A --> EV[Evaluation vs annotations]
```

The **page** is the unit of retrieval and citation. This keeps citations
simple to verify (the annotation set records evidence pages) and lets the
same retrieved pages be given to either generator, which the evaluation
requires. Only the first stage (inspect → route → extract) has been
prototyped, in `notebooks/prototypes/page_extraction.ipynb`.

## 5. Technologies

| Technology | Purpose | Status |
| --- | --- | --- |
| [PyMuPDF](https://pymupdf.readthedocs.io/) | Text, words, fonts, images, tables from PDFs; page rendering | Prototyped in notebooks |
| Tesseract (via PyMuPDF, `resources/tessdata/eng.traineddata`) | OCR for scanned pages | Prototyped in notebooks |
| pandas, pytest | Annotation files and their schema checks | Implemented (`tests/`) |
| PaddleOCR, LayoutReader, LandingAI ADE | Alternative OCR, layout, reading order, agentic extraction | Explored in `notebooks/course_labs/` only; candidates for hard pages |
| BM25 (implemented in the notebook, no library) | Lexical page retrieval baseline | Implemented in notebook 14 |
| Hugging Face `datasets`, `huggingface_hub` | Download public benchmarks at pinned revisions | Used in notebooks 12–14 |
| ChromaDB | Vector store for retrieval | Used in `notebooks/course_labs/L5`; not needed for the current baseline |
| Embedding model | Semantic page retrieval | Planned; **not chosen yet** |
| OpenAI API (`openai`, `langchain-openai`) | LLM / VLM answer generation | Used in `notebooks/course_labs/`; notebook 14 has a gated OpenAI call; provider and model for the MVP **not finalized** |
| Streamlit | User interface | Planned; not installed |

## 6. Research question and evaluation strategy

**Research question.** On the same documents, questions and retrieved pages,
does giving the model **page images** instead of **extracted text** improve
answer accuracy and citation correctness — and for which kinds of evidence
(text, tables, figures, equations, scanned text)?

**Expectation to test** (not a result): little difference on plain-text
questions; a multimodal advantage on figures and tables; scanned text depends
on OCR quality.

**Controlled design.** Only the generator's input changes between
conditions. Held constant: questions, documents, retriever, number of pages
*k*, prompt template, temperature, and — where possible — the model itself
(one model that accepts both text and images).

| | Retrieved pages (top-*k*) | Oracle pages (annotated evidence) |
| --- | --- | --- |
| **Text input** | end-to-end text-only | text-only reading ability |
| **Image input** | end-to-end multimodal | multimodal reading ability |

The oracle column gives each generator the correct pages, which separates
"the retriever missed the page" from "the model misread the page".

**Metrics.**

- *Retrieval:* page Hit@*k* — is any annotated evidence page in the top *k*?
- *Answer correctness:* numbers within tolerance; short answers by
  normalized match, checked manually; graded blind to the condition.
- *Citation correctness:* does the answer cite at least one annotated
  evidence page?
- *Abstention:* on `unanswerable` questions, does the system say the answer
  is not in the document?

Results are reported per `evidence_modality` and `question_type`, with
counts, using paired comparisons on the same questions (e.g. McNemar's test
or bootstrap intervals). Prompts and settings are tuned on the `dev` split
only; the `test` split is used once for final numbers.

**Dataset.** See [`data/annotations/README.md`](data/annotations/README.md)
for the schema and labelling workflow. `questions.csv` is currently
**empty**; the three documents in `documents.csv` are **candidates**, not yet
selected.

**Public benchmark while the project set is empty.** Notebook 14 runs the
same retrieval → answer → citation → scoring loop on a seeded subset of
**MMLongBench-Doc** (public questions with reference answers and evidence
pages). It reports Recall@k and Hit@k against an exact random-ranking
reference. Answer scores use a local re-implementation of the benchmark's
rule-based scorer and are labelled as local diagnostics, not leaderboard
results. See [`experiments/README.md`](experiments/README.md) and
[`data/external/README.md`](data/external/README.md).

## 7. Roadmap (tentative)

| Day | Milestone |
| --- | --- |
| 1 | ✅ Project foundation: README, structure, annotation schema and guide, environment review |
| 2 | ✅ Historical baseline: parsing prototype moved into `src/visualdoc/parsing.py` with unit tests; retained but not extended during notebook-first learning |
| 3 | Build and inspect page records in project notebooks; start writing questions |
| 4 | Explore embeddings and retrieval in notebooks; measure page Recall@*k* on `dev` when verified questions exist |
| 5 | Develop text-only answer generation with page citations in a notebook |
| 6 | Develop page rendering + VLM answering in a notebook (multimodal condition) |
| 7 | Build the four-condition evaluation interactively, store runs, and score |
| 8 | Finish and verify annotations; freeze the `test` split |
| 9 | Improve weak cases (tables, figures) using `dev` only |
| 10 | Streamlit app only after the learning phase and explicit approval to productionize |
| 11 | Final evaluation on `test` |
| 12 | Error analysis |
| 13 | Notebook documentation, sequential execution checks, cleanup |
| 14 | Buffer and demo |

## 8. Notebook-first development workflow

All new exploratory and experimental implementation lives directly in real
Jupyter notebooks under `notebooks/project/`. The numbered learning path is:

| Stage | Notebook | Purpose |
| --- | --- | --- |
| 00 | `00_environment_and_corpus.ipynb` | Verify the kernel, paths, document manifest, and page counts |
| 01 | `01_pdf_representation.ipynb` | Compare native PDF objects with rendered page appearance |
| 02 | `02_page_inspection.ipynb` | Derive and inspect per-page routing features |
| 03 | `03_extraction_routing.ipynb` | Make routing thresholds and failure cases explicit |
| 04 | `04_ocr_and_page_records.ipynb` | Compare OCR modes and assemble an inspectable page record |
| 05 | `05_annotations_and_quality.ipynb` | Validate annotation schemas and evaluation readiness |
| 06 | `06_embedding_and_retrieval.ipynb` | Learn vectorization, cosine similarity, and ranking transparently |
| 07 | `07_retrieval_evaluation.ipynb` | Implement Hit@*k* and keep mechanics checks separate from project results |
| 08 | `08_text_qa_with_citations.ipynb` | Construct text evidence, prompts, and citation validation |
| 09 | `09_multimodal_qa_with_citations.ipynb` | Render image evidence and construct the matched multimodal input |
| 10 | `10_controlled_evaluation.ipynb` | Define the four conditions and validate paired scoring |
| 11 | `11_error_analysis.ipynb` | Separate parsing, retrieval, generation, and citation failures |
| 12 | `12_external_datasets.ipynb` | Exploratory download log for MMLongBench-Doc, ViDoRe, OmniDocBench (raw, kept as-is) |
| 13 | `13_understand_the_datasets.ipynb` | Inspect the grain, schema, and quality of the local and external datasets |
| 14 | `14_mmlongbench_doc_benchmark.ipynb` | Reproducible MMLongBench-Doc subset: OCR fallback, BM25, Recall@k, gated cited answers, official-rule scoring |

Each notebook is independently executable and follows objective → concept →
implementation → execution → inspection → interpretation → validation. New
project notebooks do not import `src/visualdoc/` as a hidden implementation
layer. Repeated operations are intentionally visible when that supports
learning.

The existing `src/`, `tests/`, `notebooks/prototypes/`, and
`notebooks/course_labs/` directories remain untouched baselines or reference
material. Moving notebook code into Python modules or adding an application
framework is a later production phase, not part of current experimentation.
The repository-level [`AGENTS.md`](AGENTS.md) records this policy for future
development sessions.

## 9. Implemented vs planned

| Component | Status | Where |
| --- | --- | --- |
| PDF anatomy study (text, spans, images, tables, OCR) | ✅ Experiment | `notebooks/experiments/pdf_anatomy.ipynb` |
| Per-page routing: native / OCR / hybrid / review | ✅ Implemented; original prototype retained | `src/visualdoc/parsing.py`, `notebooks/prototypes/page_extraction.ipynb` |
| Notebook-first project learning path | ✅ Structured; locally runnable stages executed where inputs exist | `notebooks/project/` |
| OCR, layout, ADE, ADE-based RAG course labs | ✅ Learning material | `notebooks/course_labs/` |
| Annotation schema, guide, schema tests | ✅ Implemented | `data/annotations/`, `tests/` |
| Verified evaluation questions | ⏳ Not started (needs a human annotator) | `data/annotations/questions.csv` |
| Reusable parsing module | ✅ Historical tested baseline; frozen during notebook-first learning | `src/visualdoc/parsing.py`, `tests/test_parsing.py` |
| Retrieval | 🧪 Transparent lexical mechanics (06–07); **BM25 baseline measured on MMLongBench-Doc** (14); semantic model not selected | `notebooks/project/06_…`, `07_…`, `14_mmlongbench_doc_benchmark.ipynb` |
| Public-benchmark evaluation (MMLongBench-Doc) | ✅ Retrieval measured on a seeded 6-document subset; 🧪 answer generation gated (no model/key configured) | `notebooks/project/14_mmlongbench_doc_benchmark.ipynb`, `experiments/README.md` |
| Text-only and multimodal QA, citations | 🧪 Inputs and validation implemented; real model calls intentionally gated | `notebooks/project/08_text_qa_with_citations.ipynb`, `09_multimodal_qa_with_citations.ipynb`, `14_…` |
| Controlled evaluation on the project's own set | 🧪 Design and scoring path implemented; real runs blocked by empty verified set | `notebooks/project/10_controlled_evaluation.ipynb`, `11_error_analysis.ipynb` |
| Streamlit app | ⏳ Deferred until explicitly requested after learning | — |

## 10. Repository layout

```text
.
├── AGENTS.md                       # enforced notebook-first development policy
├── README.md                       # project overview and usage
├── pyproject.toml                  # package metadata and core/dev dependencies
├── requirements.txt               # compatibility installer
├── requirements/labs.txt          # optional heavy course-lab dependencies
├── data/
│   ├── documents/                  # three evaluation document candidates
│   ├── annotations/                # dataset schema, guide, and CSV files
│   └── external/                   # public benchmarks (see data/external/README.md)
├── resources/tessdata/             # local Tesseract language models
├── src/visualdoc/parsing.py        # reusable inspection, routing, and OCR
├── tests/                          # annotation and parsing tests
├── notebooks/
│   ├── project/                    # numbered, executable learning path (00–14)
│   ├── experiments/                # executed PDF anatomy study
│   ├── prototypes/                 # original page-routing prototype
│   └── course_labs/                # external learning/reference material
├── experiments/                    # evaluation docs; runs/ holds git-ignored run outputs
└── docs/                           # technical map and agent-skill notes
```

## 11. Setup

Tested environment: Python 3.12.6 on macOS (Apple Silicon).

```bash
# from the repository root
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env          # then fill in the keys you need
```

For the optional course labs, also install:

```bash
pip install -r requirements/labs.txt
```

Extra, non-pip requirements used only by some course labs:

- `notebooks/course_labs/L1.ipynb` uses `pytesseract`, which needs the Tesseract binary:
  `brew install tesseract`. The project notebooks do **not** need it; they use
  the OCR engine built into PyMuPDF with `resources/tessdata/`.
- `notebooks/course_labs/L3.ipynb` needs LayoutReader, which is not on PyPI:
  `git clone https://github.com/ppaanngggg/layoutreader.git notebooks/course_labs/layoutreader`
  (already git-ignored).

API keys (see `.env.example`):

| Key | Needed by |
| --- | --- |
| `OPENAI_API_KEY` | `notebooks/course_labs/L1`, `L2`, `L3`, `L5` |
| `VISION_AGENT_API_KEY` (LandingAI) | `notebooks/course_labs/L4`, `L4_II`, `L5` |
| `OPENAI_API_KEY` + `VISUALDOC_LLM_MODEL` (+ `VISUALDOC_LLM_PROVIDER=openai`) | answer generation in `notebooks/project/14_…` (optional; install with `pip install -e '.[llm]'`) |

The tests and notebooks 00–13 need no API key. Notebook 14 runs fully without
one and stops answer generation at an explicit readiness gate.

**Troubleshooting `ModuleNotFoundError: No module named 'visualdoc'` on macOS.**
If `pip show visualdoc-ai` succeeds but the import fails, the editable-install
`.pth` file may carry the macOS `hidden` flag (`ls -lO .venv/lib/python3.12/site-packages/*.pth`).
Python 3.12 skips hidden `.pth` files. Clear the flag with
`chflags nohidden .venv/lib/python3.12/site-packages/*.pth`.

## 12. Running what exists

**Tests** (from the repository root; expected: all pass):

```bash
pytest tests/ -v
```

**Notebook-first project path** — paths are resolved from the repository root,
so start Jupyter anywhere inside the checkout:

```bash
jupyter lab
```

Start with `notebooks/project/00_environment_and_corpus.ipynb` and continue in
numeric order. The project notebooks use the standard `python3` kernelspec and
contain explicit readiness gates where verified annotations or model choices
do not yet exist.

The older `notebooks/experiments/pdf_anatomy.ipynb` and
`notebooks/prototypes/page_extraction.ipynb` remain useful references. Their
saved metadata names a `conda` kernel, so select the project environment when
opening them.

**Course notebooks** — start Jupyter from their directory because these
imported notebooks intentionally use lesson-relative paths:

```bash
cd notebooks/course_labs
jupyter lab
```

They call `load_dotenv()`, which searches parent folders, so a `.env` at the
repository root should be found.

## 13. Data and licensing notes

`documents.csv` records the provenance and usage rights of every document.
Anything committed here is public: check `usage_rights` before adding a
document, and do not commit private or confidential PDFs.

MMLongBench-Doc data is licensed CC BY-NC 4.0 for research use. Its PDFs are
downloaded on demand into a git-ignored folder rather than committed. See
[`data/external/README.md`](data/external/README.md) for every external
dataset. See
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) for unresolved licensing
and redistribution notes.
