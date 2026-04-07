#!/usr/bin/env python3
"""
CWM Lab — Local Experiment UI for Auth + Image Search.

A self-contained local web server that demonstrates:
  1. CWM authentication (password vault via rod spectral fingerprints)
  2. Per-user image library enrollment and visual search
  3. Webcam-based live query

Start with:
    PYTHONPATH=. python tools/cwm_lab.py [--port 8200] [--rods 4]

Then open http://localhost:8200 in a browser.

All state is stored in data/results/lab/ as JSON files.
No external dependencies beyond numpy and Pillow.
"""

import argparse
import base64
import io
import json
import os
import sys
import tempfile
import uuid
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

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
HASH_SIZE = 8
HASH_DIM = HASH_SIZE * HASH_SIZE
CORRELATION_THRESHOLD = 0.85

# Hardware detection — set once at startup
HARDWARE_AVAILABLE = False
SCOPE_FUNCTIONS_AVAILABLE = False
try:
    from tools.cwm_picoscope import (
        check_hardware, measure_rod_fingerprint,
        get_experiment_presets as _get_experiment_presets,
        get_scope_status as _get_scope_status,
        configure_scope as _configure_scope,
        capture_block as _capture_block,
        compute_spectrum as _compute_spectrum,
        close_scope as _close_scope,
        is_scope_busy,
    )
    HARDWARE_AVAILABLE = check_hardware()
    SCOPE_FUNCTIONS_AVAILABLE = True
except (ImportError, OSError):
    pass

NAMED_PATTERNS = {
    "A": [0.25, 0.75],
    "B": [1 / 3, 2 / 3],
    "C": [0.5],
    "D": [0.2, 0.8],
}
PATTERN_CYCLE = ["A", "B", "C", "D"]

DATA_DIR = Path("data/results/lab")
USERS_DB_PATH = DATA_DIR / "users.json"

# ── Shared physics engine ─────────────────────────────────────────────────

def _channel_modes(channel: int) -> list:
    start = channel * MODES_PER_CHANNEL + 1
    return list(range(start, start + MODES_PER_CHANNEL))


def _compute_rod_fingerprint(
    pattern_name: str,
    rod_length_mm: float = 150.0,
    rod_diameter_mm: float = 6.0,
    putty_mass_mg: float = 0.8,
    rod_id: int = 1,
) -> dict:
    # ── Hardware path: real PicoScope measurement ─────────────────────
    # Skip hardware if the wizard has the scope handle open
    hw_ok = HARDWARE_AVAILABLE
    if hw_ok and SCOPE_FUNCTIONS_AVAILABLE:
        try:
            hw_ok = not is_scope_busy()
        except Exception:
            pass
    if hw_ok:
        return measure_rod_fingerprint(
            rod_id=rod_id,
            pattern_name=pattern_name,
            rod_length_mm=rod_length_mm,
            rod_diameter_mm=rod_diameter_mm,
        )

    # ── Simulation path: Rayleigh perturbation theory ─────────────────
    positions = NAMED_PATTERNS[pattern_name.upper()]
    rng = np.random.default_rng(
        seed=rod_id * 1000 + sum(ord(c) for c in pattern_name)
    )
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
        "fingerprint": spec.shift_hz.tolist(),
    }


def _extract_channel(fingerprint: list, channel: int) -> np.ndarray:
    modes = _channel_modes(channel)
    return np.array([fingerprint[m - 1] for m in modes])


def _correlate(a: np.ndarray, b: np.ndarray) -> float:
    a_c = a - a.mean()
    b_c = b - b.mean()
    na, nb = np.linalg.norm(a_c), np.linalg.norm(b_c)
    if na < 1e-30 or nb < 1e-30:
        return 0.0
    return float(np.dot(a_c, b_c) / (na * nb))


def _average_hash_from_bytes(image_bytes: bytes) -> np.ndarray:
    """Compute 8x8 average hash from raw image bytes."""
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(image_bytes)).convert("L").resize(
            (HASH_SIZE, HASH_SIZE), Image.Resampling.LANCZOS
        )
        pixels = np.array(img, dtype=np.float64).flatten()
        return (pixels > pixels.mean()).astype(np.float64)
    except ImportError:
        # Fallback: deterministic hash from byte content
        seed = sum(image_bytes[:64]) % (2**31)
        rng = np.random.default_rng(seed=seed)
        return (rng.random(HASH_DIM) > 0.5).astype(np.float64)


def _hash_to_target_vector(h: np.ndarray, n_modes: int = MODES_PER_CHANNEL) -> np.ndarray:
    group_size = max(1, len(h) // n_modes)
    target = np.zeros(n_modes)
    for i in range(n_modes):
        start = i * group_size
        end = min(start + group_size, len(h))
        target[i] = h[start:end].mean()
    norm = np.linalg.norm(target)
    if norm > 1e-30:
        target /= norm
    return target


# ── Database helpers ──────────────────────────────────────────────────────

def _load_users() -> dict:
    if USERS_DB_PATH.exists():
        return json.loads(USERS_DB_PATH.read_text())
    return {"users": {}, "rods": {}}


def _save_users(db: dict):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    USERS_DB_PATH.write_text(json.dumps(db, indent=2))


def _user_image_db_path(username: str) -> Path:
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in username)
    return DATA_DIR / f"images_{safe_name}.json"


def _load_user_images(username: str) -> dict:
    p = _user_image_db_path(username)
    if p.exists():
        return json.loads(p.read_text())
    return {"images": {}, "rods": {}}


def _save_user_images(username: str, db: dict):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    _user_image_db_path(username).write_text(json.dumps(db, indent=2))


# ── Rod management ────────────────────────────────────────────────────────

N_RODS_DEFAULT = 4


def _ensure_rods(db: dict, n_rods: int = N_RODS_DEFAULT):
    """Ensure rod fingerprints are computed and cached.

    In HARDWARE mode, this only creates the rods dict structure — actual
    fingerprints are captured one-at-a-time via /api/enroll-rod so the user
    can swap cables between measurements.  In SIMULATION mode, all rods are
    auto-enrolled immediately (no physical wiring needed).
    """
    if db.get("rods"):
        return
    db["rods"] = {}
    for rod_idx in range(1, n_rods + 1):
        pattern = PATTERN_CYCLE[(rod_idx - 1) % len(PATTERN_CYCLE)]
        if HARDWARE_AVAILABLE:
            # Placeholder — real fingerprint captured via enroll-rod wizard
            db["rods"][str(rod_idx)] = {
                "pattern": pattern,
                "fingerprint": None,
                "perturbed_hz": None,
                "enrolled": False,
            }
        else:
            fp = _compute_rod_fingerprint(pattern_name=pattern, rod_id=rod_idx)
            db["rods"][str(rod_idx)] = {
                "pattern": pattern,
                "fingerprint": fp["fingerprint"],
                "perturbed_hz": fp["perturbed_hz"],
                "enrolled": True,
            }


def _enroll_single_rod(rod_id: int, pattern_name=None) -> dict:
    """Measure one rod via PicoScope and save its fingerprint."""
    db = _load_users()
    _ensure_rods(db)

    rod_key = str(rod_id)
    if rod_key not in db["rods"]:
        return {"error": f"Rod {rod_id} does not exist in the array."}

    if pattern_name is None:
        pattern_name = db["rods"][rod_key].get("pattern", "A")

    fp = _compute_rod_fingerprint(pattern_name=pattern_name, rod_id=rod_id)
    db["rods"][rod_key]["fingerprint"] = fp["fingerprint"]
    db["rods"][rod_key]["perturbed_hz"] = fp["perturbed_hz"]
    db["rods"][rod_key]["pattern"] = pattern_name
    db["rods"][rod_key]["enrolled"] = True
    _save_users(db)

    return {
        "ok": True,
        "rod_id": rod_id,
        "pattern": pattern_name,
        "perturbed_hz": fp["perturbed_hz"],
        "fingerprint": fp["fingerprint"],
        "enrolled": True,
    }


def _get_rod_status() -> dict:
    """Return enrollment status for every rod."""
    db = _load_users()
    _ensure_rods(db)
    _save_users(db)
    rods = {}
    for rod_key, rod_data in db.get("rods", {}).items():
        rods[rod_key] = {
            "pattern": rod_data.get("pattern"),
            "enrolled": rod_data.get("enrolled", False),
        }
    all_enrolled = all(r["enrolled"] for r in rods.values())
    return {
        "rods": rods,
        "all_enrolled": all_enrolled,
        "hardware": HARDWARE_AVAILABLE,
        "n_rods": len(rods),
    }


# ── Auth (CWM Vault) ─────────────────────────────────────────────────────

def _register_user(username: str, rod_id: int, channel: int) -> dict:
    """Register a user by assigning them a rod/channel slot."""
    db = _load_users()
    _ensure_rods(db)

    if username in db["users"]:
        return {"error": f"User '{username}' already registered."}

    # Check slot availability
    slot_key = f"{rod_id}:{channel}"
    for u, udata in db["users"].items():
        if f"{udata['rod']}:{udata['channel']}" == slot_key:
            return {"error": f"Slot Rod {rod_id} Ch {channel} already taken by '{u}'."}

    rod_data = db["rods"].get(str(rod_id))
    if not rod_data:
        return {"error": f"Rod {rod_id} not initialized."}

    template = _extract_channel(rod_data["fingerprint"], channel).tolist()

    db["users"][username] = {
        "rod": rod_id,
        "channel": channel,
        "template": template,
        "rod_pattern": rod_data["pattern"],
    }
    _save_users(db)

    return {
        "ok": True,
        "username": username,
        "rod": rod_id,
        "channel": channel,
        "pattern": rod_data["pattern"],
        "modes": _channel_modes(channel),
    }


def _authenticate_user(username: str) -> dict:
    """Authenticate by re-measuring the rod and correlating."""
    db = _load_users()
    _ensure_rods(db)

    if username not in db["users"]:
        return {"authenticated": False, "error": "User not found."}

    user = db["users"][username]
    rod_data = db["rods"].get(str(user["rod"]))
    if not rod_data:
        return {"authenticated": False, "error": "Rod data missing."}

    # Simulate fresh measurement with slight noise
    fp = _compute_rod_fingerprint(
        pattern_name=rod_data["pattern"],
        rod_id=user["rod"],
    )
    measured_full = np.array(fp["fingerprint"])

    # Full-rod correlation
    enrolled_full = np.array(rod_data["fingerprint"])
    corr = _correlate(measured_full, enrolled_full)

    # Channel-level check
    template = np.array(user["template"])
    measured_ch = _extract_channel(fp["fingerprint"], user["channel"])
    ch_corr = _correlate(measured_ch, template)

    # Cross-user discrimination
    wrong_corrs = []
    for other_user, other_data in db["users"].items():
        if other_user == username:
            continue
        if other_data["rod"] == user["rod"]:
            other_template = np.array(other_data["template"])
            wrong_corrs.append(
                (_correlate(measured_ch, other_template), other_user)
            )
        else:
            other_rod = db["rods"].get(str(other_data["rod"]))
            if other_rod:
                other_fp = np.array(other_rod["fingerprint"])
                wrong_corrs.append(
                    (_correlate(measured_full, other_fp), other_user)
                )

    best_wrong = max(wrong_corrs, key=lambda x: x[0]) if wrong_corrs else (0.0, "—")
    if corr > 0 and best_wrong[0] > 0:
        margin_db = 20 * np.log10(corr / max(abs(best_wrong[0]), 1e-30))
    else:
        margin_db = float("inf") if corr > 0 else 0.0

    passed = corr >= CORRELATION_THRESHOLD

    return {
        "authenticated": passed,
        "username": username,
        "correlation": round(corr, 4),
        "channel_correlation": round(ch_corr, 4),
        "threshold": CORRELATION_THRESHOLD,
        "best_wrong_user": best_wrong[1],
        "best_wrong_corr": round(best_wrong[0], 4),
        "margin_db": round(margin_db, 1),
        "rod": user["rod"],
        "channel": user["channel"],
        "pattern": user.get("rod_pattern", "?"),
        "modes": _channel_modes(user["channel"]),
    }


def _list_users() -> dict:
    db = _load_users()
    _ensure_rods(db)
    users = []
    for username, udata in db["users"].items():
        users.append({
            "username": username,
            "rod": udata["rod"],
            "channel": udata["channel"],
            "pattern": udata.get("rod_pattern", "?"),
        })
    slots_total = len(db.get("rods", {})) * N_CHANNELS
    slots_used = len(db["users"])
    return {
        "users": users,
        "slots_total": slots_total,
        "slots_used": slots_used,
        "n_rods": len(db.get("rods", {})),
    }


# ── Image enrollment & search ────────────────────────────────────────────

def _enroll_image(username: str, image_name: str, image_bytes: bytes) -> dict:
    """Enroll a single image into the user's library."""
    img_db = _load_user_images(username)
    users_db = _load_users()
    _ensure_rods(users_db)

    # Initialize rods in image DB if needed
    if not img_db.get("rods"):
        img_db["rods"] = users_db.get("rods", {})

    # Compute hash
    h = _average_hash_from_bytes(image_bytes)
    target = _hash_to_target_vector(h)

    # Find best available slot
    n_rods = len(img_db["rods"])
    n_channels = N_CHANNELS
    used_slots = set()
    for img_name, img_data in img_db.get("images", {}).items():
        used_slots.add((str(img_data["rod"]), img_data["channel"]))

    scores = []
    for rod_id, rd in img_db["rods"].items():
        for ch in range(n_channels):
            if (rod_id, ch) in used_slots:
                continue
            ch_vec = _extract_channel(rd["fingerprint"], ch)
            ch_norm = np.linalg.norm(ch_vec)
            if ch_norm > 1e-30:
                ch_vec_n = ch_vec / ch_norm
            else:
                ch_vec_n = ch_vec
            score = _correlate(target, ch_vec_n)
            scores.append((score, rod_id, ch))

    if not scores:
        capacity = n_rods * n_channels
        return {"error": f"Library full ({capacity} slots used)."}

    scores.sort(key=lambda x: -x[0])
    best_score, best_rod, best_ch = scores[0]

    # Save image data (base64 thumbnail for display)
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(image_bytes))
        img.thumbnail((200, 200))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=80)
        thumbnail_b64 = base64.b64encode(buf.getvalue()).decode()
    except ImportError:
        thumbnail_b64 = ""

    img_db.setdefault("images", {})[image_name] = {
        "rod": best_rod,
        "channel": best_ch,
        "target": target.tolist(),
        "hash": h.tolist(),
        "score": round(best_score, 4),
        "thumbnail": thumbnail_b64,
    }

    _save_user_images(username, img_db)

    return {
        "ok": True,
        "image": image_name,
        "rod": best_rod,
        "channel": best_ch,
        "score": round(best_score, 4),
        "total_images": len(img_db["images"]),
        "capacity": n_rods * n_channels,
    }


def _query_image(username: str, image_bytes: bytes) -> dict:
    """Find the closest match in the user's library."""
    img_db = _load_user_images(username)

    if not img_db.get("images"):
        return {"error": "No images enrolled. Upload some images first."}

    query_hash = _average_hash_from_bytes(image_bytes)

    results = []
    for img_name, img_data in img_db["images"].items():
        enrolled_hash = np.array(img_data["hash"])
        corr = _correlate(query_hash, enrolled_hash)
        results.append({
            "name": img_name,
            "correlation": round(corr, 4),
            "rod": img_data["rod"],
            "channel": img_data["channel"],
            "thumbnail": img_data.get("thumbnail", ""),
        })

    results.sort(key=lambda x: -x["correlation"])

    best = results[0]
    runner = results[1] if len(results) > 1 else {"correlation": 0.0}

    if best["correlation"] > 0 and runner["correlation"] > 0:
        margin = 20 * np.log10(
            best["correlation"] / max(abs(runner["correlation"]), 1e-30)
        )
    else:
        margin = float("inf") if best["correlation"] > 0 else 0.0

    return {
        "match": best,
        "margin_db": round(margin, 1),
        "all_results": results[:5],
        "total_searched": len(results),
    }


def _get_user_library(username: str) -> dict:
    """Return the user's enrolled image library."""
    img_db = _load_user_images(username)
    images = []
    for img_name, img_data in img_db.get("images", {}).items():
        images.append({
            "name": img_name,
            "rod": img_data["rod"],
            "channel": img_data["channel"],
            "score": img_data.get("score", 0),
            "thumbnail": img_data.get("thumbnail", ""),
        })
    n_rods = len(img_db.get("rods", {}))
    return {
        "images": images,
        "total": len(images),
        "capacity": n_rods * N_CHANNELS,
        "n_rods": n_rods,
    }


def _delete_user_image(username: str, image_name: str) -> dict:
    """Remove an image from the user's library."""
    img_db = _load_user_images(username)
    if image_name in img_db.get("images", {}):
        del img_db["images"][image_name]
        _save_user_images(username, img_db)
        return {"ok": True, "deleted": image_name}
    return {"error": f"Image '{image_name}' not found."}


# ── Face recognition (shared DB) ─────────────────────────────────────────

FACES_DB_PATH = DATA_DIR / "faces.json"


def _load_faces() -> dict:
    if FACES_DB_PATH.exists():
        return json.loads(FACES_DB_PATH.read_text())
    return {"faces": {}, "rods": {}}


def _save_faces(db: dict):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    FACES_DB_PATH.write_text(json.dumps(db, indent=2))


def _enroll_face(username: str, image_bytes: bytes) -> dict:
    """Enroll a user's face photo into the shared face DB at their rod/channel slot."""
    users_db = _load_users()
    _ensure_rods(users_db)

    if username not in users_db["users"]:
        return {"error": "User not registered. Register first."}

    user = users_db["users"][username]
    rod_id = str(user["rod"])
    channel = user["channel"]

    face_db = _load_faces()

    # Initialize rods in face DB if needed
    if not face_db.get("rods"):
        face_db["rods"] = users_db.get("rods", {})

    # Compute hash
    h = _average_hash_from_bytes(image_bytes)
    target = _hash_to_target_vector(h)

    # Build thumbnail
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(image_bytes))
        img.thumbnail((200, 200))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=80)
        thumbnail_b64 = base64.b64encode(buf.getvalue()).decode()
    except ImportError:
        thumbnail_b64 = ""

    # Compute correlation with assigned slot
    rod_data = face_db["rods"].get(rod_id, users_db["rods"].get(rod_id, {}))
    if rod_data:
        ch_vec = _extract_channel(rod_data["fingerprint"], channel)
        ch_norm = np.linalg.norm(ch_vec)
        if ch_norm > 1e-30:
            ch_vec_n = ch_vec / ch_norm
        else:
            ch_vec_n = ch_vec
        score = _correlate(target, ch_vec_n)
    else:
        score = 0.0

    face_db["faces"][username] = {
        "rod": rod_id,
        "channel": channel,
        "target": target.tolist(),
        "hash": h.tolist(),
        "score": round(score, 4),
        "thumbnail": thumbnail_b64,
    }

    _save_faces(face_db)

    return {
        "ok": True,
        "username": username,
        "rod": rod_id,
        "channel": channel,
        "score": round(score, 4),
        "total_faces": len(face_db["faces"]),
    }


def _authenticate_face(image_bytes: bytes) -> dict:
    """Authenticate by converting the face image to a spectral query and
    correlating against the rod fingerprint — the same physics pipeline
    used for image search and vault auth.

    Flow: webcam frame → perceptual hash → target vector →
          correlate against every enrolled face's rod/channel fingerprint →
          best spectral match = authenticated identity.
    """
    face_db = _load_faces()
    users_db = _load_users()
    _ensure_rods(users_db)

    if not face_db.get("faces"):
        return {"authenticated": False, "error": "No faces enrolled yet."}

    query_hash = _average_hash_from_bytes(image_bytes)
    query_target = _hash_to_target_vector(query_hash)

    results = []
    for uname, fdata in face_db["faces"].items():
        rod_id = str(fdata["rod"])
        channel = fdata["channel"]

        # Get the rod's live spectral fingerprint (re-measured or from DB)
        rod_data = face_db.get("rods", {}).get(rod_id) or users_db.get("rods", {}).get(rod_id)
        if not rod_data:
            continue

        # Re-measure the rod (same as vault auth — fresh capture)
        fp = _compute_rod_fingerprint(
            pattern_name=rod_data["pattern"],
            rod_id=int(rod_id),
        )
        measured_ch = _extract_channel(fp["fingerprint"], channel)

        # Correlate the face-derived target against the rod's spectral channel
        spectral_corr = _correlate(query_target, measured_ch)

        # Also compute face-to-face hash similarity for display
        enrolled_hash = np.array(fdata["hash"])
        face_corr = _correlate(query_hash, enrolled_hash)

        results.append({
            "username": uname,
            "correlation": round(spectral_corr, 4),  # rod spectral auth
            "face_similarity": round(face_corr, 4),   # visual similarity
            "rod": rod_id,
            "channel": channel,
            "thumbnail": fdata.get("thumbnail", ""),
        })

    if not results:
        return {"authenticated": False, "error": "No valid rod data for enrolled faces."}

    results.sort(key=lambda x: -x["correlation"])

    best = results[0]
    runner = results[1] if len(results) > 1 else {"correlation": 0.0}

    if best["correlation"] > 0 and runner["correlation"] > 0:
        margin = 20 * np.log10(
            best["correlation"] / max(abs(runner["correlation"]), 1e-30)
        )
    else:
        margin = float("inf") if best["correlation"] > 0 else 0.0

    # Auth requires spectral correlation above threshold — same physics gate as vault
    passed = best["correlation"] >= CORRELATION_THRESHOLD

    return {
        "authenticated": passed,
        "face_match": best,
        "margin_db": round(margin, 1),
        "all_results": results[:5],
        "total_faces": len(results),
    }


def _get_faces() -> dict:
    """Return summary of enrolled faces."""
    face_db = _load_faces()
    faces = []
    for uname, fdata in face_db.get("faces", {}).items():
        faces.append({
            "username": uname,
            "rod": fdata["rod"],
            "channel": fdata["channel"],
            "thumbnail": fdata.get("thumbnail", ""),
        })
    return {"faces": faces, "total": len(faces)}


# ── Proof / transparency endpoint ────────────────────────────────────────

def _build_proof() -> dict:
    """Return full physics state for skeptic verification.

    Exposes every layer of the CWM pipeline:
    - Rod geometry and perturbation parameters
    - Rayleigh-computed unperturbed and perturbed mode frequencies
    - 20-mode frequency-shift fingerprints per rod
    - Channel decomposition (which modes belong to which channel)
    - Cross-correlation matrix between all rods
    - User→slot mapping with per-user cross-correlation
    - Face→slot mapping with face cross-correlation
    - Source code references for independent audit
    """
    db = _load_users()
    _ensure_rods(db)

    # ── Rod physics detail ────────────────────────────────────────────
    rods_detail = []
    for rod_id_str, rd in sorted(db.get("rods", {}).items(), key=lambda x: int(x[0])):
        rod_id = int(rod_id_str)
        pattern_name = rd["pattern"]
        positions = NAMED_PATTERNS[pattern_name]

        # Recompute to get full detail (same deterministic seed)
        rng = np.random.default_rng(
            seed=rod_id * 1000 + sum(ord(c) for c in pattern_name)
        )
        jittered = [
            max(0.01, min(0.99, frac + rng.normal(0, 0.015)))
            for frac in positions
        ]
        mass_var = 0.8 * (1.0 + rng.normal(0, 0.15))

        rod_geo = RodGeometry(
            length=150.0 / 1000.0,
            diameter=6.0 / 1000.0,
            glass_type="borosilicate",
        )
        perturbations = [
            Perturbation(
                position=frac * rod_geo.length,
                delta_mass=mass_var * 1e-6,
                label=f"x={frac:.3f}L",
            )
            for frac in jittered
        ]
        spec = rayleigh_perturbation(rod=rod_geo, perturbations=perturbations, n_modes=N_MODES)

        # Channel decomposition
        channels = []
        for ch in range(N_CHANNELS):
            modes = _channel_modes(ch)
            ch_shifts = [rd["fingerprint"][m - 1] for m in modes]
            channels.append({
                "channel": ch,
                "modes": modes,
                "shifts_hz": [round(s, 4) for s in ch_shifts],
            })

        rods_detail.append({
            "rod_id": rod_id,
            "pattern": pattern_name,
            "nominal_positions": positions,
            "jittered_positions": [round(j, 4) for j in jittered],
            "putty_mass_mg": round(mass_var, 4),
            "rod_length_mm": 150.0,
            "rod_diameter_mm": 6.0,
            "glass_type": "borosilicate",
            "unperturbed_hz": [round(f, 2) for f in spec.unperturbed_freqs.tolist()],
            "perturbed_hz": [round(f, 2) for f in rd["perturbed_hz"]],
            "shift_hz": [round(f, 4) for f in rd["fingerprint"]],
            "channels": channels,
        })

    # ── Rod cross-correlation matrix ──────────────────────────────────
    rod_ids = sorted(db.get("rods", {}).keys(), key=int)
    rod_fps = {rid: np.array(db["rods"][rid]["fingerprint"]) for rid in rod_ids}
    rod_xcorr = {}
    for r1 in rod_ids:
        row = {}
        for r2 in rod_ids:
            row[f"rod_{r2}"] = round(_correlate(rod_fps[r1], rod_fps[r2]), 4)
        rod_xcorr[f"rod_{r1}"] = row

    # ── User cross-correlation ────────────────────────────────────────
    user_names = list(db.get("users", {}).keys())
    user_xcorr = {}
    for u1 in user_names:
        ud1 = db["users"][u1]
        t1 = np.array(ud1["template"])
        row = {}
        for u2 in user_names:
            ud2 = db["users"][u2]
            if ud1["rod"] == ud2["rod"]:
                # Same rod: channel-level correlation
                t2 = np.array(ud2["template"])
                row[u2] = round(_correlate(t1, t2), 4)
            else:
                # Different rods: full fingerprint correlation
                fp1 = np.array(db["rods"][str(ud1["rod"])]["fingerprint"])
                fp2 = np.array(db["rods"][str(ud2["rod"])]["fingerprint"])
                row[u2] = round(_correlate(fp1, fp2), 4)
        user_xcorr[u1] = row

    # ── Face cross-correlation ────────────────────────────────────────
    face_db = _load_faces()
    face_names = list(face_db.get("faces", {}).keys())
    face_xcorr = {}
    for f1 in face_names:
        h1 = np.array(face_db["faces"][f1]["hash"])
        row = {}
        for f2 in face_names:
            h2 = np.array(face_db["faces"][f2]["hash"])
            row[f2] = round(_correlate(h1, h2), 4)
        face_xcorr[f1] = row

    # ── User slot map ─────────────────────────────────────────────────
    user_slots = []
    for uname, ud in db.get("users", {}).items():
        has_face = uname in face_db.get("faces", {})
        user_slots.append({
            "username": uname,
            "rod": ud["rod"],
            "channel": ud["channel"],
            "pattern": ud.get("rod_pattern", "?"),
            "modes": _channel_modes(ud["channel"]),
            "template": [round(v, 6) for v in ud["template"]],
            "has_face": has_face,
        })

    # ── Pipeline description ──────────────────────────────────────────
    pipeline = {
        "vault_auth": {
            "step_1": "Rod geometry: L=150mm, d=6mm borosilicate glass",
            "step_2": "Perturbation pattern (A/B/C/D) → putty positions along rod",
            "step_3": "Rayleigh perturbation theory → 20-mode frequency shift spectrum",
            "step_4": "Per-rod jitter (±1.5% position, ±15% mass) → unique physical fingerprint",
            "step_5": "Polysemic channel packing: modes 1-5 = Ch0, 6-10 = Ch1, 11-15 = Ch2, 16-20 = Ch3",
            "step_6": "User enrollment: 5-mode template extracted from assigned channel",
            "step_7": "Authentication: re-measure → Pearson correlation against template",
            "step_8": f"Pass if correlation ≥ {CORRELATION_THRESHOLD}",
            "physics_source": "simulations/glass_resonator.py → rayleigh_perturbation()",
        },
        "face_auth": {
            "step_1": "Webcam capture → JPEG",
            "step_2": "Pillow: convert to 8×8 grayscale → 64 pixel values",
            "step_3": "Average hash: pixel > mean → 64-bit binary vector",
            "step_4": "Compress 64 bits → 5-D target vector (group means, L2-normalised)",
            "step_5": "For each enrolled face: re-measure their assigned rod (PicoScope or Rayleigh)",
            "step_6": "Extract the face's channel from the 20-mode fingerprint → 5-D spectral vector",
            "step_7": "Correlate face-derived target against rod channel spectral vector",
            "step_8": f"Pass if spectral correlation ≥ {CORRELATION_THRESHOLD}",
            "key_point": "The face image is just the addressing key — authentication is gated by rod "
                         "spectral physics. No rod → no auth, even if the face matches perfectly.",
        },
        "why_hardware_matters": {
            "simulation_vs_real": "In simulation, rod fingerprints are deterministic from Rayleigh theory. "
                                 "With real hardware, the fingerprint comes from MEASURING the physical rod — "
                                 "manufacturing imperfections, exact putty placement, and temperature create a "
                                 "PUF (Physical Unclonable Function) that cannot be predicted or duplicated.",
            "what_changes_with_picoscope": "PicoScope 2204A replaces _compute_rod_fingerprint() with real FFT "
                                          "of PZT sensor output. Everything else (channel extraction, correlation, "
                                          "thresholding) stays identical.",
            "clonability": "Simulation fingerprints are reproducible from seed. Real rod fingerprints are not — "
                          "that's the security upgrade hardware provides.",
        },
    }

    return {
        "hardware_connected": HARDWARE_AVAILABLE,
        "measurement_source": "PicoScope 2204A (real FFT)" if HARDWARE_AVAILABLE else "Rayleigh simulation (deterministic)",
        "n_modes": N_MODES,
        "n_channels": N_CHANNELS,
        "modes_per_channel": MODES_PER_CHANNEL,
        "correlation_threshold": CORRELATION_THRESHOLD,
        "hash_size": HASH_SIZE,
        "hash_dim": HASH_DIM,
        "patterns": {k: v for k, v in NAMED_PATTERNS.items()},
        "rods": rods_detail,
        "rod_cross_correlation": rod_xcorr,
        "users": user_slots,
        "user_cross_correlation": user_xcorr,
        "face_cross_correlation": face_xcorr,
        "pipeline": pipeline,
    }


# ── HTTP server ───────────────────────────────────────────────────────────


def _json_safe(obj):
    """Handle non-JSON-serializable floats."""
    if isinstance(obj, float):
        if obj != obj:  # NaN
            return None
        if obj == float("inf") or obj == float("-inf"):
            return 999.0
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


def _sanitize_for_json(data):
    """Recursively replace inf/nan with safe values."""
    if isinstance(data, dict):
        return {k: _sanitize_for_json(v) for k, v in data.items()}
    if isinstance(data, list):
        return [_sanitize_for_json(v) for v in data]
    if isinstance(data, float):
        if data != data:
            return None
        if data == float("inf") or data == float("-inf"):
            return 999.0
    return data


# ── Scope / Experiment Wizard helpers ─────────────────────────────────────

FIREBASE_API_KEY = "AIzaSyCxlNaRNwwOim4-bSYL7MrRuQmDBznlga0"
CWM_SITE_URL = "https://coherent-wave-memory.web.app"

_capture_counter = 0


def _scope_status_safe() -> dict:
    """Return scope status, handling the case where the module is unavailable."""
    if SCOPE_FUNCTIONS_AVAILABLE:
        return _get_scope_status()
    return {
        "hardware_available": False,
        "scope_open": False,
        "driver": None,
        "config": None,
    }


def _scope_presets_safe() -> dict:
    if SCOPE_FUNCTIONS_AVAILABLE:
        return _get_experiment_presets()
    return {}


def _save_capture(capture: dict, spectrum: dict):
    """Persist the latest capture to disk for record-keeping."""
    global _capture_counter
    _capture_counter += 1
    cap_dir = DATA_DIR / "captures"
    cap_dir.mkdir(parents=True, exist_ok=True)
    fname = cap_dir / f"capture_{_capture_counter:04d}.json"
    payload = {
        "capture_id": _capture_counter,
        "n_samples": capture.get("n_samples"),
        "sample_rate": capture.get("sample_rate"),
        "range_mv": capture.get("range_mv"),
        "simulated": capture.get("simulated", False),
        "peaks": spectrum.get("peaks", []),
        "snr_db": spectrum.get("snr_db"),
        "noise_floor_db": spectrum.get("noise_floor_db"),
    }
    fname.write_text(json.dumps(payload, indent=2))


def _export_to_firebase(data: dict) -> dict:
    """Export experiment results to the community CWM Firebase project.

    Uses the Firebase Identity Toolkit REST API for anonymous auth,
    then POSTs to the cwm-site server-validated endpoint.
    """
    import urllib.request
    import urllib.error

    experiment_id = data.get("experiment_id")
    fields = data.get("data", {})
    nickname = data.get("nickname", "")
    location = data.get("location", "")
    notes = data.get("notes", "")

    if not experiment_id:
        return {"error": "experiment_id is required.", "status": 400}
    if not fields:
        return {"error": "data fields are required.", "status": 400}

    # Step 1: anonymous auth via Firebase REST API
    try:
        auth_url = (
            "https://identitytoolkit.googleapis.com/v1/accounts:signUp"
            f"?key={FIREBASE_API_KEY}"
        )
        auth_req = urllib.request.Request(
            auth_url,
            data=json.dumps({"returnSecureToken": True}).encode(),
            headers={"Content-Type": "application/json"},
        )
        auth_resp = json.loads(
            urllib.request.urlopen(auth_req, timeout=10).read()
        )
        id_token = auth_resp["idToken"]
    except Exception as e:
        return {"error": f"Firebase auth failed: {e}", "status": 401}

    # Step 2: submit to cwm-site validated endpoint
    try:
        submit_url = f"{CWM_SITE_URL}/api/submit-experiment"
        payload = {
            "experimentId": experiment_id,
            "data": fields,
            "nickname": nickname or None,
            "location": location or None,
            "notes": notes or None,
        }
        submit_req = urllib.request.Request(
            submit_url,
            data=json.dumps(payload).encode(),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {id_token}",
            },
        )
        resp_bytes = urllib.request.urlopen(submit_req, timeout=15).read()
        submit_resp = json.loads(resp_bytes)
        return {
            "ok": True,
            "submission_id": submit_resp.get("id"),
            "message": "Results submitted to community database!",
        }
    except urllib.error.HTTPError as e:
        error_body = e.read().decode() if e.fp else str(e)
        return {"error": f"Submission failed: {error_body}", "status": e.code}
    except Exception as e:
        return {"error": f"Submission failed: {e}", "status": 500}


class LabHandler(SimpleHTTPRequestHandler):
    """Handle API routes and serve the frontend."""

    n_rods = N_RODS_DEFAULT

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/" or path == "/index.html":
            self._serve_html()
        elif path == "/api/users":
            self._json_response(_list_users())
        elif path == "/api/faces":
            self._json_response(_get_faces())
        elif path == "/api/proof":
            self._json_response(_build_proof())
        elif path == "/api/scope/status":
            self._json_response(_scope_status_safe())
        elif path == "/api/rod-status":
            self._json_response(_get_rod_status())
        elif path.startswith("/api/user-rod"):
            # GET /api/user-rod?username=...
            qs = parse_qs(urlparse(self.path).query)
            username = qs.get("username", [""])[0].strip()
            if not username:
                self._json_response({"error": "username required"}, 400)
            else:
                db = _load_users()
                if username not in db.get("users", {}):
                    self._json_response({"found": False})
                else:
                    u = db["users"][username]
                    rod_key = str(u["rod"])
                    rod_data = db["rods"].get(rod_key, {})
                    self._json_response({
                        "found": True,
                        "rod": u["rod"],
                        "channel": u["channel"],
                        "pattern": rod_data.get("pattern", "?"),
                        "hardware": HARDWARE_AVAILABLE,
                    })
        elif path == "/api/scope/presets":
            self._json_response(_scope_presets_safe())
        elif path.startswith("/api/library/"):
            username = path.split("/api/library/", 1)[1]
            if username:
                self._json_response(_get_user_library(username))
            else:
                self._json_response({"error": "Username required."}, 400)
        else:
            self.send_error(404)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        content_length = int(self.headers.get("Content-Length", 0))
        if content_length > 25 * 1024 * 1024:  # 25 MB max
            self._json_response({"error": "Request too large."}, 413)
            return

        body = self.rfile.read(content_length)

        try:
            if path == "/api/register":
                data = json.loads(body)
                username = str(data.get("username", "")).strip()
                if not username or len(username) > 50:
                    self._json_response({"error": "Invalid username."}, 400)
                    return
                # Auto-assign next available slot
                db = _load_users()
                _ensure_rods(db)
                # Block registration if any rod is not yet enrolled
                unenrolled = [
                    k for k, v in db["rods"].items()
                    if not v.get("enrolled", False)
                ]
                if unenrolled:
                    self._json_response(
                        {"error": "Rods not enrolled yet. Complete the Rod Enrollment Wizard first.",
                         "unenrolled": sorted(unenrolled, key=int)}, 400
                    )
                    return
                used = set()
                for u, ud in db["users"].items():
                    used.add((ud["rod"], ud["channel"]))
                assigned = None
                for rod_id in range(1, len(db["rods"]) + 1):
                    for ch in range(N_CHANNELS):
                        if (rod_id, ch) not in used:
                            assigned = (rod_id, ch)
                            break
                    if assigned:
                        break
                if not assigned:
                    self._json_response(
                        {"error": "All slots taken. Max users reached."}, 409
                    )
                    return
                result = _register_user(username, assigned[0], assigned[1])
                self._json_response(result, 200 if result.get("ok") else 409)

            elif path == "/api/authenticate":
                data = json.loads(body)
                username = str(data.get("username", "")).strip()
                if not username:
                    self._json_response({"error": "Username required."}, 400)
                    return
                result = _authenticate_user(username)
                self._json_response(result)

            elif path == "/api/enroll-rod":
                data = json.loads(body)
                rod_id = int(data.get("rod_id", 0))
                pattern_name = data.get("pattern")
                if rod_id < 1:
                    self._json_response({"error": "Invalid rod_id."}, 400)
                    return
                result = _enroll_single_rod(rod_id, pattern_name)
                self._json_response(
                    result, 200 if result.get("ok") else 400
                )

            elif path == "/api/reset-rods":
                # Clear all rod data and re-initialize with simulation
                global HARDWARE_AVAILABLE
                db = _load_users()
                db["rods"] = {}
                db["users"] = {}
                HARDWARE_AVAILABLE = False  # force simulation mode
                _ensure_rods(db, N_RODS_DEFAULT)
                _save_users(db)
                self._json_response({"ok": True, "message": "Reset to simulation mode."})

            elif path == "/api/enroll-image":
                # Expect multipart-like JSON with base64 image
                data = json.loads(body)
                username = str(data.get("username", "")).strip()
                image_name = str(data.get("name", "")).strip()
                image_b64 = data.get("image", "")
                if not username or not image_name or not image_b64:
                    self._json_response(
                        {"error": "username, name, and image required."}, 400
                    )
                    return
                # Strip data URI prefix if present
                if "," in image_b64:
                    image_b64 = image_b64.split(",", 1)[1]
                image_bytes = base64.b64decode(image_b64)
                result = _enroll_image(username, image_name, image_bytes)
                self._json_response(result, 200 if result.get("ok") else 409)

            elif path == "/api/query-image":
                data = json.loads(body)
                username = str(data.get("username", "")).strip()
                image_b64 = data.get("image", "")
                if not username or not image_b64:
                    self._json_response(
                        {"error": "username and image required."}, 400
                    )
                    return
                if "," in image_b64:
                    image_b64 = image_b64.split(",", 1)[1]
                image_bytes = base64.b64decode(image_b64)
                result = _query_image(username, image_bytes)
                self._json_response(result)

            elif path == "/api/delete-image":
                data = json.loads(body)
                username = str(data.get("username", "")).strip()
                image_name = str(data.get("name", "")).strip()
                if not username or not image_name:
                    self._json_response(
                        {"error": "username and name required."}, 400
                    )
                    return
                result = _delete_user_image(username, image_name)
                self._json_response(result)

            elif path == "/api/enroll-face":
                data = json.loads(body)
                username = str(data.get("username", "")).strip()
                image_b64 = data.get("image", "")
                if not username or not image_b64:
                    self._json_response(
                        {"error": "username and image required."}, 400
                    )
                    return
                if "," in image_b64:
                    image_b64 = image_b64.split(",", 1)[1]
                image_bytes = base64.b64decode(image_b64)
                result = _enroll_face(username, image_bytes)
                self._json_response(result, 200 if result.get("ok") else 409)

            elif path == "/api/face-auth":
                data = json.loads(body)
                image_b64 = data.get("image", "")
                if not image_b64:
                    self._json_response(
                        {"error": "image required."}, 400
                    )
                    return
                if "," in image_b64:
                    image_b64 = image_b64.split(",", 1)[1]
                image_bytes = base64.b64decode(image_b64)
                result = _authenticate_face(image_bytes)
                self._json_response(result)

            # ── Scope / Experiment Wizard routes ──────────────
            elif path == "/api/scope/configure":
                data = json.loads(body)
                preset_id = str(data.get("preset_id", "exp03")).strip()
                pattern_name = str(data.get("pattern_name", "A")).strip()
                awg_freq = data.get("awg_freq_hz")
                if SCOPE_FUNCTIONS_AVAILABLE:
                    result = _configure_scope(
                        preset_id,
                        pattern_name=pattern_name,
                        awg_freq_hz=float(awg_freq) if awg_freq else None,
                    )
                    self._json_response(result)
                else:
                    self._json_response(
                        {"error": "Scope module not available."}, 503
                    )

            elif path == "/api/scope/capture":
                if SCOPE_FUNCTIONS_AVAILABLE:
                    capture = _capture_block()
                    if "error" in capture:
                        self._json_response(capture, 400)
                    else:
                        spectrum = _compute_spectrum(
                            capture["voltage_mv"], capture["sample_rate"]
                        )
                        # Save capture to data dir
                        _save_capture(capture, spectrum)
                        self._json_response(
                            {**capture, "spectrum": spectrum}
                        )
                else:
                    self._json_response(
                        {"error": "Scope module not available."}, 503
                    )

            elif path == "/api/scope/close":
                if SCOPE_FUNCTIONS_AVAILABLE:
                    self._json_response(_close_scope())
                else:
                    self._json_response({"ok": True})

            elif path == "/api/scope/export":
                data = json.loads(body)
                result = _export_to_firebase(data)
                status = 200 if result.get("ok") else result.pop("status", 500)
                self._json_response(result, status)

            # ── Quantum-Classical Bridge routes ───────────────
            elif path == "/api/qcb/multi-capture":
                data = json.loads(body)
                count = min(int(data.get("count", 5)), 20)
                if not SCOPE_FUNCTIONS_AVAILABLE:
                    self._json_response(
                        {"error": "Scope module not available."}, 503
                    )
                    return
                captures = []
                for i in range(count):
                    cap = _capture_block()
                    if "error" in cap:
                        self._json_response(cap, 400)
                        return
                    spec = _compute_spectrum(
                        cap["voltage_mv"], cap["sample_rate"]
                    )
                    captures.append({
                        "index": i,
                        "voltage_mv": cap["voltage_mv"][:200],  # truncate for transport
                        "sample_rate": cap["sample_rate"],
                        "n_samples": cap["n_samples"],
                        "spectrum": spec,
                    })
                self._json_response({"ok": True, "captures": captures, "count": count})

            elif path == "/api/qcb/parallel-search":
                db = _load_users()
                patterns = ["A", "B", "C", "D"]
                results = []
                t0 = __import__("time").time()
                for rod_id in range(1, min(N_RODS_DEFAULT + 1, 5)):
                    for pidx, pname in enumerate(patterns):
                        fp = _compute_rod_fingerprint(
                            pname, rod_id=rod_id
                        )
                        results.append({
                            "rod": rod_id,
                            "pattern": pname,
                            "fingerprint": fp.get("fingerprint", [])[:N_MODES],
                        })
                elapsed_ms = (__import__("time").time() - t0) * 1000
                # Correlate all against a random query (first pattern)
                if results:
                    query = np.array(results[0]["fingerprint"])
                    for r in results:
                        fp = np.array(r["fingerprint"])
                        if len(query) == len(fp) and len(fp) > 0:
                            r["correlation"] = float(np.corrcoef(query, fp)[0, 1])
                        else:
                            r["correlation"] = 0.0
                self._json_response({
                    "ok": True,
                    "query_pattern": results[0]["pattern"] if results else "A",
                    "query_rod": 1,
                    "results": results,
                    "elapsed_ms": round(elapsed_ms, 2),
                    "n_rods": N_RODS_DEFAULT,
                })

            else:
                self.send_error(404)

        except json.JSONDecodeError:
            self._json_response({"error": "Invalid JSON."}, 400)
        except Exception as e:
            self._json_response({"error": str(e)}, 500)

    def _json_response(self, data: dict, status: int = 200):
        body = json.dumps(_sanitize_for_json(data)).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _serve_html(self):
        html_path = Path(__file__).parent / "cwm_lab.html"
        if not html_path.exists():
            self.send_error(404, "cwm_lab.html not found")
            return
        body = html_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def log_message(self, format, *args):
        # Quieter logging
        if "/api/" in str(args[0]):
            sys.stderr.write(f"  {args[0]}\n")


def main():
    parser = argparse.ArgumentParser(description="CWM Lab — local experiment UI")
    parser.add_argument("--port", type=int, default=8200, help="Port (default: 8200)")
    parser.add_argument("--rods", type=int, default=4, help="Number of rods (default: 4)")
    args = parser.parse_args()

    LabHandler.n_rods = args.rods
    global N_RODS_DEFAULT
    N_RODS_DEFAULT = args.rods

    # Initialize rods on startup
    db = _load_users()
    _ensure_rods(db, args.rods)
    _save_users(db)

    hw_enrolled = sum(1 for r in db.get("rods", {}).values() if r.get("enrolled"))
    total_rods = len(db.get("rods", {}))

    server = HTTPServer(("127.0.0.1", args.port), LabHandler)
    mode = "HARDWARE (PicoScope 2204A)" if HARDWARE_AVAILABLE else "SIMULATION (Rayleigh)"
    print(f"CWM Lab running at http://localhost:{args.port}")
    print(f"  Mode:  {mode}")
    print(f"  Array: {args.rods} rods × {N_CHANNELS} channels = {args.rods * N_CHANNELS} slots")
    if HARDWARE_AVAILABLE and hw_enrolled < total_rods:
        print(f"  Rods enrolled: {hw_enrolled}/{total_rods} — complete enrollment in the browser")
    print(f"  Data:  {DATA_DIR}")
    print(f"  Press Ctrl+C to stop.\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.shutdown()


if __name__ == "__main__":
    main()
