#!/usr/bin/env python3
"""
Phase 1.6 Step 4: Re-Excitation Interference (E33 Plate Revisit)
═════════════════════════════════════════════════════════════════

The Big Test: Does coherent phononic memory persist in fused silica plates?

Protocol:
  1. Drive plate mode to CW steady state (0.5 s)
  2. Stop AWG
  3. Wait delay Δt
  4. Re-excite (CW) and capture after short settle
  5. Measure amplitude at mode frequency via I/Q demodulation
  6. Repeat across delays spanning 0 → 10τ

If residual vibration from step 2 persists through the delay and interferes
with the new excitation in step 4, the measured amplitude will differ from
the fully-decayed (Δt → ∞) baseline.

Rod E33 result:  0.27% contrast at Q ≈ 400
Plate prediction: >5% contrast at Q ≈ 3,000–40,000

Additionally runs a RESIDUAL-ONLY control: same protocol but no re-excitation
in step 4 — just capture after the delay to directly observe the free ringdown
amplitude at each delay point.

Usage:
  python tools/plate_reexcitation.py /dev/cu.usbserial-11310
  python tools/plate_reexcitation.py /dev/cu.usbserial-11310 --fast
  python tools/plate_reexcitation.py /dev/cu.usbserial-11310 --plates A G D
"""

import argparse, ctypes, json, os, sys, time
from datetime import datetime
from pathlib import Path

import numpy as np
from scipy.signal import hilbert


class _NumpyEncoder(json.JSONEncoder):
    """Handle numpy types that stdlib json chokes on."""
    def default(self, o):
        if isinstance(o, (np.bool_,)):
            return bool(o)
        if isinstance(o, (np.integer,)):
            return int(o)
        if isinstance(o, (np.floating,)):
            return float(o)
        if isinstance(o, np.ndarray):
            return o.tolist()
        return super().default(o)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from picosdk.ps2000 import ps2000
from relay_mux import RelayMux

# ── PicoScope constants ────────────────────────────────────────────
TIMEBASE = 7
DT_NS = 1280
SAMPLE_RATE = 781_250
N_SAMPLES = 8064          # 10.3 ms capture window
AWG_DRIVE_UVPP = 2_000_000  # 2 Vpp

# ── Experiment parameters ──────────────────────────────────────────
EXCITE_DURATION = 0.5     # seconds to drive CW before each measurement
MEASURE_SETTLE = 0.005    # seconds after re-excite before capture
N_REPS = 5                # repetitions per delay point
N_REPS_FAST = 3           # reps in --fast mode
CONTRAST_THRESHOLD = 0.02 # 2% contrast = positive detection

# ── Plate configuration ───────────────────────────────────────────
# Best mode per plate: (freq_hz, Q_est, tau_ms_est)
# Selected for highest Q × highest SNR from census + Q measurements
PLATE_MODES = {
    'A': (55000, 12515, 72.4),
    'B': (29200,  9433, 102.8),
    'G': (64200, 15184, 37.7),
    'D': (29300,  4378, 47.6),
    'H': (63200,  3735, 18.8),
}
PLATE_RELAY = {'A': 1, 'B': 2, 'G': 3, 'D': 5, 'H': 7}


# ── PicoScope helpers ─────────────────────────────────────────────

def _open_scope():
    handle = ps2000.ps2000_open_unit()
    if handle <= 0:
        raise RuntimeError(f"PicoScope open failed (handle={handle})")
    ps2000.ps2000_set_channel(handle, 0, True, 1, 6)   # Ch A ±1 V DC
    ps2000.ps2000_set_channel(handle, 1, False, 1, 6)   # Ch B off
    return handle


def _close_scope(handle):
    try:
        ps2000.ps2000_set_sig_gen_built_in(
            handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0)
    except Exception:
        pass
    ps2000.ps2000_stop(handle)
    ps2000.ps2000_close_unit(handle)


def _set_cw(handle, freq_hz, amp_uvpp=AWG_DRIVE_UVPP):
    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, int(amp_uvpp), 0,
        float(freq_hz), float(freq_hz), 0.0, 0.0, 0, 0)


def _stop_awg(handle):
    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0)


def _capture(handle, n_samples=N_SAMPLES):
    t_ms = ctypes.c_int32()
    ps2000.ps2000_run_block(handle, n_samples, TIMEBASE, 1, ctypes.byref(t_ms))
    while ps2000.ps2000_ready(handle) == 0:
        pass
    buf_a = (ctypes.c_int16 * n_samples)()
    buf_b = (ctypes.c_int16 * n_samples)()
    overflow = ctypes.c_int16()
    n = ps2000.ps2000_get_values(
        handle, ctypes.byref(buf_a), ctypes.byref(buf_b),
        None, None, ctypes.byref(overflow), n_samples)
    return np.array(buf_a[:n], dtype=np.float64)


def _demod_iq(waveform, freq_hz):
    """I/Q demodulation at exact frequency → (magnitude, phase)."""
    N = len(waveform)
    t = np.arange(N) * (DT_NS * 1e-9)
    cos_ref = np.cos(2.0 * np.pi * freq_hz * t)
    sin_ref = np.sin(2.0 * np.pi * freq_hz * t)
    I = 2.0 * np.mean(waveform * cos_ref)
    Q = 2.0 * np.mean(waveform * sin_ref)
    return np.hypot(I, Q), np.arctan2(Q, I)


# ── Ringdown τ measurement ────────────────────────────────────────

def measure_ringdown(handle, freq_hz, excite_s=0.5, n_captures=3):
    """Drive CW → stop → capture ringdown → fit exponential → τ, Q."""
    _set_cw(handle, freq_hz)
    time.sleep(excite_s)
    _stop_awg(handle)

    # Capture immediately (ringdown starts now)
    wfs = [_capture(handle) for _ in range(n_captures)]

    best_tau, best_Q, best_r2 = None, None, -1.0
    for wf in wfs:
        analytic = hilbert(wf)
        envelope = np.abs(analytic)
        t = np.arange(len(envelope)) * DT_NS * 1e-9

        # Fit on segment where envelope > 1% of peak
        peak = envelope.max()
        if peak < 10:
            continue
        mask = envelope > peak * 0.01
        if mask.sum() < 20:
            continue

        log_env = np.log(envelope[mask])
        t_masked = t[mask]
        coeffs = np.polyfit(t_masked, log_env, 1)
        decay_rate = -coeffs[0]
        if decay_rate <= 0:
            continue

        tau_s = 1.0 / decay_rate
        Q = np.pi * freq_hz * tau_s
        ss_res = np.sum((log_env - np.polyval(coeffs, t_masked)) ** 2)
        ss_tot = np.sum((log_env - log_env.mean()) ** 2)
        r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0

        if r2 > best_r2:
            best_tau, best_Q, best_r2 = tau_s, Q, r2

    return best_tau, best_Q, best_r2


# ── Delay schedule ─────────────────────────────────────────────────

def make_delays(tau_s, n_points=25):
    """Log-spaced delays from ~1 ms to 10τ, plus 0 ms reference."""
    delays = [0.0]  # immediate re-excitation

    # 1 ms to 10τ in log-spaced steps
    lo = 0.001
    hi = max(10.0 * tau_s, 1.0)
    log_delays = np.logspace(np.log10(lo), np.log10(hi), n_points - 1)
    delays.extend(log_delays.tolist())

    return sorted(delays)


# ── Main experiment ────────────────────────────────────────────────

def run_plate(handle, mux, plate, n_reps):
    """Full re-excitation interference experiment for one plate."""
    freq_hz, Q_est, tau_est_ms = PLATE_MODES[plate]
    relay = PLATE_RELAY[plate]
    tau_est = tau_est_ms / 1000.0

    print(f"\n{'─'*70}")
    print(f"  PLATE {plate} — {freq_hz} Hz (est Q≈{Q_est}, τ≈{tau_est_ms:.1f} ms)")
    print(f"{'─'*70}")

    mux.select(relay)
    time.sleep(0.3)

    # ── Phase 1: Ringdown τ ────────────────────────────────────────
    print(f"  [1/4] Measuring ringdown τ …")
    tau_s, Q_meas, r2 = measure_ringdown(handle, freq_hz)

    if tau_s is None or tau_s < 0.001:
        print(f"    ⚠ Ringdown fit failed — using estimate τ = {tau_est*1000:.1f} ms")
        tau_s, Q_meas, r2 = tau_est, float(Q_est), 0.0
    else:
        print(f"    τ = {tau_s*1000:.2f} ms, Q = {Q_meas:.0f}, R² = {r2:.3f}")

    # ── Phase 2: Steady-state reference ────────────────────────────
    print(f"  [2/4] Measuring steady-state reference …")
    _set_cw(handle, freq_hz)
    time.sleep(EXCITE_DURATION)

    ss_mags, ss_phases = [], []
    for _ in range(n_reps):
        wf = _capture(handle)
        mag, ph = _demod_iq(wf, freq_hz)
        ss_mags.append(mag)
        ss_phases.append(ph)
    _stop_awg(handle)
    time.sleep(0.1)

    ss_mag = float(np.mean(ss_mags))
    ss_std = float(np.std(ss_mags))
    print(f"    Steady-state: mag = {ss_mag:.0f} ± {ss_std:.0f}")

    # ── Phase 3: Delay sweep — RE-EXCITATION ──────────────────────
    delays = make_delays(tau_s)
    print(f"  [3/4] Re-excitation sweep: {len(delays)} delays, "
          f"0 ms – {delays[-1]*1000:.0f} ms ({n_reps} reps each)")

    reexcite_results = []
    t0_sweep = time.time()

    for di, delay in enumerate(delays):
        mags, phases = [], []

        for _ in range(n_reps):
            # Drive to steady state
            _set_cw(handle, freq_hz)
            time.sleep(EXCITE_DURATION)

            # Stop AWG
            _stop_awg(handle)

            # Wait the prescribed delay
            if delay > 0.01:
                time.sleep(delay)
            elif delay > 0:
                t_wait = time.perf_counter()
                while time.perf_counter() - t_wait < delay:
                    pass

            # Re-excite and settle
            _set_cw(handle, freq_hz)
            time.sleep(MEASURE_SETTLE)

            # Capture
            wf = _capture(handle)
            mag, ph = _demod_iq(wf, freq_hz)
            mags.append(mag)
            phases.append(ph)

            # Brief pause between reps
            _stop_awg(handle)
            time.sleep(0.02)

        result = {
            'delay_s': float(delay),
            'delay_tau': float(delay / tau_s),
            'mag_mean': float(np.mean(mags)),
            'mag_std': float(np.std(mags)),
            'phase_mean': float(np.mean(phases)),
            'phase_std': float(np.std(phases)),
            'mags': [float(m) for m in mags],
            'phases': [float(p) for p in phases],
            'expected_residual_frac': float(np.exp(-delay / tau_s)),
        }
        reexcite_results.append(result)

        # Progress every 5 points
        if di % 5 == 0 or di == len(delays) - 1:
            norm = result['mag_mean'] / ss_mag if ss_mag > 0 else 0
            elapsed = time.time() - t0_sweep
            print(f"    [{di+1:2d}/{len(delays)}] Δt = {delay*1000:9.3f} ms "
                  f"({delay/tau_s:6.3f} τ)  mag = {result['mag_mean']:9.0f}  "
                  f"norm = {norm:.4f}  exp(-Δt/τ) = {result['expected_residual_frac']:.4f}  "
                  f"[{elapsed:.0f}s]")

    # ── Phase 4: Delay sweep — RESIDUAL ONLY (no re-excitation) ───
    print(f"  [4/4] Residual-only control: {len(delays)} delays")

    residual_results = []
    t0_resid = time.time()

    for di, delay in enumerate(delays):
        mags, phases = [], []

        for _ in range(n_reps):
            # Drive to steady state
            _set_cw(handle, freq_hz)
            time.sleep(EXCITE_DURATION)

            # Stop AWG
            _stop_awg(handle)

            # Wait the prescribed delay
            if delay > 0.01:
                time.sleep(delay)
            elif delay > 0:
                t_wait = time.perf_counter()
                while time.perf_counter() - t_wait < delay:
                    pass

            # Capture WITHOUT re-excitation
            wf = _capture(handle)
            mag, ph = _demod_iq(wf, freq_hz)
            mags.append(mag)
            phases.append(ph)

            time.sleep(0.02)

        result = {
            'delay_s': float(delay),
            'delay_tau': float(delay / tau_s),
            'mag_mean': float(np.mean(mags)),
            'mag_std': float(np.std(mags)),
            'phase_mean': float(np.mean(phases)),
            'phase_std': float(np.std(phases)),
            'mags': [float(m) for m in mags],
            'phases': [float(p) for p in phases],
            'expected_residual_frac': float(np.exp(-delay / tau_s)),
        }
        residual_results.append(result)

        if di % 5 == 0 or di == len(delays) - 1:
            elapsed = time.time() - t0_resid
            print(f"    [{di+1:2d}/{len(delays)}] Δt = {delay*1000:9.3f} ms  "
                  f"residual mag = {result['mag_mean']:9.0f}  "
                  f"exp(-Δt/τ) = {result['expected_residual_frac']:.4f}  "
                  f"[{elapsed:.0f}s]")

    # ── Analysis ──────────────────────────────────────────────────
    # Reference = last delay point (≈ 10τ, fully decayed)
    ref_reex_mag = reexcite_results[-1]['mag_mean']
    ref_resid_mag = residual_results[-1]['mag_mean']

    # Contrast in re-excitation series
    re_mags = [r['mag_mean'] for r in reexcite_results]
    re_max, re_min = max(re_mags), min(re_mags)
    contrast = (re_max - re_min) / (re_max + re_min) if (re_max + re_min) > 0 else 0

    # Enhancement at Δt = 0 vs fully decayed
    enhancement = reexcite_results[0]['mag_mean'] / ref_reex_mag if ref_reex_mag > 0 else 0

    # Residual at Δt = 0 (should be close to steady state)
    resid_at_zero = residual_results[0]['mag_mean']
    resid_ratio = resid_at_zero / ss_mag if ss_mag > 0 else 0

    # Check: does re-excitation magnitude decay monotonically with delay?
    # (it should, as residual contribution shrinks)
    mid_idx = len(reexcite_results) // 2
    early_mean = np.mean([r['mag_mean'] for r in reexcite_results[:mid_idx]])
    late_mean = np.mean([r['mag_mean'] for r in reexcite_results[mid_idx:]])
    decay_trend = early_mean > late_mean

    # Interference verdict
    interference = (contrast > CONTRAST_THRESHOLD or enhancement > 1.05) and decay_trend
    verdict = "INTERFERENCE DETECTED" if interference else "NO SIGNIFICANT INTERFERENCE"

    print(f"\n  ══════════════════════════════════════════════════════")
    print(f"  RESULTS: Plate {plate} @ {freq_hz} Hz")
    print(f"  ══════════════════════════════════════════════════════")
    print(f"  Ringdown:    τ = {tau_s*1000:.2f} ms, Q = {Q_meas:.0f}")
    print(f"  Steady-state mag:   {ss_mag:.0f} ± {ss_std:.0f}")
    print(f"  Re-excite ref (10τ): {ref_reex_mag:.0f}")
    print(f"  Residual ref (10τ):  {ref_resid_mag:.0f}")
    print(f"  Enhancement (Δt=0): {enhancement:.3f}×  "
          f"({'↑ BOOSTED' if enhancement > 1.05 else '— flat'})")
    print(f"  Contrast:           {contrast:.4f}  ({contrast*100:.2f}%)")
    print(f"  Residual@0 / SS:    {resid_ratio:.3f}")
    print(f"  Decay trend:        {'YES' if decay_trend else 'NO'}")
    print(f"  ──────────────────────────────────────────────────────")
    print(f"  VERDICT: {verdict}")
    print(f"  ══════════════════════════════════════════════════════")

    return {
        'plate': plate,
        'relay': relay,
        'freq_hz': freq_hz,
        'tau_s': float(tau_s),
        'Q_measured': float(Q_meas),
        'ringdown_r2': float(r2),
        'ss_mag': ss_mag,
        'ss_std': ss_std,
        'ref_reexcite_mag': float(ref_reex_mag),
        'ref_residual_mag': float(ref_resid_mag),
        'enhancement_at_zero': float(enhancement),
        'contrast': float(contrast),
        'residual_at_zero_ratio': float(resid_ratio),
        'decay_trend': decay_trend,
        'interference_detected': interference,
        'verdict': verdict,
        'reexcitation': reexcite_results,
        'residual_only': residual_results,
    }


# ── Entry point ────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Phase 1.6 Step 4: Re-Excitation Interference")
    parser.add_argument('port', help="Arduino relay mux serial port")
    parser.add_argument('--plates', nargs='+', default=['A', 'B', 'G', 'D', 'H'],
                        choices=['A', 'B', 'G', 'D', 'H'],
                        help="Plates to test (default: all 5)")
    parser.add_argument('--fast', action='store_true',
                        help="Fewer reps and delay points for quick check")
    args = parser.parse_args()

    n_reps = N_REPS_FAST if args.fast else N_REPS
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')

    out_dir = Path('data/results/lab/plate_exps')
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"reexcitation_{ts}.json"

    print("=" * 70)
    print("  PHASE 1.6 STEP 4: RE-EXCITATION INTERFERENCE")
    print(f"  Plates: {', '.join(args.plates)}")
    print(f"  Reps per delay: {n_reps}")
    print(f"  Mode: {'FAST' if args.fast else 'FULL'}")
    print("=" * 70)

    handle = _open_scope()
    print(f"  PicoScope opened (Ch A ±1V DC)")

    mux = RelayMux(port=args.port)
    mux.open()
    print(f"  Relay mux connected on {args.port}")

    all_results = []
    t0 = time.time()

    try:
        for plate in args.plates:
            result = run_plate(handle, mux, plate, n_reps)
            all_results.append(result)
    finally:
        try:
            mux.off()
        except Exception:
            pass
        try:
            mux.close()
        except Exception:
            pass
        _close_scope(handle)

    elapsed = time.time() - t0

    # ── Summary ────────────────────────────────────────────────────
    print(f"\n{'=' * 70}")
    print(f"  SUMMARY — {elapsed:.0f}s ({elapsed/60:.1f} min)")
    print(f"{'=' * 70}")
    print(f"  {'Plate':>5s}  {'Freq':>7s}  {'Q':>7s}  {'τ(ms)':>7s}  "
          f"{'Enhance':>8s}  {'Contrast':>9s}  {'Verdict'}")
    print(f"  {'─'*5}  {'─'*7}  {'─'*7}  {'─'*7}  {'─'*8}  {'─'*9}  {'─'*25}")

    any_detected = False
    for r in all_results:
        det = r['interference_detected']
        if det:
            any_detected = True
        print(f"  {r['plate']:>5s}  {r['freq_hz']:>7.0f}  {r['Q_measured']:>7.0f}  "
              f"{r['tau_s']*1000:>7.1f}  {r['enhancement_at_zero']:>7.3f}×  "
              f"{r['contrast']*100:>8.2f}%  "
              f"{'✅ DETECTED' if det else '— none'}")

    if any_detected:
        print(f"\n  🔬 COHERENT PHONONIC MEMORY OBSERVED")
    else:
        print(f"\n  No significant interference detected at {CONTRAST_THRESHOLD*100:.0f}% threshold")

    # Compare to rod E33
    print(f"\n  Rod E33 baseline: 0.27% contrast at Q ≈ 400")

    # ── Save ───────────────────────────────────────────────────────
    output = {
        'experiment': 'Phase 1.6 Step 4: Re-Excitation Interference',
        'timestamp': datetime.now().isoformat(),
        'duration_s': elapsed,
        'n_reps': n_reps,
        'fast_mode': args.fast,
        'excite_duration_s': EXCITE_DURATION,
        'measure_settle_s': MEASURE_SETTLE,
        'plates_tested': args.plates,
        'results': all_results,
    }

    with open(out_path, 'w') as f:
        json.dump(output, f, indent=2, cls=_NumpyEncoder)
    print(f"\n  Results saved: {out_path}")


if __name__ == '__main__':
    main()
