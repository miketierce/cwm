# Hardware Setup & Usage Guide

> **Last validated:** May 26, 2026 — Board D producing 3.47 Vpp @ 3.69× gain.

This file documents the working bench hardware configuration for running CWM acoustic experiments. Follow these instructions exactly to reproduce the validated signal chain.

---

## Equipment List

| Item | Model | Quantity | Role |
|------|-------|----------|------|
| PicoScope | 2204A | 1 | AWG source + measurement oscilloscope |
| Op-amp | OPA2134PA (DIP-8) | 2 | Board A preamp + Board D drive buffer |
| 9V battery | Any standard 9V | 2 | Board D ±9V dual supply |
| Breadboard (half) | 30-column | 1 | Board D (drive buffer) |
| Breadboard (full) | 63-column | 1 | Board A (preamp) + Board S (DDS/control) |
| PZT transducer | 20 nF buzzer type | 2 | TX (drive) + RX (receive) |
| Relay module | 16-channel opto-isolated | 1 | Channel mux |
| Arduino | Nano/Uno | 2 | DDS control + relay control |
| AD9833 DDS | GY-9833 module | 2 | Frequency synthesis |
| Glass plate | Borosilicate | 1+ | Acoustic medium under test |
| BNC cables | BNC-to-clip or BNC-to-screw | 2 | PicoScope Ch A + AWG output |

---

## Power Supply Configuration (Board D — CRITICAL)

Board D uses a **dual ±9V battery supply** — NOT the +5V USB supply.

```
+9V Battery:  (+) terminal → red rail (J-side edge)
              (−) terminal → AGND bus wire

−9V Battery:  (−) terminal → black rail (A-side edge)
              (+) terminal → AGND bus wire

AGND:         Board S blue GND rail → Board D AGND reference
              (This is the 0V midpoint between +9V and −9V)
```

**Why dual supply?** A single +5V supply caused 388 Hz oscillation with gain >1. The ±9V configuration eliminates oscillation and provides ±8V headroom.

---

## Signal Chain

```
┌─────────────┐     ┌──────────────┐     ┌────────────┐     ┌─────────┐
│ PicoScope   │     │  Board D     │     │  TX PZT    │     │  Glass  │
│ AWG         │────▶│  Buffer Amp  │────▶│  (drive)   │────▶│  Plate  │
│ (2 Vpp)     │     │  ×3.69 gain  │     │  (20 nF)   │     │         │
└─────────────┘     └──────────────┘     └────────────┘     └────┬────┘
                                                                  │
┌─────────────┐     ┌──────────────┐     ┌────────────┐          │
│ PicoScope   │     │  Board A     │     │  RX PZT    │          │
│ Ch A        │◀────│  Preamp ×11  │◀────│  (receive) │◀─────────┘
│ (measure)   │     │              │     │  (20 nF)   │
└─────────────┘     └──────────────┘     └────────────┘
```

---

## Board D — Drive Buffer (Verified Working)

### Specifications

| Parameter | Value |
|-----------|-------|
| Topology | Non-inverting amplifier, AC-coupled input |
| Gain (designed) | 1 + 22kΩ/10kΩ = **3.2×** |
| Gain (measured) | **3.69×** (within component tolerance) |
| Supply | ±9V (dual 9V batteries) |
| Input coupling | 100 nF film cap (AC only) |
| Bias | 100 kΩ to AGND (single resistor, no divider) |
| Output impedance | 47 Ω series resistor |
| Max output | 3.47 Vpp verified (±8V rails available) |

### Component Placement

| Ref | Value | Placement | Purpose |
|-----|-------|-----------|---------|
| U2 | OPA2134PA | E10–E13 / F10–F13 | Buffer amp (channel B active) |
| Rf | 22 kΩ | G11 → G12 | Feedback resistor |
| Rg | 10 kΩ | H12 → H14 | Gain-set to AGND (**direct, no series cap**) |
| R_BIAS | 100 kΩ | J13 → AGND rail | +IN B DC reference |
| R_OUT | 47 Ω | I11 → I20 | Output series isolator |
| C_IN | 100 nF film | G9 → G13 | Input AC coupling |
| C_byp+ | 100 nF ceramic | H10 → H14 | +9V bypass to AGND |
| C_byp− | 100 nF ceramic | D13 → D14 | −9V bypass to AGND |

### Wiring

| Step | From → To | Purpose |
|------|-----------|---------|
| +9V rail | Battery (+) → J-side red rail | +9V supply |
| −9V rail | Battery (−) → A-side black rail | −9V supply |
| AGND | Board S GND → Board D (midpoint) | 0V reference |
| V+ jumper | G10 → red +9V rail | Pin 8 power |
| V− jumper | B13 → black −9V rail | Pin 4 power |
| AGND-to-col14 | J14 → AGND rail | GND reference on F-J side |
| AGND-to-col5 | C5 → AGND rail | Source return ground |
| Input route | I5 → I9 | Source hot to coupling cap |
| Channel A park | C10→C11, D12→D13 | Unused half in unity follower |
| PZT return | A20 → AGND rail | Drive PZT ground |

### Known Behavior

- **DC offset at output:** ~+4V DC (from ~+660 mV at +IN B, amplified). This is **non-blocking** — the PZT is AC-coupled.
- **No oscillation** at any frequency with ±9V supply.
- **Gain stable** across 100 Hz – 50 kHz tested range.

---

## Running an Experiment

### 1. Power Up Sequence

```
1. Connect PicoScope USB to Mac
2. Connect both 9V batteries to Board D (red rail = +9V, black rail = −9V)
3. Connect Board S USB (Arduino power for DDS/relay)
4. Verify PicoScope detected:
   python -c "from picosdk.ps2000 import ps2000; h = ps2000.ps2000_open_unit(); print(f'Handle: {h}'); ps2000.ps2000_close_unit(h)"
```

### 2. Quick Signal Test (Board D Gain Verification)

```bash
cd /Users/Mike/Code/wcfoma
source .venv/bin/activate
python3 -c "
import ctypes as ct, os, time
import numpy as np
os.environ['DYLD_LIBRARY_PATH'] = '/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources'
from picosdk.ps2000 import ps2000

handle = ps2000.ps2000_open_unit()
ps2000.ps2000_set_channel(handle, 0, 1, 1, 8)
ps2000.ps2000_set_sig_gen_built_in(handle, 0, 1000000, 0, 4567, 4567, 0, 0, 0, 0)
time.sleep(0.5)

ps2000.ps2000_set_trigger(handle, 5, 0, 0, 0, 1)
ps2000.ps2000_run_block(handle, 2048, 7, 1, ct.byref(ct.c_int32()))
time.sleep(0.2)
for _ in range(100):
    if ps2000.ps2000_ready(handle):
        break
    time.sleep(0.05)

buf = (ct.c_int16 * 2048)()
ov = ct.c_int16(0)
ps2000.ps2000_get_values(handle, ct.byref(buf), None, None, None, ct.byref(ov), 2048, 0)
mv = np.array(buf, dtype=np.float64) * (5000.0 / 32767.0)

dc = mv.mean()
pp = mv.max() - mv.min()
print(f'DC: {dc:.1f} mV | AC: {pp:.1f} mV ({pp/1000:.3f} Vpp)')
if pp > 1500:
    print(f'Gain: {pp/939.5:.2f}x — PASS')
else:
    print(f'FAIL — expected >1500 mV, got {pp:.0f} mV')

ps2000.ps2000_set_sig_gen_built_in(handle, 0, 0, 0, 1000, 1000, 0, 0, 0, 0)
ps2000.ps2000_stop(handle)
ps2000.ps2000_close_unit(handle)
"
```

**Expected output:** `Gain: 3.69x — PASS`

### 3. Full Experiment (CWM Lab)

```bash
source .venv/bin/activate
PYTHONPATH=. python tools/cwm_lab.py --port 8200
# Open http://localhost:8200
```

### 4. Power Down Sequence

```
1. Stop any running scripts
2. Disconnect Board S USB
3. Disconnect both 9V batteries from Board D
4. Disconnect PicoScope USB
```

---

## PicoScope API Reference (ps2000)

| Function | Parameters | Notes |
|----------|-----------|-------|
| `ps2000_open_unit()` | — | Returns handle (int) |
| `ps2000_set_channel(h, ch, en, dc, range)` | ch=0(A)/1(B), range 8=±5V | |
| `ps2000_set_sig_gen_built_in(h, offset, pk2pk, wave, startf, stopf, ...)` | pk2pk in µV, freq in Hz | offset=0, wave=0(sine) |
| `ps2000_run_block(h, samples, timebase, ...)` | timebase 7 = 1280ns/sample | 781 kHz sample rate |
| `ps2000_get_values(h, buf, ...)` | 16-bit ADC values | Convert: mV = raw × (range_mV / 32767) |

**Library path:** `/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources/libps2000.dylib`

**ADC conversion:** `mV = raw_value × (5000.0 / 32767.0)` for ±5V range

---

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| Oscillation (any freq) | Single-supply +5V | Switch to ±9V dual battery |
| Output railed at +9V | Floating −IN B (no DC feedback) | Check Rg (H12→H14) is direct, no series cap |
| No AC at output | Bias resistor not grounded | Verify 100kΩ from J13 to AGND rail with continuity meter |
| Signal loss at C_IN | Bad breadboard contact | Retest with fresh cap, ensure leads firmly seated |
| +2.5V DC offset on scope | Broken probe ground wire | Replace BNC cable, check ground clip continuity |
| PicoScope not found | DYLD path not set | Export DYLD_LIBRARY_PATH before import |
| Relay not switching | JD-VCC header disconnected | Connect 5V header pin to screw terminal +5V |
| EMI pickup >1 mV | Mux bus wire unshielded | Twist mux wire with AGND return wire |

---

## Related Documentation

- **Full wiring guide:** `companion/breadboard_layout_v3.html` (open in browser)
- **Lab diaries:** `docs/lab_diary_*.md`
- **Experiment protocols:** `docs/PROTOCOLS.md`
- **Experiment guide:** `companion/experiment_guide.md`
