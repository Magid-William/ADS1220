/*
 * EXP02 - ADS1220 TrackPoint bring-up logging helpers.
 *
 * The upstream analog-axis-hires driver logs raw samples only during the
 * boot calibration window (and only "on change" afterwards). This file adds
 * a small bench-only surface on top of the module's public API:
 *
 *   tpoint stream on|off   log EVERY raw sample (both channels)
 *   tpoint xy on|off       log one paired line per poll: XY <ms> <x> <y>  (EXP04)
 *   tpoint sample [n]      capture the next n samples (default 2) and print them
 *   tpoint status          device readiness + axis count
 *   tpoint calib           per-channel calibration (in_min/in_max/deadzone)
 *   tpoint idac <ua>       live IDAC excitation current (0/10/50/100/250/500/1000/1500)
 *   tpoint raw [mode] [n] [khz] [cmd] [split]
 *                          EXP08: raw byte probe; hexdump n received bytes at
 *                          SPI mode 0..3, a chosen clock, any command byte
 *                          (default 0x10 = RDATA) and an optional split read
 *                          (command alone with CS held, then the data bytes).
 *                          Defaults are the driver's own setup: mode 1, 3
 *                          bytes, 1000 kHz, RDATA, single transaction.
 *
 * Nothing here touches the analog front-end directly; every sample goes
 * through the driver's normal IDAC-gated path.
 *
 * SPDX-License-Identifier: MIT
 */

#include <stdlib.h>
#include <string.h>

#include <zephyr/kernel.h>
#include <zephyr/device.h>
#include <zephyr/devicetree.h>
#include <zephyr/init.h>
#include <zephyr/shell/shell.h>
#include <zephyr/logging/log.h>

#include <zephyr/input/input_analog_axis_hires.h>
#include <zephyr/drivers/adc/ads1220.h>
#include <zephyr/drivers/spi.h>

LOG_MODULE_REGISTER(exp02_logging, CONFIG_LOG_DEFAULT_LEVEL);

/* Node labels from boards/shields/ads1220_tpoint/ads1220_tpoint.dtsi */
#define EXP02_AXH_NODE DT_NODELABEL(anin0)
#define EXP02_ADC_NODE DT_NODELABEL(adc_ads1220)

/* The ADC's `reg`/`dev-reg` value; both nodes use 0 in this shield. */
#define EXP02_ADS1220_REG 0

static const struct device *const exp02_axh = DEVICE_DT_GET(EXP02_AXH_NODE);
static const struct device *const exp02_adc = DEVICE_DT_GET(EXP02_ADC_NODE);

static bool exp02_stream_on;
static atomic_t exp02_capture_remaining;
K_SEM_DEFINE(exp02_capture_done, 0, 1);

/*
 * EXP04: one compact paired line per poll (both channels are read in one poll,
 * ch0 then ch1). ch0 is buffered; the line is emitted when ch1 arrives.
 */
static bool exp04_xy_on;
static int32_t exp04_raw_x;

static void exp02_raw_cb(const struct device *dev, int channel, int32_t raw_val)
{
	ARG_UNUSED(dev);

	if (exp02_stream_on) {
		LOG_INF("RAW ch%d=%d", channel, raw_val);
	}

	if (exp04_xy_on) {
		if (channel == 0) {
			exp04_raw_x = raw_val;
		} else {
			LOG_INF("XY %u %d %d", (uint32_t)k_uptime_get(),
				exp04_raw_x, raw_val);
		}
	}

	if (atomic_get(&exp02_capture_remaining) > 0) {
		LOG_INF("SAMPLE ch%d=%d", channel, raw_val);
		if (atomic_dec(&exp02_capture_remaining) == 1) {
			k_sem_give(&exp02_capture_done);
		}
	}
}

static void exp02_ensure_cb(void)
{
	static bool registered;

	if (!registered) {
		analog_axis_hires_set_raw_data_cb(exp02_axh, exp02_raw_cb);
		registered = true;
	}
}

static int cmd_tpoint_stream(const struct shell *sh, size_t argc, char **argv)
{
	if (argc < 2) {
		shell_error(sh, "usage: tpoint stream on|off");
		return -EINVAL;
	}

	exp02_ensure_cb();

	if (!strcmp(argv[1], "on")) {
		exp02_stream_on = true;
		shell_print(sh, "tpoint stream: ON (every sample logged as 'RAW chN=val')");
	} else if (!strcmp(argv[1], "off")) {
		exp02_stream_on = false;
		shell_print(sh, "tpoint stream: OFF");
	} else {
		shell_error(sh, "expected 'on' or 'off', got '%s'", argv[1]);
		return -EINVAL;
	}

	return 0;
}

static int cmd_tpoint_xy(const struct shell *sh, size_t argc, char **argv)
{
	if (argc < 2) {
		shell_error(sh, "usage: tpoint xy on|off");
		return -EINVAL;
	}

	exp02_ensure_cb();

	if (!strcmp(argv[1], "on")) {
		exp04_xy_on = true;
		shell_print(sh, "tpoint xy: ON (per-poll line 'XY <ms> <x> <y>')");
	} else if (!strcmp(argv[1], "off")) {
		exp04_xy_on = false;
		shell_print(sh, "tpoint xy: OFF");
	} else {
		shell_error(sh, "expected 'on' or 'off', got '%s'", argv[1]);
		return -EINVAL;
	}

	return 0;
}

static int cmd_tpoint_sample(const struct shell *sh, size_t argc, char **argv)
{
	int n = 2;

	if (argc >= 2) {
		n = (int)strtol(argv[1], NULL, 10);
	}
	if (n <= 0) {
		n = 1;
	}

	exp02_ensure_cb();
	k_sem_reset(&exp02_capture_done);
	atomic_set(&exp02_capture_remaining, n);

	shell_print(sh, "capturing %d sample(s)...", n);

	/*
	 * Both channels are read in one poll, so n samples need n/2 polls.
	 * The driver downshifts to 1300 ms when idle, so allow generously.
	 */
	uint32_t timeout_ms = 2000 + (n / 2 + 1) * 1500;

	if (k_sem_take(&exp02_capture_done, K_MSEC(timeout_ms)) != 0) {
		atomic_set(&exp02_capture_remaining, 0);
		shell_error(sh, "timeout: no samples within %u ms", timeout_ms);
		return -ETIMEDOUT;
	}

	return 0;
}

static int cmd_tpoint_status(const struct shell *sh, size_t argc, char **argv)
{
	ARG_UNUSED(argc);
	ARG_UNUSED(argv);

	shell_print(sh, "adc_ads1220 ready : %s", device_is_ready(exp02_adc) ? "yes" : "no");
	shell_print(sh, "analog-axis ready : %s", device_is_ready(exp02_axh) ? "yes" : "no");
	shell_print(sh, "axes              : %d", analog_axis_hires_num_axes(exp02_axh));
	shell_print(sh, "stream            : %s", exp02_stream_on ? "on" : "off");

	return 0;
}

static int cmd_tpoint_calib(const struct shell *sh, size_t argc, char **argv)
{
	ARG_UNUSED(argc);
	ARG_UNUSED(argv);

	int n = analog_axis_hires_num_axes(exp02_axh);

	for (int i = 0; i < n; i++) {
		struct analog_axis_hires_calibration cal;

		if (analog_axis_hires_calibration_get(exp02_axh, i, &cal) == 0) {
			shell_print(sh, "ch %d: in_min=%d in_max=%d deadzone=%u",
				    i, cal.in_min, cal.in_max, cal.in_deadzone);
		} else {
			shell_error(sh, "ch %d: no calibration", i);
		}
	}

	return 0;
}

static int cmd_tpoint_idac(const struct shell *sh, size_t argc, char **argv)
{
	if (argc < 2) {
		shell_error(sh, "usage: tpoint idac <0|10|50|100|250|500|1000|1500>");
		return -EINVAL;
	}

	int ua = (int)strtol(argv[1], NULL, 10);
	int ret = ads1220_set_idac_ua_by_reg(EXP02_ADS1220_REG, (uint16_t)ua, true);

	shell_print(sh, "idac = %d uA (ret %d)", ua, ret);

	return ret;
}

/*
 * EXP08: raw RDATA probe. Re-reads the ADS1220 over the ADC's own SPI bus with
 * a caller-chosen SPI mode / byte count / clock and hexdumps every byte that
 * comes back - independent of the driver's hardcoded read. Used to locate the
 * (H,H,L) duplication: if rx[0] == rx[1] here too, the fault is the transfer,
 * not sys_get_be24(). Stop the XY logger first ('tpoint xy off').
 */
static int cmd_tpoint_raw(const struct shell *sh, size_t argc, char **argv)
{
	int mode = 1;   /* the driver's mode: CPOL = 0, CPHA = 1 */
	int nbytes = 3; /* the driver reads 3 bytes */
	int khz = 1000; /* spi-max-frequency in ads1220_tpoint.dtsi */
	int cmd = 0x10; /* ADS1220_RDATA_CMD; 0x20|addr<<2 = RREG */
	int split = 0;  /* 1 = issue the command alone, hold CS, then clock data */

	if (argc >= 2) {
		mode = (int)strtol(argv[1], NULL, 10);
	}
	if (argc >= 3) {
		nbytes = (int)strtol(argv[2], NULL, 10);
	}
	if (argc >= 4) {
		khz = (int)strtol(argv[3], NULL, 10);
	}
	if (argc >= 5) {
		cmd = (int)strtol(argv[4], NULL, 0);
	}
	if (argc >= 6) {
		split = (int)strtol(argv[5], NULL, 10);
	}
	if (mode < 0 || mode > 3) {
		shell_error(sh, "mode must be 0..3");
		return -EINVAL;
	}
	if (nbytes < 2) {
		nbytes = 2;
	}
	if (nbytes > 6) {
		nbytes = 6;
	}
	if (khz < 10) {
		khz = 10;
	}
	if (cmd < 0 || cmd > 0xFF) {
		shell_error(sh, "cmd must be 0..255");
		return -EINVAL;
	}

	struct spi_dt_spec spec = SPI_DT_SPEC_GET(EXP02_ADC_NODE, 0, 0);

	if (!device_is_ready(spec.bus)) {
		shell_error(sh, "SPI bus not ready");
		return -ENODEV;
	}

	uint32_t op = SPI_OP_MODE_MASTER | SPI_WORD_SET(8);

	if (mode & 1) {
		op |= SPI_MODE_CPHA;
	}
	if (mode & 2) {
		op |= SPI_MODE_CPOL;
	}
	spec.config.operation = op;
	spec.config.frequency = (uint32_t)khz * 1000U;

	uint8_t tx[6] = { 0 }; /* in split mode the command goes out separately */
	uint8_t rx[6] = { 0 };
	uint8_t txc = (uint8_t)cmd;
	uint8_t rxc = 0;

	tx[0] = split ? 0 : (uint8_t)cmd;

	struct spi_buf txb = { .buf = tx, .len = (size_t)nbytes };
	struct spi_buf rxb = { .buf = rx, .len = (size_t)nbytes };
	struct spi_buf_set txs = { .buffers = &txb, .count = 1 };
	struct spi_buf_set rxs = { .buffers = &rxb, .count = 1 };

	/*
	 * Split read: send the command byte on its own transaction with CS held
	 * low, then clock the data in a second transaction. This is what the
	 * ADS1220 datasheet describes - data starts on the first SCLK edge AFTER
	 * the command byte - and it is exactly what a single 3-byte transaction
	 * cannot do (8 clocks for the command + only 16 left for data).
	 */
	struct spi_buf t1 = { .buf = &txc, .len = 1 };
	struct spi_buf r1 = { .buf = &rxc, .len = 1 };
	struct spi_buf_set t1s = { .buffers = &t1, .count = 1 };
	struct spi_buf_set r1s = { .buffers = &r1, .count = 1 };

	shell_print(sh, "raw: cmd=0x%02X mode %d (CPOL=%d CPHA=%d), %d byte(s), %d kHz%s",
		    cmd, mode, (mode >> 1) & 1, mode & 1, nbytes, khz,
		    split ? ", split" : "");

	for (int i = 0; i < 4; i++) {
		int ret;

		if (split) {
			spec.config.operation = op | SPI_HOLD_ON_CS;
			ret = spi_transceive_dt(&spec, &t1s, &r1s);
			if (ret == 0) {
				memset(rx, 0, sizeof(rx));
				spec.config.operation = op;
				ret = spi_transceive_dt(&spec, &txs, &rxs);
			}
		} else {
			ret = spi_transceive_dt(&spec, &txs, &rxs);
		}

		if (ret != 0) {
			shell_error(sh, "[%d] spi_transceive ret %d", i, ret);
			return ret;
		}

		shell_fprintf(sh, SHELL_NORMAL, "[%d] rx:", i);
		for (int b = 0; b < nbytes; b++) {
			shell_fprintf(sh, SHELL_NORMAL, " %02X", rx[b]);
		}

		if (nbytes >= 3) {
			int32_t v = (int32_t)(((uint32_t)rx[0] << 16) |
					      ((uint32_t)rx[1] << 8) | rx[2]);

			if (v & 0x00800000) {
				v |= (int32_t)0xFF000000;
			}
			shell_fprintf(sh, SHELL_NORMAL,
				      "   be24=%d hi==mid=%s", v,
				      (rx[0] == rx[1]) ? "yes" : "no");
		}
		if (nbytes >= 4) {
			/* skip the duplicated first byte: rx = [b0, b0, b1, b2] */
			int32_t a = (int32_t)(((uint32_t)rx[1] << 16) |
					      ((uint32_t)rx[2] << 8) | rx[3]);

			if (a & 0x00800000) {
				a |= (int32_t)0xFF000000;
			}
			shell_fprintf(sh, SHELL_NORMAL, "   alt=%d", a);
		}
		shell_fprintf(sh, SHELL_NORMAL, "\n");
		k_msleep(10);
	}

	return 0;
}

SHELL_STATIC_SUBCMD_SET_CREATE(
	sub_tpoint_cmds,
	SHELL_CMD_ARG(stream, NULL, "Log every raw sample: tpoint stream on|off",
		      cmd_tpoint_stream, 2, 0),
	SHELL_CMD_ARG(xy, NULL, "Log paired raw XY per poll: tpoint xy on|off (EXP04)",
		      cmd_tpoint_xy, 2, 0),
	SHELL_CMD_ARG(sample, NULL, "Capture the next n samples (default 2)",
		      cmd_tpoint_sample, 1, 1),
	SHELL_CMD_ARG(status, NULL, "Device readiness and axis count",
		      cmd_tpoint_status, 1, 0),
	SHELL_CMD_ARG(calib, NULL, "Per-channel calibration",
		      cmd_tpoint_calib, 1, 0),
	SHELL_CMD_ARG(idac, NULL, "Set IDAC excitation current (uA)",
		      cmd_tpoint_idac, 2, 0),
	SHELL_CMD_ARG(raw, NULL, "EXP08 raw byte probe: tpoint raw [mode] [n] [khz] [cmd] [split]",
		      cmd_tpoint_raw, 1, 5),
	SHELL_SUBCMD_SET_END);

SHELL_CMD_REGISTER(tpoint, &sub_tpoint_cmds, "ADS1220 TrackPoint bring-up (EXP02)", NULL);

/*
 * EXP04: auto-enable the paired XY logger at boot so a capture does not depend
 * on typing a shell command at the right moment. APPLICATION runs after all
 * device init, so the driver's cal_lock is already initialised.
 */
static int exp02_logging_init(void)
{
#if defined(CONFIG_EXP04_XY_LOG)
	exp02_ensure_cb();
	exp04_xy_on = true;
	LOG_INF("EXP04: XY logging auto-enabled ('XY <ms> <x> <y>')");
#endif
	return 0;
}

SYS_INIT(exp02_logging_init, APPLICATION, 0);
