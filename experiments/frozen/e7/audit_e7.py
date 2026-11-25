"""Independent audit of the frozen E7 package (experiments/frozen/e7).

Standalone: it neither imports nor executes notebook 06. It shares only the frozen scoring-rule cell f653d232 of
notebook 03, executed verbatim. Statistics, citation checks, the decision rule and the plan properties are
re-implemented here from the spec text. Usage: python -I audit_e7.py <repo root> <output AUDIT.json>
"""
import hashlib
import json
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from itertools import product
from math import comb, isclose
from pathlib import Path

import numpy as np
import pandas as pd

ROOT, OUT = Path(sys.argv[1]), Path(sys.argv[2])
FROZEN = ROOT / "experiments/frozen/e7"
SMOKE_ID, FULL_ID = "20261124T143927981959Z_9b46fcad_smoke", "20261124T160111456175Z_b3d0b5c0_full"
SMOKE, FULL = FROZEN / f"run_{SMOKE_ID}", FROZEN / f"run_{FULL_ID}"
SPEC_REL, NB06_REL = "experiments/specs/e7_extract_then_answer_v1.json", "notebooks/06_extract_then_answer.ipynb"
FREEZE_COMMIT, RUN_COMMIT = "f19ac27a9b5c1d8664c1e2ae0aabc7e657d6b122", "469aff55117349ead458eba6be1f9290edb99463"
SNAPSHOT = "gpt-4o-mini-2024-07-18"
checks, recomputed = {}, {}


def check(name, passed, detail=None):
    checks[name] = {"passed": bool(passed), **({"detail": detail} if detail is not None else {})}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def git_show(commit, rel):
    out = subprocess.run(["git", "show", f"{commit}:{rel}"], cwd=ROOT, capture_output=True)
    return out.stdout if out.returncode == 0 else None


# ---------------------------------------------------------------- A. package integrity
for run_id, frozen_dir in ((SMOKE_ID, SMOKE), (FULL_ID, FULL)):
    original = ROOT / "experiments/runs/e7" / run_id
    names = sorted(p.name for p in original.iterdir())
    same = names == sorted(p.name for p in frozen_dir.iterdir()) and all((original / n).read_bytes() == (frozen_dir / n).read_bytes() for n in names)
    check(f"frozen copy of {run_id} is byte-identical to experiments/runs/e7 ({len(names)} files)", same)
eval_dir = ROOT / "data/processed/mmlongbench_doc/e7" / f"evaluation_{FULL_ID}"
check("tables/ equal notebook 06's evaluation outputs (evaluation_summary.json, per_question.csv)",
      all((eval_dir / n).read_bytes() == (FROZEN / "tables" / n).read_bytes() for n in ("evaluation_summary.json", "per_question.csv")))
post = ROOT / "data/processed/mmlongbench_doc/e7/post_run_analysis"
check("analysis/ and design/ equal their sources (report, literature review, E6 audit labels)",
      all((post / n).read_bytes() == (FROZEN / "analysis" / n).read_bytes() for n in ("E7_report_and_next_stage.md", "literature_review.md"))
      and all((ROOT / "data/processed/mmlongbench_doc/e7" / n).read_bytes() == (FROZEN / "design" / n).read_bytes()
              for n in ("e6_error_audit.csv", "e6_unanswerable_audit.csv")))

# ---------------------------------------------------------------- B. specification and code
spec_bytes = (ROOT / SPEC_REL).read_bytes()
spec = json.loads(spec_bytes)
spec_sha = sha(spec_bytes)
settings = {r: json.loads((d / "settings.json").read_text()) for r, d in ((SMOKE_ID, SMOKE), (FULL_ID, FULL))}
check("spec snapshot (both runs) = tracked spec = spec at the freeze commit and at the run commit = settings hash",
      all((d / "spec_snapshot.json").read_bytes() == spec_bytes for d in (SMOKE, FULL))
      and git_show(FREEZE_COMMIT, SPEC_REL) == spec_bytes == git_show(RUN_COMMIT, SPEC_REL)
      and all(s["spec_sha256"] == spec_sha for s in settings.values()), spec_sha)
check("spec frozen before live execution with the approved USD 9.00 cumulative ceiling",
      spec["status"] == "frozen-before-live-execution" and spec["frozen_at"] == "2026-11-24T13:35:17Z" and spec["budget"]["approved_ceiling_usd"] == 9.0)


def notebook_code_sha256(nb):
    return sha(json.dumps(["".join(c["source"]) if isinstance(c["source"], list) else c["source"] for c in nb["cells"] if c["cell_type"] == "code"]).encode())


run_code_hash = notebook_code_sha256(json.loads(git_show(RUN_COMMIT, NB06_REL)))
sessions = [json.loads(p.read_text()) for d in (SMOKE, FULL) for p in sorted(d.glob("session_*.json"))]
check("every session record names the run commit, a clean tree, unchanged protected paths and the committed spec and code",
      len(sessions) == 2 and all(s["code_provenance"]["git_commit"] == RUN_COMMIT and s["code_provenance"]["git_status"] == []
                                 and s["code_provenance"]["protected_paths_unchanged"] and s["code_provenance"]["spec_committed"]
                                 and s["code_provenance"]["notebook06_code_committed"] for s in sessions))
check("notebook 06's code hash at the run commit, recomputed, equals the recorded hash",
      all(s["code_provenance"]["notebook06_code_sha256"] == run_code_hash for s in sessions) and settings[FULL_ID]["code_provenance"]["notebook06_code_sha256"] == run_code_hash,
      run_code_hash)
commit_time = lambda c: datetime.fromisoformat(subprocess.run(["git", "show", "-s", "--format=%cI", c], cwd=ROOT, capture_output=True, text=True).stdout.strip())
logs = {SMOKE_ID: jsonl(SMOKE / "execution_log.jsonl"), FULL_ID: jsonl(FULL / "execution_log.jsonl")}
first_request = min(datetime.fromisoformat(r["request_started_at"]) for r in logs[SMOKE_ID] if r["request_started_at"])
check("freeze and run commits precede the first request", commit_time(FREEZE_COMMIT) < commit_time(RUN_COMMIT) < first_request,
      f"{commit_time(RUN_COMMIT).isoformat()} < {first_request.isoformat()}")

# ---------------------------------------------------------------- C. population and plan
questions = pd.read_parquet(ROOT / "data/processed/mmlongbench_doc/questions.parquet").set_index("qid")
e6_spec = json.loads((ROOT / "experiments/specs/e6_visual_retrieval_answering_v1.json").read_text())
pop = questions[questions["doc_id"].isin(e6_spec["population"]["documents"])]
QIDS = sorted(pop.index)
ANS = [q for q in QIDS if pop.loc[q, "answerable"]]
UNANS = [q for q in QIDS if not pop.loc[q, "answerable"]]
EVID = [q for q in ANS if len(pop.loc[q, "evidence_pages"]) > 0]
check("population: 14 documents, 118 questions = 102 answerable + 16 unanswerable; 101 evidence questions + mmlb-0599",
      pop["doc_id"].nunique() == 14 and len(QIDS) == 118 and len(ANS) == 102 and len(UNANS) == 16 and len(EVID) == 101
      and sorted(set(ANS) - set(EVID)) == ["mmlb-0599"] and set(settings[FULL_ID]["qids"]) == set(QIDS))

plan = json.loads((FULL / "execution_plan.json").read_text())
main = [i for i in plan if i["replicate_id"] == "main_r1"]
blocks = {}
for item in main:
    blocks.setdefault(item["block_index"], []).append(item)
smoke_items = [i for i in plan if i["replicate_id"] == "technical_smoke"]
block_ok = all(len(b) == 11 and len({i["qid"] for i in b}) == 1 and Counter(i["kind"] for i in b) == Counter({"v0": 1, "extract": 8, "reason": 2})
               and [i["execution_index"] for i in b] == list(range(b[0]["execution_index"], b[0]["execution_index"] + 11)) for b in blocks.values())
check("full plan: 1,309 calls = the 11-call smoke block + 118 contiguous blocks (1 V0, 8 extractions, 2 reasoning calls); indices 1..1309",
      len(plan) == 1309 and len(smoke_items) == 11 and {i["qid"] for i in smoke_items} == {"mmlb-0068"} and len(blocks) == 118 and block_ok
      and sorted({b[0]["qid"] for b in blocks.values()}) == QIDS and [i["execution_index"] for i in plan] == list(range(1, 1310)))
v0_first = sum(b[0]["kind"] == "v0" for b in blocks.values())
x4_first = sum([i["arm"] for i in b if i["kind"] == "reason"] == ["X4", "X8"] for b in blocks.values())
check("counterbalancing: V0 opens exactly 59 of 118 blocks; X4's reasoning call precedes X8's in exactly 59", v0_first == 59 and x4_first == 59,
      {"V0 first": v0_first, "X4 first": x4_first})

rankings = pd.read_parquet(ROOT / "experiments/frozen/e5/tables/rankings.parquet")
top8 = {r.qid: [int(p) for p in r.pages[:8]] for r in rankings[(rankings["arm"] == "V") & (rankings["population"] == "held-out")].itertuples()}
e6_log = jsonl(ROOT / "experiments/frozen/e6/run_20261123T200722253880Z_d94e85f1_full/execution_log.jsonl")
e6_v = {}
for r in e6_log:
    if r["replicate_id"] == "main_r1" and r["arm"] == "V" and r["status"] == "ok":
        e6_v[r["qid"]] = r
extract_pages = {b[0]["qid"]: [i["page"] for i in b if i["kind"] == "extract"] for b in blocks.values()}
check("extraction pages of every question = ColQwen2 top 8 of the frozen E5 rankings (as a set; extraction order is the plan's)",
      all(set(extract_pages[q]) == set(top8[q]) and len(extract_pages[q]) == 8 for q in QIDS))

final = {}
for r in logs[FULL_ID]:
    final[r["execution_index"]] = r
final = [final[i] for i in sorted(final)]
fmain = [r for r in final if r["replicate_id"] == "main_r1"]
v0 = {r["qid"]: r for r in fmain if r["kind"] == "v0"}
ext = {(r["qid"], r["page"]): r for r in fmain if r["kind"] == "extract"}
rea = {(r["qid"], r["arm"]): r for r in fmain if r["kind"] == "reason"}
arm_pages = {"V0": {q: v0[q]["supplied_pages"] for q in QIDS}, "X4": {q: rea[(q, "X4")]["supplied_pages"] for q in QIDS},
             "X8": {q: rea[(q, "X8")]["supplied_pages"] for q in QIDS}}
check("V0 = the frozen E6 V request on 118/118 (fingerprint and supplied pages); X4 pages = V0 pages; X8 pages = ColQwen2 top 8 in rank order",
      all(v0[q]["fingerprint"] == e6_v[q]["fingerprint"] and v0[q]["supplied_pages"] == e6_v[q]["supplied_pages"] for q in QIDS)
      and all(arm_pages["X4"][q] == arm_pages["V0"][q] for q in QIDS) and all(arm_pages["X8"][q] == top8[q] for q in QIDS))
smoke_v0 = [r for r in logs[SMOKE_ID] if r["kind"] == "v0"][0]
check("the smoke V0 request (mmlb-0068) equals the frozen E6 V request", smoke_v0["fingerprint"] == e6_v["mmlb-0068"]["fingerprint"])

# ---------------------------------------------------------------- D. log accounting
check("one final log record per planned call, in plan order, with matching question, kind, arm and page",
      len(final) == 1309 and all((r["execution_index"], r["qid"], r["kind"], r["arm"], r["page"]) == (i["execution_index"], i["qid"], i["kind"], i["arm"], i["page"])
                                 for r, i in zip(final, plan)) and len(logs[FULL_ID]) == 1309)
check("every call answered on its first attempt; no rate limit, API error, block or budget stop in either run",
      all(r["attempt"] == 1 and r["status"] in {"ok", "parse_error"} and r["source"] == "live" for log in logs.values() for r in log))
status = Counter((r["kind"], r["status"]) for r in final)
check("statuses: 1,299 ok; the 10 parse errors are all extractions (unreadable pages, scored by the frozen design)",
      sum(n for (k, s), n in status.items() if s == "ok") == 1299 and {(k, s): n for (k, s), n in status.items() if s == "parse_error"} == {("extract", "parse_error"): 10},
      {f"{k}/{s}": n for (k, s), n in status.items()})
check("served model = the pinned snapshot, sent fingerprint = planned fingerprint, integrity valid, on every call of both runs",
      all(r["served_model"] == SNAPSHOT and r["sent_fingerprint"] == r["fingerprint"] and r["integrity_valid"] and r["request_content_verified"]
          for log in logs.values() for r in log))
backends = Counter((("image" if r["kind"] in ("v0", "extract") else "text"), r["system_fingerprint"]) for log in logs.values() for r in log)
check("backends (recorded limitation): every image call on fp_022a442bda, every text-only reasoning call on fp_9400314673",
      set(backends) == {("image", "fp_022a442bda"), ("text", "fp_9400314673")}, {f"{a} {b}": n for (a, b), n in backends.items()})
diffs = Counter(r["prompt_tokens"] - r["expected_prompt_tokens"] for r in final)
check("billed prompt tokens - expected: +1 on 1,071 calls, +2 on 238 (the reasoning calls)", diffs == Counter({1: 1071, 2: 238})
      and all(r["prompt_tokens"] - r["expected_prompt_tokens"] == 2 for r in final if r["kind"] == "reason"), dict(diffs))

# ---------------------------------------------------------------- E. cache and predictions
cache_ok = True
for run_id, d in ((SMOKE_ID, SMOKE), (FULL_ID, FULL)):
    cache = jsonl(d / "response_cache.jsonl")
    keys = [e["cache_key"] for e in cache]
    live = [r for r in logs[run_id] if r["source"] == "live"]
    cache_ok &= len(keys) == len(set(keys)) == len(live) and set(keys) == {r["cache_provenance"]["cache_key"] for r in live}
    cache_ok &= all(r["cache_provenance"]["namespace"] == f"{run_id}:{r['replicate_id']}" for r in logs[run_id])
    # spec: cache key = SHA-256(run_id:replicate_id:request fingerprint)
    cache_ok &= all(r["cache_provenance"]["cache_key"] == sha(f"{run_id}:{r['replicate_id']}:{r['fingerprint']}".encode()) for r in logs[run_id])
check("caches: one entry per live call, keys unique and equal to the log's, namespaces run- and replicate-scoped", cache_ok)
pred_ok = True
for run_id, d, rep in ((SMOKE_ID, SMOKE, "technical_smoke"), (FULL_ID, FULL, "main_r1"), (FULL_ID, FULL, "technical_smoke")):
    recs = {(r["qid"], r["arm"]): r for r in logs[run_id] if r["replicate_id"] == rep and r["kind"] in ("v0", "reason")}
    for arm in ("V0", "X4", "X8"):
        preds = jsonl(d / f"predictions_{rep}_{arm}.jsonl")
        pred_ok &= all(p["pred"] == recs[(p["qid"], arm)]["pred"] and p["cited_pages"] == recs[(p["qid"], arm)]["cited_pages"] for p in preds)
        pred_ok &= len(preds) == (118 if rep == "main_r1" else 1)
check("prediction files (V0, X4, X8; main and smoke) equal the log's final answers and cited pages", pred_ok)
main_keys = {r["cache_provenance"]["cache_key"] for r in fmain if r["kind"] == "extract"}
memory_ok = all([p["page"] for p in rea[(q, a)]["memory"]["pages"]] == arm_pages[a][q] and set(rea[(q, a)]["extraction_cache_keys"]) <= main_keys
                for q in QIDS for a in ("X4", "X8"))
memory_ok &= all(set(rea[(q, "X4")]["extraction_cache_keys"]) <= set(rea[(q, "X8")]["extraction_cache_keys"]) for q in QIDS)
check("each reasoning memory lists the arm's pages in rank order and is built from this run's extractions; X4 reuses X8's", memory_ok)
readings = sum(len(arm_pages[a][q]) for a in ("X4", "X8") for q in QIDS)
check("944 paid extraction calls serve 1,403 page readings (cache reuse)", len(ext) == 944 and readings == 1403, {"extractions": len(ext), "readings": readings})

# ---------------------------------------------------------------- F. costs
price_in, price_out = spec["model"]["input_usd_per_1m_tokens"] / 1e6, spec["model"]["output_usd_per_1m_tokens"] / 1e6
cost = {run_id: sum(r["prompt_tokens"] * price_in + r["completion_tokens"] * price_out for r in log if r["source"] == "live") for run_id, log in logs.items()}
completions = {run_id: json.loads((d / "completion.json").read_text()) for run_id, d in ((SMOKE_ID, SMOKE), (FULL_ID, FULL))}
main_cost = sum(r["prompt_tokens"] * price_in + r["completion_tokens"] * price_out for r in fmain)
summary = json.loads((FROZEN / "tables/evaluation_summary.json").read_text())
check("list-price cost recomputed from billed tokens: smoke $0.063019, full $5.848038, cumulative $5.911057 <= $9.00; main replicate $5.7849",
      round(cost[SMOKE_ID], 6) == 0.063019 and round(cost[FULL_ID], 6) == completions[FULL_ID]["list_price_cost_usd"] == 5.848038
      and round(cost[SMOKE_ID] + cost[FULL_ID], 6) == completions[FULL_ID]["cumulative_list_price_cost_usd"] == 5.911057
      and isclose(main_cost, summary["experiment_list_price_usd"], abs_tol=1e-9), {"smoke": cost[SMOKE_ID], "full": cost[FULL_ID], "main_r1": main_cost})

# ---------------------------------------------------------------- G. results, re-derived
nb03 = json.loads((ROOT / "notebooks/03_evaluation.ipynb").read_text())
scorer_src = next("".join(c["source"]) for c in nb03["cells"] if c.get("id") == "f653d232")
namespace = {}
exec("import ast, re\nfrom math import isclose\n" + scorer_src, namespace)
eval_score = namespace["eval_score"]
e6v_preds = {r["qid"]: r for r in jsonl(ROOT / "experiments/frozen/e6/run_20261123T200722253880Z_d94e85f1_full/predictions_main_r1_V.jsonl")}
e6_correct = {q: eval_score(questions.loc[q, "answer"], e6v_preds[q]["pred"], questions.loc[q, "answer_format"]) > 0 for q in ANS}
check("the frozen scorer cell f653d232, executed verbatim, reproduces frozen E6 V: 38/102", sum(e6_correct.values()) == 38)

NA = "Not answerable"
preds = {"V0": {q: v0[q] for q in QIDS}, "X4": {q: rea[(q, "X4")] for q in QIDS}, "X8": {q: rea[(q, "X8")] for q in QIDS}}
score = {a: {q: (eval_score(questions.loc[q, "answer"], preds[a][q]["pred"], questions.loc[q, "answer_format"]) if preds[a][q]["status"] in ("ok", "parse_error") else 0.0)
             for q in QIDS} for a in preds}
correct = {a: {q: score[a][q] > 0 for q in QIDS} for a in preds}
acc = {a: sum(correct[a][q] for q in ANS) for a in preds}
recomputed["accuracy_102"] = acc
check("accuracy on the 102 answerable questions (score > 0): V0 38, X4 31, X8 29", acc == {"V0": 38, "X4": 31, "X8": 29}, acc)


def fixed_broken(a, b, scores=correct):
    return ([q for q in ANS if not scores[a][q] and scores[b][q]], [q for q in ANS if scores[a][q] and not scores[b][q]])


fx, br = fixed_broken("V0", "X4")
check("X4 vs V0: 3 fixed, 10 broken, the same questions as the frozen summary", (fx, br) == (summary["fixed"], summary["broken"]) and (len(fx), len(br)) == (3, 10),
      {"fixed": fx, "broken": br})

docs = np.array([pop.loc[q, "doc_id"] for q in ANS])
order = sorted(set(docs))


def compare(before, after, seed=spec["execution"]["seeds"]["bootstrap"], draws=10_000):
    b = np.array([float(before[q]) for q in ANS]); a = np.array([float(after[q]) for q in ANS]); d = a - b
    sums = np.array([d[docs == x].sum() for x in order]); counts = np.array([(docs == x).sum() for x in order])
    picks = np.random.default_rng(seed).integers(0, len(order), size=(draws, len(order)))  # 14 documents drawn with replacement
    boot = sums[picks].sum(axis=1) / counts[picks].sum(axis=1)
    signs = np.array(list(product([1.0, -1.0], repeat=len(order))))
    null = signs @ sums
    nf, nb = int(((b == 0) & (a > 0)).sum()), int(((b > 0) & (a == 0)).sum())
    n = nf + nb
    return {"delta": float(d.mean()), "fixed": nf, "broken": nb, "bootstrap_p05": float(np.percentile(boot, 5)),
            "ci95": [float(x) for x in np.percentile(boot, [2.5, 97.5])],
            "sign_flip_p_one_sided": float(np.mean(null >= sums.sum() - 1e-9)), "sign_flip_p_two_sided": float(np.mean(np.abs(null) >= abs(sums.sum()) - 1e-9)),
            "mcnemar": 1.0 if n == 0 else min(1.0, 2 * sum(comb(n, i) for i in range(min(nf, nb) + 1)) / 2 ** n),
            "document_weighted_delta": float(np.mean([d[docs == x].mean() for x in order])),
            "lodo_range": [float(min(d[docs != x].mean() for x in order)), float(max(d[docs != x].mean() for x in order))]}


prim = compare(correct["V0"], correct["X4"])
recomputed["X4_minus_V0"] = prim
fz = summary["primary_X4_minus_V0"]
lodo = list(fz["leave_one_document_out"].values())
check("X4 - V0 statistics re-implemented from the spec text equal the frozen summary (delta, bootstrap p05 and CI, sign-flip, McNemar, document-weighted, LODO)",
      isclose(prim["delta"], fz["delta"]) and isclose(prim["bootstrap_p05"], fz["bootstrap_p05"]) and np.allclose(prim["ci95"], fz["ci95"])
      and isclose(prim["sign_flip_p_one_sided"], fz["sign_flip_p_one_sided"]) and isclose(prim["sign_flip_p_two_sided"], fz["sign_flip_p_two_sided"])
      and isclose(prim["mcnemar"], fz["mcnemar_p_ignores_clustering"]) and isclose(prim["document_weighted_delta"], fz["document_weighted_delta"])
      and np.allclose(prim["lodo_range"], [min(lodo), max(lodo)]),
      {k: prim[k] for k in ("delta", "ci95", "sign_flip_p_one_sided")})
pages = compare(correct["X4"], correct["X8"]); total = compare(correct["V0"], correct["X8"])
recomputed["X8_minus_X4"], recomputed["X8_minus_V0"] = pages, total
check("X8 - X4 = -0.020 (2 fixed / 4 broken) and X8 - V0 = -0.088 (4 / 13) equal the frozen summary",
      isclose(pages["delta"], summary["additional_pages_X8_minus_X4"]["delta"]) and (pages["fixed"], pages["broken"]) == (2, 4)
      and isclose(total["delta"], summary["total_X8_minus_V0"]["delta"]) and (total["fixed"], total["broken"]) == (4, 13))


def citation(pred, cited, supplied):
    cited = list(dict.fromkeys(cited)); abstained = pred == NA
    invalid = [p for p in cited if p not in set(supplied)]
    return {"abstained": abstained, "ok": not invalid and not (not abstained and not cited)}


cit = {a: {q: citation(preds[a][q]["pred"], preds[a][q]["cited_pages"], arm_pages[a][q]) for q in QIDS} for a in preds}
abst = {a: sum(cit[a][q]["abstained"] for q in UNANS) for a in preds}
unans_correct = {a: sum(correct[a][q] for q in UNANS) for a in preds}
validity = {a: sum(cit[a][q]["ok"] for q in QIDS) / 118 for a in preds}
recomputed.update(correct_abstentions_16=abst, citation_validity_118=validity)
check("correct abstentions (16): V0 7, X4 9, X8 8, equal to the scorer's unanswerable credit and to the frozen summary",
      abst == {"V0": 7, "X4": 9, "X8": 8} == summary["abstentions"] and abst == unans_correct)
check("citation validity (118; every cited page supplied and no answer without a citation): 0.932, 0.992, 0.983, equal to the frozen summary",
      all(isclose(validity[a], summary["citation_validity"][a]) for a in preds), {a: round(v, 4) for a, v in validity.items()})


def decide(c, g1, g2):
    if not (g1 and g2):
        return "regression"
    if c["delta"] <= -0.05:
        return "regression"
    if c["delta"] < 0.05:
        return "no_meaningful_gain"
    if c["broken"] > c["fixed"] / 2:
        return "regression"
    return "strong_support" if c["bootstrap_p05"] > 0 and c["sign_flip_p_one_sided"] <= 0.05 else "promising_but_uncertain"


g = lambda a, b: (abst[b] >= abst[a] - 2, validity[b] - validity[a] >= -0.05)
verdicts = {"X4 - V0": decide(prim, *g("V0", "X4")), "X8 - X4": decide(pages, *g("X4", "X8"))}
check("decision rule re-applied from the spec text: X4 - V0 regression (delta <= -0.05; guardrails hold); X8 - X4 no_meaningful_gain",
      verdicts == {"X4 - V0": "regression", "X8 - X4": "no_meaningful_gain"} == {"X4 - V0": summary["decision"]["verdict"], "X8 - X4": summary["additional_pages_X8_minus_X4"]["decision"]["verdict"]}
      and all(g("V0", "X4")), verdicts)
noise_fx, noise_br = [q for q in ANS if not e6_correct[q] and correct["V0"][q]], [q for q in ANS if e6_correct[q] and not correct["V0"][q]]
check("session noise: frozen E6 V 38 -> live V0 38, 2 fixed / 2 broken", (sum(e6_correct.values()), acc["V0"], len(noise_fx), len(noise_br)) == (38, 38, 2, 2)
      and (summary["session_noise_frozen_E6_V_vs_V0"]["fixed"], summary["session_noise_frozen_E6_V_vs_V0"]["broken"]) == (2, 2), {"fixed": noise_fx, "broken": noise_br})
strict = {a: {q: score[a][q] >= 1 for q in QIDS} for a in preds}
sfx, sbr = fixed_broken("V0", "X4", strict)
corrected = {a: dict(correct[a]) for a in preds}
corrected["V0"]["mmlb-0998"], corrected["X4"]["mmlb-0998"] = False, True
cfx, cbr = fixed_broken("V0", "X4", corrected)
recomputed["sensitivity"] = {"strict": (len(sfx) - len(sbr)) / 102, "strict_fixed_broken": [len(sfx), len(sbr)], "0998_corrected": (len(cfx) - len(cbr)) / 102}
check("scoring sensitivity (descriptive): strict scoring gives -0.049 (4 / 9); correcting mmlb-0998 gives -0.049 (4 / 9)",
      (len(sfx), len(sbr)) == (4, 9) and (len(cfx), len(cbr)) == (4, 9))
table = pd.read_csv(FROZEN / "tables/per_question.csv")
check("tables/per_question.csv: score and correctness of all 354 rows equal the re-derived values",
      len(table) == 354 and all(isclose(r.score, score[r.arm][r.qid], abs_tol=1e-12) and bool(r.correct) == correct[r.arm][r.qid] for r in table.itertuples()))

# ---------------------------------------------------------------- H. hygiene
qtexts = [t for t in pop["question"] if len(t) > 25]
secret = re.compile(r"sk-[A-Za-z0-9_\-]{12,}")
b64 = re.compile(r"[A-Za-z0-9+/]{400,}")
annotation_keys = {"evidence_pages", "evidence_sources", "answer_format", "answerable", "reference", "answer"}
hygiene = []
for d in (SMOKE, FULL):
    for f in d.iterdir():
        text = f.read_text()
        if any(t in text for t in qtexts) or secret.search(text) or b64.search(text):
            hygiene.append(f.name)
log_keys = {k for log in logs.values() for r in log for k in r}
check("no question text, credential-like string or Base64 payload in any frozen run file; no annotation field in any log record",
      not hygiene and not (log_keys & annotation_keys), hygiene or None)

passed = sum(c["passed"] for c in checks.values())
OUT.write_text(json.dumps({
    "audit": "independent E7 audit", "run_ids": [SMOKE_ID, FULL_ID], "audited_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    "method": "standalone script outside the notebooks; it neither imports nor executes notebook 06. It reads the frozen run files, the tracked specs, "
              "the frozen E5 rankings and E6 run, git objects at the freeze and run commits, and the reference answers in questions.parquet (evaluation only). "
              "Plan properties, citation checks, cost, statistics (cluster bootstrap, exact sign-flip, McNemar, LODO) and the decision rule are re-implemented from the spec text.",
    "shared_with_notebooks": "only the frozen scoring-rule cell f653d232 of notebook 03 (eval_score and helpers), executed verbatim",
    "freeze_commit": FREEZE_COMMIT, "run_commit": RUN_COMMIT, "passed": passed, "total": len(checks), "checks": checks, "recomputed": recomputed,
}, indent=1, default=str))
print(f"{passed}/{len(checks)} checks passed")
for name, c in checks.items():
    if not c["passed"]:
        print("FAILED:", name, c.get("detail"))
