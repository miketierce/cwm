#!/usr/bin/env python3
"""
READOUT PREAMP WIRING — rebuild Board A (RX bus -> Ch A), single-stage x11.
==========================================================================
Board A got disassembled and rebuilt with the CASCADE-driver recipe (2 stages,
~1600x, clipping) -> wrong: it over-drives + clips the strong 100mm modes. The
readout amp feeds a high-Z scope, so it must be ONE stage, ~x11, LINEAR.
Generates companion/readout_preamp_wiring.html. Run: python3 tools/readout_preamp.py
"""
from pathlib import Path
OUT = Path('companion/readout_preamp_wiring')

PINOUT = [(1,'OUT A','x11 output -> Ch A'),(2,'-IN A','feedback node'),(3,'+IN A','RX bus in'),
          (4,'V-','-9 V'),(5,'+IN B','UNUSED half -> tie to AGND'),(6,'-IN B','UNUSED -> jumper to pin7'),
          (7,'OUT B','UNUSED'),(8,'V+','+9 V')]
COMPONENTS = [
    ('Rsum x6','4.7 k each','one per RX hot (B,C,D,E,F,G) -> common SUM NODE. Isolates pickups (no mutual shunt). Skip the junction board.'),
    ('C_in','100 nF','SUM NODE -> +IN A (pin 3). AC-couple.'),
    ('R_b','100 k','+IN A (pin 3) -> AGND. Bias to mid-rail.'),
    ('Rf','47 k','OUT A (pin 1) -> -IN A (pin 2). Feedback.'),
    ('Rg','1 k','-IN A (pin 2) -> AGND. Gain = 1+Rf/Rg = 48x (x11 was too low).'),
    ('R_out','47 ohm','OUT A (pin 1) -> Ch A coax. Optional, scope is high-Z.'),
    ('C+cer','100 nF','+9V row -> AGND. Ceramic, any way. Hug chip.'),
    ('C+el','10 uF','+leg +9V row, -leg AGND. Electrolytic.'),
    ('C-cer','100 nF','-9V row -> AGND. Ceramic, any way.'),
    ('C-el','10 uF','+leg AGND, -leg -9V row. FLIPPED.'),
    ('unused half','jumper','pin6 -> pin7 ; pin5 -> AGND (parks the spare op-amp, no oscillation).'),
]
PLACE = [
    ('+9 V rail','top RED','+9 V'),('-9 V rail','bottom BLUE','-9 V'),
    ('AGND rail','top BLUE = bottom RED jumpered','0 V; all returns'),
    ('U1 (OPA2134)','pin1->e6,2->e7,3->e8,4->e9 ; 8->f6,7->f7,6->f8,5->f9','notch to row 1'),
    ('SUM NODE','col a row4 (any spare)','6x Rsum land here; blacks to AGND'),
    ('Rsum 4.7k x6','each RX hot -> a4','one per plate B,C,D,E,F,G (A->cascade)'),
    ('C_in 100nF','a4 -> a8','sum node into +IN A'),('R_b 100k','a8 -> AGND','bias'),
    ('Rf 47k','a6 -> a7','pin1->pin2'),('Rg 1k','a7 -> AGND','gain x48'),
    ('R_out 47','a6 -> Ch A coax centre','to scope'),
    ('C+cer 100nF','g6 -> AGND','ceramic, hug pin8'),('C+el 10uF','+g6 -> -AGND','elec, + to +9V'),
    ('C-cer 100nF','d9 -> AGND','ceramic, hug pin4'),('C-el 10uF','+AGND -> -d9','elec, + to AGND'),
    ('pin8 ->+9V','f6 -> +9V rail',''),('pin4 ->-9V','e9 -> -9V rail',''),
    ('spare half','f8(pin6)->f7(pin7) jumper ; f9(pin5)->AGND','park unused op-amp'),
]
BOM = [('OPA2134',1,'1 of the 3 free (or any spare)'),('47k',1,'Rf'),('1k',1,'Rg'),('100k',1,'R_b'),('4.7k',6,'Rsum, 1 per RX'),
       ('47 ohm',1,'R_out'),('100nF',3,'C_in + 2 bypass'),('10uF',2,'bypass')]
NOTES=[('4K7 summing on the preamp','6x 4.7k (one per RX hot) -> sum node -> 100nF -> +IN. NO junction board. 4.7k >> source so pickups stop loading each other (was 6-7x shunt = the ~2x SNR). Sum=/6, x48 covers it.'),('Gain x48','47k/1k. ~1-9 mV RX -> ~50-430 mV, clean in +/-1 V. x11 too low (near floor), 1600x clips. x48 is the middle.'),
       ('ONE stage only','use op-amp A (pins1-3); park half B. Two stages would clip the 100mm modes (the F1-8 "quiet" bug).'),
       ('No clipper','linear readout - no diodes, no overdrive. Ch B keeps the TX bundle as drive ref.'),
       ('Re-verify','after rebuild: python3 tools/cascade_verify.py --only F5,F6,F7,F8 --step 250 --no-phase ; expect >=3x.')]

def t(hd,rows): return '<table><tr>'+''.join(f'<th>{x}</th>' for x in hd)+'</tr>'+''.join('<tr>'+''.join(f'<td>{c}</td>' for c in r)+'</tr>' for r in rows)+'</table>'
html=f"""<!doctype html><html><head><meta charset=utf-8><title>Readout preamp</title><style>
@page{{size:A4 portrait;margin:0}}html,body{{margin:0;padding:0;font-family:system-ui,sans-serif;color:#222}}
.w{{padding:8mm}}.bar{{background:#eef6ff;border:1px solid #cfe2ff;padding:8px;border-radius:6px;margin-bottom:8px;font-size:13px}}
h2{{font-size:14px;margin:9px 0 3px}}table{{border-collapse:collapse;font-size:11px;width:100%;margin-bottom:6px}}td,th{{border:1px solid #ddd;padding:2px 6px;text-align:left}}th{{background:#f3f3f3}}p{{font-size:11px}}@media print{{.np{{display:none}}.w{{padding:0}}}}</style></head><body><div class=w>
<div class="bar np"><b>Ch A readout preamp — single OPA2134 half, ×11, LINEAR (no clip).</b> Replaces the mistakenly 2-stage rebuild. <button onclick=print()>Print</button></div>
<h2>OPA2134 pinout</h2>{t(['pin','name','role'],PINOUT)}
<h2>Components (one stage)</h2>{t(['ref','value','connection'],COMPONENTS)}
<h2>Breadboard placement</h2>{t(['item','breadboard','note'],PLACE)}
<h2>BOM</h2>{t(['part','qty','use'],BOM)}
<h2>Notes</h2>{''.join(f'<p><b>{h}:</b> {x}</p>' for h,x in NOTES)}</div></body></html>"""
OUT.parent.mkdir(parents=True,exist_ok=True); OUT.with_suffix('.html').write_text(html); print('wrote',OUT.with_suffix('.html'))
