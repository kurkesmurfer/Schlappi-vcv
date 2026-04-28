"""
Module comparison measurement: THD / SFDR capture via ES-9.
ES-9 required only for run_measurement(); smoke test runs without it.
"""

import datetime
import pathlib
import sys

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import sounddevice as sd
from scipy import fft

# ── Configuration ─────────────────────────────────────────────────────────────
DEVICE_NAME    = 'ES-9'          # substring-matched against sd.query_devices()
SAMPLE_RATE    = 48000
CHANNELS_IN    = 9               # ES-9 input channels to record
OUTPUT_CHANNEL = 0               # 0-indexed ES-9 output for sine source
FUNDAMENTAL    = 440.0           # Hz — change per run (100, 440, 1000, 4000)
DURATION       = 4.0             # seconds
AMPLITUDE      = 0.8             # 0..1, leave headroom

CHANNEL_LABELS = [
    'BTFLD_hw_1', 'BTFLD_hw_2', 'BTFLD_hw_3',
    'Nibbler_hw_1', 'Nibbler_hw_2', 'Nibbler_hw_3',
    'BTMX_hw_1', 'BTMX_hw_2',
    'source_loopback',
]
# ─────────────────────────────────────────────────────────────────────────────

RESULTS_DIR  = pathlib.Path(__file__).parent / 'results'
FADE_SECONDS = 0.01   # raised-cosine fade in/out to avoid transient contamination
N_HARMONICS  = 9      # harmonics 2f..10f
BIN_GUARD    = 5      # ±bins masked around each harmonic for SFDR


# ── Device helpers ────────────────────────────────────────────────────────────

def find_device(name: str):
    """Return (index, info_dict) for first device whose name contains `name`."""
    for i, dev in enumerate(sd.query_devices()):
        if name.lower() in dev['name'].lower():
            return i, dev
    return None, None


# ── Signal generation ─────────────────────────────────────────────────────────

def generate_playback(n_out_channels: int) -> np.ndarray:
    """Sine on OUTPUT_CHANNEL, silence on all others, with raised-cosine fades."""
    n = int(DURATION * SAMPLE_RATE)
    t = np.arange(n) / SAMPLE_RATE
    sine = AMPLITUDE * np.sin(2.0 * np.pi * FUNDAMENTAL * t)

    fade_n = int(FADE_SECONDS * SAMPLE_RATE)
    ramp = 0.5 * (1.0 - np.cos(np.pi * np.arange(fade_n) / fade_n))
    sine[:fade_n]  *= ramp
    sine[-fade_n:] *= ramp[::-1]

    out = np.zeros((n, n_out_channels), dtype=np.float32)
    out[:, OUTPUT_CHANNEL] = sine.astype(np.float32)
    return out


# ── Analysis ──────────────────────────────────────────────────────────────────

def analyze_channel(signal: np.ndarray, fundamental: float = FUNDAMENTAL) -> dict:
    """
    Returns dict with thd_db, sfdr_db, noise_floor_db, fund_amp,
    harmonic_amps, spectrum, freqs.
    """
    n = len(signal)
    window = np.hanning(n)
    norm = 2.0 / np.sum(window)                    # correct amplitude after windowing
    spectrum = np.abs(fft.rfft(signal * window)) * norm
    freqs = fft.rfftfreq(n, 1.0 / SAMPLE_RATE)

    # Locate fundamental (search ±BIN_GUARD bins around expected bin)
    fund_bin_est = np.argmin(np.abs(freqs - fundamental))
    lo = max(0, fund_bin_est - BIN_GUARD)
    hi = min(len(spectrum), fund_bin_est + BIN_GUARD + 1)
    fund_bin = lo + int(np.argmax(spectrum[lo:hi]))
    fund_amp = spectrum[fund_bin]

    # Harmonic amplitudes 2f..10f
    harmonic_amps = []
    for h in range(2, 2 + N_HARMONICS):
        hf = fundamental * h
        if hf >= freqs[-1]:
            break
        hbin = np.argmin(np.abs(freqs - hf))
        lo_h = max(0, hbin - BIN_GUARD)
        hi_h = min(len(spectrum), hbin + BIN_GUARD + 1)
        harmonic_amps.append(float(np.max(spectrum[lo_h:hi_h])))

    thd_rms = np.sqrt(np.sum(np.array(harmonic_amps) ** 2))
    thd_db = 20.0 * np.log10(thd_rms / fund_amp) if fund_amp > 0 else np.nan

    # Build mask: DC region + fundamental + all harmonics ±BIN_GUARD bins
    mask = freqs < 20.0
    for h in range(1, 2 + N_HARMONICS):
        hf = fundamental * h
        if hf >= freqs[-1]:
            break
        hbin = np.argmin(np.abs(freqs - hf))
        mask[max(0, hbin - BIN_GUARD):min(len(spectrum), hbin + BIN_GUARD + 1)] = True

    remaining = spectrum[~mask]
    if len(remaining) == 0:
        sfdr_db = noise_floor_db = np.nan
    else:
        peak_spur = float(np.max(remaining))
        sfdr_db = 20.0 * np.log10(fund_amp / peak_spur) if peak_spur > 0 else np.nan
        noise_floor_db = float(20.0 * np.log10(np.median(remaining) + 1e-12))

    return {
        'fund_amp':       float(fund_amp),
        'thd_db':         float(thd_db),
        'sfdr_db':        float(sfdr_db),
        'noise_floor_db': float(noise_floor_db),
        'harmonic_amps':  harmonic_amps,
        'spectrum':       spectrum,
        'freqs':          freqs,
    }


# ── Output ────────────────────────────────────────────────────────────────────

def print_table(results: list[dict]):
    header = f"{'Label':<22} {'THD (dB)':>9} {'SFDR (dB)':>10} {'Noise (dBFS)':>13}"
    print()
    print(header)
    print('-' * len(header))
    for r in results:
        print(
            f"{r['label']:<22} {r['thd_db']:>9.1f} {r['sfdr_db']:>10.1f}"
            f" {r['noise_floor_db']:>13.1f}"
        )
    print()


def save_csv(results: list[dict], stem: str):
    RESULTS_DIR.mkdir(exist_ok=True)
    df = pd.DataFrame([{
        'label':          r['label'],
        'channel':        r['channel'],
        'fund_amp_dbfs':  round(20.0 * np.log10(r['fund_amp'] + 1e-12), 2),
        'thd_db':         round(r['thd_db'], 2),
        'sfdr_db':        round(r['sfdr_db'], 2),
        'noise_floor_db': round(r['noise_floor_db'], 2),
    } for r in results])
    path = RESULTS_DIR / f"{stem}.csv"
    df.to_csv(path, index=False)
    print(f"CSV  → {path}")


def save_spectrum_png(results: list[dict], stem: str):
    RESULTS_DIR.mkdir(exist_ok=True)
    fig, ax = plt.subplots(figsize=(14, 6))
    colors = plt.cm.tab10(np.linspace(0, 1, len(results)))

    for r, color in zip(results, colors):
        db = 20.0 * np.log10(np.maximum(r['spectrum'], 1e-12))
        ax.semilogx(r['freqs'][1:], db[1:], label=r['label'],
                    color=color, linewidth=0.8, alpha=0.85)

    ax.set_xlabel('Frequency (Hz)')
    ax.set_ylabel('Amplitude (dBFS)')
    ax.set_title(f"Magnitude spectrum — {FUNDAMENTAL:.0f} Hz  ({stem})")
    ax.set_xlim(20, SAMPLE_RATE / 2)
    ax.legend(fontsize=7, ncol=2)
    ax.grid(True, which='both', alpha=0.3)

    path = RESULTS_DIR / f"{stem}_spectrum.png"
    fig.savefig(path, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"Spectrum PNG → {path}")


def save_harmonics_png(results: list[dict], stem: str):
    RESULTS_DIR.mkdir(exist_ok=True)
    n = len(results)
    fig, axes = plt.subplots(1, n, figsize=(max(3 * n, 6), 5), sharey=True)
    if n == 1:
        axes = [axes]

    for ax, r in zip(axes, results):
        amps = r['harmonic_amps']
        if r['fund_amp'] > 0 and amps:
            db = [20.0 * np.log10(a / r['fund_amp'] + 1e-12) for a in amps]
        else:
            db = [np.nan] * len(amps)
        ax.bar(range(2, 2 + len(db)), db)
        ax.set_title(r['label'], fontsize=8)
        ax.set_xlabel('Harmonic')
        ax.axhline(0, color='k', linewidth=0.5)

    axes[0].set_ylabel('Amplitude rel. to fundamental (dB)')
    fig.suptitle(f"Harmonic amplitudes — {FUNDAMENTAL:.0f} Hz")
    fig.tight_layout()

    path = RESULTS_DIR / f"{stem}_harmonics.png"
    fig.savefig(path, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"Harmonics PNG → {path}")


# ── Measurement run ───────────────────────────────────────────────────────────

def run_measurement():
    device_idx, device_info = find_device(DEVICE_NAME)
    if device_idx is None:
        print(f"ERROR: device '{DEVICE_NAME}' not found. Available devices:")
        print(sd.query_devices())
        sys.exit(1)

    n_out = device_info['max_output_channels']
    playdata = generate_playback(n_out)

    print(f"Device : {device_info['name']}  (index {device_idx})")
    print(f"Capture: {DURATION}s  |  {SAMPLE_RATE} Hz  |  {FUNDAMENTAL:.0f} Hz sine  "
          f"|  output ch {OUTPUT_CHANNEL + 1}  |  {CHANNELS_IN} input channels")

    recording = sd.playrec(
        playdata,
        samplerate=SAMPLE_RATE,
        channels=CHANNELS_IN,
        device=device_idx,
        dtype='float32',
        blocking=True,
    )

    # Skip fade + 50 ms settling before analysis
    skip = int(FADE_SECONDS * SAMPLE_RATE) + int(0.05 * SAMPLE_RATE)
    recording = recording[skip:]

    results = []
    for ch in range(CHANNELS_IN):
        label = CHANNEL_LABELS[ch] if ch < len(CHANNEL_LABELS) else f'ch_{ch + 1}'
        r = analyze_channel(recording[:, ch])
        r['label']   = label
        r['channel'] = ch + 1
        results.append(r)

    print_table(results)

    stamp = datetime.datetime.now().strftime('%Y-%m-%d_%H%M%S')
    stem  = f"{stamp}_{int(FUNDAMENTAL)}Hz"
    save_csv(results, stem)
    save_spectrum_png(results, stem)
    save_harmonics_png(results, stem)

    return results


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == '__main__':
    print("=== sounddevice smoke test ===")
    print(sd.query_devices())

    device_idx, device_info = find_device(DEVICE_NAME)
    if device_idx is None:
        print(f"\nDevice '{DEVICE_NAME}' not found — skipping capture.")
        print("Connect and power on the ES-9, then re-run.")
        sys.exit(0)

    print(f"\nFound '{DEVICE_NAME}': {device_info['name']}  (index {device_idx})")
    run_measurement()
