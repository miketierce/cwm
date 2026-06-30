#!/usr/bin/env python3
"""
Scope probe on PicoScope Ch B — is the node a SQUARE (clipping) or SINE (linear)?
Move Ch B clip to U1 OUT B (pin 7); ground clip to AGND. Drive one tone on plate A.
Square wave => strong 3f/5f harmonics + large Vpp = comparator engaged.
Usage: python3 tools/scope_probe.py --drive F1 --freq 60000
"""
import ctypes as ct, numpy as np, serial, time, argparse
ap=argparse.ArgumentParser()
ap.add_argument('--drive',default='F1'); ap.add_argument('--freq',type=int,default=60000)
ap.add_argument('--navg',type=int,default=8); ap.add_argument('--nco-port',default='/dev/cu.usbmodem113401')
ap.add_argument('--range',type=int,default=8,help='ps2000 range enum: 7=±2V 8=±10V 9=±20V')
a=ap.parse_args()
N=8064;TB=7;FS=781250.0;NFFT=N*4;BIN=FS/NFFT
RMV={7:2000.0,8:10000.0,9:20000.0}[a.range]
LIB='/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources/libps2000.dylib'
ps=ct.CDLL(LIB);ps.ps2000_open_unit.restype=ct.c_int16;h=ps.ps2000_open_unit();assert h>0
ps.ps2000_set_channel(h,0,0,0,a.range)               # Ch A off
ps.ps2000_set_channel(h,1,1,0,a.range)               # Ch B ON, AC-coupled (strip DC/ground offset), big range
ps.ps2000_set_trigger(h,5,0,0,0,0)
s=serial.Serial(a.nco_port,115200,timeout=2);time.sleep(0.5);s.reset_input_buffer()
snd=lambda c:(s.reset_input_buffer(),s.write(f'{c}\n'.encode()),time.sleep(0.02))
snd('Foff');time.sleep(0.1);snd(f'{a.drive}:{a.freq}');time.sleep(0.15)
buf=(ct.c_int16*N)();ov=ct.c_int16();specs=[];wav=None
for _ in range(a.navg):
    tk=ct.c_int32();ps.ps2000_run_block(h,N,TB,1,ct.byref(tk))
    for _ in range(500):
        if ps.ps2000_ready(h):break
        time.sleep(0.002)
    ps.ps2000_get_values(h,None,ct.byref(buf),None,None,ct.byref(ov),N)
    d=np.array(buf[:],float)*(RMV/32767.0)
    if wav is None: wav=d.copy()
    dd=d-d.mean(); specs.append(np.abs(np.fft.rfft(dd*np.hanning(N),n=NFFT)))
sp=np.mean(specs,axis=0)
snd('Foff'); s.close(); ps.ps2000_close_unit(ct.c_int16(h))
def amp(f):
    b=int(round(f/BIN)); return float(sp[max(0,b-3):b+4].max())
f0=a.freq; vpp=(wav.max()-wav.min())/1e3; dc=wav.mean()/1e3   # mV->V
h1=amp(f0); h3=amp(3*f0); h5=amp(5*f0); h2=amp(2*f0)
dbc=lambda x:20*np.log10(x/h1) if h1>1e-6 else float('nan')
print(f"\nCh B @ {f0/1e3:.0f} kHz (range ±{RMV/1e3:.0f} V)")
print(f"  Vpp={vpp:.2f} V   DC offset={dc:+.2f} V")
print(f"  H1(f)   {h1:8.0f}")
print(f"  H2(2f)  {h2:8.0f}  ({dbc(h2):+.0f} dBc)")
print(f"  H3(3f)  {h3:8.0f}  ({dbc(h3):+.0f} dBc)")
print(f"  H5(5f)  {h5:8.0f}  ({dbc(h5):+.0f} dBc)")
sq = h3/h1 if h1>1e-6 else 0.0
if abs(dc)>3 and vpp<1:
    print(f"\n  => LATCHED at a rail (DC {dc:+.1f} V, no swing): hysteresis too wide — apply the R_b2 fix ✗")
elif vpp>4 and sq>0.1:
    print(f"\n  => SQUARE-ish (3f={sq*100:.0f}% of f, Vpp>4V): COMPARATOR ENGAGED ✓")
elif abs(dc)>3 and vpp<1:
    print(f"\n  => LATCHED at a rail (DC {dc:+.1f} V, no swing): hysteresis too wide / not toggling ✗")
else:
    print(f"\n  => SINE-ish / small (Vpp {vpp:.2f} V, 3f {sq*100:.0f}%): NOT clipping (still linear) ✗")
