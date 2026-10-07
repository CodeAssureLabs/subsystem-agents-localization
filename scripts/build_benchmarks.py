"""Build benchmark windows for additional SWE-bench Pro repositories.

For each repository:
  1. Take its SWE-bench Pro v1 instances. The fix commit is the 40-hex hash in the
     instance id; its parent is the SWE-bench Pro base commit.
  2. Slide a 183-day window over the fix-commit dates and keep the window with the
     most instances (earliest on ties). Every instance in that window is used.
  3. Gold sets: SWE = files in the SWE-bench Pro gold patch; PR = files changed
     between base and fix commit (this reproduces the PR file sets of 18/19 Ansible
     2020 instances exactly); SRC = PR filtered by common.is_source.

Writes benchmarks/benchmark_<name>_pr_gold.json in the same schema as
benchmark_ansible_pr_gold.json, so the experiment harness can read it unchanged.
"""
import datetime
import json
import re
import subprocess
from pathlib import Path

import pandas as pd

from common import ROOT, is_source

REV = ROOT
OUT = ROOT / "benchmarks"
OUT.mkdir(exist_ok=True)
REPOS = {
    "openlibrary": ("internetarchive/openlibrary", ROOT / "openlibrary.git"),
    "qutebrowser": ("qutebrowser/qutebrowser", ROOT / "qutebrowser.git"),
}
WINDOW_DAYS = 183


def git(bare, *args):
    return subprocess.run(["git", "-C", str(bare), *args], capture_output=True, text=True, check=True).stdout


def main():
    df = pd.read_parquet(ROOT / "data" / "swebpro_v1.parquet")  # SWE-bench Pro v1 test split from Hugging Face
    summary = {}
    for name, (repo, bare) in REPOS.items():
        rows = []
        for _, r in df[df.repo == repo].iterrows():
            fix = re.search(r"__[^-]+-([0-9a-f]{40})", r.instance_id).group(1)
            ts, parent = git(bare, "show", "-s", "--format=%ct %P", fix).split()[:2]
            assert parent == r.base_commit, r.instance_id
            rows.append((datetime.datetime.fromtimestamp(int(ts), datetime.timezone.utc), fix, r))
        rows.sort(key=lambda x: x[0])
        dates = [x[0] for x in rows]
        span = datetime.timedelta(days=WINDOW_DAYS)
        best_n, best_start = max(((sum(1 for e in dates if d <= e < d + span), -i) for i, d in enumerate(dates)))
        start = dates[-best_start]
        chosen = [x for x in rows if start <= x[0] < start + span]
        insts = []
        for k, (t, fix, r) in enumerate(chosen, 1):
            pr = git(bare, "diff", "--name-only", r.base_commit, fix).split()
            new = git(bare, "diff", "--name-only", "--diff-filter=A", r.base_commit, fix).split()
            swe = sorted(set(re.findall(r"^diff --git a/(\S+)", r.patch, re.M)))
            src = [f for f in pr if is_source(f)]
            insts.append({
                "instance_id": r.instance_id,
                "human_instance_number": k,
                "date": t.strftime("%Y-%m-%d"),
                "difficulty": "hard" if len(src) >= 2 else "easy",
                "base_commit": r.base_commit,
                "fix_commit": fix,
                "original_num_files": len(swe),
                "num_files": len(pr),
                "original_gold_files": swe,
                "gold_files": sorted(pr),
                "source_gold_files": sorted(src),
                "new_files": sorted(new),
                "modified_files": sorted(set(pr) - set(new)),
                "files_omitted_from_original_gold": sorted(set(pr) - set(swe)),
                "relevant_issue_links": [],
                "relevant_pr": None,
                "problem_statement": r.problem_statement,
            })
        out = {
            "repo": repo,
            "gold_basis": "files changed between base_commit and fix_commit",
            "original_gold_basis": "SWE-bench Pro v1 gold patch",
            "window": f"{chosen[0][0]:%b %Y} - {chosen[-1][0]:%b %Y}",
            "fixed_commit": chosen[0][2].base_commit,
            "total_instances": len(insts),
            "hard_instances": sum(i["difficulty"] == "hard" for i in insts),
            "total_original_gold_files": sum(i["original_num_files"] for i in insts),
            "total_pr_gold_files": sum(i["num_files"] for i in insts),
            "total_new_files": sum(len(i["new_files"]) for i in insts),
            "total_modified_files": sum(len(i["modified_files"]) for i in insts),
            "notes": [
                "Window: the 183-day window with the most SWE-bench Pro v1 instances by fix-commit date.",
                "gold_files: every file changed by the fix commit; original_gold_files: SWE-bench Pro gold patch.",
                "source_gold_files: gold_files minus tests, changelogs and build/CI metadata (G_SRC).",
                "fixed_commit: earliest base commit in the window, for building the domain-agent registry.",
            ],
            "instances": insts,
        }
        path = OUT / f"benchmark_{name}_pr_gold.json"
        json.dump(out, open(path, "w"), indent=1)
        summary[name] = {k: out[k] for k in ("window", "total_instances", "hard_instances", "total_original_gold_files",
                                             "total_pr_gold_files", "total_new_files")}
        summary[name]["src_files"] = sum(len(i["source_gold_files"]) for i in insts)
        summary[name]["distinct_base_commits"] = len({i["base_commit"] for i in insts})
        summary[name]["docs_instances"] = sum(any(f.startswith(("doc/", "docs/")) for f in i["source_gold_files"]) for i in insts)
        print(name, best_n, summary[name])
    json.dump(summary, open(OUT / "summary.json", "w"), indent=1)


if __name__ == "__main__":
    main()
