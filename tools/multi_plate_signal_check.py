#!/usr/bin/env python3
"""
Multi-Plate Signal Chain Verification

Checks that both plates (I and H) are accessible via their relay channels
and producing acoustic signal at known eigenmodes.

Hardware layout:
  Plate I (100×100, pattern I):
    NW RX → Relay 1
    NE RX → Relay 2
    SW TX → Pico NCO (GP2/GP3)

  Plate H (100×100, pattern H):
    NW RX → Relay 3
    NE RX → Relay 4
    SW TX → Pico NCO (GP2/GP3)

Signal chain:
  NCO (GP2) → breadboard → TX PZT (plate) → acoustic → RX PZT → relay mux → preamp → PicoScope Ch A

Test protocol:
  1. For each relay (1-4): drive a sweep of known eigenmodes, capture FFT, measure SNR
  2. Compare signal vs noise-floor (NCO off) at each channel
  3. Report which channels are working and which need debug
"""
import ctypes as ct
import numpy as np
import serial
import time
import json
from datetime import datetime
from pathlib import Path

# ─── Constants ───────────────────────────────────────────────────
PICO_LIB = '/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources/libps2000.dylib'
MUX_PORT = '/dev/cu.usbserial-11310'
NCO_PORT = '/dev/cu.usbmodem113301'

N = 3968
TIMEBASE = 7        # 781,250 Hz sample rate
FS = 781250.0
NFFT = N * 4
BIN_HZ_PAD = FS / NFFT
RNG = 6             # ±2V
RNG_MV = 2000

# Known eigenmodes from L1 characterization (strongest, well-separated)
TEST_FREQS = [35840, 54920, 70000, 87000, 97011, 112000]

# Relay mapping
CHANNELS = {
    1: "Plate I — NW RX",
    2: "Plate I — NE RX",
    3: "Plate H — NW RX",
    4: "Plate H — NE RX",
}

NAVG = 16  # Averages per measurement


# ─── Hardware ────────────────────────────────────────────────────
def init_hardware():
    """Initialize PicoScope, relay mux, and Pico NCO."""
    ps = ct.CDLL(PICO_LIB)
    ps.ps2000_close_unit(ct.c_int16(1))
    time.sleep(0.3)

    ps.ps2000_open_unit.restype = ct.c_int16
    handle = ps.ps2000_open_unit()
    if handle < 1:
        print(f"  ERROR: PicoScope failed to open (handle={handle})")
        return None, None, None, None
    print(f"  PicoScope: handle={handle}")
    ps.ps2000_set_channel(handle, 0, 1, 0, RNG)  # Ch A: enabled, AC, ±2V
    ps.ps2000_set_channel(handle, 1, 0, 0, RNG)  # Ch B: off

    # Relay mux
    mux = serial.Serial(MUX_PORT, 9600, timeout=2, dsrdtr=False, rtscts=False)
    mux.dtr = False
    time.sleep(2.5)
    mux.reset_input_buffer()
    print(f"  Relay mux: {MUX_PORT}")

    # NCO
    nco = serial.Serial(NCO_PORT, 115200, timeout=2)
    time.sleep(0.5)
    nco.reset_input_buffer()
    print(f"  NCO: {NCO_PORT}")

    return ps, handle, mux, nco


def nco_cmd(nco, cmd):
    nco.reset_input_buffer()
    nco.write(f'{cmd}\n'.encode())
    time.sleep(0.05)
    return nco.readline().decode(errors='replace').strip()


def set_relay(mux, relay):
    mux.reset_input_buffer()
    mux.write(f'{relay}\r\n'.encode())
    time.sleep(0.4)
    mux.read(mux.in_waiting)


def capture_magnitude(ps, handle, navg=NAVG):
    """Capture averaged magnitude spectrum."""
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


def peak_snr(spectrum, freq, window=5):
    """Get peak magnitude and SNR at a frequency."""
    b = int(round(freq / BIN_HZ_PAD))
    lo = max(0, b - window)
    hi = min(len(spectrum), b + window + 1)
    peak = float(spectrum[lo:hi].max())

    # Noise: median of spectrum excluding DC and near-signal
    noise_bins = np.concatenate([spectrum[20:lo-10], spectrum[hi+10:]])
    if len(noise_bins) > 0:
        noise = float(np.median(noise_bins))
    else:
        noise = 1.0
    snr = peak / noise if noise > 0 else 0
    return peak, noise, snr


# ─── Main ────────────────────────────────────────────────────────
def main():
    print("=" * 65)
    print("  MULTI-PLATE SIGNAL CHAIN VERIFICATION")
    print("=" * 65)
    print()
    print("  Plate I: relays 1 (NW), 2 (NE) — SW TX → NCO")
    print("  Plate H: relays 3 (NW), 4 (NE) — SW TX → NCO")
    print(f"  Test freqs: {TEST_FREQS}")
    print(f"  Averages: {NAVG}")
    print()

    ps, handle, mux, nco = init_hardware()
    if handle is None:
        return

    results = {}

    try:
        # ─── Step 1: Noise floor (NCO off) at each relay ─────────
        print("\n[1] NOISE FLOOR (NCO off)")
        print("─" * 55)
        nco_cmd(nco, 'Foff')
        time.sleep(0.5)

        noise_floors = {}
        for relay, label in CHANNELS.items():
            set_relay(mux, relay)
            time.sleep(0.2)
            sp = capture_magnitude(ps, handle, navg=8)
            # Median magnitude across spectrum
            nf = float(np.median(sp[20:]))
            noise_floors[relay] = nf
            # Also check for unexpected signal
            max_peak = float(sp[20:].max())
            print(f"  Relay {relay} ({label}): noise={nf:.1f}, max={max_peak:.1f} (ratio={max_peak/nf:.1f}×)")

        # ─── Step 2: Drive each freq, measure at each relay ──────
        print("\n[2] FREQUENCY SWEEP — SIGNAL CHECK")
        print("─" * 55)

        for freq in TEST_FREQS:
            print(f"\n  ▸ Driving {freq} Hz (F1)...")
            nco_cmd(nco, 'Foff')
            time.sleep(0.2)
            nco_cmd(nco, f'F1:{freq}')
            time.sleep(1.5)  # Ring-up

            freq_results = {}
            for relay, label in CHANNELS.items():
                set_relay(mux, relay)
                time.sleep(0.15)
                sp = capture_magnitude(ps, handle)
                peak, noise, snr = peak_snr(sp, freq)
                status = "✓ SIGNAL" if snr > 3.0 else ("△ weak" if snr > 1.5 else "✗ NONE")
                print(f"    Relay {relay} ({label}): peak={peak:.0f}, noise={noise:.0f}, SNR={snr:.1f}× {status}")
                freq_results[relay] = {
                    'peak': peak, 'noise': noise, 'snr': snr,
                    'status': 'pass' if snr > 3.0 else ('weak' if snr > 1.5 else 'fail')
                }

            results[freq] = freq_results

        nco_cmd(nco, 'Foff')

        # ─── Step 3: Summary ─────────────────────────────────────
        print("\n" + "=" * 65)
        print("  SIGNAL CHAIN SUMMARY")
        print("=" * 65)

        for relay, label in CHANNELS.items():
            snrs = [results[f][relay]['snr'] for f in TEST_FREQS]
            best_freq = TEST_FREQS[np.argmax(snrs)]
            best_snr = max(snrs)
            n_pass = sum(1 for s in snrs if s > 3.0)
            n_weak = sum(1 for s in snrs if 1.5 < s <= 3.0)
            n_fail = sum(1 for s in snrs if s <= 1.5)

            if n_pass >= 3:
                verdict = "✓ WORKING"
            elif n_pass >= 1 or n_weak >= 2:
                verdict = "△ PARTIAL"
            else:
                verdict = "✗ NO SIGNAL"

            print(f"  Relay {relay} ({label})")
            print(f"    Best: {best_freq} Hz at {best_snr:.1f}× SNR")
            print(f"    Pass/Weak/Fail: {n_pass}/{n_weak}/{n_fail} of {len(TEST_FREQS)} freqs")
            print(f"    Verdict: {verdict}")
            print()

        # ─── Step 4: Cross-plate comparison ──────────────────────
        print("  CROSS-PLATE DIFFERENTIATION")
        print("  ─────────────────────────────")
        # For each freq, compare Plate I (relays 1,2) vs Plate H (relays 3,4)
        for freq in TEST_FREQS:
            r = results[freq]
            plate_i_avg = (r[1]['snr'] + r[2]['snr']) / 2
            plate_h_avg = (r[3]['snr'] + r[4]['snr']) / 2
            if plate_i_avg > 1.5 and plate_h_avg > 1.5:
                ratio = plate_i_avg / plate_h_avg
                print(f"  {freq:>6} Hz: I={plate_i_avg:.1f}×, H={plate_h_avg:.1f}× (ratio={ratio:.2f})")
            elif plate_i_avg > 1.5:
                print(f"  {freq:>6} Hz: I={plate_i_avg:.1f}×, H=noise")
            elif plate_h_avg > 1.5:
                print(f"  {freq:>6} Hz: I=noise, H={plate_h_avg:.1f}×")
            else:
                print(f"  {freq:>6} Hz: both at noise")

        # Save
        DATA_DIR = Path(__file__).parent.parent / 'data' / 'results'
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        out_path = DATA_DIR / f'multi_plate_signal_check_{ts}.json'
        out = {
            'test': 'multi_plate_signal_check',
            'timestamp': datetime.now().isoformat(),
            'channels': {str(k): v for k, v in CHANNELS.items()},
            'test_freqs': TEST_FREQS,
            'noise_floors': {str(k): v for k, v in noise_floors.items()},
            'results': {str(f): {str(r): v for r, v in rv.items()} for f, rv in results.items()},
        }
        with open(out_path, 'w') as f:
            json.dump(out, f, indent=2)
        print(f"\n  Saved: {out_path}")

    finally:
        nco_cmd(nco, 'Foff')
        nco.close()
        mux.close()
        ps.ps2000_stop(handle)
        ps.ps2000_close_unit(ct.c_int16(handle))
        print("\n  Hardware closed.")


if __name__ == '__main__':
    main()
