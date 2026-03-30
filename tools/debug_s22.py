#!/usr/bin/env python3
"""Quick diagnostic for S22 transfer matrix and MI."""
import sys
sys.path.insert(0, '.')

import numpy as np
from simulations.bead_string import *

# 1. Verify transfer matrix: no beads → unperturbed frequencies
L, T = 0.5, 10.0
mu = string_linear_density('nylon')
f0 = unperturbed_frequencies('nylon', T, L, 5)
print('=== Transfer Matrix Verification ===')
print('Unperturbed:', f0)

f_loaded = find_loaded_eigenfrequencies(T, mu, L, np.array([]), np.array([]), 5)
print('TM (no bead):', f_loaded)
print('Match:', np.allclose(f0, f_loaded, rtol=1e-4))

# 2. Small bead (perturbative regime)
M = string_total_mass('nylon', L)
m_small = M * 0.001
f_small = find_loaded_eigenfrequencies(T, mu, L, np.array([L/3]), np.array([m_small]), 5)
shifts_small = (f_small - f0) / f0
rayleigh_pred = rayleigh_shift(0.001, np.array([L/3]), L, 5).flatten()
print('\n=== Small Bead (m/M=0.001) at L/3 ===')
print('TM shifts: ', shifts_small)
print('Rayleigh:  ', rayleigh_pred)
if np.all(rayleigh_pred != 0):
    print('Ratio:     ', shifts_small / rayleigh_pred)

# 3. Test H-B2 with tiny bead (perturbative)
m_1mm = bead_mass(0.001, 'faience')
print(f'\n=== 1mm faience bead: mass ratio = {m_1mm/M:.6f} ===')
r = exp_sin2_sensitivity(bead_diameter=0.001, n_positions=50, n_modes=5)
for i, r2 in enumerate(r.r_squared_per_mode):
    print(f'  Mode {i+1}: R² = {r2:.6f}')
print(f'  Min R²: {r.min_r_squared:.6f}')
print(f'  Verdict: {"CONFIRMED" if r.verdict else "KILLED"}')

# 4. Debug H-B4 fingerprints
print('\n=== H-B4 Fingerprint Debug ===')
r4 = exp_repositionability()
fp = r4.fingerprints
print(f'Fingerprint shape: {fp.shape}')
print(f'Shift range: [{fp.min():.6f}, {fp.max():.6f}]')
Q_eff = effective_q('nylon', 'knotted', L/2, L, 1)
sigma = 1.0 / (2.0 * Q_eff)
print(f'Noise σ = {sigma:.6f}')
# Pairwise L2 distances divided by sigma
dists = []
for i in range(fp.shape[0]):
    for j in range(i+1, fp.shape[0]):
        d = np.sqrt(np.sum((fp[i] - fp[j])**2))
        dists.append(d)
dists = np.array(dists)
print(f'Mean pairwise distance: {np.mean(dists):.6f}')
print(f'Min pairwise distance:  {np.min(dists):.6f}')
print(f'Mean dist / sigma:      {np.mean(dists)/sigma:.1f}')
print(f'Min dist / sigma:       {np.min(dists)/sigma:.1f}')
print(f'MI: {r4.mutual_information:.4f} bits')
