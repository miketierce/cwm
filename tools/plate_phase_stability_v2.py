#!/usr/bin/env python3
"""
Phase 1.6 Step 5 v2: Phase Stability with Ch B Reference
═════════════════════════════════════════════════════════════

Uses Ch B as a DDS phase reference to cancel free-running oscillator drift.
AWG → BNC tee → plates (via relay mux) → Ch A
                └→ Ch B (direct reference)

The complex ratio Z_A / Z_B cancels the arbitrary DDS phase that differs
between captures, revealing the true acoustic transfer function phase.

Additionally subtracts relay-OFF electrical baseline to isolate the
acoustic-only contribution.

Protocol per mode:
  1. Relay OFF: capture N baseline measurements (electrical only)
  2. Relay ON:  drive CW, capture N measurements through plate
  3. Compute referenced phase: angle(Z_A / Z_B) for each capture
  4. Subtract baseline: Z_on/Z_ref - Z_off/Z_ref = acoustic only
  5. Circular σ of acoustic phase = stability metric

Rod E03 result:  only 15% of modes stable (σ = 1.71 rad)
Target (plates): >50% of modes with σ_phase < 0.5 rad

Usage:
  python tools/plate_phase_stability_v2.py /dev/cu.usbserial-11310 \\
      --census data/results/lab/plate_exps/plate_census_20260418_221958.json
  python tools/plate_phase_stability_v2.py /dev/cu.usbserial-11310 \\
      --census data/results/lab/plate_exps/plate_census_20260418_221958.json --fast
"""

import argparse, ctypes, json, os, sys, time
from datetime import datetime
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cwm_picoscope
from picosdk.ps2000 import ps2000
from relay_mux import RelayMux


# ── PicoScope constants ────────────────────────────────────────────
TIMEBASE = 7
DT_NS = 1280
SAMPLE_RATE = 781_250
N_SAMPLES = 3072          # dual-channel max for 2204A (shared 8 kS buffer)
AWG_DRIVE_UVPP = 2_000_000  # 2 Vpp

# ── Experiment parameters ──────────────────────────────────────────
N_CAPTURES = 100          # captures per mode (full)
N_CAPTURES_FAST = 30      # captures per mode (--fast)
SETTLE_S = 0.5            # CW settle time before captures
MODES_PER_PLATE = 5       # top-N modes by SNR
PHASE_STABLE_THRESHOLD = 0.5   # rad — mode is "stable" if σ < this

# ── Plate → relay mapping ─────────────────────────────────────────
PLATE_RELAY = {'A': 1, 'B': 2, 'G': 3, 'D': 5, 'H': 7}
PLATE_CENSUS_KEY = {'A': '1', 'B': '2', 'G': '3_NE', 'D': '4_NE', 'H': '5_NE'}


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


# ── PicoScope helpers ─────────────────────────────────────────────

def _open_scope():
    handle = ps2000.ps2000_open_unit()
    if handle <= 0:
        raise RuntimeError(f"PicoScope open failed (handle={handle})")
    ps2000.ps2000_set_channel(handle, 0, True, 1, 6)   # Ch A ±1 V DC (plate)
    ps2000.ps2000_set_channel(handle, 1, True, 1, 6)    # Ch B ±1 V DC (AWG ref)
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
    """Capture simultaneously on Ch A and Ch B. Returns (array_a, array_b)."""
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


def _demod_iq(waveform, freq_hz):
    """I/Q demodulation → complex phasor Z = I + jQ."""
    N = len(waveform)
    t = np.arange(N) * (DT_NS * 1e-9)
    cos_ref = np.cos(2.0 * np.pi * freq_hz * t)
    sin_ref = np.sin(2.0 * np.pi * freq_hz * t)
    I = 2.0 * np.mean(waveform * cos_ref)
    Q = 2.0 * np.mean(waveform * sin_ref)
    return complex(I, Q)


# ── Circular statistics ───────────────────────────────────────────

def circular_mean(phases):
    return np.arctan2(np.mean(np.sin(phases)), np.mean(np.cos(phases)))


def circular_std(phases):
    R = np.hypot(np.mean(np.cos(phases)), np.mean(np.sin(phases)))
    R = min(R, 1.0)
    if R < 1e-10:
        return np.pi  # effectively uniform
    return np.sqrt(-2.0 * np.log(R))


# ── Census loader ─────────────────────────────────────────────────

def load_top_modes(census_path, plate, n_modes=MODES_PER_PLATE):
    with open(census_path) as f:
        census = json.load(f)
    key = PLATE_CENSUS_KEY[plate]
    peaks = census['results'][key]['peaks']
    by_snr = sorted(peaks, key=lambda m: m['snr_db'], reverse=True)
    top = by_snr[:n_modes]
    return [(m['freq_hz'], m['snr_db']) for m in top]


# ── Per-mode measurement ─────────────────────────────────────────

def measure_phase_stability(handle, mux, relay, freq_hz, n_captures):
    """
    1. Relay OFF → CW → baseline captures (electrical-only transfer function)
    2. Relay ON  → CW → plate captures (electrical + acoustic)
    3. Compute referenced phase, subtract baseline, report σ
    """
    # ── Baseline: relay OFF ──────────────────────────────────────
    mux.off()
    time.sleep(0.1)
    _set_cw(handle, freq_hz)
    time.sleep(SETTLE_S)

    baseline_phasors = []
    for _ in range(n_captures):
        a, b = _capture_dual(handle)
        Za = _demod_iq(a, freq_hz)
        Zb = _demod_iq(b, freq_hz)
        baseline_phasors.append(Za / Zb)

    baseline_mean = np.mean(baseline_phasors)

    # ── Plate measurement: relay ON ──────────────────────────────
    mux.select(relay)
    time.sleep(0.3)
    _set_cw(handle, freq_hz)
    time.sleep(SETTLE_S)

    raw_phasors = []       # Za/Zb with plate
    acoustic_phasors = []  # (Za/Zb) - baseline = acoustic only
    raw_phases = []
    acoustic_phases = []
    magnitudes_raw = []
    magnitudes_acoustic = []

    for _ in range(n_captures):
        a, b = _capture_dual(handle)
        Za = _demod_iq(a, freq_hz)
        Zb = _demod_iq(b, freq_hz)
        ratio = Za / Zb
        acoustic = ratio - baseline_mean

        raw_phasors.append(ratio)
        acoustic_phasors.append(acoustic)
        raw_phases.append(np.angle(ratio))
        acoustic_phases.append(np.angle(acoustic))
        magnitudes_raw.append(abs(ratio))
        magnitudes_acoustic.append(abs(acoustic))

    raw_phases = np.array(raw_phases)
    acoustic_phases = np.array(acoustic_phases)
    magnitudes_raw = np.array(magnitudes_raw)
    magnitudes_acoustic = np.array(magnitudes_acoustic)

    # Stats
    sigma_raw = circular_std(raw_phases)
    sigma_acoustic = circular_std(acoustic_phases)
    baseline_sigma = circular_std([np.angle(p) for p in baseline_phasors])

    # Acoustic magnitude: how much does the plate contribute?
    mean_mag_raw = float(np.mean(magnitudes_raw))
    mean_mag_acoustic = float(np.mean(magnitudes_acoustic))
    mean_mag_baseline = float(abs(baseline_mean))
    acoustic_fraction = mean_mag_acoustic / mean_mag_raw if mean_mag_raw > 0 else 0

    stable_raw = sigma_raw < PHASE_STABLE_THRESHOLD
    stable_acoustic = sigma_acoustic < PHASE_STABLE_THRESHOLD

    return {
        'freq_hz': int(freq_hz),
        'n_captures': n_captures,

        # Raw referenced (electrical + acoustic combined)
        'raw_phase_std_rad': float(sigma_raw),
        'raw_phase_std_deg': float(np.degrees(sigma_raw)),
        'raw_phase_mean_rad': float(circular_mean(raw_phases)),
        'raw_mag_mean': mean_mag_raw,
        'raw_mag_std': float(np.std(magnitudes_raw)),
        'raw_stable': stable_raw,

        # Acoustic only (baseline subtracted)
        'acoustic_phase_std_rad': float(sigma_acoustic),
        'acoustic_phase_std_deg': float(np.degrees(sigma_acoustic)),
        'acoustic_phase_mean_rad': float(circular_mean(acoustic_phases)),
        'acoustic_mag_mean': mean_mag_acoustic,
        'acoustic_mag_std': float(np.std(magnitudes_acoustic)),
        'acoustic_stable': stable_acoustic,
        'acoustic_fraction': float(acoustic_fraction),

        # Baseline (electrical only)
        'baseline_mag': mean_mag_baseline,
        'baseline_phase_std_rad': float(baseline_sigma),

        # Per-capture data for later analysis
        'raw_phases_rad': raw_phases.tolist(),
        'acoustic_phases_rad': acoustic_phases.tolist(),
        'raw_magnitudes': magnitudes_raw.tolist(),
        'acoustic_magnitudes': magnitudes_acoustic.tolist(),
    }


# ── Per-plate measurement ────────────────────────────────────────

def run_plate(handle, mux, plate, modes, n_captures):
    relay = PLATE_RELAY[plate]

    print(f"\n  ┌──────────────────────────────────────────────────")
    print(f"  │ Plate {plate}  (relay {relay})")
    print(f"  │ {len(modes)} modes × {n_captures} captures each")
    print(f"  │ Protocol: relay-OFF baseline → relay-ON → subtract")
    print(f"  └──────────────────────────────────────────────────")

    mode_results = []
    for j, (freq_hz, snr_db) in enumerate(modes):
        print(f"    [{j+1}/{len(modes)}] {freq_hz:>6.0f} Hz (SNR {snr_db:.1f} dB) ...",
              end='', flush=True)
        t0 = time.time()
        result = measure_phase_stability(handle, mux, relay, freq_hz, n_captures)
        dt = time.time() - t0
        result['census_snr_db'] = float(snr_db)

        tag_raw = '✓' if result['raw_stable'] else '✗'
        tag_acou = '✓' if result['acoustic_stable'] else '✗'
        print(f"  raw σ={result['raw_phase_std_deg']:5.1f}°[{tag_raw}]"
              f"  acoustic σ={result['acoustic_phase_std_deg']:5.1f}°[{tag_acou}]"
              f"  frac={result['acoustic_fraction']:.3f}"
              f"  ({dt:.1f}s)")
        mode_results.append(result)

    # Plate summary
    n_raw_stable = sum(1 for r in mode_results if r['raw_stable'])
    n_acou_stable = sum(1 for r in mode_results if r['acoustic_stable'])
    pct_raw = 100 * n_raw_stable / len(mode_results) if mode_results else 0
    pct_acou = 100 * n_acou_stable / len(mode_results) if mode_results else 0

    raw_sigmas = [r['raw_phase_std_rad'] for r in mode_results]
    acou_sigmas = [r['acoustic_phase_std_rad'] for r in mode_results]

    print(f"\n    Plate {plate}: raw={n_raw_stable}/{len(mode_results)} stable"
          f"  acoustic={n_acou_stable}/{len(mode_results)} stable")
    print(f"    Raw σ:  {min(raw_sigmas):.3f} – {max(raw_sigmas):.3f} rad"
          f"  (med {np.median(raw_sigmas):.3f})")
    print(f"    Acou σ: {min(acou_sigmas):.3f} – {max(acou_sigmas):.3f} rad"
          f"  (med {np.median(acou_sigmas):.3f})")

    return {
        'plate': plate,
        'relay': relay,
        'n_modes': len(mode_results),
        'n_raw_stable': n_raw_stable,
        'n_acoustic_stable': n_acou_stable,
        'pct_raw_stable': float(pct_raw),
        'pct_acoustic_stable': float(pct_acou),
        'modes': mode_results,
    }


# ── Entry point ────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Phase 1.6 Step 5 v2: Phase Stability with Ch B reference")
    parser.add_argument('port', help="Arduino relay mux serial port")
    parser.add_argument('--census', required=True,
                        help="Path to plate census JSON")
    parser.add_argument('--plates', nargs='+', default=['A', 'B', 'G', 'D', 'H'],
                        choices=['A', 'B', 'G', 'D', 'H'],
                        help="Plates to test (default: all 5)")
    parser.add_argument('--modes', type=int, default=MODES_PER_PLATE,
                        help=f"Modes per plate (default: {MODES_PER_PLATE})")
    parser.add_argument('--captures', type=int, default=None,
                        help="Captures per mode (overrides --fast)")
    parser.add_argument('--fast', action='store_true',
                        help="Fewer captures for quick check")
    args = parser.parse_args()

    n_captures = args.captures or (N_CAPTURES_FAST if args.fast else N_CAPTURES)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')

    out_dir = Path('data/results/lab/plate_exps')
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"phase_stability_v2_{ts}.json"

    # Load modes from census
    plate_modes = {}
    for plate in args.plates:
        plate_modes[plate] = load_top_modes(args.census, plate, args.modes)

    total_modes = sum(len(m) for m in plate_modes.values())
    # Each mode: N baseline captures + N plate captures + settle time
    est_time = total_modes * (2 * SETTLE_S + 2 * n_captures * 0.006 + 1)

    print("=" * 70)
    print("  PHASE 1.6 STEP 5 v2: PHASE STABILITY (Ch B REFERENCE)")
    print("=" * 70)
    print(f"  Plates: {', '.join(args.plates)}")
    print(f"  Modes per plate: {args.modes}")
    print(f"  Captures per mode: {n_captures} (× 2: baseline + plate)")
    print(f"  Total captures: {total_modes * n_captures * 2}")
    print(f"  Samples/capture: {N_SAMPLES} (dual-channel)")
    print(f"  Threshold: σ < {PHASE_STABLE_THRESHOLD} rad ({np.degrees(PHASE_STABLE_THRESHOLD):.1f}°)")
    print(f"  Census: {args.census}")
    print(f"  Est. time: ~{est_time/60:.0f} min")
    print(f"  Wiring: AWG → tee → plates(ChA) + ChB(ref)")
    print("=" * 70)
    sys.stdout.flush()

    handle = _open_scope()
    print(f"  PicoScope opened (Ch A + Ch B ±1V DC, {N_SAMPLES} samples)")

    mux = RelayMux(port=args.port)
    mux.open()
    print(f"  Relay mux connected on {args.port}")

    all_results = []
    t0 = time.time()

    try:
        for plate in args.plates:
            modes = plate_modes[plate]
            result = run_plate(handle, mux, plate, modes, n_captures)
            all_results.append(result)
    finally:
        try:
            _stop_awg(handle)
        except Exception:
            pass
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
    print(f"  {'Plate':>5s}  {'Raw':>6s}  {'Acou':>6s}  {'Total':>5s}  "
          f"{'σ_raw':>7s}  {'σ_acou':>7s}  {'Frac':>6s}")
    print(f"  {'─'*5}  {'─'*6}  {'─'*6}  {'─'*5}  {'─'*7}  {'─'*7}  {'─'*6}")

    total_raw_stable = 0
    total_acou_stable = 0
    total_tested = 0

    for r in all_results:
        raw_sigmas = [m['raw_phase_std_rad'] for m in r['modes']]
        acou_sigmas = [m['acoustic_phase_std_rad'] for m in r['modes']]
        fracs = [m['acoustic_fraction'] for m in r['modes']]
        total_raw_stable += r['n_raw_stable']
        total_acou_stable += r['n_acoustic_stable']
        total_tested += r['n_modes']
        print(f"  {r['plate']:>5s}"
              f"  {r['n_raw_stable']}/{r['n_modes']}"
              f"  {r['n_acoustic_stable']}/{r['n_modes']}"
              f"  {r['n_modes']:>5d}"
              f"  {np.median(raw_sigmas):>6.3f}"
              f"  {np.median(acou_sigmas):>6.3f}"
              f"  {np.median(fracs):>5.3f}")

    pct_raw = 100 * total_raw_stable / total_tested if total_tested > 0 else 0
    pct_acou = 100 * total_acou_stable / total_tested if total_tested > 0 else 0

    print(f"\n  Raw referenced:  {total_raw_stable}/{total_tested} modes stable ({pct_raw:.0f}%)")
    print(f"  Acoustic only:   {total_acou_stable}/{total_tested} modes stable ({pct_acou:.0f}%)")
    print(f"  Target: >50% of modes with σ < {PHASE_STABLE_THRESHOLD} rad")

    if pct_raw >= 50:
        print(f"  RAW RESULT:     ✅ PASS")
    else:
        print(f"  RAW RESULT:     ❌ FAIL")

    if pct_acou >= 50:
        print(f"  ACOUSTIC RESULT: ✅ PASS")
    else:
        print(f"  ACOUSTIC RESULT: ❌ FAIL")

    print(f"\n  Rod E03 baseline: 15% stable (σ = 1.71 rad)")
    print(f"  v1 (no ref):     0% stable (σ ≈ 2.0 rad) — DDS phase noise")

    # ── Save ───────────────────────────────────────────────────────
    output = {
        'experiment': 'Phase 1.6 Step 5 v2: Phase Stability (Ch B Reference)',
        'timestamp': datetime.now().isoformat(),
        'duration_s': elapsed,
        'n_captures': n_captures,
        'modes_per_plate': args.modes,
        'fast_mode': args.fast,
        'settle_s': SETTLE_S,
        'n_samples_per_capture': N_SAMPLES,
        'phase_stable_threshold_rad': PHASE_STABLE_THRESHOLD,
        'plates_tested': args.plates,
        'census_path': args.census,
        'wiring': 'AWG → BNC tee → plates(ChA) + ChB(direct ref)',
        'method': 'complex ratio Za/Zb cancels DDS phase; baseline subtraction isolates acoustic',
        'overall_raw_stable': total_raw_stable,
        'overall_acoustic_stable': total_acou_stable,
        'overall_tested': total_tested,
        'overall_pct_raw_stable': pct_raw,
        'overall_pct_acoustic_stable': pct_acou,
        'pass_raw': pct_raw >= 50,
        'pass_acoustic': pct_acou >= 50,
        'results': all_results,
    }

    with open(out_path, 'w') as f:
        json.dump(output, f, indent=2, cls=_NumpyEncoder)
    print(f"\n  Results saved: {out_path}")


if __name__ == '__main__':
    main()
