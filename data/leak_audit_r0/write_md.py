import json,collections
a=json.load(open('audit.json')); S=a['per_method']; F=a['flagged']
order=['rlm_haiku','rlm_sonnet','ds_nospawn','ds_adaptive','ds_adaptive_t300','ds_nudged','ds_seeded','codex']
cols=[('issue_runs','issue runs'),('with_full_trace','with code trace'),('git_any','any git'),('git_head_only','git HEAD-only'),('git_history_cmd','git history cmd'),
('git_beyond_base_attempt','beyond-base git attempt'),('git_future_commits_in_output','post-base commits in output'),('fix_commit_seen','fix commit/backport seen'),
('fix_commit_files_seen','fix-commit files seen'),('network_attempt','network attempt'),('network_success','network success'),('outside_attempt','outside-checkout access (heuristic)')]
L=[]
L.append('# Leakage audit of agent tool logs (git history, network, outside-checkout files)\n')
L.append('Scope: every agentic issue run used in the paper (runs.json: rlm_haiku, rlm_sonnet, ds_nospawn, ds_adaptive, ds_adaptive_t300, ds_nudged, codex) plus all revision/seed_ablation/*/ds_seeded_*.json. One "issue run" = one issue in one run file. Post-base commits were identified by resolving every SHA printed by git against full clones (ansible/ansible fetched to the scratchpad; local openlibrary and qutebrowser clones) and checking ancestry of and date relative to the base commit.\n')
L.append('## Counts per method (issue runs)\n')
L.append('| method | '+' | '.join(c[1] for c in cols)+' |'); L.append('|'+'---|'*(len(cols)+1))
for m in order:
    s=S[m]; L.append(f'| {m} | '+' | '.join(str(s.get(k,0)) for k,_ in cols)+' |')
L.append('\nNotes: codex has no full trace (only the first 2000 chars of the event stream, 538 visible commands, all `rg`/`git status --short`/reads of `~/.codex/memories/MEMORY.md`). rlm_sonnet 2020 (95 issue runs) has no trace at all. Outside-checkout counts for ds_* are almost entirely scratch files in /tmp, guessed non-existent paths (/tmp/ansible, /tmp/codebase) or `cwd=/tmp`; manual review found no ds_* run that read anything outside the checkout that was relevant to the issue or the gold answer.\n')
strong=[d for d in F if d['classification'] in ('POTENTIAL_LEAK_LIKELY_USED','POTENTIAL_LEAK_USE_UNCERTAIN','FIX_SEEN_NOT_USED') and d['category'] in ('git_history','network')]
L.append(f'## Potential leaks where the fix itself was observed ({len(strong)} issue runs)\n')
L.append('| class | method | window | run file | instance | gold∩pred | evidence |'); L.append('|---|---|---|---|---|---|---|')
for d in strong:
    L.append(f"| {d['classification']} | {d['method']} | {d['window']} | {d['run_file'].split('/')[-1]} | {d['instance_id'][:60]} | {len(d.get('pred_gold_overlap',[]))}/{len(d.get('gold',[]))} | {d['evidence'].replace('|','/')} |")
c=collections.Counter((d['method'],d['window']) for d in strong if d['classification']!='FIX_SEEN_NOT_USED')
L.append('\nLikely-used or uncertain, by method/window: '+', '.join(f'{m} {w}: {n}' for (m,w),n in sorted(c.items()))+'.\n')
weak=[d for d in F if d['classification']=='POTENTIAL_LEAK_WEAK_FIX_TITLE_ONLY']
L.append(f'## Weak exposure: only the one-line subject of the fix commit (or its backport) was printed ({len(weak)} issue runs)\n')
L.append('These come from `git log --all --oneline --grep=...` outputs. No file list or diff of the fix was printed. The subject can still hint at the change (e.g. rlm_sonnet 2025 run 1, ansible-4c04b8c7: subject "IncludedFile: store _from args..." → gold file playbook/included_file.py, which was predicted).\n')
L.append('| method | window | run file | instance | gold∩pred |'); L.append('|---|---|---|---|---|')
for d in weak: L.append(f"| {d['method']} | {d['window']} | {d['run_file'].split('/')[-1]} | {d['instance_id'][:60]} | {len(d['pred_gold_overlap'])}/{len(d['gold'])} |")
fut=[d for d in F if d['classification'] in ('FUTURE_HISTORY_REACHED_FIX_NOT_SEEN','BEYOND_BASE_ATTEMPT_NO_FUTURE_COMMITS_IN_OUTPUT')]
cc=collections.Counter((d['method'],d['classification']) for d in fut)
L.append(f'\n## Post-base history reached, fix not observed ({len(fut)} issue runs)\n')
L.append('; '.join(f'{m}: {n} ({cl})' for (m,cl),n in sorted(cc.items()))+'. Full list in audit.json (category git_history).\n')
L.append('## Network\n')
L.append('| class | window | run file | instance | command | evidence |'); L.append('|---|---|---|---|---|---|')
for d in F:
    if d['category']=='network': L.append(f"| {d['classification']} | {d['window']} | {d['run_file'].split('/')[-1]} | {d['instance_id'][:55]} | {d['command']} | {d['evidence'].replace('|','/')} |")
L.append('\nAll network use is rlm_sonnet (9 issue runs, 8 with at least one successful request). No ds_*, ds_seeded or rlm_haiku run made a network request (`urllib` hits there are imports or `help()` calls for reasoning about FTP status codes); `pip` use was only `pip show`/`pip list`.\n')
L.append('## Outside-checkout file access\n')
L.append('- rlm_sonnet: 94 issue runs explored the file system outside the checkout (ls/find/glob on parent dirs, $HOME, `/`), mostly because the agent believed the repo was missing. 18 of these printed names of evaluation artefacts (benchmark_*.json, report_trial*.json, *_bare repos, new_runs/). No tool output in any run contains benchmark or result-file contents: no "gold_files", "predicted_files" or "fix_commit" string in any output. The bare clones (revision/*_bare) and other checkouts (e.g. /Users/a.darryl/Desktop/rlms-agent-spawn-tests/repos/ansible__ansible, evals/repos/ansible2) appear only in listings. No code opened or ran git on them.')
L.append('- One case read another run\'s result file: rlm_sonnet 2025 run 2, ansible-558676fc ran `grep -rn "no attribute" <repo>/../../../`. The output was one line from evals/rlm_hinted_2026_haiku_2.json about a different issue: harmless.')
L.append('- One case worked on a fresh upstream clone: rlm_sonnet qutebrowser run 2, qutebrowser-36ade4bba. Its `repo_path` pointed to /tmp/qutebrowser for about 220 REPL blocks (see Network above).')
L.append('- codex: 4 runs ran `rg` on `~/.codex/memories/MEMORY.md` (a.darryl machine). The output was empty or one unrelated line.')
L.append('- rlm_haiku: 2 runs (one used a wrong guessed repo path, nothing found).')
L.append('- Side effects (not leaks): rlm_sonnet qutebrowser run 2, qutebrowser-394bfaed ran `chmod -R o+rx /Users/lwynter/Downloads/RLM`. rlm_sonnet 2026 run 1, ansible-f074c209 ran `git checkout HEAD -- .`.\n')
L.append('## What could NOT be audited\n')
for k,v in a['not_auditable'].items(): L.append(f'- **{k}**: {v}')
open('audit.md','w').write('\n'.join(L)+'\n')
print(len(L))
