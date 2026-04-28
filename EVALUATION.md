## Module Comparison Measurement Framework

### Purpose
Objective THD/SFDR comparison across hardware modules, MetaModule ports, and VCV originals
using simultaneous multi-channel capture via Expert Sleepers ES-9.

### Hardware setup
- ES-9 output channel 1: sine source (software-generated, known quality)
- ES-9 output channel 1 → buffered multiple → all module inputs under test
- ES-9 input channels 1–N: one per module output
- Recommended channel assignment:
  - Ch 1–3: BTFLD hardware units
  - Ch 4–6: Nibbler hardware units  
  - Ch 7–8: BTMX hardware units
  - Ch 9:   ES-9 loopback of source (baseline/reference)
- MetaModule and VCV captures: separate runs, same script

### Software
- Location: `tools/measure/`
- Entry point: `measure.py`
- Dependencies: `sounddevice`, `numpy`, `scipy`, `matplotlib`, `pandas`
- Python environment: see `tools/measure/requirements.txt`

### Script specification: `tools/measure/measure.py`

#### Configuration (top of file, no argparse needed initially)
```python
DEVICE_NAME   = 'ES-9'          # match output of sd.query_devices()
SAMPLE_RATE   = 48000
CHANNELS_IN   = 9               # adjust to actual channel count
OUTPUT_CHANNEL = 0              # 0-indexed ES-9 output for sine source
FUNDAMENTAL   = 440.0           # Hz, change per run
DURATION      = 4.0             # seconds capture
AMPLITUDE     = 0.8             # 0..1, leave headroom
CHANNEL_LABELS = [
    'BTFLD_hw_1', 'BTFLD_hw_2', 'BTFLD_hw_3',
    'Nibbler_hw_1', 'Nibbler_hw_2', 'Nibbler_hw_3',
    'BTMX_hw_1', 'BTMX_hw_2',
    'source_loopback'
]
```

#### Signal generation
- Generate sine via `sounddevice.playrec()` — simultaneous play+record in one call
- Sine on OUTPUT_CHANNEL only, other output channels silent
- Apply a short (10 ms) raised cosine fade-in/out to avoid transient contamination

#### Analysis per channel
For each captured channel:

1. **Window**: apply Hann window before FFT to reduce spectral leakage
2. **FFT**: `scipy.fft.rfft`, normalize to amplitude spectrum
3. **Fundamental bin**: locate peak near `FUNDAMENTAL` within ±5 bins
   (accounts for minor tuning drift)
4. **THD**: extract bins at harmonics 2f..10f, compute
   `THD_dB = 20*log10(sqrt(sum(h_i^2)) / fund_amplitude)`
5. **Alias detection**: mask all harmonic bins ±5 bins wide plus DC region <20 Hz.
   Remaining spectrum is candidate alias/spur content.
   `SFDR_dB = 20*log10(fund_amplitude / max(masked_spectrum))`
6. **Noise floor estimate**: median of masked spectrum in dB, gives SNR context

#### Output
- Console table: module label, THD (dB), SFDR (dB), noise floor (dB)
- `results/YYYY-MM-DD_HHMMSS_<fundamental>Hz.csv`: full per-channel results
- `results/YYYY-MM-DD_HHMMSS_<fundamental>Hz_spectrum.png`:
  overlaid magnitude spectra, all channels, log frequency axis, dB amplitude,
  color-coded by module type (hardware / MM port / VCV)
- `results/YYYY-MM-DD_HHMMSS_<fundamental>Hz_harmonics.png`:
  bar chart of harmonic amplitudes relative to fundamental, per channel

#### Suggested test frequencies
Run the script at each: 100 Hz, 440 Hz, 1 kHz, 4 kHz
Higher frequencies stress the alias rejection harder on 48 kHz systems.

#### Known gotchas for Claude Code
- `sounddevice.playrec()` requires `blocking=True` or explicit `sd.wait()`
- ES-9 device name on macOS may appear as `ES-9 (N in, M out)` — use substring match
- Channel indexing in sounddevice is 0-based; ES-9 panel labeling is 1-based
- ES-9 input gain is fixed; modular output at +/-5V is within its input range,
  no attenuation needed
- Hann window normalization: multiply FFT result by `2/sum(window)` for correct
  amplitude after windowing
- For VCV/MM captures (no live hardware): omit playrec, use `sd.rec()` only,
  feed sine from VCV/MM internal oscillator instead

### Planned extensions
- Parameter sweep mode: vary fold depth via MIDI CC or manual steps, capture
  at each position, produce THD-vs-parameter curve
- Schlappi² comparison column once firmware available
- Unit-to-unit spread visualization: box plot across hardware units of same type

