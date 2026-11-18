"""Schema checks for the evaluation annotations.

These tests encode the rules in data/annotations/README.md so that a
typo in a CSV (an unknown label, a page number past the end of the PDF, a
"verified" row with no verifier) fails loudly instead of silently skewing
evaluation results later.

Run from the repository root:
    pytest tests/test_annotations.py -v
"""

import csv
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
ANNOTATIONS = REPO_ROOT / "data" / "annotations"
DOCUMENTS_CSV = ANNOTATIONS / "documents.csv"
QUESTIONS_CSV = ANNOTATIONS / "questions.csv"
EXAMPLES_CSV = ANNOTATIONS / "examples" / "questions_illustrative.csv"

# --- Schema (keep in sync with data/annotations/README.md) ------------------

DOCUMENT_COLUMNS = [
    "doc_id", "file_path", "title", "doc_category", "source_kind", "page_count",
    "language", "provenance", "usage_rights", "known_content", "status", "notes",
]
QUESTION_COLUMNS = [
    "question_id", "doc_id", "split", "question", "question_type",
    "evidence_modality", "evidence_pages", "reference_answer", "answer_type",
    "evidence_note", "annotator", "verified_by", "status", "notes",
]

SOURCE_KINDS = {"born_digital", "scanned", "mixed"}
CONTENT_TYPES = {"text", "table", "figure", "equation", "scanned_text"}
DOCUMENT_STATUSES = {"candidate", "selected", "excluded"}

SPLITS = {"dev", "test"}
QUESTION_TYPES = {"lookup", "numeric", "comparison", "multi_hop", "unanswerable"}
EVIDENCE_MODALITIES = CONTENT_TYPES | {"multiple"}
ANSWER_TYPES = {"short_text", "number", "yes_no", "list", "none"}
QUESTION_STATUSES = {"draft", "verified", "rejected"}

DOC_ID = re.compile(r"^D\d{3}$")
QUESTION_ID = re.compile(r"^Q\d{4}$")
PAGE_LIST = re.compile(r"^\d+(;\d+)*$")


def read_csv(path):
    """Return (header, rows) where rows are dicts keyed by column name."""
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return reader.fieldnames, list(reader)


def load_documents():
    _, rows = read_csv(DOCUMENTS_CSV)
    return {row["doc_id"]: row for row in rows}


def question_errors(row, documents):
    """Return a list of rule violations for one question row (empty = valid)."""
    errors = []
    qid = row["question_id"]

    def require(condition, message):
        if not condition:
            errors.append(f"{qid}: {message}")

    require(QUESTION_ID.match(qid), "question_id must look like Q0001")
    require(row["doc_id"] in documents, f"unknown doc_id {row['doc_id']!r}")
    require(row["split"] in SPLITS, f"split must be one of {sorted(SPLITS)}")
    require(row["question"].strip(), "question is empty")
    require(row["question_type"] in QUESTION_TYPES, "invalid question_type")
    require(row["answer_type"] in ANSWER_TYPES, "invalid answer_type")
    require(row["annotator"].strip(), "annotator is empty")
    require(row["status"] in QUESTION_STATUSES, "invalid status")

    if row["question_type"] == "unanswerable":
        # An unanswerable question has no evidence and nothing to score against.
        for column in ("evidence_modality", "evidence_pages", "reference_answer"):
            require(not row[column].strip(), f"{column} must be empty when unanswerable")
        require(row["answer_type"] == "none", "answer_type must be 'none' when unanswerable")
    else:
        require(row["evidence_modality"] in EVIDENCE_MODALITIES, "invalid evidence_modality")
        require(row["reference_answer"].strip(), "reference_answer is empty")
        require(row["evidence_note"].strip(), "evidence_note is empty")
        require(row["answer_type"] != "none", "answer_type 'none' is only for unanswerable")
        pages = row["evidence_pages"].strip()
        if not PAGE_LIST.match(pages):
            errors.append(f"{qid}: evidence_pages must be like '12' or '12;13', got {pages!r}")
        elif row["doc_id"] in documents:
            page_count = int(documents[row["doc_id"]]["page_count"])
            for page in map(int, pages.split(";")):
                require(1 <= page <= page_count, f"page {page} outside 1..{page_count}")

    if row["status"] == "verified":
        # Verification means a human checked the row against the PDF.
        verifier = row["verified_by"].strip()
        require(verifier, "verified rows need verified_by")
        require(verifier != "ai-draft", "an AI draft cannot be its own verifier")

    return errors


# --- documents.csv ----------------------------------------------------------

def test_documents_header():
    header, _ = read_csv(DOCUMENTS_CSV)
    assert header == DOCUMENT_COLUMNS


def test_documents_rows_are_valid():
    _, rows = read_csv(DOCUMENTS_CSV)
    ids = [row["doc_id"] for row in rows]
    assert len(ids) == len(set(ids)), "duplicate doc_id"
    for row in rows:
        doc = row["doc_id"]
        assert DOC_ID.match(doc), f"{doc}: doc_id must look like D001"
        assert row["source_kind"] in SOURCE_KINDS, f"{doc}: invalid source_kind"
        assert row["status"] in DOCUMENT_STATUSES, f"{doc}: invalid status"
        assert row["page_count"].isdigit() and int(row["page_count"]) > 0, f"{doc}: bad page_count"
        content = set(row["known_content"].split(";"))
        assert content <= CONTENT_TYPES, f"{doc}: unknown known_content {content - CONTENT_TYPES}"
        for column in ("title", "provenance", "usage_rights", "language"):
            assert row[column].strip(), f"{doc}: {column} is empty"


def test_documents_match_pdf_files():
    """file_path exists and page_count matches the real PDF."""
    pymupdf = pytest.importorskip("pymupdf")
    for doc in load_documents().values():
        path = REPO_ROOT / doc["file_path"]
        assert path.is_file(), f"{doc['doc_id']}: missing file {doc['file_path']}"
        with pymupdf.open(path) as pdf:
            assert pdf.page_count == int(doc["page_count"]), (
                f"{doc['doc_id']}: page_count {doc['page_count']} != actual {pdf.page_count}"
            )


# --- questions.csv and the illustrative examples ------------------------------

@pytest.mark.parametrize("path", [QUESTIONS_CSV, EXAMPLES_CSV], ids=["questions", "examples"])
def test_question_header(path):
    header, _ = read_csv(path)
    assert header == QUESTION_COLUMNS


@pytest.mark.parametrize("path", [QUESTIONS_CSV, EXAMPLES_CSV], ids=["questions", "examples"])
def test_question_rows_are_valid(path):
    documents = load_documents()
    _, rows = read_csv(path)
    ids = [row["question_id"] for row in rows]
    assert len(ids) == len(set(ids)), "duplicate question_id"
    errors = [error for row in rows for error in question_errors(row, documents)]
    assert not errors, "\n".join(errors)


def test_evaluation_questions_use_selected_documents():
    """Only documents the team has selected may enter the evaluation set."""
    documents = load_documents()
    _, rows = read_csv(QUESTIONS_CSV)
    for row in rows:
        doc = documents.get(row["doc_id"])
        assert doc is None or doc["status"] == "selected", (
            f"{row['question_id']}: document {row['doc_id']} is not 'selected'"
        )


def test_examples_are_never_marked_verified():
    """Illustrative rows must not be mistaken for ground truth."""
    _, rows = read_csv(EXAMPLES_CSV)
    for row in rows:
        assert row["status"] == "draft", f"{row['question_id']}: examples must stay 'draft'"
        assert row["notes"].startswith("ILLUSTRATIVE"), f"{row['question_id']}: mark as ILLUSTRATIVE"


def test_validator_catches_bad_rows():
    """The validator itself must reject broken rows, otherwise the tests above prove nothing."""
    documents = {"D001": {"page_count": "10"}}
    good = {
        "question_id": "Q0001", "doc_id": "D001", "split": "dev", "question": "What?",
        "question_type": "lookup", "evidence_modality": "text", "evidence_pages": "3",
        "reference_answer": "42", "answer_type": "number", "evidence_note": "first bullet",
        "annotator": "ab", "verified_by": "", "status": "draft", "notes": "",
    }
    assert question_errors(good, documents) == []

    bad_cases = {
        "page past end of PDF": {"evidence_pages": "11"},
        "page zero (0-based mistake)": {"evidence_pages": "0"},
        "comma-separated pages": {"evidence_pages": "3,4"},
        "unknown modality": {"evidence_modality": "chart"},
        "unknown document": {"doc_id": "D999"},
        "verified without verifier": {"status": "verified"},
        "AI self-verification": {"status": "verified", "verified_by": "ai-draft"},
        "unanswerable with evidence": {"question_type": "unanswerable", "answer_type": "none"},
        "missing answer": {"reference_answer": ""},
    }
    for name, change in bad_cases.items():
        assert question_errors({**good, **change}, documents), f"validator missed: {name}"
