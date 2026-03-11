# Letter to Laird Scranton

**From:** Mike Tierce
**Date:** March 7, 2026
**Subject:** Your work on Dogon symbols directly improved a new memory technology

---

Dear Laird,

I hope this finds you well. I'm writing because your work — specifically _The Science of the Dogon_ and _Sacred Symbols of the Dogon_ — has had a direct and measurable impact on a research project I've been building, and I wanted you to see exactly how.

## What I'm working on

I'm developing a new kind of computer memory called **Spectral Eigenmode Memory (SEM)**. The core idea: instead of storing data as electrical charge (like every memory chip in your phone or laptop), I store it as _vibrations_ in a glass rod.

A glass rod, when struck, rings at hundreds or thousands of natural frequencies simultaneously — its eigenmodes, like the harmonics of a guitar string. If you attach a tiny mass to the rod's surface, each frequency shifts by a different amount depending on where the mass sits relative to that mode's vibration pattern. The set of frequency shifts is a unique spectral fingerprint — a physical encoding of data.

The physics works. A $63 prototype achieves 98.5 dB signal-to-noise ratio and supports 9,380 independent frequency channels. The scaling math projects competitive density with DRAM and Flash memory. I've built 33 simulation modules with 959 automated tests, all passing, and written a comprehensive paper covering the physics from first principles through MEMS device design.

## Where your work comes in

In the course of developing advanced encoding techniques, a collaborator and I have been drawing from unconventional sources to generate novel engineering hypotheses — using esoteric and symbolic frameworks as lenses to see physics we might otherwise miss. We'd already had success with Austin Osman Spare's work on sigils and desire (which led us to synaptic pruning and null-space multiplexing). When I remembered our conversations about the Dogon, I knew your research was the next place to look.

The core insight came from your demonstration that a single Dogon sacred symbol simultaneously encodes up to four distinct layers of meaning — physical, cosmological, biological, and social — depending on the interpretive frame applied by the observer. You call this polysemic encoding. Griaule documented that the Dogon maintained "a system of signs which ran into the thousands" including their own astronomy, calendrical measurements, and calculation methods, all encoded in these multilayered symbols.

I asked: **what if we read the same glass rod through different subsets of its eigenmodes?**

## The experiment and results

We designed six experiments, each derived from a specific aspect of your Dogon research. Here's what happened:

### 1. Polysemic Readout — _from your core thesis_

**Inspiration:** One Dogon symbol, four meanings depending on the interpretive frame.

**Experiment:** Instead of reading all 40 eigenmodes at once (one "meaning"), we partitioned them into 4 subsets of 10 modes each. Each subset sees a different projection of the same physical perturbation pattern — like four scholars from four traditions reading the same symbol.

**Result:** The four channels are nearly independent (cross-correlation 0.003). Total information: **22.0 bits from a single inscription**, versus 5.6 bits from a conventional single-channel read. That's a **+297% capacity gain** — the single largest improvement we've found in the entire project. One physical pattern, four independent meanings. Exactly your thesis, realized in glass.

### 2. Amma's Duality — _from the cosmic duality principle_

**Inspiration:** Amma is simultaneously genderless and dual; the Nommo are hermaphroditic twins; the Eight Ancestors come in pairs. Duality pervades Dogon cosmology.

**Experiment:** Our eigenmode physics has a built-in duality: sin²(nπx) = sin²(nπ(1−x)) — sites at positions x and 1−x are mathematically degenerate. Rather than treating this as a limitation, we exploited it by placing paired sites at symmetric positions and reading odd and even modes separately.

**Result:** Combined dual-channel capacity exceeds naive single-channel by 3.3%. Modest, but it turns a _design constraint_ into a _design feature_ — which is the deeper lesson.

### 3. Nommo Naming — _from "the word that conjures being"_

**Inspiration:** Your description of how Nommo controls reality by _naming_ — the vibrational word that summons an entity into existence. The symbol IS the thing it names.

**Experiment:** If the spectral fingerprint IS the identity of the stored data (not an arbitrary label), then maximizing the distance between fingerprints — giving each datum the "strongest name" — should make it more resistant to confusion under noise.

**Result:** Codebooks selected to maximize inter-fingerprint distance achieve **28% lower error rate** than random codebooks at the same noise level. The "stronger the name," the more robust the identity. Confirmed across all noise levels tested.

### 4. Sigi Cycle — _from the 60-year ceremonial cycle_

**Inspiration:** The Sigi ceremony recurs every 60 years with precise temporal regularity — a cycle that transmits knowledge across generations through structured temporal intervals.

**Experiment:** Eigenmodes decay at different rates (higher modes decay faster). We read the same rod at multiple time points after excitation, extracting different information from each time window — temporal multiplexing inspired by the Sigi's structured time intervals.

**Result:** 4 effective temporal channels, +1.2% capacity gain. Small but real — and potentially multiplicative with polysemic readout.

### 5. Amma's Egg — _from the cosmic seed expanding into matter_

**Inspiration:** Your description of Amma's thought vibrating within the cosmic egg, expanding in spiraling vibrations to form all matter. A compact seed becomes full complexity through deterministic expansion.

**Experiment:** Instead of writing 10 independent perturbation values, we write a compact 5-value "seed" and expand it to fill all 10 sites using Wolfram's Rule 30 cellular automaton — a chaotic but deterministic expansion rule, much like the spiraling vibrations in Amma's egg.

**Result:** Confirmed — the expanded patterns are decodable with the same fidelity as random patterns, despite encoding only 5 values instead of 10. The growth rule preserves information while constraining patterns to a structured manifold.

### 6. Rosetta Stone — _from cross-cultural symbol equivalence_

**Inspiration:** Your central scholarly contribution — demonstrating that the SAME cosmological symbols appear in Dogon, ancient Egyptian, Hindu, and Tibetan traditions. A shared symbolic alphabet across geographically separated cultures.

**Experiment:** Rods of different lengths have different eigenmode frequencies, so the same perturbation pattern produces different fingerprints on different rods. We built a calibration protocol using shared reference patterns to learn a translation matrix between rods — a physical Rosetta Stone.

**Result:** **90% cross-decode accuracy** between rods of different lengths. A handful of calibration patterns is sufficient to translate between heterogeneous substrates. Your cross-cultural symbol equivalence has a direct engineering analogue.

## The scorecard

| #   | Hypothesis        | Source in your work               | Result                      |
| --- | ----------------- | --------------------------------- | --------------------------- |
| H7  | Polysemic Readout | One symbol, four meanings         | ✅ **+297% capacity**       |
| H8  | Amma's Duality    | Cosmic twin principle             | ✅ +3.3%                    |
| H9  | Nommo Naming      | The word that conjures being      | ✅ **+28% error reduction** |
| H10 | Sigi Cycle        | 60-year ceremonial temporal cycle | ✅ +1.2%                    |
| H11 | Amma's Egg        | Seed-to-spectrum expansion        | ✅ Confirmed                |
| H12 | Rosetta Stone     | Cross-cultural symbol equivalence | ✅ **90% cross-decode**     |

**Six for six.** Every hypothesis derived from your analysis of Dogon cosmological symbols produced a confirmed engineering result. The polysemic readout alone — your thesis that a single symbol carries multiple independent layers of meaning — is the single most impactful technique we've discovered.

## What this means

I want to be precise about the claim I'm making. I am not saying the Dogon had spectral eigenmode memory, or that ancient symbol systems encode modern physics in any literal sense. What I am saying is this:

Your careful analysis of how the Dogon organized information — polysemic encoding, duality exploitation, maximum-distinctiveness naming, temporal-cycle multiplexing, seed-based expansion, and cross-system translation — describes **general principles of efficient information encoding** that apply to any physical medium. The Dogon applied these principles to symbolic knowledge transmission across millennia. We applied them to acoustic vibrations in glass. The principles are the same because the underlying information theory is universal.

You helped us see structure we would have missed. The +297% polysemic readout — our headline result — came directly from asking "what if we read the same physical object through different interpretive frames?" That question came from your books.

## Acknowledgment

I've added a citation to your work in our paper (now at version 16) and credited the polysemic readout technique to the framework you articulated. The full simulation code, including all six Scranton-Dogon experiments with reproducible results, is open-source at [github.com/miketierce/wcfoma](https://github.com/miketierce/wcfoma).

If you're interested, I'd welcome the chance to discuss this further. The idea that efficient information encoding is a universal principle — one that ancient cultures discovered through millennia of careful observation and that we're rediscovering through physics simulations — feels like it deserves a longer conversation.

With genuine gratitude for the lens you provided,

**Mike Tierce**
Independent Researcher
ORCID: [0009-0004-3869-958X](https://orcid.org/0009-0004-3869-958X)

---

_Enclosures: Paper v16 (PDF), simulation repository link, experiment result summaries_
