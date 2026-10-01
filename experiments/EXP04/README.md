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
- [x] Logger lives in `exp02_logging.c` (`tpoint xy on|off`); auto-enabled by
      `CONFIG_EXP04_XY_LOG`.
- [x] Mouse output: input-listener left wired but its logs silenced; no pointer
      claims in this experiment.
- [x] Rate pinned: `poll-period-downshift-ms = <8>` (single level = no downshift).
      Measured 124.6 Hz over 48 s, zero dropped lines - the pin worked.
- [x] Protocol: rest / circle / rest, 48 s, cued by `capture-serial.ps1`.
- [x] Analysis: stdlib-only Python + SVG/CSV.
- [x] Start trigger: the operator was asked via a question before the capture.

## Conclusion (findings)
_(Provisional - awaiting the operator's status declaration. The goal was
"is the capture sufficient to read X/Y and drive the mouse?"; the finding
contradicts it, so this is a candidate for **failed**.)_

**No - the raw X/Y signal is not yet usable.** 48 s captured at 124.6 Hz
(5979 samples, no dropped lines); 4243 in the motion window.

Observed:
1. **Rest is pinned to the negative rail.** With the nub untouched both channels
   read exactly `-8355840` (`0x808000`) and never move (also seen in the 7 s
   pre-test probe). So the neutral point is not mid-scale; it is saturated.
2. **The signal is one-sided.** Over the whole motion window x spans
   `-8355840 .. +207` and y `-8355840 .. +60` - it swings only *away from* the
   rail, never past the rest value, so any opposite deflection would be clipped.
3. **~68% of samples sit on the plateau.** x modal `-8355840` = 2831/4243 (67%),
   y = 2918/4243 (69%). The time trace shows a repeating settle-then-reset
   pattern with a period of a few polls, not a continuously readable bridge.
4. **The axes are not independent.** Off-plateau samples (n=1340) have
   `r(x,y) = -0.52` and PCA minor/major `0.56`; the X-Y cloud is a filled
   diagonal blob, not a ring (ASCII density + `exp04-circle.trimmed-xy-live.svg`).
5. Rest "noise" std (2.37 M) >= motion signal std (2.22 M): SNR ~1.
6. **The off-plateau samples are a poll-rate charge transient, not the circle.**
   In a raw stretch the values climb smoothly out of the plateau over ~15-25
   samples then reset (few live samples per burst, median 2, ~16 ms) - the
   classic "IDAC switched on, node RC charges" curve. And the rest and motion
   windows are **statistically indistinguishable**: ~1/3 of samples are
   off-plateau *everywhere* (13-33 of 62 per 0.5 s bin, in rest and motion
   alike), and the per-bin peak has no slow period (best autocorrelation only
   `r = +0.2`). The nub motion does not visibly modulate the capture - which is
   exactly why the scatter looks random.

Interpretation (hypotheses for the next experiment, not yet tested):
- **H1 - read-path settling (primary).** Every poll switches the IDAC on, reads
  immediately, then off; the driver's own settle delay is commented out
  (`// k_usleep(150)`), so each conversion samples a still-charging
  bridge/reference. The sawtooth in (6) is that charge curve. Cheap test: drop
  `avdd-gpios` from the axis nodes so the IDAC stays on continuously (settled)
  and re-run the circle capture.
- **H2 - front-end offset/bias (may compound H1).** At gain 64 the full-scale
  differential is only `Vref/64` (~16 mV for Vref~1 V), so a static offset of
  that size rails the reading. Measure the statics (README §7) and lower gain
  64 -> 16.

Artifacts: `exp04-circle.trimmed.log` (XY + phase lines), `exp04-circle.trimmed-xy.csv`
(t, x, y, phase), `exp04-circle.trimmed-{xy-scatter,xy-live,x,y}.svg`.
The untrimmed 1.9 MB console log stays local (untracked).

Next experiment candidates: bench-measure `R_ab`, `V(a)-V(b)`, `V(x)`, `V(y)`,
`V(a)/2` with the driver polling; confirm the `[x][y][a][b]` pad order; re-run
the circle capture at a lower gain (16).

## Learnings
- **`capture-serial.ps1` can hand you a stale USB pre-buffer.** The first ~215
  XY lines of the capture were from a console session ~46 min earlier (uptime
  ~29 s), then the clock jumped to ~2.8 M ms. Drop any inter-sample gap
  `> 1000 ms` and keep the longest contiguous segment (in `analyze_xy.py`).
- **Pin the poll rate for a capture with a single-level
  `poll-period-downshift-ms = <N>`.** `num_downshift_levels` becomes 0, so the
  driver never downshifts; measured 124.6 Hz with zero dropped lines over 48 s.
- **`CONFIG_{ZMK,ADC,GPIO,INPUT}_LOG_LEVEL_ERR` + `CONFIG_EXP04_XY_LOG` leaves
  exactly one line per poll** (`<inf> exp02_logging: XY <ms> <x> <y>`); everything
  else in the ADS1220 path goes quiet. A lone `<dbg> zmk: kscan_matrix_init...`
  still appears at boot (different module level) - harmless.
- **The nub at rest rails the ADC** (`-8355840`, `0x808000`) on both channels;
  touching moves it only toward 0. Treat the exact rail value as "saturated",
  not as a valid sample, when analysing.
- **A random-looking X-Y scatter can be a *read* artefact, not noise.** Here the
  off-plateau samples form a repeating charge curve on the poll cadence (median
  2 live samples/burst, ~16 ms) and their statistics are identical in the rest
  and motion windows. Check rest-vs-motion before calling a cloud "the signal" -
  pooling the whole capture hides this.
- **`flash-nicenano.ps1` must run under pwsh, not Windows PowerShell 5.1**
  (5.1 fails to parse `($size bytes)` inside the string). Use `& .\flash-nicenano.ps1`.
- **The nice!nano is COM8** (VID_1D50&PID_615E, sole MI_00); COM22/COM21 are a
  different ZMK device (has a shell but no `tpoint`) - leave it alone.
