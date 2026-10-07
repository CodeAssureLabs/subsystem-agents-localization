"""Extract a compact, uniform record of every experimental run.

Reads the raw run reports (which include full agent trajectories) and writes
runs.json: for each (window, method, run) the per-instance predicted files,
token usage and iteration counts, plus per-window instance metadata.
This file is the primary input to every other analysis script.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "runs.json"

NR = "new_results/relevant_traces"
TR = "traces_extracted/all_relevant_traces_for_report"

RUNS = {
    "2020": {
        "plain_haiku": [f"{NR}/plain_llm_haiku_{i}.json" for i in range(1, 6)],
        "plain_sonnet": ["report_trial1-plain1.json", "report_trial2-plain.json", "report_trial3-plain.json"],
        "rlm_haiku": [f"{NR}/rlm_hinted_haiku_{i}.json" for i in range(1, 4)],
        "rlm_sonnet": [f"report_trial{i}.json" for i in range(1, 6)],
        "ds_nospawn": [f"{TR}/ansible_report_no_subagents.json"],
        "ds_adaptive": [f"{NR}/agents_haiku_{i}.json" for i in range(1, 6)],
        "ds_adaptive_t300": [f"{TR}/ansible_report_haiku_agents_1.json", f"{TR}/ansible_report_haiku_no_nudge.json"],
        "ds_nudged": [f"{TR}/ansible_report_haiku_nudge.json"],
        "codex": [f"{NR}/codex_5-5-high_{i}.json" for i in range(1, 6)],
    },
}
for y in ("2025", "2026"):
    RUNS[y] = {
        "plain_haiku": [f"{NR}/plain_llm_{y}_haiku_{i}.json" for i in range(1, 4)],
        "plain_sonnet": [f"plain_sonnet_25_26/plain_llm_{y}_sonnet_{i}.json" for i in range(1, 4)],
        "rlm_haiku": [f"{NR}/rlm_hinted_{y}_haiku_{i}.json" for i in range(1, 4)],
        "rlm_sonnet": [f"rlm_sonnet_25_26/rlm_hinted_{y}_sonnet_{i}.json" for i in range(1, 4)],
        "ds_nospawn": [f"results_2025_2026/no_agents/no_agents_{y}_haiku_1.json"],
        "ds_adaptive": [f"{NR}/agents_{y}_haiku_{i}.json" for i in range(1, 4)],
        "codex": [f"{NR}/codex_{y}_5-5-high_{i}.json" for i in range(1, 4)],
    }


# Runs on additional repositories: new_runs/<window>/<method>_<n>.json, e.g.
# new_runs/openlibrary/ds_adaptive_1.json. Method names are the keys used above.
NEW_RUNS = ROOT / "revision" / "new_runs"
for w in ("openlibrary", "qutebrowser"):
    d = NEW_RUNS / w
    if d.is_dir():
        found = {}
        for f in sorted(d.glob("*.json")):
            method = f.stem.rsplit("_", 1)[0]
            found.setdefault(method, []).append(str(f.relative_to(ROOT)))
        if found:
            RUNS[w] = found


def norm(p):
    p = p.strip().strip("`'\"")
    p = re.sub(r"^(\./|a/|b/)", "", p)
    p = re.sub(r"^.*?/(?=(lib|docs|test|changelogs|hacking|packaging)/)", "", p)
    return p


def preds(r):
    v = r.get("predicted_files")
    if v is None:
        v = r.get("pred_files", [])
    return sorted({norm(x) for x in v if isinstance(x, str) and x.strip()})


def root_iterations(r):
    t = r.get("rlm_trajectory")
    if isinstance(t, dict) and isinstance(t.get("iterations"), list):
        return len(t["iterations"])
    return None


def main():
    out = {"windows": {}, "runs": {}}
    for window, methods in RUNS.items():
        out["runs"][window] = {}
        for method, files in methods.items():
            out["runs"][window][method] = []
            for f in files:
                x = json.load(open(ROOT / f))
                cfg = {k: v for k, v in x.get("config", {}).items() if k not in ("repo_path", "rerun_failed_from")}
                init = x.get("subagent_initialization", {}).get("metrics", {}).get("total_tokens", 0) or 0
                inst = {}
                for r in x["results"]:
                    iid = r["instance_id"]
                    inst[iid] = {
                        "pred": preds(r),
                        "tokens": r.get("total_tokens") or 0,
                        "input_tokens": r.get("input_tokens") or 0,
                        "output_tokens": r.get("output_tokens") or 0,
                        "root_iterations": root_iterations(r),
                        "repl_calls": r.get("repl_calls"),
                        "subagent_calls": r.get("subagent_consult_calls"),
                        "commit": r.get("actual_commit") or x["benchmark"].get("fixed_commit"),
                        "status": r.get("status"),
                    }
                    meta = out["windows"].setdefault(window, {}).setdefault(iid, {})
                    if r.get("problem_statement"):
                        meta["problem_statement"] = r["problem_statement"]
                    # report_trial*.json (Sonnet RLM, 2020) only records the fixed
                    # commit, so per-instance base commits come from other runs.
                    if r.get("base_commit") and r.get("actual_commit"):
                        meta.setdefault("base_commit", r["base_commit"])
                    meta.setdefault("date", r.get("date"))
                    meta.setdefault("difficulty", r.get("difficulty"))
                out["runs"][window][method].append({
                    "file": f,
                    "config": cfg,
                    "init_tokens": init,
                    "query_tokens": sum(v["tokens"] for v in inst.values()),
                    "instances": inst,
                })
                print(window, method, f, len(inst))
    json.dump(out, open(OUT, "w"), indent=1)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
