"""Independent, read-only audit of E10 (agentic document reader).

Usage:  python audit_e10.py REPO_ROOT PACKAGE_DIR [OUT_DIR]
PACKAGE_DIR is the frozen package (experiments/frozen/e10); OUT_DIR defaults to PACKAGE_DIR.

The script never calls an API, imports nothing from notebook 10 or src/visualdoc, needs no torch (it decodes
the bf16 safetensors itself) and writes no question, answer or reply text: only identifiers, counts and hashes.
It re-derives: the plan and spec identity, every call's cost and bound, B1s request identity with frozen E8,
the agent's warm start, every page it saw (from the logged requests), every search result (from the cached
query embeddings and E5's page embeddings), the limits, S-v1 scores (with notebook 03's frozen scorer cell),
the primary contrast with its bootstrap and exact sign-flip test, and the verdict.
"""
import ast
import hashlib
import json
import re
import subprocess
import sys
from collections import Counter
from itertools import permutations
from math import isclose
from pathlib import Path

import numpy as np
import pandas as pd

ROOT, PKG = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
OUT = Path(sys.argv[3]).resolve() if len(sys.argv) > 3 else PKG
FROZEN = ROOT / "experiments" / "frozen"
SPEC_PATH = ROOT / "experiments" / "specs" / "e10_agentic_reader_v1.json"
SPEC_COMMIT = "25cd488"
E5_CACHE = ROOT / "data" / "cache" / "e5" / "colqwen2-v1.0-hf@ddc07d2317c8" / "af02fac2cb9b"
QUERY_CACHE = ROOT / "data" / "cache" / "e10" / "queries_cpu"
NA = "Not answerable"
PRICE_IN, PRICE_CACHED, PRICE_OUT = 0.10 / 1e6, 0.01 / 1e6, 0.50 / 1e6
CHECKS, FACTS = [], {}


def check(name, passed, **details):
    CHECKS.append({"name": name, "passed": bool(passed), "details": details})
    print(f"[{'PASS' if passed else 'FAIL'}] {name}: {json.dumps(details, default=str)[:300]}")


def sha(b):
    return hashlib.sha256(b).hexdigest()


def jl(path):
    return [json.loads(x) for x in Path(path).read_text().splitlines() if x.strip()]


def verify_sums(pkg):
    bad = [n for d, n in (l.split(maxsplit=1) for l in (pkg / "SHA256SUMS").read_text().splitlines() if l.strip())
           if not (pkg / n).is_file() or sha((pkg / n).read_bytes()) != d]
    return len((pkg / "SHA256SUMS").read_text().splitlines()), bad


def bf16_safetensors(path):
    raw = Path(path).read_bytes()
    n = int.from_bytes(raw[:8], "little")
    header = json.loads(raw[8:8 + n])
    meta = header["embedding"]
    assert meta["dtype"] == "BF16"
    start, end = meta["data_offsets"]
    bits = np.frombuffer(raw[8 + n + start:8 + n + end], dtype="<u2").astype(np.uint32) << 16
    return bits.view(np.float32).reshape(meta["shape"])


# 1. Frozen inputs and the package itself.
for name in ("e5", "e8", "e9", "e9_stage0"):
    total, bad = verify_sums(FROZEN / name)
    check(f"frozen package {name} matches SHA256SUMS", not bad, files=total, mismatched=bad)
if (PKG / "SHA256SUMS").is_file():
    total, bad = verify_sums(PKG)
    check("E10 package matches its SHA256SUMS", not bad, files=total, mismatched=bad)

# 2. Specification identity.
committed = subprocess.run(["git", "show", f"{SPEC_COMMIT}:experiments/specs/e10_agentic_reader_v1.json"], cwd=ROOT,
                           capture_output=True, check=True).stdout
spec = json.loads(committed)
check("spec byte-identical to its freeze commit", committed == SPEC_PATH.read_bytes(), commit=SPEC_COMMIT, sha256=sha(committed)[:12])
later = subprocess.run(["git", "log", "--format=%h", f"{SPEC_COMMIT}..HEAD", "--", "experiments/specs/e10_agentic_reader_v1.json"],
                       cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
check("spec never changed after its freeze commit", not later, later_commits=later)

runs = sorted(PKG.glob("full_*"))
smokes = sorted(PKG.glob("smoke_*"))
check("one full run and the smoke runs are in the package", len(runs) == 1 and len(smokes) >= 1, full=[r.name for r in runs], smoke=[s.name for s in smokes])
RUN = runs[0]
settings = json.loads((RUN / "settings.json").read_text())
plan = settings["plan"]
check("run settings carry the frozen spec, plan and contract hashes",
      settings["spec_sha256"] == sha(committed) and settings["plan_sha256"] == spec["plans"]["full_sha256"]
      and sha(json.dumps(plan, sort_keys=True).encode()) == spec["plans"]["full_sha256"]
      and settings["agent_contract_sha256"] == spec["agent"]["agent_contract_sha256"])

# 3. Population and plan design.
rank = pd.read_parquet(FROZEN / "e5" / "tables" / "rankings.parquet")
v = rank[(rank.arm == "V") & (rank.population == "held-out")].set_index("qid")
QIDS = sorted(v.index)
manifest = pd.read_csv(FROZEN / "e5" / "tables" / "render_manifest_heldout.csv").set_index(["doc_id", "page"])
doc_pages = {d: sorted(int(p) for p in g.index.get_level_values("page")) for d, g in manifest.groupby(level="doc_id")}
blocks = {}
for item in plan:
    blocks.setdefault(item["block_index"], []).append(item)
check("plan: 118 questions x {B1s, AGa, AGb}, one block per question, positions 1-3",
      len(plan) == 354 and set(i["qid"] for i in plan) == set(QIDS)
      and all(sorted(i["arm"] for i in b) == ["AGa", "AGb", "B1s"] and len({i["qid"] for i in b}) == 1 for b in blocks.values()))
orders = Counter(tuple(i["arm"] for i in sorted(b, key=lambda x: x["position_in_block"])) for b in blocks.values())
check("plan: the six arm orders are balanced (19 or 20 blocks each)", set(orders) == set(permutations(["B1s", "AGa", "AGb"]))
      and max(orders.values()) - min(orders.values()) <= 1, orders={"-".join(k): n for k, n in orders.items()})
q_all = pd.read_parquet(ROOT / "data" / "processed" / "mmlongbench_doc" / "questions.parquet")
q = q_all[q_all.qid.isin(QIDS)].set_index("qid")
del q_all
check("no test-pool question in the plan", set(q.doc_id) == set(v.doc_id) and len(q) == 118, documents=q.doc_id.nunique())

# 4. Calls: identity, cost, bound.
calls, items = jl(RUN / "calls.jsonl"), jl(RUN / "items.jsonl")
ok_items = [i for i in items if i["status"] == "ok"]
check("354 items completed, one ok record each", len(ok_items) == 354 and len({i["execution_index"] for i in ok_items}) == 354,
      attempts=len(items), interrupted=sum(i["status"] != "ok" for i in items))
ok_calls = [c for c in calls if c["status"] == "ok"]
check("every call succeeded on one served model", len(ok_calls) == len(calls) and {c["served_model"] for c in ok_calls} == {"gpt-6-luna"},
      calls=len(calls), models=sorted({str(c.get("served_model")) for c in calls}), fingerprints=sorted({str(c.get("system_fingerprint")) for c in calls}))


def cost(c):
    p, cached = c["prompt_tokens"], c["cached_prompt_tokens"] or 0
    return max(0, p - cached) * PRICE_IN + cached * PRICE_CACHED + c["completion_tokens"] * PRICE_OUT


check("each call's cost equals its billed usage at list price", all(isclose(cost(c), c["list_price_cost_usd"], abs_tol=1e-12) for c in ok_calls))
check("no billed prompt exceeded its pre-call bound", all(c["prompt_tokens"] <= c["prompt_bound"] for c in ok_calls),
      max_ratio=round(max(c["prompt_tokens"] / c["prompt_bound"] for c in ok_calls), 4))
check("no call exceeded the output allowance", all(c["completion_tokens"] <= 800 for c in ok_calls), max=max(c["completion_tokens"] for c in ok_calls))
spend_full = sum(cost(c) for c in ok_calls)
spend_smoke = sum(cost(c) if c.get("completion_tokens") is not None else c["cost_upper_usd"] for s in smokes for c in jl(s / "calls.jsonl"))
FACTS["spend_usd"] = {"full": round(spend_full, 6), "smoke_charged": round(spend_smoke, 6), "total": round(spend_full + spend_smoke, 6)}
check("cumulative E10 spend within the $3.50 ceiling", spend_full + spend_smoke <= 3.50, **FACTS["spend_usd"])

# 5. B1s requests are frozen E8 L-B1 requests.
e8 = {(r["qid"], r["arm"]): r for r in jl(FROZEN / "e8" / "run_20261125T140433934010Z_4edb90e7_full" / "execution_log.jsonl")}
b1_calls = [c for c in ok_calls if c["arm"] == "B1s"]
check("118 B1s calls, each byte-identical (loggable form and fingerprint) to frozen E8 L-B1",
      len(b1_calls) == 118 and all(c["request"] == e8[(c["qid"], "L-B1")]["request"] and c["fingerprint"] == e8[(c["qid"], "L-B1")]["fingerprint"] for c in b1_calls))
check("B1s prompt totals equal the E8 token model exactly", all(c["prompt_tokens"] == e8[(c["qid"], "L-B1")]["prompt_tokens"] for c in b1_calls))

# 6. Agent episodes: warm start, pages seen, limits, searches.
by_attempt = {}
for c in ok_calls:
    by_attempt.setdefault(c["attempt_id"], []).append(c)


def images_in(message):
    content = message.get("content")
    return [p["sha256"] for p in content if p["type"] == "image"] if isinstance(content, list) else []


warm_ok = seen_ok = limits_ok = forced_ok = True
search_total = search_equal = 0
page_cache = {}
for item in ok_items:
    if item["arm"] == "B1s":
        continue
    own = sorted(by_attempt[item["attempt_id"]], key=lambda c: c["call_index"])
    doc = q.at[item["qid"], "doc_id"]
    top4 = [int(p) for p in v.at[item["qid"], "pages"][:4]]
    first_user = own[0]["request"]["messages"][1]
    warm_ok &= images_in(first_user) == [manifest.at[(doc, p), "sha256"] for p in top4]
    # Pages seen, rebuilt from the images in the last request plus the images a final read added (none: finish ends it).
    last = own[-1]["request"]["messages"]
    shown = [h for m in last for h in images_in(m)]
    sha_to_page = {manifest.at[(doc, p), "sha256"]: p for p in doc_pages[doc]}
    rebuilt = [sha_to_page[h] for h in shown]
    seen_ok &= rebuilt == item["pages_seen"] and len(set(rebuilt)) == len(rebuilt)
    limits_ok &= len(own) <= 6 and len(rebuilt) <= 12 and all(len(c.get("pages_shown") or []) <= 4 for c in own)
    forced_ok &= all((c["request"]["tool_choice"] != "required") == (c["call_index"] == 6 or c["forced_finish"]) for c in own)
    for c in own:
        if c.get("action") == "search":
            args = json.loads(c["tool_calls"][0]["function"]["arguments"])
            emb = bf16_safetensors(QUERY_CACHE / f"{sha(args['query'].strip().encode())}.safetensors")
            if doc not in page_cache:
                page_cache[doc] = {p: bf16_safetensors(E5_CACHE / "pages" / f"{manifest.at[(doc, p), 'sha256']}.safetensors") for p in doc_pages[doc]}
            scored = sorted(((p, float((emb @ e.T).max(axis=1).sum())) for p, e in page_cache[doc].items()), key=lambda x: (-x[1], x[0]))
            step = next(s for s in item["steps"] if s.get("call") == c["call_index"])
            search_total += 1
            search_equal += [p for p, _ in scored[:8]] == step["results"]
check("every agent episode starts with B1's exact top 4 page images", warm_ok)
check("pages seen, rebuilt from the logged requests, equal the recorded pages seen", seen_ok)
check("limits held: <= 6 calls, <= 12 distinct pages, <= 4 pages per read", limits_ok)
check("tool_choice was 'required' except on forced finishes", forced_ok)
check("every search result is reproduced from the cached query embedding and E5's page embeddings (numpy, no torch)",
      search_equal == search_total, searches=search_total, equal=search_equal)

# 7. S-v1 with notebook 03's frozen scorer cell, executed in its own namespace.
nb03 = json.loads((ROOT / "notebooks" / "03_evaluation.ipynb").read_text())
cell = next("".join(c["source"]) for c in nb03["cells"] if c.get("id") == "f653d232")
tree = ast.parse(cell)
keep = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.Import, ast.ImportFrom))
        or (isinstance(n, ast.Assign) and getattr(n.targets[0], "id", None) == "EXACT_MATCH_PATTERNS")]
ns = {"re": re, "ast": ast, "isclose": isclose}
exec(compile(ast.Module(body=keep, type_ignores=[]), "nb03_f653d232", "exec"), ns)
eval_score = ns["eval_score"]
rows = []
for item in ok_items:
    qid = item["qid"]
    s1 = eval_score(q.at[qid, "answer"], item["answer"], q.at[qid, "answer_format"])
    ev = [int(p) for p in q.at[qid, "evidence_pages"]]
    rows.append({"qid": qid, "doc": q.at[qid, "doc_id"], "arm": item["arm"], "answerable": q.at[qid, "answer_format"] != "None",
                 "correct": s1 > 0, "abstained": item["answer"] == NA,
                 "cit": item["parse_error"] is None and set(item["cited_pages"]) <= set(item["pages_seen"]) and (item["answer"] == NA or bool(item["cited_pages"])),
                 "recall": len(set(ev) & set(item["pages_seen"])) / len(set(ev)) if ev and q.at[qid, "answer_format"] != "None" else np.nan})
s = pd.DataFrame(rows)
summary = json.loads((PKG / "tables" / "evaluation_summary.json").read_text())
arms = summary["arms"]
for arm in ("B1s", "AGa", "AGb"):
    f = s[s.arm == arm]
    mine = {"S-v1 correct / 102": int(f[f.answerable].correct.sum()), "correct abstentions / 16": int(f[~f.answerable].abstained.sum()),
            "citation validity": round(float(f.cit.mean()), 6)}
    theirs = {k: arms[arm][k] for k in mine}
    check(f"{arm}: S-v1 correct, abstentions and citation validity reproduced", all(isclose(mine[k], theirs[k], abs_tol=1e-6) for k in mine), mine=mine)

ans = s[s.answerable].pivot(index="qid", columns="arm", values="correct").astype(float).sort_index()
ag, b1s = (ans.AGa + ans.AGb) / 2, ans.B1s
diff = ag - b1s
docs = q.loc[diff.index, "doc_id"].to_numpy()
order = sorted(set(docs))
sums = np.array([diff[docs == d].sum() for d in order])
counts = np.array([(docs == d).sum() for d in order])
picks = np.random.default_rng(20261128).integers(0, len(order), size=(10_000, len(order)))
boot = sums[picks].sum(axis=1) / counts[picks].sum(axis=1)
signs = np.array([[1 if (m >> i) & 1 else -1 for i in range(len(order))] for m in range(2 ** len(order))])
p_flip = float(np.mean(signs @ sums >= sums.sum() - 1e-12))
dec = summary["decision"]
FACTS["primary"] = {"delta": round(float(diff.mean()), 6), "ci95": [round(float(x), 6) for x in np.percentile(boot, [2.5, 97.5])],
                    "sign_flip_p": round(p_flip, 6)}
check("primary contrast AG - B1s reproduced (delta, 95 % interval, exact sign-flip p)",
      isclose(diff.mean(), dec["delta"], abs_tol=5e-5) and all(isclose(a, b, abs_tol=5e-5) for a, b in zip(np.percentile(boot, [2.5, 97.5]), dec["ci95"]))
      and isclose(p_flip, dec["sign-flip p"], abs_tol=1e-5), **FACTS["primary"])
fb = {rep: {"fixed": int(((ans[rep] == 1) & (b1s == 0)).sum()), "broken": int(((ans[rep] == 0) & (b1s == 1)).sum())} for rep in ("AGa", "AGb")}
check("fixed / broken per replicate reproduced", all(fb[r]["fixed"] == dec["per replicate"][r]["fixed"] and fb[r]["broken"] == dec["per replicate"][r]["broken"] for r in fb), **fb)
rec = s[s.recall.notna()].pivot(index="qid", columns="arm", values="recall")  # answerable questions with annotated evidence
FACTS["evidence_population"] = int(len(rec))
FACTS["evidence_recall_seen"] = {arm: round(float(rec[arm].mean()), 6) for arm in ("B1s", "AGa", "AGb")}
check("evidence recall of pages seen reproduced", all(isclose(FACTS["evidence_recall_seen"][a], arms[a]["evidence recall of pages seen (101)"], abs_tol=1e-6) for a in FACTS["evidence_recall_seen"]),
      **FACTS["evidence_recall_seen"])
check("verdict recorded", isinstance(dec["VERDICT (S-v1, frozen rules)"], str), verdict=dec["VERDICT (S-v1, frozen rules)"])

passed = sum(c["passed"] for c in CHECKS)
report = {"audit": "E10 independent audit", "run": RUN.name, "smoke": [x.name for x in smokes], "passed": passed, "total": len(CHECKS),
          "all_checks_passed": passed == len(CHECKS), "facts": FACTS, "checks": CHECKS}
(OUT / "AUDIT.json").write_text(json.dumps(report, indent=2, default=str) + "\n")
print(f"{passed}/{len(CHECKS)} checks passed -> {OUT / 'AUDIT.json'}")
