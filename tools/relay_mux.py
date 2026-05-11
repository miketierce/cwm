#!/usr/bin/env python3
"""
Python interface to the CWM Relay Multiplexer (Arduino Nano + 16-ch relay).

Provides a simple API to switch individual rod sense PZTs onto PicoScope
Channel A.  The Arduino firmware uses a newline-terminated serial protocol:
  '1'–'16' → activate relay N (break-before-make)
  '0'       → all relays off
  '?'       → query current state

All commands return "OK:N" where N is the active relay (0 = none).

Usage as library:
    from relay_mux import RelayMux
    with RelayMux() as mux:
        mux.select(1)       # Rod 1 on Ch A
        # ... capture ...
        mux.select(2)       # Rod 2 on Ch A
        # ... capture ...
        mux.off()            # all off

Usage from CLI:
    python tools/relay_mux.py                 # auto-detect, interactive
    python tools/relay_mux.py --port /dev/cu.usbserial-11310
    python tools/relay_mux.py --scan          # just list available ports
    python tools/relay_mux.py --select 3      # pulse relay 3, then all off on exit
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    print("ERROR: pyserial is required.  Install with:  pip install pyserial")
    sys.exit(1)


# ── Constants ─────────────────────────────────────────────────────────────

BAUD_RATE = 9600
TIMEOUT_S = 2.0        # serial read timeout
BOOT_WAIT_S = 2.5      # Arduino resets on serial open; wait for boot
CMD_SETTLE_S = 0.05    # time after sending command before reading response
CH340_DESCRIPTIONS = ("ch340", "ch341", "usb serial", "usbserial", "usbmodem")


# ── Port auto-detection ──────────────────────────────────────────────────

def find_arduino_port() -> str | None:
    """Auto-detect the Arduino Nano (CH340) serial port.

    Returns the device path string, or None if not found.
    Checks for CH340/CH341 USB-serial chips and common Arduino VID/PID pairs.
    """
    ports = serial.tools.list_ports.comports()
    candidates = []
    for p in ports:
        desc = (p.description or "").lower()
        hwid = (p.hwid or "").lower()
        # CH340/CH341 chips used by Nano clones
        if any(tag in desc for tag in CH340_DESCRIPTIONS):
            candidates.append(p.device)
        # Common CH340 USB VID:PID = 1a86:7523
        elif "1a86:7523" in hwid:
            candidates.append(p.device)
        # Arduino Nano VID:PID = 2341:0043 (genuine) or 1a86:7523 (clone)
        elif "2341:0043" in hwid:
            candidates.append(p.device)
    # Prefer /dev/cu.* over /dev/tty.* on macOS (cu doesn't block on DCD)
    cu = [p for p in candidates if "/dev/cu." in p]
    return cu[0] if cu else (candidates[0] if candidates else None)


def list_ports() -> list[dict]:
    """List all serial ports with metadata."""
    ports = serial.tools.list_ports.comports()
    return [
        {
            "device": p.device,
            "description": p.description,
            "hwid": p.hwid,
            "vid": p.vid,
            "pid": p.pid,
        }
        for p in sorted(ports, key=lambda p: p.device)
    ]


# ── RelayMux class ───────────────────────────────────────────────────────

class RelayMux:
    """Context-managed interface to the CWM relay multiplexer.

    Args:
        port: Serial port path.  None = auto-detect.
        boot_wait: Seconds to wait after opening serial (Arduino reset).
    """

    def __init__(self, port: str | None = None, boot_wait: float = BOOT_WAIT_S):
        self._port_path = port
        self._boot_wait = boot_wait
        self._ser: serial.Serial | None = None
        self._active: int = 0

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *exc):
        self.close()

    @property
    def active(self) -> int:
        """Currently active relay (0 = none, 1–16 = relay number)."""
        return self._active

    @property
    def port(self) -> str | None:
        """Serial port path in use."""
        return self._port_path

    @property
    def is_open(self) -> bool:
        return self._ser is not None and self._ser.is_open

    def open(self):
        """Open serial connection to the Arduino.

        If no port was specified, auto-detects the CH340 serial port.
        Waits for the Arduino to boot (it resets on serial open).
        """
        if self.is_open:
            return

        if self._port_path is None:
            self._port_path = find_arduino_port()
            if self._port_path is None:
                raise RuntimeError(
                    "No Arduino detected.  Plug in the Nano and check USB cable.\n"
                    "Available ports: " + str([p["device"] for p in list_ports()])
                )

        self._ser = serial.Serial(
            self._port_path,
            baudrate=BAUD_RATE,
            timeout=TIMEOUT_S,
        )

        # Arduino resets when DTR goes high (serial open).
        # Wait for bootloader + setup() to finish.
        time.sleep(self._boot_wait)

        # Drain any boot messages
        self._ser.reset_input_buffer()

        # Verify communication
        resp = self._send_cmd("?")
        if not resp.startswith("OK:"):
            raise RuntimeError(
                f"Unexpected response from Arduino: {resp!r}\n"
                f"Expected 'OK:N'.  Check firmware and wiring."
            )
        self._active = int(resp.split(":")[1])

    def close(self):
        """Turn all relays off and close serial port."""
        if self.is_open:
            try:
                self.off()
            except Exception:
                pass
            self._ser.close()
            self._ser = None

    def _send_cmd(self, cmd: str) -> str:
        """Send a command string and read the response line."""
        if not self.is_open:
            raise RuntimeError("RelayMux is not open")
        self._ser.write(f"{cmd}\n".encode("ascii"))
        time.sleep(CMD_SETTLE_S)
        line = self._ser.readline().decode("ascii", errors="replace").strip()
        return line

    def select(self, relay: int) -> int:
        """Activate a single relay (1–16).  Deactivates all others first.

        Args:
            relay: Relay number (1–16).

        Returns:
            The active relay number (should match input).

        Raises:
            ValueError: if relay is out of range.
            RuntimeError: if the Arduino responds with an error.
        """
        if not 1 <= relay <= 16:
            raise ValueError(f"Relay must be 1–16, got {relay}")
        resp = self._send_cmd(str(relay))
        if resp.startswith("OK:"):
            self._active = int(resp.split(":")[1])
        elif resp.startswith("ERR:"):
            raise RuntimeError(f"Relay error: {resp}")
        else:
            raise RuntimeError(f"Unexpected response: {resp!r}")
        return self._active

    def off(self) -> int:
        """Deactivate all relays (open circuit on Ch A).

        Returns:
            0 (no active relay).
        """
        resp = self._send_cmd("0")
        if resp.startswith("OK:"):
            self._active = int(resp.split(":")[1])
        return self._active

    def all_ne(self) -> int:
        """Unsupported by the 16-channel break-before-make firmware."""
        raise RuntimeError("all_ne() is not supported by relay_controller_16ch")

    def all_open(self) -> int:
        """Unsupported by the 16-channel break-before-make firmware."""
        raise RuntimeError("all_open() is not supported by relay_controller_16ch")

    def query(self) -> int:
        """Query current relay state without changing it."""
        resp = self._send_cmd("?")
        if resp.startswith("OK:"):
            self._active = int(resp.split(":")[1])
        return self._active

    def sweep(self, relays: list[int] | None = None,
              dwell_s: float = 0.5, callback=None):
        """Cycle through relays with optional callback at each.

        Args:
            relays: List of relay numbers to visit (default: 1–16).
            dwell_s: Time to hold each relay active.
            callback: Optional callable(relay_num) invoked after switching.
        """
        if relays is None:
            relays = list(range(1, 17))
        for r in relays:
            self.select(r)
            if callback:
                callback(r)
            time.sleep(dwell_s)
        self.off()


# ── CLI ───────────────────────────────────────────────────────────────────

def _interactive(mux: RelayMux):
    """Interactive relay control loop."""
    print(f"Connected to {mux.port}")
    print("Commands: 1–16 = select relay, 0/x = all off, ? = query, q = quit")
    while True:
        try:
            cmd = input("relay> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not cmd:
            continue
        if cmd.lower() in ("q", "quit", "exit"):
            break
        if cmd in [str(i) for i in range(17)]:
            if cmd == "0":
                mux.off()
                print(f"  All off")
            else:
                r = mux.select(int(cmd))
                print(f"  Relay {r} active")
        elif cmd == "?":
            print(f"  Active: {mux.query()}")
        elif cmd.lower() == "x":
            mux.off()
            print(f"  All off")
        elif cmd.lower() == "sweep":
            print("  Sweeping 1–16...")
            mux.sweep(dwell_s=1.0, callback=lambda r: print(f"    → Relay {r}"))
            print("  Done")
        else:
            print(f"  Unknown: {cmd!r}")
    print("Bye")


def main():
    parser = argparse.ArgumentParser(
        description="CWM Relay Multiplexer control"
    )
    parser.add_argument(
        "--port", type=str, default=None,
        help="Serial port (default: auto-detect CH340)"
    )
    parser.add_argument(
        "--scan", action="store_true",
        help="List available serial ports and exit"
    )
    parser.add_argument(
        "--select", type=int, default=None, metavar="N",
        help="Activate relay N (1–16), then turn all relays off on exit"
    )
    parser.add_argument(
        "--off", action="store_true",
        help="Turn all relays off and exit"
    )
    parser.add_argument(
        "--sweep", action="store_true",
        help="Sweep relays 1–16 with 1s dwell and exit"
    )
    args = parser.parse_args()

    if args.scan:
        ports = list_ports()
        if not ports:
            print("No serial ports found.")
        else:
            print(f"{'Device':<30} {'Description':<40} {'HWID'}")
            print(f"{'------':<30} {'-----------':<40} {'----'}")
            for p in ports:
                print(f"{p['device']:<30} {p['description']:<40} {p['hwid']}")
        auto = find_arduino_port()
        if auto:
            print(f"\nAuto-detected Arduino: {auto}")
        return

    with RelayMux(port=args.port) as mux:
        if args.select is not None:
            r = mux.select(args.select)
            print(f"Relay {r} active on {mux.port}")
        elif args.off:
            mux.off()
            print(f"All relays off on {mux.port}")
        elif args.sweep:
            print(f"Sweeping relays 1–16 on {mux.port}...")
            mux.sweep(dwell_s=1.0, callback=lambda r: print(f"  → Relay {r}"))
            print("Done")
        else:
            _interactive(mux)


if __name__ == "__main__":
    main()
