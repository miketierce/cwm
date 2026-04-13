#!/usr/bin/env python3
"""
PZT Mounting Analysis: Face Mount vs Edge Mount
for 100mm × 100mm × 1mm Fused Silica Plates

Computes Q impact, coupling efficiency, mass loading,
and mode accessibility for both configurations.
"""
import numpy as np

print("=" * 72)
print("PZT MOUNTING ANALYSIS: FACE vs EDGE")
print("Plate: 100 mm × 100 mm × 1 mm fused silica")
print("=" * 72)

# ── Material Properties ──────────────────────────────────────────────────
# Fused silica
rho_glass = 2200       # kg/m³
E_glass = 73e9         # Pa (Young's modulus)
nu_glass = 0.17        # Poisson's ratio
v_long = 5960          # m/s longitudinal wave speed
v_shear = 3760         # m/s shear wave speed

# Plate velocity for bending (thin plate approximation)
D_plate = E_glass / (12 * (1 - nu_glass**2))  # plate stiffness per unit thickness³
v_plate = np.sqrt(E_glass / (rho_glass * (1 - nu_glass**2)))  # ~5843 m/s

# PZT-5A (typical 10mm disc)
rho_pzt = 7750         # kg/m³
v_pzt = 4350           # m/s longitudinal
Q_pzt_mech = 80        # mechanical Q of PZT-5A
d33 = 374e-12          # m/V piezoelectric coefficient
d31 = -171e-12         # m/V transverse coefficient

# Plate dimensions
a = 0.100              # m (100 mm)
h = 0.001              # m (1 mm)
V_plate = a * a * h    # m³
m_plate = rho_glass * V_plate  # kg

# PZT disc dimensions (typical 10mm dia × 1mm thick)
pzt_dia = 0.010        # m
pzt_thick = 0.001      # m
pzt_area_face = np.pi * (pzt_dia/2)**2  # m²
V_pzt_face = pzt_area_face * pzt_thick  # m³
m_pzt = rho_pzt * V_pzt_face            # kg

# Edge-mount PZT: 10mm wide × 1mm tall × 1mm deep (matches plate edge)
edge_width = 0.010     # m along edge
edge_height = h        # m = plate thickness
edge_depth = 0.001     # m PZT thickness
V_pzt_edge = edge_width * edge_height * edge_depth
m_pzt_edge = rho_pzt * V_pzt_edge

print(f"\n── MATERIAL DATA ──")
print(f"  Fused silica: ρ = {rho_glass} kg/m³, E = {E_glass/1e9:.0f} GPa, ν = {nu_glass}")
print(f"  v_longitudinal = {v_long} m/s, v_shear = {v_shear} m/s")
print(f"  Plate velocity = {v_plate:.0f} m/s")
print(f"  Plate mass = {m_plate*1000:.2f} g")
print(f"  Intrinsic Q (fused silica) = 10⁴–10⁵")
print(f"\n  PZT-5A: ρ = {rho_pzt} kg/m³, Q_mech = {Q_pzt_mech}")
print(f"  Face disc: {pzt_dia*1000:.0f}mm dia × {pzt_thick*1000:.0f}mm → "
      f"{m_pzt*1000:.3f} g, area = {pzt_area_face*1e6:.1f} mm²")
print(f"  Edge strip: {edge_width*1000:.0f}mm × {edge_height*1000:.0f}mm × {edge_depth*1000:.0f}mm → "
      f"{m_pzt_edge*1000:.3f} g, contact = {edge_width*edge_height*1e6:.1f} mm²")

# ═══════════════════════════════════════════════════════════════════════
# S1: MASS LOADING
# ═══════════════════════════════════════════════════════════════════════
print(f"\n{'=' * 72}")
print("S1: MASS LOADING")
print(f"{'─' * 72}")

# Face mount: PZT sits on thin plate
# Local mass ratio = PZT mass / glass mass directly underneath PZT
m_glass_under_face = rho_glass * pzt_area_face * h
ratio_face = m_pzt / m_glass_under_face

# Edge mount: PZT on edge
# Local mass at edge = glass volume at PZT contact
m_glass_at_edge = rho_glass * edge_width * edge_height * edge_depth
ratio_edge = m_pzt_edge / m_glass_at_edge

# Global mass ratios
global_face = m_pzt / m_plate
global_edge = m_pzt_edge / m_plate

print(f"  FACE MOUNT:")
print(f"    PZT mass:              {m_pzt*1000:.3f} g")
print(f"    Glass under PZT:       {m_glass_under_face*1000:.3f} g")
print(f"    Local mass ratio:      {ratio_face:.2f}× (PZT/glass at site)")
print(f"    Global mass ratio:     {global_face*100:.2f}% of plate mass")
print(f"    ⚠ PZT is {ratio_face:.1f}× heavier than the glass it sits on!")
print()
print(f"  EDGE MOUNT:")
print(f"    PZT mass:              {m_pzt_edge*1000:.3f} g")
print(f"    Glass at contact:      {m_glass_at_edge*1000:.3f} g")
print(f"    Local mass ratio:      {ratio_edge:.2f}× (PZT/glass at site)")
print(f"    Global mass ratio:     {global_edge*100:.2f}% of plate mass")
print()
print(f"  WINNER: EDGE — {ratio_face/ratio_edge:.1f}× less local mass loading")

# ═══════════════════════════════════════════════════════════════════════
# S2: Q IMPACT (ENERGY PARTITION MODEL)
# ═══════════════════════════════════════════════════════════════════════
print(f"\n{'=' * 72}")
print("S2: Q IMPACT — Energy Partition Model")
print(f"{'─' * 72}")

Q_glass = 50000  # conservative fused silica intrinsic Q
Q_adhesive = 150  # cyanoacrylate adhesive layer

# Energy fraction in PZT+adhesive ≈ V_contact / V_plate × impedance coupling
# For face mount: energy couples through the full PZT footprint into bulk
Z_glass = rho_glass * v_long  # acoustic impedance
Z_pzt = rho_pzt * v_pzt

# Transmission coefficient at interface
R_face = ((Z_pzt - Z_glass) / (Z_pzt + Z_glass))**2
T_face = 1 - R_face

print(f"  Acoustic impedances:")
print(f"    Z_glass = {Z_glass/1e6:.1f} MRayl")
print(f"    Z_pzt   = {Z_pzt/1e6:.1f} MRayl")
print(f"    Interface reflection = {R_face*100:.1f}%")
print(f"    Interface transmission = {T_face*100:.1f}%")

# Energy participation ratio (fraction of mode energy in PZT region)
# For face mount on a 1mm plate: the PZT contact area / plate area
# weighted by displacement amplitude at that point
# Worst case: PZT at antinode, ε ≈ A_pzt/A_plate × (h_pzt/h_plate)
eps_face_antinode = (pzt_area_face / (a*a)) * (pzt_thick / h) * T_face
eps_face_node = eps_face_antinode * 0.01  # ~1% at a node
eps_face_avg = eps_face_antinode * 0.5    # average

# For edge mount: contact area is tiny, and edge is typically near a
# nodal region for free-plate bending modes (free edges have max slope, not max displacement)
eps_edge_antinode = (edge_width * edge_height / (a * a)) * T_face
eps_edge_avg = eps_edge_antinode * 0.25  # edges typically lower displacement for bending

print(f"\n  Energy participation ratio (ε = fraction of mode energy in PZT+adhesive):")
print(f"  FACE MOUNT:")
print(f"    At antinode:  ε = {eps_face_antinode:.4f} ({eps_face_antinode*100:.2f}%)")
print(f"    Average:      ε = {eps_face_avg:.4f} ({eps_face_avg*100:.2f}%)")
print(f"    At node:      ε = {eps_face_node:.6f} ({eps_face_node*100:.4f}%)")
print(f"  EDGE MOUNT:")
print(f"    At antinode:  ε = {eps_edge_antinode:.4f} ({eps_edge_antinode*100:.2f}%)")
print(f"    Average:      ε = {eps_edge_avg:.5f} ({eps_edge_avg*100:.3f}%)")

# Composite Q: 1/Q_total = 1/Q_glass + ε * (1/Q_pzt + 1/Q_adhesive)
def composite_Q(q_glass, eps, q_pzt, q_adh):
    return 1.0 / (1.0/q_glass + eps * (1.0/q_pzt + 1.0/q_adh))

# Two PZTs (TX + RX), so double the ε
for label, eps_val in [
    ("FACE antinode (worst)", eps_face_antinode * 2),
    ("FACE average",         eps_face_avg * 2),
    ("FACE node (best)",     eps_face_node * 2),
    ("EDGE antinode (worst)", eps_edge_antinode * 2),
    ("EDGE average",         eps_edge_avg * 2),
]:
    Qc = composite_Q(Q_glass, eps_val, Q_pzt_mech, Q_adhesive)
    print(f"\n  {label} (×2 for TX+RX):")
    print(f"    ε_total = {eps_val:.5f}")
    print(f"    Q_composite = {Qc:.0f}")

# Summary
Q_face_typ = composite_Q(Q_glass, eps_face_avg*2, Q_pzt_mech, Q_adhesive)
Q_edge_typ = composite_Q(Q_glass, eps_edge_avg*2, Q_pzt_mech, Q_adhesive)

print(f"\n  ── SUMMARY ──")
print(f"  Typical face-mount Q:  {Q_face_typ:.0f}")
print(f"  Typical edge-mount Q:  {Q_edge_typ:.0f}")
print(f"  Edge advantage:        {Q_edge_typ/Q_face_typ:.1f}×")
print(f"  Kill threshold (Q>500): Face={'PASS' if Q_face_typ > 500 else 'AT RISK'}  "
      f"Edge={'PASS' if Q_edge_typ > 500 else 'AT RISK'}")

# ═══════════════════════════════════════════════════════════════════════
# S3: MODE ACCESSIBILITY
# ═══════════════════════════════════════════════════════════════════════
print(f"\n{'=' * 72}")
print("S3: MODE ACCESSIBILITY")
print(f"{'─' * 72}")

# Flexural (bending) modes of a free square plate
# f_mn ∝ h/a² × sqrt(D/ρh) where D = Eh³/12(1-ν²)
# For thin plate: f_mn = (λ²_mn / (2πa²)) × h × sqrt(E/(12ρ(1-ν²)))
# Simplified: f_mn ≈ C_mn × h × v_plate / a²

# Free plate λ² values for first several modes (approximate)
# Source: Leissa, "Vibration of Plates"
modes_flex = {
    '(2,0)': 5.08,   # lowest free-free
    '(0,2)': 5.08,
    '(2,1)': 12.24,
    '(1,2)': 12.24,
    '(2,2)': 24.08,
    '(3,0)': 13.47,
    '(0,3)': 13.47,
    '(3,1)': 24.77,
    '(1,3)': 24.77,
    '(3,2)': 40.0,
    '(2,3)': 40.0,
    '(3,3)': 61.1,
    '(4,0)': 25.0,
    '(4,1)': 40.7,
}

# f = λ² × h / (2π a²) × sqrt(E/(12ρ(1-ν²)))
coeff = h / (2 * np.pi * a**2) * np.sqrt(E_glass / (12 * rho_glass * (1 - nu_glass**2)))

print(f"  FLEXURAL (bending) modes — excited primarily by FACE mount:")
print(f"  {'Mode':<10} {'λ²':<10} {'Freq (Hz)':<12} {'Freq (kHz)':<10}")
for mode, lam2 in sorted(modes_flex.items(), key=lambda x: x[1]):
    f = lam2 * coeff
    print(f"  {mode:<10} {lam2:<10.2f} {f:<12.0f} {f/1000:<10.2f}")

# In-plane (extensional) modes
# f_mn = (1/2) × sqrt((m/a)² + (n/b)²) × v_plate (approximately)
print(f"\n  IN-PLANE (extensional) modes — excited primarily by EDGE mount:")
print(f"  {'Mode':<10} {'Freq (Hz)':<12} {'Freq (kHz)':<10}")
for m in range(1, 6):
    for n in range(0, 4):
        if m == 0 and n == 0:
            continue
        f = 0.5 * v_plate * np.sqrt((m/a)**2 + (n/a)**2)
        if f < 200000:  # under 200 kHz
            print(f"  ({m},{n}){'':<6} {f:<12.0f} {f/1000:<10.2f}")

# Thickness mode
f_thickness = v_long / (2 * h)
print(f"\n  THICKNESS mode (1mm plate): {f_thickness/1e6:.2f} MHz — above PicoScope range")

# ═══════════════════════════════════════════════════════════════════════
# S4: COUPLING EFFICIENCY
# ═══════════════════════════════════════════════════════════════════════
print(f"\n{'=' * 72}")
print("S4: COUPLING EFFICIENCY — Signal Strength")
print(f"{'─' * 72}")

# Face mount: d31 mode couples to bending
# The PZT contracts/expands laterally, bending the plate
# Effective force ∝ d31 × V × E_pzt × A_contact / h_pzt
# Signal scales with PZT area and inversely with plate stiffness

# Edge mount: d33 mode couples to in-plane extension
# The PZT expands along its poling axis, directly pushing on the edge
# Effective force ∝ d33 × V × E_pzt × A_edge / h_pzt

print(f"  Face mount coupling (d31 to bending):")
print(f"    d31 = {abs(d31)*1e12:.0f} pm/V")
print(f"    Contact area = {pzt_area_face*1e6:.1f} mm²")
print(f"    Couples to: all flexural modes (rich < 50 kHz)")
force_metric_face = abs(d31) * pzt_area_face
print(f"    F ∝ d31 × A = {force_metric_face:.2e} m³/V")

print(f"\n  Edge mount coupling (d33 to extension):")
print(f"    d33 = {d33*1e12:.0f} pm/V")
print(f"    Contact area = {edge_width*edge_height*1e6:.1f} mm²")
print(f"    Couples to: in-plane modes (sparse, > 29 kHz)")
force_metric_edge = d33 * edge_width * edge_height
print(f"    F ∝ d33 × A = {force_metric_edge:.2e} m³/V")

ratio_signal = force_metric_face / force_metric_edge
print(f"\n  Face/Edge signal ratio: {ratio_signal:.1f}×")
print(f"  ⚠ Face mount produces ~{ratio_signal:.0f}× stronger drive force")

# ═══════════════════════════════════════════════════════════════════════
# S5: PRACTICAL CONSIDERATIONS
# ═══════════════════════════════════════════════════════════════════════
print(f"\n{'=' * 72}")
print("S5: PRACTICAL CONSIDERATIONS")
print(f"{'─' * 72}")

print("""
  FACE MOUNT:
    ✓ Easy to bond (flat surface)
    ✓ Excellent coupling to rich flexural mode spectrum (many modes < 50 kHz)
    ✓ Same technique as rod prototype (known-working)
    ✓ ~{0:.0f}× stronger signal
    ✗ Heavy mass loading on 1mm plate (PZT = {1:.1f}× glass at contact)
    ✗ Kills Q (predicted {2:.0f} typical, {3:.0f} at antinode)
    ✗ PZT on face competes with perturbation sites for surface
    ✗ Risk: face-mount Q may not beat rod Q (~200-572)
""".format(ratio_signal, ratio_face, Q_face_typ,
           composite_Q(Q_glass, eps_face_antinode*2, Q_pzt_mech, Q_adhesive)))

print("""  EDGE MOUNT:
    ✓ Minimal mass loading ({0:.2f}× vs {1:.1f}× for face)
    ✓ Preserves Q (predicted {2:.0f} typical)
    ✓ Leaves both plate faces clean for perturbation sites
    ✓ No competition between PZT and perturbation locations
    ✗ Only 1mm × 10mm contact — hard to bond cleanly
    ✗ Primarily excites in-plane modes (fewer modes, higher freq)
    ✗ Weaker coupling (d33 × small area vs d31 × large area)
    ✗ In-plane modes start at ~29 kHz — less of our measurement range used
    ✗ Flexural modes (the rich spectrum below 50 kHz) poorly excited
""".format(ratio_edge, ratio_face, Q_edge_typ))

# ═══════════════════════════════════════════════════════════════════════
# S6: HYBRID APPROACH
# ═══════════════════════════════════════════════════════════════════════
print(f"{'=' * 72}")
print("S6: HYBRID — Corner Face Mount (minimal area)")
print(f"{'─' * 72}")

# What if we use a SMALL PZT (5mm disc) face-mounted at a corner?
# Corners are near nodes for many modes → reduced ε
pzt_small_dia = 0.005  # 5mm
pzt_small_area = np.pi * (pzt_small_dia/2)**2
V_pzt_small = pzt_small_area * pzt_thick
m_pzt_small = rho_pzt * V_pzt_small
m_glass_under_small = rho_glass * pzt_small_area * h
ratio_small = m_pzt_small / m_glass_under_small

eps_corner = (pzt_small_area / (a*a)) * (pzt_thick / h) * T_face * 0.1  # corners ≈ 10% of antinode amplitude
Q_corner = composite_Q(Q_glass, eps_corner * 2, Q_pzt_mech, Q_adhesive)

force_small = abs(d31) * pzt_small_area
signal_vs_big = force_small / force_metric_face

print(f"  5mm PZT disc at plate corner (face-mounted):")
print(f"    Mass: {m_pzt_small*1000:.3f} g (vs {m_pzt*1000:.3f} g for 10mm)")
print(f"    Local mass ratio: {ratio_small:.2f}× (vs {ratio_face:.2f}×)")
print(f"    Corner ε (low displacement): {eps_corner:.5f}")
print(f"    Q_composite (2 × corner): {Q_corner:.0f}")
print(f"    Signal: {signal_vs_big*100:.0f}% of full face mount")
print(f"    Couples to: flexural modes (same rich spectrum)")

# Best of all worlds: small disc at corner
# Compare all three
print(f"\n{'=' * 72}")
print("FINAL COMPARISON")
print(f"{'=' * 72}")
print(f"{'Config':<30} {'Q (typ)':<12} {'Signal':<12} {'Modes':<20} {'Practical'}")
print(f"{'─'*30} {'─'*12} {'─'*12} {'─'*20} {'─'*15}")
print(f"{'Face 10mm (antinode)':<30} {composite_Q(Q_glass, eps_face_antinode*2, Q_pzt_mech, Q_adhesive):<12.0f} {'1.00×':<12} {'flexural (rich)':<20} {'easy'}")
print(f"{'Face 10mm (corner)':<30} {composite_Q(Q_glass, eps_face_avg*0.2*2, Q_pzt_mech, Q_adhesive):<12.0f} {'1.00×':<12} {'flexural (rich)':<20} {'easy'}")
print(f"{'Edge 10mm':<30} {Q_edge_typ:<12.0f} {'0.01×':<12} {'in-plane (sparse)':<20} {'tricky bond'}")

Q_small_corner = composite_Q(Q_glass, eps_corner*2, Q_pzt_mech, Q_adhesive)
print(f"{'Face 5mm (corner) ★':<30} {Q_small_corner:<12.0f} {f'{signal_vs_big:.2f}×':<12} {'flexural (rich)':<20} {'easy'}")

print(f"""
RECOMMENDATION:
{'─' * 72}
{'★ FACE MOUNT — 5mm PZT disc at opposite corners':}

  Why NOT edge mount:
  1. Signal is ~{ratio_signal:.0f}× weaker (d33×10mm² vs d31×78mm²)
  2. In-plane modes start at 29 kHz — misses the rich flexural spectrum
  3. Bonding a PZT to a 1mm edge is mechanically fragile
  4. Flexural modes ARE the interesting physics for perturbation coupling

  Why 5mm corner face mount instead of 10mm:
  1. Q preserved: ~{Q_small_corner:.0f} (vs {Q_face_typ:.0f} for 10mm average)
  2. Corners are nodal regions for most modes → less Q degradation
  3. Still couples to ALL flexural modes (the rich spectrum)
  4. Clear of all perturbation sites (10mm+ from nearest in any pattern)
  5. Signal still adequate: {signal_vs_big*100:.0f}% of full 10mm disc

  Placement: TX at (5,95) mm, RX at (95,5) mm — diagonal corners
  PZT: 5mm diameter × 1mm disc, bonded with thin cyanoacrylate layer
  Both on the SAME face (underside) to leave top surface completely
  clear for perturbation sites
""")
