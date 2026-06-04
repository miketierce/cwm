# v19 Rewrite Instructions — Coherent Wave Memory

**Purpose.** Build `v19.md` *from scratch* (do not edit v18 in place) using v18 as the
structural skeleton and folding in every hardware result accumulated in
`paper/rewrite_notes.md` plus the lab diary (`docs/lab_diary_*.md`, `docs/LAB_DIARY.md`,
`docs/WORKLIST.md`). The goal is a paper that is (a) a *valid* scientific contribution and
(b) clean enough to clear arXiv moderation and survive a skeptical referee.

**Audience for v19.** arXiv preprint in `physics.app-ph` (cross-list `cond-mat.mes-hall`,
`cs.ET`). Write for a reviewer who is sympathetic to engineering-physics proposals but
allergic to overclaiming.

**The single governing principle.** *Never let a derived or projected number wear the word
"measured."* Every quantitative claim must carry one of four labels — **Measured**,
**Derived**, **Projected**, **Modeled** — and the label must be correct. This is the change
that most determines whether v19 is taken seriously.

---

## PART 0 — Critical Integrity Fixes (do these first; they gate everything)

These three issues are the difference between "credible preprint" and "desk-rejected." They
must be resolved before any new content is added.

### 0.1 The 98.5 dB SNR must be relabeled and contextualized

- **Problem:** v18 abstract, §1.3 table, §4.3, §16, and the appendix present **98.5 dB** as a
  *measured* SNR. It is not. It is a thermodynamic bound: `SNR = ½k_eff·A² / k_BT` assuming a
  1 nm drive amplitude. The lab record (rewrite_notes E18; lab_diary 20260602 T5.1) shows
  **actually measured** SNRs of **34 dB mean / 75 dB max** (rod bench) and **42–55 dB**
  (plate, Pico NCO).
- **Fix:**
  - Relabel everywhere as **"thermal-noise-limited SNR (derived)"** or
    **"thermodynamic SNR ceiling."** Never "measured."
  - Add a measured-SNR row to the §1.3 results table: *Measured bench SNR: 42–55 dB
    (plate, Pico NCO drive); 34 dB mean / 75 dB max (4-rod borosilicate).*
  - In §4.3, keep the energy-ratio derivation but state plainly: "This is the thermodynamic
    ceiling, not an instrument reading; our bench electronics measure 42–55 dB (§4.x), and the
    gap is fully accounted for by the coupling budget of §4.y."
  - Cross-reference the 47 dB gap decomposition (rewrite_notes, "Gap Between Measured and
    Claimed Density"): 88% electrical feedthrough (~9 dB), ADC quantization (~20 dB),
    breadboard pickup (~10 dB), FFT leakage (~5–8 dB).

### 0.2 The electrical-feedthrough confound must be disclosed wherever recall/Boolean/encoding results appear

- **Problem:** The May 26 campaign (LAB_DIARY, WORKLIST T3.3b/c, T4.2) established that the
  bench signal path is **~88% electrical feedthrough, 12% acoustic** in the shared-PZT
  breadboard topology. The rewrite-notes CIM results (100% Boolean, recall, NNS) are real
  *classification* results but were obtained through that confounded path.
- **Fix:**
  - Add a dedicated subsection (proposed §4.7 "Signal-Path Decomposition and the Acoustic
    Fraction") that states the 12%/88% split up front, names the three convergent
    measurements (T2.1 13.2%, T1.2 ~12%, T3.3c ~12%), and explains the null test
    (PZT-lifted → 0% feedthrough; WORKLIST T4.1) that isolates the acoustic component.
  - Every hardware result table must note whether it survives the confound. Classification
    results (recall, Boolean, NNS, multi-level) do — they depend on spectral *shape*, which
    the E36 null-control battery proves is rod-specific (shuffle=0/4, random=22%, separation
    +12.78). Temporal-memory results do **not** — disclose them as FAILs that quantify the
    coupling limit, not as architecture failures.
  - Frame consistently: "the breadboard validates the encoding physics; MEMS geometry solves
    the coupling engineering."

### 0.3 The CHSH / "classical entanglement" material must be reframed or removed — never call it a Bell violation of a physical object

- **Problem:** lab_diary 20260602 and WORKLIST Tier 5/6 report **S = 2.83 (Tsirelson bound),
  "maximal violation," "maximally entangled Bell state."** Presenting a glass plate as
  violating a Bell inequality is the single highest-risk pseudoscience signal a moderator
  screens for. As written it would endanger the entire submission.
- **What is actually true and defensible:** the plate exhibits **non-separability of its
  frequency × space (or frequency × phase) degrees of freedom** — *classical entanglement* in
  the established sense (Spreeuw 1998; Qian & Eberly 2011; Kagalwala 2013; Aiello 2015). This
  is real, publishable physics. It is **not** quantum nonlocality and does **not** violate
  Bell's theorem in the EPR sense.
- **Fix (choose one):**
  - **Preferred for v19 arXiv:** include it as a clearly bounded subsection titled
    **"Classical Non-Separability of Frequency and Spatial Modes"** with: (1) explicit
    statement that no quantum nonlocality is claimed and Bell's theorem is not violated; (2)
    the CHSH-like S parameter framed strictly as a *non-separability witness* for a single
    classical field, with citations to the classical-entanglement literature; (3) the honest
    caveats from the diary (phase instability, magnitude-only protocol, dependence on mode-pair
    selection); (4) the multi-pair E1 result (5/5 pairs S = 2.82–2.83) to defeat the
    cherry-picking objection.
  - **Safe fallback:** cut it from v19 entirely and hold it for a standalone note. If unsure,
    cut it. The architecture stands without it.
  - **Forbidden language anywhere:** "Bell violation," "entangled Bell state," "maximally
    entangled," "Tsirelson bound" used to imply quantumness, "quantum entanglement in glass."

### 0.4 Tone discipline (applies globally)

- Remove marketing superlatives: "scaling miracle," "the money shot," "on the offensive,"
  "★★," emoji verdicts. Convert to neutral scientific register.
- Keep "exceeds 3D NAND" only with the explicit *projected* label and the packing/packaging
  caveats already in v18's density-definitions box.
- The companion book [23] (with chapters like "The Dogon Connection") may be cited for
  *narrative context only*, never as evidence for any scientific claim. v19 must be fully
  self-contained for every claim.

---

## PART 1 — Document Setup

1. Create `paper/v19.md`. Header block:
   - Title unchanged.
   - Author, ORCID, repo unchanged.
   - **Version 19 — June 2026.**
   - Keep the provisional patent line.
2. Preserve v18's two strongest credibility devices verbatim in spirit:
   - The **"Density definitions used in this paper"** box (§1.3).
   - The **"Validated vs. projected at a glance"** box.
   - The **falsification ledger** (confirmed/killed counts). Update the counts (see Part 6).
3. Add an explicit **claim-label key** near the top of §1.3:
   > Measured = instrument reading on built hardware. Derived = mathematical consequence of
   > measured quantities. Projected = engineering extrapolation to unbuilt MEMS. Modeled =
   > simulation only, not yet on hardware.

---

## PART 2 — Proposed v19 Structure (TOC)

Keep v18 Parts I–VI. Insert/modify as follows:

**Part II — Substrate and Prototype**
- §4 Macro-Scale Prototype — **expand** with the plate campaign and CIM hardware.
  - 4.1–4.6 as in v18 (with §0.1 SNR relabeling).
  - **NEW 4.7** Signal-Path Decomposition and the Acoustic Fraction (§0.2).
  - **NEW 4.8** Hardware Compute-in-Memory Results (recall, NNS, Boolean — Part 3.A).
  - **NEW 4.9** Multi-Level Capacity Measurement (T3.4 — Part 3.B).
  - **NEW 4.10** Reservoir Computing and Sequence Processing (ESN v3/v4 — Part 3.C).
  - **NEW 4.11** Falsification and Null Controls (Round 7 inoculation suite — Part 3.D).

**Part V — Advanced Techniques**
- §11 Advanced Encoding — keep as Modeled, but add a "hardware status" column to every
  sub-claim table mapping to the rewrite-notes scorecard (Part 6).
- §12 Rewritability — unchanged except hardware-status annotations.

**Part VI — Outlook**
- §13 Ultimate Limits — add the Festi/Rayleigh ν⁴ ceiling material (Part 4).
- **NEW §14 Glass Vibrational Physics Context** (short): deep-Debye operating regime,
  HET basis for PUF, Rayleigh Q ceiling. (Part 4.)
- **NEW §15 Quantum-Classical Bridge** — *heavily caveated* (Part 5). Contains the classical
  non-separability subsection (§0.3) and the honest-boundaries subsection. Only include if
  §0.3 framing is followed exactly.
- §16 Discussion / §17 Roadmap / §18 Conclusion — renumber, update.

If §15 feels risky at submission time, demote it to a single conservative paragraph in §16.2
and move the rest to a companion note.

---

## PART 3 — Hardware Results to Integrate (with exact source data)

For each result below: state the **Measured** value, cite the **data file**, and add a row to
the relevant section table. Do **not** inflate; quote the numbers as recorded.

### 3.A Compute-in-Memory (new §4.8)

Source: rewrite_notes "CIM Suite Results," Rounds 1–7; data in
`data/results/lab/cim_suite/suite_20260409_110727.json` and `_122740.json`.

| Result | Measured value | Note |
| --- | --- | --- |
| Associative recall | 4/4 rods, 100%, 3/3 reproducible, margin +5.22→+5.28 | template matching |
| Nearest-neighbor search | 66/66 across 6 pairs, Kendall τ = 1.000 | universal α=0.3→0.6 crossover |
| Boolean AND/OR/XOR | 100% on 5/6 pairs; 6/6 with 5% guard band | exceeds v18's ">90%" |
| 3-input Boolean (AND3/OR3/MAJ/XOR3) | 100% | **new claim**, not in v18 |
| Chained Boolean (A∧B)⊕C | 5/5 (100%) | gate composability without regeneration |
| Noise robustness | 100% recall+Boolean at 20× attenuation (0.2 Vpp) | margin *increases* as drive drops |
| Temporal stability | 100% across 7 sessions / 48 h, Wilson CI [75.7%,100%] | E28, E37 |

- Add the **"filter first, then threshold"** design rule (pre-scan V1→V5 path, 51%→100%).
- Add the **"enrollment is the decoder ring"** cross-cutting insight.
- State the overlap-tolerance asymmetry: Boolean fails first at 42.9% overlap; NNS tolerant.
- **Confound note (mandatory):** these are classification results validated by the E36 null
  battery; they are robust to the 88% electrical fraction because scoring is on spectral shape.

### 3.B Multi-Level Capacity (new §4.9)

Source: rewrite_notes "Plate Hardware Campaign," T3.4;
`data/results/multilevel/t3_4_multilevel_20260527_104811.json`.

- **Measured:** 4 modes × 8 amplitude levels = **4,096 patterns = 12 bits / 2.6 ms capture,
  zero classification error.** Min inter-level separation 9σ.
- Per-mode SNR 42–51 dB → Shannon 7–8.5 bits/mode (**Derived**), consistent with the measured
  level count.
- This is the **first empirical confirmation of L^M scaling** (enabled by measured mode
  orthogonality: T2.2 zero IM products, T2.3 zero cross-mode coupling).
- **Hard ceiling to disclose:** ESN v4 shows a cliff at L=2→3 — the plate is a reliable
  **1-bit-per-mode binary transducer** (WorstSep > 2.3σ at L=2; < 0.6σ at L=3). More tokens
  require **more modes, not more levels.** State this honestly; it is a clean, defensible
  result, and it tempers the multi-level capacity claim.
- Reconcile with §0.1: the 47 dB gap from 98.5 dB ceiling to 51 dB bench is the coupling
  budget, not a physics discrepancy.

### 3.C Reservoir Computing & Sequence Processing (new §4.10)

Source: rewrite_notes "Plate Reservoir Computing E09," "ESN v3," "ESN v4";
`reservoir_demo_all_20260413_142516.json`, `esn_v3_8bit_20260413_182237.json`.

- **Measured:** 5/5 plates, 100% test accuracy on 4-bit parity with degree-4 polynomial
  features over diagonal self-response (separation index 3,000–7,000).
- **Measured:** ESN v3 8-bit reversal — plate raw (16 features) = **99.5% per-bit / 96.0%
  token**, beating software polynomial deg-4 (162 features) = 65.1% / 14.9%.
- Frame as the "feature-explosion trap": resonance encoding gives a compact fixed-dimension
  representation that scales gracefully; polynomial expansion does not. This supports the
  parameter-efficiency thesis **without** quantum language.
- Keep the architecture decomposition (plate = binary feature extractor; polynomial/Duffing =
  nonlinearity; ridge = linear readout). Drop the "Attention-11 / PDP-11" tangent — too
  speculative for the paper; leave it for the book.

### 3.D Falsification & Null Controls (new §4.11)

Source: rewrite_notes Round 7 (E34–E37), Round 8 (E38);
`additional_20260411_105304.json`.

- **E36 null-control battery is the single strongest evidence in the record — feature it
  prominently:** correct 4/4 (margin +5.31); shuffled enrollment 0/4; reversed weights 4/4;
  random enrollment 22% (≈ chance); separation metric **+12.78**.
- E34 weight-ratio sweep: 7/7 ratios 100%, magnitude-only = 25% (chance) — kills the
  "arbitrary 3:1 weighting" objection.
- E35 cross-rod isolation: **−3.9 dB mean (poor)** — disclose as a known macro-bench
  limitation; recall works anyway because scoring is shape-based. MEMS vacuum isolation
  projected >40 dB.
- E38 perturbation removal: rods remain distinguishable without perturbation (gap +0.062);
  perturbation adds 1–7% band changes. Upgrade Rayleigh-perturbation claim from ❌ to ⚠️ and
  state the nuance: *location* matters more than mass at macro scale.

### 3.E Q-factor reconciliation (update §4.5, §7)

- **Measured:** plate Q = 2,759 (τ = 24.5 ms at 35,840 Hz; LAB_DIARY/WORKLIST T1.1);
  prior plate campaign Q = 7,687–33,960 (AWG ringdown). Rod-bench Q = 74–572 (coupling-loss
  limited).
- The v18 "Q = 10,000 macro prototype" figure is a **borosilicate material-Q reference**, not
  a bench measurement of the epoxied-PZT rods. State this explicitly; report the real measured
  Qs and explain the loss budget (epoxy/mount/air). Cite Festi (Part 4): material ceiling
  100,000, all shortfall is extrinsic.

---

## PART 4 — Glass Vibrational Physics Context (new §14; also touches §6, §7, §13)

Source: rewrite_notes "Festi et al. (2026)."

- **Operating regime:** CWM runs ~10⁷× below the Ioffe–Regel limit and the ~1 THz boson peak.
  State that Kirchhoff/continuum theory is *exact* (not approximate) in the kHz–MHz band.
- **Rayleigh ν⁴ ceiling:** Γ ∝ ν⁴ ⇒ Q_Rayleigh ≈ 10²³ at 100 kHz (irrelevant) but ≈ 10⁶ at
  ~25 GHz. Add as a **Projected** MEMS bandwidth ceiling in §6/§13 and as a kill criterion in
  the roadmap: modes above ~10 GHz must include a per-mode Rayleigh term.
- **HET basis for PUF:** local shear-modulus fluctuations γ ≈ 0.3 (Pan 2021) ground the
  uniqueness claim in condensed-matter physics, not "manufacturing variation."
- **Cryogenic note:** TLS dominates below ~10 K; ultrastable vapor-deposited glass suppresses
  TLS 5× — a fabrication route for space/cryo CWM. Keep brief.

Add references: Festi (PRX 16, 021021, 2026), Schirmacher (PRL 98, 025501, 2007),
Pan (PRB 104, 134106, 2021), Baldi (PRL 112, 125502, 2014), Wang (PRL 134, 196101, 2025),
Phillips (Rep. Prog. Phys. 50, 1657, 1987).

---

## PART 5 — Quantum-Classical Bridge (new §15) — HIGH CAUTION

Only build this section if every guardrail in §0.3 is honored. Structure:

- **§15.1 Classical superposition as a computational resource.** N parallel analog channels;
  make the complexity-class distinction (O(N) tasks don't need quantum). No 2^N language.
- **§15.2 Non-demolition readout.** Orthogonality identity ⇒ zero measurement back-action.
  This is a clean, correct, defensible point. Keep it factual; drop the "1:1000 vs quantum"
  marketing comparison or state it as a narrow analogy only.
- **§15.3 Classical non-separability of frequency and spatial/phase modes.** The reframed
  CHSH-analog (§0.3). Lead with the explicit disclaimer. Report E1 multi-pair (5/5,
  S=2.82–2.83) and E2 (magnitude protocol validated; phase unstable). Cite Spreeuw, Kagalwala,
  Aiello, Qian & Eberly, Wang/path-identity. Novelty claim allowed: *first demonstration of
  classical (intra-system) non-separability in an acoustic resonator* — **not** entanglement.
- **§15.4 Physical security primitives (PUF, one-way function, TRNG).** Keep but mark security
  claims as *qualitative/conjectural* — they are not formally analyzed in this paper. Soften
  "immune to Shor's" to "security rests on physical unclonability rather than computational
  hardness." Cite the Jaccard 0.10–0.20 plate-independence data as supporting, not proof.
- **§15.5 Honest boundaries.** No 2^N state space, no Bell/nonlocality, classical decoherence
  (damping) limits τ, security claims unproven. This subsection is mandatory if §15 exists.

If a reviewer would read §15 as "claims quantum advantage," it is wrong — rewrite or cut.

---

## PART 6 — Evidence Scorecard (include a condensed version in §16.1)

Reproduce the final rewrite-notes tally as a compact table, with the claim-label key. Current
running total (post Round 7/8): **17 confirmed ✅ | 9 partial/disclosed ⚠️ | 6 not-at-macro ❌
| 1 inconclusive ❓ | 1 deferred 🔲.** Replace emoji with words in the paper
(Confirmed/Partial/Not-at-macro/Inconclusive/Deferred).

Mandatory honesty rows (do not omit the failures — they are the paper's credibility):
- SNR 98.5 dB → **not at macro** (34 dB mean / 75 dB max measured).
- Q = 10,000 → **not at macro** (74–572 rod; 2,759–33,960 plate).
- v_bar = 5,315 m/s → **not confirmed at macro** (~190 m/s from irregular rod spacing; thin-bar
  assumption violated by 6 mm rod). *Note:* this is FEM-validated to 7 ppm, which is the real
  support — present FEM as the validation, not the bench.
- Phase-spectral +84% → **negative at macro** (6/40 stable).
- Parametric +12 dB → **not at macro**.
- Rayleigh perturbation → **partial** (E38).
- Cross-correlation ≤0.21 claim → **not confirmed** (max |ρ| = 0.79 at macro).

Update the falsification-ledger counts in the abstract/conclusion to the current hypothesis
totals (recompute from rewrite_notes; do not reuse v18's 99/67/32 if the count has grown).

---

## PART 7 — Consolidated New References to Add

Glass physics: Festi 2026; Schirmacher 2007; Pan 2021; Baldi 2014; Wang 2025; Phillips 1987;
Rufflé 2006.
Classical entanglement (only if §15.3 included): Spreeuw 1998 (PRA 63, 062302);
Kagalwala 2013 (Nat. Photonics 7, 72); Aiello 2015 (NJP 17, 043024); Qian & Eberly 2011
(Opt. Lett. 36, 4110); Ndagano 2016 (Nat. Phys. 13, 397); Wang/Hou 2024 (arXiv:2412.03022);
Zou-Wang-Mandel 1991 (PRL 67, 318).
Synchronization (optional, §15 only): Lai, Miranowicz & Nori 2025 (Nat. Commun. 16, 8491).

Verify every DOI before submission. Drop any reference not actually cited in v19 body.

---

## PART 8 — Figures

Reuse v18 figures. Add:
- **Fig A:** Signal-path decomposition bar (12% acoustic / 88% electrical) with the null-test.
- **Fig B:** Multi-level encoding grid — 4 modes × 8 levels, showing 9σ separation.
- **Fig C:** CIM scorecard summary (recall/NNS/Boolean) across pairs.
- **Fig D:** ESN v3 plate-vs-polynomial accuracy vs token width (feature-explosion trap).
- **Fig E (only with §15.3):** Multi-pair non-separability S values with the explicit
  "classical, not Bell-nonlocal" caption.

Every figure caption must carry the claim label of the data shown.

---

## PART 9 — Acceptance Checklist (must all be true before "v19 done")

- [ ] No derived/projected number is labeled "measured." 98.5 dB fixed everywhere (§0.1).
- [ ] Electrical-feedthrough confound disclosed in §4.7 and annotated on every HW table (§0.2).
- [ ] No "Bell violation / entangled / Tsirelson" language about any physical object (§0.3).
- [ ] §15 (if present) leads and ends with explicit no-quantum-nonlocality disclaimers.
- [ ] Every claim carries Measured/Derived/Projected/Modeled.
- [ ] Failures (SNR, Q, v_bar, phase, parametric, cross-corr) are reported, not hidden (Part 6).
- [ ] Paper is self-contained; book [23] cited only for narrative context.
- [ ] Superlatives and emoji removed; neutral scientific register throughout (§0.4).
- [ ] Falsification-ledger counts recomputed and consistent across abstract/§14/§16/conclusion.
- [ ] All new references have verified DOIs and are actually cited.
- [ ] An arXiv endorser in physics.app-ph has been identified (independent-author requirement).

---

## PART 10 — What v19 Can and Cannot Claim (one-paragraph north star)

v19 may claim: a novel architectural synthesis (multimode spectral encoding + Rayleigh
perturbation write + Hopfield/interference recall in acoustic glass resonators); a reproducible
macro demonstration of spectral classification, associative recall, O(1) nearest-neighbor,
Boolean compute, multi-level encoding, and reservoir computing; FEM validation to 7 ppm;
a rigorous five-mechanism MEMS Q model; and a documented falsification record. v19 may **not**
claim: measured MEMS performance, measured 98.5 dB SNR, quantum entanglement or Bell
violation, or proven cryptographic security. Keep the boundary between *demonstrated* and
*projected* visible on every page — that boundary is the paper's chief scientific asset.
