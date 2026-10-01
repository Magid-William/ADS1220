# Copyright (c) 2026 Magid-William
# SPDX-License-Identifier: MIT
#
# EXP02: ADS1220 TrackPoint bring-up logging helpers.
# This is a Zephyr module root (see zephyr/module.yml); this CMakeLists.txt
# adds the bench-only `tpoint` command / raw-sample logger to the ZMK app.

zephyr_library()
zephyr_library_sources_ifdef(CONFIG_EXP02_LOGGING exp02_logging.c)
