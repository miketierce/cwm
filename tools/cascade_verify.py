#!/usr/bin/env python3
"""
CASCADE ARRAY VERIFY — check every channel + the cascade + Block-B phase lock
=============================================================================
Rig (June 28 build):  Ch A = ALL RX summed -> x11 preamp.  Ch B = bundled NCO
TX tones (drive reference). So per channel we can tell DRIVE (Ch B sees the tone)
apart from COUPLING (Ch A sees a plate resonance):
    Ch B tone, Ch A peak  -> OK (drives + couples)
    Ch B tone, Ch A flat  -> wired but plate not responding (dead PZT/bond/band)
    no Ch B tone          -> NCO not outputting that channel (firmware/pin)

Array under test:
  Plate A 100mm = Block A CH1-4 (input encode) -> 3 RX -> amp -> Plate B
  Plate B 100mm = 3 cascade TX + CH13 (4th, keep OFF here) -> RX -> Ch A
  Plate C 100mm = Block B CH5-8 (4 phase-locked) -> RX -> Ch A
  Plate D 25x25 = CH9,10 ; E 25x76 = CH11,12 ; F 25x76 = CH13,14 ; G 25x76 = CH15
  (A's own RX go to the amp, NOT Ch A: so CH1-4 show on Ch A only via the cascade.)

Usage:
  python3 tools/cascade_verify.py                 # full check
  python3 tools/cascade_verify.py --quick         # 1 kHz step
  python3 tools/cascade_verify.py --only F5,F6    # subset
"""
import ctypes as ct, numpy as np, time, argparse, json
from datetime import datetime
from pathlib import Path
import serial

ap = argparse.ArgumentParser()
ap.add_argument('--nco-port', default='/dev/cu.usbmodem113401')
ap.add_argument('--step', type=int, default=500)
ap.add_argument('--quick', action='store_true', help='1 kHz step (faster)')
ap.add_argument('--navg', type=int, default=6)
ap.add_argument('--settle', type=float, default=0.05)
ap.add_argument('--only', default='', help='comma channels e.g. F5,F6')
ap.add_argument('--no-phase', action='store_true', help='skip Block-B phase test')
args = ap.parse_args()
if args.quick: args.step = 1000

# expected band per channel (lo,hi Hz) + label; large=40-100k, small mid/high
LARGE = (40000, 100000)
EXPECT = {f'F{i}': (LARGE, 'Plate A (via cascade -> B)') for i in range(1, 5)}
EXPECT.update({f'F{i}': (LARGE, 'Plate C 4-TX') for i in range(5, 9)})
EXPECT.update({'F9': ((230000, 330000), 'Plate D 25x25'), 'F10': ((230000, 330000), 'Plate D 25x25'),
               'F11': ((100000, 255000), 'Plate E 25x76'), 'F12': ((100000, 255000), 'Plate E 25x76'),
               'F13': ((40000, 255000), 'Plate F + B-4th'), 'F14': ((100000, 255000), 'Plate F 25x76'),
               'F15': ((100000, 255000), 'Plate G 25x76')})
CHANS = [c.strip() for c in args.only.split(',')] if args.only else [f'F{i}' for i in range(1, 16)]

LIB = '/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources/libps2000.dylib'
N = 3072; TB = 7; FS = 781250.0; NFFT = N*4; BIN = FS/NFFT; RNG = 6; MV = 1000.0
ps = ct.CDLL(LIB); ps.ps2000_open_unit.restype = ct.c_int16
h = ps.ps2000_open_unit()
if h <= 0: raise SystemExit(f'PicoScope open failed ({h})')
ps.ps2000_set_channel(h, 0, 1, 0, RNG)   # Ch A (RX bus)
ps.ps2000_set_channel(h, 1, 1, 0, RNG)   # Ch B (TX bundle)
ps.ps2000_set_trigger(h, 5, 0, 0, 0, 0)
nco = serial.Serial(args.nco_port, 115200, timeout=2); time.sleep(0.5)
nco.reset_input_buffer(); nco.write(b'STATUS\n'); time.sleep(0.1)
print('NCO:', nco.readline().decode(errors='replace').strip())


def cmd(c): nco.reset_input_buffer(); nco.write(f'{c}\n'.encode()); time.sleep(0.03)
def off(): cmd('Foff'); time.sleep(0.03)


def cap(navg):
    ba = (ct.c_int16*N)(); bb = (ct.c_int16*N)(); ov = ct.c_int16(); A = []; B = []
    for _ in range(navg):
        tk = ct.c_int32(); ps.ps2000_run_block(h, N, TB, 1, ct.byref(tk))
        for _ in range(500):
            if ps.ps2000_ready(h): break
            time.sleep(0.002)
        ps.ps2000_get_values(h, ct.byref(ba), ct.byref(bb), None, None, ct.byref(ov), N)
        for d, L in ((ba, A), (bb, B)):
            x = np.array(d[:], float)*(MV/32767.0); x -= x.mean()
            L.append(np.abs(np.fft.rfft(x*np.hanning(N), n=NFFT)))
    return np.mean(A, 0), np.mean(B, 0)


def pk(sp, f, s=6):
    b = int(round(f/BIN)); return float(sp[max(0, b-s):b+s+1].max())


off(); time.sleep(0.1); nA, nB = cap(args.navg); fA = np.median(nA); fB = np.median(nB)
print(f'noise floor  ChA {fA:.1f}  ChB {fB:.1f}\n')
res = {}
for ch in CHANS:
    (lo, hi), lbl = EXPECT[ch]; fr = list(range(lo, hi+1, args.step)); a = np.zeros(len(fr)); b = np.zeros(len(fr))
    for i, f in enumerate(fr):
        off(); time.sleep(0.006); cmd(f'{ch}:{f}'); time.sleep(args.settle); sA, sB = cap(args.navg)
        a[i] = pk(sA, f)/fA; b[i] = pk(sB, f)/fB
    off(); ia = int(a.argmax()); drive = float(b.max()); rxsnr = float(a[ia])
    v = 'NO DRIVE (NCO/pin)' if drive < 3 else ('OK' if rxsnr >= 3 else 'wired, plate quiet')
    res[ch] = dict(band=lbl, rx_snr=round(rxsnr, 1), f_at=fr[ia], drive=round(drive, 1), verdict=v)
    print(f'  {ch:<4} {lbl:<24} drive {drive:5.1f}x  RX {rxsnr:5.1f}x @ {fr[ia]/1000:5.1f}k  -> {v}')

# Block-B phase lock (plate C): CH5/6 same freq, sweep PH6, expect interference
if not args.no_phase:
    print('\nBlock-B phase lock (plate C, CH5+CH6 @ best C freq):')
    cf = res.get('F5', {}).get('f_at', 66000); off(); cmd(f'F5:{cf}'); cmd(f'F6:{cf}'); e = []
    for d in range(0, 360, 30):
        cmd(f'PH6:{d}'); time.sleep(0.05); sA, _ = cap(8); e.append(pk(sA, cf))
    off(); md = (max(e)-min(e))/max(e)*100 if max(e) else 0
    print(f'  E(phi) modulation {md:.0f}%  -> {"phase lock OK" if md > 20 else "weak/none (check CH5-8 on one plate)"}')

off(); nco.close(); ps.ps2000_stop(h); ps.ps2000_close_unit(ct.c_int16(h))
OUT = Path('data/results/cascade_verify'); OUT.mkdir(parents=True, exist_ok=True)
json.dump(res, open(OUT/f'verify_{datetime.now():%Y%m%d_%H%M%S}.json', 'w'), indent=2)
print('\nKEY: drive<3 = NCO not outputting; RX>=3 = plate couples; cascade = F1-4 RX peak is Plate B.')
