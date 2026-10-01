# EXP04 - Circle-motion capture: is the raw X/Y signal good enough for pointer motion?

## Summary
The front-end now responds to nub motion (EXP03 ended railed; the live console shows
ch0/ch1 differing and moving). Record ~30 s of circular nub motion with a firmware
build that logs **only paired raw X/Y samples**, then analyze whether the signal is
good enough to resolve two independent axes and drive pointer motion. No mouse
output, no rewiring in this experiment.

## Hypothesis
A ~30 s circle captured at the 8 ms poll yields raw X/Y sample pairs that are
(a) far above the noise floor, (b) trace a **closed loop/ring** in the X-Y plane
(not a line or arc), (c) swing both axes in both directions **without sitting on
the ADC rail**, and (d) therefore carry enough independent information to map to
2-D pointer motion.
Falsified if: the X-Y plot collapses to a line/arc; one direction clips at the
rail (`0x808000` / `0x7FFFFF`); motion is swamped by the alternating rail samples
seen in the pre-experiment console sample; or X and Y are near-perfectly
correlated (crosstalk / shared node - EXP03 had ch0 == ch1 *identical*).

## Methodology & blast radius
- Method:
  1. Firmware: add `tpoint xy on|off` to `exp02_logging.c`. The single
     `analog_axis_hires` raw callback dispatches: ch0 buffers `raw_x`, ch1 emits
     one line per poll `XY <uptime_ms> <raw_x> <raw_y>` (no upstream patch).
  2. Silence every other log source: `CONFIG_{ZMK,ADC,GPIO,INPUT}_LOG_LEVEL_ERR`
     (kills the `analog_axis_hires`, `spi` and `zmk_hid_mouse_*` lines). Raise
     `CONFIG_USB_CDC_ACM_RINGBUF_SIZE` to 16384.
  3. Pin the poll rate for a deterministic capture: test-time devicetree
     `poll-period-downshift-ms = <8>` (single level = no 5 s -> 100 ms -> 1300 ms
     downshift, which would otherwise gut the rate if the hand pauses).
  4. `capture-serial.ps1`: add a human cue + phase markers (`-CueAfterSeconds`,
     `-StopAfterSeconds`) so the operator knows when to circle and the analysis
     has clean window boundaries.
  5. Protocol: 5 s rest -> ~20 s slow circling (~2-3 revolutions) -> 5 s rest.
     `tpoint calib` at the start of the capture.
  6. Analysis: new `experiments/EXP04/analyze_xy.py` (stdlib only - matplotlib and
     numpy are not installed here). Emits `exp04-xy.csv`, SVG plots (X-Y ring,
     x(t), y(t)) and a findings summary.
- May touch: `exp02_logging.c`; `boards/shields/ads1220_tpoint/ads1220_tpoint.conf`
  (log levels, ring, `CONFIG_EXP04_XY_LOG`); `boards/shields/ads1220_tpoint/ads1220_tpoint.dtsi`
  (poll-rate override, clearly marked test-time); `Kconfig`;
  `capture-serial.ps1`; `experiments/EXP04/*`; `experiments-overview.md`; branch `EXP04`.
- Off-limits: `README.md` §1-§9 (design of record) *during* the run - results get
  proposed for it at conclude; `layout/`, `ads1220-tpoint/`, `refs/` (no upstream
  patch); **physical rewiring** (read-only on hardware); `flash-nicenano.ps1`
  (user-owned, untracked).

## Open questions (known unknowns)
- [ ] Where the `xy` logger lives - proposed default: extend `exp02_logging.c`.
- [ ] Mouse output during the test - proposed default: keep the input-listener
      wired but silenced; no pointer claims in this experiment.
- [ ] Rate pinning - proposed default: single-level `poll-period-downshift-ms = <8>`.
- [ ] Circle protocol - proposed default: 5 s rest / ~20 s circling / 5 s rest.
- [ ] Analysis dependencies - proposed default: stdlib-only Python + SVG/CSV.
- [ ] Start trigger - proposed default: the operator is asked (via a question) when
      to circle, rather than assuming they are at the bench.

## Conclusion (findings)
_Pending._

## Learnings
- (pending)
