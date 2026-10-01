# EXP08 - Read-path root cause: is the (H,H,L) duplication the SPI transfer?

## Summary
EXP07 showed every 24-bit sample reads as (H,H,L) (hi==mid 100%), so every earlier analog verdict is unsound. EXP08 finds why the read duplicates a byte and lands the smallest fix - devicetree or driver - that makes the read trustworthy.

## Hypothesis
The byte duplication is created by the SPI read transaction, not by the ADS1220
conversion. Two predictions:
1. Instrumenting the raw received bytes shows `rx[0] == rx[1]` at the buffer,
   before `sys_get_be24()`.
2. Once the read is corrected, `hi==mid` holds for <= 1% of samples and the
   hands-off neutral sits near the driver's documented values
   (x ~ 131622, y ~ -21) instead of ~ -4e6.

Falsified if the raw bytes are already distinct (the fault is downstream, in
`sys_get_be24()` or the axis path), or if no SPI configuration tested removes
the duplication - then it is MISO integrity / CS timing in hardware and the fix
is not firmware.

## Methodology & blast radius
- Method:
  1. Branch `EXP08` off `EXP07`; keep the pinned 8 ms poll; do the read test on
     its own before changing the analog side.
  2. Probe the transfer without touching the upstream driver:
     - `CONFIG_SPI_SHELL`: clock `RDATA` by hand at SPI mode 0 / 1 / 3 and
       100 kHz / 1 MHz / 4 MHz; hexdump the received bytes.
     - Add a `tpoint raw` helper to `exp02_logging.c` (our file) that re-reads
       the ADC with a chosen mode/length and prints every received byte.
  3. Compare against the driver's own read path (enable the commented
     `LOG_HEXDUMP_DBG(rx_buf, 3)` - in the fork, never in `refs/`).
  4. Identify the knob that removes the duplication: SPI mode/phase, the
     `RDATA` read length (3 vs 4 bytes) / DRDY handshake, or
     `spi-max-frequency`. Test fast vs slow clock with the mode held, to
     separate mode from clock.
  5. Land the fix, including in `ads1220-zephyr-module` if it is driver-side:
     point `config/west.yml` at a **fork** pinned to an `exp08-*` branch (small
     mode/length change), or **vendor** the changed driver in-repo (larger
     change, or one that pulls in the input/GPIO drivers). `refs/` stays a
     read-only reference; the change lands on the fork or the in-repo copy.
  6. Re-run 10 s hands-off + a circle capture at the design gain (64), then run
     `experiments/EXP04/analyze_xy.py` and the `hi==mid` smoke test.
- May touch: `config/west.yml` (module url/revision) and the fork repo, or
  in-repo `drivers/`; `boards/shields/ads1220_tpoint/ads1220_tpoint.dtsi`
  (+ `.conf` / `.overlay`), `boards/shields/ads1220_tpoint/README.md`;
  `exp02_logging.c`, `Kconfig`, `CMakeLists.txt`; `experiments/EXP08/*`;
  `experiments-overview.md`; branch `EXP08`.
- Off-limits: `README.md` §1-§9 (design of record), `layout/`,
  `ads1220-tpoint/`, **`refs/` itself** (the fork is not a patch to it),
  physical rewiring (firmware-first; a hardware MISO/CS fix is its own
  experiment).

## Open questions (known unknowns)
- [ ] How to land a driver change - fork pinned in `west.yml` vs vendored
  in-repo? — proposed default: fork if the change is small (mode/length),
  vendor if it grows or pulls in the input/GPIO drivers.
- [ ] Read probe - SPI shell only, or add `tpoint raw`? — proposed default: add
  `tpoint raw` (repeatable and scriptable) and cross-check with the SPI shell.
- [ ] Re-test gain - 1 or the design value 64? — proposed default: 64; EXP07
  says the "railed" verdicts were read off malformed samples and the design
  value is 64. Fall back to 1 only if it rails.
- [ ] Meter available? — proposed default: no; meter-free as in EXP07.
- [ ] Operator for the final circle re-capture? — proposed default: yes for the
  circle; the hands-off steps are operator-free.

Success criterion: `hi==mid <= 1%`, neutral near 130k / -21, and a circle
capture where x and y are no longer 0.97-correlated.

## Conclusion (findings)
_Pending._

## Learnings
- **`tpoint raw [mode] [n] [khz] [cmd] [split]` is the read-path probe.** It
  re-reads the ADC in its own SPI transaction and hexdumps every byte, so it
  bypasses `sys_get_be24()` entirely — run it before believing any statistic
  computed from logged values. (`experiments/EXP08/`.)
- **The duplication is in the SPI receive buffer, not downstream.** At the
  driver's exact setup (mode 1, 3 bytes, 1 MHz) `rx[0] == rx[1]` in 40/40, so
  `be24` = `(b0<<16)|(b0<<8)|b1` — the low byte `b2` is never read at all.
- **Mechanism: the ADS1220 is already streaming when the command is clocked in.**
  A 3-byte transfer is one byte short (8 clocks of command + only 16 left for
  data), so `rx = [b0, b0, b1]` and a 4-byte read gives `[b0, b0, b1, b2]`.
  Datasheet: *"the device starts to output the requested data on DOUT/DRDY at
  the first SCLK rising edge after the command byte."* Fix: read 4 bytes and use
  **bytes 1, 2, 3** (`rx[0]` is the ambiguous pre-command byte — ignore it).
  Verified: `hi==mid` falls from 40/40 to **0/40**.
- **`RREG` is the operator-free ground truth for the SPI phase.** At mode 1 the
  register byte (`rx[1]`) is stable across reads (`0x84`, `0xA0`, `0x10/0x30`)
  while `rx[0]` carries live conversion data. So **mode 1 (CPOL=0/CPHA=1) is
  correct** and the fault is the *read length*, not the clock phase. Modes 0/2/3
  only looked promising because garbage also tends to have `hi != mid`.
- **Bootloader entry needs a quiet console.** `devmem 0x4000051C 32 0x57` +
  `kernel reboot cold` does work, but only with the `XY`/HID log flood off.
  Always verify first: `devmem 0x4000051C 32` must answer `Read value 0x57`
  *before* the reboot is sent.
- **`gh run download` fails with "file exists" and silently leaves the OLD UF2
  in place** — `Remove-Item -Recurse artifacts\EXP0N` first, or you flash the
  previous build and debug the wrong firmware.
