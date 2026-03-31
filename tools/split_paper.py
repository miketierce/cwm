#!/usr/bin/env python3
"""
Split v18.md into two papers:

  Paper A (cwm_core.md):
    Core CWM — architecture, prototype, FEM, MEMS design, scaling, comparison, limits
    Sections 1-10, 13-16 (renumbered 11-14), Appendices A-C

  Paper B (cwm_advanced.md):
    Advanced CWM — encoding extensions, rewritability paths
    New §1 intro, old §11→§2, old §12→§3, new §4 discussion, new §5 conclusion

Handles: section extraction, section/subsection renumbering, reference filtering
and renumbering, figure display-number renumbering (not filenames), new TOC/preamble.

Does NOT handle: prose cross-reference updates (§11→Paper B citations etc.),
peer review content fixes. Those are applied manually after running this script.

Usage: cd /Users/Mike/Code/wcfoma && python tools/split_paper.py
"""

import re
from pathlib import Path

INPUT = Path('paper/v18.md')
OUTPUT_A = Path('paper/cwm_core.md')
OUTPUT_B = Path('paper/cwm_advanced.md')

# ── Figure renumbering maps ──────────────────────────────────────────────────
# Paper A: §1-10 + §13-16 figures (original → new sequential)
FIG_RENUM_A = {1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6,
               11: 7, 12: 8, 13: 9, 15: 10, 16: 11}
# Paper B: §11-12 figures (in order of appearance)
FIG_RENUM_B = {7: 1, 8: 2, 14: 3, 9: 4, 10: 5}


# ── Helpers ──────────────────────────────────────────────────────────────────

def find_section_starts(lines):
    """Return dict of section_number -> 0-indexed start line."""
    sections = {}
    for i, line in enumerate(lines):
        m = re.match(r'^## (\d+)\. ', line)
        if m:
            sections[int(m.group(1))] = i
    return sections


def find_line(lines, pattern):
    """Return 0-indexed line number of first match, or None."""
    for i, line in enumerate(lines):
        if re.search(pattern, line):
            return i
    return None


def parse_references(ref_lines):
    """Parse reference block lines into dict {ref_num: text_string}."""
    refs = {}
    current = None
    buf = []
    for line in ref_lines:
        m = re.match(r'^\[(\d+)\]', line)
        if m:
            if current is not None:
                refs[current] = '\n'.join(buf).rstrip()
            current = int(m.group(1))
            buf = [line]
        elif current is not None:
            buf.append(line)
    if current is not None:
        refs[current] = '\n'.join(buf).rstrip()
    return refs


def find_citations(text):
    """Find all citation numbers in [N], [N, M], [N, M, P] patterns."""
    numbers = set()
    for m in re.finditer(r'\[([\d,\s\u2013-]+)\](?!\()', text):
        inner = m.group(1)
        for n in re.findall(r'\d+', inner):
            numbers.add(int(n))
    return numbers


def renumber_citations(text, mapping):
    """Replace citation numbers in [N], [N, M], etc. patterns."""
    def replace_group(m):
        inner = m.group(1)
        def replace_num(n_match):
            num = int(n_match.group(0))
            return str(mapping.get(num, num))
        new_inner = re.sub(r'\d+', replace_num, inner)
        return f'[{new_inner}]'
    return re.sub(r'\[([\d,\s\u2013-]+)\](?!\()', replace_group, text)


def renumber_ref_block(refs, mapping):
    """Build a new reference list from refs dict, applying number mapping."""
    lines = []
    for old_num in sorted(mapping.keys()):
        new_num = mapping[old_num]
        if old_num in refs:
            ref_text = refs[old_num]
            # Replace leading [old] with [new]
            ref_text = re.sub(rf'^\[{old_num}\]', f'[{new_num}]', ref_text)
            lines.append(ref_text)
            lines.append('')
    return '\n'.join(lines)


def renumber_section_headers(text, mapping):
    """Renumber ## N. and ### N.X headers and §N / Section N references.
    Uses placeholder strategy to avoid cascading rewrites."""
    def _ph(n):
        return f'__SECNUM_{n:02d}__'

    # Phase 1: Replace all old numbers with unique placeholders
    for old in sorted(mapping.keys(), reverse=True):
        new = mapping[old]
        ph = _ph(new)
        text = re.sub(
            rf'^(## ){old}(\. )',
            rf'\g<1>{ph}\2',
            text, flags=re.MULTILINE
        )
        text = re.sub(
            rf'^(### ){old}\.',
            rf'\g<1>{ph}.',
            text, flags=re.MULTILINE
        )
        text = re.sub(
            rf'§§{old}\.(\d+)[–-]{old}\.(\d+)',
            rf'§§{ph}.\1–{ph}.\2',
            text
        )
        text = re.sub(rf'§{old}\.(\d)', rf'§{ph}.\1', text)
        text = re.sub(rf'Section {old}\.(\d)', rf'Section {ph}.\1', text)
        text = re.sub(rf'Section {old}(?=[\s,.\);:\]])', f'Section {ph}', text)
        text = re.sub(rf'§{old}(?=[\s,.\);:\]])', f'§{ph}', text)
        text = re.sub(rf'§§{old}(?=[\s,.\);:\]])', f'§§{ph}', text)

    # Phase 2: Replace placeholders with final numbers
    for new in sorted(set(mapping.values())):
        text = text.replace(_ph(new), str(new))

    return text


def renumber_figures(text, mapping):
    """Renumber Figure N display numbers (not filenames) in text.
    Uses placeholder strategy to avoid cascading rewrites."""
    def _ph(n):
        return f'__FIG_{n:02d}__'

    # Phase 1: Replace all old numbers with unique placeholders
    for old in sorted(mapping.keys(), reverse=True):
        ph = _ph(mapping[old])
        # "Figure 11." — period NOT followed by digit
        text = re.sub(
            rf'(Figure\s+){old}(\.(?!\d))',
            rf'\g<1>{ph}\2',
            text
        )
        # "Figure 11:" in alt text
        text = re.sub(
            rf'(Figure\s+){old}(:)',
            rf'\g<1>{ph}\2',
            text
        )
        # "Figure 11 " or "Figure 11," etc in prose
        text = re.sub(
            rf'(Figure\s+){old}(?=[\s,\)\(])',
            rf'\g<1>{ph}',
            text
        )

    # Phase 2: Replace placeholders with final numbers
    for new in sorted(set(mapping.values())):
        text = text.replace(_ph(new), str(new))

    return text


# ── Paper A preamble & TOC ───────────────────────────────────────────────────

PAPER_A_PREAMBLE = r"""# Coherent Wave Memory: Wave-Based Storage and Computation in Acoustic Glass Resonators

**Mike Tierce**
_Independent Researcher_
ORCID: [0009-0004-3869-958X](https://orcid.org/0009-0004-3869-958X)
Repository: [github.com/miketierce/cwm](https://github.com/miketierce/cwm)

**March 2026**
_U.S. Provisional Patent Application No. 64/023,264 — Filed 31 March 2026_

---

## Table of Contents

**Part I — Theory and Architecture**

1. [Introduction](#1-introduction) — The memory wall; wave-based memory; summary of results
   - 1.1 The Memory Wall
   - 1.2 Wave-Based Memory
   - 1.3 Summary of Results
2. [Architecture](#2-architecture) — Eigenmode encoding; perturbation write; interference recall
   - 2.1 Eigenmode Encoding
   - 2.2 Perturbation Encoding (Write)
   - 2.3 Interference Recall (Read / Compute)
   - 2.4 Architecture Summary

**Part II — Substrate and Prototype**

3. [Substrate Selection](#3-substrate-selection) — Ferrofluid failure; glass physics
   - 3.1 Ferrofluid: A Dead End
   - 3.2 Glass: Zero Phase Diffusion
4. [Macro-Scale Prototype](#4-macro-scale-prototype) — $230 prototype ($38 core materials); 98.5 dB derived SNR; Q = 10,000
   - 4.1 The Experiment
   - 4.2 Bill of Materials
   - 4.3 Signal-to-Noise Ratio
   - 4.4 Mode Spectrum
   - 4.5 Perturbation Encoding Demonstration
   - 4.6 Associative Recall

**Part III — Finite Element Analysis**

5. [Finite Element Analysis](#5-finite-element-analysis) — 1D/2D FEM eigenfrequencies; wave speed discovery; Pochhammer–Chree dispersion
   - 5.1 Motivation
   - 5.2 One-Dimensional FEM: Wave Speed Discovery
   - 5.3 Rayleigh Perturbation Validation
   - 5.4 Mesh Convergence
   - 5.5 Two-Dimensional FEM and Pochhammer–Chree Dispersion

**Part IV — MEMS Design and Scaling**

6. [Scaling Laws](#6-scaling-laws) — SNR, mode count, density as functions of rod length
   - 6.1 SNR Scales Linearly with Length
   - 6.2 Mode Count Is Size-Independent
   - 6.3 Density Scales as $1/L^2$
   - 6.4 Crossover Points
7. [MEMS Q-Factor Analysis](#7-mems-q-factor-analysis) — Five-mechanism loss budget
   - 7.1–7.6 Q-factor model
8. [MEMS Device Specification](#8-mems-device-specification) — Reference design; array architecture; energy budget
   - 8.1–8.5 Device specification
9. [Fabrication Pathway](#9-fabrication-pathway) — Six-step MEMS process flow
   - 9.1–9.3 Process flow; BOM; risk

**Part V — Context and Limits**

10. [Technology Comparison](#10-technology-comparison) — Density, speed, energy benchmarks
    - 10.1–10.5 Benchmarks; architectural distinction; applications
11. [Ultimate Limits](#11-ultimate-limits) — Fused silica; Tbit/cm³ arrays
    - 11.1 Fused Silica
    - 11.2 Array Performance
    - 11.3 Q-Factor Model for Fused Silica

**Part VI — Outlook**

12. [Discussion](#12-discussion) — Validated vs. projected; related work; limitations
    - 12.1 What Is Validated vs. Projected
    - 12.2 Related Work and Technology Context
    - 12.3 Limitations and Open Questions
13. [Roadmap](#13-roadmap) — Four-phase development plan
14. [Conclusion](#14-conclusion)

**Appendices**

- [A: SNR and Density Scaling Derivation](#appendix-a-snr-and-density-scaling-derivation)
- [B: Q-Factor Model Details](#appendix-b-q-factor-model-details)
- [C: Macro-Scale Experiment Guide](#appendix-c-macro-scale-experiment-guide)

"""


# ── Paper B preamble, intro, discussion, conclusion ──────────────────────────

PAPER_B_PREAMBLE = r"""# Advanced Encoding and Rewritability Techniques for Coherent Wave Memory

**Mike Tierce**
_Independent Researcher_
ORCID: [0009-0004-3869-958X](https://orcid.org/0009-0004-3869-958X)
Repository: [github.com/miketierce/cwm](https://github.com/miketierce/cwm)

**March 2026**
_U.S. Provisional Patent Application No. 64/023,264 — Filed 31 March 2026_

---

## Abstract

Coherent Wave Memory (CWM) encodes information in the acoustic eigenmode spectrum of glass resonators and computes via wave interference [PAPER_A_REF]. This companion paper develops twenty-two modeled extensions to the baseline CWM architecture. Six firmware-level techniques—synaptic pruning (+10.7% recall accuracy), in-situ Boolean computation (>90% fidelity), mode hybridization (+160% capacity), null-space multiplexing (+60%), polysemic readout (+297%), and phase-spectral encoding (+84% discriminability)—require zero hardware changes. Sixteen cross-domain investigations test 87 additional hypotheses across wave physics, information theory, and spectral analysis, confirming 51 and killing 36. Three paths to rewritability—firmware-defined virtual rewriting (4+ logical devices per rod), binary MEMS perturbation sites (7.6 bits, <0.5% Q penalty), and writable shell coatings (100 nm at Q > 5,000)—progressively transform CWM from read-only to fully reconfigurable. All extensions are simulated and validated by automated tests; none have been confirmed on hardware.

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [Advanced Encoding and Recall Techniques](#2-advanced-encoding-and-recall-techniques)
   - 2.1 Synaptic Pruning for Associative Recall
   - 2.2 In-Situ Boolean Computation
   - 2.3 Mode Hybridization at Near-Degeneracy
   - 2.4 Null-Space Multiplexing
   - 2.5 Polysemic Readout: Multi-Channel Spectral Decoding
   - 2.6 Combined Capacity Enhancement
   - 2.7 Cross-Domain Validation Summary
3. [Paths to Rewritability](#3-paths-to-rewritability)
   - 3.1 The Rewritability Question
   - 3.2 Track A: Firmware-Defined Virtual Rewriting
   - 3.3 Track B: Binary Perturbation Sites
   - 3.4 Track C: Multi-Shell Resonator
   - 3.5 Track D: Femtosecond Volumetric Inscription
   - 3.6 Layered Architecture
4. [Discussion](#4-discussion)
5. [Conclusion](#5-conclusion)

"""

PAPER_B_INTRO = r"""## 1. Introduction

Coherent Wave Memory (CWM) stores data in the eigenmode spectrum of solid glass resonators and performs nearest-neighbor search via acoustic wave interference in a single propagation cycle. The core architecture—eigenmode encoding, Rayleigh perturbation writing, and interference recall—is developed and validated at macro scale in the companion paper [PAPER_A_REF], which establishes a \$230 prototype (\$38 core materials) with 98.5 dB derived SNR, 9,380 thermally stable modes per resonator, and a five-mechanism MEMS Q-factor model predicting $Q_{\text{total}} = 9{,}097$. Full details on the architecture (eigenmode encoding, Shannon capacity, Hopfield associative recall), substrate selection, finite element validation, MEMS scaling laws, Q-factor analysis, device specification, and fabrication pathway are in [PAPER_A_REF].

This paper extends the baseline architecture in two directions. First, Section 2 presents six firmware-implementable encoding and recall techniques that enhance capacity and functionality with zero hardware changes, followed by sixteen cross-domain investigations that systematically test the boundaries of eigenmode physics across wave mechanics, information theory, and spectral analysis. Second, Section 3 develops three hardware paths to rewritability—firmware-defined virtual rewriting, binary MEMS perturbation sites, and writable shell coatings—progressively transforming CWM from a glass harmonica (fixed pitch) to a glass armonica (reconfigurable).

All extensions are modeled by simulation (48 modules total; 1,747 tests across 20 modules for cross-domain investigations alone) and await hardware validation on the MEMS prototype described in [PAPER_A_REF].

---
"""

PAPER_B_DISCUSSION = r"""## 4. Discussion

### 4.1 Practical Implications

The six core extensions of §§2.1–2.6 are immediately deployable on any CWM readout ASIC—they require only firmware changes to the signal processing pipeline. A conservative near-term estimate, applying polysemic sub-band partitioning alone, could increase effective packed-array density by 2–3× over the baseline 17.0 Gbit/cm³ reported in [PAPER_A_REF].

The gain factors reported for each technique should not be multiplied naively. Inter-technique interactions, real-device noise, and practical readout constraints at $N = 9{,}380$ modes will reduce achievable gains relative to the small-scale simulations (typically 10–50 modes) used here.

### 4.2 Falsification Record

The simulation apparatus has tested 99 hypotheses across all CWM research (including the core architecture validated in [PAPER_A_REF]): 67 confirmed, 32 falsified—all preserved with full documentation of their failure mechanisms. The killed hypotheses are as scientifically valuable as the confirmations: they map the boundaries of each technique and identify which physical frameworks transfer to finite-rank eigenmode systems and which do not.

### 4.3 Limitations

All extensions in this paper are simulated at small scale (typically 10–50 modes). Whether the capacity gains (e.g., +297% polysemic, +160% hybridization) survive scaling to thousands of modes in a physical device with real noise, fabrication tolerances, and mode coupling is an open question. The cross-domain investigations (§2.7) explore established physical frameworks, but their quantitative transfer to CWM eigenmode systems requires experimental confirmation. The rewritability paths of Section 3 each carry specific engineering risks documented in their respective subsections.

---
"""

PAPER_B_CONCLUSION = r"""## 5. Conclusion

Twenty-two modeled extensions and three rewritability paths demonstrate that the CWM eigenmode architecture supports a rich design space beyond the baseline read-only device described in [PAPER_A_REF].

The firmware-only techniques (§§2.1–2.6) offer capacity and functionality gains deployable on day one of MEMS production: synaptic pruning improves associative recall (+10.7%), Boolean computation adds logic capability (>90% fidelity), mode hybridization (+160%), null-space multiplexing (+60%), and polysemic readout (+297%) each exploit different facets of the eigenmode physics. The cross-domain validation (§2.7) maps the boundaries—51 confirmed hypotheses identify what transfers across 20 physical and mathematical frameworks; 36 killed hypotheses identify what does not.

The rewritability tracks (Section 3) provide a staged development path from read-only ROM (Stage 0) through firmware-reconfigurable (Stage 1), MEMS-switchable (Stage 2), shell-writable (Stage 3), to volumetrically inscribed (Stage 4). Each stage is backward-compatible. The key architectural insight—separating the read medium (glass rod) from the write mechanism (firmware, surface, shell, or volumetric)—enables independent optimization of acoustic quality and write endurance.

What remains is hardware. A single fabricated MEMS die with thin-film piezo readout would convert every projection in this paper into a measurement.

---

_Patent Pending — U.S. Provisional Application No. 64/023,264 (31 March 2026)._

_All quantitative claims computed from first-principles simulation code (48 modules, 2,253 automated tests, all passing). Repository: github.com/miketierce/cwm. Companion volume: github.com/miketierce/cwm-book._
"""


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    content = INPUT.read_text()
    lines = content.split('\n')

    # ── Find structural boundaries ──
    sections = find_section_starts(lines)
    ref_start = find_line(lines, r'^## References$')
    app_starts = sorted(
        i for i, l in enumerate(lines) if re.match(r'^## Appendix [A-Z]:', l)
    )

    # ── Extract blocks ──
    sec_1_10     = lines[sections[1]:sections[11]]
    sec_11       = lines[sections[11]:sections[12]]
    sec_12       = lines[sections[12]:sections[13]]
    sec_13_16    = lines[sections[13]:ref_start]

    ref_end = app_starts[0] if app_starts else len(lines)
    ref_block    = lines[ref_start:ref_end]
    appendices   = lines[app_starts[0]:] if app_starts else []

    refs = parse_references(ref_block)

    # ==================================================================
    # PAPER A — Core CWM
    # ==================================================================

    # Assemble body: §1-10 + separator + §13-16
    paper_a_body = '\n'.join(sec_1_10) + '\n\n---\n\n' + '\n'.join(sec_13_16)
    paper_a_appendix = '\n'.join(appendices)

    # Step 1: Renumber §13-16 → §11-14
    sec_renum_a = {13: 11, 14: 12, 15: 13, 16: 14}
    paper_a_body = renumber_section_headers(paper_a_body, sec_renum_a)
    paper_a_appendix = renumber_section_headers(paper_a_appendix, sec_renum_a)

    # Step 2: Renumber figures
    paper_a_body = renumber_figures(paper_a_body, FIG_RENUM_A)

    # Step 3: Determine which references are cited
    full_a_text = paper_a_body + '\n' + paper_a_appendix
    cited_a = find_citations(full_a_text) & set(refs.keys())

    # Build reference mapping (sequential, preserving order)
    cited_a_sorted = sorted(cited_a)
    ref_map_a = {old: new for new, old in enumerate(cited_a_sorted, 1)}

    # Paper B will be the next reference number
    paper_b_refnum = len(ref_map_a) + 1

    # Step 4: Renumber citations in body and appendices
    paper_a_body = renumber_citations(paper_a_body, ref_map_a)
    paper_a_appendix = renumber_citations(paper_a_appendix, ref_map_a)

    # Step 5: Build reference list
    paper_a_ref_text = renumber_ref_block(refs, ref_map_a)
    paper_b_citation = (
        f'[{paper_b_refnum}] M. Tierce, "Advanced Encoding and Rewritability '
        f'Techniques for Coherent Wave Memory," companion paper, 2026. '
        f'Repository: [github.com/miketierce/cwm](https://github.com/miketierce/cwm).\n'
    )

    # Step 6: Assemble Paper A
    paper_a = '\n'.join([
        PAPER_A_PREAMBLE.strip(),
        '',
        paper_a_body,
        '',
        '---',
        '',
        '## References',
        '',
        paper_a_ref_text.rstrip(),
        '',
        paper_b_citation,
        '---',
        '',
        paper_a_appendix.rstrip(),
        '',
    ])

    OUTPUT_A.write_text(paper_a)
    print(f'✓ Wrote {OUTPUT_A} ({len(paper_a.splitlines())} lines)')
    print(f'  References: {len(ref_map_a)} original + Paper B [{paper_b_refnum}]')
    print(f'  Original refs used: {cited_a_sorted}')
    print(f'  Original refs NOT used (§11-12 only): '
          f'{sorted(set(refs.keys()) - cited_a)}')

    # ==================================================================
    # PAPER B — Advanced Techniques
    # ==================================================================

    # Assemble body: §11 + separator + §12
    paper_b_body = '\n'.join(sec_11) + '\n\n---\n\n' + '\n'.join(sec_12)

    # Step 1: Renumber §11→§2, §12→§3
    sec_renum_b = {11: 2, 12: 3}
    paper_b_body = renumber_section_headers(paper_b_body, sec_renum_b)

    # Step 2: Renumber figures
    paper_b_body = renumber_figures(paper_b_body, FIG_RENUM_B)

    # Step 3: Determine which references are cited
    cited_b = find_citations(paper_b_body) & set(refs.keys())

    # Build reference mapping
    cited_b_sorted = sorted(cited_b)
    ref_map_b = {old: new for new, old in enumerate(cited_b_sorted, 1)}
    paper_a_refnum = len(ref_map_b) + 1

    # Step 4: Renumber citations
    paper_b_body = renumber_citations(paper_b_body, ref_map_b)

    # Step 5: Build reference list
    paper_b_ref_text = renumber_ref_block(refs, ref_map_b)
    paper_a_citation = (
        f'[{paper_a_refnum}] M. Tierce, "Coherent Wave Memory: Wave-Based '
        f'Storage and Computation in Acoustic Glass Resonators," companion '
        f'paper, 2026. Repository: [github.com/miketierce/cwm]'
        f'(https://github.com/miketierce/cwm).\n'
    )

    # Step 6: Replace PAPER_A_REF placeholders in framing text
    preamble_b = PAPER_B_PREAMBLE.replace('PAPER_A_REF', str(paper_a_refnum))
    intro_b = PAPER_B_INTRO.replace('PAPER_A_REF', str(paper_a_refnum))
    disc_b = PAPER_B_DISCUSSION.replace('PAPER_A_REF', str(paper_a_refnum))
    conc_b = PAPER_B_CONCLUSION.replace('PAPER_A_REF', str(paper_a_refnum))

    # Step 7: Assemble Paper B
    paper_b = '\n'.join([
        preamble_b.strip(),
        '',
        intro_b.strip(),
        '',
        paper_b_body,
        '',
        disc_b.strip(),
        '',
        conc_b.strip(),
        '',
        '---',
        '',
        '## References',
        '',
        paper_b_ref_text.rstrip(),
        '',
        paper_a_citation,
    ])

    OUTPUT_B.write_text(paper_b)
    print(f'\n✓ Wrote {OUTPUT_B} ({len(paper_b.splitlines())} lines)')
    print(f'  References: {len(ref_map_b)} original + Paper A [{paper_a_refnum}]')
    print(f'  Original refs used: {cited_b_sorted}')

    # ── Summary of manual work needed ──
    print('\n' + '=' * 70)
    print('MANUAL EDITS NEEDED AFTER RUNNING THIS SCRIPT')
    print('=' * 70)
    print('''
Paper A (cwm_core.md):
  1. Replace "Modeled extensions" sub-table in §1.3 with brief Paper B note
  2. Update §1.3 callout box (remove §11-specific validated items)
  3. Update §2.3 cross-ref "Section 11.1" → Paper B reference
  4. Update §10.4 cross-ref "Section 12" → Paper B reference
  5. Update §12.1 validated list (move §11/§12 items → Paper B note)
  6. Update §12.2 cross-ref "§11.7" → Paper B reference
  7. Remove §12.3 (IP discussion) — patent notice at end is sufficient
  8. Update §12.4 → §12.3 (renumber after IP removal)
  9. Update §13 Roadmap items referencing Paper B techniques
  10. Update §14 Conclusion references to §11/§12

  Peer review fixes:
  11. SNR "Measured" → "Derived" in summary table (Fix #1)
  12. Add Hopfield capacity justification paragraph (Fix #2)
  13. Figure 13 → Figure 9: clarify 8-rod array prototype (Fix #4, #10)
  14. Soften "no processor" claim in §1.2 (Fix #5)
  15. Consistent labels in summary table (Fix #6)
  16. BOM headline: "$230 prototype ($38 core)" (Fix #7)
  17. FEM "validation" → "FEM-analytical agreement" (Fix #8)
  18. Review self-citation [23] usage (Fix #9)
  19. Trim abstract to ~200 words (Fix #11)
  20. Compress ferrofluid §3.1 (Fix #13)
  21. Add transducer bandwidth caveat in §2.1 (Fix #15)
  22. Reframe confirmation rate (Fix #16)
  23. Qualify ferrofluid 77.5% simulation number (Fix #17)

Paper B (cwm_advanced.md):
  1. Update cross-refs from §11/§12 text that point to §1-10 → Paper A ref
  2. Review PAPER_A_REF placeholder replacements
  3. Verify figure captions after renumbering
''')


if __name__ == '__main__':
    main()
