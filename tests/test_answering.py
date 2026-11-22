"""VLM answering: prompt and parameters pinned to the frozen runs, request building, context and cost guards, parser, model call."""

import json
from types import SimpleNamespace

import pymupdf
import pytest

from conftest import E1_SPEC, FROZEN_E0_IMAGE_SETTINGS, FROZEN_E1_LOG, MMLB_QUESTIONS, REPO_ROOT, read_json, read_jsonl
from visualdoc import answering
from visualdoc.answering import (
    ask,
    build_request,
    check_request,
    estimate_prompt_tokens,
    image_tokens,
    loggable,
    parse_reply,
    png_size,
    request_fingerprint,
    select_pages_within_context,
    text_token_bound,
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


def test_prompt_bound_covers_every_billed_frozen_request():
    # Rebuild each billed image-only request of E1 and E3 (blank PNGs of the frozen sizes, the real
    # question) and check the bound against the prompt tokens OpenAI actually billed.
    pd = pytest.importorskip("pandas")
    if not MMLB_QUESTIONS.is_file():
        pytest.skip("MMLongBench-Doc questions not downloaded (git-ignored; notebook 00 downloads them)")
    questions = pd.read_parquet(MMLB_QUESTIONS)["question"]
    records = read_jsonl(FROZEN_E1_LOG) + [r for r in read_jsonl(FROZEN_E3_LOG) if r["condition"] == "E3_I"]
    billed = [r for r in records if r.get("prompt_tokens") is not None]
    assert len(billed) == 151
    for record in billed:
        question = questions.iloc[int(record["qid"].removeprefix("mmlb-"))]
        pages = [(n, blank_png(w, h)) for n, (w, h) in zip(record["supplied_pages"], record["image_dimensions"], strict=True)]
        bound = estimate_prompt_tokens(build_request(question, pages))
        assert record["prompt_tokens"] < bound <= record["prompt_tokens"] + 1_200, record["qid"]  # safe, not wildly loose


@pytest.mark.parametrize("text", [
    answering.IMAGE_SYSTEM_PROMPT,
    "Question: What is the CAGR of revenue between 2019 and 2021, in %?\n\nPage images:",
    "Quelle est la part (en %) des ménages équipés ? 東京の人口は？ 🚀🚀🚀",
    "\x00\x7f" * 50 + " " * 200 + "a" * 300,
])
def test_utf8_bytes_bound_the_real_token_count(text):
    tiktoken = pytest.importorskip("tiktoken")
    assert len(tiktoken.get_encoding("o200k_base").encode(text)) <= text_token_bound(text)


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
    with pytest.raises(ValueError, match="more than the 128,000-token context"):
        check_request(build_request("Q?", pages))
    kept, dropped = select_pages_within_context("Q?", pages)
    assert [n for n, _ in kept] == [7, 3, 9, 1] and dropped == [4]
    prompt, _ = check_request(build_request("Q?", kept))
    assert prompt + answering.MAX_OUTPUT_TOKENS <= answering.CONTEXT_WINDOW_TOKENS


def test_selection_total_equals_the_bound_of_the_built_request():
    pages = [(12, blank_png(768, 994)), (3, blank_png(1366, 768)), (140, blank_png(10, 10))]
    for question in ("Q?", "Wie hoch ist der Umsatz 2021 (in €)?", "x" * 5_000):
        kept, _ = select_pages_within_context(question, pages, max_prompt_tokens=10**9)
        total = (answering.FRAMING_TOKEN_ALLOWANCE + text_token_bound(answering.IMAGE_SYSTEM_PROMPT)
                 + text_token_bound(f"Question: {question}\n\nPage images:")
                 + sum(text_token_bound(f"[Page {n}]") + image_tokens(*png_size(png)) for n, png in pages))
        assert estimate_prompt_tokens(build_request(question, kept)) == total


def test_context_guard_keeps_a_ranked_prefix_only():
    pages = [(1, blank_png(768, 994)), (2, blank_png(768, 994)), (3, blank_png(100, 100))]
    one_page = estimate_prompt_tokens(build_request("Q?", pages[:1]))
    kept, dropped = select_pages_within_context("Q?", pages, max_prompt_tokens=one_page + 20_000)
    assert [n for n, _ in kept] == [1] and dropped == [2, 3]  # page 3 would fit but is ranked below a page that does not
    assert select_pages_within_context("Q?", pages, max_prompt_tokens=one_page) == (pages[:1], [2, 3])  # exactly at the limit
    assert select_pages_within_context("Q?", pages, max_prompt_tokens=one_page - 1) == ([], [1, 2, 3])


def test_a_long_question_leaves_room_for_fewer_pages():
    pages = [(n, blank_png(768, 994)) for n in (1, 2, 3, 4)]
    assert len(select_pages_within_context("Q?", pages)[0]) == 4
    long_question = "Compare the revenue figures. " * 1_000  # 29,000 bytes: the old fixed 1,000-token allowance overflowed
    kept, dropped = select_pages_within_context(long_question, pages)
    assert [n for n, _ in kept] == [1, 2, 3] and dropped == [4]
    check_request(build_request(long_question, kept))
    with pytest.raises(ValueError, match="context"):
        check_request(build_request(long_question, pages))
    assert select_pages_within_context("x" * 130_000, pages) == ([], [1, 2, 3, 4])


# --- Cost ceiling: checked before the call --------------------------------------------------------

def test_cost_is_the_list_price_of_the_bound_and_full_output():
    request = build_request("Q?", [(1, blank_png(768, 994))])
    prompt, cost = check_request(request)
    assert prompt == estimate_prompt_tokens(request)
    assert cost == pytest.approx((prompt * 0.15 + 400 * 0.60) / 1e6)
    assert check_request(request, max_cost_usd=cost) == (prompt, cost)  # a ceiling equal to the cost passes
    with pytest.raises(ValueError, match="per-request ceiling"):
        check_request(request, max_cost_usd=cost * (1 - 1e-9))


def test_a_full_context_request_stays_under_the_default_ceiling():
    full = answering.CONTEXT_WINDOW_TOKENS - answering.MAX_OUTPUT_TOKENS
    assert (full * answering.USD_PER_1M_INPUT_TOKENS + answering.MAX_OUTPUT_TOKENS * answering.USD_PER_1M_OUTPUT_TOKENS) / 1e6 \
        < answering.MAX_REQUEST_COST_USD


@pytest.mark.parametrize("ceiling", [0, -0.01, float("nan"), float("inf"), "0.05", None, True])
def test_an_invalid_ceiling_is_refused(ceiling):
    with pytest.raises(ValueError, match="cost ceiling"):
        check_request(build_request("Q?", [(1, blank_png(10, 10))]), max_cost_usd=ceiling)


@pytest.mark.parametrize(("change", "message"), [
    ({"model": "gpt-4o"}, "no context size or price"),
    ({"max_completion_tokens": None}, "max_completion_tokens"),
    ({"max_completion_tokens": 0}, "max_completion_tokens"),
    ({"max_completion_tokens": True}, "max_completion_tokens"),
])
def test_requests_of_unknown_price_or_unbounded_output_are_refused(change, message):
    with pytest.raises(ValueError, match=message):
        check_request({**build_request("Q?", [(1, blank_png(10, 10))]), **change})


def test_context_limit_counts_the_full_output_allowance(monkeypatch):
    request = build_request("Q?", [(1, blank_png(768, 994))])
    prompt, _ = check_request(request)
    monkeypatch.setattr(answering, "CONTEXT_WINDOW_TOKENS", prompt + answering.MAX_OUTPUT_TOKENS)
    check_request(request)  # exactly full
    monkeypatch.setattr(answering, "CONTEXT_WINDOW_TOKENS", prompt + answering.MAX_OUTPUT_TOKENS - 1)
    with pytest.raises(ValueError, match="context"):
        check_request(request)


def test_ask_never_calls_the_model_for_a_request_over_a_limit():
    sent = []
    create = lambda **kwargs: sent.append(kwargs) or completion('{"answer": 1, "cited_pages": [1]}')
    too_long = build_request("Q?", [(n, blank_png(768, 994)) for n in range(1, 6)])
    with pytest.raises(ValueError, match="context"):
        ask(create, too_long)
    with pytest.raises(ValueError, match="ceiling"):
        ask(create, build_request("Q?", [(1, blank_png(768, 994))]), max_cost_usd=0.001)
    assert sent == []


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
    ('{"answer": 2.7, "cited_pages": [1, 100000]}', (2.7, [1, 100000], None)),  # only the pages must be whole
    ('{"answer": 5, "cited_pages": [2.0, "07"]}', (5, [2, 7], None)),  # whole values lose nothing
])
def test_parser_accepts_the_json_contract(raw, expected):
    assert parse_reply(raw) == expected


@pytest.mark.parametrize("raw", [
    "The answer is 12 [Page 4]",  # prose instead of JSON
    '{"cited_pages": [4]}',  # no answer key
    '{"answer": "Europe IPO", "cited_pa',  # cut off
    '{"answer": 5, "cited_pages": ["page 4"]}',  # non-integer page
    '{"answer": 5, "cited_pages": 4}',  # not a list
    '{"answer": 5, "cited_pages": "45"}',  # a string is not a list of pages (it was read as [4, 5])
    '{"answer": 5, "cited_pages": null}',
    '{"answer": 5, "cited_pages": [2.7]}',  # was truncated to 2
    '{"answer": 5, "cited_pages": [-2.0]}',
    '{"answer": 5, "cited_pages": [1e400]}',  # infinity
    '{"answer": 5, "cited_pages": [true]}',  # was read as page 1
    '{"answer": 5, "cited_pages": [false]}',
    '{"answer": 5, "cited_pages": [-3]}',
    '{"answer": 5, "cited_pages": [0]}',  # pages start at 1
    '{"answer": 5, "cited_pages": ["2.7"]}',
    '{"answer": 5, "cited_pages": ["-1"]}',
    '{"answer": 5, "cited_pages": [" 4"]}',
    '{"answer": 5, "cited_pages": ["\\u0664"]}',  # an Arabic-Indic digit 4: int() would accept it
    '{"answer": 5, "cited_pages": [""]}',
    '{"answer": 5, "cited_pages": [NaN]}',
    '{"answer": 5, "cited_pages": [[4]]}',
    '["answer", 5]',  # not an object
])
def test_parser_rejects_malformed_replies(raw):
    answer, cited, error = parse_reply(raw)
    assert (answer, cited) == ("", []) and error.startswith("unparseable")


def test_a_bad_page_is_named_in_the_error():
    assert "2.7" in parse_reply('{"answer": 5, "cited_pages": [3, 2.7]}')[2]


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
