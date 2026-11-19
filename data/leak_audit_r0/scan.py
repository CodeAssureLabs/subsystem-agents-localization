import pickle,json,re,collections
units=pickle.load(open('units.pkl','rb'))
GIT=re.compile(r"""(?<![\w./-])git(?![\w-])""")
NET=re.compile(r"""\bcurl\b|\bwget\b|import\s+requests|\brequests\.(get|post|Session)|urllib|http\.client|\bsocket\b|(?<![\w/.-])gh\s+(api|pr|issue|repo)|pip3?\s+install|\buv\s+(pip|add)|github\.com|githubusercontent|https?://|\bhttpx\b|aiohttp|webbrowser""")
OUTS=re.compile(r"""\.\./|os\.path\.dirname\(\s*repo|Path\(repo_path\)\.parent|\.parent\b|expanduser|Path\.home|~/|/Users/|/private/|/tmp\b|/var/|/etc/|/opt/|/home/|benchmark|report[^\s'"]*\.json|\bgold|new_runs|seed_ablation|Downloads/RLM|\.git/|\.git['"]|chdir\(\s*['"]/|os\.walk\(\s*['"]/|glob\(\s*['"]/|listdir\(\s*['"]/|['"]/['"]|__file__|sys\.path|os\.environ""")
def strip_repo(s, repo):
    if repo:
        s = s.replace(repo, '<REPO>')
    return s
hits=[]
for ui,u in enumerate(units):
    for k,(kind,code,out) in enumerate(u['items']):
        if kind not in ('code','cmd','cmd_out','codex_partial'): continue
        if kind=='cmd_out': continue  # commands already counted from item.started; output inspected separately
        c=strip_repo(code,u['repo'])
        for cat,rx in (('git',GIT),('net',NET),('outside',OUTS)):
            for mt in rx.finditer(c):
                a=max(0,mt.start()-150); b=min(len(c),mt.end()+150)
                hits.append(dict(ui=ui,k=k,cat=cat,kind=kind,match=mt.group(0),ctx=c[a:b]))
pickle.dump(hits,open('hits.pkl','wb'))
print(collections.Counter((h['cat'],units[h['ui']]['method']) for h in hits))
print(collections.Counter((h['cat'],h['match']) for h in hits).most_common(80))
