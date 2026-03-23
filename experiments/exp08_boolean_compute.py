"""
Experiment 08: In-Situ Boolean Computation via Mode Superposition

Research Question:
    Can Boolean operations (AND, OR, XOR) be computed in a single
    acoustic cycle by superposing two patterns' spectral signatures
    and applying amplitude thresholds?

Hypothesis:
    Per paper §11.2, when two binary patterns A and B are encoded
    as mode amplitudes and superposed, the combined amplitude at
    each mode falls into three clusters:
        - Low  (both bits 0):  a_low + a_low
        - Mid  (one bit 1):    a_high + a_low  or  a_low + a_high
        - High (both bits 1):  a_high + a_high

    AND = high cluster only,  OR = mid + high,  XOR = mid only.
    This requires zero hardware changes — just threshold firmware.

Methodology:
    1. Define binary patterns as mode-amplitude vectors (high/low per mode).
    2. Superpose two patterns: S = A + B.
    3. Apply three threshold schemes to extract AND, OR, XOR.
    4. Compare extracted bits to truth-table results.
    5. Measure fidelity (fraction of correct bits) across:
       a) Varying amplitude contrast ratios (high/low from 2:1 to 10:1).
       b) Additive noise levels (simulating thermal / readout noise).
       c) Number of modes (N = 10 to 100).
    6. Test chained computation: A AND B, then result XOR C.

Claims tested:  Section 11.2 — ">90% fidelity for AND/OR/XOR"
Status:          SIMULATED (computational validation)
"""

import numpy as np
from dataclasses import dataclass, field
from typing import List, Optional, Dict


# ---------------------------------------------------------------------------
# Result data classes
# ---------------------------------------------------------------------------

@dataclass
class BooleanResult:
    """Result of a single Boolean operation via superposition."""
    operation: str                # "AND", "OR", "XOR"
    pattern_a: np.ndarray         # binary {0, 1}
    pattern_b: np.ndarray
    expected: np.ndarray          # truth-table result
    computed: np.ndarray          # threshold-extracted result
    fidelity: float               # fraction of matching bits
    combined_amplitudes: np.ndarray  # raw superposition


@dataclass
class ContrastSweepResult:
    """Boolean fidelity vs amplitude contrast ratio."""
    contrast_ratios: np.ndarray
    and_fidelity: np.ndarray
    or_fidelity: np.ndarray
    xor_fidelity: np.ndarray


@dataclass
class NoiseSweepResult:
    """Boolean fidelity vs noise level."""
    noise_levels: np.ndarray
    and_fidelity: np.ndarray
    or_fidelity: np.ndarray
    xor_fidelity: np.ndarray


@dataclass
class ChainedResult:
    """Result of chained Boolean operations: (A op1 B) op2 C."""
    op1: str
    op2: str
    expected: np.ndarray
    computed: np.ndarray
    fidelity: float


@dataclass
class BooleanComputeExperiment:
    """Full results from the Boolean computation experiment."""
    n_modes: int
    # Single operation demonstrations
    demo_results: Dict[str, BooleanResult]   # AND, OR, XOR
    # Contrast ratio sweep
    contrast_sweep: ContrastSweepResult
    # Noise robustness
    noise_sweep: NoiseSweepResult
    # Chained operations
    chained_results: List[ChainedResult]
    # Summary metrics
    mean_fidelity_clean: float               # average across ops, no noise
    min_contrast_for_90pct: float            # minimum contrast for ≥90% fidelity


# ---------------------------------------------------------------------------
# Core Boolean computation
# ---------------------------------------------------------------------------

def _encode_binary(pattern: np.ndarray, a_high: float, a_low: float) -> np.ndarray:
    """Encode a binary {0,1} pattern as mode amplitudes."""
    return np.where(pattern > 0.5, a_high, a_low)


def _threshold_and(combined: np.ndarray, a_high: float, a_low: float) -> np.ndarray:
    """Extract AND: only the high cluster (both bits = 1).

    Combined amplitudes fall into three levels:
        both-0:  2*a_low
        one-1:   a_high + a_low
        both-1:  2*a_high
    AND selects only the both-1 cluster.
    """
    both_one = 2 * a_high
    one_one = a_high + a_low
    # Threshold halfway between one-1 and both-1
    threshold = (one_one + both_one) / 2
    return np.where(combined > threshold, 1.0, 0.0)


def _threshold_or(combined: np.ndarray, a_high: float, a_low: float) -> np.ndarray:
    """Extract OR: mid + high clusters (at least one bit = 1).

    OR selects everything above the both-0 cluster.
    """
    both_zero = 2 * a_low
    one_one = a_high + a_low
    # Threshold halfway between both-0 and one-1
    threshold = (both_zero + one_one) / 2
    return np.where(combined > threshold, 1.0, 0.0)


def _threshold_xor(combined: np.ndarray, a_high: float, a_low: float) -> np.ndarray:
    """Extract XOR: mid cluster only (exactly one bit = 1).

    XOR selects the one-1 cluster but not both-0 or both-1.
    """
    both_zero = 2 * a_low
    one_one = a_high + a_low
    both_one = 2 * a_high
    # Lower bound: halfway between both-0 and one-1
    lower = (both_zero + one_one) / 2
    # Upper bound: halfway between one-1 and both-1
    upper = (one_one + both_one) / 2
    return np.where((combined > lower) & (combined < upper), 1.0, 0.0)


def compute_boolean(
    pattern_a: np.ndarray,
    pattern_b: np.ndarray,
    operation: str,
    a_high: float = 1.0,
    a_low: float = 0.2,
    noise_sigma: float = 0.0,
    rng: Optional[np.random.RandomState] = None,
) -> BooleanResult:
    """
    Compute a Boolean operation via mode superposition and thresholding.

    Parameters
    ----------
    pattern_a, pattern_b : ndarray of {0, 1}
        Binary input patterns.
    operation : str
        "AND", "OR", or "XOR".
    a_high, a_low : float
        Amplitude levels for 1-bits and 0-bits.
    noise_sigma : float
        Standard deviation of additive Gaussian noise.
    """
    if rng is None:
        rng = np.random.RandomState(0)

    # Truth table
    a = pattern_a.astype(float)
    b = pattern_b.astype(float)
    if operation == "AND":
        expected = (a * b).astype(float)
    elif operation == "OR":
        expected = np.clip(a + b, 0, 1).astype(float)
    elif operation == "XOR":
        expected = np.abs(a - b).astype(float)
    else:
        raise ValueError(f"Unknown operation: {operation}")

    # Encode as amplitudes and superpose
    amp_a = _encode_binary(a, a_high, a_low)
    amp_b = _encode_binary(b, a_high, a_low)
    combined = amp_a + amp_b

    # Add noise
    if noise_sigma > 0:
        combined = combined + rng.normal(0, noise_sigma, size=len(combined))

    # Threshold to extract result
    if operation == "AND":
        computed = _threshold_and(combined, a_high, a_low)
    elif operation == "OR":
        computed = _threshold_or(combined, a_high, a_low)
    else:
        computed = _threshold_xor(combined, a_high, a_low)

    fidelity = float(np.mean(computed == expected))

    return BooleanResult(
        operation=operation,
        pattern_a=a,
        pattern_b=b,
        expected=expected,
        computed=computed,
        fidelity=fidelity,
        combined_amplitudes=combined,
    )


# ---------------------------------------------------------------------------
# Main experiment runner
# ---------------------------------------------------------------------------

def run_experiment(
    n_modes: int = 50,
    contrast_ratios: np.ndarray = None,
    noise_levels: np.ndarray = None,
    n_trials: int = 40,
) -> BooleanComputeExperiment:
    """
    Run the full Boolean computation experiment.

    Phase 1: Demonstrate AND/OR/XOR on a single pair of patterns.
    Phase 2: Sweep contrast ratio (a_high/a_low) to find threshold.
    Phase 3: Sweep noise level for robustness.
    Phase 4: Test chained operations.
    """
    if contrast_ratios is None:
        contrast_ratios = np.array([1.5, 2.0, 3.0, 4.0, 5.0, 7.0, 10.0])
    if noise_levels is None:
        noise_levels = np.array([0.0, 0.01, 0.02, 0.05, 0.1, 0.15, 0.2, 0.3])

    rng = np.random.RandomState(42)
    ops = ["AND", "OR", "XOR"]

    # --- Phase 1: Single demo with high contrast ---
    a_high, a_low = 1.0, 0.2
    demo_a = rng.randint(0, 2, size=n_modes).astype(float)
    demo_b = rng.randint(0, 2, size=n_modes).astype(float)

    demo_results = {}
    for op in ops:
        demo_results[op] = compute_boolean(demo_a, demo_b, op,
                                           a_high=a_high, a_low=a_low)

    # --- Phase 2: Contrast ratio sweep ---
    and_fid = np.zeros(len(contrast_ratios))
    or_fid = np.zeros(len(contrast_ratios))
    xor_fid = np.zeros(len(contrast_ratios))

    for ic, ratio in enumerate(contrast_ratios):
        al = 0.2
        ah = al * ratio
        fids = {op: [] for op in ops}
        for trial in range(n_trials):
            trial_rng = np.random.RandomState(rng.randint(100000))
            pa = trial_rng.randint(0, 2, size=n_modes).astype(float)
            pb = trial_rng.randint(0, 2, size=n_modes).astype(float)
            for op in ops:
                r = compute_boolean(pa, pb, op, a_high=ah, a_low=al)
                fids[op].append(r.fidelity)
        and_fid[ic] = np.mean(fids["AND"])
        or_fid[ic] = np.mean(fids["OR"])
        xor_fid[ic] = np.mean(fids["XOR"])

    contrast_sweep = ContrastSweepResult(
        contrast_ratios=contrast_ratios,
        and_fidelity=and_fid,
        or_fidelity=or_fid,
        xor_fidelity=xor_fid,
    )

    # Min contrast for ≥90% fidelity (all three ops)
    min_fid = np.minimum(np.minimum(and_fid, or_fid), xor_fid)
    above_90 = np.where(min_fid >= 0.9)[0]
    min_contrast = float(contrast_ratios[above_90[0]]) if len(above_90) > 0 else float("inf")

    # --- Phase 3: Noise sweep (fixed contrast = 5:1) ---
    ah_noise, al_noise = 1.0, 0.2
    and_nfid = np.zeros(len(noise_levels))
    or_nfid = np.zeros(len(noise_levels))
    xor_nfid = np.zeros(len(noise_levels))

    for inl, noise in enumerate(noise_levels):
        fids = {op: [] for op in ops}
        for trial in range(n_trials):
            trial_rng = np.random.RandomState(rng.randint(100000))
            pa = trial_rng.randint(0, 2, size=n_modes).astype(float)
            pb = trial_rng.randint(0, 2, size=n_modes).astype(float)
            for op in ops:
                r = compute_boolean(pa, pb, op, a_high=ah_noise, a_low=al_noise,
                                    noise_sigma=noise, rng=trial_rng)
                fids[op].append(r.fidelity)
        and_nfid[inl] = np.mean(fids["AND"])
        or_nfid[inl] = np.mean(fids["OR"])
        xor_nfid[inl] = np.mean(fids["XOR"])

    noise_sweep = NoiseSweepResult(
        noise_levels=noise_levels,
        and_fidelity=and_nfid,
        or_fidelity=or_nfid,
        xor_fidelity=xor_nfid,
    )

    # --- Phase 4: Chained operations ---
    demo_c = rng.randint(0, 2, size=n_modes).astype(float)
    chains = [
        ("AND", "XOR"),   # (A AND B) XOR C
        ("OR", "AND"),    # (A OR B) AND C
        ("XOR", "OR"),    # (A XOR B) OR C
    ]
    chained_results = []
    for op1, op2 in chains:
        # First operation
        r1 = compute_boolean(demo_a, demo_b, op1, a_high=a_high, a_low=a_low)
        # Second operation uses first result
        r2 = compute_boolean(r1.expected, demo_c, op2, a_high=a_high, a_low=a_low)
        chained_results.append(ChainedResult(
            op1=op1, op2=op2,
            expected=r2.expected,
            computed=r2.computed,
            fidelity=r2.fidelity,
        ))

    # Mean clean fidelity
    clean_fids = [demo_results[op].fidelity for op in ops]
    mean_clean = float(np.mean(clean_fids))

    return BooleanComputeExperiment(
        n_modes=n_modes,
        demo_results=demo_results,
        contrast_sweep=contrast_sweep,
        noise_sweep=noise_sweep,
        chained_results=chained_results,
        mean_fidelity_clean=mean_clean,
        min_contrast_for_90pct=min_contrast,
    )


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def summarize(result: BooleanComputeExperiment) -> str:
    """Generate text summary of Boolean computation experiment."""
    lines = [
        "=" * 65,
        "Experiment 08: In-Situ Boolean Computation via Mode Superposition",
        "=" * 65,
        "",
        f"Network size: {result.n_modes} modes",
        "",
        "--- Single-Operation Demo (5:1 contrast, no noise) ---",
        f"{'Operation':>10} | {'Fidelity':>10}",
        "-" * 24,
    ]
    for op in ["AND", "OR", "XOR"]:
        r = result.demo_results[op]
        lines.append(f"{op:>10} | {r.fidelity:10.1%}")

    lines.append(f"\nMean clean fidelity: {result.mean_fidelity_clean:.1%}")

    lines.append("\n--- Contrast Ratio Sweep ---")
    lines.append(f"{'Ratio':>8} | {'AND':>8} | {'OR':>8} | {'XOR':>8}")
    lines.append("-" * 40)
    cs = result.contrast_sweep
    for i, ratio in enumerate(cs.contrast_ratios):
        lines.append(
            f"{ratio:8.1f} | {cs.and_fidelity[i]:8.1%} | "
            f"{cs.or_fidelity[i]:8.1%} | {cs.xor_fidelity[i]:8.1%}"
        )
    lines.append(f"\nMin contrast for ≥90% all ops: {result.min_contrast_for_90pct:.1f}:1")

    lines.append("\n--- Noise Robustness (5:1 contrast) ---")
    lines.append(f"{'Noise σ':>8} | {'AND':>8} | {'OR':>8} | {'XOR':>8}")
    lines.append("-" * 40)
    ns = result.noise_sweep
    for i, noise in enumerate(ns.noise_levels):
        lines.append(
            f"{noise:8.3f} | {ns.and_fidelity[i]:8.1%} | "
            f"{ns.or_fidelity[i]:8.1%} | {ns.xor_fidelity[i]:8.1%}"
        )

    lines.append("\n--- Chained Operations ---")
    for cr in result.chained_results:
        lines.append(f"  (A {cr.op1} B) {cr.op2} C → fidelity: {cr.fidelity:.1%}")

    lines.append("\n" + "=" * 65)
    return "\n".join(lines)


if __name__ == "__main__":
    result = run_experiment()
    print(summarize(result))
