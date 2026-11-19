#!/usr/bin/env python3
"""Leakage-relevant overlap between issue texts and resolving diffs, for all 105 issues.

Reads the benchmark (replication data/benchmark.json) and the repository clones of common.py;
writes issue_overlap.csv, issue_overlap_ids.json and issue_overlap_summary.json next to this script.

Per issue (same procedure for generated Ansible 2025/2026 texts and SWE-bench Pro texts):

Diff = `git diff <base_commit> <fix_commit>` where fix_commit is the SHA in the instance id
(verified: name-only diff == G_PR for every issue).

1. path_mention: statement contains (case-sensitive, boundary-delimited) the full repo path
   of a G_PR file, or its basename WITH extension (e.g. `galaxy.py`). Basenames that are
   generic (`__init__.py`) or have no extension (`aliases`) only count as the full path. path_mention_src: same, G_SRC files only.
2. Identifiers defined/modified by the diff (n_def_ids), from G_SRC files only:
   a. Python (.py): the innermost function/method/class (ast FunctionDef/AsyncFunctionDef/
      ClassDef, span incl. decorators) enclosing any changed line, on the post-fix side for
      '+' lines and the pre-fix side for '-' lines (git diff -U0 hunk ranges). Def/class
      headers that are themselves added/removed are covered by this. If a file fails to
      parse, fall back to `def`/`class` names on changed lines and in git hunk headers.
   b. Module names: basename stem of every changed .py G_SRC file (for `__init__.py`, the
      parent package directory name).
   c. Config keys / options (all G_SRC file types): in changed lines, (i) YAML/dict keys
      `key:` / `'key':` whose name contains `_`, `.` or `-` (so plain words like
      `description:` / `default:` are not counted), (ii) top-level (unindented) YAML keys of
      .yml/.yaml files, and (iii) CLI option strings `'--foo-bar'` (stored without dashes).
   Excluded: dunder names, names shorter than 4 characters, Python keywords/builtins.
   n_ids_in_statement = identifiers occurring verbatim (case-sensitive, not preceded/followed
   by [A-Za-z0-9_]) in the statement; frac = n_ids_in_statement / n_def_ids.
   "Distinctive" variant (frac_distinct): only identifiers that cannot be ordinary English
   words, i.e. contain `_`, `.`, `-`, a digit, or an internal capital (camelCase/PascalCase).
3. stem_mention: statement contains, case-insensitively and boundary-delimited (treating
   `_`/`-`/space as interchangeable), the basename stem of a G_SRC file (any type; for
   `__init__.py` the parent directory; leading underscores stripped), restricted to stems with >= 5 characters that are not
   in GENERIC_STEMS (English/generic words that would match ordinary prose).
"""
import ast
import builtins
import csv
import json
import keyword
import re
import subprocess
from pathlib import Path

from common import BARES  # noqa: E402

OUT = Path(__file__).resolve().parent
BENCHMARK = next(p for p in (OUT.parent / "replication" / "data" / "benchmark.json", OUT.parent / "data" / "benchmark.json") if p.exists())
REPO_OF = {"2020": "ansible", "2025": "ansible", "2026": "ansible",
           "openlibrary": "openlibrary", "qutebrowser": "qutebrowser"}
GENERATED = {"2025", "2026"}

EXCLUDE_IDS = set(keyword.kwlist) | set(dir(builtins)) | {"self", "cls", "main", "test", "tests"}
GENERIC_STEMS = {
    # Ordinary English / generic programming words that occur in prose regardless of the code.
    # Words that are ordinary English even when they are also plugin types (display, filter,
    # template, connection, collection, ...) are excluded. Distinctive project names (galaxy,
    # inventory, callback, vault, configdata, ...) are kept: naming them is the module-name hint.
    "utils", "util", "common", "basic", "other", "about", "error", "errors", "types", "parse",
    "parser", "manager", "helpers", "helper", "models", "model", "module", "modules", "plugin",
    "plugins", "index", "config", "setup", "context", "state", "default", "items", "value",
    "values", "check", "command", "commands", "standard", "server", "client", "search",
    "message", "messages", "process", "native", "objects", "object", "string", "strings",
    "version", "local", "status", "action", "actions", "tasks", "query", "queries", "update",
    "import", "imports", "export", "events", "event", "network", "window", "widgets",
    "settings", "debug", "logging", "shell", "constants", "exceptions", "cache", "paths",
    "files", "encoding", "request", "requests", "response", "history", "session", "sessions",
    "editor", "dialog", "lists", "forms", "views", "stats", "loader", "display", "filter",
    "lookup", "become", "connection", "template", "templates", "author", "authors", "works",
    "books", "editions", "account", "accounts", "browser", "downloads", "download",
    "completion", "argparse", "arguments", "validation", "collection", "collections",
    # Added after inspecting matches in ALL windows (English-word false positives):
    "metadata", "block", "strategy", "match", "archive", "resources", "login",
    "readme", "schema", "requirement", "requirements", "parameters", "warnings", "distribution",
}
# Stems < 5 chars (doc, yaml, copy, ssh, ...) are dropped by the length rule. The list errs on
# the side of excluding, so stem_mention is a lower bound.

BOUND_L = r"(?<![A-Za-z0-9_])"
BOUND_R = r"(?![A-Za-z0-9_])"


def git(repo, *args):
    return subprocess.run(["git", "-C", str(BARES[repo]), *args], capture_output=True, text=True,
                          errors="replace").stdout


def decode_statement(s):
    s = s.strip()
    if s.startswith('"') and s.endswith('"'):
        try:
            return json.loads(s)
        except json.JSONDecodeError:
            pass
    return s


def fix_of(iid):
    return re.match(r"instance_[^-]+-([0-9a-f]{40})-v", iid).group(1)


def hunks(diff_text):
    """Yield (old_start, old_len, new_start, new_len, header, minus_lines, plus_lines)."""
    out = []
    cur = None
    for line in diff_text.splitlines():
        m = re.match(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@ ?(.*)", line)
        if m:
            cur = [int(m.group(1)), int(m.group(2) or 1), int(m.group(3)), int(m.group(4) or 1),
                   m.group(5), [], []]
            out.append(cur)
        elif cur is not None and line.startswith("-") and not line.startswith("---"):
            cur[5].append(line[1:])
        elif cur is not None and line.startswith("+") and not line.startswith("+++"):
            cur[6].append(line[1:])
    return out


def def_spans(src):
    tree = ast.parse(src)
    spans = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            start = min([node.lineno] + [d.lineno for d in node.decorator_list])
            spans.append((start, node.end_lineno, node.name))
    return spans


def innermost(spans, line):
    best = None
    for s, e, n in spans:
        if s <= line <= e and (best is None or e - s < best[1] - best[0]):
            best = (s, e, n)
    return best[2] if best else None


KEY_RE = re.compile(r"""^\s*-?\s*['"]?([A-Za-z_][\w.\-]*)['"]?\s*:(?:\s|$)""")
TOPYAML_RE = re.compile(r"""^([A-Za-z_][\w.\-]*)\s*:""")
OPT_RE = re.compile(r"""['"]--([A-Za-z][\w\-]+)['"]""")
DEFLINE_RE = re.compile(r"^\s*(?:async\s+)?(?:def|class)\s+([A-Za-z_]\w*)")


def stem_of(path, strip=True):
    parts = path.split("/")
    base = parts[-1]
    stem = base.rsplit(".", 1)[0] if "." in base else base
    if stem == "__init__" and len(parts) > 1:
        stem = parts[-2]
    return stem.lstrip("_") if strip and stem != "__init__" else stem


def identifiers_for(repo, base, fix, src_files):
    ids = set()
    for path in sorted(src_files):
        d = git(repo, "diff", "-U0", base, fix, "--", path)
        hs = hunks(d)
        changed_plus = [l for h in hs for l in h[6]]
        changed_minus = [l for h in hs for l in h[5]]
        if path.endswith(".py"):
            ids.add(stem_of(path, strip=False))
            for side, commit, idx_start, idx_len in (("new", fix, 2, 3), ("old", base, 0, 1)):
                src = git(repo, "show", f"{commit}:{path}")
                if not src:
                    continue
                lines = [ln for h in hs for ln in range(h[idx_start], h[idx_start] + h[idx_len]) if h[idx_len] > 0]
                try:
                    spans = def_spans(src)
                    for ln in lines:
                        n = innermost(spans, ln)
                        if n:
                            ids.add(n)
                except SyntaxError:
                    for h in hs:
                        m = DEFLINE_RE.match(h[4] or "")
                        if m:
                            ids.add(m.group(1))
                        for l in (h[5] if side == "old" else h[6]):
                            m = DEFLINE_RE.match(l)
                            if m:
                                ids.add(m.group(1))
        for l in changed_plus + changed_minus:
            m = KEY_RE.match(l)
            if m and re.search(r"[_.\-]", m.group(1)):
                ids.add(m.group(1))
            if path.endswith((".yml", ".yaml")):
                m = TOPYAML_RE.match(l)
                if m:
                    ids.add(m.group(1))
            for m in OPT_RE.finditer(l):
                ids.add(m.group(1))
    ids = {i.strip(".-") for i in ids}
    ids = {i for i in ids if len(i) >= 4 and i not in EXCLUDE_IDS and not (i.startswith("__") and i.endswith("__"))}
    return ids


def distinctive(i):
    return bool(re.search(r"[_.\-0-9]", i) or re.search(r"[a-z][A-Z]", i))


def contains(text, token, ci=False):
    return re.search(BOUND_L + re.escape(token) + BOUND_R, text, re.I if ci else 0) is not None


def stem_hit(text, stem):
    pat = re.escape(stem.lower())
    pat = re.sub(r"(\\-|_)", "[-_ ]", pat)
    return re.search(BOUND_L.replace("_", "") + pat + r"(?![A-Za-z0-9])", text.lower()) is not None


def main():
    bench = json.load(open(BENCHMARK))
    rows, idlog = [], {}
    for w, insts in bench.items():
        repo = REPO_OF[w]
        for iid, g in insts.items():
            st = decode_statement(g["problem_statement"])
            base, fix = g["base_commit"], fix_of(iid)
            changed = set(filter(None, git(repo, "diff", "--name-only", base, fix).split("\n")))
            if changed != set(g["PR"]):  # only 502270c (base dated after fix; kept as distributed)
                print("WARN diff != G_PR", iid[:60], sorted(changed ^ set(g["PR"])))
            src = set(g["SRC"])

            def path_hits(files):
                hits = []
                for f in files:
                    b = f.split("/")[-1]
                    # basename only counts if it has an extension and is not __init__.py
                    if contains(st, f) or (b != "__init__.py" and "." in b.strip(".") and contains(st, b)):
                        hits.append(f)
                return hits
            ph_pr, ph_src = path_hits(g["PR"]), path_hits(src)

            stems = {stem_of(f) for f in src}
            stems = {s for s in stems if len(s) >= 5 and s.lower() not in GENERIC_STEMS}
            stem_hits = sorted(s for s in stems if stem_hit(st, s))

            ids = identifiers_for(repo, base, fix, src)
            in_st = sorted(i for i in ids if contains(st, i))
            dids = {i for i in ids if distinctive(i)}
            din = [i for i in in_st if i in dids]
            rows.append({
                "instance_id": iid, "window": w, "generated": w in GENERATED,
                "n_src": len(src), "statement_chars": len(st),
                "n_def_ids": len(ids), "n_ids_in_statement": len(in_st),
                "frac": round(len(in_st) / len(ids), 4) if ids else "",
                "n_distinct_ids": len(dids), "n_distinct_in_statement": len(din),
                "frac_distinct": round(len(din) / len(dids), 4) if dids else "",
                "path_mention": int(bool(ph_pr)), "path_mention_src": int(bool(ph_src)),
                "n_src_paths_named": len(ph_src),
                "stem_mention": int(bool(stem_hits)), "n_eligible_stems": len(stems),
                "n_stems_named": len(stem_hits),
            })
            idlog[iid] = {"window": w, "ids": sorted(ids), "ids_in_statement": in_st,
                          "paths_named_pr": ph_pr, "stems_eligible": sorted(stems), "stems_named": stem_hits}
    cols = list(rows[0].keys())
    with open(OUT / "issue_overlap.csv", "w", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=cols)
        wr.writeheader()
        wr.writerows(rows)
    json.dump(idlog, open(OUT / "issue_overlap_ids.json", "w"), indent=1)
    print(f"wrote {len(rows)} rows")




def summarize():
    """Per-window table + Mann-Whitney (generated vs SWE-bench Pro) -> summary.json / stdout."""
    import pandas as pd
    from scipy.stats import mannwhitneyu, fisher_exact
    d = pd.read_csv(OUT / "issue_overlap.csv")
    d["any_distinct"] = (d.n_distinct_in_statement > 0).astype(int)
    order = ["2020", "2025", "2026", "openlibrary", "qutebrowser"]
    d["group"] = d.generated.map({True: "generated (A2025+A2026)", False: "SWE-bench Pro (A2020+OL+qb)"})
    metrics = ["n_def_ids", "n_ids_in_statement", "frac", "n_distinct_ids", "n_distinct_in_statement",
               "frac_distinct"]
    rates = ["any_distinct", "path_mention", "path_mention_src", "stem_mention"]
    lines = ["| window | n | " + " | ".join(f"{m} mean / median" for m in metrics) + " | " +
             " | ".join(f"{r} (share)" for r in rates) + " | stmt chars (median) |",
             "|" + "---|" * (3 + len(metrics) + len(rates))]

    def row(name, x):
        cells = [f"{x[m].mean():.3f} / {x[m].median():.3f}" for m in metrics]
        cells += [f"{int(x[r].sum())}/{len(x)} ({x[r].mean():.2f})" for r in rates]
        return f"| {name} | {len(x)} | " + " | ".join(cells) + f" | {int(x.statement_chars.median())} |"
    for w in order:
        lines.append(row(w, d[d.window == w]))
    for gname in ["generated (A2025+A2026)", "SWE-bench Pro (A2020+OL+qb)"]:
        lines.append(row(gname, d[d.group == gname]))
    table = "\n".join(lines)
    res = {}
    gen = d[d.generated]
    for ref_name, ref in [("all_swebench_pro", d[~d.generated]), ("ansible_2020_only", d[d.window == "2020"])]:
        for m in ["frac", "frac_distinct", "n_ids_in_statement", "n_distinct_in_statement"]:
            a, b = gen[m].dropna(), ref[m].dropna()
            u, p = mannwhitneyu(a, b, alternative="two-sided")
            res[f"{m}__gen_vs_{ref_name}"] = {"n_gen": len(a), "n_ref": len(b), "U": float(u), "p": float(p),
                                              "rank_biserial": float(2 * u / (len(a) * len(b)) - 1),
                                              "median_gen": float(a.median()), "median_ref": float(b.median()),
                                              "mean_gen": float(a.mean()), "mean_ref": float(b.mean())}
        for r in ["stem_mention", "path_mention", "path_mention_src", "any_distinct"]:
            tab = [[int(gen[r].sum()), int(len(gen) - gen[r].sum())], [int(ref[r].sum()), int(len(ref) - ref[r].sum())]]
            odds, p = fisher_exact(tab)
            res[f"{r}__gen_vs_{ref_name}"] = {"table[[gen_yes,gen_no],[ref_yes,ref_no]]": tab, "odds": float(odds),
                                              "p_fisher": float(p)}
    json.dump({"table_md": table, "tests": res}, open(OUT / "issue_overlap_summary.json", "w"), indent=1)
    print(table)
    for k, v in res.items():
        print(k, {kk: (round(vv, 4) if isinstance(vv, float) else vv) for kk, vv in v.items()})


if __name__ == "__main__":
    main()
    summarize()
