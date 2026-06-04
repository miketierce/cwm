#!/usr/bin/env python3
"""Quick DDS#2 diagnostic — deeper test with more averages."""
import os, ctypes as ct, numpy as np, time, serial, sys

os.environ['DYLD_LIBRARY_PATH'] = (
    '/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources'
)
from picosdk.ps2000 import ps2000 as ps

DDS_PORT = "/dev/cu.usbserial-1120"
MUX_PORT = "/dev/cu.usbserial-11310"
N_AVG = 10
FREQ_TEST = 97011  # Best DDS#1 result

# Open hardware
print("Opening DDS...", flush=True)
dds = serial.Serial(DDS_PORT, 115200, timeout=2)
time.sleep(2.5)
dds.reset_input_buffer()
dds.write(b'D?\n')
time.sleep(0.05)
print(f"  DDS: {dds.readline().decode().strip()}", flush=True)

print("Opening PicoScope...", flush=True)
h = ps.ps2000_open_unit()
if h <= 0:
    print(f"  ERROR: PicoScope open failed (handle={h}). Trying close/reopen...", flush=True)
    ps.ps2000_close_unit(1)  # force close handle 1
    time.sleep(1)
    h = ps.ps2000_open_unit()
    if h <= 0:
        print(f"  FATAL: Still can't open PicoScope (handle={h}). Unplug/replug USB.", flush=True)
        sys.exit(1)
ps.ps2000_set_channel(h, 0, 1, 0, 7)  # ChA, AC, ±5V
ps.ps2000_set_sig_gen_built_in(h, 0, 0, 0, 0, 0, 0, 0, 0, 0)  # AWG off
print(f"  Handle: {h}", flush=True)

print("Opening Mux...", flush=True)
mux = serial.Serial(MUX_PORT, 9600, timeout=1)
time.sleep(2.5)
mux.reset_input_buffer()
mux.write(b'8\n')
time.sleep(0.05)
print(f"  Mux: {mux.readline().decode().strip()}", flush=True)


def capture_snr(freq, n_avg=10):
    """Capture with averaging and return (peak_mag, noise, snr, peak_freq)."""
    spectra = []
    for i in range(n_avg):
        buf = (ct.c_int16 * 8064)()
        ov = ct.c_int16(0)
        ps.ps2000_set_trigger(h, 0, 0, 0, 0, 100)
        ps.ps2000_run_block(h, 8064, 7, 1, ct.byref(ct.c_int32()))
        time.sleep(0.02)
        ready = False
        for _w in range(200):
            if ps.ps2000_ready(h):
                ready = True
                break
            time.sleep(0.01)
        if not ready:
            print(f"    WARNING: capture {i} timeout", flush=True)
            continue
        ps.ps2000_get_values(h, ct.byref(buf), None, None, None,
                             ct.byref(ov), 8064, 0)
        data = np.array(buf[:], dtype=float)
        data -= data.mean()
        if data.std() < 1:
            continue  # skip empty captures
        spectra.append(np.abs(np.fft.rfft(data * np.hanning(8064))))
    if not spectra:
        return 0, 1, 0, freq  # no valid captures
    spec = np.mean(spectra, axis=0)
    freqs = np.fft.rfftfreq(8064, d=1.28e-6)
    tbin = np.argmin(np.abs(freqs - freq))
    lo = max(1, tbin - 5)
    hi = min(len(spec) - 1, tbin + 5)
    pk = lo + np.argmax(spec[lo:hi + 1])
    mask = np.ones(len(spec), bool)
    mask[max(0, tbin - 20):min(len(spec), tbin + 20)] = False
    mask[0] = False
    noise = np.median(spec[mask])
    snr = spec[pk] / noise if noise > 0 else 0
    return spec[pk], noise, snr, freqs[pk]


print(f"\n--- Testing at {FREQ_TEST} Hz, {N_AVG} averages ---\n", flush=True)

# Test DDS#1 alone
dds.write(b'Foff\n')
time.sleep(0.1)
dds.readline()
time.sleep(0.3)

dds.write(f'F1:{FREQ_TEST}\n'.encode())
time.sleep(0.05)
resp = dds.readline().decode().strip()
print(f"Sent F1:{FREQ_TEST} → {resp}", flush=True)
time.sleep(0.5)
mag, noise, snr, fpk = capture_snr(FREQ_TEST, N_AVG)
print(f"DDS#1 alone: mag={mag:.0f}  noise={noise:.0f}  SNR={snr:.1f}×  peak@{fpk:.0f}Hz", flush=True)
dds.write(b'F1:off\n')
time.sleep(0.05)
dds.readline()
time.sleep(0.3)

# Test DDS#2 alone
dds.write(f'F2:{FREQ_TEST}\n'.encode())
time.sleep(0.05)
resp = dds.readline().decode().strip()
print(f"Sent F2:{FREQ_TEST} → {resp}", flush=True)
time.sleep(0.5)
mag, noise, snr, fpk = capture_snr(FREQ_TEST, N_AVG)
print(f"DDS#2 alone: mag={mag:.0f}  noise={noise:.0f}  SNR={snr:.1f}×  peak@{fpk:.0f}Hz", flush=True)
dds.write(b'F2:off\n')
time.sleep(0.05)
dds.readline()
time.sleep(0.3)

# Test BOTH simultaneously at different frequencies
print(f"\n--- Both DDS on: F1=97011, F2=54920 ---\n", flush=True)
dds.write(b'F1:97011\n')
time.sleep(0.05)
dds.readline()
dds.write(b'F2:54920\n')
time.sleep(0.05)
dds.readline()
time.sleep(0.5)

mag97, noise, snr97, fp97 = capture_snr(97011, N_AVG)
mag55, _, snr55, fp55 = capture_snr(54920, N_AVG)
print(f"97 kHz (DDS#1): SNR={snr97:.1f}×  mag={mag97:.0f}  peak@{fp97:.0f}", flush=True)
print(f"55 kHz (DDS#2): SNR={snr55:.1f}×  mag={mag55:.0f}  peak@{fp55:.0f}", flush=True)

# Diagnostic: Try DDS#3 (FSYNC D8) at 97011 — rules out SPI bus issue
print(f"\n--- DDS#3 (FSYNC D8) at 97011 Hz ---\n", flush=True)
dds.write(b'Foff\n')
time.sleep(0.1)
dds.readline()
dds.write(b'F3:97011\n')
time.sleep(0.05)
resp = dds.readline().decode().strip()
print(f"Sent F3:97011 → {resp}", flush=True)
time.sleep(0.5)
mag, noise, snr, fpk = capture_snr(97011, N_AVG)
print(f"DDS#3 alone: mag={mag:.0f}  noise={noise:.0f}  SNR={snr:.1f}×  peak@{fpk:.0f}Hz", flush=True)

# Cleanup
dds.write(b'Foff\n')
time.sleep(0.05)
dds.readline()
dds.close()
mux.close()
ps.ps2000_stop(h)
ps.ps2000_close_unit(h)

print("\n--- DIAGNOSIS ---", flush=True)
print("If DDS#1 has SNR>3 but DDS#2 has SNR<2:", flush=True)
print("  → Check: resistor at e34 making contact? (DDS2 OUT strip is a34-e34)", flush=True)
print("  → Check: FSYNC wire from a32 reaching Arduino D9?", flush=True)
print("  → Check: AGND jumper a33 → GND rail secure?", flush=True)
print("If DDS#3 also fails → shared SPI bus issue", flush=True)
print("Done.", flush=True)
