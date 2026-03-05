#!/usr/bin/env python3
"""Verify all quantitative claims for v12 paper."""
import sys, math
sys.path.insert(0, '.')
from simulations.glass_resonator import glass_database, RodGeometry
from simulations.mems_q_model import compute_Q_budget, AnchorDesign, OperatingConditions

DB = glass_database()

print("=== 1mm Borosilicate, 5um tethers, 1 Pa ===")
rod = RodGeometry(length=1e-3, diameter=40e-6, glass_type='borosilicate')
anchor = AnchorDesign(tether_width=5e-6, tether_thickness=5e-6, tether_length=50e-6)
cond = OperatingConditions(pressure=1.0)
r = compute_Q_budget(rod=rod, anchor=anchor, conditions=cond)
for c in r.components:
    print(f"  Q_{c.name}: {c.Q_value:,.0f}  ({r.loss_budget[c.name]*100:.1f}%)")
print(f"  Q_total={r.Q_total:,.0f}  n_max={r.n_max_modes:,}  bits={r.total_bits:,}  dens={r.density_gbit_cm3:.1f}")

print("\n=== 1mm Fused silica optimized ===")
rod2 = RodGeometry(length=1e-3, diameter=40e-6, glass_type='fused_silica')
a2 = AnchorDesign(tether_width=2e-6, tether_thickness=2e-6, tether_length=100e-6, isolation_trenches=True)
c2 = OperatingConditions(pressure=0.1)
r2 = compute_Q_budget(rod=rod2, anchor=a2, conditions=c2)
for c in r2.components:
    print(f"  Q_{c.name}: {c.Q_value:,.0f}  ({r2.loss_budget[c.name]*100:.1f}%)")
print(f"  Q_total={r2.Q_total:,.0f}  n_max={r2.n_max_modes:,}  bits={r2.total_bits:,}  dens={r2.density_gbit_cm3:.1f}")

print("\n=== Conservative Q=5000 ===")
alpha = DB['borosilicate'].alpha_thermal
n5k = math.floor(1.0 / (2*alpha*1.0 + 1.0/5000))
print(f"  n_max at Q=5000: {n5k:,}")

print("\n=== Fused silica material properties ===")
fs = DB['fused_silica']
print(f"  v={fs.v_longitudinal} Q={fs.Q_acoustic} alpha={fs.alpha_thermal}")
n_fs = math.floor(1.0 / (2*fs.alpha_thermal*1.0 + 1.0/fs.Q_acoustic))
n_fs01 = math.floor(1.0 / (2*fs.alpha_thermal*0.1 + 1.0/fs.Q_acoustic))
print(f"  n_max(+-1K): {n_fs:,}  n_max(+-0.1K): {n_fs01:,}")

print("\n=== Macro prototype 150mm ===")
rod3 = RodGeometry(length=0.15, diameter=6e-3, glass_type='borosilicate')
bs = DB['borosilicate']
f1 = bs.v_longitudinal / (2 * 0.15)
print(f"  f1 = {f1:.0f} Hz")
import numpy as np
K_B = 1.380649e-23
T = 300
m_eff = bs.density * np.pi * (3e-3)**2 * 0.15 / 2
k_eff = m_eff * (2*np.pi*f1)**2
E_sig = 0.5 * k_eff * (1e-9)**2
E_noise = K_B * T
snr = E_sig / E_noise
snr_db = 10*np.log10(snr)
bits_mode = 0.5 * np.log2(1 + snr)
n_max_macro = math.floor(1.0 / (2*bs.alpha_thermal*1.0 + 1.0/bs.Q_acoustic))
print(f"  SNR = {snr_db:.1f} dB  bits/mode = {bits_mode:.1f}  n_max = {n_max_macro:,}")
print(f"  total bits = {n_max_macro * bits_mode:,.0f}")
