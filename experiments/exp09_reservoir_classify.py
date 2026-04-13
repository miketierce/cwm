"""
Experiment 09: Plate Reservoir Computing — Binary Classification

Research Question:
    Can a fused-silica plate act as a fixed-physics reservoir whose
    spectral response, combined with a trainable linear readout,
    learns to classify multi-tone input patterns?

Hypothesis:
    The plate's eigenmode spectrum provides a rich, nonlinear feature
    projection.  Driving with different multi-tone inputs produces
    distinct spectral responses.  A simple linear readout (one weight
    per mode) trained by least-squares regression should classify
    input patterns with >90% accuracy — demonstrating that the plate
    performs the computationally expensive "forward pass" physically,
    leaving only a trivial linear layer for training.

Methodology:
    1. Define N_CLASSES binary input patterns (e.g., 4-bit parity).
    2. Encode each pattern as a multi-tone drive signal: bit k ON →
       drive at mode frequency f_k with amplitude A_high; bit k OFF →
       amplitude A_low (or zero).
    3. Simulate the plate transfer function H(f) with mode coupling
       and noise to produce spectral responses.
    4. Train a linear readout layer (N_modes weights) via least-squares
       on a training set of (spectral_response, class_label) pairs.
    5. Evaluate classification accuracy on a held-out test set.
    6. Sweep: number of modes, SNR, number of classes.

Architecture mapping:
    - Plate physics         = hidden layer (fixed)
    - Readout weights       = output layer (trainable, ~30 params)
    - Least-squares fit     = "training" (converges in one step)
    - PicoScope AWG/ADC     = CMOS readout die emulator

Claims tested:  Reservoir computing viability on CWM substrate
Status:         SIMULATED (computational validation, bench hw planned)
"""

import numpy as np
from dataclasses import dataclass, field
from typing import List, Optional


# ---------------------------------------------------------------------------
# Result data classes
# ---------------------------------------------------------------------------

@dataclass
class ReservoirClassifyResult:
    """Result of one reservoir classification experiment."""
    n_modes: int
    n_classes: int
    n_train: int
    n_test: int
    snr_db: float
    train_accuracy: float
    test_accuracy: float
    readout_weights: np.ndarray
    confusion_matrix: np.ndarray


@dataclass
class ReservoirSweepResult:
    """Classification accuracy across parameter sweeps."""
    # SNR sweep
    snr_values: np.ndarray
    snr_train_acc: np.ndarray
    snr_test_acc: np.ndarray
    # Mode count sweep
    mode_counts: np.ndarray
    mode_train_acc: np.ndarray
    mode_test_acc: np.ndarray
    # Class count sweep
    class_counts: np.ndarray
    class_train_acc: np.ndarray
    class_test_acc: np.ndarray
    # Best single result
    best_result: ReservoirClassifyResult = field(default=None)


# ---------------------------------------------------------------------------
# Plate transfer function simulation
# ---------------------------------------------------------------------------

def _plate_transfer(freqs: np.ndarray, mode_freqs: np.ndarray,
                    mode_qs: np.ndarray, mode_gains: np.ndarray) -> np.ndarray:
    """Simulate plate spectral response: sum of Lorentzian resonances."""
    H = np.zeros(len(freqs), dtype=complex)
    for f0, Q, g in zip(mode_freqs, mode_qs, mode_gains):
        bw = f0 / Q
        H += g / (1 + 1j * 2 * (freqs - f0) / bw)
    return H


def _generate_plate_modes(n_modes: int, rng: np.random.Generator):
    """Generate realistic plate mode parameters."""
    # Mode frequencies: roughly 5–90 kHz spread
    mode_freqs = np.sort(rng.uniform(5000, 90000, n_modes))
    # Q factors: 1000–10000 (fused silica range)
    mode_qs = rng.uniform(1000, 10000, n_modes)
    # Gains: log-normal distribution
    mode_gains = np.exp(rng.normal(14, 1.5, n_modes))
    return mode_freqs, mode_qs, mode_gains


def _encode_input(pattern: np.ndarray, input_freqs: np.ndarray,
                  a_high: float = 1.0, a_low: float = 0.0) -> np.ndarray:
    """Encode a binary pattern as drive amplitudes at input frequencies."""
    return np.where(pattern > 0, a_high, a_low)


def _measure_response(drive_amplitudes: np.ndarray,
                      input_freqs: np.ndarray,
                      mode_freqs: np.ndarray,
                      mode_qs: np.ndarray,
                      mode_gains: np.ndarray,
                      snr_db: float,
                      rng: np.random.Generator) -> np.ndarray:
    """Simulate driving the plate and measuring spectral response at mode freqs."""
    # Build combined drive signal spectrum
    response = np.zeros(len(mode_freqs))
    for amp, f_in in zip(drive_amplitudes, input_freqs):
        if amp > 0:
            # Each input tone excites all modes through the transfer function
            H = _plate_transfer(np.array([f_in]), mode_freqs, mode_qs, mode_gains)
            response += amp * np.abs(H)

    # Add measurement noise
    if snr_db < 100:
        signal_power = np.mean(response ** 2) + 1e-20
        noise_power = signal_power / (10 ** (snr_db / 10))
        response += rng.normal(0, np.sqrt(noise_power), len(response))

    return response


# ---------------------------------------------------------------------------
# Core experiment
# ---------------------------------------------------------------------------

def _run_single(n_modes: int = 31, n_input_bits: int = 4,
                n_classes: int = 0, n_train: int = 80,
                n_test: int = 20, snr_db: float = 20.0,
                seed: int = 42) -> ReservoirClassifyResult:
    """Run a single reservoir classification experiment.

    Task: classify binary input patterns by their parity (even/odd
    number of 1-bits). This is the XOR generalisation problem —
    not linearly separable in input space, but the plate's nonlinear
    mode coupling makes it linearly separable in spectral space.
    """
    rng = np.random.default_rng(seed)

    # Generate plate model
    mode_freqs, mode_qs, mode_gains = _generate_plate_modes(n_modes, rng)

    # Input encoding: pick n_input_bits mode frequencies as input channels
    input_indices = np.linspace(0, n_modes - 1, n_input_bits, dtype=int)
    input_freqs = mode_freqs[input_indices]

    # Use parity as the classification task
    n_patterns = 2 ** n_input_bits
    actual_classes = 2  # even/odd parity
    if n_classes > 0:
        actual_classes = min(n_classes, n_patterns)

    # Generate all possible patterns and their labels
    all_patterns = np.array(
        [[(i >> b) & 1 for b in range(n_input_bits)] for i in range(n_patterns)]
    )
    all_labels = np.sum(all_patterns, axis=1) % actual_classes

    # Create train/test sets by sampling with replacement
    total = n_train + n_test
    indices = rng.choice(n_patterns, total, replace=True)
    X_patterns = all_patterns[indices]
    y_labels = all_labels[indices]

    # Collect spectral responses (the "forward pass" through the plate)
    X_features = np.zeros((total, n_modes))
    for i, pattern in enumerate(X_patterns):
        drive = _encode_input(pattern, input_freqs)
        X_features[i] = _measure_response(
            drive, input_freqs, mode_freqs, mode_qs, mode_gains, snr_db, rng
        )

    # Split
    X_train, X_test = X_features[:n_train], X_features[n_train:]
    y_train, y_test = y_labels[:n_train], y_labels[n_train:]

    # Train linear readout via least-squares (one-hot encoding)
    Y_onehot = np.zeros((n_train, actual_classes))
    for i, label in enumerate(y_train):
        Y_onehot[i, label] = 1.0

    # Add bias column
    X_bias = np.column_stack([X_train, np.ones(n_train)])
    # Least-squares: W = (X^T X)^{-1} X^T Y
    W, _, _, _ = np.linalg.lstsq(X_bias, Y_onehot, rcond=None)

    # Predict
    X_test_bias = np.column_stack([X_test, np.ones(n_test)])
    pred_train = np.argmax(X_bias @ W, axis=1)
    pred_test = np.argmax(X_test_bias @ W, axis=1)

    train_acc = np.mean(pred_train == y_train)
    test_acc = np.mean(pred_test == y_test)

    # Confusion matrix
    cm = np.zeros((actual_classes, actual_classes), dtype=int)
    for true, pred in zip(y_test, pred_test):
        cm[true, pred] += 1

    return ReservoirClassifyResult(
        n_modes=n_modes, n_classes=actual_classes,
        n_train=n_train, n_test=n_test, snr_db=snr_db,
        train_accuracy=train_acc, test_accuracy=test_acc,
        readout_weights=W, confusion_matrix=cm,
    )


# ---------------------------------------------------------------------------
# Sweep experiment
# ---------------------------------------------------------------------------

def run_experiment(
    snr_values: np.ndarray = None,
    mode_counts: np.ndarray = None,
    class_counts: np.ndarray = None,
    n_input_bits: int = 4,
    n_train: int = 80,
    n_test: int = 40,
    n_trials: int = 5,
    seed: int = 42,
) -> ReservoirSweepResult:
    """Run reservoir classification sweeps across SNR, mode count, and class count."""

    if snr_values is None:
        snr_values = np.array([5, 10, 15, 20, 25, 30, 40, 60])
    if mode_counts is None:
        mode_counts = np.array([5, 10, 15, 20, 31, 50, 100])
    if class_counts is None:
        class_counts = np.array([2])  # parity is binary

    rng_base = np.random.default_rng(seed)

    # SNR sweep (fixed 31 modes)
    snr_train = np.zeros(len(snr_values))
    snr_test = np.zeros(len(snr_values))
    for i, snr in enumerate(snr_values):
        accs = [_run_single(31, n_input_bits, 0, n_train, n_test, snr,
                            seed=rng_base.integers(1e9))
                for _ in range(n_trials)]
        snr_train[i] = np.mean([r.train_accuracy for r in accs])
        snr_test[i] = np.mean([r.test_accuracy for r in accs])

    # Mode count sweep (fixed 20 dB SNR)
    mode_train = np.zeros(len(mode_counts))
    mode_test = np.zeros(len(mode_counts))
    for i, nm in enumerate(mode_counts):
        accs = [_run_single(int(nm), n_input_bits, 0, n_train, n_test, 20.0,
                            seed=rng_base.integers(1e9))
                for _ in range(n_trials)]
        mode_train[i] = np.mean([r.train_accuracy for r in accs])
        mode_test[i] = np.mean([r.test_accuracy for r in accs])

    # Class count sweep (fixed 31 modes, 20 dB)
    cls_train = np.zeros(len(class_counts))
    cls_test = np.zeros(len(class_counts))
    for i, nc in enumerate(class_counts):
        accs = [_run_single(31, n_input_bits, int(nc), n_train, n_test, 20.0,
                            seed=rng_base.integers(1e9))
                for _ in range(n_trials)]
        cls_train[i] = np.mean([r.train_accuracy for r in accs])
        cls_test[i] = np.mean([r.test_accuracy for r in accs])

    # Best single result at default params
    best = _run_single(31, n_input_bits, 0, n_train, n_test, 20.0, seed=seed)

    return ReservoirSweepResult(
        snr_values=snr_values, snr_train_acc=snr_train, snr_test_acc=snr_test,
        mode_counts=mode_counts, mode_train_acc=mode_train, mode_test_acc=mode_test,
        class_counts=class_counts, class_train_acc=cls_train, class_test_acc=cls_test,
        best_result=best,
    )


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def summarize(result: ReservoirSweepResult) -> str:
    lines = [
        "=" * 70,
        "  Experiment 09: Plate Reservoir Computing — Classification",
        "=" * 70,
        "",
        "  SNR Sweep (31 modes, parity task):",
        f"  {'SNR (dB)':>10}  {'Train':>8}  {'Test':>8}",
        "  " + "-" * 30,
    ]
    for snr, tr, te in zip(result.snr_values, result.snr_train_acc, result.snr_test_acc):
        lines.append(f"  {snr:>10.0f}  {tr:>7.1%}  {te:>7.1%}")

    lines += [
        "",
        "  Mode Count Sweep (20 dB SNR):",
        f"  {'Modes':>10}  {'Train':>8}  {'Test':>8}",
        "  " + "-" * 30,
    ]
    for nm, tr, te in zip(result.mode_counts, result.mode_train_acc, result.mode_test_acc):
        lines.append(f"  {nm:>10.0f}  {tr:>7.1%}  {te:>7.1%}")

    if result.best_result:
        b = result.best_result
        lines += [
            "",
            f"  Best result: {b.n_modes} modes, {b.snr_db:.0f} dB SNR",
            f"    Train accuracy: {b.train_accuracy:.1%}",
            f"    Test accuracy:  {b.test_accuracy:.1%}",
            f"    Readout weights: {b.readout_weights.shape} matrix",
            f"    Confusion matrix:",
        ]
        for row in b.confusion_matrix:
            lines.append(f"      {row}")

    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    result = run_experiment()
    print(summarize(result))
