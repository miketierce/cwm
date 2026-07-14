# CWM Wheel of Fortune: Existing-Data Structural Surrogate

**Status:** PRELIMINARY OFFLINE STRUCTURAL SURROGATE. This is not a symbolic-language or physical missing-letter experiment.

## Critical Distinction

All four state variables were present during every saved physical capture. Offline masking removes decoder features, not the corresponding physical drive.

A real Wheel-of-Fortune query would omit unknown symbols from the physical input and recapture the response. This archive can only hide decoder-visible feature blocks after a full-state capture. Its honest question is: **how much latent state remains recoverable from the distributed modal response?**

## Dataset

- Source: `data/results/pong/recall_enroll_20260629_120542.npz`
- 1280 captures, 256 states, 5 repeats
- 240 features, including 212 modal features
- Complete state grid: 8 x 8 x 2 x 2 = 256 states

Because the grid is complete, it has no dictionary of valid versus invalid words and no held-out compositional state. Pong attributes must not be relabeled as letters.

## Hidden-Attribute Reconstruction

Each result uses leave-one-repeat-out state centroids. `glass_readout_masked` removes the selected direct axis-window blocks but retains all modal features. `modes_only` uses only the 212 modal measurements. Noise sigma is measured in training-standardized feature units.

For `modes_only`, the physical feature vector and predicted state are identical across mask labels; only the subset scored as hidden changes. The aggregate chance column averages attributes with different cardinalities (12.5% for x/y and 50% for vx/vy); use the per-attribute table in the exploration document for the detailed baseline.

### No added synthetic noise

| Method | Hidden attributes | Hidden tuple | Hidden symbols | Chance |
| --- | ---: | ---: | ---: | ---: |
| glass_readout_masked | 1 | 88.9% | 88.9% | 31.2% |
| glass_readout_masked | 2 | 78.6% | 88.5% | 8.6% |
| glass_readout_masked | 3 | 69.1% | 88.0% | 2.0% |
| glass_readout_masked | 4 | 60.5% | 87.6% | 0.4% |
| modes_only | 1 | 87.6% | 87.6% | 31.2% |
| modes_only | 2 | 76.9% | 87.6% | 8.6% |
| modes_only | 3 | 67.9% | 87.6% | 2.0% |
| modes_only | 4 | 60.5% | 87.6% | 0.4% |
| visible_axis_windows_only | 1 | 79.4% | 79.4% | 31.2% |
| visible_axis_windows_only | 2 | 43.7% | 56.8% | 8.6% |
| visible_axis_windows_only | 3 | 12.3% | 40.6% | 2.0% |
| wire_visible | 1 | 93.8% | 93.8% | 31.2% |
| wire_visible | 2 | 62.2% | 67.9% | 8.6% |
| wire_visible | 3 | 13.9% | 40.1% | 2.0% |

### Sigma = 1 synthetic feature noise

| Method | Hidden attributes | Hidden tuple | Hidden symbols | Chance |
| --- | ---: | ---: | ---: | ---: |
| glass_readout_masked | 1 | 77.5% | 77.5% | 31.2% |
| glass_readout_masked | 2 | 56.9% | 75.0% | 8.6% |
| glass_readout_masked | 3 | 42.8% | 74.5% | 2.0% |
| glass_readout_masked | 4 | 31.0% | 72.9% | 0.4% |
| modes_only | 1 | 74.1% | 74.1% | 31.2% |
| modes_only | 2 | 53.7% | 73.6% | 8.6% |
| modes_only | 3 | 40.4% | 73.4% | 2.0% |
| modes_only | 4 | 32.0% | 73.8% | 0.4% |
| visible_axis_windows_only | 1 | 47.8% | 47.8% | 31.2% |
| visible_axis_windows_only | 2 | 13.8% | 38.9% | 8.6% |
| visible_axis_windows_only | 3 | 3.0% | 34.8% | 2.0% |
| wire_visible | 1 | 35.6% | 35.6% | 31.2% |
| wire_visible | 2 | 10.3% | 34.7% | 8.6% |
| wire_visible | 3 | 2.1% | 33.4% | 2.0% |

## Sparse-Vocabulary Abstention Proxy

A deterministic parity split enrolls 128 states and treats the other 128 as unknown. This tests physical-feature geometry and confidence only; parity is not a semantic vocabulary.

| Method | Sigma | Known exact retrieval | Known accepted | Unknown rejected | Known-vs-unknown AUC |
| --- | ---: | ---: | ---: | ---: | ---: |
| glass_readout_masked | 0.0 | 85.8% | 94.1% | 7.7% | 0.549 |
| modes_only | 0.0 | 75.0% | 94.4% | 6.9% | 0.533 |
| wire_visible | 0.0 | 100.0% | 93.9% | 100.0% | 1.000 |
| glass_readout_masked | 1.0 | 58.9% | 93.4% | 6.9% | 0.517 |
| modes_only | 1.0 | 44.5% | 94.2% | 7.0% | 0.509 |
| wire_visible | 1.0 | 11.1% | 94.7% | 7.2% | 0.524 |

## What This Settles

1. It quantifies the Wheel analogy's existing-data core: reconstruction of an enrolled physical state from a restricted decoder view.
2. It measures whether distance can support abstention when half the physical state grid is excluded from enrollment.
3. It does not test physical query completion, symbolic composition, interpolation, or generation.

## Required Physical Wheel Experiment

1. Choose a constrained bank of 8 four-symbol codewords, including easy, minimal-pair, and deliberately ambiguous clues.
2. Encode the four symbol positions on four independently controlled tones. Randomize symbol-to-amplitude mapping across sessions so scalar order cannot masquerade as spelling structure.
3. Capture full codewords for enrollment. For each clue, physically turn unknown-position drives off and recapture; do not merely hide FFT bins afterward.
4. Compare CWM with direct wire, Hamming lookup, identical software random projection, and a no-glass electrical path using the same decoder.
5. Score unique-clue top-1 accuracy, ambiguous-clue set recall, invalid-clue abstention, calibration, cross-session transfer, energy, and latency.

**Initial pass gate:** at least 80% unique-clue completion with one or two positions physically omitted, at least 10 percentage points above direct wire under matched analog noise, unknown-state AUC at least 0.90, and less than 10-point cross-session loss.

**Kill / reframe:** stop calling it physical completion if the advantage exists only under post-capture readout masking, if direct wire or Hamming lookup matches it, or if every invalid clue is confidently forced to an enrolled codeword.

## Relationship to PRs #6 and #7

- PR #7 defines Wheel of Fortune as the retrieval-versus-generation separator. This analysis addresses only the enrolled-state retrieval/abstention edge of that protocol.
- PR #6's Kaprekar benchmark is the next transition-memory stage: a controller repeatedly queries stored successor cards. It does not become acoustic arithmetic, and the current 4-8 robust-slot ceiling requires a reduced graph.

## Reproduction

```bash
python3 tools/wheel_of_fortune_surrogate.py
```

Machine-readable details are in `data/results/wheel_of_fortune_surrogate/summary.json`.
