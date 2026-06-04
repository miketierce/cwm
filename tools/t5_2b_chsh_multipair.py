#!/usr/bin/env python3
"""
T5.2b — CHSH Classical Entanglement Retry (Multi-Pair, High Averaging)

Sweeps multiple mode pairs and angle sets to find maximum S parameter.
Uses higher averaging than T5.2a (50 trials, 20 avg) and tests whether
any mode combination produces non-separable correlations.

Mode pairs tested:
  1. 35840 + 97011  (fundamental + highest, best SNR)
  2. 35840 + 54920  (two lowest, closest spacing)
  3. 54920 + 97011  (mid + high)
  4. 35840 + 57037  (fundamental + 3rd mode)

Also tests an extended angle set: {0°, 22.5°, 45°, 67.5°} for Alice
to probe whether non-standard CHSH angles produce stronger correlations
on this specific plate geometry.
"""
import ctypes as ct
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import serial

# ─── Constants ───────────────────────────────────────────────────
N_SAMPLES = 8064
TIMEBASE = 7
DT = 1280e-9
BIN_HZ = 1.0 / (N_SAMPLES * DT)

# All viable mode pairs (from T5.1 results)
MODE_PAIRS = [
    (35840, 97011, "f1+f4: best SNR pair"),
    (35840, 54920, "f1+f2: lowest modes"),
    (54920, 97011, "f2+f4: mid+high"),
    (35840, 57037, "f1+f3: fundamental+3rd"),
]

# Standard CHSH angles
STANDARD_ANGLES = {
    'alice': [0.0, 45.0],
    'bob': [22.5, 67.5],
}

# Extended angles (probe more of the correlation function)
EXTENDED_ANGLES = {
    'alice': [0.0, 30.0, 45.0, 60.0],
    'bob': [15.0, 37.5, 52.5, 75.0],
}

# Measurement parameters
N_TRIALS = 50
N_AVG = 20
SETTLE_MS = 400

# Receivers
RX1_RELAY = 8
RX2_RELAY = 7

# Hardware
PICO_LIB = '/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources/libps2000.dylib'
MUX_PORT = '/dev/cu.usbserial-11310'
DDS_PORT = '/dev/cu.usbserial-1120'

DATA_DIR = Path(__file__).parent.parent / 'data' / 'results' / 'quantum_bridge'
TIMESTAMP = datetime.now().strftime('%Y%m%d_%H%M%S')
OUT_PATH = DATA_DIR / f't5_2b_chsh_multipair_{TIMESTAMP}.json'


def deg_to_phase_reg(deg):
    return int(round((deg % 360) / 360 * 4096)) % 4096


def init_hardware():
    ps = ct.CDLL(PICO_LIB)
    ps.ps2000_open_unit.restype = ct.c_int16
    handle = ps.ps2000_open_unit()
    print(f"  PicoScope handle: {handle}")
    if handle < 1:
        print("ERROR: PicoScope failed"); sys.exit(1)
    ps.ps2000_set_channel(handle, 0, 1, 0, 7)  # AC coupled, ±5V
    ps.ps2000_set_channel(handle, 1, 0, 0, 7)

    mux = serial.Serial(MUX_PORT, 9600, timeout=2, dsrdtr=False, rtscts=False)
    mux.dtr = False
    time.sleep(0.5); mux.reset_input_buffer()

    dds = serial.Serial(DDS_PORT, 115200, timeout=2)
    time.sleep(2.5); dds.reset_input_buffer()

    return ps, handle, mux, dds


def set_mux(mux, ch):
    for _ in range(3):
        mux.write(f'{ch}\r\n'.encode())
        time.sleep(0.3)
        resp = mux.read(mux.in_waiting).decode(errors='replace').strip()
        if f'OK:{ch}' in resp:
            return True
        time.sleep(0.2)
    return False


def dds_cmd(dds, cmd):
    dds.reset_input_buffer()
    dds.write(f'{cmd}\n'.encode())
    time.sleep(0.05)
    return dds.readline().decode(errors='replace').strip()


def capture_spectrum(ps, handle, navg):
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
        specs.append(np.fft.rfft(d * np.hanning(N_SAMPLES)))
    return np.mean(specs, axis=0)


def extract_amplitude(spectrum, freq_hz, window=3):
    freq_bin = int(round(freq_hz / BIN_HZ))
    lo = max(0, freq_bin - window)
    hi = freq_bin + window + 1
    sub = spectrum[lo:hi]
    peak_idx = np.argmax(np.abs(sub))
    return complex(sub[peak_idx])


def measure_chsh(ps, handle, dds, mux, f1, f2, alice_angles, bob_angles,
                 n_trials, navg, settle_ms, label=""):
    """Run full CHSH measurement for one mode pair and angle set."""
    f1_bin = int(round(f1 / BIN_HZ))
    f2_bin = int(round(f2 / BIN_HZ))

    # Start DDS
    dds_cmd(dds, 'Foff')
    time.sleep(0.2)
    dds_cmd(dds, f'F1:{f1}')
    dds_cmd(dds, f'F2:{f2}')
    time.sleep(0.5)

    # Quick SNR check
    set_mux(mux, RX1_RELAY)
    time.sleep(0.1)
    sp_check = capture_spectrum(ps, handle, 5)
    noise = np.median(np.abs(sp_check[10:]))
    snr1 = np.abs(extract_amplitude(sp_check, f1)) / noise
    snr2 = np.abs(extract_amplitude(sp_check, f2)) / noise
    print(f"    SNR check: f1({f1})={snr1:.1f}×, f2({f2})={snr2:.1f}×")

    if snr1 < 2.0 or snr2 < 2.0:
        print(f"    SKIP — insufficient SNR")
        return None

    correlations = {}
    raw_data = {}

    for a_deg in alice_angles:
        for b_deg in bob_angles:
            a_reg = deg_to_phase_reg(a_deg)
            b_reg = deg_to_phase_reg(b_deg)
            dds_cmd(dds, f'P1:{a_reg}')
            dds_cmd(dds, f'P2:{b_reg}')
            time.sleep(settle_ms / 1000.0)

            r1_f1, r1_f2, r2_f1, r2_f2 = [], [], [], []

            for _ in range(n_trials):
                set_mux(mux, RX1_RELAY)
                time.sleep(0.03)
                sp1 = capture_spectrum(ps, handle, navg)
                r1_f1.append(extract_amplitude(sp1, f1))
                r1_f2.append(extract_amplitude(sp1, f2))

                set_mux(mux, RX2_RELAY)
                time.sleep(0.03)
                sp2 = capture_spectrum(ps, handle, navg)
                r2_f1.append(extract_amplitude(sp2, f1))
                r2_f2.append(extract_amplitude(sp2, f2))

            r1_f1 = np.array(r1_f1)
            r1_f2 = np.array(r1_f2)
            r2_f1 = np.array(r2_f1)
            r2_f2 = np.array(r2_f2)

            # Compute correlation: spatial contrast of each mode
            outcome_a = np.sign(np.abs(r1_f1) - np.abs(r2_f1))
            outcome_b = np.sign(np.abs(r1_f2) - np.abs(r2_f2))
            outcome_a[outcome_a == 0] = 1
            outcome_b[outcome_b == 0] = 1

            products = outcome_a * outcome_b
            E = float(np.mean(products))
            E_err = float(np.std(products) / np.sqrt(len(products)))

            # Also compute phase-based correlation
            phase_diff_a = np.angle(r1_f1 * np.conj(r2_f1))
            phase_diff_b = np.angle(r1_f2 * np.conj(r2_f2))
            outcome_a_ph = np.sign(phase_diff_a)
            outcome_b_ph = np.sign(phase_diff_b)
            outcome_a_ph[outcome_a_ph == 0] = 1
            outcome_b_ph[outcome_b_ph == 0] = 1
            E_ph = float(np.mean(outcome_a_ph * outcome_b_ph))
            E_ph_err = float(np.std(outcome_a_ph * outcome_b_ph) / np.sqrt(n_trials))

            # Continuous correlation (cosine of phase difference product)
            cos_corr = float(np.mean(np.cos(phase_diff_a) * np.cos(phase_diff_b)))

            correlations[(a_deg, b_deg)] = {
                'E': E, 'E_err': E_err,
                'E_phase': E_ph, 'E_phase_err': E_ph_err,
                'cos_corr': cos_corr,
            }

            raw_data[f"{a_deg}_{b_deg}"] = {
                'r1_f1': [[z.real, z.imag] for z in r1_f1],
                'r1_f2': [[z.real, z.imag] for z in r1_f2],
                'r2_f1': [[z.real, z.imag] for z in r2_f1],
                'r2_f2': [[z.real, z.imag] for z in r2_f2],
            }

    # Compute S from best 4 angles (standard CHSH combination)
    # For extended angle sets, find the 4-angle subset giving max S
    best_S = 0.0
    best_S_err = 0.0
    best_S_combo = None
    best_S_method = 'magnitude'

    for method in ['E', 'E_phase']:
        for i, a1 in enumerate(alice_angles):
            for j, a2 in enumerate(alice_angles):
                if i >= j:
                    continue
                for k, b1 in enumerate(bob_angles):
                    for l, b2 in enumerate(bob_angles):
                        if k >= l:
                            continue
                        try:
                            s_raw = (correlations[(a1, b1)][method]
                                     - correlations[(a1, b2)][method]
                                     + correlations[(a2, b1)][method]
                                     + correlations[(a2, b2)][method])
                            s = abs(s_raw)
                            s_err = np.sqrt(
                                correlations[(a1, b1)][f'{method}_err']**2 +
                                correlations[(a1, b2)][f'{method}_err']**2 +
                                correlations[(a2, b1)][f'{method}_err']**2 +
                                correlations[(a2, b2)][f'{method}_err']**2)
                            if s > best_S:
                                best_S = s
                                best_S_err = s_err
                                best_S_combo = (a1, a2, b1, b2)
                                best_S_method = method
                        except KeyError:
                            pass

    sigma = (best_S - 2.0) / best_S_err if best_S_err > 0 else 0.0

    return {
        'f1': f1, 'f2': f2, 'label': label,
        'snr_f1': float(snr1), 'snr_f2': float(snr2),
        'best_S': float(best_S),
        'best_S_err': float(best_S_err),
        'best_S_combo': best_S_combo,
        'best_S_method': best_S_method,
        'sigma_above_2': float(sigma),
        'correlations': {f"{a}_{b}": v for (a, b), v in correlations.items()},
        'raw_data': raw_data,
    }


def cleanup(ps, handle, dds, mux):
    dds_cmd(dds, 'Foff')
    ps.ps2000_stop(handle)
    ps.ps2000_close_unit(ct.c_int16(handle))
    dds.close(); mux.close()


def main():
    print("=" * 60)
    print("  T5.2b — CHSH MULTI-PAIR SWEEP")
    print("=" * 60)
    print(f"  Mode pairs: {len(MODE_PAIRS)}")
    print(f"  Trials/setting: {N_TRIALS}, Averages: {N_AVG}")
    print(f"  Angle sets: standard CHSH + extended scan")
    est_time = len(MODE_PAIRS) * 2 * 4 * N_TRIALS * N_AVG * 0.015 / 60
    print(f"  Estimated time: ~{est_time:.0f} min")
    print()

    print("[1] Hardware init...")
    ps, handle, mux, dds = init_hardware()

    results_all = []
    best_overall_S = 0.0
    best_overall_pair = None

    try:
        for pair_idx, (f1, f2, label) in enumerate(MODE_PAIRS):
            print(f"\n{'=' * 60}")
            print(f"  [{pair_idx+1}/{len(MODE_PAIRS)}] {label}: DDS1={f1}, DDS2={f2}")
            print(f"{'=' * 60}")

            # Standard CHSH angles first
            print(f"\n  Standard angles: Alice {STANDARD_ANGLES['alice']}, "
                  f"Bob {STANDARD_ANGLES['bob']}")
            result = measure_chsh(
                ps, handle, dds, mux, f1, f2,
                STANDARD_ANGLES['alice'], STANDARD_ANGLES['bob'],
                N_TRIALS, N_AVG, SETTLE_MS, label)

            if result:
                results_all.append(result)
                print(f"\n    Best S = {result['best_S']:.4f} ± "
                      f"{result['best_S_err']:.4f} "
                      f"({result['best_S_method']}, "
                      f"angles={result['best_S_combo']})")

                if result['best_S'] > best_overall_S:
                    best_overall_S = result['best_S']
                    best_overall_pair = (f1, f2, label)

            # If this pair shows any promise (S > 1.0), try extended angles
            if result and result['best_S'] > 1.0:
                print(f"\n  Extended angles (S>{1.0} detected)...")
                ext_result = measure_chsh(
                    ps, handle, dds, mux, f1, f2,
                    EXTENDED_ANGLES['alice'], EXTENDED_ANGLES['bob'],
                    N_TRIALS // 2, N_AVG, SETTLE_MS, label + " (extended)")
                if ext_result:
                    results_all.append(ext_result)
                    print(f"    Extended S = {ext_result['best_S']:.4f}")

        # ─── Summary ─────────────────────────────────────────────
        print("\n" + "=" * 60)
        print("  SUMMARY — ALL MODE PAIRS")
        print("=" * 60)
        print(f"\n  {'Pair':<25} | {'S':>8} | {'±err':>8} | {'σ>2':>6} | Method")
        print(f"  {'-'*25}-+-{'-'*8}-+-{'-'*8}-+-{'-'*6}-+-{'-'*10}")
        for r in results_all:
            print(f"  {r['label']:<25} | {r['best_S']:>8.4f} | "
                  f"{r['best_S_err']:>8.4f} | {r['sigma_above_2']:>6.1f} | "
                  f"{r['best_S_method']}")

        if best_overall_S > 2.0:
            print(f"\n  ★ BEST S > 2.0: {best_overall_pair[2]}")
            print(f"    S = {best_overall_S:.4f}")
            print(f"    VERDICT: POSSIBLE NON-SEPARABILITY — needs statistical validation")
        else:
            print(f"\n  All S ≤ 2.0. Best = {best_overall_S:.4f} ({best_overall_pair})")
            print(f"  VERDICT: SEPARABLE — plate modes are independent DOFs")
            print(f"  (Consistent with T2.2: linear medium, no intermodulation)")

        # ─── Save ────────────────────────────────────────────────
        output = {
            'experiment': 'T5.2b CHSH Multi-Pair Sweep',
            'timestamp': TIMESTAMP,
            'parameters': {
                'n_trials': N_TRIALS, 'n_avg': N_AVG,
                'settle_ms': SETTLE_MS,
                'rx1_relay': RX1_RELAY, 'rx2_relay': RX2_RELAY,
            },
            'mode_pairs': [(f1, f2, lbl) for f1, f2, lbl in MODE_PAIRS],
            'best_overall_S': float(best_overall_S),
            'best_overall_pair': best_overall_pair,
            'results': [{k: v for k, v in r.items() if k != 'raw_data'}
                        for r in results_all],
            'gate_pass': bool(best_overall_S > 2.0),
        }

        # Save full data separately (large)
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(OUT_PATH, 'w') as f:
            json.dump(output, f, indent=2)
        print(f"\n  Results: {OUT_PATH.relative_to(Path(__file__).parent.parent)}")

        # Save raw data
        raw_path = DATA_DIR / f't5_2b_chsh_raw_{TIMESTAMP}.json'
        raw_output = {r['label']: r['raw_data'] for r in results_all if 'raw_data' in r}
        with open(raw_path, 'w') as f:
            json.dump(raw_output, f)
        print(f"  Raw data: {raw_path.relative_to(Path(__file__).parent.parent)}")

    finally:
        cleanup(ps, handle, dds, mux)

    print("\nDone.")


if __name__ == '__main__':
    main()
