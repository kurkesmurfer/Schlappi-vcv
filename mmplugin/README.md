# MetaModule Plugin Binaries

This directory contains prototype `.mmplugin` binaries for the Schlappi Engineering
MetaModule port. These are provided for testing purposes — they are **not yet
official releases**.

## Installation

1. Copy the `.mmplugin` file to the `metamodule-plugins/` directory at the root of
   your MetaModule SD card or USB drive.
2. Insert the card/drive into your MetaModule and power on (or use the plugin browser
   to reload plugins if already running).
3. The three modules — **BTFLD**, **BTMX**, and **Nibbler** — will appear in the
   module browser under *Schlappi Engineering*.

## Modules

| Module | Description |
|--------|-------------|
| **BTFLD** | Bit Fold — distortion, wavefolder, and 4-bit async ADC |
| **BTMX** | BitMix — 4-channel logic mixer (AND / ADD / OR / XOR) with binary-weighted CV output |
| **Nibbler** | 4-bit binary accumulator / counter with individual bit I/O and stepped DAC output |

## Binaries

| Version | Notes |
|---------|-------|
| v2.0.22 | Current build — BTFLD ADAA + LP, BTMX base-rate Schmitt triggers, Nibbler 8× OS. **Pending hardware validation.** |
| v2.0.13 | Last hardware-validated build |

## Status

- These builds target the MetaModule hardware (STM32MP157, Cortex-A7).
- DSP has been verified in the MetaModule simulator and on hardware.
- BTFLD uses first-order ADAA (Antiderivative Anti-Aliasing) for the SAW output and
  a 10 kHz one-pole LP on SAW and STEP outputs to approximate the analog character
  of the hardware module — the MetaModule version is intentionally close to the
  hardware sound.
- CPU usage on hardware (isolated patches): BTFLD ~17%, BTMX ~13%, Nibbler ~31%.
- Feedback and bug reports welcome — please open an issue in this repository.
