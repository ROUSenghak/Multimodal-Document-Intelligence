"""Inspect PDF pages, select an extraction route, and extract their text.

The functions in this module preserve the behavior first prototyped in
``notebooks/prototypes/page_extraction.ipynb``. The routing thresholds are
heuristics validated on the repository's sample documents, not universal
PDF-classification rules.
"""

from pathlib import Path
from typing import Literal, TypedDict

import pymupdf


ExtractionMethod = Literal["NATIVE", "OCR", "HYBRID", "REVIEW"]


class PageFeatures(TypedDict):
    """Observable features used by the extraction routing heuristic."""

    native_words: int
    image_count: int
    largest_image_fraction: float


DEFAULT_TESSDATA_DIR = Path(__file__).resolve().parents[2] / "resources" / "tessdata"


def inspect_page(page: pymupdf.Page) -> PageFeatures:
    """Return native-word and raster-image coverage features for one page."""
    words = page.get_text("words")
    images = page.get_image_info()
    page_area = page.rect.get_area()

    largest_coverage = max(
        (
            (pymupdf.Rect(image["bbox"]) & page.rect).get_area() / page_area
            for image in images
        ),
        default=0.0,
    )

    return {
        "native_words": len(words),
        "image_count": len(images),
        "largest_image_fraction": round(largest_coverage, 3),
    }


def select_method(features: PageFeatures) -> ExtractionMethod:
    """Choose native extraction, OCR, hybrid OCR, or manual review."""
    words = features["native_words"]
    coverage = features["largest_image_fraction"]

    if coverage >= 0.90:
        if words == 0:
            return "OCR"
        if words < 20:
            return "HYBRID"
        return "REVIEW"

    if words > 0:
        return "NATIVE"

    return "REVIEW"


def extract_page(
    page: pymupdf.Page,
    method: ExtractionMethod | str,
    language: str = "eng",
    tessdata: str | Path | None = None,
) -> str | None:
    """Extract one page according to ``method``.

    ``HYBRID`` preserves native text and OCRs the remaining page; ``OCR``
    re-reads the full rendered page. ``REVIEW`` deliberately returns ``None``
    so callers cannot mistake an uncertain page for an empty page.
    """
    if method == "NATIVE":
        return page.get_text("text")

    if method in ("OCR", "HYBRID"):
        tessdata_dir = DEFAULT_TESSDATA_DIR if tessdata is None else Path(tessdata)
        for lang in language.split("+"):
            model_path = tessdata_dir / f"{lang}.traineddata"
            if not model_path.is_file():
                raise FileNotFoundError(f"OCR language model not found: {model_path}")

        text_page = page.get_textpage_ocr(
            language=language,
            dpi=200,
            full=(method == "OCR"),
            tessdata=str(tessdata_dir),
        )
        return page.get_text("text", textpage=text_page)

    if method == "REVIEW":
        return None

    raise ValueError(f"Unknown extraction method: {method}")

