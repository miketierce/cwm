import json, numpy as np
R = json.load(open('/Users/Mike/Code/wcfoma/data/results/k_eff/ringdown_20261029/ring_result.json'))
print(R['status']); print(json.dumps(R['outcome'], indent=0)[:900])
for rid, run in R['runs'].items():
    for k, w in run['windows'].items():
        z = w['zoom']; d = w['down']; u = w['up']
        lw = (z['f0']/z['Q']) if z.get('Q') else None
        print(f"{k:11s} fact={w['f_act_hz']:.1f} f0={z.get('f0')} Q={z.get('Q')} usableQ={z.get('usable_Q')} npts={z.get('n_points')} tauQ={w['tau_Q_ms']} "
              f"down tau={d.get('tau_ms')} r2={d.get('r2')} df={d.get('df_hz')} ratio={d.get('ratio_to_tau_Q')} | up tau={u.get('tau_ms')} df={u.get('df_hz')} ratio={u.get('ratio_to_tau_Q')} "
              f"| free={w.get('free_decay_hz')} free-f0(lw)={w.get('free_minus_f0_linewidths')} lw={lw}")
