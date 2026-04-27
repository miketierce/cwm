#!/usr/bin/env python3
"""
Nonreciprocal Coupling Test

Tests whether DDS1→plate→receivers and DDS2→plate→receivers produce
symmetric or asymmetric amplitude profiles at shared eigenmodes.

Motivation:
  Lai, Miranowicz & Nori (2025) "Nonreciprocal quantum synchronization"
  (Nature Communications 16, 8491) show that phonon synchronization can be
  one-way (nonreciprocal) and robust against noise/defects. If CWM's shared
  eigenmodes show asymmetric coupling — DDS1 drives a mode more efficiently
  than DDS2 at the same frequency, or vice versa — we have a classical analog
  of nonreciprocal phonon flow: a hardware-level one-way function.

Protocol:
  For each shared eigenmode and each receiver:
    Phase 1 (Baseline): Both DDS off → measure noise floor
    Phase 2 (DDS1 solo): DDS1 ON at its drive freq, DDS2 OFF → measure
    Phase 3 (DDS2 solo): DDS2 ON at its drive freq, DDS1 OFF → measure
    Phase 4 (Both): DDS1 + DDS2 both ON → measure
  Repeat for N trials, across all mux channels.

Output:
  - Asymmetry ratio per mode per receiver: A_dds1 / A_dds2
  - If ratio ≠ 1 beyond noise margin → nonreciprocal coupling detected
  - JSON data saved for further analysis

Usage:
  python tools/nonreciprocity_test.py
  python tools/nonreciprocity_test.py --trials 10 --navg 30
  python tools/nonreciprocity_test.py --dry-run   # reanalyze existing data
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
    description='Test nonreciprocal coupling at shared eigenmodes')
parser.add_argument('--trials', type=int, default=8,
                    help='Trials per condition (default: 8)')
parser.add_argument('--navg', type=int, default=20,
                    help='Coherent averages per spectrum (default: 20)')
parser.add_argument('--settle-ms', type=int, default=300,
                    help='Settle time after DDS change, ms (default: 300)')
parser.add_argument('--window-hz', type=float, default=2000,
                    help='Energy integration window around mode, Hz')
parser.add_argument('--dry-run', action='store_true',
                    help='Skip hardware, reanalyze existing data')
args = parser.parse_args()

DATA_DIR = Path(__file__).parent.parent / 'data' / 'results'
OUT_PATH = DATA_DIR / 'nonreciprocity_test.json'

# ─── Shared eigenmodes (from April 24 phase sweep) ──────────────
SHARED_MODES = [
    {
        'label': '~295 kHz',
        'eigenmode_freq': 294750,
        'dds1_freq': 295270,
        'dds2_freq': 294228,
    },
    {
        'label': '~167 kHz',
        'eigenmode_freq': 166745,
        'dds1_freq': 166442,
        'dds2_freq': 167047,
    },
    {
        'label': '~356 kHz',
        'eigenmode_freq': 356184,
        'dds1_freq': 355772,
        'dds2_freq': 356595,
    },
]

# All available receivers
RECEIVERS = [
    {'mux_ch': 1, 'label': 'A-NE'},
    {'mux_ch': 2, 'label': 'B-NE'},
    {'mux_ch': 3, 'label': 'G-NE'},
    {'mux_ch': 5, 'label': 'D-NE'},
    {'mux_ch': 7, 'label': 'H-NE'},
]

# ─── PicoScope constants ────────────────────────────────────────
TIMEBASE = 7
N_SAMPLES = 8064
DT = 1280e-9


# ─── Hardware setup ──────────────────────────────────────────────
def setup_hardware():
    import serial
    ps = ctypes.CDLL(
        "/Applications/PicoScope 7 T&M Early Access.app"
        "/Contents/Resources/libps2000.dylib")
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
        sys.exit("ERROR: Could not open PicoScope")

    # Channel A on, ±100mV, DC coupled; Channel B off
    ps.ps2000_set_channel(handle, 0, 1, 1, 7)
    ps.ps2000_set_channel(handle, 1, 0, 1, 7)
    # AWG off (no parasitic drive)
    ps.ps2000_set_sig_gen_built_in(
        handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0)

    mux = serial.Serial('/dev/cu.usbserial-11310', 9600, timeout=1)
    time.sleep(2)
    mux.reset_input_buffer()

    dds = serial.Serial('/dev/cu.usbserial-11330', 115200, timeout=2)
    time.sleep(2)
    dds.reset_input_buffer()

    return ps, handle, dds, mux


def cleanup_hardware(ps, handle, dds, mux):
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


# ─── DDS / mux helpers ──────────────────────────────────────────
def dds_cmd(dds, cmd):
    dds.write(f'{cmd}\n'.encode())
    time.sleep(0.01)
    return dds.readline().decode().strip()


def set_mux(mux, channel):
    mux.write(f'{channel}\n'.encode())
    time.sleep(0.15)
    mux.readline()


# ─── Capture / spectrum ─────────────────────────────────────────
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


def mode_energy(mag, freq, target_freq, window_hz=None):
    if window_hz is None:
        window_hz = args.window_hz
    mask = np.abs(freq - target_freq) < window_hz
    return float(np.sum(mag[mask]))


# ─── Measurement conditions ─────────────────────────────────────
def measure_condition(ps, handle, dds, mux, mode, condition, receivers):
    """
    Set DDS state for a condition, then measure energy at eigenmode
    across all receivers for one trial.

    condition: 'noise', 'dds1_solo', 'dds2_solo', 'both'
    Returns dict: {receiver_label: energy}
    """
    dds_cmd(dds, 'Foff')
    time.sleep(0.05)

    if condition == 'noise':
        pass  # both off
    elif condition == 'dds1_solo':
        dds_cmd(dds, f'F1:{mode["dds1_freq"]}')
    elif condition == 'dds2_solo':
        dds_cmd(dds, f'F2:{mode["dds2_freq"]}')
    elif condition == 'both':
        dds_cmd(dds, f'F1:{mode["dds1_freq"]}')
        dds_cmd(dds, f'F2:{mode["dds2_freq"]}')

    time.sleep(args.settle_ms / 1000)

    result = {}
    for rx in receivers:
        set_mux(mux, rx['mux_ch'])
        freq, mag = coherent_avg_spectrum(ps, handle, args.navg)
        # Energy at eigenmode center
        e_eigen = mode_energy(mag, freq, mode['eigenmode_freq'])
        # Also energy at each DDS-specific frequency
        e_dds1 = mode_energy(mag, freq, mode['dds1_freq'])
        e_dds2 = mode_energy(mag, freq, mode['dds2_freq'])
        result[rx['label']] = {
            'eigenmode': e_eigen,
            'at_dds1_freq': e_dds1,
            'at_dds2_freq': e_dds2,
        }
    return result


# ─── Main experiment ─────────────────────────────────────────────
def run_experiment():
    ps, handle, dds, mux = setup_hardware()
    conditions = ['noise', 'dds1_solo', 'dds2_solo', 'both']

    all_data = {}

    try:
        for mode in SHARED_MODES:
            label = mode['label']
            print(f"\n{'='*60}")
            print(f"MODE: {label}")
            print(f"  DDS1 freq: {mode['dds1_freq']} Hz")
            print(f"  DDS2 freq: {mode['dds2_freq']} Hz")
            print(f"  Eigenmode: {mode['eigenmode_freq']} Hz")
            print(f"{'='*60}")

            mode_data = {cond: [] for cond in conditions}

            for trial in range(args.trials):
                print(f"\n  Trial {trial+1}/{args.trials}")
                for cond in conditions:
                    result = measure_condition(
                        ps, handle, dds, mux, mode, cond, RECEIVERS)
                    mode_data[cond].append(result)

                    # Brief status
                    rx0 = RECEIVERS[0]['label']
                    e = result[rx0]['eigenmode']
                    print(f"    {cond:>10}: {rx0} = {e:.1f}")

            all_data[label] = mode_data

        dds_cmd(dds, 'Foff')

    finally:
        cleanup_hardware(ps, handle, dds, mux)

    return all_data


# ─── Analysis ────────────────────────────────────────────────────
def analyze(all_data):
    """Compute asymmetry ratios and significance."""
    print(f"\n{'='*70}")
    print("NONRECIPROCITY ANALYSIS")
    print(f"{'='*70}")

    summary = {}

    for mode_label, mode_data in all_data.items():
        print(f"\n--- {mode_label} ---")

        # Gather receiver labels from first trial
        rx_labels = list(mode_data['noise'][0].keys())
        n_trials = len(mode_data['noise'])

        mode_summary = {}

        for rx in rx_labels:
            noise_vals = [t[rx]['eigenmode'] for t in mode_data['noise']]
            dds1_vals = [t[rx]['eigenmode'] for t in mode_data['dds1_solo']]
            dds2_vals = [t[rx]['eigenmode'] for t in mode_data['dds2_solo']]
            both_vals = [t[rx]['eigenmode'] for t in mode_data['both']]

            noise_mean = np.mean(noise_vals)
            dds1_mean = np.mean(dds1_vals)
            dds2_mean = np.mean(dds2_vals)
            both_mean = np.mean(both_vals)

            dds1_std = np.std(dds1_vals, ddof=1) if n_trials > 1 else 0
            dds2_std = np.std(dds2_vals, ddof=1) if n_trials > 1 else 0

            # SNR above noise
            dds1_snr = (dds1_mean - noise_mean) / noise_mean if noise_mean > 0 else 0
            dds2_snr = (dds2_mean - noise_mean) / noise_mean if noise_mean > 0 else 0

            # Asymmetry: DDS1/DDS2 coupling ratio
            if dds2_mean > 0:
                asymmetry = dds1_mean / dds2_mean
            else:
                asymmetry = float('inf')

            # t-test for DDS1 vs DDS2 (paired, since same receiver)
            if n_trials > 1 and dds1_std > 0 and dds2_std > 0:
                diff = np.array(dds1_vals) - np.array(dds2_vals)
                t_stat = np.mean(diff) / (np.std(diff, ddof=1) / np.sqrt(n_trials))
                # Two-tailed p-value approximation (normal for n>6)
                from scipy import stats
                p_val = stats.t.sf(abs(t_stat), n_trials - 1) * 2
            else:
                t_stat = 0
                p_val = 1.0

            mode_summary[rx] = {
                'noise_mean': noise_mean,
                'dds1_mean': dds1_mean,
                'dds2_mean': dds2_mean,
                'both_mean': both_mean,
                'dds1_std': dds1_std,
                'dds2_std': dds2_std,
                'dds1_snr': dds1_snr,
                'dds2_snr': dds2_snr,
                'asymmetry_ratio': asymmetry,
                't_stat': t_stat,
                'p_value': p_val,
            }

            sig = '***' if p_val < 0.001 else '**' if p_val < 0.01 else '*' if p_val < 0.05 else ''
            print(f"  {rx:>5}:  DDS1={dds1_mean:8.1f} ± {dds1_std:6.1f}  "
                  f"DDS2={dds2_mean:8.1f} ± {dds2_std:6.1f}  "
                  f"ratio={asymmetry:.3f}  p={p_val:.4f} {sig}")

        summary[mode_label] = mode_summary

    # ── Verdict ──
    print(f"\n{'='*70}")
    print("VERDICT")
    print(f"{'='*70}")

    any_nonreciprocal = False
    for mode_label, mode_summary in summary.items():
        for rx, s in mode_summary.items():
            if s['p_value'] < 0.05 and abs(s['asymmetry_ratio'] - 1.0) > 0.1:
                any_nonreciprocal = True
                direction = 'DDS1 > DDS2' if s['asymmetry_ratio'] > 1 else 'DDS2 > DDS1'
                print(f"  NONRECIPROCAL: {mode_label} @ {rx}  "
                      f"ratio={s['asymmetry_ratio']:.3f} ({direction})  "
                      f"p={s['p_value']:.4f}")

    if not any_nonreciprocal:
        print("  No statistically significant asymmetry detected (p<0.05, |ratio-1|>0.1)")
        print("  Coupling appears reciprocal at current SNR.")
        print("  NOTE: DDS1 and DDS2 drive at slightly different frequencies")
        print("        (e.g., 295270 vs 294228 Hz). Any asymmetry could reflect")
        print("        different positions on the eigenmode resonance curve,")
        print("        not true nonreciprocity. To distinguish, repeat with")
        print("        both DDS at exactly the same frequency (requires AWG).")

    return summary


# ─── Main ────────────────────────────────────────────────────────
def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if args.dry_run:
        if not OUT_PATH.exists():
            sys.exit(f"ERROR: No data file at {OUT_PATH}")
        with open(OUT_PATH) as f:
            saved = json.load(f)
        analyze(saved['data'])
        return

    all_data = run_experiment()

    # Save raw data
    output = {
        'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S'),
        'args': {
            'trials': args.trials,
            'navg': args.navg,
            'settle_ms': args.settle_ms,
            'window_hz': args.window_hz,
        },
        'shared_modes': SHARED_MODES,
        'receivers': [r['label'] for r in RECEIVERS],
        'data': all_data,
    }
    with open(OUT_PATH, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nData saved: {OUT_PATH}")

    summary = analyze(all_data)

    # Append summary
    output['summary'] = {}
    for mode_label, mode_summary in summary.items():
        output['summary'][mode_label] = {}
        for rx, s in mode_summary.items():
            output['summary'][mode_label][rx] = {
                k: (float(v) if isinstance(v, (np.floating, float)) else v)
                for k, v in s.items()
            }
    with open(OUT_PATH, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    print(f"Summary appended: {OUT_PATH}")


if __name__ == '__main__':
    main()
