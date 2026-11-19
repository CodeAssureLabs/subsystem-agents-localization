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
from pathlib import Path

import numpy as np
from scipy import stats

from common import HERE, is_source, load_gold, load_runs, micro, inst_f1, prf, score_instance, tree

B = 5000
rng = np.random.default_rng(7)
runs = load_runs()["runs"]
gold = load_gold()
# Every window that has recorded runs (Ansible windows first, then added repositories).
WINDOWS = [w for w in ["2020", "2025", "2026", "openlibrary", "qutebrowser"] if w in runs]
METHODS = ["plain_haiku", "plain_sonnet", "rlm_haiku", "rlm_sonnet", "ds_repl", "ds_nospawn", "ds_maponly", "ds_adaptive",
           "ds_adaptive_t300", "ds_nudged", "codex", "rrl", "agentless", "cosil", "locagent",
           "rrl_k", "agentless_k", "cosil_k", "locagent_k",
           "ds_seeded", "rlm_haiku_r0", "ds_nospawn_r0", "ds_adaptive_r0", "rlm_sonnet_r0", "codex_r0", "ds_nudged_r0"]
RANKED = ["rrl", "agentless", "cosil", "locagent"]
# Issues whose text was written for this study from the resolving PR (Ansible 2025 and 2026).
ORGANIC = [w for w in ["2020", "openlibrary", "qutebrowser"] if w in runs]

# Python source files only (G_SRC restricted to .py): the scope that the published localizers index.
for _w in gold.values():
    for _g in _w.values():
        _g["SRC_PY"] = {f for f in _g["SRC"] if f.endswith(".py")}


def gold_map(window, kind):
    return {iid: (g[kind] if g[kind] is not None else set()) for iid, g in gold[window].items()}


# Source-file localization (G_SRC, G_SWE) excludes tests, changelogs and build metadata, so
# predictions outside that scope are removed before scoring, for every method alike.
SOURCE_KINDS = ("SRC", "SWE", "SRC_PY")


def keep_fn(kind):
    if kind == "SRC_PY":
        return lambda f: is_source(f) and f.endswith(".py")
    return is_source if kind in SOURCE_KINDS else (lambda f: True)


def run_preds(run, kind=None):
    keep = keep_fn(kind)
    if "topk" in run:
        # Ranked list cut at K, after removing out-of-scope files (as for the non-LLM rankers).
        k = run["topk"]
        return {iid: set([f for f in v["ranked"] if keep(f)][:k]) for iid, v in run["instances"].items()}
    return {iid: {f for f in v["pred"] if keep(f)} for iid, v in run["instances"].items()}


def _pooled_f1_topk(tool, k, windows, kind="SRC"):
    tp = fp = fn = 0.0
    for w in windows:
        rs = runs[w].get(tool, [])
        for r in rs:
            pr = run_preds({**r, "topk": k}, kind)
            for iid, g in gold_map(w, kind).items():
                if g:
                    a, b, c = score_instance(pr.get(iid, set()), g)
                    tp += a / len(rs); fp += b / len(rs); fn += c / len(rs)
    return prf(tp, fp, fn)[2]


def add_topk_methods(kmax=10):
    """<tool>_k: each window uses the K that maximizes pooled G_SRC micro-F1 on the other windows."""
    choice, choice_org, curve = {}, {}, {}
    for tool in RANKED:
        if not all(tool in runs[w] for w in WINDOWS):
            continue
        curve[tool] = {k: _pooled_f1_topk(tool, k, WINDOWS) for k in range(1, kmax + 1)}
        for w in WINDOWS:
            others = [x for x in WINDOWS if x != w]
            k = max(range(1, kmax + 1), key=lambda k: (_pooled_f1_topk(tool, k, others), -k))
            choice.setdefault(tool, {})[w] = k
            runs[w][tool + "_k"] = [{**r, "topk": k} for r in runs[w][tool]]
        # For the 67-issue subset, K is chosen on the other SWE-bench Pro windows only, so the
        # generated Ansible 2025/2026 issues do not influence it (<tool>_ko).
        for w in ORGANIC:
            others = [x for x in ORGANIC if x != w]
            k = max(range(1, kmax + 1), key=lambda k: (_pooled_f1_topk(tool, k, others), -k))
            choice_org.setdefault(tool, {})[w] = k
            runs[w][tool + "_ko"] = [{**r, "topk": k} for r in runs[w][tool]]
    return {"K_by_window": choice, "K_by_window_organic": choice_org, "pooled_SRC_F1_by_K": curve}


def org_name(m):
    return m + "o" if m.endswith("_k") and m[:-2] in RANKED else m


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
        "set_size": statistics.mean(len(p) for r in rs for p in run_preds(r).values()),
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


def _cells(method, kind, windows):
    """{(window, iid): (tp, fp, fn, f1)} averaged over runs, for issues with non-empty gold."""
    out = {}
    for w in windows:
        rs = runs[w].get(method)
        if not rs:
            return None
        preds = [run_preds(r, kind) for r in rs]
        for iid, g in gold_map(w, kind).items():
            if not g:
                continue
            sc = [score_instance(p.get(iid, set()), g) for p in preds]
            out[(w, iid)] = tuple(sum(x[i] for x in sc) / len(sc) for i in range(3)) + (
                statistics.mean(prf(*x)[2] for x in sc),)
    return out


def paired_diff(a, b, kind, windows):
    """Pooled micro-F1 difference and mean per-issue F1 difference (a - b), with paired
    bootstrap 95% CIs (issues resampled, same resample for both methods)."""
    ca, cb = _cells(a, kind, windows), _cells(b, kind, windows)
    if not ca or not cb:
        return None
    keys = sorted(set(ca) & set(cb))
    A = np.array([ca[k] for k in keys]); Bm = np.array([cb[k] for k in keys])

    def stat(idx):
        ta, tb = A[idx].sum(0), Bm[idx].sum(0)
        return prf(*ta[:3])[2] - prf(*tb[:3])[2], (A[idx, 3] - Bm[idx, 3]).mean()

    d_micro, d_mean = stat(np.arange(len(keys)))
    boot = np.array([stat(rng.integers(0, len(keys), len(keys))) for _ in range(B)])
    return {"n": len(keys), "d_micro": float(d_micro), "d_micro_ci": [float(x) for x in np.percentile(boot[:, 0], [2.5, 97.5])],
            "d_mean": float(d_mean), "d_mean_ci": [float(x) for x in np.percentile(boot[:, 1], [2.5, 97.5])]}


def _cells_excluding(method, kind, windows, excl):
    """Like _cells, but each issue is averaged only over the runs not listed in `excl`
    ({(window, file name, instance_id)}); issues without a remaining run are left out."""
    out = {}
    for w in windows:
        rs = runs[w].get(method)
        if not rs:
            return None
        preds = [(Path(r.get("file", "")).name, run_preds(r, kind)) for r in rs]
        for iid, g in gold_map(w, kind).items():
            if not g:
                continue
            sc = [score_instance(p.get(iid, set()), g) for name, p in preds if (w, name, iid) not in excl]
            if sc:
                out[(w, iid)] = tuple(sum(x[i] for x in sc) / len(sc) for i in range(3)) + (
                    statistics.mean(prf(*x)[2] for x in sc),)
    return out


def sensitivity_repeated(kind="SRC"):
    """Results without the repeated issue runs: each affected trial is dropped (neither its first
    attempt nor its repetition is used) and the issue is averaged over its other repetitions.
    Comparisons use the issues that both sides keep."""
    man = HERE / "repeated_runs.json"
    if not man.exists():
        return None
    wmap = {"ansible_2020": "2020", "ansible_2025": "2025", "ansible_2026": "2026",
            "openlibrary": "openlibrary", "qutebrowser": "qutebrowser"}
    cond = {"ds_adaptive": "adaptive", "ds_maponly": "maponly", "ds_nospawn": "nospawn", "ds_nudged": "nudged",
            "ds_repl": "repl", "ds_seeded": "seeded"}
    rows = json.load(open(man))
    excl = {(wmap[x["window"]], f"{cond[x['method']]}_{x['run']}.json", x["instance_id"]) for x in rows}
    out = {"excluded_trials": len(excl), "methods": {}, "comparisons": []}
    for m in sorted({x["method"] for x in rows}):
        full, part = _cells(m, kind, WINDOWS), _cells_excluding(m, kind, WINDOWS, excl)
        f_full = prf(*np.array(list(full.values()))[:, :3].sum(0))[2]
        f_part = prf(*np.array(list(part.values()))[:, :3].sum(0))[2]
        out["methods"][m] = {"F1_reported": f_full, "F1_without": f_part, "delta": f_part - f_full,
                             "issues_reported": len(full), "issues_without": len(part)}
    for a, b in (("ds_maponly", "ds_nospawn"), ("ds_adaptive", "ds_maponly"), ("ds_adaptive", "ds_nospawn")):
        ca, cb = _cells_excluding(a, kind, WINDOWS, excl), _cells_excluding(b, kind, WINDOWS, excl)
        keys = sorted(set(ca) & set(cb))
        A = np.array([ca[k] for k in keys]); Bm = np.array([cb[k] for k in keys])
        d_micro = prf(*A[:, :3].sum(0))[2] - prf(*Bm[:, :3].sum(0))[2]
        boot = []
        for _ in range(B):
            idx = rng.integers(0, len(keys), len(keys))
            boot.append(prf(*A[idx, :3].sum(0))[2] - prf(*Bm[idx, :3].sum(0))[2])
        out["comparisons"].append({"a": a, "b": b, "n": len(keys), "d_micro": float(d_micro),
                                   "d_micro_ci": [float(x) for x in np.percentile(boot, [2.5, 97.5])],
                                   "d_mean": float((A[:, 3] - Bm[:, 3]).mean())})
    return out


def failure_stats(method, windows):
    """Empty predictions, recorded errors, step-limit endings and blocked access per issue run."""
    c = defaultdict(int)
    for w in windows:
        for r in runs[w].get(method, []):
            for v in r["instances"].values():
                c["issue_runs"] += 1
                c["empty"] += not v["pred"]
                c["error"] += bool(v.get("error"))
                c["empty_error"] += (not v["pred"]) and bool(v.get("error"))
                c["step_limit"] += bool(v.get("step_limit"))
                c["step_limit_empty"] += bool(v.get("step_limit")) and not v["pred"]
                c["blocked_runs"] += bool(v.get("blocked"))
                c["single_turn"] += v.get("root_iterations") == 1 or v.get("turns") == 1
    return dict(c)


def holm(ps):
    order = sorted(range(len(ps)), key=lambda i: ps[i])
    adj = [0.0] * len(ps)
    running = 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (len(ps) - rank) * ps[i]))
        adj[i] = running
    return adj


def path_kind(p):
    """source (G_SRC rule), test, changelog, or other non-source file."""
    if is_source(p):
        return "source"
    if p.startswith("changelogs/") or p.split("/")[-1].lower().startswith("changelog"):
        return "changelog"
    parts = p.split("/")
    if {"test", "tests", "testing"} & set(parts[:-1]) or p.split("/")[-1].startswith("test_") or p.endswith(("_test.py", "conftest.py")):
        return "test"
    return "other"


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
            for p in p_new:
                out["nonexist_" + path_kind(p)] += 1
                out["phantom_" + path_kind(p)] += p not in g["PR_NEW"]
            for p in g["PR_NEW"]:
                out["gold_new_" + path_kind(p)] += 1
                out["new_hit_" + path_kind(p)] += p in pred
            out["new_hit"] += len(p_new & g["PR_NEW"])
            out["phantom"] += len(p_new - g["PR_NEW"])
            ex = score_instance(p_exist, g["PR_EXIST"])
            out["ex_tp"] += ex[0]; out["ex_fp"] += ex[1]; out["ex_fn"] += ex[2]
            out["gold_new"] += len(g["PR_NEW"])
    k = len(rs)
    res = {key: val / k for key, val in out.items()}
    for kind in ("source", "test", "changelog", "other"):
        res["new_recall_" + kind] = (out["new_hit_" + kind] / out["gold_new_" + kind]) if out["gold_new_" + kind] else None
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


def combinations():
    """Output combinations of the default system with Agentless (run k with run k), under G_SRC:
    union, intersection, and a cascade that answers with Agentless when Agentless and CoSIL agree
    and calls the domain agents otherwise."""
    if not all(m in runs[w] for w in WINDOWS for m in ("ds_adaptive", "agentless", "cosil")):
        return None
    out = {}
    for rule in ("union", "intersection", "cascade"):
        tp = fp = fn = 0.0
        cheap = n = tok = 0.0
        for w in WINDOWS:
            ra, rg, rc = runs[w]["ds_adaptive"], runs[w]["agentless"], runs[w]["cosil"]
            k = min(len(ra), len(rg), len(rc))
            for i in range(k):
                pa, pg, pc = run_preds(ra[i], "SRC"), run_preds(rg[i], "SRC"), run_preds(rc[i], "SRC")
                for iid, g in gold_map(w, "SRC").items():
                    if not g:
                        continue
                    a, b, c = pa.get(iid, set()), pg.get(iid, set()), pc.get(iid, set())
                    if rule == "union":
                        pred = a | b
                    elif rule == "intersection":
                        pred = a & b
                    else:
                        agree = bool(b) and b == c
                        pred = b if agree else a
                        cheap += agree
                        tok += (rg[i]["instances"][iid]["tokens"] + rc[i]["instances"][iid]["tokens"]
                                + (0 if agree else ra[i]["instances"][iid]["tokens"]))
                    n += 1
                    x = score_instance(pred, g)
                    tp += x[0] / k; fp += x[1] / k; fn += x[2] / k
        P, Rr, F = prf(tp, fp, fn)
        out[rule] = {"P": P, "R": Rr, "F1": F}
        if rule == "cascade":
            full = sum(v["tokens"] for w in WINDOWS for r in runs[w]["ds_adaptive"][:3] for v in r["instances"].values())
            out[rule].update({"frac_cheap": cheap / n, "token_saving": 1 - tok / full if full else None})
    return out


def main():
    out = {"by_window": {}, "pooled": {}, "tests": {}, "new_files": {}, "sensitivity": {}, "ensembles": {}, "consultation": {}}
    out["topk"] = add_topk_methods()
    out["failures"] = {m: failure_stats(m, WINDOWS) for m in METHODS if any(m in runs[w] for w in WINDOWS)}
    for w in WINDOWS:
        out["by_window"][w] = {}
        kinds = ["SRC", "PR_EXIST", "PR", "SRC_PY"] + (["SWE"] if w == "2020" else [])
        for m in METHODS:
            if m not in runs[w]:
                continue
            out["by_window"][w][m] = {k: evaluate(w, m, k) for k in kinds}
            out["new_files"].setdefault(w, {})[m] = new_file_analysis(w, m)
    for m in METHODS:
        if all(m in runs[w] for w in ("2020", "2025", "2026")):
            out["pooled"][m] = {k: pooled(m, k) for k in ["SRC", "PR_EXIST", "PR"]}
    if len(WINDOWS) > 3:
        out["pooled_all"] = {m: {k: pooled(m, k, WINDOWS) for k in ["SRC", "PR_EXIST", "SRC_PY"]}
                             for m in METHODS if all(m in runs[w] for w in WINDOWS)}
        # The 67 issues whose text was not written for this study (Ansible 2020, Open Library, qutebrowser).
        # Held-out top-K rankers (<tool>_k) use the K tuned within the subset (<tool>_ko).
        out["pooled_organic"] = {m: {k: pooled(org_name(m), k, ORGANIC) for k in ["SRC", "PR_EXIST", "SRC_PY"]}
                                 for m in METHODS if all(m in runs[w] for w in ORGANIC)}

    # Pre-declared comparison family (pooled over the 57 instances, G_SRC).
    family = [
        ("ds_adaptive", "plain_haiku", "domain agents vs plain LLM (same model)"),
        ("ds_adaptive", "rlm_haiku", "domain agents vs single-agent RLM (same model)"),
        ("ds_nospawn", "ds_repl", "repository tools vs REPL only (same coordinator, prompt, step limit)"),
        ("ds_repl", "rlm_haiku", "coordinator harness vs RLM runner (both REPL only)"),
        ("ds_nospawn", "rlm_haiku", "coordinator with repository tools vs RLM (same model)"),
        ("ds_adaptive", "ds_nospawn", "adding registry + domain agents"),
        ("ds_maponly", "ds_nospawn", "adding the registry map only (no consultation)"),
        ("ds_adaptive", "ds_maponly", "adding consultation of the domain agents to the map"),
        ("rlm_haiku", "plain_haiku", "REPL access vs none (Haiku)"),
        ("rlm_sonnet", "plain_sonnet", "REPL access vs none (Sonnet)"),
        ("ds_adaptive", "plain_sonnet", "domain agents (Haiku) vs plain LLM (Sonnet)"),
        ("ds_adaptive", "rlm_sonnet", "domain agents (Haiku) vs RLM (Sonnet)"),
        ("ds_adaptive", "codex", "domain agents (Haiku) vs Codex"),
        ("ds_adaptive", "rrl", "domain agents vs Reformulate-Retrieve-Localize (same model)"),
        ("ds_adaptive", "agentless", "domain agents vs Agentless (same model)"),
        ("ds_adaptive", "cosil", "domain agents vs CoSIL (same model)"),
        ("ds_adaptive", "locagent", "domain agents vs LocAgent (same model)"),
        ("ds_adaptive", "rrl_k", "domain agents vs RRL, held-out top-K"),
        ("ds_adaptive", "agentless_k", "domain agents vs Agentless, held-out top-K"),
        ("ds_adaptive", "cosil_k", "domain agents vs CoSIL, held-out top-K"),
        ("ds_adaptive", "locagent_k", "domain agents vs LocAgent, held-out top-K"),
    ]
    family = [(a, b, l) for a, b, l in family if all(a in runs[w] and b in runs[w] for w in WINDOWS)]
    for kind in ["SRC", "PR_EXIST", "SRC_PY"]:
        tests = []
        for a, b, label in family:
            r = paired_test(a, b, kind)
            r.update({"a": a, "b": b, "label": label})
            tests.append(r)
        adj = holm([t["p"] for t in tests])
        for t, p in zip(tests, adj):
            t["p_holm"] = p
        out["tests"][kind] = {"family": tests}
        # RQ3: guidance variants against the default system, all issues, same harness and protocol.
        guidance = []
        for a, label in (("ds_nudged", "forced consultation"), ("ds_seeded", "Agentless candidates in the prompt")):
            if all(a in runs[w] and "ds_adaptive" in runs[w] for w in WINDOWS):
                r = paired_test(a, "ds_adaptive", kind, windows=WINDOWS)
                r.update({"a": a, "b": "ds_adaptive", "label": label, "diff": paired_diff(a, "ds_adaptive", kind, WINDOWS),
                          "by_window": {w: paired_test(a, "ds_adaptive", kind, windows=[w]) for w in WINDOWS}})
                guidance.append(r)
        out["tests"][kind]["guidance"] = guidance
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
                t["diff"] = paired_diff(t["a"], t["b"], kind, WINDOWS)
            out["tests"][kind]["family_all"] = allt
            org = []
            for a, b, label in family:
                r = paired_test(org_name(a), org_name(b), kind, windows=ORGANIC)
                r.update({"a": a, "b": b, "label": label, "diff": paired_diff(org_name(a), org_name(b), kind, ORGANIC)})
                org.append(r)
            for t, p in zip(org, holm([t["p"] for t in org])):
                t["p_holm"] = p
            out["tests"][kind]["family_organic"] = org

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
                tok = sum(v["tokens"] for r in runs[w][m] for v in r["instances"].values()) / len(gold[w])
                out["ensembles"][w][f"{m}_{rule}"] = {"k": len(runs[w][m]), "tokens_per_inst": tok, **res}

    # Consultation behaviour.
    for w in WINDOWS:
        for m in ["ds_adaptive", "ds_nudged", "ds_seeded", "ds_adaptive_r0"]:
            if m not in runs[w]:
                continue
            calls = [v["subagent_calls"] or 0 for r in runs[w][m] for v in r["instances"].values()]
            out["consultation"].setdefault(w, {})[m] = {"calls_per_inst": statistics.mean(calls),
                                                        "frac_inst_with_call": statistics.mean(1 if c else 0 for c in calls)}

    out["combinations"] = combinations()
    out["sensitivity_repeated"] = sensitivity_repeated()
    json.dump(out, open(HERE / "results.json", "w"), indent=1, default=float)
    print("wrote results.json")


if __name__ == "__main__":
    main()
