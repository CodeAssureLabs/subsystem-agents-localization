"""Re-score every run under the unified gold-set definitions.

Outputs results.json with:
  - per window x method x gold: micro P/R/F1 (mean and 95% t-CI over runs),
    instance-level cluster-bootstrap CI, all-gold counts, set size, tokens;
  - pooled (all 57 instances) results;
  - new-file vs existing-file analysis;
  - paired Wilcoxon tests with Holm correction;
  - fixed-commit sensitivity analysis;
  - plain-LLM ensembling (extra inference without exploration).
"""
import json
import math
import random
import statistics
from collections import defaultdict

import numpy as np
from scipy import stats

from common import HERE, is_source, load_gold, load_runs, micro, inst_f1, prf, score_instance, tree

B = 5000
rng = np.random.default_rng(7)
runs = load_runs()["runs"]
gold = load_gold()
# Every window that has recorded runs (Ansible windows first, then added repositories).
WINDOWS = [w for w in ["2020", "2025", "2026", "openlibrary", "qutebrowser"] if w in runs]
METHODS = ["plain_haiku", "plain_sonnet", "rlm_haiku", "rlm_sonnet", "ds_nospawn", "ds_adaptive",
           "ds_adaptive_t300", "ds_nudged", "codex", "rrl", "agentless", "cosil", "locagent"]


def gold_map(window, kind):
    return {iid: (g[kind] if g[kind] is not None else set()) for iid, g in gold[window].items()}


# Source-file localization (G_SRC, G_SWE) excludes tests, changelogs and build metadata, so
# predictions outside that scope are removed before scoring, for every method alike.
SOURCE_KINDS = ("SRC", "SWE")


def run_preds(run, kind=None):
    keep = is_source if kind in SOURCE_KINDS else (lambda f: True)
    return {iid: {f for f in v["pred"] if keep(f)} for iid, v in run["instances"].items()}


def tci(xs):
    if len(xs) < 2:
        return None
    m = statistics.mean(xs)
    s = statistics.stdev(xs)
    return stats.t.ppf(0.975, len(xs) - 1) * s / math.sqrt(len(xs))


def bootstrap_micro(cells):
    """cells: list over instances of list over runs of (tp, fp, fn). Resample instances."""
    arr = np.array([[sum(c[0] for c in cell), sum(c[1] for c in cell), sum(c[2] for c in cell)] for cell in cells], float)
    n = len(arr)
    fs = []
    for _ in range(B):
        idx = rng.integers(0, n, n)
        tp, fp, fn = arr[idx].sum(0)
        fs.append(prf(tp, fp, fn)[2])
    return float(np.percentile(fs, 2.5)), float(np.percentile(fs, 97.5))


def evaluate(window, method, kind, instances=None):
    gm = gold_map(window, kind)
    if instances is not None:
        gm = {k: v for k, v in gm.items() if k in instances}
    rs = runs[window].get(method, [])
    if not rs:
        return None
    per_run = [micro(run_preds(r, kind), gm) for r in rs]
    cells = []
    for iid, g in gm.items():
        if not g:
            continue
        cells.append([score_instance(run_preds(r, kind).get(iid, set()), g) for r in rs])
    f1s = [x["F1"] for x in per_run]
    hard = [sum(1 for iid, g in gm.items() if g and gold[window][iid]["hard"] and set(g) <= run_preds(r, kind).get(iid, set())) for r in rs]
    lo, hi = bootstrap_micro(cells)
    tok = [v["tokens"] for r in rs for v in r["instances"].values()]
    return {
        "n_runs": len(rs),
        "P": statistics.mean(x["P"] for x in per_run),
        "R": statistics.mean(x["R"] for x in per_run),
        "F1": statistics.mean(f1s),
        "F1_tci": tci(f1s),
        "F1_boot": [lo, hi],
        "F1_runs": f1s,
        "all_gold": statistics.mean(x["all_gold"] for x in per_run),
        "all_gold_tci": tci([x["all_gold"] for x in per_run]),
        "hard_all_gold": statistics.mean(hard),
        "n_inst": per_run[0]["n"],
        "set_size": statistics.mean(len(v["pred"]) for r in rs for v in r["instances"].values()),
        "tokens_per_inst_median": statistics.median(tok),
        "tokens_per_inst_mean": statistics.mean(tok),
        "init_tokens": statistics.mean(r["init_tokens"] for r in rs),
        "cost_per_inst": (statistics.mean(v["cost_usd"] for r in rs for v in r["instances"].values())
                          if all("cost_usd" in v for r in rs for v in r["instances"].values()) else None),
    }


def pooled(method, kind, windows=("2020", "2025", "2026")):
    """Micro-F1 over the instances of `windows` (default: the 57 Ansible issues), pooling runs."""
    cells = []
    for w in windows:
        rs = runs[w].get(method, [])
        if not rs:
            return None
        for iid, g in gold_map(w, kind).items():
            if g:
                cells.append([score_instance(run_preds(r, kind).get(iid, set()), g) for r in rs])
    # Runs per window differ (5 in 2020, 3 later), so TP/FP/FN are averaged over
    # runs within each instance before pooling; every instance then has equal weight.
    norm = [[(c[0] / len(cell), c[1] / len(cell), c[2] / len(cell)) for c in cell] for cell in cells]
    tp = sum(sum(c[0] for c in cell) for cell in norm)
    fp = sum(sum(c[1] for c in cell) for cell in norm)
    fn = sum(sum(c[2] for c in cell) for cell in norm)
    p, r, f = prf(tp, fp, fn)
    lo, hi = bootstrap_micro(norm)
    return {"P": p, "R": r, "F1": f, "F1_boot": [lo, hi], "n_inst": len(cells)}


def per_instance_f1(window, method, kind):
    gm = gold_map(window, kind)
    rs = runs[window][method]
    return {iid: statistics.mean(inst_f1(run_preds(r, kind).get(iid, set()), g) for r in rs) for iid, g in gm.items() if g}


def paired_test(a, b, kind, windows=("2020", "2025", "2026")):
    xs, ys = [], []
    for w in windows:
        if a not in runs[w] or b not in runs[w]:
            continue
        fa, fb = per_instance_f1(w, a, kind), per_instance_f1(w, b, kind)
        for iid in fa:
            xs.append(fa[iid]); ys.append(fb[iid])
    xs, ys = np.array(xs), np.array(ys)
    d = xs - ys
    nz = d[d != 0]
    if len(nz) == 0:
        return {"n": len(d), "p": 1.0}
    res = stats.wilcoxon(xs, ys, zero_method="wilcox", alternative="two-sided")
    ranks = stats.rankdata(np.abs(nz))
    rbc = (ranks[nz > 0].sum() - ranks[nz < 0].sum()) / ranks.sum()
    gt = sum(1 for x in xs for y in ys if x > y); lt = sum(1 for x in xs for y in ys if x < y)
    cliff = (gt - lt) / (len(xs) * len(ys))
    return {"n": int(len(d)), "mean_a": float(xs.mean()), "mean_b": float(ys.mean()), "median_diff": float(np.median(d)),
            "W": float(res.statistic), "p": float(res.pvalue), "rank_biserial": float(rbc), "cliff": float(cliff),
            "wins": int((d > 0).sum()), "losses": int((d < 0).sum()), "ties": int((d == 0).sum())}


def holm(ps):
    order = sorted(range(len(ps)), key=lambda i: ps[i])
    adj = [0.0] * len(ps)
    running = 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (len(ps) - rank) * ps[i]))
        adj[i] = running
    return adj


def new_file_analysis(window, method):
    """Split predictions into paths that exist at the base commit and paths that do not."""
    rs = runs[window][method]
    out = defaultdict(float)
    for r in rs:
        for iid, v in r["instances"].items():
            g = gold[window][iid]
            t = tree(g["base_commit"])
            pred = set(v["pred"])
            p_exist = {p for p in pred if p in t}
            p_new = pred - p_exist
            out["pred_exist"] += len(p_exist)
            out["pred_nonexist"] += len(p_new)
            out["new_hit"] += len(p_new & g["PR_NEW"])
            out["phantom"] += len(p_new - g["PR_NEW"])
            ex = score_instance(p_exist, g["PR_EXIST"])
            out["ex_tp"] += ex[0]; out["ex_fp"] += ex[1]; out["ex_fn"] += ex[2]
            out["gold_new"] += len(g["PR_NEW"])
    k = len(rs)
    res = {key: val / k for key, val in out.items()}
    res["existing_F1"] = prf(out["ex_tp"], out["ex_fp"], out["ex_fn"])[2]
    res["existing_P"], res["existing_R"] = prf(out["ex_tp"], out["ex_fp"], out["ex_fn"])[:2]
    res["new_recall"] = out["new_hit"] / out["gold_new"] if out["gold_new"] else 0.0
    res["phantom_rate"] = out["phantom"] / (out["pred_exist"] + out["pred_nonexist"]) if out["pred_exist"] + out["pred_nonexist"] else 0.0
    return res


def ensemble(window, method, rule):
    rs = runs[window][method]
    preds = {}
    for iid in gold[window]:
        sets = [set(r["instances"][iid]["pred"]) for r in rs]
        if rule == "union":
            preds[iid] = set().union(*sets)
        else:
            cnt = defaultdict(int)
            for s in sets:
                for f in s:
                    cnt[f] += 1
            preds[iid] = {f for f, c in cnt.items() if c * 2 > len(sets)}
    return preds


def main():
    out = {"by_window": {}, "pooled": {}, "tests": {}, "new_files": {}, "sensitivity": {}, "ensembles": {}, "consultation": {}}
    for w in WINDOWS:
        out["by_window"][w] = {}
        kinds = ["SRC", "PR_EXIST", "PR"] + (["SWE"] if w == "2020" else [])
        for m in METHODS:
            if m not in runs[w]:
                continue
            out["by_window"][w][m] = {k: evaluate(w, m, k) for k in kinds}
            out["new_files"].setdefault(w, {})[m] = new_file_analysis(w, m)
    for m in METHODS:
        if all(m in runs[w] for w in ("2020", "2025", "2026")):
            out["pooled"][m] = {k: pooled(m, k) for k in ["SRC", "PR_EXIST", "PR"]}
    if len(WINDOWS) > 3:
        out["pooled_all"] = {m: {k: pooled(m, k, WINDOWS) for k in ["SRC", "PR_EXIST"]}
                             for m in METHODS if all(m in runs[w] for w in WINDOWS)}

    # Pre-declared comparison family (pooled over the 57 instances, G_SRC).
    family = [
        ("ds_adaptive", "plain_haiku", "domain agents vs plain LLM (same model)"),
        ("ds_adaptive", "rlm_haiku", "domain agents vs single-agent RLM (same model)"),
        ("ds_nospawn", "rlm_haiku", "coordinator+bounded I/O vs RLM REPL (same model)"),
        ("ds_adaptive", "ds_nospawn", "adding registry + domain agents"),
        ("rlm_haiku", "plain_haiku", "REPL access vs none (Haiku)"),
        ("rlm_sonnet", "plain_sonnet", "REPL access vs none (Sonnet)"),
        ("ds_adaptive", "plain_sonnet", "domain agents (Haiku) vs plain LLM (Sonnet)"),
        ("ds_adaptive", "rlm_sonnet", "domain agents (Haiku) vs RLM (Sonnet)"),
        ("ds_adaptive", "codex", "domain agents (Haiku) vs Codex"),
        ("ds_adaptive", "rrl", "domain agents vs Reformulate-Retrieve-Localize (same model)"),
        ("ds_adaptive", "agentless", "domain agents vs Agentless (same model)"),
        ("ds_adaptive", "cosil", "domain agents vs CoSIL (same model)"),
        ("ds_adaptive", "locagent", "domain agents vs LocAgent (same model)"),
    ]
    for kind in ["SRC", "PR_EXIST"]:
        tests = []
        for a, b, label in family:
            r = paired_test(a, b, kind)
            r.update({"a": a, "b": b, "label": label})
            tests.append(r)
        adj = holm([t["p"] for t in tests])
        for t, p in zip(tests, adj):
            t["p_holm"] = p
        # Consultation-policy comparison: only 2020, matched registry and timeout.
        nud = paired_test("ds_adaptive_t300", "ds_nudged", kind, windows=["2020"])
        nud.update({"a": "ds_adaptive_t300", "b": "ds_nudged", "label": "adaptive vs nudged (matched registry, 2020)"})
        out["tests"][kind] = {"family": tests, "nudge": nud}
        # Per-window spawn effect for transparency.
        out["tests"][kind]["spawn_by_window"] = {w: paired_test("ds_adaptive", "ds_nospawn", kind, windows=[w]) for w in WINDOWS}
        if len(WINDOWS) > 3:
            allt = []
            for a, b, label in family:
                r = paired_test(a, b, kind, windows=WINDOWS)
                r.update({"a": a, "b": b, "label": label})
                allt.append(r)
            for t, p in zip(allt, holm([t["p"] for t in allt])):
                t["p_holm"] = p
            out["tests"][kind]["family_all"] = allt

    # Sensitivity: drop 2020 instances whose G_SWE/G_SRC files are absent at the fixed commit.
    fixed = "01e7915b0a9778a934a0f0e9e9d110dbef7e31ec"
    t = tree(fixed)
    affected = {iid for iid, g in gold["2020"].items() if any(f not in t for f in g["SRC"])}
    keep = set(gold["2020"]) - affected
    out["sensitivity"]["affected_instances"] = sorted(affected)
    out["sensitivity"]["missing_files"] = {iid: sorted(f for f in gold["2020"][iid]["SRC"] if f not in t) for iid in affected}
    out["sensitivity"]["results"] = {m: {k: evaluate("2020", m, k, keep) for k in ["SWE", "SRC"]} for m in METHODS if m in runs["2020"]}

    # Ensembling plain LLM runs: more inference without repository exploration.
    for w in WINDOWS:
        out["ensembles"][w] = {}
        for m in ["plain_haiku", "plain_sonnet", "rlm_haiku"]:
            if m not in runs[w]:
                continue
            for rule in ["union", "majority"]:
                preds = ensemble(w, m, rule)
                res = {k: micro({i: {f for f in p if k not in SOURCE_KINDS or is_source(f)} for i, p in preds.items()},
                                gold_map(w, k)) for k in ["SRC", "PR_EXIST"]}
                tok = sum(v["tokens"] for r in runs[w][m] for v in r["instances"].values()) / 19
                out["ensembles"][w][f"{m}_{rule}"] = {"k": len(runs[w][m]), "tokens_per_inst": tok, **res}

    # Consultation behaviour.
    for w in WINDOWS:
        for m in ["ds_adaptive", "ds_adaptive_t300", "ds_nudged"]:
            if m not in runs[w]:
                continue
            calls = [v["subagent_calls"] or 0 for r in runs[w][m] for v in r["instances"].values()]
            out["consultation"].setdefault(w, {})[m] = {"calls_per_inst": statistics.mean(calls),
                                                        "frac_inst_with_call": statistics.mean(1 if c else 0 for c in calls)}

    json.dump(out, open(HERE / "results.json", "w"), indent=1, default=float)
    print("wrote results.json")


if __name__ == "__main__":
    main()
