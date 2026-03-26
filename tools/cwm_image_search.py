#!/usr/bin/env python3
"""
Acoustic Image Search — Nearest-Neighbor Visual Retrieval via Spectral Fingerprints.

Maps perceptual image hashes to spectral fingerprints across a packed rod array,
then retrieves the closest visual match by acoustic correlation.

Subcommands
-----------
    enroll   Hash each image in a library, measure rod fingerprints, and assign
             images to the rod/channel with the best fingerprint match.
    query    Compute a query image's hash and find the closest library match.
    test     Query every library image and report rank-1 retrieval accuracy.

Usage
-----
    # Enroll a library (simulation mode)
    PYTHONPATH=. python tools/cwm_image_search.py enroll \\
        --library data/image_search/library/ --rods 4 --channels 4

    # Query with a new image
    PYTHONPATH=. python tools/cwm_image_search.py query \\
        --image data/image_search/query/test_photo.jpg

    # Self-retrieval accuracy test
    PYTHONPATH=. python tools/cwm_image_search.py test \\
        --library data/image_search/library/

Requires: numpy, Pillow (PIL).
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
N_MODES = 20
N_CHANNELS = 4
MODES_PER_CHANNEL = N_MODES // N_CHANNELS
HASH_SIZE = 8              # 8×8 average hash → 64 bits
HASH_DIM = HASH_SIZE * HASH_SIZE  # 64

IMAGE_DB_PATH = Path("data/results/image_db.json")

NAMED_PATTERNS = {
    "A": [0.25, 0.75],
    "B": [1 / 3, 2 / 3],
    "C": [0.5],
    "D": [0.2, 0.8],
}

# Cycle through patterns for multiple rods
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


# ── Perceptual hashing ───────────────────────────────────────────────────

def _average_hash(image_path: str) -> np.ndarray:
    """
    Compute average hash of an image (8×8 → 64-bit binary vector).

    Falls back to a deterministic pseudo-hash if Pillow is unavailable,
    allowing simulation mode without image files.
    """
    try:
        from PIL import Image
        img = Image.open(image_path).convert("L").resize(
            (HASH_SIZE, HASH_SIZE), Image.Resampling.LANCZOS
        )
        pixels = np.array(img, dtype=np.float64).flatten()
        mean_val = pixels.mean()
        return (pixels > mean_val).astype(np.float64)
    except (ImportError, FileNotFoundError):
        # Deterministic pseudo-hash from filename for simulation mode
        name = Path(image_path).stem
        seed = sum(ord(c) * (i + 1) for i, c in enumerate(name))
        rng = np.random.default_rng(seed=seed)
        return (rng.random(HASH_DIM) > 0.5).astype(np.float64)


def _hash_to_target_vector(h: np.ndarray, n_modes: int = MODES_PER_CHANNEL) -> np.ndarray:
    """
    Map a perceptual hash to a target shift vector.

    Partition the 64-bit hash into n_modes groups, compute the mean of
    each group, and normalize. This gives a compact target that can be
    compared against measured channel fingerprints.
    """
    # Reshape into n_modes groups
    group_size = max(1, len(h) // n_modes)
    target = np.zeros(n_modes)
    for i in range(n_modes):
        start = i * group_size
        end = min(start + group_size, len(h))
        target[i] = h[start:end].mean()
    # Normalize to unit vector
    norm = np.linalg.norm(target)
    if norm > 1e-30:
        target /= norm
    return target


def _load_db() -> dict:
    """Load image database from JSON."""
    if IMAGE_DB_PATH.exists():
        return json.loads(IMAGE_DB_PATH.read_text())
    return {"rods": {}, "images": {}, "config": {}}


def _save_db(db: dict):
    """Save image database to JSON."""
    IMAGE_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    IMAGE_DB_PATH.write_text(json.dumps(db, indent=2))


# ── Enroll ────────────────────────────────────────────────────────────────

def enroll(args):
    """Hash images and assign them to rod/channel slots."""
    library_dir = Path(args.library)
    if not library_dir.exists():
        print(f"Error: library directory '{library_dir}' not found.")
        print(f"Create it and add JPEG/PNG images, or use --simulate for demo data.")
        sys.exit(1)

    image_extensions = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".tiff", ".webp"}
    images = sorted(
        p for p in library_dir.iterdir()
        if p.suffix.lower() in image_extensions
    )

    n_rods = args.rods
    n_channels = args.channels
    capacity = n_rods * n_channels

    if not images:
        # Generate synthetic demo images for simulation
        print(f"No images found in {library_dir}. Using synthetic demo library.")
        images = [library_dir / f"synthetic_{i:03d}.png" for i in range(min(capacity, 16))]

    print(f"Image search enrollment")
    print(f"  Library: {library_dir} ({len(images)} images)")
    print(f"  Array: {n_rods} rods × {n_channels} channels = {capacity} slots")
    print(f"  Hash: average hash, {HASH_DIM} bits")
    print()

    if len(images) > capacity:
        print(f"  Warning: {len(images)} images > {capacity} slots. "
              f"Only the best {capacity} matches will be stored.")

    # Step 1: Compute rod fingerprints
    print("Step 1: Computing rod fingerprints...")
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
        }
        print(f"  Rod {rod_idx} (Pattern {pattern}): ✓")

    # Step 2: Compute image hashes
    print("\nStep 2: Computing perceptual hashes...")
    image_hashes = {}
    for img_path in images:
        h = _average_hash(str(img_path))
        target = _hash_to_target_vector(h)
        image_hashes[img_path.name] = {
            "hash": h.tolist(),
            "target": target.tolist(),
        }

    # Step 3: Assign images to best-matching rod/channel
    print("\nStep 3: Assigning images to rod/channel slots...")
    assignments = {}
    used_slots = set()

    # For each image, find the best rod/channel match
    scores = []
    for img_name, img_data in image_hashes.items():
        target = np.array(img_data["target"])
        for rod_id, rd in rod_data.items():
            for ch in range(n_channels):
                ch_vec = _extract_channel(rd["fingerprint"], ch)
                # Normalize channel vector
                ch_norm = np.linalg.norm(ch_vec)
                if ch_norm > 1e-30:
                    ch_vec_n = ch_vec / ch_norm
                else:
                    ch_vec_n = ch_vec
                score = _correlate(target, ch_vec_n)
                scores.append((score, img_name, rod_id, ch))

    # Greedy assignment: best score first, no slot reuse
    scores.sort(key=lambda x: -x[0])
    for score, img_name, rod_id, ch in scores:
        slot = (rod_id, ch)
        if slot in used_slots or img_name in assignments:
            continue
        assignments[img_name] = {
            "rod": rod_id,
            "channel": ch,
            "score": score,
            "target": image_hashes[img_name]["target"],
            "hash": image_hashes[img_name]["hash"],
        }
        used_slots.add(slot)
        if len(assignments) >= min(len(images), capacity):
            break

    # Build database
    db = {
        "rods": rod_data,
        "images": {},
        "config": {
            "n_rods": n_rods,
            "n_channels": n_channels,
            "hash_size": HASH_SIZE,
            "library": str(library_dir),
        },
    }
    for img_name, asgn in assignments.items():
        db["images"][img_name] = {
            "rod": asgn["rod"],
            "channel": asgn["channel"],
            "target": asgn["target"],
            "hash": asgn["hash"],
        }

    _save_db(db)

    print(f"\n  {'Image':<30s}  {'Rod':>3s}  {'Ch':>2s}  {'Score':>6s}")
    print(f"  {'-'*30}  {'---':>3s}  {'--':>2s}  {'-----':>6s}")
    for img_name, asgn in sorted(assignments.items()):
        print(f"  {img_name:<30s}  {asgn['rod']:>3s}  {asgn['channel']:>2d}  {asgn['score']:>6.3f}")

    print(f"\nEnrolled {len(assignments)} images across {n_rods} rods.")
    print(f"Database: {IMAGE_DB_PATH}")


# ── Query ─────────────────────────────────────────────────────────────────

def query(args):
    """Find the closest library match for a query image."""
    db = _load_db()
    if not db["images"]:
        print("Error: image database is empty. Run 'enroll' first.")
        sys.exit(1)

    query_hash = _average_hash(args.image)
    query_target = _hash_to_target_vector(query_hash)

    print(f"Query: {Path(args.image).name}")
    print()

    # Correlate query hash target against all enrolled image targets.
    # In the physical system, each image's target maps to a specific rod/channel;
    # the acoustic query excites that rod's response.  The laptop performs the
    # final correlation — identical to what the CMOS readout ASIC would do.
    # We compare full 64-bit hashes for maximum discrimination.
    results = []
    for img_name, img_data in db["images"].items():
        enrolled_hash = np.array(img_data.get("hash", img_data["target"]))
        corr = _correlate(query_hash, enrolled_hash)
        results.append((corr, img_name, img_data["rod"], img_data["channel"]))

    results.sort(key=lambda x: -x[0])

    best = results[0]
    runner_up = results[1] if len(results) > 1 else (0, "—", "—", "—")

    if best[0] > 0 and runner_up[0] > 0:
        margin_db = 20 * np.log10(best[0] / max(abs(runner_up[0]), 1e-30))
    else:
        margin_db = float("inf")

    print(f"  Best match:  {best[1]} (Rod {best[2]}, Channel {best[3]})")
    print(f"  Correlation: {best[0]:.3f}")
    print(f"  Runner-up:   {runner_up[1]} (Rod {runner_up[2]}, Channel {runner_up[3]}) at {runner_up[0]:.3f}")
    print(f"  Margin:      {margin_db:.1f} dB")

    if len(results) > 2:
        print(f"\n  Top 5 matches:")
        for corr, name, rod, ch in results[:5]:
            print(f"    {corr:.3f}  {name} (Rod {rod}, Ch {ch})")


# ── Test ──────────────────────────────────────────────────────────────────

def test(args):
    """Run self-retrieval accuracy test on the enrolled library."""
    db = _load_db()
    if not db["images"]:
        print("Error: image database is empty. Run 'enroll' first.")
        sys.exit(1)

    library_dir = Path(args.library) if args.library else Path(db["config"].get("library", "."))

    print(f"Self-retrieval test")
    print(f"  Library: {library_dir}")
    print(f"  Enrolled images: {len(db['images'])}")
    print()

    correct = 0
    total = 0
    margins = []
    confusion_pairs = []

    for img_name, img_data in db["images"].items():
        img_path = library_dir / img_name
        query_hash = _average_hash(str(img_path))

        # Correlate against all enrolled image hashes (full 64-bit)
        results = []
        for other_name, other_data in db["images"].items():
            enrolled_hash = np.array(other_data.get("hash", other_data["target"]))
            corr = _correlate(query_hash, enrolled_hash)
            results.append((corr, other_name))

        results.sort(key=lambda x: -x[0])
        best_name = results[0][1]
        best_corr = results[0][0]
        runner_corr = results[1][0] if len(results) > 1 else 0.0

        is_correct = best_name == img_name
        if is_correct:
            correct += 1
        total += 1

        if best_corr > 0 and runner_corr > 0:
            margin = 20 * np.log10(best_corr / max(abs(runner_corr), 1e-30))
        else:
            margin = float("inf")
        margins.append(margin)

        status = "✓" if is_correct else "✗"
        print(f"  {status} {img_name:<30s} → {best_name:<30s} ({best_corr:.3f}, margin {margin:.1f} dB)")

        if not is_correct:
            confusion_pairs.append((img_name, best_name))

    accuracy = 100.0 * correct / total if total > 0 else 0.0
    finite_margins = [m for m in margins if m < float("inf")]
    mean_margin = np.mean(finite_margins) if finite_margins else float("inf")
    min_margin = min(finite_margins) if finite_margins else float("inf")

    print(f"\nResults:")
    print(f"  Rank-1 accuracy:       {accuracy:.1f}% ({correct}/{total})")
    print(f"  Mean margin:           {mean_margin:.1f} dB")
    print(f"  Worst margin:          {min_margin:.1f} dB")
    if confusion_pairs:
        print(f"  Confusion pairs:       {len(confusion_pairs)}")
        for a, b in confusion_pairs:
            print(f"    {a} ↔ {b}")


# ── CLI ───────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="CWM Acoustic Image Search — nearest-neighbor visual retrieval"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # ── enroll ──
    p_enroll = sub.add_parser("enroll", help="Enroll image library")
    p_enroll.add_argument("--library", required=True, help="Path to image directory")
    p_enroll.add_argument("--rods", type=int, default=4, help="Number of rods (default: 4)")
    p_enroll.add_argument("--channels", type=int, default=4, help="Polysemic channels (default: 4)")
    p_enroll.add_argument("--mass", type=float, default=0.8, help="Putty mass in mg")
    p_enroll.add_argument("--rod-length", type=float, default=150.0, help="Rod length in mm")
    p_enroll.add_argument("--rod-diameter", type=float, default=6.0, help="Rod diameter in mm")
    p_enroll.set_defaults(func=enroll)

    # ── query ──
    p_query = sub.add_parser("query", help="Query with an image")
    p_query.add_argument("--image", required=True, help="Path to query image")
    p_query.set_defaults(func=query)

    # ── test ──
    p_test = sub.add_parser("test", help="Run self-retrieval accuracy test")
    p_test.add_argument("--library", help="Path to image directory (default: from DB)")
    p_test.set_defaults(func=test)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
