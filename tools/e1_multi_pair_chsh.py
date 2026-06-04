"""
E1: Multi-Pair CHSH — Systematic (Not Cherry-Picked)

Runs the full CHSH protocol on 5 mode pairs ranked by log-ratio contrast
from the frequency sweep. Demonstrates that non-separability is a general
property of the plate, not an artifact of one lucky pair.

Hardware (same as T5.2b):
  SW TX PZT ← Pico NCO GP2+GP3 (column 23, separate board)
  NW RX PZT → preamp (×11) → PicoScope Ch A
  NE RX PZT → direct → PicoScope Ch B

Success criterion: ≥ 4/5 pairs yield S > 2.0 at 95% CI
"""
import ctypes as ct
import numpy as np
import serial
import time
from scipy.optimize import differential_evolution
import json
from datetime import datetime
from pathlib import Path

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
ps.ps2000_set_channel(h, 0, 1, 0, RNG_A)
ps.ps2000_set_channel(h, 1, 1, 0, RNG_B)

# ─── Pico NCO ─────────────────────────────────────────────────────
ser = serial.Serial('/dev/cu.usbmodem113301', 115200, timeout=2)
time.sleep(0.5)
ser.reset_input_buffer()

def nco(cmd):
    ser.reset_input_buffer()
    ser.write(f'{cmd}\n'.encode())
    time.sleep(0.05)
    return ser.readline().decode(errors='replace').strip()

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

# ─── Single-pair CHSH protocol ────────────────────────────────────
def run_chsh_pair(f1, f2, n_trials=200, navg=20, settle_s=3.0):
    """Run full CHSH on one mode pair. Returns results dict."""
    print(f"\n{'─'*60}")
    print(f"  Pair: {f1} Hz + {f2} Hz")
    print(f"{'─'*60}")

    # Start drive
    nco('Foff'); time.sleep(0.3)
    nco(f'F1:{f1}'); nco(f'F2:{f2}')
    time.sleep(settle_s)

    # Signal check
    sp_a, sp_b = capture_dual(navg)
    f1a = peak_mag(sp_a, f1); f2a = peak_mag(sp_a, f2)
    f1b = peak_mag(sp_b, f1); f2b = peak_mag(sp_b, f2)
    r1 = f1b / f1a if f1a > 1 else 0
    r2 = f2b / f2a if f2a > 1 else 0
    log_contrast = abs(np.log(max(r1, 0.001)) - np.log(max(r2, 0.001)))
    print(f"  Signal: f1 A={f1a:.0f} B={f1b:.0f} | f2 A={f2a:.0f} B={f2b:.0f}")
    print(f"  Ratio B/A: f1={r1:.3f}, f2={r2:.3f} | log-contrast={log_contrast:.2f}")

    # Collect trials
    trials = []
    for trial in range(n_trials):
        sp_a, sp_b = capture_dual(navg)
        trials.append([
            peak_mag(sp_a, f1), peak_mag(sp_b, f1),
            peak_mag(sp_a, f2), peak_mag(sp_b, f2),
        ])
        if (trial+1) % 50 == 0:
            last = np.array(trials[-20:])
            cv = np.std(last[:,0]) / np.mean(last[:,0]) * 100
            print(f"  {trial+1}/{n_trials} — CV(f1_A)={cv:.1f}%")

    nco('Foff')
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
    S_theory = 2*np.sqrt(1 + C**2)

    # Optimize
    S_opt, params_opt = optimize_S(M_avg)

    # Bootstrap (2000 for speed, still robust)
    rng = np.random.default_rng(42)
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
    ci_C = [float(np.percentile(C_boots, 2.5)), float(np.percentile(C_boots, 97.5))]
    sig_above_2 = (np.mean(S_boots) - 2.0) / np.std(S_boots) if np.std(S_boots) > 0 else 0

    # Block analysis
    block_size = 20
    n_blocks = len(M_trials) // block_size
    S_blocks = []
    for i in range(n_blocks):
        block = M_trials[i*block_size:(i+1)*block_size]
        Mb = np.mean(block, axis=0)
        Mb = Mb / np.linalg.norm(Mb, 'fro')
        S_blocks.append(S_chsh_real(Mb, params_opt))
    S_blocks = np.array(S_blocks)

    # Verdict
    if ci_S[0] > 2.0:
        verdict = 'PASS'
    elif np.mean(S_boots) > 2.0 and sig_above_2 > 2.0:
        verdict = 'PASS_2SIGMA'
    elif S_opt > 2.0:
        verdict = 'MARGINAL'
    else:
        verdict = 'FAIL'

    # Report
    a1, a2, b1, b2 = params_opt
    print(f"  ── Results ──")
    print(f"  C = {C:.4f} [{ci_C[0]:.4f}, {ci_C[1]:.4f}]")
    print(f"  S = {S_opt:.4f} (point) | {np.mean(S_boots):.4f} ± {np.std(S_boots):.4f} (boot)")
    print(f"  S 95% CI: [{ci_S[0]:.4f}, {ci_S[1]:.4f}]")
    print(f"  σ above 2.0: {sig_above_2:.1f}")
    print(f"  Blocks > 2.0: {np.sum(S_blocks > 2.0)}/{n_blocks}")
    print(f"  Verdict: {verdict}")

    # Spatial ratios for the record
    r_f1 = trials[:,1] / np.maximum(trials[:,0], 1)
    r_f2 = trials[:,3] / np.maximum(trials[:,2], 1)

    return {
        'modes': [f1, f2],
        'n_trials': n_trials,
        'state_matrix': M_avg.tolist(),
        'svd_sigma': [float(s) for s in sigma],
        'concurrence': float(C),
        'concurrence_ci_95': ci_C,
        'S_optimal': float(S_opt),
        'S_theory_max': float(S_theory),
        'optimal_angles_deg': {
            'alice': [float(np.degrees(a1)), float(np.degrees(a2))],
            'bob': [float(np.degrees(b1)), float(np.degrees(b2))]
        },
        'bootstrap': {
            'S_mean': float(np.mean(S_boots)),
            'S_std': float(np.std(S_boots)),
            'S_ci_95': ci_S,
            'sigma_above_2': float(sig_above_2),
            'n_resamples': 2000,
        },
        'blocks': {
            'S_values': S_blocks.tolist(),
            'S_mean': float(np.mean(S_blocks)),
            'S_sem': float(np.std(S_blocks) / np.sqrt(n_blocks)),
            'n_pass': int(np.sum(S_blocks > 2.0)),
            'n_blocks': n_blocks,
        },
        'signal_check': {
            'f1_chA': float(np.mean(trials[:,0])),
            'f1_chB': float(np.mean(trials[:,1])),
            'f2_chA': float(np.mean(trials[:,2])),
            'f2_chB': float(np.mean(trials[:,3])),
        },
        'spatial_ratios': {
            'f1_NE_over_NW': float(np.mean(r_f1)),
            'f2_NE_over_NW': float(np.mean(r_f2)),
            'log_contrast': float(log_contrast),
        },
        'verdict': verdict,
    }


# ═══════════════════════════════════════════════════════════════════
#  MAIN — Run all 5 pairs
# ═══════════════════════════════════════════════════════════════════

# Top 5 pairs from frequency sweep, ranked by log-ratio contrast.
# Selection: pairs where one mode is NW-dominant (B/A < 0.1) and
# the other is NE-dominant (B/A > 5), giving anti-diagonal state matrix.
PAIRS = [
    (34000, 70000),   # Best: B/A = 0.019 vs 57.0 (log-contrast ~7.7)
    (34000, 87000),   # B/A = 0.019 vs ~12  (from sweep high-contrast)
    (70000, 112000),  # B/A = 57.0 vs ~0.3  (inverted pair)
    (34000, 80000),   # B/A = 0.019 vs ~8   (different NE mode)
    (34000, 71000),   # B/A = 0.019 vs ~40  (adjacent to 70k, different mode?)
]

NTRIALS = 200
NAVG = 20

print("E1: Multi-Pair CHSH — Systematic Validation")
print("=" * 60)
print(f"Pairs: {len(PAIRS)}")
for i, (f1, f2) in enumerate(PAIRS):
    print(f"  [{i+1}] {f1} + {f2} Hz")
print(f"Trials per pair: {NTRIALS} × {NAVG} avg")
print(f"Success: ≥ 4/5 pairs with S > 2.0 at 95% CI")
print(f"Start time: {datetime.now().strftime('%H:%M:%S')}")

all_results = []
for i, (f1, f2) in enumerate(PAIRS):
    print(f"\n{'═'*60}")
    print(f"  PAIR {i+1}/{len(PAIRS)}: {f1} + {f2} Hz")
    print(f"{'═'*60}")
    t0 = time.time()
    result = run_chsh_pair(f1, f2, n_trials=NTRIALS, navg=NAVG)
    result['elapsed_s'] = time.time() - t0
    all_results.append(result)
    print(f"  (elapsed: {result['elapsed_s']:.0f}s)")

# ─── Summary ──────────────────────────────────────────────────────
print("\n\n" + "═"*60)
print("  E1 MULTI-PAIR CHSH — SUMMARY")
print("═"*60)
print(f"{'Pair':<15} {'C':>6} {'S_opt':>7} {'S_boot':>8} {'95% CI':>18} {'σ>2':>5} {'Verdict':<12}")
print("─"*75)

n_pass = 0
for r in all_results:
    f1, f2 = r['modes']
    pair_str = f"{f1//1000}k+{f2//1000}k"
    ci = r['bootstrap']['S_ci_95']
    print(f"{pair_str:<15} {r['concurrence']:>6.3f} {r['S_optimal']:>7.4f} "
          f"{r['bootstrap']['S_mean']:>7.4f}±{r['bootstrap']['S_std']:.4f} "
          f"[{ci[0]:.4f},{ci[1]:.4f}] {r['bootstrap']['sigma_above_2']:>5.1f} "
          f"{r['verdict']:<12}")
    if r['verdict'] in ('PASS', 'PASS_2SIGMA'):
        n_pass += 1

print("─"*75)
print(f"  Pairs with S > 2.0 (robust): {n_pass}/{len(PAIRS)}")
print()

if n_pass >= 4:
    overall = 'PASS'
    print("  ★★ E1 PASS — Non-separability confirmed across multiple mode pairs!")
    print("  Cherry-picking objection KILLED.")
elif n_pass >= 3:
    overall = 'PARTIAL_PASS'
    print(f"  ★ E1 PARTIAL — {n_pass}/5 pairs violate, marginal evidence")
elif n_pass >= 1:
    overall = 'WEAK'
    print(f"  △ E1 WEAK — Only {n_pass}/5 pairs violate")
else:
    overall = 'FAIL'
    print("  ✗ E1 FAIL — No pairs achieve robust violation")

# ─── Save ─────────────────────────────────────────────────────────
DATA_DIR = Path('/Users/Mike/Code/wcfoma/data/results/quantum_bridge')
DATA_DIR.mkdir(parents=True, exist_ok=True)
ts = datetime.now().strftime('%Y%m%d_%H%M%S')
out_path = DATA_DIR / f'e1_multi_pair_chsh_{ts}.json'

output = {
    'test': 'E1_multi_pair_CHSH',
    'timestamp': datetime.now().isoformat(),
    'config': {
        'pairs': PAIRS,
        'n_trials_per_pair': NTRIALS,
        'n_avg': NAVG,
        'rx_channels': {'A': 'NW_preamp_11x', 'B': 'NE_direct'},
        'tx': 'SW_PZT_PicoNCO',
        'selection_method': 'frequency_sweep_log_contrast_ranking',
    },
    'pair_results': all_results,
    'summary': {
        'n_pairs': len(PAIRS),
        'n_pass': n_pass,
        'overall_verdict': overall,
        'pass_threshold': '>=4/5 at 95% CI',
    },
}

with open(out_path, 'w') as f:
    json.dump(output, f, indent=2)
print(f"\n  Saved: {out_path}")
print(f"  Total time: {sum(r['elapsed_s'] for r in all_results):.0f}s")

# Cleanup
ser.close()
ps.ps2000_stop(h)
ps.ps2000_close_unit(ct.c_int16(h))
print("  Done.")
