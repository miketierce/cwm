#!/usr/bin/env python3
"""
PZT PLACEMENT GUIDE — where to add multipoint-TX PZTs to a 100 mm plate
=======================================================================

The 100 mm plates already carry 3 corner PZTs (per the relay map: SW=TX,
NW=RX, NE=RX; SE empty). WL-B10 (corrected 2026-06-22) wants 2-3 MORE TX
positions per plate (multipoint), up to the modal-independence ceiling of
~4-6 TX/plate. This tool answers: *where exactly?* — and prints a scale
template you can lay on the glass.

PHYSICS (consistent with tools/pzt_mounting_analysis.py):
  A flat disc bonded to the plate couples to FLEXURAL STRAIN ~ Laplacian of
  the mode shape (∇²w), NOT to displacement. Consequences, both measured/known
  in this project:
    - A free EDGE has zero bending moment -> low curvature -> corner/edge PZTs
      are WEAK couplers (~10% of an interior antinode; pzt_mounting_analysis.py).
    - Interior ANTINODES of ∇²w are the strong, information-rich drive points.
  So "add another corner" is the WORST use of a channel: it's a weak coupler AND
  it duplicates the symmetry orbit the 3 existing corners already occupy.

WHAT IT COMPUTES:
  1. Free-free square-plate modes (Warburton product of free-free beam functions)
     in the measured 40-100 kHz band -> the low-order mode set the corners drive.
  2. Strain-coupling vector c_k(x,y) = disc-averaged ∇²φ_k for every candidate
     position (a real 10 mm disc, finite footprint).
  3. GREEDY modal-independence selection: given the 3 occupied corners, add the
     position whose coupling vector most grows the addressable mode subspace
     (largest residual after projecting onto what the existing PZTs already
     reach). Repeat. This maximizes the number of modes you can INDEPENDENTLY
     address = the kernel dimension WL-B10 cares about.
  4. Emits a 1:1 scale printable (SVG + a foolproof HTML print wrapper) with a
     verification ruler, 10 mm grid, existing keep-outs, and numbered targets.

HONEST SCOPE: this is a model-based placement GUIDE (free-free BCs are an
idealization — the real plate rests on its PZTs). The deciding test is a census
after install (direct_wire_census.py); the model picks smart starting points so
the census has the best chance of a high usable-mode count.

Usage:
  python3 tools/pzt_placement.py                  # default 100mm, 3 to add
  python3 tools/pzt_placement.py --add 2 --out companion/pzt_placement_100mm
"""
import argparse
import numpy as np
from pathlib import Path

ap = argparse.ArgumentParser(description='PZT multipoint placement guide + printable')
ap.add_argument('--size', type=float, default=100.0, help='plate edge (mm, square)')
ap.add_argument('--pzt-dia', type=float, default=10.0, help='PZT disc diameter (mm)')
ap.add_argument('--edge-margin', type=float, default=1.0, help='min gap disc edge to plate edge (mm)')
ap.add_argument('--min-gap', type=float, default=4.0, help='min gap between disc EDGES (mm)')
ap.add_argument('--add', type=int, default=None, help='how many new PZTs (default 3 for tx, 4 for rx)')
ap.add_argument('--corner-inset', type=float, default=8.0, help='existing corner PZT center inset from each edge (mm)')
ap.add_argument('--role', choices=['tx', 'rx', 'both'], default='tx',
                help='tx = multipoint DRIVE discs; rx = CASCADE SENSOR discs; both = COMPLETE template (4 corner TX + 4 interior RX)')
ap.add_argument('--out', type=str, default=None, help='output path stem (.svg/.html)')
args = ap.parse_args()
if args.add is None:
    args.add = 4 if args.role in ('rx', 'both') else 3
if args.out is None:
    args.out = {'rx': 'companion/pzt_rx_placement_100mm',
                'both': 'companion/pzt_template_100mm'}.get(args.role, 'companion/pzt_placement_100mm')

L = args.size
R = args.pzt_dia / 2.0
SPACING = args.pzt_dia + args.min_gap          # min center-to-center
LO = R + args.edge_margin                      # min center coord
HI = L - LO                                     # max center coord

# Existing corner PZTs (per relay map: SW=TX, NW=RX, NE=RX occupied; SE empty).
# Layout is C4v-symmetric, so which corner is empty does not change the answer.
ins = args.corner_inset
if args.role in ('rx', 'both'):
    # CASCADE SOURCE plate: all 4 corners are the phase-locked TX (NCO Block A);
    # place the 4 RX SENSORS at interior antinodes that read independent
    # projections of the plate's field (-> cascade board -> plate B's 4 TX).
    EXISTING = {
        'SW (TX1)': (ins, ins),
        'NW (TX2)': (ins, L - ins),
        'NE (TX3)': (L - ins, L - ins),
        'SE (TX4)': (L - ins, ins),
    }
    EMPTY_CORNER = None
else:
    EXISTING = {
        'SW (TX→NCO)': (ins, ins),
        'NW (RX)':     (ins, L - ins),
        'NE (RX)':     (L - ins, L - ins),
    }
    EMPTY_CORNER = ('SE (empty)', (L - ins, ins))

# ── Free-free beam mode shapes (Euler-Bernoulli) ────────────────────────────
# idx 0 = rigid translation (const), 1 = rigid rotation (linear),
# idx>=2 = elastic modes with these βL roots of cos(βL)cosh(βL)=1:
BETA_L = [4.730041, 7.853205, 10.995608, 14.137165, 17.278760]


def beam(idx, xi):
    """Free-free beam mode value at xi∈[0,1], unit-RMS normalized."""
    if idx == 0:
        f = np.ones_like(xi)
    elif idx == 1:
        f = np.sqrt(3.0) * (1.0 - 2.0 * xi)
    else:
        bl = BETA_L[idx - 2]
        s = (np.cosh(bl) - np.cos(bl)) / (np.sinh(bl) - np.sin(bl))
        f = (np.cosh(bl * xi) + np.cos(bl * xi)) - s * (np.sinh(bl * xi) + np.sin(bl * xi))
    rms = np.sqrt(np.mean(f * f))
    return f / (rms if rms > 1e-9 else 1.0)


def kappa(idx):
    return 0.0 if idx < 2 else BETA_L[idx - 2]


# ── Build the low-order plate mode set (lowest ~15 elastic modes) ───────────
N = 221
g = np.linspace(0.0, 1.0, N)            # xi grid 0..1
X = {i: beam(i, g) for i in range(6)}   # 1-D beam fields

modes = []
for i in range(6):
    for j in range(6):
        if (i, j) in [(0, 0), (0, 1), (1, 0)]:   # pure rigid-body, no strain
            continue
        modes.append((i, j, np.hypot(kappa(i), kappa(j))))
modes.sort(key=lambda m: m[2])
modes = modes[:15]                      # the band the corners actually drive

# 2-D fields + their Laplacian (the strain a flat disc couples to), unit-RMS.
dx = (L / 1000.0) * (g[1] - g[0]) * 1000.0  # mm grid step in mm (consistent units)
h_step = g[1] - g[0]
COUP = []          # one (N,N) strain field per mode, unit-RMS
for (i, j, _k) in modes:
    W = np.outer(X[i], X[j])                       # displacement shape
    lap = np.zeros_like(W)
    lap[1:-1, :] += (W[2:, :] - 2 * W[1:-1, :] + W[:-2, :]) / h_step**2
    lap[:, 1:-1] += (W[:, 2:] - 2 * W[:, 1:-1] + W[:, :-2]) / h_step**2
    rms = np.sqrt(np.mean(lap * lap))
    COUP.append(lap / (rms if rms > 1e-9 else 1.0))
COUP = np.array(COUP)                              # (M, N, N)
M = COUP.shape[0]


def coupling_vector(cx, cy):
    """Disc-averaged strain coupling vector at center (cx,cy) mm -> length-M."""
    gx = (np.arange(N) / (N - 1)) * L
    ix = np.where((gx >= cx - R) & (gx <= cx + R))[0]
    iy = np.where((gx >= cy - R) & (gx <= cy + R))[0]
    if len(ix) == 0 or len(iy) == 0:
        return np.zeros(M)
    sub = COUP[:, np.ix_(iy, ix)[0], np.ix_(iy, ix)[1]]
    # circular mask
    XX, YY = np.meshgrid(gx[ix], gx[iy])
    mask = (XX - cx) ** 2 + (YY - cy) ** 2 <= R * R
    if mask.sum() == 0:
        return np.zeros(M)
    return (sub * mask).sum(axis=(1, 2)) / mask.sum()


# ── Existing subspace (what the 3 corner PZTs already reach) ─────────────────
def orthonormal_basis(vectors, tol=1e-9):
    Q = []
    for v in vectors:
        w = v.copy().astype(float)
        for q in Q:
            w -= np.dot(q, w) * q
        n = np.linalg.norm(w)
        if n > tol:
            Q.append(w / n)
    return Q


existing_vecs = [coupling_vector(x, y) for (x, y) in EXISTING.values()]
basis = orthonormal_basis(existing_vecs)


def addressable_rank(vectors, tol_frac=0.02):
    Mtx = np.array(vectors).T
    if Mtx.size == 0:
        return 0
    s = np.linalg.svd(Mtx, compute_uv=False)
    return int((s > tol_frac * s[0]).sum()) if len(s) else 0


# ── Greedy: add the position that most grows the addressable subspace ────────
# NEW discs are restricted to the INTERIOR: a flat disc couples to flexural
# strain (∇²w), which is ~0 at the free edges, so edge/near-edge placements are
# weak, unreliable couplers. Require the disc center >= INTERIOR_INSET from any
# edge so it sits on a genuine interior antinode.
INTERIOR_INSET = max(LO, 16.0)
lo_i, hi_i = INTERIOR_INSET, L - INTERIOR_INSET
candidates = []
step = 2.0
yy = lo_i
while yy <= hi_i + 1e-6:
    xx = lo_i
    while xx <= hi_i + 1e-6:
        candidates.append((round(xx, 1), round(yy, 1)))
        xx += step
    yy += step


def too_close(p, occupied):
    return any(np.hypot(p[0] - q[0], p[1] - q[1]) < SPACING for q in occupied)


occupied = list(EXISTING.values())
chosen = []
for _ in range(args.add):
    best, best_score, best_vec, best_w = None, -1.0, None, None
    for p in candidates:
        if too_close(p, occupied) or too_close(p, chosen):
            continue
        v = coupling_vector(*p)
        w = v.copy()
        for q in basis:
            w -= np.dot(q, w) * q
        # |residual of the REAL strain-coupling vector| = strong AND independent
        # excitation the array cannot yet reach (units of strain coupling).
        score = np.linalg.norm(w)
        if score > best_score:
            best, best_score, best_vec, best_w = p, score, v, w
    if best is None:
        break
    chosen.append(best)
    occupied.append(best)
    nb = best_w / (np.linalg.norm(best_w) + 1e-12)
    basis.append(nb)


def region(p):
    x, y = p
    c = L / 2
    near = lambda a, b: abs(a - b) < 12
    if near(x, c) and near(y, c):
        return 'CENTER (∇²w antinode of symmetric modes)'
    edge_mid = [(c, LO), (c, HI), (LO, c), (HI, c)]
    if any(np.hypot(x - ex, y - ey) < 14 for ex, ey in edge_mid):
        return 'EDGE-MIDPOINT (drives 1st bending family)'
    quart = [(L*0.25, L*0.25), (L*0.75, L*0.75), (L*0.25, L*0.75), (L*0.75, L*0.25)]
    if any(np.hypot(x - qx, y - qy) < 16 for qx, qy in quart):
        return 'QUARTER-POINT (diagonal modes)'
    return 'interior antinode'


# ── Report ───────────────────────────────────────────────────────────────
print("=" * 74)
_role_word = {'rx': 'RX cascade-sensor', 'both': 'interior-RX (+ 4 corner TX)'}.get(args.role, 'multipoint-TX')
print(f"  PZT PLACEMENT — {L:.0f} mm plate, add {args.add} {_role_word} discs")
print(f"  disc Ø{args.pzt_dia:.0f} mm | min center spacing {SPACING:.0f} mm | band: lowest {M} modes")
print("=" * 74)
print(f"  EXISTING (keep-out): " + ", ".join(f"{k} {v}" for k, v in EXISTING.items()))
if EMPTY_CORNER is not None:
    print(f"  4th corner {EMPTY_CORNER[0]} {EMPTY_CORNER[1]} is a WEAK + redundant spot — intentionally NOT chosen.")
print()
rank0 = addressable_rank(existing_vecs)
print(f"  Addressable modes with the {len(EXISTING)} corners alone : {rank0} / {M}")
running = list(existing_vecs)
for n, p in enumerate(chosen, 1):
    running.append(coupling_vector(*p))
    rk = addressable_rank(running)
    print(f"  #{n}  ({p[0]:5.1f}, {p[1]:5.1f}) mm   {region(p):<44} → addressable {rk}/{M}")
print(f"\n  Net: {rank0} → {addressable_rank(running)} independently-addressable modes "
      f"(+{addressable_rank(running) - rank0}) from {args.add} PZTs.")

# ── Scale-accurate SVG printable ────────────────────────────────────────────
MARGIN = 26.0
Wsvg, Hsvg = L + 2 * MARGIN, L + 2 * MARGIN + 34
ox, oy = MARGIN, MARGIN + 6                      # plate top-left in SVG (y-down)


def sx(x):
    return ox + x


def sy(y):
    return oy + (L - y)                           # flip so physical y is up


def disc(x, y, color, label, sub='', dash=False, num=None):
    e = f'<circle cx="{sx(x):.2f}" cy="{sy(y):.2f}" r="{R:.2f}" fill="{color}" ' \
        f'fill-opacity="{0.18 if not dash else 0.10}" stroke="{color}" stroke-width="0.5" ' \
        f'{"stroke-dasharray=\"1.5,1.2\"" if dash else ""}/>'
    cross = (f'<line x1="{sx(x)-2.2:.2f}" y1="{sy(y):.2f}" x2="{sx(x)+2.2:.2f}" y2="{sy(y):.2f}" stroke="{color}" stroke-width="0.4"/>'
             f'<line x1="{sx(x):.2f}" y1="{sy(y)-2.2:.2f}" x2="{sx(x):.2f}" y2="{sy(y)+2.2:.2f}" stroke="{color}" stroke-width="0.4"/>')
    txt = ''
    if num is not None:
        txt += f'<text x="{sx(x):.2f}" y="{sy(y)-R-1.2:.2f}" font-size="5" font-weight="bold" fill="{color}" text-anchor="middle">{num}</text>'
    txt += f'<text x="{sx(x):.2f}" y="{sy(y)+R+3.4:.2f}" font-size="2.5" fill="{color}" text-anchor="middle">{label}</text>'
    if sub:
        txt += f'<text x="{sx(x):.2f}" y="{sy(y)+R+6.2:.2f}" font-size="2.1" fill="#555" text-anchor="middle">{sub}</text>'
    return e + cross + txt


svg = []
svg.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{Wsvg:.1f}mm" height="{Hsvg:.1f}mm" '
           f'viewBox="0 0 {Wsvg:.1f} {Hsvg:.1f}">')
svg.append(f'<rect x="0" y="0" width="{Wsvg:.1f}" height="{Hsvg:.1f}" fill="white"/>')
_kind = {'rx': f'add {args.add} RX cascade sensors',
         'both': 'COMPLETE TEMPLATE · 4 corner TX + 4 interior RX'}.get(args.role, f'add {args.add} TX PZTs')
svg.append(f'<text x="{Wsvg/2:.1f}" y="6.5" font-size="3.5" font-weight="bold" text-anchor="middle" '
           f'font-family="sans-serif">{L:.0f}\u00d7{L:.0f} mm plate \u00b7 {_kind} \u00b7 PRINT AT 100% (ACTUAL SIZE)</text>')

# 10 mm grid
for k in range(0, int(L) + 1, 10):
    lw = 0.5 if k % 50 == 0 else 0.2
    col = '#bbb' if k % 50 == 0 else '#e2e2e2'
    svg.append(f'<line x1="{sx(k):.2f}" y1="{sy(0):.2f}" x2="{sx(k):.2f}" y2="{sy(L):.2f}" stroke="{col}" stroke-width="{lw}"/>')
    svg.append(f'<line x1="{sx(0):.2f}" y1="{sy(k):.2f}" x2="{sx(L):.2f}" y2="{sy(k):.2f}" stroke="{col}" stroke-width="{lw}"/>')
    if k % 20 == 0:
        svg.append(f'<text x="{sx(k):.2f}" y="{sy(0)+4.5:.2f}" font-size="2.4" fill="#888" text-anchor="middle" font-family="sans-serif">{k}</text>')
        svg.append(f'<text x="{sx(0)-3.5:.2f}" y="{sy(k)+1:.2f}" font-size="2.4" fill="#888" text-anchor="middle" font-family="sans-serif">{k}</text>')

# plate outline + corner registration ticks
svg.append(f'<rect x="{sx(0):.2f}" y="{sy(L):.2f}" width="{L:.2f}" height="{L:.2f}" fill="none" stroke="#111" stroke-width="0.8"/>')
for cx, cy in [(0, 0), (L, 0), (0, L), (L, L)]:
    svg.append(f'<line x1="{sx(cx):.2f}" y1="{sy(cy):.2f}" x2="{sx(cx)+(6 if cx==0 else -6):.2f}" y2="{sy(cy):.2f}" stroke="#111" stroke-width="0.6"/>')
    svg.append(f'<line x1="{sx(cx):.2f}" y1="{sy(cy):.2f}" x2="{sx(cx):.2f}" y2="{sy(cy)+(6 if cy==L else -6):.2f}" stroke="#111" stroke-width="0.6"/>')

# orientation label
svg.append(f'<text x="{sx(ins):.2f}" y="{sy(ins)-R-2:.2f}" font-size="2.3" fill="#888" text-anchor="middle" font-family="sans-serif">SW · TX to NCO</text>')

# existing (keep-out) + empty corner
if args.role == 'both':
    # complete template: corners are first-class TX discs (NCO Block A CH1-4)
    TXC = '#e8820e'
    for n, (name, (x, y)) in enumerate(EXISTING.items(), 1):
        svg.append(disc(x, y, TXC, name.split(' ')[0], f'TX{n} · CH{n}', dash=False))
else:
    for name, (x, y) in EXISTING.items():
        svg.append(disc(x, y, '#888', name.split(' ')[0], 'existing', dash=True))
if EMPTY_CORNER is not None:
    ex_name, (exx, exy) = EMPTY_CORNER
    svg.append(f'<circle cx="{sx(exx):.2f}" cy="{sy(exy):.2f}" r="{R:.2f}" fill="none" stroke="#ccc" stroke-width="0.4" stroke-dasharray="1,1.5"/>')
    svg.append(f'<text x="{sx(exx):.2f}" y="{sy(exy)+1:.2f}" font-size="2.0" fill="#bbb" text-anchor="middle">skip</text>')

# new targets
PALETTE = ['#c81e3a', '#1769aa', '#1b8a3a', '#9b51e0', '#d98300']
_chan = ['U1A → B-TX1', 'U1B → B-TX2', 'U2A → B-TX3', 'U2B → B-TX4']
for n, p in enumerate(chosen, 1):
    _sub = (f'RX#{n} · {_chan[(n-1) % len(_chan)]}') if args.role in ('rx', 'both') else f'new TX #{n}'
    svg.append(disc(p[0], p[1], PALETTE[(n - 1) % len(PALETTE)], f'({p[0]:.0f},{p[1]:.0f})', _sub, num=n))

# verification ruler (50 mm) bottom-left
ry = Hsvg - 16
svg.append(f'<line x1="{ox:.2f}" y1="{ry:.2f}" x2="{ox+50:.2f}" y2="{ry:.2f}" stroke="#111" stroke-width="0.6"/>')
for t in range(0, 51, 10):
    svg.append(f'<line x1="{ox+t:.2f}" y1="{ry-1.6:.2f}" x2="{ox+t:.2f}" y2="{ry+1.6:.2f}" stroke="#111" stroke-width="0.5"/>')
svg.append(f'<text x="{ox:.2f}" y="{ry-2.5:.2f}" font-size="2.6" font-weight="bold" font-family="sans-serif">VERIFY SCALE → this bar must measure exactly 50.0 mm</text>')
svg.append(f'<text x="{ox+50+2:.2f}" y="{ry+1:.2f}" font-size="2.6" font-family="sans-serif">50 mm</text>')

# legend / notes
ly = Hsvg - 8
if args.role == 'both':
    notes = ('Amber = 4 corner TX → NCO Block A (CH1-4, phase-locked, the 99.5% null). Numbered = 4 interior RX sensors '
             '→ cascade board → plate B. 8 discs total; same pattern on BOTH plates (mass-match). Leads short + twisted.')
elif args.role == 'rx':
    notes = ('Grey dashed = the 4 CORNER TX (NCO Block A, keep-out). Numbered = bond an RX SENSOR here, disc CENTER on the '
             'crosshair. Each RX → its own cascade-board channel → one of plate B’s TX. RX leads short + twisted with ground.')
else:
    notes = ('Grey dashed = existing corner PZTs (keep-out). Numbered = drill/bond here, disc CENTER on the crosshair. '
             'Corners are weak strain-couplers (~10%); interior antinodes couple richly. TX leads short + twisted with ground.')
svg.append(f'<text x="{ox:.2f}" y="{ly:.2f}" font-size="2.2" fill="#444" font-family="sans-serif">{notes}</text>')
svg.append('</svg>')
svg_text = "\n".join(svg)

outstem = Path(args.out)
outstem.parent.mkdir(parents=True, exist_ok=True)
svg_path = outstem.with_suffix('.svg')
svg_path.write_text(svg_text)

# ── Foolproof HTML print wrapper (exact scale) ──────────────────────────────
rows = "".join(
    f"<tr><td style='color:{PALETTE[(n-1)%len(PALETTE)]};font-weight:700'>#{n}</td>"
    f"<td>({p[0]:.0f}, {p[1]:.0f}) mm</td><td>{region(p)}</td></tr>"
    for n, p in enumerate(chosen, 1))
if args.role == 'both':
    footer_note = ('Origin = bottom-left. AMBER = the 4 corner TX (NCO Block A, CH1-4, phase-locked — the E9 99.5% null). '
                   'NUMBERED = the 4 interior RX sensors → OPA2134 cascade board → plate B’s 4 TX (see '
                   'companion/cascade_board_wiring). 8 discs total. Bond the SAME pattern on BOTH plates for matched mass '
                   '→ shared band; on plate B use 1 interior disc as the final RX (→ Ch A) and the other 3 as matching mass. '
                   'A PZT can’t TX and RX at once. Verify with direct_wire_census.py after bonding.')
elif args.role == 'rx':
    footer_note = ('Origin = bottom-left. The 4 grey corners are plate A’s phase-locked TX (NCO Block A); the numbered '
                   'discs are the cascade RX SENSORS — each → its own OPA2134 channel → one of plate B’s TX '
                   '(see companion/cascade_board_wiring). Give plate B the SAME 4 corner TX + IDENTICAL mass pattern so '
                   'A and B share a band. A PZT can’t TX and RX at once — these are separate discs from the corners. '
                   'Verify with direct_wire_census.py after bonding.')
else:
    footer_note = ('Origin = bottom-left; SW corner is the TX-to-NCO disc. Layout is symmetric — if your empty corner is '
                   'not SE, mirror the sheet. Model = free-free plate strain coupling (lowest %d modes); the deciding test '
                   'is a direct_wire_census.py after install. Add discs one at a time and re-census; the modal payoff '
                   'saturates by ~4–6 TX/plate.' % M)
html = f"""<!doctype html><html><head><meta charset="utf-8"><title>PZT placement {L:.0f}mm</title>
<style>
  @page {{ size: A4 portrait; margin: 8mm; }}
  * {{ box-sizing: border-box; }}
  body {{ font-family: -apple-system, system-ui, sans-serif; margin: 0; padding: 8mm; color:#222; }}
  .bar {{ background:#fff3cd; border:1px solid #ffe69c; padding:8px 12px; border-radius:6px; margin-bottom:8px; font-size:13px; }}
  button {{ font-size:14px; padding:6px 14px; border-radius:6px; border:1px solid #888; background:#f5f5f5; cursor:pointer; }}
  table {{ border-collapse:collapse; font-size:12px; margin-top:6px; }}
  td,th {{ border:1px solid #ddd; padding:3px 8px; text-align:left; }}
  svg {{ display:block; }}
  @media print {{ .noprint {{ display:none; }} body {{ padding:0; }} }}
<style>
  @page {{ size: A4 portrait; margin: 0; }}
  * {{ box-sizing: border-box; }}
  html, body {{ margin: 0; padding: 0; font-family: -apple-system, system-ui, sans-serif; color:#222; }}
  .wrap {{ padding: 8mm; }}
  .bar {{ background:#fff3cd; border:1px solid #ffe69c; padding:8px 12px; border-radius:6px; margin-bottom:8px; font-size:13px; line-height:1.5; }}
  button {{ font-size:14px; padding:6px 14px; border-radius:6px; border:1px solid #888; background:#f5f5f5; cursor:pointer; }}
  table {{ border-collapse:collapse; font-size:12px; margin-top:6px; }}
  td,th {{ border:1px solid #ddd; padding:3px 8px; text-align:left; }}
  svg {{ display:block; width:{Wsvg:.1f}mm; height:{Hsvg:.1f}mm; }}
  @media print {{
    .noprint {{ display:none !important; }}
    .wrap {{ padding: 0; }}
    svg {{ width:{Wsvg:.1f}mm !important; height:{Hsvg:.1f}mm !important; }}
  }}
</style></head><body>
<div class="wrap">
<div class="bar noprint">
  <b>Print at 100% / "Actual size" — turn OFF "Fit to page" / "Shrink to fit".</b><br>
  <b>CALIBRATE (the file can’t force your printer):</b> after printing, measure the printed <b>plate square</b> — it must be
  exactly <b>100.0&nbsp;mm</b> (and the ruler 50.0&nbsp;mm). If it measures <b>M</b>&nbsp;mm, reprint with printer
  <b>Scale = (100 / M) × your current %</b>, then re-measure. Two passes nails it.
  &nbsp; <button onclick="window.print()">Print</button>
</div>
{svg_text}
<table class="noprint"><tr><th>#</th><th>center (x,y)</th><th>why</th></tr>{rows}</table>
<p class="noprint" style="font-size:12px;color:#555;max-width:170mm">
  {footer_note}</p>
</div>
</body></html>"""
html_path = outstem.with_suffix('.html')
html_path.write_text(html)

print(f"\n  Printable written:")
print(f"    {svg_path}   (scalable, 1:1 in mm)")
print(f"    {html_path}  (open in a browser → Print at 100%)")
print("=" * 74)
