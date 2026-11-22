import numpy as np, sys
base='/Users/Mike/Code/wcfoma/data/results/k_eff/ringdown_20261029/'
for fn in ['F1_20261029_133846.npz','F2_20261029_134135.npz']:
    m=np.load(base+fn)
    zc=m['zoom_center']; f=m['zoom_f_act']; zA=m['zoom_zA']; zB=m['zoom_zB']
    clean=(m['zoom_ovf']==0)&(m['zoom_clipA']==0)&(m['zoom_clipB']==0)
    print('=====',fn,'n',len(f),'clean',clean.sum())
    for c in np.unique(zc):
        sel=(zc==c)&clean
        ff=f[sel]; a=np.abs(zA[sel]); b=np.abs(zB[sel]); H=zA[sel]/zB[sel]
        o=np.argsort(ff)
        # average repeats at same freq
        uf=np.unique(np.round(ff,3))
        print('--- window',c,'npts',sel.sum(),'distinct',len(uf))
        for u in uf:
            s=np.isclose(ff,u,atol=1e-2)
            print(f"  f={u:10.1f}  |zA|={a[s].mean():8.2f}  |zB|={b[s].mean():8.3f} (sd {b[s].std():.3f}, n={s.sum()})  |H|={np.abs(H[s]).mean():.4f}  argH={np.degrees(np.angle(H[s].mean())):7.1f}")
