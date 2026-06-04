# Pico NCO — Flash & Deploy

## Quick Start

### 1. Install MicroPython on Pico

1. Hold **BOOTSEL** button on Pico, plug USB into Mac
2. Pico mounts as `RPI-RP2` drive
3. Download MicroPython UF2: https://micropython.org/download/RPI_PICO/
4. Drag the `.uf2` file onto `RPI-RP2` — Pico reboots automatically

### 2. Deploy firmware

```bash
# Install mpremote (one time)
pip install mpremote

# Copy firmware to Pico
mpremote cp tools/pico_nco/main.py :main.py

# Verify — should print banner and "OK"
mpremote run tools/pico_nco/main.py
```

Or use **Thonny** IDE: Open `tools/pico_nco/main.py`, save to Pico as `main.py`.

### 3. Verify from Mac

```bash
# Find port
ls /dev/cu.usbmodem*

# Quick test
python3 -c "
import serial, time
ser = serial.Serial('/dev/cu.usbmodem1101', 115200, timeout=2)
time.sleep(1)
ser.reset_input_buffer()
ser.write(b'STATUS\n')
time.sleep(0.2)
print(ser.readline().decode().strip())
ser.write(b'FREQ?\n')
time.sleep(0.2)
while ser.in_waiting:
    print(ser.readline().decode().strip())
ser.close()
"
```

### 4. Use from experiment scripts

```python
from tools.pico_nco import open_pico

nco = open_pico()
nco.set_freq(35840)       # CH1 → SW PZT
nco.set_freq2(97011)      # CH2 → NE PZT
nco.set_phase(45.0)       # CH2 leads CH1 by 45°
# ... run measurement ...
nco.off()
```

## Wiring

```
Pico GP2 ──[220Ω]──→ SW PZT (+)
Pico GP3 ──[220Ω]──→ NE PZT (+)
Pico GND ───────────→ PZT grounds, breadboard GND rail
Pico VBUS ──────────  (USB power only, nothing on breadboard VCC)
```

## Troubleshooting

| Symptom                     | Fix                                                              |
| --------------------------- | ---------------------------------------------------------------- |
| No `/dev/cu.usbmodem*`      | Replug USB. Try different cable (must be data, not charge-only)  |
| Port exists but no response | MicroPython not flashed. Redo step 1                             |
| `ERR:bad_freq`              | Frequency must be integer Hz                                     |
| Output too weak             | Check 220Ω resistor. Measure with scope: expect 3.3V square wave |
| Wrong frequency             | Run `FREQ?` command to see actual vs target                      |
