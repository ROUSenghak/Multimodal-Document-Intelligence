"""End-to-end question answering over one PDF, and a command-line demonstration.

    PDF -> page text (native, OCR fallback) -> BM25 top-k pages -> 768-px page images
        -> context guard -> context and cost check -> VLM JSON answer -> citation check

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
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from .answering import (
    Contract,
    EvidenceQuote,
    LUNA_PROFILE,
    MAX_REQUEST_COST_USD,
    ModelReply,
    ProfiledModelReply,
    ReaderProfile,
    ask,
    ask_profiled,
    build_request,
    build_profiled_request,
    check_request,
    check_profiled_request,
    parse_profiled_reply,
    profiled_request_fingerprint,
    request_fingerprint,
    select_pages_within_context,
    select_profiled_pages_within_context,
)
from .citations import CitationCheck, GroundingCheck, check_citations, check_grounding
from .documents import extract_pages, render_pages
from .retrieval import TOP_K, BM25Index, Retriever


@dataclass(frozen=True)
class QAResult:
    question: str
    pdf: str
    page_count: int
    ocr_pages: int
    retrieved_pages: list[int]  # BM25 top-k, best first
    supplied_pages: list[int]  # the retrieved pages that fit the model's context
    dropped_pages: list[int]
    estimated_prompt_tokens: int  # upper bound
    cost_upper_usd: float  # list price, full output allowance; checked against the ceiling before the call
    request_fingerprint: str
    reply: ModelReply
    citations: CitationCheck

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["citations"].update(all_supplied=self.citations.all_supplied, ok=self.citations.ok)
        return result


@dataclass(frozen=True)
class Budget:
    """Hard bounds shared by baseline and future adaptive policies."""

    max_calls: int = 1
    max_pages: int = 4
    max_usd: float = 0.01

    def __post_init__(self):
        if isinstance(self.max_calls, bool) or not isinstance(self.max_calls, int) or self.max_calls < 1:
            raise ValueError("max_calls must be a positive integer")
        if isinstance(self.max_pages, bool) or not isinstance(self.max_pages, int) or self.max_pages < 1:
            raise ValueError("max_pages must be a positive integer")
        if isinstance(self.max_usd, bool) or not isinstance(self.max_usd, (int, float)) or not 0 < self.max_usd < float("inf"):
            raise ValueError("max_usd must be a positive finite number")


@dataclass(frozen=True)
class Step:
    action: str
    inputs: dict[str, Any]
    output: dict[str, Any]
    usd: float
    latency_s: float


class ReplyCache:
    """Minimal content-addressed cache interface; implementations may persist it."""

    def get(self, fingerprint: str) -> ProfiledModelReply | None:
        raise NotImplementedError

    def put(self, fingerprint: str, reply: ProfiledModelReply) -> None:
        raise NotImplementedError


class MemoryReplyCache(ReplyCache):
    """Offline/test cache. A run executor can implement the same interface with JSONL."""

    def __init__(self):
        self.replies: dict[str, ProfiledModelReply] = {}

    def get(self, fingerprint: str) -> ProfiledModelReply | None:
        return self.replies.get(fingerprint)

    def put(self, fingerprint: str, reply: ProfiledModelReply) -> None:
        self.replies[fingerprint] = reply


class JsonlReplyCache(MemoryReplyCache):
    """Append-only persistent replies keyed by request fingerprint."""

    def __init__(self, path: str | Path):
        super().__init__()
        self.path = Path(path)
        if self.path.is_file():
            for line_number, line in enumerate(self.path.read_text().splitlines(), start=1):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                    payload = record["reply"]
                    payload["evidence"] = [EvidenceQuote(**item) for item in payload["evidence"]]
                    reply = ProfiledModelReply(**payload)
                    fingerprint = record["fingerprint"]
                except (json.JSONDecodeError, KeyError, TypeError) as error:
                    raise ValueError(f"invalid reply cache record at {self.path}:{line_number}: {error}") from error
                previous = self.replies.get(fingerprint)
                if previous is not None and previous != reply:
                    raise ValueError(f"conflicting replies for fingerprint {fingerprint} in {self.path}")
                self.replies[fingerprint] = reply

    def put(self, fingerprint: str, reply: ProfiledModelReply) -> None:
        previous = self.replies.get(fingerprint)
        if previous is not None:
            if previous != reply:
                raise ValueError(f"refusing to overwrite a different reply for fingerprint {fingerprint}")
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        record = json.dumps({"fingerprint": fingerprint, "reply": asdict(reply)}, sort_keys=True)
        with self.path.open("a") as handle:
            handle.write(record + "\n")
        self.replies[fingerprint] = reply


@dataclass(frozen=True)
class B1Result:
    question: str
    pdf: str
    retriever: str
    fallback_reason: str | None
    retrieved_pages: list[int]
    supplied_pages: list[int]
    dropped_pages: list[int]
    estimated_prompt_tokens: int
    cost_upper_usd: float
    request_fingerprint: str
    cache_hit: bool
    reply: ProfiledModelReply
    citations: CitationCheck
    grounding: GroundingCheck
    trace: tuple[Step, ...]

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["citations"].update(all_supplied=self.citations.all_supplied, ok=self.citations.ok)
        result["grounding"].update(quotes_supported=self.grounding.quotes_supported, ok=self.grounding.ok)
        return result


def append_run_log(path: str | Path, result: B1Result) -> None:
    """Append one auditable trace; callers choose a git-ignored run path."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        handle.write(json.dumps(result.to_dict(), sort_keys=True, default=str) + "\n")


def answer_question(pdf_path: str | Path, question: str, create: Callable[..., Any], *, top_k: int = TOP_K,
                    tessdata: str | Path | None = None, max_cost_usd: float = MAX_REQUEST_COST_USD) -> QAResult:
    """Answer one question about one PDF with the model behind ``create``.

    Raises ValueError, before ``create`` is called, if the request could exceed
    the context window or cost more than ``max_cost_usd``.
    """
    if not str(question).strip():
        raise ValueError("the question is empty")
    pages = extract_pages(pdf_path, tessdata=tessdata)
    if not pages:
        raise ValueError(f"{Path(pdf_path).name} has no pages")
    retrieved = BM25Index({p.page: p.text for p in pages}).top_pages(question, k=top_k)
    images = render_pages(pdf_path, retrieved)
    kept, dropped = select_pages_within_context(question, [(number, images[number]) for number in retrieved])
    if not kept:
        raise ValueError("even the best-ranked page image does not fit the model's context with this question")
    request = build_request(question, kept)
    estimate, cost = check_request(request, max_cost_usd)
    reply = ask(create, request, max_cost_usd)
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
        cost_upper_usd=round(cost, 6),
        request_fingerprint=request_fingerprint(request),
        reply=reply,
        citations=check_citations(reply.answer, reply.cited_pages, supplied),
    )


def answer_question_b1(
    pdf_path: str | Path,
    question: str,
    create: Callable[..., Any],
    *,
    primary_retriever: Retriever | None = None,
    k: int = 4,
    profile: ReaderProfile = LUNA_PROFILE,
    contract: Contract = "b1",
    budget: Budget = Budget(),
    cache: ReplyCache | None = None,
    tessdata: str | Path | None = None,
) -> B1Result:
    """B1 policy: retrieve once, read once, verify once, all under ``budget``.

    A supplied visual retriever is primary. A runtime/unavailability failure is
    recorded and falls back to BM25 over the already extracted page text;
    malformed rankings still fail loudly instead of being hidden as fallback.
    """
    if not str(question).strip():
        raise ValueError("the question is empty")
    if isinstance(k, bool) or not isinstance(k, int) or not 1 <= k <= budget.max_pages:
        raise ValueError(f"k must be between 1 and the page budget ({budget.max_pages})")
    pages = extract_pages(pdf_path, tessdata=tessdata)
    if not pages:
        raise ValueError(f"{Path(pdf_path).name} has no pages")
    page_texts = {page.page: page.text for page in pages}
    bm25 = BM25Index(page_texts)

    retrieve_started = time.perf_counter()
    fallback_reason = None
    retriever = primary_retriever or bm25
    try:
        ranking = retriever.rank(question)
    except (OSError, RuntimeError) as error:
        if primary_retriever is None:
            raise
        fallback_reason = f"{type(error).__name__}: {error}"
        retriever, ranking = bm25, bm25.rank(question)
    if not ranking:
        raise ValueError(f"retriever {retriever.name!r} returned no pages")
    ranked_pages = [int(page) for page, _ in ranking]
    if len(set(ranked_pages)) != len(ranked_pages) or any(page not in page_texts for page in ranked_pages):
        raise ValueError(f"retriever {retriever.name!r} returned duplicate or unknown pages")
    selected = ranked_pages[:k]
    retrieve_step = Step(
        action="retrieve",
        inputs={"question": question, "requested_retriever": getattr(primary_retriever, "name", "bm25"), "k": k},
        output={"retriever": retriever.name, "pages": selected, "fallback_reason": fallback_reason},
        usd=0.0,
        latency_s=time.perf_counter() - retrieve_started,
    )

    images = render_pages(pdf_path, selected)
    kept, dropped = select_profiled_pages_within_context(
        question, [(page, images[page]) for page in selected], profile=profile, contract=contract
    )
    if not kept:
        raise ValueError("even the best-ranked page image does not fit the reader context")
    request = build_profiled_request(question, kept, profile=profile, contract=contract)
    prompt_tokens, cost_upper = check_profiled_request(request, profile=profile, max_cost_usd=budget.max_usd)
    fingerprint = profiled_request_fingerprint(request)

    read_started = time.perf_counter()
    reply = cache.get(fingerprint) if cache is not None else None
    cache_hit = reply is not None
    if reply is None:
        reply = ask_profiled(
            create, request, profile=profile, contract=contract, max_cost_usd=budget.max_usd
        )
        if cache is not None:
            cache.put(fingerprint, reply)
    read_step = Step(
        action="read",
        inputs={"pages": [page for page, _ in kept], "contract": contract, "request_fingerprint": fingerprint},
        output={
            "cache_hit": cache_hit,
            "served_model": reply.served_model,
            "system_fingerprint": reply.system_fingerprint,
            "parse_error": reply.error,
        },
        usd=0.0 if cache_hit else cost_upper,
        latency_s=time.perf_counter() - read_started,
    )

    verify_started = time.perf_counter()
    supplied = [page for page, _ in kept]
    citations = check_citations(reply.answer, reply.cited_pages, supplied)
    grounding = check_grounding(reply.answer, reply.cited_pages, reply.evidence, page_texts)
    verify_step = Step(
        action="verify",
        inputs={"cited_pages": reply.cited_pages, "evidence_items": len(reply.evidence)},
        output={
            "citations_ok": citations.ok,
            "quotes_supported": grounding.quotes_supported,
            "numeric_support": grounding.numeric_support,
            "grounding_ok": grounding.ok,
        },
        usd=0.0,
        latency_s=time.perf_counter() - verify_started,
    )
    return B1Result(
        question=question,
        pdf=str(pdf_path),
        retriever=retriever.name,
        fallback_reason=fallback_reason,
        retrieved_pages=selected,
        supplied_pages=supplied,
        dropped_pages=dropped,
        estimated_prompt_tokens=prompt_tokens,
        cost_upper_usd=round(cost_upper, 9),
        request_fingerprint=fingerprint,
        cache_hit=cache_hit,
        reply=reply,
        citations=citations,
        grounding=grounding,
        trace=(retrieve_step, read_step, verify_step),
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
    parser.add_argument("--max-cost-usd", type=float, default=MAX_REQUEST_COST_USD,
                        help="refuse, before calling the model, a request that could cost more (default %(default)s)")
    args = parser.parse_args(argv)

    create = openai_create() if args.live else OfflineReader()
    result = answer_question(args.pdf, args.question, create, top_k=args.top_k, max_cost_usd=args.max_cost_usd)
    print(json.dumps(result.to_dict(), indent=2, default=str))
    if not args.live:
        print("Offline mode: the answer above is a placeholder from OfflineReader, not a model result.", file=sys.stderr)
    return result


if __name__ == "__main__":
    main()
