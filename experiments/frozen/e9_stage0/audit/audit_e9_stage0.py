"""Independent audit of E9 Stage 0 (written from the frozen spec only; no code from notebook 08).

Reads only frozen inputs + the spec, then compares with the notebook's outputs.
Prints no question, answer or reply text.
"""
import ast
import glob
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[4]  # repository root (made portable when frozen; was an absolute path)
SPEC = json.loads((ROOT / "experiments/specs/e9_adaptive_evidence_v1.json").read_text())
S0 = SPEC["stage0"]
SIGNALS = ["U1_margin_45", "U2_top_standout", "U3_flatness_18", "U4_abstained", "U5_numeric_unsupported"]
BINARY = {"U4_abstained", "U5_numeric_unsupported"}
TENK = {"AMAZON_2017_10K.pdf", "COSTCO_2021_10K.pdf"}

out = {}

# ---------------------------------------------------------------- inputs
rank = pd.read_parquet(ROOT / "experiments/frozen/e5/tables/rankings.parquet")
rank = rank[(rank.population == "held-out") & (rank.arm == "V")].copy()
assert rank.qid.is_unique
rank = rank.set_index("qid")
pq = pd.read_csv(ROOT / "experiments/frozen/e5/tables/per_question.csv")
pq = pq[pq.population == "held-out"].copy().set_index("qid")
e8 = pd.read_csv(ROOT / "experiments/frozen/e8/tables/evaluation_per_question.csv")
lb1 = e8[e8.arm == "L-B1"].set_index("qid")
log_path = glob.glob(str(ROOT / "experiments/frozen/e8/run_*/execution_log.jsonl"))
assert len(log_path) == 1
records = [json.loads(line) for line in open(log_path[0])]

print("== populations ==")
print("rankings held-out V rows:", len(rank), "docs:", rank.doc_id.nunique())
print("per_question held-out rows:", len(pq), "docs:", pq.doc_id.nunique())
print("E8 L-B1 rows:", len(lb1), "answerable:", int(lb1.answerable.sum()), "unanswerable:", int((~lb1.answerable).sum()))
assert set(rank.index) == set(lb1.index), "rankings and E8 L-B1 question sets differ"
assert set(pq.index) <= set(rank.index)
ans_no_label = sorted(set(lb1.index[lb1.answerable]) - set(pq.index))
unans_labelled = sorted(set(lb1.index[~lb1.answerable]) & set(pq.index))
print("answerable but not in P0:", ans_no_label, "| unanswerable but in P0:", unans_labelled)
assert (rank.doc_id == lb1.doc_id.reindex(rank.index)).all()
assert (pq.doc_id == rank.doc_id.reindex(pq.index)).all()

e5spec = json.loads((ROOT / "experiments/frozen/e5/spec_snapshot.json").read_text())
held_docs = set(e5spec["populations"]["held_out"]["selected_documents"])
dev_docs = set(pd.read_parquet(ROOT / "experiments/frozen/e5/tables/rankings.parquet").query("population=='development'").doc_id)
touched = {"PH_2016.06.08_Economy-Final.pdf", "05-03-18-political-release.pdf", "2312.04350v3.pdf", "RAR.pdf"}
print("P_deploy docs == E5 selected held-out docs:", set(rank.doc_id) == held_docs, "| P0 docs:", pq.doc_id.nunique())
print("held-out ∩ dev:", held_docs & dev_docs, "| ∩ touched-pool:", held_docs & touched, "| |held ∪ dev| =", len(held_docs | dev_docs))

# ---------------------------------------------------------------- page convention
print("\n== page convention ==")
bad = 0
page_count_rank = {}
for qid, r in rank.iterrows():
    pages = np.asarray(r.pages, dtype=int)
    scores = np.asarray(r.scores, dtype=float)
    assert len(pages) == len(scores) == len(set(pages.tolist()))
    if not np.all(np.diff(scores) <= 0):
        bad += 1
    page_count_rank.setdefault(r.doc_id, set()).add((len(pages), pages.min(), pages.max()))
print("rankings not sorted desc:", bad)
for d, s in sorted(page_count_rank.items()):
    assert len(s) == 1
pc_pq = pq.groupby("doc_id").page_count.first()
mism = {d: (list(page_count_rank[d])[0], pc_pq.get(d)) for d in page_count_rank if list(page_count_rank[d])[0] != (pc_pq.get(d), 1, pc_pq.get(d))}
print("docs whose ranking != pages 1..page_count:", mism if mism else "none")
print("min pages per doc:", min(v for (v, _, _) in [list(s)[0] for s in page_count_rank.values()]))
ev = pq.evidence_pages.map(ast.literal_eval).map(lambda xs: [int(x) for x in xs])
ev_min = min(min(x) for x in ev); ev_out = sum(any(p < 1 or p > pq.page_count[q] for p in x) for q, x in ev.items())
print("evidence page min:", ev_min, "| questions with evidence page outside 1..page_count:", ev_out)
print("empty evidence lists in P0:", int((ev.map(len) == 0).sum()))
assert (ev.map(len) == pq.n_evidence).all()

# ---------------------------------------------------------------- labels
rk = {q: [int(p) for p in rank.loc[q, "pages"]] for q in rank.index}
lab = pd.DataFrame(index=pq.index)
lab["doc_id"] = pq.doc_id
lab["n_ev"] = ev.map(len)
lab["Y"] = [int(not set(ev[q]) <= set(rk[q][:4])) for q in pq.index]
lab["any4"] = [int(bool(set(ev[q]) & set(rk[q][:4]))) for q in pq.index]
lab["R"] = [int(lab.Y[q] == 1 and bool((set(ev[q]) - set(rk[q][:4])) & set(rk[q][4:8]))) for q in pq.index]
lab["C8"] = [int(set(ev[q]) <= set(rk[q][:8])) for q in pq.index]
lab["any8"] = [int(bool(set(ev[q]) & set(rk[q][:8]))) for q in pq.index]
# cross-check with frozen E5 metrics
y_frozen = (pq["recall@4_V"] < 1).astype(int)
print("Y vs frozen recall@4_V<1 mismatches:", int((lab.Y != y_frozen).sum()))
print("any@4 vs frozen hit@4_V mismatches:", int((lab.any4 != pq["hit@4_V"].astype(int)).sum()))
top5 = pq.top5_V.map(ast.literal_eval)
print("rankings top5 vs frozen top5_V mismatches:", int(sum(list(top5[q]) != rk[q][:5] for q in pq.index)))
fr = pq.first_rank_V
myfr = pd.Series({q: min(rk[q].index(p) + 1 for p in ev[q]) for q in pq.index})
print("first_rank_V mismatches:", int((myfr != fr).sum()))
# if the rankings were 0-based relative to evidence, shifting by 1 should look worse:
y_shift = [int(not set(ev[q]) <= set(p + 1 for p in rk[q][:4])) for q in pq.index]
print("(sensitivity) mismatches vs frozen if rankings shifted +1:", int((np.array(y_shift) != y_frozen.values).sum()))
print("base rate Y:", int(lab.Y.sum()), "/", len(lab), "| R:", int(lab.R.sum()), "| complete@8 not @4:", int(((lab.C8 == 1) & (lab.Y == 1)).sum()),
      "| none in top8:", int((lab.any8 == 0).sum()), "| incomplete & none in top8:", int(((lab.any8 == 0) & (lab.Y == 1)).sum()))

# ---------------------------------------------------------------- E8 pages read == V top 4
print("\n== E8 pages read ==")
mismatch = {"L-B1": 0, "L-B1r": 0}; order_rank = {"L-B1": 0, "L-B1r": 0}; counts = {}
lv1_sub = 0
for rec in records:
    pages = []
    for m in rec["request"]["messages"]:
        if isinstance(m["content"], list):
            for part in m["content"]:
                if part["type"] == "text" and part["text"].startswith("[Page "):
                    pages.append(int(part["text"][6:].split("]")[0]))
    counts[rec["arm"]] = counts.get(rec["arm"], 0) + 1
    if rec["arm"] in mismatch:
        if set(pages) != set(rk[rec["qid"]][:4]) or len(pages) != 4:
            mismatch[rec["arm"]] += 1
        if pages == rk[rec["qid"]][:4]:
            order_rank[rec["arm"]] += 1
print("records per arm:", counts)
print("L-B1/L-B1r requests whose [Page N] set != V top-4:", mismatch, "| in rank order:", order_rank)

# U4 from the raw parsed reply vs the evaluation table's `abstained`
reply_abst = {rec["qid"]: int(rec["parsed"]["answer"] == "Not answerable") for rec in records if rec["arm"] == "L-B1"}
print("U4 (exact 'Not answerable' in parsed reply) vs table abstained mismatches:",
      int(sum(reply_abst[q] != int(lb1.abstained[q]) for q in lb1.index)))

# ---------------------------------------------------------------- signals on P_deploy
sig = pd.DataFrame(index=rank.index)
sig["doc_id"] = rank.doc_id
for q in rank.index:
    s = np.asarray(rank.loc[q, "scores"], dtype=float)
    sig.loc[q, "U1_margin_45"] = -(s[3] - s[4]) / s[0]
    sig.loc[q, "U2_top_standout"] = -(s[0] - s.mean()) / s.std(ddof=0)
    sig.loc[q, "U3_flatness_18"] = -(s[0] - s[7]) / s[0]
    sig.loc[q, "s1"] = s[0]
    sig.loc[q, "n_pages"] = len(s)
sig["U4_abstained"] = [reply_abst[q] for q in sig.index]
ns = lb1.numeric_support.reindex(sig.index)
sig["U5_numeric_unsupported"] = [int(v is False or v == "False" or (isinstance(v, (bool, np.bool_)) and not v)) if not pd.isna(v) else 0 for v in ns]
print("\nmin s1:", sig.s1.min(), "| U5 positives:", int(sig.U5_numeric_unsupported.sum()), "| U4 positives:", int(sig.U4_abstained.sum()))

thr = {}
for u in SIGNALS:
    thr[u] = 1.0 if u in BINARY else float(np.percentile(sig[u].values, 60))
trig = pd.DataFrame({u: (sig[u] >= thr[u]) if u not in BINARY else (sig[u] == 1) for u in SIGNALS})
# percentile-method sensitivity for continuous signals
for u in SIGNALS:
    if u in BINARY:
        continue
    alt = {m: int((sig[u] >= np.percentile(sig[u].values, 60, method=m)).sum()) for m in ["linear", "lower", "higher", "nearest", "midpoint"]}
    print(f"{u}: threshold {thr[u]:.6f}; triggered/118 by percentile method {alt}")

# ---------------------------------------------------------------- statistics
def auroc_pairs(x, y):
    x = np.asarray(x, float); y = np.asarray(y, int)
    pos, neg = x[y == 1], x[y == 0]
    if len(pos) == 0 or len(neg) == 0:
        return np.nan
    d = pos[:, None] - neg[None, :]
    return ((d > 0).sum() + 0.5 * (d == 0).sum()) / (len(pos) * len(neg))

P0 = lab.join(sig.drop(columns=["doc_id"])).join(trig.add_prefix("T_"))
docs = sorted(P0.doc_id.unique())
assert len(docs) == 14
idx_by_doc = [np.flatnonzero(P0.doc_id.values == d) for d in docs]
Yv = P0.Y.values

rng = np.random.default_rng(int(S0["statistics"]["bootstrap"].split("seed ")[1].split(";")[0]))
B = 10_000
draws = rng.integers(0, len(docs), size=(B, len(docs)))
res = {}
for u in SIGNALS:
    x = P0[u].values; t = P0["T_" + u].values
    a = auroc_pairs(x, Yv)
    prec = Yv[t].mean(); base = Yv.mean()
    lodo = [auroc_pairs(x[P0.doc_id.values != d], Yv[P0.doc_id.values != d]) for d in docs]
    ab, lb = [], []
    disc = 0
    for row in draws:
        ii = np.concatenate([idx_by_doc[j] for j in row])
        yy = Yv[ii]
        if yy.min() == yy.max():
            disc += 1
            continue
        ab.append(auroc_pairs(x[ii], yy))
        tt = t[ii]
        lb.append(yy[tt].mean() - yy.mean() if tt.any() else np.nan)
    ab = np.array(ab); lb = np.array(lb)
    p = (1 + (ab <= 0.5).sum()) / (1 + len(ab))
    res[u] = dict(auroc=a, auroc_ci95=list(np.percentile(ab, [2.5, 97.5])), p_one_sided=p, lift=prec - base, precision=prec,
                  lift_ci95=list(np.nanpercentile(lb, [2.5, 97.5])), lift_nan_draws=int(np.isnan(lb).sum()), lodo_min=min(lodo),
                  triggered_P0=int(t.sum()), recoverable_triggered=int((t & (P0.R.values == 1)).sum()), draws_discarded=disc,
                  auroc_recoverable=auroc_pairs(x, P0.R.values))
# Holm step-down
order = sorted(SIGNALS, key=lambda u: res[u]["p_one_sided"])
running = 0.0
for i, u in enumerate(order):
    running = max(running, min(1.0, (len(SIGNALS) - i) * res[u]["p_one_sided"]))
    res[u]["p_holm"] = running
for u in SIGNALS:
    r = res[u]
    r["G1"] = r["auroc"] >= 0.65
    r["G2"] = r["p_holm"] <= 0.05
    r["G3"] = r["lift"] >= 0.15 and r["lift_ci95"][0] > 0
    r["G4"] = r["lodo_min"] >= 0.60
    r["G5"] = r["recoverable_triggered"] >= 6
    r["passes"] = all(r[g] for g in ["G1", "G2", "G3", "G4", "G5"])
passing = [u for u in SIGNALS if res[u]["passes"]]
selected = max(passing, key=lambda u: (res[u]["auroc"], -SIGNALS.index(u))) if passing else None
print("\n== reproduction ==")
print("passing:", passing, "| selected:", selected, "| threshold:", thr.get(selected))

# ---------------------------------------------------------------- compare with notebook outputs
summ = json.loads((ROOT / "data/processed/mmlongbench_doc/e9/stage0_summary.json").read_text())
rows = []
for u in SIGNALS:
    g = summ["gate"][u]; r = res[u]
    for k in ["auroc", "p_one_sided", "p_holm", "lift", "precision", "lodo_min", "auroc_recoverable", "triggered_P0", "recoverable_triggered", "draws_discarded"]:
        rows.append((u, k, g[k], r[k], abs(g[k] - r[k])))
    for k in ["auroc_ci95", "lift_ci95"]:
        for j in range(2):
            rows.append((u, f"{k}[{j}]", g[k][j], r[k][j], abs(g[k][j] - r[k][j])))
    for k in ["G1", "G2", "G3", "G4", "G5", "passes"]:
        rows.append((u, k, g[k], r[k], float(g[k] != r[k])))
    rows.append((u, "threshold", summ["thresholds"][u], thr[u], abs(summ["thresholds"][u] - thr[u])))
cmp = pd.DataFrame(rows, columns=["signal", "metric", "notebook", "audit", "absdiff"])
pd.set_option("display.width", 200)
print(cmp.to_string(index=False, float_format=lambda v: f"{v:.6f}"))
print("max absdiff point estimates:", cmp[~cmp.metric.str.contains("ci95|p_")].absdiff.max(),
      "| max absdiff CIs:", cmp[cmp.metric.str.contains("ci95")].absdiff.max(),
      "| max absdiff p:", cmp[cmp.metric.str.startswith("p_")].absdiff.max())
print("selected match:", summ["selected_trigger"] == selected, "| passed match:", summ["stage0_passed"] == bool(passing))
hd = summ["headroom"]
mine_hd = {"incomplete_at_4": int(lab.Y.sum()), "recoverable_ranks_5_8": int(lab.R.sum()),
           "complete_at_8_not_4": int(((lab.C8 == 1) & (lab.Y == 1)).sum()), "no_evidence_in_top_8": int((lab.any8 == 0).sum())}
print("headroom notebook:", hd, "| audit:", mine_hd)
print("population notebook:", summ["population"], "| base rate", summ["base_rate_incomplete"], "audit", round(Yv.mean(), 6))
# strata
for name, mask in [("single-page", P0.n_ev.values == 1), ("multi-page", P0.n_ev.values > 1)]:
    st = {u: auroc_pairs(P0[u].values[mask], Yv[mask]) for u in SIGNALS}
    d = max(abs(st[u] - summ["strata_auroc"][name][u]) for u in SIGNALS)
    print(f"strata {name}: n={mask.sum()} incomplete={Yv[mask].sum()} max absdiff vs notebook {d:.2e}")

# per-question file
nbq = pd.read_csv(ROOT / "data/processed/mmlongbench_doc/e9/stage0_per_question.csv").set_index("qid")
assert set(nbq.index) == set(sig.index)
for u in SIGNALS:
    print(f"per-question {u}: max |value diff| {np.max(np.abs(nbq[u].reindex(sig.index).values - sig[u].values)):.2e}; trigger mismatches "
          f"{int((nbq['trigger_' + u].reindex(sig.index).astype(bool).values != trig[u].values).sum())}")
lab_nb = nbq.loc[nbq.labelled == True]
for a, b in [("incomplete", "Y"), ("recoverable", "R"), ("complete_at_8", "C8"), ("any_at_4", "any4")]:
    print(f"per-question {a}: mismatches {int((lab_nb[a].reindex(lab.index).astype(bool).astype(int) != lab[b]).sum())}")

# ---------------------------------------------------------------- foundations: between-document structure
print("\n== between-document vs within-document ==")
U = "U3_flatness_18"
m = ~P0.doc_id.isin(TENK).values
print("10-K questions in P0:", int((~m).sum()), "| Y among 10-K:", int(Yv[~m].sum()), "| Y among others:", int(Yv[m].sum()), "/", int(m.sum()))
print("U3 AUROC excluding both 10-Ks:", round(auroc_pairs(P0[U].values[m], Yv[m]), 4), "| U3 AUROC within 10-Ks only:", round(auroc_pairs(P0[U].values[~m], Yv[~m]), 4))
num = den = 0.0; per_doc = []
for d in docs:
    mm = P0.doc_id.values == d
    y = Yv[mm]; x = P0[U].values[mm]
    npos, nneg = y.sum(), (1 - y).sum()
    a = auroc_pairs(x, y)
    per_doc.append((d[:28], int(mm.sum()), int(npos), None if np.isnan(a) else round(a, 3),
                    round(float(P0[U].values[mm].mean()), 3), int(P0["T_" + U].values[mm].sum())))
    if npos and nneg:
        num += a * npos * nneg; den += npos * nneg
print("within-document AUROC (pair-weighted mean over docs with both classes):", round(num / den, 4), "| comparable pairs:", int(den),
      "of", int(Yv.sum() * (1 - Yv).sum()))
print(pd.DataFrame(per_doc, columns=["doc", "n", "Y", "auroc", "meanU3", "trig"]).to_string(index=False))
# document-level only: replace U3 by its document mean
dm = P0.groupby("doc_id")[U].transform("mean").values
print("AUROC of document-mean U3 (pure between-document signal):", round(auroc_pairs(dm, Yv), 4))
dmy = P0.groupby("doc_id").Y.transform("mean").values
print("AUROC of document base rate (oracle between-doc, leave-in):", round(auroc_pairs(dmy, Yv), 4))
# residual within-doc
print("AUROC of U3 - doc mean(U3):", round(auroc_pairs(P0[U].values - dm, Yv), 4))

print("\n== proxies ==")
P0["page_count"] = pq.page_count
print("AUROC page_count -> Y:", round(auroc_pairs(P0.page_count.values, Yv), 4))
print("AUROC n_evidence -> Y:", round(auroc_pairs(P0.n_ev.values, Yv), 4))
def spearman(a, b):
    return np.corrcoef(pd.Series(a).rank().values, pd.Series(b).rank().values)[0, 1]
print("Pearson/Spearman U3 vs page_count (P0):", round(np.corrcoef(P0[U], P0.page_count)[0, 1], 3), round(spearman(P0[U].values, P0.page_count.values), 3))
print("Pearson/Spearman U3 vs log page_count (P0):", round(np.corrcoef(P0[U], np.log(P0.page_count))[0, 1], 3))
print("Spearman U3 vs n_evidence (P0):", round(spearman(P0[U].values, P0.n_ev.values), 3))
print("Spearman U3 vs page_count over 118 (from ranking length):", round(spearman(sig[U].values, sig.n_pages.values), 3))
# AUROC of U3 within n_evidence strata already given; also partial: within page-count terciles?
# trigger rate by doc length
# ---------------------------------------------------------------- practical usefulness
print("\n== operating point (U3) ==")
T = trig[U]
print("triggered on 118:", int(T.sum()), f"({T.mean():.3f})")
tp = P0["T_" + U].values
R = P0.R.values; C8n4 = ((P0.C8 == 1) & (P0.Y == 1)).values
print("recoverable (15): triggered", int((tp & (R == 1)).sum()), "missed", int((~tp & (R == 1)).sum()))
print("complete@8-not-@4 (8): triggered", int((tp & C8n4).sum()), "missed", int((~tp & C8n4).sum()))
print("complete@4 (62): triggered (wasted)", int((tp & (Yv == 0)).sum()))
print("incomplete but not recoverable at 8 (", int(((Yv == 1) & (R == 0)).sum()), "): triggered", int((tp & (Yv == 1) & (R == 0)).sum()))
unans = [q for q in sig.index if not lb1.answerable[q]]
print("unanswerable (", len(unans), "): triggered", int(T[unans].sum()))
noP0ans = [q for q in ans_no_label]
print("answerable-without-label triggered:", {q: bool(T[q]) for q in noP0ans})
# R AUROC for U3 vs random policy with same rate
print("recoverable capture rate:", round((tp & (R == 1)).sum() / R.sum(), 3), "vs trigger rate on P0", round(tp.mean(), 3))
print("10-K questions triggered:", int(tp[~m].sum()), "of", int((~m).sum()), "| non-10-K triggered:", int(tp[m].sum()), "of", int(m.sum()))
# which doc do recoverable triggered come from
print("recoverable by doc (triggered/total):", P0[P0.R == 1].groupby("doc_id")["T_" + U].agg(["sum", "count"]).to_dict("index"))
# G5 counted on P0 only; check same on unlabelled? n/a
# sensitivity: selection if threshold method changed
for meth in ["lower", "higher", "nearest"]:
    th = np.percentile(sig[U].values, 60, method=meth)
    tt = (P0[U].values >= th)
    print(f"threshold method {meth}: thr {th:.6f} trig P0 {tt.sum()} recoverable {int((tt & (R == 1)).sum())} lift {Yv[tt].mean() - Yv.mean():.4f}")

# ---------------------------------------------------------------- extra robustness / interpretation
print("\n== extra ==")
x3 = P0[U].values
ne = P0.n_ev.values
print("n_evidence > 4 (incomplete by construction at k=4):", int((ne > 4).sum()), "| n_evidence > 8:", int((ne > 8).sum()))
mm = ne <= 4
print("U3 AUROC on n_evidence<=4:", round(auroc_pairs(x3[mm], Yv[mm]), 4), f"(n={mm.sum()}, Y={Yv[mm].sum()})")
for k in [1, 2, 3, 4]:
    mk = ne == k
    print(f"  n_ev={k}: n={mk.sum()} Y={Yv[mk].sum()} AUROC={auroc_pairs(x3[mk], Yv[mk])}")
# within-document permutation test (shuffle U3 within each document)
rngp = np.random.default_rng(1)
obs = auroc_pairs(x3, Yv)
cnt = 0
for _ in range(5000):
    xp = x3.copy()
    for ii in idx_by_doc:
        xp[ii] = xp[rngp.permutation(ii)]
    cnt += auroc_pairs(xp, Yv) >= obs
print("within-document permutation p (U3 shuffled within docs, 5000):", (1 + cnt) / 5001)
# cluster bootstrap CIs for excl-10K AUROC and within-doc AUROC
docs_n = [d for d in docs if d not in TENK]
idx_n = [np.flatnonzero(P0.doc_id.values == d) for d in docs_n]
rngb = np.random.default_rng(2)
a_ex, a_wd = [], []
for _ in range(4000):
    row = rngb.integers(0, len(docs_n), len(docs_n))
    ii = np.concatenate([idx_n[j] for j in row])
    if Yv[ii].min() != Yv[ii].max():
        a_ex.append(auroc_pairs(x3[ii], Yv[ii]))
    row2 = rngb.integers(0, len(docs), len(docs))
    num = den = 0.0
    for j in row2:
        ii = idx_by_doc[j]; y = Yv[ii]
        npos, nneg = y.sum(), len(y) - y.sum()
        if npos and nneg:
            num += auroc_pairs(x3[ii], y) * npos * nneg; den += npos * nneg
    if den:
        a_wd.append(num / den)
print("excl-10K AUROC 95% cluster CI:", np.round(np.percentile(a_ex, [2.5, 97.5]), 3), "| P(<=0.5)", round(np.mean(np.array(a_ex) <= 0.5), 4))
print("within-doc AUROC 95% cluster CI:", np.round(np.percentile(a_wd, [2.5, 97.5]), 3), "| P(<=0.5)", round(np.mean(np.array(a_wd) <= 0.5), 4))
pdoc = [a for a in [auroc_pairs(x3[ii], Yv[ii]) for ii in idx_by_doc] if not np.isnan(a)]
print("per-doc AUROC >0.5 / =0.5 / <0.5:", sum(a > 0.5 for a in pdoc), sum(a == 0.5 for a in pdoc), sum(a < 0.5 for a in pdoc))
# recoverable-only discrimination
print("U3 AUROC Y_recoverable vs rest:", round(auroc_pairs(x3, P0.R.values), 4),
      "| C8-not-4 vs rest:", round(auroc_pairs(x3, C8n4.astype(int)), 4),
      "| among Y=1, recoverable vs not:", round(auroc_pairs(x3[Yv == 1], P0.R.values[Yv == 1]), 4))
# random-trigger null for G5: hypergeometric P(>= k recoverable | 40 of 101 drawn, 15 recoverable)
from math import comb
N, K, n = 101, 15, int(tp.sum())
def hyp_ge(k):
    return sum(comb(K, i) * comb(N - K, n - i) for i in range(k, min(K, n) + 1)) / comb(N, n)
print(f"random {n}/101 trigger: E[recoverable]={n*K/N:.2f}; P(>=6)={hyp_ge(6):.3f}; P(>=8)={hyp_ge(8):.3f}")
print("recoverable precision among triggered P0:", f"{(tp & (R == 1)).sum()}/{tp.sum()} = {(tp & (R == 1)).mean() / tp.mean():.3f}", "vs base", round(R.mean(), 3))
# descriptive: current L-B1 S-v1 correctness on the groups the trigger touches (development data)
s1c = lb1.s1_correct.reindex(P0.index).astype(bool).values
print("L-B1 S-v1 wrong among triggered recoverable:", int((tp & (R == 1) & ~s1c).sum()), "of", int((tp & (R == 1)).sum()),
      "| among triggered complete@8-not-4:", int((tp & C8n4 & ~s1c).sum()), "of", int((tp & C8n4).sum()),
      "| among all 15 recoverable:", int(((R == 1) & ~s1c).sum()),
      "| triggered and currently correct (break risk):", int((tp & s1c).sum()), "of", int(tp.sum()))
