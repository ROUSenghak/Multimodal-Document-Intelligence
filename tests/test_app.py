"""The B1 application service: offline answers, visual index and BM25 fallback, spending guards, caches, CLI.

Every model call here is a stand-in: the offline placeholder reader, or a mocked API
response (interface tests only, never results). The regression test at the end replays
frozen E8 replies through the application.
"""

import hashlib
import json
import sys
from types import ModuleType, SimpleNamespace

import numpy as np
import pymupdf
import pytest

from conftest import MMLB_DOCUMENTS, REPO_ROOT, read_jsonl
import visualdoc.app as app_module
from visualdoc.app import (
    B1App,
    CostRefused,
    DEVELOPMENT_DOCUMENTS,
    OfflineB1Reader,
    PoolDocumentRefused,
    main,
)
from visualdoc.answering import profiled_request_fingerprint
from visualdoc.retrieval import maxsim_score
from visualdoc.visual_index import EMBEDDING_DIM, SF_DATALESS, IndexKey, IndexKeyMismatch, query_sha256

E5_CACHE = REPO_ROOT / "data" / "cache" / "e5" / "colqwen2-v1.0-hf@ddc07d2317c8" / "af02fac2cb9b"
E8_RUN = REPO_ROOT / "experiments" / "frozen" / "e8" / "run_20261125T140433934010Z_4edb90e7_full"
PARITY_DOCUMENTS = ["e639029d16094ea71d964e2fb953952b.pdf", "efd88e41c5f2606c57929cac6c1c0605.pdf"]
TOPICS = ["revenue grew to 495 million dollars", "employees work in seven countries", "the board met four times",
          "carbon emissions fell by ten percent", "the new factory opened in Lyon"]


def make_pdf(path, topics=TOPICS):
    """A born-digital PDF, one topic per page, each page well above the 30-word OCR threshold."""
    document = pymupdf.open()
    for topic in topics:
        page = document.new_page(width=612, height=792)
        page.insert_textbox((50, 50, 560, 740), (f"In this report {topic}. " * 8).strip(), fontsize=11)
    document.save(path)
    document.close()
    return path


def unit_rows(seed_text, rows):
    seed = int.from_bytes(hashlib.sha256(seed_text if isinstance(seed_text, bytes) else seed_text.encode()).digest()[:8], "little")
    matrix = np.random.default_rng(seed).normal(size=(rows, EMBEDDING_DIM)).astype(np.float32)
    return matrix / np.linalg.norm(matrix, axis=1, keepdims=True)


class FakeEncoder:
    """Deterministic stand-in for ColQwen2 (tests only): vectors seeded by content hashes."""

    def __init__(self):
        self.queries = []

    def encode_pages(self, pngs):
        return {page: unit_rows(png, 6) for page, png in pngs.items()}

    def encode_query(self, question):
        self.queries.append(question)
        return unit_rows(question, 3)

    def describe(self):
        return {"encoder": "fake (tests)"}


def mocked_reply(payload, *, model="gpt-6-luna", fingerprint=None, prompt=4000, completion=40):
    """A mocked Chat Completions response (interface test only)."""
    message = SimpleNamespace(content=payload if isinstance(payload, str) else json.dumps(payload))
    return SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason="stop")], model=model,
                           system_fingerprint=fingerprint, usage=SimpleNamespace(prompt_tokens=prompt, completion_tokens=completion))


class RecordingAPI:
    """Mocked paid API: records requests and answers 495 with an evidence quote from page 1."""

    def __init__(self, payload=None, **reply_options):
        self.requests, self.payload, self.reply_options = [], payload, reply_options

    def __call__(self, **request):
        self.requests.append(request)
        payload = self.payload or {"answer": 495, "cited_pages": [1],
                                   "evidence": [{"page": 1, "quote": "In this report revenue grew to 495 million dollars."}]}
        return mocked_reply(payload, **self.reply_options)


@pytest.fixture
def pdf(tmp_path):
    return make_pdf(tmp_path / "report.pdf")


# --- documents ------------------------------------------------------------------------------------------


BENCHMARK_DOCUMENTS_SHA256 = "943a3ded03c78815b01809195922e2cf2a755f83bec967b755ca48d75cf72fe4"


def test_development_documents_are_exactly_the_20_used_in_e0_to_e7():
    pd = pytest.importorskip("pandas")
    frozen = pd.read_parquet(REPO_ROOT / "experiments" / "frozen" / "e5" / "tables" / "rankings.parquet")
    assert DEVELOPMENT_DOCUMENTS == set(frozen["doc_id"]) and len(DEVELOPMENT_DOCUMENTS) == 20
    spec = json.loads((REPO_ROOT / "experiments" / "specs" / "e5_visual_retrieval_v1.json").read_text())
    held_out = set(spec["populations"]["held_out"]["selected_documents"])
    assert len(held_out) == 14 and held_out <= DEVELOPMENT_DOCUMENTS
    assert len(DEVELOPMENT_DOCUMENTS - held_out) == spec["populations"]["development"]["documents"] == 6


def test_frozen_benchmark_document_list_defines_the_115_pool_documents():
    resource = app_module.BENCHMARK_DOCUMENTS_FILE
    assert hashlib.sha256(resource.read_bytes()).hexdigest() == BENCHMARK_DOCUMENTS_SHA256
    frozen = json.loads(resource.read_text())
    assert frozen["revision"] == "2ff6aa9237fc777b6627dc57a486e9225ac5fb86"
    assert frozen["documents"] == sorted(set(frozen["documents"])) and len(frozen["documents"]) == 135
    assert len(app_module.POOL_DOCUMENTS) == 115 and not app_module.POOL_DOCUMENTS & DEVELOPMENT_DOCUMENTS
    assert set(frozen["pool_pdf_sha256"]) <= app_module.POOL_DOCUMENTS


def test_test_pool_documents_are_refused_on_disk_or_not(tmp_path, monkeypatch):
    absent = "2312.04350v3.pdf"  # a pool document whose PDF was never downloaded
    assert absent in app_module.POOL_DOCUMENTS and not (app_module.MMLB_DOCUMENTS_DIR / absent).exists()
    app = B1App(data_dir=tmp_path / "data")
    copy = make_pdf(tmp_path / absent)  # any file carrying a pool name is refused
    with pytest.raises(PoolDocumentRefused):
        app.open_document(copy)
    with pytest.raises(PoolDocumentRefused):
        app.ask(copy, "What happened?")
    with pytest.raises(PoolDocumentRefused):
        app.save_upload(copy.read_bytes(), absent)
    # A renamed copy of a hashed pool PDF is refused by its SHA-256 (a synthetic PDF stands in for it here).
    renamed = make_pdf(tmp_path / "renamed.pdf", TOPICS[:2])
    monkeypatch.setattr(app_module, "POOL_PDF_SHA256", frozenset({hashlib.sha256(renamed.read_bytes()).hexdigest()}))
    with pytest.raises(PoolDocumentRefused):
        app.open_document(renamed)
    with pytest.raises(PoolDocumentRefused):
        app.save_upload(renamed.read_bytes(), "harmless.pdf")
    assert not list((tmp_path / "data" / "uploads").glob("*.pdf"))  # refused uploads are not kept
    assert app.open_document(make_pdf(tmp_path / "watch_d.pdf")).name == "watch_d.pdf"  # a development name
    assert not set(app.library()) & app_module.POOL_DOCUMENTS
    assert not (tmp_path / "data" / "run_log.jsonl").exists()  # no system output was produced


def test_page_cap_uploads_and_content_addressing(tmp_path, pdf, monkeypatch):
    app = B1App(data_dir=tmp_path / "data", max_pages=4, max_upload_bytes=200_000)

    def no_text_reading(*args, **kwargs):
        raise AssertionError("page text must not be read for a document over the page cap")

    with monkeypatch.context() as patch:
        patch.setattr(app_module, "inspect_document", no_text_reading)
        with pytest.raises(ValueError, match="5 pages"):
            app.open_document(pdf)
        with pytest.raises(ValueError, match="5 pages"):
            app.save_upload(pdf.read_bytes(), "long.pdf")
    with pytest.raises(ValueError, match="cannot open"):
        app.save_upload(b"%PDF-1.7 truncated", "broken.pdf")
    assert not list((tmp_path / "data" / "uploads").glob("*.pdf"))  # refused uploads are deleted
    small = make_pdf(tmp_path / "small.pdf", TOPICS[:2])
    with pytest.raises(ValueError, match="not a PDF"):
        app.save_upload(b"<html>", "x.pdf")
    with pytest.raises(ValueError, match="limit"):
        app.save_upload(b"%PDF-" + b"0" * 300_000, "big.pdf")
    document = app.save_upload(small.read_bytes(), "../../etc/My report.pdf")
    assert document.name == "My report.pdf" and document.page_count == 2 and document.born_digital
    assert document.path == tmp_path / "data" / "uploads" / f"{hashlib.sha256(small.read_bytes()).hexdigest()}.pdf"
    assert app.save_upload(small.read_bytes(), "again.pdf").sha256 == document.sha256  # same bytes, same document


# --- asking offline ---------------------------------------------------------------------------------------


def test_offline_ask_without_visual_index_falls_back_to_bm25_and_says_why(tmp_path, pdf):
    app = B1App(data_dir=tmp_path / "data")
    answer = app.ask(pdf, "How much did revenue grow?")
    result = answer.result
    assert answer.offline and answer.mode == "offline"
    assert result.reply.answer == OfflineB1Reader.ANSWER and result.reply.served_model == "offline-placeholder"
    assert result.retriever == "bm25" and "no visual index for this PDF" in result.fallback_reason
    assert result.supplied_pages[0] == 1 and answer.bm25_pages == result.supplied_pages  # BM25 finds the revenue page
    assert len(result.supplied_pages) == 4  # k = 4, as in B1
    assert result.citations.ok and result.grounding.quotes_supported  # the placeholder quotes page 1 verbatim
    assert answer.charged_usd == 0 and app.spent_usd == 0 and 0 < result.cost_upper_usd < 0.001
    (logged,) = read_jsonl(tmp_path / "data" / "run_log.jsonl")
    assert (logged["record"], logged["mode"], logged["charged_usd"]) == ("answer", "offline", 0.0)
    assert all(step["usd"] == 0 for step in logged["trace"])  # an upper bound is not reported as spend offline
    assert [step["action"] for step in logged["trace"]] == ["retrieve", "read", "verify", "baseline_retrieve"]
    assert logged["trace"][0]["output"]["fallback_reason"] == result.fallback_reason
    assert logged["trace"][3]["output"]["pages"] == answer.bm25_pages
    assert "base64" not in json.dumps(answer.to_dict(), default=str)


def test_visual_index_built_by_an_encoder_is_the_primary_retriever(tmp_path, pdf):
    encoder = FakeEncoder()
    app = B1App(data_dir=tmp_path / "data", encoder=encoder)
    document = app.open_document(pdf)
    key = app.build_visual_index(document)
    assert key == IndexKey(document.sha256) and app.store.has(key)

    question = "Where did the new factory open?"
    answer = app.ask(document, question, k=2)
    result = answer.result
    pages = app.store.load(key)
    query = unit_rows(question, 3)
    expected = sorted(pages, key=lambda p: (-maxsim_score(query, pages[p]), p))[:2]
    assert result.retriever == "visual" and result.fallback_reason is None
    assert result.supplied_pages == expected and len(answer.bm25_pages) == 2
    assert result.trace[3].output["pages"] == answer.bm25_pages  # BM25 still logged beside the visual ranking
    assert encoder.queries == [question] and app.store.load_query(query_sha256(question)) is not None

    # Same index, no live encoder, a question never encoded: BM25 fallback with the reason recorded.
    offline_app = B1App(data_dir=tmp_path / "data")
    fallback = offline_app.ask(document, "How many board meetings were held?").result
    assert fallback.retriever == "bm25" and "live encoder is off" in fallback.fallback_reason
    # ...while the question encoded before is answered from the query cache, visually.
    assert offline_app.ask(document, question, k=2).result.retriever == "visual"


def test_a_visual_index_stored_under_another_key_is_refused_loudly(tmp_path, pdf):
    app = B1App(data_dir=tmp_path / "data", encoder=FakeEncoder())
    other = app.open_document(make_pdf(tmp_path / "other.pdf", TOPICS[:3]))
    app.build_visual_index(other)
    document = app.open_document(pdf)
    target = app.store.path(IndexKey(document.sha256))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(app.store.path(IndexKey(other.sha256)).read_bytes())
    with pytest.raises(IndexKeyMismatch):
        app.ask(document, "How much did revenue grow?")


def test_second_ask_is_a_cache_hit_in_this_and_the_next_session(tmp_path, pdf):
    first_app = B1App(data_dir=tmp_path / "data")
    first = first_app.ask(pdf, "How much did revenue grow?")
    second = first_app.ask(pdf, "How much did revenue grow?")
    assert not first.result.cache_hit and second.result.cache_hit
    assert second.result.request_fingerprint == first.result.request_fingerprint
    later = B1App(data_dir=tmp_path / "data").ask(pdf, "How much did revenue grow?")  # reloaded from disk
    assert later.result.cache_hit and later.result.reply == first.result.reply
    # Live replies live in their own cache file: a placeholder can never be replayed as a live answer.
    api = RecordingAPI()
    live = B1App(data_dir=tmp_path / "data", live=True, create=api).ask(pdf, "How much did revenue grow?")
    assert not live.result.cache_hit and len(api.requests) == 1 and live.result.reply.answer == 495


# --- spending guards (mocked API) -------------------------------------------------------------------------


def test_cost_ceilings_refuse_before_any_call(tmp_path, pdf):
    api = RecordingAPI()
    strict = B1App(data_dir=tmp_path / "a", live=True, create=api, per_request_ceiling_usd=0.000001)
    with pytest.raises(CostRefused, match="refused before any model call"):
        strict.ask(pdf, "How much did revenue grow?")
    assert api.requests == [] and strict.spent_usd == 0

    # Session ceiling: room for two B1 requests (upper bound measured offline on the same PDF), not three.
    upper = B1App(data_dir=tmp_path / "probe").ask(pdf, "How much did revenue grow?").result.cost_upper_usd
    app = B1App(data_dir=tmp_path / "b", live=True, create=api, session_ceiling_usd=2.5 * upper)
    first = app.ask(pdf, "How much did revenue grow?")
    assert first.charged_usd == first.result.cost_upper_usd == upper and app.spent_usd == upper
    assert first.observed_usd == pytest.approx((4000 * 0.10 + 40 * 0.50) / 1e6)
    again = app.ask(pdf, "How much did revenue grow?")  # a cache hit costs nothing
    assert again.result.cache_hit and again.charged_usd == 0 and app.spent_usd == upper
    app.ask(pdf, "Where did the new factory open?")
    with pytest.raises(CostRefused, match="session remaining"):
        app.ask(pdf, "How many board meetings were held?")
    assert len(api.requests) == 2
    app.spent_usd = app.session_ceiling_usd
    with pytest.raises(CostRefused, match="session ceiling reached"):
        app.ask(pdf, "How much did revenue grow?")

    # A call that fails after it was sent may still be billed: the session is charged before sending.
    def timeout(**request):
        raise TimeoutError("no response")

    failing = B1App(data_dir=tmp_path / "c", live=True, create=timeout)
    with pytest.raises(TimeoutError):
        failing.ask(pdf, "How much did revenue grow?")
    assert failing.spent_usd == upper


def test_failed_replies_are_not_cached_and_identity_changes_are_flagged(tmp_path, pdf):
    broken = RecordingAPI(payload='{"answer": 495}')
    app = B1App(data_dir=tmp_path / "data", live=True, create=broken)
    assert app.ask(pdf, "How much did revenue grow?").result.reply.error.startswith("unparseable")
    assert app.ask(pdf, "How much did revenue grow?").result.cache_hit is False and len(broken.requests) == 2

    calls = iter(["fp_a", "fp_b"])
    changing = lambda **request: mocked_reply({"answer": "Not answerable", "cited_pages": [], "evidence": []},
                                              fingerprint=next(calls))
    app = B1App(data_dir=tmp_path / "other", live=True, create=changing)
    assert app.ask(pdf, "First question?").identity_warning is None
    assert "this session started with" in app.ask(pdf, "Second question?").identity_warning
    alias = B1App(data_dir=tmp_path / "alias", live=True, create=RecordingAPI(model="gpt-6-luna-2027"))
    assert "not the requested" in alias.ask(pdf, "How much did revenue grow?").identity_warning

    # A cached reply is checked too: in a new session, a reply cached under another identity is flagged.
    later = iter(["fp_c"])
    session = B1App(data_dir=tmp_path / "other", live=True, create=lambda **request: mocked_reply(
        {"answer": "Not answerable", "cited_pages": [], "evidence": []}, fingerprint=next(later)))
    assert session.ask(pdf, "Third question?").identity_warning is None
    replayed = session.ask(pdf, "First question?")
    assert replayed.result.cache_hit and "cached reply" in replayed.identity_warning


def test_live_client_has_no_retries_and_a_timeout(tmp_path, monkeypatch):
    """A fake openai module records the client settings; no real client is built and nothing is sent."""
    built = []

    class FakeOpenAI:
        def __init__(self, **settings):
            built.append(settings)
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

        def create(self, **request):
            raise AssertionError("the test never sends a request")

    fake = ModuleType("openai")
    fake.OpenAI = FakeOpenAI
    monkeypatch.setitem(sys.modules, "openai", fake)
    monkeypatch.setenv("OPENAI_API_KEY", "test-not-a-key")
    app = B1App(data_dir=tmp_path, live=True)
    assert built == [{"max_retries": 0, "timeout": 120}] and app.create.__func__ is FakeOpenAI.create


def test_offline_mode_never_calls_a_supplied_create(tmp_path, pdf):
    api = RecordingAPI()
    answer = B1App(data_dir=tmp_path, create=api).ask(pdf, "How much did revenue grow?")
    assert api.requests == [] and answer.offline and answer.result.reply.answer == OfflineB1Reader.ANSWER


def test_live_run_log_records_each_attempt_before_sending(tmp_path, pdf):
    api = RecordingAPI(prompt=100_000, completion=800)  # usage above the bound: the excess is charged
    app = B1App(data_dir=tmp_path / "ok", live=True, create=api)
    answer = app.ask(pdf, "How much did revenue grow?")
    attempt, logged = read_jsonl(app.run_log_path)
    assert attempt["record"] == "attempt" and logged["record"] == "answer"
    assert attempt["request_fingerprint"] == logged["request_fingerprint"] and attempt["mode"] == logged["mode"] == "live"
    assert attempt["charged_usd"] == answer.result.cost_upper_usd
    assert answer.observed_usd == pytest.approx((100_000 * 0.10 + 800 * 0.50) / 1e6)
    assert answer.observed_usd > answer.result.cost_upper_usd
    assert app.spent_usd == answer.charged_usd == logged["charged_usd"] == answer.observed_usd

    def broken(**request):
        raise ConnectionError("reset")

    failing = B1App(data_dir=tmp_path / "failed", live=True, create=broken)
    with pytest.raises(ConnectionError):
        failing.ask(pdf, "How much did revenue grow?")
    records = read_jsonl(failing.run_log_path)
    assert [r["record"] for r in records] == ["attempt", "attempt_failed"]  # the paid attempt stays on record
    assert records[1]["charged_usd"] > 0 and "ConnectionError" in records[1]["error"]


def test_live_mode_needs_an_exported_key_and_k_is_bounded(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        B1App(data_dir=tmp_path, live=True)
    for bad in (0, 11, True, 2.5):
        with pytest.raises(ValueError, match="k must be"):
            B1App(data_dir=tmp_path, k=bad)
    with pytest.raises(ValueError, match="positive"):
        B1App(data_dir=tmp_path, session_ceiling_usd=0)


# --- command line -----------------------------------------------------------------------------------------


def test_cli_ask_and_index(tmp_path, pdf, capsys):
    data = str(tmp_path / "data")
    assert main(["--data-dir", data, "ask", str(pdf), "How much did revenue grow?"]) == 0
    captured = capsys.readouterr()
    assert "OFFLINE PLACEHOLDER" in captured.out and "Offline mode" in captured.err
    assert "Retriever: bm25 (fallback: RuntimeError: no visual index" in captured.out
    assert main(["--data-dir", data, "ask", str(pdf), "How much did revenue grow?", "--json"]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["offline_placeholder"] is True and printed["result"]["cache_hit"] is True
    assert main(["--data-dir", data, "index", str(pdf)]) == 2  # no encoder and no E5 cache requested
    assert "no encoder" in capsys.readouterr().err
    assert main(["--data-dir", data, "ask", str(pdf), "  "]) == 2


# --- regression: the application reproduces E8's B1 requests --------------------------------------------


def e8_b1_records(doc_ids):
    pd = pytest.importorskip("pandas")
    rankings = pd.read_parquet(REPO_ROOT / "experiments" / "frozen" / "e5" / "tables" / "rankings.parquet")
    visual = rankings[rankings["arm"] == "V"].set_index("qid")
    records = [record for record in read_jsonl(E8_RUN / "execution_log.jsonl")
               if record["arm"] == "L-B1" and record["replicate_id"] == "main_r1"
               and visual.loc[record["qid"], "doc_id"] in doc_ids]
    return records, visual


def test_application_rebuilds_the_frozen_e8_b1_requests_and_replays_their_replies(tmp_path):
    """PDF -> visual index (E5 embeddings) -> top 4 -> request: fingerprint, tokens and cost equal E8's L-B1 arm."""
    if not (E5_CACHE / "config.json").exists():
        pytest.skip("E5 embedding cache absent (git-ignored; notebook 04 writes it)")
    pdfs = {doc_id: MMLB_DOCUMENTS / doc_id for doc_id in PARITY_DOCUMENTS}
    if not all(path.is_file() and not getattr(path.stat(), "st_flags", 0) & SF_DATALESS for path in pdfs.values()):
        pytest.skip("parity PDFs absent or iCloud placeholders")
    records, visual = e8_b1_records(set(PARITY_DOCUMENTS))
    assert len(records) == 14

    frozen_by_fingerprint = {record["fingerprint"]: record for record in records}

    def replay_frozen(**request):
        record = frozen_by_fingerprint[profiled_request_fingerprint(request)]  # KeyError = a different request
        return mocked_reply(record["raw_response"], model=record["served_model"], fingerprint=record["system_fingerprint"],
                            prompt=record["prompt_tokens"], completion=record["completion_tokens"])

    app = B1App(data_dir=tmp_path / "data", live=True, create=replay_frozen)
    documents = {doc_id: app.open_document(path) for doc_id, path in pdfs.items()}
    for document in documents.values():
        app.build_visual_index(document, e5_cache_dir=E5_CACHE)
    for record in records:
        text = record["request"]["messages"][1]["content"][0]["text"]
        question = text.removeprefix("Question: ").removesuffix("\n\nPage images:")
        answer = app.ask(documents[visual.loc[record["qid"], "doc_id"]], question)
        result = answer.result
        assert result.retriever == "visual" and result.fallback_reason is None, record["qid"]
        assert result.supplied_pages == list(visual.loc[record["qid"], "pages"][:4]), record["qid"]
        assert result.request_fingerprint == record["fingerprint"], record["qid"]
        assert result.estimated_prompt_tokens == record["prompt_tokens"]
        assert result.cost_upper_usd == round(record["cost_upper_usd"], 9)
        parsed = record["parsed"]
        assert (result.reply.answer, result.reply.cited_pages) == (parsed["answer"], parsed["cited_pages"]), record["qid"]
        assert [(e.page, e.quote) for e in result.reply.evidence] == [(e["page"], e["quote"]) for e in parsed["evidence"]]
        assert result.citations.all_supplied  # E8: citation validity 1.000
        assert answer.identity_warning is None
    assert app.spent_usd == pytest.approx(sum(round(r["cost_upper_usd"], 9) for r in records))
