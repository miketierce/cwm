import json, numpy as np, sys
sys.path.insert(0,'/tmp/cwm_adv_sci_xl0Fl5')
import emi_dip as E
base='/Users/Mike/Code/wcfoma/data/results/k_eff/termination_20261029/'
T=json.load(open(base+'term_result.json')); C=json.load(open(base+'confirm_result.json'))
def find_runs(d):
    return d['runs']
for name, J in (('PartA', T), ('Confirm', C)):
    runs = find_runs(J)
    for rid, run in runs.items():
        if not isinstance(run, dict) or 'windows' not in run: continue
        emi = E.analyse(base+rid+'.npz', 'F2')
        print(f"== {name} {rid}")
        print(f"{'win':10s} {'f0':>9s} {'Q':>5s} {'tauQ':>6s} {'dip%':>5s} {'K2ppm':>6s} {'fitrms':>6s} | {'tau_g':>6s} {'tau_o':>6s} {'up_g':>6s} | {'g/tauQ':>6s} {'pred':>6s} | {'o/g':>6s} {'pred(TX2 only)':>14s} | {'df o-g':>7s} {'pred TX2':>8s} | {'f_g-f0':>7s} {'pred':>5s}")
        for k, w in run['windows'].items():
            e = emi[k]; z = w['zoom']; 
            if not z.get('Q'): continue
            tq = 1e3*z['Q']/(np.pi*z['f0'])
            g = w['down']['grounded']; o = w['down']['open']; ug = w['up']['grounded']
            print(f"{k:10s} {z['f0']:9.1f} {z['Q']:5.0f} {tq:6.3f} {e['dip_pct']:5.1f} {e['k2_ppm']:6.0f} {e['vb_rms_mV']:6.2f} | {g['tau_ms']:6.3f} {o['tau_ms']:6.3f} {ug['tau_ms']:6.3f} | {g['tau_ms']/tq:6.3f} {e['pred_tauR_over_tauQ']:6.3f} | {w['down']['paired_ratio']:6.3f} {e['pred_tau_open_over_R']:14.3f} | {w['f_shift_hz']:7.1f} {e['pred_open_minus_R_hz']:8.1f} | {g['f_free_hz']-z['f0']:7.1f} {e['pred_fR_minus_f0_hz']:5.1f}  scored={w.get('scored')} usableQ={z.get('usable_Q')}")
