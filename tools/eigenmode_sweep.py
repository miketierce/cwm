#!/usr/bin/env python3
"""
Eigenmode characterization sweep.

Sweep DDS#1 across 1–200 kHz in fine steps, 20-avg coherent captures on
multiple mux channels. Build a frequency → eigenmode excitation matrix.

This maps the plate's "transfer function" — which drive frequencies excite
which eigenmodes at which receivers. This is the computational capacity
of the reservoir.

Output:
  - Console summary of top eigenmodes per drive frequency
  - NPZ data file for offline analysis
  - Identifies optimal drive frequency ranges for maximum eigenmode diversity

Usage:
  python tools/eigenmode_sweep.py [--start 1000] [--stop 200000] [--step 2000]
  python tools/eigenmode_sweep.py --fine  # Fine sweep around known good range
"""
import ctypes, numpy as np, time, serial, sys, argparse, os
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--start', type=int, default=5000, help='Start frequency (Hz)')
parser.add_argument('--stop', type=int, default=200000, help='Stop frequency (Hz)')
parser.add_argument('--step', type=int, default=5000, help='Frequency step (Hz)')
parser.add_argument('--navg', type=int, default=20, help='Coherent averages per point')
parser.add_argument('--fine', action='store_true',
                    help='Fine sweep: 20–60 kHz in 1 kHz steps')
parser.add_argument('--mux-channels', type=str, default='5',
                    help='Comma-separated mux channels (e.g. "1,3,5,7")')
parser.add_argument('--dds', type=int, choices=[1, 2], default=1,
                    help='Which DDS board to sweep (1 or 2)')
args = parser.parse_args()

if args.fine:
    args.start = 20000
    args.stop = 60000
    args.step = 1000

mux_channels = [int(c) for c in args.mux_channels.split(',')]
drive_freqs = list(range(args.start, args.stop + 1, args.step))

DATA_DIR = Path(__file__).parent.parent / 'data' / 'results'
DATA_DIR.mkdir(parents=True, exist_ok=True)

print(f"Eigenmode Characterization Sweep")
print(f"  DDS#{args.dds}: {args.start}–{args.stop} Hz, step {args.step} Hz")
print(f"  {len(drive_freqs)} drive frequencies")
print(f"  {args.navg} coherent averages per point")
print(f"  Mux channels: {mux_channels}")
est_time = len(drive_freqs) * len(mux_channels) * (args.navg * 0.015 + 0.5)
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


# ── Step 1: Measure noise baseline on each mux channel ──
print("\n=== Noise baseline (all DDS off) ===")
dds_cmd('Foff')
time.sleep(0.3)

noise_spectra = {}
for ch in mux_channels:
    mux.write(f'{ch}\n'.encode())
    time.sleep(0.15)
    mux.readline()
    time.sleep(0.1)
    freq_axis, mag = coherent_avg_spectrum(args.navg)
    noise_spectra[ch] = mag
    rms = np.sqrt(np.mean(mag ** 2))
    print(f"  Ch {ch}: RMS={rms:.0f}")

n_freq_bins = len(freq_axis)

# ── Step 2: Sweep drive frequencies ──
print(f"\n=== Sweeping DDS#{args.dds} ===")

# Storage: [n_drives × n_channels × n_freq_bins]
all_spectra = np.zeros((len(drive_freqs), len(mux_channels), n_freq_bins))
all_ratios = np.zeros((len(drive_freqs), len(mux_channels), n_freq_bins))

t0 = time.time()
for di, df in enumerate(drive_freqs):
    dds_cmd(f'F{args.dds}:{df}')
    time.sleep(0.3)

    for ci, ch in enumerate(mux_channels):
        mux.write(f'{ch}\n'.encode())
        time.sleep(0.15)
        mux.readline()
        time.sleep(0.1)

        _, mag = coherent_avg_spectrum(args.navg)
        all_spectra[di, ci, :] = mag
        noise = noise_spectra[ch]
        ratio = np.where(noise > 10, mag / noise, 1.0)
        all_ratios[di, ci, :] = ratio

    # Find top eigenmodes for this drive freq (across all channels)
    max_ratio_per_bin = np.max(all_ratios[di], axis=0)
    top_bins = np.argsort(max_ratio_per_bin)[-5:][::-1]

    elapsed = time.time() - t0
    rate = (di + 1) / elapsed
    eta = (len(drive_freqs) - di - 1) / rate

    top_str = ", ".join(f"{freq_axis[b]:.0f}Hz({max_ratio_per_bin[b]:.0f}×)"
                        for b in top_bins if max_ratio_per_bin[b] > 2.0)
    print(f"  {df:>7} Hz: {top_str}  [{di+1}/{len(drive_freqs)}, "
          f"ETA {eta:.0f}s]")

dds_cmd('Foff')

# ── Step 3: Analysis ──
print(f"\n{'='*60}")
print("EIGENMODE EXCITATION MATRIX")
print(f"{'='*60}")

# Find global eigenmodes: bins that show high ratio for ANY drive frequency
global_max = np.max(all_ratios, axis=(0, 1))  # max across drives and channels
min_sep = 500  # Hz between distinct modes
candidates = np.where((global_max > 5.0) & (freq_axis > 500))[0]
candidates = candidates[np.argsort(global_max[candidates])[::-1]]

eigenmodes = []
for idx in candidates:
    f = freq_axis[idx]
    if not any(abs(freq_axis[s] - f) < min_sep for s in eigenmodes):
        eigenmodes.append(idx)
    if len(eigenmodes) >= 20:
        break

print(f"\nTop {len(eigenmodes)} eigenmodes (across all drives):")
print(f"  {'Mode':>5} {'Freq (Hz)':>12} {'Best ratio':>12} {'Best drive':>12} {'Best ch':>8}")
print(f"  {'-'*52}")
for rank, idx in enumerate(eigenmodes):
    # Find which drive freq and channel gave the max ratio at this mode
    best_di, best_ci = np.unravel_index(
        np.argmax(all_ratios[:, :, idx]), (len(drive_freqs), len(mux_channels)))
    print(f"  {rank+1:>5} {freq_axis[idx]:>12.0f} {all_ratios[best_di, best_ci, idx]:>12.1f}× "
          f"{drive_freqs[best_di]:>12} {mux_channels[best_ci]:>8}")

# Drive frequency diversity: how many distinct eigenmodes does each drive excite?
print(f"\n{'='*60}")
print("DRIVE FREQUENCY EFFECTIVENESS")
print(f"{'='*60}")
print(f"  {'Drive (Hz)':>12} {'Modes>5×':>10} {'Modes>20×':>11} {'Best ratio':>12} {'Best mode':>12}")
print(f"  {'-'*60}")

for di, df in enumerate(drive_freqs):
    max_ratio_per_bin = np.max(all_ratios[di], axis=0)
    n_above_5 = 0
    n_above_20 = 0
    counted = []
    for idx in np.argsort(max_ratio_per_bin)[::-1]:
        if max_ratio_per_bin[idx] < 5.0:
            break
        if freq_axis[idx] < 500:
            continue
        if any(abs(freq_axis[idx] - freq_axis[c]) < min_sep for c in counted):
            continue
        counted.append(idx)
        n_above_5 += 1
        if max_ratio_per_bin[idx] > 20.0:
            n_above_20 += 1

    best_idx = np.argmax(max_ratio_per_bin[10:]) + 10  # skip DC bins
    print(f"  {df:>12} {n_above_5:>10} {n_above_20:>11} "
          f"{max_ratio_per_bin[best_idx]:>12.1f}× {freq_axis[best_idx]:>12.0f}")

# Channel diversity: do different mux channels see different modes?
if len(mux_channels) > 1:
    print(f"\n{'='*60}")
    print("SPATIAL DIVERSITY (per mux channel)")
    print(f"{'='*60}")
    for ci, ch in enumerate(mux_channels):
        ch_max = np.max(all_ratios[:, ci, :], axis=0)
        top_idx = np.argsort(ch_max)[-5:][::-1]
        modes_str = ", ".join(f"{freq_axis[b]:.0f}Hz({ch_max[b]:.0f}×)"
                              for b in top_idx if ch_max[b] > 2.0)
        print(f"  Ch {ch}: {modes_str}")

# DDS board comparison hint
if args.dds == 1:
    print(f"\n  TIP: Run again with --dds 2 to compare DDS board excitation patterns")

# ── Save data ──
tag = f"dds{args.dds}_{args.start}_{args.stop}_{args.step}"
out_path = DATA_DIR / f"eigenmode_sweep_{tag}.npz"
np.savez(out_path,
         drive_freqs=np.array(drive_freqs),
         freq_axis=freq_axis,
         mux_channels=np.array(mux_channels),
         all_spectra=all_spectra,
         all_ratios=all_ratios,
         noise_spectra=np.array([noise_spectra[ch] for ch in mux_channels]),
         eigenmodes=np.array(eigenmodes),
         eigenmode_freqs=freq_axis[eigenmodes])
print(f"\nData saved to {out_path}")

# Cleanup
mux.write(b'0\n')
mux.close()
dds.close()
ps.ps2000_set_sig_gen_built_in(handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0)
ps.ps2000_stop(handle)
ps.ps2000_close_unit(handle)
print("Done.")
