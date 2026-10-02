# EXP09 - Node sweep: is the -4.4M common-mode the AIN2 mid-bias?

## Summary
EXP08 left a -4.4M common-mode offset and r(x,y)~0.9. Sweep each front-end node with the ADC's own mux (AIN2/x/y vs AVSS + AVDD monitor), localize it (suspect: the shared AIN2 mid-bias), repair, and re-test for independent axes.

## Hypothesis
The hands-off offset (x -4.40e6, y -4.47e6 at gain 1; exact -8388608 rail at gain 64)
is the **AIN2 mid-bias node sitting at ~V(a) instead of a/2** (open/bad low leg R1,
a bad joint, or AIN2 shorted to [a]); both channels inherit it because both
subtract the same AIN2. The arithmetic: with a healthy AIN2 = a/2, x-AIN2 =
-0.52 FS would put x below the bridge's bottom node, which is not physical for a
gauge midpoint; with AIN2 = a, x-AIN2 = x-a gives an ordinary midpoint ~2.4%
below half. badjeff's own T440 example documents working neutrals (131622/-21 at
gain 64 = ~2057/0 at gain 1), so the topology is fine and this board is not.

Predictions:
1. The node sweep reads `AIN2-AVSS` at ~**+1.0 FS** (rail), not +0.5 FS.
2. `AIN0-AVSS` and `AIN1-AVSS` read ~+0.47..0.48 FS and `AIN0-AIN1` ~+7e4: the
   whole offset is the AIN2 term, i.e. the mid-taps are ordinary.
3. After repairing that leg: `AIN2-AVSS` ~+0.50 FS, hands-off x/y near neutral,
   rest r(x,y) < 0.5, and a circle capture is a ring, not a line.

Falsified if `AIN2-AVSS` reads ~0.5 FS (bias node healthy): then the offset's
origin is elsewhere (dead/imbalanced bridge, wrong pad map, or a broken/low
reference) and the unpowered pad table is the follow-up.

## Methodology & blast radius
- Method:
  1. Branch `EXP09` off `EXP08`. Keep the pinned 8 ms poll, gain 1 and IDAC 500
     (the EXP04/05 test values) for the sweep, so the numbers are comparable to
     the EXP08 axis captures.
  2. Add `tpoint nodes` to `exp02_logging.c`: program CONFIG0's MUX directly
     (RREG CONFIG0 -> change MUX bits -> WREG) and take a single-shot reading
     (`START` 0x08, wait, 4-byte `RDATA` using bytes 1..3 - the EXP08 fix
     pattern). After each sample, RREG CONFIG0 again and discard the sample if
     an axis poll rewrote the MUX mid-read; repeat to 5 accepted samples and
     print the median (plus n, min, max) as raw and %FS. The axis driver keeps
     running (no suspend), so nothing is left stopped after the command.
  3. Pairs: AIN0-AIN2, AIN1-AIN2, AIN0-AIN1, AIN0-AVSS, AIN1-AVSS, AIN2-AVSS,
     AVDD monitor, (REFP0-REFN0)/4 monitor, shorted. Self-checks: the monitor
     must read +0.250 FS and the shorted pair ~0; the AVDD monitor gives
     `Vref = 0.825 V / %FS` (spec min 0.75 V).
  4. Run the sweep (operator-free) into `exp09-node-sweep.log`; repeat once at
     IDAC 1000 uA to check that the ratios are ratiometric (i.e. independent of
     the excitation current).
  5. If AIN2 is high: minimal rework of the bias leg only (reflow/replace R1,
     check the C3 joint and any AIN2<->[a] bridge); optionally add the unpowered
     DMM table (AIN2-GND, AIN2-a, a-b, and the README 7.1 pad map). Re-run the
     sweep - it is its own continuity tester.
  6. Re-validate: restore the design gain (64 first, step down only if the
     neutral misses the in-min/in-max window), take a hands-off rest capture,
     then an operator circle capture -> `experiments/EXP04/analyze_xy.py`.
     Criterion: r(x,y) < 0.5 and a visible ring (not a line).
- May touch: `exp02_logging.c` (the sweep command), `boards/shields/ads1220_tpoint/ads1220_tpoint.dtsi`
  (gain / `idac-ua` at the end), `experiments/EXP09/*`, `experiments-overview.md`,
  branch `EXP09`. Minimal rework confined to R1/R2/C3 and their joints is in scope.
- Off-limits: `refs/`, `README.md` 1-7 (design of record; 8 open-items ticked at
  conclude), `layout/`, `ads1220-tpoint/`, `config/west.yml` (no fork change);
  no sensor re-wiring and no re-layout - a new experiment if that turns out to be
  needed.

## Open questions (known unknowns)
- [ ] Soldering if the sweep confirms the bias - proposed default: **yes, bias
      leg only**; stop and report for anything larger.
- [ ] DMM available - proposed default: **not required** (the re-run sweep is the
      tester); use it only if available.
- [ ] Sweep implementation - proposed default: **raw SPI** (WREG/RREG/START/RDATA)
      in our bench file - no fork or `adc.h` dependency, reuses the EXP08-validated
      4-byte read; the driver-path `adc_read` is the fallback.
- [ ] Gain for acceptance - proposed default: **64** (design value), step down only
      if the neutral misses the window.
- [ ] Second IDAC point - proposed default: **yes**, 1000 uA.
- [ ] Restore the shipping power values (`avdd-gpios`, poll downshift) - proposed
      default: **no**, keep the EXP04/05 test values until the analog works.
- [ ] If prediction 1 is falsified - proposed default: run the unpowered pad table
      with the operator, then conclude with the localized finding.

## Conclusion (findings)
_Pending._

## Learnings
- (none yet)
