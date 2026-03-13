"""Extended scaling analysis - fused silica arrays and crossover points."""
import numpy as np
K_B = 1.380649e-23; T = 300; A = 1e-9

# Fused silica 1mm rods at +/-0.1K
v = 5960; rho = 2200; Q = 100000; alpha = 0.55e-6; dT = 0.1
n_max = int(1/(2*alpha*dT + 1/Q))
L = 1e-3; d = L/25; r = d/2; pitch = d*2
M = rho*np.pi*r**2*L; meff = M/2; f1 = v/(2*L)
w = 2*np.pi*f1; keff = meff*w**2; Es = 0.5*keff*A**2
snr = Es/(K_B*T); bpm = 0.5*np.log2(1+snr)
bpr = n_max*bpm
rpc = 0.01/pitch; layers = 0.01/(L + 0.1e-3)
total_rods = rpc**2 * layers; total_bits = total_rods * bpr
print("Fused silica 1mm rods, +/-0.1K")
print(f"  n_max={n_max}, b/mode={bpm:.1f}, bits/rod={bpr:.0f}")
print(f"  Rods/cm={rpc:.0f}, layers={layers:.0f}, total_rods={total_rods:.0f}")
print(f"  Total bits in 1cm3: {total_bits:.2e}")
print(f"  Density: {total_bits/1e9:.0f} Gbit/cm3 = {total_bits/1e12:.2f} Tb/cm3")
print()

# 0.5mm rods fused silica
L = 0.5e-3; d = L/25; r = d/2; pitch = d*2
M = rho*np.pi*r**2*L; meff = M/2; f1 = v/(2*L)
w = 2*np.pi*f1; keff = meff*w**2; Es = 0.5*keff*A**2
snr = Es/(K_B*T); bpm = 0.5*np.log2(1+snr)
bpr = n_max*bpm
rpc = 0.01/pitch; layers = 0.01/(L + 50e-6)
total_rods = rpc**2 * layers; total_bits = total_rods * bpr
print("Fused silica 0.5mm rods, +/-0.1K")
print(f"  n_max={n_max}, b/mode={bpm:.1f}, bits/rod={bpr:.0f}")
print(f"  Rods/cm={rpc:.0f}, layers={layers:.0f}, total_rods={total_rods:.0f}")
print(f"  Total bits in 1cm3: {total_bits:.2e}")
print(f"  Density: {total_bits/1e9:.0f} Gbit/cm3 = {total_bits/1e12:.2f} Tb/cm3")
print()

# Key crossover points (borosilicate +/-1K, single rod volume)
print("=== Where single-rod WCFOMA density exceeds conventional (borosilicate, +/-1K) ===")
for name, ref in [("DRAM", 10), ("PCM", 100), ("NAND", 1000)]:
    found = False
    for Lum in range(10000, 10, -10):
        L = Lum * 1e-6; d = L/25; r = d/2
        Vol = np.pi*r**2*L; Vcm3 = Vol*1e6
        M = 2230*Vol; meff = M/2; f1 = 5500/(2*L)
        w = 2*np.pi*f1; keff = meff*w**2; Es = 0.5*keff*A**2
        snr = Es/(K_B*T); bpm = 0.5*np.log2(1+snr)
        tot = 9380*bpm; dens = (tot/1e9)/Vcm3
        if dens >= ref:
            print(f"  Exceeds {name:4s} ({ref:>4d} Gb/cm3) at L={Lum:>5d}um = {Lum/1000:.1f}mm (dens={dens:.0f} Gb/cm3)")
            found = True
            break
    if not found:
        print(f"  Does not exceed {name} in range")

print()
print("=== MEMS target design: borosilicate 1mm x 40um ===")
L = 1e-3; d = 40e-6; r = d/2
Vol = np.pi*r**2*L; Vcm3 = Vol*1e6
M = 2230*Vol; meff = M/2; f1 = 5500/(2*L)
w = 2*np.pi*f1; keff = meff*w**2; Es = 0.5*keff*A**2
snr = Es/(K_B*T); sdb = 10*np.log10(snr); bpm = 0.5*np.log2(1+snr)
n_max_b = 9380; tot = n_max_b*bpm
tau = 10000/(np.pi*f1)
Epb = Es/bpm * 1e12  # pJ per bit
print(f"  f1 = {f1:.0f} Hz = {f1/1e6:.2f} MHz")
print(f"  mass = {M:.2e} kg")
print(f"  k_eff = {keff:.2e} N/m")
print(f"  SNR = {sdb:.1f} dB, bits/mode = {bpm:.1f}")
print(f"  Total bits = {tot:.0f} ({tot/8:.0f} bytes)")
print(f"  Rod volume = {Vcm3:.2e} cm3")
print(f"  Rod density = {(tot/1e9)/Vcm3:.1f} Gbit/cm3")
print(f"  Energy/bit = {Epb:.4f} pJ ({Epb*1e3:.1f} fJ)")
print(f"  Coherence = {tau*1e3:.3f} ms")
print(f"  Readout (10 cycles) = {10/f1*1e6:.2f} us")
