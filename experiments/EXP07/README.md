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
_Pending._

## Learnings
- (pending)
