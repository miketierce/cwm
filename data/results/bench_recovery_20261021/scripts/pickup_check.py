#!/usr/bin/env python3
"""Quick Ch A pickup check: idle DC, then Vpp with CH1/CH10/CH11 driven at 50/120/250 kHz."""
import ctypes as ct, numpy as np, time, serial

ps = ct.CDLL('/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources/libps2000.dylib')
ps.ps2000_open_unit.restype = ct.c_int16
h = ps.ps2000_open_unit(); N = 3072
nco = serial.Serial('/dev/cu.usbmodem113401', 115200, timeout=2); time.sleep(0.5)


def cmd(c): nco.reset_input_buffer(); nco.write((c + '\n').encode()); time.sleep(0.05)


def grab(mv=10000):
    ba = (ct.c_int16 * N)(); bb = (ct.c_int16 * N)(); ov = ct.c_int16(); tk = ct.c_int32()
    ps.ps2000_run_block(h, N, 7, 1, ct.byref(tk))
    for _ in range(500):
        if ps.ps2000_ready(h): break
        time.sleep(0.002)
    ps.ps2000_get_values(h, ct.byref(ba), ct.byref(bb), None, None, ct.byref(ov), N)
    return np.array(ba[:], float) * mv / 32767, np.array(bb[:], float) * mv / 32767


try:
    cmd('Foff')
    ps.ps2000_set_channel(h, 0, 1, 1, 9); ps.ps2000_set_channel(h, 1, 1, 1, 9); ps.ps2000_set_trigger(h, 5, 0, 0, 0, 0)
    a, b = grab(); print('idle DC     ChA %5.0f mV     ChB %5.0f mV' % (a.mean(), b.mean()))
    ps.ps2000_set_channel(h, 0, 1, 0, 9); ps.ps2000_set_channel(h, 1, 1, 0, 9); time.sleep(1.0)
    a, b = grab(); print('tones off   ChA %5.0f mVpp   ChB %5.0f mVpp' % (np.ptp(a), np.ptp(b)))
    for ch in ('F1', 'F10', 'F11'):
        for f in (50000, 120000, 250000):
            cmd('Foff'); cmd(f'{ch}:{f}'); time.sleep(0.2)
            r = [grab() for _ in range(3)]
            print('%-3s %3dk    ChA %5.0f mVpp   ChB %5.0f mVpp' % (
                ch, f // 1000, np.median([np.ptp(x[0]) for x in r]), np.median([np.ptp(x[1]) for x in r])))
finally:
    cmd('Foff'); nco.close(); ps.ps2000_stop(h); ps.ps2000_close_unit(ct.c_int16(h))
