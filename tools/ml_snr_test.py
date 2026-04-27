#!/usr/bin/env python3
"""
ML classification test: Can a ridge classifier distinguish DDS-on from DDS-off
using SINGLE-CAPTURE full spectra as feature vectors?

If yes → reservoir computing is viable even at low per-bin SNR.
The readout layer finds the optimal linear combination of hundreds of bins.
"""
import ctypes, numpy as np, time, serial, sys
from sklearn.linear_model import RidgeClassifier, Ridge
from sklearn.model_selection import cross_val_score, StratifiedKFold
from sklearn.preprocessing import StandardScaler

ps = ctypes.CDLL("/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources/libps2000.dylib")
ps.ps2000_set_sig_gen_built_in.argtypes = [
    ctypes.c_int16, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32,
    ctypes.c_float, ctypes.c_float, ctypes.c_float, ctypes.c_float,
    ctypes.c_int32, ctypes.c_int32]

DT = 1280e-9
TIMEBASE = 7
N_SAMPLES = 8064
CH_RANGE = 7  # ±2V

for h in range(1, 5):
    ps.ps2000_close_unit(h)
time.sleep(0.5)

handle = ps.ps2000_open_unit()
print(f"PicoScope handle: {handle}")
if handle <= 0:
    sys.exit(1)

ps.ps2000_set_channel(handle, 0, 1, 1, CH_RANGE)
ps.ps2000_set_channel(handle, 1, 0, 1, CH_RANGE)
ps.ps2000_set_sig_gen_built_in(handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0)

mux = serial.Serial('/dev/cu.usbserial-11310', 9600, timeout=1)
time.sleep(2)
mux.reset_input_buffer()
mux.write(b'5\n'); time.sleep(0.05)
print(f"Mux: {mux.readline().decode().strip()}")

dds = serial.Serial('/dev/cu.usbserial-11330', 115200, timeout=2)
time.sleep(2)
dds.reset_input_buffer()


def dds_cmd(cmd):
    dds.write(f'{cmd}\n'.encode())
    time.sleep(0.01)
    return dds.readline().decode().strip()


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


def spectral_features(data):
    """Full magnitude spectrum as feature vector."""
    d = data - np.mean(data)
    w = d * np.hanning(len(d))
    mag = np.abs(np.fft.rfft(w))
    return mag[1:]  # drop DC


# ═══════════════════════════════════════════════════════
# TEST 1: Binary classification — DDS-on vs DDS-off
# ═══════════════════════════════════════════════════════
print("\n" + "="*70)
print("TEST 1: Binary classification — DDS ON vs OFF (single captures)")
print("="*70)

N_SAMPLES_PER_CLASS = 60

# Collect DDS-off samples
print(f"Collecting {N_SAMPLES_PER_CLASS} DDS-off captures...")
dds_cmd('Foff')
time.sleep(0.3)
off_spectra = []
for i in range(N_SAMPLES_PER_CLASS):
    off_spectra.append(spectral_features(capture()))
off_spectra = np.array(off_spectra)

# Collect DDS-on samples (29300 Hz)
print(f"Collecting {N_SAMPLES_PER_CLASS} DDS-on captures (F1:29300)...")
dds_cmd('F1:29300')
time.sleep(0.3)
on_spectra = []
for i in range(N_SAMPLES_PER_CLASS):
    on_spectra.append(spectral_features(capture()))
on_spectra = np.array(on_spectra)
dds_cmd('Foff')

X = np.vstack([off_spectra, on_spectra])
y = np.array([0]*N_SAMPLES_PER_CLASS + [1]*N_SAMPLES_PER_CLASS)

# Shuffle
perm = np.random.RandomState(42).permutation(len(y))
X, y = X[perm], y[perm]

scaler = StandardScaler()
X_s = scaler.fit_transform(X)

clf = RidgeClassifier(alpha=1.0)
cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
scores = cross_val_score(clf, X_s, y, cv=cv, scoring='accuracy')
print(f"\n  Ridge classifier (5-fold CV): {scores.mean():.1%} ± {scores.std():.1%}")
print(f"  Per-fold: {', '.join(f'{s:.1%}' for s in scores)}")
print(f"  Chance level: 50%")
print(f"  Feature vector length: {X.shape[1]}")

# ═══════════════════════════════════════════════════════
# TEST 2: Multi-class — distinguish different DDS frequencies
# ═══════════════════════════════════════════════════════
print("\n" + "="*70)
print("TEST 2: Multi-class — distinguish 4 different DDS frequencies")
print("="*70)

freqs = [0, 20000, 29300, 40000]  # 0 = off
N_PER_FREQ = 40
all_spectra = []
all_labels = []

for fi, freq in enumerate(freqs):
    if freq == 0:
        dds_cmd('Foff')
    else:
        dds_cmd(f'F1:{freq}')
    time.sleep(0.3)
    print(f"Collecting {N_PER_FREQ} captures at {freq} Hz...")
    for _ in range(N_PER_FREQ):
        all_spectra.append(spectral_features(capture()))
        all_labels.append(fi)
    dds_cmd('Foff')
    time.sleep(0.1)

X2 = np.array(all_spectra)
y2 = np.array(all_labels)

perm2 = np.random.RandomState(42).permutation(len(y2))
X2, y2 = X2[perm2], y2[perm2]

X2_s = StandardScaler().fit_transform(X2)

clf2 = RidgeClassifier(alpha=1.0)
cv2 = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
scores2 = cross_val_score(clf2, X2_s, y2, cv=cv2, scoring='accuracy')
print(f"\n  4-class Ridge (5-fold CV): {scores2.mean():.1%} ± {scores2.std():.1%}")
print(f"  Per-fold: {', '.join(f'{s:.1%}' for s in scores2)}")
print(f"  Chance level: 25%")

# ═══════════════════════════════════════════════════════
# TEST 3: Interleaved A/B/A/B to test temporal discrimination
# ═══════════════════════════════════════════════════════
print("\n" + "="*70)
print("TEST 3: Interleaved freq switching — temporal discrimination")
print("="*70)

N_CYCLES = 40
interleaved_spectra = []
interleaved_labels = []
freq_a, freq_b = 25000, 35000

print(f"Interleaving {freq_a} Hz and {freq_b} Hz ({N_CYCLES} cycles)...")
for i in range(N_CYCLES):
    # Freq A
    dds_cmd(f'F1:{freq_a}')
    time.sleep(0.01)  # minimal settle
    interleaved_spectra.append(spectral_features(capture()))
    interleaved_labels.append(0)

    # Freq B
    dds_cmd(f'F1:{freq_b}')
    time.sleep(0.01)
    interleaved_spectra.append(spectral_features(capture()))
    interleaved_labels.append(1)

dds_cmd('Foff')

X3 = np.array(interleaved_spectra)
y3 = np.array(interleaved_labels)

# DON'T shuffle — test on second half (temporal split)
n_train = N_CYCLES  # first half
X3_train, y3_train = X3[:n_train*2:2], y3[:n_train*2:2]  # even indices = freq_a
X3_test_a = X3[1:n_train*2:2]  # odd indices in first half = freq_b
# Actually let's just do CV on shuffled
perm3 = np.random.RandomState(42).permutation(len(y3))
X3_p, y3_p = X3[perm3], y3[perm3]
X3_s = StandardScaler().fit_transform(X3_p)
scores3 = cross_val_score(RidgeClassifier(alpha=1.0), X3_s, y3_p,
                          cv=StratifiedKFold(5, shuffle=True, random_state=42))
print(f"\n  Interleaved 2-class (5-fold CV): {scores3.mean():.1%} ± {scores3.std():.1%}")
print(f"  Chance level: 50%")

# Also test temporal split
n_half = len(y3) // 2
scaler3 = StandardScaler().fit(X3[:n_half])
X3_train_s = scaler3.transform(X3[:n_half])
X3_test_s = scaler3.transform(X3[n_half:])
clf3 = RidgeClassifier(alpha=1.0).fit(X3_train_s, y3[:n_half])
acc_temporal = clf3.score(X3_test_s, y3[n_half:])
print(f"  Temporal split (train first half, test second): {acc_temporal:.1%}")

# ═══════════════════════════════════════════════════════
# TEST 4: Regression — predict DDS frequency from spectrum
# ═══════════════════════════════════════════════════════
print("\n" + "="*70)
print("TEST 4: Regression — predict DDS frequency from single capture")
print("="*70)

test_freqs = [20000, 25000, 29300, 33000, 37000, 40000]
N_PER = 30
reg_spectra = []
reg_targets = []

for freq in test_freqs:
    dds_cmd(f'F1:{freq}')
    time.sleep(0.3)
    print(f"Collecting {N_PER} at {freq} Hz...")
    for _ in range(N_PER):
        reg_spectra.append(spectral_features(capture()))
        reg_targets.append(freq)
    dds_cmd('Foff')
    time.sleep(0.1)

X4 = np.array(reg_spectra)
y4 = np.array(reg_targets, dtype=float)

perm4 = np.random.RandomState(42).permutation(len(y4))
X4, y4 = X4[perm4], y4[perm4]
X4_s = StandardScaler().fit_transform(X4)

reg = Ridge(alpha=10.0)
from sklearn.model_selection import cross_val_predict
y4_pred = cross_val_predict(reg, X4_s, y4, cv=5)
from sklearn.metrics import r2_score, mean_absolute_error
r2 = r2_score(y4, y4_pred)
mae = mean_absolute_error(y4, y4_pred)
corr = np.corrcoef(y4, y4_pred)[0, 1]
print(f"\n  Ridge regression (5-fold CV):")
print(f"  R² = {r2:.3f}, MAE = {mae:.0f} Hz, Pearson r = {corr:.3f}")
print(f"  (R²>0 means better than predicting the mean)")

# Per-frequency accuracy
print(f"\n  Per-frequency predictions:")
for freq in test_freqs:
    mask = (y4 == freq)
    pred_mean = y4_pred[mask].mean()
    pred_std = y4_pred[mask].std()
    print(f"    Actual {freq:>5} Hz → predicted {pred_mean:.0f} ± {pred_std:.0f} Hz")

# Cleanup
dds.close()
mux.write(b'0\n'); mux.close()
ps.ps2000_set_sig_gen_built_in(handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0)
ps.ps2000_stop(handle)
ps.ps2000_close_unit(handle)
print("\nDone.")
