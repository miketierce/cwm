#!/usr/bin/env python3
"""Dual-channel AWG/preamp reference-cancel capture at 2048 samples.

Channel A is the OPA2134PA preamp output. Channel B is the AWG reference
from the BNC tee. The shorter 2048-sample block keeps dual-channel ps2000
captures reliable while preserving enough duration for a small window-width
sanity test.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import serial


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "results" / "awg"
PICO_LIB = "/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources/libps2000.dylib"

TIMEBASE = 7
DT = 1280e-9
SAMPLE_RATE = 1.0 / DT
N_SAMPLES = 2048
ADC_MAX = 32767.0

RANGE_BY_MV = {
    50: 2,
    100: 3,
    200: 4,
    500: 5,
    1000: 6,
    2000: 7,
}

DEFAULT_CANDIDATES = [
    11_400,
    19_000,
    23_900,
    29_200,
    29_900,
    33_200,
    34_500,
    35_000,
    37_000,
    45_000,
    47_800,
    49_600,
    56_200,
    58_500,
    68_200,
    89_400,
]


def parse_csv_ints(text: str) -> list[int]:
    return [int(part.strip()) for part in text.split(",") if part.strip()]


def configure_sig_gen(ps):
    ps.ps2000_set_sig_gen_built_in.argtypes = [
        ctypes.c_int16,
        ctypes.c_int32,
        ctypes.c_uint32,
        ctypes.c_int16,
        ctypes.c_float,
        ctypes.c_float,
        ctypes.c_float,
        ctypes.c_float,
        ctypes.c_int32,
        ctypes.c_uint32,
    ]
    ps.ps2000_set_sig_gen_built_in.restype = ctypes.c_int16


def open_scope(ps):
    for handle_id in range(1, 8):
        ps.ps2000_close_unit(handle_id)
    time.sleep(0.3)
    handle = ps.ps2000_open_unit()
    if handle <= 0:
        raise RuntimeError(f"Could not open PicoScope: handle={handle}")
    return handle


def awg_sine(ps, handle: int, freq_hz: float, uvpp: int):
    ps.ps2000_set_sig_gen_built_in(
        handle,
        ctypes.c_int32(0),
        ctypes.c_uint32(uvpp),
        ctypes.c_int16(0),
        ctypes.c_float(float(freq_hz)),
        ctypes.c_float(float(freq_hz)),
        ctypes.c_float(0.0),
        ctypes.c_float(0.0),
        ctypes.c_int32(0),
        ctypes.c_uint32(0),
    )


def awg_off(ps, handle: int):
    ps.ps2000_set_sig_gen_built_in(
        handle,
        ctypes.c_int32(0),
        ctypes.c_uint32(0),
        ctypes.c_int16(0),
        ctypes.c_float(1000.0),
        ctypes.c_float(1000.0),
        ctypes.c_float(0.0),
        ctypes.c_float(0.0),
        ctypes.c_int32(0),
        ctypes.c_uint32(0),
    )


def set_mux(port: str, channel: int) -> str:
    mux = serial.Serial(port, 9600, timeout=1)
    time.sleep(2)
    mux.reset_input_buffer()
    mux.write(f"{channel}\n".encode())
    time.sleep(0.05)
    response = mux.readline().decode(errors="replace").strip()
    mux.close()
    return response


def capture_dual(ps, handle: int, n_samples: int = N_SAMPLES) -> tuple[np.ndarray, np.ndarray, int]:
    buf_a = (ctypes.c_int16 * n_samples)()
    buf_b = (ctypes.c_int16 * n_samples)()
    overflow = ctypes.c_int16(0)
    ms = ctypes.c_int32(0)
    ps.ps2000_set_trigger(handle, 5, 0, 0, 0, 1)
    ps.ps2000_run_block(handle, n_samples, TIMEBASE, 1, ctypes.byref(ms))
    for _ in range(5000):
        if ps.ps2000_ready(handle):
            break
        time.sleep(0.001)
    else:
        ps.ps2000_stop(handle)
        raise RuntimeError("PicoScope dual capture timed out")

    got = ps.ps2000_get_values(
        handle,
        ctypes.byref(buf_a),
        ctypes.byref(buf_b),
        None,
        None,
        ctypes.byref(overflow),
        n_samples,
    )
    if got <= 0:
        raise RuntimeError(f"PicoScope returned {got} samples")
    return (
        np.array(buf_a[:got], dtype=np.float64),
        np.array(buf_b[:got], dtype=np.float64),
        int(overflow.value),
    )


def collect_dual(ps, handle: int, n_frames: int) -> tuple[np.ndarray, np.ndarray, list[int]]:
    frames_a = []
    frames_b = []
    overflows = []
    for _ in range(n_frames):
        frame_a, frame_b, overflow = capture_dual(ps, handle)
        frames_a.append(frame_a)
        frames_b.append(frame_b)
        overflows.append(overflow)
    return np.array(frames_a), np.array(frames_b), overflows


def centered(frames: np.ndarray) -> np.ndarray:
    return frames - np.mean(frames, axis=1, keepdims=True)


def reference_cancel(frames_a: np.ndarray, frames_b: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    a = centered(frames_a)
    b = centered(frames_b)
    denom = np.sum(b * b, axis=1)
    alpha = np.divide(np.sum(a * b, axis=1), denom, out=np.zeros_like(denom), where=denom > 1e-12)
    clean = a - alpha[:, None] * b
    return clean, alpha


def spectrum(frame: np.ndarray, nfft_multiplier: int = 4) -> tuple[np.ndarray, np.ndarray]:
    signal = frame - np.mean(frame)
    windowed = signal * np.hanning(len(signal))
    nfft = len(signal) * nfft_multiplier
    mag = np.abs(np.fft.rfft(windowed, n=nfft))
    freq = np.fft.rfftfreq(nfft, d=DT)
    return freq, mag


def average_spectrum(frames: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    mags = []
    freq_axis = None
    for frame in frames:
        freq_axis, mag = spectrum(frame)
        mags.append(mag)
    return freq_axis, np.mean(mags, axis=0)


def local_mag(freq_axis: np.ndarray, mag: np.ndarray, freq_hz: float, span_hz: float = 250.0) -> float:
    lo = np.searchsorted(freq_axis, max(0.0, freq_hz - span_hz))
    hi = np.searchsorted(freq_axis, freq_hz + span_hz)
    if hi <= lo:
        idx = int(np.argmin(np.abs(freq_axis - freq_hz)))
        return float(mag[idx])
    return float(np.max(mag[lo:hi]))


def counts_to_mv(raw: np.ndarray, range_mv: int) -> np.ndarray:
    return raw / ADC_MAX * float(range_mv)


def rms_mv(frames: np.ndarray, range_mv: int) -> float:
    centered_frames = centered(frames)
    return float(np.mean(np.sqrt(np.mean(counts_to_mv(centered_frames, range_mv) ** 2, axis=1))))


def frame_stats(frames: np.ndarray) -> dict:
    return {
        "min_count": int(np.min(frames)),
        "max_count": int(np.max(frames)),
        "max_abs_count": int(np.max(np.abs(frames))),
        "near_clip_samples": int(np.sum(np.abs(frames) >= 32_000)),
    }


def fwhm_near(freq_axis: np.ndarray, mag: np.ndarray, center_hz: float, search_hz: float = 5000.0):
    lo = np.searchsorted(freq_axis, max(0.0, center_hz - search_hz))
    hi = np.searchsorted(freq_axis, center_hz + search_hz)
    if hi <= lo + 4:
        return None
    local = mag[lo:hi]
    local_freq = freq_axis[lo:hi]
    peak_rel = int(np.argmax(local))
    peak = float(local[peak_rel])
    floor = float(np.percentile(local, 20))
    half = floor + 0.5 * (peak - floor)
    above = np.where(local >= half)[0]
    if len(above) < 2:
        return None
    return {
        "peak_hz": float(local_freq[peak_rel]),
        "peak_mag": peak,
        "floor_mag": floor,
        "fwhm_hz": float(local_freq[above[-1]] - local_freq[above[0]]),
    }


def top_bins(freq_axis: np.ndarray, mag_on: np.ndarray, mag_off: np.ndarray, drive_hz: float, n: int = 8) -> list[dict]:
    ratio = mag_on / np.maximum(mag_off, 1.0)
    mask = (freq_axis >= 1000.0) & (freq_axis <= 350000.0) & (np.abs(freq_axis - drive_hz) > 750.0)
    valid = np.where(mask)[0]
    if len(valid) == 0:
        return []
    chosen = valid[np.argsort(ratio[valid])[-n:]][::-1]
    rows = []
    for idx in chosen:
        multiple = freq_axis[idx] / drive_hz if drive_hz else 0.0
        nearest = int(round(multiple))
        rows.append({
            "freq_hz": float(freq_axis[idx]),
            "ratio": float(ratio[idx]),
            "on_mag": float(mag_on[idx]),
            "off_mag": float(mag_off[idx]),
            "nearest_harmonic": nearest,
            "harmonic_error_hz": float(abs(freq_axis[idx] - nearest * drive_hz)) if nearest >= 1 else None,
        })
    return rows


def window_rows(frames: np.ndarray, drive_hz: float, label: str) -> list[dict]:
    rows = []
    for win_n in [256, 512, 1024, N_SAMPLES]:
        mags = []
        freq_axis = None
        for frame in frames:
            segment = frame[:win_n]
            freq_axis, mag = spectrum(segment, nfft_multiplier=8)
            mags.append(mag)
        avg_mag = np.mean(mags, axis=0)
        width = fwhm_near(freq_axis, avg_mag, drive_hz)
        duration_s = win_n * DT
        rows.append({
            "label": label,
            "samples": win_n,
            "duration_ms": float(duration_s * 1000.0),
            "peak_hz": None if width is None else width["peak_hz"],
            "fwhm_hz": None if width is None else width["fwhm_hz"],
            "duration_x_fwhm": None if width is None else float(duration_s * width["fwhm_hz"]),
        })
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mux-channels", default="5,6")
    parser.add_argument("--mux-port", default="/dev/cu.usbserial-11310")
    parser.add_argument("--range-a-mv", type=int, default=200, choices=sorted(RANGE_BY_MV))
    parser.add_argument("--range-b-mv", type=int, default=50, choices=sorted(RANGE_BY_MV))
    parser.add_argument("--drive-uvpp", type=int, default=10_000)
    parser.add_argument("--settle-s", type=float, default=0.18)
    parser.add_argument("--scan-averages", type=int, default=8)
    parser.add_argument("--uncertainty-frames", type=int, default=24)
    parser.add_argument("--candidates", default=",".join(str(f) for f in DEFAULT_CANDIDATES))
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    mux_channels = parse_csv_ints(args.mux_channels)
    candidate_freqs = [float(v) for v in parse_csv_ints(args.candidates)]
    range_a_idx = RANGE_BY_MV[args.range_a_mv]
    range_b_idx = RANGE_BY_MV[args.range_b_mv]

    ps = ctypes.CDLL(PICO_LIB)
    configure_sig_gen(ps)
    handle = open_scope(ps)
    print(f"PicoScope handle: {handle}")
    print(
        f"Dual channel: N={N_SAMPLES}, duration={N_SAMPLES*DT*1000:.3f} ms, "
        f"Ch A +/-{args.range_a_mv} mV, Ch B +/-{args.range_b_mv} mV"
    )

    noise_rows = []
    scan_rows = []
    noise_a_stack = []
    noise_b_stack = []
    scan_a_stack = []
    scan_b_stack = []
    scan_clean_stack = []

    try:
        ps.ps2000_set_channel(handle, 0, 1, 1, range_a_idx)
        ps.ps2000_set_channel(handle, 1, 1, 1, range_b_idx)
        awg_off(ps, handle)
        time.sleep(0.3)

        for mux_channel in mux_channels:
            response = set_mux(args.mux_port, mux_channel)
            print(f"\n=== Mux {mux_channel} ({response}) ===")

            awg_off(ps, handle)
            time.sleep(0.25)
            noise_a, noise_b, noise_overflows = collect_dual(ps, handle, 12)
            noise_clean, noise_alpha = reference_cancel(noise_a, noise_b)
            freq_axis, noise_mag_a = average_spectrum(noise_a)
            _, noise_mag_b = average_spectrum(noise_b)
            _, noise_mag_clean = average_spectrum(noise_clean)
            noise_index = len(noise_a_stack)
            noise_a_stack.append(noise_a)
            noise_b_stack.append(noise_b)
            noise_rows.append({
                "mux": mux_channel,
                "frame_index": noise_index,
                "overflow": int(max(noise_overflows)),
                "rms_a_mv": rms_mv(noise_a, args.range_a_mv),
                "rms_b_mv": rms_mv(noise_b, args.range_b_mv),
                "rms_clean_counts": float(np.mean(np.sqrt(np.mean(noise_clean ** 2, axis=1)))),
                "alpha_mean": float(np.mean(noise_alpha)),
                "alpha_std": float(np.std(noise_alpha)),
                "a_stats": frame_stats(noise_a),
                "b_stats": frame_stats(noise_b),
            })
            print(
                f"  AWG-off A={noise_rows[-1]['rms_a_mv']:.3f} mV RMS, "
                f"B={noise_rows[-1]['rms_b_mv']:.3f} mV RMS, ov={max(noise_overflows)}"
            )

            for drive_hz in candidate_freqs:
                awg_sine(ps, handle, drive_hz, args.drive_uvpp)
                time.sleep(args.settle_s)
                frames_a, frames_b, overflows = collect_dual(ps, handle, args.scan_averages)
                clean, alpha = reference_cancel(frames_a, frames_b)
                _, mag_a = average_spectrum(frames_a)
                _, mag_b = average_spectrum(frames_b)
                _, mag_clean = average_spectrum(clean)
                target_a = local_mag(freq_axis, mag_a, drive_hz)
                target_b = local_mag(freq_axis, mag_b, drive_hz)
                target_clean = local_mag(freq_axis, mag_clean, drive_hz)
                noise_a_mag = local_mag(freq_axis, noise_mag_a, drive_hz)
                noise_b_mag = local_mag(freq_axis, noise_mag_b, drive_hz)
                noise_clean_mag = local_mag(freq_axis, noise_mag_clean, drive_hz)
                frame_index = len(scan_a_stack)
                scan_a_stack.append(frames_a)
                scan_b_stack.append(frames_b)
                scan_clean_stack.append(clean)
                row = {
                    "mux": mux_channel,
                    "drive_hz": float(drive_hz),
                    "frame_index": frame_index,
                    "overflow": int(max(overflows)),
                    "rms_a_mv": rms_mv(frames_a, args.range_a_mv),
                    "rms_b_mv": rms_mv(frames_b, args.range_b_mv),
                    "rms_clean_counts": float(np.mean(np.sqrt(np.mean(clean ** 2, axis=1)))),
                    "alpha_mean": float(np.mean(alpha)),
                    "alpha_std": float(np.std(alpha)),
                    "carrier_mag_a": float(target_a),
                    "carrier_mag_b": float(target_b),
                    "carrier_mag_clean": float(target_clean),
                    "ratio_a": float(target_a / max(noise_a_mag, 1.0)),
                    "ratio_b": float(target_b / max(noise_b_mag, 1.0)),
                    "ratio_clean": float(target_clean / max(noise_clean_mag, 1.0)),
                    "clean_vs_a_carrier_db": float(20 * np.log10(max(target_clean, 1.0) / max(target_a, 1.0))),
                    "top_a_bins": top_bins(freq_axis, mag_a, noise_mag_a, drive_hz),
                    "top_clean_bins": top_bins(freq_axis, mag_clean, noise_mag_clean, drive_hz),
                    "a_stats": frame_stats(frames_a),
                    "b_stats": frame_stats(frames_b),
                }
                scan_rows.append(row)
                print(
                    f"  {drive_hz:8.0f} Hz | A={row['ratio_a']:6.2f}x | "
                    f"clean={row['ratio_clean']:6.2f}x | "
                    f"cancel={row['clean_vs_a_carrier_db']:6.1f} dB | ov={max(overflows)}"
                )

        awg_off(ps, handle)

        valid_rows = [r for r in scan_rows if r["overflow"] == 0]
        best = max(valid_rows or scan_rows, key=lambda r: r["ratio_a"])
        best_mux = int(best["mux"])
        best_freq = float(best["drive_hz"])
        print("\n=== Selected Preparation ===")
        print(
            f"  mux={best_mux}, drive={best_freq:.0f} Hz, "
            f"A ratio={best['ratio_a']:.2f}x, clean ratio={best['ratio_clean']:.2f}x"
        )

        response = set_mux(args.mux_port, best_mux)
        print(f"  mux set: {response}")
        awg_sine(ps, handle, best_freq, args.drive_uvpp)
        time.sleep(max(args.settle_s, 0.35))
        uncertainty_a, uncertainty_b, uncertainty_overflows = collect_dual(ps, handle, args.uncertainty_frames)
        uncertainty_clean, uncertainty_alpha = reference_cancel(uncertainty_a, uncertainty_b)

        uncertainty_rows = []
        for label, frames in [("A_raw", uncertainty_a), ("B_ref", uncertainty_b), ("A_refcancel", uncertainty_clean)]:
            rows = window_rows(frames, best_freq, label)
            uncertainty_rows.extend(rows)
            print(f"\n  {label}")
            for row in rows:
                fwhm_txt = "n/a" if row["fwhm_hz"] is None else f"{row['fwhm_hz']:.1f} Hz"
                prod_txt = "n/a" if row["duration_x_fwhm"] is None else f"{row['duration_x_fwhm']:.3f}"
                print(
                    f"    window={row['duration_ms']:5.2f} ms | "
                    f"FWHM={fwhm_txt:>9} | T*dF={prod_txt}"
                )

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        stem = f"awg_preamp_refcancel_2048_{timestamp}"
        npz_path = OUT_DIR / f"{stem}.npz"
        json_path = OUT_DIR / f"{stem}.json"

        np.savez_compressed(
            npz_path,
            candidate_freqs=np.array(candidate_freqs, dtype=np.float64),
            mux_channels=np.array(mux_channels, dtype=np.int16),
            noise_rows_json=np.array(json.dumps(noise_rows)),
            scan_rows_json=np.array(json.dumps(scan_rows)),
            uncertainty_rows_json=np.array(json.dumps(uncertainty_rows)),
            noise_a=np.array(noise_a_stack, dtype=np.float64),
            noise_b=np.array(noise_b_stack, dtype=np.float64),
            scan_a=np.array(scan_a_stack, dtype=np.float64),
            scan_b=np.array(scan_b_stack, dtype=np.float64),
            scan_clean=np.array(scan_clean_stack, dtype=np.float64),
            uncertainty_a=uncertainty_a,
            uncertainty_b=uncertainty_b,
            uncertainty_clean=uncertainty_clean,
            uncertainty_overflows=np.array(uncertainty_overflows, dtype=np.int16),
            uncertainty_alpha=uncertainty_alpha,
            sample_rate=np.array(SAMPLE_RATE),
            dt=np.array(DT),
            n_samples=np.array(N_SAMPLES),
            range_a_mv=np.array(args.range_a_mv),
            range_b_mv=np.array(args.range_b_mv),
            drive_uvpp=np.array(args.drive_uvpp),
        )

        summary = {
            "timestamp": timestamp,
            "script": "tools/awg_preamp_refcancel_2048.py",
            "hardware_state": "Pico AWG drive tee to Ch B, preamp RX on Ch A, DDS disconnected/dead",
            "n_samples": N_SAMPLES,
            "duration_ms": N_SAMPLES * DT * 1000.0,
            "range_a_mv": args.range_a_mv,
            "range_b_mv": args.range_b_mv,
            "drive_uvpp": args.drive_uvpp,
            "mux_channels": mux_channels,
            "candidate_freqs": candidate_freqs,
            "noise_rows": noise_rows,
            "scan_rows": scan_rows,
            "best": best,
            "uncertainty_rows": uncertainty_rows,
            "uncertainty_alpha_mean": float(np.mean(uncertainty_alpha)),
            "uncertainty_alpha_std": float(np.std(uncertainty_alpha)),
            "data_file": str(npz_path.relative_to(ROOT)),
        }
        json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

        print("\n=== Saved ===")
        print(f"  {npz_path.relative_to(ROOT)}")
        print(f"  {json_path.relative_to(ROOT)}")
        return 0
    finally:
        try:
            awg_off(ps, handle)
        except Exception:
            pass
        ps.ps2000_stop(handle)
        ps.ps2000_close_unit(handle)


if __name__ == "__main__":
    raise SystemExit(main())