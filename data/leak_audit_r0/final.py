import pickle,re,collections,json
units=pickle.load(open('units.pkl','rb')); rows=pickle.load(open('gitrows3.pkl','rb')); per=pickle.load(open('perrun.pkl','rb'))
def core(s):
    s=re.sub(r'^\[[^\]]*\]\s*','',s); s=re.sub(r'(\s*\(#\d+\))+\s*$','',s); return s.strip()
by=collections.defaultdict(list)
for x in rows: by[x['ui']].append(x)
HEADONLY={'status','ls-files','grep','rev-parse','config','sparse-checkout','version','check-ignore','ls-tree','cat-file','describe','branch','remote','worktree','symbolic-ref'}
HIST=re.compile(r"""['"\s](log|show|diff|blame|rev-list|reflog|diff-tree|whatchanged|shortlog|annotate|bisect|archive|for-each-ref|show-ref|name-rev|merge-base|stash|tag|fetch|pull|clone|ls-remote|checkout|switch|restore)['"\s,]""")
EXECGIT=re.compile(r"""['"]git['"]|['"]git\s|f['"]git\s|^\s*/bin/zsh -lc ['"]?git|^\s*git\s|&&\s*git\s""")
def gitlines(code): return [l for l in code.split('\n') if re.search(r"\bgit\b",l) and not l.strip().startswith('#')]
# strict fix exposure
for ui in list(by):
    if not any(EXECGIT.search(l) for x in by[ui] for l in gitlines(x['code'])):
        del by[ui]; per.pop(ui,None)
for ui,rs in by.items():
    p=per[ui]; fsha=rs[0]['fix_sha']; fsub=rs[0]['fix_subject'] or ''; fc=core(fsub)
    bps={fsha[:10]}
    for x in rs:
        for tok,full,s in x['future_shas']:
            if fc and core(s)==fc and not s.startswith('Merge'): bps.add(full[:10])
    p['fix_seen_strict']=any(any(b[:7] in x['out'] for b in bps) for x in rs)
    p['backports']=sorted(bps-{fsha[:10]})
    p['hist_any']=any(HIST.search(' '+'\n'.join(gitlines(x['code']))+' ') for x in rs)
    p['beyond_attempt']=any([r for r in x['refs_in_git_lines'] if r!='checkout'] or x['future_sha_in_code'] for x in rs)
    p['future_out']=any(x['future_shas'] for x in rs)
# network (manually verified list)
NET={('rlm_sonnet','rlm_sonnet_25_26/rlm_hinted_2025_sonnet_1.json','instance_ansible__ansible-11f5563895'):('curl raw.githubusercontent.com/ansible/ansible/devel/lib/ansible/template/__init__.py','succeeded: first 50 lines (imports) of current devel template/__init__.py; not a gold file; prediction not derived from it','network_success_no_gold_info'),
('rlm_sonnet','rlm_sonnet_25_26/rlm_hinted_2025_sonnet_2.json','instance_ansible__ansible-11f5563895'):('curl raw.githubusercontent.com/ansible/ansible/devel/lib/ansible/template/__init__.py; git ls-remote https://github.com/ansible/ansible HEAD','both succeeded: 50 lines of imports of devel template/__init__.py (not a gold file) and the current HEAD sha; prediction (template/__init__.py, test_templar.py) has 0 gold files','network_success_no_gold_info'),
('rlm_sonnet','revision/new_runs/openlibrary/rlm_sonnet_2.json','instance_internetarchive__openlibrary-8a9d9d323d'):('curl api.github.com/.../contents/scripts; curl api.github.com/.../git/trees/master?recursive=1 (head -100); curl httpbin.org/ip; git ls-remote','succeeded: names of current master scripts/ directory entries and first entries of master tree; gold files (scripts/providers/isbndb.py etc.) not in output; prediction 0/4 gold','network_success_no_gold_info'),
('rlm_sonnet','revision/new_runs/openlibrary/rlm_sonnet_3.json','instance_internetarchive__openlibrary-757fcf46c7'):('curl/wget/urllib to api.github.com and raw.githubusercontent.com (catalog/merge contents, merge_marc.py, git/trees/master?recursive=1)','tree listing succeeded (current master paths under openlibrary/catalog: 5 of 7 gold paths present, but these files also exist at the base commit); contents/raw requests returned 404; urllib failed (SSL); prediction 4/7 gold','network_success_weak_info'),
('rlm_sonnet','revision/new_runs/qutebrowser/rlm_sonnet_1.json','instance_qutebrowser__qutebrowser-16de054071'):('git clone --depth=1 https://github.com/qutebrowser/qutebrowser.git /tmp/qb','clone succeeded; only top-level directory listing of /tmp/qb was printed; not used afterwards; prediction 2/5 gold','network_success_not_used'),
('rlm_sonnet','revision/new_runs/qutebrowser/rlm_sonnet_2.json','instance_qutebrowser__qutebrowser-36ade4bba5'):('git clone --depth=1 https://github.com/qutebrowser/qutebrowser /tmp/qutebrowser; then repo_path = "/tmp/qutebrowser"','clone of CURRENT upstream (post-fix) succeeded; agent reassigned repo_path to the clone at block 49 and explored it for ~220 blocks (grep/open of qutebrowser/config/qtargs.py and tests/unit/config/test_qtargs.py, which in the clone already contain _DISABLE_FEATURES/--disable-features handling); it only switched back to the base checkout at block 270; final rationale describes adding `_DISABLE_FEATURES = "--disable-features="` exactly as in upstream; prediction = gold (2/2)','POTENTIAL_LEAK_LIKELY_USED'),
('rlm_sonnet','revision/new_runs/qutebrowser/rlm_sonnet_2.json','instance_qutebrowser__qutebrowser-394bfaed65'):('git ls-remote https://github.com/qutebrowser/qutebrowser','succeeded: list of remote ref names/shas only','network_success_no_gold_info'),
('rlm_sonnet','revision/new_runs/qutebrowser/rlm_sonnet_2.json','instance_qutebrowser__qutebrowser-c09e1439f1'):('urllib.request.urlopen(api.github.com/repos/qutebrowser/qutebrowser/git/trees/main?recursive=1)','failed (SSL CERTIFICATE_VERIFY_FAILED)','network_attempt_failed'),
('rlm_sonnet','revision/new_runs/qutebrowser/rlm_sonnet_3.json','instance_qutebrowser__qutebrowser-0fc6d1109d'):('git ls-remote https://github.com/qutebrowser/qutebrowser.git HEAD','succeeded: current HEAD sha only','network_success_no_gold_info')}
def netkey(u):
    for (m,f,i),v in NET.items():
        if u['method']==m and u['file']==f and u['iid'].startswith(i): return v
# outside access heuristic
ROOTS=r"(?:/Users|/private|/tmp|/opt|/home|/var|/Library|/System|/root|/proc|~)"
OUTL=re.compile(r"""(['"])"""+ROOTS+r"""[^'"\n]*\1|listdir\(\s*['"]/['"]\)|['"]ls['"],\s*(['"]-\w+['"],\s*)?['"]/['"]|os\.walk\(\s*['"]/['"]|find\s+/|['"]find['"],\s*['"]/|dirname\(\s*(os\.path\.abspath\()?repo_path|Path\(repo_path\)\.parent|expanduser|Path\.home\(\)|\.\./""")
CALL=re.compile(r"subprocess|open\(|listdir|glob|walk|scandir|exists|isdir|Path\(|=\s*['\"]/|sys\.path|ls |find |cat ")
EVAL=re.compile(r"benchmark_\w+\.json|report_trial|rlm_hinted_|agents_20\d\d|no_agents_|_bare\b|new_runs|relevant_traces|plain_llm_")
IGN=re.compile(r"/opt/CA/|/path/to|/home/user/\.ansible|/type/list|/lists/add|/an/absolute/path|/dev/null|/bin/(sh|bash|zsh)|/usr/bin/env")
for ui,u in enumerate(units):
    if u['method']=='codex': continue
    att=False; content=False; evalnames=False
    for kd,code,out in u['items']:
        if kd!='code': continue
        c=code.replace(u['repo'] or '\0','<REPO>')
        for l in c.split('\n'):
            s=l.strip()
            if s.startswith('#') or IGN.search(s): continue
            if OUTL.search(s) and CALL.search(s) and not s.startswith('print('):
                att=True
                o=(out or '').replace(u['repo'] or '\0','<REPO>')
                if o.strip() and not re.search(r'No such file|Traceback|TimeoutExpired|Permission denied|does not exist|False\s*$',o[:300]): content=True
                if EVAL.search(o): evalnames=True
                break
    per.setdefault(ui,{})
    u['outside_attempt']=att; u['outside_content']=content; u['outside_evalnames']=evalnames
pickle.dump(per,open('perrun2.pkl','wb')); pickle.dump([(u.get('outside_attempt'),u.get('outside_content'),u.get('outside_evalnames')) for u in units],open('outside_flags.pkl','wb'))
# per method stats
M=collections.OrderedDict()
order=['rlm_haiku','rlm_sonnet','ds_nospawn','ds_adaptive','ds_adaptive_t300','ds_nudged','ds_seeded','codex']
for m in order: M[m]=collections.Counter()
for ui,u in enumerate(units):
    m=u['method']; c=M[m]; c['issue_runs']+=1
    has_trace = not any(n.startswith('no ') for n in u['notes'])
    if m=='codex': has_trace=False
    c['with_full_trace']+=has_trace
    if m=='codex':
        c['codex_partial_trace']+=1
        c['codex_visible_commands']+=u.get('codex_cmds_visible',0)
    p=per.get(ui)
    if p and 'n_git' in p:
        c['git_any']+=1
        if p['hist_any']: c['git_history_cmd']+=1
        else: c['git_head_only']+=1
        if p['beyond_attempt']: c['git_beyond_base_attempt']+=1
        if p['future_out']: c['git_future_commits_in_output']+=1
        if p['fix_seen_strict']: c['fix_commit_seen']+=1
        if p['leaked_gold']: c['fix_commit_files_seen']+=1
        if p['pred_hits_leaked']: c['pred_contains_seen_fix_files']+=1
    nk=netkey(u)
    if nk:
        c['network_attempt']+=1
        if nk[2]!='network_attempt_failed': c['network_success']+=1
    if u.get('outside_attempt'): c['outside_attempt']+=1
    if u.get('outside_content'): c['outside_content_returned']+=1
    if u.get('outside_evalnames'): c['outside_eval_artifact_names_listed']+=1
for m in order: print(m,dict(M[m]))
json.dump({m:dict(v) for m,v in M.items()},open('stats.json','w'),indent=1)
