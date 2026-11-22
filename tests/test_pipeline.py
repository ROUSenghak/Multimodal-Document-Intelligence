"""End-to-end demonstration, offline: PDF -> text -> BM25 -> images -> (stand-in) model -> citation check."""

import json
from types import SimpleNamespace

import pymupdf
import pytest

from conftest import LOCAL_DOCUMENTS
from visualdoc import pipeline
from visualdoc.pipeline import OfflineReader, answer_question, main

DEMO_PDF = LOCAL_DOCUMENTS / "ch2.pdf"
DEMO_QUESTION = "What does Cromwell's rule say about prior probability?"


def test_offline_demo_runs_end_to_end(capsys):
    result = main([str(DEMO_PDF), DEMO_QUESTION])
    printed = json.loads(capsys.readouterr().out)
    assert result.page_count == 68 and result.ocr_pages == 6
    assert result.retrieved_pages[0] == 9  # the slide that states Cromwell's rule
    # Five 4:3 slides at 768 px (25,501 image tokens each) exceed the context: the 5th-ranked page is dropped.
    assert len(result.retrieved_pages) == 5 and result.supplied_pages == result.retrieved_pages[:4] and result.dropped_pages == result.retrieved_pages[4:]
    assert result.estimated_prompt_tokens == 1_000 + 4 * 25_501
    assert result.reply.answer == OfflineReader.ANSWER and result.reply.cited_pages == [9] and result.reply.error is None
    assert result.citations.ok
    assert printed["citations"]["ok"] is True and printed["request_fingerprint"] == result.request_fingerprint
    assert "base64" not in json.dumps(printed)  # the printed result never contains image payloads


def test_the_model_receives_the_retrieved_pages_as_tagged_768_px_images():
    reader = OfflineReader()
    result = answer_question(DEMO_PDF, DEMO_QUESTION, reader, top_k=3)
    (request,) = reader.requests
    content = request["messages"][1]["content"]
    assert [p["text"] for p in content if p["type"] == "text"][1:] == [f"[Page {n}]" for n in result.supplied_pages]
    images = [p for p in content if p["type"] == "image_url"]
    assert len(images) == 3 and all(p["image_url"]["detail"] == "high" for p in images)
    assert 0 < result.cost_upper_usd < 0.05


def test_an_invalid_citation_is_flagged_not_hidden():
    def cites_printed_page(**request):
        tags = [p["text"] for p in request["messages"][1]["content"] if p["type"] == "text" and p["text"].startswith("[Page")]
        first = int(tags[0][6:-1])
        reply = json.dumps({"answer": "never give probability 0", "cited_pages": [first - 1]})
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=reply), finish_reason="stop")], model="test")

    result = answer_question(DEMO_PDF, DEMO_QUESTION, cites_printed_page, top_k=1)
    assert result.supplied_pages == [9] and result.citations.invalid == (8,)
    assert result.citations.off_by_one and not result.citations.ok


def test_an_unparseable_reply_is_reported():
    broken = lambda **_: SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="Page 9 says so."), finish_reason="stop")], model="test")
    result = answer_question(DEMO_PDF, DEMO_QUESTION, broken, top_k=1)
    assert result.reply.error.startswith("unparseable") and result.citations.missing


def test_pages_that_overflow_the_context_are_dropped(tmp_path):
    pdf = tmp_path / "letters.pdf"
    document = pymupdf.open()
    for number in range(6):
        document.new_page(width=612, height=792).insert_text((72, 100), f"budget report section {number} " * 10)
    document.save(pdf)
    document.close()
    result = answer_question(pdf, "budget report", OfflineReader(), top_k=6)
    assert len(result.retrieved_pages) == 6 and len(result.supplied_pages) == 4 and len(result.dropped_pages) == 2
    assert result.supplied_pages == result.retrieved_pages[:4]


def test_failure_cases(tmp_path, monkeypatch):
    with pytest.raises(FileNotFoundError):
        answer_question(tmp_path / "missing.pdf", DEMO_QUESTION, OfflineReader())
    with pytest.raises(ValueError, match="question is empty"):
        answer_question(DEMO_PDF, "  ", OfflineReader())
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(SystemExit, match="OPENAI_API_KEY"):
        main([str(DEMO_PDF), DEMO_QUESTION, "--live"])  # refuses before any network call
    assert pipeline.OfflineReader().requests == []
