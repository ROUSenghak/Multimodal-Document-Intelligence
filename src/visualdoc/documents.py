"""PDF processing for the application: page text for retrieval, page images for the reader.

The text policy is notebook 00's, the one behind every frozen result (E0 text
conditions, BM25 Recall@5 0.689, E3 page texts):

- take the native text layer (``get_text("text", sort=True)``);
- if it has fewer than 30 whitespace-separated words, replace it with a
  full-page Tesseract OCR at 150 dpi (PyMuPDF's built-in engine, model in
  ``resources/tessdata``).

``visualdoc.parsing`` holds an older, different policy (NATIVE / OCR / HYBRID /
REVIEW routing by image coverage, OCR at 200 dpi). It is kept unchanged as
reference, but it is not used here: on the benchmark's vector-outlined
document (``bdf54dxa.pdf``) it routes 53 of 54 pages to REVIEW and returns no
text, while this policy recovers a median of 158 words per page.

Images are rendered at the resolution adopted by E1 and retained by E2 and E3:
the whole page fitted in a 768 x 1536 px box (short x long side), opaque RGB PNG.
"""

import hashlib
from dataclasses import dataclass
from numbers import Integral
from pathlib import Path

import pymupdf

OCR_MIN_NATIVE_WORDS = 30
OCR_DPI = 150
OCR_LANGUAGE = "eng"
IMAGE_SHORT_SIDE_PX = 768
IMAGE_LONG_SIDE_PX = 1536
DEFAULT_TESSDATA_DIR = Path(__file__).resolve().parents[2] / "resources" / "tessdata"


@dataclass(frozen=True)
class PageText:
    """The text the pipeline uses for one page, and where it came from."""

    page: int  # 1-based physical page number
    text: str
    native_words: int
    ocr_used: bool


@dataclass(frozen=True)
class DocumentProfile:
    """Content identity and native-text readiness, computed without OCR or rendering."""

    sha256: str
    page_count: int
    native_words_per_page: tuple[int, ...]
    born_digital: bool


def sha256_file(path: str | Path) -> str:
    """Content key used by caches; changing the path alone does not change identity."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inspect_document(path: str | Path, *, min_native_words: int = OCR_MIN_NATIVE_WORDS) -> DocumentProfile:
    """Record native words/page; born-digital means every page clears the OCR threshold."""
    if min_native_words < 0:
        raise ValueError("min_native_words cannot be negative")
    with open_pdf(path) as document:
        words = tuple(len(page.get_text("text", sort=True).split()) for page in document)
    return DocumentProfile(sha256_file(path), len(words), words, bool(words) and all(n >= min_native_words for n in words))


def open_pdf(path: str | Path) -> pymupdf.Document:
    """Open a PDF with clear errors for a missing, unreadable or encrypted file."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"PDF not found: {path}")
    try:
        document = pymupdf.open(path)
    except Exception as error:  # PyMuPDF raises its own error types for corrupt files
        raise ValueError(f"cannot open {path.name} as a PDF: {error}") from error
    if not document.is_pdf:
        document.close()
        raise ValueError(f"{path.name} is not a PDF")
    if document.needs_pass:
        document.close()
        raise ValueError(f"{path.name} is encrypted; decrypt it first")
    return document


def get_page(document: pymupdf.Document, page_number: int) -> pymupdf.Page:
    """Return the page with this 1-based number.

    ``document[-1]`` is valid Python and silently returns the last page, so 0,
    negative and out-of-range numbers are rejected explicitly.
    """
    if isinstance(page_number, bool) or not isinstance(page_number, Integral) or not 1 <= page_number <= document.page_count:
        raise IndexError(f"page {page_number!r} is not a 1-based page number of a {document.page_count}-page PDF")
    return document[int(page_number) - 1]


def page_text(
    page: pymupdf.Page,
    *,
    ocr_min_native_words: int = OCR_MIN_NATIVE_WORDS,
    ocr_dpi: int = OCR_DPI,
    tessdata: str | Path | None = None,
) -> PageText:
    """Native text, or full-page OCR when the native layer has too few words."""
    native = page.get_text("text", sort=True)
    native_words = len(native.split())
    if native_words >= ocr_min_native_words:
        return PageText(page.number + 1, native, native_words, ocr_used=False)

    tessdata_dir = DEFAULT_TESSDATA_DIR if tessdata is None else Path(tessdata)
    model = tessdata_dir / f"{OCR_LANGUAGE}.traineddata"
    if not model.is_file():
        raise FileNotFoundError(f"OCR model not found: {model} (page {page.number + 1} has {native_words} native words and needs OCR)")
    ocr_page = page.get_textpage_ocr(language=OCR_LANGUAGE, dpi=ocr_dpi, full=True, tessdata=str(tessdata_dir))
    return PageText(page.number + 1, page.get_text("text", textpage=ocr_page, sort=True), native_words, ocr_used=True)


def extract_pages(path: str | Path, **options) -> list[PageText]:
    """Text of every page of a PDF, in page order (see ``page_text`` for the options)."""
    with open_pdf(path) as document:
        return [page_text(page, **options) for page in document]


def render_page_png(
    page: pymupdf.Page,
    short_side_px: int = IMAGE_SHORT_SIDE_PX,
    long_side_px: int = IMAGE_LONG_SIDE_PX,
) -> bytes:
    """Render the whole page (crop box, rotation applied) as a PNG fitted in the box."""
    if short_side_px <= 0 or long_side_px < short_side_px:
        raise ValueError("need 0 < short_side_px <= long_side_px")
    width, height = page.rect.width, page.rect.height
    zoom = min(short_side_px / min(width, height), long_side_px / max(width, height))
    return page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False).tobytes("png")


def render_pages(path: str | Path, page_numbers: list[int], **options) -> dict[int, bytes]:
    """PNG bytes of the requested 1-based pages (see ``render_page_png`` for the options)."""
    with open_pdf(path) as document:
        return {number: render_page_png(get_page(document, number), **options) for number in page_numbers}
