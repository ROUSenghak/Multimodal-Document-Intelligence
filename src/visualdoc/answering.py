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
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from math import ceil, floor
from typing import Any, Literal

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

# B1 is deliberately additive.  The constants and functions above/below this
# block still define the byte-identical GPT-4o-mini contract used by E1--E6.
B1_PROMPT_VERSION = "b1-image-v2"
B1_SYSTEM_PROMPT = """You answer questions about a single PDF document using only the page images provided.
Each page image is preceded by a tag [Page N], where N is the 1-based page number in the PDF.

Return a JSON object with exactly these keys:
  "answer": the shortest complete answer. Use a number (integer or decimal) when the answer is a number,
            and a JSON list when several items are asked for. If the page images do not contain the answer,
            use exactly the string "Not answerable".
  "cited_pages": a list of the page numbers N whose images support the answer ([] if "Not answerable").
  "evidence": for each cited page, one short passage copied verbatim from that page (at most 30 words)
              that supports the answer ([] if "Not answerable").

Do not use knowledge outside the page images. Do not guess."""
B1_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["answer", "cited_pages", "evidence"],
    "properties": {
        "answer": {
            "anyOf": [
                {"type": "string"},
                {"type": "number"},
                {"type": "array", "items": {"anyOf": [{"type": "string"}, {"type": "number"}]}},
            ]
        },
        "cited_pages": {"type": "array", "items": {"type": "integer"}},
        "evidence": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["page", "quote"],
                "properties": {"page": {"type": "integer"}, "quote": {"type": "string"}},
            },
        },
    },
}
JSON_OBJECT_FORMAT = {"type": "json_object"}
STRICT_B1_FORMAT = {
    "type": "json_schema",
    "json_schema": {"name": "b1_answer", "strict": True, "schema": B1_SCHEMA},
}
Contract = Literal["v1", "b1"]


def luna_image_tokens(width: int, height: int) -> int:
    """Image tokens measured by the frozen E8 smoke, not inferred from another model."""
    if width < 1 or height < 1:
        raise ValueError("image dimensions must be positive")
    return floor(1.2 * ceil(width / 32) * ceil(height / 32))


@dataclass(frozen=True)
class ReaderProfile:
    """All model-specific limits and prices needed by the model-neutral pipeline."""

    model: str
    context_tokens: int
    image_tokens: Callable[[int, int], int]
    usd_per_1m_input: float
    usd_per_1m_output: float
    request_params: Mapping[str, Any]
    max_output_tokens: int
    text_encoding: str | None = None
    text_only_framing_tokens: int = 0
    multimodal_framing_tokens: int = 0
    strict_schema_tokens: int = 0


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


GPT4O_MINI_PROFILE = ReaderProfile(
    model=MODEL,
    context_tokens=CONTEXT_WINDOW_TOKENS,
    image_tokens=image_tokens,
    usd_per_1m_input=USD_PER_1M_INPUT_TOKENS,
    usd_per_1m_output=USD_PER_1M_OUTPUT_TOKENS,
    request_params={"temperature": TEMPERATURE},
    max_output_tokens=MAX_OUTPUT_TOKENS,
)

# The alias has no dated snapshot.  A live run must therefore record the served
# model and system fingerprint; frozen replies, not this name, define a result.
LUNA_PROFILE = ReaderProfile(
    model="gpt-6-luna",
    context_tokens=128_000,
    image_tokens=luna_image_tokens,
    usd_per_1m_input=0.10,
    usd_per_1m_output=0.50,
    # Keep integer 0: JSON fingerprints distinguish ``0`` from ``0.0`` even
    # though Python and the API treat the values as numerically equal.
    request_params={"reasoning_effort": "none", "temperature": 0},
    max_output_tokens=800,
    text_encoding="o200k_base",
    text_only_framing_tokens=10,
    multimodal_framing_tokens=9,
    strict_schema_tokens=100,
)


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


def build_profiled_request(
    question: str,
    pages: Sequence[tuple[int, bytes]],
    *,
    profile: ReaderProfile = LUNA_PROFILE,
    contract: Contract = "b1",
    allow_empty_pages: bool = False,
) -> dict:
    """Build the E8/B1 request while keeping model policy in ``profile``.

    ``contract='v1'`` isolates the reader change: it uses the frozen prompt,
    JSON-object mode and 400 output tokens. ``contract='b1'`` uses the strict
    answer/citations/evidence schema and 800 output tokens.
    """
    if not str(question).strip():
        raise ValueError("the question is empty")
    if not pages and not allow_empty_pages:
        raise ValueError("at least one page image is needed")
    if len({number for number, _ in pages}) != len(pages):
        raise ValueError("a page is supplied twice")
    if contract not in ("v1", "b1"):
        raise ValueError(f"unknown answer contract {contract!r}")

    content = [{"type": "text", "text": _question_text(question)}]
    for number, png in pages:
        png_size(png)
        content.extend([
            {"type": "text", "text": _page_tag(number)},
            {"type": "image_url", "image_url": {
                "url": "data:image/png;base64," + base64.b64encode(png).decode("ascii"),
                "detail": IMAGE_DETAIL,
            }},
        ])

    request = {
        "model": profile.model,
        "messages": [
            {"role": "system", "content": IMAGE_SYSTEM_PROMPT if contract == "v1" else B1_SYSTEM_PROMPT},
            {"role": "user", "content": content},
        ],
        "response_format": JSON_OBJECT_FORMAT if contract == "v1" else STRICT_B1_FORMAT,
        "max_completion_tokens": MAX_OUTPUT_TOKENS if contract == "v1" else profile.max_output_tokens,
        **dict(profile.request_params),
    }
    return request


def _request_texts_and_dimensions(request: Mapping[str, Any]) -> tuple[list[str], list[tuple[int, int]]]:
    texts, dimensions = [], []
    for message in request["messages"]:
        content = message["content"]
        parts = [{"type": "text", "text": content}] if isinstance(content, str) else content
        for part in parts:
            if part["type"] == "text":
                texts.append(part["text"])
            elif part["type"] == "image_url":
                dimensions.append(png_size(_decoded_image(part)))
            else:
                raise ValueError(f"cannot estimate tokens for a {part['type']!r} part")
    return texts, dimensions


def estimate_profiled_prompt_tokens(request: Mapping[str, Any], profile: ReaderProfile = LUNA_PROFILE) -> int:
    """Exact E8-smoke profile estimate; fails clearly when its tokenizer is absent."""
    if request.get("model") != profile.model:
        raise ValueError(f"request model {request.get('model')!r} does not match profile {profile.model!r}")
    if profile.text_encoding is None:
        raise ValueError(f"profile {profile.model!r} has no exact text-token encoding")
    try:
        import tiktoken
    except ImportError as error:  # the request can still be built without the live/experiment extra
        raise RuntimeError("exact token checks need tiktoken; install visualdoc-ai[llm]") from error

    texts, dimensions = _request_texts_and_dimensions(request)
    encoding = tiktoken.get_encoding(profile.text_encoding)
    framing = profile.multimodal_framing_tokens if dimensions else profile.text_only_framing_tokens
    schema = profile.strict_schema_tokens if request["response_format"]["type"] == "json_schema" else 0
    return (
        sum(len(encoding.encode(text)) for text in texts)
        + framing
        + schema
        + sum(profile.image_tokens(width, height) for width, height in dimensions)
    )


def check_profiled_request(
    request: Mapping[str, Any],
    *,
    profile: ReaderProfile = LUNA_PROFILE,
    max_cost_usd: float,
) -> tuple[int, float]:
    """Check exact prompt size, context and worst-case list-price cost before a call."""
    if isinstance(max_cost_usd, bool) or not isinstance(max_cost_usd, (int, float)) or not 0 < max_cost_usd < float("inf"):
        raise ValueError(f"the cost ceiling must be a positive number of USD, not {max_cost_usd!r}")
    output = request.get("max_completion_tokens")
    if not isinstance(output, int) or isinstance(output, bool) or output < 1:
        raise ValueError("the request must bound its output with a positive max_completion_tokens")
    prompt = estimate_profiled_prompt_tokens(request, profile)
    if prompt + output > profile.context_tokens:
        raise ValueError(
            f"the request could need {prompt + output:,} tokens ({prompt:,} prompt + {output:,} output), "
            f"more than the {profile.context_tokens:,}-token context"
        )
    cost = (prompt * profile.usd_per_1m_input + output * profile.usd_per_1m_output) / 1e6
    if cost > max_cost_usd:
        raise ValueError(f"the request could cost ${cost:.6f}, above the ${max_cost_usd:.6f} per-request ceiling")
    return prompt, cost


def select_profiled_pages_within_context(
    question: str,
    pages: Sequence[tuple[int, bytes]],
    *,
    profile: ReaderProfile = LUNA_PROFILE,
    contract: Contract = "b1",
) -> tuple[list[tuple[int, bytes]], list[int]]:
    """Keep the longest ranked prefix that fits the profiled reader context."""
    kept: list[tuple[int, bytes]] = []
    for page in pages:
        candidate = [*kept, page]
        request = build_profiled_request(question, candidate, profile=profile, contract=contract)
        output = request["max_completion_tokens"]
        if estimate_profiled_prompt_tokens(request, profile) + output > profile.context_tokens:
            break
        kept = candidate
    return kept, [number for number, _ in pages[len(kept):]]


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


def profiled_loggable(request: Mapping[str, Any]) -> dict:
    """E8 log form: no Base64, but content hash, byte count and dimensions remain auditable."""

    def strip(part):
        if part.get("type") != "image_url":
            return part
        raw = _decoded_image(part)
        return {
            "type": "image",
            "sha256": hashlib.sha256(raw).hexdigest(),
            "bytes": len(raw),
            "dimensions": list(png_size(raw)),
            "detail": part["image_url"].get("detail"),
        }

    messages = [
        {
            "role": message["role"],
            "content": message["content"] if isinstance(message["content"], str) else [strip(part) for part in message["content"]],
        }
        for message in request["messages"]
    ]
    return {**{key: value for key, value in request.items() if key != "messages"}, "messages": messages}


def profiled_request_fingerprint(request: Mapping[str, Any]) -> str:
    """SHA-256 used by E8; dimensions make the reader-profile audit explicit."""
    return hashlib.sha256(json.dumps(profiled_loggable(request), sort_keys=True).encode()).hexdigest()


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


@dataclass(frozen=True)
class EvidenceQuote:
    page: int
    quote: str


@dataclass(frozen=True)
class ProfiledModelReply:
    answer: Any
    cited_pages: list[int]
    evidence: list[EvidenceQuote]
    error: str | None
    finish_reason: str | None
    served_model: str | None
    system_fingerprint: str | None
    prompt_tokens: int | None
    completion_tokens: int | None
    raw: str


def _valid_answer(answer: Any) -> bool:
    scalar = lambda value: isinstance(value, (str, int, float)) and not isinstance(value, bool)
    return scalar(answer) or (isinstance(answer, list) and all(scalar(item) for item in answer))


def parse_profiled_reply(raw_text: str, contract: Contract) -> tuple[Any, list[int], list[EvidenceQuote], str | None]:
    """Parse v1 or B1 output, enforcing the semantic part of the selected contract."""
    if contract == "v1":
        answer, cited, error = parse_reply(raw_text)
        return answer, cited, [], error
    if contract != "b1":
        raise ValueError(f"unknown answer contract {contract!r}")
    try:
        payload = json.loads(raw_text)
        if not isinstance(payload, dict) or set(payload) != {"answer", "cited_pages", "evidence"}:
            raise TypeError("B1 output must contain exactly answer, cited_pages and evidence")
        answer = payload["answer"]
        if not _valid_answer(answer):
            raise TypeError("answer is not a string, number, or list of strings/numbers")
        cited_payload = payload["cited_pages"]
        evidence_payload = payload["evidence"]
        if not isinstance(cited_payload, list) or not isinstance(evidence_payload, list):
            raise TypeError("cited_pages and evidence must be lists")
        cited = [_page_number(page) for page in cited_payload]
        evidence = []
        for item in evidence_payload:
            if not isinstance(item, dict) or set(item) != {"page", "quote"}:
                raise TypeError("each evidence item must contain exactly page and quote")
            if not isinstance(item["quote"], str):
                raise TypeError("an evidence quote is not a string")
            evidence.append(EvidenceQuote(_page_number(item["page"]), item["quote"]))
        if isinstance(answer, str) and answer.strip().lower() == "not answerable":
            answer = NOT_ANSWERABLE
        if answer == NOT_ANSWERABLE and (cited or evidence):
            raise ValueError("Not answerable must have empty cited_pages and evidence")
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        return "", [], [], f"unparseable model output: {error}"
    return answer, cited, evidence, None


def ask_profiled(
    create: Callable[..., Any],
    request: dict,
    *,
    profile: ReaderProfile = LUNA_PROFILE,
    contract: Contract = "b1",
    max_cost_usd: float,
) -> ProfiledModelReply:
    """Guard, call and parse one profiled request; API failures still propagate."""
    check_profiled_request(request, profile=profile, max_cost_usd=max_cost_usd)
    response = create(**request)
    choice = response.choices[0]
    raw = choice.message.content or ""
    answer, cited, evidence, error = parse_profiled_reply(raw, contract)
    if choice.finish_reason != "stop" and error is None:
        error = f"reply did not finish normally (finish_reason={choice.finish_reason!r})"
    usage = getattr(response, "usage", None)
    return ProfiledModelReply(
        answer=answer,
        cited_pages=cited,
        evidence=evidence,
        error=error,
        finish_reason=choice.finish_reason,
        served_model=getattr(response, "model", None),
        system_fingerprint=getattr(response, "system_fingerprint", None),
        prompt_tokens=getattr(usage, "prompt_tokens", None),
        completion_tokens=getattr(usage, "completion_tokens", None),
        raw=raw,
    )
