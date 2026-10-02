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
**success** - the read-path question is answered and the fix is landed and
validated. The falsified neutral prediction is itself the useful finding: it
proves the remaining blocker is analog, not firmware.

**The read fault is fixed.** A 4-byte RDATA read (bytes 1..3) in the module fork
`Magid-William/ads1220-zephyr-module` @ `eae64bf` (branch `exp08-read-fix`),
pinned in `config/west.yml`.

| read | `hi==mid` |
|---|---|
| driver before the fix (3 B) | 40/40 |
| raw probe, 4 B, bytes 1..3 | 0/40 |
| raw probe, split CS-held | 0/8 |
| **driver after the fix, gain 1** | **6/864 = 0.7 %** |
| driver after the fix, gain 64 | 0/211 |

`RREG` readback proved mode 1 (CPOL=0/CPHA=1) is *correct*, so the fault was the
read length, not the SPI phase - the plan's leading candidate is refuted.

**Prediction 2b is falsified.** On a confirmed hands-off run the nub sits at
mean x -4.40e6 / y -4.47e6, about 52 % of full scale below neutral, and never
approaches the documented 131622 / -21. At gain 64, now read correctly, both
channels pin at exactly -8388608 (`0x800000`, sd 0) - a true rail, so EXP07's
railed verdict was sound and only its *rendering* (`0x808000`) was malformed.

**The signal is not usable as a pointer.** With the read fixed and the 50/25 Hz
mains nulled (40 ms boxcar) on a confirmed hands-off rest run:

| | rest (23.4 s) | circle (27.0 s) |
|---|---|---|
| x sd / y sd | 9.5e4 / 9.6e4 | 1.43e5 / 1.56e5 |
| r(x,y) | +0.905 | +0.958 |
| PCA minor/major | 0.22 | 0.15 |

The motion is real - ~1.5x the rest floor, and visible in
`exp08-circle-motion.svg` - but it is **common-mode**: x and y move together, so
only ~15 % of the signal is an independent axis, giving an SNR of ~1.1 on the
axis that carries direction. A circle in the hand comes out as a straight line.
Both channels measure against the same AIN2 node, so a wander there moves x and
y together - the leading suspect for the next experiment.

## Learnings
- **`tpoint raw [mode] [n] [khz] [cmd] [split]` is the read-path probe.** It
  re-reads the ADC in its own SPI transaction and hexdumps every byte, bypassing
  `sys_get_be24()` entirely - run it before trusting any logged value.
- **A 3-byte `RDATA` read is one byte short.** The ADS1220 streams while the
  command byte is clocked in and restarts after it, so `rx = [b0, b0, b1]`:
  `b0` lands in both top bytes and `b2` is never read. Fix: read **4 bytes and
  use bytes 1..3** (`rx[0]` is the ambiguous pre-command byte). `hi==mid` goes
  from 40/40 to 0/40. Datasheet: *"the device starts to output the requested
  data on DOUT/DRDY at the first SCLK rising edge after the command byte."*
- **`RREG` readback is the operator-free ground truth for the SPI phase.** Mode 1
  returns stable config bytes (`0x84`, `0xA0`) while `rx[0]` carries live data,
  so mode 1 is correct; modes 0/2/3 only looked clean because garbage also tends
  to have `hi != mid`. Use a known register to settle any future phase doubt.
- **Landing a driver fix:** `gh repo fork badjeff/ads1220-zephyr-module`, patch,
  add a `magidwilliam` remote in `config/west.yml` and pin the **commit SHA**
  (not the branch). CI builds the fork; `refs/` stays clean.
- **Flash loop gotchas:** bootloader entry (`devmem 0x4000051C 32 0x57` +
  `kernel reboot cold`) only works with the log flood off - verify with a
  `devmem 0x4000051C 32` read-back *before* rebooting. And `gh run download`
  fails with "file exists" while silently leaving the OLD UF2 in place:
  `Remove-Item -Recurse artifacts\EXP0N` first.
- **Operator handshake:** put the instruction in the question text and have the
  operator answer "yes" as they start moving - the question tool returns the
  instant they click, so the capture starts immediately (they never see tool
  output, so a printed cue is useless). **Confirm a "rest" run afterwards**: the
  first one was actually a motion run, and every statistic from it was void.
