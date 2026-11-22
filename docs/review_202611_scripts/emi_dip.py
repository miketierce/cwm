"""Scratch analysis (read-only on the repo): does Ch B (TX junction voltage) show the electromechanical
impedance dip of each mode, and does the coupling K^2 it implies predict
 (a) the ringdown-vs-linewidth shortfall (O3), (b) the open/grounded frequency pull and tau ratio (O5)?
Model, single mode, driven TX = C0 in parallel with motional branch; source = V_s behind R:
   V_B/V_s = 1 / (1 + i rho (1 + K2 * f0^2/(f0^2 - f^2 + i f f0/Qsc))),   rho = 2 pi f R C0
   zA/zB has the short-circuit pole (f0, Qsc);   the free decay through R has
   1/Q_R = 1/Qsc + K2 rho/(1+rho^2),  f_R = f0 (1 + K2/2 * rho^2/(1+rho^2)),  open: f_o = f0 (1 + K2/2), 1/Q_o = 1/Qsc
"""
import importlib.util, json, sys
import numpy as np
from scipy.optimize import least_squares
spec = importlib.util.spec_from_file_location('fit_zoom', '/Users/Mike/Code/wcfoma/data/results/k_eff/overnight_20261026/fit_zoom.py')
fz = importlib.util.module_from_spec(spec); spec.loader.exec_module(fz)

RC0 = 220.0 * 4.1e-9   # s  (nominal; C0 is 'at least 4.1 nF' for TX2, unmeasured for TX1)

def vb_model(p, f, f0, Q, rc0):
    a, b, k2 = p
    rho = 2*np.pi*f*rc0
    y = k2 * f0**2 / (f0**2 - f**2 + 1j*f*f0/Q)
    return (a + b*(f - f0)) / np.abs(1 + 1j*rho*(1 + y))

def analyse(meta_path, path_label, rc0=RC0):
    m = np.load(meta_path)
    zc, f, zA, zB = m['zoom_center'], m['zoom_f_act'], m['zoom_zA'], m['zoom_zB']
    clean = (m['zoom_ovf']==0)&(m['zoom_clipA']==0)&(m['zoom_clipB']==0)
    out = {}
    for c in np.unique(zc):
        sel = (zc==c)&clean
        o = np.argsort(f[sel]); ff = f[sel][o]; H = (zA[sel]/zB[sel])[o]; vb = np.abs(zB[sel])[o]
        kind = 'lin' if len(ff) >= 10 else 'const'
        ft = fz.fit(ff, H, int(c), kind)
        usable = ft['in_window'] and ft['se_f0'] <= 20 and ft['rel_rms'] <= 0.10 and ft['se_lnQ'] <= 0.15
        f0, Q = ft['f0'], ft['Q']
        best = None
        for k20 in (1e-4, 5e-4, 2e-3):
            r = least_squares(lambda p: vb_model(p, ff, f0, Q, rc0) - vb, [vb.max()*1.1, 0.0, k20], x_scale=[100, 0.01, 1e-4])
            if best is None or r.cost < best.cost: best = r
        a, b, k2 = best.x
        n, npar = len(ff), 3
        cov = np.linalg.pinv(best.jac.T @ best.jac) * 2*best.cost/max(n-npar,1)
        se_k2 = float(np.sqrt(cov[2,2]))
        rms = float(np.sqrt(np.mean(best.fun**2)))
        # null model: no dip
        r0 = np.polyfit(ff - f0, vb, 1); rms0 = float(np.sqrt(np.mean((np.polyval(r0, ff-f0) - vb)**2)))
        rho0 = 2*np.pi*f0*rc0
        d_eta = k2*rho0/(1+rho0**2)
        out[f'{path_label}:{c}'] = dict(f0=f0, Q=Q, usable=bool(usable), n=n, k2_ppm=1e6*k2, se_k2_ppm=1e6*se_k2,
            vb_rms_mV=rms, vb_rms_nodip_mV=rms0, dip_pct=100*(1 - vb.min()/np.median(np.r_[vb[:2], vb[-2:]])),
            rho=rho0, K2Q=k2*Q,
            pred_tauR_over_tauQ=1/(1 + Q*d_eta),
            pred_fR_minus_f0_hz=f0*k2/2*rho0**2/(1+rho0**2),
            pred_open_minus_R_hz=f0*k2/2/(1+rho0**2),
            pred_tau_open_over_R=1 + Q*d_eta)
    return out

if __name__ == '__main__':
    base = '/Users/Mike/Code/wcfoma/data/results/k_eff/'
    R = json.load(open(base+'ringdown_20261029/ring_result.json'))
    wins = {k: w for r in R['runs'].values() for k, w in r['windows'].items()}
    res = {}
    res.update(analyse(base+'ringdown_20261029/F1_20261029_133846.npz', 'F1'))
    res.update(analyse(base+'ringdown_20261029/F2_20261029_134135.npz', 'F2'))
    print("O3 run: EMI dip on Ch B (driven TX junction) vs measured ringdown shortfall")
    print(f"{'window':10s} {'f0':>9s} {'Q':>5s} {'dip%':>5s} {'K2ppm':>7s} {'se':>5s} {'K2Q':>5s} {'rms/nodip mV':>13s} | {'pred tauR/tauQ':>14s} {'meas down':>9s} {'meas up':>8s} | {'pred fR-f0':>10s} {'meas free-f0':>12s}")
    rows = []
    for k, e in res.items():
        w = wins[k]; d = w['down']; u = w['up']
        md = d.get('ratio_to_tau_Q'); mu = u.get('ratio_to_tau_Q')
        mf = (w['free_decay_hz'] - w['zoom']['f0']) if 'free_decay_hz' in w else None
        print(f"{k:10s} {e['f0']:9.1f} {e['Q']:5.0f} {e['dip_pct']:5.1f} {e['k2_ppm']:7.0f} {e['se_k2_ppm']:5.0f} {e['K2Q']:5.2f} {e['vb_rms_mV']:6.2f}/{e['vb_rms_nodip_mV']:5.2f} | {e['pred_tauR_over_tauQ']:14.3f} {('%.3f'%md) if md else '   -  ':>9s} {('%.3f'%mu) if mu else '   -  ':>8s} | {e['pred_fR_minus_f0_hz']:10.1f} {('%.1f'%mf) if mf is not None else '-':>12s}   usable={e['usable']}")
        if md and e['usable']: rows.append((k, e['pred_tauR_over_tauQ'], md, mu, e['pred_fR_minus_f0_hz'], mf))
    rows_np = np.array([[r[1], r[2], r[3], r[4], r[5]] for r in rows], float)
    from scipy.stats import spearmanr, pearsonr
    print("n usable:", len(rows))
    print("median predicted tauR/tauQ:", np.median(rows_np[:,0]), " median measured ringdown:", np.median(rows_np[:,1]), " ring-up:", np.median(rows_np[:,2]))
    print("pearson pred vs ringdown:", pearsonr(rows_np[:,0], rows_np[:,1]), " spearman:", spearmanr(rows_np[:,0], rows_np[:,1]))
    print("pearson pred vs ringup:", pearsonr(rows_np[:,0], rows_np[:,2]))
    print("median predicted fR-f0:", np.median(rows_np[:,3]), " measured:", np.median(rows_np[:,4]), " pearson:", pearsonr(rows_np[:,3], rows_np[:,4]))
    json.dump(res, open('/tmp/cwm_adv_sci_xl0Fl5/emi_o3.json', 'w'), indent=1)
