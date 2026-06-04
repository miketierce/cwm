"""Drop-in replacement for DDS class — drives Pico NCO over USB serial.

API-compatible with dds_ad9833.DDS so existing experiment scripts work
unchanged. Just swap the import and serial port.

Usage:
    import serial
    from pico_nco.dds_pico import PicoNCO

    ser = serial.Serial('/dev/cu.usbmodem*', 115200, timeout=2)
    nco = PicoNCO(ser)
    nco.set_freq(35840)           # CH1 (legacy single-channel)
    nco.set_freq2(97011)          # CH2
    nco.set_phase(45.0)           # CH2 phase offset in degrees
    nco.off()
"""

import time
import serial


class PicoNCO:
    """Pico PIO NCO controller via USB CDC serial.

    Drop-in replacement for dds_ad9833.DDS with added dual-channel
    and phase control capabilities.
    """

    def __init__(self, ser: serial.Serial):
        """Wrap an already-open serial connection to the Pico.

        Args:
            ser: Open serial.Serial instance (Pico USB CDC).
        """
        self._ser = ser
        # Wait for Pico boot banner
        time.sleep(0.1)
        self._ser.reset_input_buffer()

    def _cmd(self, command: str, timeout: float = 0.5) -> str:
        """Send command, return response line."""
        self._ser.reset_input_buffer()
        self._ser.write(f"{command}\n".encode("ascii"))
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._ser.in_waiting:
                resp = self._ser.readline().decode("ascii", errors="replace").strip()
                if resp:
                    return resp
            time.sleep(0.005)
        return ""

    # ── API compatible with dds_ad9833.DDS ──

    def set_freq(self, freq_hz: float) -> int:
        """Set CH1 output frequency in Hz.

        Args:
            freq_hz: Target frequency (0 = off).

        Returns:
            Confirmed frequency from Pico.
        """
        freq_int = int(round(freq_hz))
        resp = self._cmd(f"F1:{freq_int}")
        if resp.startswith("DDS:"):
            return int(resp.split(":")[1])
        raise RuntimeError(f"set_freq failed: {resp!r}")

    def set_freq2(self, freq_hz: float) -> int:
        """Set CH2 output frequency in Hz.

        Args:
            freq_hz: Target frequency (0 = off).

        Returns:
            Confirmed frequency from Pico.
        """
        freq_int = int(round(freq_hz))
        resp = self._cmd(f"F2:{freq_int}")
        if resp.startswith("DDS2:"):
            return int(resp.split(":")[1])
        raise RuntimeError(f"set_freq2 failed: {resp!r}")

    def set_phase(self, degrees: float) -> float:
        """Set CH2 phase offset relative to CH1.

        Args:
            degrees: Phase offset (0–360).

        Returns:
            Confirmed phase in degrees.
        """
        resp = self._cmd(f"PHASE:{degrees:.4f}")
        if resp.startswith("PHASE:"):
            return float(resp.split(":")[1])
        raise RuntimeError(f"set_phase failed: {resp!r}")

    def set_phase_reg(self, channel: int, reg_value: int) -> str:
        """Legacy AD9833 phase register command (12-bit, 0–4095).

        Provided for backward compatibility with t5_2_chsh.py.
        """
        resp = self._cmd(f"P{channel}:{reg_value}")
        return resp

    def off(self):
        """Silence both outputs (pins LOW)."""
        resp = self._cmd("Foff")
        return resp

    def query(self) -> int:
        """Query current CH1 frequency."""
        resp = self._cmd("D?")
        if resp.startswith("DDS:"):
            return int(resp.split(":")[1])
        return 0

    def status(self) -> str:
        """Get full status report."""
        return self._cmd("STATUS")

    def freq_check(self) -> str:
        """Show eigenmode frequency accuracy."""
        return self._cmd("FREQ?")

    def sweep(self, start: float, stop: float, step: float,
              callback=None) -> int:
        """Run phase sweep on Pico.

        Args:
            start: Start phase (degrees).
            stop: Stop phase (degrees).
            step: Step size (degrees).
            callback: Optional function called with each phase value.

        Returns:
            Number of sweep steps completed.
        """
        self._ser.reset_input_buffer()
        self._ser.write(f"SWEEP:{start}:{stop}:{step}\n".encode("ascii"))

        n_steps = 0
        deadline = time.time() + 60.0  # generous timeout for long sweeps
        while time.time() < deadline:
            if self._ser.in_waiting:
                line = self._ser.readline().decode("ascii", errors="replace").strip()
                if line.startswith("SWEEP_PT:"):
                    phase = float(line.split(":")[1])
                    n_steps += 1
                    if callback:
                        callback(phase)
                elif line.startswith("SWEEP_DONE:"):
                    return int(line.split(":")[1])
            time.sleep(0.005)
        return n_steps


# ── Convenience: auto-detect Pico serial port ──

def find_pico_port() -> str:
    """Find the Pico's USB CDC serial port on macOS.

    Returns:
        Port path string (e.g., '/dev/cu.usbmodem1234').

    Raises:
        RuntimeError if no Pico found.
    """
    import glob
    candidates = glob.glob("/dev/cu.usbmodem*")
    if not candidates:
        raise RuntimeError(
            "No Pico found. Check USB connection. "
            "Expected /dev/cu.usbmodem*"
        )
    if len(candidates) == 1:
        return candidates[0]
    # Multiple — try each, look for banner
    for port in candidates:
        try:
            ser = serial.Serial(port, 115200, timeout=1)
            time.sleep(0.1)
            ser.write(b"STATUS\n")
            time.sleep(0.2)
            resp = ser.read(ser.in_waiting).decode(errors="replace")
            ser.close()
            if "CLK:" in resp:
                return port
        except (serial.SerialException, OSError):
            continue
    # Fall back to first
    return candidates[0]


def open_pico(**kwargs) -> PicoNCO:
    """Auto-detect Pico and return ready PicoNCO instance.

    Usage:
        nco = open_pico()
        nco.set_freq(35840)
    """
    port = find_pico_port()
    ser = serial.Serial(port, 115200, timeout=2, **kwargs)
    time.sleep(0.5)  # wait for MicroPython boot
    ser.reset_input_buffer()
    return PicoNCO(ser)
