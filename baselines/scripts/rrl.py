"""Reformulate, Retrieve, Localize (Caumartin and Melo, arXiv:2512.07022), reimplemented.

The original code is not public, so this follows the paper's description:
  1. An LLM extracts a JSON schema from the bug report (explanation, paths, filenames,
     identifiers, code snippet, stack trace, error message).
  2. The query is the best-performing combination in the paper, explanation + identifiers +
     code snippets, with field names, commas and quotes removed.
  3. BM25 with Pyserini's default parameters (k1=0.9, b=0.4) indexes the non-test code files
     of the repository at the issue's base commit.
  4. An agent retrieves the top-k files (k=20), may view files truncated to 512 tokens, and
     returns a ranked list of n=5 files in JSON. It is then asked once to validate its answer
     against the information it gathered (the paper's self-evaluation step).
The LLM runs with temperature 0, as in the paper.

usage: python rrl.py <run_name> <model> [ids_file]
"""
import json
import re
import subprocess
import sys
import time
from pathlib import Path

import anthropic
from rank_bm25 import BM25Okapi

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from tokenizer_shared import tokenize  # noqa: E402

BARE = {"ansible/ansible": "ansible_bare", "internetarchive/openlibrary": "openlibrary_bare",
        "qutebrowser/qutebrowser": "qutebrowser_bare"}
CODE_EXTS = (".py",)
TEST_DIRS = {"test", "tests", "testing"}
K_RETRIEVE, N_RETURN, VIEW_TOKENS = 20, 5, 512

EXTRACT_PROMPT = """Read the following bug report and extract the information below as JSON with exactly these keys:
- "explanation": a short explanation of the bug in your own words
- "paths": file or directory paths mentioned in the report (list)
- "filenames": file names mentioned in the report (list)
- "identifiers": identifiers mentioned in the bug, such as class, method and variable names (list)
- "code_snippet": code snippets from the report (string, empty if none)
- "stack_trace": the stack trace, if any (string, empty if none)
- "error_message": the error message, if any (string, empty if none)

Return only the JSON object.

Bug report:
{issue}"""

AGENT_SYSTEM = """You are a bug localization agent. Given a bug report and a repository, find the source code files that must be changed to fix the bug.
You can call `bm25_search` to retrieve candidate files with a keyword query, and `view_file` to read the beginning of a file.
When you are done, call `submit` with a ranked list of the {n} most likely files, most likely first, using exact repository paths."""

TOOLS = [
    {"name": "bm25_search", "description": f"Retrieve the top {K_RETRIEVE} files for a keyword query with BM25 over the repository's code files.",
     "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
    {"name": "view_file", "description": f"Show the first {VIEW_TOKENS} tokens of a file.",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}},
    {"name": "submit", "description": f"Submit the final ranked list of {N_RETURN} files.",
     "input_schema": {"type": "object", "properties": {"files": {"type": "array", "items": {"type": "string"}}},
                      "required": ["files"]}},
]


def is_code(path):
    parts = path.split("/")
    base = parts[-1]
    return (path.endswith(CODE_EXTS) and not (TEST_DIRS & set(parts[:-1]))
            and not re.match(r"(test_.*|.*_test)\.py$|conftest\.py$", base))


class Repo:
    def __init__(self, repo, commit):
        bare = HERE.parent / BARE[repo]
        listing = subprocess.run(["git", "-C", str(bare), "ls-tree", "-r", commit], capture_output=True, text=True, check=True).stdout
        entries = [(l.split("\t", 1)[1], l.split()[2]) for l in listing.splitlines() if l.split()[1] == "blob"]
        entries = [(p, sha) for p, sha in entries if is_code(p)]
        out = subprocess.run(["git", "-C", str(bare), "cat-file", "--batch"], input=("\n".join(s for _, s in entries) + "\n").encode(),
                             capture_output=True, check=True).stdout
        self.paths, self.text, pos = [], {}, 0
        for path, _ in entries:
            nl = out.index(b"\n", pos)
            size = int(out[pos:nl].split()[2])
            self.text[path] = out[nl + 1: nl + 1 + size].decode("utf-8", "ignore")
            self.paths.append(path)
            pos = nl + 1 + size + 1
        self.bm25 = BM25Okapi([tokenize(p) + tokenize(self.text[p]) for p in self.paths], k1=0.9, b=0.4)

    def search(self, query):
        scores = self.bm25.get_scores(tokenize(query))
        order = sorted(range(len(self.paths)), key=lambda i: -scores[i])[:K_RETRIEVE]
        return [self.paths[i] for i in order]

    def view(self, path):
        if path not in self.text:
            return f"File not found: {path}"
        words = self.text[path].split(" ")
        return " ".join(words[: VIEW_TOKENS])  # whitespace tokens approximate the paper's 512-token truncation


def build_query(schema):
    parts = [schema.get("explanation", ""), " ".join(schema.get("identifiers", []) or []), schema.get("code_snippet", "") or ""]
    return re.sub(r'[",]', " ", " ".join(p for p in parts if p))


def run_issue(client, model, inst):
    usage = {"input_tokens": 0, "output_tokens": 0}

    usage.update({"cache_creation_input_tokens": 0, "cache_read_input_tokens": 0})

    def call(**kw):
        # Prompt caching: mark the system prompt and the last block of the conversation so each
        # turn reads the previous prefix from cache. Caching changes cost only, not model outputs.
        if "system" in kw:
            kw["system"] = [{"type": "text", "text": kw["system"], "cache_control": {"type": "ephemeral"}}]
        msgs = [dict(m) for m in kw.pop("messages")]
        last = msgs[-1]
        content = last["content"]
        if isinstance(content, str):
            content = [{"type": "text", "text": content}]
        content = [c if isinstance(c, dict) else c.model_dump() for c in content]
        content[-1] = {**content[-1], "cache_control": {"type": "ephemeral"}}
        msgs[-1] = {**last, "content": content}
        r = client.messages.create(model=model, max_tokens=2048, temperature=0, messages=msgs, **kw)
        u = r.usage
        usage["input_tokens"] += u.input_tokens
        usage["output_tokens"] += u.output_tokens
        usage["cache_creation_input_tokens"] += getattr(u, "cache_creation_input_tokens", 0) or 0
        usage["cache_read_input_tokens"] += getattr(u, "cache_read_input_tokens", 0) or 0
        return r

    r = call(messages=[{"role": "user", "content": EXTRACT_PROMPT.format(issue=inst["problem_statement"])}])
    text = "".join(b.text for b in r.content if b.type == "text")
    m = re.search(r"\{.*\}", text, re.S)
    try:
        schema = json.loads(m.group(0)) if m else {}
    except ValueError:
        schema = {}
    query = build_query(schema) or inst["problem_statement"]
    repo = Repo(inst["repo"], inst["base_commit"])
    initial = repo.search(query)
    messages = [{"role": "user", "content": (f"Bug report:\n{inst['problem_statement']}\n\nReformulated query: {query}\n\n"
                                             f"Top {K_RETRIEVE} BM25 results:\n" + "\n".join(initial))}]
    submitted, validated = None, False
    overflow = False
    for _ in range(25):
        try:
            r = call(system=AGENT_SYSTEM.format(n=N_RETURN), tools=TOOLS, messages=messages)
        except anthropic.BadRequestError as e:
            if "prompt is too long" not in str(e):
                raise
            overflow = True  # context exhausted: keep the best answer so far
            break
        messages.append({"role": "assistant", "content": r.content})
        calls = [b for b in r.content if b.type == "tool_use"]
        if not calls:
            messages.append({"role": "user", "content": "Use the tools, and call `submit` when you are done."})
            continue
        results = []
        for c in calls:
            if c.name == "bm25_search":
                out = "\n".join(repo.search(c.input.get("query", "")))
            elif c.name == "view_file":
                out = repo.view(c.input.get("path", ""))
            else:
                submitted = [f for f in c.input.get("files", []) if isinstance(f, str)][:N_RETURN]
                out = "Submitted."
            results.append({"type": "tool_result", "tool_use_id": c.id, "content": out})
        if submitted is not None and not validated:
            validated = True
            results.append({"type": "text", "text": "Validate your answer against all the information you gathered. "
                                                    "If it should change, call `submit` again with the corrected ranked list; otherwise call `submit` with the same list."})
            messages.append({"role": "user", "content": results})
            submitted_first = submitted
            submitted = None
            continue
        messages.append({"role": "user", "content": results})
        if submitted is not None:
            break
    final = submitted if submitted is not None else (locals().get("submitted_first") or initial[:N_RETURN])
    return {"instance_id": inst["instance_id"], "found_files": final, "query": query, "schema": schema,
            "bm25_initial": initial, "usage": usage, "context_overflow": overflow}


def main():
    run, model = sys.argv[1], sys.argv[2]
    ids = set(Path(sys.argv[3]).read_text().split()) if len(sys.argv) > 3 else None
    out_dir = HERE / "results" / "rrl" / run
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "loc_outputs.jsonl"
    done = {json.loads(l)["instance_id"] for l in open(out)} if out.exists() else set()
    client = anthropic.Anthropic(max_retries=8)
    for line in open(HERE / "data_105.jsonl"):
        inst = json.loads(line)
        if (ids and inst["instance_id"] not in ids) or inst["instance_id"] in done:
            continue
        t0 = time.time()
        res = run_issue(client, model, inst)
        res["elapsed_s"] = round(time.time() - t0, 1)
        with open(out, "a") as f:
            f.write(json.dumps(res) + "\n")
        print(inst["instance_id"][:50], res["found_files"], res["usage"], flush=True)


if __name__ == "__main__":
    main()
