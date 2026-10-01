# EXP01 - Minimal ZMK shield for the ADS1220 TrackPoint, built on GitHub Actions

## Summary
Stand up a new repo holding a minimal nice!nano ZMK shield for the badjeff ADS1220
driver (wiring per README §2, 2.2 kΩ divider), with USB logging + Zephyr shell +
debug logs, and get it green on GitHub Actions.

## Hypothesis
Stock `zmkfirmware/zmk@main` + `badjeff/ads1220-zephyr-module@main` compiles and
links for `nice_nano@2.0.0` with our shield - all three drivers enabled, **no
`cs-gpios`** (CS tied to GND, design D6), DRDY on P1.06 - without patching either
upstream repo. Falsified if the build fails on the module's ZMK/Zephyr API
assumptions, on the CS-less SPI setup, or on board-identifier resolution.

## Methodology & blast radius
- Method:
  1. This repo **is** the ZMK module root (user decision, 2026-10-01): the
     manifest (`config/west.yml`), module marker (`zephyr/module.yml` +
     `board_root: .`), build matrix (`build.yaml`) and the shield
     (`boards/shields/ads1220_tpoint/`) live at the root of `ADS1220/`, alongside
     the design of record. A *new* GitHub repo is created and this repo is pushed
     to it (it currently has no remote).
  2. Shield `ads1220_tpoint` under `boards/shields/`: SPI2 pinctrl
     (SCK P0.08 / MOSI P0.17 / MISO P0.20), `ti,ads1220` ch0 (AIN0-AIN2) + ch1
     (AIN1-AIN2), gain 64, `ADC_REF_EXTERNAL0`, `zephyr,current-source-pin = [05 00]`,
     `ti,ads1220-gpio`, `analog-axis-hires` with `in-calib-cycle`, `zmk,input-listener`
     → `&anin0`, `CONFIG_ZMK_POINTING=y`, 1x1 dummy kscan (pro_micro 19/21 = P0.02/P0.31).
  3. `config/west.yml`: add `badjeff` remote + `ads1220-zephyr-module@main`.
     `build.yaml`: `nice_nano@2.0.0` + `ads1220_tpoint` + `snippet: zmk-usb-logging`.
  4. Push to a new public GitHub repo; `gh run watch`; on failure
     `gh run view --log-failed`; iterate until green; `gh run download` the `.uf2`.
  5. Then (bench): flash, watch the USB CDC-ACM logs, confirm driver init, IDAC,
     calibration `avg` per channel, and pointer motion.
- May touch: this repo on branch `EXP01` (the ZMK module files at the root:
  `build.yaml`, `.github/workflows/build.yml`, `config/`, `zephyr/module.yml`,
  `boards/shields/ads1220_tpoint/`; plus `experiments/EXP01/README.md` and
  `experiments-overview.md`); the new GitHub repo.
- Off-limits: README §1-§9 (design of record), `layout/`, `ads1220-tpoint/`, `refs/`.
  Any wiring change is a *finding* here, not an edit there.

## Open questions (known unknowns)
- [x] **nice!nano revision / board string** — chosen: `nice_nano@2.0.0`; fallback
  `nice_nano@2.0.0//zmk`, then `nice_nano`.
- [x] **ZMK revision** — chosen: `zmkfirmware/zmk@main` (its `zephyr` export is
  `v4.1.0+zmk-fixes`, which has `ADC_CONFIGURABLE_EXCITATION_CURRENT_SOURCE_PIN`
  that the module selects; verified `gh search code`). Fallback `v0.3`.
- [x] **Repo name / visibility / path** — chosen: new **public** GitHub repo
  `Magid-William/ADS1220`, with the module at the root of the existing local repo
  `D:\DIY\trackpoint\ADS1220`. (GitHub account: `Magid-William`.)
- [x] **CS (D6)** — chosen: follow the frozen design, CS→GND, no `cs-gpios`. This
  experiment is the vehicle that validates D6. Fallback if the driver cannot init:
  one wire CS→P0.06 + `cs-gpios = <&gpio0 6 (...) >` (the module's own example pin).
- [x] **DRDY** — chosen: include `drdy-gpios` on P1.06 (design D10; datasheet says
  DRDY is actively driven even with CS high). Fallback: drop it → driver's timed polling.
- [x] **`idac-ua`** — chosen: 500 µA (design D3). With the 2.2 kΩ divider the rule
  becomes 500 µA for measured `R_ab` ≳ 6 kΩ (see divider note below).
- [x] **`skip-change-comparator`** — chosen: off (README §5). Raw values are still
  observable: the driver logs `raw` on change and the per-channel calibration `avg`
  at boot (input_analog_axis_hires.c:328).
- [x] **Custom `tpoint` shell command** (`analog_axis_hires_set_raw_data_cb`) —
  chosen: defer to EXP02, keep the shield minimal.
- [x] **Divider = 2.2 kΩ, not 2.4 kΩ** (user deviation from README §2 and badjeff's
  `example-tpoint_idac.dtsi`, both 2400 Ω) — chosen **Option A**: one 2.2 kΩ per leg
  (R1 = R2 = 2.2 kΩ), bridging the unused second position (`D10-D13` for the R2 leg,
  `C16-E16` for the R1 leg). Divider load 4.4 kΩ (was 4.8 kΩ), AIN2 source impedance
  1.1 kΩ (was 1.2 kΩ) → no worse. Ratiometric, so gain/scale/`in-min`/`in-max` unchanged.
- [ ] **README value update** (unanswered → assumption) — assumed: fold the 2.2 kΩ
  documentation change into EXP01's *conclusion* (README §2 parts + R1/R2 rows, §4
  divider bullet, §5 `idac-ua`, §7.2 tune table; `layout/board.md` only via
  `python layout/gen.py`, never hand-edited). No README edit during the run.

### Divider note (Option A) - affects `idac-ua` only
`V(a) = I_IDAC × (R_ab ∥ 4.4 k)`, need 0.75 V ≤ V(a) ≤ 2.4 V. Only the high-`R_ab`
rows of README §7.2 shift: at 10 kΩ, 250 µA now gives 0.76 V (marginal) → use 500 µA
(1.53 V). Practical rule: **500 µA for `R_ab` ≳ 6 kΩ**.

Pre-flight check before power-up (likely silent failure mode of Option A): continuity
`R1a + bridge = 2.2 kΩ` and `R2a + bridge = 2.2 kΩ`. An *empty* (unbridged) second
position leaves the leg open → AIN2 floats → no mid-bias → both channels rail.

## Conclusion (findings)

**Goal met: a brand-new repo holds the shield and builds green in GitHub Actions,
unpatched.** Three consecutive successful runs (cold ~4.5 min) at
<https://github.com/Magid-William/ADS1220/actions>; artifact
`ads1220_tpoint-nice_nano@2.0.0-zmk.uf2` (240 KiB).

### Resolved

| item | outcome |
|---|---|
| zmk `main` + `ads1220-zephyr-module` `main` builds for `nice_nano@2.0.0` | **Hypothesis confirmed.** No patch to either upstream. ZMK's `zephyr` export `v4.1.0+zmk-fixes` has the `ADC_CONFIGURABLE_EXCITATION_CURRENT_SOURCE_PIN` the module selects. |
| **D6** — CS tied to GND, no `cs-gpios` | **Confirmed at the build/DT level.** The resolved devicetree has **zero** `cs-gpios`, and `spi_nrfx_spim.c`'s `configure()` never touches `ss_pin`, so there is no CS toggling at all — exactly what a hard-wired CS needs. That the SPI *read* completes is still a bench question. |
| Q9 — 2.2 kΩ divider (Option A) | No firmware change required (ratiometric). Recorded in the DTS comment and the shield README. |
| `CONFIG_INPUT_ANALOG_AXIS_HIRES_SETTINGS` | **Inert**: the module's symbol `depends on SETTINGS`, which is `n`, so `=y` only produced a Kconfig warning. Removed. README §5 lists it. |
| Board string / revision pinning | `nice_nano@2.0.0` resolved with no `//zmk` qualifier needed. |

### Flash

`ads1220_tpoint-nice_nano@2.0.0-zmk.uf2` was written to the nice!nano's UF2
bootloader (volume `NICENANO`, bootloader 0.6.0, nRF52840, S140 6.1.1). The drive
disappeared immediately after the copy = the bootloader accepted it and started
flashing. The software path in `flash-nicenano.ps1` was not needed; a direct copy
to the mounted drive was enough.

### Not verified — carried forward

- **No runtime logs were captured.** ADS1220 init / `power-up` / DRDY detection and
  the per-channel calibration `avg` were never observed. The expected
  `ch0 ≈ 131622`, `ch1 ≈ -21` remains a *prediction*, not a measurement.
- Pointer motion through `zmk,input-listener` + `CONFIG_ZMK_POINTING` unverified.
- The Option-A pre-flight continuity check (R1a+bridge = R2a+bridge = 2.2 kΩ) was
  not performed.
- `ads1220_tpoint` is a **unibody** shield: it has no split central/peripheral
  role. "Right side as central" is met only in the sense that the flashed device is
  a standalone central-class keyboard. An actual split right-half-as-central with
  the ADS1220 attached is a different shield.

### Module-side facts worth carrying

Builds against ZMK main but is not warning-clean: `gpio_ads1220.c` calls
`ads1220_device_{resume,suspend}_by_reg` with no prototype (defined in
`adc_ads1220.c`, never declared in `ads1220.h`), and `adc_ads1220.c` has a
`-Wmaybe-uninitialized` on `gain`. The int/uint16_t argument mismatch is harmless
under AAPCS today, but a compiler that treats implicit declarations as errors
would break the build.

### README (design of record) follow-ups

- §2 parts list + R1/R2 rows, §4 divider bullet, §5 `idac-ua`, §7.2 tune table:
  2.2 kΩ Option A (divider load 4.4 kΩ, AIN2 1.1 kΩ).
- §5: drop the inert `CONFIG_INPUT_ANALOG_AXIS_HIRES_SETTINGS=y`, or add
  `CONFIG_SETTINGS=y` if persisted calibration is wanted.

## Learnings
- ZMK module at the **repo root**: the reusable `build-user-config.yml` detects
  `zephyr/module.yml`, then builds in a temp dir with `config/` copied there and
  adds the workspace via `-DZMK_EXTRA_MODULES`. `config/`, `zephyr/`, `build.yaml`
  and `boards/shields/<x>/` can sit at the root alongside unrelated files.
- Get a green build from an existing repo:
  ```
  gh repo create <owner>/<name> --public
  git remote add origin https://github.com/<owner>/<name>.git
  git push -u origin master      # no .github/ on the base commit -> no run
  git push -u origin EXP01       # triggers the build
  gh run watch <id> --repo <owner>/<name> --exit-status
  gh run download <id> --repo <owner>/<name> -D <dir>
  ```
- `gh auth status` can print a stale display name; `gh api user --jq .login` is
  authoritative.
- **`CONFIG_INPUT_ANALOG_AXIS_HIRES_SETTINGS` needs `CONFIG_SETTINGS=y`** — without
  it Kconfig warns "assigned 'y' but got 'n'" and the line does nothing.
- **Flashing a nice!nano from Windows**: the bootloader's UF2 drive is the sure
  path — copy the `.uf2` to the mounted `NICENANO` volume; the drive vanishing
  means it was accepted. No COM port needed. The shell route (`devmem 0x4000051C
  32 0x57` + `kernel reboot cold`) only works if the running firmware exposes a
  Zephyr shell; this board enumerated on **COM22**, not the script's default COM8
  (COM8 was a stale PnP entry — check `Get-PnpDevice -Class Ports -Status OK`).
- `gh search code "<symbol>" --repo <owner>/<repo>` to confirm an upstream
  Kconfig/API exists before pinning a ZMK/Zephyr revision.

