# ads1220_tpoint

Minimal ZMK shield for a 4-wire TrackPoint strain gauge read directly by an
**ADS1220** (SPI) on a **nice!nano**, using
[`badjeff/ads1220-zephyr-module`](https://github.com/badjeff/ads1220-zephyr-module).

This is the firmware half of EXP01. The hardware design of record (wiring,
perfboard layout, diagrams) is in the parent project.

## Wiring assumed by the shield

| ADS1220 | nice!nano | note |
|---|---|---|
| SCLK (1) | P0.08 | `&spi2`, 1 MHz, mode 1 |
| DOUT/DRDY (15, MISO) | P0.20 | |
| DIN (16, MOSI) | P0.17 | |
| DRDY (14) | P1.06 | active low, pull-up |
| CS (2) | GND | **tied low, no `cs-gpios`** |
| CLK (3) | GND | internal oscillator |
| REFP0 (9) | TrackPoint `[a]` | IDAC1 exits here |
| REFN0 (8) | TrackPoint `[b]` + GND | |
| AIN0 (11) | TrackPoint `[x]` | |
| AIN1 (10) | TrackPoint `[y]` | |
| AIN2 (7) | divider midpoint | = V(a)/2 bias |
| AIN3 (6) | float | do not ground |

Divider: **R1 = R2 = 2.2 kΩ** (one resistor per leg, the unused second position
bridged), **C3 = 100 nF** at AIN2 -> AIN2 source impedance 1.1 kΩ, divider load
4.4 kΩ. Ratiometric, so gain and scale are unaffected by the value.

`idac-ua = 500 µA`. Retune once `R_ab` is measured, keeping
`V(a) = I_IDAC × (R_ab ∥ 4.4 k)` inside **0.75 V … 2.4 V**: use 500 µA for
`R_ab ≳ 6 kΩ`.

The 1×1 kscan (pro_micro 19/21 → P0.02/P0.31) is a placeholder: nothing is wired
to it, it exists only because ZMK wants a kscan and a physical layout.

## Debugging

The build uses the `zmk-usb-logging` snippet, which routes the Zephyr console and
`zephyr,shell-uart` to a USB CDC-ACM device. On top of that the shield enables:

- `CONFIG_{ZMK,ADC,GPIO,INPUT}_LOG_LEVEL_DBG`
- `CONFIG_SHELL` + `CONFIG_SHELL_BACKEND_SERIAL` (init priority 51) + `CONFIG_LOG_CMDS`
- `CONFIG_GPIO_SHELL` (`gpio get/set`, useful for poking the IDAC line)
- `CONFIG_LOG_PROCESS_THREAD_STARTUP_DELAY_MS=3000`

There is **no ZMK-specific shell** — this is the stock Zephyr shell on the ZMK USB
console. Connect to the CDC-ACM port (`tio /dev/ttyACM0`, or a serial terminal on
Windows), then raise/lower levels at runtime with `log enable dbg <module>`.

Quickest liveness check at boot — the driver logs the neutral raw value:

```
ch 0 calibrated: avg:... dt_range:... deadzone:... min:... max:...
ch 1 calibrated: avg:...
```

Expect `ch 0` (x) around `131622` and `ch 1` (y) around `-21` with this gain and
reference (badjeff's reference values). Wildly different, railed, or missing means
the analog front-end is wrong, not the firmware.

## Build

GitHub Actions builds every entry in the root `build.yaml` on push.

Locally:

```
west build -s zmk/app -b nice_nano@2.0.0 -S zmk-usb-logging -- -DSHIELD=ads1220_tpoint
```
