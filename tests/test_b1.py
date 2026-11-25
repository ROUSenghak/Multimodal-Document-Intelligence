"""B1 reader profile, grounding and bounded retrieve-read-verify policy."""

import csv
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pymupdf
import pytest

from conftest import MMLB_QUESTIONS, REPO_ROOT, read_jsonl
from visualdoc.answering import (
    JSON_OBJECT_FORMAT,
    LUNA_PROFILE,
    EvidenceQuote,
    ask_profiled,
    build_profiled_request,
    check_profiled_request,
    estimate_profiled_prompt_tokens,
    luna_image_tokens,
    parse_profiled_reply,
    build_request,
    request_fingerprint,
)
from visualdoc.citations import check_grounding, quote_match_score
from visualdoc.pipeline import Budget, JsonlReplyCache, answer_question_b1, append_run_log
from visualdoc.retrieval import CachedVisualIndex, maxsim_score


def blank_png(width, height):
    return pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, width, height), False).tobytes("png")


def completion(payload, *, model="gpt-6-luna", fingerprint=None, prompt=123, completion_tokens=17):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)), finish_reason="stop")],
        model=model,
        system_fingerprint=fingerprint,
        usage=SimpleNamespace(prompt_tokens=prompt, completion_tokens=completion_tokens),
    )


def test_frozen_s_v2_labels_are_complete_and_checksum_protected():
    folder = REPO_ROOT / "experiments" / "frozen" / "scoring_v2"
    entries = [line.split(maxsplit=1) for line in (folder / "SHA256SUMS").read_text().splitlines()]
    assert len(entries) == 4
    for expected, name in entries:
        assert hashlib.sha256((folder / name).read_bytes()).hexdigest() == expected
    pd = pytest.importorskip("pandas")
    labels = pd.read_csv(folder / "adjudication_labels.csv", dtype=str).fillna("")
    assert len(labels) == labels["item_id"].nunique() == 29
    assert labels["label"].value_counts().to_dict() == {"wrong": 21, "correct": 7, "unsure": 1}
    assert labels["identity_sha256"].str.fullmatch(r"[0-9a-f]{64}").all()


def test_e8_full_spec_pins_the_application_and_fail_closed_executor():
    spec = json.loads((REPO_ROOT / "experiments" / "specs" / "e8_reader_migration_v1.json").read_text())
    assert spec["offline_plan_regression"] == {
        "planned_calls": 354, "unique_conditions": 236, "prompt_tokens": 1_379_010,
        "maximum_output_tokens": 236_000, "list_price_upper_usd": 0.255901,
    }
    assert spec["execution"]["maximum_attempts"] == 360
    assert spec["execution"]["maximum_attempts_per_execution_index"] == 2
    assert spec["execution"]["cumulative_ceiling_usd"] == 0.50
    assert "served model or system fingerprint" in spec["execution"]["on_identity_change"]
    for module, expected in spec["application_module_sha256"].items():
        path = REPO_ROOT / "src" / Path(*module.split(".")).with_suffix(".py")
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected


def test_frozen_e8_execution_and_primary_verdict_are_complete():
    folder = REPO_ROOT / "experiments" / "frozen" / "e8"
    entries = [line.split(maxsplit=1) for line in (folder / "SHA256SUMS").read_text().splitlines()]
    assert len(entries) == 10
    for expected, name in entries:
        assert hashlib.sha256((folder / name).read_bytes()).hexdigest() == expected

    run = folder / "run_20261125T140433934010Z_4edb90e7_full"
    records = [json.loads(line) for line in (run / "execution_log.jsonl").read_text().splitlines()]
    assert len(records) == 354
    assert {record["status"] for record in records} == {"ok"}
    assert {record["attempt"] for record in records} == {1}
    assert len({record["execution_index"] for record in records}) == 354
    assert {arm: sum(record["arm"] == arm for record in records) for arm in ("L-v1", "L-B1", "L-B1r")} == {
        "L-v1": 118, "L-B1": 118, "L-B1r": 118,
    }
    assert {record["served_model"] for record in records} == {"gpt-6-luna"}
    assert {record["system_fingerprint"] for record in records} == {None}
    assert all(record["finish_reason"] == "stop" and record["parse_error"] is None for record in records)

    summary = json.loads((folder / "tables" / "evaluation_summary.json").read_text())
    assert {arm: int(summary["per_arm"][arm]["S-v1 correct / 102"]) for arm in ("L-v1", "L-B1", "L-B1r")} == {
        "L-v1": 42, "L-B1": 46, "L-B1r": 46,
    }
    assert summary["decision"]["stability flips / 102"] == 4
    assert summary["decision"]["promote B1 under frozen S-v1 rules"] is True
    assert summary["decision"]["S-v2 finalised"] is False
    queue = list(csv.DictReader((folder / "adjudication" / "blind_queue_unlabelled.csv").open()))
    assert len(queue) == len({row["item_id"] for row in queue}) == 16
    assert {row["label (correct / wrong / unsure)"] for row in queue} == {""}
    audit = json.loads((folder / "AUDIT.json").read_text())
    assert audit["passed"] and audit["checks_passed"] == audit["checks_total"] == 25


def test_measured_luna_profile_reproduces_all_six_smoke_prompt_totals():
    q45 = "According to author's definition on conscious incompetence, when can a sentence map to either [NA] or a list of sub-graph knowledge?"
    q6 = "How much did COSTCO spend on repurchasing of common stock in FY2021?Answer in millions.\n"
    portrait, landscape, paper = blank_png(768, 994), blank_png(1366, 768), blank_png(768, 1087)

    s1 = build_profiled_request(q45, [], contract="b1", allow_empty_pages=True)
    s2 = build_profiled_request(q45, [(1, portrait)], contract="b1")
    s3 = build_profiled_request(q45, [(1, landscape)], contract="b1")
    # S1--S3 isolated image-token accounting: B1 prompt with the old JSON-object envelope.
    for request in (s1, s2, s3):
        request["response_format"] = JSON_OBJECT_FORMAT
        request["max_completion_tokens"] = 400
    s4 = build_profiled_request(q45, [(2, paper), (5, paper), (8, paper)], contract="v1")
    s5 = build_profiled_request(q45, [(2, paper), (5, paper), (8, paper), (4, paper)], contract="b1")
    s6 = build_profiled_request(q6, [(29, portrait), (49, portrait), (39, portrait), (20, portrait)], contract="b1")
    observed = {
        label: estimate_profiled_prompt_tokens(request)
        for label, request in {"S1": s1, "S2": s2, "S3": s3, "S4": s4, "S5": s5, "S6": s6}.items()
    }
    assert observed == {"S1": 224, "S2": 1149, "S3": 1466, "S4": 3137, "S5": 4259, "S6": 4021}
    assert luna_image_tokens(768, 994) == 921 and luna_image_tokens(1366, 768) == 1238


def test_legacy_profile_rebuilds_all_118_frozen_e6_visual_requests():
    """Reader migration must not rewrite the matched GPT-4o-mini anchor."""
    pd = pytest.importorskip("pandas")
    manifest_path = REPO_ROOT / "data" / "processed" / "mmlongbench_doc" / "e5" / "render_manifest_heldout.csv"
    if not MMLB_QUESTIONS.is_file() or not manifest_path.is_file():
        pytest.skip("E5 render cache/questions absent: run notebooks 00 and 04")
    run = REPO_ROOT / "experiments" / "frozen" / "e6" / "run_20261123T200722253880Z_d94e85f1_full"
    records = [
        record for record in read_jsonl(run / "execution_log.jsonl")
        if record.get("replicate_id") == "main_r1" and record.get("arm") == "V" and record.get("status") == "ok"
    ]
    questions = pd.read_parquet(MMLB_QUESTIONS)
    manifest = pd.read_csv(manifest_path).set_index(["doc_id", "page"])
    assert len(records) == 118
    for record in records:
        question = questions.iloc[int(record["qid"].removeprefix("mmlb-"))]["question"]
        pages = [
            (page, (REPO_ROOT / manifest.loc[(record["doc_id"], page), "image_path"]).read_bytes())
            for page in record["supplied_pages"]
        ]
        assert request_fingerprint(build_request(question, pages)) == record["fingerprint"], record["qid"]


def test_b1_builder_and_parser_enforce_the_strict_contract():
    request = build_profiled_request("How much?", [(39, blank_png(40, 60))])
    assert request["model"] == "gpt-6-luna"
    assert request["reasoning_effort"] == "none" and request["temperature"] == 0
    assert request["response_format"]["json_schema"]["strict"] is True
    assert request["max_completion_tokens"] == 800

    raw = '{"answer":495,"cited_pages":[39],"evidence":[{"page":39,"quote":"Repurchases (495)"}]}'
    answer, cited, evidence, error = parse_profiled_reply(raw, "b1")
    assert (answer, cited, evidence, error) == (495, [39], [EvidenceQuote(39, "Repurchases (495)")], None)
    for malformed in (
        '{"answer":495,"cited_pages":[39]}',
        '{"answer":true,"cited_pages":[39],"evidence":[]}',
        '{"answer":"Not answerable","cited_pages":[39],"evidence":[]}',
    ):
        assert parse_profiled_reply(malformed, "b1")[3].startswith("unparseable")


def test_profiled_guard_prevents_a_call_and_records_alias_identity():
    request = build_profiled_request("Q?", [(1, blank_png(768, 994))])
    sent = []
    with pytest.raises(ValueError, match="per-request ceiling"):
        ask_profiled(lambda **kwargs: sent.append(kwargs), request, max_cost_usd=0.000001)
    assert sent == []

    reply = ask_profiled(
        lambda **kwargs: sent.append(kwargs) or completion(
            {"answer": "Not answerable", "cited_pages": [], "evidence": []}, fingerprint="fp_test"
        ),
        request,
        max_cost_usd=0.01,
    )
    assert sent == [request]
    assert (reply.served_model, reply.system_fingerprint, reply.prompt_tokens) == ("gpt-6-luna", "fp_test", 123)
    assert check_profiled_request(request, max_cost_usd=0.01)[0] == estimate_profiled_prompt_tokens(request)


def test_quote_and_numeric_grounding_have_positive_and_negative_controls():
    text = "Repurchases of common stock (1,358) — (23) — (472) (495) — (495)."
    exact = EvidenceQuote(39, "Repurchases of common stock (1,358) — (23) — (472) (495)")
    fuzzy = EvidenceQuote(39, "Repurchases of common stock (1,358) - (23) - (472) (495)")
    assert quote_match_score(exact.quote, text) == 1.0
    assert quote_match_score(fuzzy.quote, text) >= 0.9
    supported = check_grounding(495, [39], [fuzzy], {39: text})
    assert supported.ok and supported.numeric_support is True
    unsupported = check_grounding(496, [39], [EvidenceQuote(39, "unrelated passage")], {39: text})
    assert not unsupported.ok and unsupported.numeric_support is False
    assert not check_grounding("an answer", [], [], {39: text}).quotes_supported
    assert check_grounding("Not answerable", [], [], {39: text}).quotes_supported
    assert check_grounding(496, [39], [exact], {39: text}, derived_numbers=True).numeric_support is None


def test_cached_maxsim_ranking_uses_late_interaction_and_stable_ties():
    np = pytest.importorskip("numpy")
    query = np.array([[1.0, 0.0], [0.0, 1.0]])
    pages = {
        2: np.array([[0.8, 0.0], [0.0, 0.7]]),
        1: np.array([[1.0, 0.0], [0.0, 1.0]]),
    }
    assert maxsim_score(query, pages[1]) == pytest.approx(2.0)
    index = CachedVisualIndex(pages, lambda question: query)
    assert index.rank("find both") == [(1, pytest.approx(2.0)), (2, pytest.approx(1.5))]


def test_b1_policy_falls_back_traces_verifies_and_reuses_cache(tmp_path):
    pdf = tmp_path / "report.pdf"
    document = pymupdf.open()
    page = document.new_page(width=612, height=792)
    text = "Repurchases of common stock in fiscal 2021 were 495 million. " * 8
    page.insert_textbox((50, 50, 560, 700), text, fontsize=10)
    document.save(pdf)
    document.close()

    class UnavailableVisual:
        name = "visual"

        def rank(self, question):
            raise RuntimeError("weights are not available")

    calls = []

    def reader(**request):
        calls.append(request)
        return completion({
            "answer": 495,
            "cited_pages": [1],
            "evidence": [{"page": 1, "quote": "Repurchases of common stock in fiscal 2021 were 495 million."}],
        })

    cache_path = tmp_path / "runs" / "response_cache.jsonl"
    cache = JsonlReplyCache(cache_path)
    first = answer_question_b1(
        pdf, "How much was spent?", reader, primary_retriever=UnavailableVisual(), k=1,
        budget=Budget(max_calls=1, max_pages=1, max_usd=0.01), cache=cache,
    )
    # Reload from disk to prove reuse is not merely in-process memoization.
    second = answer_question_b1(
        pdf, "How much was spent?", reader, primary_retriever=UnavailableVisual(), k=1,
        budget=Budget(max_calls=1, max_pages=1, max_usd=0.01), cache=JsonlReplyCache(cache_path),
    )
    assert len(calls) == 1 and not first.cache_hit and second.cache_hit
    assert first.retriever == "bm25" and "weights are not available" in first.fallback_reason
    assert [step.action for step in first.trace] == ["retrieve", "read", "verify"]
    assert first.citations.ok and first.grounding.ok and first.grounding.numeric_support is True
    assert first.trace[1].usd > 0 and second.trace[1].usd == 0
    log_path = tmp_path / "runs" / "execution_log.jsonl"
    append_run_log(log_path, first)
    logged = json.loads(log_path.read_text())
    assert logged["request_fingerprint"] == first.request_fingerprint
    assert [step["action"] for step in logged["trace"]] == ["retrieve", "read", "verify"]

