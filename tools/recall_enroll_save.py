#!/usr/bin/env python3
"""
Enroll once, SAVE the raw feature matrix for unlimited offline fair-baseline /
partial-query / decoder analysis (no more bench time). Same encoding as
tools/recall_sweep.py.
"""
import ctypes as ct, numpy as np, serial, json, time, math, argparse
from pathlib import Path
from datetime import datetime
ap=argparse.ArgumentParser()
ap.add_argument('--repeats',type=int,default=5); ap.add_argument('--navg',type=int,default=24)
ap.add_argument('--settle',type=float,default=0.04)
ap.add_argument('--census',default='data/results/direct_wire_census/direct_wire_census_20260628_220731.json')
ap.add_argument('--nco-port',default='/dev/cu.usbmodem113401'); a=ap.parse_args()
N_SAMPLES=8064;TB=7;FS=781250.0;NFFT=N_SAMPLES*4;BIN=FS/NFFT;RNG=6;RMV=1000.0
LIB='/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources/libps2000.dylib'
CW,CHt,PADH=8,8,3; WIN=[-8,-4,-2,0,2,4,8];NW=len(WIN)
AXES=[('x','F4',48000,8),('y','F5',89000,8),('vx','F1',57000,2),('vy','F2',82000,2)]
OUT=Path('data/results/pong');TS=datetime.now().strftime('%Y%m%d_%H%M%S')
dl=lambda n:[round(math.asin((L+1)/n)/math.pi*1000) for L in range(n)];LVL={nm:dl(nl) for nm,_,_,nl in AXES}
def landing(bx,by,vx,vy):
    x,y=float(bx),float(by)
    for _ in range(40):
        x+=vx;y+=vy
        if y<0:y=-y;vy=-vy
        if y>CHt-1:y=2*(CHt-1)-y;vy=-vy
        if x<0:x=-x;vx=-vx
        if x>=CW-1:return int(round(np.clip(y,0,CHt-1)))
    return (CHt-1)//2
states=[(x,y,vx,vy) for x in range(CW) for y in range(CHt) for vx in(-1,1) for vy in(-1,1)];Ns=len(states)
land=np.array([landing(*s) for s in states])
cj=json.load(open(a.census));src=cj.get('all_modes') or cj['usable_modes']
freqs=np.array(sorted({float(m.get('freq',m.get('freq_hz'))) for m in src}))
Fd=len(AXES)*NW+len(freqs); DRIVEN=[i*NW+NW//2 for i in range(len(AXES))]
ps=ct.CDLL(LIB);ps.ps2000_open_unit.restype=ct.c_int16;h=ps.ps2000_open_unit();assert h>0
ps.ps2000_set_channel(h,0,1,0,RNG);ps.ps2000_set_channel(h,1,0,0,RNG);ps.ps2000_set_trigger(h,5,0,0,0,0)
nco=serial.Serial(a.nco_port,115200,timeout=2);time.sleep(0.5);nco.reset_input_buffer()
send=lambda c:(nco.reset_input_buffer(),nco.write(f'{c}\n'.encode()),time.sleep(0.01))
def cap():
    buf=(ct.c_int16*N_SAMPLES)();ov=ct.c_int16();mg=[]
    for _ in range(a.navg):
        tk=ct.c_int32();ps.ps2000_run_block(h,N_SAMPLES,TB,1,ct.byref(tk))
        for _ in range(500):
            if ps.ps2000_ready(h):break
            time.sleep(0.002)
        ps.ps2000_get_values(h,ct.byref(buf),None,None,None,ct.byref(ov),N_SAMPLES)
        d=np.array(buf[:],float)*(RMV/32767.0);d-=d.mean();mg.append(np.abs(np.fft.rfft(d*np.hanning(N_SAMPLES),n=NFFT)))
    return np.mean(mg,axis=0)
def winv(sp,f):
    o=np.zeros(NW);b=int(round(f/BIN))
    for i,k in enumerate(WIN):bb=b+k;o[i]=float(sp[max(0,bb-1):bb+2].max()) if 0<=bb<len(sp) else 0
    return o
amp=lambda sp,f:float(sp[max(0,int(round(f/BIN))-2):int(round(f/BIN))+3].max())
print(f"enroll {Ns}x{a.repeats} navg{a.navg} -> {Fd} feats");t0=time.time()
X=np.zeros((Ns*a.repeats,Fd));L=np.zeros(Ns*a.repeats,int);GI=np.zeros(Ns*a.repeats,int)
XS=np.zeros(Ns*a.repeats,int);YS=np.zeros(Ns*a.repeats,int);VX=np.zeros(Ns*a.repeats,int);VY=np.zeros(Ns*a.repeats,int);r=0
for gi,(x,y,vx,vy) in enumerate(states):
    lv={'x':x,'y':y,'vx':0 if vx<0 else 1,'vy':0 if vy<0 else 1}
    for _ in range(a.repeats):
        send('Foff');time.sleep(0.004)
        for nm,ch,fr,_ in AXES:send(f'{ch}:{fr}');send(f'A{ch[1]}:{LVL[nm][lv[nm]]}')
        time.sleep(a.settle);sp=cap()
        X[r]=np.concatenate([winv(sp,AXES[0][2]),winv(sp,AXES[1][2]),winv(sp,AXES[2][2]),winv(sp,AXES[3][2]),[amp(sp,f) for f in freqs]])
        L[r]=land[gi];GI[r]=gi;XS[r]=x;YS[r]=y;VX[r]=vx;VY[r]=vy;r+=1
    if (gi+1)%64==0:print(f"  {gi+1}/{Ns} {time.time()-t0:.0f}s")
send('Foff');nco.close();ps.ps2000_stop(h);ps.ps2000_close_unit(ct.c_int16(h))
out=OUT/f'recall_enroll_{TS}.npz'
np.savez_compressed(out,X=X,L=L,GI=GI,xs=XS,ys=YS,vx=VX,vy=VY,land=land,
    freqs=freqs,driven=np.array(DRIVEN),nw=NW,naxes=len(AXES),repeats=a.repeats,navg=a.navg,padh=PADH)
print(f"saved {out}  X{X.shape}  {time.time()-t0:.0f}s")
