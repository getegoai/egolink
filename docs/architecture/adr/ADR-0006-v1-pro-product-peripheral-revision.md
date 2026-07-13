---
document_status: authoritative
last_verified: 2026-07-13
verified_by: codex
owner: founder
---

# ADR-0006: Revise V1 Pro Product Peripherals and Interaction

- Status: accepted
- Date: 2026-07-13
- Decision owner: founder

## Context

ADR-0005 selected the V1 Pro compute and cellular platform before the final
industrial design. Product comparison against Fitbit and Xiaomi devices then
exposed five peripheral decisions that must be corrected before schematic
capture: communication scope, battery capacity, useful sensor coverage,
waterproof charging, and display cost.

This revision does not reopen the `nRF54LM20B + Air780EGH` platform decision.
It supersedes only the conflicting display, battery, sensor-population, SIM,
charging, and public voice-call clauses in ADR-0005 and the first form-factor
baseline.

## Decision

### Data-First Communication

V1 Pro has no ordinary telephone dialer, public incoming number, contact list,
or SMS user interface. Guardian communication is carried by the EgoLink data
service:

- safety events, location, device health, and guardian commands;
- short text/status messages and store-and-forward voice messages;
- a future guardian-authorized live IP audio session using the retained
  microphone, codec, and speaker path;
- SOS always has a local alarm/countdown and sends the available evidence
  bundle when cellular becomes available.

The product does not claim instant remote wake while the cellular domain is
fully off. Low-power profiles use scheduled polling and local/BLE risk wake.
An independently measured registered-modem profile may trade endurance for
seconds-level guardian reachability.

The production board populates an internal MFF2 eUICC/IoT-SIM position and
keeps an internal nano-SIM fallback under the screwed rear shell. There is no
external SIM tray. Air780EGH dual-SIM operation remains single-standby. A
consumer one-number eSIM service is not a launch dependency because operator
and terminal provisioning support must be contracted separately.

### Battery

- Nominal product target: 900 mAh protected single-cell Li-polymer.
- Minimum accepted production capacity: 850 mAh after supplier tolerance.
- Cell includes a 10k NTC and an authenticated supplier drawing, swelling
  allowance, UN38.3 evidence, and cycle-life data.
- Public endurance remains a measured result. The 48-hour guard profile is a
  launch gate; 5-7 light-use days is a target, not a current claim.

### Sensor Set

V1 Pro uses complementary sensing rather than maximizing component count:

| Signal | Baseline part | Product value |
|---|---|---|
| Motion | `QMI8658A` | activity, fall/anomaly candidates, motion context |
| Acoustic | `MMICT5838-00-012` plus call microphone | wake/event models and voice interaction |
| Optical pulse | `MAX30101EFD+T` | heart-rate/SpO2 research signals and wear-contact evidence |
| Skin temperature | `MAX30208CLB+T` | personal thermal trend and multimodal anomaly context |
| Barometric pressure | `BMP390` | floor/altitude change and GNSS vertical-context assistance |
| Position/radio | Air780EGH GNSS/cell plus nRF BLE | outdoor and near-place location evidence |

PPG and temperature outputs are wellness/context signals only. V1 makes no
medical diagnosis, clinical SpO2, fever, fall-detection, or emergency-outcome
claim without separate validation. Magnetometer, ECG/EDA, gas/air-quality,
camera, and a third Wi-Fi radio are not populated in V1 because their current
safety value does not justify interference, calibration, power, or schedule.

### Display

The Sharp Memory LCD is replaced by a 1.3-inch white monochrome COG PMOLED
contract: `SH1106G`, 128 x 64, SPI, approximately 34.5 x 23.0 x 1.45 mm glass
and 29.42 x 14.70 mm active area. `GME12864-110` is the EVT mechanical and
electrical reference, not an exclusive production supplier.

The display is normally off and wakes for alerts, status, and interaction.
OLED has weaker direct-sun readability and finite luminance life, so DVT must
pass outdoor readability, burn-in, temperature, and lifetime tests. It avoids
the Sharp panel cost and separate night front-light while keeping a simple
monochrome UI. AMOLED and color TFT remain out of scope for V1.

### Waterproof USB-C

The magnetic pogo connector is replaced by a side-mounted, mid-mount IPX8
USB-C receptacle with USB 2.0 data pins. It provides 5 V charging and
Air780EGH recovery/log access; nRF SWD remains on internal pads. Production
selection requires an integrated connector gasket, supplier lifecycle data,
and enclosure compression drawing. EVT compares an economical connector with
an authorized TE/Hirose/Amphenol-class part before DVT lock.

The enclosure targets IP68 at 1.5 m for 30 minutes, subject to DVT test. It
uses a bonded cover lens, perimeter silicone gasket, sealed buttons,
hydrophobic acoustic membranes, a pressure-equalization vent, internal SIM,
USB ESD protection, and wet-port charging lockout. V1 does not claim 5 ATM,
swimming, hot-water, or charging while wet.

## Consequences

- The rear shell gains an optical window and a thermally isolated skin-contact
  island; both require human-fit and signal-quality validation.
- USB-C and the larger battery enlarge the thickness target modestly but remove
  a proprietary charger from the user workflow.
- The retained audio path avoids a PCB respin if guardian-authorized live IP
  voice is added later; traditional PSTN calling is a software non-feature.
- Peripheral drivers and sensor-fusion work expand, but the MCU, modem,
  inter-processor contract, power-domain architecture, and edge-AI toolchain
  remain stable.

## Primary References

- Xiaomi 900 mAh product envelope: https://www.mi.com/global/product/xiaomi-smart-kids-watch/
- Air780EGH dual-SIM behavior: https://docs.openluat.com/air780egh/luatos/app/common/sim_switch/
- MAX30101: https://www.analog.com/en/products/max30101.html
- MAX30208: https://www.analog.com/en/products/max30208.html
- Bosch BMP390: https://www.bosch-sensortec.com/products/environmental-sensors/pressure-sensors/bmp390/
- 1.3-inch OLED reference drawing: https://files.seeedstudio.com/wiki/1.3inch_OLED_128%2A64-White-FPC_Datasheet/res/308020348_GME12864-110_Datasheet.pdf
- Waterproof USB-C overview: https://www.digikey.com/en/product-highlight/a/amphenol-commercial-products/waterproof-usb-type-c-connectors
