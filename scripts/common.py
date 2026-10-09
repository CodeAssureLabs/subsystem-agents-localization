"""Shared gold-set definitions and scoring helpers.

Gold-set naming used throughout the revised paper:
  G_SWE  - the SWE-bench Pro gold set (2020 window only; external reference).
  G_SRC  - source gold: files changed by the resolving PR, excluding tests,
           changelog fragments and build/CI metadata. Same rule in every window.
  G_PR   - every file changed by the resolving PR.
Each G_PR file is further tagged as EXISTING (present at the instance's base
commit) or NEW (created by the PR).
"""
import json
import os
import re
import subprocess
from functools import lru_cache
from pathlib import Path

PKG = Path(__file__).resolve().parents[1]
HERE = PKG / "data"
ROOT = PKG
# Clones (bare or normal) of the three repositories; see README.
REPO_OF = {"2020": "ansible", "2025": "ansible", "2026": "ansible", "openlibrary": "openlibrary", "qutebrowser": "qutebrowser"}
BARES = {r: Path(os.environ.get(f"{r.upper()}_REPO", PKG / f"{r}.git")) for r in set(REPO_OF.values())}
ANSIBLE_WINDOWS = ["2020", "2025", "2026"]
NEW_WINDOWS = ["openlibrary", "qutebrowser"]

TEST_DIRS = {"test", "tests", "testing"}
NON_SOURCE_PREFIXES = ("changelogs/", ".github/", ".azure-pipelines/", "packaging/", "hacking/", "licenses/",
                       "scripts/dev/", "misc/requirements/")
NON_SOURCE_FILES = {"pyproject.toml", "setup.py", "setup.cfg", "MANIFEST.in", "tox.ini", "Makefile", "package.json",
                    "package-lock.json", ".pre-commit-config.yaml"}


def is_source(path):
    """G_SRC rule, identical for every repository: drop tests, changelogs, build/CI metadata."""
    parts = path.split("/")
    base = parts[-1]
    if TEST_DIRS & set(parts[:-1]):
        return False
    if re.match(r"(test_.*|.*_test)\.py$|conftest\.py$", base):
        return False
    if path.startswith(NON_SOURCE_PREFIXES) or path in NON_SOURCE_FILES or re.match(r"requirements.*\.txt$", path):
        return False
    return not base.lower().startswith("changelog")


def bare_for(commit):
    for b in BARES.values():
        if subprocess.run(["git", "-C", str(b), "cat-file", "-e", commit + "^{commit}"], capture_output=True).returncode == 0:
            return b
    raise KeyError(commit)


@lru_cache(maxsize=None)
def tree(commit):
    out = subprocess.run(["git", "-C", str(bare_for(commit)), "ls-tree", "-r", "--name-only", commit],
                         capture_output=True, text=True, check=True).stdout
    return frozenset(out.split("\n")) - {""}


def load_runs():
    return json.load(open(HERE / "runs.json"))


def load_gold():
    """Return {window: {iid: {"SWE", "SRC", "PR", "PR_EXIST", "PR_NEW", "base_commit", ...}}} from benchmark.json."""
    raw = json.load(open(HERE / "benchmark.json"))
    gold = {}
    for w, insts in raw.items():
        gold[w] = {}
        for iid, g in insts.items():
            g = dict(g)
            for k in ("SWE", "SRC", "PR", "PR_EXIST", "PR_NEW"):
                if g.get(k) is not None:
                    g[k] = set(g[k])
            gold[w][iid] = g
    return gold


def prf(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return p, r, f


def score_instance(pred, gold):
    pred, gold = set(pred), set(gold)
    tp = len(pred & gold)
    fp = len(pred - gold)
    fn = len(gold - pred)
    return tp, fp, fn


def micro(preds_by_iid, gold_by_iid):
    """preds_by_iid: {iid: set}; gold_by_iid: {iid: set}. Instances with empty gold are skipped."""
    TP = FP = FN = 0
    allgold = 0
    n = 0
    for iid, g in gold_by_iid.items():
        if not g:
            continue
        n += 1
        tp, fp, fn = score_instance(preds_by_iid.get(iid, set()), g)
        TP += tp; FP += fp; FN += fn
        allgold += int(fn == 0)
    p, r, f = prf(TP, FP, FN)
    return {"P": p, "R": r, "F1": f, "all_gold": allgold, "n": n, "TP": TP, "FP": FP, "FN": FN}


def inst_f1(pred, gold):
    return prf(*score_instance(pred, gold))[2]


METHOD_LABELS = {
    "bm25": "BM25",
    "plain_haiku": "Plain LLM (Haiku)",
    "plain_sonnet": "Plain LLM (Sonnet)",
    "rlm_haiku": "Single-agent RLM (Haiku)",
    "rlm_sonnet": "Single-agent RLM (Sonnet)",
    "ds_nospawn": "Coordinator only (Haiku)",
    "ds_adaptive": "Domain agents, adaptive (Haiku)",
    "ds_adaptive_t300": "Domain agents, adaptive, matched (Haiku)",
    "ds_nudged": "Domain agents, nudged (Haiku)",
    "codex": "Codex 5.5 High (CLI)",
    "rrl": "Reformulate-Retrieve-Localize",
    "agentless": "Agentless (file stage)",
    "cosil": "CoSIL (file stage)",
    "locagent": "LocAgent",
}
