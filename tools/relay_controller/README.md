# CWM Relay Multiplexer Controller

Arduino Nano firmware for the 8-channel relay module that switches individual rod sense PZTs onto PicoScope Channel A.

## Hardware

| Component | Specification |
|-----------|--------------|
| Arduino Nano | ATmega328P clone with CH340 USB-serial (Type-C) |
| Relay module | 8-channel, 5V, opto-isolated, active-LOW, screw terminals |
| Jumper wires | Female-to-female DuPont, 10 cm |

## Wiring

```
Arduino Nano          8-Channel Relay Module
─────────────         ─────────────────────
D2  ──────────────→   IN1  (Rod 1 sense PZT)
D3  ──────────────→   IN2  (Rod 2 sense PZT)
D4  ──────────────→   IN3  (Rod 3 sense PZT)
D5  ──────────────→   IN4  (Rod 4 sense PZT)
D6  ──────────────→   IN5  (Rod 5, optional)
D7  ──────────────→   IN6  (Rod 6, optional)
D8  ──────────────→   IN7  (Rod 7, optional)
D9  ──────────────→   IN8  (Rod 8, optional)
5V  ──────────────→   VCC
GND ──────────────→   GND
```

Each relay's **COM** terminal connects to a rod's sense PZT hot wire. All relay **NO** (normally open) terminals are joined together and wired to PicoScope Ch A hot. All sense PZT grounds share a common bus to Ch A ground.

## Prerequisites

Install `arduino-cli` (one time):

```bash
brew install arduino-cli                    # macOS
arduino-cli core install arduino:avr        # AVR toolchain for Nano
```

## Compile (verify without flashing)

```bash
arduino-cli compile --fqbn arduino:avr:nano tools/relay_controller
```

Expected output:
```
Sketch uses 2724 bytes (8%) of program storage space.
Global variables use 236 bytes (11%) of dynamic memory.
```

## Flash

1. Plug in the Arduino Nano via USB.

2. Find the port:

   ```bash
   arduino-cli board list
   ```

   Look for a CH340 entry — typically `/dev/cu.usbserial-XXXX` on macOS.

3. Upload:

   ```bash
   arduino-cli upload \
     -p /dev/cu.usbserial-XXXX \
     --fqbn arduino:avr:nano \
     tools/relay_controller
   ```

   > **Clone with old bootloader?** If upload fails with a sync error, the Nano clone may use the older bootloader. Add the CPU option:
   > ```bash
   > arduino-cli upload \
   >   -p /dev/cu.usbserial-XXXX \
   >   --fqbn arduino:avr:nano:cpu=atmega328old \
   >   tools/relay_controller
   > ```

4. Verify — the onboard LED (pin 13) will blink 3 times on boot.

## Serial Protocol

9600 baud, 8N1. Send a single ASCII character; the Arduino responds with a newline-terminated string.

| Send | Action | Response |
|------|--------|----------|
| `1`–`8` | Activate that relay (all others off first) | `OK:N` |
| `0` or `x` | All relays off (open circuit) | `OK:0` |
| `?` | Query current state | `OK:N` |

Switching is break-before-make: all relays open for 5 ms before the new relay closes. Total switching time ~10 ms.

## Testing Without Hardware

A PTY-based emulator replicates the Arduino's serial protocol on a virtual port:

```bash
# Terminal 1 — start emulator
python tools/relay_emulator.py
# Prints: "Virtual port: /dev/ttysXXX"

# Terminal 2 — test against it
python tools/relay_mux.py --port /dev/ttysXXX --select 1
python tools/relay_mux.py --port /dev/ttysXXX --sweep
```

## Python Integration

The `relay_mux.py` driver auto-detects the CH340 port:

```python
from relay_mux import RelayMux

with RelayMux() as mux:          # auto-detect port, wait for boot
    mux.select(1)                 # Rod 1 on Ch A
    # ... capture spectrum ...
    mux.select(2)                 # Rod 2 on Ch A
    # ... capture spectrum ...
    mux.off()                     # all relays open
```

Or specify the port explicitly:

```python
with RelayMux(port="/dev/cu.usbserial-1410") as mux:
    mux.select(3)
```

CLI usage:

```bash
python tools/relay_mux.py --scan              # list serial ports
python tools/relay_mux.py                     # interactive mode
python tools/relay_mux.py --select 3          # activate relay 3
python tools/relay_mux.py --sweep             # cycle 1→2→3→4→off
python tools/relay_mux.py --off               # all off
```

## Running the Identifier with Relay Mux

```bash
# Without mux (shared Ch A, all rods blended — original mode)
PYTHONPATH=. python tools/awg_stepped_dwell_id.py

# With mux (per-rod isolation — switches relay before each rod's measurement)
PYTHONPATH=. python tools/awg_stepped_dwell_id.py --mux

# With explicit port
PYTHONPATH=. python tools/awg_stepped_dwell_id.py --mux --port /dev/cu.usbserial-1410
```

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `arduino-cli upload` sync error | Try `--fqbn arduino:avr:nano:cpu=atmega328old` |
| Port not found after plugging in | Install CH340 driver: [macOS download](https://www.wch-ic.com/downloads/CH341SER_MAC_ZIP.html) |
| `relay_mux.py` hangs on open | Arduino resets on serial connect — the 2.5s boot wait handles this. If it still hangs, check the port with `screen /dev/cu.usbserial-XXXX 9600` |
| Relay clicks but PicoScope sees nothing | Check that the NO terminal (not NC) is wired to Ch A. Verify with a multimeter in continuity mode. |
| All relays stuck on at boot | The sketch sets all pins HIGH (relay OFF) in `setup()`. If relays are active-HIGH instead of active-LOW, swap `RELAY_ON`/`RELAY_OFF` constants in the sketch. |
