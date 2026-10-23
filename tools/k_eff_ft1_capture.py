#!/usr/bin/env python3
"""FT-1 fresh full-map capture (docs/K_EFF_FAST_TRACK.md FT-1, docs/MEASUREMENT_AND_CLAIM_GATE.md FT-M).

One session = several path-state blocks captured on the same frozen frequency grid:

    QUIET            drive off; noise floor for every grid frequency
    LOOPBACK         Ch A and Ch B both on the TX junction; channel gain/phase mismatch
    GLASS            Ch A = acoustic RX via preamp, Ch B = drive tap
    ELECTRICAL_ONLY  live RX swapped for the detached dummy PZT; electronics unchanged

Physical changes between blocks are made by hand; run one block per invocation:

    python tools/k_eff_ft1_capture.py --session FT1-S1 --state QUIET --device plate100-A --fixture fixA
    python tools/k_eff_ft1_capture.py --session FT1-S1 --summarize

Per trial = one raw two-channel acquisition at one (frequency, repeat), randomized order.
Raw int8/int16 samples go to data/raw/k_eff/<session>/ (gitignored); their SHA-256 hashes,
the per-trial complex coefficients and the manifest go to data/results/k_eff/<session>/.
Diagnostics from --summarize are qualification aids, not acceptance decisions.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import secrets
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

SYS_CLK = 126_000_000
PIO_OVERHEAD = 6
N = 3072
TIMEBASE = 7
RANGES_MV = {500: 5, 1000: 6, 2000: 7, 5000: 8, 10000: 9}
REF_SNR_MIN = 20.0
ALIAS_MAX_HARMONIC = 40
ALIAS_WIDTH_BINS = 3
TAP_CHECK_HZ = 60_000
TAP_MIN_MV = 100.0
CLIP_FRACTION = 0.98
STATES = ('QUIET', 'LOOPBACK', 'GLASS', 'ELECTRICAL_ONLY')
LIB = '/Applications/PicoScope 7 T&M Early Access.app/Contents/Resources/libps2000.dylib'
REPO = Path(__file__).resolve().parents[1]
GRID_FILE = REPO / 'data/results/k_eff/ft1_frozen_grid.json'
TRIAL_FIELDS = ['session_id', 'block_id', 'state', 'trial_idx', 'order_idx', 'rep', 'channel',
                'freq_cmd_hz', 'freq_actual_hz', 'duty_permille', 't_unix', 'raw_row',
                'ovf_A', 'ovf_B', 'clip_A', 'clip_B', 'dc_A_mV', 'dc_B_mV',
                'zA_re_mV', 'zA_im_mV', 'zB_re_mV', 'zB_im_mV',
                'zA2_re_mV', 'zA2_im_mV', 'zB2_re_mV', 'zB2_im_mV',
                'zA3_re_mV', 'zA3_im_mV', 'zB3_re_mV', 'zB3_im_mV']
DEFAULT_RX = {'GLASS': 'live RX PZT, top centre', 'ELECTRICAL_ONLY': 'detached dummy PZT in place of the live RX',
              'LOOPBACK': 'live RX PZT, top centre (not read: Ch A moved)', 'QUIET': 'live RX PZT, top centre'}


def pio_actual_freq(freq_hz: float) -> float:
    period = round(SYS_CLK / freq_hz)
    period = max(period - PIO_OVERHEAD, 2) + PIO_OVERHEAD
    return SYS_CLK / period


def demod(x_mv: np.ndarray, freq_hz: float, fs: float) -> complex:
    """Peak-amplitude complex coefficient at freq_hz (Hann-weighted single-frequency DFT, phase at sample 0)."""
    x = np.asarray(x_mv, float)
    x = x - x.mean()
    w = np.hanning(len(x))
    n = np.arange(len(x))
    return complex(np.sum(x * w * np.exp(-2j * np.pi * freq_hz * n / fs)) * 2.0 / w.sum())


def alias_flags(grid: list[int], fs: float, orders=(1, 2, 3), max_harmonic: int = ALIAS_MAX_HARMONIC,
                width_hz: float | None = None) -> dict[int, list[int]]:
    """Grid points whose demod frequency n*f has a folded drive harmonic m*f (m != n) within width_hz.

    Depends only on the grid and sample rate, so the exclusion list is fixed before any data exist.
    """
    width_hz = ALIAS_WIDTH_BINS * fs / N if width_hz is None else width_hz
    nyq = fs / 2
    out = {n: [] for n in orders}
    for g in grid:
        fa = pio_actual_freq(g)
        for n in orders:
            if n * fa >= nyq:
                continue
            for m in range(1, max_harmonic + 1):
                if m == n:
                    continue
                r = (m * fa) % fs
                if abs((fs - r if r > nyq else r) - n * fa) < width_hz:
                    out[n].append(g)
                    break
    return out


def trial_order(grid: list[int], repeats: int, seed: int) -> list[tuple[int, int]]:
    pairs = [(f, r) for f in grid for r in range(repeats)]
    order = np.random.default_rng(seed).permutation(len(pairs))
    return [pairs[i] for i in order]


def pack_raw(counts: np.ndarray) -> np.ndarray:
    """The 2204A is 8-bit; ps2000 returns counts scaled by 256. Store int8 when lossless."""
    if np.all(counts % 256 == 0):
        return (counts // 256).astype(np.int8)
    return counts.astype(np.int16)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def rel(path: Path) -> str:
    path = path.resolve()
    return str(path.relative_to(REPO)) if path.is_relative_to(REPO) else str(path)


def load_or_freeze_grid(spec: str | None, grid_file: Path) -> dict:
    if grid_file.exists():
        frozen = json.loads(grid_file.read_text())
        if spec and spec != frozen['spec']:
            raise SystemExit(f'Grid is frozen as {frozen["spec"]} in {grid_file}; refusing {spec}')
        return frozen
    spec = spec or '30000:120000:500'
    lo, hi, step = (int(v) for v in spec.split(':'))
    grid = list(range(lo, hi + 1, step))
    frozen = {'spec': spec, 'freqs_hz': grid, 'n': len(grid),
              'sha256': hashlib.sha256(json.dumps(grid).encode()).hexdigest(),
              'frozen_utc': datetime.now(timezone.utc).isoformat()}
    grid_file.parent.mkdir(parents=True, exist_ok=True)
    grid_file.write_text(json.dumps(frozen, indent=1) + '\n')
    return frozen


def git_state() -> dict:
    def run(*a):
        return subprocess.run(['git', *a], cwd=REPO, capture_output=True, text=True).stdout.strip()
    return {'commit': run('rev-parse', 'HEAD'),
            'code_dirty': bool(run('status', '--porcelain', '--untracked-files=no', '--', 'tools', 'tests')),
            'worktree_dirty': bool(run('status', '--porcelain'))}


class Bench:
    def __init__(self, port: str, range_a_mv: int, range_b_mv: int):
        import ctypes as ct
        import serial
        self.ct = ct
        self.ps = ct.CDLL(LIB)
        self.ps.ps2000_open_unit.restype = ct.c_int16
        self.h = self.ps.ps2000_open_unit()
        if self.h <= 0:
            raise SystemExit(f'PicoScope open failed ({self.h})')
        self.nco = serial.Serial(port, 115200, timeout=1.0)
        time.sleep(0.5)
        self.nco.reset_input_buffer()
        self.ps.ps2000_set_channel(self.h, 0, 1, 1, RANGES_MV[range_a_mv])
        self.ps.ps2000_set_channel(self.h, 1, 1, 1, RANGES_MV[range_b_mv])
        self.ps.ps2000_set_trigger(self.h, 5, 0, 0, 0, 0)
        ti, tu, ms = ct.c_int32(), ct.c_int16(), ct.c_int32()
        if not self.ps.ps2000_get_timebase(self.h, TIMEBASE, N, ct.byref(ti), ct.byref(tu), 0, ct.byref(ms)):
            raise SystemExit('ps2000_get_timebase rejected the capture settings')
        self.dt_ns = ti.value
        self.fs = 1e9 / ti.value

    def info(self) -> dict:
        out = {}
        for line, key in ((3, 'variant'), (4, 'batch_serial'), (5, 'cal_date')):
            buf = self.ct.create_string_buffer(64)
            self.ps.ps2000_get_unit_info(self.h, buf, 64, line)
            out[key] = buf.value.decode(errors='replace')
        return out

    def query(self, cmd: str) -> str:
        self.nco.reset_input_buffer()
        self.nco.write(f'{cmd}\n'.encode())
        return self.nco.readline().decode(errors='replace').strip()

    def capture(self):
        ct = self.ct
        ba, bb, ov, tk = (ct.c_int16 * N)(), (ct.c_int16 * N)(), ct.c_int16(), ct.c_int32()
        self.ps.ps2000_run_block(self.h, N, TIMEBASE, 1, ct.byref(tk))
        for _ in range(1000):
            if self.ps.ps2000_ready(self.h):
                break
            time.sleep(0.001)
        got = self.ps.ps2000_get_values(self.h, ct.byref(ba), ct.byref(bb), None, None, ct.byref(ov), N)
        if got != N:
            raise RuntimeError(f'scope returned {got} samples, expected {N}')
        return np.array(ba[:], np.int16), np.array(bb[:], np.int16), ov.value

    def close(self, channel: str):
        try:
            self.query('Foff')
            self.query(f'A{channel[1:]}:500')
        finally:
            self.nco.close()
            self.ps.ps2000_stop(self.h)
            self.ps.ps2000_close_unit(self.ct.c_int16(self.h))


def run_block(a) -> None:
    grid = load_or_freeze_grid(a.grid, Path(a.grid_file))
    sdir = REPO / a.out_root / a.session
    rdir = REPO / a.raw_root / a.session
    sdir.mkdir(parents=True, exist_ok=True)
    rdir.mkdir(parents=True, exist_ok=True)
    mpath = sdir / 'manifest.json'
    manifest = json.loads(mpath.read_text()) if mpath.exists() else None
    if manifest and manifest['grid']['sha256'] != grid['sha256']:
        raise SystemExit('Session manifest grid differs from the frozen grid')
    if a.channel not in {f'F{i}' for i in range(1, 9)}:
        raise SystemExit('Only PIO channels F1-F8 are supported (frequency model and phase lock)')

    seed = a.seed if a.seed is not None else secrets.randbits(32)
    block_id = f'{a.state}_{datetime.now():%Y%m%d_%H%M%S}'
    if a.state == 'QUIET':
        plan = [(0, r) for r in range(a.repeats)]
    else:
        plan = trial_order(grid['freqs_hz'], a.repeats, seed)

    ranges = {'A': a.range_a_mv, 'B': a.range_b_mv}
    if manifest and manifest['acquisition']['range_mV'] != ranges:
        raise SystemExit(f'Session uses scope ranges {manifest["acquisition"]["range_mV"]} mV; refusing {ranges}')
    ka, kb = a.range_a_mv / 32767, a.range_b_mv / 32767
    bench = Bench(a.nco_port, a.range_a_mv, a.range_b_mv)
    rows, raw_a, raw_b, temps = [], [], [], []
    started = datetime.now(timezone.utc).isoformat()
    try:
        status = bench.query('STATUS')
        temp_start = bench.query('TEMP')
        bench.query('Foff')
        duty_reply = bench.query(f'A{a.channel[1:]}:{a.duty}')
        time.sleep(0.2)
        tap_check = None
        if a.state != 'QUIET':
            bench.query(f'{a.channel}:{TAP_CHECK_HZ}')
            time.sleep(0.1)
            ca, cb, _ = bench.capture()
            fa = pio_actual_freq(TAP_CHECK_HZ)
            za = abs(demod(ca * ka, fa, bench.fs))
            zb = abs(demod(cb * kb, fa, bench.fs))
            bench.query('Foff')
            tap_check = {'freq_hz': TAP_CHECK_HZ, 'chA_mV': round(za, 2), 'chB_mV': round(zb, 2)}
            if zb < TAP_MIN_MV:
                raise SystemExit(f'Tap check failed: Ch B sees {zb:.1f} mV of {a.channel}; '
                                 f'is Ch B on the {a.channel} TX junction?')
            if a.state == 'LOOPBACK' and not 0.8 < za / zb < 1.25:
                raise SystemExit(f'Tap check failed: LOOPBACK Ch A/Ch B = {za / zb:.2f}; '
                                 f'is Ch A on the {a.channel} TX junction?')
            time.sleep(0.2)
        clip_level = CLIP_FRACTION * 32512
        for k, (f, rep) in enumerate(plan):
            if f:
                reply = bench.query(f'{a.channel}:{f}')
                if not reply.startswith('DDS'):
                    raise RuntimeError(f'NCO rejected {a.channel}:{f}: {reply!r}')
            time.sleep(a.settle)
            ca, cb, ov = bench.capture()
            fa = pio_actual_freq(f) if f else 0.0
            xa, xb = ca * ka, cb * kb
            z = {}
            for m in (1, 2, 3):
                ok = f and m * fa < bench.fs / 2
                z[m] = (demod(xa, m * fa, bench.fs) if ok else 0j, demod(xb, m * fa, bench.fs) if ok else 0j)
            za, zb = z[1]
            raw_a.append(ca)
            raw_b.append(cb)
            harm = {}
            for m in (2, 3):
                harm.update({f'zA{m}_re_mV': round(z[m][0].real, 5), f'zA{m}_im_mV': round(z[m][0].imag, 5),
                             f'zB{m}_re_mV': round(z[m][1].real, 5), f'zB{m}_im_mV': round(z[m][1].imag, 5)})
            rows.append({**harm, 'session_id': a.session, 'block_id': block_id, 'state': a.state,
                         'trial_idx': len(rows), 'order_idx': k, 'rep': rep, 'channel': a.channel,
                         'freq_cmd_hz': f, 'freq_actual_hz': round(fa, 4), 'duty_permille': a.duty,
                         't_unix': round(time.time(), 4), 'raw_row': k,
                         'ovf_A': int(bool(ov & 1)), 'ovf_B': int(bool(ov & 2)),
                         'clip_A': int(np.abs(ca).max() >= clip_level), 'clip_B': int(np.abs(cb).max() >= clip_level),
                         'dc_A_mV': round(float(xa.mean()), 3), 'dc_B_mV': round(float(xb.mean()), 3),
                         'zA_re_mV': round(za.real, 5), 'zA_im_mV': round(za.imag, 5),
                         'zB_re_mV': round(zb.real, 5), 'zB_im_mV': round(zb.imag, 5)})
            if (k + 1) % 200 == 0:
                temps.append({'after_trial': k + 1, 't_unix': round(time.time(), 2), 'reply': bench.query('TEMP')})
                print(f'  {k + 1}/{len(plan)}  {temps[-1]["reply"]}', flush=True)
        bench.query('Foff')
        temp_end = bench.query('TEMP')
        scope_info = bench.info()
        fs, dt_ns = bench.fs, bench.dt_ns
    finally:
        bench.close(a.channel)

    raw_file = rdir / f'{block_id}.npz'
    np.savez_compressed(raw_file, A=pack_raw(np.array(raw_a)), B=pack_raw(np.array(raw_b)),
                        mv_per_count_A=ka, mv_per_count_B=kb, packed_scale=256)
    tpath = sdir / 'trials.csv'
    new = not tpath.exists()
    with tpath.open('a', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=TRIAL_FIELDS)
        if new:
            w.writeheader()
        w.writerows(rows)

    script = Path(__file__).resolve()
    if manifest is None:
        manifest = {
            'schema': 'cwm-ft1-manifest-v1', 'session_id': a.session, 'provenance': 'physical',
            'created_utc': started, 'device_id': a.device, 'fixture_id': a.fixture,
            'split_role': a.split_role,
            'channel_roles': {
                'A': 'acoustic RX PZT -> OPA2134 preamp -> Ch A (per-block cha_tap, rx_element, gain_config)',
                'B': 'electrical tap of the driven TX at its PZT terminal, after its 220 ohm resistor (per-block chb_tap)'},
            'reference_mode': 'simultaneous_electrical',
            'tx': {'waveform': '3.3 V CMOS square via 220 ohm per TX; duty set by A<ch>, so harmonics 2f, 3f, ... '
                               'also drive the plate (first three recorded per trial, all in raw)',
                   'inactive_tx': 'undriven NCO pins held LOW; unused corner PZTs left unconnected'},
            'grid': {k: grid[k] for k in ('spec', 'n', 'sha256')},
            'acquisition': {'scope': scope_info, 'sample_interval_ns': dt_ns, 'sample_rate_hz': fs,
                            'samples_per_channel': N, 'window_s': N / fs, 'enabled_channels': 2,
                            'adc_bits': 8, 'range_mV': ranges, 'coupling': 'DC', 'timebase': TIMEBASE,
                            'averaging_policy': 'none: one acquisition per trial, raw retained',
                            'demod': 'Hann-weighted single-frequency DFT at freq_actual_hz, peak amplitude, phase at sample 0',
                            'voltage_convention': 'peak', 'freq_actual_model': 'SYS_CLK / round(SYS_CLK / f)'},
            'thresholds_frozen': {'ref_snr_min': REF_SNR_MIN, 'clip_fraction_of_full_scale': CLIP_FRACTION,
                                  'exclusion_policy': 'exclude trials with scope overflow or clip on either channel'},
            'environment': {'power_cycled_since_previous_session': a.power_cycled,
                            'remounted_since_previous_session': a.remounted,
                            'temperature_policy': 'manual air temperature next to the plate per block; '
                                                  'RP2040 die temperature logged as a proxy'},
            'unavailable': {'plate_surface_temp': 'not measured; air temperature next to the plate recorded instead',
                            'wiring_photo_sha256': 'no photo of the current topology recorded',
                            'channel_gain_delay_calibration': 'derive from this session LOOPBACK blocks',
                            'preamp_transfer_deembedding': 'not measured; Ch A/Ch B ratio is an end-to-end transfer'},
            'exclusions': [], 'blocks': [], 'notes': a.notes}
    manifest['blocks'].append({
        'block_id': block_id, 'state': a.state, 'channel': a.channel, 'started_utc': started,
        'cha_tap': a.cha_tap or (f'{a.channel} TX junction (Ch A moved; preamp bypassed)' if a.state == 'LOOPBACK'
                                 else 'preamp output, pin 1 via 47 ohm'),
        'chb_tap': a.chb_tap or f'{a.channel} TX junction (PZT terminal, after 220 ohm)',
        'rx_element': a.rx_element or DEFAULT_RX[a.state],
        'gain_config': a.gain_config, 'rails_v': a.rails, 'ambient_temp_c': a.ambient_temp_c,
        'tap_check': tap_check,
        'ended_utc': datetime.now(timezone.utc).isoformat(), 'n_trials': len(rows),
        'repeats': a.repeats, 'seed': seed, 'settle_s': a.settle, 'duty_permille': a.duty,
        'duty_reply': duty_reply, 'nco_status_start': status,
        'nco_die_temp_start': temp_start, 'nco_die_temp_end': temp_end, 'nco_die_temp_every_200': temps,
        'nco_die_temp_note': 'RP2040 die temperature, not resonator temperature',
        'raw_file': rel(raw_file), 'raw_sha256': sha256(raw_file),
        'trials_sha256_after_block': sha256(tpath),
        'n_overflow': sum(r['ovf_A'] or r['ovf_B'] for r in rows),
        'n_clip': sum(r['clip_A'] or r['clip_B'] for r in rows),
        'grid_file': rel(Path(a.grid_file)),
        'git': git_state(), 'script': rel(script), 'script_sha256': sha256(script),
        'operator_notes': a.notes})
    mpath.write_text(json.dumps(manifest, indent=1) + '\n')
    print(f'{a.state}: {len(rows)} trials, overflow {manifest["blocks"][-1]["n_overflow"]}, '
          f'clip {manifest["blocks"][-1]["n_clip"]} -> {rel(raw_file)}')


def summarize(a) -> None:
    sdir = REPO / a.out_root / a.session
    manifest = json.loads((sdir / 'manifest.json').read_text())
    fs = manifest['acquisition']['sample_rate_hz']
    grid = json.loads(Path(a.grid_file).read_text())['freqs_hz']
    with (sdir / 'trials.csv').open() as fh:
        rows = list(csv.DictReader(fh))

    quiet = [b for b in manifest['blocks'] if b['state'] == 'QUIET']
    if not quiet:
        raise SystemExit('Summary needs a QUIET block for the noise floor')
    qa, qb = [], []
    for b in quiet:
        raw = np.load(REPO / b['raw_file'])
        sa = float(raw['mv_per_count_A']) * (256 if raw['A'].dtype == np.int8 else 1)
        sb = float(raw['mv_per_count_B']) * (256 if raw['B'].dtype == np.int8 else 1)
        for xa, xb in zip(raw['A'].astype(float) * sa, raw['B'].astype(float) * sb):
            qa.append([abs(demod(xa, pio_actual_freq(f), fs)) for f in grid])
            qb.append([abs(demod(xb, pio_actual_freq(f), fs)) for f in grid])
    noise_a = dict(zip(grid, np.median(qa, 0)))
    noise_b = dict(zip(grid, np.median(qb, 0)))

    flags = alias_flags(grid, fs)
    out = {'session_id': a.session, 'status': 'qualification diagnostics, not an acceptance decision',
           'alias_flagged_grid_hz': {f'{n}f': v for n, v in flags.items()},
           'alias_rule': f'folded drive harmonics m<={ALIAS_MAX_HARMONIC} within {ALIAS_WIDTH_BINS} bins of n*f',
           'noise_floor_mV_median': {'A': float(np.median(list(noise_a.values()))),
                                     'B': float(np.median(list(noise_b.values())))},
           'states': {}}
    per_state = {}
    groups = sorted({(r['state'], r['channel']) for r in rows if r['state'] != 'QUIET'})
    for st, ch in groups:
        state = f'{st}:{ch}'
        srows = [r for r in rows if r['state'] == st and r['channel'] == ch]
        freqs = {}
        n_bad = 0
        for r in srows:
            if int(r['ovf_A']) or int(r['ovf_B']) or int(r['clip_A']) or int(r['clip_B']):
                n_bad += 1
                continue
            f = int(r['freq_cmd_hz'])
            za = complex(float(r['zA_re_mV']), float(r['zA_im_mV']))
            zb = complex(float(r['zB_re_mV']), float(r['zB_im_mV']))
            freqs.setdefault(f, []).append((za, zb))
        table = {}
        for f, pairs in sorted(freqs.items()):
            za = np.array([p[0] for p in pairs]); zb = np.array([p[1] for p in pairs])
            snr_b = np.abs(zb) / noise_b[f]
            ok = snr_b >= REF_SNR_MIN
            hv = za[ok] / zb[ok]
            entry = {'n': len(pairs), 'n_ref_valid': int(ok.sum()),
                     'ref_snr_median': float(np.median(snr_b)),
                     'rx_snr_median': float(np.median(np.abs(za) / noise_a[f]))}
            if ok.any():
                u = hv / np.abs(hv)
                entry.update({'H_mean_re': float(hv.mean().real), 'H_mean_im': float(hv.mean().imag),
                              'H_abs_median': float(np.median(np.abs(hv))),
                              'H_abs_cv': float(np.std(np.abs(hv)) / np.mean(np.abs(hv))),
                              'H_phase_circ_std_deg': float(np.degrees(np.sqrt(-2 * np.log(max(abs(u.mean()), 1e-12)))))})
            table[f] = entry
        per_state[state] = table
        valid = [e for e in table.values() if 'H_abs_median' in e]
        out['states'][state] = {
            'n_trials': len(srows), 'n_excluded_clip_or_overflow': n_bad,
            'ref_valid_fraction': sum(e['n_ref_valid'] for e in table.values()) / max(sum(e['n'] for e in table.values()), 1),
            'H_abs_median_over_grid': float(np.median([e['H_abs_median'] for e in valid])) if valid else None,
            'H_abs_cv_median': float(np.median([e['H_abs_cv'] for e in valid])) if valid else None,
            'H_phase_std_deg_median': float(np.median([e['H_phase_circ_std_deg'] for e in valid])) if valid else None,
            'per_freq': table}

    out['loopback'], out['glass_vs_electrical_only'] = {}, {}
    for ch in sorted({c for _, c in groups}):
        lbt = per_state.get(f'LOOPBACK:{ch}', {})
        lb = [(f, complex(e['H_mean_re'], e['H_mean_im'])) for f, e in lbt.items() if 'H_mean_re' in e]
        if len(lb) >= 2:
            f = np.array([p[0] for p in lb], float); g = np.array([p[1] for p in lb])
            slope = np.polyfit(f, np.unwrap(np.angle(g)), 1)[0]
            out['loopback'][ch] = {'gain_ratio_median': float(np.median(np.abs(g))),
                                   'gain_ratio_range': [float(np.abs(g).min()), float(np.abs(g).max())],
                                   'phase_deg_median': float(np.degrees(np.median(np.angle(g)))),
                                   'implied_delay_ns': float(-slope / (2 * np.pi) * 1e9)}
        gl, eo = per_state.get(f'GLASS:{ch}', {}), per_state.get(f'ELECTRICAL_ONLY:{ch}', {})
        ratios = [gl[f]['H_abs_median'] / eo[f]['H_abs_median'] for f in gl
                  if 'H_abs_median' in gl[f] and eo.get(f, {}).get('H_abs_median', 0) > 0]
        if ratios:
            out['glass_vs_electrical_only'][ch] = {'median_ratio': float(np.median(ratios)),
                                                   'min_ratio': float(np.min(ratios)),
                                                   'median_db': float(20 * np.log10(np.median(ratios)))}
    ddir = sdir / 'derived'
    ddir.mkdir(exist_ok=True)
    (ddir / 'summary.json').write_text(json.dumps(out, indent=1, default=str) + '\n')
    brief = {k: v for k, v in out.items() if k != 'states'}
    brief['states'] = {s: {k: v for k, v in d.items() if k != 'per_freq'} for s, d in out['states'].items()}
    print(json.dumps(brief, indent=1))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--session', required=True)
    ap.add_argument('--state', choices=STATES)
    ap.add_argument('--summarize', action='store_true')
    ap.add_argument('--device', default='unknown')
    ap.add_argument('--fixture', default='unknown')
    ap.add_argument('--split-role', default='unassigned', choices=['unassigned', 'train', 'test'])
    ap.add_argument('--channel', default='F2')
    ap.add_argument('--duty', type=int, default=100, help='permille, 10..500')
    ap.add_argument('--repeats', type=int, default=20)
    ap.add_argument('--settle', type=float, default=0.04, help='s; about 5 time constants of a Q=743 mode at 30 kHz')
    ap.add_argument('--seed', type=int)
    ap.add_argument('--grid', help='lo:hi:step Hz; only used to create the frozen grid')
    ap.add_argument('--grid-file', default=str(GRID_FILE))
    ap.add_argument('--ambient-temp-c', type=float, help='manual air temperature next to the plate')
    ap.add_argument('--gain-config', help='e.g. "x48: Rf 47k, Rg 1k + 10uF"')
    ap.add_argument('--rails', help='measured rails, e.g. "+9.4/-9.4"')
    ap.add_argument('--cha-tap')
    ap.add_argument('--chb-tap')
    ap.add_argument('--rx-element')
    ap.add_argument('--power-cycled', action='store_true')
    ap.add_argument('--remounted', action='store_true')
    ap.add_argument('--notes', default='')
    ap.add_argument('--range-a-mv', type=int, default=5000, choices=sorted(RANGES_MV))
    ap.add_argument('--range-b-mv', type=int, default=5000, choices=sorted(RANGES_MV))
    ap.add_argument('--nco-port', default='/dev/cu.usbmodem113401')
    ap.add_argument('--out-root', default='data/results/k_eff')
    ap.add_argument('--raw-root', default='data/raw/k_eff')
    a = ap.parse_args()
    if a.summarize:
        summarize(a)
    elif a.state:
        run_block(a)
    else:
        ap.error('give --state or --summarize')


if __name__ == '__main__':
    main()
