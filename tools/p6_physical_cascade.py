#!/usr/bin/env python3
"""
P6 Physical: Multi-Plate Cascade — Physical Measurement

Hardware: NCO → Plate I SW TX → (acoustic) → Plate I NE RX → [jumper] → Plate H SW TX → (acoustic) → Plate H RX

Signal chain:
  - Relay 1: Plate I NW RX (direct, reference)
  - Relay 2: Plate I NE RX (direct, also cascade drive source)
  - Relay 3: Plate H NW RX (cascade output)
  - Relay 4: Plate H NE RX (cascade output)

The cascade channels carry the PRODUCT of both plates' transfer functions:
  H_cascade[f] = H_plateH[f] × H_plateI_NE[f] × coupling_efficiency

This experiment measures:
  1. Direct H matrix (Plate I alone) vs cascade H matrix (through both plates)
  2. Rank expansion: does cascading increase effective dimensionality?
  3. Spectral reshaping: which modes survive the double-plate filter?
  4. Comparison with P6 simulation predictions
"""
import ctypes as ct
import numpy as np
import serial
import time
import json
from datetime import datetime
from pathlib import Path

# ─── Hardware Constants ───────────────────────────────────────────
PICO_LIB = '/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources/libps2000.dylib'
N = 3968
TIMEBASE = 7
RNG = 6
RNG_MV = 2000
FS = 781250.0
NFFT = N * 4
BIN_HZ = FS / NFFT

# Relay map
RELAY_PI_NW = 1   # Plate I NW RX (direct reference)
RELAY_PI_NE = 2   # Plate I NE RX (also feeds cascade)
RELAY_PH_NW = 3   # Plate H NW RX (cascade output)
RELAY_PH_NE = 4   # Plate H NE RX (cascade output)

ALL_RELAYS = [RELAY_PI_NW, RELAY_PI_NE, RELAY_PH_NW, RELAY_PH_NE]
RELAY_NAMES = {1: 'PI_NW', 2: 'PI_NE', 3: 'PH_NW', 4: 'PH_NE'}

# Mode frequencies from enrollment
MODE_FREQS = [
    33040, 35840, 38740, 41570, 44530, 48510, 51510, 54920,
    57370, 60160, 63210, 66460, 69790, 73050, 76350, 79370,
    82390, 85080, 88510, 91790, 94540, 97011, 100070, 103460,
    107130, 113280, 119240
]

NAVG = 24  # Averaging passes per measurement


def setup_hardware():
    ps = ct.CDLL(PICO_LIB)
    for h in range(1, 5):
        ps.ps2000_close_unit(ct.c_int16(h))
    time.sleep(0.3)

    ps.ps2000_open_unit.restype = ct.c_int16
    handle = ps.ps2000_open_unit()
    if handle <= 0:
        raise RuntimeError(f"PicoScope open failed: handle={handle}")
    ps.ps2000_set_channel(handle, 0, 1, 0, RNG)

    ser = serial.Serial('/dev/cu.usbmodem113301', 115200, timeout=2)
    time.sleep(0.5)
    ser.reset_input_buffer()

    mux = serial.Serial('/dev/cu.usbserial-11310', 9600, timeout=2,
                        dsrdtr=False, rtscts=False)
    mux.dtr = False
    time.sleep(2.5)
    mux.reset_input_buffer()

    return ps, handle, ser, mux


def nco(ser, cmd):
    ser.reset_input_buffer()
    ser.write(f'{cmd}\n'.encode())
    time.sleep(0.05)
    return ser.readline().decode(errors='replace').strip()


def set_relay(mux, r):
    mux.reset_input_buffer()
    mux.write(f'{r}\r\n'.encode())
    time.sleep(0.35)
    mux.read(mux.in_waiting)


def capture_spectrum(ps, handle, navg=NAVG):
    buf = (ct.c_int16 * N)()
    ov = ct.c_int16()
    mags = []
    for _ in range(navg):
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
        mags.append(np.abs(np.fft.rfft(d * np.hanning(N), n=NFFT)))
    return np.mean(mags, axis=0)


def peak_amplitude(spec, freq, window=5):
    b = int(round(freq / BIN_HZ))
    return float(spec[max(0, b - window):b + window + 1].max())


def measure_noise_floor(ps, handle, mux, ser):
    """Measure noise floor with NCO off on all relays."""
    nco(ser, 'Foff')
    time.sleep(0.3)
    floors = {}
    for relay in ALL_RELAYS:
        set_relay(mux, relay)
        time.sleep(0.2)
        spec = capture_spectrum(ps, handle, navg=8)
        floors[relay] = float(np.median(spec))
    return floors


def main():
    print("=" * 70)
    print("  P6 Physical: Multi-Plate Cascade Measurement")
    print("=" * 70)
    print()
    print("  Wiring: NCO → Plate I SW TX → Plate I NE RX → Plate H SW TX → Plate H RX")
    print("  Relay 1: Plate I NW (direct)")
    print("  Relay 2: Plate I NE (direct + cascade source)")
    print("  Relay 3: Plate H NW (cascade output)")
    print("  Relay 4: Plate H NE (cascade output)")
    print(f"  Modes:   {len(MODE_FREQS)}")
    print(f"  Averaging: {NAVG} captures per measurement")
    print()

    ps, handle, ser, mux = setup_hardware()

    # ── Noise floor ───────────────────────────────────────────────
    print("  [1] Measuring noise floor...")
    noise = measure_noise_floor(ps, handle, mux, ser)
    for r, n in noise.items():
        print(f"    {RELAY_NAMES[r]}: {n:.0f} mV")
    print()

    # ── Full sweep: measure all modes on all 4 channels ──────────
    print(f"  [2] Sweeping {len(MODE_FREQS)} modes × 4 receivers...")
    # H_physical[mode_idx, relay_idx]
    H_raw = np.zeros((len(MODE_FREQS), 4))

    for i, freq in enumerate(MODE_FREQS):
        nco(ser, f'F1:{freq}')
        time.sleep(0.3)

        for j, relay in enumerate(ALL_RELAYS):
            set_relay(mux, relay)
            time.sleep(0.15)
            spec = capture_spectrum(ps, handle)
            H_raw[i, j] = peak_amplitude(spec, freq)

        # Progress
        if (i + 1) % 5 == 0 or i == 0:
            pi_nw = H_raw[i, 0]
            cascade_nw = H_raw[i, 2]
            ratio = cascade_nw / pi_nw if pi_nw > 0 else 0
            print(f"    {i+1}/{len(MODE_FREQS)}: {freq} Hz — "
                  f"PI_NW={pi_nw:.0f}, PH_NW(cascade)={cascade_nw:.0f}, "
                  f"ratio={ratio:.3f}")

    nco(ser, 'Foff')

    # ── Analysis ──────────────────────────────────────────────────
    print(f"\n  [3] Analysis...")
    print()

    # SNR check: which cascade channels are above noise?
    noise_thresh = max(noise.values()) * 3  # 3× noise floor
    cascade_valid = np.zeros(len(MODE_FREQS), dtype=bool)
    for i in range(len(MODE_FREQS)):
        if H_raw[i, 2] > noise_thresh or H_raw[i, 3] > noise_thresh:
            cascade_valid[i] = True

    n_valid = cascade_valid.sum()
    print(f"  Cascade modes above 3× noise: {n_valid}/{len(MODE_FREQS)}")
    print()

    # Direct channels (Plate I only): columns 0,1
    H_direct = H_raw[:, :2]
    # Cascade channels (Plate H output): columns 2,3
    H_cascade = H_raw[:, 2:]
    # Combined: all 4 channels
    H_combined = H_raw.copy()

    # Normalize each for SVD comparison
    def analyze(M, name, valid_mask=None):
        if valid_mask is not None:
            M = M[valid_mask]
        # Normalize columns
        col_norms = np.linalg.norm(M, axis=0)
        col_norms[col_norms == 0] = 1
        Mn = M / col_norms
        U, s, Vt = np.linalg.svd(Mn, full_matrices=False)
        s_norm = s / (s.sum() + 1e-15)
        entropy = -np.sum(s_norm * np.log(s_norm + 1e-15))
        eff_rank = np.exp(entropy)
        cond = s[0] / s[-1] if s[-1] > 1e-10 else np.inf
        print(f"    {name} ({M.shape[0]}×{M.shape[1]}):")
        print(f"      SVD σ: [{', '.join(f'{v:.3f}' for v in s)}]")
        print(f"      Condition: {cond:.2f}")
        print(f"      Eff. rank: {eff_rank:.2f}")
        return s, eff_rank, cond

    print("  Matrix analysis (all modes):")
    s_direct, rank_direct, _ = analyze(H_direct, "Direct (Plate I only, 2ch)")
    s_cascade, rank_cascade, _ = analyze(H_cascade, "Cascade (Plate H out, 2ch)")
    s_combined, rank_combined, cond_combined = analyze(H_combined, "Combined (4ch)")
    print()

    if n_valid >= 10:
        print("  Matrix analysis (cascade-valid modes only):")
        analyze(H_direct, "Direct (valid modes)", cascade_valid)
        analyze(H_cascade, "Cascade (valid modes)", cascade_valid)
        analyze(H_combined, "Combined (valid modes)", cascade_valid)
        print()

    # Coupling efficiency
    print("  Cascade coupling efficiency:")
    for i in range(len(MODE_FREQS)):
        if H_raw[i, 1] > noise_thresh:  # Only where PI_NE is strong
            coupling_nw = H_raw[i, 2] / H_raw[i, 1] if H_raw[i, 1] > 0 else 0
            coupling_ne = H_raw[i, 3] / H_raw[i, 1] if H_raw[i, 1] > 0 else 0
            if i < 5 or coupling_nw > 0.1:
                print(f"    {MODE_FREQS[i]} Hz: PI_NE→PH_NW = {coupling_nw:.4f}, "
                      f"PI_NE→PH_NE = {coupling_ne:.4f}")

    # Mean coupling
    mask = H_raw[:, 1] > noise_thresh
    if mask.sum() > 0:
        couplings = H_raw[mask, 2] / H_raw[mask, 1]
        print(f"\n    Mean coupling (PI_NE → PH_NW): {np.mean(couplings):.4f} "
              f"± {np.std(couplings):.4f}")
        print(f"    Range: [{np.min(couplings):.4f}, {np.max(couplings):.4f}]")

    # Spectral reshaping: do cascade channels have DIFFERENT mode rankings?
    print("\n  Spectral reshaping (top 5 modes by channel):")
    for j, name in enumerate(['PI_NW', 'PI_NE', 'PH_NW(cascade)', 'PH_NE(cascade)']):
        top5 = np.argsort(H_raw[:, j])[-5:][::-1]
        freqs_str = ', '.join(f'{MODE_FREQS[k]}' for k in top5)
        print(f"    {name}: {freqs_str}")

    # Rank comparison with simulation
    print("\n  Rank comparison:")
    print(f"    Direct (2ch):   eff. rank = {rank_direct:.2f}")
    print(f"    Cascade (2ch):  eff. rank = {rank_cascade:.2f}")
    print(f"    Combined (4ch): eff. rank = {rank_combined:.2f}")
    print(f"    P6 simulation predicted: 4→6 (1.5× expansion)")
    expansion = rank_combined / rank_direct if rank_direct > 0 else 0
    print(f"    Measured expansion: {expansion:.2f}×")

    # ── Verdict ───────────────────────────────────────────────────
    print()
    print("=" * 70)
    print("  P6 PHYSICAL CASCADE — VERDICT")
    print("=" * 70)
    print()

    if n_valid < 5:
        verdict = "FAIL_NO_SIGNAL"
        print(f"  ✗ FAIL — Only {n_valid} cascade modes above noise")
        print("    Passive PZT-to-PZT coupling too weak without amplifier")
    elif rank_combined > rank_direct * 1.2:
        verdict = "PASS"
        print(f"  ★ PASS — Cascade increases effective rank by {expansion:.2f}×")
        print(f"    Combined rank {rank_combined:.1f} > Direct rank {rank_direct:.1f}")
    elif n_valid >= 10:
        verdict = "PASS_MARGINAL"
        print(f"  △ PASS (marginal) — {n_valid} cascade modes detected")
        print(f"    Rank expansion: {expansion:.2f}×")
    else:
        verdict = "FAIL"
        print(f"  ✗ FAIL — Insufficient rank expansion ({expansion:.2f}×)")

    print()

    # ── Save ──────────────────────────────────────────────────────
    DATA_DIR = Path('data/results/cascade')
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    out_path = DATA_DIR / f'p6_physical_cascade_{ts}.json'

    output = {
        'experiment': 'P6_physical_cascade',
        'timestamp': datetime.now().isoformat(),
        'wiring': 'NCO → Plate_I_SW_TX → Plate_I_NE_RX → [jumper] → Plate_H_SW_TX → Plate_H_RX',
        'config': {
            'mode_frequencies_hz': MODE_FREQS,
            'relay_map': {str(k): v for k, v in RELAY_NAMES.items()},
            'n_avg': NAVG,
            'n_modes': len(MODE_FREQS),
        },
        'noise_floor': {RELAY_NAMES[k]: v for k, v in noise.items()},
        'h_matrix_raw': H_raw.tolist(),
        'h_matrix_columns': ['PI_NW', 'PI_NE', 'PH_NW_cascade', 'PH_NE_cascade'],
        'cascade_valid_modes': [MODE_FREQS[i] for i in range(len(MODE_FREQS)) if cascade_valid[i]],
        'n_cascade_valid': int(n_valid),
        'svd': {
            'direct_2ch': [float(v) for v in s_direct],
            'cascade_2ch': [float(v) for v in s_cascade],
            'combined_4ch': [float(v) for v in s_combined],
        },
        'effective_rank': {
            'direct_2ch': float(rank_direct),
            'cascade_2ch': float(rank_cascade),
            'combined_4ch': float(rank_combined),
        },
        'rank_expansion': float(expansion),
        'verdict': verdict,
    }

    with open(out_path, 'w') as f:
        json.dump(output, f, indent=2)
    print(f"  Saved: {out_path}")

    # Cleanup
    ser.close()
    mux.close()
    ps.ps2000_stop(handle)
    ps.ps2000_close_unit(ct.c_int16(handle))
    print("  Done.")


if __name__ == '__main__':
    main()
