# Runbook: LLM runs on openlibrary and qutebrowser

This is for whoever has the experiment harness (coordinator, bounded tools, registry, `consult_agents`, RLM runner, Codex runner) and the API keys. Everything else (benchmarks, gold sets, non-LLM baselines, scoring, tables, figures) is already done and lives in `revision/`.

## 1. Inputs

| Repository | Benchmark file | Window | Issues | Registry commit (`fixed_commit`) |
|---|---|---|---|---|
| internetarchive/openlibrary | `revision/benchmarks/benchmark_openlibrary_pr_gold.json` | Jul 2023 – Jan 2024 | 22 | `34099a36bcd3e9f33e169beb06f64dfab81c2cde` |
| qutebrowser/qutebrowser | `revision/benchmarks/benchmark_qutebrowser_pr_gold.json` | Nov 2020 – Apr 2021 | 26 | `e46adf32bdf880385319cb701d926fec6899046d` |

The files use the same schema as `benchmark_ansible_pr_gold.json`, with extra fields `fix_commit`, `source_gold_files` and a top-level `repo`. Use `problem_statement` as the issue text; it is the SWE-bench Pro field, which is what the Ansible runs used. The harness's own scoring does not matter, because all scoring is redone from `predicted_files`.

Clone the repositories:

```bash
git clone https://github.com/internetarchive/openlibrary.git
git clone https://github.com/qutebrowser/qutebrowser.git
```

## 2. Protocol (keep identical for every method; this fixes problems reviewers raised)

1. **Checkout.** Check out each instance's own `base_commit` before every issue, for every method that reads the repository: RLM (Haiku and Sonnet), coordinator only, domain agents, and Codex. Do not use one fixed checkout.
2. **Registry.** Build the domain-agent registry once per repository, at `fixed_commit`. Reuse it for all issues and runs of that repository. Reset per-issue notes between issues, exactly as for Ansible.
3. **Timeout.** Use 600 s per issue for all agentic runs: coordinator only, domain agents, and Codex. (Ansible mixed 300 s and 600 s.)
4. **RLM cap.** Use `max_iterations = 30` for both Haiku and Sonnet. (Ansible 2020 Sonnet used 15.)
5. **Prompt.** Use the same task prompt as for Ansible (paper, Appendix A).
6. **Models.** Use `claude-haiku-4-5` and `claude-sonnet-4-6`, plus the same Codex CLI version and reasoning setting as for Ansible. Record the exact Codex model id in the config.

## 3. Runs, in priority order

Token estimates use the Ansible averages per issue × 48 issues × runs.

| Priority | Method key | Configuration | Runs per repo | Approx. tokens (both repos) |
|---|---|---|---|---|
| 1 | `plain_haiku` | Plain LLM, Haiku | 3 | < 1M |
| 1 | `rlm_haiku` | RLM, Haiku, cap 30 | 3 | 6M |
| 1 | `ds_nospawn` | Coordinator only (no registry), Haiku | **3** (Ansible had 1) | 120M |
| 1 | `ds_adaptive` | Domain agents, adaptive, Haiku | 3 | 170M (+ about 2.5M for registry setup) |
| 2 | `plain_sonnet` | Plain LLM, Sonnet | 3 | < 1M |
| 2 | `rlm_sonnet` | RLM, Sonnet, cap 30 | 3 | 30M |
| 2 | `codex` | Codex CLI | 3 | 145M |
| 3 | `ds_nudged` | Domain agents, forced consultation, same registry | 1 | 60M |

Priority 1 gives the equal-model ablation ladder (RQ2) on the new repositories. Running `ds_nospawn` three times also removes the n=1 weakness that Reviewer 2 noted.

## 4. Output files

Save one JSON report per run, in the same format the harness wrote for Ansible:
- top-level `config`, `benchmark` and `subagent_initialization` (with `agents` and `metrics`);
- `results`, with one entry per instance.

Name the files `<method key>_<run number>.json` and put them in:

```
revision/new_runs/openlibrary/ds_adaptive_1.json
revision/new_runs/openlibrary/ds_adaptive_2.json
...
revision/new_runs/qutebrowser/codex_3.json
```

Each entry in `results` must contain at least these fields:
- `instance_id`, `problem_statement`, `predicted_files`
- `base_commit`, `actual_commit`
- `total_tokens`, `input_tokens`, `output_tokens`

For agent runs, also keep:
- `repl_calls`, `subagent_consult_calls`, `subagent_consults`
- `conversation_history`
- `rlm_trajectory` (RLM runs only)

Please also keep the **full, untruncated** `consult_agents` results; the Ansible logs cut them at 1,000 characters. They are needed to count how many domain agents answer each consultation.

## 5. Scoring (no API access needed)

```bash
cd revision/analysis
python3 extract_runs.py      # picks up new_runs/<repo>/*.json automatically
python3 evaluate.py          # adds the new windows; pooled_all and family_all tests appear
python3 tables.py            # writes tex/tables/newrepos.tex, among others
python3 figures.py
```

`results.json` then contains per-repository results, a pooled analysis over all five windows (`pooled_all`), and the planned comparisons over all 105 issues with Holm correction (`tests/*/family_all`). The paper text for the new repositories should be written after seeing these numbers.

## 6. What to expect

On the new repositories the non-LLM rankers are much stronger than on Ansible. Trained only on Ansible, L2R reaches micro-F1 0.411 (openlibrary) and 0.400 (qutebrowser) under `G_SRC`; BM25 reaches 0.397 and 0.405. On Ansible both were about 0.26. The bar for the LLM methods is therefore higher, and this should be reported whichever way it comes out.

## 7. Two facts the paper still needs from you

1. The exact rule used to select the 19 issues per window for Ansible 2025 and 2026.
2. The Codex CLI model id and reasoning-effort setting.
