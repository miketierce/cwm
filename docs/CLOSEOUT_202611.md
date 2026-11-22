# Project close-out, November 2026

**Status: archived.** This repository holds the records of Coherent Wave Memory (CWM), an independent project that ran from March to November 2026. It asked whether a fused-silica plate driven by glued piezoelectric discs could store information and compute with it. It cannot. The plate is a stable, linear, moderately damped acoustic filter. Nothing here should be cited as evidence of memory, computation, a physical unclonable function or a MEMS advantage.

The findings below come from an independent review in November 2026 that read every paper version, diary and plan, re-derived the headline numbers from the stored data, and then tried to refute its own conclusions. No finding was overturned. Lab diaries and old papers are kept unchanged as the historical record; corrections live in this note, in status notices at the top of the summary documents, and on the public site.

## What the bench showed

October 2026, Plate D (100 x 100 x 1 mm fused silica, glued 10 mm PZT discs, Raspberry Pi Pico tone source through 220 ohm, OPA2134 preamp, 8-bit PicoScope 2204A). Plans and scripts were hashed before data (local timestamps only), with plate-free loopback, dummy-receiver and quiet controls. One plate, one fixture, one week. Records: `docs/lab_diary_2026102*.md`, `docs/SESSION_HANDOFF_20261029.md`, `data/results/k_eff/`.

1. **Linear and repeatable.** At frequency-matched points, superposition holds to a median 1.2 to 2.0% within a session, against 0.8 to 1.6% for the plate-free loopback; 7 to 8% held out to a later session. The preregistered three-session test (FT-1) was scored INCONCLUSIVE and left that way; a wrong assumption in its own preregistration (drive harmonics offset from grid points by up to 52 Hz) was found afterwards. No nonlinearity above the instrument floor (about -40 dBc).
2. **Ring-down.** Decay times about 0.9 to 1.7 ms; Q roughly 136 to 635; ring-down agrees with linewidth within 20% in 9 of 10 usable windows.
3. **A receiver null is not a modal null.** A -44 dB (and -66 dB) two-transmitter null at the receiver left the plate ringing at about 47% (and 25%) of single-transmitter level after the drive stopped. Interference "erase" changes the readout, not the plate.
4. **Termination.** Opening the transmitter terminals lengthens decays by a median 6.5% (-1% to +15%) and raises mode frequencies by 21 to 40 Hz (218 to 439 ppm), reversibly. Terminal capacitance is about 4.1 nF, not the 1.2 nF used in earlier documents. Q is mechanical; the earlier "Q of 2,000 to 2,760" (fits with R squared below 0.1) is ruled out.
5. **Stability.** Mode frequencies repeat to about 3 to 13 ppm between sweeps when untouched and move about +25 to +90 ppm per degree C (die-sensor temperature); the transfer function changes 3 to 10% between sessions; touching a lead leaves percent-level steps.
6. **No memory, no computation.** Nothing persists beyond the 1 to 2 ms ring; hardware NARMA-10 fails (NMSE about 1.05 to 1.08).
7. **Change detection (April data, post hoc).** Fine spectral structure of the same undisturbed plate correlates 0.80 to 0.99 over 2 hours to 5 days, at most 0.58 between different plates, and 0.25 to 0.55 after handling or putty changes. This supports change detection in a fixed mount, not unclonable identity.
8. **Mode crowding (estimate).** About 3 flexural modes per kHz against linewidths of 124 to 330 Hz, so most "modes" at the receiver are overlapping groups.

## Corrections to earlier claims

| Claim (where it appeared) | What the data show |
|---|---|
| 100% classification, 80/80, 193 sigma (v19r, readme, site) | Test T1.3 (26 May): one plate, four single drive tones, decided by the largest of four FFT bins. It identifies the generator setting. 193 is a tone-over-floor ratio. The protocol printed in v19r section 5.1 belongs to a different, unsaved run. |
| 8 levels x 4 modes = 4,096 zero-error states | 8 to the power 4 from 32 single-tone conditions. No multi-tone state was driven; the joint test scored 8 of 1,280 and was replaced by a Monte Carlo draw. The only stored two-tone test (21 June) gives about 79% per tone and 62% on 64 joint states. |
| Those May results on the current wiring | Taken on the earlier generator and breadboard wiring, before the grounds were separated. |
| CHSH S = 2.73 to 2.83 | Computed in software from four FFT magnitudes; S = 2*sqrt(1 + C^2), a restatement of two receiver contrast ratios. All 7,260 pairs in the sweep exceed 2; the five reported are the top five; shuffling one channel reproduces them. 2.73 was never computed. |
| 0.22% drift over 16.5 million cycles | A 300 s run, five readings of one tone, on a clipped signal. |
| PZT-lifted null, zero feedthrough | One frequency, one afternoon, signal 6.6 to 8.8 times noise, no stored data. |
| 767 usable modes | 212 distinct bins counted once per transmitter; mostly an artifact of the tone generator's frequency grid against the census script's search window. |
| Associative recall 4/4, Boolean 100% (April rods) | Fixed by the scoring rules: constant or random magnitudes give the same scores. |
| NARMA-10 hybrid gain | Reproduced with no glass; the drive code peak-normalises the summed waveform. |
| Partial-query completion, 84% vs 47% (June) | The "wire" was not a wire, the hidden input stayed in the features, and a per-capture normalisation leaked the drive state. A dimension-matched digital baseline ties or wins. |
| Electronic erase, 98.9% (3 June) | Both generator pins were summed into one transducer: cancellation of drive voltage. |
| Rod prototype: 98.5 dB, Q = 10,000, 180 ms ring-down, Rayleigh within 2% (papers v11 to v18, book) | Calculated values written as measurements. No capture, driver or lab note predates 4 to 6 April 2026; the first rods did not reproduce them. The same documents state elsewhere that quantitative claims come from simulation code. |
| MEMS density, energy, speed (v15 to v18) | Projections that fail arithmetic checks by orders of magnitude. No device was built. |

The project had already retracted "the plate computes", bench reservoir computing, the 17,170x energy claim, ferrofluid substrates and quantum framing.

## What was changed in November 2026

- Status notices at the top of `readme.md`, `INDEX.md`, `paper/README.md`, `paper/CLAIMS_STATUS.md`, `paper/v19r.md` and `docs/WATER_COOLER_SUMMARY.md` (the previous summary is archived as `archive/tmp/WATER_COOLER_SUMMARY_pre_closeout_20261120.md`).
- `tests/test_mems_q_model.py`: the stale count of Q components corrected from 5 to 6 (model unchanged).
- `tools/md2pdf.py.bak` removed; `tools/thouhts.md` moved to `archive/tmp/`.
- The public site (separate repository `cwm-site`) was rebuilt as a static archive with a corrections table; the book, build guide and letter were withdrawn; the backend was removed. The book repository (`cwm-book`) carries a withdrawal notice.

## Known errata not edited in place

- Diaries and planning documents before 29 October quote a 1.2 nF transducer capacitance (about 2 kohm at 60 kHz); the measured value is at least 4.1 nF (about 650 ohm at 60 kHz).
- `docs/OFFLINE_REANALYSIS_DEBRIEF.md`, `docs/PATH_SUM_FT0_EXISTING_DATA_NOTE.md`, `docs/FULL_POTENTIAL_WORKLIST.md`, the June architecture and frontier documents and `docs/lab_diary_20260620.md` still describe partial-query completion, the E9 erase, CHSH as a headline result or the mass write as verified. Read them against the table above.
- Unmerged remote branches (July to November 2026) predate or ignore the October results; the `experiment/holographic-partial-view` branch rests on April scoring artefacts.
- Eight tool scripts embed the retired website's public web API key and post to its retired backend: `tools/associative_recall_hw.py`, `boolean_compute_hw.py`, `cim_suite_hw.py`, `cwm_lab.py`, `firestore_submit.py`, `nearest_neighbor_hw.py`, `pre_teardown.py`, `run_rod_experiments.py`. They will fail harmlessly once the backend is gone.

## Reproducing

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. python -m pytest tests -p no:cacheprovider -q
```

Run pytest on `tests/` only: from the repository root it also collects bench scripts in `tools/` whose names start with `test_`, and those try to open the oscilloscope.

The tests check the simulation code against itself; they are not physical validation. October raw captures (`data/raw/k_eff/`) are git-ignored and backed up outside the repository; their hashes are in each test's `log.jsonl`.

## Owner checklist

- [ ] **Patent.** The provisional (filed 31 March 2026) lapses on **31 March 2027** unless a non-provisional or PCT application claiming it is filed. Anything new added to a fresh US filing must be filed by **4 March 2027**, one year after the first public commit. Log in to Patent Center, confirm the filing date and fee, and download the as-filed specification (the local copy does not match the receipt's hash). If it lapses, change remaining "patent pending" wording to "a provisional application was filed on 31 March 2026 and has expired".
- [ ] **Hosting history.** The filing-day commit `3155d6d` (receipt with a postal address) was briefly on GitHub before a forced push; ask GitHub support to purge it if it is still retrievable by hash.
- [ ] **Website.** Rotate the Mailgun API key (it remains in the site's git history), revoke the Firebase service-account key, deploy the static site and deny-all rules, delete the old server function, and decide what to do with stored emails, submissions and uploads. Steps are in the site's README.
- [ ] **Licence.** There is no LICENSE file; `pyproject.toml` says MIT. Choose one (for example MIT for code, CC BY 4.0 for text and data) before archiving.
- [ ] **Data deposit.** Consider depositing the October raw data, scripts and diaries on Zenodo for a DOI and a third-party date.
- [ ] **Personal data.** `data/results/lab/users.json` and `data/results/lab/faces.json` hold first names and an image thumbnail from April tests; decide whether to keep them public.
- [ ] Commit the untracked `docs/SESSION_HANDOFF_20261029.md` and push the five 29 October commits.
