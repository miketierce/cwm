#!/usr/bin/env python3
"""
Classical Entanglement CHSH-Analog Experiment

Tests whether the glass plate's frequency × phase degrees of freedom are
non-separable ("classically entangled") by measuring a CHSH-like S parameter.

Background:
  Classical entanglement (Kagalwala et al., Nature Photonics 2013) refers to
  non-separable correlations between DOFs of a SINGLE classical field. When two
  DDS sources drive shared eigenmodes, the plate's state cannot be factored as
  |frequency⟩ ⊗ |phase⟩ because nonlinear mode mixing creates inseparable
  correlations. If S > 2, the frequency×phase state is non-separable.

  This would be the first demonstration of classical entanglement in an
  acoustic system.

Protocol:
  1. DDS1 drives shared eigenmode f₁; DDS2 drives shared eigenmode f₂
  2. Two receiver positions measured via relay mux
  3. Alice's setting: DDS1 phase ∈ {0°, 45°}
  4. Bob's setting: DDS2 phase ∈ {22.5°, 67.5°}
  5. For each of the 4 (θ_A, θ_B) pairs × N trials:
     - Set phases on both DDS boards
     - Capture spectrum at receiver R1
     - Switch mux, capture spectrum at receiver R2
     - Extract signed amplitudes at f₁ and f₂
  6. Compute correlation E(θ_A, θ_B) and CHSH S parameter

Usage:
  python tools/chsh_classical_entanglement.py
  python tools/chsh_classical_entanglement.py --trials 50 --navg 30
  python tools/chsh_classical_entanglement.py --dry-run   # analysis only, no hardware

References:
  Wang, Hou et al. (2024) arXiv:2412.03022 — path identity entanglement
  Kagalwala et al. (2013) Nature Photonics 7, 72–78 — classical entanglement
  Spreeuw (1998) PRA 63, 062302 — classical entanglement concept
"""
import argparse
import ctypes
import json
import sys
import time
from pathlib import Path

import numpy as np

# ─── Arguments ───────────────────────────────────────────────────
parser = argparse.ArgumentParser(
    description='CHSH-analog test for acoustic classical entanglement')
parser.add_argument('--trials', type=int, default=30,
                    help='Trials per measurement setting (default: 30)')
parser.add_argument('--navg', type=int, default=20,
                    help='Coherent averages per spectrum (default: 20)')
parser.add_argument('--settle-ms', type=int, default=200,
                    help='Settle time after phase change, ms (default: 200)')
parser.add_argument('--window-hz', type=float, default=2000,
                    help='Energy integration window around mode, Hz')
parser.add_argument('--dry-run', action='store_true',
                    help='Skip hardware, analyze existing data')
args = parser.parse_args()

DATA_DIR = Path(__file__).parent.parent / 'data' / 'results'
OUT_PATH = DATA_DIR / 'chsh_classical_entanglement.json'

# ─── Shared eigenmodes (from April 24 phase sweep) ──────────────
# These are the three frequency pairs where DDS1 and DDS2 share an eigenmode.
# Using the two with best measured phase contrast.
SHARED_MODES = {
    'mode_295k': {
        'label': '~295 kHz',
        'dds1_freq': 295270,
        'dds2_freq': 294228,
        'eigenmode_freq': 294750,  # approximate center
    },
    'mode_356k': {
        'label': '~356 kHz',
        'dds1_freq': 355772,
        'dds2_freq': 356595,
        'eigenmode_freq': 356184,
    },
}

# Two receiver channels for spatial diversity
RECEIVER_R1 = {'mux_ch': 5, 'label': 'D-NE (relay 4)'}
RECEIVER_R2 = {'mux_ch': 1, 'label': 'A-NE (relay 0)'}

# CHSH measurement settings (degrees)
# Alice controls DDS1 phase; Bob controls DDS2 phase.
# Standard CHSH angles: {0, π/4} × {π/8, 3π/8}
ALICE_SETTINGS = [0.0, 45.0]     # degrees
BOB_SETTINGS = [22.5, 67.5]      # degrees

# ─── PicoScope constants ────────────────────────────────────────
TIMEBASE = 7
N_SAMPLES = 8064
DT = 1280e-9

# ─── Phase conversion ───────────────────────────────────────────
def deg_to_phase_reg(deg):
    """Convert degrees to AD9833 12-bit phase register value (0–4095)."""
    return int(round((deg % 360) / 360 * 4096)) % 4096


# ─── Hardware setup ──────────────────────────────────────────────
def setup_hardware():
    """Initialize PicoScope, relay mux, and DDS controller."""
    ps = ctypes.CDLL(
        "/Applications/PicoScope 7 T&M Early Access.app"
        "/Contents/Resources/libps2000.dylib")
    ps.ps2000_set_sig_gen_built_in.argtypes = [
        ctypes.c_int16, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32,
        ctypes.c_float, ctypes.c_float, ctypes.c_float, ctypes.c_float,
        ctypes.c_int32, ctypes.c_int32]

    # Close stale handles
    for h in range(1, 5):
        ps.ps2000_close_unit(h)
    time.sleep(0.5)

    handle = ps.ps2000_open_unit()
    print(f"PicoScope handle: {handle}")
    if handle <= 0:
        print("ERROR: Could not open PicoScope")
        sys.exit(1)

    # Channel A on, Channel B off; ±100 mV range (range 7)
    ps.ps2000_set_channel(handle, 0, 1, 1, 7)
    ps.ps2000_set_channel(handle, 1, 0, 1, 7)
    # AWG off (no parasitic drive)
    ps.ps2000_set_sig_gen_built_in(
        handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0)

    import serial
    mux = serial.Serial('/dev/cu.usbserial-11310', 9600, timeout=1)
    time.sleep(2)
    mux.reset_input_buffer()

    dds = serial.Serial('/dev/cu.usbserial-11330', 115200, timeout=2)
    time.sleep(2)
    dds.reset_input_buffer()

    return ps, handle, dds, mux


def dds_cmd(dds, cmd):
    """Send command to DDS controller, return response."""
    dds.write(f'{cmd}\n'.encode())
    time.sleep(0.01)
    return dds.readline().decode().strip()


def set_mux(mux, channel):
    """Set relay mux to specified channel."""
    mux.write(f'{channel}\n'.encode())
    time.sleep(0.15)
    mux.readline()


def capture(ps, handle):
    """Single PicoScope capture, return raw ADC array."""
    buf = (ctypes.c_int16 * N_SAMPLES)()
    ov = ctypes.c_int16(0)
    ps.ps2000_set_trigger(handle, 5, 0, 0, 0, 0)  # free-running
    ms = ctypes.c_int32(0)
    ps.ps2000_run_block(handle, N_SAMPLES, TIMEBASE, 1, ctypes.byref(ms))
    for _ in range(5000):
        if ps.ps2000_ready(handle):
            break
        time.sleep(0.001)
    else:
        ps.ps2000_stop(handle)
        return np.zeros(N_SAMPLES)
    ps.ps2000_get_values(handle, ctypes.byref(buf), None, None, None,
                         ctypes.byref(ov), N_SAMPLES)
    return np.array(buf, dtype=np.float64)


def coherent_avg_spectrum(ps, handle, n_avg):
    """Capture n_avg frames, average in time domain, return (freq, complex_fft)."""
    frames = [capture(ps, handle) for _ in range(n_avg)]
    avg = np.mean(frames, axis=0)
    d = avg - np.mean(avg)
    w = d * np.hanning(len(d))
    nfft = len(d) * 4  # zero-pad for frequency resolution
    fft_complex = np.fft.rfft(w, n=nfft)
    freq = np.fft.rfftfreq(nfft, d=DT)
    return freq, fft_complex


def extract_mode_amplitude(fft_complex, freq, target_freq, window_hz):
    """
    Extract signed amplitude at target frequency.

    Returns the REAL part of the complex FFT at the peak bin within the
    window. The sign carries phase information — this is essential for
    the CHSH correlation computation.
    """
    mask = np.abs(freq - target_freq) < window_hz
    if not np.any(mask):
        return 0.0
    sub = fft_complex[mask]
    sub_freq = freq[mask]
    peak_idx = np.argmax(np.abs(sub))
    # Return the complex value at peak — we'll use real part for sign
    return complex(sub[peak_idx])


def mode_energy(fft_complex, freq, target_freq, window_hz):
    """Total spectral energy around target frequency."""
    mask = np.abs(freq - target_freq) < window_hz
    return float(np.sum(np.abs(fft_complex[mask]) ** 2)) if np.any(mask) else 0.0


def cleanup(ps, handle, dds, mux):
    """Shut down all hardware safely."""
    dds_cmd(dds, 'Foff')
    dds_cmd(dds, 'P1:0')
    dds_cmd(dds, 'P2:0')
    ps.ps2000_set_sig_gen_built_in(
        handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0)
    ps.ps2000_stop(handle)
    ps.ps2000_close_unit(handle)
    mux.write(b'0\n')
    mux.close()
    dds.close()


# ═════════════════════════════════════════════════════════════════
#  CORE MEASUREMENT
# ═════════════════════════════════════════════════════════════════

def measure_setting(ps, handle, dds, mux, mode_cfg,
                    alice_deg, bob_deg, n_trials):
    """
    Measure one (θ_A, θ_B) setting for n_trials.

    For each trial:
      1. Set DDS1 phase to alice_deg, DDS2 phase to bob_deg
      2. Capture spectrum at R1
      3. Switch mux, capture spectrum at R2
      4. Extract complex amplitude at both modes from both receivers

    Returns dict with raw measurements.
    """
    f1 = mode_cfg['dds1_freq']
    f2 = mode_cfg['dds2_freq']
    ef = mode_cfg['eigenmode_freq']
    alice_reg = deg_to_phase_reg(alice_deg)
    bob_reg = deg_to_phase_reg(bob_deg)

    results = {
        'alice_deg': alice_deg,
        'bob_deg': bob_deg,
        'alice_reg': alice_reg,
        'bob_reg': bob_reg,
        'r1_mode1_complex': [],  # complex amplitude of mode 1 at receiver 1
        'r1_mode2_complex': [],  # complex amplitude of mode 2 at receiver 1
        'r2_mode1_complex': [],  # complex amplitude of mode 1 at receiver 2
        'r2_mode2_complex': [],  # complex amplitude of mode 2 at receiver 2
        'r1_mode1_energy': [],
        'r2_mode1_energy': [],
    }

    # Set phases
    dds_cmd(dds, f'P1:{alice_reg}')
    dds_cmd(dds, f'P2:{bob_reg}')
    time.sleep(args.settle_ms / 1000.0)

    for trial in range(n_trials):
        # Measure at receiver R1
        set_mux(mux, RECEIVER_R1['mux_ch'])
        freq, fft1 = coherent_avg_spectrum(ps, handle, args.navg)
        a1_m1 = extract_mode_amplitude(fft1, freq, ef, args.window_hz)
        a1_m2 = extract_mode_amplitude(
            fft1, freq, SHARED_MODES['mode_356k']['eigenmode_freq'],
            args.window_hz)
        e1 = mode_energy(fft1, freq, ef, args.window_hz)

        # Measure at receiver R2
        set_mux(mux, RECEIVER_R2['mux_ch'])
        freq, fft2 = coherent_avg_spectrum(ps, handle, args.navg)
        a2_m1 = extract_mode_amplitude(fft2, freq, ef, args.window_hz)
        a2_m2 = extract_mode_amplitude(
            fft2, freq, SHARED_MODES['mode_356k']['eigenmode_freq'],
            args.window_hz)
        e2 = mode_energy(fft2, freq, ef, args.window_hz)

        results['r1_mode1_complex'].append([a1_m1.real, a1_m1.imag])
        results['r1_mode2_complex'].append([a1_m2.real, a1_m2.imag])
        results['r2_mode1_complex'].append([a2_m1.real, a2_m1.imag])
        results['r2_mode2_complex'].append([a2_m2.real, a2_m2.imag])
        results['r1_mode1_energy'].append(e1)
        results['r2_mode1_energy'].append(e2)

    return results


def compute_correlation(setting_data):
    """
    Compute E(θ_A, θ_B) from measurement data.

    Strategy: Use the product of signed amplitudes at the two modes
    across the two spatial receivers as the joint measurement outcome.

    For each trial:
      outcome_A = sign(Re[R1_mode1] − Re[R2_mode1])  (spatial contrast at mode 1)
      outcome_B = sign(Re[R1_mode2] − Re[R2_mode2])  (spatial contrast at mode 2)
      product = outcome_A × outcome_B

    E = <product> = (N_{++} + N_{--} − N_{+-} − N_{-+}) / N_total

    If modes are separable (independent), outcomes A and B are uncorrelated → E ≈ 0.
    If modes are non-separable, phase settings create correlated outcomes → |E| > 0.
    """
    r1_m1 = np.array(setting_data['r1_mode1_complex'])
    r1_m2 = np.array(setting_data['r1_mode2_complex'])
    r2_m1 = np.array(setting_data['r2_mode1_complex'])
    r2_m2 = np.array(setting_data['r2_mode2_complex'])

    # Spatial contrast for each mode
    # Use real part (carries phase-dependent sign) of complex amplitude
    diff_m1 = r1_m1[:, 0] - r2_m1[:, 0]  # Re[R1_mode1] - Re[R2_mode1]
    diff_m2 = r1_m2[:, 0] - r2_m2[:, 0]  # Re[R1_mode2] - Re[R2_mode2]

    outcome_a = np.sign(diff_m1)
    outcome_b = np.sign(diff_m2)

    # Replace zeros with +1 (rare, but avoid NaN)
    outcome_a[outcome_a == 0] = 1
    outcome_b[outcome_b == 0] = 1

    products = outcome_a * outcome_b
    n_pp = np.sum((outcome_a > 0) & (outcome_b > 0))
    n_mm = np.sum((outcome_a < 0) & (outcome_b < 0))
    n_pm = np.sum((outcome_a > 0) & (outcome_b < 0))
    n_mp = np.sum((outcome_a < 0) & (outcome_b > 0))

    E = float(np.mean(products))
    n_total = len(products)

    # Standard error
    E_err = float(np.std(products) / np.sqrt(n_total)) if n_total > 1 else 0

    return {
        'E': E,
        'E_err': E_err,
        'n_pp': int(n_pp),
        'n_mm': int(n_mm),
        'n_pm': int(n_pm),
        'n_mp': int(n_mp),
        'n_total': int(n_total),
    }


def compute_chsh(correlations):
    """
    Compute S = |E(a1,b1) − E(a1,b2) + E(a2,b1) + E(a2,b2)|

    Classical separable bound: S ≤ 2
    Classical entangled (non-separable) max: S = 2√2 ≈ 2.83
    """
    E = {}
    for key, c in correlations.items():
        E[key] = c['E']

    a1, a2 = ALICE_SETTINGS
    b1, b2 = BOB_SETTINGS

    S_raw = (E[(a1, b1)] - E[(a1, b2)] + E[(a2, b1)] + E[(a2, b2)])
    S = abs(S_raw)

    # Error propagation (assuming independent)
    errs = [correlations[(a1, b1)]['E_err'],
            correlations[(a1, b2)]['E_err'],
            correlations[(a2, b1)]['E_err'],
            correlations[(a2, b2)]['E_err']]
    S_err = np.sqrt(sum(e**2 for e in errs))

    sigma_above_2 = (S - 2.0) / S_err if S_err > 0 else 0

    return {
        'S': float(S),
        'S_raw': float(S_raw),
        'S_err': float(S_err),
        'sigma_above_classical': float(sigma_above_2),
        'E_values': {f"E({a},{b})": float(E[(a, b)])
                     for (a, b) in E},
    }


# ═════════════════════════════════════════════════════════════════
#  ALTERNATIVE CORRELATION METHODS
# ═════════════════════════════════════════════════════════════════

def compute_correlation_energy(setting_data):
    """
    Alternative: use energy ratio between receivers as continuous observable.

    outcome_A = (E_R1_mode1 − E_R2_mode1) / (E_R1_mode1 + E_R2_mode1)
    outcome_B = similar for mode2

    This gives a continuous [-1, +1] variable per trial, potentially
    more sensitive than the sign-based method.
    """
    r1_e = np.array(setting_data['r1_mode1_energy'])
    r2_e = np.array(setting_data['r2_mode1_energy'])

    # Normalized spatial contrast
    denom = r1_e + r2_e
    denom[denom == 0] = 1  # avoid division by zero
    contrast = (r1_e - r2_e) / denom

    return {
        'mean_contrast': float(np.mean(contrast)),
        'std_contrast': float(np.std(contrast)),
        'contrasts': contrast.tolist(),
    }


# ═════════════════════════════════════════════════════════════════
#  MAIN
# ═════════════════════════════════════════════════════════════════

def main():
    print("=" * 70)
    print(" CHSH-ANALOG CLASSICAL ENTANGLEMENT TEST")
    print(" Acoustic frequency × phase non-separability")
    print("=" * 70)
    print(f"  Trials per setting: {args.trials}")
    print(f"  Coherent averages:  {args.navg}")
    print(f"  Settings: Alice {ALICE_SETTINGS}° × Bob {BOB_SETTINGS}°")
    print(f"  = {len(ALICE_SETTINGS) * len(BOB_SETTINGS)} measurement settings"
          f" × {args.trials} trials = "
          f"{len(ALICE_SETTINGS) * len(BOB_SETTINGS) * args.trials} total")
    print()

    if args.dry_run:
        print("DRY RUN — loading existing data...")
        if not OUT_PATH.exists():
            print(f"ERROR: No data at {OUT_PATH}")
            sys.exit(1)
        with open(OUT_PATH) as f:
            results = json.load(f)
        print_results(results)
        return

    # ─── Hardware init ───────────────────────────────────────────
    ps, handle, dds, mux = setup_hardware()

    try:
        # Configure DDS: both boards driving shared eigenmodes
        mode = SHARED_MODES['mode_295k']
        print(f"\nDriving mode: {mode['label']}")
        print(f"  DDS1: {mode['dds1_freq']} Hz")
        print(f"  DDS2: {mode['dds2_freq']} Hz")

        dds_cmd(dds, 'Foff')
        dds_cmd(dds, 'P1:0')
        dds_cmd(dds, 'P2:0')
        dds_cmd(dds, f"F1:{mode['dds1_freq']}")
        dds_cmd(dds, f"F2:{mode['dds2_freq']}")
        time.sleep(0.5)

        # ─── Baseline: noise floor (DDS off) ────────────────────
        print("\nMeasuring noise baseline...")
        dds_cmd(dds, 'Foff')
        time.sleep(0.3)
        set_mux(mux, RECEIVER_R1['mux_ch'])
        freq, fft_noise = coherent_avg_spectrum(ps, handle, args.navg)
        noise_energy = mode_energy(
            fft_noise, freq, mode['eigenmode_freq'], args.window_hz)
        print(f"  Noise energy at {mode['label']}: {noise_energy:.0f}")

        # Re-enable DDS
        dds_cmd(dds, f"F1:{mode['dds1_freq']}")
        dds_cmd(dds, f"F2:{mode['dds2_freq']}")
        time.sleep(0.5)

        # ─── CHSH measurements ──────────────────────────────────
        all_settings = {}
        correlations = {}

        for alice_deg in ALICE_SETTINGS:
            for bob_deg in BOB_SETTINGS:
                key = (alice_deg, bob_deg)
                print(f"\n{'─' * 50}")
                print(f"  Setting: Alice={alice_deg}°, Bob={bob_deg}°")
                print(f"  Phase regs: P1={deg_to_phase_reg(alice_deg)}, "
                      f"P2={deg_to_phase_reg(bob_deg)}")
                print(f"  Measuring {args.trials} trials...")

                data = measure_setting(
                    ps, handle, dds, mux, mode,
                    alice_deg, bob_deg, args.trials)

                corr = compute_correlation(data)
                energy_corr = compute_correlation_energy(data)

                all_settings[f"{alice_deg}_{bob_deg}"] = {
                    'measurement': data,
                    'correlation': corr,
                    'energy_correlation': energy_corr,
                }
                correlations[key] = corr

                print(f"  E({alice_deg}°, {bob_deg}°) = "
                      f"{corr['E']:.4f} ± {corr['E_err']:.4f}")
                print(f"  Counts: ++ {corr['n_pp']}, "
                      f"-- {corr['n_mm']}, "
                      f"+- {corr['n_pm']}, "
                      f"-+ {corr['n_mp']}")
                print(f"  Energy contrast: "
                      f"{energy_corr['mean_contrast']:.4f} ± "
                      f"{energy_corr['std_contrast']:.4f}")

        # ─── Compute CHSH S parameter ───────────────────────────
        chsh = compute_chsh(correlations)

        # ─── Solo-mode baseline (separability check) ────────────
        # If we also measure with only DDS1 active (no mode mixing),
        # S should be ~0 (perfectly separable)
        print(f"\n{'─' * 50}")
        print("BASELINE: DDS1-only (expect S ≈ 0, separable)")
        dds_cmd(dds, f"F2:0")  # Turn off DDS2
        time.sleep(0.3)

        baseline_correlations = {}
        for alice_deg in ALICE_SETTINGS:
            for bob_deg in BOB_SETTINGS:
                key = (alice_deg, bob_deg)
                dds_cmd(dds, f'P1:{deg_to_phase_reg(alice_deg)}')
                time.sleep(args.settle_ms / 1000.0)

                # Quick measurement (fewer trials for baseline)
                n_base = max(10, args.trials // 3)
                data = measure_setting(
                    ps, handle, dds, mux, mode,
                    alice_deg, bob_deg, n_base)
                corr = compute_correlation(data)
                baseline_correlations[key] = corr
                print(f"  E_baseline({alice_deg}°, {bob_deg}°) = "
                      f"{corr['E']:.4f}")

        # Re-enable DDS2 for final status
        dds_cmd(dds, f"F2:{mode['dds2_freq']}")

        baseline_chsh = compute_chsh(baseline_correlations)

        # ─── Assemble results ────────────────────────────────────
        results = {
            'timestamp': time.strftime('%Y%m%d_%H%M%S'),
            'experiment': 'CHSH classical entanglement',
            'mode': mode,
            'receivers': {
                'R1': RECEIVER_R1,
                'R2': RECEIVER_R2,
            },
            'settings': {
                'alice_degrees': ALICE_SETTINGS,
                'bob_degrees': BOB_SETTINGS,
                'trials': args.trials,
                'navg': args.navg,
                'settle_ms': args.settle_ms,
                'window_hz': args.window_hz,
            },
            'noise_energy': noise_energy,
            'measurements': all_settings,
            'chsh': chsh,
            'baseline_chsh': baseline_chsh,
        }

        # ─── Save ────────────────────────────────────────────────
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(OUT_PATH, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        print(f"\nData saved to {OUT_PATH}")

        print_results(results)

    finally:
        cleanup(ps, handle, dds, mux)


def print_results(results):
    """Print formatted results summary."""
    chsh = results['chsh']
    baseline = results.get('baseline_chsh', {})

    print()
    print("=" * 70)
    print(" RESULTS: CHSH S-PARAMETER")
    print("=" * 70)

    print(f"\n  Dual-DDS (both modes driven):")
    for key, val in chsh.get('E_values', {}).items():
        print(f"    {key} = {val:.4f}")
    print(f"\n    S = {chsh['S']:.4f} ± {chsh['S_err']:.4f}")
    print(f"    σ above classical (S=2): {chsh['sigma_above_classical']:.1f}")

    if chsh['S'] > 2.0:
        if chsh['sigma_above_classical'] > 3.0:
            verdict = "NON-SEPARABLE (classically entangled) — >3σ"
        elif chsh['sigma_above_classical'] > 2.0:
            verdict = "SUGGESTIVE — >2σ but needs more trials"
        else:
            verdict = "MARGINAL — above 2 but not statistically significant"
    else:
        verdict = "SEPARABLE — no classical entanglement detected"

    print(f"\n    VERDICT: {verdict}")

    if baseline:
        print(f"\n  Single-DDS baseline:")
        print(f"    S_baseline = {baseline.get('S', 0):.4f} "
              f"± {baseline.get('S_err', 0):.4f}")
        if baseline.get('S', 0) < 1.5:
            print(f"    ✓ Baseline confirms separability (S < 1.5)")
        else:
            print(f"    ⚠ Baseline unexpectedly high — check for systematics")

    print()
    print("─" * 70)
    print("INTERPRETATION:")
    print("─" * 70)
    print("""
  S ≤ 2.0  → Frequency and phase DOFs are separable (independent).
              The plate responds to each mode independently.
              No classical entanglement.

  2.0 < S ≤ 2√2 ≈ 2.83 → Non-separable! The plate's nonlinear mode
              mixing creates inseparable frequency×phase correlations.
              This is "classical entanglement" — same mathematical
              structure as quantum entanglement, but between DOFs of
              a single system rather than between particles.
              First acoustic demonstration if confirmed.

  S > 2√2  → Measurement error or systematic bias. Classical systems
              cannot exceed 2√2. Recheck analysis.

  NOTE: Current DDS SNR (~4.5×) will add noise that dilutes S toward 2.
  With preamp (~May 1), correlations should sharpen significantly.
  If S is close to 2 now, rerun post-preamp before concluding.
    """)


if __name__ == '__main__':
    main()
