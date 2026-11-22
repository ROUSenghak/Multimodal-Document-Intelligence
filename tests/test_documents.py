"""PDF processing: text policy, OCR fallback, page numbering, rendering, and parity with frozen runs."""

import hashlib

import pymupdf
import pytest

from conftest import E1_SPEC, E3_SPEC, FROZEN_E0_IMAGE_SETTINGS, FROZEN_E1_LOG, LOCAL_DOCUMENTS, read_json, read_jsonl
from visualdoc import documents
from visualdoc.documents import extract_pages, get_page, open_pdf, page_text, render_page_png, render_pages


def make_pdf(path, pages_text):
    document = pymupdf.open()
    for text in pages_text:
        page = document.new_page(width=612, height=792)
        if text:
            page.insert_textbox(pymupdf.Rect(72, 72, 540, 720), text, fontsize=11)
    document.save(path)
    document.close()
    return path


def test_policy_constants_equal_the_frozen_settings():
    frozen = read_json(FROZEN_E0_IMAGE_SETTINGS)
    e1_768 = read_json(E1_SPEC)["conditions"]["E1_768"]
    assert (documents.OCR_MIN_NATIVE_WORDS, documents.OCR_DPI) == (frozen["ocr_min_native_words"], frozen["ocr_dpi"]) == (30, 150)
    assert (documents.IMAGE_SHORT_SIDE_PX, documents.IMAGE_LONG_SIDE_PX) == (e1_768["render_short_side_px"], e1_768["render_long_side_px"])


def test_native_page_keeps_its_text_layer():
    with open_pdf(LOCAL_DOCUMENTS / "ch2.pdf") as document:
        result = page_text(get_page(document, 9))
    assert result.page == 9 and not result.ocr_used and result.native_words >= 30
    assert "Cromwell" in result.text


def test_page_without_text_layer_is_ocred():
    with open_pdf(LOCAL_DOCUMENTS / "scanned.pdf") as document:
        result = page_text(get_page(document, 2))
    assert result.ocr_used and result.native_words == 0
    assert len(result.text.split()) > 50  # a scanned letter, read by Tesseract


def test_threshold_is_strict_below_30_words(tmp_path):
    pdf = make_pdf(tmp_path / "words.pdf", [" ".join(["word"] * 30), " ".join(["word"] * 29)])
    with open_pdf(pdf) as document:
        thirty, twenty_nine = page_text(document[0]), page_text(document[1])
    assert (thirty.native_words, thirty.ocr_used) == (30, False)
    assert (twenty_nine.native_words, twenty_nine.ocr_used) == (29, True)


def test_missing_ocr_model_fails_only_when_ocr_is_needed(tmp_path):
    with open_pdf(LOCAL_DOCUMENTS / "ch2.pdf") as document:
        assert not page_text(get_page(document, 9), tessdata=tmp_path).ocr_used  # native page: model not needed
    with open_pdf(LOCAL_DOCUMENTS / "scanned.pdf") as document:
        with pytest.raises(FileNotFoundError, match="eng.traineddata"):
            page_text(get_page(document, 2), tessdata=tmp_path)


def test_numpy_page_numbers_are_accepted():
    np = pytest.importorskip("numpy")
    with open_pdf(LOCAL_DOCUMENTS / "scanned.pdf") as document:
        assert get_page(document, np.int64(2)).number == 1


def test_extract_pages_covers_every_page_in_order():
    pages = extract_pages(LOCAL_DOCUMENTS / "scanned.pdf")
    assert [p.page for p in pages] == [1, 2, 3] and all(p.ocr_used for p in pages)


@pytest.mark.parametrize("bad", [0, -1, 4, 1.0, True, "1"])
def test_page_numbers_are_one_based_and_checked(bad):
    with open_pdf(LOCAL_DOCUMENTS / "scanned.pdf") as document:
        with pytest.raises(IndexError):
            get_page(document, bad)


def test_unreadable_inputs_have_clear_errors(tmp_path):
    with pytest.raises(FileNotFoundError, match="PDF not found"):
        open_pdf(tmp_path / "missing.pdf")
    (tmp_path / "notes.pdf").write_text("not a pdf")
    with pytest.raises(ValueError, match="cannot open|not a PDF"):
        open_pdf(tmp_path / "notes.pdf")
    encrypted = pymupdf.open()
    encrypted.new_page()
    encrypted.save(tmp_path / "locked.pdf", encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="secret", owner_pw="secret")
    with pytest.raises(ValueError, match="encrypted"):
        open_pdf(tmp_path / "locked.pdf")


def test_render_fits_the_768_by_1536_box():
    with open_pdf(LOCAL_DOCUMENTS / "ch2.pdf") as document:
        page = get_page(document, 9)
        pixmap = pymupdf.Pixmap(render_page_png(page))
    assert min(pixmap.width, pixmap.height) <= 768 and max(pixmap.width, pixmap.height) <= 1536
    assert 768 in (pixmap.width, pixmap.height) or 1536 in (pixmap.width, pixmap.height)  # one side touches the box
    assert pixmap.alpha == 0
    with open_pdf(LOCAL_DOCUMENTS / "ch2.pdf") as document:
        with pytest.raises(ValueError):
            render_page_png(get_page(document, 9), short_side_px=800, long_side_px=600)


# --- Parity with the frozen experiments (needs the git-ignored benchmark PDFs) -------------------

E3_TEXT_PAGES = [
    ("PG_2020.05.21_International-Cooperation-COVID_FINAL.pdf", 12, False),  # native text
    ("germanwingsdigitalcrisisanalysis-150403064828-conversion-gate01_95.pdf", 16, True),  # OCR, slide image
    ("bdf54dxa.pdf", 11, True),  # OCR, text drawn as vector outlines
]


@pytest.mark.parametrize(("doc_id", "page", "ocr"), E3_TEXT_PAGES)
def test_page_text_equals_the_text_pinned_by_the_e3_spec(mmlb_pdf, doc_id, page, ocr):
    pinned = read_json(E3_SPEC)["text_extraction"]["text_sha256_by_doc_page"].get(f"{doc_id}|{page}")
    if pinned is None:
        pytest.skip("page not pinned by the E3 spec")
    with open_pdf(mmlb_pdf(doc_id)) as document:
        result = page_text(get_page(document, page))
    assert result.ocr_used is ocr
    assert hashlib.sha256(result.text.strip().encode()).hexdigest() == pinned


def test_render_equals_the_frozen_e1_768_px_image(mmlb_pdf):
    record = next(r for r in read_jsonl(FROZEN_E1_LOG) if (r["replicate_id"], r["qid"], r["condition"]) == ("main_r1", "mmlb-0729", "E1_768"))
    pngs = render_pages(mmlb_pdf(record["doc_id"]), record["supplied_pages"])
    assert [hashlib.sha256(png).hexdigest() for png in pngs.values()] == record["image_sha256"]
