"""Independent, phase-free check of the two-TX null ringdown (scratch; reads only)."""
import numpy as np, hashlib
raw_p='/Users/Mike/Code/wcfoma/data/raw/k_eff/nullring_20261029/null_20261029_141642.npz'
meta_p='/Users/Mike/Code/wcfoma/data/results/k_eff/nullring_20261029/null_20261029_141642.npz'
print('raw sha256', hashlib.sha256(open(raw_p,'rb').read()).hexdigest())
raw=np.load(raw_p); m=np.load(meta_p)
fs=781250.0
ka=float(raw['mv_per_count_A']); kb=float(raw['mv_per_count_B'])
A=raw['ring_A'].astype(np.int32)*ka; B=raw['ring_B'].astype(np.int32)*kb
cond=m['cond']; tgt=m['target']; fact=m['f_act']; status=m['status']; edge=m['edge_s']
print('unique cond',np.unique(cond),'targets',np.unique(tgt),'status',np.unique(status))
def env(x,f,win_s=0.4e-3):
    n=np.arange(len(x)); mixed=(x-x.mean())*np.exp(-2j*np.pi*f*n/fs)
    L=int(round(win_s*fs))|1; w=np.hanning(L); return 2*np.convolve(mixed,w/w.sum(),mode='same')
def stop_from_B(b,f):
    # last sample where Ch B exceeds 1 V, plus half a period
    idx=np.flatnonzero(b>1000.0)
    if len(idx)==0: return None
    return idx[-1]/fs+0.5/f
t=np.arange(A.shape[1])/fs
for tg in np.unique(tgt):
    out={}
    for c in ('S1','S2','N'):
        sel=np.flatnonzero((tgt==tg)&(cond==c))
        pre=[];post=[];curves=[]
        for i in sel:
            f=fact[i]
            ts=stop_from_B(B[i],f) if c!='S1' else float(edge[i])
            if ts is None or not (0.5e-3<=ts<=2.0e-3): 
                continue
            z=env(A[i],f)
            tt=t-ts
            pre.append(np.sqrt(np.mean(np.abs(z[(tt>-0.45e-3)&(tt<-0.25e-3)])**2)))
            post.append(np.sqrt(np.mean(np.abs(z[(tt>=0.3e-3)&(tt<=1.5e-3)])**2)))
            curves.append([np.abs(z[np.argmin(np.abs(tt-x))]) for x in (0.3e-3,1.0e-3,2.0e-3)])
        out[c]=(len(pre),np.median(pre),np.median(post),np.median(np.array(curves),axis=0))
    print(tg, {c:(v[0],round(v[1],2),round(v[2],2)) for c,v in out.items()})
    print('   steady N/S2 (phase-free, mV env) =',out['N'][1]/out['S2'][1], '   post-stop rms N/S2 =',out['N'][2]/out['S2'][2])
    print('   N/S2 at 0.3/1.0/2.0 ms =',out['N'][3]/out['S2'][3], ' S1/S2 steady =',out['S1'][1]/out['S2'][1])
