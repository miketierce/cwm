"""Tests for the hardware-independent parts of the FT-1 capture tool."""

import numpy as np
import pytest

from tools.k_eff_ft1_capture import SYS_CLK, demod, pack_raw, pio_actual_freq, trial_order

FS = 781_250.0
N = 3072


def tone(freq, amp, phase, delay_s=0.0):
    t = np.arange(N) / FS - delay_s
    return amp * np.cos(2 * np.pi * freq * t + phase)


@pytest.mark.parametrize('freq', [30_000.0, 54_321.7, 97_013.3, 120_000.0])
def test_demod_recovers_peak_amplitude_and_phase_off_bin(freq):
    z = demod(tone(freq, 812.5, 0.7) + 40.0, freq, FS)

    assert abs(z) == pytest.approx(812.5, rel=1e-3)
    assert np.angle(z) == pytest.approx(0.7, abs=1e-3)


def test_transfer_ratio_is_independent_of_common_capture_timing():
    f = 73_750.0
    ratios = []
    for delay in (0.0, 3.1e-6, 11.7e-6):
        za = demod(tone(f, 300.0, 1.2, delay), f, FS)
        zb = demod(tone(f, 600.0, 0.4, delay), f, FS)
        ratios.append(za / zb)

    for r in ratios:
        assert abs(r) == pytest.approx(0.5, rel=1e-3)
        assert np.angle(r) == pytest.approx(0.8, abs=1e-3)


def test_pio_actual_frequency_is_an_integer_clock_divisor():
    assert pio_actual_freq(100_000) == 100_000.0
    f = pio_actual_freq(54_321)
    assert SYS_CLK / f == pytest.approx(round(SYS_CLK / f), abs=1e-6)
    assert f == pytest.approx(54_321, rel=5e-4)


def test_trial_order_covers_every_point_once_and_is_seeded():
    grid = [30_000, 30_500, 31_000]
    plan = trial_order(grid, 4, seed=7)

    assert sorted(plan) == sorted((f, r) for f in grid for r in range(4))
    assert plan == trial_order(grid, 4, seed=7)
    assert plan != trial_order(grid, 4, seed=8)


def test_pack_raw_is_lossless():
    eight_bit = np.array([[-128, 0, 127]], np.int16) * 256
    packed = pack_raw(eight_bit)
    assert packed.dtype == np.int8
    np.testing.assert_array_equal(packed.astype(np.int16) * 256, eight_bit)

    finer = np.array([[1, 2, 3]], np.int16)
    assert pack_raw(finer).dtype == np.int16
