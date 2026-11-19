import pickle,re,collections,json
exec(open('final.py').read().split('# per method stats')[0])   # recompute per, NET, outside flags
stats=json.load(open('stats.json'))
fixlinks=collections.defaultdict(list)
for x in rows:
    if x['ui'] in per and 'n_git' in per[x['ui']]: fixlinks[x['ui']].append(x)
MANUAL={ # (file suffix, iid prefix) -> (classification, note)
('no_agents_2025_haiku_1.json','instance_ansible__ansible-649c9ec4'):('POTENTIAL_LEAK_LIKELY_USED','git log --all --grep=EncryptedString found fix 649c9ec443 and its stable backport ebae950db2; agent ran git show --name-status ebae950db2 (lists all 4 gold files) and git show ebae950db2 -- <each file>; prediction contains all 4 gold files plus the 3 test files touched by the backport'),
('ansible_2026/ds_nospawn_3.json','instance_ansible__ansible-36e9711c'):('POTENTIAL_LEAK_LIKELY_USED','git log --all --grep=deepcopy found fix 36e9711c26; agent ran git show 36e9711c26 --stat and full diff; prediction contains the gold file; rationale mirrors the diff (__deepcopy__ returning self)'),
('rlm_hinted_2025_sonnet_1.json','instance_ansible__ansible-558676fc'):('FIX_SEEN_NOT_USED','agent ran git show 558676fcdc --stat/--name-only/diff (both gold files listed) but concluded HEAD commit 3518d48146 was the fix; prediction contains 0/2 gold files'),
('rlm_hinted_2025_sonnet_2.json','instance_ansible__ansible-532edf4c'):('POTENTIAL_LEAK_LIKELY_USED','git log --all --grep tag found fix 532edf4c35 and backport 33c55b9c25; repeated git show --stat/--name-only/diff; agent comment: "These are the commits that FIX the bug"; prediction contains the gold file'),
('rlm_hinted_2025_sonnet_3.json','instance_ansible__ansible-532edf4c'):('POTENTIAL_LEAK_LIKELY_USED','git show --stat/--name-only/diff-tree of backport 33c55b9c25 (cherry-pick of fix); prediction contains the gold file'),
('rlm_hinted_2026_sonnet_1.json','instance_ansible__ansible-36e9711c'):('POTENTIAL_LEAK_LIKELY_USED','git show 36e9711c26 --stat/--name-status/diff-tree and backport 82d13085a2; scored prediction contains the gold file'),
('rlm_hinted_2026_sonnet_1.json','instance_ansible__ansible-51d5a456'):('POTENTIAL_LEAK_LIKELY_USED','agent: "Let me look at the commit that supposedly fixed this bug"; git show 51d5a456ef --stat/--name-only/diff lists all 3 gold files; prediction contains 2/3'),
('rlm_hinted_2026_sonnet_1.json','instance_ansible__ansible-90595736'):('POTENTIAL_LEAK_LIKELY_USED','git show --name-only/--stat/diff 90595736ed (both gold files); prediction contains 1/2'),
('rlm_hinted_2026_sonnet_1.json','instance_ansible__ansible-a51536f3'):('POTENTIAL_LEAK_LIKELY_USED','agent: "Great! There\'s a commit \'Fix using the server\'s validate_certs config...\' Let\'s look at what this commit changed" then "Perfect! Now I can see the files that need to be modified"; prediction contains 3/3 gold'),
('rlm_hinted_2026_sonnet_1.json','instance_ansible__ansible-d9deb945'):('POTENTIAL_LEAK_LIKELY_USED','git show d9deb945b0 --stat/diff and backport c83999378d; prediction contains the gold file'),
('rlm_hinted_2026_sonnet_1.json','instance_ansible__ansible-f2357cdc'):('POTENTIAL_LEAK_LIKELY_USED','agent: "f2357cdc53 is the fix commit!"; git show --stat/diff/<sha>:<path> of the fix; prediction contains the gold file'),
('rlm_hinted_2026_sonnet_2.json','instance_ansible__ansible-3adecacc'):('POTENTIAL_LEAK_LIKELY_USED','agent final text: "The fix commit 3adecacccf ... was the actual fix, and I traced which files it changed"; prediction contains 5/5 gold'),
('rlm_hinted_2026_sonnet_2.json','instance_ansible__ansible-90595736'):('POTENTIAL_LEAK_LIKELY_USED','git log --all -p and git show 90595736ed (full sha); final text: "confirmed by finding the exact fix commit 90595736ed..."; prediction contains 1/2'),
('rlm_hinted_2026_sonnet_3.json','instance_ansible__ansible-36e9711c'):('POTENTIAL_LEAK_LIKELY_USED','many git show/diff-tree calls on 36e9711c26 and backport 82d13085a2; scored prediction contains the gold file'),
('rlm_hinted_2026_sonnet_3.json','instance_ansible__ansible-3adecacc'):('POTENTIAL_LEAK_LIKELY_USED','git show/diff-tree/diff 3adecacccf^..3adecacccf (all 5 gold files listed); prediction contains 2/5'),
('rlm_hinted_2026_sonnet_3.json','instance_ansible__ansible-90595736'):('POTENTIAL_LEAK_LIKELY_USED','git log -p --all --grep=86473 and git show 90595736ed --stat/diff; prediction contains 1/2'),
('rlm_hinted_2026_sonnet_3.json','instance_ansible__ansible-cb535cf3'):('POTENTIAL_LEAK_LIKELY_USED','git show cb535cf3d3 --stat/--name-only/diff; prediction contains the gold file'),
('openlibrary/rlm_sonnet_1.json','instance_internetarchive__openlibrary-3f7db6bb'):('FIX_SEEN_NOT_USED','git log --all --name-status output included fix 3f7db6bbbc with its 3 gold files; prediction contains 0/3 gold files (invented openlibrary/catalog/isbndb/*)'),
('openlibrary/rlm_sonnet_2.json','instance_internetarchive__openlibrary-30bc73a1'):('POTENTIAL_LEAK_LIKELY_USED','git log --all (with file names) showed fix 30bc73a13 "Supercharges cover archival with zip batch processing" touching archive.py/README.md/test_archive.py; agent comment lists this commit; prediction contains 5/5 gold'),
('qutebrowser/rlm_sonnet_2.json','instance_qutebrowser__qutebrowser-96b99780'):('POTENTIAL_LEAK_LIKELY_USED','git log --all -p -S parse_duration showed the fix diff (utils.py, utilcmds.py); prediction contains 2/3 gold (utils.py, test_utils.py)'),
('qutebrowser/rlm_sonnet_3.json','instance_qutebrowser__qutebrowser-f631cd44'):('POTENTIAL_LEAK_USE_UNCERTAIN','git show f631cd442 --stat/diff lists all 6 gold files; the agent had enumerated the same 7 candidate files in its comments just before ("Let me verify these files exist and check the git log"), so the output at least confirmed its list; prediction contains 6/6 gold'),
}
def manual(p):
    for (f,i),v in MANUAL.items():
        if p['file'].endswith(f) and p['iid'].startswith(i): return v
    return None
flagged=[]
def cmds(ui,only_fix=False,maxn=6):
    out=[]
    for x in fixlinks[ui]:
        if only_fix and not (x['fix_in_out'] or x['fix_subject_in_out'] or x['fix_in_code'] or x['future_shas']): continue
        for l in gitlines(x['code']):
            l=l.strip().replace(units[ui]['repo'] or '\0','<REPO>')
            if l not in out: out.append(l[:220])
        if len(out)>=maxn: break
    return out[:maxn]
for ui,p in per.items():
    if 'n_git' not in p: continue
    u=units[ui]
    base=dict(method=p['method'],window=p['window'],run_file=p['file'],instance_id=p['iid'],gold=p['gold'],prediction=p['pred'],
              pred_gold_overlap=sorted(set(p['pred'])&set(p['gold'])))
    if p['leaked_gold']:
        m=manual(p); assert m, p['iid']
        flagged.append(dict(base,category='git_history',command=cmds(ui,True),classification=m[0],
            evidence=m[1],fix_commit_and_backports_seen=p['fixshas'],gold_files_seen_in_fix_commit_output=p['leaked_gold'],prediction_contains_seen_files=p['pred_hits_leaked']))
    elif p['fix_seen_strict']:
        flagged.append(dict(base,category='git_history',command=cmds(ui,True),classification='POTENTIAL_LEAK_WEAK_FIX_TITLE_ONLY',
            evidence=f"git log --all/--grep output contained the fix commit (or its backport) one-line subject: {p['fix_subject']!r}; no file list or diff of the fix commit was printed"+(" ; agent then ran git log --grep on the fix PR number" if p['fix_ref_in_code'] else ''),
            fix_commit_and_backports_seen=p['fixshas']))
    elif p['future_out'] or p['beyond_attempt']:
        flagged.append(dict(base,category='git_history',command=cmds(ui,True,3),classification='FUTURE_HISTORY_REACHED_FIX_NOT_SEEN' if p['future_out'] else 'BEYOND_BASE_ATTEMPT_NO_FUTURE_COMMITS_IN_OUTPUT',
            evidence='git log --all / other refs listed commits after the base commit, but neither the fix commit nor a backport of it appears in any output' if p['future_out'] else 'command referenced --all/tags/other refs but no post-base commit appeared in output'))
for ui,u in enumerate(units):
    nk=netkey(u)
    if nk:
        flagged.append(dict(method=u['method'],window=u['window'],run_file=u['file'],instance_id=u['iid'],category='network',command=nk[0],classification=nk[2],evidence=nk[1],
            gold=u['gold'],prediction=u['pred'],pred_gold_overlap=sorted(set(u['pred'])&set(u['gold']))))
OTHER=[
 ('rlm_sonnet','2025','rlm_sonnet_25_26/rlm_hinted_2025_sonnet_2.json','instance_ansible__ansible-558676fc','outside_checkout',"grep -rn 'no attribute' <repo>/../../../ (= /Users/a.darryl/Desktop/swe-agent-spawning/)",'HARMLESS_NO_GOLD_INFO','output (truncated to 2000 chars) was one match inside another run\'s result file evals/rlm_hinted_2026_haiku_2.json (a transcript line for a different issue); no gold_files/fix info; prediction 0/2 gold'),
 ('rlm_sonnet','qutebrowser','revision/new_runs/qutebrowser/rlm_sonnet_2.json','instance_qutebrowser__qutebrowser-36ade4bba','outside_checkout','repo_path = "/tmp/qutebrowser" (fresh clone of upstream HEAD) then grep/open on it','POTENTIAL_LEAK_LIKELY_USED','see network entry: agent explored the post-fix upstream tree instead of the base checkout'),
 ('rlm_sonnet','qutebrowser','revision/new_runs/qutebrowser/rlm_sonnet_2.json','instance_qutebrowser__qutebrowser-394bfaed','side_effect',"subprocess.run(['chmod','-R','o+rx','/Users/lwynter/Downloads/RLM'])",'SIDE_EFFECT_NOT_A_LEAK','agent changed permissions recursively on the whole project directory (rc=0); not an information leak but a write outside the checkout'),
 ('rlm_sonnet','2026','rlm_sonnet_25_26/rlm_hinted_2026_sonnet_1.json','instance_ansible__ansible-f074c209','side_effect',"git -C <repo> checkout HEAD -- .",'SIDE_EFFECT_NOT_A_LEAK','restores the working tree to HEAD (= base commit); no history access'),
]
for m,w,f,i,cat,cmd,cl,ev in OTHER:
    u=[u for u in units if u['method']==m and u['file']==f and u['iid'].startswith(i)][0]
    flagged.append(dict(method=m,window=w,run_file=f,instance_id=u['iid'],category=cat,command=cmd,classification=cl,evidence=ev,gold=u['gold'],prediction=u['pred']))
# codex memory reads
for u in units:
    if u['method']!='codex': continue
    for kd,c,o in u['items']:
        if kd=='cmd' and 'MEMORY.md' in c:
            outs=[oo for kk,cc,oo in u['items'] if kk=='cmd_out' and cc==c]
            flagged.append(dict(method='codex',window=u['window'],run_file=u['file'],instance_id=u['iid'],category='outside_checkout',command=c,
              classification='HARMLESS_NO_GOLD_INFO',evidence='Codex read its own memory file outside the checkout; output was '+('empty' if not (outs and outs[0].strip()) else 'one unrelated line from another project: '+outs[0][:160])))
# runs listing eval artefact names
for ui,u in enumerate(units):
    if u.get('outside_evalnames'):
        flagged.append(dict(method=u['method'],window=u['window'],run_file=u['file'],instance_id=u['iid'],category='outside_checkout',
          command='filesystem exploration outside the checkout (ls/listdir/glob/find on parent dirs, $HOME, /)',classification='OUTSIDE_LISTING_ONLY_NO_GOLD_CONTENT',
          evidence='directory listings outside the checkout printed names of evaluation artefacts (e.g. benchmark_*.json, report_trial*.json, *_bare, new_runs/ result files); no output in any run contains benchmark/result-file contents (no "gold_files", "predicted_files", "fix_commit" strings in any tool output)'))
flagged.sort(key=lambda d:(d['category'],d['classification'],d['method'],d['window'],d['run_file'],d['instance_id']))
NOTAUD={
 'rlm_sonnet_2020': 'report_trial1..5.json (95 issue runs, Ansible 2020, Sonnet RLM): conversation_history is empty and there is no rlm_trajectory/trace_path; no executed code is recorded anywhere on disk (searched RLM dir, zips). NOT AUDITABLE.',
 'codex_all': 'All 353 Codex issue runs: run_cli_eval.py stores only stdout_preview = first 2000 chars of the JSONL event stream (codex ran with --ephemeral, so no ~/.codex session files). 538 command_execution items are visible (1-4 per issue, typically the first rg/git status) out of 24,559 recorded events. The rest of each Codex session is NOT AUDITABLE. Codex ran with --sandbox read-only (Codex default for that mode is no network), but this cannot be verified from the logs.',
 'coordinator_missing_history': '7 coordinator issue runs have empty conversation_history (ds_adaptive x3, ds_adaptive_t300 x2, ds_nudged x1, ds_nospawn x1); all have empty predictions, so no leak could have affected the score.',
 'coordinator_tool_args': 'Coordinator harness (ds_*): arguments of read_file / list_files / search_codebase / consult_agents are not logged (only outputs). read_file joins codebase/<arg> without a containment check, so absolute or ../ paths were possible; audit relies on outputs (no output contained benchmark/result contents or .git internals other than a binary-match notice). Subagent (consult_agents) internal tool calls are not logged, only their answers (subagents have path-scoped read/list/search tools only, no REPL).',
 'dynamic_paths': 'Outside-checkout detection for REPL code is regex based on literal paths and common traversal idioms; paths built dynamically from earlier outputs were checked only by manual reading of the flagged runs.',
}
audit=dict(scope='Agentic issue runs used in the paper (runs.json methods rlm_haiku, rlm_sonnet, ds_nospawn, ds_adaptive, ds_adaptive_t300, ds_nudged, codex; plus revision/seed_ablation/*/ds_seeded_*.json)',
  definitions={'git_any':'issue runs that executed >=1 git command','git_head_only':'only status/ls-files/grep/rev-parse/remote/config at HEAD','git_history_cmd':'executed log/show/diff/blame/etc. (incl. HEAD ancestry only)',
   'git_beyond_base_attempt':'used --all/--tags/origin/*/ls-remote/fetch or a post-base SHA in a git command','git_future_commits_in_output':'some git output contained a commit that is not an ancestor of the base commit and is newer than it (verified against full clones)',
   'fix_commit_seen':'the fixing commit SHA or a cherry-pick/backport of it appeared in a git output','fix_commit_files_seen':'a git output listed gold files as changed by the fixing commit/backport (show --stat/--name-only/diff/log -p)',
   'network_attempt':'executed curl/wget/urllib/git clone/ls-remote against the internet (manually verified)','outside_attempt':'heuristic: executed code referencing paths outside the checkout'},
  per_method=stats, flagged=flagged, not_auditable=NOTAUD)
json.dump(audit,open('audit.json','w'),indent=1)
print(collections.Counter((d['category'],d['classification'],d['method']) for d in flagged))
