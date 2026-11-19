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
# Later Ansible runs with the same protocol as the added repositories: new_runs/ansible_<year>/<method>_<n>.json
# (coordinator-only runs 2 and 3, 600 s timeout).
for y in ("2020", "2025", "2026"):
    for f in sorted((NEW_RUNS / f"ansible_{y}").glob("*.json")):
        RUNS[y].setdefault(f.stem.rsplit("_", 1)[0], []).append(str(f.relative_to(ROOT)))


# IEEE Access revision (R1): corrected harness (isolated single-commit checkouts, access guard,
# step-limit final answer, errors recorded) in new_runs_r1/<window>/<condition>_<n>.json.
# These replace the earlier coordinator-only, domain-agent and Haiku RLM runs, which are kept
# under the *_r0 names for the comparison reported in the response to reviewers.
R1 = ROOT / "revision" / "new_runs_r1"
R1_METHOD = {"nospawn": "ds_nospawn", "adaptive": "ds_adaptive", "repl": "ds_repl", "rlm": "rlm_haiku",
             "rlm_sonnet": "rlm_sonnet", "codex": "codex", "nudged": "ds_nudged", "seeded": "ds_seeded",
             "maponly": "ds_maponly"}
R1_WINDOW = {"ansible_2020": "2020", "ansible_2025": "2025", "ansible_2026": "2026",
             "openlibrary": "openlibrary", "qutebrowser": "qutebrowser"}
for wdir, w in R1_WINDOW.items():
    found = {}
    for f in sorted((R1 / wdir).glob("*_[0-9].json")):
        found.setdefault(R1_METHOD[f.stem.rsplit("_", 1)[0]], []).append(str(f.relative_to(ROOT)))
    for m, files in found.items():
        if m in RUNS[w]:
            RUNS[w][m + "_r0"] = RUNS[w].pop(m)
        RUNS[w][m] = files

# The configurations that consult domain agents (adaptive, nudged, seeded) were run under the strict
# guard with every action of every agent logged (harness action_log), in new_runs_r2/; these
# replace their runs in new_runs_r1/.
R2 = ROOT / "revision" / "new_runs_r2"
R2_CONDITIONS = ("adaptive", "nudged", "seeded")
for wdir, w in R1_WINDOW.items():
    found = {}
    for f in sorted((R2 / wdir).glob("*_[0-9].json")):
        cond = f.stem.rsplit("_", 1)[0]
        if cond in R2_CONDITIONS:
            found.setdefault(R1_METHOD[cond], []).append(str(f.relative_to(ROOT)))
    for m, files in found.items():
        RUNS[w][m] = files


def reported_reports():
    """(window folder, report path) of every agentic run report that the paper uses."""
    out = []
    for wdir in R1_WINDOW:
        for base in (R1, R2):
            for f in sorted((base / wdir).glob("*_[0-9].json")):
                cond = f.stem.rsplit("_", 1)[0]
                if (base == R2) == (cond in R2_CONDITIONS):
                    out.append((wdir, f))
    return out


# Published localization baselines (revision/baselines/results/<tool>/run<i>/), all windows.
BASELINES = ROOT / "baselines"
HAIKU = {"in": 1.0, "out": 5.0, "cache_write": 1.25, "cache_read": 0.10}  # $ per million tokens


def _baseline_records(tool, run_dir):
    """Return {instance_id: {"pred": [...], "tokens": int, "cost_usd": float}} for one baseline run."""
    recs = {}
    if tool in ("agentless", "cosil"):
        for line in open(run_dir / "loc_outputs.jsonl"):
            r = json.loads(line)
            u = (r.get("file_traj") or {}).get("usage", {})
            pin, pout = u.get("prompt_tokens", 0), u.get("completion_tokens", 0)
            recs[r["instance_id"]] = {"pred": r["found_files"], "tokens": pin + pout,
                                      "cost_usd": (pin * HAIKU["in"] + pout * HAIKU["out"]) / 1e6}
    elif tool == "rrl":
        for line in open(run_dir / "loc_outputs.jsonl"):
            r = json.loads(line)
            u = r["usage"]
            cw, cr = u.get("cache_creation_input_tokens", 0), u.get("cache_read_input_tokens", 0)
            recs[r["instance_id"]] = {"pred": r["found_files"],
                                      "tokens": u["input_tokens"] + cw + cr + u["output_tokens"],
                                      "cost_usd": (u["input_tokens"] * HAIKU["in"] + cw * HAIKU["cache_write"]
                                                   + cr * HAIKU["cache_read"] + u["output_tokens"] * HAIKU["out"]) / 1e6}
    elif tool == "locagent":
        merged = {}
        for line in open(run_dir / "merged_loc_outputs_mrr.jsonl"):
            r = json.loads(line)
            merged[r["instance_id"]] = r["found_files"]
        for line in open(run_dir / "loc_trajs.jsonl"):
            r = json.loads(line)
            us = [t["usage"] for t in r["loc_trajs"]["trajs"]]
            pin = sum(u["prompt_tokens"] for u in us)        # includes cached tokens
            pout = sum(u["completion_tokens"] for u in us)
            cr = sum(u.get("cache_read_input_tokens", 0) for u in us)
            cw = sum(u.get("cache_creation_input_tokens", 0) for u in us)
            unc = max(pin - cr - cw, 0)
            recs[r["instance_id"]] = {"pred": merged.get(r["instance_id"], []), "tokens": pin + pout,
                                      "cost_usd": (unc * HAIKU["in"] + cw * HAIKU["cache_write"] + cr * HAIKU["cache_read"]
                                                   + pout * HAIKU["out"]) / 1e6}
    return recs


def add_baselines(out):
    window_of = {iid: w for w, insts in out["windows"].items() for iid in insts}
    for tool in ("agentless", "cosil", "rrl", "locagent"):
        tool_dir = BASELINES / "results" / tool
        for run_dir in sorted(tool_dir.glob("run*")) if tool_dir.is_dir() else []:
            try:
                recs = _baseline_records(tool, run_dir)
            except FileNotFoundError:
                continue
            by_window = {}
            for iid, rec in recs.items():
                w = window_of.get(iid)
                if w:
                    by_window.setdefault(w, {})[iid] = rec
            for w, insts in by_window.items():
                instances = {iid: {"pred": sorted({norm(p) for p in rec["pred"] if isinstance(p, str)}),
                                   # The tools return ranked lists; keep the order for top-K evaluation.
                                   "ranked": list(dict.fromkeys(norm(p) for p in rec["pred"] if isinstance(p, str))),
                                   "tokens": rec["tokens"], "cost_usd": rec["cost_usd"], "input_tokens": 0,
                                   "output_tokens": 0, "root_iterations": None, "repl_calls": None,
                                   "subagent_calls": None, "commit": None, "status": None} for iid, rec in insts.items()}
                # Issues the tool never completed (e.g. a hung call that was capped) count as failures.
                for iid in out["windows"][w]:
                    if iid not in instances:
                        instances[iid] = {"pred": [], "ranked": [], "tokens": 0, "cost_usd": 0.0, "input_tokens": 0,
                                          "output_tokens": 0, "root_iterations": None, "repl_calls": None,
                                          "subagent_calls": None, "commit": None, "status": "failed"}
                out["runs"].setdefault(w, {}).setdefault(tool, []).append({
                    "file": str(run_dir.relative_to(ROOT)), "config": {"model": "claude-haiku-4-5"}, "init_tokens": 0,
                    "query_tokens": sum(v["tokens"] for v in instances.values()), "instances": instances})


# Only strip what is not part of a repository-relative path: diff prefixes, a leading slash,
# and an explicit checkout folder (owner__repo or repos/<name>/). Valid top-level directories
# such as test/ must survive: test/lib/ansible_test/... is a real Ansible path.
CHECKOUT_PREFIX = re.compile(r"^.*?(?:ansible__ansible|internetarchive__openlibrary|qutebrowser__qutebrowser|repos_isolated/[^/]+/[^/]+|repos/[^/]+/[^/]+)/")


def norm(p):
    p = p.strip().strip("`'\"")
    p = CHECKOUT_PREFIX.sub("", p)
    p = re.sub(r"^(\./|a/|b/)", "", p)
    return p.lstrip("/")


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
                        # Some runner paths record a per-issue timeout only in the answer text.
                        "status": "timeout" if "timed out after" in str(r.get("answer", "")) else r.get("status"),
                        "error": r.get("error") or (str(r.get("answer", "")).startswith("|ERROR|") or None),
                        "step_limit": r.get("step_limit_reached"),
                        "tool_calls": len(r["tool_calls"]) if isinstance(r.get("tool_calls"), list) else None,
                        "blocked": len(r.get("blocked_access") or []),
                        "turns": r.get("turn_count"),
                        "first_turn_refused": r.get("first_turn_answers_refused"),
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
    add_baselines(out)
    json.dump(out, open(OUT, "w"), indent=1)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
