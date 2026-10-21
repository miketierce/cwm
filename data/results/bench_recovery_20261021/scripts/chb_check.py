#!/usr/bin/env python3
"""Check idle offset, which NCO channels drive the plate (Ch A), and which one Ch B taps."""
import ctypes as ct, numpy as np, time, json, serial
from pathlib import Path

OUT = Path(__file__).parent / 'chb_check_result.json'
ps = ct.CDLL('/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources/libps2000.dylib')
ps.ps2000_open_unit.restype = ct.c_int16
h = ps.ps2000_open_unit(); N = 3072; FS = 781250.0; NFFT = N * 4; BIN = FS / NFFT
RANGE_MV = {6: 1000.0, 8: 5000.0, 9: 10000.0}
nco = serial.Serial('/dev/cu.usbmodem113401', 115200, timeout=2); time.sleep(0.5)
CHANS = ['F1', 'F2', 'F9', 'F12', 'F3']
freqs = np.arange(50000, 110001, 1000)


def cmd(c): nco.reset_input_buffer(); nco.write((c + '\n').encode()); time.sleep(0.03)


def setup(ra, rb, dc):
    ps.ps2000_set_channel(h, 0, 1, dc, ra); ps.ps2000_set_channel(h, 1, 1, dc, rb)
    ps.ps2000_set_trigger(h, 5, 0, 0, 0, 0)
    return RANGE_MV[ra], RANGE_MV[rb]


def grab(mva, mvb):
    ba = (ct.c_int16 * N)(); bb = (ct.c_int16 * N)(); ov = ct.c_int16(); tk = ct.c_int32()
    ps.ps2000_run_block(h, N, 7, 1, ct.byref(tk))
    for _ in range(500):
        if ps.ps2000_ready(h): break
        time.sleep(0.002)
    ps.ps2000_get_values(h, ct.byref(ba), ct.byref(bb), None, None, ct.byref(ov), N)
    return np.array(ba[:], float) * mva / 32767, np.array(bb[:], float) * mvb / 32767, ov.value


def tone_v(x, f):
    x = x - x.mean(); sp = np.abs(np.fft.rfft(x * np.hanning(N), n=NFFT)); b = int(round(f / BIN))
    return float(sp[max(0, b - 6):b + 7].max()) * 4 / N / 1000


res = {}
try:
    cmd('Foff')
    mva, mvb = setup(9, 9, 1); time.sleep(0.3)
    a, b, _ = grab(mva, mvb); res['idle_dc_10V_mV'] = round(float(a.mean()), 1)
    if abs(a.mean()) < 600:
        mva, mvb = setup(6, 9, 1); time.sleep(0.3)
        a, _, ov = grab(mva, mvb); res['idle_dc_1V_mV'] = round(float(a.mean()), 1); res['idle_1V_ovf'] = ov
    print('idle DC Ch A:', res, flush=True)

    mva, mvb = setup(9, 8, 0); time.sleep(1.0)
    for ch in CHANS: cmd(f'A{ch[1:]}:100')
    res['channels'] = {}
    for ch in CHANS:
        A, B, ovf = [], [], 0
        for f in freqs:
            cmd(f'{ch}:{int(f)}'); time.sleep(0.02)
            a, b, ov = grab(mva, mvb); ovf |= ov
            A.append(tone_v(a, f)); B.append(tone_v(b, f))
        cmd('Foff'); A, B = np.array(A), np.array(B)
        res['channels'][ch] = {'chA_median_V': round(float(np.median(A)), 4), 'chA_max_V': round(float(A.max()), 3),
                               'chB_median_V': round(float(np.median(B)), 4), 'chB_max_V': round(float(B.max()), 3),
                               'overflow': ovf, 'chA': [round(float(v), 4) for v in A], 'chB': [round(float(v), 4) for v in B]}
        r = res['channels'][ch]
        print(f'{ch:<4} ChA median {r["chA_median_V"]*1000:7.1f} mV  max {r["chA_max_V"]*1000:7.0f} mV   |   '
              f'ChB median {r["chB_median_V"]*1000:7.1f} mV  max {r["chB_max_V"]*1000:7.0f} mV  {"OVF" if ovf else ""}', flush=True)
finally:
    cmd('Foff')
    for ch in CHANS: cmd(f'A{ch[1:]}:500')
    nco.close(); ps.ps2000_stop(h); ps.ps2000_close_unit(ct.c_int16(h))
    res['freqs'] = freqs.tolist(); OUT.write_text(json.dumps(res)); print('saved', OUT)
