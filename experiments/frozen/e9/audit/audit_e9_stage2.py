"""Independent, read-only audit of E9 Stage 2 (adaptive evidence acquisition).

Usage:  python audit_e9_stage2.py [REPO_ROOT] [OUT_DIR]
REPO_ROOT defaults to the current working directory; OUT_DIR defaults to this script's directory.

The script never calls an API, never writes inside the repository, imports nothing from notebook 08,
and writes no question, answer or reply text: only identifiers, counts, hashes and page numbers.
The questions table is filtered to the 118 run qids immediately after it is read.
"""
import ast
import contextlib
import hashlib
import io
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime
from itertools import product
from math import ceil, floor, isclose
from pathlib import Path

import numpy as np
import pandas as pd
import tiktoken

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
OUT = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else Path(__file__).resolve().parent
assert (ROOT / "AGENTS.md").is_file() and (ROOT / "notebooks").is_dir(), "pass the repository root"

FROZEN = ROOT / "experiments" / "frozen"
RUN = ROOT / "experiments" / "runs" / "e9" / "20261125T171152006205Z_57d16dea_full"
SMOKE = ROOT / "experiments" / "runs" / "e9_smoke" / "20261125T171115088784Z_8a4e2bb5_smoke"
E8_RUN = FROZEN / "e8" / "run_20261125T140433934010Z_4edb90e7_full"
SPEC_PATH = ROOT / "experiments" / "specs" / "e9_adaptive_evidence_v1.json"
ADD_PATH = ROOT / "experiments" / "specs" / "e9_adaptive_evidence_v1_addendum.json"
E9_OUT = ROOT / "data" / "processed" / "mmlongbench_doc" / "e9"
NA = "Not answerable"
PRICE_IN, PRICE_CACHED, PRICE_OUT = 0.10 / 1e6, 0.01 / 1e6, 0.50 / 1e6

CHECKS = []
FACTS = {}


def check(name, passed, **details):
    CHECKS.append({"name": name, "passed": bool(passed), "details": details})
    print(f"[{'PASS' if passed else 'FAIL'}] {name}: {json.dumps(details, default=str)[:400]}")


def sha(b):
    return hashlib.sha256(b).hexdigest()


def jl(path):
    return [json.loads(x) for x in Path(path).read_text().splitlines() if x.strip()]


def verify_sums(pkg):
    lines = [x for x in (pkg / "SHA256SUMS").read_text().splitlines() if x.strip()]
    bad = [rel for h, rel in (x.split(None, 1) for x in lines) if sha((pkg / rel.strip()).read_bytes()) != h]
    return len(lines), bad


def git_show(commit, rel):
    return subprocess.run(["git", "show", f"{commit}:{rel}"], cwd=ROOT, capture_output=True, check=True).stdout


# ---------------------------------------------------------------- 0. frozen inputs
for pkg in ("e5", "e8", "e9_stage0", "scoring_v2", "e8_scoring_v2"):
    n, bad = verify_sums(FROZEN / pkg)
    check(f"frozen package {pkg} matches SHA256SUMS", not bad and n > 0, files=n, mismatched=bad)

spec_bytes, add_bytes = SPEC_PATH.read_bytes(), ADD_PATH.read_bytes()
settings = json.loads((RUN / "settings.json").read_text())
ADD = json.loads(add_bytes)
check("spec byte-identical to freeze commit 7f41eea and hash in settings/addendum",
      spec_bytes == git_show("7f41eea", "experiments/specs/e9_adaptive_evidence_v1.json")
      and sha(spec_bytes) == settings["spec_sha256"] == ADD["spec"]["sha256"], spec_sha256=sha(spec_bytes))
check("addendum byte-identical to commit a30bb29 and hash in settings",
      add_bytes == git_show("a30bb29", "experiments/specs/e9_adaptive_evidence_v1_addendum.json")
      and sha(add_bytes) == settings["addendum_sha256"], addendum_sha256=sha(add_bytes), run_git_commit=settings["git_commit"])
commit_time = subprocess.run(["git", "show", "-s", "--format=%cI", "a30bb29"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
smoke_log = jl(SMOKE / "execution_log.jsonl")
first_call = smoke_log[0]["started_at"]
check("addendum committed before the first paid call",
      datetime.fromisoformat(commit_time) < datetime.fromisoformat(first_call), addendum_commit=commit_time, first_smoke_call=first_call)

# ---------------------------------------------------------------- 1. population, rankings, trigger
rk = pd.read_parquet(FROZEN / "e5" / "tables" / "rankings.parquet")
V = rk[(rk["arm"] == "V") & (rk["population"] == "held-out")].set_index("qid")
QIDS = sorted(V.index)
assert len(QIDS) == 118
stage0 = pd.read_csv(FROZEN / "e9_stage0" / "tables" / "stage0_per_question.csv").set_index("qid")
u3 = {q: -(float(V.at[q, "scores"][0]) - float(V.at[q, "scores"][7])) / float(V.at[q, "scores"][0]) for q in QIDS}
thr = float(np.quantile(np.array([u3[q] for q in QIDS]), 0.60))
trig_recomputed = {q for q in QIDS if u3[q] >= thr}
trig_csv = set(stage0.index[stage0["trigger_U3_flatness_18"].astype(bool)])
check("U3 trigger recomputed from frozen E5 V scores = frozen Stage 0 column = addendum list",
      trig_recomputed == trig_csv == set(ADD["stage0"]["triggered_questions"]) and round(thr, 6) == ADD["stage0"]["threshold"],
      threshold=round(thr, 6), triggered=len(trig_csv))
TRIG = trig_csv

qs = pd.read_parquet(ROOT / "data" / "processed" / "mmlongbench_doc" / "questions.parquet")
qs = qs[qs["qid"].isin(set(QIDS))].set_index("qid").copy()  # filtered immediately: no test-pool row is used
assert len(qs) == 118
qs["evidence_pages"] = qs["evidence_pages"].map(lambda p: [int(x) for x in p])
assert (qs["doc_id"] == V.loc[qs.index, "doc_id"]).all()
ANS = qs["answerable"].astype(bool)
assert ((qs["answer_format"] == "None") == ~ANS).all()
FACTS["population"] = {"questions": 118, "answerable": int(ANS.sum()), "documents": int(qs["doc_id"].nunique()),
                       "triggered": len(TRIG), "triggered_answerable": int(ANS[list(TRIG)].sum())}

# ---------------------------------------------------------------- 2. plan, log integrity
plan = settings["plan"]
plan_sha = sha(json.dumps(plan, sort_keys=True).encode())
plan_prompt = sum(p["prompt_tokens"] for p in plan)
plan_out = sum(p["max_completion_tokens"] for p in plan)
plan_upper = round(plan_prompt * PRICE_IN + plan_out * PRICE_OUT, 6)
check("settings plan hash and totals equal the addendum",
      plan_sha == ADD["full"]["plan_sha256"] and len(plan) == ADD["full"]["calls"] == 354
      and plan_prompt == ADD["full"]["prompt_tokens"] and plan_out == ADD["full"]["max_output_tokens"]
      and plan_upper == ADD["full"]["upper_usd"] <= ADD["full"]["plan_upper_max_usd"],
      plan_sha256=plan_sha, calls=len(plan), prompt_tokens=plan_prompt, upper_usd=plan_upper)

log = jl(RUN / "execution_log.jsonl")
idx = [r["execution_index"] for r in log]
check("354 records, unique indices 1..354, all ok, one attempt each",
      len(log) == 354 and sorted(idx) == list(range(1, 355)) and all(r["status"] == "ok" and r["attempt"] == 1 for r in log),
      records=len(log), statuses=dict(Counter(r["status"] for r in log)), attempts=dict(Counter(r["attempt"] for r in log)))
by_idx = {p["execution_index"]: p for p in plan}
keys = ["execution_index", "replicate_id", "pair_index", "position_in_pair", "qid", "arm", "fingerprint", "max_completion_tokens"]
check("every log record matches its plan entry (index, arm, qid, fingerprint, order fields)",
      all(all(r[k] == by_idx[r["execution_index"]][k] for k in keys) for r in log))
fp_ok = [sha(json.dumps(r["request"], sort_keys=True).encode()) == r["fingerprint"] for r in log]
check("record fingerprint = sha256(json.dumps(request, sort_keys=True))", all(fp_ok), matched=sum(fp_ok))

e8 = jl(E8_RUN / "execution_log.jsonl")
e8_by = {(r["qid"], r["arm"]): r for r in e8}
R = {(r["qid"], r["arm"]): r for r in log}
assert len(R) == 354
b1_eq = [R[(q, "B1s")]["fingerprint"] == e8_by[(q, "L-B1")]["fingerprint"] == e8_by[(q, "L-B1r")]["fingerprint"]
         and R[(q, "B1s")]["request"] == e8_by[(q, "L-B1")]["request"] for q in QIDS]
check("B1s requests equal frozen E8 L-B1 (and L-B1r) fingerprints and loggable requests per qid", all(b1_eq), equal=sum(b1_eq))


def pages_and_images(req):
    content = req["messages"][1]["content"]
    pages, images = [], []
    for part in content[1:]:
        if part["type"] == "text":
            m = re.fullmatch(r"\[Page (\d+)\]", part["text"])
            assert m, "unexpected text part"
            pages.append(int(m.group(1)))
        else:
            images.append(part)
    assert len(pages) == len(images)
    return pages, images


manifest = pd.read_csv(FROZEN / "e5" / "tables" / "render_manifest_heldout.csv").set_index(["doc_id", "page"])
page_tag_ok, img_prefix_ok, header_ok, manifest_ok, f8ab_same, b1_tags_ok = [], [], [], [], [], []
used_pages = set()
for q in QIDS:
    top8 = [int(p) for p in V.at[q, "pages"][:8]]
    doc = V.at[q, "doc_id"]
    pb, ib = pages_and_images(R[(q, "B1s")]["request"])
    for arm in ("F8a", "F8b"):
        pf, imf = pages_and_images(R[(q, arm)]["request"])
        page_tag_ok.append(pf == top8 and len(set(pf)) == 8)
        img_prefix_ok.append([i["sha256"] for i in imf[:4]] == [i["sha256"] for i in ib])
        header_ok.append(R[(q, arm)]["request"]["messages"][0] == R[(q, "B1s")]["request"]["messages"][0]
                         and R[(q, arm)]["request"]["messages"][1]["content"][0] == R[(q, "B1s")]["request"]["messages"][1]["content"][0])
        for p, im in zip(pf, imf):
            row = manifest.loc[(doc, p)]
            manifest_ok.append(im["sha256"] == row["sha256"] and im["dimensions"] == [int(row["width_px"]), int(row["height_px"])]
                               and im["detail"] == "high")
            used_pages.add((doc, p))
    b1_tags_ok.append(pb == top8[:4])
    f8ab_same.append(R[(q, "F8a")]["fingerprint"] == R[(q, "F8b")]["fingerprint"])
check("B1s page tags = V top 4", all(b1_tags_ok), ok=sum(b1_tags_ok))
check("F8a/F8b page tags = V top 8 in rank order, 8 distinct pages", all(page_tag_ok), ok=sum(page_tag_ok), of=len(page_tag_ok))
check("F8 images for ranks 1-4 have the same sha256 as B1s's; system and question header identical",
      all(img_prefix_ok) and all(header_ok), images_ok=sum(img_prefix_ok), headers_ok=sum(header_ok))
check("F8a and F8b requests identical per qid", all(f8ab_same), ok=sum(f8ab_same))
disk_ok = []
for doc, p in sorted(used_pages):
    row = manifest.loc[(doc, p)]
    f = ROOT / row["image_path"]
    disk_ok.append(f.is_file() and sha(f.read_bytes()) == row["sha256"])
check("every F8 image hash/dimensions equal the frozen E5 render manifest (and the files on disk)",
      all(manifest_ok) and all(disk_ok), images=len(manifest_ok), unique_pages=len(used_pages), disk_ok=sum(disk_ok))

served = Counter(r["served_model"] for r in log)
sysfp = Counter(str(r["system_fingerprint"]) for r in log)
check("served model gpt-6-luna only", set(served) == {"gpt-6-luna"}, served=dict(served))
check("system fingerprint constant (note: value is None in every call, as in E8)", len(sysfp) == 1, values=dict(sysfp),
      e8_values=dict(Counter(str(r["system_fingerprint"]) for r in e8)))
check("finish_reason stop and no parse error", all(r["finish_reason"] == "stop" and r["parse_error"] is None for r in log),
      finish=dict(Counter(r["finish_reason"] for r in log)))
params = {json.dumps({k: v for k, v in r["request"].items() if k != "messages"}, sort_keys=True) for r in log}
e8params = {json.dumps({k: v for k, v in e8_by[(q, "L-B1")]["request"].items() if k != "messages"}, sort_keys=True) for q in QIDS}
p0 = json.loads(next(iter(params)))
check("model parameters identical across arms and equal to E8 L-B1",
      len(params) == 1 and params == e8params and p0["temperature"] == 0 and p0["reasoning_effort"] == "none"
      and p0["max_completion_tokens"] == 800 and p0["response_format"]["type"] == "json_schema"
      and p0["response_format"]["json_schema"]["strict"] is True and p0["model"] == "gpt-6-luna",
      distinct_param_sets=len(params), keys=sorted(p0))


# own reply parser (contract b1), compared with the logged parse
def parse(raw):
    d = json.loads(raw)
    assert isinstance(d, dict) and set(d) == {"answer", "cited_pages", "evidence"}
    a = d["answer"]
    if isinstance(a, str) and a.strip().lower() == "not answerable":
        a = NA
    cited = []
    for p in d["cited_pages"]:
        assert (isinstance(p, int) and not isinstance(p, bool)) or (isinstance(p, float) and p.is_integer())
        cited.append(int(p))
    for e in d["evidence"]:
        assert set(e) == {"page", "quote"}
    if a == NA:
        assert not cited and not d["evidence"]
    return a, cited


reparse = [parse(r["raw_response"]) == (r["parsed"]["answer"], r["parsed"]["cited_pages"]) for r in log]
check("independent reparse of every raw reply equals the logged parse", all(reparse), ok=sum(reparse))

# order and counterbalance
pairs = defaultdict(list)
for r in sorted(log, key=lambda r: r["execution_index"]):
    if r["arm"] in ("B1s", "F8a"):
        pairs[r["pair_index"]].append(r)
adjacent = all(len(v) == 2 and v[0]["qid"] == v[1]["qid"] and {v[0]["arm"], v[1]["arm"]} == {"B1s", "F8a"}
               and v[1]["execution_index"] == v[0]["execution_index"] + 1 == 2 * k for k, v in pairs.items())
b1_first = {v[0]["qid"] for v in pairs.values() if v[0]["arm"] == "B1s"}
f8b = sorted((r for r in log if r["arm"] == "F8b"), key=lambda r: r["execution_index"])
pair_order = [pairs[k][0]["qid"] for k in sorted(pairs)]
order_rng = np.random.default_rng(ADD["seeds"]["order"])
order = list(QIDS)
order_rng.shuffle(order)
seeded_first = set(order_rng.choice(order, size=59, replace=False).tolist())
times = sorted(log, key=lambda r: r["execution_index"])
sequential = all(datetime.fromisoformat(b["started_at"]) >= datetime.fromisoformat(a["completed_at"]) for a, b in zip(times, times[1:]))
check("B1s/F8a adjacent per question, 59/59 counterbalanced, F8b block after all pairs, executed sequentially in plan order",
      adjacent and len(pairs) == 118 and len(b1_first) == 59 and min(r["execution_index"] for r in f8b) == 237
      and [r["qid"] for r in f8b] == pair_order and sequential
      and datetime.fromisoformat(f8b[0]["started_at"]) >= datetime.fromisoformat(times[235]["completed_at"]),
      pairs=len(pairs), b1s_first=len(b1_first), f8b_first_index=f8b[0]["execution_index"], sequential=sequential)
check("pair order and 59/59 split reproduce from order seed 20261127", order == pair_order and seeded_first == b1_first)
smoke_q = sorted(np.random.default_rng(ADD["seeds"]["smoke"]).choice(QIDS, size=6, replace=False).tolist())
check("smoke qids reproduce from smoke seed 20261129", smoke_q == ADD["smoke"]["qids"], qids=smoke_q)

# ---------------------------------------------------------------- 3. tokens and cost
ENC = tiktoken.get_encoding("o200k_base")


def token_model(req):
    n, imgs = 0, 0
    for m in req["messages"]:
        parts = [{"type": "text", "text": m["content"]}] if isinstance(m["content"], str) else m["content"]
        for p in parts:
            if p["type"] == "text":
                n += len(ENC.encode(p["text"]))
            else:
                w, h = p["dimensions"]
                n += floor(1.2 * ceil(w / 32) * ceil(h / 32))
                imgs += 1
    return n + (9 if imgs else 10) + (100 if req["response_format"]["type"] == "json_schema" else 0)


def cost(r):
    c = r.get("cached_prompt_tokens") or 0
    return (r["prompt_tokens"] - c) * PRICE_IN + c * PRICE_CACHED + r["completion_tokens"] * PRICE_OUT


tok_ok = [r["prompt_tokens"] is not None and r["prompt_tokens"] == token_model(r["request"]) == by_idx[r["execution_index"]]["prompt_tokens"]
          for r in log]
full_cost = sum(cost(r) for r in log)
check("billed prompt tokens = token model = planned tokens for every full-run call", all(tok_ok), ok=sum(tok_ok))
check("per-record cost recomputes and full observed cost = $0.147055 (summary 0.14705494)",
      all(abs(cost(r) - r["list_price_cost_usd"]) < 1e-12 for r in log) and round(full_cost, 6) == 0.147055
      and abs(full_cost - json.loads((RUN / "summary.json").read_text())["observed_list_price_cost_usd"]) < 1e-9,
      full_cost_usd=round(full_cost, 8))
smoke_settings = json.loads((SMOKE / "settings.json").read_text())
smoke_plan_sha = sha(json.dumps(smoke_settings["plan"], sort_keys=True).encode())
smoke_cost = sum(cost(r) for r in smoke_log)
smoke_tok = [r["prompt_tokens"] == token_model(r["request"]) for r in smoke_log]
smoke_fp = [r["fingerprint"] == R[(r["qid"], "F8a")]["fingerprint"] for r in smoke_log]
check("smoke: plan hash = addendum, 6 ok, tokens = model, fingerprints = F8, cost = $0.004592 <= $0.02",
      smoke_plan_sha == ADD["smoke"]["plan_sha256"] and len(smoke_log) == 6 and all(r["status"] == "ok" for r in smoke_log)
      and all(smoke_tok) and all(smoke_fp) and round(smoke_cost, 6) == 0.004592 and smoke_cost <= 0.02,
      smoke_cost_usd=round(smoke_cost, 8), smoke_plan_sha256=smoke_plan_sha)
check("cumulative spend within ceiling and prior spend recorded",
      abs(settings["prior_spend_usd"] - smoke_cost) < 1e-12 and full_cost + smoke_cost <= 0.50,
      cumulative_usd=round(full_cost + smoke_cost, 6))
cache = Counter()
for r in log:
    cache[(r["arm"], r["position_in_pair"], (r["cached_prompt_tokens"] or 0) > 0)] += 1
uncached_cost = sum(r["prompt_tokens"] * PRICE_IN + r["completion_tokens"] * PRICE_OUT for r in log)
FACTS["prompt_cache"] = {
    "calls_with_cached_prefix": {f"{a}|pos{p}": n for (a, p, c), n in sorted(cache.items(), key=str) if c},
    "cached_tokens_by_arm": {a: int(sum((r["cached_prompt_tokens"] or 0) for r in log if r["arm"] == a)) for a in ("B1s", "F8a", "F8b")},
    "e8_calls_with_cached_prefix": int(sum((r.get("cached_prompt_tokens") or 0) > 0 for r in e8)),
    "full_cost_without_cache_usd": round(uncached_cost, 6),
    "cost_by_arm_usd": {a: round(sum(cost(r) for r in log if r["arm"] == a), 6) for a in ("B1s", "F8a", "F8b")},
    "median_latency_s": {a: float(np.median([r["latency_s"] for r in log if r["arm"] == a])) for a in ("B1s", "F8a", "F8b")},
}

# ---------------------------------------------------------------- 4. scoring
nb03 = json.loads((ROOT / "notebooks" / "03_evaluation.ipynb").read_text())
nb07 = json.loads((ROOT / "notebooks" / "07_baseline_consolidation.ipynb").read_text())
s1_src = "".join(next(c for c in nb03["cells"] if c.get("id") == "f653d232")["source"])
v2_src = "".join(next(c for c in nb07["cells"] if c.get("id") == "b1-scorer-v2")["source"])
NS = {"re": re, "json": json, "pd": pd, "np": np, "isclose": isclose, "ast": ast, "FROZEN_DIR": FROZEN, "NOT_ANSWERABLE": NA}
with contextlib.redirect_stdout(io.StringIO()):
    exec(s1_src, NS)
    exec(v2_src, NS)
eval_score, score_v2, DEBATABLE = NS["eval_score"], NS["score_v2"], NS["DEBATABLE_QIDS"]
FACTS["scorer_sources_sha256"] = {"nb03_f653d232": sha(s1_src.encode()), "nb07_b1-scorer-v2": sha(v2_src.encode())}


def abstained(a):
    return isinstance(a, str) and a == NA


def supplied(req):
    return pages_and_images(req)[0]


def blind_identity(q, reply):
    payload = {"document": str(qs.at[q, "doc_id"]), "evidence_pages": " ".join(map(str, qs.at[q, "evidence_pages"])),
               "question": str(qs.at[q, "question"]), "answer_format": str(qs.at[q, "answer_format"]),
               "reference": str(qs.at[q, "answer"]), "reply": json.dumps(reply) if isinstance(reply, list) else str(reply)}
    return sha(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode())


labels = {}
for pkg in ("scoring_v2", "e8_scoring_v2"):
    lab = pd.read_csv(FROZEN / pkg / "adjudication_labels.csv", dtype=str).fillna("")
    labels.update(dict(zip(lab["identity_sha256"], lab["label"])))


def score_record(q, arm, reply_rec):
    a, cited = reply_rec["parsed"]["answer"], reply_rec["parsed"]["cited_pages"]
    ref, fmt = qs.at[q, "answer"], qs.at[q, "answer_format"]
    s1 = eval_score(ref, a, fmt)
    cls, _ = score_v2(ref, a, fmt, debatable=q in DEBATABLE)
    ident = blind_identity(q, a)
    final = (labels.get(ident, "pending") if cls == "gray" else cls)
    sup = supplied(reply_rec["request"])
    return {"qid": q, "arm": arm, "doc_id": qs.at[q, "doc_id"], "answerable": bool(ANS[q]), "s1": s1, "s1_correct": s1 > 0,
            "abstained": abstained(a), "citation_valid": set(cited) <= set(sup) and (abstained(a) or bool(cited)),
            "schema_valid": reply_rec["parse_error"] is None, "v2_class": cls, "v2_final": final, "identity": ident,
            "label_reused": cls == "gray" and ident in labels, "cited": cited, "supplied": sup, "pages_read": len(sup)}


rows = [score_record(q, arm, R[(q, arm)]) for q in QIDS for arm in ("B1s", "F8a", "F8b")]
for q in QIDS:
    for name, deep in (("A1a", "F8a"), ("A1b", "F8b")):
        src = deep if q in TRIG else "B1s"
        rows.append({**score_record(q, src, R[(q, src)]), "arm": name, "source": src})
S = pd.DataFrame(rows)
S["source"] = S["source"].fillna(S["arm"])
ARMS = ["B1s", "F8a", "F8b", "A1a", "A1b"]


def arm_stats(a):
    f = S[S["arm"] == a]
    ans, un = f[f["answerable"]], f[~f["answerable"]]
    return {"S-v1 /102": int(ans["s1_correct"].sum()), "correct abstentions /16": int(un["abstained"].sum()),
            "unanswerable S-v1 >0 /16": int(un["s1_correct"].sum()),
            "citation validity": round(float(f["citation_valid"].mean()), 4), "schema validity": float(f["schema_valid"].mean()),
            "S-v2 correct": int((ans["v2_final"] == "correct").sum()), "S-v2 pending": int((ans["v2_final"] == "pending").sum()),
            "S-v2 unsure": int((ans["v2_final"] == "unsure").sum()), "labels reused": int(ans["label_reused"].sum())}


ARM_TABLE = {a: arm_stats(a) for a in ARMS}
claimed = {"B1s": (44, 9), "F8a": (46, 9), "F8b": (46, 8), "A1a": (47, 9), "A1b": (46, 9)}
check("S-v1 counts and correct abstentions per arm reproduce the claim",
      all((ARM_TABLE[a]["S-v1 /102"], ARM_TABLE[a]["correct abstentions /16"]) == claimed[a] for a in ARMS),
      recomputed={a: (ARM_TABLE[a]["S-v1 /102"], ARM_TABLE[a]["correct abstentions /16"]) for a in ARMS})
check("citation validity B1s 1.0, F8a/F8b 0.9915 (117/118)",
      ARM_TABLE["B1s"]["citation validity"] == 1.0 and ARM_TABLE["F8a"]["citation validity"] == ARM_TABLE["F8b"]["citation validity"] == 0.9915,
      recomputed={a: ARM_TABLE[a]["citation validity"] for a in ARMS})
invalid = S[~S["citation_valid"]][["arm", "qid", "doc_id", "answerable", "cited", "supplied", "abstained", "s1_correct", "source"]]
INVALID = []
for r in invalid.itertuples():
    extra = sorted(set(r.cited) - set(r.supplied))
    n_pages = int(rk[(rk["qid"] == r.qid) & (rk["arm"] == "V")]["pages"].map(len).iloc[0])
    INVALID.append({"arm": r.arm, "source_arm": r.source, "qid": r.qid, "answerable": r.answerable, "cited": r.cited,
                    "supplied": r.supplied, "cited_outside_supplied": extra, "empty_citation_on_answer": (not r.cited and not r.abstained),
                    "document_pages": n_pages, "extra_page_in_document": all(1 <= p <= n_pages for p in extra),
                    "extra_page_rank_in_V": [int(list(V.at[r.qid, "pages"]).index(p)) + 1 if p in list(V.at[r.qid, "pages"]) else None for p in extra],
                    "extra_page_is_annotated_evidence": [p in qs.at[r.qid, "evidence_pages"] for p in extra],
                    "s1_correct": bool(r.s1_correct), "triggered": r.qid in TRIG})
FACTS["invalid_citations"] = INVALID

# compare with the notebook's per-question table
nbq = pd.read_csv(E9_OUT / "evaluation_per_question.csv")
mine = S.set_index(["qid", "arm"])
theirs = nbq.set_index(["qid", "arm"])
cols = ["s1_correct", "citation_valid", "abstained", "v2_class", "v2_final", "label_reused"]
diffs = {c: int((mine.loc[theirs.index, c].astype(str) != theirs[c].astype(str)).sum()) for c in cols}
score_diff = float(np.max(np.abs(mine.loc[theirs.index, "s1"].to_numpy() - theirs["s1_score"].to_numpy())))
check("row-by-row agreement with the notebook's evaluation_per_question.csv (590 rows)",
      len(theirs) == 590 and all(v == 0 for v in diffs.values()) and score_diff < 1e-12, column_mismatches=diffs, max_s1_diff=score_diff)

# E8 frozen replies re-scored with the same scorer
e8rows = {arm: {q: eval_score(qs.at[q, "answer"], e8_by[(q, arm)]["parsed"]["answer"], qs.at[q, "answer_format"]) > 0 for q in QIDS}
          for arm in ("L-B1", "L-B1r")}
e8tab = pd.read_csv(FROZEN / "e8" / "tables" / "evaluation_per_question.csv")
e8tab_ok = all(bool(e8tab[(e8tab["arm"] == arm) & (e8tab["qid"] == q)]["s1_correct"].iloc[0]) == e8rows[arm][q] for arm in e8rows for q in QIDS)
check("frozen E8 L-B1/L-B1r replies re-score to the frozen E8 table (46/102 each)",
      e8tab_ok and sum(e8rows["L-B1"][q] for q in QIDS if ANS[q]) == 46 and sum(e8rows["L-B1r"][q] for q in QIDS if ANS[q]) == 46)

# S-v2: label reuse and the blind queue
gray = S[S["v2_class"] == "gray"]
pend = S[(S["v2_final"] == "pending") & S["answerable"] & S["arm"].isin(["B1s", "F8a", "F8b"])]
pend_ids = set(pend["identity"])
derived_pend = set(S[(S["v2_final"] == "pending") & S["arm"].isin(["A1a", "A1b"])]["identity"])
queue = pd.read_csv(E9_OUT / "adjudication_queue.csv", dtype=str).fillna("")
key = pd.read_csv(E9_OUT / "adjudication_key_SEALED.csv", dtype=str).fillna("")
q_ident = {}
for r in queue.itertuples():
    payload = {"document": r.document, "evidence_pages": r.evidence_pages, "question": r.question, "answer_format": r.answer_format,
               "reference": r.reference, "reply": r.reply}
    q_ident[r.item_id] = sha(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode())
key_ident = dict(zip(key["item_id"], key["identity"]))
arm_words = re.compile(r"\b(B1s|F8a|F8b|F8|A1a|A1b|A1|L-B1r?|arm)\b", re.I)
leak_cols = [c for c in queue.columns if arm_words.search(c)]
leak_cells = int(sum(bool(arm_words.search(str(v))) for c in ["item_id", "document", "evidence_pages", "answer_format"] for v in queue[c]))
key_arms_ok = all(set(row.arms.split(" | ")) == set(pend[pend["identity"] == row.identity]["arm"]) for row in key.itertuples())
key_qid_ok = all(set(pend[pend["identity"] == row.identity]["qid"]) == {row.qid} for row in key.itertuples())
check("blind queue = every pending answerable gray item of B1s/F8a/F8b exactly once; identities match sealed key",
      len(queue) == len(key) == len(pend_ids) == 13 and set(q_ident.values()) == pend_ids == set(key_ident.values())
      and q_ident == key_ident and queue["item_id"].is_unique and derived_pend <= pend_ids and key_arms_ok and key_qid_ok,
      queue=len(queue), pending_identities=len(pend_ids), pending_rows=len(pend), derived_subset=derived_pend <= pend_ids)
check("blind queue carries no arm information (columns and identifier cells)",
      not leak_cols and leak_cells == 0 and list(queue.columns) == ["item_id", "document", "evidence_pages", "question", "answer_format",
                                                                     "reference", "reply", "label (correct / wrong / unsure)", "note"],
      columns=list(queue.columns), labels_filled=int((queue["label (correct / wrong / unsure)"] != "").sum()))
reused = S[S["label_reused"]]
check("S-v2 classes: unanswerable never gray; reused labels come only from frozen packages; per-arm S-v2 matches notebook",
      gray["answerable"].all() and all(i in labels for i in reused["identity"])
      and all((ARM_TABLE[a]["S-v2 correct"], ARM_TABLE[a]["S-v2 pending"], ARM_TABLE[a]["S-v2 unsure"]) ==
              {"B1s": (44, 7, 1), "F8a": (47, 1, 1), "F8b": (46, 5, 1), "A1a": (47, 6, 1), "A1b": (46, 7, 1)}[a] for a in ARMS),
      v2={a: (ARM_TABLE[a]["S-v2 correct"], ARM_TABLE[a]["S-v2 pending"], ARM_TABLE[a]["S-v2 unsure"], ARM_TABLE[a]["labels reused"]) for a in ARMS},
      gray_rows=len(gray), reused_rows=len(reused), reused_label_mix=dict(Counter(labels[i] for i in reused["identity"])))

# ---------------------------------------------------------------- 5. statistics and decision rules
ansq = sorted(q for q in QIDS if ANS[q])
DOC = qs.loc[ansq, "doc_id"]
DOCS = sorted(set(DOC))


def vec(arm, col="s1_correct"):
    f = S[(S["arm"] == arm) & S["answerable"]].set_index("qid").loc[ansq]
    return f[col].astype(float)


def contrast(t, c, seed=20261128, subset=None):
    d = (t - c)
    if subset is not None:
        d = d[d.index.isin(subset)]
    docs = DOC.loc[d.index].to_numpy()
    order_ = sorted(set(docs))
    sums2 = np.array([int(round(2 * d[docs == x].sum())) for x in order_])  # exact: differences are multiples of 0.5
    counts = np.array([(docs == x).sum() for x in order_])
    picks = np.random.default_rng(seed).integers(0, len(order_), size=(10_000, len(order_)))
    boot = (sums2[picks].sum(1) / 2) / counts[picks].sum(1)
    k = len(order_)
    signs = ((np.arange(2 ** k)[:, None] >> np.arange(k)) & 1) * 2 - 1
    tstar = signs @ sums2
    return {"delta": float(d.mean()), "ci95": [float(x) for x in np.percentile(boot, [2.5, 97.5])],
            "p05": float(np.percentile(boot, 5)), "sign_flip_p": float(np.mean(tstar >= sums2.sum())), "n": len(d), "docs": k,
            "boot_fixed_denominator_p05": float(np.percentile((sums2[picks].sum(1) / 2) / len(d), 5))}


b1s, a1a, a1b, f8a, f8b_ = vec("B1s"), vec("A1a"), vec("A1b"), vec("F8a"), vec("F8b")
A1, F8 = (a1a + a1b) / 2, (f8a + f8b_) / 2
prim = contrast(A1, b1s)


def fb(t, c):
    return int(((t == 1) & (c == 0)).sum()), int(((t == 0) & (c == 1)).sum())


per_rep = {"A1a": {"delta": float((a1a - b1s).mean()), "fixed_broken": fb(a1a, b1s)},
           "A1b": {"delta": float((a1b - b1s).mean()), "fixed_broken": fb(a1b, b1s)}}
sec = {"F8 - B1s": contrast(F8, b1s), "A1 - F8": contrast(A1, F8), "F8 - B1s on triggered": contrast(F8, b1s, subset=TRIG),
       "F8 - B1s on untriggered": contrast(F8, b1s, subset=set(ansq) - TRIG)}
flips_f8 = int((f8a != f8b_).sum())
claimed_summary = json.loads((E9_OUT / "evaluation_summary.json").read_text())
cd = claimed_summary["decision"]
check("primary A1 - B1s: delta, CI95, bootstrap 5th pct, sign-flip p",
      round(prim["delta"], 4) == 0.0245 and [round(x, 4) for x in prim["ci95"]] == [0.0, 0.0505] and round(prim["p05"], 4) == 0.0052
      and prim["sign_flip_p"] == 0.125, recomputed={k: (round(v, 6) if isinstance(v, float) else v) for k, v in prim.items()})
check("per replicate: A1a +0.0294 (3/0), A1b +0.0196 (2/0)",
      per_rep["A1a"]["fixed_broken"] == (3, 0) and per_rep["A1b"]["fixed_broken"] == (2, 0)
      and round(per_rep["A1a"]["delta"], 4) == 0.0294 and round(per_rep["A1b"]["delta"], 4) == 0.0196, recomputed=per_rep)
check("secondary: F8 - B1s +0.0196, A1 - F8 +0.0049, F8a vs F8b flips 2 (answerable)",
      round(sec["F8 - B1s"]["delta"], 4) == 0.0196 and round(sec["A1 - F8"]["delta"], 4) == 0.0049 and flips_f8 == 2
      and all(abs(sec[k]["delta"] - claimed_summary["secondary"][k]["delta"]) < 1e-12
              and abs(sec[k]["p05"] - claimed_summary["secondary"][k]["p05_one_sided"]) < 1e-12
              and abs(sec[k]["sign_flip_p"] - claimed_summary["secondary"][k]["sign_flip_p"]) < 1e-12 for k in sec),
      recomputed={k: {"delta": round(v["delta"], 4), "ci95": [round(x, 4) for x in v["ci95"]], "p05": round(v["p05"], 4),
                      "p": v["sign_flip_p"]} for k, v in sec.items()}, flips_f8_answerable=flips_f8)

# frozen decision rules, applied in order
base = ARM_TABLE["B1s"]
guard = {a: {"abstentions": ARM_TABLE[a]["correct abstentions /16"] >= base["correct abstentions /16"] - 2,
             "abstention_margin": ARM_TABLE[a]["correct abstentions /16"] - (base["correct abstentions /16"] - 2),
             "citations": ARM_TABLE[a]["citation validity"] >= base["citation validity"] - 0.05,
             "citation_margin": round(ARM_TABLE[a]["citation validity"] - (base["citation validity"] - 0.05), 4),
             "schema": ARM_TABLE[a]["schema validity"] >= 0.99} for a in ["F8a", "F8b", "A1a", "A1b"]}
guard_pass = all(g["abstentions"] and g["citations"] and g["schema"] for g in guard.values())
delta = prim["delta"]
eng = delta >= 0.05 and all(v["delta"] >= 0.05 for v in per_rep.values())
broken = any(v["fixed_broken"][1] > v["fixed_broken"][0] / 2 for v in per_rep.values())
trace = []
if not guard_pass:
    verdict = "regression"; trace.append("guardrail failed")
elif delta <= -0.05:
    verdict = "regression"; trace.append("delta <= -0.05")
elif delta < 0.05:
    verdict = "no_meaningful_gain"; trace.append(f"guardrails pass; delta {delta:.4f} > -0.05; delta < +0.05 -> no_meaningful_gain")
elif not eng:
    verdict = "no_meaningful_gain"; trace.append("per-replicate engineering criterion fails")
elif broken:
    verdict = "regression"
elif sec["A1 - F8"]["delta"] <= 0:
    verdict = "more_pages_not_triggering"
elif prim["p05"] > 0 and prim["sign_flip_p"] <= 0.05 and flips_f8 <= 10:
    verdict = "adopt_adaptive_acquisition"
else:
    verdict = "promising_but_uncertain"
check("frozen decision rules (in order) give no_meaningful_gain; matches the notebook",
      verdict == "no_meaningful_gain" == cd["VERDICT (S-v1, frozen rules)"] and guard_pass == cd["guardrails pass"],
      verdict=verdict, trace=trace, guardrails=guard,
      net_fixes_needed_for_0_05=round(0.05 * 102, 2), observed_net_fixes_avg=round(delta * 102, 2),
      later_rules_if_reached={"broken>fixed/2": broken, "A1-F8>0": sec["A1 - F8"]["delta"] > 0,
                              "statistics_hold": prim["p05"] > 0 and prim["sign_flip_p"] <= 0.05, "flips_f8<=10": flips_f8 <= 10})

# ---------------------------------------------------------------- 6. interpretation challenges
# (a) session drift vs within-session churn
e8b, e8r = (pd.Series({q: float(e8rows[a][q]) for q in ansq}) for a in ("L-B1", "L-B1r"))
three = pd.DataFrame({"L-B1": e8b, "L-B1r": e8r, "B1s": b1s})
split = three[three.nunique(axis=1) > 1]
odd = {}
for q, row in split.iterrows():
    vals = row.to_dict()
    maj = 1.0 if sum(vals.values()) >= 2 else 0.0
    odd_arm = [a for a, v in vals.items() if v != maj][0]
    odd[q] = (odd_arm, "odd wrong" if vals[odd_arm] == 0 else "odd right")
odd_counts = Counter(a for a, _ in odd.values())
k_b1s, n_split = odd_counts.get("B1s", 0), len(odd)
from math import comb
p_binom = sum(comb(n_split, j) * (1 / 3) ** j * (2 / 3) ** (n_split - j) for j in range(k_b1s, n_split + 1))
raw_same = {"B1s=L-B1 raw identical": sum(R[(q, "B1s")]["raw_response"] == e8_by[(q, "L-B1")]["raw_response"] for q in QIDS),
            "L-B1=L-B1r raw identical": sum(e8_by[(q, "L-B1")]["raw_response"] == e8_by[(q, "L-B1r")]["raw_response"] for q in QIDS),
            "F8a=F8b raw identical": sum(R[(q, "F8a")]["raw_response"] == R[(q, "F8b")]["raw_response"] for q in QIDS)}
drift = {"B1s vs L-B1": {"flips": int((b1s != e8b).sum()), "fixed_broken (B1s right / B1s wrong)": fb(b1s, e8b)},
         "B1s vs L-B1r": {"flips": int((b1s != e8r).sum()), "fixed_broken": fb(b1s, e8r)},
         "L-B1 vs L-B1r (within E8)": {"flips": int((e8b != e8r).sum()), "fixed_broken": fb(e8r, e8b)},
         "questions with a 2-1 split across the three B1 replicates": n_split,
         "odd one out by replicate": dict(odd_counts),
         "B1s odd-one-out direction": dict(Counter(d for a, d in odd.values() if a == "B1s")),
         "one-sided binomial p (B1s odd one out >= observed | 1/3)": round(p_binom, 4),
         "B1s-vs-L-B1 flips on triggered answerable": int(((b1s != e8b) & b1s.index.isin(TRIG)).sum()),
         "A1 avg - L-B1": round(float((A1 - e8b).mean()), 4), "A1 avg - L-B1r": round(float((A1 - e8r).mean()), 4),
         "F8 avg - L-B1": round(float((F8 - e8b).mean()), 4), **raw_same}
check("(a) B1s vs frozen L-B1: 6 flips, 44 vs 46 reproduced", drift["B1s vs L-B1"]["flips"] == 6 and int(b1s.sum()) == 44, drift=drift)

# (d) S-v2 bounds, including the exact extremes over all labelings of the pending identities (labels shared across arms)
pend_list = sorted(pend_ids)


def v2_vec(arm, assign):
    f = S[(S["arm"] == arm) & S["answerable"]].set_index("qid").loc[ansq]
    final = [assign.get(i, v) if v == "pending" else v for i, v in zip(f["identity"], f["v2_final"])]
    return pd.Series(final, index=ansq)


def v2_delta(assign):
    b, aa, ab, fa, fbb = (v2_vec(a, assign) for a in ("B1s", "A1a", "A1b", "F8a", "F8b"))
    keep = ~((b == "unsure") | (aa == "unsure") | (ab == "unsure") | (fa == "unsure") | (fbb == "unsure"))
    c = lambda s: (s[keep] == "correct").astype(float)
    a1 = (c(aa) + c(ab)) / 2
    a1a_d, a1b_d = float((c(aa) - c(b)).mean()), float((c(ab) - c(b)).mean())
    return float((a1 - c(b)).mean()), a1a_d, a1b_d, float(((c(fa) + c(fbb)) / 2 - c(b)).mean()), int(keep.sum())


bounds = {}
for lab in ("wrong", "correct"):
    d, da, db, df, n = v2_delta({i: lab for i in pend_list})
    bounds[f"pending as {lab}"] = {"A1 - B1s": round(d, 4), "A1a - B1s": round(da, 4), "A1b - B1s": round(db, 4), "F8 - B1s": round(df, 4), "n": n}
ext = [v2_delta(dict(zip(pend_list, lab)))[:3] for lab in product(["wrong", "correct"], repeat=len(pend_list))]
bounds["exact range over all 2^13 consistent labelings"] = {
    "A1 - B1s min": round(min(e[0] for e in ext), 4), "A1 - B1s max": round(max(e[0] for e in ext), 4),
    "labelings with A1-B1s >= 0.05 and both replicates >= 0.05": int(sum(e[0] >= 0.05 and e[1] >= 0.05 and e[2] >= 0.05 for e in ext)),
    "labelings with A1-B1s <= -0.05": int(sum(e[0] <= -0.05 for e in ext))}
check("(d) S-v2 bounds reproduce the notebook and no consistent labeling reaches +0.05 or -0.05",
      bounds["pending as wrong"]["A1 - B1s"] == round(claimed_summary["s_v2"]["pending as wrong"]["A1 - B1s"], 4)
      and bounds["pending as correct"]["A1 - B1s"] == round(claimed_summary["s_v2"]["pending as correct"]["A1 - B1s"], 4)
      and bounds["exact range over all 2^13 consistent labelings"]["labelings with A1-B1s >= 0.05 and both replicates >= 0.05"] == 0
      and bounds["exact range over all 2^13 consistent labelings"]["labelings with A1-B1s <= -0.05"] == 0, bounds=bounds)

# (e) ordering
grp = pd.Series({q: ("B1s first" if q in b1_first else "F8a first") for q in ansq})
order_tab = {}
for g in ("B1s first", "F8a first"):
    m = grp == g
    order_tab[g] = {"answerable": int(m.sum()), "B1s": int(b1s[m].sum()), "F8a": int(f8a[m].sum()), "F8b": int(f8b_[m].sum()),
                    "A1a": int(a1a[m].sum()), "F8a-B1s fixed/broken": fb(f8a[m], b1s[m]), "F8a vs F8b flips": int((f8a[m] != f8b_[m]).sum()),
                    "B1s vs L-B1 flips": int((b1s[m] != e8b[m]).sum()),
                    "F8a cached-prefix calls": int(sum((R[(q, 'F8a')]["cached_prompt_tokens"] or 0) > 0 for q in grp.index[m]))}
diff_q = (f8a - b1s)
obs = diff_q[grp == "B1s first"].mean() - diff_q[grp == "F8a first"].mean()
prng = np.random.default_rng(20261130)
labs = (grp == "B1s first").to_numpy()
perm = []
for _ in range(10_000):
    s = prng.permutation(labs)
    perm.append(diff_q[s].mean() - diff_q[~s].mean())
p_order = float(np.mean(np.abs(perm) >= abs(obs) - 1e-12))
cache_f8b = pd.Series({q: (R[(q, "F8b")]["cached_prompt_tokens"] or 0) > 0 for q in ansq})
order_tab["permutation p (two-sided) for F8a-B1s differing by order"] = round(p_order, 4)
order_tab["observed difference in F8a-B1s (B1s first minus F8a first)"] = round(float(obs), 4)
order_tab["F8a vs F8b flips among F8b cached / uncached"] = [int((f8a[cache_f8b] != f8b_[cache_f8b]).sum()), int(cache_f8b.sum()),
                                                             int((f8a[~cache_f8b] != f8b_[~cache_f8b]).sum()), int((~cache_f8b).sum())]
check("(e) no detectable order effect on F8a - B1s", p_order > 0.05, order=order_tab)

# sign-flip power: how many documents carry a non-zero A1 - B1s sum (min attainable p = 2^-k when all k are positive)
dsum = (A1 - b1s).groupby(DOC.loc[ansq].to_numpy()).sum()
nonzero = dsum[dsum != 0]
FACTS["primary_per_document"] = {"documents_nonzero": int(len(nonzero)), "nonzero_sums": sorted(float(x) for x in nonzero),
                                 "min_attainable_sign_flip_p": 2.0 ** -int(len(nonzero)),
                                 "documents_needed_all_positive_for_p<=0.05": 5}
# strict S-v1 sensitivity (score == 1), descriptive
strict = {a: S[(S["arm"] == a) & S["answerable"]].set_index("qid").loc[ansq]["s1"].eq(1.0).astype(float) for a in ARMS}
FACTS["strict_s1_sensitivity"] = {"counts": {a: int(v.sum()) for a, v in strict.items()},
                                  "A1 - B1s": round(float(((strict["A1a"] + strict["A1b"]) / 2 - strict["B1s"]).mean()), 4)}

# S-v2 extremes with unsure allowed (3^13 consistent labelings, vectorised; unsure drops the question from every arm)
pid = {i: k for k, i in enumerate(pend_list)}
arms5 = ("B1s", "A1a", "A1b")
fixed_val = np.zeros((len(ansq), 3))   # 1 correct, 0 wrong, nan unsure; pending -> placeholder
pend_ix = -np.ones((len(ansq), 3), dtype=int)
for j, a in enumerate(arms5):
    f = S[(S["arm"] == a) & S["answerable"]].set_index("qid").loc[ansq]
    for i, (ident, v) in enumerate(zip(f["identity"], f["v2_final"])):
        if v == "pending":
            pend_ix[i, j] = pid[ident]
        else:
            fixed_val[i, j] = {"correct": 1.0, "wrong": 0.0, "unsure": np.nan}[v]
fv = [S[(S["arm"] == a) & S["answerable"]].set_index("qid").loc[ansq]["v2_final"] for a in ("F8a", "F8b")]
f8_unsure = np.array([(x == "unsure") or (y == "unsure") for x, y in zip(*fv)])
best, worst, hits = -1.0, 1.0, 0
codes = np.array(list(product([0.0, 1.0, np.nan], repeat=len(pend_list))))      # 1,594,323 x 13
for chunk in np.array_split(codes, 40):
    val = np.repeat(fixed_val[None], len(chunk), axis=0)
    for j in range(3):
        m = pend_ix[:, j] >= 0
        val[:, m, j] = chunk[:, pend_ix[m, j]]
    keep = ~np.isnan(val).any(axis=2) & ~f8_unsure[None]
    v = np.nan_to_num(val)
    d = np.where(keep, (v[:, :, 1] + v[:, :, 2]) / 2 - v[:, :, 0], 0.0).sum(1) / keep.sum(1)
    da = np.where(keep, v[:, :, 1] - v[:, :, 0], 0.0).sum(1) / keep.sum(1)
    db = np.where(keep, v[:, :, 2] - v[:, :, 0], 0.0).sum(1) / keep.sum(1)
    best, worst = max(best, float(d.max())), min(worst, float(d.min()))
    hits += int(((d >= 0.05) & (da >= 0.05) & (db >= 0.05)).sum())
bounds["exact range with unsure allowed (3^13)"] = {"A1 - B1s min": round(worst, 4), "A1 - B1s max": round(best, 4),
                                                                  "labelings meeting +0.05 in average and both replicates": hits}
check("(d') S-v2 with unsure allowed: no labeling of the 13 pending items reaches the +0.05 engineering criterion",
      hits == 0 and worst > -0.05, range=[round(worst, 4), round(best, 4)])

# prompt caching: server-side prefix cache was active in this session but not in E8 (identical B1 prompts, 5-10 min apart, 0 hits)
gap = lambda a, b: (datetime.fromisoformat(b["started_at"]) - datetime.fromisoformat(a["completed_at"])).total_seconds() / 60
FACTS["prompt_cache"]["e8_L-B1_to_L-B1r_gap_min"] = [round(min(gap(e8_by[(q, 'L-B1')], e8_by[(q, 'L-B1r')]) for q in QIDS), 1),
                                                     round(max(gap(e8_by[(q, 'L-B1')], e8_by[(q, 'L-B1r')]) for q in QIDS), 1)]
FACTS["prompt_cache"]["e9_F8a_to_F8b_gap_min"] = [round(min(gap(R[(q, 'F8a')], R[(q, 'F8b')]) for q in QIDS), 1),
                                                  round(max(gap(R[(q, 'F8a')], R[(q, 'F8b')]) for q in QIDS), 1)]
FACTS["prompt_cache"]["F8a_first_cached_are_smoke_qids"] = sorted(
    q for q in QIDS if R[(q, "F8a")]["position_in_pair"] == 1 and (R[(q, "F8a")]["cached_prompt_tokens"] or 0) > 0) == sorted(
    set(ADD["smoke"]["qids"]) & {q for q in QIDS if R[(q, "F8a")]["position_in_pair"] == 1 and (R[(q, "F8a")]["cached_prompt_tokens"] or 0) > 0})

# frozen package copy, if it exists (informational)
pkg_run = FROZEN / "e9" / "run_20261125T171152006205Z_57d16dea_full"
if pkg_run.is_dir():
    same = {f: (pkg_run / f).is_file() and (pkg_run / f).read_bytes() == (RUN / f).read_bytes() for f in ("execution_log.jsonl", "settings.json", "summary.json")}
    check("frozen e9 package run files byte-identical to the live run (informational)", all(same.values()), files=same)

FACTS.update({"arm_table": ARM_TABLE, "primary": prim, "per_replicate": per_rep, "secondary": sec, "flips_f8a_f8b_answerable": flips_f8,
              "flips_f8a_f8b_all118": int(sum(S[(S["arm"] == "F8a")].set_index("qid").loc[QIDS, "s1_correct"].to_numpy()
                                             != S[(S["arm"] == "F8b")].set_index("qid").loc[QIDS, "s1_correct"].to_numpy())),
              "guardrails": guard, "verdict": verdict, "drift": drift, "s_v2_bounds": bounds, "order": order_tab,
              "observed_cost_usd": {"full": round(full_cost, 6), "smoke": round(smoke_cost, 6), "cumulative": round(full_cost + smoke_cost, 6)}})
out = {"audit": "E9 Stage 2 independent audit", "run": RUN.name, "smoke": SMOKE.name,
       "repo_root": "<argument or cwd>", "passed": sum(c["passed"] for c in CHECKS), "total": len(CHECKS),
       "checks": CHECKS, "facts": FACTS}
(OUT / "audit_e9_stage2.json").write_text(json.dumps(out, indent=2, default=lambda o: o.item() if hasattr(o, "item") else str(o)) + "\n")
print(f"\n{out['passed']}/{out['total']} checks passed; verdict under frozen rules: {verdict}")
