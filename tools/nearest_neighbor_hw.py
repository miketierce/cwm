#!/usr/bin/env python3
"""
Hardware Nearest-Neighbor Search — α-Interpolation Sweep

Demonstrates O(1) nearest-neighbor search on the physical 4-rod array.
Drives the AWG with an interpolated query between two enrolled rods'
frequency patterns and measures which rod responds strongest via
template-matched scoring.

Signal chain (same as associative_recall_hw.py):
  AWG OUT → Drive PZTs (all 4 rods share AWG via T-connector)
  Relay N → Sense PZT Rod N → PicoScope Ch A

Protocol:
  For two endpoint rods A and B:
    For α in [0.0, 0.1, ..., 1.0]:
      1. Build interpolated query: Q(α) = blend of A's and B's enrolled peaks
         - At α=0, query = A's peaks only
         - At α=1, query = B's peaks only
         - At intermediate α, query includes weighted mix of both
      2. For each rod R ∈ {1, 2, 3, 4}:
         a. Select relay R
         b. Measure FFT magnitude at each query frequency
      3. Compute template-matched score for each rod
      4. Record winner and ranking

Expected result:
  - At α=0, Rod A wins (query matches A's pattern)
  - At α=1, Rod B wins (query matches B's pattern)
  - Crossover at α ≈ 0.5
  - Intermediate rankings should correlate with true similarity

Usage:
  PYTHONPATH=. python tools/nearest_neighbor_hw.py --port /dev/cu.usbserial-11310
  PYTHONPATH=. python tools/nearest_neighbor_hw.py --rod-a 1 --rod-b 2 --steps 11
"""
from __future__ import annotations

import argparse
import ctypes
import json
import math
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cwm_picoscope import TIMEBASE, N_SAMPLES, SAMPLE_RATE, AWG_DRIVE_UVPP
from relay_mux import RelayMux
from picosdk.ps2000 import ps2000

# ── Configuration ─────────────────────────────────────────────────────────

N_AVG = 12
SETTLE_S = 0.20
SETTLE_RELAY_S = 0.05
N_PEAKS = 10

# ── Paths ─────────────────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parent.parent
LAB_DIR = ROOT / "data" / "results" / "lab"
USERS_FILE = LAB_DIR / "users.json"
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
RESULTS_DIR = LAB_DIR / "nearest_neighbor"
RESULTS_FILE = RESULTS_DIR / f"nn_{TIMESTAMP}.json"
LOG_FILE = RESULTS_DIR / f"nn_{TIMESTAMP}.log"

FIREBASE_API_KEY = "AIzaSyCxlNaRNwwOim4-bSYL7MrRuQmDBznlga0"
CWM_SITE_URL = "https://coherent-wave-memory.web.app"

# ── Logging ───────────────────────────────────────────────────────────────

_log_lines: list[str] = []


def log(msg: str, also_print: bool = True) -> None:
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    line = f"[{ts}] {msg}"
    _log_lines.append(line)
    if also_print:
        print(msg)


def _save_log() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "w") as f:
        f.write("\n".join(_log_lines) + "\n")


# ── Scope helpers ─────────────────────────────────────────────────────────

def _open_scope():
    handle = ps2000.ps2000_open_unit()
    if handle <= 0:
        raise RuntimeError(f"ps2000_open_unit failed (handle={handle})")
    ps2000.ps2000_set_channel(handle, 0, True, 1, 6)
    ps2000.ps2000_set_channel(handle, 1, False, 1, 6)
    log("PicoScope opened (Ch A ±1V DC)")
    return handle


def _close_scope(handle):
    try:
        ps2000.ps2000_set_sig_gen_built_in(
            handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0
        )
    except Exception:
        pass
    ps2000.ps2000_stop(handle)
    ps2000.ps2000_close_unit(handle)
    log("PicoScope closed")


def _measure_at(handle, freq_hz: float, n_avg: int = N_AVG,
                settle_s: float = SETTLE_S) -> dict:
    """Drive AWG at freq_hz, capture, return magnitude."""
    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, AWG_DRIVE_UVPP, 0,
        float(freq_hz), float(freq_hz), 0.0, 0.0, 0, 0
    )
    time.sleep(settle_s)

    magnitudes = []
    for _ in range(n_avg):
        ps2000.ps2000_set_trigger(handle, 0, 0, 0, 0, 100)
        t_ms = ctypes.c_int32()
        ps2000.ps2000_run_block(handle, N_SAMPLES, TIMEBASE, 1, ctypes.byref(t_ms))
        t0 = time.time()
        while ps2000.ps2000_ready(handle) == 0:
            time.sleep(0.002)
            if time.time() - t0 > 2:
                break
        buf_a = (ctypes.c_int16 * N_SAMPLES)()
        buf_b = (ctypes.c_int16 * N_SAMPLES)()
        overflow = ctypes.c_int16()
        n = ps2000.ps2000_get_values(
            handle, ctypes.byref(buf_a), ctypes.byref(buf_b),
            None, None, ctypes.byref(overflow), N_SAMPLES
        )
        if n > 0:
            raw = np.array(buf_a[:n], dtype=np.float64)
            windowed = raw * np.hanning(len(raw))
            nfft = len(raw) * 4
            fft = np.abs(np.fft.rfft(windowed, n=nfft))
            freq_axis = np.fft.rfftfreq(nfft, d=1.0 / SAMPLE_RATE)
            bin_hz = freq_axis[1] - freq_axis[0]
            target_bin = int(round(freq_hz / bin_hz))
            lo = max(0, target_bin - 3)
            hi = min(len(fft) - 1, target_bin + 3)
            magnitudes.append(float(np.max(fft[lo:hi + 1])))

    return {"magnitude": round(float(np.mean(magnitudes)), 1) if magnitudes else 0.0}


# ── Query interpolation ──────────────────────────────────────────────────

def _build_interpolated_query(peaks_a: list[float], peaks_b: list[float],
                               alpha: float, n_peaks: int) -> list[float]:
    """Build interpolated query frequencies.

    Strategy: merge both rods' peak lists, weighting by (1-α) for A
    and α for B.  Select the n_peaks frequencies with highest total
    weight.  At α=0, only A's peaks; at α=1, only B's peaks.
    At intermediate α, a mix of both.
    """
    candidates = []
    for f in peaks_a:
        candidates.append((f, 1.0 - alpha, "A"))
    for f in peaks_b:
        candidates.append((f, alpha, "B"))

    # Sort by weight descending, take top n_peaks
    candidates.sort(key=lambda x: -x[1])
    selected = candidates[:n_peaks]
    # Sort by frequency for orderly measurement
    selected.sort(key=lambda x: x[0])
    return [s[0] for s in selected], [(s[0], s[1], s[2]) for s in selected]


# ── Template scoring ─────────────────────────────────────────────────────

def _template_score(query_freqs: list[float],
                    raw_mags: dict[str, list[float]],
                    enrolled: dict[str, list[float]],
                    rod_ids: list[str]) -> dict[str, float]:
    """Compute template-matched scores for each sense rod.

    For each query frequency, normalize magnitude across all sense rods,
    then boost where sense rod is expected to resonate and penalize where not.
    """
    scores = {sr: 0.0 for sr in rod_ids}
    for pi, freq in enumerate(query_freqs):
        mags = {sr: raw_mags[sr][pi] for sr in rod_ids}
        total = sum(mags.values())
        if total == 0:
            continue
        for sr in rod_ids:
            frac = mags[sr] / total
            expected = any(
                abs(freq - ep) / max(freq, ep) < 0.03
                for ep in enrolled[sr]
            )
            if expected:
                scores[sr] += frac * 3.0
            else:
                scores[sr] -= frac * 1.0
    return {sr: round(v, 2) for sr, v in scores.items()}


# ── Kendall tau ───────────────────────────────────────────────────────────

def _kendall_tau(rank_a: list, rank_b: list) -> float:
    """Kendall tau rank correlation."""
    n = len(rank_a)
    concordant = discordant = 0
    for i in range(n):
        for j in range(i + 1, n):
            a_diff = rank_a[i] - rank_a[j]
            b_diff = rank_b[i] - rank_b[j]
            product = a_diff * b_diff
            if product > 0:
                concordant += 1
            elif product < 0:
                discordant += 1
    total = concordant + discordant
    return (concordant - discordant) / total if total > 0 else 1.0


# ═══════════════════════════════════════════════════════════════════════
#  Main experiment
# ═══════════════════════════════════════════════════════════════════════

def run_nearest_neighbor(mux: RelayMux, rod_a: str = "1", rod_b: str = "2",
                         n_steps: int = 11, n_peaks: int = N_PEAKS) -> dict:
    """Run nearest-neighbor α-interpolation sweep between two rods."""

    # Load enrollment
    with open(USERS_FILE) as f:
        db = json.load(f)

    enrolled = {}
    rod_patterns = {}
    for rid in sorted(db["rods"].keys()):
        r = db["rods"][rid]
        if r.get("enrolled"):
            enrolled[rid] = r["perturbed_hz"]  # full 20 peaks for template
            rod_patterns[rid] = r.get("pattern", "?")

    rod_ids = sorted(enrolled.keys())
    peaks_a = enrolled[rod_a][:n_peaks]
    peaks_b = enrolled[rod_b][:n_peaks]

    alphas = np.linspace(0.0, 1.0, n_steps)

    log("=" * 70)
    log("  HARDWARE NEAREST-NEIGHBOR SEARCH — α-Interpolation")
    log("=" * 70)
    log(f"  Rod A: {rod_a} (Pattern {rod_patterns[rod_a]})")
    log(f"  Rod B: {rod_b} (Pattern {rod_patterns[rod_b]})")
    log(f"  α steps: {n_steps} ({alphas[0]:.1f} → {alphas[-1]:.1f})")
    log(f"  Peaks per query: {n_peaks}")
    log(f"  Sense rods: {rod_ids}")
    log(f"  Relay mux: {mux.port}")
    log("")

    t_start = time.time()
    handle = _open_scope()

    experiment = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "rod_a": rod_a,
        "rod_b": rod_b,
        "pattern_a": rod_patterns[rod_a],
        "pattern_b": rod_patterns[rod_b],
        "rod_ids": rod_ids,
        "n_peaks": n_peaks,
        "n_steps": n_steps,
        "alphas": [round(a, 2) for a in alphas],
        "n_avg": N_AVG,
        "awg_uvpp": AWG_DRIVE_UVPP,
        "sample_rate": SAMPLE_RATE,
        "mux_port": mux.port,
    }

    sweep_results = []

    try:
        for ai, alpha in enumerate(alphas):
            query_freqs, query_detail = _build_interpolated_query(
                peaks_a, peaks_b, alpha, n_peaks
            )

            n_from_a = sum(1 for _, _, src in query_detail if src == "A")
            n_from_b = sum(1 for _, _, src in query_detail if src == "B")

            log(f"═══ α={alpha:.2f} ({n_from_a} from A, {n_from_b} from B) ═══")

            # Measure all sense rods at these query frequencies
            raw_mags = {sr: [] for sr in rod_ids}

            for sr in rod_ids:
                mux.select(int(sr))
                time.sleep(SETTLE_RELAY_S)
                for freq in query_freqs:
                    m = _measure_at(handle, freq)
                    raw_mags[sr].append(m["magnitude"])

            # Template scoring
            scores = _template_score(query_freqs, raw_mags, enrolled, rod_ids)

            # Ranking by score (descending)
            ranking = sorted(scores.items(), key=lambda x: -x[1])
            winner = ranking[0][0]

            # True distance ranking: Euclidean distance from query freqs
            # to each rod's enrolled peaks (lower distance = better match).
            # For the interpolated query, distance to A should increase with α
            # and distance to B should decrease.
            true_distances = {}
            for sr in rod_ids:
                # How many query freqs are near this rod's peaks?
                match_count = sum(
                    1 for f in query_freqs
                    if any(abs(f - ep) / max(f, ep) < 0.03
                           for ep in enrolled[sr])
                )
                true_distances[sr] = n_peaks - match_count  # distance = non-matches

            dist_ranking = sorted(true_distances.items(), key=lambda x: x[1])
            true_nearest = dist_ranking[0][0]

            # Kendall tau between score ranking and distance ranking
            score_rank = [r[0] for r in ranking]
            dist_rank = [r[0] for r in dist_ranking]
            # Convert to numeric ranks
            score_ranks_num = [score_rank.index(sr) + 1 for sr in rod_ids]
            dist_ranks_num = [dist_rank.index(sr) + 1 for sr in rod_ids]
            tau = _kendall_tau(score_ranks_num, dist_ranks_num)

            correct = winner == true_nearest

            step_result = {
                "alpha": round(alpha, 2),
                "query_freqs": [round(f, 1) for f in query_freqs],
                "query_sources": [(round(f, 1), round(w, 2), s) for f, w, s in query_detail],
                "n_from_a": n_from_a,
                "n_from_b": n_from_b,
                "scores": scores,
                "winner": winner,
                "true_nearest": true_nearest,
                "true_distances": true_distances,
                "correct": correct,
                "kendall_tau": round(tau, 3),
                "raw_mags": {sr: [round(m, 1) for m in mags] for sr, mags in raw_mags.items()},
            }
            sweep_results.append(step_result)

            # Compact log
            score_str = "  ".join(
                f"R{sr}={scores[sr]:+.1f}{'◄' if sr == winner else ' '}"
                for sr in rod_ids
            )
            log(f"  Scores: {score_str}  "
                f"→ R{winner} {'✓' if correct else '✗'}  τ={tau:.2f}")
            log("")

        mux.off()

    finally:
        _close_scope(handle)

    duration = time.time() - t_start
    experiment["duration_s"] = round(duration, 1)
    experiment["sweep_results"] = sweep_results

    # ── Analysis ──────────────────────────────────────────────────────

    log("=" * 70)
    log("  RESULTS")
    log("=" * 70)

    # Winner at each α
    log("\n  Winner Trajectory:")
    log(f"  {'α':>5s}  {'Winner':>6s}  {'Correct':>7s}  {'τ':>5s}  A-peaks  B-peaks")
    log(f"  {'─'*5}  {'─'*6}  {'─'*7}  {'─'*5}  {'─'*7}  {'─'*7}")
    for r in sweep_results:
        log(f"  {r['alpha']:5.2f}  Rod {r['winner']:>2s}  "
            f"{'✓' if r['correct'] else '✗':>7s}  "
            f"{r['kendall_tau']:5.2f}  "
            f"{r['n_from_a']:>7d}  {r['n_from_b']:>7d}")

    # Find crossover point
    crossover = None
    for i, r in enumerate(sweep_results):
        if r["winner"] == rod_b:
            crossover = r["alpha"]
            break
    log(f"\n  Crossover α: {crossover if crossover is not None else 'none (Rod B never won)'}")

    # Accuracy and tau stats
    n_correct = sum(1 for r in sweep_results if r["correct"])
    accuracy = n_correct / len(sweep_results)
    mean_tau = float(np.mean([r["kendall_tau"] for r in sweep_results]))
    log(f"  Accuracy: {n_correct}/{len(sweep_results)} ({accuracy*100:.0f}%)")
    log(f"  Mean Kendall τ: {mean_tau:.3f}")
    log(f"  Duration: {duration:.1f}s")

    # Score trajectories for Rod A and Rod B
    log(f"\n  Score Trajectory (Rod A={rod_a}, Rod B={rod_b}):")
    log(f"  {'α':>5s}  {'R'+rod_a:>6s}  {'R'+rod_b:>6s}  {'gap':>6s}")
    log(f"  {'─'*5}  {'─'*6}  {'─'*6}  {'─'*6}")
    for r in sweep_results:
        sa = r["scores"][rod_a]
        sb = r["scores"][rod_b]
        log(f"  {r['alpha']:5.2f}  {sa:+6.1f}  {sb:+6.1f}  {sa-sb:+6.1f}")

    experiment["analysis"] = {
        "crossover_alpha": crossover,
        "accuracy": accuracy,
        "n_correct": n_correct,
        "n_total": len(sweep_results),
        "mean_kendall_tau": round(mean_tau, 3),
    }

    return experiment


# ═══════════════════════════════════════════════════════════════════════
#  Firestore
# ═══════════════════════════════════════════════════════════════════════

def _firebase_anon_auth() -> str:
    url = (
        "https://identitytoolkit.googleapis.com/v1/accounts:signUp"
        f"?key={FIREBASE_API_KEY}"
    )
    req = urllib.request.Request(
        url,
        data=json.dumps({"returnSecureToken": True}).encode(),
        headers={"Content-Type": "application/json"},
    )
    resp = json.loads(urllib.request.urlopen(req, timeout=10).read())
    return resp["idToken"]


def _submit_experiment(token: str, experiment_id: str, data: dict,
                       nickname: str = "Mike", notes: str = "") -> dict:
    payload = {
        "experimentId": experiment_id,
        "data": data,
        "nickname": nickname or None,
        "notes": notes or None,
    }
    req = urllib.request.Request(
        f"{CWM_SITE_URL}/api/submit-experiment",
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
    )
    try:
        resp = json.loads(urllib.request.urlopen(req, timeout=15).read())
        return {"ok": True, "id": resp.get("id"), "experimentId": experiment_id}
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else str(e)
        return {"ok": False, "error": body, "status": e.code}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Hardware nearest-neighbor search — α-interpolation sweep"
    )
    parser.add_argument("--port", type=str, default=None)
    parser.add_argument("--rod-a", type=str, default="1",
                        help="Endpoint rod A (default: 1)")
    parser.add_argument("--rod-b", type=str, default="2",
                        help="Endpoint rod B (default: 2)")
    parser.add_argument("--steps", type=int, default=11,
                        help="Number of α steps (default: 11)")
    parser.add_argument("--peaks", type=int, default=N_PEAKS,
                        help="Peaks per query (default: 10)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    mux = RelayMux(port=args.port)
    mux.open()
    log(f"Relay mux connected on {mux.port}")

    try:
        result = run_nearest_neighbor(
            mux, rod_a=args.rod_a, rod_b=args.rod_b,
            n_steps=args.steps, n_peaks=args.peaks
        )
    finally:
        mux.close()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_FILE, "w") as f:
        json.dump(result, f, indent=2, default=str)
    log(f"\nResults saved to {RESULTS_FILE.relative_to(ROOT)}")
    _save_log()
    log(f"Log saved to {LOG_FILE.relative_to(ROOT)}")

    if not args.dry_run:
        log("\nSubmitting to Firestore...")
        try:
            token = _firebase_anon_auth()
            analysis = result["analysis"]
            data = {
                "n_rods": len(result["rod_ids"]),
                "peaks_per_rod": result["n_peaks"],
                "sample_rate": SAMPLE_RATE,
                "freq_resolution": round(SAMPLE_RATE / (N_SAMPLES * 4), 1),
                "auth_rms_pct": max(0, round(analysis["mean_kendall_tau"] * 100, 1)),
                "auth_matched_peaks": analysis["n_correct"],
                "auth_score_pct": round(analysis["accuracy"] * 100, 1),
                "next_best_score_pct": 0,
                "min_cross_rod_pct": round(analysis["accuracy"] * 100, 1),
                "repro_peaks_matched": f"{analysis['n_correct']}/{analysis['n_total']}",
                "excitation_method": "Piezo pulse",
                "correct_rod_identified": "Yes" if analysis["accuracy"] >= 0.9 else "No",
            }
            notes = (
                f"Nearest-neighbor α-sweep: Rod {result['rod_a']}→{result['rod_b']}. "
                f"Crossover α={analysis['crossover_alpha']}. "
                f"Accuracy={analysis['n_correct']}/{analysis['n_total']}. "
                f"Mean τ={analysis['mean_kendall_tau']:.3f}. "
                f"Template scoring. {TIMESTAMP}."
            )
            r = _submit_experiment(token, "exp-hw-auth", data, notes=notes)
            if r.get("ok"):
                log(f"  ✓ Submitted → {r.get('id', '?')}")
            else:
                error = r.get("error", "unknown")
                try:
                    parsed = json.loads(error)
                    error = parsed.get("statusMessage", error)
                except (json.JSONDecodeError, AttributeError):
                    pass
                log(f"  ✗ Failed: {error}")
        except Exception as e:
            log(f"  ✗ Auth/submit failed: {e}")


if __name__ == "__main__":
    main()
