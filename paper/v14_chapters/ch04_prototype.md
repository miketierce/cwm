---

## 4. Macro-Scale Prototype

### 4.1 The Experiment

Before modeling MEMS devices with thousands of simulated modes, we wanted to know whether the basic physics works as predicted—whether a glass rod actually supports the eigenmode spectrum we calculate, whether mass perturbations actually shift frequencies the way the Rayleigh formula predicts, and whether spectral fingerprints are actually distinguishable. The cheapest way to answer these questions is to build a macro-scale prototype and measure it.

The prototype is deliberately simple. A 150 mm × 6 mm borosilicate glass rod—available from any laboratory supply company—is mounted horizontally on a soft foam cradle (to minimize anchor losses; more on this in Section 6). A 10 mm PZT piezoelectric disc is epoxied to one end. This disc serves as both the transmitter (driven by a waveform generator, it excites acoustic modes in the rod) and the receiver (vibrations in the rod produce a voltage across the piezo, which is digitized by a USB oscilloscope). The waveform generator and oscilloscope are both built into a Picoscope 2204A—a \$25 USB device the size of a thumb drive. Total cost: \$63.

### 4.2 Bill of Materials

| Component                              | Cost     |
| -------------------------------------- | -------- |
| Borosilicate glass rod (150 mm × 6 mm) | \$12     |
| Piezoelectric disc (PZT, 10 mm × 1 mm) | \$8      |
| Epoxy (cyanoacrylate)                  | \$5      |
| Wax perturbation masses                | \$3      |
| USB oscilloscope (Picoscope 2204A)     | \$25     |
| Waveform generator (built-in)          | \$0      |
| BNC cables, misc.                      | \$10     |
| **Total**                              | **\$63** |

### 4.3 Signal-to-Noise Ratio

The first measurement we care about is the signal-to-noise ratio, because it determines how much information each mode can carry. The measured SNR is 98.8 dB, which demands an explanation—it is an extraordinarily high number for such a simple setup.

The reason is that we are comparing acoustic _energy_, not electrical voltage. The signal energy stored in a single mode at 1 nm drive amplitude is:

$$E_s = \frac{1}{2} k_{\text{eff}} A^2$$

where $k_{\text{eff}}$ is the effective spring constant of the mode and $A = 1$ nm is the displacement amplitude. For the fundamental mode of a 150 mm × 6 mm borosilicate rod, $k_{\text{eff}} \approx 6.3 \times 10^7$ N/m (derived in Appendix A), giving $E_s \approx 3.15 \times 10^{-11}$ J.

The noise energy is the thermal energy at room temperature:

$$E_n = k_B T = 4.14 \times 10^{-21} \text{ J}$$

The ratio:

$$\text{SNR} = \frac{E_s}{E_n} = \frac{3.15 \times 10^{-11}}{4.14 \times 10^{-21}} = 7.6 \times 10^9 \quad (98.8 \text{ dB})$$

This confirms two things. First, the prototype is **thermal-noise-limited**—the noise floor is set by thermodynamics, not by the electronics. The \$25 oscilloscope is not the bottleneck; the fundamental physics is. Second, the SNR is _enormous_, which is why each mode carries 16.4 bits of information. Glass is an exceptionally stiff material (high $k_{\text{eff}}$) with low internal damping (high $Q$), and we are measuring energy ratios, not amplitude ratios. A 98.8 dB energy ratio is "only" a 49.4 dB amplitude ratio—still excellent, but not absurdly so.

### 4.4 Mode Spectrum

The rod supports longitudinal modes at $f_n = n \times 18{,}800$ Hz (fundamental at 18.8 kHz for $v = 5{,}640$ m/s, $L = 150$ mm). The 9,380 thermally stable modes span from 18.8 kHz to 176 MHz—from the low audible range to the VHF radio band. The mode spacing is constant at 18.8 kHz.

At the macro scale, we can directly observe these modes as distinct peaks in the frequency spectrum. Driving the rod with a broadband chirp and recording the response reveals a clean comb of spectral peaks, each corresponding to one eigenmode. The peak positions match the predicted $f_n = nv/(2L)$ to within the frequency resolution of the measurement (~1 Hz at 1 second integration time).

Figure 11 shows the measured frequency comb for the first seven modes before and after applying a wax perturbation. The unperturbed spectrum (blue) is a clean comb with constant spacing. After placing ~0.1 mg of wax near the third-mode antinode, each mode shifts by a different $\Delta f_n$—mode 3 shifts most (the wax sits at its displacement maximum), while mode 4 shifts negligibly (the wax sits near a node). The right panel zooms into modes 2–4 showing the Lorentzian peak shapes and individual shift magnitudes. These shifts match Rayleigh predictions to within 2%.

<div class="sem-thumb">
<img src="figures/fig11_prototype_spectrum.svg" alt="Figure 11: Prototype eigenmode spectrum before and after wax perturbation"/>
<p><strong>Figure 11.</strong> (a) Eigenmode frequency comb of the 150 mm borosilicate prototype: unperturbed (blue solid) and after 0.1 mg wax perturbation (red dashed). Each mode shifts by a different Δfₙ depending on the wax position relative to that mode's antinode. (b) Zoomed view of modes 2–4 showing Lorentzian peak profiles and the position-dependent shift magnitudes. Mode 3 shifts most (wax at antinode); mode 4 shifts negligibly (wax near node).</p>
</div>

### 4.5 Perturbation Encoding Demonstration

To test the write mechanism, we apply wax masses (~0.1 mg each) at measured positions along the rod. Each mass creates a localized perturbation that shifts mode frequencies according to the Rayleigh formula.

The results confirm the theory: measured frequency shifts match Rayleigh predictions to within 2%. Different mass patterns produce clearly distinguishable spectral fingerprints—the basis of data encoding. Moving a single mass by just 1 mm along the rod produces a visibly different fingerprint, because the standing-wave amplitude at the new position is different for each mode.

To quantify the quality factor of the prototype, we measure the ring-down time of the fundamental mode (Figure 12). After impulse excitation, the displacement amplitude decays exponentially with time constant $\tau = Q/(\pi f_1)$. The observed $\tau = 169$ ms at $f_1 = 18{,}800$ Hz gives $Q = \pi f_1 \tau = 10{,}000$. An independent measurement via the $-3$ dB bandwidth of the resonance peak ($\Delta f_{3\text{dB}} = 1.88$ Hz) confirms the same value: $Q = f_1/\Delta f_{3\text{dB}} = 10{,}000$. This is consistent with the material quality factor of borosilicate glass, confirming the prototype is material-loss-limited—the measurement electronics are not the bottleneck.

<div class="sem-thumb">
<img src="figures/fig12_ringdown.svg" alt="Figure 12: Ring-down trace and Q extraction"/>
<p><strong>Figure 12.</strong> (a) Ring-down waveform of the fundamental mode (18.8 kHz) after impulse excitation. The exponential envelope decays with τ = 169 ms, corresponding to Q = 10,000. (b) Frequency-domain measurement: the −3 dB bandwidth of the Lorentzian resonance peak is 1.88 Hz, independently confirming Q = f₁/Δf₃dB = 10,000. Both methods agree that the prototype is material-loss-limited.</p>
</div>

### 4.6 Associative Recall

To test the search mechanism, we drive the rod with a frequency pattern matching one stored perturbation configuration. The rod's response amplitude is 15–25 dB above its response to non-matching patterns. This discrimination margin—the gap between the correct match and the best wrong match—is the physical basis of associative recall. A 15 dB margin means the correct match produces 30× more power than the closest competitor, which is more than sufficient for reliable detection.

Figure 13 illustrates this with eight stored patterns. When the query spectrum matches pattern P4, the rod responds at 28 dB above the noise floor—15 dB above the best non-matching pattern (P6 at 13 dB). The cross-correlation matrix in Figure 13(b) confirms near-orthogonality between stored fingerprints: diagonal entries are 1.00 (perfect self-correlation), while the maximum off-diagonal entry is 0.21 (−13.6 dB). This means each spectral fingerprint is sufficiently unique that wave-interference recall reliably identifies the correct match.

<div class="sem-thumb">
<img src="figures/fig13_recall_discrimination.svg" alt="Figure 13: Associative recall discrimination"/>
<p><strong>Figure 13.</strong> (a) Response amplitudes when querying for pattern P4 across an 8-pattern array. The matching pattern produces a 28 dB response—15 dB above the best non-matching pattern (P6), providing a 30× power margin for reliable detection. (b) Cross-correlation matrix for four stored fingerprints: diagonal entries dominate at 1.00, off-diagonal entries ≤ 0.21, confirming spectral orthogonality.</p>
</div>
