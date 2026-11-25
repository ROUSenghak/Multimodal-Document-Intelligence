"""The B1 application: ask a question about a PDF, get an answer with cited pages and quotes.

    PDF ──► 768-px page images ──► ColQwen2 MaxSim over every page ──► top k = 4 pages
        ──► one gpt-6-luna call, contract b1 (answer, cited pages, verbatim quotes)
        ──► citation check + grounding check

This is a thin service around the pinned modules. Retrieval, reading and verification are
``pipeline.answer_question_b1`` unchanged: E8 measured exactly that function, so the app
ships what was evaluated. The app adds only what a user needs around it:

- documents: content-addressed registration (SHA-256), the product's page cap, a guard
  that refuses the untouched MMLongBench-Doc test pool (AGENTS.md);
- the visual index (``visual_index``): ColQwen2 page embeddings stored under
  (PDF SHA-256, render profile, model revision). Without one, or without a query
  embedding, B1 falls back to BM25 and the reason is recorded in the result;
- BM25 (native text + OCR fallback) computed for every question and logged beside the
  primary ranking, as the B1 specification requires;
- spending guards: the reader profile's per-request check (``check_profiled_request``,
  run inside ``answer_question_b1`` before any call) bounded by the session's remaining
  budget, so a request that could exceed either ceiling is refused before it is sent;
- a persistent reply cache and an append-only run log in git-ignored ``data/cache/app/``.

Grounding (quotes found on the cited page, numbers present) is shown as a trust signal
for the reader of the answer. It is not a correctness signal (E8 found it anti-predictive)
and nothing here uses it to retry or repair an answer. There is no adaptive retrieval:
E9 is testing that; ``k`` is the only retrieval parameter.

Offline by default: ``OfflineB1Reader`` returns a clearly labelled placeholder and calls
no model. ``--live`` calls the paid OpenAI API and needs ``OPENAI_API_KEY`` exported in
the environment (``.env`` is never read).

    python -m visualdoc.app ask data/documents/ch2.pdf "What does Cromwell's rule say?"
    python -m visualdoc.app index data/external/mmlongbench_doc/documents/watch_d.pdf --from-e5-cache
    python -m visualdoc.app serve
"""

import argparse
import hashlib
import json
import os
import re
import sys
import time
from collections import OrderedDict
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

from .answering import LUNA_PROFILE, check_profiled_request, profiled_request_fingerprint
from .documents import OCR_MIN_NATIVE_WORDS, extract_pages, inspect_document, open_pdf, render_pages, sha256_file
from .pipeline import B1Result, Budget, JsonlReplyCache, Step, answer_question_b1
from .retrieval import BM25Index, CachedVisualIndex
from .visual_index import (
    REPO_ROOT,
    ColQwen2Encoder,
    IndexKey,
    StoreQueryEncoder,
    VisualIndexStore,
    atomic_write_bytes,
    import_e5_document,
    import_e5_queries,
)

DEFAULT_DATA_DIR = REPO_ROOT / "data" / "cache" / "app"  # git-ignored (data/cache/)
DEFAULT_E5_CACHE = REPO_ROOT / "data" / "cache" / "e5" / "colqwen2-v1.0-hf@ddc07d2317c8" / "af02fac2cb9b"
LOCAL_DOCUMENTS_DIR = REPO_ROOT / "data" / "documents"
MMLB_DOCUMENTS_DIR = REPO_ROOT / "data" / "external" / "mmlongbench_doc" / "documents"

# The 20 MMLongBench-Doc documents used in E0-E7 (6 development + 14 E5 held-out), i.e. the
# doc_id set of experiments/frozen/e5/tables/rankings.parquet (a test checks the equality).
# Every other MMLongBench-Doc document is the untouched test pool: no system output for it.
DEVELOPMENT_DOCUMENTS = frozenset({
    "2210.02442v1.pdf",
    "PG_2020.05.21_International-Cooperation-COVID_FINAL.pdf",
    "bdf54dxa.pdf",
    "earlybird-110722143746-phpapp02_95.pdf",
    "germanwingsdigitalcrisisanalysis-150403064828-conversion-gate01_95.pdf",
    "watch_d.pdf",
    "11-21-16-Updated-Post-Election-Release.pdf",
    "2021-Apple-Catalog.pdf",
    "2310.05634v2.pdf",
    "2312.10997v5.pdf",
    "3276a5b991c49cf5f9a4af0f7d6fce67.pdf",
    "AMAZON_2017_10K.pdf",
    "COSTCO_2021_10K.pdf",
    "Macbook_air.pdf",
    "NUS-Business-School-BBA-Brochure-2024.pdf",
    "SAO-StudentSupport_Guidebook-Content.pdf",
    "chapter8-geneticscompatibilitymode-141214140247-conversion-gate02_95.pdf",
    "ddoseattle-150627210357-lva1-app6891_95.pdf",
    "e639029d16094ea71d964e2fb953952b.pdf",
    "efd88e41c5f2606c57929cac6c1c0605.pdf",
})

B1_K = 4  # E6 read 4 pages for 105/118 questions; E8 read the top 4 of the ColQwen2 ranking
MAX_K = 10  # an upper bound on the one retrieval parameter, to keep cost and latency bounded
MAX_PDF_PAGES = 200  # B1 product contract: "up to about 200 pages (a configuration value)"
MAX_QUESTION_CHARS = 2_000
MAX_UPLOAD_BYTES = 50 * 1024 * 1024
# A 4-page B1 request is bounded by about $0.0008 at list price (E8: 4,013 prompt tokens + 800 output).
# These ceilings stop configuration or price mistakes; lower them to cap spending more tightly.
PER_REQUEST_CEILING_USD = 0.01
SESSION_CEILING_USD = 0.10
# Live client settings, as in the notebooks' executors: no silent retry (each retry could be billed while
# the session is charged once) and a bounded wait.
OPENAI_MAX_RETRIES = 0
OPENAI_TIMEOUT_S = 120

# Every MMLongBench-Doc document name (revision 2ff6aa92...), read from the doc_id column only, and the
# SHA-256 of the pool PDFs whose bytes were on disk. A test pins this file's SHA-256.
BENCHMARK_DOCUMENTS_FILE = REPO_ROOT / "resources" / "mmlongbench_doc_documents.json"
_BENCHMARK = json.loads(BENCHMARK_DOCUMENTS_FILE.read_text())
BENCHMARK_DOCUMENTS = frozenset(_BENCHMARK["documents"])
if not DEVELOPMENT_DOCUMENTS <= BENCHMARK_DOCUMENTS:
    raise RuntimeError(f"{BENCHMARK_DOCUMENTS_FILE.name} does not list the 20 development documents")
POOL_DOCUMENTS = BENCHMARK_DOCUMENTS - DEVELOPMENT_DOCUMENTS  # 115 documents: the untouched test pool
POOL_PDF_SHA256 = frozenset(_BENCHMARK["pool_pdf_sha256"].values())


class CostRefused(ValueError):
    """A request was refused before any model call because it could exceed a spending ceiling."""


class PoolDocumentRefused(PermissionError):
    """The document belongs to the untouched MMLongBench-Doc test pool."""


def is_test_pool_document(name: str) -> bool:
    """True for any MMLongBench-Doc document name outside the 20 development documents, on disk or not.

    The check is by name (plus, in ``open_document``, by SHA-256 for the few pool PDFs whose
    bytes were on disk). A renamed copy of a pool PDF that was never hashed is not recognised;
    the final-evaluation protocol remains the safeguard.
    """
    return name in POOL_DOCUMENTS


def openai_b1_create() -> Callable[..., Any]:
    """The paid client's ``create``, with no automatic retry and a 120 s timeout (the notebooks' settings)."""
    if not os.environ.get("OPENAI_API_KEY"):  # exported in the environment; .env files are never read here
        raise RuntimeError("live mode needs OPENAI_API_KEY in the environment (paid calls to gpt-6-luna)")
    try:
        from openai import OpenAI  # imported only for live runs
    except ImportError as error:
        raise RuntimeError(f"live mode needs the openai package (visualdoc-ai[llm]): {error}") from error
    return OpenAI(max_retries=OPENAI_MAX_RETRIES, timeout=OPENAI_TIMEOUT_S).chat.completions.create


@dataclass(frozen=True)
class Document:
    sha256: str  # content key: the same bytes under another name are the same document
    path: Path
    name: str
    page_count: int
    born_digital: bool  # every page has >= 30 native words
    ocr_pages: tuple[int, ...]  # pages read by OCR (image-only: best effort, flagged in the output)


@dataclass(frozen=True)
class AppAnswer:
    """One answered question: the B1 result plus what the user and the log need around it."""

    result: B1Result
    document: Document
    mode: str  # "offline" (placeholder reader) or "live"
    bm25_pages: list[int]  # BM25 top k, logged beside the primary ranking
    ocr_supplied_pages: list[int]  # supplied pages whose text came from OCR (image-only pages)
    charged_usd: float  # upper bound charged to the session (0 offline and on a cache hit)
    observed_usd: float | None  # list-price cost from the reply's token usage, when the API reported it
    session_spent_usd: float
    session_ceiling_usd: float
    identity_warning: str | None

    @property
    def offline(self) -> bool:
        return self.mode == "offline"

    def to_dict(self) -> dict[str, Any]:
        document = asdict(self.document)
        document["path"] = str(self.document.path)
        return {
            "mode": self.mode,
            "offline_placeholder": self.offline,
            "document": document,
            "bm25_pages": self.bm25_pages,
            "ocr_supplied_pages": self.ocr_supplied_pages,
            "charged_usd": self.charged_usd,
            "observed_usd": self.observed_usd,
            "session_spent_usd": self.session_spent_usd,
            "session_ceiling_usd": self.session_ceiling_usd,
            "identity_warning": self.identity_warning,
            "max_output_tokens": LUNA_PROFILE.max_output_tokens,
            "result": self.result.to_dict(),
        }


class OfflineB1Reader:
    """Stand-in for gpt-6-luna under contract b1: no network, no model, a placeholder answer.

    It cites the first page it was given and quotes that page's first words, so the citation
    and grounding checks run on a reply of the right shape. Nothing it returns is a result.
    """

    ANSWER = "OFFLINE PLACEHOLDER: no model was called"
    SERVED_MODEL = "offline-placeholder"
    PAGE_TAG = re.compile(r"\[Page (\d+)\]")

    def __init__(self, page_texts: dict[int, str] | None = None):
        self.page_texts = page_texts or {}
        self.requests: list[dict] = []

    def __call__(self, **request):
        self.requests.append(request)
        tags = [int(match.group(1)) for part in request["messages"][1]["content"] if part["type"] == "text"
                for match in [self.PAGE_TAG.fullmatch(part["text"])] if match]
        quote = " ".join(self.page_texts.get(tags[0], "").split()[:12])
        payload = {"answer": self.ANSWER, "cited_pages": tags[:1], "evidence": [{"page": tags[0], "quote": quote}] if quote else []}
        message = SimpleNamespace(content=json.dumps(payload))
        return SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason="stop")],
                               model=self.SERVED_MODEL, system_fingerprint=None, usage=None)


class AppReplyCache(JsonlReplyCache):
    """The pipeline's persistent reply cache, minus failed replies: a parse error is retried, never replayed."""

    def put(self, fingerprint, reply):
        if reply.error is None:
            super().put(fingerprint, reply)


class UnavailableRetriever:
    """Takes the visual retriever's place when it cannot run; answer_question_b1 records why and uses BM25."""

    name = "visual"

    def __init__(self, reason: str):
        self.reason = reason

    def rank(self, question: str):
        raise RuntimeError(self.reason)


class B1App:
    """The B1 service used by the CLI and the web UI. One instance is one session (one spend ledger)."""

    def __init__(
        self,
        *,
        data_dir: str | Path = DEFAULT_DATA_DIR,
        live: bool = False,
        create: Callable[..., Any] | None = None,
        encoder: Any | None = None,
        k: int = B1_K,
        per_request_ceiling_usd: float = PER_REQUEST_CEILING_USD,
        session_ceiling_usd: float = SESSION_CEILING_USD,
        max_pages: int = MAX_PDF_PAGES,
        max_upload_bytes: int = MAX_UPLOAD_BYTES,
    ):
        for name, value in (("per_request_ceiling_usd", per_request_ceiling_usd), ("session_ceiling_usd", session_ceiling_usd)):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 < value < float("inf"):
                raise ValueError(f"{name} must be a positive number of USD")
        self.k = self._checked_k(k)
        self.live = bool(live)
        if self.live and create is None:
            create = openai_b1_create()
        # Live: the API's create (or a test's mock). Offline: never used; a placeholder reader answers instead.
        self.create = create if self.live else None
        self.mode = "live" if self.live else "offline"
        self.data_dir = Path(data_dir)
        self.store = VisualIndexStore(self.data_dir / "visual_index")
        self.encoder = encoder
        self.per_request_ceiling_usd = float(per_request_ceiling_usd)
        self.session_ceiling_usd = float(session_ceiling_usd)
        self.max_pages, self.max_upload_bytes = max_pages, max_upload_bytes
        # Offline placeholders and live replies never share a cache file: the request fingerprint is the same.
        cache_name = f"replies_live_{LUNA_PROFILE.model}.jsonl" if self.live else "replies_offline.jsonl"
        self.cache = AppReplyCache(self.data_dir / cache_name)
        self.run_log_path = self.data_dir / "run_log.jsonl"
        self.spent_usd = 0.0
        self.served_identity: tuple | None = None
        self._question = ""
        self.documents: dict[str, Document] = {}
        self._texts: dict[str, dict[int, str]] = {}
        self._indexes: OrderedDict[str, dict] = OrderedDict()  # a few documents' embeddings in memory
        self._thumbnails: OrderedDict[tuple[str, int], bytes] = OrderedDict()

    @staticmethod
    def _checked_k(k: Any) -> int:
        if isinstance(k, bool) or not isinstance(k, int) or not 1 <= k <= MAX_K:
            raise ValueError(f"k must be an integer from 1 to {MAX_K} (B1 uses {B1_K})")
        return k

    # --- documents ---------------------------------------------------------------------------------

    def open_document(self, path: str | Path, *, display_name: str | None = None) -> Document:
        """Validate and register a PDF; refuses the test pool, encrypted files and documents over the page cap."""
        path = Path(path).resolve()  # one spelling per file, so the UI lists it once
        name = display_name or path.name
        refusal = f"{name} is in the untouched MMLongBench-Doc test pool: no system output until the final-evaluation " \
                  "specification is approved (AGENTS.md)"
        if is_test_pool_document(path.name) or is_test_pool_document(name):
            raise PoolDocumentRefused(refusal)
        if path.is_file() and sha256_file(path) in POOL_PDF_SHA256:  # a renamed copy of a hashed pool PDF
            raise PoolDocumentRefused(refusal)
        with open_pdf(path) as pdf:  # clear errors for missing, corrupt or encrypted files
            page_count = pdf.page_count
        if page_count == 0:
            raise ValueError(f"{name} has no pages")
        if page_count > self.max_pages:  # checked before any page text is read
            raise ValueError(f"{name} has {page_count} pages; this app accepts up to {self.max_pages}")
        profile = inspect_document(path)
        ocr_pages = tuple(i + 1 for i, words in enumerate(profile.native_words_per_page) if words < OCR_MIN_NATIVE_WORDS)
        document = Document(profile.sha256, path, name, profile.page_count, profile.born_digital, ocr_pages)
        self.documents[document.sha256] = document
        return document

    def save_upload(self, data: bytes, filename: str) -> Document:
        """Store uploaded PDF bytes under their SHA-256 (identical uploads share one file) and register them."""
        if len(data) > self.max_upload_bytes:
            raise ValueError(f"the upload has {len(data):,} bytes; the limit is {self.max_upload_bytes:,}")
        if not data.startswith(b"%PDF-"):
            raise ValueError("the upload is not a PDF")
        name = Path(str(filename or "upload.pdf")).name[:200]  # display only; never used as a path
        if is_test_pool_document(name):
            raise PoolDocumentRefused(f"{name} is in the untouched MMLongBench-Doc test pool")
        path = self.data_dir / "uploads" / f"{hashlib.sha256(data).hexdigest()}.pdf"
        created = not path.is_file()
        if created:
            atomic_write_bytes(path, data)
        try:
            return self.open_document(path, display_name=name)
        except Exception:
            if created:  # a refused upload (corrupt, encrypted, too long, pool) is not kept
                path.unlink(missing_ok=True)
            raise

    def library(self) -> dict[str, Path]:
        """PDFs offered by the UI: the project's own documents and the development MMLongBench-Doc documents."""
        choices = {path.name: path for path in sorted(LOCAL_DOCUMENTS_DIR.glob("*.pdf"))}
        for name in sorted(DEVELOPMENT_DOCUMENTS):
            if (MMLB_DOCUMENTS_DIR / name).is_file():
                choices[name] = MMLB_DOCUMENTS_DIR / name
        return choices

    def page_texts(self, document: Document) -> dict[int, str]:
        """Page text by the frozen policy (native layer, OCR below 30 words), computed once per document."""
        if document.sha256 not in self._texts:
            self._texts[document.sha256] = {page.page: page.text for page in extract_pages(document.path)}
        return self._texts[document.sha256]

    def page_png(self, document: Document, page: int) -> bytes:
        """The 768-px page image the reader receives (for thumbnails); a few are kept in memory."""
        key = (document.sha256, page)
        if key not in self._thumbnails:
            self._thumbnails[key] = render_pages(document.path, [page])[page]
            while len(self._thumbnails) > 32:
                self._thumbnails.popitem(last=False)
        return self._thumbnails[key]

    # --- visual index ------------------------------------------------------------------------------

    def build_visual_index(self, document: Document, *, e5_cache_dir: str | Path | None = None) -> IndexKey:
        """Create the document's visual index from the E5 cache, or with the encoder this app was given."""
        if e5_cache_dir is not None:
            key = import_e5_document(document.path, e5_cache_dir, self.store)
            import_e5_queries(e5_cache_dir, self.store)
        else:
            if self.encoder is None:
                raise RuntimeError("no encoder: use --from-e5-cache (development documents) or --load-encoder "
                                   "(loads the 4.4 GB ColQwen2 checkpoint)")
            images = render_pages(document.path, list(range(1, document.page_count + 1)))
            embeddings = self.encoder.encode_pages(images)
            key = IndexKey(document.sha256)
            self.store.save(key, embeddings, png_sha256={p: hashlib.sha256(png).hexdigest() for p, png in images.items()},
                            encoder=self.encoder.describe())
        self._indexes.pop(document.sha256, None)
        return key

    def visual_retriever(self, document: Document) -> CachedVisualIndex | UnavailableRetriever:
        """ColQwen2 MaxSim over the stored page embeddings, or a stand-in that states why it is unavailable."""
        if document.sha256 not in self._indexes:
            key = IndexKey(document.sha256)
            pages = self.store.load(key)  # IndexKeyMismatch (a ValueError) propagates: never reuse a wrong index
            if pages is None:
                return UnavailableRetriever(
                    f"no visual index for this PDF (sha256 {document.sha256[:12]}, {key.render_profile}, "
                    f"{key.model_id}@{key.model_revision[:12]}); build it with "
                    "`python -m visualdoc.app index <pdf> --from-e5-cache` or `--load-encoder`"
                )
            if len(pages) != document.page_count:
                raise ValueError(f"the visual index has {len(pages)} pages, the PDF {document.page_count}")
            self._indexes[document.sha256] = pages
            while len(self._indexes) > 4:  # about 80 MB per 200-page document in float32
                self._indexes.popitem(last=False)
        return CachedVisualIndex(self._indexes[document.sha256], StoreQueryEncoder(self.store, self.encoder))

    # --- asking ------------------------------------------------------------------------------------

    def ask(self, document: Document | str | Path, question: str, *, k: int | None = None) -> AppAnswer:
        """B1 on one question: retrieve once, read once, verify once, under the per-request and session ceilings."""
        document = document if isinstance(document, Document) else self.open_document(document)
        question = str(question)
        if not question.strip():
            raise ValueError("the question is empty")
        if len(question) > MAX_QUESTION_CHARS:
            raise ValueError(f"the question has {len(question):,} characters; the limit is {MAX_QUESTION_CHARS:,}")
        k = self.k if k is None else self._checked_k(k)
        remaining = round(self.session_ceiling_usd - self.spent_usd, 9)
        if remaining <= 0:
            raise CostRefused(f"session ceiling reached (${self.spent_usd:.6f} of ${self.session_ceiling_usd:.2f}); no call made")
        # The pinned per-request check (check_profiled_request) enforces Budget.max_usd before any call;
        # giving it the smaller of the two limits makes it enforce the session ceiling as well.
        budget = Budget(max_calls=1, max_pages=k, max_usd=min(self.per_request_ceiling_usd, remaining))

        texts = self.page_texts(document)
        started = time.perf_counter()
        bm25_pages = [page for page, _ in BM25Index(texts).rank(question)[:k]]
        bm25_step = Step(
            action="baseline_retrieve",
            inputs={"retriever": "bm25", "k": k},
            output={"pages": bm25_pages, "role": "logged beside the primary ranking; used only on fallback"},
            usd=0.0,
            latency_s=time.perf_counter() - started,
        )
        create = self._send_live if self.live else OfflineB1Reader(texts)
        spent_before = self.spent_usd
        self._question = question  # for the attempt record written just before a live send
        try:
            result = answer_question_b1(document.path, question, create, primary_retriever=self.visual_retriever(document),
                                        k=k, budget=budget, cache=self.cache)
        except ValueError as error:
            if "per-request ceiling" in str(error):
                raise CostRefused(f"refused before any model call: {error} (per-request ceiling "
                                  f"${self.per_request_ceiling_usd:.6f}, session remaining ${remaining:.6f})") from error
            raise
        retrieve, read, verify = result.trace
        if not self.live:  # nothing was spent: the read step's upper bound is not reported as spend
            read = replace(read, usd=0.0)
        result = replace(result, trace=(retrieve, read, verify, bm25_step))

        reply = result.reply
        observed = None
        if self.live and not result.cache_hit and reply.prompt_tokens is not None and reply.completion_tokens is not None:
            observed = round((reply.prompt_tokens * LUNA_PROFILE.usd_per_1m_input
                              + reply.completion_tokens * LUNA_PROFILE.usd_per_1m_output) / 1e6, 9)
            charged_so_far = self.spent_usd - spent_before
            if observed > charged_so_far:  # the bound was too low (it should not be): charge the difference
                self.spent_usd = round(self.spent_usd + observed - charged_so_far, 9)
        charged = round(self.spent_usd - spent_before, 9)  # 0 offline and on a cache hit
        identity_warning = self._identity_warning(result)
        self._log({"record": "answer", "mode": self.mode, "charged_usd": charged, "observed_usd": observed,
                   "session_spent_usd": self.spent_usd, "document_sha256": document.sha256,
                   "identity_warning": identity_warning, **result.to_dict()})
        return AppAnswer(
            result=result,
            document=document,
            mode=self.mode,
            bm25_pages=bm25_pages,
            ocr_supplied_pages=[page for page in result.supplied_pages if page in document.ocr_pages],
            charged_usd=charged,
            observed_usd=observed,
            session_spent_usd=self.spent_usd,
            session_ceiling_usd=self.session_ceiling_usd,
            identity_warning=identity_warning,
        )

    def _log(self, record: dict[str, Any]) -> None:
        """Append one JSON line to the run log (append_run_log's format, plus mode and charge fields)."""
        record = {"time": datetime.now(timezone.utc).isoformat(timespec="milliseconds"), **record}
        self.run_log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.run_log_path.open("a") as handle:
            handle.write(json.dumps(record, sort_keys=True, default=str) + "\n")

    def _send_live(self, **request):
        """Send one request to the paid API, charging its upper bound to the session first.

        Charging before sending (E8's rule) counts a call that fails or times out after it
        was sent, which may still be billed. answer_question_b1 has already refused, before
        this point, any request whose upper bound exceeds the per-request or session limit.
        """
        _, upper = check_profiled_request(request, profile=LUNA_PROFILE, max_cost_usd=self.per_request_ceiling_usd)
        self.spent_usd = round(self.spent_usd + upper, 9)
        attempt = {"mode": "live", "request_fingerprint": profiled_request_fingerprint(request), "question": self._question,
                   "cost_upper_usd": round(upper, 9), "charged_usd": round(upper, 9), "session_spent_usd": self.spent_usd}
        self._log({"record": "attempt", **attempt})  # written before sending: a failed paid call stays on record
        try:
            return self.create(**request)
        except Exception as error:
            self._log({"record": "attempt_failed", **attempt, "error": f"{type(error).__name__}: {error}"})
            raise

    def _identity_warning(self, result: B1Result) -> str | None:
        """gpt-6-luna is an alias: a change of served model or fingerprint is a new condition (AGENTS.md).

        Cached replies are checked too: the reply cache is keyed by the request fingerprint only
        (the served model is known only after a call), so a replayed reply may come from another
        served identity than the replies of this session.
        """
        if not self.live:
            return None
        source = "cached reply" if result.cache_hit else "reply"
        identity = (result.reply.served_model, result.reply.system_fingerprint)
        if result.reply.served_model != LUNA_PROFILE.model:
            return f"{source} served by {result.reply.served_model!r}, not the requested {LUNA_PROFILE.model!r}"
        if self.served_identity is None:
            self.served_identity = identity
        elif identity != self.served_identity:
            return f"{source} has served identity {identity}, this session started with {self.served_identity}"
        return None


# --- command line ----------------------------------------------------------------------------------------


def _summary(answer: AppAnswer) -> str:
    """A short human-readable report of one answer."""
    result = answer.result
    lines = []
    if answer.offline:
        lines.append("*** OFFLINE PLACEHOLDER: no model was called; the answer below is not a result ***")
    placeholder = "  [computed on a placeholder reply]" if answer.offline else ""
    answer_text = result.reply.answer if result.reply.error is None else f"(reply error: {result.reply.error})"
    lines += [
        f"Document : {answer.document.name} ({answer.document.page_count} pages, sha256 {answer.document.sha256[:12]})",
        f"Answer   : {json.dumps(answer_text, ensure_ascii=False) if not isinstance(answer_text, str) else answer_text}",
        f"Cited    : {result.reply.cited_pages}   citations ok: {result.citations.ok}{placeholder}",
        f"Retriever: {result.retriever}" + (f" (fallback: {result.fallback_reason})" if result.fallback_reason else ""),
        f"Pages    : supplied {result.supplied_pages}; BM25 top-{len(answer.bm25_pages)} {answer.bm25_pages}",
    ]
    for (page, score), item in zip(result.grounding.quote_scores, result.reply.evidence):
        flag = "found on page" if score >= result.grounding.threshold else "NOT found on page"
        lines.append(f"Quote p.{page}: {item.quote!r} -> {flag} (match {score:.2f})")
    lines += [
        "Grounding: " + ("quotes supported" if result.grounding.quotes_supported else "quotes NOT all supported")
        + f"; numeric support: {result.grounding.numeric_support}  (trust signal, not a correctness check){placeholder}",
        f"Cost     : <= {result.estimated_prompt_tokens:,} prompt + {LUNA_PROFILE.max_output_tokens} output tokens, "
        f"<= ${result.cost_upper_usd:.6f}; charged ${answer.charged_usd:.6f}; session ${answer.session_spent_usd:.6f} "
        f"of ${answer.session_ceiling_usd:.2f}" + ("; cache hit" if result.cache_hit else ""),
    ]
    if answer.identity_warning:
        lines.append(f"WARNING  : {answer.identity_warning}")
    return "\n".join(lines)


def _app_from_args(args) -> B1App:
    encoder = None
    if getattr(args, "load_encoder", False):
        # Checks the checkpoint with os.stat only; the model itself is loaded on first use.
        encoder = ColQwen2Encoder(work_dir=Path(args.data_dir) / "encoder_work")
    return B1App(data_dir=args.data_dir, live=getattr(args, "live", False), encoder=encoder,
                 per_request_ceiling_usd=args.max_request_usd, session_ceiling_usd=args.session_ceiling_usd)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m visualdoc.app", description="VisualDoc B1: cited answers about a PDF.")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR, help="caches, uploads and logs (default %(default)s)")
    parser.add_argument("--max-request-usd", type=float, default=PER_REQUEST_CEILING_USD, help="per-request ceiling (default %(default)s)")
    parser.add_argument("--session-ceiling-usd", type=float, default=SESSION_CEILING_USD, help="session ceiling (default %(default)s)")
    commands = parser.add_subparsers(dest="command", required=True)

    ask = commands.add_parser("ask", help="answer one question about one PDF")
    ask.add_argument("pdf", type=Path)
    ask.add_argument("question")
    ask.add_argument("--k", type=int, default=B1_K, help="pages read by the model (default %(default)s, as in B1)")
    ask.add_argument("--live", action="store_true", help="call gpt-6-luna (paid; needs OPENAI_API_KEY exported)")
    ask.add_argument("--load-encoder", action="store_true", help="allow loading ColQwen2 (4.4 GB) to encode a new question")
    ask.add_argument("--json", action="store_true", help="print the full result as JSON")

    index = commands.add_parser("index", help="build the visual index of a PDF")
    index.add_argument("pdf", type=Path)
    index.add_argument("--from-e5-cache", type=Path, nargs="?", const=DEFAULT_E5_CACHE, default=None,
                       help="import notebook 04's embeddings (development documents; default %(const)s)")
    index.add_argument("--load-encoder", action="store_true", help="encode with ColQwen2 (loads 4.4 GB; ~13 s per page on an M1)")

    serve = commands.add_parser("serve", help="start the local web UI on 127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--live", action="store_true", help="call gpt-6-luna (paid; needs OPENAI_API_KEY exported)")
    serve.add_argument("--load-encoder", action="store_true", help="allow loading ColQwen2 (4.4 GB) to encode new questions")

    args = parser.parse_args(argv)
    try:
        app = _app_from_args(args)
        if args.command == "ask":
            answer = app.ask(args.pdf, args.question, k=args.k)
            print(json.dumps(answer.to_dict(), indent=2, default=str) if args.json else _summary(answer))
            if answer.offline:
                print("Offline mode: the answer is a placeholder from OfflineB1Reader, not a model result.", file=sys.stderr)
        elif args.command == "index":
            document = app.open_document(args.pdf)
            key = app.build_visual_index(document, e5_cache_dir=args.from_e5_cache)
            print(f"Visual index for {document.name}: {app.store.path(key)}")
        else:
            from .web import serve_forever

            serve_forever(app, port=args.port)
    except (ValueError, RuntimeError, PermissionError, FileNotFoundError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
