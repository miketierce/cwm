The user wants to build the 8-bit token ESN experiment, starting with Option 1 (D and E only, each has exactly 8 modes). Let me plan this out:

Build the 8-bit ESN tool (based on v2, but with N_INPUT_BITS=8, only plates D and E)
Run it on hardware
If results aren't favorable, move to Option 2 (all-plate combined encoder) and then Option 3
Let me first read the v2 tool to understand the structure, then build v3.

Let me read the v2 tool first.

Completed: Run v2 per-plate calibration (7/13)

Read plate_sequence_esn_v2.py, lines 1 to 120

Read plate_sequence_esn_v2.py, lines 120 to 300

Read plate_sequence_esn_v2.py, lines 300 to 560

Read plate_sequence_esn_v2.py, lines 555 to 640

Read plate_sequence_esn_v2.py, lines 640 to 730

Read plate_sequence_esn_v2.py, lines 730 to 770

Read plate_sequence_esn_v2.py, lines 770 to 795

Now I have a thorough understanding of the v2 tool. Let me build v3 for 8-bit tokens on plates D and E only. Key changes needed:

N_INPUT_BITS = 8, N_TOKENS = 256

Only calibrate plates D and E (both have 8 modes)

All 8 modes per plate are carriers (no min(4, n_modes) limit)

software_poly needs to expand 8 bits with degree 4 → 163 features (incomplete!)

Calibration: 256 tokens × 8 reps × 2 plates = 4096 captures ≈ ~27 min

For polynomial expansion, I should use degree 2 or 3 to keep feature dimensions reasonable for the ESN, since degree 4 creates too many terms.

The raw plate features give me 16 dimensions (8 modes × 2 plates), while the software polynomial approach yields 163 features — but here's the tension: with 163 features I can't represent all 256 tokens uniquely since the degree-4 polynomial basis is incomplete, missing the higher-order cross terms.

Let me verify the math: for 8-bit binary input, the complete polynomial basis needs all 256 terms, but degree-4 only captures 163 of them (1 + 8 + 28 + 56 + 70). The plate's nonlinear response might actually capture those missing higher-degree interactions, which could give it an advantage over the truncated polynomial representation.

Now I'm considering the architecture constraints—the 163-dimensional polynomial input might be too large for a 200-unit ESN, especially since I saw in v2 that high-dimensional inputs degraded performance. I could either increase the ESN hidden size for 8-bit inputs or stick with lower polynomial degrees to keep the feature space manageable. Looking at a simpler approach with just the D and E plates: each would encode 8 bits using its 8 modes, giving 16 raw dimensions when concatenated. Individual plates with polynomial features would then be much smaller—36 dimensions at degree 2 or 92 at degree 3.

The real bottleneck is that with 256^4 possible sequences but only 300 samples, the ESN needs to generalize across a massive space, and asking 200 hidden units to distinguish 256 output classes might not be enough capacity.

Looking at the ridge regression readout more carefully: with 225 training examples and 51,200 parameters to learn (200×256), I'm severely underdetermined compared to the 16-token case which had only 3,200 parameters. I need either significantly more sequences or a simpler classification target to make this work reliably.

The bit-wise approach is elegant — instead of predicting which of 256 tokens appears at each position, I'd train 8 independent binary classifiers, each learning just 400 parameters from 225 samples. That's much more tractable. Alternatively, I could scale up to 2000 sequences so each token appears roughly 31 times instead of just 4-5 times, which would give the ridge regression enough data to work with.

Actually, the per-bit method is cleaner scientifically. It's more tractable than 256-class prediction, reveals which specific bits the plate captures, and stays directly comparable to the 4-bit results. I'll use that as the primary metric with the 256-class approach as a secondary check. For the dataset, 1000 sequences (750 train, 250 test) with per-bit prediction should work well — that gives each token around 15-16 appearances on average. Now I need to figure out the calibration time across all the tokens and plate combinations.

At 0.4 seconds per capture, the full calibration run should take roughly 27 minutes, which is manageable. I'm going to build v3 now, keeping most of v2's structure but scaling up the reservoir to 300 units for the higher-dimensional task, using all 256 tokens across plates D and E, and implementing per-bit readout as the main evaluation metric. The polynomial features will expand to 163 dimensions when applied to 8 bits. Building the tool now...

Thinking through the polynomial expansion strategy—D and E each have 8 modes, so concatenating raw features gives 16 dimensions, degree-2 expansion pushes that to 72, and degree-3 gets unwieldy. Since the glass itself introduces nonlinear effects, the raw features probably already capture higher-order interactions implicitly, so I'll keep the design simple and stick with what worked in v2 but parameterized for 8-bit tokens. Writing the v3 implementation...

Key parameters: 256 unique tokens, D+E plates with 8 carriers each, per-bit readout alongside a 256-class classifier, 1000 sequences for coverage, ESN hidden layer around 200-300 units, and calibration across 256 tokens with 8 reps per plate. That's 4096 total captures across both plates—about 27 minutes at 0.4s per capture, which is manageable.

There's a quantization concern though: 8-bit unsigned values (0-255) with 8 simultaneous sinusoids means each tone gets roughly 16 effective levels after normalization, which is tight but workable.

The v2 tool's existing multitone function should handle this—it just hasn't been tested with 8 simultaneous tones yet, so I'll run it and see what the hardware produces. With N_CALIB_REPS=8 and N_AVG=4, each token capture already includes 4 internal averages, and taking the mean across 8 repetitions should further reduce noise, especially combined with baseline subtraction. For evaluation, I'm planning two metrics: per-bit accuracy treating each of the 32 binary classifiers (8 bits × 4 positions) independently with 50% random baseline, and token accuracy as a 256-class prediction problem at each position.

The 256-class approach is tight though—with 750 training samples across 256 classes per position, each class appears only ~2.9 times on average, and some classes might not appear in training at all. Ridge regression with hidden=200 dimensions can work with 750 samples, but the sparsity of class representation is the real bottleneck. I need to calculate whether the probability of missing classes is acceptable or if I should stick with the per-bit approach instead.

Using the coupon collector problem, I can estimate how many sequences are needed to see all 256 tokens at each position with high confidence. The math suggests around 1600 sequences minimum to reliably capture all classes. So I'll bump up to 2000 total sequences—1500 for training and 500 for testing—which should give me enough coverage at each position.

Now I'm reconsidering whether the 256-class approach is even necessary. Since we're working with 8-bit tokens, a per-bit prediction strategy might be more natural and interpretable. Each bit could be predicted independently, and then token accuracy would just be the product of per-bit accuracies if the bits are uncorrelated. This also lets me directly assess whether the plate captures information for each individual bit. Looking at the polynomial baseline, the degree-4 features should handle most bit interactions, though higher-order terms might be needed for some bits.

For the reversal task specifically, the structure is elegant: output bit b at position p simply equals input bit b at position (seq_len-1-p). The ESN's job is to learn which token was at which position and extract the right bit from it. Since the polynomial features already include all individual bit values as degree-1 terms, linear readout should trivially predict bits from those features. The real question is whether the ESN's recurrent dynamics encode enough positional information to reconstruct which token appeared where.

For the readout strategy, I could either train one ridge model per (position, bit) pair, or train one model per position that outputs all 8 bits at once—the latter seems cleaner. The key difference from the 4-bit case is that with 16-class softmax readout I'm directly reconstructing tokens, but with per-bit readout I'm predicting individual bits across the sequence.

Per-bit readout is much more parameter-efficient: 8 binary classifiers per position use only about 3% as many weights compared to 256-class readout, which matters when data is limited. I'll go with per-bit as the primary metric, use 256-class as a secondary check if I have enough sequences, and set N_SEQUENCES to 2000. For the implementation, I'll extract binary targets by bit-shifting and masking each token at each position, then apply ridge regression with those binary labels.

Setting up the code structure now... Looking at the timing: 256 tokens × 8 reps × 2 plates gives 4096 captures, which at 0.40s each works out to about 27 minutes—totally manageable. I want to set up a comparison between degree-4 and degree-8 polynomial features against the raw plate features to see if the hardware approach outperforms the incomplete software model.

Writing the experiment code... I need to set up per-bit binary classifiers using ridge regression with a 0.5 threshold, then compute token accuracy by checking if all 8 bits match. For the software baselines, I'm comparing degree-4 polynomials (163 features) against degree-8 polynomials (256 features) and raw bit features to see if the plate's nonlinear dynamics exceed what polynomial models can capture.

Now for the plate features themselves, I'm considering multiple representations: raw mode amplitudes from D and E separately, concatenated versions, and polynomial expansions up to degree 2 that give me 36 dimensions per plate or 72 combined. For Option 2, I'd drive all five plates in parallel using the same 8 carrier frequencies (likely D's modes) and then measure which plates respond to those carriers.

The key insight is that with 8 carriers spanning D's full range of 30-95 kHz, I'd probably excite more cross-plate modes than the 12 out of 31 we saw with just 4 carriers in v1. But this reintroduces the selectivity problem—only modes near those frequencies will respond. I think the cleaner approach is to focus on Option 1 first, where I treat D and E independently with their own 8-bit encodings, and see if that gives good results before exploring the more complex cross-plate scenario.

So here's what I'm building: a calibration pipeline that loads the mode frequencies for both plates, then systematically drives each plate with all 256 possible 8-bit combinations, capturing spectra for each one. During feature extraction, I'll baseline-subtract against the zero token, then pull out the 8 mode amplitudes with log scaling and z-scoring to normalize across the dynamic range.

For the ESN experiment, I'm running 2000 random 4-token sequences through the network and evaluating both per-bit classification accuracy and exact token recovery. I'll compare against a few baselines—the polynomial-expanded versions from v2 plus a memoryless classifier—to see how much the reservoir actually helps. Now I'm going to implement this, reusing the helper functions from before and focusing on the experiment loop itself.

Writing experiment code... I'm scaling up the sequence count to maintain the token-to-sequence ratio from the previous version, calculating that around 3000 sequences would give each token enough training examples while keeping the ESN computation manageable—though I'm second-guessing the exact number now.

Looking at the data size implications: with 256 tokens, 8 repetitions, 2 plates, and 31 spectral values per readout, I'm getting over 127,000 float values total, which is fine. But I should optimize the readout frequencies—when reading plate D, I only need its 8 modes, and same for plate E, rather than loading all 31 modes unnecessarily.

The \_capture_spectrum function extracts magnitudes at specified frequencies from a single FFT, so I can pass just D's 8 modes when reading D and E's 8 modes when reading E. I'm leaning toward keeping the v2 approach of one combined readout_freqs list (16 modes for D+E), capturing the full spectrum once, then extracting the plate-specific frequencies afterward. Though I need to check if D and E's mode frequencies overlap first.

Looking at the actual frequencies, there's some close pairs: D's 29925 Hz vs E's 29975 Hz (50 Hz apart), D's 49625 Hz vs E's 49675 Hz (50 Hz apart), and D's 94675 Hz vs E's 94775 Hz (100 Hz apart). At 24 Hz FFT resolution these are distinguishable, but there could be cross-talk when driving all plates in parallel. However, during per-plate calibration we drive one plate at a time with the mux selecting only that plate's sense PZT, so the other plate's modes won't be excited anyway.

Since the mode bandwidth is only 3-5 Hz at Q=10K, driving plate D at 29925 Hz won't significantly excite plate E's mode at 29975 Hz. This means I can just use each plate's own mode frequencies as readout frequencies during its calibration—no cross-talk problem. That does change the data structure though: instead of all plates sharing the same 31 readout frequencies like in v2, each plate now has its own set of 8 mode frequencies, and the calibration stores spectra extracted at those plate-specific frequencies.

Now I'm implementing the code to test whether glass plate resonances can capture information that degree-4 polynomials miss when working with 8-bit tokens. I'm checking which plate modes fall within the resonance bandwidth of D's carrier frequencies—D's modes span 29925 to 94675 Hz, and with a Q factor around 10,000, the bandwidth is only a few Hz, so most cross-plate modes are too far off to couple effectively. Let me map out which modes might actually respond to each D carrier. — outside bandwidth.

So C has one mode that matches D exactly at 49625 Hz, but that's just one of many modes across both plates, meaning most of the response would still be noise. Option 2 with D's carriers doesn't offer much improvement over the original approach since the mode frequencies are too spread out to find good multi-plate matches. I should focus on Option 1 with per-plate D and E calibration, and maybe include a lighter version of Option 2 as an alternative if needed.

Actually, I could do a simpler "all-plate mode" using 8-bit tokens across all five plates where each plate encodes only the bits it can represent based on its mode count, then pad the rest. But this is getting complicated. Let me just build Option 1 cleanly first since that's what the user asked for, and iterate from there if the results aren't good enough.

Now I'm deciding on the scoring approach...

I'll track three metrics: per-bit accuracy across all positions and bits as the main measure, exact-match accuracy where all 8 bits must be correct for a position, and per-bit breakdowns by position to see which ones are hardest to remember. For the sw_poly comparison, I'm looking at degree-4 on 8 bits as the incomplete baseline, degree-8 as the complete ceiling, and raw 8-bit readout, all using the same ESN framework with per-bit readout.

Now I need to implement this. I'm realizing the polynomial expansion needs degree limits—for 8 modes, degree 4 gives 163 features total including the constant term, while degree 2 is only 36 and degree 3 is 92. I should verify my interaction expansion function includes the constant and handles the feature counts correctly. I see that for ±1 inputs, squaring any element gives 1, so only distinct index combinations matter—exactly what the interaction expansion handles. With the bias term included in the hidden layer, the d=4 basis gives 163 effective features while the full d=8 basis reaches 256 features, which is enough to represent any function over the 256 tokens perfectly. Now I'm ready to start implementing.

Setting up the experiment structure with 8-bit tokens and 256 possible values, I'll keep the hardware helpers from the previous version but inline everything for clarity. The key parameters are N_INPUT_BITS=8, N_TOKENS=256, and I'm focusing on just the D+E configurations with multiple polynomial baselines at different degrees...

Defining the ESN hyperparameters that were tuned in v2, along with the plate mappings for the two hardware options. Now I'm setting up the per-bit readout function using binary ridge regression to evaluate accuracy on each bit independently.

Still writing experiment code... Writing the bit-level classification loop... I need to set up both per-bit and 256-class readout layers for comparison, then define the software baselines with their feature dimensions—raw bits, polynomial expansions up to degree 8, and the plate feature representations at various complexity levels.

For the plate features, I'm considering whether raw physical amplitudes might actually work better than polynomial expansions, since the ESN's tanh nonlinearity could capture the Duffing-like dynamics more naturally than assuming polynomial interactions. But I should stop overthinking and just implement it.

I'm also planning an --all-plates mode where I drive with D's modes but read from all 5 plates simultaneously, giving 31 total mode amplitudes as features—though most will be noise.

Actually, a better approach would be per-plate calibration with variable bit encoding: each plate gets as many carriers as it has modes, so lower-bit plates provide redundant partial views. This hybrid scheme lets me leverage the full capacity of each plate while maintaining consistency across them.

For now though, I'm just implementing Option 1 to keep things simple—D and E only with 8-carrier calibration per plate. The user wanted to start with the basic version and iterate if needed, so I'll stick with that and add the more complex modes later if they're necessary.

Now I need to figure out what's actually different between v2 and v3 to minimize the code changes...

Updating the constants... I'm simplifying the approach—just building Option 1 as the default for now, and I can add the other variants later if needed. Let me start writing the code.

Writing the experiment script... Setting up the experiment configuration with directory paths, timestamp logging, and defining which plates to use for the 8-bit test—focusing on plates D and E since they both have the required 8 resonant modes.

Now I'm establishing the token and sequence parameters for the experiment: 256 possible tokens with sequences of length 4, generating 2000 sequences for training, plus calibration and averaging settings. I'm also pulling in the ESN hyperparameters from the previous sweep—hidden layer size of 200, spectral radius of 0.9, and ridge regression alpha of 10.

Setting up the hardware interface functions... Continuing with the multitone signal generation...

I'm normalizing the buffer to prevent clipping, converting it to 8-bit unsigned integers, and then passing it to the signal generator to output the arbitrary waveform at the specified drive voltage. Now I need to set up the capture function to read back the spectrum at the target frequencies.

Setting up data capture... Still writing acquisition logic... I'm defining a function that generates polynomial interaction terms up to a specified degree by iterating through all combinations of input features and computing their products, then moving on to set up an Echo State Network class with configurable parameters like hidden dimension, spectral radius, and leak rate.

Building the ESN methods... Completing the ridge regression solver and then implementing a multiclass version that uses one-hot encoding to handle multiple output classes. Writing calibration logic... Setting up the measurement loop where I decode each token's 8 bits to determine which carrier frequencies to drive, then for each repetition I either excite the plate with a multitone signal or keep it silent, capture the resulting spectrum, and average the magnitude responses across all repetitions.

Now I'm storing the calibration data for each token and tracking progress—calculating elapsed time, capture rate, and estimating how long the remaining measurements will take across all the plates. Building the token cache...

After extracting the raw spectral features for each token and computing the log-transformed differences from baseline, I'm normalizing them with z-score standardization across all tokens. Then I'm applying polynomial expansion to create higher-dimensional feature representations, storing both the normalized raw features and the expanded polynomial versions in the cache along with their dimensionality metadata.

Now I'm setting up the experiment by initializing random sequences and splitting them into training and test sets. Still writing the ESN evaluation... Writing the multiclass comparison... Now I'm setting up the output formatting for the software baselines section, creating a table header with columns for the feature set, dimensionality, and various accuracy metrics. I'm then computing polynomial features up to degree 4 for each token and running the per-bit readout evaluation on them.

Generating baseline results... Finishing the raw bits output and moving on to evaluate plate features with per-bit readout metrics. Still writing the analysis loop... Still writing evaluation code... Still writing ensemble logic... Still writing ridge regression... Storing the ensemble results and printing the performance metrics for the D+E poly combination and the D+E poly with sw_d4 variant.

Now I'm moving into the memoryless baselines section, setting up comparisons for models that only use the last token in the sequence. Still writing the evaluation loop... Now I'm moving to the verdict section, comparing 8-bit token performance between the plate-based approaches and software implementations. I'm extracting the key metrics for the software variants and then filtering to find the best plate-only result to use as a baseline for comparison.

Printing the per-bit accuracy results... Writing comparison logic... Now I'm loading the mode census data for the target plates and verifying that plates D and E each have exactly 8 modes, then checking for any existing calibration files before proceeding. Loading calibration data and setting up hardware...

If we're doing a dry run, I load the latest 8-bit calibration file and reconstruct the per-plate data structure. Otherwise, I'm initializing the actual hardware calibration process—calculating the total number of captures needed across all tokens, repetitions, and target plates, then estimating the runtime. I open the oscilloscope handle and relay multiplexer to begin the capture sequence. Saving the calibration data to a JSON file with all the per-plate information organized, then checking if the file was created successfully before moving on to build the feature extraction pipeline. I'm setting up the results dictionary to store experiment metrics, converting numpy arrays to lists for JSON serialization and organizing the bit and exact accuracy measurements for each token configuration. I'm reviewing the ridge regression approach for binary classification—it's straightforward with 0/1 targets and 0.5 thresholding. I'm reconsidering whether to keep the 256-class baseline since the per-bit method might actually perform better by giving each binary classifier balanced 50/50 classes, but the real comparison should be between software and photonic readouts using the same method. I'm also noting that the ensemble_perbit function creates fresh ESN instances, so I need to ensure consistent seeding across runs. I see the issue now — when both feature sets have the same input dimension, they'll get identical W_in and W_rec matrices from the same seed, so the ensemble diversity comes purely from the different input features rather than from randomness. That's actually acceptable since the features themselves provide the variation needed.

For the spectrum capture, I'm switching from storing 31 FFT magnitudes per plate to just the 8 mode frequencies specific to each plate. This makes the calibration data much more compact and focused on what actually matters for each resonator.

Now I'm thinking through the progress reporting for the calibration loop—with 4096 total captures across 256 tokens, 8 repetitions, and 2 plates, I'll print updates every 32 tokens to keep the user informed without spamming output. I also need to make sure --dry-run only works with v3 calibration data, since v2 has a completely different structure and won't be compatible.

Finalizing the code now...

Actually, I'm realizing there's a subtlety with the 8-tone quantization in the AWG. When the v2 function normalizes the peak to 1.0 before 8-bit quantization, with 8 equal-amplitude tones the peak can reach 8× a single tone's amplitude, which after normalization gives each tone only about 16 quantization levels—that 24 dB SQNR I calculated. The real issue emerges at token 255...

The problem is that tokens with fewer bits set (like single-bit tokens 1, 2, 4, etc.) get normalized to a higher amplitude and thus better quantization resolution, while token 255 with all bits set gets compressed down to just 16 levels per tone. This creates systematic noise bias where high-population tokens have worse SNR than sparse ones, though the z-score normalization across all tokens will partially mitigate this effect.

I'm deciding to stick with the current equal-amplitude-per-active-tone approach and document this limitation rather than add per-tone scaling, which would complicate the power budget. But I should verify the total drive voltage stays reasonable—with 8 tones each getting 1/8 of the 2 Vpp signal, the energy per tone drops significantly, which could be a problem given the narrow 0.8-5 Hz mode bandwidth.

Now I'm realizing the quantization noise picture is more nuanced than I initially thought. The broadband quantization noise in the drive waveform gets spread across all frequencies, but only the noise components at the actual mode frequencies will matter after the plate amplifies the signal by the quality factor. So even though the per-tone drive amplitude is small (around 125 mVpp), the Q amplification at resonance should recover most of the signal, while the out-of-band quantization noise stays suppressed.

The real limiting factor is that splitting the drive across 8 tones means each mode only gets 1/8 of the signal amplitude compared to a single-tone approach, which directly hurts the ADC SNR. With my averaging scheme—4 internal averages per measurement and 8 external repetitions—I'm getting an effective √8 ≈ 2.8× SNR improvement from averaging, which helps but doesn't fully compensate for the reduced per-tone signal.

This puts my estimated 8-tone SNR around 9-13 dB, roughly 3-4.5× signal-to-noise ratio. That's tight, but worth testing since v2 actually used 4 tones on the 4-bit plates and still achieved solid accuracy, so there's precedent that this approach can work.

The math checks out: doubling from 4 to 8 tones costs 6 dB per tone, dropping the SNR from ~18 dB down to ~12 dB with the same averaging. Still manageable. If the data comes back too noisy, I can always increase the calibration repetitions or averaging.

Time to stop theorizing and just build it—the hardware will tell me if this works. I'm laying out the feature variants for both plate and software: plate gets raw (8d) and poly2 (36d), plus poly3 (92d) for comparison, while software gets raw (8d), degree-4 (162d), and degree-8 (255d) to test across the complexity spectrum. The degree-8 expansion is pushing it though—255 input dimensions feeding into a 200-unit hidden layer means the input weight matrix is already quite large, so I need to be careful about whether that's actually feasible.

Let me verify the input scaling works out: with W_in initialized from a normal distribution scaled by 0.1, and binary ±1 inputs, the pre-activation variance per hidden unit comes to about 2.55, giving a standard deviation around 1.6—that's in a reasonable range before the tanh nonlinearity, so the input shouldn't completely dominate the recurrent dynamics.

Now looking at what happens downstream: with std ≈ 1.6, about half the hidden units will saturate in tanh each step, which could be problematic. The lower-dimensional variants like sw_d4 (162d, std ≈ 1.27) and especially sw_raw (8d, std ≈ 0.28) avoid this saturation issue. The v2 results actually confirm this—concat_poly at 161d hit 80.7% while concat_raw at 31d reached 98.3%, a clear sign of saturation degrading performance. So sw_d8 with its 255 dimensions might actually underperform sw_d4 despite having more information, because the ESN can't effectively process such high-dimensional inputs without hitting saturation limits.

The solution is to scale down the input_scale inversely with dimensionality—using something like input_scale = 0.1 \* sqrt(8/dim) to keep the total input variance constant across different feature dimensions. This way, whether we're working with 8d or 255d inputs, the hidden units receive roughly the same standard deviation and avoid saturation.

Now I'm deciding between two approaches: keeping input_scale fixed like in v2 to show the raw effect of dimensionality, or normalizing it per feature set to give each one a fair shot. I think normalizing makes more sense here since we're really testing whether plate features have better information content than software features, not whether the ESN hyperparameters happen to work better for one dimensionality over another.

The standard approach in reservoir computing is to scale the input weights by input_scale / sqrt(input_dim), which keeps the total input contribution independent of how many dimensions we're feeding in. Let me implement that normalization. I'm implementing the input scaling normalization in the ESN class, but now I'm second-guessing whether changing this from v2 will make the results incomparable — maybe I should keep the input scaling consistent with the previous version to maintain a fair baseline.

Actually, the real question is simpler: does 8-bit outperform software? I'll use normalized scaling by default to give each feature set a fair shot, and include the fixed scaling as a comparison point. Let me stop overthinking this and just write the code for the new ESN implementation.

Writing the ESN implementation... I'm realizing the per-bit readout might not capture the full picture since it treats each bit independently, whereas a direct 256-class prediction could be more effective. With ridge regression on the hidden states and the sparse training data per class, I should include this as a secondary metric to compare against the per-bit approach. Let me finalize the plan and start implementing. reps per token per plate. With 256 tokens, that's 2048 captures per plate. But the per-token SNR with 8 reps and N_AVG=4 internal averages is the same regardless of number of tokens. So 8 reps should be fine.

However, to save time, maybe 4 reps is enough? With 4 reps: 256 × 4 × 2 = 2048 captures, ~14 min. With 8 reps: 4096 captures, ~27 min. The extra reps give √2 better SNR. Let me keep 8 reps since 27 min is still reasonable and we want the cleanest data possible for this important experiment.

OK coding time. For real.

Actually, let me reconsider one more time if --dry-run should also be able to fallback to using v2 calibration data for plates that have 4-bit data. No, that makes no sense — v2 has 16 tokens, v3 needs 256. Completely different calibration. OK, --dry-run only uses v3 data.

I'll add --n-reps and --n-sequences as arguments for flexibility, then just write the code. Targeting around 500 lines, efficient and focused.

Now thinking about the software baselines with per-bit readout — sw_d4 should predict individual bits very well since each bit is a linear function of the degree-1 terms, and the ESN hidden state captures bit values at each position through its memory, though the degree-4 terms add redundancy without helping predict individual bits.

For the reversal task specifically, the ESN needs to remember which token was at which position, then the readout extracts bit b from the token at position (SEQ_LENGTH-1-p). The bit value itself is a degree-1 property, but the position information comes from the ESN's memory. With 200 hidden dimensions and SEQ_LENGTH=4, the ESN needs to encode 32 bits of information across 4 tokens, which is well within capacity.

Now looking at the feature representations: sw_raw gives the ESN the raw 8-bit tokens directly, so it has all the information needed for per-bit readout. With sw_d4, the 162 features include the degree-1 terms plus higher-order interactions, but only the degree-1 terms matter for this task—the extra features add noise. If the input scaling is normalized properly, sw_d4 should perform similarly to sw_raw since the ESN's memory capacity is the real constraint here, not the feature dimensionality.

This suggests an interesting pattern: on per-bit accuracy, sw_raw, sw_d4, and sw_d8 should all perform similarly because the bottleneck is purely the ESN's ability to remember positions. But on 256-class accuracy where the full token identity matters, sw_d8 should outperform sw_d4, which outperforms sw_raw, since the higher-order interactions become crucial. For the plate features, I'm expecting a different pattern.

Actually, this reveals a critical flaw in my experiment design. Per-bit readout can't show the plate winning because it only needs degree-1 features, and software will always have zero noise advantage there. The real test is 256-class readout, where sw_d4's incomplete polynomial representation might finally give the plate a chance to compete. I need to shift my focus to that task as the primary comparison, since that's where the plate's 8-bit encoding could actually demonstrate an advantage over the software baseline. The real bottleneck is whether the ESN's hidden state actually preserves enough token identity information after compressing the input features. With sw_d4's 162-dimensional input squeezed through tiny random weights (input_scale=0.1 normalized to 0.022), a lot of the high-order correlational structure gets lost in that projection, whereas the raw 8-dimensional plate features preserve token distinctions more directly through the recurrent dynamics.

The key realization is that the ESN itself IS doing the nonlinear expansion through its tanh hidden units—adding polynomial features beforehand just creates redundancy that gets compressed away anyway. Raw features let the ESN's own recurrent dynamics handle the nonlinear feature generation, which turns out to be more effective than pre-computing polynomial expansions that then get bottlenecked through the random input matrix.

For the plate data, the situation is different: the 8-mode amplitudes are already nonlinearly transformed by the glass's Duffing-like physics, so plate_raw gets nonlinear features "for free" that sw_raw doesn't have. This means the plate data undergoes double nonlinear expansion—first from the glass physics, then from the ESN's tanh units—which could give it an advantage over both sw_raw and sw_d4 if the glass's inherent nonlinearity captures structure that random projection doesn't.

Rather than overthinking this, I should just run the experiment and let the results show whether the plate actually adds value. I'll set up 256-class readouts across all feature sets using ridge regression with α=10 on 200-dimensional hidden states. With N_SEQUENCES=3000, I'll get roughly 8.8 training examples per class per position, which should give stable enough results to see if the plate's nonlinearity genuinely outperforms the software alternatives. 3000 sequences is workable—even with 14+ ESN runs across different feature sets and readout methods, each taking a couple seconds, the total runtime stays reasonable. Now I'm ready to write the actual implementation, starting with how the ESN class should handle normalized input scaling.

Writing ESN class... I'm verifying the normalization math—the effective scale adjustment ensures that regardless of input dimension, the expected squared norm of the input contribution stays constant across different hidden units.

Now I'm ready to write the full implementation, keeping it focused and around 500 lines. I'll skip the 16-class readout variant since we're already working with 256 tokens and the user is familiar with the 4-bit results.

Writing the implementation... about the ensemble for per-bit readout. Two approaches:

Average the ridge regression RAW outputs (before thresholding) from each ESN, then threshold
Majority vote on the binary predictions
Approach 1 is more principled (soft averaging preserves gradient information). Let me use that.

For 256-class ensemble: average the class scores (before argmax) from each ESN, then argmax. Same as v2.

The user wants one tool that handles all three options, but Options 2 and 3 need different calibration protocols. I'll build Option 1 now, test it, and modify for the others if needed.

Writing the implementation...
