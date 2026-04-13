#!/usr/bin/env python3
"""E38 before/after perturbation removal comparison analysis."""
import json
import numpy as np
from itertools import combinations

pre_file = 'data/results/lab/additional_exps/additional_20260411_112952.json'
post_file = 'data/results/lab/additional_exps/additional_20260411_120229.json'

with open(pre_file) as f:
    pre = json.load(f)
with open(post_file) as f:
    post = json.load(f)

pre_rods = pre['results']['perturbation_spectrum']['rods']
post_rods = post['results']['perturbation_spectrum']['rods']
patterns = {'1': 'A', '2': 'B', '3': 'C', '4': 'E'}

print('E38 PERTURBATION SPECTRUM: FULL COMPARISON ANALYSIS')
print('=' * 70)

# Build all sweep vectors
all_sweeps = {}
for rid in ['1','2','3','4']:
    for cond, rods_data in [('pre', pre_rods), ('post', post_rods)]:
        sweep = rods_data[rid]['sweep_data']
        freqs_r = sorted([d['freq_hz'] for d in sweep])
        mags = {d['freq_hz']: d['magnitude'] for d in sweep}
        all_sweeps[f'{rid}_{cond}'] = np.array([mags[f] for f in freqs_r])

# ── S1: INTRA-ROD STABILITY ─────────────────────────────────────────────
print('\nS1: INTRA-ROD STABILITY (same rod, pre vs post)')
print('-' * 50)
for rid in ['1','2','3','4']:
    corr = np.corrcoef(all_sweeps[f'{rid}_pre'], all_sweeps[f'{rid}_post'])[0,1]
    rms = np.sqrt(np.mean((all_sweeps[f'{rid}_pre'] - all_sweeps[f'{rid}_post'])**2))
    rms_pct = rms / np.mean(all_sweeps[f'{rid}_pre']) * 100
    pre_r = pre_rods[rid]
    post_r = post_rods[rid]
    print(f'  Rod {rid} ({patterns[rid]}): r={corr:.6f}  RMS={rms_pct:.1f}%  '
          f'peaks:{pre_r["n_detected_peaks"]}->{post_r["n_detected_peaks"]}  '
          f'match:{pre_r["n_enrolled_matched"]}->{post_r["n_enrolled_matched"]}/{pre_r["n_enrolled_total"]}')

# ── S2: INTER-ROD DISCRIMINATION ────────────────────────────────────────
print('\nS2: INTER-ROD DISCRIMINATION')
print('-' * 50)
for label, cond in [('PRE-REMOVAL', 'pre'), ('POST-REMOVAL', 'post')]:
    print(f'  [{label}]')
    for (a,b) in combinations(['1','2','3','4'], 2):
        corr = np.corrcoef(all_sweeps[f'{a}_{cond}'], all_sweeps[f'{b}_{cond}'])[0,1]
        print(f'    Rod {a} vs {b}: r={corr:.6f}')
    print()

# ── S3: CONFUSION MATRIX ────────────────────────────────────────────────
print('S3: CROSS-CONDITION CONFUSION MATRIX')
print('     (row = post-removal rod, col = pre-removal rod)')
print('-' * 50)
header = '              '
for c in ['1','2','3','4']:
    header += f'  Rod{c}_pre'
print(header)

for r in ['1','2','3','4']:
    line = f'  Rod{r}_post  '
    best = -1
    best_c = ''
    corrs = []
    for c in ['1','2','3','4']:
        corr = np.corrcoef(all_sweeps[f'{r}_post'], all_sweeps[f'{c}_pre'])[0,1]
        corrs.append(corr)
        if corr > best:
            best = corr
            best_c = c
    for i, c in enumerate(['1','2','3','4']):
        marker = ' **' if c == r else ''
        line += f'  {corrs[i]:.4f}{marker}'
    line += f'  best={best_c}'
    print(line)
print('  ** = same rod (should be highest in each row)')

# ── S4: DISCRIMINATION GAP ──────────────────────────────────────────────
print('\nS4: DISCRIMINATION GAP — Can rods be told apart without perturbation?')
print('-' * 50)
intra = []
inter = []
for rid in ['1','2','3','4']:
    intra.append(np.corrcoef(all_sweeps[f'{rid}_pre'], all_sweeps[f'{rid}_post'])[0,1])
for (a,b) in combinations(['1','2','3','4'], 2):
    inter.append(np.corrcoef(all_sweeps[f'{a}_post'], all_sweeps[f'{b}_post'])[0,1])
    inter.append(np.corrcoef(all_sweeps[f'{a}_pre'], all_sweeps[f'{b}_post'])[0,1])

gap = np.mean(intra) - np.max(inter)
print(f'  Mean intra-rod r:  {np.mean(intra):.6f}')
print(f'  Max inter-rod r:   {np.max(inter):.6f}')
print(f'  Gap:               {gap:.6f}')
if gap > 0:
    print('  VERDICT: YES — rods are distinguishable without perturbation')
else:
    print('  VERDICT: NO — perturbation may be needed')

# ── S5: EFFECT SIZE BY BAND ─────────────────────────────────────────────
print('\nS5: PERTURBATION EFFECT SIZE BY FREQUENCY BAND')
print('-' * 50)
bands = [('0-2k', 0, 2000), ('2-5k', 2000, 5000), ('5-10k', 5000, 10000),
         ('10-20k', 10000, 20000), ('20-35k', 20000, 35000), ('35-50k', 35000, 50000)]

for rid in ['1','2','3','4']:
    sweep_pre = {d['freq_hz']: d['magnitude'] for d in pre_rods[rid]['sweep_data']}
    sweep_post = {d['freq_hz']: d['magnitude'] for d in post_rods[rid]['sweep_data']}
    freqs_r = sorted(sweep_pre.keys())
    pre_v = np.array([sweep_pre[f] for f in freqs_r])
    post_v = np.array([sweep_post[f] for f in freqs_r])
    pct = (post_v - pre_v) / (pre_v + 1) * 100
    parts = []
    for bname, blo, bhi in bands:
        mask = np.array([(blo <= f < bhi) for f in freqs_r])
        if mask.any():
            parts.append(f'{bname}:{np.mean(pct[mask]):+.1f}%')
    print(f'  Rod {rid} ({patterns[rid]}): {" ".join(parts)}')

# ── S6: TOP-5 PEAK FINGERPRINTS ─────────────────────────────────────────
print('\nS6: POST-REMOVAL TOP-5 PEAK FINGERPRINTS')
print('-' * 50)
rod_top5 = {}
for rid in ['1','2','3','4']:
    peaks = post_rods[rid]['detected_peaks']
    top5 = sorted(peaks, key=lambda p: p['magnitude'], reverse=True)[:5]
    rod_top5[rid] = top5
    desc = ' | '.join([f"{p['freq_hz']:.0f}Hz ({p['snr_db']:.0f}dB)" for p in top5])
    print(f'  Rod {rid} ({patterns[rid]}): {desc}')

print('\n  Top-5 overlap between rods (within +/-200Hz):')
rod_top5_freqs = {}
for rid in ['1','2','3','4']:
    rod_top5_freqs[rid] = [p['freq_hz'] for p in rod_top5[rid]]

for (a,b) in combinations(['1','2','3','4'], 2):
    overlap = 0
    for fa in rod_top5_freqs[a]:
        for fb in rod_top5_freqs[b]:
            if abs(fa-fb) <= 200:
                overlap += 1
                break
    print(f'    Rod {a} vs {b}: {overlap}/5')

print('\n' + '=' * 70)
print('ANALYSIS COMPLETE')
