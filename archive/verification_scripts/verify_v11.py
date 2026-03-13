"""Verify all quantitative claims in v11.md against physics equations."""
import math
import numpy as np

kB = 1.381e-23
T = 300

# === BOROSILICATE ===
v = 5500; rho = 2230; Q = 10000; alpha = 3.3e-6; dT = 1.0
beta = 25; A = 1e-9

n_max = int(1.0 / (2*alpha*dT + 1.0/Q))
print("=== BOROSILICATE +/-1K ===")
print(f"n_max = {n_max}")
print()

print("Length    | Diam   | f1        | SNR(dB) | b/mode | Total bits | Volume(cm3)  | Density(Gb/cm3) | E/mode(pJ) | E/bit(fJ) | Readout(us) | Coherence(ms)")
print("-" * 170)

for L in [0.150, 0.010, 0.002, 0.001, 0.0005, 0.0002, 0.0001]:
    d = L / beta
    M = rho * math.pi * (d/2)**2 * L
    m_eff = M / 2
    f1 = v / (2*L)
    omega1 = 2 * math.pi * f1
    k_eff = m_eff * omega1**2
    E_s = 0.5 * k_eff * A**2
    SNR = E_s / (kB * T)
    SNR_dB = 10 * math.log10(SNR)
    b = 0.5 * math.log2(1 + SNR)
    bits = n_max * b
    V_cm3 = math.pi * (d/2)**2 * L * 1e6
    density = bits / V_cm3
    E_per_bit = E_s / b if b > 0 else 0
    coherence = Q / (math.pi * f1)
    readout = 10 / f1

    print(f"{L*1000:7.1f}mm | {d*1e6:5.0f}um | {f1/1e3:8.1f}kHz | {SNR_dB:6.1f}  | {b:5.1f}  | {bits:10.0f} | {V_cm3:12.3e} | {density/1e9:15.1f} | {E_s*1e12:10.2f} | {E_per_bit*1e15:9.1f} | {readout*1e6:11.1f} | {coherence*1e3:7.2f}")

# === FUSED SILICA ===
print("\n=== FUSED SILICA ===")
v2 = 5960; rho2 = 2200; Q2 = 100000; alpha2 = 0.55e-6

for dT2 in [1.0, 0.1]:
    n_max2 = int(1.0 / (2*alpha2*dT2 + 1.0/Q2))
    print(f"\n  dT=+/-{dT2}K: n_max = {n_max2}")

    for L in [0.001, 0.0005]:
        d = L / beta
        M = rho2 * math.pi * (d/2)**2 * L
        f1 = v2 / (2*L)
        omega1 = 2 * math.pi * f1
        k_eff = (M/2) * omega1**2
        E_s = 0.5 * k_eff * A**2
        SNR = E_s / (kB * T)
        SNR_dB = 10 * math.log10(SNR)
        b = 0.5 * math.log2(1 + SNR)
        bits = n_max2 * b
        V_cm3 = math.pi * (d/2)**2 * L * 1e6
        density = bits / V_cm3
        print(f"    L={L*1000:.1f}mm: SNR={SNR_dB:.1f}dB, b/mode={b:.1f}, bits/rod={bits:.0f}, density={density/1e9:.0f} Gb/cm3")

# === ARRAY PACKING ===
print("\n=== ARRAY PACKING: Fused silica 0.5mm +/-0.1K ===")
L = 0.0005; d = L/beta
n_max2 = int(1.0 / (2*alpha2*0.1 + 1.0/Q2))
M = rho2 * math.pi * (d/2)**2 * L
f1 = v2/(2*L)
omega1 = 2*math.pi*f1
k_eff = (M/2) * omega1**2
E_s = 0.5 * k_eff * A**2
SNR = E_s/(kB*T)
b = 0.5 * math.log2(1+SNR)
bits_rod = n_max2 * b

pitch = 2 * d
layer_spacing = L + 0.1*L
rods_t = 0.01 / pitch
layers = 0.01 / layer_spacing
rods_cm3 = rods_t**2 * layers
total = rods_cm3 * bits_rod
print(f"  pitch={pitch*1e6:.0f}um, layer_sp={layer_spacing*1e3:.3f}mm")
print(f"  rods/cm(transverse)={rods_t:.0f}, layers={layers:.0f}")
print(f"  rods/cm3={rods_cm3:.0f}")
print(f"  bits/rod={bits_rod:.0f}")
print(f"  total bits/cm3={total:.0f}")
print(f"  density={total/1e9:.0f} Gbit/cm3 = {total/1e12:.2f} Tbit/cm3")

# === CROSSOVER POINTS ===
print("\n=== CROSSOVER POINTS (borosilicate, single rod) ===")
Ls = np.logspace(-4, -0.5, 50000)
for name, target in [("DRAM", 10e9), ("PCM", 100e9), ("NAND", 1000e9)]:
    for Lx in Ls:
        d = Lx/beta
        M = rho * math.pi * (d/2)**2 * Lx
        f1 = v/(2*Lx)
        omega1 = 2*math.pi*f1
        k_eff = (M/2)*omega1**2
        E_s = 0.5*k_eff*A**2
        SNR_x = E_s/(kB*T)
        bx = 0.5*math.log2(1+SNR_x)
        V_cm3 = math.pi*(d/2)**2*Lx*1e6
        dens = n_max*bx/V_cm3
        if dens >= target:
            print(f"  {name} ({target/1e9:.0f} Gb/cm3): crossover at L={Lx*1000:.2f} mm")
            break

# === HOPFIELD ===
P = 0.138 * n_max
print(f"\nHopfield capacity: 0.138 x {n_max} = {P:.0f} patterns")

# === SNR COEFFICIENT ===
coeff = rho * math.pi**3 * v**2 * A**2 / (16 * beta**2 * kB * T)
print(f"SNR = {coeff:.2e} * L  (L in meters)")

# === Q=5000 degraded scenario ===
print("\n=== DEGRADED Q=5000 ===")
Q_deg = 5000
n_max_deg = int(1.0 / (2*alpha*dT + 1.0/Q_deg))
L = 0.001; d = L/beta
M = rho * math.pi * (d/2)**2 * L
f1 = v/(2*L)
omega1 = 2*math.pi*f1
k_eff = (M/2)*omega1**2
E_s = 0.5*k_eff*A**2
SNR_x = E_s/(kB*T)
bx = 0.5*math.log2(1+SNR_x)
bits_deg = n_max_deg * bx
V_cm3 = math.pi*(d/2)**2*L*1e6
dens_deg = bits_deg/V_cm3
print(f"  n_max(Q=5000) = {n_max_deg}")
print(f"  bits/rod = {bits_deg:.0f}")
print(f"  density = {dens_deg/1e9:.1f} Gb/cm3")

# === Q=1000 degraded scenario ===
Q_deg2 = 1000
n_max_deg2 = int(1.0 / (2*alpha*dT + 1.0/Q_deg2))
bits_deg2 = n_max_deg2 * bx
dens_deg2 = bits_deg2/V_cm3
print(f"\n  n_max(Q=1000) = {n_max_deg2}")
print(f"  bits/rod = {bits_deg2:.0f}")
print(f"  density = {dens_deg2/1e9:.1f} Gb/cm3")

print("\n=== ALL VERIFICATIONS COMPLETE ===")
