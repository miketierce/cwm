import csv, numpy as np, collections
def load(sess):
    H=collections.defaultdict(list)
    with open(f'/Users/Mike/Code/wcfoma/data/results/k_eff/{sess}/trials.csv') as fh:
        for r in csv.DictReader(fh):
            if r['state']!='GLASS': continue
            if int(r['ovf_A']) or int(r['ovf_B']) or int(r['clip_A']) or int(r['clip_B']): continue
            zA=complex(float(r['zA_re_mV']),float(r['zA_im_mV'])); zB=complex(float(r['zB_re_mV']),float(r['zB_im_mV']))
            if abs(zB)==0: continue
            H[(r['channel'],int(r['freq_cmd_hz']))].append(zA/zB)
    return {k:np.mean(v) for k,v in H.items()}
S={s:load(s) for s in ('FT1-S1','FT1-S2','FT1-S3')}
for s,h in S.items():
    chans=sorted(set(k[0] for k in h)); print(s, chans, {c:sum(1 for k in h if k[0]==c) for c in chans})
def corr(h1,c1,h2,c2):
    f=sorted(set(k[1] for k in h1 if k[0]==c1)&set(k[1] for k in h2 if k[0]==c2))
    a=np.log(np.abs([h1[(c1,x)] for x in f])); b=np.log(np.abs([h2[(c2,x)] for x in f]))
    return len(f), float(np.corrcoef(a,b)[0,1])
for s in S:
    print(s,'between paths F1 vs F2 log|H| corr:',corr(S[s],'F1',S[s],'F2'))
for a,b in (('FT1-S1','FT1-S2'),('FT1-S2','FT1-S3'),('FT1-S1','FT1-S3')):
    print(a,b,'same path F1:',corr(S[a],'F1',S[b],'F1'),' F2:',corr(S[a],'F2',S[b],'F2'))
