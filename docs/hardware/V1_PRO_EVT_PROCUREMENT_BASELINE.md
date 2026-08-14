---
document_status: superseded
last_verified: 2026-08-14
verified_by: codex
owner: founder
baseline: 5 EVT devices plus bring-up spares
---

# EgoLink V1 Pro EVT Procurement Baseline

> **Superseded 2026-08-14:** ADR-0008 replaces the V1 Pro watch/BOM route.
> Stop new purchases from this list. Existing items, if already acquired, are
> evaluation assets only. The current EgoLink Core A0 candidate list requires
> new official-document, schematic, sourcing, and founder gates before a new
> procurement baseline may be issued.

This list implements ADR-0005, the ADR-0006 peripheral revision, and the final
product envelope in
`docs/product/V1_PRO_FORM_FACTOR_BASELINE.md`. The first custom PCB is a
form-factor EVT board, not a loose desktop board. Buy only the reduced
`Buy now` section immediately.
Bare production parts are deliberately split out because the schematic,
footprints, and JLCPCB assembly inventory must be checked before ordering.
Prices and stock are snapshots from 2026-07-13 and must be rechecked at order
time.

## 1. Buy Now: Development and Validation Hardware

| Priority | Exact item | Qty | Preferred channel | Purpose / acceptance |
|---|---|---:|---|---|
| P0 | `NRF54LM20-DK` | 1 | Mouser/DigiKey/Nordic authorized distributor; place backorder | Known-good NPU target and SWD/J-Link reference for the custom board |
| P0 | Air780EGH bare module | 10 | OpenLuat official channel | Five EVT boards plus assembly and rework spares |
| P1 | 1.3-inch white COG OLED samples, `SH1106G`, 128x64 SPI, `GME12864-110` envelope | 5 | Display maker or authorized sample channel | Optical, outdoor readability, FPC and lifetime comparison; no breakout PCB in the product |
| P1 | Custom protected Li-polymer samples, nominal 900 mAh, 3-wire 10k NTC, max target 7.2 x 34.5 x 39.0 mm | 5 | Battery maker with drawing, UN38.3 and swelling data | Mechanical fit and measured runtime; reject marketplace-only capacity claims |
| P1 | `TYPE-C 16PFS LTH7.45 IPX8` (`C3020055`) and one TE/Hirose/Amphenol IPX8 USB-C candidate | 10 each | LCSC plus authorized distributor | Connector-envelope, cable-strain, ingress and cost comparison |
| P1 | LTE wideband FPC antenna, 50 ohm, U.FL/I-PEX | 5 | OpenLuat/module vendor | EVT radio baseline, not final enclosure antenna |
| P1 | GNSS active antenna, 3.3 V, U.FL/I-PEX | 5 | OpenLuat/module vendor | EVT GNSS baseline, not final enclosure antenna |
| P1 | 8-ohm 1 W miniature speaker | 5 | LCSC/known acoustic supplier | Call and alert audio bench work |
| P1 | 3 V 10 mm coin vibration motor | 5 | LCSC/known motor supplier | Local alert interaction |
| P1 | Nano-SIM cards with data service | 3 | China Mobile, China Unicom, China Telecom | Registration, data, low-power and coverage comparison; PSTN calling is not a V1 feature |

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
| `MAX30101EFD+T` | 15 | LCSC `C2859066`; optical pulse/SpO2 research signal, rear optical window required |
| `MAX30208CLB+T` | 15 | LCSC `C2874216`; skin-temperature trend, thermal-island layout required |
| `BMP390` | 15 | LCSC `C5124834`; pressure/altitude context, hydrophobic vent required |
| `ES8311` | 20 | OpenLuat/LCSC authorized source; verify lot and stock before order |
| `NS4150B` | 20 | LCSC `C189961` |
| `W25Q128JVPIQ` | 20 | DigiKey authorized channel; 8-WSON 6x5 mm |
| 1.3-inch `SH1106G` white COG OLED | 10 | Qualify two display suppliers against ADR-0006 FPC, glass and optical contract |

## 3. Do Not Buy Until the Schematic Review

The following parts depend on reference layouts, antenna tuning, battery and
enclosure dimensions. Buying them now creates waste without accelerating the
project:

- nRF54LM20B crystals, RF matching network, 2.4 GHz antenna and SWF connector;
- BQ25895, TPS62840 and Air780EGH inductors and all high-current capacitors;
- final IPX8 USB-C connector, CC resistors, wet-port circuit and ESD parts;
- final LTE/GNSS antenna elements and coax lengths;
- final interaction microphone, acoustic membranes, pressure vent and gasket;
- production MFF2 eUICC/IoT-SIM and provisioning contract;
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
- The display is normally off. Qualify the white COG OLED for direct-sun
  readability, burn-in, low/high temperature, FPC life and screen-on energy.
- MAX30101 and MAX30208 are context sensors, not medical measurement claims.
- Do not freeze an MFF2 eUICC vendor before operator provisioning, account,
  real-name registration and replacement workflows are contractually clear.
- PPK2 is already available and is not repurchased. It is suitable for the
  always-on domain; use the custom-board shunts, oscilloscope and current probe
  for 4G transient validation.

## 5. Estimated First Purchase Budget

The reduced direct-to-form-factor route is expected to keep the initial
off-board purchase near CNY 3,000-5,000 including sensor, display, connector
and battery samples, international freight and tax, but excluding custom PCBA
and enclosure fabrication.

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
- MAX30101: https://www.lcsc.com/product-detail/C2859066.html
- MAX30208: https://www.lcsc.com/product-detail/C2874216.html
- BMP390: https://www.lcsc.com/product-detail/pressure-sensors_bosch-bmp390_C5124834.html
- OLED reference drawing: https://files.seeedstudio.com/wiki/1.3inch_OLED_128%2A64-White-FPC_Datasheet/res/308020348_GME12864-110_Datasheet.pdf
- EVT IPX8 USB-C: https://www.lcsc.com/product-detail/usb-connectors_shou-han-type-c-16pfs-lth7-45-ipx8_C3020055.html
