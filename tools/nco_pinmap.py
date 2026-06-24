#!/usr/bin/env python3
"""
NCO PIN MAP — color-coded Raspberry Pi Pico pinout for the maxed CWM firmware
=============================================================================
Renders a scale, color-coded SVG (+ HTML print wrapper) of the Pico header so
you can see at a glance which plate / TX connects to which pin, grouped by the
three phase-coherent blocks of firmware v2.0 (tools/pico_nco/main.py):

  Block A = PIO0 SM0-3  → CH1-4  → GP2,3,4,5   (pins 4,5,6,7)   — 4 phase-locked
  Block B = PIO1 SM0-3  → CH5-8  → GP6,7,8,9   (pins 9,10,11,12)— 4 phase-locked
  Block C = PWM s0-3,5-7→ CH9-15 → GP16,18,20,22,10,12,14       — 7 independent

Each PIO block holds up to 4 TX in phase = one big multipoint/interference
plate. The PWM block = independent tones for simple single/dual-TX plates.

Usage:  python3 tools/nco_pinmap.py     → companion/nco_pinmap.svg + .html
"""
from pathlib import Path

OUT = Path('companion/nco_pinmap')

# ── Colors ──────────────────────────────────────────────────────────────────
A = '#c81e3a'      # Block A (PIO0)
B = '#1769aa'      # Block B (PIO1)
C = '#1b8a3a'      # Block C (PWM)
GND = '#5a5a5a'
PWR = '#d98300'
FREE = '#b9b9b9'   # unused GPIO
SPECIAL = '#8a6d3b'

# ── Pin table: pin# -> (label, sublabel, color, group) ──────────────────────
# group: 'A','B','C' = a TX channel; '' = not a drive pin.
PINS = {
    1:  ('GP0',  'free',        FREE, ''),
    2:  ('GP1',  'free',        FREE, ''),
    3:  ('GND',  'return',      GND,  ''),
    4:  ('GP2',  'CH1',         A,    'A'),
    5:  ('GP3',  'CH2',         A,    'A'),
    6:  ('GP4',  'CH3',         A,    'A'),
    7:  ('GP5',  'CH4',         A,    'A'),
    8:  ('GND',  'return',      GND,  ''),
    9:  ('GP6',  'CH5',         B,    'B'),
    10: ('GP7',  'CH6',         B,    'B'),
    11: ('GP8',  'CH7',         B,    'B'),
    12: ('GP9',  'CH8',         B,    'B'),
    13: ('GND',  'return',      GND,  ''),
    14: ('GP10', 'CH13',        C,    'C'),
    15: ('GP11', 'free',        FREE, ''),
    16: ('GP12', 'CH14',        C,    'C'),
    17: ('GP13', 'free',        FREE, ''),
    18: ('GND',  'return',      GND,  ''),
    19: ('GP14', 'CH15',        C,    'C'),
    20: ('GP15', 'free',        FREE, ''),
    21: ('GP16', 'CH9',         C,    'C'),
    22: ('GP17', 'free',        FREE, ''),
    23: ('GND',  'return',      GND,  ''),
    24: ('GP18', 'CH10',        C,    'C'),
    25: ('GP19', 'free',        FREE, ''),
    26: ('GP20', 'CH11',        C,    'C'),
    27: ('GP21', 'free',        FREE, ''),
    28: ('GND',  'return',      GND,  ''),
    29: ('GP22', 'CH12',        C,    'C'),
    30: ('RUN',  '',            SPECIAL, ''),
    31: ('GP26', 'free·ADC0',   FREE, ''),
    32: ('GP27', 'free·ADC1',   FREE, ''),
    33: ('GND',  'return',      GND,  ''),
    34: ('GP28', 'free·ADC2',   FREE, ''),
    35: ('VREF', '',            SPECIAL, ''),
    36: ('3V3',  'out',         PWR,  ''),
    37: ('3V3_EN', '',          SPECIAL, ''),
    38: ('GND',  'return',      GND,  ''),
    39: ('VSYS', '',            PWR,  ''),
    40: ('VBUS', '5V',          PWR,  ''),
}

# ── Geometry (mm, A4 portrait) ──────────────────────────────────────────────
Wmm, Hmm = 210.0, 297.0
ROW = 10.4
TOP = 84.0                      # y of first pin row center
BOARD_W = 34.0
BOARD_X = (Wmm - BOARD_W) / 2   # board left edge
PILL_W = 58.0
PILL_H = 8.6
svg = []
svg.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{Wmm}mm" height="{Hmm}mm" viewBox="0 0 {Wmm} {Hmm}">')
svg.append(f'<rect width="{Wmm}" height="{Hmm}" fill="white"/>')

# Title
svg.append(f'<text x="{Wmm/2}" y="13" font-size="6.2" font-weight="bold" text-anchor="middle" '
           f'font-family="sans-serif">CWM NCO — Pico pin map (firmware v2.0, 15 tones)</text>')
svg.append(f'<text x="{Wmm/2}" y="20.5" font-size="3.4" text-anchor="middle" fill="#555" '
           f'font-family="sans-serif">2 large plates (4 TX phase-locked each, Blocks A/B) + 7 small plates (1 TX each, varied mass, Block C) · every TX via its own 220 Ω → PZT, twisted GND return</text>')

# ── Legend ──────────────────────────────────────────────────────────────────
def chip(x, y, color, title, sub):
    s = f'<rect x="{x}" y="{y}" width="6" height="6" rx="1" fill="{color}"/>'
    s += f'<text x="{x+8}" y="{y+2.7}" font-size="3.5" font-weight="bold" font-family="sans-serif">{title}</text>'
    s += f'<text x="{x+8}" y="{y+6.4}" font-size="2.9" fill="#555" font-family="sans-serif">{sub}</text>'
    return s

ly = 26
svg.append(chip(10, ly, A, 'Block A · LARGE plate 1 · CH1-4',
                'pins 4,5,6,7 — 4 TX phase-locked (PH1-4) · cancellation / path-integral'))
svg.append(chip(10, ly + 9, B, 'Block B · LARGE plate 2 · CH5-8',
                'pins 9,10,11,12 — 4 TX phase-locked (PH5-8) · 2nd parallel propagator'))
svg.append(chip(10, ly + 18, C, 'Block C · 7 SMALL plates · CH9-15',
                'pins 21,24,26,29,14,16,19 — 1 TX each, varied geometry + mass (kernel breadth)'))
svg.append(chip(118, ly, GND, 'GND', 'PZT return; pair with the nearest TX as a twisted lead'))
svg.append(chip(118, ly + 9, PWR, '3V3 / VSYS / VBUS', 'power — do NOT drive a PZT from these'))
svg.append(chip(118, ly + 18, FREE, 'free GPIO', 'spare (slice B-channels / ADC) — not used by firmware'))

# ── Pico board ──────────────────────────────────────────────────────────────
board_top = TOP - ROW * 0.7
board_bot = TOP + ROW * 19 + ROW * 0.7
svg.append(f'<rect x="{BOARD_X}" y="{board_top}" width="{BOARD_W}" height="{board_bot-board_top}" '
           f'rx="3" fill="#0d4d2b" stroke="#063019" stroke-width="0.5"/>')
# USB shield at top
svg.append(f'<rect x="{Wmm/2-7}" y="{board_top-5.5}" width="14" height="6" rx="1.2" fill="#9aa0a6"/>')
svg.append(f'<text x="{Wmm/2}" y="{board_top+ (board_bot-board_top)/2}" font-size="4.2" fill="#bfe9cf" '
           f'text-anchor="middle" font-family="sans-serif" transform="rotate(-90 {Wmm/2} {board_top+(board_bot-board_top)/2})">Raspberry Pi Pico</text>')


def pill(cx_outer, y, side, pinno, label, sub, color, group):
    """Draw a pin pill. side='L' extends left, 'R' extends right."""
    g = []
    # solder pad on the board edge
    padx = BOARD_X if side == 'L' else BOARD_X + BOARD_W
    g.append(f'<circle cx="{padx}" cy="{y}" r="1.5" fill="#e8c558" stroke="#7a5b00" stroke-width="0.3"/>')
    # pill rectangle
    if side == 'L':
        px = padx - 3 - PILL_W
        lead_x1, lead_x2 = padx, padx - 3
    else:
        px = padx + 3
        lead_x1, lead_x2 = padx, padx + 3
    g.append(f'<line x1="{lead_x1}" y1="{y}" x2="{lead_x2}" y2="{y}" stroke="{color}" stroke-width="1.1"/>')
    strong = group in ('A', 'B', 'C')
    fill = color if strong else 'white'
    op = 1.0 if strong else 1.0
    txtcol = 'white' if strong else '#333'
    g.append(f'<rect x="{px}" y="{y-PILL_H/2}" width="{PILL_W}" height="{PILL_H}" rx="1.6" '
             f'fill="{fill}" fill-opacity="{op}" stroke="{color}" stroke-width="0.6"/>')
    # pin number bubble (always near the board)
    bx = px + PILL_W - 4 if side == 'L' else px + 4
    g.append(f'<circle cx="{bx}" cy="{y}" r="2.7" fill="white" stroke="{color}" stroke-width="0.5"/>')
    g.append(f'<text x="{bx}" y="{y+1.1}" font-size="2.8" text-anchor="middle" font-family="sans-serif" fill="#333">{pinno}</text>')
    # labels
    if side == 'L':
        tx = px + 6
        anchor = 'start'
    else:
        tx = px + PILL_W - 6
        anchor = 'end'
    big = f'{label}'
    if strong:
        big = f'{sub} · {label}'        # e.g. "CH1 · GP2"
    g.append(f'<text x="{tx}" y="{y-0.4}" font-size="3.2" font-weight="bold" text-anchor="{anchor}" '
             f'font-family="sans-serif" fill="{txtcol}">{big}</text>')
    smalltxt = '' if strong else sub
    if smalltxt:
        g.append(f'<text x="{tx}" y="{y+3.1}" font-size="2.4" text-anchor="{anchor}" '
                 f'font-family="sans-serif" fill="#666">{smalltxt}</text>')
    return "".join(g)


# left column pins 1..20 (top to bottom)
for i in range(20):
    pinno = i + 1
    y = TOP + i * ROW
    label, sub, color, group = PINS[pinno]
    svg.append(pill(BOARD_X, y, 'L', pinno, label, sub, color, group))

# right column pins 40..21 (top to bottom: pin 40 at top)
for i in range(20):
    pinno = 40 - i
    y = TOP + i * ROW
    label, sub, color, group = PINS[pinno]
    svg.append(pill(BOARD_X + BOARD_W, y, 'R', pinno, label, sub, color, group))

# ── Grouping brackets for the two phase-locked plates (left side) ───────────
def bracket(y0, y1, color, text):
    x = BOARD_X - 3 - PILL_W - 3
    s = f'<path d="M {x} {y0} q -3 0 -3 3 L {x-3} {y1-3} q 0 3 3 3" fill="none" stroke="{color}" stroke-width="0.8"/>'
    ymid = (y0 + y1) / 2
    s += (f'<text x="{x-5}" y="{ymid}" font-size="3.0" font-weight="bold" fill="{color}" '
          f'text-anchor="middle" font-family="sans-serif" transform="rotate(-90 {x-5} {ymid})">{text}</text>')
    return s

svg.append(bracket(TOP + 3 * ROW - PILL_H/2, TOP + 6 * ROW + PILL_H/2, A, 'LARGE PLATE 1 · 4 TX'))
svg.append(bracket(TOP + 8 * ROW - PILL_H/2, TOP + 11 * ROW + PILL_H/2, B, 'LARGE PLATE 2 · 4 TX'))

# ── Footer wiring notes ─────────────────────────────────────────────────────
fy = board_bot + 8
notes = [
    ('Wiring per TX:', 'NCO pin → 220 Ω → PZT hot leg; PZT other leg → nearest GND pin. Keep every TX lead short.'),
    ('Twist the return:', 'each TX hot wire twisted with a GND return — kills the radiated EMI that cost 8–260× SNR. NO TX buffer (direct drive is amplitude-matched).'),
    ('Large plates (A,B):', '4 TX at modal positions: corners + (50,28),(50,72),(72,50) mm (see pzt_placement). Same freq, sweep PH1-4 / PH5-8 → 4-path interference + 99.5% null.'),
    ('Small plates (C):', 'CH9→sm1(p21) CH10→sm2(p24) CH11→sm3(p26) CH12→sm4(p29) CH13→sm5(p14) CH14→sm6(p16) CH15→sm7(p19). 1 TX each, UNIQUE geometry+mass (band offset ≥10%).'),
    ('Readout:', 'one RX pickup per plate → parallel → ×11 preamp → Ch A. Tap the 4K7-summed drive bus → Ch B = phase reference for cancellation.'),
    ('After wiring:', 'run direct_wire_census.py per plate (solo) → catalogs/ → re-run array_design.py on the real combs.'),
]
for k, (h, t) in enumerate(notes):
    yy = fy + k * 5.0
    svg.append(f'<text x="12" y="{yy}" font-size="3.0" font-weight="bold" font-family="sans-serif" fill="#222">{h}</text>')
    svg.append(f'<text x="44" y="{yy}" font-size="3.0" font-family="sans-serif" fill="#444">{t}</text>')

svg.append('</svg>')
svg_text = "\n".join(svg)

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.with_suffix('.svg').write_text(svg_text)

html = f"""<!doctype html><html><head><meta charset="utf-8"><title>CWM NCO pin map</title>
<style>@page{{size:A4 portrait;margin:6mm}}body{{margin:0;padding:6mm;font-family:system-ui,sans-serif}}
.bar{{background:#eef6ff;border:1px solid #cfe2ff;padding:6px 12px;border-radius:6px;margin-bottom:6px;font-size:13px}}
button{{font-size:14px;padding:5px 13px;border-radius:6px;border:1px solid #888;background:#f5f5f5;cursor:pointer}}
@media print{{.noprint{{display:none}}body{{padding:0}}}}</style></head><body>
<div class="bar noprint">Color-coded Pico pin map for NCO firmware v2.0 (15 tones, 3 phase-coherent blocks).
&nbsp;<button onclick="window.print()">Print</button></div>
{svg_text}
</body></html>"""
OUT.with_suffix('.html').write_text(html)
print(f"wrote {OUT.with_suffix('.svg')}")
print(f"wrote {OUT.with_suffix('.html')}")
