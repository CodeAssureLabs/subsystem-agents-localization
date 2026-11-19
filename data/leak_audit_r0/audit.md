# Leakage audit of agent tool logs (git history, network, outside-checkout files)

Scope: every agentic issue run used in the paper (runs.json: rlm_haiku, rlm_sonnet, ds_nospawn, ds_adaptive, ds_adaptive_t300, ds_nudged, codex) plus all revision/seed_ablation/*/ds_seeded_*.json. One "issue run" = one issue in one run file. Post-base commits were identified by resolving every SHA printed by git against full clones (ansible/ansible fetched to the scratchpad; local openlibrary and qutebrowser clones) and checking ancestry of and date relative to the base commit.

## Counts per method (issue runs)

| method | issue runs | with code trace | any git | git HEAD-only | git history cmd | beyond-base git attempt | post-base commits in output | fix commit/backport seen | fix-commit files seen | network attempt | network success | outside-checkout access (heuristic) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| rlm_haiku | 315 | 315 | 19 | 2 | 17 | 13 | 14 | 7 | 0 | 0 | 0 | 2 |
| rlm_sonnet | 353 | 258 | 163 | 6 | 157 | 110 | 101 | 44 | 19 | 9 | 8 | 94 |
| ds_nospawn | 315 | 314 | 9 | 6 | 3 | 2 | 2 | 2 | 2 | 0 | 0 | 26 |
| ds_adaptive | 353 | 350 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 38 |
| ds_adaptive_t300 | 38 | 36 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 4 |
| ds_nudged | 19 | 18 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 |
| ds_seeded | 315 | 315 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 34 |
| codex | 353 | 0 | 26 | 26 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

Notes: codex has no full trace (only the first 2000 chars of the event stream, 538 visible commands, all `rg`/`git status --short`/reads of `~/.codex/memories/MEMORY.md`). rlm_sonnet 2020 (95 issue runs) has no trace at all. Outside-checkout counts for ds_* are almost entirely scratch files in /tmp, guessed non-existent paths (/tmp/ansible, /tmp/codebase) or `cwd=/tmp`; manual review found no ds_* run that read anything outside the checkout that was relevant to the issue or the gold answer.

## Potential leaks where the fix itself was observed (22 issue runs)

| class | method | window | run file | instance | gold∩pred | evidence |
|---|---|---|---|---|---|---|
| FIX_SEEN_NOT_USED | rlm_sonnet | 2025 | rlm_hinted_2025_sonnet_1.json | instance_ansible__ansible-558676fcdc6d3f083f4a5582427675842d | 0/2 | agent ran git show 558676fcdc --stat/--name-only/diff (both gold files listed) but concluded HEAD commit 3518d48146 was the fix; prediction contains 0/2 gold files |
| FIX_SEEN_NOT_USED | rlm_sonnet | openlibrary | rlm_sonnet_1.json | instance_internetarchive__openlibrary-3f7db6bbbcc7c418b3db72 | 0/3 | git log --all --name-status output included fix 3f7db6bbbc with its 3 gold files; prediction contains 0/3 gold files (invented openlibrary/catalog/isbndb/*) |
| POTENTIAL_LEAK_LIKELY_USED | ds_nospawn | 2025 | no_agents_2025_haiku_1.json | instance_ansible__ansible-649c9ec4431feca274e4d14d7a1bc835d7 | 4/4 | git log --all --grep=EncryptedString found fix 649c9ec443 and its stable backport ebae950db2; agent ran git show --name-status ebae950db2 (lists all 4 gold files) and git show ebae950db2 -- <each file>; prediction contains all 4 gold files plus the 3 test files touched by the backport |
| POTENTIAL_LEAK_LIKELY_USED | ds_nospawn | 2026 | ds_nospawn_3.json | instance_ansible__ansible-36e9711c26f4efcf3df7b1eb5c66dd1d78 | 1/1 | git log --all --grep=deepcopy found fix 36e9711c26; agent ran git show 36e9711c26 --stat and full diff; prediction contains the gold file; rationale mirrors the diff (__deepcopy__ returning self) |
| POTENTIAL_LEAK_LIKELY_USED | rlm_sonnet | 2025 | rlm_hinted_2025_sonnet_2.json | instance_ansible__ansible-532edf4c357257b68b828a620c6a890fef | 1/1 | git log --all --grep tag found fix 532edf4c35 and backport 33c55b9c25; repeated git show --stat/--name-only/diff; agent comment: "These are the commits that FIX the bug"; prediction contains the gold file |
| POTENTIAL_LEAK_LIKELY_USED | rlm_sonnet | 2025 | rlm_hinted_2025_sonnet_3.json | instance_ansible__ansible-532edf4c357257b68b828a620c6a890fef | 1/1 | git show --stat/--name-only/diff-tree of backport 33c55b9c25 (cherry-pick of fix); prediction contains the gold file |
| POTENTIAL_LEAK_LIKELY_USED | rlm_sonnet | 2026 | rlm_hinted_2026_sonnet_1.json | instance_ansible__ansible-36e9711c26f4efcf3df7b1eb5c66dd1d78 | 1/1 | git show 36e9711c26 --stat/--name-status/diff-tree and backport 82d13085a2; scored prediction contains the gold file |
| POTENTIAL_LEAK_LIKELY_USED | rlm_sonnet | 2026 | rlm_hinted_2026_sonnet_1.json | instance_ansible__ansible-51d5a456ef5342f5b18739d4211ac09ff9 | 2/3 | agent: "Let me look at the commit that supposedly fixed this bug"; git show 51d5a456ef --stat/--name-only/diff lists all 3 gold files; prediction contains 2/3 |
| POTENTIAL_LEAK_LIKELY_USED | rlm_sonnet | 2026 | rlm_hinted_2026_sonnet_1.json | instance_ansible__ansible-90595736ed35a88e63b6c680d6a1daa38a | 1/2 | git show --name-only/--stat/diff 90595736ed (both gold files); prediction contains 1/2 |
| POTENTIAL_LEAK_LIKELY_USED | rlm_sonnet | 2026 | rlm_hinted_2026_sonnet_1.json | instance_ansible__ansible-a51536f311d937ee92f7185fac445ca39b | 3/3 | agent: "Great! There's a commit 'Fix using the server's validate_certs config...' Let's look at what this commit changed" then "Perfect! Now I can see the files that need to be modified"; prediction contains 3/3 gold |
| POTENTIAL_LEAK_LIKELY_USED | rlm_sonnet | 2026 | rlm_hinted_2026_sonnet_1.json | instance_ansible__ansible-d9deb945b0186724585747477940fdd1b7 | 1/1 | git show d9deb945b0 --stat/diff and backport c83999378d; prediction contains the gold file |
| POTENTIAL_LEAK_LIKELY_USED | rlm_sonnet | 2026 | rlm_hinted_2026_sonnet_1.json | instance_ansible__ansible-f2357cdc53c99b7444f09deea398f0b80f | 1/1 | agent: "f2357cdc53 is the fix commit!"; git show --stat/diff/<sha>:<path> of the fix; prediction contains the gold file |
| POTENTIAL_LEAK_LIKELY_USED | rlm_sonnet | 2026 | rlm_hinted_2026_sonnet_2.json | instance_ansible__ansible-3adecacccf408960128d7cc122e8212a88 | 5/5 | agent final text: "The fix commit 3adecacccf ... was the actual fix, and I traced which files it changed"; prediction contains 5/5 gold |
| POTENTIAL_LEAK_LIKELY_USED | rlm_sonnet | 2026 | rlm_hinted_2026_sonnet_2.json | instance_ansible__ansible-90595736ed35a88e63b6c680d6a1daa38a | 1/2 | git log --all -p and git show 90595736ed (full sha); final text: "confirmed by finding the exact fix commit 90595736ed..."; prediction contains 1/2 |
| POTENTIAL_LEAK_LIKELY_USED | rlm_sonnet | 2026 | rlm_hinted_2026_sonnet_3.json | instance_ansible__ansible-36e9711c26f4efcf3df7b1eb5c66dd1d78 | 1/1 | many git show/diff-tree calls on 36e9711c26 and backport 82d13085a2; scored prediction contains the gold file |
| POTENTIAL_LEAK_LIKELY_USED | rlm_sonnet | 2026 | rlm_hinted_2026_sonnet_3.json | instance_ansible__ansible-3adecacccf408960128d7cc122e8212a88 | 2/5 | git show/diff-tree/diff 3adecacccf^..3adecacccf (all 5 gold files listed); prediction contains 2/5 |
| POTENTIAL_LEAK_LIKELY_USED | rlm_sonnet | 2026 | rlm_hinted_2026_sonnet_3.json | instance_ansible__ansible-90595736ed35a88e63b6c680d6a1daa38a | 1/2 | git log -p --all --grep=86473 and git show 90595736ed --stat/diff; prediction contains 1/2 |
| POTENTIAL_LEAK_LIKELY_USED | rlm_sonnet | 2026 | rlm_hinted_2026_sonnet_3.json | instance_ansible__ansible-cb535cf3d3159e24b813f4eb9085340ff6 | 1/1 | git show cb535cf3d3 --stat/--name-only/diff; prediction contains the gold file |
| POTENTIAL_LEAK_LIKELY_USED | rlm_sonnet | openlibrary | rlm_sonnet_2.json | instance_internetarchive__openlibrary-30bc73a1395fba2300087c | 5/5 | git log --all (with file names) showed fix 30bc73a13 "Supercharges cover archival with zip batch processing" touching archive.py/README.md/test_archive.py; agent comment lists this commit; prediction contains 5/5 gold |
| POTENTIAL_LEAK_LIKELY_USED | rlm_sonnet | qutebrowser | rlm_sonnet_2.json | instance_qutebrowser__qutebrowser-96b997802e942937e81d2b8a32 | 2/3 | git log --all -p -S parse_duration showed the fix diff (utils.py, utilcmds.py); prediction contains 2/3 gold (utils.py, test_utils.py) |
| POTENTIAL_LEAK_USE_UNCERTAIN | rlm_sonnet | qutebrowser | rlm_sonnet_3.json | instance_qutebrowser__qutebrowser-f631cd4422744160d9dcf7a045 | 6/6 | git show f631cd442 --stat/diff lists all 6 gold files; the agent had enumerated the same 7 candidate files in its comments just before ("Let me verify these files exist and check the git log"), so the output at least confirmed its list; prediction contains 6/6 gold |
| POTENTIAL_LEAK_LIKELY_USED | rlm_sonnet | qutebrowser | rlm_sonnet_2.json | instance_qutebrowser__qutebrowser-36ade4bba504eb96f05d32ceab | 2/2 | clone of CURRENT upstream (post-fix) succeeded; agent reassigned repo_path to the clone at block 49 and explored it for ~220 blocks (grep/open of qutebrowser/config/qtargs.py and tests/unit/config/test_qtargs.py, which in the clone already contain _DISABLE_FEATURES/--disable-features handling); it only switched back to the base checkout at block 270; final rationale describes adding `_DISABLE_FEATURES = "--disable-features="` exactly as in upstream; prediction = gold (2/2) |

Likely-used or uncertain, by method/window: ds_nospawn 2025: 1, ds_nospawn 2026: 1, rlm_sonnet 2025: 2, rlm_sonnet 2026: 12, rlm_sonnet openlibrary: 1, rlm_sonnet qutebrowser: 3.

## Weak exposure: only the one-line subject of the fix commit (or its backport) was printed (32 issue runs)

These come from `git log --all --oneline --grep=...` outputs. No file list or diff of the fix was printed. The subject can still hint at the change (e.g. rlm_sonnet 2025 run 1, ansible-4c04b8c7: subject "IncludedFile: store _from args..." → gold file playbook/included_file.py, which was predicted).

| method | window | run file | instance | gold∩pred |
|---|---|---|---|---|
| rlm_haiku | 2025 | rlm_hinted_2025_haiku_2.json | instance_ansible__ansible-11f5563895b3549d266435d7b15624fb63 | 0/5 |
| rlm_haiku | 2025 | rlm_hinted_2025_haiku_3.json | instance_ansible__ansible-558676fcdc6d3f083f4a5582427675842d | 1/2 |
| rlm_haiku | 2026 | rlm_hinted_2026_haiku_1.json | instance_ansible__ansible-36e9711c26f4efcf3df7b1eb5c66dd1d78 | 0/1 |
| rlm_haiku | 2026 | rlm_hinted_2026_haiku_1.json | instance_ansible__ansible-51d5a456ef5342f5b18739d4211ac09ff9 | 2/3 |
| rlm_haiku | 2026 | rlm_hinted_2026_haiku_2.json | instance_ansible__ansible-90595736ed35a88e63b6c680d6a1daa38a | 0/2 |
| rlm_haiku | 2026 | rlm_hinted_2026_haiku_3.json | instance_ansible__ansible-49f1615157c54a119d0e51b4df0e7c410e | 0/2 |
| rlm_haiku | 2026 | rlm_hinted_2026_haiku_3.json | instance_ansible__ansible-51d5a456ef5342f5b18739d4211ac09ff9 | 1/3 |
| rlm_sonnet | 2025 | rlm_hinted_2025_sonnet_1.json | instance_ansible__ansible-11f5563895b3549d266435d7b15624fb63 | 1/5 |
| rlm_sonnet | 2025 | rlm_hinted_2025_sonnet_1.json | instance_ansible__ansible-4c04b8c7c3f43b9c50831e97e4479e428c | 1/1 |
| rlm_sonnet | 2025 | rlm_hinted_2025_sonnet_1.json | instance_ansible__ansible-58bad718597540acdb9d861b803d5e3cfb | 1/4 |
| rlm_sonnet | 2025 | rlm_hinted_2025_sonnet_2.json | instance_ansible__ansible-91453e30afb2bef252049e73d853be06e7 | 2/3 |
| rlm_sonnet | 2025 | rlm_hinted_2025_sonnet_3.json | instance_ansible__ansible-46abcfcc824c199ad17ba5e3a9ceaf1611 | 1/2 |
| rlm_sonnet | 2025 | rlm_hinted_2025_sonnet_3.json | instance_ansible__ansible-558676fcdc6d3f083f4a5582427675842d | 0/2 |
| rlm_sonnet | 2026 | rlm_hinted_2026_sonnet_1.json | instance_ansible__ansible-49f1615157c54a119d0e51b4df0e7c410e | 2/2 |
| rlm_sonnet | 2026 | rlm_hinted_2026_sonnet_2.json | instance_ansible__ansible-f074c20929aad799b935a89494f7cc565c | 1/2 |
| rlm_sonnet | 2026 | rlm_hinted_2026_sonnet_3.json | instance_ansible__ansible-948f8f42d09e9ad1f0582611fa17a6f5ad | 3/3 |
| rlm_sonnet | openlibrary | rlm_sonnet_1.json | instance_internetarchive__openlibrary-fdbc0d8f418333c7e575c4 | 2/5 |
| rlm_sonnet | openlibrary | rlm_sonnet_2.json | instance_internetarchive__openlibrary-798a582540019363d14b20 | 6/9 |
| rlm_sonnet | openlibrary | rlm_sonnet_3.json | instance_internetarchive__openlibrary-1351c59fd43689753de1fc | 7/7 |
| rlm_sonnet | openlibrary | rlm_sonnet_3.json | instance_internetarchive__openlibrary-1be7de788a444f6255e89c | 2/7 |
| rlm_sonnet | openlibrary | rlm_sonnet_3.json | instance_internetarchive__openlibrary-c8996ecc40803b9155935f | 4/4 |
| rlm_sonnet | qutebrowser | rlm_sonnet_1.json | instance_qutebrowser__qutebrowser-34a13afd36b5e529d553892b1c | 0/2 |
| rlm_sonnet | qutebrowser | rlm_sonnet_1.json | instance_qutebrowser__qutebrowser-54bcdc1eefa86cc20790973d69 | 0/2 |
| rlm_sonnet | qutebrowser | rlm_sonnet_1.json | instance_qutebrowser__qutebrowser-96b997802e942937e81d2b8a32 | 2/3 |
| rlm_sonnet | qutebrowser | rlm_sonnet_2.json | instance_qutebrowser__qutebrowser-9b71c1ea67a9e7eb70dd83214d | 1/5 |
| rlm_sonnet | qutebrowser | rlm_sonnet_2.json | instance_qutebrowser__qutebrowser-fd6790fe8c02b144ab2464f1fc | 10/12 |
| rlm_sonnet | qutebrowser | rlm_sonnet_3.json | instance_qutebrowser__qutebrowser-01d1d1494411380d97cac14614 | 2/4 |
| rlm_sonnet | qutebrowser | rlm_sonnet_3.json | instance_qutebrowser__qutebrowser-0b621cb0ce2b54d3f93d8d41d8 | 2/3 |
| rlm_sonnet | qutebrowser | rlm_sonnet_3.json | instance_qutebrowser__qutebrowser-34a13afd36b5e529d553892b1c | 0/2 |
| rlm_sonnet | qutebrowser | rlm_sonnet_3.json | instance_qutebrowser__qutebrowser-44e64199ed38003253f0296bad | 2/2 |
| rlm_sonnet | qutebrowser | rlm_sonnet_3.json | instance_qutebrowser__qutebrowser-96b997802e942937e81d2b8a32 | 2/3 |
| rlm_sonnet | qutebrowser | rlm_sonnet_3.json | instance_qutebrowser__qutebrowser-9b71c1ea67a9e7eb70dd83214d | 0/5 |

## Post-base history reached, fix not observed (73 issue runs)

rlm_haiku: 7 (FUTURE_HISTORY_REACHED_FIX_NOT_SEEN); rlm_sonnet: 9 (BEYOND_BASE_ATTEMPT_NO_FUTURE_COMMITS_IN_OUTPUT); rlm_sonnet: 57 (FUTURE_HISTORY_REACHED_FIX_NOT_SEEN). Full list in audit.json (category git_history).

## Network

| class | window | run file | instance | command | evidence |
|---|---|---|---|---|---|
| POTENTIAL_LEAK_LIKELY_USED | qutebrowser | rlm_sonnet_2.json | instance_qutebrowser__qutebrowser-36ade4bba504eb96f05d3 | git clone --depth=1 https://github.com/qutebrowser/qutebrowser /tmp/qutebrowser; then repo_path = "/tmp/qutebrowser" | clone of CURRENT upstream (post-fix) succeeded; agent reassigned repo_path to the clone at block 49 and explored it for ~220 blocks (grep/open of qutebrowser/config/qtargs.py and tests/unit/config/test_qtargs.py, which in the clone already contain _DISABLE_FEATURES/--disable-features handling); it only switched back to the base checkout at block 270; final rationale describes adding `_DISABLE_FEATURES = "--disable-features="` exactly as in upstream; prediction = gold (2/2) |
| network_attempt_failed | qutebrowser | rlm_sonnet_2.json | instance_qutebrowser__qutebrowser-c09e1439f145c66ee3af5 | urllib.request.urlopen(api.github.com/repos/qutebrowser/qutebrowser/git/trees/main?recursive=1) | failed (SSL CERTIFICATE_VERIFY_FAILED) |
| network_success_no_gold_info | 2025 | rlm_hinted_2025_sonnet_1.json | instance_ansible__ansible-11f5563895b3549d266435d7b1562 | curl raw.githubusercontent.com/ansible/ansible/devel/lib/ansible/template/__init__.py | succeeded: first 50 lines (imports) of current devel template/__init__.py; not a gold file; prediction not derived from it |
| network_success_no_gold_info | 2025 | rlm_hinted_2025_sonnet_2.json | instance_ansible__ansible-11f5563895b3549d266435d7b1562 | curl raw.githubusercontent.com/ansible/ansible/devel/lib/ansible/template/__init__.py; git ls-remote https://github.com/ansible/ansible HEAD | both succeeded: 50 lines of imports of devel template/__init__.py (not a gold file) and the current HEAD sha; prediction (template/__init__.py, test_templar.py) has 0 gold files |
| network_success_no_gold_info | openlibrary | rlm_sonnet_2.json | instance_internetarchive__openlibrary-8a9d9d323dfcf2a5b | curl api.github.com/.../contents/scripts; curl api.github.com/.../git/trees/master?recursive=1 (head -100); curl httpbin.org/ip; git ls-remote | succeeded: names of current master scripts/ directory entries and first entries of master tree; gold files (scripts/providers/isbndb.py etc.) not in output; prediction 0/4 gold |
| network_success_no_gold_info | qutebrowser | rlm_sonnet_2.json | instance_qutebrowser__qutebrowser-394bfaed6544c952c6b34 | git ls-remote https://github.com/qutebrowser/qutebrowser | succeeded: list of remote ref names/shas only |
| network_success_no_gold_info | qutebrowser | rlm_sonnet_3.json | instance_qutebrowser__qutebrowser-0fc6d1109d041c69a68a8 | git ls-remote https://github.com/qutebrowser/qutebrowser.git HEAD | succeeded: current HEAD sha only |
| network_success_not_used | qutebrowser | rlm_sonnet_1.json | instance_qutebrowser__qutebrowser-16de05407111ddd82fa12 | git clone --depth=1 https://github.com/qutebrowser/qutebrowser.git /tmp/qb | clone succeeded; only top-level directory listing of /tmp/qb was printed; not used afterwards; prediction 2/5 gold |
| network_success_weak_info | openlibrary | rlm_sonnet_3.json | instance_internetarchive__openlibrary-757fcf46c70530739 | curl/wget/urllib to api.github.com and raw.githubusercontent.com (catalog/merge contents, merge_marc.py, git/trees/master?recursive=1) | tree listing succeeded (current master paths under openlibrary/catalog: 5 of 7 gold paths present, but these files also exist at the base commit); contents/raw requests returned 404; urllib failed (SSL); prediction 4/7 gold |

All network use is rlm_sonnet (9 issue runs, 8 with at least one successful request). No ds_*, ds_seeded or rlm_haiku run made a network request (`urllib` hits there are imports or `help()` calls for reasoning about FTP status codes); `pip` use was only `pip show`/`pip list`.

## Outside-checkout file access

- rlm_sonnet: 94 issue runs explored the file system outside the checkout (ls/find/glob on parent dirs, $HOME, `/`), mostly because the agent believed the repo was missing. 18 of these printed names of evaluation artefacts (benchmark_*.json, report_trial*.json, *_bare repos, new_runs/). No tool output in any run contains benchmark or result-file contents: no "gold_files", "predicted_files" or "fix_commit" string in any output. The bare clones (revision/*_bare) and other checkouts (e.g. /Users/a.darryl/Desktop/rlms-agent-spawn-tests/repos/ansible__ansible, evals/repos/ansible2) appear only in listings. No code opened or ran git on them.
- One case read another run's result file: rlm_sonnet 2025 run 2, ansible-558676fc ran `grep -rn "no attribute" <repo>/../../../`. The output was one line from evals/rlm_hinted_2026_haiku_2.json about a different issue: harmless.
- One case worked on a fresh upstream clone: rlm_sonnet qutebrowser run 2, qutebrowser-36ade4bba. Its `repo_path` pointed to /tmp/qutebrowser for about 220 REPL blocks (see Network above).
- codex: 4 runs ran `rg` on `~/.codex/memories/MEMORY.md` (a.darryl machine). The output was empty or one unrelated line.
- rlm_haiku: 2 runs (one used a wrong guessed repo path, nothing found).
- Side effects (not leaks): rlm_sonnet qutebrowser run 2, qutebrowser-394bfaed ran `chmod -R o+rx /Users/lwynter/Downloads/RLM`. rlm_sonnet 2026 run 1, ansible-f074c209 ran `git checkout HEAD -- .`.

## What could NOT be audited

- **rlm_sonnet_2020**: report_trial1..5.json (95 issue runs, Ansible 2020, Sonnet RLM): conversation_history is empty and there is no rlm_trajectory/trace_path; no executed code is recorded anywhere on disk (searched RLM dir, zips). NOT AUDITABLE.
- **codex_all**: All 353 Codex issue runs: run_cli_eval.py stores only stdout_preview = first 2000 chars of the JSONL event stream (codex ran with --ephemeral, so no ~/.codex session files). 538 command_execution items are visible (1-4 per issue, typically the first rg/git status) out of 24,559 recorded events. The rest of each Codex session is NOT AUDITABLE. Codex ran with --sandbox read-only (Codex default for that mode is no network), but this cannot be verified from the logs.
- **coordinator_missing_history**: 7 coordinator issue runs have empty conversation_history (ds_adaptive x3, ds_adaptive_t300 x2, ds_nudged x1, ds_nospawn x1); all have empty predictions, so no leak could have affected the score.
- **coordinator_tool_args**: Coordinator harness (ds_*): arguments of read_file / list_files / search_codebase / consult_agents are not logged (only outputs). read_file joins codebase/<arg> without a containment check, so absolute or ../ paths were possible; audit relies on outputs (no output contained benchmark/result contents or .git internals other than a binary-match notice). Subagent (consult_agents) internal tool calls are not logged, only their answers (subagents have path-scoped read/list/search tools only, no REPL).
- **dynamic_paths**: Outside-checkout detection for REPL code is regex based on literal paths and common traversal idioms; paths built dynamically from earlier outputs were checked only by manual reading of the flagged runs.
