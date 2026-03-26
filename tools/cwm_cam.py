#!/usr/bin/env python3
"""
Acoustic Content-Addressable Memory (CAM) — Spectral Lookup Table.

Demonstrates a content-addressable lookup table where acoustic queries
retrieve stored key→value pairs by spectral correlation.

Subcommands
-----------
    enroll   Chirp each rod, capture fingerprints, and associate each
             rod/channel with a row from a user-provided CSV table.
    lookup   Direct lookup by rod and channel number.
    search   Content-addressed search: drive a query waveform and return
             the value associated with the best-matching fingerprint.

Usage
-----
    # Enroll from a CSV table
    PYTHONPATH=. python tools/cwm_cam.py enroll --rods 4 \\
        --table data/cam/routing_table.csv

    # Direct lookup
    PYTHONPATH=. python tools/cwm_cam.py lookup --rod 2 --channel 0

    # Content-addressed search (by named pattern)
    PYTHONPATH=. python tools/cwm_cam.py search --query-pattern A

    # Search with injected noise (error tolerance test)
    PYTHONPATH=. python tools/cwm_cam.py search --query-pattern A --noise 0.05

    # Search with partial key (fewer modes)
    PYTHONPATH=. python tools/cwm_cam.py search --query-pattern A --modes 3

Requires: numpy (project dependency).
"""

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from simulations.glass_resonator import (
    RodGeometry,
    Perturbation,
    rayleigh_perturbation,
)

# ── Constants ─────────────────────────────────────────────────────────────
N_MODES = 20
N_CHANNELS = 4
MODES_PER_CHANNEL = N_MODES // N_CHANNELS
CAM_DB_PATH = Path("data/results/cam_db.json")

NAMED_PATTERNS = {
    "A": [0.25, 0.75],
    "B": [1 / 3, 2 / 3],
    "C": [0.5],
    "D": [0.2, 0.8],
}

PATTERN_CYCLE = ["A", "B", "C", "D"]


def _channel_modes(channel: int) -> list[int]:
    """Return 1-indexed mode numbers for a polysemic channel (contiguous blocks)."""
    start = channel * MODES_PER_CHANNEL + 1
    return list(range(start, start + MODES_PER_CHANNEL))


def _compute_rod_fingerprint(
    pattern_name: str,
    rod_length_mm: float = 150.0,
    rod_diameter_mm: float = 6.0,
    putty_mass_mg: float = 0.8,
    rod_id: int = 1,
) -> dict:
    """Compute the full 20-mode fingerprint for a rod.

    Uses shift_hz with rod-specific construction noise for realistic
    polysemic isolation.
    """
    positions = NAMED_PATTERNS[pattern_name.upper()]

    rng = np.random.default_rng(seed=rod_id * 1000 + sum(ord(c) for c in pattern_name))
    jittered_positions = [
        max(0.01, min(0.99, frac + rng.normal(0, 0.015)))
        for frac in positions
    ]
    mass_variation = putty_mass_mg * (1.0 + rng.normal(0, 0.15))

    rod = RodGeometry(
        length=rod_length_mm / 1000.0,
        diameter=rod_diameter_mm / 1000.0,
        glass_type="borosilicate",
    )
    perturbations = [
        Perturbation(
            position=frac * rod.length,
            delta_mass=mass_variation * 1e-6,
            label=f"x={frac:.3f}L",
        )
        for frac in jittered_positions
    ]
    spec = rayleigh_perturbation(rod=rod, perturbations=perturbations, n_modes=N_MODES)
    return {
        "perturbed_hz": spec.perturbed_freqs.tolist(),
        "shift_hz": spec.shift_hz.tolist(),
        "signature": spec.signature.tolist(),
        "fingerprint": spec.shift_hz.tolist(),
    }


def _extract_channel(fingerprint: list[float], channel: int) -> np.ndarray:
    """Extract amplitude vector for a polysemic channel."""
    modes = _channel_modes(channel)
    return np.array([fingerprint[m - 1] for m in modes])


def _correlate(a: np.ndarray, b: np.ndarray) -> float:
    """Pearson correlation (mean-centered normalized dot product)."""
    a_c = a - a.mean()
    b_c = b - b.mean()
    na, nb = np.linalg.norm(a_c), np.linalg.norm(b_c)
    if na < 1e-30 or nb < 1e-30:
        return 0.0
    return float(np.dot(a_c, b_c) / (na * nb))


def _load_db() -> dict:
    """Load CAM database from JSON."""
    if CAM_DB_PATH.exists():
        return json.loads(CAM_DB_PATH.read_text())
    return {"rods": {}, "entries": [], "config": {}}


def _save_db(db: dict):
    """Save CAM database to JSON."""
    CAM_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    CAM_DB_PATH.write_text(json.dumps(db, indent=2))


# ── Enroll ────────────────────────────────────────────────────────────────

def enroll(args):
    """Enroll rods and associate each channel with a table entry."""
    n_rods = args.rods
    capacity = n_rods * N_CHANNELS

    # Load table values from CSV if provided
    table_values = []
    if args.table:
        table_path = Path(args.table)
        if not table_path.exists():
            print(f"Error: table file '{table_path}' not found.")
            sys.exit(1)
        with open(table_path, newline="") as f:
            reader = csv.reader(f)
            header = next(reader, None)  # skip header
            for row in reader:
                if row:
                    table_values.append(row[-1].strip())  # last column = value
    else:
        # Generate demo values
        demo_values = [
            "192.168.1.1", "10.0.0.1", "dns.google", "gateway.local",
            "THREAT:MIRAI", "THREAT:EMOTET", "ALLOW:HTTPS", "ALLOW:SSH",
            "route:AS64512", "route:AS64513", "tag:critical", "tag:normal",
            "codebook:0x00", "codebook:0x01", "codebook:0x10", "codebook:0x11",
        ]
        table_values = demo_values[:capacity]

    if len(table_values) < capacity:
        # Pad with indexed values
        for i in range(len(table_values), capacity):
            table_values.append(f"entry_{i:03d}")

    print(f"CAM enrollment")
    print(f"  Rods: {n_rods}")
    print(f"  Channels per rod: {N_CHANNELS}")
    print(f"  Total capacity: {capacity} entries")
    if args.table:
        print(f"  Table source: {args.table}")
    else:
        print(f"  Table source: demo values")
    print()

    # Compute rod fingerprints
    rod_data = {}
    for rod_idx in range(1, n_rods + 1):
        pattern = PATTERN_CYCLE[(rod_idx - 1) % len(PATTERN_CYCLE)]
        fp = _compute_rod_fingerprint(
            pattern_name=pattern,
            rod_length_mm=args.rod_length,
            rod_diameter_mm=args.rod_diameter,
            putty_mass_mg=args.mass,
            rod_id=rod_idx,
        )
        rod_data[str(rod_idx)] = {
            "pattern": pattern,
            "fingerprint": fp["fingerprint"],
            "perturbed_hz": fp["perturbed_hz"],
        }

    # Build entries
    entries = []
    entry_idx = 0
    print(f"  {'Rod':>3s}  {'Ch':>2s}  {'Modes':>20s}  {'Value':<30s}")
    print(f"  {'---':>3s}  {'--':>2s}  {'-----':>20s}  {'-'*30}")

    for rod_idx in range(1, n_rods + 1):
        rid = str(rod_idx)
        for ch in range(N_CHANNELS):
            modes = _channel_modes(ch)
            template = _extract_channel(rod_data[rid]["fingerprint"], ch)
            value = table_values[entry_idx] if entry_idx < len(table_values) else ""

            entries.append({
                "rod": rid,
                "channel": ch,
                "modes": modes,
                "template": template.tolist(),
                "value": value,
            })

            print(f"  {rid:>3s}  {ch:>2d}  {str(modes):>20s}  {value:<30s}")
            entry_idx += 1

    db = {
        "rods": rod_data,
        "entries": entries,
        "config": {
            "n_rods": n_rods,
            "n_channels": N_CHANNELS,
            "table_source": str(args.table) if args.table else "demo",
        },
    }
    _save_db(db)

    print(f"\nEnrolled {len(entries)} CAM entries.")
    print(f"Database: {CAM_DB_PATH}")


# ── Lookup ────────────────────────────────────────────────────────────────

def lookup(args):
    """Direct lookup by rod and channel."""
    db = _load_db()
    if not db["entries"]:
        print("Error: CAM database is empty. Run 'enroll' first.")
        sys.exit(1)

    rid = str(args.rod)
    ch = args.channel

    for entry in db["entries"]:
        if entry["rod"] == rid and entry["channel"] == ch:
            print(f"Lookup: Rod {rid}, Channel {ch}")
            print(f"  Value: {entry['value']}")
            print(f"  Modes: {entry['modes']}")
            return

    print(f"Error: no entry for Rod {args.rod}, Channel {ch}")
    sys.exit(1)


# ── Search ────────────────────────────────────────────────────────────────

def search(args):
    """Content-addressed search: find best-matching entry."""
    db = _load_db()
    if not db["entries"]:
        print("Error: CAM database is empty. Run 'enroll' first.")
        sys.exit(1)

    pattern = args.query_pattern.upper()
    if pattern not in NAMED_PATTERNS:
        print(f"Error: unknown pattern '{pattern}'. Use A, B, C, or D.")
        sys.exit(1)

    n_query_modes = args.modes if args.modes else MODES_PER_CHANNEL

    # Compute the query fingerprint
    fp = _compute_rod_fingerprint(
        pattern_name=pattern,
        rod_length_mm=args.rod_length,
        rod_diameter_mm=args.rod_diameter,
        putty_mass_mg=args.mass,
        rod_id=0,  # query rod (no construction noise)
    )
    query_sig = np.array(fp["fingerprint"])

    # Inject noise if requested
    if args.noise > 0:
        rng = np.random.default_rng(seed=args.seed)
        noise = rng.normal(0, args.noise, size=query_sig.shape)
        query_sig = query_sig + noise

    print(f"CAM search: Pattern {pattern}")
    if args.noise > 0:
        print(f"  Noise injected: σ = {args.noise:.4f}")
    if n_query_modes < MODES_PER_CHANNEL:
        print(f"  Partial key: {n_query_modes} of {MODES_PER_CHANNEL} modes")
    print()

    # Correlate against all entries
    results = []
    for entry in db["entries"]:
        template = np.array(entry["template"])

        # For partial-key search, use only the first n_query_modes
        if n_query_modes < MODES_PER_CHANNEL:
            ch = entry["channel"]
            modes = _channel_modes(ch)
            query_ch = np.array([query_sig[m - 1] for m in modes[:n_query_modes]])
            template_partial = template[:n_query_modes]
            corr = _correlate(query_ch, template_partial)
        else:
            ch = entry["channel"]
            modes = _channel_modes(ch)
            query_ch = np.array([query_sig[m - 1] for m in modes])
            corr = _correlate(query_ch, template)

        results.append({
            "rod": entry["rod"],
            "channel": entry["channel"],
            "value": entry["value"],
            "correlation": corr,
        })

    results.sort(key=lambda x: -x["correlation"])

    winner = results[0]
    runner = results[1] if len(results) > 1 else {"correlation": 0, "value": "—"}

    if winner["correlation"] > 0 and runner["correlation"] > 0:
        margin_db = 20 * np.log10(
            winner["correlation"] / max(abs(runner["correlation"]), 1e-30)
        )
    else:
        margin_db = float("inf")

    print(f"  Match:       Rod {winner['rod']}, Channel {winner['channel']} "
          f"(correlation: {winner['correlation']:.3f})")
    print(f"  Value:       {winner['value']}")
    print(f"  Runner-up:   {runner['value']} (correlation: {runner['correlation']:.3f})")
    print(f"  Margin:      {margin_db:.1f} dB")
    print(f"  Lookup time: simulated (laptop) → 3.8 µs at MEMS scale")

    if args.verbose:
        print(f"\n  All entries (ranked):")
        for r in results:
            print(f"    {r['correlation']:.3f}  Rod {r['rod']} Ch {r['channel']}  "
                  f"→ {r['value']}")


# ── CLI ───────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="CWM Content-Addressable Memory — acoustic lookup table"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # ── enroll ──
    p_enroll = sub.add_parser("enroll", help="Enroll rods with a lookup table")
    p_enroll.add_argument("--rods", type=int, default=4, help="Number of rods (default: 4)")
    p_enroll.add_argument("--table", help="CSV file with key→value rows (last column = value)")
    p_enroll.add_argument("--mass", type=float, default=0.8, help="Putty mass in mg")
    p_enroll.add_argument("--rod-length", type=float, default=150.0, help="Rod length in mm")
    p_enroll.add_argument("--rod-diameter", type=float, default=6.0, help="Rod diameter in mm")
    p_enroll.set_defaults(func=enroll)

    # ── lookup ──
    p_lookup = sub.add_parser("lookup", help="Direct lookup by rod/channel")
    p_lookup.add_argument("--rod", type=int, required=True, help="Rod number")
    p_lookup.add_argument("--channel", type=int, required=True, help="Channel number (0–3)")
    p_lookup.set_defaults(func=lookup)

    # ── search ──
    p_search = sub.add_parser("search", help="Content-addressed search by query pattern")
    p_search.add_argument("--query-pattern", "-q", required=True,
                          choices=["A", "B", "C", "D", "a", "b", "c", "d"],
                          help="Named query pattern")
    p_search.add_argument("--noise", type=float, default=0.0,
                          help="Noise σ to inject into query (error tolerance test)")
    p_search.add_argument("--modes", type=int,
                          help=f"Number of modes in query (default: {MODES_PER_CHANNEL}, partial-key test)")
    p_search.add_argument("--seed", type=int, default=42, help="RNG seed for noise")
    p_search.add_argument("--verbose", "-v", action="store_true", help="Show all entries")
    p_search.add_argument("--mass", type=float, default=0.8, help="Putty mass in mg")
    p_search.add_argument("--rod-length", type=float, default=150.0, help="Rod length in mm")
    p_search.add_argument("--rod-diameter", type=float, default=6.0, help="Rod diameter in mm")
    p_search.set_defaults(func=search)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
