"""How often the coordinator's file-reading tool returned only the first lines of a long file (RQ2).

The run traces of the coordinator-only configuration on Open Library and qutebrowser record every tool
result. A read of a file longer than 300 lines returns "File is large (N lines) ... First lines preview",
so these reads can be counted from the traces. The full size of each such file is taken from the
repository at the issue's base commit.

  python3 tool_limits.py --build RUNS_DIR   # from the raw traces (new_runs/), writes ../data/tool_limits.json
  python3 tool_limits.py                    # summary from ../data/tool_limits.json
"""
import glob
import json
import re
import statistics
import subprocess
import sys
from pathlib import Path

from common import BARES

OUT = Path(__file__).resolve().parents[1] / "data" / "tool_limits.json"
REPOS = ("openlibrary", "qutebrowser")


def build(runs_dir):
    records = []
    for repo in REPOS:
        for f in sorted(glob.glob(f"{runs_dir}/{repo}/ds_nospawn_*.json")):
            run = Path(f).stem
            for r in json.load(open(f))["results"]:
                reads = limited = 0
                files = []
                for m in r.get("conversation_history") or []:
                    t = str(m.get("content", ""))
                    if m.get("role") != "tool" or not t.startswith("read_file"):
                        continue
                    reads += 1
                    if "File is large (" in t and "First lines preview" in t:
                        limited += 1
                        path = re.search(r'read_file\("([^"]+)"', t).group(1)
                        n_lines = int(re.search(r"File is large \((\d+) lines", t).group(1))
                        size = subprocess.run(["git", "-C", str(BARES[repo]), "cat-file", "-s", f"{r['base_commit']}:{path}"],
                                              capture_output=True, text=True)
                        files.append({"path": path, "lines": n_lines, "chars": int(size.stdout) if size.returncode == 0 else None})
                records.append({"repo": repo, "run": run, "instance_id": r["instance_id"], "reads": reads,
                                "limited_reads": limited, "limited_files": files})
    OUT.write_text(json.dumps(records, indent=1))
    print("wrote", OUT)


def summary():
    records = json.load(open(OUT))
    files = [f for r in records for f in r["limited_files"]]
    chars = [f["chars"] for f in files if f["chars"]]
    reads = sum(r["reads"] for r in records)
    limited = sum(r["limited_reads"] for r in records)
    hit = sum(1 for r in records if r["limited_reads"])
    print(f"issue runs: {len(records)}, with at least one limited read: {hit} ({hit / len(records):.0%})")
    print(f"file reads: {reads}, limited to the first lines: {limited} ({limited / reads:.0%})")
    print(f"limited files: median {statistics.median(f['lines'] for f in files):.0f} lines, "
          f"mean {statistics.mean(chars):,.0f} characters (about {statistics.mean(chars) / 4:,.0f} tokens)")


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--build":
        build(sys.argv[2])
    summary()
