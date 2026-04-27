#!/usr/bin/env python3
"""
Two-DDS Interaction Mapping.

Drive DDS#1 and DDS#2 at various frequency pairs simultaneously.
Measure eigenmode response and identify intermodulation products
that appear ONLY when both DDS are active (nonlinear mixing in glass).

This is the key test for computational nonlinearity — a linear system
would only show the sum of individual DDS responses, but a nonlinear
reservoir produces new spectral features at f1±f2, 2f1±f2, etc.

Protocol:
  1. Noise baseline (both DDS off)
  2. DDS#1-only sweep (reference)
  3. DDS#2-only sweep (reference)
  4. Both-DDS sweep (all frequency pairs)
  5. Interaction analysis: both_response - (dds1_only + dds2_only)
     Positive residuals = nonlinear intermodulation products

Uses optimal drive frequencies from eigenmode_sweep results.

Usage:
  python tools/two_dds_interaction.py
  python tools/two_dds_interaction.py --f1 50000 --f2 55000  # Single pair
  python tools/two_dds_interaction.py --top 5  # Top 5 drives per DDS
"""
import ctypes, numpy as np, time, serial, sys, argparse, os
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--f1', type=int, nargs='+', default=None,
                    help='DDS#1 frequencies (Hz). Default: auto from sweep data')
parser.add_argument('--f2', type=int, nargs='+', default=None,
                    help='DDS#2 frequencies (Hz). Default: auto from sweep data')
parser.add_argument('--top', type=int, default=4,
                    help='Number of top drive freqs per DDS (if auto)')
parser.add_argument('--navg', type=int, default=20,
                    help='Coherent averages per measurement')
parser.add_argument('--mux-channel', type=int, default=5,
                    help='Mux channel for readout')
args = parser.parse_args()

DATA_DIR = Path(__file__).parent.parent / 'data' / 'results'
DATA_DIR.mkdir(parents=True, exist_ok=True)

# ── Auto-select best drive frequencies from sweep data ──
def load_best_drives(dds_num, top_n):
    """Load eigenmode sweep NPZ and pick top drive frequencies by best ratio."""
    pattern = f"eigenmode_sweep_dds{dds_num}_*.npz"
    candidates = sorted(DATA_DIR.glob(pattern))
    if not candidates:
        return None
    data = np.load(candidates[-1])
    drive_freqs = data['drive_freqs']
    all_ratios = data['all_ratios']
    # Best ratio per drive frequency
    best_per_drive = np.max(all_ratios, axis=(1, 2))  # max across channels and freq bins
    top_idx = np.argsort(best_per_drive)[-top_n:][::-1]
    return drive_freqs[top_idx].tolist()


if args.f1 is None:
    args.f1 = load_best_drives(1, args.top)
    if args.f1 is None:
        print("No DDS#1 sweep data found. Run eigenmode_sweep.py --dds 1 first,")
        print("or specify frequencies with --f1")
        sys.exit(1)
    print(f"Auto-selected DDS#1 drives from sweep: {args.f1}")

if args.f2 is None:
    args.f2 = load_best_drives(2, args.top)
    if args.f2 is None:
        print("No DDS#2 sweep data found. Run eigenmode_sweep.py --dds 2 first,")
        print("or specify frequencies with --f2")
        sys.exit(1)
    print(f"Auto-selected DDS#2 drives from sweep: {args.f2}")

n_pairs = len(args.f1) * len(args.f2)
n_solo = len(args.f1) + len(args.f2)
n_total = 1 + n_solo + n_pairs  # noise + solo + pairs
est_time = n_total * (args.navg * 0.015 + 0.5)

print(f"\nTwo-DDS Interaction Mapping")
print(f"  DDS#1 frequencies: {args.f1}")
print(f"  DDS#2 frequencies: {args.f2}")
print(f"  {n_pairs} frequency pairs + {n_solo} solo references")
print(f"  {args.navg} coherent averages per point")
print(f"  Mux channel: {args.mux_channel}")
print(f"  Estimated time: {est_time:.0f}s ({est_time/60:.1f} min)")

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
print(f"\nPicoScope handle: {handle}")
if handle <= 0:
    sys.exit(1)

ps.ps2000_set_channel(handle, 0, 1, 1, 7)
ps.ps2000_set_channel(handle, 1, 0, 1, 7)
ps.ps2000_set_sig_gen_built_in(handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0)

mux = serial.Serial('/dev/cu.usbserial-11310', 9600, timeout=1)
time.sleep(2)
mux.reset_input_buffer()

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


def coherent_avg_spectrum(n_avg):
    frames = [capture() for _ in range(n_avg)]
    avg = np.mean(frames, axis=0)
    d = avg - np.mean(avg)
    w = d * np.hanning(len(d))
    nfft = len(d) * 4
    mag = np.abs(np.fft.rfft(w, n=nfft))
    freq = np.fft.rfftfreq(nfft, d=DT)
    return freq, mag


# ── Select mux channel ──
mux.write(f'{args.mux_channel}\n'.encode())
time.sleep(0.15)
mux.readline()
time.sleep(0.1)

# ── Step 1: Noise baseline ──
print("\n=== Noise baseline (both DDS off) ===")
dds_cmd('Foff')
time.sleep(0.3)
freq_axis, noise_mag = coherent_avg_spectrum(args.navg)
noise_rms = np.sqrt(np.mean(noise_mag ** 2))
print(f"  RMS={noise_rms:.0f}")

n_bins = len(freq_axis)

# ── Step 2: DDS#1-only reference ──
print("\n=== DDS#1-only reference ===")
dds1_spectra = {}
for f1 in args.f1:
    dds_cmd('Foff')
    time.sleep(0.1)
    dds_cmd(f'F1:{f1}')
    time.sleep(0.3)
    _, mag = coherent_avg_spectrum(args.navg)
    dds1_spectra[f1] = mag
    ratio_max = np.max(mag / np.where(noise_mag > 10, noise_mag, 1))
    best_bin = np.argmax(mag / np.where(noise_mag > 10, noise_mag, 1))
    print(f"  {f1:>6} Hz: peak {freq_axis[best_bin]:.0f}Hz ({ratio_max:.0f}×)")

# ── Step 3: DDS#2-only reference ──
print("\n=== DDS#2-only reference ===")
dds2_spectra = {}
for f2 in args.f2:
    dds_cmd('Foff')
    time.sleep(0.1)
    dds_cmd(f'F2:{f2}')
    time.sleep(0.3)
    _, mag = coherent_avg_spectrum(args.navg)
    dds2_spectra[f2] = mag
    ratio_max = np.max(mag / np.where(noise_mag > 10, noise_mag, 1))
    best_bin = np.argmax(mag / np.where(noise_mag > 10, noise_mag, 1))
    print(f"  {f2:>6} Hz: peak {freq_axis[best_bin]:.0f}Hz ({ratio_max:.0f}×)")

# ── Step 4: Both-DDS pairs ──
print("\n=== Both-DDS pairs ===")
pair_spectra = {}
t0 = time.time()
pair_count = 0

for f1 in args.f1:
    for f2 in args.f2:
        dds_cmd('Foff')
        time.sleep(0.1)
        dds_cmd(f'F1:{f1}')
        time.sleep(0.05)
        dds_cmd(f'F2:{f2}')
        time.sleep(0.3)

        _, mag = coherent_avg_spectrum(args.navg)
        pair_spectra[(f1, f2)] = mag
        pair_count += 1

        # Compute interaction: both - (solo1 + solo2 - noise)
        # This isolates products that only appear with both active
        linear_sum = dds1_spectra[f1] + dds2_spectra[f2] - noise_mag
        interaction = mag - linear_sum

        # Find top positive interaction bins (nonlinear products)
        int_ratio = interaction / np.where(noise_mag > 10, noise_mag, 1)
        top_int = np.argsort(int_ratio)[-5:][::-1]
        pos_products = [(freq_axis[b], int_ratio[b])
                        for b in top_int if int_ratio[b] > 3.0]

        elapsed = time.time() - t0
        eta = (n_pairs - pair_count) * elapsed / pair_count if pair_count else 0

        if pos_products:
            prods_str = ", ".join(f"{f:.0f}Hz({r:.0f}×)" for f, r in pos_products[:3])
            print(f"  F1={f1:>6}, F2={f2:>6}: IM products: {prods_str}  "
                  f"[{pair_count}/{n_pairs}, ETA {eta:.0f}s]")
        else:
            print(f"  F1={f1:>6}, F2={f2:>6}: no IM products above 3×  "
                  f"[{pair_count}/{n_pairs}, ETA {eta:.0f}s]")

dds_cmd('Foff')

# ── Step 5: Analysis ──
print(f"\n{'='*60}")
print("INTERACTION ANALYSIS")
print(f"{'='*60}")

# For each pair, compute interaction strength
print(f"\n{'Pair':>20} {'IM products':>12} {'Max IM ratio':>14} {'Best IM freq':>14}")
print(f"  {'-'*62}")

all_im_products = []
pair_results = []

for f1 in args.f1:
    for f2 in args.f2:
        linear_sum = dds1_spectra[f1] + dds2_spectra[f2] - noise_mag
        interaction = pair_spectra[(f1, f2)] - linear_sum
        int_ratio = interaction / np.where(noise_mag > 10, noise_mag, 1)

        # Count distinct IM products above threshold
        min_sep = 500  # Hz
        candidates = np.where((int_ratio > 3.0) & (freq_axis > 500))[0]
        candidates = candidates[np.argsort(int_ratio[candidates])[::-1]]

        im_modes = []
        for idx in candidates:
            f = freq_axis[idx]
            if not any(abs(freq_axis[s] - f) < min_sep for s in im_modes):
                im_modes.append(idx)

        n_im = len(im_modes)
        if n_im > 0:
            best_idx = im_modes[0]
            best_ratio = int_ratio[best_idx]
            best_freq = freq_axis[best_idx]
        else:
            best_ratio = 0
            best_freq = 0

        pair_results.append({
            'f1': f1, 'f2': f2, 'n_im': n_im,
            'best_ratio': best_ratio, 'best_freq': best_freq,
            'im_modes': im_modes
        })

        for idx in im_modes:
            all_im_products.append({
                'freq': freq_axis[idx], 'ratio': int_ratio[idx],
                'f1': f1, 'f2': f2
            })

        print(f"  F1={f1:>6},F2={f2:>6} {n_im:>12} {best_ratio:>14.1f}× "
              f"{best_freq:>14.0f}")

# Sort pairs by IM product count
pair_results.sort(key=lambda p: (-p['n_im'], -p['best_ratio']))

print(f"\n{'='*60}")
print("BEST PAIRS FOR NONLINEAR COMPUTATION")
print(f"{'='*60}")
for i, p in enumerate(pair_results[:5]):
    print(f"  {i+1}. F1={p['f1']}, F2={p['f2']}: "
          f"{p['n_im']} IM products, best {p['best_ratio']:.1f}× "
          f"at {p['best_freq']:.0f} Hz")

# Global IM product census
print(f"\n{'='*60}")
print("INTERMODULATION PRODUCT CENSUS")
print(f"{'='*60}")

# Deduplicate IM products by frequency
all_im_products.sort(key=lambda x: -x['ratio'])
unique_im = []
for prod in all_im_products:
    if not any(abs(prod['freq'] - u['freq']) < 500 for u in unique_im):
        unique_im.append(prod)

print(f"\n{len(unique_im)} distinct IM frequencies detected")
print(f"{'Rank':>5} {'IM Freq (Hz)':>14} {'Ratio':>8} {'Source pair':>20}")
print(f"  {'-'*50}")
for i, im in enumerate(unique_im[:15]):
    print(f"  {i+1:>3} {im['freq']:>14.0f} {im['ratio']:>8.1f}× "
          f"F1={im['f1']},F2={im['f2']}")

# Superposition test: compare actual both-on vs linear sum
print(f"\n{'='*60}")
print("SUPERPOSITION VIOLATION (nonlinearity metric)")
print(f"{'='*60}")

for f1 in args.f1:
    for f2 in args.f2:
        linear_sum = dds1_spectra[f1] + dds2_spectra[f2] - noise_mag
        actual = pair_spectra[(f1, f2)]
        # RMS of the difference (interaction energy)
        diff = actual - linear_sum
        diff_rms = np.sqrt(np.mean(diff ** 2))
        linear_rms = np.sqrt(np.mean(linear_sum ** 2))
        nonlin_pct = 100.0 * diff_rms / linear_rms if linear_rms > 0 else 0
        print(f"  F1={f1:>6},F2={f2:>6}: "
              f"interaction={diff_rms:.0f}, linear={linear_rms:.0f}, "
              f"nonlinearity={nonlin_pct:.1f}%")

# ── Save data ──
out_path = DATA_DIR / "two_dds_interaction.npz"
np.savez(out_path,
         f1_list=np.array(args.f1),
         f2_list=np.array(args.f2),
         freq_axis=freq_axis,
         noise_mag=noise_mag,
         dds1_spectra=np.array([dds1_spectra[f] for f in args.f1]),
         dds2_spectra=np.array([dds2_spectra[f] for f in args.f2]),
         pair_spectra=np.array([[pair_spectra[(f1, f2)] for f2 in args.f2]
                                for f1 in args.f1]),
         n_avg=args.navg,
         mux_channel=args.mux_channel)
print(f"\nData saved to {out_path}")

# Cleanup
mux.write(b'0\n')
mux.close()
dds.close()
ps.ps2000_set_sig_gen_built_in(handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0)
ps.ps2000_stop(handle)
ps.ps2000_close_unit(handle)
print("Done.")
