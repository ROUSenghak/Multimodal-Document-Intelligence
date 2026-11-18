# Course labs

This directory contains the six DeepLearning.AI course notebooks that were
used to explore OCR, layout analysis, hosted document extraction, and RAG.
They are reference and learning material, not the VisualDoc application.

Run them from this directory because the notebooks intentionally use local
paths for their lesson assets:

```bash
cd notebooks/course_labs
jupyter lab
```

Install their optional dependencies from the repository root with:

```bash
pip install -r requirements/labs.txt
```

The notebooks that call OpenAI or LandingAI also require the keys documented
in the repository's `.env.example`. `L3.ipynb` additionally expects a clean
LayoutReader checkout at `notebooks/course_labs/layoutreader/`.

Execution state varies: most notebooks were imported without saved outputs,
and `L5.ipynb` requires ADE output to be generated before its RAG cells run.

