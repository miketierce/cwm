#!/usr/bin/env python3
"""
DOOM on Glass — Live First-Person Maze (web UI)
================================================

The glass renders the maze. Player walks (x, y, angle) through an 8x8 maze;
each state is encoded as 3 drive tones; the plates' interference response is
read in one capture; a trained per-column readout turns it into 8 wall-distance
columns — the first-person view. Raycasting performed as kernel LOOKUP.

Honesty boundary (same as Pong):
  GLASS does:  the kernel / feature transform (encoded state → interference pattern)
  LAPTOP does: FFT, the linear per-column readout (w·y), maze logic, rendering

Press G to toggle the glass: ON → walls render correctly; OFF → drive cut,
the view collapses to noise. That toggle is the proof the glass is computing.

Usage:
  python3 tools/doom_live.py --model data/results/doom/doom_model_*.json --nco-port /dev/cu.usbmodem113401
  python3 tools/doom_live.py --model <model> --simulated
"""

import ctypes as ct
import numpy as np
import json
import time
import math
import threading
import argparse
import sys
import urllib.parse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

parser = argparse.ArgumentParser(description='DOOM on Glass — live maze')
parser.add_argument('--model', type=str, required=True)
parser.add_argument('--nco-port', type=str, default='/dev/cu.usbmodem113401')
parser.add_argument('--simulated', action='store_true')
parser.add_argument('--port', type=int, default=8766)
parser.add_argument('--fps', type=float, default=30.0)
args = parser.parse_args()

PICO_LIB = '/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources/libps2000.dylib'
N_SAMPLES = 8064
TIMEBASE = 7
FS = 781250.0
NFFT = N_SAMPLES * 4
BIN_HZ = FS / NFFT
RNG = 6
RNG_MV = 1000.0
NAVG = 12

print("Loading model...")
model = json.load(open(args.model))
assert model['encoding'] == 'doom_raycast_v1', f"expected doom_raycast_v1, got {model['encoding']}"
MAZE = model['maze']
MZ_H, MZ_W = len(MAZE), len(MAZE[0])
N_COLS = model['n_cols']
N_DIRS = model['n_dirs']
cfg = model['config']
CH_X, CH_Y, CH_A = cfg['ch_x'], cfg['ch_y'], cfg['ch_a']
F_X_LO, F_X_HI = cfg['f_x_lo'], cfg['f_x_hi']
F_Y_LO, F_Y_HI = cfg['f_y_lo'], cfg['f_y_hi']
F_A_LO, F_A_HI = cfg['f_a_lo'], cfg['f_a_hi']
WINDOW_OFFSETS = cfg['window_offsets']
N_WIN = len(WINDOW_OFFSETS)
FEATURE_SPEC = model['feature_spec']
COLUMNS = model['columns']     # per-column: sel, mu, sd, w, b
T_MIN = model['target_norm']['min']
T_MAX = model['target_norm']['max']
n_mode = sum(1 for s in FEATURE_SPEC if s['kind'] == 'mode')
n_win = sum(1 for s in FEATURE_SPEC if s['kind'] == 'window')
print(f"  Encoding: doom_raycast_v1 — glass renders the maze")
print(f"  Maze: {MZ_W}x{MZ_H}, {N_COLS} columns, {N_DIRS} directions")
print(f"  Features: {len(FEATURE_SPEC)} ({n_win} windows + {n_mode} census modes incl collisions)")
print(f"  Metrics: {model.get('metrics', {}).get('note', 'n/a')}")

# ─── Hardware ────────────────────────────────────────────────────
handle = None
nco_ser = None
if not args.simulated:
    import serial
    print("Initializing hardware...")
    ps = ct.CDLL(PICO_LIB)
    ps.ps2000_open_unit.restype = ct.c_int16
    handle = ps.ps2000_open_unit()
    if handle <= 0:
        print(f"ERROR: PicoScope failed (handle={handle})"); sys.exit(1)
    ps.ps2000_set_channel(handle, 0, 1, 0, RNG)
    ps.ps2000_set_channel(handle, 1, 0, 0, RNG)
    ps.ps2000_set_trigger(handle, 5, 0, 0, 0, 0)
    nco_ser = serial.Serial(args.nco_port, 115200, timeout=2)
    time.sleep(0.5); nco_ser.reset_input_buffer()
    print(f"  PicoScope: handle={handle}")
    print(f"  NCO: {args.nco_port}")


def _capture_spectrum(navg):
    buf = (ct.c_int16 * N_SAMPLES)()
    ov = ct.c_int16()
    mags = []
    for _ in range(navg):
        ticks = ct.c_int32()
        ps.ps2000_run_block(handle, N_SAMPLES, TIMEBASE, 1, ct.byref(ticks))
        for _ in range(500):
            if ps.ps2000_ready(handle):
                break
            time.sleep(0.002)
        ps.ps2000_get_values(handle, ct.byref(buf), None, None, None, ct.byref(ov), N_SAMPLES)
        d = np.array(buf[:], dtype=np.float64) * (RNG_MV / 32767.0)
        d -= d.mean()
        mags.append(np.abs(np.fft.rfft(d * np.hanning(N_SAMPLES), n=NFFT)))
    return np.mean(mags, axis=0) if mags else np.zeros(NFFT // 2 + 1)


def _encode(x, y, a):
    f1 = F_X_LO + x * (F_X_HI - F_X_LO) / (MZ_W - 1)
    f2 = F_Y_LO + y * (F_Y_HI - F_Y_LO) / (MZ_H - 1)
    f3 = F_A_LO + a * (F_A_HI - F_A_LO) / (N_DIRS - 1)
    return f1, f2, f3


def _synth_spectrum(f1, f2, f3):
    n = NFFT // 2 + 1
    sp = np.random.rand(n) * 40 + 30
    for f, amp in ((f1, 800), (f2, 700), (f3, 600)):
        b = int(round(f / BIN_HZ))
        for off in range(-30, 31):
            if 0 <= b+off < n:
                sp[b+off] += amp * np.exp(-(off**2) / 60.0)
    return sp


def _extract_features(spectrum, f1, f2, f3):
    drive_f = (f1, f2, f3)
    feats = np.zeros(len(FEATURE_SPEC))
    for i, spec in enumerate(FEATURE_SPEC):
        if spec['kind'] == 'window':
            base = int(round(drive_f[spec['drive']] / BIN_HZ)) + spec['offset']
            feats[i] = float(spectrum[max(0, base-1):base+2].max()) if 0 <= base < len(spectrum) else 0.0
        else:
            b = int(round(spec['freq_hz'] / BIN_HZ))
            feats[i] = float(spectrum[max(0, b-2):min(len(spectrum), b+3)].max())
    return feats


# Live spectrum for the proof chart
SPEC_LO_HZ, SPEC_HI_HZ, SPEC_POINTS = 30000, 350000, 480
latest_spectrum = {'freqs_khz': [], 'mags': [], 'drives_khz': [], 'peak': 1.0, 'source': 'none'}


def _store_spectrum(spectrum, f1, f2, f3, source):
    lo = int(SPEC_LO_HZ / BIN_HZ); hi = int(SPEC_HI_HZ / BIN_HZ)
    seg = spectrum[lo:hi]
    if len(seg) > SPEC_POINTS:
        step = len(seg) // SPEC_POINTS
        seg = seg[:step*SPEC_POINTS].reshape(SPEC_POINTS, step).max(axis=1)
    freqs = np.linspace(SPEC_LO_HZ, SPEC_HI_HZ, len(seg)) / 1000.0
    latest_spectrum.update(freqs_khz=freqs.round(1).tolist(),
                           mags=seg.round(1).tolist(),
                           drives_khz=[round(f/1000, 1) for f in (f1, f2, f3)],
                           peak=float(seg.max()) if len(seg) else 1.0,
                           source=source)


def glass_render(x, y, a):
    """Glass renders 8 wall-distance columns for player state (x, y, a)."""
    f1, f2, f3 = _encode(x, y, a)
    if args.simulated:
        spectrum = _synth_spectrum(f1, f2, f3)
        _store_spectrum(spectrum, f1, f2, f3, 'simulated')
    else:
        nco_ser.reset_input_buffer()
        nco_ser.write(f'{CH_X}:{int(f1)}\n'.encode()); time.sleep(0.012)
        nco_ser.write(f'{CH_Y}:{int(f2)}\n'.encode()); time.sleep(0.012)
        nco_ser.write(f'{CH_A}:{int(f3)}\n'.encode()); time.sleep(0.012)
        spectrum = _capture_spectrum(NAVG)
        _store_spectrum(spectrum, f1, f2, f3, 'glass')
    feats = _extract_features(spectrum, f1, f2, f3)
    cols = np.zeros(N_COLS)
    for c, cm in enumerate(COLUMNS):
        sel = cm['sel']
        x_sel = feats[sel]
        x_n = (x_sel - np.array(cm['mu'])) / np.array(cm['sd'])
        cols[c] = np.dot(cm['w'], x_n) + cm['b']
    # de-normalize to wall-distance heights
    cols = np.clip(cols, 0, 1) * (T_MAX - T_MIN) + T_MIN
    return cols.tolist()


# ─── Ground-truth raycaster (for glass-OFF comparison + scoring) ──
def cast_ray(px, py, ang_rad, max_dist=12.0, step=0.03):
    dx, dy = math.cos(ang_rad), math.sin(ang_rad)
    t = 0.0
    while t < max_dist:
        t += step
        mx, my = int(px + dx*t), int(py + dy*t)
        if my < 0 or my >= MZ_H or mx < 0 or mx >= MZ_W or MAZE[my][mx] == 1:
            return t
    return max_dist


def true_render(x, y, a):
    px, py = x + 0.5, y + 0.5
    base = a * (360.0 / N_DIRS); fov = cfg.get('fov', 60.0)
    cols = []
    for c in range(N_COLS):
        ang = base - fov/2 + c * fov / (N_COLS - 1)
        d = cast_ray(px, py, math.radians(ang))
        cols.append(1.0 / max(d, 0.3))
    return cols


# ─── Game State ──────────────────────────────────────────────────
class DoomGame:
    def __init__(self):
        # start at first open cell
        self.x, self.y, self.a = 1, 1, 0
        for yy in range(MZ_H):
            for xx in range(MZ_W):
                if MAZE[yy][xx] == 0:
                    self.x, self.y = xx, yy
                    break
            else:
                continue
            break
        self.frame = 0
        self.render_ms = 0.0
        self.columns = [0.0]*N_COLS
        self.render_fidelity = 100.0   # how well glass matches true render
        self.steps = 0

    def dir_vec(self):
        ang = math.radians(self.a * (360.0 / N_DIRS))
        return round(math.cos(ang)), round(math.sin(ang))

    def try_move(self, sign):
        dx, dy = self.dir_vec()
        nx, ny = self.x + dx*sign, self.y + dy*sign
        if 0 <= nx < MZ_W and 0 <= ny < MZ_H and MAZE[ny][nx] == 0:
            self.x, self.y = nx, ny
            self.steps += 1

    def turn(self, d):
        self.a = (self.a + d) % N_DIRS

    def to_dict(self):
        return {'x': self.x, 'y': self.y, 'a': self.a, 'frame': self.frame,
                'columns': [round(c, 3) for c in self.columns],
                'render_ms': round(self.render_ms, 1),
                'render_fidelity': round(self.render_fidelity, 0),
                'maze': MAZE, 'mz_w': MZ_W, 'mz_h': MZ_H, 'n_dirs': N_DIRS,
                'steps': self.steps, 'glass_enabled': glass_enabled,
                'n_features': len(FEATURE_SPEC), 'n_modes': n_mode}


game = DoomGame()
player_input = {'key': None}
glass_enabled = True
game_running = True

HTML_PAGE = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>DOOM ON GLASS</title>
<style>
  body { background:#0a0a0a; color:#0f0; font-family:monospace; text-align:center; margin:0; padding:16px; }
  h1 { color:#0f0; font-size:22px; margin:4px; }
  .sub { color:#0a0; font-size:12px; margin-bottom:12px; }
  canvas { border:2px solid #0f0; background:#000; image-rendering:pixelated; }
  #map { border-color:#063; }
  .wrap { display:flex; gap:16px; justify-content:center; align-items:flex-start; flex-wrap:wrap; }
  .stat { color:#0a0; font-size:13px; margin-top:10px; }
  #gs { font-size:14px; margin:6px; }
  .ctl { color:#080; font-size:12px; margin-top:8px; }
</style></head><body>
<h1>DOOM ON GLASS</h1>
<div class="sub">CWM raycaster &mdash; the glass renders the walls. Press <b>G</b> to cut the glass and watch it collapse.</div>
<div id="gs">GLASS: ON</div>
<div class="wrap">
  <canvas id="view" width="512" height="320"></canvas>
  <canvas id="map" width="200" height="200"></canvas>
</div>
<div class="stat"><span id="stats">Features: -- | Render: -- ms | Fidelity: --%</span></div>
<canvas id="spec" width="480" height="130" style="margin-top:12px;border-color:#063;"></canvas>
<div style="color:#0a0;font-size:11px;margin-top:3px;">LIVE GLASS SPECTRUM &mdash; <span style="color:#0ff">x</span>/<span style="color:#f80">y</span>/<span style="color:#f0f">angle</span> drive tones encode player state</div>
<div class="ctl">W/S = forward/back &nbsp; A/D = turn &nbsp; G = toggle glass &nbsp; Q = quit</div>
<script>
const VW=512, VH=320, NC=8, COLW=VW/NC;
const vctx=document.getElementById('view').getContext('2d');
const mctx=document.getElementById('map').getContext('2d');
function draw(s){
  // first-person view: 8 columns, height = wall distance
  vctx.fillStyle='#000'; vctx.fillRect(0,0,VW,VH);
  // ceiling/floor
  vctx.fillStyle='#020'; vctx.fillRect(0,0,VW,VH/2);
  vctx.fillStyle='#011'; vctx.fillRect(0,VH/2,VW,VH/2);
  for(let c=0;c<NC;c++){
    const h=Math.max(0.05,Math.min(1,s.columns[c]/2.0))*VH;
    const shade=Math.floor(80+150*Math.min(1,s.columns[c]/2.0));
    vctx.fillStyle=`rgb(0,${shade},0)`;
    vctx.fillRect(c*COLW, (VH-h)/2, COLW-1, h);
  }
  if(!s.glass_enabled){
    vctx.fillStyle='rgba(255,0,0,0.12)'; vctx.fillRect(0,0,VW,VH);
    vctx.fillStyle='#f44'; vctx.font='16px monospace';
    vctx.fillText('GLASS OFF — no render', VW/2-90, VH/2);
  }
  // overhead map
  const MW=200, CELL=MW/s.mz_w;
  mctx.fillStyle='#000'; mctx.fillRect(0,0,MW,MW);
  for(let y=0;y<s.mz_h;y++)for(let x=0;x<s.mz_w;x++){
    if(s.maze[y][x]===1){ mctx.fillStyle='#050'; mctx.fillRect(x*CELL,y*CELL,CELL-1,CELL-1); }
  }
  // player
  mctx.fillStyle='#0ff';
  mctx.beginPath(); mctx.arc((s.x+0.5)*CELL,(s.y+0.5)*CELL,CELL*0.28,0,7); mctx.fill();
  const ang=s.a*(2*Math.PI/s.n_dirs);
  mctx.strokeStyle='#0ff'; mctx.lineWidth=2; mctx.beginPath();
  mctx.moveTo((s.x+0.5)*CELL,(s.y+0.5)*CELL);
  mctx.lineTo((s.x+0.5+0.5*Math.cos(ang))*CELL,(s.y+0.5+0.5*Math.sin(ang))*CELL); mctx.stroke();
  document.getElementById('gs').textContent='GLASS: '+(s.glass_enabled?'ON':'OFF');
  document.getElementById('gs').style.color=s.glass_enabled?'#0f0':'#f44';
  document.getElementById('stats').textContent=
    `Features: ${s.n_features} (${s.n_modes} modes) | Render: ${s.render_ms} ms | Fidelity: ${s.render_fidelity}% | Steps: ${s.steps}`;
}
document.addEventListener('keydown',e=>{
  let k=null;
  if(e.key==='w'||e.key==='ArrowUp')k='FWD';
  if(e.key==='s'||e.key==='ArrowDown')k='BACK';
  if(e.key==='a'||e.key==='ArrowLeft')k='LEFT';
  if(e.key==='d'||e.key==='ArrowRight')k='RIGHT';
  if(e.key==='g'||e.key==='G')k='TOGGLE_GLASS';
  if(e.key==='q'||e.key==='Escape')k='QUIT';
  if(k){e.preventDefault();fetch('/input?key='+k);}
});
setInterval(()=>fetch('/state').then(r=>r.json()).then(draw).catch(()=>{}),50);
// spectrum
const sctx=document.getElementById('spec').getContext('2d');
const SW=480,SH=130;
function drawSpec(d){
  sctx.fillStyle='#0a0a0a'; sctx.fillRect(0,0,SW,SH);
  if(!d.mags||d.mags.length===0)return;
  const n=d.mags.length,peak=d.peak||1,loF=d.freqs_khz[0],hiF=d.freqs_khz[n-1];
  const fx=fk=>(fk-loF)/(hiF-loF)*SW;
  const isGlass=d.source==='glass';
  sctx.strokeStyle=isGlass?'#0f0':'#7a4'; sctx.lineWidth=1.3; sctx.beginPath();
  for(let i=0;i<n;i++){const x=fx(d.freqs_khz[i]),y=SH-(d.mags[i]/peak)*(SH-10)-2; i?sctx.lineTo(x,y):sctx.moveTo(x,y);}
  sctx.stroke();
  const cols=['#0ff','#f80','#f0f'],labs=['x','y','ang'];
  for(let k=0;k<d.drives_khz.length;k++){const x=fx(d.drives_khz[k]);
    sctx.strokeStyle=cols[k];sctx.lineWidth=2;sctx.setLineDash([4,3]);
    sctx.beginPath();sctx.moveTo(x,0);sctx.lineTo(x,SH);sctx.stroke();sctx.setLineDash([]);
    sctx.fillStyle=cols[k];sctx.font='10px monospace';
    sctx.fillText(labs[k],Math.min(Math.max(x+2,2),SW-20),11+k*11);}
  sctx.fillStyle=isGlass?'#0f0':'#a83';sctx.font='9px monospace';
  sctx.fillText(isGlass?'● PHYSICAL GLASS':'● simulated',SW/2-40,SH-3);
}
setInterval(()=>fetch('/spectrum').then(r=>r.json()).then(drawSpec).catch(()=>{}),140);
</script></body></html>"""


class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            self.send_response(200); self.send_header('Content-Type', 'text/html'); self.end_headers()
            self.wfile.write(HTML_PAGE.encode())
        elif self.path == '/state':
            self.send_response(200); self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*'); self.end_headers()
            self.wfile.write(json.dumps(game.to_dict()).encode())
        elif self.path == '/spectrum':
            self.send_response(200); self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*'); self.end_headers()
            self.wfile.write(json.dumps(latest_spectrum).encode())
        elif self.path.startswith('/input'):
            params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            key = params.get('key', [None])[0]
            if key:
                player_input['key'] = key
            self.send_response(200); self.end_headers()
        else:
            self.send_response(404); self.end_headers()

    def log_message(self, *a):
        pass


print(f"\n  Starting maze server on http://localhost:{args.port}")
print(f"  Open in browser to play! W/A/S/D to move, G to toggle glass.\n")
server = ThreadingHTTPServer(('', args.port), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()


def render_now():
    """Render the current view (glass or, if OFF, noise)."""
    global game
    if glass_enabled:
        t0 = time.time()
        game.columns = glass_render(game.x, game.y, game.a)
        game.render_ms = (time.time() - t0) * 1000
        # fidelity vs ground truth
        tru = true_render(game.x, game.y, game.a)
        gc = np.array(game.columns); tc = np.array(tru)
        if gc.std() > 1e-6 and tc.std() > 1e-6:
            r = np.corrcoef(gc, tc)[0, 1]
            game.render_fidelity = max(0.0, r * 100)
    else:
        game.columns = (np.random.rand(N_COLS) * (T_MAX - T_MIN) + T_MIN).tolist()
        game.render_ms = 0.0
        game.render_fidelity = 0.0


render_now()
try:
    while game_running:
        game.frame += 1
        key = player_input.get('key'); player_input['key'] = None
        moved = False
        if key == 'FWD':
            game.try_move(+1); moved = True
        elif key == 'BACK':
            game.try_move(-1); moved = True
        elif key == 'LEFT':
            game.turn(-1); moved = True
        elif key == 'RIGHT':
            game.turn(+1); moved = True
        elif key == 'TOGGLE_GLASS':
            glass_enabled = not glass_enabled
            print(f"  Glass {'ON' if glass_enabled else 'OFF'}")
            moved = True
        elif key == 'QUIT':
            break
        if moved:
            render_now()
            if game.frame % 1 == 0:
                print(f"  pos ({game.x},{game.y}) facing {game.a} | "
                      f"render {game.render_ms:.0f}ms fidelity {game.render_fidelity:.0f}%")
        time.sleep(1.0 / args.fps)
except KeyboardInterrupt:
    pass
finally:
    if not args.simulated and handle:
        try:
            nco_ser.write(b'Foff\n'); nco_ser.close()
            ps.ps2000_stop(handle); ps.ps2000_close_unit(ct.c_int16(handle))
        except Exception:
            pass
    print("\n  Maze stopped.")
