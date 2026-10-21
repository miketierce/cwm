#!/usr/bin/env python3
"""Post-rebuild diagnostic for the single-slide rig (preamp -> Ch A, Board D tap -> Ch B)."""
import ctypes as ct, numpy as np, time, json, sys
from pathlib import Path
import serial

OUT = Path(__file__).parent / 'slide_diag_result.json'
LIB = '/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources/libps2000.dylib'
N, TB, FS = 3072, 7, 781250.0
NFFT = N * 4; BIN = FS / NFFT
RANGE_MV = {6: 1000.0, 8: 5000.0, 9: 10000.0}

ps = ct.CDLL(LIB); ps.ps2000_open_unit.restype = ct.c_int16
h = ps.ps2000_open_unit()
if h <= 0: sys.exit(f'PicoScope open failed ({h})')
nco = serial.Serial('/dev/cu.usbmodem113401', 115200, timeout=2); time.sleep(0.5)


def cmd(c): nco.reset_input_buffer(); nco.write(f'{c}\n'.encode()); time.sleep(0.03)


def setup(ra, rb, dc):
    ps.ps2000_set_channel(h, 0, 1, dc, ra); ps.ps2000_set_channel(h, 1, 1, dc, rb)
    ps.ps2000_set_trigger(h, 5, 0, 0, 0, 0)
    return RANGE_MV[ra], RANGE_MV[rb]


def raw(mva, mvb):
    ba = (ct.c_int16 * N)(); bb = (ct.c_int16 * N)(); ov = ct.c_int16(); tk = ct.c_int32()
    ps.ps2000_run_block(h, N, TB, 1, ct.byref(tk))
    for _ in range(500):
        if ps.ps2000_ready(h): break
        time.sleep(0.002)
    ps.ps2000_get_values(h, ct.byref(ba), ct.byref(bb), None, None, ct.byref(ov), N)
    return np.array(ba[:], float) * mva / 32767, np.array(bb[:], float) * mvb / 32767, ov.value


def spec(navg, mva, mvb):
    A, B, ovs = [], [], 0
    for _ in range(navg):
        a, b, ov = raw(mva, mvb); ovs |= ov
        for x, L in ((a, A), (b, B)):
            x = x - x.mean(); L.append(np.abs(np.fft.rfft(x * np.hanning(N), n=NFFT)))
    return np.mean(A, 0), np.mean(B, 0), ovs


def pk(sp, f, s=6):
    b = int(round(f / BIN)); return float(sp[max(0, b - s):b + s + 1].max())


res = {}
try:
    cmd('Foff'); time.sleep(0.1)
    # Stage 0: DC idle levels
    mva, mvb = setup(9, 9, 1)
    a, b, _ = raw(mva, mvb)
    res['idle_dc_mV'] = {'chA_mean': round(float(a.mean()), 1), 'chA_pp': round(float(np.ptp(a)), 1),
                         'chB_mean': round(float(b.mean()), 1), 'chB_pp': round(float(np.ptp(b)), 1)}
    print('Stage 0 idle DC (mV):', res['idle_dc_mV'], flush=True)
    if abs(a.mean()) > 3000:
        print('Preamp output near a rail -> stopping'); raise SystemExit

    # AC-coupled spectra from here on
    mva, mvb = setup(6, 8, 0)
    nA, nB, _ = spec(6, mva, mvb); fA, fB = np.median(nA), np.median(nB)
    res['noise_floor'] = {'chA': round(float(fA), 2), 'chB': round(float(fB), 2)}

    # Stage 1: which channels are wired to anything
    print('\nStage 1 channel map (x noise floor):', flush=True)
    probe = [60000, 150000, 230000]; stage1 = {}
    for i in range(1, 16):
        ra, rb, ovf = [], [], 0
        for f in probe:
            cmd('Foff'); cmd(f'F{i}:{f}'); time.sleep(0.05)
            sA, sB, ov = spec(3, mva, mvb); ovf |= ov
            ra.append(pk(sA, f) / fA); rb.append(pk(sB, f) / fB)
        cmd('Foff')
        stage1[f'F{i}'] = {'chA_max': round(max(ra), 1), 'chB_max': round(max(rb), 1), 'overflow': ovf}
        print(f'  F{i:<3} ChA {max(ra):7.1f}x   ChB {max(rb):7.1f}x  {"OVF" if ovf else ""}', flush=True)
    res['stage1'] = stage1

    live = sorted(stage1, key=lambda c: -(stage1[c]['chA_max'] + stage1[c]['chB_max']))
    live = [c for c in live if stage1[c]['chA_max'] >= 3 or stage1[c]['chB_max'] >= 5][:4]
    print('\nlive channels:', live or 'none', flush=True)

    # Stage 2: fine sweep of live channels through the RX
    freqs = np.arange(30000, 330001, 500); res['stage2'] = {}
    for ch in live:
        a = np.zeros(len(freqs)); b = np.zeros(len(freqs)); ovf = 0
        for k, f in enumerate(freqs):
            cmd(f'{ch}:{int(f)}'); time.sleep(0.02)
            sA, sB, ov = spec(3, mva, mvb); ovf |= ov
            a[k] = pk(sA, f) / fA; b[k] = pk(sB, f) / fB
        cmd('Foff')
        idx = [j for j in range(1, len(a) - 1) if a[j] >= a[j - 1] and a[j] >= a[j + 1] and a[j] >= 5]
        top = sorted(idx, key=lambda j: -a[j])[:8]
        res['stage2'][ch] = {'chA_peaks': [(int(freqs[j]), round(float(a[j]), 1)) for j in sorted(top)],
                             'chA_median': round(float(np.median(a)), 1),
                             'chB_median': round(float(np.median(b)), 1), 'overflow': ovf,
                             'chA_curve': [round(float(v), 2) for v in a]}
        print(f'\n{ch}: ChB median {np.median(b):.1f}x  ChA median {np.median(a):.1f}x  {"OVF" if ovf else ""}', flush=True)
        for j in sorted(top): print(f'   peak {freqs[j]/1000:6.1f} kHz  {a[j]:7.1f}x', flush=True)
finally:
    cmd('Foff'); nco.close(); ps.ps2000_stop(h); ps.ps2000_close_unit(ct.c_int16(h))
    OUT.write_text(json.dumps(res, indent=1)); print('\nsaved', OUT)
