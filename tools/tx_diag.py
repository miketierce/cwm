#!/usr/bin/env python3
"""
TX Channel Diagnostic — is a drive channel actually coupling to its plate?
==========================================================================

Why this exists:
  direct_wire_census.py decides a channel is "dead" from a 3-point connection
  check (48/72/96 kHz, SNR>2) and only ever sweeps 30-150 kHz. That gate can
  call a channel dead when it actually has modes *between* those three probe
  points or *above* 150 kHz. This tool removes that ambiguity:

    - sweeps EACH channel across an extended range (default 30-350 kHz)
    - low detection threshold so weak coupling still shows
    - reports max SNR, the frequency where it occurs, and how many points
      cleared threshold — per channel, side by side
    - always include a known-good control channel so "dead" is judged
      against a working channel measured in the same run / same noise floor

Verdict logic (per channel):
    SILENT  : max SNR < 1.5  everywhere  -> no acoustic coupling at all
              (open wire / dead PZT / unbonded PZT / missing 220R)
    WEAK    : 1.5 <= max SNR < 3.0        -> couples but barely
    OK      : max SNR >= 3.0              -> real resonances present

Usage:
  python3 tools/tx_diag.py                       # all 5 channels, 30-350 kHz
  python3 tools/tx_diag.py --tx F3,F5            # suspect F3 vs control F5
  python3 tools/tx_diag.py --tx F3 --stop 350000 --step 250 --navg 12
"""

import ctypes as ct
import numpy as np
import time
import argparse
import json
from datetime import datetime
from pathlib import Path

parser = argparse.ArgumentParser(description='TX channel acoustic-coupling diagnostic')
parser.add_argument('--tx', type=str, default='F1,F2,F3,F4,F5',
                    help='Channels to test (default: all five)')
parser.add_argument('--start', type=int, default=30000)
parser.add_argument('--stop', type=int, default=350000,
                    help='Extended ceiling — small plates resonate >150 kHz (default 350000)')
parser.add_argument('--step', type=int, default=500)
parser.add_argument('--navg', type=int, default=8)
parser.add_argument('--settle', type=float, default=0.05)
parser.add_argument('--nco-port', type=str, default='/dev/cu.usbmodem113401')
parser.add_argument('--silent-snr', type=float, default=1.5)
parser.add_argument('--ok-snr', type=float, default=3.0)
args = parser.parse_args()

CHANNELS = [c.strip() for c in args.tx.split(',')]
FREQS = list(range(args.start, args.stop + 1, args.step))

PICO_LIB = '/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources/libps2000.dylib'
N_SAMPLES = 8064
TIMEBASE = 7            # 781.25 kS/s, Nyquist 390.6 kHz
FS = 781250.0
NFFT = N_SAMPLES * 4
BIN_HZ = FS / NFFT
RNG = 6
RNG_MV = 1000.0

if args.stop > 380000:
    raise SystemExit(f"--stop {args.stop} exceeds Nyquist (390.6 kHz at timebase {TIMEBASE}).")

import serial

print("=" * 70)
print("  TX CHANNEL DIAGNOSTIC — acoustic coupling per drive channel")
print(f"  Range: {args.start/1000:.0f}-{args.stop/1000:.0f} kHz, step {args.step} Hz "
      f"({len(FREQS)} pts), navg {args.navg}")
print(f"  Channels: {CHANNELS}")
print("=" * 70)

ps = ct.CDLL(PICO_LIB)
ps.ps2000_open_unit.restype = ct.c_int16
handle = ps.ps2000_open_unit()
if handle <= 0:
    raise SystemExit(f"  ERROR: PicoScope open failed (handle={handle})")
ps.ps2000_set_channel(handle, 0, 1, 0, RNG)   # Ch A on, AC, ±1V
ps.ps2000_set_channel(handle, 1, 0, 0, RNG)   # Ch B off
ps.ps2000_set_trigger(handle, 5, 0, 0, 0, 0)  # free-run

nco = serial.Serial(args.nco_port, 115200, timeout=2)
time.sleep(0.5)
nco.reset_input_buffer()
nco.write(b'STATUS\n')
time.sleep(0.1)
print(f"  NCO: {nco.readline().decode(errors='replace').strip()}")


def nco_cmd(cmd):
    nco.reset_input_buffer()
    nco.write(f'{cmd}\n'.encode())
    time.sleep(0.03)


def nco_off():
    nco_cmd('Foff')
    time.sleep(0.02)


def capture(navg):
    buf = (ct.c_int16 * N_SAMPLES)()
    ov = ct.c_int16()
    mags = []
    for _ in range(navg):
        ticks = ct.c_int32()
        ps.ps2000_run_block(handle, N_SAMPLES, TIMEBASE, 1, ct.byref(ticks))
        for _ in range(500):
            if ps.ps2000_ready(handle):
                break
            time.sleep(0.002)
        else:
            continue
        ps.ps2000_get_values(handle, ct.byref(buf), None, None, None,
                             ct.byref(ov), N_SAMPLES)
        d = np.array(buf[:], dtype=np.float64) * (RNG_MV / 32767.0)
        d -= d.mean()
        mags.append(np.abs(np.fft.rfft(d * np.hanning(N_SAMPLES), n=NFFT)))
    return np.mean(mags, axis=0) if mags else np.zeros(NFFT // 2 + 1)


def peak_at(spectrum, freq, search=5):
    b = int(round(freq / BIN_HZ))
    lo = max(0, b - search)
    hi = min(len(spectrum), b + search + 1)
    return float(spectrum[lo:hi].max())


# Noise floor: everything off
print("\n[1] Noise floor (all TX off)...")
nco_off()
time.sleep(0.1)
noise_sp = capture(args.navg)
noise_floor = float(np.median(noise_sp))
print(f"  Noise floor (median bin): {noise_floor:.1f}")

results = {}
for ci, ch in enumerate(CHANNELS):
    print(f"\n[2.{ci+1}] Sweeping {ch} ({ci+1}/{len(CHANNELS)})...")
    snrs = np.zeros(len(FREQS))
    t0 = time.time()
    for i, f in enumerate(FREQS):
        nco_off()
        time.sleep(0.008)
        nco_cmd(f'{ch}:{f}')
        time.sleep(args.settle)
        sp = capture(args.navg)
        snrs[i] = peak_at(sp, f) / noise_floor
        if (i + 1) % 40 == 0 or (i + 1) == len(FREQS):
            eta = (time.time() - t0) / (i + 1) * (len(FREQS) - i - 1)
            print(f"    {i+1}/{len(FREQS)} — {f/1000:.0f} kHz — "
                  f"SNR {snrs[i]:.1f}× — running max {snrs[:i+1].max():.1f}× — ETA {eta:.0f}s")
    nco_off()

    imax = int(np.argmax(snrs))
    max_snr = float(snrs[imax])
    f_at_max = FREQS[imax]
    n_ok = int(np.sum(snrs >= args.ok_snr))
    n_weak = int(np.sum((snrs >= args.silent_snr) & (snrs < args.ok_snr)))
    # how many of the OK hits are above the old 150 kHz census ceiling
    n_ok_above_150 = int(np.sum((snrs >= args.ok_snr) & (np.array(FREQS) > 150000)))

    if max_snr < args.silent_snr:
        verdict = 'SILENT (no acoustic coupling)'
    elif max_snr < args.ok_snr:
        verdict = 'WEAK (couples but barely)'
    else:
        verdict = 'OK (real resonances)'

    results[ch] = {
        'max_snr': max_snr, 'f_at_max_hz': f_at_max,
        'n_ok': n_ok, 'n_weak': n_weak, 'n_ok_above_150khz': n_ok_above_150,
        'verdict': verdict,
    }
    print(f"  → {ch}: max SNR {max_snr:.1f}× @ {f_at_max/1000:.1f} kHz | "
          f"OK pts {n_ok} ({n_ok_above_150} above 150 kHz), weak {n_weak} → {verdict}")

nco_off()
nco.close()
ps.ps2000_stop(handle)
ps.ps2000_close_unit(ct.c_int16(handle))

print("\n" + "=" * 70)
print("  SUMMARY")
print("=" * 70)
print(f"  {'CH':<5}{'maxSNR':>8}{'@kHz':>8}{'OK':>5}{'>150k':>7}{'weak':>6}  verdict")
print(f"  {'-'*5}{'-'*8}{'-'*8}{'-'*5}{'-'*7}{'-'*6}  {'-'*30}")
for ch in CHANNELS:
    r = results[ch]
    print(f"  {ch:<5}{r['max_snr']:>8.1f}{r['f_at_max_hz']/1000:>8.1f}"
          f"{r['n_ok']:>5}{r['n_ok_above_150khz']:>7}{r['n_weak']:>6}  {r['verdict']}")

# Interpretation hint
silent = [c for c in CHANNELS if results[c]['max_snr'] < args.silent_snr]
above_only = [c for c in CHANNELS
              if results[c]['n_ok'] > 0 and results[c]['n_ok'] == results[c]['n_ok_above_150khz']]
print()
if silent:
    print(f"  ⚠️  SILENT channels: {silent} — these have NO coupling anywhere in "
          f"{args.start/1000:.0f}-{args.stop/1000:.0f} kHz.")
    print(f"      Likely physical: open wire, missing 220Ω, dead/unbonded TX PZT.")
    print(f"      Verify: continuity NCO pin → 220Ω → PZT, and PZT bond to plate.")
if above_only:
    print(f"  ℹ️  Channels alive ONLY above 150 kHz: {above_only} — the census "
          f"missed these by capping at 150 kHz, NOT a hardware fault.")
if not silent and not above_only:
    print("  All tested channels coupled within the standard band.")

OUT = Path('data/results/tx_diag')
OUT.mkdir(parents=True, exist_ok=True)
ts = datetime.now().strftime('%Y%m%d_%H%M%S')
with open(OUT / f'tx_diag_{ts}.json', 'w') as f:
    json.dump({'timestamp': ts, 'config': vars(args), 'noise_floor': noise_floor,
               'freqs_hz': FREQS, 'results': results}, f, indent=2)
print(f"\n  Saved: {OUT / f'tx_diag_{ts}.json'}")
print("=" * 70)
