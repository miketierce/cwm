"""
Publication-Quality Plotting for WCFOMA Simulations

Generates figures matching the paper's claims and roadmap needs.
All plots use consistent styling suitable for arXiv / journal submission.
"""

import numpy as np
import matplotlib.pyplot as plt
import matplotlib as mpl
from pathlib import Path
from typing import Optional, Dict, List

# ---------------------------------------------------------------------------
# Style configuration
# ---------------------------------------------------------------------------
WCFOMA_STYLE = {
    'figure.figsize': (8, 5),
    'figure.dpi': 150,
    'font.size': 11,
    'font.family': 'serif',
    'axes.labelsize': 12,
    'axes.titlesize': 13,
    'legend.fontsize': 10,
    'xtick.labelsize': 10,
    'ytick.labelsize': 10,
    'axes.grid': True,
    'grid.alpha': 0.3,
    'lines.linewidth': 2,
}

COLORS = {
    'normal': '#2196F3',
    'normal_stressed': '#F44336',
    'zim': '#4CAF50',
    'zim_stressed': '#FF9800',
    'theory': '#9E9E9E',
    'threshold': '#E91E63',
}


def apply_style():
    """Apply WCFOMA publication style to matplotlib."""
    mpl.rcParams.update(WCFOMA_STYLE)


def save_figure(fig, name: str, output_dir: str = "analysis/figures"):
    """Save figure as both PNG and PDF."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    fig.savefig(out / f"{name}.png", bbox_inches='tight', dpi=300)
    fig.savefig(out / f"{name}.pdf", bbox_inches='tight')
    print(f"Saved: {out / name}.png/pdf")


# ---------------------------------------------------------------------------
# 1D Resonator Plots
# ---------------------------------------------------------------------------
def plot_1d_time_series(results: dict, save: bool = True):
    """
    Plot displacement vs time for the four standard 1D cases.
    Corresponds to paper Section 5.3 results.
    """
    apply_style()
    fig, axes = plt.subplots(2, 2, figsize=(12, 8))
    axes = axes.flatten()

    for ax, (label, r) in zip(axes, results.items()):
        color = (COLORS['zim'] if 'ZIM' in label else COLORS['normal'])
        ax.plot(r.t * 1000, r.x, color=color, alpha=0.8)
        ax.set_title(f"{label}\nf={r.f_theory:.1f} Hz, τ={r.coherence_time:.4f} s")
        ax.set_xlabel('Time (ms)')
        ax.set_ylabel('Displacement')

    fig.suptitle('1D Resonator: Normal vs ZIM Under Shear Stress', fontsize=14)
    plt.tight_layout()

    if save:
        save_figure(fig, 'exp_1d_time_series')
    return fig


def plot_frequency_drift_comparison(gamma_values, drift_1d, drift_3d,
                                     save: bool = True):
    """
    Plot frequency drift vs shear strain for 1D and 3D.
    Corresponds to paper Section 5.3 / Experiment 03.
    """
    apply_style()
    fig, ax = plt.subplots()

    ax.plot(gamma_values, drift_1d, color=COLORS['normal'],
            label='1D (isotropic)', linewidth=2)
    ax.plot(gamma_values, drift_3d, color=COLORS['zim'],
            label='3D (anisotropic, z-axis)', linewidth=2)

    ax.set_xlabel('Shear Strain γ')
    ax.set_ylabel('Frequency Drift (%)')
    ax.set_title('Tamper Signal: Frequency Drift vs Mechanical Stress')
    ax.legend()
    ax.axhline(y=33, color=COLORS['threshold'], linestyle='--',
               alpha=0.5, label='Paper claim: ~33% (1D)')

    plt.tight_layout()
    if save:
        save_figure(fig, 'exp_frequency_drift')
    return fig


# ---------------------------------------------------------------------------
# Thermal / Mode Density Plots
# ---------------------------------------------------------------------------
def plot_thermal_mode_margin(result_normal, result_zim, save: bool = True):
    """
    Plot mode distinguishability margin vs mode number.
    Corresponds to Addendum thermal drift analysis.
    """
    apply_style()
    fig, ax = plt.subplots(figsize=(10, 5))

    ax.plot(result_normal.mode_numbers, result_normal.margins / 1e6,
            color=COLORS['normal'], label=f'Normal ({result_normal.max_safe_modes} modes)')
    ax.plot(result_zim.mode_numbers, result_zim.margins / 1e6,
            color=COLORS['zim'], label=f'ZIM ({result_zim.max_safe_modes} modes)')

    ax.axhline(y=0, color=COLORS['threshold'], linestyle='--', alpha=0.7,
               label='Distinguishability limit')
    ax.set_xlabel('Mode Number n')
    ax.set_ylabel('Margin (MHz)')
    ax.set_title('Mode Distinguishability Under Thermal Drift (±5 K)')
    ax.legend()
    ax.set_xlim(0, result_zim.max_safe_modes * 1.2)

    plt.tight_layout()
    if save:
        save_figure(fig, 'exp_thermal_margin')
    return fig


def plot_sensitivity_sweep(param_values, modes, densities,
                            param_name: str, save: bool = True):
    """
    Plot sensitivity sweep results (modes and density vs parameter).
    """
    apply_style()
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))

    ax1.plot(param_values, modes, color=COLORS['zim'], linewidth=2)
    ax1.set_xlabel(param_name)
    ax1.set_ylabel('Max Safe Modes')
    ax1.set_title(f'Mode Count vs {param_name}')

    ax2.plot(param_values, densities, color=COLORS['zim_stressed'], linewidth=2)
    ax2.set_xlabel(param_name)
    ax2.set_ylabel('Storage Density (Tb/cm³)')
    ax2.set_title(f'Density vs {param_name}')

    plt.tight_layout()
    if save:
        save_figure(fig, f'exp_sweep_{param_name.replace(" ", "_").lower()}')
    return fig


# ---------------------------------------------------------------------------
# Coherence Comparison
# ---------------------------------------------------------------------------
def plot_coherence_comparison(eta_values, tau_normal, tau_zim, tau_theory,
                               save: bool = True):
    """
    Plot coherence time vs damping for normal vs ZIM.
    Corresponds to Experiment 01 results.
    """
    apply_style()
    fig, ax = plt.subplots()

    ax.loglog(eta_values, tau_theory, '--', color=COLORS['theory'],
              label='Theory: τ = 1/(2η)', linewidth=1.5)
    ax.loglog(eta_values, tau_normal, 'o-', color=COLORS['normal'],
              label='Normal (measured)', markersize=4)
    ax.loglog(eta_values, tau_zim, 's-', color=COLORS['zim'],
              label='ZIM (measured)', markersize=4)

    ax.set_xlabel('Damping η (1/s)')
    ax.set_ylabel('Coherence Time τ (s)')
    ax.set_title('Mode Coherence Time: Normal vs ZIM')
    ax.legend()

    plt.tight_layout()
    if save:
        save_figure(fig, 'exp_coherence_comparison')
    return fig


# ---------------------------------------------------------------------------
# Architecture Diagram
# ---------------------------------------------------------------------------
def plot_architecture_layers(save: bool = True):
    """
    Generate a simplified architecture layer diagram (Figure 1 analog).
    """
    apply_style()
    fig, ax = plt.subplots(figsize=(10, 6))

    layers = [
        ("Wave-Coherent Memory Substrate\n(Standing waves + ZIM packing)",
         '#E3F2FD', 0.8),
        ("Interference-Based Computation\n(Mode excitation & interference)",
         '#E8F5E9', 0.6),
        ("Passive Mechanical Shielding\n(Dilatancy-driven tamper detection)",
         '#FFF3E0', 0.4),
        ("Optional Quantum Verification\n(Room-temp Rb vapor correlations)",
         '#F3E5F5', 0.2),
    ]

    for i, (label, color, y) in enumerate(layers):
        rect = plt.Rectangle((0.1, y), 0.8, 0.15, facecolor=color,
                               edgecolor='#333', linewidth=1.5, zorder=2)
        ax.add_patch(rect)
        ax.text(0.5, y + 0.075, label, ha='center', va='center',
                fontsize=11, fontweight='bold', zorder=3)

    # Dashed arrows for optional quantum coupling
    ax.annotate('', xy=(0.92, 0.35), xytext=(0.92, 0.275),
                arrowprops=dict(arrowstyle='->', linestyle='--',
                                color='purple', lw=1.5))

    ax.set_xlim(0, 1)
    ax.set_ylim(0.1, 1.0)
    ax.set_title('WCFOMA Architecture: Four Interacting Layers', fontsize=14)
    ax.axis('off')

    plt.tight_layout()
    if save:
        save_figure(fig, 'architecture_layers')
    return fig
