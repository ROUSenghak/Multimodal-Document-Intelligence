# Untouched test pool: what has been seen (ledger)

- **Purpose.** Record, before any final evaluation, every piece of information about the MMLongBench-Doc test pool that has already been displayed or used. A reviewer can then judge how "untouched" it is.
- **Maintenance.** Update this ledger whenever new pool metadata is read. Nothing in it may be used to tune a system.
- **Compiled:** 2026-11-25, by a scan of every tracked file, every notebook output and the git-ignored `data/processed/` and `experiments/runs/` folders. The scan printed file names and counts only. Each match was then classified by its role, with pool text masked.

## Definition

The **pool** is every MMLongBench-Doc document (revision `2ff6aa92…`) outside the 20 used so far:
- the 6 development documents of E0–E4 (`in_subset`);
- the 14 held-out documents of E5–E7, now development data.

That leaves **115 documents and 916 questions.**

## What is known, by level

| Level | Information | Where it was seen | Documents concerned |
|---|---|---|---|
| 0. Frame | Document file names and benchmark types for all 135 documents. The full question table (questions, answers, evidence) is **in the repository** (`data/external/mmlongbench_doc/data/*.parquet`, and `questions.parquet` built by notebook 00). Being present is not being inspected; see levels 1–3. | Repository | all 115 |
| 0. Frame | File sizes, aggregated: "135 documents referenced, 125 of at most 15 MB" | Notebook 00 output (2026-11-19 onward) | all |
| 1. Whole-benchmark aggregates (pool included) | Answerable × answer-format cross-table over all 1,091 questions | Notebook 00 output | all |
| 1. Pool aggregates | 115 documents, 916 questions, 705 answerable | E6 error decomposition (2026-11-24); E7 spec `final_test_proposal` | all |
| 1. Pool aggregates | Documents and questions per benchmark type (frame counts only) | Post-E7 assessment, 2026-11-25 (`docs/baseline_consolidation_assessment.md` §4.2) | all |
| 1. Pool aggregates | Number of eligible documents per type at the E5 selection (≤ 15 MB, not excluded): Academic 19, Admin/Industry 10, Brochure 14, Financial 11, Guidebook 16, Research report 29, Tutorial 16 | Notebook 04 `e5-select` output | all |
| 2. Per-document metadata | Page count and file size; the PDF downloaded; rejected by E5's 100-page cap | Notebook 04 `e5-select` output | `3M_2018_10K.pdf` (160 pages), `mmdetection-readthedocs-io-en-v2.18.0.pdf` (468), `dr-vorapptchapter1emissionsources-121120210508-phpapp02_95.pdf` (196) |
| 3. Question content | `mmlb-0000`: question, reference answer, evidence page, format | Notebook 00 output; archived notebooks 12, 13, 14 | `PH_2016.06.08_Economy-Final.pdf` (its PDF is also downloaded; it was once tracked in git) |
| 3. Question content | `mmlb-0000`–`mmlb-0002`: question (truncated), reference answer, format, evidence pages and sources | This session, 2026-11-25, a schema inspection printed the table's first three rows. **This was an inadvertent display.** | `PH_2016.06.08_Economy-Final.pdf` |
| 3. Question content | `mmlb-0210`, `mmlb-0980`: reference answer and format (a scorer self-check listing references that score 0 against themselves) | Archived notebook 14 | `05-03-18-political-release.pdf`, `2312.04350v3.pdf` |
| 3. Named in archived work | Document name only | Archived notebooks (listed by the E5 spec as touched) | `RAR.pdf` |
| 2. Per-document metadata | The SHA-256 of the PDF bytes (no text, image or page extracted), computed so that the application's test-pool guard can also refuse the file under another name; and the list of all 135 document names (`resources/mmlongbench_doc_documents.json`, built from the `doc_id` column only) | Application layer, 2026-11-25 | `PH_2016.06.08_Economy-Final.pdf` (hash); all (names, level 0) |
| 2–4. Final evaluation, step 1 (approved, spec `experiments/specs/final_evaluation_v1.json`, commit `1c54a3e`) | 2026-11-25: all 111 pool PDFs downloaded at the pinned revision; per-document size, SHA-256 and page count; per-page native text, OCR text, 768-px renders and ColQwen2 page embeddings (indexing). **No question, answer or evidence read at this step.** | Notebook 09, `index` mode | the 111 evaluation documents |
| — | 2026-11-26: the index was frozen and committed (`experiments/frozen/final_index`) before any question was read. 110 documents (`mi_phone.pdf` excluded, D1), 5,554 pages | Notebook 09 | the 110 evaluation documents |
| 4. System outputs | **None.** No retriever ranking, model reply or score has been produced for any pool question. The archived matches are scorer self-checks on reference strings. | — | — |

## Consequences for the final evaluation

1. **Exclude the four question-level-touched documents**, as E5 already did for its held-out selection:
   - `PH_2016.06.08_Economy-Final.pdf`
   - `05-03-18-political-release.pdf`
   - `2312.04350v3.pdf`
   - `RAR.pdf`

   This leaves **111 documents**. Their exact question counts are computed only when the final-evaluation specification is frozen.
2. **Keep the three documents whose page count was seen.** A page count is frame metadata, not content.
   - Any page cap for the final evaluation must be fixed in its specification before indexing.
   - E5's 100-page cap was a laptop-compute rule. With GPU indexing it is not needed. Note that it would exclude long 10-Ks, which are central to the product scope.
3. **Use the pool once.** Run the frozen baseline, and any frozen improvement, in the same session; report pre-registered metrics; do no per-question error analysis on the pool beyond blind scoring adjudication.
4. **No split of the pool now.** The owner's decision of 2026-11-25 is to preserve it whole; see `docs/baseline_b1_specification.md` §6 for the reasoning.
