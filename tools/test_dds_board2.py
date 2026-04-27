#!/usr/bin/env python3
"""Quick test for AD9833 board #3 on FSYNC D8."""
import serial, time, ctypes, numpy as np

PORT = "/dev/cu.usbserial-11330"
FREQS = [1000, 10000, 50000]
DDS_CH = 3  # F3: commands, FSYNC on D8

ser = serial.Serial(PORT, 9600, timeout=2)
time.sleep(2)
boot = ser.readline().decode("ascii", errors="replace").strip()
print("Boot:", boot)

ps = ctypes.CDLL("libps2000.dylib")
h = ps.ps2000_open_unit()
ps.ps2000_set_channel(h, 0, 1, 1, 7)   # Ch A enabled
ps.ps2000_set_channel(h, 1, 0, 1, 7)   # Ch B disabled

results = []
for freq in FREQS:
    ser.reset_input_buffer()
    cmd = "F%d:%d\n" % (DDS_CH, freq)
    ser.write(cmd.encode())
    time.sleep(0.05)
    resp = ser.readline().decode("ascii", errors="replace").strip()
    print("\n--- %d Hz ---" % freq)
    print("  Sent: F%d:%d  Response: %s" % (DDS_CH, freq, resp))

    ser.write(b"D?\n")
    time.sleep(0.05)
    q = ser.readline().decode("ascii", errors="replace").strip()
    print("  Query: %s" % q)

    serial_ok = ("DDS:%d" % freq) in resp or ("%d=%d" % (DDS_CH, freq)) in q
    label = "PASS" if serial_ok else "FAIL"
    print("  Serial: %s" % label)

    # PicoScope capture
    time.sleep(0.2)
    ps.ps2000_set_trigger(h, 5, 0, 0, 0, 100)
    t_ms = ctypes.c_int32()
    ps.ps2000_run_block(h, 8064, 7, 1, ctypes.byref(t_ms))
    t0 = time.time()
    while ps.ps2000_ready(h) == 0:
        time.sleep(0.001)
        if time.time() - t0 > 5:
            break

    buf_a = (ctypes.c_int16 * 8064)()
    buf_b = (ctypes.c_int16 * 8064)()
    ov = ctypes.c_int16()
    n = ps.ps2000_get_values(h, ctypes.byref(buf_a), ctypes.byref(buf_b),
                             None, None, ctypes.byref(ov), 8064)

    data = np.array(buf_a[:n], dtype=float)
    data -= np.mean(data)
    dt = 1280e-9
    fs = 1.0 / dt
    spectrum = np.abs(np.fft.rfft(data * np.hanning(len(data))))
    freqs_arr = np.fft.rfftfreq(len(data), d=dt)
    min_bin = int(500 / (fs / len(data))) + 1
    peak_idx = np.argmax(spectrum[min_bin:]) + min_bin
    peak_freq = freqs_arr[peak_idx]
    peak_mag = spectrum[peak_idx]
    noise = np.median(spectrum[min_bin:])
    snr = peak_mag / noise if noise > 0 else 0
    freq_err = abs(peak_freq - freq) / freq
    pico_ok = freq_err < 0.05 and snr > 5
    label = "PASS" if pico_ok else "FAIL"
    print("  Peak: %.0f Hz, SNR: %.0fx  Pico: %s" % (peak_freq, snr, label))
    results.append((serial_ok, pico_ok))

ser.write(("F%d:off\n" % DDS_CH).encode())
time.sleep(0.05)
ser.readline()
ser.close()
ps.ps2000_stop(h)
ps.ps2000_close_unit(h)

s = sum(r[0] for r in results)
p = sum(r[1] for r in results)
print("\n===  BOARD #%d (D%d):  Serial %d/3  PicoScope %d/3  ===" % (DDS_CH, 11 - DDS_CH, s, p))
if s == 3 and p == 3:
    print("BOARD #%d GOOD" % DDS_CH)
elif s == 3:
    print("SPI OK but no analog output -- check OUT solder")
else:
    print("BOARD #2 FAIL")
