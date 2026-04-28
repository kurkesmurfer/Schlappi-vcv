"""
BTMX isolation test — binary count stimulus, latency + STEP spectrum.

The 4-bit binary count (BIT1 at BASE_FREQ, BIT2/4/8 at f/2/4/8) is fed
to one input group (side A = IN1-4 or side B = IN5-8).  The other group
receives constant high (5 V).  With AND logic this passes the count
transparently to the MIX outputs.  Test both sides to verify symmetry.

Cross-correlation between each MIX output and its input bit gives
processing latency.  ES-9 roundtrip latency is removed via loopback.

ES-9 wiring
-----------
  OUT 1  →  BTMX IN1   (BIT1, LSB)
  OUT 2  →  BTMX IN2   (BIT2)
  OUT 3  →  BTMX IN3   (BIT4)
  OUT 4  →  BTMX IN4   (BIT8, MSB)
  OUT 5  →  BTMX IN5   (BIT1 or high)
  OUT 6  →  BTMX IN6   (BIT2 or high)
  OUT 7  →  BTMX IN7   (BIT4 or high)
  OUT 8  →  BTMX IN8   (BIT8 or high)

  IN  1  ←  BTMX STEP
  IN  2  ←  BTMX MIX1  (ch 1+5)
  IN  3  ←  BTMX MIX2  (ch 2+6)
  IN  4  ←  BTMX MIX3  (ch 3+7)
  IN  5  ←  BTMX MIX4  (ch 4+8)
  IN  6  ←  loopback (OUT 1 = BIT1) — ES-9 latency reference

Module state to document before running
-----------------------------------------
  All 8 channel switches, Logic Mode A and B.
  For AND: all switches off (or as relevant to your patch).
  Set PLATFORM, PLUGIN_VERSION, LOGIC_MODE below.
"""

import sys
import datetime
import pathlib

import matplotlib.pyplot as plt
import numpy as np
import sounddevice as sd
from scipy import fft as scipy_fft

import registry
from measure import find_device, SAMPLE_RATE

# ── Configuration — edit before each run ──────────────────────────────────────
PLATFORM       = 'metamodule'   # 'metamodule' | 'vcvrack'
PLUGIN_VERSION = '2.0.22'
SDK_VERSION    = 'api-v2.1.0'

LOGIC_MODE     = 'AND'          # document actual module switch state
DURATION       = 4.0
FADE_SECONDS   = 0.01
HIGH_LEVEL     = 0.5            # 5 V when ES-9 FS = 10 V

DEVICE_NAME    = 'ES-9'
BASE_FREQS     = [100, 220, 440, 880, 2000]   # Hz for BIT1
TEST_SIDES     = ['A', 'B']

# ES-9 assignments (0-indexed)
N_CAPTURE_CH   = 9
OUTPUTS = {      # name: ES-9 input index
    'STEP': 0,
    'MIX1': 1,
    'MIX2': 2,
    'MIX3': 3,
    'MIX4': 4,
}
LOOPBACK_IN    = 5   # IN6 ← OUT1 (BIT1 reference)

# OUT indices for side A (IN1-4) and side B (IN5-8)
_SIDE_A = [0, 1, 2, 3]
_SIDE_B = [4, 5, 6, 7]

RESULTS_DIR = pathlib.Path(__file__).parent / 'results'
# ─────────────────────────────────────────────────────────────────────────────


def _generate_count(base_freq: float, n_out: int, side: str) -> tuple[np.ndarray, list]:
    """
    Returns (playdata, ref_signals).
    ref_signals[i] is the ideal BIT(i) waveform before any ES-9 round-trip,
    used as the reference for cross-correlation.
    """
    n = int(DURATION * SAMPLE_RATE)
    period = max(1, int(SAMPLE_RATE / base_freq))
    counter = np.arange(n) // period   # increments at base_freq

    fade_n   = int(FADE_SECONDS * SAMPLE_RATE)
    envelope = np.ones(n, dtype=np.float32)
    ramp = 0.5 * (1.0 - np.cos(np.pi * np.arange(fade_n) / fade_n))
    envelope[:fade_n]  = ramp
    envelope[-fade_n:] = ramp[::-1]

    bits = [
        (((counter >> b) & 1).astype(np.float32) * HIGH_LEVEL * envelope)
        for b in range(4)
    ]
    const = np.full(n, HIGH_LEVEL, dtype=np.float32) * envelope

    out = np.zeros((n, n_out), dtype=np.float32)
    count_outs = _SIDE_A if side == 'A' else _SIDE_B
    const_outs = _SIDE_B if side == 'A' else _SIDE_A

    for i, ch in enumerate(count_outs):
        out[:, ch] = bits[i]
    for ch in const_outs:
        out[:, ch] = const

    return out, bits


def _cross_correlate(ref: np.ndarray, captured: np.ndarray) -> tuple[int, float]:
    """Return (lag_samples, normalised_peak_correlation)."""
    r = ref - ref.mean()
    c = captured - captured.mean()
    r_std, c_std = r.std(), c.std()
    if r_std < 1e-9 or c_std < 1e-9:
        return 0, 0.0
    corr = np.correlate(c, r, mode='full')
    lag  = int(np.argmax(corr)) - (len(r) - 1)
    peak = float(np.max(corr) / (r_std * c_std * len(r)))
    return lag, peak


def _step_spectrum(step_signal: np.ndarray, base_freq: float) -> dict:
    """FFT of STEP output.  Fundamental = base_freq/16 (one full 0-15 cycle)."""
    fund = base_freq / 16.0
    n = len(step_signal)
    window = np.hanning(n)
    norm   = 2.0 / np.sum(window)
    spec   = np.abs(scipy_fft.rfft(step_signal * window)) * norm
    freqs  = scipy_fft.rfftfreq(n, 1.0 / SAMPLE_RATE)

    guard    = 3
    fund_bin = int(np.argmin(np.abs(freqs - fund)))
    fund_amp = float(np.max(spec[max(0, fund_bin - guard):fund_bin + guard + 1]))

    harmonics_dbfs = []
    for h in range(2, 18):
        hf = fund * h
        if hf >= freqs[-1]:
            break
        hbin = int(np.argmin(np.abs(freqs - hf)))
        harmonics_dbfs.append(
            round(float(20.0 * np.log10(
                np.max(spec[max(0, hbin - guard):hbin + guard + 1]) + 1e-12)), 2)
        )

    return {
        'fundamental_hz':     round(fund, 3),
        'fund_amp_dbfs':      round(float(20.0 * np.log10(fund_amp + 1e-12)), 2),
        'harmonic_amps_dbfs': harmonics_dbfs,
        '_spec':  spec,
        '_freqs': freqs,
    }


def _run_capture(device_idx: int, n_out: int, base_freq: float, side: str) -> dict:
    playdata, refs = _generate_count(base_freq, n_out, side)
    rec = sd.playrec(playdata, samplerate=SAMPLE_RATE,
                     channels=N_CAPTURE_CH, device=device_idx,
                     dtype='float32', blocking=True)
    skip = int(FADE_SECONDS * SAMPLE_RATE) + int(0.05 * SAMPLE_RATE)
    rec  = rec[skip:]
    refs = [r[skip:] for r in refs]

    # ES-9 roundtrip latency from loopback of BIT1
    es9_lag, es9_corr = _cross_correlate(refs[0], rec[:, LOOPBACK_IN])

    # Per-MIX latency, corrected for ES-9 roundtrip
    mix_latency = {}
    for i, name in enumerate(['MIX1', 'MIX2', 'MIX3', 'MIX4']):
        ch  = OUTPUTS[name]
        ref = refs[i] if i < len(refs) else refs[0]
        lag, corr = _cross_correlate(ref, rec[:, ch])
        mix_latency[name] = {
            'lag_samples': lag - es9_lag,
            'lag_us':      round((lag - es9_lag) / SAMPLE_RATE * 1e6, 1),
            'correlation': round(corr, 4),
        }

    step = _step_spectrum(rec[:, OUTPUTS['STEP']], base_freq)

    return {
        'base_freq_hz':    base_freq,
        'side':            side,
        'es9_lag_samples': es9_lag,
        'es9_corr':        round(es9_corr, 4),
        'mix_latency':     mix_latency,
        'step_spectrum':   {k: v for k, v in step.items() if not k.startswith('_')},
        '_step_spec':      step['_spec'],
        '_step_freqs':     step['_freqs'],
    }


def _save_step_png(results: list, stem: str):
    RESULTS_DIR.mkdir(exist_ok=True)
    fig, ax = plt.subplots(figsize=(14, 5))
    colors = plt.cm.tab10(np.linspace(0, 1, len(results)))

    for r, color in zip(results, colors):
        spec  = r.get('_step_spec')
        freqs = r.get('_step_freqs')
        if spec is None:
            continue
        db    = 20.0 * np.log10(np.maximum(spec, 1e-12))
        label = f"f={r['base_freq_hz']}Hz  side={r['side']}"
        ax.semilogx(freqs[1:], db[1:], label=label, color=color, linewidth=0.8, alpha=0.85)

    ax.set_xlabel('Frequency (Hz)')
    ax.set_ylabel('Amplitude (dBFS)')
    ax.set_title(f"BTMX STEP spectrum — {PLATFORM}  v{PLUGIN_VERSION}  logic={LOGIC_MODE}")
    ax.set_xlim(20, SAMPLE_RATE / 2)
    ax.legend(fontsize=7, ncol=2)
    ax.grid(True, which='both', alpha=0.3)
    fig.tight_layout()
    path = RESULTS_DIR / f"{stem}_step_spectra.png"
    fig.savefig(path, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"STEP spectra PNG  → {path}")


def _save_latency_png(results: list, stem: str):
    RESULTS_DIR.mkdir(exist_ok=True)
    mix_names = ['MIX1', 'MIX2', 'MIX3', 'MIX4']
    freqs     = sorted({r['base_freq_hz'] for r in results})
    sides     = sorted({r['side'] for r in results})

    fig, axes = plt.subplots(1, len(sides), figsize=(7 * len(sides), 4), sharey=True)
    if len(sides) == 1:
        axes = [axes]

    for ax, side in zip(axes, sides):
        side_results = [r for r in results if r['side'] == side]
        for mix in mix_names:
            lags = [r['mix_latency'].get(mix, {}).get('lag_us', float('nan'))
                    for r in side_results]
            ax.plot([r['base_freq_hz'] for r in side_results], lags,
                    marker='o', label=mix)
        ax.set_xscale('log')
        ax.set_xlabel('BIT1 frequency (Hz)')
        ax.set_title(f"Side {side}")
        ax.legend(fontsize=8)
        ax.grid(True, which='both', alpha=0.3)

    axes[0].set_ylabel('Latency (µs, ES-9 corrected)')
    fig.suptitle(f"BTMX MIX latency — {PLATFORM}  v{PLUGIN_VERSION}  logic={LOGIC_MODE}")
    fig.tight_layout()
    path = RESULTS_DIR / f"{stem}_latency.png"
    fig.savefig(path, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"Latency PNG       → {path}")


def _print_table(results: list):
    print(f"\nBTMX  [{PLATFORM}  v{PLUGIN_VERSION}  logic={LOGIC_MODE}]")
    hdr = (f"  {'side':<4} {'BIT1 Hz':>8}   {'ES9 lag':>8}"
           f"   {'MIX1':>9} {'MIX2':>9} {'MIX3':>9} {'MIX4':>9}"
           f"   {'STEP fund':>9}")
    print(hdr)
    print('  ' + '-' * (len(hdr) - 2))
    for r in results:
        lats = r['mix_latency']
        def _lag(name):
            v = lats.get(name, {}).get('lag_us')
            return f"{v:>8.1f}µ" if v is not None else f"{'—':>9}"
        print(f"  {r['side']:<4} {r['base_freq_hz']:>8.0f}"
              f"   {r['es9_lag_samples']:>6}smp"
              f"   {_lag('MIX1')} {_lag('MIX2')} {_lag('MIX3')} {_lag('MIX4')}"
              f"   {r['step_spectrum']['fund_amp_dbfs']:>8.1f}")
    print()


def run():
    device_idx, device_info = find_device(DEVICE_NAME)
    if device_idx is None:
        print(f"ERROR: '{DEVICE_NAME}' not found."); sys.exit(1)
    n_out = device_info['max_output_channels']
    print(f"Device : {device_info['name']}  (index {device_idx})")
    print(f"Config : {PLATFORM}  v{PLUGIN_VERSION}  logic={LOGIC_MODE}")
    print(f"         Set all BTMX switches to match '{LOGIC_MODE}' before proceeding.")

    all_results = []
    for side in TEST_SIDES:
        for freq in BASE_FREQS:
            print(f"  side={side}  BIT1={freq:.0f} Hz … ", end='', flush=True)
            r = _run_capture(device_idx, n_out, freq, side)
            all_results.append(r)
            print(f"done  (ES-9 lag {r['es9_lag_samples']} smp)")

    _print_table(all_results)

    stamp = datetime.datetime.now().strftime('%Y-%m-%d_%H%M%S')
    stem  = f"{stamp}_BTMX_{PLATFORM}"
    RESULTS_DIR.mkdir(exist_ok=True)
    _save_step_png(all_results, stem)
    _save_latency_png(all_results, stem)

    # Strip raw spectra before registry write
    clean = [{k: v for k, v in r.items() if not k.startswith('_')} for r in all_results]

    entry_id = registry.append({
        'module':         'BTMX',
        'platform':       PLATFORM,
        'plugin_version': PLUGIN_VERSION,
        'sdk_version':    SDK_VERSION,
        'conditions': {
            'logic_mode': LOGIC_MODE,
            'base_freqs': BASE_FREQS,
            'test_sides': TEST_SIDES,
            'high_level': HIGH_LEVEL,
        },
        'results': clean,
    })
    print(f"Registry  → {entry_id}")


if __name__ == '__main__':
    run()
