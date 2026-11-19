"""Insert the issue runs repeated under the stricter guard into the run reports.

The access audit (access_audit.py) found issue runs whose agent code ran grep or find in the
shared temporary directory and was shown files of our analysis tools (gold files and answers).
They were repeated in the same condition and with the same registry session under a guard with a
private temporary directory (harness/rerun_tmpguard.py), and the repeated runs are reported:

  new_runs_r1/<window>/<cond>_<n>.json              repeated issue runs, marked "rerun": "tmpguard"
  new_runs_r1/<window>/<cond>_<n>.pre_tmpguard.json the report with the first attempts (audit only)

It also writes repeated_runs.json, the manifest of the repeated issue runs (window, method,
repetition, issue, dates and guards of the first attempt and the repetition, registry session).

Usage: python3 merge_tmpguard.py
"""
import json
import shutil
from pathlib import Path

from extract_runs import R1, R1_METHOD, R2_CONDITIONS

HERE = Path(__file__).resolve().parent
GUARD_FIRST = {"mode": "shared-tmp", "used_for": "all revision issue runs except the repeated ones (2026-11-18)",
               "reproduce_with": "AGENT_GUARD_MODE=shared-tmp in the published harness"}
GUARD_REPEAT = {"mode": "strict", "used_for": "the repeated issue runs (2026-11-19)",
                "reproduce_with": "AGENT_GUARD_MODE=strict (the default) in the published harness"}

SRC = R1 / "rerun_tmpguard"


def main():
    manifest = []
    for f in sorted(SRC.glob("*.json")):
        window, rest = f.stem.split("_", 1) if not f.stem.startswith("ansible") else ("_".join(f.stem.split("_")[:2]), "_".join(f.stem.split("_")[2:]))
        target = R1 / window / f"{rest}.json"
        backup = target.with_name(f"{rest}.pre_tmpguard.json")
        if not backup.exists():
            shutil.copy(target, backup)
        orig = json.load(open(backup))
        new = json.load(open(f))
        a = sorted(x.get("name") for x in (orig.get("subagent_initialization") or {}).get("agents") or [])
        b = sorted(x.get("name") for x in (new.get("subagent_initialization") or {}).get("agents") or [])
        assert a == b, f"{f.name}: registry differs from that of the run"
        repl = {r["instance_id"]: {**r, "rerun": "tmpguard"} for r in new["results"]}
        out = {**orig, "results": [{**repl[r["instance_id"]], "index": r["index"]} if r["instance_id"] in repl else r
                                   for r in orig["results"]]}
        assert sum(r.get("rerun") == "tmpguard" for r in out["results"]) == len(repl)
        json.dump(out, open(target, "w"), indent=1)
        cond, k = rest.rsplit("_", 1)
        first = {r["instance_id"]: r for r in orig["results"]}
        for r in new["results"]:
            manifest.append({
                "window": window, "method": R1_METHOD[cond], "run": int(k), "instance_id": r["instance_id"],
                "first_attempt": {"run_started": orig.get("run_at"), "guard": GUARD_FIRST,
                                  "session_id": first[r["instance_id"]].get("session_id")},
                "repetition": {"run_started": new.get("run_at"), "guard": GUARD_REPEAT, "session_id": r.get("session_id"),
                               "registry_reused": bool((new.get("config") or {}).get("reuse_initialized_session")),
                               "blocked_access": r.get("blocked_access")},
                "registry_agents": len(a), "registry_identical": a == b,
            })
        print(f"{target.relative_to(R1)}: {len(repl)} repeated issue run(s), registry of {len(a)} agents kept")
    # Configurations whose reported runs are in new_runs_r2 (all actions logged, strict guard) are not
    # affected by the repetition, so the manifest lists only the repeated issue runs that are reported.
    manifest = [m for m in manifest if m["method"] not in {R1_METHOD[c] for c in R2_CONDITIONS}]
    json.dump(manifest, open(HERE / "repeated_runs.json", "w"), indent=1)
    print(f"repeated_runs.json: {len(manifest)} issue runs")


if __name__ == "__main__":
    main()
