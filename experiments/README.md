# `experiments/` — results and runs

| Folder | Tracked | Content |
| --- | --- | --- |
| `frozen/mmlongbench_doc/` | yes | The canonical text run (conditions A, C) and image run (B, D), copied byte for byte, with `SHA256SUMS` and a provenance [README](frozen/mmlongbench_doc/README.md). Never edited. |
| `frozen/e1/` | yes | Byte-identical copy of the E1 full run `20261121T131525011829Z_29c92c8a` plus its per-question table, six figures, `PROVENANCE.json`, `SHA256SUMS` and a [README](frozen/e1/README.md) with results and limitations. Notebook 03 evaluates it by default. Never edited. |
| `frozen/e2/` | yes | Byte-identical copy of the E2 full run `20261122T120924635816Z_4f2e1369` (Qwen3-VL-8B vs GPT-4o-mini) plus its per-question table, four figures, an independent `AUDIT.json` (44/44), `PROVENANCE.json`, `SHA256SUMS` and a [README](frozen/e2/README.md). Notebook 03 evaluates it by default. Never edited. |
| `frozen/e3/` | yes | Byte-identical copy of the E3 full run `20261122T143134629529Z_4c62bfc2` (text vs images vs both) plus its per-question table, four figures, an independent `AUDIT.json` (55/55), `PROVENANCE.json`, `SHA256SUMS` and a [README](frozen/e3/README.md). Notebook 03 evaluates it by default. Never edited. |
| `runs/` | no (git-ignored) | Raw outputs of live runs. New runs from `notebooks/02_question_answering.ipynb` go to `runs/qa/<UTC timestamp>_<mode>/`; the historical runs of the archived notebooks 14 and 15 stay in `runs/mmlongbench_doc/` and `runs/mmlongbench_doc_multimodal/` where they exist. |

Experiment E1 resolution runs are isolated under
`runs/e1/<UTC timestamp>_<unique id>_<mode>_<render profile>/`. Creation is
exclusive: an existing run is never overwritten. The protocol is frozen in
[`specs/e1_image_resolution_v1.json`](specs/e1_image_resolution_v1.json).
E1's default `offline` mode creates no run directory and makes no API call; it
writes only regenerable design, request-estimate and cost-plan files to
`data/processed/mmlongbench_doc/e1/`.

A paid run directory contains these audit files:

- `settings.json`, `spec_snapshot.json`, `execution_plan.json` and
  `request_estimates.csv`;
- `execution_log.jsonl` in actual request order, including timestamps,
  dimensions, full image hashes, token usage, model/system fingerprints and
  cache provenance;
- `response_cache.jsonl`, scoped to that run and replicate only;
- `smoke_gate.json` and `smoke_records.jsonl`;
- `completion.json`;
- for pilot/full, `predictions_main_r1_E1_512.jsonl` and
  `predictions_main_r1_E1_768.jsonl`;
- for full only, `predictions_control_r2_E1_512.jsonl`;
- after evaluation, `evaluation_summary.json` and the full-run summary figure.

Cached-response lookup latency is recorded separately from the originating
live API latency. A new run or replicate has a new cache namespace and cannot
reuse a previous replicate's response.

Experiment E3 (text–image fusion) runs go to `runs/e3/<UTC timestamp>_<unique id>_<mode>/`,
with the same exclusive creation and the same audit files as E2: settings, spec snapshot,
execution plan, request plan, session records, an append-only execution log, a run-scoped
response cache, gates, predictions per replicate and condition, and `completion.json`
(or a `stop_*.json` record that a resumed run continues). The protocol
[`specs/e3_text_image_fusion_v1.json`](specs/e3_text_image_fusion_v1.json) was frozen on
2026-11-22 with a cumulative USD 1.25 budget for all E3 runs. Paid modes also require the spec and notebook 02's code
to equal git HEAD, and record the commit in `settings.json`. The approved smoke, pilot and full runs completed on
2026-11-22 ($0.91 in all, list price); the full run is frozen in [`frozen/e3/`](frozen/e3/README.md), and the
smoke and pilot runs stay git-ignored in `runs/e3/` with their checksums in its `PROVENANCE.json`.

Experiment E4 (the application end to end) runs go to `runs/e4/<UTC timestamp>_<unique id>_<mode>/`, with E3's audit
files (settings with the application's module hashes, spec snapshot, plans, session records, append-only log, run-scoped
cache, smoke gate, predictions per replicate and arm, `completion.json` or `stop_*.json`). The protocol
[`specs/e4_application_end_to_end_v1.json`](specs/e4_application_end_to_end_v1.json) was frozen in commit `72791e9`
(ceiling $1.50). The approved smoke run (`20261123T000439244313Z_ea059977_smoke`) and full run
(`20261123T000625940289Z_15119ec0_full`) completed on 2026-11-23 ($1.2006 in all, list price). Both are frozen, byte for
byte, in [`frozen/e4/`](frozen/e4/README.md) with the evaluation summary, an independent audit (35/35) and the provenance.

Experiment E6 (visual retrieval, end to end: GPT-4o-mini on OCR + BM25 pages versus ColQwen2 pages, E5's 118 held-out
questions) runs go to `runs/e6/<UTC timestamp>_<unique id>_<mode>/`, with E4's audit files and no annotation in the logs. The
protocol [`specs/e6_visual_retrieval_answering_v1.json`](specs/e6_visual_retrieval_answering_v1.json) was frozen on 2026-11-23
with notebook 05 (cumulative ceiling USD 5.60, retries included; upper bound of all stages USD 3.80). No paid call has been
made; the smoke and full stages each need separate authorization.

## How results are reproduced

```text
00 → pages and images ─┐
01 → rankings ─────────┼─► 02 (replay: rebuild every request, assert it equals the frozen one, reuse the reply)
frozen predictions ────┘        └─► predictions/{A,B,C,D}.jsonl ─► 03 (score, compare, analyse; asserts the frozen numbers)
```

What is verified on every execution, without API calls:

- the document subset, question ids, full BM25 rankings (57/57) and the retrieval table (Recall@5 0.689, Hit@5 0.800) equal the frozen run;
- the 124 page images sent to the model are reproduced byte for byte;
- page lists, both system prompts (hashes `f60729bf0b66`, `35ff2e8b91f9`), generation parameters, token estimates and all 95 image-request fingerprints equal what was sent;
- every per-question score, the four-condition counts (A 7/40, B 7/40, C 9/40, D 11/38) and the five paired summaries equal the frozen files;
- for E1, the 113 frozen requests are rebuilt with identical fingerprints and replicate-specific cache keys (02). The frozen run's evaluation, integrity audit and per-question table are re-derived exactly, and the references 10/37, 11/37, 16/37 hold (03).

What cannot be verified without paying for new calls: whether the model would
give the same replies today. At temperature 0, 3–6 of 57 text predictions
changed between identical runs on 2026-11-19, with no score change; image
run-to-run variation has not been measured.

## Settings that define a run

Defined in one `SETTINGS` cell per notebook and recorded with each live run:
dataset revision `2ff6aa92…`, seed 42, 6 documents ≤ 15 MB, OCR below 30
native words at 150 dpi, BM25 k1 = 1.5 and b = 0.75, top-k = 5, 3,500
characters per text page, render box 512 × 1024 px, `detail: high`, model
`gpt-4o-mini-2024-07-18`, temperature 0, 400 output tokens, prompt versions
`mmlb-structured-v1` (text) and `mmlb-image-v1` (images).
