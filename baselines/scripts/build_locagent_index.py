"""Build LocAgent's graph and BM25 indexes for our instances from local clones.

Uses LocAgent's own build_graph (graph index v2.3) and build_code_retriever_from_repo
(BM25, similarity_top_k=10 as in build_bm25_index.py), applied to each base commit
extracted with `git archive` from the local bare clones instead of cloning from GitHub.
Outputs index/graph/<instance_id>.pkl and index/bm25/<instance_id>/.
"""
import json
import pickle
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "LocAgent"))
from dependency_graph.build_graph import build_graph  # noqa: E402
from plugins.location_tools.retriever.bm25_retriever import build_code_retriever_from_repo  # noqa: E402

BARE = {"ansible/ansible": "ansible_bare", "internetarchive/openlibrary": "openlibrary_bare",
        "qutebrowser/qutebrowser": "qutebrowser_bare"}
GRAPH = HERE / "index" / "graph"
BM25 = HERE / "index" / "bm25"
GRAPH.mkdir(parents=True, exist_ok=True)
BM25.mkdir(parents=True, exist_ok=True)


def build(inst):
    iid = inst["instance_id"]
    gfile, bdir = GRAPH / f"{iid}.pkl", BM25 / iid
    if gfile.exists() and (bdir / "corpus.jsonl").exists():
        return "skip"
    with tempfile.TemporaryDirectory() as tmp:
        repo_dir = Path(tmp) / inst["repo"].replace("/", "__")
        repo_dir.mkdir()
        bare = HERE.parent / BARE[inst["repo"]]
        archive = subprocess.run(["git", "-C", str(bare), "archive", inst["base_commit"]], capture_output=True, check=True).stdout
        subprocess.run(["tar", "-x", "-C", str(repo_dir)], input=archive, check=True)
        if not gfile.exists():
            G = build_graph(str(repo_dir), global_import=True)
            with open(gfile, "wb") as f:
                pickle.dump(G, f)
        if not (bdir / "corpus.jsonl").exists():
            build_code_retriever_from_repo(str(repo_dir.resolve()), persist_path=str(bdir), similarity_top_k=10)
    return "built"


if __name__ == "__main__":
    rows = [json.loads(l) for l in open(HERE / "data_105.jsonl")]
    only = set(json.load(open(HERE / "pilot_ids.json"))) if "--pilot" in sys.argv else None
    for r in rows:
        if only and r["instance_id"] not in only:
            continue
        print(r["instance_id"][:60], build(r), flush=True)
