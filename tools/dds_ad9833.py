"""Thin wrapper for AD9833 DDS control via the relay_controller_dds firmware.

Works alongside RelayMux — same serial connection, extended command set.
The firmware accepts 'F<freq>\n' for DDS and '1'–'8' for relays on the same port.
"""

import time
import serial


class DDS:
    """AD9833 DDS controller via Arduino serial.

    Uses the same serial connection as RelayMux (relay_controller_dds firmware).
    """

    def __init__(self, ser: serial.Serial):
        """Wrap an already-open serial connection.

        Args:
            ser: Open serial.Serial instance (shared with RelayMux).
        """
        self._ser = ser

    def set_freq(self, freq_hz: float) -> int:
        """Set DDS output frequency in Hz.

        Args:
            freq_hz: Target frequency (1–12,500,000 Hz).

        Returns:
            Confirmed frequency from Arduino.
        """
        cmd = f"F{int(round(freq_hz))}\n"
        self._ser.write(cmd.encode("ascii"))
        time.sleep(0.005)
        resp = self._ser.readline().decode("ascii", errors="replace").strip()
        if resp.startswith("DDS:"):
            return int(resp.split(":")[1])
        raise RuntimeError(f"DDS set_freq failed: {resp!r}")

    def off(self):
        """Silence DDS output (hold reset)."""
        self._ser.write(b"Foff\n")
        time.sleep(0.005)
        self._ser.readline()

    def query(self) -> int:
        """Query current DDS frequency."""
        self._ser.write(b"D?\n")
        time.sleep(0.005)
        resp = self._ser.readline().decode("ascii", errors="replace").strip()
        if resp.startswith("DDS:"):
            return int(resp.split(":")[1])
        return 0
