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
_Pending._

## Learnings
- `gh search code "<symbol>" --repo <owner>/<repo>` — use to confirm an upstream
  Kconfig/API exists before committing to a ZMK/Zephyr revision.
- ZMK module at the *repo root*: the reusable `build-user-config.yml` detects
  `zephyr/module.yml` and then (a) runs the build in a temp dir with `config/`
  copied there and (b) adds the workspace via `-DZMK_EXTRA_MODULES`. So a repo can
  hold `config/`, `zephyr/`, `build.yaml` and `boards/shields/<x>/` at the root
  alongside unrelated files. Push `master` before `EXP01`: a commit without
  `.github/workflows/` starts no run, which avoids a red build on the base branch.
- `gh auth status` printed the account as `Maged-William` but the real login is
  `Magid-William`; `gh api user --jq .login` is authoritative.
- Board string `nice_nano@2.0.0` resolves fine for `zmkfirmware/zmk@main`
  (its `zephyr` export is `v4.1.0+zmk-fixes`); no `//zmk` qualifier needed.
- **`CONFIG_INPUT_ANALOG_AXIS_HIRES_SETTINGS` is inert unless `CONFIG_SETTINGS=y`**
  (the module's Kconfig has `depends on SETTINGS`). README §5 lists it, but with
  SETTINGS=n Kconfig only warns "assigned 'y' but got 'n'". Dropped from the
  shield .conf for EXP01.
- **D6 confirmed in the resolved devicetree**: the generated DT contains zero
  `cs-gpios`, and `zephyr/drivers/spi/spi_nrfx_spim.c` `configure()` never sets
  `ss_pin`, so SPI runs with no CS toggling — exactly what the hard-wired CS needs.
- Module-side build warnings (upstream, not ours; nothing to patch here):
  `gpio_ads1220.c` calls `ads1220_device_{resume,suspend}_by_reg` without a
  prototype (defined in `adc_ads1220.c`, not in `ads1220.h`), and
  `adc_ads1220.c` has a `-Wmaybe-uninitialized` on `gain`. `Deprecated symbol
  KSCAN is enabled` is ZMK/Zephyr-wide (any `zmk,kscan-gpio-matrix` shield).

