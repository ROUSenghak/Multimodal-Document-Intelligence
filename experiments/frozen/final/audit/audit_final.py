#!/usr/bin/env python
"""Independent, read-only audit of the final held-out evaluation (notebook 09, spec final_evaluation_v1).

Usage:  python audit_final.py [REPO_ROOT] [OUT_DIR] [--skip-maxsim]
  REPO_ROOT defaults to the first parent of the current directory holding pyproject.toml and AGENTS.md.
  OUT_DIR defaults to this script's directory. Writes audit_final.json there and nothing else.

Never calls an API, never writes to the repository, and prints/writes no question, answer, evidence or reply text:
only ids, counts, hashes and statistics. No per-question error analysis is done.
"""
import ast
import hashlib
import json
import math
import re
import subprocess
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from math import ceil, floor, isclose
from pathlib import Path

import numpy as np
import pandas as pd

T0 = time.time()
ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
FLAGS = {a for a in sys.argv[1:] if a.startswith("--")}


def find_root(start):
    for c in (start, *start.parents):
        if (c / "pyproject.toml").is_file() and (c / "AGENTS.md").is_file():
            return c
    raise SystemExit("repository root not found (pass it as the first argument)")


ROOT = find_root(Path(ARGS[0]).resolve() if ARGS else Path.cwd().resolve())
OUT = Path(ARGS[1]).resolve() if len(ARGS) > 1 else Path(__file__).resolve().parent
OUT.mkdir(parents=True, exist_ok=True)

SPEC_P = ROOT / "experiments/specs/final_evaluation_v1.json"
DEV_P = ROOT / "experiments/specs/final_evaluation_v1_deviations.md"
PLAN_P = ROOT / "experiments/specs/final_evaluation_v1_plan.json"
FIDX = ROOT / "experiments/frozen/final_index"
FRET = ROOT / "experiments/frozen/final_retrieval"
FINAL = ROOT / "data/processed/mmlongbench_doc/final"
RUN = sorted((ROOT / "experiments/runs/final").glob("*_full"))
SMOKE = sorted((ROOT / "experiments/runs/final_smoke").glob("*_smoke"))
NB09 = ROOT / "notebooks/09_final_evaluation.ipynb"
NB07 = ROOT / "notebooks/07_baseline_consolidation.ipynb"
NB03 = ROOT / "notebooks/03_evaluation.ipynb"
E8_LOG = ROOT / "experiments/frozen/e8/run_20261125T140433934010Z_4edb90e7_full/execution_log.jsonl"
NA = "Not answerable"
PRICE = {"input": 0.10 / 1e6, "cached_input": 0.01 / 1e6, "output": 0.50 / 1e6}
CLAIMED = {  # the numbers the brief asks to reproduce (rounded as stated there)
    "C1 B1 correct": 288, "C1 B1 n": 674, "C1 B1 accuracy": 0.4273, "C1 CI low": 0.3858, "C1 CI high": 0.4697,
    "C1 core correct": 77, "C1 core n": 207, "C1 core accuracy": 0.372, "C1 core CI low": 0.305, "C1 core CI high": 0.443,
    "C2 delta": 0.1187, "C2 CI low": 0.0883, "C2 CI high": 0.1499, "C2 p05": 0.0926, "C2 sign-flip p": 1e-05, "C2 fixed": 103, "C2 broken": 23,
    "C3 delta": 0.0208, "C3 CI low": 0.0072, "C3 CI high": 0.0361, "C3 sign-flip p": 0.00463, "C3 fixed": 19, "C3 broken": 5,
    "B1 correct": 288, "T1 correct": 208, "A1 correct": 302, "F8 correct": 84, "F8 answerable": 259,
    "B1 abstentions": 120, "T1 abstentions": 140, "A1 abstentions": 121, "unanswerable": 198,
    "B1 citation validity": 1.0, "T1 citation validity": 0.9954, "observed cost USD": 0.99023348, "smoke cost USD": 0.003216,
    "D2 reply not numeric": 2, "D2 reference not numeric": 0,
    "S-v2 B1-T1 low": 0.0772, "S-v2 B1-T1 high": 0.1499, "S-v2 A1-B1 low": 0.0148, "S-v2 A1-B1 high": 0.0282, "S-v2 pending items": 85,
    "V recall@4": 0.711, "BM25 recall@4": 0.543, "retrieval questions": 666,
}

checks, repro, robustness, notes = [], [], {}, []


def check(name, passed, **details):
    checks.append({"name": name, "passed": bool(passed), "details": details})
    print(f"[{'PASS' if passed else 'FAIL'}] {name}  {json.dumps(details, default=str)[:300]}", flush=True)


def git(*args, check_rc=True):
    r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True)
    if check_rc and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {r.stderr.decode()[:200]}")
    return r.stdout


def git_rc(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True).returncode


def sha256b(b):
    return hashlib.sha256(b).hexdigest()


def sha256f(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for blk in iter(lambda: f.read(1 << 24), b""):
            h.update(blk)
    return h.hexdigest()


def read_jsonl(p):
    return [json.loads(l) for l in Path(p).read_text().splitlines() if l.strip()]


def nb_cells(source_bytes):
    return {c.get("id"): c for c in json.loads(source_bytes)["cells"]}


def cell_src(c):
    return "".join(c["source"])


def cell_out(c):
    t = ""
    for o in c.get("outputs", []):
        if "text" in o:
            t += "".join(o["text"])
        elif "data" in o and "text/plain" in o["data"]:
            t += "".join(o["data"]["text/plain"])
    return t


def committed_clean(path):
    rel = str(Path(path).relative_to(ROOT))
    tracked = bool(git("ls-files", "--", rel).strip())
    unchanged = git_rc("diff", "--quiet", "HEAD", "--", rel) == 0
    untracked = git("ls-files", "--others", "--exclude-standard", "--", rel).strip()
    return tracked and unchanged and not untracked


def commits_touching(rel):
    return git("log", "--format=%h", "--", rel).decode().split()


# ======================================================================================================
# 1. Integrity and provenance
# ======================================================================================================
SPEC = json.loads(SPEC_P.read_text())
PLAN_SPEC = json.loads(PLAN_P.read_text())
HEAD = git("rev-parse", "--short=7", "HEAD").decode().strip()

check("1.01 spec equals its freeze commit 1c54a3e and is unchanged at HEAD",
      git("show", "1c54a3e:experiments/specs/final_evaluation_v1.json") == SPEC_P.read_bytes() and committed_clean(SPEC_P)
      and commits_touching("experiments/specs/final_evaluation_v1.json") == ["1c54a3e"],
      commits=commits_touching("experiments/specs/final_evaluation_v1.json"), sha256=sha256f(SPEC_P))
check("1.02 deviations file committed and unchanged at HEAD (D1 then D2)", committed_clean(DEV_P),
      commits=commits_touching("experiments/specs/final_evaluation_v1_deviations.md"))
check("1.03 plan spec committed once (8d5768a) and unchanged",
      committed_clean(PLAN_P) and commits_touching("experiments/specs/final_evaluation_v1_plan.json") == ["8d5768a"],
      commits=commits_touching("experiments/specs/final_evaluation_v1_plan.json"), sha256=sha256f(PLAN_P))


def sums_ok(folder):
    bad = []
    for line in (folder / "SHA256SUMS").read_text().splitlines():
        if line.strip():
            digest, name = line.split(maxsplit=1)
            if sha256f(folder / name.strip()) != digest:
                bad.append(name.strip())
    listed = {l.split(maxsplit=1)[1].strip() for l in (folder / "SHA256SUMS").read_text().splitlines() if l.strip()}
    on_disk = {p.name for p in folder.iterdir() if p.is_file()} - {"SHA256SUMS"}
    return bad, sorted(on_disk - listed)


for folder, commit in ((FIDX, "ab8a9c8"), (FRET, "8d5768a")):
    bad, unlisted = sums_ok(folder)
    rel = str(folder.relative_to(ROOT))
    check(f"1.04 {rel}: committed in {commit} only, clean, SHA256SUMS valid", not bad and not unlisted and committed_clean(folder)
          and commits_touching(rel) == [commit], bad=bad, unlisted=unlisted, commits=commits_touching(rel))

# processed copies equal frozen copies
same = {n: sha256f(FIDX / n) == sha256f(FINAL / n) for n in ("index_manifest.csv", "pool_documents.csv", "parity_gate.json")}
same["rankings.parquet"] = sha256f(FRET / "rankings.parquet") == sha256f(FINAL / "rankings.parquet")
check("1.05 working copies in data/processed/.../final equal the frozen packages", all(same.values()), **same)

# Git ordering
anc = lambda a, b: git_rc("merge-base", "--is-ancestor", a, b) == 0
chain = ["1c54a3e", "dfeaad0", "476b156", "ab8a9c8", "8d5768a", "de38422", "61f769f", "bcf0345"]
ordered = all(anc(a, b) for a, b in zip(chain, chain[1:])) and anc("bcf0345", "HEAD")
first_question_commit = commits_touching("experiments/frozen/final_retrieval")[-1]
pre_index = git("show", "ab8a9c8:notebooks/09_final_evaluation.ipynb")
pre_q_out = cell_out(nb_cells(pre_index)["fe-questions"])
idx_summary = json.loads((FIDX / "index_summary.json").read_text())
check("1.06 index frozen (ab8a9c8) before the first commit carrying question-derived files (final_retrieval, plan)",
      ordered and first_question_commit == "8d5768a" and anc("ab8a9c8", first_question_commit) and "Questions unread" in pre_q_out
      and idx_summary.get("questions_read") is False,
      chain=chain, first_question_derived_commit=first_question_commit, index_summary_questions_read=idx_summary.get("questions_read"),
      notebook_at_ab8a9c8_fe_questions_output="Questions unread" in pre_q_out)

# The evaluation and scorer code was fixed before any question was read (f0122c9) and unchanged up to the run commit.
EVAL_CELLS = ["fe-scorer-prelude", "fe-scorer-v1", "fe-scorer-v2", "fe-scorer-check", "fe-eval", "fe-requests", "fe-plan", "fe-executor", "fe-run"]
c_pre =nb_cells(git("show", "f0122c9:notebooks/09_final_evaluation.ipynb"))
c_run = nb_cells(git("show", "61f769f:notebooks/09_final_evaluation.ipynb"))
c_d2 = nb_cells(git("show", "bcf0345:notebooks/09_final_evaluation.ipynb"))
c_wt = nb_cells(NB09.read_bytes())
changed_pre_run = [k for k in EVAL_CELLS if cell_src(c_pre[k]) != cell_src(c_run[k])]
check("1.07 scoring, claims, request, plan and executor cells identical from f0122c9 (before questions) to the run commit 61f769f",
      not changed_pre_run, changed=changed_pre_run)

# D2: only D2 cells changed, D2-only lines in fe-eval; worktree code equals bcf0345; no committed evaluation output.
import difflib
changed_run_d2 = sorted(k for k in set(c_run) | set(c_d2) if cell_src(c_run.get(k, {"source": []})) != cell_src(c_d2.get(k, {"source": []})))
diff_lines = [l for l in difflib.unified_diff(cell_src(c_run["fe-eval"]).splitlines(), cell_src(c_d2["fe-eval"]).splitlines(), lineterm="", n=0)
              if l[:1] in "+-" and not l.startswith(("+++", "---"))]


def strip_d2(src):
    """Remove exactly the D2 additions from the bcf0345 fe-eval; what remains must equal the run commit's fe-eval."""
    src = src.replace("  # D2 wrapper; the kind of exception, if any, is kept per reply", "").replace('"s1_exception": s1_exception, ', "")
    lines = [l for l in src.splitlines() if "s1_exception = s1_exception_kind" not in l and '"D2_' not in l]
    return "\n".join(lines).replace('"observed_cost_usd": float(paid["cost_usd"].sum()),\n', '"observed_cost_usd": float(paid["cost_usd"].sum())}\n')


non_d2_lines = [] if strip_d2(cell_src(c_d2["fe-eval"])) == cell_src(c_run["fe-eval"]) else diff_lines
wt_changed = sorted(k for k in set(c_wt) | set(c_d2) if cell_src(c_wt.get(k, {"source": []})) != cell_src(c_d2.get(k, {"source": []})))
nb_commits = commits_touching("notebooks/09_final_evaluation.ipynb")
eval_outputs_committed = []
for c in nb_commits:
    out = cell_out(nb_cells(git("show", f"{c}:notebooks/09_final_evaluation.ipynb")).get("fe-eval", {"outputs": []}))
    if out.strip() and "No completed final run" not in out:
        eval_outputs_committed.append(c)
tracked_outputs = git("ls-files", "--", "data/processed/mmlongbench_doc/final", "experiments/frozen/final", "experiments/runs").decode().split()
run_log = read_jsonl(RUN[0] / "execution_log.jsonl")
run_end = max(datetime.fromisoformat(r["completed_at"]) for r in run_log)
d2_time = datetime.fromisoformat(git("show", "-s", "--format=%cI", "bcf0345").decode().strip())
eval_mtime = datetime.fromtimestamp((FINAL / "evaluation_summary.json").stat().st_mtime, tz=timezone.utc)
check("1.08 D2 (bcf0345) committed after the run ended and before any evaluation output; only D2 code changed; nothing evaluated is committed",
      changed_run_d2 == ["fe-eval", "fe-scorer-d2", "fe-scorer-d2-md"] and not non_d2_lines and not wt_changed and not eval_outputs_committed
      and not tracked_outputs and run_end < d2_time < eval_mtime,
      cells_changed_by_d2=changed_run_d2, non_d2_diff_lines=len(non_d2_lines), worktree_code_vs_bcf0345=wt_changed,
      commits_with_eval_output=eval_outputs_committed, tracked_eval_files=len(tracked_outputs),
      run_end_utc=run_end.isoformat(), d2_commit=d2_time.isoformat(), evaluation_summary_mtime_utc=eval_mtime.isoformat(),
      note="eval-output mtime is file-system evidence only (not cryptographic)")

# Settings and plan hashes
assert len(RUN) == 1, f"expected one full run directory, found {len(RUN)}"
settings = json.loads((RUN[0] / "settings.json").read_text())
plan = settings["plan"]
plan_hash = sha256b(json.dumps(plan, sort_keys=True).encode())
pdesign = json.loads((FINAL / "plan_design.json").read_text())
tot_prompt = sum(i["prompt_tokens"] for i in plan)
tot_out = sum(i["max_completion_tokens"] for i in plan)
upper = round(tot_prompt * PRICE["input"] + tot_out * PRICE["output"], 6)
check("1.09 settings: spec/plan-spec hashes, plan hash = plan spec full.plan_sha256, totals equal the frozen plan",
      settings["spec_sha256"] == sha256f(SPEC_P) and settings["plan_spec_sha256"] == sha256f(PLAN_P)
      and plan_hash == PLAN_SPEC["full"]["plan_sha256"] and len(plan) == PLAN_SPEC["full"]["calls"] == 2079
      and tot_prompt == PLAN_SPEC["full"]["prompt_tokens"] and tot_out == PLAN_SPEC["full"]["max_output_tokens"]
      and upper == PLAN_SPEC["full"]["upper_usd"] and dict(Counter(i["arm"] for i in plan)) == PLAN_SPEC["full"]["arms"]
      and pdesign["full_plan"] == plan and {k: v for k, v in pdesign.items() if k not in ("smoke_plan", "full_plan")} == PLAN_SPEC
      and settings["git_commit"].startswith("61f769f") and PLAN_SPEC["spec_commit"] == "1c54a3e"
      and PLAN_SPEC["index_manifest_sha256"] == sha256f(FIDX / "index_manifest.csv"),
      plan_sha256=plan_hash, run_commit=settings["git_commit"][:7], plan_upper_usd=upper, prompt_tokens=tot_prompt)

# ======================================================================================================
# 2. Population (questions are read here for scoring only; nothing textual is printed)
# ======================================================================================================
doc_list = json.loads((ROOT / "resources/mmlongbench_doc_documents.json").read_text())
ALL = sorted(doc_list["documents"])
e5spec = json.loads((ROOT / "experiments/specs/e5_visual_retrieval_v1.json").read_text())
HELD14 = sorted(e5spec["populations"]["held_out"]["selected_documents"])
DEV6 = sorted(pd.read_csv(ROOT / "experiments/frozen/e5/tables/per_question.csv").query("population == 'development'")["doc_id"].unique())
TOUCHED = sorted(SPEC["population"]["excluded_touched_documents"])
ledger = (ROOT / "experiments/test_pool_ledger.md").read_text()
ledger_touched = sorted(set(re.findall(r"^\s+- `([^`]+\.pdf)`", ledger.split("## Consequences")[1], re.M)))
POOL = sorted(set(ALL) - set(HELD14) - set(DEV6) - set(TOUCHED))
pdocs = pd.read_csv(FIDX / "pool_documents.csv")
EVAL_DOCS = sorted(pdocs.loc[pdocs["verified"] & (pdocs["pages"] >= 1) & (pdocs["encrypted"] != True), "doc_id"])
raw_path = ROOT / "data/external/mmlongbench_doc/data/train-00000-of-00001.parquet"
allq = pd.read_parquet(ROOT / "data/processed/mmlongbench_doc/questions.parquet")
raw = pd.read_parquet(raw_path)
raw.insert(0, "qid", [f"mmlb-{i:04d}" for i in raw.index])
pool_q = allq[allq["doc_id"].isin(EVAL_DOCS)].set_index("qid").copy()
pool_q["evidence_pages"] = pool_q["evidence_pages"].map(lambda ps: [int(p) for p in ps])
rawp = raw.set_index("qid").loc[pool_q.index]
raw_equal = all((rawp[c].astype(str) == pool_q[c].astype(str)).all() for c in ("doc_id", "doc_type", "question", "answer", "answer_format")) \
    and all(ast.literal_eval(a) == list(b) for a, b in zip(rawp["evidence_pages"], pool_q["evidence_pages"]))
dev_docs_in_pool = sorted(set(pool_q["doc_id"]) & (set(HELD14) | set(DEV6) | set(TOUCHED)))
check("2.01 population: 135 - 20 development - 4 touched = 111; 110 verified (mi_phone.pdf excluded, D1)",
      len(ALL) == 135 and len(HELD14) == 14 and len(DEV6) == 6 and len(set(HELD14) | set(DEV6)) == 20 and len(POOL) == 111
      and sorted(pdocs["doc_id"]) == POOL and len(EVAL_DOCS) == 110 and set(POOL) - set(EVAL_DOCS) == {"mi_phone.pdf"}
      and TOUCHED == ledger_touched and doc_list["revision"] == SPEC["population"]["revision"],
      pool=len(POOL), verified=len(EVAL_DOCS), excluded=sorted(set(POOL) - set(EVAL_DOCS)), ledger_touched_equals_spec=TOUCHED == ledger_touched)
check("2.02 questions: 872 in 110 documents, 674 answerable / 198 unanswerable, no development or touched document, references equal the git-tracked raw table",
      len(pool_q) == 872 and pool_q.index.is_unique and pool_q["doc_id"].nunique() == 110 and int(pool_q["answerable"].sum()) == 674
      and not dev_docs_in_pool and "mi_phone.pdf" not in set(pool_q["doc_id"]) and raw_equal and committed_clean(raw_path)
      and (pool_q["answerable"] == (pool_q["answer"] != NA)).all() and (pool_q.loc[~pool_q["answerable"], "answer_format"] == "None").all(),
      questions=len(pool_q), documents=int(pool_q["doc_id"].nunique()), answerable=int(pool_q["answerable"].sum()),
      dev_or_touched_docs_included=dev_docs_in_pool, equal_to_raw_tracked_table=raw_equal)
qman = pd.read_csv(FRET / "query_manifest.csv").set_index("qid")
check("2.03 frozen query manifest covers exactly these 872 questions with matching question-text hashes",
      set(qman.index) == set(pool_q.index) and all(qman.at[q, "question_sha256"] == sha256b(pool_q.at[q, "question"].encode()) for q in pool_q.index),
      rows=len(qman))

# D1: the local PDF bytes of the 110 evaluated documents still equal the hashes recorded at the pinned revision (no download:
# iCloud 'dataless' placeholders are skipped, never read, because reading one would fetch it over the network).
import os
PDF_DIR = ROOT / "data/external/mmlongbench_doc/documents"
MAN_PAGES = pd.read_csv(FIDX / "index_manifest.csv").groupby("doc_id").size().to_dict()
pdf_ok, pdf_skipped, pdf_bad, pages_ok = 0, [], [], 0
try:
    import pymupdf
except ImportError:
    pymupdf = None
for r in pdocs[pdocs["doc_id"].isin(EVAL_DOCS)].itertuples():
    p = PDF_DIR / r.doc_id
    if not p.is_file() or (getattr(os.stat(p), "st_flags", 0) & 0x40000000):
        pdf_skipped.append(r.doc_id)
        continue
    if r.hash_kind == "sha256":
        h = sha256f(p)
    else:
        data = p.read_bytes()
        h = hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()
    if h == r.recorded_hash == r.local_hash:
        pdf_ok += 1
    else:
        pdf_bad.append(r.doc_id)
    if pymupdf is not None:
        with pymupdf.open(p) as pdf:
            pages_ok += pdf.page_count == r.pages == MAN_PAGES[r.doc_id]
check("2.04 D1: every evaluated PDF available locally hashes to the revision's recorded hash (LFS SHA-256 or git blob SHA-1); page counts = manifest",
      not pdf_bad and pdf_ok + len(pdf_skipped) == 110 and (pymupdf is None or pages_ok == pdf_ok), verified=pdf_ok, page_counts_ok=pages_ok,
      skipped_dataless_or_missing=len(pdf_skipped), mismatched=pdf_bad,
      kinds=dict(Counter(pdocs.loc[pdocs["doc_id"].isin(EVAL_DOCS), "hash_kind"])))

# ======================================================================================================
# 1 (cont.). Log, requests, rankings
# ======================================================================================================
RK = pd.read_parquet(FRET / "rankings.parquet")
manifest = pd.read_csv(FIDX / "index_manifest.csv")
mpages = manifest.groupby("doc_id")["page"].apply(lambda s: sorted(int(x) for x in s))
img_sha = {(d, int(p)): s for d, p, s in zip(manifest["doc_id"], manifest["page"], manifest["sha256"])}
rk_ok = all(RK.at[q, "doc_id"] == pool_q.at[q, "doc_id"] and RK.at[q, "n_pages"] == len(mpages[RK.at[q, "doc_id"]])
            and sorted(RK.at[q, "V_pages"]) == mpages[RK.at[q, "doc_id"]] == sorted(RK.at[q, "A_pages"])
            and all(a >= b for a, b in zip(RK.at[q, "V_scores"], RK.at[q, "V_scores"][1:]))
            and all(a >= b for a, b in zip(RK.at[q, "A_scores"], RK.at[q, "A_scores"][1:])) for q in pool_q.index) and set(RK.index) == set(pool_q.index)
k = RK["n_pages"].clip(upper=8)
u3 = np.array([-(s[0] - s[kk - 1]) / s[0] for s, kk in zip(RK["V_scores"], k)])
trig = (RK["n_pages"] > 4).to_numpy() & (u3 >= -0.153079)
check("1.10 frozen rankings: full best-first rankings of every page; U3 trigger recomputed = frozen flag (335)",
      rk_ok and (trig == RK["triggered"].to_numpy()).all() and np.allclose(u3, RK["U3"].to_numpy(), rtol=0, atol=1e-12) and int(trig.sum()) == 335
      and (pool_docs_pages := pdocs.set_index("doc_id").loc[EVAL_DOCS, "pages"].to_dict()) == {d: len(mpages[d]) for d in EVAL_DOCS},
      triggered=int(trig.sum()), triggered_answerable=int((trig & pool_q.loc[RK.index, "answerable"].to_numpy()).sum()))
TRIG = dict(zip(RK.index, trig))

# Seeded order reconstruction
rng = np.random.default_rng(20261201)
qids = sorted(pool_q.index)
rng.shuffle(qids)
expected_order = []
for q in qids:
    arms = [a for a in ("B1", "T1", "F8") if a != "F8" or TRIG[q]]
    expected_order += [(q, a) for a in rng.permutation(arms).tolist()]
check("1.11 plan order equals the seeded order (seed 20261201) with F8 exactly for triggered questions",
      expected_order == [(i["qid"], i["arm"]) for i in plan] and [i["execution_index"] for i in plan] == list(range(1, 2080)),
      calls=len(expected_order))

# Log records
by_index = {i["execution_index"]: i for i in plan}
idx_counts = Counter(r["execution_index"] for r in run_log)
fp_ok = sum(sha256b(json.dumps(r["request"], sort_keys=True).encode()) == r["fingerprint"] == by_index[r["execution_index"]]["fingerprint"] for r in run_log)
field_ok = sum(all(r[f] == by_index[r["execution_index"]][f] for f in ("qid", "arm", "source", "replicate_id", "max_completion_tokens")) for r in run_log)
check("1.12 execution log: 2079 records, 2079 unique indices, one attempt each, all ok, fingerprints = sha256(json.dumps(request, sort_keys=True)) = plan",
      len(run_log) == 2079 and set(idx_counts) == set(range(1, 2080)) and max(idx_counts.values()) == 1
      and all(r["attempt"] == 1 and r["status"] == "ok" for r in run_log) and fp_ok == 2079 and field_ok == 2079,
      records=len(run_log), unique_indices=len(idx_counts), fingerprints_ok=fp_ok, plan_fields_ok=field_ok,
      statuses=dict(Counter(r["status"] for r in run_log)))

# Requests
e8 = [r for r in read_jsonl(E8_LOG) if r["arm"] == "L-B1"]
TEMPLATE = sorted(e8, key=lambda r: r["qid"])[0]["request"]
TPARAMS = {k: v for k, v in TEMPLATE.items() if k != "messages"}
QRE = re.compile(r"\AQuestion: (.*)\n\nPage images:\Z", re.S)
TAG = re.compile(r"\A\[Page (\d+)\]\Z")
problems = Counter()
for r in run_log:
    req, q, arm = r["request"], r["qid"], r["arm"]
    doc = pool_q.at[q, "doc_id"]
    if {k: v for k, v in req.items() if k != "messages"} != TPARAMS:
        problems["params differ from E8 L-B1 template"] += 1
    msgs = req["messages"]
    if len(msgs) != 2 or msgs[0] != TEMPLATE["messages"][0] or msgs[1]["role"] != "user":
        problems["message layout / system prompt"] += 1
        continue
    parts = msgs[1]["content"]
    m = QRE.match(parts[0].get("text", "")) if parts and parts[0]["type"] == "text" else None
    if not m or sha256b(m.group(1).encode()) != sha256b(pool_q.at[q, "question"].encode()):
        problems["question text differs from questions.parquet"] += 1
    pages = []
    for tag, img in zip(parts[1::2], parts[2::2]):
        t = TAG.match(tag.get("text", "")) if tag["type"] == "text" else None
        if not t or img["type"] != "image":
            problems["page/tag layout"] += 1
            break
        p = int(t.group(1))
        pages.append(p)
        if img["sha256"] != img_sha[(doc, p)]:
            problems["image hash differs from the index manifest page"] += 1
        if img.get("detail") != "high":
            problems["image detail not high"] += 1
    if len(parts) != 1 + 2 * len(pages):
        problems["trailing parts"] += 1
    expected = {"B1": RK.at[q, "V_pages"][:4], "T1": RK.at[q, "A_pages"][:4], "F8": RK.at[q, "V_pages"][:8]}[arm]
    if pages != [int(x) for x in expected]:
        problems[f"{arm} pages differ from the frozen ranking"] += 1
    if arm == "F8" and not TRIG[q]:
        problems["F8 on an untriggered question"] += 1
arms_per_q = defaultdict(set)
for r in run_log:
    arms_per_q[r["qid"]].add(r["arm"])
coverage = all(arms_per_q[q] == ({"B1", "T1", "F8"} if TRIG[q] else {"B1", "T1"}) for q in pool_q.index)
check("1.13 requests: page tags and images equal the frozen rankings in order (B1 V top4, T1 BM25 top4, F8 V top8), F8 only and always when triggered, "
      "question text and system prompt and parameters equal the frozen template",
      not problems and coverage and TPARAMS == {"model": "gpt-6-luna", "response_format": TPARAMS["response_format"], "max_completion_tokens": 800,
                                               "reasoning_effort": "none", "temperature": 0}
      and TPARAMS["response_format"]["type"] == "json_schema" and TPARAMS["response_format"]["json_schema"]["strict"] is True,
      problems=dict(problems), coverage=coverage, params=sorted(TPARAMS))


# Reader identity, parse, tokens, cost
def page_number(v):
    if isinstance(v, bool):
        raise ValueError
    if isinstance(v, int):
        n = v
    elif isinstance(v, float) and v.is_integer():
        n = int(v)
    elif isinstance(v, str) and v.isascii() and v.isdigit():
        n = int(v)
    else:
        raise ValueError
    if n < 1:
        raise ValueError
    return n


def parse_reply(raw_text):
    """The B1 contract, re-implemented: exactly answer/cited_pages/evidence; abstention canonicalised and without citations."""
    try:
        d = json.loads(raw_text)
        if not isinstance(d, dict) or set(d) != {"answer", "cited_pages", "evidence"}:
            return None
        sc = lambda v: isinstance(v, (str, int, float)) and not isinstance(v, bool)
        a = d["answer"]
        if not (sc(a) or (isinstance(a, list) and all(sc(x) for x in a))):
            return None
        if not isinstance(d["cited_pages"], list) or not isinstance(d["evidence"], list):
            return None
        cited = [page_number(p) for p in d["cited_pages"]]
        ev = []
        for it in d["evidence"]:
            if not isinstance(it, dict) or set(it) != {"page", "quote"} or not isinstance(it["quote"], str):
                return None
            ev.append({"page": page_number(it["page"]), "quote": it["quote"]})
        if isinstance(a, str) and a.strip().lower() == "not answerable":
            a = NA
        if a == NA and (cited or ev):
            return None
        return {"answer": a, "cited_pages": cited, "evidence": ev}
    except (ValueError, TypeError, KeyError):
        return None


parse_mismatch = sum(parse_reply(r["raw_response"]) != r["parsed"] for r in run_log)
check("1.14 reader: served model only gpt-6-luna, one system fingerprint, finish_reason stop, no parse error, re-parse of every raw reply = stored parse",
      {r["served_model"] for r in run_log} == {"gpt-6-luna"} and len({r["system_fingerprint"] for r in run_log}) == 1
      and all(r["finish_reason"] == "stop" and r["parse_error"] is None for r in run_log) and parse_mismatch == 0,
      served_models=sorted({r["served_model"] for r in run_log}), system_fingerprints=sorted(map(str, {r["system_fingerprint"] for r in run_log})),
      reparse_mismatches=parse_mismatch)

import tiktoken
ENC = tiktoken.get_encoding("o200k_base")


def token_model(logged):
    texts, dims = [], []
    for msg in logged["messages"]:
        for part in ([{"type": "text", "text": msg["content"]}] if isinstance(msg["content"], str) else msg["content"]):
            if part["type"] == "text":
                texts.append(part["text"])
            elif part["type"] == "image":
                dims.append(tuple(part["dimensions"]))
    return sum(len(ENC.encode(t)) for t in texts) + (9 if dims else 10) + (100 if logged["response_format"]["type"] == "json_schema" else 0) \
        + sum(floor(1.2 * ceil(w / 32) * ceil(h / 32)) for w, h in dims)


billed_eq = sum(r["prompt_tokens"] == by_index[r["execution_index"]]["prompt_tokens"] for r in run_log)
model_eq = sum(token_model(r["request"]) == by_index[r["execution_index"]]["prompt_tokens"] for r in run_log)
diffs = [r["prompt_tokens"] - by_index[r["execution_index"]]["prompt_tokens"] for r in run_log]
check("1.15 billed prompt tokens equal planned (and the token model) on every call",
      billed_eq == 2079 and model_eq == 2079, billed_equal=billed_eq, token_model_equal=model_eq,
      calls_billed_more=sum(d > 0 for d in diffs), calls_billed_less=sum(d < 0 for d in diffs), extra_tokens=sum(diffs),
      by_arm=dict(Counter(r["arm"] for r, d in zip(run_log, diffs) if d)), questions_affected=len({r["qid"] for r, d in zip(run_log, diffs) if d}),
      billed_prompt_tokens=sum(r["prompt_tokens"] for r in run_log), planned_prompt_tokens=tot_prompt,
      cached_tokens=sum(r["cached_prompt_tokens"] for r in run_log),
      calls_with_cache=sum(r["cached_prompt_tokens"] > 0 for r in run_log), completion_tokens=sum(r["completion_tokens"] for r in run_log))


# Explanation: the token model evaluates floor((1.2 * tiles_w) * tiles_h) left to right in floating point; for 24 x 35 tiles this is
# floor(1007.9999999999999) = 1007, while the exact value is 1008. Count, per call, the images where float and exact arithmetic differ.
def float_artifacts(logged):
    n = 0
    for part in logged["messages"][1]["content"]:
        if part["type"] == "image":
            w, h = part["dimensions"]
            tw, th = ceil(w / 32), ceil(h / 32)
            n += (12 * tw * th) // 10 - floor(1.2 * tw * th)
    return n


explained = sum(float_artifacts(r["request"]) == d for r, d in zip(run_log, diffs))
art_dims = sorted({tuple(p["dimensions"]) for r in run_log for p in r["request"]["messages"][1]["content"]
                   if p["type"] == "image" and (12 * ceil(p["dimensions"][0] / 32) * ceil(p["dimensions"][1] / 32)) // 10
                   != floor(1.2 * ceil(p["dimensions"][0] / 32) * ceil(p["dimensions"][1] / 32))})
check("1.15b every billed-vs-planned difference = 1 token per image whose tile product hits a float-rounding artifact in the token model",
      explained == 2079, calls_explained=explained, artifact_image_dimensions=art_dims,
      cost_effect_usd=round(sum(diffs) * PRICE["input"], 9))


def cost(r):
    p, c = r["prompt_tokens"] or 0, r.get("cached_prompt_tokens") or 0
    return max(0, p - c) * PRICE["input"] + c * PRICE["cached_input"] + r["completion_tokens"] * PRICE["output"]


obs = sum(cost(r) for r in run_log)
summ = json.loads((RUN[0] / "summary.json").read_text())
smoke_log = read_jsonl(SMOKE[0] / "execution_log.jsonl")
smoke_settings = json.loads((SMOKE[0] / "settings.json").read_text())
smoke_cost = sum(cost(r) for r in smoke_log)
per_rec = max(abs(cost(r) - r["list_price_cost_usd"]) for r in run_log)
check("1.16 cost recomputed at $0.10/1M input, $0.01/1M cached, $0.50/1M output; within the frozen ceilings",
      abs(obs - 0.99023348) < 1e-9 and abs(obs - summ["observed_list_price_cost_usd"]) < 1e-9 and per_rec < 1e-12
      and abs(summ["budget_accounted_usd_including_prior"] - (obs + smoke_cost)) < 1e-9 and obs + smoke_cost <= 2.5 and upper <= 2.4,
      observed_usd=round(obs, 9), smoke_usd=round(smoke_cost, 9), total_usd=round(obs + smoke_cost, 9), max_per_record_diff=per_rec)
dev_qids_heldout = set(allq.loc[allq["doc_id"].isin(HELD14), "qid"])
check("1.17 smoke: 6 calls on development questions only (plan qids), all ok, same model, never scored with the pool",
      len(smoke_log) == 6 and sorted({r["qid"] for r in smoke_log}) == PLAN_SPEC["smoke"]["qids"] and {r["qid"] for r in smoke_log} <= dev_qids_heldout
      and not ({r["qid"] for r in smoke_log} & set(pool_q.index)) and all(r["status"] == "ok" for r in smoke_log)
      and sha256b(json.dumps(smoke_settings["plan"], sort_keys=True).encode()) == PLAN_SPEC["smoke"]["plan_sha256"]
      and all(json.loads((SMOKE[0] / "smoke_gate.json").read_text()).values()),
      calls=len(smoke_log), arms=dict(Counter(r["arm"] for r in smoke_log)))

# ======================================================================================================
# 3. Re-scoring: frozen S-v1 (notebook 03 f653d232) + D2 (own implementation) + S-v2 (notebook 07 b1-scorer-v2)
# ======================================================================================================
nb03 = {c.get("id"): cell_src(c) for c in json.loads(NB03.read_text())["cells"]}
nb07 = {c.get("id"): cell_src(c) for c in json.loads(NB07.read_text())["cells"]}
nb09 = {k: cell_src(v) for k, v in c_wt.items()}
frozen_cell = nb03["f653d232"]
tree = ast.parse(frozen_cell)
f03 = {n.name: ast.get_source_segment(frozen_cell, n) for n in tree.body if isinstance(n, ast.FunctionDef)}
t07 = ast.parse(nb07["b1-scorer-v1"])
f07 = {n.name: ast.get_source_segment(nb07["b1-scorer-v1"], n) for n in t07.body if isinstance(n, ast.FunctionDef)}
NAMES = ["levenshtein_distance", "anls_compute", "is_float_equal", "get_clean_string", "is_exact_match", "isfloat", "as_list", "eval_score"]
check("3.01 scorer provenance: notebook 07/09 S-v1 functions = notebook 03 f653d232; notebook 09 scorer cells = notebook 07 pinned cells",
      all(f03[n].strip() == f07[n].strip() for n in NAMES) and nb09["fe-scorer-v1"] == nb07["b1-scorer-v1"] and nb09["fe-scorer-v2"] == nb07["b1-scorer-v2"]
      and sha256b(nb07["b1-scorer-v2"].encode()) == "902708ba537d580db8c67858fe9a2231e5b546f1538a2b955a3eadff551b8707"
      and sha256b(nb07["b1-scorer-v1"].encode()) == "329f91f3ceda29146ec8a0c2467f11fdf7fdbd66c1e6af29123e1983a3fc7ee7",
      nb03_cell_sha256=sha256b(frozen_cell.encode()))

NS = {"re": re, "ast": ast, "json": json, "isclose": isclose, "pd": pd, "np": np, "NOT_ANSWERABLE": NA, "FROZEN_DIR": ROOT / "experiments/frozen"}
exec(compile(frozen_cell, "nb03_f653d232", "exec"), NS)
FROZEN_EVAL = NS["eval_score"]
clean = NS["get_clean_string"]


def numeric_after_clean(v):
    try:
        float(clean(str(v)))
        return True
    except ValueError:
        return False


def s1_d2(gt, pred, fmt):
    """D2, implemented from the deviations text: only when the frozen function raises on a Float question."""
    try:
        return FROZEN_EVAL(gt, pred, fmt), None
    except Exception:
        if fmt != "Float":
            raise
        if not numeric_after_clean(gt):
            return 0.0, "reference not numeric"
        if not numeric_after_clean(pred):
            return 0.0, "reply not numeric"
        raise


# D2 changes no historical score: the frozen E8/E9 S-v1 tables re-scored with this implementation.
hist_q = allq.set_index("qid")
hist_checked, hist_bad = 0, 0
for package, arms in (("e8", {"L-v1", "L-B1", "L-B1r"}), ("e9", {"B1s", "F8a", "F8b"})):
    log = read_jsonl(next((ROOT / "experiments/frozen" / package).glob("run_*_full")) / "execution_log.jsonl")
    table = pd.read_csv(ROOT / "experiments/frozen" / package / "tables/evaluation_per_question.csv").set_index(["qid", "arm"])["s1_score"]
    for rec in log:
        if rec["arm"] in arms:
            s, kind = s1_d2(hist_q.at[rec["qid"], "answer"], rec["parsed"]["answer"], hist_q.at[rec["qid"], "answer_format"])
            hist_checked += 1
            hist_bad += kind is not None or abs(s - table[(rec["qid"], rec["arm"])]) > 1e-12
check("3.02 own D2 implementation reproduces all frozen E8/E9 S-v1 scores (no exception in development data)",
      hist_checked == 708 and hist_bad == 0, checked=hist_checked, mismatches=hist_bad)

exec(compile(nb07["b1-scorer-v2"], "nb07_b1_scorer_v2", "exec"), NS)  # its own invented-case asserts run here
NS["eval_score"] = lambda gt, pred, fmt: s1_d2(gt, pred, fmt)[0]  # score_v2 resolves eval_score at call time (as notebook 09 does)
score_v2 = NS["score_v2"]
DEBATABLE = NS["DEBATABLE_QIDS"]

# Reference-not-numeric questions: every arm scores 0 (D2)
rows = []
for r in run_log:
    q, arm = r["qid"], r["arm"]
    ans, cited = r["parsed"]["answer"], r["parsed"]["cited_pages"]
    ref, fmt = pool_q.at[q, "answer"], pool_q.at[q, "answer_format"]
    s, kind = s1_d2(ref, ans, fmt)
    v2c, _ = score_v2(ref, ans, fmt, debatable=q in DEBATABLE)
    supplied = {"B1": RK.at[q, "V_pages"][:4], "T1": RK.at[q, "A_pages"][:4], "F8": RK.at[q, "V_pages"][:8]}[arm]
    rows.append({"qid": q, "doc_id": pool_q.at[q, "doc_id"], "arm": arm, "answerable": bool(pool_q.at[q, "answerable"]), "s1": s,
                 "s1_exc": kind, "v2": v2c, "cit": set(cited) <= {int(x) for x in supplied} and (ans == NA or bool(cited)),
                 "abst": ans == NA, "pred": ans, "exec": r["execution_index"]})
paid = pd.DataFrame(rows)
ref_nn_q = set(paid.loc[paid["s1_exc"] == "reference not numeric", "qid"])
paid.loc[paid["qid"].isin(ref_nn_q), "s1"] = 0.0
paid["c"] = paid["s1"] > 0
paid["strict"] = paid["s1"] == 1.0
byarm = {a: f.set_index("qid") for a, f in paid.groupby("arm")}
a1 = byarm["B1"].copy()
for q in a1.index:
    if TRIG[q]:
        a1.loc[q] = byarm["F8"].loc[q]
a1["arm"] = "A1"
a1 = a1.reset_index()
scores = pd.concat([paid, a1], ignore_index=True)


# Blind identity (the notebook's arm-blind serialisation), used to match pending items and the queue.
def blind_row(q, pred):
    return {"document": pool_q.at[q, "doc_id"], "evidence_pages": " ".join(map(str, pool_q.at[q, "evidence_pages"])),
            "question": pool_q.at[q, "question"], "answer_format": pool_q.at[q, "answer_format"], "reference": pool_q.at[q, "answer"],
            "reply": json.dumps(pred) if isinstance(pred, list) else str(pred)}


def blind_identity(row):
    return sha256b(json.dumps({c: str(row[c]) for c in ["document", "evidence_pages", "question", "answer_format", "reference", "reply"]},
                              sort_keys=True, ensure_ascii=False).encode())


scores["identity"] = [blind_identity(blind_row(q, p)) for q, p in zip(scores["qid"], scores["pred"])]
owner = {}
for pkg in ("scoring_v2", "e8_scoring_v2", "e9_scoring_v2", "final_scoring_v2"):
    f = ROOT / "experiments/frozen" / pkg / "adjudication_labels.csv"
    if f.is_file():
        lab = pd.read_csv(f, dtype=str).fillna("")
        owner.update(dict(zip(lab["identity_sha256"], lab["label"])))
owner_hits = int(scores.loc[scores["v2"] == "gray", "identity"].isin(owner).sum())
scores["v2f"] = np.where(scores["v2"] == "gray", scores["identity"].map(owner).fillna("pending"), scores["v2"])

# Per-question comparison with the notebook's table
nbt = pd.read_csv(FINAL / "evaluation_per_question.csv")
mine = scores.set_index(["qid", "arm"])
theirs = nbt.set_index(["qid", "arm"])
assert set(mine.index) == set(theirs.index) and len(mine) == len(theirs) == 2951
theirs = theirs.loc[mine.index]
cmp = {
    "s1_score max |diff|": float((mine["s1"] - theirs["s1_score"]).abs().max()),
    "s1_correct mismatches": int((mine["c"] != theirs["s1_correct"]).sum()),
    "v2_class mismatches": int((mine["v2"] != theirs["v2_class"]).sum()),
    "v2_final mismatches": int((mine["v2f"] != theirs["v2_final"]).sum()),
    "citation_valid mismatches": int((mine["cit"] != theirs["citation_valid"]).sum()),
    "abstained mismatches": int((mine["abst"] != theirs["abstained"]).sum()),
    "s1_exception mismatches": int((mine["s1_exc"].fillna("none") != theirs["s1_exception"].fillna("none")).sum()),
}
check("3.03 every reply re-scored (2,079 replies + 872 derived A1 rows): identical to the notebook's per-question table",
      cmp["s1_score max |diff|"] < 1e-12 and all(v == 0 for k, v in cmp.items() if k.endswith("mismatches")), **cmp,
      owner_label_hits_from_development_packages=owner_hits)


# Statistics -------------------------------------------------------------------------------------
def vec(arm, col="c", subset=None, frame=None):
    f = (frame if frame is not None else scores)
    f = f[(f["arm"] == arm) & f["answerable"]].set_index("qid").sort_index()
    if subset is not None:
        f = f[f.index.isin(subset)]
    return f[col].astype(float)


def per_doc(values):
    docs = pool_q.loc[values.index, "doc_id"].to_numpy()
    order = sorted(set(docs))
    v = values.to_numpy()
    return np.array([v[docs == d].sum() for d in order]), np.array([(docs == d).sum() for d in order]), order


def boot(sums, counts, seed=20261202, draws=10_000):
    picks = np.random.default_rng(seed).integers(0, len(sums), (draws, len(sums)))
    return sums[picks].sum(axis=1) / counts[picks].sum(axis=1)


def signflip_p(doc_values, seed=20261203, draws=100_000):
    signs = np.random.default_rng(seed).choice([-1.0, 1.0], size=(draws, len(doc_values))).astype(np.float32)
    t = signs @ doc_values.astype(np.float32)
    return float((1 + np.sum(t >= doc_values.sum() - 1e-6)) / (1 + draws))


def acc_ci(values):
    s, c, order = per_doc(values)
    b = boot(s, c)
    return {"n": len(values), "correct": int(values.sum()), "accuracy": float(values.mean()), "ci95": [float(x) for x in np.percentile(b, [2.5, 97.5])],
            "documents": len(order)}


def contrast(t, c):
    d = (t - c).sort_index()
    s, n, order = per_doc(d)
    b = boot(s, n)
    return {"n": len(d), "delta": float(d.mean()), "ci95": [float(x) for x in np.percentile(b, [2.5, 97.5])], "p05_one_sided": float(np.percentile(b, 5)),
            "sign_flip_p": signflip_p(s), "fixed": int(((t == 1) & (c == 0)).sum()), "broken": int(((t == 0) & (c == 1)).sum()), "documents": len(order)}


def c2_verdict(r):
    return "visual_retrieval_confirmed" if r["delta"] > 0 and r["p05_one_sided"] > 0 and r["sign_flip_p"] <= 0.05 else \
        "reversed" if r["ci95"][1] < 0 else "visual_retrieval_not_confirmed"


def c3_verdict(r):
    return "a1_gain_supported" if r["p05_one_sided"] > 0 and r["sign_flip_p"] <= 0.05 else "a1_gain_not_supported"


REPORT = {"Financial report", "Research report / Introduction", "Administration/Industry file"}
bd = manifest.groupby("doc_id")["native_words"].apply(lambda w: float((w >= 30).mean()) >= 0.8)
pool_q["born_digital"] = pool_q["doc_id"].map(bd)
pool_q["core"] = pool_q["born_digital"] & pool_q["doc_type"].isin(REPORT)
CORE = set(pool_q.index[pool_q["core"]])
C1 = {"overall": acc_ci(vec("B1")), "core scope": acc_ci(vec("B1", subset=CORE))}
C2 = contrast(vec("B1"), vec("T1"))
C2["verdict"] = c2_verdict(C2)
C3 = contrast(vec("A1"), vec("B1"))
C3["verdict"] = c3_verdict(C3)


def arm_stats(arm):
    f = scores[scores["arm"] == arm]
    a, u = f[f["answerable"]], f[~f["answerable"]]
    return {"answerable": len(a), "correct": int(a["c"].sum()), "accuracy": float(a["c"].mean()), "unanswerable": len(u),
            "abstentions": int(u["abst"].sum()), "citation_validity": float(f["cit"].mean()), "v2_correct": int((a["v2f"] == "correct").sum()),
            "v2_pending": int((a["v2f"] == "pending").sum()), "strict_correct": int(a["strict"].sum())}


ARM = {a: arm_stats(a) for a in ("B1", "T1", "A1", "F8")}


# S-v2 exact ranges (own derivation): the contrast is linear in the per-identity labels, so its extremes are attained identity by identity.
def v2_range(t_arm, c_arm, return_vectors=False):
    t = scores[(scores["arm"] == t_arm) & scores["answerable"]].set_index("qid").sort_index()
    c = scores[(scores["arm"] == c_arm) & scores["answerable"]].set_index("qid").loc[t.index]
    base = (t["v2f"] == "correct").astype(int) - (c["v2f"] == "correct").astype(int)
    w = Counter(t.loc[t["v2f"] == "pending", "identity"])
    w.subtract(Counter(c.loc[c["v2f"] == "pending", "identity"]))
    lo_ids = {i for i, x in w.items() if x < 0}   # labelled correct to minimise
    hi_ids = {i for i, x in w.items() if x > 0}   # labelled correct to maximise

    def realise(correct_ids):
        tv = ((t["v2f"] == "correct") | ((t["v2f"] == "pending") & t["identity"].isin(correct_ids))).astype(float)
        cv = ((c["v2f"] == "correct") | ((c["v2f"] == "pending") & c["identity"].isin(correct_ids))).astype(float)
        return tv, cv
    lo_t, lo_c = realise(lo_ids)
    hi_t, hi_c = realise(hi_ids)
    n = len(t)
    lo, hi = float((lo_t - lo_c).mean()), float((hi_t - hi_c).mean())
    # brute-force sanity: 2,000 random consistent labellings stay inside [lo, hi]
    ids = sorted(set(t.loc[t["v2f"] == "pending", "identity"]) | set(c.loc[c["v2f"] == "pending", "identity"]))
    g = np.random.default_rng(7)
    inside = True
    for _ in range(2000):
        lab = {i for i, bit in zip(ids, g.integers(0, 2, len(ids))) if bit}
        tv, cv = realise(lab)
        val = float((tv - cv).mean())
        inside &= lo - 1e-12 <= val <= hi + 1e-12
    out = {"low": lo, "high": hi, "n": n, "pending_identities": len(ids), "random_labellings_inside": bool(inside),
           "auto_only_delta": float(base.mean())}
    return (out, (lo_t, lo_c), (hi_t, hi_c)) if return_vectors else out


V2_C2, V2_C2_lo, V2_C2_hi = v2_range("B1", "T1", True)
V2_C3, V2_C3_lo, V2_C3_hi = v2_range("A1", "B1", True)
pend = scores[(scores["v2f"] == "pending") & scores["answerable"] & scores["arm"].isin(["B1", "T1", "F8"])]
pending_ids = set(pend["identity"])
id_qids = pend.groupby("identity")["qid"].nunique()

# Retrieval
withev = [q for q in pool_q.index if pool_q.at[q, "answerable"] and pool_q.at[q, "evidence_pages"]]
rec = pd.DataFrame([{"qid": q, "V": len(set(pool_q.at[q, "evidence_pages"]) & set(RK.at[q, "V_pages"][:4])) / len(set(pool_q.at[q, "evidence_pages"])),
                     "A": len(set(pool_q.at[q, "evidence_pages"]) & set(RK.at[q, "A_pages"][:4])) / len(set(pool_q.at[q, "evidence_pages"])),
                     "Vc": set(pool_q.at[q, "evidence_pages"]) <= set(RK.at[q, "V_pages"][:4]),
                     "Ac": set(pool_q.at[q, "evidence_pages"]) <= set(RK.at[q, "A_pages"][:4])} for q in withev]).set_index("qid")
RET = {"questions": len(rec), "V recall@4": float(rec["V"].mean()), "BM25 recall@4": float(rec["A"].mean()),
       "V complete@4": float(rec["Vc"].mean()), "BM25 complete@4": float(rec["Ac"].mean())}
RET_C = contrast(rec["V"], rec["A"])

D2_counts = dict(Counter(paid.loc[paid["answerable"], "s1_exc"].fillna("none")))
D2_arms = dict(Counter(paid.loc[paid["s1_exc"].notna(), "arm"]))

# Reproduction table ------------------------------------------------------------------------------
S = json.loads((FINAL / "evaluation_summary.json").read_text())


def add(name, claimed_brief, claimed_json, recomputed):
    d_json = None if claimed_json is None else abs(float(claimed_json) - float(recomputed))
    d_brief = None if claimed_brief is None else abs(float(claimed_brief) - float(recomputed))
    repro.append({"quantity": name, "claimed_brief": claimed_brief, "claimed_summary_json": claimed_json, "recomputed": recomputed,
                  "abs_diff_vs_json": d_json, "abs_diff_vs_brief": d_brief})


add("C1 B1 correct", 288, S["C1"]["overall"]["correct"], C1["overall"]["correct"])
add("C1 B1 n answerable", 674, S["C1"]["overall"]["n"], C1["overall"]["n"])
add("C1 B1 accuracy", 0.4273, S["C1"]["overall"]["accuracy"], C1["overall"]["accuracy"])
add("C1 CI 2.5%", 0.3858, S["C1"]["overall"]["ci95"][0], C1["overall"]["ci95"][0])
add("C1 CI 97.5%", 0.4697, S["C1"]["overall"]["ci95"][1], C1["overall"]["ci95"][1])
add("C1 core correct", 77, S["C1"]["core scope"]["correct"], C1["core scope"]["correct"])
add("C1 core n", 207, S["C1"]["core scope"]["n"], C1["core scope"]["n"])
add("C1 core documents", None, S["C1"]["core scope"]["documents"], C1["core scope"]["documents"])
add("C1 core accuracy", 0.372, S["C1"]["core scope"]["accuracy"], C1["core scope"]["accuracy"])
add("C1 core CI 2.5%", 0.305, S["C1"]["core scope"]["ci95"][0], C1["core scope"]["ci95"][0])
add("C1 core CI 97.5%", 0.443, S["C1"]["core scope"]["ci95"][1], C1["core scope"]["ci95"][1])
for tag, mineC, jsC, br in (("C2", C2, S["C2"], ("C2", 0.1187, 0.0883, 0.1499, 0.0926, 1e-05, 103, 23)),
                            ("C3", C3, S["C3"], ("C3", 0.0208, 0.0072, 0.0361, None, 0.00463, 19, 5))):
    add(f"{tag} delta", br[1], jsC["delta"], mineC["delta"])
    add(f"{tag} CI 2.5%", br[2], jsC["ci95"][0], mineC["ci95"][0])
    add(f"{tag} CI 97.5%", br[3], jsC["ci95"][1], mineC["ci95"][1])
    add(f"{tag} bootstrap 5th pct", br[4], jsC["p05_one_sided"], mineC["p05_one_sided"])
    add(f"{tag} sign-flip p", br[5], jsC["sign_flip_p"], mineC["sign_flip_p"])
    add(f"{tag} fixed", br[6], jsC["fixed"], mineC["fixed"])
    add(f"{tag} broken", br[7], jsC["broken"], mineC["broken"])
for arm, keyc, keya in (("B1", "B1 correct", "B1 abstentions"), ("T1", "T1 correct", "T1 abstentions"), ("A1", "A1 correct", "A1 abstentions"), ("F8", "F8 correct", None)):
    add(f"{arm} S-v1 correct", CLAIMED[keyc], S["arms"][arm]["S-v1 correct"], ARM[arm]["correct"])
    add(f"{arm} answerable", 259 if arm == "F8" else 674, S["arms"][arm]["answerable"], ARM[arm]["answerable"])
    add(f"{arm} correct abstentions", CLAIMED[keya] if keya else None, S["arms"][arm]["correct abstentions"], ARM[arm]["abstentions"])
    add(f"{arm} citation validity", CLAIMED.get(f"{arm} citation validity"), S["arms"][arm]["citation validity"], ARM[arm]["citation_validity"])
    add(f"{arm} S-v2 auto correct", None, S["arms"][arm]["S-v2 correct (auto + owner)"], ARM[arm]["v2_correct"])
    add(f"{arm} S-v2 pending (answerable rows)", None, S["arms"][arm]["S-v2 pending"], ARM[arm]["v2_pending"])
    add(f"{arm} cost USD", None, S["arms"][arm]["cost USD"], float(sum(cost(r) for r in run_log if r["arm"] == arm)) if arm != "A1" else
        float(sum(cost(r) for r in run_log if (r["arm"] == "F8") or (r["arm"] == "B1" and not TRIG[r["qid"]]))))
add("observed cost USD", 0.99023348, S["observed_cost_usd"], obs)
add("smoke cost USD", 0.003216, None, smoke_cost)
add("D2 reply not numeric (answerable paid replies)", 2, S["D2_s1_exceptions"].get("reply not numeric", 0), D2_counts.get("reply not numeric", 0))
add("D2 reference-not-numeric questions", 0, S["D2_questions_reference_not_numeric"], len(ref_nn_q))
add("S-v2 B1-T1 low", 0.0772, S["S_v2_ranges"]["B1 - T1"][0], V2_C2["low"])
add("S-v2 B1-T1 high", 0.1499, S["S_v2_ranges"]["B1 - T1"][1], V2_C2["high"])
add("S-v2 A1-B1 low", 0.0148, S["S_v2_ranges"]["A1 - B1"][0], V2_C3["low"])
add("S-v2 A1-B1 high", 0.0282, S["S_v2_ranges"]["A1 - B1"][1], V2_C3["high"])
add("S-v2 pending items (unique identities)", 85, S["S_v2_ranges"]["pending items"], len(pending_ids))
add("retrieval questions", 666, S["retrieval"]["questions"], RET["questions"])
add("V recall@4", 0.711, S["retrieval"]["V recall@4"], RET["V recall@4"])
add("BM25 recall@4", 0.543, S["retrieval"]["BM25 recall@4"], RET["BM25 recall@4"])
add("V complete@4", None, S["retrieval"]["V complete@4"], RET["V complete@4"])
add("BM25 complete@4", None, S["retrieval"]["BM25 complete@4"], RET["BM25 complete@4"])
add("V-BM25 recall@4 delta", None, S["retrieval"]["V - BM25 recall@4"]["delta"], RET_C["delta"])
add("V-BM25 recall@4 5th pct", None, S["retrieval"]["V - BM25 recall@4"]["p05_one_sided"], RET_C["p05_one_sided"])
add("triggered", None, S["triggered"], int(trig.sum()))

max_json = max(x["abs_diff_vs_json"] for x in repro if x["abs_diff_vs_json"] is not None)
brief_tol = lambda x: 0.6 * 10 ** -(len(str(x["claimed_brief"]).split(".")[-1]) if "." in str(x["claimed_brief"]) and "e" not in str(x["claimed_brief"]) else 0)
brief_bad = [x["quantity"] for x in repro if x["claimed_brief"] is not None and x["abs_diff_vs_brief"] > max(brief_tol(x), 1e-9)]
check("3.04 every claimed number reproduced (exact vs summary JSON; within stated rounding vs the brief)",
      max_json < 1e-9 and not brief_bad, max_abs_diff_vs_summary_json=max_json, brief_mismatches=brief_bad, quantities=len(repro))
check("3.05 verdicts: C2 visual_retrieval_confirmed, C3 a1_gain_supported (applied from the frozen rules)",
      C2["verdict"] == S["C2"]["verdict"] == "visual_retrieval_confirmed" and C3["verdict"] == S["C3"]["verdict"] == "a1_gain_supported",
      C2=C2["verdict"], C3=C3["verdict"])
check("3.06 S-v2: 85 pending identities, each labelled once and consistently across arms; exact ranges reproduced; random labellings stay inside",
      len(pending_ids) == 85 and V2_C2["random_labellings_inside"] and V2_C3["random_labellings_inside"] and owner_hits == 0,
      identities_shared_by_several_questions=int((id_qids > 1).sum()), B1_T1=V2_C2, A1_B1=V2_C3)
check("3.07 D2 counts: 2 'reply not numeric' answerable replies, 0 'reference not numeric' questions",
      D2_counts.get("reply not numeric", 0) == 2 and len(ref_nn_q) == 0 and set(D2_counts) <= {"none", "reply not numeric"},
      counts=D2_counts, arms_of_affected_replies=D2_arms,
      affected_qids=sorted(paid.loc[paid["s1_exc"].notna(), "qid"].unique().tolist()))
pdq = pool_q.loc[sorted(CORE)]
check("3.08 core scope definition: born-digital share (native_words>=30) >= 0.8 AND doc_type in the three report types",
      len(CORE & set(pool_q.index[pool_q["answerable"]])) == 207 and pdq["doc_id"].nunique() >= 32,
      core_documents=int(pdq["doc_id"].nunique()), core_answerable=len(CORE & set(pool_q.index[pool_q["answerable"]])),
      born_digital_documents=int(bd.loc[EVAL_DOCS].sum()))

# ======================================================================================================
# 4. Robustness (reported only; never a re-decision)
# ======================================================================================================
def rule_eval(t, c, kind):
    r = contrast(t, c)
    r["verdict"] = c2_verdict(r) if kind == "C2" else c3_verdict(r)
    return r


def equal_weight(t, c):
    d = (t - c).sort_index()
    s, n, order = per_doc(d)
    m = s / n
    picks = np.random.default_rng(20261202).integers(0, len(m), (10_000, len(m)))
    b = m[picks].mean(axis=1)
    return {"documents": len(m), "delta": float(m.mean()), "ci95": [float(x) for x in np.percentile(b, [2.5, 97.5])],
            "p05_one_sided": float(np.percentile(b, 5)), "sign_flip_p": signflip_p(m)}


def loo(t, c, kind):
    d = (t - c).sort_index()
    docs = pool_q.loc[d.index, "doc_id"]
    deltas, verdicts = [], Counter()
    for doc in sorted(set(docs)):
        keep = d.index[docs != doc]
        deltas.append(float(d.loc[keep].mean()))
        verdicts[rule_eval(t.loc[keep], c.loc[keep], kind)["verdict"]] += 1
    return {"delta_min": min(deltas), "delta_max": max(deltas), "verdicts": dict(verdicts)}


def mcnemar(t, c):
    b, cc = int(((t == 1) & (c == 0)).sum()), int(((t == 0) & (c == 1)).sum())
    n = b + cc
    p = min(1.0, 2 * sum(math.comb(n, i) for i in range(0, min(b, cc) + 1)) / 2 ** n) if n else 1.0
    return {"fixed": b, "broken": cc, "discordant": n, "exact_two_sided_p": p}


B1v, T1v, A1v = vec("B1"), vec("T1"), vec("A1")
d2_q = set(paid.loc[paid["s1_exc"].notna(), "qid"])
keep = [q for q in B1v.index if q not in d2_q]
robustness["equal_weight_documents"] = {"C2": equal_weight(B1v, T1v), "C3": equal_weight(A1v, B1v)}
robustness["leave_one_document_out"] = {"C2": loo(B1v, T1v, "C2"), "C3": loo(A1v, B1v, "C3")}
robustness["excluding_D2_questions"] = {"questions_removed": sorted(d2_q), "C2": rule_eval(B1v.loc[keep], T1v.loc[keep], "C2"),
                                        "C3": rule_eval(A1v.loc[keep], B1v.loc[keep], "C3")}
robustness["strict_s1_score_eq_1"] = {"B1 correct": ARM["B1"]["strict_correct"], "T1 correct": ARM["T1"]["strict_correct"],
                                      "A1 correct": ARM["A1"]["strict_correct"],
                                      "C2": rule_eval(vec("B1", "strict"), vec("T1", "strict"), "C2"),
                                      "C3": rule_eval(vec("A1", "strict"), vec("B1", "strict"), "C3")}
robustness["s2_worst_and_best_case_labelling"] = {
    "C2_worst": rule_eval(V2_C2_lo[0], V2_C2_lo[1], "C2"), "C2_best": rule_eval(V2_C2_hi[0], V2_C2_hi[1], "C2"),
    "C3_worst": rule_eval(V2_C3_lo[0], V2_C3_lo[1], "C3"), "C3_best": rule_eval(V2_C3_hi[0], V2_C3_hi[1], "C3")}
diff_q = A1v.index[A1v != B1v]
robustness["C3_changes_on_triggered"] = {"fixed": int(((A1v == 1) & (B1v == 0)).sum()), "broken": int(((A1v == 0) & (B1v == 1)).sum()),
                                         "on_triggered": int(sum(TRIG[q] for q in diff_q)), "on_untriggered": int(sum(not TRIG[q] for q in diff_q)),
                                         "untriggered_A1_reply_is_B1_reply": bool(all(
                                             scores[(scores["arm"] == "A1") & (scores["qid"] == q)]["exec"].item() ==
                                             scores[(scores["arm"] == "B1") & (scores["qid"] == q)]["exec"].item() for q in pool_q.index if not TRIG[q]))}
robustness["mcnemar"] = {"C2 B1 vs T1": mcnemar(B1v, T1v), "C3 A1 vs B1": mcnemar(A1v, B1v),
                         "C3 restricted to triggered answerable": {"n": int(sum(TRIG[q] for q in A1v.index))}}
robustness["seed_sensitivity"] = {}
for seed in (1, 2, 3):
    for tag, (t, c) in (("C2", (B1v, T1v)), ("C3", (A1v, B1v))):
        d = (t - c).sort_index()
        s, n, _ = per_doc(d)
        b = boot(s, n, seed=seed)
        robustness["seed_sensitivity"][f"{tag} seed {seed}"] = {"p05": float(np.percentile(b, 5)), "sign_flip_p": signflip_p(s, seed=seed + 100)}
ct = robustness["C3_changes_on_triggered"]
check("4.01 C3 fixed/broken all on triggered questions (by construction); untriggered A1 reuses the B1 reply",
      ct["on_untriggered"] == 0 and ct["on_triggered"] == ct["fixed"] + ct["broken"] == 24 and ct["untriggered_A1_reply_is_B1_reply"], **ct)


# S-v2 range when the owner may also answer 'unsure' (AGENTS.md: unsure is excluded from paired contrasts, shrinking n).
# Each pending identity belongs to one question (checked in 3.06), so questions are independent; the extreme ratio
# sum(contribution) / #included is found exactly by Dinkelbach iteration over per-question option sets.
def v2_range_with_unsure(t_arm, c_arm):
    t = scores[(scores["arm"] == t_arm) & scores["answerable"]].set_index("qid").sort_index()
    c = scores[(scores["arm"] == c_arm) & scores["answerable"]].set_index("qid").loc[t.index]
    options = []
    for q in t.index:
        st, sc = t.at[q, "v2f"], c.at[q, "v2f"]
        ids = sorted({x for x, s in ((t.at[q, "identity"], st), (c.at[q, "identity"], sc)) if s == "pending"})
        opts = set()
        for labs in __import__("itertools").product(("correct", "wrong", "unsure"), repeat=len(ids)):
            lab = dict(zip(ids, labs))
            if "unsure" in labs:
                opts.add((0, 0))
                continue
            tv = (st == "correct") or (st == "pending" and lab[t.at[q, "identity"]] == "correct")
            cv = (sc == "correct") or (sc == "pending" and lab[c.at[q, "identity"]] == "correct")
            opts.add((int(tv) - int(cv), 1))
        options.append(sorted(opts))

    def extreme(sign):
        r = 0.0
        for _ in range(100):
            chosen = [max(o, key=lambda x: sign * (x[0] - r * x[1])) for o in options]
            new = sum(a for a, _ in chosen) / sum(n for _, n in chosen)
            if abs(new - r) < 1e-15:
                break
            r = new
        return r, sum(n for _, n in chosen)
    (hi, n_hi), (lo, n_lo) = extreme(+1), extreme(-1)
    return {"low": lo, "n_at_low": n_lo, "high": hi, "n_at_high": n_hi}


robustness["s2_range_allowing_unsure"] = {"B1 - T1": v2_range_with_unsure("B1", "T1"), "A1 - B1": v2_range_with_unsure("A1", "B1")}

# Descriptive subgroups (not a claim): recomputed and compared with the summary JSON.
ans_q = pool_q[pool_q["answerable"]].copy()
ans_q["pages"] = ans_q["doc_id"].map(pdocs.set_index("doc_id")["pages"])
groupings = {"document type": ans_q["doc_type"], "core scope": ans_q["core"].map({True: "core", False: "other"}),
             "document length": pd.cut(ans_q["pages"], [0, 50, 200, 10_000], labels=["<= 50", "51-200", "> 200"]).astype(str),
             "evidence span": ans_q["evidence_pages"].map(lambda e: "none annotated" if not e else "1" if len(e) == 1 else "2-3" if len(e) <= 3 else "4+"),
             "answer format": ans_q["answer_format"], "born-digital": ans_q["born_digital"].map({True: "born-digital", False: "image-heavy"})}
sub = {}
for name, labels in groupings.items():
    for value in sorted(set(labels)):
        idx = labels.index[labels == value]
        sub[(name, str(value))] = (len(idx), float(B1v.loc[idx].mean()), float(T1v.loc[idx].mean()))
src = ans_q["evidence_sources"].explode().dropna()
for value in sorted(set(src)):
    idx = sorted(set(src.index[src == value]))
    sub[("evidence source (overlapping)", str(value))] = (len(idx), float(B1v.loc[idx].mean()), float(T1v.loc[idx].mean()))
claimed_sub = {(r["grouping"], str(r["group"])): (r["n"], r["B1"], r["T1"]) for r in S["subgroups"]}
sub_diff = max(max(abs(a - b) for a, b in zip(sub[k], claimed_sub[k])) for k in sub) if set(sub) == set(claimed_sub) else None
check("3.09 descriptive subgroup table (27 rows) reproduced", sub_diff is not None and sub_diff < 1e-9, rows=len(sub), max_abs_diff=sub_diff,
      B1_minus_T1_min_over_document_types=min(sub[k][1] - sub[k][2] for k in sub if k[0] == "document type"))


# ======================================================================================================
# 1 (cont.). Independent recomputation of retrieval: BM25 from page texts; ColQwen2 MaxSim from cached embeddings
# ======================================================================================================
pages_tbl = pd.concat([pd.read_parquet(p) for p in sorted((FINAL / "pages").glob("*.parquet"))], ignore_index=True)
pages_tbl = pages_tbl[pages_tbl["doc_id"].isin(EVAL_DOCS)]
mi = manifest.set_index(["doc_id", "page"])
txt_ok = sum(sha256b(t.encode()) == mi.at[(d, int(p)), "text_sha256"] for d, p, t in zip(pages_tbl["doc_id"], pages_tbl["page"], pages_tbl["text"]))
TOK = re.compile(r"[a-z0-9]+")


def bm25(texts, query, k1=1.5, b=0.75):
    toks = {p: TOK.findall(str(t).lower()) for p, t in texts.items()}
    N = len(toks)
    avgdl = max(float(np.mean([len(v) for v in toks.values()])), 1.0)
    df = Counter(t for v in toks.values() for t in set(v))
    terms = set(TOK.findall(query.lower()))
    out = []
    for p, v in toks.items():
        tf = Counter(v)
        s = 0.0
        for t in terms:
            if tf[t]:
                idf = math.log(1 + (N - df[t] + 0.5) / (df[t] + 0.5))
                s += idf * tf[t] * (k1 + 1) / (tf[t] + k1 * (1 - b + b * len(v) / avgdl))
        out.append((p, s))
    return sorted(out, key=lambda x: (-x[1], x[0]))


def consistent(order, scores_by_page, tol):
    s = [scores_by_page[p] for p in order]
    return set(order) == set(scores_by_page) and all(a >= b - tol for a, b in zip(s, s[1:]))


bm_exact = bm_cons = 0
bm_maxdiff = 0.0
top4_same = 0
for doc, g in pool_q.groupby("doc_id"):
    dp = pages_tbl[pages_tbl["doc_id"] == doc]
    texts = dict(zip(dp["page"].astype(int), dp["text"]))
    for q in g.index:
        r = bm25(texts, pool_q.at[q, "question"])
        sc = dict(r)
        bm_exact += [p for p, _ in r] == [int(x) for x in RK.at[q, "A_pages"]]
        bm_cons += consistent([int(x) for x in RK.at[q, "A_pages"]], sc, 1e-9)
        top4_same += [p for p, _ in r][:4] == [int(x) for x in RK.at[q, "A_pages"][:4]]
        bm_maxdiff = max(bm_maxdiff, max(abs(sc[int(p)] - s) for p, s in zip(RK.at[q, "A_pages"], RK.at[q, "A_scores"])))
check("1.18 BM25 (T1) recomputed independently from the page texts (text hashes = manifest): rankings equal the frozen ones",
      txt_ok == len(manifest) == len(pages_tbl) and bm_cons == 872 and top4_same == 872 and bm_maxdiff < 1e-9,
      text_hashes_ok=txt_ok, pages=len(manifest), identical_full_rankings=bm_exact, consistent=bm_cons, identical_top4=top4_same, max_score_diff=bm_maxdiff)

if "--skip-maxsim" not in FLAGS:
    import torch
    from safetensors.torch import load_file
    torch.set_num_threads(max(1, torch.get_num_threads()))
    CACHE = ROOT / "data/cache/final/colqwen2-v1.0-hf@ddc07d2317c8/af02fac2cb9b"
    emb_ok = sum(sha256f(CACHE / "pages" / f"{s}.safetensors") == e for s, e in
                 manifest.drop_duplicates("sha256")[["sha256", "embedding_sha256"]].itertuples(index=False))
    q_ok = sum(sha256f(CACHE / "queries" / f"{sha256b(pool_q.at[q, 'question'].encode())}.safetensors") == qman.at[q, "embedding_sha256"] for q in pool_q.index)
    v_exact = v_cons = v_top8 = 0
    v_maxdiff = 0.0
    for doc, g in pool_q.groupby("doc_id"):
        dm = manifest[manifest["doc_id"] == doc]
        embs = {int(p): load_file(str(CACHE / "pages" / f"{s}.safetensors"))["embedding"].float() for p, s in zip(dm["page"], dm["sha256"])}
        for q in g.index:
            qe = load_file(str(CACHE / "queries" / f"{sha256b(pool_q.at[q, 'question'].encode())}.safetensors"))["embedding"].float()
            sc = {p: float((qe @ e.T).max(dim=1).values.sum()) for p, e in embs.items()}
            order = sorted(sc, key=lambda p: (-sc[p], p))
            v_exact += order == [int(x) for x in RK.at[q, "V_pages"]]
            v_cons += consistent([int(x) for x in RK.at[q, "V_pages"]], sc, 1e-4)
            v_top8 += order[:8] == [int(x) for x in RK.at[q, "V_pages"][:8]]
            v_maxdiff = max(v_maxdiff, max(abs(sc[int(p)] - s) for p, s in zip(RK.at[q, "V_pages"], RK.at[q, "V_scores"])))
        del embs
    check("1.19 ColQwen2 MaxSim (B1/F8) recomputed from the cached embeddings (hashes = manifests): consistent with the frozen rankings",
          emb_ok == manifest["sha256"].nunique() and q_ok == 872 and v_cons == 872 and v_maxdiff < 1e-3,
          page_embeddings_hash_ok=emb_ok, distinct_pages=int(manifest["sha256"].nunique()), query_embeddings_hash_ok=q_ok,
          identical_full_rankings=v_exact, consistent_within_1e4=v_cons, identical_top8=v_top8, max_score_diff=v_maxdiff)
else:
    notes.append("MaxSim recomputation skipped (--skip-maxsim)")

# ======================================================================================================
# 5. Hygiene
# ======================================================================================================
PATTERNS = {"openai_key": r"sk-[A-Za-z0-9_\-]{20,}", "aws_key_id": r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b",
            "assignment_of_secret": r"(?i)(?:api[_-]?key|secret[_-]?(?:access[_-]?)?key|access[_-]?key(?:[_-]?id)?|session[_-]?token|password|authorization)[\"']?\s*[:=]",
            "bearer": r"Bearer\s+[A-Za-z0-9._\-]{16,}",
            "env_var_with_value": r"(?:OPENAI_API_KEY|AWS_SECRET_ACCESS_KEY|AWS_ACCESS_KEY_ID|AWS_SESSION_TOKEN)[\"']?\s*[:=]\s*[\"']?[A-Za-z0-9]",
            "jwt": r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\."}
scan_files = [p for d in (RUN[0], SMOKE[0]) for p in sorted(d.rglob("*")) if p.is_file()] + \
             [p for p in sorted(FINAL.glob("*")) if p.is_file() and p.suffix in (".csv", ".json")] + [NB09]
hits, name_refs = {}, {}
for p in scan_files:
    text = p.read_text(errors="replace")
    for name, pat in PATTERNS.items():
        n = len(re.findall(pat, text))
        if n:
            hits[f"{p.relative_to(ROOT)}::{name}"] = n
    n = len(re.findall(r"OPENAI_API_KEY|AWS_SECRET_ACCESS_KEY|AWS_SESSION_TOKEN", text))
    if n:
        name_refs[str(p.relative_to(ROOT))] = n  # variable NAMES only (e.g. os.getenv("OPENAI_API_KEY")): informational
env_tracked = bool(git("ls-files", "--", ".env").strip())
check("5.01 no credential or API key in the run directories, final outputs or notebook 09 (pattern scan); .env untracked",
      not hits and not env_tracked and set(settings) == {"run_id", "mode", "git_commit", "spec_sha256", "plan_spec_sha256", "budget_usd", "prior_spend_usd", "plan"},
      files_scanned=len(scan_files), hits=hits, env_var_name_references_without_value=name_refs, env_tracked=env_tracked)

# 5.03 Pool text outside the blind queue: literals in the committed D2 text/cells equal to a pool reference; pool questions or
# long reference answers rendered in notebook 09's outputs or in the final summary/per-question table. Counts and qids only.
pool_refs = pool_q.loc[pool_q["answerable"], "answer"]
d2_text = DEV_P.read_text().split("## D2")[1] + cell_src(c_d2["fe-scorer-d2"]) + cell_src(c_d2["fe-scorer-d2-md"])
literals = set(re.findall(r'"([^"\n]{2,80})"', d2_text)) | set(re.findall(r"`([^`\n]{2,80})`", d2_text)) | set(re.findall(r"\(\"?(\$[\d,.]+)", d2_text))
lit_hits = sorted(pool_refs.index[pool_refs.isin(literals) & (pool_refs.str.len() >= 4)])
outputs_text = "\n".join(cell_out(c) for c in c_wt.values()) + (FINAL / "evaluation_summary.json").read_text() + (FINAL / "evaluation_per_question.csv").read_text()
q_in_outputs = sum(q in outputs_text for q in pool_q["question"] if len(q) >= 30)
a_in_outputs = sum(a in outputs_text for a in pool_refs if len(a) >= 12 and not re.fullmatch(r"[\d.,%$ ]+", a))
ledger_mentions = "D2" in ledger and any(q in ledger for q in lit_hits)
check("5.03 no pool question/answer text outside the blind queue (committed D2 text, notebook 09 outputs, summary, per-question table)",
      not lit_hits and q_in_outputs == 0 and a_in_outputs == 0,
      committed_D2_literals_equal_to_a_pool_reference=len(lit_hits), qids=lit_hits, committed_in="bcf0345 (deviations.md D2 section, fe-scorer-d2, fe-scorer-d2-md)",
      recorded_in_ledger=ledger_mentions, pool_questions_in_outputs=q_in_outputs, long_pool_answers_in_outputs=a_in_outputs)

queue = pd.read_csv(FINAL / "adjudication_queue.csv", dtype=str, keep_default_na=False)
key = pd.read_csv(FINAL / "adjudication_key_SEALED.csv", dtype=str, keep_default_na=False)
arm_tokens = {"B1", "T1", "F8", "A1", "L-B1", "B1s", "F8a", "F8b"}
arm_cells = int(sum(queue[c].isin(arm_tokens).sum() for c in queue.columns))
arm_cols = [c for c in queue.columns if re.search(r"(?i)\barm|qid|exec|fingerprint", c)]
q_ids = [blind_identity(r) for _, r in queue.iterrows()]
key_map = dict(zip(key["item_id"], key["identity"]))
id_match = sum(key_map.get(i) == idn for i, idn in zip(queue["item_id"], q_ids))
mine_arms = pend.groupby("identity")["arm"].agg(lambda a: " | ".join(sorted(set(a))))
key_arms_ok = sum(mine_arms.get(i) == a for i, a in zip(key["identity"], key["arms"]))
key_qid_ok = sum(i in set(pend.loc[pend["qid"] == q, "identity"]) for q, i in zip(key["qid"], key["identity"]))
# The notebook's shuffle (random_state 20261205) of pending identities in log order, reproduced: the item order carries no arm order.
items = pend.sort_values("exec").drop_duplicates("identity")[["identity", "qid"]].sample(frac=1.0, random_state=20261205).reset_index(drop=True)
order_ok = items["identity"].tolist() == [key_map[f"FINAL-ADJ-{i + 1:04d}"] for i in range(len(items))]
labels_empty = queue["label (correct / wrong / unsure)"].eq("").all()
check("5.02 blind queue: no arm/qid column or arm-valued cell; 85 items whose recomputed identities equal the sealed key; key arms/qids correct; seeded order",
      len(queue) == len(key) == 85 and not arm_cols and arm_cells == 0 and id_match == 85 and key_arms_ok == 85 and key_qid_ok == 85
      and set(key_map.values()) == pending_ids and order_ok,
      columns=list(queue.columns), arm_like_columns=arm_cols, arm_valued_cells=arm_cells, identity_matches=id_match, key_arms_ok=key_arms_ok,
      key_qids_ok=key_qid_ok, seeded_order_reproduced=order_ok, labels_still_empty=bool(labels_empty))

# ======================================================================================================
# Write
# ======================================================================================================
result = {"audit": "final held-out evaluation v1", "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
          "repo_head": HEAD, "run_id": settings["run_id"], "all_checks_passed": all(c["passed"] for c in checks),
          "checks": checks, "reproduction": repro,
          "recomputed": {"C1": C1, "C2": C2, "C3": C3, "arms": ARM, "S_v2": {"B1 - T1": V2_C2, "A1 - B1": V2_C3, "pending_identities": len(pending_ids)},
                         "retrieval": {**RET, "V - BM25 recall@4": RET_C}, "D2": {"counts_answerable_paid": D2_counts, "arms": D2_arms}},
          "robustness": robustness, "notes": notes,
          "audited_file_sha256": {str(p.relative_to(ROOT)): sha256f(p) for p in
                                  [RUN[0] / "execution_log.jsonl", RUN[0] / "settings.json", RUN[0] / "summary.json",
                                   SMOKE[0] / "execution_log.jsonl", SMOKE[0] / "settings.json",
                                   FINAL / "evaluation_summary.json", FINAL / "evaluation_per_question.csv", FINAL / "adjudication_queue.csv",
                                   FINAL / "adjudication_key_SEALED.csv", FINAL / "plan_design.json",
                                   ROOT / "data/processed/mmlongbench_doc/questions.parquet", NB09]},
          "unfrozen_state": {"experiments/frozen/final exists": (ROOT / "experiments/frozen/final").is_dir(),
                             "run directory git-ignored": git_rc("check-ignore", "-q", str(RUN[0].relative_to(ROOT))) == 0,
                             "uncommitted paths": git("status", "--porcelain").decode().split("\n")[:-1]},
          "runtime_s": round(time.time() - T0, 1)}
(OUT / "audit_final.json").write_text(json.dumps(result, indent=1, default=str) + "\n")
print(f"\n{sum(c['passed'] for c in checks)}/{len(checks)} checks passed; written {OUT.name}/audit_final.json in {result['runtime_s']} s")
