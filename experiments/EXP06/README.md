# EXP06 - Gain 16: does the neutral come into the input window?

## Summary
EXP05 showed the nub reads like a contact: hands-off is a single stable value
(`-8355840`, the negative rail), hand-on is ~40% off-plateau junk that does not
change with position. Leading suspect: at gain 64 the input window is only about
`Vref/64` (~16 mV), so the neutral offset pins the reading to the rail. Drop the
gain to 16 (4x wider window) and repeat the short circle capture.

## Hypothesis
With `zephyr,gain = "ADC_GAIN_16"` the neutral offset fits inside the input
window, so hands-off no longer sits on the rail and a 10 s circle capture yields
a continuously readable, position-dependent signal (ideally a ring in X-Y).
Falsified if hands-off is still railed and/or the circle capture is still
position-independent - which would point at the excitation voltage / bridge
(measure `V(a)`, `R_ab`), not the gain.

## Methodology & blast radius
- Method:
  1. Branch `EXP06` off `EXP05` (keeps: quiet `XY` logger, pinned 8 ms poll,
     IDAC always on - no `avdd-gpios`).
  2. Devicetree only: change both channels `zephyr,gain` from `ADC_GAIN_64` to
     `ADC_GAIN_16` (ADC gain is 1/2/4/8/16/32/64/128; 16 widens the window 4x and
     also widens the PGA common-mode range).
  3. Build (GitHub Actions), flash to COM8, confirm `XY` lines.
  4. **Hands-off baseline first** (cheap, no operator): is it still railed?
  5. Then a ~18 s capture: rest 4 s -> circle ~10 s -> rest 4 s.
  6. Analyse with `experiments/EXP04/analyze_xy.py`, compare with EXP04/EXP05.
- May touch: `boards/shields/ads1220_tpoint/ads1220_tpoint.dtsi` (gain),
  `experiments/EXP06/*`, `experiments-overview.md`, branch `EXP06`.
- Off-limits: `README.md` §1-§9 (design of record), `layout/`, `ads1220-tpoint/`,
  `refs/` (no upstream patch), **physical rewiring** (read-only on hardware).

## Open questions (known unknowns)
- [ ] Gain step - proposed default: 16. If still railed, try 8 then 4.
- [ ] `in-min`/`in-max` - left as-is; the raw capture does not use them and the
      boot calibration overwrites `in_min`/`in_max` anyway. Revisit for shipping.
- [ ] Capture length - proposed default: hands-off baseline + ~18 s circle run.
- [ ] Analyzer - reuse `experiments/EXP04/analyze_xy.py`.

## Conclusion (findings)
**Status: failed** (operator-declared). The hypothesis - that gain 16 would bring
the neutral into the input window - is falsified, so the experiment missed its goal.

**Gain is not the lever. At gain 16 the hands-off reading is the exact same
code as at gain 64 (`-8355840`), and the circle capture is unchanged.**

- Hands-off baseline, gain 16: `0%` off-plateau, one value (`-8355840`) for 8 s -
  byte-identical to gain 64 (EXP05).
- Hands-free `tpoint idac` sweep (gain 16): the reading **does** respond to the
  excitation - `idac 0` gives 51 distinct values, `idac 100` 2, `idac 500` and
  `1500` exactly 1 (railed). So the SPI/ADC path is alive and the reading is
  excitation-linked; it is simply pinned.
- Circle capture, gain 16 (20 s): off-plateau fraction flat at 39-55% in every
  0.5 s bin, rest and motion alike; rest std (3.24 M) >= motion std (2.78 M);
  plateau 54%; no position dependence. Identical in character to EXP04/EXP05.
- The off-plateau values cluster about every ~65600 counts (about `2^16`, i.e.
  `full-scale/127`) with fine noise on top, at both gains.

Reading: the **normalised** bridge imbalance (or bias error) looks very large -
still railed at gain 16 means the differential exceeds roughly 6% of the bridge
excitation, which no healthy strain-gauge neutral should do - and it does not
scale the way a normal conversion would. That pointed at the analog front-end /
wiring, not at the firmware.

**Postscript (EXP07) - that reading was wrong.** EXP07 found the logged 24-bit
samples are malformed: the top two bytes are identical in 100% of samples, at
every gain, on both axes. A malformed word (`H, H, L`) cannot be inverted into a
bridge voltage, so no "imbalance" can be inferred from it at all. What the
identical rail at gain 16 and 64 actually shows is that the corrupted word is the
same regardless of gain, i.e. it was never a conversion of the bridge in the first
place. The real fault is in the SPI transfer, not the front-end; see EXP07.

Artifacts: `exp06-hands-off.log`, `exp06-idac-sweep.log`, `exp06-circle.log`,
`exp06-circle.trimmed.log` (+ csv/svg via the EXP04 analyzer).

**Next experiment - superseded by EXP07.** This pointed at a meter session
(`R_ab` unpowered; then `V(a)`, `V(b)`, `V(x)`, `V(y)`, `V(AIN2)` with the driver
polling). Still worth doing eventually, but EXP07's malformed-sample finding has
to be settled first: there is no point measuring a bridge whose samples cannot be
read correctly.

## Learnings
- **Hands-off at gain 16 and gain 64 give the identical code**, so the rail is not
  an input-window problem and lowering the gain is not a fix.
- **`tpoint idac <ua>` is a hands-free liveness test.** `0` -> many distinct
  values, `500`/`1500` -> one. Proves the ADC and SPI answer, and that the reading
  follows the excitation, with no operator and no rebuild.
- **Per-bin off-plateau fraction** is the fast "is the nub doing anything?" test;
  it was flat at ~45% here.
- **Do the hands-free work first.** Baselines and IDAC sweeps need no operator, so
  they can settle a question before ever asking someone to touch the nub.
