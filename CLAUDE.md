# Schlappi Engineering — MetaModule Port
## Project Overview

This project ports the Schlappi Engineering VCVRack plugin to run natively on the
4ms MetaModule hardware. The three modules being ported are:

- **Nibbler** — 4-bit digital accumulator (CMOS binary counter, 0–15, with individual
  bit I/O and stepped voltage DAC outputs)
- **BTMX** (BitMix) — 4-channel selectable logic function module; 4 logic functions,
  binary-weighted stepped CV output; works at audio and gate rates
- **BTFLD** (Bit Fold) — distortion, wavefolder, and 4-bit async ADC; frequency
  multiplication; unipolar and bipolar operation

The original VCVRack plugin was written by a student with endorsement from Eric Schlappi
and Dan Green (4ms). The student ran out of time before completing the MetaModule port,
but made significant progress — the `metamodule/` directory and SDK submodule are
already present in the repo.

**Source repo:** https://github.com/SchlappiEngineering/Schlappi-vcv

---

## Repository Layout

```
Schlappi-vcv/
├── src/                        # VCVRack plugin C++ source (the DSP core)
├── res/                        # SVG panel graphics (need PNG conversion for MM)
├── images/                     # Reference images
├── metamodule/                 # MetaModule port (partially complete)
│   ├── CMakeLists.txt          # May exist — check and complete if needed
│   ├── plugin-mm.json          # MetaModule manifest — check and complete
│   └── assets/                 # PNG assets for MetaModule (may be empty/missing)
├── metamodule-plugin-sdk/      # Git submodule, pinned at ca30a93
│   └── (4ms SDK)
├── plugin.json                 # VCVRack plugin manifest (brand slug, module list)
└── .github/workflows/          # CI — may have build hints
```

**First task in every session:** run `ls metamodule/` and `cat metamodule/CMakeLists.txt`
to understand what the student completed. Do not assume file contents.

---

## Environment & Toolchain

### Confirmed local paths
```
RACK_DIR=~/Development/Rack2SDK                         # fill in exact path if different
METAMODULE_SDK_DIR=~/Development/metamodule-plugin-sdk  # central copy, not the submodule
ARM_TOOLCHAIN_v12=/Applications/ArmGNUToolchain/12.3.rel1/arm-none-eabi/bin
ARM_TOOLCHAIN_v10=/Users/peet/Development/bluenet/tools/gcc-arm-none-eabi-10.3-2021.10/bin
```

### Toolchain situation — critical
There are **two ARM toolchains** on this machine. They must never be confused:

| Toolchain | Version | Path | Used for |
|-----------|---------|------|----------|
| bluenet (on PATH) | gcc 10.3-2021.10 | `…/bluenet/tools/gcc-arm-none-eabi-10.3-2021.10/bin` | nRF52/54 (Nordic) |
| ArmGNUToolchain (NOT on PATH) | gcc 12.3.rel1 | `/Applications/ArmGNUToolchain/12.3.rel1/arm-none-eabi/bin` | MetaModule |

The bluenet toolchain wins `which arm-none-eabi-gcc` — **this is intentional and correct**.
The MetaModule SDK requires v12 and will produce errors or silently wrong output with v10.
Always pass `TOOLCHAIN_BASE_DIR` explicitly; never rely on the ambient PATH for MM builds.

### SDK submodule policy
The repo contains `metamodule-plugin-sdk/` as a git submodule (pinned at `ca30a93`).
We do **not** use the submodule. Instead we point cmake at the central copy:
```
~/Development/metamodule-plugin-sdk
```
Do not run `git submodule update --init` — leave the submodule uninitialised.
If cmake complains about a missing SDK, always fix by passing `METAMODULE_SDK_DIR`,
not by initialising the submodule.

If the SDK version ever matters (the submodule pin differs from your central copy),
check: `git -C ~/Development/metamodule-plugin-sdk log --oneline -1` vs `ca30a93`.

### Build command (MetaModule plugin)
```bash
cd metamodule
cmake --fresh -B build -G Ninja \
  -DTOOLCHAIN_BASE_DIR=/Applications/ArmGNUToolchain/12.3.rel1/arm-none-eabi/bin \
  -DMETAMODULE_SDK_DIR=~/Development/metamodule-plugin-sdk
cmake --build build
```
Output will be a `.mmplugin` file in `metamodule/metamodule-plugins/`.

### Build command (VCVRack plugin, for reference/testing DSP)
```bash
cd Schlappi-vcv
RACK_DIR=~/Development/Rack2SDK make   # adjust path if needed
```

---

## MetaModule SDK — Key Facts

The SDK wraps the Rack API so that **existing VCVRack `src/` code compiles largely
unchanged** for ARM. The plugin-facing API closely mirrors Rack SDK v2.4.1.

### What the SDK handles automatically
- Rack `Module::process()` loop
- Param, Input, Output, Light indexing
- `APP->engine` and timing infrastructure

### What requires attention when porting
- **No nanovg / UI drawing code runs on hardware.** Widgets are rendered by the MM
  engine. Children of Param/Jack/Light widgets are ignored — pure DSP code is fine,
  any custom `draw()` overrides in the widget classes will be silently skipped.
- **SVGs must be converted to PNGs** for the `assets/` directory. The MetaModule
  renders its own panel from these PNGs. Use `rsvg-convert` or Inkscape batch export.
  If blocked on assets, create an empty `assets/` dir to unblock compilation.
- **`plugin-mm.json`** is required alongside the standard `plugin.json`. It describes
  the brand and which modules to expose on MetaModule.

### plugin-mm.json structure (minimal example)
```json
{
  "plugin-name": "SchlappiEngineering",
  "plugin-version": "2.0.0",
  "modules": [
    { "slug": "Nibbler",  "name": "Nibbler"  },
    { "slug": "BTMX",     "name": "BTMX"     },
    { "slug": "BTFLD",    "name": "BTFLD"    }
  ]
}
```
The `slug` values must match those in `plugin.json` exactly.

---

## Module DSP Notes

These modules are based on CMOS 4-bit binary logic — the DSP cores are integer/bitwise
operations with minimal floating point. They should cross-compile to ARM cleanly.

### Nibbler
- Counts 0–15 in binary on a clock input; reset, carry, and individual bit outputs
- DAC output: binary-weighted sum of bit outputs → stepped voltage (0 to ~10V)
- Watch for: any `float`-based bit manipulation that might behave differently under
  ARM strict aliasing

### BTMX
- 4 channels × 2 inputs each; shared logic function selector (AND/OR/XOR/XNOR or similar)
- Binary-weighted sum output for melodic/modulation CV
- Each channel has a hardware toggle switch — maps to a Param in VCVRack

### BTFLD
- Async 4-bit ADC: converts analog signal to 4 gate outputs (MSB–LSB)
- Wavefolder / distortion path in parallel
- Can run unipolar (0–10V) or bipolar (±5V) — check how mode switching is implemented
  (likely a Param or input normalling)

---

## Known Issues / Things to Check

- [ ] Confirm what the student completed in `metamodule/` — CMakeLists, JSON, assets
- [ ] Check `.github/workflows/` for any existing MetaModule CI that reveals build intent
- [ ] Do NOT initialise the git submodule — use `~/Development/metamodule-plugin-sdk` instead
- [ ] Verify `RACK_DIR` exact path (`ls ~/Development/Rack2SDK` or equivalent)
- [ ] SVG → PNG conversion for panel graphics (can defer; create empty `assets/` to unblock)
- [ ] Test VCVRack build still works after any changes
- [ ] Once `.mmplugin` builds, test first in simulator, then on MetaModule hardware

### Toolchain sanity check (run before first build)
```bash
# Should report 10.3 — bluenet toolchain, correct
arm-none-eabi-gcc --version

# Should report 12.3 — MetaModule toolchain, correct
/Applications/ArmGNUToolchain/12.3.rel1/arm-none-eabi/bin/arm-none-eabi-gcc --version
```

---

## Simulator

> **Before rebuilding the simulator**, read `~/Development/metamodule/CLAUDE.md`.
> A parallel Claude Code session (SignalFunctionSet port) maintains that file with
> up-to-date notes on `ext-plugins.cmake`, registered external plugins, and any
> known cmake issues affecting the shared simulator build.

The firmware simulator runs the actual MetaModule firmware natively on macOS using SDL2
for graphics and audio. **Confirmed working** on this machine (Apple Silicon, SDL2 2.32.10
via `/opt/homebrew`).

### Location
```
~/Development/metamodule/simulator/
```

### Running the simulator
```bash
cd ~/Development/metamodule/simulator
./build/simulator --zoom 250 --sdcarddir ~/Development/mm-sdcard --audioout 2
```
`--zoom 250` is recommended on this machine (Retina). `--audioout 2` selects MacBook Pro Speakers.
Audio devices on this machine:
```
0: BlackHole 16ch
1: BlackHole 64ch
2: MacBook Pro Speakers  ← use this
3: Microsoft Teams Audio
4: Aggregate Device
```

### Testing a plugin in the simulator
This is the fast iteration loop — much quicker than flash-to-hardware.

**Step 1: Register the plugin with the simulator** (one-time setup per plugin)

Edit `~/Development/metamodule/simulator/ext-plugins.cmake` and add two lines
pointing at the Schlappi plugin build output. See `docs/simulator-ext-plugins.md`
in the firmware repo for exact syntax.

**Step 2: Minor plugin.cpp change**

Two lines need to change in `plugin.cpp` to register with the simulator's module
factory rather than the hardware one. Wrap with `#ifdef METAMODULE_BUILTIN` so
the same source compiles for VCVRack, simulator, and hardware:
```cpp
#ifdef METAMODULE_BUILTIN
  // simulator/hardware registration
#else
  // VCVRack registration
#endif
```

**Step 3: Build simulator with plugin**
```bash
cd ~/Development/metamodule/simulator
cmake --fresh -B build -G Ninja
cmake --build build
```

**Step 4: Create a local SD card directory**
```bash
mkdir -p ~/Development/mm-sdcard/metamodule-plugins
cp ~/Development/Schlappi-vcv/metamodule/metamodule-plugins/SchlappiEngineering.mmplugin \
   ~/Development/mm-sdcard/metamodule-plugins/
```

**Step 5: Run with your test SD card**
```bash
./build/simulator --zoom 250 --sdcarddir ~/Development/mm-sdcard --audioout 2
```

### Simulator options reference
| Flag | Default | Purpose |
|------|---------|---------|
| `--zoom` | 100 | Display zoom % — use 200 on Retina |
| `--sdcarddir` | `patches/` | Local dir simulating SD card root |
| `--flashdir` | `../patches/default/` | Local dir simulating NOR flash |
| `--assets` | `../firmware/build/assets.uimg` | Firmware assets file |
| `--audioout` | 0 | SDL audio device ID |
| `--fullScaleVolts` | 5 | Peak volts = full scale audio |

### SDL2
Installed via Apple Silicon Homebrew: `/opt/homebrew/Cellar/sdl2/2.32.10`
If cmake can't find SDL2 during simulator build, force it with:
```bash
-DSDL2_DIR=/opt/homebrew/lib/cmake/SDL2
```

---

## Deployment (hardware)

Copy the built `.mmplugin` file to a USB drive or microSD card:
```bash
cp metamodule/metamodule-plugins/SchlappiEngineering.mmplugin /Volumes/<drive>/metamodule-plugins/
```
The `metamodule-plugins/` directory must be at the **root level** of the drive.
Insert into MetaModule — it will appear in the module browser.

---

## References

- MetaModule Plugin SDK: https://github.com/4ms/metamodule-plugin-sdk
- MetaModule Plugin Examples: https://github.com/4ms/metamodule-plugin-examples
- MetaModule Rack Interface (API docs): https://github.com/4ms/metamodule-rack-interface
- MetaModule Firmware + Simulator: https://github.com/4ms/metamodule
- Simulator docs: `~/Development/metamodule/docs/simulator-*.md`
- ARM GNU Toolchain v12 download: https://developer.arm.com/downloads/-/arm-gnu-toolchain-downloads

