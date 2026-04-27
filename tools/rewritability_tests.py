#!/usr/bin/env python3
"""
Rewritability Test Suite — Four experiments toward RAM-like glass memory.

Test 1: Firmware Virtual Rewriting (Track A)
  - SVD partition of plate eigenmode spectra into orthogonal subspaces
  - Prove writing to subspace A doesn't corrupt readout from subspace B
  - Uses existing census data (no hardware needed)

Test 2: Perturbation Toggle (Track B analog)
  - Enroll clean slide/plate baseline → apply removable perturbation → re-measure
  - Remove → re-measure → verify return to baseline
  - Requires physical intervention (interactive)

Test 3: Antiphase Erase (dual-DDS interference)
  - Drive DDS#1 and DDS#2 at a shared eigenmode frequency
  - Measure: does the combined response differ from the sum of individuals?
  - If DDS#1 and DDS#2 have opposite coupling phase → destructive interference = erase

Test 4: Broadband Erase (AWG noise burst)
  - Excite specific eigenmodes with CW drive
  - Measure elevated eigenmode energy
  - Drive broadband noise via AWG → re-measure
  - Check if excited modes return to baseline

Usage:
  python tools/rewritability_tests.py --test 1          # Firmware SVD (offline)
  python tools/rewritability_tests.py --test 2          # Perturbation toggle (interactive)
  python tools/rewritability_tests.py --test 3          # Antiphase erase (hardware)
  python tools/rewritability_tests.py --test 4          # Broadband erase (hardware)
  python tools/rewritability_tests.py --test all        # Run 1, then 3, then 4
"""
import argparse, json, sys, time, os
import numpy as np
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--test', type=str, default='all',
                    help='Which test: 1, 2, 3, 4, or all')
parser.add_argument('--navg', type=int, default=20,
                    help='Coherent averages per measurement (tests 2-4)')
parser.add_argument('--mux-channel', type=int, default=5,
                    help='Mux channel for readout')
args = parser.parse_args()

DATA_DIR = Path(__file__).parent.parent / 'data' / 'results'
PLATE_DIR = DATA_DIR / 'lab' / 'plate_exps'

# ═══════════════════════════════════════════════════════════════════
#  TEST 1: Firmware Virtual Rewriting (SVD Subspace Partitioning)
# ═══════════════════════════════════════════════════════════════════

def test1_firmware_virtual_rewrite():
    """
    Prove that a single plate's eigenmode spectrum can be partitioned into
    independent subspaces that don't interfere with each other.

    This is Track A rewritability: the glass is physically fixed, but we
    can treat different frequency bands as independent "virtual devices."
    """
    print("=" * 60)
    print("TEST 1: FIRMWARE VIRTUAL REWRITING (SVD)")
    print("=" * 60)

    # Load the most recent plate census sweep data
    sweep_files = sorted(PLATE_DIR.glob("plate_census_sweeps_*.json"))
    if not sweep_files:
        print("ERROR: No plate census sweep data found.")
        print("  Need: data/results/lab/plate_exps/plate_census_sweeps_*.json")
        return False

    latest = sweep_files[-1]
    print(f"\nLoading census: {latest.name}")
    with open(latest) as f:
        census = json.load(f)

    # Also load peak data for mode identification
    peak_files = sorted(PLATE_DIR.glob("plate_census_2026*.json"))
    latest_peaks = peak_files[-1] if peak_files else None
    peaks_data = None
    if latest_peaks:
        with open(latest_peaks) as f:
            pd = json.load(f)
            peaks_data = pd.get('results', pd)

    plate_names = list(census.keys())
    print(f"Plates available: {plate_names}")

    # Build spectral matrix: each row = one plate's magnitude spectrum
    spectra = {}
    freqs = None
    for pname in plate_names:
        sweep = census[pname]['sweep_data']
        f_arr = np.array([s['freq_hz'] for s in sweep])
        m_arr = np.array([s['magnitude'] for s in sweep])
        if freqs is None:
            freqs = f_arr
        spectra[pname] = m_arr

    n_freq = len(freqs)
    print(f"Frequency points: {n_freq} ({freqs[0]:.0f}–{freqs[-1]:.0f} Hz)")

    # ── Per-plate SVD subspace analysis ──
    # For each plate, identify strong modes, then partition into subspaces
    print(f"\n--- Per-plate mode partitioning ---")

    for pname in plate_names:
        mag = spectra[pname]

        # Normalize
        mag_norm = mag / np.max(mag)

        # Find peaks (local maxima above threshold)
        threshold = 0.1  # 10% of max
        peaks = []
        for i in range(2, len(mag_norm) - 2):
            if (mag_norm[i] > mag_norm[i-1] and mag_norm[i] > mag_norm[i+1]
                    and mag_norm[i] > mag_norm[i-2] and mag_norm[i] > mag_norm[i+2]
                    and mag_norm[i] > threshold):
                # Check not too close to existing peak
                if not any(abs(freqs[i] - freqs[p]) < 1000 for p in peaks):
                    peaks.append(i)

        n_modes = len(peaks)
        peak_freqs = freqs[peaks]
        print(f"\n  Plate {pname}: {n_modes} modes above {threshold*100:.0f}% threshold")
        if n_modes < 4:
            print(f"    Too few modes for subspace test, skipping")
            continue

        # Partition modes into 2 subspaces: low-half and high-half
        mid = n_modes // 2
        sub_A = peaks[:mid]
        sub_B = peaks[mid:]

        print(f"    Subspace A ({len(sub_A)} modes): "
              f"{freqs[sub_A[0]]:.0f}–{freqs[sub_A[-1]]:.0f} Hz")
        print(f"    Subspace B ({len(sub_B)} modes): "
              f"{freqs[sub_B[0]]:.0f}–{freqs[sub_B[-1]]:.0f} Hz")

        # Build "fingerprint" vectors for each subspace
        vec_A = mag[sub_A]
        vec_B = mag[sub_B]

        # Normalize fingerprint vectors
        vec_A_n = vec_A / np.linalg.norm(vec_A)
        vec_B_n = vec_B / np.linalg.norm(vec_B)

        # Cross-talk metric: how much does subspace A's fingerprint
        # correlate with subspace B's modes (and vice versa)?
        # Use the off-diagonal blocks of the full coupling matrix.

        # Build per-mode energy vectors across ALL plates for these modes
        # This tests: if we "write" a pattern by selecting plates with specific
        # subspace-A signatures, does subspace-B remain independent?

        print(f"\n    Cross-subspace independence test:")

        # For each pair of plates, compute correlation within each subspace
        # and cross-correlation between subspaces
        all_plates = list(spectra.keys())
        if len(all_plates) < 3:
            print(f"    Need ≥3 plates for cross-plate test")
            continue

        # Build matrix: rows = plates, columns = mode magnitudes
        mat_A = np.array([spectra[p][sub_A] for p in all_plates])
        mat_B = np.array([spectra[p][sub_B] for p in all_plates])

        # Normalize per plate
        for i in range(len(all_plates)):
            na = np.linalg.norm(mat_A[i])
            nb = np.linalg.norm(mat_B[i])
            if na > 0: mat_A[i] /= na
            if nb > 0: mat_B[i] /= nb

        # Within-subspace correlation (should be high — plates differ here)
        corr_AA = np.corrcoef(mat_A)
        corr_BB = np.corrcoef(mat_B)

        # Cross-subspace: correlation between A-rankings and B-rankings
        # If subspaces are independent, knowing a plate's A-ranking tells
        # you nothing about its B-ranking
        # Use Spearman rank correlation on plate orderings
        from scipy import stats

        # Rank plates by their norm in each subspace
        norms_A = np.linalg.norm(mat_A, axis=1)
        norms_B = np.linalg.norm(mat_B, axis=1)
        ranks_A = stats.rankdata(norms_A)
        ranks_B = stats.rankdata(norms_B)

        rho, p_val = stats.spearmanr(ranks_A, ranks_B)

        # Also compute SVD on combined matrix
        combined = np.hstack([mat_A, mat_B])
        U, S, Vt = np.linalg.svd(combined, full_matrices=False)

        # How much variance does subspace A explain vs B?
        n_A = mat_A.shape[1]
        n_B = mat_B.shape[1]

        # Project Vt rows onto A and B columns
        var_explained = S ** 2
        total_var = np.sum(var_explained)

        # Effective dimensionality
        cumvar = np.cumsum(var_explained) / total_var
        eff_dim = np.searchsorted(cumvar, 0.95) + 1

        print(f"    Within-subspace A correlation (mean off-diag): "
              f"{np.mean(corr_AA[np.triu_indices_from(corr_AA, k=1)]):.3f}")
        print(f"    Within-subspace B correlation (mean off-diag): "
              f"{np.mean(corr_BB[np.triu_indices_from(corr_BB, k=1)]):.3f}")
        print(f"    Cross-subspace rank correlation (Spearman ρ): "
              f"{rho:.3f} (p={p_val:.3f})")
        print(f"    SVD effective dimensionality (95% var): {eff_dim}")
        print(f"    Singular values: {', '.join(f'{s:.2f}' for s in S[:5])}")

        if abs(rho) < 0.5 and p_val > 0.05:
            print(f"    ✓ INDEPENDENT — subspace A ranking does NOT predict subspace B")
            print(f"      → Virtual rewriting feasible: change 'written' subspace, "
                  f"other subspace unaffected")
        elif abs(rho) < 0.7:
            print(f"    ~ PARTIALLY INDEPENDENT — some cross-talk")
        else:
            print(f"    ✗ CORRELATED — subspaces are not independent (ρ={rho:.2f})")

    # ── Cross-plate discrimination within subspaces ──
    print(f"\n--- Cross-plate discrimination per subspace ---")

    # For each plate, check if it's distinguishable from all others
    # using ONLY subspace A modes, and ONLY subspace B modes
    for pname in plate_names:
        mag = spectra[pname]
        mag_norm = mag / np.max(mag)
        peaks = []
        for i in range(2, len(mag_norm) - 2):
            if (mag_norm[i] > mag_norm[i-1] and mag_norm[i] > mag_norm[i+1]
                    and mag_norm[i] > mag_norm[i-2] and mag_norm[i] > mag_norm[i+2]
                    and mag_norm[i] > 0.1):
                if not any(abs(freqs[i] - freqs[p]) < 1000 for p in peaks):
                    peaks.append(i)

        if len(peaks) < 4:
            continue

        mid = len(peaks) // 2
        sub_A = peaks[:mid]
        sub_B = peaks[mid:]

        # Cosine similarity against all other plates in each subspace
        others = [p for p in plate_names if p != pname]
        for sub_name, sub_idx in [("A", sub_A), ("B", sub_B)]:
            ref_vec = spectra[pname][sub_idx]
            ref_norm = ref_vec / np.linalg.norm(ref_vec)

            sims = []
            for other in others:
                other_vec = spectra[other][sub_idx]
                other_norm = other_vec / np.linalg.norm(other_vec)
                sim = np.dot(ref_norm, other_norm)
                sims.append((other, sim))

            max_sim = max(s for _, s in sims)
            min_sim = min(s for _, s in sims)
            print(f"  Plate {pname} subspace {sub_name}: "
                  f"max similarity to others = {max_sim:.3f}, "
                  f"min = {min_sim:.3f}")

    # ── Summary ──
    print(f"\n{'='*60}")
    print("TEST 1 SUMMARY: FIRMWARE VIRTUAL REWRITING")
    print(f"{'='*60}")
    print(f"  Plates analyzed: {len(plate_names)}")
    print(f"  Frequency range: {freqs[0]:.0f}–{freqs[-1]:.0f} Hz")
    print(f"  Method: Split eigenmodes into low/high subspaces, test independence")
    print(f"  If subspaces are independent: changing which 'virtual device' is")
    print(f"  active (by selecting different mode subsets in firmware) gives")
    print(f"  multiple rewritable addresses per physical resonator.")

    return True


# ═══════════════════════════════════════════════════════════════════
#  Hardware setup (shared by tests 2-4)
# ═══════════════════════════════════════════════════════════════════

def setup_hardware():
    """Initialize PicoScope, DDS, and mux. Returns (ps, handle, dds, mux)."""
    import ctypes, serial

    ps = ctypes.CDLL(
        "/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources/libps2000.dylib")
    ps.ps2000_set_sig_gen_built_in.argtypes = [
        ctypes.c_int16, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32,
        ctypes.c_float, ctypes.c_float, ctypes.c_float, ctypes.c_float,
        ctypes.c_int32, ctypes.c_int32]

    for h in range(1, 5):
        ps.ps2000_close_unit(h)
    time.sleep(0.5)

    handle = ps.ps2000_open_unit()
    print(f"PicoScope handle: {handle}")
    if handle <= 0:
        sys.exit(1)

    ps.ps2000_set_channel(handle, 0, 1, 1, 7)  # Ch A on, AC, ±2V
    ps.ps2000_set_channel(handle, 1, 0, 1, 7)  # Ch B off
    ps.ps2000_set_sig_gen_built_in(handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0)

    mux = serial.Serial('/dev/cu.usbserial-11310', 9600, timeout=1)
    time.sleep(2)
    mux.reset_input_buffer()

    dds = serial.Serial('/dev/cu.usbserial-11330', 115200, timeout=2)
    time.sleep(2)
    dds.reset_input_buffer()

    return ps, handle, dds, mux


def dds_cmd(dds, cmd):
    dds.write(f'{cmd}\n'.encode())
    time.sleep(0.01)
    return dds.readline().decode().strip()


TIMEBASE = 7
N_SAMPLES = 8064
DT = 1280e-9


def capture(ps, handle):
    import ctypes
    buf = (ctypes.c_int16 * N_SAMPLES)()
    ov = ctypes.c_int16(0)
    ps.ps2000_set_trigger(handle, 5, 0, 0, 0, 0)
    ms = ctypes.c_int32(0)
    ps.ps2000_run_block(handle, N_SAMPLES, TIMEBASE, 1, ctypes.byref(ms))
    for _ in range(5000):
        if ps.ps2000_ready(handle):
            break
        time.sleep(0.001)
    else:
        ps.ps2000_stop(handle)
        return np.zeros(N_SAMPLES)
    ps.ps2000_get_values(handle, ctypes.byref(buf), None, None, None,
                         ctypes.byref(ov), N_SAMPLES)
    return np.array(buf, dtype=np.float64)


def coherent_avg_spectrum(ps, handle, n_avg):
    frames = [capture(ps, handle) for _ in range(n_avg)]
    avg = np.mean(frames, axis=0)
    d = avg - np.mean(avg)
    w = d * np.hanning(len(d))
    nfft = len(d) * 4
    mag = np.abs(np.fft.rfft(w, n=nfft))
    freq = np.fft.rfftfreq(nfft, d=DT)
    return freq, mag


def cleanup_hardware(ps, handle, dds, mux):
    dds_cmd(dds, 'Foff')
    ps.ps2000_set_sig_gen_built_in(handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0)
    ps.ps2000_stop(handle)
    ps.ps2000_close_unit(handle)
    mux.write(b'0\n')
    mux.close()
    dds.close()


# ═══════════════════════════════════════════════════════════════════
#  TEST 2: Perturbation Toggle (interactive)
# ═══════════════════════════════════════════════════════════════════

def test2_perturbation_toggle():
    """
    Interactive reversible perturbation test.
    Enroll baseline → apply perturbation → measure → remove → measure.
    """
    print("=" * 60)
    print("TEST 2: REVERSIBLE PERTURBATION TOGGLE")
    print("=" * 60)
    print("\nThis test requires physical interaction with the setup.")
    print("You'll need: Blu-Tack, tape, or similar removable mass.")

    ps, handle, dds, mux = setup_hardware()

    # Select mux channel
    mux.write(f'{args.mux_channel}\n'.encode())
    time.sleep(0.15)
    mux.readline()
    time.sleep(0.1)

    dds_cmd(dds, 'Foff')
    time.sleep(0.3)

    results = {'baselines': [], 'perturbed': [], 'restored': []}
    n_cycles = 3

    try:
        # Phase 1: Baseline measurement
        print(f"\n--- Phase 1: Baseline (clean glass, no perturbation) ---")
        input("Press Enter when glass is CLEAN (no perturbation)...")

        print("  Measuring baseline (3 captures for reproducibility)...")
        baselines = []
        for i in range(3):
            freq, mag = coherent_avg_spectrum(ps, handle, args.navg)
            baselines.append(mag)
            time.sleep(0.2)

        baseline_avg = np.mean(baselines, axis=0)
        baseline_std = np.std(baselines, axis=0)
        baseline_rms = np.sqrt(np.mean(baseline_avg ** 2))

        # Find strong modes in baseline
        ratio = baseline_avg / np.where(baseline_std > 0, baseline_std, 1)
        top_modes = np.argsort(ratio)[-10:][::-1]
        print(f"  Baseline RMS: {baseline_rms:.0f}")
        print(f"  Top 5 stable modes:")
        for idx in top_modes[:5]:
            print(f"    {freq[idx]:.0f} Hz (SNR={ratio[idx]:.0f}×)")

        results['baselines'].append(baseline_avg.tolist())

        # Phase 2-4: Toggle cycles
        for cycle in range(n_cycles):
            print(f"\n--- Cycle {cycle+1}/{n_cycles}: APPLY perturbation ---")
            input(f"  Place Blu-Tack/tape on the glass, then press Enter...")
            time.sleep(0.5)

            print("  Measuring perturbed state...")
            _, perturbed_mag = coherent_avg_spectrum(ps, handle, args.navg)
            results['perturbed'].append(perturbed_mag.tolist())

            # Compare to baseline
            diff = perturbed_mag - baseline_avg
            diff_rms = np.sqrt(np.mean(diff ** 2))
            cosine_sim = np.dot(baseline_avg, perturbed_mag) / (
                np.linalg.norm(baseline_avg) * np.linalg.norm(perturbed_mag))

            # Find modes that shifted most
            rel_change = np.abs(diff) / np.where(baseline_avg > 100, baseline_avg, 100)
            shifted_modes = np.argsort(rel_change)[-5:][::-1]

            print(f"  Perturbation effect:")
            print(f"    RMS difference: {diff_rms:.0f} (baseline RMS: {baseline_rms:.0f})")
            print(f"    Cosine similarity: {cosine_sim:.4f}")
            print(f"    Top shifted modes:")
            for idx in shifted_modes:
                pct = 100 * rel_change[idx]
                direction = "↑" if diff[idx] > 0 else "↓"
                print(f"      {freq[idx]:.0f} Hz: {direction}{pct:.1f}%")

            # Phase 3: Remove perturbation
            print(f"\n--- Cycle {cycle+1}/{n_cycles}: REMOVE perturbation ---")
            input(f"  Remove the Blu-Tack/tape, then press Enter...")
            time.sleep(0.5)

            print("  Measuring restored state...")
            _, restored_mag = coherent_avg_spectrum(ps, handle, args.navg)
            results['restored'].append(restored_mag.tolist())

            # Compare restored to original baseline
            restore_diff = restored_mag - baseline_avg
            restore_rms = np.sqrt(np.mean(restore_diff ** 2))
            restore_sim = np.dot(baseline_avg, restored_mag) / (
                np.linalg.norm(baseline_avg) * np.linalg.norm(restored_mag))

            print(f"  Restoration quality:")
            print(f"    RMS from baseline: {restore_rms:.0f} (perturbation was {diff_rms:.0f})")
            print(f"    Cosine similarity: {restore_sim:.4f} (perturbed was {cosine_sim:.4f})")

            if restore_sim > cosine_sim:
                recovery = (restore_sim - cosine_sim) / (1.0 - cosine_sim) * 100
                print(f"    ✓ RECOVERY: {recovery:.1f}% of the way back to baseline")
            else:
                print(f"    ✗ NOT RECOVERED — restored state diverged further")

        # Summary
        print(f"\n{'='*60}")
        print("TEST 2 SUMMARY: PERTURBATION TOGGLE")
        print(f"{'='*60}")
        print(f"  Cycles completed: {n_cycles}")

        perturbed_sims = []
        restored_sims = []
        for i in range(min(len(results['perturbed']), len(results['restored']))):
            p_mag = np.array(results['perturbed'][i])
            r_mag = np.array(results['restored'][i])
            p_sim = np.dot(baseline_avg, p_mag) / (
                np.linalg.norm(baseline_avg) * np.linalg.norm(p_mag))
            r_sim = np.dot(baseline_avg, r_mag) / (
                np.linalg.norm(baseline_avg) * np.linalg.norm(r_mag))
            perturbed_sims.append(p_sim)
            restored_sims.append(r_sim)

        if perturbed_sims:
            print(f"  Perturbed similarity: {np.mean(perturbed_sims):.4f} ± {np.std(perturbed_sims):.4f}")
            print(f"  Restored similarity:  {np.mean(restored_sims):.4f} ± {np.std(restored_sims):.4f}")

            if np.mean(restored_sims) > np.mean(perturbed_sims) + 0.01:
                print(f"  ✓ REVERSIBLE — removal restores spectrum closer to baseline")
                print(f"    → Track B rewritability mechanism validated at macro scale")
            else:
                print(f"  ✗ NOT CLEARLY REVERSIBLE — removal doesn't reliably restore baseline")

        # Save
        out_path = DATA_DIR / "rewritability_perturbation_toggle.npz"
        np.savez(out_path, freq=freq, baseline=baseline_avg,
                 baseline_std=baseline_std,
                 perturbed=np.array(results['perturbed']),
                 restored=np.array(results['restored']))
        print(f"\n  Data saved to {out_path}")

    finally:
        cleanup_hardware(ps, handle, dds, mux)

    return True


# ═══════════════════════════════════════════════════════════════════
#  TEST 3: Antiphase Erase (dual-DDS interference)
# ═══════════════════════════════════════════════════════════════════

def test3_antiphase_erase():
    """
    Drive DDS#1 and DDS#2 at shared eigenmode frequencies.
    Compare: solo DDS#1, solo DDS#2, both together.
    If coupling phases differ, both-on could suppress a mode.
    """
    print("=" * 60)
    print("TEST 3: ANTIPHASE ERASE (DUAL-DDS INTERFERENCE)")
    print("=" * 60)

    # Load eigenmode sweep data to find shared modes
    d1 = np.load(DATA_DIR / 'eigenmode_sweep_dds1_5000_100000_5000.npz')
    d2 = np.load(DATA_DIR / 'eigenmode_sweep_dds2_5000_100000_5000.npz')

    freq_axis_sweep = d1['freq_axis']
    e1_freqs = d1['eigenmode_freqs']
    e2_freqs = d2['eigenmode_freqs']
    e1_ratios = np.max(d1['all_ratios'], axis=(0, 1))
    e2_ratios = np.max(d2['all_ratios'], axis=(0, 1))

    # Find eigenmodes that both DDS boards excite
    shared = []
    for i, f1 in enumerate(e1_freqs):
        for j, f2 in enumerate(e2_freqs):
            if abs(f1 - f2) < 2000:
                shared.append({
                    'freq': (f1 + f2) / 2,
                    'dds1_freq': f1,
                    'dds2_freq': f2,
                    'dds1_rank': i,
                    'dds2_rank': j,
                })

    if not shared:
        print("No shared eigenmodes found between DDS#1 and DDS#2.")
        print("Cannot test antiphase erase.")
        return False

    print(f"\nShared eigenmodes (excited by both DDS boards):")
    for s in shared:
        print(f"  ~{s['freq']:.0f} Hz (DDS1 rank #{s['dds1_rank']+1}, "
              f"DDS2 rank #{s['dds2_rank']+1})")

    # Also test non-shared modes as control
    # Find best DDS#1-only drive freqs for each shared eigenmode
    drive_freqs_1 = d1['drive_freqs']
    drive_freqs_2 = d2['drive_freqs']

    # For each shared eigenmode, find which drive freq excites it best on each DDS
    for s in shared:
        f_target = s['freq']
        bin_idx = np.argmin(np.abs(freq_axis_sweep - f_target))

        # Best DDS#1 drive for this eigenmode
        dds1_ratios_at_mode = d1['all_ratios'][:, 0, bin_idx]  # first mux channel
        s['best_drive_1'] = int(drive_freqs_1[np.argmax(dds1_ratios_at_mode)])
        s['ratio_1'] = float(np.max(dds1_ratios_at_mode))

        # Best DDS#2 drive for this eigenmode
        dds2_ratios_at_mode = d2['all_ratios'][:, 0, bin_idx]
        s['best_drive_2'] = int(drive_freqs_2[np.argmax(dds2_ratios_at_mode)])
        s['ratio_2'] = float(np.max(dds2_ratios_at_mode))

    # Setup hardware
    ps, handle, dds, mux = setup_hardware()

    mux.write(f'{args.mux_channel}\n'.encode())
    time.sleep(0.15)
    mux.readline()
    time.sleep(0.1)

    try:
        # Noise baseline
        print(f"\n--- Noise baseline ---")
        dds_cmd(dds, 'Foff')
        time.sleep(0.3)
        freq, noise_mag = coherent_avg_spectrum(ps, handle, args.navg)
        noise_rms = np.sqrt(np.mean(noise_mag ** 2))
        print(f"  RMS: {noise_rms:.0f}")

        print(f"\n--- Testing shared eigenmodes ---")

        for s in shared:
            f_target = s['freq']
            drive1 = s['best_drive_1']
            drive2 = s['best_drive_2']
            bin_idx = np.argmin(np.abs(freq - f_target))
            # Use a window around the target frequency
            window = 5  # bins
            lo = max(0, bin_idx - window)
            hi = min(len(freq), bin_idx + window + 1)

            print(f"\n  Eigenmode ~{f_target:.0f} Hz:")
            print(f"    Best DDS#1 drive: {drive1} Hz ({s['ratio_1']:.0f}× in sweep)")
            print(f"    Best DDS#2 drive: {drive2} Hz ({s['ratio_2']:.0f}× in sweep)")

            # Measure DDS#1 only
            dds_cmd(dds, 'Foff')
            time.sleep(0.1)
            dds_cmd(dds, f'F1:{drive1}')
            time.sleep(0.3)
            _, mag_1 = coherent_avg_spectrum(ps, handle, args.navg)
            energy_1 = np.sum(mag_1[lo:hi])
            ratio_1 = energy_1 / np.sum(noise_mag[lo:hi]) if np.sum(noise_mag[lo:hi]) > 0 else 0

            # Measure DDS#2 only
            dds_cmd(dds, 'Foff')
            time.sleep(0.1)
            dds_cmd(dds, f'F2:{drive2}')
            time.sleep(0.3)
            _, mag_2 = coherent_avg_spectrum(ps, handle, args.navg)
            energy_2 = np.sum(mag_2[lo:hi])
            ratio_2 = energy_2 / np.sum(noise_mag[lo:hi]) if np.sum(noise_mag[lo:hi]) > 0 else 0

            # Measure BOTH DDS
            dds_cmd(dds, 'Foff')
            time.sleep(0.1)
            dds_cmd(dds, f'F1:{drive1}')
            time.sleep(0.05)
            dds_cmd(dds, f'F2:{drive2}')
            time.sleep(0.3)
            _, mag_both = coherent_avg_spectrum(ps, handle, args.navg)
            energy_both = np.sum(mag_both[lo:hi])
            ratio_both = energy_both / np.sum(noise_mag[lo:hi]) if np.sum(noise_mag[lo:hi]) > 0 else 0

            # Linear prediction: if no interference, both = dds1 + dds2 - noise
            noise_energy = np.sum(noise_mag[lo:hi])
            linear_pred = energy_1 + energy_2 - noise_energy

            # Interference metric
            if linear_pred > 0:
                interference = (energy_both - linear_pred) / linear_pred * 100
            else:
                interference = 0

            print(f"    DDS#1 only:  energy={energy_1:.0f} ({ratio_1:.1f}× noise)")
            print(f"    DDS#2 only:  energy={energy_2:.0f} ({ratio_2:.1f}× noise)")
            print(f"    Both DDS:    energy={energy_both:.0f} ({ratio_both:.1f}× noise)")
            print(f"    Linear pred: energy={linear_pred:.0f}")
            print(f"    Interference: {interference:+.1f}%", end="")

            if interference < -20:
                print(f" → DESTRUCTIVE (partial erase!)")
            elif interference < -5:
                print(f" → Mildly destructive")
            elif interference > 20:
                print(f" → CONSTRUCTIVE (amplification)")
            elif interference > 5:
                print(f" → Mildly constructive")
            else:
                print(f" → ~Linear (no significant interference)")

            # Also check full-spectrum deviation
            linear_full = mag_1 + mag_2 - noise_mag
            actual_diff = mag_both - linear_full
            diff_rms = np.sqrt(np.mean(actual_diff ** 2))
            linear_rms = np.sqrt(np.mean(linear_full ** 2))
            nonlin_pct = 100 * diff_rms / linear_rms if linear_rms > 0 else 0
            print(f"    Full-spectrum nonlinearity: {nonlin_pct:.1f}%")

        # Also test: can one DDS erase what the other wrote?
        # Drive DDS#1 to "write" energy into a mode, then add DDS#2 at same mode
        print(f"\n--- Sequential write/erase test ---")
        for s in shared:
            f_target = s['freq']
            bin_idx = np.argmin(np.abs(freq - f_target))
            lo = max(0, bin_idx - window)
            hi = min(len(freq), bin_idx + window + 1)

            print(f"\n  Mode ~{f_target:.0f} Hz:")

            # Write: DDS#1 on for 500ms, then measure
            dds_cmd(dds, 'Foff')
            time.sleep(0.1)
            dds_cmd(dds, f'F1:{s["best_drive_1"]}')
            time.sleep(0.5)
            _, mag_written = coherent_avg_spectrum(ps, handle, args.navg)
            written_energy = np.sum(mag_written[lo:hi])

            # Erase attempt: add DDS#2, measure
            dds_cmd(dds, f'F2:{s["best_drive_2"]}')
            time.sleep(0.3)
            _, mag_erased = coherent_avg_spectrum(ps, handle, args.navg)
            erased_energy = np.sum(mag_erased[lo:hi])

            # Turn off DDS#1, keep DDS#2 (residual test)
            dds_cmd(dds, f'F1:off')
            time.sleep(0.3)
            _, mag_residual = coherent_avg_spectrum(ps, handle, args.navg)
            residual_energy = np.sum(mag_residual[lo:hi])

            print(f"    Written (DDS#1):       {written_energy:.0f}")
            print(f"    +DDS#2 (erase try):    {erased_energy:.0f} "
                  f"({(erased_energy/written_energy-1)*100:+.1f}%)")
            print(f"    DDS#2 only (residual):  {residual_energy:.0f}")

            if erased_energy < written_energy * 0.8:
                print(f"    ✓ PARTIAL ERASE — DDS#2 reduced mode energy by "
                      f"{(1-erased_energy/written_energy)*100:.0f}%")
            elif erased_energy > written_energy * 1.2:
                print(f"    ↑ CONSTRUCTIVE — DDS#2 amplified the mode")
            else:
                print(f"    ~ No significant erase effect")

        dds_cmd(dds, 'Foff')

        # Summary
        print(f"\n{'='*60}")
        print("TEST 3 SUMMARY: ANTIPHASE ERASE")
        print(f"{'='*60}")
        print(f"  Shared eigenmodes tested: {len(shared)}")
        print(f"  Interference = (both - linear_sum) / linear_sum")
        print(f"  Negative = destructive interference = partial mode erasure")
        print(f"  Positive = constructive = mode amplification")
        print(f"  If any mode shows >20% destructive: selective erase is possible")

    finally:
        cleanup_hardware(ps, handle, dds, mux)

    return True


# ═══════════════════════════════════════════════════════════════════
#  TEST 4: Broadband Erase (AWG noise burst)
# ═══════════════════════════════════════════════════════════════════

def test4_broadband_erase():
    """
    Test if broadband AWG noise can thermalize (reset) excited eigenmodes.

    Protocol:
    1. Measure noise baseline (everything off)
    2. Drive a CW tone via DDS#1 → measure elevated eigenmode energy
    3. Turn DDS off but immediately drive AWG broadband noise for N ms
    4. Turn AWG off → measure: are modes back to baseline?
    5. Control: turn DDS off, no noise, measure natural decay
    """
    print("=" * 60)
    print("TEST 4: BROADBAND ERASE (AWG NOISE BURST)")
    print("=" * 60)

    import ctypes

    ps, handle, dds, mux = setup_hardware()

    mux.write(f'{args.mux_channel}\n'.encode())
    time.sleep(0.15)
    mux.readline()
    time.sleep(0.1)

    # AWG waveform types: 0=sine, 1=square, 2=triangle, 3=ramp_up,
    # 4=ramp_down, 5=sinc, 6=gaussian, 7=half_sine, 8=dc
    # For broadband: sweep sine rapidly across wide range
    # ps2000 sig gen can do a frequency sweep

    # Best DDS#1 drive frequency (50kHz was the sweet spot)
    drive_freq = 50000

    try:
        # Step 1: Noise baseline
        print(f"\n--- Step 1: Noise baseline ---")
        dds_cmd(dds, 'Foff')
        ps.ps2000_set_sig_gen_built_in(handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0)
        time.sleep(0.5)
        freq, noise_mag = coherent_avg_spectrum(ps, handle, args.navg)
        noise_rms = np.sqrt(np.mean(noise_mag ** 2))
        print(f"  RMS: {noise_rms:.0f}")

        # Find baseline energy at key eigenmodes
        # Use eigenmode sweep data for mode locations
        d1 = np.load(DATA_DIR / 'eigenmode_sweep_dds1_5000_100000_5000.npz')
        eigenmode_bins = d1['eigenmodes'][:10]  # top 10 modes
        eigenmode_freqs_list = d1['eigenmode_freqs'][:10]

        # Map sweep eigenmode freqs to our capture freq axis
        mode_bins = [np.argmin(np.abs(freq - ef)) for ef in eigenmode_freqs_list]

        baseline_energies = [noise_mag[b] for b in mode_bins]
        print(f"  Eigenmode baseline energies:")
        for i, (ef, be) in enumerate(zip(eigenmode_freqs_list, baseline_energies)):
            print(f"    {ef:.0f} Hz: {be:.0f}")

        # Step 2: Drive CW to excite modes
        print(f"\n--- Step 2: CW excitation at {drive_freq} Hz ---")
        dds_cmd(dds, f'F1:{drive_freq}')
        time.sleep(0.5)
        _, excited_mag = coherent_avg_spectrum(ps, handle, args.navg)

        excited_energies = [excited_mag[b] for b in mode_bins]
        print(f"  Eigenmode energies (CW on):")
        for i, (ef, ee, be) in enumerate(zip(eigenmode_freqs_list, excited_energies, baseline_energies)):
            ratio = ee / be if be > 0 else 0
            print(f"    {ef:.0f} Hz: {ee:.0f} ({ratio:.1f}× baseline)")

        # Step 3: DDS off, natural decay (control)
        print(f"\n--- Step 3: Natural decay (DDS off, no erase) ---")
        dds_cmd(dds, 'Foff')

        # Measure at several delay points
        for delay_ms in [10, 50, 100, 500]:
            time.sleep(delay_ms / 1000.0)
            _, decay_mag = coherent_avg_spectrum(ps, handle, 5)  # fewer avgs for speed
            decay_energies = [decay_mag[b] for b in mode_bins]

            retained = []
            for ee, de, be in zip(excited_energies, decay_energies, baseline_energies):
                if ee > be * 1.5:  # only count modes that were actually excited
                    ret = (de - be) / (ee - be) * 100 if (ee - be) > 0 else 0
                    retained.append(ret)

            avg_ret = np.mean(retained) if retained else 0
            print(f"    +{delay_ms:>4} ms: {avg_ret:>6.1f}% retained "
                  f"({len(retained)} excited modes)")

        # Step 4: Re-excite, then broadband erase
        print(f"\n--- Step 4: CW excitation → broadband erase ---")

        for erase_duration_ms in [50, 200, 1000]:
            # Re-excite
            dds_cmd(dds, f'F1:{drive_freq}')
            time.sleep(0.5)
            _, pre_erase_mag = coherent_avg_spectrum(ps, handle, args.navg)

            # DDS off + AWG broadband sweep immediately
            dds_cmd(dds, 'Foff')

            # AWG sweep: sine from 1kHz to 200kHz, sweep time = erase_duration
            # Sweep mode: 0=up, 1=down, 2=up-down, 3=down-up
            # sweepType enum: 0=UP
            # Using fast sweep across wide band for broadband-like excitation
            uvpp = 2000000  # 2Vpp (maximum AWG output for strong erase)
            ps.ps2000_set_sig_gen_built_in(
                handle, 0, uvpp, 0,  # offset, pk-pk, waveType=sine
                1000.0, 200000.0,    # startFreq, stopFreq
                float(erase_duration_ms) / 1000.0,  # increment (Hz/sweep)
                0.001,               # dwell time per step (1ms)
                0, 0)                # sweepType=UP, sweeps=0 (continuous)

            time.sleep(erase_duration_ms / 1000.0 + 0.1)

            # AWG off
            ps.ps2000_set_sig_gen_built_in(
                handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0)
            time.sleep(0.1)

            # Measure post-erase
            _, post_erase_mag = coherent_avg_spectrum(ps, handle, args.navg)

            pre_energies = [pre_erase_mag[b] for b in mode_bins]
            post_energies = [post_erase_mag[b] for b in mode_bins]

            erased_count = 0
            print(f"\n  Erase duration: {erase_duration_ms} ms")
            for ef, pre, post, base in zip(
                    eigenmode_freqs_list, pre_energies, post_energies, baseline_energies):
                if pre > base * 1.5:
                    recovery = (post - base) / (pre - base) * 100 if (pre - base) > 0 else 0
                    erased = recovery < 30
                    if erased:
                        erased_count += 1
                    marker = "✓ erased" if erased else f"{recovery:.0f}% remains"
                    print(f"    {ef:.0f} Hz: pre={pre:.0f}, post={post:.0f}, "
                          f"baseline={base:.0f} → {marker}")

            total_excited = sum(1 for pre, base in zip(pre_energies, baseline_energies)
                                if pre > base * 1.5)
            if total_excited > 0:
                print(f"    Erased {erased_count}/{total_excited} excited modes")

        # Summary
        print(f"\n{'='*60}")
        print("TEST 4 SUMMARY: BROADBAND ERASE")
        print(f"{'='*60}")
        print(f"  Protocol: CW excitation → DDS off → AWG broadband sweep → measure")
        print(f"  Erase = mode energy returns to noise baseline")
        print(f"  If broadband erase works: we can 'clear' glass to known state")
        print(f"  This is the equivalent of RAM power-on-reset")

    finally:
        cleanup_hardware(ps, handle, dds, mux)

    return True


# ═══════════════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    tests = args.test.split(',') if ',' in args.test else [args.test]

    if 'all' in tests:
        tests = ['1', '3', '4']  # skip interactive test 2

    for t in tests:
        t = t.strip()
        if t == '1':
            test1_firmware_virtual_rewrite()
        elif t == '2':
            test2_perturbation_toggle()
        elif t == '3':
            test3_antiphase_erase()
        elif t == '4':
            test4_broadband_erase()
        else:
            print(f"Unknown test: {t}")
        print()
