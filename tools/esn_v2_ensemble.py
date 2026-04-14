#!/usr/bin/env python3
"""
ESN v2 offline part 2: ensemble of per-plate ESNs + hyperparameter sweep.
Goal: find an approach that beats sw_poly using existing calibration data,
then design the per-plate calibration experiment.
"""
import json
import numpy as np
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LAB_DIR = ROOT / "data" / "results" / "lab" / "plate_exps"

with open(sorted(LAB_DIR.glob("esn_calibration_*.json"))[-1]) as f:
    d = json.load(f)

calib = d['calibration']
modes = d['plate_modes']
freqs = d['readout_freqs_hz']
drive_freqs = [modes['D'][i] for i in d['input_indices']]

baseline = {pid: np.array(calib['0']['mean'][pid]) for pid in ['1','2','3','4','5']}
pnames = {'1': 'A', '2': 'B', '3': 'C', '4': 'D', '5': 'E'}

# Identify signal modes per plate
signal_modes = {}
for pid, pname in pnames.items():
    sig = []
    for mf in modes[pname]:
        ri = int(np.argmin([abs(mf - rf) for rf in freqs]))
        max_snr = max(calib[str(t)]['mean'][pid][ri] / max(baseline[pid][ri], 1) - 1
                       for t in range(1, 16))
        if max_snr > 5:
            sig.append((mf, ri, max_snr))
    signal_modes[pid] = sig


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


def software_poly(token):
    bits = np.array([(token >> b) & 1 for b in range(4)], dtype=np.float64)
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
    d_dim = Hb_tr.shape[1]
    Y_oh = np.zeros((len(y_tr), n_classes))
    for i, c in enumerate(y_tr):
        Y_oh[i, c] = 1.0
    W = np.linalg.solve(Hb_tr.T @ Hb_tr + alpha * np.eye(d_dim),
                         Hb_tr.T @ Y_oh)
    pred_te = np.argmax(Hb_te @ W, axis=1)
    te_acc = float(np.mean(pred_te == y_te))
    # Return raw scores too for ensemble
    return te_acc, Hb_te @ W


def run_esn_experiment(token_feats, sequences, reversed_seqs, n_train,
                       esn_params=None):
    """Run ESN and return per-position test accuracy."""
    if esn_params is None:
        esn_params = {}
    dim = len(token_feats[0])
    all_feats = [[token_feats[int(t)] for t in seq] for seq in sequences]

    esn = ESN(input_dim=dim, **esn_params)
    H_tr = esn.collect_states(all_feats[:n_train])
    H_te = esn.collect_states(all_feats[n_train:])

    pos_test = []
    all_scores = []
    for pos in range(4):
        y_tr = reversed_seqs[:n_train, pos]
        y_te = reversed_seqs[n_train:, pos]
        te_acc, scores = ridge_multiclass(H_tr, H_te, y_tr, y_te)
        pos_test.append(te_acc)
        all_scores.append(scores)

    return np.mean(pos_test), pos_test, all_scores


# ── Build per-plate token features ──

plate_token_feats = {}
for pid, pname in pnames.items():
    smodes = signal_modes[pid]
    if not smodes:
        continue
    feats = []
    for t in range(16):
        vals = [calib[str(t)]['mean'][pid][ri] - baseline[pid][ri]
                for _, ri, _ in smodes]
        feats.append(np.array(vals))
    # Normalize
    arr = np.array(feats)
    mu = arr.mean(axis=0)
    sigma = arr.std(axis=0) + 1e-8
    feats = [(f - mu) / sigma for f in feats]

    # Also build polynomial version
    if len(smodes) <= 4:
        deg = 4
    elif len(smodes) <= 6:
        deg = 3
    else:
        deg = 2
    feats_poly = [interaction_expand(f, max_degree=deg) for f in feats]
    plate_token_feats[pname] = {'raw': feats, 'poly': feats_poly}
    print(f"Plate {pname}: {len(smodes)} signal modes → "
          f"raw {len(feats[0])}d, poly {len(feats_poly[0])}d")

# ── Sequences ──
rng = np.random.default_rng(42)
N_SEQ = 300
sequences = rng.integers(0, 16, size=(N_SEQ, 4))
reversed_seqs = sequences[:, ::-1].copy()
n_train = 225

# ── 1. Per-plate individual ESN ──
print(f"\n{'=' * 70}")
print("  PART 1: Per-plate ESN (individual)")
print(f"{'=' * 70}")

per_plate_results = {}
for pname, pdata in plate_token_feats.items():
    for ftype in ['raw', 'poly']:
        label = f"{pname}_{ftype}"
        token_f = pdata[ftype]
        mean_acc, pos_acc, scores = run_esn_experiment(
            token_f, sequences, reversed_seqs, n_train)
        per_plate_results[label] = {
            'mean': mean_acc, 'pos': pos_acc, 'scores': scores}
        print(f"  {label:>12s} ({len(token_f[0]):3d}d): "
              f"last={pos_acc[0]:.1%} t3={pos_acc[1]:.1%} "
              f"t2={pos_acc[2]:.1%} first={pos_acc[3]:.1%} "
              f"mean={mean_acc:.1%}")

# sw_poly baseline
sw_feats = [software_poly(t) for t in range(16)]
sw_mean, sw_pos, sw_scores = run_esn_experiment(
    sw_feats, sequences, reversed_seqs, n_train)
print(f"  {'sw_poly':>12s} ({len(sw_feats[0]):3d}d): "
      f"last={sw_pos[0]:.1%} t3={sw_pos[1]:.1%} "
      f"t2={sw_pos[2]:.1%} first={sw_pos[3]:.1%} "
      f"mean={sw_mean:.1%} ◀SW")


# ── 2. Ensemble: combine per-plate scores ──
print(f"\n{'=' * 70}")
print("  PART 2: ENSEMBLE (combine per-plate ESN predictions)")
print(f"{'=' * 70}")

def ensemble_accuracy(score_dicts, reversed_seqs, n_train):
    """Average raw scores from multiple ESNs, then argmax."""
    pos_accs = []
    for pos in range(4):
        y_te = reversed_seqs[n_train:, pos]
        combined_scores = np.zeros_like(score_dicts[0][pos])
        for sd in score_dicts:
            # Normalize scores (softmax-like)
            s = sd[pos]
            s_norm = s - s.mean(axis=1, keepdims=True)
            s_std = s.std(axis=1, keepdims=True) + 1e-8
            combined_scores += s_norm / s_std
        preds = np.argmax(combined_scores, axis=1)
        pos_accs.append(float(np.mean(preds == y_te)))
    return np.mean(pos_accs), pos_accs

# Ensemble of ALL plates (poly features)
all_plate_scores = [per_plate_results[f'{p}_poly']['scores']
                    for p in plate_token_feats if f'{p}_poly' in per_plate_results]
ens_mean, ens_pos = ensemble_accuracy(all_plate_scores, reversed_seqs, n_train)
print(f"  {'all_plates':>20s}: last={ens_pos[0]:.1%} t3={ens_pos[1]:.1%} "
      f"t2={ens_pos[2]:.1%} first={ens_pos[3]:.1%} mean={ens_mean:.1%}")

# Ensemble of plates + sw_poly
all_plus_sw = all_plate_scores + [sw_scores]
ens_sw_mean, ens_sw_pos = ensemble_accuracy(all_plus_sw, reversed_seqs, n_train)
print(f"  {'plates+sw_poly':>20s}: last={ens_sw_pos[0]:.1%} t3={ens_sw_pos[1]:.1%} "
      f"t2={ens_sw_pos[2]:.1%} first={ens_sw_pos[3]:.1%} mean={ens_sw_mean:.1%}")

# Top-2 plates + sw_poly
# Sort plates by performance
sorted_plates = sorted(per_plate_results.items(), key=lambda x: -x[1]['mean'])
print(f"\n  Per-plate ranking:")
for label, r in sorted_plates:
    print(f"    {label:>12s}: {r['mean']:.1%}")

# Try top-N combinations
for n_top in [2, 3]:
    top_labels = [l for l, _ in sorted_plates[:n_top] if '_poly' in l]
    if len(top_labels) < n_top:
        top_labels = [l for l, _ in sorted_plates[:n_top * 2] if '_poly' in l][:n_top]
    top_scores = [per_plate_results[l]['scores'] for l in top_labels]
    top_mean, top_pos = ensemble_accuracy(top_scores, reversed_seqs, n_train)
    print(f"  {'top-' + str(n_top) + ' poly':>20s}: last={top_pos[0]:.1%} "
          f"t3={top_pos[1]:.1%} t2={top_pos[2]:.1%} first={top_pos[3]:.1%} "
          f"mean={top_mean:.1%} ({', '.join(top_labels)})")

    # With sw_poly added
    combo_scores = top_scores + [sw_scores]
    combo_mean, combo_pos = ensemble_accuracy(combo_scores, reversed_seqs, n_train)
    print(f"  {'top-' + str(n_top) + '+sw':>20s}: last={combo_pos[0]:.1%} "
          f"t3={combo_pos[1]:.1%} t2={combo_pos[2]:.1%} first={combo_pos[3]:.1%} "
          f"mean={combo_mean:.1%}")


# ── 3. Hyperparameter sweep for D4_signal_poly4 ──
print(f"\n{'=' * 70}")
print("  PART 3: HYPERPARAMETER SWEEP (D4 signal + poly4)")
print(f"{'=' * 70}")

d4_feats = plate_token_feats['D']['poly'] if 'D' in plate_token_feats else None
if d4_feats:
    best_plate = {'mean': 0, 'params': {}}
    best_sw = {'mean': 0, 'params': {}}

    configs = []
    for hidden in [50, 100, 200]:
        for sr in [0.5, 0.9, 0.99]:
            for leak in [0.1, 0.3, 0.5, 0.9]:
                for iscale in [0.1, 0.3, 0.5]:
                    configs.append({
                        'hidden_dim': hidden,
                        'spectral_radius': sr,
                        'leak': leak,
                        'input_scale': iscale
                    })

    print(f"  Testing {len(configs)} configurations...")
    for cfg in configs:
        # D4 poly4
        m1, _, _ = run_esn_experiment(d4_feats, sequences, reversed_seqs, n_train,
                                       esn_params=cfg)
        if m1 > best_plate['mean']:
            best_plate = {'mean': m1, 'params': cfg.copy()}

        # sw_poly
        m2, _, _ = run_esn_experiment(sw_feats, sequences, reversed_seqs, n_train,
                                       esn_params=cfg)
        if m2 > best_sw['mean']:
            best_sw = {'mean': m2, 'params': cfg.copy()}

    print(f"\n  Best D4_signal_poly4: {best_plate['mean']:.1%}")
    print(f"    params: {best_plate['params']}")
    print(f"  Best sw_poly:         {best_sw['mean']:.1%}")
    print(f"    params: {best_sw['params']}")
    diff = best_plate['mean'] - best_sw['mean']
    print(f"\n  Gap at best params: {diff:+.1%} "
          f"({'PLATE WINS' if diff > 0.02 else 'TIE' if abs(diff) <= 0.02 else 'SW WINS'})")

    # Check at sw_poly's best params whether D4 does better
    m_d4_at_sw, _, _ = run_esn_experiment(
        d4_feats, sequences, reversed_seqs, n_train, esn_params=best_sw['params'])
    m_sw_at_sw, _, _ = run_esn_experiment(
        sw_feats, sequences, reversed_seqs, n_train, esn_params=best_sw['params'])
    print(f"\n  At sw_poly's best params:")
    print(f"    D4_signal_poly4: {m_d4_at_sw:.1%}")
    print(f"    sw_poly:         {m_sw_at_sw:.1%}")
    print(f"    gap: {m_d4_at_sw - m_sw_at_sw:+.1%}")


# ── 4. Concatenated features with ADAPTIVE input scaling ──
print(f"\n{'=' * 70}")
print("  PART 4: CONCAT with adapted ESN")
print(f"{'=' * 70}")

# Concat all signal modes (12 dims) - no polynomial, let ESN do nonlinearity
sig_concat = []
for t in range(16):
    feats = []
    for pid in ['1', '2', '3', '4', '5']:
        for mf, ri, _ in signal_modes[pid]:
            feats.append(calib[str(t)]['mean'][pid][ri] - baseline[pid][ri])
    sig_concat.append(np.array(feats))
arr = np.array(sig_concat)
mu = arr.mean(axis=0)
sigma = arr.std(axis=0) + 1e-8
sig_concat = [(f - mu) / sigma for f in sig_concat]

# Try ESN with input_scale adapted to dim
for iscale in [0.05, 0.1, 0.15, 0.2, 0.3]:
    m, p, _ = run_esn_experiment(sig_concat, sequences, reversed_seqs, n_train,
                                  esn_params={'input_scale': iscale})
    print(f"  signal_12 iscale={iscale:.2f}: "
          f"last={p[0]:.1%} t3={p[1]:.1%} t2={p[2]:.1%} first={p[3]:.1%} "
          f"mean={m:.1%}")


# ── Final summary ──
print(f"\n{'═' * 70}")
print("  SUMMARY")
print(f"{'═' * 70}")
print(f"  sw_poly (default ESN):    {sw_mean:.1%}")
if d4_feats:
    print(f"  D4_poly4 (default ESN):   {per_plate_results.get('D_poly', {}).get('mean', 0):.1%}")
    print(f"  D4_poly4 (best ESN):      {best_plate['mean']:.1%}")
    print(f"  sw_poly (best ESN):       {best_sw['mean']:.1%}")
print(f"  Ensemble all plates:      {ens_mean:.1%}")
print(f"  Ensemble plates+sw:       {ens_sw_mean:.1%}")
print(f"\n  Conclusion...")
if best_plate['mean'] > best_sw['mean'] + 0.02:
    print(f"  → D4 PLATE BEATS sw_poly by {best_plate['mean']-best_sw['mean']:.1%}")
    print(f"  → Per-plate calibration should amplify this advantage!")
elif ens_sw_mean > sw_mean + 0.02:
    print(f"  → ENSEMBLE beats individual by {ens_sw_mean-sw_mean:.1%}")
    print(f"  → Per-plate calibration (5 independent drives) = true ensemble")
else:
    print(f"  → Cannot beat sw_poly with existing D-only data")
    print(f"  → Per-plate calibration IS needed for 31 clean independent features")
