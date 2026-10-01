# EXP03 - ADS1220 no-read root cause: CS must not be tied to GND

## Summary
The ADS1220 never returned a valid register read (EXP02: `config0 mismatch
0x1C != 0xFF`; after pulling the decoupling caps: `0x1C != 0xAF`), so channel
setup aborted and no sample was ever taken. Root cause: **D6 - CS tied to GND -
is incompatible with the `badjeff/ads1220-zephyr-module` driver.** Driving CS
from a GPIO fixes it: both channels now set up, calibrate and stream samples.

## Hypothesis
The ADS1220 is powered and alive; the readback failure is the **CS-tied-low
framing (D6)**. Delimiting frames with a CS edge (`cs-gpios`) restores a valid
`CONFIG0` readback and channel setup. Falsified if, with CS framed and
power/continuity verified, `CONFIG0` still mismatches.

Result: **confirmed.** CS on P0.10 (`cs-gpios`) gives `Channel 0 setup done` ->
`All channels setup complete` with zero mismatches.

## Methodology & blast radius
- Method (as run):
  1. Meter the rails at the chip pins (AVDD/DVDD) and the digital lines.
  2. Isolate the bus: `device list`, then raw `spi`-shell transfers on the
     controller `spi@40023000` (mode 1 = `h`), spaced seconds apart.
  3. Establish whether the failure is electrical or framing by comparing
     spaced frames (>> the ~55 ms SPI timeout) with the driver's immediate
     write-then-readback.
  4. Move CS off GND onto a GPIO and add `cs-gpios` to `&spi2`; rebuild via
     GitHub Actions, flash, `capture-serial.ps1 -Reset`.
- May touch (actual): `boards/shields/ads1220_tpoint/ads1220_tpoint.dtsi`
  (`cs-gpios`, `drdy-gpios`), `ads1220_tpoint.conf`
  (`CONFIG_NFCT_PINS_AS_GPIOS`), `ads1220_tpoint/README.md`,
  `experiments/EXP03/README.md`, `experiments-overview.md`, branch `EXP03`,
  capture logs. **Physical:** CS (pin 2) moved from GND to nice!nano P0.10;
  DRDY (pin 14) is on P0.06.
- Off-limits: `README.md` §1-§9 (design of record), `layout/`,
  `ads1220-tpoint/`, `refs/` (no upstream patch - so a driver-side fix was not
  an option).

## Open questions (known unknowns)
- [x] Bench gear - meter only. (Enough: the shell probes plus continuity.)
- [x] Hardware - plain breakout, **no regulator** (no VIN) -> README §8 item
  "does it carry its own regulator?" = **no**.
- [x] Caps - refit C1/C2 before powered tests.
- [x] CS pin - user chose **P0.10** (not the P0.06 the module examples use).

## Bench log (condensed)
| # | Check | Result | Note |
|---|---|---|---|
| 1 | AVDD-AGND / DVDD-DGND | 3.3 V / 3.3 V | chip powered |
| 2 | Continuity SCLK/MOSI/MISO | pin 1->P0.08, 16->P0.17, 15->P0.20 all beep | digital lines good |
| 3 | Continuity DRDY | pin 14 -> **P0.06** (not P1.06 as designed) | `drdy-gpios` corrected |
| 4 | `spi transceive 23 00 00 00 00` (CS on GND) | `a2 3b ff ff ff`, then `fd 2d f7 ff ff` | not repeatable -> MISO floating when not driving |
| 5 | Spaced write/read (CS on GND): `40 1C` ... `23 00 00 00 00` | CONFIG0 = `1C` | chip fine when frames are seconds apart |
| 6 | Gapless `40 1C 23 00 00 00 00` | CONFIG0 = `1C` | within one SCLK burst |
| 7 | Driver boot (CS on GND) | `config0 0x1C != 0x00`; ch1 read `0x1C` after writing `0x3C` | one-transaction lag |
| 8 | CS moved to P0.10 (loose wire) | `0xFF`, no storm | chip not selected |
| 9 | CS on P0.10 wired correctly | **setup done, 0 mismatches, calib runs, samples stream** | **fixed** |
| 10 | Live after fix | `SAMPLE ch0=-8355840` / `ch1=-8355840`, constant | analog front-end railed (separate issue) |

## Conclusion (findings)
**Status: success (user-declared). The no-read fault is found, fixed and verified.**

### Root cause - D6: CS tied to GND
With CS held low the ADS1220 has no frame boundary, so it commits a WREG only at
a CS edge **or after its SPI timeout** (14000 x tMOD; tMOD = 1/256 kHz = 3.9 us
-> **~55 ms**). The driver writes each CONFIGn and reads it straight back
(microseconds later), so the readback always returned the **previous** value:
`ch0 write 0x1C -> read 0x00`, `ch1 write 0x3C -> read 0x1C`, `CONFIG2 -> 0x00`.
`ads1220_setup` therefore returned `-EIO` on every attempt, its `last_config*`
cache never advanced, and no sample was ever produced. The same applied to the
`gpio_ads1220` IDAC writes.

The chip, the SPI lines and the decoupling were never at fault: with frames
spaced beyond the timeout - `spi`-shell transfers are seconds apart - a
write/read round-trip returns the value written, even inside a single gapless
SCLK burst.

### Fix (verified)
CS moved off GND to **P0.10** and `&spi2` given
`cs-gpios = <&gpio0 10 (GPIO_ACTIVE_LOW | GPIO_PULL_UP)>;`, plus
`CONFIG_NFCT_PINS_AS_GPIOS=y` (P0.09/P0.10 are the nRF52840 NFC antenna pins).
Each transaction is now delimited by a CS edge, every WREG commits immediately,
and the driver sets up both channels, auto-calibrates and streams samples with
zero register mismatches.

### Also corrected
- **DRDY is wired to P0.06**, not P1.06; `drdy-gpios` updated to
  `<&gpio0 6 (GPIO_ACTIVE_LOW | GPIO_PULL_UP)>`.
- The shield README's bring-up example was wrong: `spi conf adc_ads1220` binds
  the ADC node and the transfer lands in `ads1220_channel_setup`; use the SPI
  controller name `spi@40023000`.
- The breakout has **no regulator** (no VIN), so the §2 "feed AVDD/DVDD from
  3V3" wiring is correct.

### Handed forward (analog, not firmware)
Both channels now read a **constant `-8355840`** (`0x808000`), identical and
deadzone 0 - the ADC works but the front-end is railed, i.e. no usable
excitation/bias yet (README §4: without a current source the bridge floats and
the reference collapses). Next: measure `R_ab` (unpowered) and, with the driver
polling, `V(a)-V(b)` (>= 0.75 V) and `V(x) ~= V(y) ~= V(a)/2`, and confirm the
`[x][y][a][b]` pad order (README §7).

## Learnings
- **CS tied to GND cannot work with this ADC driver.** The ADS1220 commits a
  WREG only at a CS edge or after its **~55 ms** SPI timeout (14000 x tMOD,
  tMOD = 1/256 kHz). Any driver that writes then immediately reads a register
  back will read the *previous* value. Use `cs-gpios` on a GPIO. Symptom:
  `config0 mismatch` with a one-transaction lag, forever.
- **A failed channel setup does NOT stop the poll loop.** The failure is inside
  the per-poll read path, so the log floods at the poll rate (~127/s at 8 ms).
- **`spi conf` needs the SPI controller name, not the ADC node.** `device list`
  -> `spi@40023000`; `spi conf spi@40023000 1000000 h`. `spi conf adc_ads1220`
  binds the ADC and the transfer calls into `ads1220_channel_setup`.
- **Zephyr `spi` shell modes** are a letter sequence: `o`=CPOL, `h`=CPHA,
  `l`=LSB, `T`=TI (`h` alone = mode 1 = ADS1220). `spi cs <spi-dev> <pin> [flags]`.
- **nRF52840 P0.09/P0.10 are the NFC antenna pins**; they are only GPIO with
  `CONFIG_NFCT_PINS_AS_GPIOS=y` (nice!nano/ZMK likely already sets it).
- **ADS1220 command bytes** (`adc_ads1220.c`): RESET `0x06`, START/SYNC `0x08`,
  POWERDOWN `0x02`, RDATA `0x10`, RREG `0x20 | (addr<<2)`,
  WREG `0x40 | (addr<<2)`.
