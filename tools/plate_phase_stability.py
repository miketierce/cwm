#!/usr/bin/env python3
"""
Phase 1.6 Step 5: Phase Stability (E03 Plate Revisit)
═════════════════════════════════════════════════════════

Measure how stable the phase is at each plate's strongest resonances
under continuous CW excitation.

Protocol per mode:
  1. Drive CW at mode frequency → steady state (0.5 s settle)
  2. Capture 100 waveforms back-to-back
  3. I/Q demodulate each capture → extract phase
  4. Compute circular standard deviation of phase
  5. Mode is "stable" if σ_phase < 0.5 rad

Rod E03 result:  only 15% of modes stable (σ = 1.71 rad)
Target (plates): >50% of modes with σ_phase < 0.5 rad

Usage:
  python tools/plate_phase_stability.py /dev/cu.usbserial-11310 \\
      --census data/results/lab/plate_exps/plate_census_20260418_221958.json
  python tools/plate_phase_stability.py /dev/cu.usbserial-11310 \\
      --census data/results/lab/plate_exps/plate_census_20260418_221958.json --fast
  python tools/plate_phase_stability.py /dev/cu.usbserial-11310 \\
      --census data/results/lab/plate_exps/plate_census_20260418_221958.json --plates A G
"""

import argparse, ctypes, json, os, sys, time
from datetime import datetime
from pathlib import Path

import numpy as np

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
N_CAPTURES = 100          # captures per mode (full)
N_CAPTURES_FAST = 30      # captures per mode (--fast)
SETTLE_S = 0.5            # CW settle time before captures
MODES_PER_PLATE = 5       # top-N modes by SNR
PHASE_STABLE_THRESHOLD = 0.5   # rad — mode is "stable" if σ < this

# ── Plate → relay mapping ─────────────────────────────────────────
PLATE_RELAY = {'A': 1, 'B': 2, 'G': 3, 'D': 5, 'H': 7}
# Census key corresponding to the NE channel for each plate
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


# ── Circular statistics ───────────────────────────────────────────

def circular_mean(phases):
    """Mean direction of angles (radians)."""
    return np.arctan2(np.mean(np.sin(phases)), np.mean(np.cos(phases)))


def circular_std(phases):
    """Circular standard deviation (radians). 0 = perfectly stable."""
    R = np.hypot(np.mean(np.cos(phases)), np.mean(np.sin(phases)))
    R = min(R, 1.0)  # clamp numerical noise
    return np.sqrt(-2.0 * np.log(R))


# ── Census loader ─────────────────────────────────────────────────

def load_top_modes(census_path, plate, n_modes=MODES_PER_PLATE):
    """Load top-N modes by SNR for a plate from census JSON."""
    with open(census_path) as f:
        census = json.load(f)

    key = PLATE_CENSUS_KEY[plate]
    peaks = census['results'][key]['peaks']
    by_snr = sorted(peaks, key=lambda m: m['snr_db'], reverse=True)
    top = by_snr[:n_modes]
    return [(m['freq_hz'], m['snr_db']) for m in top]


# ── Per-mode measurement ─────────────────────────────────────────

def measure_phase_stability(handle, freq_hz, n_captures):
    """Drive CW, capture N waveforms, return phase statistics."""
    _set_cw(handle, freq_hz)
    time.sleep(SETTLE_S)

    magnitudes = []
    phases = []
    for i in range(n_captures):
        wf = _capture(handle)
        mag, phi = _demod_iq(wf, freq_hz)
        magnitudes.append(mag)
        phases.append(phi)

    magnitudes = np.array(magnitudes)
    phases = np.array(phases)

    sigma = circular_std(phases)
    mean_phase = circular_mean(phases)
    stable = sigma < PHASE_STABLE_THRESHOLD

    return {
        'freq_hz': int(freq_hz),
        'n_captures': n_captures,
        'mag_mean': float(np.mean(magnitudes)),
        'mag_std': float(np.std(magnitudes)),
        'mag_cv': float(np.std(magnitudes) / np.mean(magnitudes)) if np.mean(magnitudes) > 0 else 0.0,
        'phase_mean_rad': float(mean_phase),
        'phase_std_rad': float(sigma),
        'phase_std_deg': float(np.degrees(sigma)),
        'stable': stable,
        'phases_rad': phases.tolist(),
        'magnitudes': magnitudes.tolist(),
    }


# ── Per-plate measurement ────────────────────────────────────────

def run_plate(handle, mux, plate, modes, n_captures):
    """Measure phase stability at each mode for one plate."""
    relay = PLATE_RELAY[plate]
    mux.select(relay)
    time.sleep(0.3)

    print(f"\n  ┌──────────────────────────────────────────────────")
    print(f"  │ Plate {plate}  (relay {relay})")
    print(f"  │ {len(modes)} modes × {n_captures} captures each")
    print(f"  └──────────────────────────────────────────────────")

    mode_results = []
    for j, (freq_hz, snr_db) in enumerate(modes):
        print(f"    [{j+1}/{len(modes)}] {freq_hz:>6.0f} Hz (SNR {snr_db:.1f} dB) ...", end='', flush=True)
        t0 = time.time()
        result = measure_phase_stability(handle, freq_hz, n_captures)
        dt = time.time() - t0
        result['census_snr_db'] = float(snr_db)

        tag = '✓ STABLE' if result['stable'] else '✗ unstable'
        print(f"  σ={result['phase_std_deg']:5.1f}°  ({result['phase_std_rad']:.3f} rad)"
              f"  mag={result['mag_mean']:.0f}±{result['mag_std']:.0f}"
              f"  [{tag}]  ({dt:.1f}s)")
        mode_results.append(result)

    # Plate summary
    n_stable = sum(1 for r in mode_results if r['stable'])
    pct = 100 * n_stable / len(mode_results) if mode_results else 0

    print(f"\n    Plate {plate} summary: {n_stable}/{len(mode_results)} modes stable ({pct:.0f}%)")
    sigmas = [r['phase_std_rad'] for r in mode_results]
    print(f"    σ range: {min(sigmas):.3f} – {max(sigmas):.3f} rad"
          f"  (median {np.median(sigmas):.3f})")

    return {
        'plate': plate,
        'relay': relay,
        'n_modes': len(mode_results),
        'n_stable': n_stable,
        'pct_stable': float(pct),
        'modes': mode_results,
    }


# ── AWG-off noise floor control ──────────────────────────────────

def measure_noise_floor(handle, modes):
    """With AWG off, measure at each mode frequency to get baseline noise."""
    _stop_awg(handle)
    time.sleep(0.1)

    results = []
    for freq_hz, snr_db in modes:
        wf = _capture(handle)
        mag, phi = _demod_iq(wf, freq_hz)
        results.append({'freq_hz': int(freq_hz), 'mag': float(mag), 'phase_rad': float(phi)})
    return results


# ── Entry point ────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Phase 1.6 Step 5: Phase Stability (E03 revisit)")
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
    out_path = out_dir / f"phase_stability_{ts}.json"

    # Load modes from census
    plate_modes = {}
    for plate in args.plates:
        plate_modes[plate] = load_top_modes(args.census, plate, args.modes)

    total_modes = sum(len(m) for m in plate_modes.values())
    est_time = total_modes * (SETTLE_S + n_captures * 0.015 + 1)  # rough estimate

    print("=" * 70)
    print("  PHASE 1.6 STEP 5: PHASE STABILITY (E03 REVISIT)")
    print(f"  Plates: {', '.join(args.plates)}")
    print(f"  Modes per plate: {args.modes}")
    print(f"  Captures per mode: {n_captures}")
    print(f"  Total measurements: {total_modes} modes × {n_captures} captures"
          f" = {total_modes * n_captures}")
    print(f"  Threshold: σ < {PHASE_STABLE_THRESHOLD} rad ({np.degrees(PHASE_STABLE_THRESHOLD):.1f}°)")
    print(f"  Census: {args.census}")
    print(f"  Est. time: ~{est_time/60:.0f} min")
    print("=" * 70)
    sys.stdout.flush()

    handle = _open_scope()
    print(f"  PicoScope opened (Ch A ±1V DC)")

    mux = RelayMux(port=args.port)
    mux.open()
    print(f"  Relay mux connected on {args.port}")

    all_results = []
    noise_floors = {}
    t0 = time.time()

    try:
        for plate in args.plates:
            modes = plate_modes[plate]

            # Noise floor measurement first (AWG off)
            mux.select(PLATE_RELAY[plate])
            time.sleep(0.3)
            nf = measure_noise_floor(handle, modes)
            noise_floors[plate] = nf

            # Phase stability measurement (CW drive)
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
    print(f"  {'Plate':>5s}  {'Stable':>8s}  {'Total':>5s}  {'Pct':>5s}  "
          f"{'σ_min':>7s}  {'σ_med':>7s}  {'σ_max':>7s}")
    print(f"  {'─'*5}  {'─'*8}  {'─'*5}  {'─'*5}  {'─'*7}  {'─'*7}  {'─'*7}")

    total_stable = 0
    total_tested = 0
    for r in all_results:
        sigmas = [m['phase_std_rad'] for m in r['modes']]
        total_stable += r['n_stable']
        total_tested += r['n_modes']
        print(f"  {r['plate']:>5s}  {r['n_stable']:>8d}  {r['n_modes']:>5d}  "
              f"{r['pct_stable']:>4.0f}%  "
              f"{min(sigmas):>6.3f}  {np.median(sigmas):>6.3f}  {max(sigmas):>6.3f}")

    overall_pct = 100 * total_stable / total_tested if total_tested > 0 else 0
    print(f"\n  Overall: {total_stable}/{total_tested} modes stable ({overall_pct:.0f}%)")
    print(f"  Target:  >50% of modes with σ < {PHASE_STABLE_THRESHOLD} rad")

    if overall_pct >= 50:
        print(f"  RESULT: ✅ PASS — phase stability meets target")
    else:
        print(f"  RESULT: ❌ FAIL — phase stability below target")

    print(f"\n  Rod E03 baseline: 15% stable (σ = 1.71 rad)")
    if overall_pct > 15:
        print(f"  Improvement over rods: {overall_pct:.0f}% vs 15%")
    else:
        print(f"  No improvement over rod E03 result")

    # ── Save ───────────────────────────────────────────────────────
    output = {
        'experiment': 'Phase 1.6 Step 5: Phase Stability (E03 Revisit)',
        'timestamp': datetime.now().isoformat(),
        'duration_s': elapsed,
        'n_captures': n_captures,
        'modes_per_plate': args.modes,
        'fast_mode': args.fast,
        'settle_s': SETTLE_S,
        'phase_stable_threshold_rad': PHASE_STABLE_THRESHOLD,
        'plates_tested': args.plates,
        'census_path': args.census,
        'overall_stable': total_stable,
        'overall_tested': total_tested,
        'overall_pct_stable': overall_pct,
        'pass': overall_pct >= 50,
        'noise_floors': noise_floors,
        'results': all_results,
    }

    with open(out_path, 'w') as f:
        json.dump(output, f, indent=2, cls=_NumpyEncoder)
    print(f"\n  Results saved: {out_path}")


if __name__ == '__main__':
    main()
