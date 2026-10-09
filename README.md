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
| `data/runs.json` | Every LLM run: per-instance predicted files, token counts, REPL calls, consultation counts, commit used, and run configuration. |
| `data/results.json`, `data/ir_results.json`, `data/ir_results_new_repos.json` | Outputs of `evaluate.py` and `ir_baselines.py` (Ansible leave-one-window-out; `--new-repos`: trained on Ansible, tested on the added repositories). |
| `data/swebench_pro_v1_repo_stats.csv` | Per-repository statistics of SWE-bench Pro v1 used for repository selection. |
| `scripts/` | Analysis code (see below). |
| `data/tool_limits.json`, `scripts/tool_limits.py` | Every file read of the coordinator-only runs on Open Library and qutebrowser, with the reads that returned only the first lines of a long file (RQ2). `python3 tool_limits.py` prints the counts reported in the paper. |
| `traces/` | (to be added) raw run reports including full agent trajectories and domain-agent registries. |

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
```

`extract_runs.py` builds `data/runs.json` from the raw run reports (in `traces/`); it is included for transparency and is not needed to reproduce the tables.

## Gold-set definitions

* `PR`: all files changed by the resolving pull request.
* `SRC`: `PR` minus test files (any `test`/`tests`/`testing` directory, `test_*.py`, `conftest.py`), changelogs, and build/CI/dev-tooling metadata; same rule for every repository (`common.is_source`).
* `PR_EXIST` / `PR_NEW`: files of `PR` that do / do not exist at the instance's base commit.
* `SWE`: the files of the SWE-bench Pro gold patch (all windows except Ansible 2025 and 2026, which are not in SWE-bench Pro).

## Notes

* Under `SRC` and `SWE`, predicted files that `common.is_source` classifies as tests, changelogs or metadata are removed before scoring, for every method; the rankers' candidate lists are filtered before the top-K cutoff. `PR`, `PR_EXIST` and `PR_NEW` are scored on all predictions.

* The Ansible 2020 Sonnet RLM runs used a single checkout at `01e7915`; all other repository-accessing methods used each instance's own base commit. `evaluate.py` reports a sensitivity analysis excluding affected instances.
* Raw run reports with full trajectories (about 7 GB) are archived separately; `data/runs.json` holds everything the analysis uses.
* Bootstrap resampling uses a fixed seed; results are deterministic.
