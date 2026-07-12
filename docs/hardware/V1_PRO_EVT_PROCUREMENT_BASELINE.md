---
document_status: authoritative
last_verified: 2026-07-12
verified_by: codex
owner: founder
baseline: 5 EVT devices plus bring-up spares
---

# EgoLink V1 Pro EVT Procurement Baseline

This list implements ADR-0005. Buy only the `Buy now` section immediately.
Bare production parts are deliberately split out because the schematic,
footprints, and JLCPCB assembly inventory must be checked before ordering.
Prices and stock are snapshots from 2026-07-12 and must be rechecked at order
time.

## 1. Buy Now: Development and Validation Hardware

| Priority | Exact item | Qty | Preferred channel | Purpose / acceptance |
|---|---|---:|---|---|
| P0 | `NRF54LM20-DK` | 2 | Mouser/DigiKey/Nordic authorized distributor; place backorder | Two independent nRF54LM20B boards for firmware/AI and power benchmarking |
| P0 | Air780EGH official core board or EVB | 2 | OpenLuat official Taobao channel linked from its documentation | LuatOS, LTE, GNSS, low-power, UART and recovery work |
| P0 | Air780EGH bare module | 10 | OpenLuat official channel | Five EVT boards plus assembly and rework spares |
| P0 | `EV_T5838-FX2` | 2 | DigiKey/Mouser | Always-on microphone and AAD/NPU experiments |
| P0 | QMI8658A breakout board | 3 | Waveshare or another board with published schematic | Motion data, interrupt, FIFO and power validation |
| P0 | AirAUDIO_1010 or official ES8311 audio board | 2 | OpenLuat official channel | Verify Air780EGH VoLTE/TTS codec, microphone and speaker path |
| P0 | `BQ25895EVM-664` | 1 | TI/DigiKey/Mouser | Charger, ship mode, load transient and battery power-path tests |
| P0 | MAX17048 evaluation/breakout board | 2 | ADI/Adafruit authorized channel | Battery-gauge comparison with the existing EgoLink driver |
| P1 | `LS013B7DH03` display | 3 | DigiKey authorized channel | Low-power UI bring-up and readability check |
| P1 | 1-cell protected Li-polymer, 700-900 mAh, 3-wire 10k NTC | 5 | Battery maker with datasheet and UN38.3 report | Bench runtime; do not freeze final dimensions from a marketplace photo |
| P1 | LTE wideband FPC antenna, 50 ohm, U.FL/I-PEX | 5 | OpenLuat/module vendor | EVT radio baseline, not final enclosure antenna |
| P1 | GNSS active antenna, 3.3 V, U.FL/I-PEX | 5 | OpenLuat/module vendor | EVT GNSS baseline, not final enclosure antenna |
| P1 | 8-ohm 1 W miniature speaker | 5 | LCSC/known acoustic supplier | Call and alert audio bench work |
| P1 | 3 V 10 mm coin vibration motor | 5 | LCSC/known motor supplier | Local alert interaction |
| P1 | Nano-SIM cards with data and VoLTE enabled | 3 | China Mobile, China Unicom, China Telecom | Registration, data, low-power and call comparison |

Current authorized-channel constraint: `NRF54LM20-DK` and the QFN
`nRF54LM20B-QGAA-R7` show zero stock and roughly 16-week factory lead time;
Mouser shows development-kit receipts beginning around late July 2026. Place a
backorder for two kits and submit Nordic's project-sampling form in parallel.
Do not buy nRF54LM20B from an untraceable broker.

## 2. Request / Backorder Now: Production Silicon

These quantities cover five EVT assemblies, board loss, and rework. Purchase
only from the manufacturer or an authorized distributor.

| Exact MPN | Qty | Status / action |
|---|---:|---|
| `nRF54LM20B-QGAA-R7` | 15 | Request project samples and backorder QFN52 cut tape; no broker substitution |
| `BQ25895RTWR` | 15 | LCSC `C80200` currently stocked; wait for schematic BOM lock before checkout |
| `MAX17048G+T10` | 15 | LCSC `C2682616` currently stocked; existing driver asset |
| `TPS62840DLCR` | 15 | LCSC `C2071859`; 3.0 V always-on buck |
| `TPS7A0218PDBVR` | 15 | LCSC `C3748843`; 1.8 V T5838 rail |
| `TPS22965DSGR` | 15 | LCSC `C122837`; 6 A cellular load switch |
| `QMI8658A` | 20 | LCSC `C3021082`; six-axis IMU |
| `MMICT5838-00-012` | 20 | DigiKey/Mouser authorized cut tape; JLCPCB `C7230692` is listed |
| `ES8311` | 20 | OpenLuat/LCSC authorized source; verify lot and stock before order |
| `NS4150B` | 20 | LCSC `C189961` |
| `W25Q128JVPIQ` | 20 | DigiKey authorized channel; 8-WSON 6x5 mm |
| `LS013B7DH03` | 8 | DigiKey authorized channel; includes display assembly spares |

## 3. Do Not Buy Until the Schematic Review

The following parts depend on reference layouts, antenna tuning, battery and
enclosure dimensions. Buying them now creates waste without accelerating the
project:

- nRF54LM20B crystals, RF matching network, 2.4 GHz antenna and SWF connector;
- BQ25895, TPS62840 and Air780EGH inductors and all high-current capacitors;
- USB-C or magnetic charging connector and ESD parts;
- final LTE/GNSS antenna elements and coax lengths;
- final analog call microphone, acoustic mesh and gasket;
- final battery cell, connector and NTC curve;
- buttons, vibration mount, speaker cavity, enclosure and flex cables;
- generic resistors/capacitors and PCB fabrication quantity.

These become a separate JLCPCB-ready BOM only after schematic ERC, footprint
review, manufacturer reference-design comparison, and a supply check on the
same day as checkout.

## 4. Order Notes

- Mark every invoice and package with full MPN, channel, date code and lot.
- Keep one unopened sample of every critical IC lot.
- Do not accept `nRF54LM20A` as a substitute: it is pin-compatible but has no
  Axon NPU and would remove the performance model's central capability.
- Do not substitute Air780EPM/EGP: the lower-memory variants do not support the
  required audio path. Air780EGH is the frozen GNSS plus external-codec part.
- The screen is reflective and has no backlight. Readability in darkness uses
  a separately switched side light only if user testing requires it.
- PPK2 is already available and is not repurchased. It is suitable for the
  always-on domain; use the BQ25895 EVM, oscilloscope and current probe for 4G
  transient validation.

## 5. Estimated First Purchase Budget

Allow approximately CNY 3,000-5,000 for the development/validation hardware,
international freight and tax, excluding the later custom-PCB components.
Do not optimize this estimate by dropping the second nRF board or second
microphone board; independent bring-up and power measurement save more time
than they cost.

## 6. Stock Evidence Snapshot

- nRF54LM20B QFN: https://www.digikey.com/en/products/detail/nordic-semiconductor-asa/NRF54LM20B-QGAA-R7/29209035
- nRF54LM20 DK: https://www.nordicsemi.com/Products/Development-hardware/nRF54LM20-DK/Hardware-files
- T5838 evaluation board: https://www.digikey.com/en/products/detail/tdk-invensense/EV-T5838-FX2/16903856
- QMI8658A: https://www.lcsc.com/brand/1249-11546.html
- BQ25895: https://www.lcsc.com/product-detail/Battery-Management-ICs_Texas-Instruments-BQ25895RTWR_C80200.html
- MAX17048: https://www.lcsc.com/product-detail/battery-management_analog-devices-inc-maxim-integrated-max17048g-t10_C2682616.html
- TPS62840: https://www.lcsc.com/product-detail/dc-dc-converters_texas-instruments-tps62840dlcr_C2071859.html
- TPS7A02: https://www.lcsc.com/product-detail/C3748843.html
- TPS22965: https://www.lcsc.com/product-detail/C122837.html
- W25Q128JVPIQ: https://www.digikey.com/en/products/detail/winbond-electronics/W25Q128JVPIQ/6819668
- LS013B7DH03: https://www.digikey.com/en/products/filter/lcd-oled-graphic/107
