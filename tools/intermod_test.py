#!/usr/bin/env python3
"""
2-Tone Intermod Test — clean nonlinearity probe for the A->clip->B cascade.

Drive plate A with two tones f1,f2 (NCO F1,F2 = CH1,CH2). A linear medium
returns ONLY f1,f2. A nonlinearity makes intermod products: 3rd-order
2f1-f2, 2f2-f1 (the diagnostic — they sit near the carriers, can't be a stray
mode), plus f1+f2 and 2f1,2f2. All products kept <166 kHz (preamp BW) and
<390 kHz (Nyquist). Run once clipping (Rg2=1k), once linear (Rg2=10k); compare
IMD3. Rising IMD3 with clip = real cascade nonlinearity.

Usage:
  python tools/intermod_test.py                 # f1=60k f2=66k, navg 16
  python tools/intermod_test.py --f1 62000 --f2 70000
"""
import ctypes as ct, numpy as np, serial, time, argparse

ap = argparse.ArgumentParser()
ap.add_argument('--f1', type=int, default=60000)
ap.add_argument('--f2', type=int, default=66000)
ap.add_argument('--navg', type=int, default=16)
ap.add_argument('--nco-port', default='/dev/cu.usbmodem113401')
a = ap.parse_args()

N=8064; TB=7; FS=781250.0; NFFT=N*4; BIN=FS/NFFT; RNG=6; RNG_MV=1000.0
LIB='/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources/libps2000.dylib'
ps=ct.CDLL(LIB); ps.ps2000_open_unit.restype=ct.c_int16
h=ps.ps2000_open_unit(); assert h>0,'pico open fail'
ps.ps2000_set_channel(h,0,1,0,RNG); ps.ps2000_set_channel(h,1,0,0,RNG)
ps.ps2000_set_trigger(h,5,0,0,0,0)
s=serial.Serial(a.nco_port,115200,timeout=2); time.sleep(0.5); s.reset_input_buffer()
def cmd(c): s.reset_input_buffer(); s.write(f'{c}\n'.encode()); time.sleep(0.03)
def cap(navg):
    buf=(ct.c_int16*N)(); ov=ct.c_int16(); mg=[]
    for _ in range(navg):
        tk=ct.c_int32(); ps.ps2000_run_block(h,N,TB,1,ct.byref(tk))
        for _ in range(500):
            if ps.ps2000_ready(h): break
            time.sleep(0.002)
        ps.ps2000_get_values(h,ct.byref(buf),None,None,None,ct.byref(ov),N)
        d=np.array(buf[:],float)*(RNG_MV/32767.0); d-=d.mean()
        mg.append(np.abs(np.fft.rfft(d*np.hanning(N),n=NFFT)))
    return np.mean(mg,axis=0)
def peak(sp,f,w=5):
    b=int(round(f/BIN)); return float(sp[max(0,b-w):b+w+1].max())

cmd('Foff'); time.sleep(0.1); noise=np.median(cap(a.navg));
cmd(f'F1:{a.f1}'); cmd(f'F2:{a.f2}'); time.sleep(0.1); sp=cap(a.navg)
f1,f2=a.f1,a.f2
pts={'f1':f1,'f2':f2,'2f1-f2':2*f1-f2,'2f2-f1':2*f2-f1,'f1+f2':f1+f2,'2f1':2*f1,'2f2':2*f2}
print(f"\nnoise floor {noise:.0f} | f1={f1/1e3:.1f}k f2={f2/1e3:.1f}k  (all products <166k OK)")
c=(peak(sp,f1)+peak(sp,f2))/2
for k,fp in pts.items():
    m=peak(sp,fp); print(f"  {k:7s} {fp/1e3:6.1f}k  mag {m:7.0f}  SNR {m/noise:5.1f}x  IMDrel {20*np.log10(m/c):6.1f}dB")
imd3=max(peak(sp,2*f1-f2),peak(sp,2*f2-f1))
print(f"\nIMD3 = {20*np.log10(imd3/c):.1f} dBc (linear ~ noise; clip lifts it). carrier {c:.0f}")
cmd('Foff'); s.close(); ps.ps2000_close_unit(h)
