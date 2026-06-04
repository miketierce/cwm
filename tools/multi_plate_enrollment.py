#!/usr/bin/env python3
"""
Multi-Plate Enrollment Sweep (Fine-Grain Mode Census)
=====================================================

Sweeps 30–120 kHz in fine steps on EACH relay channel independently.
Builds separate mode lists for each plate/receiver, then constructs
an expanded H matrix (N_modes × 4 receivers).

Hardware layout:
  TX: Pico NCO GP2 (F1:freq) → drives BOTH plates simultaneously
      (both SW TX PZTs wired to same NCO output)

  RX via relay mux → preamp (Board A ×11) → PicoScope Ch A:
    Relay 1: Plate I, NW
    Relay 2: Plate I, NE
    Relay 3: Plate H, NW
    Relay 4: Plate H, NE

Protocol:
  For each frequency:
    For each relay (1-4):
      Switch relay, settle, capture magnitude (averaged)
  → Produces a 4-column response matrix per frequency
  → Detect modes (peaks in any channel)
  → Build N_modes × 4 H matrix

Output:
  data/results/h_matrix/multi_plate_enrollment_TIMESTAMP.json
  data/results/h_matrix/multi_plate_enrollment_TIMESTAMP.npz

Usage:
  python3 tools/multi_plate_enrollment.py                    # 1 kHz steps (fast)
  python3 tools/multi_plate_enrollment.py --step 500         # 500 Hz steps
  python3 tools/multi_plate_enrollment.py --fine             # 200 Hz steps (thorough)
  python3 tools/multi_plate_enrollment.py --start 30000 --stop 120000 --step 200
"""
import ctypes as ct
import numpy as np
import serial
import time
import json
import argparse
from datetime import datetime
from pathlib import Path
from scipy.signal import find_peaks

# ─── Args ─────────────────────────────────────────────────────────
parser = argparse.ArgumentParser(description='Multi-plate enrollment sweep')
parser.add_argument('--start', type=int, default=30000,
                    help='Start frequency Hz (default: 30000)')
parser.add_argument('--stop', type=int, default=120000,
                    help='Stop frequency Hz (default: 120000)')
parser.add_argument('--step', type=int, default=1000,
                    help='Frequency step Hz (default: 1000)')
parser.add_argument('--navg', type=int, default=16,
                    help='Captures averaged per measurement (default: 16)')
parser.add_argument('--settle', type=float, default=0.25,
                    help='Settle time after freq change (default: 0.25s)')
parser.add_argument('--relay-settle', type=float, default=0.15,
                    help='Settle time after relay switch (default: 0.15s)')
parser.add_argument('--snr-threshold', type=float, default=5.0,
                    help='SNR threshold for mode detection (default: 5.0)')
parser.add_argument('--fine', action='store_true',
                    help='Fine sweep: 200 Hz steps')
parser.add_argument('--relays', type=str, default='1,2,3,4',
                    help='Comma-separated relay numbers to scan (default: 1,2,3,4)')
args = parser.parse_args()

if args.fine:
    args.step = 200

FREQS = list(range(args.start, args.stop + 1, args.step))
N_FREQS = len(FREQS)
RELAYS = [int(r.strip()) for r in args.relays.split(',')]
N_RELAYS = len(RELAYS)

RELAY_LABELS = {
    1: "Plate I NW",
    2: "Plate I NE",
    3: "Plate H NW",
    4: "Plate H NE",
    7: "Old plate SW",
    8: "Old plate NE",
}

# ─── Constants ────────────────────────────────────────────────────
PICO_LIB = '/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources/libps2000.dylib'
MUX_PORT = '/dev/cu.usbserial-11310'
NCO_PORT = '/dev/cu.usbmodem113301'

N = 3968
TIMEBASE = 7
FS = 781250.0
NFFT = N * 4
BIN_HZ = FS / NFFT
RNG = 6
RNG_MV = 2000.0

# ─── Header ──────────────────────────────────────────────────────
print("=" * 70)
print("  MULTI-PLATE ENROLLMENT SWEEP")
print("=" * 70)
print(f"  Range: {args.start/1000:.1f} – {args.stop/1000:.1f} kHz, step={args.step} Hz")
print(f"  Frequencies: {N_FREQS}")
print(f"  Relays: {RELAYS} ({', '.join(RELAY_LABELS.get(r, f'?{r}') for r in RELAYS)})")
print(f"  Averaging: {args.navg} captures/point")
print(f"  Settle: {args.settle}s (freq), {args.relay_settle}s (relay)")

# Time estimate: per freq = settle + N_relays*(relay_settle + navg*capture_time)
capture_time = args.navg * 0.012  # ~12ms per capture
per_freq = args.settle + N_RELAYS * (args.relay_settle + capture_time)
est_time = N_FREQS * per_freq
print(f"  Estimated time: {est_time:.0f}s ({est_time/60:.1f} min)")
print()


# ─── Hardware ────────────────────────────────────────────────────
print("[0] Initializing hardware...")
ps = ct.CDLL(PICO_LIB)
ps.ps2000_close_unit(ct.c_int16(1))
time.sleep(0.3)

ps.ps2000_open_unit.restype = ct.c_int16
h = ps.ps2000_open_unit()
if h <= 0:
    print(f"  ERROR: PicoScope open failed (handle={h})")
    raise SystemExit(1)
print(f"  PicoScope: handle={h}")
ps.ps2000_set_channel(h, 0, 1, 0, RNG)  # Ch A: enabled, AC, ±2V
ps.ps2000_set_channel(h, 1, 0, 0, RNG)  # Ch B: off (only using mux→preamp→Ch A)

# Relay mux
mux = serial.Serial(MUX_PORT, 9600, timeout=2, dsrdtr=False, rtscts=False)
mux.dtr = False
time.sleep(2.5)
mux.reset_input_buffer()
print(f"  Relay mux: {MUX_PORT}")

# NCO
nco_ser = serial.Serial(NCO_PORT, 115200, timeout=2)
time.sleep(0.5)
nco_ser.reset_input_buffer()
print(f"  NCO: {NCO_PORT}")


def nco(cmd):
    nco_ser.reset_input_buffer()
    nco_ser.write(f'{cmd}\n'.encode())
    time.sleep(0.05)
    return nco_ser.readline().decode(errors='replace').strip()


def set_relay(relay):
    mux.reset_input_buffer()
    mux.write(f'{relay}\r\n'.encode())
    time.sleep(args.relay_settle)
    mux.read(mux.in_waiting)


def capture_magnitude(navg):
    """Single-channel magnitude spectrum (Ch A only), averaged."""
    buf = (ct.c_int16 * N)()
    ov = ct.c_int16()
    mags = []
    for _ in range(navg):
        ps.ps2000_set_trigger(h, 5, 0, 0, 0, 0)
        ticks = ct.c_int32()
        ps.ps2000_run_block(h, N, TIMEBASE, 1, ct.byref(ticks))
        for _ in range(500):
            if ps.ps2000_ready(h):
                break
            time.sleep(0.002)
        ps.ps2000_get_values(h, ct.byref(buf), None, None, None,
                             ct.byref(ov), N, 0)
        d = np.array(buf[:], dtype=np.float64) * (RNG_MV / 32767.0)
        d -= d.mean()
        mags.append(np.abs(np.fft.rfft(d * np.hanning(N), n=NFFT)))
    return np.mean(mags, axis=0)


def peak_at(sp, freq, w=5):
    """Peak magnitude near target frequency."""
    b = int(round(freq / BIN_HZ))
    return float(sp[max(0, b-w):b+w+1].max())


# ─── Step 1: Noise floor per relay ───────────────────────────────
print("\n[1] Measuring noise floor (NCO off)...")
nco('Foff')
time.sleep(0.5)

noise_floors = {}
for relay in RELAYS:
    set_relay(relay)
    time.sleep(0.2)
    sp = capture_magnitude(8)
    nf = float(np.median(sp[20:]))
    noise_floors[relay] = nf
    peak = float(sp[20:].max())
    print(f"  Relay {relay} ({RELAY_LABELS.get(relay, '?')}): "
          f"noise={nf:.1f}, max={peak:.1f} ({peak/nf:.1f}×)")


# ─── Step 2: Frequency sweep, all relays per freq ────────────────
print(f"\n[2] Sweeping {N_FREQS} frequencies × {N_RELAYS} relays...")

# response[i, j] = peak magnitude at freq i, relay j
response = np.zeros((N_FREQS, N_RELAYS))

t0 = time.time()
for i, freq in enumerate(FREQS):
    nco(f'F1:{freq}')
    time.sleep(args.settle)

    for j, relay in enumerate(RELAYS):
        set_relay(relay)
        sp = capture_magnitude(args.navg)
        response[i, j] = peak_at(sp, freq)

    if (i + 1) % 10 == 0 or (i + 1) == N_FREQS:
        elapsed = time.time() - t0
        eta = elapsed / (i + 1) * (N_FREQS - i - 1)
        snrs = [response[i, j] / noise_floors[RELAYS[j]]
                for j in range(N_RELAYS)]
        snr_str = ' '.join(f"R{RELAYS[j]}:{snrs[j]:.0f}×" for j in range(N_RELAYS))
        print(f"  {i+1}/{N_FREQS} — {freq/1000:.1f} kHz — {snr_str} — ETA {eta:.0f}s")

nco('Foff')
elapsed_total = time.time() - t0
print(f"  Sweep complete: {elapsed_total:.0f}s ({elapsed_total/60:.1f} min)")


# ─── Step 3: Mode detection ──────────────────────────────────────
print(f"\n[3] Detecting modes (SNR > {args.snr_threshold}× on any channel)...")

# Compute SNR per channel
snr = np.zeros_like(response)
for j, relay in enumerate(RELAYS):
    snr[:, j] = response[:, j] / noise_floors[relay]

# Combined SNR (max across channels)
snr_max = np.max(snr, axis=1)

# Find peaks
min_distance = max(1, 2000 // args.step)  # At least 2 kHz apart
peaks_idx, _ = find_peaks(snr_max,
                          height=args.snr_threshold,
                          distance=min_distance,
                          prominence=2.0)

modes = []
for idx in peaks_idx:
    freq = FREQS[idx]
    mags = response[idx, :]
    snrs = snr[idx, :]
    modes.append({
        'freq_hz': freq,
        'magnitudes': {RELAY_LABELS.get(RELAYS[j], f'R{RELAYS[j]}'): float(mags[j])
                       for j in range(N_RELAYS)},
        'snrs': {RELAY_LABELS.get(RELAYS[j], f'R{RELAYS[j]}'): float(snrs[j])
                 for j in range(N_RELAYS)},
        'best_snr': float(np.max(snrs)),
        'best_channel': RELAY_LABELS.get(RELAYS[int(np.argmax(snrs))], '?'),
    })

modes.sort(key=lambda m: m['freq_hz'])
n_modes = len(modes)

print(f"\n  Detected {n_modes} modes:")
print(f"  {'Freq':>8} | " + ' | '.join(f"{'R'+str(r)+' SNR':>8}" for r in RELAYS) + " | Best")
print(f"  {'-'*8}-+-" + '-+-'.join(f"{'-'*8}" for _ in RELAYS) + "-+------")
for m in modes:
    snr_vals = [m['snrs'][RELAY_LABELS.get(RELAYS[j], f'R{RELAYS[j]}')] for j in range(N_RELAYS)]
    line = f"  {m['freq_hz']:>7} | " + ' | '.join(f"{s:>8.1f}" for s in snr_vals)
    line += f" | {m['best_snr']:.0f}×"
    print(line)


# ─── Step 4: Build multi-plate H matrix ─────────────────────────
print(f"\n[4] Building H matrix ({n_modes} × {N_RELAYS})...")

if n_modes < 2:
    print("  ERROR: Need at least 2 modes. Check signal chain!")
    nco_ser.close(); mux.close()
    ps.ps2000_stop(h); ps.ps2000_close_unit(ct.c_int16(h))
    raise SystemExit(1)

# H[i, j] = magnitude of mode i at receiver j
H_raw = np.zeros((n_modes, N_RELAYS))
for i, m in enumerate(modes):
    for j in range(N_RELAYS):
        key = RELAY_LABELS.get(RELAYS[j], f'R{RELAYS[j]}')
        H_raw[i, j] = m['magnitudes'][key]

# Row-normalize (unit spatial vector per mode)
row_norms = np.linalg.norm(H_raw, axis=1, keepdims=True)
H_norm = H_raw / np.where(row_norms > 0, row_norms, 1.0)

print(f"  H_raw shape: {H_raw.shape}")
print(f"  H_norm (row-normalized, first 10 modes):")
col_labels = [RELAY_LABELS.get(RELAYS[j], f'R{RELAYS[j]}')[:6] for j in range(N_RELAYS)]
print(f"    {'Freq':>8} | " + ' | '.join(f"{l:>6}" for l in col_labels))
for i in range(min(n_modes, 10)):
    freq = modes[i]['freq_hz']
    vals = ' | '.join(f"{H_norm[i,j]:>6.3f}" for j in range(N_RELAYS))
    print(f"    {freq:>7} | {vals}")
if n_modes > 10:
    print(f"    ... ({n_modes - 10} more modes)")


# ─── Step 5: SVD analysis ────────────────────────────────────────
print(f"\n[5] SVD analysis...")

U, sigma, Vh = np.linalg.svd(H_raw, full_matrices=False)
sigma_norm = sigma / sigma[0]
cond_number = sigma[0] / sigma[-1] if sigma[-1] > 0 else np.inf

# Effective rank
sigma_sq = sigma**2 / np.sum(sigma**2)
entropy = -np.sum(sigma_sq * np.log2(sigma_sq + 1e-15))
eff_rank = 2**entropy

print(f"  Singular values: {np.array2string(sigma, precision=1)}")
print(f"  Normalized:      {np.array2string(sigma_norm, precision=3)}")
print(f"  Condition number: {cond_number:.2f}")
print(f"  Effective rank (entropy): {eff_rank:.2f}")
print(f"  Max possible rank: {min(n_modes, N_RELAYS)}")


# ─── Step 6: Per-plate analysis ──────────────────────────────────
print(f"\n[6] Per-plate mode comparison...")

# Plate I (cols 0,1) vs Plate H (cols 2,3) — if we have 4 relays
if N_RELAYS >= 4:
    plate_i_power = np.sum(H_raw[:, :2]**2, axis=1)
    plate_h_power = np.sum(H_raw[:, 2:4]**2, axis=1)

    print(f"  {'Freq':>8} | {'Plate I':>8} | {'Plate H':>8} | {'Ratio I/H':>9} | Note")
    print(f"  {'-'*8}-+-{'-'*8}-+-{'-'*8}-+-{'-'*9}-+------")
    for i, m in enumerate(modes):
        pi = plate_i_power[i]
        ph = plate_h_power[i]
        ratio = pi / ph if ph > 0 else float('inf')
        note = ""
        if ratio > 3:
            note = "I-dominant"
        elif ratio < 0.33:
            note = "H-dominant"
        elif 0.5 < ratio < 2:
            note = "shared"
        print(f"  {m['freq_hz']:>7} | {pi:>8.0f} | {ph:>8.0f} | {ratio:>9.2f} | {note}")

    # Angular diversity between plates
    angles_i = np.arctan2(H_raw[:, 1], H_raw[:, 0])  # Plate I: NE/NW
    angles_h = np.arctan2(H_raw[:, 3], H_raw[:, 2])  # Plate H: NE/NW
    angle_diff = np.abs(angles_i - angles_h)
    print(f"\n  Angular diversity (I vs H): "
          f"mean={np.degrees(np.mean(angle_diff)):.1f}°, "
          f"max={np.degrees(np.max(angle_diff)):.1f}°")


# ─── Step 7: Signal chain verdict ────────────────────────────────
print(f"\n[7] Signal chain verdict...")
for j, relay in enumerate(RELAYS):
    n_above = int(np.sum(snr[:, j] > args.snr_threshold))
    max_snr = float(np.max(snr[:, j]))
    if max_snr > 10:
        status = "GOOD"
    elif max_snr > 3:
        status = "WEAK"
    else:
        status = "NO SIGNAL"
    print(f"  Relay {relay} ({RELAY_LABELS.get(relay, '?'):>10}): "
          f"{n_above:>3} modes above threshold, max SNR={max_snr:.1f}× — {status}")


# ─── Save ─────────────────────────────────────────────────────────
print(f"\n[8] Saving results...")
DATA_DIR = Path(__file__).parent.parent / 'data' / 'results' / 'h_matrix'
DATA_DIR.mkdir(parents=True, exist_ok=True)
ts = datetime.now().strftime('%Y%m%d_%H%M%S')

json_path = DATA_DIR / f'multi_plate_enrollment_{ts}.json'
out = {
    'test': 'multi_plate_enrollment',
    'timestamp': datetime.now().isoformat(),
    'config': {
        'start_hz': args.start,
        'stop_hz': args.stop,
        'step_hz': args.step,
        'n_freqs': N_FREQS,
        'navg': args.navg,
        'settle_s': args.settle,
        'relay_settle_s': args.relay_settle,
        'snr_threshold': args.snr_threshold,
        'relays': RELAYS,
        'relay_labels': {str(r): RELAY_LABELS.get(r, f'R{r}') for r in RELAYS},
    },
    'noise_floors': {str(r): noise_floors[r] for r in RELAYS},
    'n_modes': n_modes,
    'modes': modes,
    'h_matrix_raw': H_raw.tolist(),
    'h_matrix_normalized': H_norm.tolist(),
    'svd': {
        'singular_values': sigma.tolist(),
        'condition_number': float(cond_number),
        'effective_rank': float(eff_rank),
    },
    'mode_frequencies_hz': [m['freq_hz'] for m in modes],
    'elapsed_s': elapsed_total,
}
with open(json_path, 'w') as f:
    json.dump(out, f, indent=2)
print(f"  JSON: {json_path}")

npz_path = DATA_DIR / f'multi_plate_enrollment_{ts}.npz'
np.savez(npz_path,
         freqs=np.array(FREQS),
         response=response,
         snr=snr,
         H_raw=H_raw,
         H_norm=H_norm,
         noise_floors=np.array([noise_floors[r] for r in RELAYS]))
print(f"  NPZ: {npz_path}")


# ─── Summary ─────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("  ENROLLMENT SUMMARY")
print("=" * 70)
print(f"  Modes detected: {n_modes}")
print(f"  H matrix rank:  {min(n_modes, N_RELAYS)} (max possible={min(n_modes, N_RELAYS)})")
print(f"  SVD effective rank: {eff_rank:.2f}")
print(f"  Condition number:   {cond_number:.1f}")
if N_RELAYS >= 4 and n_modes >= 4:
    print(f"\n  ★ With {n_modes} modes × 4 receivers, H is {n_modes}×4 (rank up to 4)")
    print(f"    This is 2× the rank of the original 2-receiver setup!")
    print(f"    Re-running L3 with this H should break the absorption theorem.")
print(f"\n  Next: python3 tools/l3_train_through_h.py --h-matrix {json_path}")
print()

# Cleanup
nco_ser.close()
mux.close()
ps.ps2000_stop(h)
ps.ps2000_close_unit(ct.c_int16(h))
print("  Hardware closed.")
