# Annotation Guide

This guide defines how to build the evaluation set for VisualDoc AI: which
documents are used, which questions are asked, and what counts as a correct
answer and correct evidence.

The evaluation set exists to answer one research question (see the root
`README.md`): **when does giving a model the page image (multimodal) beat
giving it only extracted text (text-only)?** Every field below exists so that
results can be sliced along that question.

> **Status:** `questions.csv` is intentionally empty. No question in this
> repository is ground truth until a human has verified it against the PDF
> (`status = verified`). The rows in `examples/` are AI-drafted illustrations
> of the format, not evaluation data.

---

## 1. Files

| File | Purpose |
| --- | --- |
| `documents.csv` | One row per document in the corpus. |
| `questions.csv` | One row per question. The evaluation set. |
| `examples/questions_illustrative.csv` | Format examples. Never scored. |
| `../../tests/test_annotations.py` | Automated schema checks. Run before every commit that touches annotations. |

Both CSVs are UTF-8, comma-separated, with a header row. Use a spreadsheet
editor or a text editor; if a field contains a comma, the editor must quote it
(LibreOffice, Excel and Python's `csv` module do this automatically).

---

## 2. `documents.csv` schema

| Column | Required | Allowed values / format | Meaning |
| --- | --- | --- | --- |
| `doc_id` | yes | `D` + 3 digits, unique (`D001`) | Stable identifier, referenced by `questions.csv`. Never reuse a retired ID. |
| `file_path` | yes | Path relative to repo root | Where the PDF lives. |
| `title` | yes | Free text | Human-readable title. |
| `doc_category` | yes | Free text, lowercase (`lecture_slides`, `letter`, `financial_report`, …) | Genre; used to report results per genre. |
| `source_kind` | yes | `born_digital`, `scanned`, `mixed` | How the PDF was produced. `mixed` = some pages born-digital and some scanned, or a scan with a full searchable (OCR) text layer. A scan with a stray native heading or stamp is still `scanned` (note it in `notes`). |
| `page_count` | yes | Positive integer | Must equal the PDF's page count (checked by the tests). |
| `language` | yes | ISO 639-1 code (`en`, `fr`) | Main language. Determines OCR language model. |
| `provenance` | yes | Free text | Where the file came from (URL, course, generator). |
| `usage_rights` | yes | Free text | What we are allowed to do with it. Write `unverified` if unknown. |
| `known_content` | yes | `;`-separated subset of `text`, `table`, `figure`, `equation`, `scanned_text` | Content types confirmed present (not guessed). |
| `status` | yes | `candidate`, `selected`, `excluded` | Only `selected` documents may have questions in `questions.csv`. |
| `notes` | no | Free text | Anything an annotator should know (e.g. tricky pages). |

---

## 3. `questions.csv` schema

| Column | Required | Allowed values / format | Meaning |
| --- | --- | --- | --- |
| `question_id` | yes | `Q` + 4 digits, unique (`Q0001`) | Stable identifier. Never renumber. |
| `doc_id` | yes | An existing `doc_id` | The document the question is about. |
| `split` | yes | `dev`, `test` | See §6. |
| `question` | yes | Free text | Self-contained question, answerable from the document alone. |
| `question_type` | yes | `lookup`, `numeric`, `comparison`, `multi_hop`, `unanswerable` | The *reasoning* required (§4). |
| `evidence_modality` | if answerable | `text`, `table`, `figure`, `equation`, `scanned_text`, `multiple` | *Where* the answer lives (§4). Empty for `unanswerable`. |
| `evidence_pages` | if answerable | `;`-separated 1-based page numbers (`12` or `12;13`) | All pages needed to answer. Empty for `unanswerable`. |
| `reference_answer` | if answerable | Free text | The shortest complete correct answer. Empty for `unanswerable`. |
| `answer_type` | yes | `short_text`, `number`, `yes_no`, `list`, `none` | How the answer will be scored (§5). `none` only for `unanswerable`. |
| `evidence_note` | if answerable | Free text | Where on the page: "table *Usual conjugate pairs*, row Poisson". Lets a verifier find it in seconds. |
| `annotator` | yes | Initials, or `ai-draft` | Who wrote the question. |
| `verified_by` | if verified | Initials | Who checked it against the PDF. Cannot be `ai-draft`. |
| `status` | yes | `draft`, `verified`, `rejected` | Only `verified` rows are used in evaluation. |
| `notes` | no | Free text | Ambiguities, alternative accepted answers, units. |

### Page numbering

`evidence_pages` uses the **physical page index, starting at 1** — the number
your PDF viewer shows in its page box, and `doc[page - 1]` in PyMuPDF. It is
**not** the printed page label. In `data/documents/apple_10k.pdf`, for example,
physical page 32 is printed as "Form 10-K | 21" because of the cover and
table of contents. Citations produced by the system will be compared to this field, so
one convention must be used everywhere.

---

## 4. Two independent labels: reasoning type and evidence modality

Each question gets two labels, and they are deliberately orthogonal:

- `question_type` — **what kind of reasoning** is needed.
- `evidence_modality` — **what kind of content** holds the answer.

Keeping them separate lets the evaluation ask "does multimodal help on *table*
questions?" independently of "does it help on *comparison* questions?". If
they were merged into one label ("chart question"), those effects could not be
told apart.

### `question_type`

| Value | Definition | Example |
| --- | --- | --- |
| `lookup` | One fact, stated in one place. | "Which law gives states primary enforcement responsibility?" |
| `numeric` | The answer is a number, read or computed. | "What was total net sales in fiscal 2023?" |
| `comparison` | Compare two or more items or values. | "Which curve is higher for large τ²?" |
| `multi_hop` | Combine facts from two or more locations. | "The model defined on one slide uses which conjugate prior, according to the summary table on another?" |
| `unanswerable` | The document does not contain the answer. | "Which software does the deck recommend?" |

Out of scope for the MVP: open-ended summaries ("summarise chapter 2"). They
cannot be scored reliably with a small annotated set.

### `evidence_modality`

Label the content a reader must *look at* to answer:

| Value | Use when the answer is in… |
| --- | --- |
| `text` | Ordinary born-digital prose or bullet points. |
| `table` | A table's cells (born-digital). |
| `figure` | A chart, plot, diagram, or photo — including text that exists only inside the image. |
| `equation` | Mathematical notation (often extracted badly, e.g. `∫` → `R`). |
| `scanned_text` | Text that exists only as pixels on a scanned page. |
| `multiple` | Two or more of the above are required. |

Tip: if you are unsure whether text is native or scanned, open the page in
`archive/notebooks/experiments/pdf_anatomy.ipynb` style — `page.get_text("words")` returns nothing
for text that exists only as pixels.

---

## 5. Writing reference answers

- **Read the answer off the page.** Never write an answer from memory or
  general knowledge, and never copy a model's answer.
- **Shortest complete answer.** "Ga(a + s, b + n)", not a sentence.
- **Numbers:** include units and scale as printed ("$383,285 million").
  Note the expected precision in `notes` if rounding is acceptable.
- **Facts repeated on several pages:** list every page where the answer is
  fully stated (Apple's total net sales appears on at least pages 32, 33,
  40, 47 and 61), or narrow the question to one location. Otherwise a
  correct citation to another page is scored as wrong.
- **`yes_no`:** answer `yes` or `no` only.
- **`list`:** `;`-separated items; note in `notes` whether order matters.
- **Alternative answers:** if several phrasings are equally correct, put the
  main one in `reference_answer` and the others in `notes`
  (`also accept: SDWA`).
- **If you cannot decide what the correct answer is, the question is
  ambiguous** — rewrite it or mark it `rejected`.

---

## 6. Workflow

1. **Select documents.** Set `status = selected` in `documents.csv`. Check
   `usage_rights` first: anything committed to this repository is public.
2. **Write questions before building the pipeline.** Questions written after
   seeing system output tend to favour what the system already does well.
3. **Draft.** Open the PDF, find the evidence, write the question, the
   answer, `evidence_pages`, and `evidence_note`. Set `status = draft`.
4. **Verify (separate pass).** Re-open the PDF at `evidence_pages` and check:
   - the answer is on those pages and is correct;
   - the question has exactly one correct answer;
   - the question does not leak the answer or the page number;
   - for `unanswerable`: search the *whole* document, including images. A
     text search alone misses content inside figures and scans.

   Then set `verified_by` and `status = verified`. Ideally the verifier is a
   different person. For a solo project, verify on a different day, starting
   from the PDF rather than from memory, and say so in the project report.
5. **Assign a split.** Put roughly 20–30% of verified questions in `dev` and
   the rest in `test`. Tune prompts, chunk sizes and thresholds on `dev`
   only. Look at `test` results only for final comparisons; otherwise the
   reported numbers are optimistic.
6. **Run the checks:** `pytest tests/test_annotations.py`.

### AI-drafted questions

A language model may propose candidate questions to speed up drafting. Such
rows must have `annotator = ai-draft` and `status = draft`, and they become
evaluation data only after a human performs step 4. Do not let the model
under evaluation draft questions: it would bias the set toward questions it
can answer.

---

## 7. Coverage targets for the MVP

These are targets, not requirements. Adjust after the first annotation pass.

- 2–4 selected documents, including at least one scanned and one with
  tables/figures.
- About 60–100 verified questions in total.
- Every `evidence_modality` value except `multiple` should have at least
  ~10 questions. With fewer, per-category differences are noise.
- About 10% `unanswerable`, to measure whether the system abstains instead of
  hallucinating.

---

## 8. Quality checklist (per question)

- [ ] Answerable from the document alone, without outside knowledge.
- [ ] One unambiguous correct answer (or alternatives listed in `notes`).
- [ ] `evidence_pages` lists *all* pages needed, using physical page numbers.
- [ ] `evidence_modality` describes where the evidence actually is, not where
      you expect a parser to find it.
- [ ] No page numbers or answer fragments leaked in the question.
- [ ] Verified against the PDF in a separate pass.
