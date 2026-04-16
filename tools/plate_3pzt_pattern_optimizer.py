#!/usr/bin/env python3
"""
Plate 3-PZT Pattern Optimizer
==============================

Simulates a 100 mm x 100 mm x 1 mm fused silica plate with 3 face-mounted
PZT-5A discs (10 mm dia x 1 mm thick) bonded at corners with cyanoacrylate.

Models:
  - Kirchhoff thin-plate eigenfrequencies (simply-supported approximation)
  - PZT mass loading via Rayleigh perturbation (frequency shift)
  - PZT Q-damping via energy partition model (per-mode Q reduction)
  - Perturbation-site mass loading (frequency shifts + degeneracy splitting)
  - TX->RX coupling efficiency (mode shape amplitude at PZT positions)
  - Detectability criterion: SNR > 6 dB at the RX PZT location

Goal: Find perturbation patterns that maximize the number of detectable modes
on the 3-PZT plates (G, D, F -- shelves 3, 4, 5).

Usage:
    python tools/plate_3pzt_pattern_optimizer.py
"""
import numpy as np
from dataclasses import dataclass
from typing import List

# =====================================================================
# Material & geometry constants
# =====================================================================

# Fused silica
RHO_GLASS = 2200.0       # kg/m^3
E_GLASS = 73.0e9         # Pa
NU_GLASS = 0.17          # Poisson's ratio
Q_GLASS = 50_000.0       # intrinsic Q

# Plate geometry (all in SI: meters, kg)
A = 0.100                # plate side length (m)
H = 0.001                # plate thickness (m)
RHO_H = RHO_GLASS * H   # areal mass density (kg/m^2)
M_PLATE = RHO_GLASS * A * A * H  # total plate mass (kg)

# Flexural rigidity D = Eh^3 / (12(1-nu^2))
D_FLEX = E_GLASS * H**3 / (12.0 * (1.0 - NU_GLASS**2))

# PZT-5A (10 mm dia x 1 mm thick)
RHO_PZT = 7750.0
PZT_DIA = 0.010           # m
PZT_THICK = 0.001         # m
PZT_AREA = np.pi * (PZT_DIA / 2)**2
M_PZT = RHO_PZT * PZT_AREA * PZT_THICK  # ~0.609 g
Q_PZT = 80.0
Q_ADHESIVE = 150.0

# Acoustic impedance transmission coefficient
Z_GLASS = RHO_GLASS * 5960.0
Z_PZT = RHO_PZT * 4350.0
T_INTERFACE = 1.0 - ((Z_PZT - Z_GLASS) / (Z_PZT + Z_GLASS))**2

# PZT positions in METERS (physical coordinates on 100 mm plate)
# TX at (5, 95) mm --> SW corner
# RX_NE at (95, 5) mm --> NE corner
# RX_NW at (5, 5) mm --> NW corner
PZT_POSITIONS = [
    (0.005, 0.095),   # TX (SW corner)
    (0.095, 0.005),   # RX_NE (NE corner)
    (0.005, 0.005),   # RX_NW (NW corner)
]
PZT_LABELS = ["TX(SW)", "RX_NE", "RX_NW"]
PZT_POSITIONS_2PZT = PZT_POSITIONS[:2]

# Perturbation mass per site (~0.05 g silicone putty)
M_PERT = 0.05e-3  # kg

# Detection thresholds
SNR_THRESHOLD_DB = 6.0
F_MIN = 200.0
F_MAX = 100_000.0
N_MAX = 30


# =====================================================================
# Physics model — FREE plate with PZT spatial averaging
# =====================================================================
#
# FREE plate mode shapes: cos(n*pi*x/a) * cos(m*pi*y/a)
# Corners have LARGE amplitude (free edges → max displacement).
#
# PZT spatial averaging: a 10mm disc integrates the mode shape
# over its footprint, suppressing high-order modes as sinc():
#   coupling(n) ∝ cos(nπx_c/a) × sinc(n × R_pzt / a)
# where sinc(x) = sin(πx)/(πx).
#
# This naturally cuts off modes with n > ~a/R_pzt ≈ 20, and
# substantially reduces coupling for n > ~8.
#
# Calibration: Q_GLASS_EFF and CONTACT_ENHANCE are tuned so that
# 2-PZT plates detect ~6-8 modes and 3-PZT detect ~3-4 modes,
# matching the April 12/14 census observations.

Q_GLASS_EFF = 15_000.0    # effective Q (includes air + support losses)
CONTACT_ENHANCE = 5.0      # bonded PZT coupling enhancement
PZT_RADIUS = PZT_DIA / 2  # 5mm


def plate_eigenfreq(n: int, m: int) -> float:
    """Free square plate eigenfrequency (Kirchhoff approximation)."""
    return (np.pi / 2.0) * np.sqrt(D_FLEX / RHO_H) * (
        (n / A)**2 + (m / A)**2
    )


def _sinc_factor(n: int) -> float:
    """
    PZT spatial averaging factor for mode index n.
    sinc(n * R_pzt / a) = sin(n*pi*R/a) / (n*pi*R/a)
    Disc of radius R=5mm on plate of side a=100mm.
    """
    x = n * PZT_RADIUS / A  # n * 0.005 / 0.100 = n * 0.05
    if abs(x) < 1e-12:
        return 1.0
    return np.sin(np.pi * x) / (np.pi * x)


def mode_shape_point(n: int, m: int, x: float, y: float) -> float:
    """Point mode shape (signed) for free plate."""
    return np.cos(n * np.pi * x / A) * np.cos(m * np.pi * y / A)


def mode_shape_sq(n: int, m: int, x: float, y: float) -> float:
    """Squared point mode shape at (x,y)."""
    return mode_shape_point(n, m, x, y)**2


def pzt_coupling(n: int, m: int, pzt_x: float, pzt_y: float) -> float:
    """
    Effective PZT coupling: point mode shape × spatial averaging.
    Returns SIGNED coupling (sign matters for interference).
    """
    phi = mode_shape_point(n, m, pzt_x, pzt_y)
    avg = _sinc_factor(n) * _sinc_factor(m)
    return phi * avg


def pzt_coupling_sq(n: int, m: int, pzt_x: float, pzt_y: float) -> float:
    """Squared effective PZT coupling (for energy fraction)."""
    return pzt_coupling(n, m, pzt_x, pzt_y)**2


def pzt_energy_fraction(n: int, m: int, pzt_x: float, pzt_y: float) -> float:
    """
    Fraction of mode energy stored in PZT+adhesive.
    Uses effective coupling including spatial averaging.
    """
    c_sq = pzt_coupling_sq(n, m, pzt_x, pzt_y)
    return (PZT_AREA / (A * A)) * (PZT_THICK / H) * T_INTERFACE * CONTACT_ENHANCE * c_sq


def composite_Q(n: int, m: int, pzt_positions: list) -> float:
    """Composite Q: 1/Q = 1/Q_glass + sum eps_k * (1/Q_pzt + 1/Q_adh)."""
    loss = 1.0 / Q_GLASS_EFF
    for (px, py) in pzt_positions:
        eps = pzt_energy_fraction(n, m, px, py)
        loss += eps * (1.0 / Q_PZT + 1.0 / Q_ADHESIVE)
    return 1.0 / loss


def rayleigh_freq_shift(n: int, m: int, mass: float,
                         x: float, y: float) -> float:
    """Rayleigh perturbation: df/f = -(dm / 2M) * phi^2(x,y)."""
    return -(mass / (2.0 * M_PLATE)) * mode_shape_sq(n, m, x, y)


def pzt_mass_loading_shift(n: int, m: int, pzt_positions: list) -> float:
    """Total fractional frequency shift from PZT mass loading."""
    total = 0.0
    for (px, py) in pzt_positions:
        total += rayleigh_freq_shift(n, m, M_PZT, px, py)
    return total


def coupling_amplitude(n: int, m: int, x: float, y: float) -> float:
    """Effective PZT coupling amplitude (absolute value, with sinc factor)."""
    return abs(pzt_coupling(n, m, x, y))


@dataclass
class ModeInfo:
    n: int
    m: int
    f_bare: float
    f_loaded: float
    Q_eff: float
    tx_coupling: float
    rx_ne_coupling: float
    rx_nw_coupling: float
    snr_ne: float
    snr_nw: float
    detectable_ne: bool
    detectable_nw: bool
    detectable_any: bool
    pert_shift_pct: float


def estimate_snr_db(tx_coupling: float, rx_coupling: float,
                     Q_eff: float) -> float:
    """
    Relative SNR in dB.  SNR ~ Q * |phi_TX| * |phi_RX|.
    Calibrated so that a strong low-order mode at Q=50k gives ~22 dB.
    """
    signal = Q_eff * tx_coupling * rx_coupling
    if signal <= 0:
        return -np.inf
    # Calibrate: strongest 2-PZT mode (low-order, coupling~0.9, Q~800)
    # gives ~22 dB. ref_signal = 800 × 0.9 × 0.9 ≈ 648
    ref_signal = 650.0
    return 20.0 * np.log10(max(signal / ref_signal, 1e-10)) + 22.0


def analyze_plate(pzt_positions: list,
                   perturbation_sites: list,
                   label: str = "") -> List[ModeInfo]:
    """Full analysis: enumerate modes, apply mass loading + Q damping."""
    has_nw = len(pzt_positions) >= 3
    tx_pos = pzt_positions[0]
    rx_ne_pos = pzt_positions[1]
    rx_nw_pos = pzt_positions[2] if has_nw else (0, 0)

    modes = []
    for n in range(1, N_MAX + 1):
        for m in range(1, N_MAX + 1):
            f_bare = plate_eigenfreq(n, m)
            if f_bare < F_MIN * 0.5 or f_bare > F_MAX * 1.5:
                continue

            pzt_shift = pzt_mass_loading_shift(n, m, pzt_positions)
            pert_shift = 0.0
            for (sx, sy) in perturbation_sites:
                pert_shift += rayleigh_freq_shift(n, m, M_PERT, sx, sy)

            f_loaded = f_bare * (1.0 + pzt_shift + pert_shift)
            if f_loaded < F_MIN or f_loaded > F_MAX:
                continue

            Q_eff = composite_Q(n, m, pzt_positions)

            tx_c = coupling_amplitude(n, m, *tx_pos)
            rx_ne_c = coupling_amplitude(n, m, *rx_ne_pos)
            rx_nw_c = coupling_amplitude(n, m, *rx_nw_pos) if has_nw else 0.0

            snr_ne = estimate_snr_db(tx_c, rx_ne_c, Q_eff)
            snr_nw = estimate_snr_db(tx_c, rx_nw_c, Q_eff) if has_nw else -np.inf

            det_ne = snr_ne >= SNR_THRESHOLD_DB
            det_nw = snr_nw >= SNR_THRESHOLD_DB
            det_any = det_ne or det_nw

            modes.append(ModeInfo(
                n=n, m=m, f_bare=f_bare, f_loaded=f_loaded, Q_eff=Q_eff,
                tx_coupling=tx_c, rx_ne_coupling=rx_ne_c,
                rx_nw_coupling=rx_nw_c,
                snr_ne=snr_ne, snr_nw=snr_nw,
                detectable_ne=det_ne, detectable_nw=det_nw,
                detectable_any=det_any,
                pert_shift_pct=pert_shift * 100.0,
            ))

    modes.sort(key=lambda m: m.f_loaded)
    return modes


def count_detectable(modes: List[ModeInfo]) -> dict:
    ne = sum(1 for m in modes if m.detectable_ne)
    nw = sum(1 for m in modes if m.detectable_nw)
    any_path = sum(1 for m in modes if m.detectable_any)
    return {"NE": ne, "NW": nw, "any": any_path, "total_in_band": len(modes)}


def frequency_spread(modes: List[ModeInfo]) -> float:
    det_freqs = sorted([m.f_loaded for m in modes if m.detectable_any])
    if len(det_freqs) < 2:
        return 0.0
    return float(np.mean(np.diff(det_freqs)))


def resolved_peak_count(modes: List[ModeInfo]) -> int:
    """
    Count individually RESOLVABLE peaks in a frequency sweep.

    Two modes are unresolved (appear as one peak) if their frequency
    difference is less than the wider of their linewidths.
    Degenerate (n,m)/(m,n) pairs count as one peak unless split by
    perturbation.

    This is the physically meaningful metric: how many peaks will
    the sweep measurement actually see?
    """
    det_modes = sorted(
        [m for m in modes if m.detectable_any],
        key=lambda m: m.f_loaded
    )
    if not det_modes:
        return 0

    # Merge modes that are within linewidth of each other
    peaks = []
    current_cluster = [det_modes[0]]
    for m in det_modes[1:]:
        prev = current_cluster[-1]
        lw = max(prev.f_loaded / prev.Q_eff, m.f_loaded / m.Q_eff)
        if m.f_loaded - prev.f_loaded <= lw:
            current_cluster.append(m)
        else:
            peaks.append(current_cluster)
            current_cluster = [m]
    peaks.append(current_cluster)
    return len(peaks)


def degeneracy_splitting_score(modes: List[ModeInfo]) -> int:
    """Count (n,m)/(m,n) pairs that are split wider than linewidth."""
    det_modes = [m for m in modes if m.detectable_any]
    pairs_seen = set()
    split_count = 0
    for m1 in det_modes:
        for m2 in det_modes:
            if m1.n == m2.m and m1.m == m2.n and m1.n != m1.m:
                pair_key = (min(m1.n, m1.m), max(m1.n, m1.m))
                if pair_key in pairs_seen:
                    continue
                pairs_seen.add(pair_key)
                lw = max(m1.f_loaded / m1.Q_eff, m2.f_loaded / m2.Q_eff)
                if abs(m1.f_loaded - m2.f_loaded) > lw:
                    split_count += 1
    return split_count


# =====================================================================
# Perturbation pattern library
# =====================================================================

def mm_to_m(sites_mm: list) -> list:
    """Convert (x_mm, y_mm) list to meters."""
    return [(x / 1000.0, y / 1000.0) for (x, y) in sites_mm]


# Existing physical patterns (from plate_perturbation_templates.html)
PATTERNS = {
    "A_center_quarter": mm_to_m([
        (50, 50), (25, 25), (75, 25), (25, 75), (75, 75)
    ]),
    "B_edge_midpoints": mm_to_m([
        (50, 15), (50, 85), (15, 50), (85, 50), (30, 70)
    ]),
    "C_third_grid": mm_to_m([
        (33, 33), (67, 33), (33, 67), (67, 67), (50, 33), (50, 67)
    ]),
    "D_diagonal": mm_to_m([
        (20, 20), (40, 35), (50, 50), (60, 65), (80, 80)
    ]),
    "E_diagonal_dup": mm_to_m([
        (20, 20), (40, 35), (50, 50), (60, 65), (80, 80)
    ]),
    "F_antidiag_zigzag": mm_to_m([
        (20, 80), (35, 55), (50, 50), (65, 35), (80, 20)
    ]),
    "G_asymm_pentagon": mm_to_m([
        (30, 70), (60, 80), (80, 50), (65, 20), (25, 35)
    ]),
}


# --- New candidate pattern generators ---

def make_r2_pattern(n_sites: int, seed_offset: float = 0.5) -> list:
    """R2 quasi-random placement (Roberts 2018), avoiding PZT corners. Returns meters."""
    phi1 = 0.7548776662466927
    phi2 = 0.5698402909980532
    sites = []
    k = 0
    while len(sites) < n_sites:
        frac_x = ((k + seed_offset) * phi1) % 1.0
        frac_y = ((k + seed_offset) * phi2) % 1.0
        x = frac_x * A
        y = frac_y * A
        k += 1
        too_close = False
        for (px, py) in PZT_POSITIONS:
            if np.sqrt((x - px)**2 + (y - py)**2) < 0.012:
                too_close = True
                break
        if x < 0.008 or x > 0.092 or y < 0.008 or y > 0.092:
            too_close = True
        if not too_close:
            sites.append((x, y))
        if k > 1000:
            break
    return sites


def make_asymmetric_diagonal(n_sites: int = 5) -> list:
    """Diagonal that breaks x<->y mirror symmetry. Returns meters."""
    sites = []
    for i in range(n_sites):
        frac_x = 0.15 + 0.70 * i / (n_sites - 1)
        frac_y = 0.30 + 0.40 * (frac_x / 0.85)**1.5
        x, y = frac_x * A, frac_y * A
        for (px, py) in PZT_POSITIONS:
            if np.sqrt((x - px)**2 + (y - py)**2) < 0.012:
                y = min(0.088, y + 0.015)
        sites.append((x, y))
    return sites


def make_antinode_targeted(n_range: range, m_range: range, n_sites: int = 6) -> list:
    """Place sites at antinodes of target mode groups. Returns meters."""
    grid = np.linspace(0.010, 0.090, 50)
    xx, yy = np.meshgrid(grid, grid)
    sensitivity = np.zeros_like(xx)
    for n in n_range:
        for m in m_range:
            sensitivity += np.cos(n * np.pi * xx / A)**2 * np.cos(m * np.pi * yy / A)**2
    for (px, py) in PZT_POSITIONS:
        dist = np.sqrt((xx - px)**2 + (yy - py)**2)
        sensitivity[dist < 0.012] = 0
    best_sites = []
    for _ in range(n_sites):
        idx = np.unravel_index(np.argmax(sensitivity), sensitivity.shape)
        sx, sy = float(xx[idx]), float(yy[idx])
        best_sites.append((sx, sy))
        dist = np.sqrt((xx - sx)**2 + (yy - sy)**2)
        sensitivity[dist < 0.012] = 0
    return best_sites


def make_off_diagonal_cluster(n_sites: int = 5) -> list:
    """Sites in SE quadrant (no PZT). Returns meters."""
    sites = []
    for i in range(n_sites):
        t = i / (n_sites - 1)
        x = (0.55 + 0.33 * t) * A
        y = (0.15 + 0.28 * np.sin(np.pi * t * 0.8)) * A
        sites.append((x, y))
    return sites


def make_symmetry_breaker(n_sites: int = 6) -> list:
    """Golden spiral -- maximum asymmetry. Returns meters."""
    phi = (1 + np.sqrt(5)) / 2
    sites = []
    for k in range(n_sites):
        r = (0.15 + 0.25 * np.sqrt((k + 1) / n_sites)) * A
        theta = 2 * np.pi * k / phi**2
        x = 0.050 + r * np.cos(theta)
        y = 0.050 + r * np.sin(theta)
        x = np.clip(x, 0.010, 0.090)
        y = np.clip(y, 0.010, 0.090)
        ok = True
        for (px, py) in PZT_POSITIONS:
            if np.sqrt((x - px)**2 + (y - py)**2) < 0.012:
                ok = False
        if ok:
            sites.append((float(x), float(y)))
    return sites


def make_edge_parallel(n_sites: int = 5) -> list:
    """Sites along y=40 mm. Returns meters."""
    sites = []
    for i in range(n_sites):
        x = (0.15 + 0.70 * i / (n_sites - 1)) * A
        y = 0.040
        sites.append((x, y))
    return sites


def make_scattered_interior(n_sites: int = 7) -> list:
    """Halton sequence scattered sites. Returns meters."""
    def halton(i, base):
        f, r = 1.0, 0.0
        while i > 0:
            f /= base
            r += f * (i % base)
            i //= base
        return r

    sites = []
    k = 1
    while len(sites) < n_sites and k < 200:
        x = (halton(k, 2) * 0.76 + 0.12) * A
        y = (halton(k, 3) * 0.76 + 0.12) * A
        k += 1
        ok = True
        for (px, py) in PZT_POSITIONS:
            if np.sqrt((x - px)**2 + (y - py)**2) < 0.012:
                ok = False
        if ok:
            sites.append((x, y))
    return sites


def make_weighted_antinode_6(n_sites: int = 6) -> list:
    """Weight antinodes by 1/(n^2+m^2), penalize y=x diagonal. Returns meters."""
    grid = np.linspace(0.010, 0.090, 60)
    xx, yy = np.meshgrid(grid, grid)
    sensitivity = np.zeros_like(xx)
    for n in range(1, 12):
        for m in range(1, 12):
            weight = 1.0 / (n**2 + m**2)
            sensitivity += weight * np.cos(n * np.pi * xx / A)**2 * np.cos(m * np.pi * yy / A)**2
    for (px, py) in PZT_POSITIONS:
        dist = np.sqrt((xx - px)**2 + (yy - py)**2)
        sensitivity[dist < 0.012] = 0
    diag_dist = np.abs(xx - yy)
    sensitivity *= (0.3 + 0.7 * np.minimum(diag_dist / 0.020, 1.0))
    sites = []
    for _ in range(n_sites):
        idx = np.unravel_index(np.argmax(sensitivity), sensitivity.shape)
        sx, sy = float(xx[idx]), float(yy[idx])
        sites.append((sx, sy))
        dist = np.sqrt((xx - sx)**2 + (yy - sy)**2)
        sensitivity[dist < 0.010] = 0
    return sites


def make_high_order_splitter(n_sites: int = 6) -> list:
    """Target high-order mode antinodes (n,m >= 3). Returns meters."""
    return make_antinode_targeted(range(3, 8), range(3, 8), n_sites)


# Build candidate pattern dict (existing + generated)
CANDIDATE_PATTERNS = dict(PATTERNS)
CANDIDATE_PATTERNS.update({
    "R2_quasi_6": make_r2_pattern(6),
    "asymm_diagonal_5": make_asymmetric_diagonal(5),
    "antinode_low_6": make_antinode_targeted(range(1, 6), range(1, 6), 6),
    "antinode_mid_6": make_antinode_targeted(range(2, 7), range(2, 7), 6),
    "off_diagonal_5": make_off_diagonal_cluster(5),
    "symm_breaker_6": make_symmetry_breaker(6),
    "edge_parallel_5": make_edge_parallel(5),
    "scattered_7": make_scattered_interior(7),
    "weighted_antinode_6": make_weighted_antinode_6(6),
    "high_order_split_6": make_high_order_splitter(6),
})


# =====================================================================
# Main analysis
# =====================================================================

def run_comparison():
    print("=" * 90)
    print("PLATE 3-PZT PATTERN OPTIMIZER")
    print("=" * 90)
    print(f"\nPlate: {A*1000:.0f} mm x {A*1000:.0f} mm x {H*1000:.1f} mm fused silica")
    print(f"PZT: {PZT_DIA*1000:.0f} mm dia x {PZT_THICK*1000:.0f} mm, mass = {M_PZT*1000:.3f} g each")
    print(f"Plate mass: {M_PLATE*1000:.2f} g")
    print(f"3-PZT total: {3*M_PZT*1000:.3f} g = {3*M_PZT/M_PLATE*100:.1f}% of plate mass")
    print(f"Perturbation mass/site: {M_PERT*1e6:.0f} ug")
    print(f"Frequency range: {F_MIN:.0f} - {F_MAX:.0f} Hz")
    print(f"Detection threshold: SNR >= {SNR_THRESHOLD_DB:.0f} dB")
    print(f"\nPZT positions (mm):")
    for label, (px, py) in zip(PZT_LABELS, PZT_POSITIONS):
        print(f"  {label}: ({px*1000:.1f}, {py*1000:.1f})")

    # Baseline: no perturbation
    print(f"\n{'=' * 90}")
    print("BASELINE: No perturbation sites")
    print(f"{'=' * 90}")

    modes_2pzt_bare = analyze_plate(PZT_POSITIONS_2PZT, [], "2-PZT bare")
    modes_3pzt_bare = analyze_plate(PZT_POSITIONS, [], "3-PZT bare")
    c2 = count_detectable(modes_2pzt_bare)
    c3 = count_detectable(modes_3pzt_bare)
    rp_2 = resolved_peak_count(modes_2pzt_bare)
    rp_3 = resolved_peak_count(modes_3pzt_bare)
    print(f"\n  2-PZT (TX+RX_NE):  {c2['NE']:>3} modes above threshold  |  {rp_2:>3} resolved peaks")
    print(f"  3-PZT (TX+NE+NW):  {c3['any']:>3} modes above threshold  |  {rp_3:>3} resolved peaks")
    print(f"  Peak loss from 3rd PZT: {rp_2 - rp_3}")
    print(f"\n  NOTE: With no perturbation, degenerate (n,m)/(m,n) pairs are")
    print(f"  UNRESOLVED — they appear as ONE peak.  Perturbation splits them.")

    # Sweep all patterns
    print(f"\n{'=' * 90}")
    print("PATTERN COMPARISON: 3-PZT — resolved peaks (what the sweep actually sees)")
    print(f"{'=' * 90}")
    print(f"\n  {'Pattern':<28} {'Sites':>5}  {'Peaks':>5} {'Split':>5}  {'MinGap':>8}  {'Score':>6}")
    print(f"  {'_' * 75}")

    results = []
    for name, sites in sorted(CANDIDATE_PATTERNS.items()):
        modes = analyze_plate(PZT_POSITIONS, sites, name)
        peaks = resolved_peak_count(modes)
        splits = degeneracy_splitting_score(modes)

        # minimum gap: smallest spacing between resolved peaks
        det_freqs = sorted([m.f_loaded for m in modes if m.detectable_any])
        gaps = np.diff(det_freqs) if len(det_freqs) > 1 else [0]
        # Filter to only inter-peak gaps (> linewidth)
        real_gaps = [g for g in gaps if g > 0.1]
        min_gap = min(real_gaps) if real_gaps else 0

        # Score: resolved peaks (primary) + splitting bonus + gap bonus
        score = peaks + 0.5 * splits + 0.01 * min_gap

        results.append({
            'name': name,
            'sites': len(sites),
            'peaks': peaks,
            'splits': splits,
            'min_gap': min_gap,
            'score': score,
            'site_positions': sites,
        })

        print(f"  {name:<26} {len(sites):>5}  {peaks:>5} {splits:>5}  {min_gap:>6.1f} Hz  {score:>6.1f}")

    results.sort(key=lambda r: r['score'], reverse=True)

    print(f"\n{'=' * 90}")
    print("TOP 5 PATTERNS (by resolved-peak score)")
    print(f"{'=' * 90}")

    for i, r in enumerate(results[:5]):
        print(f"\n  #{i+1}: {r['name']}  (score = {r['score']:.1f})")
        print(f"       Resolved peaks: {r['peaks']}")
        print(f"       Degeneracy splits: {r['splits']}")
        print(f"       Min peak gap: {r['min_gap']:.1f} Hz")
        print(f"       Sites (mm): ", end="")
        for (x, y) in r['site_positions']:
            print(f"({x*1000:.1f},{y*1000:.1f}) ", end="")
        print()

    # Also compare 2-PZT with these patterns
    print(f"\n{'=' * 90}")
    print("2-PZT COMPARISON: Same patterns on 2-PZT plates")
    print(f"{'=' * 90}")
    print(f"\n  {'Pattern':<28} {'2-PZT peaks':>11}  {'3-PZT peaks':>11}  {'Delta':>6}")
    print(f"  {'_' * 65}")
    for r in results[:10]:
        modes_2 = analyze_plate(PZT_POSITIONS_2PZT, r['site_positions'])
        rp2 = resolved_peak_count(modes_2)
        print(f"  {r['name']:<26} {rp2:>11}  {r['peaks']:>11}  {r['peaks'] - rp2:>+6}")
        print(f"       Sites (mm): ", end="")
        for (x, y) in r['site_positions']:
            print(f"({x*1000:.1f},{y*1000:.1f}) ", end="")
        print()

    # Detailed mode table for the winner — show first 30 resolved peaks
    winner = results[0]
    print(f"\n{'=' * 90}")
    print(f"WINNER MODE TABLE: {winner['name']} — first 30 detectable modes")
    print(f"{'=' * 90}")

    modes = analyze_plate(PZT_POSITIONS, winner['site_positions'], winner['name'])
    det_modes = [m for m in modes if m.detectable_any][:30]
    print(f"\n  {'(n,m)':<8} {'f_loaded':>9} {'Q_eff':>8} {'Coupling':>8} {'SNR_NE':>7} {'df_pert':>8}  {'Split?'}")
    print(f"  {'_' * 70}")
    for m in det_modes:
        # Check if this mode is part of a split degenerate pair
        split = ""
        if m.n != m.m:
            partner = [p for p in modes if p.n == m.m and p.m == m.n and p.detectable_any]
            if partner:
                lw = max(m.f_loaded / m.Q_eff, partner[0].f_loaded / partner[0].Q_eff)
                gap = abs(m.f_loaded - partner[0].f_loaded)
                if gap > lw:
                    split = f"SPLIT ({gap:.1f} Hz gap, {gap/lw:.1f}x lw)"
                else:
                    split = f"unresolved ({gap:.1f} Hz < {lw:.1f} Hz lw)"
            else:
                split = "partner killed"
        print(f"  ({m.n},{m.m}){'':<3} {m.f_loaded:>9.0f} {m.Q_eff:>8.0f} "
              f"{m.tx_coupling:>8.4f} {m.snr_ne:>7.1f} {m.pert_shift_pct:>7.3f}%  {split}")

    # Physical recommendation
    print(f"\n{'=' * 90}")
    print("RECOMMENDATION FOR PHYSICAL PLATES")
    print(f"{'=' * 90}")
    print(f"\n  Best pattern: {winner['name']}")
    print(f"  Place putty masses at these positions (mm from SW corner):")
    for i, (x, y) in enumerate(winner['site_positions']):
        print(f"    Site {i+1}: ({x*1000:>5.1f}, {y*1000:>5.1f}) mm")
    print(f"\n  Expected improvement: {winner['splits']} degenerate pairs split")
    print(f"  on 3-PZT plates (G, D, F)")

    # Compare top 3 patterns on both 2-PZT and 3-PZT
    print(f"\n  Comparison with current patterns:")
    for existing in ["D_diagonal", "F_antidiag_zigzag", "G_asymm_pentagon"]:
        if existing in CANDIDATE_PATTERNS:
            m_ex = analyze_plate(PZT_POSITIONS, CANDIDATE_PATTERNS[existing])
            rp_ex = resolved_peak_count(m_ex)
            sp_ex = degeneracy_splitting_score(m_ex)
            print(f"    {existing:26s}: {rp_ex:>3} peaks, {sp_ex:>3} splits")
    print(f"    {winner['name']:26s}: {winner['peaks']:>3} peaks, {winner['splits']:>3} splits  <-- RECOMMENDED")

    return results


if __name__ == "__main__":
    results = run_comparison()
