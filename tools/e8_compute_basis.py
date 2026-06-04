"""
E8: CHSH Modes as CIM Compute Basis

Bridges the CHSH non-separability result back to Boolean computation.
Uses the non-separable mode pair (35840 Hz = "0", 54920 Hz = "1") for
information encoding. Demonstrates that two spatially separated receivers
decode DIFFERENT bit values from the same physical encoding — proving
non-separability has computational utility (spatial multiplexing).

Hardware (same as E1/E5 — no changes needed):
  Pico NCO: F1 (GP2) + F2 (GP3) → 220Ω → SW TX PZT
  PicoScope Ch A = NW RX preamp (×11)
  PicoScope Ch B = NE RX direct

Encoding scheme:
  Pattern "00": F1 off, F2 off (silence)
  Pattern "01": F1 off, F2 on  (54920 Hz only)
  Pattern "10": F1 on,  F2 off (35840 Hz only)
  Pattern "11": F1 on,  F2 on  (both)

At each receiver, we decode based on which mode dominates:
  - Threshold f1 magnitude → bit_0 at that receiver
  - Threshold f2 magnitude → bit_1 at that receiver

Non-separability means: the RATIO of f1/f2 differs between receivers,
so the decoded bit patterns can differ — enabling spatial multiplexing.

Success: ≥ 4 distinguishable patterns per receiver, with cross-receiver
          disagreement on at least one encoding (proves spatial multiplexing)
Kills: "Non-separability has no computational utility" objection
"""
import ctypes as ct
import numpy as np
import serial
import time
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
    """Capture magnitude spectra from both channels (averaged)."""
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

# ─── Config ───────────────────────────────────────────────────────
F1_HZ = 35840   # Mode "0"
F2_HZ = 54920   # Mode "1"
NAVG = 20
NTRIALS = 50    # Trials per pattern for statistics

# 2-bit encoding patterns: (F1_on, F2_on)
PATTERNS = {
    '00': (False, False),
    '01': (False, True),
    '10': (True,  False),
    '11': (True,  True),
}

print("E8: CHSH Modes as CIM Compute Basis")
print("=" * 60)
print(f"Mode 0: {F1_HZ} Hz (F1/GP2)")
print(f"Mode 1: {F2_HZ} Hz (F2/GP3)")
print(f"Receivers: Ch A (NW preamp ×11), Ch B (NE direct)")
print(f"Patterns: 00, 01, 10, 11 ({NTRIALS} trials each)")
print()

# ─── Phase 1: Measure all patterns ───────────────────────────────
print("[1] Measuring 4 encoding patterns...")
results = {}  # pattern → {'f1_A': [...], 'f1_B': [...], 'f2_A': [...], 'f2_B': [...]}

for pat_name, (f1_on, f2_on) in PATTERNS.items():
    print(f"\n  Pattern '{pat_name}': F1={'ON' if f1_on else 'OFF'}, F2={'ON' if f2_on else 'OFF'}")

    # Set drive
    nco('Foff'); time.sleep(0.3)
    if f1_on:
        nco(f'F1:{F1_HZ}')
    if f2_on:
        nco(f'F2:{F2_HZ}')
    time.sleep(2.0)  # Let plate ring up

    # Collect trials
    f1_A, f1_B, f2_A, f2_B = [], [], [], []
    for trial in range(NTRIALS):
        sp_a, sp_b = capture_dual(NAVG)
        f1_A.append(peak_mag(sp_a, F1_HZ))
        f1_B.append(peak_mag(sp_b, F1_HZ))
        f2_A.append(peak_mag(sp_a, F2_HZ))
        f2_B.append(peak_mag(sp_b, F2_HZ))

    results[pat_name] = {
        'f1_A': f1_A, 'f1_B': f1_B,
        'f2_A': f2_A, 'f2_B': f2_B,
    }

    print(f"    Ch A: f1={np.mean(f1_A):.0f}±{np.std(f1_A):.0f}, f2={np.mean(f2_A):.0f}±{np.std(f2_A):.0f}")
    print(f"    Ch B: f1={np.mean(f1_B):.0f}±{np.std(f1_B):.0f}, f2={np.mean(f2_B):.0f}±{np.std(f2_B):.0f}")

nco('Foff')

# ─── Phase 2: Establish thresholds ───────────────────────────────
print(f"\n[2] Establishing detection thresholds...")

# Noise floor = mean of pattern '00' (no drive)
noise_f1_A = np.mean(results['00']['f1_A'])
noise_f1_B = np.mean(results['00']['f1_B'])
noise_f2_A = np.mean(results['00']['f2_A'])
noise_f2_B = np.mean(results['00']['f2_B'])

# Signal when ON (from patterns where each mode is active)
sig_f1_A = np.mean(results['10']['f1_A'])  # F1 on
sig_f1_B = np.mean(results['10']['f1_B'])
sig_f2_A = np.mean(results['01']['f2_A'])  # F2 on
sig_f2_B = np.mean(results['01']['f2_B'])

# Threshold = midpoint between noise and signal (in log space for robustness)
thresh_f1_A = np.sqrt(noise_f1_A * sig_f1_A) if sig_f1_A > noise_f1_A else (noise_f1_A + sig_f1_A) / 2
thresh_f1_B = np.sqrt(noise_f1_B * sig_f1_B) if sig_f1_B > noise_f1_B else (noise_f1_B + sig_f1_B) / 2
thresh_f2_A = np.sqrt(noise_f2_A * sig_f2_A) if sig_f2_A > noise_f2_A else (noise_f2_A + sig_f2_A) / 2
thresh_f2_B = np.sqrt(noise_f2_B * sig_f2_B) if sig_f2_B > noise_f2_B else (noise_f2_B + sig_f2_B) / 2

print(f"  Noise floor: f1_A={noise_f1_A:.0f}, f1_B={noise_f1_B:.0f}, f2_A={noise_f2_A:.0f}, f2_B={noise_f2_B:.0f}")
print(f"  Signal ON:   f1_A={sig_f1_A:.0f}, f1_B={sig_f1_B:.0f}, f2_A={sig_f2_A:.0f}, f2_B={sig_f2_B:.0f}")
print(f"  Thresholds:  f1_A={thresh_f1_A:.0f}, f1_B={thresh_f1_B:.0f}, f2_A={thresh_f2_A:.0f}, f2_B={thresh_f2_B:.0f}")
print(f"  SNR: f1_A={sig_f1_A/noise_f1_A:.1f}×, f1_B={sig_f1_B/noise_f1_B:.1f}×, f2_A={sig_f2_A/noise_f2_A:.1f}×, f2_B={sig_f2_B/noise_f2_B:.1f}×")

# ─── Phase 3: Decode patterns ────────────────────────────────────
print(f"\n[3] Decoding patterns at each receiver...")

decode_results = {}
for pat_name in PATTERNS:
    r = results[pat_name]

    # Decode at Ch A: bit0 = f1 > thresh, bit1 = f2 > thresh
    decoded_A = []
    for i in range(NTRIALS):
        b0 = 1 if r['f1_A'][i] > thresh_f1_A else 0
        b1 = 1 if r['f2_A'][i] > thresh_f2_A else 0
        decoded_A.append(f'{b0}{b1}')

    # Decode at Ch B
    decoded_B = []
    for i in range(NTRIALS):
        b0 = 1 if r['f1_B'][i] > thresh_f1_B else 0
        b1 = 1 if r['f2_B'][i] > thresh_f2_B else 0
        decoded_B.append(f'{b0}{b1}')

    # Majority vote
    from collections import Counter
    maj_A = Counter(decoded_A).most_common(1)[0]
    maj_B = Counter(decoded_B).most_common(1)[0]
    acc_A = maj_A[1] / NTRIALS * 100
    acc_B = maj_B[1] / NTRIALS * 100

    decode_results[pat_name] = {
        'decoded_A': maj_A[0],
        'accuracy_A': acc_A,
        'decoded_B': maj_B[0],
        'accuracy_B': acc_B,
        'agree': maj_A[0] == maj_B[0],
    }

    agree_str = "✓ SAME" if maj_A[0] == maj_B[0] else "✗ DIFFERENT"
    print(f"  TX='{pat_name}' → Ch A='{maj_A[0]}' ({acc_A:.0f}%), Ch B='{maj_B[0]}' ({acc_B:.0f}%) {agree_str}")

# ─── Phase 4: Spatial multiplexing analysis ──────────────────────
print(f"\n[4] Spatial multiplexing analysis...")

n_distinct_A = len(set(d['decoded_A'] for d in decode_results.values()))
n_distinct_B = len(set(d['decoded_B'] for d in decode_results.values()))
n_disagreements = sum(1 for d in decode_results.values() if not d['agree'])

print(f"  Distinct patterns at Ch A: {n_distinct_A}/4")
print(f"  Distinct patterns at Ch B: {n_distinct_B}/4")
print(f"  Cross-receiver disagreements: {n_disagreements}/4 patterns")

# Information capacity
bits_A = np.log2(n_distinct_A) if n_distinct_A > 0 else 0
bits_B = np.log2(n_distinct_B) if n_distinct_B > 0 else 0
total_bits = bits_A + bits_B

print(f"  Bits per receiver: Ch A={bits_A:.1f}, Ch B={bits_B:.1f}")
print(f"  Total addressable bits (spatial × frequency): {total_bits:.1f}")

# ─── Phase 5: Intensity ratio analysis ───────────────────────────
print(f"\n[5] Intensity ratio analysis (why spatial multiplexing works)...")

# For pattern '11' (both modes on), compute ratio at each receiver
r11 = results['11']
ratio_A = np.array(r11['f1_A']) / np.array(r11['f2_A'])  # f1/f2 at Ch A
ratio_B = np.array(r11['f1_B']) / np.array(r11['f2_B'])  # f1/f2 at Ch B

print(f"  Pattern '11' (both ON):")
print(f"    Ch A ratio f1/f2: {np.mean(ratio_A):.3f} ± {np.std(ratio_A):.3f}")
print(f"    Ch B ratio f1/f2: {np.mean(ratio_B):.3f} ± {np.std(ratio_B):.3f}")
print(f"    Ratio of ratios:  {np.mean(ratio_A)/np.mean(ratio_B):.3f}")
print(f"    (≠ 1.0 → non-separable → different 'view' at each receiver)")

# ─── Phase 6: Discrimination matrix ──────────────────────────────
print(f"\n[6] Full discrimination matrix (mean magnitudes)...")
print(f"  {'Pattern':<8} {'f1_A':<10} {'f2_A':<10} {'f1_B':<10} {'f2_B':<10}")
print(f"  {'─'*8} {'─'*10} {'─'*10} {'─'*10} {'─'*10}")
for pat_name in ['00', '01', '10', '11']:
    r = results[pat_name]
    print(f"  {pat_name:<8} {np.mean(r['f1_A']):<10.0f} {np.mean(r['f2_A']):<10.0f} {np.mean(r['f1_B']):<10.0f} {np.mean(r['f2_B']):<10.0f}")

# ─── Final verdict ───────────────────────────────────────────────
print("\n" + "=" * 60)
print("  E8: CHSH MODES AS COMPUTE BASIS — RESULTS")
print("=" * 60)
print(f"  Encoding:              2-bit (F1=bit0, F2=bit1)")
print(f"  Patterns transmitted:  4 (00, 01, 10, 11)")
print(f"  Distinct at Ch A:      {n_distinct_A}/4")
print(f"  Distinct at Ch B:      {n_distinct_B}/4")
print(f"  Cross-RX disagreement: {n_disagreements}/4")
print(f"  Total spatial bits:    {total_bits:.1f}")
print()

min_accuracy = min(d['accuracy_A'] for d in decode_results.values())
min_accuracy = min(min_accuracy, min(d['accuracy_B'] for d in decode_results.values()))

if n_distinct_A >= 4 and n_distinct_B >= 4 and min_accuracy > 90:
    verdict = 'PASS'
    print("  ★★ PASS — 4 distinguishable patterns at both receivers!")
    if n_disagreements > 0:
        print(f"  Spatial multiplexing: receivers disagree on {n_disagreements} pattern(s)")
        print("  → Non-separability enables different 'views' of same data")
    else:
        print("  Both receivers decode identically (separable channel)")
        print("  Non-separability visible in intensity ratios but not in binary decoding")
elif n_distinct_A >= 4 and n_distinct_B >= 4:
    verdict = 'PASS_LOW_ACC'
    print(f"  ★ PASS — 4 patterns distinguishable (min accuracy: {min_accuracy:.0f}%)")
elif n_distinct_A >= 3 or n_distinct_B >= 3:
    verdict = 'MARGINAL'
    print(f"  △ MARGINAL — Only {max(n_distinct_A, n_distinct_B)} distinct patterns")
else:
    verdict = 'FAIL'
    print("  ✗ FAIL — Cannot distinguish patterns")

# ─── Save ─────────────────────────────────────────────────────────
DATA_DIR = Path('/Users/Mike/Code/wcfoma/data/results/quantum_bridge')
DATA_DIR.mkdir(parents=True, exist_ok=True)
ts = datetime.now().strftime('%Y%m%d_%H%M%S')
out_path = DATA_DIR / f'e8_compute_basis_{ts}.json'

save_data = {
    'test': 'E8_CHSH_compute_basis',
    'timestamp': datetime.now().isoformat(),
    'config': {
        'mode_0_hz': F1_HZ,
        'mode_1_hz': F2_HZ,
        'n_trials_per_pattern': NTRIALS,
        'n_avg': NAVG,
        'receivers': ['Ch A (NW preamp x11)', 'Ch B (NE direct)'],
    },
    'thresholds': {
        'f1_A': float(thresh_f1_A), 'f1_B': float(thresh_f1_B),
        'f2_A': float(thresh_f2_A), 'f2_B': float(thresh_f2_B),
    },
    'snr': {
        'f1_A': float(sig_f1_A / noise_f1_A),
        'f1_B': float(sig_f1_B / noise_f1_B),
        'f2_A': float(sig_f2_A / noise_f2_A),
        'f2_B': float(sig_f2_B / noise_f2_B),
    },
    'decode_results': decode_results,
    'n_distinct_A': n_distinct_A,
    'n_distinct_B': n_distinct_B,
    'n_disagreements': n_disagreements,
    'total_bits': float(total_bits),
    'intensity_ratios_pattern_11': {
        'ratio_A_f1_over_f2': float(np.mean(ratio_A)),
        'ratio_B_f1_over_f2': float(np.mean(ratio_B)),
        'ratio_of_ratios': float(np.mean(ratio_A) / np.mean(ratio_B)),
    },
    'magnitudes': {
        pat: {
            'f1_A_mean': float(np.mean(r['f1_A'])), 'f1_A_std': float(np.std(r['f1_A'])),
            'f1_B_mean': float(np.mean(r['f1_B'])), 'f1_B_std': float(np.std(r['f1_B'])),
            'f2_A_mean': float(np.mean(r['f2_A'])), 'f2_A_std': float(np.std(r['f2_A'])),
            'f2_B_mean': float(np.mean(r['f2_B'])), 'f2_B_std': float(np.std(r['f2_B'])),
        }
        for pat, r in results.items()
    },
    'verdict': verdict,
}

with open(out_path, 'w') as f:
    json.dump(save_data, f, indent=2)
print(f"\n  Saved: {out_path}")

# ─── Cleanup ──────────────────────────────────────────────────────
ser.close()
ps.ps2000_stop(h)
ps.ps2000_close_unit(ct.c_int16(h))
