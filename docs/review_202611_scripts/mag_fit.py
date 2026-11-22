"""Offline test: Q from |zA| alone (source-referenced; includes the driven TX's 220-ohm loss) versus Q from zA/zB
(junction-referenced; excludes it). Prediction: Q_src/Q_junction ~ 1/(1+dip); ringdown tau should match tau from Q_src."""
import importlib.util, json, numpy as np, sys
sys.path.insert(0,'/tmp/cwm_adv_sci_xl0Fl5')
import emi_dip as E
fz = E.fz
base='/Users/Mike/Code/wcfoma/data/results/k_eff/'
R = json.load(open(base+'ringdown_20261029/ring_result.json'))
wins = {k: w for r in R['runs'].values() for k, w in r['windows'].items()}
emi = json.load(open('/tmp/cwm_adv_sci_xl0Fl5/emi_o3.json'))
rows=[]
for fn, lab in (('ringdown_20261029/F1_20261029_133846.npz','F1'),('ringdown_20261029/F2_20261029_134135.npz','F2')):
    m=np.load(base+fn); zc, f, zA, zB = m['zoom_center'], m['zoom_f_act'], m['zoom_zA'], m['zoom_zB']
    for c in np.unique(zc):
        sel=(zc==c); o=np.argsort(f[sel]); ff=f[sel][o]; a=np.abs(zA[sel])[o]; H=(zA[sel]/zB[sel])[o]
        # complex source-referenced estimate: G = H * |zB| * exp(i*phase model) -- use fitted model phase of V_B/V_s
        key=f'{lab}:{c}'; e=emi[key]; w=wins[key]
        fc=fz.fit(ff,H,int(c),'lin' if len(ff)>=10 else 'const')
        fm=fz.fit(ff,a,int(c),'mag')
        # model-based complex reconstruction of zA/V_s
        rho=2*np.pi*ff*E.RC0; k2=e['k2_ppm']*1e-6
        y=k2*fc['f0']**2/(fc['f0']**2-ff**2+1j*ff*fc['f0']/fc['Q'])
        G=H/(1+1j*rho*(1+y))
        fg=fz.fit(ff,G,int(c),'lin' if len(ff)>=10 else 'const')
        d=w['down']
        tq=lambda q,f0: 1e3*q/(np.pi*f0)
        rd=d.get('tau_ms')
        rows.append((key, fc['Q'], fm['Q'], fm['se_lnQ'], fg['Q'], e['dip_pct'], rd, tq(fc['Q'],fc['f0']), tq(fm['Q'],fm['f0']), tq(fg['Q'],fg['f0']), fm['f0']-fc['f0'], fg['f0']-fc['f0'], w['zoom'].get('usable_Q')))
print(f"{'window':10s} {'Qjunc':>6s} {'Qmag':>6s} {'se':>5s} {'Qsrc(model)':>11s} {'dip%':>5s} | {'Qmag/Qj':>7s} {'Qsrc/Qj':>7s} {'1/(1+dip)':>9s} | {'ring/tauQj':>10s} {'ring/tauQmag':>12s} {'ring/tauQsrc':>12s} | {'f0mag-f0j':>9s} {'f0src-f0j':>9s}")
for r in rows:
    key,qj,qm,se,qs,dip,rd,tj,tm,ts,dfm,dfs,us=r
    print(f"{key:10s} {qj:6.0f} {qm:6.0f} {se:5.2f} {qs:11.0f} {dip:5.1f} | {qm/qj:7.3f} {qs/qj:7.3f} {1/(1+dip/100):9.3f} | {rd/tj:10.3f} {rd/tm:12.3f} {rd/ts:12.3f} | {dfm:9.1f} {dfs:9.1f}  usableQ={us}")
u=[r for r in rows if r[-1]]
print('usable n',len(u))
print('median ring/tauQ junction:',np.median([r[6]/r[7] for r in u]),' mag:',np.median([r[6]/r[8] for r in u]),' src(model):',np.median([r[6]/r[9] for r in u]))
print('median Qmag/Qj',np.median([r[2]/r[1] for r in u]),' median Qsrc/Qj',np.median([r[4]/r[1] for r in u]))
