---

## 5. Scaling Laws

The macro prototype demonstrates the physics. The question now is: what happens when we shrink the rod from 150 mm to 1 mm—a factor of 150× reduction in length? Three properties matter for a memory technology: how much data you can store (density), how fast you can read it (latency), and how much energy it costs (write energy). We need to understand how each scales with rod length.

### 5.1 SNR Scales Linearly with Length

From the derivation in Appendix A, the signal-to-noise ratio depends on rod length as:

$$\text{SNR} = \frac{\rho \pi^3 v^2 A^2}{16 \beta^2 k_B T} \cdot L = c \cdot L$$

where $c = 5.06 \times 10^7$ m⁻¹ for borosilicate at standard conditions ($\rho = 2{,}230$ kg/m³, $v = 5{,}640$ m/s, $A = 1$ nm, $\beta = L/d = 25$, $T = 300$ K).

The physical reason is straightforward: a shorter rod has less mass, so its effective spring constant is lower, so it stores less elastic energy at the same displacement amplitude. Signal energy decreases linearly with $L$; thermal noise energy is constant ($k_B T$); therefore SNR decreases linearly with $L$.

For a 1 mm rod: $\text{SNR} = 5.06 \times 10^7 \times 10^{-3} = 5.06 \times 10^4$, or 47 dB. This gives $b = \frac{1}{2}\log_2(1 + 50{,}600) = 7.8$ bits per mode. Reduced from 16.4 bits at macro scale, but still a substantial information capacity per mode.

For a 0.5 mm rod: SNR $= 2.53 \times 10^4$ (44 dB), giving 7.3 bits/mode. The returns diminish slowly because information scales as the _logarithm_ of SNR.

### 5.2 Mode Count Is Size-Independent

This is the most counterintuitive and most important scaling result. The formula $n_{\max} = \lfloor 1/(2\alpha\Delta T) \rfloor$ contains no $L$. A 1 mm rod supports the same 9,380 modes as the 150 mm prototype.

Why? Because both the mode spacing and the thermal shift scale identically with $L$. The mode spacing is $\Delta f = v/(2L)$—smaller rods have wider spacing. The maximum usable frequency before thermal shifts cause mode overlap is $f_{\max} = v/(2L\cdot 2\alpha\Delta T)$—also proportional to $1/L$. The ratio $f_{\max}/\Delta f = 1/(2\alpha\Delta T) = n_{\max}$ is independent of $L$.

Physically: a smaller rod has fewer modes per unit frequency (they are more widely spaced), but the usable frequency range is proportionally wider (because the thermal shift per mode is smaller relative to the spacing). These two effects cancel exactly.

### 5.3 Density Scales as $1/L^2$

Combining the two results above, we can derive how storage density scales with rod length. The total bits per rod is:

$$B(L) = n_{\max} \cdot \frac{1}{2}\log_2\!\big(1 + c \cdot L\big)$$

The volume of a single rod (with aspect ratio $\beta = L/d$) is:

$$V = \frac{\pi}{4} d^2 L = \frac{\pi L^3}{4\beta^2}$$

So the density is:

$$\rho_{\text{bits}} = \frac{B(L)}{V} = \frac{2\beta^2 n_{\max} \log_2(1 + cL)}{\pi L^3}$$

For $cL \gg 1$ (which holds for all practical rod lengths above ~100 nm), $\log_2(1 + cL) \approx \log_2 c + \log_2 L$. The logarithm varies slowly, so the dominant scaling is:

$$\rho_{\text{bits}} \sim \frac{\log_2 L}{L^3} \approx \frac{1}{L^2} \quad \text{(effective scaling)}$$

The key implication: **making rods smaller always increases density**, even though each rod stores fewer bits (because SNR drops with $L$). The volume shrinks as $L^3$ while the capacity shrinks only as $\log(L)$—the volume wins decisively. This is why CWM gets more competitive, not less, as it scales to MEMS dimensions.

### 5.4 Crossover Points

We can now compute the rod lengths at which CWM matches the density of existing memory technologies:

| Crossover        | Rod length | CWM density    | Incumbent density |
| ---------------- | ---------- | -------------- | ----------------- |
| CWM = DRAM       | 2.1 mm     | 10 Gbit/cm³    | 10 Gbit/cm³       |
| CWM = PCM        | 1.0 mm     | 95 Gbit/cm³    | 64 Gbit/cm³       |
| CWM = NAND Flash | 0.45 mm    | 1,000 Gbit/cm³ | 1,000 Gbit/cm³    |

All three crossovers fall within standard MEMS fabrication range (0.1–5 mm features). The 1 mm reference design of this paper sits between the DRAM and Flash crossovers—at 95.5 Gbit/cm³, it is 10× DRAM and competitive with PCM.

<div class="cwm-thumb">
<img src="figures/fig5_scaling.svg" alt="Figure 5: Scaling from macro to MEMS"/>
<p><strong>Figure 5.</strong> (a) Size comparison at three scales: the 150 mm macro prototype (0.04 Gbit/cm³), the 1 mm borosilicate MEMS rod (95.5 Gbit/cm³, 2,400× denser), and a 0.5 mm fused silica array (1.4 Tbit/cm³, 35,000× denser). All designs share the same thermally stable mode physics. (b) Log–log density vs. rod length showing CWM crossing DRAM at 2.1 mm, PCM at 1.0 mm, and NAND Flash at 0.45 mm—all within standard MEMS fabrication range.</p>
</div>
