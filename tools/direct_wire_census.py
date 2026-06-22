#!/usr/bin/env python3
"""
Direct-Wire Census — Spectral Port Multiplexing Validation
==========================================================

All RX PZTs are wired directly (bypassing relay mux) to preamp → PicoScope chA.
The NCO drives each plate's TX independently via F1/F2/F3.

This script:
  1. Validates the signal path (noise floor, then single-tone check per TX)
  2. Sweeps each TX channel independently (30–150 kHz)
  3. Sweeps all TX channels simultaneously (validates no destructive interference)
  4. Detects all usable modes and checks for collisions
  5. Reports: total spectral budget, usable modes, kernel dimension

Hardware:
  TX: Pico NCO F1/F2/F3 → 3 plates (independent drive)
  RX: 7 PZTs wired direct to preamp → PicoScope Ch A (one summed port)

Usage:
  python tools/direct_wire_census.py
  python tools/direct_wire_census.py --step 200        # finer sweep
  python tools/direct_wire_census.py --start 20000     # wider range
  python tools/direct_wire_census.py --tx F1           # single TX only
"""

import ctypes as ct
import numpy as np
import serial
import time
import json
import argparse
from datetime import datetime
from pathlib import Path

# ─── Args ─────────────────────────────────────────────────────────
parser = argparse.ArgumentParser(description='Direct-wire spectral census')
parser.add_argument('--start', type=int, default=30000,
                    help='Start frequency Hz (default: 30000)')
parser.add_argument('--stop', type=int, default=150000,
                    help='Stop frequency Hz (default: 150000)')
parser.add_argument('--step', type=int, default=500,
                    help='Frequency step Hz (default: 500)')
parser.add_argument('--navg', type=int, default=8,
                    help='FFT captures averaged per measurement (default: 8)')
parser.add_argument('--settle', type=float, default=0.05,
                    help='Settle time after freq change in seconds (default: 0.05)')
parser.add_argument('--tx', type=str, default='F1,F2,F3,F4,F5',
                    help='TX channels to test (default: F1,F2,F3,F4,F5)')
parser.add_argument('--nco-port', type=str, default='/dev/cu.usbmodem113401',
                    help='NCO serial port')
parser.add_argument('--snr-threshold', type=float, default=3.0,
                    help='SNR threshold for mode detection (default: 3.0)')
parser.add_argument('--collision-bw', type=float, default=500.0,
                    help='Collision bandwidth Hz — modes closer than this are ambiguous (default: 500)')
parser.add_argument('--probe-points', type=int, default=24,
                    help='Connection-check probe points spread across the band (default: 24). '
                         'Higher = less chance of missing a narrow-mode channel between probes.')
parser.add_argument('--gate-snr', type=float, default=1.8,
                    help='Connection-check SNR threshold to call a channel alive (default: 1.8)')
parser.add_argument('--force', action='store_true',
                    help='Skip the connection-check gate and sweep ALL requested TX channels. '
                         'Use when a channel has narrow/high-Q modes the gate might miss.')
parser.add_argument('--keep-collisions', action='store_true',
                    help='Do NOT discard colliding modes. Tag each mode with collision status '
                         'and partners, and report the FULL mode set as the kernel. A collision '
                         'bin holds the interference SUM of two plates — that can be a usable, '
                         'repeatable feature for a learned readout, not garbage. Pair with '
                         '--repeat-passes to score each mode by repeatability instead.')
parser.add_argument('--repeat-passes', type=int, default=0,
                    help='If >0, re-measure every detected mode this many extra times (driving its '
                         'owning TX) to score per-mode repeatability (CV across passes). The '
                         'principled replacement for the attributability/collision filter: a '
                         'feature is good if it is REPEATABLE, regardless of whether it is '
                         'spectrally unique. Default 0 = off.')
args = parser.parse_args()

TX_CHANNELS = [ch.strip() for ch in args.tx.split(',')]
FREQS = list(range(args.start, args.stop + 1, args.step))
N_FREQS = len(FREQS)

# ─── Constants ────────────────────────────────────────────────────
PICO_LIB = '/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources/libps2000.dylib'

N_SAMPLES = 8064          # samples per capture
TIMEBASE = 7              # 1280 ns/sample → 781.25 kS/s
FS = 781250.0             # sample rate
NFFT = N_SAMPLES * 4      # zero-pad for interpolation
BIN_HZ = FS / NFFT       # frequency resolution per FFT bin
RNG = 6                   # ±1V range
RNG_MV = 1000.0           # mV full-scale for range 6

# ─── Output ───────────────────────────────────────────────────────
OUT_DIR = Path('data/results/direct_wire_census')
OUT_DIR.mkdir(parents=True, exist_ok=True)
TIMESTAMP = datetime.now().strftime('%Y%m%d_%H%M%S')

# ─── Header ───────────────────────────────────────────────────────
print("=" * 70)
print("  DIRECT-WIRE SPECTRAL CENSUS")
print("  7 RX PZTs → preamp → PicoScope Ch A (no relay mux)")
print("=" * 70)
print(f"  Range: {args.start/1000:.1f} – {args.stop/1000:.1f} kHz, step={args.step} Hz")
print(f"  Frequencies: {N_FREQS}")
print(f"  TX channels: {TX_CHANNELS}")
print(f"  Averaging: {args.navg} captures/point")
print(f"  SNR threshold: {args.snr_threshold}×")
print(f"  Collision BW: {args.collision_bw} Hz")
est_time = N_FREQS * (args.settle + args.navg * 0.012) * (len(TX_CHANNELS) + 1)
print(f"  Estimated time: {est_time:.0f}s ({est_time/60:.1f} min)")
print()

# ─── Hardware Init ────────────────────────────────────────────────
print("[0] Initializing hardware...")

# PicoScope
ps = ct.CDLL(PICO_LIB)
ps.ps2000_open_unit.restype = ct.c_int16
handle = ps.ps2000_open_unit()
if handle <= 0:
    print(f"  ERROR: PicoScope open failed (handle={handle})")
    raise SystemExit(1)
ps.ps2000_set_channel(handle, 0, 1, 0, RNG)   # Ch A: enabled, AC coupled, ±1V
ps.ps2000_set_channel(handle, 1, 0, 0, RNG)   # Ch B: off
ps.ps2000_set_trigger(handle, 5, 0, 0, 0, 0)  # no trigger, free-run
print(f"  PicoScope: handle={handle}, Ch A AC-coupled ±{RNG_MV}mV")

# NCO
nco_ser = serial.Serial(args.nco_port, 115200, timeout=2)
time.sleep(0.5)
nco_ser.reset_input_buffer()
print(f"  NCO: {args.nco_port}")

# Check NCO responds
nco_ser.write(b'STATUS\n')
time.sleep(0.1)
status = nco_ser.readline().decode(errors='replace').strip()
print(f"  NCO status: {status}")


def nco_cmd(cmd):
    """Send NCO command, return response."""
    nco_ser.reset_input_buffer()
    nco_ser.write(f'{cmd}\n'.encode())
    time.sleep(0.03)
    resp = ''
    if nco_ser.in_waiting:
        resp = nco_ser.read(nco_ser.in_waiting).decode(errors='replace').strip()
    return resp


def nco_off():
    """All channels off."""
    nco_cmd('Foff')
    time.sleep(0.02)


def nco_drive(channel, freq):
    """Drive one TX channel at given frequency."""
    nco_cmd(f'{channel}:{freq}')


def capture_spectrum(navg):
    """Capture and average magnitude spectrum on Ch A (direct-wire)."""
    buf = (ct.c_int16 * N_SAMPLES)()
    ov = ct.c_int16()
    mags = []
    for _ in range(navg):
        ticks = ct.c_int32()
        ps.ps2000_run_block(handle, N_SAMPLES, TIMEBASE, 1, ct.byref(ticks))
        for attempt in range(500):
            if ps.ps2000_ready(handle):
                break
            time.sleep(0.002)
        else:
            continue  # skip this capture if timeout
        ps.ps2000_get_values(handle, ct.byref(buf), None, None, None,
                             ct.byref(ov), N_SAMPLES)
        d = np.array(buf[:], dtype=np.float64) * (RNG_MV / 32767.0)
        d -= d.mean()
        w = np.hanning(N_SAMPLES)
        mags.append(np.abs(np.fft.rfft(d * w, n=NFFT)))
    if not mags:
        return np.zeros(NFFT // 2 + 1)
    return np.mean(mags, axis=0)


def peak_magnitude(spectrum, freq, search_bins=5):
    """Peak magnitude near target frequency."""
    bin_idx = int(round(freq / BIN_HZ))
    lo = max(0, bin_idx - search_bins)
    hi = min(len(spectrum), bin_idx + search_bins + 1)
    return float(spectrum[lo:hi].max())


def find_modes(freqs, magnitudes, noise_floor, snr_threshold, min_sep_hz=1500):
    """Detect modes from sweep data. Returns list of (freq, magnitude, snr)."""
    snr = magnitudes / max(noise_floor, 1e-10)
    modes = []

    for i in range(1, len(magnitudes) - 1):
        # Local peak
        if magnitudes[i] > magnitudes[i-1] and magnitudes[i] > magnitudes[i+1]:
            if snr[i] >= snr_threshold:
                # Check prominence (at least 2× local floor)
                left_min = min(magnitudes[max(0, i-5):i]) if i > 0 else magnitudes[i]
                right_min = min(magnitudes[i+1:min(len(magnitudes), i+6)]) if i < len(magnitudes)-1 else magnitudes[i]
                local_floor = (left_min + right_min) / 2
                if magnitudes[i] > local_floor * 1.5:
                    modes.append((freqs[i], magnitudes[i], float(snr[i])))

    # Remove modes too close together (keep strongest)
    if not modes:
        return modes
    modes.sort(key=lambda x: x[2], reverse=True)
    filtered = []
    for freq, mag, s in modes:
        if all(abs(freq - f) >= min_sep_hz for f, _, _ in filtered):
            filtered.append((freq, mag, s))
    filtered.sort(key=lambda x: x[0])
    return filtered


# ─── Step 1: Noise Floor ─────────────────────────────────────────
print("\n[1] Measuring noise floor (all TX off)...")
nco_off()
time.sleep(0.3)

noise_spectrum = capture_spectrum(args.navg * 2)  # extra averaging for noise
# Exclude DC and very low bins
noise_floor = float(np.median(noise_spectrum[20:]))
noise_peak = float(noise_spectrum[20:].max())
noise_mean = float(noise_spectrum[20:].mean())

print(f"  Noise floor (median): {noise_floor:.2f}")
print(f"  Noise peak: {noise_peak:.2f} ({noise_peak/noise_floor:.1f}× median)")
print(f"  Noise mean: {noise_mean:.2f}")

if noise_peak > noise_floor * 20:
    print(f"  ⚠️  High noise spikes detected — check for EMI pickup or loose wires")


# ─── Step 2: Connection Check (broadband probe per TX) ───────────
# NOTE: the old gate probed only 3 fixed frequencies (48/72/96 kHz). A channel
# whose modes are narrow and happen to sit BETWEEN those points was wrongly
# flagged dead (this false-negatived F3 on 2026-06-20: it actually has 16 modes,
# peak 6.2× @ 87.5 kHz). The gate now probes many points spread across the full
# configured band, and --force skips it entirely.
if args.force:
    print("\n[2] Connection check SKIPPED (--force) — sweeping all requested TX.")
    connection_ok = {ch: True for ch in TX_CHANNELS}
else:
    print(f"\n[2] Connection check — {args.probe_points} probes across "
          f"{args.start/1000:.0f}–{args.stop/1000:.0f} kHz per TX channel...")

    # Probe points spread evenly across the WHOLE band (inclusive of both ends).
    if args.probe_points < 2:
        test_freqs = [(args.start + args.stop) // 2]
    else:
        test_freqs = [int(round(args.start + i * (args.stop - args.start) / (args.probe_points - 1)))
                      for i in range(args.probe_points)]
    connection_ok = {}

    for ch in TX_CHANNELS:
        responses = []
        for tf in test_freqs:
            nco_off()
            time.sleep(0.02)
            nco_drive(ch, tf)
            time.sleep(args.settle * 2)  # extra settle for connection check
            sp = capture_spectrum(args.navg)
            snr = peak_magnitude(sp, tf) / noise_floor
            responses.append(snr)

        best_snr = max(responses)
        best_f = test_freqs[int(np.argmax(responses))]
        n_hits = sum(1 for s in responses if s > args.gate_snr)
        # Channel is alive if ANY probe point clears the gate threshold.
        ch_ok = best_snr > args.gate_snr
        connection_ok[ch] = ch_ok
        if ch_ok:
            print(f"  → {ch}: CONNECTED ✓  best {best_snr:.1f}× @ {best_f/1000:.1f} kHz "
                  f"({n_hits}/{len(test_freqs)} probes hit)")
        else:
            print(f"  → {ch}: NO SIGNAL ✗  best {best_snr:.1f}× @ {best_f/1000:.1f} kHz "
                  f"(below gate {args.gate_snr}× — re-run with --force to sweep anyway)")

    nco_off()

active_channels = [ch for ch in TX_CHANNELS if connection_ok.get(ch, False)]
dead_channels = [ch for ch in TX_CHANNELS if not connection_ok.get(ch, False)]

print(f"\n  Summary: {len(active_channels)} active TX: {active_channels}")
if dead_channels:
    print(f"  ⚠️  Gated-out TX: {dead_channels} — below gate at all probe points.")
    print(f"  If you believe one is wired, re-run with --force (narrow modes can hide between probes).")

if not active_channels:
    print("\n  ERROR: No TX channels responding. Check:")
    print("    - NCO powered and outputting?")
    print("    - 220Ω resistors in place?")
    print("    - PZT connections (TX side)?")
    print("    - Preamp powered?")
    print("    - Or re-run with --force to sweep regardless of the gate.")
    nco_ser.close()
    ps.ps2000_stop(handle)
    ps.ps2000_close_unit(ct.c_int16(handle))
    raise SystemExit(1)


# ─── Step 3: Full Sweep Per TX Channel ────────────────────────────
print(f"\n[3] Full sweep: {N_FREQS} frequencies × {len(active_channels)} TX channels...")

# response_per_tx[ch] = array of magnitudes at each frequency
response_per_tx = {}

for ch_idx, ch in enumerate(active_channels):
    print(f"\n  Sweeping {ch} ({ch_idx+1}/{len(active_channels)})...")
    magnitudes = np.zeros(N_FREQS)
    t0 = time.time()

    for i, freq in enumerate(FREQS):
        nco_off()
        time.sleep(0.01)
        nco_drive(ch, freq)
        time.sleep(args.settle)
        sp = capture_spectrum(args.navg)
        magnitudes[i] = peak_magnitude(sp, freq)

        if (i + 1) % 20 == 0 or (i + 1) == N_FREQS:
            elapsed = time.time() - t0
            eta = elapsed / (i + 1) * (N_FREQS - i - 1)
            current_snr = magnitudes[i] / noise_floor
            print(f"    {i+1}/{N_FREQS} — {freq/1000:.1f} kHz — "
                  f"SNR={current_snr:.1f}× — ETA {eta:.0f}s")

    response_per_tx[ch] = magnitudes
    nco_off()

    # Quick mode count for this channel
    modes_ch = find_modes(FREQS, magnitudes, noise_floor, args.snr_threshold)
    print(f"  → {ch}: {len(modes_ch)} modes detected (SNR > {args.snr_threshold}×)")


# ─── Step 4: Combined Sweep (all TX simultaneously) ──────────────
print(f"\n[4] Combined sweep: all active TX driving simultaneously...")

combined_magnitudes = np.zeros(N_FREQS)
t0 = time.time()

for i, freq in enumerate(FREQS):
    nco_off()
    time.sleep(0.01)
    # Drive ALL active TX at the same frequency simultaneously
    for ch in active_channels:
        nco_drive(ch, freq)
    time.sleep(args.settle)
    sp = capture_spectrum(args.navg)
    combined_magnitudes[i] = peak_magnitude(sp, freq)

    if (i + 1) % 20 == 0 or (i + 1) == N_FREQS:
        elapsed = time.time() - t0
        eta = elapsed / (i + 1) * (N_FREQS - i - 1)
        current_snr = combined_magnitudes[i] / noise_floor
        print(f"    {i+1}/{N_FREQS} — {freq/1000:.1f} kHz — "
              f"SNR={current_snr:.1f}× — ETA {eta:.0f}s")

nco_off()


# ─── Step 5: Mode Detection & Collision Analysis ─────────────────
print(f"\n[5] Mode detection and collision analysis...")

# Detect modes per TX channel
modes_per_tx = {}
all_modes = []

for ch in active_channels:
    modes_ch = find_modes(FREQS, response_per_tx[ch], noise_floor, args.snr_threshold)
    modes_per_tx[ch] = modes_ch
    for freq, mag, snr in modes_ch:
        all_modes.append({'freq': freq, 'mag': mag, 'snr': snr, 'tx': ch})
    print(f"  {ch}: {len(modes_ch)} modes")

# Detect modes on combined (all TX)
modes_combined = find_modes(FREQS, combined_magnitudes, noise_floor, args.snr_threshold)
print(f"  Combined (all TX): {len(modes_combined)} modes")

# Sort all modes by frequency
all_modes.sort(key=lambda m: m['freq'])

# Check for collisions (modes from DIFFERENT TX channels within collision_bw)
collisions = []
for i in range(len(all_modes)):
    for j in range(i + 1, len(all_modes)):
        if all_modes[j]['freq'] - all_modes[i]['freq'] > args.collision_bw:
            break
        if all_modes[i]['tx'] != all_modes[j]['tx']:
            collisions.append((all_modes[i], all_modes[j]))

# Tag colliding modes (do NOT discard yet — that is a policy decision below)
collision_freqs = set()
for m1, m2 in collisions:
    collision_freqs.add(m1['freq'])
    collision_freqs.add(m2['freq'])
for m in all_modes:
    m['collision'] = m['freq'] in collision_freqs

# ─── Optional: per-mode repeatability scoring ────────────────────
# The principled replacement for the collision filter: a feature is useful
# if it is REPEATABLE, regardless of whether another channel shares its bin.
# We re-measure each mode's amplitude --repeat-passes extra times (driving its
# owning TX) and report CV = std/mean across passes. repeatability = 1/(1+CV).
if args.repeat_passes > 0:
    print(f"\n[5b] Repeatability scoring ({args.repeat_passes} extra passes per mode)...")
    n_modes = len(all_modes)
    amp_passes = {id(m): [] for m in all_modes}
    for p in range(args.repeat_passes):
        for m in all_modes:
            nco_off()
            time.sleep(0.005)
            nco_drive(m['tx'], m['freq'])
            time.sleep(args.settle)
            sp = capture_spectrum(args.navg)
            amp_passes[id(m)].append(peak_magnitude(sp, m['freq']))
        print(f"    pass {p+1}/{args.repeat_passes} done")
    nco_off()
    for m in all_modes:
        a = np.array(amp_passes[id(m)], dtype=float)
        mean = float(a.mean()) if len(a) else 0.0
        cv = float(a.std() / mean) if mean > 1e-9 else 9.9
        m['repeat_cv'] = round(cv, 3)
        m['repeatability'] = round(1.0 / (1.0 + cv), 3)
else:
    for m in all_modes:
        m['repeat_cv'] = None
        m['repeatability'] = None

# ─── Usability policy ────────────────────────────────────────────
# Default: drop collisions (spectral-attribution kernel — one bin = one plate).
# --keep-collisions: keep everything (interference-sum kernel — let the learned
#   readout decide via weights; collision bins carry the coherent sum of plates).
# If repeatability was scored, rank the kept set by repeatability × SNR.
if args.keep_collisions:
    usable_modes = list(all_modes)
    policy = 'keep-all (interference-sum kernel)'
else:
    usable_modes = [m for m in all_modes if not m['collision']]
    policy = 'drop-collisions (spectral-attribution kernel)'

if args.repeat_passes > 0:
    usable_modes.sort(key=lambda m: -(m['repeatability'] or 0) * m['snr'])

n_total = len(all_modes)
n_collisions = len(collision_freqs)
n_usable = len(usable_modes)

# Combined check: compare individual sum vs combined response
# If combined response at a mode is much weaker than individual → destructive interference
print(f"\n  --- Interference Check ---")
interference_issues = 0
for m in usable_modes:
    freq = m['freq']
    freq_idx = min(range(N_FREQS), key=lambda i: abs(FREQS[i] - freq))

    # Individual response (the TX that owns this mode)
    individual_mag = response_per_tx[m['tx']][freq_idx]
    combined_mag = combined_magnitudes[freq_idx]

    ratio_db = 20 * np.log10(combined_mag / max(individual_mag, 1e-10))
    if ratio_db < -6:  # >6 dB loss when combined
        interference_issues += 1
        if interference_issues <= 5:
            print(f"    ⚠️  {freq/1000:.1f} kHz ({m['tx']}): "
                  f"individual={individual_mag:.1f}, combined={combined_mag:.1f} "
                  f"({ratio_db:.1f} dB loss)")

if interference_issues == 0:
    print("    All modes: combined ≥ individual (no destructive interference) ✓")
elif interference_issues <= 5:
    print(f"    {interference_issues} modes show >6 dB loss in combined drive")
else:
    print(f"    ⚠️  {interference_issues} modes show >6 dB loss — "
          f"possible intermodulation or phase cancellation")


# ─── Step 6: Report ──────────────────────────────────────────────
print("\n" + "=" * 70)
print("  CENSUS RESULTS")
print("=" * 70)

print(f"\n  Signal path: 7 RX PZTs → preamp → PicoScope Ch A (direct-wire)")
print(f"  Active TX channels: {active_channels}")
print(f"  Bandwidth: {args.start/1000:.0f} – {args.stop/1000:.0f} kHz")
print(f"  Noise floor: {noise_floor:.2f} (median FFT bin)")

print(f"\n  Modes per TX channel:")
for ch in active_channels:
    modes_ch = modes_per_tx[ch]
    if modes_ch:
        freqs_str = ', '.join(f"{f/1000:.1f}" for f, _, _ in modes_ch[:10])
        if len(modes_ch) > 10:
            freqs_str += f" ... (+{len(modes_ch)-10} more)"
        print(f"    {ch}: {len(modes_ch)} modes — {freqs_str} kHz")
    else:
        print(f"    {ch}: 0 modes ✗")

print(f"\n  Collision analysis:")
print(f"    Total modes (all TX): {n_total}")
print(f"    Collisions (within {args.collision_bw} Hz): {n_collisions} modes affected")
print(f"    Usability policy: {policy}")
print(f"    Kernel size under policy: {n_usable}")
if not args.keep_collisions:
    print(f"    Drop-collision efficiency: {n_usable/max(n_total,1)*100:.0f}%")
    print(f"    (collisions discarded: {n_total - n_usable}. Re-run with "
          f"--keep-collisions --repeat-passes 3 to score them instead of discarding.)")
else:
    print(f"    Keeping ALL {n_total} modes — learned readout weights decide value.")

if args.repeat_passes > 0:
    rep_vals = [m['repeatability'] for m in all_modes if m['repeatability'] is not None]
    coll_rep = [m['repeatability'] for m in all_modes if m['collision'] and m['repeatability'] is not None]
    noncoll_rep = [m['repeatability'] for m in all_modes if not m['collision'] and m['repeatability'] is not None]
    print(f"\n  Repeatability (1/(1+CV), higher=more stable):")
    print(f"    All modes:        mean {np.mean(rep_vals):.2f}")
    if coll_rep:
        print(f"    Collision modes:  mean {np.mean(coll_rep):.2f}  (n={len(coll_rep)})")
    if noncoll_rep:
        print(f"    Non-collision:    mean {np.mean(noncoll_rep):.2f}  (n={len(noncoll_rep)})")
    print(f"    → If collision modes are as repeatable as non-collision, the "
          f"'collision' label is not a quality signal — keep them.")

print(f"\n  ┌─────────────────────────────────────────────┐")
print(f"  │  KERNEL DIMENSION (multi-tone readout):  {n_usable:>3}  │")
print(f"  │  (one FFT capture, no relay switching)       │")
print(f"  └─────────────────────────────────────────────┘")

if n_usable >= 32:
    print(f"\n  ✓ DOOM-ready: kernel dim {n_usable} ≥ 32 (need 8 for Pong, 32 for DOOM)")
elif n_usable >= 8:
    print(f"\n  ✓ Pong-ready: kernel dim {n_usable} ≥ 8 (sufficient for Pong)")
    print(f"    DOOM needs ≥32 — add more plates or improve SNR")
else:
    print(f"\n  ✗ Insufficient: kernel dim {n_usable} < 8")
    print(f"    Check: wiring, preamp gain, EMI shielding, PZT bonds")

# Pong feasibility
if n_usable >= 8:
    print(f"\n  Pong at 66 fps: FEASIBLE")
    print(f"    - Drive: multi-tone burst at {n_usable} frequencies")
    print(f"    - Capture: one FFT (10 ms)")
    print(f"    - Extract: {n_usable} amplitudes")
    print(f"    - Decision: w·y (one dot product, {n_usable} floats)")

# Print full mode table
print(f"\n  Full mode table ({n_total} modes, policy: {policy}):")
hdr_rep = f" | {'Repeat':>6}" if args.repeat_passes > 0 else ""
print(f"  {'Freq (kHz)':>10} | {'TX':>4} | {'Mag':>8} | {'SNR':>6}{hdr_rep} | Status")
print(f"  {'-'*10}-+-{'-'*4}-+-{'-'*8}-+-{'-'*6}-+{'-'*9 if args.repeat_passes>0 else ''}-------")
table_modes = sorted(all_modes, key=lambda m: m['freq'])
for m in table_modes:
    if args.keep_collisions:
        status = "✓ kept" if not m['collision'] else "≈ collision (kept)"
    else:
        status = "✓ usable" if not m['collision'] else "✗ collision"
    rep_str = f" | {m['repeatability']:>6.2f}" if args.repeat_passes > 0 else ""
    print(f"  {m['freq']/1000:>10.1f} | {m['tx']:>4} | {m['mag']:>8.1f} | "
          f"{m['snr']:>6.1f}{rep_str} | {status}")


# ─── Step 7: Save Results ─────────────────────────────────────────
print(f"\n[7] Saving results...")

results = {
    'timestamp': TIMESTAMP,
    'config': {
        'freq_start': args.start,
        'freq_stop': args.stop,
        'freq_step': args.step,
        'n_freqs': N_FREQS,
        'navg': args.navg,
        'settle_s': args.settle,
        'snr_threshold': args.snr_threshold,
        'collision_bw': args.collision_bw,
        'gate_snr': args.gate_snr,
        'probe_points': args.probe_points,
        'force': args.force,
        'keep_collisions': args.keep_collisions,
        'repeat_passes': args.repeat_passes,
        'usability_policy': policy,
        'tx_requested': TX_CHANNELS,
        'tx_channels': active_channels,
        'rx_config': '7 PZTs direct-wire to preamp → PicoScope Ch A',
    },
    'noise': {
        'floor_median': noise_floor,
        'peak': noise_peak,
        'mean': noise_mean,
    },
    'modes_per_tx': {
        ch: [{'freq_hz': f, 'magnitude': m, 'snr': s}
             for f, m, s in modes_per_tx[ch]]
        for ch in active_channels
    },
    'modes_combined': [{'freq_hz': f, 'magnitude': m, 'snr': s}
                       for f, m, s in modes_combined],
    'all_modes': all_modes,
    'usable_modes': [{'freq_hz': m['freq'], 'tx': m['tx'],
                      'magnitude': m['mag'], 'snr': m['snr'],
                      'collision': m['collision'],
                      'repeatability': m['repeatability']}
                     for m in usable_modes],
    'summary': {
        'total_modes': n_total,
        'collision_count': n_collisions,
        'usable_modes': n_usable,
        'efficiency_pct': round(n_usable / max(n_total, 1) * 100, 1),
        'kernel_dimension': n_usable,
        'keep_collisions': args.keep_collisions,
        'pong_feasible': n_usable >= 8,
        'doom_feasible': n_usable >= 32,
        'interference_issues': interference_issues,
    },
}

json_path = OUT_DIR / f'direct_wire_census_{TIMESTAMP}.json'
with open(json_path, 'w') as f:
    json.dump(results, f, indent=2)
print(f"  JSON: {json_path}")

# Save raw sweep data as npz
npz_path = OUT_DIR / f'direct_wire_census_{TIMESTAMP}.npz'
sweep_data = {'freqs': np.array(FREQS), 'noise_spectrum': noise_spectrum,
              'combined': combined_magnitudes}
for ch in active_channels:
    sweep_data[f'sweep_{ch}'] = response_per_tx[ch]
np.savez(npz_path, **sweep_data)
print(f"  NPZ: {npz_path}")


# ─── Cleanup ──────────────────────────────────────────────────────
nco_off()
nco_ser.close()
ps.ps2000_stop(handle)
ps.ps2000_close_unit(ct.c_int16(handle))

print(f"\n{'='*70}")
print(f"  Done. Kernel dimension = {n_usable} modes.")
if n_usable >= 8:
    print(f"  Next: run tools/pong_train.py to collect training data.")
print(f"{'='*70}")
