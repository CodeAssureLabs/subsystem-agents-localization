"""Build Agentless repository-structure files for our instances from local clones.

Equivalent to Agentless's get_project_structure_from_scratch (clone + checkout +
create_structure), but extracts each base commit from the local bare clones with
`git archive` instead of cloning from GitHub. Output: structures/<instance_id>.json
in the format Agentless and CoSIL read via PROJECT_FILE_LOC.
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "Agentless"))
from get_repo_structure.get_repo_structure import create_structure  # noqa: E402

BARE = {"ansible/ansible": "ansible_bare", "internetarchive/openlibrary": "openlibrary_bare",
        "qutebrowser/qutebrowser": "qutebrowser_bare"}
TOP = {"ansible/ansible": "ansible", "internetarchive/openlibrary": "openlibrary", "qutebrowser/qutebrowser": "qutebrowser"}
OUT = HERE / "structures"
OUT.mkdir(exist_ok=True)


def build(inst):
    out = OUT / f"{inst['instance_id']}.json"
    if out.exists():
        return "skip"
    with tempfile.TemporaryDirectory() as tmp:
        repo_dir = Path(tmp) / TOP[inst["repo"]]
        repo_dir.mkdir()
        bare = HERE.parent / BARE[inst["repo"]]
        archive = subprocess.run(["git", "-C", str(bare), "archive", inst["base_commit"]], capture_output=True, check=True).stdout
        subprocess.run(["tar", "-x", "-C", str(repo_dir)], input=archive, check=True)
        structure = create_structure(str(repo_dir))
    json.dump({"repo": inst["repo"], "base_commit": inst["base_commit"], "structure": structure,
               "instance_id": inst["instance_id"]}, open(out, "w"))
    return "built"


if __name__ == "__main__":
    rows = [json.loads(l) for l in open(HERE / "data_105.jsonl")]
    only = set(json.load(open(HERE / "pilot_ids.json"))) if "--pilot" in sys.argv else None
    for r in rows:
        if only and r["instance_id"] not in only:
            continue
        print(r["instance_id"][:60], build(r), flush=True)
