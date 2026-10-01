# EXP03 - ADS1220 no-read root cause: CS-to-GPIO rework

## Summary
The ADS1220 never returns a valid register read (EXP02: `0x1C != 0xFF`; after
pulling the C1/C2 decoupling caps: `0x1C != 0xAF`), so channel setup aborts and
no sample is ever taken. Prove the chip is alive and powered, then remove the
one deviation from every working module example - CS tied to GND - and drive CS
from P0.06.

## Hypothesis
The ADS1220 is powered and alive; the readback failure is the **CS-tied-low SPI
framing (D6)**. Driving CS from P0.06 with
`cs-gpios = <&gpio0 6 (GPIO_ACTIVE_LOW | GPIO_PULL_UP)>` restores a valid
`CONFIG0` readback (`0x1C`) and the channel sets up. Falsified if, with CS
properly framed **and** power/continuity verified, `CONFIG0` still mismatches -
which points at the chip/supply/pin path instead.

Caveat (kept honest): a framing-only fault should return a plausible-but-wrong
byte, whereas `0xFF`/`0xAF` is floating-input behaviour. However, with CS tied
low the device only drives DOUT while it is actually outputting register data,
so a mis-framed RREG also leaves DOUT floating. The two hypotheses are still
both live; the isolated `spi`-shell probe below separates them.

Why the `spi` shell is decisive and safe: the `analog_axis_hires` thread
`return`s and exits on the first channel-setup failure
(`input_analog_axis_hires.c:520`), so the bus is idle afterwards (the boot log
shows the error exactly once). Each shell transaction is also separated by many
seconds - far longer than the ADS1220 SPI timeout - so every shell frame has a
clean boundary even with CS tied low. That makes the shell the closest thing to
proper CS framing without the rework.

## Methodology & blast radius
- Method:
  1. Refit **C1 (AVDD-AGND)** and **C2 (DVDD-DGND)**; re-seat the socketed module.
  2. Meter, unpowered - continuity of SCLK P0.08->pin 1, MOSI P0.17->pin 16,
     MISO P0.20->pin 15, DRDY P1.06->pin 14, CS pin 2->GND, CLK pin 3->GND.
  3. Meter, powered at the *chip* pins - AVDD/DVDD rails, supply current, and
     the breakout's regulator question (README §8).
  4. **Decisive isolated probe** (bus idle after the boot failure):
     `spi conf adc_ads1220 1000000 h` then `spi transceive 06` (RESET), wait,
     `spi transceive 20 00` (RREG CONFIG0), wait, `spi transceive 40 1C`
     (WREG CONFIG0=0x1C), wait, `spi transceive 20 00`. A clean `0x1C` readback
     proves the chip is alive and pins are good -> framing is the fault. A
     floating `0xFF`/`0xAF` -> the chip never drove DOUT -> electrical fault.
  5. **D6 rework** (the change under test): cut CS off GND, wire ADS1220 CS
     (pin 2) -> nice!nano D1 / P0.06; add
     `cs-gpios = <&gpio0 6 (GPIO_ACTIVE_LOW | GPIO_PULL_UP)>;` to `&spi2` and
     drop the "CS tied to GND" comment in `ads1220_tpoint.dtsi`.
  6. Build (GitHub Actions) + flash + `capture-serial.ps1 -Reset`. Expect
     `Channel 0 setup done` -> `All channels setup complete` -> calibration ->
     `tpoint sample`.
  7. If it still fails: record the new readback byte and fall back to the
     electrical fault tree (steps 2-4) rather than more firmware.
- May touch: `boards/shields/ads1220_tpoint/ads1220_tpoint.dtsi` (cs-gpios),
  `boards/shields/ads1220_tpoint/README.md` (wiring table D6),
  `experiments/EXP03/README.md`, `experiments-overview.md`, branch `EXP03`, a
  new capture log. **Physical rework:** CS pin 2 -> P0.06 (D1).
- Off-limits: `README.md` §1-§9 (design of record - §8's D6 item is updated only
  after the user declares success), `layout/`, `ads1220-tpoint/`, `refs/`. The
  CS-tied-low build stays reproducible on the `EXP02` branch.

## Open questions (known unknowns)
- [x] Bench gear - **meter only** (user). Decisive instruments: DC rail/current
  checks + the isolated `spi`-shell register probe. A scope capture is deferred.
- [x] Hardware - **breakout module**; no VIN -> plain breakout with no regulator
  (README §8 resolved to *none*).
- [x] Caps - deliberately removed; **refit C1/C2 before powered tests**.
- [x] D6 rework - **included** in this experiment (cs-gpios from P0.06).

## Bench log (running)
| # | Measurement | Reading | Note |
|---|---|---|---|
| 1 | AVDD - AGND (DC V) | 3.3 V | chip powered |
| 2 | DVDD - DGND (DC V) | 3.3 V | chip powered |
| 3 | VIN | absent | plain breakout, no LDO |
| 4 | `device list` | `spi@40023000` (label `spi2`), `adc_ads1220@0` | SPI controller name is `spi@40023000` |
| 5 | `spi transceive 06` (RESET) | RX `fd` | |
| 6 | `spi transceive 23 00 00 00 00` | RX `a2 3b ff ff ff` | not `00 00 00 00` (reset default) |
| 7 | `spi transceive 40 1C` (WREG CONFIG0=1C) | RX `ff fc` | |
| 8 | `spi transceive 23 00 00 00 00` | RX `a2 3b fc a2 3b` | write did NOT take |
| 9 | same read repeated (mode 0 / `h`) | `ff ff ff ff ff` / `fd 2d f7 ff ff` | **varies run to run -> floating, not chip data** |
| 10 | `gpio get gpio1 6` (DRDY) | `0` | **wrong pin** - DRDY is wired to P0.06, so this read a floating pin |
| 11 | DRDY after POWERDOWN (`02`) and START (`08`) | `0` | read of the wrong (floating) pin - meaningless |
| 12 | Continuity DRDY (14) -> P0.06 | beeps | actual wiring: DRDY on P0.06 (nice!nano D1), not P1.06 |
| 13 | Continuity DRDY (14) -> GND | open | DRDY not shorted |
| 14 | Continuity MISO (15) -> P0.20 | beeps | MISO wire is good |
| 15 | Continuity MOSI (16) -> P0.17 | beeps | |
| 16 | Continuity SCLK (1) -> P0.08 | beeps | |
| 17 | Continuity CS (2) -> GND, CLK (3) -> GND | **not measured** | current leading suspect |
| 17a | CS moved to P0.10, `cs-gpios`, GPIO_ACTIVE_LOW | `config0 0x1C != 0xFF` | chip deselected: CS not driven low |
| 17b | `+ CONFIG_NFCT_PINS_AS_GPIOS=y` (P0.10 is an NFC pin) | still `0xFF` | not the blocker (nice!nano likely already sets it) |
| 18 | CS wired correctly to P0.10 + `cs-gpios` | setup succeeds, **0 mismatches**, calib runs, samples stream | **root cause fixed** |
| 19 | post-fix calibration / live | ch0 & ch1 `avg:-8355840` (constant), dt_range 1310600, deadzone 0 | analog front-end railed - a new (analog) problem |
| 18 | Boot with `drdy-gpios = <&gpio0 6>` (P0.06) | `config0 mismatch! 0x1C != 0x00` | readback now the ADS1220 reset default, not floating |
| 19 | Poll loop after failure | ~127 `mismatch`/s, channel retried every 8 ms | thread keeps polling; log flood is expected |
| 20 | ch0 write `0x1C` -> read `0x00`; ch1 write `0x3C` -> read `0x1C` | one-transaction lag | write lands, readback returns previous value -> framing |

### Root cause (provisional)
**D6 (CS tied to GND) breaks the register handshake.** With CS low, the ADS1220
commits a WREG only at a frame boundary - a CS edge or the ~55 ms SPI timeout.
The driver writes CONFIGn and reads it back microseconds later, so the readback
always returns the *previous* value (measured: ch0 write `0x1C` read `0x00`;
ch1 write `0x3C` read `0x1C`; CONFIG2 read `0x00`) and `channel_setup` returns
`-EIO` forever. The same applies to the `gpio_ads1220` IDAC writes. The chip,
MISO and the wiring are all good: spaced shell frames (gap >> timeout) read back
correctly. Every working module example delimits frames with CS edges
(`cs-gpios = <&gpio0 6 ...>`). Fix options: CS on a GPIO (stock driver), or a
driver patch that waits > timeout between a write and its readback.

### Correction
The bullet below ("DRDY low with a pull-up configured = ...") is **wrong**: DRDY
is wired to P0.06, so `gpio get gpio1 6` was reading an unconnected, floating
P1.06. There is currently **no evidence the chip drives DRDY**. Note also that
since DRDY is really on P0.06, the earlier `spi conf ... h` transactions were
fine and the MISO crosstalk stands on its own.

### Raw probe reading
- `spi conf adc_ads1220 ...` (the shield README's example) is **wrong**: it binds
  the ADC node, so `spi transceive` lands in `ads1220_channel_setup` (logs
  `Invalid given gain: 0` + a bogus `config0 mismatch`, returns `-EIO`). Use the
  SPI controller name `spi@40023000`.
- Reads are **not repeatable** (`a2 3b ff ff ff` then `a2 3b fc a2 3b` then
  `fd 2d f7 ff ff`), so the repeated `a2 3b` was coincidence: MISO carries
  crosstalk, the ADS1220 is not driving DOUT.
- Non-read commands (`06`/`02`/`08`) return `ff`/`fc`; reads return varying bytes.
  Consistent with a floating MISO being excited by MOSI/SCLK.
- DRDY miswired: the chip's DRDY (pin 14) is on nice!nano **P0.06**, but the
  shield expects **P1.06** (`drdy-gpios`). Corrected in `ads1220_tpoint.dtsi`
  (`<&gpio0 6 ...>`) and the shield README; the parent README §2 design of record
  still says P1.06 and is left alone until the user declares success.
- The single cause that explains *all* of it is a broken/undriven **DOUT** path:
  with CS tied low the ADS1220 drives DOUT/DRDY *always* (TI E2E 571924), so a
  floating MISO means the chip is not driving it - either the chip is not running
  or the pin 15 -> P0.20 wire is open. Still to be separated from CS-tied-low
  framing by the continuity + loopback checks.

### Datasheet / TI E2E facts
- All config registers reset to `00h` (SBAS501 8.6.1.1-8.6.1.4).
- SPI mode 1 (CPOL=0, CPHA=1) - matches the driver's `SPI_MODE_CPHA` and the
  shell's `h` option.
- The SPI timeout resets the ADS1220's internal SCLK counter, functionally like
  toggling CS, so spaced CS-tied-low frames are legal (TI E2E 765504).
- **With CS tied low, DOUT/DRDY is always driven** - a floating MISO is a fault,
  not an idle state (TI E2E 571924).
- In single-shot mode (the reset default) a WREG also starts a conversion
  (SBAS501 8.4.2.1); START/SYNC does not force DOUT/DRDY high.

## Conclusion (findings)
_Pending._

## Learnings
- **A failed channel setup does NOT kill the poll thread.** (Corrects an earlier
  claim in this file.) `input_analog_axis_hires.c:228` calls
  `adc_channel_setup_dt` inside the per-poll read path and only `return`s from
  that one read on failure; the poll loop keeps firing. At the 8 ms active period
  this is ~127 failures/s, which is what floods the log after a failure. EXP02's
  "shell collides with the poller" caveat therefore always applies.
- **The ADS1220 SPI timeout is ~55 ms.** 14000 x tMOD, tMOD = 1/256 kHz (internal
  osc) = 3.906 us -> **54.7 ms**. With CS tied low, a WREG is only committed at a
  frame boundary: a CS rising edge *or* the SPI timeout. The driver writes then
  immediately reads back (microseconds apart), so it always reads the *previous*
  value. This is the root cause (see Conclusion).
- **ADS1220 command bytes** (`adc_ads1220.c`): RESET `0x06`, START/SYNC `0x08`,
  POWERDOWN `0x02`, RDATA `0x10`, RREG `0x20 | (addr<<2)`, WREG `0x40 | (addr<<2)`;
  RREG/WREG send 2 command bytes, so `spi transceive 20 00` reads CONFIG0 and
  `spi transceive 40 1C` writes CONFIG0 = 0x1C.
- **`spi conf` needs the SPI controller name, not the ADC node.** `device list`
  shows `spi@40023000` (label `spi2`) and `adc_ads1220@0`. `spi conf adc_ads1220`
  binds the ADC, and `spi transceive` then calls into `ads1220_channel_setup`
  (`Invalid given gain`, bogus `config0 mismatch`, `-EIO`). Always
  `spi conf spi@40023000 1000000 h`. (The shield README's bring-up example is wrong.)
- **Zephyr `spi` shell option letters** (`spi_shell.c`): `o`=CPOL, `h`=CPHA,
  `l`=LSB, `T`=TI frame - a *sequence* of letters (e.g. `oh` = mode 3). `c` is
  not a valid setting. `h` alone = mode 1 = what the ADS1220 needs.
- **`spi cs` needs the SPI device as a subcommand** and takes the pin only
  (`spi cs spi@40023000 <pin> [flags]`); `spi cs spi@40023000 gpio0 10` fails with
  "invalid pin number: gpio0". Without a CS the shell's `transceive` on the
  controller reads `0xFF` once the ADS1220 CS is no longer tied low.
- **nRF52840 P0.09/P0.10 are the NFC antenna pins (NFC1/NFC2).** They are not
  GPIO unless `CONFIG_NFCT_PINS_AS_GPIOS=y` (nice!nano/ZMK likely already sets
  it, since D10/D16 are P0.09/P0.10). Worth knowing before choosing a CS pin.
- **The result of the fix:** with `cs-gpios = <&gpio0 10 (GPIO_ACTIVE_LOW |
  GPIO_PULL_UP)>` both channels set up, calibration runs and samples stream with
  zero register mismatches. CS tied to GND is the wrong answer for this driver.
