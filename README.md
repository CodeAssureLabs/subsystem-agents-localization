# Replication package: Exploration Structure in LLM Agents for Multi-File Change Localization

This package regenerates every table and figure of the paper from the recorded predictions.

The agent implementation used for all LLM runs (coordinator, repository tools, domain-agent registry,
RLM and Codex runners) is at https://github.com/CodeAssureLabs/swe-agent-spawning.

## Contents

| Path | Description |
|---|---|
| `data/benchmark.json` | The 105 instances (Ansible 2020/2025/2026, Open Library, qutebrowser): instance id, base commit, issue text, and the gold sets `SWE` (SWE-bench Pro gold patch, where available), `SRC`, `PR`, `PR_EXIST`, `PR_NEW`. |
| `benchmarks/` | Open Library and qutebrowser windows in the experiment harness's input format (`build_benchmarks.py`). |
| `harness_patches/` | Changes made to the experiment harness (CodeAssureLabs/swe-agent-spawning) for the added repositories: full consultation logging, Codex reasoning-effort option, batch script, hung-call watchdog. `seed_files.diff` and `run_seed_ablation.sh` add and run the `--seed-files` option of the seeding ablation. |
| `baselines/` | The four published LLM localizers (Agentless, CoSIL, LocAgent, and our reimplementation of Reformulate-Retrieve-Localize): run scripts, our changes to their code, and all predictions. See `baselines/README.md`. |
| `seed_ablation/` | The seeding ablation: Agentless candidates per instance, the seeded domain-agent runs, and `score_ablation.py`, which produces its table. |
| `RUNBOOK_new_repos.md` | Protocol used for the Open Library and qutebrowser runs. |
| `data/runs.json` | Every LLM run: per-instance predicted files (and ranked lists for the published localizers), token counts, REPL calls, consultation counts, status, step-limit endings, commit used, and run configuration. Runs of the first submission that were replaced in the revision are kept under `<method>_r0`. |
| `data/tool_logs.jsonl.gz` | Revision runs: one line per agentic issue run with every tool call and its arguments, every access refused by the guard, status and step-limit ending, the RLM's REPL code, and every Codex command (`scripts/export_r1.py`). |
| `data/r1_runs.json`, `data/path_audit.json` | Date and configuration of every revision run, and the tool calls whose path argument lies outside the checkout (none). |
| `data/access_audit.json` | Access audit of all 2,205 revision issue runs (`scripts/access_audit.py`). Every agent action (tool call, REPL block, Codex command) is paired with its output. Actions are checked for history and network commands, paths outside the checkout, benchmark or result file names, and use of the shared temporary directory; outputs for the resolving commit's hash, lines the resolving commit adds, and, for actions in the temporary directory, every path shown, the issue's gold files, and files of our analysis tools. Contains the coverage per configuration (`tables/audit.tex`), flag counts, and every flag with its context. The script fails instead of skipping when a log, clone, or commit is missing; it takes `--runs`, `--harness`, and `--repeated` and needs the raw run reports and full clones. |
| `data/access_audit_evidence.json` | Sanitized evidence for the audit: the 9 repeated issue runs with the actions in the temporary directory and their outputs for the first attempt and the repetition, every action in the temporary directory of the reported runs with its output and the paths it showed, and every match of a line added by the fix with its context, classification, and reason. |
| `data/repeated_runs.json` | Manifest of the 4 reported issue runs (coordinator-only and map-only) that were repeated under the strict guard: window, configuration, repetition, issue, start time and guard of the first attempt and of the repetition, registry session, confirmation that the registry was reused, and the accesses the guard refused. Both guards are available in the harness (`AGENT_GUARD_MODE=shared-tmp`, used for all other revision runs, and `strict`). |
| `data/outcomes.json` | How every agentic issue run ended: file list, empty list, step limit with or without a file list, timeout, or error, with instance identifiers (`scripts/text_numbers.py`). |
| `data/leak_audit_r0/` | Audit of the tool logs of the first-submission runs for access to later git history, the network, and files outside the checkout. |
| `data/issue_overlap*` | Overlap between issue texts and the identifiers changed by the fix, for all 105 issues (`scripts/issue_overlap.py`). |
| `data/results_pre_R1.json` | Results of the first submission, for the before/after comparison in the response to the reviewers. |
| `data/results.json`, `data/ir_results.json`, `data/ir_results_new_repos.json` | Outputs of `evaluate.py` and `ir_baselines.py` (Ansible leave-one-window-out; `--new-repos`: trained on Ansible, tested on the added repositories). |
| `data/swebench_pro_v1_repo_stats.csv` | Per-repository statistics of SWE-bench Pro v1 used for repository selection. |
| `scripts/` | Analysis code (see below). |
| `data/tool_limits.json`, `scripts/tool_limits.py` | Every file read of the coordinator-only runs on Open Library and qutebrowser, with the reads that returned only the first lines of a long file (RQ2). `python3 tool_limits.py` prints the counts reported in the paper. |
| `data/registries.json` | Every domain-agent registry of the revision runs: window, method, run, the commit at which it was built, initialization tokens, and for each agent its name, folders, area description and familiarization summary. |
| `data_generation/` | Selection of the Ansible 2025 and 2026 pull requests and generation of their issue texts with a Codex worker (copied from the harness repository): selection rules, curated PR lists, and the generation instruction. |
| `prompts.md` | All prompts: task prompts, system prompts of the coordinator and the domain agents, registry construction, the seeded variant, and the baselines. |

## Reproducing

```bash
pip install numpy scipy scikit-learn rank-bm25 matplotlib
git clone --bare https://github.com/ansible/ansible.git ansible.git                  # or set ANSIBLE_REPO=/path
git clone --bare https://github.com/internetarchive/openlibrary.git openlibrary.git  # or OPENLIBRARY_REPO
git clone --bare https://github.com/qutebrowser/qutebrowser.git qutebrowser.git      # or QUTEBROWSER_REPO
cd scripts
python3 evaluate.py        # rescoring, bootstrap CIs, Wilcoxon/Holm tests, new-file analysis, sensitivity, ensembles
python3 ir_baselines.py              # rankers on Ansible, leave-one-window-out (~5 min)
python3 ir_baselines.py --new-repos  # rankers trained on Ansible, tested on Open Library and qutebrowser
python3 tables.py          # LaTeX tables -> ../tables/
python3 figures.py         # figures -> ../figures/
python3 text_numbers.py    # every number quoted in the text -> ../tables/numbers.tex
```

`extract_runs.py` builds `data/runs.json` from the raw run reports; it is included for transparency and is not needed to reproduce the tables.

## Gold-set definitions

* `PR`: all files changed by the resolving pull request.
* `SRC`: `PR` minus test files (any `test`/`tests`/`testing` directory, `test_*.py`, `conftest.py`), changelogs, and build/CI/dev-tooling metadata; same rule for every repository (`common.is_source`).
* `PR_EXIST` / `PR_NEW`: files of `PR` that do / do not exist at the instance's base commit.
* `SWE`: the files of the SWE-bench Pro gold patch (all windows except Ansible 2025 and 2026, which are not in SWE-bench Pro).

## Revision (IEEE Access, first resubmission)

All agentic configurations were rerun with the corrected harness (CodeAssureLabs/swe-agent-spawning, `run_revision_r1.py`):
each issue runs in a checkout that contains only its base commit, agent code runs under a guard that refuses network access,
`git`, and files outside the checkout, an issue that reaches the step limit gets a final answer turn instead of an unflagged
empty prediction, the RLM runner takes one REPL action per turn, and `extract_runs.norm` no longer rewrites valid
`test/...` paths. The published localizers are also scored at a held-out top-K, and every method on Python files only.

## Notes

* Under `SRC` and `SWE`, predicted files that `common.is_source` classifies as tests, changelogs or metadata are removed before scoring, for every method; the rankers' candidate lists are filtered before the top-K cutoff. `PR`, `PR_EXIST` and `PR_NEW` are scored on all predictions.

* The raw run reports with the full agent conversations are too large for this repository and are available from the authors on request. `data/runs.json` and `data/tool_logs.jsonl.gz` hold everything the analysis uses. `scripts/access_audit.py` also reads the tool outputs in the raw reports and the full clones, so it runs only with those; its complete output is in `data/access_audit.json`.
* Bootstrap resampling uses a fixed seed; results are deterministic.
