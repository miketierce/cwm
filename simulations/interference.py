"""
Multi-Mode Interference Simulation for WCFOMA

Models the superposition, storage, and retrieval of multiple resonant
eigenmodes within a single cavity — the core computation mechanism of
the WCFOMA architecture (paper Section 3.3).

Capabilities:
  - Encode N data values as mode amplitudes + phases
  - Simulate time evolution of superposition
  - Readout via projection (inner product / matched filter)
  - Associative recall via partial-pattern interference
  - Measure retrieval fidelity under noise and damping

This module directly addresses the Phase 1 question: "Can multiple modes
actually coexist without nonlinear coupling?" (Open Question #2).
"""

import numpy as np
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass
class ModeEncoding:
    """A data vector encoded as mode amplitudes and phases."""
    amplitudes: np.ndarray        # |a_n| for each mode
    phases: np.ndarray            # φ_n for each mode (radians)
    frequencies: np.ndarray       # f_n for each mode (Hz)
    damping_rates: np.ndarray     # η_n for each mode (1/s)
    label: str = ""

    @property
    def n_modes(self) -> int:
        return len(self.amplitudes)

    def complex_amplitudes(self) -> np.ndarray:
        """Return a_n · exp(iφ_n)."""
        return self.amplitudes * np.exp(1j * self.phases)


@dataclass
class InterferenceResult:
    """Result of a multi-mode interference simulation."""
    time: np.ndarray
    signal: np.ndarray            # Total field u(t)
    mode_signals: np.ndarray      # Individual mode contributions (n_modes × n_time)
    encoding: ModeEncoding
    readout_fidelity: float = 0.0
    retrieved_amplitudes: Optional[np.ndarray] = None
    retrieved_phases: Optional[np.ndarray] = None
    snr_db: float = 0.0
    label: str = ""


# ---------------------------------------------------------------------------
# Mode spectrum generation
# ---------------------------------------------------------------------------
def generate_mode_spectrum(
    n_modes: int = 10,
    f_fundamental: float = 17000.0,
    eta_base: float = 50.0,
    Q: float = 500.0,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Generate frequency and damping arrays for a 1D cavity.

    f_n = n · f_fundamental
    η_n = π · f_n / Q   (from Q = ω / (2η) → η = πf/Q)

    Returns
    -------
    frequencies : ndarray of shape (n_modes,)
    damping_rates : ndarray of shape (n_modes,)
    """
    ns = np.arange(1, n_modes + 1)
    frequencies = ns * f_fundamental
    damping_rates = np.pi * frequencies / Q
    return frequencies, damping_rates


# ---------------------------------------------------------------------------
# Encoding / writing
# ---------------------------------------------------------------------------
def encode_data(
    data: np.ndarray,
    n_modes: int = None,
    f_fundamental: float = 17000.0,
    Q: float = 500.0,
    encoding: str = "amplitude",
    label: str = "",
) -> ModeEncoding:
    """
    Encode a data vector into mode amplitudes/phases.

    Parameters
    ----------
    data : ndarray
        Data to encode. Length determines number of modes used.
    n_modes : int, optional
        Number of modes (default = len(data)).
    f_fundamental : float
        Fundamental frequency (Hz).
    Q : float
        Quality factor (sets damping).
    encoding : str
        'amplitude' — data → amplitudes, phases = 0
        'phase'     — amplitudes = 1, data → phases (scaled to [0, 2π))
        'complex'   — data[:N] → amplitudes, data[N:] → phases

    Returns
    -------
    ModeEncoding
    """
    if n_modes is None:
        n_modes = len(data)

    frequencies, damping = generate_mode_spectrum(n_modes, f_fundamental, Q=Q)

    if encoding == "amplitude":
        amplitudes = np.abs(data[:n_modes])
        phases = np.zeros(n_modes)
    elif encoding == "phase":
        amplitudes = np.ones(n_modes)
        phases = np.array(data[:n_modes]) * 2 * np.pi / np.max(np.abs(data[:n_modes]) + 1e-30)
    elif encoding == "complex":
        half = n_modes
        amplitudes = np.abs(data[:half])
        phases = np.angle(data[:half]) if np.iscomplexobj(data) else np.zeros(half)
    else:
        raise ValueError(f"Unknown encoding: {encoding}")

    return ModeEncoding(
        amplitudes=amplitudes,
        phases=phases,
        frequencies=frequencies,
        damping_rates=damping,
        label=label,
    )


# ---------------------------------------------------------------------------
# Time evolution
# ---------------------------------------------------------------------------
def evolve_superposition(
    encoding: ModeEncoding,
    t_end: float = 0.01,
    n_points: int = 10000,
    noise_amplitude: float = 0.0,
) -> InterferenceResult:
    """
    Evolve the multi-mode superposition in time.

    u(t) = Σ_n  a_n · exp(-η_n·t) · cos(2π f_n t + φ_n) + noise

    Parameters
    ----------
    encoding : ModeEncoding
        Encoded data.
    t_end : float
        Simulation duration (s).
    n_points : int
        Number of time samples.
    noise_amplitude : float
        Gaussian noise std dev (0 = noiseless).

    Returns
    -------
    InterferenceResult
    """
    t = np.linspace(0, t_end, n_points)
    n_modes = encoding.n_modes

    mode_signals = np.zeros((n_modes, n_points))
    for n in range(n_modes):
        envelope = encoding.amplitudes[n] * np.exp(-encoding.damping_rates[n] * t)
        mode_signals[n] = envelope * np.cos(
            2 * np.pi * encoding.frequencies[n] * t + encoding.phases[n]
        )

    signal = np.sum(mode_signals, axis=0)

    if noise_amplitude > 0:
        signal += np.random.normal(0, noise_amplitude, n_points)

    return InterferenceResult(
        time=t,
        signal=signal,
        mode_signals=mode_signals,
        encoding=encoding,
    )


# ---------------------------------------------------------------------------
# Readout / decoding
# ---------------------------------------------------------------------------
def readout_modes(
    result: InterferenceResult,
    method: str = "matched_filter",
) -> InterferenceResult:
    """
    Extract mode amplitudes and phases from the time-domain signal.

    Parameters
    ----------
    result : InterferenceResult
        Evolved superposition.
    method : str
        'matched_filter' — project signal onto each mode's template
        'fft'            — FFT peak detection at known frequencies

    Returns
    -------
    InterferenceResult (updated with retrieved amplitudes/phases/fidelity)
    """
    t = result.time
    signal = result.signal
    encoding = result.encoding
    dt = t[1] - t[0]
    n_modes = encoding.n_modes

    retrieved_amp = np.zeros(n_modes)
    retrieved_phase = np.zeros(n_modes)

    if method == "matched_filter":
        for n in range(n_modes):
            # Template: undamped cosine + sine at mode frequency
            cos_template = np.cos(2 * np.pi * encoding.frequencies[n] * t)
            sin_template = np.sin(2 * np.pi * encoding.frequencies[n] * t)

            # Project
            c_coeff = 2.0 * np.mean(signal * cos_template)
            s_coeff = -2.0 * np.mean(signal * sin_template)

            retrieved_amp[n] = np.sqrt(c_coeff**2 + s_coeff**2)
            retrieved_phase[n] = np.arctan2(s_coeff, c_coeff)

    elif method == "fft":
        freqs_fft = np.fft.rfftfreq(len(t), dt)
        spectrum = np.fft.rfft(signal)
        for n in range(n_modes):
            idx = np.argmin(np.abs(freqs_fft - encoding.frequencies[n]))
            retrieved_amp[n] = 2.0 * np.abs(spectrum[idx]) / len(t)
            retrieved_phase[n] = np.angle(spectrum[idx])

    # Compute fidelity: normalized inner product of original and retrieved
    orig = encoding.complex_amplitudes()
    retr = retrieved_amp * np.exp(1j * retrieved_phase)

    # Normalize
    norm_orig = np.linalg.norm(orig)
    norm_retr = np.linalg.norm(retr)
    if norm_orig > 0 and norm_retr > 0:
        fidelity = np.abs(np.dot(orig.conj(), retr)) / (norm_orig * norm_retr)
    else:
        fidelity = 0.0

    # SNR
    signal_power = np.mean(signal**2)
    noise_power = np.mean((signal - np.sum(result.mode_signals, axis=0))**2)
    snr_db = 10 * np.log10(signal_power / (noise_power + 1e-30))

    result.retrieved_amplitudes = retrieved_amp
    result.retrieved_phases = retrieved_phase
    result.readout_fidelity = fidelity
    result.snr_db = snr_db
    return result


# ---------------------------------------------------------------------------
# Associative recall
# ---------------------------------------------------------------------------
def associative_recall(
    stored_patterns: List[ModeEncoding],
    query: np.ndarray,
    n_modes: int = 10,
    f_fundamental: float = 17000.0,
    Q: float = 500.0,
    noise: float = 0.0,
) -> Tuple[int, float, np.ndarray]:
    """
    Demonstrate associative recall via mode interference.

    Store multiple patterns, present a partial/noisy query, and determine
    which stored pattern has the highest overlap.

    Parameters
    ----------
    stored_patterns : list of ModeEncoding
        Previously stored data.
    query : ndarray
        Partial or noisy input pattern.
    n_modes : int
        Number of modes per pattern.
    f_fundamental : float
        Fundamental frequency.
    Q : float
        Quality factor.
    noise : float
        Noise level on readout.

    Returns
    -------
    best_match_idx : int
        Index of best-matching stored pattern.
    best_overlap : float
        Overlap score (0-1).
    overlaps : ndarray
        All overlap scores.
    """
    query_enc = encode_data(query, n_modes=n_modes, f_fundamental=f_fundamental, Q=Q)
    q_vec = query_enc.complex_amplitudes()
    q_norm = np.linalg.norm(q_vec)
    if q_norm == 0:
        return 0, 0.0, np.zeros(len(stored_patterns))

    overlaps = np.zeros(len(stored_patterns))
    for i, pattern in enumerate(stored_patterns):
        p_vec = pattern.complex_amplitudes()
        p_norm = np.linalg.norm(p_vec)
        if p_norm > 0:
            overlaps[i] = np.abs(np.dot(p_vec.conj(), q_vec)) / (p_norm * q_norm)

    best_idx = np.argmax(overlaps)
    return best_idx, overlaps[best_idx], overlaps


# ---------------------------------------------------------------------------
# Full write-read-verify cycle
# ---------------------------------------------------------------------------
def write_read_verify(
    data: np.ndarray,
    n_modes: int = None,
    Q: float = 500.0,
    t_hold: float = 0.001,
    noise: float = 0.0,
    encoding: str = "amplitude",
) -> dict:
    """
    Complete write → hold → read → verify cycle.

    Parameters
    ----------
    data : ndarray
        Data vector to store.
    n_modes : int
        Number of modes.
    Q : float
        Quality factor.
    t_hold : float
        Hold time before readout (s).
    noise : float
        Readout noise level.
    encoding : str
        Encoding strategy.

    Returns
    -------
    dict with keys: encoding, result, fidelity, snr_db
    """
    enc = encode_data(data, n_modes=n_modes, Q=Q, encoding=encoding, label="write")
    result = evolve_superposition(enc, t_end=t_hold, noise_amplitude=noise)
    result = readout_modes(result, method="matched_filter")

    return {
        "encoding": enc,
        "result": result,
        "fidelity": result.readout_fidelity,
        "snr_db": result.snr_db,
        "n_modes": enc.n_modes,
        "t_hold": t_hold,
        "Q": Q,
        "noise": noise,
    }


def fidelity_sweep(
    data: np.ndarray,
    Q_values: np.ndarray = None,
    hold_times: np.ndarray = None,
    noise_levels: np.ndarray = None,
) -> dict:
    """
    Sweep parameters and measure retrieval fidelity.

    Returns dict of sweep_name → (param_values, fidelity_values).
    """
    if Q_values is None:
        Q_values = np.logspace(1, 4, 15)
    if hold_times is None:
        hold_times = np.logspace(-5, -1, 15)
    if noise_levels is None:
        noise_levels = np.logspace(-4, 0, 15)

    results = {}

    # Q sweep
    fid_Q = []
    for Q in Q_values:
        r = write_read_verify(data, Q=Q, t_hold=1e-4, noise=0.0)
        fid_Q.append(r["fidelity"])
    results["Q"] = (Q_values, np.array(fid_Q))

    # Hold time sweep
    fid_t = []
    for th in hold_times:
        r = write_read_verify(data, Q=500, t_hold=th, noise=0.0)
        fid_t.append(r["fidelity"])
    results["hold_time"] = (hold_times, np.array(fid_t))

    # Noise sweep
    fid_n = []
    for ns in noise_levels:
        r = write_read_verify(data, Q=500, t_hold=1e-4, noise=ns)
        fid_n.append(r["fidelity"])
    results["noise"] = (noise_levels, np.array(fid_n))

    return results
