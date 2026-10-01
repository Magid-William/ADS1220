/*
 * EXP02 - ADS1220 TrackPoint bring-up logging helpers.
 *
 * The upstream analog-axis-hires driver logs raw samples only during the
 * boot calibration window (and only "on change" afterwards). This file adds
 * a small bench-only surface on top of the module's public API:
 *
 *   tpoint stream on|off   log EVERY raw sample (both channels)
 *   tpoint sample [n]      capture the next n samples (default 2) and print them
 *   tpoint status          device readiness + axis count
 *   tpoint calib           per-channel calibration (in_min/in_max/deadzone)
 *   tpoint idac <ua>       live IDAC excitation current (0/10/50/100/250/500/1000/1500)
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
#include <zephyr/shell/shell.h>
#include <zephyr/logging/log.h>

#include <zephyr/input/input_analog_axis_hires.h>
#include <zephyr/drivers/adc/ads1220.h>

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

static void exp02_raw_cb(const struct device *dev, int channel, int32_t raw_val)
{
	ARG_UNUSED(dev);

	if (exp02_stream_on) {
		LOG_INF("RAW ch%d=%d", channel, raw_val);
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

SHELL_STATIC_SUBCMD_SET_CREATE(
	sub_tpoint_cmds,
	SHELL_CMD_ARG(stream, NULL, "Log every raw sample: tpoint stream on|off",
		      cmd_tpoint_stream, 2, 0),
	SHELL_CMD_ARG(sample, NULL, "Capture the next n samples (default 2)",
		      cmd_tpoint_sample, 1, 1),
	SHELL_CMD_ARG(status, NULL, "Device readiness and axis count",
		      cmd_tpoint_status, 1, 0),
	SHELL_CMD_ARG(calib, NULL, "Per-channel calibration",
		      cmd_tpoint_calib, 1, 0),
	SHELL_CMD_ARG(idac, NULL, "Set IDAC excitation current (uA)",
		      cmd_tpoint_idac, 2, 0),
	SHELL_SUBCMD_SET_END);

SHELL_CMD_REGISTER(tpoint, &sub_tpoint_cmds, "ADS1220 TrackPoint bring-up (EXP02)", NULL);
