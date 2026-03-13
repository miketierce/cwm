#!/usr/bin/env python3
"""Verify scaling table, crossovers, energy, latency for v12."""
import math, numpy as np

K_B = 1.380649e-23; T = 300; v = 5500; rho = 2230; alpha = 3.3e-6; Q = 10000
beta = 25; A = 1e-9; dT = 1.0
n_max = math.floor(1/(2*alpha*dT + 1/Q))
print(f'n_max = {n_max}')
print()

print("=== Borosilicate Scaling Table ===")
for L in [0.15, 0.01, 0.002, 0.001, 0.0005, 0.0002, 0.0001]:
    d = L / beta
    m_eff = rho * np.pi * (d/2)**2 * L / 2
    f1 = v / (2*L)
    k_eff = m_eff * (2*np.pi*f1)**2
    E_sig = 0.5 * k_eff * A**2
    snr = E_sig / (K_B * T)
    snr_db = 10*np.log10(snr)
    b = 0.5 * np.log2(1 + snr)
    total = n_max * b
    vol = np.pi * (d/2)**2 * L
    vol_cm3 = vol * 1e6
    dens = total / vol_cm3 / 1e9
    E_bit = E_sig / b
    t_read = 10 / f1
    print(f'L={L*1e3:6.1f}mm  d={d*1e6:5.0f}um  f1={f1/1e3:8.0f}kHz  SNR={snr_db:5.1f}dB  b={b:4.1f}  total={total:8.0f}  dens={dens:10.1f} Gbit/cm3  E/bit={E_bit:.2e}J  t={t_read*1e6:.1f}us')

print()
print("=== Crossover check ===")
# Find L where density = target
targets = {'DRAM (10)': 10, 'PCM (100)': 100, 'NAND (1000)': 1000}
for name, target in targets.items():
    for L_um in range(50, 5000):
        L = L_um * 1e-6
        d = L / beta
        m_eff = rho * np.pi * (d/2)**2 * L / 2
        f1 = v / (2*L)
        k_eff = m_eff * (2*np.pi*f1)**2
        E_sig = 0.5 * k_eff * A**2
        snr = E_sig / (K_B * T)
        b = 0.5 * np.log2(1 + snr)
        total = n_max * b
        vol_cm3 = np.pi * (d/2)**2 * L * 1e6
        dens = total / vol_cm3 / 1e9
        if dens >= target:
            print(f'{name}: crossover at L = {L*1e3:.2f} mm (dens={dens:.1f})')
            break

print()
print("=== Fused silica 0.5mm array ===")
fs_v = 5960; fs_rho = 2200; fs_alpha = 0.55e-6; fs_Q = 100000
L = 0.5e-3; d = 20e-6
n_fs = math.floor(1/(2*fs_alpha*0.1 + 1/fs_Q))
m_eff = fs_rho * np.pi * (d/2)**2 * L / 2
f1 = fs_v / (2*L)
k_eff = m_eff * (2*np.pi*f1)**2
E_sig = 0.5 * k_eff * A**2
snr = E_sig / (K_B * T)
snr_db = 10*np.log10(snr)
b = 0.5 * np.log2(1 + snr)
total = n_fs * b
vol_cm3 = np.pi * (d/2)**2 * L * 1e6
dens_single = total / vol_cm3 / 1e9
print(f'n_max(+-0.1K)={n_fs:,}  SNR={snr_db:.1f}dB  b={b:.1f}  total={total:,.0f}  single_dens={dens_single:.0f} Gbit/cm3')

# Array packing
pitch = 40e-6  # 2x diameter
layer_spacing = 0.55e-3
rods_x = 0.01 / pitch
rods_y = 0.01 / pitch
layers = 0.01 / layer_spacing
total_rods = rods_x * rods_y * layers
array_bits = total_rods * total
array_density = array_bits / 1e9  # per cm^3
print(f'pitch={pitch*1e6:.0f}um  layers={layers:.0f}  total_rods={total_rods:,.0f}')
print(f'array_bits={array_bits:,.0f}  array_density={array_density:,.0f} Gbit/cm3')

print()
print("=== Hopfield capacity ===")
p_max = 0.138 * 9380
print(f'P_max = 0.138 * 9380 = {p_max:.0f}')

print()
print("=== Energy check at 1mm ===")
L = 1e-3; d = 40e-6
m_eff = rho * np.pi * (d/2)**2 * L / 2
f1 = v / (2*L)
k_eff = m_eff * (2*np.pi*f1)**2
E_sig = 0.5 * k_eff * A**2
b = 0.5 * np.log2(1 + E_sig / (K_B * T))
E_per_bit = E_sig / b
print(f'E_mode = {E_sig:.2e} J  b = {b:.1f}  E/bit = {E_per_bit:.2e} J = {E_per_bit*1e15:.1f} fJ')
print(f't_read = {10/f1 * 1e6:.1f} us')
