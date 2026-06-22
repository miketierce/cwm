#!/usr/bin/env python3
"""
PONG ON GLASS — heading-recall edition (difficulty = heading resolution)
========================================================================

The glass paddle PREDICTS where the ball will arrive by RECALL, using the two
validated channels of this session:
  • position (ball_y)  → AMPLITUDE of a fixed mode (proven monotonic)
  • heading  (angle)   → RELATIVE PHASE between two co-driven corners, read
                          jitter-free as interference ENERGY (validated 98%/4°)

DIFFICULTY = how much heading information is encoded (the user's idea):
  easy   K=2  headings (coarse: up vs down — like the old binary tag)
  hard   K=4  headings
  expert K=8  headings (fine angle → predicts angled shots precisely)
Finer heading ⇒ the glass resolves the ball's true angle ⇒ better bounce
prediction ⇒ higher intercept. The ball physics support angled travel (paddle
"English"), so heading actually carries information — without that, more K would
be meaningless theater.

HOW A DECISION WORKS (genuine compute-by-recall):
  1. encode current (ball_y level, heading index) as amplitude + relative-phase drive
  2. capture: read ball_y from the amplitude window; read heading from interference
     energy at 2 I/Q modes (91k,86k) → recover heading index
  3. recall the nearest enrolled (pos,heading) card → read its STORED LANDING
     (forward-simulated y where the ball reaches the right wall, with wall bounces)
  4. move the paddle to that predicted landing
The deck is enrolled on real glass at boot. Glass OFF = random drift (control).

Honest scope: classical; heading resolution is SNR-limited; the landing is a
stored forward-sim (the glass does the position+heading READ and the associative
RECALL, the laptop runs game logic + the stored sim). Web UI on --port.

Usage:
  python3 tools/pong_heading_live.py --nco-port /dev/cu.usbmodem113401 --difficulty expert
  python3 tools/pong_heading_live.py --simulated --difficulty expert   # no hardware
"""
import ctypes as ct
import numpy as np
import json, time, math, argparse, sys, threading, urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

ap = argparse.ArgumentParser(description='Pong on glass — heading recall')
ap.add_argument('--nco-port', type=str, default='/dev/cu.usbmodem113401')
ap.add_argument('--simulated', action='store_true')
ap.add_argument('--difficulty', type=str, default='expert', choices=['easy', 'hard', 'expert'])
ap.add_argument('--port', type=int, default=8765)
ap.add_argument('--ball-speed', type=float, default=0.35, help='cells the ball advances per step')
ap.add_argument('--step-ms', type=int, default=220, help='ms between ball steps (>= glass decision time)')
ap.add_argument('--pos-levels', type=int, default=6, help='L ball_y enrollment levels')
ap.add_argument('--repeats', type=int, default=4, help='enrollment repeats per card')
ap.add_argument('--navg', type=int, default=4)
args = ap.parse_args()

K_BY_DIFF = {'easy': 2, 'hard': 4, 'expert': 8}
K = K_BY_DIFF[args.difficulty]
L = args.pos_levels

# ─── Constants ───────────────────────────────────────────────────────────────
PICO_LIB = '/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources/libps2000.dylib'
N_SAMPLES = 8064; TIMEBASE = 7; FS = 781250.0; NFFT = N_SAMPLES * 4
BIN_HZ = FS / NFFT; RNG = 6; RNG_MV = 1000.0
COURT_W, COURT_H = 16, 12
PADDLE_H = 3
THETA_MAX = 55.0                     # max heading angle off horizontal (deg)
POS_CH, POS_FREQ = 'F4', 48000       # ball_y → amplitude
IQ_MODES = [91000, 86000]            # heading → relative phase, read at these I/Q modes (F1+F2)
WIN = [-8, -4, -2, 0, 2, 4, 8]; NW = len(WIN)


def duty_levels(n):
    return [round(math.asin((i + 1) / n) / math.pi * 1000) for i in range(n)]
POS_DUTY = duty_levels(L)
# heading index h∈[0,K) → angle and → encoded relative phase (spread across the circle)
HEAD_ANGLE = [(-THETA_MAX + 2 * THETA_MAX * h / (K - 1)) if K > 1 else 0.0 for h in range(K)]
HEAD_PHASE = [round(360.0 * h / K) for h in range(K)]   # the PH2 we drive to encode heading h


def angle_to_head_idx(theta_deg):
    """Quantize a real heading angle to the nearest enrolled heading index."""
    return int(np.argmin([abs(((theta_deg - a + 180) % 360) - 180) for a in HEAD_ANGLE]))


def landing_for(by_level, h):
    """Forward-sim: ball at ball_y(level), heading angle HEAD_ANGLE[h], travelling right.
    Return the y-cell (0..COURT_H-1) where it reaches the right wall, with top/bottom bounces."""
    y = (by_level + 0.5) * COURT_H / L
    th = math.radians(HEAD_ANGLE[h])
    vx, vy = math.cos(th), math.sin(th)
    x = 1.0
    for _ in range(2000):
        x += vx * 0.25; y += vy * 0.25
        if y < 0: y = -y; vy = -vy
        if y > COURT_H - 1: y = 2 * (COURT_H - 1) - y; vy = -vy
        if x >= COURT_W - 1:
            return int(np.clip(round(y), 0, COURT_H - 1))
    return COURT_H // 2


# enrolled cards: (position level, heading index)
CARDS = [(p, h) for p in range(L) for h in range(K)]
NCARD = len(CARDS)
CARD_LANDING = np.array([landing_for(p, h) for (p, h) in CARDS])

print("=" * 72)
print(f"  PONG ON GLASS — heading recall   difficulty={args.difficulty} (K={K} headings)")
print(f"  position→{POS_CH}@{POS_FREQ//1000}k amp ({L} levels)   heading→relative phase @ {IQ_MODES} Hz")
print(f"  {NCARD} cards (L×K) enrolled on glass")
print("=" * 72)

# ─── Hardware ────────────────────────────────────────────────────────────────
handle = None; nco = None
if not args.simulated:
    import serial
    ps = ct.CDLL(PICO_LIB); ps.ps2000_open_unit.restype = ct.c_int16
    handle = ps.ps2000_open_unit()
    if handle <= 0:
        print(f"ERROR PicoScope {handle}"); sys.exit(1)
    ps.ps2000_set_channel(handle, 0, 1, 0, RNG); ps.ps2000_set_channel(handle, 1, 0, 0, RNG)
    ps.ps2000_set_trigger(handle, 5, 0, 0, 0, 0)
    nco = serial.Serial(args.nco_port, 115200, timeout=2); time.sleep(0.5); nco.reset_input_buffer()
    nco.write(b'STATUS\n'); time.sleep(0.2)
    st = nco.readline().decode(errors='replace').strip()
    print("  NCO:", st)
    if 'PHA:' not in st:
        print("ERROR: firmware lacks PHA (per-channel phase). Flash pico_nco/main.py."); sys.exit(1)


def send(c):
    nco.reset_input_buffer(); nco.write(f'{c}\n'.encode()); time.sleep(0.009)


def capture():
    buf = (ct.c_int16 * N_SAMPLES)(); ov = ct.c_int16(); mags = []
    for _ in range(args.navg):
        tk = ct.c_int32(); ps.ps2000_run_block(handle, N_SAMPLES, TIMEBASE, 1, ct.byref(tk))
        for _ in range(500):
            if ps.ps2000_ready(handle): break
            time.sleep(0.002)
        else: continue
        ps.ps2000_get_values(handle, ct.byref(buf), None, None, None, ct.byref(ov), N_SAMPLES)
        d = np.array(buf[:], float) * (RNG_MV / 32767.0); d -= d.mean()
        mags.append(np.abs(np.fft.rfft(d * np.hanning(N_SAMPLES), n=NFFT)))
    return np.mean(mags, axis=0) if mags else np.zeros(NFFT // 2 + 1)


def amp_window(spec, f):
    out = np.zeros(NW); b = int(round(f / BIN_HZ))
    for i, o in enumerate(WIN):
        k = b + o; out[i] = float(spec[max(0, k - 1):k + 2].max()) if 0 <= k < len(spec) else 0.0
    return out
def energy_at(spec, f, half=2):
    b = int(round(f / BIN_HZ)); return float(spec[max(0, b - half):b + half + 1].sum())


_rng = np.random.default_rng(0)
# synthetic modeshape phases for --simulated heading readout
_SIM_THETAK = {91000: 270.0, 86000: 180.0}


def read_fingerprint(p, h):
    """Drive position-amp + heading-phase; return (pos_window[NW], heading_energy[len(IQ)])."""
    if args.simulated:
        pw = np.zeros(NW); pw[NW // 2] = (p + 1) / L * 3.0 + 0.05 * _rng.standard_normal()
        he = []
        for m in IQ_MODES:
            th = HEAD_PHASE[h]
            he.append((1 + 0.95 * math.cos(math.radians(th - _SIM_THETAK[m]))) * 1.0 + 0.02 * _rng.standard_normal())
        return pw, np.array(he)
    # position read: drive F4 at POS amplitude alone
    send('Foff'); send(f'{POS_CH}:{POS_FREQ}'); send(f'A{POS_CH[1]}:{POS_DUTY[p]}')
    time.sleep(0.03); sp = capture(); pw = amp_window(sp, POS_FREQ)
    # heading read: for each I/Q mode, co-drive F1+F2 at that mode with PH2 = heading phase
    he = []
    for m in IQ_MODES:
        send('Foff'); send(f'F1:{m}'); send('A1:500'); send(f'F2:{m}'); send('A2:500')
        send('PH1:0'); send(f'PH2:{HEAD_PHASE[h]}')
        time.sleep(0.03); sp = capture(); he.append(energy_at(sp, m))
    return pw, np.array(he)


# ─── Enroll the deck on glass ────────────────────────────────────────────────
print(f"\n[enroll] {NCARD} cards × {args.repeats} repeats ...")
R = args.repeats
POSF = np.zeros((NCARD * R, NW)); HEDF = np.zeros((NCARD * R, len(IQ_MODES)))
clab = np.zeros(NCARD * R, int); row = 0
t0 = time.time()
for ci, (p, h) in enumerate(CARDS):
    for r in range(R):
        pw, he = read_fingerprint(p, h); POSF[row] = pw; HEDF[row] = he; clab[row] = ci; row += 1
    if not args.simulated and (ci + 1) % 6 == 0:
        print(f"    {ci+1}/{NCARD} ({time.time()-t0:.0f}s)")
# centroids (per card) in normalized space
POSn = (POSF - POSF.mean(0)) / (POSF.std(0) + 1e-9)
HEDn = (HEDF - HEDF.mean(0)) / (HEDF.std(0) + 1e-9)
POS_MU, POS_SD = POSF.mean(0), POSF.std(0) + 1e-9
HED_MU, HED_SD = HEDF.mean(0), HEDF.std(0) + 1e-9
CENT = np.zeros((NCARD, NW + len(IQ_MODES)))
for c in range(NCARD):
    m = clab == c
    CENT[c] = np.concatenate([POSn[m].mean(0), HEDn[m].mean(0)])
print(f"[enroll] done ({time.time()-t0:.0f}s). Deck ready.\n")


def glass_predict_landing(by_level, theta_deg):
    """Drive the CURRENT ball state, read it back off glass, recall nearest card → stored landing."""
    h_true = angle_to_head_idx(theta_deg)
    pw, he = read_fingerprint(by_level, h_true)
    q = np.concatenate([(pw - POS_MU) / POS_SD, (he - HED_MU) / HED_SD])
    c = int(np.argmin(((CENT - q) ** 2).sum(1)))
    return int(CARD_LANDING[c]), c


# ═══ GAME ════════════════════════════════════════════════════════════════════
class Game:
    def __init__(self):
        self.reset_ball(+1)
        self.pl = COURT_H / 2; self.pr = COURT_H / 2
        self.sl = 0; self.sr = 0; self.frame = 0
        self.intercepts = 0; self.rallies = 0; self.dec_ms = 0.0
        self.glass_on = True; self.lock = threading.Lock()
        self.glass_target = COURT_H / 2     # where glass predicts the ball will land
        self.need_predict = True            # predict once when ball starts heading right
        self.last_card = -1

    def reset_ball(self, vx_dir):
        # serve from the edge the ball travels FROM, so the full-width enrolled landing matches
        self.bx = 1.0 if vx_dir > 0 else COURT_W - 1.0
        self.by = _rng.uniform(2, COURT_H - 2)
        th = math.radians(_rng.uniform(-THETA_MAX, THETA_MAX))
        self.vx = vx_dir * abs(math.cos(th)); self.vy = math.sin(th)

    def heading_deg(self):
        return math.degrees(math.atan2(self.vy, abs(self.vx)))

    def step(self, speed):
        prev_vx = self.vx
        self.bx += self.vx * speed; self.by += self.vy * speed
        if self.by < 0: self.by = -self.by; self.vy = -self.vy
        if self.by > COURT_H - 1: self.by = 2 * (COURT_H - 1) - self.by; self.vy = -self.vy
        # left paddle (auto-tracks, imperfect)
        if self.bx < 1:
            if abs(self.by - self.pl) <= PADDLE_H / 2 + 0.5:
                self.bx = 1; self._english(self.pl, +1); self.need_predict = True
            else:
                self.sr += 1; self.reset_ball(+1); self.need_predict = True
        # right paddle (glass)
        if self.bx > COURT_W - 1:
            self.rallies += 1
            if abs(self.by - self.pr) <= PADDLE_H / 2 + 0.5:
                self.intercepts += 1; self.bx = COURT_W - 1; self._english(self.pr, -1)
            else:
                self.sl += 1; self.reset_ball(-1)

    def _english(self, paddle_y, vx_dir):
        off = float(np.clip((self.by - paddle_y) / (PADDLE_H / 2 + 0.5), -1, 1))
        th = math.radians(off * THETA_MAX)
        self.vx = vx_dir * abs(math.cos(th)); self.vy = math.sin(th)

    def by_level(self):
        return int(np.clip(self.by * L / COURT_H, 0, L - 1))

    def to_dict(self):
        return {'bx': round(self.bx, 2), 'by': round(self.by, 2),
                'pl': round(self.pl, 2), 'pr': round(self.pr, 2),
                'sl': self.sl, 'sr': self.sr, 'frame': self.frame,
                'heading': round(self.heading_deg(), 1),
                'intercept': round(self.intercepts / max(self.rallies, 1) * 100),
                'dec_ms': round(self.dec_ms, 0), 'K': K, 'diff': args.difficulty,
                'glass_on': self.glass_on, 'court_w': COURT_W, 'court_h': COURT_H, 'paddle_h': PADDLE_H}


game = Game()
player_key = {'k': None}


def game_loop():
    last = time.time()
    while True:
        time.sleep(0.005)
        now = time.time()
        if (now - last) * 1000 < args.step_ms:
            # handle input between steps for responsiveness
            k = player_key['k']; player_key['k'] = None
            if k == 'UP': game.pl = max(PADDLE_H / 2, game.pl - 1)
            elif k == 'DOWN': game.pl = min(COURT_H - 1 - PADDLE_H / 2, game.pl + 1)
            elif k == 'G': game.glass_on = not game.glass_on
            continue
        last = now
        with game.lock:
            game.frame += 1
            # auto left paddle drifts toward ball (beatable)
            game.pl += np.clip(game.by - game.pl, -1, 1) * 0.6
            # glass PREDICTS the landing ONCE, right after the ball leaves the left paddle
            # (matches the full-width enrolled landing) — then holds. This is prediction, not tracking.
            if game.vx > 0 and game.need_predict:
                game.need_predict = False
                if game.glass_on:
                    t = time.time()
                    land, card = glass_predict_landing(game.by_level(), game.heading_deg())
                    game.dec_ms = (time.time() - t) * 1000
                    game.glass_target = float(land); game.last_card = card
                else:
                    game.dec_ms = 0.0
                    game.glass_target = float(np.clip(game.pr + _rng.choice([-3, -2, 2, 3]), 0, COURT_H - 1))
            # move the glass paddle toward its predicted target (only while ball approaches)
            if game.vx > 0:
                game.pr += np.clip(game.glass_target - game.pr, -2, 2)
                game.pr = float(np.clip(game.pr, PADDLE_H / 2, COURT_H - 1 - PADDLE_H / 2))
            game.step(args.ball_speed)


HTML = """<!DOCTYPE html><html><head><meta charset=utf-8><title>PONG ON GLASS — heading recall</title>
<style>body{background:#0a0a14;color:#cde;font-family:monospace;text-align:center}
canvas{background:#000;border:1px solid #345;margin-top:8px}
#hud{margin:6px;font-size:14px}.b{color:#6cf}.g{color:#6f9}.r{color:#f86}</style></head>
<body><div id=hud></div><canvas id=c width=640 height=480></canvas>
<div style=font-size:12px;margin-top:6px>W/S or ↑/↓ move &nbsp; G toggle glass</div>
<script>
const cv=document.getElementById('c'),x=cv.getContext('2d');let S={};
function draw(s){S=s;const W=cv.width,H=cv.height,cw=W/s.court_w,ch=H/s.court_h;
x.clearRect(0,0,W,H);
x.fillStyle='#6cf';x.fillRect(s.bx*cw-3,s.by*ch-3,6,6);
x.fillStyle='#9ad';x.fillRect(2,(s.pl-s.paddle_h/2)*ch,6,s.paddle_h*ch);
x.fillStyle=s.glass_on?'#6f9':'#555';x.fillRect(W-8,(s.pr-s.paddle_h/2)*ch,6,s.paddle_h*ch);
document.getElementById('hud').innerHTML=
'<span class=b>'+s.sl+'</span> : <span class=g>'+s.sr+'</span> &nbsp; '+
'difficulty <b>'+s.diff+'</b> (K='+s.K+') &nbsp; '+
'glass intercept <span class=g>'+s.intercept+'%</span> &nbsp; '+
'heading '+s.heading+'° &nbsp; decide '+s.dec_ms+'ms &nbsp; '+
'glass <span class='+(s.glass_on?'g':'r')+'>'+(s.glass_on?'ON':'OFF')+'</span>';}
document.addEventListener('keydown',e=>{let k=null;
if(e.key=='ArrowUp'||e.key=='w')k='UP';else if(e.key=='ArrowDown'||e.key=='s')k='DOWN';
else if(e.key=='g'||e.key=='G')k='G';if(k){e.preventDefault();fetch('/input?key='+k);}});
setInterval(()=>fetch('/state').then(r=>r.json()).then(draw).catch(()=>{}),50);
</script></body></html>"""


class TServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        if self.path == '/':
            self.send_response(200); self.send_header('Content-Type', 'text/html'); self.end_headers()
            self.wfile.write(HTML.encode())
        elif self.path == '/state':
            self.send_response(200); self.send_header('Content-Type', 'application/json'); self.end_headers()
            with game.lock:
                self.wfile.write(json.dumps(game.to_dict()).encode())
        elif self.path.startswith('/input'):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            player_key['k'] = q.get('key', [None])[0]
            self.send_response(200); self.end_headers(); self.wfile.write(b'ok')
        else:
            self.send_response(404); self.end_headers()


if __name__ == '__main__':
    threading.Thread(target=game_loop, daemon=True).start()
    srv = TServer(('127.0.0.1', args.port), H)
    print(f"  ▶ http://localhost:{args.port}/   (difficulty={args.difficulty}, K={K})")
    print("  Glass predicts the bounce by recalling (position, heading) → stored landing.")
    print("  Ctrl-C to stop.\n")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n  stopping...")
        if nco: send('Foff'); nco.close()
        if handle: ps.ps2000_stop(handle); ps.ps2000_close_unit(ct.c_int16(handle))
