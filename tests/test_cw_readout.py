"""
Tests for CW vs Impulse readout simulation.

Validates the physics of CW lock-in readout against analytical predictions.
"""

import pytest
import numpy as np

from simulations.cw_readout import (
    GlassRodParams,
    ringdown_time,
    impulse_snr,
    cw_snr,
    snr_vs_integration_time,
    find_crossover,
    cw_gain_table,
    two_phase_readout,
    noise_environment_comparison,
    run_cw_readout_analysis,
    V_BAR_BORO, Q_MAT_BORO, V_BAR_SILICA, Q_MAT_SILICA,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def boro_rod():
    """Standard 150mm borosilicate rod."""
    return GlassRodParams()


@pytest.fixture
def mems_rod():
    """1mm MEMS borosilicate rod."""
    return GlassRodParams(L=1e-3, d=40e-6)


@pytest.fixture
def silica_rod():
    """150mm fused silica rod."""
    return GlassRodParams(
        L=0.150,
        v_bar=V_BAR_SILICA,
        rho=2200.0,
        E=73.0e9,
        Q=Q_MAT_SILICA,
    )


# ---------------------------------------------------------------------------
# GlassRodParams property tests
# ---------------------------------------------------------------------------
class TestGlassRodParams:
    """Test physical parameter calculations."""

    def test_fundamental_frequency_boro(self, boro_rod):
        """f₀ = v_bar / (2L) = 5315 / (2×0.15) = 17716.7 Hz."""
        expected = V_BAR_BORO / (2.0 * 0.15)
        assert abs(boro_rod.f0 - expected) < 1.0  # within 1 Hz

    def test_fundamental_frequency_mems(self, mems_rod):
        """f₀ = 5315 / (2×0.001) = 2,657,500 Hz."""
        expected = V_BAR_BORO / (2.0 * 1e-3)
        assert abs(mems_rod.f0 - expected) < 1.0

    def test_ringdown_time_boro(self, boro_rod):
        """τ = Q/(π f₀) = 10000/(π × 17717) ≈ 0.1797 s."""
        expected = 10000.0 / (np.pi * boro_rod.f0)
        assert abs(boro_rod.tau - expected) / expected < 1e-6

    def test_ringdown_time_mems(self, mems_rod):
        """τ = 10000/(π × 2.66 MHz) ≈ 1.2 ms."""
        tau = mems_rod.tau
        assert tau < 2e-3  # less than 2 ms
        assert tau > 0.5e-3  # more than 0.5 ms

    def test_linewidth(self, boro_rod):
        """δf = f₀/Q = 17717/10000 ≈ 1.77 Hz."""
        expected = boro_rod.f0 / boro_rod.Q
        assert abs(boro_rod.linewidth - expected) < 0.01

    def test_effective_mass_positive(self, boro_rod):
        assert boro_rod.m_eff > 0

    def test_effective_spring_constant_positive(self, boro_rod):
        assert boro_rod.k_eff > 0

    def test_thermal_noise_amplitude(self, boro_rod):
        """Thermal noise should be much less than 1 nm."""
        assert boro_rod.thermal_noise_amplitude < 1e-9
        assert boro_rod.thermal_noise_amplitude > 0

    def test_snr_linear_positive(self, boro_rod):
        """SNR at 1 nm drive should be > 1."""
        assert boro_rod.snr_linear > 1.0


# ---------------------------------------------------------------------------
# Ringdown time function
# ---------------------------------------------------------------------------
class TestRingdownTime:
    """Test the standalone ringdown_time function."""

    def test_matches_rod_property(self, boro_rod):
        tau = ringdown_time(boro_rod.Q, boro_rod.f0)
        assert abs(tau - boro_rod.tau) < 1e-12

    def test_proportional_to_Q(self):
        """τ doubles when Q doubles."""
        tau1 = ringdown_time(10000, 17000)
        tau2 = ringdown_time(20000, 17000)
        assert abs(tau2 / tau1 - 2.0) < 1e-10

    def test_inversely_proportional_to_f0(self):
        """τ halves when f₀ doubles."""
        tau1 = ringdown_time(10000, 17000)
        tau2 = ringdown_time(10000, 34000)
        assert abs(tau1 / tau2 - 2.0) < 1e-10


# ---------------------------------------------------------------------------
# Impulse readout
# ---------------------------------------------------------------------------
class TestImpulseReadout:
    """Test impulse (ring-and-listen) readout."""

    def test_returns_correct_strategy(self, boro_rod):
        result = impulse_snr(boro_rod)
        assert result.strategy == "impulse"

    def test_integration_time_equals_tau(self, boro_rod):
        result = impulse_snr(boro_rod)
        assert abs(result.t_int - boro_rod.tau) < 1e-12

    def test_snr_positive(self, boro_rod):
        result = impulse_snr(boro_rod)
        assert result.snr_db > 0
        assert result.snr_linear > 1

    def test_snr_decreases_with_noise(self, boro_rod):
        """Higher noise floor → lower SNR."""
        snr_clean = impulse_snr(boro_rod, noise_floor_db=0).snr_db
        snr_noisy = impulse_snr(boro_rod, noise_floor_db=20).snr_db
        assert snr_noisy < snr_clean

    def test_noise_floor_shifts_snr_exactly(self, boro_rod):
        """Adding X dB noise floor reduces SNR by X dB."""
        nf = 20.0
        snr_clean = impulse_snr(boro_rod, noise_floor_db=0).snr_db
        snr_noisy = impulse_snr(boro_rod, noise_floor_db=nf).snr_db
        assert abs((snr_clean - snr_noisy) - nf) < 0.01

    def test_bandwidth_equals_1_over_tau(self, boro_rod):
        result = impulse_snr(boro_rod)
        expected_bw = 1.0 / boro_rod.tau
        assert abs(result.bandwidth - expected_bw) < 1e-6

    def test_energy_positive(self, boro_rod):
        result = impulse_snr(boro_rod)
        assert result.energy_total > 0
        assert result.power_avg > 0


# ---------------------------------------------------------------------------
# CW readout
# ---------------------------------------------------------------------------
class TestCWReadout:
    """Test CW lock-in readout."""

    def test_returns_correct_strategy(self, boro_rod):
        result = cw_snr(boro_rod, t_int=1.0)
        assert result.strategy == "cw"

    def test_at_tau_matches_impulse(self, boro_rod):
        """At T_int = τ, CW should match impulse (break-even)."""
        tau = boro_rod.tau
        imp = impulse_snr(boro_rod)
        cw = cw_snr(boro_rod, t_int=tau)
        assert abs(cw.snr_db - imp.snr_db) < 0.5  # within 0.5 dB

    def test_exceeds_impulse_at_longer_times(self, boro_rod):
        """CW at 10s should exceed impulse."""
        imp = impulse_snr(boro_rod)
        cw = cw_snr(boro_rod, t_int=10.0)
        assert cw.snr_db > imp.snr_db

    def test_gain_follows_sqrt_law(self, boro_rod):
        """CW gain should be 10·log10(T_int/τ) in power = 5·log10(T_int/τ) in amplitude.

        Actually we report power SNR, so gain = 10·log10(T_int/τ).
        """
        tau = boro_rod.tau
        t_int = 10.0
        imp = impulse_snr(boro_rod)
        cw = cw_snr(boro_rod, t_int=t_int)
        expected_gain = 10.0 * np.log10(t_int / tau)
        actual_gain = cw.snr_db - imp.snr_db
        assert abs(actual_gain - expected_gain) < 0.5

    def test_minimum_integration_time_is_tau(self, boro_rod):
        """If t_int < τ, effective time should be clamped to τ."""
        tau = boro_rod.tau
        result = cw_snr(boro_rod, t_int=tau / 100)
        assert result.t_int >= tau

    def test_snr_decreases_with_noise(self, boro_rod):
        """Higher noise floor → lower CW SNR."""
        snr_clean = cw_snr(boro_rod, 10.0, noise_floor_db=0).snr_db
        snr_noisy = cw_snr(boro_rod, 10.0, noise_floor_db=20).snr_db
        assert snr_noisy < snr_clean

    def test_bandwidth_narrows_with_time(self, boro_rod):
        """Longer integration → narrower bandwidth."""
        bw1 = cw_snr(boro_rod, t_int=1.0).bandwidth
        bw2 = cw_snr(boro_rod, t_int=10.0).bandwidth
        assert bw2 < bw1

    def test_energy_grows_with_time(self, boro_rod):
        """Longer integration costs more energy."""
        e1 = cw_snr(boro_rod, t_int=1.0).energy_total
        e2 = cw_snr(boro_rod, t_int=10.0).energy_total
        assert e2 > e1


# ---------------------------------------------------------------------------
# SNR curves
# ---------------------------------------------------------------------------
class TestSNRCurves:
    """Test SNR-vs-time curve generation."""

    def test_returns_correct_shapes(self, boro_rod):
        t, snr_imp, snr_cw = snr_vs_integration_time(boro_rod)
        assert len(t) == len(snr_imp) == len(snr_cw)
        assert len(t) > 10

    def test_impulse_is_flat(self, boro_rod):
        """Impulse SNR should be constant (no benefit from waiting)."""
        t, snr_imp, snr_cw = snr_vs_integration_time(boro_rod)
        assert np.std(snr_imp) < 0.01  # essentially constant

    def test_cw_grows_monotonically(self, boro_rod):
        """CW SNR should increase with integration time."""
        t, snr_imp, snr_cw = snr_vs_integration_time(boro_rod)
        # After τ, CW should be monotonically increasing
        tau = boro_rod.tau
        mask = t >= tau
        cw_post_tau = snr_cw[mask]
        diffs = np.diff(cw_post_tau)
        assert np.all(diffs >= -0.01)  # non-decreasing (allow tiny float noise)


# ---------------------------------------------------------------------------
# Crossover
# ---------------------------------------------------------------------------
class TestCrossover:
    """Test crossover point identification."""

    def test_crossover_at_tau(self, boro_rod):
        """Crossover should occur at τ."""
        xo = find_crossover(boro_rod)
        assert abs(xo.t_crossover - boro_rod.tau) < 1e-10

    def test_crossover_has_noise_floor(self, boro_rod):
        xo = find_crossover(boro_rod, noise_floor_db=20.0)
        assert xo.noise_floor_db == 20.0


# ---------------------------------------------------------------------------
# Gain table
# ---------------------------------------------------------------------------
class TestGainTable:
    """Test gain table generation."""

    def test_returns_expected_length(self, boro_rod):
        table = cw_gain_table(boro_rod)
        assert len(table) == 4  # default: [τ, 1s, 10s, 60s]

    def test_gain_at_tau_is_zero(self, boro_rod):
        """At T_int = τ, gain should be ~0 dB."""
        table = cw_gain_table(boro_rod)
        assert abs(table[0]["gain_db"]) < 0.5

    def test_gains_increase_monotonically(self, boro_rod):
        """Longer integration → more gain."""
        table = cw_gain_table(boro_rod)
        for i in range(len(table) - 1):
            assert table[i + 1]["gain_db"] >= table[i]["gain_db"] - 0.01

    def test_1s_gain_positive(self, boro_rod):
        """At 1s, CW should have significant gain over 180ms impulse."""
        table = cw_gain_table(boro_rod)
        # τ ≈ 0.18s, so 1s is ~5.6τ, gain ≈ 10·log10(5.6) ≈ 7.5 dB
        row_1s = table[1]
        assert row_1s["gain_db"] > 5.0
        assert row_1s["gain_db"] < 15.0

    def test_60s_gain_large(self, boro_rod):
        """At 60s, CW gain should be > 20 dB."""
        table = cw_gain_table(boro_rod)
        row_60s = table[3]
        assert row_60s["gain_db"] > 20.0

    def test_custom_times(self, boro_rod):
        table = cw_gain_table(boro_rod, integration_times=[0.5, 2.0, 30.0])
        assert len(table) == 3


# ---------------------------------------------------------------------------
# Two-phase readout
# ---------------------------------------------------------------------------
class TestTwoPhaseReadout:
    """Test two-phase array readout model."""

    def test_phase1_time_is_tau(self, boro_rod):
        result = two_phase_readout(boro_rod)
        assert abs(result.t_phase1 - boro_rod.tau) < 1e-10

    def test_total_time(self, boro_rod):
        t_cw = 5.0
        result = two_phase_readout(boro_rod, t_cw=t_cw)
        expected = boro_rod.tau + t_cw
        assert abs(result.t_total - expected) < 1e-10

    def test_phase2_snr_exceeds_phase1(self, boro_rod):
        """CW precision read should exceed impulse coarse read."""
        result = two_phase_readout(boro_rod, t_cw=10.0)
        assert result.snr_phase2_db > result.snr_phase1_db

    def test_gain_positive(self, boro_rod):
        """Two-phase should always show positive gain for t_cw > τ."""
        result = two_phase_readout(boro_rod, t_cw=10.0)
        assert result.gain_vs_impulse_db > 0

    def test_energy_phase2_exceeds_phase1(self, boro_rod):
        """Phase 2 (sustained CW) should cost more energy than Phase 1."""
        result = two_phase_readout(boro_rod, t_cw=10.0)
        assert result.energy_phase2 > result.energy_phase1

    def test_mems_scale(self, mems_rod):
        """Two-phase should work at MEMS scale too."""
        result = two_phase_readout(mems_rod, t_cw=1.0)
        assert result.snr_phase1_db > 0
        assert result.snr_phase2_db > 0
        # MEMS τ ≈ 1.2 ms, so t_cw = 1s ≈ 833τ → big gain
        assert result.gain_vs_impulse_db > 20


# ---------------------------------------------------------------------------
# Noise environment comparison
# ---------------------------------------------------------------------------
class TestNoiseComparison:
    """Test noise environment sweep."""

    def test_default_returns_5_environments(self, boro_rod):
        rows = noise_environment_comparison(boro_rod)
        assert len(rows) == 5

    def test_all_gains_positive(self, boro_rod):
        """CW should beat impulse in all environments at 10s integration."""
        rows = noise_environment_comparison(boro_rod, t_int=10.0)
        for row in rows:
            assert row["gain_db"] > 0

    def test_gain_same_across_noise(self, boro_rod):
        """CW gain should be the same regardless of noise floor
        (both degrade equally, gain is ratio)."""
        rows = noise_environment_comparison(boro_rod, t_int=10.0)
        gains = [row["gain_db"] for row in rows]
        # All gains should be approximately equal
        assert max(gains) - min(gains) < 1.0

    def test_labels_present(self, boro_rod):
        rows = noise_environment_comparison(boro_rod)
        for row in rows:
            assert "label" in row
            assert len(row["label"]) > 0


# ---------------------------------------------------------------------------
# Full analysis runner
# ---------------------------------------------------------------------------
class TestFullAnalysis:
    """Test the comprehensive analysis runner."""

    def test_returns_all_keys(self):
        results = run_cw_readout_analysis()
        expected_keys = [
            "rod_params", "tau", "gain_table", "noise_comparison",
            "two_phase", "snr_curves", "crossovers"
        ]
        for key in expected_keys:
            assert key in results, f"Missing key: {key}"

    def test_tau_matches_rod(self):
        results = run_cw_readout_analysis()
        rod = results["rod_params"]
        assert abs(results["tau"] - rod.tau) < 1e-12

    def test_gain_table_populated(self):
        results = run_cw_readout_analysis()
        assert len(results["gain_table"]) > 0

    def test_snr_curves_for_three_environments(self):
        results = run_cw_readout_analysis()
        assert len(results["snr_curves"]) == 3

    def test_two_phase_populated(self):
        results = run_cw_readout_analysis()
        assert len(results["two_phase"]) == 5

    def test_crossovers_populated(self):
        results = run_cw_readout_analysis()
        assert len(results["crossovers"]) == 3


# ---------------------------------------------------------------------------
# Quantitative validation against paper values
# ---------------------------------------------------------------------------
class TestPaperValues:
    """Validate specific numerical claims from the paper/conversation."""

    def test_macro_rod_f0(self):
        """150mm boro rod: f₀ ≈ 17,717 Hz."""
        rod = GlassRodParams(L=0.150)
        assert abs(rod.f0 - 17716.7) < 1.0

    def test_macro_rod_tau(self):
        """τ = Q/(πf₀) = 10000/(π×17717) ≈ 0.1797 s ≈ 180 ms."""
        rod = GlassRodParams(L=0.150)
        assert abs(rod.tau - 0.1797) < 0.005

    def test_mems_rod_f0(self):
        """1mm boro rod: f₀ ≈ 2.66 MHz."""
        rod = GlassRodParams(L=1e-3, d=40e-6)
        assert abs(rod.f0 - 2.6575e6) < 1e3

    def test_mems_rod_tau(self):
        """1mm MEMS rod: τ ≈ 1.2 ms."""
        rod = GlassRodParams(L=1e-3, d=40e-6)
        assert abs(rod.tau - 1.197e-3) < 0.1e-3

    def test_cw_gain_1s_boro(self):
        """At 1s integration on macro rod: gain ≈ 7-8 dB."""
        rod = GlassRodParams(L=0.150)
        table = cw_gain_table(rod, integration_times=[1.0])
        gain = table[0]["gain_db"]
        assert 5.0 < gain < 12.0

    def test_cw_gain_10s_boro(self):
        """At 10s: gain ≈ 17-18 dB."""
        rod = GlassRodParams(L=0.150)
        table = cw_gain_table(rod, integration_times=[10.0])
        gain = table[0]["gain_db"]
        assert 14.0 < gain < 20.0

    def test_cw_gain_60s_boro(self):
        """At 60s: gain ≈ 25 dB."""
        rod = GlassRodParams(L=0.150)
        table = cw_gain_table(rod, integration_times=[60.0])
        gain = table[0]["gain_db"]
        assert 22.0 < gain < 30.0

    def test_silica_tau(self):
        """Fused silica at 150mm: τ = 100000/(π×19900) ≈ 1.6 s."""
        rod = GlassRodParams(
            L=0.150, v_bar=V_BAR_SILICA, Q=Q_MAT_SILICA
        )
        assert rod.tau > 1.0  # > 1 second
        assert rod.tau < 3.0  # < 3 seconds
