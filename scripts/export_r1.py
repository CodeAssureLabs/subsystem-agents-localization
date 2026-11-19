"""Export compact records of the revision (R1) runs for the replication package.

  data/registries.json      every domain-agent registry: window, method, run, commit, size, tokens, agents
  data/tool_logs.jsonl.gz   one line per issue run: tool calls with arguments, refused accesses,
                            step-limit ending, status, error, and (for Codex) every shell command
  data/path_audit.json      tool calls whose path argument points outside the checkout (should be empty)
  data/r1_runs.json         run date and configuration of every revision run

Usage: python3 export_r1.py [--out DIR]   (default: next to this script)
"""
import argparse
import gzip
import json
from pathlib import Path

from common import ROOT
from extract_runs import R1_METHOD, R1_WINDOW, reported_reports

AGENTIC_FIELDS = ("status", "error", "step_limit_reached", "blocked_access", "turn_count",
                  "first_turn_answers_refused", "elapsed_s", "total_tokens")


def codex_commands(events_file):
    cmds = []
    if not events_file:
        return cmds
    path = Path(events_file.replace(".partial_events", "_events"))
    if not path.exists():
        return cmds
    for line in path.read_text().splitlines():
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        item = e.get("item") or {}
        if e.get("type") == "item.completed" and item.get("type") == "command_execution":
            cmds.append(item.get("command", ""))
    return cmds


def outside(arg):
    try:
        a = json.loads(arg)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(a, dict):
        return None
    for k in ("file_path", "directory", "path", "paths"):
        v = a.get(k)
        for p in (v if isinstance(v, list) else [v]):
            if isinstance(p, str) and (p.startswith("/") or p.startswith("~") or ".." in Path(p).parts):
                return p
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=Path(__file__).resolve().parent)
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    regs, audit, n, meta = [], [], 0, []
    with gzip.open(a.out / "tool_logs.jsonl.gz", "wt") as fh:
        for wdir, f in reported_reports():
            w = R1_WINDOW[wdir]
            cond, run = f.stem.rsplit("_", 1)
            method = R1_METHOD[cond]
            d = json.load(open(f))
            meta.append({"window": w, "method": method, "run": run, "run_at": d.get("run_at"),
                         "config": {k: v for k, v in (d.get("config") or {}).items() if k not in ("repo_path", "repo")}})
            init = d.get("subagent_initialization") or {}
            if init.get("agents"):
                regs.append({"window": w, "method": method, "run": run,
                             "registry_commit": d.get("benchmark", {}).get("fixed_commit"),
                             "n_agents": len(init["agents"]),
                             "init_tokens": (init.get("metrics") or {}).get("total_tokens"),
                             "agents": init["agents"],
                             # every tool call during registry initialization (runs with the action log)
                             "init_actions": [{k: x.get(k) for k in ("agent", "tool", "args")}
                                              for x in init.get("agent_actions") or []]})
            for r in d["results"]:
                n += 1
                rec = {"window": w, "method": method, "run": run, "instance_id": r["instance_id"],
                       "tool_calls": r.get("tool_calls"), **{k: r.get(k) for k in AGENTIC_FIELDS if k in r}}
                if r.get("agent_actions") is not None:
                    # every tool call of every agent (coordinator and domain agents), without outputs
                    rec["agent_actions"] = [{k: x.get(k) for k in ("agent", "tool", "args")} for x in r["agent_actions"]]
                if method == "codex":
                    rec["commands"] = codex_commands(r.get("events_file"))
                if method.startswith("rlm"):
                    rec["repl_code"] = [cb.get("code") for it in (r.get("rlm_trajectory") or {}).get("iterations", [])
                                        for cb in it.get("code_blocks", []) or []]
                fh.write(json.dumps(rec) + "\n")
                for t in (r.get("tool_calls") or []) + [{"name": x.get("tool"), "args": json.dumps(x.get("args"))}
                                                        for x in r.get("agent_actions") or []]:
                    p = outside(t.get("args"))
                    if p:
                        audit.append({"window": w, "method": method, "run": run, "instance_id": r["instance_id"],
                                      "tool": t["name"], "path": p})
    json.dump(regs, open(a.out / "registries.json", "w"), indent=1)
    json.dump(meta, open(a.out / "r1_runs.json", "w"), indent=1)
    json.dump({"issue_runs": n, "tool_calls_with_outside_path": audit}, open(a.out / "path_audit.json", "w"), indent=1)
    print(f"{n} issue runs, {len(regs)} registries, {len(audit)} tool calls with a path outside the checkout")


if __name__ == "__main__":
    main()
