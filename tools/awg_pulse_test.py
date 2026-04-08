#!/usr/bin/env python3
"""
AWG pulse excitation: try to replicate a 'tap' via PZT.

Use the PS2000 arbitrary waveform generator to output a sharp pulse,
then capture the response. If the PZT can deliver enough impulse,
this is equivalent to an automated tap.

Also tests: improved sweep capture with 100 averages to properly
sample the full sweep range (addressing the original 4-capture bug).
"""
import ctypes
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cwm_picoscope import (TIMEBASE, N_SAMPLES, SAMPLE_RATE, AWG_DRIVE_UVPP,
                            _extract_peaks_blind, score_spectrum_against_rod)
from picosdk.ps2000 import ps2000

USERS = Path(__file__).resolve().parent.parent / "data" / "results" / "lab" / "users.json"
with open(USERS) as f:
    db = json.load(f)

rod1_hz = db["rods"]["1"]["perturbed_hz"][:10]


handle = ps2000.ps2000_open_unit()
if handle <= 0:
    print(f"FATAL: handle={handle}")
    sys.exit(1)
print(f"Scope opened (handle={handle})\n")

try:
    ps2000.ps2000_set_channel(handle, 0, True, 1, 6)   # Ch A ±1V
    ps2000.ps2000_set_channel(handle, 1, False, 1, 6)   # Ch B OFF

    def cap(n_samples=N_SAMPLES, auto_ms=10):
        ps2000.ps2000_set_trigger(handle, 0, 0, 0, 0, auto_ms)
        t_ms = ctypes.c_int32()
        ps2000.ps2000_run_block(handle, n_samples, TIMEBASE, 1, ctypes.byref(t_ms))
        t0 = time.time()
        while ps2000.ps2000_ready(handle) == 0:
            time.sleep(0.001)
            if time.time() - t0 > 5:
                return None
        a = (ctypes.c_int16 * n_samples)()
        b = (ctypes.c_int16 * n_samples)()
        ov = ctypes.c_int16()
        n = ps2000.ps2000_get_values(handle, ctypes.byref(a), ctypes.byref(b),
                                      None, None, ctypes.byref(ov), n_samples)
        return np.array(a[:n], dtype=np.float64) if n > 0 else None

    def fft_avg(captures, pad=4):
        if not captures:
            return None, None, 0
        cap_len = len(captures[0])
        nfft = cap_len * pad
        freq = np.fft.rfftfreq(nfft, d=1.0 / SAMPLE_RATE)
        acc = np.zeros(nfft // 2 + 1)
        for raw in captures:
            w = raw[:cap_len] * np.hanning(cap_len)
            acc += np.abs(np.fft.rfft(w, n=nfft))
        return freq, acc / len(captures), freq[1]

    def score_result(freq, mag, bin_hz, label=""):
        min_bin = int(500 / bin_hz)
        noise = np.median(mag[min_bin:])
        pk_idx = min_bin + np.argmax(mag[min_bin:])
        pk = mag[pk_idx]
        snr = pk / noise if noise > 0 else 0
        # Count enrolled peaks
        matched = 0
        for rf in rod1_hz:
            tb = int(round(rf / bin_hz))
            lo = max(min_bin, tb - 3)
            hi = min(len(mag) - 1, tb + 3)
            if np.max(mag[lo:hi + 1]) > noise * 5:
                matched += 1
        print(f"  {label}: peak={pk:.0f} @ {freq[pk_idx]:.0f} Hz, "
              f"noise={noise:.0f}, SNR={snr:.1f}x, enrolled={matched}/10")
        try:
            peaks = _extract_peaks_blind(freq, mag, bin_hz)
            print(f"    Blind peaks ({len(peaks)}): "
                  f"{[round(p,1) for p in peaks[:10]]}")
            # Score against all rods
            for rid in sorted(db["rods"].keys()):
                r = db["rods"][rid]
                if not r.get("enrolled"):
                    continue
                sc = score_spectrum_against_rod(freq, mag, bin_hz,
                                                r["perturbed_hz"][:10])
                print(f"    vs Rod {rid}: score={sc['score']*100:.1f}%, "
                      f"matched={sc['n_matched']}/{sc['n_total']}")
        except RuntimeError as e:
            print(f"    Peak extraction: {e}")
        return snr, matched

    # === Test 1: Noise baseline ===
    print("=== T1: NOISE BASELINE ===")
    raw = cap(auto_ms=100)
    if raw is not None:
        rms = np.sqrt(np.mean(raw ** 2))
        print(f"  Noise RMS={rms:.1f} ADC")

    # === Test 2: AWG pulse via arbitrary waveform ===
    print("\n=== T2: AWG PULSE (arbitrary waveform) ===")
    for pulse_width in [1, 4, 16, 64]:
        arb_len = 4096
        buf = np.zeros(arb_len, dtype=np.float64)
        # Sharp pulse at start
        buf[:pulse_width] = 1.0
        # Map to unsigned 8-bit
        arb_u8 = ((buf * 127) + 128).clip(0, 255).astype(np.uint8)
        arb_buf = (ctypes.c_uint8 * arb_len)(*arb_u8.tolist())

        # Set repetition rate: pick delta_phase for ~1 kHz rep rate
        # f_rep = delta_phase * 48e6 / 2^32 / arb_len
        # For f_rep=1000: delta_phase = 1000 * 2^32 / 48e6 * arb_len
        #                              = 1000 * 4294967296 / 48000000 * 4096
        # Actually ps2000 arb gen formula differs, let me use reasonable value
        # delta_phase = target_freq * arb_len * 2^32 / dac_clock
        # For PS2204A, DAC clock = 48 MHz (from SDK docs)
        # f_rep = delta_phase * 48e6 / (arb_len * 2^32)
        # Want f_rep ≈ 100 Hz (10ms period, matches capture window)
        target_rep = 100.0
        delta_phase = int(target_rep * arb_len * (2**32) / 48_000_000)
        if delta_phase < 1:
            delta_phase = 1
        actual_rep = delta_phase * 48_000_000 / (arb_len * (2**32))
        print(f"\n  Pulse width={pulse_width} samples, "
              f"rep ~{actual_rep:.1f} Hz, delta_phase={delta_phase}")

        try:
            ps2000.ps2000_set_sig_gen_arbitrary(
                handle, 0, AWG_DRIVE_UVPP,
                delta_phase, delta_phase,
                0, 0,
                arb_buf, arb_len, 0, 0
            )
        except Exception as e:
            print(f"  FAILED to set arb gen: {e}")
            continue

        time.sleep(0.5)
        caps = []
        for _ in range(16):
            r = cap(auto_ms=10)
            if r is not None:
                caps.append(r)
        if caps:
            freq, mag, bin_hz = fft_avg(caps)
            score_result(freq, mag, bin_hz, f"pulse_w{pulse_width}")

    # === Test 3: SWEEP with 100 averages (proper coverage) ===
    print("\n=== T3: SWEEP WITH 100 AVERAGES ===")
    dwell = 0.001
    sweep_s = 0.5
    inc = (100000.0 - 1000.0) * dwell / sweep_s
    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, AWG_DRIVE_UVPP, 0,
        1000.0, 100000.0, float(inc), float(dwell), 0, 0
    )
    # Wait for one full sweep cycle
    time.sleep(0.5)
    captures = []
    for i in range(100):
        r = cap(auto_ms=10)
        if r is not None:
            captures.append(r)
    print(f"  Captured {len(captures)} blocks across ~{len(captures)*10/1000:.1f}s")
    if captures:
        freq, mag, bin_hz = fft_avg(captures)
        score_result(freq, mag, bin_hz, "100-avg sweep")

    # === Test 4: SWEEP with 200 averages ===
    print("\n=== T4: SWEEP WITH 200 AVERAGES ===")
    # AWG is still running from T3
    captures = []
    for i in range(200):
        r = cap(auto_ms=10)
        if r is not None:
            captures.append(r)
    print(f"  Captured {len(captures)} blocks across ~{len(captures)*10/1000:.1f}s")
    if captures:
        freq, mag, bin_hz = fft_avg(captures)
        score_result(freq, mag, bin_hz, "200-avg sweep")

    # === Test 5: Confirm original 4-avg issue ===
    print("\n=== T5: ORIGINAL 4-AVERAGE SWEEP (reproducing the bug) ===")
    # AWG still running
    captures = []
    for i in range(4):
        r = cap(auto_ms=10)
        if r is not None:
            captures.append(r)
    if captures:
        freq, mag, bin_hz = fft_avg(captures)
        score_result(freq, mag, bin_hz, "4-avg sweep")

finally:
    ps2000.ps2000_stop(handle)
    ps2000.ps2000_close_unit(handle)
    print("\nScope closed.")
