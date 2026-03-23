# CWM Introduction Video — Script

**Working title:** _"What if memory was made of vibration?"_
**Target length:** 18–22 minutes
**Audience:** Curious generalists, physics students, makers, MEMS researchers
**Tone:** Conversational but precise. No hype, no hedging. Let the physics do the talking.
**Visual style:** Bench-top footage, oscilloscope screen captures, simple animations over paper diagrams, direct-to-camera narration.

---

## COLD OPEN [0:00–1:30]

**[VISUAL: Close-up of a glass rod sitting on a workbench. A hand taps the end with a fingernail. Cut to an oscilloscope screen showing a decaying burst of oscillation — the ring-down.]**

**NARRATOR (V/O):**
That sound you can't quite hear — it's 17,717 hertz, just above the range of most adult ears — is a glass rod vibrating. Not randomly. In a pattern. A very specific pattern that has been the same since the day this rod was manufactured, and will stay the same until something physically breaks it.

**[VISUAL: Cut to the FFT screen. A clean comb of spectral peaks appears.]**

What you're looking at is the frequency spectrum of that vibration. Each peak is a standing wave — a natural resonance of the glass. The first peak is the fundamental. The second is exactly double. The third, triple. They go on — in this rod, there are over nine thousand of them before they become too close together to resolve.

**[VISUAL: Zoom out to reveal the full bench setup — rod in cooler, PicoScope, laptop.]**

Every one of those peaks is an independent channel. Think of it as nine thousand radio stations, all broadcasting from the same piece of glass, all at the same time, and none of them interfering with each other.

Now here's the question this video is about: what if you could use those channels to store information?

**[TITLE CARD: "Coherent Wave Memory — What if memory was made of vibration?"]**

---

## ACT 1: THE PROBLEM [1:30–4:00]

### The memory wall

**[VISUAL: Simple animation — a CPU chip on the left, a memory chip on the right, a thin bus connecting them. Data packets shuffle back and forth.]**

**NARRATOR:**
Every piece of technology you own — your phone, your laptop, every server in every data centre — stores data as an electrical state. A charge trapped on a tiny capacitor. A resistance value in a junction. Electrons stuck on a floating gate. To _read_ that data, the processor fetches it across a bus. To _compute_ on it, the processor fetches it again, operates on it, and writes the result back.

In 1978, John Backus — the man who invented FORTRAN — stood up at his Turing Award lecture and called this architecture a "bottleneck." He was right, and the bottleneck has gotten worse every year since. Processors have gotten ten thousand times faster. Memory bandwidth has improved by about a hundred. In modern data centres, more than half the energy goes not to _computing_ but to _moving data_ between the processor and the memory.

It's called the memory wall. And it exists because of how we encode data — electrically.

### A different encoding

**[VISUAL: Cut back to the glass rod.]**

**NARRATOR:**
But what if data wasn't electrical? What if it was _mechanical_? Not a charge on a capacitor, but a vibration in a piece of glass?

That's what Coherent Wave Memory is. CWM. It stores information in the eigenmode spectrum of a glass resonator — the set of natural frequencies at which the glass vibrates. To write data, you change the rod's mass distribution. To read, you tap it and listen. To _search_ — and this is where it gets interesting — you drive an array of rods with a query signal, and the rod whose stored pattern matches the query vibrates the loudest. No processor. No memory bus. No software. The physics does the computation.

And you can prove all of this with thirty-nine dollars' worth of parts from Amazon.

---

## ACT 2: THE PHYSICS [4:00–8:30]

### Eigenmodes

**[VISUAL: Animation of a rod vibrating in its fundamental mode — compression and expansion along the length, with a sine wave overlaid. Then mode 2 (two half-waves), mode 3, etc.]**

**NARRATOR:**
When you tap a glass rod, it vibrates. But not at one frequency — at many frequencies simultaneously, each one a different standing wave pattern called an eigenmode.

The fundamental mode is the simplest: the rod compresses and expands as a whole, with maximum displacement at both ends and zero displacement at the center. The second mode has two compression zones and _two_ nodes — points that don't move. The third mode, three. And so on.

Each mode has a precise frequency determined by the rod's length and the speed of sound in the glass:

**[VISUAL: The equation $f_n = n \times v / (2L)$ appears on screen, with numbers filling in: $v = 5{,}315$ m/s, $L = 150$ mm, $f_1 = 17{,}717$ Hz.]**

For this rod — 150 millimetres of borosilicate glass — the fundamental is 17,717 hertz. The second mode is 35,434. The third is 53,151. The spacing is constant: 17,717 hertz between every pair of adjacent modes. It's a frequency comb — a perfect ladder of resonances.

And here is the critical property: these modes are _independent_. You can excite the second mode without disturbing the first. You can measure the fifth without affecting the third. Each mode is its own information channel, operating in the same physical medium as all the others, simultaneously, without crosstalk.

### Perturbation encoding — the write operation

**[VISUAL: A small ball of silicone putty being pressed onto the rod at a marked position. Cut to the FFT screen — the peaks shift.]**

**NARRATOR:**
Now stick a tiny mass on the rod — a speck of silicone putty, about a tenth of a milligram — and measure the spectrum again.

The peaks have moved. Not all by the same amount. Mode 3 shifted the most. Mode 4 barely moved. Modes 2, 5, 6, and 7 each shifted by different amounts.

Why? Because the mass sits at a specific position along the rod, and each mode has a different pattern of movement at that position. If the mass is at a point of maximum displacement for mode 3 — an antinode — then mode 3 has to work harder to accelerate that extra mass, and its frequency drops. But mode 4 has a _node_ at that position — a point that doesn't move — so mode 4 doesn't even feel the extra mass.

**[VISUAL: The Rayleigh formula appears: $\Delta f_n / f_n = -(\delta m / 2M) \sin^2(n\pi x / L)$. Animated $\sin^2$ curves overlaid on the rod for modes 1–5, showing which modes have antinodes at the putty position.]**

This is the Rayleigh perturbation formula, published by Lord Rayleigh in 1877. The shift depends on where the mass sits relative to each mode's standing wave pattern — specifically, on $\sin^2$ of the mode number times the position. Different position, different pattern of shifts. Different mass, different magnitude of shifts. The set of all shifts across all modes is a unique _spectral fingerprint_ — a pattern that encodes the mass's position and size.

_That's the write operation._ Place a mass. The spectrum changes. The new spectrum _is_ the stored data.

**[VISUAL: Move the putty to a new position. The spectrum shifts differently. Remove it entirely — peaks snap back.]**

And it's reversible. Peel off the putty and the spectrum returns to its original state. The rod remembers nothing. Or — put the putty back at the same position, and the rod reproduces the exact same fingerprint. Every time.

### Associative recall — the search operation

**[VISUAL: Two rods side by side in a cooler, each with putty at different positions.]**

**NARRATOR:**
This is where CWM stops being a curiosity and becomes an architecture.

Imagine two rods, each with putty at a different position — two different stored "words." You want to find which rod matches a query. In a normal computer, you'd read both spectra digitally, compute the correlation, and compare. Sequential. Two rods is trivial; two billion is not.

CWM does it differently. Encode your query as a set of frequencies — the spectral fingerprint you're looking for — and drive _both_ rods with that signal simultaneously. Each rod absorbs energy at frequencies where its eigenmodes live. The rod whose eigenmode pattern best matches the query absorbs more energy and vibrates louder.

**[VISUAL: Oscilloscope showing two response traces — one tall, one short. The tall one is the match.]**

The matching rod's response is 15 to 25 decibels above the non-matching rod. That's 30 to 300 times more acoustic power. You cannot mistake the answer. And the computation — finding the best match — takes about 4 microseconds. The time for sound to travel the length of the rod and interfere. No processor involved. The glass did it.

This is not a trick. It's interference. The query signal contains energy at specific frequencies. The matching rod has resonances at those frequencies, so the energy piles up — constructive interference. The non-matching rod's resonances are at _different_ frequencies, so the query energy doesn't accumulate — destructive interference. The physics _is_ the computation.

---

## ACT 3: BUILD IT YOURSELF [8:30–14:30]

### The parts list

**[VISUAL: Each item laid out on the bench as it's mentioned. Price tags appear beside each.]**

**NARRATOR:**
Here is everything you need. And I mean _everything_.

One pack of borosilicate glass rods — 150 millimetres long, 6 millimetres in diameter. Fifteen rods in a pack. Eight dollars.

One pack of piezoelectric discs — PZT ceramic, 10 millimetres across, with pre-soldered leads. Fifteen discs. Seven dollars.

One tube of super glue. Five dollars.

One pack of Mack's Pillow Soft silicone putty earplugs — these are your perturbation masses. Nine dollars.

BNC cables and connectors. Ten dollars.

And an oscilloscope. The PicoScope 2204A is a USB oscilloscope the size of a thumb drive, with a built-in waveform generator and free FFT software. A hundred and ninety-two dollars. But if your school already has any oscilloscope with FFT capability — and most physics labs do — you don't need to buy one. The core materials cost is thirty-nine dollars.

Two pieces of cardboard from any shipping box. Free.

A styrofoam cooler from the grocery store. Five dollars.

That's it. Total: under fifty dollars for the core kit, or about two-forty if you need the scope.

### Assembly

**[VISUAL: Time-lapse of assembly — cleaning the rod, building the mount, gluing the PZT, curing.]**

**NARRATOR:**
Step one: clean a glass rod with rubbing alcohol. Finger oils damp the vibrations more than you'd think.

Step two: build the mount. Cut two rectangles of cardboard sized to slot inside the styrofoam cooler. Punch a small pinhole through each — just big enough for the rod to pass through. Space the dividers 75 millimetres apart inside the cooler. This puts each support at one-quarter and three-quarters of the rod's length — the exact displacement nodes of the second vibrational mode.

**[VISUAL: Wine glass analogy — hold the glass by the stem, it rings. Touch the rim, it goes silent.]**

This is the same physics that makes a wine glass ring. You hold it by the stem — a vibrational node — and energy can't leak through a point that isn't moving. Press your finger on the rim — an antinode — and you kill the sound instantly. Your cardboard dividers are the rod's "stems."

Step three: glue the piezo disc to one end of the rod. One tiny drop of super glue, centered. Less is more — excess glue adds damping. Hold for thirty seconds.

Step four: wait. Let the glue cure for twenty-four hours. This is the hardest part.

Step five: connect the PZT leads to the oscilloscope. Tap the rod with a fingernail. You should see a burst of oscillation decaying over a few hundred milliseconds. If you do — you've built a working CWM prototype.

### The first measurement

**[VISUAL: Live screen recording — PicoScope software. Chirp is sent, response recorded, FFT computed. The frequency comb appears.]**

**NARRATOR:**
Set the PicoScope to generate a broadband chirp — a sweeping sinusoid from 1 kilohertz to 200 kilohertz. This excites every eigenmode in that range. Record the response through the same piezo disc, and compute the FFT.

What you'll see is this: a frequency comb. Sharp peaks at 17.7 kilohertz, 35.4, 53.1, 70.8, 88.5 — the first five longitudinal modes of your glass rod, exactly where the formula predicts. Each peak is a standing wave. Each peak is an independent information channel.

Measure the quality factor by driving the fundamental mode to steady state and then cutting the drive. Watch the amplitude decay — it should take about 180 milliseconds to fall to 37 percent. From that, Q equals pi times frequency times the decay time: about 10,000 for borosilicate glass. That means each vibration cycle reflects off the rod's ends and comes back with 99.97 percent of its energy intact. The rod rings for ten thousand cycles before the vibration fades.

### The perturbation test

**[VISUAL: Pinching off a tiny ball of silicone putty, weighing it on a milligram scale, pressing it onto the rod at a marked position.]**

**NARRATOR:**
Now the real test. Take a tiny piece of silicone putty — tear off a crumb, about a tenth of a milligram if you can weigh it — and press it onto the rod at a measured position. Say 55 millimetres from the PZT end.

Run the chirp again. Look at the FFT.

**[VISUAL: Before-and-after spectrum, with shift arrows highlighting each mode's movement.]**

The peaks have moved. Mode 3 dropped by about 2 hertz. Mode 4 barely budged — maybe a tenth of a hertz. Modes 1, 2, 5, 6, 7 all shifted by different amounts. Plot those shifts against $\sin^2(n\pi x/L)$ for the known position, and you'll get a straight line. The slope tells you the mass ratio. The fit should be within 5 to 10 percent of the Rayleigh prediction — often within 2 percent.

Now move the putty. A different position produces a different fingerprint. Remove it entirely — the spectrum snaps back to baseline. Every time.

That's data, physically written in glass and physically read back through vibration. Not simulated. Not theoretical. Measured on a kitchen table with hardware that arrived in a brown cardboard box.

### The discrimination test

**[VISUAL: Two rods, patterns A and B. Query waveform constructed on AWG. Response comparison.]**

**NARRATOR:**
For the final demonstration, you need two rods with two different putty patterns. Pattern A: putty at the quarter-points. Pattern B: putty at the third-points.

Measure each rod's spectrum. Build a multi-tone query waveform from Pattern A's shifted frequencies using the PicoScope's waveform generator — summing sinusoids at each of the shifted mode frequencies. Drive Rod A with this query. Measure the response. Then drive Rod B with the same query.

Rod A — the match — should produce a response 15 to 25 dB above Rod B. Thirty to three hundred times more acoustic power. The glass did the pattern matching for you, in the time it takes sound to traverse the rod. About four microseconds.

---

## ACT 4: WHY IT MATTERS [14:30–17:30]

### Scaling

**[VISUAL: Side-by-side — macro rod (150 mm) and a MEMS resonator diagram (1 mm). Same physics, same equations, different size.]**

**NARRATOR:**
Everything you just saw on a 150-millimetre glass rod works the same way on a 1-millimetre MEMS resonator. The physics is scale-invariant. The Rayleigh formula doesn't change. The eigenmode comb doesn't change. The interference-based recall doesn't change. Only the numbers change.

At 1 millimetre: the mode spacing widens to 2.66 megahertz. The fundamental hits 2.66 megahertz — well within electronic measurement range. A five-mechanism loss model predicts Q around 9,000 — nearly identical to the macro prototype. And the storage density? Ninety-five gigabits per cubic centimetre in the active volume. Seventeen gigabits per cubic centimetre in a packed array, accounting for packaging overhead.

For comparison, Flash memory — the technology in every SSD and every phone — stores about four gigabits per cubic centimetre. CWM projects four times that density in a _first-generation_ borosilicate design. In fused silica — which has ten times the quality factor — the projected density rises to 1.4 _terabits_ per cubic centimetre.

These are projections, not measurements. The MEMS device hasn't been built yet. But the projection rests on two things that _have_ been measured: the eigenmode physics (this video) and the quality factor of glass (180 years of published data). The scaling laws are mathematical consequences. If the physics works at 150 millimetres — and it does — and the glass Q survives at 1 millimetre — and the loss model says it does — then the density follows from arithmetic.

### Native computation

**[VISUAL: Animation — an array of rods receiving a query waveform simultaneously. One rod lights up brighter than the others.]**

**NARRATOR:**
But density isn't the revolutionary claim. The revolutionary claim is computation.

Every memory technology we have today is passive — it stores data and waits for a processor to come fetch it. CWM stores data _and_ computes on it in the same physical act. Drive a rod with a query and it performs a dot product — the fundamental operation of neural networks, search engines, and pattern recognition — in the time it takes a sound wave to bounce back and forth. Four microseconds. No processor. No bus. No memory wall.

This is not an incremental improvement. It is a different category. It's what happens when you stop encoding data as a static electrical state and start encoding it as a dynamic physical process.

### The accessibility argument

**[VISUAL: Cut back to the bench. The whole setup — cooler, PicoScope, laptop. Modest. Ordinary.]**

**NARRATOR:**
There is one more thing that matters, and it has nothing to do with density or speed.

This prototype costs thirty-nine dollars. A student can build it. A teacher can run the experiments in a week. The physics is accessible, the measurements are reproducible, and the paper is open-access. You don't need a clean room. You don't need a network analyser. You don't need an institutional affiliation. You need a glass rod, a piezo disc, some super glue, and curiosity.

Benjamin Franklin built the glass armonica because he believed scientific instruments should be available to anyone curious enough to play them. The CWM prototype is designed in that spirit. The glass rod is the armonica's descendant.

If any of this interests you — if you want to see a frequency comb appear on your own screen, or watch a spectrum shift when you press putty onto glass, or hear a rod ring at ten thousand cycles — everything you need is linked in the description below. The full paper. The experiment guide with step-by-step procedures, troubleshooting, and printable worksheets. Purchase links for every item. And the open-source simulation code to model it yourself.

Build it. Measure it. See for yourself whether the physics is real.

---

## CLOSING [17:30–18:30]

**[VISUAL: Close-up of the rod in the cooler mount, PZT leads trailing out. Quiet. Still.]**

**NARRATOR:**
A 150-millimetre glass rod has been vibrating in the same eigenmode pattern since the day it cooled from the furnace. It will keep vibrating in that pattern for as long as the glass exists. The information is not stored _in_ the glass the way a charge is stored on a capacitor — it _is_ the glass. The geometry is the memory.

All we did was learn to read it.

**[FADE TO BLACK]**

**[END CARD: Links to paper, experiment guide, and GitHub repo. "Replicate the experiment: cwm.dev/research"]**

---

## PRODUCTION NOTES

### B-roll needed

| Segment        | Shot                                    | Notes                                                  |
| -------------- | --------------------------------------- | ------------------------------------------------------ |
| Cold open      | Fingernail tap, extreme close-up        | Capture audio even if inaudible — use waveform overlay |
| Cold open      | PicoScope FFT screen capture            | Live recording, not mockup                             |
| Assembly       | Time-lapse: cleaning, gluing, curing    | Label each step with time-stamp                        |
| Assembly       | Wine glass demo — ring vs. mute         | Classic demo, 5 seconds                                |
| Assembly       | Cardboard divider cutting from template | Show printed template being traced                     |
| Perturbation   | Milligram scale weighing putty          | Close-up of scale display                              |
| Perturbation   | Before/after FFT overlay                | Split screen or toggle                                 |
| Discrimination | Two-rod setup, matched vs. unmatched    | Response amplitude traces side by side                 |
| Scaling        | MEMS cross-section diagram              | Paper figure or clean animation                        |
| Closing        | Rod in cooler, static shot, long hold   | Contemplative. No movement.                            |

### Key numbers to display on screen

| Quantity               | Value         | Context                          |
| ---------------------- | ------------- | -------------------------------- |
| Fundamental frequency  | 17,717 Hz     | First peak in FFT                |
| Mode spacing           | 17,717 Hz     | Constant — the frequency comb    |
| Quality factor         | 10,000        | Ring-down measurement            |
| SNR                    | 98.5 dB       | Thermal-noise-limited            |
| Bits per mode          | 16.4          | Shannon limit                    |
| Thermally stable modes | 9,380         | Across the rod's bandwidth       |
| Core BOM cost          | ~$39          | Without oscilloscope             |
| Complete kit cost      | ~$231         | With PicoScope 2204A             |
| Discrimination margin  | 15–25 dB      | Matched vs. non-matched response |
| Rayleigh accuracy      | < 2% error    | Measured vs. predicted shifts    |
| Macro Q (borosilicate) | 10,000        | Material-loss-limited            |
| MEMS Q (modeled)       | 9,097         | Five-mechanism loss budget       |
| MEMS density           | 17.0 Gbit/cm³ | Packed-array, borosilicate       |
| Fused silica density   | 1.4 Tbit/cm³  | Packed-array, projected          |
| Write energy           | 15 fJ/bit     | Projected                        |
| Recall time            | 3.8 µs        | Acoustic transit                 |

### Suggested chapter markers (for YouTube)

| Timestamp | Title                                       |
| --------- | ------------------------------------------- |
| 0:00      | Cold open — the glass rod rings             |
| 1:30      | The memory wall problem                     |
| 4:00      | How eigenmodes store data                   |
| 6:15      | Perturbation encoding — the write operation |
| 7:30      | Associative recall — physics as computation |
| 8:30      | Build it yourself — $39 parts list          |
| 10:00     | Assembly and first measurement              |
| 12:00     | The perturbation test                       |
| 13:15     | The discrimination test                     |
| 14:30     | Scaling to MEMS                             |
| 16:00     | Native computation — why it's different     |
| 17:00     | The accessibility argument                  |
| 17:30     | Closing                                     |

### Description box links

- **Full paper (PDF):** cwm.dev/research
- **Experiment guide (PDF):** cwm.dev/research (includes printable worksheets and cardboard templates)
- **Amazon kit (one-click cart):** linked on cwm.dev/experiment
- **GitHub repository:** github.com/miketierce/cwm
- **Simulation source code:** github.com/miketierce/cwm/simulations
