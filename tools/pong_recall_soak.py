#!/usr/bin/env python3
"""
Pong Recall SOAK — future-state-recall autopilot, long-run stability log.

Enrolls the deck once (256 states -> stored LANDING = forward-sim future),
then plays random balls for HOURS: query live glass, recall nearest card,
read its stored future, place paddle. Logs glass vs wire hit-rate + noise
floor every ~30s so we see drift over the run. Reuses pong_predict_recall
encoding exactly (amplitude axes + census mode pool).

Usage:
  python3 tools/pong_recall_soak.py --hours 2 --census data/results/direct_wire_census/direct_wire_census_20260628_220731.json
"""
import ctypes as ct, numpy as np, serial, json, time, math, argparse, sys
from pathlib import Path
from datetime import datetime

ap = argparse.ArgumentParser()
ap.add_argument('--hours', type=float, default=2.0)
ap.add_argument('--cadence', type=float, default=30.0)
ap.add_argument('--repeats', type=int, default=2)
ap.add_argument('--noise', type=float, default=1.0, help='query noise sigma (standardized space); recall should beat wire here')
ap.add_argument('--topk', type=int, default=0, help='glass = top-K Fisher-separating features (0=all 779)')
ap.add_argument('--navg', type=int, default=10)
ap.add_argument('--settle', type=float, default=0.04)
ap.add_argument('--census', default=None)
ap.add_argument('--nco-port', default='/dev/cu.usbmodem113401')
a = ap.parse_args()

N_SAMPLES=8064; TIMEBASE=7; FS=781250.0; NFFT=N_SAMPLES*4; BIN=FS/NFFT; RNG=6; RNG_MV=1000.0
LIB='/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources/libps2000.dylib'
COURT_W, COURT_H, PADDLE_H = 8, 8, 3
WIN=[-8,-4,-2,0,2,4,8]; NW=len(WIN)
AXES=[('x','F4',48000,8),('y','F5',89000,8),('vx','F1',57000,2),('vy','F2',82000,2)]
OUT=Path('data/results/pong'); OUT.mkdir(parents=True, exist_ok=True); TS=datetime.now().strftime('%Y%m%d_%H%M%S')
CSV=OUT/f'recall_soak_{TS}.csv'
dl=lambda n:[round(math.asin((L+1)/n)/math.pi*1000) for L in range(n)]; LVL={nm:dl(nl) for nm,_,_,nl in AXES}

def landing(bx,by,vx,vy):
    x,y=float(bx),float(by)
    for _ in range(40):
        x+=vx; y+=vy
        if y<0:y=-y;vy=-vy
        if y>COURT_H-1:y=2*(COURT_H-1)-y;vy=-vy
        if x<0:x=-x;vx=-vx
        if x>=COURT_W-1:return int(round(np.clip(y,0,COURT_H-1)))
    return (COURT_H-1)//2
states=[(x,y,vx,vy) for x in range(COURT_W) for y in range(COURT_H) for vx in(-1,1) for vy in(-1,1)]
N=len(states); land=np.array([landing(*s) for s in states])
cp=Path(a.census) if a.census else sorted(Path('data/results/direct_wire_census').glob('*.json'))[-1]
cj=json.load(open(cp)); src=cj.get('all_modes') or cj['usable_modes']
freqs=np.array(sorted({float(m.get('freq',m.get('freq_hz'))) for m in src}))
DRIVEN={nm:i*NW+NW//2 for i,(nm,_,_,_) in enumerate(AXES)}; Fd=len(AXES)*NW+len(freqs)
print(f"deck {N} states, {len(freqs)} modes -> {Fd} feats; csv {CSV.name}")

ps=ct.CDLL(LIB); ps.ps2000_open_unit.restype=ct.c_int16; h=ps.ps2000_open_unit(); assert h>0
ps.ps2000_set_channel(h,0,1,0,RNG); ps.ps2000_set_channel(h,1,0,0,RNG); ps.ps2000_set_trigger(h,5,0,0,0,0)
nco=serial.Serial(a.nco_port,115200,timeout=2); time.sleep(0.5); nco.reset_input_buffer()
send=lambda c:(nco.reset_input_buffer(),nco.write(f'{c}\n'.encode()),time.sleep(0.01))
def cap():
    buf=(ct.c_int16*N_SAMPLES)(); ov=ct.c_int16(); mg=[]
    for _ in range(a.navg):
        tk=ct.c_int32(); ps.ps2000_run_block(h,N_SAMPLES,TIMEBASE,1,ct.byref(tk))
        for _ in range(500):
            if ps.ps2000_ready(h):break
            time.sleep(0.002)
        ps.ps2000_get_values(h,ct.byref(buf),None,None,None,ct.byref(ov),N_SAMPLES)
        d=np.array(buf[:],float)*(RNG_MV/32767.0); d-=d.mean(); mg.append(np.abs(np.fft.rfft(d*np.hanning(N_SAMPLES),n=NFFT)))
    return np.mean(mg,axis=0)
def winv(sp,f):
    o=np.zeros(NW); b=int(round(f/BIN))
    for i,k in enumerate(WIN): bb=b+k; o[i]=float(sp[max(0,bb-1):bb+2].max()) if 0<=bb<len(sp) else 0
    return o
amp=lambda sp,f:float(sp[max(0,int(round(f/BIN))-2):int(round(f/BIN))+3].max())
def feats(s,xx,yy,vx,vy):
    lv={'x':xx,'y':yy,'vx':0 if vx<0 else 1,'vy':0 if vy<0 else 1}
    send('Foff'); time.sleep(0.004)
    for nm,ch,fr,_ in AXES: send(f'{ch}:{fr}'); send(f'A{ch[1]}:{LVL[nm][lv[nm]]}')
    time.sleep(a.settle); sp=cap()
    return np.concatenate([winv(sp,AXES[0][2]),winv(sp,AXES[1][2]),winv(sp,AXES[2][2]),winv(sp,AXES[3][2]),[amp(sp,f) for f in freqs]]), sp

# enroll deck
print("enrolling..."); t0=time.time(); deck=np.zeros((N*a.repeats,Fd)); dland=np.zeros(N*a.repeats,int); row=0
for gi,s in enumerate(states):
    for r in range(a.repeats):
        f,_=feats(s,*s); deck[row]=f; dland[row]=land[gi]; row+=1
    if (gi+1)%64==0: print(f"  {gi+1}/{N}")
deck=deck/(deck.mean(1,keepdims=True)+1e-9); mu=deck.mean(0); sd=deck.std(0); sd[sd<1e-9]=1; A=(deck-mu)/sd
wire=np.array(sorted(DRIVEN.values()))
if a.topk and a.topk<Fd:
    cls=np.unique(dland); gm=A.mean(0); bw=np.zeros(Fd); wi=np.zeros(Fd)
    for c in cls:
        v=A[dland==c]; bw+=len(v)*(v.mean(0)-gm)**2; wi+=((v-v.mean(0))**2).sum(0)
    gcols=np.argsort(-(bw/(wi+1e-9)))[:a.topk]
else: gcols=np.arange(Fd)
print(f"glass feats={len(gcols)} (topk={a.topk}), wire feats={len(wire)}")
print(f"enroll {time.time()-t0:.0f}s; soak {a.hours}h -> {CSV}")
CSV.write_text("t_min,balls,glass_hit,wire_hit,noise_sigma,nf\n")
rng=np.random.default_rng(); end=time.time()+a.hours*3600; ng=nw=tot=0; ck=time.time()
print(f"query noise sigma={a.noise}")
while time.time()<end:
    s=states[rng.integers(N)]; f,sp=feats(s,*s); q=(f/(f.mean()+1e-9)-mu)/sd
    q=q+rng.standard_normal(Fd)*a.noise
    qg=q[gcols]; nn=np.argsort(((A[:,gcols]-qg)**2).sum(1))[0]; gp=dland[nn]
    qw=q[wire]; nw_=np.argsort(((A[:,wire]-qw)**2).sum(1))[0]; wp=dland[nw_]
    tru=land[states.index(s)]; ng+=abs(gp-tru)<=PADDLE_H//2; nw+=abs(wp-tru)<=PADDLE_H//2; tot+=1
    if time.time()-ck>=a.cadence:
        nf=np.median(sp); print(f"{(time.time()-end+a.hours*3600)/60:.0f}m balls={tot} glass={ng/tot*100:.0f}% wire={nw/tot*100:.0f}% nf={nf:.0f}")
        open(CSV,'a').write(f"{(a.hours*3600-(end-time.time()))/60:.1f},{tot},{ng/tot*100:.1f},{nw/tot*100:.1f},{a.noise},{nf:.0f}\n"); ck=time.time()
send('Foff'); nco.close(); ps.ps2000_stop(h); ps.ps2000_close_unit(ct.c_int16(h)); print("done")
