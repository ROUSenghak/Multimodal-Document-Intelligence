"""Answer a question from page images with a vision-language model, as structured JSON.

This is the configuration the frozen experiments retained: GPT-4o-mini
(``gpt-4o-mini-2024-07-18``) reading 768-px page images (E1 adopted 768 px;
E2 retained GPT-4o-mini over Qwen3-VL-8B; E3 retained images only over images
plus extracted text). The system prompt, the user-message layout
(``Question: ...``, then ``[Page N]`` before each image) and the parameters are
those of notebook 02's image conditions, byte for byte; the tests check them
against the frozen runs. The reply parser is stricter than notebook 02's about
cited pages (it rejects 2.7, true, 0 and negatives instead of coercing them)
and gives the same result on every frozen reply.

Every request passes ``check_request`` before it is sent: its prompt-token upper
bound plus the full output allowance must fit the context window, and its
maximum cost must stay under a per-request ceiling.

The model is called through ``create``, any callable with the signature of
``openai.OpenAI().chat.completions.create``. Nothing here imports a client or
reads a credential, so every function can be tested offline.
"""

import base64
import hashlib
import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from math import ceil
from typing import Any

MODEL = "gpt-4o-mini-2024-07-18"
IMAGE_PROMPT_VERSION = "mmlb-image-v1"
IMAGE_SYSTEM_PROMPT = """You answer questions about a single PDF document using only the page images provided.
Each page image is preceded by a tag [Page N], where N is the 1-based page number in the PDF.

Return a JSON object with exactly these keys:
  "answer": the shortest complete answer. Use a number (integer or decimal) when the answer is a number,
            and a JSON list when several items are asked for. If the page images do not contain the answer,
            use exactly the string "Not answerable".
  "cited_pages": a list of the page numbers N whose images support the answer ([] if "Not answerable").

Do not use knowledge outside the page images. Do not guess."""
IMAGE_DETAIL = "high"
TEMPERATURE = 0.0
MAX_OUTPUT_TOKENS = 400

# Prompt-size guard. GPT-4o-mini bills a high-detail image as 2,833 + 5,667 tokens per 512-px tile
# after fitting it in 2048 x 2048 and reducing (never enlarging) its short side to 768 px; this rule
# reproduced every billed count of the frozen runs. Five 768-px pages can exceed the 128k context.
CONTEXT_WINDOW_TOKENS = 128_000
IMAGE_BASE_TOKENS = 2_833
IMAGE_TILE_TOKENS = 5_667
# Text is bounded without a tokenizer: o200k_base is byte-level BPE, so a text never encodes to more
# tokens than its UTF-8 bytes (about 4x the real count for English). Message framing added 10-29
# tokens beyond the exact text tokens in all 151 billed image-only requests of E1 and E3.
FRAMING_TOKEN_ALLOWANCE = 100
USD_PER_1M_INPUT_TOKENS = 0.15  # list prices checked on 2026-11-22; verify before relying on costs
USD_PER_1M_OUTPUT_TOKENS = 0.60
# Per-request spending ceiling, checked before every call. A request that fills the context costs at
# most about $0.0194 at the prices above, so this default only stops price or configuration mistakes;
# pass a lower value (``--max-cost-usd``) to cap spending more tightly.
MAX_REQUEST_COST_USD = 0.02

NOT_ANSWERABLE = "Not answerable"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def prompt_hash() -> str:
    """sha256(version + prompt)[:12], the identifier the frozen runs record."""
    return hashlib.sha256((IMAGE_PROMPT_VERSION + IMAGE_SYSTEM_PROMPT).encode()).hexdigest()[:12]


def png_size(png: bytes) -> tuple[int, int]:
    """(width, height) read from the PNG header."""
    if not isinstance(png, bytes) or not png.startswith(PNG_SIGNATURE) or len(png) < 24:
        raise ValueError("page image is not a PNG")
    return int.from_bytes(png[16:20], "big"), int.from_bytes(png[20:24], "big")


def image_tokens(width: int, height: int) -> int:
    """Prompt tokens GPT-4o-mini bills for one high-detail image of this size."""
    scale = min(1.0, 2048 / max(width, height))
    width, height = width * scale, height * scale
    short_scale = 768 / min(width, height)
    if short_scale < 1:
        width, height = width * short_scale, height * short_scale
    tiles = ceil(round(width, 6) / 512) * ceil(round(height, 6) / 512)
    return IMAGE_BASE_TOKENS + IMAGE_TILE_TOKENS * tiles


def text_token_bound(text: str) -> int:
    """Upper bound on the tokens of a text: its UTF-8 bytes (byte-level BPE never needs more)."""
    return len(text.encode("utf-8"))


def _question_text(question: str) -> str:
    return f"Question: {question}\n\nPage images:"


def _page_tag(number: int) -> str:
    return f"[Page {number}]"


def _decoded_image(part: dict) -> bytes:
    return base64.b64decode(part["image_url"]["url"].split(",", 1)[1])


def estimate_prompt_tokens(request: dict) -> int:
    """Upper bound on a built request's prompt tokens: text bytes, billed image tokens and framing."""
    total = FRAMING_TOKEN_ALLOWANCE
    for message in request["messages"]:
        content = message["content"]
        for part in [{"type": "text", "text": content}] if isinstance(content, str) else content:
            if part["type"] == "text":
                total += text_token_bound(part["text"])
            elif part["type"] == "image_url":
                total += image_tokens(*png_size(_decoded_image(part)))
            else:
                raise ValueError(f"cannot estimate tokens for a {part['type']!r} part")
    return total


def select_pages_within_context(
    question: str,
    pages: Sequence[tuple[int, bytes]],
    max_prompt_tokens: int = CONTEXT_WINDOW_TOKENS - MAX_OUTPUT_TOKENS,
) -> tuple[list[tuple[int, bytes]], list[int]]:
    """Keep the longest prefix of the ranked pages whose prompt, with this question, fits.

    The running total equals ``estimate_prompt_tokens(build_request(question, kept))``.
    Returns (kept pages, dropped page numbers). Pages after the first one that
    does not fit are dropped too, so the kept pages are always the best-ranked.
    """
    kept = []
    total = FRAMING_TOKEN_ALLOWANCE + text_token_bound(IMAGE_SYSTEM_PROMPT) + text_token_bound(_question_text(question))
    for number, png in pages:
        cost = text_token_bound(_page_tag(number)) + image_tokens(*png_size(png))
        if total + cost > max_prompt_tokens:
            break
        kept.append((number, png))
        total += cost
    return kept, [number for number, _ in pages[len(kept):]]


def check_request(request: dict, max_cost_usd: float = MAX_REQUEST_COST_USD) -> tuple[int, float]:
    """(prompt-token bound, maximum cost in USD) of a request, checked before it is sent.

    Raises ValueError, so nothing is sent, when the model's price and context are
    unknown, the output is unbounded, the prompt plus the full output allowance
    could exceed the context window, or the maximum cost exceeds ``max_cost_usd``.
    """
    if isinstance(max_cost_usd, bool) or not isinstance(max_cost_usd, (int, float)) or not 0 < max_cost_usd < float("inf"):  # and NaN
        raise ValueError(f"the cost ceiling must be a positive number of USD, not {max_cost_usd!r}")
    if request.get("model") != MODEL:
        raise ValueError(f"no context size or price is known for model {request.get('model')!r}")
    output = request.get("max_completion_tokens")
    if not isinstance(output, int) or isinstance(output, bool) or output < 1:
        raise ValueError("the request must bound its output with a positive max_completion_tokens")
    prompt = estimate_prompt_tokens(request)
    if prompt + output > CONTEXT_WINDOW_TOKENS:
        raise ValueError(f"the request could need {prompt + output:,} tokens ({prompt:,} prompt + {output:,} output), "
                         f"more than the {CONTEXT_WINDOW_TOKENS:,}-token context")
    cost = (prompt * USD_PER_1M_INPUT_TOKENS + output * USD_PER_1M_OUTPUT_TOKENS) / 1e6
    if cost > max_cost_usd:
        raise ValueError(f"the request could cost ${cost:.4f}, above the ${max_cost_usd:.4f} per-request ceiling")
    return prompt, cost


def build_request(question: str, pages: Sequence[tuple[int, bytes]], model: str = MODEL) -> dict:
    """Chat Completions arguments: system prompt, then the question and each tagged page image."""
    if not str(question).strip():
        raise ValueError("the question is empty")
    if not pages:
        raise ValueError("at least one page image is needed")
    if len({number for number, _ in pages}) != len(pages):
        raise ValueError("a page is supplied twice")
    content = [{"type": "text", "text": _question_text(question)}]
    for number, png in pages:
        png_size(png)  # rejects anything that is not a PNG
        content += [
            {"type": "text", "text": _page_tag(number)},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(png).decode("ascii"), "detail": IMAGE_DETAIL}},
        ]
    return {
        "model": model,
        "messages": [{"role": "system", "content": IMAGE_SYSTEM_PROMPT}, {"role": "user", "content": content}],
        "response_format": {"type": "json_object"},
        "max_completion_tokens": MAX_OUTPUT_TOKENS,
        "temperature": TEMPERATURE,
    }


def loggable(request: dict) -> dict:
    """The request with every image replaced by its SHA-256 and size: safe to save, no Base64."""

    def strip(part):
        if part.get("type") == "image_url":
            raw = _decoded_image(part)
            return {"type": "image", "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw), "detail": part["image_url"].get("detail")}
        return part

    messages = [{"role": m["role"], "content": m["content"] if isinstance(m["content"], str) else [strip(p) for p in m["content"]]}
                for m in request["messages"]]
    return {**{key: value for key, value in request.items() if key != "messages"}, "messages": messages}


def request_fingerprint(request: dict) -> str:
    """SHA-256 of the loggable request: equal fingerprints mean byte-identical requests."""
    return hashlib.sha256(json.dumps(loggable(request), sort_keys=True).encode()).hexdigest()


def _page_number(value: Any) -> int:
    """A cited page >= 1: a JSON integer, a whole float such as 2.0, or ASCII digits such as "4". Never rounded."""
    if isinstance(value, int) and not isinstance(value, bool):
        number = value
    elif isinstance(value, float) and value.is_integer():  # 2.0 loses nothing; 2.7, inf and NaN are refused
        number = int(value)
    elif isinstance(value, str) and value.isascii() and value.isdigit():
        number = int(value)
    else:
        raise ValueError(f"cited page {value!r} is not a page number")
    if number < 1:
        raise ValueError(f"cited page {value!r} is not a page number (pages start at 1)")
    return number


def parse_reply(raw_text: str) -> tuple[Any, list[int], str | None]:
    """(answer, cited pages, error or None) from the model's JSON reply.

    A citation that is not a whole page number (2.7, true, -1, 0, "page 4") makes
    the reply unparseable, as any other breach of the JSON contract does.
    """
    try:
        payload = json.loads(raw_text)
        answer = payload["answer"]
        cited_pages = payload.get("cited_pages", [])
        if not isinstance(cited_pages, list):
            raise TypeError(f"cited_pages is a {type(cited_pages).__name__}, not a list")
        cited = [_page_number(page) for page in cited_pages]
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        return "", [], f"unparseable model output: {error}"
    if isinstance(answer, str) and answer.strip().lower() == "not answerable":
        answer = NOT_ANSWERABLE
    return answer, cited, None


@dataclass(frozen=True)
class ModelReply:
    answer: Any
    cited_pages: list[int]
    error: str | None
    finish_reason: str | None
    served_model: str | None
    raw: str


def ask(create: Callable[..., Any], request: dict, max_cost_usd: float = MAX_REQUEST_COST_USD) -> ModelReply:
    """Check the request's context and cost limits, send it, and parse the reply.

    A request over a limit raises ValueError before ``create`` is called. API
    errors propagate to the caller (no retry here).
    """
    check_request(request, max_cost_usd)
    response = create(**request)
    choice = response.choices[0]
    raw = choice.message.content or ""
    answer, cited, error = parse_reply(raw)
    if choice.finish_reason != "stop" and error is None:
        error = f"reply did not finish normally (finish_reason={choice.finish_reason!r})"
    return ModelReply(answer, cited, error, choice.finish_reason, getattr(response, "model", None), raw)
