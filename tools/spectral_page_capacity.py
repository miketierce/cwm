#!/usr/bin/env python3
"""
Spectral page capacity analysis from existing CWM data (PR #3).

Answers: can different frequency bands in the acoustic response be treated
as independent "pages" — each addressed by a different drive frequency and
containing different stored information?

Tests:
1. Band-wise mutual information: do different spectral bands encode different
   state information?
2. Cross-talk matrix: does changing drive in band A leak into readouts in band B?
3. Page classification: can each frequency band independently identify the
   stored state?
4. Multi-page capacity: how many independent pages can the same object support?

Usage: python3 tools/spectral_page_capacity.py [npz]
"""
import numpy as np, json, sys, glob, time
from pathlib import Path
from sklearn.linear_model import RidgeClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import LeaveOneGroupOut

results = {}
t0 = time.time()

# ==============================================================
# Load data
# ==============================================================

# 1. Multitone Pong data (3-channel drive, 767 modes)
mt_files = sorted(glob.glob('data/results/pong/pong_multitone_data_*.npz'))
# 2. Recall enrollment (4-axis drive, 212 modes)
re_file = sorted(glob.glob('data/results/pong/recall_enroll_*.npz'))[-1]

# Load recall enrollment for primary analysis
d = np.load(re_file)
X = d['X']; L = d['L']; R = int(d['repeats']); NW = int(d['nw'])
naxes = int(d['naxes']); Fd = X.shape[1]; freqs = d['freqs']
xs = d['xs']; ys = d['ys']; vx = d['vx']; vy = d['vy']
axis_block = naxes * NW
X = X / (X.mean(1, keepdims=True) + 1e-9)

print(f"Recall enrollment: X{X.shape}, {len(freqs)} mode freqs "
      f"({freqs.min():.0f}-{freqs.max():.0f} Hz)")
print(f"Axis block: {axis_block}, Modes: {Fd - axis_block}")
results['source'] = re_file
results['n_modes'] = int(len(freqs))
results['freq_range'] = [float(freqs.min()), float(freqs.max())]


# ==============================================================
# 1. DEFINE SPECTRAL PAGES (frequency bands)
# ==============================================================
print("\n" + "=" * 60)
print("1. SPECTRAL PAGE DEFINITIONS")
print("=" * 60)

# Split modes into pages by frequency band
n_pages_options = [2, 3, 4, 6, 8]
mode_indices = np.arange(axis_block, Fd)  # indices of mode features in X

for n_pages in n_pages_options:
    page_size = len(mode_indices) // n_pages
    pages = []
    for p in range(n_pages):
        start = p * page_size
        end = (p + 1) * page_size if p < n_pages - 1 else len(mode_indices)
        page_idx = mode_indices[start:end]
        freq_lo = freqs[start] if start < len(freqs) else 0
        freq_hi = freqs[min(end - 1, len(freqs) - 1)] if end > 0 else 0
        pages.append({
            'idx': page_idx,
            'freq_range': (float(freq_lo), float(freq_hi)),
            'n_features': len(page_idx),
        })
    if n_pages <= 4:
        for i, pg in enumerate(pages):
            print(f"  {n_pages}-page split: page {i} = "
                  f"{pg['freq_range'][0]:.0f}-{pg['freq_range'][1]:.0f} Hz "
                  f"({pg['n_features']} features)")


# ==============================================================
# 2. PAGE-WISE CLASSIFICATION ACCURACY
# ==============================================================
print("\n" + "=" * 60)
print("2. PAGE-WISE LANDING RECALL (each band alone, LORO)")
print("=" * 60)


def loro_ridge(Xf, lab, groups):
    """Leave-one-repeat-out Ridge classification."""
    sc = StandardScaler()
    logo = LeaveOneGroupOut()
    preds = np.zeros(len(lab), dtype=int)
    for tr, te in logo.split(Xf, lab, groups):
        Xs = sc.fit_transform(Xf[tr])
        clf = RidgeClassifier(alpha=1.0).fit(Xs, lab[tr])
        preds[te] = clf.predict(sc.transform(Xf[te]))
    acc = np.mean(np.abs(preds - lab) <= 1) * 100  # PADH//2 = 1
    return acc


groups = np.arange(len(X)) % R  # repeat index

page_accuracy = {}
for n_pages in n_pages_options:
    page_size = len(mode_indices) // n_pages
    accs = []
    for p in range(n_pages):
        start = p * page_size
        end = (p + 1) * page_size if p < n_pages - 1 else len(mode_indices)
        idx = mode_indices[start:end]
        acc = loro_ridge(X[:, idx], L, groups)
        accs.append(round(acc, 1))

    # Also test all modes combined
    acc_all = loro_ridge(X[:, mode_indices], L, groups)

    # And axis-only
    acc_axis = loro_ridge(X[:, :axis_block], L, groups)

    page_accuracy[f'{n_pages}_pages'] = {
        'per_page': accs,
        'all_modes': round(acc_all, 1),
        'axis_only': round(acc_axis, 1),
    }
    print(f"  {n_pages} pages: {accs}  |  all={acc_all:.1f}  axis={acc_axis:.1f}")

results['page_accuracy'] = page_accuracy
print(f"  [{time.time() - t0:.0f}s elapsed]")


# ==============================================================
# 3. CROSS-TALK MATRIX
# ==============================================================
print("\n" + "=" * 60)
print("3. CROSS-TALK: correlation between drive changes and mode responses")
print("=" * 60)

# For each axis (drive frequency), measure how much each mode band responds
# Cross-talk = how much does changing axis_i affect modes in band_j?
n_pages = 4
page_size = len(mode_indices) // n_pages

# Compute: for each axis, what's the variance explained in each band?
crosstalk = np.zeros((naxes, n_pages))
AXES = ['x', 'y', 'vx', 'vy']

for ai in range(naxes):
    # Get the axis variable
    if ai == 0: ax_val = xs
    elif ai == 1: ax_val = ys
    elif ai == 2: ax_val = vx
    else: ax_val = vy

    for p in range(n_pages):
        start = p * page_size
        end = (p + 1) * page_size if p < n_pages - 1 else len(mode_indices)
        idx = mode_indices[start:end]

        # Correlation between axis value and band features
        band_feats = X[:, idx]
        # Mean absolute correlation across band features
        corrs = []
        for f in range(band_feats.shape[1]):
            c = np.corrcoef(ax_val, band_feats[:, f])[0, 1]
            if np.isfinite(c):
                corrs.append(abs(c))
        crosstalk[ai, p] = np.mean(corrs) if corrs else 0

print(f"  Mean |correlation| between axis drive and mode band response:")
print(f"  {'Axis':<6s}" + "".join(f"  Band{p}" for p in range(n_pages)))
for ai in range(naxes):
    row = "  ".join(f"{crosstalk[ai, p]:.3f}" for p in range(n_pages))
    print(f"  {AXES[ai]:<6s}{row}")

# Cross-talk ratio: off-diagonal / on-diagonal
# Which band responds most to which axis?
results['crosstalk'] = {
    'axes': AXES,
    'n_pages': n_pages,
    'matrix': crosstalk.tolist(),
}


# ==============================================================
# 4. MULTI-PAGE CAPACITY: independent information per band
# ==============================================================
print("\n" + "=" * 60)
print("4. MULTI-PAGE CAPACITY (independent state info per band)")
print("=" * 60)

# For each band, how many distinct states can it discriminate?
# Test: predict (x, y, vx, vy) individually from each band
state_vars = {
    'x': xs, 'y': ys, 'vx': (vx > 0).astype(int), 'vy': (vy > 0).astype(int),
    'landing': L,
}

n_pages = 4
page_size = len(mode_indices) // n_pages

capacity = {}
print(f"  {'Band':<20s}" + "".join(f"  {v:>8s}" for v in state_vars))
for p in range(n_pages):
    start = p * page_size
    end = (p + 1) * page_size if p < n_pages - 1 else len(mode_indices)
    idx = mode_indices[start:end]
    freq_lo = freqs[start]; freq_hi = freqs[min(end-1, len(freqs)-1)]
    label = f"B{p}({freq_lo:.0f}-{freq_hi:.0f})"

    band_cap = {}
    vals = []
    for vname, vdata in state_vars.items():
        acc = loro_ridge(X[:, idx], vdata, groups)
        band_cap[vname] = round(acc, 1)
        vals.append(f"{acc:8.1f}")
    capacity[label] = band_cap
    print(f"  {label:<20s}" + "".join(vals))

# Also test all modes and axis-only
for tag, idx_set in [('ALL_MODES', mode_indices), ('AXIS_ONLY', np.arange(axis_block))]:
    vals = []
    cap = {}
    for vname, vdata in state_vars.items():
        acc = loro_ridge(X[:, idx_set], vdata, groups)
        cap[vname] = round(acc, 1)
        vals.append(f"{acc:8.1f}")
    capacity[tag] = cap
    print(f"  {tag:<20s}" + "".join(vals))

results['multi_page_capacity'] = capacity
print(f"  [{time.time() - t0:.0f}s elapsed]")


# ==============================================================
# 5. MULTITONE DATA: frequency-address isolation
# ==============================================================
if mt_files:
    print("\n" + "=" * 60)
    print("5. MULTITONE DATA: drive-frequency addressing")
    print("=" * 60)

    mt_results = {}
    for mf_path in mt_files[-2:]:  # use latest two
        md = np.load(mf_path)
        Y = md['Y']  # (256, 779)
        targets = md['targets']
        drive_freqs = md['drive_freqs']  # (256, 3)
        mode_freqs = md['mode_freqs']  # (767,)

        print(f"\n  File: {Path(mf_path).name}")
        print(f"  Y: {Y.shape}, {len(mode_freqs)} modes")

        # The 3 drive channels each address different frequency bands
        # Test: can we decode each drive channel independently?
        Y_norm = Y / (Y.mean(1, keepdims=True) + 1e-9)

        # Split modes into 3 bands matching the 3 drive channels
        n_modes = len(mode_freqs)
        drive_ranges = [
            (35000, 65000),   # ch0
            (70000, 100000),  # ch1
            (105000, 135000), # ch2
        ]

        file_res = {}
        for ch in range(3):
            lo, hi = drive_ranges[ch]
            band_mask = (mode_freqs >= lo) & (mode_freqs <= hi)
            n_in_band = band_mask.sum()

            # Features in this band
            # Y columns: first 12 are drive windows (4 per channel), rest are modes
            # Actually: Y has 779 cols = 12 drive + 767 modes
            n_drive_feats = Y.shape[1] - n_modes
            mode_start = n_drive_feats

            band_idx = np.where(band_mask)[0] + mode_start
            out_band_idx = np.where(~band_mask)[0] + mode_start

            # Quantize drive channel into levels for classification
            ch_vals = drive_freqs[:, ch]
            ch_levels = np.unique(ch_vals)
            ch_labels = np.searchsorted(ch_levels, ch_vals)

            # Classify drive-channel level from in-band vs out-band features
            if n_in_band > 0 and len(ch_levels) > 1:
                sc = StandardScaler()
                # Simple 70/30 split (no repeat structure in multitone data)
                n_tr = int(len(Y_norm) * 0.7)
                clf_in = RidgeClassifier(alpha=1.0)
                Xs = sc.fit_transform(Y_norm[:n_tr, band_idx])
                clf_in.fit(Xs, ch_labels[:n_tr])
                acc_in = np.mean(clf_in.predict(
                    sc.transform(Y_norm[n_tr:, band_idx])) == ch_labels[n_tr:]) * 100

                sc2 = StandardScaler()
                clf_out = RidgeClassifier(alpha=1.0)
                Xs2 = sc2.fit_transform(Y_norm[:n_tr, out_band_idx])
                clf_out.fit(Xs2, ch_labels[:n_tr])
                acc_out = np.mean(clf_out.predict(
                    sc2.transform(Y_norm[n_tr:, out_band_idx])) == ch_labels[n_tr:]) * 100

                print(f"  Ch{ch} ({lo/1000:.0f}-{hi/1000:.0f}kHz, "
                      f"{len(ch_levels)} levels, {n_in_band} in-band modes):")
                print(f"    in-band acc:  {acc_in:.1f}%")
                print(f"    out-band acc: {acc_out:.1f}% (cross-talk)")
                print(f"    isolation:    {acc_in - acc_out:+.1f}%")

                file_res[f'ch{ch}'] = {
                    'freq_range': [lo, hi],
                    'n_levels': len(ch_levels),
                    'n_in_band': int(n_in_band),
                    'in_band_acc': round(acc_in, 1),
                    'out_band_acc': round(acc_out, 1),
                    'isolation': round(acc_in - acc_out, 1),
                }

        mt_results[Path(mf_path).name] = file_res

    results['multitone_isolation'] = mt_results


# ==============================================================
# Save
# ==============================================================
out = Path('data/results/spectral_page_capacity.json')
json.dump(results, open(out, 'w'), indent=1)
print(f"\n{'=' * 60}")
print(f"Saved to {out}")
print(f"Total time: {time.time() - t0:.0f}s")
