#!/usr/bin/env python3
"""
Acoustic Password Vault — Polysemic Packed-Array Credential Store.

Demonstrates a physically unclonable function (PUF) security device where
each glass rod stores 4 independent credentials via polysemic readout.

Subcommands
-----------
    enroll   Chirp a rod, capture its fingerprint, split into 4 polysemic
             channels, and save templates to the vault database.
    verify   Query a rod, correlate against stored template, and return
             a pass/fail authentication decision.
    status   Print the current vault contents.

Usage
-----
    # Enroll rod 1 (simulation mode — no hardware required)
    PYTHONPATH=. python tools/cwm_vault.py enroll --rod 1

    # Enroll rod 1 with custom pattern
    PYTHONPATH=. python tools/cwm_vault.py enroll --rod 1 --pattern A

    # Assign labels to channels
    PYTHONPATH=. python tools/cwm_vault.py enroll --rod 1 --labels email bank laptop vpn

    # Verify a credential
    PYTHONPATH=. python tools/cwm_vault.py verify --label email

    # Verify with injected noise (attack test)
    PYTHONPATH=. python tools/cwm_vault.py verify --label email --noise 0.02

    # Show vault contents
    PYTHONPATH=. python tools/cwm_vault.py status

Requires: numpy (project dependency).
"""

import argparse
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
N_MODES = 20               # Total modes measured per rod
N_CHANNELS = 4             # Polysemic channels
MODES_PER_CHANNEL = N_MODES // N_CHANNELS  # 5 modes per channel
CORRELATION_THRESHOLD = 0.85
VAULT_DB_PATH = Path("data/results/vault_db.json")

# Named perturbation patterns (same as awg_waveform.py)
NAMED_PATTERNS = {
    "A": [0.25, 0.75],
    "B": [1 / 3, 2 / 3],
    "C": [0.5],
    "D": [0.2, 0.8],
}

DEFAULT_ROD_PATTERNS = {
    1: "A",
    2: "B",
    3: "C",
    4: "D",
    5: "A",
    6: "B",
    7: "C",
    8: "D",
    9: "A",
    10: "B",
}


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
    """Compute the full 20-mode fingerprint for a rod with a named pattern.

    Uses shift_hz as the fingerprint basis (the actual perturbation signal
    measured by PicoScope FFT).  Adds rod-specific construction noise to
    simulate real-world position jitter (±0.5 mm) and mass variation (±5%),
    seeded by rod_id for reproducibility.
    """
    positions = NAMED_PATTERNS[pattern_name.upper()]

    # Simulate construction imprecision: position jitter and mass variation
    # Real hand-placement of putty pellets has ~±2 mm position error on
    # a 150 mm rod and ~±15% mass variation between pellets.
    rng = np.random.default_rng(seed=rod_id * 1000 + sum(ord(c) for c in pattern_name))
    jittered_positions = [
        max(0.01, min(0.99, frac + rng.normal(0, 0.015)))  # ±2 mm on 150 mm rod
        for frac in positions
    ]
    mass_variation = putty_mass_mg * (1.0 + rng.normal(0, 0.15))  # ±15% mass

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

    # Use shift_hz as the primary fingerprint — this is the actual
    # perturbation signal that distinguishes patterns and channels.
    return {
        "perturbed_hz": spec.perturbed_freqs.tolist(),
        "shift_hz": spec.shift_hz.tolist(),
        "signature": spec.signature.tolist(),
        "fingerprint": spec.shift_hz.tolist(),
    }


def _extract_channel(fingerprint: list[float], channel: int) -> np.ndarray:
    """Extract amplitude vector for a polysemic channel from a full fingerprint."""
    modes = _channel_modes(channel)
    return np.array([fingerprint[m - 1] for m in modes])


def _correlate(a: np.ndarray, b: np.ndarray) -> float:
    """Pearson correlation between two vectors (mean-centered, then normalized).

    This measures the similarity of the shift *pattern shape* while being
    invariant to overall magnitude — the physically meaningful comparison
    for polysemic readout.
    """
    a_c = a - a.mean()
    b_c = b - b.mean()
    na = np.linalg.norm(a_c)
    nb = np.linalg.norm(b_c)
    if na < 1e-30 or nb < 1e-30:
        return 0.0
    return float(np.dot(a_c, b_c) / (na * nb))


def _load_vault() -> dict:
    """Load vault database from JSON."""
    if VAULT_DB_PATH.exists():
        return json.loads(VAULT_DB_PATH.read_text())
    return {"rods": {}, "labels": {}}


def _save_vault(vault: dict):
    """Save vault database to JSON."""
    VAULT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    VAULT_DB_PATH.write_text(json.dumps(vault, indent=2))


# ── Enroll ────────────────────────────────────────────────────────────────

def enroll(args):
    """Enroll a rod into the vault, creating 4 polysemic channel templates."""
    rod_id = str(args.rod)
    pattern = args.pattern or DEFAULT_ROD_PATTERNS.get(args.rod, "A")

    print(f"Enrolling Rod {rod_id} (Pattern {pattern.upper()})")
    print(f"  Rod: {args.rod_length} mm × {args.rod_diameter} mm borosilicate")
    print(f"  Putty mass: {args.mass} mg per pellet")
    print(f"  Polysemic channels: {N_CHANNELS} ({MODES_PER_CHANNEL} modes each)")
    print()

    fp = _compute_rod_fingerprint(
        pattern_name=pattern,
        rod_length_mm=args.rod_length,
        rod_diameter_mm=args.rod_diameter,
        putty_mass_mg=args.mass,
        rod_id=args.rod,
    )

    vault = _load_vault()
    vault["rods"][rod_id] = {
        "pattern": pattern.upper(),
        "fingerprint": fp["fingerprint"],
        "perturbed_hz": fp["perturbed_hz"],
        "channels": {},
    }

    default_labels = [f"rod{rod_id}_ch{c}" for c in range(N_CHANNELS)]
    labels = args.labels if args.labels and len(args.labels) == N_CHANNELS else default_labels

    print(f"  {'Channel':>7s}  {'Modes':>20s}  {'Label':>16s}  {'Norm':>8s}")
    print(f"  {'-------':>7s}  {'-----':>20s}  {'-----':>16s}  {'----':>8s}")

    for ch in range(N_CHANNELS):
        modes = _channel_modes(ch)
        template = _extract_channel(fp["fingerprint"], ch)
        label = labels[ch]

        vault["rods"][rod_id]["channels"][str(ch)] = {
            "label": label,
            "modes": modes,
            "template": template.tolist(),
        }
        vault["labels"][label] = {"rod": rod_id, "channel": ch}

        norm = np.linalg.norm(template)
        print(f"  {ch:7d}  {str(modes):>20s}  {label:>16s}  {norm:8.4f}")

    _save_vault(vault)
    print()
    print(f"Enrolled {N_CHANNELS} credentials for Rod {rod_id}.")
    print(f"Total vault credentials: {len(vault['labels'])}")
    print(f"Database: {VAULT_DB_PATH}")

    # Show cross-channel isolation
    print()
    print("Polysemic isolation (cross-channel correlation):")
    for i in range(N_CHANNELS):
        ti = _extract_channel(fp["fingerprint"], i)
        for j in range(i + 1, N_CHANNELS):
            tj = _extract_channel(fp["fingerprint"], j)
            xcorr = _correlate(ti, tj)
            print(f"  Ch {i} vs Ch {j}: {xcorr:+.4f}")


# ── Verify ────────────────────────────────────────────────────────────────

def verify(args):
    """Verify a credential by label.

    Authentication uses the full 20-mode rod fingerprint (not just the
    5-mode channel subset) for maximum discrimination.  The channel index
    is used only to select which credential label we're authenticating.
    """
    vault = _load_vault()

    if args.label not in vault["labels"]:
        print(f"Error: label '{args.label}' not found in vault.")
        print(f"Available labels: {list(vault['labels'].keys())}")
        sys.exit(1)

    entry = vault["labels"][args.label]
    rod_id = entry["rod"]
    channel = entry["channel"]
    rod_data = vault["rods"][rod_id]

    print(f"Verifying: '{args.label}'")
    print(f"  Expected: Rod {rod_id}, Channel {channel} (Pattern {rod_data['pattern']})")
    print()

    # Simulate a fresh measurement (same rod, with optional noise)
    fp = _compute_rod_fingerprint(
        pattern_name=rod_data["pattern"],
        rod_length_mm=args.rod_length,
        rod_diameter_mm=args.rod_diameter,
        putty_mass_mg=args.mass,
        rod_id=int(rod_id),
    )
    measured = np.array(fp["fingerprint"])

    # Add noise if requested (simulates environmental drift or attack)
    if args.noise > 0:
        rng = np.random.default_rng(seed=args.seed)
        noise = rng.normal(0, args.noise, size=measured.shape)
        measured = measured + noise
        print(f"  Noise injected: σ = {args.noise:.4f}")

    # Authenticate using full 20-mode fingerprint against enrolled template
    enrolled_fp = np.array(rod_data["fingerprint"])
    corr = _correlate(measured, enrolled_fp)
    passed = corr >= CORRELATION_THRESHOLD

    # Discrimination: compare against ALL other rods' full fingerprints
    wrong_corrs = []
    for other_rod_id, other_rod_data in vault["rods"].items():
        if other_rod_id == rod_id:
            continue
        other_fp = np.array(other_rod_data["fingerprint"])
        wrong_corrs.append((_correlate(measured, other_fp), other_rod_id))

    if wrong_corrs:
        best_wrong_corr, best_wrong_rod = max(wrong_corrs, key=lambda x: x[0])
    else:
        best_wrong_corr, best_wrong_rod = 0.0, "—"

    if best_wrong_corr > 0 and corr > 0:
        margin_db = 20 * np.log10(corr / max(abs(best_wrong_corr), 1e-30))
    else:
        margin_db = float("inf")

    status = "PASS ✓" if passed else "FAIL ✗"
    print(f"  Rod authentication (20 modes):")
    print(f"    Correlation:        {corr:.4f}")
    print(f"    Threshold:          {CORRELATION_THRESHOLD:.2f}")
    print(f"    Best wrong rod:     {best_wrong_corr:.4f} (Rod {best_wrong_rod})")
    print(f"    Discrimination:     {margin_db:.1f} dB")
    print(f"    Result:             {status}")

    # Also show channel-level isolation for educational value
    ch_template = np.array(rod_data["channels"][str(channel)]["template"])
    query_ch = _extract_channel(measured.tolist(), channel)
    ch_corr = _correlate(query_ch, ch_template)
    ch_wrong = []
    for ch_id in range(N_CHANNELS):
        if ch_id == channel:
            continue
        wt = np.array(rod_data["channels"][str(ch_id)]["template"])
        ch_wrong.append(_correlate(query_ch, wt))
    best_ch_wrong = max(ch_wrong) if ch_wrong else 0.0

    print(f"  Channel isolation (polysemic, {MODES_PER_CHANNEL} modes):")
    print(f"    Ch {channel} correlation: {ch_corr:.4f}")
    print(f"    Best wrong channel: {best_ch_wrong:.4f}")

    if args.wrong_rod:
        print()
        print("Attack test: wrong-rod correlation matrix (full 20-mode)")
        for other_rod_id, other_rod_data in vault["rods"].items():
            if other_rod_id == rod_id:
                continue
            fp2 = _compute_rod_fingerprint(pattern_name=other_rod_data["pattern"], rod_id=int(other_rod_id))
            c = _correlate(np.array(fp2["fingerprint"]), enrolled_fp)
            print(f"    Rod {other_rod_id} ({other_rod_data['pattern']}): {c:.4f}")


# ── Status ────────────────────────────────────────────────────────────────

def status(args):
    """Print vault contents."""
    vault = _load_vault()

    if not vault["rods"]:
        print("Vault is empty. Enroll rods with: cwm_vault.py enroll --rod N")
        return

    print(f"Vault database: {VAULT_DB_PATH}")
    print(f"Enrolled rods: {len(vault['rods'])}")
    print(f"Total credentials: {len(vault['labels'])}")
    print()

    for rod_id, rod_data in sorted(vault["rods"].items()):
        print(f"  Rod {rod_id} (Pattern {rod_data['pattern']}):")
        for ch_id, ch_data in sorted(rod_data["channels"].items()):
            label = ch_data["label"]
            modes = ch_data["modes"]
            print(f"    Ch {ch_id}: '{label}' — modes {modes}")
    print()

    # Cross-rod isolation matrix
    rod_ids = sorted(vault["rods"].keys())
    if len(rod_ids) > 1:
        print("Cross-rod correlation matrix (channel 0 vs channel 0):")
        for i, ri in enumerate(rod_ids):
            ti = np.array(vault["rods"][ri]["channels"]["0"]["template"])
            for rj in rod_ids[i + 1:]:
                tj = np.array(vault["rods"][rj]["channels"]["0"]["template"])
                xcorr = _correlate(ti, tj)
                print(f"  Rod {ri} vs Rod {rj}: {xcorr:+.4f}")


# ── CLI ───────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="CWM Acoustic Password Vault — polysemic packed-array credential store"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # ── enroll ──
    p_enroll = sub.add_parser("enroll", help="Enroll a rod into the vault")
    p_enroll.add_argument("--rod", type=int, required=True, help="Rod number (1–10)")
    p_enroll.add_argument("--pattern", choices=["A", "B", "C", "D", "a", "b", "c", "d"],
                          help="Perturbation pattern (default: auto-assigned)")
    p_enroll.add_argument("--labels", nargs=4, help="Labels for 4 polysemic channels")
    p_enroll.add_argument("--mass", type=float, default=0.8, help="Putty mass in mg (default: 0.8)")
    p_enroll.add_argument("--rod-length", type=float, default=150.0, help="Rod length in mm")
    p_enroll.add_argument("--rod-diameter", type=float, default=6.0, help="Rod diameter in mm")
    p_enroll.set_defaults(func=enroll)

    # ── verify ──
    p_verify = sub.add_parser("verify", help="Verify a credential")
    p_verify.add_argument("--label", required=True, help="Credential label to verify")
    p_verify.add_argument("--noise", type=float, default=0.0, help="Noise σ to inject (attack test)")
    p_verify.add_argument("--seed", type=int, default=42, help="RNG seed for noise injection")
    p_verify.add_argument("--wrong-rod", action="store_true", help="Show wrong-rod correlations")
    p_verify.add_argument("--mass", type=float, default=0.8, help="Putty mass in mg")
    p_verify.add_argument("--rod-length", type=float, default=150.0, help="Rod length in mm")
    p_verify.add_argument("--rod-diameter", type=float, default=6.0, help="Rod diameter in mm")
    p_verify.set_defaults(func=verify)

    # ── status ──
    p_status = sub.add_parser("status", help="Show vault contents")
    p_status.set_defaults(func=status)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
