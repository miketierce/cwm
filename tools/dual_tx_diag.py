#!/usr/bin/env python3
"""Dual-TX diagnostic: verify DDS1→SW PZT and DDS2→NE PZT both reach NW RX (relay 7)."""

import ctypes as ct
import numpy as np
import serial
import time
import os

os.environ['DYLD_LIBRARY_PATH'] = '/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources'
ps = ct.CDLL('/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources/libps2000.dylib')

# --- Open hardware ---
ps.ps2000_open_unit.restype = ct.c_int16
h = ps.ps2000_open_unit()
print(f"PicoScope handle: {h}")
assert h > 0, "PicoScope failed to open"

ps.ps2000_set_channel(h, 0, 1, 0, 7)  # Ch A: AC coupled, ±5V
ps.ps2000_set_channel(h, 1, 0, 0, 7)  # Ch B: off

dds = serial.Serial('/dev/cu.usbserial-1120', 115200, timeout=2)
time.sleep(2.5)
dds.reset_input_buffer()

mux = serial.Serial('/dev/cu.usbserial-11310', 9600, timeout=2, dsrdtr=False, rtscts=False)
mux.dtr = False
time.sleep(0.5)
mux.reset_input_buffer()

# Select relay 7 (NW RX)
for _ in range(4):
    mux.write(b'7\r\n')
    time.sleep(0.5)
    resp = mux.read(mux.in_waiting).decode(errors='replace').strip()
    if 'OK:7' in resp:
        break
    time.sleep(0.8)
print(f"Relay mux: {resp}")

# --- Capture params ---
NSAMPLES = 8064
TIMEBASE = 7  # 781250 Hz
SR = 781250.0
BIN_HZ = SR / NSAMPLES  # ~96.9 Hz
N_AVG = 10

buf = (ct.c_int16 * NSAMPLES)()
ov = ct.c_int16()


def capture_avg(n=N_AVG):
    """Capture n blocks and return averaged magnitude spectrum."""
    spectra = []
    for _ in range(n):
        ps.ps2000_set_trigger(h, 5, 0, 0, 0, 0)
        ticks = ct.c_int32()
        ps.ps2000_run_block(h, NSAMPLES, TIMEBASE, 1, ct.byref(ticks))
        for __ in range(500):
            if ps.ps2000_ready(h):
                break
            time.sleep(0.001)
        ps.ps2000_get_values(h, ct.byref(buf), None, None, None, ct.byref(ov), NSAMPLES, 0)
        raw = np.array(buf[:], dtype=float)
        raw -= np.mean(raw)
        sp = np.abs(np.fft.rfft(raw * np.hanning(NSAMPLES)))
        spectra.append(sp)
        time.sleep(0.005)
    return np.mean(spectra, axis=0)


def peak_at(spectrum, freq_hz, search_bins=5):
    """Return peak magnitude within ±search_bins of target frequency."""
    b = int(round(freq_hz / BIN_HZ))
    lo = max(0, b - search_bins)
    hi = min(len(spectrum) - 1, b + search_bins)
    return float(np.max(spectrum[lo:hi+1]))


def noise_floor(spectrum, exclude_freqs, exclude_width=10):
    """Median of spectrum excluding regions around known frequencies."""
    mask = np.ones(len(spectrum), dtype=bool)
    for f in exclude_freqs:
        b = int(round(f / BIN_HZ))
        mask[max(0, b-exclude_width):b+exclude_width+1] = False
    mask[:5] = False  # exclude DC region
    return float(np.median(spectrum[mask]))


# --- Test frequencies ---
F1 = 35840   # DDS1 → SW PZT
F2 = 97011   # DDS2 → NE PZT

print("\n" + "="*60)
print("DUAL-TX DIAGNOSTIC")
print("="*60)
print(f"  DDS1 → Board D Ch B → SW PZT @ {F1} Hz")
print(f"  DDS2 → Board D Ch A → NE PZT @ {F2} Hz")
print(f"  RX: NW PZT → relay 7 → Board A → PicoScope Ch A")
print(f"  Capture: {NSAMPLES} samples @ {SR/1000:.0f} kHz, {N_AVG} averages")
print("="*60)

# --- Test 1: Noise floor (both off) ---
print("\n[1] NOISE FLOOR (both DDS off)...")
dds.write(b'Foff\n')
time.sleep(0.2)
dds.reset_input_buffer()
time.sleep(0.1)

sp_noise = capture_avg()
nf = noise_floor(sp_noise, [F1, F2])
pk1_noise = peak_at(sp_noise, F1)
pk2_noise = peak_at(sp_noise, F2)
print(f"    Noise floor (median): {nf:.1f}")
print(f"    @ {F1} Hz: {pk1_noise:.1f}  (should be ~noise)")
print(f"    @ {F2} Hz: {pk2_noise:.1f}  (should be ~noise)")

# --- Test 2: DDS1 only → SW PZT ---
print(f"\n[2] DDS1 ONLY @ {F1} Hz (SW TX)...")
dds.write(f'F1:{F1}\n'.encode())
time.sleep(0.3)
dds.reset_input_buffer()

sp_dds1 = capture_avg()
pk1_dds1 = peak_at(sp_dds1, F1)
pk2_dds1 = peak_at(sp_dds1, F2)
nf1 = noise_floor(sp_dds1, [F1, F2])
snr1 = pk1_dds1 / nf1 if nf1 > 0 else 0
print(f"    @ {F1} Hz: {pk1_dds1:.1f}  SNR = {snr1:.1f}×")
print(f"    @ {F2} Hz: {pk2_dds1:.1f}  (crosstalk check)")

dds.write(b'Foff\n')
time.sleep(0.2)
dds.reset_input_buffer()

# --- Test 3: DDS2 only → NE PZT ---
print(f"\n[3] DDS2 ONLY @ {F2} Hz (NE TX)...")
dds.write(f'F2:{F2}\n'.encode())
time.sleep(0.3)
dds.reset_input_buffer()

sp_dds2 = capture_avg()
pk1_dds2 = peak_at(sp_dds2, F1)
pk2_dds2 = peak_at(sp_dds2, F2)
nf2 = noise_floor(sp_dds2, [F1, F2])
snr2 = pk2_dds2 / nf2 if nf2 > 0 else 0
print(f"    @ {F1} Hz: {pk1_dds2:.1f}  (crosstalk check)")
print(f"    @ {F2} Hz: {pk2_dds2:.1f}  SNR = {snr2:.1f}×")

dds.write(b'Foff\n')
time.sleep(0.2)
dds.reset_input_buffer()

# --- Test 4: Both DDS simultaneously ---
print(f"\n[4] BOTH DDS: DDS1@{F1} + DDS2@{F2}...")
dds.write(f'F1:{F1}\n'.encode())
time.sleep(0.1)
dds.reset_input_buffer()
dds.write(f'F2:{F2}\n'.encode())
time.sleep(0.3)
dds.reset_input_buffer()

sp_both = capture_avg()
pk1_both = peak_at(sp_both, F1)
pk2_both = peak_at(sp_both, F2)
nf_both = noise_floor(sp_both, [F1, F2])
snr1_both = pk1_both / nf_both if nf_both > 0 else 0
snr2_both = pk2_both / nf_both if nf_both > 0 else 0
print(f"    @ {F1} Hz: {pk1_both:.1f}  SNR = {snr1_both:.1f}×")
print(f"    @ {F2} Hz: {pk2_both:.1f}  SNR = {snr2_both:.1f}×")

# --- Test 5: Swap frequencies to confirm routing ---
print(f"\n[5] SWAP: DDS1@{F2} + DDS2@{F1} (verify independent routing)...")
dds.write(b'Foff\n')
time.sleep(0.2)
dds.reset_input_buffer()
dds.write(f'F1:{F2}\n'.encode())
time.sleep(0.1)
dds.reset_input_buffer()
dds.write(f'F2:{F1}\n'.encode())
time.sleep(0.3)
dds.reset_input_buffer()

sp_swap = capture_avg()
pk1_swap = peak_at(sp_swap, F2)  # DDS1 now at F2
pk2_swap = peak_at(sp_swap, F1)  # DDS2 now at F1
nf_swap = noise_floor(sp_swap, [F1, F2])
snr1_swap = pk1_swap / nf_swap if nf_swap > 0 else 0
snr2_swap = pk2_swap / nf_swap if nf_swap > 0 else 0
print(f"    DDS1@{F2}: {pk1_swap:.1f}  SNR = {snr1_swap:.1f}×")
print(f"    DDS2@{F1}: {pk2_swap:.1f}  SNR = {snr2_swap:.1f}×")

# --- Cleanup ---
dds.write(b'Foff\n')
time.sleep(0.1)
ps.ps2000_stop(h)
ps.ps2000_close_unit(ct.c_int16(h))
dds.close()
mux.close()

# --- Summary ---
print("\n" + "="*60)
print("SUMMARY")
print("="*60)

PASS_THRESHOLD = 3.0  # need at least 3× SNR

results = []

# DDS1 channel working?
dds1_ok = snr1 >= PASS_THRESHOLD
results.append(("DDS1 → SW PZT → NW RX", snr1, dds1_ok))

# DDS2 channel working?
dds2_ok = snr2 >= PASS_THRESHOLD
results.append(("DDS2 → NE PZT → NW RX", snr2, dds2_ok))

# Both simultaneously?
both_ok = snr1_both >= PASS_THRESHOLD and snr2_both >= PASS_THRESHOLD
results.append(("Both simultaneous", min(snr1_both, snr2_both), both_ok))

# Swap confirms independent routing?
swap_ok = snr1_swap >= PASS_THRESHOLD and snr2_swap >= PASS_THRESHOLD
results.append(("Frequency swap", min(snr1_swap, snr2_swap), swap_ok))

all_pass = True
for label, snr_val, ok in results:
    status = "PASS" if ok else "FAIL"
    if not ok:
        all_pass = False
    print(f"  [{status}] {label:30s} SNR={snr_val:.1f}×")

print()
if all_pass:
    print(">>> ALL PASS — Dual-TX wiring verified! Ready for T5.2/T5.3/T5.5.")
else:
    print(">>> FAIL — Check wiring. See individual test results above.")
print()
