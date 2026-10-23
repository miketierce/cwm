#!/usr/bin/env python3
"""Clipping pre-qualification (2026-10-23): full FT-1 grid, CH1 and CH2 at 10% duty.

Usage (from the repo root): python clip_prequal.py [out.json] [range_code_A] [range_code_B]
Defaults reproduce the first run (clip_prequal_10pct_duty_10V.json: both channels on the
±10V range, code 9). ps2000 range codes: 7 = ±2V, 8 = ±5V, 9 = ±10V.

Writes {channel: [(freq_hz, chA_waveform_peak_mV, chA_fundamental_peak_mV, chB_waveform_peak_mV), ...]}.
"""
import ctypes as ct, numpy as np, time, json, serial, sys
sys.path.insert(0, '.')
from tools.k_eff_ft1_capture import demod, pio_actual_freq

OUT = sys.argv[1] if len(sys.argv) > 1 else 'clip_prequal_10pct_duty_10V.json'
RA = int(sys.argv[2]) if len(sys.argv) > 2 else 9
RB = int(sys.argv[3]) if len(sys.argv) > 3 else 9
MV_OF = {7: 2000.0, 8: 5000.0, 9: 10000.0}
MVA, MVB = MV_OF[RA], MV_OF[RB]
ps = ct.CDLL('/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources/libps2000.dylib')
ps.ps2000_open_unit.restype = ct.c_int16
h = ps.ps2000_open_unit(); N = 3072; FS = 781250.0
ps.ps2000_set_channel(h, 0, 1, 1, RA); ps.ps2000_set_channel(h, 1, 1, 1, RB); ps.ps2000_set_trigger(h, 5, 0, 0, 0, 0)
nco = serial.Serial('/dev/cu.usbmodem113401', 115200, timeout=1); time.sleep(0.5)


def q(c):
    nco.reset_input_buffer(); nco.write((c + '\n').encode()); return nco.readline().decode().strip()


grid = list(range(30000, 120001, 500)); res = {}
try:
    for ch in ('F1', 'F2'):
        q('Foff'); q(f'A{ch[1:]}:100'); rows = []
        for f in grid:
            q(f'{ch}:{f}'); time.sleep(0.04)
            ba = (ct.c_int16 * N)(); bb = (ct.c_int16 * N)(); ov = ct.c_int16(); tk = ct.c_int32()
            ps.ps2000_run_block(h, N, 7, 1, ct.byref(tk))
            while not ps.ps2000_ready(h): time.sleep(0.001)
            ps.ps2000_get_values(h, ct.byref(ba), ct.byref(bb), None, None, ct.byref(ov), N)
            a = np.array(ba[:], float) * MVA / 32767; b = np.array(bb[:], float) * MVB / 32767
            rows.append((f, float(np.abs(a).max()), abs(demod(a, pio_actual_freq(f), FS)), float(np.abs(b).max())))
        q('Foff'); q(f'A{ch[1:]}:500'); res[ch] = rows
finally:
    q('Foff'); nco.close(); ps.ps2000_stop(h); ps.ps2000_close_unit(ct.c_int16(h))
json.dump(res, open(OUT, 'w'))
