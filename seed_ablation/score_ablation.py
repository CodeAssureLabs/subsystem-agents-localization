"""Seeding ablation: domain agents with and without the Agentless file-level candidates in the
coordinator prompt, on all 105 issues, plus offline combinations of the two methods' outputs.

Scoring follows analysis/evaluate.py: source-only predictions under G_SRC, run-averaged counts per
issue for pooled micro-F1 (issue-bootstrap CI), and the Wilcoxon signed-rank test on run-averaged
per-issue F1. Writes results.json here and tex/tables/seed.tex.

usage: python score_ablation.py
"""
import json
import sys
from pathlib import Path

import numpy as np
from scipy import stats

P = Path(__file__).resolve().parent
sys.path.insert(0, str(P.parent / ("analysis" if (P.parent / "analysis").is_dir() else "scripts")))
from common import load_gold, load_runs, prf, score_instance, is_source  # noqa: E402

WINDOWS = ["2020", "2025", "2026", "openlibrary", "qutebrowser"]
PARTS = {"2020": ["ansible_2020"], "2025": ["ansible_2025"], "2026": ["ansible_2026"],
         "openlibrary": ["openlibrary_pilot", "openlibrary_rest"], "qutebrowser": ["qutebrowser_pilot", "qutebrowser_rest"]}
B = 5000
rng = np.random.default_rng(0)
gold = load_gold()
R = load_runs()["runs"]
seeds = {k: json.load(open(P / f"seeds_agentless_run{k}.json")) for k in (1, 2, 3)}


def seeded(w):
    """The three seeded runs of window w as [{iid: {"pred", "tokens"}}], or None if incomplete."""
    runs = []
    for k in (1, 2, 3):
        run = {}
        for part in PARTS[w]:
            f = P / part / f"ds_seeded_{k}.json"
            if not f.exists():
                return None
            for r in json.load(open(f))["results"]:
                run[r["instance_id"]] = {"pred": r.get("predicted_files") or [], "tokens": r.get("total_tokens") or 0}
        runs.append(run)
    return runs


def existing(w, m):
    return [{i: {"pred": x["pred"], "tokens": x["tokens"]} for i, x in run["instances"].items()} for run in R[w][m]]


def combine(w, how):
    """Offline combinations of run k of the domain agents with run k of Agentless (and CoSIL)."""
    da, ag, co = existing(w, "ds_adaptive")[:3], existing(w, "agentless"), existing(w, "cosil")
    out = []
    for k in range(3):
        run = {}
        for i in da[k]:
            d, a, c = set(da[k][i]["pred"]), set(ag[k][i]["pred"]), set(co[k][i]["pred"])
            cheap = ag[k][i]["tokens"] + co[k][i]["tokens"]
            if how == "union":
                run[i] = {"pred": d | a, "tokens": da[k][i]["tokens"] + ag[k][i]["tokens"]}
            elif how == "intersection":
                run[i] = {"pred": d & a, "tokens": da[k][i]["tokens"] + ag[k][i]["tokens"]}
            elif how == "cascade":  # answer cheaply when Agentless and CoSIL return the same files
                agree = a == c and a
                run[i] = {"pred": a if agree else d, "tokens": cheap + (0 if agree else da[k][i]["tokens"]), "cheap": bool(agree)}
        out.append(run)
    return out


def preds(x, kind):
    return {p for p in x["pred"] if is_source(p)} if kind in ("SRC", "SWE") else set(x["pred"])


def cells(runs_by_w, kind):
    out = []
    for w, runs in runs_by_w.items():
        for i, g in gold[w].items():
            gs = set(g[kind])
            if gs:
                out.append((w, i, [score_instance(preds(run[i], kind), gs) for run in runs]))
    return out


def pooled(runs_by_w, kind):
    cs = cells(runs_by_w, kind)
    arr = np.array([[sum(c[j] for c in cell) / len(cell) for j in range(3)] for _, _, cell in cs])
    p, r, f = prf(*arr.sum(0))
    boots = [prf(*arr[rng.integers(0, len(arr), len(arr))].sum(0))[2] for _ in range(B)]
    return {"P": p, "R": r, "F1": f, "ci": [float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))]}


def per_issue(runs_by_w, kind):
    return {(w, i): float(np.mean([prf(*c)[2] for c in cell])) for w, i, cell in cells(runs_by_w, kind)}


def paired(a, b):
    keys = sorted(set(a) & set(b))
    xs, ys = np.array([a[k] for k in keys]), np.array([b[k] for k in keys])
    d = xs - ys
    nz = d[d != 0]
    res = stats.wilcoxon(xs, ys, zero_method="wilcox", alternative="two-sided")
    ranks = stats.rankdata(np.abs(nz))
    boots = [d[rng.integers(0, len(d), len(d))].mean() for _ in range(B)]
    return {"n": len(d), "mean_diff": float(d.mean()), "ci": [float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))],
            "wins": int((d > 0).sum()), "losses": int((d < 0).sum()), "ties": int((d == 0).sum()),
            "p": float(res.pvalue), "rank_biserial": float((ranks[nz > 0].sum() - ranks[nz < 0].sum()) / ranks.sum())}


def tokens(runs_by_w):
    """Mean tokens per issue, averaged over windows as in the main results table."""
    return float(np.mean([np.mean([x["tokens"] for run in runs for x in run.values()]) for runs in runs_by_w.values()]))


def main():
    done = [w for w in WINDOWS if seeded(w)]
    print("complete windows:", done)
    if not done:
        return
    S = {w: seeded(w) for w in done}
    M = {"ds_adaptive": {w: existing(w, "ds_adaptive") for w in done},
         "ds_seeded": S,
         "agentless": {w: existing(w, "agentless") for w in done},
         "union": {w: combine(w, "union") for w in done},
         "intersection": {w: combine(w, "intersection") for w in done},
         "cascade": {w: combine(w, "cascade") for w in done}}
    res = {"windows": done, "methods": {}, "tests": {}, "per_window": {}}
    for m, rb in M.items():
        res["methods"][m] = {k: pooled(rb, k) for k in ("SRC", "PR_EXIST")}
        res["methods"][m]["tokens"] = tokens(rb)
        print(f"{m:13s} SRC F1 {res['methods'][m]['SRC']['F1']:.3f} {np.round(res['methods'][m]['SRC']['ci'], 3)} "
              f"P {res['methods'][m]['SRC']['P']:.2f} R {res['methods'][m]['SRC']['R']:.2f} "
              f"EXIST {res['methods'][m]['PR_EXIST']['F1']:.3f} tokens {res['methods'][m]['tokens'] / 1e3:.0f}k")
    for kind in ("SRC", "PR_EXIST"):
        t = paired(per_issue(S, kind), per_issue(M["ds_adaptive"], kind))
        res["tests"][kind] = t
        print(f"seeded - unseeded [{kind}] {t['mean_diff']:+.3f} {np.round(t['ci'], 3)} W/L/T {t['wins']}/{t['losses']}/{t['ties']} "
              f"p={t['p']:.3f} r={t['rank_biserial']:+.2f}")
    for w in done:
        res["per_window"][w] = {m: pooled({w: M[m][w]}, "SRC")["F1"] for m in ("ds_adaptive", "ds_seeded")}
        res["per_window"][w]["p"] = paired(per_issue({w: S[w]}, "SRC"), per_issue({w: M["ds_adaptive"][w]}, "SRC"))["p"]
        print(f"  {w:12s} unseeded {res['per_window'][w]['ds_adaptive']:.3f} seeded {res['per_window'][w]['ds_seeded']:.3f} p={res['per_window'][w]['p']:.3f}")
    # How the seeded coordinator used the candidates.
    adopt = adopt_ok = other = other_ok = 0
    for w in done:
        for k, run in enumerate(S[w], 1):
            for i, x in run.items():
                for f in preds(x, "SRC"):
                    ok = f in gold[w][i]["SRC"]
                    if f in seeds[k][i]:
                        adopt += 1; adopt_ok += ok
                    else:
                        other += 1; other_ok += ok
    res["adoption"] = {"from_seed": adopt, "from_seed_correct": adopt_ok, "other": other, "other_correct": other_ok}
    cheap = [x.get("cheap", False) for rb in M["cascade"].values() for run in rb for x in run.values()]
    res["cascade_cheap_share"] = float(np.mean(cheap))
    print(f"seed files in seeded predictions: {adopt} ({adopt_ok / max(adopt, 1):.0%} correct); other files {other} "
          f"({other_ok / max(other, 1):.0%} correct); cascade answered cheaply on {res['cascade_cheap_share']:.0%}")
    json.dump(res, open(P / "results.json", "w"), indent=1)
    write_table(res)


LABEL = {"ds_adaptive": "Domain agents", "ds_seeded": "Domain agents, Agentless candidates in prompt",
         "agentless": "Agentless (file stage)", "union": "Union of domain agents and Agentless",
         "intersection": "Files predicted by both", "cascade": "Cascade (Agentless if it agrees with CoSIL)"}


def write_table(res):
    def fmt(v):
        return f"{v:.3f}".lstrip("0")
    rows = []
    for m in ("ds_adaptive", "ds_seeded", "agentless", "union", "intersection", "cascade"):
        x = res["methods"][m]
        tok = x["tokens"]
        tok = f"{tok / 1e6:.2f}M" if tok >= 1e5 else f"{tok / 1e3:.0f}k"
        rows.append(f"{LABEL[m]} & {fmt(x['SRC']['P'])} & {fmt(x['SRC']['R'])} & {fmt(x['SRC']['F1'])} [{fmt(x['SRC']['ci'][0])}, {fmt(x['SRC']['ci'][1])}] & {fmt(x['PR_EXIST']['F1'])} & {tok} \\\\")
        if m in ("ds_seeded", "agentless"):
            rows.append("\\midrule")
    t = res["tests"]["SRC"]
    tex = r"""\begin{table}[t]
\centering
\caption{Candidate files from Agentless (RQ3), over the 105 issues. In the second row the coordinator receives the Agentless candidates in its prompt (three runs). The last three rows combine the final outputs of existing runs without new LLM calls. Pooled micro-F1 under $G_{SRC}$ with 95\% issue-bootstrap intervals, and under $G_{PR}^{exist}$.}
\label{tab:seed}
\scriptsize
\setlength{\tabcolsep}{3pt}
\begin{tabular}{p{3.1cm}ccccc}
\toprule
& \multicolumn{3}{c}{$G_{SRC}$} & $G_{PR}^{exist}$ & \\
\cmidrule(lr){2-4}\cmidrule(lr){5-5}
Method & P & R & F1 [95\% CI] & F1 & Tokens \\
\midrule
""" + "\n".join(rows) + r"""
\bottomrule
\end{tabular}
\end{table}
"""
    (P.parent / "tex" / "tables" if (P.parent / "tex").is_dir() else P.parent / "tables").joinpath("seed.tex").write_text(tex)
    print("wrote tex/tables/seed.tex")


if __name__ == "__main__":
    main()
