#!/usr/bin/env python3
"""
Pong on Glass — Live Game
==========================

Real-time Pong where the glass AI plays right paddle.
Uses trained weights from pong_train.py.

Controls:
  W / Up Arrow   — move paddle up
  S / Down Arrow — move paddle down
  Q / Escape     — quit

Usage:
  python3 tools/pong_live.py --model data/results/pong/pong_model_TIMESTAMP.json
  python3 tools/pong_live.py --model data/results/pong/pong_model_TIMESTAMP.json --simulated
"""

import ctypes as ct
import numpy as np
import json
import time
import argparse
import sys
import threading
from pathlib import Path
from http.server import HTTPServer, SimpleHTTPRequestHandler
from socketserver import ThreadingMixIn
import urllib.parse


class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True

# ─── Args ─────────────────────────────────────────────────────────
parser = argparse.ArgumentParser(description='Pong on Glass — Live Game')
parser.add_argument('--model', type=str, required=True,
                    help='Path to trained model JSON')
parser.add_argument('--nco-port', type=str, default='/dev/cu.usbmodem113401')
parser.add_argument('--simulated', action='store_true',
                    help='Run without hardware (simulated kernel)')
parser.add_argument('--fps', type=float, default=30.0,
                    help='Target frame rate (default: 30 — render/input rate)')
parser.add_argument('--ball-speed', type=int, default=6,
                    help='Frames between ball moves (default: 6 → ~5 cells/sec)')
parser.add_argument('--port', type=int, default=8765,
                    help='Web UI port (default: 8765)')
parser.add_argument('--difficulty', type=str, default='hard',
                    choices=['easy', 'hard', 'adaptive', 'mirror'],
                    help='Glass AI difficulty (default: hard)')
args = parser.parse_args()

# ─── Load Model ──────────────────────────────────────────────────
print("Loading model...")
with open(args.model) as f:
    model = json.load(f)

ENCODING = model.get('encoding', 'singletone')
w = np.array(model['weights'])
bias = model['bias']
MODEL_W = model['config']['court_w']   # 8 — model quantization grid
MODEL_H = model['config']['court_h']

# Visual court is larger than model grid for playability
COURT_W = 16
COURT_H = 12
PADDLE_H = 3  # paddle height in cells

if ENCODING == 'multitone_v2_drivewindow':
    # V2: drive-window readout + quadratic. Glass TRACKS the ball.
    cfg = model['config']
    CH_X, CH_Y, CH_V = cfg['ch_x'], cfg['ch_y'], cfg['ch_v']
    F_X_LO, F_X_HI = cfg['f_x_lo'], cfg['f_x_hi']
    F_Y_LO, F_Y_HI = cfg['f_y_lo'], cfg['f_y_hi']
    F_V_LO, F_V_HI = cfg['f_v_lo'], cfg['f_v_hi']
    WINDOW_OFFSETS = cfg['window_offsets']
    N_WIN = len(WINDOW_OFFSETS)
    USE_QUADRATIC = cfg.get('quadratic', True)
    TARGET_MODE = cfg.get('target', 'track')
    MU = np.array(model['normalization']['mu'])
    SD = np.array(model['normalization']['sd'])
    K = MODEL_W  # nominal "kernel dim" for display = grid
    print(f"  Encoding: multitone v2 (drive-window) — glass {TARGET_MODE}s ball")
    print(f"  Drive channels: x={CH_X}, y={CH_Y}, v={CH_V}")
    print(f"  Features: {N_WIN}×3 windows{' + 6 quad' if USE_QUADRATIC else ''}")
    print(f"  Metrics: {model.get('metrics', {}).get('note', 'n/a')}")
elif ENCODING == 'multitone_v2_selected':
    # V2-selected: features chosen from the FULL census mode pool (incl collisions)
    # by leakage-free top-K selection. Each feature is a drive-window bin OR a
    # fixed census-mode amplitude, described in feature_spec.
    cfg = model['config']
    CH_X, CH_Y, CH_V = cfg['ch_x'], cfg['ch_y'], cfg['ch_v']
    F_X_LO, F_X_HI = cfg['f_x_lo'], cfg['f_x_hi']
    F_Y_LO, F_Y_HI = cfg['f_y_lo'], cfg['f_y_hi']
    F_V_LO, F_V_HI = cfg['f_v_lo'], cfg['f_v_hi']
    WINDOW_OFFSETS = cfg['window_offsets']
    N_WIN = len(WINDOW_OFFSETS)
    TARGET_MODE = cfg.get('target', 'track')
    FEATURE_SPEC = model['feature_spec']
    MU = np.array(model['normalization']['mu'])
    SD = np.array(model['normalization']['sd'])
    K = len(FEATURE_SPEC)
    n_mode = sum(1 for s in FEATURE_SPEC if s['kind'] == 'mode')
    n_win = sum(1 for s in FEATURE_SPEC if s['kind'] == 'window')
    print(f"  Encoding: multitone v2-SELECTED — glass {TARGET_MODE}s ball")
    print(f"  Drive channels: x={CH_X}, y={CH_Y}, v={CH_V}")
    print(f"  Features: {K} selected ({n_win} windows + {n_mode} census modes incl collisions)")
    print(f"  Metrics: {model.get('metrics', {}).get('note', 'n/a')}")
else:
    # V1: single-tone legacy
    mode_freqs = np.array(model['mode_freqs_hz'])
    state_freqs = np.array(model['state_freqs_hz'])
    Y_mean = np.array(model['normalization']['y_mean'])
    Y_std = np.array(model['normalization']['y_std'])
    K = len(mode_freqs)
    TX_CH = model['config']['tx_channel']
    print(f"  Encoding: single-tone (legacy)")
    print(f"  Kernel dim: {K}")
    print(f"  TX channel: {TX_CH}")
print(f"  Court: {COURT_W}x{COURT_H} (model grid: {MODEL_W}x{MODEL_H})")
print(f"  Difficulty: {args.difficulty}")


# ─── Hardware / Constants ─────────────────────────────────────────
PICO_LIB = '/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources/libps2000.dylib'
N_SAMPLES = 8064
TIMEBASE = 7
FS = 781250.0
NFFT = N_SAMPLES * 4
BIN_HZ = FS / NFFT
NYQUIST = FS / 2
RNG = 6
RNG_MV = 1000.0
NAVG = 8 if ENCODING == 'multitone_v2_drivewindow' else 4  # v2 needs more for SNR


# ─── Game State ───────────────────────────────────────────────────
class PongGame:
    def __init__(self):
        self.ball_x = COURT_W // 2
        self.ball_y = COURT_H // 2
        self.ball_vx = 1
        self.ball_vy = 1
        self.paddle_left = COURT_H // 2   # player
        self.paddle_right = COURT_H // 2  # glass AI
        self.score_left = 0
        self.score_right = 0
        self.rallies = 0
        self.glass_intercepts = 0
        self.frame = 0
        self.glass_decision_ms = 0.0
        self.score_flash = 0        # countdown frames for flash animation
        self.score_flash_side = ''  # 'left' or 'right' (who scored)
        self.paused_frames = 0      # pause after score
        # Adaptive mode state
        self.player_history = []  # (state_idx, player_paddle_y)

    def state_index(self):
        """Quantize ball position to 8x8 model grid for state lookup."""
        bx = int(self.ball_x * MODEL_W / COURT_W)
        by = int(self.ball_y * MODEL_H / COURT_H)
        bx = max(0, min(MODEL_W - 1, bx))
        by = max(0, min(MODEL_H - 1, by))
        vx_bit = 0 if self.ball_vx == -1 else 1
        vy_bit = 0 if self.ball_vy == -1 else 1
        return bx * 32 + by * 4 + vx_bit * 2 + vy_bit

    def model_state(self):
        """Current ball state quantized to the model grid (bx, by, vx, vy)."""
        bx = max(0, min(MODEL_W - 1, int(self.ball_x * MODEL_W / COURT_W)))
        by = max(0, min(MODEL_H - 1, int(self.ball_y * MODEL_H / COURT_H)))
        return bx, by, self.ball_vx, self.ball_vy

    def step(self):
        """Advance ball one cell."""
        if self.paused_frames > 0:
            self.paused_frames -= 1
            return

        next_x = self.ball_x + self.ball_vx
        next_y = self.ball_y + self.ball_vy

        # Bounce off top/bottom
        if next_y < 0:
            next_y = -next_y
            self.ball_vy *= -1
        if next_y >= COURT_H:
            next_y = 2 * (COURT_H - 1) - next_y
            self.ball_vy *= -1

        self.ball_x = next_x
        self.ball_y = next_y

        # Left wall: player paddle
        if self.ball_x < 0:
            half_paddle = PADDLE_H // 2
            if abs(self.ball_y - self.paddle_left) <= half_paddle:
                self.ball_vx = 1
                self.ball_x = 0
                self.rallies += 1
            else:
                self.score_right += 1
                self._score_event('right')

        # Right wall: glass paddle
        if self.ball_x >= COURT_W:
            half_paddle = PADDLE_H // 2
            if abs(self.ball_y - self.paddle_right) <= half_paddle:
                self.ball_vx = -1
                self.ball_x = COURT_W - 1
                self.rallies += 1
                self.glass_intercepts += 1
            else:
                self.score_left += 1
                self._score_event('left')

    def _score_event(self, side):
        """Trigger score animation and reset ball."""
        self.score_flash = 20       # 20 ball-steps of flash
        self.score_flash_side = side
        self.paused_frames = 8      # pause before ball resumes
        self.ball_x = COURT_W // 2
        self.ball_y = COURT_H // 2
        self.ball_vx = 1 if np.random.rand() > 0.5 else -1
        self.ball_vy = 1 if np.random.rand() > 0.5 else -1

    def to_dict(self):
        intercept_rate = (self.glass_intercepts / max(self.rallies, 1)) * 100
        if self.score_flash > 0:
            self.score_flash -= 1
        return {
            'ball_x': self.ball_x, 'ball_y': self.ball_y,
            'ball_vx': self.ball_vx, 'ball_vy': self.ball_vy,
            'paddle_left': self.paddle_left,
            'paddle_right': self.paddle_right,
            'score_left': self.score_left,
            'score_right': self.score_right,
            'frame': self.frame,
            'glass_decision_ms': round(self.glass_decision_ms, 1),
            'kernel_dim': K,
            'intercept_rate': round(intercept_rate, 0),
            'difficulty': args.difficulty,
            'score_flash': self.score_flash,
            'score_flash_side': self.score_flash_side,
            'court_w': COURT_W, 'court_h': COURT_H,
            'paddle_h': PADDLE_H,
            'glass_enabled': glass_enabled,
        }


# ─── Glass AI ────────────────────────────────────────────────────
handle = None
nco_ser = None

if not args.simulated:
    import serial
    print("Initializing hardware...")
    ps = ct.CDLL(PICO_LIB)
    ps.ps2000_open_unit.restype = ct.c_int16
    handle = ps.ps2000_open_unit()
    if handle <= 0:
        print(f"ERROR: PicoScope failed (handle={handle})")
        sys.exit(1)
    ps.ps2000_set_channel(handle, 0, 1, 0, RNG)
    ps.ps2000_set_channel(handle, 1, 0, 0, RNG)
    ps.ps2000_set_trigger(handle, 5, 0, 0, 0, 0)
    nco_ser = serial.Serial(args.nco_port, 115200, timeout=2)
    time.sleep(0.5)
    nco_ser.reset_input_buffer()
    print(f"  PicoScope: handle={handle}")
    print(f"  NCO: {args.nco_port}")


def _capture_spectrum(navg):
    """Capture averaged magnitude spectrum from PicoScope."""
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
        ps.ps2000_get_values(handle, ct.byref(buf), None, None, None,
                             ct.byref(ov), N_SAMPLES)
        d = np.array(buf[:], dtype=np.float64) * (RNG_MV / 32767.0)
        d -= d.mean()
        mags.append(np.abs(np.fft.rfft(d * np.hanning(N_SAMPLES), n=NFFT)))
    return np.mean(mags, axis=0) if mags else np.zeros(NFFT // 2 + 1)


def _encode_v2(bx, by, vx, vy):
    """Map model-grid state to 3 drive frequencies (must match training)."""
    f1 = F_X_LO + bx * (F_X_HI - F_X_LO) / (MODEL_W - 1)
    f2 = F_Y_LO + by * (F_Y_HI - F_Y_LO) / (MODEL_H - 1)
    vq = (1 if vx == 1 else 0) * 2 + (1 if vy == 1 else 0)
    f3 = F_V_LO + vq * (F_V_HI - F_V_LO) / 3
    return f1, f2, f3


def _extract_v2_features(spectrum, f1, f2, f3):
    """Drive-window readout + quadratic cross-products (must match training)."""
    phys = np.zeros(3 * N_WIN)
    for di, fd in enumerate((f1, f2, f3)):
        base = int(round(fd / BIN_HZ))
        for wi, off in enumerate(WINDOW_OFFSETS):
            b = base + off
            phys[di*N_WIN + wi] = float(spectrum[max(0,b-1):b+2].max()) if 0 <= b < len(spectrum) else 0.0
    ds = np.array([phys[di*N_WIN:(di+1)*N_WIN].max() for di in range(3)])
    if USE_QUADRATIC:
        cross = np.array([ds[0]*ds[1], ds[0]*ds[2], ds[1]*ds[2],
                          ds[0]**2, ds[1]**2, ds[2]**2])
        return np.concatenate([phys, cross])
    return phys


# ─── Live Spectrum (proof the glass is doing the work) ───────────
SPEC_LO_HZ = 30000
SPEC_HI_HZ = 150000
SPEC_POINTS = 480
latest_spectrum = {'freqs_khz': [], 'mags': [], 'drives_khz': [], 'peak': 1.0, 'source': 'init'}


def _synth_spectrum(f1, f2, f3):
    """Synthetic spectrum for simulated mode (fixed plate resonances + drive peaks)."""
    n = NFFT // 2 + 1
    freqs = np.arange(n) * BIN_HZ
    spec = np.random.rand(n) * 40 + 110  # noise floor
    for rf in (34500, 48000, 55000, 62500, 79500, 87000, 96000, 119000, 143500):
        spec += (350 + np.random.rand() * 150) / (1 + ((freqs - rf) / 300) ** 2)
    for fd in (f1, f2, f3):  # strong response at driven frequencies
        spec += 850 / (1 + ((freqs - fd) / 150) ** 2)
    return spec


def _store_spectrum(spectrum, f1, f2, f3, source):
    """Downsample spectrum to the working band for the live chart."""
    lo = int(SPEC_LO_HZ / BIN_HZ)
    hi = min(len(spectrum), int(SPEC_HI_HZ / BIN_HZ))
    band = spectrum[lo:hi]
    n = len(band)
    if n == 0:
        return
    group = max(1, n // SPEC_POINTS)
    freqs_khz, mags = [], []
    for i in range(0, n, group):
        chunk = band[i:i+group]
        mags.append(float(chunk.max()))
        freqs_khz.append(round((lo + i) * BIN_HZ / 1000.0, 2))
    latest_spectrum['freqs_khz'] = freqs_khz
    latest_spectrum['mags'] = mags
    latest_spectrum['drives_khz'] = [round(f1/1000, 2), round(f2/1000, 2), round(f3/1000, 2)]
    latest_spectrum['peak'] = max(mags) if mags else 1.0
    latest_spectrum['source'] = source


def glass_infer_v2(bx, by, vx, vy):
    """Glass tracks the ball: drive 3 tones, read paddle position."""
    f1, f2, f3 = _encode_v2(bx, by, vx, vy)
    if args.simulated:
        spectrum = _synth_spectrum(f1, f2, f3)
        feats = _extract_v2_features(spectrum, f1, f2, f3)
        _store_spectrum(spectrum, f1, f2, f3, 'simulated')
    else:
        nco_ser.reset_input_buffer()
        nco_ser.write(f'{CH_X}:{int(f1)}\n'.encode()); time.sleep(0.012)
        nco_ser.write(f'{CH_Y}:{int(f2)}\n'.encode()); time.sleep(0.012)
        nco_ser.write(f'{CH_V}:{int(f3)}\n'.encode()); time.sleep(0.012)
        spectrum = _capture_spectrum(NAVG)
        feats = _extract_v2_features(spectrum, f1, f2, f3)
        _store_spectrum(spectrum, f1, f2, f3, 'glass')
    feats_n = (feats - MU) / SD
    paddle_model = float(w @ feats_n + bias) * (MODEL_H - 1)
    paddle = paddle_model * (COURT_H - 1) / (MODEL_H - 1)
    if args.difficulty == 'easy':
        paddle += np.random.randn() * 3.0
    return np.clip(paddle, 0, COURT_H - 1)


def _extract_selected_features(spectrum, f1, f2, f3):
    """Extract features per FEATURE_SPEC (windows + census modes)."""
    drive_f = (f1, f2, f3)
    feats = np.zeros(len(FEATURE_SPEC))
    for i, spec in enumerate(FEATURE_SPEC):
        if spec['kind'] == 'window':
            base = int(round(drive_f[spec['drive']] / BIN_HZ)) + spec['offset']
            feats[i] = float(spectrum[max(0, base-1):base+2].max()) if 0 <= base < len(spectrum) else 0.0
        else:  # mode: fixed-frequency amplitude (search ±2 bins)
            b = int(round(spec['freq_hz'] / BIN_HZ))
            feats[i] = float(spectrum[max(0, b-2):min(len(spectrum), b+3)].max())
    return feats


def glass_infer_v2_selected(bx, by, vx, vy):
    """Glass tracks the ball using features selected from the full mode pool."""
    f1, f2, f3 = _encode_v2(bx, by, vx, vy)
    if args.simulated:
        spectrum = _synth_spectrum(f1, f2, f3)
        _store_spectrum(spectrum, f1, f2, f3, 'simulated')
    else:
        nco_ser.reset_input_buffer()
        nco_ser.write(f'{CH_X}:{int(f1)}\n'.encode()); time.sleep(0.012)
        nco_ser.write(f'{CH_Y}:{int(f2)}\n'.encode()); time.sleep(0.012)
        nco_ser.write(f'{CH_V}:{int(f3)}\n'.encode()); time.sleep(0.012)
        spectrum = _capture_spectrum(NAVG)
        _store_spectrum(spectrum, f1, f2, f3, 'glass')
    feats = _extract_selected_features(spectrum, f1, f2, f3)
    feats_n = (feats - MU) / SD
    paddle_model = float(w @ feats_n + bias) * (MODEL_H - 1)
    paddle = paddle_model * (COURT_H - 1) / (MODEL_H - 1)
    if args.difficulty == 'easy':
        paddle += np.random.randn() * 3.0
    return np.clip(paddle, 0, COURT_H - 1)


def glass_infer(state_idx):
    """Query the glass and return paddle_y prediction (single-tone legacy)."""
    drive_freq = int(state_freqs[state_idx])

    if args.simulated:
        # Simulate kernel response
        gradient = np.zeros(K)
        for m, mode_freq in enumerate(mode_freqs):
            delta = abs(drive_freq - mode_freq)
            bw = mode_freq / 200
            gradient[m] = 1.0 / (1.0 + (2 * delta / bw) ** 2)
        gradient += np.random.randn(K) * 0.05
    else:
        # Real hardware query
        nco_ser.reset_input_buffer()
        nco_ser.write(f'{TX_CH}:{drive_freq}\n'.encode())
        time.sleep(0.02)
        spectrum = _capture_spectrum(NAVG)

        # Extract mode amplitudes
        gradient = np.zeros(K)
        for m, freq in enumerate(mode_freqs):
            bin_idx = int(round(freq / BIN_HZ))
            lo = max(0, bin_idx - 3)
            hi = min(len(spectrum), bin_idx + 4)
            gradient[m] = float(spectrum[lo:hi].max())

    # Normalize using training stats
    gradient_norm = (gradient - Y_mean) / Y_std

    # Apply readout weights — model outputs in model grid (0 to MODEL_H-1)
    paddle_pred_model = float(w @ gradient_norm + bias) * (MODEL_H - 1)
    # Scale to visual court
    paddle_pred = paddle_pred_model * (COURT_H - 1) / (MODEL_H - 1)

    # Apply difficulty
    if args.difficulty == 'easy':
        paddle_pred += np.random.randn() * 3.0
    elif args.difficulty == 'adaptive':
        pass  # future: use learned player model
    elif args.difficulty == 'mirror':
        pass  # future: predict player instead

    return np.clip(paddle_pred, 0, COURT_H - 1)


# ─── Web UI ──────────────────────────────────────────────────────
game = PongGame()
player_input = {'key': None}
glass_enabled = True
game_running = True

CANVAS_W = COURT_W * 40
CANVAS_H = COURT_H * 40

HTML_PAGE = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>PONG ON GLASS</title>
<style>
  body {{ background: #111; color: #0f0; font-family: monospace; text-align: center; margin: 0; padding: 20px; }}
  h1 {{ color: #0f0; font-size: 24px; margin-bottom: 5px; }}
  .subtitle {{ color: #0a0; font-size: 12px; margin-bottom: 20px; }}
  canvas {{ border: 2px solid #0f0; display: block; margin: 0 auto; background: #111; }}
  .stats {{ color: #0a0; font-size: 14px; margin-top: 15px; }}
  .score {{ font-size: 48px; color: #0f0; margin: 10px 0; }}
  .score .flash {{ animation: pulse 0.3s ease-out; }}
  @keyframes pulse {{ 0% {{ transform: scale(1.5); color: #fff; }} 100% {{ transform: scale(1); color: #0f0; }} }}
  .controls {{ color: #080; font-size: 12px; margin-top: 10px; }}
</style></head><body>
<h1>PONG ON GLASS</h1>
<div class="subtitle">CWM Level 3 Kernel Demo - Your opponent is {K}-dimensional glass</div>
<div class="score"><span id="sl">0</span> : <span id="sr">0</span></div>
<div id="glass-status" style="font-size:14px;margin:5px 0;color:#0f0;">GLASS: ON</div>
<canvas id="c" width="{CANVAS_W}" height="{CANVAS_H}"></canvas>
<div class="stats">
  <span id="stats">Kernel: {K} dims | Decision: -- ms | Intercept: --%</span>
</div>
<canvas id="spec" width="480" height="150" style="margin-top:14px; border-color:#063;"></canvas>
<div id="spec-label" style="color:#0a0; font-size:11px; margin-top:4px;">
  LIVE GLASS SPECTRUM &mdash; <span style="color:#0ff">x</span>/<span style="color:#f80">y</span>/<span style="color:#f0f">v</span> drive tones encode the current ball state. Watch the peaks move as you play.
</div>
<div class="controls">W/S or Up/Down to move | G to toggle glass | Q to quit</div>
<script>
const CW={CANVAS_W}, CH={CANVAS_H};
const canvas=document.getElementById('c'), ctx=canvas.getContext('2d');
let prevScoreL=0, prevScoreR=0;

function draw(s) {{
  const W=s.court_w, H=s.court_h, PH=s.paddle_h;
  const CELLW=CW/W, CELLH=CH/H;

  // Score flash overlay
  if(s.score_flash > 0) {{
    let alpha = s.score_flash / 20.0 * 0.4;
    if(s.score_flash_side==='left') {{
      ctx.fillStyle=`rgba(0,255,255,${{alpha}})`;
    }} else {{
      ctx.fillStyle=`rgba(255,136,0,${{alpha}})`;
    }}
    ctx.fillRect(0,0,CW,CH);
  }} else {{
    ctx.fillStyle='#111'; ctx.fillRect(0,0,CW,CH);
  }}

  // Center line (dashed)
  ctx.strokeStyle='#333'; ctx.lineWidth=2; ctx.setLineDash([8,8]);
  ctx.beginPath(); ctx.moveTo(CW/2,0); ctx.lineTo(CW/2,CH); ctx.stroke();
  ctx.setLineDash([]);

  // Ball
  let ballColor = '#0f0';
  if(s.score_flash > 15) ballColor = '#fff';  // flash white on score
  ctx.fillStyle=ballColor;
  ctx.shadowColor=ballColor; ctx.shadowBlur=12;
  ctx.beginPath(); ctx.arc(s.ball_x*CELLW+CELLW/2, s.ball_y*CELLH+CELLH/2, CELLW/3, 0, Math.PI*2); ctx.fill();
  ctx.shadowBlur=0;

  // Paddles
  const padW=10, halfPad=PH/2;
  ctx.fillStyle='#0ff';
  ctx.fillRect(4, (s.paddle_left-halfPad)*CELLH, padW, PH*CELLH);
  ctx.fillStyle='#f80';
  ctx.fillRect(CW-14, (s.paddle_right-halfPad)*CELLH, padW, PH*CELLH);

  // Score update with flash class
  let slEl = document.getElementById('sl');
  let srEl = document.getElementById('sr');
  if(s.score_left !== prevScoreL) {{ slEl.className='flash'; setTimeout(()=>slEl.className='',300); prevScoreL=s.score_left; }}
  if(s.score_right !== prevScoreR) {{ srEl.className='flash'; setTimeout(()=>srEl.className='',300); prevScoreR=s.score_right; }}
  slEl.textContent=s.score_left;
  srEl.textContent=s.score_right;
  document.getElementById('stats').textContent=
    `Kernel: ${{s.kernel_dim}} dims | Decision: ${{s.glass_decision_ms}} ms | Intercept: ${{s.intercept_rate}}% | Frame: ${{s.frame}}`;
  let gs = document.getElementById('glass-status');
  if(s.glass_enabled) {{ gs.textContent='GLASS: ON'; gs.style.color='#0f0'; }}
  else {{ gs.textContent='GLASS: OFF (random)'; gs.style.color='#f44'; }}
}}

document.addEventListener('keydown', e => {{
  let key=null;
  if(e.key==='w'||e.key==='ArrowUp') key='UP';
  if(e.key==='s'||e.key==='ArrowDown') key='DOWN';
  if(e.key==='g') key='TOGGLE_GLASS';
  if(e.key==='q'||e.key==='Escape') key='QUIT';
  if(key) {{ e.preventDefault(); fetch('/input?key='+key); }}
}});

setInterval(()=>{{
  fetch('/state').then(r=>r.json()).then(draw).catch(()=>{{}});
}}, 33);

// ── Live spectrum chart (proof the glass is computing) ──
const specCanvas=document.getElementById('spec'), sctx=specCanvas.getContext('2d');
const SW=480, SH=150;
function drawSpec(d) {{
  sctx.fillStyle='#0a0a0a'; sctx.fillRect(0,0,SW,SH);
  if(!d.mags || d.mags.length===0) return;
  const n=d.mags.length, peak=d.peak||1;
  const loF=d.freqs_khz[0], hiF=d.freqs_khz[n-1];
  const fx = fk => (fk-loF)/(hiF-loF)*SW;
  const isGlass = d.source==='glass';
  // spectrum trace
  sctx.strokeStyle = isGlass ? '#0f0' : '#7a4';
  sctx.lineWidth=1.5; sctx.beginPath();
  for(let i=0;i<n;i++) {{
    const x=fx(d.freqs_khz[i]);
    const y=SH-(d.mags[i]/peak)*(SH-12)-2;
    if(i===0) sctx.moveTo(x,y); else sctx.lineTo(x,y);
  }}
  sctx.stroke();
  sctx.lineTo(SW,SH); sctx.lineTo(0,SH); sctx.closePath();
  sctx.fillStyle = isGlass ? 'rgba(0,255,0,0.12)' : 'rgba(120,160,60,0.10)';
  sctx.fill();
  // drive-tone markers
  const colors=['#0ff','#f80','#f0f'], labels=['x','y','v'];
  for(let k=0;k<d.drives_khz.length;k++) {{
    const x=fx(d.drives_khz[k]);
    sctx.strokeStyle=colors[k]; sctx.lineWidth=2; sctx.setLineDash([4,3]);
    sctx.beginPath(); sctx.moveTo(x,0); sctx.lineTo(x,SH); sctx.stroke();
    sctx.setLineDash([]);
    sctx.fillStyle=colors[k]; sctx.font='10px monospace';
    sctx.fillText(labels[k]+' '+d.drives_khz[k].toFixed(0)+'k', Math.min(Math.max(x+2,2),SW-46), 11+k*12);
  }}
  // band labels + source tag
  sctx.fillStyle='#063'; sctx.font='9px monospace';
  sctx.fillText(loF.toFixed(0)+' kHz',2,SH-3);
  sctx.fillText(hiF.toFixed(0)+' kHz',SW-46,SH-3);
  sctx.fillStyle=isGlass?'#0f0':'#a83'; sctx.font='9px monospace';
  sctx.fillText(isGlass?'● PHYSICAL GLASS':'● simulated',SW/2-40,SH-3);
}}
setInterval(()=>{{
  fetch('/spectrum').then(r=>r.json()).then(drawSpec).catch(()=>{{}});
}}, 120);
</script></body></html>"""


class GameHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode())
        elif self.path == '/state':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(game.to_dict()).encode())
        elif self.path == '/spectrum':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(latest_spectrum).encode())
        elif self.path.startswith('/input'):
            params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            key = params.get('key', [None])[0]
            if key:
                player_input['key'] = key
            self.send_response(200)
            self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *a):
        pass  # suppress request logging


# ─── Main Game Loop ──────────────────────────────────────────────
print(f"\n  Starting game server on http://localhost:{args.port}")
print(f"  Open in browser to play!")
print(f"  Press Ctrl+C to quit.\n")

server = ThreadingHTTPServer(('', args.port), GameHandler)
server_thread = threading.Thread(target=server.serve_forever, daemon=True)
server_thread.start()

frame_time = 1.0 / args.fps

try:
    while game_running:
        t0 = time.time()
        game.frame += 1

        # Player input
        key = player_input.get('key')
        player_input['key'] = None
        if key == 'UP' and game.paddle_left > PADDLE_H // 2:
            game.paddle_left -= 1
        elif key == 'DOWN' and game.paddle_left < COURT_H - 1 - PADDLE_H // 2:
            game.paddle_left += 1
        elif key == 'TOGGLE_GLASS':
            glass_enabled = not glass_enabled
            print(f"  Glass {'ON' if glass_enabled else 'OFF'}")
        elif key == 'QUIT':
            break

        # Step ball only every N frames (decouple speed from render rate)
        ball_moved = (game.frame % args.ball_speed == 0)

        # Glass AI decision only when ball moves (prevents jitter)
        if ball_moved:
            if glass_enabled:
                t_glass = time.time()
                if ENCODING == 'multitone_v2_drivewindow':
                    paddle_target = glass_infer_v2(*game.model_state())
                elif ENCODING == 'multitone_v2_selected':
                    paddle_target = glass_infer_v2_selected(*game.model_state())
                else:
                    paddle_target = glass_infer(game.state_index())
                game.glass_decision_ms = (time.time() - t_glass) * 1000
            else:
                # Glass OFF: random drift (clearly worse)
                game.glass_decision_ms = 0.0
                paddle_target = game.paddle_right + np.random.choice([-1, 0, 0, 1])
                paddle_target = float(paddle_target)

            game.paddle_right = int(round(paddle_target))
            game.paddle_right = max(PADDLE_H // 2, min(COURT_H - 1 - PADDLE_H // 2, game.paddle_right))

            # Record for adaptive mode
            game.player_history.append((game.state_index(), game.paddle_left))

            game.step()

        # Frame pacing
        elapsed = time.time() - t0
        sleep_time = frame_time - elapsed
        if sleep_time > 0:
            time.sleep(sleep_time)

        # Console status every 100 frames
        if game.frame % 100 == 0:
            intercept_pct = game.glass_intercepts / max(game.rallies, 1) * 100
            print(f"  Frame {game.frame}: score {game.score_left}-{game.score_right}, "
                  f"glass intercepts {intercept_pct:.0f}%, "
                  f"decision {game.glass_decision_ms:.1f}ms")

except KeyboardInterrupt:
    print("\n  Game stopped.")

finally:
    if handle and not args.simulated:
        nco_ser.write(b'Foff\n')
        time.sleep(0.05)
        nco_ser.close()
        ps.ps2000_stop(handle)
        ps.ps2000_close_unit(ct.c_int16(handle))
    server.shutdown()

# Final stats
intercept_pct = game.glass_intercepts / max(game.rallies, 1) * 100
print(f"\n  FINAL: {game.frame} frames, score {game.score_left}-{game.score_right}")
print(f"  Glass intercept rate: {intercept_pct:.0f}%")
print(f"  Avg decision time: {game.glass_decision_ms:.1f} ms")
