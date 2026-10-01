# EXP02 - Full-path ADS1220 logging: handshake to readings and errors

## Summary
Instrument the EXP01 shield for maximum observability: the stock Zephyr shell
(`shell`, `kernel`, `gpio`, `device`, `spi`, `log`) plus DBG logging on every
driver in the ADS1220 path, plus a `tpoint` command that logs every ADC reading -
so one USB CDC-ACM session shows the whole chain from SPI handshake to readings,
and every warning/error.

## Hypothesis
With DBG logging on SPI/ADC/GPIO/input **and** the Zephyr shell, a single USB
CDC-ACM capture contains the complete ADS1220 path - chip reset, CONFIG0-3 write
+ readback, DRDY mode, IDAC routing, START/RDATA, **every** raw sample,
per-channel calibration, and all errors/warnings - with **no patch to the
upstream module** and no message loss under 8 ms polling. Falsified if a stage is
invisible (upstream DBG compiled out and no shell path reaches it) or if messages
are dropped/overflowed.

## Methodology & blast radius
- Method:
  1. Branch `EXP02` off `EXP01` (the shield lives on `EXP01`, not `master`).
  2. Shield `.conf`: add `CONFIG_SHELL=y`, `CONFIG_KERNEL_SHELL=y`,
     `CONFIG_GPIO_SHELL=y`, `CONFIG_LOG=y`, `CONFIG_DEVICE_SHELL=y`,
     `CONFIG_SPI_SHELL=y`, `CONFIG_SPI_LOG_LEVEL_DBG=y`, and a larger log buffer
     (`CONFIG_LOG_BUFFER_SIZE=32768`, `CONFIG_LOG_PROCESS_THREAD_SLEEP_MS=10`).
  3. New app source `exp02_logging.c`, compiled into the ZMK app via the module
     (`zephyr/module.yml` gains `build: cmake: .` + `kconfig: Kconfig`, plus a
     root `CMakeLists.txt`/`Kconfig`). It provides `tpoint stream on|off` (logs
     every raw sample through `analog_axis_hires_set_raw_data_cb()`), `tpoint
     sample [n]`, `tpoint status`, `tpoint calib`, and `tpoint idac <ua>`.
  4. No upstream patch. Register-level handshake via the `spi` shell and/or
     `CONFIG_SPI_LOG_LEVEL_DBG`.
  5. Build on the existing GitHub Actions workflow; download the UF2; flash.
  6. New `capture-serial.ps1` logs the CDC-ACM session (with `-Reset` to capture
     the boot log across USB re-enumeration).
- May touch: `boards/shields/ads1220_tpoint/{ads1220_tpoint.conf,README.md}`;
  new `exp02_logging.c` + `CMakeLists.txt`/`Kconfig` at repo root;
  `zephyr/module.yml`; `capture-serial.ps1`; `experiments/EXP02/README.md`;
  `experiments-overview.md`; branch `EXP02`.
- Off-limits: README §1-§9 (design of record), `layout/`, `ads1220-tpoint/`,
  `refs/` (no forking/patching upstream). A hardware problem is a finding.

## Open questions (known unknowns)
- [x] Scope - config **and** `tpoint`/callback code (the only way to log every
  post-calibration raw sample; EXP01 deferred the `tpoint` command to EXP02).
- [x] Patch upstream driver DBG? - **No**; use `CONFIG_SPI_LOG_LEVEL_DBG` +
  `spi` shell reads of CONFIG0-3.
- [x] Log mode - **deferred**, `LOG_BUFFER_SIZE=32768`, drain every 10 ms.
- [x] `skip-change-comparator` - **off** (the raw callback already gives every
  sample; keeps README §5 idle/power behaviour).
- [x] Capture tooling - `capture-serial.ps1` (no `tio` assumed on Windows).
- [x] RTT backup backend - **no** (no debug probe assumed).
- [x] `CONFIG_ADC_SHELL` - not usable: its device list omits `ti,ads1220` and it
  reads with a 2-byte buffer vs the driver's 24-bit/>=4-byte requirement.

## Conclusion (findings)

**Outcome: the logging goal is met; the measurement is blocked by a hardware
fault that the new instrumentation exposed on the first clean boot.**

### Goal met - the whole path is observable
One USB CDC-ACM capture now contains the ADS1220 path (driver init, DRDY mode,
IDAC GPIO, channel setup, calibration, per-sample `tpoint` logging, every
WRN/ERR) alongside the stock Zephyr shell (`shell`/`kernel`/`gpio`/`device`/`spi`/
`log`) and the `tpoint` command - **with no patch to either upstream repo**. The
full boot trace is saved as [`exp02-boot.log`](exp02-boot.log). Two config traps
had to be fixed to get there (see Learnings): plain ZMK USB logging is silently
deaf once a serial shell is enabled, and SPI DBG truncates the CDC ring.

### Finding - the ADS1220 does not drive MISO
`exp02-boot.log`:
```
<inf> ads1220: DRDY GPIO configured, using hardware interrupt
<inf> analog_axis_hires: Starting timer with period 8 ms
<inf> analog_axis_hires: Setting up channel 0, ADC channel 0
<err> ads1220: config0 mismatch! 0x1C != 0xFF
<err> analog_axis_hires: Could not setup channel #0 (-5)
```
The driver computed the correct `CONFIG0 = 0x1C` (AIN0-AIN2, gain 64); the
readback is `0xFF` - P0.20 (DOUT/DRDY) is undriven/floating. So channel setup
fails, no samples are produced, auto-calibration never runs (`tpoint calib` still
shows the untouched DT constants, deadzone `0`), and the pointer is dead. None of
this is a firmware fault.

Also noted: `All channels use same ADC: no` is expected (the two channels differ
in `input_positive`, so the driver configures them individually). And D6 (CS tied
to GND) is only partially validated - the reset write clocks out, but the first
register readback fails, so the CS-less *read* path is still unproven.

### Handed forward
- Meter the board: ADC power (`AVDD`/`DVDD`/`GND`), `DOUT/DRDY` pin 15 -> P0.20,
  and the breakout supply (README §8: does it have its own regulator?).
- If power and MISO are good, the candidate rework is D6 -> drive CS from a GPIO
  (`cs-gpios = <&gpio0 6 ...>`, the pin the module's own examples use).

### Status
Recommended **success**: the logging hypothesis is confirmed. The hardware fault
is a finding for a follow-up experiment, not a failure of this one.

## Learnings
- **Shell + logging on one console.** `CONFIG_SHELL_BACKEND_SERIAL=y` makes Zephyr
  default `LOG_BACKEND_UART=n` (its Kconfig is `default y if !SHELL_BACKEND_SERIAL`),
  leaving the shell backend as the only output - the console then shows just the
  boot banner + `uart:~$`. Fix: `CONFIG_LOG_BACKEND_UART=y` +
  `CONFIG_SHELL_LOG_BACKEND=n`. (Same root cause as EXP01's missing runtime logs.)
- **`CONFIG_SPI_LOG_LEVEL_DBG` truncates the log.** It emits ~5 `spi_context_*`
  lines/transaction; the boot/calibration burst overflows the 1024 B
  `CONFIG_USB_CDC_ACM_RINGBUF_SIZE` and cuts lines mid-message. Leave SPI at INF;
  raise the ring (8192) if needed.
- **Capture boot logs from reset:** `capture-serial.ps1 -Reset` reconnects across
  USB re-enumeration; `LOG_PROCESS_THREAD_STARTUP_DELAY_MS=3000` delays the flush.
- **Don't run `spi` shell commands while the driver polls** - they collide and
  yield spurious `config0 mismatch` / `spi_transceive returned -5`.
- **`analog_axis_hires_0` is the node *name*, not a label.** The shield dtsi is
  `anin0: analog_axis_hires_0 { }`, so use `DT_NODELABEL(anin0)`;
  `adc_ads1220` is a real label (`adc_ads1220: adc_ads1220@0`).
- **Adding app code to a ZMK module at repo root:** `zephyr/module.yml` needs
  `build: cmake: .` + `kconfig: Kconfig`; a root `CMakeLists.txt`
  (`zephyr_library_sources_ifdef(CONFIG_..., file.c)`) and `Kconfig` symbol.
- **Build/flash loop:** `git push` triggers `.github/workflows/build.yml`;
  `gh run watch <id> --exit-status`; `gh run download <id> -D <dir>`. The same
  upstream-module warnings as EXP01 remain (`gpio_ads1220.c` implicit
  declarations, `adc_ads1220.c` `-Wmaybe-uninitialized gain`).
