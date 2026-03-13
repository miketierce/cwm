"""Scaling analysis for MEMS glass resonator WCFOMA."""
import numpy as np

K_B = 1.380649e-23
T = 300.0

# Borosilicate — v_bar = sqrt(E/rho), E=63 GPa, rho=2230 kg/m3
v = 5315.2; rho = 2230.0; Q = 10000.0; alpha = 3.3e-6
n_max_boro = int(1.0 / (2*alpha*1.0 + 1.0/Q))

# Fused silica — v_bar = sqrt(E/rho), E=72 GPa, rho=2200 kg/m3
v_fs = 5720.0; rho_fs = 2200.0; Q_fs = 100000.0; alpha_fs = 0.55e-6
n_max_fs_1K = int(1.0 / (2*alpha_fs*1.0 + 1.0/Q_fs))
n_max_fs_01K = int(1.0 / (2*alpha_fs*0.1 + 1.0/Q_fs))

print(f"n_max borosilicate +/-1K = {n_max_boro}")
print(f"n_max fused silica +/-1K = {n_max_fs_1K}")
print(f"n_max fused silica +/-0.1K = {n_max_fs_01K}")
print()

A = 1e-9  # 1 nm drive

def analyze(label, lengths_mm, mat_v, mat_rho, mat_Q, mat_alpha, dT, A_drive):
    n_max = int(1.0 / (2*mat_alpha*dT + 1.0/mat_Q))
    print(f"=== {label} (n_max={n_max}) ===")
    print(f"{'L':>8} {'d':>8} {'M':>10} {'f1':>10} {'SNR':>7} {'b/m':>5} {'total':>8} {'Vol':>10} {'Density':>10}")
    print(f"{'(mm)':>8} {'(um)':>8} {'(kg)':>10} {'(Hz)':>10} {'(dB)':>7} {'':>5} {'(bits)':>8} {'(cm3)':>10} {'(Gb/cm3)':>10}")
    for Lmm in lengths_mm:
        L = Lmm * 1e-3
        d = L / 25.0
        r = d / 2.0
        Vol = np.pi * r**2 * L
        Vcm3 = Vol * 1e6
        M = mat_rho * Vol
        meff = M / 2.0
        f1 = mat_v / (2.0 * L)
        omega = 2 * np.pi * f1
        keff = meff * omega**2
        Es = 0.5 * keff * A_drive**2
        snr = Es / (K_B * T)
        sdb = 10 * np.log10(snr)
        bpm = 0.5 * np.log2(1 + snr)
        tot = n_max * bpm
        dens = (tot / 1e9) / Vcm3
        E_per_bit_fJ = (Es / bpm) * 1e15
        print(f"{Lmm:>8.1f} {d*1e6:>8.1f} {M:>10.2e} {f1:>10.0f} {sdb:>7.1f} {bpm:>5.1f} {tot:>8.0f} {Vcm3:>10.2e} {dens:>10.1f}")
    print()

# Borosilicate at +/-1K
analyze("Borosilicate, 25:1 AR, 1nm drive, +/-1K",
        [150, 50, 10, 5, 2, 1, 0.5, 0.2, 0.1],
        v, rho, Q, alpha, 1.0, A)

# Fused silica at +/-1K
analyze("Fused silica, 25:1 AR, 1nm drive, +/-1K",
        [10, 5, 2, 1, 0.5, 0.2, 0.1],
        v_fs, rho_fs, Q_fs, alpha_fs, 1.0, A)

# Fused silica at +/-0.1K
analyze("Fused silica, 25:1 AR, 1nm drive, +/-0.1K",
        [10, 5, 2, 1, 0.5, 0.2, 0.1],
        v_fs, rho_fs, Q_fs, alpha_fs, 0.1, A)

print("Reference densities:")
print("  DRAM  = 10 Gbit/cm3    (0.01 Tb/cm3)")
print("  PCM   = 100 Gbit/cm3   (0.1 Tb/cm3)")
print("  NAND  = 1000 Gbit/cm3  (1.0 Tb/cm3)")
print()

# Energy analysis
print("=== Energy per bit (borosilicate) ===")
for Lmm in [150, 10, 1, 0.1]:
    L = Lmm * 1e-3; d = L/25; r = d/2
    M = rho * np.pi * r**2 * L; meff = M/2
    f1 = v/(2*L); omega = 2*np.pi*f1; keff = meff*omega**2
    Es = 0.5*keff*A**2; snr = Es/(K_B*T); bpm = 0.5*np.log2(1+snr)
    print(f"  L={Lmm:>6.1f}mm: E_mode={Es:.2e} J, b/mode={bpm:.1f}, E/bit={Es/bpm*1e12:.4f} pJ")
print()

# Latency analysis
print("=== Readout latency (borosilicate, Q=10000) ===")
for Lmm in [150, 10, 1, 0.1]:
    L = Lmm*1e-3; f1 = v/(2*L)
    tau = Q/(np.pi*f1)
    fft_time_us = (1.0/f1) * 10 * 1e6  # ~10 cycles for FFT window
    print(f"  L={Lmm:>6.1f}mm: f1={f1:>10.0f} Hz, coherence={tau*1e3:.3f} ms, ~10-cycle window={fft_time_us:.1f} us")
print()

# Array packing analysis
print("=== Array packing: 1mm rods in 1 cm3 ===")
L = 1e-3; d = L/25; r = d/2
pitch = d * 2  # 2x diameter pitch for isolation
rods_per_cm = 0.01 / pitch  # rods along one transverse axis
layers = 0.01 / (L + 0.1e-3)  # layers along rod axis (with 100um gap)
total_rods = rods_per_cm**2 * layers
M = rho * np.pi * r**2 * L; meff = M/2
f1 = v/(2*L); omega = 2*np.pi*f1; keff = meff*omega**2
Es = 0.5*keff*A**2; snr = Es/(K_B*T); bpm = 0.5*np.log2(1+snr)
bits_per_rod = n_max_boro * bpm
total_bits = total_rods * bits_per_rod
print(f"  Rod: {L*1e3:.1f}mm x {d*1e6:.0f}um")
print(f"  Pitch: {pitch*1e6:.0f} um (2x diameter)")
print(f"  Rods per cm (transverse): {rods_per_cm:.0f}")
print(f"  Layers (along rod axis): {layers:.0f}")
print(f"  Total rods in 1cm3: {total_rods:.0f}")
print(f"  Bits per rod: {bits_per_rod:.0f}")
print(f"  Total bits in 1cm3: {total_bits:.0e}")
print(f"  Density: {total_bits/1e9:.1f} Gbit/cm3")
print(f"  Density: {total_bits/1e12:.3f} Tbit/cm3")
