#!/usr/bin/env python3
"""
Phase Contrast & Address Selectivity Experiment

Part 1: CONTRAST REPEATABILITY
  - For each shared eigenmode, rapidly toggle between constructive and
    destructive phase N times. Measure the contrast ratio each time.
  - This proves the amplitude control is REPEATABLE, not just noise.

Part 2: ADDRESS SELECTIVITY MATRIX
  - Drive DDS#1 at each eigenmode's best frequency
  - Apply DDS#2 at constructive phase (amplify) and destructive phase (erase)
  - Measure ALL eigenmodes simultaneously
  - Build a crosstalk matrix: does erasing mode A affect modes B and C?

Part 3: BINARY PHASE-SHIFT KEYING (BPSK) DEMO
  - Encode a bit pattern by toggling DDS#2 between constructive (1) and
    destructive (0) phases. Read back the pattern from mode energy.
  - This is the simplest possible "write data" demonstration.

Usage:
  python tools/phase_contrast_selectivity.py
  python tools/phase_contrast_selectivity.py --trials 20 --bpsk-bits 16
"""
import argparse, sys, time, ctypes, json
import numpy as np
import serial
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--trials', type=int, default=10,
                    help='Repetitions per contrast measurement')
parser.add_argument('--navg', type=int, default=20,
                    help='Coherent averages per spectrum')
parser.add_argument('--mux-channel', type=int, default=5)
parser.add_argument('--bpsk-bits', type=int, default=8,
                    help='Number of bits for BPSK demo')
args = parser.parse_args()

DATA_DIR = Path(__file__).parent.parent / 'data' / 'results'

# ─── Hardware (same as phase_sweep_erase.py) ───
TIMEBASE = 7
N_SAMPLES = 8064
DT = 1280e-9


def setup_hardware():
    ps = ctypes.CDLL(
        "/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources/libps2000.dylib")
    ps.ps2000_set_sig_gen_built_in.argtypes = [
        ctypes.c_int16, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32,
        ctypes.c_float, ctypes.c_float, ctypes.c_float, ctypes.c_float,
        ctypes.c_int32, ctypes.c_int32]
    for h in range(1, 5):
        ps.ps2000_close_unit(h)
    time.sleep(0.5)
    handle = ps.ps2000_open_unit()
    print(f"PicoScope handle: {handle}")
    if handle <= 0:
        sys.exit(1)
    ps.ps2000_set_channel(handle, 0, 1, 1, 7)
    ps.ps2000_set_channel(handle, 1, 0, 1, 7)
    ps.ps2000_set_sig_gen_built_in(handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0)
    mux = serial.Serial('/dev/cu.usbserial-11310', 9600, timeout=1)
    time.sleep(2)
    mux.reset_input_buffer()
    dds = serial.Serial('/dev/cu.usbserial-11330', 115200, timeout=2)
    time.sleep(2)
    dds.reset_input_buffer()
    return ps, handle, dds, mux


def dds_cmd(dds, cmd):
    dds.write(f'{cmd}\n'.encode())
    time.sleep(0.01)
    return dds.readline().decode().strip()


def capture(ps, handle):
    buf = (ctypes.c_int16 * N_SAMPLES)()
    ov = ctypes.c_int16(0)
    ps.ps2000_set_trigger(handle, 5, 0, 0, 0, 0)
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
    frames = [capture(ps, handle) for _ in range(n_avg)]
    avg = np.mean(frames, axis=0)
    d = avg - np.mean(avg)
    w = d * np.hanning(len(d))
    nfft = len(d) * 4
    mag = np.abs(np.fft.rfft(w, n=nfft))
    freq = np.fft.rfftfreq(nfft, d=DT)
    return freq, mag


def mode_energy(mag, freq, target_freq, window_hz=2000):
    mask = np.abs(freq - target_freq) < window_hz
    return np.sum(mag[mask])


def cleanup_hardware(ps, handle, dds, mux):
    dds_cmd(dds, 'Foff')
    dds_cmd(dds, 'P1:0')
    dds_cmd(dds, 'P2:0')
    ps.ps2000_set_sig_gen_built_in(handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0)
    ps.ps2000_stop(handle)
    ps.ps2000_close_unit(handle)
    mux.write(b'0\n')
    mux.close()
    dds.close()


def load_sweep_data():
    """Load phase sweep results for constructive/destructive phases."""
    sweep_path = DATA_DIR / 'phase_sweep_erase.json'
    if not sweep_path.exists():
        print("ERROR: Run phase_sweep_erase.py first")
        sys.exit(1)
    with open(sweep_path) as f:
        sweep = json.load(f)

    modes = []
    for key, sd in sweep.items():
        energies = np.array(sd['energies'])
        phases = np.array(sd['phase_values'])
        min_idx = int(np.argmin(energies))
        max_idx = int(np.argmax(energies))
        modes.append({
            'eigenmode_freq': sd['eigenmode_freq'],
            'drive1': sd['drive1'],
            'drive2': sd['drive2'],
            'destructive_phase': int(phases[min_idx]),
            'destructive_deg': sd['phase_degrees'][min_idx],
            'constructive_phase': int(phases[max_idx]),
            'constructive_deg': sd['phase_degrees'][max_idx],
            'sweep_min_energy': float(energies[min_idx]),
            'sweep_max_energy': float(energies[max_idx]),
            'solo1_energy': sd['solo1_energy'],
            'noise_energy': sd['noise_energy'],
            'contrast_ratio': float(energies[max_idx] / energies[min_idx]),
        })
    return modes


# ═══════════════════════════════════════════════════════════════════
#  PART 1: Contrast Repeatability
# ═══════════════════════════════════════════════════════════════════

def contrast_repeatability(ps, handle, dds, modes):
    print("=" * 60)
    print("PART 1: CONTRAST REPEATABILITY")
    print("=" * 60)
    print(f"  Trials per mode: {args.trials}")
    print(f"  Toggle: constructive phase → measure → destructive → measure")

    all_results = {}

    for m in modes:
        ef = m['eigenmode_freq']
        print(f"\n--- Eigenmode ~{ef:.0f} Hz ---")
        print(f"  DDS#1 drive: {m['drive1']} Hz")
        print(f"  DDS#2 drive: {m['drive2']} Hz")
        print(f"  Constructive: phase={m['constructive_phase']} ({m['constructive_deg']:.0f}°)")
        print(f"  Destructive:  phase={m['destructive_phase']} ({m['destructive_deg']:.0f}°)")
        print(f"  Sweep contrast: {m['contrast_ratio']:.2f}x")

        # Set up both DDS at their drive freqs
        dds_cmd(dds, 'Foff')
        dds_cmd(dds, 'P1:0')
        dds_cmd(dds, f'F1:{m["drive1"]}')
        dds_cmd(dds, f'F2:{m["drive2"]}')
        time.sleep(0.3)

        constructive_energies = []
        destructive_energies = []

        print(f"\n  {'Trial':>5} | {'Constructive':>12} | {'Destructive':>12} | {'Ratio':>6}")
        print(f"  {'-'*5} | {'-'*12} | {'-'*12} | {'-'*6}")

        for t in range(args.trials):
            # Constructive phase
            dds_cmd(dds, f'P2:{m["constructive_phase"]}')
            time.sleep(0.15)
            freq, mag_c = coherent_avg_spectrum(ps, handle, args.navg)
            e_c = mode_energy(mag_c, freq, ef)
            constructive_energies.append(e_c)

            # Destructive phase
            dds_cmd(dds, f'P2:{m["destructive_phase"]}')
            time.sleep(0.15)
            _, mag_d = coherent_avg_spectrum(ps, handle, args.navg)
            e_d = mode_energy(mag_d, freq, ef)
            destructive_energies.append(e_d)

            ratio = e_c / e_d if e_d > 0 else float('inf')
            print(f"  {t+1:>5} | {e_c:>12.0f} | {e_d:>12.0f} | {ratio:>5.2f}x")

        dds_cmd(dds, 'Foff')

        c_arr = np.array(constructive_energies)
        d_arr = np.array(destructive_energies)

        # Paired t-test
        from scipy import stats
        t_stat, p_val = stats.ttest_rel(c_arr, d_arr)

        mean_ratio = np.mean(c_arr) / np.mean(d_arr) if np.mean(d_arr) > 0 else 0
        win_rate = np.sum(c_arr > d_arr) / len(c_arr) * 100

        print(f"\n  Summary:")
        print(f"    Constructive mean: {np.mean(c_arr):.0f} ± {np.std(c_arr):.0f}")
        print(f"    Destructive mean:  {np.mean(d_arr):.0f} ± {np.std(d_arr):.0f}")
        print(f"    Mean ratio:        {mean_ratio:.2f}x")
        print(f"    Win rate:          {win_rate:.0f}% (constructive > destructive)")
        print(f"    Paired t-test:     t={t_stat:.2f}, p={p_val:.4f}")

        if p_val < 0.05 and mean_ratio > 1.1:
            print(f"    ✓ STATISTICALLY SIGNIFICANT — phase controls amplitude (p={p_val:.4f})")
        elif p_val < 0.1:
            print(f"    ~ TRENDING — p={p_val:.3f}, needs more trials or better SNR")
        else:
            print(f"    ✗ NOT SIGNIFICANT — p={p_val:.3f}, lost in noise")

        all_results[f"{ef:.0f}"] = {
            'constructive': c_arr.tolist(),
            'destructive': d_arr.tolist(),
            'mean_ratio': float(mean_ratio),
            'win_rate': float(win_rate),
            't_stat': float(t_stat),
            'p_value': float(p_val),
        }

    return all_results


# ═══════════════════════════════════════════════════════════════════
#  PART 2: Address Selectivity Matrix
# ═══════════════════════════════════════════════════════════════════

def address_selectivity_matrix(ps, handle, dds, modes):
    print(f"\n\n{'='*60}")
    print("PART 2: ADDRESS SELECTIVITY MATRIX")
    print("=" * 60)
    print(f"  For each mode: measure ALL modes when that mode is amplified/erased")

    n_modes = len(modes)
    eigenfreqs = [m['eigenmode_freq'] for m in modes]

    # Also add some non-shared eigenmodes as bystanders
    d1 = np.load(DATA_DIR / 'eigenmode_sweep_dds1_5000_100000_5000.npz')
    top_eigenmodes = d1['eigenmode_freqs'][:5]
    bystander_freqs = [f for f in top_eigenmodes
                       if not any(abs(f - ef) < 5000 for ef in eigenfreqs)][:3]

    all_freqs = eigenfreqs + list(bystander_freqs)
    all_labels = [f"~{f:.0f}Hz" for f in all_freqs]
    n_all = len(all_freqs)

    print(f"  Shared eigenmodes: {[f'{f:.0f}' for f in eigenfreqs]}")
    print(f"  Bystander modes:   {[f'{f:.0f}' for f in bystander_freqs]}")

    # Baseline: everything off
    dds_cmd(dds, 'Foff')
    dds_cmd(dds, 'P1:0')
    dds_cmd(dds, 'P2:0')
    time.sleep(0.3)
    freq, baseline_mag = coherent_avg_spectrum(ps, handle, args.navg)
    baseline = np.array([mode_energy(baseline_mag, freq, f) for f in all_freqs])

    # Matrix: rows = which mode is being targeted, cols = energy at each mode
    # Two matrices: one for constructive, one for destructive
    matrix_constructive = np.zeros((n_modes, n_all))
    matrix_destructive = np.zeros((n_modes, n_all))
    matrix_solo = np.zeros((n_modes, n_all))

    for i, m in enumerate(modes):
        ef = m['eigenmode_freq']
        print(f"\n  Targeting mode ~{ef:.0f} Hz (DDS#1={m['drive1']}, DDS#2={m['drive2']})")

        # Solo DDS#1
        dds_cmd(dds, 'Foff')
        dds_cmd(dds, 'P1:0')
        dds_cmd(dds, f'F1:{m["drive1"]}')
        time.sleep(0.3)
        _, solo_mag = coherent_avg_spectrum(ps, handle, args.navg)
        matrix_solo[i] = [mode_energy(solo_mag, freq, f) for f in all_freqs]

        # Constructive (both DDS, constructive phase)
        dds_cmd(dds, f'F2:{m["drive2"]}')
        dds_cmd(dds, f'P2:{m["constructive_phase"]}')
        time.sleep(0.3)
        _, c_mag = coherent_avg_spectrum(ps, handle, args.navg)
        matrix_constructive[i] = [mode_energy(c_mag, freq, f) for f in all_freqs]

        # Destructive (both DDS, destructive phase)
        dds_cmd(dds, f'P2:{m["destructive_phase"]}')
        time.sleep(0.3)
        _, d_mag = coherent_avg_spectrum(ps, handle, args.navg)
        matrix_destructive[i] = [mode_energy(d_mag, freq, f) for f in all_freqs]

    dds_cmd(dds, 'Foff')

    # Print crosstalk matrix
    print(f"\n  ── CROSSTALK MATRIX: % change from baseline ──")
    print(f"\n  CONSTRUCTIVE PHASE (amplify target):")
    header = f"  {'Target':>12} |" + "".join(f" {l:>12}" for l in all_labels)
    print(header)
    print(f"  {'-'*12} |" + "".join(f" {'-'*12}" for _ in all_labels))
    for i, m in enumerate(modes):
        row_label = f"~{m['eigenmode_freq']:.0f}Hz"
        vals = (matrix_constructive[i] - baseline) / np.where(baseline > 0, baseline, 1) * 100
        row = f"  {row_label:>12} |"
        for j, v in enumerate(vals):
            marker = " *" if j == i else "  "  # mark the target column
            row += f" {v:>10.1f}%{marker[1]}"
        print(row)

    print(f"\n  DESTRUCTIVE PHASE (erase target):")
    print(header)
    print(f"  {'-'*12} |" + "".join(f" {'-'*12}" for _ in all_labels))
    for i, m in enumerate(modes):
        row_label = f"~{m['eigenmode_freq']:.0f}Hz"
        vals = (matrix_destructive[i] - baseline) / np.where(baseline > 0, baseline, 1) * 100
        row = f"  {row_label:>12} |"
        for j, v in enumerate(vals):
            marker = " *" if j == i else "  "
            row += f" {v:>10.1f}%{marker[1]}"
        print(row)

    # Selectivity metric: for each targeted mode, what's the ratio of
    # target change vs average bystander change?
    print(f"\n  ── SELECTIVITY METRICS ──")
    print(f"  {'Target':>12} | {'Target Δ%':>10} | {'Bystander avg Δ%':>17} | {'Selectivity':>11}")
    print(f"  {'-'*12} | {'-'*10} | {'-'*17} | {'-'*11}")

    for i, m in enumerate(modes):
        # Use the phase that produces the BIGGEST absolute change on target
        c_changes = (matrix_constructive[i] - baseline) / np.where(baseline > 0, baseline, 1) * 100
        d_changes = (matrix_destructive[i] - baseline) / np.where(baseline > 0, baseline, 1) * 100

        # Use constructive for "write" selectivity
        target_change = c_changes[i]
        bystander_changes = np.abs(np.concatenate([c_changes[:i], c_changes[i+1:]]))
        avg_bystander = np.mean(bystander_changes)
        selectivity = abs(target_change) / avg_bystander if avg_bystander > 0 else float('inf')

        row_label = f"~{m['eigenmode_freq']:.0f}Hz"
        marker = "✓" if selectivity > 2 else "~" if selectivity > 1 else "✗"
        print(f"  {row_label:>12} | {target_change:>+9.1f}% | {avg_bystander:>16.1f}% | "
              f"{selectivity:>9.1f}x {marker}")

    return {
        'baseline': baseline.tolist(),
        'constructive': matrix_constructive.tolist(),
        'destructive': matrix_destructive.tolist(),
        'solo': matrix_solo.tolist(),
        'all_freqs': [float(f) for f in all_freqs],
        'labels': all_labels,
    }


# ═══════════════════════════════════════════════════════════════════
#  PART 3: Binary Phase-Shift Keying (BPSK) Demo
# ═══════════════════════════════════════════════════════════════════

def bpsk_demo(ps, handle, dds, modes):
    print(f"\n\n{'='*60}")
    print("PART 3: BINARY PHASE-SHIFT KEYING (BPSK) DEMO")
    print("=" * 60)

    # Pick the mode with best contrast
    best = max(modes, key=lambda m: m['contrast_ratio'])
    ef = best['eigenmode_freq']
    print(f"  Best contrast mode: ~{ef:.0f} Hz ({best['contrast_ratio']:.2f}x)")
    print(f"  Constructive: phase={best['constructive_phase']} ({best['constructive_deg']:.0f}°)")
    print(f"  Destructive:  phase={best['destructive_phase']} ({best['destructive_deg']:.0f}°)")

    n_bits = args.bpsk_bits
    # Generate random bit pattern
    rng = np.random.RandomState(42)
    tx_bits = rng.randint(0, 2, size=n_bits)
    print(f"  TX pattern ({n_bits} bits): {''.join(str(b) for b in tx_bits)}")

    # Set up DDS
    dds_cmd(dds, 'Foff')
    dds_cmd(dds, 'P1:0')
    dds_cmd(dds, f'F1:{best["drive1"]}')
    dds_cmd(dds, f'F2:{best["drive2"]}')
    time.sleep(0.3)

    # Measure threshold: midpoint between constructive and destructive energies
    # First get a few samples of each to set threshold
    print(f"\n  Calibrating threshold...")
    cal_c, cal_d = [], []
    for _ in range(3):
        dds_cmd(dds, f'P2:{best["constructive_phase"]}')
        time.sleep(0.15)
        freq, mag = coherent_avg_spectrum(ps, handle, args.navg)
        cal_c.append(mode_energy(mag, freq, ef))

        dds_cmd(dds, f'P2:{best["destructive_phase"]}')
        time.sleep(0.15)
        _, mag = coherent_avg_spectrum(ps, handle, args.navg)
        cal_d.append(mode_energy(mag, freq, ef))

    mean_c = np.mean(cal_c)
    mean_d = np.mean(cal_d)
    threshold = (mean_c + mean_d) / 2
    print(f"  Constructive mean: {mean_c:.0f}")
    print(f"  Destructive mean:  {mean_d:.0f}")
    print(f"  Threshold:         {threshold:.0f}")
    print(f"  Separation:        {abs(mean_c - mean_d):.0f} "
          f"({abs(mean_c-mean_d)/threshold*100:.1f}% of threshold)")

    # Transmit and receive
    print(f"\n  Transmitting {n_bits} bits...")
    rx_energies = []
    rx_bits = []

    for i, bit in enumerate(tx_bits):
        if bit == 1:
            dds_cmd(dds, f'P2:{best["constructive_phase"]}')
        else:
            dds_cmd(dds, f'P2:{best["destructive_phase"]}')
        time.sleep(0.15)
        _, mag = coherent_avg_spectrum(ps, handle, args.navg)
        energy = mode_energy(mag, freq, ef)
        rx_energies.append(energy)

        # Decode: above threshold = 1 (constructive), below = 0 (destructive)
        # If constructive > destructive, threshold works normally
        # If constructive < destructive, invert
        if mean_c > mean_d:
            rx_bit = 1 if energy > threshold else 0
        else:
            rx_bit = 0 if energy > threshold else 1
        rx_bits.append(rx_bit)

    dds_cmd(dds, 'Foff')

    rx_bits = np.array(rx_bits)
    errors = np.sum(tx_bits != rx_bits)
    ber = errors / n_bits * 100

    print(f"\n  TX: {''.join(str(b) for b in tx_bits)}")
    print(f"  RX: {''.join(str(b) for b in rx_bits)}")
    print(f"  ERR:{''.join('^' if tx_bits[i] != rx_bits[i] else ' ' for i in range(n_bits))}")
    print(f"\n  Bit errors: {errors}/{n_bits} (BER = {ber:.1f}%)")

    if ber == 0:
        print(f"  ✓✓ PERFECT — {n_bits}-bit message transmitted through glass via phase encoding!")
    elif ber < 10:
        print(f"  ✓ GOOD — {100-ber:.0f}% accuracy, would improve with preamp/ECC")
    elif ber < 30:
        print(f"  ~ MARGINAL — above chance (50%) but error-prone")
    else:
        print(f"  ✗ POOR — near random ({ber:.0f}% BER)")

    # Show energy histogram
    e_arr = np.array(rx_energies)
    ones_energies = e_arr[tx_bits == 1]
    zeros_energies = e_arr[tx_bits == 0]
    print(f"\n  Energy distribution:")
    print(f"    Bit=1 (constructive): {np.mean(ones_energies):.0f} ± {np.std(ones_energies):.0f}")
    print(f"    Bit=0 (destructive):  {np.mean(zeros_energies):.0f} ± {np.std(zeros_energies):.0f}")
    overlap = 0
    if len(ones_energies) > 0 and len(zeros_energies) > 0:
        gap = abs(np.mean(ones_energies) - np.mean(zeros_energies))
        spread = np.std(ones_energies) + np.std(zeros_energies)
        snr_bits = gap / spread if spread > 0 else 0
        print(f"    Symbol SNR:           {snr_bits:.2f} (>1 = distinguishable)")

    return {
        'tx_bits': tx_bits.tolist(),
        'rx_bits': rx_bits.tolist(),
        'rx_energies': [float(e) for e in rx_energies],
        'errors': int(errors),
        'ber': float(ber),
        'threshold': float(threshold),
    }


# ═══════════════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    modes = load_sweep_data()
    print(f"Loaded {len(modes)} modes from phase sweep data:")
    for m in modes:
        print(f"  ~{m['eigenmode_freq']:.0f} Hz: "
              f"constructive={m['constructive_phase']} ({m['constructive_deg']:.0f}°), "
              f"destructive={m['destructive_phase']} ({m['destructive_deg']:.0f}°), "
              f"contrast={m['contrast_ratio']:.2f}x")

    ps, handle, dds, mux = setup_hardware()
    mux.write(f'{args.mux_channel}\n'.encode())
    time.sleep(0.15)
    mux.readline()
    time.sleep(0.1)

    try:
        # Part 1: Contrast repeatability
        contrast_results = contrast_repeatability(ps, handle, dds, modes)

        # Part 2: Address selectivity matrix
        selectivity_results = address_selectivity_matrix(ps, handle, dds, modes)

        # Part 3: BPSK demo
        bpsk_results = bpsk_demo(ps, handle, dds, modes)

        # Save everything
        out = {
            'contrast': contrast_results,
            'selectivity': selectivity_results,
            'bpsk': bpsk_results,
        }
        out_path = DATA_DIR / 'phase_contrast_selectivity.json'
        with open(out_path, 'w') as f:
            json.dump(out, f, indent=2)
        print(f"\nAll results saved to {out_path}")

    finally:
        cleanup_hardware(ps, handle, dds, mux)

    print(f"\n{'='*60}")
    print("EXPERIMENT COMPLETE")
    print(f"{'='*60}")
