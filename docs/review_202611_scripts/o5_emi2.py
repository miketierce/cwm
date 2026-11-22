import json, numpy as np, sys
sys.path.insert(0,'/tmp/cwm_adv_sci_xl0Fl5')
import emi_dip as E
base='/Users/Mike/Code/wcfoma/data/results/k_eff/termination_20261029/'
C=json.load(open(base+'confirm_result.json'))
run=C['runs'][0]
print([k for k in run.keys()])
rid=run.get('run_id','F2_20261029_221306')
wins = run['windows'] if 'windows' in run else run['scored']['windows']
rows=[]
for rc0_label, rc0 in (('220ohm x 4.1nF', 220*4.1e-9), ('270ohm x 4.1nF', 270*4.1e-9), ('220ohm x 5.5nF', 220*5.5e-9)):
    emi = E.analyse(base+rid+'.npz', 'F2', rc0=rc0)
    print('== confirm run', rid, ' RC0 =', rc0_label)
    print(f"{'win':10s} {'tauQ':>6s} {'dip%':>5s} {'K2ppm':>6s} | {'g/tauQ':>6s} {'pred':>6s} | {'o/g':>6s} {'predTX2':>7s} | {'df o-g':>7s} {'predTX2':>7s}")
    for k, w in wins.items():
        e = emi[k]; z = w['zoom']
        if not z.get('Q'): continue
        tq = 1e3*z['Q']/(np.pi*z['f0'])
        g = w['down']['grounded']; o = w['down']['open']
        print(f"{k:10s} {tq:6.3f} {e['dip_pct']:5.1f} {e['k2_ppm']:6.0f} | {g['tau_ms']/tq:6.3f} {e['pred_tauR_over_tauQ']:6.3f} | {w['down']['paired_ratio']:6.3f} {e['pred_tau_open_over_R']:7.3f} | {w['f_shift_hz']:7.1f} {e['pred_open_minus_R_hz']:7.1f}   scored={w.get('scored')}")
