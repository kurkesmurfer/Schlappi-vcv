# Schlappi Engineering VCV Rack + MetaModule Modules

<img src="images/screenshot.png">

Digital adaptations of [Schlappi Engineering](https://schlappiengineering.com) hardware modules,
for **VCV Rack** and the **4ms MetaModule** Eurorack computer.
Includes [Nibbler](https://schlappiengineering.com/products/nibbler-preorder),
[BTMX](https://schlappiengineering.com/products/btmx), and
[BTFLD](https://schlappiengineering.com/products/btfld).

---

## Modules

### BTFLD — Bit Fold

A distortion, wavefolder, and 4-bit async ADC in one module. An incoming signal is
quantised into four binary gate outputs (MSB–LSB), which can be summed back into a
stepped CV or passed individually to other logic modules. A parallel wavefold path
produces frequency-multiplication-style harmonic saturation. Operates in unipolar
(0–10 V) or bipolar (±5 V) mode.

### BTMX — BitMix

Four-channel logic mixer. Each channel presents two inputs and a shared logic-function
selector (AND / ADD / OR / XOR). Channel outputs are binary-weighted and summed into a
single melodic/modulation CV output, and are also available individually. Operates at
full audio rate — useful as both a rhythmic gate mangler and an audio-rate harmonic
source.

### Nibbler

A 4-bit binary accumulator (CMOS counter, 0–15). A clock input advances the count;
carry, reset, and individual bit outputs are provided. A binary-weighted DAC output
produces a stepped voltage (0–10 V) corresponding to the current count, making it
useful for generating stepped sequences, rhythmic divisions, and Boolean logic.

---

## VCV Rack

The plugin is available through the [VCV Rack Library](https://library.vcvrack.com/)
under the *Schlappi Engineering* brand. Like the hardware modules, all three support
signals up to audio rate. Triggers and gates follow VCV Rack's
[voltage standards](https://vcvrack.com/manual/VoltageStandards). BTFLD output is
realistically saturated.

---

## MetaModule Port

### Status

Fully functional on MetaModule hardware (STM32MP157C, Cortex-A7). All three modules
have been verified in the firmware simulator and on hardware across multiple test patches.
Pre-built binaries are in [`mmplugin/`](mmplugin/).

### Installation

1. Copy the `.mmplugin` file from [`mmplugin/`](mmplugin/) to the `metamodule-plugins/`
   directory at the root of your MetaModule SD card or USB drive.
2. Insert the card/drive into your MetaModule and power on (or use the plugin browser to
   reload plugins if already running).
3. BTFLD, BTMX, and Nibbler appear in the module browser under *Schlappi Engineering*.

> **Remove any older version** before copying a new one — MetaModule loads all
> `.mmplugin` files it finds and will conflict if two versions of the same plugin
> are present.

---

## Technical Implementation — MetaModule DSP

The MetaModule runs at 48 kHz on a Cortex-A7 with strict real-time budget constraints.
The original VCVRack DSP used high-ratio oversampling (up to 16×) to suppress aliasing —
effective on a laptop, but far too expensive for embedded hardware. Each module was
rewritten under a compile-time guard (`#ifdef METAMODULE`) so the VCVRack and MetaModule
builds share the same source file while using different DSP paths.

### BTFLD

**Original path (VCVRack):** 8× upsampling (Q12 FIR), a BitCalculator/oddTracker
hysteresis stage requiring 12 consecutive samples at the same odd value before
asserting a gate, and 6 FIR decimators on the outputs. CPU on MetaModule: >99%
(unusable).

**MetaModule path:** First-order Antiderivative Anti-Aliasing (ADAA) on the SAW
output eliminates discontinuity-induced aliasing without oversampling. Bit outputs
are extracted directly from the quantised signal at base rate. A 10 kHz one-pole
low-pass filter on the SAW and STEP outputs approximates the analog roll-off of the
hardware module. CPU on MetaModule hardware: **~17%**.

ADAA works by integrating the transfer function analytically and computing the
output as the finite difference of antiderivatives, which cancels the spectral
artefacts that arise from sampling a nonlinear discontinuity directly. The result
is perceptually very close to the oversampled version — subjective listening tests
show the difference to be minimal.

### BTMX

**Original path (VCVRack):** 16× upsampling (Q4 FIR) on all four channels, full FIR
decimation on MIX and STEP outputs. CPU on MetaModule: >99% (unusable).

**MetaModule path:** Schmitt triggers at base rate replace the upsampled threshold
comparators. Boolean logic (AND/OR/XOR) operates on the Schmitt trigger outputs. A
10 kHz one-pole low-pass filter on the STEP output smooths the binary-weighted sum.
CPU on MetaModule hardware: **~13%**.

### Nibbler

**Original path (VCVRack):** 16× oversampling (Q4 FIR) on clock and reset inputs.

**MetaModule path:** Oversampling ratio reduced to 8× (Q2 FIR). Input processing
guarded with `isConnected()` checks to skip inactive channels. Light update divider
increased to 256 samples. CPU on MetaModule hardware: **~31%**.

### Denormal float suppression

All three modules set the ARM Flush-to-Zero (FTZ) bit in the FPSCR register on every
`process()` call. Denormal floats in one-pole filters accumulate exponentially and
cause audible HF glitching on hardware; FTZ eliminates this without affecting the
audible frequency range.

---

## Building from Source

### Dependencies

- ARM GNU Toolchain 12.3 (`arm-none-eabi-gcc`)
- MetaModule Plugin SDK ([4ms/metamodule-plugin-sdk](https://github.com/4ms/metamodule-plugin-sdk))
- Ninja build system

### MetaModule plugin

```bash
cd metamodule
cmake --fresh -B build -G Ninja \
  -DTOOLCHAIN_BASE_DIR=/path/to/ArmGNUToolchain/12.3.rel1/arm-none-eabi/bin \
  -DMETAMODULE_SDK_DIR=/path/to/metamodule-plugin-sdk
cmake --build build
# Output: metamodule/metamodule-plugins/SchlappiEngineering-vX.Y.Z.mmplugin
```

### VCV Rack plugin

```bash
RACK_DIR=/path/to/Rack2SDK make
```

---

## Credits

Original VCVRack plugin by a student contributor with support from Eric Schlappi and
Dan Green (4ms). MetaModule port and DSP optimisation by subsequent contributors.
Hardware modules by [Schlappi Engineering](https://schlappiengineering.com).
