"""Non-LLM localization baselines, each indexed at the instance's own base commit.

  bm25       BM25Okapi over path + content tokens (k1=1.2, b=0.75)
  vsm        TF-IDF cosine similarity (sublinear tf)
  rvsm       BugLocator's revised VSM: cosine x logistic document-length prior
  path_bm25  BM25 over path tokens only
  l2r        Pairwise linear learning-to-rank (RankSVM formulation as in
             Ye et al., FSE 2014) over the four scores above plus file-name
             mention, change recency and change frequency features.
             Trained leave-one-window-out (two windows train, one tests).

Every ranker yields a ranked list; we report the top-K envelope (K=1..30),
the micro-F1 at a K selected on the training windows (no test-set tuning),
and rank metrics (Recall@10, MAP, MRR).
"""
import json
import math
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from rank_bm25 import BM25Okapi
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.svm import LinearSVC

from common import ANSIBLE_WINDOWS, HERE, NEW_WINDOWS, ROOT, bare_for, is_source, load_gold, micro

from tokenizer import tokenize  # noqa: E402  (same tokenizer as the original BM25 baseline)

EXTS = {".py", ".rst", ".txt", ".yml", ".yaml", ".cs", ".ps1", ".psm1", ".md", ".j2", ".ini", ".cfg"}
KS = list(range(1, 31))
TOPN = 300
gold = load_gold()
WINDOWS = ANSIBLE_WINDOWS
token_cache = {}


def git(commit, *args):
    return subprocess.run(["git", "-C", str(bare_for(commit)), *args], capture_output=True, text=True, check=True).stdout


def corpus(commit):
    entries = []
    for line in git(commit, "ls-tree", "-r", commit).splitlines():
        meta, path = line.split("\t", 1)
        _, typ, sha = meta.split()
        if typ == "blob" and Path(path).suffix.lower() in EXTS:
            entries.append((path, sha))
    missing = [sha for _, sha in entries if sha not in token_cache]
    if missing:
        proc = subprocess.run(["git", "-C", str(bare_for(commit)), "cat-file", "--batch"], input=("\n".join(missing) + "\n").encode(),
                              capture_output=True, check=True)
        buf = proc.stdout
        pos = 0
        for sha in missing:
            nl = buf.index(b"\n", pos)
            size = int(buf[pos:nl].split()[2])
            body = buf[nl + 1: nl + 1 + size].decode("utf-8", "ignore")
            pos = nl + 1 + size + 1
            token_cache[sha] = tokenize(body)
    paths = [p for p, _ in entries]
    path_toks = [tokenize(p) for p in paths]
    content_toks = [token_cache[s] for _, s in entries]
    return paths, path_toks, content_toks


def history(commit, days=365):
    ts = int(git(commit, "show", "-s", "--format=%ct", commit).strip())
    since = ts - days * 86400
    out = git(commit, "log", f"--since={since}", "--format=@%ct", "--name-only", commit)
    freq, last = Counter(), {}
    cur = None
    for line in out.splitlines():
        if line.startswith("@"):
            cur = int(line[1:])
        elif line.strip():
            freq[line] += 1
            last.setdefault(line, cur)
    return ts, freq, last


def minmax(x):
    x = np.asarray(x, float)
    lo, hi = x.min(), x.max()
    return (x - lo) / (hi - lo) if hi > lo else np.zeros_like(x)


def features_for(window, iid):
    g = gold[window][iid]
    commit = g["base_commit"]
    paths, ptoks, ctoks = corpus(commit)
    docs = [p + c for p, c in zip(ptoks, ctoks)]
    q = tokenize(g["problem_statement"])
    bm = BM25Okapi(docs, k1=1.2, b=0.75).get_scores(q)
    pbm = BM25Okapi([p or ["_"] for p in ptoks], k1=1.2, b=0.75).get_scores(q)
    vec = TfidfVectorizer(analyzer=lambda d: d, sublinear_tf=True, norm="l2")
    X = vec.fit_transform(docs)
    qv = vec.transform([q])
    vsm = (X @ qv.T).toarray().ravel()
    length = np.array([len(d) for d in docs], float)
    nlen = minmax(np.log1p(length))
    rvsm = vsm * (1.0 / (1.0 + np.exp(-nlen)))
    qset = set(q)
    raw = g["problem_statement"]
    stem_hit = np.array([1.0 if re.search(r"\b" + re.escape(Path(p).stem) + r"\b", raw) and len(Path(p).stem) > 3 else 0.0
                         for p in paths])
    path_overlap = np.array([len(qset & set(t)) / (len(set(t)) or 1) for t in ptoks])
    ts, freq, last = history(commit)
    recency = np.array([1.0 / (1.0 + (ts - last[p]) / 86400 / 30) if p in last else 0.0 for p in paths])
    frequency = np.log1p(np.array([freq.get(p, 0) for p in paths], float))
    F = np.vstack([minmax(bm), minmax(pbm), minmax(vsm), minmax(rvsm), stem_hit, path_overlap, recency, frequency,
                   nlen]).T
    return paths, {"bm25": bm, "vsm": vsm, "rvsm": rvsm, "path_bm25": pbm}, F


FEATURES = ["bm25", "path_bm25", "vsm", "rvsm", "stem_mention", "path_overlap", "recency", "frequency", "log_length"]


def rank(paths, scores, kind=None):
    """Top-N ranking. For source-file localization (SRC, SWE) only source files are candidates."""
    order = np.argsort(-scores, kind="stable")
    ranked = [paths[i] for i in order]
    if kind in ("SRC", "SWE"):
        ranked = [p for p in ranked if is_source(p)]
    return ranked[:TOPN]


def rank_metrics(ranking, g):
    if not g:
        return None
    hits = [i for i, p in enumerate(ranking) if p in g]
    ap = sum((k + 1) / (i + 1) for k, i in enumerate(hits)) / len(g)
    rr = 1.0 / (hits[0] + 1) if hits else 0.0
    r10 = len({p for p in ranking[:10] if p in g}) / len(g)
    return ap, rr, r10


def evaluate_rankings(rankings, kind):
    out = {}
    for w in WINDOWS:
        gm = {iid: gold[w][iid][kind] or set() for iid in gold[w]}
        env = {K: micro({iid: set(r[:K]) for iid, r in rankings[w].items()}, gm) for K in KS}
        ms = [rank_metrics(rankings[w][iid], g) for iid, g in gm.items() if g]
        ms = [m for m in ms if m]
        out[w] = {"envelope": {K: {k: v[k] for k in ("P", "R", "F1", "all_gold")} for K, v in env.items()},
                  "MAP": float(np.mean([m[0] for m in ms])), "MRR": float(np.mean([m[1] for m in ms])),
                  "R@10": float(np.mean([m[2] for m in ms]))}
    # K chosen on the two other windows (micro-F1 summed over them), evaluated on the held-out one.
    for w in WINDOWS:
        others = [o for o in WINDOWS if o != w]
        bestK = max(KS, key=lambda K: sum(out[o]["envelope"][K]["F1"] for o in others))
        out[w]["K_transfer"] = bestK
        out[w]["F1_transfer"] = out[w]["envelope"][bestK]["F1"]
        out[w]["allgold_transfer"] = out[w]["envelope"][bestK]["all_gold"]
        bK = max(KS, key=lambda K: out[w]["envelope"][K]["F1"])
        out[w]["K_oracle"], out[w]["F1_oracle"] = bK, out[w]["envelope"][bK]["F1"]
    return out


def train_rank_svm(data, kind, rng):
    Xs = []
    for w, iid, paths, F in data:
        g = gold[w][iid][kind] or set()
        pos = [i for i, p in enumerate(paths) if p in g]
        if not pos:
            continue
        top = set(np.argsort(-F[:, 0])[:TOPN].tolist())
        neg_pool = [i for i in top if paths[i] not in g and (kind not in ("SRC", "SWE") or is_source(paths[i]))]
        neg = rng.choice(neg_pool, size=min(60, len(neg_pool)), replace=False)
        for i in pos:
            for j in neg:
                Xs.append(F[i] - F[j])
    Xs = np.array(Xs)
    X = np.vstack([Xs, -Xs])
    y = np.r_[np.ones(len(Xs)), -np.ones(len(Xs))]
    clf = LinearSVC(C=0.1, fit_intercept=False, max_iter=20000)
    clf.fit(X, y)
    return clf.coef_.ravel()


def main():
    rng = np.random.default_rng(11)
    cache = {}
    for w in WINDOWS:
        for iid in gold[w]:
            paths, sc, F = features_for(w, iid)
            cache[(w, iid)] = (paths, sc, F)
            print(w, iid[:40], len(paths), flush=True)
    results = {}
    for kind in ["SRC", "PR_EXIST", "SWE"]:
        rankings = {}
        for name in ["bm25", "vsm", "rvsm", "path_bm25"]:
            rankings[name] = {w: {iid: rank(cache[(w, iid)][0], cache[(w, iid)][1][name], kind) for iid in gold[w]} for w in WINDOWS}
        rankings["l2r"] = {}
        weights = {}
        for w in WINDOWS:
            train = [(o, iid, cache[(o, iid)][0], cache[(o, iid)][2]) for o in WINDOWS if o != w for iid in gold[o]]
            kind_train = "SRC" if kind == "SWE" else kind
            wv = train_rank_svm(train, kind_train, rng)
            weights[w] = dict(zip(FEATURES, wv.round(4).tolist()))
            rankings["l2r"][w] = {iid: rank(cache[(w, iid)][0], cache[(w, iid)][2] @ wv, kind) for iid in gold[w]}
        if kind == "SWE":
            # G_SWE exists only for 2020; score that window alone.
            res = {}
            for name, rk in rankings.items():
                gm = {iid: gold["2020"][iid]["SWE"] for iid in gold["2020"]}
                env = {K: micro({iid: set(r[:K]) for iid, r in rk["2020"].items()}, gm) for K in KS}
                bK = max(KS, key=lambda K: env[K]["F1"])
                res[name] = {"K_oracle": bK, "F1_oracle": env[bK]["F1"], "all_gold": env[bK]["all_gold"],
                             "envelope": {K: {k: env[K][k] for k in ("P", "R", "F1", "all_gold")} for K in KS}}
            results[kind] = res
            continue
        results[kind] = {name: evaluate_rankings(rk, kind) for name, rk in rankings.items()}
        results[kind]["l2r_weights"] = weights
    json.dump(results, open(HERE / "ir_results.json", "w"), indent=1)
    for kind in ["SRC", "PR_EXIST"]:
        print("==", kind)
        for name in ["bm25", "vsm", "rvsm", "path_bm25", "l2r"]:
            r = results[kind][name]
            print(f"{name:10s}", " | ".join(
                f"{w}: Ktr={r[w]['K_transfer']} F1tr={r[w]['F1_transfer']:.3f} F1or={r[w]['F1_oracle']:.3f}@{r[w]['K_oracle']} "
                f"R@10={r[w]['R@10']:.2f} MAP={r[w]['MAP']:.2f}" for w in WINDOWS))
    print("== SWE", {n: (v["F1_oracle"], v["K_oracle"]) for n, v in results["SWE"].items()})


def main_cross_project():
    """Train L2R and choose K on the three Ansible windows; test on the new repositories."""
    rng = np.random.default_rng(11)
    cache = {}
    for w in ANSIBLE_WINDOWS + NEW_WINDOWS:
        for iid in gold[w]:
            cache[(w, iid)] = features_for(w, iid)
        print("features", w, flush=True)
    results = {}
    for kind in ["SRC", "PR_EXIST", "SWE"]:
        train = [(o, iid, cache[(o, iid)][0], cache[(o, iid)][2]) for o in ANSIBLE_WINDOWS for iid in gold[o]]
        wv = train_rank_svm(train, "SRC" if kind == "SWE" else kind, rng)
        res = {"l2r_weights": dict(zip(FEATURES, wv.round(4).tolist()))}
        for name in ["bm25", "vsm", "rvsm", "path_bm25", "l2r"]:
            def ranking(w, iid):
                paths, sc, F = cache[(w, iid)]
                return rank(paths, F @ wv if name == "l2r" else sc[name], kind)
            envs = {}
            for w in ANSIBLE_WINDOWS + NEW_WINDOWS:
                gm = {iid: gold[w][iid][kind] or set() for iid in gold[w]}
                rk = {iid: ranking(w, iid) for iid in gold[w]}
                envs[w] = ({K: micro({iid: set(r[:K]) for iid, r in rk.items()}, gm) for K in KS}, rk, gm)
            kind_train = [w for w in ANSIBLE_WINDOWS if kind != "SWE" or w == "2020"]
            Ktr = max(KS, key=lambda K: sum(envs[w][0][K]["F1"] for w in kind_train))
            res[name] = {}
            for w in NEW_WINDOWS:
                env, rk, gm = envs[w]
                ms = [rank_metrics(rk[iid], g) for iid, g in gm.items() if g]
                ms = [m for m in ms if m]
                bK = max(KS, key=lambda K: env[K]["F1"])
                res[name][w] = {"K_transfer": Ktr, "F1_transfer": env[Ktr]["F1"], "allgold_transfer": env[Ktr]["all_gold"],
                                "K_oracle": bK, "F1_oracle": env[bK]["F1"],
                                "MAP": float(np.mean([m[0] for m in ms])), "MRR": float(np.mean([m[1] for m in ms])),
                                "R@10": float(np.mean([m[2] for m in ms])),
                                "envelope": {K: {k: env[K][k] for k in ("P", "R", "F1", "all_gold")} for K in KS}}
        results[kind] = res
    json.dump(results, open(HERE / "ir_results_new_repos.json", "w"), indent=1)
    for kind in ["SRC", "PR_EXIST", "SWE"]:
        print("==", kind)
        for name in ["bm25", "vsm", "rvsm", "path_bm25", "l2r"]:
            r = results[kind][name]
            print(f"{name:10s}", " | ".join(f"{w}: K={r[w]['K_transfer']} F1={r[w]['F1_transfer']:.3f} (oracle {r[w]['F1_oracle']:.3f}@{r[w]['K_oracle']}) "
                                            f"R@10={r[w]['R@10']:.2f} MAP={r[w]['MAP']:.2f}" for w in NEW_WINDOWS))


if __name__ == "__main__":
    if "--new-repos" in sys.argv:
        main_cross_project()
    else:
        main()
