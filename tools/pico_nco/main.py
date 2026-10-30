"""
Pico PIO+PWM NCO — 15-tone phase-coherent signal generator
==========================================================
Firmware for Raspberry Pi Pico H (RP2040).
Replaces two dead AD9833 DDS modules for CWM experiments.

Architecture (v2.0, 2026-06-22 — maxed for WL-B10 multipoint arrays):
  - System clock: 126 MHz (all four glass eigenmodes within resonance bandwidth)
  - 15 independent tones in THREE phase-coherent blocks:
      Block A = PIO0 SM0-3 → CH1-4 → GP2,3,4,5 (pins 4,5,6,7).
                4 tones phase-locked (PH1-4): interference / multi-TX plate 1.
      Block B = PIO1 SM0-3 → CH5-8 → GP6,7,8,9 (pins 9,10,11,12).
                4 tones phase-locked (PH5-8): interference / multi-TX plate 2.
                → either PIO block holds 3 (or 4) TX in phase for a large plate.
      Block C = PWM slices 0,1,2,3,5,6,7 → CH9-15 → GP16,18,20,22,10,12,14.
                7 independent tones, sync-started phase-aligned at 0°.
  - Phase is coherent WITHIN a block, not across blocks.
  - Why 15 not 16: PWM slice 4 routes only to GP8/GP9 (used by Block B) or
    GP24/GP25 (not on the header), so 7 PWM tones is the clean header maximum.
  - 3.3 V square wave → 220 Ω → PZT (fundamental ≈ 2.1 Vpp). PWM also square.

v2.1 (2026-10-29): adds Fz, a stop that leaves the drive pins high-impedance, so a
ringdown can be compared with the TX PZTs open-circuit instead of grounded through
220 Ω (worklist O5). Every other command is unchanged.

Serial protocol (USB CDC, appears as /dev/cu.usbmodem*):
  F1:<hz>..F8:<hz>   Set PIO channel frequency (0 = off). CH1-4 Block A, CH5-8 Block B.
  F9:<hz>..F15:<hz>  Set PWM channel frequency (0 = off). Block C.
  F<hz>              Set CH1 frequency (legacy single-channel mode)
  A<ch>:<permille>   Channel DUTY = amplitude (10..500 = 1%..50%, any ch 1-15).
                     Fundamental amplitude ∝ sin(π·duty); 500 = max. ('amplitude of
                     a fixed mode' encoding, T3.4.)
  Foff               Stop all outputs (pins LOW)
  Fz                 Stop all outputs, pins high-impedance (TX PZTs open-circuit)
  PHASE:<deg>        Set CH2 phase offset relative to CH1 (alias of PH2)
  PH1:<deg>..PH4:<deg>  Per-channel absolute phase for Block A (CH1-4, PIO0).
  PH5:<deg>..PH8:<deg>  Per-channel absolute phase for Block B (CH5-8, PIO1).
                     Drive N channels at the SAME freq on one plate, each at its
                     own phase → N-path interference sum |Σ aₖ e^{iφₖ}| ². Up to
                     4 phase-locked TX per PIO block.
  STATUS             Report full state (CH1-8, PWM, DUTY, PHA, PHB)
  FREQ?              Show eigenmode frequency errors
  SWEEP:<s>:<e>:<step>  CH2 phase sweep, reports "SWEEP_PT:<deg>" at each step
  TEMP / TIME        RP2040 die temperature / uptime

Install: Copy this file to Pico as main.py (via Thonny or mpremote).
Backup of the previous 6-channel firmware: tools/pico_nco/main_v1.1_6ch_backup.py
"""

import machine
import rp2
from rp2 import PIO, StateMachine, asm_pio
import sys
import select
import time

# ─── Internal Sensors ────────────────────────────────────────────
# RP2040 ADC4 = internal temperature sensor
# Conversion: T(°C) = 27 - (V - 0.706) / 0.001721
_adc_temp = machine.ADC(4)
_boot_ticks = time.ticks_us()

# ─── System Clock ────────────────────────────────────────────────
# 126 MHz gives all four eigenmodes within resonance bandwidth.
# Well within RP2040 spec (rated 133 MHz, commonly run at 250 MHz).
machine.freq(126_000_000)
SYS_CLK = machine.freq()

# ─── Pin Assignments ─────────────────────────────────────────────
# Block A = PIO0 SM0-3 (one phase-locked quad) — interference / multi-TX plate 1
PIN_CH1 = 2    # GP2  pin4  — Block A TX1
PIN_CH2 = 3    # GP3  pin5  — Block A TX2
PIN_CH3 = 4    # GP4  pin6  — Block A TX3
PIN_CH4 = 5    # GP5  pin7  — Block A TX4
# Block B = PIO1 SM0-3 (one phase-locked quad) — interference / multi-TX plate 2
PIN_CH5 = 6    # GP6  pin9  — Block B TX1
PIN_CH6 = 7    # GP7  pin10 — Block B TX2
PIN_CH7 = 8    # GP8  pin11 — Block B TX3 (added 2026-06-22, PIO1 SM2)
PIN_CH8 = 9    # GP9  pin12 — Block B TX4 (added 2026-06-22, PIO1 SM3)
# Block C = PWM slices (sync-started, phase-aligned at 0°) — independent tones.
# CH9-15 → PWM slices 0,1,2,3,5,6,7. (Slice 4 only routes to GP8/GP9 — taken by
# Block B — or GP24/GP25 which are not on the Pico header, so it is unavailable.
# 7 PWM tones is the clean header maximum → 8 PIO + 7 PWM = 15 independent tones.)
PWM_PINS = {9: 16, 10: 18, 11: 20, 12: 22, 13: 10, 14: 12, 15: 14}
#  CH  GP  pin  slice          CH  GP  pin  slice
#   9  16  21   s0             12  22  29   s3
#  10  18  24   s1             13  10  14   s5
#  11  20  26   s2             14  12  16   s6
#                              15  14  19   s7
PWM_BASE = 0x40050000          # RP2040 PWM peripheral base
PWM_EN = PWM_BASE + 0xa0       # one bit per slice → single write starts all in phase
LED_PIN = 25   # Onboard LED — blinks on command receipt

led = machine.Pin(LED_PIN, machine.Pin.OUT)

# ─── PIO NCO Program ────────────────────────────────────────────
# Each state machine runs this program independently.
# Timing per main-loop iteration:
#   HIGH phase: set(pins,1)[1] + mov(x,y)[1] + jmp_loop[high+1] = high + 3
#   LOW phase:  set(pins,0)[1] + mov(x,isr)[1] + jmp_loop[low+1] = low + 3
#   Total period = high + low + 6 clock ticks
#
# First cycle uses X directly (no mov from Y), so:
#   First HIGH = set[1] + jmp_loop[first_high+1] = first_high + 2
#   First LOW  = set[1] + mov[1] + jmp_loop[low+1] = low + 3
#   First period = first_high + low + 5
#
# Phase offset: SM1's first_high is extended by delay_ticks,
# permanently shifting its waveform relative to SM0.

@asm_pio(set_init=PIO.OUT_LOW)
def nco_prog():
    # ── Initialization (runs once) ──
    pull(block)              # Get first_high_count from FIFO
    mov(x, osr)             # X = first_high_count
    pull(block)              # Get low_count
    mov(isr, osr)           # ISR = low_count (permanent)
    pull(block)              # Get normal_high_count
    mov(y, osr)             # Y = normal_high_count (permanent)

    # ── First cycle (may be extended for phase offset) ──
    set(pins, 1)            # Output HIGH
    label("first_h")
    jmp(x_dec, "first_h")   # Count: first_high + 1 cycles

    set(pins, 0)            # Output LOW
    mov(x, isr)             # X = low_count
    label("first_l")
    jmp(x_dec, "first_l")   # Count: low + 1 cycles

    # ── Main loop (constant period, runs forever) ──
    wrap_target()
    set(pins, 1)            # Output HIGH
    mov(x, y)               # X = normal_high_count
    label("high")
    jmp(x_dec, "high")      # Count: high + 1 cycles

    set(pins, 0)            # Output LOW
    mov(x, isr)             # X = low_count
    label("low")
    jmp(x_dec, "low")       # Count: low + 1 cycles
    wrap()


# ─── Frequency Calculation ───────────────────────────────────────
OVERHEAD = 6   # Fixed overhead per main-loop period (ticks)

def freq_to_counts(freq_hz):
    """Convert target frequency to (high_count, low_count) for PIO.

    Returns (high, low) such that period = high + low + 6 ticks.
    Near-50% duty cycle; for odd periods, HIGH gets the extra tick.
    """
    if freq_hz <= 0:
        return (1, 1)
    period = round(SYS_CLK / freq_hz)
    remainder = period - OVERHEAD
    if remainder < 2:
        remainder = 2
    high = (remainder + 1) // 2   # ceil
    low = remainder // 2          # floor
    return (high, low)


def counts_to_freq(high, low):
    """Convert PIO counts back to actual output frequency."""
    period = high + low + OVERHEAD
    return SYS_CLK / period


def counts_to_period(high, low):
    """Total period in clock ticks."""
    return high + low + OVERHEAD


def pwm_slice(gp):
    """RP2040 PWM slice (0-7) that owns a GPIO."""
    return (gp >> 1) & 0x7


def apply_duty(high, low, duty_permille):
    """Re-split a (high, low) pair to a target duty cycle WITHOUT changing the
    total period (so the frequency is unchanged). duty_permille is the HIGH
    fraction in permille (10..500 = 1%..50%).

    A square wave's FUNDAMENTAL amplitude at the drive frequency scales as
    sin(π·duty), so sweeping duty from 50% down toward 0% gives a clean,
    MONOTONIC amplitude knob on the existing fixed-voltage NCO — enabling the
    proven 'amplitude of a fixed mode' encoding (T3.4) with no rewiring.
    Harmonics move to 3f/5f and are rejected by the plate resonance.
    """
    active = high + low
    if active < 2:
        return (1, 1)
    nh = (active * duty_permille + 500) // 1000   # rounded
    if nh < 1:
        nh = 1
    if nh > active - 1:
        nh = active - 1
    return (nh, active - nh)


# ─── State ───────────────────────────────────────────────────────
sm0 = None
sm1 = None
sm2 = None
sm3 = None
sm4 = None
sm5 = None
sm6 = None
sm7 = None
current_freq1 = 0
current_freq2 = 0
current_freq3 = 0
current_freq4 = 0
current_freq5 = 0
current_freq6 = 0
current_freq7 = 0
current_freq8 = 0
current_phase = 0.0    # degrees, CH2 relative to CH1 (alias: PH2 / PHASE)
# Per-channel phase (deg). Block A (PIO0, CH1-4) phase-locks via PH1-4; Block B
# (PIO1, CH5-8) phase-locks via PH5-8. Phase is coherent WITHIN a PIO block
# (shared simultaneous start), NOT across blocks. Two PIO blocks = two
# independent interference-capable plates, each holding up to 4 TX in phase.
# All phases 0 = bit-for-bit the legacy behavior.
current_phase1 = 0.0
current_phase3 = 0.0
current_phase4 = 0.0
current_phase5 = 0.0
current_phase6 = 0.0
current_phase7 = 0.0
current_phase8 = 0.0
# Per-channel duty cycle (permille of period high). 500 = 50% = MAX amplitude.
# Lower duty = lower fundamental amplitude (amp ∝ sin(π·duty)). Amplitude knob.
duty1 = 500
duty2 = 500
duty3 = 500
duty4 = 500
duty5 = 500
duty6 = 500
duty7 = 500
duty8 = 500
# Block C — PWM tone state (CH9-15). Independent tones; phase-aligned at start.
pwm_freq = {ch: 0 for ch in PWM_PINS}
pwm_duty = {ch: 500 for ch in PWM_PINS}
pwm_obj = {ch: None for ch in PWM_PINS}
running = False
pins_floating = False  # True after Fz: idle drive pins are inputs, not driven LOW

# PIO0 control register for simultaneous SM start
PIO0_BASE = 0x50200000
PIO_CTRL = PIO0_BASE + 0x000

# PIO1 control register (CH5 lives here — PIO0 has only 4 state machines)
PIO1_BASE = 0x50300000
PIO1_CTRL = PIO1_BASE + 0x000


# ─── Oscillator Control ──────────────────────────────────────────
def start_oscillators():
    """Start all active channels with current freq/phase settings."""
    global sm0, sm1, sm2, sm3, sm4, sm5, sm6, sm7, running

    stop_oscillators()

    any_pwm = any(pwm_freq[ch] > 0 for ch in PWM_PINS)
    if (current_freq1 <= 0 and current_freq2 <= 0 and current_freq3 <= 0
            and current_freq4 <= 0 and current_freq5 <= 0 and current_freq6 <= 0
            and current_freq7 <= 0 and current_freq8 <= 0 and not any_pwm):
        return

    h1, l1 = freq_to_counts(current_freq1) if current_freq1 > 0 else (1, 1)
    h2, l2 = freq_to_counts(current_freq2) if current_freq2 > 0 else (1, 1)
    h3, l3 = freq_to_counts(current_freq3) if current_freq3 > 0 else (1, 1)
    h4, l4 = freq_to_counts(current_freq4) if current_freq4 > 0 else (1, 1)
    h5, l5 = freq_to_counts(current_freq5) if current_freq5 > 0 else (1, 1)
    h6, l6 = freq_to_counts(current_freq6) if current_freq6 > 0 else (1, 1)
    h7, l7 = freq_to_counts(current_freq7) if current_freq7 > 0 else (1, 1)
    h8, l8 = freq_to_counts(current_freq8) if current_freq8 > 0 else (1, 1)

    # Apply per-channel duty (amplitude) — preserves period, so freq unchanged.
    if current_freq1 > 0:
        h1, l1 = apply_duty(h1, l1, duty1)
    if current_freq2 > 0:
        h2, l2 = apply_duty(h2, l2, duty2)
    if current_freq3 > 0:
        h3, l3 = apply_duty(h3, l3, duty3)
    if current_freq4 > 0:
        h4, l4 = apply_duty(h4, l4, duty4)
    if current_freq5 > 0:
        h5, l5 = apply_duty(h5, l5, duty5)
    if current_freq6 > 0:
        h6, l6 = apply_duty(h6, l6, duty6)
    if current_freq7 > 0:
        h7, l7 = apply_duty(h7, l7, duty7)
    if current_freq8 > 0:
        h8, l8 = apply_duty(h8, l8, duty8)

    # Per-channel phase delays (clock ticks) for CH1-4 on PIO0. Each channel's
    # first HIGH is extended by its delay, shifting all of its cycles by that phase.
    # Only PIO0 SMs (CH1-4) share the simultaneous start, so only they can be
    # phase-locked; CH5 (PIO1) has no phase control. With all phases 0 this is a
    # no-op (identical to the original CH2-only behavior).
    def _phase_delay(freq, ph, h, l):
        if freq <= 0 or ph == 0.0:
            return 0
        period = counts_to_period(h, l)
        if period <= 0:
            return 0
        return round((ph % 360.0) / 360.0 * period) % period
    delay1 = _phase_delay(current_freq1, current_phase1, h1, l1)
    delay_ticks = _phase_delay(current_freq2, current_phase, h2, l2)  # CH2 (backward compat)
    delay3 = _phase_delay(current_freq3, current_phase3, h3, l3)
    delay4 = _phase_delay(current_freq4, current_phase4, h4, l4)
    delay5 = _phase_delay(current_freq5, current_phase5, h5, l5)   # PIO1 group (Block B)
    delay6 = _phase_delay(current_freq6, current_phase6, h6, l6)
    delay7 = _phase_delay(current_freq7, current_phase7, h7, l7)
    delay8 = _phase_delay(current_freq8, current_phase8, h8, l8)

    # Create state machines in PIO 0 (shared clock, simultaneous start)
    if current_freq1 > 0:
        sm0 = StateMachine(0, nco_prog, freq=SYS_CLK,
                           set_base=machine.Pin(PIN_CH1))
        sm0.put(h1 + delay1)     # first_high extended by CH1 phase delay
        sm0.put(l1)              # low_count
        sm0.put(h1)              # normal_high

    if current_freq2 > 0:
        sm1 = StateMachine(1, nco_prog, freq=SYS_CLK,
                           set_base=machine.Pin(PIN_CH2))
        sm1.put(h2 + delay_ticks)   # first_high extended by phase delay
        sm1.put(l2)                  # low_count
        sm1.put(h2)                  # normal_high (subsequent cycles)

    if current_freq3 > 0:
        sm2 = StateMachine(2, nco_prog, freq=SYS_CLK,
                           set_base=machine.Pin(PIN_CH3))
        sm2.put(h3 + delay3)     # first_high extended by CH3 phase delay
        sm2.put(l3)              # low_count
        sm2.put(h3)              # normal_high

    if current_freq4 > 0:
        sm3 = StateMachine(3, nco_prog, freq=SYS_CLK,
                           set_base=machine.Pin(PIN_CH4))
        sm3.put(h4 + delay4)     # first_high extended by CH4 phase delay
        sm3.put(l4)              # low_count
        sm3.put(h4)              # normal_high

    # CH5/CH6 live on PIO1 (SM index 4,5). They share PIO1's simultaneous start
    # (enabled together below) → phase-coherent as a pair, an independent
    # interference-capable group. PH5/PH6 extend each first-HIGH like PIO0.
    if current_freq5 > 0:
        sm4 = StateMachine(4, nco_prog, freq=SYS_CLK,
                           set_base=machine.Pin(PIN_CH5))
        sm4.put(h5 + delay5)     # first_high extended by CH5 phase delay
        sm4.put(l5)              # low_count
        sm4.put(h5)              # normal_high

    # CH6 on PIO1 (SM index 5) — 2nd channel of the Block B phase-locked quad.
    if current_freq6 > 0:
        sm5 = StateMachine(5, nco_prog, freq=SYS_CLK,
                           set_base=machine.Pin(PIN_CH6))
        sm5.put(h6 + delay6)     # first_high extended by CH6 phase delay
        sm5.put(l6)              # low_count
        sm5.put(h6)              # normal_high

    # CH7/CH8 on PIO1 (SM index 6/7) — 3rd/4th channels of the Block B quad. All
    # four PIO1 SMs share PIO1's simultaneous start → up to 4 phase-locked TX on
    # ONE plate (PH5-8). This is the block that keeps 3 (or 4) TX in phase.
    if current_freq7 > 0:
        sm6 = StateMachine(6, nco_prog, freq=SYS_CLK,
                           set_base=machine.Pin(PIN_CH7))
        sm6.put(h7 + delay7)     # first_high extended by CH7 phase delay
        sm6.put(l7)              # low_count
        sm6.put(h7)              # normal_high

    if current_freq8 > 0:
        sm7 = StateMachine(7, nco_prog, freq=SYS_CLK,
                           set_base=machine.Pin(PIN_CH8))
        sm7.put(h8 + delay8)     # first_high extended by CH8 phase delay
        sm7.put(l8)              # low_count
        sm7.put(h8)              # normal_high

    # Start Block A (PIO0 SM0-3) simultaneously via direct register write
    enable_mask = 0
    if sm0:
        enable_mask |= 0x01   # SM0 enable
    if sm1:
        enable_mask |= 0x02   # SM1 enable
    if sm2:
        enable_mask |= 0x04   # SM2 enable
    if sm3:
        enable_mask |= 0x08   # SM3 enable

    machine.mem32[PIO_CTRL] = enable_mask

    # Start Block B (PIO1 SM0-3) — set all four enable bits together so they
    # launch on the same clock edge (PIO1 SM0=bit0 .. SM3=bit3) → phase-locked.
    pio1_mask = 0
    if sm4:
        pio1_mask |= 0x01
    if sm5:
        pio1_mask |= 0x02
    if sm6:
        pio1_mask |= 0x04
    if sm7:
        pio1_mask |= 0x08
    if pio1_mask:
        machine.mem32[PIO1_CTRL] = pio1_mask

    # ── Block C: PWM tones (CH9-15) ─────────────────────────────────────
    # Independent tones for simple / single-TX plates. machine.PWM sets each
    # slice's GPIO function, period and duty; then a single write to PWM_EN
    # (after zeroing counters) launches the whole block phase-aligned at 0°.
    active_slices = 0
    for ch, gp in PWM_PINS.items():
        if pwm_freq[ch] > 0:
            if pwm_obj[ch] is None:
                pwm_obj[ch] = machine.PWM(machine.Pin(gp))
            pwm_obj[ch].freq(pwm_freq[ch])
            pwm_obj[ch].duty_u16((65535 * pwm_duty[ch]) // 1000)
            active_slices |= (1 << pwm_slice(gp))
        elif pwm_obj[ch] is not None:
            try:
                pwm_obj[ch].deinit()
            except Exception:
                pass
            pwm_obj[ch] = None
            machine.Pin(gp, machine.Pin.OUT).value(0)
    if active_slices:
        machine.mem32[PWM_EN] = 0                       # freeze all slices
        for ch, gp in PWM_PINS.items():
            if pwm_freq[ch] > 0:
                machine.mem32[PWM_BASE + 0x08 + pwm_slice(gp) * 0x14] = 0   # zero counter
        machine.mem32[PWM_EN] = active_slices           # launch together (phase-aligned)

    running = True

def stop_oscillators():
    """Stop all channels, force outputs LOW."""
    global sm0, sm1, sm2, sm3, sm4, sm5, sm6, sm7, running, pins_floating

    # Disable all state machines in PIO 0 and PIO 1 (Blocks A and B)
    machine.mem32[PIO_CTRL] = 0x00
    machine.mem32[PIO1_CTRL] = 0x00

    # Force outputs LOW via exec (works even when SM disabled)
    for sm in (sm0, sm1, sm2, sm3, sm4, sm5, sm6, sm7):
        if sm:
            try:
                sm.exec(0xE000)    # set(pins, 0)
            except:
                pass
    sm0 = None
    sm1 = None
    sm2 = None
    sm3 = None
    sm4 = None
    sm5 = None
    sm6 = None
    sm7 = None

    # Disable Block C (PWM) slices and release their pins LOW
    try:
        machine.mem32[PWM_EN] = 0
    except Exception:
        pass
    for ch, gp in PWM_PINS.items():
        if pwm_obj[ch] is not None:
            try:
                pwm_obj[ch].deinit()
            except Exception:
                pass
            pwm_obj[ch] = None
        machine.Pin(gp, machine.Pin.OUT).value(0)

    # Belt-and-suspenders: set PIO pins LOW from CPU
    for p in (PIN_CH1, PIN_CH2, PIN_CH3, PIN_CH4, PIN_CH5, PIN_CH6, PIN_CH7, PIN_CH8):
        machine.Pin(p, machine.Pin.OUT).value(0)

    running = False
    pins_floating = False


def float_outputs():
    """Stop all channels and leave every drive pin high-impedance (TX PZTs open-circuit).

    The state machines stop with the same single register write as stop_oscillators(),
    then the pins are released as inputs with no pull instead of being driven LOW.
    The next F command (via start_oscillators -> stop_oscillators) drives them again.
    """
    global sm0, sm1, sm2, sm3, sm4, sm5, sm6, sm7, running, pins_floating

    machine.mem32[PIO_CTRL] = 0x00
    machine.mem32[PIO1_CTRL] = 0x00
    for p in (PIN_CH1, PIN_CH2, PIN_CH3, PIN_CH4, PIN_CH5, PIN_CH6, PIN_CH7, PIN_CH8):
        machine.Pin(p, machine.Pin.IN, None)
    sm0 = None
    sm1 = None
    sm2 = None
    sm3 = None
    sm4 = None
    sm5 = None
    sm6 = None
    sm7 = None

    try:
        machine.mem32[PWM_EN] = 0
    except Exception:
        pass
    for ch, gp in PWM_PINS.items():
        if pwm_obj[ch] is not None:
            try:
                pwm_obj[ch].deinit()
            except Exception:
                pass
            pwm_obj[ch] = None
        machine.Pin(gp, machine.Pin.IN, None)

    running = False
    pins_floating = True


# ─── Command Handler ─────────────────────────────────────────────
def handle_command(cmd):
    """Parse and execute a serial command. Returns response string."""
    global current_freq1, current_freq2, current_freq3, current_freq4, current_freq5, current_freq6, current_phase
    global current_freq7, current_freq8
    global current_phase1, current_phase3, current_phase4, current_phase5, current_phase6, current_phase7, current_phase8
    global duty1, duty2, duty3, duty4, duty5, duty6, duty7, duty8

    cmd = cmd.strip()
    if not cmd:
        return ""

    # Blink LED on command
    led.toggle()

    # ── F1:<freq> — Set channel 1 ──
    if cmd.startswith("F1:"):
        try:
            freq = int(cmd[3:])
            current_freq1 = freq
            start_oscillators()
            if freq > 0:
                actual = counts_to_freq(*freq_to_counts(freq))
                return f"DDS:{freq}"
            else:
                return "DDS:0"
        except ValueError:
            return "ERR:bad_freq"

    # ── F2:<freq> — Set channel 2 ──
    elif cmd.startswith("F2:"):
        try:
            freq = int(cmd[3:])
            current_freq2 = freq
            start_oscillators()
            if freq > 0:
                actual = counts_to_freq(*freq_to_counts(freq))
                return f"DDS2:{freq}"
            else:
                return "DDS2:0"
        except ValueError:
            return "ERR:bad_freq"

    # ── F<freq> — Legacy single-channel mode (CH1 only) ──
    elif cmd.startswith("F") and cmd[1:].isdigit():
        try:
            freq = int(cmd[1:])
            current_freq1 = freq
            start_oscillators()
            return f"DDS:{freq}"
        except ValueError:
            return "ERR:bad_freq"

    # ── F3:<freq> — Set channel 3 ──
    elif cmd.startswith("F3:"):
        try:
            freq = int(cmd[3:])
            current_freq3 = freq
            start_oscillators()
            if freq > 0:
                actual = counts_to_freq(*freq_to_counts(freq))
                return f"DDS3:{freq}"
            else:
                return "DDS3:0"
        except ValueError:
            return "ERR:bad_freq"

    # ── F4:<freq> — Set channel 4 (25mm plate TX) ──
    elif cmd.startswith("F4:"):
        try:
            freq = int(cmd[3:])
            current_freq4 = freq
            start_oscillators()
            if freq > 0:
                actual = counts_to_freq(*freq_to_counts(freq))
                return f"DDS4:{freq}"
            else:
                return "DDS4:0"
        except ValueError:
            return "ERR:bad_freq"

    # ── F5:<freq> — Set channel 5 (5th plate TX, GP6 on PIO1) ──
    elif cmd.startswith("F5:"):
        try:
            freq = int(cmd[3:])
            current_freq5 = freq
            start_oscillators()
            if freq > 0:
                actual = counts_to_freq(*freq_to_counts(freq))
                return f"DDS5:{freq}"
            else:
                return "DDS5:0"
        except ValueError:
            return "ERR:bad_freq"

    # ── F6:<freq> — Set channel 6 (6th TX, GP7/pin10 on PIO1 SM1) ──
    elif cmd.startswith("F6:"):
        try:
            freq = int(cmd[3:])
            current_freq6 = freq
            start_oscillators()
            if freq > 0:
                actual = counts_to_freq(*freq_to_counts(freq))
                return f"DDS6:{freq}"
            else:
                return "DDS6:0"
        except ValueError:
            return "ERR:bad_freq"

    # ── F7:<freq> — Block B TX3 (GP8/pin11, PIO1 SM2) ──
    elif cmd.startswith("F7:"):
        try:
            current_freq7 = int(cmd[3:])
            start_oscillators()
            return f"DDS7:{current_freq7}"
        except ValueError:
            return "ERR:bad_freq"

    # ── F8:<freq> — Block B TX4 (GP9/pin12, PIO1 SM3) ──
    elif cmd.startswith("F8:"):
        try:
            current_freq8 = int(cmd[3:])
            start_oscillators()
            return f"DDS8:{current_freq8}"
        except ValueError:
            return "ERR:bad_freq"

    # ── F9:..F15: — Block C PWM tones (independent plates) ──
    elif cmd[:1] == "F" and ":" in cmd and cmd[1:cmd.index(":")].isdigit() \
            and 9 <= int(cmd[1:cmd.index(":")]) <= 15:
        try:
            ch = int(cmd[1:cmd.index(":")])
            pwm_freq[ch] = int(cmd[cmd.index(":") + 1:])
            start_oscillators()
            return f"DDS{ch}:{pwm_freq[ch]}"
        except (ValueError, KeyError):
            return "ERR:bad_freq"

    # ── A<ch>:<permille> — Set channel DUTY = amplitude (10..500 = 1%..50%) ──
    # Fundamental amplitude at the mode ∝ sin(π·duty); 500 = max, lower = quieter.
    # This is the amplitude knob for the proven 'amplitude of a fixed mode' encoding.
    elif cmd[:1] == "A" and ":" in cmd and cmd[1:cmd.index(":")].isdigit():
        try:
            ch = int(cmd[1:cmd.index(":")])
            d = int(cmd[cmd.index(":") + 1:])
            d = 10 if d < 10 else (500 if d > 500 else d)
            if ch == 1:
                duty1 = d
            elif ch == 2:
                duty2 = d
            elif ch == 3:
                duty3 = d
            elif ch == 4:
                duty4 = d
            elif ch == 5:
                duty5 = d
            elif ch == 6:
                duty6 = d
            elif ch == 7:
                duty7 = d
            elif ch == 8:
                duty8 = d
            elif ch in PWM_PINS:
                pwm_duty[ch] = d
            else:
                return "ERR:bad_ch"
            start_oscillators()
            return f"AMP{ch}:{d}"
        except (ValueError, IndexError):
            return "ERR:bad_amp"

    # ── Foff / FOFF — Stop all ──
    elif cmd in ("Foff", "FOFF", "foff"):
        stop_oscillators()
        current_freq1 = 0
        current_freq2 = 0
        current_freq3 = 0
        current_freq4 = 0
        current_freq5 = 0
        current_freq6 = 0
        current_freq7 = 0
        current_freq8 = 0
        for ch in PWM_PINS:
            pwm_freq[ch] = 0
        return "DDS:0"

    # ── Fz / FZ — Stop all, drive pins high-impedance (TX PZTs open-circuit) ──
    elif cmd in ("Fz", "FZ", "fz"):
        float_outputs()
        current_freq1 = 0
        current_freq2 = 0
        current_freq3 = 0
        current_freq4 = 0
        current_freq5 = 0
        current_freq6 = 0
        current_freq7 = 0
        current_freq8 = 0
        for ch in PWM_PINS:
            pwm_freq[ch] = 0
        return "DDS:Z"

    # ── PHASE:<degrees> — Set CH2 phase offset ──
    elif cmd.startswith("PHASE:"):
        try:
            phase = float(cmd[6:])
            current_phase = phase % 360.0
            if running:
                start_oscillators()
            return f"PHASE:{current_phase:.2f}"
        except ValueError:
            return "ERR:bad_phase"

    # ── PHk:<deg> — Per-channel absolute phase for CH1-4 (PIO0, phase-locked) ──
    # Enables an N-path interference sum: drive several channels at the SAME freq
    # on one plate, each at its own phase → glass computes |Σ aₖ e^{iφₖ}|². PH2 == PHASE.
    elif cmd.startswith("PH1:"):
        try:
            current_phase1 = float(cmd[4:]) % 360.0
            if running:
                start_oscillators()
            return f"PH1:{current_phase1:.2f}"
        except ValueError:
            return "ERR:bad_phase"
    elif cmd.startswith("PH2:"):
        try:
            current_phase = float(cmd[4:]) % 360.0
            if running:
                start_oscillators()
            return f"PH2:{current_phase:.2f}"
        except ValueError:
            return "ERR:bad_phase"
    elif cmd.startswith("PH3:"):
        try:
            current_phase3 = float(cmd[4:]) % 360.0
            if running:
                start_oscillators()
            return f"PH3:{current_phase3:.2f}"
        except ValueError:
            return "ERR:bad_phase"
    elif cmd.startswith("PH4:"):
        try:
            current_phase4 = float(cmd[4:]) % 360.0
            if running:
                start_oscillators()
            return f"PH4:{current_phase4:.2f}"
        except ValueError:
            return "ERR:bad_phase"
    elif cmd.startswith("PH5:"):
        try:
            current_phase5 = float(cmd[4:]) % 360.0
            if running:
                start_oscillators()
            return f"PH5:{current_phase5:.2f}"
        except ValueError:
            return "ERR:bad_phase"
    elif cmd.startswith("PH6:"):
        try:
            current_phase6 = float(cmd[4:]) % 360.0
            if running:
                start_oscillators()
            return f"PH6:{current_phase6:.2f}"
        except ValueError:
            return "ERR:bad_phase"
    elif cmd.startswith("PH7:"):
        try:
            current_phase7 = float(cmd[4:]) % 360.0
            if running:
                start_oscillators()
            return f"PH7:{current_phase7:.2f}"
        except ValueError:
            return "ERR:bad_phase"
    elif cmd.startswith("PH8:"):
        try:
            current_phase8 = float(cmd[4:]) % 360.0
            if running:
                start_oscillators()
            return f"PH8:{current_phase8:.2f}"
        except ValueError:
            return "ERR:bad_phase"

    # ── P1:<reg> — Legacy AD9833 phase register for CH1 (ignored, phase is relative) ──
    elif cmd.startswith("P1:"):
        # AD9833 used 12-bit reg (0-4095 = 0-360°). Convert to degrees.
        try:
            reg = int(cmd[3:])
            # For legacy compat: P1 sets the reference (always 0 internally)
            return f"P1:{reg}"
        except ValueError:
            return "ERR:bad_phase"

    # ── P2:<reg> — Legacy AD9833 phase register for CH2 ──
    elif cmd.startswith("P2:"):
        try:
            reg = int(cmd[3:])
            current_phase = (reg / 4096.0) * 360.0
            if running:
                start_oscillators()
            return f"P2:{reg}"
        except ValueError:
            return "ERR:bad_phase"

    # ── D? — Query frequency (legacy) ──
    elif cmd == "D?":
        return f"DDS:{current_freq1}"

    # ── STATUS — Full state report ──
    elif cmd == "STATUS":
        def _af(f):
            return counts_to_freq(*freq_to_counts(f)) if f > 0 else 0.0
        pwm_report = ",".join(
            f"{ch}:{(pwm_obj[ch].freq() if pwm_obj[ch] else 0)}" for ch in sorted(PWM_PINS))
        return (
            f"CLK:{SYS_CLK} "
            f"CH1:{current_freq1}({_af(current_freq1):.1f}Hz) "
            f"CH2:{current_freq2}({_af(current_freq2):.1f}Hz) "
            f"CH3:{current_freq3}({_af(current_freq3):.1f}Hz) "
            f"CH4:{current_freq4}({_af(current_freq4):.1f}Hz) "
            f"CH5:{current_freq5}({_af(current_freq5):.1f}Hz) "
            f"CH6:{current_freq6}({_af(current_freq6):.1f}Hz) "
            f"CH7:{current_freq7}({_af(current_freq7):.1f}Hz) "
            f"CH8:{current_freq8}({_af(current_freq8):.1f}Hz) "
            f"PWM[{pwm_report}] "
            f"DUTY:{duty1},{duty2},{duty3},{duty4},{duty5},{duty6},{duty7},{duty8} "
            f"PH:{current_phase:.2f}deg "
            f"PHA:{current_phase1:.0f},{current_phase:.0f},{current_phase3:.0f},{current_phase4:.0f} "
            f"PHB:{current_phase5:.0f},{current_phase6:.0f},{current_phase7:.0f},{current_phase8:.0f} "
            f"RUN:{'Y' if running else 'N'} "
            f"IDLE:{'Z' if pins_floating else 'LOW'}"
        )

    # ── FREQ? — Show eigenmode accuracy ──
    elif cmd == "FREQ?":
        modes = [35840, 54920, 57037, 97011]
        lines = []
        for m in modes:
            h, l = freq_to_counts(m)
            actual = counts_to_freq(h, l)
            err = actual - m
            bw = m / 3500.0
            lines.append(f"  {m}->{actual:.1f}Hz err={err:+.1f} BW={bw:.1f}")
        return "MODES:\n" + "\n".join(lines)

    # ── SWEEP:<start>:<stop>:<step> — Phase sweep for CHSH ──
    elif cmd.startswith("SWEEP:"):
        try:
            parts = cmd[6:].split(":")
            start_deg = float(parts[0])
            stop_deg = float(parts[1])
            step_deg = float(parts[2])

            if step_deg <= 0:
                return "ERR:step<=0"

            n_steps = 0
            phase = start_deg
            while phase <= stop_deg + 0.001:
                current_phase = phase % 360.0
                start_oscillators()
                # Report each step so host can trigger measurement
                print(f"SWEEP_PT:{current_phase:.2f}")
                time.sleep_ms(50)   # brief settle
                phase += step_deg
                n_steps += 1

            return f"SWEEP_DONE:{n_steps}"
        except (ValueError, IndexError):
            return "ERR:bad_sweep"

    # ── TEMP — Read RP2040 internal temperature sensor ──
    elif cmd == "TEMP":
        raw = _adc_temp.read_u16()
        voltage = raw * 3.3 / 65535.0
        temp_c = 27.0 - (voltage - 0.706) / 0.001721
        return f"TEMP:{temp_c:.2f}C ADC:{raw}"

    # ── TIME — Uptime in microseconds since boot ──
    elif cmd == "TIME":
        elapsed = time.ticks_diff(time.ticks_us(), _boot_ticks)
        return f"TIME:{elapsed}us"

    else:
        return f"ERR:unknown '{cmd[:20]}'"


# ─── Main ────────────────────────────────────────────────────────
def main():
    # Startup banner
    print("")
    print("CWM Pico NCO v2.1 — 15 tones (8 PIO + 7 PWM), 3 phase-coherent blocks")
    print(f"CLK:{SYS_CLK/1e6:.0f}MHz  BlockA GP2-5  BlockB GP6-9  BlockC PWMx7")
    print("OK")

    # Ensure all outputs start LOW (PIO Blocks A+B and PWM Block C)
    for p in (PIN_CH1, PIN_CH2, PIN_CH3, PIN_CH4, PIN_CH5, PIN_CH6, PIN_CH7, PIN_CH8):
        machine.Pin(p, machine.Pin.OUT).value(0)
    for gp in PWM_PINS.values():
        machine.Pin(gp, machine.Pin.OUT).value(0)

    # Non-blocking serial read via poll
    poll = select.poll()
    poll.register(sys.stdin, select.POLLIN)

    buf = ""
    while True:
        events = poll.poll(100)   # 100 ms timeout
        for obj, event in events:
            if event & select.POLLIN:
                char = sys.stdin.read(1)
                if char in ('\n', '\r'):
                    if buf:
                        response = handle_command(buf)
                        if response:
                            print(response)
                        buf = ""
                else:
                    buf += char


# Run
main()
