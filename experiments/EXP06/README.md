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
_Pending._

## Learnings
- (pending)
