# Frozen MMLongBench-Doc results

Byte-identical copies of the two runs that produced every reported answer
result. They are committed so that `notebooks/02_question_answering.ipynb`
(in its default `replay` mode) and `notebooks/03_evaluation.ipynb` can
reproduce the evaluation **without any API call**. Verify the files with:

```bash
cd experiments/frozen/mmlongbench_doc && shasum -a 256 -c SHA256SUMS
```

| Folder | Conditions | Produced by (now in `archive/notebooks/project_v1/`) | Model |
| --- | --- | --- | --- |
| `text_run_20261119T220858Z_a351a532/` | A (text, retrieved pages) `predictions.jsonl`; C (text, oracle pages) `oracle_predictions.jsonl` | `14_mmlongbench_doc_benchmark.ipynb`, `full` mode, 2026-11-19 | requested `gpt-4o-mini`, served `gpt-4o-mini-2024-07-18` |
| `image_run_20261119T232847Z_65ccf1ef/` | B (images, retrieved) `predictions_retrieved_images.jsonl`; D (images, oracle) `predictions_oracle_images.jsonl` | `15_multimodal_mmlongbench_doc.ipynb`, `full` mode, 2026-11-20 | requested and served `gpt-4o-mini-2024-07-18` |

Notes on provenance:

- Other full text runs from 2026-11-19 (configuration hashes `99abf141` and
  `a351a532`) gave the same per-question scores; notebook 14 reported that
  4–6 of 57 predictions differed between runs at temperature 0.
- The image run made 65 live calls (52 for B, 13 for D) and reused 30 replies
  from the response cache (5 from the pilot, 25 where the D request was
  byte-identical to a B or pilot request). Run `20261119T233345Z_65ccf1ef`
  re-executed the same configuration entirely from the cache and produced
  identical predictions; it is not copied here.
- The last saved execution of the archived notebook 15 ran in `off` mode
  (run `20261120T135912Z_3e6c4902`, no image predictions). Its markdown
  results section describes the full run above, which is the run kept here.
- Image records contain image SHA-256 hashes and request fingerprints, never
  Base64 payloads. No file contains an API key (checked when frozen).
- `scored_*.csv` and `paired_*.csv` contain question text from
  MMLongBench-Doc, which is licensed CC BY-NC 4.0 (research use).

Other run folders (smoke tests, pilots, the failed `429` run
`20261119T210333Z_84cb44ab`, `off` executions) remain only in the git-ignored
`experiments/runs/` on the machine that produced them.
