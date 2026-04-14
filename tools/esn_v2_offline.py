#!/usr/bin/env python3
"""
ESN v2 offline analysis: test cleaned feature sets on existing calibration.
No hardware needed — loads cached calibration data.

Goal: beat sw_poly (65.3%) by using:
1. Signal-only modes (12/31 have SNR > 5)
2. D-only modes (4 signal + 4 noise = 8, or just 4 signal)
3. Baseline subtraction + normalization
4. Mode ratio features
5. Per-plate polynomial on clean features only
"""
import json
import numpy as np
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LAB_DIR = ROOT / "data" / "results" / "lab" / "plate_exps"

# Load calibration
calib_files = sorted(LAB_DIR.glob("esn_calibration_*.json"))
with open(calib_files[-1]) as f:
    d = json.load(f)

calib = d['calibration']
modes = d['plate_modes']
freqs = d['readout_freqs_hz']
drive_freqs = [modes['D'][i] for i in d['input_indices']]
print(f"Loaded: {calib_files[-1].name}")
print(f"Drive freqs: {drive_freqs}")

# ── Identify signal vs noise modes ──

baseline = {pid: np.array(calib['0']['mean'][pid]) for pid in ['1','2','3','4','5']}
pnames = {'1': 'A', '2': 'B', '3': 'C', '4': 'D', '5': 'E'}

signal_modes = {}  # pid -> [(freq, readout_idx, max_snr)]
for pid, pname in pnames.items():
    sig = []
    for mf in modes[pname]:
        ri = int(np.argmin([abs(mf - rf) for rf in freqs]))
        base_val = baseline[pid][ri]
        max_snr = max(calib[str(t)]['mean'][pid][ri] / max(base_val, 1) - 1
                       for t in range(1, 16))
        if max_snr > 5:
            sig.append((mf, ri, max_snr))
    signal_modes[pid] = sig

total_sig = sum(len(v) for v in signal_modes.values())
print(f"\nSignal modes: {total_sig}/31")
for pid, pname in pnames.items():
    if signal_modes[pid]:
        info = [f"{s[0]:.0f}Hz(SNR={s[2]:.0f})" for s in signal_modes[pid]]
        print(f"  {pname}: {', '.join(info)}")


# ── Helpers ──

def interaction_expand(x, max_degree=3):
    n = len(x)
    terms = list(x)
    for deg in range(2, max_degree + 1):
        for combo in combinations(range(n), deg):
            t = 1.0
            for idx in combo:
                t *= x[idx]
            terms.append(t)
    return np.array(terms)


def normalize_list(features_list):
    arr = np.array(features_list)
    mu = arr.mean(axis=0)
    sigma = arr.std(axis=0) + 1e-8
    return [(f - mu) / sigma for f in features_list]


def software_poly(token, n_bits=4):
    bits = np.array([(token >> b) & 1 for b in range(n_bits)], dtype=np.float64)
    return interaction_expand(bits * 2 - 1, max_degree=4)


class ESN:
    def __init__(self, input_dim, hidden_dim=100, spectral_radius=0.9,
                 input_scale=0.3, leak=0.5, seed=42):
        rng = np.random.default_rng(seed)
        self.hidden_dim = hidden_dim
        self.leak = leak
        self.W_in = rng.standard_normal((hidden_dim, input_dim)) * input_scale
        W = rng.standard_normal((hidden_dim, hidden_dim))
        rho = np.max(np.abs(np.linalg.eigvals(W)))
        self.W_rec = W * (spectral_radius / rho) if rho > 0 else W

    def run_sequence(self, feat_seq):
        h = np.zeros(self.hidden_dim)
        for x in feat_seq:
            h = (1 - self.leak) * h + self.leak * np.tanh(
                self.W_in @ x + self.W_rec @ h)
        return h

    def collect_states(self, all_seqs):
        return np.array([self.run_sequence(s) for s in all_seqs])


def ridge_multiclass(H_tr, H_te, y_tr, y_te, n_classes=16, alpha=10.0):
    Hb_tr = np.column_stack([H_tr, np.ones(len(H_tr))])
    Hb_te = np.column_stack([H_te, np.ones(len(H_te))])
    d = Hb_tr.shape[1]
    Y_oh = np.zeros((len(y_tr), n_classes))
    for i, c in enumerate(y_tr):
        Y_oh[i, c] = 1.0
    W = np.linalg.solve(Hb_tr.T @ Hb_tr + alpha * np.eye(d), Hb_tr.T @ Y_oh)
    tr_acc = float(np.mean(np.argmax(Hb_tr @ W, axis=1) == y_tr))
    te_acc = float(np.mean(np.argmax(Hb_te @ W, axis=1) == y_te))
    return tr_acc, te_acc


# ── Build token → feature caches ──

token_feats = {}

# 1. Signal-only (12 modes, baseline-subtracted, normalized)
sig_raw = []
for t in range(16):
    feats = []
    for pid in ['1', '2', '3', '4', '5']:
        for mf, ri, _ in signal_modes[pid]:
            feats.append(calib[str(t)]['mean'][pid][ri] - baseline[pid][ri])
    sig_raw.append(np.array(feats))
sig_norm = normalize_list(sig_raw)
token_feats['signal_12_raw'] = sig_norm
token_feats['signal_12_poly3'] = [interaction_expand(f, 3) for f in sig_norm]
token_feats['signal_12_poly4'] = [interaction_expand(f, 4) for f in sig_norm]

# 2. Signal log-amplitude
sig_log = []
for t in range(16):
    feats = []
    for pid in ['1', '2', '3', '4', '5']:
        for mf, ri, _ in signal_modes[pid]:
            val = calib[str(t)]['mean'][pid][ri] - baseline[pid][ri]
            feats.append(np.log1p(max(0, val)))
    sig_log.append(np.array(feats))
sig_log_norm = normalize_list(sig_log)
token_feats['signal_12_log'] = sig_log_norm
token_feats['signal_12_log_poly3'] = [interaction_expand(f, 3) for f in sig_log_norm]

# 3. D signal modes only (4 modes)
d4_raw = []
for t in range(16):
    vals = [calib[str(t)]['mean']['4'][ri] - baseline['4'][ri]
            for _, ri, _ in signal_modes['4']]
    d4_raw.append(np.array(vals))
d4_norm = normalize_list(d4_raw)
token_feats['D4_signal'] = d4_norm
token_feats['D4_signal_poly4'] = [interaction_expand(f, 4) for f in d4_norm]

# 4. D all 8 modes
d8_raw = []
for t in range(16):
    spec = np.array(calib[str(t)]['mean']['4'])
    base = baseline['4']
    vals = []
    for mf in modes['D']:
        ri = int(np.argmin([abs(mf - rf) for rf in freqs]))
        vals.append(spec[ri] - base[ri])
    d8_raw.append(np.array(vals))
d8_norm = normalize_list(d8_raw)
token_feats['D8_all'] = d8_norm
token_feats['D8_all_poly3'] = [interaction_expand(f, 3) for f in d8_norm]

# 5. Mode ratios: pairwise ratios among signal modes
ratio_feats = []
for t in range(16):
    vals = []
    for pid in ['1', '2', '3', '4', '5']:
        for mf, ri, _ in signal_modes[pid]:
            vals.append(calib[str(t)]['mean'][pid][ri] - baseline[pid][ri])
    rats = []
    for i in range(len(vals)):
        for j in range(i + 1, len(vals)):
            rats.append(vals[i] / (abs(vals[j]) + 1.0))
    ratio_feats.append(np.array(rats))
ratio_norm = normalize_list(ratio_feats)
token_feats['mode_ratios'] = ratio_norm

# 6. Signal + ratios
token_feats['signal_plus_ratios'] = [
    np.concatenate([sig_norm[t], ratio_norm[t]]) for t in range(16)]

# 7. Per-plate poly (only on signal modes) — like v1 but trimmed
perplate_poly = []
for t in range(16):
    all_terms = []
    for pid in ['1', '2', '3', '4', '5']:
        smodes = signal_modes[pid]
        if smodes:
            vals = np.array([calib[str(t)]['mean'][pid][ri] - baseline[pid][ri]
                             for _, ri, _ in smodes])
            vals_log = np.log1p(np.maximum(vals, 0))
            mu = np.mean(vals_log) if len(vals_log) > 1 else 0
            sigma = np.std(vals_log) + 1e-8 if len(vals_log) > 1 else 1
            vals_std = (vals_log - mu) / sigma
            deg = 4 if len(smodes) <= 4 else 3
            poly = interaction_expand(vals_std, max_degree=deg)
            all_terms.extend(poly.tolist())
    perplate_poly.append(np.array(all_terms))
token_feats['perplate_signal_poly'] = perplate_poly

# 8. Cross-plate mode cluster: group by drive frequency
# Each drive freq excites modes on multiple plates simultaneously
# The PATTERN of response across plates is a unique feature
cluster_feats = []
drive_clusters = {}
for df in drive_freqs:
    cluster = []
    for pid in ['1', '2', '3', '4', '5']:
        for mf, ri, snr in signal_modes[pid]:
            if abs(mf - df) < 200:
                cluster.append((pid, ri, snr))
    drive_clusters[df] = cluster

for t in range(16):
    feats = []
    for df in drive_freqs:
        cluster = drive_clusters[df]
        vals = [calib[str(t)]['mean'][pid][ri] - baseline[pid][ri]
                for pid, ri, _ in cluster]
        feats.extend(vals)
        # Add ratios within cluster (cross-plate response ratios)
        if len(vals) >= 2:
            for i in range(len(vals)):
                for j in range(i + 1, len(vals)):
                    feats.append(vals[i] / (abs(vals[j]) + 1.0))
    cluster_feats.append(np.array(feats))
cluster_norm = normalize_list(cluster_feats)
token_feats['drive_clusters'] = cluster_norm
token_feats['drive_clusters_poly3'] = [interaction_expand(f, 3) for f in cluster_norm]

# Software baselines
token_feats['sw_poly'] = [software_poly(t) for t in range(16)]
token_feats['raw_bits'] = [np.array([(t >> b) & 1 for b in range(4)],
                                     dtype=np.float64) for t in range(16)]

# ── Print dimensions ──
print(f"\n  Feature dimensions:")
for name, cache in sorted(token_feats.items()):
    print(f"    {name}: {len(cache[0])}")

# ── ESN Experiment ──

rng = np.random.default_rng(42)
sequences = rng.integers(0, 16, size=(300, 4))
reversed_seqs = sequences[:, ::-1].copy()
n_train = 225

print(f"\n{'Feature Set':>30s} {'dim':>5s} {'last':>7s} "
      f"{'t3':>7s} {'t2':>7s} {'first':>7s} {'mean':>7s}")
print("-" * 80)

all_results = {}
for fs_name in ['sw_poly', 'raw_bits',
                'D4_signal', 'D4_signal_poly4',
                'D8_all', 'D8_all_poly3',
                'signal_12_raw', 'signal_12_poly3', 'signal_12_poly4',
                'signal_12_log', 'signal_12_log_poly3',
                'perplate_signal_poly',
                'mode_ratios', 'signal_plus_ratios',
                'drive_clusters', 'drive_clusters_poly3']:
    cache = token_feats[fs_name]
    dim = len(cache[0])

    all_feats = [[cache[int(t)] for t in seq] for seq in sequences]
    esn = ESN(input_dim=dim)
    H_tr = esn.collect_states(all_feats[:n_train])
    H_te = esn.collect_states(all_feats[n_train:])

    pos_test = []
    for pos in range(4):
        y_tr = reversed_seqs[:n_train, pos]
        y_te = reversed_seqs[n_train:, pos]
        _, te = ridge_multiclass(H_tr, H_te, y_tr, y_te)
        pos_test.append(te)

    mean_test = np.mean(pos_test)
    marker = ' ◀SW' if fs_name == 'sw_poly' else (' ★' if mean_test > 0.653 else '')
    print(f"{fs_name:>30s} {dim:5d} {pos_test[0]:6.1%} {pos_test[1]:6.1%} "
          f"{pos_test[2]:6.1%} {pos_test[3]:6.1%} {mean_test:6.1%}{marker}")
    all_results[fs_name] = {'mean': mean_test, 'pos': pos_test, 'dim': dim}

print(f"\n{'═' * 60}")
print(f"  COMPARISON vs sw_poly ({all_results['sw_poly']['mean']:.1%})")
print(f"{'═' * 60}")
sw = all_results['sw_poly']['mean']
for name, r in sorted(all_results.items(), key=lambda x: -x[1]['mean']):
    if name in ('sw_poly', 'raw_bits'):
        continue
    diff = r['mean'] - sw
    tag = 'BEATS ✓' if diff > 0.02 else 'TIES ≈' if abs(diff) <= 0.02 else 'LOSES ✗'
    print(f"  {name:>30s}: {r['mean']:6.1%} ({diff:+6.1%}) {tag}")
