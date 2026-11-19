"""Generate the LaTeX tables of the revised manuscript from results.json and the IR results.

Windows: Ansible 2020/2025/2026, openlibrary, qutebrowser (105 issues).
"""
import json
import statistics

from common import HERE, METHOD_LABELS, load_gold, load_runs

OUT = HERE.parent / "tables"
OUT.mkdir(parents=True, exist_ok=True)
R = json.load(open(HERE / "results.json"))
IR = json.load(open(HERE / "ir_results.json"))                # Ansible windows, leave-one-window-out
IRN = json.load(open(HERE / "ir_results_new_repos.json"))     # new repositories, trained on Ansible
gold = load_gold()
runs = load_runs()["runs"]
W = ["2020", "2025", "2026", "openlibrary", "qutebrowser"]
WL = {"2020": "Ans.\\ 2020", "2025": "Ans.\\ 2025", "2026": "Ans.\\ 2026", "openlibrary": "OpenLib.", "qutebrowser": "Qutebr."}
REPO = {"2020": "ansible/ansible", "2025": "ansible/ansible", "2026": "ansible/ansible",
        "openlibrary": "internetarchive/openlibrary", "qutebrowser": "qutebrowser/qutebrowser"}
LLM = ["plain_haiku", "plain_sonnet", "rlm_haiku", "rlm_sonnet", "ds_repl", "ds_nospawn", "ds_maponly", "ds_adaptive", "codex"]
# Published localization methods, all run with Claude Haiku 4.5: complete lists and held-out top-K.
BASE = ["rrl", "agentless", "cosil", "locagent"]
BASE_K = [m + "_k" for m in BASE]
ALL = LLM + BASE
ALLK = LLM + BASE + BASE_K
N_ALL = sum(len(gold[w]) for w in W)


def f3(x):
    return f"{x:.3f}".lstrip("0") if x < 1 else f"{x:.3f}"


def ci(v):
    return f"{f3(v['F1'])}" + (f"\\,$\\pm$\\,{f3(v['F1_tci'])}" if v.get("F1_tci") is not None else "")


def tok(x):
    return f"{x/1e6:.2f}M" if x >= 1e5 else f"{x/1e3:.0f}k"


def ir(name, w, kind="SRC"):
    return (IR if w in ("2020", "2025", "2026") else IRN)[kind][name][w]


def bold_best(cells, vals):
    best = max(vals)
    second = max([v for v in vals if v < best] or [best])
    return [f"\\textbf{{{c}}}" if v == best else (f"\\underline{{{c}}}" if v == second else c) for c, v in zip(cells, vals)]


def write(name, s):
    if name in ("main", "benchmark", "newfiles") and "\\resizebox" not in s:
        s = s.replace("\\begin{tabular}", "\\resizebox{\\textwidth}{!}{%\n\\begin{tabular}", 1)
        s = s.replace("\\end{tabular}", "\\end{tabular}}", 1)
    if name in ("swe2020", "docs", "sensitivity") and "\\resizebox" not in s:
        s = s.replace("\\begin{tabular}", "\\resizebox{\\columnwidth}{!}{%\n\\begin{tabular}", 1)
        s = s.replace("\\end{tabular}", "\\end{tabular}}", 1)
    (OUT / f"{name}.tex").write_text(s)


def benchmark_table():
    rows = []
    for w in W:
        g = gold[w]
        dates = sorted(x["date"] for x in g.values())
        rows.append(" & ".join([
            f"\\texttt{{{REPO[w]}}}", f"{dates[0][:7]} -- {dates[-1][:7]}", str(len(g)), str(sum(x['hard'] for x in g.values())),
            str(len({x['base_commit'] for x in g.values()})),
            str(sum(len(x['SRC']) for x in g.values())),
            str(sum(len(x['PR']) for x in g.values())),
            str(sum(len(x['PR_EXIST']) for x in g.values())),
            str(sum(len(x['PR_NEW']) for x in g.values())),
            str(sum(x['docs'] for x in g.values())),
            str(sum(len(x['SWE']) for x in g.values())) if next(iter(g.values()))["SWE"] is not None else "--",
        ]) + r" \\")
    tot = [str(N_ALL), str(sum(v['hard'] for w in W for v in gold[w].values())), "",
           str(sum(len(v['SRC']) for w in W for v in gold[w].values())), str(sum(len(v['PR']) for w in W for v in gold[w].values())),
           str(sum(len(v['PR_EXIST']) for w in W for v in gold[w].values())), str(sum(len(v['PR_NEW']) for w in W for v in gold[w].values())),
           str(sum(v['docs'] for w in W for v in gold[w].values())), ""]
    rows.append(r"\midrule")
    rows.append("Total & & " + " & ".join(tot) + r" \\")
    write("benchmark", r"""\begin{table*}[t]
\centering
\caption{Benchmark windows. An issue is hard if $|G_{SRC}|\geq 2$. Commits is the number of distinct base commits, since each issue is evaluated at its own base commit. $G_{PR}^{exist}$ and $G_{PR}^{new}$ split $G_{PR}$ by whether the file exists at the base commit. Docs counts the issues whose $G_{SRC}$ contains a documentation file under \texttt{docs/} or \texttt{doc/}. The 2025 and 2026 Ansible base commits contain no documentation directory. $G_{SWE}$ counts the files of the SWE-bench Pro gold patches, and the 2025 and 2026 Ansible issues are not in SWE-bench Pro.}
\label{tab:benchmark}
\small
\setlength{\tabcolsep}{4pt}
\begin{tabular}{llrrrrrrrrr}
\toprule
Repository & Issue dates & Issues & Hard & Commits & $|G_{SRC}|$ & $|G_{PR}|$ & $|G_{PR}^{exist}|$ & $|G_{PR}^{new}|$ & Docs & $|G_{SWE}|$ \\
\midrule
""" + "\n".join(rows) + r"""
\bottomrule
\end{tabular}
\end{table*}
""")


def main_table():
    rows = []
    names = ALLK + ["bm25", "l2r"]
    cols = []
    for w in W:
        cells, vals = [], []
        for m in names:
            if m in ("bm25", "l2r"):
                v = ir(m, w)
                cells.append(f3(v["F1_transfer"])); vals.append(v["F1_transfer"])
            else:
                v = R["by_window"][w][m]["SRC"]
                cells.append(ci(v)); vals.append(v["F1"])
        cols.append(bold_best(cells, vals))
    pa = [R["pooled_all"][m]["SRC"] for m in ALLK]
    pcells = bold_best([f"{f3(v['F1'])} [{f3(v['F1_boot'][0])}, {f3(v['F1_boot'][1])}]" for v in pa], [v["F1"] for v in pa])
    for i, m in enumerate(names):
        label = {"bm25": "BM25", "l2r": "Learning-to-rank"}.get(m, METHOD_LABELS.get(m))
        if m in ALLK:
            n = "/".join(str(R["by_window"][w][m]["SRC"]["n_runs"]) for w in W)
            t = tok(statistics.mean(R["by_window"][w][m]["SRC"]["tokens_per_inst_mean"] for w in W))
            pc = pcells[i]
        else:
            n, t, pc = "det.", "--", "--"
        if m in ("ds_repl", "codex", "rrl", "rrl_k", "bm25"):
            rows.append(r"\midrule")
        rows.append(" & ".join([label, n] + [cols[j][i] for j in range(len(W))] + [pc, t]) + r" \\")
    write("main", r"""\begin{table*}[t]
\centering
\caption{Micro-F1 under the source gold set $G_{SRC}$, defined by the same rule in every repository. Each window shows the mean over $n$ independent runs with the 95\% Student-$t$ half-width across runs, omitted when $n=1$. Pooled is the micro-F1 over all """ + str(N_ALL) + r""" issues with a 95\% issue-level bootstrap CI (5{,}000 resamples), which reflects the sampling of issues rather than of runs. The published localizers are scored on their complete ranked lists and, in the rows marked top-$K$, on their first $K$ files with $K$ chosen on the other four windows. Tokens is the mean number of input and output tokens per issue, excluding the one-off registry initialization. The non-LLM rankers return the top-$K$ files. $K$, and the learning-to-rank model, are chosen on other windows only, namely the two other Ansible windows for Ansible and all Ansible windows for the two added repositories. The best value per column is in bold and the second best is underlined.}
\label{tab:main}
\small
\setlength{\tabcolsep}{3.5pt}
\begin{tabular}{lcccccccr}
\toprule
& & \multicolumn{3}{c}{\texttt{ansible}} & & & & \\
\cmidrule(lr){3-5}
Method & $n$ & 2020 & 2025 & 2026 & \texttt{openlibrary} & \texttt{qutebrowser} & Pooled [95\% CI] & Tokens/issue \\
\midrule
""" + "\n".join(rows) + r"""
\bottomrule
\end{tabular}
\end{table*}
""")


def allgold_table():
    rows = []
    for m in ALL:
        cells = [f"{R['by_window'][w][m]['SRC']['all_gold']:.1f}" for w in W]
        hard = sum(R['by_window'][w][m]['SRC']['hard_all_gold'] for w in W)
        tot = sum(R['by_window'][w][m]['SRC']['all_gold'] for w in W)
        rows.append(f"{METHOD_LABELS[m]} & " + " & ".join(cells) + f" & {tot:.1f} & {hard:.1f} \\\\")
    n = [len(gold[w]) for w in W]
    nh = sum(v['hard'] for w in W for v in gold[w].values())
    write("allgold", r"""\begin{table}[t]
\centering
\caption{All-gold issues under $G_{SRC}$, given as the mean number of issues over runs whose complete source gold set is predicted. The windows contain """ + "/".join(map(str, n)) + r""" issues. Hard gives the all-gold count on the """ + str(nh) + r""" issues with $|G_{SRC}|\geq 2$.}
\label{tab:allgold}
\resizebox{\columnwidth}{!}{%
\begin{tabular}{lrrrrrrr}
\toprule
Method & """ + " & ".join(WL[w] for w in W) + r""" & Total & Hard \\
\midrule
""" + "\n".join(rows) + r"""
\bottomrule
\end{tabular}}
\end{table}
""")


def swe_table():
    rows = []
    ms = ["plain_haiku", "plain_sonnet", "rlm_haiku", "rlm_sonnet", "ds_repl", "ds_nospawn", "ds_maponly", "ds_adaptive", "ds_nudged", "ds_seeded", "codex"]
    vals = [R["by_window"]["2020"][m]["SWE"] for m in ms]
    cells = bold_best([ci(v) for v in vals], [v["F1"] for v in vals])
    for m, v, c in zip(ms, vals, cells):
        rows.append(f"{METHOD_LABELS[m]} & {v['n_runs']} & {f3(v['P'])} & {f3(v['R'])} & {c} & {v['all_gold']:.1f} & {v['hard_all_gold']:.1f} & {v['set_size']:.1f} \\\\")
    for name, lab in [("bm25", "BM25"), ("l2r", "Learning-to-rank")]:
        v = IR["SWE"][name]
        e = v["envelope"][str(v["K_oracle"])]
        rows.append(f"{lab} (best $K$={v['K_oracle']}) & det. & {f3(e['P'])} & {f3(e['R'])} & {f3(v['F1_oracle'])} & {v['all_gold']} & -- & {v['K_oracle']} \\\\")
    write("swe2020", r"""\begin{table}[t]
\centering
\caption{Ansible 2020 window scored against the SWE-bench Pro gold set $G_{SWE}$ (63 files) for comparability with SWE-bench Pro reporting, including the RQ3 variants. HAG is the all-gold count on the 16 issues with $|G_{SRC}|\geq 2$, and $|\hat F|$ is the mean predicted set size. For the non-LLM rankers, $K$ is tuned on this window, which gives an optimistic upper bound.}
\label{tab:swe2020}
\scriptsize
\setlength{\tabcolsep}{2.5pt}
\begin{tabular}{lrrrrrrr}
\toprule
Method & $n$ & P & R & F1 & AG & HAG & $|\hat F|$ \\
\midrule
""" + "\n".join(rows) + r"""
\bottomrule
\end{tabular}
\end{table}
""")


def newfile_table():
    rows = []
    agg = lambda m, key: sum(R["new_files"][w][m].get(key, 0.0) for w in W)
    gnew = {k: agg("codex", "gold_new_" + k) for k in ("source", "test", "changelog", "other")}
    for m in ALL:
        v = {w: R["new_files"][w][m] for w in W}
        nr_src = agg(m, "new_hit_source") / gnew["source"] if gnew["source"] else 0.0
        nr_oth = sum(agg(m, "new_hit_" + k) for k in ("test", "changelog", "other")) / max(1e-9, sum(gnew[k] for k in ("test", "changelog", "other")))
        ph_src = agg(m, "phantom_source") / N_ALL
        ph_tc = (agg(m, "phantom_test") + agg(m, "phantom_changelog") + agg(m, "phantom_other")) / N_ALL
        share = agg(m, "phantom_source") / max(1e-9, agg(m, "pred_exist") + agg(m, "pred_nonexist"))
        rows.append(f"{METHOD_LABELS[m]} & " + " & ".join(f3(v[w]['existing_F1']) for w in W) +
                    f" & {100*nr_src:.0f}\\% & {100*nr_oth:.0f}\\% & {ph_tc:.2f} & {ph_src:.2f} & {100*share:.0f}\\% \\\\")
    write("newfiles", r"""\begin{table*}[t]
\centering
\caption{Existing-file and new-file localization. Existing-file F1 is the micro-F1 of the predictions that exist at the base commit, scored against $G_{PR}^{exist}$. New recall is the share of files created by the resolving PRs whose exact path was predicted, separately for the """ + f"{gnew['source']:.0f}" + r""" new source files (by the $G_{SRC}$ rule) and the """ + f"{sum(gnew[k] for k in ('test', 'changelog', 'other')):.0f}" + r""" new tests, changelog fragments, and other files. The last three columns count predicted paths that neither exist at the base commit nor are created by the PR, per issue, split into proposed tests, changelogs, and other non-source files, and source paths, and give the share of all predicted paths that are such source paths.}
\label{tab:newfiles}
\small
\setlength{\tabcolsep}{3.5pt}
\begin{tabular}{lrrrrrrrrrr}
\toprule
& \multicolumn{5}{c}{Existing-file F1} & \multicolumn{2}{c}{New recall} & \multicolumn{3}{c}{Non-existent paths} \\
\cmidrule(lr){2-6}\cmidrule(lr){7-8}\cmidrule(lr){9-11}
Method & """ + " & ".join(WL[w] for w in W) + r""" & Source & Other & Test etc./iss. & Source/iss. & Source share \\
\midrule
""" + "\n".join(rows) + r"""
\bottomrule
\end{tabular}
\end{table*}
""")


def tests_table():
    rows = []
    s = R["tests"]["SRC"]["family_all"]
    e = {(t["a"], t["b"]): t for t in R["tests"]["PR_EXIST"]["family_all"]}
    labels = {
        ("ds_adaptive", "plain_haiku"): "Domain agents vs plain LLM",
        ("ds_adaptive", "rlm_haiku"): "Domain agents vs RLM",
        ("ds_nospawn", "ds_repl"): r"Repository tools vs REPL only$^\star$",
        ("ds_repl", "rlm_haiku"): r"Coordinator harness vs RLM runner$^\star$",
        ("ds_nospawn", "rlm_haiku"): "Coordinator only vs RLM",
        ("ds_adaptive", "ds_nospawn"): r"Registry (map + consultation)$^\star$",
        ("ds_maponly", "ds_nospawn"): r"Registry map only$^\star$",
        ("ds_adaptive", "ds_maponly"): r"Consultation, given the map$^\star$",
        ("rlm_haiku", "plain_haiku"): r"RLM vs plain LLM$^\star$",
        ("rlm_sonnet", "plain_sonnet"): "RLM vs plain LLM (Sonnet)",
        ("ds_adaptive", "plain_sonnet"): "Domain agents vs plain LLM (Sonnet)",
        ("ds_adaptive", "rlm_sonnet"): "Domain agents vs RLM (Sonnet)",
        ("ds_adaptive", "codex"): "Domain agents vs Codex",
        ("ds_adaptive", "rrl"): "Domain agents vs RRL",
        ("ds_adaptive", "agentless"): "Domain agents vs Agentless",
        ("ds_adaptive", "cosil"): "Domain agents vs CoSIL",
        ("ds_adaptive", "locagent"): "Domain agents vs LocAgent",
        ("ds_adaptive", "rrl_k"): "Domain agents vs RRL, top-$K$",
        ("ds_adaptive", "agentless_k"): "Domain agents vs Agentless, top-$K$",
        ("ds_adaptive", "cosil_k"): "Domain agents vs CoSIL, top-$K$",
        ("ds_adaptive", "locagent_k"): "Domain agents vs LocAgent, top-$K$",
    }

    def p(x):
        return "$<$.001" if x < 0.001 else f"{x:.3f}".lstrip("0")

    def d(x):
        return f"{x:+.3f}".replace("-", "$-$")

    def ci(lo, hi):
        return f"[{d(lo)}, {d(hi)}]"

    for a in s:
        b = e[(a["a"], a["b"])]
        da, db = a["diff"], b["diff"]
        rows.append(f"{labels[(a['a'], a['b'])]} & {d(da['d_micro'])} {ci(*da['d_micro_ci'])} & {d(da['d_mean'])} {ci(*da['d_mean_ci'])} & "
                    f"{a['wins']}/{a['losses']} & {p(a['p_holm'])} & {a['rank_biserial']:+.2f} & {d(db['d_mean'])} & {p(b['p_holm'])} \\\\")
    write("tests", r"""\begin{table*}[t]
\centering
\caption{Paired comparisons over all """ + str(N_ALL) + r""" issues, all methods with Claude Haiku 4.5 unless marked Sonnet or Codex. $\Delta_{\mu}$ is the difference in pooled micro-F1 and $\Delta_{i}$ the mean difference in per-issue F1 (first minus second method, each issue's F1 averaged over runs), each with a 95\% paired bootstrap interval over issues. W/L counts the issues on which the first method is better or worse. $p_{Holm}$ is from the two-sided Wilcoxon signed-rank test on per-issue F1, Holm-adjusted over the """ + str(len(s)) + r""" planned comparisons, and $r$ is the matched-pairs rank-biserial correlation. $^\star$Step of the sequence of RQ2; only ``Repository tools vs REPL only'' changes a single component (Section~\ref{sec:rq2}).}
\label{tab:tests}
\scriptsize
\setlength{\tabcolsep}{3pt}
\begin{tabular}{lccrrrrr}
\toprule
& \multicolumn{5}{c}{$G_{SRC}$} & \multicolumn{2}{c}{$G_{PR}^{exist}$} \\
\cmidrule(lr){2-6}\cmidrule(lr){7-8}
Comparison & $\Delta_{\mu}$ [95\% CI] & $\Delta_{i}$ [95\% CI] & W/L & $p_{Holm}$ & $r$ & $\Delta_{i}$ & $p_{Holm}$ \\
\midrule
""" + "\n".join(rows) + r"""
\bottomrule
\end{tabular}
\end{table*}
""")


def subsets_table():
    """Python-only gold set and the 67 issues whose texts were not written for this study."""
    rows = []
    for m in ALLK:
        a = R["pooled_all"][m]["SRC"]; b = R["pooled_all"][m]["SRC_PY"]; c = R["pooled_organic"][m]["SRC"]
        cell = lambda v: f"{f3(v['F1'])} [{f3(v['F1_boot'][0])}, {f3(v['F1_boot'][1])}]"
        if m in ("ds_repl", "codex", "rrl", "rrl_k"):
            rows.append(r"\midrule")
        rows.append(f"{METHOD_LABELS[m]} & {cell(a)} & {cell(b)} & {cell(c)} \\\\")
    npy = sum(len(g['SRC_PY']) for w in W for g in gold[w].values()) if 'SRC_PY' in next(iter(gold['2020'].values())) else \
        sum(1 for w in W for g in gold[w].values() for f in g['SRC'] if f.endswith('.py'))
    nsrc = sum(len(g['SRC']) for w in W for g in gold[w].values())
    n_org = sum(len(gold[w]) for w in ("2020", "openlibrary", "qutebrowser"))
    write("subsets", r"""\begin{table}[t]
\centering
\caption{Pooled micro-F1 with 95\% issue-bootstrap CIs on three scopes. $G_{SRC}$: all """ + str(N_ALL) + r""" issues. Python only: the """ + str(npy) + r""" Python files of the """ + str(nsrc) + r""" $G_{SRC}$ files, with predictions restricted to Python source files, which is the scope that the published localizers index. Without generated texts: the """ + str(n_org) + r""" issues of Ansible 2020, Open Library, and qutebrowser, whose issue texts come from SWE-bench Pro.}
\label{tab:subsets}
\resizebox{\columnwidth}{!}{%
\begin{tabular}{lccc}
\toprule
Method & $G_{SRC}$ & Python only & Without generated texts \\
\midrule
""" + "\n".join(rows) + r"""
\bottomrule
\end{tabular}}
\end{table}
""")


def guidance_table():
    """RQ3: forced consultation and Agentless candidates against the default system, plus output combinations."""
    def d(x):
        return f"{x:+.3f}".replace("-", "$-$")

    def ci(lo, hi):
        return f"[{d(lo)}, {d(hi)}]"

    rows = []
    gd = {t["a"]: t for t in R["tests"]["SRC"]["guidance"]}
    for m, lab in (("ds_adaptive", "Default (adaptive)"), ("ds_nudged", "Nudged consultation"), ("ds_seeded", "Seeded with Agentless")):
        v = R["pooled_all"][m]["SRC"]
        calls = statistics.mean(R["consultation"][w][m]["calls_per_inst"] for w in W)
        t = tok(statistics.mean(R["by_window"][w][m]["SRC"]["tokens_per_inst_mean"] for w in W))
        if m in gd:
            g = gd[m]; dd = g["diff"]
            pval = "$<$.001" if g["p"] < 0.001 else f"{g['p']:.2f}"
            cmp = (f"{d(dd['d_micro'])} {ci(*dd['d_micro_ci'])} & {d(dd['d_mean'])} {ci(*dd['d_mean_ci'])} & "
                   f"{g['wins']}/{g['losses']} & {pval}")
        else:
            cmp = "-- & -- & -- & --"
        rows.append(f"{lab} & {f3(v['F1'])} & {f3(v['P'])} & {f3(v['R'])} & {calls:.2f} & {t} & {cmp} \\\\")
    c = R.get("combinations") or {}
    if c:
        rows.append(r"\midrule")
        for rule, lab in (("union", "Union with Agentless"), ("intersection", "Intersection with Agentless"), ("cascade", r"Cascade$^\dagger$")):
            v = c[rule]
            rows.append(f"{lab} & {f3(v['F1'])} & {f3(v['P'])} & {f3(v['R'])} & & & & & & \\\\")
    note = ""
    if c:
        note = (r" $^\dagger$Answers with the Agentless files when Agentless and CoSIL return the same set ("
                + f"{100*c['cascade']['frac_cheap']:.0f}" + r"\% of issue runs) and with the default system otherwise, saving "
                + f"{100*c['cascade']['token_saving']:.0f}" + r"\% of its tokens.")
    write("guidance", r"""\begin{table*}[t]
\centering
\caption{Guiding the coordinator (RQ3), pooled over all """ + str(N_ALL) + r""" issues under $G_{SRC}$, with three runs of the default system and one run of each variant. Consult. is the mean number of consultation calls per issue and Tokens the mean tokens per issue. $\Delta_{\mu}$ and $\Delta_{i}$ are the differences from the default system in pooled micro-F1 and in mean per-issue F1, with 95\% paired bootstrap intervals, W/L counts issues better and worse than the default, and $p$ is from the two-sided Wilcoxon signed-rank test. The lower rows combine the final outputs of the default system and of Agentless without changing the coordinator.""" + note + r"""}
\label{tab:guidance}
\small
\setlength{\tabcolsep}{3.5pt}
\begin{tabular}{lrrrrrccrr}
\toprule
Variant & F1 & P & R & Consult. & Tokens & $\Delta_{\mu}$ [95\% CI] & $\Delta_{i}$ [95\% CI] & W/L & $p$ \\
\midrule
""" + "\n".join(rows) + r"""
\bottomrule
\end{tabular}
\end{table*}
""")


def ir_table():
    rows = []
    names = [("bm25", "BM25"), ("vsm", "VSM (TF-IDF)"), ("rvsm", "rVSM (BugLocator)"), ("path_bm25", "BM25, path only"), ("l2r", "Learning-to-rank")]
    cols = []
    for w in W:
        cols.append(bold_best([f3(ir(n, w)["F1_transfer"]) for n, _ in names], [ir(n, w)["F1_transfer"] for n, _ in names]))
    for i, (n, lab) in enumerate(names):
        rows.append(f"{lab} & " + " & ".join(f"{cols[j][i]} & {ir(n, w)['MAP']:.2f}" for j, w in enumerate(W)) + r" \\")
    write("ir", r"""\begin{table*}[t]
\centering
\caption{Non-LLM baselines under $G_{SRC}$, each indexed at the issue's own base commit. F1 is the micro-F1 at the cutoff $K$ selected on other windows, namely the two other Ansible windows for Ansible and all Ansible windows for the added repositories, whose learning-to-rank model is also trained on Ansible only. MAP is the mean average precision of the full ranking. The best F1 per window is in bold.}
\label{tab:ir}
\small
\setlength{\tabcolsep}{4pt}
\begin{tabular}{lrrrrrrrrrr}
\toprule
& \multicolumn{2}{c}{""" + "} & \\multicolumn{2}{c}{".join(WL[w] for w in W) + r"""} \\
""" + "".join(f"\\cmidrule(lr){{{2+2*j}-{3+2*j}}}" for j in range(len(W))) + r"""
Ranker & """ + " & ".join(["F1 & MAP"] * len(W)) + r""" \\
\midrule
""" + "\n".join(rows) + r"""
\bottomrule
\end{tabular}
\end{table*}
""")


def ensemble_table():
    rows = []
    for m, lab in [("plain_haiku", "Plain LLM (Haiku)"), ("plain_sonnet", "Plain LLM (Sonnet)"), ("rlm_haiku", "RLM (Haiku)")]:
        cells = []
        for w in W:
            cells.append(f"{f3(R['by_window'][w][m]['SRC']['F1'])} / {f3(R['ensembles'][w][f'{m}_majority']['SRC']['F1'])}")
        rows.append(f"{lab} & " + " & ".join(cells) + r" \\")
    rows.append(r"\midrule")
    rows.append("Domain agents (Haiku), single run & " + " & ".join(f3(R['by_window'][w]['ds_adaptive']['SRC']['F1']) for w in W) + r" \\")
    write("ensemble", r"""\begin{table*}[t]
\centering
\caption{Extra inference without exploration. Each cell gives the micro-F1 under $G_{SRC}$ of a single run and of a majority vote over the 3 to 5 independent runs of each baseline, in which a file is kept if more than half of the runs predict it. Union voting was lower than majority voting in every cell and is reported in the replication package.}
\label{tab:ensemble}
\small
\begin{tabular}{lccccc}
\toprule
Method & """ + " & ".join(WL[w] for w in W) + r""" \\
\midrule
""" + "\n".join(rows) + r"""
\bottomrule
\end{tabular}
\end{table*}
""")


def sensitivity_table():
    rows = []
    for m in LLM:
        full = R["by_window"]["2020"][m]["SWE"]["F1"]
        sub = R["sensitivity"]["results"][m]["SWE"]["F1"]
        rows.append(f"{METHOD_LABELS[m]} & {f3(full)} & {f3(sub)} & {sub-full:+.3f} \\\\")
    write("sensitivity", r"""\begin{table}[t]
\centering
\caption{Checkout-policy sensitivity (Ansible 2020, $G_{SWE}$). Restricting to the 13 issues whose gold files all exist at the earliest commit \texttt{01e7915} (used by the 2020 Sonnet RLM runs) leaves the ranking of methods unchanged.}
\label{tab:sensitivity}
\scriptsize
\begin{tabular}{lrrr}
\toprule
Method & All 19 & 13 unaffected & $\Delta$ \\
\midrule
""" + "\n".join(rows) + r"""
\bottomrule
\end{tabular}
\end{table}
""")


def audit_table():
    A = json.load(open(HERE / "access_audit.json"))
    runs_with = lambda m, cat, roles: len({(x["window"], x["run"], x["instance_id"]) for x in A["flags"]
                                           if x["method"] == m and x["category"] == cat and x["role"] in roles})
    rows = []
    order = ["rlm_haiku", "rlm_sonnet", "ds_repl", "ds_nospawn", "ds_maponly", "ds_adaptive", "ds_nudged", "ds_seeded", "codex"]
    for m in order:
        c = A["coverage"].get(m)
        if not c:
            continue
        act = c.get("reported_actions", 0) + c.get("repetition_actions", 0)
        out = c.get("reported_outputs", 0) + c.get("repetition_outputs", 0)
        mb = (c.get("reported_output_chars", 0) + c.get("repetition_output_chars", 0)) / 1e6
        n = lambda x: f"{x:,}".replace(",", "{,}")
        rows.append(f"{METHOD_LABELS[m]} & {c['issue_runs']} & {n(act)} & {n(out)} & {mb:.1f} & "
                    f"{runs_with(m, 'temp_dir', ('reported', 'first_attempt'))} & "
                    f"{runs_with(m, 'analysis_tool_files', ('first_attempt',))} \\\\")
    write("audit", r"""\begin{table}[t]
\centering
\caption{Coverage of the access audit per configuration: issue runs, agent actions (tool calls, REPL blocks, Codex commands) and their outputs scanned, size of the scanned outputs, issue runs whose agent code used the shared temporary directory, and among them the issue runs whose output showed files of our analysis tools, which were repeated (Section~\ref{sec:protocol}).}
\label{tab:audit}
\scriptsize
\begin{tabular}{lrrrrrr}
\toprule
Configuration & Runs & Actions & Outputs & MB & \texttt{/tmp} & Repeated \\
\midrule
""" + "\n".join(rows) + r"""
\bottomrule
\end{tabular}
\end{table}
""")


def docs_table():
    rows = []
    specs = [("2020", "docs/"), ("qutebrowser", "doc/")]
    stats = {}
    for w, pre in specs:
        g = gold[w]
        dg = {iid: {f for f in x["SRC"] if f.startswith(pre)} for iid, x in g.items()}
        sg = {iid: {f for f in x["SRC"] if not f.startswith(pre)} for iid, x in g.items()}
        stats[w] = (sum(len(v) for v in sg.values()), sum(len(v) for v in dg.values()))
        for m in ALL:
            rs = runs[w][m]
            dr = statistics.mean(sum(len(set(r["instances"][iid]["pred"]) & dg[iid]) for iid in g) for r in rs) / stats[w][1]
            sr = statistics.mean(sum(len(set(r["instances"][iid]["pred"]) & sg[iid]) for iid in g) for r in rs) / stats[w][0]
            stats[(w, m)] = (sr, dr)
    for m in ALL:
        cells = []
        for w, _ in specs:
            sr, dr = stats[(w, m)]
            cells.append(f"{100*sr:.0f}\\% & {100*dr:.0f}\\%")
        rows.append(f"{METHOD_LABELS[m]} & " + " & ".join(cells) + r" \\")
    write("docs", r"""\begin{table}[t]
\centering
\caption{Documentation co-change. Recall of code and of documentation files in $G_{SRC}$ for Ansible 2020 (""" + f"{stats['2020'][0]} code, {stats['2020'][1]} documentation files" + r""") and qutebrowser (""" + f"{stats['qutebrowser'][0]} code, {stats['qutebrowser'][1]} documentation files" + r""").}
\label{tab:docs}
\scriptsize
\begin{tabular}{lrrrr}
\toprule
& \multicolumn{2}{c}{Ansible 2020} & \multicolumn{2}{c}{qutebrowser} \\
\cmidrule(lr){2-3}\cmidrule(lr){4-5}
Method & Code & Docs & Code & Docs \\
\midrule
""" + "\n".join(rows) + r"""
\bottomrule
\end{tabular}
\end{table}
""")


if __name__ == "__main__":
    benchmark_table(); main_table(); allgold_table(); swe_table(); newfile_table(); tests_table(); ir_table()
    docs_table(); subsets_table(); guidance_table(); audit_table()
    print("tables written to", OUT)
