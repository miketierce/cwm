#!/usr/bin/env python3
"""
T5.2 — CHSH Classical Entanglement Test (Pico NCO)

Demonstrates non-separability of the plate's frequency × space degrees
of freedom via a CHSH inequality violation.

Physics:
  The plate is driven at two eigenfrequencies f1, f2 simultaneously.
  Each mode has a distinct spatial pattern across the plate. At two
  receiver positions (RX1=relay 7, RX2=relay 8), we measure complex
  amplitudes forming a 2×2 state matrix:

    M = [[A(f1,RX1), A(f1,RX2)],
         [A(f2,RX1), A(f2,RX2)]]

  If the rows are proportional (same spatial pattern for both modes),
  the state is separable and S ≤ 2. If not, it's classically entangled
  and S can reach 2√2 ≈ 2.83.

Protocol (Kagalwala/Qian/Eberly intensity-based CHSH):
  1. Drive both modes, capture complex spectra at both receivers
  2. Form normalized state matrix M from measured amplitudes
  3. Compute correlation function E(θ_A, θ_B) using:
       I(θ_A, θ_B) = |⟨θ_A| M |θ_B⟩|²
       E = [I(a,b) + I(a⊥,b⊥) - I(a,b⊥) - I(a⊥,b)] / [sum]
  4. S = |E(a1,b1) - E(a1,b2) + E(a2,b1) + E(a2,b2)|
  5. Also sweep DDS phase to verify correlation tracks cos(2Δθ)

Pass criteria: S > 2.0 (violates separable bound)
Ideal max:    S = 2√2 ≈ 2.83 (maximally non-separable)

Hardware:
  Pico NCO:   /dev/cu.usbmodem113301, CH1=54920 Hz (GP2/SW), CH2=97011 Hz (GP3/NE)
  PicoScope:  2204A, ±2V AC, timebase 7, N=3968
  Relay mux:  /dev/cu.usbserial-11310, relay 7=SW RX, relay 8=NE RX
  Preamp:     Board A (OPA2134PA ×11), 100nF AC coupling cap
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
parser = argparse.ArgumentParser(description='T5.2 CHSH classical entanglement (Pico NCO)')
parser.add_argument('--trials', type=int, default=50,
                    help='Paired captures per measurement (default: 50)')
parser.add_argument('--settle', type=float, default=2.0,
                    help='Initial ring-up time, seconds (default: 2.0)')
parser.add_argument('--phase-sweep', action='store_true', default=True,
                    help='Also sweep DDS phase to map correlation (default: True)')
args = parser.parse_args()

# ─── Constants ───────────────────────────────────────────────────
N = 3968
TIMEBASE = 7           # 1280 ns/sample → 781,250 Hz
DT = 1280e-9
FS = 1.0 / DT
BIN_HZ = FS / N       # 196.89 Hz/bin
NFFT_PAD = 4
NFFT = N * NFFT_PAD
BIN_HZ_PAD = FS / NFFT
RNG = 6               # ±2V
RNG_MV = 2000

# Best mode pair from T5.1 baseline
F1 = 54920   # CH1 (GP2/SW TX) — "Alice's mode"
F2 = 97011   # CH2 (GP3/NE TX) — "Bob's mode"
F1_BIN = int(round(F1 / BIN_HZ_PAD))
F2_BIN = int(round(F2 / BIN_HZ_PAD))

# Receivers
RX1_RELAY = 7   # SW corner
RX2_RELAY = 8   # NE corner

# CHSH angles (degrees) — optimal for max violation
# Will be refined after measuring the state matrix
ALICE_ANGLES = [0.0, 45.0]
BOB_ANGLES = [22.5, 67.5]

# Hardware
PICO_LIB = '/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources/libps2000.dylib'
MUX_PORT = '/dev/cu.usbserial-11310'
NCO_PORT = '/dev/cu.usbmodem113301'

# Output
DATA_DIR = Path(__file__).parent.parent / 'data' / 'results' / 'quantum_bridge'
TIMESTAMP = datetime.now().strftime('%Y%m%d_%H%M%S')
OUT_PATH = DATA_DIR / f't5_2_chsh_pico_{TIMESTAMP}.json'


# ─── Hardware ────────────────────────────────────────────────────
def init_hardware():
    """Initialize PicoScope, relay mux, and Pico NCO."""
    ps = ct.CDLL(PICO_LIB)
    ps.ps2000_close_unit(ct.c_int16(1))
    time.sleep(0.3)

    ps.ps2000_open_unit.restype = ct.c_int16
    handle = ps.ps2000_open_unit()
    print(f"  PicoScope handle: {handle}")
    if handle < 1:
        print("ERROR: PicoScope failed to open")
        sys.exit(1)
    ps.ps2000_set_channel(handle, 0, 1, 0, RNG)  # Ch A: AC, ±2V
    ps.ps2000_set_channel(handle, 1, 0, 0, RNG)  # Ch B: off

    # Relay mux
    mux = serial.Serial(MUX_PORT, 9600, timeout=2, dsrdtr=False, rtscts=False)
    mux.dtr = False
    time.sleep(2.5)
    mux.reset_input_buffer()

    # Pico NCO
    nco = serial.Serial(NCO_PORT, 115200, timeout=2)
    time.sleep(0.5)
    nco.reset_input_buffer()

    return ps, handle, mux, nco


def nco_cmd(nco, cmd):
    """Send NCO command and read response."""
    nco.reset_input_buffer()
    nco.write(f'{cmd}\n'.encode())
    time.sleep(0.05)
    return nco.readline().decode(errors='replace').strip()


def set_relay(mux, relay):
    """Set relay mux channel."""
    mux.reset_input_buffer()
    mux.write(f'{relay}\r\n'.encode())
    time.sleep(0.4)
    resp = mux.read(mux.in_waiting).decode(errors='replace').strip()
    return 'OK' in resp


def capture_complex(ps, handle):
    """Single capture → complex FFT (zero-padded)."""
    buf = (ct.c_int16 * N)()
    ov = ct.c_int16()
    ps.ps2000_set_trigger(handle, 5, 0, 0, 0, 0)
    ticks = ct.c_int32()
    ps.ps2000_run_block(handle, N, TIMEBASE, 1, ct.byref(ticks))
    for _ in range(500):
        if ps.ps2000_ready(handle):
            break
        time.sleep(0.002)
    ps.ps2000_get_values(handle, ct.byref(buf), None, None, None,
                         ct.byref(ov), N, 0)
    d = np.array(buf[:], dtype=np.float64) * (RNG_MV / 32767.0)
    d -= d.mean()
    return np.fft.rfft(d * np.hanning(N), n=NFFT)


def extract_peak(spectrum, freq, window=5):
    """Extract complex amplitude at freq (peak within ±window bins)."""
    b = int(round(freq / BIN_HZ_PAD))
    lo = max(0, b - window)
    hi = min(len(spectrum), b + window + 1)
    sub = spectrum[lo:hi]
    idx = np.argmax(np.abs(sub))
    return complex(sub[idx])


def compute_snr(spectrum, freq, window=5):
    """Compute SNR in dB at given frequency."""
    b = int(round(freq / BIN_HZ_PAD))
    lo = max(0, b - window)
    hi = min(len(spectrum), b + window + 1)
    peak = np.abs(spectrum[lo:hi]).max()
    # Noise: median excluding DC and signal regions
    noise_region = np.abs(spectrum[20:])
    for f in [F1, F2]:
        fb = int(round(f / BIN_HZ_PAD)) - 20
        noise_region = np.concatenate([
            noise_region[:max(0, fb - 10)],
            noise_region[min(len(noise_region), fb + 11):]
        ])
    noise = np.median(noise_region) if len(noise_region) > 10 else 1.0
    return 20 * np.log10(peak / noise) if noise > 0 else 0.0


# ─── CHSH Mathematics ────────────────────────────────────────────
def intensity(M, theta_a, theta_b):
    """
    Compute projection intensity I(θ_A, θ_B).

    Alice projects frequency DOF onto (cos θ_A, sin θ_A).
    Bob projects spatial DOF onto (cos θ_B, sin θ_B).
    I = |⟨a| M |b⟩|²
    """
    a = np.array([np.cos(theta_a), np.sin(theta_a)])
    b = np.array([np.cos(theta_b), np.sin(theta_b)])
    projection = a @ M @ b
    return float(np.abs(projection) ** 2)


def correlation_E(M, theta_a, theta_b):
    """
    Compute CHSH correlation E(θ_A, θ_B) using intensity formula.

    E = [I(a,b) + I(a⊥,b⊥) - I(a,b⊥) - I(a⊥,b)] / [sum of all four]
    """
    a = theta_a
    b = theta_b
    a_perp = a + np.pi / 2
    b_perp = b + np.pi / 2

    I_ab = intensity(M, a, b)
    I_apbp = intensity(M, a_perp, b_perp)
    I_abp = intensity(M, a, b_perp)
    I_apb = intensity(M, a_perp, b)

    numer = I_ab + I_apbp - I_abp - I_apb
    denom = I_ab + I_apbp + I_abp + I_apb
    return numer / denom if denom > 0 else 0.0


def compute_S(M, alice_angles_rad, bob_angles_rad):
    """Compute CHSH S parameter."""
    a1, a2 = alice_angles_rad
    b1, b2 = bob_angles_rad

    E11 = correlation_E(M, a1, b1)
    E12 = correlation_E(M, a1, b2)
    E21 = correlation_E(M, a2, b1)
    E22 = correlation_E(M, a2, b2)

    S = abs(E11 - E12 + E21 + E22)
    return S, {'E11': E11, 'E12': E12, 'E21': E21, 'E22': E22}


def optimal_chsh_angles(M):
    """
    Find measurement angles that maximize S using SVD.

    For M = U Σ V†, the optimal angles are aligned to the SVD bases
    with 22.5° offsets.
    """
    U, sigma, Vh = np.linalg.svd(M)

    # The correlation function in SVD-aligned coordinates is:
    # E(α, β) = (σ₁²cos(2α)cos(2β) + σ₂²sin(2α)sin(2β)) / (σ₁² + σ₂²)
    # which simplifies for CHSH to specific angle combinations.

    # For maximum S, use angles at π/8 offsets
    # Alice: 0, π/4 in U-basis → α₁=0, α₂=π/4
    # Bob: π/8, 3π/8 in V-basis → β₁=π/8, β₂=3π/8

    # Get rotation angles of U and V
    # U rotates frequency basis, V rotates spatial basis
    alpha_offset = np.arctan2(U[1, 0].real, U[0, 0].real)
    beta_offset = np.arctan2(Vh[0, 1].real, Vh[0, 0].real)

    # Optimal CHSH angles (absolute)
    alice = [alpha_offset, alpha_offset + np.pi / 4]
    bob = [beta_offset + np.pi / 8, beta_offset + 3 * np.pi / 8]

    # Theoretical maximum S for this state
    s1, s2 = sigma[0], sigma[1]
    # Concurrence C = 2*s1*s2 / (s1² + s2²)
    concurrence = 2 * s1 * s2 / (s1**2 + s2**2) if (s1**2 + s2**2) > 0 else 0
    # S_max = 2√(1 + C²) for the intensity-based CHSH
    S_max = 2 * np.sqrt(1 + concurrence**2)

    return alice, bob, {
        'sigma': [float(s1), float(s2)],
        'concurrence': float(concurrence),
        'S_theoretical_max': float(S_max),
        'alpha_offset_deg': float(np.degrees(alpha_offset)),
        'beta_offset_deg': float(np.degrees(beta_offset)),
    }


# ─── Main ────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("  T5.2 — CHSH CLASSICAL ENTANGLEMENT (Pico NCO)")
    print("=" * 60)
    print(f"  Modes: f1={F1} Hz (CH1/SW TX), f2={F2} Hz (CH2/NE TX)")
    print(f"  Receivers: RX1=relay {RX1_RELAY} (SW), RX2=relay {RX2_RELAY} (NE)")
    print(f"  Trials: {args.trials} paired captures")
    print(f"  Pass criterion: S > 2.0")
    print()

    # ─── Init ────────────────────────────────────────────────────
    print("[1] Hardware init...")
    ps, handle, mux, nco = init_hardware()

    try:
        # ─── Start drives ────────────────────────────────────────
        print("\n[2] Starting dual-mode drive...")
        nco_cmd(nco, 'Foff')
        time.sleep(0.3)
        print(f"    {nco_cmd(nco, f'F1:{F1}')}")
        print(f"    {nco_cmd(nco, f'F2:{F2}')}")
        nco_cmd(nco, 'P1:0')
        nco_cmd(nco, 'P2:0')
        print(f"    Waiting {args.settle}s for ring-up...")
        time.sleep(args.settle)

        # ─── Validate both receivers ─────────────────────────────
        print("\n[3] Validating receivers...")
        for relay, name in [(RX1_RELAY, 'RX1/SW'), (RX2_RELAY, 'RX2/NE')]:
            set_relay(mux, relay)
            time.sleep(0.2)
            sp = capture_complex(ps, handle)
            snr1 = compute_snr(sp, F1)
            snr2 = compute_snr(sp, F2)
            print(f"    {name} (relay {relay}): "
                  f"f1={snr1:.1f} dB, f2={snr2:.1f} dB")
            if snr1 < 10:
                print(f"    WARNING: f1 SNR low on {name}")
            if snr2 < 6:
                print(f"    WARNING: f2 SNR low on {name}")

        # ─── Collect state matrices ──────────────────────────────
        print(f"\n[4] Collecting {args.trials} paired measurements...")
        matrices = []  # List of 2×2 complex matrices
        raw_amps = []  # For JSON export

        for trial in range(args.trials):
            # Capture at RX1
            set_relay(mux, RX1_RELAY)
            time.sleep(0.08)
            sp1 = capture_complex(ps, handle)
            a_f1_rx1 = extract_peak(sp1, F1)
            a_f2_rx1 = extract_peak(sp1, F2)

            # Capture at RX2 (plate still ringing — Q=3500, decay time ~60ms)
            set_relay(mux, RX2_RELAY)
            time.sleep(0.08)
            sp2 = capture_complex(ps, handle)
            a_f1_rx2 = extract_peak(sp2, F1)
            a_f2_rx2 = extract_peak(sp2, F2)

            # Form state matrix M: rows=frequency, cols=space
            M = np.array([[a_f1_rx1, a_f1_rx2],
                          [a_f2_rx1, a_f2_rx2]], dtype=complex)
            matrices.append(M)

            raw_amps.append({
                'f1_rx1': [float(a_f1_rx1.real), float(a_f1_rx1.imag)],
                'f1_rx2': [float(a_f1_rx2.real), float(a_f1_rx2.imag)],
                'f2_rx1': [float(a_f2_rx1.real), float(a_f2_rx1.imag)],
                'f2_rx2': [float(a_f2_rx2.real), float(a_f2_rx2.imag)],
            })

            if (trial + 1) % 10 == 0:
                print(f"    {trial + 1}/{args.trials}")

        # ─── Compute CHSH from averaged matrix ───────────────────
        print("\n[5] Computing CHSH S parameter...")

        # Average matrix (complex mean preserves phase if stable)
        M_avg = np.mean(matrices, axis=0)

        # Normalize: divide by Frobenius norm
        M_norm = M_avg / np.linalg.norm(M_avg, 'fro')

        print(f"\n    State matrix M (normalized):")
        print(f"    [[{M_norm[0,0]:.4f}, {M_norm[0,1]:.4f}],")
        print(f"     [{M_norm[1,0]:.4f}, {M_norm[1,1]:.4f}]]")

        # Singular values → concurrence → theoretical S_max
        opt_alice, opt_bob, svd_info = optimal_chsh_angles(M_norm)
        print(f"\n    SVD: σ₁={svd_info['sigma'][0]:.4f}, σ₂={svd_info['sigma'][1]:.4f}")
        print(f"    Concurrence: {svd_info['concurrence']:.4f}")
        print(f"    Theoretical S_max: {svd_info['S_theoretical_max']:.4f}")

        # Compute S with standard angles
        S_std, E_std = compute_S(M_norm,
                                  [np.radians(a) for a in ALICE_ANGLES],
                                  [np.radians(b) for b in BOB_ANGLES])
        print(f"\n    Standard angles (0/45/22.5/67.5):")
        print(f"      E(0°, 22.5°)  = {E_std['E11']:+.4f}")
        print(f"      E(0°, 67.5°)  = {E_std['E12']:+.4f}")
        print(f"      E(45°, 22.5°) = {E_std['E21']:+.4f}")
        print(f"      E(45°, 67.5°) = {E_std['E22']:+.4f}")
        print(f"      S = {S_std:.4f}")

        # Compute S with optimal SVD-aligned angles
        S_opt, E_opt = compute_S(M_norm, opt_alice, opt_bob)
        print(f"\n    Optimal angles (SVD-aligned):")
        print(f"      Alice: [{np.degrees(opt_alice[0]):.1f}°, {np.degrees(opt_alice[1]):.1f}°]")
        print(f"      Bob:   [{np.degrees(opt_bob[0]):.1f}°, {np.degrees(opt_bob[1]):.1f}°]")
        print(f"      E(a1,b1) = {E_opt['E11']:+.4f}")
        print(f"      E(a1,b2) = {E_opt['E12']:+.4f}")
        print(f"      E(a2,b1) = {E_opt['E21']:+.4f}")
        print(f"      E(a2,b2) = {E_opt['E22']:+.4f}")
        print(f"      S = {S_opt:.4f}")

        # ─── Bootstrap error bars ────────────────────────────────
        print("\n[6] Bootstrap confidence interval (1000 resamples)...")
        n_boot = 1000
        S_boot = []
        rng = np.random.default_rng(42)
        for _ in range(n_boot):
            idx = rng.choice(len(matrices), size=len(matrices), replace=True)
            M_b = np.mean([matrices[i] for i in idx], axis=0)
            M_b_norm = M_b / np.linalg.norm(M_b, 'fro')
            S_b, _ = compute_S(M_b_norm, opt_alice, opt_bob)
            S_boot.append(S_b)

        S_boot = np.array(S_boot)
        S_mean = float(np.mean(S_boot))
        S_std_err = float(np.std(S_boot))
        S_ci_lo = float(np.percentile(S_boot, 2.5))
        S_ci_hi = float(np.percentile(S_boot, 97.5))
        sigma_above_2 = (S_mean - 2.0) / S_std_err if S_std_err > 0 else 0

        print(f"    S = {S_mean:.4f} ± {S_std_err:.4f}")
        print(f"    95% CI: [{S_ci_lo:.4f}, {S_ci_hi:.4f}]")
        print(f"    σ above 2.0: {sigma_above_2:.1f}")

        # ─── Phase sweep verification ────────────────────────────
        phase_sweep_data = None
        if args.phase_sweep:
            print("\n[7] Phase sweep — mapping correlation vs DDS phase...")
            phase_sweep_data = []
            # Sweep CH1 phase from 0° to 360° in steps
            set_relay(mux, RX1_RELAY)
            time.sleep(0.1)

            for phase_deg in range(0, 360, 15):
                nco_cmd(nco, f'PHASE:{phase_deg}')
                time.sleep(0.15)

                # Capture at both receivers
                set_relay(mux, RX1_RELAY)
                time.sleep(0.08)
                sp1 = capture_complex(ps, handle)
                a1 = extract_peak(sp1, F1)

                set_relay(mux, RX2_RELAY)
                time.sleep(0.08)
                sp2 = capture_complex(ps, handle)
                a2 = extract_peak(sp2, F1)

                # Spatial contrast for f1 as function of phase
                contrast = (np.abs(a1) - np.abs(a2)) / (np.abs(a1) + np.abs(a2))
                phase_diff = np.angle(a2 / a1) * 180 / np.pi

                phase_sweep_data.append({
                    'phase_deg': phase_deg,
                    'mag_rx1': float(np.abs(a1)),
                    'mag_rx2': float(np.abs(a2)),
                    'contrast': float(contrast),
                    'rx_phase_diff': float(phase_diff),
                })

            # Reset phase
            nco_cmd(nco, 'PHASE:0')

            # Report
            contrasts = [d['contrast'] for d in phase_sweep_data]
            print(f"    Phase sweep: contrast range = "
                  f"[{min(contrasts):.3f}, {max(contrasts):.3f}]")
            print(f"    Contrast varies with phase: "
                  f"{'YES' if max(contrasts) - min(contrasts) > 0.05 else 'NO'}")

        # ─── Results ─────────────────────────────────────────────
        print("\n" + "=" * 60)
        print("  RESULTS — T5.2 CHSH Classical Entanglement")
        print("=" * 60)
        print(f"  State matrix concurrence: {svd_info['concurrence']:.4f}")
        print(f"  S (optimal angles):       {S_opt:.4f}")
        print(f"  S (bootstrap mean ± err): {S_mean:.4f} ± {S_std_err:.4f}")
        print(f"  S (95% CI):               [{S_ci_lo:.4f}, {S_ci_hi:.4f}]")
        print(f"  σ above separable bound:  {sigma_above_2:.1f}")
        print()

        if S_ci_lo > 2.0:
            print("  ★ PASS — S > 2.0 with 95% confidence")
            print("    The plate's frequency×space state is NON-SEPARABLE.")
            verdict = 'PASS'
        elif S_mean > 2.0:
            print("  △ MARGINAL — S > 2.0 but CI includes 2.0")
            verdict = 'MARGINAL'
        else:
            print("  ✗ FAIL — S ≤ 2.0 (state appears separable)")
            verdict = 'FAIL'

        # ─── Save results ────────────────────────────────────────
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        results = {
            'test': 'T5.2_CHSH_classical_entanglement',
            'timestamp': datetime.now().isoformat(),
            'hardware': {
                'nco_port': NCO_PORT,
                'f1_hz': F1,
                'f2_hz': F2,
                'rx1_relay': RX1_RELAY,
                'rx2_relay': RX2_RELAY,
                'n_samples': N,
                'timebase': TIMEBASE,
                'nfft_pad': NFFT_PAD,
            },
            'state_matrix': {
                'real': M_norm.real.tolist(),
                'imag': M_norm.imag.tolist(),
            },
            'svd': svd_info,
            'chsh': {
                'S_optimal': float(S_opt),
                'S_standard': float(S_std),
                'S_bootstrap_mean': S_mean,
                'S_bootstrap_std': S_std_err,
                'S_ci_95': [S_ci_lo, S_ci_hi],
                'sigma_above_2': sigma_above_2,
                'optimal_alice_deg': [float(np.degrees(a)) for a in opt_alice],
                'optimal_bob_deg': [float(np.degrees(b)) for b in opt_bob],
                'E_optimal': E_opt,
                'E_standard': E_std,
            },
            'verdict': verdict,
            'n_trials': args.trials,
            'raw_amplitudes': raw_amps,
        }
        if phase_sweep_data:
            results['phase_sweep'] = phase_sweep_data

        with open(OUT_PATH, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"\n  Results saved: {OUT_PATH}")

    finally:
        nco_cmd(nco, 'Foff')
        ps.ps2000_stop(handle)
        ps.ps2000_close_unit(ct.c_int16(handle))
        nco.close()
        mux.close()
        print("\n  Hardware released.")


if __name__ == '__main__':
    main()
