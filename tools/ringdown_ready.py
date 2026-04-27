#!/usr/bin/env python3
"""
Ringdown validation script — ready for preamp day.

Measures eigenmode decay after DDS-off at 431 Hz capture rate (TB5/1024).
Designed to detect temporal memory: does eigenmode energy persist across captures?

Protocol:
  1. Discover eigenmodes (20-avg, TB7/8064 for resolution)
  2. Switch to fast capture (TB5/1024, 431 Hz)
  3. DDS on for 200 frames (steady-state)
  4. DDS off, capture 100 frames (ringdown)
  5. Measure per-frame eigenmode composite energy
  6. Fit exponential decay, report τ

Run before preamp: establishes noise-floor baseline.
Run after preamp: should show clear exponential decay at eigenmodes.

Usage:
  python tools/ringdown_ready.py [--drive 29300] [--mux 5] [--gain 1]
"""
import ctypes, numpy as np, time, serial, sys, argparse

# ── Args ──
parser = argparse.ArgumentParser()
parser.add_argument('--drive', type=int, default=29300, help='DDS drive frequency (Hz)')
parser.add_argument('--mux', type=int, default=5, help='Mux channel (1-8)')
parser.add_argument('--gain', type=float, default=1.0,
                    help='Preamp gain factor (for display scaling only)')
args = parser.parse_args()

# ── PicoScope setup ──
ps = ctypes.CDLL(
    "/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources/libps2000.dylib")
ps.ps2000_set_sig_gen_built_in.argtypes = [
    ctypes.c_int16, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32,
    ctypes.c_float, ctypes.c_float, ctypes.c_float, ctypes.c_float,
    ctypes.c_int32, ctypes.c_int32]

# Close stale handles
for h in range(1, 5):
    ps.ps2000_close_unit(h)
time.sleep(0.5)

handle = ps.ps2000_open_unit()
print(f"PicoScope handle: {handle}")
if handle <= 0:
    print("ERROR: Could not open PicoScope")
    sys.exit(1)

ps.ps2000_set_channel(handle, 0, 1, 1, 7)   # Ch A, DC, ±5V
ps.ps2000_set_channel(handle, 1, 0, 1, 7)   # Ch B off
ps.ps2000_set_sig_gen_built_in(handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0)

# ── Serial setup ──
mux = serial.Serial('/dev/cu.usbserial-11310', 9600, timeout=1)
time.sleep(2)
mux.reset_input_buffer()
mux.write(f'{args.mux}\n'.encode())
time.sleep(0.05)
print(f"Mux: {mux.readline().decode().strip()}")

dds = serial.Serial('/dev/cu.usbserial-11330', 115200, timeout=2)
time.sleep(2)
dds.reset_input_buffer()


def dds_cmd(cmd):
    dds.write(f'{cmd}\n'.encode())
    time.sleep(0.01)
    return dds.readline().decode().strip()


def capture_block(n_samples, timebase):
    """Single capture at given timebase/samples."""
    buf = (ctypes.c_int16 * n_samples)()
    ov = ctypes.c_int16(0)
    ps.ps2000_set_trigger(handle, 5, 0, 0, 0, 0)
    ms = ctypes.c_int32(0)
    ps.ps2000_run_block(handle, n_samples, timebase, 1, ctypes.byref(ms))
    for _ in range(5000):
        if ps.ps2000_ready(handle):
            break
        time.sleep(0.001)
    else:
        ps.ps2000_stop(handle)
        return np.zeros(n_samples)
    ps.ps2000_get_values(handle, ctypes.byref(buf), None, None, None,
                         ctypes.byref(ov), n_samples)
    return np.array(buf, dtype=np.float64)


def spectrum(data, dt):
    """Windowed FFT magnitude spectrum."""
    d = data - np.mean(data)
    w = d * np.hanning(len(d))
    nfft = len(d) * 4
    mag = np.abs(np.fft.rfft(w, n=nfft))
    freq = np.fft.rfftfreq(nfft, d=dt)
    return freq, mag


# ────────────────────────────────────────
# PHASE 1: Eigenmode discovery (slow capture for resolution)
# ────────────────────────────────────────
SLOW_TB = 7
SLOW_N = 8064
SLOW_DT = 1280e-9  # TB7 sample interval

print(f"\n{'='*60}")
print(f"PHASE 1: Eigenmode discovery (TB{SLOW_TB}/{SLOW_N}, 20-avg)")
print(f"Drive: DDS#1 @{args.drive} Hz, Mux ch {args.mux}")
print(f"{'='*60}")

# Noise baseline
dds_cmd('Foff')
time.sleep(0.3)
noise_frames = []
for _ in range(20):
    noise_frames.append(capture_block(SLOW_N, SLOW_TB))
freq_slow, mag_off = spectrum(np.mean(noise_frames, axis=0), SLOW_DT)

# DDS on
dds_cmd(f'F1:{args.drive}')
time.sleep(0.5)
on_frames = []
for _ in range(20):
    on_frames.append(capture_block(SLOW_N, SLOW_TB))
_, mag_on = spectrum(np.mean(on_frames, axis=0), SLOW_DT)
dds_cmd('Foff')

# Find eigenmodes
ratio = np.where(mag_off > 10, mag_on / mag_off, 1.0)
min_sep = 500  # Hz
candidates = np.where((ratio > 3.0) & (freq_slow > 500))[0]
candidates = candidates[np.argsort(ratio[candidates])[::-1]]

eigenmodes = []
for idx in candidates:
    f = freq_slow[idx]
    too_close = any(abs(freq_slow[s] - f) < min_sep for s in eigenmodes)
    if not too_close:
        eigenmodes.append(idx)
    if len(eigenmodes) >= 15:
        break

eigenmodes.sort(key=lambda i: ratio[i], reverse=True)

print(f"\nFound {len(eigenmodes)} eigenmodes:")
print(f"  {'Freq (Hz)':>12} {'Ratio':>8}")
print(f"  {'-'*22}")
for idx in eigenmodes:
    print(f"  {freq_slow[idx]:>12.0f} {ratio[idx]:>8.1f}×")

if not eigenmodes:
    print("ERROR: No eigenmodes found. Check DDS and wiring.")
    sys.exit(1)

# Map slow-capture eigenmode frequencies to fast-capture bin indices
eigenmode_freqs = [freq_slow[i] for i in eigenmodes[:10]]

# ────────────────────────────────────────
# PHASE 2: Fast ringdown capture (TB5/1024, 431 Hz)
# ────────────────────────────────────────
FAST_TB = 5
FAST_N = 1024
FAST_DT = 320e-9  # TB5 sample interval
FAST_WINDOW = FAST_N * FAST_DT  # 0.328 ms
FAST_RATE = 1.0 / (FAST_WINDOW + 0.001)  # ~300 Hz accounting for overhead

# Compute fast-capture bin indices for eigenmode frequencies
fast_nfft = FAST_N * 4
fast_freqs = np.fft.rfftfreq(fast_nfft, d=FAST_DT)
fast_bins = []
for ef in eigenmode_freqs:
    fb = np.argmin(np.abs(fast_freqs - ef))
    fast_bins.append(fb)
    # Include 1 neighbor on each side for spectral leakage
fast_bin_ranges = [(max(0, b - 1), min(len(fast_freqs) - 1, b + 1))
                   for b in fast_bins]

print(f"\n{'='*60}")
print(f"PHASE 2: Fast ringdown (TB{FAST_TB}/{FAST_N}, ~{1/0.00235:.0f} Hz)")
print(f"Eigenmode bins mapped to fast FFT:")
for i, (ef, fb) in enumerate(zip(eigenmode_freqs, fast_bins)):
    print(f"  Mode {i}: {ef:.0f} Hz → fast bin {fb} ({fast_freqs[fb]:.0f} Hz)")
print(f"{'='*60}")

N_STEADY = 200   # Frames with DDS on (steady-state)
N_RINGDOWN = 100  # Frames after DDS off
N_NOISE = 50      # Noise floor frames

def fast_eigenmode_energy(data):
    """Extract eigenmode composite energy from a single fast capture."""
    d = data - np.mean(data)
    w = d * np.hanning(len(d))
    mag = np.abs(np.fft.rfft(w, n=fast_nfft))
    # Sum energy at all eigenmode bins
    total = 0
    per_mode = []
    for lo, hi in fast_bin_ranges:
        e = np.max(mag[lo:hi + 1])
        per_mode.append(e)
        total += e
    return total, per_mode

# Phase 2a: Noise floor
print("\nCapturing noise floor...")
dds_cmd('Foff')
time.sleep(0.3)
noise_energies = []
for _ in range(N_NOISE):
    data = capture_block(FAST_N, FAST_TB)
    e, _ = fast_eigenmode_energy(data)
    noise_energies.append(e)
noise_mean = np.mean(noise_energies)
noise_std = np.std(noise_energies)
print(f"  Noise: {noise_mean:.0f} ± {noise_std:.0f}")

# Phase 2b: Steady-state
print(f"\nCapturing steady-state ({N_STEADY} frames, DDS on)...")
dds_cmd(f'F1:{args.drive}')
time.sleep(0.5)
steady_energies = []
steady_per_mode = []
for _ in range(N_STEADY):
    data = capture_block(FAST_N, FAST_TB)
    e, pm = fast_eigenmode_energy(data)
    steady_energies.append(e)
    steady_per_mode.append(pm)
steady_mean = np.mean(steady_energies)
steady_std = np.std(steady_energies)
print(f"  Steady-state: {steady_mean:.0f} ± {steady_std:.0f}")
print(f"  SNR vs noise: {(steady_mean - noise_mean) / max(noise_std, 1):.1f}σ")

# Phase 2c: Ringdown — DDS off, capture immediately
print(f"\nRingdown: DDS off → capturing {N_RINGDOWN} frames...")
dds_cmd('Foff')  # Fire-and-forget would be faster but we want confirmation
t0 = time.time()

rd_energies = []
rd_times = []
rd_per_mode = []
for _ in range(N_RINGDOWN):
    data = capture_block(FAST_N, FAST_TB)
    t = time.time() - t0
    e, pm = fast_eigenmode_energy(data)
    rd_energies.append(e)
    rd_times.append(t)
    rd_per_mode.append(pm)

rd_energies = np.array(rd_energies)
rd_times = np.array(rd_times)

# ────────────────────────────────────────
# PHASE 3: Analysis
# ────────────────────────────────────────
print(f"\n{'='*60}")
print("PHASE 3: Ringdown analysis")
print(f"{'='*60}")

# Sigma above noise for each frame
rd_sigma = (rd_energies - noise_mean) / max(noise_std, 1)

print(f"\n{'Frame':>6} {'Time(ms)':>10} {'Energy':>10} {'σ above noise':>14} {'%steady':>9}")
print("-" * 55)
for i in range(min(30, len(rd_times))):
    pct = rd_energies[i] / max(steady_mean, 1) * 100
    marker = " ***" if rd_sigma[i] > 3.0 else " *" if rd_sigma[i] > 2.0 else ""
    print(f"{i:>6} {rd_times[i]*1000:>10.1f} {rd_energies[i]:>10.0f} "
          f"{rd_sigma[i]:>14.1f} {pct:>8.1f}%{marker}")

# Count significant frames
sig3 = np.sum(rd_sigma > 3.0)
sig2 = np.sum(rd_sigma > 2.0)
print(f"\n  Frames > 3σ: {sig3}/{len(rd_energies)}")
print(f"  Frames > 2σ: {sig2}/{len(rd_energies)}")

if sig3 >= 3:
    last_sig = np.where(rd_sigma > 3.0)[0][-1]
    print(f"  Last 3σ frame: #{last_sig} at {rd_times[last_sig]*1000:.1f} ms")
    print(f"  → Ringdown detectable for ~{rd_times[last_sig]*1000:.0f} ms")

# Attempt exponential fit: E(t) = A * exp(-t/τ) + C
from scipy.optimize import curve_fit

def exp_decay(t, A, tau, C):
    return A * np.exp(-t / tau) + C

try:
    # Use first 50 frames for fit
    n_fit = min(50, len(rd_times))
    p0 = [steady_mean - noise_mean, 0.002, noise_mean]  # initial guess: τ~2ms
    bounds = ([0, 0.0001, 0], [1e8, 1.0, 1e8])
    popt, pcov = curve_fit(exp_decay, rd_times[:n_fit], rd_energies[:n_fit],
                           p0=p0, bounds=bounds, maxfev=5000)
    A_fit, tau_fit, C_fit = popt
    residuals = rd_energies[:n_fit] - exp_decay(rd_times[:n_fit], *popt)
    ss_res = np.sum(residuals**2)
    ss_tot = np.sum((rd_energies[:n_fit] - np.mean(rd_energies[:n_fit]))**2)
    r_squared = 1 - ss_res / max(ss_tot, 1)

    print(f"\n  Exponential fit: E(t) = {A_fit:.0f} × exp(-t/{tau_fit*1000:.2f}ms) + {C_fit:.0f}")
    print(f"  τ = {tau_fit*1000:.2f} ms")
    print(f"  R² = {r_squared:.3f}")
    if r_squared > 0.5 and tau_fit > 0.0005:
        print(f"  ✓ RINGDOWN DETECTED — τ = {tau_fit*1000:.2f} ms")
        retention = np.exp(-2.35e-3 / tau_fit) * 100
        print(f"  At 425 Hz capture rate: {retention:.1f}% retention per step")
    else:
        print(f"  ✗ No clear decay (R²={r_squared:.3f}, τ={tau_fit*1000:.2f} ms)")
except Exception as e:
    print(f"\n  Exponential fit failed: {e}")
    print("  (Expected pre-preamp — signal is below noise floor)")

# ── Summary ──
print(f"\n{'='*60}")
print("SUMMARY")
print(f"{'='*60}")
print(f"  Drive frequency:      {args.drive} Hz")
print(f"  Eigenmodes found:     {len(eigenmodes)}")
print(f"  Best eigenmode ratio: {ratio[eigenmodes[0]]:.0f}× (coherent avg)")
print(f"  Noise floor:          {noise_mean:.0f} ± {noise_std:.0f}")
print(f"  Steady-state:         {steady_mean:.0f} ± {steady_std:.0f}")
print(f"  Steady/noise:         {(steady_mean - noise_mean) / max(noise_std, 1):.1f}σ")
print(f"  3σ ringdown frames:   {sig3}/{len(rd_energies)}")
if args.gain > 1:
    print(f"  Preamp gain:          {args.gain}×")

# Cleanup
dds_cmd('Foff')
mux.write(b'0\n')
mux.close()
dds.close()
ps.ps2000_set_sig_gen_built_in(handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0)
ps.ps2000_stop(handle)
ps.ps2000_close_unit(handle)
print("\nDone.")
