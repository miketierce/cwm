"""
E3: Temporal Stability / PUF Repeatability
==========================================

Proves the non-separable state is stable over hours (PUF property).
Runs CHSH on the optimal pair (34k+70k) every 30 min for 3 hours
(7 measurements). Compares state matrices via Frobenius distance.

Hardware (same as E1/E2):
  SW TX PZT ← Pico NCO GP2+GP3 (column 23, separate board)
  NW RX PZT → preamp (×11) → PicoScope Ch A
  NE RX PZT → direct → PicoScope Ch B

Authentication: NCO internal temperature (RP2040 ADC4) and uptime
logged at each measurement point to prove temporal separation.

Success criterion:
  - All 7 runs: S > 2.5, C > 0.95
  - State matrix Frobenius drift < 1% between consecutive measurements
  - Kills "transient artifact" / "not reproducible" objection

Usage:
  python3 tools/e3_temporal_stability.py [--interval 1800] [--runs 7]
"""
import ctypes as ct
import numpy as np
import serial
import time
import json
import argparse
from datetime import datetime
from pathlib import Path
from scipy.optimize import differential_evolution

# ─── Args ─────────────────────────────────────────────────────────
parser = argparse.ArgumentParser(description='E3: Temporal stability (PUF)')
parser.add_argument('--interval', type=int, default=1800,
                    help='Seconds between measurements (default: 1800 = 30 min)')
parser.add_argument('--runs', type=int, default=7,
                    help='Number of measurement epochs (default: 7)')
parser.add_argument('--trials', type=int, default=200,
                    help='Trials per epoch (default: 200)')
parser.add_argument('--navg', type=int, default=20,
                    help='Captures averaged per trial (default: 20)')
args = parser.parse_args()

INTERVAL_S = args.interval
N_EPOCHS = args.runs
N_TRIALS = args.trials
NAVG = args.navg

# ─── Mode pair (best from E1) ────────────────────────────────────
F1, F2 = 34000, 70000

# ─── PicoScope ────────────────────────────────────────────────────
PICO_LIB = '/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources/libps2000.dylib'
ps = ct.CDLL(PICO_LIB)
ps.ps2000_close_unit(ct.c_int16(1))
time.sleep(0.3)

N = 3968; TIMEBASE = 7
FS = 781250.0; NFFT = N * 4; BIN_HZ = FS / NFFT

RNG_A = 6; RNG_A_MV = 2000.0
RNG_B = 6; RNG_B_MV = 2000.0

ps.ps2000_open_unit.restype = ct.c_int16
h = ps.ps2000_open_unit()
assert h > 0, f"PicoScope open failed: {h}"
ps.ps2000_set_channel(h, 0, 1, 0, RNG_A)   # Ch A: NW preamp
ps.ps2000_set_channel(h, 1, 1, 0, RNG_B)   # Ch B: NE direct

# ─── Pico NCO ─────────────────────────────────────────────────────
ser = serial.Serial('/dev/cu.usbmodem113301', 115200, timeout=2)
time.sleep(0.5)
ser.reset_input_buffer()


def nco(cmd):
    ser.reset_input_buffer()
    ser.write(f'{cmd}\n'.encode())
    time.sleep(0.05)
    return ser.readline().decode(errors='replace').strip()


def nco_temp():
    """Read NCO internal temperature. Returns (temp_c, raw_adc) or (None, None)."""
    resp = nco('TEMP')
    # Expected: "TEMP:27.43C ADC:17234"
    try:
        parts = resp.split()
        temp_c = float(parts[0].split(':')[1].rstrip('C'))
        adc_raw = int(parts[1].split(':')[1])
        return temp_c, adc_raw
    except (IndexError, ValueError):
        return None, None


def nco_time():
    """Read NCO uptime in microseconds. Returns int or None."""
    resp = nco('TIME')
    # Expected: "TIME:123456789us"
    try:
        return int(resp.split(':')[1].rstrip('us'))
    except (IndexError, ValueError):
        return None


# ─── Capture ──────────────────────────────────────────────────────
def capture_dual(navg=20):
    buf_a = (ct.c_int16 * N)()
    buf_b = (ct.c_int16 * N)()
    ov = ct.c_int16()
    mags_a, mags_b = [], []
    for _ in range(navg):
        ps.ps2000_set_trigger(h, 5, 0, 0, 0, 0)
        ticks = ct.c_int32()
        ps.ps2000_run_block(h, N, TIMEBASE, 1, ct.byref(ticks))
        for _ in range(500):
            if ps.ps2000_ready(h):
                break
            time.sleep(0.002)
        ps.ps2000_get_values(h, ct.byref(buf_a), ct.byref(buf_b),
                             None, None, ct.byref(ov), N, 0)
        da = np.array(buf_a[:], dtype=np.float64) * (RNG_A_MV / 32767.0)
        db = np.array(buf_b[:], dtype=np.float64) * (RNG_B_MV / 32767.0)
        da -= da.mean(); db -= db.mean()
        win = np.hanning(N)
        mags_a.append(np.abs(np.fft.rfft(da * win, n=NFFT)))
        mags_b.append(np.abs(np.fft.rfft(db * win, n=NFFT)))
    return np.mean(mags_a, axis=0), np.mean(mags_b, axis=0)


def peak_mag(sp, freq, w=5):
    b = int(round(freq / BIN_HZ))
    return float(sp[max(0, b-w):b+w+1].max())


# ─── CHSH math ────────────────────────────────────────────────────
def S_chsh_real(M, params):
    a1, a2, b1, b2 = params
    def I_p(al, be):
        a = np.array([np.cos(al), np.sin(al)])
        b = np.array([np.cos(be), np.sin(be)])
        return float((a @ M @ b)**2)
    def E(al, be):
        i1 = I_p(al, be); i2 = I_p(al+np.pi/2, be+np.pi/2)
        i3 = I_p(al, be+np.pi/2); i4 = I_p(al+np.pi/2, be)
        d = i1 + i2 + i3 + i4
        return (i1 + i2 - i3 - i4) / d if d > 1e-15 else 0
    return abs(E(a1, b1) - E(a1, b2) + E(a2, b1) + E(a2, b2))


def optimize_S(M):
    def neg_S(p): return -S_chsh_real(M, p)
    r = differential_evolution(neg_S, [(0, np.pi)]*4,
                               maxiter=3000, seed=42, tol=1e-10, polish=True)
    return -r.fun, r.x


# ─── Single epoch CHSH measurement ───────────────────────────────
def run_epoch(epoch_idx, settle_s=3.0):
    """Run one full CHSH measurement. Returns results dict."""
    t_start = datetime.now()

    # NCO telemetry (pre-measurement)
    temp_pre, adc_pre = nco_temp()
    uptime_pre = nco_time()

    # Start drive
    nco('Foff'); time.sleep(0.3)
    nco(f'F1:{F1}'); nco(f'F2:{F2}')
    time.sleep(settle_s)

    # Collect trials
    trials = []
    for trial in range(N_TRIALS):
        sp_a, sp_b = capture_dual(NAVG)
        trials.append([
            peak_mag(sp_a, F1), peak_mag(sp_b, F1),
            peak_mag(sp_a, F2), peak_mag(sp_b, F2),
        ])
        if (trial+1) % 50 == 0:
            last = np.array(trials[-20:])
            cv = np.std(last[:,0]) / np.mean(last[:,0]) * 100
            print(f"    {trial+1}/{N_TRIALS} — CV(f1_A)={cv:.1f}%")

    nco('Foff')

    # NCO telemetry (post-measurement)
    temp_post, adc_post = nco_temp()
    uptime_post = nco_time()

    trials = np.array(trials)

    # State matrix
    M_trials = []
    for t in trials:
        M = np.array([[t[0], t[1]], [t[2], t[3]]])
        r1n = np.linalg.norm(M[0]); r2n = np.linalg.norm(M[1])
        if r1n > 0 and r2n > 0:
            Mn = np.array([[M[0,0]/r1n, M[0,1]/r1n], [M[1,0]/r2n, M[1,1]/r2n]])
            Mn = Mn / np.linalg.norm(Mn, 'fro')
            M_trials.append(Mn)

    M_avg = np.mean(M_trials, axis=0)
    M_avg = M_avg / np.linalg.norm(M_avg, 'fro')

    U, sigma, Vh = np.linalg.svd(M_avg)
    C = 2*sigma[0]*sigma[1] / (sigma[0]**2 + sigma[1]**2)

    # Optimize S
    S_opt, params_opt = optimize_S(M_avg)

    # Bootstrap (2000 resamples)
    rng = np.random.default_rng(42 + epoch_idx)
    S_boots, C_boots = [], []
    for _ in range(2000):
        idx = rng.choice(len(M_trials), size=len(M_trials), replace=True)
        Mb = np.mean([M_trials[j] for j in idx], axis=0)
        Mb = Mb / np.linalg.norm(Mb, 'fro')
        S_boots.append(S_chsh_real(Mb, params_opt))
        _, sig_b, _ = np.linalg.svd(Mb)
        C_boots.append(2*sig_b[0]*sig_b[1] / (sig_b[0]**2 + sig_b[1]**2))

    S_boots = np.array(S_boots); C_boots = np.array(C_boots)
    ci_S = [float(np.percentile(S_boots, 2.5)), float(np.percentile(S_boots, 97.5))]
    sig_above_2 = (np.mean(S_boots) - 2.0) / np.std(S_boots) if np.std(S_boots) > 0 else 0

    # Block analysis (10 blocks of 20)
    block_size = 20
    n_blocks = len(M_trials) // block_size
    S_blocks = []
    for i in range(n_blocks):
        block = M_trials[i*block_size:(i+1)*block_size]
        Mb = np.mean(block, axis=0)
        Mb = Mb / np.linalg.norm(Mb, 'fro')
        S_blocks.append(S_chsh_real(Mb, params_opt))

    t_end = datetime.now()

    return {
        'epoch': epoch_idx,
        'timestamp_start': t_start.isoformat(),
        'timestamp_end': t_end.isoformat(),
        'duration_s': (t_end - t_start).total_seconds(),
        'nco_telemetry': {
            'temp_pre_c': temp_pre,
            'temp_post_c': temp_post,
            'adc_pre': adc_pre,
            'adc_post': adc_post,
            'uptime_pre_us': uptime_pre,
            'uptime_post_us': uptime_post,
        },
        'state_matrix': M_avg.tolist(),
        'svd_sigma': [float(s) for s in sigma],
        'concurrence': float(C),
        'S_optimal': float(S_opt),
        'S_bootstrap_mean': float(np.mean(S_boots)),
        'S_bootstrap_std': float(np.std(S_boots)),
        'S_ci_95': ci_S,
        'sigma_above_2': float(sig_above_2),
        'blocks_above_2': int(np.sum(np.array(S_blocks) > 2.0)),
        'n_blocks': n_blocks,
        'magnitudes': {
            'f1_A_mean': float(np.mean(trials[:,0])),
            'f1_B_mean': float(np.mean(trials[:,1])),
            'f2_A_mean': float(np.mean(trials[:,2])),
            'f2_B_mean': float(np.mean(trials[:,3])),
            'f1_A_cv': float(np.std(trials[:,0]) / np.mean(trials[:,0]) * 100),
            'f2_A_cv': float(np.std(trials[:,2]) / np.mean(trials[:,2]) * 100),
        },
        'optimal_angles_deg': {
            'alice': [float(np.degrees(params_opt[0])), float(np.degrees(params_opt[1]))],
            'bob': [float(np.degrees(params_opt[2])), float(np.degrees(params_opt[3]))],
        },
    }


# ═══════════════════════════════════════════════════════════════════
#  MAIN — Run E3 temporal stability protocol
# ═══════════════════════════════════════════════════════════════════
print("E3: Temporal Stability / PUF Repeatability")
print("=" * 60)
print(f"Mode pair: {F1} + {F2} Hz")
print(f"Epochs: {N_EPOCHS} × {N_TRIALS} trials @ {NAVG} avg")
print(f"Interval: {INTERVAL_S}s ({INTERVAL_S/60:.0f} min)")
print(f"Total duration: ~{(N_EPOCHS-1)*INTERVAL_S/60:.0f} min + measurement time")
print()

# Check NCO telemetry availability
temp_test, _ = nco_temp()
time_test = nco_time()
if temp_test is not None:
    print(f"  NCO temperature: {temp_test:.2f}°C (sensor available)")
else:
    print("  NCO temperature: NOT AVAILABLE (firmware update needed)")
if time_test is not None:
    print(f"  NCO uptime: {time_test/1e6:.1f}s")
else:
    print("  NCO uptime: NOT AVAILABLE (firmware update needed)")
print()

# ─── Run epochs ───────────────────────────────────────────────────
epochs = []
reference_matrix = None

for epoch in range(N_EPOCHS):
    print(f"\n{'━'*60}")
    print(f"  EPOCH {epoch+1}/{N_EPOCHS}  —  {datetime.now().strftime('%H:%M:%S')}")
    print(f"{'━'*60}")

    result = run_epoch(epoch)
    epochs.append(result)

    # Frobenius drift from reference (first epoch)
    M_curr = np.array(result['state_matrix'])
    if reference_matrix is None:
        reference_matrix = M_curr
        frob_drift = 0.0
    else:
        frob_drift = float(np.linalg.norm(M_curr - reference_matrix, 'fro')
                           / np.linalg.norm(reference_matrix, 'fro') * 100)
    result['frobenius_drift_pct'] = frob_drift

    # Drift from previous epoch
    if epoch > 0:
        M_prev = np.array(epochs[epoch-1]['state_matrix'])
        step_drift = float(np.linalg.norm(M_curr - M_prev, 'fro')
                           / np.linalg.norm(M_prev, 'fro') * 100)
    else:
        step_drift = 0.0
    result['step_drift_pct'] = step_drift

    # Report
    temp_str = f"{result['nco_telemetry']['temp_pre_c']:.1f}°C" if result['nco_telemetry']['temp_pre_c'] else "N/A"
    print(f"\n  C = {result['concurrence']:.4f}")
    print(f"  S = {result['S_optimal']:.4f} ({result['S_bootstrap_mean']:.4f} ± {result['S_bootstrap_std']:.4f})")
    print(f"  σ above 2.0: {result['sigma_above_2']:.0f}")
    print(f"  Blocks > 2.0: {result['blocks_above_2']}/{result['n_blocks']}")
    print(f"  Frobenius drift from epoch 1: {frob_drift:.3f}%")
    print(f"  Step drift from previous: {step_drift:.3f}%")
    print(f"  NCO temp: {temp_str}")
    print(f"  Duration: {result['duration_s']:.1f}s")

    # Pass/fail per epoch
    if result['S_ci_95'][0] > 2.5:
        print(f"  ★ PASS (S > 2.5 at 95% CI)")
    elif result['S_ci_95'][0] > 2.0:
        print(f"  ✓ PASS (S > 2.0 at 95% CI)")
    else:
        print(f"  ✗ FAIL (S CI includes ≤ 2.0)")

    # Wait for next epoch (unless last)
    if epoch < N_EPOCHS - 1:
        wait_s = INTERVAL_S - result['duration_s']
        if wait_s > 0:
            next_time = datetime.now().timestamp() + wait_s
            next_str = datetime.fromtimestamp(next_time).strftime('%H:%M:%S')
            print(f"\n  Waiting {wait_s:.0f}s until next epoch ({next_str})...")
            time.sleep(wait_s)

# ─── Final Analysis ───────────────────────────────────────────────
print(f"\n\n{'═'*60}")
print("  E3 TEMPORAL STABILITY — FINAL RESULTS")
print(f"{'═'*60}")

S_values = [e['S_optimal'] for e in epochs]
C_values = [e['concurrence'] for e in epochs]
drift_values = [e['frobenius_drift_pct'] for e in epochs]
temp_values = [e['nco_telemetry']['temp_pre_c'] for e in epochs
               if e['nco_telemetry']['temp_pre_c'] is not None]

print(f"\n  Epochs completed: {len(epochs)}")
print(f"  Time span: {epochs[0]['timestamp_start']} → {epochs[-1]['timestamp_end']}")
print(f"\n  S values: {[f'{s:.4f}' for s in S_values]}")
print(f"  S mean ± std: {np.mean(S_values):.4f} ± {np.std(S_values):.4f}")
print(f"  S range: [{min(S_values):.4f}, {max(S_values):.4f}]")
print(f"\n  C values: {[f'{c:.4f}' for c in C_values]}")
print(f"  C mean ± std: {np.mean(C_values):.4f} ± {np.std(C_values):.4f}")
print(f"\n  Frobenius drift from epoch 1: {[f'{d:.3f}%' for d in drift_values]}")
print(f"  Max drift: {max(drift_values):.3f}%")

if temp_values:
    print(f"\n  NCO temperature: {min(temp_values):.1f}°C → {max(temp_values):.1f}°C "
          f"(Δ={max(temp_values)-min(temp_values):.1f}°C)")

# Verdict
all_S_pass = all(s > 2.5 for s in S_values)
all_C_pass = all(c > 0.95 for c in C_values)
drift_pass = max(drift_values) < 1.0

print(f"\n  Criteria:")
print(f"    All S > 2.5:           {'PASS' if all_S_pass else 'FAIL'} (min={min(S_values):.4f})")
print(f"    All C > 0.95:          {'PASS' if all_C_pass else 'FAIL'} (min={min(C_values):.4f})")
print(f"    Frobenius drift < 1%:  {'PASS' if drift_pass else 'FAIL'} (max={max(drift_values):.3f}%)")

if all_S_pass and all_C_pass and drift_pass:
    verdict = 'PASS'
    print(f"\n  ★★ OVERALL: PASS — State is temporally stable (PUF property confirmed)")
elif all(s > 2.0 for s in S_values) and all(c > 0.90 for c in C_values):
    verdict = 'PASS_RELAXED'
    print(f"\n  ★ OVERALL: PASS (relaxed) — All S > 2.0, C > 0.90")
else:
    verdict = 'FAIL'
    print(f"\n  ✗ OVERALL: FAIL")

# ─── Save ─────────────────────────────────────────────────────────
DATA_DIR = Path('/Users/Mike/Code/wcfoma/data/results/quantum_bridge')
DATA_DIR.mkdir(parents=True, exist_ok=True)
ts = datetime.now().strftime('%Y%m%d_%H%M%S')
out_path = DATA_DIR / f'e3_temporal_stability_{ts}.json'

results = {
    'test': 'E3_temporal_stability',
    'timestamp': datetime.now().isoformat(),
    'config': {
        'modes': [F1, F2],
        'n_epochs': N_EPOCHS,
        'interval_s': INTERVAL_S,
        'n_trials': N_TRIALS,
        'n_avg': NAVG,
    },
    'summary': {
        'S_mean': float(np.mean(S_values)),
        'S_std': float(np.std(S_values)),
        'S_min': float(min(S_values)),
        'S_max': float(max(S_values)),
        'C_mean': float(np.mean(C_values)),
        'C_std': float(np.std(C_values)),
        'C_min': float(min(C_values)),
        'max_frobenius_drift_pct': float(max(drift_values)),
        'temp_range_c': [float(min(temp_values)), float(max(temp_values))] if temp_values else None,
        'verdict': verdict,
    },
    'epochs': epochs,
}

with open(out_path, 'w') as f:
    json.dump(results, f, indent=2)
print(f"\n  Saved: {out_path}")

# ─── Cleanup ──────────────────────────────────────────────────────
nco('Foff')
ser.close()
ps.ps2000_stop(h)
ps.ps2000_close_unit(ct.c_int16(h))
