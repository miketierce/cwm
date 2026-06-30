#!/usr/bin/env python3
"""
Offline recall analysis from a saved enroll matrix (tools/recall_enroll_save.py).
Closes the honest gaps with NO bench time:
  - FAIR DIMENSIONALITY: expand the 4 wire bins to 779 random dims (wire_rp).
    If glass still beats wire_rp under noise, the 763 mode dims carry INDEPENDENT
    state info -> structured physics advantage, not just "more dimensions".
  - PARTIAL QUERY: hide vx,vy; recall landing from x,y only (pattern completion).
  - MODE DROPOUT: zero a fraction of modes (dead-sensor proxy) vs accuracy.
All leave-one-repeat-out, fair query noise to every method.
Usage: python3 tools/recall_analyze.py [npz]
"""
import numpy as np, json, sys, glob
from pathlib import Path
p=sys.argv[1] if len(sys.argv)>1 else sorted(glob.glob('data/results/pong/recall_enroll_*.npz'))[-1]
d=np.load(p); X=d['X']; L=d['L']; R=int(d['repeats']); PADH=int(d['padh']); driven=d['driven']
NW=int(d['nw']); naxes=int(d['naxes']); Fd=X.shape[1]; axis_block=naxes*NW
X=X/(X.mean(1,keepdims=True)+1e-9)            # drift-normalize per capture
rng=np.random.default_rng(0)
RP=rng.standard_normal((len(driven),Fd))/np.sqrt(len(driven))   # wire->779 random expansion

def feats(kind):
    if kind=='wire4': return X[:,driven]
    if kind=='wire_rp779': return X[:,driven]@RP
    if kind=='glass779': return X
    if kind.startswith('randmodes'):
        navail=Fd-axis_block; k=min(int(kind[9:]),navail); idx=rng.choice(np.arange(axis_block,Fd),k,replace=False); return X[:,idx]
    if kind=='glass_top256':
        A=(X-X.mean(0))/(X.std(0)+1e-9); gm=A.mean(0); bw=np.zeros(Fd); wi=np.zeros(Fd)
        for c in np.unique(L):
            v=A[L==c]; bw+=len(v)*(v.mean(0)-gm)**2; wi+=((v-v.mean(0))**2).sum(0)
        return X[:,np.argsort(-(bw/(wi+1e-9)))[:256]]
    raise ValueError(kind)

def loro(Xf,lab,sig,k=3,mask=None):
    hit=tot=0; rr=np.random.default_rng(1)
    for rt in range(R):
        te=[i for i in range(len(lab)) if i%R==rt]; tr=[i for i in range(len(lab)) if i%R!=rt]
        mu=Xf[tr].mean(0); sd=Xf[tr].std(0); sd[sd<1e-9]=1; A=(Xf[tr]-mu)/sd; dl=lab[tr]
        for i in te:
            q=(Xf[i]-mu)/sd
            if mask is not None: q=q*mask
            q=q+rr.standard_normal(Xf.shape[1])*sig
            nn=np.argsort(((A-q)**2).sum(1))[:k]; pr=int(round(np.median(dl[nn]))); hit+=abs(pr-lab[i])<=PADH//2; tot+=1
    return hit/tot*100

methods=['wire4','wire_rp779','glass779','glass_top256','randmodes256']
sig_grid=[0,0.5,1,1.5,2,3]
res={'sigma':sig_grid,'Fd':int(Fd),'n_modes':int(Fd-axis_block),'methods':{}}
print(f"Fd={Fd} (axis {axis_block} + modes {Fd-axis_block})")
print("=== FAIR-BASELINE sigma sweep (landing recall, LORO) ===")
print("method        "+"  ".join(f"s{ s}" for s in sig_grid))
for m in methods:
    Xf=feats(m); row=[loro(Xf,L,s) for s in sig_grid]; res['methods'][m]=row
    print(f"{m:13s} "+"  ".join(f"{v:4.0f}" for v in row))

# PARTIAL QUERY: hide vx,vy axis windows (blocks 2,3), recall landing from x,y + modes
mask=np.ones(Fd); mask[2*NW:4*NW]=0
pq_glass=[loro(X,L,s,mask=mask) for s in sig_grid]
pq_wire=[loro(X[:,driven],L,s,mask=(np.array([1,1,0,0]))) for s in sig_grid]
res['partial_query']={'glass779':pq_glass,'wire4':pq_wire}
print("\n=== PARTIAL QUERY (vx,vy hidden) landing recall ===")
print("glass779 "+"  ".join(f"{v:4.0f}" for v in pq_glass))
print("wire4    "+"  ".join(f"{v:4.0f}" for v in pq_wire))

# MODE DROPOUT at sigma=1: zero a fraction of the 767 mode features (dead-sensor proxy)
print("\n=== MODE DROPOUT @ sigma=1 (glass) ===")
drop=[0,0.1,0.25,0.5,0.75,0.9]; dr=[]
modes=np.arange(axis_block,Fd)
for fr in drop:
    Xd=X.copy()
    if fr>0:
        z=rng.choice(modes,int(fr*len(modes)),replace=False); Xd[:,z]=0
    v=loro(Xd,L,1.0); dr.append(v); print(f"drop {int(fr*100):2d}%: {v:4.0f}")
res['mode_dropout']={'frac':drop,'acc':dr}
out=Path(p).with_name('recall_analysis_'+Path(p).stem.split('_')[-1]+'.json')
json.dump(res,open(out,'w'),indent=1); print("\nsaved",out)
