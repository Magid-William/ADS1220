# TrackPoint → ADS1220 → nice!nano (ZMK)

Status: **design frozen (bench bring-up pending `R(a↔b)` measurement).**
Scope: wiring + firmware for reading a 4-wire TrackPoint strain-gauge sensor
directly with an ADS1220, using the `badjeff/ads1220-zephyr-module`.

Parts: 1× ADS1220, 1× 4-wire TrackPoint (controller removed), 1× nice!nano,
4× 1.2 kΩ (divider: 2 in series per branch = 2.4 kΩ), 3× 100 nF, 8×16 dotted perfboard.

---

## 1. Decisions (locked)

| # | Decision | Choice | Reason |
|---|----------|--------|--------|
| D1 | Sensor interface | Analog 4-wire `[x][y][a][b]`, original TP controller removed | Confirmed by owner; T440 4-wire variant |
| D2 | ADC | ADS1220, badjeff module (`main`) | Chosen by owner |
| D3 | Bridge excitation | **IDAC1 → REFP0**, 250–500 µA (tune per §6.2) | No extra parts; matches `example-tpoint_idac.dtsi` |
| D4 | ADC reference | `REFP0/REFN0` (`ADC_REF_EXTERNAL0`) = bridge excitation | Ratiometric: IDAC tolerance cancels |
| D5 | Mid-bias | R1 = R2 = 2 × 1.2 kΩ in series (2.4 kΩ branch) → AIN2 (= a/2), + **C3 = 100 nF** AIN2↔GND | 0 V differential at rest; low AIN2 source impedance (1.2 kΩ) keeps the ADC's input-current error small (§3) |
| D6 | CS | Tied to GND; **no `cs-gpios` in DTS** | Datasheet-allowed; single SPI device; saves a pin |
| D7 | CLK | Tied to GND | Selects internal oscillator |
| D8 | AIN3 / REFN1 | Floating | Internal low-side switch lives on this pin |
| D9 | SPI | `&spi2`, 1 MHz, mode 1 (driver sets CPHA itself) | Matches module example |
| D10 | DRDY | P1.06 (`gpio1 6`) | Needed: DOUT cannot signal DRDY when CS is low |
| D11 | Channel config | AIN0−AIN2 (X), AIN1−AIN2 (Y); gain 64 @ 330 SPS | Matches `example-tpoint_idac.dtsi` |
| D12 | Power strategy | IDAC gated per conversion; poll downshift 8 → 100 → 1300 ms | Lowest average draw without a external wake hook (§5) |

---

## 2. Wiring (final)

Sensor is two half-bridges sharing [a] (top) and [b] (bottom):

```
  a ── G4 ── x ── G2 ── b      (X axis, mid-tap = x)
  a ── G1 ── y ── G3 ── b      (Y axis, mid-tap = y)
```

| ADS1220 (TSSOP-16 pin) | Connect to | Note |
|---|------------|------|
| SCLK (1) | nice!nano **P0.08** | |
| CS (2) | **GND** | tied low permanently |
| CLK (3) | **GND** | internal oscillator |
| DGND (4) | GND | |
| AVSS / AGND (5) | GND | |
| AIN3 / REFN1 (6) | **float** | do not ground |
| AIN2 (7) | R1/R2 midpoint | = a/2 bias into both channels |
| REFN0 (8) | TrackPoint **[b] + GND** | |
| REFP0 (9) | TrackPoint **[a] + R2** | IDAC1 exits here |
| AIN1 (10) | TrackPoint **[y]** | Y channel |
| AIN0 / REFP1 (11) | TrackPoint **[x]** | X channel |
| AVDD (12) | nice!nano VCC + 100 nF to GND | |
| DVDD (13) | nice!nano VCC + 100 nF to GND | |
| DRDY (14) | nice!nano **P1.06** | active low |
| DOUT/DRDY (15) | nice!nano **P0.20** (MISO) | |
| DIN (16) | nice!nano **P0.17** (MOSI) | |
| — | R1: **AIN2 ↔ GND** ([b]) | 2 × 1.2 kΩ in series = 2.4 kΩ, matched to R2 |
| — | R2: **AIN2 ↔ [a]** (REFP0) | 2 × 1.2 kΩ in series = 2.4 kΩ, matched to R1 |
| — | C3: **AIN2 ↔ GND** | 100 nF, settles the ADC's switched-cap input |

Owners's original drawing is correct as-is; the IDAC needs no extra wire. Only the
divider values changed (2.4 kΩ branches) plus **C3 = 100 nF** at AIN2.

Diagrams: `ads1220-tpoint/` (`.tex`, `.pdf`, `.png`, `.svg`) — page 1 = pinout +
digital + power, page 2 = analog front-end (rhombus).

---

## 3. Key facts behind the choices

- **Excitation is mandatory.** REFP0/REFN0 are buffered *sense* inputs (ref input
  current ±10 nA). They cannot power the bridge. Without a current source the
  bridge floats, the reference is ~0 V and both channels read noise. (Datasheet
  §9.1.4; ref input spec.)
- **IDAC** = ADS1220 built-in programmable current source, 10 µA…1.5 mA, routable
  to AIN0-3, REFP0 or REFN0; both IDACs may share a pin. Compliance:
  pin voltage ≤ AVDD − 0.9 V = **2.4 V** at 3.3 V.
- **Reference limits:** VREFP0 − VREFN0 ∈ **[0.75 V, AVDD]**.
- **Ratiometric:** reference = bridge excitation, so IDAC accuracy/drift cancels.
  Reference inputs do not load the bridge.
- **CS low is legal:** "CS can be tied low permanently in case the serial bus is
  not shared with any other device." An internal SPI timeout (~14000 × tMOD)
  resyncs the interface; DRDY (pin 14) "is always actively driven, even when CS
  is high".
- **CLK:** "Connect the CLK pin to DGND before power-up or reset to activate the
  internal oscillator."
- **AIN3:** "Leave the AIN3/REFN1 pin floating when not used" — it connects to
  AVSS through the internal low-side switch. Corollary: never enable
  `low-side-power-switch` with this wiring.
- **Divider value (R1 = R2 = 2.4 kΩ).** AIN2's source impedance is R1 ∥ R2. The
  ADC inputs draw nA-level bias/sampling current and TI warns that "the input
  currents flowing into and out of the device cause a voltage drop across the
  resistors". With 47 kΩ (23.5 kΩ at AIN2) that mismatch against the ~2 kΩ x/y
  taps is worth hundreds of µV — several percent of the ±19 mV full scale at
  gain 64 — and it drifts with temperature. TI's own input-filter example uses
  1 kΩ. 2.2–4.7 kΩ is the usable window; **2.4 kΩ chosen** (1.2 kΩ at AIN2).
  The divider is *not* in the reference path, so its tolerance does not affect
  the scale factor — it only sets the a/2 bias.
- **C3 = 100 nF from AIN2 to GND** settles the switched-capacitor input charge
  and filters the bias node; it also makes the divider's DC error irrelevant at
  the modulator rate. Sits at the AIN2 pin.
- **Driver behaviour (verified in source):** SPI mode 1; single-shot conversions
  (START/SYNC per read, `CONFIG1.MODE = 1`); PM suspend = `POWERDOWN` (400 nA);
  `idac-ua` sets the current, `zephyr,current-source-pin` routes it.

---

## 4. Configuration

`config/west.yml`:

```yaml
- name: ads1220-zephyr-module
  remote: badjeff
  revision: main
```

Overlay (adapt node names to the target shield):

```dts
&pinctrl {
    spi2_default: spi2_default {
        group1 {
            psels = <NRF_PSEL(SPIM_SCK, 0, 8)>,
                    <NRF_PSEL(SPIM_MOSI, 0, 17)>,
                    <NRF_PSEL(SPIM_MISO, 0, 20)>;
        };
    };
    spi2_sleep: spi2_sleep {
        group1 {
            psels = <NRF_PSEL(SPIM_SCK, 0, 8)>,
                    <NRF_PSEL(SPIM_MOSI, 0, 17)>,
                    <NRF_PSEL(SPIM_MISO, 0, 20)>;
            low-power-enable;
        };
    };
};

#include <dt-bindings/spi/spi.h>

&spi2 {
    compatible = "nordic,nrf-spim";
    status = "okay";
    pinctrl-0 = <&spi2_default>;
    pinctrl-1 = <&spi2_sleep>;
    pinctrl-names = "default", "sleep";
    /* no cs-gpios: CS is tied to GND */

    adc_ads1220: adc_ads1220@0 {
        compatible = "ti,ads1220";
        status = "okay";
        spi-max-frequency = <1000000>;
        reg = <0>;
        #io-channel-cells = <1>;
        #address-cells = <1>;
        #size-cells = <0>;
        drdy-gpios = <&gpio1 6 (GPIO_ACTIVE_LOW | GPIO_PULL_UP)>;
        idac-ua = <500>;   /* tune so V(a) >= 0.75 V, see README §6.2 */

        adc_ads1220_ch0: channel@0 {
            reg = <0>;
            zephyr,resolution = <24>;
            zephyr,gain = "ADC_GAIN_64";
            zephyr,reference = "ADC_REF_EXTERNAL0";
            zephyr,acquisition-time = <330>;
            zephyr,input-positive = <0>;          /* AIN0 = x */
            zephyr,input-negative = <2>;          /* AIN2 = a/2 */
            zephyr,current-source-pin = [05 00];  /* IDAC1 -> REFP0 */
        };
        adc_ads1220_ch1: channel@1 {
            reg = <1>;
            zephyr,resolution = <24>;
            zephyr,gain = "ADC_GAIN_64";
            zephyr,reference = "ADC_REF_EXTERNAL0";
            zephyr,acquisition-time = <330>;
            zephyr,input-positive = <1>;          /* AIN1 = y */
            zephyr,input-negative = <2>;
            zephyr,current-source-pin = [05 00];
        };
    };
};

#include <zephyr/dt-bindings/gpio/gpio_ads1220.h>

/ {
    gpio_ads1220: gpio_ads1220 {
        compatible = "ti,ads1220-gpio";
        status = "okay";
        gpio-controller;
        #gpio-cells = <2>;
        dev-reg = <0>;
        idac-ua-high = <500>;  /* keep equal to idac-ua above */
        idac-ua-low = <0>;
    };
};

#include <zephyr/dt-bindings/input/input-event-codes.h>

/ {
    anin0: analog_axis_hires_0 {
        compatible = "analog-axis-hires";
        status = "okay";

        /* 8 ms active -> 100 ms after 5 s -> 1300 ms after 7 s more */
        poll-period-downshift-ms = <8 5000 100 7000 1300>;

        axis-x {
            io-channels = <&adc_ads1220 0>;
            avdd-gpios = <&gpio_ads1220 ADS1220_GPIO_PIN_IDAC GPIO_ACTIVE_HIGH>;
            in-min = <( 131622 - 655300 )>;
            in-max = <( 131622 + 655300 )>;
            in-calib-cycle = <100>;
            in-deadzone-calib-scale-pctg = <110>;
            out-min = <( -127 )>;
            out-max = <( 127 )>;
            zephyr,axis-type = <INPUT_EV_REL>;
            zephyr,axis = <INPUT_REL_X>;
        };
        axis-y {
            io-channels = <&adc_ads1220 1>;
            avdd-gpios = <&gpio_ads1220 ADS1220_GPIO_PIN_IDAC GPIO_ACTIVE_HIGH>;
            in-min = <( -21 - 655300 )>;
            in-max = <( -21 + 655300 )>;
            in-calib-cycle = <100>;
            in-deadzone-calib-scale-pctg = <110>;
            out-min = <( -127 )>;
            out-max = <( 127 )>;
            zephyr,axis-type = <INPUT_EV_REL>;
            zephyr,axis = <INPUT_REL_Y>;
        };
    };
};
```

`.conf`:

```
CONFIG_SPI=y
CONFIG_GPIO=y
CONFIG_ADC=y
CONFIG_INPUT=y
CONFIG_INPUT_ANALOG_AXIS_HIRES=y
CONFIG_INPUT_ANALOG_AXIS_HIRES_SETTINGS=y
CONFIG_MULTITHREADING=y
```

Rules:
- Do **not** set `low-side-power-switch` (D8).
- Do **not** add `skip-change-comparator` initially (reports every poll → power
  draw and possible idle-sleep interference).
- Keep `idac-ua` and `idac-ua-high` equal.
- `in-min`/`in-max` are sensor-specific; `in-calib-cycle` replaces them at boot.

---

## 5. Power budget

| State | Estimate | Basis |
|---|---|---|
| Idle, poll 1300 ms | IDAC ~0.5 % duty ≈ **1–2 µA** avg; ADC in single-shot idle | 2 conversions × ~3 ms per 1300 ms |
| Active, poll 8 ms | IDAC ~75 % duty (e.g. 500 µA → **~375 µA** avg) | 2 conversions × ~3 ms per 8 ms |
| ADS1220 itself | ~120 µA duty-cycle mode; **400 nA** in POWERDOWN | Datasheet |
| vs. `[a]` → 3.3 V | bridge always powered, `3.3 V / R_ab` (hundreds of µA–1 mA) | rejected (D3) |

Estimates only until measured. Final period **1300 ms** (not 0) so the driver
never suspends the ADC — a 0 ms final period requires an external `RESUME` call.

---

## 6. Bring-up checklist

1. **Pad verification (unpowered).** All gauges ≈ R:
   `a↔b = R`, `x↔y = R`, and `a↔x = a↔y = b↔x = b↔y = 0.75 R`.
   Any near-0 Ω or open → wrong pads / 6-wire variant.
2. **Measure `R_ab`.** Pick the IDAC step from this table
   (`R_par = R_ab ∥ 4.8 k` for the 2.4 kΩ branches, V(a) target ≥ 0.75 V,
   compliance ≤ 2.4 V):

   | R_ab | R_par | step | resulting V(a) |
   |------|-------|------|----------------|
   | 1 k  | 0.83 k | 1000 µA | 0.83 V |
   | 2 k  | 1.41 k | 1000 µA | 1.41 V |
   | 3 k  | 1.85 k | 500 µA  | 0.92 V |
   | 4 k  | 2.18 k | 500 µA  | 1.09 V |
   | 6 k  | 2.67 k | 500 µA  | 1.33 V |
   | 10 k | 3.24 k | 250 µA  | 0.81 V |
   | 15 k | 3.62 k | 250 µA  | 0.90 V |
   | 20 k | 3.87 k | 250 µA  | 0.97 V |

3. **Power-up:** DVDD = AVDD = 3.3 V, no shorts, AIN3 untouched.
4. **Static voltages (driver polling):** V(a)−V(b) ≥ 0.75 V and
   V(x) ≈ V(y) ≈ V(a)/2 (± few mV at rest).
5. **Firmware:** both channels must move on the correct axis; if a channel
   clips/saturates, lower gain 64 → 16; then let `in-calib-cycle` set neutral,
   then tune `in-deadzone-calib-scale-pctg` / direction in ZMK.

---

## 7. Open items

- [ ] AliExpress ADS1220 board: does it carry its own 3.3 V regulator?
      If yes → feed its regulator input, not DVDD/AVDD from VCC.
      If chip + caps only → wiring as in §2.
- [ ] Measured `R_ab` → final `idac-ua` (see §6.2).
- [ ] Sensor pad order confirmation `[x][y][a][b]` (bottom view).
- [ ] Optional later: EN pin + final period 0 for true POWERDOWN
      (needs an external `ANALOG_AXIS_HIRES_ATTR_RESUME` caller).

---

## 8. References

- TI ADS1220 datasheet SBAS501: §8.3.2.1 (PGA common mode), §8.3.9 (low-side
  switch), §8.5.1 (SPI, CS tied low, SPI timeout, DRDY), §9.1.2 (analog input
  filtering — filter-resistor warning, 1 kΩ example), §9.1.3 (external reference),
  §9.1.4 (common mode), §9.1.5 (unused inputs), ref/IDAC electrical tables.
- `badjeff/ads1220-zephyr-module`: `README.md`, `example-tpoint_idac.dtsi`,
  `example-tpoint_avdd.dtsi`, `drivers/adc/adc_ads1220.c`,
  `drivers/input/input_analog_axis_hires.c`.
- `Magid-William/Articles` → `TrackPoint/README.md` §5.3 (24-bit ADC approach).
