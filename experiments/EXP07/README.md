# EXP07 - Gain ladder: how big is the neutral offset?

## Summary
EXP06 falsified "gain 16 fixes it": the hands-off reading at gain 16 is
byte-identical to gain 64 (`-8355840`), so the neutral offset is much larger
than the input window. Walk the gain down (8 -> 4 -> 1) and record the hands-off
reading at each step. This is all hands-free until something comes off the rail.

## Hypothesis
The neutral is railed because the normalised bridge imbalance
`(V(x) - V(AIN2)) / (V(a) - V(b))` exceeds `1/gain`. Lowering the gain widens the
window, so at some step the hands-off reading leaves the rail and becomes a real
value. The step at which it leaves bounds the imbalance: 8 -> >12.5%, 4 -> >25%,
1 -> >100%.
Falsified (for the front-end) if even gain 1 stays railed - then the imbalance
exceeds 100%, which is a wiring/pad fault, not an offset.

## Methodology & blast radius
- Method:
  1. Branch `EXP07` off `EXP06` (keeps: quiet `XY` logger, pinned 8 ms poll,
     IDAC always on).
  2. Devicetree only: step `zephyr,gain` 16 -> 8 -> 4 -> 1, one build+flash per
     step, and take a **hands-off** capture at each (no operator needed).
  3. Stop as soon as hands-off leaves the rail; then ask the operator for a
     10 s circle at that gain.
  4. If a gain leaves the rail, also record the neutral code, to sanity-check it
     against the expected mid-scale.
- May touch: `boards/shields/ads1220_tpoint/ads1220_tpoint.dtsi` (gain),
  `experiments/EXP07/*`, `experiments-overview.md`, branch `EXP07`.
- Off-limits: `README.md` §1-§9 (design of record), `layout/`, `ads1220-tpoint/`,
  `refs/` (no upstream patch), **physical rewiring** (read-only on hardware).

## Open questions (known unknowns)
- [ ] Start gain - proposed default: 8 (what was promised), then 4, then 1.
- [ ] Meter - not available yet, so this experiment must be meter-free.
- [ ] Analyzer - reuse `experiments/EXP04/analyze_xy.py`.

## Conclusion (findings)
_(Provisional - awaiting the operator's status declaration. The ladder
hypothesis is falsified, and the experiment turned up a sample-format fault that
matters more than the gain.)_

**Gain ladder, hands-off (no operator), one value logged per step:**

| gain | hands-off x | verdict |
|---|---|---|
| 64 | exactly `-8355840` | railed |
| 16 | exactly `-8355840` | railed |
| 8  | exactly `-8355840` | railed |
| 4  | `-8355840` 94% of the time, one step (~65800) off otherwise | barely off |
| 1  | wanders `-3.5M .. -5.6M` | off the rail |

So the gain ladder does eventually break the rail (at gain 1, not 8), but it does
**not** produce a usable signal. In the 18 s circle at gain 1 the resting and
circling windows are indistinguishable (motion sd 4.4e5 vs rest sd 8.0e5, SNR
0.56 < 1), x and y move together, and the value wanders the same way whether or
not the nub is touched. Same verdict as EXP04-EXP06, reached from the other side.

**The real find: the samples are malformed.**

Every 24-bit sample has its **top two bytes identical** - i.e. the word is
`(H, H, L)`. Measured directly on the logged values:

| capture | x | y |
|---|---|---|
| EXP05 gain 64 | 2488/2488 = 100% | 100% |
| EXP06 gain 16 | 2239/2239 = 100% | 100% |
| EXP07 gain 1  | 2244/2244 = 100% | 100% |

The old "rail" has the same shape: `-8355840` = `0x808000` = bytes `80 80 00`,
and every other level seen in EXP04-EXP06 (`0xFCFC20`, `0xF9F96C`, ...) is the
same pattern. A genuine 24-bit conversion gives `byte0 == byte1` about 1 time in
256; 2244/2244 is not a property of the signal, it is a property of the read.

The data path is simple and checks out: `ads1220_read_sample()` does a 3-byte
`RDATA` transceive and `sys_get_be24(rx_buf)`, sign-extended; the axis driver
passes `bufs[i]` straight through (`int32_t raw_val = bufs[i];`). Nothing in that
path duplicates a byte. The duplication is therefore in the SPI transfer itself
(clock phase/frequency, MISO integrity, or CS timing), not in the sensor.

**Consequence: EXP04/EXP05/EXP06's "the front-end saturates" is not sound.**
Those verdicts were read off malformed samples. What the bridge actually does is
unknown until the read is fixed, and the gain should be put back to the design
value (64) for any re-test.

Artifacts: `exp07-gain8-hands-off.log`, `exp07-gain4-hands-off.log`,
`exp07-gain1-hands-off.log`, `exp07-gain1-circle.log`,
`exp07-gain1-circle.trimmed.log`; builds in `artifacts/EXP07*`.

## Learnings
- **`hi == mid` is the sample-format smoke test.** For each logged 24-bit `v`,
  check `((v>>16)&0xFF) == ((v>>8)&0xFF)`. It should hold ~0.4% of the time; it
  held 100% in EXP05/06/07. Run this on every future capture before believing any
  statistic computed from the raw values.
- **Flash loop, reliable order:** push -> `gh run watch <id> --exit-status` ->
  `gh run download <id> -D <dir>` -> if the serial bootloader entry fails, wait
  and `Get-CimInstance Win32_LogicalDisk | ? VolumeName -eq NICENANO`; the
  `G: NICENANO` drive often appears 30-90 s later, and copying the UF2 to it is
  the whole flash.
- The serial `devmem 0x4000051C 32 0x57` + `kernel reboot cold` bootloader entry
  is unreliable while the 125 Hz `XY` log floods the console. Stop the log first
  (`tpoint xy off`) or just wait for the drive.
- The COM port moves across a reboot (`COM8` -> `COM15` -> `COM8`); re-probe
  ports after every flash instead of assuming `COM8`.
- `tpoint idac <ua>` remains the cheapest hands-free liveness test: `0` -> many
  distinct values, `500`/`1500` -> one. It proves the ADC and SPI answer without
  the operator or a rebuild.
