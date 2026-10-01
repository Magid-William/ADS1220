# EXP05 - IDAC always-on: is the capture a poll-rate settling artefact?

## Summary
EXP04 could not see the nub in a 48 s circle capture: the values were ~2/3
pinned to the negative rail and the rest were a fast charge curve on the poll
cadence, with rest and motion statistically identical. Hypothesis: the driver
switches the IDAC on for every single read and reads before the bridge/reference
has settled. Leave the IDAC on continuously and repeat a short circle capture.

## Hypothesis
With the IDAC left on continuously (no per-poll gating) every conversion runs on
a settled bridge/reference, so a 10 s circle capture shows a **continuous,
non-railed** signal whose rest and motion windows differ (ideally a closed ring
in X-Y) and the fast settle sawtooth disappears.
Falsified if the capture is still mostly railed/transient, or if rest and motion
stay statistically indistinguishable (which would point at the analog front-end,
not the read timing).

## Methodology & blast radius
- Method:
  1. Branch `EXP05` off `EXP04` (keeps the quiet `XY <ms> <x> <y>` logger and
     the pinned 8 ms poll rate).
  2. Devicetree only: **remove `avdd-gpios`** from both `axis-x` and `axis-y`.
     `avdd-gpios` is optional; with it absent `has_gpio_avdd` is false and the
     driver never calls the `gpio_ads1220` IDAC on/off. The IDAC then stays at
     `idac-ua = <500>` (the ADC node value, re-programmed by each channel
     setup). No upstream patch.
  3. Build (GitHub Actions), flash to COM8, confirm `XY` lines.
  4. Capture ~18 s: rest 4 s -> circle ~10 s -> rest 4 s, using
     `capture-serial.ps1 -CueAfterSeconds/-StopAfterSeconds`.
  5. Analyse with `experiments/EXP04/analyze_xy.py` and compare against EXP04
     (plateau fraction, off-plateau signal, rest-vs-motion difference).
- May touch: `boards/shields/ads1220_tpoint/ads1220_tpoint.dtsi` (remove
  `avdd-gpios`), `experiments/EXP05/*`, `experiments-overview.md`, branch `EXP05`.
- Off-limits: `README.md` §1-§9 (design of record), `layout/`, `ads1220-tpoint/`,
  `refs/` (no upstream patch), **physical rewiring** (read-only on hardware).

## Open questions (known unknowns)
- [ ] Read change - proposed default: remove `avdd-gpios` (IDAC stays at 500 uA
      continuously). Alt: `skip-reg-write-low` on the `gpio_ads1220` node.
- [ ] Capture length - proposed default: ~18 s total (4 s rest / 10 s circle /
      4 s rest), per the operator's request.
- [ ] Power - IDAC on continuously is ~500 uA average; bench-only, reverted after.
- [ ] Analyzer - proposed default: reuse `experiments/EXP04/analyze_xy.py`.

## Conclusion (findings)
_Pending._

## Learnings
- (pending)
