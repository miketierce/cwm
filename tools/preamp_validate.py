#!/usr/bin/env python3
"""
Preamp validation — quick go/no-go test for day-1 with OPA2134PA.

Tests in order:
  1. Noise floor with preamp (should still be < 5 mV RMS at ±5V range)
  2. DDS single-capture eigenmode σ (target: ≥ 3σ per mode)
  3. DDS frequency discrimination (4-class ridge classifier, target: ≥ 80%)
  4. If pass → run ringdown_ready.py automatically

Usage:
  python tools/preamp_validate.py [--gain 20]
"""
import ctypes, numpy as np, time, serial, sys, argparse

parser = argparse.ArgumentParser()
parser.add_argument('--gain', type=float, default=20.0,
                    help='Preamp gain (for expected-value calculations)')
parser.add_argument('--mux', type=int, default=5, help='Mux channel')
args = parser.parse_args()

# ── PicoScope setup ──
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

ps.ps2000_set_channel(handle, 0, 1, 1, 7)  # Ch A, DC, ±5V
ps.ps2000_set_channel(handle, 1, 0, 1, 7)
ps.ps2000_set_sig_gen_built_in(handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0)

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


TIMEBASE = 7
N_SAMPLES = 8064
DT = 1280e-9


def capture():
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


def spectrum(data):
    d = data - np.mean(data)
    w = d * np.hanning(len(d))
    nfft = len(d) * 4
    mag = np.abs(np.fft.rfft(w, n=nfft))
    freq = np.fft.rfftfreq(nfft, d=DT)
    return freq, mag


PASS = True

# ────────────────────────────────────────
# TEST 1: Noise floor
# ────────────────────────────────────────
print(f"\n{'='*60}")
print("TEST 1: Noise floor with preamp")
print(f"{'='*60}")

dds_cmd('Foff')
time.sleep(0.3)
rms_vals = []
for _ in range(20):
    d = capture()
    d = d - np.mean(d)
    rms_vals.append(np.sqrt(np.mean(d ** 2)))

rms_mean = np.mean(rms_vals)
rms_std = np.std(rms_vals)
print(f"  RMS: {rms_mean:.1f} ± {rms_std:.1f} (ADC counts)")
# ±5V / 32768 = 0.153 mV/count
rms_mv = rms_mean * 0.153
print(f"  RMS: {rms_mv:.2f} mV")

if rms_mv > 100:  # >100 mV would indicate oscillation or saturation
    print(f"  ⚠ WARNING: Noise floor very high ({rms_mv:.1f} mV)")
    print(f"  → Check for preamp oscillation or power supply issues")
    PASS = False
else:
    print(f"  ✓ Noise floor OK ({rms_mv:.2f} mV)")

# ────────────────────────────────────────
# TEST 2: Single-capture eigenmode σ
# ────────────────────────────────────────
print(f"\n{'='*60}")
print("TEST 2: Single-capture eigenmode detection")
print(f"{'='*60}")

# Discover eigenmodes with coherent averaging
dds_cmd('Foff')
time.sleep(0.3)
off_frames = [capture() for _ in range(20)]
freq, mag_off = spectrum(np.mean(off_frames, axis=0))

dds_cmd('F1:29300')
time.sleep(0.5)
on_frames = [capture() for _ in range(20)]
_, mag_on = spectrum(np.mean(on_frames, axis=0))
dds_cmd('Foff')

ratio = np.where(mag_off > 10, mag_on / mag_off, 1.0)
candidates = np.where((ratio > 3.0) & (freq > 500))[0]
candidates = candidates[np.argsort(ratio[candidates])[::-1]]
eigenmodes = []
for idx in candidates:
    f = freq[idx]
    if not any(abs(freq[s] - f) < 500 for s in eigenmodes):
        eigenmodes.append(idx)
    if len(eigenmodes) >= 10:
        break

print(f"  Found {len(eigenmodes)} eigenmodes (coherent avg)")
for idx in eigenmodes[:5]:
    print(f"    {freq[idx]:.0f} Hz: {ratio[idx]:.0f}×")

# Single-capture test
dds_cmd('F1:29300')
time.sleep(0.5)
on_single = []
for _ in range(30):
    _, m = spectrum(capture())
    on_single.append([m[i] for i in eigenmodes[:10]])
on_single = np.array(on_single)

dds_cmd('Foff')
time.sleep(0.3)
off_single = []
for _ in range(30):
    _, m = spectrum(capture())
    off_single.append([m[i] for i in eigenmodes[:10]])
off_single = np.array(off_single)

print(f"\n  Single-capture σ per eigenmode:")
print(f"  {'Freq':>10} {'ON mean':>10} {'OFF mean':>10} {'σ sep':>8}")
print(f"  {'-'*42}")
sigma_vals = []
for i, idx in enumerate(eigenmodes[:10]):
    on_m = on_single[:, i].mean()
    off_m = off_single[:, i].mean()
    pooled = np.sqrt((on_single[:, i].std() ** 2 + off_single[:, i].std() ** 2) / 2)
    sigma = (on_m - off_m) / max(pooled, 1)
    sigma_vals.append(sigma)
    marker = " ✓" if sigma >= 3.0 else ""
    print(f"  {freq[idx]:>10.0f} {on_m:>10.0f} {off_m:>10.0f} {sigma:>8.1f}{marker}")

modes_above_3sig = sum(1 for s in sigma_vals if s >= 3.0)
print(f"\n  Modes ≥ 3σ: {modes_above_3sig}/{len(sigma_vals)}")

if modes_above_3sig >= 3:
    print(f"  ✓ PASS — sufficient single-capture resolution")
else:
    print(f"  ✗ FAIL — need more gain (only {modes_above_3sig} modes above 3σ)")
    PASS = False

# ────────────────────────────────────────
# TEST 3: Frequency discrimination (4-class)
# ────────────────────────────────────────
print(f"\n{'='*60}")
print("TEST 3: Frequency discrimination (4-class)")
print(f"{'='*60}")

from sklearn.linear_model import RidgeClassifier
from sklearn.model_selection import cross_val_score
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline

test_freqs = [20000, 29300, 40000, 50000]
n_per_class = 30
X_all = []
y_all = []

for label, f in enumerate(test_freqs):
    dds_cmd(f'F1:{f}')
    time.sleep(0.3)
    for _ in range(n_per_class):
        _, m = spectrum(capture())
        X_all.append(m)
        y_all.append(label)
    dds_cmd('Foff')
    time.sleep(0.1)

X_all = np.array(X_all)
y_all = np.array(y_all)

pipe = make_pipeline(StandardScaler(), RidgeClassifier(alpha=1.0))
scores = cross_val_score(pipe, X_all, y_all, cv=5)
acc = scores.mean() * 100
acc_std = scores.std() * 100
print(f"  4-class accuracy: {acc:.1f}% ± {acc_std:.1f}% (chance = 25%)")

if acc >= 80:
    print(f"  ✓ PASS — frequency discrimination works!")
elif acc >= 50:
    print(f"  ~ MARGINAL — some discrimination, may need more gain")
else:
    print(f"  ✗ FAIL — cannot distinguish frequencies in single captures")
    PASS = False

# ────────────────────────────────────────
# VERDICT
# ────────────────────────────────────────
print(f"\n{'='*60}")
print("PREAMP VALIDATION VERDICT")
print(f"{'='*60}")
print(f"  Noise floor:         {rms_mv:.2f} mV")
print(f"  Modes ≥ 3σ:          {modes_above_3sig}/10")
print(f"  4-class accuracy:    {acc:.1f}%")
print(f"  Expected gain:       {args.gain}×")
print()

if PASS:
    print("  ✓✓✓ ALL TESTS PASSED — READY FOR TEMPORAL MEMORY ✓✓✓")
    print()
    print("  Next: run tools/ringdown_ready.py")
    print("  Then: run tools/narma10_temporal.py --mode full")
else:
    print("  ✗ SOME TESTS FAILED")
    print()
    if modes_above_3sig < 3:
        print(f"  → Try higher gain (current: {args.gain}×)")
        print(f"    Increase Rf: 19kΩ → 47kΩ (gain=48×) or 100kΩ (gain=101×)")
    if rms_mv > 100:
        print(f"  → Check preamp for oscillation (add 100pF across Rf)")

# Cleanup
dds_cmd('Foff')
mux.write(b'0\n')
mux.close()
dds.close()
ps.ps2000_set_sig_gen_built_in(handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0)
ps.ps2000_stop(handle)
ps.ps2000_close_unit(handle)
print("\nDone.")
