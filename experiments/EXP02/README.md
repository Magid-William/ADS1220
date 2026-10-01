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
  2. Shield `.conf`: add the user-requested `CONFIG_SHELL=y`,
     `CONFIG_KERNEL_SHELL=y`, `CONFIG_GPIO_SHELL=y`, `CONFIG_LOG=y`, plus
     `CONFIG_DEVICE_SHELL=y`, `CONFIG_SPI_SHELL=y`, `CONFIG_SPI_LOG_LEVEL_DBG=y`,
     and a larger log buffer (`CONFIG_LOG_BUFFER_SIZE=32768`,
     `CONFIG_LOG_PROCESS_THREAD_SLEEP_MS=10`). Keep the EXP01 DBG levels and
     `CONFIG_LOG_CMDS=y`.
  3. New app source `exp02_logging.c`, compiled into the ZMK app via the module
     (`zephyr/module.yml` gains `build: cmake: .`, plus a root `CMakeLists.txt`).
     It provides `tpoint stream on|off` (logs every raw sample through
     `analog_axis_hires_set_raw_data_cb()`), `tpoint read`, `tpoint status`,
     `tpoint calib`, and `tpoint idac <ua>` (`ads1220_set_idac_ua_by_reg`).
  4. No upstream patch. Handshake register values are read with the `spi` shell
     (`spi conf adc_ads1220 1000000 h`; `spi transceive 06`; `spi transceive 20 00`;
     `spi transceive 23 00 00 00 00`); `CONFIG_SPI_LOG_LEVEL_DBG` shows every
     driver SPI transaction's status.
  5. Build on the existing GitHub Actions workflow; download the UF2; flash.
  6. New `capture-serial.ps1` logs the CDC-ACM session; run boot + handshake +
     `tpoint` sequence; read findings.
- May touch: `boards/shields/ads1220_tpoint/{ads1220_tpoint.conf,README.md}`;
  new `exp02_logging.c` + `CMakeLists.txt` at repo root; `zephyr/module.yml`;
  `capture-serial.ps1`; `experiments/EXP02/README.md`; `experiments-overview.md`;
  branch `EXP02`.
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
- [x] Capture tooling - new `capture-serial.ps1` (no `tio` assumed on Windows).
- [x] RTT backup backend - **no** (no debug probe assumed).
- [x] `CONFIG_ADC_SHELL` - not usable: its device list omits `ti,ads1220` and it
  reads with a 2-byte buffer vs the driver's 24-bit/>=4-byte requirement.

## Conclusion (findings)
_Pending._

## Learnings
- `<command that worked>` - use when <condition>
