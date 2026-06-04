#!/usr/bin/env python3
"""
T5.2 — CHSH Classical Entanglement Test

Tests whether the fused silica plate's frequency × phase degrees of freedom
exhibit non-separable ("classically entangled") correlations via a CHSH-like
S parameter.

Protocol:
  1. DDS1 drives mode f₁ = 35,840 Hz; DDS2 drives mode f₂ = 97,011 Hz
  2. Two receiver positions via relay mux (relay 8 = NE, relay 7 = SW)
  3. Alice's setting: DDS1 phase ∈ {0°, 45°}
  4. Bob's setting: DDS2 phase ∈ {22.5°, 67.5°}
  5. For each of 4 (θ_A, θ_B) pairs × N trials:
     - Set phases on DDS
     - Capture spectrum at receiver R1 and R2
     - Extract complex amplitudes at f₁ and f₂
  6. Compute E(θ_A, θ_B) correlations and CHSH S parameter

Pass criteria: S > 2.0 with σ_S < 0.3

Hardware:
  PicoScope 2204A: ±5V, AC coupled, timebase 7, 8064 samples
  DDS: /dev/cu.usbserial-1120, 115200 baud
  Relay mux: /dev/cu.usbserial-11310, 9600 baud
  Signal path: DDS → 10kΩ sum → PZT → Plate → RX PZT → Relay Mux → Board A (×11) → PicoScope
"""
import argparse
import ctypes as ct
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import serial

# ─── Arguments ───────────────────────────────────────────────────
parser = argparse.ArgumentParser(description='T5.2 CHSH classical entanglement')
parser.add_argument('--trials', type=int, default=30,
                    help='Trials per measurement setting (default: 30)')
parser.add_argument('--navg', type=int, default=12,
                    help='Spectral averages per measurement (default: 12)')
parser.add_argument('--settle-ms', type=int, default=300,
                    help='Settle time after phase change, ms (default: 300)')
args = parser.parse_args()

# ─── Constants ───────────────────────────────────────────────────
N_SAMPLES = 8064
TIMEBASE = 7        # 1280 ns/sample → 781,250 Hz sample rate
DT = 1280e-9
BIN_HZ = 1.0 / (N_SAMPLES * DT)  # ≈ 96.9 Hz

# Mode pair (from T5.1 recommended)
F1 = 35840    # DDS1 frequency — Alice's mode
F2 = 97011    # DDS2 frequency — Bob's mode
F1_BIN = int(round(F1 / BIN_HZ))
F2_BIN = int(round(F2 / BIN_HZ))

# CHSH measurement angles (degrees)
ALICE_ANGLES = [0.0, 45.0]       # DDS1 phase settings
BOB_ANGLES = [22.5, 67.5]        # DDS2 phase settings

# Receivers
RX1_RELAY = 8   # NE corner (confirmed)
RX2_RELAY = 7   # SW corner (to validate)

# Hardware paths
PICO_LIB = '/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources/libps2000.dylib'
MUX_PORT = '/dev/cu.usbserial-11310'
DDS_PORT = '/dev/cu.usbserial-1120'

# Output
DATA_DIR = Path(__file__).parent.parent / 'data' / 'results' / 'quantum_bridge'
TIMESTAMP = datetime.now().strftime('%Y%m%d_%H%M%S')
OUT_PATH = DATA_DIR / f't5_2_chsh_{TIMESTAMP}.json'


# ─── Phase conversion ───────────────────────────────────────────
def deg_to_phase_reg(deg):
    """Convert degrees to AD9833 12-bit phase register (0–4095)."""
    return int(round((deg % 360) / 360 * 4096)) % 4096


# ─── Hardware init ───────────────────────────────────────────────
def init_hardware():
    """Initialize PicoScope, relay mux, and DDS."""
    ps = ct.CDLL(PICO_LIB)
    ps.ps2000_open_unit.restype = ct.c_int16
    handle = ps.ps2000_open_unit()
    print(f"  PicoScope handle: {handle}")
    if handle < 1:
        print("ERROR: PicoScope failed to open")
        sys.exit(1)

    # Ch A: enabled, AC coupled (dc=0), ±5V (range 7)
    ps.ps2000_set_channel(handle, 0, 1, 0, 7)
    # Ch B: disabled
    ps.ps2000_set_channel(handle, 1, 0, 0, 7)

    # Relay mux
    mux = serial.Serial(MUX_PORT, 9600, timeout=2, dsrdtr=False, rtscts=False)
    mux.dtr = False
    time.sleep(0.5)
    mux.reset_input_buffer()

    # DDS controller
    dds = serial.Serial(DDS_PORT, 115200, timeout=2)
    time.sleep(2.5)  # boot wait
    dds.reset_input_buffer()

    return ps, handle, mux, dds


def set_mux(mux, channel):
    """Set relay mux channel with retry."""
    for attempt in range(3):
        mux.write(f'{channel}\r\n'.encode())
        time.sleep(0.3)
        resp = mux.read(mux.in_waiting).decode(errors='replace').strip()
        if f'OK:{channel}' in resp:
            return True
        time.sleep(0.3)
    print(f"  WARNING: Mux channel {channel} not confirmed")
    return False


def dds_cmd(dds, cmd):
    """Send DDS command and read response."""
    dds.reset_input_buffer()
    dds.write(f'{cmd}\n'.encode())
    time.sleep(0.05)
    resp = dds.readline().decode(errors='replace').strip()
    return resp


def capture_spectrum(ps, handle, navg=8):
    """Capture navg frames, return averaged magnitude spectrum."""
    buf = (ct.c_int16 * N_SAMPLES)()
    ov = ct.c_int16()
    specs = []

    for _ in range(navg):
        ps.ps2000_set_trigger(handle, 5, 0, 0, 0, 0)
        ticks = ct.c_int32()
        ps.ps2000_run_block(handle, N_SAMPLES, TIMEBASE, 1, ct.byref(ticks))
        time.sleep(0.005)
        for _w in range(500):
            if ps.ps2000_ready(handle):
                break
            time.sleep(0.002)
        ps.ps2000_get_values(handle, ct.byref(buf), None, None, None,
                             ct.byref(ov), N_SAMPLES, 0)
        d = np.array(buf[:], dtype=np.float64)
        d -= d.mean()
        sp = np.fft.rfft(d * np.hanning(N_SAMPLES))
        specs.append(sp)

    return np.mean(specs, axis=0)  # complex average


def extract_amplitude(spectrum, freq_bin, window=3):
    """Extract complex amplitude near target bin (peak within ±window)."""
    lo = max(0, freq_bin - window)
    hi = freq_bin + window + 1
    sub = spectrum[lo:hi]
    peak_idx = np.argmax(np.abs(sub))
    return complex(sub[peak_idx])


def cleanup(ps, handle, dds, mux):
    """Shut down hardware."""
    dds_cmd(dds, 'Foff')
    ps.ps2000_stop(handle)
    ps.ps2000_close_unit(ct.c_int16(handle))
    dds.close()
    mux.close()


# ─── CHSH measurement ───────────────────────────────────────────
def measure_one_setting(ps, handle, dds, mux, alice_deg, bob_deg, n_trials, navg):
    """
    Measure one (θ_A, θ_B) setting for n_trials.

    For each trial:
      1. Set DDS1 phase, DDS2 phase
      2. Capture complex spectrum at RX1
      3. Switch mux, capture at RX2
      4. Extract complex amplitudes at f₁ and f₂ from both receivers

    Returns arrays of complex amplitudes.
    """
    alice_reg = deg_to_phase_reg(alice_deg)
    bob_reg = deg_to_phase_reg(bob_deg)

    # Set phases
    dds_cmd(dds, f'P1:{alice_reg}')
    dds_cmd(dds, f'P2:{bob_reg}')
    time.sleep(args.settle_ms / 1000.0)

    # Storage: [trial] → complex amplitude
    r1_f1 = []  # Receiver 1, mode f₁
    r1_f2 = []  # Receiver 1, mode f₂
    r2_f1 = []  # Receiver 2, mode f₁
    r2_f2 = []  # Receiver 2, mode f₂

    for trial in range(n_trials):
        # Measure at RX1
        set_mux(mux, RX1_RELAY)
        time.sleep(0.05)
        sp1 = capture_spectrum(ps, handle, navg)
        r1_f1.append(extract_amplitude(sp1, F1_BIN))
        r1_f2.append(extract_amplitude(sp1, F2_BIN))

        # Measure at RX2
        set_mux(mux, RX2_RELAY)
        time.sleep(0.05)
        sp2 = capture_spectrum(ps, handle, navg)
        r2_f1.append(extract_amplitude(sp2, F1_BIN))
        r2_f2.append(extract_amplitude(sp2, F2_BIN))

    return {
        'r1_f1': np.array(r1_f1),
        'r1_f2': np.array(r1_f2),
        'r2_f1': np.array(r2_f1),
        'r2_f2': np.array(r2_f2),
    }


def compute_correlation(data):
    """
    Compute E(θ_A, θ_B) from measurement data.

    Observable:
      outcome_A = sign(|R1_f1| - |R2_f1|)  (spatial contrast of Alice's mode)
      outcome_B = sign(|R1_f2| - |R2_f2|)  (spatial contrast of Bob's mode)
      E = <outcome_A × outcome_B>

    If modes are separable: E ≈ 0 (no correlation between spatial patterns).
    If non-separable: phase settings create correlated spatial responses.
    """
    # Use magnitude for spatial contrast (phase-independent)
    mag_r1_f1 = np.abs(data['r1_f1'])
    mag_r2_f1 = np.abs(data['r2_f1'])
    mag_r1_f2 = np.abs(data['r1_f2'])
    mag_r2_f2 = np.abs(data['r2_f2'])

    # Spatial contrast for each mode
    outcome_a = np.sign(mag_r1_f1 - mag_r2_f1)
    outcome_b = np.sign(mag_r1_f2 - mag_r2_f2)

    # Replace zeros
    outcome_a[outcome_a == 0] = 1
    outcome_b[outcome_b == 0] = 1

    products = outcome_a * outcome_b
    E = float(np.mean(products))
    E_err = float(np.std(products) / np.sqrt(len(products)))

    n_pp = int(np.sum((outcome_a > 0) & (outcome_b > 0)))
    n_mm = int(np.sum((outcome_a < 0) & (outcome_b < 0)))
    n_pm = int(np.sum((outcome_a > 0) & (outcome_b < 0)))
    n_mp = int(np.sum((outcome_a < 0) & (outcome_b > 0)))

    return {
        'E': E, 'E_err': E_err,
        'n_pp': n_pp, 'n_mm': n_mm, 'n_pm': n_pm, 'n_mp': n_mp,
    }


def compute_correlation_phase(data):
    """
    Alternative correlation using phase difference between receivers.

    outcome_A = sign(angle(R1_f1) - angle(R2_f1))
    outcome_B = sign(angle(R1_f2) - angle(R2_f2))

    Phase-based observable may be more sensitive to DDS phase control.
    """
    phase_r1_f1 = np.angle(data['r1_f1'])
    phase_r2_f1 = np.angle(data['r2_f1'])
    phase_r1_f2 = np.angle(data['r1_f2'])
    phase_r2_f2 = np.angle(data['r2_f2'])

    # Phase difference (wrapped to [-π, π])
    diff_a = np.angle(np.exp(1j * (phase_r1_f1 - phase_r2_f1)))
    diff_b = np.angle(np.exp(1j * (phase_r1_f2 - phase_r2_f2)))

    outcome_a = np.sign(diff_a)
    outcome_b = np.sign(diff_b)
    outcome_a[outcome_a == 0] = 1
    outcome_b[outcome_b == 0] = 1

    products = outcome_a * outcome_b
    E = float(np.mean(products))
    E_err = float(np.std(products) / np.sqrt(len(products)))

    return {'E_phase': E, 'E_phase_err': E_err}


def compute_S(correlations):
    """
    Compute CHSH S = |E(a1,b1) - E(a1,b2) + E(a2,b1) + E(a2,b2)|

    Classical separable bound: S ≤ 2
    Non-separable (classically entangled) max: S = 2√2 ≈ 2.83
    """
    a1, a2 = ALICE_ANGLES
    b1, b2 = BOB_ANGLES

    E = {k: v['E'] for k, v in correlations.items()}
    errs = {k: v['E_err'] for k, v in correlations.items()}

    S_raw = E[(a1, b1)] - E[(a1, b2)] + E[(a2, b1)] + E[(a2, b2)]
    S = abs(S_raw)
    S_err = np.sqrt(sum(errs[k]**2 for k in correlations))
    sigma = (S - 2.0) / S_err if S_err > 0 else 0.0

    return {
        'S': float(S),
        'S_raw': float(S_raw),
        'S_err': float(S_err),
        'sigma_above_2': float(sigma),
    }


# ─── Main ────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("  T5.2 — CHSH CLASSICAL ENTANGLEMENT TEST")
    print("=" * 60)
    print(f"  DDS1 (Alice): {F1} Hz, angles {ALICE_ANGLES}°")
    print(f"  DDS2 (Bob):   {F2} Hz, angles {BOB_ANGLES}°")
    print(f"  Receivers: relay {RX1_RELAY} (NE) + relay {RX2_RELAY} (SW)")
    print(f"  Trials/setting: {args.trials}, Averages: {args.navg}")
    print(f"  Total measurements: {4 * args.trials * 2} spectra")
    print()

    # ─── Init ────────────────────────────────────────────────────
    print("[1] Hardware init...")
    ps, handle, mux, dds = init_hardware()

    try:
        # ─── Validate RX2 ────────────────────────────────────────
        print("\n[2] Validating dual receivers...")
        dds_cmd(dds, 'Foff')
        time.sleep(0.2)
        dds_cmd(dds, f'F1:{F1}')
        dds_cmd(dds, f'F2:{F2}')
        time.sleep(0.5)

        set_mux(mux, RX1_RELAY)
        time.sleep(0.1)
        sp_rx1 = capture_spectrum(ps, handle, 8)
        snr_rx1_f1 = np.abs(extract_amplitude(sp_rx1, F1_BIN)) / np.median(np.abs(sp_rx1[10:]))
        snr_rx1_f2 = np.abs(extract_amplitude(sp_rx1, F2_BIN)) / np.median(np.abs(sp_rx1[10:]))

        set_mux(mux, RX2_RELAY)
        time.sleep(0.1)
        sp_rx2 = capture_spectrum(ps, handle, 8)
        snr_rx2_f1 = np.abs(extract_amplitude(sp_rx2, F1_BIN)) / np.median(np.abs(sp_rx2[10:]))
        snr_rx2_f2 = np.abs(extract_amplitude(sp_rx2, F2_BIN)) / np.median(np.abs(sp_rx2[10:]))

        print(f"    RX1 (relay {RX1_RELAY}): f1={snr_rx1_f1:.1f}×, f2={snr_rx1_f2:.1f}×")
        print(f"    RX2 (relay {RX2_RELAY}): f1={snr_rx2_f1:.1f}×, f2={snr_rx2_f2:.1f}×")

        if snr_rx2_f1 < 1.5 and snr_rx2_f2 < 1.5:
            print(f"    WARNING: RX2 (relay {RX2_RELAY}) shows no signal!")
            print(f"    Trying alternative relays...")
            # Try relays 1-6
            for alt_relay in [1, 2, 3, 4, 5, 6]:
                set_mux(mux, alt_relay)
                time.sleep(0.1)
                sp_alt = capture_spectrum(ps, handle, 5)
                snr_alt = np.abs(extract_amplitude(sp_alt, F2_BIN)) / np.median(np.abs(sp_alt[10:]))
                if snr_alt > 2.0:
                    print(f"    Found signal on relay {alt_relay}: {snr_alt:.1f}×")
                    RX2_RELAY_ACTUAL = alt_relay
                    break
            else:
                print("    ERROR: No second receiver found. Cannot run CHSH.")
                print("    CHSH requires two spatially distinct measurement points.")
                cleanup(ps, handle, dds, mux)
                sys.exit(1)
        else:
            RX2_RELAY_ACTUAL = RX2_RELAY

        # ─── Validate phase control ─────────────────────────────
        print("\n[3] Validating DDS phase control...")
        # Measure at 0° and 180° — should see phase flip in FFT
        dds_cmd(dds, 'P1:0')
        time.sleep(0.2)
        set_mux(mux, RX1_RELAY)
        sp_0 = capture_spectrum(ps, handle, 10)
        amp_0 = extract_amplitude(sp_0, F1_BIN)

        dds_cmd(dds, 'P1:2048')  # 180°
        time.sleep(0.2)
        sp_180 = capture_spectrum(ps, handle, 10)
        amp_180 = extract_amplitude(sp_180, F1_BIN)

        phase_shift = np.angle(amp_180 / amp_0) * 180 / np.pi
        print(f"    Phase 0° → 180°: measured shift = {phase_shift:.1f}°")
        print(f"    Magnitude ratio: {np.abs(amp_180)/np.abs(amp_0):.2f}")

        if abs(abs(phase_shift) - 180) > 60:
            print(f"    WARNING: Phase shift {phase_shift:.1f}° != expected ±180°")
            print(f"    Phase control may not be working properly.")
            print(f"    Continuing anyway — results may be null (S≈0).")
        else:
            print(f"    ✓ Phase control confirmed.")

        # Reset phase
        dds_cmd(dds, 'P1:0')
        dds_cmd(dds, 'P2:0')
        time.sleep(0.2)

        # ─── CHSH Measurements ───────────────────────────────────
        print(f"\n[4] CHSH measurements ({4 * args.trials} trial-pairs)...")
        correlations = {}
        all_data = {}

        for alice_deg in ALICE_ANGLES:
            for bob_deg in BOB_ANGLES:
                key = (alice_deg, bob_deg)
                print(f"\n    Setting: Alice={alice_deg}°, Bob={bob_deg}°")

                data = measure_one_setting(
                    ps, handle, dds, mux,
                    alice_deg, bob_deg, args.trials, args.navg)

                corr = compute_correlation(data)
                phase_corr = compute_correlation_phase(data)
                correlations[key] = corr

                print(f"      E = {corr['E']:+.4f} ± {corr['E_err']:.4f}"
                      f"  (++:{corr['n_pp']} --:{corr['n_mm']}"
                      f" +-:{corr['n_pm']} -+:{corr['n_mp']})")
                print(f"      E_phase = {phase_corr['E_phase']:+.4f} ± "
                      f"{phase_corr['E_phase_err']:.4f}")

                # Store for JSON (convert complex to [re, im])
                all_data[f"{alice_deg}_{bob_deg}"] = {
                    'alice_deg': alice_deg,
                    'bob_deg': bob_deg,
                    'correlation': corr,
                    'phase_correlation': phase_corr,
                    'r1_f1': [[z.real, z.imag] for z in data['r1_f1']],
                    'r1_f2': [[z.real, z.imag] for z in data['r1_f2']],
                    'r2_f1': [[z.real, z.imag] for z in data['r2_f1']],
                    'r2_f2': [[z.real, z.imag] for z in data['r2_f2']],
                }

        # ─── Baseline: DDS2 off (should give S ≈ 0) ─────────────
        print(f"\n[5] Baseline (DDS2 off, expect S ≈ 0)...")
        dds_cmd(dds, 'Foff')
        time.sleep(0.2)
        dds_cmd(dds, f'F1:{F1}')  # Only DDS1 active
        time.sleep(0.3)

        baseline_correlations = {}
        n_base = max(10, args.trials // 3)
        for alice_deg in ALICE_ANGLES:
            for bob_deg in BOB_ANGLES:
                key = (alice_deg, bob_deg)
                data = measure_one_setting(
                    ps, handle, dds, mux,
                    alice_deg, bob_deg, n_base, args.navg)
                corr = compute_correlation(data)
                baseline_correlations[key] = corr
                print(f"    E_base({alice_deg}°,{bob_deg}°) = {corr['E']:+.4f}")

        # ─── Compute S ──────────────────────────────────────────
        chsh = compute_S(correlations)
        baseline_chsh = compute_S(baseline_correlations)

        # ─── Results ─────────────────────────────────────────────
        print("\n" + "=" * 60)
        print("  RESULTS")
        print("=" * 60)
        print(f"\n  Correlations (dual-DDS):")
        for (a, b), c in correlations.items():
            print(f"    E({a}°, {b}°) = {c['E']:+.4f} ± {c['E_err']:.4f}")

        print(f"\n  S = {chsh['S']:.4f} ± {chsh['S_err']:.4f}")
        print(f"  σ above classical (S=2): {chsh['sigma_above_2']:.1f}")

        print(f"\n  Baseline (DDS1 only):")
        print(f"  S_baseline = {baseline_chsh['S']:.4f} ± {baseline_chsh['S_err']:.4f}")

        # Verdict
        if chsh['S'] > 2.0 and chsh['sigma_above_2'] > 3.0:
            verdict = "PASS — NON-SEPARABLE (>3σ above classical bound)"
            gate_pass = True
        elif chsh['S'] > 2.0 and chsh['sigma_above_2'] > 2.0:
            verdict = "MARGINAL — S>2 but only 2-3σ; more trials needed"
            gate_pass = False
        elif chsh['S'] > 2.0:
            verdict = "WEAK — S>2 but not statistically significant"
            gate_pass = False
        else:
            verdict = "FAIL — SEPARABLE (S ≤ 2)"
            gate_pass = False

        print(f"\n  VERDICT: {verdict}")

        # ─── Save ────────────────────────────────────────────────
        results = {
            'experiment': 'T5.2 CHSH Classical Entanglement',
            'timestamp': TIMESTAMP,
            'hardware': {
                'dds1_freq': F1, 'dds2_freq': F2,
                'rx1_relay': RX1_RELAY,
                'rx2_relay': RX2_RELAY_ACTUAL,
                'scope_range': '±5V', 'coupling': 'AC',
                'navg': args.navg, 'trials': args.trials,
                'settle_ms': args.settle_ms,
            },
            'validation': {
                'rx1_snr_f1': float(snr_rx1_f1),
                'rx1_snr_f2': float(snr_rx1_f2),
                'rx2_snr_f1': float(snr_rx2_f1),
                'rx2_snr_f2': float(snr_rx2_f2),
                'phase_shift_deg': float(phase_shift),
            },
            'chsh': chsh,
            'baseline_chsh': baseline_chsh,
            'measurements': all_data,
            'gate_pass': gate_pass,
            'verdict': verdict,
        }

        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(OUT_PATH, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"\n  Results saved: {OUT_PATH.relative_to(Path(__file__).parent.parent)}")

    finally:
        cleanup(ps, handle, dds, mux)

    print("\nDone.")


if __name__ == '__main__':
    main()
