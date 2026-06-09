"""
Ringdown Capture — 321 kHz mode on 25mm plate
==============================================
Drive at resonance for 200ms, kill NCO, capture decay.
Q = 6750 → τ = 6.7ms → expect clear exponential decay in 10ms window.

Drive: F4 (GP5, pin 7) → 25mm plate SW TX
Read:  Relay 5 = 25mm NW RX

Usage:
    python tools/ringdown_capture.py
"""

import ctypes
import time
import serial
import numpy as np
import sys
import os
import json
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
from relay_mux import RelayMux

# ─── Configuration ───────────────────────────────────────────────
PICO_LIB = '/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources/libps2000.dylib'
NCO_PORT = '/dev/cu.usbmodem113301'
MUX_PORT = '/dev/cu.usbserial-11310'

# Target mode
FREQ_HZ = 320_650   # bare2 NW measurement of 321 kHz mode

# Capture settings — TB7 for maximum window length
TIMEBASE = 7         # 1280 ns/sample → 781.25 kS/s
N_SAMPLES = 8064     # 10.3 ms capture window

# Timing
DRIVE_MS = 200       # drive for 200ms (30× τ, well past steady state)
POST_OFF_DELAY_MS = 0.5  # tiny delay after Foff before capture

NCO_CMD = 'F4'
RELAY = 5            # 25mm NW — best signal

# ─── Helpers ─────────────────────────────────────────────────────
def setup_picoscope():
    ps = ctypes.CDLL(PICO_LIB)
    handle = ps.ps2000_open_unit()
    if handle <= 0:
        raise RuntimeError(f"PicoScope open failed: {handle}")
    ps.ps2000_set_channel(handle, 0, 1, 1, 6)   # Ch A on, DC, ±1V
    ps.ps2000_set_channel(handle, 1, 0, 1, 6)   # Ch B off
    ps.ps2000_set_trigger(handle, 5, 0, 0, 0, 0) # no trigger, free-run
    return ps, handle


def acquire(ps, handle):
    """Capture one block, return raw array in mV."""
    t_ms = ctypes.c_int32()
    ps.ps2000_run_block(handle, N_SAMPLES, TIMEBASE, 1, ctypes.byref(t_ms))
    count = 0
    while not ps.ps2000_ready(handle):
        time.sleep(0.001)
        count += 1
        if count > 2000:
            return None
    buf = (ctypes.c_int16 * N_SAMPLES)()
    overflow = ctypes.c_int16()
    ps.ps2000_get_values(handle, ctypes.byref(buf), None, None, None,
                         ctypes.byref(overflow), N_SAMPLES)
    data = np.array(buf, dtype=np.float64)
    return data * 1000.0 / 32767.0  # mV (±1V range)


def set_freq(nco, freq):
    """Set NCO frequency."""
    nco.write(f'{NCO_CMD}:{freq}\n'.encode())
    time.sleep(0.05)
    if nco.in_waiting:
        nco.read(nco.in_waiting)


def stop_nco(nco):
    """Kill NCO output."""
    nco.write(b'Foff\n')
    # Don't wait for response — time-critical


# ─── Main ────────────────────────────────────────────────────────
def main():
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    outdir = 'data/results/lab/25mm_plate/ringdown'
    os.makedirs(outdir, exist_ok=True)

    fs = 1e9 / 1280.0  # 781250 Hz
    dt = 1280e-9       # seconds per sample

    print("=" * 60)
    print("RINGDOWN CAPTURE — 25mm Plate, 321 kHz mode")
    print("=" * 60)
    print(f"  Drive: {NCO_CMD} at {FREQ_HZ:,} Hz for {DRIVE_MS} ms")
    print(f"  Capture: {N_SAMPLES} samples at TB{TIMEBASE} = {N_SAMPLES*dt*1000:.1f} ms window")
    print(f"  Expected τ = 6.7 ms (Q ≈ 6750)")
    print()

    # Open hardware
    print("Opening PicoScope...", end=' ', flush=True)
    ps, handle = setup_picoscope()
    print("OK")

    print("Opening NCO...", end=' ', flush=True)
    nco = serial.Serial(NCO_PORT, 115200, timeout=1)
    time.sleep(0.5)
    if nco.in_waiting:
        nco.read(nco.in_waiting)
    print("OK")

    print("Opening relay mux...", end=' ', flush=True)
    mux = RelayMux(MUX_PORT)
    mux.open()
    mux.select(RELAY)
    time.sleep(0.1)
    print("OK")
    print()

    # ─── Capture sequence ───
    # 1. First capture a "driven" reference (steady-state)
    print("1. Capturing driven steady-state reference...")
    set_freq(nco, FREQ_HZ)
    time.sleep(DRIVE_MS / 1000.0)  # let mode build up
    driven_data = acquire(ps, handle)
    if driven_data is None:
        print("   FAILED — no data")
        return
    driven_rms = np.sqrt(np.mean(driven_data**2))
    driven_peak = np.max(np.abs(driven_data))
    print(f"   Driven: RMS={driven_rms:.2f} mV, Peak={driven_peak:.2f} mV")

    # 2. Now the ringdown capture: stop NCO then immediately acquire
    print("2. Ringdown capture (Foff → acquire)...")

    # Keep driving to re-establish steady state
    set_freq(nco, FREQ_HZ)
    time.sleep(DRIVE_MS / 1000.0)

    # Critical timing: stop drive, tiny delay, then capture
    stop_nco(nco)
    time.sleep(POST_OFF_DELAY_MS / 1000.0)
    ringdown_data = acquire(ps, handle)

    if ringdown_data is None:
        print("   FAILED — no data")
        return

    # 3. Capture noise floor (NCO already off)
    print("3. Capturing noise floor...")
    time.sleep(0.05)
    noise_data = acquire(ps, handle)
    noise_rms = np.sqrt(np.mean(noise_data**2)) if noise_data is not None else 0
    print(f"   Noise floor: RMS={noise_rms:.3f} mV")
    print()

    # ─── Analysis ───
    print("─── RINGDOWN ANALYSIS ───")

    # Compute envelope via Hilbert transform
    from scipy.signal import hilbert
    analytic = hilbert(ringdown_data)
    envelope = np.abs(analytic)

    # Time axis
    t_ms_arr = np.arange(N_SAMPLES) * dt * 1000  # milliseconds

    # Find where envelope starts decaying (first point above noise)
    noise_level = noise_rms * 3  # 3σ threshold
    above_noise = envelope > noise_level

    if not np.any(above_noise):
        print("   No signal above noise — ringdown too fast or not captured")
        print(f"   Max envelope: {np.max(envelope):.3f} mV, Noise threshold: {noise_level:.3f} mV")
    else:
        # Find the start and end of ringdown
        first_above = np.argmax(above_noise)
        last_above = len(above_noise) - 1 - np.argmax(above_noise[::-1])

        print(f"   Signal above noise: t = {t_ms_arr[first_above]:.2f} – {t_ms_arr[last_above]:.2f} ms")
        print(f"   Initial envelope: {envelope[first_above]:.2f} mV")
        print(f"   Final envelope: {envelope[last_above]:.3f} mV")
        print(f"   Decay ratio: {envelope[first_above]/max(envelope[last_above], 0.01):.1f}×")
        print()

        # Fit exponential decay: envelope = A * exp(-t/τ)
        # Use log-linear fit on the above-noise region
        mask = above_noise & (envelope > noise_level * 2)  # extra margin
        if np.sum(mask) > 20:
            t_fit = t_ms_arr[mask]
            env_fit = envelope[mask]

            # Log-linear fit: ln(env) = ln(A) - t/τ
            log_env = np.log(env_fit)
            # Remove any NaN/inf
            valid = np.isfinite(log_env)
            t_fit = t_fit[valid]
            log_env = log_env[valid]

            if len(t_fit) > 10:
                coeffs = np.polyfit(t_fit, log_env, 1)
                slope = coeffs[0]  # -1/τ in 1/ms
                intercept = coeffs[1]

                tau_ms = -1.0 / slope
                A_fit = np.exp(intercept)

                # Q from ringdown
                Q_ringdown = np.pi * FREQ_HZ * tau_ms / 1000.0

                # Fit quality (R²)
                predicted = coeffs[0] * t_fit + coeffs[1]
                ss_res = np.sum((log_env - predicted)**2)
                ss_tot = np.sum((log_env - np.mean(log_env))**2)
                r_squared = 1 - ss_res / ss_tot

                print(f"   EXPONENTIAL FIT:")
                print(f"   τ = {tau_ms:.2f} ms")
                print(f"   Q (ringdown) = πf₀τ = {Q_ringdown:.0f}")
                print(f"   A₀ = {A_fit:.2f} mV")
                print(f"   R² = {r_squared:.4f}")
                print()
                print(f"   Compare: Q (frequency-domain BW) = 6750")
                print(f"   Ratio: Q_ringdown / Q_BW = {Q_ringdown/6750:.2f}")
            else:
                print("   Insufficient valid points for exponential fit")
                tau_ms = None
                Q_ringdown = None
                r_squared = None
        else:
            print(f"   Insufficient points above noise ({np.sum(mask)}) for fit")
            tau_ms = None
            Q_ringdown = None
            r_squared = None

    # ─── Save results ───
    output = {
        'timestamp': timestamp,
        'experiment': 'ringdown',
        'plate': '25mm fused silica',
        'mode_hz': FREQ_HZ,
        'drive_cmd': NCO_CMD,
        'relay': RELAY,
        'channel': '25mm NW',
        'drive_ms': DRIVE_MS,
        'post_off_delay_ms': POST_OFF_DELAY_MS,
        'timebase': TIMEBASE,
        'n_samples': N_SAMPLES,
        'fs_hz': fs,
        'dt_ns': 1280,
        'driven_rms_mV': round(float(driven_rms), 3),
        'driven_peak_mV': round(float(driven_peak), 3),
        'noise_rms_mV': round(float(noise_rms), 4),
        'ringdown_waveform_mV': [round(float(x), 3) for x in ringdown_data],
        'envelope_mV': [round(float(x), 3) for x in envelope],
        'driven_waveform_mV': [round(float(x), 3) for x in driven_data],
    }

    if tau_ms is not None:
        output['fit'] = {
            'tau_ms': round(tau_ms, 3),
            'Q_ringdown': round(Q_ringdown, 0),
            'A0_mV': round(float(A_fit), 3),
            'r_squared': round(r_squared, 5),
        }

    outfile = os.path.join(outdir, f'ringdown_{timestamp}.json')
    with open(outfile, 'w') as f:
        json.dump(output, f)
    print(f"\nSaved: {outfile}")

    # Cleanup
    ps.ps2000_close_unit(handle)
    nco.close()
    mux.close()
    print("Hardware closed.")


if __name__ == '__main__':
    main()
