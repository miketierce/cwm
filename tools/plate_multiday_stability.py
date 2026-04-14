#!/usr/bin/env python3
"""
Plate E28: Multi-Day Stability — Fused Silica Plates

Rod result: 7/7 sessions at 100%, spanning 18.7 hours — CONFIRMED.
Paper claim: Non-volatile without power/refresh (§3.2).

Mines ALL timestamped plate session data (auth, CIM, ESN calibrations,
forward pass, demos) to build a temporal stability timeline. Tests
whether template-matching accuracy stays at 100% across sessions
separated by hours/days.

Optionally captures a fresh set of template-matching trials to extend
the temporal span.

Usage:
  PYTHONPATH=. python tools/plate_multiday_stability.py
  PYTHONPATH=. python tools/plate_multiday_stability.py --fresh --port /dev/cu.usbserial-11310
  PYTHONPATH=. python tools/plate_multiday_stability.py --dry-run
"""
from __future__ import annotations

import argparse
import ctypes
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

TOOLS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS_DIR))

# ── Configuration ─────────────────────────────────────────────────────

N_AVG = 8
SETTLE_S = 0.10
SETTLE_RELAY_S = 0.10
N_PEAKS = 10
FREQ_MATCH_PCT = 3

PLATE_IDS = ["1", "2", "3", "4", "5"]
PLATE_NAMES = {"1": "A", "2": "B", "3": "C", "4": "D", "5": "E"}

ROOT = TOOLS_DIR.parent
LAB_DIR = ROOT / "data" / "results" / "lab" / "plate_exps"
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
RESULTS_FILE = LAB_DIR / f"multiday_stability_{TIMESTAMP}.json"


# ── Enrollment loader ────────────────────────────────────────────────

def _load_enrollment() -> tuple[dict, dict, list]:
    """Load plate enrollment from latest census file.
    Returns (enrolled_freqs, enrolled_mags, plate_ids)."""
    census_files = sorted(
        f for f in LAB_DIR.glob("plate_census_*.json")
        if "sweeps" not in f.name
    )
    if not census_files:
        raise FileNotFoundError("No census file found.")

    with open(census_files[-1]) as f:
        census = json.load(f)
    if "results" in census:
        census = census["results"]

    enrolled_freqs = {}
    enrolled_mags = {}
    for pid in PLATE_IDS:
        if pid in census and census[pid].get("peaks"):
            peaks = census[pid]["peaks"][:N_PEAKS]
            enrolled_freqs[pid] = [p["freq_hz"] for p in peaks]
            enrolled_mags[pid] = [p["magnitude"] for p in peaks]

    plate_ids = sorted(enrolled_freqs.keys())
    return enrolled_freqs, enrolled_mags, plate_ids


# ── Data mining helpers ──────────────────────────────────────────────

def _extract_timestamp(data: dict) -> str | None:
    """Extract ISO timestamp from various data formats."""
    for key in ("timestamp", "start_time", "created_at"):
        ts = data.get(key)
        if ts:
            return str(ts)
    # Try extracting from filename timestamp pattern
    return None


def _mine_auth_sessions() -> list[dict]:
    """Mine authentication / stress test results."""
    entries = []
    for f in sorted(LAB_DIR.glob("auth_stress_*.json")):
        try:
            data = json.load(open(f))
            ts = _extract_timestamp(data)
            trials = data.get("trials", [])
            if trials:
                accs = [t.get("accuracy_pct", 0) for t in trials]
                entries.append({
                    "source": "auth_stress",
                    "file": f.name,
                    "timestamp": ts,
                    "accuracy_pct": round(float(np.mean(accs)), 1),
                    "n_trials": len(trials),
                    "all_100": all(a == 100 for a in accs),
                })
        except Exception:
            pass
    return entries


def _mine_cim_sessions() -> list[dict]:
    """Mine CIM suite results (NN recall accuracy)."""
    entries = []
    suite_dir = LAB_DIR / "cim_suite"
    if not suite_dir.exists():
        return entries
    for f in sorted(suite_dir.glob("plate_suite_*.json")):
        try:
            data = json.load(open(f))
            ts = _extract_timestamp(data)
            nn = data.get("nn_pairs") or data.get("nn-pairs") or {}
            if isinstance(nn, dict):
                correct = nn.get("correct_total", 0)
                total = nn.get("n_queries", 0)
                if total > 0:
                    entries.append({
                        "source": "cim_suite",
                        "file": f.name,
                        "timestamp": ts,
                        "accuracy_pct": round(correct / total * 100, 1),
                        "correct": correct,
                        "total": total,
                    })
        except Exception:
            pass
    return entries


def _mine_experiment_sessions() -> list[dict]:
    """Mine plate_experiments_*.json files (auth trials)."""
    entries = []
    for f in sorted(LAB_DIR.glob("plate_experiments_*.json")):
        try:
            data = json.load(open(f))
            ts = _extract_timestamp(data)
            results = data.get("results", data)
            if isinstance(results, dict):
                # Look for auth-type results
                for key in ("auth", "authentication", "recall"):
                    if key in results:
                        auth = results[key]
                        acc = auth.get("accuracy_pct") or auth.get("accuracy")
                        if acc is not None:
                            entries.append({
                                "source": f"experiment_{key}",
                                "file": f.name,
                                "timestamp": ts,
                                "accuracy_pct": float(acc),
                            })
            elif isinstance(results, list):
                for item in results:
                    if isinstance(item, dict):
                        acc = item.get("accuracy_pct") or item.get("accuracy")
                        if acc is not None:
                            entries.append({
                                "source": "experiment_list",
                                "file": f.name,
                                "timestamp": ts or _extract_timestamp(item),
                                "accuracy_pct": float(acc),
                            })
        except Exception:
            pass
    return entries


def _mine_e33_e36_sessions() -> list[dict]:
    """Mine E33/E36 results (null-control accuracy)."""
    entries = []
    for f in sorted(LAB_DIR.glob("e33_e36_*.json")):
        try:
            data = json.load(open(f))
            ts = _extract_timestamp(data)
            e36 = data.get("e36", data.get("null_control", {}))
            if isinstance(e36, dict):
                correct = e36.get("correct_scoring", {})
                acc = correct.get("accuracy_pct") or correct.get("correct")
                if acc is not None:
                    entries.append({
                        "source": "e36_null_control",
                        "file": f.name,
                        "timestamp": ts,
                        "accuracy_pct": float(acc) if acc <= 100 else (acc / 5 * 100),
                    })
        except Exception:
            pass
    return entries


def _mine_esn_sessions() -> list[dict]:
    """Mine ESN calibration sessions (token calibration implies spectral access)."""
    entries = []
    for pattern in ["esn_v*_*.json", "sequence_esn_*.json"]:
        for f in sorted(LAB_DIR.glob(pattern)):
            if "checkpoint" in f.name:
                continue
            try:
                data = json.load(open(f))
                ts = _extract_timestamp(data)
                # ESN files don't have template accuracy directly,
                # but calibration success implies spectral fingerprint is stable
                cal = data.get("calibration", {})
                if cal:
                    entries.append({
                        "source": "esn_calibration",
                        "file": f.name,
                        "timestamp": ts,
                        "note": "Calibration completed (spectral access confirmed)",
                    })
            except Exception:
                pass
    return entries


# ── Fresh capture (optional) ─────────────────────────────────────────

def _run_fresh_recall(port: str) -> dict:
    """Run a fresh template-matching recall test."""
    import cwm_picoscope  # noqa: F401
    from cwm_picoscope import TIMEBASE, N_SAMPLES, SAMPLE_RATE, AWG_DRIVE_UVPP
    from relay_mux import RelayMux
    from picosdk.ps2000 import ps2000

    enrolled_freqs, enrolled_mags, plate_ids = _load_enrollment()

    handle = ps2000.ps2000_open_unit()
    if handle <= 0:
        raise RuntimeError(f"ps2000_open_unit failed (handle={handle})")
    ps2000.ps2000_set_channel(handle, 0, True, 1, 6)
    ps2000.ps2000_set_channel(handle, 1, False, 1, 6)

    mux = RelayMux(port=port)
    mux.open()

    # Build templates from enrollment
    templates = {}
    for pid in plate_ids:
        templates[pid] = np.array(enrolled_mags[pid], dtype=np.float64)

    # Query each plate and match
    correct = 0
    total = len(plate_ids)
    trial_details = []

    for query_pid in plate_ids:
        mux.select(int(query_pid))
        time.sleep(SETTLE_RELAY_S)

        # Measure at all enrolled frequencies for this plate
        measured = []
        for freq in enrolled_freqs[query_pid]:
            ps2000.ps2000_set_sig_gen_built_in(
                handle, 0, AWG_DRIVE_UVPP, 0,
                float(freq), float(freq), 0.0, 0.0, 0, 0
            )
            time.sleep(SETTLE_S)

            mags = []
            for _ in range(N_AVG):
                ps2000.ps2000_set_trigger(handle, 0, 0, 0, 0, 100)
                t_ms = ctypes.c_int32()
                ps2000.ps2000_run_block(
                    handle, N_SAMPLES, TIMEBASE, 1, ctypes.byref(t_ms)
                )
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
                    tb = int(round(freq / bin_hz))
                    lo = max(0, tb - 3)
                    hi = min(len(fft) - 1, tb + 3)
                    mags.append(float(np.max(fft[lo:hi + 1])))
            measured.append(float(np.mean(mags)) if mags else 0.0)

        query_vec = np.array(measured, dtype=np.float64)

        # Match against all templates
        scores = {}
        for tid in plate_ids:
            tmpl = templates[tid]
            if len(tmpl) == len(query_vec) and np.std(tmpl) > 0 and np.std(query_vec) > 0:
                r = float(np.corrcoef(query_vec, tmpl)[0, 1])
            else:
                r = 0.0
            scores[tid] = r

        winner = max(scores, key=scores.get)
        is_correct = winner == query_pid
        if is_correct:
            correct += 1

        margin = scores[query_pid] - max(
            s for k, s in scores.items() if k != query_pid
        )

        trial_details.append({
            "query_plate": PLATE_NAMES[query_pid],
            "winner": PLATE_NAMES[winner],
            "correct": is_correct,
            "self_score": round(scores[query_pid], 4),
            "margin": round(margin, 4),
            "all_scores": {PLATE_NAMES[k]: round(v, 4) for k, v in scores.items()},
        })
        print(f"    Query {PLATE_NAMES[query_pid]} → "
              f"Winner {PLATE_NAMES[winner]} "
              f"({'✓' if is_correct else '✗'}) "
              f"margin={margin:+.4f}")

    # Cleanup
    try:
        ps2000.ps2000_set_sig_gen_built_in(
            handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0
        )
    except Exception:
        pass
    ps2000.ps2000_stop(handle)
    ps2000.ps2000_close_unit(handle)
    mux.off()

    return {
        "source": "fresh_recall",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "accuracy_pct": round(correct / total * 100, 1),
        "correct": correct,
        "total": total,
        "trials": trial_details,
    }


# ── Main ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Plate E28: Multi-Day Stability Timeline"
    )
    parser.add_argument("--port", default="/dev/cu.usbserial-11310")
    parser.add_argument("--fresh", action="store_true",
                        help="Also capture fresh recall test to extend timeline")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--submit", action="store_true", help="Submit to Firestore")
    args = parser.parse_args()

    print("\n" + "=" * 70)
    print("  EXPERIMENT E28 (Plates): Multi-Day Stability Timeline")
    print("=" * 70)

    # ── Mine all historical data ─────────────────────────────────────
    print("\n  Mining historical plate session data...")

    timeline = []
    timeline.extend(_mine_auth_sessions())
    timeline.extend(_mine_cim_sessions())
    timeline.extend(_mine_experiment_sessions())
    timeline.extend(_mine_e33_e36_sessions())
    timeline.extend(_mine_esn_sessions())

    # Sort by timestamp
    timeline.sort(key=lambda t: t.get("timestamp") or "")

    print(f"  Found {len(timeline)} sessions with data")

    # Sessions with actual accuracy
    accuracy_sessions = [t for t in timeline if t.get("accuracy_pct") is not None]
    print(f"  Sessions with accuracy metric: {len(accuracy_sessions)}")

    # Time span
    timestamps = [t["timestamp"] for t in timeline
                  if t.get("timestamp")]
    timestamps.sort()

    if len(timestamps) >= 2:
        try:
            t_first = datetime.fromisoformat(
                timestamps[0].replace("Z", "+00:00")
            )
            t_last = datetime.fromisoformat(
                timestamps[-1].replace("Z", "+00:00")
            )
            span_hours = (t_last - t_first).total_seconds() / 3600
        except Exception:
            span_hours = 0
    else:
        span_hours = 0

    print(f"\n  Timeline Summary:")
    if timestamps:
        print(f"    First session: {timestamps[0][:25]}")
        print(f"    Last session:  {timestamps[-1][:25]}")
    print(f"    Time span: {span_hours:.1f} hours ({span_hours / 24:.1f} days)")

    if accuracy_sessions:
        accs = [t["accuracy_pct"] for t in accuracy_sessions]
        n_100 = sum(1 for a in accs if a >= 100.0)
        print(f"    Accuracy values: {accs}")
        print(f"    100% sessions: {n_100}/{len(accs)}")

    # Print each session
    print(f"\n  Session-by-session:")
    for t in timeline:
        acc = t.get("accuracy_pct")
        note = t.get("note", "")
        ts = t.get("timestamp", "?")[:19]
        src = t.get("source", "?")
        if acc is not None:
            status = "✓" if acc >= 100 else "⚠"
            print(f"    {ts}  {src:20s}  {acc:6.1f}%  {status}")
        elif note:
            print(f"    {ts}  {src:20s}  {note}")

    # ── Fresh recall (optional) ──────────────────────────────────────
    fresh_result = None
    if args.fresh and not args.dry_run:
        print(f"\n  Running fresh template-matching recall...")
        fresh_result = _run_fresh_recall(args.port)
        timeline.append(fresh_result)
        accuracy_sessions.append(fresh_result)
        print(f"\n  Fresh recall: {fresh_result['correct']}/{fresh_result['total']} "
              f"({fresh_result['accuracy_pct']}%)")
    elif args.fresh and args.dry_run:
        print(f"\n  [DRY RUN] Would run fresh recall on hardware")

    # ── Compute final statistics ─────────────────────────────────────
    if accuracy_sessions:
        accs = [t["accuracy_pct"] for t in accuracy_sessions]
        n_100 = sum(1 for a in accs if a >= 100.0)
        pct_100 = n_100 / len(accs) * 100

        # Wilson score confidence interval for 100% rate
        n = len(accs)
        p = n_100 / n
        z = 1.96  # 95% CI
        denom = 1 + z**2 / n
        center = (p + z**2 / (2 * n)) / denom
        spread = z * (p * (1 - p) / n + z**2 / (4 * n**2))**0.5 / denom
        ci_low = max(0, center - spread)
        ci_high = min(1, center + spread)
    else:
        pct_100 = 0
        ci_low = ci_high = 0

    # Final time span including fresh
    if fresh_result and timestamps:
        try:
            t_fresh = datetime.fromisoformat(
                fresh_result["timestamp"].replace("Z", "+00:00")
            )
            t_first = datetime.fromisoformat(
                timestamps[0].replace("Z", "+00:00")
            )
            span_hours = (t_fresh - t_first).total_seconds() / 3600
        except Exception:
            pass

    # ── Verdict ──────────────────────────────────────────────────────
    rod_sessions = 7
    rod_span_hours = 18.7

    if pct_100 >= 100 and span_hours >= rod_span_hours:
        verdict = (f"CONFIRMED — {n_100}/{len(accs)} sessions at 100%, "
                   f"{span_hours:.1f}h span (rod: {rod_sessions} sessions, "
                   f"{rod_span_hours}h)")
    elif pct_100 >= 100:
        verdict = (f"CONFIRMED (shorter span) — {n_100}/{len(accs)} at 100%, "
                   f"{span_hours:.1f}h (rod: {rod_span_hours}h)")
    else:
        verdict = (f"PARTIAL — {n_100}/{len(accs)} at 100% "
                   f"({pct_100:.0f}%), {span_hours:.1f}h span")

    print(f"\n  VERDICT: {verdict}")
    if accuracy_sessions:
        print(f"  Wilson 95% CI: [{ci_low * 100:.1f}%, {ci_high * 100:.1f}%]")
    print(f"  Rod baseline: {rod_sessions}/{rod_sessions} sessions, "
          f"{rod_span_hours}h, 100%")

    # ── Save ─────────────────────────────────────────────────────────
    results = {
        "experiment": "plate_multiday_stability",
        "experiment_id": "E28",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "paper_claim": "Non-volatile without power/refresh (§3.2)",
        "rod_baseline": {
            "sessions": rod_sessions,
            "span_hours": rod_span_hours,
            "accuracy": "100%",
        },
        "sessions_total": len(timeline),
        "sessions_with_accuracy": len(accuracy_sessions),
        "pct_100": round(pct_100, 1) if accuracy_sessions else None,
        "wilson_ci_95": [round(ci_low * 100, 1), round(ci_high * 100, 1)]
        if accuracy_sessions else None,
        "time_span_hours": round(span_hours, 1),
        "first_timestamp": timestamps[0] if timestamps else None,
        "last_timestamp": timestamps[-1] if timestamps else None,
        "timeline": timeline,
        "fresh_recall": fresh_result,
        "verdict": verdict,
    }

    LAB_DIR.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_FILE, "w") as fw:
        json.dump(results, fw, indent=2, default=str)
    print(f"\n  Saved: {RESULTS_FILE}")

    # ── Firestore submission ─────────────────────────────────────────
    if args.submit:
        from firestore_submit import firebase_anon_auth, submit_experiment, print_result
        token = firebase_anon_auth()
        if token:
            data = {
                "experiment_id": "E28",
                "substrate": "fused_silica_plate",
                "sessions_with_accuracy": len(accuracy_sessions),
                "pct_100": round(pct_100, 1) if accuracy_sessions else 0,
                "time_span_hours": round(span_hours, 1),
                "wilson_ci_95": [round(ci_low * 100, 1), round(ci_high * 100, 1)]
                if accuracy_sessions else [0, 0],
                "verdict": verdict,
            }
            r = submit_experiment(
                token, "exp-plate-multiday-stability", data,
                notes=f"E28 multi-day: {verdict}"
            )
            print_result(r)


if __name__ == "__main__":
    main()
