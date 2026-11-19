"""Write tex/numbers.tex: every number quoted in the running text, as \\val{key} macros.

Inputs: results.json and results_pre_R1.json (evaluate.py before and after the revision),
runs.json (extract_runs.py), tool_logs.jsonl.gz, registries.json and r1_runs.json (export_r1.py),
issue_overlap_summary.json (issue_overlap.py), and leak_audit_r0/audit.json (audit of the
first-submission runs). Nothing here is typed by hand.
"""
import gzip
import json
import statistics
from pathlib import Path

from common import HERE, load_gold, load_runs

OUT = HERE.parent / "tables" / "numbers.tex"
R = json.load(open(HERE / "results.json"))
runs = load_runs()["runs"]
gold = load_gold()
W = ["2020", "2025", "2026", "openlibrary", "qutebrowser"]
vals = {}


def f3(x):
    return f"{x:.3f}"


def pct(x):
    return f"{100 * x:.0f}\\%"


def sgn(x):
    return f"{x:+.3f}".replace("-", "$-$")


def pv(p):
    return "<0.001" if p < 0.001 else f"{p:.3f}"


def put(key, value):
    vals[key] = value


def rng(xs, fmt=str):
    xs = sorted(xs)
    return fmt(xs[0]) if xs[0] == xs[-1] else f"{fmt(xs[0])} to {fmt(xs[-1])}"


# ---- compact records of the revision runs (export_r1.py) ----
LOGS = [json.loads(l) for l in gzip.open(HERE / "tool_logs.jsonl.gz", "rt")]
REGS = json.load(open(HERE / "registries.json"))
META = json.load(open(HERE / "r1_runs.json"))

# ---- tool use of the coordinator (coordinator-only runs) ----
calls, n = {}, 0
for r in LOGS:
    if r["method"] != "ds_nospawn":
        continue
    n += 1
    for t in r.get("tool_calls") or []:
        calls[t["name"]] = calls.get(t["name"], 0) + 1
for name, key in [("read_file", "read"), ("search_codebase", "search"), ("list_files", "list"),
                  ("python_repl", "repl"), ("parse_file", "parse")]:
    if n:
        put(f"tools-{key}", f"{calls.get(name, 0) / n:.1f}")

# ---- registries ----
regs = {w: [r["n_agents"] for r in REGS if r["window"] == w] for w in W}
init = [r["init_tokens"] for r in REGS if r.get("init_tokens")]
ans = regs["2020"] + regs["2025"] + regs["2026"]
if ans:
    put("reg-ansible", rng(ans))
for w in ("openlibrary", "qutebrowser"):
    if regs[w]:
        put(f"reg-{w}", rng(regs[w]))
allreg = [x for v in regs.values() for x in v]
if allreg:
    put("reg-all", rng(allreg))
if init:
    put("init-tokens", rng([x / 1e6 for x in init], lambda x: f"{x:.2f}M"))

# ---- consultation ----
cons = R.get("consultation", {})
fr = [cons[w]["ds_adaptive"]["frac_inst_with_call"] for w in W if "ds_adaptive" in cons.get(w, {})]
if fr:
    put("consult-frac", rng(fr, pct))

# ---- RLM turns ----
for m, key in (("rlm_haiku", "rlm-haiku-turns"), ("rlm_sonnet", "rlm-sonnet-turns")):
    t = [v["turns"] for w in W for r in runs[w].get(m, []) for v in r["instances"].values() if v.get("turns")]
    if t:
        put(key, f"{statistics.median(t):.0f}")

# ---- gold-set facts ----
src = [f for w in W for g in gold[w].values() for f in g["SRC"]]
put("nonpy-src", pct(sum(not f.endswith(".py") for f in src) / len(src)))
put("n-family", str(len(R["tests"]["SRC"]["family_all"])))

# ---- access guard and failures in the R1 runs ----
put("blocked-total", f"{sum(len(r.get('blocked_access') or []) for r in LOGS):,}".replace(",", "{,}"))
put("blocked-runs", str(sum(bool(r.get("blocked_access")) for r in LOGS)))
put("agentic-runs", f"{len(LOGS):,}".replace(",", "{,}"))
blk = {"git": 0, "python": 0, "tmp": 0, "dir": 0, "url": 0}
for r in LOGS:
    for b in r.get("blocked_access") or []:
        head = b["detail"].split(":")[0]
        if head == "git":
            blk["git"] += 1
        elif head.startswith("python"):
            blk["python"] += 1
        elif head.startswith(("cwd=/tmp", "cwd=/private/tmp", "cwd=/var/folders", "/tmp", "/private/tmp", "/var/folders", "chdir /tmp")):
            blk["tmp"] += 1
        elif head.startswith(("/", "cwd=")):
            blk["dir"] += 1
        else:
            blk["url"] += 1
for k, v in blk.items():
    put(f"blk-{k}", str(v))
fs = R["failures"]
for m, key in (("ds_nospawn", "nospawn"), ("ds_repl", "repl"), ("ds_adaptive", "adaptive")):
    if m in fs:
        put(f"steplimit-{key}", f"{fs[m]['step_limit']} of {fs[m]['issue_runs']}")
agentic_methods = ["rlm_haiku", "rlm_sonnet", "ds_repl", "ds_nospawn", "ds_maponly", "ds_adaptive", "ds_nudged",
                   "ds_seeded", "codex"]
to = sum(1 for w in W for m in agentic_methods for r in runs[w].get(m, []) for v in r["instances"].values()
         if v.get("status") == "timeout")
er = sum(1 for w in W for m in agentic_methods for r in runs[w].get(m, []) for v in r["instances"].values()
         if v.get("error") and v.get("status") != "timeout")
put("timeouts", {0: "No", 1: "One"}.get(to, str(to)))
put("errors", {0: "none", 1: "one"}.get(er, str(er)))

# ---- how each agentic issue run ended (one classification, written to outcomes.json) ----
outcomes, oc = [], {}
for w in W:
    for m in agentic_methods:
        for k, r in enumerate(runs[w].get(m, []), 1):
            for iid, v in r["instances"].items():
                if v.get("status") == "timeout":
                    o = "timeout"
                elif v.get("error"):
                    o = "error"
                elif v.get("step_limit"):
                    o = "step_limit_files" if v["pred"] else "step_limit_no_files"
                else:
                    o = "files" if v["pred"] else "empty_list"
                outcomes.append({"window": w, "method": m, "run": k, "instance_id": iid, "outcome": o})
                oc.setdefault(m, {}).setdefault(o, 0)
                oc[m][o] += 1
json.dump({"counts": oc, "issue_runs": outcomes}, open(HERE / "outcomes.json", "w"), indent=1)
n_sl = sum(c.get("step_limit_files", 0) + c.get("step_limit_no_files", 0) for c in oc.values())
put("steplimit-total", str(n_sl))
put("steplimit-nofiles", str(sum(c.get("step_limit_no_files", 0) for c in oc.values())))
put("emptylist-codex", str(oc.get("codex", {}).get("empty_list", 0)))
put("emptylist-other", str(sum(c.get("empty_list", 0) for m, c in oc.items() if m != "codex")))
put("n-prexist", str(sum(1 for w in W for g in gold[w].values() if g["PR_EXIST"])))

# ---- access audit of all revision runs (access_audit.py) and the repeated issue runs ----
AUD = json.load(open(HERE / "access_audit.json"))["summary"]
assert AUD["analysis_tool_files_reported"] == 0 and AUD["fix_hash_reported"] == 0
assert AUD["gold_files_in_temp_output_not_supplied_by_agent"] == 0
put("aud-goldtmp", str(AUD["gold_files_in_temp_output_reported"]))
_BT = json.load(open(HERE / "access_audit.json"))["outputs_by_tool"]
_FT = ("read_file", "search_codebase", "list_files", "parse_file")
for _m, _k in (("ds_nospawn", "nospawn"), ("ds_maponly", "maponly")):
    put(f"aud-prev-{_k}", f"{sum(_BT[_m].get(t, {}).get('preview', 0) for t in _FT):,}".replace(",", "{,}"))
    put(f"aud-ftool-{_k}", f"{sum(sum(_BT[_m].get(t, {}).values()) for t in _FT):,}".replace(",", "{,}"))
put("aud-tmp-runs", str(AUD["temp_dir"]))
put("aud-tmp-exposed", str(AUD["analysis_tool_files_first_attempts"]))
put("aud-addline-runs", str(AUD["fix_added_line_reported"]))
_AF = json.load(open(HERE / "access_audit.json"))["flags"]
_R2M = {"ds_adaptive", "ds_nudged", "ds_seeded"}
_tmp = lambda strict: len({(x["window"], x["method"], x["run"], x["instance_id"]) for x in _AF
                           if x["category"] == "temp_dir" and x["role"] in ("reported", "first_attempt")
                           and (x["method"] in _R2M) == strict})
put("aud-tmp-shared", str(_tmp(False)))
put("aud-tmp-strict", str(_tmp(True)))
put("aud-domain-actions", f"{AUD['domain_actions_reported']:,}".replace(",", "{,}"))
put("aud-init-actions", f"{AUD['registry_init_actions']:,}".replace(",", "{,}"))
put("aud-registry-texts", str(AUD["registry_texts"]))
assert AUD["registry_flags"] == 0
cls = AUD["fix_added_line_by_class"]
put("aud-addline-matches", str(sum(cls.values())))
put("aud-addline-agent", str(cls.get("agent_written", 0)))
put("aud-addline-consult", str(cls.get("domain_agent_answer", 0)))
COVA = json.load(open(HERE / "access_audit.json"))["coverage"]
put("aud-actions", f"{sum(c.get('reported_actions', 0) + c.get('repetition_actions', 0) for c in COVA.values()):,}".replace(",", "{,}"))
put("aud-outputs", f"{sum(c.get('reported_outputs', 0) + c.get('repetition_outputs', 0) for c in COVA.values()):,}".replace(",", "{,}"))
REP = json.load(open(HERE / "repeated_runs.json"))
_d = sorted({x["repetition"]["run_started"][:10] for x in REP})
import datetime as _dt0
put("repeat-date", ", ".join(_dt0.date.fromisoformat(d).strftime("%B %-d, %Y") for d in _d))
SENS = R.get("sensitivity_repeated") or {}
if SENS:
    dl = [v["delta"] for v in SENS["methods"].values() if v["issues_without"] == v["issues_reported"]]
    _m = max(abs(x) for x in dl)
    put("sens-maxdelta", "less than 0.001" if _m < 0.0005 else f"at most {_m:.3f}")
    nd = SENS["methods"].get("ds_nudged")
    if nd:
        put("sens-nudged-n", str(nd["issues_without"]))
    for c in SENS["comparisons"]:
        tag = f"{c['a'].replace('_', '')}-{c['b'].replace('_', '')}"
        put(f"sens-dm-{tag}", sgn(c["d_micro"]))
        put(f"sens-dmci-{tag}", f"[{sgn(c['d_micro_ci'][0])}, {sgn(c['d_micro_ci'][1])}]")

# ---- audit of the first-submission runs ----
aud = json.load(open(HERE / "leak_audit_r0" / "audit.json"))["per_method"]
put("audit-leak-runs", str(sum(v.get("fix_commit_files_seen") or 0 for v in aud.values())))

# ---- generated issue texts ----
ov = json.load(open(HERE / "issue_overlap_summary.json"))["tests"]
a = ov["frac__gen_vs_all_swebench_pro"]; b = ov["frac_distinct__gen_vs_all_swebench_pro"]
c = ov["stem_mention__gen_vs_all_swebench_pro"]["table[[gen_yes,gen_no],[ref_yes,ref_no]]"]
d = ov["path_mention__gen_vs_all_swebench_pro"]["table[[gen_yes,gen_no],[ref_yes,ref_no]]"]
put("gen-frac-gen", f"{a['median_gen']:.2f}"); put("gen-frac-swe", f"{a['median_ref']:.2f}"); put("gen-frac-p", f"{a['p']:.2f}")
put("gen-dist-gen", f"{b['mean_gen']:.2f}"); put("gen-dist-swe", f"{b['mean_ref']:.2f}"); put("gen-dist-p", f"{b['p']:.2f}")
put("gen-stem-gen", str(c[0][0])); put("gen-stem-swe", str(c[1][0]))
put("gen-stem-p", f"{ov['stem_mention__gen_vs_all_swebench_pro']['p_fisher']:.2f}")
put("gen-path-swe", str(d[1][0]))


# ---- pooled results and paired differences (filled in by results_numbers below) ----
def pooled(m, kind="SRC", key="pooled_all"):
    v = R.get(key, {}).get(m, {}).get(kind)
    return v


def results_numbers():
    for m in R.get("pooled_all", {}):
        tag = m.replace("_", "")
        for kind in ("SRC", "PR_EXIST", "SRC_PY"):
            v = pooled(m, kind)
            if v:
                k = kind.replace("_", "").lower()
                put(f"F-{tag}-{k}", f3(v["F1"]))
                put(f"CI-{tag}-{k}", f"[{f3(v['F1_boot'][0])}, {f3(v['F1_boot'][1])}]")
                put(f"P-{tag}-{k}", f3(v["P"])); put(f"R-{tag}-{k}", f3(v["R"]))
        v = pooled(m, "SRC", "pooled_organic")
        if v:
            put(f"Forg-{tag}-src", f3(v["F1"]))
    for kind in ("SRC", "PR_EXIST", "SRC_PY"):
        k = kind.replace("_", "").lower()
        for fam, suf in (("family_all", ""), ("family_organic", "-org")):
            for t in R["tests"][kind].get(fam, []):
                tag = f"{t['a'].replace('_', '')}-{t['b'].replace('_', '')}-{k}{suf}"
                put(f"d-{tag}", sgn(t["mean_a"] - t["mean_b"]))
                put(f"p-{tag}", pv(t["p_holm"]))
                put(f"wl-{tag}", f"{t['wins']} issues better and {t['losses']} worse")
                put(f"r-{tag}", f"{t['rank_biserial']:.2f}")
                dd = t.get("diff")
                if dd:
                    put(f"dm-{tag}", sgn(dd["d_micro"]))
                    put(f"dmci-{tag}", f"[{sgn(dd['d_micro_ci'][0])}, {sgn(dd['d_micro_ci'][1])}]")
                    put(f"dici-{tag}", f"[{sgn(dd['d_mean_ci'][0])}, {sgn(dd['d_mean_ci'][1])}]")
                    put(f"dicihi-{tag}", f"{dd['d_mean_ci'][1]:.3f}")
        for t in R["tests"][kind].get("guidance", []):
            tag = f"{t['a'].replace('_', '')}-{k}"
            put(f"gd-{tag}", sgn(t["mean_a"] - t["mean_b"])); put(f"gp-{tag}", pv(t["p"]))
            put(f"gwl-{tag}", f"{t['wins']} and {t['losses']}")
            dd = t["diff"]
            put(f"gdm-{tag}", sgn(dd["d_micro"]))
            put(f"gdmci-{tag}", f"[{sgn(dd['d_micro_ci'][0])}, {sgn(dd['d_micro_ci'][1])}]")
            put(f"gdici-{tag}", f"[{sgn(dd['d_mean_ci'][0])}, {sgn(dd['d_mean_ci'][1])}]")
    for m in R.get("pooled_all", {}):
        # Same estimator as Table 5 and Figure 3: the mean of the five window means.
        bw = [R["by_window"][w][m]["SRC"]["tokens_per_inst_mean"] for w in W if m in R["by_window"].get(w, {})]
        if len(bw) == len(W):
            t = statistics.mean(bw)
            put(f"tok-{m.replace('_', '')}", f"{t / 1e6:.2f}M" if t >= 1e5 else f"{t / 1e3:.0f}k")
    for tool, ks in R.get("topk", {}).get("K_by_window", {}).items():
        put(f"K-{tool}", rng(list(ks.values())))


results_numbers()

# ---- before/after comparisons for the response to reviewers ----
OLD = json.load(open(HERE / "results_pre_R1.json"))
for m in OLD.get("pooled_all", {}):
    v = OLD["pooled_all"][m].get("SRC")
    if v:
        put(f"old-F-{m.replace('_', '')}-src", f3(v["F1"]))
import re as _re
_old_norm = _re.compile(r"^.*?/(?=(lib|docs|test|changelogs|hacking|packaging)/)")
first_submission = ["plain_haiku", "plain_sonnet", "rlm_haiku_r0", "rlm_sonnet_r0", "ds_nospawn_r0", "ds_adaptive_r0",
                    "ds_adaptive_t300", "ds_nudged_r0", "codex_r0", "agentless", "cosil", "rrl", "locagent"]
put("norm-corrupted", str(sum(1 for w in W for m in first_submission for r in runs[w].get(m, [])
                              for v in r["instances"].values() for p in v["pred"] if _old_norm.sub("", p) != p)))
gains = []
for m in ("rlm_haiku", "rlm_sonnet", "ds_nospawn", "ds_adaptive", "codex"):
    if m in OLD.get("pooled_all", {}) and f"{m}_r0" in R.get("pooled_all", {}):
        gains.append(R["pooled_all"][f"{m}_r0"]["SRC"]["F1"] - OLD["pooled_all"][m]["SRC"]["F1"])
if gains:
    put("norm-max-gain", f"{max(gains):.3f}")
nf = R["new_files"]
gsrc = sum(nf[w]["codex"].get("gold_new_source", 0) for w in W)
goth = sum(nf[w]["codex"].get(f"gold_new_{k}", 0) for w in W for k in ("test", "changelog", "other"))
put("newfiles-gold-src", f"{gsrc:.0f}"); put("newfiles-gold-other", f"{goth:.0f}")
both = [m for m in nf["2020"] if all(m in nf[w] for w in W) and not m.endswith("_r0")]
best_src = max(sum(nf[w][m].get("new_hit_source", 0) for w in W) / gsrc for m in both) if gsrc else 0
best_oth = max(sum(nf[w][m].get(f"new_hit_{k}", 0) for w in W for k in ("test", "changelog", "other")) / goth
               for m in both) if goth else 0
put("newfiles-max-src", pct(best_src)); put("newfiles-max-other", pct(best_oth))
dates = sorted({(m.get("run_at") or "")[:10] for m in META} - {""})
if dates:
    import datetime as _dt
    fmt = lambda d: _dt.date.fromisoformat(d).strftime("%B %-d, %Y")
    put("run-dates", fmt(dates[0]) if len(dates) == 1 else f"{fmt(dates[0])} to {fmt(dates[-1])}")


# ---- RQ1/RQ4 details ----
nf = R["new_files"]
for m in R.get("pooled_all", {}):
    if not all(m in nf[w] for w in W):
        continue
    tot = sum(nf[w][m]["pred_exist"] + nf[w][m]["pred_nonexist"] for w in W)
    src_ph = sum(nf[w][m].get("phantom_source", 0) for w in W)
    oth_ph = sum(nf[w][m].get(f"phantom_{k}", 0) for w in W for k in ("test", "changelog", "other"))
    tag = m.replace("_", "")
    if tot:
        put(f"phsrc-{tag}", pct(src_ph / tot)); put(f"photh-{tag}", pct(oth_ph / tot))
    put(f"newsrc-{tag}", f"{sum(nf[w][m].get('new_hit_source', 0) for w in W):.1f}")
# documentation recall (Ansible 2020 docs/, qutebrowser doc/)
for w, pre in (("2020", "docs/"), ("qutebrowser", "doc/")):
    g = gold[w]
    dg = {iid: {f for f in x["SRC"] if f.startswith(pre)} for iid, x in g.items()}
    nd = sum(len(v) for v in dg.values())
    for m in R.get("pooled_all", {}):
        rs = runs[w].get(m, [])
        if not rs or m.endswith("_k"):
            continue
        rec = statistics.mean(sum(len(set(r["instances"][iid]["pred"]) & dg[iid]) for iid in g) for r in rs) / nd
        put(f"doc-{m.replace('_', '')}-{w}", pct(rec))
# best non-LLM ranker per repository (F1 at held-out K)
IR = json.load(open(HERE / "ir_results.json")); IRN = json.load(open(HERE / "ir_results_new_repos.json"))
best = lambda src, w: max(v[w]["F1_transfer"] for k, v in src["SRC"].items() if k != "l2r_weights" and w in v)
put("ir-best-ansible", rng([best(IR, w) for w in ("2020", "2025", "2026")], f3))
put("ir-best-new", rng([best(IRN, w) for w in ("openlibrary", "qutebrowser")], f3))
# consultation behaviour of the default system
cons = R.get("consultation", {})
for m in ("ds_adaptive", "ds_nudged", "ds_seeded"):
    v = [cons[w][m] for w in W if m in cons.get(w, {})]
    if len(v) == len(W):
        tag = m.replace("_", "")
        put(f"calls-{tag}", f"{statistics.mean(x['calls_per_inst'] for x in v):.2f}")
        put(f"consultfrac-{tag}", pct(statistics.mean(x['frac_inst_with_call'] for x in v)))

lines = ["% Generated by analysis/text_numbers.py. Do not edit."]
for k in sorted(vals):
    lines.append(f"\\expandafter\\def\\csname val@{k}\\endcsname{{{vals[k]}}}")
OUT.write_text("\n".join(lines) + "\n")
print(f"wrote {len(vals)} values to {OUT}")
