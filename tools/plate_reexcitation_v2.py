#!/usr/bin/env python3
"""
Phase 1.6 Step 4 v2: Re-Excitation Interference (Phasor Subtraction)
═════════════════════════════════════════════════════════════════════

Revisits E33 with Ch B DDS phase reference + complex baseline subtraction.

v1 flaw: Raw magnitude differencing on Ch A measured ~99.9% electrical
crosstalk (direct AWG→scope coupling), masking any acoustic signal.

v2 fix:
  - Ch B captures AWG reference simultaneously → Za/Zb cancels DDS phase
  - Relay-OFF baseline → subtract electrical-only transfer function
  - Residual acoustic phasor isolated: amplitude AND phase vs delay

Protocol per delay point:
  1. Relay-OFF baseline: CW → capture Za/Zb (electrical only)
  2. Relay-ON measurement:
     a. Drive CW steady state (0.5 s)
     b. Stop AWG, wait delay Δt
     c. Re-excite CW, brief settle
     d. Capture Za/Zb (electrical + acoustic)
  3. Acoustic phasor = (Za/Zb)_on - (Za/Zb)_off_baseline

If residual vibration from step (b) persists through the delay and
interferes with new excitation in step (c), the ACOUSTIC phasor will
shift in both magnitude and phase compared to the fully-decayed reference.

Wiring: AWG → BNC tee → plates (relay mux → Ch A) + Ch B (direct ref)

Usage:
  python tools/plate_reexcitation_v2.py /dev/cu.usbserial-11310
  python tools/plate_reexcitation_v2.py /dev/cu.usbserial-11310 --fast
  python tools/plate_reexcitation_v2.py /dev/cu.usbserial-11310 --plates A B
"""

import argparse, ctypes, json, os, sys, time
from datetime import datetime
from pathlib import Path

import numpy as np
from scipy.signal import hilbert

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cwm_picoscope
from picosdk.ps2000 import ps2000
from relay_mux import RelayMux


class _NumpyEncoder(json.JSONEncoder):
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


# ── PicoScope constants ────────────────────────────────────────────
TIMEBASE = 7
DT_NS = 1280
SAMPLE_RATE = 781_250
N_SAMPLES = 3072          # dual-channel (shared 8 kS buffer)
AWG_DRIVE_UVPP = 2_000_000

# ── Experiment parameters ──────────────────────────────────────────
EXCITE_DURATION = 0.5     # seconds to drive CW before each measurement
MEASURE_SETTLE = 0.005    # seconds after re-excite before capture
N_REPS = 5
N_REPS_FAST = 3
N_DELAY_POINTS = 25
N_DELAY_POINTS_FAST = 15
N_BASELINE = 10           # baseline captures per mode
CONTRAST_THRESHOLD = 0.02 # 2% acoustic contrast = positive detection

# ── Plate configuration ───────────────────────────────────────────
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
    ps2000.ps2000_set_channel(handle, 0, True, 1, 6)   # Ch A (plate)
    ps2000.ps2000_set_channel(handle, 1, True, 1, 6)    # Ch B (AWG ref)
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


def _capture_dual(handle, n_samples=N_SAMPLES):
    """Capture Ch A + Ch B simultaneously."""
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
    return (np.array(buf_a[:n], dtype=np.float64),
            np.array(buf_b[:n], dtype=np.float64))


def _capture_single_a(handle, n_samples=N_SAMPLES):
    """Capture Ch A only (for ringdown — AWG is off so Ch B is useless)."""
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


def _demod_iq_complex(waveform, freq_hz):
    """I/Q demodulation → complex phasor."""
    N = len(waveform)
    t = np.arange(N) * (DT_NS * 1e-9)
    cos_ref = np.cos(2.0 * np.pi * freq_hz * t)
    sin_ref = np.sin(2.0 * np.pi * freq_hz * t)
    I = 2.0 * np.mean(waveform * cos_ref)
    Q = 2.0 * np.mean(waveform * sin_ref)
    return complex(I, Q)


def _referenced_phasor(a, b, freq_hz):
    """Compute Za/Zb — DDS-phase-cancelled transfer function."""
    Za = _demod_iq_complex(a, freq_hz)
    Zb = _demod_iq_complex(b, freq_hz)
    return Za / Zb


# ── Circular statistics ───────────────────────────────────────────

def circular_std(phases):
    R = np.hypot(np.mean(np.cos(phases)), np.mean(np.sin(phases)))
    R = min(R, 1.0)
    if R < 1e-10:
        return np.pi
    return np.sqrt(-2.0 * np.log(R))


# ── Ringdown ──────────────────────────────────────────────────────

def measure_ringdown(handle, freq_hz, excite_s=0.5, n_captures=3):
    """Drive CW → stop → capture ringdown → fit τ, Q."""
    _set_cw(handle, freq_hz)
    time.sleep(excite_s)
    _stop_awg(handle)

    wfs = [_capture_single_a(handle) for _ in range(n_captures)]

    best_tau, best_Q, best_r2 = None, None, -1.0
    for wf in wfs:
        analytic = hilbert(wf)
        envelope = np.abs(analytic)
        t = np.arange(len(envelope)) * DT_NS * 1e-9

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
    delays = [0.0]
    lo = 0.001
    hi = max(10.0 * tau_s, 1.0)
    log_delays = np.logspace(np.log10(lo), np.log10(hi), n_points - 1)
    delays.extend(log_delays.tolist())
    return sorted(delays)


# ── Baseline capture ──────────────────────────────────────────────

def capture_baseline(handle, freq_hz, n_baseline=N_BASELINE):
    """CW drive with relay OFF → electrical-only transfer function."""
    _set_cw(handle, freq_hz)
    time.sleep(0.5)

    phasors = []
    for _ in range(n_baseline):
        a, b = _capture_dual(handle)
        phasors.append(_referenced_phasor(a, b, freq_hz))

    return np.mean(phasors)


# ── Main experiment ────────────────────────────────────────────────

def run_plate(handle, mux, plate, n_reps, n_delays):
    freq_hz, Q_est, tau_est_ms = PLATE_MODES[plate]
    relay = PLATE_RELAY[plate]
    tau_est = tau_est_ms / 1000.0

    print(f"\n{'─'*70}")
    print(f"  PLATE {plate} — {freq_hz} Hz (est Q≈{Q_est}, τ≈{tau_est_ms:.1f} ms)")
    print(f"{'─'*70}")

    # ── Ringdown τ ─────────────────────────────────────────────────
    mux.select(relay)
    time.sleep(0.3)
    print(f"  [1/5] Measuring ringdown τ …")
    tau_s, Q_meas, r2 = measure_ringdown(handle, freq_hz)

    if tau_s is None or tau_s < 0.001:
        print(f"    ⚠ Ringdown fit failed — using estimate τ = {tau_est*1000:.1f} ms")
        tau_s, Q_meas, r2 = tau_est, float(Q_est), 0.0
    else:
        print(f"    τ = {tau_s*1000:.2f} ms, Q = {Q_meas:.0f}, R² = {r2:.3f}")

    # ── Electrical baseline (relay OFF) ────────────────────────────
    print(f"  [2/5] Measuring electrical baseline (relay OFF) …")
    mux.off()
    time.sleep(0.2)
    baseline = capture_baseline(handle, freq_hz)
    print(f"    Baseline: |H_elec| = {abs(baseline):.4f}, "
          f"∠H_elec = {np.degrees(np.angle(baseline)):.1f}°")

    # ── Steady-state reference (relay ON, CW) ─────────────────────
    print(f"  [3/5] Measuring steady-state reference (relay ON) …")
    mux.select(relay)
    time.sleep(0.3)
    _set_cw(handle, freq_hz)
    time.sleep(EXCITE_DURATION)

    ss_phasors = []
    for _ in range(n_reps):
        a, b = _capture_dual(handle)
        ss_phasors.append(_referenced_phasor(a, b, freq_hz))

    ss_total = np.mean(ss_phasors)
    ss_acoustic = ss_total - baseline
    ss_acou_mag = abs(ss_acoustic)
    ss_acou_phase = np.angle(ss_acoustic)
    ss_fraction = ss_acou_mag / abs(ss_total) if abs(ss_total) > 0 else 0

    print(f"    Total:    |H| = {abs(ss_total):.4f}, ∠ = {np.degrees(np.angle(ss_total)):.1f}°")
    print(f"    Acoustic: |H| = {ss_acou_mag:.4f}, ∠ = {np.degrees(ss_acou_phase):.1f}°"
          f"  (fraction = {ss_fraction:.3f})")
    _stop_awg(handle)
    time.sleep(0.1)

    # ── Delay sweep: RE-EXCITATION ────────────────────────────────
    delays = make_delays(tau_s, n_delays)
    print(f"  [4/5] Re-excitation sweep: {len(delays)} delays, "
          f"0 – {delays[-1]*1000:.0f} ms ({n_reps} reps each)")

    reexcite_results = []
    t0_sweep = time.time()

    for di, delay in enumerate(delays):
        rep_phasors_total = []
        rep_phasors_acoustic = []

        for _ in range(n_reps):
            # Drive to steady state
            _set_cw(handle, freq_hz)
            time.sleep(EXCITE_DURATION)

            # Stop AWG — ringdown begins
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

            # Capture dual-channel
            a, b = _capture_dual(handle)
            phasor = _referenced_phasor(a, b, freq_hz)
            acoustic = phasor - baseline

            rep_phasors_total.append(phasor)
            rep_phasors_acoustic.append(acoustic)

            _stop_awg(handle)
            time.sleep(0.02)

        # Statistics for this delay point
        acou_mags = [abs(p) for p in rep_phasors_acoustic]
        acou_phases = [np.angle(p) for p in rep_phasors_acoustic]
        total_mags = [abs(p) for p in rep_phasors_total]

        result = {
            'delay_s': float(delay),
            'delay_tau': float(delay / tau_s),
            'acoustic_mag_mean': float(np.mean(acou_mags)),
            'acoustic_mag_std': float(np.std(acou_mags)),
            'acoustic_phase_mean': float(np.mean(acou_phases)),
            'acoustic_phase_std': float(circular_std(acou_phases)),
            'total_mag_mean': float(np.mean(total_mags)),
            'total_mag_std': float(np.std(total_mags)),
            'expected_residual_frac': float(np.exp(-delay / tau_s)),
            'acoustic_mags': [float(m) for m in acou_mags],
            'acoustic_phases': [float(p) for p in acou_phases],
        }
        reexcite_results.append(result)

        if di % 5 == 0 or di == len(delays) - 1:
            norm = result['acoustic_mag_mean'] / ss_acou_mag if ss_acou_mag > 0 else 0
            elapsed = time.time() - t0_sweep
            print(f"    [{di+1:2d}/{len(delays)}] Δt={delay*1000:9.3f} ms "
                  f"({delay/tau_s:5.2f}τ)  "
                  f"|acou|={result['acoustic_mag_mean']:.4f}  "
                  f"norm={norm:.4f}  "
                  f"∠={np.degrees(result['acoustic_phase_mean']):+6.1f}°  "
                  f"exp(-Δt/τ)={result['expected_residual_frac']:.4f}  "
                  f"[{elapsed:.0f}s]")

    # ── Delay sweep: RESIDUAL ONLY (no re-excitation) ─────────────
    print(f"  [5/5] Residual-only control: {len(delays)} delays")

    residual_results = []
    t0_resid = time.time()

    for di, delay in enumerate(delays):
        rep_phasors_acoustic = []

        for _ in range(n_reps):
            # Drive to steady state
            _set_cw(handle, freq_hz)
            time.sleep(EXCITE_DURATION)

            # Stop AWG
            _stop_awg(handle)

            # Wait delay
            if delay > 0.01:
                time.sleep(delay)
            elif delay > 0:
                t_wait = time.perf_counter()
                while time.perf_counter() - t_wait < delay:
                    pass

            # Capture WITHOUT re-excitation
            # AWG is off → Ch B has no signal → Za/Zb is undefined
            # Instead, just capture Ch A raw and demod
            a, b = _capture_dual(handle)
            Za = _demod_iq_complex(a, freq_hz)
            # With AWG off, use magnitude only (no reference possible)
            rep_phasors_acoustic.append(Za)

            time.sleep(0.02)

        resid_mags = [abs(p) for p in rep_phasors_acoustic]

        result = {
            'delay_s': float(delay),
            'delay_tau': float(delay / tau_s),
            'residual_mag_mean': float(np.mean(resid_mags)),
            'residual_mag_std': float(np.std(resid_mags)),
            'expected_residual_frac': float(np.exp(-delay / tau_s)),
            'residual_mags': [float(m) for m in resid_mags],
        }
        residual_results.append(result)

        if di % 5 == 0 or di == len(delays) - 1:
            elapsed = time.time() - t0_resid
            print(f"    [{di+1:2d}/{len(delays)}] Δt={delay*1000:9.3f} ms  "
                  f"residual={result['residual_mag_mean']:.0f}  "
                  f"exp(-Δt/τ)={result['expected_residual_frac']:.4f}  "
                  f"[{elapsed:.0f}s]")

    # ── Analysis ──────────────────────────────────────────────────
    # Reference = last delay point (≈ 10τ, fully decayed)
    ref_acou_mag = reexcite_results[-1]['acoustic_mag_mean']
    ref_acou_phase = reexcite_results[-1]['acoustic_phase_mean']

    # Acoustic magnitude contrast
    acou_mags_all = [r['acoustic_mag_mean'] for r in reexcite_results]
    acou_max, acou_min = max(acou_mags_all), min(acou_mags_all)
    mag_contrast = (acou_max - acou_min) / (acou_max + acou_min) if (acou_max + acou_min) > 0 else 0

    # Phase shift: difference between Δt=0 and Δt=10τ
    phase_at_zero = reexcite_results[0]['acoustic_phase_mean']
    phase_shift = abs(phase_at_zero - ref_acou_phase)
    # Wrap to [0, π]
    if phase_shift > np.pi:
        phase_shift = 2 * np.pi - phase_shift

    # Enhancement: acoustic mag at Δt=0 vs fully decayed
    enhancement = reexcite_results[0]['acoustic_mag_mean'] / ref_acou_mag if ref_acou_mag > 0 else 0

    # Decay trend: does acoustic magnitude change monotonically with delay?
    mid_idx = len(reexcite_results) // 2
    early_mag = np.mean([r['acoustic_mag_mean'] for r in reexcite_results[:mid_idx]])
    late_mag = np.mean([r['acoustic_mag_mean'] for r in reexcite_results[mid_idx:]])
    mag_trend = abs(early_mag - late_mag) / ((early_mag + late_mag) / 2) if (early_mag + late_mag) > 0 else 0

    # Phase trend: do early delays have different phase than late?
    early_phases = [r['acoustic_phase_mean'] for r in reexcite_results[:mid_idx]]
    late_phases = [r['acoustic_phase_mean'] for r in reexcite_results[mid_idx:]]
    phase_trend = abs(np.mean(np.sin(early_phases)) - np.mean(np.sin(late_phases)))

    # Verdict
    interference = (mag_contrast > CONTRAST_THRESHOLD or
                    phase_shift > 0.1 or
                    enhancement > 1.05 or enhancement < 0.95)
    verdict = "INTERFERENCE DETECTED" if interference else "NO SIGNIFICANT INTERFERENCE"

    print(f"\n  ══════════════════════════════════════════════════════")
    print(f"  RESULTS: Plate {plate} @ {freq_hz} Hz")
    print(f"  ══════════════════════════════════════════════════════")
    print(f"  Ringdown:        τ = {tau_s*1000:.2f} ms, Q = {Q_meas:.0f}")
    print(f"  Acoustic frac:   {ss_fraction:.3f}")
    print(f"  SS acoustic mag: {ss_acou_mag:.4f}")
    print(f"  Ref (10τ) mag:   {ref_acou_mag:.4f}")
    print(f"  ──────────────────────────────────────────────────────")
    print(f"  Mag contrast:    {mag_contrast:.4f}  ({mag_contrast*100:.2f}%)"
          f"  {'← ABOVE threshold' if mag_contrast > CONTRAST_THRESHOLD else ''}")
    print(f"  Enhancement:     {enhancement:.4f}×"
          f"  {'← SHIFTED' if abs(enhancement - 1) > 0.05 else '— flat'}")
    print(f"  Phase shift:     {np.degrees(phase_shift):.2f}°"
          f"  {'← SHIFTED' if phase_shift > 0.1 else '— flat'}")
    print(f"  Mag trend:       {mag_trend:.4f}")
    print(f"  Phase trend:     {phase_trend:.4f}")
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
        'baseline_mag': float(abs(baseline)),
        'baseline_phase_deg': float(np.degrees(np.angle(baseline))),
        'ss_total_mag': float(abs(ss_total)),
        'ss_acoustic_mag': float(ss_acou_mag),
        'ss_acoustic_phase_deg': float(np.degrees(ss_acou_phase)),
        'ss_acoustic_fraction': float(ss_fraction),
        'ref_acoustic_mag': float(ref_acou_mag),
        'ref_acoustic_phase_deg': float(np.degrees(ref_acou_phase)),
        'mag_contrast': float(mag_contrast),
        'enhancement': float(enhancement),
        'phase_shift_deg': float(np.degrees(phase_shift)),
        'mag_trend': float(mag_trend),
        'phase_trend': float(phase_trend),
        'interference_detected': interference,
        'verdict': verdict,
        'reexcitation': reexcite_results,
        'residual_only': residual_results,
    }


# ── Entry point ────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Phase 1.6 Step 4 v2: Re-Excitation Interference (Phasor)")
    parser.add_argument('port', help="Arduino relay mux serial port")
    parser.add_argument('--plates', nargs='+', default=['A', 'B', 'G', 'D', 'H'],
                        choices=['A', 'B', 'G', 'D', 'H'],
                        help="Plates to test (default: all 5)")
    parser.add_argument('--fast', action='store_true',
                        help="Fewer reps and delay points")
    args = parser.parse_args()

    n_reps = N_REPS_FAST if args.fast else N_REPS
    n_delays = N_DELAY_POINTS_FAST if args.fast else N_DELAY_POINTS
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')

    out_dir = Path('data/results/lab/plate_exps')
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"reexcitation_v2_{ts}.json"

    print("=" * 70)
    print("  PHASE 1.6 STEP 4 v2: RE-EXCITATION INTERFERENCE (PHASOR)")
    print("=" * 70)
    print(f"  Plates: {', '.join(args.plates)}")
    print(f"  Reps per delay: {n_reps}")
    print(f"  Delay points: {n_delays}")
    print(f"  Mode: {'FAST' if args.fast else 'FULL'}")
    print(f"  Wiring: AWG → tee → plates(ChA) + ChB(ref)")
    print(f"  Method: Za/Zb referenced + baseline subtraction")
    print("=" * 70)

    handle = _open_scope()
    print(f"  PicoScope opened (Ch A + Ch B ±1V DC, {N_SAMPLES} samples)")

    mux = RelayMux(port=args.port)
    mux.open()
    print(f"  Relay mux connected on {args.port}")

    all_results = []
    t0 = time.time()

    try:
        for plate in args.plates:
            result = run_plate(handle, mux, plate, n_reps, n_delays)
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
          f"{'Frac':>5s}  {'MagΔ%':>6s}  {'PhaseΔ':>7s}  {'Verdict'}")
    print(f"  {'─'*5}  {'─'*7}  {'─'*7}  {'─'*7}  {'─'*5}  {'─'*6}  {'─'*7}  {'─'*25}")

    any_detected = False
    for r in all_results:
        det = r['interference_detected']
        if det:
            any_detected = True
        print(f"  {r['plate']:>5s}  {r['freq_hz']:>7.0f}  {r['Q_measured']:>7.0f}  "
              f"{r['tau_s']*1000:>7.1f}  "
              f"{r['ss_acoustic_fraction']:>4.2f}  "
              f"{r['mag_contrast']*100:>5.2f}%  "
              f"{r['phase_shift_deg']:>6.2f}°  "
              f"{'✅ DETECTED' if det else '— none'}")

    if any_detected:
        print(f"\n  🔬 COHERENT PHONONIC MEMORY OBSERVED")
    else:
        print(f"\n  No significant interference at {CONTRAST_THRESHOLD*100:.0f}% / 0.1 rad threshold")

    print(f"\n  v1 result:  all plates — 0.11–0.29% (magnitude only, no phase ref)")
    print(f"  Rod E33:    0.27% contrast at Q ≈ 400")

    # ── Save ───────────────────────────────────────────────────────
    output = {
        'experiment': 'Phase 1.6 Step 4 v2: Re-Excitation Interference (Phasor)',
        'timestamp': datetime.now().isoformat(),
        'duration_s': elapsed,
        'n_reps': n_reps,
        'n_delay_points': n_delays,
        'fast_mode': args.fast,
        'excite_duration_s': EXCITE_DURATION,
        'measure_settle_s': MEASURE_SETTLE,
        'n_baseline': N_BASELINE,
        'n_samples_per_capture': N_SAMPLES,
        'wiring': 'AWG → BNC tee → plates(ChA) + ChB(direct ref)',
        'method': 'Za/Zb referenced + electrical baseline subtraction',
        'plates_tested': args.plates,
        'any_interference': any_detected,
        'results': all_results,
    }

    with open(out_path, 'w') as f:
        json.dump(output, f, indent=2, cls=_NumpyEncoder)
    print(f"\n  Results saved: {out_path}")


if __name__ == '__main__':
    main()
