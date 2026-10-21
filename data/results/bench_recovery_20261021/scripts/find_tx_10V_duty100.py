#!/usr/bin/env python3
"""Find which NCO channels acoustically drive the plate under the RX.

Common-mode electrical pickup is identical on every channel, so each channel's
Ch A response is divided by the cross-channel median at each frequency; only
channels with plate resonances stand out.
"""
import ctypes as ct, numpy as np, time, json, serial, sys
from pathlib import Path

OUT = Path(__file__).parent / 'find_tx_10V_duty100.json'
ps = ct.CDLL('/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources/libps2000.dylib')
ps.ps2000_open_unit.restype = ct.c_int16
h = ps.ps2000_open_unit(); N = 3072; FS = 781250.0; NFFT = N * 4; BIN = FS / NFFT; MV = 10000.0
nco = serial.Serial('/dev/cu.usbmodem113401', 115200, timeout=2); time.sleep(0.5)
freqs = np.arange(30000, 120001, 250)
chans = sys.argv[1].split(',') if len(sys.argv) > 1 else [f'F{i}' for i in range(1, 16)]
CONTROL = sys.argv[2] if len(sys.argv) > 2 else None


def cmd(c): nco.reset_input_buffer(); nco.write((c + '\n').encode()); time.sleep(0.02)


def amp(f, navg=2):
    out, ovs = [], 0
    for _ in range(navg):
        ba = (ct.c_int16 * N)(); ov = ct.c_int16(); tk = ct.c_int32()
        ps.ps2000_run_block(h, N, 7, 1, ct.byref(tk))
        for _ in range(500):
            if ps.ps2000_ready(h): break
            time.sleep(0.002)
        ps.ps2000_get_values(h, ct.byref(ba), None, None, None, ct.byref(ov), N); ovs |= ov.value
        x = np.array(ba[:], float) * MV / 32767; x -= x.mean()
        sp = np.abs(np.fft.rfft(x * np.hanning(N), n=NFFT)); b = int(round(f / BIN))
        out.append(sp[max(0, b - 6):b + 7].max())
    return float(np.mean(out)), ovs


A = np.zeros((len(chans), len(freqs))); OV = {}
try:
    cmd('Foff'); cmd('A9:100'); cmd('A12:100')
    ps.ps2000_set_channel(h, 0, 1, 0, 9); ps.ps2000_set_channel(h, 1, 0, 0, 9); ps.ps2000_set_trigger(h, 5, 0, 0, 0, 0)
    time.sleep(1.0)
    for i, ch in enumerate(chans):
        ovf = 0
        for k, f in enumerate(freqs):
            cmd(f'{ch}:{int(f)}'); time.sleep(0.015)
            A[i, k], ov = amp(f); ovf |= ov
        cmd('Foff'); OV[ch] = ovf
        print(f'{ch} swept {"(OVF)" if ovf else ""}', flush=True)
finally:
    cmd('Foff'); cmd('A9:500'); cmd('A12:500'); nco.close(); ps.ps2000_stop(h); ps.ps2000_close_unit(ct.c_int16(h))

med = A[chans.index(CONTROL)] if CONTROL else np.median(A, axis=0); R = A / med
full = MV * N / 4
print('\nraw level vs scope full scale (median / max):')
for i, ch in enumerate(chans):
    print(f'  {ch:<4} {np.median(A[i]) / full:.3f} / {A[i].max() / full:.3f}', flush=True)
print('ratio reference:', CONTROL or 'cross-channel median')
res = {}
print('\nchannel  bins>3x  bins>10x  max_ratio  top peaks (kHz: ratio)')
for i, ch in enumerate(chans):
    r = R[i]; idx = [k for k in range(1, len(r) - 1) if r[k] >= r[k - 1] and r[k] >= r[k + 1] and r[k] >= 3]
    top = sorted(idx, key=lambda k: -r[k])[:6]
    res[ch] = {'bins_gt3': int((r > 3).sum()), 'bins_gt10': int((r > 10).sum()), 'max_ratio': round(float(r.max()), 1),
               'peaks': [(float(freqs[k]) / 1000, round(float(r[k]), 1)) for k in sorted(top)], 'overflow': OV.get(ch, 0)}
    pk = ', '.join(f'{f:.2f}:{v}' for f, v in res[ch]['peaks'])
    print(f'{ch:<7}  {res[ch]["bins_gt3"]:6d}  {res[ch]["bins_gt10"]:7d}  {res[ch]["max_ratio"]:8.1f}   {pk}', flush=True)
OUT.write_text(json.dumps({'channels': res, 'freqs': freqs.tolist(), 'A': A.round(2).tolist()}))
print('\nsaved', OUT)
