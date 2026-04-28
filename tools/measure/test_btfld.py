"""
BTFLD isolation test — sine stimulus, all outputs captured.

ES-9 wiring
-----------
  OUT 1  →  BTFLD IN         (sine signal)
  OUT 2  →  BTFLD CV         (silence — gain set by module parameter)
  OUT 3  →  BTFLD INJECT     (silence)

  IN  1  ←  BTFLD SAW
  IN  2  ←  BTFLD BIT8
  IN  3  ←  BTFLD BIT4
  IN  4  ←  BTFLD BIT2
  IN  5  ←  BTFLD BIT1
  IN  6  ←  BTFLD STEP
  IN  9  ←  loopback (OUT 1) — source reference

Module state to document before running
-----------------------------------------
  GAIN knob, RANGE switch (unipolar/bipolar)
  Set PLATFORM, PLUGIN_VERSION, GAIN_PARAM, RANGE_PARAM below.
"""

import sys
import datetime
import pathlib

import matplotlib.pyplot as plt
import numpy as np
import sounddevice as sd
from scipy import fft as scipy_fft

import registry
from measure import find_device, analyze_channel, SAMPLE_RATE

# ── Configuration — edit before each run ──────────────────────────────────────
PLATFORM       = 'metamodule'   # 'metamodule' | 'vcvrack' | 'hardware'
PLUGIN_VERSION = '2.0.22'
SDK_VERSION    = 'api-v2.1.0'

GAIN_PARAM     = 0.75           # knob position 0..1
RANGE_PARAM    = 'unipolar'     # 'unipolar' | 'bipolar'

DEVICE_NAME    = 'ES-9'
DURATION       = 4.0
AMPLITUDE      = 0.8
FADE_SECONDS   = 0.01
TEST_FREQS     = [100, 440, 1000, 4000]

# ES-9 assignments (0-indexed)
SIGNAL_OUT     = 0   # OUT1 → BTFLD IN
N_CAPTURE_CH   = 9
OUTPUTS = {          # name: ES-9 input index
    'SAW':  0,
    'BIT8': 1,
    'BIT4': 2,
    'BIT2': 3,
    'BIT1': 4,
    'STEP': 5,
}
LOOPBACK_IN    = 8   # IN9

RESULTS_DIR = pathlib.Path(__file__).parent / 'results'
# ─────────────────────────────────────────────────────────────────────────────


def _generate_playback(freq: float, n_out: int) -> np.ndarray:
    n = int(DURATION * SAMPLE_RATE)
    t = np.arange(n) / SAMPLE_RATE
    sine = AMPLITUDE * np.sin(2.0 * np.pi * freq * t)
    fade_n = int(FADE_SECONDS * SAMPLE_RATE)
    ramp = 0.5 * (1.0 - np.cos(np.pi * np.arange(fade_n) / fade_n))
    sine[:fade_n]  *= ramp
    sine[-fade_n:] *= ramp[::-1]
    out = np.zeros((n, n_out), dtype=np.float32)
    out[:, SIGNAL_OUT] = sine.astype(np.float32)
    return out


def _run_freq(device_idx: int, n_out: int, freq: float) -> dict:
    rec = sd.playrec(_generate_playback(freq, n_out), samplerate=SAMPLE_RATE,
                     channels=N_CAPTURE_CH, device=device_idx,
                     dtype='float32', blocking=True)
    skip = int(FADE_SECONDS * SAMPLE_RATE) + int(0.05 * SAMPLE_RATE)
    rec  = rec[skip:]

    outputs = {}
    spectra = {}
    for name, ch in OUTPUTS.items():
        a = analyze_channel(rec[:, ch], fundamental=freq)
        outputs[name] = {
            'thd_db':         round(float(a['thd_db']),         2),
            'sfdr_db':        round(float(a['sfdr_db']),        2),
            'noise_floor_db': round(float(a['noise_floor_db']), 2),
            'fund_amp_dbfs':  round(float(20.0 * np.log10(a['fund_amp'] + 1e-12)), 2),
        }
        spectra[name] = (a['spectrum'], a['freqs'])

    loop = analyze_channel(rec[:, LOOPBACK_IN], fundamental=freq)
    return {
        'freq_hz':  freq,
        'outputs':  outputs,
        'loopback': {'fund_amp_dbfs': round(float(20.0 * np.log10(loop['fund_amp'] + 1e-12)), 2)},
        '_spectra': spectra,
    }


def _save_spectrum_png(results: list, stem: str):
    RESULTS_DIR.mkdir(exist_ok=True)
    n = len(results)
    fig, axes = plt.subplots(n, 1, figsize=(14, 4 * n), sharex=True)
    if n == 1:
        axes = [axes]
    colors = plt.cm.tab10(np.linspace(0, 1, len(OUTPUTS)))

    for ax, r in zip(axes, results):
        for (name, _), color in zip(OUTPUTS.items(), colors):
            spec, freqs = r['_spectra'][name]
            db = 20.0 * np.log10(np.maximum(spec, 1e-12))
            ax.semilogx(freqs[1:], db[1:], label=name, color=color,
                        linewidth=0.8, alpha=0.85)
        ax.set_title(f"{r['freq_hz']:.0f} Hz  (loopback fund: {r['loopback']['fund_amp_dbfs']:.1f} dBFS)",
                     fontsize=9)
        ax.set_ylabel('dBFS')
        ax.legend(fontsize=7, ncol=3)
        ax.grid(True, which='both', alpha=0.3)
        ax.set_xlim(20, SAMPLE_RATE / 2)

    axes[-1].set_xlabel('Frequency (Hz)')
    fig.suptitle(f"BTFLD — {PLATFORM}  v{PLUGIN_VERSION}  gain={GAIN_PARAM}  {RANGE_PARAM}")
    fig.tight_layout()
    path = RESULTS_DIR / f"{stem}_spectrum.png"
    fig.savefig(path, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"Spectrum PNG  → {path}")


def _print_table(results: list):
    print(f"\nBTFLD  [{PLATFORM}  v{PLUGIN_VERSION}  gain={GAIN_PARAM}  {RANGE_PARAM}]")
    hdr = f"  {'Output':<8} {'Freq':>6}   {'THD (dB)':>9} {'SFDR (dB)':>10} {'Noise (dBFS)':>13} {'Fund (dBFS)':>12}"
    print(hdr)
    print('  ' + '-' * (len(hdr) - 2))
    for r in results:
        for name, m in r['outputs'].items():
            print(f"  {name:<8} {r['freq_hz']:>6.0f}"
                  f"   {m['thd_db']:>9.1f} {m['sfdr_db']:>10.1f}"
                  f" {m['noise_floor_db']:>13.1f} {m['fund_amp_dbfs']:>12.1f}")
    print()


def run():
    device_idx, device_info = find_device(DEVICE_NAME)
    if device_idx is None:
        print(f"ERROR: '{DEVICE_NAME}' not found."); sys.exit(1)
    n_out = device_info['max_output_channels']
    print(f"Device : {device_info['name']}  (index {device_idx})")
    print(f"Config : {PLATFORM}  v{PLUGIN_VERSION}  gain={GAIN_PARAM}  {RANGE_PARAM}")

    all_results = []
    for freq in TEST_FREQS:
        print(f"  {freq:.0f} Hz … ", end='', flush=True)
        r = _run_freq(device_idx, n_out, freq)
        all_results.append(r)
        print("done")

    _print_table(all_results)

    stamp = datetime.datetime.now().strftime('%Y-%m-%d_%H%M%S')
    stem  = f"{stamp}_BTFLD_{PLATFORM}"
    _save_spectrum_png(all_results, stem)

    # Strip raw spectra before writing to registry
    clean = [{k: v for k, v in r.items() if k != '_spectra'} for r in all_results]

    entry_id = registry.append({
        'module':         'BTFLD',
        'platform':       PLATFORM,
        'plugin_version': PLUGIN_VERSION,
        'sdk_version':    SDK_VERSION,
        'conditions': {
            'gain_param':  GAIN_PARAM,
            'range_param': RANGE_PARAM,
            'freqs_hz':    TEST_FREQS,
            'amplitude':   AMPLITUDE,
        },
        'results': clean,
    })
    print(f"Registry  → {entry_id}")


if __name__ == '__main__':
    run()
