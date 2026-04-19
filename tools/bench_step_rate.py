#!/usr/bin/env python3
"""Benchmark: minimum step time for temporal reservoir."""
import ctypes
import time
import numpy as np

# Must set DYLD_LIBRARY_PATH before importing
from picosdk.ps2000 import ps2000

TIMEBASE = 7
N_SAMPLES = 256

def wait_ready(handle, timeout_s=2.0):
    """Poll ps2000_ready with timeout to avoid infinite hang."""
    t0 = time.perf_counter()
    while ps2000.ps2000_ready(handle) == 0:
        if time.perf_counter() - t0 > timeout_s:
            raise TimeoutError(f"ps2000_ready timed out after {timeout_s}s")
    return time.perf_counter() - t0


def main():
    handle = ps2000.ps2000_open_unit()
    assert handle > 0, f"open failed: {handle}"
    print(f"  handle={handle}")

    # Reset scope state from any previous crash
    ps2000.ps2000_stop(handle)
    time.sleep(0.05)

    ps2000.ps2000_set_channel(handle, 0, True, 1, 6)
    ps2000.ps2000_set_channel(handle, 1, False, 1, 6)
    # source=5 (none/auto), auto_ms=1  — matches cwm_picoscope.py
    ps2000.ps2000_set_trigger(handle, 5, 0, 0, 0, 1)

    # Pre-allocate reusable ctypes buffers (avoid per-call alloc)
    buf_a = (ctypes.c_int16 * N_SAMPLES)()
    buf_b = (ctypes.c_int16 * N_SAMPLES)()
    overflow = ctypes.c_int16()
    t_ms = ctypes.c_int32()

    # Warm-up: verify scope is responsive
    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, 1_000_000, 0, 29900.0, 29900.0, 0.0, 0.0, 0, 0)
    time.sleep(0.1)
    ps2000.ps2000_run_block(handle, N_SAMPLES, TIMEBASE, 1, ctypes.byref(t_ms))
    try:
        wait_ready(handle, timeout_s=5.0)
    except TimeoutError:
        print("ERROR: Scope not responding. Unplug and replug USB cable.")
        ps2000.ps2000_close_unit(handle)
        return
    ps2000.ps2000_get_values(
        handle, ctypes.byref(buf_a), ctypes.byref(buf_b),
        None, None, ctypes.byref(overflow), N_SAMPLES)
    print("  Warm-up capture OK")

    N = 500
    rng = np.random.default_rng(42)
    amps = rng.integers(100_000, 2_000_000, N).astype(np.int32)
    waveforms = np.zeros((N, N_SAMPLES), dtype=np.int16)

    # ── Test 1: Tight inlined loop ─────────────────────────────
    print("Test 1: Inlined loop (500 steps)")
    step_times = np.zeros(N)
    t0 = time.perf_counter()
    for i in range(N):
        ts = time.perf_counter()
        ps2000.ps2000_set_sig_gen_built_in(
            handle, 0, int(amps[i]), 0, 29900.0, 29900.0, 0.0, 0.0, 0, 0)
        ps2000.ps2000_run_block(handle, N_SAMPLES, TIMEBASE, 1, ctypes.byref(t_ms))
        while ps2000.ps2000_ready(handle) == 0:
            pass
        ps2000.ps2000_get_values(
            handle, ctypes.byref(buf_a), ctypes.byref(buf_b),
            None, None, ctypes.byref(overflow), N_SAMPLES)
        waveforms[i] = np.frombuffer(buf_a, dtype=np.int16, count=N_SAMPLES)
        step_times[i] = time.perf_counter() - ts
    total = time.perf_counter() - t0
    ms = step_times * 1000

    print(f"  Rate: {N/total:.1f} Hz ({ms.mean():.2f} ms/step)")
    print(f"  p50={np.median(ms):.2f} p95={np.percentile(ms, 95):.2f} "
          f"max={ms.max():.2f}")

    # ── Test 2: Component timing ─────────────────────────────
    print("\nTest 2: Component timing (100 steps)")
    t_sig, t_blk, t_rdy, t_get, t_cpy = [], [], [], [], []
    for i in range(100):
        a = time.perf_counter()
        ps2000.ps2000_set_sig_gen_built_in(
            handle, 0, int(amps[i]), 0, 29900.0, 29900.0, 0.0, 0.0, 0, 0)
        b = time.perf_counter()
        ps2000.ps2000_run_block(handle, N_SAMPLES, TIMEBASE, 1, ctypes.byref(t_ms))
        c = time.perf_counter()
        while ps2000.ps2000_ready(handle) == 0:
            pass
        d = time.perf_counter()
        ps2000.ps2000_get_values(
            handle, ctypes.byref(buf_a), ctypes.byref(buf_b),
            None, None, ctypes.byref(overflow), N_SAMPLES)
        e = time.perf_counter()
        waveforms[i] = np.frombuffer(buf_a, dtype=np.int16, count=N_SAMPLES)
        f = time.perf_counter()
        t_sig.append(b - a)
        t_blk.append(c - b)
        t_rdy.append(d - c)
        t_get.append(e - d)
        t_cpy.append(f - e)

    print(f"  sig_gen:    {np.mean(t_sig)*1000:.2f} ms")
    print(f"  run_block:  {np.mean(t_blk)*1000:.2f} ms")
    print(f"  ready_wait: {np.mean(t_rdy)*1000:.2f} ms")
    print(f"  get_values: {np.mean(t_get)*1000:.2f} ms")
    print(f"  np.copy:    {np.mean(t_cpy)*1000:.3f} ms")
    total_ms = sum(np.mean(t) for t in [t_sig, t_blk, t_rdy, t_get, t_cpy]) * 1000
    print(f"  TOTAL:      {total_ms:.2f} ms")

    # ── Test 3: Capture-only (no sig_gen change) ───────────────
    print("\nTest 3: Capture-only (no AWG change, 200 steps)")
    cap_times = []
    for _ in range(200):
        ts = time.perf_counter()
        ps2000.ps2000_run_block(handle, N_SAMPLES, TIMEBASE, 1, ctypes.byref(t_ms))
        while ps2000.ps2000_ready(handle) == 0:
            pass
        ps2000.ps2000_get_values(
            handle, ctypes.byref(buf_a), ctypes.byref(buf_b),
            None, None, ctypes.byref(overflow), N_SAMPLES)
        cap_times.append(time.perf_counter() - ts)
    cap_ms = np.array(cap_times) * 1000
    print(f"  Rate: {200/(sum(cap_times)):.1f} Hz ({cap_ms.mean():.2f} ms)")

    # ── Test 4: Amplitude verification ─────────────────────────
    print("\nTest 4: Amplitude verification")
    for amp_uvpp, label in [(2_000_000, "HIGH"), (200_000, "LOW")]:
        rmss = []
        for _ in range(10):
            ps2000.ps2000_set_sig_gen_built_in(
                handle, 0, amp_uvpp, 0, 29900.0, 29900.0, 0.0, 0.0, 0, 0)
            ps2000.ps2000_run_block(
                handle, N_SAMPLES, TIMEBASE, 1, ctypes.byref(t_ms))
            while ps2000.ps2000_ready(handle) == 0:
                pass
            ps2000.ps2000_get_values(
                handle, ctypes.byref(buf_a), ctypes.byref(buf_b),
                None, None, ctypes.byref(overflow), N_SAMPLES)
            d = np.frombuffer(buf_a, dtype=np.int16, count=N_SAMPLES).astype(float)
            rmss.append(np.sqrt(np.mean(d ** 2)))
        print(f"  {label} ({amp_uvpp/1e6:.1f}Vpp): RMS={np.mean(rmss[-5:]):.1f}")

    # ── Temporal retention summary ─────────────────────────────
    tau = 1.99
    mean_ms = ms.mean()
    ret = np.exp(-mean_ms / tau)
    print(f"\nTemporal retention at {1000/mean_ms:.0f} Hz ({mean_ms:.1f}ms/step):")
    for name, tau_ms in [("29.9k", 1.99), ("19.0k", 2.07), ("68.2k", 1.49)]:
        r1 = np.exp(-mean_ms / tau_ms)
        r2 = r1 ** 2
        print(f"  {name} (tau={tau_ms}ms): {r1*100:.1f}% per step, "
              f"{r2*100:.2f}% @ 2 steps")

    # ── Test 5: Pipelined (capture THEN sig_gen) ───────────────
    print("\nTest 5: Pipelined — capture first, sig_gen after (500 steps)")
    step_times5 = np.zeros(N)
    # Initial sig_gen for first step
    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, int(amps[0]), 0, 29900.0, 29900.0, 0.0, 0.0, 0, 0)
    time.sleep(0.02)  # let first DDS settle
    t0 = time.perf_counter()
    for i in range(N):
        ts = time.perf_counter()
        # Capture current state (DDS should have settled from prev sig_gen)
        ps2000.ps2000_run_block(handle, N_SAMPLES, TIMEBASE, 1, ctypes.byref(t_ms))
        while ps2000.ps2000_ready(handle) == 0:
            pass
        ps2000.ps2000_get_values(
            handle, ctypes.byref(buf_a), ctypes.byref(buf_b),
            None, None, ctypes.byref(overflow), N_SAMPLES)
        waveforms[i] = np.frombuffer(buf_a, dtype=np.int16, count=N_SAMPLES)
        # Set NEXT amplitude (DDS update runs in background during next iteration)
        next_amp = int(amps[(i + 1) % N])
        ps2000.ps2000_set_sig_gen_built_in(
            handle, 0, next_amp, 0, 29900.0, 29900.0, 0.0, 0.0, 0, 0)
        step_times5[i] = time.perf_counter() - ts
    total5 = time.perf_counter() - t0
    ms5 = step_times5 * 1000
    print(f"  Rate: {N/total5:.1f} Hz ({ms5.mean():.2f} ms/step)")
    print(f"  p50={np.median(ms5):.2f} p95={np.percentile(ms5, 95):.2f} "
          f"max={ms5.max():.2f}")

    # ── Test 6: sig_gen → sleep → capture (DDS settle test) ────
    print("\nTest 6: sig_gen → sleep(15ms) → capture (100 steps)")
    step_times6 = np.zeros(100)
    for i in range(100):
        ps2000.ps2000_set_sig_gen_built_in(
            handle, 0, int(amps[i]), 0, 29900.0, 29900.0, 0.0, 0.0, 0, 0)
        time.sleep(0.015)
        ts = time.perf_counter()
        ps2000.ps2000_run_block(handle, N_SAMPLES, TIMEBASE, 1, ctypes.byref(t_ms))
        while ps2000.ps2000_ready(handle) == 0:
            pass
        ps2000.ps2000_get_values(
            handle, ctypes.byref(buf_a), ctypes.byref(buf_b),
            None, None, ctypes.byref(overflow), N_SAMPLES)
        step_times6[i] = time.perf_counter() - ts
    ms6 = step_times6 * 1000
    print(f"  Capture after 15ms settle: {ms6.mean():.2f} ms "
          f"(p50={np.median(ms6):.2f})")

    # ── Test 7: Frequency encoding instead of amplitude ────────
    print("\nTest 7: Frequency change only (amplitude fixed, 200 steps)")
    freqs = np.linspace(28000.0, 32000.0, 200)
    step_times7 = np.zeros(200)
    t0 = time.perf_counter()
    for i in range(200):
        ts = time.perf_counter()
        ps2000.ps2000_set_sig_gen_built_in(
            handle, 0, 1_000_000, 0, freqs[i], freqs[i], 0.0, 0.0, 0, 0)
        ps2000.ps2000_run_block(handle, N_SAMPLES, TIMEBASE, 1, ctypes.byref(t_ms))
        while ps2000.ps2000_ready(handle) == 0:
            pass
        ps2000.ps2000_get_values(
            handle, ctypes.byref(buf_a), ctypes.byref(buf_b),
            None, None, ctypes.byref(overflow), N_SAMPLES)
        step_times7[i] = time.perf_counter() - ts
    total7 = time.perf_counter() - t0
    ms7 = step_times7 * 1000
    print(f"  Rate: {200/total7:.1f} Hz ({ms7.mean():.2f} ms/step)")
    print(f"  p50={np.median(ms7):.2f} p95={np.percentile(ms7, 95):.2f}")

    # ── Test 8: Pipelined capture-then-siggen component timing ─
    print("\nTest 8: Pipelined component timing (100 steps)")
    t_cap8, t_sig8 = [], []
    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, int(amps[0]), 0, 29900.0, 29900.0, 0.0, 0.0, 0, 0)
    time.sleep(0.02)
    for i in range(100):
        a = time.perf_counter()
        ps2000.ps2000_run_block(handle, N_SAMPLES, TIMEBASE, 1, ctypes.byref(t_ms))
        while ps2000.ps2000_ready(handle) == 0:
            pass
        ps2000.ps2000_get_values(
            handle, ctypes.byref(buf_a), ctypes.byref(buf_b),
            None, None, ctypes.byref(overflow), N_SAMPLES)
        b = time.perf_counter()
        ps2000.ps2000_set_sig_gen_built_in(
            handle, 0, int(amps[(i+1) % N]), 0, 29900.0, 29900.0, 0.0, 0.0, 0, 0)
        c = time.perf_counter()
        t_cap8.append(b - a)
        t_sig8.append(c - b)
    print(f"  capture: {np.mean(t_cap8)*1000:.2f} ms  sig_gen: {np.mean(t_sig8)*1000:.2f} ms")
    print(f"  total: {(np.mean(t_cap8) + np.mean(t_sig8))*1000:.2f} ms")
    pipe_rate = 1000 / ((np.mean(t_cap8) + np.mean(t_sig8)) * 1000)
    print(f"  Effective rate: {pipe_rate:.1f} Hz")

    mean_pipe = (np.mean(t_cap8) + np.mean(t_sig8)) * 1000
    print(f"\n  Pipelined retention at {1000/mean_pipe:.0f} Hz ({mean_pipe:.1f}ms/step):")
    for name, tau_ms in [("29.9k", 1.99), ("19.0k", 2.07), ("68.2k", 1.49)]:
        r1 = np.exp(-mean_pipe / tau_ms)
        print(f"    {name}: {r1*100:.1f}% per step")

    # Cleanup
    ps2000.ps2000_set_sig_gen_built_in(
        handle, 0, 0, 0, 1000.0, 1000.0, 0.0, 0.0, 0, 0)
    ps2000.ps2000_stop(handle)
    ps2000.ps2000_close_unit(handle)
    print("\nDone.")

if __name__ == "__main__":
    main()
