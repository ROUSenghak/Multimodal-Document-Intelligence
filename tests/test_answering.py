"""VLM answering: prompt and parameters pinned to the frozen runs, request building, context guard, parser, model call."""

import json
from types import SimpleNamespace

import pymupdf
import pytest

from conftest import E1_SPEC, FROZEN_E0_IMAGE_SETTINGS, FROZEN_E1_LOG, MMLB_QUESTIONS, REPO_ROOT, read_json, read_jsonl
from visualdoc import answering
from visualdoc.answering import (
    ask,
    build_request,
    estimate_prompt_tokens,
    image_tokens,
    loggable,
    parse_reply,
    png_size,
    request_fingerprint,
    select_pages_within_context,
)
from visualdoc.documents import render_pages

FROZEN_E3_LOG = REPO_ROOT / "experiments" / "frozen" / "e3" / "run_20261122T143134629529Z_4c62bfc2_full" / "execution_log.jsonl"


def blank_png(width, height):
    return pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, width, height), False).tobytes("png")


def completion(content, finish_reason="stop", model="gpt-4o-mini-2024-07-18"):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content), finish_reason=finish_reason)], model=model)


# --- Pinned to the frozen experiments -------------------------------------------------------------

def test_prompt_and_parameters_equal_the_frozen_image_runs():
    frozen = read_json(FROZEN_E0_IMAGE_SETTINGS)
    model = read_json(E1_SPEC)["model"]
    assert answering.IMAGE_SYSTEM_PROMPT == frozen["image_system_prompt"]
    assert answering.prompt_hash() == frozen["image_prompt_hash"] == model["image_prompt_hash"] == "35ff2e8b91f9"
    assert answering.IMAGE_PROMPT_VERSION == frozen["prompt_version"] == model["image_prompt_version"]
    assert (answering.MODEL, answering.IMAGE_DETAIL) == (model["requested_snapshot"], model["image_detail"])
    assert (answering.TEMPERATURE, answering.MAX_OUTPUT_TOKENS) == (model["temperature"], model["max_output_tokens"])
    assert (answering.IMAGE_BASE_TOKENS, answering.IMAGE_TILE_TOKENS, answering.CONTEXT_WINDOW_TOKENS) == (
        frozen["image_base_tokens"], frozen["image_tile_tokens"], frozen["context_window_tokens"])


def test_parser_reproduces_every_frozen_gpt4o_mini_reply():
    records = read_jsonl(FROZEN_E1_LOG) + read_jsonl(FROZEN_E3_LOG)
    assert len(records) == 113 + 151
    for record in records:
        answer, cited, error = parse_reply(record["raw_response"])
        assert (answer, cited, error) == (record["pred"], record["cited_pages"], record["parse_error"]), record["qid"]


def test_text_allowance_covers_every_frozen_e1_request():
    # The frozen estimate = text tokens (tiktoken) + image tokens; the allowance must cover the text part.
    for record in read_jsonl(FROZEN_E1_LOG):
        images = sum(image_tokens(w, h) for w, h in record["image_dimensions"])
        assert 0 < record["estimated_prompt_tokens"] - images <= answering.TEXT_TOKEN_ALLOWANCE, record["qid"]


def test_request_fingerprint_equals_the_frozen_e1_768_request(mmlb_pdf):
    pd = pytest.importorskip("pandas")
    record = next(r for r in read_jsonl(FROZEN_E1_LOG) if (r["replicate_id"], r["qid"], r["condition"]) == ("main_r1", "mmlb-0729", "E1_768"))
    question = pd.read_parquet(MMLB_QUESTIONS).iloc[int(record["qid"].removeprefix("mmlb-"))]["question"]
    pngs = render_pages(mmlb_pdf(record["doc_id"]), record["supplied_pages"])
    request = build_request(question, list(pngs.items()))
    assert request_fingerprint(request) == record["fingerprint"]


# --- Token estimate and context guard ---------------------------------------------------------------

def test_image_token_rule_matches_documented_examples():
    tiles = lambda w, h: (image_tokens(w, h) - answering.IMAGE_BASE_TOKENS) // answering.IMAGE_TILE_TOKENS
    assert tiles(1024, 1024) == 4 and tiles(2048, 4096) == 6 and tiles(512, 512) == 1
    assert tiles(768, 1366) == 6  # a 16:9 slide at 768 px: 36,835 tokens


def test_five_portrait_768_px_pages_do_not_fit_and_the_last_is_dropped():
    pages = [(n, blank_png(768, 994)) for n in (7, 3, 9, 1, 4)]  # ranked order, US-letter pages at 768 px
    assert estimate_prompt_tokens(pages) > answering.CONTEXT_WINDOW_TOKENS - answering.MAX_OUTPUT_TOKENS
    kept, dropped = select_pages_within_context(pages)
    assert [n for n, _ in kept] == [7, 3, 9, 1] and dropped == [4]
    assert estimate_prompt_tokens(kept) <= answering.CONTEXT_WINDOW_TOKENS - answering.MAX_OUTPUT_TOKENS


def test_context_guard_keeps_a_ranked_prefix_only():
    pages = [(1, blank_png(768, 994)), (2, blank_png(768, 994)), (3, blank_png(100, 100))]
    kept, dropped = select_pages_within_context(pages, max_prompt_tokens=answering.TEXT_TOKEN_ALLOWANCE + 30_000)
    assert [n for n, _ in kept] == [1] and dropped == [2, 3]  # page 3 would fit but is ranked below a page that does not
    assert select_pages_within_context(pages, max_prompt_tokens=10) == ([], [1, 2, 3])


# --- Request building ---------------------------------------------------------------------------

def test_request_layout_and_loggable_form():
    request = build_request("What is shown?", [(4, blank_png(20, 10)), (2, blank_png(10, 20))])
    assert request["messages"][0] == {"role": "system", "content": answering.IMAGE_SYSTEM_PROMPT}
    content = request["messages"][1]["content"]
    assert [part["type"] for part in content] == ["text", "text", "image_url", "text", "image_url"]
    assert content[0]["text"] == "Question: What is shown?\n\nPage images:" and content[1]["text"] == "[Page 4]" and content[3]["text"] == "[Page 2]"
    assert {k: request[k] for k in ("model", "temperature", "max_completion_tokens", "response_format")} == {
        "model": "gpt-4o-mini-2024-07-18", "temperature": 0.0, "max_completion_tokens": 400, "response_format": {"type": "json_object"}}
    logged = json.dumps(loggable(request))
    assert "base64" not in logged and logged.count('"type": "image"') == 2
    assert request_fingerprint(request) != request_fingerprint(build_request("What is shown?", [(4, blank_png(20, 10))]))


@pytest.mark.parametrize(("question", "pages", "message"), [
    ("  ", [(1, b"\x89PNG\r\n\x1a\n" + bytes(16))], "question is empty"),
    ("Q?", [], "at least one page"),
    ("Q?", [(1, b"%PDF-1.7 not an image")], "not a PNG"),
])
def test_invalid_requests_are_rejected(question, pages, message):
    with pytest.raises(ValueError, match=message):
        build_request(question, pages)


def test_duplicate_pages_are_rejected():
    png = blank_png(10, 10)
    with pytest.raises(ValueError, match="twice"):
        build_request("Q?", [(1, png), (1, png)])
    assert png_size(png) == (10, 10)


# --- Parsing and the model call -----------------------------------------------------------------

@pytest.mark.parametrize(("raw", "expected"), [
    ('{"answer": "not answerable", "cited_pages": []}', ("Not answerable", [], None)),
    ('{"answer": 12, "cited_pages": ["4"]}', (12, [4], None)),
    ('{"answer": ["Circle", "Rectangle"], "cited_pages": [3, 7]}', (["Circle", "Rectangle"], [3, 7], None)),
    ('{"answer": 2.5}', (2.5, [], None)),
])
def test_parser_accepts_the_json_contract(raw, expected):
    assert parse_reply(raw) == expected


@pytest.mark.parametrize("raw", [
    "The answer is 12 [Page 4]",  # prose instead of JSON
    '{"cited_pages": [4]}',  # no answer key
    '{"answer": "Europe IPO", "cited_pa',  # cut off
    '{"answer": 5, "cited_pages": ["page 4"]}',  # non-integer page
    '{"answer": 5, "cited_pages": 4}',  # not a list
])
def test_parser_rejects_malformed_replies(raw):
    answer, cited, error = parse_reply(raw)
    assert (answer, cited) == ("", []) and error.startswith("unparseable")


def test_ask_sends_the_request_unchanged_and_parses_the_reply():
    sent = []
    request = build_request("Q?", [(1, blank_png(10, 10))])
    reply = ask(lambda **kwargs: sent.append(kwargs) or completion('{"answer": 41, "cited_pages": [1]}'), request)
    assert sent == [request]
    assert (reply.answer, reply.cited_pages, reply.error, reply.served_model) == (41, [1], None, "gpt-4o-mini-2024-07-18")


def test_ask_flags_truncated_and_empty_replies():
    request = build_request("Q?", [(1, blank_png(10, 10))])
    truncated = ask(lambda **_: completion('{"answer": 41, "cited_pages": [1]}', finish_reason="length"), request)
    assert truncated.answer == 41 and "finish_reason='length'" in truncated.error
    empty = ask(lambda **_: completion(None), request)
    assert empty.error.startswith("unparseable") and empty.raw == ""


def test_api_errors_propagate():
    def failing(**_):
        raise TimeoutError("network down")

    with pytest.raises(TimeoutError):
        ask(failing, build_request("Q?", [(1, blank_png(10, 10))]))
