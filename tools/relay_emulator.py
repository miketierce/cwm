#!/usr/bin/env python3
"""
Software emulator for the CWM relay controller Arduino sketch.

Creates a virtual serial port (pseudo-terminal) that behaves exactly like
the real Arduino Nano running relay_controller.ino.  This lets you test
relay_mux.py and awg_stepped_dwell_id.py --mux without any hardware.

Usage:
    # Terminal 1: start the emulator
    python tools/relay_emulator.py
    # It will print something like: "Virtual port: /dev/ttys004"

    # Terminal 2: test relay_mux against it
    python tools/relay_mux.py --port /dev/ttys004
    # Or:
    python tools/relay_mux.py --port /dev/ttys004 --select 3

    # Or run the identifier in mux mode against the emulator:
    PYTHONPATH=. python tools/awg_stepped_dwell_id.py --mux --port /dev/ttys004

Press Ctrl+C to stop the emulator.
"""
from __future__ import annotations

import os
import select
import sys
import tty
import termios


def main():
    # Create a pseudo-terminal pair
    master_fd, slave_fd = os.openpty()
    slave_name = os.ttyname(slave_fd)

    # Configure the slave side like a serial port (raw mode, no echo)
    attrs = termios.tcgetattr(slave_fd)
    tty.setraw(slave_fd)
    # Set baud rate to 9600 (B9600 = 13 on most systems)
    try:
        termios.cfsetispeed(attrs, termios.B9600)
        termios.cfsetospeed(attrs, termios.B9600)
        termios.tcsetattr(slave_fd, termios.TCSANOW, attrs)
    except Exception:
        pass  # PTY baud rate is virtual anyway

    print(f"╔══════════════════════════════════════════════════╗")
    print(f"║  CWM Relay Controller Emulator                  ║")
    print(f"║  Virtual port: {slave_name:<33} ║")
    print(f"║  Protocol: 9600 baud, '1'-'8'/0/x/?             ║")
    print(f"║  Press Ctrl+C to stop                           ║")
    print(f"╚══════════════════════════════════════════════════╝")
    print()

    active_relay = 0
    BBM_DELAY = 0.005  # emulate 5ms break-before-make (negligible in practice)

    # Send boot message (like the real Arduino)
    boot_msg = "OK:0\r\n"
    os.write(master_fd, boot_msg.encode())
    print(f"[EMU] Boot → OK:0")

    try:
        while True:
            # Wait for data on the master side (what pyserial writes to slave)
            rlist, _, _ = select.select([master_fd], [], [], 1.0)
            if not rlist:
                continue

            data = os.read(master_fd, 256)
            if not data:
                break

            for byte in data:
                cmd = chr(byte)

                # Skip whitespace
                if cmd in ('\n', '\r'):
                    continue

                if '1' <= cmd <= '8':
                    relay = int(cmd)
                    # Break-before-make: all off, then activate
                    old = active_relay
                    active_relay = relay
                    resp = f"OK:{active_relay}\r\n"
                    os.write(master_fd, resp.encode())
                    print(f"[EMU] '{cmd}' → relay {old}→{active_relay}  {resp.strip()}")

                elif cmd in ('0', 'x', 'X'):
                    old = active_relay
                    active_relay = 0
                    resp = f"OK:{active_relay}\r\n"
                    os.write(master_fd, resp.encode())
                    print(f"[EMU] '{cmd}' → relay {old}→OFF  {resp.strip()}")

                elif cmd == '?':
                    resp = f"OK:{active_relay}\r\n"
                    os.write(master_fd, resp.encode())
                    print(f"[EMU] '?' → {resp.strip()}")

                else:
                    resp = f"ERR:unknown command '{cmd}'\r\n"
                    os.write(master_fd, resp.encode())
                    print(f"[EMU] '{cmd}' → {resp.strip()}")

    except KeyboardInterrupt:
        print(f"\n[EMU] Shutting down")
    finally:
        os.close(master_fd)
        os.close(slave_fd)
        print(f"[EMU] Closed {slave_name}")


if __name__ == "__main__":
    main()
