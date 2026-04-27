#!/usr/bin/env python3
"""
3-Source Kernel Experiment — 2× AD9833 DDS + PicoScope AWG

Drives 3 carrier tones at enrolled eigenmode frequencies into glass
plates through a resistor summing network → TX PZT (all plates in parallel).
Reads acoustic response from a selected plate's RX PZT via relay mux → Ch A.

Hardware:
  - Carrier 0: AD9833 DDS #1 (Arduino Nano #2, F1:<freq>)
  - Carrier 1: AD9833 DDS #2 (Arduino Nano #2, F2:<freq>)
  - Carrier 2: PicoScope AWG (built-in sig gen, CW sine)
  - Relay mux: Arduino Nano #1, selects which plate's RX PZT → Ch A
  - TX path: summing node → all drive PZTs in parallel
  - RX path: selected plate's sense PZT → relay → PicoScope Ch A

3 carriers → 7 binary ON/OFF patterns (2^3 - 1, excluding all-off).
Readout at carrier fundamentals + all 2nd-order IM products.

Usage:
    DYLD_LIBRARY_PATH="/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources" \\
        python tools/kernel_3source.py --port /dev/cu.usbserial-11330 \\
        --mux-port /dev/cu.usbserial-11310 --plate 4_NE \\
        [--carriers 29300,47800,34900] [--n-avg 20] [--prescan-avg 24]
"""
from __future__ import annotations

import argparse
import ctypes
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np

TOOLS_DIR = Path(__file__).resolve().parent
ROOT = TOOLS_DIR.parent
RESULTS_DIR = ROOT / "data" / "results" / "lab" / "plate_exps" / "kernel"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# ── PicoScope constants ──
TIMEBASE = 7                      # 1280 ns/sample
DT = 1280e-9
SAMPLE_RATE = int(1e9 / 1280)     # 781 250 Hz
N_SAMPLES = 8064
N_SAMPLES_2CH = 2048          # ps2000 2204A max with both channels enabled
AWG_UVPP = 600_000                # 600 mVpp (≈ AD9833 output level)
CH_A_RANGE = 7                    # ±2 V  (summing node)
CH_B_RANGE = 7                    # ±2 V  (AWG reference via T-connector)

# ── Timing ──
SETTLE_S = 0.12                   # after any carrier change
PRESCAN_SETTLE_S = 0.20           # extra settle for pre-scan

# ── Default enrolled eigenmodes (from plate 4_NE census) ──
DEFAULT_CARRIERS = [29300, 47800, 34900]

# ── Top eigenmode candidates per plate (from census sweeps 2026-04-18) ──
CANDIDATE_FREQS = {
    "4_NE": [47800, 29300, 64300, 63200, 34900, 48500, 62300,
             43300, 54900, 41900, 30000, 55500, 35700, 28900],
}

# Minimum Hz separation between selected carriers (for clean IM products)
MIN_CARRIER_SEP = 4000

# ── Plate → relay channel mapping (NE read PZTs) ──
RECEIVER_MAP = {
    "1":    (1, "A-NE"),
    "2":    (2, "B-NE"),
    "3_NE": (3, "G-NE"),
    "4_NE": (5, "D-NE"),
    "5_NE": (7, "H-NE"),
}


def log(msg):
    print(msg, flush=True)


# ═══════════════════════════════════════════════════════════════════════
#  Hardware: PicoScope 2204A (ctypes, ps2000 driver)
# ═══════════════════════════════════════════════════════════════════════

class PicoScope:
    def __init__(self, two_ch=False):
        self.ps = ctypes.CDLL("libps2000.dylib")
        self.ps.ps2000_set_sig_gen_built_in.argtypes = [
            ctypes.c_int16, ctypes.c_int32, ctypes.c_uint32, ctypes.c_int16,
            ctypes.c_float, ctypes.c_float, ctypes.c_float, ctypes.c_float,
            ctypes.c_int32, ctypes.c_uint32,
        ]
        self.ps.ps2000_set_sig_gen_built_in.restype = ctypes.c_int16

        self.handle = self.ps.ps2000_open_unit()
        if self.handle <= 0:
            raise RuntimeError(f"ps2000_open_unit failed ({self.handle})")

        self.two_ch = two_ch
        # Ch A: acoustic response via relay mux
        self.ps.ps2000_set_channel(self.handle, 0, 1, 1, CH_A_RANGE)
        # Ch B: AWG reference via T-connector (or disabled)
        self.ps.ps2000_set_channel(self.handle, 1, 1 if two_ch else 0, 1, CH_B_RANGE)
        self.n_samples = N_SAMPLES_2CH if two_ch else N_SAMPLES
        mode_str = "Ch A + Ch B (T-ref)" if two_ch else "Ch A only"
        log(f"  PicoScope opened (handle={self.handle}), {mode_str}, "
            f"{self.n_samples} samples")

    def awg_sine(self, freq_hz, uvpp=None):
        if uvpp is None:
            uvpp = AWG_UVPP
        self.ps.ps2000_set_sig_gen_built_in(
            self.handle, 0, uvpp, 0,
            float(freq_hz), float(freq_hz), 0.0, 0.0, 0, 0)

    def awg_off(self):
        self.ps.ps2000_set_sig_gen_built_in(
            self.handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0)

    def capture(self):
        """Capture from Ch A (and Ch B if two_ch). Returns (a, b) float64."""
        # source=0 (Ch A), threshold=0, rising, delay=0, auto_ms=100
        self.ps.ps2000_set_trigger(self.handle, 0, 0, 0, 0, 100)
        t_ms = ctypes.c_int32()
        ns = self.n_samples
        self.ps.ps2000_run_block(
            self.handle, ns, TIMEBASE, 1, ctypes.byref(t_ms))
        t0 = time.time()
        while self.ps.ps2000_ready(self.handle) == 0:
            time.sleep(0.002)
            if time.time() - t0 > 5:
                raise TimeoutError("PicoScope capture timed out")
        buf_a = (ctypes.c_int16 * ns)()
        buf_b = (ctypes.c_int16 * ns)()
        overflow = ctypes.c_int16()
        n = self.ps.ps2000_get_values(
            self.handle, ctypes.byref(buf_a), ctypes.byref(buf_b),
            None, None, ctypes.byref(overflow), ns)
        if n <= 0:
            raise RuntimeError(f"ps2000_get_values returned {n}")
        return (np.array(buf_a[:n], dtype=np.float64),
                np.array(buf_b[:n], dtype=np.float64))

    def close(self):
        self.awg_off()
        self.ps.ps2000_stop(self.handle)
        self.ps.ps2000_close_unit(self.handle)
        log("  PicoScope closed")


# ═══════════════════════════════════════════════════════════════════════
#  Hardware: AD9833 DDS via Arduino Nano serial
# ═══════════════════════════════════════════════════════════════════════

class DDSController:
    def __init__(self, port, baud=115200):
        import serial
        self.ser = serial.Serial(port, baud, timeout=2)
        time.sleep(2)
        self.ser.reset_input_buffer()
        log(f"  DDS controller opened on {port} @ {baud} baud")

    def set_freq(self, channel, freq_hz):
        """Set DDS channel (1 or 2) to freq_hz. 0 → off."""
        if freq_hz == 0:
            cmd = f"F{channel}:off\n"
        else:
            cmd = f"F{channel}:{int(freq_hz)}\n"
        self.ser.write(cmd.encode())
        time.sleep(0.002)
        return self.ser.readline().decode("ascii", errors="replace").strip()

    def all_off(self):
        self.ser.write(b"Foff\n")
        time.sleep(0.002)
        return self.ser.readline().decode("ascii", errors="replace").strip()

    def query(self):
        self.ser.write(b"D?\n")
        time.sleep(0.002)
        return self.ser.readline().decode("ascii", errors="replace").strip()

    def close(self):
        self.all_off()
        self.ser.close()
        log("  DDS controller closed")


# ═══════════════════════════════════════════════════════════════════════
#  Spectral helpers
# ═══════════════════════════════════════════════════════════════════════

def extract_at_bins(data, readout_freqs, zero_pad=4):
    """FFT with Hanning window + zero-pad, return magnitudes at bins."""
    data = data - np.mean(data)
    windowed = data * np.hanning(len(data))
    nfft = len(data) * zero_pad
    fft_c = np.fft.rfft(windowed, n=nfft)
    freq_axis = np.fft.rfftfreq(nfft, d=DT)
    bin_hz = freq_axis[1] - freq_axis[0]

    mags = np.zeros(len(readout_freqs))
    for j, rf in enumerate(readout_freqs):
        tb = int(round(rf / bin_hz))
        lo = max(0, tb - 3)
        hi = min(len(fft_c) - 1, tb + 3)
        pk = lo + np.argmax(np.abs(fft_c[lo:hi + 1]))
        mags[j] = np.abs(fft_c[pk])
    return mags


def extract_complex_at_bins(data, readout_freqs, zero_pad=4):
    """FFT with Hanning window, return complex values at readout bins."""
    data = data - np.mean(data)
    windowed = data * np.hanning(len(data))
    nfft = len(data) * zero_pad
    fft_c = np.fft.rfft(windowed, n=nfft)
    freq_axis = np.fft.rfftfreq(nfft, d=DT)
    bin_hz = freq_axis[1] - freq_axis[0]

    vals = np.zeros(len(readout_freqs), dtype=np.complex128)
    for j, rf in enumerate(readout_freqs):
        tb = int(round(rf / bin_hz))
        lo = max(0, tb - 3)
        hi = min(len(fft_c) - 1, tb + 3)
        pk = lo + np.argmax(np.abs(fft_c[lo:hi + 1]))
        vals[j] = fft_c[pk]
    return vals


def capture_averaged(scope, readout_freqs, n_avg):
    """Capture n_avg frames, return averaged (ch_a_mags, ch_b_mags)."""
    mag_a = np.zeros(len(readout_freqs))
    mag_b = np.zeros(len(readout_freqs))
    for _ in range(n_avg):
        a, b = scope.capture()
        mag_a += extract_at_bins(a, readout_freqs)
        mag_b += extract_at_bins(b, readout_freqs)
    return mag_a / n_avg, mag_b / n_avg


def capture_coherent(scope, readout_freqs, n_avg):
    """Capture n_avg frames with phase coherence.
    Returns (ch_a_mags, ch_b_mags, phase_stability).

    Phase stability = mean |<exp(j*delta_phase)>| across captures.
    = 1.0 for perfect phase lock (genuine signal), ~0.0 for noise.
    """
    n_bins = len(readout_freqs)
    mag_a = np.zeros(n_bins)
    mag_b = np.zeros(n_bins)
    # Accumulate unit phasors of (phase_A - phase_B) for coherence metric
    phasor_sum = np.zeros(n_bins, dtype=np.complex128)

    for _ in range(n_avg):
        a, b = scope.capture()
        ca = extract_complex_at_bins(a, readout_freqs)
        cb = extract_complex_at_bins(b, readout_freqs)
        mag_a += np.abs(ca)
        mag_b += np.abs(cb)
        # Phase difference phasor: exp(j*(angle_a - angle_b))
        # Where Ch B has signal (AWG on), this measures phase stability
        # Where Ch B is noise, the phasor will be random → |mean| ≈ 0
        with np.errstate(divide='ignore', invalid='ignore'):
            ratio = ca * np.conj(cb)
            norms = np.abs(ratio)
            norms[norms == 0] = 1
            phasor_sum += ratio / norms

    mag_a /= n_avg
    mag_b /= n_avg
    # Phase stability: |mean phasor| ∈ [0, 1]
    phase_stability = np.abs(phasor_sum) / n_avg

    return mag_a, mag_b, phase_stability


# ═══════════════════════════════════════════════════════════════════════
#  Phase 0: Compute readout frequencies
# ═══════════════════════════════════════════════════════════════════════

def compute_readout_freqs(carrier_freqs):
    """Carriers + all 2nd-order IM products (|fi−fj|, fi+fj, 2fi−fj)."""
    readout = set()
    im_labels = {}
    n = len(carrier_freqs)

    for i, f in enumerate(carrier_freqs):
        rf = round(f)
        readout.add(rf)
        im_labels[rf] = f"f{i}"

    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            fi, fj = carrier_freqs[i], carrier_freqs[j]
            for label, imf in [
                (f"|f{i}-f{j}|", abs(fi - fj)),
                (f"f{i}+f{j}", fi + fj),
                (f"2f{i}-f{j}", abs(2 * fi - fj)),
            ]:
                imf_r = round(imf)
                if 1000 < imf_r < SAMPLE_RATE // 2:
                    readout.add(imf_r)
                    if imf_r not in im_labels:
                        im_labels[imf_r] = label

    readout_sorted = sorted(readout)
    n_c = len(carrier_freqs)
    log(f"  Readout bins: {len(readout_sorted)} total "
        f"({n_c} carriers + {len(readout_sorted) - n_c} IM products)")
    for rf in readout_sorted:
        log(f"    {rf:>8d} Hz  {im_labels.get(rf, '')}")
    return readout_sorted, im_labels


# ═══════════════════════════════════════════════════════════════════════
#  Phase 0: Candidate frequency scan + auto-balance
# ═══════════════════════════════════════════════════════════════════════

def scan_candidates(scope, candidates, n_avg, ref_mvpp=400):
    """Drive each candidate frequency on AWG, measure plate acoustic response.
    Returns list of (freq_hz, magnitude, snr) sorted by magnitude descending."""

    log("\n══════════════════════════════════════════════════")
    log("  Phase 0: CANDIDATE FREQUENCY SCAN")
    log("══════════════════════════════════════════════════")
    log(f"  {len(candidates)} candidates, {ref_mvpp} mVpp ref, {n_avg} avg")

    scope.awg_off()
    time.sleep(PRESCAN_SETTLE_S)
    bl_mags = np.zeros(len(candidates))
    for _ in range(n_avg):
        a, _ = scope.capture()
        bl_mags += extract_at_bins(a, candidates)
    bl_mags /= n_avg
    mean_bl = np.mean(bl_mags)
    log(f"  Baseline noise floor: {mean_bl:.0f}")

    results = []
    for i, freq in enumerate(candidates):
        scope.awg_sine(freq, uvpp=ref_mvpp * 1000)
        time.sleep(PRESCAN_SETTLE_S)
        mag_sum = 0.0
        for _ in range(n_avg):
            a, _ = scope.capture()
            m = extract_at_bins(a, [freq])
            mag_sum += m[0]
        mag = mag_sum / n_avg
        snr = mag / (bl_mags[i] + 1)
        results.append((freq, mag, snr))
        log(f"    {freq:>6.0f} Hz  mag={mag:>10.0f}  SNR={snr:>7.1f}×")

    scope.awg_off()
    time.sleep(SETTLE_S)

    results.sort(key=lambda x: -x[1])
    return results


def auto_balance(scan_results, min_sep=MIN_CARRIER_SEP):
    """Filter to strong modes (geometric-mean, diary V5), pick 3 well-separated,
    assign strongest-responding to DDS (weak sources), weakest to AWG (strong source).
    Returns (carrier_freqs=[dds1, dds2, awg], awg_mvpp)."""

    mags = np.array([r[1] for r in scan_results])

    # Geometric-mean threshold (V5: upper/lower halves)
    sorted_mags = np.sort(mags)
    mid = len(sorted_mags) // 2
    upper_gm = np.exp(np.mean(np.log(sorted_mags[mid:] + 1)))
    lower_gm = np.exp(np.mean(np.log(sorted_mags[:mid] + 1)))
    threshold = np.sqrt(upper_gm * lower_gm)

    strong = [(f, m, s) for f, m, s in scan_results if m > threshold]
    log(f"\n  Geometric-mean threshold: {threshold:.0f}")
    log(f"  Strong modes: {len(strong)} / {len(scan_results)}")
    for f, m, s in strong:
        log(f"    {f:>6.0f} Hz  mag={m:>10.0f}  SNR={s:>7.1f}×")

    if len(strong) < 3:
        log("  WARNING: <3 strong modes, using top 3 overall")
        strong = list(scan_results[:3])

    # Greedy selection: start with strongest, then pick most-separated
    selected = [strong[0]]
    pool = list(strong[1:])

    while len(selected) < 3 and pool:
        best_i = -1
        best_gap = -1
        for i, (f, m, s) in enumerate(pool):
            gap = min(abs(f - sf) for sf, _, _ in selected)
            if gap > best_gap:
                best_gap = gap
                best_i = i
        if best_gap < min_sep:
            pool.pop(best_i)
            if not pool:
                break
            continue
        selected.append(pool.pop(best_i))

    if len(selected) < 3:
        log("  WARNING: could not find 3 modes with sufficient separation")
        # Fall back to top 3 regardless of separation
        selected = list(scan_results[:3])

    # Sort: strongest first
    selected.sort(key=lambda x: -x[1])

    # Assign: top 2 → DDS (weak ~600mVpp through 1kΩ), 3rd → AWG (strong, variable)
    dds1_f, dds1_m, _ = selected[0]
    dds2_f, dds2_m, _ = selected[1]
    awg_f, awg_m, _ = selected[2]

    # Estimate AWG amplitude to balance received levels.
    # Empirical: DDS boards (~600mVpp through 1kΩ) produce acoustic signal
    # equivalent to ~100mVpp of AWG (through 600Ω direct to summing node).
    # From scan (all at same AWG ref): plate_response ∝ scan_mag.
    # Target: awg_mvpp × awg_plate_response ≈ dds_equiv × dds_plate_response
    mean_dds_scan = (dds1_m + dds2_m) / 2
    dds_equiv_mvpp = 100  # empirical: DDS ≈ 100mVpp of AWG power
    awg_mvpp = int(dds_equiv_mvpp * mean_dds_scan / (awg_m + 1))
    awg_mvpp = max(50, min(2000, awg_mvpp))

    carriers = [dds1_f, dds2_f, awg_f]

    log(f"\n  Auto-balance assignment:")
    log(f"    DDS#1: {dds1_f:.0f} Hz  (plate response: {dds1_m:.0f})")
    log(f"    DDS#2: {dds2_f:.0f} Hz  (plate response: {dds2_m:.0f})")
    log(f"    AWG:   {awg_f:.0f} Hz   (plate response: {awg_m:.0f})")
    log(f"    AWG amplitude: {awg_mvpp} mVpp")
    log(f"    Carrier separation: "
        f"{abs(carriers[0]-carriers[1]):.0f}, "
        f"{abs(carriers[0]-carriers[2]):.0f}, "
        f"{abs(carriers[1]-carriers[2]):.0f} Hz")

    return carriers, awg_mvpp


# ═══════════════════════════════════════════════════════════════════════
#  Drive control
# ═══════════════════════════════════════════════════════════════════════

def drive_pattern(dds, scope, carrier_freqs, pattern):
    """Set carriers ON/OFF.  [0]=DDS#1, [1]=DDS#2, [2]=AWG."""
    if pattern[0]:
        dds.set_freq(1, carrier_freqs[0])
    else:
        dds.set_freq(1, 0)
    if pattern[1]:
        dds.set_freq(2, carrier_freqs[1])
    else:
        dds.set_freq(2, 0)
    if pattern[2]:
        scope.awg_sine(carrier_freqs[2])
    else:
        scope.awg_off()
    time.sleep(SETTLE_S)


def silence_all(dds, scope):
    dds.all_off()
    scope.awg_off()
    time.sleep(SETTLE_S)


# ═══════════════════════════════════════════════════════════════════════
#  Phase 1: Pre-scan
# ═══════════════════════════════════════════════════════════════════════

def prescan(dds, scope, carrier_freqs, readout_freqs, n_avg):
    n_bins = len(readout_freqs)
    n_carriers = len(carrier_freqs)
    use_coherence = scope.two_ch

    log("\n══════════════════════════════════════════════════")
    log("  Phase 1: PRE-SCAN")
    if use_coherence:
        log("  (Phase-coherent mode: Ch B = AWG reference)")
    log("══════════════════════════════════════════════════")

    # Baseline
    silence_all(dds, scope)
    time.sleep(PRESCAN_SETTLE_S)
    baseline, _ = capture_averaged(scope, readout_freqs, n_avg)
    log(f"  Baseline captured (mean={np.mean(baseline):.0f})")

    # Each carrier alone
    single_mags = np.zeros((n_carriers, n_bins))
    source_names = ["DDS#1", "DDS#2", "AWG"]
    for ci in range(n_carriers):
        pat = [0] * n_carriers
        pat[ci] = 1
        drive_pattern(dds, scope, carrier_freqs, pat)
        time.sleep(PRESCAN_SETTLE_S)
        mags, _ = capture_averaged(scope, readout_freqs, n_avg)
        single_mags[ci] = mags
        log(f"  {source_names[ci]} @ {carrier_freqs[ci]:.0f} Hz: "
            f"max={np.max(mags):.0f}  mean={np.mean(mags):.0f}")

    # All-on (with coherence if available)
    drive_pattern(dds, scope, carrier_freqs, [1] * n_carriers)
    time.sleep(PRESCAN_SETTLE_S)
    if use_coherence:
        all_on, all_on_chb, phase_stab = capture_coherent(
            scope, readout_freqs, n_avg)
    else:
        all_on, all_on_chb = capture_averaged(scope, readout_freqs, n_avg)
        phase_stab = None
    log(f"  All-on: max={np.max(all_on):.0f}  mean={np.mean(all_on):.0f}")
    if phase_stab is not None:
        log(f"  Ch B ref max={np.max(all_on_chb):.0f}  "
            f"mean phase stability={np.mean(phase_stab):.3f}")

    silence_all(dds, scope)

    # Classify bins
    noise_floor = baseline + 1
    all_on_snr = all_on / noise_floor
    single_max_snr = np.max(single_mags / noise_floor[np.newaxis, :], axis=0)

    carrier_mask = (all_on_snr > 3.0) | (single_max_snr > 5.0)
    im_mask = np.zeros(n_bins, dtype=bool)
    for j in range(n_bins):
        if all_on_snr[j] > 1.3 and single_max_snr[j] < 1.5:
            im_mask[j] = True
        # Phase coherence boost: if Ch B ref shows the bin is phase-locked
        # to AWG, it's more likely genuine IM (even if magnitude is marginal)
        if phase_stab is not None and phase_stab[j] > 0.7:
            if all_on_snr[j] > 1.15 and single_max_snr[j] < 1.5:
                im_mask[j] = True

    live_mask = carrier_mask | im_mask
    n_live = int(np.sum(live_mask))
    n_im = int(np.sum(im_mask))

    log(f"\n  Pre-scan results:")
    log(f"    Live bins:    {n_live} / {n_bins}")
    log(f"    Carrier bins: {int(np.sum(carrier_mask))}")
    log(f"    Pure IM bins: {n_im}")
    carrier_set = set(round(f) for f in carrier_freqs)
    for j in np.where(live_mask)[0]:
        tag = ""
        if im_mask[j]:
            tag += " [IM]"
        if readout_freqs[j] in carrier_set:
            tag += " [carrier]"
        ps_str = ""
        if phase_stab is not None:
            ps_str = f"  φ-lock={phase_stab[j]:.2f}"
        log(f"      {readout_freqs[j]:>8d} Hz  "
            f"SNR_all={all_on_snr[j]:>6.1f}  "
            f"SNR_single={single_max_snr[j]:>6.1f}{ps_str}{tag}")

    return {
        "live_mask": live_mask,
        "im_mask": im_mask,
        "baseline": baseline,
        "single_mags": single_mags,
        "all_on": all_on,
        "all_on_chb": all_on_chb,
        "all_on_snr": all_on_snr,
        "single_max_snr": single_max_snr,
        "phase_stability": phase_stab,
    }


# ═══════════════════════════════════════════════════════════════════════
#  Phase 2: Kernel measurement
# ═══════════════════════════════════════════════════════════════════════

def measure_kernel(dds, scope, carrier_freqs, readout_freqs, live_mask,
                   n_avg):
    n_carriers = len(carrier_freqs)
    n_patterns = (2 ** n_carriers) - 1
    live_idx = np.where(live_mask)[0]
    n_live = len(live_idx)
    use_coherence = scope.two_ch

    log(f"\n══════════════════════════════════════════════════")
    log(f"  Phase 2: KERNEL MEASUREMENT")
    if use_coherence:
        log(f"  (Phase-coherent: {scope.n_samples} samples/ch)")
    log(f"══════════════════════════════════════════════════")
    log(f"  {n_patterns} patterns × {n_avg} averages × {n_live} live bins")
    est_s = n_patterns * (SETTLE_S + n_avg * (scope.n_samples * DT + 0.005))
    log(f"  Estimated time: {est_s:.0f} s")

    # Binary patterns (1 … 2^N−1)
    patterns = np.zeros((n_patterns, n_carriers), dtype=np.float64)
    for p in range(n_patterns):
        bits = p + 1
        for c in range(n_carriers):
            patterns[p, c] = 1.0 if (bits >> c) & 1 else 0.0

    K_full = np.zeros((n_patterns, len(readout_freqs)))
    K_chb = np.zeros((n_patterns, len(readout_freqs)))
    K_phase_stab = np.zeros((n_patterns, len(readout_freqs)))

    order = np.random.permutation(n_patterns)
    for step_i, pi in enumerate(order):
        pat = patterns[pi].tolist()
        drive_pattern(dds, scope, carrier_freqs, pat)

        if use_coherence:
            mags_a, mags_b, ps = capture_coherent(
                scope, readout_freqs, n_avg)
            K_phase_stab[pi] = ps
        else:
            mags_a, mags_b = capture_averaged(scope, readout_freqs, n_avg)

        K_full[pi] = mags_a
        K_chb[pi] = mags_b

        pat_str = "".join(str(int(patterns[pi, c])) for c in range(n_carriers))
        extra = ""
        if use_coherence:
            mean_ps = np.mean(ps[live_idx])
            extra = f"  φ-lock={mean_ps:.2f}"
        log(f"    [{step_i + 1}/{n_patterns}] "
            f"pattern={pat_str}  "
            f"max_live={np.max(mags_a[live_idx]):.0f}{extra}")

    silence_all(dds, scope)

    K = K_full[:, live_idx]
    return K, patterns, K_full, K_chb, live_idx, K_phase_stab


# ═══════════════════════════════════════════════════════════════════════
#  Phase 3: Evaluation
# ═══════════════════════════════════════════════════════════════════════

def evaluate_kernel(K, patterns, carrier_freqs, readout_freqs, live_idx,
                    im_labels):
    from sklearn.linear_model import Ridge, RidgeClassifier
    from sklearn.preprocessing import StandardScaler
    from scipy.spatial.distance import cdist

    n_patterns, n_features = K.shape
    n_carriers = patterns.shape[1]

    log(f"\n══════════════════════════════════════════════════")
    log(f"  Phase 3: EVALUATION")
    log(f"  Kernel matrix: {n_patterns} × {n_features}")
    log(f"══════════════════════════════════════════════════")

    results = {}

    # ── 3a. Effective rank ──
    sc = StandardScaler()
    K_s = sc.fit_transform(K)
    U, S, Vt = np.linalg.svd(K_s, full_matrices=False)
    S_norm = S / S[0] if S[0] > 0 else S
    eff_rank = int(np.sum(S_norm > 0.01))
    s_entropy = -np.sum(
        (S_norm[S_norm > 0] ** 2) * np.log(S_norm[S_norm > 0] ** 2 + 1e-12))

    results["effective_rank"] = eff_rank
    results["sv_entropy"] = round(float(s_entropy), 4)
    results["top_svs"] = [round(float(s), 4) for s in S_norm[:min(10, len(S_norm))]]

    log(f"\n  3a. Effective rank: {eff_rank} / "
        f"{min(n_patterns, n_features)}")
    log(f"      SV entropy:     {s_entropy:.4f}")
    log(f"      Top SVs:        {S_norm[:6].round(3)}")

    # ── 3b. Kernel alignment ──
    K_gram = K_s @ K_s.T
    X_in = patterns
    K_lin = X_in @ X_in.T

    dists = cdist(X_in, X_in, "sqeuclidean")
    sigma = np.median(dists[dists > 0]) ** 0.5
    K_rbf = np.exp(-dists / (2 * sigma ** 2))
    K_poly2 = (X_in @ X_in.T + 1) ** 2
    K_poly3 = (X_in @ X_in.T + 1) ** 3

    def centered_alignment(K1, K2):
        n = K1.shape[0]
        H = np.eye(n) - np.ones((n, n)) / n
        Kc1, Kc2 = H @ K1 @ H, H @ K2 @ H
        num = np.sum(Kc1 * Kc2)
        den = np.sqrt(np.sum(Kc1 ** 2) * np.sum(Kc2 ** 2))
        return float(num / den) if den > 0 else 0.0

    align = {
        "linear": round(centered_alignment(K_gram, K_lin), 4),
        "rbf": round(centered_alignment(K_gram, K_rbf), 4),
        "poly_d2": round(centered_alignment(K_gram, K_poly2), 4),
        "poly_d3": round(centered_alignment(K_gram, K_poly3), 4),
    }
    results["kernel_alignment"] = align
    log(f"\n  3b. Kernel alignment (centered):")
    for k, v in align.items():
        log(f"      {k:>10s}: {v:.4f}")

    # ── 3c. Classification (leave-one-out) ──
    log(f"\n  3c. Classification (LOO):")
    results["classification"] = {}

    def loo_classify(X, y, name):
        n = len(y)
        correct = 0
        for i in range(n):
            X_tr = np.delete(X, i, axis=0)
            y_tr = np.delete(y, i)
            sc_l = StandardScaler()
            X_tr_s = sc_l.fit_transform(X_tr)
            X_te_s = sc_l.transform(X[i:i + 1])
            clf = RidgeClassifier(alpha=1.0)
            clf.fit(X_tr_s, y_tr)
            if clf.predict(X_te_s)[0] == y[i]:
                correct += 1
        acc = correct / n
        results["classification"][name] = round(acc, 4)
        return acc

    parity = np.array([int(np.sum(patterns[i]) % 2) for i in range(n_patterns)])
    acc_par_plate = loo_classify(K_s, parity, "parity_plate")
    acc_par_lin = loo_classify(patterns, parity, "parity_linear")

    # Quadratic baseline
    quad_feats = []
    for i in range(n_carriers):
        for j in range(i + 1, n_carriers):
            quad_feats.append(patterns[:, i] * patterns[:, j])
    if quad_feats:
        X_quad = np.column_stack([patterns] + quad_feats)
        acc_par_quad = loo_classify(X_quad, parity, "parity_quadratic")
    else:
        acc_par_quad = acc_par_lin

    log(f"    Parity:   plate={acc_par_plate:.1%}  "
        f"linear={acc_par_lin:.1%}  quad={acc_par_quad:.1%}")

    majority = np.array([int(np.sum(patterns[i]) > n_carriers / 2)
                         for i in range(n_patterns)])
    acc_maj_plate = loo_classify(K_s, majority, "majority_plate")
    acc_maj_lin = loo_classify(patterns, majority, "majority_linear")
    log(f"    Majority: plate={acc_maj_plate:.1%}  linear={acc_maj_lin:.1%}")

    if n_carriers >= 2:
        and_01 = np.array([int(patterns[i, 0] * patterns[i, 1])
                           for i in range(n_patterns)])
        acc_and_plate = loo_classify(K_s, and_01, "and01_plate")
        acc_and_lin = loo_classify(patterns, and_01, "and01_linear")
        log(f"    AND(0,1): plate={acc_and_plate:.1%}  "
            f"linear={acc_and_lin:.1%}")

    # ── 3d. Function approximation (LOO NMSE) ──
    log(f"\n  3d. Function approximation (LOO NMSE):")
    results["function_approx"] = {}

    def loo_nmse(X, y, name):
        n = len(y)
        preds = np.zeros(n)
        for i in range(n):
            X_tr = np.delete(X, i, axis=0)
            y_tr = np.delete(y, i)
            sc_l = StandardScaler()
            X_tr_s = sc_l.fit_transform(X_tr)
            X_te_s = sc_l.transform(X[i:i + 1])
            reg = Ridge(alpha=1.0)
            reg.fit(X_tr_s, y_tr)
            preds[i] = reg.predict(X_te_s)[0]
        var = np.var(y)
        nmse = float(np.mean((y - preds) ** 2) / var) if var > 0 else float("inf")
        results["function_approx"][name] = round(nmse, 4)
        return nmse

    y_pair = np.zeros(n_patterns)
    for i in range(n_carriers):
        for j in range(i + 1, n_carriers):
            y_pair += patterns[:, i] * patterns[:, j]

    nmse_pair_plate = loo_nmse(K_s, y_pair, "pairwise_plate")
    nmse_pair_lin = loo_nmse(patterns, y_pair, "pairwise_linear")
    log(f"    Pairwise: plate={nmse_pair_plate:.4f}  "
        f"linear={nmse_pair_lin:.4f}")

    y_prod = np.prod(patterns, axis=1)
    nmse_prod_plate = loo_nmse(K_s, y_prod, "full_product_plate")
    nmse_prod_lin = loo_nmse(patterns, y_prod, "full_product_linear")
    log(f"    Product:  plate={nmse_prod_plate:.4f}  "
        f"linear={nmse_prod_lin:.4f}")

    if n_carriers >= 3:
        y_nl = (np.sin(np.pi * patterns[:, 0] * patterns[:, 1])
                + np.cos(np.pi * patterns[:, 2]))
        nmse_nl_plate = loo_nmse(K_s, y_nl, "sincos_plate")
        nmse_nl_lin = loo_nmse(patterns, y_nl, "sincos_linear")
        log(f"    sin·cos:  plate={nmse_nl_plate:.4f}  "
            f"linear={nmse_nl_lin:.4f}")

    # ── 3e. Software comparison: Random Fourier Features ──
    log(f"\n  3e. Software comparison (RFF, dim={n_features}):")
    rng = np.random.default_rng(42)
    W = rng.normal(0, 2.0, (n_carriers, n_features))
    b = rng.uniform(0, 2 * np.pi, n_features)
    X_rff = np.sqrt(2 / n_features) * np.cos(patterns @ W + b)

    nmse_rff_pair = loo_nmse(X_rff, y_pair, "pairwise_rff")
    nmse_rff_prod = loo_nmse(X_rff, y_prod, "full_product_rff")
    acc_rff_par = loo_classify(X_rff, parity, "parity_rff")

    log(f"    RFF pairwise: {nmse_rff_pair:.4f}  (plate: {nmse_pair_plate:.4f})")
    log(f"    RFF product:  {nmse_rff_prod:.4f}  (plate: {nmse_prod_plate:.4f})")
    log(f"    RFF parity:   {acc_rff_par:.1%}   (plate: {acc_par_plate:.1%})")

    return results


# ═══════════════════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="3-Source Kernel Experiment (2× AD9833 + PicoScope AWG)")
    parser.add_argument("--port", default="/dev/cu.usbserial-11330",
                        help="DDS Arduino (Ard2) serial port")
    parser.add_argument("--mux-port", default="/dev/cu.usbserial-11310",
                        help="Relay mux Arduino (Ard1) serial port")
    parser.add_argument("--plate", default="4_NE",
                        help="Plate ID for relay mux (1, 2, 3_NE, 4_NE, 5_NE)")
    parser.add_argument("--carriers", default=",".join(str(f) for f in DEFAULT_CARRIERS),
                        help="Comma-separated carrier freqs in Hz")
    parser.add_argument("--n-avg", type=int, default=20,
                        help="Averages per capture in kernel phase")
    parser.add_argument("--prescan-avg", type=int, default=24,
                        help="Averages per capture in pre-scan")
    parser.add_argument("--awg-mvpp", type=int, default=600,
                        help="AWG amplitude in mV peak-to-peak")
    parser.add_argument("--scan", action="store_true",
                        help="Phase 0: scan candidate freqs, auto-balance")
    parser.add_argument("--candidates",
                        help="Comma-separated candidate freqs for --scan "
                             "(default: census top modes for plate)")
    parser.add_argument("--phase-ref", action="store_true",
                        help="Enable Ch B as AWG phase reference via "
                             "T-connector (2048 samples, phase-coherent)")
    args = parser.parse_args()

    carrier_freqs = [float(f) for f in args.carriers.split(",")]
    n_carriers = len(carrier_freqs)
    global AWG_UVPP
    AWG_UVPP = args.awg_mvpp * 1000

    log("══════════════════════════════════════════════════════")
    log("  3-Source Kernel Experiment")
    log("  2× AD9833 DDS + PicoScope AWG")
    log("══════════════════════════════════════════════════════")
    if args.scan:
        log("  Mode: AUTO-SCAN + BALANCE")
    else:
        log(f"  Carriers: {carrier_freqs}")
        log(f"  Sources:  DDS#1={carrier_freqs[0]:.0f} Hz, "
            f"DDS#2={carrier_freqs[1]:.0f} Hz, "
            f"AWG={carrier_freqs[2]:.0f} Hz")
    if args.phase_ref:
        log("  Phase ref: Ch B via T-connector (2048 samples/ch)")
    log(f"  AWG amplitude: {args.awg_mvpp} mVpp")
    log(f"  Plate: {args.plate}")

    if args.plate not in RECEIVER_MAP:
        log(f"  ERROR: unknown plate '{args.plate}'. "
            f"Valid: {list(RECEIVER_MAP.keys())}")
        sys.exit(1)
    relay_ch, relay_label = RECEIVER_MAP[args.plate]
    log(f"  Relay mux: ch {relay_ch} ({relay_label})")
    log(f"  TX path: summing node → all drive PZTs (parallel)")
    log(f"  RX path: plate {args.plate} sense PZT → relay {relay_ch} → Ch A")

    # Open hardware — mux first (avoid USB contention with PicoScope)
    from relay_mux import RelayMux

    # Relay mux firmware requires newline-terminated commands
    class RelayMuxNL(RelayMux):
        def _send_cmd(self, cmd):
            if not self.is_open:
                raise RuntimeError("RelayMux is not open")
            self._ser.write((cmd + "\n").encode("ascii"))
            import time as _t
            _t.sleep(0.05)
            line = self._ser.readline().decode("ascii", errors="replace").strip()
            return line

    mux = RelayMuxNL(port=args.mux_port)
    mux.open()
    mux.select(relay_ch)
    time.sleep(0.15)
    log(f"  Relay mux opened, selected ch {relay_ch}")

    dds = DDSController(args.port)
    scope = PicoScope(two_ch=args.phase_ref)

    scan_result = None

    try:
        # Verify DDS
        resp = dds.query()
        log(f"  DDS query: {resp}")

        # ── Phase 0: Auto-scan (optional) ──
        if args.scan:
            if args.candidates:
                cands = [float(f) for f in args.candidates.split(",")]
            elif args.plate in CANDIDATE_FREQS:
                cands = [float(f) for f in CANDIDATE_FREQS[args.plate]]
            else:
                log(f"  ERROR: no candidate freqs for plate '{args.plate}'. "
                    f"Use --candidates.")
                sys.exit(1)

            scan_result = scan_candidates(
                scope, cands, args.prescan_avg, ref_mvpp=400)
            carrier_freqs, balanced_mvpp = auto_balance(scan_result)
            AWG_UVPP = balanced_mvpp * 1000
            n_carriers = len(carrier_freqs)
            log(f"\n  Selected carriers: {carrier_freqs}")
            log(f"  Sources:  DDS#1={carrier_freqs[0]:.0f} Hz, "
                f"DDS#2={carrier_freqs[1]:.0f} Hz, "
                f"AWG={carrier_freqs[2]:.0f} Hz")
            log(f"  Balanced AWG: {balanced_mvpp} mVpp")

        if n_carriers != 3:
            log(f"  ERROR: exactly 3 carriers required, got {n_carriers}")
            sys.exit(1)

        # Compute readout bins (may have changed after scan)
        readout_freqs, im_labels = compute_readout_freqs(carrier_freqs)

        # Phase 1
        ps_result = prescan(dds, scope, carrier_freqs, readout_freqs,
                            args.prescan_avg)
        live_mask = ps_result["live_mask"]

        if np.sum(live_mask) < 3:
            log("  WARNING: fewer than 3 live bins")

        # Phase 2
        K, patterns, K_full, K_chb, live_idx, K_phase_stab = measure_kernel(
            dds, scope, carrier_freqs, readout_freqs, live_mask, args.n_avg)

        # Phase 3
        results = evaluate_kernel(
            K, patterns, carrier_freqs, readout_freqs, live_idx, im_labels)

    finally:
        silence_all(dds, scope)
        scope.close()
        dds.close()
        mux.off()
        mux.close()
        log("  Relay mux closed")

    # ── Save ──
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    prefix = f"kernel_3source_{ts}"

    npz_path = RESULTS_DIR / f"{prefix}.npz"
    np.savez(npz_path,
             K=K,
             patterns=patterns,
             K_full=K_full,
             K_chb=K_chb,
             K_phase_stab=K_phase_stab,
             carrier_freqs=np.array(carrier_freqs),
             readout_freqs=np.array(readout_freqs),
             live_mask=live_mask,
             live_idx=live_idx,
             prescan_baseline=ps_result["baseline"],
             prescan_all_on=ps_result["all_on"],
             prescan_single=ps_result["single_mags"],
             prescan_phase_stability=(
                 ps_result["phase_stability"]
                 if ps_result["phase_stability"] is not None
                 else np.array([])))

    def jsonify(obj):
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, dict):
            return {k: jsonify(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [jsonify(v) for v in obj]
        return obj

    json_path = RESULTS_DIR / f"{prefix}.json"
    with open(json_path, "w") as f:
        json.dump({
            "timestamp": ts,
            "plate": args.plate,
            "relay_ch": relay_ch,
            "sources": ["AD9833_DDS1", "AD9833_DDS2", "PicoScope_AWG"],
            "n_carriers": n_carriers,
            "carrier_freqs": [round(cf, 1) for cf in carrier_freqs],
            "readout_freqs": readout_freqs,
            "im_labels": im_labels,
            "n_readout": len(readout_freqs),
            "n_live": int(np.sum(live_mask)),
            "live_freqs": [readout_freqs[j] for j in live_idx],
            "n_avg": args.n_avg,
            "prescan_avg": args.prescan_avg,
            "awg_mvpp": AWG_UVPP // 1000,
            "phase_ref": args.phase_ref,
            "auto_scan": args.scan,
            "scan_results": (
                [{"freq": f, "mag": round(m, 1), "snr": round(s, 2)}
                 for f, m, s in scan_result]
                if scan_result else None),
            "results": jsonify(results),
        }, f, indent=2)

    log(f"\n  Saved: {npz_path}")
    log(f"  Saved: {json_path}")
    log("  Done.")


if __name__ == "__main__":
    main()
