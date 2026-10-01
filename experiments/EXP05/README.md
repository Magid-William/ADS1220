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
**Status: failed** (operator-declared). The hypothesis - that leaving the IDAC on
continuously would reveal a settled, non-railed signal - is falsified, so the
experiment missed its goal.

**H1 (read-path settling) is falsified: leaving the IDAC on continuously did not
change the picture.** IDAC gating was not the cause.

The decisive comparison is hands-off vs hand-on, all on the same EXP05 firmware:

| capture | nub | x off-plateau |
|---|---|---|
| `exp05-probe.log` (6 s, right after flash) | hands off | **0%** - one value, `-8355840`, the whole time |
| hands-off baseline (8 s) | hands off | **0%** - still one value |
| `exp05-circle.log` (20 s, rest + 10 s circle) | hand on the nub | **~40% in every 0.5 s bin**, rest and motion alike |

Inside the circle capture the off-plateau fraction is flat at ~40% from start to
finish (39-50%), and the per-bin peak is essentially constant (~`-600000`,
range `-197587 .. -921304`) whether you were holding still or circling. The
off-plateau values fall on a **small fixed set of levels** spaced ~`2^16`
(about `-197600, -394900, -460600, -526500, -592200, -658100, -723900, -789700,
-855400, -921300`).

So: touching the nub switches the ADC from the rail into a fixed, position-
*independent* pattern. The nub currently reads like a **contact**, not a
position sensor - any contact saturates the front-end and the position is lost.

This matches README §8 / EXP03 ("analog front-end is railed") and points at:
- the IDAC compliance bound `V(a) <= AVDD - 0.9 V = 2.4 V` being exceeded
  (`V(a) = I_IDAC x (R_ab || 4.4k)`), and/or
- the neutral sitting outside the +/-`Vref/64` (~16 mV) input window at gain 64.

**Postscript (EXP07).** Both suspects above are now suspect in turn. EXP07 found
the logged 24-bit samples are malformed - the top two bytes are identical in 100%
of samples - and the "fixed ladder spaced ~`2^16`" noted below is that fault's
signature: a word written as `(H, H, L)` can only step in `H`, i.e. about `2^16`
per count. So the contact-not-a-sensor reading, and the rail/offset reading with
it, were taken from corrupted samples. The hypothesis is falsified regardless
(removing `avdd-gpios` changed nothing), but the analog conclusion does not hold.

Artifacts: `exp05-circle.log`, `exp05-circle-xy.csv`, `exp05-circle-{xy-scatter,
xy-live,x,y}.svg`. Analysis reused `experiments/EXP04/analyze_xy.py`.

Next experiment candidates (in order):
1. Bench-measure `R_ab`, `V(a)-V(b)`, `V(a)`, `V(x)`, `V(y)`, `V(AIN2)` with the
   driver polling; pick `idac-ua` so `V(a)` is inside 0.75-2.4 V.
2. Same capture at **gain 16** (then 8) so the neutral offset fits the window.
3. Only then a full circle capture to test X/Y independence.

## Learnings
- **Hands-off vs hand-on is the discriminator.** Nub untouched: one value forever
  (0% off-plateau). Hand on: ~40% off-plateau *regardless of position*. Take a
  hands-off baseline before blaming firmware or the read path.
- **Removing `avdd-gpios` leaves the IDAC on continuously** (`has_gpio_avdd` is
  false; `data->idac_ua` stays at the ADC node's `idac-ua` and each channel setup
  re-programs it). It builds and runs fine - and changed nothing, so the EXP04
  sawtooth was not IDAC gating.
- **A fixed ladder of levels spaced ~`2^16` is the duplicated-byte fault, not a
  quantised sensor.** A 24-bit word written as `(H, H, L)` can only step in `H`,
  i.e. by about `2^16` per count. See EXP07.
- **A second `capture-serial.ps1` run right after a capture is a free hands-off
  baseline** and needs no operator, so ask for the baseline separately from the
  circle run.
