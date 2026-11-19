"""Audit what the agents of the revision runs could have seen of the solutions.

For every agentic issue run the audit pairs each action of the agent (tool call, REPL block,
Codex command) with the output it was shown, adds the answers of the domain agents, and flags

  actions  history commands (git log/show/diff/...), network clients or URLs, paths outside the
           issue's checkout (absolute paths, ~, ..), names of benchmark or result files, and use
           of the shared temporary directory (cwd=/tmp, chdir, /tmp paths, gettempdir);
  outputs  the hash of the resolving commit; every line of at least 30 characters that the
           resolving commit adds and that occurs nowhere in the tree of the base commit; and,
           for outputs of actions in the temporary directory, every path shown, the gold files
           of the issue, and files of our analysis tools (Claude Code scratch directories).

Each fix-line match is classified: text the agent wrote itself (the line occurs in one of its own
actions, or the REPL echoes the agent's code), an answer of a domain agent, text of the issue, or
a manual decision recorded in MANUAL below with its reason.

The audit fails, instead of skipping, when a run report, a Codex event log, an RLM trajectory, a
clone, or a base or resolving commit is missing.

Inputs (defaults are the authors' layout):
  --runs DIR       run reports DIR/<window>/<condition>_<n>.json (and .pre_tmpguard.json for the
                   first attempts of the repeated issue runs)
  --harness DIR    the harness checkout: evals/benchmark_*.json and the full clones under evals/repos
  --repeated FILE  manifest of the repeated issue runs (merge_tmpguard.py)
Outputs (in --out):
  access_audit.json           coverage per method, flag counts, every flag with its context
  access_audit_evidence.json  sanitized evidence: the repeated issue runs (first attempt and
                              repetition), every action in the temporary directory with its
                              output, and every fix-line match with its classification
Usage: python3 access_audit.py [--runs DIR] [--harness DIR] [--repeated FILE] [--out DIR]
"""
import argparse
import json
import re
import subprocess
from collections import Counter, defaultdict
from pathlib import Path

from common import ROOT
from extract_runs import R1_METHOD, R1_WINDOW, R2_CONDITIONS

R2_METHODS = {R1_METHOD[c] for c in R2_CONDITIONS}

HERE = Path(__file__).resolve().parent
BENCHMARKS = {"ansible_2020": "benchmark_ansible.json", "ansible_2025": "benchmark_ansible_2025_stress.json",
              "ansible_2026": "benchmark_ansible_2026_ytd.json", "openlibrary": "benchmark_openlibrary.json",
              "qutebrowser": "benchmark_qutebrowser.json"}
GIT_HIST = re.compile(r"\bgit\b[^\n]{0,40}?\b(log|show|diff|rev-list|reflog|fetch|clone|pull|cat-file|blame|checkout|branch|tag|grep|stash)\b")
NET = re.compile(r"\b(curl|wget|gh\s+(api|pr|issue|repo)|pip3?\s+(install|download)|urllib|requests\.(get|post)|https?://)")
ABS = re.compile(r"(?<![\w.])((?:/Users|/private|/tmp|/var|/etc|/opt|/home|/Volumes)/[^\s'\"\\),\]]*|~/[^\s'\"]*|\$HOME|(?:\.\./)+[^\s'\"]*)")
TEMP_IN = re.compile(r"""(cwd\s*=\s*\\?['"](/private)?/(tmp|var)|chdir\(\s*\\?['"](/private)?/(tmp|var)|\\?['"](/private)?/tmp(/[^'"\\]*)?\\?['"]|\\?['"]/var/folders|gettempdir|\bcd\s+/tmp)""")
ANALYSIS_FILES = re.compile(r"claude-\d+/|scratchpad/|leak_audit|issue_gen")
SENSITIVE = re.compile(r"(repos/|new_runs|benchmark_|_gold|gold_files|results\.json|swebpro|\.parquet|resubmission|revision_backup)")
SHOWN_PATH = re.compile(r"(?:^|[\s'\"(])((?:\./|/(?:private/)?tmp/|/var/folders/)[^\s'\":]+)", re.M)

# Fix-line matches that the automatic classification leaves open, decided by reading the context.
MANUAL = {
    "default: ~/.ansible/galaxy_cache": ("agent_written", "the coordinator's own plan of configuration options to add"),
    "from ansible.cli.doc import DocCLI": ("domain_agent_answer", "a domain agent's description of how the CLI stub loads DocCLI"),
    "env/set/A_PATH//an/absolute/path": ("agent_written", "the coordinator's own change plan, quoting the example of the issue text"),
    '"Programming Language :: Python :: 3.14",': ("agent_written", "a classifier list the agent wrote in its own code"),
    "from openlibrary.solr.utils import get_solr_next": ("agent_written", "a change plan the agent printed with print()"),
    "'date': arg_opts.get('removed_at_date')": ("agent_written", "proposed code in a change plan the model generated and printed"),
    "'loop_with', 'name', 'no_log', 'register', 'run_once', 'tags'": ("agent_written", "an 'Updated:' version of a constant in a change plan the model generated"),
    "content_type, body = prepare_multipart(body)": ("agent_written", "proposed code marked '# function doesn't exist yet' in the model's plan"),
    "def get_exports(self, lst: List, raw: bool = False)": ("agent_written", "an 'After' alternative in a change plan the model generated"),
    "except (OSError, OverflowError) as e:": ("agent_written", "proposed try-except in a change plan the model generated"),
    "from openlibrary.catalog.utils import expand_record": ("agent_written", "a 'Change ... to ...' instruction in a change plan the model generated"),
    "if publication_year := get_publication_year(": ("agent_written", "proposed function body in a change plan the model generated"),
    "play_context.from_attrs(pc_data)": ("agent_written", "a 'Replace ... with ...' instruction in a change plan the model generated"),
}


class AuditError(SystemExit):
    pass


def git(clone, *args, **kw):
    r = subprocess.run(["git", "-C", str(clone), *args], capture_output=True, text=True, **kw)
    if r.returncode != 0 and args[0] in ("diff", "cat-file"):
        raise AuditError(f"git {' '.join(args)} failed in {clone}: {r.stderr.strip()[:200]}")
    return r


def fix_commits(harness):
    """Resolving commit per instance: fix_commit where given, else the hash in the SWE-bench Pro style id."""
    out = {}
    for b in BENCHMARKS.values():
        d = json.load(open(harness / "evals" / b))
        for x in d if isinstance(d, list) else d["instances"]:
            m = re.search(r"__[\w-]+?-([0-9a-f]{40})", x["instance_id"])
            out[x["instance_id"]] = x.get("fix_commit") or (m.group(1) if m else None)
    return out


def added_lines(clone, base, fix, cache):
    key = f"{base}..{fix}"
    if key in cache:
        return cache[key]
    for c in (base, fix):
        git(clone, "cat-file", "-e", f"{c}^{{commit}}")
    diff = git(clone, "diff", "--unified=0", base, fix, timeout=120).stdout
    out, cur, base_text = set(), None, ""
    for line in diff.splitlines():
        if line.startswith("+++ "):
            cur = line[6:] if line.startswith("+++ b/") else None
            base_text = git(clone, "show", f"{base}:{cur}").stdout if cur else ""
        elif cur and line.startswith("+") and not line.startswith("+++"):
            s = line[1:].strip()
            if len(s) >= 30 and s not in base_text:
                out.add(s)
    if out:  # keep only lines that occur nowhere in the tree of the base commit
        present = {l.strip() for l in git(clone, "grep", "-h", "-F", "-f", "/dev/stdin", base,
                                          input="\n".join(out)).stdout.splitlines()}
        out = {s for s in out if not any(s in l for l in present)}
    cache[key] = sorted(out)
    return cache[key]


def actions(method, r, report_path):
    """Yield (kind, action_text, [output_texts]) for everything the agent ran and saw."""
    if r.get("agent_actions") is not None:
        # complete log of every tool call of the coordinator and the domain agents, with outputs
        for x in r["agent_actions"]:
            kind = ("consult" if x.get("tool") == "consult_agents" else "tool_call") if x.get("agent") == "coordinator" \
                else "domain_action"
            yield kind, f"{x.get('tool')} {json.dumps(x.get('args'))}", [x.get("output") or ""]
        return
    if method == "codex":
        ev = r.get("events_file")
        p = Path(ev.replace(".partial_events", "_events")) if ev else None
        if p is None or not p.exists():
            raise AuditError(f"{report_path.name} {r['instance_id']}: Codex event log missing ({ev})")
        for line in p.read_text().splitlines():
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            it = e.get("item") or {}
            if e.get("type") == "item.completed" and it.get("type") == "command_execution":
                yield "codex_command", it.get("command", ""), [it.get("aggregated_output", "")]
            elif e.get("type") == "item.completed" and it.get("type") not in (None, "agent_message", "reasoning"):
                yield f"codex_{it.get('type')}", json.dumps(it)[:4000], []
        return
    if method.startswith("rlm"):
        its = (r.get("rlm_trajectory") or {}).get("iterations")
        if its is None:
            raise AuditError(f"{report_path.name} {r['instance_id']}: RLM trajectory missing")
        for it in its:
            for cb in it.get("code_blocks") or []:
                res = cb.get("result") or {}
                yield "repl", cb.get("code") or "", [f"{res.get('stdout', '')}\n{res.get('stderr', '')}"]
        return
    hist = r.get("conversation_history")
    if hist is None:
        raise AuditError(f"{report_path.name} {r['instance_id']}: conversation history missing")
    cur, outs = None, []
    for m in hist:
        c = str(m.get("content"))
        if m.get("role") == "assistant" and c.startswith("tool_call:"):
            if cur is not None:
                yield "tool_call", cur, outs
            cur, outs = c[len("tool_call:"):].strip(), []
        elif m.get("role") == "tool" and cur is not None:
            outs.append(c)
        elif m.get("role") != "tool" and cur is not None:
            yield "tool_call", cur, outs
            cur, outs = None, []
    if cur is not None:
        yield "tool_call", cur, outs
    for c in r.get("subagent_consults") or []:
        yield "consult", json.dumps(c.get("args")), [str(c.get("result_preview", ""))]


# Actions that execute code or commands; only these can use the temporary directory.
EXECUTING = ("python_repl", "run_command", "bash", "shell")


def check_action(text, checkout_root):
    hits = []
    executes = not text.startswith(("{", "[")) and (text.split(" ", 1)[0] in EXECUTING or not re.match(r"^[a-z_]+ [\[{]", text))
    for cat, rx in (("temp_dir", TEMP_IN), ("git_history", GIT_HIST), ("network", NET), ("sensitive_name", SENSITIVE)):
        if cat == "temp_dir" and not executes:
            continue
        m = rx.search(text)
        if m:
            hits.append((cat, m.group(0)))
    for m in ABS.finditer(text):
        p = m.group(1)
        if checkout_root and p.startswith(checkout_root):
            continue
        if re.match(r"/(Users|home)/[^/]+/(\.local|Library/Python|miniconda|anaconda|\.pyenv)", p) or "site-packages" in p:
            continue
        if p in ("/tmp", "/dev/null") or p.startswith("/dev/"):
            continue
        hits.append(("outside_path", p[:200]))
    return hits


def sanitize(text, limit=2000):
    home = str(Path.home())
    text = text.replace(home, "~").replace(home.replace("/", "-"), "-~")
    return text if len(text) <= limit else text[:limit] + f" [... {len(text) - limit} more characters]"


def classify_fix_line(line, own_actions, problem, output, kind):
    for prefix, decision in MANUAL.items():
        if line.startswith(prefix):
            return decision
    if kind == "consult" or output.startswith("consult_agents"):
        return "domain_agent_answer", "answer of a domain agent"
    if output.startswith("python_repl input"):
        return "agent_written", "the REPL tool echoes the agent's own code"
    key = line[:30]
    if any(key in a for a in own_actions):
        return "agent_written", "the line occurs in one of the agent's own actions"
    if key in problem:
        return "issue_text", "the line occurs in the issue text"
    return "unclassified", ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=Path, default=ROOT / "revision" / "new_runs_r1")
    ap.add_argument("--runs-r2", type=Path, default=ROOT / "revision" / "new_runs_r2",
                    help="reports of the configurations that consult domain agents (adaptive, nudged, seeded), "
                         "run with the strict guard and the action log of every agent")
    ap.add_argument("--harness", type=Path, default=ROOT / "revision" / "harness")
    ap.add_argument("--repeated", type=Path, default=HERE / "repeated_runs.json")
    ap.add_argument("--out", type=Path, default=HERE)
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    cache_f = a.out / ".added_lines_cache.json"
    cache = json.load(open(cache_f)) if cache_f.exists() else {}
    fixes = fix_commits(a.harness)
    manifest = [x for x in json.load(open(a.repeated)) if x["method"] not in R2_METHODS]
    repeated = {(x["window"], x["method"], x["run"], x["instance_id"]) for x in manifest}

    reports = []
    for wdir in R1_WINDOW:
        found = [f for base in (a.runs, a.runs_r2) for f in sorted((base / wdir).glob("*_[0-9].json"))
                 if (base == a.runs_r2) == (f.stem.rsplit("_", 1)[0] in R2_CONDITIONS)]
        if not found:
            raise AuditError(f"no run reports in {a.runs / wdir}")
        for c in R2_CONDITIONS:
            n1 = len(list((a.runs / wdir).glob(f"{c}_[0-9].json")))
            n2 = len(list((a.runs_r2 / wdir).glob(f"{c}_[0-9].json")))
            if n2 != n1:
                raise AuditError(f"{wdir}: {n2} {c} reports in {a.runs_r2}, expected {n1}")
        for f in found:
            reports.append((wdir, f, f.stem, False))
            pre = f.with_name(f"{f.stem}.pre_tmpguard.json")
            if pre.exists():
                reports.append((wdir, pre, f.stem, True))

    coverage = defaultdict(Counter)
    flags, temp_evidence, fixline_evidence, n_reported = [], [], [], 0
    window_fix = {}
    by_tool = defaultdict(lambda: defaultdict(Counter))
    for wdir, f, stem, first_attempts in reports:
        w = R1_WINDOW[wdir]
        cond, run = stem.rsplit("_", 1)
        method = R1_METHOD[cond]
        d = json.load(open(f))
        bench = json.load(open(a.harness / "evals" / BENCHMARKS[wdir]))
        expected = len(bench if isinstance(bench, list) else bench["instances"])
        if not first_attempts and len(d["results"]) != expected:
            raise AuditError(f"{f}: {len(d['results'])} issue runs, expected {expected}")
        if first_attempts:
            d["results"] = [r for r in d["results"] if (wdir, method, int(run), r["instance_id"]) in repeated]
        cfg = d.get("config") or {}
        clone = a.harness / (cfg.get("history_repo") or "")
        if not (clone / ".git").exists() and not (clone / "HEAD").exists():
            raise AuditError(f"{f}: clone {clone} missing")
        checkout_root = str(Path(cfg["repo_path"]).parent.parent) if cfg.get("repo_path") else ""
        for r in d["results"]:
            key = (wdir, method, int(run), r["instance_id"])
            role = "first_attempt" if first_attempts else ("repetition" if key in repeated else "reported")
            n_reported += role != "first_attempt"
            fix, base = fixes.get(r["instance_id"]), r.get("base_commit")
            if not fix or not base:
                raise AuditError(f"{f} {r['instance_id']}: resolving or base commit unknown")
            added = added_lines(clone, base, fix, cache)
            gold = [g for g in r.get("gold_files") or []]
            problem = r.get("problem_statement") or ""
            acts = list(actions(method, r, f))
            own = [t for _, t, _ in acts]
            cov = coverage[method]
            if role != "first_attempt":
                cov["issue_runs"] += 1
            cov[f"{role}_actions"] += len(acts)
            cov[f"{role}_domain_actions"] += sum(1 for k, _, _ in acts if k == "domain_action")
            if role != "first_attempt":
                for k, t, outs in acts:
                    tool = t.split(" ", 1)[0]
                    for o in outs:
                        if o.startswith("python_repl input"):
                            continue
                        # The runner of the configurations without the action log keeps the first 500 characters
                        # of an ordinary tool result; REPL inputs and outputs are kept in full as separate records.
                        prev = o.endswith("...") and len(o) >= 500 and not o.startswith("python_repl output")
                        by_tool[method][tool]["preview" if prev else "complete"] += 1
            cov[f"{role}_outputs"] += sum(len(o) for _, _, o in acts)
            cov[f"{role}_output_chars"] += sum(len(x) for _, _, o in acts for x in o)
            base_flag = {"window": w, "method": method, "run": int(run), "instance_id": r["instance_id"], "role": role}
            for kind, text, outs in acts:
                hits = check_action(text, checkout_root)
                for cat, ev in hits:
                    flags.append({**base_flag, "source": kind, "category": cat, "evidence": ev, "text": text[:600]})
                in_temp = any(c == "temp_dir" for c, _ in hits)
                joined = "\n".join(outs)
                if in_temp:
                    shown = sorted({p for p in SHOWN_PATH.findall(joined)})
                    an = ANALYSIS_FILES.search(joined)
                    # Each returned record separately; the REPL tool also logs the agent's own code ("python_repl input").
                    returned = [o for o in outs if not o.startswith("python_repl input")]
                    gold_shown = sorted({g for g in gold for o in returned if g in o})
                    # Provenance: a gold path that also occurs in the agent's own action was supplied by the agent
                    # (a failed access or an existence check), not retrieved from outside the checkout.
                    gold_retrieved = [g for g in gold_shown if g not in text]
                    if an:
                        flags.append({**base_flag, "source": kind, "category": "analysis_tool_files",
                                      "evidence": an.group(0), "text": joined[max(0, an.start() - 200):an.start() + 400]})
                    temp_evidence.append({**base_flag, "action": sanitize(text, 1500), "output": sanitize(joined, 3000),
                                          "paths_shown": [sanitize(p, 300) for p in shown[:200]],
                                          "analysis_tool_files": bool(an), "gold_files_named_in_output": gold_shown,
                                          "gold_files_not_supplied_by_agent": gold_retrieved})
                for o in outs:
                    if fix[:10] in o:
                        i = o.index(fix[:10])
                        flags.append({**base_flag, "source": kind, "category": "fix_hash", "evidence": fix[:10],
                                      "text": o[max(0, i - 300):i + 300]})
                    for s in added:
                        if s in o:
                            i = o.index(s)
                            label, why = classify_fix_line(s, own, problem, o, kind)
                            flags.append({**base_flag, "source": kind, "category": "fix_added_line", "evidence": s[:200],
                                          "classification": label, "text": o[max(0, i - 300):i + 300]})
                            fixline_evidence.append({**base_flag, "line": s, "classification": label, "reason": why,
                                                     "context": sanitize(o[max(0, i - 400):i + 400], 1200)})
                            break
        if not first_attempts:
            # Registry initialization runs once per window before the issues, so its actions and the
            # registry texts (which the map-only coordinator sees) are checked against every issue of the window.
            init = d.get("subagent_initialization") or {}
            if wdir not in window_fix:
                rows = bench if isinstance(bench, list) else bench["instances"]
                # The registry is built at the earliest base commit of the window, so lines that already
                # exist in that tree are part of what the registry agents legitimately read.
                reg_commit = (d.get("benchmark") or {}).get("fixed_commit") or rows[0]["base_commit"]
                lines_all = {x["instance_id"]: added_lines(clone, x["base_commit"], fixes[x["instance_id"]], cache) for x in rows}
                cand = sorted({l for v in lines_all.values() for l in v})
                present = {l.strip() for l in git(clone, "grep", "-h", "-F", "-f", "/dev/stdin", reg_commit,
                                                   input="\n".join(cand)).stdout.splitlines()} if cand else set()
                window_fix[wdir] = [(fixes[x["instance_id"]][:10], [l for l in lines_all[x["instance_id"]]
                                                                    if not any(l in p for p in present)]) for x in rows]
            def scan_text(text):
                m = ANALYSIS_FILES.search(text)
                if m:
                    return "analysis_tool_files", m.group(0)
                for h, lines in window_fix[wdir]:
                    if h in text:
                        return "fix_hash", h
                    for line in lines:
                        if line in text:
                            return "fix_added_line", line[:200]
                return None
            reg = {"window": w, "method": method, "run": int(run), "instance_id": "(registry)"}
            for ag in init.get("agents") or []:
                coverage[method]["registry_texts"] += 1
                hit = scan_text(json.dumps(ag))
                if hit:
                    flags.append({**reg, "role": "registry_text", "source": ag.get("name"), "category": hit[0],
                                  "evidence": hit[1], "text": json.dumps(ag)[:1200]})
            for x in init.get("agent_actions") or []:
                coverage[method]["registry_init_actions"] += 1
                text = f"{x.get('tool')} {json.dumps(x.get('args'))}"
                hits = check_action(text, checkout_root)
                for cat, ev in hits:
                    flags.append({**reg, "role": "registry_init", "source": x.get("agent"), "category": cat,
                                  "evidence": ev, "text": text[:600]})
                out = x.get("output") or ""
                hit = scan_text(out)
                if hit:
                    flags.append({**reg, "role": "registry_init", "source": x.get("agent"), "category": hit[0],
                                  "evidence": hit[1], "text": out[:1200]})
                if any(c == "temp_dir" for c, _ in hits):
                    temp_evidence.append({**reg, "role": "registry_init", "action": sanitize(text, 1500),
                                          "output": sanitize(out, 3000), "paths_shown": [], "analysis_tool_files": bool(ANALYSIS_FILES.search(out)),
                                          "gold_files_named_in_output": []})
    json.dump(cache, open(cache_f, "w"))

    def runs_with(cat, roles):
        return len({(x["window"], x["method"], x["run"], x["instance_id"]) for x in flags
                    if x["category"] == cat and x["role"] in roles})
    unclassified = [x for x in fixline_evidence if x["classification"] == "unclassified"]
    if unclassified:
        raise AuditError(f"{len(unclassified)} fix-line matches need a manual decision: "
                         + "; ".join(sorted({x['line'][:60] for x in unclassified})))
    reported = ("reported", "repetition")
    summary = {
        "issue_runs_reported": n_reported,
        "issue_runs_repeated": len(repeated),
        "temp_dir": runs_with("temp_dir", ("reported", "first_attempt")),  # the issue runs as first run
        "temp_dir_reported": runs_with("temp_dir", reported),
        "analysis_tool_files_first_attempts": runs_with("analysis_tool_files", ("first_attempt",)),
        "analysis_tool_files_reported": runs_with("analysis_tool_files", reported),
        "gold_files_in_temp_output_reported": len([x for x in temp_evidence if x["gold_files_named_in_output"] and x["role"] in reported]),
        "gold_files_in_temp_output_not_supplied_by_agent": len([x for x in temp_evidence if x.get("gold_files_not_supplied_by_agent")
                                                                and x["role"] in reported]),
        "fix_hash_reported": runs_with("fix_hash", reported),
        "fix_added_line_reported": runs_with("fix_added_line", reported),
        "registry_flags": len([x for x in flags if x["role"] in ("registry_init", "registry_text")
                               and x["category"] in ("analysis_tool_files", "fix_hash", "fix_added_line")]),
        "registry_init_actions": sum(c.get("registry_init_actions", 0) for c in coverage.values()),
        "registry_texts": sum(c.get("registry_texts", 0) for c in coverage.values()),
        "domain_actions_reported": sum(c.get("reported_domain_actions", 0) for c in coverage.values()),
        "fix_added_line_by_class": dict(Counter(x["classification"] for x in fixline_evidence if x["role"] in reported)),
    }
    counts = Counter((x["method"], x["category"]) for x in flags if x["role"] in reported)
    for x in flags:
        x["text"], x["evidence"] = sanitize(x["text"], 1200), sanitize(x["evidence"], 300)
    json.dump({"summary": summary, "coverage": {m: dict(c) for m, c in sorted(coverage.items())},
               "outputs_by_tool": {m: {t: dict(c) for t, c in v.items()} for m, v in sorted(by_tool.items())},
               "flag_counts": {f"{m}|{c}": n for (m, c), n in sorted(counts.items())}, "flags": flags},
              open(a.out / "access_audit.json", "w"), indent=1)
    json.dump({"summary": summary,
               "repeated_issue_runs": [{**m,
                                        "first_attempt_temp_dir_actions": [t for t in temp_evidence if t["role"] == "first_attempt"
                                                                           and (t["window"], t["method"], t["run"], t["instance_id"]) ==
                                                                           (R1_WINDOW[m["window"]], m["method"], m["run"], m["instance_id"])],
                                        "repetition_temp_dir_actions": [t for t in temp_evidence if t["role"] == "repetition"
                                                                        and (t["window"], t["method"], t["run"], t["instance_id"]) ==
                                                                        (R1_WINDOW[m["window"]], m["method"], m["run"], m["instance_id"])]}
                                       for m in manifest],
               "temp_dir_actions_reported_runs": [t for t in temp_evidence if t["role"] == "reported"],
               "fix_added_line_matches": [x for x in fixline_evidence if x["role"] in reported]},
              open(a.out / "access_audit_evidence.json", "w"), indent=1)
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
