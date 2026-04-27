#!/usr/bin/env python3
"""
NARMA-10 with Virtual Rewrite — Track A Temporal Memory

Applies the "firmware-defined virtual rewriting" concept from the
CWM rewritability advance paper (Track A, §H7–H9) to close the
temporal memory gap in NARMA-10 on glass plates.

THE PROBLEM
-----------
Plate modes decay in 0.4–2.1 ms; NARMA steps are 17 ms apart at 58 Hz.
Zero physical memory between steps.  The current best (ladder_resid_esn
= 0.170) relies on a software ESN to provide temporal state.  The plate
contributes nonlinear mixing but no memory.

THE INSIGHT FROM TRACK A
-------------------------
Track A showed that changing the *excitation configuration* creates a
new "virtual device" — the SAME rod, a DIFFERENT logical memory.

Applied to NARMA:  encoding ŷ(t) on an 11th carrier makes each step's
excitation a DIFFERENT virtual device.  The plate's IM products between
the feedback carrier and input carriers physically compute:

    ŷ(t) × u(t-i)    — the exact cross-terms NARMA-10 needs.

THE FIX TO THE BROKEN FEEDBACK
-------------------------------
The original run_closed_loop adds y_fb as a raw scalar feature.
Ridge regression trivially learns y(t+1) ≈ 0.3·y(t), getting NMSE=0
open-loop but diverging to NMSE=1.85 closed-loop.

Virtual rewrite fix:
  1. NEVER hand the model the raw ŷ(t) value.
  2. ŷ(t) modulates ONLY the 11th carrier amplitude.
  3. The model MUST extract y-information from IM products in the
     spectrum — the plate's lossy, nonlinear mixing prevents trivial
     copying and adds natural regularization.

Usage:
  python tools/narma_virtual_rewrite.py --simulate --steps 3000
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

TOOLS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS_DIR))
ROOT = TOOLS_DIR.parent
RESULTS_DIR = ROOT / "data" / "results" / "lab" / "plate_exps" / "narma10"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# ═══════════════════════════════════════════════════════════════════════
#  Constants
# ═══════════════════════════════════════════════════════════════════════

NARMA_ORDER = 10
N_WASHOUT = 50
RIDGE_ALPHAS = [0.001, 0.01, 0.1, 1.0, 10.0, 100.0]

LADDER_CARRIERS_HZ = [
    19_000, 23_900, 29_200, 29_900, 34_550,
    37_000, 45_000, 49_600, 56_200, 58_500,
]

# 53.9 kHz: best IM coverage — 26 IM hits on 19 unique mode landings.
# (11.4 kHz only gives 12 hits on 12 modes.)
FEEDBACK_FREQ = 53_900

MODE_CLUSTERS_HZ = [
    11_425, 15_100, 16_000, 17_375, 19_000, 23_900, 29_200, 29_900,
    31_600, 33_225, 34_550, 36_000, 37_000, 42_300, 45_000, 47_800,
    49_600, 51_500, 53_900, 56_200, 58_500, 62_000, 65_075, 68_200,
    70_800, 73_500, 76_200, 78_800, 81_500, 84_200, 86_900, 89_400,
    95_000,
]

DEFAULT_Q = 200
NL_STRENGTH = 0.15
NOISE_FLOOR = 50.0


def log(msg):
    print(msg, flush=True)


# ═══════════════════════════════════════════════════════════════════════
#  NARMA-10 generator
# ═══════════════════════════════════════════════════════════════════════

def generate_narma10(n_steps, rng):
    u = rng.uniform(0, 0.5, n_steps)
    y = np.zeros(n_steps)
    for t in range(NARMA_ORDER, n_steps - 1):
        y_sum = np.sum(y[t - 9:t + 1])
        y[t + 1] = (0.3 * y[t]
                     + 0.05 * y[t] * y_sum
                     + 1.5 * u[t - 9] * u[t]
                     + 0.1)
    return u, y


# ═══════════════════════════════════════════════════════════════════════
#  Readout frequency computation
# ═══════════════════════════════════════════════════════════════════════

def compute_readout_freqs(carriers, all_modes, nyquist=390_000):
    IM_TOL = 0.02
    readout, labels, im_map = [], [], []
    seen = set()

    for f in all_modes:
        readout.append(f)
        ci = None
        for idx, cf in enumerate(carriers):
            if abs(f - cf) / max(f, cf) < 0.02:
                ci = idx
                break
        labels.append(f"carrier_{ci}" if ci is not None else f"mode_{f/1000:.1f}k")
        im_map.append((ci if ci is not None else -1,
                        ci if ci is not None else -1,
                        "self" if ci is not None else "ambient"))
        seen.add(f)

    for i in range(len(carriers)):
        for j in range(i + 1, len(carriers)):
            fi, fj = carriers[i], carriers[j]
            for im_f, im_type in [(abs(fi - fj), "IM2d"), (fi + fj, "IM2s")]:
                if im_f < 1000 or im_f > nyquist:
                    continue
                for mf in all_modes:
                    if abs(im_f - mf) / max(im_f, mf) < IM_TOL:
                        if mf not in seen:
                            readout.append(mf)
                            labels.append(f"{im_type}_{i}x{j}")
                            im_map.append((i, j, im_type))
                            seen.add(mf)
                        break

    for i in range(len(carriers)):
        for j in range(len(carriers)):
            if i == j:
                continue
            f3 = abs(2 * carriers[i] - carriers[j])
            if f3 < 1000 or f3 > nyquist:
                continue
            for mf in all_modes:
                if abs(f3 - mf) / max(f3, mf) < IM_TOL:
                    if mf not in seen:
                        readout.append(mf)
                        labels.append(f"IM3_{i}x{j}")
                        im_map.append((i, j, "IM3"))
                        seen.add(mf)
                    break

    return readout, labels, im_map


# ═══════════════════════════════════════════════════════════════════════
#  Vectorized plate simulator
# ═══════════════════════════════════════════════════════════════════════

def _lorentzian_matrix(freqs, mode_freqs, mode_Qs):
    """(n_freqs, n_modes) Lorentzian gain matrix."""
    f = np.asarray(freqs, dtype=np.float64).reshape(-1, 1)
    mf = np.asarray(mode_freqs, dtype=np.float64).reshape(1, -1)
    mQ = np.asarray(mode_Qs, dtype=np.float64).reshape(1, -1)
    bw = mf / (2 * mQ)
    return bw**2 / ((f - mf)**2 + bw**2)


class PlateSimulator:
    """Pre-computes Lorentzian matrices for fast repeated calls."""

    def __init__(self, carriers, readout_freqs, mode_freqs,
                 mode_Qs=None, nl_strength=NL_STRENGTH):
        if mode_Qs is None:
            mode_Qs = [DEFAULT_Q] * len(mode_freqs)
        self.n_carriers = len(carriers)
        self.n_readout = len(readout_freqs)
        self.nl = nl_strength
        self.mQ = np.asarray(mode_Qs, dtype=np.float64)

        self.drive_L = _lorentzian_matrix(carriers, mode_freqs, mode_Qs)
        self.read_L = _lorentzian_matrix(readout_freqs, mode_freqs, mode_Qs)
        self.read_mQ1000 = self.read_L * (self.mQ * 1000)  # precompute

        # IM frequencies: all carrier pairs → sum and diff
        c = np.asarray(carriers, dtype=np.float64)
        im_freqs, im_pairs = [], []
        for i in range(len(c)):
            for k in range(i + 1, len(c)):
                im_freqs.extend([c[i] + c[k], abs(c[i] - c[k])])
                im_pairs.extend([(i, k), (i, k)])
        self.im_pairs = im_pairs
        if im_freqs:
            im_drive = _lorentzian_matrix(im_freqs, mode_freqs, mode_Qs)
            self.im_read_mQ = im_drive * (self.mQ * 1000)  # (n_im, M)
        else:
            self.im_read_mQ = np.zeros((0, len(mode_freqs)))

    def __call__(self, amplitudes, rng=None):
        amps = np.asarray(amplitudes, dtype=np.float64)

        # Linear: each carrier excites modes, read at each readout freq
        mode_exc = (self.drive_L * amps[:, None]).sum(axis=0)  # (M,)
        mags = self.read_mQ1000 @ mode_exc  # (R,) — matrix-vector, not sum

        # Correction: read_mQ1000 is (R, M), mode_exc is (M,)
        # result is (R,) — dot product per readout freq. ✓

        # IM: quadratic mixing
        if self.im_pairs:
            im_amps = np.array([amps[i] * amps[k]
                                for i, k in self.im_pairs])
            mask = im_amps > 0
            if mask.any():
                im_exc = (self.im_read_mQ[mask] * im_amps[mask, None]).sum(axis=0)
                mags += self.nl * (self.read_L * (im_exc * self.mQ * 1000)).sum(axis=1)

        if rng is not None:
            mags += rng.normal(0, NOISE_FLOOR, self.n_readout)
        return np.abs(mags)


# ═══════════════════════════════════════════════════════════════════════
#  Feature collection
# ═══════════════════════════════════════════════════════════════════════

def collect_features(u, y_true, sim, n_total, start,
                     feedback_mode="none", y_hat_prev=None,
                     sampling_schedule=None, rng=None):
    """Collect per-step features. NO raw y_fb appended."""
    use_fb = feedback_mode != "none"
    X = np.zeros((n_total, sim.n_readout))

    for idx in range(n_total):
        t = start + idx
        if t < NARMA_ORDER:
            continue
        window = u[t - 9:t + 1]
        amps = list(window * 2.0)

        if use_fb:
            if feedback_mode == "teacher":
                y_fb = np.clip(y_true[t], 0, 2) / 2.0
            elif feedback_mode == "predicted":
                y_fb = np.clip(y_hat_prev[idx] if y_hat_prev is not None else 0,
                               0, 2) / 2.0
            elif feedback_mode == "scheduled":
                p = sampling_schedule[idx] if sampling_schedule is not None else 1.0
                if rng.random() < p:
                    y_fb = np.clip(y_true[t], 0, 2) / 2.0
                else:
                    y_fb = np.clip(
                        y_hat_prev[idx] if y_hat_prev is not None else 0,
                        0, 2) / 2.0
            amps.append(y_fb)

        X[idx] = sim(amps, rng=rng)
    return X


# ═══════════════════════════════════════════════════════════════════════
#  Evaluation helpers
# ═══════════════════════════════════════════════════════════════════════

def nmse(y_true, y_pred):
    var = np.var(y_true)
    return float(np.mean((y_true - y_pred) ** 2) / var) if var > 0 else float('inf')


def train_ridge(X_train, y_train):
    from sklearn.model_selection import KFold
    scaler = StandardScaler()
    X_s = scaler.fit_transform(X_train)
    best_alpha, best_cv = 1.0, float('inf')
    kf = KFold(n_splits=5, shuffle=False)
    for alpha in RIDGE_ALPHAS:
        scores = []
        for tr, va in kf.split(X_s):
            reg = Ridge(alpha=alpha)
            reg.fit(X_s[tr], y_train[tr])
            scores.append(nmse(y_train[va], reg.predict(X_s[va])))
        m = np.mean(scores)
        if m < best_cv:
            best_cv, best_alpha = m, alpha
    reg = Ridge(alpha=best_alpha)
    reg.fit(X_s, y_train)
    return reg, scaler, best_alpha


def eval_ridge(reg, scaler, X_train, y_train, X_test, y_test, name):
    return {
        "name": name,
        "nmse_train": round(nmse(y_train, reg.predict(scaler.transform(X_train))), 6),
        "nmse_test": round(nmse(y_test, reg.predict(scaler.transform(X_test))), 6),
        "features": X_train.shape[1],
    }


def run_esn(X_input, y_train, y_test, n_train, name, rng, hidden=64):
    W_in = rng.uniform(-0.1, 0.1, (hidden, X_input.shape[1]))
    W_res = rng.normal(0, 1, (hidden, hidden))
    W_res *= 0.9 / np.max(np.abs(np.linalg.eigvals(W_res)))
    leak = 0.5
    X_esn = np.zeros((len(X_input), hidden))
    state = np.zeros(hidden)
    for i in range(len(X_input)):
        pre = np.tanh(W_in @ X_input[i] + W_res @ state)
        state = (1 - leak) * state + leak * pre
        X_esn[i] = state
    reg, sc, alpha = train_ridge(X_esn[:n_train], y_train)
    return eval_ridge(reg, sc, X_esn[:n_train], y_train,
                      X_esn[n_train:], y_test, name)


def svd_project(X, n_components=None):
    from sklearn.decomposition import TruncatedSVD
    if n_components is None:
        full = TruncatedSVD(n_components=min(X.shape) - 1)
        full.fit(X)
        cumvar = np.cumsum(full.explained_variance_ratio_)
        n_components = max(10, min(int(np.searchsorted(cumvar, 0.99)) + 1,
                                   X.shape[1] // 2))
    svd = TruncatedSVD(n_components=n_components)
    return svd.fit_transform(X), svd, n_components


# ═══════════════════════════════════════════════════════════════════════
#  Main experiment
# ═══════════════════════════════════════════════════════════════════════

def run_experiment(args):
    rng = np.random.default_rng(args.seed)
    log("=== NARMA-10 Virtual Rewrite Experiment ===")
    log(f"Steps: {args.steps}  Seed: {args.seed}")
    log(f"Feedback carrier: {FEEDBACK_FREQ/1000:.1f} kHz")

    # ── Generate NARMA data ──
    u, y = generate_narma10(args.steps, rng)
    start = NARMA_ORDER + N_WASHOUT
    total = args.steps - start - 1
    n_train = int(total * 0.7)
    n_test = total - n_train
    y_all = y[start:start + total]
    y_tr, y_te = y_all[:n_train], y_all[n_train:]
    log(f"Data: {total} usable ({n_train} train / {n_test} test)")

    # ── Readout frequencies ──
    c10 = list(LADDER_CARRIERS_HZ)
    c11 = c10 + [FEEDBACK_FREQ]
    r10, _, _ = compute_readout_freqs(c10, MODE_CLUSTERS_HZ)
    r11, _, _ = compute_readout_freqs(c11, MODE_CLUSTERS_HZ)
    log(f"Readout: {len(r10)} (10-carrier), {len(r11)} (11-carrier)")
    log(f"Feedback adds {len(r11) - len(r10)} new IM readout channels")

    # ── Build simulators (vectorized — fast) ──
    t0 = time.time()
    sim10 = PlateSimulator(c10, r10, MODE_CLUSTERS_HZ)
    sim11 = PlateSimulator(c11, r11, MODE_CLUSTERS_HZ)
    log(f"Simulators ready ({time.time()-t0:.2f}s)")

    # Shared input-window features
    win = np.array([u[start + i - 9:start + i + 1] for i in range(total)])
    results = []

    # ══════════════════════════════════════════════════════════════════
    #  A. Baseline: No feedback (10 carriers)
    # ══════════════════════════════════════════════════════════════════
    log("\n─── A. No Feedback (baseline) ───")
    t0 = time.time()
    X_nf = collect_features(u, y, sim10, total, start,
                            feedback_mode="none", rng=rng)
    log(f"  {total} spectra in {time.time()-t0:.1f}s")

    # A1: spectrum only
    reg, sc, al = train_ridge(X_nf[:n_train], y_tr)
    r = eval_ridge(reg, sc, X_nf[:n_train], y_tr, X_nf[n_train:], y_te,
                   "A1_no_feedback_spectrum")
    r["best_alpha"] = al
    results.append(r)
    log(f"  A1 spectrum-only:       NMSE = {r['nmse_test']:.4f}")

    # A2: spectrum + window
    X_nfw = np.hstack([X_nf, win])
    reg, sc, al = train_ridge(X_nfw[:n_train], y_tr)
    r = eval_ridge(reg, sc, X_nfw[:n_train], y_tr, X_nfw[n_train:], y_te,
                   "A2_no_feedback_spec_window")
    r["best_alpha"] = al
    results.append(r)
    log(f"  A2 spectrum + window:   NMSE = {r['nmse_test']:.4f}")

    # A3: software ESN baseline
    r = run_esn(win, y_tr, y_te, n_train, "A3_software_esn", rng)
    results.append(r)
    log(f"  A3 software ESN:        NMSE = {r['nmse_test']:.4f}")

    # A4: plate→ESN (no feedback)
    r = run_esn(X_nf, y_tr, y_te, n_train, "A4_plate_esn_no_fb", rng)
    results.append(r)
    log(f"  A4 plate→ESN:           NMSE = {r['nmse_test']:.4f}")

    # ══════════════════════════════════════════════════════════════════
    #  B. Broken Baseline: Raw y_fb feature
    # ══════════════════════════════════════════════════════════════════
    log("\n─── B. Raw Feedback (broken baseline) ───")
    t0 = time.time()
    X_tf = collect_features(u, y, sim11, total, start,
                            feedback_mode="teacher", rng=rng)
    log(f"  Collected in {time.time()-t0:.1f}s")

    y_fb_raw = np.array([np.clip(y[start + i], 0, 2) / 2.0
                         for i in range(total)]).reshape(-1, 1)
    X_brk = np.hstack([X_tf, win, y_fb_raw])
    reg_b, sc_b, al = train_ridge(X_brk[:n_train], y_tr)
    r = eval_ridge(reg_b, sc_b, X_brk[:n_train], y_tr,
                   X_brk[n_train:], y_te, "B1_raw_fb_openloop")
    r["best_alpha"] = al
    results.append(r)
    log(f"  B1 open-loop (teacher): NMSE = {r['nmse_test']:.4f}")
    log(f"     (Near-zero = model copies y_fb)")

    # B2: closed-loop — will diverge
    yp = np.zeros(total)
    yp[:n_train] = reg_b.predict(sc_b.transform(X_brk[:n_train]))
    for idx in range(n_train, total):
        t = start + idx
        w = u[t-9:t+1]
        yfb = np.clip(yp[idx-1], 0, 2) / 2.0
        spec = sim11(list(w * 2.0) + [yfb], rng=rng)
        feat = np.concatenate([spec, w, [yfb]])
        yp[idx] = reg_b.predict(sc_b.transform(feat.reshape(1,-1)))[0]
    nm = nmse(y_te, yp[n_train:])
    results.append({"name": "B2_raw_fb_closedloop",
                    "nmse_test": round(nm, 6), "features": X_brk.shape[1]})
    log(f"  B2 closed-loop:         NMSE = {nm:.4f}  ← diverges")

    # ══════════════════════════════════════════════════════════════════
    #  C. Virtual Rewrite: IM-only feedback (THE FIX)
    # ══════════════════════════════════════════════════════════════════
    log("\n─── C. Virtual Rewrite: IM-Only Feedback ───")
    log("  ŷ(t) on 11th carrier ONLY — no raw feature")
    t0 = time.time()

    # Teacher-forced collection (reuse X_tf which has 11-carrier teacher)
    X_im = X_tf  # spectrum already captured with teacher y on carrier 11
    log(f"  (reusing teacher capture from B)")

    # C1: open-loop
    X_imw = np.hstack([X_im, win])
    reg_c, sc_c, al = train_ridge(X_imw[:n_train], y_tr)
    r = eval_ridge(reg_c, sc_c, X_imw[:n_train], y_tr,
                   X_imw[n_train:], y_te, "C1_im_fb_openloop")
    r["best_alpha"] = al
    results.append(r)
    log(f"  C1 open-loop (teacher): NMSE = {r['nmse_test']:.4f}")

    # C2: closed-loop
    log("  C2: closed-loop inference...")
    yp_c = np.zeros(total)
    yp_c[:n_train] = reg_c.predict(sc_c.transform(X_imw[:n_train]))
    for idx in range(n_train, total):
        t = start + idx
        w = u[t-9:t+1]
        yfb = np.clip(yp_c[idx-1], 0, 2) / 2.0
        spec = sim11(list(w * 2.0) + [yfb], rng=rng)
        feat = np.concatenate([spec, w])
        yp_c[idx] = reg_c.predict(sc_c.transform(feat.reshape(1,-1)))[0]
    nm = nmse(y_te, yp_c[n_train:])
    results.append({"name": "C2_im_fb_closedloop",
                    "nmse_test": round(nm, 6),
                    "features": X_imw.shape[1]})
    log(f"  C2 closed-loop:         NMSE = {nm:.4f}  ← virtual rewrite")

    # ══════════════════════════════════════════════════════════════════
    #  D. IM Feedback + Scheduled Sampling
    # ══════════════════════════════════════════════════════════════════
    log("\n─── D. IM Feedback + Scheduled Sampling ───")
    log("  3-pass: teacher → scheduled → closed-loop")

    # Pass 1: initial model from teacher capture
    reg_d, sc_d, _ = train_ridge(X_imw[:n_train], y_tr)
    yhat1 = np.zeros(total)
    yhat1[:n_train] = reg_d.predict(sc_d.transform(X_imw[:n_train]))

    # Closed-loop training predictions
    for idx in range(n_train):
        t = start + idx
        w = u[t-9:t+1]
        yfb = 0 if idx == 0 else np.clip(yhat1[idx-1], 0, 2) / 2.0
        spec = sim11(list(w * 2.0) + [yfb], rng=rng)
        feat = np.concatenate([spec, w])
        yhat1[idx] = reg_d.predict(sc_d.transform(feat.reshape(1,-1)))[0]

    # Pass 2: scheduled sampling p: 1.0 → 0.2
    log("  Pass 2: scheduled sampling...")
    sched = np.concatenate([np.linspace(1.0, 0.2, n_train),
                            np.full(n_test, 0.0)])
    X_sch = collect_features(u, y, sim11, total, start,
                             feedback_mode="scheduled",
                             y_hat_prev=yhat1,
                             sampling_schedule=sched, rng=rng)
    X_schw = np.hstack([X_sch, win])
    reg_d2, sc_d2, al = train_ridge(X_schw[:n_train], y_tr)

    # Pass 3: closed-loop eval
    log("  Pass 3: closed-loop eval...")
    yp_d = np.zeros(total)
    yp_d[:n_train] = reg_d2.predict(sc_d2.transform(X_schw[:n_train]))
    for idx in range(n_train, total):
        t = start + idx
        w = u[t-9:t+1]
        yfb = np.clip(yp_d[idx-1], 0, 2) / 2.0
        spec = sim11(list(w * 2.0) + [yfb], rng=rng)
        feat = np.concatenate([spec, w])
        yp_d[idx] = reg_d2.predict(sc_d2.transform(feat.reshape(1,-1)))[0]
    nm = nmse(y_te, yp_d[n_train:])
    results.append({"name": "D_scheduled_closedloop",
                    "nmse_test": round(nm, 6),
                    "features": X_schw.shape[1],
                    "best_alpha": al})
    log(f"  D closed-loop:          NMSE = {nm:.4f}  ← scheduled")

    # ══════════════════════════════════════════════════════════════════
    #  E. IM Feedback + SVD (Track A, H7)
    # ══════════════════════════════════════════════════════════════════
    log("\n─── E. IM Feedback + SVD Projection (H7) ───")
    X_svd, svd_m, nc = svd_project(X_im)
    log(f"  SVD: {X_im.shape[1]} → {nc} components")
    X_svdw = np.hstack([X_svd, win])
    reg_e, sc_e, al = train_ridge(X_svdw[:n_train], y_tr)
    r = eval_ridge(reg_e, sc_e, X_svdw[:n_train], y_tr,
                   X_svdw[n_train:], y_te, "E1_svd_openloop")
    r["best_alpha"] = al
    results.append(r)
    log(f"  E1 SVD open-loop:       NMSE = {r['nmse_test']:.4f}")

    # E2: SVD closed-loop
    yp_e = np.zeros(total)
    yp_e[:n_train] = reg_e.predict(sc_e.transform(X_svdw[:n_train]))
    for idx in range(n_train, total):
        t = start + idx
        w = u[t-9:t+1]
        yfb = np.clip(yp_e[idx-1], 0, 2) / 2.0
        spec = sim11(list(w * 2.0) + [yfb], rng=rng)
        sp_svd = svd_m.transform(spec.reshape(1,-1))[0]
        feat = np.concatenate([sp_svd, w])
        yp_e[idx] = reg_e.predict(sc_e.transform(feat.reshape(1,-1)))[0]
    nm = nmse(y_te, yp_e[n_train:])
    results.append({"name": "E2_svd_closedloop",
                    "nmse_test": round(nm, 6),
                    "features": X_svdw.shape[1]})
    log(f"  E2 SVD closed-loop:     NMSE = {nm:.4f}")

    # ══════════════════════════════════════════════════════════════════
    #  F. IM Feedback + ESN
    # ══════════════════════════════════════════════════════════════════
    log("\n─── F. IM Feedback + ESN ───")
    r = run_esn(X_im, y_tr, y_te, n_train, "F1_im_fb_esn", rng)
    results.append(r)
    log(f"  F1 plate(+fb)→ESN:      NMSE = {r['nmse_test']:.4f}")

    # F2: Template residual approach (what works on hardware)
    # Bin inputs into 10 buckets, compute mean template per bucket,
    # subtract → residual captures nonlinear deviations
    log("  F2: Template residual + feedback ESN...")
    n_bins = 10
    u_current = np.array([u[start + i] for i in range(total)])
    bin_edges = np.linspace(0, 0.5, n_bins + 1)
    bin_idx = np.digitize(u_current, bin_edges) - 1
    bin_idx = np.clip(bin_idx, 0, n_bins - 1)
    templates = np.zeros((n_bins, X_im.shape[1]))
    for b in range(n_bins):
        mask = (bin_idx[:n_train] == b)
        if mask.any():
            templates[b] = X_im[:n_train][mask].mean(axis=0)
    X_resid = X_im - templates[bin_idx]
    r = run_esn(X_resid, y_tr, y_te, n_train, "F2_resid_fb_esn", rng)
    results.append(r)
    log(f"  F2 resid(+fb)→ESN:      NMSE = {r['nmse_test']:.4f}")

    # F3: No-feedback residual → ESN (to compare)
    templates_nf = np.zeros((n_bins, X_nf.shape[1]))
    for b in range(n_bins):
        mask = (bin_idx[:n_train] == b)
        if mask.any():
            templates_nf[b] = X_nf[:n_train][mask].mean(axis=0)
    X_resid_nf = X_nf - templates_nf[bin_idx]
    r = run_esn(X_resid_nf, y_tr, y_te, n_train, "F3_resid_nofb_esn", rng)
    results.append(r)
    log(f"  F3 resid(no fb)→ESN:    NMSE = {r['nmse_test']:.4f}")

    # F4: Concat [spectrum, residual, window] → ESN
    X_concat = np.hstack([X_im, X_resid, win])
    r = run_esn(X_concat, y_tr, y_te, n_train, "F4_concat_fb_esn", rng)
    results.append(r)
    log(f"  F4 concat(+fb)→ESN:     NMSE = {r['nmse_test']:.4f}")

    # ══════════════════════════════════════════════════════════════════
    #  G. Reduced Feedback Amplitude (attenuate error propagation)
    #     Key idea: scale y_fb by 0.2 so spectrum is 80% u-driven.
    #     IM products still carry y×u info but errors have less impact.
    # ══════════════════════════════════════════════════════════════════
    log("\n─── G. Reduced Feedback Amplitude ───")
    for fb_scale in [0.1, 0.2, 0.5]:
        log(f"  Testing fb_scale={fb_scale}...")
        # Teacher capture with scaled feedback
        X_gs = np.zeros((total, sim11.n_readout))
        for idx in range(total):
            t = start + idx
            if t < NARMA_ORDER:
                continue
            w = u[t-9:t+1]
            yfb = np.clip(y[t], 0, 2) / 2.0 * fb_scale
            X_gs[idx] = sim11(list(w * 2.0) + [yfb], rng=rng)

        X_gsw = np.hstack([X_gs, win])
        reg_g, sc_g, al = train_ridge(X_gsw[:n_train], y_tr)
        r_ol = eval_ridge(reg_g, sc_g, X_gsw[:n_train], y_tr,
                          X_gsw[n_train:], y_te,
                          f"G_fb{fb_scale}_openloop")
        results.append(r_ol)
        log(f"    open-loop:  NMSE = {r_ol['nmse_test']:.4f}")

        # Closed-loop with same scale
        yp_g = np.zeros(total)
        yp_g[:n_train] = reg_g.predict(sc_g.transform(X_gsw[:n_train]))
        for idx in range(n_train, total):
            t = start + idx
            w = u[t-9:t+1]
            yfb = np.clip(yp_g[idx-1], 0, 2) / 2.0 * fb_scale
            spec = sim11(list(w * 2.0) + [yfb], rng=rng)
            feat = np.concatenate([spec, w])
            yp_g[idx] = reg_g.predict(sc_g.transform(feat.reshape(1,-1)))[0]
        nm = nmse(y_te, yp_g[n_train:])
        results.append({"name": f"G_fb{fb_scale}_closedloop",
                        "nmse_test": round(nm, 6),
                        "features": X_gsw.shape[1]})
        log(f"    closed-loop: NMSE = {nm:.4f}")

    # ══════════════════════════════════════════════════════════════════
    #  H. Exponential smoothing on predictions
    #     Damp oscillations: ŷ_smooth = α·ŷ_new + (1-α)·ŷ_prev
    # ══════════════════════════════════════════════════════════════════
    log("\n─── H. Prediction Smoothing ───")
    for smooth_alpha in [0.3, 0.5, 0.7]:
        yp_h = np.zeros(total)
        yp_h[:n_train] = reg_c.predict(sc_c.transform(X_imw[:n_train]))
        for idx in range(n_train, total):
            t = start + idx
            w = u[t-9:t+1]
            yfb = np.clip(yp_h[idx-1], 0, 2) / 2.0
            spec = sim11(list(w * 2.0) + [yfb], rng=rng)
            feat = np.concatenate([spec, w])
            raw_pred = reg_c.predict(sc_c.transform(feat.reshape(1,-1)))[0]
            yp_h[idx] = smooth_alpha * raw_pred + (1 - smooth_alpha) * yp_h[idx-1]
        nm = nmse(y_te, yp_h[n_train:])
        results.append({"name": f"H_smooth_{smooth_alpha}_closedloop",
                        "nmse_test": round(nm, 6),
                        "features": X_imw.shape[1]})
        log(f"  α={smooth_alpha}: NMSE = {nm:.4f}")

    # ══════════════════════════════════════════════════════════════════
    #  I. Best combo: reduced amplitude + smoothing + scheduled
    # ══════════════════════════════════════════════════════════════════
    log("\n─── I. Combined: scale=0.2, smooth=0.5, scheduled ───")
    FB_SCALE_I = 0.2
    SMOOTH_I = 0.5

    # Pass 1: teacher with reduced amplitude
    X_i1 = np.zeros((total, sim11.n_readout))
    for idx in range(total):
        t = start + idx
        if t < NARMA_ORDER:
            continue
        w = u[t-9:t+1]
        yfb = np.clip(y[t], 0, 2) / 2.0 * FB_SCALE_I
        X_i1[idx] = sim11(list(w * 2.0) + [yfb], rng=rng)
    X_i1w = np.hstack([X_i1, win])
    reg_i1, sc_i1, _ = train_ridge(X_i1w[:n_train], y_tr)
    yhat_i = np.zeros(total)
    yhat_i[:n_train] = reg_i1.predict(sc_i1.transform(X_i1w[:n_train]))

    # CL predictions for training
    for idx in range(n_train):
        t = start + idx
        w = u[t-9:t+1]
        yfb = 0 if idx == 0 else np.clip(yhat_i[idx-1], 0, 2) / 2.0 * FB_SCALE_I
        spec = sim11(list(w * 2.0) + [yfb], rng=rng)
        feat = np.concatenate([spec, w])
        raw = reg_i1.predict(sc_i1.transform(feat.reshape(1,-1)))[0]
        yhat_i[idx] = SMOOTH_I * raw + (1-SMOOTH_I) * (yhat_i[idx-1] if idx > 0 else 0)

    # Pass 2: scheduled
    sched_i = np.concatenate([np.linspace(1.0, 0.1, n_train),
                              np.full(n_test, 0.0)])
    X_i2 = np.zeros((total, sim11.n_readout))
    for idx in range(total):
        t = start + idx
        if t < NARMA_ORDER:
            continue
        w = u[t-9:t+1]
        if rng.random() < sched_i[idx]:
            yfb = np.clip(y[t], 0, 2) / 2.0 * FB_SCALE_I
        else:
            yfb = np.clip(yhat_i[idx], 0, 2) / 2.0 * FB_SCALE_I
        X_i2[idx] = sim11(list(w * 2.0) + [yfb], rng=rng)
    X_i2w = np.hstack([X_i2, win])
    reg_i2, sc_i2, al = train_ridge(X_i2w[:n_train], y_tr)

    # Final closed-loop eval
    yp_i = np.zeros(total)
    yp_i[:n_train] = reg_i2.predict(sc_i2.transform(X_i2w[:n_train]))
    for idx in range(n_train, total):
        t = start + idx
        w = u[t-9:t+1]
        yfb = np.clip(yp_i[idx-1], 0, 2) / 2.0 * FB_SCALE_I
        spec = sim11(list(w * 2.0) + [yfb], rng=rng)
        feat = np.concatenate([spec, w])
        raw = reg_i2.predict(sc_i2.transform(feat.reshape(1,-1)))[0]
        yp_i[idx] = SMOOTH_I * raw + (1-SMOOTH_I) * yp_i[idx-1]
    nm = nmse(y_te, yp_i[n_train:])
    results.append({"name": "I_combined_closedloop",
                    "nmse_test": round(nm, 6),
                    "features": X_i2w.shape[1],
                    "fb_scale": FB_SCALE_I, "smooth": SMOOTH_I})
    log(f"  I combined closed-loop: NMSE = {nm:.4f}")

    # ══════════════════════════════════════════════════════════════════
    #  Summary
    # ══════════════════════════════════════════════════════════════════
    log("\n" + "═" * 62)
    log("  RESULTS SUMMARY — Virtual Rewrite for NARMA-10")
    log("═" * 62)
    log(f"  {'Approach':<33s} {'NMSE':>8s}  Notes")
    log("  " + "─" * 58)
    for r in results:
        n = r["name"]
        te = r.get("nmse_test", float('inf'))
        note = ""
        if "raw_fb" in n and "closed" in n:
            note = "← DIVERGES"
        elif "no_feedback" in n and "esn" not in n:
            note = "← no temporal memory"
        elif "software_esn" in n:
            note = "← software only"
        elif "im_fb_closedloop" in n:
            note = "← VIRTUAL REWRITE"
        elif "scheduled" in n:
            note = "← stabilized"
        elif "svd" in n and "closed" in n:
            note = "← H7 projection"
        elif n.startswith("F"):
            note = "← IM + ESN"
        log(f"  {n:<33s} {te:>8.4f}  {note}")

    # Key deltas
    nf = next((r for r in results if "A1" in r["name"]), None)
    esn = next((r for r in results if "A3" in r["name"]), None)
    c2 = next((r for r in results if "C2" in r["name"]), None)
    f_ = next((r for r in results if r["name"].startswith("F")), None)
    if nf and c2:
        log(f"\n  IM feedback vs no feedback: "
            f"{nf['nmse_test']:.4f} → {c2['nmse_test']:.4f} "
            f"(Δ = {nf['nmse_test'] - c2['nmse_test']:+.4f})")
    if esn and f_:
        log(f"  IM+ESN vs software ESN:     "
            f"{esn['nmse_test']:.4f} → {f_['nmse_test']:.4f} "
            f"(Δ = {esn['nmse_test'] - f_['nmse_test']:+.4f})")

    # ── Save ──
    output = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "script": "narma_virtual_rewrite.py",
        "concept": "Track A virtual rewriting for NARMA-10 temporal memory",
        "steps": args.steps, "seed": args.seed, "simulate": True,
        "carriers_10": c10, "carriers_11": c11,
        "feedback_freq_hz": FEEDBACK_FREQ,
        "n_readout_10": len(r10), "n_readout_11": len(r11),
        "n_new_im_channels": len(r11) - len(r10),
        "n_train": n_train, "n_test": n_test,
        "results": results,
    }
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    outfile = RESULTS_DIR / f"narma10_virtual_rewrite_{ts}.json"
    with open(outfile, "w") as f:
        json.dump(output, f, indent=2)
    log(f"\nSaved → {outfile}")
    return output


def main():
    parser = argparse.ArgumentParser(
        description="NARMA-10 with Track A Virtual Rewrite feedback")
    parser.add_argument("--steps", type=int, default=3000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--simulate", action="store_true", default=True)
    args = parser.parse_args()
    run_experiment(args)


if __name__ == "__main__":
    main()
