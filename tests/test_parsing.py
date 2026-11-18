"""Regression tests for the reusable PDF parsing prototype."""

from pathlib import Path

import pymupdf
import pytest

from visualdoc.parsing import extract_page, inspect_page, select_method


REPO_ROOT = Path(__file__).resolve().parents[1]
DOCUMENTS = REPO_ROOT / "data" / "documents"


@pytest.mark.parametrize(
    ("filename", "page_number", "expected"),
    [
        ("ch2.pdf", 9, "NATIVE"),
        ("scanned.pdf", 1, "HYBRID"),
        ("scanned.pdf", 2, "OCR"),
    ],
)
def test_known_pages_follow_expected_routes(filename, page_number, expected):
    with pymupdf.open(DOCUMENTS / filename) as document:
        features = inspect_page(document[page_number - 1])

    assert select_method(features) == expected


def test_native_extraction_returns_slide_text():
    with pymupdf.open(DOCUMENTS / "ch2.pdf") as document:
        text = extract_page(document[8], "NATIVE")

    assert text is not None
    assert "Cromwell" in text


def test_hybrid_ocr_preserves_native_heading():
    with pymupdf.open(DOCUMENTS / "scanned.pdf") as document:
        page = document[0]
        native_text = page.get_text("text")
        hybrid_text = extract_page(page, "HYBRID")

    assert hybrid_text is not None
    assert "SAMPLE LETTER" in hybrid_text
    assert len(hybrid_text.split()) > len(native_text.split())


def test_missing_ocr_model_has_actionable_error(tmp_path):
    with pymupdf.open(DOCUMENTS / "scanned.pdf") as document:
        with pytest.raises(FileNotFoundError, match="fra.traineddata"):
            extract_page(document[1], "OCR", language="fra", tessdata=tmp_path)


def test_review_returns_none():
    with pymupdf.open(DOCUMENTS / "ch2.pdf") as document:
        assert extract_page(document[0], "REVIEW") is None


def test_unknown_method_is_rejected():
    with pymupdf.open(DOCUMENTS / "ch2.pdf") as document:
        with pytest.raises(ValueError, match="Unknown extraction method"):
            extract_page(document[0], "INVALID")

