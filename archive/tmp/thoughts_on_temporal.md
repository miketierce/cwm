The results are in. Let me analyze:

Step rate: 58.3 Hz (17.15 ms/step). That's much slower than the target of 250+ Hz. The built-in sine gen USB calls are taking ~17ms per step, not the 3-4ms I estimated. The USB latency on macOS is clearly higher than expected.

At 58 Hz (17.15ms/step), the temporal retention is:

29.9 kHz (τ=1.99ms): exp(-17.15/1.99) = exp(-8.6) ≈ 0.02% → effectively ZERO

This is confirmed by the metrics: temporal demodulation performs worse than baseline, adds nothing to the input signal alone, and the shuffle test shows zero temporal memory. All the plate features are just noise at this step rate.

The 17ms step time is the bottleneck—the sine generator USB calls are the culprit.

Looking at the narma_ladder run with multitone arbitrary waveform and 8064 samples averaged twice, it takes 403ms per step. Even after removing the 120ms settle time and cutting averages to 1 and samples to 256, I'm still looking at ~140ms per capture—far slower than expected, which suggests the USB interface itself is the limiting factor.

When I break down the fast run at 2.48/s (403ms per step), the actual capture operation for 8064 samples takes about 194ms, but the theoretical time for that many samples at 781 kHz is only 10.3ms. That means roughly 184ms is pure USB overhead from triggering, running the block, polling for readiness, and retrieving values.

With the optimized 256-sample version running at 17ms per step, the capture drops to ~7ms while the signal generator setup takes ~10ms, which is much more reasonable.

The real bottleneck is that each USB call on macOS ARM64 adds 5-10ms of latency. To hit 400 Hz (2.5ms per step), I'd need total USB overhead under 2.5ms, which is impossible with multiple calls per step. I'm considering streaming mode where the scope continuously captures and sends data while I change the AWG amplitude with one USB call per step, though that would still cap out around 100 Hz. Another option is pre-loading the entire sequence as an AM-modulated waveform that slowly changes amplitude in a single ARB waveform.

The ARB buffer is only 4096 samples though, so I can't encode 3000 different amplitude steps into it. I could treat each ARB cycle as a step when playing at high speed—at 400 Hz that gives me 2.5ms per cycle—but then every cycle has the same amplitude. External modulation via a DAC isn't available with my current hardware, and bypassing the Python wrapper for direct USB control probably won't help much given the protocol overhead. The real question is whether I can eliminate one of the USB calls per step, though I still need to set the AWG parameters.

Actually, I'm realizing the streaming mode might work differently. Instead of setting amplitude and capturing for each step individually, I could start a continuous streaming capture, then periodically read the accumulated data while changing the AWG amplitude in between. That way I'd capture one long waveform and segment it by amplitude afterward.

But there's still the USB bottleneck—each step needs at least one call to update the signal generator, plus periodic reads of the streaming data. So realistically I'm looking at around 2 USB calls per step minimum, which limits me to roughly 58 Hz.

At that rate, the time between steps is about 17ms. For the time constants I'm working with—even the faster ones like 1.49ms—the signal retention drops to nearly zero between steps, so I'd lose all the information I'm trying to capture.

I need at least 200 Hz sampling to preserve even 1% of the signal between steps. The real question is whether I can optimize the signal generator calls themselves. If ps2000_set_sig_gen_built_in is slow because it's reconfiguring the DDS every time, maybe I can work around that by keeping the frequency fixed and only changing amplitude. That's already what I'm doing—only the pk_to_pk parameter changes. But the driver might still be doing a full reconfiguration under the hood.

Let me try loading the arbitrary waveform once and then just modulating the amplitude through the pk_to_pk parameter on subsequent calls, which should skip the expensive DDS reconfiguration.

Looking at the actual API, though, every call to set_sig_gen_arbitrary sends the full 4096-byte buffer over USB, which is slower than the built-in call with just 10 parameters. So that won't help. It seems like 58 Hz is probably the practical limit for the step rate with this driver on macOS.

Let me think about a different strategy entirely—what if instead of modulating the AWG at each step, I use a fixed broadband drive signal and encode the input some other way? The plate would vibrate continuously in its eigenmodes, but I'd need a way to inject the input signal. Without a second channel, I'm limited to either physically tapping the plate (not automated) or encoding it as a modulation of the drive itself, which brings me back to the same problem.

Actually, what if I pre-compute an arbitrary waveform that contains amplitude modulation built into the buffer itself? With 4096 samples repeating at the repetition frequency, I could encode the input information directly into the waveform shape.

The issue is that when the buffer loops, there's a discontinuity—the amplitude jumps from one value back to the previous one, creating an artifact. Even with the maximum 8192-sample buffer, I'm running into the same looping problem. The envelope needs to transition smoothly across buffer boundaries, but the ARB repeats, so I get a step change every cycle.

I've also considered using the signal generator's frequency sweep feature to encode the input as frequency modulation instead, but that doesn't give me the nonlinear mixing behavior I need. And I keep hitting the same wall: macOS USB latency limits me to about 60 Hz step rate with three USB calls per step.

What if I could get down to just one USB call per step? The idea would be to skip capturing after each modulation and instead do one long capture at the end. But that won't work—I need the plate's response at each individual step to see how it reacts to each input value.

Actually, wait. What if I start a continuous streaming capture that runs for the entire experiment, then modulate the AWG during the capture without reading the data until it's all done? I'd set the AWG to the first input value, wait about 2.
