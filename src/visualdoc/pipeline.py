"""End-to-end question answering over one PDF, and a command-line demonstration.

    PDF -> page text (native, OCR fallback) -> BM25 top-k pages -> 768-px page images
        -> context guard -> VLM JSON answer -> citation check

Offline by default: the demonstration uses ``OfflineReader``, a stand-in that
calls no model and always cites the first page it was given. Its answer is a
placeholder, never a result. ``--live`` sends the page images to OpenAI (paid;
needs ``OPENAI_API_KEY`` and the ``openai`` package).

    python -m visualdoc.pipeline data/documents/ch2.pdf "Who led the Parliamentarian army?"

Untested combination: the frozen experiments measured BM25 top-5 at 512 px
(E0 condition B) and 768-px images on annotated evidence pages (E1-E3), not
BM25-retrieved pages at 768 px. This default follows those decisions, but its
accuracy has not been measured.
"""

import argparse
import json
import os
import re
import sys
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from .answering import (
    MAX_OUTPUT_TOKENS,
    USD_PER_1M_INPUT_TOKENS,
    USD_PER_1M_OUTPUT_TOKENS,
    ModelReply,
    ask,
    build_request,
    estimate_prompt_tokens,
    request_fingerprint,
    select_pages_within_context,
)
from .citations import CitationCheck, check_citations
from .documents import extract_pages, render_pages
from .retrieval import TOP_K, BM25Index


@dataclass(frozen=True)
class QAResult:
    question: str
    pdf: str
    page_count: int
    ocr_pages: int
    retrieved_pages: list[int]  # BM25 top-k, best first
    supplied_pages: list[int]  # the retrieved pages that fit the model's context
    dropped_pages: list[int]
    estimated_prompt_tokens: int
    cost_upper_usd: float  # list price, full output allowance
    request_fingerprint: str
    reply: ModelReply
    citations: CitationCheck

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["citations"].update(all_supplied=self.citations.all_supplied, ok=self.citations.ok)
        return result


def answer_question(pdf_path: str | Path, question: str, create: Callable[..., Any], *, top_k: int = TOP_K, tessdata: str | Path | None = None) -> QAResult:
    """Answer one question about one PDF with the model behind ``create``."""
    if not str(question).strip():
        raise ValueError("the question is empty")
    pages = extract_pages(pdf_path, tessdata=tessdata)
    if not pages:
        raise ValueError(f"{Path(pdf_path).name} has no pages")
    retrieved = BM25Index({p.page: p.text for p in pages}).top_pages(question, k=top_k)
    images = render_pages(pdf_path, retrieved)
    kept, dropped = select_pages_within_context([(number, images[number]) for number in retrieved])
    if not kept:
        raise ValueError("even the best-ranked page image does not fit the model's context")
    request = build_request(question, kept)
    estimate = estimate_prompt_tokens(kept)
    reply = ask(create, request)
    supplied = [number for number, _ in kept]
    return QAResult(
        question=question,
        pdf=str(pdf_path),
        page_count=len(pages),
        ocr_pages=sum(p.ocr_used for p in pages),
        retrieved_pages=retrieved,
        supplied_pages=supplied,
        dropped_pages=dropped,
        estimated_prompt_tokens=estimate,
        cost_upper_usd=round((estimate * USD_PER_1M_INPUT_TOKENS + MAX_OUTPUT_TOKENS * USD_PER_1M_OUTPUT_TOKENS) / 1e6, 6),
        request_fingerprint=request_fingerprint(request),
        reply=reply,
        citations=check_citations(reply.answer, reply.cited_pages, supplied),
    )


class OfflineReader:
    """Stand-in for the VLM: no network, no model. Cites the first supplied page; the answer is a placeholder."""

    ANSWER = "(offline demonstration: no model was called)"

    def __init__(self):
        self.requests: list[dict] = []

    def __call__(self, **request):
        self.requests.append(request)
        tags = [int(m) for part in request["messages"][1]["content"] if part["type"] == "text" for m in re.findall(r"^\[Page (\d+)\]$", part["text"])]
        reply = json.dumps({"answer": self.ANSWER, "cited_pages": tags[:1]})
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=reply), finish_reason="stop")], model="offline-reader")


def openai_create() -> Callable[..., Any]:
    """The paid OpenAI client's ``create``, after checking that a key is configured."""
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("--live needs OPENAI_API_KEY in the environment (it sends page images to OpenAI and is billed).")
    from openai import OpenAI  # imported only for live runs

    return OpenAI().chat.completions.create


def main(argv: list[str] | None = None) -> QAResult:
    parser = argparse.ArgumentParser(description="Answer a question about a PDF from its pages, with cited pages.")
    parser.add_argument("pdf", type=Path)
    parser.add_argument("question")
    parser.add_argument("--top-k", type=int, default=TOP_K, help="pages retrieved by BM25 (default %(default)s)")
    parser.add_argument("--live", action="store_true", help="call OpenAI (paid) instead of the offline stand-in")
    args = parser.parse_args(argv)

    create = openai_create() if args.live else OfflineReader()
    result = answer_question(args.pdf, args.question, create, top_k=args.top_k)
    print(json.dumps(result.to_dict(), indent=2, default=str))
    if not args.live:
        print("Offline mode: the answer above is a placeholder from OfflineReader, not a model result.", file=sys.stderr)
    return result


if __name__ == "__main__":
    main()
