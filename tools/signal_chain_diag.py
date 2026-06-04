#!/usr/bin/env python3
"""
Signal Chain Stage-by-Stage Diagnostic — Post Ground Fix

Run this AFTER restoring probe ground continuity.
Tests each stage independently to isolate any remaining faults
in the dual-TX rewire (May 29, 2026).

Stages tested:
  1. Noise floor (everything off)
  2. DDS1 output at Board D Ch B input (pre-amp)
  3. DDS2 output at Board D Ch A input (pre-amp)
  4. Board D Ch B output (post-amp, pre-PZT)
  5. Board D Ch A output (post-amp, pre-PZT)
  6. Full chain: DDS1 → Board D Ch B → SW PZT → plate → NW RX → Board A → scope
  7. Full chain: DDS2 → Board D Ch A → NE PZT → plate → NW RX → Board A → scope
  8. Both channels simultaneous

INSTRUCTIONS:
  Move the probe to the indicated test point for each stage.
  Press Enter when the probe is in position.
  The script measures and prints results before moving to the next stage.
"""

import ctypes as ct
import numpy as np
import serial
import time
import os
import sys

os.environ['DYLD_LIBRARY_PATH'] = '/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources'
ps = ct.CDLL('/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources/libps2000.dylib')

# --- Configuration ---
F1 = 35840   # DDS1 frequency (Hz)
F2 = 97011   # DDS2 frequency (Hz)
NSAMPLES = 8064
TIMEBASE = 7  # 781250 Hz sample rate
SR = 781250.0
BIN_HZ = SR / NSAMPLES
N_AVG = 20   # more averaging for clean measurements
ADC_TO_MV_5V = 5000.0 / 32767.0   # ±5V range
ADC_TO_MV_2V = 2000.0 / 32767.0   # ±2V range

# --- Hardware init ---
print("Opening PicoScope...")
ps.ps2000_open_unit.restype = ct.c_int16
h = ps.ps2000_open_unit()
if h <= 0:
    print(f"ERROR: PicoScope handle = {h}. USB reset needed.")
    sys.exit(1)
print(f"  Handle: {h} — OK")

# Start with ±2V for maximum sensitivity on DDS-level signals
RANGE = 6  # ±2V
ADC_TO_MV = ADC_TO_MV_2V
ps.ps2000_set_channel(h, 0, 1, 0, RANGE)  # Ch A: AC coupled
ps.ps2000_set_channel(h, 1, 0, 0, 7)      # Ch B: off

print("Opening DDS serial...")
dds = serial.Serial('/dev/cu.usbserial-1120', 115200, timeout=2)
time.sleep(2.5)
dds.reset_input_buffer()
# Verify DDS responds
dds.write(b'Foff\n')
time.sleep(0.2)
resp = dds.read(dds.in_waiting).decode(errors='replace').strip()
print(f"  DDS response: '{resp}'")

buf = (ct.c_int16 * NSAMPLES)()
ov = ct.c_int16()


def capture_avg(n=N_AVG):
    """Capture n blocks, return (time_domain_avg, spectrum_avg)."""
    spectra = []
    raws = []
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
        raws.append(raw)
        raw_ac = raw - np.mean(raw)
        sp = np.abs(np.fft.rfft(raw_ac * np.hanning(NSAMPLES)))
        spectra.append(sp)
        time.sleep(0.005)
    return np.mean(raws, axis=0), np.mean(spectra, axis=0)


def analyze(raw, spectrum, label, target_freqs=None):
    """Print comprehensive signal analysis."""
    rms_mv = np.std(raw) * ADC_TO_MV
    pp_mv = (np.max(raw) - np.min(raw)) * ADC_TO_MV
    dc_mv = np.mean(raw) * ADC_TO_MV

    print(f"\n  {'─'*50}")
    print(f"  {label}")
    print(f"  {'─'*50}")
    print(f"  DC offset:  {dc_mv:.1f} mV")
    print(f"  RMS (AC):   {rms_mv:.2f} mV")
    print(f"  Pk-Pk:      {pp_mv:.1f} mV")

    if target_freqs:
        # Noise floor (exclude target regions)
        mask = np.ones(len(spectrum), dtype=bool)
        for f in target_freqs:
            b = int(round(f / BIN_HZ))
            mask[max(0, b-10):b+11] = False
        mask[:5] = False
        nf = float(np.median(spectrum[mask]))

        for f in target_freqs:
            b = int(round(f / BIN_HZ))
            pk = float(np.max(spectrum[max(0, b-5):b+6]))
            snr = pk / nf if nf > 0 else 0
            status = "✓ GOOD" if snr > 3 else ("~ MARGINAL" if snr > 1.5 else "✗ ABSENT")
            print(f"  @ {f:>6} Hz:  peak={pk:.0f}  noise={nf:.0f}  SNR={snr:.1f}×  {status}")

    return rms_mv, pp_mv


def set_range_for_signal(expected_pp_mv):
    """Switch PicoScope range based on expected signal level."""
    global RANGE, ADC_TO_MV
    if expected_pp_mv > 3500:
        new_range = 8  # ±10V
        ADC_TO_MV = 10000.0 / 32767.0
    elif expected_pp_mv > 1500:
        new_range = 7  # ±5V
        ADC_TO_MV = ADC_TO_MV_5V
    elif expected_pp_mv > 500:
        new_range = 6  # ±2V
        ADC_TO_MV = ADC_TO_MV_2V
    else:
        new_range = 5  # ±1V
        ADC_TO_MV = 1000.0 / 32767.0
    if new_range != RANGE:
        RANGE = new_range
        ps.ps2000_set_channel(h, 0, 1, 0, RANGE)
        time.sleep(0.1)


def wait_for_probe(instruction):
    """Prompt user to move probe and wait for Enter."""
    print(f"\n{'='*60}")
    print(f"  PROBE POSITION: {instruction}")
    print(f"{'='*60}")
    input("  Press Enter when probe is in position...")


# ============================================================
# STAGE 0: Ground continuity check
# ============================================================
print("\n" + "█"*60)
print("  STAGE 0: GROUND REFERENCE CHECK")
print("█"*60)
print("""
  Before proceeding, confirm:
  1. Probe ground clip has continuity to BNC shell (multimeter beep)
  2. BNC shell is connected to Board S purple GND rail
  3. If using a jumper bypass: BNC shell → Board S GND (short wire)
""")
input("  Press Enter to confirm ground is connected and start diagnostics...")

# ============================================================
# STAGE 1: Noise floor
# ============================================================
print("\n" + "█"*60)
print("  STAGE 1: NOISE FLOOR (all DDS off)")
print("█"*60)

wait_for_probe("Board D Ch B INPUT (col 13, +IN B pin)")

dds.write(b'Foff\n')
time.sleep(0.3)
dds.reset_input_buffer()

set_range_for_signal(200)  # expect small noise
raw, sp = capture_avg()
rms_noise, pp_noise = analyze(raw, sp, "NOISE FLOOR (DDS off)", [F1, F2])

# ============================================================
# STAGE 2: DDS1 output (pre Board D)
# ============================================================
print("\n" + "█"*60)
print("  STAGE 2: DDS1 OUTPUT (before Board D)")
print("█"*60)

wait_for_probe("DDS1 OUT wire / Board D Ch B input coupling cap (before 100nF)")

set_range_for_signal(600)  # DDS output ~600 mV pp
dds.write(f'F1:{F1}\n'.encode())
time.sleep(0.5)
dds.reset_input_buffer()

raw, sp = capture_avg()
rms_dds1, pp_dds1 = analyze(raw, sp, f"DDS1 OUTPUT @ {F1} Hz", [F1])

dds.write(b'Foff\n')
time.sleep(0.2)
dds.reset_input_buffer()

# Quick DDS2 check at same point if they share a board
print("\n  Also checking DDS2 at same probe point...")
dds.write(f'F2:{F2}\n'.encode())
time.sleep(0.5)
dds.reset_input_buffer()
raw, sp = capture_avg()
analyze(raw, sp, f"DDS2 OUTPUT @ {F2} Hz (expect ~0 here if separate routing)", [F2])

dds.write(b'Foff\n')
time.sleep(0.2)
dds.reset_input_buffer()

# ============================================================
# STAGE 3: Board D Ch B output (post-amp)
# ============================================================
print("\n" + "█"*60)
print("  STAGE 3: BOARD D CHANNEL B OUTPUT (post-amp, before 47Ω)")
print("█"*60)

wait_for_probe("Board D Ch B output (pin 7 / col 11, or after 47Ω at col 20)")

set_range_for_signal(2500)  # expect ~2.2 Vpp (600mV × 3.69)
dds.write(f'F1:{F1}\n'.encode())
time.sleep(0.5)
dds.reset_input_buffer()

raw, sp = capture_avg()
rms_bd_b, pp_bd_b = analyze(raw, sp, f"BOARD D Ch B OUTPUT @ {F1} Hz", [F1])

# Calculate gain
if pp_dds1 > 10:
    gain_b = pp_bd_b / pp_dds1
    expected_gain = 3.69
    gain_ok = abs(gain_b - expected_gain) / expected_gain < 0.3
    status = "✓ CORRECT" if gain_ok else "✗ WRONG"
    print(f"  GAIN: {gain_b:.2f}× (expected {expected_gain:.2f}×) {status}")
else:
    print(f"  GAIN: cannot calculate (DDS1 input was too small: {pp_dds1:.1f} mV)")

dds.write(b'Foff\n')
time.sleep(0.2)
dds.reset_input_buffer()

# ============================================================
# STAGE 4: DDS2 → Board D Ch A output
# ============================================================
print("\n" + "█"*60)
print("  STAGE 4: BOARD D CHANNEL A OUTPUT (DDS2 path)")
print("█"*60)

wait_for_probe("Board D Ch A output (pin 1 output / after 47Ω to NE PZT)")

set_range_for_signal(2500)
dds.write(f'F2:{F2}\n'.encode())
time.sleep(0.5)
dds.reset_input_buffer()

raw, sp = capture_avg()
rms_bd_a, pp_bd_a = analyze(raw, sp, f"BOARD D Ch A OUTPUT @ {F2} Hz", [F2])

dds.write(b'Foff\n')
time.sleep(0.2)
dds.reset_input_buffer()

# ============================================================
# STAGE 5: Full chain — DDS1 → plate → NW RX
# ============================================================
print("\n" + "█"*60)
print("  STAGE 5: FULL CHAIN — DDS1 → SW PZT → plate → NW RX")
print("█"*60)

wait_for_probe("Normal position: Board A output → PicoScope Ch A BNC (AC coupled, ±5V)")

set_range_for_signal(500)  # RX signal after Board A ×11
# Switch to ±5V for full chain (Board A output can be larger)
RANGE = 7
ADC_TO_MV = ADC_TO_MV_5V
ps.ps2000_set_channel(h, 0, 1, 0, RANGE)
time.sleep(0.1)

# Need relay mux for this
print("  Opening relay mux...")
try:
    mux = serial.Serial('/dev/cu.usbserial-11310', 9600, timeout=2, dsrdtr=False, rtscts=False)
    mux.dtr = False
    time.sleep(0.5)
    mux.reset_input_buffer()
    for _ in range(4):
        mux.write(b'7\r\n')
        time.sleep(0.5)
        resp = mux.read(mux.in_waiting).decode(errors='replace').strip()
        if 'OK:7' in resp:
            break
        time.sleep(0.8)
    print(f"  Relay 7 (NW RX): {resp}")
    mux_ok = True
except Exception as e:
    print(f"  WARNING: relay mux failed ({e}). Testing without mux.")
    mux_ok = False

# DDS1 solo
dds.write(f'F1:{F1}\n'.encode())
time.sleep(0.5)
dds.reset_input_buffer()

raw, sp = capture_avg()
analyze(raw, sp, f"FULL CHAIN: DDS1@{F1} → SW PZT → NW RX", [F1, F2])

dds.write(b'Foff\n')
time.sleep(0.2)
dds.reset_input_buffer()

# ============================================================
# STAGE 6: Full chain — DDS2 → plate → NW RX
# ============================================================
print("\n" + "█"*60)
print("  STAGE 6: FULL CHAIN — DDS2 → NE PZT → plate → NW RX")
print("█"*60)

dds.write(f'F2:{F2}\n'.encode())
time.sleep(0.5)
dds.reset_input_buffer()

raw, sp = capture_avg()
analyze(raw, sp, f"FULL CHAIN: DDS2@{F2} → NE PZT → NW RX", [F1, F2])

dds.write(b'Foff\n')
time.sleep(0.2)
dds.reset_input_buffer()

# ============================================================
# STAGE 7: Both DDS simultaneous
# ============================================================
print("\n" + "█"*60)
print("  STAGE 7: DUAL-TX SIMULTANEOUS")
print("█"*60)

dds.write(f'F1:{F1}\n'.encode())
time.sleep(0.1)
dds.reset_input_buffer()
dds.write(f'F2:{F2}\n'.encode())
time.sleep(0.5)
dds.reset_input_buffer()

raw, sp = capture_avg()
analyze(raw, sp, f"BOTH: DDS1@{F1} + DDS2@{F2} → NW RX", [F1, F2])

# ============================================================
# SUMMARY
# ============================================================
print("\n" + "█"*60)
print("  DIAGNOSTIC SUMMARY")
print("█"*60)

print(f"""
  Signal levels measured:
  ─────────────────────────────────────────────────
  Noise floor (DDS off):        {pp_noise:.0f} mV pp
  DDS1 raw output:              {pp_dds1:.0f} mV pp  (expect 300-600)
  Board D Ch B output:          {pp_bd_b:.0f} mV pp  (expect ~2200)
  Board D Ch A output:          {pp_bd_a:.0f} mV pp  (expect ~2200)
  ─────────────────────────────────────────────────
""")

# Diagnosis
issues = []
if pp_dds1 < 100:
    issues.append("DDS1 output absent — check DDS1 AGND, DDS1 OUT wire, Arduino power")
if pp_bd_b < 500 and pp_dds1 > 100:
    issues.append("Board D Ch B not amplifying — check V+/V- power, Rf/Rg connections, input coupling cap")
if pp_bd_a < 500:
    issues.append("Board D Ch A not amplifying — check new Ch A wiring (pins 1,2,3)")
if pp_dds1 < 50 and pp_noise > 30:
    issues.append("PROBE GROUND STILL OPEN? Noise ≈ DDS signal suggests floating measurement")

if issues:
    print("  ISSUES DETECTED:")
    for i, issue in enumerate(issues, 1):
        print(f"    {i}. {issue}")
else:
    print("  ✓ All stages appear functional!")
    print("  → Run tools/dual_tx_diag.py for full dual-TX validation")

# Cleanup
dds.write(b'Foff\n')
ps.ps2000_stop(h)
ps.ps2000_close_unit(ct.c_int16(h))
dds.close()
if mux_ok:
    mux.close()
print("\nDone.")
