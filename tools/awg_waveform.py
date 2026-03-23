#!/usr/bin/env python3
"""
PicoScope AWG waveform generator for CWM experiments.

Computes the spectral fingerprint of a perturbation pattern (e.g. Pattern A)
and synthesizes a multi-tone arbitrary waveform suitable for loading into the
PicoScope 2204A's AWG via PicoScope 7 software.

Output formats
--------------
- CSV: one sample per line, normalised to ±1.  Import via PicoScope 7 →
  AWG → Arbitrary → File → Import CSV.
- WAV (16-bit PCM): can be imported directly by some PicoScope versions
  or used with the picosdk-python-wrappers for programmatic control.

Usage
-----
    # Default: Pattern A (L/4 + 3L/4), 5 modes, 0.1 V/tone
    python tools/awg_waveform.py

    # Custom perturbation positions (fractions of L)
    python tools/awg_waveform.py --positions 0.333 0.667 --modes 5

    # All four guide patterns
    python tools/awg_waveform.py --pattern A
    python tools/awg_waveform.py --pattern B
    python tools/awg_waveform.py --pattern C
    python tools/awg_waveform.py --pattern D

    # Specify output directory
    python tools/awg_waveform.py --pattern A -o output/

Requires: numpy (already a project dependency).
Optional: scipy (for WAV export — falls back to CSV-only if absent).
"""

import argparse
import sys
from pathlib import Path

import numpy as np

# Allow running from repo root: PYTHONPATH=. python tools/awg_waveform.py
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from simulations.glass_resonator import (
    RodGeometry,
    Perturbation,
    rayleigh_perturbation,
)

# ── PicoScope 2204A AWG constraints ──────────────────────────────────────
AWG_SAMPLE_RATE = 1_000_000   # 1 MS/s (2204A max AWG sample rate)
AWG_BUFFER_MAX = 8192         # 2204A AWG buffer: 4096 or 8192 samples
AWG_VMAX = 2.0                # ±2 V max output
AWG_RESOLUTION = 8            # 8-bit DAC

# ── Named perturbation patterns from Template T.3 ────────────────────────
NAMED_PATTERNS = {
    "A": {"fractions": [0.25, 0.75],   "label": "Quarter-points L/4 + 3L/4"},
    "B": {"fractions": [1/3, 2/3],     "label": "Third-points L/3 + 2L/3"},
    "C": {"fractions": [0.5],          "label": "Midpoint L/2"},
    "D": {"fractions": [0.2, 0.8],     "label": "Fifth-points L/5 + 4L/5"},
}


def compute_fingerprint(
    positions_frac: list[float],
    n_modes: int = 5,
    putty_mass_mg: float = 0.8,
    rod_length_mm: float = 150.0,
    rod_diameter_mm: float = 6.0,
    glass_type: str = "borosilicate",
):
    """
    Compute the perturbed mode frequencies for a given pattern.

    Parameters
    ----------
    positions_frac : list of float
        Perturbation positions as fractions of rod length (e.g. [0.25, 0.75]).
    n_modes : int
        Number of modes to include in the fingerprint.
    putty_mass_mg : float
        Mass of each putty pellet in milligrams.
    rod_length_mm : float
        Rod length in millimeters.
    rod_diameter_mm : float
        Rod diameter in millimeters.
    glass_type : str
        Glass type key from the simulation database.

    Returns
    -------
    dict with keys:
        unperturbed_hz  : array of unperturbed frequencies [Hz]
        perturbed_hz    : array of perturbed frequencies [Hz]
        shift_hz        : array of frequency shifts [Hz]
        shift_ppm       : array of shifts in ppm
    """
    rod = RodGeometry(
        length=rod_length_mm / 1000.0,
        diameter=rod_diameter_mm / 1000.0,
        glass_type=glass_type,
    )
    perturbations = [
        Perturbation(
            position=frac * rod.length,
            delta_mass=putty_mass_mg * 1e-6,
            label=f"x={frac:.3f}L",
        )
        for frac in positions_frac
    ]
    spec = rayleigh_perturbation(rod=rod, perturbations=perturbations, n_modes=n_modes)

    return {
        "unperturbed_hz": spec.unperturbed_freqs,
        "perturbed_hz": spec.perturbed_freqs,
        "shift_hz": spec.shift_hz,
        "shift_ppm": spec.shifts * 1e6,
        "mode_numbers": spec.mode_numbers,
    }


def synthesize_multitone(
    frequencies_hz: np.ndarray,
    amplitude_per_tone_v: float = 0.1,
    sample_rate: int = AWG_SAMPLE_RATE,
    n_samples: int = AWG_BUFFER_MAX,
):
    """
    Synthesize a multi-tone waveform buffer for the PicoScope AWG.

    The waveform is a sum of sinusoids at the given frequencies, each with
    equal amplitude.  The buffer is designed to loop seamlessly on the AWG.

    Parameters
    ----------
    frequencies_hz : array-like
        Tone frequencies in Hz.
    amplitude_per_tone_v : float
        Peak amplitude of each tone in volts.
    sample_rate : int
        AWG sample rate in Hz.
    n_samples : int
        Number of samples in the AWG buffer.

    Returns
    -------
    dict with keys:
        samples_v     : float64 array of voltage values
        samples_norm  : float64 array normalised to ±1 (for CSV export)
        sample_rate   : int
        duration_s    : float
        peak_v        : float (actual peak of the composite waveform)
        frequencies   : array of frequencies used
    """
    frequencies_hz = np.asarray(frequencies_hz, dtype=np.float64)
    t = np.arange(n_samples) / sample_rate

    # Sum equal-amplitude sinusoids
    waveform = np.zeros(n_samples, dtype=np.float64)
    for f in frequencies_hz:
        waveform += amplitude_per_tone_v * np.sin(2.0 * np.pi * f * t)

    peak_v = np.max(np.abs(waveform))

    # Normalise to ±1 for CSV import (PicoScope scales by its amplitude setting)
    if peak_v > 0:
        normalised = waveform / peak_v
    else:
        normalised = waveform

    return {
        "samples_v": waveform,
        "samples_norm": normalised,
        "sample_rate": sample_rate,
        "duration_s": n_samples / sample_rate,
        "peak_v": peak_v,
        "frequencies": frequencies_hz,
    }


def export_csv(samples_norm: np.ndarray, path: Path):
    """Export normalised samples as a single-column CSV for PicoScope import."""
    np.savetxt(str(path), samples_norm, fmt="%.8f", header="amplitude", comments="")


def export_wav(samples_norm: np.ndarray, sample_rate: int, path: Path):
    """Export as 16-bit PCM WAV file."""
    try:
        import wave
        import struct
    except ImportError:
        print(f"  (wave module not available; skipping WAV export)")
        return

    # Scale to 16-bit signed integer range
    int16_max = 32767
    int_samples = np.clip(samples_norm * int16_max, -32768, 32767).astype(np.int16)

    with wave.open(str(path), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sample_rate)
        wf.writeframes(int_samples.tobytes())


def generate_query_waveform(
    pattern: str = "A",
    n_modes: int = 5,
    amplitude_v: float = 0.1,
    putty_mass_mg: float = 0.8,
    output_dir: str = ".",
    rod_length_mm: float = 150.0,
    rod_diameter_mm: float = 6.0,
):
    """
    End-to-end generation: compute fingerprint → synthesize → export.

    Parameters
    ----------
    pattern : str
        Pattern name (A, B, C, or D) or "custom".
    n_modes : int
        Number of modes in the query.
    amplitude_v : float
        Per-tone amplitude in volts.
    putty_mass_mg : float
        Putty pellet mass in mg (per pellet).
    output_dir : str
        Directory for output files.
    rod_length_mm, rod_diameter_mm : float
        Rod geometry.

    Returns
    -------
    dict with fingerprint data, waveform data, and file paths.
    """
    pat = NAMED_PATTERNS[pattern.upper()]
    positions = pat["fractions"]
    label = pat["label"]

    print(f"Pattern {pattern.upper()}: {label}")
    print(f"  Perturbation positions: {[f'{p*100:.1f}%' for p in positions]}")
    print(f"  Putty mass: {putty_mass_mg} mg per pellet ({len(positions)} pellets)")
    print(f"  Rod: {rod_length_mm} mm × {rod_diameter_mm} mm borosilicate")
    print()

    # ── Step 1: Compute fingerprint ──
    fp = compute_fingerprint(
        positions_frac=positions,
        n_modes=n_modes,
        putty_mass_mg=putty_mass_mg,
        rod_length_mm=rod_length_mm,
        rod_diameter_mm=rod_diameter_mm,
    )

    print("Mode frequencies (Hz):")
    print(f"  {'Mode':>4s}  {'Unperturbed':>12s}  {'Perturbed':>12s}  {'Shift':>10s}  {'ppm':>8s}")
    print(f"  {'----':>4s}  {'----------':>12s}  {'---------':>12s}  {'-----':>10s}  {'---':>8s}")
    for i in range(n_modes):
        print(
            f"  {fp['mode_numbers'][i]:4d}  "
            f"{fp['unperturbed_hz'][i]:12.1f}  "
            f"{fp['perturbed_hz'][i]:12.1f}  "
            f"{fp['shift_hz'][i]:10.2f}  "
            f"{fp['shift_ppm'][i]:8.1f}"
        )
    print()

    # ── Step 2: Synthesize waveform ──
    wf = synthesize_multitone(
        frequencies_hz=fp["perturbed_hz"],
        amplitude_per_tone_v=amplitude_v,
    )

    n_tones = len(fp["perturbed_hz"])
    print(f"Waveform synthesis:")
    print(f"  Tones: {n_tones} × {amplitude_v} V = {n_tones * amplitude_v:.1f} V max theoretical")
    print(f"  Actual peak: {wf['peak_v']:.3f} V")
    print(f"  Buffer: {len(wf['samples_norm'])} samples at {wf['sample_rate']/1e6:.1f} MS/s")
    print(f"  Duration: {wf['duration_s']*1000:.2f} ms (loops continuously on AWG)")
    print()

    # ── Step 3: Export ──
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    csv_path = out / f"query_{pattern.upper()}.csv"
    wav_path = out / f"query_{pattern.upper()}.wav"

    export_csv(wf["samples_norm"], csv_path)
    print(f"  CSV → {csv_path}")

    export_wav(wf["samples_norm"], wf["sample_rate"], wav_path)
    print(f"  WAV → {wav_path}")

    print()
    print("PicoScope 7 import steps:")
    print(f"  1. Open PicoScope 7 → Tools → Signal Generator")
    print(f"  2. Wave Type → Arbitrary")
    print(f"  3. Click 'Import' → select '{csv_path.name}'")
    print(f"  4. Set Amplitude to {wf['peak_v']:.3f} Vpp (matches {amplitude_v} V per tone)")
    print(f"  5. Set Sample Rate to {wf['sample_rate']/1e6:.0f} MS/s")
    print(f"  6. Click 'Start' — the AWG now outputs Query {pattern.upper()}")

    return {
        "fingerprint": fp,
        "waveform": wf,
        "csv_path": str(csv_path),
        "wav_path": str(wav_path),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Generate PicoScope AWG waveforms for CWM experiments"
    )
    parser.add_argument(
        "--pattern", "-p", default="A",
        choices=["A", "B", "C", "D", "a", "b", "c", "d"],
        help="Named perturbation pattern (default: A)",
    )
    parser.add_argument(
        "--modes", "-m", type=int, default=5,
        help="Number of modes in the query (default: 5)",
    )
    parser.add_argument(
        "--amplitude", "-a", type=float, default=0.1,
        help="Per-tone amplitude in volts (default: 0.1)",
    )
    parser.add_argument(
        "--mass", type=float, default=0.8,
        help="Putty pellet mass in mg (default: 0.8)",
    )
    parser.add_argument(
        "--output", "-o", default=".",
        help="Output directory (default: current directory)",
    )
    parser.add_argument(
        "--rod-length", type=float, default=150.0,
        help="Rod length in mm (default: 150)",
    )
    parser.add_argument(
        "--rod-diameter", type=float, default=6.0,
        help="Rod diameter in mm (default: 6)",
    )
    parser.add_argument(
        "--all", action="store_true",
        help="Generate waveforms for all four patterns (A, B, C, D)",
    )
    args = parser.parse_args()

    patterns = ["A", "B", "C", "D"] if args.all else [args.pattern.upper()]

    for pat in patterns:
        generate_query_waveform(
            pattern=pat,
            n_modes=args.modes,
            amplitude_v=args.amplitude,
            putty_mass_mg=args.mass,
            output_dir=args.output,
            rod_length_mm=args.rod_length,
            rod_diameter_mm=args.rod_diameter,
        )
        if pat != patterns[-1]:
            print("=" * 60)
            print()


if __name__ == "__main__":
    main()
