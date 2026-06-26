#!/usr/bin/env python3
"""
CASCADE BOARD WIRING — OPA2134 RX→TX coupling board (with non-linear option)
============================================================================
Generates companion/cascade_board_wiring.html : a print-ready bench sheet for
the analog cascade link that composes two plates (plate A's field -> gain ->
NON-LINEARITY -> plate B's TX), the physical "future-of-future" step.

WHY 2 STAGES + A NON-LINEARITY (decided 2026-06-24):
  - A linear cascade (linear plate o linear coupling o linear plate) is just ONE
    linear map -> no compute beyond a single linear layer (the deep-learning
    collapse). Real depth needs a NON-LINEARITY between the stages. The |.|^2 FFT
    readout is an OUTPUT non-linearity only; it does not make the A->B coupling
    non-linear. So we add a soft-clipper in the analog link.
  - The cascade signal is WEAK (~1000x sensor->actuator loss) AND must reach the
    diode knee to engage the non-linearity, so we need ~600-1600x gain = TWO
    OPA2134 stages per channel (one chip = one full channel = rank-1).

FIRST EXPERIMENT (this sheet): rank-1, ONE OPA2134, two stages + soft-clipper,
into TWO MATCHED 25x76 slides (same mass -> shared band). Prove the non-linear
composition, then scale rank by adding chips.

Usage:  python3 tools/cascade_board.py   -> companion/cascade_board_wiring.html
"""
from pathlib import Path

OUT = Path('companion/cascade_board_wiring')

# ── OPA2134 (dual op-amp, DIP-8) ────────────────────────────────────────────
PINOUT = [
    (1, 'OUT A', 'stage-1 output'),
    (2, '-IN A', 'stage-1 feedback node'),
    (3, '+IN A', 'stage-1 input (RX in)'),
    (4, 'V-', 'to -9 V rail'),
    (5, '+IN B', 'stage-2 input (from stage-1)'),
    (6, '-IN B', 'stage-2 feedback node'),
    (7, 'OUT B', 'stage-2 output (to clipper)'),
    (8, 'V+', 'to +9 V rail'),
]

# ── Per-channel components (one full cascade channel = one OPA2134) ──────────
COMPONENTS = [
    ('C_in',  '100 nF film', 'plate-A RX hot -> +IN A (pin 3). AC-couples the pickup.'),
    ('R_b1',  '100 kOhm',    '+IN A (pin 3) -> AGND. Input bias to mid-rail (0 V).'),
    ('Rf1',   '47 kOhm',     'OUT A (pin 1) -> -IN A (pin 2). Stage-1 feedback.'),
    ('Rg1',   '1.2 kOhm',    '-IN A (pin 2) -> AGND. Sets stage-1 gain = 1+Rf1/Rg1 ~ 40x.'),
    ('C_c',   '100 nF film', 'OUT A (pin 1) -> +IN B (pin 5). Couples stage-1 into stage-2.'),
    ('R_b2',  '100 kOhm',    '+IN B (pin 5) -> AGND. Stage-2 input bias.'),
    ('Rf2',   '47 kOhm',     'OUT B (pin 7) -> -IN B (pin 6). Stage-2 feedback.'),
    ('Rg2',   '1.2 kOhm',    '-IN B (pin 6) -> AGND. Stage-2 gain ~40x (total ~1600x).'),
    ('(D1,D2)', 'OPTIONAL diodes/LEDs', 'OUT B node -> AGND, anti-parallel, for a SOFTER knee LATER. '
              'NOT NEEDED: the non-linearity is the OP-AMP clipping at its rails (see notes). LED pair (~+/-1.8 V) works if you have LEDs.'),
    ('R_out', '47 Ohm',      'OUT B node (after diodes) -> plate-B TX hot. Cap-load isolation (NOT 220).'),
    ('C+ cer', '100 nF', 'ceramic "104". +9 V pin-8 row -> AGND. Any orientation. Hug the chip.'),
    ('C+ el',  '10 uF',  'electrolytic. + leg -> +9 V (pin-8 row), − leg -> AGND. Hug the chip.'),
    ('C− cer', '100 nF', 'ceramic "104". −9 V pin-4 row -> AGND. Any orientation. Hug the chip.'),
    ('C− el',  '10 uF',  'electrolytic. + leg -> AGND, − leg -> −9 V (pin-4 row). FLIPPED vs the +9 V cap.'),
]

# ── Breadboard placement — FULL board, 3 chips (U1,U2,U3) = rank-3 ───────────
# Columns a-e (left of trench) and f-j (right). Each DIP-8, notch toward row 1,
# straddles the trench: pins 1-4 down column e, pins 8-5 down column f. Left-pin
# tie points are columns a-d; right-pin tie points are columns g-j.
# Rails: top red = +9 V, bottom blue = -9 V, AGND = top-blue jumpered to bottom-red.
def channel_placement(k, r):
    """Placement rows for channel k (chip Uk) with its DIP at base row r."""
    U = f'U{k}'
    return [
        (f'{U} (OPA2134 #{k})',
         f'pin1->e{r}, pin2->e{r+1}, pin3->e{r+2}, pin4->e{r+3} ; pin8->f{r}, pin7->f{r+1}, pin6->f{r+2}, pin5->f{r+3}',
         'notch toward row 1'),
        (f'C_in{k} 100nF',  f'plate A RX{k} hot  ->  a{r+2}', 'into +IN A (pin 3)'),
        (f'R_b1.{k} 100k',  f'a{r+2}  ->  AGND rail', 'stage-1 input bias'),
        (f'Rf1.{k} 47k',    f'a{r}  ->  a{r+1}', 'OUT A(pin1) -> -IN A(pin2)'),
        (f'Rg1.{k} 1.2k',   f'a{r+1}  ->  AGND rail', 'stage-1 gain ~40x'),
        (f'C_c{k} 100nF',   f'a{r}  ->  j{r+3}', 'OUT A(pin1) -> +IN B(pin5)'),
        (f'R_b2.{k} 100k',  f'j{r+3}  ->  AGND rail', 'stage-2 input bias'),
        (f'Rf2.{k} 47k',    f'j{r+1}  ->  j{r+2}', 'OUT B(pin7) -> -IN B(pin6)'),
        (f'Rg2.{k} 12k|1.2k', f'j{r+2}  ->  AGND rail', '12k = LINEAR, 1.2k = CLIP'),
        (f'R_out{k} 47',    f'j{r+1}  ->  plate B TX{k} hot', 'OUT B node -> TX (cap-load iso)'),
        (f'C+cer.{k} 100nF', f'g{r}  ->  AGND rail', f'ceramic "104" on the +9V row (pin 8 = f{r}). ANY orientation. Hug the chip.'),
        (f'C+el.{k} 10uF',  f'+leg g{r}  ->  −leg AGND rail', f'ELECTROLYTIC: + leg to the +9V row, − leg to AGND. Hug the chip.'),
        (f'C−cer.{k} 100nF', f'd{r+3}  ->  AGND rail', f'ceramic "104" on the −9V row (pin 4 = e{r+3}). ANY orientation. Hug the chip.'),
        (f'C−el.{k} 10uF',  f'+leg AGND rail  ->  −leg d{r+3}', f'ELECTROLYTIC: + leg to AGND, − leg to the −9V row (FLIPPED — −9V is below ground). Hug the chip.'),
        (f'{U} pin8 -> +9V', f'f{r}  ->  +9 V rail', 'V+'),
        (f'{U} pin4 -> -9V', f'e{r+3}  ->  -9 V rail', 'V-'),
    ]


RAILS = [
    ('+9 V rail', 'top RED rail', 'from Board-D / bench +9 V'),
    ('-9 V rail', 'bottom BLUE rail', 'from -9 V'),
    ('AGND rail', 'top BLUE rail, jumpered to bottom RED', '0 V supply midpoint; ALL returns star here'),
    ('plate A RX cold/shield (x3)', 'AGND rail', 'each RX ground return'),
    ('plate B TX cold (x3)', 'AGND rail', 'each TX ground return'),
]

# 3 DIPs spaced 16 rows apart on a full (63-row) board: U1@6, U2@22, U3@38.
PLACEMENT = RAILS + channel_placement(1, 6) + channel_placement(2, 22) + channel_placement(3, 38)

# ── Net list (the unambiguous source of truth) ──────────────────────────────
NETLIST = [
    ('PLATE A RX (hot)', 'C_in -> +IN A (pin 3)'),
    ('PLATE A RX (cold/shield)', 'AGND bus'),
    ('+IN A (pin 3)', 'C_in, R_b1(->AGND)'),
    ('-IN A (pin 2)', 'Rf1(->OUT A), Rg1(->AGND)'),
    ('OUT A (pin 1)', 'Rf1, C_c(->+IN B)'),
    ('+IN B (pin 5)', 'C_c, R_b2(->AGND)'),
    ('-IN B (pin 6)', 'Rf2(->OUT B), Rg2(->AGND)'),
    ('OUT B (pin 7)', 'Rf2, R_out  [optional D1/D2 anti-parallel ->AGND for a softer knee]'),
    ('R_out far end', 'PLATE B TX (hot)'),
    ('PLATE B TX (cold)', 'AGND bus'),
    ('pin 8 (V+)', '+9 V rail, C_by+(->AGND)'),
    ('pin 4 (V-)', '-9 V rail, C_by-(->AGND)'),
    ('AGND bus', 'supply 0 V midpoint; all returns star here'),
]

BOM = [
    ('OPA2134PA', 3, 'dual op-amp, DIP-8. ONE chip = ONE full channel (its 2 halves = the 2 stages). 3 chips = rank-3. '
     'You have 4; the 4th stays on Board A (Ch A readout). ALSO the non-linearity (rail clip).'),
    ('(diodes / LEDs)', '0-2', 'OPTIONAL, softer knee later. NOT needed - op-amp rail clipping is the non-linearity. LED pair (~1.8 V) works if on hand.'),
    ('47 kOhm 1%', 6, 'Rf1, Rf2  (2 per channel x3)'),
    ('1.2 kOhm 1%', 6, 'Rg1 x3, plus Rg2-CLIP x3'),
    ('12 kOhm 1%', 3, 'Rg2-LINEAR (swap with the 1.2k per channel = the linear/non-linear toggle)'),
    ('100 kOhm', 6, 'R_b1, R_b2 bias  (2 per channel x3)'),
    ('47 Ohm', 3, 'R_out  (1 per channel x3)'),
    ('100 nF film', 12, 'C_in, C_c + 2x bypass  (4 per channel x3)'),
    ('10 uF electrolytic', 6, 'rail bulk bypass (2 per channel x3). POLARIZED — + leg to the MORE-POSITIVE side (so + to +9V on one cap, + to AGND on the -9V cap).'),
    ('+/-9 V supply', 1, 'dual rail (Board D supply or bench)'),
]

# ── Channel -> chip -> plate map (rank-3 = 3 chips) ─────────────────────────
CHANNELS = [
    ('CH1', 'U1 (OPA2134 #1)', 'plate A RX1 (50,28)', 'plate B TX1'),
    ('CH2', 'U2 (OPA2134 #2)', 'plate A RX2 (50,72)', 'plate B TX2'),
    ('CH3', 'U3 (OPA2134 #3)', 'plate A RX3 (28,50)', 'plate B TX3'),
    ('(CH4)', '(needs a 4th chip)', 'plate A RX4 (72,50) — bond as mass, leave unwired', '(plate B TX4)'),
]

NOTES = [
    ('Gain / bandwidth', 'Two stages ~40x each = ~1600x makes up the ~1000x cascade loss AND drives stage-2 into its '
     'rails (the clip). For the 25x76 SLIDES (mid band ~100-255 kHz) use ~25x/stage (Rg=2 kOhm) so each stage keeps '
     'BW = 8 MHz/25 ~ 320 kHz; total ~600x still reaches the rails. Hard clip above ~200 kHz may show slew recovery - fine for a first proof.'),
    ('The non-linearity = the OP-AMP (no diodes to buy)', 'You cannot make a non-linearity from R and C alone - they '
     'are linear. But the OPA2134 you already have IS one: drive stage 2 hard and its output SATURATES at the +/-9 V '
     'rails = hard clipping. With 2x ~40x stages the stage-2 output wants ~8 V, so it naturally clips. Hard clip makes '
     'MORE harmonics than a diode soft-clip = an even clearer non-linear signature.'),
    ('Linear vs non-linear = a GAIN SWAP', 'Toggle the experiment by swapping Rg2 (a resistor you already have): '
     'Rg2 = 12 kOhm -> total ~200x -> stage-2 out ~1 V (LINEAR baseline, below rails); Rg2 = 1.2 kOhm -> total ~1600x '
     '-> clips at the rails (NON-LINEAR). Same board, two resistor values, no diodes. A pot for Rg2 = a continuous knob.'),
    ('Plate B is driven by THIS board', 'NOT by the NCO. Disconnect NCO from plate B for the cascade run. Plate A is '
     'still NCO-driven (input encoding). Read plate B -> x11 preamp -> Ch A.'),
    ('Matched plates', 'Both 25x76 slides must share a band (same mass/geometry) so A''s output lands on B''s resonances. '
     'Soft-clip keeps the fundamental so same-band works; it adds harmonics for the non-linear richness.'),
    ('Stability + isolation', 'Keep R_out = 47 Ohm for cap-load stability. Mechanically ISOLATE the slides (separate '
     'mounts) so an A->B->A acoustic loop cannot oscillate. The buffer is one-way electrically.'),
    ('Validate first', 'Bench-test ONE channel at the slide frequency into a real PZT: scope OUT B for clean gain, then '
     'add the diodes and confirm soft-clipping onset. THEN connect plate B.'),
    ('Scaling rank', 'ONE channel = ONE OPA2134 (its two halves are the two gain stages). You have 4 chips, 1 on the '
     'Ch A readout -> 3 free -> RANK-3 (3 channels). Rank-4 needs a 4th chip (~$3). No LEDs on hand, so the op-amp rail '
     'clip IS the non-linearity (which is the recommended one anyway). First slide test only needs 1 channel (rank-1).'),
]

# ── SVG signal-flow (boxes + arrows; renders reliably) ──────────────────────
def box(x, y, w, h, fill, title, sub):
    s = f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="2.5" fill="{fill}" stroke="#333" stroke-width="0.5"/>'
    s += f'<text x="{x+w/2:.1f}" y="{y+h/2-0.5:.1f}" font-size="3.2" font-weight="bold" text-anchor="middle" font-family="sans-serif" fill="#111">{title}</text>'
    s += f'<text x="{x+w/2:.1f}" y="{y+h/2+3.4:.1f}" font-size="2.4" text-anchor="middle" font-family="sans-serif" fill="#444">{sub}</text>'
    return s


def arrow(x1, y, x2):
    return (f'<line x1="{x1}" y1="{y}" x2="{x2-1.4}" y2="{y}" stroke="#333" stroke-width="0.6"/>'
            f'<path d="M {x2} {y} l -2 -1.2 l 0 2.4 z" fill="#333"/>')


Wsvg, Hsvg = 250.0, 46.0
svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{Wsvg}mm" height="{Hsvg}mm" viewBox="0 0 {Wsvg} {Hsvg}">',
       f'<rect width="{Wsvg}" height="{Hsvg}" fill="white"/>',
       f'<text x="{Wsvg/2}" y="6" font-size="3.4" font-weight="bold" text-anchor="middle" font-family="sans-serif">ONE CHANNEL = ONE OPA2134 (halves A+B = the 2 stages)  ·  RX → ×2 gain → rail-clip → TX  ·  build 3 chips = rank-3</text>']
y = 16
xs = [4, 42, 82, 122, 165, 206]
svg.append(box(xs[0], y, 34, 16, '#e8eef7', 'PLATE A', 'RX pickup (~mV)'))
svg.append(arrow(xs[0]+34, y+8, xs[1]))
svg.append(box(xs[1], y, 36, 16, '#fde9d0', 'STAGE 1', 'OPA2134 ½A · ×40'))
svg.append(arrow(xs[1]+36, y+8, xs[2]))
svg.append(box(xs[2], y, 36, 16, '#fde9d0', 'STAGE 2', 'OPA2134 ½B · ×40'))
svg.append(arrow(xs[2]+36, y+8, xs[3]))
svg.append(box(xs[3], y, 39, 16, '#f7d7da', 'CLIP', 'op-amp rails (free)'))
svg.append(arrow(xs[3]+39, y+8, xs[4]))
svg.append(box(xs[4], y, 37, 16, '#d7f0dd', '47 Ω', 'cap-load isolation'))
svg.append(arrow(xs[4]+37, y+8, xs[5]))
svg.append(box(xs[5], y, 40, 16, '#e8eef7', 'PLATE B', 'TX (driven here)'))
svg.append(f'<text x="{Wsvg/2}" y="42" font-size="2.6" text-anchor="middle" font-family="sans-serif" fill="#a23">'
           f'LOW gain (Rg2 12k) = linear baseline (one linear map).  HIGH gain (Rg2 1.2k) = op-amp CLIPS at its rails = the real non-linear 2-step.  No diodes.</text>')
svg.append('</svg>')
svg_text = "\n".join(svg)

# ── HTML wrapper ────────────────────────────────────────────────────────────
def tbl(headers, rows):
    h = "".join(f"<th>{x}</th>" for x in headers)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f"<table><tr>{h}</tr>{body}</table>"

pin_tbl = tbl(['pin', 'name', 'role'], [(p, n, r) for p, n, r in PINOUT])
comp_tbl = tbl(['ref', 'value', 'connection'], COMPONENTS)
place_tbl = tbl(['item', 'breadboard', 'note'], PLACEMENT)
net_tbl = tbl(['node', 'connects to'], NETLIST)
bom_tbl = tbl(['part', 'qty', 'purpose'], [(p, q, u) for p, q, u in BOM])
chan_tbl = tbl(['channel', 'chip', 'input (plate A RX)', 'output (plate B TX)'], CHANNELS)
notes_html = "".join(f"<p><b>{h}:</b> {t}</p>" for h, t in NOTES)

html = f"""<!doctype html><html><head><meta charset="utf-8"><title>Cascade board wiring</title>
<style>
  @page {{ size: A4 landscape; margin: 0; }}
  * {{ box-sizing: border-box; }}
  html, body {{ margin:0; padding:0; font-family:-apple-system,system-ui,sans-serif; color:#222; }}
  .wrap {{ padding: 8mm; }}
  .bar {{ background:#eef6ff; border:1px solid #cfe2ff; padding:8px 12px; border-radius:6px; margin-bottom:8px; font-size:13px; line-height:1.5; }}
  button {{ font-size:14px; padding:6px 13px; border-radius:6px; border:1px solid #888; background:#f5f5f5; cursor:pointer; }}
  h2 {{ font-size:14px; margin:10px 0 3px; }}
  table {{ border-collapse:collapse; font-size:10.5px; margin:2px 0 6px; width:100%; }}
  td,th {{ border:1px solid #ddd; padding:2px 6px; text-align:left; vertical-align:top; }}
  th {{ background:#f3f3f3; }}
  .cols {{ display:flex; gap:10px; }}
  .cols > div {{ flex:1; }}
  p {{ font-size:11px; margin:3px 0; }}
  svg {{ display:block; width:{Wsvg}mm; height:{Hsvg}mm; max-width:100%; }}
  @media print {{ .noprint {{ display:none !important; }} .wrap {{ padding:0; }} }}
</style></head><body>
<div class="wrap">
<div class="bar noprint">
  <b>Cascade board — OPA2134 RX→TX coupling; the non-linearity is the op-amp clipping at its rails (NO diodes / NO LEDs).</b><br>
  rank-3 = 3 chips (each chip = one channel = two stages). Run each channel <b>twice</b>: Rg2 = 12k (linear) then 1.2k (clipped / non-linear) — the difference is the experiment.
  &nbsp;<button onclick="window.print()">Print</button>
</div>
{svg_text}
<h2>Channels &mdash; rank-3 (3 of your 4 OPA2134; the 4th stays on Ch A). Each channel = ONE chip = TWO stages.</h2>
{chan_tbl}
<div class="cols">
  <div>
    <h2>OPA2134 pinout (DIP-8, notch up)</h2>
    {pin_tbl}
    <h2>Per-channel components (identical for U1 / U2 / U3)</h2>
    {comp_tbl}
    <h2>Bill of materials &mdash; whole board (3 channels)</h2>
    {bom_tbl}
  </div>
  <div>
    <h2>Breadboard placement &mdash; full board, U1 / U2 / U3 (rank-3)</h2>
    {place_tbl}
    <h2>Net list &mdash; per channel (identical for U1 / U2 / U3)</h2>
    {net_tbl}
  </div>
</div>
<h2>Build &amp; experiment notes</h2>
{notes_html}
</div>
</body></html>"""

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.with_suffix('.svg').write_text(svg_text)
OUT.with_suffix('.html').write_text(html)
print("wrote", OUT.with_suffix('.svg'))
print("wrote", OUT.with_suffix('.html'))
