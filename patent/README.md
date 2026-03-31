# CWM Provisional Patent — Filing Kit

## Readiness Assessment

**You are ready to file.** The existing v18 paper is a 1,571-line technical specification with architecture, prototype results, MEMS design, scaling laws, fabrication pathway, advanced encoding techniques, and rewritability paths. That is far more than what most provisionals contain. A provisional patent application does not require formal claims, an oath/declaration, or any specific formatting — it only needs a written description adequate to enable a person skilled in the art to make and use the invention.

---

## What Is a Provisional Patent Application?

A provisional patent application (PPA) establishes a **priority date** — the date from which your invention is considered filed. It lasts **12 months**, during which you must convert it to a non-provisional (full) utility patent application or it expires. The provisional itself is never examined and never publishes. Its sole purpose is to plant a flag on the date.

**Why this matters now:** Once your priority date is established, no patent filed after that date can block your claims, regardless of when they publish or issue. Filing even one day before a competitor files gives you senior rights.

---

## Filing Cost

You almost certainly qualify as a **micro entity**, which gets the lowest fee tier.

| Entity status | Provisional filing fee |
|---|---|
| Large entity | $325 |
| Small entity | $130 |
| **Micro entity** | **$65** |

### Micro Entity Qualification (37 CFR 1.29)

You qualify as a micro entity if ALL of the following are true:

- [ ] You qualify as a small entity (not a large corporation, not obligated to assign to one)
- [ ] You have not been named as inventor on more than four previously filed US patent applications (not counting provisionals that were never converted)
- [ ] Your gross income in the previous calendar year did not exceed three times the US median household income (~$232,000 for 2025 filings, based on ~$77,400 median)
- [ ] You have not assigned, granted, or conveyed (and are not obligated to do so) a license or ownership interest to an entity whose gross income exceeded that same threshold

If all boxes check, you pay **$65**.

---

## What Goes in the Envelope

### 1. Cover Sheet

Use **USPTO Form PTO/SB/16** (Provisional Application for Patent Cover Sheet). A fillable PDF is available at:

    https://www.uspto.gov/patents/apply/forms

Fill in:

- **Title of Invention:** Coherent Wave Memory: Wave-Based Storage and Computation in Acoustic Glass Resonators
- **Inventor(s):** Mike Tierce
- **Correspondence Address:** [Your mailing address]
- **Entity Status:** Micro Entity
- **Docket Number (optional):** CWM-PROV-001

### 2. Micro Entity Certification

Use **USPTO Form PTO/SB/15A** (Certification of Micro Entity Status — Gross Income Basis). Available at the same forms page. Sign and date it. This goes in the envelope with the cover sheet.

### 3. Specification (the description of your invention)

**Use the paper PDF directly: `paper/v18.pdf`**

Print the existing two-column PDF. It is your specification. It describes:

- The architecture (eigenmode encoding, perturbation write, interference recall)
- The macro-scale prototype (BOM, SNR, Q-factor, mode spectrum, perturbation encoding, associative recall)
- Finite element validation (1D/2D FEM, Pochhammer–Chree dispersion)
- MEMS scaling laws (SNR, mode count, density as functions of rod length)
- MEMS Q-factor analysis (five-mechanism loss budget)
- MEMS device specification (reference design, array architecture, energy budget)
- Fabrication pathway (six-step MEMS process flow, MEMS BOM, risk assessment)
- Advanced encoding techniques (synaptic pruning, in-situ Boolean computation, mode hybridization, null-space multiplexing, polysemic readout)
- Paths to rewritability (firmware virtual rewriting, binary perturbation sites, writable shell)
- Ultimate limits (fused silica arrays, Tbit/cm³ projections)

A provisional specification does not need to be in any particular format. A published paper format is perfectly acceptable.

### 4. Drawings

Print the 16 figures from `paper/figures/`:

| Figure | Description |
|---|---|
| fig1_architecture.svg | System architecture overview |
| fig2_mems_cross_section.svg | MEMS device cross-section |
| fig3_eigenmode_encoding.svg | Eigenmode encoding principle |
| fig4_q_budget.svg | Q-factor budget breakdown |
| fig5_scaling.svg | Scaling laws |
| fig6_fabrication.svg | Fabrication process flow |
| fig7_weight_pruning.svg | Synaptic weight pruning |
| fig8_compute_in_memory.svg | In-situ Boolean computation |
| fig9_avoided_crossing.svg | Mode hybridization / avoided crossing |
| fig10_null_space.svg | Null-space multiplexing |
| fig11_prototype_spectrum.svg | Prototype mode spectrum |
| fig12_ringdown.svg | Ringdown / Q measurement |
| fig13_recall_discrimination.svg | Associative recall discrimination |
| fig14_mode_splitting.svg | Mode splitting detail |
| fig15_cw_readout.svg | CW readout architecture |
| fig16_two_phase_readout.svg | Two-phase readout timing |

Print these at reasonable size (one per page is fine). Label each "Figure N" to match the specification references.

### 5. Filing Fee

Write a check for **$65.00** payable to:

    Director of the United States Patent and Trademark Office

Or include a credit card payment form (PTO-2038 Deposit Account/Credit Card Payment Form).

---

## How to File by Mail

Put items 1–5 in a single envelope and mail to:

    Commissioner for Patents
    P.O. Box 1450
    Alexandria, VA 22313-1450

**CRITICAL:** Use USPS Priority Mail or Express Mail (or use the Certificate of Mailing procedure below), because the filing date is assigned when the USPTO *receives* the application, not when you mail it.

### Certificate of Mailing (strongly recommended)

Include the following statement on the cover sheet or on a separate signed page:

> I hereby certify that this correspondence is being deposited with the United States Postal Service with sufficient postage as first class mail in an envelope addressed to: Commissioner for Patents, P.O. Box 1450, Alexandria, VA 22313-1450 on [DATE].
>
> Signature: ___________________
> Typed name: Mike Tierce
> Date: ___________________

This certificate, under 37 CFR 1.8, gives you the **mailing date** as your filing date even if USPS delays delivery.

---

## Alternative: File Electronically (Faster, Same Cost)

The USPTO's **Patent Center** (https://patentcenter.uspto.gov) allows electronic filing. Advantages:

- Instant filing receipt with confirmed priority date
- No risk of mail loss or delay
- Same $65 micro entity fee (no paper surcharge for provisionals)
- PDF upload — just upload v18.pdf and the figure files

To file electronically:
1. Create a USPTO.gov account at https://account.uspto.gov
2. Log in to Patent Center at https://patentcenter.uspto.gov
3. Select "Provisional application"
4. Upload the specification PDF and drawings
5. Fill in the cover sheet fields online
6. Certify micro entity status
7. Pay $65 by credit card
8. Receive filing receipt immediately

**I recommend electronic filing if you want the priority date locked in today.** Mail filing is fine but adds days of uncertainty.

---

## What Happens After Filing

1. **You receive a filing receipt** with an application number and filing date. Keep this safe.
2. **The provisional is never examined.** It just sits at the USPTO establishing your priority date.
3. **Within 12 months** you must file a non-provisional utility patent application claiming priority to this provisional, or the provisional expires and the priority date is lost.
4. **During those 12 months** you can:
   - Continue developing the technology
   - Publish papers, present at conferences, talk to investors — all without jeopardizing your filing date
   - Mark materials "Patent Pending" (once filed)
   - Add additional provisionals if the invention evolves significantly
   - Retain a patent attorney to draft the formal non-provisional application with proper claims

---

## What the Provisional Protects

The provisional protects **everything adequately described in the specification you file**. The v18 paper describes:

1. **The core apparatus:** A MEMS glass resonator array where information is stored as perturbation mass patterns and read via eigenmode spectral analysis
2. **The write method:** Lithographic deposition of perturbation masses at calculated positions along a glass rod resonator
3. **The read/compute method:** Simultaneous multi-mode excitation, FFT-based spectral analysis, and correlation-based associative recall
4. **Six advanced encoding techniques:** Synaptic pruning, in-situ Boolean computation, mode hybridization, null-space multiplexing, polysemic readout, combined capacity enhancement
5. **Three rewritability architectures:** Firmware virtual rewriting via mode-subset partitioning, binary perturbation sites with electrostatic MEMS latches, writable conformal shell
6. **The MEMS fabrication pathway:** Six-step process flow (wafer prep, DRIE, metal deposition, piezo deposition, tether release, vacuum packaging)
7. **Scaling laws and performance projections:** Density, SNR, mode count, energy budget as functions of device geometry

All of these are described in sufficient detail for a person skilled in MEMS device fabrication to understand and reproduce the invention. That is the legal standard for a provisional.

---

## What It Does NOT Protect

- Features you invent *after* filing and do not describe in the specification
- Broad abstract ideas that are not tied to the specific physical implementation
- Anything described in prior art that existed before your filing date

For inventions made during Phase 1 experiments, you can file **additional provisional applications** (each costs $65) to capture new features. When you file the non-provisional within 12 months, you can claim priority to all of them.

---

## Recommended Next Steps After Filing

1. **Get a patent attorney** to review and draft the non-provisional before the 12-month deadline. Budget ~$5,000–$15,000 for a competent patent prosecution attorney in the MEMS/semiconductor space. Some do flat-rate provisionals-to-nonprovisional conversions.
2. **Consider a PCT (international) filing** within 12 months if you want patent protection outside the US ($1,400–$4,000 depending on search authority).
3. **Keep detailed lab notebooks** during the BOM experiments — these are evidence of reduction to practice if priority is ever contested.
4. **Do not publicly disclose** anything not already in the specification *before* filing. (Your GitHub repo and website are already public, which is fine — they support your case for prior art and inventorship, and the US gives a 1-year grace period from first public disclosure to file.)

---

## Grace Period Note

Under US patent law (35 U.S.C. § 102(b)(1)), you have a **one-year grace period** from the date of your own public disclosure to file a patent application. Your GitHub repo's first public commit was **March 4, 2026**, so your hard deadline is **March 4, 2027**. Filing the provisional NOW stops that clock by establishing a priority date. Do not wait.

---

## Checklist Before Mailing

- [ ] PTO/SB/16 cover sheet — filled and signed
- [ ] PTO/SB/15A micro entity certification — filled and signed
- [ ] Printed specification (paper/v18.pdf, two-column version)
- [ ] Printed drawings (16 figures from paper/figures/, one per page)
- [ ] Check for $65.00 payable to "Director of the United States Patent and Trademark Office"
- [ ] Certificate of Mailing statement — signed and dated
- [ ] Keep a complete photocopy of everything you mail
- [ ] Use USPS Priority Mail or Express Mail with tracking number

---

## Files in This Folder

| File | Purpose |
|---|---|
| README.md | This document — filing instructions |
| CLAIMS_DRAFT.md | Optional draft claims for reference (not required for provisional) |

The specification and drawings are the existing files at `paper/v18.pdf` and `paper/figures/*.svg`. Do not duplicate them here — just print from those locations.
