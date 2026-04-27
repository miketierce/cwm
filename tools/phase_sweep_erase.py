#!/usr/bin/env python3
"""
Phase-Sweep Selective Erase Experiment

Exploits the new P1:/P2: phase registers on the AD9833 DDS firmware.
For each shared eigenmode:
  1. Drive DDS#1 at the best excitation frequency (fixed phase=0)
  2. Sweep DDS#2 phase from 0→4095 (0→2π) in N steps
  3. Measure mode energy at each phase offset
  4. Find the phase that gives MINIMUM energy (best destructive interference)
  5. Attempt a full write→erase→verify cycle at that optimal phase

AD9833 phase register: 12-bit (0-4095), maps linearly to 0-2π radians.
  Phase in degrees = phase_val * 360 / 4096
  Phase in radians = phase_val * 2π / 4096

Usage:
  python tools/phase_sweep_erase.py                    # Full sweep + cycle test
  python tools/phase_sweep_erase.py --phase-steps 72   # 5° resolution (72 steps)
  python tools/phase_sweep_erase.py --phase-steps 360  # 1° resolution (slow)
  python tools/phase_sweep_erase.py --skip-sweep        # Use saved optimal phases
"""
import argparse, sys, time, ctypes, json
import numpy as np
import serial
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--phase-steps', type=int, default=72,
                    help='Number of phase steps in sweep (default 72 = 5° resolution)')
parser.add_argument('--navg', type=int, default=20,
                    help='Coherent averages per measurement')
parser.add_argument('--mux-channel', type=int, default=5,
                    help='Mux channel for readout')
parser.add_argument('--skip-sweep', action='store_true',
                    help='Skip phase sweep, load saved optimal phases')
parser.add_argument('--cycles', type=int, default=5,
                    help='Number of write/erase/verify cycles')
args = parser.parse_args()

DATA_DIR = Path(__file__).parent.parent / 'data' / 'results'

# ─── Hardware setup ───
TIMEBASE = 7
N_SAMPLES = 8064
DT = 1280e-9


def setup_hardware():
    ps = ctypes.CDLL(
        "/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources/libps2000.dylib")
    ps.ps2000_set_sig_gen_built_in.argtypes = [
        ctypes.c_int16, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32,
        ctypes.c_float, ctypes.c_float, ctypes.c_float, ctypes.c_float,
        ctypes.c_int32, ctypes.c_int32]

    for h in range(1, 5):
        ps.ps2000_close_unit(h)
    time.sleep(0.5)

    handle = ps.ps2000_open_unit()
    print(f"PicoScope handle: {handle}")
    if handle <= 0:
        sys.exit(1)

    ps.ps2000_set_channel(handle, 0, 1, 1, 7)
    ps.ps2000_set_channel(handle, 1, 0, 1, 7)
    ps.ps2000_set_sig_gen_built_in(handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0)

    mux = serial.Serial('/dev/cu.usbserial-11310', 9600, timeout=1)
    time.sleep(2)
    mux.reset_input_buffer()

    dds = serial.Serial('/dev/cu.usbserial-11330', 115200, timeout=2)
    time.sleep(2)
    dds.reset_input_buffer()

    return ps, handle, dds, mux


def dds_cmd(dds, cmd):
    dds.write(f'{cmd}\n'.encode())
    time.sleep(0.01)
    return dds.readline().decode().strip()


def capture(ps, handle):
    buf = (ctypes.c_int16 * N_SAMPLES)()
    ov = ctypes.c_int16(0)
    ps.ps2000_set_trigger(handle, 5, 0, 0, 0, 0)
    ms = ctypes.c_int32(0)
    ps.ps2000_run_block(handle, N_SAMPLES, TIMEBASE, 1, ctypes.byref(ms))
    for _ in range(5000):
        if ps.ps2000_ready(handle):
            break
        time.sleep(0.001)
    else:
        ps.ps2000_stop(handle)
        return np.zeros(N_SAMPLES)
    ps.ps2000_get_values(handle, ctypes.byref(buf), None, None, None,
                         ctypes.byref(ov), N_SAMPLES)
    return np.array(buf, dtype=np.float64)


def coherent_avg_spectrum(ps, handle, n_avg):
    frames = [capture(ps, handle) for _ in range(n_avg)]
    avg = np.mean(frames, axis=0)
    d = avg - np.mean(avg)
    w = d * np.hanning(len(d))
    nfft = len(d) * 4
    mag = np.abs(np.fft.rfft(w, n=nfft))
    freq = np.fft.rfftfreq(nfft, d=DT)
    return freq, mag


def mode_energy(mag, freq, target_freq, window_hz=2000):
    """Sum magnitude in a window around target frequency."""
    mask = np.abs(freq - target_freq) < window_hz
    return np.sum(mag[mask])


def cleanup_hardware(ps, handle, dds, mux):
    dds_cmd(dds, 'Foff')
    dds_cmd(dds, 'P1:0')
    dds_cmd(dds, 'P2:0')
    ps.ps2000_set_sig_gen_built_in(handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0)
    ps.ps2000_stop(handle)
    ps.ps2000_close_unit(handle)
    mux.write(b'0\n')
    mux.close()
    dds.close()


# ─── Load shared eigenmode data ───
def load_shared_eigenmodes():
    d1 = np.load(DATA_DIR / 'eigenmode_sweep_dds1_5000_100000_5000.npz')
    d2 = np.load(DATA_DIR / 'eigenmode_sweep_dds2_5000_100000_5000.npz')

    freq_axis = d1['freq_axis']
    e1_freqs = d1['eigenmode_freqs']
    e2_freqs = d2['eigenmode_freqs']
    drive_freqs_1 = d1['drive_freqs']
    drive_freqs_2 = d2['drive_freqs']

    shared = []
    for i, f1 in enumerate(e1_freqs):
        for j, f2 in enumerate(e2_freqs):
            if abs(f1 - f2) < 2000:
                # Find best drive freq for each DDS at this eigenmode
                bin_idx = np.argmin(np.abs(freq_axis - (f1 + f2) / 2))
                r1 = d1['all_ratios'][:, 0, bin_idx]
                r2 = d2['all_ratios'][:, 0, bin_idx]
                shared.append({
                    'eigenmode_freq': (f1 + f2) / 2,
                    'dds1_eigenmode': f1,
                    'dds2_eigenmode': f2,
                    'best_drive_1': int(drive_freqs_1[np.argmax(r1)]),
                    'best_drive_2': int(drive_freqs_2[np.argmax(r2)]),
                    'ratio_1': float(np.max(r1)),
                    'ratio_2': float(np.max(r2)),
                })

    return shared


# ═══════════════════════════════════════════════════════════════════
#  PHASE 1: Phase Sweep — find optimal destructive interference
# ═══════════════════════════════════════════════════════════════════

def phase_sweep(ps, handle, dds, shared):
    """Sweep DDS#2 phase for each shared eigenmode, map interference pattern."""
    print("=" * 60)
    print("PHASE 1: PHASE SWEEP — MAPPING INTERFERENCE PATTERN")
    print("=" * 60)

    n_steps = args.phase_steps
    phase_values = np.linspace(0, 4095, n_steps, endpoint=False, dtype=int)
    phase_degrees = phase_values * 360.0 / 4096

    print(f"Phase steps: {n_steps} ({360/n_steps:.1f}° resolution)")
    print(f"Averages per measurement: {args.navg}")

    results = {}

    for s in shared:
        f_target = s['eigenmode_freq']
        drive1 = s['best_drive_1']
        drive2 = s['best_drive_2']

        print(f"\n--- Eigenmode ~{f_target:.0f} Hz ---")
        print(f"  DDS#1 drive: {drive1} Hz, DDS#2 drive: {drive2} Hz")

        # Noise baseline
        dds_cmd(dds, 'Foff')
        dds_cmd(dds, 'P1:0')
        dds_cmd(dds, 'P2:0')
        time.sleep(0.3)
        freq, noise_mag = coherent_avg_spectrum(ps, handle, args.navg)
        noise_energy = mode_energy(noise_mag, freq, f_target)

        # DDS#1 solo (write reference)
        dds_cmd(dds, f'F1:{drive1}')
        dds_cmd(dds, 'P1:0')
        time.sleep(0.3)
        _, solo1_mag = coherent_avg_spectrum(ps, handle, args.navg)
        solo1_energy = mode_energy(solo1_mag, freq, f_target)

        print(f"  Noise energy: {noise_energy:.0f}")
        print(f"  DDS#1 solo:   {solo1_energy:.0f} ({solo1_energy/noise_energy:.1f}× noise)")

        # DDS#2 solo at phase=0 (reference)
        dds_cmd(dds, 'F1:off')
        dds_cmd(dds, f'F2:{drive2}')
        dds_cmd(dds, 'P2:0')
        time.sleep(0.3)
        _, solo2_mag = coherent_avg_spectrum(ps, handle, args.navg)
        solo2_energy = mode_energy(solo2_mag, freq, f_target)
        print(f"  DDS#2 solo:   {solo2_energy:.0f} ({solo2_energy/noise_energy:.1f}× noise)")

        # ── Phase sweep: both DDS on, sweep DDS#2 phase ──
        print(f"\n  Sweeping DDS#2 phase (DDS#1 fixed at phase=0, freq={drive1})...")
        dds_cmd(dds, f'F1:{drive1}')
        dds_cmd(dds, 'P1:0')
        dds_cmd(dds, f'F2:{drive2}')

        energies = np.zeros(n_steps)
        full_spec_rms = np.zeros(n_steps)

        for i, pval in enumerate(phase_values):
            resp = dds_cmd(dds, f'P2:{pval}')
            time.sleep(0.1)
            _, mag = coherent_avg_spectrum(ps, handle, args.navg)
            energies[i] = mode_energy(mag, freq, f_target)
            full_spec_rms[i] = np.sqrt(np.mean(mag ** 2))

            if (i + 1) % max(1, n_steps // 10) == 0:
                pct = (i + 1) / n_steps * 100
                deg = phase_degrees[i]
                print(f"    [{pct:3.0f}%] phase={pval:4d} ({deg:5.1f}°) "
                      f"energy={energies[i]:.0f} "
                      f"({energies[i]/solo1_energy*100:.0f}% of solo)")

        # Find optimal phase
        min_idx = np.argmin(energies)
        max_idx = np.argmax(energies)
        optimal_phase = int(phase_values[min_idx])
        optimal_deg = phase_degrees[min_idx]
        min_energy = energies[min_idx]
        max_energy = energies[max_idx]
        contrast = (max_energy - min_energy) / max_energy * 100 if max_energy > 0 else 0

        print(f"\n  ── RESULTS for ~{f_target:.0f} Hz ──")
        print(f"  Best erase phase:  {optimal_phase} ({optimal_deg:.1f}°)")
        print(f"  Min energy:        {min_energy:.0f} ({min_energy/noise_energy:.1f}× noise)")
        print(f"  Max energy:        {max_energy:.0f} ({max_energy/noise_energy:.1f}× noise)")
        print(f"  DDS#1 solo:        {solo1_energy:.0f}")
        print(f"  Interference contrast: {contrast:.1f}%")
        print(f"  Erase depth vs solo: {(1 - min_energy/solo1_energy)*100:.1f}% reduction")

        if min_energy < solo1_energy * 0.5:
            print(f"  ✓✓ STRONG ERASE — mode energy halved at optimal phase")
        elif min_energy < solo1_energy * 0.8:
            print(f"  ✓ PARTIAL ERASE — {(1-min_energy/solo1_energy)*100:.0f}% reduction")
        elif min_energy < solo1_energy:
            print(f"  ~ WEAK ERASE — only {(1-min_energy/solo1_energy)*100:.0f}% reduction")
        else:
            print(f"  ✗ NO ERASE — minimum is above solo energy")

        results[f"{f_target:.0f}"] = {
            'eigenmode_freq': f_target,
            'drive1': drive1,
            'drive2': drive2,
            'noise_energy': float(noise_energy),
            'solo1_energy': float(solo1_energy),
            'solo2_energy': float(solo2_energy),
            'phase_values': phase_values.tolist(),
            'phase_degrees': phase_degrees.tolist(),
            'energies': energies.tolist(),
            'full_spec_rms': full_spec_rms.tolist(),
            'optimal_phase': optimal_phase,
            'optimal_deg': float(optimal_deg),
            'min_energy': float(min_energy),
            'max_energy': float(max_energy),
            'contrast_pct': float(contrast),
        }

    dds_cmd(dds, 'Foff')

    # Save results
    out_path = DATA_DIR / 'phase_sweep_erase.json'
    with open(out_path, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\nPhase sweep data saved to {out_path}")

    return results


# ═══════════════════════════════════════════════════════════════════
#  PHASE 2: Write → Erase → Rewrite → Verify Cycling
# ═══════════════════════════════════════════════════════════════════

def write_erase_cycle(ps, handle, dds, shared, sweep_results):
    """Attempt full write→erase→verify cycles using optimal phases."""
    print("\n" + "=" * 60)
    print("PHASE 2: WRITE → ERASE → REWRITE → VERIFY CYCLING")
    print("=" * 60)

    n_cycles = args.cycles

    for s in shared:
        f_target = s['eigenmode_freq']
        key = f"{f_target:.0f}"
        if key not in sweep_results:
            print(f"\n  Skipping ~{f_target:.0f} Hz (no sweep data)")
            continue

        sr = sweep_results[key]
        drive1 = sr['drive1']
        drive2 = sr['drive2']
        optimal_phase = sr['optimal_phase']
        optimal_deg = sr['optimal_deg']
        noise_energy = sr['noise_energy']

        print(f"\n--- Eigenmode ~{f_target:.0f} Hz ---")
        print(f"  DDS#1 drive: {drive1} Hz (write)")
        print(f"  DDS#2 drive: {drive2} Hz, phase={optimal_phase} ({optimal_deg:.1f}°) (erase)")
        print(f"  Cycles: {n_cycles}")

        freq = None
        cycle_data = {
            'baseline': [], 'written': [], 'erased': [],
            'rewritten': [], 'cosine_write': [], 'cosine_erase': [],
        }

        # Baseline (everything off)
        dds_cmd(dds, 'Foff')
        dds_cmd(dds, 'P1:0')
        dds_cmd(dds, 'P2:0')
        time.sleep(0.3)
        freq, baseline_mag = coherent_avg_spectrum(ps, handle, args.navg)
        baseline_energy = mode_energy(baseline_mag, freq, f_target)
        print(f"  Baseline energy: {baseline_energy:.0f}")

        print(f"\n  {'Cycle':>5} | {'Written':>8} | {'Erased':>8} | "
              f"{'Erase%':>7} | {'Re-written':>10} | {'Recovery%':>9}")
        print(f"  {'-'*5:>5} | {'-'*8:>8} | {'-'*8:>8} | "
              f"{'-'*7:>7} | {'-'*10:>10} | {'-'*9:>9}")

        for c in range(n_cycles):
            # ── WRITE: DDS#1 on, DDS#2 off ──
            dds_cmd(dds, f'F2:off')
            dds_cmd(dds, 'P1:0')
            dds_cmd(dds, f'F1:{drive1}')
            time.sleep(0.3)
            _, write_mag = coherent_avg_spectrum(ps, handle, args.navg)
            write_energy = mode_energy(write_mag, freq, f_target)

            # ── ERASE: Add DDS#2 at optimal antiphase ──
            dds_cmd(dds, f'P2:{optimal_phase}')
            dds_cmd(dds, f'F2:{drive2}')
            time.sleep(0.3)
            _, erase_mag = coherent_avg_spectrum(ps, handle, args.navg)
            erase_energy = mode_energy(erase_mag, freq, f_target)

            # Turn off DDS#2 (erase off), keep DDS#1 (rewrite check)
            dds_cmd(dds, f'F2:off')
            time.sleep(0.3)
            _, rewrite_mag = coherent_avg_spectrum(ps, handle, args.navg)
            rewrite_energy = mode_energy(rewrite_mag, freq, f_target)

            # Metrics
            erase_pct = (1 - erase_energy / write_energy) * 100 if write_energy > 0 else 0
            recovery_pct = (rewrite_energy / write_energy) * 100 if write_energy > 0 else 0

            cycle_data['written'].append(float(write_energy))
            cycle_data['erased'].append(float(erase_energy))
            cycle_data['rewritten'].append(float(rewrite_energy))

            # Cosine similarity (full spectrum)
            cos_we = np.dot(write_mag, erase_mag) / (
                np.linalg.norm(write_mag) * np.linalg.norm(erase_mag))
            cos_wr = np.dot(write_mag, rewrite_mag) / (
                np.linalg.norm(write_mag) * np.linalg.norm(rewrite_mag))
            cycle_data['cosine_erase'].append(float(cos_we))
            cycle_data['cosine_write'].append(float(cos_wr))

            print(f"  {c+1:>5} | {write_energy:>8.0f} | {erase_energy:>8.0f} | "
                  f"{erase_pct:>6.1f}% | {rewrite_energy:>10.0f} | {recovery_pct:>8.1f}%")

        # Turn everything off between modes
        dds_cmd(dds, 'Foff')
        time.sleep(0.2)

        # ── Summary for this eigenmode ──
        avg_erase = np.mean([(1 - e / w) * 100
                             for w, e in zip(cycle_data['written'], cycle_data['erased'])
                             if w > 0])
        avg_recovery = np.mean([r / w * 100
                                for w, r in zip(cycle_data['written'], cycle_data['rewritten'])
                                if w > 0])
        avg_cos_erase = np.mean(cycle_data['cosine_erase'])
        avg_cos_write = np.mean(cycle_data['cosine_write'])

        print(f"\n  Summary (~{f_target:.0f} Hz, {n_cycles} cycles):")
        print(f"    Avg erase depth:      {avg_erase:.1f}%")
        print(f"    Avg rewrite recovery: {avg_recovery:.1f}%")
        print(f"    Avg cosine (write vs erase):   {avg_cos_erase:.4f}")
        print(f"    Avg cosine (write vs rewrite):  {avg_cos_write:.4f}")

        if avg_erase > 30 and avg_recovery > 80:
            print(f"    ✓✓ WRITE/ERASE CYCLING WORKS — "
                  f"{avg_erase:.0f}% erase, {avg_recovery:.0f}% recovery")
        elif avg_erase > 20:
            print(f"    ✓ PARTIAL — erase works ({avg_erase:.0f}%) but "
                  f"recovery {'good' if avg_recovery > 80 else 'incomplete'}")
        else:
            print(f"    ✗ INSUFFICIENT ERASE — only {avg_erase:.0f}% reduction")

    # Also try the most interesting test: address selectivity
    # Write mode A via DDS#1, erase mode A via DDS#2,
    # verify mode B (different eigenmode) is unaffected
    if len(shared) >= 2:
        print(f"\n\n{'='*60}")
        print("PHASE 3: ADDRESS SELECTIVITY — ERASE ONE MODE, PRESERVE ANOTHER")
        print(f"{'='*60}")

        mode_a = shared[0]
        mode_b = shared[1] if len(shared) > 1 else shared[0]
        fa = mode_a['eigenmode_freq']
        fb = mode_b['eigenmode_freq']

        key_a = f"{fa:.0f}"
        if key_a not in sweep_results:
            print("  No sweep data for mode A, skipping")
            return

        sr_a = sweep_results[key_a]

        print(f"  Mode A (target): ~{fa:.0f} Hz")
        print(f"  Mode B (bystander): ~{fb:.0f} Hz")
        print(f"  Erase phase for A: {sr_a['optimal_phase']} ({sr_a['optimal_deg']:.1f}°)")

        # Baseline
        dds_cmd(dds, 'Foff')
        dds_cmd(dds, 'P1:0')
        dds_cmd(dds, 'P2:0')
        time.sleep(0.3)
        freq, baseline_mag = coherent_avg_spectrum(ps, handle, args.navg)
        base_a = mode_energy(baseline_mag, freq, fa)
        base_b = mode_energy(baseline_mag, freq, fb)

        # Write mode A (DDS#1 at mode A's drive freq)
        dds_cmd(dds, f'F1:{sr_a["drive1"]}')
        time.sleep(0.3)
        _, write_mag = coherent_avg_spectrum(ps, handle, args.navg)
        write_a = mode_energy(write_mag, freq, fa)
        write_b = mode_energy(write_mag, freq, fb)

        # Erase mode A (add DDS#2 at optimal antiphase)
        dds_cmd(dds, f'P2:{sr_a["optimal_phase"]}')
        dds_cmd(dds, f'F2:{sr_a["drive2"]}')
        time.sleep(0.3)
        _, erase_mag = coherent_avg_spectrum(ps, handle, args.navg)
        erase_a = mode_energy(erase_mag, freq, fa)
        erase_b = mode_energy(erase_mag, freq, fb)

        dds_cmd(dds, 'Foff')

        print(f"\n  {'':>15} | {'Baseline':>10} | {'Written':>10} | {'After Erase':>12}")
        print(f"  {'Mode A (target)':>15} | {base_a:>10.0f} | {write_a:>10.0f} | {erase_a:>12.0f}")
        print(f"  {'Mode B (bystdr)':>15} | {base_b:>10.0f} | {write_b:>10.0f} | {erase_b:>12.0f}")

        a_change = (erase_a - write_a) / write_a * 100 if write_a > 0 else 0
        b_change = (erase_b - write_b) / write_b * 100 if write_b > 0 else 0

        print(f"\n  Mode A change after erase: {a_change:+.1f}%")
        print(f"  Mode B change after erase: {b_change:+.1f}%")

        if a_change < -20 and abs(b_change) < 15:
            print(f"  ✓✓ ADDRESS SELECTIVE — erased A by {-a_change:.0f}%, "
                  f"B changed only {abs(b_change):.0f}%")
        elif a_change < -20:
            print(f"  ✓ ERASE WORKS but bystander affected ({b_change:+.0f}%)")
        else:
            print(f"  ✗ ERASE INSUFFICIENT at this mode ({a_change:+.0f}%)")


# ═══════════════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    shared = load_shared_eigenmodes()
    if not shared:
        print("No shared eigenmodes found. Run eigenmode_sweep first.")
        sys.exit(1)

    print(f"Shared eigenmodes: {len(shared)}")
    for s in shared:
        print(f"  ~{s['eigenmode_freq']:.0f} Hz: "
              f"DDS#1@{s['best_drive_1']}Hz, DDS#2@{s['best_drive_2']}Hz")

    # Check firmware phase support
    print("\nVerifying DDS firmware has phase control...")

    ps, handle, dds, mux = setup_hardware()

    mux.write(f'{args.mux_channel}\n'.encode())
    time.sleep(0.15)
    mux.readline()
    time.sleep(0.1)

    # Test phase command
    resp = dds_cmd(dds, 'P1:0')
    if 'PH1' in resp:
        print(f"  ✓ Phase control confirmed: {resp}")
    elif 'ERR' in resp:
        print(f"  ✗ Firmware does not support phase commands: {resp}")
        print("    Flash updated dds_controller.ino first!")
        cleanup_hardware(ps, handle, dds, mux)
        sys.exit(1)
    else:
        print(f"  ? Unexpected response: {resp}")
        print("    Continuing anyway...")

    try:
        if args.skip_sweep:
            sweep_path = DATA_DIR / 'phase_sweep_erase.json'
            if sweep_path.exists():
                with open(sweep_path) as f:
                    sweep_results = json.load(f)
                print(f"\nLoaded saved phase sweep from {sweep_path}")
            else:
                print(f"No saved sweep at {sweep_path}, running sweep...")
                sweep_results = phase_sweep(ps, handle, dds, shared)
        else:
            sweep_results = phase_sweep(ps, handle, dds, shared)

        # Phase 2: Write/erase cycling
        write_erase_cycle(ps, handle, dds, shared, sweep_results)

    finally:
        cleanup_hardware(ps, handle, dds, mux)

    print(f"\n{'='*60}")
    print("EXPERIMENT COMPLETE")
    print(f"{'='*60}")
