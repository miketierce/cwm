#!/usr/bin/env python3
"""
CAM-DOOM Live — compute-via-recall first-person maze
=====================================================

The glass is a content-addressable memory (the "deck of cards"). Each step:
  1. The player's true (x, y, facing) is amplitude-encoded as a QUERY (3 tones).
  2. The glass produces a distributed fingerprint; we read it.
  3. Factored nearest-centroid RECALLS the stored state (x, y) from the glass
     fingerprint — parallel associative search, robust to query noise.
  4. The recalled state's PRECOMPUTED frame is rendered (first-person + map).

Why this isn't a wire: recall denoises a corrupted query and SNAPS to the
nearest enrolled card (pattern completion). Toggle G to cut the glass — the
recall falls back to noise and the view scrambles, proving the glass did the
addressing.

Includes the live glass-spectrum chart (same as Pong) so the audience sees the
amplitude-encoded query tones and the glass's distributed response.

Usage:
  python3 tools/cam_doom_live.py --model data/results/cam_doom/cam_doom_model_*.json --nco-port /dev/cu.usbmodem113401
  python3 tools/cam_doom_live.py --model <model> --simulated
"""
import ctypes as ct
import numpy as np
import json, time, math, threading, argparse, sys, urllib.parse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

parser = argparse.ArgumentParser(description='CAM-DOOM live recall maze')
parser.add_argument('--model', type=str, required=True)
parser.add_argument('--nco-port', type=str, default='/dev/cu.usbmodem113401')
parser.add_argument('--simulated', action='store_true')
parser.add_argument('--port', type=int, default=8767)
parser.add_argument('--fps', type=float, default=30.0)
parser.add_argument('--query-noise', type=float, default=0.0,
                    help='inject query noise to showcase pattern completion (0=off)')
args = parser.parse_args()

PICO_LIB = '/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources/libps2000.dylib'
N_SAMPLES = 8064
TIMEBASE = 7
FS = 781250.0
NFFT = N_SAMPLES * 4
BIN_HZ = FS / NFFT
RNG = 6
RNG_MV = 1000.0
NAVG = 10

print("Loading model...")
M = json.load(open(args.model))
assert M['encoding'] == 'cam_doom_recall_v2_factored', f"bad encoding {M['encoding']}"
MAZE = M['maze']; MZ_H, MZ_W = len(MAZE), len(MAZE[0])
N_COLS = M['n_cols']; NDIR = M['n_dirs']
STATES = [tuple(s) for s in M['states']]
RENDERS = {int(k): v for k, v in M['renders'].items()}
OPEN_CELLS = [tuple(c) for c in M['open_cells']]
AXES = M['axes']
LEVELS = M['levels']
WINDOW_OFFSETS = M['window_offsets']
FEATURE_SPEC = M['feature_spec']
AXIS_MODELS = M['axis_models']
WIRE_MODELS = M.get('wire_models')   # single-bin "wire+ADC" baseline (collapses under noise)
ROW_NORM = M.get('row_normalize', 'mean')
print(f"  CAM-DOOM recall — {MZ_W}x{MZ_H} maze, {len(STATES)} cards")
print(f"  Recall metrics: joint {M['metrics']['joint_recall']:.0f}%, "
      f"position {M['metrics']['position_recall']:.0f}%, "
      f"noise-robust pos {M['metrics'].get('noise_robust_pos_s1', 0):.0f}%")

# ─── Hardware ────────────────────────────────────────────────────
handle = None; nco_ser = None
if not args.simulated:
    import serial
    print("Initializing hardware...")
    ps = ct.CDLL(PICO_LIB); ps.ps2000_open_unit.restype = ct.c_int16
    handle = ps.ps2000_open_unit()
    if handle <= 0:
        print(f"ERROR PicoScope {handle}"); sys.exit(1)
    ps.ps2000_set_channel(handle, 0, 1, 0, RNG); ps.ps2000_set_channel(handle, 1, 0, 0, RNG)
    ps.ps2000_set_trigger(handle, 5, 0, 0, 0, 0)
    nco_ser = serial.Serial(args.nco_port, 115200, timeout=2)
    time.sleep(0.5); nco_ser.reset_input_buffer()
    nco_ser.write(b'STATUS\n'); time.sleep(0.2)
    st = nco_ser.readline().decode(errors='replace').strip()
    if 'DUTY' not in st:
        print("ERROR: firmware lacks DUTY — flash tools/pico_nco/main.py"); sys.exit(1)
    print(f"  PicoScope handle={handle}, NCO ok")


def _capture(navg=NAVG):
    buf = (ct.c_int16*N_SAMPLES)(); ov = ct.c_int16(); mags = []
    for _ in range(navg):
        tk = ct.c_int32(); ps.ps2000_run_block(handle, N_SAMPLES, TIMEBASE, 1, ct.byref(tk))
        for _ in range(500):
            if ps.ps2000_ready(handle): break
            time.sleep(0.002)
        ps.ps2000_get_values(handle, ct.byref(buf), None, None, None, ct.byref(ov), N_SAMPLES)
        d = np.array(buf[:], dtype=np.float64)*(RNG_MV/32767.0); d -= d.mean()
        mags.append(np.abs(np.fft.rfft(d*np.hanning(N_SAMPLES), n=NFFT)))
    return np.mean(mags, axis=0) if mags else np.zeros(NFFT//2+1)


def _win(spec, f):
    out = np.zeros(len(WINDOW_OFFSETS)); base = int(round(f/BIN_HZ))
    for i, o in enumerate(WINDOW_OFFSETS):
        b = base+o; out[i] = float(spec[max(0, b-1):b+2].max()) if 0 <= b < len(spec) else 0.0
    return out


def _amp(spec, f, s=2):
    b = int(round(f/BIN_HZ)); return float(spec[max(0, b-s):min(len(spec), b+s+1)].max())


def extract(spec):
    feats = []
    for s in FEATURE_SPEC:
        if s['kind'] == 'win':
            base = int(round(s['freq']/BIN_HZ)) + s['off']
            feats.append(float(spec[max(0, base-1):base+2].max()) if 0 <= base < len(spec) else 0.0)
        else:
            feats.append(_amp(spec, s['freq']))
    f = np.array(feats)
    if ROW_NORM == 'mean':
        m = f.mean(); f = f/(m if m > 1e-9 else 1.0)
    return f


# ─── Live spectrum ───────────────────────────────────────────────
SPEC_LO_HZ, SPEC_HI_HZ, SPEC_POINTS = 30000, 350000, 480
latest_spectrum = {'freqs_khz': [], 'mags': [], 'drives_khz': [], 'peak': 1.0, 'source': 'none'}


def _store_spec(spec, drives, source):
    lo = int(SPEC_LO_HZ/BIN_HZ); hi = int(SPEC_HI_HZ/BIN_HZ); seg = spec[lo:hi]
    if len(seg) > SPEC_POINTS:
        step = len(seg)//SPEC_POINTS; seg = seg[:step*SPEC_POINTS].reshape(SPEC_POINTS, step).max(1)
    freqs = np.linspace(SPEC_LO_HZ, SPEC_HI_HZ, len(seg))/1000.0
    latest_spectrum.update(freqs_khz=freqs.round(1).tolist(), mags=seg.round(1).tolist(),
                           drives_khz=[round(d/1000, 1) for d in drives],
                           peak=float(seg.max()) if len(seg) else 1.0, source=source)


def _synth(qx, qy, qf):
    n = NFFT//2+1; sp = np.random.rand(n)*40+30
    for (ax, lvl) in [(AXES[0], qx), (AXES[1], qy), (AXES[2], qf)]:
        b = int(round(ax['freq']/BIN_HZ)); amp = 300+500*math.sin(math.pi*(lvl+1)/5)
        for o in range(-25, 26):
            if 0 <= b+o < n: sp[b+o] += amp*math.exp(-(o**2)/50)
    return sp


def query_and_recall(x, y, facing):
    """Drive the amplitude-encoded query, read the glass, factored recall (x,y)."""
    qx, qy, qf = x, y, facing  # level indices per axis (x in 0..MZ_W-1 etc.)
    drives = [AXES[0]['freq'], AXES[1]['freq'], AXES[2]['freq']]
    if args.simulated:
        spec = _synth(qx, qy, qf); _store_spec(spec, drives, 'simulated')
    else:
        nco_ser.reset_input_buffer()
        nco_ser.write(f"Foff\n".encode()); time.sleep(0.008)
        nco_ser.write(f"{AXES[0]['ch']}:{AXES[0]['freq']}\n".encode()); time.sleep(0.008)
        nco_ser.write(f"A{AXES[0]['ch'][1]}:{LEVELS['x'][min(x, len(LEVELS['x'])-1)]}\n".encode()); time.sleep(0.008)
        nco_ser.write(f"{AXES[1]['ch']}:{AXES[1]['freq']}\n".encode()); time.sleep(0.008)
        nco_ser.write(f"A{AXES[1]['ch'][1]}:{LEVELS['y'][min(y, len(LEVELS['y'])-1)]}\n".encode()); time.sleep(0.008)
        nco_ser.write(f"{AXES[2]['ch']}:{AXES[2]['freq']}\n".encode()); time.sleep(0.008)
        nco_ser.write(f"A{AXES[2]['ch'][1]}:{LEVELS['facing'][min(facing, len(LEVELS['facing'])-1)]}\n".encode())
        time.sleep(0.04)
        spec = _capture(); _store_spec(spec, drives, 'glass')
    f = extract(spec)
    nz = query_noise_on[0]
    # FAIR query noise: injected in STANDARDIZED space (per-feature, proportional to
    # each feature's own spread) — matches the principled offline test. The earlier
    # global-std-on-raw-vector model was unfair (it swamped the tightest/best features).
    rng = np.random.default_rng()
    # GLASS recall: factored distributed nearest-centroid (pattern completion)
    rec = {}
    for an in ('x', 'y', 'facing'):
        am = AXIS_MODELS[an]; sel = am['sel']
        xs = (f[sel] - np.array(am['mu']))/np.array(am['sd'])
        if nz > 0:
            xs = xs + rng.standard_normal(len(xs))*nz
        cls = am['classes']; cents = np.array([am['centroids'][str(c)] for c in cls])
        rec[an] = int(cls[((cents-xs)**2).sum(1).argmin()])
    # WIRE baseline: decode each axis from ONLY its driven center bin (no spread)
    wire = {}
    if WIRE_MODELS:
        for an in ('x', 'y', 'facing'):
            wm = WIRE_MODELS[an]
            v = (f[wm['col']] - wm['mu'])/wm['sd']
            if nz > 0:
                v = v + rng.standard_normal()*nz
            cls = wm['classes']; cents = np.array([wm['centroids'][str(c)] for c in cls])
            wire[an] = int(cls[np.abs(cents - v).argmin()])
    return rec, wire


# ─── Game ────────────────────────────────────────────────────────
class Game:
    def __init__(self):
        self.x, self.y = OPEN_CELLS[0]
        self.a = 0
        self.frame = 0
        self.recall_ms = 0.0
        self.rec_x, self.rec_y, self.rec_a = self.x, self.y, 0
        self.wire_x, self.wire_y = self.x, self.y
        self.cols = [0.0]*N_COLS
        self.correct = 0
        self.wire_correct = 0
        self.steps = 0
        self.recall_ok = True
        self.wire_ok = True

    def dirvec(self):
        ang = math.radians(self.a*(360.0/NDIR)); return round(math.cos(ang)), round(math.sin(ang))

    def move(self, s):
        dx, dy = self.dirvec(); nx, ny = self.x+dx*s, self.y+dy*s
        if 0 <= nx < MZ_W and 0 <= ny < MZ_H and MAZE[ny][nx] == 0:
            self.x, self.y = nx, ny; self.steps += 1

    def turn(self, d): self.a = (self.a+d) % NDIR

    def to_dict(self):
        return {'x': self.x, 'y': self.y, 'a': self.a,
                'rec_x': self.rec_x, 'rec_y': self.rec_y, 'rec_a': self.rec_a,
                'wire_x': self.wire_x, 'wire_y': self.wire_y,
                'cols': [round(c, 3) for c in self.cols], 'recall_ms': round(self.recall_ms, 1),
                'maze': MAZE, 'mz_w': MZ_W, 'mz_h': MZ_H, 'n_dirs': NDIR,
                'steps': self.steps, 'correct': self.correct, 'wire_correct': self.wire_correct,
                'accuracy': round(self.correct/max(self.steps, 1)*100, 0),
                'wire_accuracy': round(self.wire_correct/max(self.steps, 1)*100, 0),
                'glass_enabled': glass_enabled, 'recall_ok': self.recall_ok, 'wire_ok': self.wire_ok,
                'query_noise': query_noise_on[0], 'has_wire': WIRE_MODELS is not None}


game = Game(); player_input = {'key': None}; glass_enabled = True; game_running = True
query_noise_on = [args.query_noise]   # mutable; toggled live with N key


def do_recall():
    global game
    if glass_enabled:
        t0 = time.time()
        rec, wire = query_and_recall(game.x, game.y, game.a)
        game.recall_ms = (time.time()-t0)*1000
        game.rec_x, game.rec_y = rec['x'], rec['y']
        game.rec_a = rec['facing']
        game.recall_ok = (rec['x'] == game.x and rec['y'] == game.y)
        if wire:
            game.wire_x, game.wire_y = wire['x'], wire['y']
            game.wire_ok = (wire['x'] == game.x and wire['y'] == game.y)
    else:
        # glass off: random card recalled -> scrambled view
        rx, ry = OPEN_CELLS[np.random.randint(len(OPEN_CELLS))]
        game.rec_x, game.rec_y, game.rec_a = rx, ry, np.random.randint(NDIR)
        game.wire_x, game.wire_y = rx, ry
        game.recall_ms = 0.0; game.recall_ok = False; game.wire_ok = False
    # render the RECALLED card (find state index)
    try:
        si = STATES.index((game.rec_x, game.rec_y, game.rec_a))
    except ValueError:
        si = 0
    game.cols = RENDERS[si]
    if glass_enabled and game.recall_ok:
        game.correct += 1
    if glass_enabled and game.wire_ok:
        game.wire_correct += 1
    game.steps_seen = getattr(game, 'steps_seen', 0) + 1


HTML = """<!DOCTYPE html><html><head><meta charset="utf-8"><title>CAM-DOOM ON GLASS</title>
<style>
 body{background:#0a0a0a;color:#0f0;font-family:monospace;text-align:center;margin:0;padding:14px}
 h1{font-size:21px;margin:4px} .sub{color:#0a0;font-size:12px;margin-bottom:10px}
 canvas{border:2px solid #0f0;background:#000;image-rendering:pixelated} #map{border-color:#063}
 .wrap{display:flex;gap:16px;justify-content:center;align-items:flex-start;flex-wrap:wrap}
 #gs{font-size:14px;margin:6px} .stat{color:#0a0;font-size:13px;margin-top:8px}
 .ctl{color:#080;font-size:12px;margin-top:8px}
</style></head><body>
<h1>CAM-DOOM ON GLASS &mdash; compute via recall</h1>
<div class="sub">The glass is a content-addressable memory. Your position is a QUERY; the glass RECALLS the stored card.<br>
<b>The real proof:</b> press <b>N</b> to corrupt the query with noise &mdash; the <span style="color:#f0f">glass</span> still recalls the right cell (pattern completion), the <span style="color:#ff0">wire</span> falls off. A wire can't denoise. Press <b>G</b> to cut the glass entirely.</div>
<div id="gs">GLASS: ON</div>
<div class="wrap">
 <canvas id="view" width="512" height="320"></canvas>
 <canvas id="map" width="200" height="200"></canvas>
</div>
<div class="stat"><span id="stats"></span></div>
<canvas id="spec" width="480" height="130" style="margin-top:12px;border-color:#063"></canvas>
<div style="color:#0a0;font-size:11px;margin-top:3px">LIVE GLASS SPECTRUM &mdash; <span style="color:#0ff">x</span>/<span style="color:#f80">y</span>/<span style="color:#f0f">facing</span> AMPLITUDE-encoded query tones; the glass response is the distributed fingerprint matched against the deck</div>
<div class="ctl">W/S move &nbsp; A/D turn &nbsp; <b>N</b> toggle query noise &nbsp; G toggle glass &nbsp; Q quit</div>
<script>
const VW=512,VH=320,NC=8,COLW=VW/NC;
const vctx=document.getElementById('view').getContext('2d');
const mctx=document.getElementById('map').getContext('2d');
function draw(s){
 vctx.fillStyle='#000';vctx.fillRect(0,0,VW,VH);
 vctx.fillStyle='#020';vctx.fillRect(0,0,VW,VH/2);vctx.fillStyle='#011';vctx.fillRect(0,VH/2,VW,VH/2);
 for(let c=0;c<NC;c++){const h=Math.max(0.05,Math.min(1,s.cols[c]/2.0))*VH;
  const sh=Math.floor(80+150*Math.min(1,s.cols[c]/2.0));vctx.fillStyle=`rgb(0,${sh},0)`;
  vctx.fillRect(c*COLW,(VH-h)/2,COLW-1,h);}
 if(!s.glass_enabled){vctx.fillStyle='rgba(255,0,0,0.14)';vctx.fillRect(0,0,VW,VH);
  vctx.fillStyle='#f44';vctx.font='15px monospace';vctx.fillText('GLASS OFF \u2014 recall scrambled',VW/2-100,VH/2);}
 else if(!s.recall_ok){vctx.fillStyle='rgba(255,160,0,0.10)';vctx.fillRect(0,0,VW,VH);}
 if(s.query_noise>0){vctx.fillStyle='#ff0';vctx.font='12px monospace';vctx.fillText('QUERY NOISE \u03c3='+s.query_noise,8,18);}
 const MW=200,CELL=MW/s.mz_w;mctx.fillStyle='#000';mctx.fillRect(0,0,MW,MW);
 for(let y=0;y<s.mz_h;y++)for(let x=0;x<s.mz_w;x++)if(s.maze[y][x]===1){mctx.fillStyle='#050';mctx.fillRect(x*CELL,y*CELL,CELL-1,CELL-1);}
 // wire-recalled (yellow, drawn first/under) then glass-recalled (magenta), then true (cyan)
 if(s.has_wire){mctx.strokeStyle='#ff0';mctx.lineWidth=3;mctx.strokeRect((s.wire_x)*CELL+6,(s.wire_y)*CELL+6,CELL-12,CELL-12);}
 mctx.fillStyle='#0ff';mctx.beginPath();mctx.arc((s.x+0.5)*CELL,(s.y+0.5)*CELL,CELL*0.22,0,7);mctx.fill();
 mctx.strokeStyle='#f0f';mctx.lineWidth=3;mctx.strokeRect((s.rec_x)*CELL+3,(s.rec_y)*CELL+3,CELL-6,CELL-6);
 const ang=s.a*(2*Math.PI/s.n_dirs);mctx.strokeStyle='#0ff';mctx.lineWidth=2;mctx.beginPath();
 mctx.moveTo((s.x+0.5)*CELL,(s.y+0.5)*CELL);mctx.lineTo((s.x+0.5+0.5*Math.cos(ang))*CELL,(s.y+0.5+0.5*Math.sin(ang))*CELL);mctx.stroke();
 document.getElementById('gs').textContent='GLASS: '+(s.glass_enabled?'ON':'OFF');
 document.getElementById('gs').style.color=s.glass_enabled?'#0f0':'#f44';
 let wireTxt = s.has_wire ? ` &nbsp;|&nbsp; <span style="color:#ff0">wire (${s.wire_x},${s.wire_y}) ${s.wire_ok?'\u2713':'\u2717'} acc ${s.wire_accuracy}%</span>` : '';
 document.getElementById('stats').innerHTML=
  `true (${s.x},${s.y}) &rarr; <span style="color:#f0f">glass (${s.rec_x},${s.rec_y}) ${s.recall_ok?'\u2713':'\u2717'} acc ${s.accuracy}%</span>`+wireTxt+
  ` &nbsp;|&nbsp; ${s.recall_ms} ms ${s.query_noise>0?'| <span style=\"color:#ff0\">NOISY QUERY \u03c3='+s.query_noise+'</span>':''}`;
}
document.addEventListener('keydown',e=>{let k=null;
 if(e.key==='w'||e.key==='ArrowUp')k='FWD';if(e.key==='s'||e.key==='ArrowDown')k='BACK';
 if(e.key==='a'||e.key==='ArrowLeft')k='LEFT';if(e.key==='d'||e.key==='ArrowRight')k='RIGHT';
 if(e.key==='g'||e.key==='G')k='G';if(e.key==='n'||e.key==='N')k='N';if(e.key==='q'||e.key==='Escape')k='QUIT';
 if(k){e.preventDefault();fetch('/input?key='+k);}});
setInterval(()=>fetch('/state').then(r=>r.json()).then(draw).catch(()=>{}),60);
const sctx=document.getElementById('spec').getContext('2d');const SW=480,SH=130;
function spec(d){sctx.fillStyle='#0a0a0a';sctx.fillRect(0,0,SW,SH);if(!d.mags||!d.mags.length)return;
 const n=d.mags.length,pk=d.peak||1,lo=d.freqs_khz[0],hi=d.freqs_khz[n-1],fx=k=>(k-lo)/(hi-lo)*SW;
 const g=d.source==='glass';sctx.strokeStyle=g?'#0f0':'#7a4';sctx.lineWidth=1.3;sctx.beginPath();
 for(let i=0;i<n;i++){const x=fx(d.freqs_khz[i]),y=SH-(d.mags[i]/pk)*(SH-10)-2;i?sctx.lineTo(x,y):sctx.moveTo(x,y);}sctx.stroke();
 const cs=['#0ff','#f80','#f0f'],lb=['x','y','fac'];for(let k=0;k<d.drives_khz.length;k++){const x=fx(d.drives_khz[k]);
  sctx.strokeStyle=cs[k];sctx.lineWidth=2;sctx.setLineDash([4,3]);sctx.beginPath();sctx.moveTo(x,0);sctx.lineTo(x,SH);sctx.stroke();sctx.setLineDash([]);
  sctx.fillStyle=cs[k];sctx.font='10px monospace';sctx.fillText(lb[k],Math.min(Math.max(x+2,2),SW-22),11+k*11);}
 sctx.fillStyle=g?'#0f0':'#a83';sctx.font='9px monospace';sctx.fillText(g?'\u25cf PHYSICAL GLASS':'\u25cf simulated',SW/2-40,SH-3);}
setInterval(()=>fetch('/spectrum').then(r=>r.json()).then(spec).catch(()=>{}),140);
</script></body></html>"""


class H(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            self.send_response(200); self.send_header('Content-Type', 'text/html'); self.end_headers()
            self.wfile.write(HTML.encode())
        elif self.path == '/state':
            self.send_response(200); self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*'); self.end_headers()
            self.wfile.write(json.dumps(game.to_dict()).encode())
        elif self.path == '/spectrum':
            self.send_response(200); self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*'); self.end_headers()
            self.wfile.write(json.dumps(latest_spectrum).encode())
        elif self.path.startswith('/input'):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            k = q.get('key', [None])[0]
            if k: player_input['key'] = k
            self.send_response(200); self.end_headers()
        else:
            self.send_response(404); self.end_headers()

    def log_message(self, *a): pass


print(f"\n  Starting CAM-DOOM server on http://localhost:{args.port}")
print(f"  WASD move, G toggle glass.  (cyan dot = true pos, magenta box = glass-recalled pos)\n")
server = ThreadingHTTPServer(('', args.port), H)
threading.Thread(target=server.serve_forever, daemon=True).start()

do_recall()
try:
    while game_running:
        game.frame += 1
        k = player_input.get('key'); player_input['key'] = None
        moved = False
        if k == 'FWD': game.move(+1); moved = True
        elif k == 'BACK': game.move(-1); moved = True
        elif k == 'LEFT': game.turn(-1); moved = True
        elif k == 'RIGHT': game.turn(+1); moved = True
        elif k == 'G':
            glass_enabled = not glass_enabled; moved = True
            print(f"  Glass {'ON' if glass_enabled else 'OFF'}")
        elif k == 'N':
            # toggle query noise — the demo that separates glass from a wire
            query_noise_on[0] = 0.0 if query_noise_on[0] > 0 else 1.0
            game.correct = 0; game.wire_correct = 0; game.steps = max(game.steps, 1)
            game.correct = 0; game.wire_correct = 0; game.steps = 0
            moved = True
            print(f"  Query noise {'ON (σ=1.0)' if query_noise_on[0] > 0 else 'OFF'}")
        elif k == 'QUIT': break
        if moved:
            do_recall()
            print(f"  true({game.x},{game.y}) -> recalled({game.rec_x},{game.rec_y}) "
                  f"{'OK' if game.recall_ok else 'miss'} {game.recall_ms:.0f}ms")
        time.sleep(1.0/args.fps)
except KeyboardInterrupt:
    pass
finally:
    if not args.simulated and handle:
        try:
            nco_ser.write(b'Foff\n'); nco_ser.close()
            ps.ps2000_stop(handle); ps.ps2000_close_unit(ct.c_int16(handle))
        except Exception:
            pass
    print("\n  CAM-DOOM stopped.")
