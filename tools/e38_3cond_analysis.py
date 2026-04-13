#!/usr/bin/env python3
"""E38 three-condition perturbation comparison:
  1. Original perturbation (as enrolled)
  2. Perturbation removed (clean rods)
  3. Random re-perturbation (new random sites)
"""
import json
import numpy as np
from itertools import combinations

orig_file = 'data/results/lab/additional_exps/additional_20260411_112952.json'
clean_file = 'data/results/lab/additional_exps/additional_20260411_120229.json'
rand_file = 'data/results/lab/additional_exps/additional_20260411_124246.json'

with open(orig_file) as f:
    orig = json.load(f)
with open(clean_file) as f:
    clean = json.load(f)
with open(rand_file) as f:
    rand = json.load(f)

orig_rods = orig['results']['perturbation_spectrum']['rods']
clean_rods = clean['results']['perturbation_spectrum']['rods']
rand_rods = rand['results']['perturbation_spectrum']['rods']

patterns = {'1': 'A', '2': 'B', '3': 'C', '4': 'E'}
cond_names = {'orig': 'Original Pert', 'clean': 'No Pert', 'rand': 'Random Pert'}

print('E38 THREE-CONDITION PERTURBATION ANALYSIS')
print('=' * 72)
print(f'  Condition 1: Original perturbation  ({orig_file})')
print(f'  Condition 2: Perturbation removed    ({clean_file})')
print(f'  Condition 3: Random re-perturbation  ({rand_file})')
print()

# Build all sweep vectors
all_sweeps = {}
for rid in ['1','2','3','4']:
    for cond_key, rods_data in [('orig', orig_rods), ('clean', clean_rods), ('rand', rand_rods)]:
        sweep = rods_data[rid]['sweep_data']
        freqs_r = sorted([d['freq_hz'] for d in sweep])
        mags = {d['freq_hz']: d['magnitude'] for d in sweep}
        all_sweeps[f'{rid}_{cond_key}'] = np.array([mags[f] for f in freqs_r])

# ── S1: PEAK SUMMARY TABLE ──────────────────────────────────────────────
print('S1: PEAK & MATCH SUMMARY')
print('-' * 72)
print(f'  {"Rod":<10} {"Orig Peaks":<14} {"Clean Peaks":<14} {"Rand Peaks":<14}')
print(f'  {"":10} {"(matched)":<14} {"(matched)":<14} {"(matched)":<14}')
for rid in ['1','2','3','4']:
    o = orig_rods[rid]
    c = clean_rods[rid]
    r = rand_rods[rid]
    print(f'  Rod {rid} ({patterns[rid]})  '
          f'{o["n_detected_peaks"]:>2} ({o["n_enrolled_matched"]:>2}/{o["n_enrolled_total"]})   '
          f'{c["n_detected_peaks"]:>2} ({c["n_enrolled_matched"]:>2}/{c["n_enrolled_total"]})   '
          f'{r["n_detected_peaks"]:>2} ({r["n_enrolled_matched"]:>2}/{r["n_enrolled_total"]})')

# ── S2: INTRA-ROD CORRELATION MATRIX (same rod across conditions) ────────
print('\nS2: INTRA-ROD CORRELATION (same rod, different conditions)')
print('-' * 72)
print(f'  {"Rod":<10} {"Orig↔Clean":<14} {"Orig↔Rand":<14} {"Clean↔Rand":<14}')
intra_oc = []
intra_or = []
intra_cr = []
for rid in ['1','2','3','4']:
    oc = np.corrcoef(all_sweeps[f'{rid}_orig'], all_sweeps[f'{rid}_clean'])[0,1]
    oran = np.corrcoef(all_sweeps[f'{rid}_orig'], all_sweeps[f'{rid}_rand'])[0,1]
    cr = np.corrcoef(all_sweeps[f'{rid}_clean'], all_sweeps[f'{rid}_rand'])[0,1]
    intra_oc.append(oc)
    intra_or.append(oran)
    intra_cr.append(cr)
    print(f'  Rod {rid} ({patterns[rid]})  {oc:.6f}      {oran:.6f}      {cr:.6f}')
print(f'  {"Mean":<10} {np.mean(intra_oc):.6f}      {np.mean(intra_or):.6f}      {np.mean(intra_cr):.6f}')

# ── S3: KEY QUESTION — Does random pert look more like original or clean?
print('\nS3: KEY QUESTION — Random pert closer to original or clean?')
print('-' * 72)
for rid in ['1','2','3','4']:
    r_to_orig = np.corrcoef(all_sweeps[f'{rid}_rand'], all_sweeps[f'{rid}_orig'])[0,1]
    r_to_clean = np.corrcoef(all_sweeps[f'{rid}_rand'], all_sweeps[f'{rid}_clean'])[0,1]
    closer = 'ORIGINAL' if r_to_orig > r_to_clean else 'CLEAN'
    diff = abs(r_to_orig - r_to_clean)
    print(f'  Rod {rid} ({patterns[rid]}): rand↔orig={r_to_orig:.6f}  rand↔clean={r_to_clean:.6f}  '
          f'→ closer to {closer} (Δ={diff:.6f})')

# ── S4: INTER-ROD DISCRIMINATION BY CONDITION ───────────────────────────
print('\nS4: INTER-ROD DISCRIMINATION BY CONDITION')
print('-' * 72)
for cond_key, cond_label in [('orig', 'ORIGINAL PERT'), ('clean', 'NO PERT'), ('rand', 'RANDOM PERT')]:
    corrs = []
    print(f'  [{cond_label}]')
    for (a,b) in combinations(['1','2','3','4'], 2):
        corr = np.corrcoef(all_sweeps[f'{a}_{cond_key}'], all_sweeps[f'{b}_{cond_key}'])[0,1]
        corrs.append(corr)
        print(f'    Rod {a} vs {b}: r={corr:.6f}')
    print(f'    Mean={np.mean(corrs):.6f}  Max={np.max(corrs):.6f}')
    print()

# ── S5: 3-CONDITION CONFUSION MATRIX ────────────────────────────────────
print('S5: CROSS-CONDITION CONFUSION MATRIX (rand row vs orig column)')
print('     Can random-pert rod correctly self-identify against original?')
print('-' * 72)
header = '              '
for c in ['1','2','3','4']:
    header += f'  Rod{c}_orig'
print(header)

correct = 0
for r in ['1','2','3','4']:
    line = f'  Rod{r}_rand  '
    best = -1
    best_c = ''
    corrs = []
    for c in ['1','2','3','4']:
        corr = np.corrcoef(all_sweeps[f'{r}_rand'], all_sweeps[f'{c}_orig'])[0,1]
        corrs.append(corr)
        if corr > best:
            best = corr
            best_c = c
    for i, c in enumerate(['1','2','3','4']):
        marker = ' **' if c == r else ''
        line += f'  {corrs[i]:.4f}{marker}'
    match = '✓' if best_c == r else '✗'
    line += f'  best={best_c} {match}'
    if best_c == r:
        correct += 1
    print(line)
print(f'  ** = same rod (should be highest)')
print(f'  Correct identifications: {correct}/4')

# Also clean vs orig
print('\n  CLEAN row vs ORIG column:')
header = '              '
for c in ['1','2','3','4']:
    header += f'  Rod{c}_orig'
print(header)

correct2 = 0
for r in ['1','2','3','4']:
    line = f'  Rod{r}_clean '
    best = -1
    best_c = ''
    corrs = []
    for c in ['1','2','3','4']:
        corr = np.corrcoef(all_sweeps[f'{r}_clean'], all_sweeps[f'{c}_orig'])[0,1]
        corrs.append(corr)
        if corr > best:
            best = corr
            best_c = c
    for i, c in enumerate(['1','2','3','4']):
        marker = ' **' if c == r else ''
        line += f'  {corrs[i]:.4f}{marker}'
    match = '✓' if best_c == r else '✗'
    line += f'  best={best_c} {match}'
    if best_c == r:
        correct2 += 1
    print(line)
print(f'  Correct identifications: {correct2}/4')

# ── S6: DISCRIMINATION GAP — ALL 3 CONDITIONS ───────────────────────────
print('\nS6: DISCRIMINATION GAP — 3-condition')
print('-' * 72)

# Intra-rod: all same-rod cross-condition correlations
intra_all = []
for rid in ['1','2','3','4']:
    for (ca, cb) in combinations(['orig','clean','rand'], 2):
        intra_all.append(np.corrcoef(all_sweeps[f'{rid}_{ca}'], all_sweeps[f'{rid}_{cb}'])[0,1])

# Inter-rod: all different-rod, any-condition correlations
inter_all = []
for (a,b) in combinations(['1','2','3','4'], 2):
    for ca in ['orig','clean','rand']:
        for cb in ['orig','clean','rand']:
            inter_all.append(np.corrcoef(all_sweeps[f'{a}_{ca}'], all_sweeps[f'{b}_{cb}'])[0,1])

gap = np.mean(intra_all) - np.max(inter_all)
print(f'  Mean intra-rod r (all condition pairs):  {np.mean(intra_all):.6f}  (n={len(intra_all)})')
print(f'  Max inter-rod r (any condition pair):     {np.max(inter_all):.6f}  (n={len(inter_all)})')
print(f'  Gap:                                      {gap:.6f}')
if gap > 0:
    print('  VERDICT: YES — rods are distinguishable across ALL conditions')
else:
    print('  VERDICT: NO — gap collapsed; perturbation location may matter')

# ── S7: RMS CHANGE BY CONDITION PAIR ────────────────────────────────────
print('\nS7: RMS % CHANGE BY CONDITION PAIR')
print('-' * 72)
for rid in ['1','2','3','4']:
    ref = np.mean(all_sweeps[f'{rid}_orig'])
    rms_oc = np.sqrt(np.mean((all_sweeps[f'{rid}_orig'] - all_sweeps[f'{rid}_clean'])**2)) / ref * 100
    rms_or = np.sqrt(np.mean((all_sweeps[f'{rid}_orig'] - all_sweeps[f'{rid}_rand'])**2)) / ref * 100
    rms_cr = np.sqrt(np.mean((all_sweeps[f'{rid}_clean'] - all_sweeps[f'{rid}_rand'])**2)) / ref * 100
    print(f'  Rod {rid} ({patterns[rid]}): orig↔clean={rms_oc:.1f}%  orig↔rand={rms_or:.1f}%  clean↔rand={rms_cr:.1f}%')

# ── S8: EFFECT SIZE BY FREQUENCY BAND (rand vs orig) ────────────────────
print('\nS8: PERTURBATION EFFECT SIZE BY BAND (Random vs Original)')
print('-' * 72)
bands = [('0-2k', 0, 2000), ('2-5k', 2000, 5000), ('5-10k', 5000, 10000),
         ('10-20k', 10000, 20000), ('20-35k', 20000, 35000), ('35-50k', 35000, 50000)]

for rid in ['1','2','3','4']:
    sweep_orig = {d['freq_hz']: d['magnitude'] for d in orig_rods[rid]['sweep_data']}
    sweep_rand = {d['freq_hz']: d['magnitude'] for d in rand_rods[rid]['sweep_data']}
    freqs_r = sorted(sweep_orig.keys())
    orig_v = np.array([sweep_orig[f] for f in freqs_r])
    rand_v = np.array([sweep_rand[f] for f in freqs_r])
    pct = (rand_v - orig_v) / (orig_v + 1) * 100
    parts = []
    for bname, blo, bhi in bands:
        mask = np.array([(blo <= f < bhi) for f in freqs_r])
        if mask.any():
            parts.append(f'{bname}:{np.mean(pct[mask]):+.1f}%')
    print(f'  Rod {rid} ({patterns[rid]}): {" ".join(parts)}')

# ── S9: DOES PERTURBATION LOCATION MATTER? ──────────────────────────────
print('\nS9: LOCATION SENSITIVITY — Does position of perturbation matter?')
print('-' * 72)
print('  Comparing: orig↔rand correlation vs orig↔clean correlation')
print('  If rand ≈ orig >> clean: location DOES NOT matter (mass-loading only)')
print('  If rand ≈ clean: perturbation at random sites has no effect')
print('  If orig >> rand > clean: location PARTIALLY matters')
print()
for rid in ['1','2','3','4']:
    r_oc = np.corrcoef(all_sweeps[f'{rid}_orig'], all_sweeps[f'{rid}_clean'])[0,1]
    r_or = np.corrcoef(all_sweeps[f'{rid}_orig'], all_sweeps[f'{rid}_rand'])[0,1]
    r_cr = np.corrcoef(all_sweeps[f'{rid}_clean'], all_sweeps[f'{rid}_rand'])[0,1]

    # Classification
    if r_or > r_oc and r_or > r_cr:
        verdict = 'Rand closer to Orig → location does NOT matter much'
    elif r_cr > r_or:
        verdict = 'Rand closer to Clean → random pert ≈ no change'
    else:
        verdict = 'Mixed — location partially matters'

    print(f'  Rod {rid} ({patterns[rid]}): orig↔clean={r_oc:.6f}  orig↔rand={r_or:.6f}  clean↔rand={r_cr:.6f}')
    print(f'    → {verdict}')

print('\n' + '=' * 72)
print('ANALYSIS COMPLETE')
