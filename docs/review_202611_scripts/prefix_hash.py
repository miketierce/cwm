import hashlib, json
p='/Users/Mike/Code/wcfoma/docs/lab_diary_20261029.md'
data=open(p,'rb').read()
lines=data.split(b'\n')
targets={}
for folder in ('ringdown_20261029','nullring_20261029','termination_20261029'):
    for line in open(f'/Users/Mike/Code/wcfoma/data/results/k_eff/{folder}/log.jsonl'):
        d=json.loads(line)
        if d.get('event','').startswith('prereg') or d.get('event')=='confirm_prereg' or 'sha256' in d and isinstance(d['sha256'],dict):
            h=d['sha256'].get('docs/lab_diary_20261029.md') if isinstance(d.get('sha256'),dict) else None
            if h: targets[(folder,d.get('event'),d.get('time'))]=h
print(len(targets),'logged diary hashes')
found={}
acc=b''
for i,l in enumerate(lines):
    for cand in (acc+l, acc+l+b'\n'):
        hh=hashlib.sha256(cand).hexdigest()
        for k,v in targets.items():
            if v==hh: found[k]=(i+1, cand.endswith(b'\n'))
    acc+=l+b'\n'
for k,v in targets.items():
    print(k, v[:16], '-> matches prefix ending at line', found.get(k))
